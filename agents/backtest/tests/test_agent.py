"""Backtest complet sur données synthétiques, dans un dossier temporaire (sans réseau, sans config/ ni data/)."""
import json
import logging
import tempfile
import unittest
from pathlib import Path

from agents.backtest.agent import main


class TestAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dossier = tempfile.TemporaryDirectory()
        cls.sortie = Path(cls.dossier.name) / "backtest"
        logging.disable(logging.INFO)
        try:
            cls.code = main(["--test", "--sortie", str(cls.sortie), "--date", "2026-11-14"])
        finally:
            logging.disable(logging.NOTSET)

    @classmethod
    def tearDownClass(cls):
        cls.dossier.cleanup()

    def test_fichiers(self):
        self.assertEqual(self.code, 0)
        for f in ("resultats.json", "rapport-2026-11.md", "proposition-2026-11.json"):
            self.assertTrue((self.sortie / f).exists(), f)

    def test_resultats(self):
        r = json.loads((self.sortie / "resultats.json").read_text(encoding="utf-8"))
        self.assertTrue(r["meta"]["fictif"])
        d = r["donnees"]
        self.assertEqual(set(d["sections"]), {"pays", "chef", "entreprises", "matieres", "secteurs", "tendance"})
        verdicts = {"Garder", "Alléger", "Supprimer", "Données insuffisantes"}
        for s in d["sections"].values():
            for sig in s["signaux"].values():
                self.assertIn(sig["verdict"], verdicts)
                self.assertIn(str(s["horizon_reference"]), sig["horizons"])
        self.assertIn("momentum", d["sections"]["pays"]["signaux"])
        self.assertIn("note_globale", d["sections"]["entreprises"]["signaux"])
        self.assertIn("stops", d["sections"]["entreprises"]["regles"])
        self.assertIn("concentration", d["sections"]["chef"]["regles"])
        self.assertIn("forte_saine", d["sections"]["chef"]["regles"]["tendance"]["horizons"]["3"])
        t = d["sections"]["tendance"]["suivi_tendance"]
        self.assertIn(t["definition"], ("12-1", "12", "6-1", "6", "3-1"))
        self.assertEqual(set(t["periodes"]["definitions"]), {"12-1", "12", "6-1", "6", "3-1"})
        self.assertTrue({"parabolique", "valorisation", "positionnement"} <= set(t["exces"]))
        self.assertTrue(t["poche"]["variantes"])
        self.assertIsNotNone(t["poche"]["retenue"])
        self.assertTrue(d["non_testables"])

    def test_rapport_et_proposition(self):
        texte = (self.sortie / "rapport-2026-11.md").read_text(encoding="utf-8")
        for mot in ("Biais du survivant", "Non testables", "Note actuelle contre note recalibrée", "Suivi de tendance", "Poche « tendance »", "Stops"):
            self.assertIn(mot, texte)
        p = json.loads((self.sortie / "proposition-2026-11.json").read_text(encoding="utf-8"))
        fichiers = {x["fichier"] for x in p["propositions"]}
        self.assertTrue({"agents/pays/config.json", "agents/chef/config.json", "agents/entreprises/config.json"} <= fichiers)
        for x in p["propositions"]:
            self.assertAlmostEqual(sum(x["propose"].values()), sum(x["actuel"].values()), places=2)

    def test_variations_reference_combinaisons(self):
        d = json.loads((self.sortie / "resultats.json").read_text(encoding="utf-8"))["donnees"]
        pays = d["sections"]["pays"]["signaux"]
        for k in ("croissance_pib", "indicateur_avance", "inflation", "taux_reel", "devise_3m", "valorisation"):
            self.assertIn(f"var3_{k}", pays)
            self.assertIn(f"var6_{k}", pays)
        self.assertEqual(pays["var3_inflation"]["libelle"], "Inflation — variation 3 mois")
        self.assertIn("var_marge_op", d["sections"]["entreprises"]["signaux"])
        self.assertIn("var3_positionnement", d["sections"]["matieres"]["signaux"])
        for nom in ("pays", "entreprises", "matieres"):
            s = d["sections"][nom]
            self.assertIn("vs_indice_annuel_pct", s["reference_momentum"]["verification"])
            ng = s["signaux"]["note_globale"]
            self.assertIn("vs_momentum_annuel_pct", ng["portefeuille"]["verification"])  # chaque note face au momentum seul
            for h in ("3", "6"):
                self.assertIn("battent_indice_pct", ng["horizons"][h])
                self.assertIn("gain_perte", ng["horizons"][h])
            c = s["combinaisons"]
            self.assertLessEqual(c["essais"], 8 * 7 // 2 + 8 * 7 * 6 // 6)  # au plus C(8,2) + C(8,3)
            for r in c["retenues"]:
                self.assertIn(r["verdict"], ("Confirmée", "Prometteuse (non significative)", "Non confirmée"))
                self.assertIn("vs_momentum_annuel_pct", r["comparaison"]["verification"])
                self.assertIn("gain_perte", r["cible"]["6"])
        self.assertTrue(1 <= len(d["en_bref"]) <= 10)

    def test_resume_final(self):
        texte = (self.sortie / "rapport-2026-11.md").read_text(encoding="utf-8")
        fin = texte.rstrip().split("## En bref")[-1].strip().splitlines()
        self.assertTrue(texte.rstrip().rfind("## En bref") > texte.rfind("## Sources"))  # le rapport se termine par le résumé
        self.assertLessEqual(len([l for l in fin if l.strip()]), 10)
        for mot in ("Ce qui anticipe", "Ce qui n'anticipe pas", "Bat le momentum seul"):
            self.assertIn(mot, texte.split("## En bref")[-1])
        self.assertIn("Cible et comparaison au « momentum seul »", texte)
        self.assertIn("Combinaisons de signaux", texte)


if __name__ == "__main__":
    unittest.main()
