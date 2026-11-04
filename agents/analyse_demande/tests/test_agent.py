"""Tests de l'analyse à la demande, sans réseau : python -m unittest discover -s agents -t .
Les événements GitHub « issues: opened » sont simulés (fichier JSON comme GITHUB_EVENT_PATH)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agents.analyse_demande import agent as AG
from agents.analyse_demande import reponse as T
from agents.analyse_demande.resolution import pays_du_symbole, resoudre, saisie
from agents.commun.essais import copier_donnees_test
from agents.commun.sortie import lire_json
from agents.pays.textes import ton_conforme

RACINE = Path(__file__).resolve().parents[3]
DONNEES = Path(__file__).resolve().parent / "donnees"
SUFFIXES = AG.CFG["suffixes_pays"]


def evenement(titre, auteur="jcn1996", proprietaire="jcn1996", numero=42):
    return {"action": "opened", "issue": {"number": numero, "title": titre, "user": {"login": auteur},
                                          "html_url": f"https://github.com/{proprietaire}/Plateforme-eco/issues/{numero}"},
            "repository": {"owner": {"login": proprietaire}}}


class TestSaisie(unittest.TestCase):
    def test_titre(self):
        self.assertEqual(saisie("Analyse : ASML"), "ASML")
        self.assertEqual(saisie("analyse:  Hermès  "), "Hermès")
        self.assertEqual(saisie("Analyse : MC.PA"), "MC.PA")  # espace insécable (clavier français)
        self.assertIsNone(saisie("Analyse du marché"))
        self.assertIsNone(saisie("Analyse : "))

    def test_pays(self):
        self.assertEqual(pays_du_symbole("MC.PA", SUFFIXES), "FR")
        self.assertEqual(pays_du_symbole("7203.T", SUFFIXES), "JP")
        self.assertEqual(pays_du_symbole("005930.KS", SUFFIXES), "KR")
        self.assertEqual(pays_du_symbole("AAPL", SUFFIXES), "US")
        self.assertEqual(pays_du_symbole("ASML", SUFFIXES, "Netherlands"), "NL")


class TestResolution(unittest.TestCase):
    Q = json.loads((DONNEES / "recherche.json").read_text(encoding="utf-8"))
    COURS = {"MC.PA": ([("2026-10-01", 500.0, 1e6), ("2026-10-02", 510.0, 1e6)], "EUR"),
             "LVMUY": ([("2026-10-01", 100.0, 1e4)], "USD"), "AAPL": ([("2026-10-01", 200.0, 5e7)], "USD")}

    def res(self, texte):
        return resoudre(texte, lambda q: self.Q.get(q.lower(), []), lambda s: self.COURS.get(s, ([], None)),
                        lambda d: {"USD": 1.0, "EUR": 1.1}, [("RMS.PA", "Hermès International"), ("AAPL", "Apple Inc.")])

    def test_nom_plus_liquide(self):
        r = self.res("LVMH")
        self.assertEqual(r["choisi"]["symbole"], "MC.PA")
        self.assertEqual([a["symbole"] for a in r["autres"]], ["LVMUY"])

    def test_accents(self):
        r = self.res("LVMH")
        r2 = resoudre("Lvmh", lambda q: self.Q.get(q.lower(), []) if q == "Lvmh" else [], lambda s: self.COURS.get(s, ([], None)),
                      lambda d: {"USD": 1.0, "EUR": 1.1}, [])
        self.assertEqual(r2["choisi"]["symbole"], r["choisi"]["symbole"])
        vus = []
        resoudre("Hermès", lambda q: vus.append(q) or [], lambda s: ([], None), lambda d: {}, [])
        self.assertIn("Hermes", vus)

    def test_ticker_exact(self):
        r = self.res("7203.T")
        self.assertEqual(r["methode"], "ticker")
        self.assertEqual(r["choisi"]["symbole"], "7203.T")
        self.assertEqual(r["autres"][0]["symbole"], "TM")

    def test_ticker_hors_recherche(self):
        r = self.res("AAPL")  # pas de réponse de recherche pour « aapl » : interrogation directe des cours
        self.assertEqual(r["choisi"]["symbole"], "AAPL")

    def test_introuvable_avec_suggestions(self):
        r = self.res("Hermes Internationale")
        self.assertEqual(r["statut"], "introuvable")
        self.assertIn("RMS.PA (Hermès International)", r["suggestions"])


class TestDeBoutEnBout(unittest.TestCase):
    """Événements simulés : une société américaine, une européenne, une asiatique ; introuvable ; refus."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.data = self.dir / "data"
        (self.data / "journal").mkdir(parents=True)
        # Jamais les vrais data/ ni config/ : pays.json et macro.json de test, copie de test de la liste de surveillance
        copier_donnees_test(self.data)
        medianes = {"Information Technology|monde": {"per": 28.0, "ev_ebitda": 19.0, "n": 50},
                    "Information Technology|amerique_nord": {"per": 30.0, "ev_ebitda": 21.0, "n": 30},
                    "Consumer Discretionary|monde": {"per": 18.0, "ev_ebitda": 11.0, "n": 60},
                    "Consumer Discretionary|europe": {"per": 20.0, "ev_ebitda": 12.0, "n": 20},
                    "Consumer Discretionary|asie_pacifique": {"per": 12.0, "ev_ebitda": 8.0, "n": 20}}
        pairs = [{"ticker": f"P{i}", "nom": f"Pair {i}", "pays": "US", "region": "amerique_nord", "secteur_gics": s, "note": n}
                 for i, (s, n) in enumerate([("Information Technology", 80), ("Information Technology", 40),
                                             ("Consumer Discretionary", 70), ("Consumer Discretionary", 30), ("Consumer Discretionary", 55)])]
        (self.data / "entreprises.json").write_text(json.dumps({"meta": {"fictif": False, "medianes": medianes}, "donnees": pairs}), encoding="utf-8")
        self.surv = self.dir / "surveillance.json"
        shutil.copy(DONNEES / "surveillance.json", self.surv)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def lancer(self, titre, **k):
        chemin = self.dir / "evenement.json"
        chemin.write_text(json.dumps(evenement(titre, **k)), encoding="utf-8")
        sortie = self.dir / "sortie"
        code = AG.main(["--evenement", str(chemin), "--sortie", str(sortie), "--data", str(self.data),
                        "--surveillance", str(self.surv), "--test", "--date", "2026-11-03"])
        return code, json.loads((sortie / "resultat.json").read_text(encoding="utf-8")), (sortie / "reponse.md").read_text(encoding="utf-8")

    def test_trois_societes(self):
        for titre, ticker, pays in (("Analyse : Apple", "AAPL", "US"), ("Analyse : LVMH", "MC.PA", "FR"), ("Analyse : 7203.T", "7203.T", "JP")):
            code, res, texte = self.lancer(titre)
            self.assertEqual((code, res["statut"], res["ticker"]), (0, "ok", ticker), texte)
            fiche = lire_json(self.data / "analyses" / f"{ticker}.json")["donnees"]
            self.assertEqual(fiche["pays"], pays)
            r = fiche["recommandation"]
            self.assertIn(r["si_non_detenu"], ("Acheter", "Acheter sur repli", "Attendre", "Éviter"))
            self.assertIn(r["si_detenu"], ("Renforcer", "Conserver", "Alléger", "Vendre"))
            self.assertTrue(2 <= len(r["conditions_invalidation"]) <= 3)
            self.assertIn("revue_critique", fiche)
            self.assertIsNotNone(fiche["rang_secteur"])
            # Réponse : note, verdict, recommandation, 5 indicateurs, risques, confiance, lien, mention
            self.assertIn(f"/100", texte)
            self.assertIn(f"https://jcn1996.github.io/Plateforme-eco/#analyse-{ticker}", texte)
            self.assertEqual(texte.count("\n| ") - 1, 5)
            self.assertIn("Principaux risques", texte)
            self.assertIn("Niveau de confiance", texte)
            self.assertIn("Avis indicatif généré automatiquement", texte)
            self.assertTrue(ton_conforme(texte.replace(fiche["nom"], "")), texte)
        idx = lire_json(self.data / "analyses" / "index.json")["donnees"]
        self.assertEqual({x["ticker"] for x in idx}, {"AAPL", "MC.PA", "7203.T"})
        self.assertTrue(all(x["recommandation"]["n"] and x["note"] for x in idx))
        surv = lire_json(self.surv)["societes"]
        self.assertEqual([s["ticker"] for s in surv], ["MC.PA", "AAPL", "7203.T"])  # MC.PA y était déjà
        j = lire_json(self.data / "journal" / "analyse-demande.json")
        self.assertTrue(j["meta"]["sante"]["a_la_demande"])
        self.assertEqual(j["meta"]["sante"]["analyses_reussies"], 3)
        self.assertFalse(j["meta"]["sante"]["degrade"])
        self.assertIn("analyse-demande.json", json.dumps(lire_json(self.data / "journal" / "index.json")))
        # Le suivi enregistre chaque analyse à la demande
        from datetime import date
        from agents.entreprises import suivi as S
        h = []
        cfg = json.loads((RACINE / "agents" / "entreprises" / "config.json").read_text(encoding="utf-8"))["recommandation"]["suivi"]
        self.assertEqual(S.enregistrer(h, self.data, date(2026, 11, 3), cfg), 3)
        self.assertTrue(all(x["source"] == "demande" and x["issue"] == 42 for x in h))

    def test_nouvelle_analyse_remplace_la_ligne(self):
        self.lancer("Analyse : LVMH")
        self.lancer("Analyse : MC.PA", numero=43)
        idx = lire_json(self.data / "analyses" / "index.json")["donnees"]
        self.assertEqual(len(idx), 1)
        self.assertEqual(idx[0]["issue"], 43)
        self.assertEqual(idx[0]["precedentes"][0]["issue"], 42)

    def test_introuvable(self):
        code, res, texte = self.lancer("Analyse : ZZQX societe imaginaire")
        self.assertEqual(res["statut"], "introuvable")
        self.assertIn("introuvable", texte)
        self.assertIn("ZZQX.X", texte)
        self.assertFalse((self.data / "analyses" / "index.json").exists())
        self.assertFalse(lire_json(self.data / "journal" / "analyse-demande.json")["meta"]["sante"]["degrade"])

    def test_refus_si_pas_proprietaire(self):
        code, res, texte = self.lancer("Analyse : Apple", auteur="inconnu")
        self.assertEqual(res["statut"], "refus")
        self.assertEqual(res["fermeture"], "not planned")
        self.assertIn("réservées au propriétaire", texte)
        self.assertFalse((self.data / "analyses").exists())
        self.assertFalse((self.data / "journal" / "analyse-demande.json").exists())

    def test_echec_enregistre(self):
        chemin = self.dir / "evenement.json"
        chemin.write_text(json.dumps(evenement("Analyse : Apple")), encoding="utf-8")
        AG.main(["--evenement", str(chemin), "--sortie", str(self.dir / "s"), "--data", str(self.data),
                 "--surveillance", str(self.surv), "--echec", "installation impossible"])
        s = lire_json(self.data / "journal" / "analyse-demande.json")["meta"]["sante"]
        self.assertTrue(s["degrade"])
        self.assertEqual(s["dernier_echec"]["detail"], "installation impossible")
        self.assertIsNone(s["derniere_execution"])


class TestTextes(unittest.TestCase):
    def test_refus_et_echec_conformes(self):
        for t in (T.reponse_refus(), T.reponse_echec("ASML", "délai dépassé", None), T.reponse_introuvable("x", ["A (B)"])):
            self.assertTrue(ton_conforme(t), t)


if __name__ == "__main__":
    unittest.main()
