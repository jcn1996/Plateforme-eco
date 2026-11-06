"""Tests de l'agent flux commerciaux, sans réseau : python -m unittest discover -s agents/flux -t .

Ils ne lisent ni ne modifient les vrais config/ et data/ : tout se passe dans un dossier temporaire,
avec les réponses enregistrées du FMI et de UN Comtrade (tests/donnees/, voir capturer_donnees_test.py).
"""
import logging
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.commun.sortie import ecrire_json, lire_json
from agents.flux import agent, controles

DATE_TEST = "2026-08-20"
MAINTENANT = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
TOUS = list(agent.CONFIG["pays"])


def lancer(dossier: Path, donnees_test: Path = agent.DONNEES_TEST, date: str = DATE_TEST) -> int:
    return agent.main(["--test", "--data", str(dossier), "--donnees-test", str(donnees_test), "--date", date])


class Base(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.d = Path(tempfile.mkdtemp(prefix="flux-"))

    def tearDown(self):
        logging.disable(logging.NOTSET)
        shutil.rmtree(self.d, ignore_errors=True)


class TestMois(unittest.TestCase):
    def test_decaler(self):
        self.assertEqual(agent.decaler("2026-07", -12), "2025-07")
        self.assertEqual(agent.decaler("2026-01", -1), "2025-12")
        self.assertEqual(agent.decaler("2025-12", 1), "2026-01")
        self.assertEqual(agent.ecart_mois("2026-07", "2026-11"), 4)


class TestCalcul(unittest.TestCase):
    def test_exportations_puis_miroir(self):
        series = {
            ("X", "FR", "DE"): {"2025-07": 8e9, "2026-07": 10e9},   # exportations de la France
            ("M", "DE", "FR"): {"2025-07": 9e9, "2026-07": 10.5e9},  # miroir, même mois : comparé (écart 5 %)
            ("M", "JP", "TW"): {"2025-07": 20e9, "2026-07": 19e9},  # Taïwan ne déclare pas : miroir japonais
            ("X", "KR", "MX"): {"2025-06": 30e9, "2026-06": 30e9},
            ("M", "MX", "KR"): {"2025-07": 25e9, "2026-07": 26e9},  # miroir plus récent : retenu
        }
        flux = {(f["de"], f["vers"]): f for f in agent.calculer_flux(series, ["FR", "DE", "JP", "TW", "MX", "KR"])}
        fr = flux[("FR", "DE")]
        self.assertEqual((fr["montant_md"], fr["periode"], fr["mesure"], fr["declarant"]), (10.0, "2026-07", "exportations", "FR"))
        self.assertEqual((fr["variation_12m_pct"], fr["tendance"]), (25.0, "hausse"))
        self.assertEqual((fr["controle"], fr["ecart_max_pct"]), ("concordantes", 5.0))
        self.assertEqual([s["retenue"] for s in fr["sources"]], [True, False])
        tw = flux[("TW", "JP")]
        self.assertEqual((tw["mesure"], tw["declarant"], tw["variation_12m_pct"], tw["tendance"]), ("importations", "JP", -5.0, "baisse"))
        self.assertEqual(tw["controle"], "une seule source")
        kr = flux[("KR", "MX")]
        self.assertEqual((kr["periode"], kr["mesure"], kr["tendance"]), ("2026-07", "importations", "stable"))
        self.assertNotIn(("DE", "FR"), flux)  # aucune donnée dans ce sens

    def test_variation_inconnue(self):
        f = agent.calculer_flux({("X", "FR", "DE"): {"2026-07": 1e9}}, ["FR", "DE"])[0]
        self.assertIsNone(f["variation_12m_pct"])
        self.assertEqual(f["tendance"], "inconnue")
        self.assertFalse(f["a_verifier"])


class TestControles(unittest.TestCase):
    SERIES = {
        ("X", "MX", "US"): {"2025-07": 46.75e9, "2026-07": 69.75e9},   # déclaration du Mexique
        ("M", "US", "MX"): {"2025-07": 45.37e9, "2026-07": 60.55e9},   # déclaration des États-Unis (FMI)
    }

    def test_etats_unis_sans_census(self):
        """Sans clé Census : la déclaration des États-Unis relayée par le FMI est la source officielle retenue."""
        f = agent.calculer_flux(self.SERIES, ["MX", "US"])[0]
        self.assertEqual((f["montant_md"], f["declarant"], f["source"]), (60.55, "US", agent.SOURCE_FMI))
        self.assertEqual(f["controle"], "sources divergentes")  # 69,75 contre 60,55 : 15,2 %
        self.assertEqual(f["ecart_max_pct"], 15.2)
        self.assertEqual(f["variation_12m_pct"], 33.5)
        self.assertFalse(f["a_verifier"])

    def test_census_retenu(self):
        census = {("M", "US", "MX"): {"2025-07": 45.7e9, "2026-07": 60.9e9}}
        f = agent.calculer_flux(self.SERIES, ["MX", "US"], census=census)[0]
        self.assertEqual((f["montant_md"], f["source"], f["declarant"]), (60.9, agent.SOURCE_CENSUS, "US"))
        # La déclaration américaine du FMI (même origine que le Census) n'est pas comptée comme seconde source
        self.assertEqual([s["nom"] for s in f["sources"]], [agent.SOURCE_CENSUS, agent.SOURCE_FMI])
        self.assertEqual(f["sources"][1]["declarant"], "MX")

    def test_forte_variation(self):
        series = {("X", "VN", "JP"): {"2025-07": 10e9, "2026-07": 15e9},   # +50 %
                  ("M", "JP", "VN"): {"2025-07": 10e9, "2026-07": 14.5e9}}  # +45 % : confirme
        f = agent.calculer_flux(series, ["VN", "JP"])[0]
        self.assertEqual((f["a_verifier"], f["variation_confirmee"]), (False, True))
        series[("M", "JP", "VN")] = {"2025-07": 14e9, "2026-07": 14.5e9}   # +3,6 % : ne confirme pas
        f = agent.calculer_flux(series, ["VN", "JP"])[0]
        self.assertEqual((f["a_verifier"], f["variation_confirmee"]), (True, False))
        del series[("M", "JP", "VN")]                                        # une seule source
        self.assertTrue(agent.calculer_flux(series, ["VN", "JP"])[0]["a_verifier"])

    def test_somme_et_total(self):
        series = {("X", "FR", "DE"): {"2026-07": 6e9}, ("X", "FR", "IT"): {"2026-07": 5e9},
                  ("X", "FR", controles.MONDE): {"2026-07": 10e9}}
        totaux = controles.controler_totaux(series, ["FR", "DE", "IT"])
        self.assertEqual(totaux[0]["statut"], "somme supérieure au total")
        self.assertEqual((totaux[0]["somme_partenaires_md"], totaux[0]["total_md"]), (11.0, 10.0))
        flux = agent.calculer_flux(series, ["FR", "DE", "IT"], totaux=totaux)
        self.assertTrue(all(f["controle"] == "sources divergentes" for f in flux))
        self.assertIn("supérieures au total", flux[0]["raisons"][0])
        series[("X", "FR", controles.MONDE)] = {"2026-07": 50e9}
        self.assertEqual(controles.controler_totaux(series, ["FR", "DE", "IT"])[0]["statut"], "ok")

    def test_total_banque_mondiale(self):
        mois = [f"2025-{m:02d}" for m in range(1, 13)]
        series = {("X", "TW", "JP"): {m: 1e9 for m in mois}}  # pas de total FMI
        self.assertEqual(controles.controler_totaux(series, ["TW", "JP"])[0]["statut"], "total indisponible")
        t = controles.controler_totaux(series, ["TW", "JP"], {"TW": {"2025": 10e9}})[0]
        self.assertEqual((t["statut"], t["somme_partenaires_md"], t["source_total"]), ("somme supérieure au total", 12.0,
                                                                                         "Banque mondiale (total annuel)"))


    def test_selection(self):
        codes = ["A", "B", "C", "D", "E"]
        flux = [{"de": a, "vers": b, "montant_md": float(i)} for i, (a, b) in
                enumerate((a, b) for a in codes for b in codes if a != b)]
        choisis = agent.selectionner(flux, codes, n=2, m=3)
        for c in codes:
            self.assertEqual(sum(f["top_de"] for f in choisis if f["de"] == c), 2)
            self.assertEqual(sum(f["top_vers"] for f in choisis if f["vers"] == c), 2)
        mondiaux = [f for f in choisis if f["mondial"]]
        self.assertEqual([f["montant_md"] for f in mondiaux], [19.0, 18.0, 17.0])
        self.assertTrue(all(f["top_de"] or f["top_vers"] or f["mondial"] for f in choisis))
        self.assertLess(len(choisis), len(flux))  # les petits flux sont écartés
        self.assertEqual(choisis, sorted(choisis, key=lambda f: -f["montant_md"]))


class TestSources(unittest.TestCase):
    def test_fmi_enregistre(self):
        series = agent.lire_fmi(agent.LecteurTest(agent.DONNEES_TEST), TOUS, "2025-01")
        self.assertIn(("X", "MX", "US"), series)
        self.assertIn(("M", "US", "TW"), series)
        self.assertNotIn("TW", {decl for (_, decl, _) in series})  # Taïwan ne déclare pas au FMI
        self.assertGreater(series[("X", "MX", "US")]["2026-07"], 1e10)

    def test_comtrade_enregistre(self):
        series = agent.lire_comtrade(agent.LecteurTest(agent.DONNEES_TEST), TOUS, MAINTENANT)
        mois = {p for s in series.values() for p in s}
        self.assertEqual(mois, {"2026-06", "2025-06"})
        self.assertIn(("X", "US", "CA"), series)


class TestAgent(Base):
    def test_execution_complete(self):
        ecrire_json(self.d / "pays.json", {"meta": {}, "donnees": [{"code": c} for c in TOUS]})
        # Point de départ : l'ancien fichier fictif
        ecrire_json(self.d / "flux.json", {"meta": {"fictif": True}, "donnees": [{"de": "US", "vers": "IN", "montant_md": 18.4}]})
        self.assertEqual(lancer(self.d), 0)
        f = lire_json(self.d / "flux.json")
        self.assertFalse(f["meta"]["fictif"])
        self.assertEqual(f["meta"]["source"], agent.SOURCE_FMI)
        self.assertEqual(f["meta"]["periode_recente"], "2026-07")
        self.assertIn("décalées de 1 à 2 mois", f["meta"]["mention"])
        flux = f["donnees"]
        self.assertEqual(sum(x["mondial"] for x in flux), agent.CONFIG["flux_mondiaux"])
        for c in TOUS:
            self.assertLessEqual(sum(x["top_de"] for x in flux if x["de"] == c), agent.CONFIG["partenaires_par_pays"])
        self.assertTrue(any(x["de"] == "TW" for x in flux))
        self.assertTrue(all(x["tendance"] in ("hausse", "baisse", "stable", "inconnue") for x in flux))
        self.assertTrue(all(x["controle"] in ("concordantes", "sources divergentes", "une seule source") for x in flux))
        # Flux des États-Unis : source officielle américaine (Census Bureau, données de test)
        mx = next(x for x in flux if (x["de"], x["vers"]) == ("MX", "US"))
        self.assertEqual((mx["source"], mx["declarant"], mx["controle"]), (agent.SOURCE_CENSUS, "US", "sources divergentes"))
        self.assertLess(mx["montant_md"], 69.75)  # la déclaration mexicaine (69,75 Md$) n'est plus retenue
        # Somme des exportations vers les partenaires suivis ≤ total, pour chaque pays déclarant
        totaux = lire_json(self.d / "journal" / "agent-flux.json")["controles"]["totaux"]
        self.assertTrue(all(t["statut"] == "ok" for t in totaux if t["pays"] != "TW"), totaux)

        j = lire_json(self.d / "journal" / "agent-flux.json")
        s = j["meta"]["sante"]
        self.assertEqual((s["agent"], s["workflow"], s["sources_ok"], s["degrade"]), ("flux", "agent-flux.yml", 2, False))
        self.assertEqual(s["planning"]["crons"], ["23 5 * * 2"])
        self.assertEqual(s["prochaine_prevue"], "2026-08-25T05:23:00Z")  # mardi suivant
        self.assertEqual([x["nom"] for x in s["sources"]], [agent.SOURCE_FMI, agent.SOURCE_CENSUS])
        self.assertIn("resume", j["controles"])
        self.assertEqual(j["donnees"][-1]["flux"], len(flux))  # résumé des contrôles journalisé
        index = lire_json(self.d / "journal" / "index.json")["donnees"]
        self.assertIn("agent-flux.json", [e["fichier"] for e in index])

        # Deuxième exécution identique : le fichier des flux n'est pas réécrit
        genere = f["meta"]["genere_le"]
        lancer(self.d)
        self.assertEqual(lire_json(self.d / "flux.json")["meta"]["genere_le"], genere)

    def test_sans_cle_census(self):
        agent.main(["--test", "--data", str(self.d), "--date", DATE_TEST, "--census-cle", ""])
        s = lire_json(self.d / "journal" / "agent-flux.json")["meta"]["sante"]
        census = next(x for x in s["sources"] if x["nom"] == agent.SOURCE_CENSUS)
        self.assertEqual(census["etat"], "non configurée")
        self.assertFalse(s["degrade"])  # clé facultative : ni comptée, ni en échec
        mx = next(x for x in lire_json(self.d / "flux.json")["donnees"] if (x["de"], x["vers"]) == ("MX", "US"))
        self.assertEqual((mx["source"], mx["declarant"], mx["montant_md"]), (agent.SOURCE_FMI, "US", 60.55))

    def test_secours_comtrade(self):
        donnees = self.d / "donnees"
        donnees.mkdir()
        for motif in ("comtrade_*.json", "census_*.json", "banque_mondiale.json"):
            for p in agent.DONNEES_TEST.glob(motif):
                shutil.copy(p, donnees)  # pas de réponse du FMI
        self.assertEqual(lancer(self.d / "data", donnees), 0)
        f = lire_json(self.d / "data" / "flux.json")
        self.assertEqual(f["meta"]["source"], agent.SOURCE_COMTRADE)
        # Comtrade : juin 2026 ; les flux des États-Unis prennent le Census Bureau, plus récent (juillet)
        self.assertEqual({x["periode"] for x in f["donnees"] if "US" not in (x["de"], x["vers"])}, {"2026-06"})
        self.assertEqual({x["source"] for x in f["donnees"] if "US" in (x["de"], x["vers"])}, {agent.SOURCE_CENSUS})
        s = lire_json(self.d / "data" / "journal" / "agent-flux.json")["meta"]["sante"]
        self.assertEqual([x["etat"] for x in s["sources"]], ["échec", "secours", "ok", "ok"])  # FMI, Comtrade, Census, Banque mondiale
        self.assertTrue(s["degrade"])
        # Sans total « Monde » dans ces réponses Comtrade, le total annuel de la Banque mondiale sert au contrôle
        totaux = lire_json(self.d / "data" / "journal" / "agent-flux.json")["controles"]["totaux"]
        self.assertTrue(all(t["statut"] == "total indisponible" or t["source_total"].startswith("Banque") for t in totaux))

    def test_toutes_sources_en_panne(self):
        ancien = {"meta": {"fictif": False, "source": "x"}, "donnees": [{"de": "US", "vers": "CA", "montant_md": 1.0}]}
        ecrire_json(self.d / "data" / "flux.json", ancien)
        vide = self.d / "vide"
        vide.mkdir()
        self.assertEqual(lancer(self.d / "data", vide), 0)
        self.assertEqual(lire_json(self.d / "data" / "flux.json"), ancien)  # dernier fichier conservé
        s = lire_json(self.d / "data" / "journal" / "agent-flux.json")["meta"]["sante"]
        self.assertEqual([x["etat"] for x in s["sources"]][:2], ["échec", "échec"])
        self.assertEqual(s["sources_ok"], 0)

    def test_donnees_perimees(self):
        lancer(self.d, date="2027-06-01")  # dernier mois 2026-07 : 11 mois de retard
        s = lire_json(self.d / "journal" / "agent-flux.json")["meta"]["sante"]
        self.assertEqual(s["sources"][0]["etat"], "périmée")
        self.assertTrue(s["degrade"])

    def test_pays_suivis(self):
        ecrire_json(self.d / "pays.json", {"meta": {}, "donnees": [{"code": "FR"}, {"code": "DE"}, {"code": "XX"}]})
        self.assertEqual(agent.codes_suivis(self.d), ["FR", "DE"])
        self.assertEqual(agent.codes_suivis(self.d / "absent"), TOUS)


if __name__ == "__main__":
    unittest.main()
