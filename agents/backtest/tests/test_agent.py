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


if __name__ == "__main__":
    unittest.main()
