"""
Statistiques du backtest (fonctions pures, sans réseau).

Convention : un « panneau » est un DataFrame pandas indexé par les fins de mois (dates de
rééquilibrage), une colonne par actif. Un signal à la date t n'utilise que des données
publiées au plus tard à t ; le rendement futur à h mois va de t à t + h.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

ORDRE_VERDICTS = ["Garder", "Alléger", "Supprimer", "Données insuffisantes"]


# ------------------------------------------------------------------ outils

def fin_de_mois(serie: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Dernière valeur connue de chaque mois (index : dernier jour calendaire du mois)."""
    if serie is None or len(serie) == 0:
        return serie
    x = serie.sort_index()
    x.index = pd.DatetimeIndex(x.index)
    return x.groupby(x.index.to_period("M")).last().set_axis(
        x.groupby(x.index.to_period("M")).last().index.to_timestamp(how="end").normalize(), axis=0)


def rendements_futurs(prix: pd.DataFrame | pd.Series, h: int):
    """Rendement de t à t + h mois (NaN si le prix futur n'est pas encore connu)."""
    return prix.shift(-h) / prix - 1


def _r(x, d=4):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, d)


def newey_west_t(x: pd.Series, decalages: int) -> float | None:
    """Statistique t de la moyenne, corrigée de l'autocorrélation (Newey-West, noyau de Bartlett) :
    indispensable quand les rendements à h mois se chevauchent d'un mois sur l'autre."""
    v = pd.Series(x).dropna().to_numpy(dtype=float)
    n = len(v)
    if n < 6:
        return None
    e = v - v.mean()
    var = float(e @ e) / n
    for l in range(1, min(decalages, n - 1) + 1):
        g = float(e[l:] @ e[:-l]) / n
        var += 2 * (1 - l / (decalages + 1)) * g
    if var <= 0:
        return None
    return float(v.mean() / math.sqrt(var / n))


def ic_series(signal: pd.DataFrame, futur: pd.DataFrame, actifs_min: int) -> pd.Series:
    """Coefficient d'information de chaque date : corrélation de rang (Spearman) entre le signal
    et le rendement futur, sur les actifs où les deux sont connus (au moins `actifs_min`)."""
    s, f = signal.align(futur, join="inner")
    ok = s.notna() & f.notna()
    s, f = s.where(ok), f.where(ok)
    rs, rf = s.rank(axis=1), f.rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0)
    rf = rf.sub(rf.mean(axis=1), axis=0)
    num = (rs * rf).sum(axis=1)
    den = np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1))
    ic = num / den.replace(0, np.nan)
    ic[ok.sum(axis=1) < actifs_min] = np.nan
    return ic


def paniers(signal: pd.DataFrame, q: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Masques des meilleurs et des pires q (20 %) à chaque date (au moins un actif de chaque côté)."""
    n = signal.notna().sum(axis=1)
    k = np.maximum(1, np.floor(n * q)).astype(int)
    rang_haut = signal.rank(axis=1, ascending=False, method="first")
    rang_bas = signal.rank(axis=1, ascending=True, method="first")
    haut = rang_haut.le(k, axis=0) & signal.notna()
    bas = rang_bas.le(k, axis=0) & signal.notna()
    return haut, bas


def rotation(panier: pd.DataFrame) -> pd.Series:
    """Part du panier renouvelée d'un mois sur l'autre."""
    p = panier.astype(bool)
    avant = p.shift(1, fill_value=False).astype(bool)
    gardes = (p & avant).sum(axis=1)
    taille = p.sum(axis=1).replace(0, np.nan)
    rot = 1 - gardes / taille
    rot.iloc[:1] = 1.0  # premier mois : constitution du panier
    return rot


def moyenne_panier(futur: pd.DataFrame, panier: pd.DataFrame) -> pd.Series:
    f, p = futur.align(panier, join="inner")
    return f.where(p).mean(axis=1)


# ------------------------------------------------------------------ analyse d'un signal

def analyser_signal(signal: pd.DataFrame, prix: pd.DataFrame, indice: pd.Series | None, horizons: list[int],
                    h_ref: int, q: float, frais_pct: float, regimes: pd.Series | None,
                    separation: pd.Timestamp | None, cfg_verdicts: dict) -> dict:
    """Toutes les mesures d'un signal (ou d'une note) : par horizon, stabilité, régimes, verdict."""
    signal = signal.reindex(index=prix.index, columns=prix.columns)
    haut, bas = paniers(signal, q)
    res = {"horizons": {}, "actifs_moyen": _r(signal.notna().sum(axis=1)[signal.notna().sum(axis=1) > 0].mean(), 1)}
    ics = {}
    for h in horizons:
        fut = rendements_futurs(prix, h)
        ic = ic_series(signal, fut, cfg_verdicts["actifs_min"])
        ics[h] = ic
        m_haut, m_bas = moyenne_panier(fut, haut), moyenne_panier(fut, bas)
        ecart = (m_haut - m_bas).where(ic.notna())
        b = rendements_futurs(indice, h).reindex(prix.index) if indice is not None else fut.mean(axis=1)
        vs_indice = (m_haut - b).where(ic.notna())
        # Taux de réussite : part des actifs du panier haut qui battent l'indice sur h mois,
        # part des actifs du panier bas qui font moins bien que lui
        f_rel = fut.sub(b, axis=0)
        valide = ic.notna()
        r_haut = (f_rel.where(haut) > 0).where(haut & f_rel.notna())[valide]
        r_bas = (f_rel.where(bas) < 0).where(bas & f_rel.notna())[valide]
        res["horizons"][str(h)] = {
            "mois": int(valide.sum()),
            "ic_moyen": _r(ic.mean()),
            "ic_t": _r(newey_west_t(ic, max(h, 1)), 2),
            "ic_positif_pct": _r(100 * (ic.dropna() > 0).mean(), 1) if valide.any() else None,
            "haut_pct": _r(100 * m_haut[valide].mean(), 2),
            "bas_pct": _r(100 * m_bas[valide].mean(), 2),
            "indice_pct": _r(100 * b[valide].mean(), 2),
            "ecart_pct": _r(100 * ecart.mean(), 2),
            "haut_vs_indice_pct": _r(100 * vs_indice.mean(), 2),
            "mois_gagnants_pct": _r(100 * (ecart.dropna() > 0).mean(), 1) if valide.any() else None,
            "reussite_haut_pct": _r(100 * np.nanmean(r_haut.to_numpy(dtype=float)), 1) if r_haut.notna().any().any() else None,
            "reussite_bas_pct": _r(100 * np.nanmean(r_bas.to_numpy(dtype=float)), 1) if r_bas.notna().any().any() else None,
        }
    # Frais : rééquilibrage mensuel des deux paniers ; aller-retour payé sur la part renouvelée
    fut1 = rendements_futurs(prix, 1)
    valide1 = ics[1].notna() if 1 in ics else ic_series(signal, fut1, cfg_verdicts["actifs_min"]).notna()
    rot_h, rot_b = rotation(haut), rotation(bas)
    brut = (moyenne_panier(fut1, haut) - moyenne_panier(fut1, bas))[valide1]
    cout = ((rot_h + rot_b) * frais_pct / 100)[valide1]
    net = brut - cout
    b1 = rendements_futurs(indice, 1).reindex(prix.index) if indice is not None else fut1.mean(axis=1)
    haut_net = (moyenne_panier(fut1, haut) - b1 - rot_h * frais_pct / 100)[valide1]
    res["frais"] = {
        "aller_retour_pct": frais_pct,
        "rotation_mensuelle_pct": _r(100 * (rot_h[valide1].mean() + rot_b[valide1].mean()) / 2, 1),
        "ecart_brut_annuel_pct": _r(1200 * brut.mean(), 2),
        "ecart_net_annuel_pct": _r(1200 * net.mean(), 2),
        "haut_vs_indice_net_annuel_pct": _r(1200 * haut_net.mean(), 2),
        "cout_annuel_pct": _r(1200 * cout.mean(), 2),
    }
    # Stabilité dans le temps (horizon de référence)
    ic_ref = ics[h_ref].dropna()
    par_annee = ic_ref.groupby(ic_ref.index.year).mean()
    res["stabilite"] = {
        "par_annee": {str(a): _r(v, 3) for a, v in par_annee.items()},
        "annees_positives_pct": _r(100 * (par_annee > 0).mean(), 1) if len(par_annee) else None,
    }
    # Séparation apprentissage / vérification hors échantillon
    if separation is None and len(ic_ref):
        separation = ic_ref.index[len(ic_ref) // 2]
    app = ic_ref[ic_ref.index <= separation] if separation is not None else ic_ref.iloc[:0]
    ver = ic_ref[ic_ref.index > separation] if separation is not None else ic_ref.iloc[:0]
    net_ver = net[net.index > separation] if separation is not None else net.iloc[:0]
    res["echantillons"] = {
        "separation": separation.strftime("%Y-%m-%d") if separation is not None else None,
        "apprentissage": {"mois": len(app), "ic_moyen": _r(app.mean()), "ic_t": _r(newey_west_t(app, h_ref), 2),
                          "debut": app.index[0].strftime("%Y-%m") if len(app) else None},
        "verification": {"mois": len(ver), "ic_moyen": _r(ver.mean()), "ic_t": _r(newey_west_t(ver, h_ref), 2),
                         "ecart_net_annuel_pct": _r(1200 * net_ver.mean(), 2),
                         "fin": ver.index[-1].strftime("%Y-%m") if len(ver) else None},
        "total": {"mois": len(ic_ref), "ic_moyen": _r(ic_ref.mean()), "ic_t": _r(newey_west_t(ic_ref, h_ref), 2)},
    }
    # Par régime de marché (calme, tension)
    res["regimes"] = {}
    if regimes is not None and len(ic_ref):
        reg = regimes.reindex(ic_ref.index)
        for nom in ("calme", "tension"):
            x = ic_ref[reg == nom]
            res["regimes"][nom] = {"mois": len(x), "ic_moyen": _r(x.mean()), "ic_t": _r(newey_west_t(x, h_ref), 2)}
    res["horizon_reference"] = h_ref
    res["verdict"], res["raison"] = verdict(res, cfg_verdicts)
    return res


def verdict(res: dict, cfg: dict) -> tuple[str, str]:
    """« Garder », « Alléger », « Supprimer » ou « Données insuffisantes » (règles dans config.json et methode.md)."""
    e = res["echantillons"]
    app, ver, tot = e["apprentissage"], e["verification"], e["total"]
    if tot["mois"] < cfg["mois_min"] or ver["mois"] < cfg["mois_min_verification"] or (res.get("actifs_moyen") or 0) < cfg["actifs_min"]:
        return "Données insuffisantes", (f"{tot['mois']} mois mesurés dont {ver['mois']} hors échantillon, "
                                          f"{fr(res.get('actifs_moyen') or 0, 0, False)} actifs en moyenne : pas de conclusion "
                                          f"(minimum {cfg['mois_min']} mois, {cfg['mois_min_verification']} hors échantillon, {cfg['actifs_min']} actifs)")
    ic_a, ic_v, t_v, ic_t = app["ic_moyen"] or 0, ver["ic_moyen"] or 0, ver["ic_t"] or 0, tot["ic_moyen"] or 0
    net_v = ver.get("ecart_net_annuel_pct")
    if ic_a > 0 and ic_t >= cfg["ic_garder"] and ic_v >= cfg["ic_garder"] and t_v >= cfg["t_garder"] and (net_v is None or net_v > 0):
        return "Garder", (f"prédictif dans les deux moitiés (IC {fr(ic_a)} puis {fr(ic_v)} hors échantillon, t = {fr(t_v, 1, False)}), "
                          f"écart meilleurs − pires de {fr(net_v, 1)} %/an après frais hors échantillon")
    if ic_v <= 0 and ic_t <= cfg["ic_supprimer"]:
        sens = " (de sens contraire)" if ic_t < -cfg["ic_supprimer"] else ""
        return "Supprimer", (f"aucun pouvoir prédictif{sens} : IC {fr(ic_t)} sur tout l'historique, "
                             f"{fr(ic_v)} hors échantillon")
    raisons = []
    if ic_a <= 0:
        raisons.append(f"IC négatif ou nul en apprentissage ({fr(ic_a)})")
    if ic_v < cfg["ic_garder"]:
        raisons.append(f"IC hors échantillon faible ({fr(ic_v)})")
    elif t_v < cfg["t_garder"]:
        raisons.append(f"peu significatif hors échantillon (t = {fr(t_v, 1, False)})")
    if net_v is not None and net_v <= 0:
        raisons.append(f"écart effacé par les frais ({fr(net_v, 1)} %/an)")
    return "Alléger", "signal faible ou instable : " + ", ".join(raisons or ["résultats mitigés"])


def fr(x, d: int = 3, signe: bool = True) -> str:
    if x is None:
        return "n. d."
    return (f"{x:+.{d}f}" if signe and x else f"{x:.{d}f}").replace(".", ",").replace("-", "−")


# ------------------------------------------------------------------ combinaison de signaux

def note_ponderee(notes: dict[str, pd.DataFrame], poids: dict[str, float]) -> pd.DataFrame:
    """Moyenne pondérée des notes disponibles (poids renormalisés sur les notes présentes, comme les agents)."""
    cles = [k for k in poids if k in notes and poids[k]]
    if not cles:
        return pd.DataFrame()
    ref = notes[cles[0]]
    idx = ref.index
    cols = ref.columns
    for k in cles[1:]:
        idx = idx.union(notes[k].index)
        cols = cols.union(notes[k].columns)
    total = pd.DataFrame(0.0, index=idx, columns=cols)
    somme = pd.DataFrame(0.0, index=idx, columns=cols)
    for k in cles:
        n = notes[k].reindex(index=idx, columns=cols)
        total = total + n.fillna(0) * poids[k]
        somme = somme + n.notna() * poids[k]
    return total / somme.replace(0, np.nan)


def percentile_transversal(signal: pd.DataFrame) -> pd.DataFrame:
    """Percentile (0–100) de chaque actif dans sa classe, date par date."""
    return signal.rank(axis=1, pct=True) * 100


def regimes_depuis_vix(vix: pd.Series, seuil: float) -> pd.Series:
    """« calme » / « tension » selon la moyenne mensuelle du VIX."""
    m = vix.dropna().groupby(pd.DatetimeIndex(vix.dropna().index).to_period("M")).mean()
    m.index = m.index.to_timestamp(how="end").normalize()
    return m.map(lambda v: "tension" if v >= seuil else "calme")


def resume_verdicts(resultats: dict[str, dict]) -> dict[str, int]:
    compte = {v: 0 for v in ORDRE_VERDICTS}
    for r in resultats.values():
        compte[r["verdict"]] = compte.get(r["verdict"], 0) + 1
    return compte
