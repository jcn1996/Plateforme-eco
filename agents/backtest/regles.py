"""
Règles du chef d'orchestre et du trader, rejouées mois par mois avec leurs propres fonctions
(agents/chef/moteur.py) sur les familles reconstituables des pays : fondamentaux (moyenne des notes
croissance, indicateur avancé, inflation, taux réel), valorisation, tendance, cycle (phase du pays).
Les familles sans historique sont retirées et les poids renormalisés (comme quand une famille manque).

Tests : pondérations (score du chef contre familles seules et équipondération), seuils des verdicts,
niveaux de conviction et nombre de groupes concordants, règle anti-euphorie (momentum extrême),
concentration du portefeuille (nombre de lignes, plafond par ligne), stops et prise de bénéfices du trader.
"""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd

from ..chef import moteur as M
from ..chef import tendance as TD
from . import stats as S
from .secteurs import phases as phases_cycle

FAMILLES_RECONSTITUEES = ("fondamentaux", "valorisation", "tendance", "cycle")
FONDAMENTAUX = ("croissance_pib", "indicateur_avance", "inflation", "taux_reel")
PALIER = {"calme": "Calme", "tension": "Tension"}


def config_backtest(cfg_chef: dict) -> dict:
    c = copy.deepcopy(cfg_chef)
    c["poids"]["pays"] = {f: w for f, w in c["poids"]["pays"].items() if f in FAMILLES_RECONSTITUEES}
    return c


def familles_pays(lot: dict, cfg_chef: dict, cfg_macro: dict) -> dict[str, pd.DataFrame]:
    """Notes absolues des familles, par pays et par mois."""
    n = lot["notes"]
    mois, cols = lot["mois"], lot["prix"].columns
    fond = pd.concat([n[k].reindex(index=mois, columns=cols) for k in FONDAMENTAUX if k in n]).groupby(level=0).mean()
    cycle = pd.DataFrame(np.nan, index=mois, columns=cols)
    table = cfg_chef["cycle"]["phases"]
    v = lot["valeurs"]
    for c in cols:
        if c in v["indicateur_avance"] and c in v["inflation"]:
            ph = phases_cycle(v["indicateur_avance"][c], v["inflation"][c], mois, cfg_macro["seuils"])
            cycle[c] = [np.nan if p is None else (table.get(p) or {}).get("actions", np.nan) for p in ph]
    return {"fondamentaux": fond.reindex(index=mois, columns=cols), "valorisation": n["valorisation"], "tendance": n["momentum"],
            "cycle": cycle}


def melanger_percentile(abs_: pd.DataFrame, cfg_chef: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score de famille = poids_percentile × percentile dans la classe + (1 − poids) × note absolue (classe ≥ taille_min)."""
    p = cfg_chef["percentiles"]
    pct = S.percentile_transversal(abs_)
    grande = abs_.notna().sum(axis=1) >= p["taille_min"]
    mix = abs_.copy()
    mix[grande] = (p["poids_percentile"] * pct + (1 - p["poids_percentile"]) * abs_)[grande]
    return mix, pct


def rejouer_chef(lot: dict, cfg_chef: dict, cfg_macro: dict, regimes: pd.Series | None) -> dict:
    """Score, verdict, conviction et suivi de tendance du chef d'orchestre, pour chaque pays et chaque mois. Tendance
    reconstituée sur les cours mensuels de l'ETF : 12-1, moyenne 10 mois (≈ 200 jours), accélération sur 1 mois."""
    cfg = config_backtest(cfg_chef)
    abs_ = familles_pays(lot, cfg_chef, cfg_macro)
    mix, pct = {}, {}
    for f, df in abs_.items():
        if f == "cycle":
            mix[f], pct[f] = df, None
        else:
            mix[f], pct[f] = melanger_percentile(df, cfg_chef)
    mois, cols = lot["mois"], lot["prix"].columns
    hausse = lot["valeurs"]["momentum"].reindex(index=mois, columns=cols)
    px = lot["prix"].reindex(columns=cols)
    p12_1 = (px.shift(1) / px.shift(12) - 1) * 100
    mm10 = px.rolling(10, min_periods=10).mean()
    r1 = px.pct_change(fill_method=None)
    accel = r1 / r1.shift(1).rolling(12, min_periods=9).std().replace(0, np.nan)
    rs = p12_1.rank(axis=1, pct=True) * 100
    sortie = {k: pd.DataFrame(np.nan if k == "score" else None, index=mois, columns=cols, dtype=float if k == "score" else object)
              for k in ("score", "verdict", "conviction", "excessive", "forte", "groupes")}
    paliers = {}
    for t in mois:
        palier = PALIER.get(regimes.get(t)) if regimes is not None else None
        palier = palier or "Vigilance"
        paliers[t] = palier
        for c in cols:
            fams = {}
            for f in FAMILLES_RECONSTITUEES:
                x = mix[f].at[t, c] if c in mix[f] else np.nan
                if pd.isna(x):
                    continue
                fams[f] = {"note": float(x), "note_absolue": float(abs_[f].at[t, c]), "coef": 1.0, "texte": f}
                if f == "tendance":
                    fams[f]["percentile_classe"] = None if pct[f] is None or pd.isna(pct[f].at[t, c]) else float(pct[f].at[t, c])
                    fams[f]["hausse_12m"] = None if pd.isna(hausse.at[t, c]) else float(hausse.at[t, c])
            if len(fams) < 2:
                continue
            o = {"type": "pays", "familles": fams}
            if not pd.isna(p12_1.at[t, c]) and not pd.isna(mm10.at[t, c]):
                n_rs = int(rs.loc[t].notna().sum())
                o["suivi_tendance"] = {"categorie": "pays", "perf_12_1": float(p12_1.at[t, c]), "cours": float(px.at[t, c]),
                                       "mm200": float(mm10.at[t, c]), "au_dessus_mm200": bool(px.at[t, c] > mm10.at[t, c]),
                                       "perf_1m": float(r1.at[t, c] * 100) if not pd.isna(r1.at[t, c]) else None,
                                       "acceleration": None if pd.isna(accel.at[t, c]) else float(accel.at[t, c]),
                                       "vol_mensuelle": None, "plus_haut_12m": float(px[c].loc[:t].iloc[-12:].max()),
                                       "force_relative": float(rs.at[t, c]) if n_rs >= cfg["suivi_tendance"]["actifs_min"] else None,
                                       "rang": None, "sur": n_rs}
                TD.evaluer(o, cfg)
            M.scorer(o, cfg, palier)
            objection = TD.verifier(o, t.strftime("%Y-%m-%d"), cfg)
            v = M.verdict_de(o["score"], cfg)
            v, _ = M.exiger_moteur(o, v, cfg)
            conv = M.conviction(o, v, [objection] if objection else [], 1.0, cfg)
            v, _ = M.plafonner_extreme(v, conv, cfg)
            sortie["score"].at[t, c] = o["score"]
            sortie["verdict"].at[t, c] = v
            sortie["conviction"].at[t, c] = conv["niveau"]
            sortie["excessive"].at[t, c] = bool(o.get("tendance_excessive"))
            sortie["forte"].at[t, c] = bool(o.get("tendance_forte"))
            sortie["groupes"].at[t, c] = len(conv["groupes"])
    sortie["familles"] = mix
    sortie["familles_absolues"] = abs_
    sortie["paliers"] = pd.Series(paliers)
    return sortie


def score_avec_poids(familles: dict[str, pd.DataFrame], paliers: pd.Series, cfg_chef: dict, poids: dict) -> pd.DataFrame:
    """Score du chef pour d'autres poids de base (multiplicateurs de régime appliqués), pour le recalibrage."""
    tot = num = None
    for f, w in poids.items():
        if f not in familles or not w:
            continue
        mult = paliers.map(lambda p: (cfg_chef["regimes"].get(p) or {}).get(f, 1.0)).astype(float)
        df = familles[f]
        ww = df.notna().mul(mult * w, axis=0)
        num = df.fillna(0).mul(mult * w, axis=0) if num is None else num + df.fillna(0).mul(mult * w, axis=0)
        tot = ww if tot is None else tot + ww
    return num / tot.replace(0, np.nan)


# ------------------------------------------------------------------ tests des verdicts et de la conviction

def _relatif(prix: pd.DataFrame, indice: pd.Series | None, h: int) -> pd.DataFrame:
    fut = S.rendements_futurs(prix, h)
    b = S.rendements_futurs(indice, h).reindex(prix.index) if indice is not None else fut.mean(axis=1)
    return fut.sub(b, axis=0) * 100


def _valeurs(df: pd.DataFrame, masque: pd.DataFrame) -> pd.Series:
    """Valeurs de df là où le masque est vrai (une ligne par actif et par date)."""
    x = df.where(masque.astype(bool)).stack()
    return x.dropna()


def _tableau(cle: pd.DataFrame, rel: pd.DataFrame, fut_abs: pd.DataFrame, ordre: list[str], reussite) -> dict:
    res = {}
    for v in ordre:
        masque = (cle == v) & rel.notna()
        x = _valeurs(rel, masque)
        if not len(x):
            res[v] = {"n": 0}
            continue
        a = _valeurs(fut_abs, masque).reindex(x.index)
        res[v] = {"n": int(len(x)), "relative_moyenne_pct": S._r(x.mean(), 2), "relative_mediane_pct": S._r(x.median(), 2),
                  "reussite_pct": S._r(100 * reussite(v, x, a).mean(), 1)}
    return res


def _reussite_verdict(v, rel, abs_):
    if v in ("Renforcer", "Renforcer fortement"):
        return rel > 0
    if v in ("Alléger", "Éviter"):
        return rel < 0
    return rel.abs() <= 5


def tester_verdicts(chef: dict, prix: pd.DataFrame, indice: pd.Series | None, horizons: list[int], cfg_chef: dict,
                    separation: pd.Timestamp) -> dict:
    ordre = list(reversed(cfg_chef["verdicts"]["ordre"]))
    res = {"par_verdict": {}, "par_conviction": {}, "par_groupes": {}, "seuils": cfg_chef["verdicts"]["seuils"],
           "groupes_forte": cfg_chef["conviction"]["groupes_forte"], "groupes_moyenne": cfg_chef["conviction"]["groupes_moyenne"]}
    positif = chef["verdict"].isin(["Renforcer", "Renforcer fortement"])
    for h in horizons:
        rel = _relatif(prix, indice, h)
        fut = S.rendements_futurs(prix, h) * 100
        res["par_verdict"][str(h)] = _tableau(chef["verdict"], rel, fut, ordre, _reussite_verdict)
        conv = chef["conviction"].where(positif)
        res["par_conviction"][str(h)] = _tableau(conv, rel, fut, ["forte", "moyenne", "faible"], lambda v, r, a: r > 0)
        g = chef["groupes"].where(positif).map(lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else f"{int(x)} groupe(s)")
        res["par_groupes"][str(h)] = _tableau(g, rel, fut, [f"{i} groupe(s)" for i in range(0, 5)], lambda v, r, a: r > 0)
    # Les verdicts sont-ils ordonnés ? (performance relative croissante d'« Éviter » à « Renforcer fortement »)
    for h, tab in res["par_verdict"].items():
        moy = [tab[v].get("relative_moyenne_pct") for v in reversed(ordre) if tab[v].get("n", 0) >= 30]
        tab["_ordonne"] = bool(len(moy) >= 3 and all(a <= b for a, b in zip(moy, moy[1:])))
    # Hors échantillon seulement, à l'horizon de référence
    return res


def tester_tendance(chef: dict, prix: pd.DataFrame, indice: pd.Series | None, horizons: list[int], cfg_chef: dict) -> dict:
    """Règle de tendance du chef d'orchestre, rejouée sur les pays : les tendances fortes saines (premier tiers de force
    relative, tendance positive, sans excès) font-elles mieux ensuite que les autres pays ? Les tendances fortes en
    excès (valorisation tendue, accélération parabolique) font-elles moins bien que les saines ?"""
    forte = chef["forte"].fillna(False).astype(bool)
    excessive = chef["excessive"].fillna(False).astype(bool)
    connu = chef["score"].notna()
    ct = cfg_chef["suivi_tendance"]
    res = {"regle": {"premier_tiers": ct["premier_tiers"], "parabole_k": ct["parabole_k"],
                     "valorisation_percentile": ct["valorisation_percentile"]}, "horizons": {}}
    for h in horizons:
        rel = _relatif(prix, indice, h)

        def bloc(m):
            x = _valeurs(rel, m & rel.notna())
            return {"n": int(len(x)), "relative_moyenne_pct": S._r(x.mean(), 2) if len(x) else None,
                    "reussite_pct": S._r(100 * (x > 0).mean(), 1) if len(x) else None}
        res["horizons"][str(h)] = {"forte_saine": bloc(forte), "forte_en_exces": bloc(excessive),
                                   "autres": bloc(connu & ~forte & ~excessive)}
    return res


# ------------------------------------------------------------------ portefeuilles (concentration)

def stats_portefeuille(r: pd.Series, rf_pct: float = 2.0) -> dict:
    r = r.dropna()
    if len(r) < 12:
        return {"mois": len(r)}
    valeur = (1 + r).cumprod()
    an = valeur.iloc[-1] ** (12 / len(r)) - 1
    vol = r.std() * math.sqrt(12)
    perte = (valeur / valeur.cummax() - 1).min()
    return {"mois": len(r), "rendement_annuel_pct": S._r(100 * an, 2), "volatilite_pct": S._r(100 * vol, 2),
            "sharpe": S._r((an - rf_pct / 100) / vol, 2) if vol else None, "perte_max_pct": S._r(100 * perte, 2)}


def tester_concentration(chef: dict, prix: pd.DataFrame, indice: pd.Series | None, cfg_trader: dict, lignes: list[int],
                         frais_pct: float, separation: pd.Timestamp) -> dict:
    """Cœur du trader : verdicts positifs de conviction moyenne ou forte, classés par conviction puis score,
    N lignes au plus, poids ∝ conviction plafonné par ligne, excédent en liquidités (non rémunérées)."""
    fut1 = S.rendements_futurs(prix, 1)
    conv_poids = cfg_trader["coeur"]["convictions"]
    plafond = cfg_trader["coeur"]["max_ligne"] / 100
    eligible = chef["verdict"].isin(["Renforcer", "Renforcer fortement"]) & chef["conviction"].isin(list(conv_poids))
    res = {"lignes": {}, "regle_actuelle": cfg_trader["coeur"]["max_lignes"], "plafond_ligne_pct": cfg_trader["coeur"]["max_ligne"]}

    def simuler(n_max):
        poids_prec = pd.Series(0.0, index=prix.columns)
        rend = {}
        for t in prix.index:
            ok = [c for c in prix.columns if eligible.at[t, c] and not pd.isna(fut1.at[t, c])]
            ok.sort(key=lambda c: (-conv_poids.get(chef["conviction"].at[t, c], 0), -chef["score"].at[t, c]))
            choisis = ok[:n_max] if n_max else ok
            w = pd.Series(0.0, index=prix.columns)
            if choisis:
                brut = pd.Series({c: conv_poids[chef["conviction"].at[t, c]] for c in choisis})
                w[choisis] = (brut / brut.sum()).clip(upper=plafond)
            if pd.isna(fut1.loc[t]).all():
                continue
            # Rotation : achats + ventes ÷ 2 par rapport aux poids de la veille (dérivés avec les cours) ;
            # l'aller-retour complet est payé sur la part renouvelée
            rot = (w - poids_prec).abs().sum() / 2
            r = fut1.loc[t].fillna(0)
            brut = float((w * r).sum())
            rend[t] = brut - rot * frais_pct / 100
            poids_prec = w * (1 + r) / (1 + brut)
        return pd.Series(rend)

    for n in lignes + [0]:
        r = simuler(n)
        cle = str(n) if n else "toutes"
        res["lignes"][cle] = {"total": stats_portefeuille(r), "apprentissage": stats_portefeuille(r[r.index <= separation]),
                              "verification": stats_portefeuille(r[r.index > separation])}
    eq = fut1.mean(axis=1).where(fut1.notna().sum(axis=1) > 0)
    res["equipondere"] = {"total": stats_portefeuille(eq), "verification": stats_portefeuille(eq[eq.index > separation])}
    if indice is not None:
        b = S.rendements_futurs(indice, 1).reindex(prix.index)
        res["indice"] = {"total": stats_portefeuille(b), "verification": stats_portefeuille(b[b.index > separation])}
    return res


# ------------------------------------------------------------------ stops et prise de bénéfices (satellites)

def simuler_position(p: np.ndarray, st: dict | None) -> tuple[float, str]:
    """Rendement d'une position achetée au premier cours de p et gardée jusqu'au dernier, avec ou sans les règles
    du trader : stop −15 %, suiveur 15 % sous le plus haut dès +20 %, déclenché après 2 relevés sous le stop,
    un tiers vendu à +30 % (une fois). Renvoie (rendement, motif de sortie)."""
    e = p[0]
    if st is None:
        return p[-1] / e - 1, "échéance"
    part, encaisse, plus_haut, sous, prise = 1.0, 0.0, e, 0, False
    for x in p[1:]:
        plus_haut = max(plus_haut, x)
        stop = e * (1 - st["stop_pct"] / 100)
        if plus_haut >= e * (1 + st["suiveur_declenchement_pct"] / 100):
            stop = max(stop, plus_haut * (1 - st["suiveur_pct"] / 100))
        if not prise and x >= e * (1 + st["prise_benefices_pct"] / 100):
            encaisse += part * st["prise_benefices_part"] * x / e
            part *= 1 - st["prise_benefices_part"]
            prise = True
        sous = sous + 1 if x < stop else 0
        if sous >= st["confirmations"]:
            return encaisse + part * x / e - 1, "stop suiveur" if stop > e * (1 - st["stop_pct"] / 100) else "stop"
    return encaisse + part * p[-1] / e - 1, "prise de bénéfices puis échéance" if prise else "échéance"


def tester_stops(note: pd.DataFrame, quotidien: pd.DataFrame, cfg_trader: dict, lignes: int, mois_detention: int,
                 frais_pct: float, separation: pd.Timestamp) -> dict:
    """Chaque mois, les `lignes` sociétés les mieux notées sont achetées et gardées `mois_detention` mois,
    avec et sans les stops du trader. Comparaison des rendements par position (frais compris)."""
    st = cfg_trader["stops"]
    lignes_res = {"avec": [], "sans": [], "motifs": {}, "dates": []}
    q = quotidien.sort_index()
    for t in note.index:
        rang = note.loc[t].dropna().sort_values(ascending=False)
        fin = t + pd.DateOffset(months=mois_detention)
        if fin > q.index[-1]:
            break
        for tk in rang.index[:lignes]:
            p = q[tk].loc[t + pd.Timedelta(days=1):fin].dropna().to_numpy()
            if len(p) < 20:
                continue
            r_sans, _ = simuler_position(p, None)
            r_avec, motif = simuler_position(p, st)
            cout_extra = frais_pct / 200 if motif != "échéance" else 0  # vente anticipée ou partielle : un ordre de plus
            lignes_res["sans"].append(r_sans - frais_pct / 100)
            lignes_res["avec"].append(r_avec - frais_pct / 100 - cout_extra)
            lignes_res["motifs"][motif] = lignes_res["motifs"].get(motif, 0) + 1
            lignes_res["dates"].append(t)

    def bloc(masque):
        a = np.array(lignes_res["avec"])[masque]
        s = np.array(lignes_res["sans"])[masque]
        if not len(a):
            return {"positions": 0}
        return {"positions": int(len(a)), "moyenne_avec_pct": S._r(100 * a.mean(), 2), "moyenne_sans_pct": S._r(100 * s.mean(), 2),
                "pire_avec_pct": S._r(100 * a.min(), 1), "pire_sans_pct": S._r(100 * s.min(), 1),
                "reussite_avec_pct": S._r(100 * (a > 0).mean(), 1), "reussite_sans_pct": S._r(100 * (s > 0).mean(), 1),
                "ecart_type_avec_pct": S._r(100 * a.std(), 1), "ecart_type_sans_pct": S._r(100 * s.std(), 1)}
    d = np.array(lignes_res["dates"], dtype="datetime64[ns]")
    sep = np.datetime64(separation)
    return {"regles": st, "lignes": lignes, "detention_mois": mois_detention, "motifs": lignes_res["motifs"],
            "total": bloc(np.ones(len(d), bool)), "apprentissage": bloc(d <= sep), "verification": bloc(d > sep)}
