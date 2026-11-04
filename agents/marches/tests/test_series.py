"""Séries compactes pour les graphiques de secours de l'appli."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from agents.commun.series import serie_graphique
from agents.marches import agent


class TestSeries(unittest.TestCase):
    def setUp(self):
        debut = date(2025, 1, 1)
        self.points = [(debut + timedelta(days=i), 100 + i, 1000) for i in range(500)]

    def test_un_an_quotidien(self):
        s = serie_graphique(self.points)
        self.assertEqual(s[-1], [(date(2025, 1, 1) + timedelta(days=499)).isoformat(), 599])
        self.assertLessEqual(len(s), 373)
        self.assertTrue(all(a[0] < b[0] for a, b in zip(s, s[1:])))

    def test_hebdomadaire(self):
        s = serie_graphique(self.points, hebdo=True)
        self.assertTrue(52 <= len(s) <= 55)
        self.assertEqual(s[-1][1], 599)  # la dernière séance est toujours conservée

    def test_valeurs_aberrantes_ignorees(self):
        self.assertEqual(serie_graphique([("2026-01-02", float("nan")), ("2026-01-03", 0), ("2026-01-05", "x")]), [])
        self.assertEqual(serie_graphique([]), [])

    def test_fichier_reecrit_seulement_si_change(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "cours" / "marches.json"
            self.assertTrue(agent.enregistrer_series({"^NDX": [["2026-11-03", 1.0]]}, chemin))
            self.assertFalse(agent.enregistrer_series({"^NDX": [["2026-11-03", 1.0]]}, chemin))
            self.assertTrue(agent.enregistrer_series({"GC=F": [["2026-11-03", 2.0]]}, chemin))
            self.assertIn("^NDX", agent.lire_json(chemin)["donnees"])  # série absente de l'exécution : conservée


if __name__ == "__main__":
    unittest.main()
