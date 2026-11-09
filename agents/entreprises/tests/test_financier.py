"""Tests de l'analyse financière approfondie (financier.py), sans réseau : python -m unittest discover -s agents -t ."""
import copy
import json
import unittest
from pathlib import Path

from agents.entreprises import analyse as A
from agents.entreprises import financier as F
from agents.entreprises import recommandation as R
from agents.entreprises.agent import note_avec_dynamique
from agents.pays.textes import ton_conforme

DOSSIER = Path(__file__).resolve().parents[1]
CONFIG = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
CFG = CONFIG["analyse_financiere"]


def exercice(fin, **k):
    e = {"fin": fin, "ca": 1000.0, "marge_brute": 400.0, "cout_ventes": 600.0, "ebit": 150.0, "ebitda": 200.0, "resultat_net": 100.0,
         "cfo": 130.0, "capex": 50.0, "fcf": 80.0, "amortissements": 50.0, "immobilisations": 500.0, "actifs": 2000.0,
         "actifs_courants": 600.0, "passifs_courants": 300.0, "passifs_totaux": 1000.0, "benefices_non_distribues": 400.0,
         "creances": 150.0, "stocks": 100.0, "fournisseurs": 80.0, "sga": 120.0, "dette_lt": 300.0, "dette_totale": 400.0,
         "tresorerie": 100.0, "interets": 20.0, "taux_impot": 0.25, "capital_investi": 1200.0, "capitaux_propres": 1000.0,
         "actions": 100.0, "goodwill": 200.0, "rd": 60.0, "dividendes": -30.0, "rachats": -20.0, "emissions": 5.0}
    e.update(k)
    return e


def societe(**k):
    an = [exercice("2025-12-31"), exercice("2024-12-31", ca=950.0, resultat_net=95.0, ebit=140.0, marge_brute=380.0, cout_ventes=570.0),
          exercice("2023-12-31", ca=900.0, resultat_net=90.0, ebit=130.0, marge_brute=360.0, cout_ventes=540.0),
          exercice("2022-12-31", ca=850.0, resultat_net=85.0, ebit=125.0, marge_brute=340.0, cout_ventes=510.0, actions=110.0),
          exercice("2021-12-31", ca=800.0, resultat_net=80.0, ebit=120.0, marge_brute=320.0, cout_ventes=480.0)]
    s = {"annuel": an, "cours": [], "capitalisation_usd": 2000.0, "fx_comptes": 1.0, "region": "amerique_nord",
         "secteur_gics": "Information Technology", "financier": None, "beta": 1.2, "detention_dirigeants": 0.08}
    s.update(k)
    return s


class TestIndicateurs(unittest.TestCase):
    def test_altman_formule(self):
        a0 = exercice("2025-12-31")
        z = F.altman(a0, 2000.0)
        attendu = 1.2 * 300 / 2000 + 1.4 * 400 / 2000 + 3.3 * 150 / 2000 + 0.6 * 2000 / 1000 + 1.0 * 1000 / 2000
        self.assertAlmostEqual(z["z"], round(attendu, 2))
        self.assertEqual(F.zone_altman(z["z"], CFG), "grise")
        self.assertEqual(F.zone_altman(1.0, CFG), "détresse")
        self.assertEqual(F.zone_altman(3.5, CFG), "sûre")
        self.assertIsNone(F.altman({**a0, "benefices_non_distribues": None}, 2000.0))  # jamais d'approximation

    def test_beneish(self):
        a1 = exercice("2024-12-31")
        b = F.beneish(exercice("2025-12-31"), a1)
        # Exercices identiques sauf TATA : tous les indices valent 1
        self.assertTrue(all(abs(v - 1) < 1e-9 for k, v in b["variables"].items() if k != "TATA"))
        self.assertAlmostEqual(b["m"], round(-4.84 + 0.920 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 + 4.679 * (-30 / 2000) - 0.327, 2))
        # Créances qui explosent et résultat sans cash : suspect
        a0 = exercice("2025-12-31", creances=400.0, ca=1500.0, resultat_net=300.0, cfo=50.0)
        self.assertGreater(F.beneish(a0, a1)["m"], CFG["beneish"]["seuil"])
        self.assertEqual(F.beneish({**a0, "sga": None}, a1)["neutres"], ["SGAI"])
        self.assertIsNone(F.beneish({**a0, "creances": None}, a1))
        self.assertIsNone(F.beneish(a0, None))

    def test_normalisation_et_sommet_de_cycle(self):
        serie = [{"fin": f"202{i}-12-31", "resultat_net": v} for i, v in zip((5, 4, 3, 2, 1), (300.0, 100.0, 80.0, 60.0, 60.0))]
        n = F.normalisation(serie, None, CFG)
        self.assertAlmostEqual(n["benefice_moyen"], 120.0)
        self.assertAlmostEqual(n["benefices_normalises"], 2.5)
        self.assertTrue(n["sommet_cycle"])
        self.assertFalse(F.normalisation(serie[1:], None, CFG)["sommet_cycle"])  # 100 / 75 = 1,33 : sous le seuil
        self.assertNotIn("benefice_moyen", F.normalisation(serie[:2], None, CFG))  # moins de 3 exercices
        n = F.normalisation(serie[:3], None, CFG)
        self.assertFalse(n["sommet_cycle"])  # 3 exercices : rapport calculé, alerte réservée à 4 exercices ou plus
        # Croissance régulière, marge stable : bénéfice et CA progressent ensemble, pas de sommet de cycle
        croiss = [{"fin": f"202{i}-12-31", "resultat_net": v, "ca": v * 10} for i, v in zip((5, 4, 3, 2, 1), (200.0, 150.0, 115.0, 90.0, 70.0))]
        n = F.normalisation(croiss, None, CFG)
        self.assertGreater(n["benefices_normalises"], CFG["normalisation"]["seuil_sommet"])
        self.assertAlmostEqual(n["exces_marge"], 1.0)
        self.assertFalse(n["sommet_cycle"])
        # Bénéfice actuel négatif : rapport non significatif, note dédiée
        n = F.normalisation([{"fin": "2025-12-31", "resultat_net": -50.0}] + serie[1:], None, CFG)
        self.assertNotIn("benefices_normalises", n)
        self.assertEqual(F.notes(n, None, CFG)["benefices_normalises"], CFG["baremes"]["benefice_actuel_negatif"])

    def test_wacc(self):
        w = F.wacc({"beta": 1.2, "region": "europe"}, exercice("2025-12-31"), 2000.0, CFG)
        rf = 4.0 + 0.5
        ke = rf + 1.2 * 5.0
        kd = max(rf, 20 / 400 * 100)  # 5 % < plancher 4,5 % ? non : 5 %
        attendu = (2000 * ke + 400 * kd * 0.75) / 2400
        self.assertAlmostEqual(w["wacc"], round(attendu, 2))
        self.assertEqual(F.wacc({"beta": 9.0}, exercice("2025-12-31"), 2000.0, CFG)["beta"], CFG["wacc"]["beta_max"])
        self.assertEqual(F.wacc({}, exercice("2025-12-31"), 2000.0, CFG)["beta_source"], "valeur par défaut")

    def test_regularite(self):
        serie = societe()["annuel"]
        r = F.regularite(serie, CFG)
        self.assertEqual(r["regularite_croissance_pct"], 100)
        self.assertLess(r["stabilite_marge_pts"], 1.0)
        self.assertGreaterEqual(r["regularite"], 85)
        self.assertEqual(F.regularite(serie[:3], CFG), {})

    def test_cycle_cash(self):
        c = F.cycle_cash(exercice("2025-12-31"))
        self.assertEqual(c["jours"], round(150 / 1000 * 365 + 100 / 600 * 365 - 80 / 600 * 365))
        self.assertEqual(F.cycle_cash({**exercice("2025-12-31"), "stocks": None})["stocks"], 0)  # services : pas de stocks
        self.assertIsNone(F.cycle_cash({**exercice("2025-12-31"), "fournisseurs": None}))

    def test_serie_sec_completee(self):
        s = societe(annuel=societe()["annuel"][:4])
        s["officiel"] = {"historique": [{"fin": "2025-12-31", "ca": 1010.0, "resultat_net": 101.0},
                                        {"fin": "2020-12-31", "ca": 700.0, "resultat_net": 70.0},
                                        {"fin": "2019-12-31", "ca": 650.0, "resultat_net": 60.0}]}
        serie = F.serie_annuelle(s, 5)
        self.assertEqual([x["fin"] for x in serie], ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31", "2020-12-31"])
        self.assertEqual(serie[0]["ca"], 1010.0)  # la SEC l'emporte sur l'exercice commun
        self.assertEqual(s["annuel"][0]["ca"], 1000.0)  # données d'origine inchangées

    def test_mesures_completes(self):
        s = societe()
        m = A.mesures(s)
        for cle in ("fcf_yield", "benefices_normalises", "roic_wacc", "regularite", "rendement_actionnaire", "altman_z", "mscore",
                    "goodwill_actif", "current_ratio", "marge_brute", "cycle_cash", "capex_amortissements", "intensite_rd",
                    "detention_dirigeants", "evolution_actions"):
            self.assertIn(cle, m, cle)
        self.assertAlmostEqual(m["fcf_yield"], 4.0)
        self.assertAlmostEqual(m["rendement_actionnaire"], (30 + 20 - 5) / 2000 * 100)
        self.assertAlmostEqual(m["evolution_actions"], (100 / 110 - 1) * 100)
        self.assertAlmostEqual(m["detention_dirigeants"], 8.0)
        self.assertEqual(m["alertes"], [])
        n = F.notes(m, None, CFG)
        self.assertEqual(set(n), set(F.LIBELLES))
        ind = F.indicateurs(m, n)
        for x in ind.values():
            self.assertTrue(ton_conforme(x["affichage"] + " " + x["complement"]), x)
        self.assertTrue(ton_conforme(A.etude_approfondie(m)))
        # Hors technologies et santé : pas d'intensité en R&D
        self.assertNotIn("intensite_rd", A.mesures(societe(secteur_gics="Industrials")))

    def test_financieres(self):
        m = A.mesures(societe(financier="banque", secteur_gics="Financials"))
        for cle in ("altman_z", "mscore", "fcf_yield", "roic_wacc", "cycle_cash", "current_ratio"):
            self.assertNotIn(cle, m)
        n = F.notes(m, "banque", CFG)
        self.assertTrue(set(n) <= set(F.FINANCIERS))
        self.assertIn("rendement_actionnaire", n)

    def test_alerte_mscore(self):
        s = societe()
        s["annuel"][0] = exercice("2025-12-31", creances=400.0, ca=1500.0, resultat_net=300.0, cfo=50.0)
        m = A.mesures(s)
        self.assertIn("mscore", [a["cle"] for a in m["alertes"]])
        self.assertTrue(ton_conforme(m["alertes"][-1]["texte"]))


class TestIntegration(unittest.TestCase):
    def test_couverture_sur_indicateurs_de_base(self):
        p = {"a": 0.5, "b": 0.3, "x": 0.2}
        g = A.note_globale({"a": 70, "b": 70}, p, ["a", "b"])
        self.assertEqual(g["couverture"], 1.0)  # indicateur approfondi « x » absent : couverture intacte
        self.assertEqual(A.note_globale({"a": 70, "b": 70}, p)["couverture"], 0.8)
        g = note_avec_dynamique({"a": 70, "b": 70, "x": 20}, p, None, 0.08, ["a", "b"])
        self.assertEqual(g["note"], round(70 * 0.8 + 20 * 0.2))

    def test_ponderations(self):
        for k in ("ponderations", "ponderations_financieres"):
            self.assertAlmostEqual(sum(v for c, v in CONFIG[k].items() if not c.startswith("_")), 1.0)
        for c in CONFIG["ponderations"]:
            if not c.startswith("_"):
                self.assertTrue(c in A.BAREMES or c in F.LIBELLES, c)
        familles = [c for v in CFG["familles"].values() for c in v]
        self.assertEqual(len(familles), len(set(familles)))

    def test_meme_perimetre(self):
        from agents.entreprises.agent import meme_perimetre
        e = {"analyse_financiere": {"indicateurs": {"fcf_yield": {}, "altman_z": {}}}}
        self.assertTrue(meme_perimetre(e, e))
        self.assertFalse(meme_perimetre({}, e))  # fiche d'avant l'analyse approfondie
        self.assertFalse(meme_perimetre({"analyse_financiere": {"indicateurs": {"fcf_yield": {}}}}, e))  # comptes relus

    def test_sous_notes(self):
        sn = F.sous_notes({"fcf_yield": 80, "roic_wacc": 60, "fscore": 90}, CFG)
        self.assertEqual(sn["valeur_cycle"]["note"], 70)
        self.assertEqual(sn["qualite"]["note"], 90)
        self.assertIsNone(sn["alignement"]["note"])

    def test_criteres_pepite(self):
        cfg = CONFIG["pepites"]
        m = A.mesures(societe())
        base = A.criteres_pepite(m, {}, None, cfg)["criteres"]
        self.assertTrue(base["zscore_hors_detresse"] and base["mscore_non_suspect"] and base["pas_de_sommet_de_cycle"])
        m2 = {**m, "altman": {"z": 1.2, "zone": "détresse"}, "sommet_cycle": True, "beneish": {"m": -1.0, "suspect": True}}
        c = A.criteres_pepite(m2, {}, None, cfg)
        self.assertFalse(c["ok"])
        self.assertFalse(c["criteres"]["zscore_hors_detresse"] or c["criteres"]["pas_de_sommet_de_cycle"] or c["criteres"]["mscore_non_suspect"])
        self.assertNotIn("zscore_hors_detresse", A.criteres_pepite(m2, {}, "banque", cfg)["criteres"])
        sans = copy.deepcopy(cfg)
        sans["exclure_sommet_cycle"] = False
        self.assertNotIn("pas_de_sommet_de_cycle", A.criteres_pepite(m2, {}, None, sans)["criteres"])


def soc_reco(prix=15.0):
    return {"prix": prix, "devise_cours": "EUR", "devise_comptes": "EUR", "actions": 100.0,
            "annuel": [{"fin": "2025-12-31", "ca": 1100.0, "ebit": 220.0, "ebitda": 300.0, "resultat_net": 100.0, "fcf": 90.0}],
            "fx_comptes": 1.1, "fx_cours": 1.1, "region": "europe", "financier": None, "date_cours": "2026-11-02"}


def mes(**k):
    m = {"per_mediane_regionale": 20.0, "ev_ebitda_mediane_regionale": 10.0, "dette_nette": 200.0, "croissance_ca_3ans": 6.0,
         "momentum_12m": 12.0, "fscore": {"score": 7}, "alertes": []}
    m.update(k)
    return m


class TestRecommandation(unittest.TestCase):
    CR = CONFIG["recommandation"]

    def test_valorisation_sur_benefices_normalises(self):
        normal = R.valeur_estimee(mes(), soc_reco(), self.CR)
        cycle = R.valeur_estimee(mes(sommet_cycle=True, benefice_moyen=50.0, benefices_normalises=2.0, benefice_moyen_annees=5,
                                     fcf_moyen=40.0), soc_reco(), self.CR)
        self.assertLess(cycle["centrale"], normal["centrale"])
        self.assertIn("sommet de cycle", cycle["normalisation"])
        self.assertIsNone(normal["normalisation"])
        r = R.recommander(soc_reco(), mes(sommet_cycle=True, benefice_moyen=50.0, benefices_normalises=2.0, benefice_moyen_annees=5),
                          70, "élevé", [], self.CR)
        self.assertIn("bénéfices normalisés", r["justification"])
        self.assertTrue(ton_conforme(r["justification"]))

    def test_altman_detresse_signal_qualite_defavorable(self):
        # Z-score seul (filiale de financement…) : pas de signal défavorable
        r = R.recommander(soc_reco(), mes(altman={"z": 1.1, "zone": "détresse", "confirme": False}), 70, "élevé", [], self.CR)
        self.assertNotEqual(next(x for x in r["signaux"] if x["cle"] == "qualite")["sens"], -1)
        r = R.recommander(soc_reco(), mes(altman={"z": 1.1, "zone": "détresse", "confirme": True, "signes": ["current ratio 0,8"]}),
                          70, "élevé", [], self.CR)
        q = next(x for x in r["signaux"] if x["cle"] == "qualite")
        self.assertEqual(q["sens"], -1)
        self.assertIn("détresse", q["texte"])
        self.assertNotEqual(r["si_non_detenu"], "Acheter")
        self.assertTrue(any("Z-score" in c for c in r["conditions_invalidation"]) or len(r["conditions_invalidation"]) >= 2)


if __name__ == "__main__":
    unittest.main()
