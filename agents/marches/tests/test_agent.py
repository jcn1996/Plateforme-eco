"""Tests de l'agent marchés, sans réseau : python -m unittest discover -s agents -t ."""
import unittest
from datetime import date, datetime, timedelta, timezone

from agents.marches import agent

NDX = agent.ACTIFS[0]
BTC = next(a for a in agent.ACTIFS if a["symbole"] == "BTC-USD")
UTC = timezone.utc


class TestCalcul(unittest.TestCase):
    def test_variations(self):
        heure = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
        clotures = [(date(2025, 10, 31), 100.0), (date(2025, 11, 3), 105.0),
                    (date(2026, 10, 30), 200.0), (date(2026, 11, 2), 210.0)]
        e = agent.calculer(NDX, 210.0, heure, clotures, True, "Yahoo Finance")
        self.assertEqual(e["variation"], 5.0)        # 210 / 200
        self.assertEqual(e["variation_1an"], 110.0)  # 210 / 100 (clôture du 31/10/2025, ≤ 02/11/2025)
        self.assertEqual(e["heure"], "2026-11-02T16:00:00Z")
        self.assertEqual(e["statut"], "ouvert")
        self.assertFalse(e["ancienne"])

    def test_historique_insuffisant(self):
        heure = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
        e = agent.calculer(NDX, 10.0, heure, [(date(2026, 11, 2), 10.0)], False, "Stooq")
        self.assertIsNone(e["variation"])
        self.assertIsNone(e["variation_1an"])
        self.assertEqual(e["statut"], "fermé")


class TestStatut(unittest.TestCase):
    maintenant = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)

    def test_seance(self):
        debut, fin = self.maintenant - timedelta(hours=3), self.maintenant + timedelta(hours=3)
        self.assertTrue(agent.est_ouvert(NDX, self.maintenant - timedelta(minutes=15), self.maintenant, debut, fin))
        self.assertFalse(agent.est_ouvert(NDX, self.maintenant - timedelta(minutes=15), self.maintenant + timedelta(hours=4), debut, fin))
        # Jour férié : dans les horaires, mais aucun cours récent
        self.assertFalse(agent.est_ouvert(NDX, self.maintenant - timedelta(days=1), self.maintenant, debut, fin))

    def test_bitcoin(self):
        self.assertTrue(agent.est_ouvert(BTC, self.maintenant - timedelta(minutes=30), self.maintenant))


class TestStooq(unittest.TestCase):
    def test_lecture(self):
        prix, heure = agent.lire_stooq_cours("Symbol,Date,Time,Open,High,Low,Close,Volume\n^NDX,2026-11-02,18:30:00,1,2,0,28450.5,0\n")
        self.assertEqual(prix, 28450.5)
        self.assertEqual(heure, datetime(2026, 11, 2, 17, 30, tzinfo=UTC))  # 18:30 heure de Varsovie (UTC+1)
        self.assertEqual(agent.lire_stooq_quotidien("Date,Open,High,Low,Close,Volume\n2026-10-30,1,2,0,3.5,0\n"),
                         [(date(2026, 10, 30), 3.5)])
        with self.assertRaises(agent.ErreurSource):
            agent.lire_stooq_cours("Symbol,Date,Time,Open,High,Low,Close,Volume\n^NDX,N/D,N/D,N/D,N/D,N/D,N/D,N/D\n")


class TestSecours(unittest.TestCase):
    def test_ordre_des_sources(self):
        maintenant = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
        precedentes = {BTC["nom"]: {"nom": BTC["nom"], "valeur": 1.0, "heure": "2026-11-01T10:00:00Z",
                                    "source": "Yahoo Finance", "statut": "ouvert"}}

        def yahoo(a, m):
            if a["symbole"] in ("BTC-USD", "^FCHI"):
                raise agent.ErreurSource("panne")
            return {"nom": a["nom"], "valeur": 1, "variation": 0, "variation_1an": 0, "statut": "ouvert", "source": "Yahoo Finance"}

        def stooq(a, m, t):
            if a["symbole"] == "^FCHI":
                return {"nom": a["nom"], "valeur": 2, "variation": 0, "variation_1an": 0, "statut": "fermé", "source": "Stooq"}
            raise agent.ErreurSource("panne")

        res = agent.collecter(maintenant, precedentes, yahoo, stooq)
        self.assertEqual([e["nom"] for e in res], [a["nom"] for a in agent.ACTIFS])
        par_nom = {e["nom"]: e for e in res}
        self.assertEqual(par_nom["CAC 40"]["source"], "Stooq")
        self.assertTrue(par_nom["Bitcoin"]["ancienne"])
        self.assertEqual(par_nom["Bitcoin"]["heure"], "2026-11-01T10:00:00Z")
        self.assertEqual(par_nom["Bitcoin"]["statut"], "fermé")


if __name__ == "__main__":
    unittest.main()
