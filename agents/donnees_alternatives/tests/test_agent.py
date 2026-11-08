"""Tests de l'agent données alternatives, sans réseau : python -m unittest discover -s agents/donnees_alternatives -t .
Les données de test (agents/donnees_alternatives/tests/donnees) sont des captures réelles des 07 et 08/11/2026
(Destatis, FRED, DBnomics, USGS, Drewry, Yahoo, Indeed, TSA, Wikipédia). Les sources à clé (EIA, ENTSO-E),
Google Trends (refusé lors de la capture) et les fichiers CSV facultatifs sont simulés dans des dossiers
temporaires. Les tests n'utilisent jamais les vrais config/ et data/."""
import json
import math
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from agents.commun.essais import JOUR_TEST, copier_donnees_test
from agents.commun.sortie import ecrire_json, lire_json
from agents.donnees_alternatives import analyse as A
from agents.donnees_alternatives import sources as S
from agents.donnees_alternatives.agent import indicateurs_config, main

DOSSIER = Path(__file__).resolve().parent
DONNEES = DOSSIER / "donnees"
CFG = json.loads((DOSSIER.parent / "config.json").read_text(encoding="utf-8"))
JOUR = date(2026, 11, 7)


def mensuelle(n, depart=100.0, croissance=0.0, saison=0.0, fin=date(2026, 9, 1)):
    """n mois jusqu'à `fin` ; croissance mensuelle (%) ; amplitude saisonnière (%)."""
    pts = []
    a, m = fin.year, fin.month
    mois = []
    for _ in range(n):
        mois.append((a, m))
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    for k, (a, m) in enumerate(reversed(mois)):
        v = depart * (1 + croissance / 100) ** k * (1 + saison / 100 * math.sin(m / 12 * 2 * math.pi))
        pts.append((f"{a}-{m:02d}-01", round(v, 3)))
    return pts


def quotidienne(n, f, fin=JOUR):
    return [((fin - timedelta(days=n - 1 - k)).isoformat(), f(k)) for k in range(n)]


def ind(cle, note, categorie="transport", poids=1.0, **kw):
    return {"cle": cle, "nom": cle.replace("_", " ").capitalize(), "pays": "XX", "categorie": categorie, "poids": poids, "note": note,
            "perimee": False, "methode_note": "percentiles", "frequence": "mensuelle", "variation_12m": (note - 50) / 5,
            "source_nom": "Source de test", **kw}


class TestSeries(unittest.TestCase):
    def test_hausse_reguliere_puis_acceleration(self):
        pts = mensuelle(120, croissance=0.2)
        pts[-1] = (pts[-1][0], pts[-1][1] * 1.06)  # dernier mois nettement au-dessus
        a = A.analyser_serie(pts, "mensuelle", JOUR)
        self.assertGreater(a["variation_12m"], 7)
        self.assertGreater(a["percentile_12m"], 95)
        self.assertGreater(a["note"], 80)
        self.assertEqual(a["methode_note"], "percentiles")
        self.assertFalse(a["perimee"])

    def test_baisse_note_basse_et_sens_inverse(self):
        pts = mensuelle(120, croissance=0.2)
        pts[-1] = (pts[-1][0], pts[-1][1] * 0.94)
        self.assertLess(A.analyser_serie(pts, "mensuelle", JOUR)["note"], 20)
        self.assertGreater(A.analyser_serie(pts, "mensuelle", JOUR, sens=-1)["note"], 80)

    def test_saisonnalite(self):
        pts = mensuelle(60, saison=10)
        a = A.analyser_serie(pts, "mensuelle", JOUR)
        self.assertAlmostEqual(a["ecart_saisonnier"], 0, delta=0.5)  # le mois est conforme à sa saison
        pts[-1] = (pts[-1][0], pts[-1][1] * 1.08)
        self.assertGreater(A.analyser_serie(pts, "mensuelle", JOUR)["ecart_saisonnier"], 7)

    def test_historique_court_echelle_fixe_et_peremption(self):
        a = A.analyser_serie(mensuelle(14, croissance=1), "mensuelle", JOUR)
        self.assertEqual(a["methode_note"], "échelle fixe (historique court)")
        self.assertGreater(a["note"], 50)
        self.assertIsNone(a["percentile_12m"])
        vieux = A.analyser_serie(mensuelle(30, fin=date(2025, 12, 1)), "mensuelle", JOUR, fraicheur_jours=110)
        self.assertTrue(vieux["perimee"])

    def test_quotidienne_fenetres_28_jours(self):
        pts = quotidienne(800, lambda k: 100 + (10 if k >= 772 else 0))
        a = A.analyser_serie(pts, "quotidienne", JOUR)
        self.assertAlmostEqual(a["variation_1m"], 10, delta=0.1)
        self.assertAlmostEqual(a["variation_12m"], 10, delta=0.1)

    def test_releves_clairsemes(self):
        """Source accumulée (WCI) : deux relevés à un an d'écart suffisent pour la variation sur 12 mois."""
        a = A.analyser_serie([("2025-11-06", 1959.4), ("2026-11-05", 4389.0)], "hebdomadaire", JOUR)
        self.assertAlmostEqual(a["variation_12m"], 124, delta=0.1)

    def test_ecart_tendance_ignore_mois_manquants(self):
        pts = [p for p in mensuelle(24) if p[0][:7] not in ("2025-10", "2025-11")]
        # Seule la fenêtre qui s'achève en septembre 2025 est complète ; les suivantes contiennent les mois manquants
        self.assertEqual([m for m, _ in A.ecarts_tendance(pts)], ["2025-09-01"])

    def test_percentile(self):
        self.assertEqual(A.percentile(5, list(range(10))), None)  # moins de 12 valeurs
        self.assertEqual(A.percentile(10, list(range(20))), 52.5)


class TestScorePays(unittest.TestCase):
    def test_un_seul_indicateur_pas_de_conclusion(self):
        r = A.score_pays([ind("camions", 90)], CFG)
        self.assertIsNone(r["score"])
        self.assertIn("au moins 2", r["raison"])

    def test_acceleration_avec_deux_concordants(self):
        r = A.score_pays([ind("camions", 80), ind("emploi", 70, "emploi")], CFG)
        self.assertEqual(r["lecture"], "accélération")
        self.assertTrue(r["marque"])
        self.assertEqual(r["confiance"]["niveau"], "moyen")  # deux indicateurs : jamais « élevé »

    def test_un_seul_fort_reste_stable(self):
        r = A.score_pays([ind("camions", 100), ind("emploi", 50, "emploi")], CFG)
        self.assertEqual(r["lecture"], "stable")
        self.assertIn("un seul indicateur", r["lecture_non_retenue"])

    def test_ralentissement_et_confiance(self):
        inds = [ind("a", 25), ind("b", 30, "energie"), ind("c", 35, "emploi")]
        r = A.score_pays(inds, CFG)
        self.assertEqual(r["lecture"], "ralentissement")
        self.assertEqual(r["confiance"]["niveau"], "élevé")
        tort = A.donner_tort(r, inds)
        self.assertTrue(any("températures" in t for t in tort))

    def test_perimes_et_attention_exclus(self):
        r = A.score_pays([ind("a", 80), ind("b", 80, perimee=True), ind("c", 80, "attention")], CFG)
        self.assertIsNone(r["score"])

    def test_divergence_avec_officiel(self):
        inds = [ind("camions", 30), ind("electricite", 35, "energie")]
        r = A.score_pays(inds, CFG)
        off = A.officiel({"indicateurs": {"croissance_pib": {"libelle": "Croissance du PIB", "valeur": 4.5, "unite": "%", "note": 71},
                                          "indicateur_avance": {"libelle": "Indicateur avancé (OCDE)", "valeur": 101.2, "note": 62}}})
        d = A.divergence(r, off, inds, CFG)
        self.assertEqual(d["sens"], "officiel_solide_reel_faible")
        self.assertIn("activité réelle en retrait", d["texte"])
        self.assertIsNone(A.divergence(A.score_pays([ind("a", 55), ind("b", 52)], CFG), off, inds, CFG))


class TestAttention(unittest.TestCase):
    def test_wikipedia_et_trends(self):
        wiki = {"article": "Acme", "vues": [[f"d{k:03d}", 1000 if k < 90 else 2500] for k in range(120)]}
        trends = [[f"d{k:03d}", 20 if k < 70 else 50] for k in range(92)]
        a = A.attention(wiki, trends, CFG["attention"])
        self.assertEqual(a["tendance"], "en hausse")
        self.assertGreater(a["variation_moyenne_pct"], 100)
        self.assertIsNone(A.attention({"vues": [["d", 3]] * 120}, None, CFG["attention"]))  # trop peu de vues

    def test_nom_recherche(self):
        self.assertEqual(S.nom_recherche("Industrias Peñoles, S.A.B. de C.V."), "Industrias Peñoles")
        self.assertEqual(S.nom_recherche("Tapestry, Inc."), "Tapestry")
        self.assertEqual(S.nom_recherche("Rolls-Royce Holdings plc"), "Rolls-Royce Holdings")


class TestLectureSources(unittest.TestCase):
    def test_drewry(self):
        page = ("<p>WCI edges down 1%, but remains 124% higher YoY.</p><p>Our detailed assessment for Thursday, 05 Nov 2026</p>"
                "<p>The Drewry World Container Index (WCI), the benchmark, decreased 1% to $4,389 per 40ft container this week.</p>")
        self.assertEqual(S.lire_drewry(page), {"date": "2026-11-05", "valeur": 4389.0, "variation_12m": 124.0})

    def test_usgs(self):
        t = ("Total shipments of portland and blended cement, including imports, in the United States and Puerto Rico in July 2026 were\n"
             "an estimated 10.1 million metric tons (Mt), a 1.4 percent increase from shipments in July 2025")
        self.assertEqual(S.lire_usgs(t), {"mois": "2026-07-01", "valeur": 10.1, "variation_12m": 1.4})

    def test_tsa(self):
        page = "<tr><td>11/5/2026</td><td>2,610,670</td></tr><tr><td>11/4/2026</td><td>2,400,000</td></tr>"
        self.assertEqual(S.lire_tsa(page), [("2026-11-04", 2400000.0), ("2026-11-05", 2610670.0)])

    def test_entsoe(self):
        points = "".join(f"<Point><position>{k}</position><quantity>{1000 + k}</quantity></Point>" for k in range(1, 25))
        xml = ('<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"><TimeSeries><Period>'
               f'<timeInterval><start>2026-11-01T23:00Z</start><end>2026-11-02T23:00Z</end></timeInterval><resolution>PT60M</resolution>{points}'
               '</Period></TimeSeries></GL_MarketDocument>')
        r = S.lire_entsoe(xml)
        self.assertEqual(r, [("2026-11-02", 1013.0)])  # 24 h qui commencent le 01/11 à 23 h UTC : un seul jour complet

    def test_csv_url_et_eia(self):
        texte = "date,pays,indicateur,valeur\n2026-09-01,IN,no2,51.2\n2026-09-01,IN,lumieres,3.1\n2026-08-01,in,no2,49\n"
        self.assertEqual(S.lire_csv_url(texte, "IN", "no2"), [("2026-08-01", 49.0), ("2026-09-01", 51.2)])
        self.assertEqual(S.lire_eia({"response": {"data": [{"period": "2026-11-01", "value": "1000"}]}}), [("2026-11-01", 1000.0)])

    def test_nbs(self):
        objet = {"returncode": 200, "returndata": {"datanodes": [
            {"code": "zb.A02090Y01_sj.202609", "data": {"data": 15012.3, "hasdata": True}, "wds": [{"wdcode": "zb", "valuecode": "A02090Y01"}, {"wdcode": "sj", "valuecode": "202609"}]},
            {"code": "zb.A02090Y01_sj.202602", "data": {"data": 0, "hasdata": False}, "wds": [{"wdcode": "zb", "valuecode": "A02090Y01"}, {"wdcode": "sj", "valuecode": "202602"}]},
            {"code": "zb.A02090Y03_sj.202609", "data": {"data": -4.1, "hasdata": True}, "wds": [{"wdcode": "zb", "valuecode": "A02090Y03"}, {"wdcode": "sj", "valuecode": "202609"}]}]}}
        self.assertEqual(S.lire_nbs(objet, "A02090Y01"), [("2026-09-01", 15012.3)])
        with self.assertRaises(S.ErreurSource):
            S.lire_nbs({"returncode": 501, "returndata": "erreur"}, "A02090Y01")

    def test_douanes_taiwan(self):
        texte = ('\ufeff"年度","月份","出口總值(新臺幣千元)","出口(新臺幣千元)"\n'
                 '"115","8","2655171348","2405929261"\n"114","12","1","1"\n')
        self.assertEqual(S.lire_douanes_taiwan(texte), [("2025-12-01", 0.0), ("2026-08-01", 2655.171)])
        with self.assertRaises(S.ErreurSource):
            S.lire_douanes_taiwan('"a","b"\n1,2\n')

    def test_source_de_secours(self):
        f = S.FournisseurReel.__new__(S.FournisseurReel)
        f._nbs = lambda p, j: (_ for _ in ()).throw(S.ErreurSource("HTTP 403"))
        f._dbnomics = lambda p, j: ([("2025-12-01", 1.0)], "API DBnomics")
        ind = {"cle": "ciment_cn", "source": "nbs", "params": {}, "secours": {"source": "dbnomics", "nom": "DBnomics"}}
        points, detail = f.serie(ind, JOUR)
        self.assertEqual(points, [("2025-12-01", 1.0)])
        self.assertTrue(detail.startswith("secours : DBnomics"))
        with self.assertRaises(S.ErreurSource):
            f.serie({**ind, "secours": None}, JOUR)

    def test_captures_reelles_lisibles(self):
        d = json.loads((DONNEES / "camions_de.json").read_text(encoding="utf-8"))
        self.assertGreater(len(d["points"]), 6000)
        self.assertTrue(all(len(p) == 2 for p in d["points"][:10]))


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="alt-"))
        self.data = self.d / "data"
        copier_donnees_test(self.data, ("pays.json",))
        # Liste de surveillance et pépites de test (noms présents dans la capture Wikipédia)
        ecrire_json(self.d / "surveillance.json", {"societes": [{"ticker": "NXT.L", "pays": "GB"}]})
        ecrire_json(self.data / "entreprises.json", {"meta": {}, "donnees": [{"ticker": "NXT.L", "nom": "NEXT plc", "pays": "GB"}]})
        ecrire_json(self.data / "pepites.json", {"meta": {}, "donnees": [{"ticker": "TPR", "nom": "Tapestry, Inc.", "pays": "US"},
                                                                          {"ticker": "2914.T", "nom": "Japan Tobacco Inc.", "pays": "JP"}]})
        self.tests = self.d / "donnees"
        shutil.copytree(DONNEES, self.tests)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def lancer(self, jour="2026-11-07"):
        return main(["--test", "--donnees-test", str(self.tests), "--data", str(self.data), "--surveillance", str(self.d / "surveillance.json"),
                     "--date", jour])

    def test_execution_complete(self):
        self.assertEqual(self.lancer(), 0)
        d = lire_json(self.data / "donnees_alternatives.json")
        self.assertFalse(d["meta"]["fictif"])
        pays = {p["code"]: p for p in d["donnees"]["pays"]}
        # Chine : ciment et électricité publiés par DBnomics jusqu'à décembre 2025 seulement : périmés, pas de score
        self.assertIsNone(pays["CN"]["score"])
        # Pays à un seul indicateur (Indeed) : pas de conclusion
        self.assertIsNone(pays["FR"]["score"])
        for code in ("DE", "US"):
            self.assertIsNotNone(pays[code]["score"])
            self.assertIn(pays[code]["lecture"], ("accélération", "stable", "ralentissement"))
            self.assertTrue(2 <= len(pays[code]["ce_qui_pourrait_me_donner_tort"]) <= 3)
            self.assertIn(pays[code]["confiance"]["niveau"], ("faible", "moyen"))
        inds = {i["cle"]: i for i in d["donnees"]["indicateurs"]}
        self.assertNotIn("electricite_fr", inds)  # ENTSO-E sans clé : ignorée
        # Satellites désactivés par défaut : ni interrogés, ni affichés, ni comptés dans la santé
        self.assertFalse([k for k in inds if k.startswith(("no2_", "lumieres_"))])
        self.assertFalse([s for s in d["donnees"]["sources_ignorees"] if "Sentinel" in s or "Black Marble" in s])
        # Chine : API du NBS inaccessible lors de la capture → DBnomics en secours, date de la dernière donnée explicite
        cn = inds["ciment_cn"]
        self.assertEqual(cn["etat_source"], "secours")
        self.assertTrue(cn["perimee"])
        self.assertIn("Dernière donnée disponible : décembre 2025", cn["lecture"])
        # Taïwan et Corée : exportations mensuelles, avec la mention « pas de donnée anticipée gratuite »
        for cle in ("exportations_tw", "exportations_kr"):
            self.assertIn("mensuel, pas de donnée anticipée gratuite", inds[cle]["mention"])
            self.assertIsNotNone(inds[cle]["note"])
        self.assertEqual(inds["exportations_tw"]["date"], "2026-08-01")
        self.assertIsNone(inds["exportations_tw"]["percentile_tendance"])  # série brute : variation sur 12 mois seulement
        self.assertNotIn("exportations_kr_20j", inds)  # option CSV sans adresse : ignorée
        de = inds["camions_de"]
        for champ in ("valeur", "date", "variation_1m", "variation_12m", "ecart_tendance", "ecart_saisonnier", "percentile_12m", "note"):
            self.assertIsNotNone(de[champ], champ)
        self.assertLessEqual(len(de["serie"]), CFG["historique_points"])
        self.assertEqual(d["donnees"]["tableau_mondial"][0], "camions_de")
        self.assertIn("fret_conteneurs", d["donnees"]["tableau_mondial"])
        # Attention du public : information (capture Wikipédia), sans entrer dans les scores
        self.assertTrue({a["ticker"] for a in d["donnees"]["attention"]} >= {"TPR", "2914.T"})
        # Fichiers annexes
        self.assertTrue((self.data / "recap" / "donnees-alternatives-2026-11-07.md").exists())
        self.assertTrue((self.data / "historique" / "donnees_alternatives" / "2026-11-07.json").exists())
        self.assertTrue((self.data / "historique" / "donnees_alternatives" / "accumule.json").exists())
        j = lire_json(self.data / "journal" / "agent-donnees-alternatives.json")
        s = j["meta"]["sante"]
        self.assertEqual((s["agent"], s["workflow"], s["ordre"]), ("donnees-alternatives", "agent-donnees-alternatives.yml", 12))
        self.assertFalse(s["degrade"])
        etats = {x["nom"]: x["etat"] for x in s["sources"]}
        self.assertEqual(etats["ENTSO-E, charge réalisée"], "non configurée")
        self.assertEqual(etats["Bureau national des statistiques de Chine — Production de ciment"], "secours")
        self.assertNotIn("NASA Black Marble", etats)
        index = lire_json(self.data / "journal" / "index.json")
        self.assertIn("agent-donnees-alternatives.json", [e["fichier"] for e in index["donnees"]])

    def test_source_en_panne_degrade_l_agent(self):
        self.assertEqual(self.lancer(), 0)
        (self.tests / "tsa_us.json").unlink()
        self.assertEqual(self.lancer("2026-11-08"), 0)
        s = lire_json(self.data / "journal" / "agent-donnees-alternatives.json")["meta"]["sante"]
        self.assertTrue(s["degrade"])
        self.assertTrue(any("Passagers" in r for r in s["raisons"]))
        etats = {x["nom"]: x["etat"] for x in s["sources"]}
        self.assertEqual(etats["TSA"], "échec")

    def test_cle_configuree_et_signaux(self):
        """Électricité allemande et française simulées (comme avec ENTSOE_API_KEY) : ralentissement marqué en Allemagne."""
        baisse = quotidienne(1100, lambda k: 60000 * (0.85 if k >= 1050 else 1.0))
        for cle in ("electricite_de", "electricite_fr"):
            (self.tests / f"{cle}.json").write_text(json.dumps({"points": baisse, "detail": "simulation"}), encoding="utf-8")
        camions = json.loads((self.tests / "camions_de.json").read_text(encoding="utf-8"))
        camions["points"] = [[d, v * (0.85 if d >= "2026-10-01" else 1)] for d, v in camions["points"]]
        (self.tests / "camions_de.json").write_text(json.dumps(camions), encoding="utf-8")
        self.assertEqual(self.lancer(), 0)
        pays = {p["code"]: p for p in lire_json(self.data / "donnees_alternatives.json")["donnees"]["pays"]}
        self.assertEqual(pays["DE"]["indicateurs_utilises"], 3)
        self.assertEqual(pays["DE"]["lecture"], "ralentissement")
        self.assertIsNotNone(pays["FR"]["score"])  # Indeed + électricité : deux indicateurs
        sig = lire_json(self.data / "signaux" / "donnees_alternatives.json")["donnees"]
        types = {(s["type"], s["cle"]) for s in sig}
        self.assertIn(("activite_ralentissement", "DE"), types)
        self.assertTrue(all(s["pays"] for s in sig if s["type"].startswith("activite")))
        # Seconde exécution identique : pas de nouveau signal (seulement les changements)
        self.assertEqual(self.lancer("2026-11-08"), 0)
        sig2 = lire_json(self.data / "signaux" / "donnees_alternatives.json")["donnees"]
        self.assertFalse([s for s in sig2 if s["date"] == "2026-11-08" and s["type"].startswith("activite")])

    def test_trends_simule(self):
        (self.tests / "attention_trends.json").write_text(json.dumps(
            {"Tapestry": [[(JOUR - timedelta(days=91 - k)).isoformat(), 20 if k < 64 else 60] for k in range(92)]}), encoding="utf-8")
        self.assertEqual(self.lancer(), 0)
        att = {a["ticker"]: a for a in lire_json(self.data / "donnees_alternatives.json")["donnees"]["attention"]}
        self.assertIn("trends", att["TPR"])
        self.assertGreater(att["TPR"]["trends"]["variation_pct"], 100)

    def test_textes_conformes(self):
        self.assertEqual(self.lancer(), 0)
        d = lire_json(self.data / "donnees_alternatives.json")["donnees"]
        textes = [p["texte"] for p in d["pays"]] + [i["lecture"] for i in d["indicateurs"]]
        self.assertTrue(A.conformes(textes))

    def test_configuration(self):
        inds = indicateurs_config(CFG)
        cles = [i["cle"] for i in inds]
        self.assertEqual(len(cles), len(set(cles)))
        self.assertIn("offres_emploi_us", cles)
        self.assertNotIn("no2_in", cles)  # satellites désactivés par défaut
        self.assertIn("no2_in", [i["cle"] for i in indicateurs_config({**CFG, "satellites": {**CFG["satellites"], "actif": True}})])
        for i in inds:
            self.assertIn(i["frequence"], CFG["fraicheur_jours"])
            self.assertIn(i["categorie"], CFG["categories"])


class TestAgentPays(unittest.TestCase):
    """Sous-note « Activité réelle » de l'agent pays : présente seulement pour les pays qui ont un score."""

    def test_sous_note_activite_reelle(self):
        from agents.pays.agent import main as pays
        d = Path(tempfile.mkdtemp(prefix="alt-pays-"))
        try:
            alt = {"meta": {"fictif": False}, "donnees": {"date": JOUR_TEST, "indicateurs": [
                {"cle": "a", "nom": "Camions", "note": 80}, {"cle": "b", "nom": "Électricité", "note": 75}],
                "pays": [{"code": "DE", "score": 78.0, "lecture": "accélération", "indicateurs_utilises": 2, "indicateurs": ["a", "b"],
                          "confiance": {"niveau": "moyen"}},
                         {"code": "FR", "score": None, "indicateurs": ["a"]}]}}
            ecrire_json(d / "alt.json", alt)
            commun = ["--test", "--donnees-test", str(Path(__file__).resolve().parents[2] / "pays" / "tests" / "donnees"),
                      "--historique", str(d / "historique"), "--journal", str(d / "journal.json"), "--recap", str(d / "recap"), "--date", JOUR_TEST]
            self.assertEqual(pays(commun + ["--sortie", str(d / "avec.json"), "--alternatives", str(d / "alt.json")]), 0)
            self.assertEqual(pays(commun + ["--sortie", str(d / "sans.json"), "--alternatives", str(d / "absent.json")]), 0)
            avec = {p["code"]: p for p in lire_json(d / "avec.json")["donnees"]}
            sans = {p["code"]: p for p in lire_json(d / "sans.json")["donnees"]}
            de = avec["DE"]["indicateurs"]["activite_reelle"]
            self.assertEqual((de["note"], de["lecture"]), (78, "accélération"))
            self.assertNotIn("activite_reelle", avec["FR"]["indicateurs"])
            # Pays sans score : note et couverture inchangées
            self.assertEqual(avec["FR"]["note"], sans["FR"]["note"])
            self.assertEqual(avec["FR"]["confiance"], sans["FR"]["confiance"])
            # Pays avec score : la sous-note pèse dans la note brute
            self.assertNotEqual(avec["DE"]["note_brute"], sans["DE"]["note_brute"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
