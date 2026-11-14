"""
Univers des opportunités et familles de signaux.

Chaque opportunité :
    {id, type, cle, nom, classe_cycle, zone, pays, secteur, symbole, cours, date_cours, themes,
     familles: {famille: {note, texte, source, agent, coef}}, invalidations, objets liés}
- `note` : score /100 de la famille (au-dessus de 50 = favorable) ; quand la classe compte au moins
  `percentiles.taille_min` éléments, le score est un mélange du percentile dans la classe et de la note
  absolue de l'agent (voir config.json, « percentiles ») ;
- `coef` : fiabilité de la famille = fraîcheur et santé de l'agent source × confiance de la valeur.
Aucune valeur n'est inventée : une famille sans donnée est absente, et c'est signalé.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median

from ..commun.sortie import lire_json
from ..risque.calculs import date_fr, fr
from .entrees import coef_confiance

RACINE = Path(__file__).resolve().parents[2]


def borne(x: float) -> float:
    return max(0.0, min(100.0, x))


def zone_par_pays() -> dict:
    return json.loads((RACINE / "agents" / "macro" / "config.json").read_text(encoding="utf-8")).get("zone_par_pays", {})


def pays_config() -> dict:
    return json.loads((RACINE / "agents" / "pays" / "config.json").read_text(encoding="utf-8"))["pays"]


# ------------------------------------------------------------------ percentiles

def percentile(valeur: float, valeurs: list[float]) -> float:
    n = len(valeurs)
    if not n:
        return 50.0
    inf = sum(1 for v in valeurs if v < valeur)
    eg = sum(1 for v in valeurs if v == valeur)
    return round((inf + 0.5 * eg) / n * 100, 1)


def normaliser(opps: list[dict], config: dict, base: dict[str, list[float]] | None = None) -> None:
    """Remplace la note absolue de chaque famille par le mélange percentile / note absolue, quand la classe
    (ou la distribution de référence `base`) compte assez d'éléments."""
    cp = config["percentiles"]
    familles = {f for o in opps for f in o["familles"]}
    for f in familles:
        valeurs = (base or {}).get(f) or [o["familles"][f]["note"] for o in opps if f in o["familles"] and o["familles"][f].get("percentile", True)]
        if len(valeurs) < cp["taille_min"]:
            continue
        for o in opps:
            fam = o["familles"].get(f)
            if not fam or fam.get("percentile") is False:
                continue
            p = percentile(fam["note"], valeurs)
            fam["note_absolue"] = round(fam["note"], 1)
            fam["percentile_classe"] = p
            fam["note"] = round(cp["poids_percentile"] * p + (1 - cp["poids_percentile"]) * fam["note"], 1)


def famille(note, texte: str, source: str, agent: str, coef: float, percentile_ok: bool = True) -> dict | None:
    if note is None:
        return None
    return {"note": round(borne(note), 1), "texte": texte, "source": source, "agent": agent, "coef": round(coef, 2),
            "percentile": percentile_ok}


def ajouter(o: dict, cle: str, fam: dict | None) -> None:
    if fam:
        o["familles"][cle] = fam


# ------------------------------------------------------------------ contexte commun

class Contexte:
    def __init__(self, entrees: dict, config: dict, data: Path):
        self.e, self.config, self.data = entrees, config, data
        self.pays_cfg = pays_config()
        self.zones_pays = zone_par_pays()
        macro = entrees["macro"].donnees if entrees["macro"].disponible else {}
        self.macro = macro or {}
        self.zones = {z.get("cle"): z for z in ((self.macro.get("cycle") or {}).get("zones") or [])}
        risque = entrees["risque"].donnees if entrees["risque"].disponible else {}
        self.risque = risque or {}
        self.palier = ((self.risque.get("mondial") or {}).get("palier")) or "Vigilance"
        self.geo = (entrees["geopolitique"].donnees or {}) if entrees["geopolitique"].disponible else {}
        self.pays = {p["code"]: p for p in (entrees["pays"].donnees or [])} if entrees["pays"].disponible else {}
        self.mp = (entrees["matieres_premieres"].donnees or {}) if entrees["matieres_premieres"].disponible else {}
        self.entreprises = entrees["entreprises"].donnees or [] if entrees["entreprises"].disponible else []
        self.par_ticker = {x["ticker"]: x for x in self.entreprises if isinstance(x, dict) and x.get("ticker")}
        self.pepites = (entrees["pepites"].donnees or []) if entrees["pepites"].disponible else []
        self.inities = (entrees["inities"].donnees or {}) if entrees["inities"].disponible else {}
        self.analyses = (entrees["analyses"].donnees or []) if entrees["analyses"].disponible else []
        self._fiches = {}
        self.cfg_entreprises = config_entreprises()
        self.exclues: dict[str, str] = {}  # holdings, fonds, BDC, SPAC écartés (ticker → nom)
        etat_risque = lire_json(data / "risque" / "etat.json") or {}
        self.series_taux = ((etat_risque.get("lentes") or {}).get("series") or {})

    def coef(self, agent: str, confiance=None) -> float:
        return self.e[agent].coef * (coef_confiance(confiance, self.config) if confiance is not None else 1.0)

    def zone(self, code: str) -> dict | None:
        z = self.zones.get(self.zones_pays.get(code))
        return z or self.zones.get("monde")

    def phase(self, cle_zone: str) -> str | None:
        return (self.zones.get(cle_zone) or {}).get("phase")

    def fiche(self, ticker: str) -> dict:
        if ticker not in self._fiches:
            e = self.par_ticker.get(ticker) or {}
            chemin = e.get("fiche")
            f = (lire_json(self.data / chemin.removeprefix("data/")) or {}).get("donnees") if chemin else None
            self._fiches[ticker] = f or {}
        return self._fiches[ticker]

    def cycle_note(self, classe: str, phase: str | None) -> float | None:
        if not phase:
            return None
        return (self.config["cycle"]["phases"].get(phase) or {}).get(classe)

    def banque(self, cle: str) -> dict:
        return next((b for b in self.macro.get("banques_centrales") or [] if b.get("cle") == cle), {})

    def signal_recession(self, cle: str) -> dict:
        return next((s for s in ((self.macro.get("recession") or {}).get("signaux") or []) if s.get("cle") == cle), {})


def famille_cycle(ctx: Contexte, classe: str, cle_zone: str | None, nom_zone: str | None, extra: float = 0, extra_texte: str = "") -> dict | None:
    phase = ctx.phase(cle_zone) if cle_zone else None
    n = ctx.cycle_note(classe, phase)
    if n is None:
        return None
    z = ctx.zones.get(cle_zone) or {}
    libelle = {"actions": "actions", "obligations_longues": "obligations longues", "obligations_courtes": "obligations courtes",
               "matieres": "matières premières", "or": "or", "liquidites": "liquidités"}[classe]
    texte = f"{nom_zone or z.get('nom')} en phase « {phase} » (agent macro) : historiquement {'favorable' if n >= 60 else 'défavorable' if n <= 40 else 'neutre'} aux {libelle} ({fr(n, 0)}/100)"
    return famille(n + extra, texte + extra_texte, "agent macro (data/macro.json), tableau des phases (config.json)", "macro",
                   ctx.coef("macro", z.get("confiance")), percentile_ok=False)


# ------------------------------------------------------------------ pays

NOTES_FONDAMENTALES = ("croissance_pib", "indicateur_avance", "inflation", "taux_reel", "activite_reelle")  # activité réelle : si l'agent pays la publie


def opportunites_pays(ctx: Contexte) -> list[dict]:
    res = []
    dyn_par_pays = {}
    for e in ctx.entreprises:
        d = (ctx.fiche(e["ticker"]).get("dynamique") or {}) if ctx.e["entreprises"].disponible else {}
        if isinstance(d, dict) and d.get("note") is not None and d.get("fiabilite") != "indicative":
            dyn_par_pays.setdefault(e.get("pays"), []).append(d["note"])
    geo_pays = (ctx.geo.get("pays") or {})
    risque_pays = (ctx.risque.get("pays") or {})
    for code, cfg in ctx.pays_cfg.items():
        p = ctx.pays.get(code)
        o = {"id": f"pays-{code}", "type": "pays", "cle": code, "nom": cfg["nom"], "pays": code, "classe_cycle": "actions",
             "symbole": cfg.get("etf"), "familles": {}, "invalidations": [], "themes": []}
        z = ctx.zone(code) or {}
        o["zone"] = z.get("cle")
        if p:
            inds = p.get("indicateurs") or {}
            conf = (p.get("confiance") or {}).get("niveau")
            notes = [(k, inds[k]) for k in NOTES_FONDAMENTALES if (inds.get(k) or {}).get("note") is not None]
            if notes:
                texte = " ; ".join(f"{i['libelle'].lower()} {fr(i['valeur'], 1)}{(' ' + i['unite']) if i.get('unite') and i['unite'] != '%' else (' %' if i.get('unite') == '%' else '')} ({i['note']}/100)" for _, i in notes)
                ajouter(o, "fondamentaux", famille(mean(i["note"] for _, i in notes), texte[0].upper() + texte[1:], "agent pays (data/pays.json)", "pays", ctx.coef("pays", conf)))
            v = inds.get("valorisation") or {}
            if v.get("note") is not None:
                c = ctx.coef("pays", "faible" if v.get("a_verifier") else v.get("confiance"))
                ajouter(o, "valorisation", famille(v["note"], f"PER de l'ETF {v.get('symbole', '')} {fr(v.get('per'), 1)} contre une médiane de {fr(v.get('mediane'), 1)} pour les pays suivis ({v['note']}/100)"
                                                   + (" — valeur à vérifier selon l'agent pays" if v.get("a_verifier") else ""), "agent pays (data/pays.json)", "pays", c))
            m = inds.get("momentum") or {}
            if m.get("note") is not None:
                ajouter(o, "tendance", famille(m["note"], f"{m.get('indice') or m.get('symbole')} {fr(m.get('valeur'), 1, True)} % sur 12 mois en monnaie locale ({m['note']}/100)",
                                               "agent pays (data/pays.json)", "pays", ctx.coef("pays", m.get("confiance"))))
                o["familles"]["tendance"]["hausse_12m"] = m.get("valeur")
            fl = ((p.get("detail") or {}).get("flux_etrangers") or {})
            if fl.get("note") is not None:
                ajouter(o, "flux", famille(fl["note"], f"Flux de l'ETF {fl.get('symbole')} : {fl.get('tendance_flux') or 'n. d.'}, {fr(fl.get('valeur'), 2, True)} % de l'encours sur {fl.get('periode_valeur', '1m')} ({fl['note']}/100 ; ETF cotés aux États-Unis seulement)",
                                           "agent pays (flux des ETF pays)", "pays", ctx.coef("pays", fl.get("confiance"))))
            o["invalidations"] = list(p.get("contre_scenario") or [])[:2]
            o["note_agent"] = p.get("note")
        ajouter(o, "cycle", famille_cycle(ctx, "actions", o["zone"], z.get("nom")))
        r = risque_pays.get(code) or {}
        if r.get("score") is not None:
            ajouter(o, "risque", famille(100 - r["score"], f"Score de risque {r['score']}/100 (agent risque : marché, devise, souverain, vulnérabilité macro)", "agent risque (data/risque.json)", "risque", ctx.coef("risque")))
        g = geo_pays.get(code) or {}
        if g.get("score") is not None:
            ajouter(o, "geopolitique", famille(100 - g["score"], f"Risque géopolitique {g['score']}/100, {g.get('evenements_14j', 0)} événement(s) en 14 jours (agent géopolitique)", "agent géopolitique (data/geopolitique.json)", "geopolitique", ctx.coef("geopolitique")))
        dyn = dyn_par_pays.get(code) or []
        if len(dyn) >= 5:
            ajouter(o, "resultats", famille(median(dyn), f"Dynamique des résultats médiane de {fr(median(dyn), 0)}/100 sur {len(dyn)} sociétés du pays (révisions des analystes, surprises, guidance)",
                                            "agent entreprises (fiches)", "entreprises", ctx.coef("entreprises")))
        if code in ("TW", "KR"):
            o["themes"].append("semi")
        if code in ("SA", "AE"):
            o["themes"].append("petrole")
        res.append(o)
    return res


# ------------------------------------------------------------------ matières premières et or

def opportunites_matieres(ctx: Contexte) -> tuple[list[dict], dict | None]:
    matieres, or_ = [], None
    for m in ctx.mp.get("matieres") or []:
        sn = m.get("sous_notes") or {}
        conf = m.get("confiance")
        c = ctx.coef("matieres_premieres", conf)
        est_or = m.get("cle") == "or"
        o = {"id": "or" if est_or else f"matiere-{m['cle']}", "type": "or" if est_or else "matieres", "cle": m["cle"], "nom": m["nom"],
             "famille_mp": m.get("famille"), "classe_cycle": "or" if est_or else "matieres", "zone": "monde", "symbole": m.get("symbole"),
             "cours": m.get("cours"), "date_cours": m.get("date_cours"), "familles": {}, "invalidations": list(m.get("invalidations") or [])[:2],
             "themes": [t for t, cfg in ctx.config["themes"]["liste"].items() if m["cle"] in (cfg.get("matieres") or [])],
             "verdict_agent": m.get("verdict"), "note_agent": m.get("note")}

        def sn_(k):
            x = sn.get(k)
            return x if isinstance(x, dict) and x.get("note") is not None else None
        fond = [x for x in (sn_("courbe"), sn_("stocks")) if x]
        if fond and not est_or:
            ajouter(o, "fondamentaux", famille(mean(x["note"] for x in fond), " ; ".join(x["texte"] for x in fond), "agent matières premières (courbe, stocks)", "matieres_premieres", c))
        if sn_("niveau"):
            ajouter(o, "valorisation", famille(sn_("niveau")["note"], sn_("niveau")["texte"], sn_("niveau").get("source") or "agent matières premières", "matieres_premieres", c))
        if sn_("tendance"):
            ajouter(o, "tendance", famille(sn_("tendance")["note"], sn_("tendance")["texte"], sn_("tendance").get("source") or "agent matières premières", "matieres_premieres", c))
            o["familles"]["tendance"]["hausse_12m"] = sn_("tendance").get("variation_12m")
        fl = [x for x in (sn_("flux"), sn_("positionnement")) if x]
        if fl:
            ajouter(o, "flux", famille(mean(x["note"] for x in fl), " ; ".join(x["texte"] for x in fl), "agent matières premières (flux des ETF, CFTC)", "matieres_premieres", c))
            if (sn_("positionnement") or {}).get("percentile") is not None:
                o["familles"]["flux"]["percentile_cftc"] = sn_("positionnement")["percentile"]
        if sn_("geopolitique"):
            ajouter(o, "geopolitique", famille(sn_("geopolitique")["note"], sn_("geopolitique")["texte"], "agent matières premières (événements de l'agent géopolitique)", "matieres_premieres", c))
        cyc = famille_cycle(ctx, o["classe_cycle"], "monde", "Monde")
        if cyc and sn_("macro"):
            cyc["note"] = round((cyc["note"] + sn_("macro")["note"]) / 2, 1)
            cyc["texte"] += f" ; moteurs macro propres : {sn_('macro')['texte']}"
        ajouter(o, "cycle", cyc)
        rp = ctx.config["risque_par_palier"][o["classe_cycle"]].get(ctx.palier)
        if rp is not None:
            ajouter(o, "risque", famille(rp, f"Palier de risque mondial « {ctx.palier} » : {'favorable' if rp >= 60 else 'défavorable' if rp <= 40 else 'neutre'} pour {'une valeur refuge' if est_or else 'les matières premières'}",
                                         "agent risque (palier) et tableau par palier (config.json)", "risque", ctx.coef("risque"), percentile_ok=False))
        if est_or:
            f = famille_taux_reel_or(ctx)
            ajouter(o, "fondamentaux", f)
            or_ = o
        else:
            matieres.append(o)
    return matieres, or_


def famille_taux_reel_or(ctx: Contexte) -> dict | None:
    tr = ((ctx.macro.get("taux_reels") or {}).get("etats_unis") or {}).get("attendu_10a") or {}
    if tr.get("valeur") is None:
        return None
    c = ctx.config["or"]
    var = tr.get("variation_12m") or 0
    note = 50 + c["variation_taux_reel_pente"] * var + c["niveau_taux_reel_pente"] * (tr["valeur"] - c["niveau_taux_reel_reference"])
    return famille(note, f"Taux réel attendu à 10 ans aux États-Unis {fr(tr['valeur'], 2)} % ({fr(var, 2, True)} pt sur 12 mois) : un taux réel {'en hausse pèse' if var > 0 else 'en baisse soutient'} sur l'or",
                   tr.get("source") or "agent macro (FRED DFII10)", "macro", ctx.coef("macro"), percentile_ok=False)


# ------------------------------------------------------------------ obligations et liquidités

def _derniere(serie):
    return serie[-1] if serie else None


def _il_y_a(serie, mois: int):
    if not serie or len(serie) <= mois:
        return None
    return serie[-1 - mois]


def opportunites_obligations(ctx: Contexte) -> tuple[list[dict], list[dict]]:
    cb = ctx.config["obligations"]
    tr_us = (ctx.macro.get("taux_reels") or {}).get("etats_unis") or {}
    att = tr_us.get("attendu_10a") or {}
    pm = tr_us.get("point_mort_10a") or {}
    us10 = round(att["valeur"] + pm["valeur"], 2) if att.get("valeur") is not None and pm.get("valeur") is not None else None
    pente_us = ctx.signal_recession("courbe_us_10_2").get("valeur")
    us2 = round(us10 - pente_us, 2) if us10 is not None and pente_us is not None else None
    infl_us = ((ctx.zones.get("etats_unis") or {}).get("inflation") or {}).get("valeur")
    infl_ez = ((ctx.zones.get("zone_euro") or {}).get("inflation") or {}).get("valeur")
    bund_serie = ctx.series_taux.get("taux:DE") or []
    bund10 = _derniere(bund_serie)
    pente_de = ctx.signal_recession("courbe_allemagne_10_2").get("valeur")
    bund2 = round(bund10[1] - pente_de, 2) if bund10 and pente_de is not None else None
    fed, bce = ctx.banque("fed"), ctx.banque("bce")
    cmacro = ctx.coef("macro")
    crisque = ctx.coef("risque")

    def reel(taux, infl):
        return None if taux is None or infl is None else round(taux - infl, 2)

    def f_val(taux, infl, libelle, source, coef=cmacro):
        r = reel(taux, infl)
        if r is None:
            return None
        return famille(cb["taux_reel_base"] + cb["taux_reel_pente"] * r, f"{libelle} {fr(taux, 2)} % moins {fr(infl, 1)} % d'inflation : rendement réel de {fr(r, 2, True)} %", source, "macro", coef, False)

    def f_infl(infl, zone, pente=None):
        if infl is None:
            return None
        cible = cb["cibles_inflation"][zone]
        n = 50 + cb["inflation_ecart_cible_pente"] * (infl - cible)
        t = f"Inflation à {fr(infl, 1)} % pour une cible de {fr(cible, 1)} %"
        if pente is not None:
            n = (n + 50 + cb["pente_courbe_pente"] * pente) / 2
            t += f" ; pente 10 ans − 2 ans de {fr(pente, 2, True)} pt"
        return famille(n, t, "agent macro (data/macro.json)", "macro", cmacro, False)

    def f_cb(b, nom):
        t = b.get("tendance_12m") or {}
        if t.get("variation_pts") is None:
            return None
        dm = b.get("dernier_mouvement") or {}
        n = 50 + cb["variation_taux_pente"] * t["variation_pts"]
        if dm.get("sens") == "hausse":
            n -= 8
        elif dm.get("sens") == "baisse":
            n += 8
        return famille(n, f"{nom} : taux {fr(b.get('taux'), 2)} %, {fr(t['variation_pts'], 2, True)} pt sur 12 mois, dernier mouvement : {dm.get('sens', 'n. d.')} le {date_fr(dm.get('date'))}",
                       b.get("source") or "agent macro", "macro", cmacro, False)

    def f_risque(classe, libelle):
        rp = ctx.config["risque_par_palier"][classe].get(ctx.palier)
        return famille(rp, f"Palier de risque mondial « {ctx.palier} » : {libelle}", "agent risque (palier) et tableau par palier (config.json)", "risque", crisque, False) if rp is not None else None

    obligs = []
    # États-Unis, longues (10 ans)
    o = {"id": "oblig-us-longues", "type": "obligations", "cle": "us-longues", "nom": "Obligations d'État américaines longues (10 ans)", "zone": "etats_unis",
         "classe_cycle": "obligations_longues", "symbole": "TLT", "indice_suivi": "obligations_us", "familles": {}, "themes": [],
         "invalidations": ["Une remontée de l'inflation sous-jacente ou du point mort d'inflation pousserait les taux longs à la hausse."]}
    if att.get("valeur") is not None:
        ajouter(o, "valorisation", famille(cb["taux_reel_base"] + cb["taux_reel_pente"] * att["valeur"], f"Taux réel attendu à 10 ans {fr(att['valeur'], 2)} % (rendement nominal {fr(us10, 2)} %, point mort {fr(pm.get('valeur'), 2)} %)",
                                           att.get("source") or "FRED DFII10", "macro", cmacro, False))
        if att.get("variation_12m") is not None:
            ajouter(o, "tendance", famille(50 + cb["variation_taux_pente"] * att["variation_12m"], f"Taux réel à 10 ans {fr(att['variation_12m'], 2, True)} pt sur 12 mois (une hausse des taux fait baisser le prix des obligations)",
                                           att.get("source") or "FRED DFII10", "macro", cmacro, False))
    ajouter(o, "fondamentaux", f_infl(infl_us, "etats_unis", pente_us))
    ajouter(o, "cycle", famille_cycle(ctx, "obligations_longues", "etats_unis", "États-Unis"))
    ajouter(o, "risque", f_risque("obligations_longues", "les obligations d'État longues servent de refuge quand le stress monte"))
    obligs.append(o)
    # États-Unis, courtes (2 ans)
    o = {"id": "oblig-us-courtes", "type": "obligations", "cle": "us-courtes", "nom": "Obligations d'État américaines courtes (2 ans)", "zone": "etats_unis",
         "classe_cycle": "obligations_courtes", "symbole": "SHY", "indice_suivi": "obligations_us", "familles": {}, "themes": [],
         "invalidations": ["Une reprise des hausses de taux de la Fed ferait baisser les obligations courtes."]}
    ajouter(o, "valorisation", f_val(us2, infl_us, "Rendement à 2 ans estimé (10 ans − pente 10 ans − 2 ans)", "agent macro (FRED DFII10, T10YIE, T10Y2Y ; inflation OCDE)"))
    ajouter(o, "tendance", f_cb(fed, "Fed"))
    ajouter(o, "fondamentaux", f_infl(infl_us, "etats_unis"))
    ajouter(o, "cycle", famille_cycle(ctx, "obligations_courtes", "etats_unis", "États-Unis"))
    ajouter(o, "risque", f_risque("obligations_courtes", "faible sensibilité aux taux, rôle de réserve"))
    obligs.append(o)
    # Zone euro, longues (Bund 10 ans)
    o = {"id": "oblig-euro-longues", "type": "obligations", "cle": "euro-longues", "nom": "Obligations d'État de la zone euro longues (Bund 10 ans)", "zone": "zone_euro",
         "classe_cycle": "obligations_longues", "symbole": "IBGL.AS", "indice_suivi": "obligations_euro", "familles": {}, "themes": [],
         "invalidations": ["Une accélération de l'inflation de la zone euro ou de nouvelles hausses de la BCE pèseraient sur les taux longs."]}
    if bund10:
        ajouter(o, "valorisation", f_val(bund10[1], infl_ez, f"Rendement de l'État allemand à 10 ans (OCDE via FRED, {bund10[0][:7]})", "agent risque (OCDE via FRED, IRLTLT01DEM156N) ; inflation Eurostat", ctx.coef("risque")))
        ancien = _il_y_a(bund_serie, 12)
        if ancien:
            var = round(bund10[1] - ancien[1], 2)
            ajouter(o, "tendance", famille(50 + cb["variation_taux_pente"] * var, f"Bund 10 ans {fr(var, 2, True)} pt sur 12 mois ({fr(ancien[1], 2)} % → {fr(bund10[1], 2)} %)",
                                           "agent risque (OCDE via FRED)", "risque", ctx.coef("risque"), False))
    ajouter(o, "fondamentaux", f_infl(infl_ez, "zone_euro", pente_de))
    ajouter(o, "cycle", famille_cycle(ctx, "obligations_longues", "zone_euro", "Zone euro"))
    ajouter(o, "risque", f_risque("obligations_longues", "les obligations d'État longues servent de refuge quand le stress monte"))
    obligs.append(o)
    # Zone euro, courtes (2 ans)
    o = {"id": "oblig-euro-courtes", "type": "obligations", "cle": "euro-courtes", "nom": "Obligations d'État de la zone euro courtes (2 ans)", "zone": "zone_euro",
         "classe_cycle": "obligations_courtes", "symbole": "IBGS.AS", "indice_suivi": "obligations_euro", "familles": {}, "themes": [],
         "invalidations": ["De nouvelles hausses de la BCE feraient baisser les obligations courtes."]}
    ajouter(o, "valorisation", f_val(bund2, infl_ez, "Rendement allemand à 2 ans estimé (10 ans − pente 10 ans − 2 ans)", "agent risque (OCDE via FRED) et agent macro (Bundesbank)"))
    ajouter(o, "tendance", f_cb(bce, "BCE"))
    ajouter(o, "fondamentaux", f_infl(infl_ez, "zone_euro"))
    ajouter(o, "cycle", famille_cycle(ctx, "obligations_courtes", "zone_euro", "Zone euro"))
    ajouter(o, "risque", f_risque("obligations_courtes", "faible sensibilité aux taux, rôle de réserve"))
    obligs.append(o)

    # Liquidités
    cl = ctx.config["liquidites"]
    liqs = []
    for cle, nom, b, infl, zone, sym in (("usd", "Liquidités en dollars", fed, infl_us, "etats_unis", "BIL"), ("eur", "Liquidités en euros", bce, infl_ez, "zone_euro", "XEON.DE")):
        o = {"id": f"liquidites-{cle}", "type": "liquidites", "cle": cle, "nom": nom, "zone": zone, "classe_cycle": "liquidites", "symbole": sym,
             "indice_suivi": "liquidites", "familles": {}, "themes": [],
             "invalidations": ["Une baisse des taux directeurs réduirait le rendement des liquidités ; une détente du stress favoriserait les actifs risqués."]}
        r = reel(b.get("taux"), infl)
        if r is not None:
            ajouter(o, "valorisation", famille(cl["taux_reel_base"] + cl["taux_reel_pente"] * r, f"Rendement monétaire réel : taux {b.get('nom')} {fr(b.get('taux'), 2)} % − inflation {fr(infl, 1)} % = {fr(r, 2, True)} %",
                                               "agent macro (banques centrales, inflation)", "macro", cmacro, False))
            o["rendement_reel"] = r
        ajouter(o, "cycle", famille_cycle(ctx, "liquidites", zone, None))
        ajouter(o, "risque", f_risque("liquidites", "les liquidités protègent quand le stress monte"))
        liqs.append(o)
    return obligs, liqs


# ------------------------------------------------------------------ entreprises

def config_entreprises() -> dict:
    return json.loads((RACINE / "agents" / "entreprises" / "config.json").read_text(encoding="utf-8"))["pepites"]


def est_vehicule(ctx: "Contexte", e: dict) -> bool:
    """Holding, société d'investissement, fonds fermé, BDC, véhicule de crédit ou SPAC : exclu du classement et des
    alertes (évaluation par le PER non pertinente ; décote sur l'actif net non disponible gratuitement)."""
    from ..entreprises.analyse import est_holding
    if not e:
        return False
    exclu = bool(e.get("holding") or ctx.fiche(e["ticker"]).get("holding")) or est_holding(
        e.get("nom") or "", ctx.fiche(e["ticker"]).get("industrie") or e.get("industrie"), e["ticker"], ctx.cfg_entreprises, e.get("secteur_gics"))
    if exclu:
        ctx.exclues.setdefault(e["ticker"], e.get("nom") or e["ticker"])
    return exclu


def selection_entreprises(ctx: Contexte, pays_attractifs: list[str]) -> list[tuple[str, list[str]]]:
    """[(ticker, [provenances])] : pépites, qualité à prix raisonnable, liste de surveillance, analyses à la demande,
    et les meilleures sociétés de chaque pays attractif."""
    cfg = ctx.config["univers"]
    prov: dict[str, list[str]] = {}
    noms: dict[str, str] = {}

    def add(t, p):
        if t in ctx.par_ticker and est_vehicule(ctx, ctx.par_ticker[t]):
            ctx.exclues.setdefault(t, ctx.par_ticker[t].get("nom") or t)
            return
        nom = ((ctx.par_ticker.get(t) or {}).get("nom") or "").strip().lower()
        if nom and noms.setdefault(nom, t) != t:  # même société sous une autre cotation : une seule ligne
            t = noms[nom]
        if t in ctx.par_ticker:
            prov.setdefault(t, [])
            if p not in prov[t]:
                prov[t].append(p)
    for x in ctx.pepites:
        add(x.get("ticker"), "Pépite" if x.get("liste") == "pepites" else "Qualité à prix raisonnable")
    for e in ctx.entreprises:
        if e.get("surveillance"):
            add(e["ticker"], "Liste de surveillance")
    for a in ctx.analyses:
        add(a.get("ticker"), "Analyse à la demande")
    for code in pays_attractifs:
        for e in meilleures_du_pays(ctx, code):
            add(e["ticker"], f"Parmi les meilleures sociétés du pays ({code})")
    # Tour d'horizon : les meilleures sociétés de chaque secteur, pour un panorama diversifié
    ordre = {"Acheter": 0, "Acheter sur repli": 1, "Attendre": 2, "Éviter": 3}
    par_secteur = {}
    for e in sorted((e for e in ctx.entreprises if e.get("note") is not None and e.get("secteur_gics")),
                    key=lambda e: (ordre.get((e.get("recommandation") or {}).get("n"), 2), -e["note"])):
        if par_secteur.get(e["secteur_gics"], 0) < cfg["entreprises_par_secteur"] and not est_vehicule(ctx, e):
            par_secteur[e["secteur_gics"]] = par_secteur.get(e["secteur_gics"], 0) + 1
            add(e["ticker"], f"Parmi les meilleures sociétés de son secteur ({e.get('secteur_nom') or e['secteur_gics']})")
    return list(prov.items())[:cfg["entreprises_max"]]


def meilleures_du_pays(ctx: Contexte, code: str) -> list[dict]:
    n = ctx.config["univers"]["entreprises_par_pays_attractif"]
    cands = [e for e in ctx.entreprises if e.get("pays") == code and e.get("note") is not None and not est_vehicule(ctx, e)]
    ordre = {"Acheter": 0, "Acheter sur repli": 1, "Attendre": 2, "Éviter": 3}
    cands.sort(key=lambda e: (ordre.get((e.get("recommandation") or {}).get("n"), 2), -e["note"]))
    return cands[:n]


def note_inities(x: dict) -> tuple[float | None, str]:
    if not x:
        return None, ""
    if x.get("ventes_massives"):
        return 30, "Ventes massives et groupées de dirigeants"
    a, c = x.get("score_achats"), x.get("conviction")
    if not a and not c:
        return None, ""
    textes = [t for t in (x.get("texte_achats"), x.get("texte_conviction")) if t]
    return 50 + 0.45 * max(a or 0, c or 0), " ; ".join(textes)


def opportunites_entreprises(ctx: Contexte, selection: list[tuple[str, list[str]]], familles_pays: dict[str, dict]) -> list[dict]:
    univ = [e for e in ctx.entreprises if e.get("note") is not None]
    ind_note = lambda e, k: ((e.get("indicateurs") or {}).get(k) or {}).get("note")  # noqa: E731
    base = {"fondamentaux": [e["note"] for e in univ],
            "valorisation": [mean(v) for e in univ if (v := [n for n in (ind_note(e, "per_secteur"), ind_note(e, "ev_ebitda_secteur")) if n is not None])],
            "tendance": [n for e in univ if (n := ind_note(e, "momentum_12m")) is not None]}
    themes = ctx.config["themes"]["liste"]
    sect_cycle = ctx.config["cycle"]["secteurs"]
    ini = ctx.inities.get("societes") or {}
    res = []
    for t, provenances in selection:
        e = ctx.par_ticker[t]
        f = ctx.fiche(t)
        conf = (e.get("confiance") or {}).get("niveau") if isinstance(e.get("confiance"), dict) else e.get("confiance")
        c = ctx.coef("entreprises", conf)
        reco = f.get("recommandation") or {}
        o = {"id": f"entreprise-{t}", "type": "entreprises", "cle": t, "nom": e.get("nom") or t, "pays": e.get("pays"), "secteur": e.get("secteur_gics"),
             "secteur_nom": e.get("secteur_nom"), "industrie": f.get("industrie") or e.get("industrie"), "classe_cycle": "actions", "symbole": t,
             "cours": reco.get("cours"), "date_cours": reco.get("date_cours"), "devise": reco.get("devise") or e.get("devise"),
             "provenances": provenances, "familles": {}, "themes": [], "note_agent": e.get("note"),
             "recommandation_agent": (e.get("recommandation") or {}).get("n"),
             "invalidations": list(f.get("contre_scenario") or [])[:2] if isinstance(f.get("contre_scenario"), list) else []}
        z = ctx.zone(e.get("pays")) or {}
        o["zone"] = z.get("cle")
        ajouter(o, "fondamentaux", famille(e["note"], f"Note de l'agent entreprises {e['note']}/100 : {e.get('verdict', '')[:160]}", "agent entreprises (data/entreprises.json)", "entreprises", c))
        vals = [(k, (e.get("indicateurs") or {}).get(k)) for k in ("per_secteur", "ev_ebitda_secteur")]
        vals = [(k, v) for k, v in vals if v and v.get("note") is not None]
        if vals:
            texte = " ; ".join(f"{v['libelle']} {v.get('affichage', '')}" for _, v in vals)
            if reco.get("ecart_pct") is not None and (reco.get("valeur") or {}).get("fiable"):
                texte += f" ; valeur estimée {fr(reco['ecart_pct'], 1, True)} % par rapport au cours"
            ajouter(o, "valorisation", famille(mean(v["note"] for _, v in vals), texte, "agent entreprises", "entreprises", c))
        m = (e.get("indicateurs") or {}).get("momentum_12m") or {}
        if m.get("note") is not None:
            ajouter(o, "tendance", famille(m["note"], f"Momentum sur 12 mois {m.get('affichage', '')} ({m.get('complement', '')})", "agent entreprises (Yahoo Finance)", "entreprises", c))
            o["familles"]["tendance"]["hausse_12m"] = m.get("valeur")
        for fam in ("flux", "risque", "geopolitique"):
            fp = familles_pays.get(e.get("pays"), {}).get(fam)
            if fp:
                fp = {**fp, "texte": f"{ctx.pays_cfg.get(e.get('pays'), {}).get('nom', e.get('pays'))} : {fp['texte']}", "percentile": False}
                if fam == "risque":
                    alertes = [a for a in (f.get("alertes") or []) if isinstance(a, dict)]
                    if alertes:
                        fp["note"] = round(borne(fp["note"] - min(30, 10 * len(alertes))), 1)
                        fp["texte"] += " ; signaux d'alerte comptables : " + ", ".join(a.get("titre", "") for a in alertes[:3])
                o["familles"][fam] = fp
        phase = ctx.phase(o["zone"]) if o["zone"] else None
        inflex = (sect_cycle.get(phase) or {}).get(e.get("secteur_gics"), 0)
        ajouter(o, "cycle", famille_cycle(ctx, "actions", o["zone"], z.get("nom"), inflex,
                                          f" ; secteur {e.get('secteur_nom') or e.get('secteur_gics')} : {fr(inflex, 0, True)} pt dans cette phase" if inflex else ""))
        n_ini, t_ini = note_inities(ini.get(t))
        if n_ini is not None:
            ajouter(o, "inities", famille(n_ini, t_ini, "agent initiés (data/inities.json)", "inities", ctx.coef("inities"), False))
        dyn = f.get("dynamique") or {}
        if isinstance(dyn, dict) and dyn.get("note") is not None:
            cdyn = c * (0.6 if dyn.get("fiabilite") == "indicative" else 1)
            ajouter(o, "resultats", famille(dyn["note"], dyn.get("texte") or f"{dyn['note']}/100", "agent entreprises (guidance SEC + Gemini, analystes Yahoo)", "entreprises", cdyn, False))
        industrie = (o.get("industrie") or "")
        for cle, th in themes.items():
            if t in (th.get("tickers") or []) or any(i in industrie for i in (th.get("industries") or [])):
                o["themes"].append(cle)
        res.append(o)
    normaliser(res, ctx.config, base)
    return res
