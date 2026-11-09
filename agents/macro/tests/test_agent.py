"""Tests de l'agent macro, sans réseau : python -m unittest discover -s agents -t .
Les données de test (agents/macro/tests/donnees) sont des captures réelles du 02/11/2026."""
import json
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from agents.commun.sortie import lire_json
from agents.macro import analyse as A
from agents.macro.agent import main

CFG = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
JOUR = date(2026, 11, 2)


def serie_mensuelle(valeurs, debut=(2025, 1)):
    a, m = debut
    res = []
    for v in valeurs:
        res.append((f"{a}-{m:02d}", v))
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return res


class TestPhase(unittest.TestCase):
    def test_quadrants(self):
        hausse = serie_mensuelle([99 + 0.1 * k for k in range(10)])
        baisse = serie_mensuelle([101 - 0.1 * k for k in range(10)])
        inf_hausse = serie_mensuelle([2 + 0.2 * k for k in range(10)])
        inf_baisse = serie_mensuelle([4 - 0.2 * k for k in range(10)])
        s = CFG["seuils"]
        self.assertEqual(A.phase_zone(hausse, inf_baisse, (3, 3.2), (3, 2.5), s)["phase"], "Reprise")
        self.assertEqual(A.phase_zone(hausse, inf_hausse, (3, 3.2), (2, 2.5), s)["phase"], "Surchauffe")
        self.assertEqual(A.phase_zone(baisse, inf_hausse, (3, 2.5), (2, 2.5), s)["phase"], "Ralentissement inflationniste")
        self.assertEqual(A.phase_zone(baisse, inf_baisse, (3, 2.5), (3, 2.5), s)["phase"], "Expansion sans inflation")

    def test_deux_signaux_concordants_pour_changer(self):
        # La croissance accélère longtemps, puis un seul mois de baisse : la phase ne change pas
        cli = serie_mensuelle([99 + 0.1 * k for k in range(10)] + [99.6])
        inf = serie_mensuelle([4 - 0.2 * k for k in range(11)])
        z = A.phase_zone(cli, inf, (3, 3.2), (3, 2.5), CFG["seuils"])
        self.assertEqual(z["phase"], "Reprise")
        # Deux mois de baisse et un FMI en baisse : changement annoncé, avec la phase précédente et sa date
        cli = serie_mensuelle([99 + 0.1 * k for k in range(10)] + [99.6, 99.2])
        inf = serie_mensuelle([4 - 0.2 * k for k in range(12)])
        z = A.phase_zone(cli, inf, (3.2, 3.0), (3, 2.5), CFG["seuils"])
        self.assertEqual(z["phase"], "Expansion sans inflation")
        self.assertEqual(z["phase_precedente"], "Reprise")
        self.assertEqual(z["depuis"], "2025-11")  # baisse sur 3 mois + FMI : deux signaux concordants

    def test_donnees_insuffisantes(self):
        self.assertIsNone(A.phase_zone(serie_mensuelle([100, 101]), serie_mensuelle([2, 3]), None, None, CFG["seuils"]))


class TestRecession(unittest.TestCase):
    cfg = CFG["recession"]

    def test_courbe_inversee(self):
        s = [("2026-10-01", 0.2), ("2026-10-02", -0.1), ("2026-10-12", -0.2)]
        e = A.etat_courbe(s, self.cfg, JOUR)
        self.assertEqual((e["niveau"], e["depuis"], e["jours"]), ("rouge", "2026-10-02", 10))

    def test_desinversion_recente_puis_ancienne(self):
        s = [("2026-01-01", -0.3), ("2026-06-01", -0.1), ("2026-07-01", 0.6)]
        self.assertEqual(A.etat_courbe(s, self.cfg, JOUR)["niveau"], "orange")
        s = [("2023-01-01", -0.3), ("2023-07-01", 0.6), ("2026-10-01", 0.8)]
        self.assertEqual(A.etat_courbe(s, self.cfg, JOUR)["niveau"], "vert")

    def test_sahm(self):
        chomage = serie_mensuelle([3.5] * 14 + [3.8, 4.1, 4.4])
        self.assertAlmostEqual(dict(A.sahm_calculee(chomage))["2026-05"], 0.6, places=2)
        self.assertEqual(A.niveau_sahm(0.6, self.cfg), "rouge")
        self.assertEqual(A.niveau_sahm(0.35, self.cfg), "orange")

    def test_cli(self):
        self.assertEqual(A.niveau_cli(99.5, -0.2), "rouge")
        self.assertEqual(A.niveau_cli(100.5, -0.2), "orange")
        self.assertEqual(A.niveau_cli(100.5, 0.2), "vert")


class TestBanques(unittest.TestCase):
    def test_mouvement_tendance_et_verification(self):
        bis = [("2025-10-01", 2.0), ("2026-06-01", 2.0), ("2026-09-16", 2.25), ("2026-10-26", 2.25)]
        nat = [("2025-10-01", 2.0), ("2026-09-16", 2.25), ("2026-10-29", 2.5)]
        cal = {"dates": ["2026-10-28", "2026-12-09"]}
        b = A.banque_centrale("boc", {"nom": "BoC", "pays": "Canada"}, bis, nat, "nationale", cal, JOUR)
        self.assertEqual(b["taux"], 2.5)
        self.assertEqual(b["dernier_mouvement"]["date"], "2026-10-29")
        self.assertEqual(b["tendance_12m"], {"variation_pts": 0.5, "sens": "hausse"})
        self.assertEqual(b["prochaine_reunion"], {"date": "2026-12-09", "jours": 37})
        self.assertEqual(b["verification"], "non comparable")  # la BRI n'a pas encore le dernier mouvement

    def test_sans_calendrier(self):
        self.assertIsNone(A.prochaine_reunion({"sans_calendrier": True, "note": "x"}, JOUR)["date"])
        self.assertEqual(A.prochaine_reunion({"dates": ["2026-01-01"]}, JOUR)["note"], "aucune date future dans le calendrier")


class TestTauxReels(unittest.TestCase):
    def test_passe_attendu_et_verification(self):
        fed = [("2025-11-01", 4.4), ("2026-11-02", 3.9)]
        inflation = [(f"2025-{m:02d}", 2.9) for m in range(9, 13)] + [(f"2026-{m:02d}", 3.7) for m in range(1, 10)]
        dfii10 = [("2025-10-31", 1.8), ("2026-11-02", 2.6)]
        t10 = [("2025-10-31", 2.3), ("2026-11-02", 2.3)]
        r = A.taux_reels_us(fed, "Fed", inflation, {"DFII10": dfii10, "T10YIE": t10}, {}, [("2026-11-02", 4.88)])
        self.assertEqual(r["passe"]["valeur"], 0.2)  # 3,9 − 3,7
        self.assertEqual(r["passe"]["variation_12m"], -1.3)  # (3,9 − 3,7) − (4,4 − 2,9)
        self.assertEqual((r["attendu_10a"]["valeur"], r["attendu_10a"]["variation_12m"], r["attendu_10a"]["sens"]), (2.6, 0.8, "hausse"))
        self.assertEqual(r["attendu_10a"]["verification"], "concordant")  # 4,88 − 2,3 = 2,58
        self.assertEqual(r["point_mort_10a"]["sens"], "stable")
        self.assertIsNone(r["attendu_5a"])
        self.assertIn("supérieur de 2,4 pt", r["texte"])
        self.assertTrue(A.ton_conforme(r["texte"]))
        divergent = A.taux_reels_us(None, "", None, {"DFII10": dfii10, "T10YIE": t10}, {}, [("2026-11-02", 5.2)])
        self.assertEqual(divergent["attendu_10a"]["verification"], "divergent")
        self.assertIsNone(divergent["passe"])

    def test_aucune_donnee(self):
        self.assertIsNone(A.taux_reels_us(None, "", None, {}, {}))


class TestCalendrier(unittest.TestCase):
    def test_structure(self):
        cal = json.loads((Path(__file__).resolve().parents[1] / "calendrier_banques_centrales.json").read_text(encoding="utf-8"))
        self.assertEqual(set(cal["banques"]), set(CFG["banques_centrales"]))
        for cle, b in cal["banques"].items():
            self.assertTrue(b["source"].startswith("http"), cle)
            self.assertEqual(b["dates"], sorted(b["dates"]), cle)
            for d in b["dates"]:
                date.fromisoformat(d)
            if not b.get("sans_calendrier"):
                self.assertTrue(b["dates"], cle)


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dossier)

    def test_execution_complete(self):
        self.assertEqual(main(["--test", "--data", str(self.dossier), "--date", "2026-11-02"]), 0)
        d = lire_json(self.dossier / "macro.json")
        self.assertFalse(d["meta"]["fictif"])
        donnees = d["donnees"]
        self.assertEqual([z["cle"] for z in donnees["cycle"]["zones"]],
                         ["monde", "etats_unis", "zone_euro", "chine", "japon", "emergents"])
        for z in donnees["cycle"]["zones"]:
            self.assertIn(z["phase"], A.PHASES.values())
            self.assertIn(z["confiance"], ("faible", "moyen", "élevé"))
            self.assertTrue(z["contre_scenario"])
        self.assertEqual(len(donnees["banques_centrales"]), 11)
        self.assertEqual(len(donnees["recession"]["signaux"]), 6)
        self.assertEqual(len(donnees["lectures_pays"]), 31)
        us = donnees["taux_reels"]["etats_unis"]
        for cle in ("passe", "attendu_10a", "attendu_5a", "point_mort_10a", "point_mort_5a"):
            self.assertIsNotNone(us[cle]["valeur"], cle)
        self.assertEqual(us["attendu_10a"]["verification"], "concordant")
        self.assertFalse(donnees["taux_reels"]["zone_euro"]["disponible"])
        self.assertTrue(A.ton_conforme(us["texte"]))
        # Ton froid : aucun superlatif, et deux phrases par pays
        for l in donnees["lectures_pays"].values():
            self.assertTrue(A.ton_conforme(l["texte"]))
            self.assertEqual(l["texte"].count(". ") + 1, 2, l["texte"])
        self.assertTrue((self.dossier / "historique" / "macro" / "2026-11-02.json").exists())
        self.assertTrue((self.dossier / "recap" / "macro-2026-11-02.md").exists())
        self.assertIsNotNone(lire_json(self.dossier / "signaux" / "macro.json"))
        journal = lire_json(self.dossier / "journal" / "agent-macro.json")
        self.assertEqual(journal["meta"]["sante"]["intervalle_min"], 1440)
        self.assertTrue(journal["meta"]["sante"]["echeances"])
        index = lire_json(self.dossier / "journal" / "index.json")["donnees"]
        self.assertIn("agent-macro.json", [e["fichier"] for e in index])

    def test_signal_de_changement_de_phase(self):
        main(["--test", "--data", str(self.dossier), "--date", "2026-11-02"])
        chemin = self.dossier / "macro.json"
        d = lire_json(chemin)
        z0 = d["donnees"]["cycle"]["zones"][0]
        brute = z0["phase_brute"]
        # État précédent différent, nouvelle phase observée depuis 22 jours : le changement est confirmé aujourd'hui
        z0.update({"phase": "Surchauffe", "changement_en_cours": {"vers": brute, "depuis": "2026-10-11"}})
        chemin.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        main(["--test", "--data", str(self.dossier), "--date", "2026-11-02"])
        types = [s["type"] for s in lire_json(self.dossier / "signaux" / "macro.json")["donnees"]]
        self.assertIn("changement_de_phase", types)
        self.assertEqual(lire_json(chemin)["donnees"]["cycle"]["zones"][0]["phase"], brute)

    def test_pas_de_changement_de_phase_avant_confirmation(self):
        main(["--test", "--data", str(self.dossier), "--date", "2026-11-02"])
        chemin = self.dossier / "macro.json"
        d = lire_json(chemin)
        d["donnees"]["cycle"]["zones"][0].update({"phase": "Surchauffe", "changement_en_cours": None})
        chemin.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        (self.dossier / "signaux" / "macro.json").unlink()
        main(["--test", "--data", str(self.dossier), "--date", "2026-11-02"])
        z = lire_json(chemin)["donnees"]["cycle"]["zones"][0]
        self.assertEqual(z["phase"], "Surchauffe")
        self.assertIn("en cours de confirmation", z["changement_en_cours"]["texte"])
        types = [s["type"] for s in lire_json(self.dossier / "signaux" / "macro.json")["donnees"]]
        self.assertNotIn("changement_de_phase", types)



class TestConfirmationPhase(unittest.TestCase):
    """Anti-girouette de la phase : une nouvelle phase n'est publiée qu'après 3 semaines d'observation continue."""

    CFG = {"semaines": 3, "signaux_min": 2}
    E, R = "Expansion sans inflation", "Ralentissement inflationniste"

    def zone(self, phase, conc_inf=2):
        return {"phase": phase, "phase_precedente": None, "depuis": None, "croissance": {"concordants": 3}, "inflation": {"concordants": conc_inf}}

    def test_alternance_du_debut_novembre_neutralisee(self):
        # Historique réel du monde (02/11 → 08/11), puis la phase brute du 09/11
        obs = [("2026-11-02", self.E), ("2026-11-03", self.R), ("2026-11-04", self.R), ("2026-11-05", self.E),
               ("2026-11-06", self.R), ("2026-11-07", self.E), ("2026-11-08", self.E)]
        z = A.confirmer_phase(self.zone(self.R), None, obs, date(2026, 11, 9), self.CFG)
        self.assertEqual(z["phase"], self.E)
        self.assertEqual(z["phase_brute"], self.R)
        self.assertEqual(z["changement_en_cours"]["vers"], self.R)
        self.assertIn("en cours de confirmation", z["changement_en_cours"]["texte"])

    def test_changement_confirme_apres_trois_semaines(self):
        ancienne = None
        publiees = []
        d0 = date(2026, 11, 9)
        for k in range(25):
            jour_k = d0 + timedelta(days=k)
            z = A.confirmer_phase(self.zone(self.R), ancienne, [("2026-11-01", self.E)], jour_k, self.CFG)
            publiees.append(z["phase"])
            ancienne = z
        self.assertEqual(publiees[20], self.E)  # 20 jours d'observation : pas encore
        self.assertEqual(publiees[21], self.R)  # 21 jours : confirmé
        self.assertEqual(ancienne["phase_precedente"], self.E)
        self.assertIsNone(ancienne["changement_en_cours"])

    def test_interruption_remet_le_decompte_a_zero(self):
        ancienne = A.confirmer_phase(self.zone(self.R), None, [("2026-11-01", self.E)], date(2026, 11, 2), self.CFG)
        for k in range(3, 15):
            ancienne = A.confirmer_phase(self.zone(self.R), ancienne, [], date(2026, 11, k), self.CFG)
        ancienne = A.confirmer_phase(self.zone(self.E), ancienne, [], date(2026, 11, 15), self.CFG)  # retour : décompte annulé
        self.assertIsNone(ancienne["changement_en_cours"])
        z = A.confirmer_phase(self.zone(self.R), ancienne, [], date(2026, 11, 16), self.CFG)
        self.assertEqual(z["changement_en_cours"]["depuis"], "2026-11-16")

    def test_deux_signaux_concordants_exiges(self):
        ancienne = A.confirmer_phase(self.zone(self.R, conc_inf=1), None, [("2026-10-01", self.E)], date(2026, 11, 1), self.CFG)
        for k in range(2, 31):
            ancienne = A.confirmer_phase(self.zone(self.R, conc_inf=1), ancienne, [], date(2026, 11, k), self.CFG)
        self.assertEqual(ancienne["phase"], self.E)  # l'axe inflation n'a qu'un signal : pas de changement
        self.assertFalse(ancienne["changement_en_cours"]["signaux_concordants"])
        z = A.confirmer_phase(self.zone(self.R, conc_inf=2), ancienne, [], date(2026, 12, 1), self.CFG)
        self.assertEqual(z["phase"], self.R)


if __name__ == "__main__":
    unittest.main()
