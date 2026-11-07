"""
Analyse d'une société (fonctions pures, testables sans réseau).

Indicateurs (sociétés non financières) : croissance du CA (1 an, tendance 3 ans), croissance du bénéfice,
marge opérationnelle et son évolution, conversion du bénéfice en cash (FCF), dette nette / EBITDA,
couverture des intérêts, ROIC, PER et VE/EBITDA comparés à la médiane du secteur (mondiale et régionale),
momentum 6 et 12 mois, F-score de Piotroski.
Banques et assurances : ROE, coût / revenu (banques), croissance des dépôts ou des primes, croissance,
PER relatif, momentum.

Règles de conduite (comme l'agent pays) : ton froid, pas de superlatifs, deux signaux concordants au
minimum pour un verdict tranché, confiance plafonnée à « moyen » quand Yahoo est la seule source des comptes.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

from ..pays.textes import nb, ton_conforme  # noqa: F401

LIBELLES = {
    "croissance_ca": "Croissance du CA",
    "croissance_benefice": "Croissance du bénéfice",
    "marge_op": "Marge opérationnelle",
    "conversion_cash": "Conversion du bénéfice en cash",
    "dette_ebitda": "Dette nette / EBITDA",
    "couverture_interets": "Couverture des intérêts",
    "roic": "ROIC",
    "roe": "ROE",
    "cout_revenu": "Coût / revenu",
    "croissance_bilan": "Croissance des dépôts ou des primes",
    "per_secteur": "PER vs secteur",
    "ev_ebitda_secteur": "VE/EBITDA vs secteur",
    "momentum_12m": "Momentum 12 mois",
    "fscore": "F-score de Piotroski",
}


# ------------------------------------------------------------------ outils

def lin(x, points):
    """Interpolation linéaire par morceaux, bornée aux extrémités : points = [(x0, note0), (x1, note1), …]."""
    if x is None:
        return None
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return round(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return points[-1][1]


def ratio(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def pct(a, b):
    """Variation en % de b vers a (b > 0)."""
    if a is None or b is None or b <= 0:
        return None
    return (a / b - 1) * 100


def variation_absolue(a, b):
    """Variation relative quand la base peut être négative (bénéfice) : (a − b) / |b|."""
    if a is None or b in (None, 0):
        return None
    return (a - b) / abs(b) * 100


def mediane(valeurs):
    v = [x for x in valeurs if x is not None]
    return statistics.median(v) if v else None


# ------------------------------------------------------------------ mesures de base

def type_financier(secteur: str | None, info: dict, a0: dict) -> str | None:
    if secteur != "Financials":
        return None
    industrie = (info.get("industry") or "").lower()
    if a0.get("depots") is not None or "bank" in industrie:
        return "banque"
    if a0.get("primes") is not None or "insurance" in industrie:
        return "assurance"
    return "autre"


def momentum(cours: list, jours: int) -> float | None:
    if not cours:
        return None
    fin = date.fromisoformat(cours[-1][0])
    avant = [c for d, c, *_ in cours if date.fromisoformat(d) <= fin - timedelta(days=jours)]
    return round((cours[-1][1] / avant[-1] - 1) * 100, 1) if avant else None


def fscore(a0: dict, a1: dict) -> dict | None:
    """F-score de Piotroski (9 critères) sur les deux derniers exercices. None si moins de 7 critères calculables."""
    def roa(a):
        return ratio(a.get("resultat_net"), a.get("actifs"))
    criteres = [
        ("Résultat net positif", (a0.get("resultat_net") or 0) > 0 if a0.get("resultat_net") is not None else None),
        ("Flux d'exploitation positif", (a0.get("cfo") or 0) > 0 if a0.get("cfo") is not None else None),
        ("Rentabilité des actifs en hausse", roa(a0) > roa(a1) if roa(a0) is not None and roa(a1) is not None else None),
        ("Flux d'exploitation supérieur au résultat", a0["cfo"] > a0["resultat_net"] if a0.get("cfo") is not None and a0.get("resultat_net") is not None else None),
        ("Endettement à long terme en baisse",
         ratio(a0.get("dette_lt") or 0, a0.get("actifs")) <= ratio(a1.get("dette_lt") or 0, a1.get("actifs"))
         if a0.get("actifs") and a1.get("actifs") else None),
        ("Liquidité courante en hausse",
         ratio(a0.get("actifs_courants"), a0.get("passifs_courants")) > ratio(a1.get("actifs_courants"), a1.get("passifs_courants"))
         if all(x.get(k) for x in (a0, a1) for k in ("actifs_courants", "passifs_courants")) else None),
        ("Pas d'émission d'actions", a0["actions"] <= a1["actions"] * 1.005 if a0.get("actions") and a1.get("actions") else None),
        ("Marge brute en hausse",
         ratio(a0.get("marge_brute"), a0.get("ca")) > ratio(a1.get("marge_brute"), a1.get("ca"))
         if all(x.get(k) for x in (a0, a1) for k in ("marge_brute", "ca")) else None),
        ("Rotation des actifs en hausse",
         ratio(a0.get("ca"), a0.get("actifs")) > ratio(a1.get("ca"), a1.get("actifs"))
         if all(x.get(k) for x in (a0, a1) for k in ("ca", "actifs")) else None),
    ]
    calcules = [(l, v) for l, v in criteres if v is not None]
    if len(calcules) < 7:
        return None
    score = sum(1 for _, v in calcules if v)
    # Ramené sur 9 si un ou deux critères manquent (règle de trois arrondie)
    return {"score": round(score * 9 / len(calcules)), "calcules": len(calcules),
            "criteres": [{"libelle": l, "ok": v} for l, v in criteres]}


def alertes(a0: dict, a1: dict | None) -> list[dict]:
    """Signaux d'alerte comptables."""
    res = []
    rn, cfo = a0.get("resultat_net"), a0.get("cfo")
    if rn and rn > 0 and cfo is not None and cfo < 0.5 * rn:
        res.append({"cle": "ecart_benefice_cash", "titre": "Bénéfice peu converti en cash",
                    "texte": f"flux d'exploitation égal à {nb(cfo / rn * 100, 0)} % du résultat net"})
    if a1:
        if a0.get("actions") and a1.get("actions") and a0["actions"] > a1["actions"] * 1.05:
            res.append({"cle": "dilution", "titre": "Dilution forte",
                        "texte": f"nombre d'actions en hausse de {nb(pct(a0['actions'], a1['actions']), 1)} % sur un an"})
        g_ca = pct(a0.get("ca"), a1.get("ca"))
        for cle, titre in (("creances", "Hausse anormale des créances"), ("stocks", "Hausse anormale des stocks")):
            g = pct(a0.get(cle), a1.get(cle))
            if g is not None and g_ca is not None and a0.get(cle, 0) > 0.05 * (a0.get("ca") or 0) and g - g_ca > 15:
                res.append({"cle": cle, "titre": titre,
                            "texte": f"{'créances' if cle == 'creances' else 'stocks'} en hausse de {nb(g, 1)} % pour un CA en hausse de {nb(g_ca, 1)} %"})
    return res


def mesures(s: dict) -> dict:
    """Mesures brutes d'une société (avant comparaison sectorielle et notation)."""
    an = s.get("annuel") or []
    a0 = an[0] if an else {}
    a1 = an[1] if len(an) > 1 else None
    a3 = an[3] if len(an) > 3 else (an[-1] if len(an) > 2 else None)
    m = {"exercice": a0.get("fin")}
    m["croissance_ca"] = pct(a0.get("ca"), a1.get("ca")) if a1 else None
    if a3 and a3.get("ca") and a0.get("ca") and a3 is not a0:
        n = round((date.fromisoformat(a0["fin"]) - date.fromisoformat(a3["fin"])).days / 365.25)
        m["croissance_ca_3ans"] = ((a0["ca"] / a3["ca"]) ** (1 / n) - 1) * 100 if n and a3["ca"] > 0 and a0["ca"] > 0 else None
    m["croissance_benefice"] = variation_absolue(a0.get("resultat_net"), a1.get("resultat_net")) if a1 else None
    m["marge_op"] = ratio(a0.get("ebit"), a0.get("ca"))
    m["marge_op"] = m["marge_op"] * 100 if m["marge_op"] is not None else None
    m0 = ratio(a1.get("ebit"), a1.get("ca")) if a1 else None
    m["marge_op_variation"] = (m["marge_op"] - m0 * 100) if m["marge_op"] is not None and m0 is not None else None
    m["fcf"] = a0.get("fcf")
    m["conversion_cash"] = (a0["fcf"] / a0["resultat_net"] * 100) if a0.get("fcf") is not None and (a0.get("resultat_net") or 0) > 0 else None
    dn = (a0.get("dette_totale") or 0) - (a0.get("tresorerie") or 0) if a0.get("dette_totale") is not None or a0.get("tresorerie") is not None else None
    m["dette_nette"] = dn
    eb = a0.get("ebitda")
    m["dette_ebitda"] = (dn / eb) if dn is not None and eb and eb > 0 else (None if dn is None or eb is None else 99.0 if dn > 0 else -1.0)
    # Charge d'intérêts absente des données : indicateur non disponible (on ne suppose pas qu'elle est nulle)
    m["couverture_interets"] = ratio(a0.get("ebit"), a0.get("interets")) if a0.get("interets") else None
    t = a0.get("taux_impot")
    t = 0.25 if t is None or not 0 <= t <= 0.5 else t
    m["roic"] = (a0["ebit"] * (1 - t) / a0["capital_investi"] * 100) if a0.get("ebit") is not None and (a0.get("capital_investi") or 0) > 0 else None
    m["roe"] = (a0["resultat_net"] / a0["capitaux_propres"] * 100) if a0.get("resultat_net") is not None and (a0.get("capitaux_propres") or 0) > 0 else None
    m["cout_revenu"] = ratio(a0.get("charges_exploitation"), a0.get("ca"))
    m["cout_revenu"] = m["cout_revenu"] * 100 if m["cout_revenu"] is not None and 0 < m["cout_revenu"] < 2 else None
    for cle in ("depots", "primes", "actifs"):
        if a1 and a0.get(cle) and a1.get(cle):
            m["croissance_bilan"] = pct(a0[cle], a1[cle])
            m["croissance_bilan_base"] = cle
            break
    m["fscore"] = fscore(a0, a1) if a1 else None
    m["alertes"] = alertes(a0, a1) if a0 else []
    cours = s.get("cours") or []
    m["momentum_3m"], m["momentum_6m"], m["momentum_12m"] = momentum(cours, 91), momentum(cours, 182), momentum(cours, 365)
    # Valorisation : capitalisation convertie dans la devise des comptes
    cap_usd = s.get("capitalisation_usd")
    fx_c = s.get("fx_comptes")
    cap_c = cap_usd / fx_c if cap_usd and fx_c else None
    rn_ttm = s.get("resultat_net_ttm") or a0.get("resultat_net")
    m["per"] = cap_c / rn_ttm if cap_c and rn_ttm and rn_ttm > 0 else None
    m["per_negatif"] = bool(cap_c and rn_ttm is not None and rn_ttm <= 0)
    m["ev_ebitda"] = (cap_c + (dn or 0)) / eb if cap_c and eb and eb > 0 else None
    return m


# ------------------------------------------------------------------ médianes sectorielles

def medianes_sectorielles(societes: list[dict]) -> dict:
    """Médianes du PER et du VE/EBITDA par secteur (mondial) et par secteur × région (au moins 5 valeurs)."""
    groupes = {}
    for s in societes:
        m = s["mesures"]
        for cle in ((s["secteur_gics"], None), (s["secteur_gics"], s["region"])):
            g = groupes.setdefault(cle, {"per": [], "ev_ebitda": []})
            if m.get("per") and 0 < m["per"] < 200:
                g["per"].append(m["per"])
            if m.get("ev_ebitda") and 0 < m["ev_ebitda"] < 100:
                g["ev_ebitda"].append(m["ev_ebitda"])
    return {cle: {k: (round(statistics.median(v), 2) if len(v) >= 5 else None) for k, v in g.items()} | {"n": len(g["per"])}
            for cle, g in groupes.items()}


def comparer(m: dict, secteur: str, region: str, med: dict) -> dict:
    """Prime (+) ou décote (−) en % par rapport à la médiane régionale du secteur, à défaut mondiale."""
    res = {}
    for cle in ("per", "ev_ebitda"):
        mondiale = (med.get((secteur, None)) or {}).get(cle)
        regionale = (med.get((secteur, region)) or {}).get(cle)
        ref = regionale or mondiale
        res[f"{cle}_mediane_mondiale"] = mondiale
        res[f"{cle}_mediane_regionale"] = regionale
        res[f"{cle}_secteur"] = round((m[cle] / ref - 1) * 100, 1) if m.get(cle) and ref else None
    return res


# ------------------------------------------------------------------ notation

BAREMES = {
    "croissance_ca": [(-10, 10), (0, 40), (10, 75), (25, 95)],
    "croissance_benefice": [(-30, 10), (0, 45), (15, 75), (40, 90)],
    "marge_op": [(0, 20), (10, 55), (25, 85), (40, 95)],
    "conversion_cash": [(0, 20), (50, 45), (100, 80), (130, 90)],
    "dette_ebitda": [(-1, 95), (0, 92), (1, 80), (2, 65), (3, 45), (5, 15), (99, 5)],
    "couverture_interets": [(1, 10), (3, 45), (8, 75), (20, 95)],
    "roic": [(0, 15), (8, 50), (15, 75), (25, 92)],
    "roe": [(0, 15), (8, 45), (12, 65), (18, 85), (25, 92)],
    "cout_revenu": [(40, 90), (55, 65), (70, 35), (85, 10)],
    "croissance_bilan": [(-5, 20), (0, 40), (5, 60), (10, 75), (20, 85)],
    "per_secteur": [(-40, 90), (-20, 75), (0, 55), (30, 30), (80, 10)],
    "ev_ebitda_secteur": [(-40, 90), (-20, 75), (0, 55), (30, 30), (80, 10)],
    "momentum_12m": [(-30, 10), (0, 45), (20, 70), (50, 85)],
    "fscore": [(0, 5), (3, 30), (5, 55), (7, 80), (9, 97)],
}


def notes(m: dict, financier: str | None) -> dict:
    """Note /100 de chaque indicateur disponible."""
    n = {}
    for cle in BAREMES:
        v = m.get(cle)
        if cle == "fscore":
            v = (m.get("fscore") or {}).get("score")
        if cle == "conversion_cash" and v is None and m.get("fcf") is not None and m["fcf"] < 0:
            n[cle] = 15
            continue
        if cle == "per_secteur" and v is None and m.get("per_negatif"):
            n[cle] = 15
            continue
        if v is not None:
            note = lin(v, BAREMES[cle])
            if cle == "marge_op" and m.get("marge_op_variation") is not None:
                note += 5 if m["marge_op_variation"] > 0.5 else -5 if m["marge_op_variation"] < -0.5 else 0
            n[cle] = max(0, min(100, note))
    if financier:  # critères non pertinents pour une banque ou un assureur
        for cle in ("marge_op", "conversion_cash", "dette_ebitda", "couverture_interets", "roic", "ev_ebitda_secteur", "fscore"):
            n.pop(cle, None)
        if financier != "banque":
            n.pop("cout_revenu", None)
    else:
        for cle in ("roe", "cout_revenu", "croissance_bilan"):
            n.pop(cle, None)
    return n


def note_globale(n: dict, ponderations: dict) -> dict:
    poids = {k: v for k, v in ponderations.items() if not k.startswith("_")}
    total = sum(poids.values())
    dispo = {k: w for k, w in poids.items() if k in n}
    if not dispo:
        return {"note": None, "couverture": 0.0, "ramenee": False}
    brute = sum(n[k] * w for k, w in dispo.items()) / sum(dispo.values())
    couverture = sum(dispo.values()) / total
    note = round(brute)
    # Deux signaux concordants au minimum pour un verdict tranché
    forts = sum(1 for k in dispo if n[k] >= 65)
    faibles = sum(1 for k in dispo if n[k] < 45)
    ramenee = False
    if note >= 65 and forts < 2:
        note, ramenee = 64, True
    elif note < 50 and faibles < 2:
        note, ramenee = 50, True
    return {"note": note, "brute": round(brute, 1), "couverture": round(couverture, 2), "ramenee": ramenee}


def niveau(note: int | None) -> str | None:
    if note is None:
        return None
    return "attractif" if note >= 65 else "neutre" if note >= 50 else "defavorable"


def confiance(s: dict, g: dict, aujourdhui: date) -> dict:
    raisons = []
    niveau_c = "élevé"
    verif = (s.get("verification") or {}).get("statut")
    if not s.get("officiel"):
        niveau_c = "moyen"
        raisons.append("comptes issus de Yahoo Finance uniquement (pas de source officielle exploitée)")
    elif verif == "divergent":
        niveau_c = "moyen"
        raisons.append("écart entre la source officielle et Yahoo Finance (la source officielle est retenue)")
    elif verif == "concordant":
        raisons.append("comptes vérifiés avec la source officielle")
    if g["couverture"] < 0.6:
        niveau_c = "faible"
        raisons.append(f"seulement {round(g['couverture'] * 100)} % des indicateurs disponibles")
    ex = (s.get("annuel") or [{}])[0].get("fin")
    if ex and (aujourdhui - date.fromisoformat(ex)).days > 550:
        niveau_c = "faible"
        raisons.append(f"dernier exercice clos le {ex}")
    if g.get("ramenee"):
        raisons.append("note ramenée en zone neutre : moins de deux signaux concordants")
    return {"niveau": niveau_c, "raisons": raisons}


# ------------------------------------------------------------------ indicateurs affichés et textes

def _aff(cle: str, v) -> str:
    if v is None:
        return "non disponible"
    if cle in ("croissance_ca", "croissance_benefice", "momentum_12m", "per_secteur", "ev_ebitda_secteur", "croissance_bilan"):
        return f"{nb(v, 1, signe=True)} %"
    if cle in ("marge_op", "roic", "roe", "cout_revenu", "conversion_cash"):
        return f"{nb(v, 1)} %"
    if cle == "dette_ebitda":
        return "trésorerie nette" if v < 0 else "EBITDA négatif" if v >= 99 else f"{nb(v, 1)}×"
    if cle == "couverture_interets":
        return "pas de charge d'intérêts" if v >= 100 else f"{nb(v, 1)}×"
    if cle == "fscore":
        return f"{v}/9"
    return nb(v, 1)


def indicateurs_affiches(m: dict, n: dict) -> dict:
    res = {}
    for cle in n:
        v = (m.get("fscore") or {}).get("score") if cle == "fscore" else m.get(cle)
        compl = ""
        if cle == "croissance_ca" and m.get("croissance_ca_3ans") is not None:
            compl = f"tendance sur 3 ans : {nb(m['croissance_ca_3ans'], 1, signe=True)} % par an"
        elif cle == "marge_op" and m.get("marge_op_variation") is not None:
            compl = f"{nb(m['marge_op_variation'], 1, signe=True)} pt sur un an"
        elif cle == "per_secteur" and m.get("per"):
            ref = m.get("per_mediane_regionale") or m.get("per_mediane_mondiale")
            compl = f"PER {nb(m['per'], 1)}" + (f" ; médiane du secteur {nb(ref, 1)}" if ref else "")
        elif cle == "per_secteur" and m.get("per_negatif"):
            compl = "résultat négatif : PER non significatif"
        elif cle == "ev_ebitda_secteur" and m.get("ev_ebitda"):
            ref = m.get("ev_ebitda_mediane_regionale") or m.get("ev_ebitda_mediane_mondiale")
            compl = f"VE/EBITDA {nb(m['ev_ebitda'], 1)}" + (f" ; médiane {nb(ref, 1)}" if ref else "")
        elif cle == "momentum_12m" and m.get("momentum_6m") is not None:
            compl = f"6 mois : {nb(m['momentum_6m'], 1, signe=True)} %"
        elif cle == "conversion_cash" and m.get("fcf") is not None and m["fcf"] < 0:
            compl = "flux de trésorerie disponible négatif"
        elif cle == "croissance_bilan" and m.get("croissance_bilan_base"):
            compl = {"depots": "dépôts", "primes": "primes", "actifs": "total du bilan"}[m["croissance_bilan_base"]] + " sur un an"
        res[cle] = {"libelle": LIBELLES[cle], "valeur": None if v is None else round(v, 2), "note": n[cle],
                    "affichage": "flux négatif" if cle == "conversion_cash" and v is None else "PER négatif" if cle == "per_secteur" and v is None else _aff(cle, v),
                    "complement": compl}
    return res


def verdict(ind: dict, note: int | None) -> str:
    if note is None:
        return "Données insuffisantes pour noter la société."
    tri = sorted(ind.items(), key=lambda kv: -kv[1]["note"])
    forts = [f"{v['libelle'].lower()} : {v['affichage']}" for _, v in tri[:2] if v["note"] >= 60]
    faibles = [f"{v['libelle'].lower()} : {v['affichage']}" for _, v in tri[::-1][:1] if v["note"] < 45]
    debut = {"attractif": "Dossier solide sur les comptes", "neutre": "Dossier équilibré", "defavorable": "Dossier fragile"}[niveau(note)]
    t = debut
    if forts:
        t += " ; points forts : " + ", ".join(forts)
    if faibles:
        t += " ; point faible : " + faibles[0]
    return t + "."


def contre_scenario(m: dict, ind: dict) -> list[str]:
    res = []
    if (m.get("croissance_ca") or 0) > 10:
        res.append("La croissance du chiffre d'affaires repose sur le dernier exercice : un ralentissement au prochain rapport annuel ferait baisser la note.")
    if (m.get("per_secteur") or 0) < -15:
        res.append("La décote de valorisation peut refléter un risque que les comptes ne montrent pas (secteur en déclin, gouvernance, réglementation).")
    if (m.get("per_secteur") or 0) > 25:
        res.append("La valorisation est supérieure à celle du secteur : une déception sur les résultats pèserait davantage sur le cours.")
    if m.get("dette_ebitda") is not None and 2 < m["dette_ebitda"] < 99:
        res.append("L'endettement rend la société sensible à une hausse des taux ou à une baisse de l'EBITDA.")
    if (m.get("momentum_12m") or 0) < -15:
        res.append("Le cours recule sur 12 mois : le marché anticipe peut-être une détérioration non encore visible dans les comptes.")
    if m.get("alertes"):
        res.append("Signal d'alerte comptable relevé : la qualité du résultat est à vérifier dans le rapport annuel.")
    if not res:
        res.append("Les indicateurs reposent sur les derniers comptes annuels : un changement de tendance au prochain trimestre n'est pas encore pris en compte.")
    return res[:4]


def etude(nom: str, m: dict, ind: dict, montants: dict, devise: str) -> list[dict]:
    def part(cle):
        return ind.get(cle, {}).get("affichage", "non disponible")
    ca = montants.get("ca")
    return [
        {"titre": "Activité", "texte": f"Chiffre d'affaires de {ca['local_texte']} ({ca['usd_texte']}) sur l'exercice clos le {m.get('exercice')}, "
                                       f"en variation de {part('croissance_ca')} sur un an." if ca else "Chiffre d'affaires non disponible."},
        {"titre": "Rentabilité", "texte": f"Marge opérationnelle : {part('marge_op')} ; ROIC : {part('roic')} ; ROE : {_aff('roe', m.get('roe'))}."},
        {"titre": "Trésorerie et bilan", "texte": f"Conversion du bénéfice en cash : {part('conversion_cash')} ; dette nette / EBITDA : {part('dette_ebitda')} ; "
                                                  f"couverture des intérêts : {part('couverture_interets')}."},
        {"titre": "Valorisation et marché", "texte": f"PER vs secteur : {part('per_secteur')} ; VE/EBITDA vs secteur : {part('ev_ebitda_secteur')} ; "
                                                     f"momentum 12 mois : {part('momentum_12m')}."},
        {"titre": "Qualité des comptes", "texte": "F-score de Piotroski : " + part("fscore") + ". "
                                                  + ("Signaux d'alerte : " + " ; ".join(a["titre"].lower() for a in m.get("alertes", [])) + "." if m.get("alertes") else "Aucun signal d'alerte comptable relevé.")},
    ]


def montant_texte(v: float | None, devise: str) -> str:
    if v is None:
        return "n. d."
    a = abs(v)
    if a >= 1e9:
        return f"{nb(v / 1e9, 1)} Md {devise}"
    if a >= 1e6:
        return f"{nb(v / 1e6, 0)} M {devise}"
    return f"{nb(v, 0)} {devise}"


# ------------------------------------------------------------------ pépites et contexte

def ajustement_contexte(note_pays: int | None, phase: str | None, cfg: dict) -> dict:
    a = 0.0
    details = []
    if note_pays is not None:
        p = cfg["poids_pays"] * (note_pays - 50)
        a += p
        details.append(f"pays noté {note_pays}/100 : {nb(p, 1, signe=True)} pt")
    if phase:
        p = cfg["points_phase"].get(phase, 0)
        a += p
        details.append(f"phase « {phase} » : {nb(p, 0, signe=True)} pt")
    a = max(-cfg["plafond"], min(cfg["plafond"], a))
    return {"points": round(a, 1), "details": details}


def criteres_pepite(m: dict, n: dict, financier: str | None, cfg: dict) -> dict:
    """Critères cumulés (seuils en configuration). Renvoie le détail critère par critère."""
    val = m.get("per_secteur") if m.get("per_secteur") is not None else m.get("ev_ebitda_secteur")
    c = {
        "croissance_ca": (m.get("croissance_ca") or -999) >= cfg["croissance_ca_min"],
        "marge_en_hausse": (m.get("marge_op_variation") or -1) > 0 if not financier else (m.get("croissance_benefice") or -1) > 0,
        "cash_positif": (m.get("fcf") or -1) > 0 if not financier else (m.get("roe") or 0) > 10,
        "dette": (m.get("dette_ebitda") if m.get("dette_ebitda") is not None else 99) <= cfg["dette_ebitda_max"] if not financier else True,
        "fscore": ((m.get("fscore") or {}).get("score") or 0) >= cfg["fscore_min"] if not financier else True,
        "valorisation": val is not None and val <= cfg["valorisation_max_pct"],
        "aucune_alerte": not m.get("alertes"),
    }
    return {"ok": all(c.values()), "criteres": c}


def revue_critique(s: dict, m: dict, ind: dict, pays: dict | None, devise_3m: float | None) -> dict:
    faibles = [f"{v['libelle']} : {v['affichage']}" for v in sorted(ind.values(), key=lambda v: v["note"])[:2] if v["note"] < 60]
    risques = faibles or ["Aucun indicateur sous 60/100 : le risque principal est un retournement de la tendance récente."]
    if (m.get("croissance_ca") or 0) > 25:
        risques.append("Croissance très rapide : vérifier qu'elle ne provient pas d'une acquisition ou d'un élément non récurrent.")
    piege = "peu probable au vu des comptes"
    if (m.get("per_secteur") or 0) < -20 and ((m.get("momentum_12m") or 0) < 0 or (m.get("croissance_benefice") or 0) < 0):
        piege = "possible : décote marquée associée à un cours ou à un bénéfice en recul"
    devise = s.get("devise_comptes") or "?"
    change = "comptes en dollars : pas de risque de change direct pour un investisseur en dollars" if devise == "USD" else \
        f"comptes en {devise} : la performance en dollars dépend aussi du change" + (f" (devise du pays {nb(devise_3m, 1, signe=True)} % sur 3 mois contre le dollar)" if devise_3m is not None else "")
    risque_pays = "note du pays non disponible"
    if pays:
        risque_pays = f"{pays['nom']} noté {pays.get('note')}/100 ({pays.get('niveau')}), confiance {((pays.get('confiance') or {}).get('niveau')) or '?'}"
        if (pays.get("qualite") or {}).get("alerte"):
            risque_pays += " ; alerte sur la qualité des données du pays"
    a_verifier = [
        "Lire le dernier rapport annuel : origine de la croissance (organique ou acquisitions), concentration des clients.",
        "Vérifier l'actionnariat (actionnaire de contrôle, État) et la politique de dividende.",
        "Comparer avec les publications trimestrielles les plus récentes, postérieures aux comptes analysés.",
    ]
    if s.get("pays") in ("CN", "SA", "AE", "VN", "EG", "TR", "AR"):
        a_verifier.append("Vérifier l'accessibilité du titre pour un investisseur étranger et les contrôles de capitaux.")
    return {"risques": risques, "piege_de_valeur": piege, "risque_change": change, "risque_pays": risque_pays,
            "a_verifier": a_verifier, "rapport_officiel": (s.get("officiel") or {}).get("url")}


# ------------------------------------------------------------------ cotations multiples, holdings, listes de pépites

def regrouper_cotations(societes: list[dict], cle) -> list[dict]:
    """Une société cotée plusieurs fois (catégories d'actions A/B, double cotation NEM / NEM.AX) n'apparaît
    qu'une fois : on garde la cotation la plus liquide et on note les autres dans « autres_cotations ».
    Même nom ne suffit pas (EQT Corporation et EQT AB sont deux sociétés) : il faut aussi le même secteur
    et des capitalisations comparables (rapport de 1 à 2 au plus)."""
    groupes = {}
    for s in societes:
        groupes.setdefault(cle(s.get("nom") or s["ticker"]) or s["ticker"], []).append(s)

    def compatibles(a, b):
        if a.get("secteur_gics") != b.get("secteur_gics"):
            return False
        ca, cb = a.get("capitalisation_usd"), b.get("capitalisation_usd")
        return not (ca and cb) or 0.5 <= ca / cb <= 2

    res = []
    for g in groupes.values():
        g = sorted(g, key=lambda s: (bool(s.get("surveillance")), s.get("liquidite_musd") or 0), reverse=True)
        grappes = []
        for s in g:
            for gr in grappes:
                if compatibles(gr[0], s):
                    gr.append(s)
                    break
            else:
                grappes.append([s])
        for gr in grappes:
            principale = gr[0]
            principale["autres_cotations"] = [{"ticker": s["ticker"], "pays": s["pays"]} for s in gr[1:]]
            res.append(principale)
    return res


def est_holding(nom: str, industrie: str | None, ticker: str, cfg: dict, secteur: str | None = None) -> bool:
    """Holding, société d'investissement (ex. Investor AB), fonds fermé, BDC, véhicule de crédit ou SPAC : exclus des
    pépites et du chef d'orchestre, et jamais « Acheter » sur une valorisation PER, faute de pouvoir mesurer la décote
    sur l'actif net avec des sources gratuites."""
    ind = (industrie or "").lower()
    if ticker in cfg.get("tickers_exclus", []):
        return True
    if any(x.lower() in ind for x in cfg.get("industries_exclues", [])):
        return True
    n = f" {(nom or '').lower()} "
    nom_holding = any(m in n for m in cfg.get("holdings_mots", []))
    # Industrie inconnue (.info refusé) : le nom suffit pour une société du secteur Finance
    if nom_holding and ("asset management" in ind or (not ind and secteur == "Financials")):
        return True
    # Fonds fermés, BDC, véhicules de crédit : leur valeur se lit sur l'actif net, pas sur un PER
    nom_fonds = any(m in n for m in cfg.get("fonds_mots", []))
    if nom_fonds and (any(x.lower() in ind for x in cfg.get("fonds_industries", [])) or (not ind and secteur == "Financials")):
        return True
    # SPAC (sociétés d'acquisition sans activité propre)
    if any(m in n for m in cfg.get("spac_mots", [])):
        return True
    return False


def selection_listes(candidats: list[dict], cfg: dict) -> dict[str, list[dict]]:
    """candidats : sociétés qui remplissent tous les critères ({ticker, cap, analystes, secteur, note_ajustee}).
    « pepites » : capitalisation entre cap_min et cap_max (Md$), peu suivies ; « qpr » : au-dessus de cap_max.
    Au plus plafond_par_secteur sociétés d'un même secteur dans chaque liste."""
    listes = {"pepites": [], "qpr": []}
    par_secteur = {"pepites": {}, "qpr": {}}
    for c in sorted(candidats, key=lambda c: -c["note_ajustee"]):
        cap = c.get("cap") or 0
        if cap >= cfg["cap_max_md"]:
            liste, maximum = "qpr", cfg.get("nombre_max_qpr", cfg["nombre_max"])
        elif cap >= cfg["cap_min_md"] and (c.get("analystes") is None or c["analystes"] <= cfg["analystes_max"]):
            liste, maximum = "pepites", cfg["nombre_max"]
        else:
            continue  # trop suivie pour une pépite, trop petite pour la liste « qualité à prix raisonnable »
        n = par_secteur[liste].get(c["secteur"], 0)
        if n >= cfg["plafond_par_secteur"] or len(listes[liste]) >= maximum:
            continue
        par_secteur[liste][c["secteur"]] = n + 1
        listes[liste].append(c)
    return listes


# Industries Yahoo fréquentes : libellé français et sensibilité principale
INDUSTRIES = {
    "gold": ("mines d'or", "sensibilité au cours de l'or"),
    "other precious metals & mining": ("mines de métaux précieux", "sensibilité aux cours des métaux précieux"),
    "copper": ("mines de cuivre", "sensibilité au cours du cuivre"),
    "other industrial metals & mining": ("mines de métaux industriels", "sensibilité aux cours des métaux"),
    "steel": ("sidérurgistes", "sensibilité au cycle de l'acier"),
    "oil & gas e&p": ("producteurs de pétrole et de gaz", "sensibilité aux cours du pétrole et du gaz"),
    "oil & gas integrated": ("pétrolières intégrées", "sensibilité aux cours du pétrole"),
    "oil & gas midstream": ("transport de pétrole et de gaz", "sensibilité aux volumes d'hydrocarbures"),
    "semiconductors": ("fabricants de semi-conducteurs", "sensibilité au cycle des semi-conducteurs"),
    "semiconductor equipment & materials": ("équipementiers de semi-conducteurs", "sensibilité au cycle des semi-conducteurs"),
    "banks - regional": ("banques régionales", "sensibilité aux taux et au crédit"),
    "banks - diversified": ("banques", "sensibilité aux taux et au crédit"),
    "insurance - property & casualty": ("assureurs dommages", "sensibilité aux sinistres et aux catastrophes naturelles"),
    "agricultural inputs": ("producteurs d'engrais", "sensibilité aux prix des engrais et du gaz"),
    "airlines": ("compagnies aériennes", "sensibilité au kérosène et à la demande de voyages"),
}


def concentration(candidats: list[dict], cfg: dict) -> list[str]:
    """Avertissement quand une industrie (ou un secteur) est surreprésentée parmi les candidates."""
    total = len(candidats)
    if not total:
        return []
    avert = []
    for cle, libelle_par_defaut in (("industrie", None), ("secteur_nom", None)):
        compte = {}
        for c in candidats:
            if c.get(cle):
                compte[c[cle]] = compte.get(c[cle], 0) + 1
        for valeur, n in sorted(compte.items(), key=lambda kv: -kv[1]):
            if n >= cfg["concentration_min"] and n / total >= cfg["concentration_seuil"]:
                if cle == "industrie":
                    nom, risque = INDUSTRIES.get(valeur.lower(), (f"« {valeur} »", "sensibilité au cycle de cette industrie"))
                    avert.append(f"{n} candidates sur {total} sont des {nom} : {risque}." if valeur.lower() in INDUSTRIES
                                 else f"{n} candidates sur {total} relèvent de l'industrie {nom} : {risque}.")
                else:
                    avert.append(f"{n} candidates sur {total} appartiennent au secteur {valeur} : concentration sectorielle.")
        if avert:
            break  # l'industrie, plus précise, suffit quand elle est déjà surreprésentée
    return avert
