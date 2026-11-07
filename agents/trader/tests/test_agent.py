"""Tests de l'agent trader (démo) : données de test construites de toutes pièces (tests/fabrique.py), cours simulés,
dossier temporaire. Les vrais config/ et data/ ne sont jamais lus ni modifiés ; aucun accès au réseau."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.trader import performance as F
from agents.trader import portefeuille as P
from agents.trader import strategie as S
from agents.trader.agent import charger_config, executer
from agents.trader.sources import FournisseurSimule
from agents.trader.tests.fabrique import ENTREPRISES, preparer, simuler

SAMEDI = datetime(2026, 11, 7, 22, 30, tzinfo=timezone.utc)
LUNDI_MATIN = datetime(2026, 11, 9, 7, 33, tzinfo=timezone.utc)


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
        self.f = FournisseurSimule(debut="2026-06-01")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lancer(self, maintenant, mode="horaire", **prep):
        preparer(self.data, maintenant, **prep)
        return executer(self.f, self.config, self.data, maintenant, mode)


class TestDecision(BaseTrader):
    def test_premiere_decision(self):
        r = self.lancer(LUNDI_MATIN, "decision")
        d = r["decision"]
        self.assertIsNotNone(d)
        c = d["cibles"]
        self.assertAlmostEqual(sum(c["poches"].values()), 100, delta=0.05)
        self.assertGreaterEqual(c["poches"]["liquidites"], self.config["liquidites_min_par_palier"]["Vigilance"] - 1e-6)
        self.assertLessEqual(c["poches"]["satellite"], self.config["poches"]["satellite"] + 1e-6)
        sats = [l for l in c["lignes"] if l["poche"] == "satellite"]
        self.assertTrue(sats)
        for l in sats:
            self.assertLessEqual(l["cible"], self.config["satellites"]["max_ligne"] + 1e-6)
        noms = {l["symbole"] for l in sats}
        # forte ou moyenne, sans objection sérieuse, au moins 2 agents indépendants
        self.assertIn("AAA", noms)
        self.assertIn("CCC.T", noms)
        self.assertNotIn("EEE", noms, "objection sérieuse du contradicteur")
        self.assertNotIn("FFF", noms, "une seule source")
        self.assertNotIn("GGG", noms, "conviction faible")
        self.assertNotIn("HHH", noms, "verdict neutre")
        ecartes = {x["id"]: x["raison"] for x in d["satellites_ecartes"]}
        self.assertIn("une seule source", ecartes["entreprise-FFF"])
        # cœur : supports cotés ; pays sans ETF redistribué ; ligne « Alléger » exclue
        coeur = {l["symbole"] for l in c["lignes"] if l["poche"] == "coeur"}
        self.assertTrue({"SPY", "EWJ", "EWY", "GLD", "SHY", "IEF", "TLT", "IBGS.AS", "BNO"} <= coeur)
        self.assertNotIn("EWZ", coeur)
        self.assertFalse(any(s.endswith("=F") for s in coeur))
        # les ordres attendent l'ouverture : rien d'exécuté au moment de la décision
        self.assertFalse(r["executees"])
        self.assertTrue(r["etat"]["ordres"])
        for o in r["etat"]["ordres"]:
            self.assertTrue(o["raison"]["texte"])
            self.assertTrue(o["donner_tort"], "chaque décision dit ce qui pourrait lui donner tort")
        self.assertTrue(d["donner_tort"])
        pf = lire(self.data / "portefeuille.json")
        self.assertFalse(pf["meta"]["fictif"])
        self.assertTrue(pf["meta"]["demo"])
        self.assertEqual(pf["donnees"]["mention"], "Portefeuille fictif à but de démonstration, aucun ordre réel.")
        self.assertEqual(pf["donnees"]["valeur_actuelle"], 100000)

    def test_execution_au_premier_cours_apres_la_decision(self):
        self.lancer(LUNDI_MATIN, "decision")
        r = self.lancer(LUNDI_MATIN.replace(hour=15, minute=5))
        self.assertTrue(r["executees"])
        for op in r["executees"]:
            self.assertGreaterEqual(op["date"], op["decide_le"])
            self.assertEqual(op["date"], "2026-11-09T14:30:00Z", "première barre après la décision")
            self.assertAlmostEqual(op["frais_eur"], op["montant_eur"] * 0.001, delta=0.011)
            self.assertGreater(op["prix_local"], op["cours_marche"], "écart achat/vente payé à l'achat")
            self.assertEqual(op["quantite"], int(op["quantite"]))
        ops = lire(self.data / "trader" / "operations.json")["donnees"]
        self.assertEqual(len(ops), len(r["executees"]))
        o = ops[0]
        for champ in ("date", "sens", "symbole", "quantite", "prix_local", "prix_eur", "frais_eur", "raison", "donner_tort", "taux_change"):
            self.assertIn(champ, o)
        self.assertIn("verdict", o["raison"])
        self.assertIn("agents", o["raison"])
        sat = [x for x in ops if x["poche"] == "satellite"]
        self.assertTrue(all(x["stop"] for x in sat), "stop associé à chaque satellite")
        # valorisation cohérente : valeur = liquidités + positions, liquidités ≥ plancher (à la tolérance près)
        v = r["valo"]
        self.assertAlmostEqual(v["valeur"], v["liquidites"] + sum(p["valeur_eur"] for p in r["etat"]["positions"].values()), delta=0.01)
        self.assertLess(v["valeur"], 100000, "frais et écarts payés")
        self.assertGreater(v["valeur"], 99000)

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
        self.lancer(LUNDI_MATIN, "decision")
        o = next(o for o in lire(self.data / "trader" / "etat.json")["ordres"] if o["symbole"] == "DDD.L")
        self.assertEqual(o["devise"], "GBp", "Londres cote en pence, quelle que soit la devise des comptes")
        self.assertAlmostEqual(P.en_euros(100, "GBp", {"GBP": 0.8}), 1.25)
        self.assertAlmostEqual(P.en_euros(100, "USD", {"USD": 1.25}), 80)


class TestAttente(BaseTrader):
    def test_chef_perime(self):
        r = self.lancer(LUNDI_MATIN, "decision", age_chef_h=40)
        self.assertIsNone(r["decision"])
        self.assertTrue(any("chef d'orchestre" in x for x in r["attente"]["raisons"]))
        self.assertFalse(r["etat"]["ordres"])
        self.assertTrue(r["sante"]["degrade"])
        pf = lire(self.data / "portefeuille.json")["donnees"]
        self.assertEqual(pf["statut"]["etat"], "en attente")
        j = lire(self.data / "journal" / "agent-trader.json")
        self.assertTrue(j["donnees"][-1]["attente"])
        self.assertEqual(j["meta"]["sante"]["agent"], "trader")

    def test_chef_degrade(self):
        r = self.lancer(LUNDI_MATIN, "decision", chef_degrade=True)
        self.assertIsNone(r["decision"])
        self.assertTrue(any("dégradé" in x for x in r["attente"]["raisons"]))

    def test_analyse_du_jour_absente_puis_rattrapage_horaire(self):
        r = self.lancer(LUNDI_MATIN, "decision", analyse_du_jour=False)
        self.assertIsNone(r["decision"])
        r = self.lancer(LUNDI_MATIN.replace(hour=9, minute=5))
        self.assertIsNotNone(r["decision"], "la première exécution horaire où les données sont prêtes décide")
        self.assertIsNone(r["attente"])
        r = self.lancer(LUNDI_MATIN.replace(hour=10, minute=5))
        self.assertIsNone(r["decision"], "une seule décision par jour")


class TestRisque(BaseTrader):
    def _investir(self):
        self.lancer(LUNDI_MATIN, "decision")
        self.lancer(LUNDI_MATIN.replace(hour=15, minute=5))

    def test_stop_confirme_par_deux_releves(self):
        self.f.chocs = {"AAA": [("2026-11-10", 0.78)]}
        self._investir()
        mardi = LUNDI_MATIN + timedelta(days=1)
        r = self.lancer(mardi.replace(hour=15, minute=5))
        self.assertFalse([o for o in r["imposes"] if o["symbole"] == "AAA"], "un seul relevé : pas encore de stop")
        self.assertEqual(r["etat"]["positions"]["AAA"]["confirmations_stop"], 1)
        r = self.lancer(mardi.replace(hour=18, minute=5))
        stop = [o for o in r["imposes"] if o["symbole"] == "AAA"]
        self.assertEqual(len(stop), 1)
        self.assertEqual(stop[0]["motif"], "stop")
        r = self.lancer(mardi.replace(hour=21, minute=5))
        op = next(o for o in r["executees"] if o["symbole"] == "AAA")
        self.assertLess(op["resultat"]["plus_value_eur"], 0)
        self.assertTrue(op["resultat"]["solde"])
        self.assertNotIn("AAA", r["etat"]["positions"])
        # pas de rachat le lendemain malgré le verdict toujours positif
        r = self.lancer(mardi + timedelta(days=1), "decision")
        self.assertNotIn("AAA", {l["symbole"] for l in r["decision"]["cibles"]["lignes"]})

    def test_prise_de_benefices_et_stop_suiveur(self):
        self.f.chocs = {"BBB": [("2026-11-10", 1.4)]}
        self._investir()
        mardi = LUNDI_MATIN + timedelta(days=1)
        q0 = None
        r = self.lancer(mardi.replace(hour=15, minute=5))
        p = r["etat"]["positions"]["BBB"]
        q0 = p["quantite"]
        self.assertEqual(p["stop_type"], "suiveur")
        self.assertGreater(p["stop_local"], p["prix_revient_local"], "le suiveur protège un gain")
        pb = [o for o in r["imposes"] if o["symbole"] == "BBB"]
        self.assertEqual(pb[0]["motif"], "prise de bénéfices")
        self.assertEqual(pb[0]["quantite"], int(q0 * 0.33))
        r = self.lancer(mardi.replace(hour=18, minute=5))
        op = next(o for o in r["executees"] if o["symbole"] == "BBB")
        self.assertGreater(op["resultat"]["plus_value_eur"], 0)
        self.assertTrue(r["etat"]["positions"]["BBB"]["prise_benefices_faite"])
        r = self.lancer(mardi.replace(hour=21, minute=5))
        self.assertFalse([o for o in r["imposes"] if o["symbole"] == "BBB"], "une seule prise de bénéfices")

    def test_sortie_sur_eviter_et_objection(self):
        self._investir()
        mardi = LUNDI_MATIN + timedelta(days=1, minutes=-1)
        modifs = {("entreprises", "entreprise-AAA"): {"verdict": "Éviter"},
                  ("entreprises", "entreprise-CCC.T"): {"objection": {"objection": "Objection nouvelle.", "serieuse": True}}}
        r = self.lancer(mardi, modifs=modifs)
        motifs = {o["symbole"]: o["motif"] for o in r["imposes"]}
        self.assertEqual(motifs.get("AAA"), "sortie sur verdict")
        self.assertEqual(motifs.get("CCC.T"), "sortie sur objection")
        self.assertTrue(all(o["imposee"] for o in r["imposes"]))

    def test_pas_de_sortie_sur_verdict_si_chef_perime(self):
        self._investir()
        mardi = LUNDI_MATIN + timedelta(days=1, minutes=-1)
        r = self.lancer(mardi, modifs={("entreprises", "entreprise-AAA"): {"verdict": "Éviter"}}, age_chef_h=40)
        self.assertFalse([o for o in r["imposes"] if o["motif"] == "sortie sur verdict"])

    def test_plancher_de_liquidites_en_crise(self):
        self._investir()
        mardi = LUNDI_MATIN + timedelta(days=1, minutes=-1)
        r = self.lancer(mardi, palier="Crise")
        ventes = [o for o in r["imposes"] if o["motif"] == "plancher de liquidités"]
        self.assertTrue(ventes)
        r = self.lancer(mardi.replace(hour=15, minute=5), palier="Crise")
        self.assertGreaterEqual(r["donnees"]["liquidites_pct"], 35 - self.config["tolerance_plancher_points"] - 0.5)
        r = self.lancer(mardi.replace(hour=18, minute=5), palier="Crise")
        self.assertFalse([o for o in r["imposes"] if o["motif"] == "plancher de liquidités"], "plancher rétabli : plus de vente")


class TestRegles(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()

    def test_rotation_mensuelle(self):
        maintenant = datetime(2026, 11, 9, 8, tzinfo=timezone.utc)
        ops = [{"sens": "vente", "imposee": False, "montant_eur": 20000, "date": "2026-11-01T15:00:00Z"},
               {"sens": "vente", "imposee": True, "montant_eur": 50000, "date": "2026-11-02T15:00:00Z"},
               {"sens": "vente", "imposee": False, "montant_eur": 9000, "date": "2026-09-01T15:00:00Z"}]
        self.assertEqual(S.rotation_utilisee(ops, maintenant, 30), 20000)
        etat = P.etat_initial(self.config, maintenant)
        etat["positions"] = {"X": {"symbole": "X", "nom": "X", "quantite": 100, "prix_revient_eur": 150, "dernier_cours_eur": 150, "poids": 15,
                                   "poche": "coeur", "classe": "actions", "devise": "USD", "cout_total_eur": 15000}}
        c = {"lignes": {}, "sorties": {}, "liquidites": 10, "liquidites_min": 10}
        valo = {"valeur": 100000, "liquidites": 85000}
        ordres, notes = S.generer_ordres(c, etat, valo, ops, "Vigilance", self.config, maintenant)
        self.assertFalse(ordres, "30 % de 100 000 € moins 20 000 € déjà vendus : la vente de 15 000 € est reportée")
        self.assertTrue(any("rotation" in n for n in notes))
        c["sorties"] = {"X": ("sortie sur verdict", "test", True)}
        ordres, _ = S.generer_ordres(c, etat, valo, ops, "Vigilance", self.config, maintenant)
        self.assertEqual(len(ordres), 1, "une sortie imposée n'est jamais bloquée par la rotation")

    def test_seuil_de_reequilibrage(self):
        maintenant = datetime(2026, 11, 9, 8, tzinfo=timezone.utc)
        etat = P.etat_initial(self.config, maintenant)
        etat["positions"] = {"SPY": {"symbole": "SPY", "nom": "SPY", "quantite": 10, "prix_revient_eur": 500, "dernier_cours_eur": 500, "poids": 20,
                                     "poche": "coeur", "classe": "actions", "devise": "USD", "cout_total_eur": 5000}}
        e = {"cible": 22, "poche": "coeur", "classe": "actions", "support": {"symbole": "SPY", "nom": "SPY", "devise": "USD"}, "ligne": {"id": "pays-US"}}
        c = {"lignes": {"SPY": e}, "sorties": {}, "liquidites": 78, "liquidites_min": 10}
        valo = {"valeur": 100000, "liquidites": 80000}
        ordres, _ = S.generer_ordres(c, etat, valo, [], "Vigilance", self.config, maintenant)
        self.assertFalse(ordres, "écart de 2 points : sous le seuil de 3 points")
        e["cible"] = 24
        ordres, _ = S.generer_ordres(c, etat, valo, [], "Vigilance", self.config, maintenant)
        self.assertEqual(len(ordres), 1)
        self.assertEqual(ordres[0]["sens"], "achat")

    def test_volatilite_et_plafond(self):
        pts = [(str(i), 100 * (1.01 if i % 2 else 0.99) ** 1) for i in range(80)]
        self.assertGreater(S.volatilite(pts, 63), 10)
        self.assertIsNone(S.volatilite(pts[:5], 63))
        p = S._plafonner({"a": 20, "b": 5, "c": 5}, 8)
        self.assertLessEqual(max(p.values()), 8 + 1e-9)
        self.assertLessEqual(sum(p.values()), 30 + 1e-9)

    def test_statistiques(self):
        h = {f"2026-0{1 + i // 28}-{1 + i % 28:02d}": {"portefeuille": 100000 * (1 + 0.001 * i), "msci_world": 100000} for i in range(40)}
        pts = F.serie(h, "portefeuille")
        r = F.risque(pts, self.config)
        self.assertIsNotNone(r["sharpe"])
        self.assertEqual(r["perte_max"], 0)
        self.assertIsNotNone(F.perf_periode(pts, 30))
        self.assertIsNone(F.perf_periode(pts, 91))
        ops = [{"sens": "vente", "resultat": {"plus_value_eur": 100, "plus_value_pct": 10}}, {"sens": "vente", "resultat": {"plus_value_eur": -50, "plus_value_pct": -5}},
               {"sens": "achat"}]
        s = F.stats_operations(ops)
        self.assertEqual(s["taux_reussite"], 50)
        self.assertEqual(s["gain_moyen_pct"], 10)
        self.assertEqual(s["perte_moyenne_pct"], -5)


class TestSimulation(BaseTrader):
    def test_simulation_trois_mois(self):
        """Trois mois de séances simulées : performance, risque, attribution cohérents ; aucune règle violée."""
        self.f.chocs = {"CCC.T": [("2026-09-15", 0.8)], "AAA": [("2026-09-20", 1.35)]}
        evenements = {"2026-10-05": {"palier": "Tension"}, "2026-10-20": {"palier": "Vigilance"},
                      "2026-10-12": {"modifs": {("entreprises", "entreprise-BBB"): {"verdict": "Alléger"}}}}
        res = simuler(executer, self.f, self.config, self.data, "2026-09-01", 92, heures=(15, 21), evenements=evenements)
        self.assertTrue(all(r["ok"] for r in res))
        pf = lire(self.data / "portefeuille.json")["donnees"]
        st = pf["statistiques"]
        self.assertGreaterEqual(len(pf["historique"]), 60)
        self.assertIsNotNone(st["performance"]["un_mois"])
        self.assertIsNotNone(st["risque"]["sharpe"])
        self.assertIsNotNone(st["risque"]["volatilite"])
        self.assertLessEqual(st["risque"]["perte_max"], 0)
        self.assertIsNotNone(st["performance_msci_world"]["depuis_debut"])
        self.assertGreater(st["operations"]["cloturees"], 0)
        # attribution : la somme des poches égale exactement le gain total (réalisé + latent, frais compris)
        total = sum(x["eur"] for x in st["attribution"]["poches"])
        self.assertAlmostEqual(total, pf["valeur_actuelle"] - 100000, delta=1)
        self.assertAlmostEqual(sum(x["eur"] for x in st["attribution"]["familles"]), total, delta=1)
        ops = lire(self.data / "trader" / "operations.json")["donnees"]
        motifs = {o["motif"] for o in ops}
        self.assertIn("stop", motifs)
        self.assertIn("prise de bénéfices", motifs)
        self.assertIn("sortie sur verdict", motifs)
        self.assertIn("plancher de liquidités", motifs)
        for o in ops:
            self.assertGreaterEqual(o["date"], o["decide_le"], "jamais un cours antérieur à la décision")
        for p in pf["positions"]:
            if p["poche"] == "satellite":
                self.assertLessEqual(p["poids"], self.config["satellites"]["max_ligne"] + 2.5, "8 % par ligne (hors dérive de cours)")
        self.assertGreaterEqual(pf["liquidites"], 0)
        noms = {o["symbole"] for o in ops}
        self.assertFalse({"EEE", "FFF", "GGG"} & noms)
        self.assertEqual({e[0] for e in ENTREPRISES} & {"EEE"}, {"EEE"})


if __name__ == "__main__":
    unittest.main()
