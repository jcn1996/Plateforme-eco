"""Statistiques du backtest : IC, paniers, frais, verdicts (données synthétiques)."""
import unittest

import numpy as np
import pandas as pd

from agents.backtest import stats as S

CFG = {"mois_min": 48, "mois_min_verification": 24, "actifs_min": 8, "ic_garder": 0.03, "t_garder": 1.5, "ic_supprimer": 0.01}


def panneau(n_mois=180, n_actifs=20, graine=1, pouvoir=0.0):
    """Prix mensuels et signal ; `pouvoir` : part du rendement du mois suivant expliquée par le signal."""
    r = np.random.default_rng(graine)
    idx = pd.date_range("2008-01-31", periods=n_mois, freq="ME")
    sig = pd.DataFrame(r.normal(size=(n_mois, n_actifs)), index=idx, columns=[f"A{i}" for i in range(n_actifs)])
    rend = r.normal(0.005, 0.05, size=(n_mois, n_actifs)) + pouvoir * 0.05 * sig.to_numpy()
    # le signal de t prédit le rendement de t à t+1 : le prix de t+1 en dépend
    prix = pd.DataFrame(100 * np.exp(np.cumsum(np.vstack([np.zeros(n_actifs), rend[:-1]]), axis=0)), index=idx, columns=sig.columns)
    return sig, prix


class TestOutils(unittest.TestCase):
    def test_ic_parfait_et_inverse(self):
        idx = pd.date_range("2020-01-31", periods=3, freq="ME")
        s = pd.DataFrame([[1, 2, 3, 4, 5, 6, 7, 8]] * 3, index=idx, dtype=float)
        self.assertTrue(np.allclose(S.ic_series(s, s * 2, 8), 1))
        self.assertTrue(np.allclose(S.ic_series(s, -s, 8), -1))
        self.assertTrue(S.ic_series(s, s, 9).isna().all())  # pas assez d'actifs

    def test_paniers_et_rotation(self):
        s = pd.DataFrame([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]], dtype=float,
                         index=pd.date_range("2020-01-31", periods=2, freq="ME"))
        haut, bas = S.paniers(s, 0.2)
        self.assertEqual(haut.sum(axis=1).tolist(), [2, 2])
        self.assertEqual(list(haut.columns[haut.iloc[0]]), [8, 9])
        self.assertEqual(S.rotation(haut).tolist(), [1.0, 1.0])  # panier entièrement renouvelé

    def test_newey_west(self):
        x = pd.Series([0.1, 0.12, 0.08, 0.11, 0.09, 0.1, 0.13, 0.07])
        self.assertGreater(S.newey_west_t(x, 1), 5)
        self.assertIsNone(S.newey_west_t(pd.Series([1.0, 2.0]), 1))

    def test_fin_de_mois(self):
        s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2020-01-02", "2020-01-30", "2020-02-03"]))
        m = S.fin_de_mois(s)
        self.assertEqual(m.tolist(), [2.0, 3.0])
        self.assertEqual(m.index[0], pd.Timestamp("2020-01-31"))


class TestVerdicts(unittest.TestCase):
    def analyser(self, sig, prix, sep=None):
        return S.analyser_signal(sig, prix, None, [1, 3], 1, 0.2, 0.2, None, sep, CFG)

    def test_signal_predictif_garde(self):
        sig, prix = panneau(pouvoir=0.4)
        r = self.analyser(sig, prix)
        self.assertEqual(r["verdict"], "Garder", r["raison"])
        self.assertGreater(r["horizons"]["1"]["ic_moyen"], 0.1)
        self.assertGreater(r["horizons"]["1"]["ecart_pct"], 0)

    def test_signal_inverse_supprime(self):
        sig, prix = panneau(pouvoir=0.4, graine=3)
        r = self.analyser(-sig, prix)
        self.assertEqual(r["verdict"], "Supprimer")
        self.assertIn("sens contraire", r["raison"])

    def test_bruit_jamais_garde(self):
        for g in range(4):
            sig, prix = panneau(pouvoir=0.0, graine=10 + g)
            self.assertNotEqual(self.analyser(sig, prix)["verdict"], "Garder")

    def test_petit_echantillon(self):
        sig, prix = panneau(n_mois=40, pouvoir=0.5)
        r = self.analyser(sig, prix)
        self.assertEqual(r["verdict"], "Données insuffisantes")

    def test_frais_reduisent_l_ecart(self):
        sig, prix = panneau(pouvoir=0.3)
        r0 = S.analyser_signal(sig, prix, None, [1], 1, 0.2, 0.0, None, None, CFG)
        r1 = S.analyser_signal(sig, prix, None, [1], 1, 0.2, 1.0, None, None, CFG)
        self.assertGreater(r0["frais"]["ecart_net_annuel_pct"], r1["frais"]["ecart_net_annuel_pct"])
        self.assertEqual(r0["frais"]["ecart_net_annuel_pct"], r0["frais"]["ecart_brut_annuel_pct"])

    def test_separation_et_regimes(self):
        sig, prix = panneau(pouvoir=0.3)
        reg = pd.Series(["calme", "tension"] * 90, index=prix.index)
        r = S.analyser_signal(sig, prix, None, [1], 1, 0.2, 0.2, reg, pd.Timestamp("2014-12-31"), CFG)
        e = r["echantillons"]
        self.assertEqual(e["apprentissage"]["mois"] + e["verification"]["mois"], e["total"]["mois"])
        self.assertTrue(all(d <= "2014-12" for d in [e["apprentissage"]["debut"]]))
        self.assertEqual(r["regimes"]["calme"]["mois"] + r["regimes"]["tension"]["mois"], e["total"]["mois"])

    def test_note_ponderee(self):
        idx = pd.date_range("2020-01-31", periods=1, freq="ME")
        a = pd.DataFrame([[80.0, np.nan]], index=idx, columns=["X", "Y"])
        b = pd.DataFrame([[40.0, 60.0]], index=idx, columns=["X", "Y"])
        n = S.note_ponderee({"a": a, "b": b}, {"a": 3, "b": 1})
        self.assertAlmostEqual(n.at[idx[0], "X"], 70.0)
        self.assertAlmostEqual(n.at[idx[0], "Y"], 60.0)  # poids renormalisés sur les notes présentes


if __name__ == "__main__":
    unittest.main()
