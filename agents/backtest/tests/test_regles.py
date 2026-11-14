"""Règles du trader (stops, prise de bénéfices) et statistiques de portefeuille."""
import unittest

import numpy as np
import pandas as pd

from agents.backtest import regles as R

STOPS = {"stop_pct": 15, "suiveur_declenchement_pct": 20, "suiveur_pct": 15, "confirmations": 2,
         "prise_benefices_pct": 30, "prise_benefices_part": 0.33}


class TestStops(unittest.TestCase):
    def test_sans_regles(self):
        self.assertAlmostEqual(R.simuler_position(np.array([100, 50, 120.0]), None)[0], 0.2)

    def test_stop_confirme_deux_fois(self):
        r, motif = R.simuler_position(np.array([100, 84, 90, 84, 83, 60.0]), STOPS)
        self.assertEqual(motif, "stop")
        self.assertAlmostEqual(r, -0.17)  # sorti au second relevé sous le stop (83), pas à 60

    def test_suiveur_et_prise_de_benefices(self):
        r, motif = R.simuler_position(np.array([100, 125, 131, 140, 118, 117, 50.0]), STOPS)
        self.assertEqual(motif, "stop suiveur")  # stop relevé à 140 × 0,85 = 119
        self.assertAlmostEqual(r, 0.33 * 1.31 + 0.67 * 1.17 - 1, places=6)

    def test_portefeuille(self):
        r = pd.Series([0.01] * 24, index=pd.date_range("2020-01-31", periods=24, freq="ME"))
        s = R.stats_portefeuille(r)
        self.assertAlmostEqual(s["rendement_annuel_pct"], 100 * (1.01 ** 12 - 1), places=1)
        self.assertEqual(s["perte_max_pct"], 0.0)
        self.assertEqual(R.stats_portefeuille(r.iloc[:5]), {"mois": 5})


if __name__ == "__main__":
    unittest.main()
