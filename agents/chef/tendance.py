"""
Suivi de tendance (momentum) du chef d'orchestre : se laisser porter par ce qui marche.

- Tendance positive : performance sur 12 mois hors dernier mois (« 12-1 ») positive ET cours au-dessus de sa moyenne
  mobile 200 jours.
- Force relative : percentile de la performance 12-1 dans la catégorie (pays, matières premières et or, entreprises,
  secteurs).
- Tendance forte : tendance positive et force relative dans le premier tiers.
- Une tendance forte n'est pénalisée que si elle s'accompagne d'au moins un excès : valorisation tendue, positionnement
  encombré (CFTC ou flux des ETF extrêmes) ou accélération parabolique (hausse sur 1 mois très supérieure à la
  volatilité mensuelle habituelle). Sinon, elle compte comme un signal positif.

Seuils : agents/chef/config.json (bloc « suivi_tendance »), fixés par le backtest (data/backtest/tendance-2026-11.md).
Cours : ETF pays (data/cours/etf-pays.json), séries des matières premières (data/matieres_premieres.json), cours
hebdomadaires des fiches entreprises, ETF sectoriels (Yahoo Finance, déjà lus pour les secteurs).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import mean, stdev

from ..commun.sortie import lire_json
from .moteur import ent, fr

CATEGORIE = {"pays": "pays", "matieres": "matieres", "or": "matieres", "entreprises": "entreprises", "secteurs": "secteurs"}
LIBELLE_CATEGORIE = {"pays": "pays", "matieres": "matières premières", "entreprises": "entreprises", "secteurs": "secteurs"}


# ------------------------------------------------------------------ cours

def _points(serie) -> list[tuple[date, float]]:
    res = []
    for p in serie or []:
        try:
            d = date.fromisoformat(str(p[0])[:10])
            v = float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if v > 0 and not math.isnan(v):
            res.append((d, v))
    res.sort()
    return res


def series_locales(ctx, data) -> dict[str, list]:
    """Séries de cours déjà produites par les autres agents, par symbole."""
    res = {}
    etf = (lire_json(data / "cours" / "etf-pays.json") or {}).get("donnees") or {}
    for s, pts in etf.items():
        if isinstance(pts, list):
            res[s] = pts
    for m in ctx.mp.get("matieres") or []:
        if m.get("symbole") and m.get("serie"):
            res[m["symbole"]] = m["serie"]
    return res


def serie_entreprise(ctx, ticker: str) -> list:
    return (ctx.fiche(ticker) or {}).get("cours_hebdo") or []


def _cours_au(pts: list[tuple[date, float]], jour: date) -> float | None:
    """Dernier cours connu au plus tard à `jour` (None si la série commence après)."""
    v = None
    for d, x in pts:
        if d > jour:
            break
        v = x
    return v


def mesures(serie, config: dict) -> dict | None:
    """Performance 12-1, performance 1 mois, moyenne 200 jours, volatilité mensuelle habituelle, plus haut 12 mois.
    Fonctionne sur une série quotidienne ou hebdomadaire (fenêtres en jours calendaires)."""
    ct = config["suivi_tendance"]
    pts = _points(serie)
    if len(pts) < 20:
        return None
    fin, cours = pts[-1]
    if (pts[0][0] - (fin - timedelta(days=365))).days > ct["tolerance_jours"]:
        return None  # moins de 12 mois d'historique
    p1 = _cours_au(pts, fin - timedelta(days=30))
    p12 = _cours_au(pts, fin - timedelta(days=365)) or pts[0][1]
    fen = [x for d, x in pts if d > fin - timedelta(days=ct["mm_jours_calendaires"])]
    mm = mean(fen) if len(fen) >= 10 else None
    mensuels = [_cours_au(pts, fin - timedelta(days=round(30.44 * k))) for k in range(1, 14)]
    r = [a / b - 1 for a, b in zip(mensuels[:-1], mensuels[1:]) if a and b]
    vol = stdev(r) * 100 if len(r) >= 9 else None
    perf_1m = (cours / p1 - 1) * 100 if p1 else None
    haut = max(x for d, x in pts if d > fin - timedelta(days=365))
    return {"date": fin.isoformat(), "cours": round(cours, 4), "perf_12_1": round((p1 / p12 - 1) * 100, 2) if p1 and p12 else None,
            "perf_1m": None if perf_1m is None else round(perf_1m, 2), "mm200": None if mm is None else round(mm, 4),
            "au_dessus_mm200": None if mm is None else cours > mm, "vol_mensuelle": None if vol is None else round(vol, 2),
            "acceleration": round(perf_1m / vol, 2) if perf_1m is not None and vol else None,
            "plus_haut_12m": round(haut, 4)}


# ------------------------------------------------------------------ force relative et excès

def preparer(opps: list[dict], series: dict, config: dict, ctx=None) -> None:
    """Calcule le suivi de tendance de chaque opportunité (o["suivi_tendance"]) et la force relative dans sa catégorie.
    À appeler avant le score : une tendance forte sans excès relève la note de tendance à un plancher (signal positif)."""
    ct = config["suivi_tendance"]
    par_cat: dict[str, list[dict]] = {}
    for o in opps:
        cat = CATEGORIE.get(o["type"])
        if not cat:
            continue
        s = series.get(o.get("symbole"))
        if not s and o["type"] == "entreprises" and ctx is not None:
            s = serie_entreprise(ctx, o.get("cle") or o.get("symbole"))
        m = mesures(s, config) if s else None
        if not m or m["perf_12_1"] is None:
            continue
        o["suivi_tendance"] = m | {"categorie": cat}
        par_cat.setdefault(cat, []).append(o)
    for cat, l in par_cat.items():
        vals = sorted(o["suivi_tendance"]["perf_12_1"] for o in l)
        n = len(vals)
        for o in l:
            st = o["suivi_tendance"]
            v = st["perf_12_1"]
            if n >= ct["actifs_min"]:
                inf = sum(1 for x in vals if x < v)
                eg = sum(1 for x in vals if x == v)
                st["force_relative"] = round(100 * (inf + 0.5 * eg) / n, 1)
                st["rang"] = n - inf - eg + 1
                st["sur"] = n
            else:
                st["force_relative"] = None
            evaluer(o, config)


def exces(o: dict, config: dict) -> list[str]:
    """Excès qui rendent une forte hausse pénalisante (seuils du backtest)."""
    ct = config["suivi_tendance"]
    st = o["suivi_tendance"]
    res = []
    val = o["familles"].get("valorisation")
    if val is not None:
        note = val.get("note_absolue", val["note"])
        if note is not None and note <= 100 - ct["valorisation_percentile"]:
            res.append(f"valorisation tendue ({ent(note)}/100, au-delà du {ct['valorisation_percentile']}e percentile) : {val['texte']}")
    fl = o["familles"].get("flux")
    if fl is not None:
        pc = fl.get("percentile_cftc")
        if pc is not None and pc >= ct["cftc_percentile"]:
            res.append(f"positionnement encombré : gérants au {ent(pc)}e percentile de leur position nette sur 3 ans (CFTC ; seuil {ct['cftc_percentile']})")
        elif o["type"] in ("pays", "secteurs") and fl.get("note_absolue", fl["note"]) is not None \
                and fl.get("note_absolue", fl["note"]) >= ct["flux_note_extreme"]:
            res.append(f"flux des ETF extrêmes ({ent(fl.get('note_absolue', fl['note']))}/100, seuil {ct['flux_note_extreme']}) : {fl['texte']}")
    a = st.get("acceleration")
    if a is not None and a > ct["parabole_k"]:
        res.append(f"accélération parabolique : {fr(st['perf_1m'], 1, True)} % sur 1 mois, soit {fr(a, 1)} fois la volatilité mensuelle "
                   f"habituelle ({fr(st['vol_mensuelle'], 1)} % ; seuil {fr(ct['parabole_k'], 1)})")
    return res


def evaluer(o: dict, config: dict) -> None:
    ct = config["suivi_tendance"]
    st = o["suivi_tendance"]
    st["positive"] = bool(st["perf_12_1"] > 0 and st.get("au_dessus_mm200"))
    fr_ = st.get("force_relative")
    st["forte"] = bool(st["positive"] and fr_ is not None and fr_ >= ct["premier_tiers"])
    st["exces"] = exces(o, config) if st["forte"] else []
    st["invalidation"] = {"mm200": st.get("mm200"),
                          "stop_suiveur": round(st["plus_haut_12m"] * (1 - ct["stop_suiveur_pct"] / 100), 4),
                          "ecart_mm200_pct": round((st["cours"] / st["mm200"] - 1) * 100, 1) if st.get("mm200") else None}
    o["tendance_forte"] = st["forte"] and not st["exces"]
    o["tendance_excessive"] = st["forte"] and bool(st["exces"])
    t = o["familles"].get("tendance")
    texte = (f"12 mois hors dernier mois {fr(st['perf_12_1'], 1, True)} %, cours {'au-dessus' if st.get('au_dessus_mm200') else 'en dessous'} "
             f"de la moyenne 200 jours" + (f", force relative {ent(fr_)}e percentile des {LIBELLE_CATEGORIE[st['categorie']]} ({st['rang']}e sur {st['sur']})"
                                            if fr_ is not None else ""))
    st["texte"] = texte
    if t is not None and o["tendance_forte"] and t["note"] < ct["note_plancher_forte"]:
        t["note_avant_tendance"] = t["note"]
        t["note"] = float(ct["note_plancher_forte"])  # tendance forte sans excès : signal positif
        t["texte"] = f"{t['texte']} ; tendance forte et intacte ({texte})"
    elif t is not None:
        t["texte"] = f"{t['texte']} ; {texte}"


def verifier(o: dict, jour: str, config: dict) -> dict | None:
    """Objection sérieuse seulement pour une tendance forte accompagnée d'au moins un excès."""
    st = o.get("suivi_tendance") or {}
    if not o.get("tendance_excessive"):
        return None
    return {"objection": "Tendance forte mais en excès : " + " ; ".join(st["exces"]) + ". La hausse peut se poursuivre, mais le risque "
                         "de retournement est plus élevé que pour une tendance saine.",
            "ajustement": "abaisser", "signal": "Suivi de tendance (excès, règle du chef d'orchestre)", "date": jour,
            "methode": "suivi de tendance", "serieuse": True}


# ------------------------------------------------------------------ rubrique « Tendances fortes »

def tendances_fortes(lignes: list[dict], config: dict) -> list[dict]:
    """Actifs en tête de force relative dont la tendance est intacte, avec le niveau qui invaliderait la tendance."""
    ct = config["suivi_tendance"]
    res = []
    for l in lignes:
        st = l.get("suivi_tendance") or {}
        if not st.get("forte"):
            continue
        inv = st.get("invalidation") or {}
        niveau = inv.get("mm200") or inv.get("stop_suiveur")
        res.append({"id": l["id"], "type": l["type"], "nom": l["nom"], "symbole": l.get("symbole"), "categorie": st["categorie"],
                    "verdict": l.get("verdict"), "score": l.get("score"), "perf_12_1": st["perf_12_1"], "perf_1m": st.get("perf_1m"),
                    "force_relative": st.get("force_relative"), "rang": st.get("rang"), "sur": st.get("sur"), "cours": st["cours"],
                    "date": st["date"], "mm200": st.get("mm200"), "stop_suiveur": inv.get("stop_suiveur"), "niveau_invalidation": niveau,
                    "distance_invalidation_pct": round((st["cours"] / niveau - 1) * 100, 1) if niveau else None,
                    "exces": st.get("exces") or [], "saine": not st.get("exces")})
    res.sort(key=lambda x: (not x["saine"], -(x["force_relative"] or 0), -(x["perf_12_1"] or 0)))
    par_cat: dict[str, int] = {}
    garde = []
    for x in res:
        if par_cat.get(x["categorie"], 0) >= ct["rubrique_par_categorie"]:
            continue
        par_cat[x["categorie"]] = par_cat.get(x["categorie"], 0) + 1
        garde.append(x)
    return garde
