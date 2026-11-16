"""États des entrées du chef d'orchestre (à jour, dégradé, en panne) selon le planning de chaque agent.
Données construites de toutes pièces dans un dossier temporaire (ni config/ ni data/ réels)."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.chef.agent import charger_config
from agents.chef.entrees import charger

ENT = ["30 22 * * 1-5", "10 3 * * 6"]


def t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


class TestEntrees(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        (self.data / "journal").mkdir()
        self.config = charger_config()
        self.config["entrees"]["fichiers"] = {
            "entreprises": {"fichier": "entreprises.json", "journal": "agent-entreprises.json", "libelle": "Agent entreprises", "age_max_h": 30},
            "pays": {"fichier": "pays.json", "journal": "agent-pays.json", "libelle": "Agent pays", "age_max_h": 30},
            "absent": {"fichier": "absent.json", "journal": "agent-absent.json", "libelle": "Absent", "age_max_h": 30}}

    def tearDown(self):
        self.tmp.cleanup()

    def ecrire(self, nom, genere, sante=None, journal=None):
        (self.data / nom).write_text(json.dumps({"meta": {"genere_le": genere}, "donnees": []}), encoding="utf-8")
        if sante is not None:
            (self.data / "journal" / journal).write_text(json.dumps({"meta": {"sante": sante}}), encoding="utf-8")

    def test_trois_etats(self):
        self.ecrire("entreprises.json", "2026-11-14T11:14:38Z",
                    {"derniere_execution": "2026-11-14T10:37:27Z", "planning": {"crons": ENT}, "degrade": False}, "agent-entreprises.json")
        self.ecrire("pays.json", "2026-11-16T15:37:14Z",
                    {"derniere_execution": "2026-11-16T15:37:14Z", "planning": {"crons": ["11 6 * * *"]}, "degrade": True,
                     "raisons": ["Argentine · Flux étrangers : 0 source valide au lieu de 1 (perdue : globalx)"],
                     "raisons_depuis": {"Argentine · Flux étrangers": "2026-11-14T15:00:00Z"}}, "agent-pays.json")
        e = charger(self.data, self.config, t("2026-11-16T17:00:00Z"))
        # 54 h sans exécution, mais aucune exécution prévue manquée : plus « périmée »
        self.assertEqual((e["entreprises"].etat, e["entreprises"].coef), ("à jour", 1.0))
        self.assertEqual(e["pays"].etat, "dégradé")
        self.assertEqual(e["pays"].resume()["raisons_depuis"], {"Argentine · Flux étrangers": "2026-11-14T15:00:00Z"})
        self.assertEqual(e["absent"].etat, "manquante")
        # Mardi 16 h : l'exécution de lundi 22 h 30 a été manquée (marge 11,2 h dépassée)
        e = charger(self.data, self.config, t("2026-11-17T16:00:00Z"))
        self.assertEqual(e["entreprises"].etat, "en panne")
        self.assertIn("manquée", e["entreprises"].resume()["panne"]["raison"])
        self.assertLess(e["entreprises"].coef, 1.0)
        # Deux jours plus tard : coefficient au plancher
        e = charger(self.data, self.config, t("2026-11-19T12:00:00Z"))
        self.assertEqual(e["entreprises"].coef, self.config["entrees"]["coef_perime_min"])


if __name__ == "__main__":
    unittest.main()
