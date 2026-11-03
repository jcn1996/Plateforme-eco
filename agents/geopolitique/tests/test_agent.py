"""Tests de l'agent géopolitique (sans réseau ; Gemini et GDELT simulés)."""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.commun.sortie import lire_json
from agents.commun.telechargement import ErreurSource
from agents.geopolitique import evenements as E
from agents.geopolitique import ia
from agents.geopolitique import score as S
from agents.geopolitique.agent import DOSSIER, charger_config, executer, requetes_groupees
from agents.geopolitique.sources import ClientGdelt, FournisseurTest, agreger_export, lire_federal_register, lire_ofac, lire_rss

DONNEES = DOSSIER / "tests" / "donnees"
MAINTENANT = datetime(2026, 11, 3, 14, 5, tzinfo=timezone.utc)
PACIFIQUE = ZoneInfo("America/Los_Angeles")


def t(texte):
    return datetime.fromisoformat(texte.replace("Z", "+00:00"))


class Reponse:
    def __init__(self, code, corps, entetes=None):
        self.status_code, self._corps = code, corps
        self.text = json.dumps(corps) if not isinstance(corps, str) else corps
        self.headers = entetes or {}

    def json(self):
        return self._corps


def analyse_type(eid, sources):
    ids = [s["id"] for s in sources]
    return {"evenement": eid,
            "resume": [{"texte": "Les sources rapportent l'événement.", "sources": ids[:1]},
                       {"texte": "Une deuxième source le confirme.", "sources": ids[1:2] or ids[:1]}],
            "pays": [], "categorie": None, "gravite": 2,
            "actifs": [{"actif": "pétrole", "sens": "hausse", "texte": "Un risque pèse sur l'offre.", "sources": ids[:1]}],
            "horizon": "jours", "confiance": "moyenne",
            "contre": [{"texte": "Une désescalade rapide limiterait l'effet.", "sources": ids[:1]}]}


class GeminiSimule:
    """Gemini simulé. `scenario(modele, n)` renvoie, pour le n-ième appel (1, 2…) à un modèle, None
    (réponse normale) ou (code, corps) ; `fabrique(evenement_id, sources)` remplace l'analyse produite."""

    def __init__(self, horloge=None, fabrique=None, scenario=None):
        self.appels, self.horloge, self.fabrique, self.scenario = [], horloge, fabrique or analyse_type, scenario
        self.par_modele = {}

    def __call__(self, url, params=None, timeout=None, json=None):
        modele = url.split("/models/")[1].split(":")[0]
        self.par_modele[modele] = self.par_modele.get(modele, 0) + 1
        self.appels.append((self.horloge() if self.horloge else None, modele))
        erreur = self.scenario(modele, self.par_modele[modele]) if self.scenario else None
        if erreur:
            return Reponse(erreur[0], erreur[1])
        prompt = json["contents"][0]["parts"][0]["text"]
        blocs = __import__("json").loads(prompt[prompt.index("Événements :\n") + len("Événements :\n"):])
        analyses = [self.fabrique(b["evenement"], b["sources"]) for b in blocs]
        return Reponse(200, {"candidates": [{"content": {"parts": [{"text": __import__("json").dumps({"analyses": analyses})}]}}]})


SURCHARGE = (503, '{"error": {"code": 503, "message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}}')
QUOTA_JOUR = (429, '{"error": {"code": 429, "message": "You exceeded your current quota: GenerateRequestsPerDayPerProjectPerModel-FreeTier", "status": "RESOURCE_EXHAUSTED"}}')
QUOTA_MINUTE = (429, '{"error": {"code": 429, "message": "Quota exceeded: GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "details": [{"retryDelay": "20s"}]}}')


class Horloge:
    """Horloge simulée : dormir() avance le temps."""

    def __init__(self, debut):
        self.t = debut
        self.attentes = []

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.attentes.append(s)
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
        self.horloge = Horloge(maintenant)
        return executer(self.f, self.config, self.data, maintenant, mode, cle_gemini=cle, poster=poster,
                        horloge=self.horloge, dormir=self.horloge.dormir)

    def publics(self):
        return lire_json(self.data / "geopolitique.json")["donnees"]


# ------------------------------------------------------------------ sources

class TestSources(unittest.TestCase):
    def test_flux_rss_reels(self):
        for chemin in sorted(DONNEES.glob("rss_*.xml")):
            items = lire_rss(chemin.read_text(encoding="utf-8"))
            self.assertTrue(items, chemin.name)
            self.assertTrue(all(i["url"].startswith("http") and i["titre"] and i["date"] for i in items), chemin.name)

    def test_ofac_et_federal_register(self):
        actions = lire_ofac((DONNEES / "ofac.html").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(actions), 5)
        self.assertTrue(all(a["url"].startswith("https://ofac.treasury.gov/recent-actions/") for a in actions))
        docs = lire_federal_register((DONNEES / "federal_register.json").read_text(encoding="utf-8"))
        self.assertTrue(any(d["type"] == "Presidential Document" for d in docs))

    def test_fichier_evenements_gdelt(self):
        fips = {p["fips"] for p in charger_config()["pays"].values()}
        agg = agreger_export((DONNEES / "gdelt_export.csv").read_text(encoding="utf-8"), fips)
        self.assertIn("US", agg)
        self.assertTrue(set(agg) <= fips)

    def test_requetes_groupees(self):
        g = charger_config()["gdelt"]
        groupes = requetes_groupees(g["requetes"], g["longueur_max_requete"])
        self.assertTrue(groupes[0].startswith("(sanctions OR embargo"))
        self.assertLess(len(groupes), len(g["requetes"]))  # moins de requêtes qu'une par thème
        self.assertTrue(all(len(q) <= g["longueur_max_requete"] and q.count("(") == 1 for q in groupes))
        self.assertTrue(any('"strait of hormuz"' in q for q in groupes))
        attendus = {t.strip() for r in g["requetes"].values() for t in r.strip("()").split(" OR ")}
        obtenus = {t for q in groupes for t in q.strip("()").split(" OR ")}
        self.assertEqual(obtenus, attendus)  # aucun terme perdu


class SessionSimulee:
    def __init__(self, reponses):
        self.reponses, self.appels = list(reponses), []

    def get(self, url, params=None, timeout=None):
        self.appels.append(params)
        return self.reponses.pop(0)


class TestClientGdelt(unittest.TestCase):
    cfg = {"delai_entre_requetes_secondes": 6, "essais": 4, "attentes_reprise_secondes": [10, 20, 40], "budget_secondes": 240}

    def client(self, reponses, cfg=None):
        self.t = 0.0
        self.attentes = []

        def dormir(s):
            self.attentes.append(s)
            self.t += s
        return ClientGdelt(cfg or self.cfg, SessionSimulee(reponses), horloge=lambda: self.t, dormir=dormir)

    def test_reprises_sur_429_et_5xx_avec_attente_croissante(self):
        c = self.client([Reponse(429, "Please limit requests to one every 5 seconds"), Reponse(503, "busy"),
                         Reponse(200, '{"articles": []}')])
        with self.assertLogs("agent-geopolitique", "WARNING") as journal:
            self.assertEqual(c.requete("groupee", {}), '{"articles": []}')
        self.assertEqual(self.attentes, [10, 20])
        self.assertEqual([x["code"] for x in c.tentatives], [429, 503, 200])
        self.assertTrue(any("HTTP 429 (essai 1/4)" in m for m in journal.output))  # code exact journalisé
        self.assertTrue(any("HTTP 503 (essai 2/4)" in m for m in journal.output))

    def test_retry_after_et_intervalle_minimal(self):
        c = self.client([Reponse(429, "limite", {"Retry-After": "30"}), Reponse(200, "{}"), Reponse(200, "{}")])
        c.requete("a", {})
        self.assertEqual(self.attentes, [30])  # Retry-After plus long que la première attente (10 s)
        c.requete("b", {})  # requête suivante immédiate : au moins 6 s après la précédente
        self.assertEqual(self.attentes[-1], 6)

    def test_budget_et_erreur_definitive(self):
        c = self.client([Reponse(429, "x")] * 10, {**self.cfg, "budget_secondes": 25})
        with self.assertRaises(ErreurSource) as e:
            c.requete("groupee", {})
        self.assertIn("429", str(e.exception))
        self.assertLessEqual(self.t, 25)
        c = self.client([Reponse(400, "query too long")])
        with self.assertRaises(ErreurSource):
            c.requete("groupee", {})
        self.assertEqual(len(c.tentatives), 1)  # 400 : pas de nouvelle tentative


# ------------------------------------------------------------------ regroupement, doublons, pays

def article(titre, domaine, date="2026-11-03T10:00:00Z", description="", langue="en"):
    return {"titre": titre, "url": f"https://{domaine}/{abs(hash((titre, domaine)))}", "domaine": domaine, "date": date,
            "description": description, "langue": langue}


class TestRegroupement(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()
        self.det = E.Detecteur(self.config)

    def test_detection_et_titres_gdelt(self):
        self.assertIn("US", self.det.pays_de("US strikes Iran"))
        self.assertNotIn("US", self.det.pays_de("Let us talk about it"))
        self.assertEqual(E.nettoyer_titre("U . S . Carries Out Defensive Strike On Iranian Island"), "U.S. Carries Out Defensive Strike On Iranian Island")
        self.assertEqual(E.nettoyer_titre("It Election Day . Control of Congress"), "It Election Day. Control of Congress")
        self.assertEqual(self.det.categorie_de("The US-China trade war seems to have subsided"), "commerce")

    def test_depeche_reprise_comptee_une_fois(self):
        arts = [{"titre": "A new cold war: hackers target fridges", "domaine": d} for d in ("ksut.org", "wcsufm.org", "kfoo.org")]
        arts.append({"titre": "Hackers hit supermarket freezers in Europe", "domaine": "bbc.co.uk"})
        self.assertEqual(E.independantes(arts), 2)

    def test_qeshm_un_seul_evenement_avec_7_sources(self):
        """Exemple de production : deux événements pour la même frappe, à fusionner."""
        a = [article("US strikes Iranian island ahead of midterm elections", "bbc.co.uk", "2026-11-03T09:00:00Z"),
             article("US strikes Iran's Qeshm Island as Vance voices optimism about a deal", "theguardian.com", "2026-11-03T09:30:00Z"),
             article("US conducts series of 'defensive strikes' against Iran", "aljazeera.com", "2026-11-03T10:00:00Z")]
        b = [article("U . S . Carries Out Defensive Strike On Iranian Island", d, "2026-11-03T12:00:00Z")
             for d in ("bozemandailychronicle.com", "wfmz.com", "stcatharinesstandard.ca", "kxan.com")]
        evts = []
        E.regrouper([E.preparer(x, self.det) for x in a], evts, self.config, MAINTENANT)
        e2 = []
        E.regrouper([E.preparer(x, self.det) for x in b], e2, self.config, MAINTENANT)
        evts += e2  # deux événements distincts, comme en production
        self.assertGreaterEqual(len(evts), 2)
        resultat, fusions = E.fusionner(evts, self.det)
        self.assertEqual(len(resultat), 1)
        self.assertTrue(fusions)
        self.assertEqual(len(E.sources_publiques(resultat[0])), 7)
        self.assertEqual(E.independantes(resultat[0]["articles"]), 4)  # les 4 reprises AP comptent pour une
        self.assertEqual(E.pays_principaux(resultat[0], self.det)[:2], ["US", "IR"])

    def test_evenements_differents_non_fusionnes(self):
        a = [article("US strikes Iranian island ahead of midterm elections", "bbc.co.uk")]
        b = [article("Can US midterm election really change Trump's Iran policy?", "dw.com")]
        evts = []
        for lot in (a, b):
            e = []
            E.regrouper([E.preparer(x, self.det) for x in lot], e, self.config, MAINTENANT)
            evts += e
        self.assertEqual(len(E.fusionner(evts, self.det)[0]), 2)

    def test_pays_principaux_elections_americaines(self):
        titres = ["US midterm voting begins in high-stakes test of Trump's presidency", "Polls open in closely contested US midterm elections",
                  "US midterm elections live: Polls open in test for Trump", "Americans begin voting in elections to decide control of Congress",
                  "Wall Street braces as voters head to high-stakes polls"]
        arts = [article(x, f"site{i}.com") for i, x in enumerate(titres)]
        arts.append(article("Midterms : un vote décisif pour Donald Trump", "france24.com", description="Le correspondant de France 24 à Paris…", langue="fr"))
        arts.append(article("What the US election means for Ukraine", "site9.com", description="Kyiv watches the vote"))
        evts = []
        E.regrouper([p for p in (E.preparer(x, self.det) for x in arts) if p], evts, self.config, MAINTENANT)
        principal = max(evts, key=lambda e: len(e["articles"]))
        self.assertEqual(E.pays_principaux(principal, self.det), ["US"])
        self.assertEqual(E.pays_principaux(principal, self.det, ["Les Américains votent pour renouveler le Congrès."]), ["US"])
        # Résumé de Gemini qui évoque l'Ukraine et l'Iran : pas rattaché à ces pays (cités dans peu d'articles)
        resume = ["Les électeurs américains votent ; les enjeux incluent la politique envers l'Ukraine et l'Iran."]
        self.assertEqual(E.pays_principaux(principal, self.det, resume), ["US"])


# ------------------------------------------------------------------ exécution complète

class TestSansIA(Base):
    def test_version_sans_ia_signalee(self):
        r = self.lancer(mode="quotidien")
        d = self.publics()
        self.assertEqual(d["mode_ia"], "sans IA")
        self.assertIn("clé GEMINI_API_KEY absente", d["avertissement_ia"])
        self.assertTrue(d["evenements"])
        for e in d["evenements"]:
            self.assertTrue(e["gravite"] <= 3 and not e["ia"] and e["sources"])
            self.assertEqual(e["mention"], "non analysé")
            self.assertIn(e["titre_langue"], ("anglais", "français"))
        self.assertEqual(len(d["pays"]), len(self.config["pays"]))
        self.assertTrue((self.data / "recap" / "geopolitique-2026-11-03.md").exists())
        self.assertIn("non analysé", (self.data / "recap" / "geopolitique-2026-11-03.md").read_text(encoding="utf-8"))
        s = lire_json(self.data / "journal" / "agent-geopolitique.json")["meta"]["sante"]
        self.assertEqual(s["intervalle_min"], 60)
        self.assertEqual(next(x for x in s["sources"] if x["nom"].startswith("Gemini"))["etat"], "non configurée")
        doc = next(x for x in s["sources"] if x["nom"].startswith("GDELT, API DOC"))
        self.assertEqual(doc["etat"], "ok")
        self.assertIn("requêtes groupées", doc["detail"])
        self.assertTrue(r["recap"])

    def test_requetes_par_theme_si_groupee_desactivee(self):
        self.config["gdelt"]["requete_groupee"] = False
        r = self.lancer()
        doc = next(x for x in r["sante"]["sources"] if x["nom"].startswith("GDELT, API DOC"))
        self.assertEqual(doc["etat"], "partielle")  # requête « coup » absente des données de test

    def test_synthese_une_fois_par_jour(self):
        self.assertFalse(self.lancer(t("2026-11-03T05:03:00Z"))["recap"])
        self.assertTrue(self.lancer(t("2026-11-03T07:03:00Z"))["recap"])
        self.assertFalse(self.lancer(t("2026-11-03T08:03:00Z"))["recap"])


class TestGemini(Base):
    def test_analyse_cache_et_statut_ok(self):
        g = GeminiSimule()
        r1 = self.lancer(cle="cle-test", poster=g)
        self.assertGreater(r1["rapport_ia"]["analyses"], 0)
        self.assertFalse(r1["sante"]["degrade"], r1["sante"]["raisons"])  # Gemini répond, sources présentes : OK
        d = self.publics()
        self.assertEqual(d["mode_ia"], "gemini")
        for e in (x for x in d["evenements"] if x["ia"]):
            urls = {s["url"] for s in e["sources"]}
            self.assertIsNone(e["mention"])
            for a in e["resume"] + e["actifs"] + e["contre"]:
                self.assertTrue(a["sources"] and set(a["sources"]) <= urls)
                self.assertTrue(ia.en_francais(a["texte"]))
        n = len(g.appels)
        self.lancer(MAINTENANT + timedelta(hours=1), cle="cle-test", poster=g)
        restants = [e for e in r1["etat"]["evenements"] if E.significatif(e, self.config) and not e.get("analyse")]
        self.assertLessEqual(len(g.appels) - n, -(-len(restants) // self.config["gemini"]["evenements_par_appel"]))

    def test_anti_hallucination_et_francais(self):
        def fabrique(eid, sources):
            un = [sources[0]["id"]]
            return {"evenement": eid,
                    "resume": [{"texte": "Les États-Unis ont frappé une île iranienne.", "sources": un},
                               {"texte": "Affirmation inventée par le modèle.", "sources": ["S99"]},
                               {"texte": "The United States struck an Iranian island.", "sources": un}],
                    "pays": ["US", "XX"], "categorie": "inconnue", "gravite": 5,
                    "actifs": [{"actif": "pétrole", "sens": "hausse", "texte": "Sans source dans la réponse."},
                               {"actif": "licornes", "sens": "hausse", "texte": "Un actif inconnu de la liste.", "sources": un},
                               {"actif": "or", "sens": "hausse", "texte": "Une situation catastrophique pour le marché.", "sources": un}],
                    "horizon": "années", "confiance": "certaine", "contre": []}
        r = self.lancer(cle="cle-test", poster=GeminiSimule(fabrique=fabrique))
        analyses = [e for e in self.publics()["evenements"] if e["ia"]]
        self.assertTrue(analyses)
        for e in analyses:
            self.assertEqual([x["texte"] for x in e["resume"]], ["Les États-Unis ont frappé une île iranienne."])
            self.assertEqual(e["actifs"], [])
            self.assertEqual(e["gravite"], 3)
            self.assertIn("plafonnée à 3", e["note_gravite"])
            self.assertNotIn("XX", e["pays"])
            self.assertIn(e["categorie"], self.config["categories"])
            self.assertEqual((e["horizon"], e["confiance"]), ("semaines", "faible"))
        sup = " ".join(r["rapport_ia"]["suppressions"])
        for motif in ("sans source", "ton non conforme", "pas en français"):
            self.assertIn(motif, sup)

    def test_resume_en_anglais_repasse_sans_ia(self):
        fab = lambda eid, sources: {"evenement": eid, "resume": [{"texte": "The strike was confirmed by the ministry.", "sources": [sources[0]["id"]]}], "gravite": 3}
        self.lancer(cle="cle-test", poster=GeminiSimule(fabrique=fab))
        evts = self.publics()["evenements"]
        self.assertFalse(any(e["ia"] for e in evts))
        self.assertTrue(all(e["mention"] == "non analysé" for e in evts))

    def test_gravite_4_avec_deux_sources_et_signal(self):
        def fab(eid, sources):
            par_dom = {}
            for s in sources:
                par_dom.setdefault(s["domaine"], s["id"])
            ids = list(par_dom.values())
            return {"evenement": eid, "resume": [{"texte": "Le fait est confirmé par deux sources.", "sources": ids[:2]}], "gravite": 4,
                    "actifs": [], "horizon": "jours", "confiance": "moyenne", "contre": []}
        r = self.lancer(cle="cle-test", poster=GeminiSimule(fabrique=fab))
        graves = [e for e in self.publics()["evenements"] if e["gravite"] == 4]
        self.assertTrue(graves)
        self.assertTrue(all(e["sources_independantes"] >= 2 for e in graves))
        self.assertTrue(any(s["type"] == "evenement_grave" for s in r["signaux"]))

    def test_priorite_aux_gravites_3_et_plus(self):
        evts = [{"id": f"e{i}", "categorie": c, "pays": ["US"], "noyau": [], "premier": "2026-11-03T10:00:00Z", "dernier": "2026-11-03T10:00:00Z",
                 "articles": [{"titre": f"t{i}{k}", "url": f"https://d{k}.example/{i}", "domaine": f"d{k}.example", "origine": "gdelt"} for k in range(n)]}
               for i, (c, n) in enumerate([("election", 9), ("diplomatie", 8), ("conflit", 3), ("sanctions", 3)])]
        ordre = [e["id"] for e in sorted(evts, key=lambda e: ia.priorite(e, self.config), reverse=True)]
        self.assertEqual(set(ordre[:2]), {"e2", "e3"})  # conflit et sanctions (gravité 3) avant élection et diplomatie


class TestGeminiPannes(Base):
    def test_503_puis_reponse_au_troisieme_essai(self):
        g = GeminiSimule(scenario=lambda m, n: SURCHARGE if n <= 2 else None)
        r = self.lancer(cle="cle-test", poster=g)
        premier = self.config["gemini"]["modeles"][0]["nom"]
        self.assertEqual([m for _, m in g.appels[:3]], [premier] * 3)
        self.assertIn(5, self.horloge.attentes)
        self.assertIn(15, self.horloge.attentes)  # attente progressive
        self.assertGreater(r["rapport_ia"]["analyses"], 0)
        self.assertFalse(r["sante"]["degrade"], r["sante"]["raisons"])

    def test_modele_de_secours(self):
        premier, second = (m["nom"] for m in self.config["gemini"]["modeles"][:2])
        g = GeminiSimule(scenario=lambda m, n: SURCHARGE if m == premier else None)
        r = self.lancer(cle="cle-test", poster=g)
        self.assertEqual(g.par_modele[premier], self.config["gemini"]["essais"])  # 3 essais, puis secours
        self.assertGreater(g.par_modele[second], 0)
        self.assertIn(second, r["rapport_ia"]["modeles_utilises"])
        self.assertFalse(r["sante"]["degrade"], r["sante"]["raisons"])
        gemini = next(x for x in r["sante"]["sources"] if x["nom"].startswith("Gemini"))
        self.assertIn("secours", gemini["detail"])
        self.assertTrue(any(e["ia"] and e["modele"] == second for e in self.publics()["evenements"]))

    def test_tous_les_modeles_en_panne(self):
        r = self.lancer(cle="cle-test", poster=GeminiSimule(scenario=lambda m, n: SURCHARGE))
        d = self.publics()
        self.assertEqual(d["mode_ia"], "sans IA")
        self.assertIn("HTTP 503", d["avertissement_ia"])
        self.assertTrue(r["sante"]["degrade"])
        self.assertTrue(any("Gemini indisponible" in x for x in r["sante"]["raisons"]))

    def test_modele_inconnu_passe_au_suivant_sans_insister(self):
        premier = self.config["gemini"]["modeles"][0]["nom"]
        g = GeminiSimule(scenario=lambda m, n: (404, "model not found") if m == premier else None)
        r = self.lancer(cle="cle-test", poster=g)
        self.assertEqual(g.par_modele[premier], 1)
        self.assertGreater(r["rapport_ia"]["analyses"], 0)

    def test_429_du_jour_suspend_le_modele_jusqu_au_lendemain(self):
        premier, second = (m["nom"] for m in self.config["gemini"]["modeles"][:2])
        etat = {"bloque": True}
        g = GeminiSimule(scenario=lambda m, n: QUOTA_JOUR if (m == premier and etat["bloque"]) else None)
        r = self.lancer(cle="cle-test", poster=g)
        self.assertTrue(r["rapport_ia"]["quota_atteint"])
        self.assertEqual(g.par_modele[premier], 1)
        self.assertFalse(r["sante"]["degrade"], r["sante"]["raisons"])  # le secours a répondu
        q = r["etat"]["quota_gemini"]["modeles"][premier]
        self.assertEqual(q["plafond_jour"], 1)
        self.assertEqual(q["limite_apprise"], 1)
        # Plus tard le même jour (heure du Pacifique) : plus d'appel au premier modèle
        n = g.par_modele[premier]
        self.lancer(MAINTENANT + timedelta(hours=3), cle="cle-test", poster=g)
        self.assertEqual(g.par_modele[premier], n)
        # Le lendemain (après minuit, heure du Pacifique) : de nouveau appelé
        etat["bloque"] = False
        lendemain = datetime(2026, 11, 4, 9, 5, tzinfo=timezone.utc)
        (self.data / "recap" / "geopolitique-2026-11-04.md").parent.mkdir(exist_ok=True)
        st = lire_json(self.data / "geopolitique" / "etat.json")
        for e in st["evenements"]:
            e.pop("analyse", None)
        (self.data / "geopolitique" / "etat.json").write_text(json.dumps(st), encoding="utf-8")
        self.lancer(lendemain, cle="cle-test", poster=g)
        self.assertGreater(g.par_modele[premier], n)

    def test_429_par_minute_attend_puis_reessaie(self):
        premier = self.config["gemini"]["modeles"][0]["nom"]
        g = GeminiSimule(scenario=lambda m, n: QUOTA_MINUTE if (m == premier and n == 1) else None)
        r = self.lancer(cle="cle-test", poster=g)
        self.assertIn(20, self.horloge.attentes)  # retryDelay respecté
        self.assertGreater(r["rapport_ia"]["modeles_utilises"].get(premier, 0), 0)
        self.assertIsNone(r["etat"]["quota_gemini"]["modeles"][premier].get("plafond_jour"))

    def test_fusion_confirmee_par_gemini(self):
        def fab(eid, sources):
            a = analyse_type(eid, sources)
            a["meme_que"] = fab.premier.setdefault("id", eid) if fab.premier.get("id") != eid else None
            return a
        fab.premier = {}
        r = self.lancer(cle="cle-test", poster=GeminiSimule(fabrique=fab))
        self.assertTrue(r["rapport_ia"]["fusions"])
        ids = {e["id"] for e in r["etat"]["evenements"]}
        for base, autre in r["rapport_ia"]["fusions"]:
            self.assertFalse(base in ids and autre in ids)


# ------------------------------------------------------------------ quotas sur des journées complètes

def evenement_synthetique(i: int, maintenant: datetime, categorie="conflit") -> dict:
    date = E.iso(maintenant)
    return {"id": f"evt-{i}", "categorie": categorie, "pays": ["US"], "noyau": [], "premier": date, "dernier": date,
            "articles": [{"titre": f"Titre {i} {k}", "url": f"https://d{k}.example/{i}", "domaine": f"d{k}.example",
                          "date": date, "origine": "gdelt"} for k in range(3)]}


class TestQuotasJournee(unittest.TestCase):
    """Exécutions horaires sur plusieurs jours de quota (jour du Pacifique), avec toujours plus
    d'événements à analyser que le quota n'en permet."""

    def simuler(self, debut: datetime, heures: int, extra=(), evenements_par_heure=200, scenario=None, config=None):
        config = config or charger_config()
        cfg = config["gemini"]
        etat, h = {}, Horloge(debut)
        g = GeminiSimule(horloge=h, scenario=scenario)
        par_execution, i = [], 0
        for m in sorted([debut + timedelta(hours=k, minutes=3) for k in range(heures)] + list(extra)):
            h.t = max(h.t, m)
            quotas = ia.Quotas(etat, cfg, horloge=h, dormir=h.dormir)
            candidats = [evenement_synthetique(i + k, m) for k in range(evenements_par_heure)]
            i += evenements_par_heure
            avant = len(g.appels)
            rapport = ia.analyser(candidats, config, quotas, h(), cle="cle-test", poster=g)
            par_execution.append((m, len(g.appels) - avant, rapport))
        return cfg, g, par_execution, etat

    def verifier(self, cfg, g, par_execution):
        limites = {m["nom"]: m for m in cfg["modeles"]}
        par_jour = {}
        for t_appel, modele in g.appels:
            cle = (modele, t_appel.astimezone(PACIFIQUE).date())
            par_jour[cle] = par_jour.get(cle, 0) + 1
        for (modele, j), n in par_jour.items():
            self.assertLessEqual(n, int(limites[modele]["rpd"] * (1 - cfg["marge"])), f"{modele} le {j} : {n}")
        for _, n, _ in par_execution:
            self.assertLessEqual(n, cfg["appels_max_par_execution"])
        for modele in limites:
            appels = [t_a for t_a, m in g.appels if m == modele]
            rpm = int(limites[modele]["rpm"] * (1 - cfg["marge"]))
            for k, a in enumerate(appels):
                self.assertLessEqual(len([b for b in appels if timedelta(0) <= a - b < timedelta(seconds=60)]), rpm)
                if k:
                    self.assertGreaterEqual((a - appels[k - 1]).total_seconds(), 60 / rpm - 1e-6)
        return par_jour

    def test_deux_journees_completes_horaires(self):
        debut = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)  # minuit, heure du Pacifique
        cfg, g, par_execution, _ = self.simuler(debut, 48)
        par_jour = self.verifier(cfg, g, par_execution)
        premier = cfg["modeles"][0]
        limite = int(premier["rpd"] * (1 - cfg["marge"]))
        for j in {k[1] for k in par_jour}:
            n = par_jour.get((premier["nom"], j), 0)
            self.assertGreaterEqual(n, limite - cfg["appels_max_par_execution"])  # budget utilisé…
        soir = [n for m, n, _ in par_execution if m.astimezone(PACIFIQUE).hour >= 18]
        self.assertGreater(sum(soir), 0)  # … et réparti jusqu'au soir

    def test_lancements_manuels_en_plus(self):
        debut = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
        extra = [debut + timedelta(hours=k, minutes=30) for k in range(0, 24, 2)]
        cfg, g, par_execution, _ = self.simuler(debut, 24, extra)
        self.verifier(cfg, g, par_execution)

    def test_429_reduit_les_appels_jusqu_au_lendemain(self):
        """La limite réelle du modèle est plus basse que la configuration : 30 appels par jour."""
        debut = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
        reel = {"n": 0, "jour": None}
        config = charger_config()
        cfg = config["gemini"]
        premier = cfg["modeles"][0]["nom"]
        etat, h = {}, Horloge(debut)

        def scenario(modele, n):
            if modele != premier:
                return None
            jour = h().astimezone(PACIFIQUE).date()
            if reel["jour"] != jour:
                reel.update(jour=jour, n=0)
            reel["n"] += 1
            return QUOTA_JOUR if reel["n"] > 30 else None
        g = GeminiSimule(horloge=h, scenario=scenario)
        for k in range(48):
            h.t = max(h.t, debut + timedelta(hours=k, minutes=3))
            quotas = ia.Quotas(etat, cfg, horloge=h, dormir=h.dormir)
            ia.analyser([evenement_synthetique(1000 * k + x, h()) for x in range(60)], config, quotas, h(), cle="c", poster=g)
        appels_premier = [t_a for t_a, m in g.appels if m == premier]
        j1 = [a for a in appels_premier if a.astimezone(PACIFIQUE).date() == debut.astimezone(PACIFIQUE).date() + timedelta(days=0)]
        j2 = [a for a in appels_premier if a.astimezone(PACIFIQUE).date() == debut.astimezone(PACIFIQUE).date() + timedelta(days=1)]
        self.assertEqual(len(j1), 31)  # 30 acceptés + le 429, puis plus rien ce jour-là
        self.assertLessEqual(len(j2), int(30 * (1 - cfg["marge"])))  # limite apprise, marge de 20 %
        self.assertEqual(etat["quota_gemini"]["modeles"][premier]["limite_apprise"], 31)
        self.assertGreater(len([1 for _, m in g.appels if m != premier]), 0)  # le secours a pris le relais

    def test_configuration(self):
        cfg = charger_config()["gemini"]
        self.assertEqual(cfg["marge"], 0.2)
        self.assertEqual(cfg["fuseau_quota"], "America/Los_Angeles")
        self.assertEqual(len(cfg["modeles"]), 3)
        self.assertTrue(all(m["rpd"] > 0 and m["rpm"] > 0 for m in cfg["modeles"]))


# ------------------------------------------------------------------ score

class TestScore(unittest.TestCase):
    def test_gravite_et_anciennete(self):
        cfg = charger_config()["score"]
        e = lambda g, jours: {"pays_principaux": ["FR"], "gravite": g, "dernier": E.iso(MAINTENANT - timedelta(days=jours))}
        faible, _ = S.composante_evenements("FR", [e(1, 0)], MAINTENANT, cfg)
        fort, _ = S.composante_evenements("FR", [e(4, 0), e(3, 1)], MAINTENANT, cfg)
        ancien, _ = S.composante_evenements("FR", [e(4, 10), e(3, 11)], MAINTENANT, cfg)
        self.assertLess(faible, fort)
        self.assertLess(ancien, fort)
        cite, _ = S.composante_evenements("FR", [{"pays": ["FR"], "pays_principaux": ["US"], "gravite": 4, "dernier": E.iso(MAINTENANT)}], MAINTENANT, cfg)
        self.assertEqual(cite, 0)  # pays seulement cité : pas compté

    def test_variation_et_tendance(self):
        hist = [["2026-10-25", 30], ["2026-10-27", 40], ["2026-11-02", 50]]
        self.assertEqual(S.variation_7j(hist, 55, MAINTENANT.date()), 15)
        jours, fichiers = {}, {}
        for k in range(30):
            j = (MAINTENANT.date() - timedelta(days=k)).isoformat()
            jours[j] = {"FR": {"conflits": 20 if k < 7 else 10}}
            fichiers[j] = 96
        self.assertGreater(S.composante_tendance(jours, fichiers, "FR", MAINTENANT.date()), 50)

    def test_sobriete_et_langue(self):
        self.assertTrue(ia.sobre("Les droits de douane augmentent de 10 %."))
        self.assertFalse(ia.sobre("Une situation catastrophique et sans précédent."))
        self.assertTrue(ia.en_francais("Les États-Unis ont frappé une île iranienne."))
        self.assertFalse(ia.en_francais("The United States struck an Iranian island."))

    def test_renvois_retires_du_texte(self):
        sources = [{"id": "S1", "url": "https://a.example/1", "domaine": "a.example", "titre": "t"}]
        res = ia._affirmations([{"texte": "Les électeurs votent pour le Congrès [S1].", "sources": ["S1"]}], {"S1": sources[0]}, 2, [])
        self.assertEqual(res[0]["texte"], "Les électeurs votent pour le Congrès.")


if __name__ == "__main__":
    unittest.main()
