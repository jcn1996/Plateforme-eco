"""Tests de l'agent initiés : données de test (formats réels de la SEC, de l'AMF, de la BaFin et du greffe de la
Chambre, contenus fictifs), sans réseau, dans un dossier temporaire (jamais les vrais config/ et data/)."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from agents.inities import analyse as A
from agents.inities.agent import main

DONNEES = Path(__file__).resolve().parent / "donnees"
CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
JOUR = "2026-11-06"


def depot(fichier: str) -> str:
    return json.loads((DONNEES / "depot.json").read_text(encoding="utf-8"))[fichier]


class TestFormulaire4(unittest.TestCase):
    def test_achat_du_pdg_retenu(self):
        f4 = A.lire_form4(depot("edgar/data/111/0000009001-26-000001.txt"))
        ops = A.operations(f4, "0000009001-26-000001", "2026-11-05")
        self.assertEqual(len(ops), 1)
        a = ops[0]
        self.assertEqual((a["type"], a["ticker"], a["fonction"], a["actions"], a["avant"]), ("achat", "SMLC", "pdg_daf", 20000, 10000))
        self.assertEqual(a["montant"], 200000)

    def test_plusieurs_lignes_regroupees(self):
        f4 = A.lire_form4(depot("edgar/data/111/0000009002-26-000001.txt"))
        a = A.operations(f4, "x", "2026-11-05")[0]
        self.assertEqual(a["actions"], 5000)
        self.assertEqual(a["avant"], 5000)  # 10 000 après, 5 000 achetées
        self.assertEqual(a["fonction"], "pdg_daf")  # directeur financier

    def test_operation_programmee_exclue(self):
        f4 = A.lire_form4(depot("edgar/data/320193/0000009004-26-000001.txt"))
        self.assertTrue(f4["programme_10b5_1"])
        self.assertEqual(A.operations(f4, "x", "2026-11-06"), [])

    def test_exercice_d_options_exclu(self):
        f4 = A.lire_form4(depot("edgar/data/320193/0000009005-26-000001.txt"))
        ops = A.operations(f4, "x", "2026-11-06")
        self.assertEqual([o["type"] for o in ops], ["vente"])  # le code M n'est pas un achat

    def test_vente_programmee_marquee(self):
        f4 = A.lire_form4(depot("edgar/data/1002910/0000009200-26-000001.txt"))
        self.assertTrue(A.operations(f4, "x", "2026-11-05")[0]["programme"])

    def test_fonctions(self):
        self.assertEqual(A.fonction({"titre": "President and CEO", "dirigeant": True}), "pdg_daf")
        self.assertEqual(A.fonction({"titre": "SVP Sales", "dirigeant": True}), "dirigeant")
        self.assertEqual(A.fonction({"titre": None, "administrateur": True}), "administrateur")
        self.assertEqual(A.fonction({"dix_pct": True}), "actionnaire_10pct")


class TestScore(unittest.TestCase):
    def achat(self, d, qui, fonction="dirigeant", actions=1000, avant=10000, ticker="X"):
        return {"date": d, "declarant": qui, "cik_declarant": qui, "fonction": fonction, "actions": actions, "avant": avant,
                "apres": avant + actions, "montant": actions * 10.0, "ticker": ticker, "devise": "USD", "pays": "US"}

    def test_achats_groupes_petite_valeur(self):
        achats = [self.achat("2026-11-01", "a", "pdg_daf", 5000, 5000), self.achat("2026-11-02", "b"), self.achat("2026-11-03", "c")]
        s = A.score_societe(achats, achats, None, 1.0, CONFIG, date(2026, 11, 6), "2025-01-01")
        self.assertEqual(s["acheteurs_30j"], 3)
        self.assertGreaterEqual(s["score"], 80)

    def test_achat_isole_grande_valeur_plus_faible(self):
        a = [self.achat("2026-11-01", "a", "administrateur", 100, 100000)]
        s = A.score_societe(a, a, None, 500.0, CONFIG, date(2026, 11, 6), "2025-01-01")
        self.assertLess(s["score"], 50)

    def test_achat_routinier(self):
        hist = [self.achat(d, "a") for d in ("2026-02-01", "2026-05-01", "2026-08-01")]
        a = self.achat("2026-11-01", "a")
        nature, _ = A.caractere(a, hist + [a], None, CONFIG, "2024-01-01")
        self.assertEqual(nature, "routinier")

    def test_achat_apres_baisse_opportuniste(self):
        cours = [["2026-07-01", 20.0], ["2026-10-30", 14.0]]
        nature, raison = A.caractere(self.achat("2026-11-01", "a"), [], cours, CONFIG, None)
        self.assertEqual(nature, "opportuniste")
        self.assertIn("baisse", raison)

    def test_historique_trop_court(self):
        nature, _ = A.caractere(self.achat("2026-11-01", "a"), [], None, CONFIG, "2026-10-01")
        self.assertEqual(nature, "inconnu")

    def test_ventes_ordinaires_pas_un_signal(self):
        v = [{"date": "2026-11-02", "declarant": "a", "actions": 100, "avant": 10000, "montant": 1e6, "programme": False},
             {"date": "2026-11-03", "declarant": "b", "actions": 100, "avant": 10000, "montant": 1e6, "programme": False}]
        self.assertIsNone(A.ventes_massives(v, CONFIG, date(2026, 11, 6)))


class TestTreizeF(unittest.TestCase):
    def test_mouvements(self):
        cur = A.lire_13f(depot("edgar/data/1549575/0001549575-26-000020.txt"))
        prec = A.lire_13f(depot("edgar/data/1549575/0001549575-26-000015.txt"))
        self.assertEqual(cur["periode"], "2026-09-30")
        c = A.comparer_13f(cur, prec, CONFIG)
        self.assertEqual(c["nb_positions"], 3)
        self.assertEqual([p["nom"] for p in c["nouvelles"]], ["SMALLCAP INDUSTRIES INC"])
        self.assertEqual([p["nom"] for p in c["allegements"]], ["WARRIOR MET COAL INC"])
        self.assertEqual([p["nom"] for p in c["sorties"]], ["CONSOL ENERGY INC"])
        self.assertAlmostEqual(sum(p["poids"] for p in c["positions"]), 100, delta=0.1)

    def test_options_hors_poids(self):
        c = A.comparer_13f(A.lire_13f(depot("edgar/data/1067983/0000950123-26-011000.txt")), None, CONFIG)
        self.assertEqual(c["nb_positions"], 3)
        self.assertEqual(c["options"][0]["option"], "PUT")

    def test_conviction_concentree(self):
        conv = A.conviction({"X": [{"cle": "a", "nom": "A", "poids": 12.0, "mouvement": "nouvelle"}],
                             "Y": [{"cle": "b", "nom": "B", "poids": 0.3, "mouvement": None}]}, CONFIG)
        self.assertGreater(conv["X"]["score"], conv["Y"]["score"])
        self.assertGreaterEqual(conv["X"]["score"], CONFIG["signaux"]["conviction_favorable"])

    def test_statut(self):
        self.assertEqual(A.statut_13f("2025-09-30", date(2026, 11, 6), CONFIG), "inactif")
        self.assertEqual(A.statut_13f("2026-06-30", date(2026, 11, 6), CONFIG), "actif")


class TestAutresSources(unittest.TestCase):
    def test_13d(self):
        x = A.lire_13d(depot("edgar/data/222/0000899140-26-001217.txt"))
        self.assertEqual((x["societe"], x["cik"], x["pct"], x["date_evenement"], x["investisseur"]),
                         ("Activ Target Corp", "222", 7.5, "2026-11-03", "Third Point LLC"))

    def test_amf(self):
        pdf = json.loads((DONNEES / "amf_pdf.json").read_text(encoding="utf-8"))
        a = A.lire_dd_amf(pdf["2026/a.pdf"], "n", "2026-11-05")
        self.assertEqual((a["date"], a["actions"], a["prix"], a["montant"], a["fonction"], a["devise"]), ("2026-11-03", 500, 600, 300000, "pdg_daf", "EUR"))
        self.assertIsNone(A.lire_dd_amf(pdf["2026/b.pdf"], "n", "2026-11-05"))  # cession

    def test_bafin(self):
        csv = json.loads((DONNEES / "bafin.json").read_text(encoding="utf-8"))["2026-10-07|2026-11-06"]
        r = A.lire_bafin(csv)
        self.assertEqual(len(r), 1)  # la vente (Verkauf) est ignorée
        self.assertEqual((r[0]["montant"], r[0]["prix"], r[0]["fonction"], r[0]["date"]), (1000000, 200, "pdg_daf", "2026-11-04"))

    def test_chambre(self):
        txt = json.loads((DONNEES / "chambre_ptr.json").read_text(encoding="utf-8"))["2026|20035770"]
        ops = A.lire_ptr_chambre(txt)
        self.assertEqual([(o["ticker"], o["type"], o["date_operation"]) for o in ops],
                         [("AAPL", "achat", "2026-09-14"), ("MSFT", "vente partielle", "2026-10-01")])

    def test_actionnariat_xbrl(self):
        xml = json.loads((DONNEES / "nse_xbrl.json").read_text(encoding="utf-8"))["https://nsearchives.nseindia.com/x/edel.xml"]
        shp = A.lire_actionnariat_xbrl(xml)
        self.assertEqual(shp["date"], "2026-09-30")
        self.assertIn({"nom": "Pabrai Wagons Fund", "pct": 1.54, "actions": 14572000.0, "categorie": "Cat1"}, shp["actionnaires"])

    def test_pourcentage_kap(self):
        self.assertEqual(A.pct_kap("paylarım 05/11/2026 tarihi itibariyle %.6,25 sınırına ulaşmıştır."), 6.25)
        self.assertEqual(A.pct_kap("sermayedeki paylarımız %5,40 sınırına ulaşmıştır"), 5.4)

    def test_nom_seul_compare(self):
        al = ["Pabrai", "Dalal Street, LLC", "Dhandho India Zero Fee Fund"]
        self.assertEqual(A.nom_correspond("Pabrai Investment funds along with pac", al), "Pabrai")
        self.assertEqual(A.nom_correspond("DHANDHO INDIA ZERO FEE FUND OFFSHORE LTD", al), "Dhandho India Zero Fee Fund")
        self.assertIsNone(A.nom_correspond("Dalal Street Investments Mumbai Pvt Ltd", al))  # nom courant en Inde

    def test_seuils(self):
        self.assertEqual(A.chercher_entites("Dalal Street, LLC a franchi le seuil de 5 % et détient 5,12 % du capital", ["Dalal Street"])[1], 5.12)
        self.assertEqual(A.chercher_entites("Pabrai Investment Fund 3 paylarında %5,40 oranına", ["Pabrai Investment Fund"])[1], 5.4)
        self.assertIsNone(A.chercher_entites("Autre Gestion détient 10 %", ["Dalal Street"]))


class TestAgent(unittest.TestCase):
    """Exécutions complètes de l'agent sur les données de test."""

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="inities-"))
        self.data = self.dossier / "data"
        self.data.mkdir()
        shutil.copy(DONNEES / "entreprises.json", self.data / "entreprises.json")
        self.donnees = self.dossier / "donnees"
        shutil.copytree(DONNEES, self.donnees)
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)
        shutil.rmtree(self.dossier, ignore_errors=True)

    def lancer(self, jour=JOUR, mode="complet"):
        code = main(["--test", "--donnees-test", str(self.donnees), "--data", str(self.data), "--mode", mode,
                     "--super-investisseurs", str(DONNEES / "super_investisseurs.json"), "--date", jour])
        self.assertEqual(code, 0)
        return json.loads((self.data / "inities.json").read_text(encoding="utf-8"))

    def test_execution_complete(self):
        d = self.lancer()["donnees"]
        soc = {s["cle"]: s for s in d["dirigeants"]["societes"]}
        self.assertEqual(set(soc), {"SMLC", "MC.PA", "SAP.DE"})  # AAPL : 10b5-1 et petit achat exclus
        self.assertGreaterEqual(soc["SMLC"]["score"], 80)
        self.assertEqual(soc["SMLC"]["acheteurs_30j"], 3)
        self.assertEqual([v["ticker"] for v in d["dirigeants"]["ventes_massives"]], ["AEE"])
        inv = {i["cle"]: i for i in d["super_investisseurs"]}
        self.assertEqual(inv["burry"]["statut"], "inactif")
        self.assertEqual(inv["ackman-ancien"]["statut"], "13F-NT")
        self.assertEqual(inv["pabrai"]["trimestre_texte"], "T3 2026")
        self.assertEqual({h["pays"] for h in inv["pabrai"]["hors_us"]}, {"FR", "TR", "IN"})
        self.assertEqual(d["mentions"]["13f"], "13F : positions américaines uniquement, avec jusqu'à 45 jours de retard")
        conv = {c["ticker"]: c for c in d["conviction"]}
        self.assertEqual(conv["SMLC"]["nombre"], 2)
        self.assertEqual(d["activistes"][0]["super_investisseur"], "loeb")
        self.assertEqual({e["ticker"]: e["retard_jours"] for e in d["elus"]}, {"AAPL": 49, "MSFT": 32})
        s = d["societes"]["SMLC"]
        self.assertEqual((s["score_achats"], s["acheteurs_30j"], len(s["super_investisseurs"])), (soc["SMLC"]["score"], 3, 2))
        self.assertTrue(d["societes"]["AEE"]["ventes_massives"])
        sig = json.loads((self.data / "signaux" / "inities.json").read_text(encoding="utf-8"))["donnees"]
        self.assertEqual({x["type"] for x in sig}, {"achats_groupes", "nouveau_13d"})
        j = json.loads((self.data / "journal" / "agent-inities.json").read_text(encoding="utf-8"))
        self.assertEqual(j["meta"]["sante"]["agent"], "inities")
        self.assertIn("agent-inities.json", (self.data / "journal" / "index.json").read_text(encoding="utf-8"))
        self.assertTrue((self.data / "recap" / f"inities-{JOUR}.md").exists())

    def test_relance_sans_doublon(self):
        self.lancer()
        etat = json.loads((self.data / "inities" / "etat.json").read_text(encoding="utf-8"))
        self.lancer()
        etat2 = json.loads((self.data / "inities" / "etat.json").read_text(encoding="utf-8"))
        self.assertEqual(len(etat["achats"]), len(etat2["achats"]))
        sig = json.loads((self.data / "signaux" / "inities.json").read_text(encoding="utf-8"))["donnees"]
        self.assertEqual(len([x for x in sig if x["type"] == "achats_groupes"]), 1)

    def test_nouveau_13f_signal(self):
        self.lancer()
        # Le trimestre précédent était le dernier lu : le 13F du 04/11 est nouveau
        chemin = self.data / "inities" / "etat.json"
        etat = json.loads(chemin.read_text(encoding="utf-8"))
        etat["f13"]["pabrai"]["accession"] = "0001549575-26-000015"
        chemin.write_text(json.dumps(etat), encoding="utf-8")
        self.lancer()
        sig = json.loads((self.data / "signaux" / "inities.json").read_text(encoding="utf-8"))["donnees"]
        nouv = [x for x in sig if x["type"] == "nouvelle_position_super_investisseur"]
        self.assertEqual([x["cle"] for x in nouv], ["SMLC"])
        self.assertEqual(nouv[0]["importance"], "forte")

    def test_mode_leger(self):
        d = self.lancer(mode="leger")["donnees"]
        etats = json.loads((self.data / "inities.json").read_text(encoding="utf-8"))["meta"]["etat_des_sources"]
        self.assertNotIn("SEC EDGAR, formulaires 4 (dirigeants)", etats)
        self.assertEqual(d["dirigeants"]["societes"], [])
        self.assertTrue(d["elus"])
        self.assertEqual(d["super_investisseurs"][0]["trimestre_texte"], "T3 2026")

    def test_positions_hors_us(self):
        d = self.lancer()["donnees"]
        pos = {(p["pays"], p["societe"]): p for p in d["positions_hors_us"] if p["investisseur"] == "pabrai"}
        edel = pos[("IN", "Edelweiss Financial Services Limited")]
        # Cession SAST sous 5 % en 2024, puis actionnaire de plus de 1 % au 30/09/2026 : position actuelle 1,54 %
        self.assertEqual((edel["pct"], edel["statut"], edel["entite"], edel["date"]), (1.54, "détenue", "Pabrai Wagons Fund", "2026-09-30"))
        self.assertEqual(pos[("IN", "Testco Industries Limited")]["statut"], "détenue")
        self.assertEqual((pos[("TR", "EXTKS")]["pct"], pos[("TR", "EXTKS")]["ticker"]), (5.4, "EXTKS.IS"))
        self.assertEqual(pos[("FR", "EXEMPLE SA")]["pct"], 5.12)
        self.assertNotIn(("IN", "Autre Limited"), pos)  # « Dalal Street » d'un autre déclarant
        # Rain : cession SAST à 3,96 % en 2024, absente des actionnaires de plus de 1 % au 30/09/2026
        rain = pos[("IN", "Rain Industries Limited")]
        self.assertEqual((rain["statut"], rain["type"], rain["date"], rain["pct"]), ("sous le seuil", "sortie", "2026-09-30", None))
        # Journal de la recherche : ce qui a été cherché, sur quelle période, et trouvé
        r = d["recherche_hors_us"]
        self.assertIn("Pabrai", r["noms_cherches"]["pabrai"])
        sast = r["sources"]["nse_sast"]
        self.assertEqual(sast["periodes"], ["2021-01-01", JOUR])
        self.assertEqual(sast["documents_examines"], 5)
        self.assertEqual(len(sast["trouves"]), 3)
        self.assertIn("clé non configurée", r["sources"]["dart"]["detail"])
        self.assertIn("clé non configurée", r["sources"]["edinet"]["detail"])
        self.assertEqual(r["sources"]["kap"]["documents_examines"], 2)  # deux notifications DKB lues, rapport financier ignoré
        etat = json.loads((self.data / "inities" / "etat.json").read_text(encoding="utf-8"))
        self.assertEqual(etat["curseurs_hors_us"]["nse_sast"], "2021-01-01")  # historique entièrement rattrapé
        self.assertLess(etat["curseurs_hors_us"]["kap"], "2026-10-27")  # rattrapage KAP commencé
        # Conviction : la position indienne compte pour la société (ticker NSE)
        self.assertEqual(d["societes"]["EDELWEISS.NS"]["super_investisseurs"][0]["pct_capital"], 1.54)
        recap = (self.data / "recap" / f"inities-{JOUR}.md").read_text(encoding="utf-8")
        self.assertIn("Recherche effectuée", recap)
        self.assertIn("Pabrai Wagons Fund", recap)

    def test_sortie_sous_1_pct(self):
        self.lancer()
        # Trimestre suivant : Pabrai ne figure plus parmi les actionnaires de plus de 1 % d'Edelweiss
        chemin = self.donnees / "nse_actionnariat.json"
        d = json.loads(chemin.read_text(encoding="utf-8"))
        d["EDELWEISS"].insert(0, {"date": "31-DEC-2026", "id": "220001", "xbrl": "https://nsearchives.nseindia.com/x/edel-t4.xml",
                                  "societe": "Edelweiss Financial Services Limited", "depot": "15-JAN-2027"})
        chemin.write_text(json.dumps(d), encoding="utf-8")
        d = self.lancer("2027-01-20")["donnees"]
        edel = next(p for p in d["positions_hors_us"] if p["societe"] == "Edelweiss Financial Services Limited")
        self.assertEqual((edel["statut"], edel["type"], edel["date"]), ("sous le seuil", "sortie", "2026-12-31"))

    def test_kap_secondaire_ne_degrade_pas(self):
        (self.donnees / "kap_liste.json").unlink()
        self.lancer()
        j = json.loads((self.data / "journal" / "agent-inities.json").read_text(encoding="utf-8"))
        s = j["meta"]["sante"]
        kap = next(x for x in s["sources"] if x["nom"].startswith("KAP"))
        self.assertEqual((kap["etat"], kap["secondaire"]), ("échec", True))
        self.assertFalse(s["degrade"])
        self.assertEqual(j["donnees"][-1]["recherche_hors_us"]["sources"]["kap"]["etat"][:6], "erreur")

    def test_source_en_panne(self):
        (self.donnees / "bafin.json").unlink()
        d = self.lancer()["donnees"]
        self.assertNotIn("SAP.DE", {s["cle"] for s in d["dirigeants"]["societes"]})
        j = json.loads((self.data / "journal" / "agent-inities.json").read_text(encoding="utf-8"))
        bafin = next(s for s in j["meta"]["sante"]["sources"] if s["nom"].startswith("BaFin"))
        self.assertEqual(bafin["etat"], "échec")


if __name__ == "__main__":
    unittest.main()
