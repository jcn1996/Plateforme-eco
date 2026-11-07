"""Tests du planificateur avec des heures simulées (sans réseau, sans gh)."""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.commun.sortie import lire_json
from agents.planificateur.agent import decider, planifier, taches

UTC = timezone.utc
WORKFLOWS = {
    "agent-marches.yml": ['"7,22,37,52 7-21 * * 1-5"', '"7 22 * * 1-5"', '"7 * * * 0,6"'],
    "agent-pays.yml": ['"11 6 * * *"'],
    "agent-entreprises.yml": ['"30 22 * * 1-5"', '"10 3 * * 6"'],
    "maintien.yml": ['"41 4 * * 1"'],
    "planificateur.yml": [],
    "rattrapage.yml": ['"29 * * * *"'],
}


def t(texte):
    return datetime.fromisoformat(texte.replace("Z", "+00:00"))


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.wf, self.jr = self.d / "workflows", self.d / "journal"
        self.wf.mkdir()
        self.jr.mkdir()
        for nom, crons in WORKFLOWS.items():
            lignes = "\n".join(f"    - cron: {c}" for c in crons)
            (self.wf / nom).write_text(f"on:\n  schedule:\n{lignes}\n  workflow_dispatch:\n", encoding="utf-8")
        self.lances = []

    def tearDown(self):
        shutil.rmtree(self.d)

    def journal(self, workflow, derniere):
        nom = workflow.replace(".yml", ".json")
        (self.jr / nom).write_text(json.dumps({"derniere_execution": derniere, "meta": {"sante": {"workflow": workflow, "derniere_execution": derniere}}}))

    def appel(self, maintenant, en_cours=lambda w: False):
        def lanceur(workflow, params):
            self.lances.append((workflow, params))
            return True, ""
        return planifier(t(maintenant), self.jr, self.wf, en_cours=en_cours, lanceur=lanceur)

    def tache(self, workflow, cron):
        return next(x for x in taches(self.wf, self.jr) if x["workflow"] == workflow and x["cron"] == cron)


class TestDecisions(Base):
    def test_marches_creneau_du_puis_fait(self):
        self.journal("agent-marches.yml", "2026-11-02T09:53:00Z")  # lundi
        tache = self.tache("agent-marches.yml", "7,22,37,52 7-21 * * 1-5")
        d = decider(tache, t("2026-11-02T10:15:00Z"), [])
        self.assertEqual((d["lancer"], d["creneau"]), (True, "2026-11-02T10:07:00Z"))
        self.journal("agent-marches.yml", "2026-11-02T10:09:00Z")  # exécuté par le planning GitHub
        self.assertFalse(decider(self.tache("agent-marches.yml", "7,22,37,52 7-21 * * 1-5"), t("2026-11-02T10:15:00Z"), [])["lancer"])

    def test_marge_de_deux_minutes(self):
        self.journal("agent-marches.yml", "2026-11-02T09:40:00Z")
        d = decider(self.tache("agent-marches.yml", "7,22,37,52 7-21 * * 1-5"), t("2026-11-02T10:08:00Z"), [])
        self.assertEqual(d["creneau"], "2026-11-02T09:52:00Z")  # 10 h 07 + 2 min pas encore atteint
        self.assertTrue(d["lancer"])  # mais le créneau de 9 h 52 n'est pas fait

    def test_pays_une_fois_par_jour(self):
        self.journal("agent-pays.yml", "2026-11-02T06:20:00Z")
        tache = self.tache("agent-pays.yml", "11 6 * * *")
        self.assertFalse(decider(tache, t("2026-11-03T06:10:00Z"), [])["lancer"])  # pas encore l'heure
        self.assertTrue(decider(tache, t("2026-11-03T06:15:00Z"), [])["lancer"])
        self.assertTrue(decider(tache, t("2026-11-03T15:00:00Z"), [])["lancer"])  # toujours dû l'après-midi s'il manque

    def test_jamais_deux_fois_le_meme_creneau(self):
        self.journal("agent-pays.yml", "2026-11-02T06:20:00Z")

        def pays():
            return [l for l in self.lances if l[0] == "agent-pays.yml"]
        r1 = self.appel("2026-11-03T06:15:00Z")
        self.assertEqual(len(pays()), 1)
        self.appel("2026-11-03T06:30:00Z")  # l'agent tourne encore : pas de nouveau lancement
        self.assertEqual(len(pays()), 1)
        self.appel("2026-11-03T07:20:00Z")  # 65 min sans résultat : nouvelle tentative
        self.assertEqual(len(pays()), 2)
        self.appel("2026-11-03T08:30:00Z")  # 2 tentatives faites : on s'arrête
        self.assertEqual(len(pays()), 2)
        self.journal("agent-pays.yml", "2026-11-03T08:40:00Z")
        self.appel("2026-11-04T06:15:00Z")  # créneau du lendemain : nouveau lancement
        self.assertEqual(len(pays()), 3)
        self.assertTrue(r1["ecrit"])

    def test_pays_flux_du_soir(self):
        # Mode « flux » de l'agent pays : en soirée à New York (2 h 07 UTC, du mardi au samedi)
        (self.wf / "agent-pays.yml").write_text('on:\n  schedule:\n    - cron: "11 6 * * *"\n    - cron: "7 2 * * 2-6"\n  workflow_dispatch:\n',
                                                encoding="utf-8")
        pays = lambda: [l for l in self.lances if l[0] == "agent-pays.yml"]
        self.journal("agent-pays.yml", "2026-11-02T06:20:00Z")      # lundi, exécution complète faite
        self.appel("2026-11-03T02:15:00Z")                          # mardi 2 h 15 UTC = lundi 21 h 15 à New York
        self.assertEqual(pays(), [("agent-pays.yml", {"mode": "flux"})])
        self.journal("agent-pays.yml", "2026-11-03T02:20:00Z")
        self.appel("2026-11-03T06:15:00Z")                          # exécution complète du matin
        self.assertEqual(pays()[-1], ("agent-pays.yml", {"mode": "complet"}))
        self.lances.clear()
        self.journal("agent-pays.yml", "2026-11-08T06:20:00Z")      # dimanche : pas de flux (marchés fermés la veille)
        self.appel("2026-11-09T02:15:00Z")
        self.assertEqual(pays(), [])

    def test_revision_complete_du_samedi(self):
        self.journal("agent-entreprises.yml", "2026-11-06T22:45:00Z")  # quotidienne de vendredi faite
        self.appel("2026-11-07T03:15:00Z")
        self.assertIn(("agent-entreprises.yml", {"mode": "complet"}), self.lances)

    def test_un_seul_lancement_par_workflow(self):
        self.journal("agent-entreprises.yml", "2026-11-05T22:45:00Z")  # vendredi manqué ET samedi dû
        self.appel("2026-11-07T03:15:00Z")
        self.assertEqual([l for l in self.lances if l[0] == "agent-entreprises.yml"], [("agent-entreprises.yml", {"mode": "complet"})])

    def test_maintien_du_lundi_sans_journal(self):
        self.appel("2026-11-09T04:45:00Z")
        self.assertIn(("maintien.yml", {}), self.lances)
        n = len(self.lances)
        self.appel("2026-11-09T06:00:00Z")
        self.assertEqual(len([l for l in self.lances[n:] if l[0] == "maintien.yml"]), 0)

    def test_workflows_ignores_et_execution_en_cours(self):
        self.journal("agent-pays.yml", "2026-11-02T06:20:00Z")
        self.appel("2026-11-03T06:15:00Z", en_cours=lambda w: w == "agent-pays.yml")
        self.assertNotIn("agent-pays.yml", [l[0] for l in self.lances])
        self.assertNotIn("rattrapage.yml", [l[0] for l in self.lances])
        trace = lire_json(self.jr / "planificateur.json")["donnees"]
        self.assertIn("ignoré", [x["statut"] for x in trace if x["workflow"] == "agent-pays.yml"])

    def test_battement_sans_commit_inutile(self):
        for w in ("agent-marches.yml", "agent-pays.yml", "agent-entreprises.yml"):
            self.journal(w, "2026-11-04T10:50:00Z")  # tous les créneaux de la période simulée sont faits
        self.appel("2026-11-04T10:15:00Z")  # maintien lancé + premier battement
        self.assertTrue(self.appel("2026-11-04T10:15:00Z")["ecrit"] is False)
        self.assertFalse(self.appel("2026-11-04T10:30:00Z")["ecrit"])  # 15 min : rien à écrire
        r = self.appel("2026-11-04T10:36:00Z")  # 21 min depuis le dernier appel enregistré
        self.assertTrue(r["ecrit"])
        meta = lire_json(self.jr / "planificateur.json")["meta"]
        self.assertEqual(meta["dernier_appel"], "2026-11-04T10:36:00Z")
        self.assertEqual(meta["sante"]["panne_minutes"], 45)
        index = lire_json(self.jr / "index.json")["donnees"]
        self.assertIn("planificateur.json", [e["fichier"] for e in index])


class TestGeopolitique(Base):
    """Agent géopolitique : planning réel (workflow du dépôt), toutes les heures, mode « quotidien » à 6 h 03."""

    def setUp(self):
        super().setUp()
        reel = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "agent-geopolitique.yml"
        shutil.copy(reel, self.wf / "agent-geopolitique.yml")
        for w in ("agent-marches.yml", "agent-pays.yml", "agent-entreprises.yml", "maintien.yml"):
            (self.wf / w).unlink()

    def geo(self):
        return [l for l in self.lances if l[0] == "agent-geopolitique.yml"]

    def test_toutes_les_heures(self):
        self.journal("agent-geopolitique.yml", "2026-11-03T13:04:00Z")
        self.appel("2026-11-03T14:00:00Z")
        self.assertEqual(self.geo(), [])  # créneau de 14 h 03 pas encore atteint
        self.appel("2026-11-03T14:06:00Z")
        self.assertEqual(self.geo(), [("agent-geopolitique.yml", {"mode": "horaire"})])
        self.journal("agent-geopolitique.yml", "2026-11-03T14:08:00Z")
        self.appel("2026-11-03T14:21:00Z")
        self.assertEqual(len(self.geo()), 1)  # fait : pas de second lancement

    def test_synthese_de_six_heures(self):
        self.journal("agent-geopolitique.yml", "2026-11-03T05:04:00Z")
        self.appel("2026-11-03T06:06:00Z")
        self.assertEqual(self.geo(), [("agent-geopolitique.yml", {"mode": "quotidien"})])

    def test_six_heures_manquee_rattrapee_en_quotidien(self):
        # Exécution de 5 h faite ; 6 h 03 et 7 h 03 manquées : le créneau le plus récent (horaire) est lancé,
        # l'agent écrit quand même la synthèse du jour, qui manque après 6 h UTC
        self.journal("agent-geopolitique.yml", "2026-11-03T05:04:00Z")
        self.appel("2026-11-03T07:10:00Z")
        self.assertEqual(self.geo(), [("agent-geopolitique.yml", {"mode": "horaire"})])


class TestRisque(Base):
    """Agent risque : planning réel, toutes les heures en séance (en semaine), analyse complète à 22 h 45."""

    def setUp(self):
        super().setUp()
        reel = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "agent-risque.yml"
        shutil.copy(reel, self.wf / "agent-risque.yml")
        for w in ("agent-marches.yml", "agent-pays.yml", "agent-entreprises.yml", "maintien.yml"):
            (self.wf / w).unlink()

    def risque(self):
        return [l for l in self.lances if l[0] == "agent-risque.yml"]

    def test_horaire_en_seance(self):
        self.journal("agent-risque.yml", "2026-11-03T13:18:00Z")  # mardi
        self.appel("2026-11-03T14:20:00Z")
        self.assertEqual(self.risque(), [("agent-risque.yml", {"mode": "horaire"})])

    def test_analyse_complete_du_soir(self):
        self.journal("agent-risque.yml", "2026-11-03T21:18:00Z")
        self.appel("2026-11-03T22:48:00Z")
        self.assertEqual(self.risque(), [("agent-risque.yml", {"mode": "complet"})])

    def test_rien_le_week_end_sauf_le_soir(self):
        self.journal("agent-risque.yml", "2026-11-06T22:46:00Z")  # vendredi soir, analyse complète faite
        self.appel("2026-11-07T14:20:00Z")  # samedi
        self.assertEqual(self.risque(), [])


class TestMatieresPremieres(Base):
    """Agent matières premières : planning réel, en semaine à 22 h 15 UTC (rien le week-end)."""

    def setUp(self):
        super().setUp()
        reel = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "agent-matieres-premieres.yml"
        shutil.copy(reel, self.wf / "agent-matieres-premieres.yml")
        for w in ("agent-marches.yml", "agent-pays.yml", "agent-entreprises.yml", "maintien.yml"):
            (self.wf / w).unlink()

    def lances_mp(self):
        return [l for l in self.lances if l[0] == "agent-matieres-premieres.yml"]

    def test_lance_le_soir_en_semaine(self):
        self.journal("agent-matieres-premieres.yml", "2026-11-02T22:20:00Z")  # lundi soir fait
        self.appel("2026-11-03T22:20:00Z")  # mardi, créneau de 22 h 15 dû
        self.assertEqual(self.lances_mp(), [("agent-matieres-premieres.yml", {})])

    def test_vendredi_soir_puis_rien_le_week_end(self):
        self.journal("agent-matieres-premieres.yml", "2026-11-06T22:18:00Z")  # vendredi soir (rapport CFTC du jour)
        self.appel("2026-11-07T14:20:00Z")  # samedi
        self.appel("2026-11-08T23:00:00Z")  # dimanche soir
        self.assertEqual(self.lances_mp(), [])


class TestInities(Base):
    """Agent initiés : planning réel ; « complet » du mardi au samedi (formulaires 4, 13D, AMF de la veille),
    « leger » le dimanche et le lundi (vérification quotidienne des 13F et des élus)."""

    def setUp(self):
        super().setUp()
        reel = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "agent-inities.yml"
        shutil.copy(reel, self.wf / "agent-inities.yml")
        for w in ("agent-marches.yml", "agent-pays.yml", "agent-entreprises.yml", "maintien.yml"):
            (self.wf / w).unlink()

    def lances_i(self):
        return [l for l in self.lances if l[0] == "agent-inities.yml"]

    def test_complet_en_semaine(self):
        self.journal("agent-inities.yml", "2026-11-02T06:40:00Z")  # lundi (léger) fait
        self.appel("2026-11-03T06:45:00Z")  # mardi
        self.assertEqual(self.lances_i(), [("agent-inities.yml", {"mode": "complet"})])

    def test_leger_le_dimanche(self):
        self.journal("agent-inities.yml", "2026-11-07T06:40:00Z")  # samedi (complet) fait
        self.appel("2026-11-08T07:00:00Z")  # dimanche
        self.assertEqual(self.lances_i(), [("agent-inities.yml", {"mode": "leger"})])
        self.appel("2026-11-08T07:15:00Z")  # déjà lancé pour ce créneau
        self.assertEqual(len(self.lances_i()), 1)


if __name__ == "__main__":
    unittest.main()
