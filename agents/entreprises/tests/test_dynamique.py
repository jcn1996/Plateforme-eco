"""Tests de la dynamique des résultats (guidance, analystes, note du bloc, recommandation), sans réseau ni Gemini réel.
Les vrais config/ et data/ ne sont jamais lus ni modifiés : dossiers temporaires uniquement."""
import copy
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from agents.entreprises import agent as AG
from agents.entreprises import dynamique as D
from agents.entreprises import recommandation as R
from agents.pays.textes import ton_conforme

DOSSIER = Path(__file__).resolve().parents[1]
CONFIG = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
CFG = CONFIG["dynamique"]
CFG_R = CONFIG["recommandation"]
ANALYSTES = json.loads((DOSSIER / "tests" / "donnees" / "societes.json").read_text(encoding="utf-8"))["analystes"]
JOUR = date(2026, 11, 6)

COMMUNIQUE = """<html><body>
<p>ACME Corp Reports Third Quarter 2026 Results</p>
<p>Revenue was $5.1 billion, up 8% compared with the third quarter of 2025.</p>
<p><b>Outlook</b></p>
<p>ACME now expects full-year 2026 revenue of $20.5 billion to $20.9 billion, up from its prior outlook of $20.0 billion to $20.6 billion.</p>
<table><tr><td>Diluted EPS</td><td>$</td><td>4.10 - 4.30</td></tr></table>
<p>This press release contains forward-looking statements within the meaning of the Private Securities Litigation Reform Act; the company expects nothing.</p>
</body></html>"""
CITATION_CA = "ACME now expects full-year 2026 revenue of $20.5 billion to $20.9 billion, up from its prior outlook of $20.0 billion to $20.6 billion."


def guidance(**k):
    g = {"indicateur": "chiffre_affaires", "libelle": "Chiffre d'affaires", "periode": "exercice 2026", "valeur": "20,5 à 20,9 Md$",
         "bas": 20.5, "haut": 20.9, "unite": "Md$", "evolution": "relevée", "citation": CITATION_CA}
    g.update(k)
    return g


class TestAnalystes(unittest.TestCase):
    def test_lecture_quote_summary(self):
        a = D.lire_analystes(ANALYSTES["AAPL"])
        self.assertEqual(set(a["estimations"]), {"0q", "+1q", "0y", "+1y"})
        self.assertIsNotNone(a["estimations"]["0y"]["bpa"]["actuel"])
        self.assertLessEqual(len(a["surprises"]), 4)
        self.assertEqual(a["surprises"], sorted(a["surprises"], key=lambda s: s["trimestre"]))
        self.assertGreaterEqual(a["analystes"], 3)
        self.assertIsNotNone(a["objectifs"]["ecart_pct"])
        self.assertIsNone(D.lire_analystes(None))

    def test_format_brut_ou_formate(self):
        brut = {"earningsTrend": {"trend": [{"period": "0y", "epsTrend": {"current": {"raw": 2.2}, "30daysAgo": {"raw": 2.0}, "90daysAgo": 1.8},
                                             "epsRevisions": {"upLast30days": {"raw": 5}, "downLast30days": 1},
                                             "earningsEstimate": {"numberOfAnalysts": {"raw": 6}}}]},
                "earningsHistory": {"history": [{"epsActual": 1.1, "epsEstimate": 1.0, "quarter": {"raw": 1767139200}}]},
                "financialData": {"currentPrice": 50.0, "targetMeanPrice": 60.0, "targetHighPrice": 70, "targetLowPrice": 40, "numberOfAnalystOpinions": 5}}
        a = D.lire_analystes(brut)
        self.assertEqual(a["surprises"][0], {"trimestre": "2025-12-31", "publie": 1.1, "estime": 1.0, "surprise_pct": 10.0})
        self.assertEqual(a["objectifs"]["ecart_pct"], 20.0)
        rv = D.revisions(a)
        self.assertEqual(rv["30j_pct"], 10.0)
        self.assertAlmostEqual(rv["90j_pct"], 22.2)
        self.assertEqual((rv["hausse_30j"], rv["baisse_30j"]), (5, 1))

    def test_bpa_proche_de_zero(self):
        self.assertIsNone(D.variation_pct(0.5, 0.0))
        self.assertAlmostEqual(D.variation_pct(-0.5, -1.0), 50.0)  # perte qui se réduit : amélioration


class TestCommunique(unittest.TestCase):
    TEXTES = [("https://www.sec.gov/ex99.htm", D.html_en_texte(COMMUNIQUE))]

    def test_texte_et_passages(self):
        t = self.TEXTES[0][1]
        self.assertIn("Diluted EPS | $ | 4.10 - 4.30", t)
        p = D.extraire_passages(self.TEXTES, 12000)
        textes = [x["texte"] for x in p]
        self.assertIn("Outlook", textes)
        self.assertIn(CITATION_CA, textes)
        self.assertFalse(any("forward-looking" in x for x in textes))  # mentions juridiques écartées
        self.assertEqual(D.extraire_passages([("u", "Revenue was $5 billion.\nNet income was $1 billion.")], 12000), [])

    def test_citation(self):
        self.assertEqual(D.citation_retrouvee(CITATION_CA.replace("’", "'"), self.TEXTES), "https://www.sec.gov/ex99.htm")
        self.assertIsNotNone(D.citation_retrouvee("Diluted EPS $4.10 - 4.30 ", self.TEXTES))  # cellules de tableau
        self.assertIsNotNone(D.citation_retrouvee("ACME now expects full-year 2026 revenue … up from its prior outlook", self.TEXTES))
        self.assertIsNone(D.citation_retrouvee("ACME now expects full-year 2027 revenue of $25 billion.", self.TEXTES))
        self.assertIsNone(D.citation_retrouvee("Outlook", self.TEXTES))  # trop court pour être une preuve

    def test_nombres(self):
        self.assertEqual(D._nombres("$1,250.5 million and 10.2%"), {1250.5, 10.2})
        self.assertEqual(D._nombres("10,2 à 10,4 Md$"), {10.2, 10.4})
        self.assertEqual(D._nombres("1 250 M$"), {1250.0})

    def test_validation(self):
        brut = {"guidances": [
            guidance(),
            guidance(libelle="Inventée", citation="ACME expects 2027 revenue of $30 billion, driven by new products."),
            guidance(libelle="Chiffre faux", valeur="21 à 22 Md$", bas=21, haut=22),
            guidance(indicateur="dividende"),
            guidance(indicateur="bpa", libelle="BPA dilué", valeur="4,10 à 4,30 $", bas=4.1, haut=4.3, unite="$", evolution="initiée",
                     citation="Diluted EPS | $ | 4.10 - 4.30"),
        ]}
        g, rejets = D.valider_guidances(brut, self.TEXTES, [], CFG)
        self.assertEqual([x["libelle"] for x in g], ["Chiffre d'affaires", "BPA dilué"])
        self.assertEqual(len(rejets), 3)
        self.assertTrue(all(x["url"] == "https://www.sec.gov/ex99.htm" for x in g))
        self.assertEqual(D.evolution_ensemble(g), "relevée")
        self.assertEqual(D.valider_guidances("pas du JSON", self.TEXTES, [], CFG), ([], ["format de réponse inattendu"]))

    def test_evolution_recalculee_par_les_chiffres(self):
        prec = [{**guidance(valeur="21 à 21,4 Md$", bas=21.0, haut=21.4), "date": "2026-07-30"}]
        g, _ = D.valider_guidances({"guidances": [guidance(evolution="relevée")]}, self.TEXTES, prec, CFG)
        self.assertEqual(g[0]["evolution"], "abaissée")  # milieu 20,7 contre 21,2 : abaissée malgré Gemini
        self.assertEqual(g[0]["evolution_gemini"], "relevée")
        self.assertEqual(g[0]["precedente"]["date"], "2026-07-30")

    def test_evolution_ensemble_prudente(self):
        g = [{"indicateur": "chiffre_affaires", "evolution": "relevée"}, {"indicateur": "bpa", "evolution": "abaissée"},
             {"indicateur": "autre", "evolution": "retirée"}]
        self.assertEqual(D.evolution_ensemble(g), "abaissée")  # indicateurs principaux d'abord, le plus défavorable l'emporte


# ------------------------------------------------------------------ collecte de bout en bout (SEC et Gemini simulés)

class SecFactice:
    actif = True

    def __init__(self, depots):
        self.depots, self.appels = depots, []

    def resultats_8k(self, cik, fenetre, aujourdhui):
        return self.depots.get(cik, [])

    def pieces_jointes(self, d):
        return [{"type": "8-K", "url": d["base"] + "/8k.htm"}, {"type": "EX-99.1", "url": d["base"] + "/ex99.htm"}]

    def document(self, url):
        self.appels.append(url)
        return COMMUNIQUE


class Reponse:
    def __init__(self, code, corps):
        self.status_code, self._corps, self.text = code, corps, json.dumps(corps)

    def json(self):
        return self._corps


def poster_gemini(guidances, appels):
    def poster(url, params=None, timeout=None, json=None):
        appels.append(url)
        texte = __import__("json").dumps({"guidances": guidances})
        return Reponse(200, {"candidates": [{"content": {"parts": [{"text": texte}]}}]})
    return poster


def poster_en_panne(appels):
    def poster(url, params=None, timeout=None, json=None):
        appels.append(url)
        return Reponse(503, {"error": "overloaded"})
    return poster


class TestCollecte(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="dyn-"))
        self.base = {"ACME": {"pays": "US", "nom": "ACME Corp", "ids": {"cik": "0000000001"}},
                     "EURO.PA": {"pays": "FR", "nom": "Euro SA", "ids": {}}}
        depot = {"cik": "0000000001", "accession": "0000000001-26-000010", "date": "2026-10-30", "periode": "2026-10-30",
                 "url_depot": "https://www.sec.gov/Archives/edgar/data/1/000000000126000010/0000000001-26-000010-index.htm",
                 "base": "https://www.sec.gov/Archives/edgar/data/1/000000000126000010"}
        self.sec = SecFactice({"0000000001": [depot]})
        self.yahoo = type("Y", (), {"analystes": lambda self, t: ANALYSTES.get("AAPL") if t == "ACME" else None})()
        self.f = type("F", (), {"sec": self.sec, "yahoo": self.yahoo})()
        # Horloge simulée : avance quand l'agent attend (intervalle entre deux appels à Gemini)
        self.t = datetime(2026, 11, 6, 22, 30, tzinfo=timezone.utc)
        self.horloge = lambda: self.t

    def dormir(self, secondes):
        from datetime import timedelta
        self.t += timedelta(seconds=secondes)

    def tearDown(self):
        shutil.rmtree(self.data)

    def executer(self, cle, poster):
        return D.executer(self.f, self.base, CONFIG, self.data, JOUR, cle, poster=poster, horloge=self.horloge, dormir=self.dormir)

    def test_sans_cle_puis_reprise(self):
        r = self.executer("", None)
        self.assertEqual(r["guidance"]["en_attente"], 1)
        stock = D.lire_stock(self.data)
        self.assertEqual(stock["ACME"]["guidance"]["statut"], "non analysée")
        self.assertEqual(stock["ACME"]["guidance"]["dernier"]["raison"], "secret GEMINI_API_KEY absent")
        self.assertEqual(stock["EURO.PA"]["guidance"]["statut"], "non disponible")
        self.assertIn("analystes", stock["ACME"])
        self.assertNotIn("analystes", stock["EURO.PA"])  # Yahoo ne publie rien
        # Exécution suivante avec Gemini : le communiqué est repris et analysé
        appels = []
        r = self.executer("cle", poster_gemini([guidance(evolution="initiée")], appels))
        self.assertEqual(len(appels), 1)
        h = json.loads((self.data / "historique" / "guidance" / "ACME.json").read_text(encoding="utf-8"))["donnees"]
        self.assertEqual(len(h["communiques"]), 1)
        c = h["communiques"][0]
        self.assertEqual((c["statut"], c["evolution"]), ("analysée", "initiée"))
        self.assertEqual(c["guidances"][0]["citation"], CITATION_CA)
        self.assertTrue(c["url_depot"].startswith("https://www.sec.gov/"))
        # Déjà analysé : plus d'appel
        appels.clear()
        self.executer("cle", poster_gemini([], appels))
        self.assertEqual(appels, [])
        etat = json.loads((self.data / "entreprises" / "etat_dynamique.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(m["appels"] for m in etat["quota_gemini"]["modeles"].values()), 1)

    def test_gemini_en_panne_puis_citation_inventee(self):
        appels = []
        r = self.executer("cle", poster_en_panne(appels))
        self.assertEqual(r["guidance"]["en_attente"], 1)
        self.assertLessEqual(len(appels), sum(CFG["gemini"]["essais"] for _ in CFG["gemini"]["modeles"]))
        stock = D.lire_stock(self.data)
        self.assertEqual(stock["ACME"]["guidance"]["statut"], "non analysée")
        # Gemini répond, mais sans citation retrouvée : rien n'est retenu
        r = self.executer("cle", poster_gemini([guidance(citation="ACME expects record revenue of $40 billion next year.")], []))
        h = D.lire_historique(self.data / "historique" / "guidance", "ACME")
        self.assertEqual(h["communiques"][0]["statut"], "aucune guidance")
        self.assertIsNone(D.lire_stock(self.data)["ACME"]["guidance"]["retenue"])

    def test_budget_respecte(self):
        cfg = copy.deepcopy(CONFIG)
        for m in cfg["dynamique"]["gemini"]["modeles"]:
            m["rpd"] = 1
        depots = {f"{i:010d}": [{"cik": f"{i:010d}", "accession": f"acc-{i}", "date": f"2026-10-{10 + i:02d}", "url_depot": "u",
                                 "base": f"https://www.sec.gov/{i}"}] for i in range(1, 6)}
        self.f.sec = SecFactice(depots)
        base = {f"T{i}": {"pays": "US", "nom": f"T{i}", "ids": {"cik": f"{i:010d}"}} for i in range(1, 6)}
        appels = []
        r = D.executer(self.f, base, cfg, self.data, JOUR, "cle", poster=poster_gemini([guidance()], appels),
                       horloge=self.horloge, dormir=self.dormir)
        self.assertEqual(len(appels), len(cfg["dynamique"]["gemini"]["modeles"]))  # 1 appel par modèle et par jour
        self.assertEqual(r["guidance"]["en_attente"], 5 - len(appels))
        # Les plus récents d'abord
        self.assertEqual(D.lire_stock(self.data)["T5"]["guidance"]["statut"], "analysée")


# ------------------------------------------------------------------ note du bloc

def donnees(evolution=None, date_g="2026-10-30", analystes="AAPL", **k):
    g = {"statut": "analysée", "dernier": {"date": date_g}, "retenue": None}
    if evolution:
        g["retenue"] = {"date": date_g, "evolution": evolution, "accession": "a1",
                        "guidances": [guidance(evolution=evolution)], "url_communique": "https://www.sec.gov/ex99.htm"}
    a = D.lire_analystes(ANALYSTES[analystes]) if analystes else None
    return {"guidance": g, "analystes": a, **k}


class TestBloc(unittest.TestCase):
    def test_guidance_relevee_et_abaissee(self):
        haut = D.bloc(donnees("relevée"), "US", CFG, JOUR)
        bas = D.bloc(donnees("abaissée"), "US", CFG, JOUR)
        self.assertGreater(haut["note"], bas["note"])
        self.assertIsNone(haut["guidance_negative"])
        self.assertEqual(bas["guidance_negative"]["evolution"], "abaissée")
        self.assertTrue(any(c["cle"] == "guidance" for c in haut["composantes"]))
        for b in (haut, bas):
            self.assertTrue(ton_conforme(b["texte"]), b["texte"])
            self.assertTrue(all(ton_conforme(c) for c in b["contre"]))
            self.assertIn(b["confiance"], ("élevé", "moyen", "faible"))

    def test_guidance_ancienne_ignoree(self):
        b = D.bloc(donnees("abaissée", date_g="2026-05-01"), "US", CFG, JOUR)
        self.assertIsNone(b["guidance_negative"])
        self.assertFalse(any(c["cle"] == "guidance" for c in b["composantes"]))

    def test_peu_d_analystes(self):
        a = D.lire_analystes(ANALYSTES["AAPL"])
        a["analystes"] = 2
        b = D.bloc({"analystes": a, "guidance": {"statut": "non disponible"}}, "FR", CFG, JOUR)
        self.assertEqual(b["fiabilite"], "indicative")
        self.assertIsNone(b["note"])  # révisions et surprises exclues de la note
        self.assertTrue(b["estimations"])  # mais affichées
        self.assertTrue(any("indicatif" in c for c in b["contre"]))

    def test_hors_etats_unis(self):
        b = D.bloc(donnees(analystes="MC.PA", guidance={"statut": "non disponible"}), "FR", CFG, JOUR)
        self.assertEqual(b["guidance"]["statut"], "non disponible")
        self.assertIsNotNone(b["note"])
        self.assertNotEqual(b["confiance"], "élevé")

    def test_sans_donnees(self):
        b = D.bloc(None, "US", CFG, JOUR)
        self.assertIsNone(b["note"])
        self.assertEqual(b["sens"], 0)
        self.assertEqual(b["guidance"]["statut"], "non analysée")

    def test_badge(self):
        self.assertEqual(D.badge_guidance(D.bloc(donnees("relevée"), "US", CFG, JOUR), CFG, JOUR)["evolution"], "relevée")
        self.assertIsNone(D.badge_guidance(D.bloc(donnees("maintenue"), "US", CFG, JOUR), CFG, JOUR))
        self.assertIsNone(D.badge_guidance(D.bloc(donnees("relevée", date_g="2026-08-01"), "US", CFG, JOUR), CFG, JOUR))

    def test_note_globale_ponderation_moderee(self):
        n, p = {"a": 60, "b": 60}, {"a": 0.5, "b": 0.5}
        g = AG.note_avec_dynamique(n, p, 100, 0.08)
        self.assertEqual(g["note_sans_dynamique"], 60)
        self.assertEqual(g["note"], round(60 * 0.92 + 100 * 0.08))
        self.assertEqual(AG.note_avec_dynamique(n, p, None, 0.08)["note"], 60)
        self.assertEqual(AG.note_avec_dynamique({"a": 60}, p, 100, 0.08)["couverture"], 0.5)  # couverture inchangée

    def test_signaux_chef_d_orchestre(self):
        avant = {"ticker": "ACME", "nom": "ACME", "dynamique": D.bloc(donnees("maintenue"), "US", CFG, JOUR)}
        apres_d = donnees("abaissée")
        apres_d["guidance"]["retenue"]["accession"] = "a2"
        apres = {"ticker": "ACME", "nom": "ACME", "dynamique": D.bloc(apres_d, "US", CFG, JOUR)}
        s = D.signaux(apres, avant, CFG, JOUR, "source")
        self.assertEqual([x["type"] for x in s], ["guidance_abaissee"])
        self.assertIn("Citation", s[0]["explication"])
        self.assertEqual(D.signaux(apres, apres, CFG, JOUR, "source"), [])  # rien de nouveau
        self.assertEqual(D.signaux(apres, None, CFG, JOUR, "source"), [])  # première publication : pas de signal
        self.assertEqual(D.signaux(apres, {"ticker": "ACME", "nom": "ACME"}, CFG, JOUR, "source"), [])  # bloc précédent absent
        ancien_d = donnees("abaissée", date_g="2026-09-01")
        ancien_d["guidance"]["retenue"]["accession"] = "a3"
        ancien = {"ticker": "ACME", "nom": "ACME", "dynamique": D.bloc(ancien_d, "US", CFG, JOUR)}
        self.assertEqual(D.signaux(ancien, avant, CFG, JOUR, "source"), [])  # communiqué ancien rattrapé : pas de signal
        # Forte révision et grosse surprise
        b2 = copy.deepcopy(avant["dynamique"])
        b2["revisions"]["30j_pct"] = 15.0
        b2["surprises"] = b2["surprises"][:-1] + [{"trimestre": "2026-12-31", "publie": 2.0, "estime": 1.5, "surprise_pct": 33.3}]
        s = D.signaux({**avant, "dynamique": b2}, avant, CFG, JOUR, "source")
        self.assertEqual(sorted(x["type"] for x in s), ["forte_revision", "grosse_surprise"])
        for x in s:
            self.assertTrue(ton_conforme(x["titre"]))


# ------------------------------------------------------------------ recommandation

def societe(prix=15.0):
    return {"prix": prix, "devise_cours": "EUR", "devise_comptes": "EUR", "actions": 100.0,
            "annuel": [{"fin": "2025-12-31", "ca": 1100.0, "ebit": 220.0, "ebitda": 300.0, "resultat_net": 100.0, "fcf": 90.0}],
            "fx_comptes": 1.1, "fx_cours": 1.1, "region": "europe", "financier": None, "date_cours": "2026-11-02"}


def mesures(**k):
    m = {"per_mediane_regionale": 20.0, "ev_ebitda_mediane_regionale": 10.0, "dette_nette": 200.0, "croissance_ca_3ans": 6.0,
         "momentum_12m": 12.0, "fscore": {"score": 7}, "alertes": []}
    m.update(k)
    return m


def bloc_neutre(negative=None, sens=0):
    return {"note": 55, "sens": sens, "texte": "55/100 : guidance maintenue", "fiabilite": "normale",
            "guidance_negative": negative}


class TestRecommandation(unittest.TestCase):
    NEG = {"evolution": "abaissée", "date": "2026-10-20", "jours": 17}

    def test_cinq_signaux(self):
        r = R.recommander(societe(), mesures(), 70, "élevé", [], CFG_R, dynamique=bloc_neutre(), exc_guidance=CFG["exception_guidance"])
        self.assertEqual(len(r["signaux"]), 5)
        self.assertEqual(r["signaux"][-1]["libelle"], "Dynamique des résultats")
        self.assertIn("Signaux sur 5", r["justification"])
        self.assertEqual(r["si_non_detenu"], "Acheter")
        # Signal défavorable de la dynamique : plus de 3 signaux concordants sans opposition
        r = R.recommander(societe(), mesures(), 70, "élevé", [], CFG_R, dynamique=bloc_neutre(sens=-1))
        self.assertNotEqual(r["si_non_detenu"], "Acheter")

    def test_guidance_abaissee_interdit_acheter(self):
        r = R.recommander(societe(), mesures(), 70, "élevé", [], CFG_R, dynamique=bloc_neutre(self.NEG), exc_guidance=CFG["exception_guidance"])
        self.assertIn(r["si_non_detenu"], ("Acheter sur repli", "Attendre"))
        self.assertNotEqual(r["si_detenu"], "Renforcer")
        self.assertIn("guidance abaissée le 20/10/2026", r["justification"])
        self.assertIsNone(r["exception_guidance"])
        self.assertTrue(any("Guidance" in c for c in r["conditions_invalidation"]) or len(r["conditions_invalidation"]) >= 2)
        # Repli : la valorisation deviendrait favorable, mais « Acheter » reste exclu
        r = R.recommander(societe(19.0), mesures(momentum_12m=6.0), 70, "élevé", [], CFG_R, dynamique=bloc_neutre(self.NEG),
                          exc_guidance=CFG["exception_guidance"])
        if r["si_non_detenu"] == "Acheter sur repli":
            self.assertIn("reste exclu", r["justification"])

    def test_exception_baisse_deja_integree(self):
        # Valeur estimée ≈ 18,7 : à 12, décote de plus de 50 % ; cours en recul de 30 % sur 12 mois ; note et qualité favorables
        m = mesures(momentum_12m=-30.0)
        r = R.recommander(societe(12.0), m, 70, "élevé", [], CFG_R, dynamique=bloc_neutre(self.NEG), exc_guidance=CFG["exception_guidance"])
        self.assertIsNotNone(r["exception_guidance"])
        self.assertIn("paraît intégrée", r["justification"])
        self.assertTrue(ton_conforme(r["justification"]))
        # Sans recul du cours : pas d'exception
        r = R.recommander(societe(12.0), mesures(), 70, "élevé", [], CFG_R, dynamique=bloc_neutre(self.NEG), exc_guidance=CFG["exception_guidance"])
        self.assertIsNone(r["exception_guidance"])
        self.assertNotEqual(r["si_non_detenu"], "Acheter")

    def test_sans_dynamique_inchange(self):
        r = R.recommander(societe(), mesures(), 70, "élevé", [], CFG_R)
        self.assertEqual(len(r["signaux"]), 4)


if __name__ == "__main__":
    unittest.main()
