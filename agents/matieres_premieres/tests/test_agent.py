"""Tests de l'agent matières premières, sans réseau : python -m unittest discover -s agents/matieres_premieres -t .
Les données de test (agents/matieres_premieres/tests/donnees) sont des captures réelles du 07/11/2026,
sauf les stocks EIA (pas de clé lors de la capture) : série synthétique créée dans un dossier temporaire.
Les tests n'utilisent jamais les vrais config/ et data/ : tout est écrit dans des dossiers temporaires."""
import json
import math
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from agents.commun.essais import copier_donnees_test
from agents.commun.sortie import ecrire_json, lire_json
from agents.matieres_premieres import analyse as A
from agents.matieres_premieres.agent import flux_etf, main
from agents.matieres_premieres.sources import contrats_suivants, lire_wasde

DOSSIER = Path(__file__).resolve().parent
CFG = json.loads((DOSSIER.parent / "config.json").read_text(encoding="utf-8"))
JOUR = date(2026, 11, 7)


def quotidienne(valeurs, fin=JOUR):
    n = len(valeurs)
    return [((fin - timedelta(days=n - 1 - k)).isoformat(), v) for k, v in enumerate(valeurs)]


def eia_synthetique(fin=date(2026, 10, 30), ecart=0.0, dernier_saut=0.0):
    """Stocks hebdomadaires saisonniers sur 6 ans ; `ecart` : écart (en %) de la dernière année à la normale."""
    points = []
    for k in range(6 * 52, -1, -1):
        d = fin - timedelta(weeks=k)
        v = 420 + 20 * math.sin(d.timetuple().tm_yday / 365.25 * 2 * math.pi)
        if k < 52:
            v *= 1 + ecart / 100
        points.append([d.isoformat(), round(v, 1)])
    points[-1][1] += dernier_saut
    return points


class TestCalculs(unittest.TestCase):
    def test_contrats_suivants(self):
        c = contrats_suivants("CL", "NYM", "FGHJKMNQUVXZ", JOUR, 3)
        self.assertEqual([x["symbole"] for x in c], ["CLZ26.NYM", "CLF27.NYM", "CLG27.NYM"])
        c = contrats_suivants("GC", "CMX", "GJMQVZ", JOUR, 2)
        self.assertEqual([x["echeance"] for x in c], ["2026-12", "2027-02"])

    def test_tendance(self):
        hausse = quotidienne([100 + k * 0.1 for k in range(400)])
        t = A.tendance(hausse)
        self.assertGreater(t["note"], 60)
        self.assertIn("au-dessus de sa moyenne 200 jours", t["texte"])
        baisse = quotidienne([140 - k * 0.1 for k in range(400)])
        self.assertLess(A.tendance(baisse)["note"], 40)
        self.assertIsNone(A.tendance(hausse[:30]))

    def test_courbe_backwardation_et_contango(self):
        contrats = [{"symbole": f"X{k}", "echeance": f"2027-{k:02d}"} for k in range(1, 13)]
        tendu = {f"X{k}": ["2026-11-06", 100 - k] for k in range(1, 13)}
        c = A.courbe(contrats, tendu, 99, 2.0)
        self.assertEqual(c["structure"], "backwardation")
        self.assertGreater(c["note"], 50)
        detendu = {f"X{k}": ["2026-11-06", 100 + k] for k in range(1, 13)}
        c = A.courbe(contrats, detendu, 101, 2.0)
        self.assertEqual(c["structure"], "contango")
        self.assertLess(c["roulement_pct_an"], 0)
        # Un contrat aberrant (illiquide) est écarté ; moins de deux contrats : pas de note
        self.assertIsNone(A.courbe(contrats[:2], {"X1": ["2026-11-06", 100], "X2": ["2026-11-06", 500]}, 100, 2.0))

    def test_positionnement_a_contre_courant(self):
        semaines = [((JOUR - timedelta(weeks=156 - k)).isoformat(), k) for k in range(157)]
        encombre = [{"date": d, "long": 1000 + 10 * k, "short": 1000, "oi": 50000} for d, k in semaines]
        p = A.positionnement(encombre, JOUR, CFG["seuils"])
        self.assertEqual(p["extreme"], "encombre")
        self.assertLess(p["note"], 40)
        vendeur = [{"date": d, "long": 1000, "short": 1000 + 10 * k, "oi": 50000} for d, k in semaines]
        p = A.positionnement(vendeur, JOUR, CFG["seuils"])
        self.assertEqual(p["extreme"], "capitulation")
        self.assertGreater(p["note"], 60)
        self.assertIsNone(A.positionnement(encombre[:20], JOUR, CFG["seuils"]))

    def test_stocks_eia_moyenne_5_ans_et_choc(self):
        normal = {"brut": [tuple(p) for p in eia_synthetique()]}
        s = A.stocks_eia(normal, ["brut"], CFG["eia"], CFG["seuils"])
        self.assertAlmostEqual(s["ecart_moyen_pct"], 0, delta=0.5)
        bas = {"brut": [tuple(p) for p in eia_synthetique(ecart=-8, dernier_saut=-25)]}
        s = A.stocks_eia(bas, ["brut"], CFG["eia"], CFG["seuils"])
        self.assertLess(s["ecart_moyen_pct"], -7)
        self.assertGreater(s["note"], 60)  # stocks bas : marché tendu, favorable
        self.assertTrue(s["series"][0]["choc"])

    def test_stocks_usda_croisement(self):
        psd = {"publication": "2026-10", "produits": {"ble": {str(a): {"stocks_fin": 250 + a % 7 * 5, "consommation": 800} for a in range(2000, 2027)}}}
        wasde = {"publication": "2026-10", "produits": {"ble": {"campagne": "2026/27", "stocks_fin": 270, "consommation": 800,
                                                                 "precedent": {"stocks_fin": 250, "consommation": 800}}}}
        psd["produits"]["ble"]["2026"] = {"stocks_fin": 255, "consommation": 800}
        s, verif = A.stocks_usda("ble", psd, wasde, CFG["seuils"])
        self.assertEqual(verif, "divergent")  # PSD 2026 : 255/800, WASDE : 270/800 (écart > 3 %)
        self.assertTrue(s["choc"])  # révision de +8 % des stocks
        psd["produits"]["ble"]["2026"] = {"stocks_fin": 270, "consommation": 800}
        self.assertEqual(A.stocks_usda("ble", psd, wasde, CFG["seuils"])[1], "concordant")
        self.assertEqual(A.stocks_usda("ble", None, None, CFG["seuils"]), (None, "aucune_source"))

    def test_lire_wasde(self):
        texte = "\n".join([
            "                         World Wheat Supply and Use  1/",
            "                                  2025/26 Est.",
            "World  3/                 260.40  844.06  221.57  168.65  822.90  226.91  281.55",
            "                                  2026/27 Proj.",
            "World  3/               ",
            "                     Sep  280.60  822.43  207.48  164.73  826.75  211.77  276.29",
            "                     Oct  281.55  822.39  204.80  166.90  827.90  208.97  276.04",
            "  World Less China      ",
            "                     Sep  158.40  681.43  201.48  133.73  678.75  210.77  156.09",
            "                         World Coarse Grain Supply and Use  1/",
            "World  3/                 1.00  1.00  1.00  1.00  1.00  1.00  1.00"])
        w = lire_wasde(texte, "World Wheat Supply and Use")
        self.assertEqual((w["campagne"], w["mois"], w["stocks_fin"], w["consommation"]), ("2026/27", "Oct", 276.04, 827.9))
        self.assertEqual(w["precedent"]["stocks_fin"], 276.29)

    def test_verdict_deux_signaux_concordants(self):
        cfg = CFG["verdicts"]
        un_seul = {"tendance": {"note": 95}, "courbe": {"note": 55}, "macro": {"note": 55}}
        v, _, _, raison = A.verdict(65, un_seul, cfg, "moyen")
        self.assertEqual(v, "Neutre (biais positif)")
        self.assertIn("1 signal concordant", raison)
        deux = {"tendance": {"note": 80}, "courbe": {"note": 70}, "macro": {"note": 50}}
        self.assertEqual(A.verdict(65, deux, cfg, "moyen")[:2], ("Surpondérer", ["tendance", "courbe"]))
        baissier = {"tendance": {"note": 20}, "stocks": {"note": 30}, "macro": {"note": 45}}
        self.assertEqual(A.verdict(35, baissier, cfg, "élevé")[0], "Sous-pondérer")
        # Hystérésis : un « Surpondérer » est conservé à 59 si les signaux restent concordants
        self.assertEqual(A.verdict(59, deux, cfg, "moyen", "Surpondérer")[0], "Surpondérer")
        self.assertEqual(A.verdict(59, deux, cfg, "moyen")[0], "Neutre")
        self.assertEqual(A.verdict(None, deux, cfg, "faible")[0], "Neutre")

    def test_verdict_exige_une_confiance_suffisante(self):
        """Cas du gaz TTF du 07/11 : note 68, deux signaux concordants, mais confiance « faible »."""
        cfg = CFG["verdicts"]
        deux = {"tendance": {"note": 95}, "geopolitique": {"note": 71}, "macro": {"note": 47}, "niveau": {"note": 27}}
        v, _, _, raison = A.verdict(68.5, deux, cfg, "faible")
        self.assertEqual(v, "Neutre (biais positif)")
        self.assertIn("confiance « faible »", raison)
        baissier = {"tendance": {"note": 20}, "stocks": {"note": 30}}
        self.assertEqual(A.verdict(35, baissier, cfg, "faible")[0], "Neutre (biais négatif)")
        # Les deux conditions manquent : les deux raisons sont données
        self.assertIn(" et ", A.verdict(35, {"tendance": {"note": 20}}, cfg, "faible")[3])
        # Hystérésis : un « Surpondérer » précédent n'est pas conservé si la confiance tombe à « faible »
        self.assertEqual(A.verdict(59, deux, cfg, "faible", "Surpondérer")[0], "Neutre (biais positif)")

    def test_controle_final_des_verdicts(self):
        cfg = CFG["verdicts"]
        bon = {"nom": "Or", "verdict": "Surpondérer", "confiance": "moyen", "signaux_favorables": ["a", "b"]}
        self.assertEqual(A.controler_verdict(bon, cfg), [])
        self.assertEqual(len(A.controler_verdict({**bon, "confiance": "faible"}, cfg)), 1)
        self.assertEqual(len(A.controler_verdict({**bon, "confiance": "faible", "signaux_favorables": ["a"]}, cfg)), 2)
        self.assertEqual(A.controler_verdict({"nom": "Or", "verdict": "Neutre (biais positif)", "confiance": "faible"}, cfg), [])
        self.assertTrue(A.controler_verdict({"nom": "Or", "verdict": "Acheter"}, cfg))

    def test_verdict_famille_avec_biais(self):
        cfg = CFG["verdicts"]
        self.assertEqual(A.verdict_famille([70, 68], ["Surpondérer", "Surpondérer"], cfg), "Surpondérer")
        self.assertEqual(A.verdict_famille([70, 68], ["Neutre (biais positif)", "Surpondérer"], cfg), "Neutre (biais positif)")
        self.assertEqual(A.verdict_famille([50, 52], ["Neutre", "Neutre"], cfg), "Neutre")

    def test_note_globale_repartit_les_poids(self):
        sous = {"tendance": {"note": 80}, "stocks": None, "macro": {"note": 40}}
        self.assertEqual(A.note_globale(sous, {"tendance": 1, "stocks": 5, "macro": 1}), 60.0)
        self.assertIsNone(A.note_globale({"tendance": None}, {"tendance": 1}))

    def test_arguments_et_invalidations(self):
        sous = {k: {"note": n, "texte": f"texte {k}"} for k, n in zip(CFG["sous_notes"], (80, 70, 65, 50, 45, 30, 20, 55))}
        pour, contre = A.arguments(sous, CFG["sous_notes"])
        self.assertEqual(len(pour), 3)
        self.assertEqual(len(contre), 3)
        self.assertTrue(pour[0].startswith("Tendance et momentum (80/100)"))
        self.assertTrue(contre[0].startswith("Flux des ETF (20/100)"))
        serie = quotidienne([100 + k * 0.1 for k in range(300)])
        sous["tendance"]["mm200"] = 115.0
        sous["courbe"].update(roulement_pct_an=-4.0, structure="contango")
        sous["positionnement"].update(percentile=50)
        sous["stocks"].update(type="eia", ecart_moyen_pct=3.0)
        for v in A.VERDICTS:
            self.assertEqual(len(A.invalidations(v, {"unite": "$"}, sous, serie, CFG["seuils"])), 2)

    def test_geopolitique_premiers_producteurs(self):
        m = next(x for x in CFG["matieres"] if x["cle"] == "wti")
        geo = {"date": "2026-11-07", "evenements": [
            {"titre": "Tensions dans le Golfe", "categorie": "maritime", "pays": ["IR"], "chronologie": [{"date": "2026-11-05T10:00:00Z", "gravite": 4}]},
            {"titre": "Élection locale", "categorie": "election", "pays": ["US"], "chronologie": [{"date": "2026-11-05T10:00:00Z", "gravite": 4}]},
            {"titre": "Ancien conflit", "categorie": "conflit", "pays": ["SA"], "chronologie": [{"date": "2026-09-01T10:00:00Z", "gravite": 5}]}]}
        g = A.geopolitique(m, geo, None, JOUR, 14)
        self.assertEqual([e["titre"] for e in g["evenements"]], ["Tensions dans le Golfe"])
        self.assertGreater(g["note"], 50)
        self.assertEqual(A.geopolitique(m, {"evenements": []}, None, JOUR, 14)["note"], 50)

    def test_ton_factuel(self):
        self.assertFalse(A.conformes(["Une hausse spectaculaire du cuivre"]))
        self.assertTrue(A.conformes(["Niveau historique (40/100) : cours au percentile 66"]))

    def test_flux_etf_historique(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        for k in range(40, 0, -1):
            j = JOUR - timedelta(days=k)
            ecrire_json(d / f"{j.isoformat()}.json", {"meta": {}, "donnees": {"etf": {"GLD": {"date": j.isoformat(), "parts": 1e6 + (40 - k) * 1000, "vl": 100.0}}}})
        res, du_jour = flux_etf(d, {"GLD": {"date": JOUR.isoformat(), "parts": 1.05e6, "vl": 100.0, "encours": 1.05e8}}, CFG, JOUR)
        self.assertIn("GLD", du_jour)
        self.assertTrue(res["GLD"]["periodes"]["1m"]["complet"])
        self.assertGreater(res["GLD"]["periodes"]["1m"]["flux_musd"], 0)
        f = A.flux({"GLD": res["GLD"]})
        self.assertGreater(f["note"], 50)
        # Historique trop court : « en cours de constitution », sans note
        res, _ = flux_etf(Path(tempfile.mkdtemp()), {"SLV": {"date": JOUR.isoformat(), "parts": 1e6, "vl": 30.0}}, CFG, JOUR)
        self.assertIsNone(A.flux({"SLV": res["SLV"]})["note"])


class TestAgent(unittest.TestCase):
    """Exécution complète en mode test, dans un dossier temporaire."""

    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp(prefix="mp-"))
        cls.data = cls.d / "data"
        copier_donnees_test(cls.data, ("macro.json",))
        ecrire_json(cls.data / "risque.json", {"meta": {"fictif": False}, "donnees": {"mondial": {"palier": "Tension"}}})
        ecrire_json(cls.data / "geopolitique.json", {"meta": {"fictif": False}, "donnees": {"date": "2026-11-07", "evenements": [
            {"id": "e1", "titre": "Frappes près d'un terminal pétrolier", "categorie": "conflit", "pays": ["SA"], "mondial": False,
             "chronologie": [{"date": "2026-11-06T08:00:00Z", "gravite": 4}]}]}})
        ecrire_json(cls.data / "entreprises.json", {"meta": {"fictif": False}, "donnees": [
            {"ticker": "NEM", "nom": "Newmont", "pays": "US", "note": 80, "recommandation": {"n": "Acheter"}, "fiche": "data/entreprises/fiches/NEM.json"},
            {"ticker": "XOM", "nom": "ExxonMobil", "pays": "US", "note": 58, "recommandation": {"n": "Attendre"}, "fiche": "data/entreprises/fiches/XOM.json"}]})
        cls.surveillance = cls.d / "surveillance.json"
        cls.surveillance.write_text(json.dumps({"societes": [{"ticker": "XOM", "pays": "US"}]}), encoding="utf-8")
        cls.donnees = cls.d / "donnees"
        shutil.copytree(DOSSIER / "donnees", cls.donnees)
        (cls.donnees / "eia.json").write_text(json.dumps({k: eia_synthetique(ecart=-6 if k != "gaz" else 4) for k in CFG["eia"]}), encoding="utf-8")
        cls.args = ["--test", "--donnees-test", str(cls.donnees), "--data", str(cls.data), "--surveillance", str(cls.surveillance), "--date", "2026-11-07"]
        assert main(cls.args) == 0
        cls.sortie = lire_json(cls.data / "matieres_premieres.json")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, True)

    def test_perimetre_complet(self):
        cles = [m["cle"] for m in self.sortie["donnees"]["matieres"]]
        self.assertEqual(cles, [m["cle"] for m in CFG["matieres"]])
        self.assertEqual(len(cles), 18)
        self.assertEqual([f["cle"] for f in self.sortie["donnees"]["familles"]], list(CFG["familles"]))
        self.assertFalse(self.sortie["meta"]["fictif"])

    def test_fiche_complete(self):
        for m in self.sortie["donnees"]["matieres"]:
            self.assertIn(m["verdict"], A.VERDICTS)
            self.assertIn(m["confiance"], ("faible", "moyen", "élevé"))
            self.assertEqual(len(m["invalidations"]), 2, m["nom"])
            self.assertTrue(m["ce_qui_pourrait_me_donner_tort"])
            self.assertLessEqual(len(m["arguments_pour"]), 3)
            self.assertTrue(m["serie"], m["nom"])
            self.assertTrue(m["sources"])
            # Règle vérifiée sur toutes les matières premières : pas de recommandation directionnelle
            # sans confiance « moyen » ou « élevé » et deux signaux concordants
            if m["verdict"] in ("Surpondérer", "Sous-pondérer"):
                self.assertIn(m["confiance"], ("moyen", "élevé"), m["nom"])
                self.assertGreaterEqual(len(m["signaux_favorables" if m["verdict"] == "Surpondérer" else "signaux_defavorables"]), 2, m["nom"])
                self.assertIsNone(m["verdict_non_retenu"])
            if m["verdict"].startswith("Neutre ("):
                self.assertTrue(m["verdict_non_retenu"], m["nom"])
            self.assertEqual(A.controler_verdict(m, CFG["verdicts"]), [], m["nom"])

    def test_sources_croisees(self):
        par = {m["cle"]: m for m in self.sortie["donnees"]["matieres"]}
        self.assertEqual(par["wti"]["sous_notes"]["stocks"]["type"], "eia")
        self.assertEqual(par["ble"]["sous_notes"]["stocks"]["type"], "usda")
        self.assertIn(par["ble"]["sous_notes"]["stocks"]["verification"], ("concordant", "divergent"))
        self.assertIsNotNone(par["or"]["sous_notes"]["positionnement"])
        self.assertIsNotNone(par["wti"]["sous_notes"]["courbe"])
        self.assertTrue(par["uranium"]["indirect"])
        self.assertIn("indicateur indirect", par["uranium"]["mention"])
        self.assertIsNone(par["uranium"]["sous_notes"]["courbe"])
        self.assertEqual(par["wti"]["sous_notes"]["geopolitique"]["evenements"][0]["pays"], ["SA"])

    def test_producteurs_et_double_exposition(self):
        par = {m["cle"]: m for m in self.sortie["donnees"]["matieres"]}
        self.assertEqual([s["ticker"] for s in par["or"]["societes"]], ["NEM"])
        self.assertIsNone(par["or"]["double_exposition"])
        self.assertTrue(par["wti"]["societes"][0]["deja_detenue"])
        self.assertIn("ExxonMobil", par["wti"]["double_exposition"])
        za = next(p for p in par["platine"]["producteurs"] if p["code"] == "ZA")
        self.assertTrue(za["suivi"])
        ru = next(p for p in par["platine"]["producteurs"] if p["code"] == "RU")
        self.assertEqual((ru["nom"], ru["suivi"]), ("Russie", False))
        # Contango : le coût de roulement des supports à base de contrats à terme est chiffré
        self.assertTrue(any(s.get("cout_roulement") for s in par["cuivre"]["supports"]))

    def test_journal_sante_et_sorties(self):
        j = lire_json(self.data / "journal" / "agent-matieres-premieres.json")
        s = j["meta"]["sante"]
        self.assertEqual((s["agent"], s["workflow"]), ("matieres-premieres", "agent-matieres-premieres.yml"))
        self.assertEqual(s["planning"]["crons"], ["15 22 * * 1-5"])
        self.assertEqual(j["derniere_execution"], "2026-11-07T22:20:00Z")
        index = lire_json(self.data / "journal" / "index.json")
        self.assertIn("agent-matieres-premieres.json", [e["fichier"] for e in index["donnees"]])
        self.assertTrue((self.data / "recap" / "matieres-premieres-2026-11-07.md").exists())
        h = lire_json(self.data / "historique" / "matieres_premieres" / "2026-11-07.json")
        self.assertIn("or", h["donnees"]["notes"])
        self.assertIn("GLD", h["donnees"]["etf"])
        self.assertTrue(lire_json(self.data / "signaux" / "matieres_premieres.json")["donnees"] is not None)

    def test_ton(self):
        d = self.sortie["donnees"]
        textes = [t for m in d["matieres"] for t in m["arguments_pour"] + m["arguments_contre"] + m["invalidations"]]
        self.assertTrue(A.conformes(textes))

    def test_changement_de_verdict_signale(self):
        data2 = self.d / "data2"
        shutil.copytree(self.data, data2)
        ancien = lire_json(data2 / "matieres_premieres.json")
        cible = ancien["donnees"]["matieres"][0]
        cible["verdict"] = "Sous-pondérer" if cible["verdict"] != "Sous-pondérer" else "Surpondérer"
        ecrire_json(data2 / "matieres_premieres.json", ancien)
        args = [a if a != str(self.data) else str(data2) for a in self.args]
        args[args.index("--date") + 1] = "2026-11-09"
        self.assertEqual(main(args), 0)
        signaux = lire_json(data2 / "signaux" / "matieres_premieres.json")["donnees"]
        s = [x for x in signaux if x["type"] == "changement_verdict" and x["cle"] == cible["cle"]]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["importance"], "forte")

    def test_contradicteur_verifie_le_verdict(self):
        """Le contradicteur (agent risque) ne revoit un changement de verdict que s'il est toujours en vigueur."""
        from agents.risque.contradicteur import Sources, valide
        cfg_risque = json.loads((DOSSIER.parents[1] / "risque" / "config.json").read_text(encoding="utf-8"))
        m = self.sortie["donnees"]["matieres"][0]
        src = Sources(self.data)
        signal = {"type": "changement_verdict", "cle": m["cle"], "date": "2026-11-07", "importance": "forte",
                  "titre": f"{m['nom']} : passage de « X » à « {m['verdict']} »"}
        self.assertTrue(valide("matieres_premieres.json", signal, src, cfg_risque, "2026-11-08")[0])
        signal["titre"] = f"{m['nom']} : passage de « {m['verdict']} » à « Autre »"
        self.assertFalse(valide("matieres_premieres.json", signal, src, cfg_risque, "2026-11-08")[0])

    def test_gaz_europeen_neutre_avec_biais(self):
        """Gaz TTF (données réelles du 07/11), confiance « faible » → jamais « Surpondérer » ni « Sous-pondérer ».
        Indépendant des pondérations (que le backtest peut faire évoluer) : la note au-delà du seuil donne un biais
        positif, sinon un verdict neutre (la règle elle-même est testée avec une note fixe dans test_verdict_exige_une_confiance_suffisante)."""
        ttf = next(m for m in self.sortie["donnees"]["matieres"] if m["cle"] == "gaz_europe")
        self.assertEqual(ttf["confiance"], "faible")
        self.assertNotIn(ttf["verdict"], ("Surpondérer", "Sous-pondérer"))
        if ttf["note"] >= CFG["verdicts"]["surponderer"]:
            self.assertEqual(ttf["verdict"], "Neutre (biais positif)")
            self.assertIn("confiance « faible »", ttf["verdict_non_retenu"])
        else:
            self.assertTrue(ttf["verdict"].startswith("Neutre"))

    def test_source_en_panne(self):
        donnees = self.d / "donnees_panne"
        shutil.copytree(DOSSIER / "donnees", donnees)
        (donnees / "cftc.json").unlink()
        data3 = self.d / "data3"
        copier_donnees_test(data3, ("macro.json",))
        args = ["--test", "--donnees-test", str(donnees), "--data", str(data3), "--surveillance", str(self.surveillance), "--date", "2026-11-07"]
        self.assertEqual(main(args), 0)
        s = lire_json(data3 / "journal" / "agent-matieres-premieres.json")["meta"]["sante"]
        etats = {x["nom"]: x["etat"] for x in s["sources"]}
        self.assertEqual(etats["CFTC, Commitments of Traders (API publique Socrata)"], "échec")
        self.assertEqual(etats["EIA, stocks hebdomadaires (API v2, clé EIA_API_KEY)"], "non configurée")
        sortie = lire_json(data3 / "matieres_premieres.json")["donnees"]
        self.assertTrue(all(m["sous_notes"]["positionnement"] is None for m in sortie["matieres"]))


if __name__ == "__main__":
    unittest.main()
