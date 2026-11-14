"""
Lot « secteurs » : ETF sectoriels américains (SPDR), momentum 12 mois et rotation selon la phase du cycle
reconstituée mois par mois avec la règle de l'agent macro (agents/macro/analyse.py, phase_zone).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..macro import analyse as M
from ..pays import notation as N
from . import stats as S
from .pays import _retarder


def phases(cli: pd.Series, inflation: pd.Series, mois: pd.DatetimeIndex, seuils: dict) -> pd.Series:
    """Phase du cycle connue à chaque fin de mois (séries déjà retardées de leur délai de publication).
    Sans prévision du FMI (pas d'historique daté) : le vote se fait sur les deux autres signaux."""
    res = {}
    c, i = cli.dropna(), inflation.dropna()
    for t in mois:
        cc = [(d.strftime("%Y-%m"), float(v)) for d, v in c.loc[:t].iloc[-18:].items()]
        ii = [(d.strftime("%Y-%m"), float(v)) for d, v in i.loc[:t].iloc[-18:].items()]
        z = M.phase_zone(cc, ii, None, None, seuils) if len(cc) >= 5 and len(ii) >= 5 else None
        res[t] = z["phase"] if z else None
    return pd.Series(res, dtype=object)


def construire(fournisseur, cfg_chef: dict, cfg_macro: dict, cfg: dict, debut: str) -> dict:
    etf = cfg["secteurs"]["etf"]
    ref = cfg["secteurs"]["indice_reference"]
    c = fournisseur.cours(list(etf.values()) + [ref], debut)
    aj = S.fin_de_mois(c["ajuste"])
    mois = aj.index[aj.index >= pd.Timestamp(debut) + pd.offsets.MonthEnd(12)]
    prix = pd.DataFrame({s: aj[t] for s, t in etf.items() if t in aj}).reindex(mois)
    indice = aj[ref].reindex(mois) if ref in aj else None
    mom = (prix / prix.shift(12) - 1) * 100
    retards = cfg["pays"]["retard_publication_mois"]
    cli = _retarder(fournisseur.ocde_cli(["USA"], debut).get("USA"), retards["indicateur_avance"], mois)
    infl = _retarder(fournisseur.ocde_inflation(["USA"], debut).get("USA"), retards["inflation"], mois)
    ph = phases(cli, infl, mois, cfg_macro["seuils"])
    inflexions = cfg_chef["cycle"]["secteurs"]
    cycle = pd.DataFrame({s: [np.nan if p is None else float((inflexions.get(p) or {}).get(s, 0)) for p in ph] for s in prix.columns},
                         index=mois)
    notes = {"momentum_12m": mom.map(lambda v: np.nan if pd.isna(v) else N.note_momentum(v)), "cycle": 50 + 3 * cycle}
    # Note de rotation (signaux reconstituables, poids du chef d'orchestre pour les secteurs : tendance 15, cycle 18)
    p = cfg_chef["poids"]["secteurs"]
    glob = S.note_ponderee({"tendance": S.percentile_transversal(mom) * 0.5 + notes["momentum_12m"] * 0.5, "cycle": notes["cycle"]},
                           {"tendance": p["tendance"], "cycle": p["cycle"]})
    return {"prix": prix, "indice": indice, "notes": notes, "note_globale": glob.reindex(index=mois, columns=prix.columns),
            "mois": mois, "phases": ph}
