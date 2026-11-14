"""Recalibrage des poids et écriture ciblée dans un fichier de configuration (copie temporaire)."""
import json
import tempfile
import unittest
from pathlib import Path

from agents.backtest import recalibrage as RC

CFG = {"ic_reference": 0.05, "facteur_max": 2.0, "retrait": 0.5}


def res(ic, verdict="Alléger"):
    return {"verdict": verdict, "echantillons": {"apprentissage": {"ic_moyen": ic}}}


class TestRecalibrage(unittest.TestCase):
    def test_somme_conservee_et_sens(self):
        poids = {"a": 0.2, "b": 0.2, "c": 0.1}
        nv, _ = RC.recalibrer({"a": res(0.10), "b": res(-0.05)}, poids, CFG)
        self.assertAlmostEqual(sum(nv.values()), 0.5, places=6)
        self.assertGreater(nv["a"], nv["b"])
        self.assertGreater(nv["b"], 0)  # retrait vers le poids actuel : jamais supprimé d'un coup

    def test_non_teste_inchange_en_proportion(self):
        poids = {"a": 10, "b": 10}
        nv, detail = RC.recalibrer({"a": res(0.05), "b": res(0.0, "Données insuffisantes")}, poids, CFG, 0)
        self.assertEqual(nv, {"a": 10, "b": 10})
        self.assertIn("inchangé", detail["b"])

    def test_non_teste_garde_exactement_son_poids(self):
        poids = {"a": 20, "b": 20, "stocks": 25, "macro": 35}
        nv, _ = RC.recalibrer({"a": res(0.0), "b": res(0.10), "stocks": res(None, "Données insuffisantes")}, poids, CFG, 0)
        self.assertEqual(nv["stocks"], 25)
        self.assertEqual(nv["macro"], 35)
        self.assertEqual(nv["a"] + nv["b"], 40)
        self.assertGreater(nv["b"], nv["a"])

    def test_meilleure(self):
        a = {"verdict": "Alléger", "echantillons": {"verification": {"ic_moyen": 0.02, "ecart_net_annuel_pct": 1.0}}}
        b = {"verdict": "Garder", "echantillons": {"verification": {"ic_moyen": 0.04, "ecart_net_annuel_pct": 2.0}}}
        self.assertTrue(RC.meilleure(a, b)[0])
        self.assertFalse(RC.meilleure(b, a)[0])

    def test_remplacer_valeurs_sans_reformater(self):
        texte = '{\n  "_commentaire": "x",\n  "autre": {"ponderations": {"a": 1}},\n  "ponderations": {\n    "a": 0.2, "b": 0.3\n  },\n  "fin": [1, 2]\n}\n'
        nouveau = RC.remplacer_valeurs(texte, ["ponderations"], {"a": 0.25})
        self.assertEqual(json.loads(nouveau)["ponderations"], {"a": 0.25, "b": 0.3})
        self.assertEqual(json.loads(nouveau)["autre"], {"ponderations": {"a": 1}})
        self.assertEqual(nouveau.replace("0.25", "0.2"), texte)  # une seule valeur change
        with self.assertRaises(KeyError):
            RC.remplacer_valeurs(texte, ["ponderations"], {"zz": 1})
        imbrique = RC.remplacer_valeurs(texte, ["autre", "ponderations"], {"a": 2})
        self.assertEqual(json.loads(imbrique)["autre"]["ponderations"]["a"], 2)

    def test_appliquer_seulement_les_propositions_retenues(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "agents" / "x" / "config.json"
            f.parent.mkdir(parents=True)
            f.write_text('{"poids": {"pays": {"a": 10, "b": 20}}}', encoding="utf-8")
            prop = {"propositions": [
                {"fichier": "agents/x/config.json", "chemin": ["poids", "pays"], "actuel": {"a": 10, "b": 20}, "propose": {"a": 12, "b": 18}, "retenue": True},
                {"fichier": "agents/x/config.json", "chemin": ["poids", "pays"], "actuel": {"a": 10}, "propose": {"a": 99}, "retenue": False}]}
            self.assertEqual(RC.appliquer(prop, Path(d)), ["agents/x/config.json"])
            self.assertEqual(json.loads(f.read_text())["poids"]["pays"], {"a": 12, "b": 18})


if __name__ == "__main__":
    unittest.main()
