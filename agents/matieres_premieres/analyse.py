"""
Calculs de l'agent matières premières (fonctions pures, testées sans réseau).

Chaque sous-note est sur 100 : au-dessus de 50, le facteur est favorable à une exposition à la
matière première sur 3 à 12 mois ; en dessous, défavorable. Une sous-note sans donnée vaut None
et sa pondération est répartie sur les autres. Règles détaillées : regles.md.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from statistics import mean, pstdev

MOTS_INTERDITS = re.compile(r"\b(incroyable|exceptionnel\w*|énorme|explos\w*|flambée|euphori\w*|spectaculaire|"
                            r"fantastique|massi\w+|effondrement|krach|à ne pas manquer|immanquable)\b", re.I)
VERDICTS = ("Surpondérer", "Neutre", "Sous-pondérer")


# ------------------------------------------------------------------ outils

def jour(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def borne(x: float, bas: float = 5, haut: float = 95) -> int:
    return int(round(max(bas, min(haut, x))))


def fr(x: float | None, dec: int = 1, signe: bool = False) -> str:
    """Nombre à la française : 1 234,5 ; −2,1 ; +3,0 avec signe=True."""
    if x is None:
        return "n.d."
    texte = f"{abs(x):,.{dec}f}".replace(",", " ").replace(".", ",")
    if x < 0 and float(texte.replace(" ", "").replace(",", ".")) != 0:
        return "−" + texte
    return ("+" + texte) if signe else texte


def pct(x: float | None, dec: int = 1) -> str:
    return f"{fr(x, dec, True)} %"


def date_fr(d: str | None) -> str:
    if not d:
        return "date inconnue"
    d = str(d)
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) >= 10 else f"{d[5:7]}/{d[:4]}"


def valeur_a(serie, quand: date):
    """Dernière valeur à ou avant `quand` (série triée [(date, valeur)])."""
    res = None
    cible = quand.isoformat()
    for d, v in serie:
        if d <= cible:
            res = v
        else:
            break
    return res


def variation(serie, jours: int) -> float | None:
    if not serie:
        return None
    fin = jour(serie[-1][0])
    debut = valeur_a(serie, fin - timedelta(days=jours))
    if not debut:
        return None
    return (serie[-1][1] / debut - 1) * 100


def moyenne_mobile(serie, n: int = 200) -> float | None:
    """Moyenne des n dernières clôtures quotidiennes (la série est quotidienne sur ses 14 derniers mois)."""
    if len(serie) < n:
        return None
    return mean(v for _, v in serie[-n:])


def percentile(valeurs: list[float], x: float) -> float | None:
    if not valeurs:
        return None
    return round(sum(1 for v in valeurs if v <= x) / len(valeurs) * 100, 1)


def conformes(textes) -> bool:
    return not any(MOTS_INTERDITS.search(t or "") for t in textes)


def sous_note(note, texte: str, source: str, date_donnee: str | None, **details) -> dict:
    return {"note": note, "texte": texte, "source": source, "date": date_donnee, **details}


# ------------------------------------------------------------------ 1. tendance et momentum

def tendance(serie) -> dict | None:
    if not serie or len(serie) < 60:
        return None
    r1, r3, r12 = variation(serie, 30), variation(serie, 91), variation(serie, 365)
    if r3 is None:
        return None
    mm200 = moyenne_mobile(serie)
    dernier = serie[-1][1]
    au_dessus = mm200 is not None and dernier > mm200
    note = 50 + 0.8 * r3 + 0.3 * (r12 or 0) + (0 if mm200 is None else (5 if au_dessus else -5))
    morceaux = [f"{pct(r3)} sur 3 mois"]
    if r12 is not None:
        morceaux.append(f"{pct(r12)} sur 12 mois")
    if mm200 is not None:
        morceaux.append(f"{'au-dessus' if au_dessus else 'en dessous'} de sa moyenne 200 jours ({fr(mm200, 2)})")
    return sous_note(borne(note), "Cours " + ", ".join(morceaux), "Yahoo Finance (yfinance), contrat le plus proche", serie[-1][0],
                     variation_1m=_arr(r1), variation_3m=_arr(r3), variation_12m=_arr(r12), mm200=_arr(mm200, 4))


def _arr(x, dec=2):
    return None if x is None else round(x, dec)


# ------------------------------------------------------------------ 2. structure de la courbe

def courbe(contrats: list[dict], prix: dict, front: float | None, seuil: float) -> dict | None:
    """contrats : [{symbole, echeance}] ; prix : {symbole: [date, clôture]}.
    Rendement de roulement annualisé entre le premier contrat coté et celui d'environ 12 mois plus loin :
    positif = backwardation (prix futurs plus bas : marché tendu), négatif = contango (marché détendu)."""
    points = []
    for c in contrats:
        p = prix.get(c["symbole"])
        if not p or not p[1] or p[1] <= 0:
            continue
        if front and abs(p[1] / front - 1) > 0.5:  # donnée aberrante (contrat illiquide)
            continue
        points.append({"echeance": c["echeance"], "symbole": c["symbole"], "prix": p[1], "date": p[0]})
    if len(points) < 2:
        return None
    pres = points[0]
    a0, m0 = map(int, pres["echeance"].split("-"))

    def ecart(p):
        a, m = map(int, p["echeance"].split("-"))
        return (a - a0) * 12 + m - m0
    candidats = [p for p in points[1:] if ecart(p) >= 3]
    if not candidats:
        return None
    loin = min(candidats, key=lambda p: abs(ecart(p) - 12))
    mois = ecart(loin)
    roulement = (pres["prix"] / loin["prix"] - 1) * 12 / mois * 100
    structure = "backwardation" if roulement > seuil else "contango" if roulement < -seuil else "plate"
    lecture = {"backwardation": "prix futurs plus bas : marché tendu", "contango": "prix futurs plus élevés : marché détendu",
               "plate": "prix futurs proches du comptant"}[structure]
    note = borne(50 + roulement * 2.5, 10, 90)
    texte = (f"Courbe en {structure} ({lecture}) : rendement de roulement de {pct(roulement)} par an "
             f"entre {pres['echeance']} et {loin['echeance']}")
    return sous_note(note, texte, "Yahoo Finance (yfinance), contrats des échéances suivantes", max(p["date"] for p in points),
                     structure=structure, roulement_pct_an=round(roulement, 2), points=points)


# ------------------------------------------------------------------ 3. stocks

def _moyenne_5_ans(serie, d: date) -> float | None:
    valeurs = []
    for k in range(1, 6):
        cible = d - timedelta(days=round(365.25 * k))
        proches = [v for x, v in serie if abs((jour(x) - cible).days) <= 4]
        if proches:
            valeurs.append(proches[0])
    return mean(valeurs) if len(valeurs) >= 4 else None


def stocks_eia(series: dict, cles: list[str], cfg_eia: dict, seuils: dict) -> dict | None:
    details = []
    for cle in cles:
        s = series.get(cle) or []
        if len(s) < 60:
            continue
        d, v = s[-1]
        moy = _moyenne_5_ans(s, jour(d))
        if moy is None:
            continue
        variations = [b[1] - a[1] for a, b in zip(s, s[1:])][-260:]
        hebdo = s[-1][1] - s[-2][1]
        z = (hebdo - mean(variations)) / pstdev(variations) if len(variations) > 10 and pstdev(variations) else None
        details.append({"cle": cle, "libelle": cfg_eia[cle]["libelle"], "unite": cfg_eia[cle]["unite"], "date": d,
                        "valeur": round(v, 1), "moyenne_5_ans": round(moy, 1), "ecart_pct": round((v / moy - 1) * 100, 2),
                        "variation_hebdo": round(hebdo, 1), "z_hebdo": None if z is None else round(z, 2),
                        "choc": bool(z is not None and abs(z) >= seuils["choc_stocks_z"]),
                        "historique": [[x, round(y, 1)] for x, y in s[-53:]]})
    if not details:
        return None
    ecart = mean(x["ecart_pct"] for x in details)
    note = borne(50 - ecart * 2.5, 10, 90)
    principal = details[0]
    texte = (f"{principal['libelle'][0].upper()}{principal['libelle'][1:]} à {fr(principal['valeur'], 1)} {principal['unite']}, "
             f"{pct(principal['ecart_pct'])} par rapport à la moyenne sur 5 ans")
    if len(details) > 1:
        texte += f" ; écart moyen des {len(details)} séries suivies : {pct(ecart)}"
    return sous_note(note, texte, "EIA (département américain de l'Énergie), API v2", max(x["date"] for x in details),
                     series=details, ecart_moyen_pct=round(ecart, 2), type="eia")


def stocks_usda(cle: str, psd: dict | None, wasde: dict | None, seuils: dict) -> tuple[dict | None, str]:
    """Ratio stocks de fin de campagne / consommation mondiale. Renvoie (sous-note, vérification)."""
    historique = ((psd or {}).get("produits") or {}).get(cle) or {}
    w = ((wasde or {}).get("produits") or {}).get(cle)
    actuel, source, campagne = None, None, None
    if w:
        actuel = w["stocks_fin"] / w["consommation"] * 100
        campagne = w["campagne"]
        source = f"USDA, WASDE ({(wasde or {}).get('publication')})"
    annees = sorted(historique)
    if actuel is None and annees:
        a = annees[-1]
        actuel = historique[a]["stocks_fin"] / historique[a]["consommation"] * 100
        campagne = f"{a}/{(int(a) + 1) % 100:02d}"
        source = f"USDA, base PSD ({(psd or {}).get('publication')})"
    if actuel is None:
        return None, "aucune_source"
    an_courant = campagne[:4]
    passes = [historique[a]["stocks_fin"] / historique[a]["consommation"] * 100 for a in annees if a < an_courant]
    verification, note_verif = "source_unique", None
    if w and an_courant in historique:
        psd_ratio = historique[an_courant]["stocks_fin"] / historique[an_courant]["consommation"] * 100
        ecart = abs(psd_ratio / actuel - 1) * 100
        verification = "concordant" if ecart <= seuils["tolerance_wasde_psd_pct"] else "divergent"
        note_verif = f"base PSD : {fr(psd_ratio, 1)} % (écart {fr(ecart, 1)} %)"
    p = percentile(passes, actuel) if len(passes) >= 10 else None
    revision = None
    if w and w.get("precedent"):
        revision = (w["stocks_fin"] / w["precedent"]["stocks_fin"] - 1) * 100
    note = borne(85 - 0.7 * p, 10, 90) if p is not None else borne(50 - (actuel - 25) * 1.5, 15, 85)
    texte = f"Stocks mondiaux de fin de campagne {campagne} à {fr(actuel, 1)} % de la consommation"
    if p is not None:
        texte += f" (percentile {fr(p, 0)} depuis {annees[0]})"
    if revision is not None:
        texte += f" ; révision du mois : {pct(revision)} sur les stocks"
    return sous_note(note, texte, source, (wasde or psd or {}).get("publication"), type="usda", ratio_pct=round(actuel, 2),
                     percentile=p, campagne=campagne, revision_pct=_arr(revision),
                     choc=bool(revision is not None and abs(revision) >= seuils["revision_wasde_pct"]),
                     verification=verification, note_verification=note_verif,
                     historique=[[a, round(historique[a]["stocks_fin"] / historique[a]["consommation"] * 100, 2)] for a in annees[-15:]]), verification


# ------------------------------------------------------------------ 4. positionnement (CFTC)

def positionnement(lignes: list[dict], aujourdhui: date, seuils: dict) -> dict | None:
    if not lignes:
        return None
    lignes = sorted(lignes, key=lambda l: l["date"])
    debut = (jour(lignes[-1]["date"]) - timedelta(days=3 * 365 + 3)).isoformat()
    fen = [l for l in lignes if l["date"] >= debut]
    if len(fen) < 52:
        return None
    nets = [l["long"] - l["short"] for l in fen]
    dernier = fen[-1]
    net = nets[-1]
    p = percentile(nets, net)
    if p >= seuils["percentile_encombre"]:
        note, lecture = 25, "position très encombrée à l'achat : risque de retournement"
    elif p <= seuils["percentile_capitulation"]:
        note, lecture = 75, "position très vendeuse : lecture à contre-courant favorable"
    else:
        note, lecture = borne(50 + (50 - p) * 0.2), "position dans sa plage habituelle"
    part = net / dernier["oi"] * 100 if dernier.get("oi") else None
    var4 = net - nets[-5] if len(nets) >= 5 else None
    texte = (f"Position nette des gérants (managed money) de {fr(net, 0, True)} contrats"
             f"{f' ({fr(part, 1, True)} % de l’intérêt ouvert)' if part is not None else ''}, percentile {fr(p, 0)} sur 3 ans : {lecture}")
    return sous_note(note, texte, "CFTC, Commitments of Traders (disaggregated, contrats à terme), API Socrata", dernier["date"],
                     net=net, percentile=p, part_oi_pct=_arr(part), variation_4s=var4,
                     extreme="encombre" if p >= seuils["percentile_encombre"] else "capitulation" if p <= seuils["percentile_capitulation"] else None,
                     historique=[[l["date"], l["long"] - l["short"]] for l in fen[-52:]], marche=dernier.get("marche"))


# ------------------------------------------------------------------ 5. moteurs macro

def _var_pts(serie, jours=91):
    if not serie:
        return None
    fin = jour(serie[-1][0])
    debut = valeur_a(serie, fin - timedelta(days=jours))
    return None if debut is None else serie[-1][1] - debut


def macro(nature: str, ctx: dict) -> dict | None:
    """nature : or, argent, industriel, agricole. ctx : taux_reel, dollar (séries FRED), cycle (macro.json), palier (risque.json)."""
    tr, usd = ctx.get("taux_reel"), ctx.get("dollar")
    d_tr = _var_pts(tr)
    d_usd = variation(usd, 91) if usd else None
    cycle = ctx.get("cycle") or {}
    palier = ctx.get("palier")
    morceaux, sources, dates = [], [], []
    if nature in ("or", "argent"):
        if d_tr is None and d_usd is None:
            return None
        n_or = 50 - 30 * (d_tr or 0) - 3 * (d_usd or 0)
        if d_tr is not None:
            morceaux.append(f"taux réel américain à 10 ans à {fr(tr[-1][1], 2)} % ({fr(d_tr, 2, True)} pt sur 3 mois)")
            sources.append("FRED (DFII10)"); dates.append(tr[-1][0])
        if d_usd is not None:
            morceaux.append(f"dollar {pct(d_usd)} sur 3 mois")
            sources.append("FRED (DTWEXBGS)"); dates.append(usd[-1][0])
        note = n_or
        if nature == "argent" and cycle.get("cli") is not None:
            n_ind = 50 + (cycle["cli"] - 100) * 8 + (cycle.get("cli_3m") or 0) * 25
            note = 0.6 * n_or + 0.4 * n_ind
            morceaux.append(f"indicateur avancé de l'OCDE (G20) à {fr(cycle['cli'], 1)}")
            sources.append("agent macro (OCDE)")
    elif nature == "industriel":
        if cycle.get("cli") is None:
            return None
        note = 50 + (cycle["cli"] - 100) * 8 + (cycle.get("cli_3m") or 0) * 25 - 1.5 * (d_usd or 0)
        note += {"Reprise": 5, "Surchauffe": 3, "Ralentissement inflationniste": -5, "Expansion sans inflation": 0}.get(cycle.get("phase"), 0)
        morceaux.append(f"indicateur avancé de l'OCDE (G20) à {fr(cycle['cli'], 1)} ({fr(cycle.get('cli_3m'), 2, True)} pt sur 3 mois), "
                        f"phase « {cycle.get('phase', 'inconnue')} »")
        sources.append("agent macro (OCDE, phase du cycle)"); dates.append(cycle.get("date"))
        if d_usd is not None:
            morceaux.append(f"dollar {pct(d_usd)} sur 3 mois")
            sources.append("FRED (DTWEXBGS)")
        if palier in ("Tension", "Crise"):
            note -= 4 if palier == "Tension" else 8
            morceaux.append(f"palier de risque mondial « {palier} »")
            sources.append("agent risque")
    else:  # agricole
        if d_usd is None:
            return None
        note = 50 - 3 * d_usd
        morceaux.append(f"dollar {pct(d_usd)} sur 3 mois (un dollar plus faible soutient les prix en dollars)")
        sources.append("FRED (DTWEXBGS)"); dates.append(usd[-1][0])
    texte = morceaux[0][0].upper() + " ; ".join(morceaux)[1:]
    return sous_note(borne(note, 10, 90), texte, ", ".join(sources), max((d for d in dates if d), default=None),
                     variation_taux_reel_3m=_arr(d_tr), variation_dollar_3m=_arr(d_usd))


# ------------------------------------------------------------------ 6. contexte géopolitique

def geopolitique(m: dict, geo: dict | None, palier: str | None, aujourdhui: date, jours: int) -> dict | None:
    if geo is None and palier is None:
        return None
    cfg = m.get("geopolitique") or {}
    # Producteurs du premier rang (5 premiers) et zones sensibles pour l'approvisionnement (config « zones »)
    producteurs = {c for c, r in m.get("producteurs", []) if r <= 5} | set(cfg.get("zones", []))
    categories = set(cfg.get("categories", []))
    limite = (aujourdhui - timedelta(days=jours)).isoformat()
    retenus = []
    for e in (geo or {}).get("evenements", []):
        if e.get("categorie") not in categories:
            continue
        entrees = [c for c in (e.get("chronologie") or [e]) if (c.get("date") or "")[:10] >= limite]
        if not entrees:
            continue
        gravite = max((c.get("gravite") or 0) for c in entrees)
        pays = set(e.get("pays") or [])
        if gravite < 3 or not (pays & producteurs or e.get("mondial")):
            continue
        retenus.append({"titre": e.get("titre"), "gravite": gravite, "pays": sorted(pays & producteurs), "categorie": e.get("categorie_libelle") or e.get("categorie"),
                        "date": max(c.get("date") or "" for c in entrees)[:10]})
    retenus.sort(key=lambda r: (r["gravite"], r["date"]), reverse=True)
    poids = sum(r["gravite"] - 2 for r in retenus)
    note = 50 + min(25, poids * 3)
    morceaux = []
    if retenus:
        morceaux.append(f"{len(retenus)} événement{'s' if len(retenus) > 1 else ''} de gravité 3 ou plus en {jours} jours "
                        f"touchant les principaux producteurs ou l'approvisionnement (ex. « {retenus[0]['titre']} »)")
    else:
        morceaux.append(f"aucun événement de gravité 3 ou plus touchant les principaux producteurs en {jours} jours")
    if cfg.get("refuge") and palier:
        bonus = {"Vigilance": 3, "Tension": 8, "Crise": 15}.get(palier, 0)
        note += bonus
        morceaux.append(f"palier de risque mondial « {palier} » (rôle de valeur refuge)")
    texte = morceaux[0][0].upper() + " ; ".join(morceaux)[1:]
    return sous_note(borne(note, 20, 85), texte, "agent géopolitique (data/geopolitique.json)" + (", agent risque" if cfg.get("refuge") else ""),
                     (geo or {}).get("date"), evenements=retenus[:5])


# ------------------------------------------------------------------ 7. flux des ETF

def flux(par_etf: dict[str, dict]) -> dict | None:
    """par_etf : {etf: {periodes: {"1m": {...}, "3m": {...}}, encours, nom}} (calculés par l'agent)."""
    complets = {e: x for e, x in par_etf.items() if (x.get("periodes") or {}).get("1m", {}).get("complet")}
    if not par_etf:
        return None
    if not complets:
        jours = max(((x.get("periodes") or {}).get("1m") or {}).get("jours_disponibles") or 0 for x in par_etf.values())
        return sous_note(None, f"Flux des ETF ({', '.join(par_etf)}) en cours de constitution ({jours} jours d'historique sur 30)",
                         "Yahoo Finance (parts en circulation × valeur liquidative)", None, etf=par_etf, statut="en cours de constitution")
    total = sum(x["periodes"]["1m"]["flux_musd"] for x in complets.values())
    encours = sum((x.get("encours") or 0) for x in complets.values())
    part = total / (encours / 1e6) * 100 if encours else None
    note = borne(50 + (part or 0) * 6, 15, 85)
    texte = f"Flux nets sur 1 mois des ETF {', '.join(complets)} : {fr(total, 0, True)} M$" + (f" ({pct(part, 2)} de l'encours)" if part is not None else "")
    return sous_note(note, texte, "Yahoo Finance (parts en circulation × valeur liquidative)",
                     max((x["periodes"]["1m"].get("fin") or "" for x in complets.values()), default=None) or None,
                     etf=par_etf, flux_1m_musd=round(total, 1), part_encours_pct=_arr(part, 3), statut="complet")


# ------------------------------------------------------------------ 8. niveau historique

def niveau(serie, cpi) -> dict | None:
    if not serie:
        return None
    fin = jour(serie[-1][0])
    debut = (fin - timedelta(days=3653)).isoformat()
    points = [(d, v) for d, v in serie if d >= debut]
    if len(points) < 200 or jour(points[0][0]) > fin - timedelta(days=5 * 365):
        return None
    reel = points
    corrige = False
    if cpi:
        dernier_cpi = cpi[-1][1]
        reel = []
        for d, v in points:
            c = valeur_a(cpi, jour(d))
            if c:
                reel.append((d, v * dernier_cpi / c))
        corrige = len(reel) >= 200
        if not corrige:
            reel = points
    annees = round((fin - jour(points[0][0])).days / 365.25)
    p = percentile([v for _, v in reel], reel[-1][1])
    note = borne(80 - 0.6 * p, 15, 80)
    texte = (f"Cours {'corrigé de l’inflation américaine ' if corrige else ''}au percentile {fr(p, 0)} de sa plage sur {annees} ans "
             f"(plus bas {fr(min(v for _, v in points), 2)}, plus haut {fr(max(v for _, v in points), 2)} en valeur nominale)")
    return sous_note(note, texte, "Yahoo Finance (yfinance)" + (", FRED (CPIAUCSL)" if corrige else ""), serie[-1][0],
                     percentile=p, corrige_inflation=corrige, annees=annees,
                     plus_bas=round(min(v for _, v in points), 4), plus_haut=round(max(v for _, v in points), 4))


# ------------------------------------------------------------------ note globale, verdict, confiance

def note_globale(sous: dict[str, dict | None], ponderations: dict[str, float]) -> float | None:
    total = poids = 0.0
    for cle, w in ponderations.items():
        s = sous.get(cle)
        if w and s and s.get("note") is not None:
            total += w * s["note"]
            poids += w
    return round(total / poids, 1) if poids else None


def verdict(note: float | None, sous: dict, cfg: dict, precedent: str | None = None) -> tuple[str, list[str], list[str]]:
    """Renvoie (verdict, signaux favorables, signaux défavorables). Deux signaux concordants au minimum
    pour « Surpondérer » ou « Sous-pondérer » ; hystérésis autour des seuils pour éviter les allers-retours."""
    if note is None:
        return "Neutre", [], []
    fav = [k for k, s in sous.items() if s and s.get("note") is not None and s["note"] >= cfg["signal_favorable"]]
    defav = [k for k, s in sous.items() if s and s.get("note") is not None and s["note"] <= cfg["signal_defavorable"]]
    h = cfg["hysteresis"]
    haut = cfg["surponderer"] - (h if precedent == "Surpondérer" else 0)
    bas = cfg["sous_ponderer"] + (h if precedent == "Sous-pondérer" else 0)
    n = cfg["signaux_concordants_min"]
    if note >= haut and len(fav) >= n:
        return "Surpondérer", fav, defav
    if note <= bas and len(defav) >= n:
        return "Sous-pondérer", fav, defav
    return "Neutre", fav, defav


def confiance(sous: dict, note: float | None, indirect: bool = False) -> str:
    notes = [s["note"] for s in sous.values() if s and s.get("note") is not None]
    if note is None or len(notes) <= 3 or indirect:
        return "faible"
    dispersion = pstdev(notes) if len(notes) > 1 else 0
    if len(notes) >= 6 and abs(note - 50) >= 12 and dispersion < 20:
        return "élevé"
    return "moyen" if len(notes) >= 5 else "faible"


def arguments(sous: dict, libelles: dict) -> tuple[list[str], list[str]]:
    """3 arguments pour (sous-notes les plus favorables), 3 contre (les plus défavorables), sans doublon."""
    notes = sorted(((k, s) for k, s in sous.items() if s and s.get("note") is not None), key=lambda x: x[1]["note"], reverse=True)
    pour = [k for k, s in notes if s["note"] > 50][:3]
    contre = [k for k, s in reversed(notes) if s["note"] < 50 and k not in pour][:3]
    # Moins de 3 facteurs nettement orientés : on complète avec les plus proches de la neutralité
    reste = [k for k, _ in notes if k not in pour and k not in contre]
    while len(pour) < 3 and reste:
        pour.append(reste.pop(0))
    while len(contre) < 3 and reste:
        contre.append(reste.pop())
    f = lambda k: f"{libelles[k]} ({sous[k]['note']}/100) : {sous[k]['texte']}."
    return [f(k) for k in pour], [f(k) for k in contre]


def invalidations(v: str, m: dict, sous: dict, serie, seuils: dict) -> list[str]:
    """Deux conditions précises qui invalideraient le verdict."""
    u = m.get("unite", "")
    t = sous.get("tendance") or {}
    mm = t.get("mm200")
    trois_mois = [x for d, x in serie if d >= (jour(serie[-1][0]) - timedelta(days=91)).isoformat()] if serie else []
    haut3, bas3 = (max(trois_mois), min(trois_mois)) if trois_mois else (None, None)
    c, s, p = sous.get("courbe"), sous.get("stocks"), sous.get("positionnement")
    res = []
    if v == "Surpondérer":
        if mm:
            res.append(f"une clôture sous la moyenne 200 jours ({fr(mm, 2)} {u})")
        if c:
            res.append(f"un passage de la courbe en contango au-delà de {fr(seuils['structure_pct_an'], 0)} % par an (aujourd'hui {pct(c['roulement_pct_an'])})")
        if p:
            res.append(f"une position nette des gérants au-delà du percentile {seuils['percentile_encombre']} sur 3 ans (aujourd'hui {fr(p['percentile'], 0)})")
        if s and s.get("type") == "eia":
            res.append(f"des stocks repassant au-dessus de leur moyenne sur 5 ans (écart actuel {pct(s['ecart_moyen_pct'])})")
    elif v == "Sous-pondérer":
        if mm:
            res.append(f"une clôture au-dessus de la moyenne 200 jours ({fr(mm, 2)} {u})")
        if s and s.get("type") == "eia":
            res.append(f"des stocks repassant sous leur moyenne sur 5 ans (écart actuel {pct(s['ecart_moyen_pct'])})")
        if s and s.get("type") == "usda":
            res.append(f"une révision en baisse de plus de {fr(seuils['revision_wasde_pct'], 0)} % des stocks mondiaux de fin de campagne (WASDE)")
        if c:
            res.append(f"un passage de la courbe en backwardation au-delà de {fr(seuils['structure_pct_an'], 0)} % par an (aujourd'hui {pct(c['roulement_pct_an'])})")
        if p:
            res.append(f"une position nette des gérants sous le percentile {seuils['percentile_capitulation']} sur 3 ans (capitulation ; aujourd'hui {fr(p['percentile'], 0)})")
    else:
        if haut3:
            res.append(f"une clôture au-dessus du plus haut de 3 mois ({fr(haut3, 2)} {u}) avec au moins deux sous-notes favorables")
        if bas3:
            res.append(f"une clôture sous le plus bas de 3 mois ({fr(bas3, 2)} {u}) avec au moins deux sous-notes défavorables")
    if len(res) < 2:
        res.append("une note globale qui franchit 60 ou 40 lors d'une prochaine exécution")
    return res[:2]


def donner_tort(v: str, m: dict, sous: dict, contre: list[str], pour: list[str]) -> str:
    risque = m.get("risque_specifique")
    if v == "Surpondérer":
        base = f"Le principal point faible : {contre[0][0].lower() + contre[0][1:]}" if contre else ""
        return f"{base} Le scénario serait contredit par {risque}.".strip()
    if v == "Sous-pondérer":
        base = f"Le principal point fort : {pour[0][0].lower() + pour[0][1:]}" if pour else ""
        return f"{base} Un choc d'offre ou une reprise de la demande contredirait cette lecture prudente.".strip()
    return f"Les signaux se compensent ; une rupture nette dans un sens (cours, stocks ou positionnement) suffirait à trancher. Risque propre : {risque}."


def verdict_famille(notes: list[float], verdicts: list[str], cfg: dict) -> str:
    if not notes:
        return "Neutre"
    moy = mean(notes)
    sur, sous_ = verdicts.count("Surpondérer"), verdicts.count("Sous-pondérer")
    if moy >= cfg["surponderer"] - 5 and sur >= max(2, len(verdicts) / 2):
        return "Surpondérer"
    if moy <= cfg["sous_ponderer"] + 5 and sous_ >= max(2, len(verdicts) / 2):
        return "Sous-pondérer"
    return "Neutre"


# ------------------------------------------------------------------ signaux

def signaux(precedent: dict | None, actuel: dict, aujourdhui: date, seuils: dict) -> list[dict]:
    """Changement de verdict, positionnement extrême, retournement de la courbe, choc de stocks."""
    res = []
    anciens = {m["cle"]: m for m in (precedent or {}).get("matieres", [])}
    d = aujourdhui.isoformat()
    for m in actuel["matieres"]:
        a = anciens.get(m["cle"])
        nom = m["nom"]
        if a and a.get("verdict") != m["verdict"]:
            res.append({"date": d, "type": "changement_verdict", "cle": m["cle"], "importance": "forte",
                        "titre": f"{nom} : passage de « {a.get('verdict')} » à « {m['verdict']} »",
                        "explication": f"{nom} : note {fr(m['note'], 0)}/100 (précédente {fr(a.get('note'), 0)}), confiance {m['confiance']}. "
                                       + " ".join(m["arguments_pour"][:1] + m["arguments_contre"][:1]),
                        "source": "agent matières premières"})
        p = (m["sous_notes"].get("positionnement") or {})
        pa = ((a or {}).get("sous_notes") or {}).get("positionnement") or {}
        if p.get("extreme") and p.get("extreme") != pa.get("extreme") and p.get("date") != pa.get("date"):
            res.append({"date": d, "type": "positionnement_extreme", "cle": m["cle"], "importance": "moyenne",
                        "titre": f"{nom} : positionnement {'très encombré à l’achat' if p['extreme'] == 'encombre' else 'très vendeur'} (percentile {fr(p['percentile'], 0)} sur 3 ans)",
                        "explication": p["texte"] + ".", "source": p["source"]})
        c = m["sous_notes"].get("courbe") or {}
        ca = ((a or {}).get("sous_notes") or {}).get("courbe") or {}
        if c.get("structure") in ("contango", "backwardation") and ca.get("structure") in ("contango", "backwardation") and c["structure"] != ca["structure"]:
            res.append({"date": d, "type": "retournement_courbe", "cle": m["cle"], "importance": "moyenne",
                        "titre": f"{nom} : la courbe passe de {ca['structure']} à {c['structure']}",
                        "explication": c["texte"] + ".", "source": c["source"]})
        s = m["sous_notes"].get("stocks") or {}
        sa = ((a or {}).get("sous_notes") or {}).get("stocks") or {}
        if s.get("date") and s.get("date") != sa.get("date"):
            if s.get("type") == "eia":
                for x in s["series"]:
                    ancien = next((y for y in sa.get("series", []) if y["cle"] == x["cle"]), {})
                    franchit = ancien and (abs(x["ecart_pct"]) >= seuils["choc_stocks_ecart_pct"]) != (abs(ancien.get("ecart_pct", 0)) >= seuils["choc_stocks_ecart_pct"])
                    if x.get("choc") or franchit:
                        res.append({"date": d, "type": "choc_stocks", "cle": f"{m['cle']}-{x['cle']}", "importance": "moyenne",
                                    "titre": f"{nom} : {x['libelle']} {fr(x['variation_hebdo'], 1, True)} {x['unite']} sur la semaine ({pct(x['ecart_pct'])} par rapport à la moyenne sur 5 ans)",
                                    "explication": s["texte"] + ".", "source": s["source"]})
            elif s.get("choc"):
                res.append({"date": d, "type": "choc_stocks", "cle": m["cle"], "importance": "moyenne",
                            "titre": f"{nom} : stocks mondiaux révisés de {pct(s['revision_pct'])} (WASDE)",
                            "explication": s["texte"] + ".", "source": s["source"]})
    return res
