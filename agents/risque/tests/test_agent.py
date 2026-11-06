"""Tests de l'agent risque : données de test enregistrées (agents/risque/tests/donnees), dossier
temporaire, sans réseau ni Gemini réel. Les vrais config/ et data/ ne sont jamais lus ni modifiés."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.commun.essais import copier_donnees_test
from agents.risque import calculs as C
from agents.risque import contradicteur as K
from agents.risque import mondial as M
from agents.risque.agent import charger_config, executer, pays_suivis
from agents.risque.sources import FournisseurTest

DONNEES = Path(__file__).resolve().parent / "donnees"
PAYS_TEST = ["US", "FR", "DE", "IT", "ES", "BR", "TR", "JP", "MX"]
MAINTENANT = datetime(2026, 11, 6, 22, 45, tzinfo=timezone.utc)


def ecrire(chemin: Path, objet) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet, ensure_ascii=False), encoding="utf-8")


def preparer_data(dossier: Path) -> None:
    """data/ de test : pays.json et macro.json produits par les agents en mode test, plus
    geopolitique.json, entreprises.json et des signaux d'autres agents écrits ici."""
    copier_donnees_test(dossier, ("pays.json",))
    ecrire(dossier / "geopolitique.json", {"meta": {}, "donnees": {"pays": {
        "US": {"score": 72}, "FR": {"score": 20}, "DE": {"score": 18}, "IT": {"score": 15}, "BR": {"score": 6},
        "TR": {"score": 55}, "JP": {"score": 12}, "MX": {"score": 30}, "ES": {"score": 10}}}})
    ecrire(dossier / "entreprises.json", {"meta": {}, "donnees": [{"ticker": "0700.HK", "pays": "CN"}, {"ticker": "PAYX", "pays": "US"}]})
    ecrire(dossier / "signaux" / "geopolitique.json", {"meta": {}, "donnees": [
        {"type": "evenement_grave", "cle": "evt-1", "date": "2026-11-04", "importance": "haute",
         "titre": "Événement de gravité 4 : tensions au Moyen-Orient", "pays": ["US"], "sources": ["https://a.example/1"]},
        {"type": "evenement_grave", "cle": "evt-2", "date": "2026-11-03", "importance": "haute",
         "titre": "Événement de gravité 4 : frappes", "pays": ["FR"], "sources": ["https://a.example/2", "https://b.example/3"]},
    ]})
    ecrire(dossier / "signaux" / "macro.json", {"meta": {}, "donnees": [
        {"date": "2026-11-06", "type": "changement_de_phase", "cle": "monde", "importance": "forte",
         "titre": "Monde : passage de « Expansion sans inflation » à « Ralentissement inflationniste »",
         "explication": "Indicateur avancé de l'OCDE (G20) à 100,1, −0,06 pt sur 3 mois.", "source": "OCDE"},
        {"date": "2026-11-05", "type": "changement_de_phase", "cle": "monde", "importance": "forte",
         "titre": "Monde : passage de « Ralentissement inflationniste » à « Expansion sans inflation »",
         "explication": "Indicateur avancé de l'OCDE (G20) à 100,2, −0,08 pt sur 3 mois.", "source": "OCDE"},
    ]})
    ecrire(dossier / "signaux" / "entreprises.json", {"meta": {}, "donnees": [
        {"date": "2026-11-05", "type": "nouvelle_pepite", "cle": "0700.HK", "importance": "moyenne",
         "titre": "Tencent entre dans la liste", "explication": "point faible : momentum 12 mois : −32,0 %."},
        {"date": "2026-11-05", "type": "variation_de_note", "cle": "AAPL", "importance": "faible", "titre": "Note en baisse"},
        {"date": "2026-10-01", "type": "nouvelle_pepite", "cle": "OLD", "importance": "moyenne", "titre": "Trop ancien"},
    ]})


class FournisseurCompteur(FournisseurTest):
    def __init__(self, dossier):
        super().__init__(dossier)
        self.appels = {"fred": 0, "cours": 0}

    def fred(self, serie, depuis):
        self.appels["fred"] += 1
        return super().fred(serie, depuis)

    def cours(self, symboles, periode):
        self.appels["cours"] += 1
        return super().cours(symboles, periode)


class BaseRisque(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="risque-"))
        self.data = self.tmp / "data"
        preparer_data(self.data)
        self.config = charger_config()
        self.pays = {k: v for k, v in pays_suivis().items() if k in PAYS_TEST}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lancer(self, f=None, mode="complet", maintenant=MAINTENANT, **kw):
        kw.setdefault("dormir", lambda s: None)
        return executer(f or FournisseurTest(DONNEES), self.config, self.data, maintenant, mode, cle_gemini=kw.pop("cle", ""),
                        pays=self.pays, **kw)


class TestExecution(BaseRisque):
    def test_execution_complete(self):
        r = self.lancer()
        self.assertTrue(r["ok"])
        d = json.loads((self.data / "risque.json").read_text(encoding="utf-8"))
        m = d["donnees"]["mondial"]
        self.assertIn(m["palier"], ["Calme", "Vigilance", "Tension", "Crise"])
        self.assertTrue(0 <= m["score"] <= 100)
        self.assertEqual(len(m["principaux"]), 3)
        self.assertTrue(m["contre"], "rubrique « Ce qui pourrait me donner tort »")
        self.assertIn(m["confiance"]["niveau"], ["faible", "moyen", "élevé"])
        self.assertTrue(m["faits"] and isinstance(m["interpretations"], list))
        # Seuils calés sur les percentiles (plus de 5 ans d'historique dans les données de test)
        s = d["donnees"]["seuils"]
        self.assertIn("percentiles", s["methode"])
        self.assertLess(s["Vigilance"], s["Tension"])
        self.assertLess(s["Tension"], s["Crise"])
        # Indicateurs : valeur, percentile, tendance ; VSTOXX absent des données : indisponible
        inds = {i["cle"]: i for i in d["donnees"]["indicateurs"]}
        self.assertTrue(inds["vix"]["disponible"])
        self.assertIn(inds["vix"]["verification"], ("concordant", "divergent"))
        self.assertFalse(inds["vstoxx"]["disponible"])
        for i in inds.values():
            if i["disponible"]:
                self.assertTrue(0 <= i["percentile"] <= 100)
                self.assertIn(i["tendance"], ("hausse", "baisse", "stable", None))
        self.assertGreaterEqual(len(d["donnees"]["historique"]), 50)  # graphique sur 12 mois (hebdomadaire)
        self.assertTrue(d["donnees"]["correlations"]["paires"])
        self.assertFalse(d["meta"]["fictif"])

    def test_pays_texte_et_decomposition(self):
        self.lancer()
        d = json.loads((self.data / "risque.json").read_text(encoding="utf-8"))["donnees"]
        for code in PAYS_TEST:
            p = d["pays"][code]
            self.assertIsNotNone(p["score"], code)
            self.assertTrue(set(p["composantes"]) <= {"marche", "devise", "souverain", "macro", "geopolitique"})
            self.assertEqual(p["texte"].count(". "), 1, p["texte"])  # deux phrases
            for c in p["composantes"].values():
                self.assertTrue(0 <= c["score"] <= 100)
                self.assertTrue(c["source"])
        self.assertIn("souverain", d["pays"]["IT"]["composantes"])
        self.assertEqual(d["pays"]["IT"]["composantes"]["souverain"]["reference"], "DE")
        self.assertEqual(d["pays"]["BR"]["composantes_manquantes"], ["souverain"])
        self.assertEqual(d["pays"]["US"]["composantes"]["geopolitique"]["score"], 72)

    def test_journal_sante_historique_recap(self):
        self.lancer()
        j = json.loads((self.data / "journal" / "agent-risque.json").read_text(encoding="utf-8"))
        s = j["meta"]["sante"]
        self.assertEqual((s["agent"], s["ordre"], s["workflow"]), ("risque", 7, "agent-risque.yml"))
        self.assertTrue(s["planning"]["crons"])  # lus dans .github/workflows/agent-risque.yml
        self.assertFalse(s["degrade"], s["raisons"])
        noms = {x["nom"]: x["etat"] for x in s["sources"]}
        self.assertEqual(noms["Gemini (objections du contradicteur)"], "non configurée")
        index = json.loads((self.data / "journal" / "index.json").read_text(encoding="utf-8"))
        self.assertIn("agent-risque.json", [e["fichier"] for e in index["donnees"]])
        self.assertTrue((self.data / "historique" / "risque" / "2026-11-06.json").exists())
        recap = (self.data / "recap" / "risque-2026-11-06.md").read_text(encoding="utf-8")
        self.assertIn("Ce qui pourrait me donner tort", recap)
        self.assertIn("Objections du contradicteur", recap)

    def test_mode_horaire_reutilise_les_sources_lentes(self):
        f = FournisseurCompteur(DONNEES)
        self.lancer(f, mode="complet")
        n = f.appels["fred"]
        self.lancer(f, mode="horaire", maintenant=MAINTENANT.replace(hour=23, minute=17))
        self.assertEqual(f.appels["fred"], n, "FRED non relevé en mode horaire (moins de 20 h)")
        self.assertEqual(f.appels["cours"], 4, "Yahoo relevé à chaque exécution")
        self.assertTrue((self.data / "risque.json").exists())

    def test_source_en_panne(self):
        self.lancer()
        panne = self.tmp / "donnees"
        shutil.copytree(DONNEES, panne)
        (panne / "fred_BAMLH0A0HYM2.json").unlink()
        r = self.lancer(FournisseurTest(panne), maintenant=MAINTENANT.replace(day=7))
        self.assertTrue(r["ok"])
        etats = {v["nom"]: v["etat"] for v in r["sante"]["sources"]}
        # Dernière valeur gardée (périmée), l'indicateur reste calculé
        self.assertEqual(etats["FRED, ICE BofA US High Yield OAS (BAMLH0A0HYM2)"], "périmée")
        self.assertTrue(r["indicateurs"]["hy_us"]["disponible"])

    def test_aucune_source(self):
        vide = self.tmp / "vide"
        vide.mkdir()
        r = self.lancer(FournisseurTest(vide))
        self.assertFalse(r["ok"])
        self.assertFalse((self.data / "risque.json").exists())


class TestContradicteur(BaseRisque):
    def revues(self):
        return {r["id"]: r for r in json.loads((self.data / "signaux" / "revues.json").read_text(encoding="utf-8"))["donnees"]}

    def test_objections_par_regles(self):
        self.lancer()
        rv = self.revues()
        # Seuls les signaux d'importance moyenne ou forte, des 7 derniers jours
        self.assertNotIn("entreprises|variation_de_note|AAPL|2026-11-05", rv)
        self.assertNotIn("entreprises|nouvelle_pepite|OLD|2026-10-01", rv)
        self.assertEqual(rv["geopolitique|evenement_grave|evt-1|2026-11-04"]["ajustement"], "signal fragile")  # une seule source
        self.assertEqual(rv["macro|changement_de_phase|monde|2026-11-06"]["ajustement"], "signal fragile")  # alternance
        self.assertEqual(rv["entreprises|nouvelle_pepite|0700.HK|2026-11-05"]["ajustement"], "abaisser")  # momentum −32 %
        for r in rv.values():
            self.assertIn(r["ajustement"], K.AJUSTEMENTS)
            self.assertEqual(r["methode"], "règles")
            self.assertTrue(r["faits"] and all(x["source"] for x in r["faits"]))
            self.assertRegex(r["objection"], r"\[F\d")  # objection sourcée
        # Une revue n'est pas refaite à l'exécution suivante
        r2 = self.lancer(mode="horaire", maintenant=MAINTENANT.replace(hour=23, minute=17))
        self.assertEqual(r2["revues"], [])
        d = json.loads((self.data / "risque.json").read_text(encoding="utf-8"))["donnees"]
        self.assertTrue(d["objections"])

    def test_gemini_valide_et_rejet(self):
        appels = []

        class Reponse:
            status_code = 200

            def __init__(self, texte):
                self.text = json.dumps({"candidates": [{"content": {"parts": [{"text": texte}]}}]})

            def json(self):
                return json.loads(self.text)

        def poster(url, params=None, timeout=None, json=None):
            appels.append(url)
            import json as j
            consigne = json["contents"][0]["parts"][0]["text"]
            blocs = j.loads(consigne.split("\n\n")[-1])
            revues = []
            for b in blocs:
                if b["agent"] == "entreprises":  # chiffre inventé : rejeté
                    revues.append({"id": b["id"], "objection": "Baisse de 57 % [F1].", "faits": ["F1"], "ajustement": "abaisser"})
                else:
                    revues.append({"id": b["id"], "objection": f"{b['faits'][0]['texte']} [F1].", "faits": ["F1"], "ajustement": "maintenir"})
            return Reponse(j.dumps({"revues": revues}))

        horloge = [MAINTENANT]

        def dormir(s):
            horloge[0] += timedelta(seconds=s)

        r = self.lancer(cle="cle-de-test", poster=poster, horloge=lambda: horloge[0], dormir=dormir)
        self.assertTrue(appels)
        self.assertLessEqual(len(appels), self.config["gemini"]["appels_max_par_execution"])
        rv = self.revues()
        self.assertEqual(rv["macro|changement_de_phase|monde|2026-11-06"]["methode"], "gemini")
        self.assertEqual(rv["entreprises|nouvelle_pepite|0700.HK|2026-11-05"]["methode"], "règles")
        self.assertTrue(any("chiffres absents" in x for x in r["rapport"]["rejets"]))
        # Budget propre à l'agent risque : compteur dans data/risque/etat.json
        etat = json.loads((self.data / "risque" / "etat.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(m["appels"] for m in etat["quota_gemini"]["modeles"].values()), len(appels))


class TestPalier(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()
        self.seuils = {"Vigilance": 55, "Tension": 72, "Crise": 85}

    def ind(self, cle, famille, score):
        return {"cle": cle, "famille": famille, "disponible": True, "score": score, "poids": 10}

    def test_initial(self):
        e, attente = M.decider_palier(None, "Tension", {}, self.seuils, self.config, "2026-11-06")
        self.assertEqual((e["actuel"], attente), ("Tension", None))

    def test_deux_signaux_concordants(self):
        avant = {"actuel": "Calme", "depuis": "2026-10-01", "precedent": None}
        seul = {"a": self.ind("a", "volatilite", 90), "b": self.ind("b", "volatilite", 80), "c": self.ind("c", "credit", 30)}
        e, attente = M.decider_palier(avant, "Vigilance", seul, self.seuils, self.config, "2026-11-06")
        self.assertEqual(e["actuel"], "Calme")
        self.assertEqual(attente["vers"], "Vigilance")
        deux = {**seul, "c": self.ind("c", "credit", 60)}
        e, attente = M.decider_palier(avant, "Vigilance", deux, self.seuils, self.config, "2026-11-06")
        self.assertEqual((e["actuel"], e["precedent"], e["changement_le"], attente), ("Vigilance", "Calme", "2026-11-06", None))

    def test_palier_de(self):
        self.assertEqual(M.palier_de(54.9, self.seuils, self.config["paliers"]), "Calme")
        self.assertEqual(M.palier_de(85, self.seuils, self.config["paliers"]), "Crise")


class TestCalculs(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(C.percentile([1, 2, 3, 4], 4), 87.5)
        self.assertEqual(C.percentile([1, 2, 3, 4], 0), 0)

    def test_baisse_et_volatilite(self):
        serie = [(f"2026-01-{i:02d}", v) for i, v in enumerate([100, 110, 120, 90] * 7 + [100, 99], 1)]
        self.assertEqual(C.baisse_plus_haut(serie), round(100 * (99 / 120 - 1), 2))
        self.assertGreater(C.volatilite(serie, 21), 0)

    def test_borne_et_format(self):
        self.assertEqual(C.borne(-15, 0, -30), 50)
        self.assertEqual(C.borne(99, 0, 6), 100)
        self.assertEqual(C.fr(-2.345, 1, True), "−2,3")
        self.assertEqual(C.fr(1234.5, 1), "1 234,5")


if __name__ == "__main__":
    unittest.main()
