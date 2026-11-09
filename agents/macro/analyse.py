"""
Analyse de l'agent macro (fonctions pures, testables sans réseau).

Phase du cycle (par zone) : croissance qui accélère ou ralentit × inflation qui accélère ou ralentit.
  croissance ↑, inflation ↓ : « Reprise »
  croissance ↑, inflation ↑ : « Surchauffe »
  croissance ↓, inflation ↑ : « Ralentissement inflationniste »
  croissance ↓, inflation ↓ : « Expansion sans inflation » (l'activité se modère, l'inflation reflue)

Chaque axe est tranché par un vote de trois signaux :
  1. la variation sur 3 mois de la série mensuelle (indicateur avancé de l'OCDE, ou inflation) ;
  2. la même variation, un mois plus tôt (persistance) ;
  3. la prévision du FMI pour l'année en cours comparée à l'année précédente.
Deux signaux concordants au minimum sont exigés pour fixer la direction d'un axe ;
sinon la direction précédente est conservée : pas de changement de phase annoncé.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone

from ..pays.textes import nb, ton_conforme  # noqa: F401  (ton_conforme réexporté pour les tests)

PHASES = {
    (1, -1): "Reprise",
    (1, 1): "Surchauffe",
    (-1, 1): "Ralentissement inflationniste",
    (-1, -1): "Expansion sans inflation",
}
SENS = {1: "accélère", -1: "ralentit", 0: "stable"}

Serie = list[tuple[str, float]]


# ------------------------------------------------------------------ outils

def mensuelle(serie: Serie) -> Serie:
    """Dernière valeur de chaque mois : [('2026-09', 100.9), …]."""
    par_mois = {}
    for d, v in sorted(serie):
        par_mois[str(d)[:7]] = v
    return sorted(par_mois.items())


def agreger(series: list[Serie], methode: str = "moyenne") -> Serie:
    """Moyenne (ou médiane) mois par mois, sur les mois où toutes les séries sont présentes."""
    series = [dict(mensuelle(s)) for s in series if s]
    if not series:
        return []
    mois = sorted(set.intersection(*(set(s) for s in series)))
    f = statistics.median if methode == "mediane" else statistics.fmean
    return [(m, f([s[m] for s in series])) for m in mois]


def direction(delta: float | None, seuil: float) -> int:
    if delta is None:
        return 0
    return 1 if delta > seuil else -1 if delta < -seuil else 0


def valeur_au(serie: Serie, jour: date) -> float | None:
    """Dernière valeur à une date ≤ jour."""
    avant = [v for d, v in serie if str(d)[:10] <= jour.isoformat()]
    return avant[-1] if avant else None


def jour(d: str) -> date:
    return date.fromisoformat(str(d)[:10])


def date_fr(d: str | date | None) -> str:
    if not d:
        return "date inconnue"
    s = str(d)
    if len(s) == 7:
        mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        return f"{mois[int(s[5:7]) - 1]} {s[:4]}"
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}"


def pts(x: float, decimales: int = 2) -> str:
    return f"{nb(x, decimales, signe=True)} pt"


# ------------------------------------------------------------------ phase du cycle

def _vote(serie: list[float], t: int, seuil: float, fmi: int) -> tuple[int, list[int]]:
    votes = [direction(serie[t] - serie[t - 3], seuil) if t >= 3 else 0,
             direction(serie[t - 1] - serie[t - 4], seuil) if t >= 4 else 0,
             fmi]
    plus, moins = votes.count(1), votes.count(-1)
    return (1 if plus >= 2 else -1 if moins >= 2 else 0), votes


def phase_zone(cli: Serie, inflation: Serie, fmi_croissance: tuple[float, float] | None,
               fmi_inflation: tuple[float, float] | None, seuils: dict, mois_max: int = 18) -> dict | None:
    """Reconstitue la phase mois par mois (sur les mois communs aux deux séries) et renvoie
    la phase actuelle, la précédente, la date du changement, les positions et les signaux."""
    c, i = dict(mensuelle(cli)), dict(mensuelle(inflation))
    mois = sorted(set(c) & set(i))[-mois_max:]
    if len(mois) < 5:
        return None
    xc, xi = [c[m] for m in mois], [i[m] for m in mois]
    fmi_g = direction(fmi_croissance[1] - fmi_croissance[0], seuils["fmi_croissance_pts"]) if fmi_croissance else 0
    fmi_i = direction(fmi_inflation[1] - fmi_inflation[0], seuils["fmi_inflation_pts"]) if fmi_inflation else 0
    g = inf = None
    historique, votes_g, votes_i, concord_g, concord_i = [], [], [], 0, 0
    for t in range(4, len(mois)):
        vg, votes_g = _vote(xc, t, seuils["cli_pts"], fmi_g)
        vi, votes_i = _vote(xi, t, seuils["inflation_pts"], fmi_i)
        # Direction fixée seulement avec deux signaux concordants ; sinon on garde la précédente
        if vg:
            g = vg
        elif g is None:
            g = direction(xc[t] - xc[t - 3], 0) or 1
        if vi:
            inf = vi
        elif inf is None:
            inf = direction(xi[t] - xi[t - 3], 0) or -1
        concord_g, concord_i = max(votes_g.count(vg), 0) if vg else 1, max(votes_i.count(vi), 0) if vi else 1
        historique.append((mois[t], PHASES[(g, inf)]))
    phase = historique[-1][1]
    debut = len(historique) - 1
    while debut > 0 and historique[debut - 1][1] == phase:
        debut -= 1
    precedente = historique[debut - 1][1] if debut > 0 else None
    t = len(mois) - 1
    return {
        "phase": phase,
        "phase_precedente": precedente,
        "depuis": historique[debut][0] if precedente else None,
        "date_donnees": mois[-1],
        "position": {"x": round(xc[t] - xc[t - 3], 3), "y": round(xi[t] - xi[t - 3], 3)},
        "position_precedente": {"x": round(xc[t - 1] - xc[t - 4], 3), "y": round(xi[t - 1] - xi[t - 4], 3)},
        "croissance": {"direction": SENS[g], "concordants": concord_g, "votes": votes_g,
                       "cli": round(xc[t], 2), "cli_3m": round(xc[t] - xc[t - 3], 2)},
        "inflation": {"direction": SENS[inf], "concordants": concord_i, "votes": votes_i,
                      "valeur": round(xi[t], 2), "variation_3m": round(xi[t] - xi[t - 3], 2)},
        "historique": historique[-12:],
    }


# ------------------------------------------------------------------ confirmation de la phase (anti-girouette)

AXES = {v: k for k, v in PHASES.items()}  # phase → (croissance, inflation)


def _etape(confirmee: str | None, candidat: dict | None, brute: str, jour_iso: str, concordance_ok: bool, jours_requis: int):
    """Une observation de la phase brute. Renvoie (phase confirmée, candidat, changement aujourd'hui)."""
    if confirmee is None:
        return brute, None, False
    if brute == confirmee:
        return confirmee, None, False
    if not candidat or candidat.get("vers") != brute:
        candidat = {"vers": brute, "depuis": jour_iso}  # nouvelle phase observée : le décompte repart de zéro
    jours = (jour(jour_iso) - jour(candidat["depuis"])).days
    if jours >= jours_requis and concordance_ok:
        return brute, None, True
    return confirmee, candidat, False


def rejouer(historique: list[tuple[str, str]], jours_requis: int) -> tuple[str | None, dict | None]:
    """Phase confirmée et candidat après les observations passées [(AAAA-MM-JJ, phase brute)] (premier passage)."""
    confirmee, candidat = None, None
    for d, brute in sorted(historique):
        confirmee, candidat, _ = _etape(confirmee, candidat, brute, d, True, jours_requis)
    return confirmee, candidat


def axes_concordants(z: dict, de: str, vers: str, signaux_min: int) -> bool:
    """Chaque axe qui change entre les deux phases a-t-il au moins `signaux_min` signaux concordants ?"""
    a, b = AXES.get(de), AXES.get(vers)
    if not a or not b:
        return True
    ok = True
    if a[0] != b[0]:
        ok &= (z.get("croissance") or {}).get("concordants", 0) >= signaux_min
    if a[1] != b[1]:
        ok &= (z.get("inflation") or {}).get("concordants", 0) >= signaux_min
    return ok


def confirmer_phase(z: dict, ancienne: dict | None, historique: list[tuple[str, str]], aujourdhui: date, cfg: dict) -> dict:
    """Applique la confirmation à la phase brute du jour (z["phase"]). La phase publiée ne change qu'après
    `semaines` semaines d'observation continue de la nouvelle phase, avec deux signaux concordants par axe."""
    requis = 7 * cfg["semaines"]
    brute = z["phase"]
    if ancienne and ancienne.get("confirmation_v"):
        confirmee = ancienne.get("phase")
        candidat = ancienne.get("changement_en_cours")
        candidat = {"vers": candidat["vers"], "depuis": candidat["depuis"]} if candidat else None
    else:
        confirmee, candidat = rejouer([(d, p) for d, p in historique if d < aujourdhui.isoformat()], requis)
    concordance = axes_concordants(z, confirmee, brute, cfg["signaux_min"]) if confirmee else True
    nouvelle, candidat, change = _etape(confirmee, candidat, brute, aujourdhui.isoformat(), concordance, requis)
    z = {**z, "phase_brute": brute, "confirmation_v": 1, "changement_en_cours": None}
    if change:
        z.update({"phase": nouvelle, "phase_precedente": confirmee, "depuis": aujourdhui.isoformat(), "confirme_le": aujourdhui.isoformat()})
    elif nouvelle != brute:
        jours = (aujourdhui - jour(candidat["depuis"])).days
        z.update({"phase": nouvelle,
                  "phase_precedente": (ancienne or {}).get("phase_precedente") if (ancienne or {}).get("phase") == nouvelle else None,
                  "depuis": (ancienne or {}).get("depuis") if (ancienne or {}).get("phase") == nouvelle else None,
                  "changement_en_cours": {
                      "vers": brute, "depuis": candidat["depuis"], "jours": jours, "jours_requis": requis, "signaux_concordants": concordance,
                      "texte": (f"Changement de phase en cours de confirmation : « {brute} » observée depuis le {date_fr(candidat['depuis'])} "
                                f"({jours} jour{'s' if jours > 1 else ''} sur {requis} requis"
                                + ("" if concordance else ", deux signaux concordants pas encore réunis")
                                + f") ; la phase publiée reste « {nouvelle} »."),
                  }})
    elif (ancienne or {}).get("phase") == nouvelle and (ancienne or {}).get("confirmation_v"):
        # phase inchangée : on garde la date et la phase précédente publiées
        z.update({"phase_precedente": ancienne.get("phase_precedente"), "depuis": ancienne.get("depuis")})
    return z


def confiance_zone(z: dict, aujourdhui: date) -> str:
    ancien = (aujourdhui - date.fromisoformat(z["date_donnees"] + "-28")).days > 125
    c = (z["croissance"]["concordants"], z["inflation"]["concordants"])
    if ancien or min(c) < 2:
        return "faible"
    return "élevé" if c == (3, 3) else "moyen"


NOMS_VOTES = ["variation sur 3 mois", "variation sur 3 mois, un mois plus tôt", "prévision du FMI"]


def contre_scenario_zone(z: dict, nom_cli: str) -> list[str]:
    g, i = z["croissance"], z["inflation"]
    res = []
    if g["direction"] == "accélère":
        res.append(f"Un recul de l'indicateur avancé ({nom_cli}) sur 3 mois, confirmé par un second signal, ferait passer la croissance en ralentissement.")
    else:
        res.append(f"Une remontée de l'indicateur avancé ({nom_cli}) sur 3 mois, confirmée par un second signal, ferait passer la croissance en accélération.")
    if i["direction"] == "accélère":
        res.append("Un repli de l'inflation sur 3 mois, confirmé par un second signal, changerait la phase.")
    else:
        res.append("Une remontée de l'inflation sur 3 mois, confirmée par un second signal, changerait la phase.")
    for axe, libelle in ((g, "croissance"), (i, "inflation")):
        sens = 1 if axe["direction"] == "accélère" else -1
        contraires = [NOMS_VOTES[k] for k, v in enumerate(axe["votes"]) if v == -sens]
        if contraires:
            res.append(f"Signal discordant sur la {libelle} : {', '.join(contraires)}.")
    return res


def texte_zone(nom: str, z: dict, nom_cli: str, fmi_g, fmi_i, an: int) -> str:
    g, i = z["croissance"], z["inflation"]
    t = f"{nom} : phase « {z['phase']} »"
    if z.get("phase_precedente") and z.get("depuis"):
        t += f" depuis {date_fr(z['depuis'])} (précédente : « {z['phase_precedente']} »)"
    t += (f". Indicateur avancé de l'OCDE ({nom_cli}) à {nb(g['cli'], 1)}, {pts(g['cli_3m'])} sur 3 mois ; "
          f"inflation à {nb(i['valeur'], 1)} %, {pts(i['variation_3m'], 1)} sur 3 mois ({date_fr(z['date_donnees'])}).")
    if fmi_g and fmi_i:
        t += (f" Le FMI prévoit {nb(fmi_g[1], 1)} % de croissance en {an} contre {nb(fmi_g[0], 1)} % en {an - 1}, "
              f"et {nb(fmi_i[1], 1)} % d'inflation contre {nb(fmi_i[0], 1)} %.")
    if z.get("changement_en_cours"):
        t += " " + z["changement_en_cours"]["texte"]
    return t


# ------------------------------------------------------------------ signaux de récession

def etat_courbe(serie: Serie, cfg: dict, aujourdhui: date) -> dict | None:
    """Écart de taux : niveau (vert/orange/rouge), durée de l'inversion ou date de la désinversion."""
    if not serie:
        return None
    serie = sorted(serie)
    d, v = serie[-1]
    res = {"valeur": round(v, 2), "date": d, "inversee": v < 0}
    if v < 0:
        k = len(serie) - 1
        while k > 0 and serie[k - 1][1] < 0:
            k -= 1
        res["depuis"] = serie[k][0]
        res["jours"] = (jour(d) - jour(serie[k][0])).days
        res["niveau"] = "rouge"
        res["texte"] = f"inversée depuis le {date_fr(serie[k][0])} ({res['jours']} jours)"
        return res
    negatifs = [k for k, (_, x) in enumerate(serie) if x < 0]
    if negatifs:
        fin = negatifs[-1]
        debut = fin
        while debut > 0 and serie[debut - 1][1] < 0:
            debut -= 1
        res["desinversion"] = serie[fin + 1][0]
        res["duree_inversion"] = (jour(serie[fin][0]) - jour(serie[debut][0])).days
        recente = (aujourdhui - jour(res["desinversion"])).days <= cfg["desinversion_jours"]
    else:
        recente = False
    if recente:
        res["niveau"] = "orange"
        res["texte"] = f"positive, mais désinversée depuis le {date_fr(res['desinversion'])} seulement (après {res['duree_inversion']} jours d'inversion)"
    elif v < cfg["courbe_orange_sous"]:
        res["niveau"] = "orange"
        res["texte"] = "positive mais proche de zéro"
    else:
        res["niveau"] = "vert"
        res["texte"] = "positive" + (f" ; dernière inversion terminée le {date_fr(res['desinversion'])}" if negatifs else "")
    return res


def ecart(long: Serie, court: Serie) -> Serie:
    c = dict(court)
    return [(d, round(v - c[d], 4)) for d, v in sorted(long) if d in c]


def sahm_calculee(chomage: Serie) -> Serie:
    """Règle de Sahm : moyenne mobile 3 mois du chômage moins son minimum des 12 mois précédents."""
    m = mensuelle(chomage)
    moy = [(m[k][0], statistics.fmean(v for _, v in m[k - 2:k + 1])) for k in range(2, len(m))]
    return [(moy[k][0], round(moy[k][1] - min(v for _, v in moy[k - 12:k]), 2)) for k in range(12, len(moy))]


def niveau_sahm(v: float, cfg: dict) -> str:
    return "rouge" if v >= cfg["sahm_rouge"] else "orange" if v >= cfg["sahm_orange"] else "vert"


def niveau_cli(valeur: float, variation_3m: float) -> str:
    if valeur < 100 and variation_3m < 0:
        return "rouge"
    if valeur < 100 or variation_3m < 0:
        return "orange"
    return "vert"


def verification(a: float | None, b: float | None, tolerance: float) -> str:
    if a is None or b is None:
        return "source_unique"
    return "concordant" if abs(a - b) <= tolerance else "divergent"


# ------------------------------------------------------------------ banques centrales

def mouvements(serie: Serie) -> list[dict]:
    res = []
    for (d0, v0), (d1, v1) in zip(serie, serie[1:]):
        if abs(v1 - v0) >= 0.001:
            res.append({"date": d1, "avant": v0, "apres": v1, "sens": "hausse" if v1 > v0 else "baisse",
                        "ampleur_pts": round(v1 - v0, 3)})
    return res


def prochaine_reunion(cal: dict, aujourdhui: date) -> dict:
    if cal.get("sans_calendrier"):
        return {"date": None, "jours": None, "note": cal.get("note")}
    futures = [d for d in cal.get("dates", []) if d >= aujourdhui.isoformat()]
    if not futures:
        return {"date": None, "jours": None, "note": "aucune date future dans le calendrier"}
    return {"date": futures[0], "jours": (date.fromisoformat(futures[0]) - aujourdhui).days}


def banque_centrale(cle: str, cfg: dict, bis: Serie | None, nationale: Serie | None, nom_nationale: str | None,
                    cal: dict, aujourdhui: date) -> dict | None:
    """Taux actuel, dernier mouvement, tendance sur 12 mois, prochaine réunion, vérification BRI / source nationale."""
    candidates = [(s, n) for s, n in ((nationale, nom_nationale), (bis, "BRI, taux directeurs (WS_CBPOL, quotidien)")) if s]
    if not candidates:
        return None
    # Série de référence : la plus récente (la source nationale l'emporte à date égale)
    serie, source = max(candidates, key=lambda c: c[0][-1][0])
    d, taux = serie[-1]
    mvts = mouvements(serie)
    an = valeur_au(serie, aujourdhui - timedelta(days=365))
    if an is None and bis:
        an = valeur_au(bis, aujourdhui - timedelta(days=365))
    variation = round(taux - an, 3) if an is not None else None
    res = {
        "cle": cle, "nom": cfg["nom"], "pays": cfg["pays"], "taux": round(taux, 3), "date": d, "source": source,
        "dernier_mouvement": mvts[-1] if mvts else None,
        "tendance_12m": {"variation_pts": variation,
                         "sens": None if variation is None else "hausse" if variation > 0.001 else "baisse" if variation < -0.001 else "stable"},
        "prochaine_reunion": prochaine_reunion(cal, aujourdhui),
    }
    if bis and nationale:
        db, vb = bis[-1]
        dn, vn = nationale[-1]
        if abs(vb - vn) <= 0.01:
            res["verification"] = "concordant"
        elif mvts and db < mvts[-1]["date"]:
            res["verification"] = "non comparable"
            res["note_verification"] = f"la BRI n'intègre pas encore le dernier mouvement (dernier point du {date_fr(db)} à {nb(vb, 2)} %)"
        else:
            res["verification"] = "divergent"
            res["note_verification"] = f"BRI à {nb(vb, 2)} % le {date_fr(db)}, source nationale à {nb(vn, 2)} % le {date_fr(dn)}"
    else:
        res["verification"] = "source_unique"
    return res


def phrase_banque(b: dict, nom_banque: str) -> str:
    if b.get("fourchette"):
        bas, haut = b["fourchette"]
        t = f"Fourchette cible de la {nom_banque or 'banque centrale'} à {nb(bas, 2)}–{nb(haut, 2)} % ({date_fr(b['date'])})"
    elif nom_banque:
        t = f"Taux directeur de la {nom_banque} à {nb(b['taux'], 2)} % ({date_fr(b['date'])})"
    else:
        t = f"Taux directeur à {nb(b['taux'], 2)} % ({date_fr(b['date'])})"
    m = b.get("dernier_mouvement")
    if m:
        t += f", dernier mouvement : {m['sens']} de {nb(abs(m['ampleur_pts']), 2)} pt le {date_fr(m['date'])}"
    tend = b.get("tendance_12m") or {}
    if tend.get("variation_pts") is not None:
        t += " ; inchangé sur 12 mois" if tend.get("sens") == "stable" else f" ; {pts(tend['variation_pts'])} sur 12 mois"
    return t


# ------------------------------------------------------------------ taux réels (États-Unis)

NOTE_5A5A_ZONE_EURO = ("La BCE ne publie pas gratuitement le point mort d'inflation à 5 ans dans 5 ans "
                       "(calculé à partir des swaps indexés sur l'inflation, données de marché sous licence) ; "
                       "aucune série de ce type dans le BCE Data Portal.")


def _sens(variation: float | None, seuil: float = 0.05) -> str | None:
    if variation is None:
        return None
    return "hausse" if variation > seuil else "baisse" if variation < -seuil else "stable"


def tendance_quotidienne(serie: Serie | None, source: str) -> dict | None:
    """Dernière valeur d'une série quotidienne (en %) et variation sur 12 mois (en points)."""
    if not serie:
        return None
    serie = sorted(serie)
    d, v = serie[-1]
    an = valeur_au(serie, jour(d) - timedelta(days=365))
    var = round(v - an, 2) if an is not None else None
    return {"valeur": round(v, 2), "date": d, "variation_12m": var, "sens": _sens(var), "source": source}


def taux_reel_passe(fed: Serie | None, inflation: Serie | None, source: str) -> dict | None:
    """Taux réel passé : taux de la Fed moins l'inflation des 12 derniers mois (dernier mois publié),
    et le même calcul 12 mois plus tôt."""
    if not fed or not inflation:
        return None
    fed, m = sorted(fed), mensuelle(inflation)
    d_fed, taux = fed[-1]
    mois, inf = m[-1]
    v = taux - inf
    var = None
    if len(m) >= 13:
        mois_12, inf_12 = m[-13]
        taux_12 = valeur_au(fed, jour(d_fed) - timedelta(days=365))
        if taux_12 is not None:
            var = round(v - (taux_12 - inf_12), 2)
    return {"valeur": round(v, 2), "taux_directeur": round(taux, 3), "date_taux": d_fed, "inflation": round(inf, 2),
            "date_inflation": mois, "variation_12m": var, "sens": _sens(var), "source": source}


def texte_taux_reels(passe: dict | None, attendu: dict | None, point_mort: dict | None) -> str:
    """Phrase d'explication (ton factuel) du bloc « Taux réels États-Unis »."""
    morceaux = []
    if passe:
        morceaux.append(f"Le taux réel passé ({nb(passe['taux_directeur'], 2)} % pour la Fed, milieu de la fourchette, moins {nb(passe['inflation'], 1)} % "
                        f"d'inflation sur 12 mois) est de {nb(passe['valeur'], 2, signe=True)} % : il mesure la politique "
                        "monétaire par rapport à l'inflation déjà constatée.")
    if attendu and point_mort:
        morceaux.append(f"Le taux réel attendu à 10 ans ({nb(attendu['valeur'], 2)} %) est le rendement des obligations du Trésor "
                        f"indexées sur l'inflation ; le point mort ({nb(point_mort['valeur'], 2)} %) est l'inflation moyenne "
                        "que le marché anticipe sur la même durée (rendement nominal moins rendement réel).")
    elif attendu:
        morceaux.append(f"Le taux réel attendu à 10 ans ({nb(attendu['valeur'], 2)} %) est le rendement des obligations "
                        "du Trésor indexées sur l'inflation.")
    if passe and attendu:
        ecart = attendu["valeur"] - passe["valeur"]
        if abs(ecart) < 0.25:
            morceaux.append("Les deux mesures sont proches.")
        else:
            morceaux.append(f"Le taux réel attendu à 10 ans est {'supérieur' if ecart > 0 else 'inférieur'} de {nb(abs(ecart), 1)} pt "
                            "au taux réel passé.")
    if attendu and attendu.get("sens") in ("hausse", "baisse"):
        morceaux.append(f"Sur 12 mois, le taux réel attendu est en {attendu['sens']} de {nb(abs(attendu['variation_12m']), 2)} pt : "
                        f"{'les conditions financières se resserrent' if attendu['sens'] == 'hausse' else 'les conditions financières s’assouplissent'}.")
    return " ".join(morceaux)


def taux_reels_us(fed: Serie | None, nom_fed: str, inflation: Serie | None, series: dict, sources: dict,
                  nominal_10a: Serie | None = None, tolerance: float = 0.1) -> dict | None:
    """Bloc « Taux réels États-Unis » : taux réel passé, taux réel attendu à 5 et 10 ans (DFII5, DFII10),
    points morts d'inflation à 5 et 10 ans (T5YIE, T10YIE). Vérification du taux réel à 10 ans :
    rendement nominal à 10 ans (Yahoo ^TNX) moins le point mort à 10 ans, à la même date."""
    passe = taux_reel_passe(fed, inflation, f"{nom_fed} ; OCDE, inflation des États-Unis (IPC, glissement annuel)")
    attendu_10 = tendance_quotidienne(series.get("DFII10"), sources.get("DFII10", "FRED (DFII10)"))
    attendu_5 = tendance_quotidienne(series.get("DFII5"), sources.get("DFII5", "FRED (DFII5)"))
    pm_10 = tendance_quotidienne(series.get("T10YIE"), sources.get("T10YIE", "FRED (T10YIE)"))
    pm_5 = tendance_quotidienne(series.get("T5YIE"), sources.get("T5YIE", "FRED (T5YIE)"))
    if not any((passe, attendu_10, attendu_5, pm_10, pm_5)):
        return None
    if attendu_10:
        attendu_10["verification"] = "source_unique"
        if nominal_10a and series.get("T10YIE"):
            j = jour(attendu_10["date"])
            nom, pm = valeur_au(nominal_10a, j), valeur_au(series["T10YIE"], j)
            if nom is not None and pm is not None:
                calc = nom - pm
                attendu_10["verification"] = verification(attendu_10["valeur"], calc, tolerance)
                attendu_10["note_verification"] = f"Yahoo Finance ^TNX ({nb(nom, 2)} %) moins le point mort à 10 ans : {nb(calc, 2)} %"
    return {
        "passe": passe, "attendu_10a": attendu_10, "attendu_5a": attendu_5, "point_mort_10a": pm_10, "point_mort_5a": pm_5,
        "texte": texte_taux_reels(passe, attendu_10, pm_10),
    }


# ------------------------------------------------------------------ marchés

def marche(serie: Serie, cfg: dict) -> dict | None:
    if not serie:
        return None
    d, v = serie[-1]
    j = jour(d)

    def var(jours):
        ref = valeur_au(serie, j - timedelta(days=jours))
        return round((v / ref - 1) * 100, 2) if ref else None
    return {"symbole": cfg["symbole"], "nom": cfg["nom"], "unite": cfg["unite"], "valeur": round(v, 4), "date": d,
            "variation_3m": var(91), "variation_12m": var(365), "source": "Yahoo Finance via yfinance, clôture quotidienne"}


def hebdomadaire(serie: Serie, depuis: date) -> Serie:
    """Dernier point de chaque semaine ISO, à partir de `depuis` (pour le graphique)."""
    par_semaine = {}
    for d, v in sorted(serie):
        j = jour(d)
        if j >= depuis:
            par_semaine[j.isocalendar()[:2]] = (d, round(v, 3))
    return list(par_semaine.values())


# ------------------------------------------------------------------ lecture par pays

def lecture_pays(code: str, cfg_pays: dict, banque: dict | None, nom_banque: str | None,
                 cli: Serie | None, zone: dict | None, nom_zone: str | None) -> str:
    if banque:
        p1 = phrase_banque(banque, nom_banque) + "."
    else:
        p1 = "Taux directeur non disponible dans les sources consultées (BRI)."
    cli_m = mensuelle(cli) if cli else []
    if len(cli_m) >= 4:
        m, v = cli_m[-1]
        var3 = v - cli_m[-4][1]
        p2 = (f"Indicateur avancé de l'OCDE à {nb(v, 1)} ({date_fr(m)}), {'en hausse' if var3 > 0.05 else 'en baisse' if var3 < -0.05 else 'stable'} sur 3 mois"
              f" et {'au-dessus' if v >= 100 else 'en dessous'} de sa tendance de long terme (100)")
        p2 += f" ; {nom_zone} : phase « {zone['phase']} »." if zone else "."
    elif zone:
        p2 = f"Pas d'indicateur avancé de l'OCDE pour ce pays ; {nom_zone} : phase « {zone['phase']} » ({date_fr(zone['date_donnees'])})."
    else:
        p2 = "Pas d'indicateur avancé de l'OCDE pour ce pays."
    return f"{p1} {p2}"


# ------------------------------------------------------------------ signaux pour le chef d'orchestre

def signaux(precedent: dict | None, actuel: dict, aujourdhui: date) -> list[dict]:
    """Événements détectés depuis l'exécution précédente (ou, à la première, dans les 7 derniers jours)."""
    res = []
    p = precedent or {}
    jour_s = aujourdhui.isoformat()
    # Changements de phase
    anciennes = {z["cle"]: z.get("phase") for z in (p.get("cycle") or {}).get("zones", [])}
    for z in actuel["cycle"]["zones"]:
        avant = anciennes.get(z["cle"])
        if avant and z.get("phase") and avant != z["phase"]:
            res.append({"date": jour_s, "type": "changement_de_phase", "cle": z["cle"],
                        "importance": "forte" if z["cle"] == "monde" else "moyenne",
                        "titre": f"{z['nom']} : passage de « {avant} » à « {z['phase']} »",
                        "explication": z.get("texte", ""), "source": "OCDE, FMI, Eurostat"})
    # Mouvements de banques centrales
    anciens_mvts = {b["cle"]: (b.get("dernier_mouvement") or {}).get("date") for b in p.get("banques_centrales", [])}
    for b in actuel["banques_centrales"]:
        m = b.get("dernier_mouvement")
        if not m:
            continue
        nouveau = (m["date"] != anciens_mvts.get(b["cle"])) if b["cle"] in anciens_mvts else (aujourdhui - jour(m["date"])).days <= 7
        if nouveau:
            res.append({"date": m["date"], "type": "mouvement_banque_centrale", "cle": b["cle"],
                        "importance": "forte" if b["cle"] in ("fed", "bce") else "moyenne",
                        "titre": f"{b['nom']} : {m['sens']} de {nb(abs(m['ampleur_pts']), 2)} pt, à {nb(m['apres'], 2)} %",
                        "explication": phrase_banque(b, b["nom"]) + ".", "source": b["source"]})
    # Inversion / désinversion des courbes ; règle de Sahm
    anciens = {s["cle"]: s for s in (p.get("recession") or {}).get("signaux", [])}
    for s in actuel["recession"]["signaux"]:
        a = anciens.get(s["cle"])
        if s["cle"].startswith("courbe") and "inversee" in s:
            change = (a is not None and "inversee" in a and a["inversee"] != s["inversee"])
            premiere = a is None and ((s.get("depuis") and (aujourdhui - jour(s["depuis"])).days <= 7)
                                      or (s.get("desinversion") and (aujourdhui - jour(s["desinversion"])).days <= 7))
            if change or premiere:
                res.append({"date": s["date"], "type": "inversion_courbe" if s["inversee"] else "desinversion_courbe", "cle": s["cle"],
                            "importance": "moyenne" if "allemagne" in s["cle"] else "forte",
                            "titre": f"{s['libelle']} : {'inversion' if s['inversee'] else 'désinversion'}",
                            "explication": f"{s['libelle']} à {pts(s['valeur'])} le {date_fr(s['date'])} ; {s['texte']}.", "source": s["source"]})
        if s["cle"] == "sahm" and s.get("valeur") is not None:
            avant = a.get("valeur") if a else None
            seuil = 0.5
            if (avant is not None and (avant < seuil) != (s["valeur"] < seuil)) or (avant is None and s["valeur"] >= seuil):
                res.append({"date": s["date"], "type": "regle_de_sahm", "cle": "sahm",
                            "importance": "forte" if s["valeur"] >= seuil else "moyenne",
                            "titre": "Règle de Sahm déclenchée" if s["valeur"] >= seuil else "Règle de Sahm repassée sous le seuil",
                            "explication": s["texte"], "source": s["source"]})
    return res


def conformes(textes: list[str]) -> bool:
    return all(ton_conforme(t) for t in textes if t)


def iso_maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
