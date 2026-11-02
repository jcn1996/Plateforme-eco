"""
Tests de l'agent pays (sans réseau) : python -m unittest discover -s agents -t .
Ils utilisent les données de test de agents/pays/tests/donnees.
"""
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from agents.commun.sortie import lire_json
from agents.pays import notation, textes
from agents.pays.agent import main

DONNEES = Path(__file__).resolve().parent / "donnees"
JOUR = "2026-11-02"


class TestNotation(unittest.TestCase):
    def test_regles_simples(self):
        self.assertEqual(notation.note_croissance(2), 51)
        self.assertEqual(notation.note_inflation(2.0, 2.0), 90)        # inflation à la cible
        self.assertEqual(notation.note_inflation(4.0, 2.0), 60)        # 2 points d'écart
        self.assertEqual(notation.note_inflation(-1.0, 2.0), 45)       # déflation pénalisée aussi
        self.assertLessEqual(notation.note_inflation(30, 5), 10)       # inflation très élevée
        self.assertEqual(notation.note_taux_reel(1.5, "stable"), 80)   # zone saine
        self.assertLess(notation.note_taux_reel(-4, "stable"), 30)     # très négatif = risque
        self.assertEqual(notation.note_valorisation(0), 60)
        self.assertEqual(notation.note_momentum(0), 50)

    def test_pas_de_conclusion_forte_sans_deux_indicateurs(self):
        p = {"croissance_pib": 0.2, "inflation": 0.2, "momentum": 0.15}
        un_seul = {"croissance_pib": {"note": 100}, "inflation": {"note": 60}, "momentum": {"note": 60}}
        r = notation.note_globale(un_seul, p)
        self.assertTrue(r["ramenee"])
        self.assertEqual(r["note"], 64)
        deux = {"croissance_pib": {"note": 90}, "inflation": {"note": 80}, "momentum": {"note": 60}}
        self.assertFalse(notation.note_globale(deux, p)["ramenee"])
        # Une valeur « à vérifier » ne compte pas comme confirmation
        douteux = {"croissance_pib": {"note": 90}, "inflation": {"note": 80, "a_verifier": True}, "momentum": {"note": 60}}
        self.assertTrue(notation.note_globale(douteux, p)["ramenee"])

    def test_indicateur_manquant_exclu_et_confiance(self):
        p = {"a": 0.5, "b": 0.5}
        r = notation.note_globale({"a": {"note": 70, "libelle": "A"}, "b": {"note": None, "libelle": "B"}}, p)
        self.assertEqual(r["couverture"], 0.5)
        c = notation.confiance({"a": {"note": 70, "libelle": "A"}, "b": {"note": None, "libelle": "B"}}, p, r["couverture"])
        self.assertEqual(c["niveau"], "faible")


class TestTextes(unittest.TestCase):
    def test_mots_interdits(self):
        self.assertFalse(textes.ton_conforme("Une croissance exceptionnelle"))
        self.assertFalse(textes.ton_conforme("C'est INCONTOURNABLE"))
        self.assertFalse(textes.ton_conforme("l'explosion des prix"))
        self.assertTrue(textes.ton_conforme("Croissance de 2,1 % selon le FMI."))


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.sortie = self.dossier / "pays.json"
        # Point de départ : l'ancien fichier fictif (avec les flux de capitaux)
        fictif = {"meta": {"fictif": True, "genere_le": "2026-11-01T07:00:00Z"},
                  "donnees": [{"code": "FR", "note": 58, "flux": [{"vers": "US", "montant_md": 4.4}]}]}
        self.sortie.write_text(json.dumps(fictif), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dossier)

    def lancer(self, donnees=DONNEES, jour=JOUR):
        return main(["--test", "--donnees-test", str(donnees), "--sortie", str(self.sortie),
                     "--historique", str(self.dossier / "historique"), "--flux", str(self.dossier / "flux.json"), "--date", jour])

    def test_execution_complete(self):
        self.assertEqual(self.lancer(), 0)
        f = lire_json(self.sortie)
        self.assertEqual(f["meta"]["source"], "agent-pays")
        self.assertIs(f["meta"]["fictif"], False)
        self.assertEqual(len(f["donnees"]), 31)
        for p in f["donnees"]:
            self.assertIn(p["confiance"]["niveau"], ("faible", "moyen", "élevé"))
            self.assertTrue(p["contre_scenario"])
            for t in [p["verdict"], *p["contre_scenario"], *p["lecture"].values()]:
                self.assertTrue(textes.ton_conforme(t), t)
            for ind in {**p["indicateurs"], **p["detail"]}.values():
                if ind.get("valeur") is not None:
                    self.assertTrue(ind["date"] and ind["source"], ind)   # date et source exactes
            self.assertIsNone(p["detail"]["flux_etrangers"]["valeur"])   # non disponible
        self.assertTrue((self.dossier / "historique" / f"{JOUR}.json").exists())
        # Les flux fictifs ont été déplacés
        self.assertEqual(lire_json(self.dossier / "flux.json")["donnees"][0]["de"], "FR")

    def test_aucun_changement_aucune_ecriture(self):
        self.lancer()
        avant = self.sortie.read_text(encoding="utf-8")
        self.lancer()
        self.assertEqual(self.sortie.read_text(encoding="utf-8"), avant)

    def test_source_en_panne_et_tendance(self):
        self.lancer()
        # Deuxième exécution : la BIS est en panne et la croissance du FMI a changé
        modif = self.dossier / "donnees"
        shutil.copytree(DONNEES, modif)
        (modif / "bis.json").unlink()
        fmi = json.loads((modif / "fmi_NGDP_RPCH.json").read_text(encoding="utf-8"))
        fmi["FRA"]["2026"] = fmi["FRA"]["2026"] + 1.0
        (modif / "fmi_NGDP_RPCH.json").write_text(json.dumps(fmi), encoding="utf-8")
        self.assertEqual(self.lancer(modif, "2026-11-03"), 0)   # l'agent ne plante pas
        f = lire_json(self.sortie)
        fr = next(p for p in f["donnees"] if p["code"] == "FR")
        self.assertTrue(fr["indicateurs"]["taux_reel"]["ancienne"])            # dernière valeur connue conservée
        self.assertIn("raison_ancienne", fr["indicateurs"]["taux_reel"])
        self.assertIn("erreur", f["meta"]["etat_des_sources"]["bis"])
        pib = fr["indicateurs"]["croissance_pib"]
        self.assertAlmostEqual(pib["precedent"]["valeur"] + 1.0, pib["valeur"], places=2)   # tendance


if __name__ == "__main__":
    unittest.main()
