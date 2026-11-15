"""Sélections du backtest (agents/chef/selections.py) : combinaisons, univers, paris pays. Données construites de toutes
pièces (aucun accès aux vrais config/ et data/, hormis la configuration du chef d'orchestre dans agents/)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agents.chef import selections as SEL
from agents.chef.agent import charger_config


class Ctx:
    """Contexte minimal : entreprises, fiches et matières premières."""

    def __init__(self, entreprises=(), fiches=None, matieres=()):
        self.entreprises = list(entreprises)
        self._fiches = fiches or {}
        self.mp = {"matieres": list(matieres)}

    def fiche(self, t):
        return self._fiches.get(t, {})


def societe(t, secteur="Industrials", pays="US", cap=10.0, **kw):
    return {"ticker": t, "nom": f"Société {t}", "pays": pays, "secteur_gics": secteur, "secteur_nom": secteur, "capitalisation_md": cap,
            "financier": None, "holding": False, "devise": "USD", **kw}


def fiche(mscore, goodwill, fcf, conversion):
    return {"indicateurs": {"conversion_cash": {"note": conversion}},
            "analyse_financiere": {"indicateurs": {"mscore": {"note": mscore}, "goodwill_actif": {"note": goodwill}, "fcf_yield": {"note": fcf}}}}


class TestCombinaisons(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()

    def test_percentiles_comme_le_backtest(self):
        p = SEL.percentiles({"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8, "i": 9, "j": 10})
        self.assertEqual([round(p[k]) for k in "hij"], [80, 90, 100])
        self.assertEqual(round(p["g"]), 70)
        eg = SEL.percentiles({"a": 1, "b": 1})
        self.assertEqual(eg, {"a": 75.0, "b": 75.0})  # rangs moyens pour les égalités

    def test_retenue_seulement_au_dela_du_seuil_sur_chaque_signal(self):
        notes = {k: {"x": i, "y": i} for i, k in enumerate("abcdefghij", 1)}
        notes["j"]["y"] = 1  # premier sur x, dernier sur y
        retenus, _ = SEL.retenir(notes, [{"cle": "x+y", "signaux": ["x", "y"]}], 70)
        self.assertEqual(set(retenus), {"h", "i"}, "strictement au-delà du 70e percentile (meilleurs 30 %) sur les deux")

    def test_entreprises_univers_du_backtest(self):
        ents = [societe(f"T{i:02d}", cap=10) for i in range(12)]
        ents += [societe("FIN", secteur="Financials"), societe("IMMO", secteur="Real Estate"), societe("PETITE", cap=1.5),
                 societe("HORSUS", pays="FR"), societe("HOLD", holding=True)]
        fiches = {e["ticker"]: fiche(50 + i * 4, 50 + i * 4, 50 + i * 4, 50 + i * 4) for i, e in enumerate(ents)}
        r = SEL.entreprises(Ctx(ents, fiches), self.config)
        self.assertEqual(r["univers"], 12, "financières, immobilier, holdings, hors États-Unis et < 2 Md$ exclus")
        tickers = [x["ticker"] for x in r["retenues"]]
        self.assertEqual(set(tickers), {"T08", "T09", "T10", "T11"}, "percentile > 70 sur chaque signal (rang 9 sur 12 : 75e)")
        x = r["retenues"][0]
        self.assertEqual(x["ticker"], "T11")
        self.assertEqual(len(x["combinaisons"]), 3)
        self.assertEqual(x["id"], "selection-T11")
        self.assertEqual(x["secteur"], "Industrials")
        self.assertEqual({c["retenues"] for c in r["combinaisons"]}, {4})

    def test_matieres_contrats_a_terme(self):
        mats = [{"cle": f"m{i}", "nom": f"M{i}", "symbole": f"M{i}=F", "sous_notes": {"niveau": {"note": 40 + i * 5}, "positionnement": {"note": 40 + i * 5}}}
                for i in range(9)]
        mats.append({"cle": "or", "nom": "Or", "symbole": "GC=F", "sous_notes": {"niveau": {"note": 99}, "positionnement": {"note": 99}}})
        mats.append({"cle": "uranium", "nom": "Uranium", "symbole": "URA", "sous_notes": {"niveau": {"note": 99}, "positionnement": {"note": 99}}})
        r = SEL.matieres(Ctx(matieres=mats), self.config)
        self.assertEqual(r["univers"], 10, "l'uranium (ETF, pas un contrat à terme) hors univers, comme dans le backtest")
        ids = [x["id"] for x in r["retenues"]]
        self.assertEqual(ids[0], "or")
        self.assertEqual(set(ids), {"or", "matiere-m8", "matiere-m7"})


class TestParisPays(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()

    def pays(self, cle, positive=True, accel=1.0, valo=55, perf=15.0, mesure=True):
        st = {"perf_12_1": perf if mesure else None, "positive": positive, "au_dessus_mm200": positive, "acceleration": accel, "perf_1m": 3.0,
              "force_relative": 70.0, "texte": "test"} if mesure else {}
        fam = {"valorisation": {"note": valo, "note_absolue": valo}} if valo is not None else {}
        return {"id": f"pays-{cle}", "cle": cle, "nom": cle, "symbole": f"ETF{cle}", "suivi_tendance": st, "familles": fam}

    def test_entree_et_sortie(self):
        e = SEL.evaluer_pays(self.pays("A"), self.config)
        self.assertTrue(e["entree_ok"])
        self.assertFalse(e["sortie"])
        e = SEL.evaluer_pays(self.pays("B", valo=25), self.config)
        self.assertFalse(e["entree_ok"])
        self.assertTrue(e["sortie"])
        self.assertIn("valorisation tendue", e["raisons_sortie"][0])
        e = SEL.evaluer_pays(self.pays("C", accel=2.5), self.config)
        self.assertTrue(e["sortie"], "accélération parabolique ≥ 2,5")
        e = SEL.evaluer_pays(self.pays("D", accel=2.49), self.config)
        self.assertFalse(e["sortie"])
        e = SEL.evaluer_pays(self.pays("E", positive=False, perf=-3.0), self.config)
        self.assertTrue(e["sortie"])
        self.assertTrue(e["raisons_sortie"][0].startswith("tendance cassée"))
        e = SEL.evaluer_pays(self.pays("F", valo=None), self.config)
        self.assertFalse(e["entree_ok"], "valorisation non vérifiable : pas d'entrée")
        self.assertFalse(e["sortie"], "mais pas de sortie imposée")

    def test_detenus_a_revendre(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            (data / "portefeuille.json").write_text(json.dumps({"donnees": {"positions": [
                {"symbole": "ETFB", "poche": "pays"}, {"symbole": "ETFA", "poche": "pays"}, {"symbole": "XYZ", "poche": "entreprises"},
                {"symbole": "ETFG", "poche": "coeur", "type": "pays"}]}}), encoding="utf-8")
            detenus = SEL.symboles_detenus(data)
        self.assertEqual(detenus, {"ETFA", "ETFB"}, "un ETF pays de l'ancienne méthode n'est pas un pari pays")
        r = SEL.paris_pays([self.pays("A"), self.pays("B", valo=20), self.pays("G")], self.config, detenus)
        self.assertEqual([x["cle"] for x in r["a_revendre"]], ["B"])
        self.assertEqual({x["cle"] for x in r["candidats"]}, {"A", "G"})
        self.assertTrue(next(x for x in r["candidats"] if x["cle"] == "A")["detenu"])


if __name__ == "__main__":
    unittest.main()
