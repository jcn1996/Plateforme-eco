"""
Niveau de risque mondial : indicateurs de stress, percentiles sur 10 ans, score /100, palier.

- Chaque indicateur est placé dans sa distribution historique (jusqu'à 10 ans) : son score est
  son percentile (100 = niveau de stress le plus élevé observé).
- Score mondial = moyenne pondérée des scores des indicateurs disponibles (pondérations en config).
- Seuils des paliers : percentiles de la distribution historique du score lui-même (au moins
  5 ans d'historique), sinon valeurs fixes de la config.
- Changement de palier : au moins deux indicateurs concordants, de familles différentes, doivent
  être eux-mêmes au niveau du nouveau palier ; sinon le palier précédent est conservé
  (changement « en attente »).
"""
from __future__ import annotations

from datetime import timedelta

from . import calculs as C


def id_source(src: dict) -> str:
    if src["type"] == "yahoo":
        return f"yahoo:{src['symbole']}"
    if src["type"] == "fred":
        return f"fred:{src['serie']}"
    if src["type"] == "bce":
        return f"bce:{src['flux']}:{src['cle']}"
    if src["type"] == "ecart_souverain":
        return f"ecart:{src['pays']}"
    raise ValueError(src["type"])


def sources_indicateur(cfg_ind: dict) -> list[tuple[str, str]]:
    """[(identifiant de série, nom de la source)], principale en tête."""
    res = [(id_source(s), s["nom"]) for s in cfg_ind["sources"]]
    for s in cfg_ind["sources"]:
        if s["type"] == "ecart_souverain":
            res.append((f"ecart_bce:{s['pays']}", f"BCE Data Portal, taux à 10 ans (IRS, convergence), {s['pays']} − DE, mensuel"))
    return res


def transformer(serie, cfg_ind: dict):
    if cfg_ind.get("transformation") == "variation_3m":
        return C.serie_variation(serie, 63)
    return list(serie)


AGE_MAX = {"pts": 7, "pt": 45, "": 14, "%": 7}  # âge maximal d'un point pour le score historique


def construire_indicateurs(series: dict, config: dict, aujourdhui) -> dict:
    """Pour chaque indicateur : série retenue, valeur, percentile, tendance, vérification croisée."""
    debut = (C.jour(aujourdhui) - timedelta(days=365 * config["historique_annees"] + 5)).isoformat()
    res = {}
    for cle, ci in config["indicateurs"].items():
        srcs = sources_indicateur(ci)
        disponibles = [(i, nom) for i, nom in srcs if series.get(i)]
        if not disponibles:
            res[cle] = {"cle": cle, "nom": ci["nom"], "famille": ci["famille"], "disponible": False, "facultatif": bool(ci.get("facultatif")),
                        "poids": ci["poids"], "sources_valides": [], "sources_configurees": [n for _, n in srcs]}
            continue
        id_principal, nom_principal = disponibles[0]
        serie = [p for p in transformer(series[id_principal], ci) if p[0] >= debut]
        if len(serie) < 10:
            res[cle] = {"cle": cle, "nom": ci["nom"], "famille": ci["famille"], "disponible": False, "facultatif": bool(ci.get("facultatif")),
                        "poids": ci["poids"], "sources_valides": [], "sources_configurees": [n for _, n in srcs]}
            continue
        d, v = serie[-1]
        tries = sorted(p[1] for p in serie)
        pct = C.percentile(tries, v)
        # Vérification croisée : dernière date commune avec la source secondaire
        verification, ecart, valeur_controle = "source_unique", None, None
        for i2, nom2 in disponibles[1:]:
            s2 = transformer(series[i2], ci)
            p2 = C.valeur_a(s2, d, 10)
            p1 = C.valeur_a(serie, p2[0]) if p2 is not None else None
            if p1 is not None and p1[0] == p2[0]:  # comparaison à la même date
                ecart = round(abs(p2[1] - p1[1]), 3)
                valeur_controle = {"source": nom2, "valeur": round(p2[1], 3), "date": p2[0], "valeur_principale": round(p1[1], 3)}
                verification = "concordant" if ecart <= ci.get("tolerance", max(0.15, abs(v) * 0.1)) else "divergent"
                break
        # Tendance : valeur un mois plus tôt
        il_y_a_1m = C.valeur_a(serie, C.jour(d) - timedelta(days=30))
        variation_1m = round(v - il_y_a_1m[1], 3) if il_y_a_1m else None
        ecart_type = (sum((x - sum(tries) / len(tries)) ** 2 for x in tries) / len(tries)) ** 0.5
        if variation_1m is None:
            sens = None
        elif abs(variation_1m) < 0.15 * ecart_type:
            sens = "stable"
        else:
            sens = "hausse" if variation_1m > 0 else "baisse"
        annees = round((C.jour(d) - C.jour(serie[0][0])).days / 365.25, 1)
        res[cle] = {
            "cle": cle, "nom": ci["nom"], "famille": ci["famille"], "disponible": True, "facultatif": bool(ci.get("facultatif")),
            "poids": ci["poids"], "unite": ci["unite"], "decimales": ci.get("decimales", 2),
            "valeur": round(v, 4), "date": d, "percentile": pct, "score": pct, "historique_annees": annees,
            "min_historique": round(tries[0], 3), "max_historique": round(tries[-1], 3), "mediane_historique": round(tries[len(tries) // 2], 3),
            "variation_1m": variation_1m, "tendance": sens, "source": nom_principal, "secours": id_principal != srcs[0][0],
            "verification": verification, "ecart_sources": ecart, "controle": valeur_controle,
            "sources_valides": [n for _, n in disponibles], "sources_configurees": [n for _, n in srcs],
            "_serie": serie, "_tries": tries,
        }
    return res


def score_pondere(scores: dict[str, float], poids: dict[str, float], part_min: float = 0.5):
    total = sum(poids.values())
    dispo = {k: s for k, s in scores.items() if s is not None}
    w = sum(poids[k] for k in dispo)
    if not total or w / total < part_min:
        return None
    return round(sum(poids[k] * s for k, s in dispo.items()) / w, 1)


def historique_score(inds: dict, aujourdhui, annees: int) -> list[list]:
    """Score mondial recalculé chaque vendredi sur `annees` ans (percentiles sur toute la période)."""
    actifs = {k: i for k, i in inds.items() if i["disponible"]}
    poids = {k: i["poids"] for k, i in actifs.items()}
    fin = C.jour(aujourdhui)
    d = fin - timedelta(days=365 * annees)
    d += timedelta(days=(4 - d.weekday()) % 7)
    res = []
    while d <= fin:
        scores = {}
        for k, i in actifs.items():
            p = C.valeur_a(i["_serie"], d, AGE_MAX.get(i["unite"], 14))
            scores[k] = C.percentile(i["_tries"], p[1]) if p else None
        s = score_pondere(scores, poids)
        if s is not None:
            res.append([d.isoformat(), s])
        d += timedelta(days=7)
    return res


def seuils(historique: list[list], config: dict) -> dict:
    cfg = config["seuils"]
    if historique:
        annees = (C.jour(historique[-1][0]) - C.jour(historique[0][0])).days / 365.25
    else:
        annees = 0
    if annees >= cfg["annees_min"]:
        valeurs = sorted(x[1] for x in historique)
        res = {p: round(valeurs[min(len(valeurs) - 1, int(len(valeurs) * q / 100))], 1) for p, q in cfg["percentiles"].items()}
        # Seuils strictement croissants
        precedent = 0
        for p in config["paliers"][1:]:
            res[p] = max(res[p], precedent + 1)
            precedent = res[p]
        return {**res, "methode": f"percentiles {', '.join(f'{q}' for q in cfg['percentiles'].values())} du score sur {annees:.1f} ans",
                "annees": round(annees, 1)}
    return {**cfg["fixes"], "methode": f"seuils fixes (historique de {annees:.1f} an(s), moins de {cfg['annees_min']} ans)", "annees": round(annees, 1)}


def palier_de(score: float | None, s: dict, paliers: list[str]) -> str | None:
    if score is None:
        return None
    res = paliers[0]
    for p in paliers[1:]:
        if score >= s[p]:
            res = p
    return res


def decider_palier(etat_palier: dict | None, brut: str, inds: dict, s: dict, config: dict, aujourdhui: str) -> tuple[dict, dict | None]:
    """Applique la règle des deux signaux concordants. Renvoie (nouvel état du palier, changement en attente)."""
    paliers = config["paliers"]
    if not etat_palier or etat_palier.get("actuel") not in paliers:
        return {"actuel": brut, "depuis": aujourdhui, "precedent": None, "changement_le": None, "initial": True}, None
    actuel = etat_palier["actuel"]
    if brut == actuel:
        return etat_palier, None
    hausse = paliers.index(brut) > paliers.index(actuel)
    concordants = []
    for k, i in inds.items():
        if not i["disponible"]:
            continue
        niveau = palier_de(i["score"], s, paliers)
        if (hausse and paliers.index(niveau) >= paliers.index(brut)) or (not hausse and paliers.index(niveau) <= paliers.index(brut)):
            concordants.append(i)
    familles = sorted({i["famille"] for i in concordants})
    mini = config["changement_palier"]["concordance_min"]
    if len(familles) >= mini:
        return {"actuel": brut, "depuis": aujourdhui, "precedent": actuel, "changement_le": aujourdhui,
                "concordants": [i["cle"] for i in concordants]}, None
    return etat_palier, {"vers": brut, "familles_concordantes": familles, "indicateurs_concordants": [i["cle"] for i in concordants],
                         "manque": mini - len(familles)}


def contributions(inds: dict) -> list[dict]:
    """Poids de chaque indicateur dans l'écart du score à la neutralité (50)."""
    actifs = [i for i in inds.values() if i["disponible"]]
    total = sum(i["poids"] for i in actifs) or 1
    res = [{"cle": i["cle"], "nom": i["nom"], "famille": i["famille"], "percentile": i["percentile"],
            "contribution": round(i["poids"] / total * (i["score"] - 50), 1)} for i in actifs]
    return sorted(res, key=lambda x: -abs(x["contribution"]))


def correlations(cours: dict, config: dict) -> dict:
    cfg = config["correlations"]
    actifs = cfg["actifs"]
    paires = []
    cles = list(actifs)
    for x in range(len(cles)):
        for y in range(x + 1, len(cles)):
            a, b = cles[x], cles[y]
            sa, sb = cours.get(actifs[a]["symbole"]), cours.get(actifs[b]["symbole"])
            if not sa or not sb:
                continue
            court, long_ = C.correlation(sa, sb, cfg["jours_court"]), C.correlation(sa, sb, cfg["jours_long"])
            if court is None:
                continue
            paires.append({"a": a, "b": b, "nom": f"{actifs[a]['nom']} / {actifs[b]['nom']}", "correlation_3m": court, "correlation_12m": long_,
                           "ecart": None if long_ is None else round(court - long_, 2)})
    return {"paires": paires, "source": "Yahoo Finance via yfinance, rendements quotidiens (" + ", ".join(a["symbole"] for a in actifs.values()) + ")"}


def texte_valeur(i: dict) -> str:
    unite = {"pts": "", "pt": " pt", "": "", "%": " %"}.get(i["unite"], " " + i["unite"])
    signe = i["unite"] == "%"
    return f"{C.fr(i['valeur'], i['decimales'], signe)}{unite}"


def synthese(score, etat_palier: dict, attente: dict | None, inds: dict, s: dict, config: dict, date_calcul: str) -> dict:
    """Explication factuelle, interprétations, confiance et « Ce qui pourrait me donner tort »."""
    contrib = contributions(inds)
    top = contrib[:3]
    actifs = [i for i in inds.values() if i["disponible"]]
    poids_total = sum(i["poids"] for i in inds.values() if not i["facultatif"])
    poids_dispo = sum(i["poids"] for i in actifs if not i["facultatif"])
    familles = {}
    for i in actifs:
        familles.setdefault(i["famille"], []).append(i["score"])
    moy_fam = {f: round(sum(v) / len(v), 1) for f, v in familles.items()}
    nfam = config["familles"]

    palier = etat_palier["actuel"]
    faits = [f"Score de stress financier mondial : {C.fr(score, 0)}/100 au {C.date_fr(date_calcul)} (palier « {palier} »"
             + (f" depuis le {C.date_fr(etat_palier['depuis'])}, précédent : « {etat_palier['precedent']} »" if etat_palier.get("precedent")
                else f" depuis le {C.date_fr(etat_palier['depuis'])}") + ")."]
    faits.append("Indicateurs qui pèsent le plus : " + " ; ".join(
        f"{inds[t['cle']]['nom']} à {texte_valeur(inds[t['cle']])} (percentile {C.fr(t['percentile'], 0)} sur {C.fr(inds[t['cle']]['historique_annees'], 0)} ans)"
        for t in top) + ".")
    explication = " ".join(faits)

    interpretations = []
    if moy_fam:
        haute = max(moy_fam, key=moy_fam.get)
        basse = min(moy_fam, key=moy_fam.get)
        if moy_fam[haute] - moy_fam[basse] >= 25:
            interpretations.append(f"Le stress se concentre sur la famille « {nfam.get(haute, haute)} » (percentile moyen {C.fr(moy_fam[haute], 0)}), "
                                   f"alors que la famille « {nfam.get(basse, basse)} » reste à un niveau bas (percentile moyen {C.fr(moy_fam[basse], 0)}).")
        else:
            interpretations.append(f"Les familles d'indicateurs sont cohérentes entre elles (percentiles moyens de {C.fr(min(moy_fam.values()), 0)} "
                                   f"à {C.fr(max(moy_fam.values()), 0)}).")
    if attente:
        interpretations.append(f"Le score correspond au palier « {attente['vers']} », mais le changement n'est pas confirmé : "
                               f"{len(attente['familles_concordantes'])} famille(s) concordante(s) sur {config['changement_palier']['concordance_min']} requises.")

    raisons, niveau = [], 2
    part = poids_dispo / poids_total if poids_total else 0
    if part < 0.85:
        niveau -= 1
        raisons.append(f"indicateurs disponibles : {round(100 * part)} % des pondérations")
    divergents = [i["nom"] for i in actifs if i["verification"] == "divergent"]
    if divergents:
        niveau -= 1
        raisons.append("sources divergentes : " + ", ".join(divergents))
    if len(moy_fam) >= 2 and max(moy_fam.values()) - min(moy_fam.values()) >= 40:
        niveau -= 1
        raisons.append("familles d'indicateurs discordantes")
    if attente:
        niveau -= 1
        raisons.append("changement de palier en attente de confirmation")
    if not raisons:
        raisons.append("indicateurs disponibles, sources concordantes, familles cohérentes")
    confiance = {"niveau": ["faible", "faible", "moyen", "élevé"][max(0, min(3, niveau + 1))], "raisons": raisons}

    contre = []
    vol = moy_fam.get("volatilite")
    cred = moy_fam.get("credit")
    if vol is not None and cred is not None and vol - cred >= 25:
        contre.append("Le stress vient surtout de la volatilité : sans élargissement des écarts de crédit, un pic de volatilité se résorbe souvent en quelques semaines.")
    if cred is not None and vol is not None and cred - vol >= 25:
        contre.append("Les écarts de crédit sont tendus mais la volatilité reste contenue : les marchés d'actions ne valident pas (encore) ce stress.")
    hebdo = [i["nom"] for i in actifs if i["cle"] in ("stlfsi", "nfci")]
    if hebdo:
        contre.append(f"Les indices officiels hebdomadaires ({', '.join(hebdo)}) sont publiés avec environ une semaine de retard.")
    if any(i["cle"] == "spread_it" for i in actifs):
        contre.append("Les écarts souverains reposent sur des moyennes mensuelles (OCDE) : un mouvement récent n'y apparaît pas encore.")
    if s.get("annees", 0) < config["seuils"]["annees_min"]:
        contre.append("L'historique disponible est court : les seuils des paliers sont fixes et non calés sur 10 ans.")
    if attente:
        contre.append(f"Un second signal concordant suffirait à faire passer le palier à « {attente['vers']} ».")
    manquants = [i["nom"] for i in inds.values() if not i["disponible"] and not i["facultatif"]]
    if manquants:
        contre.append("Indicateurs indisponibles pour cette mise à jour : " + ", ".join(manquants) + ".")
    return {"explication": explication, "faits": faits, "interpretations": interpretations, "confiance": confiance,
            "contre": contre, "principaux": top, "familles": {nfam.get(f, f): v for f, v in moy_fam.items()}}
