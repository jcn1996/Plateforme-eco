"""Fiches d'investissement lisibles (agents/chef/fiches.py) : 5 blocs construits par règles, sans donnée inventée.
Données construites de toutes pièces (ni config/ ni data/ réels)."""
from __future__ import annotations

import unittest

from agents.chef import fiches as FI
from agents.chef.agent import charger_config

LIGNE_E = {"id": "selection-PTON", "categorie": "entreprises", "nom": "Peloton", "symbole": "PTON", "ticker": "PTON", "conviction": "forte",
           "combinaisons": ["mscore+goodwill_actif", "goodwill_actif+fcf_yield"], "date_entree": "2026-11-16",
           "backtest": [{"combinaison": "Goodwill / actif + Rendement du FCF", "ecart_indice_pct": 2.2, "gagnants_pct": 46.8, "verdict": "Prometteuse", "mois": 99}]}
FICHE = {"note": 52, "momentum": {"m3": -2.3, "m6": -0.8, "m12": -27.3},
         "indicateurs": {"conversion_cash": {"valeur": 597.6}, "dette_ebitda": {"valeur": 2.06}, "couverture_interets": {"valeur": 1.72},
                         "fscore": {"valeur": 7}},
         "analyse_financiere": {"indicateurs": {"fcf_yield": {"valeur": 16.92}, "altman_z": {"valeur": -1.07}, "mscore": {"valeur": -3.29},
                                                "goodwill_actif": {"valeur": 2.14}, "evolution_actions": {"valeur": 22.95}}},
         "valorisation": {"per": 15.35, "per_secteur": -11.9},
         "alertes": [{"cle": "dilution", "titre": "Dilution forte", "texte": "nombre d'actions en hausse de 7,9 % sur un an"}],
         "recommandation": {"si_non_detenu": "Éviter"}, "contre_scenario": ["Le cours recule sur 12 mois."]}


class TestFiches(unittest.TestCase):
    def setUp(self):
        self.ct = charger_config()["suivi_tendance"]

    def verifier_forme(self, f):
        self.assertLessEqual(len(f["entete"]["verdict"].split()), FI.MOTS_VERDICT)
        self.assertTrue(1 <= len(f["pour"]) <= 3)
        self.assertTrue(1 <= len(f["contre"]) <= 3)
        self.assertIn(f["momentum"]["mot"], ("favorable", "neutre", "défavorable", "inconnu"))
        self.assertTrue(f["sortie"])
        for k in ("verdict", "pour", "contre", "momentum"):
            self.assertTrue(f["courte"][k])

    def test_entreprise(self):
        f = FI.fiche_entreprise(LIGNE_E, FICHE, 6.7, self.ct)
        self.verifier_forme(f)
        self.assertEqual(f["entete"]["poids_texte"], "6,7 % du portefeuille démo")
        self.assertEqual(f["pour"][0], "Le cash-flow disponible représente 16,9 % de la valeur en Bourse par an.")  # critère de la combinaison d'abord
        self.assertTrue(all("percentile" not in p for p in f["pour"]), "jamais un percentile seul")
        self.assertIn("Z-score d'Altman de −1,07", f["contre"][0])
        self.assertTrue(any("Dilution" in c for c in f["contre"]))
        self.assertEqual(f["momentum"]["mot"], "défavorable")
        self.assertIn("contredit le dossier", f["momentum"]["contradiction"])
        self.assertIn("contredit le dossier", f["courte"]["momentum"])
        self.assertIn("bilan fragile", f["entete"]["verdict"])
        self.assertEqual(f["base_statistique"]["combinaisons"][0]["ecart_indice_pct"], 2.2)

    def test_donnees_manquantes_signalees(self):
        f = FI.fiche_entreprise(LIGNE_E, None, None, self.ct)
        self.verifier_forme(f)
        self.assertEqual(f["entete"]["poids_texte"], "non détenue par le portefeuille démo")
        self.assertIn("fiche de l'agent entreprises absente", f["pour"][0])
        self.assertEqual(f["momentum"]["mot"], "inconnu")
        self.assertIn("donnée manquante", f["momentum"]["texte"])

    def test_matiere(self):
        l = {"id": "matiere-palladium", "categorie": "matieres", "nom": "Palladium", "symbole": "PA=F", "cle": "palladium", "conviction": "faible", "backtest": []}
        m = {"cours": 950.0, "unite": "$/once", "variation_12m": -32.8, "serie": [["2026-05-18", 1420.0], ["2026-11-17", 950.0]],
             "sous_notes": {"niveau": {"note": 79, "percentile": 1.3, "corrige_inflation": True, "annees": 10, "plus_bas": 655.35, "plus_haut": 2979.9},
                            "positionnement": {"note": 75, "net": -15714.0, "percentile": 3.2, "part_oi_pct": -52.86},
                            "tendance": {"note": 14, "texte": "Cours −26,4 % sur 3 mois", "variation_3m": -26.4, "variation_12m": -32.8},
                            "courbe": {"note": 34, "structure": "contango", "roulement_pct_an": -6.55}}}
        f = FI.fiche_matiere(l, m, 8.1)
        self.verifier_forme(f)
        self.assertIn("plus bas que 99 % des cours des 10 dernières années", f["pour"][0])
        self.assertIn("nets vendeurs de 15 714 contrats", f["pour"][1])
        self.assertIn("contango", " ".join(f["contre"]))
        self.assertEqual(f["momentum"]["m6"], -33.1)
        self.assertIn("parie sur un rebond", f["momentum"]["contradiction"])

    def test_pays(self):
        l = {"id": "pays-CO", "categorie": "pays", "nom": "Colombie", "symbole": "COLO", "cle": "CO", "conviction": "faible",
             "backtest": [{"combinaison": "Tendance saine + valorisation non tendue", "ecart_indice_pct": -3.36, "gagnants_pct": 50.2}]}
        o = {"suivi_tendance": {"perf_12_1": 40.71, "perf_1m": -9.12, "mm200": 43.44, "rang": 3, "sur": 30,
                                "invalidation": {"mm200": 43.44, "ecart_mm200_pct": 3.5}}}
        p = {"indicateurs": {"valorisation": {"per": 9.6, "mediane": 14.4, "symbole": "COLO"}}, "contre_scenario": []}
        serie = [["2025-11-17", 35.0], ["2026-05-18", 36.0], ["2026-08-17", 48.0], ["2026-11-17", 44.96]]
        f = FI.fiche_pays(l, o, p, serie, 4.4, self.ct, l["backtest"])
        self.verifier_forme(f)
        self.assertIn("PER de l'ETF COLO de 9,6 contre 14,4", f["pour"][1])
        self.assertIn("43,44", f["sortie"])
        self.assertTrue(any("3,4 points par an de moins que l'indice mondial" in c for c in f["contre"]))
        self.assertEqual(f["momentum"]["mot"], "neutre")  # +28 % sur 12 mois mais −6 % sur 3 mois

    def test_verdict_vingt_mots_sans_troncature(self):
        v = FI.phrase_verdict(["atout numéro un très long", "atout numéro deux très long"],
                              ["réserve numéro un très longue", "réserve numéro deux très longue"], False, None, "défaut")
        self.assertLessEqual(len(v.split()), 20)
        self.assertNotIn("…", v)

    def test_momentum(self):
        self.assertEqual(FI.mot_momentum(5, 8, 20), "favorable")
        self.assertEqual(FI.mot_momentum(-2, -1, -27), "défavorable")
        self.assertEqual(FI.mot_momentum(-8, 23, 28), "neutre")
        self.assertEqual(FI.mot_momentum(None, None, None), "inconnu")
        self.assertIsNone(FI.perf_serie([["2026-11-01", 10]], 3))


if __name__ == "__main__":
    unittest.main()
