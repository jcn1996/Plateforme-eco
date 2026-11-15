"""Signaux en observation : enregistrement quotidien, sans usage pour décider, performance à 1, 3 et 6 mois.
Données de test construites de toutes pièces, dossier temporaire, cours simulés (aucun réseau)."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.trader import observation as OB
from agents.trader.agent import charger_config
from agents.trader.sources import FournisseurSimule

JOUR = datetime(2026, 11, 9, 16, 0, tzinfo=timezone.utc)


def ecrire(chemin: Path, objet) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet, ensure_ascii=False), encoding="utf-8")


def sources(data: Path, jour: str, revision: float = 1.05) -> None:
    ecrire(data / "inities.json", {"meta": {}, "donnees": {"dirigeants": {"achats": [
        {"date": jour, "depot": jour, "pays": "US", "ticker": "BRK.B", "societe": "Berkshire", "declarant": "X", "titre": "Directeur",
         "montant": 250000, "devise": "USD", "acc": "acc-1"},
        {"date": "2026-09-01", "depot": "2026-09-01", "pays": "US", "ticker": "OLD", "societe": "Ancien", "declarant": "Y", "acc": "acc-0"}]}}})
    ecrire(data / "entreprises" / "dynamique.json", {"meta": {}, "societes": {
        "AAA": {"analystes": {"estimations": {"0y": {"bpa": {"actuel": 2.0 * revision, "30j": 2.0}, "analystes": 12,
                                                      "revisions": {"hausse_30j": 6, "baisse_30j": 1}}}},
                "guidance": {"dernier": {"date": jour, "accession": "g-1", "statut": "relevée"}}},
        "BBB": {"analystes": {"estimations": {"0y": {"bpa": {"actuel": 2.02, "30j": 2.0}, "analystes": 12,
                                                      "revisions": {"hausse_30j": 6, "baisse_30j": 1}}}},
                "guidance": {"dernier": {"date": jour, "accession": "g-2", "statut": "maintenue"}}},
        "CCC": {"analystes": {"estimations": {"0y": {"bpa": {"actuel": 3.0, "30j": 2.0}, "analystes": 2,
                                                      "revisions": {"hausse_30j": 2, "baisse_30j": 0}}}}}}})


class TestObservation(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.INFO)
        self.tmp = Path(tempfile.mkdtemp(prefix="observation-"))
        self.data = self.tmp / "data"
        self.config = charger_config()
        self.f = FournisseurSimule(debut="2026-06-01")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        logging.disable(logging.NOTSET)

    def lancer(self, t):
        self.f.maintenant = t
        return OB.mettre_a_jour(self.f, self.data, self.config, t)

    def lire(self):
        return json.loads((self.data / "observation.json").read_text(encoding="utf-8"))["donnees"]

    def test_enregistrement_quotidien_et_filtres(self):
        sources(self.data, JOUR.date().isoformat())
        r = self.lancer(JOUR)
        self.assertEqual(r["nouveaux"], 3)
        d = self.lire()
        par_type = {s["type"]: s for s in d["signaux"]}
        self.assertEqual(set(par_type), {"achat_dirigeant", "revision_analystes", "relevement_guidance"})
        self.assertEqual(par_type["achat_dirigeant"]["symbole"], "BRK-B", "symbole Yahoo d'une action américaine")
        self.assertEqual(par_type["revision_analystes"]["symbole"], "AAA", "BBB : +1 % seulement ; CCC : 2 analystes")
        self.assertNotIn("OLD", {s["symbole"] for s in d["signaux"]}, "pas de rattrapage d'anciens signaux")
        for s in d["signaux"]:
            self.assertIsNotNone(s["cours_depart"])
            self.assertEqual(s["date_depart"], "2026-11-09")
        self.assertIn("jamais utilisés pour décider", d["regle"])
        self.assertIsNone(self.lancer(JOUR + timedelta(hours=3)), "une fois par jour")
        r = self.lancer(JOUR + timedelta(days=1))
        self.assertEqual(r["nouveaux"], 0, "déjà enregistrés ; la même révision n'est pas reprise avant 30 jours")

    def test_performance_aux_horizons(self):
        sources(self.data, JOUR.date().isoformat())
        self.lancer(JOUR)
        self.lancer(JOUR + timedelta(days=20))
        self.assertFalse([s for s in self.lire()["signaux"] if s.get("performance")], "rien à 1 mois avant 30 jours")
        self.lancer(JOUR + timedelta(days=31))
        d = self.lire()
        premiers = [s for s in d["signaux"] if s["date_depart"] == "2026-11-09"]
        self.assertEqual(len(premiers), 3)
        nouvelle = [s for s in d["signaux"] if s["date_depart"] != "2026-11-09"]
        self.assertEqual([s["type"] for s in nouvelle], ["revision_analystes"], "révision toujours en cours après 30 jours : nouvel enregistrement")
        for s in premiers:
            self.assertEqual(set(s["performance"]), {"1"})
            p = s["performance"]["1"]
            self.assertIsNotNone(p["msci_world_pct"])
            self.assertAlmostEqual(p["ecart_points"], p["pct"] - p["msci_world_pct"], places=6)
        self.lancer(JOUR + timedelta(days=92))
        r = self.lire()["resume"]
        for t in OB.TYPES:
            self.assertEqual(r[t]["horizons"]["3"]["n"], 1)
            self.assertEqual(r[t]["horizons"]["6"]["n"], 0)
            self.assertIsNotNone(r[t]["horizons"]["1"]["battent_indice_pct"])


if __name__ == "__main__":
    unittest.main()
