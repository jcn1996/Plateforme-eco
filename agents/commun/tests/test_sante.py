"""Tests du bloc « santé des agents » (sans réseau)."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.commun import sante
from agents.commun.sortie import lire_json

UTC = timezone.utc
CRONS_MARCHES = ["7,22,37,52 7-21 * * 1-5", "7 22 * * 1-5", "7 * * * 0,6"]


class TestPlanification(unittest.TestCase):
    def test_prochaine_execution(self):
        lundi = datetime(2026, 11, 2, 17, 34, tzinfo=UTC)
        self.assertEqual(sante.prochaine_execution(CRONS_MARCHES, lundi), datetime(2026, 11, 2, 17, 37, tzinfo=UTC))
        # Après 22 h 07 en semaine : prochaine à 7 h 07 le lendemain
        self.assertEqual(sante.prochaine_execution(CRONS_MARCHES, datetime(2026, 11, 2, 22, 7, tzinfo=UTC)),
                         datetime(2026, 11, 3, 7, 7, tzinfo=UTC))
        # Vendredi soir : le samedi est horaire
        self.assertEqual(sante.prochaine_execution(CRONS_MARCHES, datetime(2026, 11, 6, 22, 10, tzinfo=UTC)),
                         datetime(2026, 11, 7, 0, 7, tzinfo=UTC))
        self.assertEqual(sante.prochaine_execution(["0 6 * * *"], lundi), datetime(2026, 11, 3, 6, 0, tzinfo=UTC))

    def test_intervalle_prevu(self):
        def intervalle(crons, t):
            return sante.bloc_sante("t", "T", 1, "x.yml", [], t, crons=crons)["intervalle_min"]
        self.assertEqual(intervalle(["0 6 * * *"], datetime(2026, 11, 2, 6, 4, tzinfo=UTC)), 1440)   # lancé en retard
        self.assertEqual(intervalle(["0 6 * * *"], datetime(2026, 11, 2, 18, 1, tzinfo=UTC)), 1440)  # lancé à la main
        self.assertEqual(intervalle(CRONS_MARCHES, datetime(2026, 11, 2, 17, 34, tzinfo=UTC)), 15)
        self.assertEqual(intervalle(CRONS_MARCHES, datetime(2026, 11, 2, 22, 9, tzinfo=UTC)), 9 * 60)  # nuit
        self.assertEqual(intervalle(CRONS_MARCHES, datetime(2026, 11, 7, 13, 5, tzinfo=UTC)), 60)     # week-end

    def test_lecture_des_workflows(self):
        self.assertEqual(sante.crons_du_workflow("agent-marches.yml"),
                         CRONS_MARCHES[:2] + ["7 0-6,23 * * 1-5", "7 * * * 0,6", "22,37,52 22-23 * * 0"])
        self.assertEqual(sante.crons_du_workflow("agent-pays.yml"), ["11 6 * * *"])
        self.assertEqual(sante.crons_du_workflow("agent-macro.yml"), ["41 6 * * *"])
        for fichier in ("agent-marches.yml", "agent-pays.yml", "agent-macro.yml", "rattrapage.yml", "maintien.yml"):
            # Aucune tâche à une minute ronde (souvent retardée ou sautée par GitHub)
            for cron in sante.crons_du_workflow(fichier):
                self.assertNotIn(cron.split()[0], ("0", "*", "*/15", "30"), f"{fichier} : {cron}")


class TestBloc(unittest.TestCase):
    maintenant = datetime(2026, 11, 2, 17, 34, tzinfo=UTC)

    def bloc(self, sources, precedent=None, maintenant=None):
        return sante.bloc_sante("test", "Agent test", 9, "x.yml", sources, maintenant or self.maintenant,
                                precedent, crons=["0 6 * * *"])

    def test_comptage_et_dates(self):
        precedent = {"sources": [{"nom": "b", "derniere_donnee_valide": "2026-11-01T06:00:00Z"}]}
        b = self.bloc([{"nom": "a", "etat": "ok"}, {"nom": "b", "etat": "échec"}, {"nom": "c", "etat": "non configurée"},
                       {"nom": "d", "etat": "périmée", "derniere_donnee_valide": "2025-01"}], precedent)
        self.assertEqual((b["sources_ok"], b["sources_total"]), (1, 3))  # seule la source « ok » répond ; « non configurée » non comptée
        par_nom = {s["nom"]: s for s in b["sources"]}
        self.assertEqual(par_nom["a"]["derniere_donnee_valide"], "2026-11-02T17:34:00Z")
        self.assertEqual(par_nom["b"]["derniere_donnee_valide"], "2026-11-01T06:00:00Z")  # reprise du bloc précédent
        self.assertEqual(b["intervalle_min"], 1440)  # quotidien à 6 h : 24 h, même pour une exécution à 17 h 34
        self.assertEqual(b["prochaine_prevue"], "2026-11-03T06:00:00Z")

    def test_regle_degrade(self):
        ind = lambda valides, configurees: {"valides": valides, "configurees": configurees}
        # Première exécution : la référence est l'état courant, rien n'est dégradé
        raisons, ref = sante.degradation({"US · Inflation": ind(["ocde", "fmi"], ["ocde", "fmi", "bls"])}, {})
        self.assertEqual((raisons, ref["US · Inflation"]), ([], ["fmi", "ocde"]))
        # Une source périmée remplacée par une source à jour : pas dégradé
        raisons, ref = sante.degradation({"US · Inflation": ind(["bls", "fmi"], ["ocde", "fmi", "bls"])}, ref)
        self.assertEqual(raisons, [])
        # Deux sources → une seule : dégradé, et la référence est conservée
        raisons, ref2 = sante.degradation({"US · Inflation": ind(["fmi"], ["ocde", "fmi", "bls"])}, ref)
        self.assertEqual(len(raisons), 1)
        self.assertIn("perdue : bls", raisons[0])
        self.assertEqual(ref2, ref)
        raisons, _ = sante.degradation({"US · Inflation": ind(["fmi"], ["ocde", "fmi", "bls"])}, ref2)
        self.assertEqual(len(raisons), 1)  # reste dégradé tant que la source n'est pas revenue
        # La source perdue est retirée de la configuration : plus attendue
        raisons, ref3 = sante.degradation({"US · Inflation": ind(["fmi"], ["ocde", "fmi"])}, ref2)
        self.assertEqual((raisons, ref3["US · Inflation"]), ([], ["fmi"]))

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
            # Planning complet et champs horaires recopiés au premier niveau du journal
            j = lire_json(chemin)
            self.assertEqual(j["derniere_execution"], "2026-11-02T19:34:00Z")
            self.assertEqual(j["prochaine_prevue"], "2026-11-03T06:00:00Z")
            self.assertEqual(j["intervalle_min"], 1440)
            self.assertEqual(j["planning"], {"crons": ["0 6 * * *"], "fuseau": "UTC"})
            self.assertEqual(j["meta"]["sante"]["planning"], j["planning"])
            index = lire_json(Path(dossier) / "index.json")["donnees"]
            self.assertEqual(index, [{"agent": "test", "libelle": "Agent test", "ordre": 9, "fichier": "agent-test.json"}])


if __name__ == "__main__":
    unittest.main()
