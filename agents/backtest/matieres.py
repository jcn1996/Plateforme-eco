"""
Lot « matières premières » : sous-notes reconstituées mois par mois avec les fonctions de l'agent
matières premières (agents/matieres_premieres/analyse.py) : tendance, structure de la courbe (proxy du
rendement de portage), stocks EIA, positionnement CFTC, niveau historique ; note globale pondérée par famille.
Non testés : moteurs macro (contexte multiple), flux des ETF et géopolitique (pas d'historique).
"""
from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from ..matieres_premieres import analyse as MA
from . import stats as S

SOUS_NOTES = ("tendance", "courbe", "stocks", "positionnement", "niveau")


def _liste(serie: pd.Series) -> list[tuple[str, float]]:
    s = serie.dropna()
    return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in s.items()]


def construire(fournisseur, cfg_mp: dict, cfg: dict, debut: str) -> dict:
    matieres = [m for m in cfg_mp["matieres"] if m["symbole"].endswith("=F")]
    etf_portage = cfg["matieres"]["etf_portage"]
    c = fournisseur.cours([m["symbole"] for m in matieres] + list(etf_portage.values()), debut)
    aj = c["ajuste"]
    mens = S.fin_de_mois(aj)
    mois = mens.index[mens.index >= pd.Timestamp(debut) + pd.offsets.MonthEnd(12)]
    cles = [m["cle"] for m in matieres if m["symbole"] in aj]
    prix = pd.DataFrame({m["cle"]: mens[m["symbole"]] for m in matieres if m["symbole"] in mens}).reindex(mois)
    seuils = cfg_mp["seuils"]
    cftc = fournisseur.cftc([m["cftc"] for m in matieres if m.get("cftc")], "2006-01-01")
    cpi = _liste(fournisseur.fred("CPIAUCSL"))
    eia_series = {}
    for cle, sources in cfg["matieres"]["eia"].items():
        for url, nom in sources:
            eia_series[(cle, nom)] = _liste(fournisseur.eia_xls(url))
    cfg_eia = {"brut": {"libelle": "stocks de brut", "unite": "Mb"}, "gaz": {"libelle": "stocks de gaz", "unite": "Gpi³"}}
    notes = {k: pd.DataFrame(np.nan, index=mois, columns=cles) for k in SOUS_NOTES}
    globale = pd.DataFrame(np.nan, index=mois, columns=cles)
    r_cftc, r_eia = cfg["matieres"]["retard_cftc_jours"], cfg["matieres"]["retard_eia_jours"]
    for m in matieres:
        if m["cle"] not in cles:
            continue
        serie = _liste(aj[m["symbole"]])
        dates = [d for d, _ in serie]
        etf = etf_portage.get(m["cle"])
        lignes = (cftc.get(m.get("cftc")) if m.get("cftc") else None)
        lignes = lignes.sort_values("date").to_dict("records") if lignes is not None and len(lignes) else []
        dates_cftc = [l["date"] for l in lignes]
        pond = cfg_mp["familles"][m["famille"]]["ponderations"]
        for t in mois:
            jour = t.strftime("%Y-%m-%d")
            k = bisect.bisect_right(dates, jour)
            if k < 60:
                continue
            sous = {"tendance": MA.tendance(serie[:k])}
            # Structure de la courbe (proxy) : ETF à contrats − contrat proche sur 3 mois, annualisé
            if etf and etf in aj:
                a, b = aj[etf].loc[:t].dropna(), aj[m["symbole"]].loc[:t].dropna()
                if len(a) > 70 and len(b) > 70:
                    t0 = t - pd.Timedelta(days=91)
                    ra = a.iloc[-1] / a.asof(t0) - 1
                    rb = b.iloc[-1] / b.asof(t0) - 1
                    if not (np.isnan(ra) or np.isnan(rb)):
                        roulement = (ra - rb) * 4 * 100
                        sous["courbe"] = {"note": MA.borne(50 + roulement * 2.5, 10, 90)}
            # Stocks EIA, publiés environ une semaine après la date de relevé
            limite = (t - pd.Timedelta(days=r_eia)).strftime("%Y-%m-%d")
            series = {nom: [x for x in s if x[0] <= limite] for (cle, nom), s in eia_series.items() if cle == m["cle"]}
            if series:
                sous["stocks"] = MA.stocks_eia(series, list(series), cfg_eia, seuils)
            # Positionnement CFTC (rapport du mardi publié le vendredi)
            if lignes:
                limite = (t - pd.Timedelta(days=r_cftc)).strftime("%Y-%m-%d")
                kc = bisect.bisect_right(dates_cftc, limite)
                if kc >= 52:
                    sous["positionnement"] = MA.positionnement(lignes[:kc], t.date(), seuils)
            cpi_t = [x for x in cpi if x[0] <= (t - pd.offsets.MonthEnd(1)).strftime("%Y-%m-%d")]
            sous["niveau"] = MA.niveau(serie[:k], cpi_t)
            for nom, sn in sous.items():
                if sn and sn.get("note") is not None:
                    notes[nom].at[t, m["cle"]] = sn["note"]
            g = MA.note_globale(sous, pond)
            if g is not None:
                globale.at[t, m["cle"]] = g
    return {"prix": prix, "indice": None, "notes": {k: v for k, v in notes.items() if v.notna().any().any()},
            "note_globale": globale, "mois": mois}
