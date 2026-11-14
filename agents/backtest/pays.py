"""
Lot « pays » : notes reconstituées mois par mois avec les fonctions mêmes de l'agent pays
(agents/pays/notation.py), à partir de données historiques datées par leur publication.

Indicateurs testés : croissance du PIB, indicateur avancé, inflation, taux réel, valorisation
(proxy : rendement du dividende de l'ETF pays, comparé à la médiane), momentum 12 mois, devise
3 mois (indicateur de détail, hors note globale), puis la note globale (règle de prudence comprise)
et la note globale « brute » (sans la règle de prudence).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..pays import notation as N
from . import stats as S


def _mensuel(df: pd.DataFrame) -> pd.DataFrame:
    return S.fin_de_mois(df) if df is not None and len(df) else pd.DataFrame()


def _retarder(serie: pd.Series, mois: int, index: pd.DatetimeIndex) -> pd.Series:
    """Valeur connue à chaque fin de mois : la série publiée avec `mois` mois de retard."""
    if serie is None or not len(serie):
        return pd.Series(np.nan, index=index)
    s = serie.copy()
    s.index = (pd.DatetimeIndex(s.index).to_period("M") + mois).to_timestamp(how="end").normalize()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(index.union(s.index)).ffill(limit=3).reindex(index)


def _appliquer(f, *panneaux: pd.DataFrame) -> pd.DataFrame:
    """Applique une fonction de notation case par case (NaN si une entrée manque)."""
    ref = panneaux[0]
    vals = [p.reindex(index=ref.index, columns=ref.columns).to_numpy(dtype=object) for p in panneaux]
    out = np.full(ref.shape, np.nan)
    for i in range(ref.shape[0]):
        for j in range(ref.shape[1]):
            args = [v[i, j] for v in vals]
            if any(a is None or (isinstance(a, float) and np.isnan(a)) for a in args[:1]):
                continue
            args = [None if (isinstance(a, float) and np.isnan(a)) else a for a in args]
            out[i, j] = f(*args)
    return pd.DataFrame(out, index=ref.index, columns=ref.columns)


def construire(fournisseur, pays_cfg: dict, indices: dict, ponderations: dict, cfg: dict, debut: str) -> dict:
    """Renvoie {prix, indice, notes, valeurs, note_globale, fin} pour le lot pays."""
    codes = sorted(pays_cfg)
    etf = {c: pays_cfg[c].get("etf") for c in codes if pays_cfg[c].get("etf")}
    idx_sym = {c: (indices.get(c) or {}).get("yahoo") for c in codes
               if (indices.get(c) or {}).get("yahoo") and (indices.get(c) or {}).get("etat_yahoo") == "ok"}
    fx = {c: pays_cfg[c]["devise"] for c in codes if (pays_cfg[c].get("devise") or {}).get("symbole")}
    ref = cfg["pays"]["indice_reference"]
    c = fournisseur.cours(list(etf.values()) + list(idx_sym.values()) + [f["symbole"] for f in fx.values()] + [ref], debut)
    aj = _mensuel(c["ajuste"])
    cl = _mensuel(c["cloture"])
    mois = aj.index[aj.index >= pd.Timestamp(debut) + pd.offsets.MonthEnd(12)]
    prix = pd.DataFrame({k: aj[s] for k, s in etf.items() if s in aj}).reindex(mois)
    indice = aj[ref].reindex(mois) if ref in aj else None
    retards = cfg["pays"]["retard_publication_mois"]
    valeurs, notes = {}, {}

    # Momentum 12 mois : indice national en monnaie locale, à défaut l'ETF pays (règle de l'agent pays)
    mom = {}
    for k in codes:
        s = idx_sym.get(k)
        serie = cl[s] if s and s in cl and cl[s].notna().sum() > 24 else (aj[etf[k]] if etf.get(k) in aj else None)
        if serie is not None:
            mom[k] = (serie / serie.shift(12) - 1) * 100
    valeurs["momentum"] = pd.DataFrame(mom).reindex(mois)
    notes["momentum"] = valeurs["momentum"].map(lambda v: np.nan if pd.isna(v) else N.note_momentum(v))

    # Valorisation (proxy) : rendement du dividende sur 12 mois de l'ETF pays ; PER implicite = 1 / rendement,
    # comparé à la médiane des pays (même barème que le PER de l'agent pays)
    div = c["dividendes"].fillna(0)
    rend = {}
    for k, s in etf.items():
        if s in div and s in c["cloture"]:
            somme = div[s].rolling("365D").sum()
            r = (somme / c["cloture"][s] * 100).where(lambda x: x > 0)
            rend[k] = S.fin_de_mois(r)
    rend = pd.DataFrame(rend).reindex(mois)
    rend.loc[rend.index < pd.Timestamp(debut) + pd.Timedelta(days=400)] = np.nan  # 12 mois de dividendes au moins
    mediane = rend.median(axis=1)
    ecart_per = (1 / rend).mul(mediane, axis=0).sub(1).mul(100)
    valeurs["valorisation"] = ecart_per
    notes["valorisation"] = ecart_per.map(lambda v: np.nan if pd.isna(v) else N.note_valorisation(v))

    # Devise contre le dollar sur 3 mois (appréciation positive)
    dev = {}
    for k, f in fx.items():
        if f["symbole"] in cl:
            v = (cl[f["symbole"]] / cl[f["symbole"]].shift(3) - 1) * 100
            dev[k] = -v if f.get("inverse") else v
    valeurs["devise_3m"] = pd.DataFrame(dev).reindex(mois)
    notes["devise_3m"] = valeurs["devise_3m"].map(lambda v: np.nan if pd.isna(v) else N.note_devise(v))

    # Indicateur avancé de l'OCDE : niveau et pente sur 3 mois, connus avec 2 mois de retard
    iso3 = {k: pays_cfg[k]["iso3"] for k in codes if pays_cfg[k].get("iso3")}
    cli = fournisseur.ocde_cli(list(iso3.values()), debut)
    cli_p = pd.DataFrame({k: _retarder(cli.get(z), retards["indicateur_avance"], mois) for k, z in iso3.items()})
    valeurs["indicateur_avance"] = cli_p
    notes["indicateur_avance"] = _appliquer(lambda a, b: N.note_indicateur_avance(a, b), cli_p, cli_p.shift(3))

    # Inflation (OCDE, glissement annuel), cible de la banque centrale
    infl = fournisseur.ocde_inflation(list(iso3.values()), debut)
    inf_p = pd.DataFrame({k: _retarder(infl.get(z), retards["inflation"], mois) for k, z in iso3.items()})
    valeurs["inflation"] = inf_p
    cibles = pd.DataFrame({k: pays_cfg[k].get("cible_inflation") for k in inf_p.columns}, index=mois, dtype=float)
    notes["inflation"] = _appliquer(lambda i, cib: N.note_inflation(i, cib), inf_p, cibles)

    # Taux réel = taux directeur (BRI) − inflation ; direction de la banque centrale sur 3 mois
    bis = {k: pays_cfg[k].get("bis") for k in codes if pays_cfg[k].get("bis")}
    taux = fournisseur.bis_taux(sorted(set(bis.values())), debut)
    t_p = pd.DataFrame({k: _retarder(taux.get(b), retards["taux_directeur"], mois) for k, b in bis.items()})
    reel = t_p - inf_p.reindex(columns=t_p.columns)
    variation = t_p - t_p.shift(3)
    direction = variation.map(lambda v: None if pd.isna(v) else "hausse" if v > 0.1 else "baisse" if v < -0.1 else "stable")
    valeurs["taux_reel"] = reel
    notes["taux_reel"] = _appliquer(lambda r, d: N.note_taux_reel(r, d), reel, direction)

    # Croissance du PIB (FMI) : année écoulée, connue après la publication d'avril (révisions comprises)
    fmi = fournisseur.fmi_croissance()
    cr = pd.DataFrame(index=mois, columns=list(iso3), dtype=float)
    for k, z in iso3.items():
        x = fmi.get(z) or {}
        for t in mois:
            annee = t.year - 1 if t.month > retards["croissance_pib"] else t.year - 2
            cr.loc[t, k] = x.get(annee, np.nan)
    valeurs["croissance_pib"] = cr
    notes["croissance_pib"] = cr.map(lambda v: np.nan if pd.isna(v) else N.note_croissance(v))

    # Note globale (pondérations de l'agent pays ; activité réelle absente : facultative, sans effet sur la couverture)
    notes_glob, brute = _notes_globales(notes, ponderations, prix.columns, mois)
    for k in list(notes):
        notes[k] = notes[k].reindex(index=mois, columns=prix.columns)
    return {"prix": prix, "indice": indice, "notes": notes, "valeurs": valeurs, "note_globale": notes_glob,
            "note_globale_brute": brute, "mois": mois, "symboles": etf}


def _notes_globales(notes: dict, ponderations: dict, colonnes, mois):
    poids = {k: v for k, v in ponderations.items() if not k.startswith("_")}
    cles = [k for k in poids if k in notes]
    arr = {k: notes[k].reindex(index=mois, columns=colonnes).to_numpy(dtype=float) for k in cles}
    out = np.full((len(mois), len(colonnes)), np.nan)
    brut = np.full_like(out, np.nan)
    for i in range(len(mois)):
        for j in range(len(colonnes)):
            ind = {k: {"note": arr[k][i, j], "libelle": k} for k in cles if not np.isnan(arr[k][i, j])}
            if len(ind) < 2:
                continue
            g = N.note_globale(ind, poids, facultatifs=("activite_reelle",))
            out[i, j], brut[i, j] = g["note"], g["brute"]
    return pd.DataFrame(out, index=mois, columns=colonnes), pd.DataFrame(brut, index=mois, columns=colonnes)


INDICATEURS_VARIATION = ("croissance_pib", "indicateur_avance", "inflation", "taux_reel", "devise_3m", "valorisation")


def variations(lot: dict, mois_liste=(3, 6)) -> dict[str, pd.DataFrame]:
    """Variation de la note de chaque indicateur sur 3 et 6 mois : amélioration (+) ou dégradation (−) selon les barèmes
    de l'agent pays (pour l'inflation et le taux réel, rapprochement ou éloignement de la zone jugée saine). Les notes
    étant calculées sur des séries déjà décalées de leur délai de publication, la variation l'est aussi."""
    res = {}
    for k in INDICATEURS_VARIATION:
        n = lot["notes"].get(k)
        if n is None:
            continue
        for m in mois_liste:
            res[f"var{m}_{k}"] = n - n.shift(m)
    return res
