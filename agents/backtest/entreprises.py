"""
Lot « entreprises » (États-Unis) : comptes SEC XBRL reconstitués « tels qu'ils étaient connus » à chaque fin de
mois (seuls les 10-K déposés avant cette date sont lus ; un retraitement n'est visible qu'après son dépôt), puis
notés avec les fonctions mêmes de l'agent entreprises (agents/entreprises/analyse.py et financier.py).
"""
from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from ..entreprises import analyse as A
from ..entreprises import financier as F
from ..commun.journal import journal
from . import stats as S

LOG = journal("backtest")


class Comptes:
    """Faits compacts d'une société → exercices connus à une date donnée."""

    def __init__(self, faits: dict):
        self.par_cle = {}
        for cle, lignes in (faits.get("faits") or {}).items():
            # (fin, rang du concept) → liste triée de (dépôt, valeur)
            d = {}
            for rang, fin, depot, val in lignes:
                d.setdefault(fin, {}).setdefault(rang, []).append((depot, val))
            for fin in d:
                for rang in d[fin]:
                    d[fin][rang].sort()
            self.par_cle[cle] = d
        self.actions = sorted(faits.get("actions_circulation") or [])
        self._depots_actions = [a[0] for a in self.actions]

    def _valeur(self, cle: str, fin: str, jour: str):
        par_rang = (self.par_cle.get(cle) or {}).get(fin)
        if not par_rang:
            return None
        for rang in sorted(par_rang):  # concept préféré d'abord
            pts = par_rang[rang]
            i = bisect.bisect_right(pts, (jour, float("inf")))
            if i:
                return pts[i - 1][1]  # dernière publication déposée au plus tard ce jour
        return None

    def exercices(self, jour: str, n: int = 6) -> list[dict]:
        fins = set()
        for cle in ("ca", "resultat_net"):
            for fin, par_rang in (self.par_cle.get(cle) or {}).items():
                if any(pts[0][0] <= jour for pts in par_rang.values()):
                    fins.add(fin)
        res = []
        for fin in sorted(fins, reverse=True)[:n]:
            e = {"fin": fin, "devise": "USD"}
            for cle in self.par_cle:
                v = self._valeur(cle, fin, jour)
                if v is not None:
                    e[cle] = v
            if e.get("capex") is not None:
                e["capex"] = abs(e["capex"])
            if e.get("interets") is not None:
                e["interets"] = abs(e["interets"])
            if e.get("cfo") is not None and e.get("capex") is not None:
                e["fcf"] = e["cfo"] - e["capex"]
            if e.get("ebit") is not None and e.get("amortissements") is not None:
                e["ebitda"] = e["ebit"] + abs(e["amortissements"])
            if e.get("dette_lt") is not None or e.get("dette_ct") is not None or e.get("emprunts_ct") is not None:
                e["dette_totale"] = (e.get("dette_lt") or 0) + (e.get("dette_ct") or 0) + (e.get("emprunts_ct") or 0)
            if e.get("capitaux_propres") is not None:
                e["capital_investi"] = e["capitaux_propres"] + (e.get("dette_totale") or 0) - (e.get("tresorerie") or 0)
            if e.get("impot") is not None and e.get("resultat_avant_impot"):
                e["taux_impot"] = e["impot"] / e["resultat_avant_impot"]
            if e.get("marge_brute") is None and e.get("ca") is not None and e.get("cout_ventes") is not None:
                e["marge_brute"] = e["ca"] - e["cout_ventes"]
            if len(e) > 4:
                res.append(e)
        return res

    def actions_au(self, jour: str):
        """(date de dépôt, nombre d'actions en circulation) le plus récent déposé au plus tard ce jour."""
        i = bisect.bisect_right(self._depots_actions, jour)
        return tuple(self.actions[i - 1]) if i else (None, None)


VARIATIONS = {
    "var_marge_op": "Marge opérationnelle — variation annuelle",
    "var_marge_brute": "Marge brute — variation annuelle",
    "var_croissance_ca": "Croissance du CA — accélération",
    "var_intensite_rd": "Intensité en R&D — variation annuelle",
}


def _part(a: dict, num: str, den: str = "ca") -> float | None:
    x, y = a.get(num), a.get(den)
    return x / y * 100 if x is not None and y and y > 0 else None


def variations_comptes(an: list[dict]) -> dict[str, float]:
    """Variations entre les deux derniers exercices déposés (seule fréquence des 10-K ; chaque valeur n'est connue
    qu'après le dépôt de l'exercice le plus récent, comme les niveaux) : marges et intensité en R&D (points de CA),
    accélération de la croissance du CA (croissance du dernier exercice − celle du précédent, en points)."""
    res = {}
    if len(an) < 2:
        return res
    a0, a1 = an[0], an[1]
    for cle, num in (("var_marge_op", "ebit"), ("var_marge_brute", "marge_brute"), ("var_intensite_rd", "rd")):
        x0, x1 = _part(a0, num), _part(a1, num)
        if x0 is not None and x1 is not None:
            res[cle] = x0 - x1
    if len(an) >= 3:
        ca = [a.get("ca") for a in an[:3]]
        if all(c and c > 0 for c in ca):
            res["var_croissance_ca"] = ((ca[0] / ca[1]) - (ca[1] / ca[2])) * 100
    return res


def facteur_divisions(divisions: pd.Series) -> pd.Series:
    """Produit des divisions d'actions postérieures à chaque date (1 s'il n'y en a pas)."""
    d = divisions.fillna(0)
    d = d.where(d > 0, 1.0)
    # produit des divisions strictement après t = produit total / produit cumulé jusqu'à t
    cumul = d.cumprod()
    return cumul.iloc[-1] / cumul if len(cumul) else cumul


def exces_univers(prix: pd.DataFrame, indice: pd.Series | None, masque: pd.DataFrame | None, h: int = 12) -> float | None:
    """Performance moyenne à h mois de l'univers équipondéré moins celle de l'indice (points par an) : mesure
    du biais du survivant (un univers « actuel » rejoué dans le passé bat l'indice par construction)."""
    if indice is None:
        return None
    fut = S.rendements_futurs(prix, h)
    if masque is not None:
        fut = fut.where(masque)
    e = (fut.mean(axis=1) - S.rendements_futurs(indice, h).reindex(prix.index)).dropna()
    return S._r(100 * e.mean() * 12 / h, 2) if len(e) else None


def construire(fournisseur, societes: list[dict], cfg_ent: dict, cfg: dict, debut: str, tranche: tuple[int, int] | None = None,
               lire_seulement: bool = False) -> dict | None:
    """Télécharge (lot `tranche`) ou assemble (tout l'univers) le panneau des entreprises."""
    exclus = set(cfg["entreprises"]["secteurs_exclus"])
    univers = [s for s in societes if s.get("pays") == "US" and s.get("secteur") not in exclus][:cfg["entreprises"]["max_societes"]]
    try:
        ciks = fournisseur.sec_ciks()
    except Exception as e:
        LOG.warning("SEC : liste des CIK indisponible (%s)", e)
        return None
    for s in univers:
        s["cik"] = s.get("cik") or ciks.get(s["ticker"].upper().replace(".", "-"))
    univers = [s for s in univers if s.get("cik")]
    if tranche:
        i, n = tranche
        univers = univers[i::n]
    faits = {}
    for k, s in enumerate(univers):
        f = fournisseur.sec_faits(s["cik"])
        if f and f.get("faits"):
            faits[s["ticker"]] = f
        if k % 50 == 0:
            LOG.info("SEC : %d/%d sociétés", k, len(univers))
    if lire_seulement:
        return {"societes": len(faits)}
    ref = cfg["entreprises"]["indice_reference"]
    tickers = sorted(faits)
    c = fournisseur.cours(tickers + [ref], debut)
    aj = S.fin_de_mois(c["ajuste"])
    cl = S.fin_de_mois(c["cloture"])
    quotidien = c["ajuste"]
    mois = aj.index[aj.index >= pd.Timestamp(debut) + pd.offsets.MonthEnd(12)]
    tickers = [t for t in tickers if t in aj]
    prix = aj[tickers].reindex(mois)
    indice = aj[ref].reindex(mois) if ref in aj else None
    divisions = {t: facteur_divisions(c["divisions"][t]) for t in tickers if t in c["divisions"]}
    secteur = {s["ticker"]: s.get("secteur") for s in univers}
    cfg_af = cfg_ent["analyse_financiere"]
    poids = {k: v for k, v in cfg_ent["ponderations"].items() if not k.startswith("_")}
    couverture = cfg_af.get("couverture_sur")
    comptes = {t: Comptes(faits[t]) for t in tickers}
    cles = list(poids)
    notes = {k: np.full((len(mois), len(tickers)), np.nan) for k in cles + ["note_globale", "note_globale_brute", "capitalisation"] + list(VARIATIONS)}
    for i, t in enumerate(mois):
        jour = t.strftime("%Y-%m-%d")
        mes = {}
        for j, tk in enumerate(tickers):
            an = comptes[tk].exercices(jour)
            if len(an) < 2 or pd.isna(prix.iat[i, j]):
                continue
            depot, nb_actions = comptes[tk].actions_au(jour)
            cap = None
            if nb_actions and not pd.isna(cl.at[t, tk]) and tk in divisions:
                fac = divisions[tk]
                k_depot = fac.index.searchsorted(pd.Timestamp(depot))
                f_depot = float(fac.iloc[min(k_depot, len(fac) - 1)]) if len(fac) else 1.0
                # Cours « Close » de Yahoo : ajusté des divisions jusqu'à aujourd'hui. Capitalisation à t =
                # cours ajusté × actions déposées × divisions postérieures au dépôt.
                cap = float(cl.at[t, tk]) * nb_actions * f_depot
                notes["capitalisation"][i, j] = cap
            serie = quotidien[tk].loc[:t].dropna()
            cours = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in serie.iloc[-400::5].items()]
            if cours and cours[-1][0] != serie.index[-1].strftime("%Y-%m-%d"):
                cours.append((serie.index[-1].strftime("%Y-%m-%d"), float(serie.iloc[-1])))
            for k, v in variations_comptes(an).items():
                notes[k][i, j] = v
            s = {"annuel": an, "cours": cours, "capitalisation_usd": cap, "fx_comptes": 1.0, "secteur_gics": secteur.get(tk),
                 "financier": None}
            try:
                mes[tk] = (j, A.mesures(s, cfg_af))
            except Exception as e:  # une donnée incohérente ne bloque pas le mois
                LOG.debug("mesures %s %s : %s", tk, jour, e)
        med = A.medianes_sectorielles([{"mesures": m, "secteur_gics": secteur.get(tk), "region": "amerique_nord"} for tk, (_, m) in mes.items()])
        for tk, (j, m) in mes.items():
            m.update(A.comparer(m, secteur.get(tk), "amerique_nord", med))
            n = A.notes(m, None)
            n.update(F.notes(m, None, cfg_af))
            for k in cles:
                if k in n:
                    notes[k][i, j] = n[k]
            g = A.note_globale(n, poids, couverture)
            if g["note"] is not None:
                notes["note_globale"][i, j] = g["note"]
                notes["note_globale_brute"][i, j] = g["brute"]
        if i % 24 == 0:
            LOG.info("entreprises : %s (%d sociétés notées)", jour, len(mes))
    panneaux = {k: pd.DataFrame(v, index=mois, columns=tickers) for k, v in notes.items()}
    # Contre le biais du survivant : à chaque date, seules les sociétés déjà assez grandes À CETTE DATE sont notées
    # (une petite société d'hier encore présente aujourd'hui est, le plus souvent, une réussite connue après coup)
    seuil = cfg["entreprises"].get("capitalisation_min_usd") or 0
    retenues = panneaux["capitalisation"] >= seuil
    biais = {"seuil_capitalisation_usd": seuil,
             "univers_complet_vs_indice_pct": exces_univers(prix, indice, None),
             "univers_retenu_vs_indice_pct": exces_univers(prix, indice, retenues),
             "societes_retenues_moyenne": S._r(retenues.sum(axis=1)[retenues.sum(axis=1) > 0].mean(), 0)}
    for k in list(panneaux):
        if k != "capitalisation":
            panneaux[k] = panneaux[k].where(retenues)
    return {"prix": prix, "indice": indice, "notes": {k: panneaux[k] for k in cles if panneaux[k].notna().any().any()},
            "variations": {k: panneaux[k] for k in VARIATIONS if panneaux[k].notna().any().any()}, "retenues": retenues,
            "note_globale": panneaux["note_globale"], "note_globale_brute": panneaux["note_globale_brute"],
            "mois": mois, "quotidien": quotidien[tickers], "secteurs": secteur, "capitalisation": panneaux["capitalisation"],
            "biais_survivant": biais}
