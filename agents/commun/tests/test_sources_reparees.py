"""Sources réparées le 16/11/2026 (sans réseau) : Global X (429, protection anti-robots), gaz européen TTF (API « chart »
de Yahoo en repli), expéditions de ciment américaines (adresses directes des rapports USGS)."""
import unittest
from datetime import date

from agents.commun.telechargement import attente_demandee
from agents.donnees_alternatives.sources import USGS_PDF, liens_usgs_directs
from agents.matieres_premieres.sources import lire_chart_yahoo
from agents.pays.sources_flux import diagnostic_blocage


class Reponse:
    def __init__(self, code, entetes=None):
        self.status_code, self.headers = code, entetes or {}


class TestSources(unittest.TestCase):
    def test_attente_demandee_par_le_serveur(self):
        self.assertEqual(attente_demandee(Reponse(429, {"Retry-After": "20"})), 20.0)
        self.assertEqual(attente_demandee(Reponse(429, {"Retry-After": "3600"})), 120.0)  # bornée à 2 min
        self.assertEqual(attente_demandee(Reponse(429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})), 0.0)
        self.assertEqual(attente_demandee(Reponse(500, {"Retry-After": "20"})), 0.0)
        self.assertEqual(attente_demandee(None), 0.0)

    def test_global_x_protection_anti_robots(self):
        page = "<html><head><title>Vercel Security Checkpoint</title></head><body>…</body></html>"
        d = diagnostic_blocage("https://www.globalxetfs.com/funds/argt/ : HTTP 429", page)
        self.assertIn("protection anti-robots", d)
        self.assertIn("déclarées manquantes", d)
        self.assertIsNone(diagnostic_blocage("https://www.globalxetfs.com/funds/argt/ : HTTP 429", "Too many requests"))
        self.assertIsNone(diagnostic_blocage("HTTP 500", page))

    def test_ttf_api_chart_yahoo(self):
        j = {"chart": {"result": [{"meta": {"gmtoffset": -18000}, "timestamp": [1794546000, 1794632400, 1794718800],
                                   "indicators": {"quote": [{"close": [90.952, None, 84.8]}]}}]}}
        self.assertEqual(lire_chart_yahoo(j), [("2026-11-13", 90.952), ("2026-11-15", 84.8)])
        self.assertEqual(lire_chart_yahoo({"chart": {"result": None, "error": {"code": "Not Found"}}}), [])

    def test_ciment_usgs_adresses_directes(self):
        liens = liens_usgs_directs(date(2026, 1, 16), 3)
        self.assertEqual([m for _, m in liens], ["202512", "202511", "202510"])
        self.assertEqual(liens[0][0], USGS_PDF.format(mois="202512"))

    def test_flux_declares_manquants_avec_la_raison(self):
        import json
        from pathlib import Path
        from agents.pays import flux_etf
        cfg = json.loads((Path(__file__).resolve().parents[2] / "pays" / "config.json").read_text(encoding="utf-8"))["flux_etf"]
        serie = [{"date": "2026-11-05", "parts": 7634975.0, "vl": 74.14, "encours": 566040000.0, "source": "globalx"},
                 {"date": "2026-11-06", "parts": 7564975.0, "vl": 73.93, "encours": 559320000.0, "source": "globalx"}]
        etats = {"flux_globalx": "erreur : ARGT : requêtes automatiques bloquées par la protection anti-robots du site"}
        choix = flux_etf.choisir_releve("ARGT", "globalx", {"flux_yahoo_parts": {}}, cfg, date(2026, 11, 16), etats)
        self.assertEqual(choix["verification"], "aucune_source")
        self.assertIn("protection anti-robots", choix["sources"][0]["raison"])
        ind = flux_etf.indicateur("ARGT", "globalx", choix, serie, cfg, date(2026, 11, 16))
        self.assertIsNone(ind["valeur"])
        self.assertIn("aucune source disponible depuis le relevé du 2026-11-06", ind["raison"])
        self.assertIn("flux déclarés manquants", ind["raison"])


if __name__ == "__main__":
    unittest.main()
