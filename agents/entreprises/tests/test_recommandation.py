"""Tests de la recommandation et de son suivi, sans réseau : python -m unittest discover -s agents -t ."""
import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from agents.entreprises import analyse as A
from agents.entreprises import recommandation as R
from agents.entreprises import suivi as S
from agents.pays.textes import ton_conforme

DOSSIER = Path(__file__).resolve().parents[1]
CFG = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))["recommandation"]

A0 = {"fin": "2025-12-31", "ca": 1100.0, "ebit": 220.0, "ebitda": 300.0, "resultat_net": 100.0, "fcf": 90.0}


def societe(prix=20.0, **k):
    return {"prix": prix, "devise_cours": "EUR", "devise_comptes": "EUR", "actions": 100.0, "annuel": [A0],
            "fx_comptes": 1.1, "fx_cours": 1.1, "region": "europe", "financier": None, "date_cours": "2026-11-02", **k}


def mesures(**k):
    m = {"per_mediane_regionale": 20.0, "ev_ebitda_mediane_regionale": 10.0, "dette_nette": 200.0, "croissance_ca_3ans": 6.0,
         "momentum_12m": 12.0, "fscore": {"score": 7}, "alertes": []}
    m.update(k)
    return m


class TestValeur(unittest.TestCase):
    def test_multiples(self):
        v = R.valeur_multiples(mesures(), 100.0, 300.0, 100.0, None)
        # PER : 20 × 100 / 100 = 20 ; VE/EBITDA : (10 × 300 − 200) / 100 = 28
        self.assertAlmostEqual(v["bas"], 20.0)
        self.assertAlmostEqual(v["haut"], 28.0)
        self.assertAlmostEqual(v["centrale"], 24.0)

    def test_financier_sans_ve_ebitda_ni_dcf(self):
        v = R.valeur_multiples(mesures(), 100.0, 300.0, 100.0, "banque")
        self.assertAlmostEqual(v["centrale"], 20.0)
        self.assertIsNone(R.valeur_dcf(mesures(), 90.0, 100.0, "banque", "europe", CFG["dcf"]))

    def test_dcf_monotone(self):
        bas = R.actualiser(100, 5, 2, 10, 5)
        haut = R.actualiser(100, 5, 2, 8, 5)
        self.assertGreater(haut, bas)
        # Croissance nulle et taux de 10 % avec croissance terminale nulle : rente perpétuelle = 1 000
        self.assertAlmostEqual(R.actualiser(100, 0, 0, 10, 5), 1000, places=6)
        d = R.valeur_dcf(mesures(), 90.0, 100.0, None, "europe", CFG["dcf"])
        self.assertLess(d["bas"], d["centrale"])
        self.assertLess(d["centrale"], d["haut"])
        self.assertEqual(d["hypotheses"]["taux_actualisation"], CFG["dcf"]["taux_base"] + CFG["dcf"]["primes_region"]["europe"])

    def test_conversion_de_devise(self):
        s = societe(devise_comptes="USD", fx_comptes=1.0, fx_cours=0.5)  # comptes en dollars, cours en devise à 0,5 $
        v = R.valeur_estimee(mesures(), s, CFG)
        v_eur = R.valeur_estimee(mesures(), societe(), CFG)
        self.assertAlmostEqual(v["centrale"], v_eur["centrale"] * 2, places=3)


class TestRegles(unittest.TestCase):
    def test_acheter(self):
        r = R.recommander(societe(prix=15.0), mesures(), 70, "élevé", ["risque"], CFG)
        self.assertEqual(r["si_non_detenu"], "Acheter")
        self.assertEqual(r["si_detenu"], "Renforcer")
        self.assertGreaterEqual(r["concordants"]["favorables"], 3)
        self.assertTrue(2 <= len(r["conditions_invalidation"]) <= 3)
        self.assertEqual(r["mention"], R.MENTION)

    def test_alerte_interdit_acheter(self):
        m = mesures(alertes=[{"cle": "dilution", "titre": "Dilution forte", "texte": "…"}])
        r = R.recommander(societe(prix=15.0), m, 70, "élevé", [], CFG)
        self.assertNotIn(r["si_non_detenu"], ("Acheter", "Acheter sur repli"))
        self.assertNotEqual(r["si_detenu"], "Renforcer")

    def test_confiance_faible_interdit_acheter_et_vendre(self):
        r = R.recommander(societe(prix=15.0), mesures(), 70, "faible", [], CFG)
        self.assertNotEqual(r["si_non_detenu"], "Acheter")
        self.assertIn("confiance faible", r["justification"])
        m = mesures(momentum_12m=-30.0, fscore={"score": 2})
        r = R.recommander(societe(prix=60.0), m, 40, "faible", [], CFG)
        self.assertNotEqual(r["si_detenu"], "Vendre")
        r = R.recommander(societe(prix=60.0), m, 40, "moyen", [], CFG)
        self.assertEqual(r["si_detenu"], "Vendre")
        self.assertEqual(r["si_non_detenu"], "Éviter")

    def test_acheter_sur_repli(self):
        # Valeur estimée ≈ 18,7 : au cours de 19, l'écart est trop faible ; repli à valeur / 1,15
        # Momentum neutre : la valorisation est le troisième signal manquant
        m = mesures(momentum_12m=2.0)
        r = R.recommander(societe(prix=19.0), m, 70, "moyen", [], CFG)
        self.assertEqual(r["si_non_detenu"], "Acheter sur repli")
        self.assertAlmostEqual(r["prix_repli"], r["valeur"]["centrale"] / 1.15, places=3)
        # Au prix de repli, la recommandation devient « Acheter »
        r2 = R.recommander(societe(prix=r["prix_repli"] * 0.999), m, 70, "moyen", [], CFG)
        self.assertEqual(r2["si_non_detenu"], "Acheter")

    def test_repli_trop_eloigne(self):
        r = R.recommander(societe(prix=60.0), mesures(momentum_12m=2.0), 70, "moyen", [], CFG)
        self.assertEqual(r["si_non_detenu"], "Attendre")
        self.assertIn("trop éloigné", r["justification"])

    def test_signaux_inities_ponderation_moderee(self):
        # Deux signaux pleins (note, valorisation) : il manque 1 ; les deux signaux de l'agent initiés pèsent 0,5 chacun
        m = mesures(momentum_12m=2.0, fscore={"score": 5})
        ini = {"score_achats": 82, "texte_achats": "3 acheteurs distincts en 30 jours", "conviction": 60,
               "texte_conviction": "2 super-investisseurs : Mohnish Pabrai (30,0 %)"}
        r = R.recommander(societe(prix=15.0), m, 70, "élevé", [], CFG, inities=ini)
        self.assertEqual(r["si_non_detenu"], "Acheter")
        self.assertEqual(r["concordants"]["favorables_ponderes"], 3.0)
        self.assertIn("en pondération", r["justification"])
        un_seul = R.recommander(societe(prix=15.0), m, 70, "élevé", [], CFG, inities={**ini, "conviction": None})
        self.assertNotEqual(un_seul["si_non_detenu"], "Acheter")  # 2,5 signaux pondérés : insuffisant
        sans = R.recommander(societe(prix=15.0), m, 70, "élevé", [], CFG)
        self.assertNotIn("inities", [x["cle"] for x in sans["signaux"]])  # agent initiés absent : signaux inchangés
        for t in [r["justification"], *r["conditions_invalidation"], *(x["texte"] for x in r["signaux"])]:
            self.assertTrue(ton_conforme(t), t)

    def test_ventes_massives_seul_cas_negatif(self):
        ventes = {"ventes_massives": {"texte": "3 dirigeants ont vendu 7,2 M$ en 30 jours."}}
        r = R.recommander(societe(prix=15.0), mesures(), 70, "élevé", [], CFG, inities=ventes)
        s = next(x for x in r["signaux"] if x["cle"] == "inities")
        self.assertEqual(s["sens"], -1)
        self.assertNotEqual(r["si_non_detenu"], "Acheter")  # un signal défavorable interdit « Acheter »
        neutre = R.recommander(societe(prix=15.0), mesures(), 70, "élevé", [], CFG, inities={})
        self.assertEqual(neutre["si_non_detenu"], "Acheter")
        self.assertEqual({x["cle"]: x["sens"] for x in neutre["signaux"]}["inities"], 0)

    def test_textes_conformes(self):
        for prix, note, m in ((15.0, 70, mesures()), (60.0, 40, mesures(momentum_12m=-30.0)), (22.0, 55, mesures(momentum_12m=None))):
            r = R.recommander(societe(prix=prix), m, note, "moyen", [], CFG)
            for t in [r["justification"], *r["conditions_invalidation"], *(x["texte"] for x in r["signaux"])]:
                self.assertTrue(ton_conforme(t), t)

    def test_seuils_lus_en_configuration(self):
        cfg = copy.deepcopy(CFG)
        cfg["regles"]["signaux_concordants_min"] = 5  # impossible avec 4 signaux
        r = R.recommander(societe(prix=15.0), mesures(), 70, "élevé", [], cfg)
        self.assertNotEqual(r["si_non_detenu"], "Acheter")


class TestSuivi(unittest.TestCase):
    CFG_S = CFG["suivi"]

    def test_performance_et_reussite(self):
        h = [{"id": "x", "date": "2026-01-02", "date_cours": "2026-01-02", "source": "demande", "ticker": "AAA",
              "recommandation": "Acheter", "detenu": "Renforcer", "suivi": {}},
             {"id": "y", "date": "2026-01-02", "date_cours": "2026-01-02", "source": "entreprises", "ticker": "BBB",
              "recommandation": "Éviter", "detenu": "Vendre", "suivi": {}}]
        series = {"AAA": [("2026-01-02", 100.0), ("2026-04-03", 120.0)], "BBB": [("2026-01-02", 50.0), ("2026-04-03", 50.0)],
                  "URTH": [("2026-01-02", 10.0), ("2026-04-03", 10.5)]}
        n = S.mettre_a_jour(h, series, "URTH", date(2026, 4, 10), self.CFG_S)
        self.assertEqual(n, 2)
        self.assertEqual(h[0]["suivi"]["3"]["perf_pct"], 20.0)
        self.assertEqual(h[0]["suivi"]["3"]["relative_pct"], 15.0)
        self.assertTrue(h[0]["suivi"]["3"]["reussite"])
        self.assertTrue(h[1]["suivi"]["3"]["reussite"])  # −5 % relatif : « Éviter » réussi
        self.assertNotIn("6", h[0]["suivi"])
        f = S.fiabilite(h, self.CFG_S)
        self.assertEqual(f["si_non_detenu"]["Acheter"]["3"]["taux_pct"], 100)
        self.assertEqual(f["si_detenu"]["Vendre"]["3"]["relative_moyenne_pct"], -5.0)

    def test_enregistrement_sur_changement(self):
        with tempfile.TemporaryDirectory() as t:
            data = Path(t)
            (data / "entreprises" / "fiches").mkdir(parents=True)
            reco = R.recommander(societe(prix=15.0), mesures(), 70, "élevé", [], CFG)
            fiche = {"ticker": "AAA", "nom": "AAA SA", "note": 70, "recommandation": reco}
            (data / "entreprises" / "fiches" / "AAA.json").write_text(json.dumps({"donnees": fiche}), encoding="utf-8")
            leger = {"meta": {"fictif": False}, "donnees": [{"ticker": "AAA", "nom": "AAA SA", "recommandation": R.resume(reco)}]}
            (data / "entreprises.json").write_text(json.dumps(leger), encoding="utf-8")
            h = []
            self.assertEqual(S.enregistrer(h, data, date(2026, 11, 3), self.CFG_S), 1)
            self.assertEqual(S.enregistrer(h, data, date(2026, 11, 4), self.CFG_S), 0)  # inchangée
            leger["donnees"][0]["recommandation"]["n"] = "Attendre"
            (data / "entreprises.json").write_text(json.dumps(leger), encoding="utf-8")
            self.assertEqual(S.enregistrer(h, data, date(2026, 11, 5), self.CFG_S), 0)  # moins de 7 jours
            self.assertEqual(S.enregistrer(h, data, date(2026, 11, 12), self.CFG_S), 1)
            self.assertEqual(h[0]["cours"], 15.0)


class TestLectureInities(unittest.TestCase):
    """data/inities.json n'est lu que s'il est récent (sinon les deux signaux de l'agent initiés sont absents)."""

    def test_fraicheur(self):
        from agents.entreprises.agent import lire_inities
        cfg = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))["recommandation"]["inities"]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertIsNone(lire_inities(d, cfg, date(2026, 11, 6)))
            (d / "inities.json").write_text(json.dumps({"donnees": {"date": "2026-11-05", "societes": {"X": {"score_achats": 70}}}}), encoding="utf-8")
            self.assertEqual(lire_inities(d, cfg, date(2026, 11, 6))["X"]["score_achats"], 70)
            self.assertIsNone(lire_inities(d, cfg, date(2026, 12, 6)))


if __name__ == "__main__":
    unittest.main()
