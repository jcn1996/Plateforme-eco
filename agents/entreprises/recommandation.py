"""
Recommandation à 12 mois (fonctions pures, testables sans réseau). Règles détaillées et seuils :
agents/entreprises/recommandation.md et la section « recommandation » de agents/entreprises/config.json.

Deux lectures :
  - si non détenu : Acheter / Acheter sur repli / Attendre / Éviter ;
  - si détenu     : Renforcer / Conserver / Alléger / Vendre.

Fourchette de valeur estimée par deux méthodes : multiples (PER et VE/EBITDA) comparés à la médiane
du secteur, et actualisation simplifiée des flux de trésorerie disponibles (hypothèses affichées).

Cinq signaux : note globale, valorisation (écart au cours), momentum 12 mois, qualité comptable, dynamique
des résultats (guidance, révisions des analystes, surprises).
« Acheter » ou « Vendre » exigent une confiance « moyen » ou « élevé » et au moins 3 signaux concordants ;
un signal d'alerte comptable interdit « Acheter » (et « Renforcer ») ; une guidance abaissée ou retirée depuis
moins de 90 jours aussi, sauf si la valorisation intègre déjà une forte baisse (exception justifiée).
"""
from __future__ import annotations

from ..pays.textes import nb

MENTION = "Avis indicatif généré automatiquement, sans prise en compte d'un profil ou d'une situation personnelle."
NON_DETENU = ("Acheter", "Acheter sur repli", "Attendre", "Éviter")
DETENU = ("Renforcer", "Conserver", "Alléger", "Vendre")
LIBELLES_SIGNAUX = {"note": "Note globale", "valorisation": "Valorisation", "momentum": "Momentum 12 mois",
                    "qualite": "Qualité comptable", "dynamique": "Dynamique des résultats"}


def _moyenne(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def prix_texte(v: float | None, devise: str | None) -> str:
    if v is None:
        return "n. d."
    return f"{nb(v, 2 if abs(v) < 1000 else 0)} {devise or ''}".strip()


# ------------------------------------------------------------------ valeur estimée

def valeur_multiples(m: dict, rn_ttm, ebitda, actions, financier) -> dict | None:
    """Valeur par action (devise des comptes) implicite si la société se payait au multiple médian de son secteur."""
    if not actions:
        return None
    estimations, detail = [], []
    ref_per = m.get("per_mediane_regionale") or m.get("per_mediane_mondiale")
    if ref_per and rn_ttm and rn_ttm > 0:
        estimations.append(ref_per * rn_ttm / actions)
        detail.append(f"PER médian du secteur {nb(ref_per, 1)}")
    ref_ev = m.get("ev_ebitda_mediane_regionale") or m.get("ev_ebitda_mediane_mondiale")
    if not financier and ref_ev and ebitda and ebitda > 0:
        v = (ref_ev * ebitda - (m.get("dette_nette") or 0)) / actions
        if v > 0:
            estimations.append(v)
            detail.append(f"VE/EBITDA médian du secteur {nb(ref_ev, 1)}")
    if not estimations:
        return None
    centrale = _moyenne(estimations)
    bas, haut = (min(estimations), max(estimations)) if len(estimations) > 1 else (centrale * 0.9, centrale * 1.1)
    return {"cle": "multiples", "nom": "Multiples comparés à la médiane du secteur", "bas": bas, "centrale": centrale, "haut": haut,
            "hypotheses": {"references": detail, "base": "médiane régionale du secteur, à défaut mondiale"}}


def actualiser(fcf: float, croissance: float, terminale: float, taux: float, annees: int) -> float:
    """Valeur actuelle des flux : croissance de `croissance` % ramenée linéairement à `terminale` % en `annees` ans,
    puis valeur terminale de Gordon-Shapiro."""
    r, gt = taux / 100, terminale / 100
    va, flux = 0.0, fcf
    for t in range(1, annees + 1):
        g = (croissance + (terminale - croissance) * (t - 1) / max(1, annees - 1)) / 100
        flux *= 1 + g
        va += flux / (1 + r) ** t
    return va + flux * (1 + gt) / (r - gt) / (1 + r) ** annees


def valeur_dcf(m: dict, fcf, actions, financier, region: str | None, cfg: dict) -> dict | None:
    """Actualisation simplifiée des flux de trésorerie disponibles (sociétés non financières, FCF positif)."""
    if financier or not actions or not fcf or fcf <= 0:
        return None
    base = m.get("croissance_ca_3ans") if m.get("croissance_ca_3ans") is not None else m.get("croissance_ca")
    g = cfg["croissance_defaut"] if base is None else max(cfg["croissance_min"], min(cfg["croissance_max"], base))
    taux = cfg["taux_base"] + cfg["primes_region"].get(region or "", cfg["primes_region"].get("autre", 0))
    gt, n, dn = cfg["croissance_terminale"], cfg["annees"], m.get("dette_nette") or 0

    def par_action(gg, tt):
        return (actualiser(fcf, gg, gt, tt, n) - dn) / actions
    centrale = par_action(g, taux)
    if centrale <= 0:
        return None
    ec_t, ec_g = cfg["ecart_taux"], cfg["ecart_croissance"]
    bas = max(0.0, par_action(max(0.0, g - ec_g), taux + ec_t))
    haut = par_action(g + ec_g, max(gt + 1.0, taux - ec_t))
    return {"cle": "dcf", "nom": "Flux de trésorerie disponibles actualisés", "bas": bas, "centrale": centrale, "haut": haut,
            "hypotheses": {"flux_initial": fcf, "croissance": round(g, 1), "croissance_terminale": gt, "taux_actualisation": round(taux, 1),
                           "annees": n, "fourchette": f"taux ±{nb(ec_t, 0)} pt, croissance ±{nb(ec_g, 0)} pt"}}


def valeur_estimee(m: dict, s: dict, cfg: dict) -> dict | None:
    """Fourchette de valeur par action, dans la devise de cotation. None si aucune méthode n'est calculable."""
    a0 = (s.get("annuel") or [{}])[0]
    actions = s.get("actions")
    rn_ttm = s.get("resultat_net_ttm") or a0.get("resultat_net")
    fx_c, fx_p = s.get("fx_comptes"), s.get("fx_cours")
    if s.get("devise_comptes") == s.get("devise_cours"):
        k = 1.0
    elif fx_c and fx_p:
        k = fx_c / fx_p
    else:
        return None
    methodes = [x for x in (valeur_multiples(m, rn_ttm, a0.get("ebitda"), actions, s.get("financier")),
                            valeur_dcf(m, a0.get("fcf"), actions, s.get("financier"), s.get("region"), cfg["dcf"])) if x]
    if not methodes:
        return None
    for x in methodes:
        for c in ("bas", "centrale", "haut"):
            x[c] = round(x[c] * k, 4)
    centrale = _moyenne(x["centrale"] for x in methodes)
    prix = s.get("prix")
    res = {"bas": round(_moyenne(x["bas"] for x in methodes), 4), "centrale": round(centrale, 4),
           "haut": round(_moyenne(x["haut"] for x in methodes), 4), "methodes": methodes,
           "ecart_pct": round((centrale / prix - 1) * 100, 1) if prix else None, "fiable": True, "reserve": None}
    # Méthodes très divergentes ou valeur sans rapport avec le cours : fourchette affichée, signal neutralisé
    if len(methodes) == 2:
        rapport = max(methodes[0]["centrale"], methodes[1]["centrale"]) / max(1e-9, min(methodes[0]["centrale"], methodes[1]["centrale"]))
        if rapport > cfg["divergence_max"]:
            res["fiable"], res["reserve"] = False, f"les deux méthodes divergent fortement (rapport de 1 à {nb(rapport, 1)})"
    if prix and not cfg["ecart_plausible"][0] <= (centrale / prix - 1) * 100 <= cfg["ecart_plausible"][1]:
        res["fiable"], res["reserve"] = False, "écart au cours hors de la plage plausible : estimation à vérifier"
    return res


# ------------------------------------------------------------------ signaux

def signaux(note: int, m: dict, valeur: dict | None, financier, cfg: dict, dynamique: dict | None = None) -> list[dict]:
    s = cfg["signaux"]
    res = []
    sens = 1 if note >= s["note_positive"] else -1 if note < s["note_negative"] else 0
    res.append({"cle": "note", "sens": sens, "texte": f"{note}/100"})
    if valeur and valeur.get("ecart_pct") is not None and valeur["fiable"]:
        e = valeur["ecart_pct"]
        sens = 1 if e >= s["valorisation_positive"] else -1 if e <= -s["valorisation_negative"] else 0
        res.append({"cle": "valorisation", "sens": sens, "texte": f"valeur estimée {nb(e, 1, signe=True)} % par rapport au cours"})
    else:
        res.append({"cle": "valorisation", "sens": 0, "texte": "non exploitable" + (f" ({valeur['reserve']})" if valeur and valeur.get("reserve") else "")})
    mo = m.get("momentum_12m")
    sens = 0 if mo is None else 1 if mo >= s["momentum_positif"] else -1 if mo <= s["momentum_negatif"] else 0
    res.append({"cle": "momentum", "sens": sens, "texte": "non disponible" if mo is None else f"{nb(mo, 1, signe=True)} %"})
    f = (m.get("fscore") or {}).get("score")
    if m.get("alertes"):
        sens, texte = -1, "signal d'alerte : " + m["alertes"][0]["titre"].lower()
    elif financier:
        roe = m.get("roe")
        sens = 1 if roe is not None and roe >= s["roe_financier_min"] else 0
        texte = "aucun signal d'alerte" + (f", ROE {nb(roe, 1)} %" if roe is not None else "")
    elif f is None:
        sens, texte = 0, "aucun signal d'alerte, F-score non calculable"
    else:
        sens = 1 if f >= s["fscore_positif"] else -1 if f <= s["fscore_negatif"] else 0
        texte = f"aucun signal d'alerte, F-score {f}/9"
    res.append({"cle": "qualite", "sens": sens, "texte": texte})
    if dynamique is not None:
        if dynamique.get("note") is None:
            res.append({"cle": "dynamique", "sens": 0, "texte": dynamique.get("texte") or "non disponible"})
        else:
            res.append({"cle": "dynamique", "sens": dynamique["sens"], "texte": dynamique["texte"]
                        + (" (données indicatives : peu d'analystes)" if dynamique.get("fiabilite") == "indicative" else "")})
    for x in res:
        x["libelle"] = LIBELLES_SIGNAUX[x["cle"]]
    return res


# ------------------------------------------------------------------ conditions qui invalideraient la recommandation

def _condition(sig: dict, but: str, note: int, m: dict, valeur: dict | None, prix, devise, cfg: dict) -> str | None:
    """Condition précise qui ferait basculer un signal : but = « annuler » (signal favorable perdu),
    « retourner » (signal défavorable qui cesse) ou « obtenir » (signal neutre qui deviendrait favorable)."""
    s = cfg["signaux"]
    c = sig["cle"]
    if c == "note":
        if but == "annuler":
            return f"Note globale sous {s['note_positive']}/100 à la prochaine révision des comptes (aujourd'hui {note})."
        if but == "retourner":
            return f"Note globale remontée à {s['note_negative']}/100 ou plus (aujourd'hui {note})."
        return f"Note globale portée à {s['note_positive']}/100 ou plus (aujourd'hui {note})."
    if c == "valorisation":
        if not valeur or valeur.get("ecart_pct") is None or not valeur["fiable"]:
            return None
        seuil_haut = valeur["centrale"] / (1 + s["valorisation_positive"] / 100)
        seuil_bas = valeur["centrale"] / (1 - s["valorisation_negative"] / 100)
        if but == "annuler":
            return f"Cours au-dessus de {prix_texte(seuil_haut, devise)} : l'écart à la valeur estimée passerait sous +{nb(s['valorisation_positive'], 0)} %."
        if but == "retourner":
            return f"Cours sous {prix_texte(seuil_bas, devise)} (aujourd'hui {prix_texte(prix, devise)}) : la survalorisation disparaîtrait."
        return f"Cours sous {prix_texte(seuil_haut, devise)} (aujourd'hui {prix_texte(prix, devise)}) : décote d'au moins {nb(s['valorisation_positive'], 0)} % sur la valeur estimée."
    if c == "momentum":
        mo = m.get("momentum_12m")
        if mo is None:
            return None
        if but == "annuler":
            return f"Momentum 12 mois sous {nb(s['momentum_positif'], 0, signe=True)} % (aujourd'hui {nb(mo, 1, signe=True)} %)."
        if but == "retourner":
            return f"Momentum 12 mois remonté au-dessus de {nb(s['momentum_negatif'], 0, signe=True)} % (aujourd'hui {nb(mo, 1, signe=True)} %)."
        return f"Momentum 12 mois au-dessus de {nb(s['momentum_positif'], 0, signe=True)} % (aujourd'hui {nb(mo, 1, signe=True)} %)."
    if c == "qualite":
        if but == "annuler":
            return f"Apparition d'un signal d'alerte comptable ou F-score sous {s['fscore_positif']}/9 au prochain rapport annuel."
        if but == "retourner":
            return ("Disparition du signal d'alerte comptable au prochain rapport annuel." if m.get("alertes")
                    else f"F-score remonté au-dessus de {s['fscore_negatif']}/9 au prochain rapport annuel.")
        return f"F-score d'au moins {s['fscore_positif']}/9 sans signal d'alerte comptable au prochain rapport annuel."
    if c == "dynamique":
        if but == "annuler":
            return "Guidance abaissée ou retirée au prochain communiqué de résultats, ou estimations de BPA révisées en baisse sur 30 jours."
        if but == "retourner":
            return "Guidance relevée ou maintenue au prochain communiqué de résultats, et estimations de BPA stabilisées sur 30 jours."
        return "Guidance relevée ou estimations de BPA révisées en hausse sur 30 et 90 jours."
    return None


# ------------------------------------------------------------------ recommandation

def exception_guidance(gn: dict | None, valeur: dict | None, m: dict, exc: dict | None) -> str | None:
    """Guidance abaissée ou retirée récemment : justification de l'exception si la valorisation intègre déjà une forte
    baisse (valeur estimée fiable au moins decote_min_pct % au-dessus du cours et momentum 12 mois ≤ momentum_max_pct %)."""
    if not gn or not exc or not valeur or not valeur.get("fiable") or valeur.get("ecart_pct") is None:
        return None
    mo = m.get("momentum_12m")
    if valeur["ecart_pct"] >= exc["decote_min_pct"] and mo is not None and mo <= exc["momentum_max_pct"]:
        return (f"Guidance {gn['evolution']} le {gn['date'][8:10]}/{gn['date'][5:7]}/{gn['date'][:4]}, mais le cours a déjà reculé de "
                f"{nb(abs(mo), 1)} % sur 12 mois et se situe {nb(valeur['ecart_pct'], 1)} % sous la valeur estimée : la baisse paraît "
                "intégrée dans la valorisation, « Acheter » reste possible")
    return None


def recommander(s: dict, m: dict, note: int | None, confiance: str, risques: list[str], cfg: dict,
                dynamique: dict | None = None, exc_guidance: dict | None = None) -> dict | None:
    """s : société (prix, devise_cours, actions, annuel, fx_comptes, fx_cours, region, financier) ;
    m : mesures après comparaison sectorielle ; note : note globale ; confiance : « élevé », « moyen » ou « faible » ;
    dynamique : bloc « Dynamique des résultats » (dynamique.bloc) ; exc_guidance : config dynamique.exception_guidance."""
    if note is None or not s.get("prix"):
        return None
    prix, devise = s["prix"], s.get("devise_cours")
    valeur = valeur_estimee(m, s, cfg)
    sig = signaux(note, m, valeur, s.get("financier"), cfg, dynamique)
    pos = [x for x in sig if x["sens"] > 0]
    neg = [x for x in sig if x["sens"] < 0]
    r = cfg["regles"]
    conf_ok = confiance in r["confiances_tranchees"]
    alerte = bool(m.get("alertes"))
    v = next(x for x in sig if x["cle"] == "valorisation")
    autres = [x for x in sig if x["cle"] != "valorisation"]
    prix_repli = None
    exclusions = []

    gn = (dynamique or {}).get("guidance_negative")
    exception = exception_guidance(gn, valeur, m, exc_guidance)
    bloque_guidance = bool(gn) and not exception
    achat = len(pos) >= r["signaux_concordants_min"] and not neg and conf_ok and not alerte and not bloque_guidance
    if len(pos) >= r["signaux_concordants_min"] and not neg and not achat:
        exclusions.append("« Acheter » exclu : " + ("signal d'alerte comptable" if alerte else f"confiance {confiance}" if not conf_ok
                                                     else f"guidance {gn['evolution']} le {gn['date'][8:10]}/{gn['date'][5:7]}/{gn['date'][:4]} (moins de 90 jours)"))
    # « Acheter sur repli » : tout est réuni sauf la valorisation, qui deviendrait favorable plus bas
    repli = (not achat and conf_ok and not alerte and valeur and valeur["fiable"] and valeur.get("ecart_pct") is not None
             and v["sens"] <= 0 and sum(1 for x in autres if x["sens"] > 0) >= r["signaux_concordants_min"] - 1
             and not any(x["sens"] < 0 for x in autres))
    if repli:
        prix_repli = round(valeur["centrale"] / (1 + cfg["signaux"]["valorisation_positive"] / 100), 4)
        # Repli trop éloigné du cours : « Attendre » (le niveau reste indiqué)
        repli = prix_repli >= prix * (1 - r["repli_max_pct"] / 100)
    ecart = (valeur or {}).get("ecart_pct")
    if achat:
        nd = "Acheter"
    elif repli:
        nd = "Acheter sur repli"
    elif len(neg) >= r["eviter_negatifs_min"] and len(neg) > len(pos):
        nd = "Éviter"
    else:
        nd = "Attendre"
    vente = len(neg) >= r["signaux_concordants_min"] and not pos and conf_ok
    if len(neg) >= r["signaux_concordants_min"] and not pos and not conf_ok:
        exclusions.append(f"« Vendre » exclu : confiance {confiance}")
    if achat:
        d = "Renforcer"
    elif vente:
        d = "Vendre"
    elif (len(neg) >= r["alleger_negatifs_min"] and len(neg) > len(pos)) or (
            ecart is not None and valeur["fiable"] and ecart <= -r["alleger_survalorisation_pct"]
            and note < cfg["signaux"]["note_positive"]):
        d = "Alléger"
    else:
        d = "Conserver"

    # Conditions qui invalideraient la recommandation (2 ou 3)
    if nd in ("Acheter",):
        cibles = [(x, "annuler") for x in pos]
    elif nd == "Éviter" or d in ("Vendre", "Alléger"):
        cibles = [(x, "retourner") for x in neg] + [(x, "annuler") for x in pos]
    elif nd == "Acheter sur repli":
        cibles = [(v, "obtenir")] + [(x, "annuler") for x in pos]
    else:
        cibles = [(x, "obtenir") for x in sig if x["sens"] == 0] + [(x, "retourner") for x in neg] + [(x, "annuler") for x in pos]
    conditions = []
    for x, but in cibles:
        t = _condition(x, but, note, m, valeur, prix, devise, cfg)
        if t and t not in conditions:
            conditions.append(t)
    if len(conditions) < 2:
        conditions.append("Publication de comptes trimestriels en net recul par rapport aux derniers comptes annuels analysés.")
    conditions = conditions[:3]

    def compte(liste, mot):
        return f"{len(liste)} {mot}{'s' if len(liste) > 1 else ''}" + (f" ({', '.join(x['libelle'].lower() for x in liste)})" if liste else "")
    justif = f"Signaux sur {len(sig)} : {compte(pos, 'favorable')}, {compte(neg, 'défavorable')} ; niveau de confiance : {confiance}."
    if exclusions:
        justif += " " + " ; ".join(exclusions) + "."
    if exception:
        justif += f" {exception}."
    if prix_repli and nd == "Acheter sur repli" and bloque_guidance:
        justif += (f" Repli sous {prix_texte(prix_repli, devise)} (aujourd'hui {prix_texte(prix, devise)}) : la valorisation deviendrait favorable,"
                   f" mais « Acheter » reste exclu tant que la guidance {gn['evolution']} a moins de 90 jours.")
    elif prix_repli and nd == "Acheter sur repli":
        justif += f" Passerait à « Acheter » sous {prix_texte(prix_repli, devise)} (aujourd'hui {prix_texte(prix, devise)}), comptes inchangés."
    elif prix_repli:
        justif += (f" Passerait à « Acheter » sous {prix_texte(prix_repli, devise)}, soit {nb((1 - prix_repli / prix) * 100, 0)} % sous le cours :"
                   f" repli jugé trop éloigné (plus de {nb(r['repli_max_pct'], 0)} %) pour « Acheter sur repli ».")

    def arrondi(x):
        return None if x is None else round(x, 4)
    return {
        "horizon_mois": cfg["horizon_mois"], "si_non_detenu": nd, "si_detenu": d,
        "cours": arrondi(prix), "devise": devise, "date_cours": s.get("date_cours"),
        "valeur": valeur, "ecart_pct": ecart, "prix_repli": prix_repli,
        "signaux": sig, "concordants": {"favorables": len(pos), "defavorables": len(neg)},
        "confiance": confiance, "justification": justif, "exception_guidance": exception,
        "conditions_invalidation": conditions, "risques": risques[:3], "mention": MENTION,
    }


def resume(r: dict | None) -> dict | None:
    """Version courte (listes, data/entreprises.json, pépites)."""
    if not r:
        return None
    return {"n": r["si_non_detenu"], "d": r["si_detenu"], "e": r.get("ecart_pct")}
