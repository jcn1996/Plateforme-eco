"""
Tests des flux d'investissement des ETF pays (sans réseau) : python -m unittest discover -s agents/pays -t .
Tout est écrit dans des dossiers temporaires : les vrais config/ et data/ ne sont ni lus ni modifiés
(sauf agents/pays/config.json, la configuration de l'agent, en lecture seule).
"""
import json
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from agents.commun.sortie import lire_json
from agents.pays import flux_etf, notation, textes
from agents.pays.agent import main
from agents.pays.sources_flux import lire_globalx, lire_ishares, lire_ssga, lire_vaneck

ICI = Path(__file__).resolve().parent
DONNEES = ICI / "donnees"
PAGES = DONNEES / "pages"
CONFIG = json.loads((ICI.parent / "config.json").read_text(encoding="utf-8"))["flux_etf"]
RACINE = ICI.parents[2]


def serie(depart: date, parts: list[float], vl: float = 10.0) -> list[dict]:
    """Relevés de jours ouvrés consécutifs à partir de « depart »."""
    res, d = [], depart
    for p in parts:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        res.append({"date": d.isoformat(), "parts": float(p), "vl": vl, "encours": p * vl, "source": "ishares"})
        d += timedelta(days=1)
    return res


class TestLecture(unittest.TestCase):
    """Extraits des vraies réponses des émetteurs (novembre 2026)."""

    def test_ishares(self):
        r = lire_ishares((PAGES / "ishares_EWJ.html").read_text(encoding="utf-8"))
        self.assertEqual(r["date"], "2026-11-05")
        self.assertEqual(r["parts"], 254_250_000)
        self.assertAlmostEqual(r["vl"], 88.430198)
        self.assertAlmostEqual(r["parts"] * r["vl"] / r["encours"], 1, places=3)   # cohérent avec l'actif net publié

    def test_globalx(self):
        r = lire_globalx((PAGES / "globalx_ARGT.html").read_text(encoding="utf-8"))
        self.assertEqual((r["date"], r["parts"], r["vl"]), ("2026-11-05", 7_634_975, 74.14))
        self.assertAlmostEqual(r["encours"], 566.04e6)

    def test_ssga_et_vaneck(self):
        r = lire_ssga((PAGES / "ssga_SPY.xlsx").read_bytes())
        self.assertEqual(r["date"], "2026-11-05")
        self.assertEqual(r["parts"], 1_060_932_116)
        self.assertEqual(r["historique"][-1][0], "2026-11-05")                       # plus récent en dernier
        self.assertLess(r["historique"][0][0], r["historique"][-1][0])
        v = lire_vaneck((PAGES / "vaneck_VNM.xlsx").read_bytes())
        self.assertEqual(v["date"], "2026-11-05")
        self.assertEqual(v["parts"] % 1000, 0)                                       # parts déduites, arrondies au millier
        self.assertAlmostEqual(v["parts"] * v["vl"] / v["encours"], 1, places=3)
        dates = [x[0] for x in v["historique"]]
        self.assertNotIn("2026-11-01", dates)                                        # dimanche recopié de la veille : écarté

    def test_page_sans_donnees(self):
        with self.assertRaises(ValueError):
            lire_ishares("<html>maintenance</html>")
        with self.assertRaises(ValueError):
            lire_globalx("<html></html>")


class TestCalculs(unittest.TestCase):
    def test_flux_du_jour(self):
        a = {"parts": 1_000_000, "vl": 50}
        self.assertEqual(flux_etf.flux_du_jour(a, {"parts": 1_100_000, "vl": 51}), 100_000 * 51)   # Δparts × VL du jour
        self.assertEqual(flux_etf.flux_du_jour(a, {"parts": 2_000_000, "vl": 25}), 0.0)            # division des parts
        self.assertIsNone(flux_etf.flux_du_jour(a, {"parts": 3_000_000, "vl": 50}))                # variation aberrante
        self.assertIsNone(flux_etf.flux_du_jour(None, a))

    def test_periodes_et_constitution(self):
        s = serie(date(2026, 10, 8), [1e6 + 1e4 * i for i in range(17)])            # 17 jours ouvrés : du 08/10 au 30/10
        ind = flux_etf.indicateur("EWJ", "ishares", None, s, CONFIG, date(2026, 11, 2))
        p = ind["periodes"]
        self.assertTrue(p["1s"]["complet"])
        self.assertFalse(p["1m"]["complet"])
        self.assertEqual(p["1m"]["statut"], "en cours de constitution")
        self.assertFalse(p["3m"]["complet"])
        self.assertEqual(ind["periode_valeur"], "1s")                     # le mois n'est pas complet : 1 semaine
        self.assertAlmostEqual(p["1s"]["flux_musd"], 0.5)                  # 5 jours × 10 000 parts × 10 $
        self.assertEqual(ind["serie_consecutive"], {"sens": "entrées", "jours": 16, "depuis": s[1]["date"]})
        self.assertEqual(ind["tendance_flux"], "entrées nettes")
        self.assertIn(AVERTISSEMENT_US, ind["avertissement"])
        self.assertEqual(ind["cumul"][-1][1], 1.6)
        self.assertEqual(ind["cumul"][0], [s[0]["date"], 0.0])            # la courbe part de zéro

    def test_un_seul_releve(self):
        ind = flux_etf.indicateur("EWJ", "ishares", None, serie(date(2026, 10, 30), [100]), CONFIG, date(2026, 11, 2))
        self.assertIsNone(ind["valeur"])
        self.assertIn("en cours de constitution", ind["raison"])
        self.assertTrue(all(p["statut"] == "en cours de constitution" for p in ind["periodes"].values()))

    def test_sans_etf(self):
        ind = flux_etf.indicateur(None, None, None, [], CONFIG, date(2026, 11, 2))
        self.assertIsNone(ind["valeur"])
        self.assertIn("aucun ETF", ind["raison"])

    def test_releve_trop_ancien(self):
        ind = flux_etf.indicateur("EWJ", "ishares", None, serie(date(2026, 9, 1), [100] * 10), CONFIG, date(2026, 11, 2))
        self.assertIsNone(ind["valeur"])
        self.assertIn("trop ancien", ind["raison"])

    def test_note_et_encombrement(self):
        self.assertEqual(notation.note_flux(0), 50)
        self.assertEqual(notation.note_flux(5, "1m"), 80)
        self.assertEqual(notation.note_flux(-5, "1m"), 20)
        self.assertEqual(notation.note_flux(2.5, "1s"), 80)
        # 60 jours calmes, puis une semaine d'entrées de 8 % de l'encours
        calmes = [1_000_000 + (i % 2) * 1000 for i in range(60)]
        forte = [calmes[-1] * (1 + 0.016 * k) for k in range(1, 6)]
        s = serie(date(2026, 8, 3), calmes + forte)
        fin = date.fromisoformat(s[-1]["date"])
        ind = flux_etf.indicateur("EWJ", "ishares", None, s, CONFIG, fin)
        self.assertTrue(ind["encombrement"]["signale"])
        self.assertIn("Position possiblement encombrée", ind["encombrement"]["texte"])
        self.assertLessEqual(flux_etf.noter(ind, CONFIG), CONFIG["encombrement"]["plafond_note"])
        self.assertTrue(textes.ton_conforme(ind["encombrement"]["texte"]))
        # Des sorties ne sont jamais « encombrées »
        baisse = serie(date(2026, 8, 3), calmes + [calmes[-1] * (1 - 0.016 * k) for k in range(1, 6)])
        self.assertNotIn("encombrement", flux_etf.indicateur("EWJ", "ishares", None, baisse, CONFIG, fin))


AVERTISSEMENT_US = "cotés aux États-Unis uniquement"


class TestVerificationCroisee(unittest.TestCase):
    def releve(self, parts, d="2026-10-30", encours=None):
        return {"date": d, "parts": parts, "vl": 10.0, "encours": encours}

    def test_concorde_diverge_secours(self):
        src = {"flux_ishares": {"EWJ": self.releve(1000)}, "flux_yahoo_parts": {"EWJ": self.releve(1010)}}
        c = flux_etf.choisir_releve("EWJ", "ishares", src, CONFIG, date(2026, 11, 2))
        self.assertEqual((c["retenu"]["source"], c["verification"]), ("ishares", "concordant"))
        src["flux_yahoo_parts"]["EWJ"] = self.releve(1100)
        c = flux_etf.choisir_releve("EWJ", "ishares", src, CONFIG, date(2026, 11, 2))
        self.assertEqual(c["verification"], "divergent")
        self.assertEqual(c["retenu"]["source"], "ishares")                    # l'émetteur reste prioritaire
        # Émetteur en panne : Yahoo Finance en secours
        c = flux_etf.choisir_releve("EWJ", "ishares", {"flux_ishares": None, "flux_yahoo_parts": src["flux_yahoo_parts"]}, CONFIG, date(2026, 11, 2))
        self.assertEqual((c["retenu"]["source"], c["verification"]), ("yahoo_parts", "source_unique"))
        self.assertEqual(c["sources"][0]["statut"], "échec")

    def test_rejets(self):
        src = {"flux_ishares": {"EWJ": self.releve(1000, encours=20_000)},           # parts × VL ≠ actif net publié
               "flux_yahoo_parts": {"EWJ": self.releve(1000, d="2026-10-01")}}       # trop ancien
        c = flux_etf.choisir_releve("EWJ", "ishares", src, CONFIG, date(2026, 11, 2))
        self.assertIsNone(c["retenu"])
        self.assertEqual([s["statut"] for s in c["sources"]], ["rejetée", "rejetée"])
        self.assertTrue(c["sources"][1]["raison"].startswith("trop ancienne"))


class TestSignaux(unittest.TestCase):
    def test_inversion(self):
        parts = [1000 - 3 * i for i in range(20)] + [943 + 4 * i for i in range(1, 6)]   # 4 semaines de sorties puis entrées
        s = serie(date(2026, 9, 28), [p * 1000 for p in parts])
        fin = date.fromisoformat(s[-1]["date"])
        types = {x["type"] for x in flux_etf.signaux("JP", "Japon", "EWJ", s, CONFIG, fin)}
        self.assertIn("inversion_flux", types)

    def test_flux_inhabituel(self):
        parts = [1_000_000 + (i % 2) * 500 for i in range(30)] + [1_060_000]                # +6 % en un jour
        s = serie(date(2026, 9, 21), parts)
        fin = date.fromisoformat(s[-1]["date"])
        sig = flux_etf.signaux("JP", "Japon", "EWJ", s, CONFIG, fin)
        x = next(x for x in sig if x["type"] == "entrees_inhabituelles")
        self.assertEqual((x["cle"], x["date"], x["importance"]), ("JP", s[-1]["date"], "forte"))
        self.assertIn("cotés aux États-Unis", x["explication"])
        self.assertTrue(textes.ton_conforme(x["titre"] + " " + x["explication"]))
        # Calme : aucun signal
        self.assertEqual(flux_etf.signaux("JP", "Japon", "EWJ", s[:-1], CONFIG, fin), [])

    def test_ecriture_sans_doublon(self):
        d = Path(tempfile.mkdtemp())
        try:
            s = {"date": "2026-11-02", "type": "inversion_flux", "cle": "JP", "importance": "moyenne", "titre": "t", "explication": "e", "source": "x"}
            self.assertTrue(flux_etf.ecrire_signaux(d / "pays.json", [s], date(2026, 11, 2), "1.2"))
            self.assertFalse(flux_etf.ecrire_signaux(d / "pays.json", [s], date(2026, 11, 2), "1.2"))
            self.assertEqual(len(lire_json(d / "pays.json")["donnees"]), 1)
        finally:
            shutil.rmtree(d)


class TestHistorique(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_aller_retour(self):
        h = {}
        r1 = {"date": "2026-10-29", "parts": 1e6, "vl": 10.0, "encours": 1e7, "source": "ishares"}
        r2 = {"date": "2026-10-30", "parts": 1.1e6, "vl": 10.0, "encours": 1.1e7, "source": "ishares"}
        m = set(flux_etf.completer_historique(h, "EWJ", r1, "concordant", 100, date(2026, 11, 2)))
        m |= set(flux_etf.completer_historique(h, "EWJ", r2, "source_unique", 100, date(2026, 11, 2)))
        flux_etf.ecrire_historique(self.d, h, m, "2026-11-02T00:00:00Z", "1.2")
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["2026-10-29.json", "2026-10-30.json"])
        self.assertEqual(lire_json(self.d / "2026-10-30.json")["donnees"]["EWJ"]["flux_musd"], 1.0)   # 100 000 parts × 10 $
        relu = flux_etf.lire_historique(self.d, date(2026, 11, 2), 400)
        self.assertEqual([r["parts"] for r in relu["EWJ"]], [1e6, 1.1e6])
        # Même relevé : rien à réécrire
        self.assertEqual(flux_etf.completer_historique(relu, "EWJ", r2, "source_unique", 100, date(2026, 11, 2)), [])


class TestAgentFlux(unittest.TestCase):
    """Agent complet puis mode « flux » du soir, dans un dossier temporaire."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.reel = {p: (p.stat().st_mtime if p.exists() else None)
                     for p in (RACINE / "data" / "pays.json", RACINE / "data" / "signaux" / "pays.json")}

    def tearDown(self):
        shutil.rmtree(self.d)

    def lancer(self, donnees, jour, *autres):
        return main(["--test", "--donnees-test", str(donnees), "--sortie", str(self.d / "pays.json"),
                     "--historique", str(self.d / "historique" / "pays"), "--journal", str(self.d / "journal" / "agent-pays.json"),
                     "--recap", str(self.d / "recap"), "--date", jour, *autres])

    def test_complet_puis_flux(self):
        self.assertEqual(self.lancer(DONNEES, "2026-11-02"), 0)
        f = lire_json(self.d / "pays.json")
        par = {p["code"]: p for p in f["donnees"]}
        us = par["US"]["detail"]["flux_etrangers"]
        self.assertEqual((us["symbole"], us["periode_valeur"], us["verification"]), ("SPY", "1m", "concordant"))
        self.assertIsNotNone(us["note"])
        self.assertTrue(all(us["periodes"][k]["complet"] for k in ("1s", "1m", "3m")))   # historique publié par SSGA
        self.assertIn("cotés aux États-Unis", us["avertissement"])
        jp = par["JP"]["detail"]["flux_etrangers"]
        self.assertIsNone(jp["valeur"])                                                  # premier relevé iShares
        self.assertEqual(jp["periodes"]["1m"]["statut"], "en cours de constitution")
        self.assertIn("aucun ETF", par["EG"]["detail"]["flux_etrangers"]["raison"])
        self.assertTrue((self.d / "historique" / "flux_etf" / "2026-10-30.json").exists())
        self.assertIn("flux_ishares", f["meta"]["etat_des_sources"])

        # Soir : nouveau relevé iShares (+1 % de parts pour le Japon) → mode « flux »
        modif = self.d / "donnees"
        shutil.copytree(DONNEES, modif)
        ish = json.loads((modif / "flux_ishares.json").read_text(encoding="utf-8"))
        ish["EWJ"] = {**ish["EWJ"], "date": "2026-11-02", "parts": ish["EWJ"]["parts"] * 1.01,
                      "encours": ish["EWJ"]["parts"] * 1.01 * ish["EWJ"]["vl"]}
        (modif / "flux_ishares.json").write_text(json.dumps(ish), encoding="utf-8")
        avant = lire_json(self.d / "pays.json")
        self.assertEqual(self.lancer(modif, "2026-11-02", "--mode", "flux"), 0)
        apres = lire_json(self.d / "pays.json")
        jp2 = next(p for p in apres["donnees"] if p["code"] == "JP")
        self.assertEqual(jp2["detail"]["flux_etrangers"]["releves"], 2)
        self.assertGreater(jp2["detail"]["flux_etrangers"]["periodes"]["1s"]["flux_musd"], 0)
        # Le reste de la fiche n'a pas bougé
        jp1 = next(p for p in avant["donnees"] if p["code"] == "JP")
        self.assertEqual(jp1["indicateurs"], jp2["indicateurs"])
        self.assertEqual(jp1["note"], jp2["note"])
        self.assertEqual(avant["meta"]["genere_le"], apres["meta"]["genere_le"])
        self.assertIn("bis", apres["meta"]["etat_des_sources"])                          # états du matin conservés
        sante = lire_json(self.d / "journal" / "agent-pays.json")["meta"]["sante"]
        self.assertIn("flux_ishares", {s["nom"] for s in sante["sources"]})
        self.assertIn("bis", {s["nom"] for s in sante["sources"]})
        self.assertTrue((self.d / "historique" / "flux_etf" / "2026-11-02.json").exists())
        self.assertTrue((self.d / "signaux" / "pays.json").exists())

    def test_isolation_des_vrais_fichiers(self):
        self.lancer(DONNEES, "2026-11-02")
        for chemin, mtime in self.reel.items():
            self.assertEqual(chemin.stat().st_mtime if chemin.exists() else None, mtime, chemin)


if __name__ == "__main__":
    unittest.main()
