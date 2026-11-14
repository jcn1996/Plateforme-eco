"""
Backtest des règles de notation (méthode : agents/backtest/methode.md).

    python -m agents.backtest                         # tous les lots puis le rapport (vraies sources)
    python -m agents.backtest --lot pays              # un lot (pays, entreprises, matieres, secteurs, tendance)
    python -m agents.backtest --lot sec --tranche 0/4 # téléchargement SEC d'une tranche (workflow, en parallèle)
    python -m agents.backtest --lot rapport           # assemble les lots déjà calculés
    python -m agents.backtest --test --sortie /tmp/bt # données synthétiques, sans réseau
    python -m agents.backtest --appliquer-proposition data/backtest/proposition-2026-11.json

Résultats : data/backtest/resultats.json (écran « Backtest »), data/backtest/rapport-AAAA-MM.md,
data/backtest/proposition-AAAA-MM.json. Aucun réglage d'un autre agent n'est modifié, sauf par
--appliquer-proposition, utilisé seulement pour préparer la pull request séparée de proposition.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from . import donnees as D
from . import entreprises as E
from . import matieres as MT
from . import pays as P
from . import combinaisons as CB
from . import recalibrage as RC
from . import reference as RF
from . import regles as R
from . import secteurs as SC
from . import stats as S
from . import tendance as T

LOG = journal("backtest")
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
LOTS = ("pays", "entreprises", "matieres", "secteurs", "tendance")

LIBELLES = {
    # pays
    "croissance_pib": "Croissance du PIB", "indicateur_avance": "Indicateur avancé (OCDE)", "inflation": "Inflation",
    "taux_reel": "Taux réel", "valorisation": "Valorisation relative", "momentum": "Momentum 12 mois", "devise_3m": "Devise sur 3 mois",
    "note_globale": "Note globale actuelle", "note_globale_brute": "Note globale sans règle de prudence",
    "note_recalibree": "Note recalibrée",
    # chef
    "score_chef": "Score du chef d'orchestre", "famille_fondamentaux": "Famille Fondamentaux", "famille_valorisation": "Famille Valorisation",
    "famille_tendance": "Famille Tendance", "famille_cycle": "Famille Cycle", "equipondere": "Familles équipondérées",
    "score_recalibre": "Score recalibré",
    # entreprises
    "croissance_ca": "Croissance du CA", "croissance_benefice": "Croissance du bénéfice", "marge_op": "Marge opérationnelle",
    "conversion_cash": "Conversion du bénéfice en cash", "dette_ebitda": "Dette nette / EBITDA", "couverture_interets": "Couverture des intérêts",
    "roic": "ROIC", "per_secteur": "PER relatif au secteur", "ev_ebitda_secteur": "VE/EBITDA relatif au secteur",
    "momentum_12m": "Momentum 12 mois", "fscore": "F-score de Piotroski", "fcf_yield": "Rendement du FCF",
    "benefices_normalises": "Bénéfices normalisés", "roic_wacc": "ROIC − coût du capital", "regularite": "Régularité",
    "rendement_actionnaire": "Rendement pour l'actionnaire", "altman_z": "Z-score d'Altman", "mscore": "M-score de Beneish",
    "goodwill_actif": "Goodwill / actif", "current_ratio": "Current ratio", "marge_brute": "Marge brute", "cycle_cash": "Cycle de conversion du cash",
    "capex_amortissements": "Capex / amortissements", "intensite_rd": "Intensité en R&D", "evolution_actions": "Évolution du nombre d'actions",
    # matières, secteurs
    "tendance": "Tendance", "courbe": "Structure de la courbe (portage)", "stocks": "Stocks EIA", "positionnement": "Positionnement CFTC",
    "niveau": "Niveau historique", "cycle": "Phase du cycle (rotation)",
}
TITRES = {"pays": "Pays", "entreprises": "Entreprises américaines", "matieres": "Matières premières", "secteurs": "Secteurs (États-Unis)",
          "chef": "Chef d'orchestre (pays)", "tendance": "Suivi de tendance (ETF pays, secteurs, matières)"}


def lire_configs(racine: Path) -> dict:
    c = {}
    for nom, chemin in {"bt": DOSSIER / "config.json", "pays": racine / "agents/pays/config.json", "chef": racine / "agents/chef/config.json",
                        "macro": racine / "agents/macro/config.json", "trader": racine / "agents/trader/config.json",
                        "entreprises": racine / "agents/entreprises/config.json", "mp": racine / "agents/matieres_premieres/config.json"}.items():
        c[nom] = json.loads(Path(chemin).read_text(encoding="utf-8"))
    return c


# ------------------------------------------------------------------ analyse commune

def separation_du_lot(note: pd.DataFrame, cfg: dict) -> pd.Timestamp | None:
    if cfg["periode"].get("separation"):
        return pd.Timestamp(cfg["periode"]["separation"])
    ok = note.index[note.notna().sum(axis=1) >= cfg["verdicts"]["actifs_min"]]
    return ok[len(ok) // 2] if len(ok) else None


def analyser(signaux: dict[str, pd.DataFrame], lot: dict, nom: str, cfg: dict, regimes, separation) -> dict:
    h_ref = cfg["horizon_reference"][nom if nom in cfg["horizon_reference"] else "pays"]
    frais = cfg["frais"].get(nom, cfg["frais"]["pays"])
    res = {}
    for k, sig in signaux.items():
        if sig is None or not sig.notna().any().any():
            continue
        res[k] = S.analyser_signal(sig, lot["prix"], lot.get("indice"), cfg["horizons_mois"], h_ref, cfg["quantile"], frais,
                                   regimes, separation, cfg["verdicts"])
        res[k]["libelle"] = libelle(k)
        ref = lot.get("reference")
        if ref is not None:  # panier des meilleurs 20 % comparé à l'indice et au momentum seul
            r = RF.rendement_signal(sig, lot["prix"], ref["indice_serie"], cfg["quantile"], frais)
            res[k]["portefeuille"] = RF.comparer(r, ref["indice_serie"], ref["serie"], separation)
    return res


def libelle(k: str) -> str:
    """Libellé d'un signal, y compris les variations (var3_inflation → « Inflation — variation 3 mois »)."""
    if k in LIBELLES:
        return LIBELLES[k]
    if k in E.VARIATIONS:
        return E.VARIATIONS[k]
    if k.startswith("var") and "_" in k:
        mois, base = k[3:].split("_", 1)
        if mois.isdigit():
            return f"{LIBELLES.get(base, base)} — variation {mois} mois"
    return k


def avec_reference(lot: dict, nom: str, cfg: dict, sep, masque=None) -> dict:
    """Ajoute au lot la référence « momentum seul » (meilleurs 20 % sur 12 mois hors dernier mois, frais compris)."""
    lot["reference"] = RF.reference_momentum(lot["prix"], lot.get("indice"), cfg["quantile"], cfg["frais"][nom], sep, masque)
    return lot["reference"]["resume"]


def combiner_signaux(signaux: dict, res: dict, lot: dict, nom: str, cfg: dict, sep) -> dict:
    return CB.tester(signaux, res, lot["prix"], lot.get("indice"), lot["reference"]["serie"], cfg["frais"][nom], sep,
                     cfg["combinaisons"], {k: v.get("libelle", k) for k, v in res.items()})


def _periode(lot: dict) -> dict:
    p = lot["prix"].dropna(how="all")
    return {"debut": p.index[0].strftime("%Y-%m") if len(p) else None, "fin": p.index[-1].strftime("%Y-%m") if len(p) else None,
            "actifs": int(p.notna().any().sum())}


def _resume_note(r: dict) -> dict:
    v = r["echantillons"]["verification"]
    return {"ic_verification": v["ic_moyen"], "t_verification": v["ic_t"], "ecart_net_verification_pct": v.get("ecart_net_annuel_pct"),
            "ic_apprentissage": r["echantillons"]["apprentissage"]["ic_moyen"], "verdict": r["verdict"]}


def proposer(agent: str, fichier: str, chemin: list[str], poids: dict, resultats: dict, cfg: dict, combiner, lot: dict, nom: str,
             regimes, separation, decimales: int = 3, note_actuelle=None) -> tuple[dict, dict, dict]:
    """Recalibre `poids` sur l'apprentissage, compare la note recalibrée à l'actuelle hors échantillon."""
    nouveaux, detail = RC.recalibrer(resultats, poids, cfg["recalibrage"], decimales)
    actuelle = note_actuelle if note_actuelle is not None else combiner(poids)
    r = analyser({"actuelle": actuelle, "recalibree": combiner(nouveaux)}, lot, nom, cfg, regimes, separation)
    if "actuelle" not in r or "recalibree" not in r:
        return {"agent": agent, "fichier": fichier, "chemin": chemin, "actuel": poids, "propose": poids, "retenue": False,
                "raison": "note non calculable"}, {}, {}
    retenue, raison = RC.meilleure(r["actuelle"], r["recalibree"])
    retenue = retenue and nouveaux != poids
    return ({"agent": agent, "fichier": fichier, "chemin": chemin, "actuel": poids, "propose": nouveaux, "retenue": retenue,
             "raison": raison, "detail": detail, "note_actuelle": _resume_note(r["actuelle"]),
             "note_recalibree": _resume_note(r["recalibree"])}, r["actuelle"], r["recalibree"])


# ------------------------------------------------------------------ lots

def lot_pays(f, c: dict, racine: Path, test: bool, regimes) -> dict:
    cfg = c["bt"]
    debut = cfg["periode"]["debut"]
    pays_cfg = f.pays_test() if test else c["pays"]["pays"]
    indices = {} if test else (lire_json(racine / "config/indices_pays.json") or {}).get("pays", {})
    poids = {k: v for k, v in c["pays"]["ponderations"].items() if not k.startswith("_")}
    lot = P.construire(f, pays_cfg, indices, poids, cfg, debut)
    sep = separation_du_lot(lot["note_globale"], cfg)
    ref = avec_reference(lot, "pays", cfg, sep)
    var = P.variations(lot, cfg["variations"]["mois"])
    signaux = dict(lot["notes"]) | var | {"note_globale": lot["note_globale"], "note_globale_brute": lot["note_globale_brute"]}
    res = analyser(signaux, lot, "pays", cfg, regimes, sep)
    combis = combiner_signaux(dict(lot["notes"]) | var, res, lot, "pays", cfg, sep)
    poids_testes = {k: v for k, v in poids.items() if k in lot["notes"]}
    poids_fixes = {k: v for k, v in poids.items() if k not in poids_testes}

    def combiner(p):
        return P._notes_globales(lot["notes"], p | poids_fixes, lot["prix"].columns, lot["mois"])[0]
    prop_pays, _, recal = proposer("pays", "agents/pays/config.json", ["ponderations"], poids_testes, res, cfg, combiner, lot, "pays",
                                   regimes, sep, 3, note_actuelle=lot["note_globale"])
    prop_pays["propose"] = prop_pays["propose"] | poids_fixes
    prop_pays["actuel"] = poids
    if recal:
        res["note_recalibree"] = recal | {"libelle": LIBELLES["note_recalibree"]}

    # Chef d'orchestre : rejoué sur les pays
    chef = R.rejouer_chef(lot, c["chef"], c["macro"], regimes)
    fam = chef["familles"]
    sig_chef = {"score_chef": chef["score"]} | {f"famille_{k}": v for k, v in fam.items()}
    sig_chef["equipondere"] = S.note_ponderee(fam, {k: 1 for k in fam})
    res_chef = analyser(sig_chef, lot, "chef", cfg, regimes, sep)
    poids_chef = {k: v for k, v in c["chef"]["poids"]["pays"].items() if k in R.FAMILLES_RECONSTITUEES}
    res_fam = {k.replace("famille_", ""): v for k, v in res_chef.items() if k.startswith("famille_")}
    prop_chef, _, recal_chef = proposer("chef", "agents/chef/config.json", ["poids", "pays"], poids_chef, res_fam, cfg,
                                        lambda p: R.score_avec_poids(fam, chef["paliers"], c["chef"], p), lot, "chef", regimes, sep, 0,
                                        note_actuelle=chef["score"])
    prop_chef["propose"] = c["chef"]["poids"]["pays"] | prop_chef["propose"]
    prop_chef["actuel"] = c["chef"]["poids"]["pays"]
    if recal_chef:
        res_chef["score_recalibre"] = recal_chef | {"libelle": LIBELLES["score_recalibre"]}
    horizons = cfg["horizons_mois"]
    regles = {
        "verdicts": R.tester_verdicts(chef, lot["prix"], lot["indice"], horizons, c["chef"], sep),
        "tendance": R.tester_tendance(chef, lot["prix"], lot["indice"], horizons, c["chef"]),
        "concentration": R.tester_concentration(chef, lot["prix"], lot["indice"], c["trader"], cfg["regles"]["concentration_lignes"],
                                                cfg["frais"]["pays"], sep),
        "horizon_reference": cfg["horizon_reference"]["chef"],
    }
    return {"pays": {"titre": TITRES["pays"], "periode": _periode(lot), "separation": _iso(sep), "signaux": res,
                     "horizon_reference": cfg["horizon_reference"]["pays"], "indice": cfg["pays"]["indice_reference"],
                     "biais_survivant": {"univers_complet_vs_indice_pct": E.exces_univers(lot["prix"], lot["indice"], None)},
                     "reference_momentum": ref, "combinaisons": combis},
            "chef": {"titre": TITRES["chef"], "periode": _periode(lot), "separation": _iso(sep), "signaux": res_chef, "regles": regles,
                     "reference_momentum": ref,
                     "horizon_reference": cfg["horizon_reference"]["chef"], "indice": cfg["pays"]["indice_reference"]},
            "_propositions": [prop_pays, prop_chef]}


def _societes(f, racine: Path, test: bool) -> list[dict]:
    if test:
        return f.societes_test()
    u = lire_json(racine / "data/entreprises/univers.json") or {}
    return [{"ticker": s["ticker"], "pays": s.get("pays"), "secteur": s.get("secteur"), "nom": s.get("nom")} for s in u.get("societes", [])]


def lot_entreprises(f, c: dict, racine: Path, test: bool, regimes) -> dict | None:
    cfg = c["bt"]
    lot = E.construire(f, _societes(f, racine, test), c["entreprises"], cfg, cfg["periode"]["debut"])
    if not lot:
        return None
    sep = separation_du_lot(lot["note_globale"], cfg)
    ref = avec_reference(lot, "entreprises", cfg, sep, lot.get("retenues"))
    var = lot.get("variations") or {}
    signaux = dict(lot["notes"]) | var | {"note_globale": lot["note_globale"], "note_globale_brute": lot["note_globale_brute"]}
    res = analyser(signaux, lot, "entreprises", cfg, regimes, sep)
    combis = combiner_signaux(dict(lot["notes"]) | var, res, lot, "entreprises", cfg, sep)
    from ..entreprises import analyse as A
    poids = {k: v for k, v in c["entreprises"]["ponderations"].items() if not k.startswith("_")}
    couverture = c["entreprises"]["analyse_financiere"].get("couverture_sur")
    arr = {k: v.to_numpy(dtype=float) for k, v in lot["notes"].items()}

    def combiner(p):
        out = np.full(lot["note_globale"].shape, np.nan)
        for i in range(out.shape[0]):
            for j in range(out.shape[1]):
                n = {k: a[i, j] for k, a in arr.items() if not np.isnan(a[i, j])}
                if n:
                    out[i, j] = A.note_globale(n, p, couverture)["note"] or np.nan
        return pd.DataFrame(out, index=lot["note_globale"].index, columns=lot["note_globale"].columns)
    prop, _, recal = proposer("entreprises", "agents/entreprises/config.json", ["ponderations"], poids, res, cfg, combiner, lot,
                              "entreprises", regimes, sep, 3, note_actuelle=lot["note_globale"])
    if recal:
        res["note_recalibree"] = recal | {"libelle": LIBELLES["note_recalibree"]}
    st = R.tester_stops(lot["note_globale"], lot["quotidien"], c["trader"], cfg["regles"]["stops_lignes"], cfg["regles"]["stops_detention_mois"],
                        cfg["frais"]["entreprises"], sep)
    return {"entreprises": {"titre": TITRES["entreprises"], "periode": _periode(lot), "separation": _iso(sep), "signaux": res,
                            "horizon_reference": cfg["horizon_reference"]["entreprises"], "indice": cfg["entreprises"]["indice_reference"],
                            "regles": {"stops": st}, "biais_survivant": lot.get("biais_survivant"),
                            "reference_momentum": ref, "combinaisons": combis},
            "_propositions": [prop]}


def lot_matieres(f, c: dict, racine: Path, test: bool, regimes) -> dict:
    cfg = c["bt"]
    lot = MT.construire(f, c["mp"], cfg, cfg["periode"]["debut"])
    sep = separation_du_lot(lot["note_globale"], cfg)
    ref = avec_reference(lot, "matieres", cfg, sep)
    var = lot.get("variations") or {}
    res = analyser(dict(lot["notes"]) | var | {"note_globale": lot["note_globale"]}, lot, "matieres", cfg, regimes, sep)
    combis = combiner_signaux(dict(lot["notes"]) | var, res, lot, "matieres", cfg, sep)
    familles = {m["cle"]: m["famille"] for m in c["mp"]["matieres"]}
    from ..matieres_premieres import analyse as MA
    props = []
    nouveaux_par_famille = {}
    for fam, d in c["mp"]["familles"].items():
        pond = d["ponderations"]
        testes = {k: v for k, v in pond.items() if k in lot["notes"]}
        nv, detail = RC.recalibrer(res, testes, cfg["recalibrage"], 0)
        nouveaux_par_famille[fam] = (pond, pond | nv, detail)

    def combiner(choix):
        out = pd.DataFrame(np.nan, index=lot["note_globale"].index, columns=lot["note_globale"].columns)
        for cle in out.columns:
            pond = choix[familles[cle]]
            for t in out.index:
                sous = {k: {"note": lot["notes"][k].at[t, cle]} for k in lot["notes"] if not pd.isna(lot["notes"][k].at[t, cle])}
                if sous:
                    out.at[t, cle] = MA.note_globale(sous, pond)
        return out
    act = {fam: v[0] for fam, v in nouveaux_par_famille.items()}
    nouv = {fam: v[1] for fam, v in nouveaux_par_famille.items()}
    r = analyser({"actuelle": lot["note_globale"], "recalibree": combiner(nouv)}, lot, "matieres", cfg, regimes, sep)
    if "recalibree" in r:
        retenue, raison = RC.meilleure(r["actuelle"], r["recalibree"])
        res["note_recalibree"] = r["recalibree"] | {"libelle": LIBELLES["note_recalibree"]}
        for fam in act:
            props.append({"agent": "matieres_premieres", "fichier": "agents/matieres_premieres/config.json", "chemin": ["familles", fam, "ponderations"],
                          "actuel": act[fam], "propose": nouv[fam], "retenue": retenue and act[fam] != nouv[fam], "raison": raison,
                          "detail": nouveaux_par_famille[fam][2], "note_actuelle": _resume_note(r["actuelle"]),
                          "note_recalibree": _resume_note(r["recalibree"])})
    return {"matieres": {"titre": TITRES["matieres"], "periode": _periode(lot), "separation": _iso(sep), "signaux": res,
                         "horizon_reference": cfg["horizon_reference"]["matieres"], "indice": "moyenne équipondérée de l'univers",
                         "reference_momentum": ref, "combinaisons": combis},
            "_propositions": props}


def lot_secteurs(f, c: dict, racine: Path, test: bool, regimes) -> dict:
    cfg = c["bt"]
    lot = SC.construire(f, c["chef"], c["macro"], cfg, cfg["periode"]["debut"])
    sep = separation_du_lot(lot["note_globale"], cfg)
    res = analyser(dict(lot["notes"]) | {"note_globale": lot["note_globale"]}, lot, "secteurs", cfg, regimes, sep)
    res["note_globale"]["libelle"] = "Note de rotation (tendance et cycle)"
    phases = lot["phases"].dropna()
    return {"secteurs": {"titre": TITRES["secteurs"], "periode": _periode(lot), "separation": _iso(sep), "signaux": res,
                         "horizon_reference": cfg["horizon_reference"]["secteurs"], "indice": cfg["secteurs"]["indice_reference"],
                         "phases": {p: int(n) for p, n in phases.value_counts().items()}},
            "_propositions": []}


def lot_tendance(f, c: dict, racine: Path, test: bool, regimes) -> dict:
    cfg = c["bt"]
    pays_cfg = f.pays_test() if test else c["pays"]["pays"]
    r = T.construire(f, cfg, pays_cfg, c["mp"], cfg["periode"]["debut"])
    return {"tendance": {"titre": TITRES["tendance"], "periode": r["periode"], "separation": r["separation"], "signaux": {},
                         "suivi_tendance": r}, "_propositions": []}


def _iso(t):
    return t.strftime("%Y-%m-%d") if t is not None else None


# ------------------------------------------------------------------ assemblage

def assembler(lots: dict[str, dict], c: dict, sources: dict, jour: str, test: bool) -> tuple[dict, dict]:
    sections, propositions = {}, []
    for nom in ("pays", "chef", "entreprises", "matieres", "secteurs", "tendance"):
        for l in lots.values():
            if l and nom in l:
                sections[nom] = l[nom]
    for l in lots.values():
        propositions += (l or {}).get("_propositions", [])
    verdicts = {}
    for nom, s in sections.items():
        for k, r in s["signaux"].items():
            if k in ("note_recalibree", "score_recalibre"):
                continue
            verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
    resultats = {"jour": jour, "sections": sections, "non_testables": c["bt"]["non_testables"], "verdicts": verdicts,
                 "methode": {"horizons_mois": c["bt"]["horizons_mois"], "quantile_pct": int(c["bt"]["quantile"] * 100),
                             "frais_pct": {k: v for k, v in c["bt"]["frais"].items() if not k.startswith("_")},
                             "regimes": c["bt"]["regimes"], "verdicts": {k: v for k, v in c["bt"]["verdicts"].items() if not k.startswith("_")},
                             "recalibrage": {k: v for k, v in c["bt"]["recalibrage"].items() if not k.startswith("_")}},
                 "sources": list(sources.values()),
                 "propositions": [{k: v for k, v in p.items() if k != "detail"} | {"detail": p.get("detail")} for p in propositions]}
    from .rapport import resume_simple
    resultats["en_bref"] = [l for l in resume_simple(resultats)[2:] if l]
    proposition = {"jour": jour, "propositions": propositions,
                   "a_valider": any(p.get("retenue") for p in propositions),
                   "mention": "Proposition seulement : rien n'est appliqué sans validation dans une pull request séparée."}
    return resultats, proposition


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Backtest des règles de notation")
    ap.add_argument("--lot", default="tout", choices=("tout", "rapport", "sec") + LOTS)
    ap.add_argument("--tranche", help="i/n : tranche des sociétés à télécharger (lot sec)")
    ap.add_argument("--test", action="store_true", help="données synthétiques, sans réseau")
    ap.add_argument("--racine", default=str(RACINE), help="racine du dépôt (configs des agents, data/)")
    ap.add_argument("--sortie", help="dossier des résultats (défaut : data/backtest)")
    ap.add_argument("--lots", help="dossier des résultats intermédiaires par lot (défaut : agents/.cache/backtest/lots)")
    ap.add_argument("--cache", default=str(D.CACHE))
    ap.add_argument("--journal", help="journal de santé (défaut : data/journal/agent-backtest.json ; aucun en mode test)")
    ap.add_argument("--date", help="AAAA-MM-JJ (nom du rapport)")
    ap.add_argument("--appliquer-proposition", help="écrit les pondérations retenues d'une proposition dans les configs des agents")
    a = ap.parse_args(argv)
    racine = Path(a.racine)
    if a.appliquer_proposition:
        modifies = RC.appliquer(json.loads(Path(a.appliquer_proposition).read_text(encoding="utf-8")), racine)
        print("\n".join(modifies) if modifies else "aucune pondération à modifier")
        return 0
    c = lire_configs(racine)
    if a.test:
        c["bt"]["periode"]["debut"] = "2009-01-01"
        c["bt"]["verdicts"]["actifs_min"] = 5
        c["bt"]["entreprises"]["capitalisation_min_usd"] = 0  # sociétés fictives : capitalisations sans échelle réelle
    jour = a.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sortie = Path(a.sortie) if a.sortie else racine / "data" / "backtest"
    dossier_lots = Path(a.lots) if a.lots else (sortie / "lots" if a.test else Path(a.cache) / "lots")
    f = D.FournisseurTest() if a.test else D.FournisseurReel(Path(a.cache))
    if a.lot == "sec":
        i, n = (int(x) for x in (a.tranche or "0/1").split("/"))
        r = E.construire(f, _societes(f, racine, a.test), c["entreprises"], c["bt"], c["bt"]["periode"]["debut"], (i, n), lire_seulement=True)
        LOG.info("SEC, tranche %d/%d : %s", i, n, r)
        ecrire_json(dossier_lots / f"sources-sec-{i}.json", list(getattr(f, "sources", {}).values()))
        return 0 if r else 1
    regimes = None
    if a.lot != "rapport":
        vix = f.fred(c["bt"]["regimes"]["serie"])
        regimes = S.regimes_depuis_vix(vix, c["bt"]["regimes"]["seuil_tension"]) if len(vix) else None
    fonctions = {"pays": lot_pays, "entreprises": lot_entreprises, "matieres": lot_matieres, "secteurs": lot_secteurs, "tendance": lot_tendance}
    a_faire = LOTS if a.lot == "tout" else ((a.lot,) if a.lot in LOTS else ())
    for nom in a_faire:
        LOG.info("Lot %s…", nom)
        try:
            r = fonctions[nom](f, c, racine, a.test, regimes)
        except Exception as e:  # un lot en échec n'empêche pas les autres
            LOG.exception("lot %s en échec : %s", nom, e)
            r = None
        ecrire_json(dossier_lots / f"{nom}.json", {"lot": nom, "jour": jour, "resultat": r, "sources": list(getattr(f, "sources", {}).values())})
    if a.lot not in ("tout", "rapport"):
        return 0
    # Rapport : tous les lots disponibles
    lots, sources = {}, {}
    for nom in LOTS:
        x = lire_json(dossier_lots / f"{nom}.json")
        if x:
            lots[nom] = x.get("resultat")
            for s in x.get("sources") or []:
                e = sources.setdefault(s["nom"], {"nom": s["nom"], "ok": 0, "echecs": 0, "detail": None})
                e["ok"] += s.get("ok", 0)
                e["echecs"] += s.get("echecs", 0)
                e["detail"] = e["detail"] or s.get("detail")
    for fichier in dossier_lots.glob("sources-sec-*.json"):
        for s in lire_json(fichier) or []:
            e = sources.setdefault(s["nom"], {"nom": s["nom"], "ok": 0, "echecs": 0, "detail": None})
            e["ok"] += s.get("ok", 0)
            e["echecs"] += s.get("echecs", 0)
    resultats, proposition = assembler(lots, c, sources, jour, a.test)
    # Garde-fou : pas de nouveau réglage d'une section récemment recalibrée (propositions précédentes, lues avant d'écrire)
    anciennes = []
    for fichier in sorted(sortie.glob("proposition-*.json")):
        x = lire_json(fichier)
        if x:
            anciennes.append((fichier.stem.replace("proposition-", ""), x))
    RC.bloquer_recalibrages_rapproches(proposition["propositions"], anciennes, jour[:7], c["bt"]["recalibrage"].get("delai_mois", 6))
    proposition["a_valider"] = any(p.get("retenue") for p in proposition["propositions"])
    resultats["propositions"] = [{k: v for k, v in p.items() if k != "detail"} | {"detail": p.get("detail")} for p in proposition["propositions"]]
    from .rapport import rapport_markdown
    mois = jour[:7]
    ecrire_json(sortie / "resultats.json", enveloppe(resultats, "agent backtest (données historiques gratuites)", fictif=a.test,
                                                     rapport=f"data/backtest/rapport-{mois}.md", proposition=f"data/backtest/proposition-{mois}.json"))
    ecrire_json(sortie / f"proposition-{mois}.json", proposition)
    (sortie / f"rapport-{mois}.md").write_text(rapport_markdown(resultats, proposition), encoding="utf-8")
    LOG.info("Rapport écrit : %s", sortie / f"rapport-{mois}.md")
    manquants = [n for n in LOTS if not lots.get(n)]
    if not a.test or a.journal:
        chemin = Path(a.journal) if a.journal else racine / "data" / "journal" / "agent-backtest.json"
        etats = [{"nom": s["nom"], "etat": "ok" if not s["echecs"] else ("partielle" if s["ok"] else "échec"),
                  "detail": s.get("detail")} for s in sources.values()]
        bloc = sante.bloc_sante("backtest", "Backtest des règles", 20, "backtest.yml", etats, datetime.now(timezone.utc),
                                (lire_json(chemin) or {}).get("meta", {}).get("sante"),
                                raisons_supplementaires=[f"lot {n} non calculé" for n in manquants])
        sante.enregistrer_sante(chemin, bloc, forcer=True, description="Backtest mensuel des règles de notation")
    return 0 if not manquants else 1
