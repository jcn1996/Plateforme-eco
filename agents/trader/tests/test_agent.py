"""Tests de l'agent trader (démo) : données de test construites de toutes pièces (tests/fabrique.py), cours simulés,
dossier temporaire. Les vrais config/ et data/ ne sont jamais lus ni modifiés ; aucun accès au réseau."""
from __future__ import annotations

import copy
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
from agents.trader.tests.fabrique import preparer, simuler

SAMEDI = datetime(2026, 11, 7, 22, 30, tzinfo=timezone.utc)
LUNDI_MATIN = datetime(2026, 11, 9, 7, 33, tzinfo=timezone.utc)
OBJECTION = {"objection": "Objection nouvelle.", "serieuse": True}


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
    def test_premiere_decision(self):
        r = self.lancer(LUNDI_MATIN, "decision")
        d = r["decision"]
        self.assertIsNotNone(d)
        c = d["cibles"]
        lignes = c["lignes"]
        self.assertAlmostEqual(sum(c["poches"].values()), 100, delta=0.05)
        self.assertGreaterEqual(c["poches"]["liquidites"], self.config["liquidites_min_par_palier"]["Vigilance"] - 1e-6)
        # concentration : 15 lignes au plus, 4 % minimum
        self.assertLessEqual(len(lignes), 15)
        for l in lignes:
            self.assertGreaterEqual(l["cible"], 4 - 1e-6, l["nom"])
        coeur = [l for l in lignes if l["poche"] == "coeur"]
        sats = [l for l in lignes if l["poche"] == "satellite"]
        self.assertTrue(8 <= len(coeur) <= 12, len(coeur))
        # diversification : au moins 4 classes ou zones
        self.assertGreaterEqual(d["diversification"]["nombre_zones"], 4)
        self.assertGreaterEqual(len({l["zone"] for l in lignes}), 4)
        # cœur : « Renforcer » de conviction moyenne ou forte (obligations exceptées), jamais d'ETF monde ni d'ETF pays « Neutre »
        for l in coeur:
            if l["classe"] != "obligations":
                self.assertIn(l["verdict"], ("Renforcer", "Renforcer fortement"))
                self.assertIn(l["conviction"], ("moyenne", "forte"))
        symboles = {l["symbole"] for l in lignes}
        self.assertFalse({"IXN", "URTH", "EWG", "EWU"} & symboles, "ni ETF monde, ni ETF pays « Neutre »")
        # jamais d'achat « À surveiller » ou sous objection
        self.assertFalse({"XLE", "KKK", "EWT", "BNO", "EEE"} & symboles)
        ecartees = {x["nom"]: x["raison"] for x in d["satellites_ecartes"]}
        self.assertIn("objection", ecartees["Énergie — États-Unis"])
        self.assertIn("À surveiller", ecartees["Kappa Surveillée"])
        self.assertIn("monde", ecartees["Technologie — Monde"])
        self.assertIn("une seule source", ecartees["Phi Source Unique"])
        # satellites : convictions fortes seulement
        self.assertTrue(sats)
        for l in sats:
            self.assertEqual(l["conviction"], "forte")
            self.assertLessEqual(l["cible"], self.config["satellites"]["max_ligne"] + 1e-6)
        self.assertNotIn("CCC.T", symboles, "conviction moyenne : pas de satellite")
        # obligations : poids neutre pour un verdict « Neutre »
        for l in lignes:
            if l["classe"] == "obligations":
                self.assertEqual(l["cible"], 5)
        self.assertNotIn("TLT", symboles)
        # ordres en attente de l'ouverture, chacun justifié
        self.assertFalse(r["executees"])
        self.assertEqual(len(r["etat"]["ordres"]), len(lignes))
        for o in r["etat"]["ordres"]:
            self.assertTrue(o["raison"]["texte"])
            self.assertTrue(o["donner_tort"])
        self.assertTrue(d["donner_tort"])
        self.assertTrue(d["arbitrages"])
        pf = lire(self.data / "portefeuille.json")
        self.assertFalse(pf["meta"]["fictif"])
        self.assertEqual(pf["donnees"]["mention"], "Portefeuille fictif à but de démonstration, aucun ordre réel.")

    def test_correlation_sur_un_an(self):
        self.f = FournisseurSimule(debut="2025-09-01", jumeaux={"EWD": "XLV"})
        d = self.lancer(LUNDI_MATIN, "decision")["decision"]
        symboles = {l["symbole"] for l in d["cibles"]["lignes"]}
        self.assertIn("XLV", symboles)
        self.assertNotIn("EWD", symboles)
        raison = next(x["raison"] for x in d["satellites_ecartes"] if x["nom"] == "Suède")
        self.assertIn("corrélation", raison)
        self.assertLessEqual(d["diversification"]["correlation_max"]["valeur"], self.config["coeur"]["correlation_max"])
        self.assertEqual(d["diversification"]["paires_mesurees"], d["diversification"]["paires_possibles"])

    def test_une_seule_decision_par_jour(self):
        self.lancer(LUNDI_MATIN, "decision")
        r = self.lancer(LUNDI_MATIN.replace(hour=15, minute=5))
        achats = {o["symbole"] for o in r["executees"]}
        self.assertTrue(achats)
        n = len(r["etat"]["ordres"])
        r = self.lancer(LUNDI_MATIN.replace(hour=17, minute=46), "decision", modifs={("pays", "pays-KR"): {"verdict": "Neutre"}})
        self.assertIsNone(r["decision"], "la décision du jour n'est pas recalculée")
        self.assertEqual(len(r["etat"]["ordres"]), n)
        self.assertFalse([o for o in r["etat"]["ordres"] if o["sens"] == "vente" and o["symbole"] in achats],
                         "pas d'achat puis de vente du même titre le même jour")
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
        sat = [x for x in r["executees"] if x["poche"] == "satellite"]
        self.assertTrue(all(x["stop"] for x in sat), "stop associé à chaque satellite")
        v = r["valo"]
        self.assertAlmostEqual(v["valeur"], v["liquidites"] + sum(p["valeur_eur"] for p in r["etat"]["positions"].values()), delta=0.01)
        self.assertLessEqual(len(r["etat"]["positions"]), 15)

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


class TestAttente(BaseTrader):
    def test_chef_perime(self):
        r = self.lancer(LUNDI_MATIN, "decision", age_chef_h=40)
        self.assertIsNone(r["decision"])
        self.assertTrue(any("chef d'orchestre" in x for x in r["attente"]["raisons"]))
        self.assertFalse(r["etat"]["ordres"])
        self.assertTrue(r["sante"]["degrade"])
        self.assertEqual(lire(self.data / "portefeuille.json")["donnees"]["statut"]["etat"], "en attente")

    def test_chef_degrade(self):
        r = self.lancer(LUNDI_MATIN, "decision", chef_degrade=True)
        self.assertIsNone(r["decision"])
        self.assertTrue(any("dégradé" in x for x in r["attente"]["raisons"]))

    def test_analyse_du_jour_absente_puis_rattrapage_horaire(self):
        r = self.lancer(LUNDI_MATIN, "decision", analyse_du_jour=False)
        self.assertIsNone(r["decision"])
        r = self.lancer(LUNDI_MATIN.replace(hour=9, minute=5))
        self.assertIsNotNone(r["decision"], "la première exécution horaire où les données sont prêtes décide")
        r = self.lancer(LUNDI_MATIN.replace(hour=10, minute=5))
        self.assertIsNone(r["decision"], "une seule décision par jour")


class TestRisque(BaseTrader):
    def test_stop_ecourte_la_detention_minimale(self):
        self.f.chocs = {"III": [("2026-11-10", 0.78)]}
        self.investir()
        mardi = LUNDI_MATIN + timedelta(days=1)
        r = self.lancer(mardi.replace(hour=15, minute=5))
        self.assertEqual(r["etat"]["positions"]["III"]["confirmations_stop"], 1)
        r = self.lancer(mardi.replace(hour=18, minute=5))
        stop = [o for o in r["imposes"] if o["symbole"] == "III"]
        self.assertEqual([o["motif"] for o in stop], ["stop"], "le stop s'applique même avant 5 jours de détention")
        r = self.lancer(mardi.replace(hour=21, minute=5))
        op = next(o for o in r["executees"] if o["symbole"] == "III")
        self.assertLess(op["resultat"]["plus_value_eur"], 0)
        r = self.lancer(mardi + timedelta(days=1), "decision")
        self.assertNotIn("III", {l["symbole"] for l in r["decision"]["cibles"]["lignes"]}, "pas de rachat après un stop")

    def test_sortie_sur_verdict_apres_detention_minimale(self):
        self.investir()
        modifs = {("secteurs", "secteur-etats_unis-sante"): {"verdict": "Éviter"}, ("entreprises", "entreprise-BBB"): {"objection": OBJECTION}}
        mardi = LUNDI_MATIN + timedelta(days=1, hours=1)
        r = self.lancer(mardi, modifs=modifs)
        self.assertFalse([o for o in r["imposes"] if o["symbole"] in ("XLV", "BBB")], "détention minimale de 5 jours")
        lundi_suivant = LUNDI_MATIN + timedelta(days=7, hours=1)
        r = self.lancer(lundi_suivant, modifs=modifs)
        motifs = {o["symbole"]: o["motif"] for o in r["imposes"]}
        self.assertEqual(motifs.get("XLV"), "sortie sur verdict")
        self.assertEqual(motifs.get("BBB"), "sortie sur objection")

    def test_prise_de_benefices_apres_detention_minimale(self):
        self.f.chocs = {"BBB": [("2026-11-10", 1.4)]}
        self.investir()
        r = self.lancer((LUNDI_MATIN + timedelta(days=1)).replace(hour=15, minute=5))
        self.assertEqual(r["etat"]["positions"]["BBB"]["stop_type"], "suiveur")
        self.assertFalse([o for o in r["imposes"] if o["symbole"] == "BBB"])
        r = self.lancer((LUNDI_MATIN + timedelta(days=7)).replace(hour=15, minute=5))
        pb = [o for o in r["imposes"] if o["symbole"] == "BBB"]
        self.assertEqual(pb[0]["motif"], "prise de bénéfices")

    def test_plancher_de_liquidites_en_crise(self):
        self.investir()
        t = LUNDI_MATIN + timedelta(days=7, minutes=-1)
        r = self.lancer(t, palier="Crise")
        self.assertTrue([o for o in r["imposes"] if o["motif"] == "plancher de liquidités"])
        r = self.lancer(t.replace(hour=15, minute=5), palier="Crise")
        self.assertGreaterEqual(r["donnees"]["liquidites_pct"], 35 - self.config["tolerance_plancher_points"] - 0.5)


class TestTransition(BaseTrader):
    """Lignes détenues qui ne respectent plus les règles : réduction progressive et expliquée."""

    def test_reduction_progressive(self):
        self.config = copy.deepcopy(self.config)
        self.config["transition"]["sorties_max_par_jour"] = 2
        self.investir()
        tenues = set(lire(self.data / "trader" / "etat.json")["positions"])
        # le chef d'orchestre change d'avis sur plusieurs lignes (sans « Alléger » : pas de sortie imposée)
        modifs = {("pays", "pays-JP"): {"verdict": "Neutre"}, ("pays", "pays-IN"): {"objection": OBJECTION},
                  ("or", "or"): {"conviction": "faible"}, ("panorama", None): {"a_surveiller": [{"id": "pays-SE"}]}}
        mardi = LUNDI_MATIN + timedelta(days=1)
        d = self.lancer(mardi, "decision", modifs=modifs)["decision"]
        arb = {a["symbole"]: a for a in d["arbitrages"]}
        for s in ("EWJ", "INDA", "GLD", "EWD"):
            self.assertIn(s, tenues)
            self.assertEqual(arb[s]["action"], "conservée pour l'instant", "détention minimale de 5 jours")
            self.assertIn("2026-11-14", arb[s]["raison"])
        self.assertIn("pas d'ETF pays « Neutre »", arb["EWJ"]["raison"])
        self.assertIn("objection", arb["INDA"]["raison"])
        self.assertIn("À surveiller", arb["EWD"]["raison"])
        self.assertFalse([o for o in self.lancer(mardi.replace(hour=15, minute=5), modifs=modifs)["executees"] if o["sens"] == "vente"])
        # après la détention minimale : au plus 2 sorties par décision, chacune expliquée, règles enfreintes d'abord
        jour = LUNDI_MATIN + timedelta(days=7)
        vendues = []
        for _ in range(4):
            d = self.lancer(jour, "decision", modifs=modifs)["decision"]
            ventes = [a for a in d["arbitrages"] if a["action"] == "vente totale"]
            self.assertLessEqual(len(ventes), 2)
            if len(vendues) < 4:
                self.assertTrue(set(a["symbole"] for a in ventes) <= {"EWJ", "INDA", "GLD", "EWD"}, "règles enfreintes soldées en premier")
            vendues += [a["symbole"] for a in ventes]
            for o in lire(self.data / "trader" / "etat.json")["ordres"]:
                if o["motif"] == "mise en conformité":
                    self.assertIn("Mise en conformité", o["raison"]["texte"])
            self.lancer(jour.replace(hour=15, minute=5), modifs=modifs)
            jour += timedelta(days=1)
        self.assertEqual(vendues[:4] and set(vendues[:4]), {"EWJ", "INDA", "GLD", "EWD"})
        positions = lire(self.data / "trader" / "etat.json")["positions"]
        self.assertFalse({"EWJ", "INDA", "GLD", "EWD"} & set(positions))
        self.assertLessEqual(len(positions), 15)

    def test_quinze_lignes_au_plus_pendant_la_transition(self):
        """Un portefeuille trop dispersé n'ouvre aucune nouvelle ligne tant qu'il dépasse 15 lignes."""
        maintenant = LUNDI_MATIN
        etat = P.etat_initial(self.config, maintenant)
        for i in range(20):
            s = f"X{i:02d}"
            etat["positions"][s] = {"symbole": s, "nom": s, "quantite": 10, "prix_revient_eur": 400, "dernier_cours_eur": 400, "poids": 4,
                                    "poche": "coeur", "classe": "actions", "devise": "USD", "cout_total_eur": 4000, "ouverte_le": "2026-11-08T14:30:00Z"}
        e = {"cible": 6, "poche": "coeur", "classe": "actions", "zone": "Europe", "support": {"symbole": "NEW", "nom": "Nouvelle", "devise": "USD"},
             "ligne": {"id": "pays-NEW", "nom": "Nouvelle", "type": "pays"}}
        c = {"lignes": {"NEW": e}, "exclusions": {f"X{i:02d}": (True, "règle enfreinte") for i in range(20)}, "liquidites": 10, "liquidites_min": 10}
        ordres, _, arb = S.generer_ordres(c, etat, {"valeur": 100000, "liquidites": 20000}, [], "Vigilance", self.config, maintenant)
        self.assertFalse(ordres, "détention minimale : aucune vente ; 20 lignes : aucune entrée")
        self.assertEqual(next(a for a in arb if a["symbole"] == "NEW")["action"], "entrée reportée")


class TestRegles(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()

    def test_seuil_de_reequilibrage(self):
        maintenant = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)
        etat = P.etat_initial(self.config, maintenant)
        etat["positions"] = {"SPY": {"symbole": "SPY", "nom": "SPY", "quantite": 10, "prix_revient_eur": 500, "dernier_cours_eur": 500, "poids": 10,
                                     "poche": "coeur", "classe": "actions", "devise": "USD", "cout_total_eur": 5000, "ouverte_le": "2026-11-09T14:30:00Z"}}
        e = {"cible": 12, "poche": "coeur", "classe": "actions", "zone": "Amérique du Nord", "support": {"symbole": "SPY", "nom": "SPY", "devise": "USD"},
             "ligne": {"id": "pays-US"}}
        c = {"lignes": {"SPY": e}, "exclusions": {}, "liquidites": 88, "liquidites_min": 10}
        valo = {"valeur": 100000, "liquidites": 90000}
        ordres, _, _ = S.generer_ordres(c, etat, valo, [], "Vigilance", self.config, maintenant)
        self.assertFalse(ordres, "écart de 2 points : sous le seuil de 3 points")
        e["cible"] = 14
        ordres, _, _ = S.generer_ordres(c, etat, valo, [], "Vigilance", self.config, maintenant)
        self.assertEqual([o["sens"] for o in ordres], ["achat"])
        e["cible"] = 6
        ordres, _, _ = S.generer_ordres(c, etat, valo, [], "Vigilance", self.config, maintenant)
        self.assertEqual([o["motif"] for o in ordres], ["rééquilibrage"])
        ordres, _, arb = S.generer_ordres(c, etat, valo, [], "Vigilance", self.config, datetime(2026, 11, 12, 8, tzinfo=timezone.utc))
        self.assertFalse(ordres, "réduction impossible avant 5 jours de détention")
        self.assertEqual(arb[0]["action"], "réduction reportée")

    def test_correlation(self):
        a = [(f"d{i:03d}", 100 * (1.01 if i % 3 else 0.98) ** (i % 7)) for i in range(200)]
        ra = S.rendements(a)
        self.assertAlmostEqual(S.correlation(ra, ra), 1.0, places=6)
        self.assertAlmostEqual(S.correlation(ra, {k: -v for k, v in ra.items()}), -1.0, places=6)
        self.assertIsNone(S.correlation(ra, dict(list(ra.items())[:50])), "moins de 120 dates communes")

    def test_volatilite(self):
        pts = [(str(i), 100 * (1.01 if i % 2 else 0.99)) for i in range(80)]
        self.assertGreater(S.volatilite(pts, 63), 10)
        self.assertIsNone(S.volatilite(pts[:5], 63))

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
        """Trois mois simulés : règles respectées à chaque séance ; performance, risque et attribution cohérents."""
        self.f = FournisseurSimule(debut="2025-06-01", chocs={"III": [("2026-09-15", 0.8)], "BBB": [("2026-09-20", 1.35)]})
        ev = {"2026-10-05": {"palier": "Tension"}, "2026-10-20": {"palier": "Vigilance"},
              "2026-10-12": {"modifs": {("pays", "pays-JP"): {"verdict": "Neutre"}, ("secteurs", "secteur-etats_unis-sante"): {"verdict": "Alléger"}}}}
        res = simuler(executer, self.f, self.config, self.data, "2026-09-01", 92, heures=(15, 21), evenements=ev)
        self.assertTrue(all(r["ok"] for r in res))
        for r in res:
            self.assertLessEqual(len(r["etat"]["positions"]), 15)
            if r["decision"]:
                self.assertLessEqual(len(r["decision"]["cibles"]["lignes"]), 15)
        decisions = defaultdict(int)
        for r in res:
            if r["decision"]:
                decisions[r["decision"]["date"]] += 1
        self.assertEqual(set(decisions.values()), {1}, "une seule décision par jour")
        ops = lire(self.data / "trader" / "operations.json")["donnees"]
        achats = {}
        par_jour = defaultdict(set)
        for o in ops:
            self.assertGreaterEqual(o["date"], o["decide_le"])
            par_jour[(o["date"][:10], o["symbole"])].add(o["sens"])
            if o["sens"] == "achat":
                achats[o["symbole"]] = o["date"]
            elif o["motif"] != "stop":
                dernier = achats.get(o["symbole"])
                if dernier:
                    jours = (datetime.fromisoformat(o["date"][:10]) - datetime.fromisoformat(dernier[:10])).days
                    self.assertGreaterEqual(jours, 5, f"{o['symbole']} vendu {jours} j après un achat ({o['motif']})")
        self.assertFalse([k for k, v in par_jour.items() if v == {"achat", "vente"}], "pas d'achat et de vente du même titre le même jour")
        pf = lire(self.data / "portefeuille.json")["donnees"]
        st = pf["statistiques"]
        self.assertIsNotNone(st["risque"]["sharpe"])
        self.assertIsNotNone(st["performance_msci_world"]["depuis_debut"])
        total = sum(x["eur"] for x in st["attribution"]["poches"])
        self.assertAlmostEqual(total, pf["valeur_actuelle"] - 100000, delta=1)
        motifs = {o["motif"] for o in ops}
        self.assertIn("stop", motifs)
        for r in res:  # pendant la « Tension » : 20 % de liquidités au moins (tolérance d'un point, dérive des cours)
            if "2026-10-07" <= r["donnees"]["maj"][:10] <= "2026-10-19":
                self.assertGreaterEqual(r["donnees"]["liquidites_pct"], 20 - self.config["tolerance_plancher_points"] - 0.5)
        self.assertTrue({"sortie sur verdict", "mise en conformité"} & motifs)
        self.assertFalse({"EEE", "FFF", "GGG", "KKK", "XLE", "IXN", "EWG"} & {o["symbole"] for o in ops})


if __name__ == "__main__":
    unittest.main()
