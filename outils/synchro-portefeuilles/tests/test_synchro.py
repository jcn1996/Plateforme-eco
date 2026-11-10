"""Tests de la synchronisation (relevés FICTIFS, sans réseau) :
python -m unittest discover -s outils/synchro-portefeuilles -t outils/synchro-portefeuilles"""
import json
import os
import sys
import unittest

ICI = os.path.dirname(__file__)
sys.path.insert(0, os.path.dirname(ICI))

import synchro_portefeuilles as s  # noqa: E402


class TestSynchro(unittest.TestCase):
    def test_ibkr(self):
        with open(os.path.join(ICI, "ibkr_fictif.xml"), "rb") as f:
            pf = s.ibkr_positions(f.read())
        self.assertEqual(len(pf), 1)
        p = pf[0]
        self.assertEqual(p["cle"], "ibkr-U***0000")
        self.assertNotIn("U0000000", json.dumps(pf), "numéro de compte masqué")
        lignes = {l["nom"]: l for l in p["lignes"]}
        self.assertEqual(len(p["lignes"]), 4, "ligne LOT ignorée, liquidités ajoutées")
        self.assertEqual(lignes["MICROSOFT CORP"]["ticker"], "MSFT")
        self.assertEqual(lignes["MICROSOFT CORP"]["valeur"], 3600.0)  # 4000 USD × 0,9
        self.assertEqual(lignes["AMUNDI MSCI WORLD (exemple)"]["ticker"], "CW8.PA")
        self.assertEqual(lignes["AMUNDI MSCI WORLD (exemple)"]["type"], "etf")
        self.assertEqual(lignes["BERKSHIRE HATHAWAY (exemple)"]["ticker"], "BRK-B")
        self.assertEqual(lignes["Liquidités"]["valeur"], 1234.5)
        self.assertEqual(lignes["MICROSOFT CORP"]["date"], "2026-11-09")

    def test_etoro(self):
        with open(os.path.join(ICI, "etoro_fictif.json"), encoding="utf-8") as f:
            brut = json.load(f)
        instruments = {
            1001: {"instrumentID": 1001, "symbolFull": "AAPL", "instrumentDisplayName": "Apple (exemple)", "instrumentTypeID": 5},
            1002: {"instrumentID": 1002, "symbolFull": "BMW.DE", "instrumentDisplayName": "BMW (exemple)", "instrumentTypeID": 5},
            100000: {"instrumentID": 100000, "symbolFull": "BTC", "instrumentDisplayName": "Bitcoin", "instrumentTypeID": 10},
        }
        lignes = {l["ticker"]: l for l in s.etoro_positions(brut, instruments, 1.1, "2026-11-10")}
        self.assertEqual(lignes["AAPL"]["quantite"], 3)  # deux positions agrégées, casses mélangées
        self.assertAlmostEqual(lignes["AAPL"]["prix_revient"], 110.0)
        self.assertAlmostEqual(lignes["AAPL"]["valeur"], 300.0, places=2)  # (330 + 0) / 1,1
        self.assertEqual(lignes["BTC-USD"]["type"], "crypto")
        self.assertIn("BMW.DE", lignes, "positions copiées (mirrors) incluses")
        self.assertIn("levier", lignes["BMW.DE"]["note"])

    def test_chiffrement_aller_retour(self):
        contenu = {"portefeuilles": [{"nom": "fictif", "lignes": [{"nom": "X", "valeur": 1.0}]}]}
        env = s.chiffrer(contenu, "mot de passe fictif", iterations=100_000)
        self.assertEqual(env["format"], s.FORMAT_CHIFFRE)
        self.assertNotIn("fictif", env["donnees"])
        self.assertEqual(s.dechiffrer(env, "mot de passe fictif"), contenu)
        with self.assertRaises(Exception):
            s.dechiffrer(env, "mauvais")

    def test_mot_de_passe_obligatoire(self):
        ancien = os.environ.pop("PORTEFEUILLE_MOT_DE_PASSE", None)
        try:
            self.assertEqual(s.main(["--sortie", os.devnull, "--sans-historiques"]), 1)
        finally:
            if ancien is not None:
                os.environ["PORTEFEUILLE_MOT_DE_PASSE"] = ancien

    def test_masquer(self):
        self.assertEqual(s.masquer("U1234567"), "U***4567")
        self.assertEqual(s.masquer("123"), "***")


if __name__ == "__main__":
    unittest.main()
