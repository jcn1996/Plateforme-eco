"""Tests de l'agent entreprises, sans réseau : python -m unittest discover -s agents -t ."""
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from agents.commun.essais import copier_donnees_test
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


class TestListes(unittest.TestCase):
    def test_regroupement_des_cotations(self):
        soc = [{"ticker": "NEM", "nom": "Newmont Corporation", "pays": "US", "liquidite_musd": 900},
               {"ticker": "NEM.AX", "nom": "Newmont Corporation", "pays": "AU", "liquidite_musd": 40},
               {"ticker": "INVE-A.ST", "nom": "Investor AB ser. A", "pays": "SE", "liquidite_musd": 5},
               {"ticker": "INVE-B.ST", "nom": "Investor AB ser. B", "pays": "SE", "liquidite_musd": 60}]
        soc += [{"ticker": "EQT", "nom": "EQT Corporation", "pays": "US", "liquidite_musd": 300, "secteur_gics": "Energy", "capitalisation_usd": 34e9},
                {"ticker": "EQT.ST", "nom": "EQT AB", "pays": "SE", "liquidite_musd": 50, "secteur_gics": "Financials", "capitalisation_usd": 30e9}]
        r = {x["ticker"]: x for x in A.regrouper_cotations(soc, U.cle_societe)}
        self.assertEqual(set(r), {"NEM", "INVE-B.ST", "EQT", "EQT.ST"})  # même nom, secteurs différents : deux sociétés
        self.assertEqual(r["NEM"]["autres_cotations"], [{"ticker": "NEM.AX", "pays": "AU"}])

    def test_holdings(self):
        self.assertTrue(A.est_holding("Investor AB", "Asset Management", "INVE-B.ST", CFG["pepites"]))
        self.assertFalse(A.est_holding("BlackRock, Inc.", "Asset Management", "BLK", CFG["pepites"]))
        self.assertTrue(A.est_holding("Some Fund", "Closed-End Fund - Equity", "X", CFG["pepites"]))
        self.assertTrue(A.est_holding("Investor AB", None, "INVE-B.ST", CFG["pepites"], "Financials"))  # industrie inconnue

    def test_deux_listes_et_plafond_par_secteur(self):
        cfg = {**CFG["pepites"], "plafond_par_secteur": 2}
        c = ([{"ticker": f"OR{i}", "cap": 5, "analystes": 3, "secteur": "Materials", "note_ajustee": 90 - i} for i in range(4)]
             + [{"ticker": "SUIVIE", "cap": 5, "analystes": 25, "secteur": "Industrials", "note_ajustee": 95},
                {"ticker": "GRANDE", "cap": 300, "analystes": 40, "secteur": "Health Care", "note_ajustee": 80},
                {"ticker": "INCONNUE", "cap": 2, "analystes": None, "secteur": "Energy", "note_ajustee": 70}])
        l = A.selection_listes(c, cfg)
        self.assertEqual([x["ticker"] for x in l["pepites"]], ["OR0", "OR1", "INCONNUE"])  # 2 par secteur ; trop suivie écartée
        self.assertEqual([x["ticker"] for x in l["qpr"]], ["GRANDE"])

    def test_concentration(self):
        c = [{"industrie": "Gold", "secteur_nom": "Matériaux"}] * 9 + [{"industrie": f"X{i}", "secteur_nom": "Industrie"} for i in range(51)]
        self.assertEqual(A.concentration(c, CFG["pepites"]), ["9 candidates sur 60 sont des mines d'or : sensibilité au cours de l'or."])


class TestWikipedia(unittest.TestCase):
    def test_tableau(self):
        html = ("<table class='wikitable'><tr><th>Ticker</th><th>Logo</th><th>Company</th><th>Prime Standard Sector</th></tr>"
                + "".join(f"<tr><td>{t}</td><td></td><td>{n}</td><td>{sct}</td></tr>" for t, n, sct in [
                    ("ADS.DE", "Adidas", "Consumer Goods"), ("AIR.PA", "Airbus", "Industrials"), ("ALV.DE", "Allianz", "Insurance"),
                    ("BAS.DE", "BASF", "Chemicals"), ("BAYN.DE", "Bayer", "Pharma & Healthcare"), ("BMW.DE", "BMW", "Automobile")])
                + "</table>")
        r = U.lire_wikipedia(html, "DE", {"suffixe": ".DE"})
        self.assertEqual([x["ticker"] for x in r], ["ADS.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BMW.DE"])  # Airbus (Paris) écarté
        self.assertEqual(r[1]["secteur"], "Financials")
        self.assertEqual(r[3]["secteur"], "Health Care")

    def test_prefixes_et_zero(self):
        html = ("<table class='wikitable'><tr><th>Ticker</th><th>Name</th><th>Sub-index</th></tr>"
                + "".join(f"<tr><td>{t}</td><td>{n}</td><td>Finance</td></tr>" for t, n in [
                    ("SEHK: 5", "HSBC"), ("SEHK: 388", "HKEx"), ("SSE: 600519", "Moutai"), ("SZSE: 300750", "CATL"), ("SEHK: 939", "CCB")])
                + "</table>")
        r = U.lire_wikipedia(html, "CN", {"suffixe": ".HK", "zero_pad": 4, "prefixes": {"SEHK": ".HK", "SSE": ".SS", "SZSE": ".SZ"}})
        self.assertEqual([x["ticker"] for x in r], ["0005.HK", "0388.HK", "600519.SS", "300750.SZ", "0939.HK"])

    def test_liste_nikkei(self):
        html = "<h3>Automotive</h3><ul>" + "".join(f"<li>{n} (TYO: {c})</li>" for n, c in [
            ("Toyota Motor Corp.", "7203"), ("Honda Motor Co., Ltd.", "7267"), ("Nissan", "7201"), ("Subaru", "7270"), ("Mazda", "7261")]) + "</ul>"
        r = U.lire_wikipedia(html, "JP", {"suffixe": ".T", "mode": "liste", "motif": "\\(TYO:\\s*([0-9A-Z]{4})\\)"})
        self.assertEqual(r[0], {"ticker": "7203.T", "nom": "Toyota Motor Corp.", "pays": "JP", "secteur": "Consumer Discretionary", "poids": 0.0})

    def test_page_sans_tableau(self):
        with self.assertRaises(ValueError):
            U.lire_wikipedia("<p>Top 10 constituents: Al Rajhi Bank…</p>", "SA", {"suffixe": ".SR"})


class TestCompositionsManquantes(unittest.TestCase):
    def test_global_x(self):
        csv = ("Global X MSCI Colombia ETF\nFund Holdings Data as of 11/02/2026\n"
               "% of Net Assets,Ticker,Name,SEDOL,Market Price ($),Shares Held,Market Value ($)\n"
               '0.03,"",COLOMBIAN PESO,"",0.0003,"146,321,312.77","45,798.11"\n'
               '-4.22,"",CASH,"",1.0,"-7,428,122.64","-7,428,122.64"\n'
               '15.57,PFCIBEST CB,GRUPO CIBEST SA,BTPR2M4,23.31,"1,177,011.00","27,438,489.63"\n'
               '7.97,ECOPETL CB,ECOPETROL SA,B2473N4,0.87,"16,144,629.00","14,047,947.56"\n')
        r = U.lire_positions_globalx(csv)
        self.assertEqual([(x["code"], x["poids"]) for x in r], [("PFCIBEST CB", 15.57), ("ECOPETL CB", 7.97)])

    def test_liste_manuelle_avant_la_derniere_liste_connue(self):
        connu = {"societes": [{"ticker": "OLD.VN", "nom": "Ancienne", "pays": "VN", "secteur": None, "poids": 1}]}
        man = {"VN": {"verifie_le": "2026-11-03", "societes": [{"ticker": "VCB.VN", "nom": "Vietcombank"}, {"ticker": "FPT.VN", "nom": "FPT"}]}}
        liste, etats = U.construire(None, CFG, connu, [], [], ["VN"], man)
        self.assertEqual([s["ticker"] for s in liste], ["VCB.VN", "FPT.VN"])
        self.assertEqual((etats["VN"]["etat"], etats["VN"]["verifie_le"]), ("manuelle", "2026-11-03"))
        self.assertIn("liste manuelle (vérifiée le 03/11/2026)", etats["VN"]["source"])

    def test_sante_liste_manuelle(self):
        from datetime import datetime, timezone
        from agents.entreprises import agent as AG
        d = Path(tempfile.mkdtemp())
        try:
            f = type("F", (), {"sec": type("S", (), {"actif": True})()})()
            etats = {"VN": {"etat": "manuelle", "source": "liste manuelle (vérifiée le 03/11/2026)", "verifie_le": "2026-11-03", "nombre": 6}}
            b = AG.enregistrer_sante(d, etats, None, f, {}, {}, datetime(2026, 12, 1, tzinfo=timezone.utc))
            self.assertFalse(b["degrade"])
            self.assertEqual(b["sources"][0]["manuelle"], "2026-11-03")
            b = AG.enregistrer_sante(d, etats, None, f, {}, {}, datetime(2027, 6, 1, tzinfo=timezone.utc))  # plus de 6 mois
            self.assertTrue(b["degrade"])
        finally:
            shutil.rmtree(d)

    def test_fichier_des_listes_manuelles(self):
        # Copie de test (tests/donnees) : les tests ne lisent jamais le vrai config/compositions_manuelles.json
        m = json.loads((DOSSIER / "tests" / "donnees" / "compositions_manuelles.json").read_text(encoding="utf-8"))["pays"]
        self.assertEqual(set(m), {"VN", "EG", "AE"})
        for code, v in m.items():
            date.fromisoformat(v["verifie_le"])
            self.assertTrue(v["source"].startswith("http"))
            self.assertGreaterEqual(len(v["societes"]), 10)


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
        copier_donnees_test(self.dossier)  # pays.json et macro.json de test, jamais les vrais data/
        donnees = DOSSIER / "tests" / "donnees"
        self.fichiers = ["--surveillance", str(donnees / "surveillance.json"),
                         "--compositions-manuelles", str(donnees / "compositions_manuelles.json")]

    def tearDown(self):
        shutil.rmtree(self.dossier)

    def test_execution_complete_puis_quotidienne(self):
        from agents.entreprises.agent import main
        self.assertEqual(main(["--mode", "complet", "--test", "--data", str(self.dossier), "--date", "2026-11-02", *self.fichiers]), 0)
        e = lire_json(self.dossier / "entreprises.json")
        self.assertFalse(e["meta"]["fictif"])
        self.assertGreater(len(e["donnees"]), 5)
        for x in e["donnees"]:
            self.assertIn(x["niveau"], ("attractif", "neutre", "defavorable"))
            self.assertTrue(A.ton_conforme(x["verdict"]))
            fiche = lire_json(self.dossier / x["fiche"].removeprefix("data/"))["donnees"]  # détail de la société
            self.assertTrue(fiche["contre_scenario"])
            if not fiche["sources"]["officielle"]:
                self.assertNotEqual(fiche["confiance"]["niveau"], "élevé")
        officielles = [lire_json(self.dossier / x["fiche"].removeprefix("data/"))["donnees"]["sources"]["officielle"] for x in e["donnees"]]
        self.assertIn("ESEF (filings.xbrl.org)", officielles)
        secteurs = lire_json(self.dossier / "secteurs.json")["donnees"]
        tickers = {x["ticker"] for x in e["donnees"]}
        for s in secteurs:
            self.assertTrue(set(s["entreprises"]) <= tickers)
        self.assertIsNotNone(lire_json(self.dossier / "pepites.json"))
        self.assertTrue((self.dossier / "recap" / "entreprises-2026-11-02.md").exists())
        sante = lire_json(self.dossier / "journal" / "agent-entreprises.json")["meta"]["sante"]
        self.assertEqual(sante["agent"], "entreprises")
        # Mise à jour quotidienne à partir de la base enregistrée
        self.assertEqual(main(["--mode", "quotidien", "--test", "--data", str(self.dossier), "--date", "2026-11-03", *self.fichiers]), 0)


if __name__ == "__main__":
    unittest.main()
