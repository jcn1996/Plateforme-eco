"""
Catégorie « Secteurs » du chef d'orchestre : les 11 secteurs GICS au niveau mondial et par grande zone
(États-Unis, Europe, émergents), quand les données le permettent. Méthode : methode.md, § Secteurs.

Familles de signaux par secteur et par zone :
- fondamentaux : note médiane des sociétés du secteur (agent entreprises) ;
- valorisation : rendement des bénéfices médian (100 / PER médian) corrigé de la croissance médiane des bénéfices,
  comparé aux autres secteurs de la zone ;
- dynamique des résultats : note médiane « Dynamique des résultats » (guidance, révisions, surprises) ;
- tendance : performance sur 12 mois de l'ETF sectoriel (XLK… aux États-Unis, iShares Global… dans le monde,
  iShares STOXX Europe 600 en Europe) ; sans ETF (émergents) : momentum médian des sociétés ;
- flux : flux des ETF sectoriels, même méthode que les ETF pays (parts en circulation × VL ; émetteur, puis Yahoo) ;
- adéquation au cycle : tableau de rotation sectorielle selon la phase de l'agent macro ;
- initiés : achats de dirigeants et conviction des super-investisseurs, agrégés ;
- risque : sensibilité défensive ou cyclique selon le palier de risque ; géopolitique : exposition aux actifs cités
  par les événements récents (pétrole, gaz, défense…).
Holdings, fonds, BDC et SPAC sont exclus des agrégats. Une ligne exige au moins `societes_min` sociétés.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from ..commun.sortie import ecrire_json, lire_json
from ..entreprises.univers import GICS
from ..pays import flux_etf
from ..risque.calculs import date_fr, fr
from . import univers as U


def _med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return median(xs) if len(xs) else None


def zones_de(pays: str, cfg: dict) -> list[str]:
    return [z for z, c in cfg["zones"].items() if c["pays"] is None or pays in c["pays"]]


def agreger(ctx: "U.Contexte", cfg: dict) -> dict[tuple[str, str], list[dict]]:
    """{(zone, secteur GICS): [mesures par société]}, holdings et fonds exclus."""
    ini = (ctx.inities.get("societes") or {})
    res: dict[tuple[str, str], list[dict]] = {}
    for e in ctx.entreprises:
        g = e.get("secteur_gics")
        if not g or g not in GICS or e.get("note") is None or U.est_vehicule(ctx, e):
            continue
        f = ctx.fiche(e["ticker"])
        ind = e.get("indicateurs") or {}
        dyn = f.get("dynamique") if isinstance(f.get("dynamique"), dict) else {}
        x = ini.get(e["ticker"]) or {}
        m = {"ticker": e["ticker"], "note": e["note"], "per": (f.get("valorisation") or {}).get("per"),
             "croissance": (ind.get("croissance_benefice") or {}).get("valeur"), "momentum": (ind.get("momentum_12m") or {}).get("valeur"),
             "dynamique": dyn.get("note") if dyn and dyn.get("fiabilite") != "indicative" else None,
             "inities_pos": bool((x.get("score_achats") or 0) >= 60 or (x.get("conviction") or 0) >= 50),
             "inities_neg": bool(x.get("ventes_massives"))}
        for z in zones_de(e.get("pays"), cfg):
            res.setdefault((z, g), []).append(m)
    return res


def rendement(mes: list[dict], cv: dict) -> tuple[float | None, float | None, float | None]:
    pers = [m["per"] for m in mes if isinstance(m["per"], (int, float)) and 0 < m["per"] < 200]
    per = _med(pers)
    cr = _med([m["croissance"] for m in mes])
    if not per:
        return None, None, cr
    c = max(cv["croissance_min"], min(cv["croissance_max"], cr or 0))
    return round(100 / per + cv["poids_croissance"] * c, 2), per, cr


def perf_12m(serie: list) -> tuple[float | None, float | None, str | None]:
    """(performance sur 12 mois, sur 6 mois, date du dernier cours) d'une série [(date, clôture, …)]."""
    if not serie or len(serie) < 30:
        return None, None, None
    fin = date.fromisoformat(serie[-1][0])

    def a(jours):
        lim = (fin - timedelta(days=jours)).isoformat()
        avant = [p for p in serie if p[0] <= lim]
        return avant[-1][1] if avant else None
    c = serie[-1][1]
    p12, p6 = a(365), a(182)
    return (round((c / p12 - 1) * 100, 1) if p12 else None), (round((c / p6 - 1) * 100, 1) if p6 else None), serie[-1][0]


def expositions_geo(ctx: "U.Contexte", cfg: dict, jour: str) -> dict[str, tuple[int, list[str]]]:
    """{secteur: (somme des effets, titres)} à partir des événements géopolitiques récents."""
    cg = cfg["geopolitique"]
    lim = (date.fromisoformat(jour) - timedelta(days=cg["jours"])).isoformat()
    res = {}
    for e in ctx.geo.get("evenements") or []:
        if (e.get("gravite") or 0) < cg["gravite_min"] or (e.get("dernier") or "")[:10] < lim:
            continue
        for a in e.get("actifs") or []:
            sens = {"hausse": 1, "baisse": -1}.get(a.get("sens"))
            if not sens:
                continue
            for g, expo in cg["expositions"].items():
                eff = expo.get((a.get("actif") or "").lower())
                if eff:
                    s, titres = res.get(g, (0, []))
                    res[g] = (s + eff * sens, titres + [f"{e.get('titre')} ({a.get('actif')} en {a.get('sens')})"])
    return res


# ------------------------------------------------------------------ flux des ETF sectoriels

def flux(f, data: Path, config: dict, aujourdhui: date) -> tuple[dict, dict]:
    """{etf: indicateur de flux} et état de la source. Historique jour par jour dans data/chef/flux_secteurs/."""
    cfg_f = json.loads((U.RACINE / "agents" / "pays" / "config.json").read_text(encoding="utf-8"))["flux_etf"]
    emetteurs = config["secteurs"]["flux_emetteurs"]
    dossier = data / "chef" / "flux_secteurs"
    historique = flux_etf.lire_historique(dossier, aujourdhui, cfg_f["conservation_jours"])
    try:
        src = f.flux_secteurs(emetteurs)
        etat = {"etat": "ok", "detail": ", ".join(f"{k.removeprefix('flux_')} : {len(v or {})}" for k, v in src.items())}
    except Exception as e:  # noqa: BLE001 — sans relevé du jour, l'historique accumulé reste utilisable
        src, etat = {}, {"etat": "échec", "detail": str(e)[:200]}
    res, modifiees = {}, set()
    for etf, em in emetteurs.items():
        choix = flux_etf.choisir_releve(etf, em["emetteur"], src, cfg_f, aujourdhui)
        if choix["retenu"]:
            modifiees |= set(flux_etf.completer_historique(historique, etf, choix["retenu"], choix["verification"],
                                                           cfg_f["remplissage_jours"], aujourdhui))
        ind = flux_etf.indicateur(etf, em["emetteur"], choix, historique.get(etf, []), cfg_f, aujourdhui)
        ind["note"] = flux_etf.noter(ind, cfg_f)
        ind.pop("cumul", None)
        res[etf] = ind
    if modifiees:
        flux_etf.ecrire_historique(dossier, historique, modifiees, aujourdhui.isoformat(), "chef")
    return res, etat


# ------------------------------------------------------------------ opportunités

def opportunites(ctx: "U.Contexte", series: dict, flux_ind: dict, jour: str) -> list[dict]:
    config = ctx.config
    cfg = config["secteurs"]
    cv, cm = cfg["valorisation"], cfg["momentum"]
    agg = agreger(ctx, cfg)
    geo = expositions_geo(ctx, cfg, jour)
    ce = ctx.coef("entreprises")
    res = []
    for zone, cz in cfg["zones"].items():
        lignes = []
        rends = {g: rendement(agg.get((zone, g), []), cv) for g in GICS}
        med_rend = _med([r[0] for r in rends.values() if r[0] is not None])
        for g, (nom_fr, slug) in GICS.items():
            mes = agg.get((zone, g), [])
            if len(mes) < cfg["societes_min"]:
                continue
            etf = (cfg["etf"].get(g) or {}).get(zone)
            o = {"id": f"secteur-{zone}-{slug}", "type": "secteurs", "cle": f"{zone}:{g}", "nom": f"{nom_fr} — {cz['libelle']}",
                 "secteur": g, "secteur_nom": nom_fr, "zone_secteur": zone, "zone_libelle": cz["libelle"], "zone": cz["phase"],
                 "classe_cycle": "actions", "symbole": etf, "devise": cz["devise"] if etf else None, "indice_suivi": "secteurs",
                 "nb_societes": len(mes), "familles": {}, "themes": [], "invalidations": []}
            if etf in cfg.get("etf_europe_approche", {}):
                o["etf_approche"] = cfg["etf_europe_approche"][etf]
            src = f"agent entreprises ({len(mes)} sociétés, {cz['libelle']})"
            n = _med([m["note"] for m in mes])
            U.ajouter(o, "fondamentaux", U.famille(n, f"Note médiane de {fr(n, 0)}/100 sur {len(mes)} sociétés du secteur ({cz['libelle']})", src, "entreprises", ce))
            r, per, cr = rends[g]
            if r is not None and med_rend is not None:
                U.ajouter(o, "valorisation", U.famille(50 + cv["pente"] * (r - med_rend),
                          f"PER médian {fr(per, 1)}, croissance médiane du bénéfice {fr(cr, 1, True)} % : rendement des bénéfices corrigé de la croissance "
                          f"de {fr(r, 1)} contre {fr(med_rend, 1)} pour l'ensemble des secteurs de la zone", src, "entreprises", ce))
            d = [m["dynamique"] for m in mes if m["dynamique"] is not None]
            if len(d) >= cfg["societes_min"]:
                U.ajouter(o, "resultats", U.famille(median(d), f"Dynamique des résultats médiane de {fr(median(d), 0)}/100 sur {len(d)} sociétés (guidance, révisions des analystes, surprises)",
                                                    "agent entreprises (fiches)", "entreprises", ce, False))
            p12, p6, d_cours = perf_12m(series.get(etf) or []) if etf else (None, None, None)
            if p12 is not None:
                U.ajouter(o, "tendance", U.famille(50 + cm["pente"] * p12, f"ETF {etf} {fr(p12, 1, True)} % sur 12 mois, {fr(p6, 1, True)} % sur 6 mois (cours du {date_fr(d_cours)})"
                                                   + (f" — {o['etf_approche']}" if o.get("etf_approche") else ""), f"Yahoo Finance, {etf}", "marches", 1.0))
                o["familles"]["tendance"]["hausse_12m"] = p12
                o["cours"], o["date_cours"] = series[etf][-1][1], d_cours
            else:
                mm = _med([m["momentum"] for m in mes])
                if mm is not None:
                    U.ajouter(o, "tendance", U.famille(50 + cm["pente"] * mm, f"Momentum médian des sociétés du secteur {fr(mm, 1, True)} % sur 12 mois (pas d'ETF sectoriel exploitable)",
                                                       src, "entreprises", ce * 0.85))
                    o["familles"]["tendance"]["hausse_12m"] = mm
            fi = flux_ind.get(etf) if etf else None
            if fi and fi.get("note") is not None:
                U.ajouter(o, "flux", U.famille(fi["note"], f"Flux de l'ETF {etf} : {fi.get('tendance_flux') or 'n. d.'}, {fr(fi.get('valeur'), 2, True)} % de l'encours sur {fi.get('periode_valeur')}"
                                               + (" ; position possiblement encombrée" if fi.get("encombrement") else ""), fi.get("source") or f"émetteur, {etf}", "marches", 1.0, False))
            phase = ctx.phase(cz["phase"])
            rot = (cfg["rotation"].get(phase) or {}).get(g) if phase else None
            if rot is not None:
                U.ajouter(o, "cycle", U.famille(rot, f"{(ctx.zones.get(cz['phase']) or {}).get('nom', cz['libelle'])} en phase « {phase} » : rotation sectorielle "
                                                f"{'favorable' if rot >= 60 else 'défavorable' if rot <= 40 else 'neutre'} au secteur ({fr(rot, 0)}/100)",
                                                "agent macro et tableau de rotation sectorielle (config.json)", "macro", ctx.coef("macro"), False))
            pos, neg = sum(m["inities_pos"] for m in mes), sum(m["inities_neg"] for m in mes)
            if pos or neg:
                U.ajouter(o, "inities", U.famille(max(30, min(80, 50 + cfg["inities"]["pas"] * (pos - neg))),
                                                  f"{pos} société(s) avec achats de dirigeants ou super-investisseurs, {neg} avec ventes massives",
                                                  "agent initiés (data/inities.json)", "inities", ctx.coef("inities"), False))
            sens = cfg["sensibilite"].get(g, "neutre")
            rp = cfg["risque_par_palier"][sens].get(ctx.palier)
            if rp is not None:
                U.ajouter(o, "risque", U.famille(rp, f"Secteur {sens} au palier de risque « {ctx.palier} » ({fr(rp, 0)}/100)",
                                                 "agent risque (palier) et sensibilités sectorielles (config.json)", "risque", ctx.coef("risque"), False))
            if g in geo:
                s, titres = geo[g]
                cg = cfg["geopolitique"]
                U.ajouter(o, "geopolitique", U.famille(max(cg["min"], min(cg["max"], 50 + cg["pas"] * s)),
                                                       f"Exposition aux événements récents : {'; '.join(titres[:2])}", "agent géopolitique (actifs touchés)",
                                                       "geopolitique", ctx.coef("geopolitique"), False))
            o["invalidations"] = [f"Un changement de phase du cycle ({cz['libelle']}) modifierait la rotation sectorielle.",
                                  "Une révision en baisse des bénéfices du secteur contredirait la valorisation."]
            lignes.append(o)
        U.normaliser(lignes, config)
        res += lignes
    return res
