"""Robustesse de l'agent pays : une source ou un texte ne doit jamais faire échouer toute l'exécution.

Cas réel (14/11/2026) : le signal « Brésil : sorties inhabituelles sur l'ETF EWZ » contenait « (historique
encore court) » ; « historique » est un mot interdit des règles de conduite et la vérification levait une
exception : l'agent s'arrêtait à chaque exécution depuis le 09/11.
"""
import json
import shutil
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from agents.commun.sortie import lire_json
from agents.pays import flux_etf, textes
from agents.pays import agent as A

DONNEES = Path(__file__).resolve().parent / "donnees"
JOUR = "2026-11-02"


class TestTextes(unittest.TestCase):
    def test_textes_des_signaux_conformes(self):
        # Série courte (seuil fixe) avec une sortie très forte le dernier jour : le texte qui a bloqué l'agent
        serie = [{"date": f"2026-11-{j:02d}", "parts": 1_000_000 if j < 13 else 900_000, "vl": 30.0, "encours": 3e7, "source": "ishares"}
                 for j in (10, 11, 12, 13)]
        res = flux_etf.signaux("BR", "Brésil", "EWZ", serie, A.CONFIG_FLUX, date(2026, 11, 14))
        self.assertTrue(res, "le signal de sorties inhabituelles doit exister")
        for s in res:
            self.assertTrue(textes.ton_conforme(s["titre"] + " " + s["explication"]), s["explication"])

    def test_neutraliser(self):
        t = "Hausse Historique et spectaculaire, sans mot à retirer ailleurs."
        n = textes.neutraliser(t)
        self.assertTrue(textes.ton_conforme(n))
        self.assertEqual(n, "Hausse [mot retiré] et [mot retiré], sans mot à retirer ailleurs.")
        self.assertEqual(textes.neutraliser("Texte sans problème."), "Texte sans problème.")

    def test_signal_non_conforme_ne_bloque_plus(self):
        with tempfile.TemporaryDirectory() as d:
            args = mock.Mock(historique_flux=str(Path(d) / "flux"), signaux=str(Path(d) / "signaux.json"))
            signal = {"date": JOUR, "type": "sorties_inhabituelles", "cle": "BR", "importance": "forte",
                      "titre": "Brésil : sorties inhabituelles sur l'ETF EWZ", "source": "iShares",
                      "explication": "−50 M$ en une séance (historique encore court)."}
            A.ecrire_flux(args, {"historique": {}, "signaux": [signal]}, date.fromisoformat(JOUR), "2026-11-02T06:00:00Z")
            ecrit = lire_json(Path(d) / "signaux.json")["donnees"][0]
            self.assertTrue(textes.ton_conforme(ecrit["explication"]))
            self.assertIn("[mot retiré]", ecrit["explication"])


class TestDelais(unittest.TestCase):
    def test_source_bloquee_abandonnee(self):
        appels = {"lente": lambda: time.sleep(5) or {"x": 1}, "rapide": lambda: {"a": 1, "b": 2}}
        debut = time.monotonic()
        res, etats = A.interroger(appels, {}, delai_source_s=0.3, budget_s=60)
        self.assertLess(time.monotonic() - debut, 3)
        self.assertIsNone(res["lente"])
        self.assertIn("délai maximal dépassé", etats["lente"])
        self.assertEqual(etats["rapide"], "ok")

    def test_budget_epuise(self):
        appels = {"a": lambda: time.sleep(0.2) or {"x": 1}, "b": lambda: {"y": 1}}
        res, etats = A.interroger(appels, {}, delai_source_s=10, budget_s=5.1)
        self.assertEqual(etats["a"], "ok")
        self.assertIn("budget de temps", etats["b"])
        self.assertIsNone(res["b"])

    def test_erreur_transmise(self):
        def casse():
            raise RuntimeError("serveur indisponible")
        res, etats = A.interroger({"x": casse}, {}, delai_source_s=5, budget_s=60)
        self.assertIsNone(res["x"])
        self.assertIn("serveur indisponible", etats["x"])


class TestJournalDesTentatives(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.sortie = self.dossier / "pays.json"
        self.journal = self.dossier / "journal.json"

    def tearDown(self):
        shutil.rmtree(self.dossier)

    def lancer(self, donnees=DONNEES):
        return A.main(["--test", "--donnees-test", str(donnees), "--sortie", str(self.sortie),
                       "--historique", str(self.dossier / "historique" / "pays"), "--journal", str(self.journal),
                       "--recap", str(self.dossier / "recap"), "--date", JOUR])

    def test_succes_puis_echec(self):
        self.assertEqual(self.lancer(), 0)
        j = lire_json(self.journal)
        t = j["meta"]["sante"]["derniere_tentative"]
        self.assertIn(t["statut"], ("ok", "partiel"))   # données de test : certaines sources facultatives manquent
        derniere_reussie = j["meta"]["sante"]["derniere_execution"]
        # Échec inattendu : la date de la tentative et la raison sont enregistrées, la dernière réussite est conservée
        with mock.patch.object(A, "executer", side_effect=RuntimeError("panne simulée")):
            self.assertEqual(self.lancer(), 1)
            self.assertEqual(self.lancer(), 1)
        j = lire_json(self.journal)
        t = j["meta"]["sante"]["derniere_tentative"]
        self.assertEqual(t["statut"], "echec")
        self.assertIn("panne simulée", t["raison"])
        self.assertEqual(t["echecs_consecutifs"], 2)
        self.assertEqual(j["derniere_tentative"], t)                      # recopiée au premier niveau
        self.assertEqual(j["meta"]["sante"]["derniere_execution"], derniere_reussie)

    def test_echec_partiel(self):
        modif = self.dossier / "donnees"
        shutil.copytree(DONNEES, modif)
        (modif / "bis.json").unlink()
        self.assertEqual(self.lancer(modif), 0)
        t = lire_json(self.journal)["meta"]["sante"]["derniere_tentative"]
        self.assertEqual(t["statut"], "partiel")
        self.assertIn("bis", t["raison"])
        self.assertIn("dernières valeurs connues conservées", t["raison"])


if __name__ == "__main__":
    unittest.main()
