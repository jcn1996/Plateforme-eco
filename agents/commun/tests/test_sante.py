"""Tests du bloc « santé des agents » (sans réseau)."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.commun import sante
from agents.commun.sortie import lire_json

UTC = timezone.utc
CRONS_MARCHES = ["*/15 7-21 * * 1-5", "0 22 * * 1-5", "0 * * * 0,6"]


class TestPlanification(unittest.TestCase):
    def test_prochaine_execution(self):
        lundi = datetime(2026, 11, 2, 17, 34, tzinfo=UTC)
        self.assertEqual(sante.prochaine_execution(CRONS_MARCHES, lundi), datetime(2026, 11, 2, 17, 45, tzinfo=UTC))
        # Après 22 h en semaine : prochaine à 7 h le lendemain
        self.assertEqual(sante.prochaine_execution(CRONS_MARCHES, datetime(2026, 11, 2, 22, 0, tzinfo=UTC)),
                         datetime(2026, 11, 3, 7, 0, tzinfo=UTC))
        # Vendredi soir : le samedi est horaire
        self.assertEqual(sante.prochaine_execution(CRONS_MARCHES, datetime(2026, 11, 6, 22, 3, tzinfo=UTC)),
                         datetime(2026, 11, 7, 0, 0, tzinfo=UTC))
        self.assertEqual(sante.prochaine_execution(["0 6 * * *"], lundi), datetime(2026, 11, 3, 6, 0, tzinfo=UTC))

    def test_lecture_des_workflows(self):
        self.assertEqual(sante.crons_du_workflow("agent-marches.yml"), CRONS_MARCHES)
        self.assertEqual(sante.crons_du_workflow("agent-pays.yml"), ["0 6 * * *"])


class TestBloc(unittest.TestCase):
    maintenant = datetime(2026, 11, 2, 17, 34, tzinfo=UTC)

    def bloc(self, sources, precedent=None, maintenant=None):
        return sante.bloc_sante("test", "Agent test", 9, "x.yml", sources, maintenant or self.maintenant,
                                precedent, crons=["0 6 * * *"])

    def test_comptage_et_dates(self):
        precedent = {"sources": [{"nom": "b", "derniere_donnee_valide": "2026-11-01T06:00:00Z"}]}
        b = self.bloc([{"nom": "a", "etat": "ok"}, {"nom": "b", "etat": "échec"}, {"nom": "c", "etat": "non configurée"},
                       {"nom": "d", "etat": "périmée", "derniere_donnee_valide": "2025-01"}], precedent)
        self.assertEqual((b["sources_ok"], b["sources_total"]), (2, 3))
        par_nom = {s["nom"]: s for s in b["sources"]}
        self.assertEqual(par_nom["a"]["derniere_donnee_valide"], "2026-11-02T17:34:00Z")
        self.assertEqual(par_nom["b"]["derniere_donnee_valide"], "2026-11-01T06:00:00Z")  # reprise du bloc précédent
        self.assertEqual(b["intervalle_min"], 746)  # jusqu'au lendemain 6 h
        self.assertEqual(b["prochaine_prevue"], "2026-11-03T06:00:00Z")

    def test_battement_et_index(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "agent-test.json"
            b1 = self.bloc([{"nom": "a", "etat": "ok"}])
            self.assertTrue(sante.enregistrer_sante(chemin, b1, battement=timedelta(hours=1)))
            # 10 min plus tard, rien n'a changé : pas d'écriture
            b2 = self.bloc([{"nom": "a", "etat": "ok"}], maintenant=self.maintenant + timedelta(minutes=10))
            self.assertFalse(sante.enregistrer_sante(chemin, b2, battement=timedelta(hours=1)))
            # Une source tombe : écriture immédiate
            b3 = self.bloc([{"nom": "a", "etat": "échec"}], maintenant=self.maintenant + timedelta(minutes=20))
            self.assertTrue(sante.enregistrer_sante(chemin, b3, battement=timedelta(hours=1)))
            # 2 h plus tard, même état : le battement force l'écriture
            b4 = self.bloc([{"nom": "a", "etat": "échec"}], maintenant=self.maintenant + timedelta(hours=2))
            self.assertTrue(sante.enregistrer_sante(chemin, b4, battement=timedelta(hours=1)))
            self.assertEqual(lire_json(chemin)["meta"]["sante"]["derniere_execution"], "2026-11-02T19:34:00Z")
            index = lire_json(Path(dossier) / "index.json")["donnees"]
            self.assertEqual(index, [{"agent": "test", "libelle": "Agent test", "ordre": 9, "fichier": "agent-test.json"}])


if __name__ == "__main__":
    unittest.main()
