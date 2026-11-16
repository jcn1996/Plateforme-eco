"""Tests de l'agent trader (démo) : données de test construites de toutes pièces (tests/fabrique.py), cours simulés,
dossier temporaire. Les vrais config/ et data/ ne sont jamais lus ni modifiés ; aucun accès au réseau."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import unittest
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.trader import performance as F
from agents.trader import portefeuille as P
from agents.trader import strategie as S
from agents.trader.agent import charger_config, executer
from agents.trader.sources import FournisseurSimule
from agents.trader.tests.fabrique import PARIS, SELECTION_ENTREPRISES, evaluation, preparer, simuler

SAMEDI = datetime(2026, 11, 7, 22, 30, tzinfo=timezone.utc)
LUNDI_MATIN = datetime(2026, 11, 9, 7, 33, tzinfo=timezone.utc)
DECEMBRE = datetime(2026, 12, 1, 7, 33, tzinfo=timezone.utc)  # premier jour de décision de décembre : rééquilibrage mensuel


def paris(**changements):
    """Évaluations des paris pays, avec des changements {cle: {champ: valeur}}."""
    res = []
    for c, n, e, f, ok, so, r in PARIS:
        x = evaluation(c, n, e, f, ok, so, r)
        x.update(changements.get(c, {}))
        res.append(x)
    return res


def setUpModule():
    logging.disable(logging.INFO)  # journaux de l'agent inutiles dans la sortie des tests


def tearDownModule():
    logging.disable(logging.NOTSET)


def lire(chemin: Path):
    return json.loads(chemin.read_text(encoding="utf-8"))


class BaseTrader(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trader-"))
        self.data = self.tmp / "data"
        self.config = charger_config()
        self.f = FournisseurSimule(debut="2025-09-01")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lancer(self, maintenant, mode="horaire", forcer=False, **prep):
        preparer(self.data, maintenant, **prep)
        return executer(self.f, self.config, self.data, maintenant, mode, forcer=forcer)

    def investir(self, **prep):
        """Décision lundi 7 h 33, exécution lundi 15 h 05."""
        self.lancer(LUNDI_MATIN, "decision", **prep)
        return self.lancer(LUNDI_MATIN.replace(hour=15, minute=5), **prep)


class TestDecision(BaseTrader):
    def test_premiere_decision_changement_de_methode(self):
        r = self.lancer(LUNDI_MATIN, "decision")
        d = r["decision"]
        self.assertEqual(d["type"], "changement de méthode")
        cm = self.config["methode"]
        c = d["cibles"]
        lignes = c["lignes"]
        self.assertAlmostEqual(sum(c["poches"].values()), 100, delta=0.05)
        # structure : 15 lignes au plus, 4 à 8 % par ligne
        self.assertLessEqual(len(lignes), cm["max_lignes"])
        for l in lignes:
            self.assertGreaterEqual(l["cible"], cm["ligne_min"] - 1e-6, l["nom"])
            self.assertLessEqual(l["cible"], cm["ligne_max"] + 1e-6, l["nom"])
        # poches : entreprises 70-85 %, matières 0-20 %, ETF pays 0-15 % (3 lignes au plus)
        self.assertTrue(cm["entreprises"]["min_pct"] - 1e-6 <= c["poches"]["entreprises"] <= cm["entreprises"]["max_pct"] + 1e-6, c["poches"])
        self.assertLessEqual(c["poches"]["matieres"], cm["matieres"]["max_pct"] + 1e-6)
        self.assertLessEqual(c["poches"]["pays"], cm["pays"]["max_pct"] + 1e-6)
        pays = [l for l in lignes if l["poche"] == "pays"]
        self.assertEqual({l["symbole"] for l in pays}, {"EWJ", "EWY", "INDA"}, "les 3 paris de plus forte tendance (pas le Mexique, 4e)")
        # 25 % au plus par secteur : 3 sociétés de technologie sur 4
        tech = [l for l in lignes if l.get("secteur") == "Information Technology"]
        self.assertLessEqual(sum(l["cible"] for l in tech), cm["entreprises"]["max_secteur_pct"] + 1e-6)
        self.assertEqual(len(tech), 3)
        # matières : supports cotés (PALL, GLD) ; cacao sans support écarté ; jamais d'ETF monde
        symboles = {l["symbole"] for l in lignes}
        self.assertTrue({"PALL", "GLD"} <= symboles)
        self.assertFalse(set(self.config["etf_monde"]) & symboles)
        ecartees = {x["nom"]: x["raison"] for x in d["ecartees"]}
        self.assertIn("aucun support coté", ecartees["Cacao"])
        self.assertIn("secteur", ecartees["Société S04"])
        # ordres en attente de l'ouverture, chacun justifié ; méthode enregistrée avec sa date
        self.assertFalse(r["executees"])
        self.assertEqual(len(r["etat"]["ordres"]), len(lignes))
        for o in r["etat"]["ordres"]:
            self.assertTrue(o["raison"]["texte"])
            self.assertTrue(o["donner_tort"])
        self.assertEqual(r["etat"]["methode"]["version"], cm["version"])
        self.assertEqual(r["etat"]["changements_methode"][0]["date"], "2026-11-09")
        # rapport de référence : le dernier recalibrage validé publié par le chef d'orchestre (jamais en dur dans les réglages)
        self.assertNotIn("rapport", cm)
        self.assertEqual(r["etat"]["methode"]["rapport"], "data/backtest/rapport-2026-11.md")
        regles = " ".join(lire(self.data / "portefeuille.json")["donnees"]["regles"])
        self.assertIn("data/backtest/rapport-2026-11.md", regles)
        self.assertIn("Goodwill / actif + Rendement du FCF", regles, "combinaisons en service lues dans les sélections du chef")
        self.assertIn("Niveau historique + Positionnement CFTC", regles)
        pf = lire(self.data / "portefeuille.json")["donnees"]
        self.assertEqual(pf["changements_methode"][0]["date"], "2026-11-09")
        self.assertEqual(pf["mention"], "Portefeuille fictif à but de démonstration, aucun ordre réel.")
        self.assertFalse(lire(self.data / "portefeuille.json")["meta"]["fictif"])

    def test_peu_de_candidats_le_reste_en_liquidites(self):
        modifs = {("selections", None): {"entreprises": SELECTION_ENTREPRISES[4:9], "matieres": [], "evaluations": []}}
        d = self.lancer(LUNDI_MATIN, "decision", modifs=modifs)["decision"]
        c = d["cibles"]
        self.assertEqual(len(c["lignes"]), 5)
        for l in c["lignes"]:
            self.assertAlmostEqual(l["cible"], self.config["methode"]["ligne_max"], places=6)
        self.assertAlmostEqual(c["poches"]["liquidites"], 60, places=4)
        self.assertTrue(any("liquidités" in a for a in d["avertissements"]))

    def test_une_seule_decision_par_jour(self):
        self.lancer(LUNDI_MATIN, "decision")
        r = self.lancer(LUNDI_MATIN.replace(hour=15, minute=5))
        self.assertTrue(r["executees"])
        n = len(r["etat"]["ordres"])
        r = self.lancer(LUNDI_MATIN.replace(hour=17, minute=46), "decision")
        self.assertIsNone(r["decision"], "la décision du jour n'est pas recalculée")
        self.assertEqual(len(r["etat"]["ordres"]), n)
        r = self.lancer(LUNDI_MATIN.replace(hour=18, minute=5), "decision", forcer=True)
        self.assertIsNotNone(r["decision"], "--forcer permet de refaire la décision (usage manuel)")

    def test_execution_au_premier_cours_apres_la_decision(self):
        r = self.investir()
        self.assertTrue(r["executees"])
        for op in r["executees"]:
            self.assertGreaterEqual(op["date"], op["decide_le"])
            self.assertEqual(op["date"], "2026-11-09T14:30:00Z", "première barre après la décision")
            self.assertAlmostEqual(op["frais_eur"], op["montant_eur"] * 0.001, delta=0.011)
            self.assertGreater(op["prix_local"], op["cours_marche"], "écart achat/vente payé à l'achat")
            self.assertNotIn("stop", op, "plus de stop")
        v = r["valo"]
        self.assertAlmostEqual(v["valeur"], v["liquidites"] + sum(p["valeur_eur"] for p in r["etat"]["positions"].values()), delta=0.01)
        self.assertLessEqual(len(r["etat"]["positions"]), 15)
        self.assertEqual({p["poche"] for p in r["etat"]["positions"].values()}, {"entreprises", "matieres", "pays"})

    def test_jamais_un_cours_passe(self):
        t = LUNDI_MATIN.replace(hour=16, minute=10)
        self.lancer(t, "decision")
        r = self.lancer(t.replace(hour=18, minute=5))
        self.assertTrue(r["executees"])
        for op in r["executees"]:
            self.assertEqual(op["date"], "2026-11-09T16:30:00Z")

    def test_decision_du_samedi_executee_lundi(self):
        self.lancer(SAMEDI, "decision")
        r = self.lancer(SAMEDI + timedelta(hours=10))  # dimanche : marchés fermés
        self.assertFalse(r["executees"])
        r = self.lancer(LUNDI_MATIN.replace(hour=15, minute=5), age_chef_h=0.5)
        self.assertTrue(r["executees"])

    def test_devise_en_sous_unites(self):
        self.assertEqual(P.devise_de("DDD.L", "GBP", self.config, {}), "GBp", "Londres cote en pence, quelle que soit la devise des comptes")
        self.assertAlmostEqual(P.en_euros(100, "GBp", {"GBP": 0.8}), 1.25)


class TestAttente(BaseTrader):
    def test_chef_perime(self):
        r = self.lancer(LUNDI_MATIN, "decision", age_chef_h=40)
        self.assertIsNone(r["decision"])
        self.assertTrue(any("chef d'orchestre" in x for x in r["attente"]["raisons"]))
        self.assertFalse(r["etat"]["ordres"])
        self.assertTrue(r["sante"]["degrade"])
        self.assertEqual(lire(self.data / "portefeuille.json")["donnees"]["statut"]["etat"], "en attente")

    def test_chef_degrade_mais_donnees_completes(self):
        """Un chef d'orchestre « dégradé » pour une raison étrangère à ses données (ex. Gemini en 503) ne bloque pas."""
        r = self.lancer(LUNDI_MATIN, "decision", chef_degrade=True)
        self.assertIsNotNone(r["decision"])
        self.assertIsNone(r["attente"])

    def test_donnees_du_chef_incompletes(self):
        cas = {
            "entrée manquante": ({("entrees", None): {"retirer": "entreprises"}}, "entrée « entreprises » manquante"),
            "scores absents": ({("pays", f"pays-{c}"): {"score": None} for c in ("US", "JP", "KR", "DE", "IN")}, "sans score ni verdict"),
            "liste vide": ({("vider", "pays"): {}}, "aucune ligne « pays »"),
            "sélections absentes": ({("selections", None): None}, "sélections du backtest absentes"),
        }
        for nom, (modifs, attendu) in cas.items():
            with self.subTest(nom):
                shutil.rmtree(self.data, ignore_errors=True)
                r = self.lancer(LUNDI_MATIN, "decision", modifs=modifs)
                self.assertIsNone(r["decision"])
                self.assertTrue(any(attendu in x for x in r["attente"]["raisons"]), r["attente"]["raisons"])

    def test_palier_de_risque_absent(self):
        r = self.lancer(LUNDI_MATIN, "decision", palier=None)
        self.assertIsNone(r["decision"])
        self.assertTrue(any("palier" in x for x in r["attente"]["raisons"]))

    def test_analyse_du_jour_absente_puis_rattrapage_horaire(self):
        r = self.lancer(LUNDI_MATIN, "decision", analyse_du_jour=False)
        self.assertIsNone(r["decision"])
        r = self.lancer(LUNDI_MATIN.replace(hour=9, minute=5))
        self.assertIsNotNone(r["decision"], "la première exécution horaire où les données sont prêtes décide")
        r = self.lancer(LUNDI_MATIN.replace(hour=10, minute=5))
        self.assertIsNone(r["decision"], "une seule décision par jour")


class TestVerificationMensuelle(BaseTrader):
    """Ni stop ni prise de bénéfices : vente quand l'actif sort de sa combinaison, vérifiée une fois par mois."""
    SANS_S05 = {("selections", None): {"entreprises": [x for x in SELECTION_ENTREPRISES if x[0] != "S05"]}}

    def test_sortie_de_combinaison_au_rééquilibrage_du_mois(self):
        self.investir()
        self.assertIn("S05", lire(self.data / "trader" / "etat.json")["positions"])
        r = self.lancer(LUNDI_MATIN + timedelta(days=1), "decision", modifs=self.SANS_S05)
        self.assertNotIn("cibles", r["decision"], "pas de rééquilibrage avant le mois suivant")
        self.assertIn("vérification mensuelle", r["decision"]["resume"])
        self.assertFalse([o for o in r["etat"]["ordres"] if o["symbole"] == "S05"])
        self.assertFalse(r["imposes"])
        r = self.lancer(DECEMBRE, "decision", modifs=self.SANS_S05)
        self.assertEqual(r["decision"]["type"], "rééquilibrage mensuel")
        vente = [o for o in r["etat"]["ordres"] if o["symbole"] == "S05"]
        self.assertEqual([(o["sens"], o["motif"]) for o in vente], [("vente", "sortie de combinaison")])
        self.assertIn("n'est plus retenue par sa combinaison", vente[0]["raison"]["texte"])

    def test_forte_hausse_sans_prise_de_benefices(self):
        self.f.chocs = {"S06": [("2026-11-10", 1.8)], "S07": [("2026-11-10", 0.6)]}
        self.investir()
        r = self.lancer((LUNDI_MATIN + timedelta(days=7)).replace(hour=15, minute=5))
        self.assertFalse(r["imposes"], "ni stop après −40 %, ni prise de bénéfices après +80 %")
        self.assertTrue({"S06", "S07"} <= set(r["etat"]["positions"]))
        # rééquilibrage du mois : la ligne trop lourde revient vers 8 % au plus, sans être vendue en totalité
        d = self.lancer(DECEMBRE, "decision")["decision"]
        arb = {a["symbole"]: a for a in d["arbitrages"]}
        self.assertEqual(arb["S06"]["action"], "réduction")
        self.assertIn("S06", r["etat"]["positions"])

    def test_lignes_detenues_avant_les_nouvelles(self):
        self.investir()
        tenues = {s for s, p in lire(self.data / "trader" / "etat.json")["positions"].items() if p["poche"] == "entreprises"}
        nouvelles = [("N01", "Energy"), ("N02", "Health Care"), ("N03", "Materials")]
        modifs = {("selections", None): {"entreprises": nouvelles + SELECTION_ENTREPRISES}}  # mieux classées que les détenues
        d = self.lancer(DECEMBRE, "decision", modifs=modifs)["decision"]
        retenues = {l["symbole"] for l in d["cibles"]["lignes"] if l["poche"] == "entreprises"}
        self.assertTrue(tenues <= retenues, "toujours retenues par leur combinaison : gardées")


class TestListeUnique(BaseTrader):
    """Le trader n'achète que dans la liste unique du chef d'orchestre ; une sortie de liste en cours de mois est vendue."""
    GARDER = ["selection-S01", "selection-S05", "selection-S06", "selection-S07", "selection-S08", "matiere-palladium", "pays-JP"]

    def test_achats_limites_a_la_liste(self):
        r = self.lancer(LUNDI_MATIN, "decision", modifs={("liste", None): {"garder": self.GARDER}})
        symboles = {l["symbole"] for l in r["decision"]["cibles"]["lignes"]}
        self.assertTrue(symboles)
        self.assertTrue(symboles <= {"S01", "S05", "S06", "S07", "S08", "PALL", "EWJ"} | {s["symbole"] for s in self.config["supports"].get("matiere-palladium", [])},
                        symboles)
        self.assertNotIn("S02", symboles)

    def test_sortie_de_liste_en_cours_de_mois(self):
        self.investir(modifs={("liste", None): {"garder": self.GARDER}})
        self.assertIn("S05", lire(self.data / "trader" / "etat.json")["positions"])
        garder = [i for i in self.GARDER if i != "selection-S05"]
        r = self.lancer(LUNDI_MATIN + timedelta(days=2, hours=1), modifs={("liste", None): {"garder": garder, "sorties": ["selection-S05"]}})
        vente = [o for o in r["imposes"] if o["symbole"] == "S05"]
        self.assertEqual([o["motif"] for o in vente], ["sortie de la liste"])
        self.assertIn("confirmée 5 jours de suite", vente[0]["raison"]["texte"])
        self.assertFalse([o for o in r["imposes"] if o["symbole"] in ("S01", "S06")], "les autres lignes de la liste restent")


class TestParisPays(BaseTrader):
    def test_sortie_des_qu_un_exces_se_declenche_et_journal(self):
        self.investir()
        exces = ["valorisation tendue (25/100 : au-delà du 70e percentile)"]
        modifs = {("selections", None): {"evaluations": paris(JP={"entree_ok": False, "sortie": True, "raisons_sortie": exces, "raisons_refus": exces})}}
        mardi = LUNDI_MATIN + timedelta(days=1)
        r = self.lancer(mardi.replace(hour=9, minute=5), modifs=modifs)
        sortie = [o for o in r["imposes"] if o["symbole"] == "EWJ"]
        self.assertEqual([o["motif"] for o in sortie], ["excès"], "vente dès que l'excès se déclenche, sans attendre le mois suivant")
        self.assertIn("valorisation tendue", sortie[0]["raison"]["texte"])
        self.lancer(mardi.replace(hour=15, minute=5), modifs=modifs)
        pf = lire(self.data / "portefeuille.json")["donnees"]
        p = next(x for x in pf["paris_pays"] if x["symbole"] == "EWJ")
        self.assertEqual(p["statut"], "clos")
        for champ in ("entree_le", "raison_entree", "sortie_le", "raison_sortie", "performance_pct", "msci_world_pct", "ecart_points"):
            self.assertIsNotNone(p.get(champ), champ)
        self.assertIn("pari pays", p["raison_entree"])
        ouverts = [x for x in pf["paris_pays"] if x["statut"] == "ouvert"]
        self.assertEqual({x["symbole"] for x in ouverts}, {"EWY", "INDA"})
        self.assertTrue(all(x.get("performance_pct") is not None for x in ouverts))

    def test_tendance_cassee(self):
        self.investir()
        cassee = ["tendance cassée : 12 mois hors dernier mois −2,0 %, cours sous la moyenne 200 jours"]
        modifs = {("selections", None): {"evaluations": paris(KR={"entree_ok": False, "sortie": True, "raisons_sortie": cassee, "raisons_refus": cassee})}}
        r = self.lancer(LUNDI_MATIN + timedelta(days=2, hours=2), modifs=modifs)
        self.assertEqual([o["motif"] for o in r["imposes"] if o["symbole"] == "EWY"], ["sortie de tendance"])

    def test_pari_garde_sans_exces_ni_cassure(self):
        """Une condition d'entrée manque désormais (valorisation non publiée), mais ni excès ni cassure : le pari reste."""
        self.investir()
        modifs = {("selections", None): {"evaluations": paris(IN={"entree_ok": False, "raisons_refus": ["valorisation relative non disponible"]})}}
        r = self.lancer(DECEMBRE, "decision", modifs=modifs)
        self.assertIn("INDA", {l["symbole"] for l in r["decision"]["cibles"]["lignes"]})
        self.assertFalse([o for o in r["etat"]["ordres"] if o["symbole"] == "INDA" and o["sens"] == "vente" and o["quantite"] and o["motif"] != "rééquilibrage"])


class TestChangementDeMethode(BaseTrader):
    def test_lignes_de_l_ancienne_methode_vendues_et_historique_conserve(self):
        etat = P.etat_initial(self.config, LUNDI_MATIN - timedelta(days=30))
        etat["liquidites"] = 40000.0
        for s, poche in (("SPY", "coeur"), ("XLV", "coeur"), ("BBB", "satellite"), ("EWU", "tendance")):
            etat["positions"][s] = {"symbole": s, "nom": s, "quantite": 100, "prix_revient_eur": 150, "prix_revient_local": 165, "dernier_cours_eur": 150,
                                    "poids": 15, "poche": poche, "classe": "actions", "type": "pays", "devise": "USD", "cout_total_eur": 15000,
                                    "ouverte_le": "2026-10-01T14:30:00Z", "realise_eur": 0.0, "frais_eur": 0.0}
        etat["historique"] = {"2026-10-15": {"portefeuille": 99000.0, "msci_world": 100500.0}}
        (self.data / "trader").mkdir(parents=True, exist_ok=True)
        (self.data / "trader" / "etat.json").write_text(json.dumps(etat), encoding="utf-8")
        r = self.lancer(LUNDI_MATIN, "decision")
        d = r["decision"]
        self.assertEqual(d["type"], "changement de méthode")
        ventes = {o["symbole"]: o for o in r["etat"]["ordres"] if o["sens"] == "vente"}
        self.assertEqual(set(ventes), {"SPY", "XLV", "BBB", "EWU"}, "toutes les lignes de l'ancienne méthode, en une fois")
        for o in ventes.values():
            self.assertEqual(o["motif"], "changement de méthode")
            self.assertIn("ancienne méthode", o["raison"]["texte"])
        r = self.lancer(LUNDI_MATIN.replace(hour=15, minute=5))
        ops = lire(self.data / "trader" / "operations.json")["donnees"]
        self.assertEqual({o["symbole"] for o in ops if o["motif"] == "changement de méthode"}, {"SPY", "XLV", "BBB", "EWU"})
        pf = lire(self.data / "portefeuille.json")["donnees"]
        self.assertEqual(pf["historique"][0]["date"], "2026-10-15", "historique de performance conservé")
        self.assertEqual(pf["changements_methode"][0]["date"], "2026-11-09")
        self.assertEqual(pf["methode"]["depuis"], "2026-11-09")
        # une seconde décision le mois suivant n'est plus un changement de méthode
        self.assertEqual(self.lancer(DECEMBRE, "decision")["decision"]["type"], "rééquilibrage mensuel")
        self.assertEqual(len(lire(self.data / "trader" / "etat.json")["changements_methode"]), 1)


class TestPoches(BaseTrader):
    def test_indice_de_poche_neutre_aux_achats_et_ventes(self):
        h = {"2026-11-09": {"poches": {"entreprises": 1010.0}, "msci_world": 100.0},
             "2026-11-10": {"poches": {"entreprises": 2110.5}, "msci_world": 101.0},  # +1 000 achetés en début de journée, puis +5 %
             "2026-11-11": {"poches": {"entreprises": 1050.0}, "msci_world": 102.0}}  # 1 060,50 vendus en fin de journée, cours inchangés
        flux = {"2026-11-09": {"entreprises": 1000.0}, "2026-11-10": {"entreprises": 1000.0}, "2026-11-11": {"entreprises": -1060.5}}
        pts = F.indice_poche(h, flux, "entreprises")
        self.assertAlmostEqual(pts[0][1], 101.0)
        self.assertAlmostEqual(pts[1][1], 101.0 * 1.05, places=6)
        self.assertAlmostEqual(pts[2][1], 101.0 * 1.05, places=6)
        etat = {"historique": h, "flux_poches": flux}
        r = F.performance_poches(etat, "2026-11-09")["entreprises"]
        self.assertAlmostEqual(r["performance"], 6.05, places=2)
        self.assertAlmostEqual(r["msci_world"], 2.0, places=2)
        self.assertAlmostEqual(r["ecart_points"], 4.05, places=2)

    def test_suivi_separe_contre_le_msci_world(self):
        self.investir()
        for j in (1, 2, 3):
            r = self.lancer((LUNDI_MATIN + timedelta(days=j)).replace(hour=15, minute=5))
        st = lire(self.data / "portefeuille.json")["donnees"]["statistiques"]["poches"]
        for poche in ("entreprises", "matieres", "pays"):
            self.assertEqual(st[poche]["depuis"], "2026-11-09")
            self.assertGreaterEqual(st[poche]["jours"], 4)
            self.assertIsNotNone(st[poche]["performance"])
            self.assertIsNotNone(st[poche]["msci_world"])
        self.assertAlmostEqual(sum(st[p]["valeur_eur"] for p in st) + r["valo"]["liquidites"], r["valo"]["valeur"], delta=0.05)


class TestRegles(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()

    def test_seuil_de_reequilibrage(self):
        maintenant = datetime(2026, 12, 1, 8, tzinfo=timezone.utc)
        etat = P.etat_initial(self.config, maintenant)
        etat["positions"] = {"S01": {"symbole": "S01", "nom": "S01", "quantite": 10, "prix_revient_eur": 500, "dernier_cours_eur": 500, "poids": 5,
                                     "poche": "entreprises", "classe": "actions", "devise": "USD", "cout_total_eur": 5000, "ouverte_le": "2026-11-09T14:30:00Z"}}
        e = {"cible": 7, "poche": "entreprises", "classe": "actions", "zone": "Amérique du Nord", "support": {"symbole": "S01", "nom": "S01", "devise": "USD"},
             "ligne": {"id": "selection-S01", "type": "entreprises", "raison": "test"}}
        c = {"lignes": {"S01": e}, "exclusions": {}}
        valo = {"valeur": 100000, "liquidites": 95000}
        ordres, _, arb = S.generer_ordres(c, etat, valo, self.config, maintenant)
        self.assertFalse(ordres, "écart de 2 points : sous le seuil de 3 points")
        self.assertEqual(arb[0]["action"], "conservée")
        e["cible"] = 8
        etat["positions"]["S01"]["poids"] = 3.5  # sous 4 % : rééquilibrée même sous le seuil
        ordres, _, _ = S.generer_ordres(c, etat, valo, self.config, maintenant)
        self.assertEqual([o["sens"] for o in ordres], ["achat"])
        etat["positions"]["S01"]["poids"] = 12  # au-dessus de 8 %
        ordres, _, _ = S.generer_ordres(c, etat, valo, self.config, maintenant)
        self.assertEqual([(o["sens"], o["motif"]) for o in ordres], [("vente", "rééquilibrage")])

    def test_statistiques(self):
        h = {f"2026-0{1 + i // 28}-{1 + i % 28:02d}": {"portefeuille": 100000 * (1 + 0.001 * i), "msci_world": 100000} for i in range(40)}
        pts = F.serie(h, "portefeuille")
        r = F.risque(pts, self.config)
        self.assertIsNotNone(r["sharpe"])
        self.assertEqual(r["perte_max"], 0)
        self.assertIsNotNone(F.perf_periode(pts, 30))
        self.assertIsNone(F.perf_periode(pts, 91))
        s = F.stats_operations([{"sens": "vente", "resultat": {"plus_value_eur": 100, "plus_value_pct": 10}},
                                {"sens": "vente", "resultat": {"plus_value_eur": -50, "plus_value_pct": -5}}, {"sens": "achat"}])
        self.assertEqual((s["taux_reussite"], s["gain_moyen_pct"], s["perte_moyenne_pct"]), (50, 10, -5))


class TestSimulation(BaseTrader):
    def test_simulation_trois_mois(self):
        """Trois mois simulés : règles respectées à chaque séance, un rééquilibrage par mois, ni stop ni prise de bénéfices."""
        self.f = FournisseurSimule(debut="2025-06-01", chocs={"S05": [("2026-09-15", 0.6)], "S06": [("2026-09-20", 1.5)]})
        moins_s07 = [x for x in SELECTION_ENTREPRISES if x[0] != "S07"]
        exces = ["accélération parabolique (test)"]
        ev = {"2026-10-12": {"modifs": {("selections", None): {"entreprises": moins_s07}}},
              "2026-10-20": {"modifs": {("selections", None): {"entreprises": moins_s07, "evaluations": paris(
                  KR={"entree_ok": False, "sortie": True, "raisons_sortie": exces, "raisons_refus": exces})}}}}
        res = simuler(executer, self.f, self.config, self.data, "2026-09-01", 92, heures=(15, 21), evenements=ev)
        self.assertTrue(all(r["ok"] for r in res))
        cm = self.config["methode"]
        for r in res:
            self.assertLessEqual(len(r["etat"]["positions"]), cm["max_lignes"])
        reeq = [r["decision"] for r in res if r["decision"] and r["decision"].get("cibles")]
        self.assertEqual([d["date"][:7] for d in reeq], ["2026-09", "2026-10", "2026-11", "2026-12"], "un rééquilibrage par mois")
        self.assertEqual(reeq[0]["type"], "changement de méthode")
        ops = lire(self.data / "trader" / "operations.json")["donnees"]
        motifs = {o["motif"] for o in ops}
        self.assertFalse({"stop", "prise de bénéfices", "plancher de liquidités"} & motifs)
        self.assertIn("excès", motifs, "pari pays vendu dès l'excès (20 octobre)")
        s07 = [o for o in ops if o["symbole"] == "S07" and o["sens"] == "vente"]
        self.assertEqual([o["motif"] for o in s07], ["sortie de combinaison"])
        self.assertTrue(s07[0]["date"].startswith("2026-11-02"), "vendue au rééquilibrage de novembre, pas avant")
        par_jour = defaultdict(set)
        for o in ops:
            self.assertGreaterEqual(o["date"], o["decide_le"])
            par_jour[(o["date"][:10], o["symbole"])].add(o["sens"])
        self.assertFalse([k for k, v in par_jour.items() if v == {"achat", "vente"}], "pas d'achat et de vente du même titre le même jour")
        pf = lire(self.data / "portefeuille.json")["donnees"]
        st = pf["statistiques"]
        self.assertIsNotNone(st["risque"]["sharpe"])
        self.assertAlmostEqual(sum(x["eur"] for x in st["attribution"]["poches"]), pf["valeur_actuelle"] - 100000, delta=1)
        for poche in ("entreprises", "matieres", "pays"):
            self.assertGreater(st["poches"][poche]["jours"], 40)
        self.assertTrue(any(p["statut"] == "clos" and p["symbole"] == "EWY" for p in pf["paris_pays"]))


if __name__ == "__main__":
    unittest.main()
