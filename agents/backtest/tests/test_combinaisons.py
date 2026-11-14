"""Référence « momentum seul », combinaisons de signaux, variations et mesures « cible » (données synthétiques)."""
import unittest

import numpy as np
import pandas as pd

from agents.backtest import combinaisons as CB
from agents.backtest import reference as RF
from agents.backtest import stats as S
from agents.backtest.entreprises import variations_comptes
from agents.backtest.matieres import variations as variations_matieres
from agents.backtest.pays import variations as variations_pays

CFG = {"signaux_max": 6, "seuil_percentile": 70, "retenues_max": 5, "alpha": 0.05, "mois_min_apprentissage": 36, "mois_actifs_min_pct": 50}


def prix_aleatoires(n_mois=180, n_actifs=25, graine=0):
    r = np.random.default_rng(graine)
    idx = pd.date_range("2008-01-31", periods=n_mois, freq="ME")
    rend = r.normal(0.005, 0.05, size=(n_mois, n_actifs))
    return pd.DataFrame(100 * np.exp(np.cumsum(rend, axis=0)), index=idx, columns=[f"A{i}" for i in range(n_actifs)])


def resultat(ic_app, verdict="Alléger"):
    return {"verdict": verdict, "echantillons": {"apprentissage": {"ic_moyen": ic_app}}}


class TestReference(unittest.TestCase):
    def test_momentum_hors_dernier_mois(self):
        idx = pd.date_range("2020-01-31", periods=14, freq="ME")
        p = pd.DataFrame({"X": [100.0] * 12 + [200.0, 50.0]}, index=idx)
        m = RF.momentum_12_1(p)
        self.assertAlmostEqual(m["X"].iloc[12], 0.0)   # le saut du dernier mois n'est pas compté
        self.assertAlmostEqual(m["X"].iloc[13], 1.0)   # il l'est le mois suivant (t − 1)

    def test_panier_vide_reste_dans_l_indice(self):
        p = prix_aleatoires(n_mois=30)
        b = RF.indice_mensuel(p, None)
        r = RF.rendement_masque(pd.DataFrame(False, index=p.index, columns=p.columns), p, b, 0.3)
        pd.testing.assert_series_equal(r.dropna(), b.loc[r.dropna().index], check_names=False)

    def test_frais_et_comparaison(self):
        p = prix_aleatoires()
        b = RF.indice_mensuel(p, None)
        sig = RF.momentum_12_1(p)
        r0, r1 = RF.rendement_signal(sig, p, b, 0.2, 0.0), RF.rendement_signal(sig, p, b, 0.2, 1.0)
        self.assertGreater(r0.sum(), r1.sum())
        c = RF.comparer(r0, b, r1, p.index[90])
        self.assertIn("vs_momentum_annuel_pct", c["verification"])
        self.assertGreater(c["total"]["vs_momentum_annuel_pct"], 0)  # sans frais, mieux que la même règle avec frais

    def test_loi_normale(self):
        self.assertAlmostEqual(RF.t_critique(0.05), 1.645, places=2)
        self.assertAlmostEqual(RF.p_unilaterale(1.96), 0.025, places=3)
        self.assertGreater(RF.t_critique(0.05 / 50), RF.t_critique(0.05))  # plus d'essais, seuil plus haut


class TestCombinaisons(unittest.TestCase):
    def test_masque_tous_les_signaux(self):
        idx = pd.date_range("2020-01-31", periods=1, freq="ME")
        a = pd.DataFrame([list(range(10))], index=idx, columns=list("ABCDEFGHIJ"), dtype=float)
        b = pd.DataFrame([list(range(10))[::-1]], index=idx, columns=list("ABCDEFGHIJ"), dtype=float)
        self.assertEqual(list(a.columns[CB.masque_combine([a], 70).iloc[0]]), ["H", "I", "J"])
        self.assertFalse(CB.masque_combine([a, b], 70).any().any())  # aucun actif en tête des deux classements

    def test_candidats_et_redondance(self):
        res = {"momentum": resultat(0.05), "valorisation": resultat(0.02, "Garder"), "taux_reel": resultat(-0.01),
               "inflation": resultat(0.08, "Supprimer"), "note_globale": resultat(0.2, "Garder"), "var3_x": resultat(0.03)}
        self.assertEqual(CB.candidats(res, 10), ["momentum", "var3_x", "valorisation"])
        self.assertEqual(CB.candidats(res, 2), ["momentum", "var3_x"])
        self.assertTrue(CB.redondante(("var3_inflation", "var6_inflation")))
        self.assertFalse(CB.redondante(("inflation", "var3_inflation", "momentum")))

    def test_bruit_pur_jamais_confirme(self):
        """Des signaux sans aucun pouvoir prédictif ne doivent produire aucune combinaison « Confirmée »."""
        for graine in range(3):
            p = prix_aleatoires(graine=graine)
            r = np.random.default_rng(100 + graine)
            sig = {f"s{i}": pd.DataFrame(r.normal(size=p.shape), index=p.index, columns=p.columns) for i in range(6)}
            res = {k: resultat(0.04) for k in sig}
            out = CB.tester(sig, res, p, None, None, 0.3, p.index[90], CFG, {})
            self.assertEqual(out["essais"], 15 + 20)
            self.assertGreater(out["seuil_t_bonferroni"], 2.9)
            self.assertFalse([x for x in out["retenues"] if x["verdict"] == "Confirmée"])
            for x in out["retenues"]:
                self.assertGreaterEqual(x["p_holm"], x["p_verification"] or 0)

    def test_signal_fort_confirme(self):
        p = prix_aleatoires(n_actifs=30, graine=5)
        fut = S.rendements_futurs(p, 1)
        r = np.random.default_rng(1)
        bon = fut + pd.DataFrame(r.normal(0, 0.03, size=p.shape), index=p.index, columns=p.columns)  # « connaît » le mois suivant
        sig = {"a": bon, "b": bon + pd.DataFrame(r.normal(0, 0.03, size=p.shape), index=p.index, columns=p.columns)}
        out = CB.tester(sig, {"a": resultat(0.3), "b": resultat(0.2)}, p, None, None, 0.0, p.index[90], CFG, {"a": "A", "b": "B"})
        self.assertEqual(out["retenues"][0]["libelle"], "A + B")
        self.assertEqual(out["retenues"][0]["verdict"], "Confirmée")


class TestVariationsEtCible(unittest.TestCase):
    def test_cible(self):
        c = S.cible(pd.Series([0.10, 0.05, -0.05, np.nan]))
        self.assertEqual(c["cas"], 3)
        self.assertAlmostEqual(c["battent_indice_pct"], 66.7)
        self.assertAlmostEqual(c["gain_perte"], 1.5)
        self.assertIsNone(S.cible(pd.Series([0.1]))["gain_perte"])  # aucun perdant : rapport non défini

    def test_variations_pays(self):
        idx = pd.date_range("2020-01-31", periods=7, freq="ME")
        note = pd.DataFrame({"FR": [50, 52, 54, 56, 58, 60, 62.0]}, index=idx)
        v = variations_pays({"notes": {"inflation": note}})
        self.assertEqual(set(v), {"var3_inflation", "var6_inflation"})
        self.assertEqual(v["var3_inflation"]["FR"].iloc[-1], 6.0)
        self.assertEqual(v["var6_inflation"]["FR"].iloc[-1], 12.0)
        self.assertTrue(np.isnan(v["var6_inflation"]["FR"].iloc[5]))  # pas de valeur avant 6 mois d'historique

    def test_variations_comptes(self):
        an = [{"ca": 120.0, "ebit": 24.0, "marge_brute": 60.0, "rd": 12.0}, {"ca": 100.0, "ebit": 15.0, "marge_brute": 45.0, "rd": 8.0},
              {"ca": 90.0}]
        v = variations_comptes(an)
        self.assertAlmostEqual(v["var_marge_op"], 5.0)
        self.assertAlmostEqual(v["var_marge_brute"], 5.0)
        self.assertAlmostEqual(v["var_intensite_rd"], 2.0)
        self.assertAlmostEqual(v["var_croissance_ca"], (1.2 - 100 / 90) * 100)
        self.assertEqual(variations_comptes(an[:1]), {})

    def test_variations_matieres_sens(self):
        idx = pd.date_range("2020-01-31", periods=4, freq="ME")
        brut = {"stocks_ecart": pd.DataFrame({"wti": [10.0, 8, 6, 4]}, index=idx),
                "part_oi": pd.DataFrame({"wti": [5.0, 6, 7, 9]}, index=idx)}
        v = variations_matieres(brut)
        self.assertEqual(v["var3_stocks"]["wti"].iloc[-1], 6.0)          # déstockage : favorable (+)
        self.assertEqual(v["var3_positionnement"]["wti"].iloc[-1], 4.0)  # achats des gérants : +
        self.assertNotIn("var6_stocks", v)                               # pas encore 6 mois d'historique


if __name__ == "__main__":
    unittest.main()
