"""Entretien de la méthode du chef d'orchestre et du trader : combinaisons rejugées, garde-fous, historique, écriture
des réglages, dernier rapport validé. Données synthétiques et dossiers temporaires (aucun accès aux vrais data/ ;
les configurations d'agents sont copiées avant d'être modifiées)."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from agents.backtest import entretien as EN
from agents.backtest import recalibrage as RC
from agents.backtest.tests.test_combinaisons import CFG, prix_aleatoires
from agents.commun import methode as M

RACINE = Path(__file__).resolve().parents[3]
CFG_ENT = {"fichier": "agents/chef/config.json", "classes": ["entreprises", "matieres"], "mois_consecutifs_retrait": 2,
           "ajouts_par_trimestre": 1, "prefixes_exclus": ["var3_", "var6_", "var_"]}
SELECTIONS = {"entreprises": {"combinaisons": [{"cle": "a+b", "signaux": ["a", "b"], "libelle": "A + B"},
                                               {"cle": "c+d", "signaux": ["c", "d"], "libelle": "C + D"}]},
              "matieres": {"combinaisons": [{"cle": "n+p", "signaux": ["n", "p"], "libelle": "N + P"}]}}


def verif(vi, vm=1.0):
    return {"verification": {"vs_indice_annuel_pct": vi, "vs_momentum_annuel_pct": vm}}


def service(cle, verdict, vi=-1.0):
    return {"cle": cle, "libelle": cle.upper().replace("+", " + "), "signaux": cle.split("+"), "verdict": verdict, **verif(vi)}


def candidat(cle="e+f", t=4.0):
    return {"cle": cle, "signaux": cle.split("+"), "libelle": cle.upper().replace("+", " + "), "verdict": "Prometteuse (non significative)",
            "t_apprentissage": t, "seuil_t": 3.2, **verif(2.0, 1.5)}


def scenario(retire, ajoute, vi, vm=1.0):
    return {"retire": sorted(retire), "ajoute": ajoute, **verif(vi, vm)}


def sections(ent_service, cand=None, scenarios=(), mat=None):
    s = {"entreprises": {"entretien": {"en_service": ent_service, "candidat": cand, "ecartees": [], "scenarios": list(scenarios)}}}
    s["matieres"] = {"entretien": mat or {"en_service": [service("n+p", "Prometteuse (non significative)", 1.0)], "candidat": None,
                                          "ecartees": [], "scenarios": [scenario([], None, 1.0)]}}
    return s


def historique(mois, verdicts, statut="rien à modifier", ajout=False):
    return {"mois": mois, "verdicts": {"entreprises": verdicts}, "statut": statut,
            "changements": [{"action": "ajouter", "classe": "entreprises"}] if ajout else []}


class TestDecision(unittest.TestCase):
    def test_retrait_seulement_apres_deux_mois_non_confirmee(self):
        sec = sections([service("a+b", "Non confirmée"), service("c+d", "Prometteuse (non significative)", 1.0)],
                       scenarios=[scenario([], None, 0.5), scenario(["a+b"], None, 1.0)])
        d = EN.decider(sec, [], "2027-01", SELECTIONS, CFG_ENT)
        self.assertEqual(d["modifications"], [], "un seul mois « Non confirmée » : conservée")
        self.assertTrue(any("deux mois de suite" in r for r in d["refus"]))
        d = EN.decider(sec, [historique("2026-11", {"a+b": "Non confirmée"})], "2027-01", SELECTIONS, CFG_ENT)
        self.assertEqual(d["modifications"], [], "mois précédent manquant : pas deux mois de suite")
        d = EN.decider(sec, [historique("2026-12", {"a+b": "Non confirmée"})], "2027-01", SELECTIONS, CFG_ENT)
        self.assertEqual(len(d["modifications"]), 1)
        m = d["modifications"][0]
        self.assertEqual(m["chemin"], ["selections", "entreprises", "combinaisons"])
        self.assertEqual([c["cle"] for c in m["propose"]], ["c+d"])
        self.assertEqual(m["type"], "combinaisons")
        self.assertEqual(d["changements"][0]["action"], "retirer")

    def test_aucun_changement_sans_amelioration_hors_echantillon(self):
        sec = sections([service("a+b", "Non confirmée"), service("c+d", "Prometteuse (non significative)", 1.0)],
                       scenarios=[scenario([], None, 0.5), scenario(["a+b"], None, 0.4)])
        d = EN.decider(sec, [historique("2026-12", {"a+b": "Non confirmée"})], "2027-01", SELECTIONS, CFG_ENT)
        self.assertEqual(d["modifications"], [])
        self.assertTrue(any("n'améliore pas" in r for r in d["refus"]))
        # mieux face à l'indice mais moins bien face au momentum seul : pas d'amélioration
        sec["entreprises"]["entretien"]["scenarios"] = [scenario([], None, 0.5, 1.0), scenario(["a+b"], None, 0.8, 0.2)]
        d = EN.decider(sec, [historique("2026-12", {"a+b": "Non confirmée"})], "2027-01", SELECTIONS, CFG_ENT)
        self.assertEqual(d["modifications"], [])

    def test_ajout_une_combinaison_par_trimestre(self):
        sec = sections([service("a+b", "Prometteuse (non significative)", 1.0), service("c+d", "Prometteuse (non significative)", 1.0)],
                       cand=candidat(), scenarios=[scenario([], None, 0.5), scenario([], "e+f", 0.9)])
        d = EN.decider(sec, [], "2027-02", SELECTIONS, CFG_ENT)
        self.assertEqual([c["cle"] for c in d["modifications"][0]["propose"]], ["a+b", "c+d", "e+f"])
        self.assertIn("seuil corrigé des essais", d["changements"][0]["raison"])
        # déjà un ajout proposé (en attente ou validé) dans le trimestre : reporté
        for statut in ("à valider", "validé"):
            d = EN.decider(sec, [historique("2027-01", {}, statut, ajout=True)], "2027-02", SELECTIONS, CFG_ENT)
            self.assertEqual(d["modifications"], [], statut)
            self.assertTrue(any("ce trimestre" in r for r in d["refus"]))
        # ajout refusé (non validé), ou trimestre précédent : de nouveau possible
        d = EN.decider(sec, [historique("2027-01", {}, "non validé", ajout=True)], "2027-02", SELECTIONS, CFG_ENT)
        self.assertEqual(len(d["modifications"]), 1)
        d = EN.decider(sec, [historique("2026-12", {}, "validé", ajout=True)], "2027-01", SELECTIONS, CFG_ENT)
        self.assertEqual(len(d["modifications"]), 1)
        # ajout qui n'améliore pas le panier : écarté
        sec["entreprises"]["entretien"]["scenarios"] = [scenario([], None, 0.5), scenario([], "e+f", 0.3)]
        self.assertEqual(EN.decider(sec, [], "2027-02", SELECTIONS, CFG_ENT)["modifications"], [])

    def test_une_seule_poche_recoit_l_ajout(self):
        mat = {"en_service": [service("n+p", "Prometteuse (non significative)", 1.0)], "candidat": candidat("q+r", 5.0),
               "ecartees": [], "scenarios": [scenario([], None, 1.0), scenario([], "q+r", 2.0)]}
        sec = sections([service("a+b", "Prometteuse (non significative)", 1.0)], cand=candidat("e+f", 4.0),
                       scenarios=[scenario([], None, 0.5), scenario([], "e+f", 0.9)], mat=mat)
        d = EN.decider(sec, [], "2027-02", SELECTIONS, CFG_ENT)
        self.assertEqual([m["chemin"][1] for m in d["modifications"]], ["matieres"], "meilleur t d'apprentissage d'abord, un seul ajout")

    def test_derniere_combinaison_conservee(self):
        sec = sections([service("a+b", "Non confirmée")], scenarios=[scenario([], None, -1.0)])
        sel = {"entreprises": {"combinaisons": SELECTIONS["entreprises"]["combinaisons"][:1]}, "matieres": SELECTIONS["matieres"]}
        d = EN.decider(sec, [historique("2026-12", {"a+b": "Non confirmée"})], "2027-01", sel, CFG_ENT)
        self.assertEqual(d["modifications"], [])
        self.assertTrue(any("dernière combinaison" in r for r in d["refus"]))

    def test_lot_manquant(self):
        d = EN.decider({"matieres": sections([])["matieres"]}, [], "2027-01", SELECTIONS, CFG_ENT)
        self.assertEqual(d["modifications"], [])
        self.assertTrue(any("non évaluées" in r for r in d["refus"]))


class TestLot(unittest.TestCase):
    def test_evaluation_des_combinaisons_en_service(self):
        p = prix_aleatoires(n_mois=180, n_actifs=30, graine=3)
        fut = p.pct_change().shift(-1)
        r = np.random.default_rng(1)
        bruit = lambda: pd.DataFrame(r.normal(size=p.shape), index=p.index, columns=p.columns)  # noqa: E731
        signaux = {"a": fut + 0.02 * bruit(), "b": fut + 0.02 * bruit(), "c": bruit(), "d": bruit(), "e": fut + 0.02 * bruit(), "f": fut + 0.02 * bruit()}
        combis = {"seuil_t_bonferroni": 3.0, "retenues": [
            {"signaux": ["e", "f"], "libelle": "E + F", "verdict": "Confirmée", "t_apprentissage": 6.0,
             "comparaison": {"verification": {"vs_indice_annuel_pct": 30.0, "vs_momentum_annuel_pct": 25.0}}},
            {"signaux": ["var_x", "f"], "libelle": "Var X + F", "verdict": "Confirmée", "t_apprentissage": 9.0,
             "comparaison": {"verification": {"vs_indice_annuel_pct": 30.0, "vs_momentum_annuel_pct": 25.0}}},
            {"signaux": ["a", "b"], "libelle": "déjà en service", "verdict": "Confirmée", "t_apprentissage": 9.0, "comparaison": {}}]}
        en_service = SELECTIONS["entreprises"]["combinaisons"] + [{"cle": "z+a", "signaux": ["z", "a"], "libelle": "Z + A"}]
        momentum = p.pct_change().mean(axis=1)
        e = EN.evaluer_lot(en_service, combis, signaux, p, None, momentum, 0.1, p.index[90], CFG, CFG_ENT, {})
        v = {x["cle"]: x for x in e["en_service"]}
        self.assertEqual(v["z+a"]["verdict"], "Non évaluable")
        self.assertNotEqual(v["a+b"]["verdict"], "Non confirmée", "signaux qui anticipent le mois suivant")
        self.assertEqual(v["c+d"]["verdict"], "Non confirmée", "bruit pur")
        self.assertEqual(e["candidat"]["cle"], "e+f", "variation exclue, combinaison déjà en service ignorée")
        self.assertIn("variation", e["ecartees"][0]["raisons"][0])
        cles = {(tuple(s["retire"]), s["ajoute"]) for s in e["scenarios"]}
        self.assertEqual(cles, {((), None), ((), "e+f"), (("c+d",), None), (("c+d",), "e+f")})
        sc = {(tuple(s["retire"]), s["ajoute"]): s for s in e["scenarios"]}
        self.assertTrue(EN.ameliore(sc[(("c+d",), None)], sc[((), None)]), "retirer le bruit améliore le panier")


class TestHistoriqueEtReglages(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="entretien-"))
        (self.tmp / "agents/chef").mkdir(parents=True)
        shutil.copy(RACINE / "agents/chef/config.json", self.tmp / "agents/chef/config.json")
        self.config = json.loads((self.tmp / "agents/chef/config.json").read_text(encoding="utf-8"))["selections"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proposition(self):
        actuel = self.config["entreprises"]["combinaisons"]
        propose = actuel[1:] + [{"cle": "roic+fcf_yield", "signaux": ["roic", "fcf_yield"], "libelle": "ROIC + Rendement du FCF"}]
        mod = {"agent": "chef", "fichier": "agents/chef/config.json", "chemin": ["selections", "entreprises", "combinaisons"], "type": "combinaisons",
               "actuel": actuel, "propose": propose, "retenue": True}
        changements = [{"classe": "entreprises", "action": "retirer", "cle": actuel[0]["cle"], "libelle": actuel[0]["libelle"], "raison": "« Non confirmée » deux mois de suite"},
                       {"classe": "entreprises", "action": "ajouter", "cle": "roic+fcf_yield", "libelle": "ROIC + Rendement du FCF", "raison": "passe le seuil"}]
        return {"verdicts": {}, "changements": changements, "refus": [], "modifications": [mod],
                "effets": {"entreprises": {"avant": {"vs_indice_annuel_pct": 1.0, "vs_momentum_annuel_pct": 0.5},
                                           "apres": {"vs_indice_annuel_pct": 2.0, "vs_momentum_annuel_pct": 1.0}}}}

    def test_ecriture_des_combinaisons_et_validation(self):
        d = self.proposition()
        e = EN.entree("2027-01-03", d, [], "data/backtest/rapport-2027-01.md")
        self.assertEqual(e["statut"], "à valider")
        self.assertIn("retrait de", e["texte"])
        self.assertFalse(M.appliquee(e, self.tmp))
        avant = (self.tmp / "agents/chef/config.json").read_text(encoding="utf-8")
        modifies = RC.appliquer({"propositions": d["modifications"]}, self.tmp)
        self.assertEqual(modifies, ["agents/chef/config.json"])
        apres = (self.tmp / "agents/chef/config.json").read_text(encoding="utf-8")
        cfg = json.loads(apres)
        self.assertEqual(cfg["selections"]["entreprises"]["combinaisons"], d["modifications"][0]["propose"])
        self.assertEqual(cfg["selections"]["matieres"], self.config["matieres"], "le reste du fichier est intact")
        self.assertEqual(avant.splitlines()[:100], apres.splitlines()[:100], "mise en forme conservée hors du tableau")
        self.assertTrue(M.appliquee(e, self.tmp), "pull request fusionnée : réglages en service")
        # statuts : validé dès que les réglages sont en service ; sinon « non validé » une fois le mois passé
        h = [dict(e)]
        EN.mettre_a_jour_statuts(h, self.tmp, "2027-01-20")
        self.assertEqual((h[0]["statut"], h[0]["valide_le"]), ("validé", "2027-01-20"))

    def test_non_valide_et_dernier_rapport_valide(self):
        data = self.tmp / "data"
        base = {"mois": "2026-11", "rapport": "data/backtest/rapport-2026-11.md", "statut": "validé", "modifications": []}
        e = EN.entree("2027-01-03", self.proposition(), [], "data/backtest/rapport-2027-01.md")
        h = EN.enregistrer([base], e)
        self.assertTrue(EN.noter_pull_request(h, "2027-01", "https://github.com/jcn1996/Plateforme-eco/pull/70"))
        (data / "backtest").mkdir(parents=True)
        (data / "backtest/recalibrages.json").write_text(json.dumps({"meta": {}, "donnees": {"historique": h}}), encoding="utf-8")
        self.assertEqual(M.rapport_valide(data, self.tmp), "data/backtest/rapport-2026-11.md", "proposition pas encore fusionnée")
        RC.appliquer({"propositions": self.proposition()["modifications"]}, self.tmp)
        self.assertEqual(M.rapport_valide(data, self.tmp), "data/backtest/rapport-2027-01.md", "fusionnée : nouveau rapport de référence")
        self.assertIsNone(M.rapport_valide(self.tmp / "vide", self.tmp))
        # même mois relancé, même proposition : le lien de pull request est gardé
        h2 = EN.enregistrer(h, EN.entree("2027-01-04", self.proposition(), [], "data/backtest/rapport-2027-01.md"))
        self.assertEqual(h2[-1]["pull_request"], "https://github.com/jcn1996/Plateforme-eco/pull/70")
        self.assertEqual(len(h2), 2)
        # mois suivant sans fusion : non validé
        h3 = [dict(x) for x in h]
        shutil.copy(RACINE / "agents/chef/config.json", self.tmp / "agents/chef/config.json")
        EN.mettre_a_jour_statuts(h3, self.tmp, "2027-02-03")
        self.assertEqual(h3[-1]["statut"], "non validé")

    def test_rien_a_modifier(self):
        e = EN.entree("2027-01-03", {"verdicts": {}, "changements": [], "refus": [], "modifications": [], "effets": {}}, [], "r.md")
        self.assertEqual((e["statut"], e["texte"]), ("rien à modifier", "Recalibrage du mois : rien à modifier"))
        self.assertFalse(EN.noter_pull_request([e], "2027-01", "url"))

    def test_corps_de_la_pull_request(self):
        d = self.proposition()
        pond = [{"agent": "entreprises", "fichier": "agents/entreprises/config.json", "chemin": ["ponderations"], "propose": {"roic": 2}, "raison": "hors échantillon, IC +0,01 → +0,02"}]
        e = EN.entree("2027-01-03", d, pond, "r.md")
        corps = EN.corps_pull_request({"jour": "2027-01-03", "recalibrage": {k: e[k] for k in ("changements", "effets")}})
        lignes = corps.strip().splitlines()
        self.assertLessEqual(len(lignes), 10)
        texte = "\n".join(lignes)
        for mot in ("Ce qui change", "Pourquoi", "Effet attendu", "Limites", "agent entreprises", "retrait de"):
            self.assertIn(mot, texte)


if __name__ == "__main__":
    unittest.main()
