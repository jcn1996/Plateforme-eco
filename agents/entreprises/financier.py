"""
Analyse financière approfondie (fonctions pures, testables sans réseau). Règles et seuils :
agents/entreprises/analyse_financiere.md et section « analyse_financiere » de agents/entreprises/config.json.

Données : états financiers annuels Yahoo Finance (jusqu'à 5 exercices), complétés par la SEC (XBRL companyfacts,
jusqu'à 6 exercices : chiffre d'affaires, résultat net, résultat opérationnel, marge brute, flux d'exploitation)
pour les sociétés américaines ; la source officielle l'emporte sur l'exercice commun. Détention des dirigeants et
bêta : Yahoo Finance. Un indicateur dont une donnée manque n'est pas calculé (jamais d'hypothèse silencieuse),
sauf exceptions documentées (stocks absents = 0 pour le cycle de conversion du cash ; DEPI et SGAI neutres, à 1,
dans le M-score quand amortissements ou frais commerciaux manquent).

Familles (sous-notes) :
- valeur et cycle : rendement du flux de trésorerie disponible, bénéfices normalisés (sommet de cycle possible),
  ROIC − WACC, régularité sur 5 ans, rendement pour l'actionnaire ;
- solidité et fiabilité : Z-score d'Altman, M-score de Beneish, goodwill / actif total, current ratio (et
  dette nette / EBITDA, couverture des intérêts) ;
- qualité : marge brute et sa stabilité, cycle de conversion du cash, capex / amortissements, intensité en R&D
  (technologies et santé) (et F-score, conversion du bénéfice en cash) ;
- alignement : part du capital détenue par les dirigeants, évolution du nombre d'actions sur 3 ans.
Banques et assurances : seuls les indicateurs pertinents sont gardés (bénéfices normalisés, régularité de la
croissance, rendement pour l'actionnaire, alignement) ; Z-score, M-score et ratios d'exploitation sont exclus.
"""
from __future__ import annotations

import functools
import json
import statistics
from datetime import date
from pathlib import Path

from ..pays.textes import nb

DOSSIER = Path(__file__).resolve().parent

LIBELLES = {
    "fcf_yield": "Rendement du flux de trésorerie disponible",
    "benefices_normalises": "Bénéfice actuel / moyenne",
    "roic_wacc": "ROIC − coût du capital",
    "regularite": "Régularité sur 5 ans",
    "rendement_actionnaire": "Rendement pour l'actionnaire",
    "altman_z": "Z-score d'Altman",
    "mscore": "M-score de Beneish",
    "goodwill_actif": "Goodwill / actif total",
    "current_ratio": "Current ratio",
    "marge_brute": "Marge brute",
    "cycle_cash": "Cycle de conversion du cash",
    "capex_amortissements": "Capex / amortissements",
    "intensite_rd": "Intensité en R&D",
    "detention_dirigeants": "Capital détenu par les dirigeants",
    "evolution_actions": "Nombre d'actions sur 3 ans",
}
NOMS_FAMILLES = {"valeur_cycle": "Valeur et cycle", "solidite": "Solidité et fiabilité", "qualite": "Qualité", "alignement": "Alignement"}
# Indicateurs gardés pour les banques et assurances
FINANCIERS = ("benefices_normalises", "regularite", "rendement_actionnaire", "detention_dirigeants", "evolution_actions")


@functools.lru_cache(maxsize=1)
def config_defaut() -> dict:
    return json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))["analyse_financiere"]


def _r(x, ch=2):
    return None if x is None else round(x, ch)


def _div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def lin(x, points):
    if x is None:
        return None
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return round(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return points[-1][1]


# ------------------------------------------------------------------ série longue (Yahoo + SEC)

def serie_annuelle(s: dict, annees: int) -> list[dict]:
    """Exercices du plus récent au plus ancien : Yahoo, complété et corrigé par la SEC (même exercice à 40 jours
    près : la source officielle l'emporte) ; exercices SEC plus anciens ajoutés pour atteindre `annees`."""
    yahoo = [dict(x) for x in (s.get("annuel") or []) if x.get("fin")]
    sec = [x for x in ((s.get("officiel") or {}).get("historique") or []) if x.get("fin")]
    for x in yahoo:
        dx = date.fromisoformat(x["fin"])
        for o in sec:
            if abs((date.fromisoformat(o["fin"]) - dx).days) <= 40:
                for cle in ("ca", "resultat_net", "ebit", "marge_brute", "cfo"):
                    if o.get(cle) is not None:
                        x[cle] = o[cle]
                o["_utilise"] = True
                break
    plus_ancien = min((x["fin"] for x in yahoo), default="9999")
    res = yahoo + [{k: v for k, v in o.items() if not k.startswith("_")} for o in sec
                   if not o.get("_utilise") and o["fin"] < plus_ancien]
    for o in sec:
        o.pop("_utilise", None)
    return sorted(res, key=lambda x: x["fin"], reverse=True)[:annees]


# ------------------------------------------------------------------ indicateurs

def normalisation(serie: list[dict], rn_actuel, cfg: dict) -> dict:
    """Bénéfice actuel rapporté à la moyenne des `annees` derniers exercices. « Sommet de cycle possible » quand ce
    rapport dépasse seuil_sommet ET que l'écart ne s'explique pas par la croissance du chiffre d'affaires : rapport des
    bénéfices ÷ rapport des chiffres d'affaires (CA du dernier exercice / CA moyen) au-dessus de seuil_marge, c'est-à-dire
    une marge nette nettement supérieure à sa moyenne, et au plus haut des exercices étudiés. Une société en croissance
    régulière à marge stable, ou qui sort d'un creux, n'est donc pas signalée. Moyenne positive et au moins
    annees_min_alerte exercices requis."""
    c = cfg["normalisation"]
    rns = [x["resultat_net"] for x in serie if x.get("resultat_net") is not None][:c["annees"]]
    cas = [x["ca"] for x in serie if x.get("ca")][:c["annees"]]
    fcfs = [x["fcf"] for x in serie if x.get("fcf") is not None][:c["annees"]]
    res = {}
    if len(fcfs) >= c["annees_min"]:
        res["fcf_moyen"] = statistics.fmean(fcfs)
    if len(rns) < c["annees_min"]:
        return res
    moy = statistics.fmean(rns)
    act = rn_actuel if rn_actuel is not None else rns[0]
    res.update({"benefice_moyen": moy, "benefice_moyen_annees": len(rns), "benefice_actuel": act, "sommet_cycle": False})
    if moy <= 0 or act <= 0:  # bénéfice actuel ou moyen négatif : rapport non significatif
        return res
    ratio = act / moy
    res["benefices_normalises"] = ratio
    ratio_ca = cas[0] / statistics.fmean(cas) if len(cas) >= c["annees_min"] and statistics.fmean(cas) > 0 else None
    res["exces_marge"] = ratio / ratio_ca if ratio_ca else ratio  # sans CA : rapport des bénéfices seul
    # Marge nette au plus haut des exercices étudiés : sans cela, l'écart vient d'un creux passé (restructuration),
    # pas d'un pic actuel
    marges = [x["resultat_net"] / x["ca"] for x in serie[:c["annees"]] if x.get("resultat_net") is not None and x.get("ca")]
    record = len(marges) < 2 or marges[0] >= max(marges[1:])
    res["sommet_cycle"] = bool(ratio > c["seuil_sommet"] and res["exces_marge"] > c["seuil_marge"] and record
                               and len(rns) >= c["annees_min_alerte"])
    return res


def wacc(s: dict, a0: dict, cap_c, cfg: dict) -> dict | None:
    """Coût moyen pondéré du capital estimé : fonds propres au coût CAPM (taux sans risque + prime du pays ou de la
    région + bêta × prime de marché), dette au coût apparent (intérêts / dette, borné), après impôt, pondérés aux
    valeurs de marché (capitalisation) et comptables (dette)."""
    c = cfg["wacc"]
    if not cap_c or cap_c <= 0:
        return None
    beta_src = s.get("beta")
    beta = c["beta_defaut"] if beta_src is None else min(c["beta_max"], max(c["beta_min"], beta_src))
    rf = c["taux_sans_risque"] + c["primes_region"].get(s.get("region") or "", c["primes_region"].get("autre", 0))
    ke = rf + beta * c["prime_marche"]
    dette = a0.get("dette_totale") or 0
    kd_brut = _div(a0.get("interets"), dette)
    kd = rf + c["marge_dette_defaut"] if kd_brut is None else min(rf + c["marge_dette_max"], max(rf, kd_brut * 100))
    t = a0.get("taux_impot")
    t = c["impot_defaut"] if t is None or not 0 <= t <= 0.5 else t
    w = (cap_c * ke + dette * kd * (1 - t)) / (cap_c + dette)
    return {"wacc": round(w, 2), "cout_fonds_propres": round(ke, 2), "cout_dette": round(kd, 2), "beta": round(beta, 2),
            "beta_source": "Yahoo Finance" if beta_src is not None else "valeur par défaut", "taux_sans_risque": round(rf, 2),
            "prime_marche": c["prime_marche"], "impot": round(t * 100, 1), "part_dette": round(dette / (cap_c + dette) * 100, 1)}


def regularite(serie: list[dict], cfg: dict) -> dict:
    """Part des années de croissance du CA et écart-type de la marge opérationnelle et de la marge brute (points)."""
    c = cfg["regularite"]
    res = {}
    cas = [x["ca"] for x in serie if x.get("ca")]
    if len(cas) >= c["annees_min"]:
        hausses = sum(1 for a, b in zip(cas, cas[1:]) if a > b)
        res["regularite_croissance_pct"] = round(hausses / (len(cas) - 1) * 100)
        res["regularite_annees"] = len(cas)
    for cle, src in (("stabilite_marge_pts", "ebit"), ("stabilite_marge_brute_pts", "marge_brute")):
        marges = [x[src] / x["ca"] * 100 for x in serie if x.get(src) is not None and x.get("ca")]
        if len(marges) >= c["annees_min"]:
            res[cle] = round(statistics.pstdev(marges), 2)
    parts = []
    if "regularite_croissance_pct" in res:
        parts.append(lin(res["regularite_croissance_pct"], c["bareme_croissance"]))
    if "stabilite_marge_pts" in res:
        parts.append(lin(res["stabilite_marge_pts"], c["bareme_ecart_type"]))
    if parts:
        res["regularite"] = round(sum(parts) / len(parts))
    return res


def altman(a0: dict, cap_c) -> dict | None:
    """Z-score d'Altman (modèle d'origine, sociétés non financières) : 1,2 A + 1,4 B + 3,3 C + 0,6 D + 1,0 E."""
    ta = a0.get("actifs")
    besoin = (a0.get("actifs_courants"), a0.get("passifs_courants"), a0.get("benefices_non_distribues"), a0.get("ebit"),
              a0.get("passifs_totaux"), a0.get("ca"))
    if not ta or ta <= 0 or not cap_c or any(x is None for x in besoin) or not a0["passifs_totaux"]:
        return None
    a = (a0["actifs_courants"] - a0["passifs_courants"]) / ta
    b = a0["benefices_non_distribues"] / ta
    c = a0["ebit"] / ta
    d = cap_c / a0["passifs_totaux"]
    e = a0["ca"] / ta
    z = 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e
    return {"z": round(z, 2), "composantes": {"fonds_roulement": round(a, 3), "benefices_non_distribues": round(b, 3), "ebit": round(c, 3),
                                              "capitalisation_passifs": round(d, 3), "rotation_actifs": round(e, 3)}}


def zone_altman(z: float | None, cfg: dict) -> str | None:
    if z is None:
        return None
    return "sûre" if z > cfg["altman"]["zone_sure"] else "grise" if z >= cfg["altman"]["zone_detresse"] else "détresse"


def beneish(a0: dict, a1: dict | None) -> dict | None:
    """M-score de Beneish (8 variables) : −4,84 + 0,920 DSRI + 0,528 GMI + 0,404 AQI + 0,892 SGI + 0,115 DEPI
    − 0,172 SGAI + 4,679 TATA − 0,327 LVGI. DEPI et SGAI valent 1 (neutres) quand amortissements ou frais
    commerciaux manquent ; les autres variables sont obligatoires."""
    if not a1:
        return None

    def cogs(a):
        if a.get("cout_ventes") is not None:
            return a["cout_ventes"]
        return a["ca"] - a["marge_brute"] if a.get("ca") is not None and a.get("marge_brute") is not None else None
    try:
        s0, s1 = a0["ca"], a1["ca"]
        dsri = (a0["creances"] / s0) / (a1["creances"] / s1)
        gm0, gm1 = (s0 - cogs(a0)) / s0, (s1 - cogs(a1)) / s1
        gmi = gm1 / gm0
        aqi = (1 - (a0["actifs_courants"] + a0["immobilisations"]) / a0["actifs"]) / (1 - (a1["actifs_courants"] + a1["immobilisations"]) / a1["actifs"])
        sgi = s0 / s1
        lv0 = (a0["passifs_courants"] + (a0.get("dette_lt") or 0)) / a0["actifs"]
        lv1 = (a1["passifs_courants"] + (a1.get("dette_lt") or 0)) / a1["actifs"]
        lvgi = lv0 / lv1
        tata = (a0["resultat_net"] - a0["cfo"]) / a0["actifs"]
    except (KeyError, TypeError, ZeroDivisionError):
        return None
    neutres = []
    try:
        depi = (a1["amortissements"] / (a1["amortissements"] + a1["immobilisations"])) / (a0["amortissements"] / (a0["amortissements"] + a0["immobilisations"]))
    except (KeyError, TypeError, ZeroDivisionError):
        depi = 1.0
        neutres.append("DEPI")
    try:
        sgai = (a0["sga"] / s0) / (a1["sga"] / s1)
    except (KeyError, TypeError, ZeroDivisionError):
        sgai = 1.0
        neutres.append("SGAI")
    m = -4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi
    return {"m": round(m, 2), "neutres": neutres,
            "variables": {k: round(v, 3) for k, v in (("DSRI", dsri), ("GMI", gmi), ("AQI", aqi), ("SGI", sgi), ("DEPI", depi),
                                                       ("SGAI", sgai), ("LVGI", lvgi), ("TATA", tata))}}


def cycle_cash(a0: dict) -> dict | None:
    """Jours de créances + jours de stocks − jours de fournisseurs (stocks absents : 0, cas des services)."""
    ca = a0.get("ca")
    cogs = a0.get("cout_ventes")
    if cogs is None and ca is not None and a0.get("marge_brute") is not None:
        cogs = ca - a0["marge_brute"]
    if not ca or ca <= 0 or not cogs or cogs <= 0 or a0.get("creances") is None or a0.get("fournisseurs") is None:
        return None
    dso = a0["creances"] / ca * 365
    dio = (a0.get("stocks") or 0) / cogs * 365
    dpo = a0["fournisseurs"] / cogs * 365
    return {"jours": round(dso + dio - dpo), "creances": round(dso), "stocks": round(dio), "fournisseurs": round(dpo)}


def mesures_avancees(s: dict, m: dict, cap_c, cfg: dict | None = None) -> dict:
    """Indicateurs de l'analyse approfondie (ajoutés aux mesures de base)."""
    cfg = cfg or config_defaut()
    an = s.get("annuel") or []
    a0 = an[0] if an else {}
    a1 = an[1] if len(an) > 1 else None
    fin = s.get("financier")
    serie = serie_annuelle(s, cfg["normalisation"]["annees"])
    res = {}
    # Valeur et cycle
    if not fin and a0.get("fcf") is not None and cap_c:
        res["fcf_yield"] = a0["fcf"] / cap_c * 100
    res.update(normalisation(serie, s.get("resultat_net_ttm"), cfg))
    if not fin and m.get("roic") is not None:
        w = wacc(s, a0, cap_c, cfg)
        if w:
            res["wacc"] = w
            res["roic_wacc"] = m["roic"] - w["wacc"]
    res.update(regularite(serie, cfg))
    flux = [a0.get(k) for k in ("dividendes", "rachats", "emissions")]
    if cap_c and any(x is not None for x in flux):
        div, rach, emis = (abs(x or 0) for x in flux)
        res["rendement_actionnaire"] = (div + rach - emis) / cap_c * 100
        res["rendement_actionnaire_detail"] = {"dividendes": round(div / cap_c * 100, 2), "rachats": round(rach / cap_c * 100, 2),
                                               "emissions": round(emis / cap_c * 100, 2)}
    # Solidité et fiabilité
    if not fin:
        z = altman(a0, cap_c)
        if z:
            res["altman"] = {**z, "zone": zone_altman(z["z"], cfg)}
            res["altman_z"] = z["z"]
        b = beneish(a0, a1)
        if b:
            res["beneish"] = {**b, "suspect": b["m"] > cfg["beneish"]["seuil"]}
            res["mscore"] = b["m"]
        cr = _div(a0.get("actifs_courants"), a0.get("passifs_courants"))
        if cr is not None:
            res["current_ratio"] = cr
        if res.get("altman", {}).get("zone") == "détresse":
            # Détresse confirmée par un autre signe de fragilité (le Z-score seul pénalise les filiales de financement
            # et les sociétés qui ont beaucoup racheté leurs actions)
            c = cfg["altman"]["confirmation"]
            signes = []
            if m.get("couverture_interets") is not None and m["couverture_interets"] < c["couverture_interets_max"]:
                signes.append(f"couverture des intérêts {nb(m['couverture_interets'], 1)}×")
            if a0.get("fcf") is not None and a0["fcf"] < 0:
                signes.append("flux de trésorerie disponible négatif")
            if cr is not None and cr < c["current_ratio_min"]:
                signes.append(f"current ratio {nb(cr, 2)}")
            res["altman"]["confirme"] = bool(signes)
            res["altman"]["signes"] = signes
    gw = a0.get("goodwill")
    base_gw = "goodwill"
    if gw is None and a0.get("goodwill_incorporels") is not None:
        gw, base_gw = a0["goodwill_incorporels"], "goodwill et incorporels"
    if gw is not None and a0.get("actifs"):
        res["goodwill_actif"] = gw / a0["actifs"] * 100
        res["goodwill_base"] = base_gw
    # Qualité
    if not fin:
        mb = _div(a0.get("marge_brute"), a0.get("ca"))
        if mb is not None and 0 <= mb <= 1:
            res["marge_brute"] = mb * 100
        cc = cycle_cash(a0)
        if cc:
            res["cycle_cash"] = cc["jours"]
            res["cycle_cash_detail"] = cc
        if a0.get("capex") is not None and a0.get("amortissements"):
            res["capex_amortissements"] = abs(a0["capex"]) / abs(a0["amortissements"])
        if s.get("secteur_gics") in cfg["secteurs_rd"] and a0.get("ca"):
            if a0.get("rd") is not None:
                res["intensite_rd"] = abs(a0["rd"]) / a0["ca"] * 100
    # Alignement
    if s.get("detention_dirigeants") is not None and 0 <= s["detention_dirigeants"] <= 1:
        res["detention_dirigeants"] = s["detention_dirigeants"] * 100
    a3 = an[3] if len(an) > 3 else None
    if a3 and a0.get("actions") and a3.get("actions"):
        res["evolution_actions"] = (a0["actions"] / a3["actions"] - 1) * 100
    return res


# ------------------------------------------------------------------ notes, affichage, familles

def notes(m: dict, financier: str | None, cfg: dict) -> dict:
    b = cfg["baremes"]
    n = {}
    for cle in LIBELLES:
        v = m.get(cle)
        if v is None:
            if cle == "benefices_normalises" and m.get("benefice_moyen") is not None and m.get("benefice_actuel") is not None and m["benefice_actuel"] <= 0 < m["benefice_moyen"]:
                n[cle] = b["benefice_actuel_negatif"]
            continue
        if cle == "regularite":
            n[cle] = int(v)
            continue
        if cle == "benefices_normalises" and m.get("exces_marge") is not None:
            v = m["exces_marge"]  # note sur la part du bénéfice que la croissance du CA n'explique pas
        note = lin(v, b[cle])
        if cle == "marge_brute" and m.get("stabilite_marge_brute_pts") is not None:
            e = m["stabilite_marge_brute_pts"]
            note += 5 if e <= cfg["regularite"]["marge_brute_stable_pts"] else -5 if e >= cfg["regularite"]["marge_brute_instable_pts"] else 0
        n[cle] = max(0, min(100, note))
    if financier:
        n = {k: v for k, v in n.items() if k in FINANCIERS}
    return n


def affichage(cle: str, m: dict) -> tuple[str, str]:
    """(valeur affichée, complément) d'un indicateur."""
    v = m.get(cle)
    if v is None:
        if cle == "benefices_normalises" and m.get("benefice_actuel") is not None and m["benefice_actuel"] <= 0:
            return "bénéfice négatif", f"moyenne sur {m.get('benefice_moyen_annees')} ans positive"
        return "non disponible", ""
    if cle == "fcf_yield":
        return f"{nb(v, 1)} %", "flux de trésorerie disponible / capitalisation"
    if cle == "benefices_normalises":
        c = f"moyenne sur {m.get('benefice_moyen_annees')} ans"
        if m.get("exces_marge") is not None:
            c += f" ; corrigé de la croissance du CA : {nb(m['exces_marge'], 2)}×"
        return f"{nb(v, 2)}×", c + (" · sommet de cycle possible" if m.get("sommet_cycle") else "")
    if cle == "roic_wacc":
        w = m.get("wacc") or {}
        return f"{nb(v, 1, signe=True)} pt", f"ROIC {nb(m.get('roic'), 1)} % ; coût du capital estimé {nb(w.get('wacc', 0), 1)} %"
    if cle == "regularite":
        parts = []
        if m.get("regularite_croissance_pct") is not None:
            parts.append(f"CA en hausse {m['regularite_croissance_pct']} % des années")
        if m.get("stabilite_marge_pts") is not None:
            parts.append(f"écart-type de la marge op. {nb(m['stabilite_marge_pts'], 1)} pt")
        return f"{int(v)}/100", " ; ".join(parts) + (f" ({m.get('regularite_annees')} exercices)" if m.get("regularite_annees") else "")
    if cle == "rendement_actionnaire":
        d = m.get("rendement_actionnaire_detail") or {}
        return f"{nb(v, 1, signe=True)} %", f"dividendes {nb(d.get('dividendes', 0), 1)} % + rachats {nb(d.get('rachats', 0), 1)} % − émissions {nb(d.get('emissions', 0), 1)} %"
    if cle == "altman_z":
        return nb(v, 2), f"zone {(m.get('altman') or {}).get('zone')}"
    if cle == "mscore":
        b = m.get("beneish") or {}
        c = "au-dessus du seuil : manipulation possible" if b.get("suspect") else "sous le seuil"
        return nb(v, 2), c + (f" ; {', '.join(b['neutres'])} neutres (données manquantes)" if b.get("neutres") else "")
    if cle == "goodwill_actif":
        return f"{nb(v, 1)} %", m.get("goodwill_base") or ""
    if cle == "current_ratio":
        return f"{nb(v, 2)}×", "actifs courants / passifs courants"
    if cle == "marge_brute":
        e = m.get("stabilite_marge_brute_pts")
        return f"{nb(v, 1)} %", f"écart-type sur 5 ans : {nb(e, 1)} pt" if e is not None else ""
    if cle == "cycle_cash":
        d = m.get("cycle_cash_detail") or {}
        return f"{nb(v, 0)} jours", f"créances {d.get('creances')} j + stocks {d.get('stocks')} j − fournisseurs {d.get('fournisseurs')} j"
    if cle == "capex_amortissements":
        return f"{nb(v, 2)}×", "au-dessus de 1 : investissement supérieur à l'usure des actifs"
    if cle == "intensite_rd":
        return f"{nb(v, 1)} %", "R&D / chiffre d'affaires"
    if cle == "detention_dirigeants":
        return f"{nb(v, 1)} %", "dirigeants et administrateurs (Yahoo Finance)"
    if cle == "evolution_actions":
        return f"{nb(v, 1, signe=True)} %", "baisse : rachats nets ; hausse : dilution"
    return nb(v, 2), ""


def indicateurs(m: dict, n: dict) -> dict:
    res = {}
    for cle in LIBELLES:
        if cle not in n:
            continue
        aff, compl = affichage(cle, m)
        res[cle] = {"libelle": LIBELLES[cle], "valeur": _r(m.get(cle)), "note": n[cle], "affichage": aff, "complement": compl}
    return res


def sous_notes(n_tous: dict, cfg: dict) -> dict:
    """Note de chaque famille = moyenne des notes disponibles de ses indicateurs."""
    res = {}
    for fam, cles in cfg["familles"].items():
        v = [n_tous[k] for k in cles if k in n_tous]
        res[fam] = {"nom": NOMS_FAMILLES.get(fam, fam), "note": round(sum(v) / len(v)) if v else None, "indicateurs": len(v),
                    "cles": [k for k in cles if k in n_tous]}
    return res


def alertes(m: dict) -> list[dict]:
    """Signal d'alerte comptable issu du M-score (bloque « Acheter » et les pépites, comme les autres alertes)."""
    b = m.get("beneish")
    if b and b.get("suspect"):
        return [{"cle": "mscore", "titre": "M-score de Beneish suspect",
                 "texte": f"M-score de {nb(b['m'], 2)}, au-dessus du seuil de détection : manipulation des résultats possible, à vérifier dans le rapport annuel"}]
    return []


def details(m: dict) -> dict:
    """Informations affichées sous les familles (hypothèses du coût du capital, zones, variables)."""
    d = {}
    for cle in ("wacc", "altman", "beneish", "cycle_cash_detail", "rendement_actionnaire_detail"):
        if m.get(cle):
            d[cle] = m[cle]
    if m.get("benefice_moyen") is not None:
        d["normalisation"] = {"benefice_moyen": m["benefice_moyen"], "annees": m.get("benefice_moyen_annees"),
                              "benefice_actuel": m.get("benefice_actuel"), "ratio": _r(m.get("benefices_normalises")),
                              "exces_marge": _r(m.get("exces_marge")),
                              "sommet_cycle": bool(m.get("sommet_cycle")), "fcf_moyen": m.get("fcf_moyen")}
    return d
