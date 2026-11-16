"""Alerte de panne : un agent dont une exécution prévue a été manquée (au-delà de sa marge) ou a échoué est affiché en tête des alertes."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.chef.agent import alertes_pannes


class TestAlertesPannes(unittest.TestCase):
    def test_pannes(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            (data / "journal").mkdir()
            index = {"donnees": [{"agent": "pays", "libelle": "Agent pays", "ordre": 1, "fichier": "agent-pays.json"},
                                 {"agent": "macro", "libelle": "Agent macro", "ordre": 3, "fichier": "agent-macro.json"}]}
            (data / "journal" / "index.json").write_text(json.dumps(index), encoding="utf-8")
            pays = {"meta": {"sante": {"agent": "pays", "libelle": "Agent pays", "workflow": "agent-pays.yml",
                                       "derniere_execution": "2026-11-09T16:05:36Z", "planning": {"crons": ["11 6 * * *"]},
                                       "derniere_tentative": {"date": "2026-11-14T13:27:34Z", "statut": "echec",
                                                              "raison": "ValueError : signal non conforme"}}}}
            macro = {"meta": {"sante": {"agent": "macro", "derniere_execution": "2026-11-14T06:45:00Z",
                                        "planning": {"crons": ["41 6 * * *"]}}}}
            (data / "journal" / "agent-pays.json").write_text(json.dumps(pays), encoding="utf-8")
            (data / "journal" / "agent-macro.json").write_text(json.dumps(macro), encoding="utf-8")
            al = alertes_pannes(data, datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc))
            self.assertEqual(len(al), 1)
            a = al[0]
            self.assertTrue(a["panne"])
            self.assertEqual((a["agent"], a["importance"], a["route"]), ("sante", "forte", {"type": "sante"}))
            self.assertIn("Agent pays", a["titre"])
            self.assertIn("09/11/2026", a["texte"])
            self.assertIn("signal non conforme", a["texte"])
            # Agent de quelques exécutions par semaine, entre deux exécutions prévues : pas d'alerte
            ent = {"meta": {"sante": {"agent": "entreprises", "derniere_execution": "2026-11-14T10:37:27Z",
                                      "planning": {"crons": ["30 22 * * 1-5", "10 3 * * 6"]}}}}
            (data / "journal" / "agent-entreprises.json").write_text(json.dumps(ent), encoding="utf-8")
            index["donnees"].append({"agent": "entreprises", "libelle": "Agent entreprises", "ordre": 4, "fichier": "agent-entreprises.json"})
            (data / "journal" / "index.json").write_text(json.dumps(index), encoding="utf-8")
            self.assertEqual([x["id"] for x in alertes_pannes(data, datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc))
                              if x["id"] == "panne-entreprises"], [])


if __name__ == "__main__":
    unittest.main()
