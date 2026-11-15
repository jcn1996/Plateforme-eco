"""
Sélections issues du backtest, publiées dans data/chef.json (« selections ») et utilisées par l'agent trader et l'écran
« Où investir ». Rapport de référence : le dernier recalibrage validé (data/backtest/recalibrages.json, voir
agents/commun/methode.py), jamais un nom de rapport écrit en dur. Les listes de combinaisons (config.json → selections)
sont entretenues chaque mois par le backtest (agents/backtest/entretien.py), sous validation humaine.

1. Entreprises : sociétés retenues par au moins une des combinaisons en service. Un actif est retenu par
   une combinaison s'il est dans les meilleurs 30 % (percentile > 70 dans l'univers) sur CHACUN de ses signaux. Univers :
   celui du backtest (sociétés américaines non financières, hors immobilier et holdings, capitalisation ≥ 2 Md$), notes
   de l'agent entreprises (mêmes barèmes que dans le backtest).
2. Matières premières : celles retenues par les combinaisons en service (au départ « Niveau historique + Positionnement
   CFTC » ; contrats à terme suivis par l'agent matières premières, sous-notes de l'agent).
3. Paris pays : ETF pays en tendance haussière et saine (suivi de tendance existant : performance 12 mois hors dernier
   mois positive et cours au-dessus de la moyenne 200 jours, sans excès) dont la valorisation relative n'est pas tendue.
   Sortie dès qu'un critère d'excès du rapport se déclenche (accélération parabolique ≥ 2,5 fois la volatilité mensuelle,
   valorisation au-delà du 70e percentile, positionnement au 90e percentile) ou que la tendance casse.
Les notes et verdicts pays restent publiés, comme contexte économique : le backtest les juge non prédictifs, ils ne
servent plus à classer les pays dans « Où investir ».
"""
from __future__ import annotations

from pathlib import Path

from ..commun import methode as M
from ..commun.sortie import lire_json
from .moteur import ent, fr


LIBELLES = {"mscore": "M-score", "goodwill_actif": "goodwill / actif", "fcf_yield": "rendement du FCF", "conversion_cash": "conversion en cash",
            "niveau": "niveau historique", "positionnement": "positionnement CFTC"}


def percentiles(valeurs: dict[str, float]) -> dict[str, float]:
    """Percentile (0–100) de chaque actif dans l'univers, rangs moyens pour les égalités (comme le backtest)."""
    tri = sorted(valeurs.values())
    n = len(tri)
    res = {}
    for k, v in valeurs.items():
        inf = sum(1 for x in tri if x < v)
        eg = sum(1 for x in tri if x == v)
        res[k] = 100 * (inf + (eg + 1) / 2) / n  # rang moyen ÷ n, comme pandas rank(pct=True)
    return res


def retenir(notes: dict[str, dict[str, float]], combinaisons: list[dict], seuil: float) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """notes = {actif: {signal: note}}. Renvoie ({actif: [combinaisons qui le retiennent]}, {signal: {actif: percentile}})."""
    signaux = sorted({s for c in combinaisons for s in c["signaux"]})
    pct = {s: percentiles({a: n[s] for a, n in notes.items() if n.get(s) is not None}) for s in signaux}
    retenus: dict[str, list[str]] = {}
    for c in combinaisons:
        for a in notes:
            if all(pct[s].get(a) is not None and pct[s][a] > seuil for s in c["signaux"]):
                retenus.setdefault(a, []).append(c["cle"])
    return retenus, pct


# ------------------------------------------------------------------ entreprises

def notes_entreprise(fiche: dict, signaux: list[str]) -> dict[str, float]:
    ind = dict(fiche.get("indicateurs") or {})
    ind.update(((fiche.get("analyse_financiere") or {}).get("indicateurs")) or {})
    return {s: float(ind[s]["note"]) for s in signaux if isinstance(ind.get(s), dict) and ind[s].get("note") is not None}


def univers_entreprises(ctx, cfg: dict) -> list[dict]:
    ce = cfg["entreprises"]
    res = []
    for e in ctx.entreprises:
        if not isinstance(e, dict) or e.get("pays") not in ce["pays"] or e.get("financier") or e.get("holding"):
            continue
        if e.get("secteur_gics") in ce["secteurs_exclus"] or (e.get("capitalisation_md") or 0) < ce["capitalisation_min_md"]:
            continue
        res.append(e)
    return res


def entreprises(ctx, config: dict) -> dict:
    cfg = config["selections"]
    combis = cfg["entreprises"]["combinaisons"]
    signaux = sorted({s for c in combis for s in c["signaux"]})
    univers = univers_entreprises(ctx, cfg)
    notes, infos = {}, {}
    for e in univers:
        n = notes_entreprise(ctx.fiche(e["ticker"]), signaux)
        if n:
            notes[e["ticker"]], infos[e["ticker"]] = n, e
    retenus, pct = retenir(notes, combis, cfg["seuil_percentile"])
    libelles = {c["cle"]: c["libelle"] for c in combis}
    lignes = []
    for t, cles in retenus.items():
        e = infos[t]
        sig = sorted({s for c in combis if c["cle"] in cles for s in c["signaux"]})
        lignes.append({"id": f"selection-{t}", "type": "entreprises", "ticker": t, "symbole": t, "nom": e.get("nom") or t, "pays": e.get("pays"),
                       "secteur": e.get("secteur_gics"), "secteur_nom": e.get("secteur_nom") or e.get("secteur_gics"), "devise": e.get("devise") or "USD",
                       "capitalisation_md": e.get("capitalisation_md"), "combinaisons": cles, "combinaisons_libelles": [libelles[c] for c in cles],
                       "percentiles": {s: round(pct[s][t], 1) for s in sig}, "notes": {s: notes[t][s] for s in sig},
                       "score": round(sum(pct[s][t] for s in sig) / len(sig), 1),
                       "texte": " ; ".join(f"{libelles[c]}" for c in cles) + " — " + ", ".join(f"{LIBELLES.get(s, s)} {ent(pct[s][t])}e percentile" for s in sig)})
    lignes.sort(key=lambda x: (-len(x["combinaisons"]), -x["score"], x["ticker"]))
    return {"univers": len(univers), "notees": len(notes),
            "combinaisons": [{**c, "retenues": sum(1 for x in lignes if c["cle"] in x["combinaisons"])} for c in combis],
            "retenues": lignes}


# ------------------------------------------------------------------ matières premières

def matieres(ctx, config: dict) -> dict:
    cfg = config["selections"]
    combis = cfg["matieres"]["combinaisons"]
    signaux = sorted({s for c in combis for s in c["signaux"]})
    notes, infos = {}, {}
    for m in ctx.mp.get("matieres") or []:
        if not str(m.get("symbole") or "").endswith("=F"):  # univers du backtest : contrats à terme
            continue
        sn = m.get("sous_notes") or {}
        n = {s: float(sn[s]["note"]) for s in signaux if isinstance(sn.get(s), dict) and sn[s].get("note") is not None}
        if n:
            notes[m["cle"]], infos[m["cle"]] = n, m
    retenus, pct = retenir(notes, combis, cfg["seuil_percentile"])
    libelles = {c["cle"]: c["libelle"] for c in combis}
    lignes = []
    for cle, cles in retenus.items():
        m = infos[cle]
        sig = sorted({s for c in combis if c["cle"] in cles for s in c["signaux"]})
        lignes.append({"id": "or" if cle == "or" else f"matiere-{cle}", "type": "or" if cle == "or" else "matieres", "cle": cle,
                       "nom": m.get("nom") or cle, "symbole": m.get("symbole"), "combinaisons": cles,
                       "combinaisons_libelles": [libelles[c] for c in cles], "percentiles": {s: round(pct[s][cle], 1) for s in sig},
                       "notes": {s: notes[cle][s] for s in sig}, "score": round(sum(pct[s][cle] for s in sig) / len(sig), 1),
                       "texte": ", ".join(f"{LIBELLES.get(s, s)} {ent(pct[s][cle])}e percentile" for s in sig)})
    lignes.sort(key=lambda x: (-x["score"], x["cle"]))
    return {"univers": len(notes), "combinaisons": [{**c, "retenues": len(lignes)} for c in combis], "retenues": lignes}


# ------------------------------------------------------------------ paris pays

def evaluer_pays(o: dict, config: dict) -> dict:
    """Entrée possible ? Sortie imposée ? (seuils d'excès du rapport, lus dans le bloc « suivi_tendance »)."""
    ct = config["suivi_tendance"]
    st = o.get("suivi_tendance") or {}
    val = (o.get("familles") or {}).get("valorisation")
    vnote = None if val is None else val.get("note_absolue", val.get("note"))
    exces = []
    if vnote is not None and vnote <= 100 - ct["valorisation_percentile"]:
        exces.append(f"valorisation tendue ({ent(vnote)}/100 : au-delà du {ct['valorisation_percentile']}e percentile)")
    a = st.get("acceleration")
    if a is not None and a >= ct["parabole_k"]:
        exces.append(f"accélération parabolique ({fr(st.get('perf_1m'), 1, True)} % sur 1 mois, {fr(a, 1)} fois la volatilité mensuelle ; "
                     f"seuil {fr(ct['parabole_k'], 1)})")
    pc = ((o.get("familles") or {}).get("flux") or {}).get("percentile_cftc")
    if pc is not None and pc >= ct["cftc_percentile"]:
        exces.append(f"positionnement encombré ({ent(pc)}e percentile ; seuil {ct['cftc_percentile']})")
    mesuree = bool(st) and st.get("perf_12_1") is not None
    positive = bool(st.get("positive"))
    refus, sortie = list(exces), list(exces)
    if not mesuree:
        refus.append("tendance non mesurable (historique de l'ETF insuffisant)")
    elif not positive:
        cassee = (f"tendance cassée : 12 mois hors dernier mois {fr(st.get('perf_12_1'), 1, True)} %, cours "
                  f"{'au-dessus' if st.get('au_dessus_mm200') else 'sous'} la moyenne 200 jours")
        refus.append(cassee)
        sortie.append(cassee)
    if vnote is None:
        refus.append("valorisation relative non disponible")
    return {"id": o["id"], "cle": o.get("cle"), "nom": o.get("nom"), "symbole": o.get("symbole"), "entree_ok": not refus, "sortie": bool(sortie),
            "raisons_refus": refus, "raisons_sortie": sortie, "force_relative": st.get("force_relative"), "perf_12_1": st.get("perf_12_1"),
            "valorisation_note": None if vnote is None else round(vnote, 1), "acceleration": a, "tendance": st.get("texte"),
            "mm200": st.get("mm200"), "cours": st.get("cours")}


def symboles_detenus(data: Path) -> set[str]:
    """ETF pays détenus comme paris pays par le portefeuille démo (dernière sortie de l'agent trader ; les ETF pays de
    l'ancienne méthode, vendus au changement de méthode, ne sont pas des paris)."""
    pf = (lire_json(data / "portefeuille.json") or {}).get("donnees") or {}
    return {p["symbole"] for p in pf.get("positions") or [] if p.get("poche") == "pays"}


def paris_pays(pays: list[dict], config: dict, detenus: set[str]) -> dict:
    ev = [evaluer_pays(o, config) for o in pays if o.get("symbole")]
    for e in ev:
        e["detenu"] = e["symbole"] in detenus
    cands = sorted((e for e in ev if e["entree_ok"]), key=lambda e: -(e["force_relative"] or 0))
    a_revendre = [e for e in ev if e["detenu"] and e["sortie"]]
    return {"regle": ("Entrée : tendance haussière et saine (12 mois hors dernier mois positive, cours au-dessus de la moyenne 200 jours, "
                      "aucun excès) et valorisation relative non tendue. Sortie dès qu'un excès se déclenche (accélération parabolique ≥ 2,5, "
                      "valorisation ≥ 70e percentile, positionnement ≥ 90e percentile) ou que la tendance casse."),
            "candidats": cands, "a_revendre": a_revendre, "detenus": [e for e in ev if e["detenu"]],
            "evaluation": sorted(ev, key=lambda e: (not e["entree_ok"], -(e["force_relative"] or 0)))}


def construire(ctx, pays: list[dict], config: dict, data: Path, jour: str) -> dict:
    cfg = config["selections"]
    valide = M.dernier_valide(data)
    return {"date": jour, "source": valide["rapport"] if valide else None,
            "recalibrage_valide": {k: valide.get(k) for k in ("mois", "texte", "pull_request", "valide_le")} if valide else None,
            "seuil_percentile": cfg["seuil_percentile"],
            "methode": cfg["_commentaire"], "entreprises": entreprises(ctx, config), "matieres": matieres(ctx, config),
            "paris_pays": paris_pays(pays, config, symboles_detenus(data)), "mention_pays": cfg["mention_pays"]}
