"""Liste unique du chef d'orchestre (agents/chef/liste.py) : révision mensuelle, stabilité, sorties confirmées, conviction
par le nombre de combinaisons, résultats du backtest. Données construites de toutes pièces (ni config/ ni data/ réels)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agents.chef import liste as LI
from agents.chef.agent import charger_config

COMBIS = ["mscore+goodwill_actif", "goodwill_actif+fcf_yield", "conversion_cash+goodwill_actif+fcf_yield"]


def entreprise(t, n=1, score=80.0):
    return {"id": f"selection-{t}", "type": "entreprises", "ticker": t, "symbole": t, "nom": f"Société {t}", "pays": "US", "secteur": "Industrials",
            "combinaisons": COMBIS[:n], "combinaisons_libelles": [], "percentiles": {"goodwill_actif": 90.0, "fcf_yield": 85.0}, "score": score}


def matiere(cle, score=80.0):
    return {"id": f"matiere-{cle}", "type": "matieres", "cle": cle, "nom": cle.capitalize(), "symbole": f"{cle[:2].upper()}=F",
            "combinaisons": ["niveau+positionnement"], "percentiles": {"niveau": 90.0, "positionnement": 80.0}, "score": score}


def pays(code, force=80.0, sortie=False, entree_ok=True):
    return {"id": f"pays-{code}", "cle": code, "nom": f"Pays {code}", "symbole": f"E{code}", "entree_ok": entree_ok, "sortie": sortie,
            "raisons_sortie": ["tendance cassée : cours sous la moyenne 200 jours"] if sortie else [], "force_relative": force,
            "valorisation_note": 55, "tendance": "tendance saine (test)", "mm200": 40.0}


def selections(ents=(), mats=(), paris=(), evaluation=None):
    ev = list(evaluation if evaluation is not None else paris)
    return {"entreprises": {"retenues": list(ents)}, "matieres": {"retenues": list(mats)},
            "paris_pays": {"candidats": [p for p in paris if p["entree_ok"] and not p["sortie"]], "evaluation": ev}}


BT = {"jour": "2026-11-14",
      "entreprises": {frozenset(["mscore", "goodwill_actif"]): {"ecart_indice_pct": 4.6, "gagnants_pct": 46.6, "verdict": "Prometteuse", "mois": 99}},
      "matieres": {}, "pays": {"ecart_indice_pct": -3.4, "gagnants_pct": 50.2, "verdict": "suivi de tendance", "mois": 100}}


class TestListe(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()
        self.cl = self.config["liste"]

    def maj(self, etat, sel, jour, detenus=None):
        return LI.mettre_a_jour(etat, sel, jour, self.config, BT, detenus)

    def test_revision_quinze_lignes_dans_l_ordre(self):
        sel = selections([entreprise(f"E{i:02d}", 1 + i % 3, 90 - i) for i in range(20)], [matiere(c) for c in ("cuivre", "or", "ble", "sucre", "mais", "soja")],
                         [pays(c, 90 - i) for i, c in enumerate(("PL", "CO", "CA", "JP"))])
        li, etat = self.maj(None, sel, "2026-11-02")
        self.assertEqual(li["nombre"], self.cl["max_lignes"])
        self.assertEqual(li["par_categorie"]["entreprises"], self.cl["min_entreprises"])
        self.assertLessEqual(li["par_categorie"]["matieres"], self.cl["max_matieres"])
        self.assertLessEqual(li["par_categorie"]["pays"], self.cl["max_pays"])
        cats = [l["categorie"] for l in li["lignes"]]
        self.assertEqual(cats, sorted(cats, key=["entreprises", "matieres", "pays"].index))
        # conviction : nombre de combinaisons, pas la note ; les entreprises retenues par 3 combinaisons d'abord
        ents = [l for l in li["lignes"] if l["categorie"] == "entreprises"]
        self.assertEqual(ents[0]["nb_combinaisons"], 3)
        self.assertEqual({l["conviction"] for l in li["lignes"] if l["nb_combinaisons"] == 3}, {"forte"})
        self.assertEqual(LI.conviction(2), "moyenne")
        self.assertEqual(LI.conviction(1), "faible")
        # chaque ligne : combinaison, résultat au backtest, date d'entrée, ce qui la ferait sortir
        for l in li["lignes"]:
            self.assertTrue(l["combinaisons_libelles"], l["id"])
            self.assertTrue(l["backtest"], l["id"])
            self.assertEqual(l["date_entree"], "2026-11-02")
            self.assertTrue(l["sortie_si"], l["id"])
        e = next(l for l in ents if "mscore+goodwill_actif" in l["combinaisons"])
        self.assertEqual(e["backtest"][0]["ecart_indice_pct"], 4.6)
        p = next(l for l in li["lignes"] if l["categorie"] == "pays")
        self.assertEqual(p["backtest"][0]["ecart_indice_pct"], -3.4)
        self.assertIn("tendance casse", p["sortie_si"])
        self.assertEqual(len([m for m in li["mouvements"] if m["sens"] == "entrée"]), 15)
        self.assertEqual(len(li["top3"]), 3)
        self.assertEqual(li["prochaine_revision"], "2026-12")

    def test_aucune_entree_en_cours_de_mois(self):
        li, etat = self.maj(None, selections([entreprise("A")]), "2026-11-02")
        li, etat = self.maj(etat, selections([entreprise("A"), entreprise("B", 3)], [matiere("cuivre")], [pays("PL")]), "2026-11-10")
        self.assertEqual([l["id"] for l in li["lignes"]], ["selection-A"])
        li, etat = self.maj(etat, selections([entreprise("A"), entreprise("B", 3)], [matiere("cuivre")], [pays("PL")]), "2026-12-01")
        self.assertEqual({l["id"] for l in li["lignes"]}, {"selection-A", "selection-B", "matiere-cuivre", "pays-PL"})
        self.assertTrue(all(m["date"].startswith("2026-12") for m in li["mouvements"]), "journal du mois seulement")

    def test_sortie_confirmee_cinq_jours_de_suite(self):
        sel = selections([entreprise("A"), entreprise("B")])
        li, etat = self.maj(None, sel, "2026-11-02")
        sans_b = selections([entreprise("A")])
        for i, j in enumerate(("2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06")):
            li, etat = self.maj(etat, sans_b, j)
            li, etat = self.maj(etat, sans_b, j)  # plusieurs exécutions le même jour : un seul jour compté
            b = next(l for l in li["lignes"] if l["id"] == "selection-B")
            self.assertEqual(b["jours_hors"], i + 1)
            self.assertIn("hors de sa combinaison", b["alerte_sortie"])
        # retour dans la combinaison : compteur remis à zéro
        li, etat = self.maj(etat, sel, "2026-11-09")
        self.assertEqual(next(l for l in li["lignes"] if l["id"] == "selection-B")["jours_hors"], 0)
        for j in ("2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"):
            li, etat = self.maj(etat, sans_b, j)
        self.assertIn("selection-B", {l["id"] for l in li["lignes"]})
        li, etat = self.maj(etat, sans_b, "2026-11-16")
        self.assertNotIn("selection-B", {l["id"] for l in li["lignes"]})
        m = li["mouvements"][0]
        self.assertEqual((m["sens"], m["id"]), ("sortie", "selection-B"))
        self.assertIn("confirmée 5 jours de suite", m["texte"])

    def test_pari_pays_sorti_des_l_exces_ou_la_cassure(self):
        li, etat = self.maj(None, selections(paris=[pays("PL"), pays("CO")]), "2026-11-02")
        self.assertEqual(li["par_categorie"]["pays"], 2)
        # une condition d'entrée manque (valorisation non disponible) sans excès ni cassure : le pari reste
        li, etat = self.maj(etat, selections(paris=[pays("PL", entree_ok=False), pays("CO")]), "2026-11-03")
        self.assertEqual(li["par_categorie"]["pays"], 2)
        li, etat = self.maj(etat, selections(paris=[pays("PL"), pays("CO", sortie=True)]), "2026-11-04")
        self.assertEqual([l["id"] for l in li["lignes"]], ["pays-PL"])
        self.assertIn("tendance cassée", li["mouvements"][0]["texte"])

    def test_revision_garde_les_lignes_retenues_et_celles_du_portefeuille(self):
        ents = [entreprise(f"E{i:02d}", 1, 90 - i) for i in range(12)]
        li, etat = self.maj(None, selections(ents[:3]), "2026-11-02", detenus={"E11"})
        self.assertEqual(li["nombre"], 3)
        li, etat = self.maj(etat, selections(ents), "2026-12-01", detenus={"E11"})
        ids = [l["id"] for l in li["lignes"]]
        self.assertEqual(len(ids), 12)
        li, etat = self.maj(etat, selections(ents + [entreprise(f"N{i}", 1, 99) for i in range(5)]), "2027-01-04", detenus={"E11"})
        ids = {l["id"] for l in li["lignes"]}
        self.assertTrue({f"selection-E{i:02d}" for i in range(12)} <= ids, "lignes encore retenues gardées malgré de meilleures nouvelles")

    def test_resultats_du_backtest_lus_dans_le_dernier_rapport(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "backtest").mkdir()
            r = {"donnees": {"jour": "2026-11-14", "sections": {
                "entreprises": {"combinaisons": {"retenues": [{"signaux": ["goodwill_actif", "fcf_yield"], "verdict": "Prometteuse",
                                                                "comparaison": {"verification": {"vs_indice_annuel_pct": 2.2, "mois": 99}},
                                                                "cible_verification": {"6": {"battent_indice_pct": 46.8}}}]}},
                "tendance": {"suivi_tendance": {"poche": {"retenue": {"definition": "12-1", "variante": "v"},
                                                          "variantes": [{"definition": "12-1", "variante": "v", "verification": {"rendement_annuel_pct": 8.3, "mois": 100}}],
                                                          "references": {"indice": {"verification": {"rendement_annuel_pct": 11.7}}}},
                                                 "filtre": {"3m": {"premier_tiers_tendance_positive": {"reussite_pct": 50.2}}}}}}}}
            (Path(d) / "backtest" / "resultats.json").write_text(json.dumps(r), encoding="utf-8")
            bt = LI.resultats_backtest(Path(d), self.cl)
        self.assertEqual(bt["entreprises"][frozenset(["fcf_yield", "goodwill_actif"])]["gagnants_pct"], 46.8)
        self.assertEqual(bt["pays"]["ecart_indice_pct"], -3.4)
        self.assertEqual(bt["pays"]["gagnants_pct"], 50.2)

    def test_sans_selections_rien_ne_change(self):
        li, etat = self.maj(None, selections([entreprise("A")]), "2026-11-02")
        li2, etat2 = self.maj(etat, None, "2026-11-03")
        self.assertEqual([l["id"] for l in li2["lignes"]], ["selection-A"])


if __name__ == "__main__":
    unittest.main()
