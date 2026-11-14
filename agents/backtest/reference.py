"""
Référence simple « momentum seul » et comparaison d'un panier à l'indice et à cette référence.

Momentum seul : à chaque fin de mois, les meilleurs 20 % sur 12 mois hors dernier mois (cours de t − 12 à t − 1),
équipondérés, rééquilibrés chaque mois, frais compris (aller-retour payé sur la part renouvelée du panier).
Une note ou une combinaison n'apporte quelque chose que si elle fait mieux que cette règle sans analyse.
"""
from __future__ import annotations

import math

import pandas as pd

from . import stats as S


def momentum_12_1(prix: pd.DataFrame) -> pd.DataFrame:
    """Performance de t − 12 à t − 1 mois (le dernier mois, souvent en retournement, est exclu)."""
    return prix.shift(1) / prix.shift(12) - 1


def rendement_masque(masque: pd.DataFrame, prix: pd.DataFrame, indice_r: pd.Series, frais_pct: float) -> pd.Series:
    """Rendement mensuel net d'un panier équipondéré (actifs du masque à la fin du mois t, détenus de t à t + 1).
    Un mois sans aucun actif retenu, le panier reste investi dans l'indice (écart nul)."""
    fut1 = S.rendements_futurs(prix, 1)
    m = masque.reindex(index=prix.index, columns=prix.columns).fillna(False).astype(bool) & fut1.notna()
    brut = fut1.where(m).mean(axis=1)
    rot = S.rotation(m) * frais_pct / 100
    r = (brut - rot).where(m.any(axis=1))
    r = r.fillna(indice_r.reindex(prix.index))
    return r.where(fut1.notna().any(axis=1))


def rendement_signal(signal: pd.DataFrame, prix: pd.DataFrame, indice_r: pd.Series, q: float, frais_pct: float) -> pd.Series:
    haut, _ = S.paniers(signal.reindex(index=prix.index, columns=prix.columns), q)
    return rendement_masque(haut, prix, indice_r, frais_pct)


def indice_mensuel(prix: pd.DataFrame, indice: pd.Series | None) -> pd.Series:
    """Rendement mensuel de l'indice de référence (à défaut : moyenne équipondérée de l'univers)."""
    if indice is not None:
        return S.rendements_futurs(indice, 1).reindex(prix.index)
    return S.rendements_futurs(prix, 1).mean(axis=1)


def p_unilaterale(t: float | None) -> float | None:
    """Probabilité (loi normale) d'obtenir au moins t par hasard : test unilatéral « fait mieux »."""
    if t is None or (isinstance(t, float) and math.isnan(t)):
        return None
    return 0.5 * math.erfc(t / math.sqrt(2))


def t_critique(alpha: float) -> float:
    """Quantile unilatéral de la loi normale (bissection, sans scipy)."""
    bas, haut = 0.0, 10.0
    for _ in range(80):
        mil = (bas + haut) / 2
        if p_unilaterale(mil) > alpha:
            bas = mil
        else:
            haut = mil
    return (bas + haut) / 2


def _bloc(r: pd.Series, b: pd.Series, m: pd.Series | None) -> dict:
    ok = r.notna() & b.notna()
    r, b = r[ok], b[ok]
    if len(r) < 12:
        return {"mois": int(len(r))}
    an = lambda x: (1 + x).prod() ** (12 / len(x)) - 1  # noqa: E731
    vol = r.std() * math.sqrt(12)
    valeur = (1 + r).cumprod()
    res = {"mois": int(len(r)), "rendement_annuel_pct": S._r(100 * an(r), 2), "indice_annuel_pct": S._r(100 * an(b), 2),
           "vs_indice_annuel_pct": S._r(100 * (an(r) - an(b)), 2), "t_vs_indice": S._r(S.newey_west_t(r - b, 2), 2),
           "volatilite_pct": S._r(100 * vol, 1), "sharpe": S._r((an(r) - 0.02) / vol, 2) if vol else None,
           "perte_max_pct": S._r(100 * (valeur / valeur.cummax() - 1).min(), 1)}
    if m is not None:
        mm = m.reindex(r.index)
        ok2 = mm.notna()
        if ok2.sum() >= 12:
            res["momentum_annuel_pct"] = S._r(100 * an(mm[ok2]), 2)
            res["vs_momentum_annuel_pct"] = S._r(100 * (an(r[ok2]) - an(mm[ok2])), 2)
            res["t_vs_momentum"] = S._r(S.newey_west_t(r[ok2] - mm[ok2], 2), 2)
    return res


def comparer(r: pd.Series, indice_r: pd.Series, momentum_r: pd.Series | None, separation: pd.Timestamp | None) -> dict:
    """Panier comparé à l'indice et à la référence momentum, sur tout l'historique, l'apprentissage et la vérification."""
    b = indice_r.reindex(r.index)
    out = {"total": _bloc(r, b, momentum_r)}
    if separation is not None:
        out["apprentissage"] = _bloc(r[r.index <= separation], b[b.index <= separation], momentum_r)
        out["verification"] = _bloc(r[r.index > separation], b[b.index > separation], momentum_r)
    return out


def reference_momentum(prix: pd.DataFrame, indice: pd.Series | None, q: float, frais_pct: float, separation,
                       masque: pd.DataFrame | None = None) -> dict:
    """Portefeuille « momentum seul » d'un lot : série mensuelle nette et comparaison à l'indice."""
    sig = momentum_12_1(prix)
    if masque is not None:
        sig = sig.where(masque.reindex(index=sig.index, columns=sig.columns).fillna(False).astype(bool))
    b = indice_mensuel(prix, indice)
    r = rendement_signal(sig, prix, b, q, frais_pct)
    haut, _ = S.paniers(sig, q)
    rel = {h: S.rendements_futurs(prix, h).sub(S.rendements_futurs(indice, h).reindex(prix.index) if indice is not None
                                               else S.rendements_futurs(prix, h).mean(axis=1), axis=0) for h in (3, 6)}
    return {"serie": r, "indice_serie": b, "signal": sig,
            "resume": comparer(r, b, None, separation) | {"cible": {str(h): S.cible(rel[h].where(haut)) for h in rel},
                                                         "regle": "meilleurs 20 % sur 12 mois hors dernier mois, rééquilibrage mensuel, frais compris"}}
