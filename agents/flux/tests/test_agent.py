"""Tests de l'agent flux commerciaux, sans réseau : python -m unittest discover -s agents/flux -t .

Ils ne lisent ni ne modifient les vrais config/ et data/ : tout se passe dans un dossier temporaire,
avec les réponses enregistrées du FMI et de UN Comtrade (tests/donnees/, voir capturer_donnees_test.py).
"""
import logging
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.commun.sortie import ecrire_json, lire_json
from agents.flux import agent

DATE_TEST = "2026-08-20"
MAINTENANT = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
TOUS = list(agent.CONFIG["pays"])


def lancer(dossier: Path, donnees_test: Path = agent.DONNEES_TEST, date: str = DATE_TEST) -> int:
    return agent.main(["--test", "--data", str(dossier), "--donnees-test", str(donnees_test), "--date", date])


class Base(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.d = Path(tempfile.mkdtemp(prefix="flux-"))

    def tearDown(self):
        logging.disable(logging.NOTSET)
        shutil.rmtree(self.d, ignore_errors=True)


class TestMois(unittest.TestCase):
    def test_decaler(self):
        self.assertEqual(agent.decaler("2026-07", -12), "2025-07")
        self.assertEqual(agent.decaler("2026-01", -1), "2025-12")
        self.assertEqual(agent.decaler("2025-12", 1), "2026-01")
        self.assertEqual(agent.ecart_mois("2026-07", "2026-11"), 4)


class TestCalcul(unittest.TestCase):
    def test_exportations_puis_miroir(self):
        series = {
            ("X", "FR", "DE"): {"2025-07": 8e9, "2026-07": 10e9},   # exportations de la France
            ("M", "DE", "FR"): {"2025-07": 9e9, "2026-07": 11e9},   # miroir, même mois : ignoré
            ("M", "US", "TW"): {"2025-07": 20e9, "2026-07": 19e9},  # Taïwan ne déclare pas : miroir américain
            ("X", "US", "MX"): {"2025-06": 30e9, "2026-06": 30e9},
            ("M", "MX", "US"): {"2025-07": 25e9, "2026-07": 26e9},  # miroir plus récent : retenu
        }
        flux = {(f["de"], f["vers"]): f for f in agent.calculer_flux(series, ["FR", "DE", "US", "TW", "MX"], 5)}
        fr = flux[("FR", "DE")]
        self.assertEqual((fr["montant_md"], fr["periode"], fr["mesure"], fr["declarant"]), (10.0, "2026-07", "exportations", "FR"))
        self.assertEqual((fr["variation_12m_pct"], fr["tendance"]), (25.0, "hausse"))
        tw = flux[("TW", "US")]
        self.assertEqual((tw["mesure"], tw["declarant"], tw["variation_12m_pct"], tw["tendance"]), ("importations", "US", -5.0, "baisse"))
        us = flux[("US", "MX")]
        self.assertEqual((us["periode"], us["mesure"], us["tendance"]), ("2026-07", "importations", "stable"))
        self.assertNotIn(("DE", "FR"), flux)  # aucune donnée dans ce sens

    def test_variation_inconnue(self):
        f = agent.calculer_flux({("X", "FR", "DE"): {"2026-07": 1e9}}, ["FR", "DE"], 5)[0]
        self.assertIsNone(f["variation_12m_pct"])
        self.assertEqual(f["tendance"], "inconnue")

    def test_selection(self):
        codes = ["A", "B", "C", "D", "E"]
        flux = [{"de": a, "vers": b, "montant_md": float(i)} for i, (a, b) in
                enumerate((a, b) for a in codes for b in codes if a != b)]
        choisis = agent.selectionner(flux, codes, n=2, m=3)
        for c in codes:
            self.assertEqual(sum(f["top_de"] for f in choisis if f["de"] == c), 2)
            self.assertEqual(sum(f["top_vers"] for f in choisis if f["vers"] == c), 2)
        mondiaux = [f for f in choisis if f["mondial"]]
        self.assertEqual([f["montant_md"] for f in mondiaux], [19.0, 18.0, 17.0])
        self.assertTrue(all(f["top_de"] or f["top_vers"] or f["mondial"] for f in choisis))
        self.assertLess(len(choisis), len(flux))  # les petits flux sont écartés
        self.assertEqual(choisis, sorted(choisis, key=lambda f: -f["montant_md"]))


class TestSources(unittest.TestCase):
    def test_fmi_enregistre(self):
        series = agent.lire_fmi(agent.LecteurTest(agent.DONNEES_TEST), TOUS, "2025-01")
        self.assertIn(("X", "MX", "US"), series)
        self.assertIn(("M", "US", "TW"), series)
        self.assertNotIn("TW", {decl for (_, decl, _) in series})  # Taïwan ne déclare pas au FMI
        self.assertGreater(series[("X", "MX", "US")]["2026-07"], 1e10)

    def test_comtrade_enregistre(self):
        series = agent.lire_comtrade(agent.LecteurTest(agent.DONNEES_TEST), TOUS, MAINTENANT)
        mois = {p for s in series.values() for p in s}
        self.assertEqual(mois, {"2026-06", "2025-06"})
        self.assertIn(("X", "US", "CA"), series)


class TestAgent(Base):
    def test_execution_complete(self):
        ecrire_json(self.d / "pays.json", {"meta": {}, "donnees": [{"code": c} for c in TOUS]})
        # Point de départ : l'ancien fichier fictif
        ecrire_json(self.d / "flux.json", {"meta": {"fictif": True}, "donnees": [{"de": "US", "vers": "IN", "montant_md": 18.4}]})
        self.assertEqual(lancer(self.d), 0)
        f = lire_json(self.d / "flux.json")
        self.assertFalse(f["meta"]["fictif"])
        self.assertEqual(f["meta"]["source"], agent.SOURCE_FMI)
        self.assertEqual(f["meta"]["periode_recente"], "2026-07")
        self.assertIn("décalées de 1 à 2 mois", f["meta"]["mention"])
        flux = f["donnees"]
        self.assertEqual(sum(x["mondial"] for x in flux), agent.CONFIG["flux_mondiaux"])
        for c in TOUS:
            self.assertLessEqual(sum(x["top_de"] for x in flux if x["de"] == c), agent.CONFIG["partenaires_par_pays"])
        self.assertTrue(any(x["de"] == "TW" for x in flux))
        self.assertTrue(all(x["tendance"] in ("hausse", "baisse", "stable", "inconnue") for x in flux))

        j = lire_json(self.d / "journal" / "agent-flux.json")
        s = j["meta"]["sante"]
        self.assertEqual((s["agent"], s["workflow"], s["sources_ok"], s["degrade"]), ("flux", "agent-flux.yml", 1, False))
        self.assertEqual(s["planning"]["crons"], ["23 5 * * 2"])
        self.assertEqual(s["prochaine_prevue"], "2026-08-25T05:23:00Z")  # mardi suivant
        index = lire_json(self.d / "journal" / "index.json")["donnees"]
        self.assertIn("agent-flux.json", [e["fichier"] for e in index])

        # Deuxième exécution identique : le fichier des flux n'est pas réécrit
        genere = f["meta"]["genere_le"]
        lancer(self.d)
        self.assertEqual(lire_json(self.d / "flux.json")["meta"]["genere_le"], genere)

    def test_secours_comtrade(self):
        donnees = self.d / "donnees"
        donnees.mkdir()
        for p in agent.DONNEES_TEST.glob("comtrade_*.json"):
            shutil.copy(p, donnees)  # pas de réponse du FMI
        self.assertEqual(lancer(self.d / "data", donnees), 0)
        f = lire_json(self.d / "data" / "flux.json")
        self.assertEqual(f["meta"]["source"], agent.SOURCE_COMTRADE)
        self.assertEqual(f["meta"]["periode_recente"], "2026-06")
        s = lire_json(self.d / "data" / "journal" / "agent-flux.json")["meta"]["sante"]
        self.assertEqual([x["etat"] for x in s["sources"]], ["échec", "secours"])
        self.assertTrue(s["degrade"])

    def test_toutes_sources_en_panne(self):
        ancien = {"meta": {"fictif": False, "source": "x"}, "donnees": [{"de": "US", "vers": "CA", "montant_md": 1.0}]}
        ecrire_json(self.d / "data" / "flux.json", ancien)
        vide = self.d / "vide"
        vide.mkdir()
        self.assertEqual(lancer(self.d / "data", vide), 0)
        self.assertEqual(lire_json(self.d / "data" / "flux.json"), ancien)  # dernier fichier conservé
        s = lire_json(self.d / "data" / "journal" / "agent-flux.json")["meta"]["sante"]
        self.assertEqual([x["etat"] for x in s["sources"]], ["échec", "échec"])
        self.assertEqual(s["sources_ok"], 0)

    def test_donnees_perimees(self):
        lancer(self.d, date="2027-06-01")  # dernier mois 2026-07 : 11 mois de retard
        s = lire_json(self.d / "journal" / "agent-flux.json")["meta"]["sante"]
        self.assertEqual(s["sources"][0]["etat"], "périmée")
        self.assertTrue(s["degrade"])

    def test_pays_suivis(self):
        ecrire_json(self.d / "pays.json", {"meta": {}, "donnees": [{"code": "FR"}, {"code": "DE"}, {"code": "XX"}]})
        self.assertEqual(agent.codes_suivis(self.d), ["FR", "DE"])
        self.assertEqual(agent.codes_suivis(self.d / "absent"), TOUS)


if __name__ == "__main__":
    unittest.main()
