"""
Combinaisons de signaux (paires et triplets).

Règle : un actif est retenu seulement s'il est dans les meilleurs 30 % (percentile > 70 dans sa classe, date par date)
sur CHACUN des signaux combinés ; panier équipondéré, rééquilibrage mensuel, frais compris.

Garde-fous contre les faux positifs :
- candidats : signaux classés « Garder » ou « Alléger », avec un IC positif sur l'apprentissage, au plus
  `signaux_max` (les meilleurs IC d'apprentissage) → au plus C(n, 2) + C(n, 3) essais ;
- classement des combinaisons sur la période d'apprentissage SEULEMENT (statistique t de l'écart à l'indice) ;
  seuil de Bonferroni sur le nombre d'essais (combien survivraient à la correction, sans regarder la suite) ;
- les `retenues_max` meilleures sont jugées hors échantillon, avec une correction de Holm sur leur nombre ;
- verdict « Confirmée » seulement si l'écart hors échantillon est significatif après correction ET positif face à
  l'indice et au momentum seul.
Limite assumée : la liste des candidats s'appuie sur le verdict de chaque signal, qui regarde aussi la seconde moitié ;
d'où l'exigence d'un IC positif sur l'apprentissage et la correction des essais, plus sévère que nécessaire.
"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

from . import reference as RF
from . import stats as S

NOTES = ("note_", "score_", "equipondere")


def candidats(resultats: dict[str, dict], signaux_max: int) -> list[str]:
    ok = []
    for k, r in resultats.items():
        if k.startswith(NOTES) or r.get("verdict") not in ("Garder", "Alléger"):
            continue
        ic = r["echantillons"]["apprentissage"]["ic_moyen"]
        if ic is not None and ic > 0:
            ok.append((ic, k))
    return [k for _, k in sorted(ok, reverse=True)[:signaux_max]]


def base(cle: str) -> str:
    """Indicateur d'origine d'un signal en variation (var3_inflation → inflation)."""
    if cle.startswith("var") and "_" in cle and cle[3:].split("_", 1)[0].isdigit():
        return cle.split("_", 1)[1]
    return cle


def redondante(combo) -> bool:
    """Deux variations du même indicateur (sur 3 et 6 mois) disent presque la même chose : pas un vrai essai."""
    vues = set()
    for k in combo:
        if base(k) != k:
            if base(k) in vues:
                return True
            vues.add(base(k))
    return False


def masque_combine(signaux: list[pd.DataFrame], seuil_pct: float) -> pd.DataFrame:
    """Vrai si l'actif est au-delà du percentile `seuil_pct` sur chacun des signaux (et connu pour tous)."""
    m = None
    for s in signaux:
        x = S.percentile_transversal(s) > seuil_pct  # strict : 3 actifs sur 10 pour les meilleurs 30 %
        x = x & s.notna()
        m = x if m is None else (m & x.reindex_like(m).fillna(False))
    return m.fillna(False).astype(bool)


def _cible(masque: pd.DataFrame, prix: pd.DataFrame, indice: pd.Series | None, h: int, periode=None) -> dict:
    fut = S.rendements_futurs(prix, h)
    b = S.rendements_futurs(indice, h).reindex(prix.index) if indice is not None else fut.mean(axis=1)
    rel = fut.sub(b, axis=0).where(masque.reindex_like(fut).fillna(False).astype(bool))
    if periode is not None:
        rel = rel[periode(rel.index)]
    return S.cible(rel)


def evaluer(masque: pd.DataFrame, prix: pd.DataFrame, indice: pd.Series | None, indice_r: pd.Series, momentum_r: pd.Series | None,
            frais_pct: float, separation) -> dict:
    r = RF.rendement_masque(masque, prix, indice_r, frais_pct)
    taille = masque.sum(axis=1)
    ver = (lambda i: i > separation) if separation is not None else None
    return {"serie": r, "comparaison": RF.comparer(r, indice_r, momentum_r, separation),
            "taille_moyenne": S._r(taille[taille > 0].mean(), 1), "mois_avec_actifs_pct": S._r(100 * (taille > 0).mean(), 0),
            "cible": {str(h): _cible(masque, prix, indice, h) for h in (3, 6)},
            "cible_verification": {str(h): _cible(masque, prix, indice, h, ver) for h in (3, 6)} if ver else {}}


def tester(signaux: dict[str, pd.DataFrame], resultats: dict[str, dict], prix: pd.DataFrame, indice: pd.Series | None,
           momentum_r: pd.Series | None, frais_pct: float, separation, cfg: dict, libelles: dict) -> dict:
    cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
    pool = [k for k in candidats(resultats, cfg["signaux_max"]) if k in signaux]
    indice_r = RF.indice_mensuel(prix, indice)
    essais = []
    for n in (2, 3):
        for combo in combinations(pool, n):
            if redondante(combo):
                continue
            m = masque_combine([signaux[k].reindex(index=prix.index, columns=prix.columns) for k in combo], cfg["seuil_percentile"])
            ev = evaluer(m, prix, indice, indice_r, momentum_r, frais_pct, separation)
            app = ev["comparaison"].get("apprentissage", {})
            essais.append({"signaux": list(combo), "ev": ev, "t_app": app.get("t_vs_indice"), "mois_app": app.get("mois", 0)})
    n_essais = len(essais)
    alpha = cfg["alpha"]
    seuil_t = RF.t_critique(alpha / n_essais) if n_essais else None
    valides = [e for e in essais if e["t_app"] is not None and e["mois_app"] >= cfg["mois_min_apprentissage"]
               and e["ev"]["mois_avec_actifs_pct"] and e["ev"]["mois_avec_actifs_pct"] >= cfg["mois_actifs_min_pct"]]
    valides.sort(key=lambda e: e["t_app"], reverse=True)
    retenues = [e for e in valides if e["t_app"] > 0][:cfg["retenues_max"]]
    # Hors échantillon : p unilatérale de l'écart à l'indice, correction de Holm sur les combinaisons retenues
    for e in retenues:
        v = e["ev"]["comparaison"].get("verification", {})
        e["p"] = RF.p_unilaterale(v.get("t_vs_indice"))
    ordre = sorted(range(len(retenues)), key=lambda i: retenues[i]["p"] if retenues[i]["p"] is not None else 1.0)
    k = len(retenues)
    maxi = 0.0
    for rang, i in enumerate(ordre):
        p = retenues[i]["p"] if retenues[i]["p"] is not None else 1.0
        maxi = max(maxi, min(1.0, p * (k - rang)))
        retenues[i]["p_holm"] = maxi
    sortie = []
    for e in retenues:
        v = e["ev"]["comparaison"].get("verification", {})
        vi, vm = v.get("vs_indice_annuel_pct"), v.get("vs_momentum_annuel_pct")
        if (e["p_holm"] < alpha) and (vi or 0) > 0 and (vm is None or vm > 0):
            verdict = "Confirmée"
        elif (vi or 0) > 0:
            verdict = "Prometteuse (non significative)"
        else:
            verdict = "Non confirmée"
        sortie.append({"signaux": e["signaux"], "libelle": " + ".join(libelles.get(s, s) for s in e["signaux"]),
                       "verdict": verdict, "t_apprentissage": e["t_app"], "p_verification": S._r(e["p"], 4),
                       "p_holm": S._r(e["p_holm"], 4), "comparaison": e["ev"]["comparaison"],
                       "taille_moyenne": e["ev"]["taille_moyenne"], "mois_avec_actifs_pct": e["ev"]["mois_avec_actifs_pct"],
                       "cible": e["ev"]["cible"], "cible_verification": e["ev"]["cible_verification"]})
    return {"regle": f"actif retenu s'il est dans les meilleurs {100 - cfg['seuil_percentile']:.0f} % sur chaque signal combiné",
            "candidats": [{"cle": k, "libelle": libelles.get(k, k)} for k in pool], "essais": n_essais,
            "seuil_t_bonferroni": S._r(seuil_t, 2) if seuil_t else None,
            "passent_bonferroni_apprentissage": sum(1 for e in valides if seuil_t and e["t_app"] >= seuil_t),
            "alpha": alpha, "retenues": sortie}
