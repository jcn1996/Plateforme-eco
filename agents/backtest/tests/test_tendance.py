"""Lot « tendance » du backtest : mesures, force relative, excès et poche simulée (données construites, sans réseau)."""
import unittest

import numpy as np
import pandas as pd

from agents.backtest import tendance as T


def cours(rendements: dict[str, float], jours: int = 900, graine: int = 3) -> pd.DataFrame:
    r = np.random.default_rng(graine)
    idx = pd.bdate_range("2020-01-01", periods=jours)
    return pd.DataFrame({s: 100 * np.exp(np.cumsum(mu + r.normal(0, 0.005, jours))) for s, mu in rendements.items()}, index=idx)


class TestTendance(unittest.TestCase):
    def setUp(self):
        self.q = cours({"A": 0.002, "B": 0.001, "C": 0.0, "D": -0.001, "E": -0.002, "F": 0.0005})
        self.cat = {"x": list(self.q.columns)}
        self.me = T.mesures(self.q)

    def test_mesures_et_rang(self):
        t = self.me["prix"].index[-1]
        p = self.me["perf"]["12-1"].loc[t]
        self.assertGreater(p["A"], p["C"])
        self.assertGreater(p["C"], p["E"])
        self.assertTrue(self.me["au_dessus"].loc[t, "A"])
        self.assertFalse(self.me["au_dessus"].loc[t, "E"])
        rs = T.rang_categorie(self.me["perf"]["12-1"], self.cat).loc[t]
        self.assertEqual(rs.idxmax(), "A")
        self.assertEqual(rs.idxmin(), "E")
        rel = T.relatif_categorie(T.S.rendements_futurs(self.me["prix"], 1), self.cat)
        self.assertAlmostEqual(float(rel.iloc[-3].sum()), 0.0, places=9)

    def test_percentile_historique(self):
        s = pd.DataFrame({"x": list(range(1, 21))})
        p = T.percentile_historique(s, 10, 5)["x"]
        self.assertAlmostEqual(p.iloc[-1], 100.0)  # au-dessus des 9 valeurs précédentes de la fenêtre
        self.assertTrue(np.isnan(p.iloc[3]))  # moins de 5 observations

    def test_poche_et_stop(self):
        sans = T.simuler_poche(self.q, self.me, self.cat, "12-1", {"lignes": 2}, 0.1)
        self.assertGreater(len(sans["mensuel"]), 12)
        self.assertTrue(sans["operations"] > 0)
        # Chute brutale de A : le stop −10 % la fait sortir, sans stop elle reste jusqu'à la fin du mois
        q = self.q.copy()
        q.loc[q.index[700]:, "A"] *= 0.7
        me = T.mesures(q)
        avec = T.simuler_poche(q, me, self.cat, "12-1", {"lignes": 2, "stop_pct": 10, "confirmations": 1}, 0.1)
        self.assertGreaterEqual(avec["motifs"].get("stop", 0), 1)

    def test_choix_de_la_variante(self):
        def v(defn, nom, regle, a, b):
            return {"definition": defn, "variante": nom, "regle": regle, "apprentissage": {"sharpe": a}, "verification": {"sharpe": b}}
        res = [v("12-1", "base", {}, 0.1, 0.4), v("12-1", "sur-ajustée", {"x": 1}, 0.9, 0.1), v("12-1", "robuste", {"y": 1}, 0.3, 0.45)]
        self.assertEqual(T.choisir(res)["variante"], "robuste")


if __name__ == "__main__":
    unittest.main()
