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
        self.assertEqual(len(p["lignes"]), 8, "ligne LOT ignorée, liquidités ajoutées")
        self.assertEqual(lignes["MICROSOFT CORP"]["ticker"], "MSFT")
        self.assertEqual(lignes["MICROSOFT CORP"]["valeur"], 3600.0)  # 4000 USD × 0,9
        self.assertEqual(lignes["AMUNDI MSCI WORLD (exemple)"]["ticker"], "CW8.PA")
        self.assertEqual(lignes["AMUNDI MSCI WORLD (exemple)"]["type"], "etf")
        self.assertEqual(lignes["BERKSHIRE HATHAWAY (exemple)"]["ticker"], "BRK-B")
        self.assertEqual(lignes["Liquidités"]["valeur"], 1234.5)
        self.assertEqual(lignes["MICROSOFT CORP"]["date"], "2026-11-09")

    def test_ibkr_options(self):
        with open(os.path.join(ICI, "ibkr_fictif.xml"), "rb") as f:
            lignes = {l["nom"]: l for l in s.ibkr_positions(f.read())[0]["lignes"]}
        call = lignes["MSFT 18DEC26 450 C"]
        self.assertEqual(call["type"], "option")
        self.assertIsNone(call["ticker"], "jamais le ticker du sous-jacent")
        self.assertEqual(call["multiplicateur"], 100)
        self.assertEqual(call["prix_revient"], 10)
        self.assertEqual(call["valeur"], 2250.0)  # 2 × 12,5 × 100 USD × 0,9
        self.assertEqual(call["option"], {"sous_jacent": "MSFT", "echeance": "2026-12-18", "prix_exercice": 450, "sens": "call"})
        # Sans champs Flex : symbole OCC, multiplicateur 100 par défaut, position vendeuse
        put = lignes["OPTION FICTIVE (exemple)"]
        self.assertEqual(put["option"], {"sous_jacent": "XYZ", "echeance": "2027-01-15", "prix_exercice": 50, "sens": "put"})
        self.assertEqual(put["multiplicateur"], 100)
        self.assertAlmostEqual(put["prix_revient"], 3.0)  # −300 ÷ (−1 × 100)
        self.assertEqual(put["valeur"], -180.0)
        self.assertEqual(s.option_ibkr({"description": "ABC 18DEC26 45.5 P"}), {"sous_jacent": "ABC", "echeance": "2026-12-18", "prix_exercice": 45.5, "sens": "put"})

    def test_ibkr_prix_revient_manquant(self):
        with open(os.path.join(ICI, "ibkr_fictif.xml"), "rb") as f:
            lignes = {l["nom"]: l for l in s.ibkr_positions(f.read())[0]["lignes"]}
        self.assertAlmostEqual(lignes["PETROLE FICTIF (exemple)"]["prix_revient"], 15.0)  # Cost Basis Money ÷ quantité
        self.assertEqual(lignes["PETROLE FICTIF (exemple)"]["ticker"], "PFX.TO")
        self.assertNotIn("multiplicateur", lignes["PETROLE FICTIF (exemple)"])
        self.assertIsNone(lignes["SANS COUT FICTIF (exemple)"]["prix_revient"])

    def test_symboles_etoro(self):
        self.assertEqual(s.symbole_yahoo_etoro("GOOG"), "GOOGL")
        self.assertEqual(s.symbole_yahoo_etoro("ZURN.ZU"), "ZURN.SW")
        self.assertEqual(s.symbole_yahoo_etoro("BARC.L"), "BARC.L")
        self.assertEqual(s.symbole_yahoo_etoro("PHIA.NV"), "PHIA.AS")
        self.assertEqual(s.symbole_yahoo_etoro("EDP.LSB"), "EDP.LS")
        self.assertEqual(s.symbole_yahoo_etoro("700.HK"), "0700.HK")
        self.assertEqual(s.symbole_yahoo_etoro("BRK.B"), "BRK-B")
        self.assertEqual(s.symbole_yahoo_etoro("FIG"), "FIG")
        self.assertEqual(s.symbole_yahoo_etoro("BTC"), "BTC-USD")
        self.assertEqual(s.symbole_yahoo_etoro("ETHUSD"), "ETH-USD")
        self.assertEqual(s.symbole_yahoo_etoro("BTC", crypto=False), "BTC", "type eToro « action » prioritaire")

    def test_profils_publics(self):
        demandes = []

        def faux_yahoo(symbole):  # aucun réseau : réponses fictives
            demandes.append(symbole)
            return {"FIG": {"sector": "Technology", "country": "United States"}}.get(symbole, {})

        pf = [{"lignes": [
            {"ticker": "FIG", "type": "action", "quantite": 12},
            {"ticker": "BTC-USD", "type": "crypto", "quantite": 0.1},
        ]}]
        profils = s.profils_publics(["FIG", "INCONNU"], lire=faux_yahoo)
        self.assertEqual(profils, {"FIG": {"secteur": "Information Technology", "pays": "US", "source": "Yahoo Finance"}})
        self.assertEqual(demandes, ["FIG", "INCONNU"], "seuls les symboles sont transmis")
        s.ajouter_profils(pf, profils)
        self.assertEqual(pf[0]["lignes"][0]["profil_public"]["pays"], "US")
        self.assertNotIn("profil_public", pf[0]["lignes"][1])

    def test_etoro(self):
        with open(os.path.join(ICI, "etoro_fictif.json"), encoding="utf-8") as f:
            brut = json.load(f)
        instruments = {
            1001: {"instrumentID": 1001, "symbolFull": "AAPL", "instrumentDisplayName": "Apple (exemple)", "instrumentTypeID": 5},
            1002: {"instrumentID": 1002, "symbolFull": "BMW.DE", "instrumentDisplayName": "BMW (exemple)", "instrumentTypeID": 5},
            100000: {"instrumentID": 100000, "symbolFull": "BTC", "instrumentDisplayName": "Bitcoin", "instrumentTypeID": 10},
            1003: {"instrumentID": 1003, "symbolFull": "GOOG", "instrumentDisplayName": "Classe C (exemple)", "instrumentTypeID": 5},
            1004: {"instrumentID": 1004, "symbolFull": "ZURN.ZU", "instrumentDisplayName": "Assureur suisse (exemple)", "instrumentTypeID": 5},
            1005: {"instrumentID": 1005, "symbolFull": "FIG", "instrumentDisplayName": "Introduction récente (exemple)", "instrumentTypeID": 5},
        }
        lignes = {l["ticker"]: l for l in s.etoro_positions(brut, instruments, 1.1, "2026-11-10")}
        self.assertEqual(lignes["AAPL"]["quantite"], 3)  # deux positions agrégées, casses mélangées
        self.assertAlmostEqual(lignes["AAPL"]["prix_revient"], 110.0)
        self.assertAlmostEqual(lignes["AAPL"]["valeur"], 300.0, places=2)  # (330 + 0) / 1,1
        self.assertEqual(lignes["BTC-USD"]["type"], "crypto")
        self.assertIn("BMW.DE", lignes, "positions copiées (mirrors) incluses")
        self.assertIn("levier", lignes["BMW.DE"]["note"])
        self.assertEqual(lignes["GOOGL"]["type"], "action")
        self.assertEqual(lignes["ZURN.SW"]["quantite"], 2)
        self.assertEqual(lignes["FIG"]["type"], "action")

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
