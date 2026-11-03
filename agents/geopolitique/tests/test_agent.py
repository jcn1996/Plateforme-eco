"""Tests de l'agent géopolitique (sans réseau ; Gemini simulé)."""
import json
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.commun.sortie import lire_json
from agents.geopolitique import evenements as E
from agents.geopolitique import ia
from agents.geopolitique import score as S
from agents.geopolitique.agent import DOSSIER, charger_config, executer
from agents.geopolitique.sources import FournisseurTest, agreger_export, lire_federal_register, lire_ofac, lire_rss

DONNEES = DOSSIER / "tests" / "donnees"
MAINTENANT = datetime(2026, 11, 3, 14, 5, tzinfo=timezone.utc)


def t(texte):
    return datetime.fromisoformat(texte.replace("Z", "+00:00"))


class Reponse:
    def __init__(self, code, corps):
        self.status_code, self._corps = code, corps
        self.text = json.dumps(corps) if not isinstance(corps, str) else corps

    def json(self):
        return self._corps


class GeminiSimule:
    """Répond à chaque appel : une analyse par événement du prompt, qui cite S1 et S2.
    `fabrique(evenement_id, sources)` peut remplacer l'analyse produite."""

    def __init__(self, horloge=None, fabrique=None, code=200):
        self.appels, self.horloge, self.fabrique, self.code = [], horloge, fabrique, code

    def __call__(self, url, params=None, timeout=None, json=None):
        self.appels.append(self.horloge() if self.horloge else None)
        if self.code != 200:
            return Reponse(self.code, "erreur simulée")
        prompt = json["contents"][0]["parts"][0]["text"]
        blocs = __import__("json").loads(prompt[prompt.index("Événements :\n") + len("Événements :\n"):])
        analyses = []
        for b in blocs:
            ids = [s["id"] for s in b["sources"]]
            if self.fabrique:
                analyses.append(self.fabrique(b["evenement"], b["sources"]))
                continue
            analyses.append({"evenement": b["evenement"],
                             "resume": [{"texte": "Les sources rapportent l'événement.", "sources": ids[:1]},
                                        {"texte": "Une deuxième source le confirme.", "sources": ids[1:2] or ids[:1]}],
                             "pays": b["pays_detectes"], "categorie": b["categorie_detectee"], "gravite": 2,
                             "actifs": [{"actif": "pétrole", "sens": "hausse", "texte": "Risque sur l'offre.", "sources": ids[:1]}],
                             "horizon": "jours", "confiance": "moyenne",
                             "contre": [{"texte": "Une désescalade rapide limiterait l'effet.", "sources": ids[:1]}]})
        return Reponse(200, {"candidates": [{"content": {"parts": [{"text": __import__("json").dumps({"analyses": analyses})}]}}]})


class Horloge:
    """Horloge simulée : dormir() avance le temps."""

    def __init__(self, debut):
        self.t = debut

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += timedelta(seconds=s)


class Base(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()
        self.data = Path(tempfile.mkdtemp())
        (self.data / "journal").mkdir()
        self.f = FournisseurTest(DONNEES)

    def tearDown(self):
        shutil.rmtree(self.data)

    def lancer(self, maintenant=MAINTENANT, cle="", poster=None, mode="horaire"):
        h = Horloge(maintenant)
        return executer(self.f, self.config, self.data, maintenant, mode, cle_gemini=cle, poster=poster, horloge=h, dormir=h.dormir)


# ------------------------------------------------------------------ sources

class TestSources(unittest.TestCase):
    def test_flux_rss_reels(self):
        for chemin in sorted(DONNEES.glob("rss_*.xml")):
            items = lire_rss(chemin.read_text(encoding="utf-8"))
            self.assertTrue(items, chemin.name)
            self.assertTrue(all(i["url"].startswith("http") and i["titre"] for i in items), chemin.name)
            self.assertTrue(all(i["date"] for i in items), chemin.name)

    def test_ofac_et_federal_register(self):
        actions = lire_ofac((DONNEES / "ofac.html").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(actions), 5)
        self.assertTrue(all(a["url"].startswith("https://ofac.treasury.gov/recent-actions/") for a in actions))
        self.assertRegex(actions[0]["date"], r"^\d{4}-\d{2}-\d{2}T")
        docs = lire_federal_register((DONNEES / "federal_register.json").read_text(encoding="utf-8"))
        self.assertTrue(any(d["type"] == "Presidential Document" for d in docs))

    def test_fichier_evenements_gdelt(self):
        fips = {p["fips"] for p in charger_config()["pays"].values()}
        agg = agreger_export((DONNEES / "gdelt_export.csv").read_text(encoding="utf-8"), fips)
        self.assertIn("US", agg)
        self.assertNotIn("GM", set(agg) - fips)  # seulement les pays suivis
        self.assertGreater(agg["US"]["articles"], 0)

    def test_domaine(self):
        from agents.geopolitique.sources import domaine
        self.assertEqual(domaine("https://feeds.bbci.co.uk/news/x"), "bbci.co.uk")
        self.assertEqual(domaine("https://www.theguardian.com/world/x"), "theguardian.com")


# ------------------------------------------------------------------ regroupement

class TestRegroupement(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()
        self.det = E.Detecteur(self.config)

    def test_detection(self):
        self.assertIn("US", self.det.pays_de("US strikes Iran"))
        self.assertNotIn("US", self.det.pays_de("Let us talk about it"))  # « us » en minuscules : pas les États-Unis
        self.assertEqual(self.det.categorie_de("The US-China trade war seems to have subsided"), "commerce")
        self.assertEqual(self.det.categorie_de("UK sanctions Sudanese military leaders"), "sanctions")

    def test_depeche_reprise_comptee_une_fois(self):
        arts = [{"titre": "A new cold war: hackers target fridges", "domaine": d} for d in ("ksut.org", "wcsufm.org", "kfoo.org")]
        arts.append({"titre": "Hackers hit supermarket freezers in Europe", "domaine": "bbc.co.uk"})
        self.assertEqual(E.independantes(arts), 2)

    def test_meme_evenement(self):
        arts = [{"titre": "US strikes Iran's Qeshm Island", "url": "https://a.example/1", "domaine": "a.example", "date": "2026-11-03T10:00:00Z"},
                {"titre": "Pentagon confirms strikes on Qeshm Island in Iran", "url": "https://b.example/2", "domaine": "b.example", "date": "2026-11-03T11:00:00Z"},
                {"titre": "UK sanctions Sudanese military leaders", "url": "https://c.example/3", "domaine": "c.example", "date": "2026-11-03T11:00:00Z"}]
        evts = []
        E.regrouper([E.preparer(a, self.det) for a in arts], evts, self.config, MAINTENANT)
        self.assertEqual(len(evts), 2)
        qeshm = next(e for e in evts if "IR" in e["pays"])
        self.assertEqual(len(qeshm["articles"]), 2)


# ------------------------------------------------------------------ exécution complète

class TestSansIA(Base):
    def test_version_sans_ia_signalee(self):
        r = self.lancer(mode="quotidien")
        d = lire_json(self.data / "geopolitique.json")["donnees"]
        self.assertEqual(d["mode_ia"], "sans IA")
        self.assertIn("clé GEMINI_API_KEY absente", d["avertissement_ia"])
        self.assertTrue(d["evenements"])
        self.assertTrue(all(e["gravite"] <= 3 and not e["ia"] and e["sources"] for e in d["evenements"]))
        self.assertEqual(len(d["pays"]), len(self.config["pays"]))
        self.assertTrue(all(0 <= p["score"] <= 100 for p in d["pays"].values() if p["score"] is not None))
        self.assertIn("gpr", d["indices"])
        self.assertLessEqual(len(d["indices"]["gpr"]["serie"]), 54)
        # Synthèse, historique, signaux, journal et santé
        self.assertTrue((self.data / "recap" / "geopolitique-2026-11-03.md").exists())
        self.assertTrue((self.data / "historique" / "geopolitique" / "2026-11-03.json").exists())
        self.assertIsNotNone(lire_json(self.data / "signaux" / "geopolitique.json"))
        j = lire_json(self.data / "journal" / "agent-geopolitique.json")
        s = j["meta"]["sante"]
        self.assertEqual(s["workflow"], "agent-geopolitique.yml")
        self.assertEqual(s["intervalle_min"], 60)
        gemini = next(x for x in s["sources"] if x["nom"].startswith("Gemini"))
        self.assertEqual(gemini["etat"], "non configurée")
        coup = next(x for x in s["sources"] if x["nom"].startswith("GDELT, API DOC"))
        self.assertEqual(coup["etat"], "partielle")  # requête « coup » absente des données de test
        index = lire_json(self.data / "journal" / "index.json")
        self.assertIn("agent-geopolitique.json", [e["fichier"] for e in index["donnees"]])
        self.assertTrue(r["recap"])

    def test_synthese_une_fois_par_jour(self):
        self.assertFalse(self.lancer(t("2026-11-03T05:03:00Z"))["recap"])  # avant 6 h UTC
        self.assertTrue(self.lancer(t("2026-11-03T07:03:00Z"))["recap"])   # 6 h manquée : rattrapée
        self.assertFalse(self.lancer(t("2026-11-03T08:03:00Z"))["recap"])  # déjà écrite


class TestGemini(Base):
    def test_analyse_et_cache(self):
        g = GeminiSimule()
        r1 = self.lancer(cle="cle-test", poster=g)
        self.assertGreater(r1["rapport_ia"]["analyses"], 0)
        d = lire_json(self.data / "geopolitique.json")["donnees"]
        self.assertEqual(d["mode_ia"], "gemini")
        analyses = [e for e in d["evenements"] if e["ia"]]
        for e in analyses:
            urls = {s["url"] for s in e["sources"]}
            for a in e["resume"] + e["actifs"] + e["contre"]:
                self.assertTrue(a["sources"] and set(a["sources"]) <= urls)
        # Une heure plus tard, mêmes données : les événements analysés viennent du cache
        n = len(g.appels)
        self.lancer(MAINTENANT + timedelta(hours=1), cle="cle-test", poster=g)
        appels_2 = len(g.appels) - n
        restants = [e for e in r1["etat"]["evenements"] if E.significatif(e, self.config) and not e.get("analyse")]
        self.assertLessEqual(appels_2, -(-len(restants) // self.config["gemini"]["evenements_par_appel"]))

    def test_anti_hallucination(self):
        def fabrique(eid, sources):
            ids = [s["id"] for s in sources]
            un_domaine = ids[:1]
            return {"evenement": eid,
                    "resume": [{"texte": "Fait sourcé.", "sources": un_domaine},
                               {"texte": "Affirmation inventée.", "sources": ["S99"]}],
                    "pays": ["US", "XX"], "categorie": "inconnue", "gravite": 5,
                    "actifs": [{"actif": "pétrole", "sens": "hausse", "texte": "Sans source."},
                               {"actif": "licornes", "sens": "hausse", "texte": "Actif inconnu.", "sources": un_domaine},
                               {"actif": "or", "sens": "hausse", "texte": "Une situation catastrophique.", "sources": un_domaine}],
                    "horizon": "années", "confiance": "certaine", "contre": []}
        r = self.lancer(cle="cle-test", poster=GeminiSimule(fabrique=fabrique))
        d = lire_json(self.data / "geopolitique.json")["donnees"]
        analyses = [e for e in d["evenements"] if e["ia"]]
        self.assertTrue(analyses)
        for e in analyses:
            self.assertEqual([x["texte"] for x in e["resume"]], ["Fait sourcé."])
            self.assertEqual(e["actifs"], [])                 # sans source, inconnu ou dramatisant : supprimés
            self.assertEqual(e["gravite"], 3)                # 5 avec une seule source indépendante : plafonnée
            self.assertIn("plafonnée à 3", e["note_gravite"])
            self.assertNotIn("XX", e["pays"])
            self.assertIn(e["categorie"], self.config["categories"])
            self.assertEqual((e["horizon"], e["confiance"]), ("semaines", "faible"))
        self.assertTrue(any("sans source" in s for s in r["rapport_ia"]["suppressions"]))
        self.assertTrue(any("ton non conforme" in s for s in r["rapport_ia"]["suppressions"]))

    def test_resume_sans_source_repasse_sans_ia(self):
        fab = lambda eid, sources: {"evenement": eid, "resume": [{"texte": "Rien de sourcé.", "sources": []}], "gravite": 4}
        self.lancer(cle="cle-test", poster=GeminiSimule(fabrique=fab))
        d = lire_json(self.data / "geopolitique.json")["donnees"]
        self.assertFalse(any(e["ia"] for e in d["evenements"]))
        self.assertTrue(all(e["gravite"] <= 3 for e in d["evenements"]))

    def test_gravite_4_avec_deux_sources_et_signal(self):
        def fab(eid, sources):
            par_dom = {}
            for s in sources:
                par_dom.setdefault(s["domaine"], s["id"])
            ids = list(par_dom.values())
            return {"evenement": eid, "resume": [{"texte": "Fait confirmé par deux sources.", "sources": ids[:2]}], "gravite": 4,
                    "pays": [], "categorie": None, "actifs": [], "horizon": "jours", "confiance": "moyenne", "contre": []}
        r = self.lancer(cle="cle-test", poster=GeminiSimule(fabrique=fab))
        d = lire_json(self.data / "geopolitique.json")["donnees"]
        graves = [e for e in d["evenements"] if e["gravite"] == 4]
        self.assertTrue(graves)
        self.assertTrue(all(e["sources_independantes"] >= 2 for e in graves))
        self.assertTrue(any(s["type"] == "evenement_grave" for s in r["signaux"]))
        # Pas de second signal pour le même événement
        r2 = self.lancer(MAINTENANT + timedelta(hours=1), cle="cle-test", poster=GeminiSimule(fabrique=fab))
        self.assertFalse([s for s in r2["signaux"] if s["type"] == "evenement_grave" and s["cle"] in {e["id"] for e in graves}])

    def test_gemini_indisponible(self):
        r = self.lancer(cle="cle-test", poster=GeminiSimule(code=500))
        d = lire_json(self.data / "geopolitique.json")["donnees"]
        self.assertEqual(d["mode_ia"], "sans IA")
        self.assertIn("HTTP 500", d["avertissement_ia"])
        self.assertTrue(r["sante"]["degrade"])
        self.assertTrue(any("Gemini indisponible" in x for x in r["sante"]["raisons"]))

    def test_429_suspend_une_heure(self):
        g = GeminiSimule(code=429)
        r = self.lancer(cle="cle-test", poster=g)
        self.assertTrue(r["rapport_ia"]["quota_atteint"])
        self.assertFalse(r["sante"]["degrade"] and any("Gemini" in x for x in r["sante"]["raisons"]))
        self.assertEqual(len(g.appels), 1)
        r2 = self.lancer(MAINTENANT + timedelta(minutes=30), cle="cle-test", poster=g)
        self.assertEqual(r2["rapport_ia"]["appels"], 0)
        g.code = 200
        r3 = self.lancer(MAINTENANT + timedelta(minutes=70), cle="cle-test", poster=g)
        self.assertGreater(r3["rapport_ia"]["appels"], 0)


# ------------------------------------------------------------------ quotas sur une journée complète

def evenement_synthetique(i: int, maintenant: datetime) -> dict:
    """Événement significatif (3 domaines, pays suivi), jamais analysé."""
    date = E.iso(maintenant)
    return {"id": f"evt-{i}", "categorie": "conflit", "pays": ["US"], "noyau": [], "premier": date, "dernier": date,
            "articles": [{"titre": f"Titre {i} {k}", "url": f"https://d{k}.example/{i}", "domaine": f"d{k}.example",
                          "date": date, "origine": "gdelt"} for k in range(3)]}


class TestQuotasJournee(unittest.TestCase):
    """Exécutions horaires sur plus d'un jour de quota (jour du Pacifique), avec toujours plus
    d'événements à analyser que le quota n'en permet."""

    def simuler(self, debut: datetime, heures: int, extra: list[datetime] = ()):
        config = charger_config()
        cfg = config["gemini"]
        etat, h = {}, Horloge(debut)
        g = GeminiSimule(horloge=h)
        par_execution, i = [], 0
        moments = sorted([debut + timedelta(hours=k, minutes=3) for k in range(heures)] + list(extra))
        for m in moments:
            h.t = max(h.t, m)
            quota = ia.Quota(etat, cfg, horloge=h, dormir=h.dormir)
            candidats = []
            for _ in range(12):  # 12 nouveaux événements par heure
                candidats.append(evenement_synthetique(i, m))
                i += 1
            avant = len(g.appels)
            rapport = ia.analyser(candidats, config, quota, h(), cle="cle-test", poster=g)
            par_execution.append((m, len(g.appels) - avant, rapport))
        return cfg, g, par_execution

    def verifier(self, cfg, g, par_execution):
        fuseau = ZoneInfo(cfg["fuseau_quota"])
        par_jour = {}
        for t_appel in g.appels:
            j = t_appel.astimezone(fuseau).date()
            par_jour[j] = par_jour.get(j, 0) + 1
        for j, n in par_jour.items():
            self.assertLessEqual(n, cfg["quota_jour"], f"quota du {j} dépassé : {n}")
        for m, n, _ in par_execution:
            self.assertLessEqual(n, cfg["appels_max_par_execution"])
        for k, a in enumerate(g.appels):
            dans_la_minute = [b for b in g.appels if timedelta(0) <= a - b < timedelta(seconds=60)]
            self.assertLessEqual(len(dans_la_minute), cfg["quota_minute"])
            if k:
                self.assertGreaterEqual((a - g.appels[k - 1]).total_seconds(), cfg["intervalle_min_secondes"])
        return par_jour

    def test_journee_complete_horaire(self):
        # Du 03/11 à 8 h UTC (minuit, heure du Pacifique) au 05/11 à 8 h UTC : deux jours de quota complets
        debut = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
        cfg, g, par_execution = self.simuler(debut, 48)
        par_jour = self.verifier(cfg, g, par_execution)
        self.assertEqual(len(par_jour), 2)
        # Le budget est utilisé, et réparti sur la journée (pas épuisé dès le matin)
        for n in par_jour.values():
            self.assertGreaterEqual(n, cfg["quota_jour"] - cfg["appels_max_par_execution"])
        derniere_heure = [n for m, n, _ in par_execution if m.astimezone(ZoneInfo(cfg["fuseau_quota"])).hour >= 18]
        self.assertGreater(sum(derniere_heure), 0)
        analyses = sum(r["analyses"] for _, _, r in par_execution)
        self.assertEqual(analyses, len(g.appels) * cfg["evenements_par_appel"])

    def test_lancements_manuels_et_rattrapages_en_plus(self):
        debut = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
        extra = [debut + timedelta(hours=k, minutes=30) for k in range(0, 24, 2)]  # 12 exécutions de plus
        cfg, g, par_execution = self.simuler(debut, 24, extra)
        par_jour = self.verifier(cfg, g, par_execution)
        self.assertLessEqual(sum(par_jour.values()), cfg["quota_jour"])

    def test_configuration_par_defaut_plausible(self):
        cfg = charger_config()["gemini"]
        self.assertLessEqual(cfg["appels_max_par_execution"] * 24, 24 * cfg["quota_jour"])
        self.assertGreaterEqual(cfg["intervalle_min_secondes"], 60 / cfg["quota_minute"])
        self.assertEqual(cfg["fuseau_quota"], "America/Los_Angeles")


# ------------------------------------------------------------------ score

class TestScore(unittest.TestCase):
    def test_gravite_et_anciennete(self):
        cfg = charger_config()["score"]
        e = lambda g, jours: {"pays": ["FR"], "gravite": g, "dernier": E.iso(MAINTENANT - timedelta(days=jours))}
        faible, _ = S.composante_evenements("FR", [e(1, 0)], MAINTENANT, cfg)
        fort, _ = S.composante_evenements("FR", [e(4, 0), e(3, 1)], MAINTENANT, cfg)
        ancien, _ = S.composante_evenements("FR", [e(4, 10), e(3, 11)], MAINTENANT, cfg)
        self.assertLess(faible, fort)
        self.assertLess(ancien, fort)
        self.assertLessEqual(fort, 100)

    def test_variation_et_tendance(self):
        hist = [["2026-10-25", 30], ["2026-10-27", 40], ["2026-11-02", 50]]
        self.assertEqual(S.variation_7j(hist, 55, MAINTENANT.date()), 15)  # par rapport au 27/10
        self.assertIsNone(S.variation_7j([["2026-11-01", 50]], 55, MAINTENANT.date()))
        jours, fichiers = {}, {}
        for k in range(30):
            j = (MAINTENANT.date() - timedelta(days=k)).isoformat()
            jours[j] = {"FR": {"conflits": 20 if k < 7 else 10}}
            fichiers[j] = 96
        self.assertGreater(S.composante_tendance(jours, fichiers, "FR", MAINTENANT.date()), 50)
        self.assertIsNone(S.composante_tendance({}, {}, "FR", MAINTENANT.date()))

    def test_sobriete(self):
        self.assertTrue(ia.sobre("Les droits de douane augmentent de 10 %."))
        self.assertFalse(ia.sobre("Une situation catastrophique et sans précédent."))


if __name__ == "__main__":
    unittest.main()
