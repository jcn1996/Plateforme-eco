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
from agents.chef import tendance as TD
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
        # Suivi de tendance : mesuré pour les pays (ETF), matières, entreprises et secteurs ; rubrique « Tendances fortes »
        suivis = {l["type"] for l in r["lignes"] if l.get("suivi_tendance")}
        self.assertTrue({"pays", "matieres", "entreprises", "secteurs"} <= suivis, suivis)
        self.assertTrue(d["tendances_fortes"])
        for x in d["tendances_fortes"]:
            self.assertGreaterEqual(x["force_relative"], self.config["suivi_tendance"]["premier_tiers"])
            self.assertGreater(x["perf_12_1"], 0)
            self.assertGreater(x["cours"], x["mm200"])
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
        cv = self.config["verdicts"]
        self.assertEqual((cv["marge"], cv["jours_confirmation"]), (5, 3))
        etat = {"x": {"verdict": "Neutre", "depuis": "2026-11-01", "score": 55, "candidat": None}}
        for jour, attendu in (("2026-11-05", "Neutre"), ("2026-11-05", "Neutre"), ("2026-11-06", "Neutre"), ("2026-11-07", "Renforcer")):
            o = {"id": "x", "score": 61.0}  # au-delà du seuil de 58, mais de moins de 5 points
            M.appliquer_hysteresis(o, "Renforcer", etat, jour, self.config)
            self.assertEqual(o["verdict"], attendu, jour)  # changement le 3e jour seulement
        self.assertIn("3 jours", o["changement"]["explication"])
        # franchissement avec une marge d'au moins 5 points : changement immédiat
        o = {"id": "x", "score": 27.0}
        M.appliquer_hysteresis(o, "Éviter", etat, "2026-11-08", self.config)
        self.assertIn(o["verdict"], ("Alléger", "Éviter"))
        self.assertIn("marge", o["changement"]["explication"])
        # marge de 4 points seulement : pas de changement immédiat
        etat = {"x": {"verdict": "Neutre", "depuis": "2026-11-01", "score": 55, "candidat": None}}
        o = {"id": "x", "score": 62.0}
        M.appliquer_hysteresis(o, "Renforcer", etat, "2026-11-05", self.config)
        self.assertEqual(o["verdict"], "Neutre")
        # retour sous le seuil : le candidat est oublié
        etat = {"x": {"verdict": "Neutre", "depuis": "2026-11-01", "score": 55, "candidat": None}}
        M.appliquer_hysteresis({"id": "x", "score": 59.0}, "Renforcer", etat, "2026-11-05", self.config)
        M.appliquer_hysteresis({"id": "x", "score": 59.0}, "Renforcer", etat, "2026-11-06", self.config)
        M.appliquer_hysteresis({"id": "x", "score": 55.0}, "Neutre", etat, "2026-11-07", self.config)
        o = {"id": "x", "score": 59.0}
        M.appliquer_hysteresis(o, "Renforcer", etat, "2026-11-08", self.config)
        self.assertEqual(o["verdict"], "Neutre")

    def test_conviction_exige_un_signal_solide(self):
        # Cas de « Technologies de l'information — Émergents » (09/11) : valorisation bien classée dans sa zone
        # (percentile 86) mais à peine favorable en absolu (56) ; résultats à 64 ; cycle et momentum favorables
        o = self.opp({"fondamentaux": 80.8, "valorisation": 71.2, "resultats": 63.5, "tendance": 80, "cycle": 72, "risque": 50}, "secteurs")
        o["familles"]["valorisation"]["note_absolue"] = 55.9
        M.scorer(o, self.config, "Vigilance")
        c = M.conviction(o, "Renforcer", [], 1.0, self.config)
        self.assertEqual(c["niveau"], "moyenne")
        self.assertTrue(any("signal solide" in r for r in c["raisons"]))
        # dynamique des résultats nettement favorable : conviction forte possible
        o["familles"]["resultats"]["note"] = 70
        self.assertEqual(M.conviction(o, "Renforcer", [], 1.0, self.config)["niveau"], "forte")
        # cycle et momentum seuls (avec des fondamentaux) : jamais forte
        o2 = self.opp({"fondamentaux": 75, "tendance": 85, "cycle": 80, "valorisation": 50}, "secteurs")
        M.scorer(o2, self.config, "Vigilance")
        self.assertEqual(M.conviction(o2, "Renforcer", [], 1.0, self.config)["niveau"], "moyenne")
        # contrôle de cohérence avant publication : même règle
        l = {"verdict": "Renforcer", "conviction": "forte", "familles": {"fondamentaux": {"note": 80}, "tendance": {"note": 80}, "cycle": {"note": 72},
                                                                       "valorisation": {"note": 71, "note_absolue": 56}}}
        self.assertIsNotNone(M.controle_coherence(l, self.config))
        self.assertEqual(l["conviction"], "moyenne")

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


def poster_ok(url, params=None, timeout=None, json=None):
    rep = {"essentiel": [{"texte": f"{x} reste à suivre [F1].", "faits": ["F1"]} for x in ("Le risque", "Le cycle", "Le panorama", "Le marché", "Le contexte")],
           "vigilance": [{"texte": "Point de vigilance [F1].", "faits": ["F1"]}]}
    return Reponse(200, {"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(rep, ensure_ascii=False)}]}}]})


def poster_503(*a, **k):
    return Reponse(503, {"error": {"message": "The model is overloaded."}})


class TestRedactionGemini(BaseChef):
    """Gemini ne sert qu'à la rédaction : son échec est une information (« rédaction par règles »), jamais une
    dégradation du chef d'orchestre ; nouvelle tentative 30 minutes plus tard."""

    def source_gemini(self):
        s = lire(self.data / "journal" / "agent-chef.json")["meta"]["sante"]
        return s, next(x for x in s["sources"] if x["nom"].startswith("Gemini"))

    def test_503_information_sans_degradation(self):
        r = self.lancer(cle="cle-test", poster=poster_503)
        self.assertEqual(r["briefing"]["mode"], "règles")
        self.assertFalse(r["sante"]["degrade"], r["sante"]["raisons"])
        s, g = self.source_gemini()
        self.assertEqual(g["etat"], "information")
        self.assertIn("rédaction par règles", g["detail"])
        self.assertIn("22:30", g["detail"])
        self.assertFalse(any(r_.startswith("Gemini") for r_ in s["raisons"]))
        self.assertEqual(s["sources_total"], sum(1 for x in s["sources"] if x["etat"] not in ("non configurée", "information")))
        self.assertEqual(r["etat"]["redaction_en_attente"]["apres"], "2026-11-07T22:30:00Z")
        self.assertIn("nouvelle tentative de rédaction vers 22:30 UTC", r["briefing"]["raison_regles"])

    def test_reprise_reussie_30_minutes_plus_tard(self):
        self.lancer(cle="cle-test", poster=poster_503)
        chef_avant = lire(self.data / "chef.json")
        appels = []

        def poster(*a, **k):
            appels.append(1)
            return poster_ok(*a, **k)
        r = self.lancer("redaction", MAINTENANT + timedelta(minutes=10), cle="cle-test", poster=poster)
        self.assertEqual(r["reprise"]["etat"], "en attente")
        self.assertFalse(appels, "pas d'appel avant l'heure prévue")
        r = self.lancer("redaction", MAINTENANT + timedelta(minutes=31), cle="cle-test", poster=poster)
        self.assertEqual(r["reprise"]["etat"], "réussie")
        b = lire(self.data / "chef" / "briefing-2026-11-07.json")["donnees"]
        self.assertEqual(b["mode"], "gemini")
        self.assertEqual(b["reprise"]["tentative"], 1)
        self.assertIsNone(b["raison_regles"])
        self.assertIn("Gemini", (self.data / "chef" / "briefing-2026-11-07.md").read_text(encoding="utf-8"))
        chef = lire(self.data / "chef.json")
        self.assertEqual(chef["donnees"]["synthese"]["essentiel"][0], b["essentiel"][0]["texte"])
        self.assertEqual(chef["meta"]["genere_le"], chef_avant["meta"]["genere_le"], "données inchangées : date des données conservée")
        self.assertEqual(chef["donnees"]["pays"], chef_avant["donnees"]["pays"])
        self.assertNotIn("redaction_en_attente", r["etat"])
        s, g = self.source_gemini()
        self.assertEqual(g["etat"], "ok")
        self.assertFalse(s["degrade"])
        self.assertEqual(s["derniere_execution"], "2026-11-07T22:31:00Z")
        r = self.lancer("redaction", MAINTENANT + timedelta(minutes=45), cle="cle-test", poster=poster)
        self.assertEqual(r["reprise"]["etat"], "rien à faire")

    def test_reprises_en_echec_puis_abandon(self):
        self.lancer(cle="cle-test", poster=poster_503)
        r = self.lancer("redaction", MAINTENANT + timedelta(minutes=31), cle="cle-test", poster=poster_503)
        self.assertEqual(r["reprise"]["etat"], "échec")
        self.assertEqual(r["etat"]["redaction_en_attente"]["apres"], "2026-11-07T23:01:00Z")
        self.assertFalse(r["sante"]["degrade"])
        r = self.lancer("redaction", MAINTENANT + timedelta(minutes=62), cle="cle-test", poster=poster_503)
        self.assertEqual(r["reprise"]["etat"], "échec")
        self.assertNotIn("redaction_en_attente", r["etat"])
        b = lire(self.data / "chef" / "briefing-2026-11-07.json")["donnees"]
        self.assertEqual(b["mode"], "règles")
        self.assertIn("plus de nouvelle tentative", b["raison_regles"])
        s, g = self.source_gemini()
        self.assertEqual(g["etat"], "information")
        self.assertFalse(s["degrade"])

    def test_mise_a_jour_legere_reprend_la_redaction(self):
        self.lancer(cle="cle-test", poster=poster_503)
        r = self.lancer("leger", MAINTENANT + timedelta(minutes=50), cle="cle-test", poster=poster_ok)
        self.assertEqual(r["briefing"]["mode"], "gemini")
        self.assertFalse(r["sante"]["degrade"])

    def test_pas_de_reprise_sans_cle(self):
        r = self.lancer()
        self.assertNotIn("redaction_en_attente", r["etat"])
        _, g = self.source_gemini()
        self.assertEqual(g["etat"], "non configurée")


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


class TestCorrectionsQualite(BaseChef):
    """Corrections après la première exécution : holdings et fonds, risque frein, momentum, contradicteur,
    alertes, Gemini, cohérence, panorama."""

    def test_holdings_exclues(self):
        r = self.lancer()
        d = r["donnees"]
        tickers = {l["cle"] for l in d["entreprises"]}
        self.assertNotIn("INVE-B.ST", tickers)
        self.assertIn("INVE-B.ST", {x["ticker"] for x in d["exclues"]})
        for p in d["pays"]:
            self.assertNotIn("INVE-B.ST", {s["ticker"] for s in p.get("societes") or []})
        self.assertNotIn("Investor", json.dumps(lire(self.data / "alertes.json"), ensure_ascii=False))

    def test_objection_sur_la_bonne_entite(self):
        r = self.lancer()
        ae = next(l for l in r["donnees"]["pays"] if l["cle"] == "AE")
        de = next(l for l in r["donnees"]["pays"] if l["cle"] == "DE")
        for o in ae.get("objections") or []:
            self.assertNotIn("Allemagne", o["objection"])
            self.assertNotIn("EWG", o["objection"])
        self.assertTrue(any("Émirats" in o["objection"] for o in ae.get("objections") or []))
        for o in de.get("objections") or []:
            self.assertNotIn("Émirats", o["objection"])

    def test_objection_par_entite_v3(self):
        revue = {"id": "geopolitique|evenement_grave|e|2026-11-06", "specifique": True, "ajustement": "signal fragile", "objection": "global",
                 "signal": {"agent": "geopolitique", "type": "evenement_grave", "cle": "e", "date": "2026-11-06", "titre": "t"},
                 "par_entite": {"AE": {"objection": "Objections spécifiques : point AE [F2].", "ajustement": "abaisser"}}}
        sig = {"geopolitique": [{"type": "evenement_grave", "cle": "e", "date": "2026-11-06", "pays": ["DE", "AE"]}]}
        res = M.objections_par_cible([revue], sig, {}, "2026-11-07", self.config, {"DE": "Allemagne", "AE": "Émirats arabes unis"})
        self.assertEqual(res["pays-AE"][0]["objection"], "Objections spécifiques : point AE.")
        self.assertEqual(res["pays-AE"][0]["ajustement"], "abaisser")
        self.assertNotIn("pays-DE", res)  # aucune objection propre à l'Allemagne dans cette revue

    def test_alertes_filtrees(self):
        from agents.chef import univers as U
        from agents.chef import entrees as E
        from agents.chef.agent import alerte_admissible
        ctx = U.Contexte(E.charger(self.data, self.config, MAINTENANT), self.config, self.data)
        note = next(e["ticker"] for e in ctx.entreprises if e.get("note") is not None and not U.est_vehicule(ctx, e))
        cas = [({"cle": "X", "titre": "Third Point LLC déclare 100,0 % de Third Point Private Capital Income Fund (13D)"}, False),
               ({"cle": "NONE", "titre": "Carlyle Credit Solutions : 3 dirigeants achètent sur le marché en 30 jours"}, False),
               ({"cle": "ZZZZ", "titre": "Société inconnue : 3 dirigeants achètent"}, False),
               ({"cle": "INVE-B.ST", "titre": "Investor AB : 3 dirigeants achètent"}, False),
               ({"cle": note, "titre": "Société : 3 dirigeants achètent sur le marché en 30 jours"}, True)]
        for s, attendu in cas:
            self.assertEqual(alerte_admissible(ctx, "inities", s, self.config)[0], attendu, s["titre"])
        self.assertTrue(alerte_admissible(ctx, "macro", {"titre": "x"}, self.config)[0])

    def test_coherence_et_conviction_forte(self):
        r = self.lancer()
        for l in r["lignes"]:
            if l["conviction"] == "forte" and M.DIRECTION[l["verdict"]] == 1:
                pos = [f for f, x in l["familles"].items() if x["note"] >= 60 and f not in ("risque", "geopolitique")
                       and not (f == "tendance" and l.get("tendance_excessive"))]
                self.assertGreaterEqual(len(pos), 3, l["nom"])
            if l.get("tendance_excessive") and M.DIRECTION[l["verdict"]] == 1:
                self.assertNotEqual(l["conviction"], "forte", l["nom"])
                self.assertTrue(any("Tendance forte mais en excès" in o["objection"] for o in l["objections"]), l["nom"])

    def test_pays_jamais_recommande_par_le_seul_risque(self):
        r = self.lancer()
        for l in r["donnees"]["pays"]:
            for f in ("risque", "geopolitique"):
                if f in l["familles"]:
                    self.assertLessEqual(l["familles"][f]["note"], self.config["risque_frein"]["plafond"])
            if M.DIRECTION[l["verdict"]] == 1 and l["score"] >= 58:
                self.assertTrue(any(l["familles"].get(f, {}).get("note", 0) >= 60 for f in ("fondamentaux", "valorisation", "tendance", "flux")), l["nom"])

    def test_panorama(self):
        r = self.lancer()
        p = r["donnees"]["panorama"]
        cp = self.config["panorama"]
        ent = p["entreprises"]
        self.assertGreaterEqual(len(ent), cp["entreprises_min"])
        from collections import Counter
        self.assertLessEqual(max(Counter(x["secteur"] for x in ent).values()), cp["max_par_secteur"])
        self.assertLessEqual(max(Counter(x["pays"] for x in ent).values()), cp["max_par_pays"])
        self.assertGreaterEqual(len({x["secteur"] for x in ent}), cp["min_secteurs"])
        self.assertGreaterEqual(len({x["pays"] for x in ent}), cp["min_pays"])
        self.assertLessEqual(len(p["pays"]), 5)
        self.assertLessEqual(len(p["matieres"]), 3)
        self.assertIsNotNone(p["or"])
        self.assertEqual(len(p["obligations"]), 4)
        self.assertEqual(len(p["liquidites"]), 2)
        self.assertLessEqual(len(p["top"]), 5)
        self.assertLessEqual(max(Counter(x["type"] for x in p["top"]).values()), 3)
        cle = [(x["a_surveiller"], -x["score"]) for x in p["pays"]]
        self.assertEqual(cle, sorted(cle))  # par score, les lignes « à surveiller » après les autres
        lignes = {l["id"]: l for l in r["lignes"]}
        for x in p["top"]:
            l = lignes[x["id"]]
            self.assertFalse((l.get("objection") or {}).get("serieuse"), x["nom"])
            self.assertFalse(l.get("tendance_excessive"), x["nom"])
        self.assertLessEqual(max(Counter(x["type"] for x in p["a_surveiller"]).values() or [0]), cp["a_surveiller_par_type"])
        # le briefing résume par catégorie
        textes = [x["texte"] for x in r["briefing"]["essentiel"]]
        for debut in ("Pays :", "Matières premières :", "Obligations et liquidités :", "Secteurs :"):
            self.assertTrue(any(t.startswith(debut) for t in textes), debut)

    def test_raison_sans_gemini_et_chaine_de_secours(self):
        r = self.lancer()
        self.assertIn("GEMINI_API_KEY absente", r["briefing"]["raison_regles"])
        self.assertIn("GEMINI_API_KEY absente", (self.data / "chef" / "briefing-2026-11-07.md").read_text(encoding="utf-8"))
        self.assertIn("GEMINI_API_KEY absente", json.dumps(lire(self.data / "journal" / "agent-chef.json"), ensure_ascii=False))
        appels = []

        def poster(url, params=None, timeout=None, json=None):
            appels.append(url)
            if "flash-latest" in url:
                return Reponse(503, {})
            rep = {"essentiel": [{"texte": f"Phrase {i} [F1].", "faits": ["F1"]} for i in range(5)], "vigilance": []}
            return Reponse(200, {"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(rep)}]}}]})
        self.tearDown()
        self.setUp()
        r = self.lancer(cle="cle-test", poster=poster)
        self.assertEqual(r["briefing"]["mode"], "gemini")
        self.assertEqual(r["briefing"]["modele"], "gemini-3.5-flash-lite")  # modèle de secours
        self.assertTrue(any("flash-latest" in u for u in appels))


class TestMoteurRegles(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()

    def opp(self, notes, type_="pays"):
        return {"id": "x", "type": type_, "familles": {f: {"note": n, "coef": 1.0, "texte": f, "source": "s", "agent": "pays"} for f, n in notes.items()}}

    def test_risque_frein(self):
        o = self.opp({"risque": 95, "geopolitique": 95, "fondamentaux": 52, "valorisation": 50, "tendance": 50, "cycle": 70})
        M.appliquer_frein_risque(o, self.config)
        self.assertEqual(o["familles"]["risque"]["note"], 55)
        self.assertEqual(M.exiger_moteur(o, "Renforcer", self.config)[0], "Neutre")
        o["familles"]["valorisation"]["note"] = 70
        self.assertEqual(M.exiger_moteur(o, "Renforcer", self.config)[0], "Renforcer")
        # obligations : le palier de risque reste un moteur (valeur refuge)
        ob = self.opp({"risque": 75}, "obligations")
        M.appliquer_frein_risque(ob, self.config)
        self.assertEqual(ob["familles"]["risque"]["note"], 75)

    @staticmethod
    def serie(debut: float, fin: float, dernier_mois: float = 0.0, n: int = 300) -> list:
        """Série quotidienne régulière de `debut` à `fin`, puis `dernier_mois` % sur les 21 dernières séances."""
        from datetime import date as d_, timedelta as td_
        j0 = d_(2025, 9, 1)
        pts = []
        for i in range(n):
            x = debut + (fin - debut) * min(i, n - 22) / (n - 22)
            if i >= n - 22:
                x = fin * (1 + dernier_mois / 100 * (i - (n - 22)) / 21)
            pts.append([(j0 + td_(days=round(i * 365 * 1.2 / n))).isoformat(), round(x, 4)])
        return pts

    def test_mesures_tendance(self):
        m = TD.mesures(self.serie(100, 150), self.config)
        self.assertGreater(m["perf_12_1"], 30)
        self.assertTrue(m["au_dessus_mm200"])
        self.assertLess(m["acceleration"] or 0, 1)
        baisse = TD.mesures(self.serie(150, 100), self.config)
        self.assertLess(baisse["perf_12_1"], 0)
        self.assertFalse(baisse["au_dessus_mm200"])
        self.assertIsNone(TD.mesures(self.serie(100, 150)[-100:], self.config))  # moins de 12 mois d'historique

    def test_tendance_forte_saine_ou_en_exces(self):
        cfg = self.config
        opps = []
        for i, (deb, fin) in enumerate([(100, 180), (100, 140), (100, 120), (100, 105), (100, 95), (100, 90)]):
            o = self.opp({"tendance": 55, "valorisation": 60, "fondamentaux": 62, "cycle": 60}, "matieres")
            o.update({"id": f"m{i}", "nom": f"M{i}", "symbole": f"S{i}"})
            opps.append(o)
        series = {f"S{i}": self.serie(d, f) for i, (d, f) in enumerate([(100, 180), (100, 140), (100, 120), (100, 105), (100, 95), (100, 90)])}
        TD.preparer(opps, series, cfg)
        forte, moyenne, faible = opps[0], opps[2], opps[5]
        self.assertTrue(forte["suivi_tendance"]["forte"])
        self.assertTrue(forte["tendance_forte"])
        self.assertFalse(forte["tendance_excessive"])
        self.assertEqual(forte["familles"]["tendance"]["note"], cfg["suivi_tendance"]["note_plancher_forte"])  # signal positif
        self.assertIsNone(TD.verifier(forte, "2026-11-07", cfg))
        self.assertFalse(moyenne["suivi_tendance"]["forte"])
        self.assertFalse(faible["suivi_tendance"]["positive"])
        # Même hausse, mais valorisation tendue (au-delà du 70e percentile) : excès → objection sérieuse
        o = opps[1]
        o["familles"]["valorisation"]["note_absolue"] = 20
        TD.evaluer(o, cfg)
        self.assertTrue(o["tendance_excessive"])
        obj = TD.verifier(o, "2026-11-07", cfg)
        self.assertTrue(obj["serieuse"])
        self.assertIn("valorisation tendue", obj["objection"])
        M.scorer(o, cfg, "Vigilance")
        self.assertNotIn("marche", M.groupes_concordants(o, 1, cfg))
        self.assertNotEqual(M.conviction(o, "Renforcer", [obj], 1.0, cfg)["niveau"], "forte")
        # Positionnement encombré (CFTC au 90e percentile) et accélération parabolique
        o = opps[0]
        o["familles"]["flux"] = {"note": 40, "coef": 1.0, "texte": "CFTC", "source": "s", "agent": "mp", "percentile_cftc": 95}
        TD.evaluer(o, cfg)
        self.assertTrue(any("positionnement encombré" in x for x in o["suivi_tendance"]["exces"]))
        o["familles"].pop("flux")
        o["suivi_tendance"].update({"perf_1m": 25.0, "vol_mensuelle": 5.0, "acceleration": 5.0})
        TD.evaluer(o, cfg)
        self.assertTrue(any("parabolique" in x for x in o["suivi_tendance"]["exces"]))
        # Rubrique « Tendances fortes » : niveau d'invalidation = moyenne 200 jours
        tf = TD.tendances_fortes([dict(x, verdict="Neutre", score=60) for x in opps], cfg)
        self.assertEqual({x["id"] for x in tf}, {x["id"] for x in opps if x["suivi_tendance"]["forte"]})
        for x in tf:
            self.assertEqual(x["niveau_invalidation"], x["mm200"])
            self.assertGreater(x["distance_invalidation_pct"], 0)

    def test_controle_coherence(self):
        l = {"verdict": "Renforcer", "conviction": "forte", "familles": {"fondamentaux": {"note": 70}, "valorisation": {"note": 65},
                                                                       "risque": {"note": 90}, "cycle": {"note": 55}}}
        self.assertIsNotNone(M.controle_coherence(l, self.config))
        self.assertEqual(l["conviction"], "moyenne")
        l2 = {"verdict": "Renforcer", "conviction": "forte", "familles": {"fondamentaux": {"note": 70}, "valorisation": {"note": 65}, "flux": {"note": 61}}}
        self.assertIsNone(M.controle_coherence(l2, self.config))
        self.assertEqual(l2["conviction"], "forte")


class TestSecteurs(BaseChef):
    def test_secteurs_par_zone(self):
        from collections import Counter
        r = self.lancer()
        d = r["donnees"]
        sect = d["secteurs"]
        self.assertTrue(sect)
        par_zone = Counter(l["zone_secteur"] for l in sect)
        self.assertEqual(par_zone["monde"], 11)
        self.assertTrue(all(n <= 11 for n in par_zone.values()))
        self.assertEqual(set(par_zone) - set(self.config["secteurs"]["zones"]), set())
        tech_us = next(l for l in sect if l["id"] == "secteur-etats_unis-technologie")
        self.assertEqual(tech_us["symbole"], "XLK")
        self.assertIn("XLK", tech_us["familles"]["tendance"]["texte"])
        self.assertIn("flux", tech_us["familles"])  # historique SSGA : flux disponibles d'emblée
        self.assertIn("cycle", tech_us["familles"])
        self.assertIn("valorisation", tech_us["familles"])
        for l in sect:
            self.assertIn(l["verdict"], VERDICTS)
            self.assertGreaterEqual(l["nb_societes"], self.config["secteurs"]["societes_min"])
            if l["zone_secteur"] == "emergents":
                self.assertIsNone(l.get("symbole"))
                if "tendance" in l["familles"]:
                    self.assertIn("sociétés", l["familles"]["tendance"]["texte"])
        self.assertTrue(list((self.data / "chef" / "flux_secteurs").glob("*.json")))
        j = lire(self.data / "journal" / "agent-chef.json")
        noms = [s["nom"] for s in j["meta"]["sante"]["sources"]]
        self.assertTrue(any("ETF sectoriels" in n for n in noms))

    def test_rotation_complete(self):
        from agents.entreprises.univers import GICS
        rot = self.config["secteurs"]["rotation"]
        for phase in self.config["cycle"]["phases"]:
            self.assertEqual(set(rot[phase]), set(GICS), phase)
        self.assertEqual(set(self.config["secteurs"]["etf"]), set(GICS))
        self.assertEqual(set(self.config["secteurs"]["sensibilite"]), set(GICS))

    def test_panorama_briefing_allocation(self):
        r = self.lancer()
        d = r["donnees"]
        p = d["panorama"]
        self.assertLessEqual(len(p["secteurs"]), 3)
        self.assertEqual(len({x["nom"].split(" — ")[0] for x in p["secteurs"]}), len(p["secteurs"]))
        self.assertTrue(any(x["texte"].startswith("Secteurs :") for x in r["briefing"]["essentiel"]))
        self.assertIn("Secteurs (top 3", (self.data / "chef" / "briefing-2026-11-07.md").read_text(encoding="utf-8"))
        lignes = {l["id"]: l for l in r["lignes"]}
        cs = self.config["secteurs"]
        for prof in d["allocation"]["profils"].values():
            sect = [x for x in prof["lignes"] if x["type"] == "secteurs" and x["poids"] > 0]
            self.assertLessEqual(len(sect), cs["allocation_max_lignes"])
            self.assertEqual(len({lignes[x["id"]]["secteur"] for x in sect}), len(sect))  # une zone par secteur
            for x in sect:
                self.assertTrue(lignes[x["id"]].get("symbole"))
                self.assertIn(lignes[x["id"]]["verdict"], ("Renforcer", "Renforcer fortement"))
            self.assertAlmostEqual(sum(x["poids"] for x in prof["lignes"]), 100, delta=0.6)

    def test_secteur_sans_signal_moteur_reste_neutre(self):
        o = {"id": "s", "type": "secteurs", "familles": {f: {"note": n, "coef": 1, "texte": f, "source": "s", "agent": "x"}
                                                         for f, n in {"cycle": 90, "risque": 85, "fondamentaux": 52}.items()}}
        self.assertEqual(M.exiger_moteur(o, "Renforcer", self.config)[0], "Neutre")


class TestTraderSecteurs(unittest.TestCase):
    def test_lignes_secteurs_lues_par_le_trader(self):
        from agents.trader import strategie as T
        chef = {"secteurs": [{"id": "secteur-monde-technologie", "type": "secteurs", "symbole": "IXN", "nom": "Tech — Monde", "devise": "USD"}]}
        self.assertIn("secteur-monde-technologie", T.lignes_chef(chef))
        self.assertEqual(T.CLASSE_DE["secteurs"], "actions")
        self.assertEqual(T.supports_de(chef["secteurs"][0], {"supports": {}})[0]["symbole"], "IXN")


class TestAntiGirouetteHistoriqueReel(unittest.TestCase):
    """Non-régression : scores réels des 7 secteurs dont le verdict a changé le 09/11/2026 à 8 h 33 (avant l'anti-girouette
    renforcé). Avec 5 points de marge ou 3 jours de suite, seul « Énergie — Monde » (seuil franchi de plus de 5 points) change."""

    SEQUENCES = {  # (jour, score) de chaque exécution, du premier verdict (08/11) à l'exécution du 09/11
        "secteur-monde-energie": [("2026-11-08", 56.9), ("2026-11-08", 57.4), ("2026-11-09", 64.2)],
        "secteur-etats_unis-materiaux": [("2026-11-08", 59.0), ("2026-11-08", 55.0), ("2026-11-09", 55.6)],
        "secteur-etats_unis-sante": [("2026-11-08", 56.6), ("2026-11-08", 59.3), ("2026-11-09", 60.8)],
        "secteur-europe-finance": [("2026-11-08", 57.9), ("2026-11-08", 58.7), ("2026-11-09", 58.7)],
        "secteur-europe-communication": [("2026-11-08", 41.0), ("2026-11-08", 45.3), ("2026-11-09", 45.3)],
        "secteur-emergents-conso-discretionnaire": [("2026-11-08", 42.4), ("2026-11-08", 44.4), ("2026-11-09", 44.4)],
        "secteur-emergents-finance": [("2026-11-08", 58.5), ("2026-11-08", 57.5), ("2026-11-09", 57.5)],
    }

    def rejouer(self, config):
        etat, changes = {}, []
        for i, seq in self.SEQUENCES.items():
            for jour, score in seq:
                o = {"id": i, "score": score}
                deja = i in etat
                M.appliquer_hysteresis(o, M.verdict_de(score, config), etat, jour, config)
                if deja and o.get("changement"):
                    changes.append(i)
        return changes

    def test_un_seul_changement_avec_les_regles_actuelles(self):
        config = charger_config()
        self.assertEqual(self.rejouer(config), ["secteur-monde-energie"])
        ancien = copy.deepcopy(config)
        ancien["verdicts"].update({"marge": 3, "jours_confirmation": 2})
        self.assertGreaterEqual(len(self.rejouer(ancien)), 5)  # l'ancien réglage changeait la plupart de ces verdicts
