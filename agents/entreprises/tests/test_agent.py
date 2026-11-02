"""Tests de l'agent entreprises, sans réseau : python -m unittest discover -s agents -t ."""
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from agents.commun.sortie import lire_json
from agents.entreprises import analyse as A
from agents.entreprises import comptes as C
from agents.entreprises import univers as U

DOSSIER = Path(__file__).resolve().parents[1]
CFG = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))


def exercice(fin, **v):
    return {"fin": fin, **v}


A0 = exercice("2025-12-31", ca=1100.0, ebit=220.0, ebitda=300.0, resultat_net=150.0, cfo=200.0, capex=40.0, fcf=160.0,
              dette_totale=300.0, tresorerie=200.0, capitaux_propres=900.0, actifs=2000.0, actifs_courants=600.0,
              passifs_courants=300.0, dette_lt=250.0, actions=100.0, creances=150.0, stocks=100.0, marge_brute=500.0,
              capital_investi=1100.0, interets=10.0, taux_impot=0.25)
A1 = exercice("2024-12-31", ca=1000.0, ebit=190.0, ebitda=260.0, resultat_net=120.0, cfo=170.0, capex=40.0, fcf=130.0,
              dette_totale=320.0, tresorerie=150.0, capitaux_propres=800.0, actifs=1900.0, actifs_courants=520.0,
              passifs_courants=300.0, dette_lt=270.0, actions=100.0, creances=140.0, stocks=95.0, marge_brute=440.0,
              capital_investi=1050.0, interets=11.0, taux_impot=0.25)


class TestMesures(unittest.TestCase):
    def test_mesures_de_base(self):
        m = A.mesures({"annuel": [A0, A1], "cours": [], "capitalisation_usd": 3000.0, "fx_comptes": 1.0})
        self.assertAlmostEqual(m["croissance_ca"], 10.0)
        self.assertAlmostEqual(m["croissance_benefice"], 25.0)
        self.assertAlmostEqual(m["marge_op"], 20.0)
        self.assertAlmostEqual(m["marge_op_variation"], 1.0)
        self.assertAlmostEqual(m["dette_ebitda"], 1 / 3)
        self.assertAlmostEqual(m["couverture_interets"], 22.0)
        self.assertAlmostEqual(m["roic"], 15.0)
        self.assertAlmostEqual(m["per"], 20.0)
        self.assertAlmostEqual(m["ev_ebitda"], 3100 / 300)
        self.assertEqual(m["alertes"], [])

    def test_fscore(self):
        f = A.fscore(A0, A1)
        self.assertEqual(f["calcules"], 9)
        self.assertEqual(f["score"], 9)  # tous les critères sont remplis dans cet exemple

    def test_alertes(self):
        a0 = {**A0, "cfo": 50.0, "actions": 110.0, "creances": 220.0}
        cles = [x["cle"] for x in A.alertes(a0, A1)]
        self.assertEqual(cles, ["ecart_benefice_cash", "dilution", "creances"])


class TestNotation(unittest.TestCase):
    def test_bareme(self):
        self.assertEqual(A.lin(10, A.BAREMES["croissance_ca"]), 75)
        self.assertEqual(A.lin(-50, A.BAREMES["croissance_ca"]), 10)
        self.assertEqual(A.lin(100, A.BAREMES["croissance_ca"]), 95)

    def test_financieres_criteres_adaptes(self):
        m = {"roe": 14.0, "cout_revenu": 50.0, "croissance_bilan": 6.0, "dette_ebitda": 5.0, "roic": 3.0, "croissance_ca": 5.0}
        n = A.notes(m, "banque")
        self.assertIn("roe", n)
        self.assertIn("cout_revenu", n)
        self.assertNotIn("dette_ebitda", n)
        self.assertNotIn("roic", n)
        self.assertNotIn("roe", A.notes(m, None))

    def test_deux_signaux_concordants(self):
        p = {"a": 0.5, "b": 0.5}
        self.assertTrue(A.note_globale({"a": 95, "b": 50}, p)["ramenee"])   # un seul signal fort
        self.assertEqual(A.note_globale({"a": 95, "b": 50}, p)["note"], 64)
        self.assertFalse(A.note_globale({"a": 80, "b": 70}, p)["ramenee"])
        self.assertEqual(A.note_globale({"a": 20, "b": 70}, p)["note"], 50)  # un seul signal faible

    def test_confiance_plafonnee_sans_source_officielle(self):
        g = {"couverture": 1.0, "ramenee": False}
        self.assertEqual(A.confiance({"annuel": [A0]}, g, date(2026, 11, 2))["niveau"], "moyen")
        s = {"annuel": [A0], "officiel": {"fin": "2025-12-31"}, "verification": {"statut": "concordant"}}
        self.assertEqual(A.confiance(s, g, date(2026, 11, 2))["niveau"], "élevé")

    def test_pepite_et_contexte(self):
        m = A.mesures({"annuel": [A0, A1], "cours": [], "capitalisation_usd": 3000.0, "fx_comptes": 1.0})
        m.update({"per_secteur": -5.0})
        n = A.notes(m, None)
        self.assertTrue(A.criteres_pepite(m, n, None, CFG["pepites"])["ok"])
        m["alertes"] = [{"cle": "dilution"}]
        self.assertFalse(A.criteres_pepite(m, n, None, CFG["pepites"])["ok"])
        ctx = A.ajustement_contexte(90, "Reprise", CFG["contexte"])
        self.assertEqual(ctx["points"], CFG["contexte"]["plafond"])  # plafonné
        self.assertLess(A.ajustement_contexte(30, "Ralentissement inflationniste", CFG["contexte"])["points"], 0)

    def test_ton(self):
        ind = A.indicateurs_affiches(A.mesures({"annuel": [A0, A1], "cours": []}), {"croissance_ca": 75, "marge_op": 70})
        self.assertTrue(A.ton_conforme(A.verdict(ind, 70)))


class TestUnivers(unittest.TestCase):
    def test_ishares(self):
        csv = ("iShares MSCI Japan ETF\nFund Holdings as of,\"Oct 31, 2026\"\n\n"
               "Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date\n"
               "\"7203\",\"TOYOTA MOTOR CORP\",\"Consumer Discretionary\",\"Equity\",\"1\",\"4.50\",\"1\",\"1\",\"1\",\"Japan\",\"Tokyo Stock Exchange\",\"JPY\",\"1\",\"JPY\",\"-\"\n"
               "\"8306\",\"MITSUBISHI UFJ FINANCIAL GROUP INC\",\"Financials\",\"Equity\",\"1\",\"5.10\",\"1\",\"1\",\"1\",\"Japan\",\"Tokyo Stock Exchange\",\"JPY\",\"1\",\"JPY\",\"-\"\n"
               "\"JPY\",\"JPY CASH\",\"Cash and/or Derivatives\",\"Cash\",\"1\",\"0.10\",\"1\",\"1\",\"1\",\"Japan\",\"-\",\"JPY\",\"1\",\"JPY\",\"-\"\n")
        r = U.lire_ishares(csv, "JP")
        self.assertEqual([x["ticker"] for x in r], ["8306.T", "7203.T"])
        self.assertEqual(r[1]["secteur"], "Consumer Discretionary")
        with self.assertRaises(ValueError):
            U.lire_ishares("<html>page</html>", "JP")

    def test_symboles(self):
        self.assertEqual(U.symbole_yahoo("700", "Hong Kong Exchanges And Clearing Ltd", "CN"), "0700.HK")
        self.assertEqual(U.symbole_yahoo("BRK.B", "New York Stock Exchange Inc.", "US"), "BRK-B")
        self.assertEqual(U.symbole_yahoo("005930", "Korea Exchange (Stock Market)", "KR"), "005930.KS")
        self.assertIsNone(U.symbole_yahoo("ABC", "Bourse inconnue", "XX"))
        self.assertEqual(U.secteur_gics("Consumer Cyclical"), "Consumer Discretionary")

    def test_doublons(self):
        depart = [{"ticker": "GOOGL", "nom": "Alphabet Inc. Class A", "pays": "US", "secteur": None, "poids": 2},
                  {"ticker": "GOOG", "nom": "Alphabet Inc. Class C", "pays": "US", "secteur": None, "poids": 1},
                  {"ticker": "BHP.AX", "nom": "BHP Group Limited", "pays": "AU", "secteur": None, "poids": 1},
                  {"ticker": "BHG.JO", "nom": "BHP Group Ltd", "pays": "ZA", "secteur": None, "poids": 1}]
        liste, _ = U.construire(None, CFG, None, depart, [], ["US", "AU", "ZA"])
        self.assertEqual([s["ticker"] for s in liste], ["GOOGL", "BHP.AX"])

    def test_secours_et_surveillance(self):
        connu = {"societes": [{"ticker": "AAA", "nom": "A", "pays": "FR", "secteur": "Energy", "poids": 1}]}
        liste, etats = U.construire(None, CFG, connu, [{"ticker": "BBB", "nom": "B", "pays": "DE", "secteur": None, "poids": 0}],
                                    [{"ticker": "ZZZ", "pays": "FR"}], ["FR", "DE"])
        self.assertEqual(etats["FR"]["etat"], "ancienne")
        self.assertEqual(etats["DE"]["etat"], "depart")
        self.assertEqual([s["ticker"] for s in liste], ["AAA", "BBB", "ZZZ"])
        self.assertTrue(liste[-1]["surveillance"])


class TestComptes(unittest.TestCase):
    def test_verification(self):
        off = {"fin": "2025-12-31", "ca": 1000.0, "resultat_net": 100.0}
        self.assertEqual(C.verifier(off, [exercice("2025-12-31", ca=1010.0, resultat_net=101.0)], 5)["statut"], "concordant")
        self.assertEqual(C.verifier(off, [exercice("2025-12-31", ca=1200.0, resultat_net=101.0)], 5)["statut"], "divergent")
        self.assertEqual(C.verifier(off, [exercice("2023-12-31", ca=1000.0)], 5)["statut"], "non comparable")

    def test_devise_centimes(self):
        self.assertEqual(C.devise_majeure("GBp"), ("GBP", 100))
        self.assertEqual(C.devise_majeure("EUR"), ("EUR", 1.0))


@unittest.skipUnless((DOSSIER / "tests" / "donnees" / "societes.json").exists(), "données de test absentes")
class TestAgent(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        racine = DOSSIER.parents[1]
        for f in ("pays.json", "macro.json"):
            shutil.copy(racine / "data" / f, self.dossier / f)

    def tearDown(self):
        shutil.rmtree(self.dossier)

    def test_execution_complete_puis_quotidienne(self):
        from agents.entreprises.agent import main
        self.assertEqual(main(["--mode", "complet", "--test", "--data", str(self.dossier), "--date", "2026-11-02"]), 0)
        e = lire_json(self.dossier / "entreprises.json")
        self.assertFalse(e["meta"]["fictif"])
        self.assertGreater(len(e["donnees"]), 5)
        for x in e["donnees"]:
            self.assertIn(x["niveau"], ("attractif", "neutre", "defavorable"))
            self.assertTrue(A.ton_conforme(x["verdict"]))
            self.assertTrue(x["contre_scenario"])
            if not x["sources"]["officielle"]:
                self.assertNotEqual(x["confiance"]["niveau"], "élevé")
        secteurs = lire_json(self.dossier / "secteurs.json")["donnees"]
        tickers = {x["ticker"] for x in e["donnees"]}
        for s in secteurs:
            self.assertTrue(set(s["entreprises"]) <= tickers)
        self.assertIsNotNone(lire_json(self.dossier / "pepites.json"))
        self.assertTrue((self.dossier / "recap" / "entreprises-2026-11-02.md").exists())
        sante = lire_json(self.dossier / "journal" / "agent-entreprises.json")["meta"]["sante"]
        self.assertEqual(sante["agent"], "entreprises")
        # Mise à jour quotidienne à partir de la base enregistrée
        self.assertEqual(main(["--mode", "quotidien", "--test", "--data", str(self.dossier), "--date", "2026-11-03"]), 0)


if __name__ == "__main__":
    unittest.main()
