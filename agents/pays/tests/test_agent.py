"""
Tests de l'agent pays (sans réseau) : python -m unittest discover -s agents -t .
Ils utilisent les données de test de agents/pays/tests/donnees.
"""
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from agents.commun.sortie import lire_json
from agents.pays import croisement, notation, textes
from agents.pays.agent import main, qualite, sources_sante

DONNEES = Path(__file__).resolve().parent / "donnees"
JOUR = "2026-11-02"


class TestNotation(unittest.TestCase):
    def test_regles_simples(self):
        self.assertEqual(notation.note_croissance(2), 51)
        self.assertEqual(notation.note_inflation(2.0, 2.0), 90)        # inflation à la cible
        self.assertEqual(notation.note_inflation(4.0, 2.0), 60)        # 2 points d'écart
        self.assertEqual(notation.note_inflation(-1.0, 2.0), 45)       # déflation pénalisée aussi
        self.assertLessEqual(notation.note_inflation(30, 5), 10)       # inflation très élevée
        self.assertEqual(notation.note_taux_reel(1.5, "stable"), 80)   # zone saine
        self.assertLess(notation.note_taux_reel(-4, "stable"), 30)     # très négatif = risque
        self.assertEqual(notation.note_valorisation(0), 60)
        self.assertEqual(notation.note_momentum(0), 50)

    def test_pas_de_conclusion_forte_sans_deux_indicateurs(self):
        p = {"croissance_pib": 0.2, "inflation": 0.2, "momentum": 0.15}
        un_seul = {"croissance_pib": {"note": 100}, "inflation": {"note": 60}, "momentum": {"note": 60}}
        r = notation.note_globale(un_seul, p)
        self.assertTrue(r["ramenee"])
        self.assertEqual(r["note"], 64)
        deux = {"croissance_pib": {"note": 90}, "inflation": {"note": 80}, "momentum": {"note": 60}}
        self.assertFalse(notation.note_globale(deux, p)["ramenee"])
        # Une valeur « à vérifier » ne compte pas comme confirmation
        douteux = {"croissance_pib": {"note": 90}, "inflation": {"note": 80, "a_verifier": True}, "momentum": {"note": 60}}
        self.assertTrue(notation.note_globale(douteux, p)["ramenee"])

    def test_indicateur_manquant_exclu_et_confiance(self):
        p = {"a": 0.5, "b": 0.5}
        r = notation.note_globale({"a": {"note": 70, "libelle": "A"}, "b": {"note": None, "libelle": "B"}}, p)
        self.assertEqual(r["couverture"], 0.5)
        c = notation.confiance({"a": {"note": 70, "libelle": "A"}, "b": {"note": None, "libelle": "B"}}, p, r["couverture"])
        self.assertEqual(c["niveau"], "faible")


class TestTextes(unittest.TestCase):
    def test_mots_interdits(self):
        self.assertFalse(textes.ton_conforme("Une croissance exceptionnelle"))
        self.assertFalse(textes.ton_conforme("C'est INCONTOURNABLE"))
        self.assertFalse(textes.ton_conforme("l'explosion des prix"))
        self.assertTrue(textes.ton_conforme("Croissance de 2,1 % selon le FMI."))


class TestSante(unittest.TestCase):
    def test_sources_sante(self):
        etats = {"fmi": "ok", "bis": "erreur : HTTP 503", "fred": "erreur : clé FRED_API_KEY absente : source ignorée",
                 "ocde": "partiel (3/10)", "textes": "règles"}
        echecs = [{"pays": "US", "indicateur": "inflation", "source": "BLS", "statut": "rejetée",
                   "raison": "trop ancienne (donnée mensuelle de 2025-01, plus de 6 mois)", "date": "2025-01"}]
        journal = {"donnees": [{"genere_le": "2026-10-30T06:01:00Z", "etat_des_sources": {"bis": "ok"}},
                               {"genere_le": "2026-10-31T06:01:00Z", "etat_des_sources": {"bis": "erreur : x"}}]}
        res = {s["nom"]: s for s in sources_sante(etats, echecs, journal)}
        self.assertNotIn("textes", res)
        self.assertEqual(res["bis"]["etat"], "échec")
        self.assertEqual(res["bis"]["derniere_donnee_valide"], "2026-10-30T06:01:00Z")
        self.assertEqual(res["fred"]["etat"], "non configurée")
        self.assertEqual(res["ocde"]["etat"], "partielle")
        self.assertEqual(res["BLS"]["etat"], "périmée")
        self.assertEqual(res["BLS"]["derniere_donnee_valide"], "2025-01")


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.sortie = self.dossier / "pays.json"
        # Point de départ : l'ancien fichier fictif (avec les flux de capitaux)
        fictif = {"meta": {"fictif": True, "genere_le": "2026-11-01T07:00:00Z"},
                  "donnees": [{"code": "FR", "note": 58, "flux": [{"vers": "US", "montant_md": 4.4}]}]}
        self.sortie.write_text(json.dumps(fictif), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dossier)

    def lancer(self, donnees=DONNEES, jour=JOUR):
        return main(["--test", "--donnees-test", str(donnees), "--sortie", str(self.sortie),
                     "--historique", str(self.dossier / "historique"), "--flux", str(self.dossier / "flux.json"),
                     "--journal", str(self.dossier / "journal.json"), "--recap", str(self.dossier / "recap"), "--date", jour])

    def copie_donnees(self):
        modif = self.dossier / "donnees"
        shutil.copytree(DONNEES, modif)
        return modif

    def test_execution_complete(self):
        self.assertEqual(self.lancer(), 0)
        f = lire_json(self.sortie)
        self.assertEqual(f["meta"]["source"], "agent-pays")
        self.assertIs(f["meta"]["fictif"], False)
        self.assertEqual(len(f["donnees"]), 31)
        for p in f["donnees"]:
            self.assertIn(p["confiance"]["niveau"], ("faible", "moyen", "élevé"))
            self.assertTrue(p["contre_scenario"])
            for t in [p["verdict"], *p["contre_scenario"], *p["lecture"].values()]:
                self.assertTrue(textes.ton_conforme(t), t)
            for ind in {**p["indicateurs"], **p["detail"]}.values():
                if ind.get("valeur") is not None:
                    self.assertTrue(ind["date"] and ind["source"], ind)   # date et source exactes
            self.assertIsNone(p["detail"]["flux_etrangers"]["valeur"])   # non disponible
        self.assertTrue((self.dossier / "historique" / f"{JOUR}.json").exists())
        # Vérification croisée : chaque indicateur publié décrit ses sources et la valeur retenue
        for p in f["donnees"]:
            self.assertIn("qualite", p)
            for ind in p["indicateurs"].values():
                if ind.get("valeur") is not None:
                    self.assertIn(ind["verification"], ("concordant", "divergent", "source_unique"))
                    self.assertEqual(sum(s["statut"] == "retenue" for s in ind["sources"]), 1, ind)
                    self.assertIn(ind["confiance"], ("faible", "moyen", "élevé"))
                    if ind["verification"] == "source_unique":
                        self.assertNotEqual(ind["confiance"], "élevé")   # une seule source : « moyen » au plus
        # Journal des sources et récapitulatif
        self.assertTrue(lire_json(self.dossier / "journal.json")["donnees"])
        recap = (self.dossier / "recap" / f"pays-{JOUR}.md").read_text(encoding="utf-8")
        for titre in ("Ce qui a changé", "Divergences entre sources", "Données manquantes", "mouvements de notes", "Sources en échec"):
            self.assertIn(titre, recap)
        self.assertTrue(textes.ton_conforme(recap))
        # Les flux fictifs ont été déplacés
        self.assertEqual(lire_json(self.dossier / "flux.json")["donnees"][0]["de"], "FR")

    def test_aucun_changement_aucune_ecriture(self):
        self.lancer()
        avant = self.sortie.read_text(encoding="utf-8")
        self.lancer()
        self.assertEqual(self.sortie.read_text(encoding="utf-8"), avant)

    def test_source_en_panne_et_tendance(self):
        self.lancer()
        # Deuxième exécution : la BIS est en panne et la croissance du FMI a changé
        modif = self.copie_donnees()
        (modif / "bis.json").unlink()
        (modif / "bce_taux.json").unlink()      # la France a deux sources de taux : BCE et BRI
        fmi = json.loads((modif / "fmi_NGDP_RPCH.json").read_text(encoding="utf-8"))
        fmi["FRA"]["2026"] = fmi["FRA"]["2026"] + 1.0
        (modif / "fmi_NGDP_RPCH.json").write_text(json.dumps(fmi), encoding="utf-8")
        self.assertEqual(self.lancer(modif, "2026-11-03"), 0)   # l'agent ne plante pas
        f = lire_json(self.sortie)
        fr = next(p for p in f["donnees"] if p["code"] == "FR")
        self.assertTrue(fr["indicateurs"]["taux_reel"]["ancienne"])            # dernière valeur connue conservée
        self.assertIn("raison_ancienne", fr["indicateurs"]["taux_reel"])
        self.assertIn("erreur", f["meta"]["etat_des_sources"]["bis"])
        self.assertEqual(fr["indicateurs"]["taux_reel"]["confiance"], "faible")
        statuts = {s["source"]: s["statut"] for s in fr["indicateurs"]["taux_reel"]["sources"]}
        self.assertEqual(statuts, {"bce_taux": "échec", "bis": "échec"})   # l'état des sources du jour est montré
        pib = fr["indicateurs"]["croissance_pib"]
        self.assertAlmostEqual(pib["precedent"]["valeur"] + 1.0, pib["valeur"], places=2)   # tendance

    def test_divergence_entre_sources(self):
        # Croissance 2026 de la France : FMI 0,4 % et OCDE 1,0 % → écart supérieur à 0,5 point
        self.lancer()
        fr = next(p for p in lire_json(self.sortie)["donnees"] if p["code"] == "FR")
        pib = fr["indicateurs"]["croissance_pib"]
        self.assertEqual(pib["verification"], "divergent")
        self.assertEqual(pib["confiance"], "faible")
        self.assertEqual(pib["sources"][0]["source"], "fmi")                  # source prioritaire retenue
        self.assertIn("diverge", [s["statut"] for s in pib["sources"]])
        self.assertTrue(any("sources divergentes" in r for r in fr["confiance"]["raisons"]))
        self.assertNotEqual(fr["confiance"]["niveau"], "élevé")              # la divergence fait baisser la confiance
        self.assertTrue(any("divergent" in c for c in fr["contre_scenario"]))
        recap = next((self.dossier / "recap").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("France, croissance du PIB", recap)

    def test_alerte_qualite_et_journal(self):
        # Pannes simultanées : plus d'un tiers des sources de la France échouent
        modif = self.copie_donnees()
        for nom in ("ocde_cli", "ocde_inflation", "ocde_eo", "eurostat", "bce_taux", "fmi_PCPIPCH"):
            (modif / f"{nom}.json").unlink()
        self.assertEqual(self.lancer(modif), 0)
        f = lire_json(self.sortie)
        fr = next(p for p in f["donnees"] if p["code"] == "FR")
        self.assertTrue(fr["qualite"]["alerte"])
        self.assertIn("FR", f["meta"]["alertes_qualite"])
        entree = lire_json(self.dossier / "journal.json")["donnees"][-1]
        self.assertIn("eurostat", entree["sources_en_erreur"])
        self.assertTrue(any(e["pays"] == "FR" and e["statut"] == "échec" for e in entree["echecs_et_rejets"]))
        self.assertIn("Qualité des données", next((self.dossier / "recap").glob("*.md")).read_text(encoding="utf-8"))


class TestCroisement(unittest.TestCase):
    AUJ = date(2026, 11, 2)

    def cand(self, source, niveau, valeur, periode, nature="mensuelle"):
        return {"source": source, "nom": source, "niveau": niveau, "valeur": valeur, "date": periode, "nature": nature}

    def test_hierarchie_et_tolerance(self):
        c = [self.cand("ocde", "internationale", 3.0, "2026-09"), self.cand("insee", "nationale", 2.8, "2026-09")]
        r = croisement.choisir(c, [-15, 300], 0.5, self.AUJ)
        self.assertEqual(r["retenu"]["source"], "insee")            # source nationale prioritaire
        self.assertEqual(r["verification"], "concordant")             # écart faible : 0,2 point
        r = croisement.choisir(c + [self.cand("eurostat", "internationale", 3.6, "2026-09")], [-15, 300], 0.5, self.AUJ)
        self.assertEqual(r["verification"], "divergent")              # écart important : 0,8 point
        # À fiabilité égale, la plus récente l'emporte
        r = croisement.choisir([self.cand("a", "internationale", 1, "2026-08"), self.cand("b", "internationale", 1.1, "2026-09")], None, 0.5, self.AUJ)
        self.assertEqual(r["retenu"]["source"], "b")

    def test_rejets_et_source_unique(self):
        c = [self.cand("bls", "nationale", 3.0, "2025-01"),            # plus de 6 mois : rejetée
             self.cand("aberrante", "nationale", 900, "2026-09"),       # hors bornes : rejetée
             self.cand("ocde", "internationale", 3.7, "2026-09"),
             self.cand("fmi", "internationale", 3.6, "2026", "annuelle")]
        r = croisement.choisir(c, [-15, 300], 0.5, self.AUJ)
        self.assertEqual(r["retenu"]["source"], "ocde")
        statuts = {s["source"]: s["statut"] for s in r["sources"]}
        self.assertEqual(statuts, {"bls": "rejetée", "aberrante": "rejetée", "ocde": "retenue", "fmi": "non comparable"})
        self.assertEqual(r["verification"], "source_unique")
        self.assertIn("plus de 6 mois", next(s["raison"] for s in r["sources"] if s["source"] == "bls"))

    def test_qualite(self):
        t = [{"source": "a", "nom": "A", "statut": "retenue"}, {"source": "b", "nom": "B", "statut": "échec", "raison": "panne"},
             {"source": "c", "nom": "C", "statut": "concorde"}]
        self.assertFalse(qualite(t)["alerte"])                         # 1 sur 3 : pas plus d'un tiers
        self.assertTrue(qualite(t + [{"source": "d", "nom": "D", "statut": "rejetée", "raison": "trop ancienne"}])["alerte"])

    def test_plafond_confiance(self):
        p = {"a": 0.5, "b": 0.5}
        uniques = {"a": {"note": 70, "libelle": "A", "verification": "source_unique"},
                   "b": {"note": 70, "libelle": "B", "verification": "source_unique"}}
        self.assertEqual(notation.confiance(uniques, p, 1.0)["niveau"], "moyen")
        croisees = {"a": {"note": 70, "libelle": "A", "verification": "concordant"},
                    "b": {"note": 70, "libelle": "B", "verification": "source_unique"}}
        self.assertEqual(notation.confiance(croisees, p, 1.0)["niveau"], "élevé")


if __name__ == "__main__":
    unittest.main()
