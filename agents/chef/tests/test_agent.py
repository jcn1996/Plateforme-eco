"""Tests du chef d'orchestre : copie de données de test (agents/chef/tests/donnees), dossier temporaire, sans
réseau ni Gemini réel. Les vrais config/ et data/ ne sont jamais lus ni modifiés."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.chef import allocation as A
from agents.chef import moteur as M
from agents.chef import suivi as S
from agents.chef import synthese as Y
from agents.chef.agent import charger_config, executer
from agents.chef.sources import FournisseurTest

DONNEES = Path(__file__).resolve().parent / "donnees"
MAINTENANT = datetime(2026, 11, 7, 22, 0, tzinfo=timezone.utc)  # un samedi
VERDICTS = {"Renforcer fortement", "Renforcer", "Neutre", "Alléger", "Éviter"}


def lire(chemin: Path):
    return json.loads(chemin.read_text(encoding="utf-8"))


def ecrire(chemin: Path, objet) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet, ensure_ascii=False), encoding="utf-8")


class Reponse:
    def __init__(self, code, corps):
        self.status_code, self._corps = code, corps
        self.text = json.dumps(corps)

    def json(self):
        return self._corps


class BaseChef(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="chef-"))
        self.data = self.tmp / "data"
        shutil.copytree(DONNEES / "data", self.data)
        self.config = charger_config()
        self.f = FournisseurTest(DONNEES)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lancer(self, mode="complet", maintenant=MAINTENANT, **kw):
        horloge = {"t": maintenant}  # horloge simulée : avance quand le code attend (limite d'appels par minute)

        def dormir(s):
            horloge["t"] += timedelta(seconds=s)
        return executer(self.f, self.config, self.data, maintenant, mode, cle_gemini=kw.pop("cle", ""), deposer=False,
                        horloge=lambda: horloge["t"], dormir=dormir, **kw)


class TestExecutionComplete(BaseChef):
    def test_sorties_et_contenu(self):
        r = self.lancer()
        self.assertTrue(r["ok"])
        chef = lire(self.data / "chef.json")
        d = chef["donnees"]
        self.assertFalse(chef["meta"]["fictif"])
        self.assertEqual(len(d["pays"]), 31)
        self.assertGreaterEqual(len(d["matieres"]), 15)
        self.assertIsNotNone(d["or"])
        self.assertEqual(len(d["obligations"]), 4)
        self.assertEqual(len(d["liquidites"]), 2)
        self.assertTrue(d["entreprises"])
        self.assertEqual(d["mention"], "Avis indicatif généré automatiquement, sans prise en compte d'un profil ou d'une situation personnelle.")
        for l in r["lignes"]:
            self.assertIn(l["verdict"], VERDICTS)
            self.assertIn(l["conviction"], ("faible", "moyenne", "forte"))
            self.assertTrue(0 <= l["score"] <= 100)
            self.assertTrue(l["donner_tort"], l["id"])
            self.assertIn(l["fleche"], ("↑", "↓", "→"))
            self.assertLessEqual(len(l["pour"]), 3)
            self.assertLessEqual(len(l["contre"]), 3)
        # une société n'apparaît qu'une fois même cotée plusieurs fois
        noms = [l["nom"].lower() for l in d["entreprises"]]
        self.assertEqual(len(noms), len(set(noms)))
        # pays attractifs : 3 meilleures sociétés
        for p in d["pays"]:
            if p["verdict"] in ("Renforcer", "Renforcer fortement"):
                self.assertTrue(1 <= len(p.get("societes") or []) <= 3)
        # briefing, alertes, historique, revue hebdomadaire (samedi), suivi, santé
        jour = "2026-11-07"
        b = lire(self.data / "chef" / f"briefing-{jour}.json")["donnees"]
        self.assertEqual(len(b["essentiel"]), 5)
        self.assertLessEqual(len(b["ou_investir"]), 5)
        self.assertEqual(b["mode"], "règles")
        self.assertIn("central", b["scenarios"])
        self.assertTrue(b["scenarios"]["alternatif"]["declencheurs"])
        self.assertTrue(any("Nova" in x["libelle"] for x in b["agenda"]), b["agenda"])
        self.assertTrue((self.data / "chef" / f"briefing-{jour}.md").exists())
        self.assertTrue((self.data / "recap" / f"chef-hebdo-{jour}.md").exists())
        self.assertTrue((self.data / "historique" / "chef" / f"{jour}.json").exists())
        al = lire(self.data / "alertes.json")
        self.assertFalse(al["meta"]["fictif"])
        self.assertLessEqual(len(al["donnees"]), 4)
        suivi = lire(self.data / "chef" / "suivi.json")
        self.assertEqual(len(suivi["donnees"]), len([l for l in r["lignes"] if l.get("symbole")]))
        j = lire(self.data / "journal" / "agent-chef.json")
        self.assertEqual(j["meta"]["sante"]["agent"], "chef")
        self.assertIn("agent-chef.json", json.dumps(lire(self.data / "journal" / "index.json")))

    def test_allocation(self):
        r = self.lancer()
        alloc = r["donnees"]["allocation"]
        ca = self.config["allocation"]
        for cle, p in alloc["profils"].items():
            total = sum(x["poids"] for x in p["lignes"])
            self.assertAlmostEqual(total, 100, delta=0.6, msg=cle)
            liq = sum(x["poids"] for x in p["lignes"] if x["classe"] == "liquidites")
            self.assertGreaterEqual(liq + 0.6, alloc["liquidites_min"], cle)
            for x in p["lignes"]:
                if x["poche"] == "satellite":
                    self.assertLessEqual(x["poids"], ca["max_ligne_satellite"] + 0.6)
                if x["type"] == "entreprises" and x["poche"] == "cœur":
                    self.fail("une entreprise ne peut être qu'un satellite")
        self.assertLessEqual(alloc["profils"]["prudent"]["classes"].get("actions", 0), alloc["profils"]["dynamique"]["classes"].get("actions", 0))

    def test_rotation_limitee(self):
        self.lancer()
        r2 = self.lancer(maintenant=MAINTENANT + timedelta(days=1, hours=-14))
        for p in r2["donnees"]["allocation"]["profils"].values():
            for x in p["lignes"]:
                if x["variation"] is not None and x["poche"] != "sortie":
                    self.assertTrue(x["variation"] == 0 or abs(x["variation"]) >= 0.05)

    def test_entree_manquante_signalee(self):
        (self.data / "inities.json").unlink()
        r = self.lancer()
        self.assertTrue(r["ok"])
        e = {x["cle"]: x for x in r["donnees"]["entrees"]}
        self.assertEqual(e["inities"]["etat"], "manquante")
        self.assertTrue(all("Initiés et super-investisseurs" in l["familles_manquantes"] for l in r["donnees"]["entreprises"]))
        self.assertTrue(any("Agent initiés" in v for v in r["donnees"]["vigilance"]))

    def test_trop_peu_d_entrees(self):
        for f in ("pays.json", "macro.json", "risque.json", "geopolitique.json", "matieres_premieres.json", "entreprises.json", "pepites.json"):
            (self.data / f).unlink()
        r = self.lancer()
        self.assertFalse(r["ok"])
        self.assertFalse((self.data / "chef.json").exists())


class TestModeLeger(BaseChef):
    def test_sans_declencheur_pas_de_recalcul(self):
        self.lancer()
        avant = lire(self.data / "chef.json")["donnees"]
        r = self.lancer("leger", MAINTENANT + timedelta(minutes=50))
        self.assertFalse(r["recalcul"])
        apres = lire(self.data / "chef.json")["donnees"]
        self.assertEqual([l["score"] for l in avant["pays"]], [l["score"] for l in apres["pays"]])

    def test_changement_de_palier_recalcule(self):
        self.lancer()
        risque = lire(self.data / "risque.json")
        risque["donnees"]["mondial"]["palier"] = "Crise"
        ecrire(self.data / "risque.json", risque)
        r = self.lancer("leger", MAINTENANT + timedelta(minutes=50))
        self.assertTrue(r["recalcul"])
        self.assertTrue(any("palier" in x for x in r["donnees"]["declencheurs"]))
        self.assertEqual(r["donnees"]["regime"]["palier"], "Crise")
        self.assertGreaterEqual(r["donnees"]["allocation"]["liquidites_min"], 20)

    def test_choc_de_marche_ne_touche_que_les_actifs_risques(self):
        self.lancer()
        avant = {l["id"]: l for l in lire(self.data / "chef.json")["donnees"]["obligations"]}
        m = lire(self.data / "marches.json")
        for x in m["donnees"]:
            if x["symbole"] == "^GSPC":
                x["variation"] = -4.2
                x["ancienne"] = False
        ecrire(self.data / "marches.json", m)
        r = self.lancer("leger", MAINTENANT + timedelta(minutes=50))
        self.assertTrue(r["recalcul"])
        self.assertTrue(any("choc" in x for x in r["donnees"]["declencheurs"]))
        apres = {l["id"]: l for l in r["donnees"]["obligations"]}
        self.assertEqual(avant, apres)


class TestMoteur(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()

    def opp(self, notes, type_="pays", coef=1.0):
        return {"id": "x", "type": type_, "familles": {f: {"note": n, "coef": coef, "texte": f, "source": "s", "agent": "pays"} for f, n in notes.items()}}

    def test_regime_tension_favorise_risque(self):
        calme = M.poids("pays", self.config, "Calme")
        tension = M.poids("pays", self.config, "Tension")
        self.assertGreater(tension["risque"] / sum(tension.values()), calme["risque"] / sum(calme.values()))
        self.assertLess(tension["tendance"] / sum(tension.values()), calme["tendance"] / sum(calme.values()))
        self.assertGreater(tension["fondamentaux"] / sum(tension.values()), calme["fondamentaux"] / sum(calme.values()))

    def test_donnees_peu_fiables_ramenees_vers_neutre(self):
        a = self.opp({f: 90 for f in self.config["poids"]["pays"]})
        b = self.opp({f: 90 for f in self.config["poids"]["pays"]}, coef=0.5)
        M.scorer(a, self.config, "Vigilance")
        M.scorer(b, self.config, "Vigilance")
        self.assertEqual(a["score"], 90)
        self.assertLess(b["score"], a["score"])
        self.assertGreater(b["score"], 50)

    def test_hysteresis(self):
        etat = {"x": {"verdict": "Neutre", "depuis": "2026-11-01", "score": 55, "candidat": None}}
        o = {"id": "x", "score": 59.0}
        M.appliquer_hysteresis(o, "Renforcer", etat, "2026-11-05", self.config)
        self.assertEqual(o["verdict"], "Neutre")
        self.assertIn("en_attente", o)
        o = {"id": "x", "score": 59.5}
        M.appliquer_hysteresis(o, "Renforcer", etat, "2026-11-05", self.config)  # même jour : toujours en attente
        self.assertEqual(o["verdict"], "Neutre")
        o = {"id": "x", "score": 59.2}
        M.appliquer_hysteresis(o, "Renforcer", etat, "2026-11-06", self.config)  # 2e jour : confirmé
        self.assertEqual(o["verdict"], "Renforcer")
        self.assertIn("2 jours", o["changement"]["explication"])
        # franchissement avec marge : changement immédiat
        o = {"id": "x", "score": 30.0}
        M.appliquer_hysteresis(o, "Éviter", etat, "2026-11-07", self.config)
        self.assertIn(o["verdict"], ("Alléger", "Éviter"))
        self.assertIn("marge", o["changement"]["explication"])
        # retour sous le seuil : le candidat est oublié
        etat = {"x": {"verdict": "Neutre", "depuis": "2026-11-01", "score": 55, "candidat": None}}
        M.appliquer_hysteresis({"id": "x", "score": 59.0}, "Renforcer", etat, "2026-11-05", self.config)
        M.appliquer_hysteresis({"id": "x", "score": 55.0}, "Neutre", etat, "2026-11-06", self.config)
        o = {"id": "x", "score": 59.0}
        M.appliquer_hysteresis(o, "Renforcer", etat, "2026-11-07", self.config)
        self.assertEqual(o["verdict"], "Neutre")

    def test_conviction(self):
        o = self.opp({"fondamentaux": 70, "valorisation": 72, "tendance": 68, "risque": 65, "cycle": 50})
        M.scorer(o, self.config, "Vigilance")
        self.assertEqual(M.conviction(o, "Renforcer", [], 1.0, self.config)["niveau"], "forte")
        self.assertEqual(M.conviction(o, "Renforcer", [], 0.8, self.config)["niveau"], "moyenne")  # donnée périmée
        obj = [{"objection": "o", "ajustement": "abaisser", "serieuse": True}]
        self.assertEqual(M.conviction(o, "Renforcer", obj, 1.0, self.config)["niveau"], "moyenne")
        # deux familles du même groupe ne comptent qu'une fois
        o2 = self.opp({"fondamentaux": 70, "resultats": 75, "valorisation": 50, "tendance": 50})
        M.scorer(o2, self.config, "Vigilance")
        self.assertEqual(len(M.conviction(o2, "Renforcer", [], 1.0, self.config)["groupes"]), 1)
        self.assertEqual(M.conviction(o, "Neutre", [], 1.0, self.config)["niveau"] in ("faible", "moyenne"), True)

    def test_extreme_exige_conviction(self):
        v, raison = M.plafonner_extreme("Renforcer fortement", {"niveau": "faible"}, self.config)
        self.assertEqual(v, "Renforcer")
        self.assertIsNotNone(raison)
        self.assertEqual(M.plafonner_extreme("Éviter", {"niveau": "forte"}, self.config)[0], "Éviter")

    def test_concentration(self):
        lignes = [{"nom": f"S{i}", "verdict": "Renforcer", "themes": ["semi"] if i < 4 else []} for i in range(8)]
        c = M.concentrations(lignes, self.config)
        self.assertEqual(c[0]["theme"], "semi")
        self.assertEqual(c[0]["part"], 50)


class TestBriefingGemini(BaseChef):
    def test_affirmations_non_sourcees_supprimees(self):
        def poster(url, params=None, timeout=None, json=None):
            rep = {"essentiel": [{"texte": "Le risque mondial reste en « Vigilance » [F1].", "faits": ["F1"]},
                                 {"texte": "La phase du cycle est stable [F2].", "faits": ["F2"]},
                                 {"texte": "Les marchés vont monter de 25 % [F1].", "faits": ["F1"]},
                                 {"texte": "Phrase sans source."},
                                 {"texte": "Les meilleures opportunités sont listées [F3].", "faits": ["F3"]},
                                 {"texte": "Le contexte reste à surveiller [F2].", "faits": ["F2"]}],
                   "vigilance": [{"texte": "Point de vigilance [F1].", "faits": ["F1"]}]}
            return Reponse(200, {"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(rep, ensure_ascii=False)}]}}]})
        r = self.lancer(cle="cle-test", poster=poster)
        b = r["briefing"]
        self.assertEqual(b["mode"], "gemini")
        textes = [x["texte"] for x in b["essentiel"]]
        self.assertNotIn("Phrase sans source.", textes)
        self.assertFalse(any("25 %" in t for t in textes))
        self.assertTrue(all("[F" not in t for t in textes))
        self.assertEqual(len(b["affirmations_supprimees"]), 2)

    def test_gemini_indisponible_version_regles(self):
        r = self.lancer(cle="cle-test", poster=lambda *a, **k: Reponse(500, {}))
        self.assertEqual(r["briefing"]["mode"], "règles")
        self.assertTrue(r["gemini"]["erreurs"])


class TestAlertes(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()

    def test_filtre_contradicteur(self):
        jour = "2026-11-07"
        sig = {"risque": [{"date": jour, "type": "changement_de_palier", "cle": "monde", "importance": "forte", "titre": "Palier"}],
               "pays": [{"date": jour, "type": "sorties_inhabituelles", "cle": "VN", "importance": "moyenne", "titre": "Vietnam : sorties"}],
               "macro": [{"date": "2026-10-20", "type": "changement_de_phase", "cle": "monde", "importance": "forte", "titre": "Ancien"}]}
        revues = [{"id": f"pays|sorties_inhabituelles|VN|{jour}", "specifique": True, "ajustement": "signal fragile", "objection": "o"}]
        al = Y.alertes(sig, revues, [], datetime(2026, 11, 7, 12, tzinfo=timezone.utc), self.config, set())
        self.assertEqual([a["titre"] for a in al], ["Palier"])
        self.assertEqual(Y.alertes({}, [], [], datetime(2026, 11, 7, tzinfo=timezone.utc), self.config, set()), [])

    def test_abaisser_reduit_importance(self):
        jour = "2026-11-07"
        sig = {"pays": [{"date": jour, "type": "sorties_inhabituelles", "cle": "VN", "importance": "moyenne", "titre": "Vietnam : sorties"}]}
        revues = [{"id": f"pays|sorties_inhabituelles|VN|{jour}", "specifique": True, "ajustement": "abaisser", "objection": "o"}]
        self.assertEqual(Y.alertes(sig, revues, [], datetime(2026, 11, 7, tzinfo=timezone.utc), self.config, set()), [])


class TestSuivi(unittest.TestCase):
    def setUp(self):
        self.cfg = charger_config()["suivi"]

    def test_mesure_et_calibration(self):
        hist = []
        lignes = [{"id": "pays-US", "type": "pays", "nom": "États-Unis", "verdict": "Renforcer", "conviction": "forte", "score": 65, "symbole": "SPY"},
                  {"id": "matiere-brent", "type": "matieres", "nom": "Brent", "verdict": "Éviter", "conviction": "faible", "score": 30, "symbole": "BZ=F"}]
        self.assertEqual(S.enregistrer(hist, lignes, "2026-01-05", self.cfg), 2)
        self.assertEqual(S.enregistrer(hist, lignes, "2026-01-06", self.cfg), 0)  # verdict inchangé : pas de nouvelle entrée
        series = FournisseurTest(DONNEES).series(["SPY", "URTH", "BZ=F", "DBC"])
        n = S.mesurer(hist, series, datetime(2026, 11, 7).date(), self.cfg)
        self.assertEqual(n, 6)  # 1, 3 et 6 mois pour chacun ; 12 mois pas encore échu
        us = hist[0]["suivi"]["3"]
        self.assertTrue(us["reussite"])  # SPY monte plus que URTH
        self.assertFalse(hist[1]["suivi"]["3"]["reussite"])  # Brent monte plus que DBC : « Éviter » raté
        fia = S.fiabilite(hist, self.cfg)
        self.assertEqual(fia["par_conviction"]["forte"]["3"]["taux_pct"], 100)
        self.assertEqual(fia["calibration"]["3"]["statut"], "insuffisant")
        # changement de verdict : nouvelle entrée
        lignes[0] = {**lignes[0], "verdict": "Neutre"}
        self.assertEqual(S.enregistrer(hist, lignes, "2026-02-01", self.cfg), 1)

    def test_calibration_a_revoir(self):
        par = {"forte": {"3": {"n": 12, "taux_pct": 40}}, "moyenne": {"3": {"n": 15, "taux_pct": 55}}, "faible": {"3": {"n": 20, "taux_pct": 50}}}
        self.assertEqual(S.calibration(par, self.cfg)["3"]["statut"], "à revoir")
        par["forte"]["3"]["taux_pct"] = 70
        par["faible"]["3"]["taux_pct"] = 45
        self.assertEqual(S.calibration(par, self.cfg)["3"]["statut"], "correcte")


class TestAllocationUnitaire(unittest.TestCase):
    def test_classe_sans_ligne_eligible_passe_en_liquidites(self):
        config = copy.deepcopy(charger_config())
        lignes = [{"id": "pays-A", "type": "pays", "nom": "A", "pays": "A", "score": 30, "verdict": "Éviter", "conviction": "forte", "themes": []},
                  {"id": "oblig", "type": "obligations", "nom": "O", "score": 60, "verdict": "Renforcer", "conviction": "moyenne", "themes": []},
                  {"id": "liq", "type": "liquidites", "nom": "L", "score": 50, "verdict": "Neutre", "conviction": "faible", "themes": []}]
        a = A.construire(lignes, "Vigilance", None, config)
        p = a["profils"]["dynamique"]
        self.assertNotIn("actions", p["classes"])
        self.assertTrue(any("liquidités" in x for x in p["avertissements"]))
        self.assertAlmostEqual(sum(x["poids"] for x in p["lignes"]), 100, delta=0.5)


if __name__ == "__main__":
    unittest.main()
