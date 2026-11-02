"""Tests du rattrapage, sans réseau : python -m unittest discover -s agents/rattrapage -t ."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.commun.sortie import ecrire_json, lire_json
from agents.rattrapage import agent as R

UTC = timezone.utc
MARCHES = ["7,22,37,52 7-21 * * 1-5", "7 22 * * 1-5", "7 * * * 0,6"]


def ag(derniere, crons=MARCHES, nom="marches"):
    return {"agent": nom, "workflow": f"agent-{nom}.yml", "derniere_execution": derniere, "crons": crons}


class TestDecision(unittest.TestCase):
    def test_journee(self):
        t = datetime(2026, 11, 3, 10, 29, tzinfo=UTC)  # mardi
        self.assertFalse(R.a_relancer(ag("2026-11-03T10:08:00Z"), t, [])[0])
        self.assertFalse(R.a_relancer(ag("2026-11-03T09:23:00Z"), t, [])[0])  # 9 h 37 manque depuis 52 min
        relancer, raison, manquante = R.a_relancer(ag("2026-11-03T09:08:00Z"), t, [])  # 9 h 22 manque depuis 67 min
        self.assertTrue(relancer)
        self.assertEqual(manquante, datetime(2026, 11, 3, 9, 22, tzinfo=UTC))
        self.assertIn("67 min", raison)

    def test_nuit_et_week_end(self):
        # La nuit, après l'exécution de 22 h 07 : rien ne manque jusqu'à 7 h 07
        self.assertFalse(R.a_relancer(ag("2026-11-03T22:08:00Z"), datetime(2026, 11, 4, 3, 29, tzinfo=UTC), [])[0])
        self.assertFalse(R.a_relancer(ag("2026-11-03T22:08:00Z"), datetime(2026, 11, 4, 7, 29, tzinfo=UTC), [])[0])
        self.assertTrue(R.a_relancer(ag("2026-11-03T22:08:00Z"), datetime(2026, 11, 4, 8, 29, tzinfo=UTC), [])[0])
        # Week-end (horaire) : relance si 13 h 07 manque à 14 h 29
        self.assertFalse(R.a_relancer(ag("2026-11-07T13:08:00Z"), datetime(2026, 11, 7, 14, 29, tzinfo=UTC), [])[0])
        self.assertTrue(R.a_relancer(ag("2026-11-07T12:08:00Z"), datetime(2026, 11, 7, 14, 29, tzinfo=UTC), [])[0])

    def test_quotidien(self):
        crons = ["11 6 * * *"]
        self.assertFalse(R.a_relancer(ag("2026-11-02T06:15:00Z", crons, "pays"), datetime(2026, 11, 3, 6, 29, tzinfo=UTC), [])[0])
        self.assertTrue(R.a_relancer(ag("2026-11-02T06:15:00Z", crons, "pays"), datetime(2026, 11, 3, 7, 29, tzinfo=UTC), [])[0])
        self.assertTrue(R.a_relancer(ag(None, crons, "pays"), datetime(2026, 11, 3, 7, 29, tzinfo=UTC), [])[0])

    def test_une_relance_par_heure(self):
        t = datetime(2026, 11, 3, 10, 29, tzinfo=UTC)
        deja = [{"agent": "marches", "statut": "relancé", "relance_le": "2026-11-03T09:45:00Z"}]
        self.assertEqual(R.a_relancer(ag("2026-11-03T08:00:00Z"), t, deja)[:2], (False, "déjà relancé dans l'heure"))
        deja[0]["relance_le"] = "2026-11-03T09:29:00Z"
        self.assertTrue(R.a_relancer(ag("2026-11-03T08:00:00Z"), t, deja)[0])
        deja[0] |= {"relance_le": "2026-11-03T10:00:00Z", "statut": "échec"}  # un échec n'empêche pas de réessayer
        self.assertTrue(R.a_relancer(ag("2026-11-03T08:00:00Z"), t, deja)[0])


class TestRattraper(unittest.TestCase):
    def test_trace_et_limite(self):
        with tempfile.TemporaryDirectory() as dossier:
            d = Path(dossier)
            ecrire_json(d / "index.json", {"meta": {}, "donnees": []})
            ecrire_json(d / "agent-marches.json", {"meta": {"sante": {"agent": "marches", "workflow": "agent-marches.yml",
                                                                       "derniere_execution": "2026-11-03T08:00:00Z"}},
                                                    "donnees": []})
            ecrire_json(d / "agent-pays.json", {"meta": {"sante": {"agent": "pays", "workflow": "agent-pays.yml"}},
                                                "derniere_execution": "2026-11-03T06:15:00Z", "donnees": []})
            lances = []
            lanceur = lambda wf: (lances.append(wf) or (True, ""))
            t = datetime(2026, 11, 3, 10, 29, tzinfo=UTC)
            nouvelles = R.rattraper(t, d, en_cours=lambda wf: False, lanceur=lanceur)
            self.assertEqual(lances, ["agent-marches.yml"])  # l'agent pays est à jour
            self.assertEqual(nouvelles[0]["statut"], "relancé")
            self.assertEqual(nouvelles[0]["execution_manquante"], "2026-11-03T08:07:00Z")
            # Relancé une deuxième fois dans l'heure : non
            R.rattraper(t.replace(minute=50), d, en_cours=lambda wf: False, lanceur=lanceur)
            self.assertEqual(lances, ["agent-marches.yml"])
            # Exécution déjà en attente : tracée, non relancée
            R.rattraper(t.replace(hour=11), d, en_cours=lambda wf: True, lanceur=lanceur)
            self.assertEqual(lances, ["agent-marches.yml"])
            trace = lire_json(d / "rattrapage.json")["donnees"]
            self.assertEqual([e["statut"] for e in trace], ["relancé", "ignoré"])


if __name__ == "__main__":
    unittest.main()
