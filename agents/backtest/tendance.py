"""
Lot « tendance » : suivi de tendance (momentum) sur les ETF pays, les ETF sectoriels américains et les ETF de
matières premières. Sert à fixer les seuils du chef d'orchestre (tendance positive, force relative, excès) et de la
poche « tendance » de l'agent trader (stops, sortie).

1. Périodes de momentum : performance 12 mois hors dernier mois (12-1), 12 mois, 6-1, 6 mois, 3-1 — coefficient
   d'information (IC) dans chaque catégorie et écart entre le premier et le dernier tiers.
2. Filtre de tendance : premier tiers de force relative avec ou sans « tendance positive » (12-1 > 0 et cours au-dessus
   de la moyenne 200 jours).
3. Excès : parmi les tendances fortes (premier tiers, tendance positive), les actifs à valorisation tendue (pays :
   rendement du dividende au plus bas de son historique sur 5 ans), à positionnement encombré (matières : percentile
   CFTC sur 3 ans) ou en accélération parabolique (hausse sur 1 mois > k × écart-type mensuel habituel) font-ils moins
   bien ensuite que les autres ?
4. Poche « tendance » : simulation quotidienne (tendances fortes achetées en fin de mois, sans rééquilibrage des
   gagnants), avec plusieurs stops suiveurs et règles de sortie, frais compris.

Toutes les mesures à la date t n'utilisent que des cours connus en t ; les ordres sont passés au cours de clôture du
jour de bourse suivant.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import stats as S
from .regles import stats_portefeuille

DEFINITIONS = {  # (mois de début, mois de fin exclus) : performance du cours de t − début à t − fin
    "12-1": (12, 1), "12": (12, 0), "6-1": (6, 1), "6": (6, 0), "3-1": (3, 1),
}
LIBELLES_DEF = {"12-1": "12 mois hors dernier mois", "12": "12 mois", "6-1": "6 mois hors dernier mois", "6": "6 mois",
                "3-1": "3 mois hors dernier mois"}


# ------------------------------------------------------------------ univers et mesures

def univers(cfg: dict, pays_cfg: dict, cfg_mp: dict) -> dict[str, dict[str, str]]:
    """{catégorie: {nom: symbole}}. Matières : ETF adossés aux contrats (rendements investissables, sans saut de
    changement d'échéance)."""
    noms_mp = {m["cle"]: m["nom"] for m in cfg_mp.get("matieres", [])}
    return {
        "pays": {c: p["etf"] for c, p in sorted(pays_cfg.items()) if p.get("etf")},
        "secteurs": dict(cfg["secteurs"]["etf"]),
        "matieres": {noms_mp.get(k, k): s for k, s in cfg["matieres"]["etf_portage"].items()},
    }


def mesures(quot: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Mesures de fin de mois à partir des cours quotidiens ajustés."""
    q = quot.sort_index()
    m = S.fin_de_mois(q)
    mm200 = S.fin_de_mois(q.rolling(200, min_periods=180).mean())
    perf = {k: (m.shift(b) / m.shift(a) - 1) * 100 for k, (a, b) in DEFINITIONS.items()}
    r1 = m.pct_change(fill_method=None)
    vol = r1.shift(1).rolling(12, min_periods=9).std()  # écart-type mensuel habituel (12 mois précédents)
    return {"prix": m, "mm200": mm200, "au_dessus": m > mm200, "perf": perf, "r1": r1 * 100,
            "parabole": r1 / vol.replace(0, np.nan)}


def rang_categorie(signal: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    """Percentile (0-100) de chaque actif dans sa catégorie, à chaque date."""
    out = pd.DataFrame(np.nan, index=signal.index, columns=signal.columns)
    for cols in categories.values():
        c = [x for x in cols if x in signal.columns]
        if len(c) >= 2:
            out[c] = signal[c].rank(axis=1, pct=True) * 100
    return out


def relatif_categorie(futur: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    """Rendement futur moins la moyenne équipondérée de la catégorie."""
    out = pd.DataFrame(np.nan, index=futur.index, columns=futur.columns)
    for cols in categories.values():
        c = [x for x in cols if x in futur.columns]
        if c:
            out[c] = futur[c].sub(futur[c].mean(axis=1), axis=0)
    return out


def rendement_dividende(cloture: pd.DataFrame, dividendes: pd.DataFrame) -> pd.DataFrame:
    """Rendement du dividende sur 12 mois glissants (fin de mois), en %."""
    d = dividendes.fillna(0).resample("ME").sum().rolling(12, min_periods=12).sum()
    d.index = d.index.normalize()
    c = S.fin_de_mois(cloture)
    return (d.reindex(c.index) / c * 100).where(lambda x: x > 0)


def percentile_historique(serie: pd.DataFrame, fenetre: int, min_periodes: int) -> pd.DataFrame:
    """Percentile (0-100) de la valeur courante dans sa propre histoire récente (`fenetre` observations)."""
    def pct(x):
        x = x[~np.isnan(x)]
        return np.nan if len(x) < min_periodes else 100 * (x[:-1] < x[-1]).mean() + 50 * (x[:-1] == x[-1]).mean()
    return serie.rolling(fenetre, min_periods=min_periodes).apply(pct, raw=True)


def cftc_percentile(lignes: pd.DataFrame | None, mois: pd.DatetimeIndex, retard_jours: int) -> pd.Series:
    """Position nette des gérants en % de l'intérêt ouvert, percentile sur 3 ans (156 semaines), connue à chaque fin
    de mois (publication avec `retard_jours` jours de retard)."""
    if lignes is None or not len(lignes):
        return pd.Series(np.nan, index=mois)
    l = lignes.copy()
    l["date"] = pd.to_datetime(l["date"]) + pd.Timedelta(days=retard_jours)
    l = l.sort_values("date").set_index("date")
    net = (l["long"] - l["short"]) / l["oi"].replace(0, np.nan)
    p = percentile_historique(net.to_frame("x"), 156, 104)["x"]
    return p.reindex(p.index.union(mois)).ffill(limit=6).reindex(mois)


# ------------------------------------------------------------------ 1. périodes de momentum

def _moyennes(x: pd.Series, sep: pd.Timestamp) -> dict:
    x = x.dropna()
    a, v = x[x.index <= sep], x[x.index > sep]
    return {"mois": int(len(x)), "total": S._r(x.mean(), 4) if len(x) else None,
            "apprentissage": S._r(a.mean(), 4) if len(a) else None, "verification": S._r(v.mean(), 4) if len(v) else None,
            "t": S._r(S.newey_west_t(x, 3), 2)}


def comparer_periodes(me: dict, categories: dict, sep: pd.Timestamp, actifs_min: int) -> dict:
    """IC (Spearman, dans chaque catégorie) à 1 et 3 mois, et écart premier tiers − dernier tiers à 1 mois."""
    prix = me["prix"]
    fut = {h: S.rendements_futurs(prix, h) for h in (1, 3)}
    res = {}
    for k, sig in me["perf"].items():
        par_cat, ics, ecarts = {}, {1: [], 3: []}, []
        for cat, cols in categories.items():
            c = [x for x in cols if x in prix.columns]
            if len(c) < 3:
                continue
            d = {}
            for h in (1, 3):
                ic = S.ic_series(sig[c], fut[h][c], min(actifs_min, len(c)))
                ics[h].append(ic)
                d[f"ic_{h}m"] = _moyennes(ic, sep)
            rg = sig[c].rank(axis=1, pct=True)
            f1 = fut[1][c]
            ecart = (f1.where(rg > 2 / 3).mean(axis=1) - f1.where(rg <= 1 / 3).mean(axis=1)) * 100
            ecarts.append(ecart)
            d["ecart_tiers_1m_pct"] = _moyennes(ecart, sep)
            par_cat[cat] = d
        if not par_cat:
            continue
        res[k] = {"libelle": LIBELLES_DEF[k], "categories": par_cat,
                  "ic_1m": _moyennes(pd.concat(ics[1], axis=1).mean(axis=1), sep),
                  "ic_3m": _moyennes(pd.concat(ics[3], axis=1).mean(axis=1), sep),
                  "ecart_tiers_1m_pct": _moyennes(pd.concat(ecarts, axis=1).mean(axis=1), sep)}
    # Choix sur l'apprentissage seulement : IC moyen à 1 et 3 mois
    def cle(k):
        r = res[k]
        return np.nanmean([r["ic_1m"]["apprentissage"] or np.nan, r["ic_3m"]["apprentissage"] or np.nan])
    choisi = max(res, key=cle) if res else None
    return {"definitions": res, "retenue": choisi}


# ------------------------------------------------------------------ 2. filtre de tendance

def _bloc(x: pd.DataFrame, masque: pd.DataFrame, sep: pd.Timestamp) -> dict:
    x = x.where(masque & x.notna())
    v = x.stack().dropna()
    if not len(v):
        return {"n": 0}
    dates = v.index.get_level_values(0)
    a, b = v[dates <= sep], v[dates > sep]
    f = lambda s: S._r(100 * s.mean(), 2) if len(s) else None  # noqa: E731
    return {"n": int(len(v)), "moyenne_pct": f(v), "apprentissage_pct": f(a), "verification_pct": f(b),
            "reussite_pct": S._r(100 * (v > 0).mean(), 1), "n_apprentissage": int(len(a)), "n_verification": int(len(b))}


def tester_filtre(me: dict, categories: dict, defn: str, sep: pd.Timestamp) -> dict:
    """Rendement à 1 et 3 mois, relatif à la catégorie, du premier tiers de force relative selon que la tendance
    est positive (12-1 > 0 et cours > moyenne 200 jours) ou non ; et rendement absolu selon la tendance seule."""
    rs = rang_categorie(me["perf"][defn], categories)
    pos = (me["perf"][defn] > 0) & me["au_dessus"]
    res = {}
    for h in (1, 3):
        fut = S.rendements_futurs(me["prix"], h)
        rel = relatif_categorie(fut, categories)
        haut = rs >= 200 / 3
        res[f"{h}m"] = {
            "premier_tiers_tendance_positive": _bloc(rel, haut & pos, sep),
            "premier_tiers_tendance_negative": _bloc(rel, haut & ~pos & rs.notna(), sep),
            "absolu_tendance_positive": _bloc(fut, pos & rs.notna(), sep),
            "absolu_tendance_negative": _bloc(fut, ~pos & rs.notna(), sep),
        }
    return res


# ------------------------------------------------------------------ 3. excès

def tester_exces(me: dict, categories: dict, defn: str, sep: pd.Timestamp, grilles: dict,
                 valo_pct: pd.DataFrame | None, cftc_pct: pd.DataFrame | None, n_min: int) -> dict:
    """Parmi les tendances fortes, écart de rendement relatif (1 et 3 mois) entre actifs en excès et les autres,
    pour chaque seuil de la grille. Seuil retenu : écart le plus défavorable aux actifs en excès sur
    l'apprentissage (au moins n_min cas), confirmé seulement s'il garde le même signe hors échantillon."""
    rs = rang_categorie(me["perf"][defn], categories)
    forte = (rs >= 200 / 3) & (me["perf"][defn] > 0) & me["au_dessus"]
    criteres = {"parabolique": {k: me["parabole"] > k for k in grilles["parabole_k"]}}
    if valo_pct is not None:
        criteres["valorisation"] = {p: valo_pct.reindex_like(rs) <= 100 - p for p in grilles["valorisation_percentile"]}
    if cftc_pct is not None:
        criteres["positionnement"] = {p: cftc_pct.reindex_like(rs) >= p for p in grilles["cftc_percentile"]}
    fut = {h: relatif_categorie(S.rendements_futurs(me["prix"], h), categories) for h in (1, 3)}
    res = {}
    for nom, seuils in criteres.items():
        lignes = {}
        for s, m in seuils.items():
            m = m.fillna(False).astype(bool)
            d = {}
            for h in (1, 3):
                e, n = _bloc(fut[h], forte & m, sep), _bloc(fut[h], forte & ~m, sep)
                d[f"{h}m"] = {"exces": e, "sans_exces": n,
                              "ecart_apprentissage_pct": _diff(e.get("apprentissage_pct"), n.get("apprentissage_pct")),
                              "ecart_verification_pct": _diff(e.get("verification_pct"), n.get("verification_pct"))}
            lignes[str(s)] = d
        candidats = [(s, d) for s, d in lignes.items() if d["3m"]["exces"].get("n_apprentissage", 0) >= n_min
                     and d["3m"]["ecart_apprentissage_pct"] is not None]
        retenu, confirme = None, False
        if candidats:
            s, d = min(candidats, key=lambda x: x[1]["3m"]["ecart_apprentissage_pct"])
            if d["3m"]["ecart_apprentissage_pct"] < 0:
                retenu = s
                v = d["3m"]["ecart_verification_pct"]
                confirme = v is not None and v < 0 and d["3m"]["exces"].get("n_verification", 0) >= n_min // 2
        res[nom] = {"seuils": lignes, "retenu": retenu, "confirme": confirme}
    res["tendances_fortes"] = {"n": int(forte.sum().sum())}
    return res


def _diff(a, b):
    return None if a is None or b is None else round(a - b, 2)


# ------------------------------------------------------------------ 4. poche « tendance »

def simuler_poche(quot: pd.DataFrame, me: dict, categories: dict, defn: str, regle: dict, frais_ordre_pct: float,
                  exces: pd.DataFrame | None = None) -> dict:
    """Poche investie sur les tendances fortes (au plus `lignes` positions, une part de 1/lignes de la poche à
    l'achat, gagnants jamais allégés). Achats en fin de mois ; sorties : stop suiveur (quotidien, après
    `confirmations` clôtures sous le niveau), tendance cassée ou force relative sortie du premier tiers
    (fin de mois). Renvoie {mensuel: rendements mensuels, operations, motifs}."""
    q = quot.sort_index()
    rs = rang_categorie(me["perf"][defn], categories)
    perf = me["perf"][defn]
    mm = q.rolling(200, min_periods=180).mean()
    jours = q.index
    fins = set(pd.Series(jours, index=jours).groupby(jours.to_period("M")).max())
    rang_sortie = regle.get("sortie_rang", 200 / 3)
    n_lignes, conf = regle["lignes"], regle.get("confirmations", 1)
    cash, pos = 1.0, {}  # pos : symbole -> {parts, haut, sous}
    attente = None  # décisions de fin de mois exécutées à la clôture suivante
    valeurs, motifs, operations = {}, {}, 0
    frais = frais_ordre_pct / 100
    Q, MM = q.to_numpy(dtype=float), mm.to_numpy(dtype=float)
    col = {c: i for i, c in enumerate(q.columns)}
    for i, d in enumerate(jours):
        px = Q[i]
        if attente is not None:  # exécution des ordres décidés la veille (fin de mois)
            ventes, achats = attente
            for s in ventes:
                if s in pos and not np.isnan(px[col[s]]):
                    cash += pos.pop(s)["parts"] * px[col[s]] * (1 - frais)
                    operations += 1
            valeur = cash + sum(p["parts"] * px[col[s]] for s, p in pos.items() if not np.isnan(px[col[s]]))
            for s in achats:
                if len(pos) >= n_lignes or s in pos or np.isnan(px[col[s]]):
                    continue
                montant = min(cash, valeur / n_lignes)
                if montant <= valeur * 0.02:
                    break
                cash -= montant
                pos[s] = {"parts": montant * (1 - frais) / px[col[s]], "haut": px[col[s]], "sous": 0}
                operations += 1
            attente = None
        # stops quotidiens
        for s in list(pos):
            x = px[col[s]]
            if np.isnan(x):
                continue
            p = pos[s]
            p["haut"] = max(p["haut"], x)
            niveaux = []
            if regle.get("stop_mm200") and not np.isnan(MM[i, col[s]]):
                niveaux.append(MM[i, col[s]])
            if regle.get("stop_pct"):
                niveaux.append(p["haut"] * (1 - regle["stop_pct"] / 100))
            if niveaux and x < max(niveaux):
                p["sous"] += 1
                if p["sous"] >= conf:
                    cash += p["parts"] * x * (1 - frais)
                    operations += 1
                    del pos[s]
                    motifs["stop"] = motifs.get("stop", 0) + 1
            else:
                p["sous"] = 0
        valeurs[d] = cash + sum(p["parts"] * px[col[s]] for s, p in pos.items() if not np.isnan(px[col[s]]))
        if d in fins:
            t = d.to_period("M").to_timestamp(how="end").normalize()
            if t not in rs.index:
                continue
            r, pf = rs.loc[t], perf.loc[t]
            au_dessus = me["au_dessus"].loc[t]
            ex = exces.loc[t] if exces is not None and t in exces.index else None
            ventes = []
            for s in pos:
                if pd.isna(r.get(s)) or r[s] < rang_sortie:
                    ventes.append(s)
                    motifs["force relative"] = motifs.get("force relative", 0) + 1
                elif regle.get("sortie_tendance", True) and not (pf.get(s, np.nan) > 0 and bool(au_dessus.get(s, False))):
                    ventes.append(s)
                    motifs["tendance cassée"] = motifs.get("tendance cassée", 0) + 1
            elig = r[(r >= 200 / 3) & (pf > 0) & au_dessus.reindex(r.index).fillna(False).astype(bool)]
            if ex is not None and regle.get("filtre_exces"):
                elig = elig[~ex.reindex(elig.index).fillna(False).astype(bool)]
            achats = [s for s in elig.sort_values(ascending=False).index if s not in pos and s not in ventes]
            attente = (ventes, achats)
    v = pd.Series(valeurs)
    mensuel = S.fin_de_mois(v).pct_change(fill_method=None).dropna()
    return {"mensuel": mensuel, "operations": operations, "motifs": motifs}


def _stats(r: pd.Series, sep: pd.Timestamp) -> dict:
    return {"total": stats_portefeuille(r), "apprentissage": stats_portefeuille(r[r.index <= sep]),
            "verification": stats_portefeuille(r[r.index > sep])}


def choisir(res: list[dict]) -> dict | None:
    """Variante retenue : meilleur ratio de Sharpe sur l'apprentissage, parmi celles qui ne font pas moins bien hors
    échantillon que la règle de base de la même définition (sortie sur la force relative seule, sans stop) — garde-fou
    contre une variante réglée sur le hasard de la première moitié."""
    def sh(x, periode):
        v = x[periode].get("sharpe")
        return -9 if v is None else v
    base = {x["definition"]: x for x in res if not x["regle"]}
    ok = [x for x in res if x["definition"] in base and sh(x, "verification") >= sh(base[x["definition"]], "verification") - 1e-9]
    return max(ok or res, key=lambda x: sh(x, "apprentissage")) if res else None


def tester_poche(quot: pd.DataFrame, me: dict, categories: dict, defns: list[str], variantes: list[dict], lignes: int,
                 frais_ordre_pct: float, sep: pd.Timestamp, exces: pd.DataFrame | None, indice: pd.Series | None) -> dict:
    res = []
    for defn in defns:
        for v in variantes:
            regle = {"lignes": lignes} | v
            s = simuler_poche(quot, me, categories, defn, regle, frais_ordre_pct, exces)
            mois = max(len(s["mensuel"]) / 12, 1)
            res.append({"definition": defn, "variante": v["nom"], "regle": {k: x for k, x in v.items() if k != "nom"},
                        "operations_par_an": S._r(s["operations"] / mois, 1), "motifs": s["motifs"]} | _stats(s["mensuel"], sep))
    # Références : univers équipondéré (rééquilibré chaque mois) et indice mondial
    pm = S.fin_de_mois(quot)
    eq = pm.pct_change(fill_method=None).mean(axis=1).dropna()
    refs = {"univers_equipondere": _stats(eq.iloc[12:], sep)}
    if indice is not None and len(indice):
        refs["indice"] = _stats(S.fin_de_mois(indice).pct_change(fill_method=None).dropna().iloc[12:], sep)

    meilleure = choisir(res)
    return {"variantes": res, "references": refs, "lignes": lignes, "frais_ordre_pct": frais_ordre_pct,
            "retenue": {"definition": meilleure["definition"], "variante": meilleure["variante"]} if meilleure else None}


# ------------------------------------------------------------------ lot complet

def construire(fournisseur, cfg: dict, pays_cfg: dict, cfg_mp: dict, debut: str) -> dict:
    ct = cfg["tendance"]
    u = univers(cfg, pays_cfg, cfg_mp)
    symboles = sorted({s for d in u.values() for s in d.values()})
    ref = cfg["pays"]["indice_reference"]
    c = fournisseur.cours(symboles + [ref], debut)
    quot = c["ajuste"][[s for s in symboles if s in c["ajuste"]]].sort_index()
    quot = quot.loc[:, quot.notna().sum() > 300]
    categories = {cat: [s for s in d.values() if s in quot.columns] for cat, d in u.items()}
    me = mesures(quot)
    mois = me["prix"].index[me["prix"].index >= pd.Timestamp(debut) + pd.offsets.MonthEnd(13)]
    me = {k: ({kk: vv.reindex(mois) for kk, vv in v.items()} if isinstance(v, dict) else v.reindex(mois)) for k, v in me.items()}
    sep = mois[len(mois) // 2] if cfg["periode"].get("separation") is None else pd.Timestamp(cfg["periode"]["separation"])
    # Valorisation (pays) : rendement du dividende au plus bas de son historique sur 5 ans = valorisation tendue
    pays_cols = categories["pays"]
    rd = rendement_dividende(c["cloture"][pays_cols], c["dividendes"][pays_cols]) if pays_cols else None
    valo = percentile_historique(rd, 60, 36).reindex(mois) if rd is not None else None
    # Positionnement (matières) : percentile CFTC sur 3 ans
    codes = {m["cle"]: m.get("cftc") for m in cfg_mp.get("matieres", []) if m.get("cftc")}
    etf_cle = cfg["matieres"]["etf_portage"]
    cftc = fournisseur.cftc(sorted({codes[k] for k in etf_cle if k in codes}), "2006-01-01")
    cftc_pct = pd.DataFrame({s: cftc_percentile(cftc.get(codes.get(k)), mois, cfg["matieres"]["retard_cftc_jours"])
                             for k, s in etf_cle.items() if s in quot.columns and codes.get(k)}, index=mois)
    periodes = comparer_periodes(me, categories, sep, cfg["verdicts"]["actifs_min"])
    defn = ct.get("definition_forcee") or periodes["retenue"] or "12-1"
    filtre = tester_filtre(me, categories, defn, sep)
    exces = tester_exces(me, categories, defn, sep, ct["grilles"], valo, cftc_pct if len(cftc_pct.columns) else None, ct["exces_n_min"])
    # Masque d'excès avec les seuils retenus (pour la variante « filtre des excès » de la poche)
    masque = pd.DataFrame(False, index=mois, columns=quot.columns)
    k = exces["parabolique"]["retenu"]
    if k is not None:
        masque |= (me["parabole"] > float(k)).fillna(False)
    if valo is not None and exces.get("valorisation", {}).get("retenu") is not None:
        masque |= (valo.reindex_like(masque) <= 100 - float(exces["valorisation"]["retenu"])).fillna(False)
    if exces.get("positionnement", {}).get("retenu") is not None:
        masque |= (cftc_pct.reindex_like(masque) >= float(exces["positionnement"]["retenu"])).fillna(False)
    quot_sim = quot.loc[quot.index >= mois[0] - pd.Timedelta(days=400)]
    frais_ordre = cfg["frais"]["pays"] / 2
    poche = tester_poche(quot_sim, me, categories, sorted({defn, "12-1", "6-1"}), ct["variantes"], ct["lignes"], frais_ordre, sep,
                         masque, c["ajuste"][ref] if ref in c["ajuste"] else None)
    return {"periode": {"debut": mois[0].strftime("%Y-%m-%d"), "fin": mois[-1].strftime("%Y-%m-%d"), "mois": len(mois)},
            "separation": sep.strftime("%Y-%m-%d"), "univers": {k: len(v) for k, v in categories.items()},
            "periodes": periodes, "definition": defn, "filtre": filtre, "exces": exces, "poche": poche}


def resume(r: dict) -> list[str]:
    """Lignes du rapport (Markdown)."""
    if not r:
        return ["Lot non calculé."]
    L = [f"Période : {r['periode']['debut']} → {r['periode']['fin']} ({r['periode']['mois']} mois), coupure apprentissage / "
         f"vérification au {r['separation']}. Univers : " + ", ".join(f"{k} {n}" for k, n in r["univers"].items()) + " ETF.", ""]
    L += ["**Périodes de momentum** (IC moyen dans chaque catégorie ; écart mensuel premier − dernier tiers) :", "",
          "| Définition | IC 1 mois (appr. / vérif.) | IC 3 mois (appr. / vérif.) | Écart des tiers à 1 mois, % (appr. / vérif.) |",
          "|---|---|---|---|"]
    for k, d in r["periodes"]["definitions"].items():
        L.append(f"| {d['libelle']}{' (retenue)' if k == r['definition'] else ''} | {S.fr(d['ic_1m']['apprentissage'])} / {S.fr(d['ic_1m']['verification'])}"
                 f" | {S.fr(d['ic_3m']['apprentissage'])} / {S.fr(d['ic_3m']['verification'])}"
                 f" | {S.fr(d['ecart_tiers_1m_pct']['apprentissage'], 2)} / {S.fr(d['ecart_tiers_1m_pct']['verification'], 2)} |")
    f3 = r["filtre"]["3m"]
    L += ["", "**Filtre de tendance** (rendement à 3 mois relatif à la catégorie, premier tiers de force relative) : "
          f"tendance positive {S.fr(f3['premier_tiers_tendance_positive'].get('moyenne_pct'), 2)} % "
          f"({f3['premier_tiers_tendance_positive'].get('n', 0)} cas), tendance négative "
          f"{S.fr(f3['premier_tiers_tendance_negative'].get('moyenne_pct'), 2)} % ({f3['premier_tiers_tendance_negative'].get('n', 0)} cas). "
          f"Rendement absolu à 3 mois : {S.fr(f3['absolu_tendance_positive'].get('moyenne_pct'), 2)} % en tendance positive, "
          f"{S.fr(f3['absolu_tendance_negative'].get('moyenne_pct'), 2)} % sinon.", "",
          "**Excès** (tendances fortes ; écart de rendement relatif à 3 mois, actifs en excès − autres) :", "",
          "| Critère | Seuil | Cas (appr. / vérif.) | Écart appr. % | Écart vérif. % |", "|---|---|---|---|---|"]
    for nom in ("parabolique", "valorisation", "positionnement"):
        e = r["exces"].get(nom)
        if not e:
            continue
        for s, d in e["seuils"].items():
            x = d["3m"]
            marque = " ✔" if s == e["retenu"] and e["confirme"] else (" (retenu, non confirmé)" if s == e["retenu"] else "")
            L.append(f"| {nom} | {s}{marque} | {x['exces'].get('n_apprentissage', 0)} / {x['exces'].get('n_verification', 0)} | "
                     f"{S.fr(x['ecart_apprentissage_pct'], 2)} | {S.fr(x['ecart_verification_pct'], 2)} |")
    p = r["poche"]
    L += ["", f"**Poche « tendance »** ({p['lignes']} lignes au plus, frais {S.fr(p['frais_ordre_pct'], 2, False)} % par ordre) :", "",
          "| Momentum | Variante | Rendement annuel % (appr. / vérif.) | Sharpe (appr. / vérif.) | Perte max % (appr. / vérif.) | Ordres par an |",
          "|---|---|---|---|---|---|"]
    for v in p["variantes"]:
        a, b = v["apprentissage"], v["verification"]
        ret = p["retenue"] and v["definition"] == p["retenue"]["definition"] and v["variante"] == p["retenue"]["variante"]
        L.append(f"| {v['definition']} | {v['variante']}{' (retenue)' if ret else ''} | {S.fr(a.get('rendement_annuel_pct'), 1)} / {S.fr(b.get('rendement_annuel_pct'), 1)}"
                 f" | {S.fr(a.get('sharpe'), 2)} / {S.fr(b.get('sharpe'), 2)} | {S.fr(a.get('perte_max_pct'), 1)} / {S.fr(b.get('perte_max_pct'), 1)}"
                 f" | {S.fr(v['operations_par_an'], 0, False)} |")
    for nom, x in p["references"].items():
        a, b = x["apprentissage"], x["verification"]
        L.append(f"| — | {'Univers équipondéré' if nom == 'univers_equipondere' else 'Indice mondial (ACWI)'} | {S.fr(a.get('rendement_annuel_pct'), 1)} / {S.fr(b.get('rendement_annuel_pct'), 1)}"
                 f" | {S.fr(a.get('sharpe'), 2)} / {S.fr(b.get('sharpe'), 2)} | {S.fr(a.get('perte_max_pct'), 1)} / {S.fr(b.get('perte_max_pct'), 1)} | — |")
    return L
