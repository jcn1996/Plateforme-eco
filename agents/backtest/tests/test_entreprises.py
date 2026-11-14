"""Comptes SEC « tels qu'ils étaient connus » : aucune donnée utilisée avant sa date de dépôt."""
import unittest

import pandas as pd

from agents.backtest.donnees import compacter_faits_sec
from agents.backtest.entreprises import Comptes, facteur_divisions


def faits():
    # FY2019 déposé le 2020-02-20, puis retraité dans le 10-K de 2021 (déposé le 2021-02-18)
    return {"faits": {
        "ca": [[0, "2019-12-31", "2020-02-20", 100.0], [0, "2019-12-31", "2021-02-18", 90.0], [0, "2020-12-31", "2021-02-18", 120.0],
               [1, "2018-12-31", "2019-02-21", 80.0]],
        "resultat_net": [[0, "2019-12-31", "2020-02-20", 10.0], [0, "2020-12-31", "2021-02-18", 12.0]],
        "cfo": [[0, "2019-12-31", "2020-02-20", 11.0], [0, "2020-12-31", "2021-02-18", 15.0]], "capex": [[0, "2020-12-31", "2021-02-18", -5.0]],
        "ebit": [[0, "2020-12-31", "2021-02-18", 20.0]], "amortissements": [[0, "2020-12-31", "2021-02-18", 4.0]],
        "capitaux_propres": [[0, "2020-12-31", "2021-02-18", 50.0]], "dette_lt": [[0, "2020-12-31", "2021-02-18", 30.0]],
        "tresorerie": [[0, "2020-12-31", "2021-02-18", 10.0]],
    }, "actions_circulation": [["2020-02-20", 1000.0], ["2021-02-18", 1100.0]]}


class TestComptes(unittest.TestCase):
    def test_pas_de_donnee_future(self):
        c = Comptes(faits())
        self.assertEqual(c.exercices("2020-02-19"), [])  # rien de 2019 avant son dépôt (2018 n'a qu'un poste)
        an = c.exercices("2020-06-30")
        self.assertEqual([e["fin"] for e in an], ["2019-12-31"])
        self.assertEqual(an[0]["ca"], 100.0)  # valeur d'origine : le retraitement n'est pas encore déposé

    def test_retraitement_visible_apres_depot(self):
        an = Comptes(faits()).exercices("2021-03-31")
        self.assertEqual([e["fin"] for e in an], ["2020-12-31", "2019-12-31"])
        self.assertEqual(an[1]["ca"], 90.0)
        e = an[0]
        self.assertEqual(e["fcf"], 10.0)  # capex en valeur absolue
        self.assertEqual(e["ebitda"], 24.0)
        self.assertEqual(e["dette_totale"], 30.0)
        self.assertEqual(e["capital_investi"], 70.0)

    def test_actions_en_circulation(self):
        c = Comptes(faits())
        self.assertEqual(c.actions_au("2020-01-01"), (None, None))
        self.assertEqual(c.actions_au("2020-12-31"), ("2020-02-20", 1000.0))

    def test_facteur_divisions(self):
        d = pd.Series([0, 2.0, 0, 3.0, 0], index=pd.date_range("2020-01-01", periods=5))
        self.assertEqual(facteur_divisions(d).tolist(), [6.0, 3.0, 3.0, 1.0, 1.0])

    def test_compacter(self):
        brut = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                {"start": "2019-01-01", "end": "2019-12-31", "val": 5, "form": "10-K", "filed": "2020-02-01"},
                {"start": "2019-10-01", "end": "2019-12-31", "val": 1, "form": "10-K", "filed": "2020-02-01"},  # trimestre : ignoré
                {"start": "2019-01-01", "end": "2019-12-31", "val": 5, "form": "10-Q", "filed": "2020-05-01"}]}},  # pas un 10-K
            "Assets": {"units": {"USD": [{"end": "2019-12-31", "val": 9, "form": "10-K", "filed": "2020-02-01"}]}}},
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2020-01-15", "val": 7, "form": "10-K", "filed": "2020-02-01"}]}}}}}
        c = compacter_faits_sec(brut)
        self.assertEqual(c["faits"]["ca"], [[0, "2019-12-31", "2020-02-01", 5.0]])
        self.assertEqual(c["faits"]["actifs"], [[0, "2019-12-31", "2020-02-01", 9.0]])
        self.assertEqual(c["actions_circulation"], [["2020-02-01", 7.0]])


if __name__ == "__main__":
    unittest.main()
