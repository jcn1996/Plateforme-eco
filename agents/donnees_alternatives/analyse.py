"""
Calculs de l'agent données alternatives (sans réseau, testés seuls). Règles : voir regles.md.

Pour chaque indicateur : dernière valeur, variations sur 1 et 12 mois, écart à la tendance (moyenne des
3 derniers mois contre celle des 12 derniers), écart à la normale saisonnière, percentile historique de la
variation sur 12 mois, note d'activité /100. Puis, par pays : score d'activité /100 (au moins 2 indicateurs
à jour), lecture « accélération », « stable » ou « ralentissement », confiance, « Ce qui pourrait me donner
tort », divergence avec les statistiques officielles de l'agent pays.
"""
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from statistics import mean, pstdev

Serie = list[tuple[str, float]]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MOTS_INTERDITS = ("certain", "garanti", "assurément", "sans aucun doute", "exceptionnel", "incroyable", "acheter", "vendre")


def fr(x, d=1, signe=False) -> str:
    if x is None:
        return "n. d."
    t = f"{abs(x):,.{d}f}".replace(",", " ").replace(".", ",")
    if signe:
        return ("+" if x > 0 else "−" if x < 0 else "") + t
    return ("−" if x < 0 else "") + t


def date_fr(d: str | None) -> str:
    if not d:
        return "date inconnue"
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) >= 10 else d


def mois_fr(d: str) -> str:
    return f"{MOIS[int(d[5:7]) - 1]} {d[:4]}"


def jour(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def arrondi(x: float) -> int:
    """Arrondi à l'entier le plus proche, 0,5 vers le haut (comme l'appli), pour que textes et affichage concordent."""
    return int(math.floor(x + 0.5))


def borner(x: float, a: float = 0, b: float = 100) -> float:
    return max(a, min(b, x))


def pct(a, b) -> float | None:
    return None if a is None or b in (None, 0) else (a / b - 1) * 100


def percentile(valeur: float, historique: list[float]) -> float | None:
    """Part des valeurs historiques inférieures (les égalités comptent pour moitié), en %."""
    h = [x for x in historique if x is not None]
    if len(h) < 12 or valeur is None:
        return None
    return round(100 * (sum(1 for x in h if x < valeur) + 0.5 * sum(1 for x in h if x == valeur)) / len(h), 1)


def conformes(textes: list[str]) -> bool:
    return not any(re.search(rf"\b{m}\b", (t or "").lower()) for t in textes for m in MOTS_INTERDITS)


# ------------------------------------------------------------------ séries

def mensuelle(points: Serie, frequence: str, aujourdhui: date) -> Serie:
    """Moyenne par mois calendaire (AAAA-MM-01). Pour une série quotidienne, le mois en cours n'est gardé
    qu'avec au moins 10 jours ; pour une série hebdomadaire, au moins 2 relevés."""
    groupes: dict[str, list[float]] = {}
    for d, v in points:
        groupes.setdefault(d[:7] + "-01", []).append(v)
    mini = {"quotidienne": 10, "hebdomadaire": 2}.get(frequence, 1)
    res = []
    for m, vals in sorted(groupes.items()):
        en_cours = m[:7] == aujourdhui.isoformat()[:7]
        if frequence != "mensuelle" and (len(vals) < mini if en_cours else len(vals) < max(1, mini // 3)):
            continue
        res.append((m, mean(vals)))
    return res


def _decaler_mois(m: str, n: int) -> str:
    a, mo = int(m[:4]), int(m[5:7]) - n
    while mo <= 0:
        a, mo = a - 1, mo + 12
    return f"{a}-{mo:02d}-01"


def glissements(M: Serie, n: int = 12) -> list[tuple[str, float]]:
    """Variations (%) d'un mois sur le même mois n mois plus tôt."""
    idx = dict(M)
    return [(m, pct(v, idx.get(_decaler_mois(m, n)))) for m, v in M if idx.get(_decaler_mois(m, n))]


def ecarts_tendance(M: Serie) -> list[tuple[str, float]]:
    """Écart (%) entre la moyenne des 3 derniers mois et celle des 12 derniers, à chaque mois."""
    res = []
    for i in range(11, len(M)):
        if M[i - 11][0] != _decaler_mois(M[i][0], 11):
            continue  # mois manquants : pas d'écart calculé sur une fenêtre incomplète
        trois = mean(v for _, v in M[i - 2:i + 1])
        douze = mean(v for _, v in M[i - 11:i + 1])
        res.append((M[i][0], pct(trois, douze)))
    return res


def ecart_saisonnier(M: Serie) -> float | None:
    """Écart (%) du dernier mois à sa normale saisonnière : moyenne des 12 mois précédents × facteur du même
    mois calendaire (rapport moyen, sur les années passées, entre ce mois et la moyenne des 12 mois qui le précèdent)."""
    if len(M) < 37:
        return None
    facteurs = []
    for i in range(12, len(M) - 1):
        if M[i][0][5:7] == M[-1][0][5:7]:
            base = mean(v for _, v in M[i - 12:i])
            if base:
                facteurs.append(M[i][1] / base)
    if len(facteurs) < 2:
        return None
    attendu = mean(v for _, v in M[-13:-1]) * mean(facteurs)
    return pct(M[-1][1], attendu)


def fenetre(points: Serie, fin: date, jours: int) -> float | None:
    debut = fin - timedelta(days=jours)
    vals = [v for d, v in points if debut < jour(d) <= fin]
    return mean(vals) if len(vals) >= max(2, jours // 7) else None


def proche(points: Serie, cible: date, tolerance: int) -> float | None:
    cands = [(abs((jour(d) - cible).days), v) for d, v in points if abs((jour(d) - cible).days) <= tolerance]
    return min(cands)[1] if cands else None


def analyser_serie(points: Serie, frequence: str, aujourdhui: date, sens: int = 1, fraicheur_jours: int = 110) -> dict | None:
    """Mesures d'un indicateur et note d'activité /100 (au-dessus de 50 : activité plus soutenue que d'habitude)."""
    points = sorted((str(d)[:10], float(v)) for d, v in points if v is not None)
    if len(points) < 2:
        return None
    derniere_date, derniere = points[-1]
    M = mensuelle(points, frequence, aujourdhui)
    if frequence == "mensuelle":
        idx = dict(M)
        v1 = pct(M[-1][1], M[-2][1]) if len(M) >= 2 else None
        v12 = pct(M[-1][1], idx.get(_decaler_mois(M[-1][0], 12)))
    else:
        fin = jour(derniere_date)
        recent = fenetre(points, fin, 28)
        v1 = pct(recent, fenetre(points, fin - timedelta(days=28), 28))
        v12 = pct(recent, fenetre(points, fin - timedelta(days=364), 28))
        # Historique clairsemé (source accumulée relevé après relevé) : point le plus proche, à quelques jours près
        if v12 is None:
            v12 = pct(derniere, proche(points, fin - timedelta(days=364), 10))
        if v1 is None:
            v1 = pct(derniere, proche(points, fin - timedelta(days=28), 7))
    g = [x for _, x in glissements(M)]
    t = ecarts_tendance(M)
    tendance = t[-1][1] if t else None
    p12 = percentile(v12, g[:-1] if frequence == "mensuelle" else g) if v12 is not None else None
    pt = percentile(tendance, [x for _, x in t[:-1]]) if tendance is not None else None
    if p12 is not None and pt is not None:
        note, methode = 0.6 * p12 + 0.4 * pt, "percentiles"
    elif p12 is not None:
        note, methode = p12, "percentiles"
    elif v12 is not None:  # historique trop court pour un percentile : échelle fixe
        note, methode = 50 + 50 * math.tanh(v12 / 12), "échelle fixe (historique court)"
    elif v1 is not None:
        note, methode = 50 + 50 * math.tanh(v1 / 6), "échelle fixe (historique court)"
    else:
        note, methode = None, None
    if note is not None and sens < 0:
        note = 100 - note
    age = (aujourdhui - jour(derniere_date)).days
    return {
        "valeur": round(derniere, 3), "date": derniere_date,
        "variation_1m": round(v1, 2) if v1 is not None else None,
        "variation_12m": round(v12, 2) if v12 is not None else None,
        "ecart_tendance": round(tendance, 2) if tendance is not None else None,
        "ecart_saisonnier": round(es, 2) if (es := ecart_saisonnier(M)) is not None else None,
        "percentile_12m": p12, "percentile_tendance": pt,
        "note": round(note, 1) if note is not None else None, "methode_note": methode,
        "historique_mois": len(M), "age_jours": age, "perimee": age > fraicheur_jours,
    }


def serie_graphique(points: Serie, frequence: str, aujourdhui: date, n: int = 110) -> list[list]:
    """Mini-graphique : moyennes hebdomadaires (séries quotidiennes) sur 2 ans, sinon points mensuels ou hebdomadaires."""
    if frequence == "quotidienne":
        semaines: dict[tuple, list] = {}
        for d, v in points:
            if jour(d) >= aujourdhui - timedelta(days=730):
                semaines.setdefault(jour(d).isocalendar()[:2], []).append((d, v))
        res = [[max(x[0] for x in vals), round(mean(x[1] for x in vals), 3)] for _, vals in sorted(semaines.items())]
    else:
        res = [[d, round(v, 3)] for d, v in points]
    return res[-n:]


# ------------------------------------------------------------------ textes d'un indicateur

def lecture_indicateur(nom: str, a: dict) -> str:
    morceaux = []
    if a.get("variation_12m") is not None:
        morceaux.append(f"{fr(a['variation_12m'], 1, True)} % sur 12 mois")
    if a.get("variation_1m") is not None:
        morceaux.append(f"{fr(a['variation_1m'], 1, True)} % sur 1 mois")
    if a.get("ecart_tendance") is not None:
        morceaux.append(f"écart à la tendance {fr(a['ecart_tendance'], 1, True)} %")
    if a.get("percentile_12m") is not None:
        morceaux.append(f"percentile {fr(a['percentile_12m'], 0)} de l'historique")
    return f"{nom} : " + (", ".join(morceaux) if morceaux else "variation non calculable") + "."


# ------------------------------------------------------------------ score par pays

def score_pays(indicateurs: list[dict], cfg: dict) -> dict:
    """Score d'activité /100 (moyenne pondérée des notes des indicateurs à jour), lecture et confiance.
    Moins de `indicateurs_min` indicateurs à jour : pas de score (pas de conclusion sur un seul indicateur)."""
    s = cfg["score"]
    actifs = [i for i in indicateurs if i.get("note") is not None and not i.get("perimee") and i["categorie"] != "attention"]
    if len(actifs) < s["indicateurs_min"]:
        return {"score": None, "lecture": None, "indicateurs_utilises": len(actifs),
                "raison": f"{len(actifs)} indicateur{'s' if len(actifs) > 1 else ''} à jour : au moins {s['indicateurs_min']} sont nécessaires pour conclure"}
    poids = sum(i["poids"] for i in actifs)
    score = arrondi(sum(i["poids"] * i["note"] for i in actifs) / poids)  # entier, 0,5 vers le haut (comme l'appli)
    hauts = [i for i in actifs if i["note"] >= s["seuil_concordant_haut"]]
    bas = [i for i in actifs if i["note"] <= s["seuil_concordant_bas"]]
    if score >= s["acceleration"] and len(hauts) >= s["concordants_min"]:
        lecture = "accélération"
    elif score <= s["ralentissement"] and len(bas) >= s["concordants_min"]:
        lecture = "ralentissement"
    else:
        lecture = "stable"
    non_retenue = None
    if lecture == "stable" and (score >= s["acceleration"] or score <= s["ralentissement"]):
        sens = "accélération" if score >= s["acceleration"] else "ralentissement"
        non_retenue = f"score dans la zone « {sens} », mais un seul indicateur dans ce sens : lecture maintenue à « stable »"
    conf = confiance(actifs, indicateurs)
    marque = lecture != "stable" and (score >= s["marque_haut"] or score <= s["marque_bas"])
    return {"score": arrondi(score), "lecture": lecture, "marque": marque, "lecture_non_retenue": non_retenue,
            "indicateurs_utilises": len(actifs), "confiance": conf,
            "pour": [i["cle"] for i in hauts], "contre": [i["cle"] for i in bas]}


def confiance(actifs: list[dict], tous: list[dict]) -> dict:
    score, raisons = 1.0, []
    if len(actifs) == 2:
        score -= 0.25
        raisons.append("deux indicateurs seulement")
    notes = [i["note"] for i in actifs]
    if len(notes) >= 2 and pstdev(notes) > 20:
        score -= 0.2
        raisons.append("indicateurs peu concordants")
    if any(i.get("mention_proxy") for i in actifs):
        score -= 0.1
        raisons.append("au moins un indicateur approché ou expérimental")
    courts = [i["nom"] for i in actifs if i.get("methode_note") != "percentiles"]
    if courts:
        score -= 0.1
        raisons.append("historique court pour : " + ", ".join(courts))
    perimes = [i["nom"] for i in tous if i.get("perimee")]
    if perimes:
        score -= 0.05 * len(perimes)
        raisons.append("données anciennes écartées : " + ", ".join(perimes))
    score = max(0.0, round(score, 2))
    niveau = "élevé" if score >= 0.8 and len(actifs) >= 3 else "moyen" if score >= 0.55 else "faible"
    if not raisons:
        raisons.append("indicateurs à jour, concordants et à historique long")
    return {"niveau": niveau, "score": score, "raisons": raisons}


def donner_tort(res: dict, indicateurs: list[dict]) -> list[str]:
    """« Ce qui pourrait me donner tort » : 2 à 3 éléments concrets."""
    pts = []
    lecture = res.get("lecture")
    actifs = [i for i in indicateurs if i.get("note") is not None and not i.get("perimee")]
    if lecture == "accélération":
        contraires = [i for i in actifs if i["note"] < 50]
    elif lecture == "ralentissement":
        contraires = [i for i in actifs if i["note"] > 50]
    else:
        contraires = sorted(actifs, key=lambda i: abs(i["note"] - 50), reverse=True)[:1]
    for i in contraires[:2]:
        pts.append(f"{i['nom']} va dans l'autre sens ({fr(i.get('variation_12m'), 1, True)} % sur 12 mois)")
    if res.get("indicateurs_utilises", 0) <= 2:
        pts.append("la lecture repose sur deux indicateurs seulement : une seule révision peut la modifier")
    if any(i["categorie"] == "energie" for i in actifs):
        pts.append("la consommation d'électricité varie aussi avec les températures, pas seulement avec l'activité")
    if any(i.get("frequence") == "mensuelle" for i in actifs):
        pts.append("les données mensuelles sont publiées avec retard et souvent révisées")
    if not pts:
        pts.append("un changement simultané de plusieurs indicateurs lors des prochaines publications")
    vus, res_ = set(), []
    for p in pts:
        if p not in vus:
            vus.add(p)
            res_.append(p[0].upper() + p[1:] + ".")
    return res_[:3]


def officiel(pays: dict | None) -> dict | None:
    """Note moyenne des statistiques officielles de l'agent pays (croissance du PIB, indicateur avancé de l'OCDE)."""
    if not pays:
        return None
    inds = pays.get("indicateurs") or {}
    retenus = [(k, inds[k]) for k in ("croissance_pib", "indicateur_avance") if (inds.get(k) or {}).get("note") is not None]
    if not retenus:
        return None
    return {"note": round(mean(i["note"] for _, i in retenus), 1),
            "texte": " ; ".join(f"{i['libelle'].lower()} {fr(i.get('valeur'), 1)}{' %' if i.get('unite') == '%' else ''} ({i['note']}/100)" for _, i in retenus)}


def divergence(res: dict, off: dict | None, indicateurs: list[dict], cfg: dict) -> dict | None:
    """Les données alternatives contredisent-elles les statistiques officielles ?"""
    s = cfg["score"]
    if not off or res.get("score") is None:
        return None
    sc = res["score"]
    baisse = [i for i in indicateurs if i.get("note") is not None and not i.get("perimee") and i["note"] <= 45]
    hausse = [i for i in indicateurs if i.get("note") is not None and not i.get("perimee") and i["note"] >= 55]
    def liste(xs):
        return ", ".join(f"{i['nom'].lower()} {fr(i.get('variation_12m'), 1, True)} %" for i in xs[:3])
    if off["note"] >= s["divergence_officiel_haut"] and sc <= s["divergence_alternatif_bas"] and len(baisse) >= 2:
        return {"sens": "officiel_solide_reel_faible",
                "texte": f"Statistiques officielles solides ({off['texte']}) mais activité réelle en retrait (score {fr(sc, 0)}/100 : {liste(baisse)} sur 12 mois)."}
    if off["note"] <= s["divergence_officiel_bas"] and sc >= s["divergence_alternatif_haut"] and len(hausse) >= 2:
        return {"sens": "officiel_faible_reel_solide",
                "texte": f"Statistiques officielles faibles ({off['texte']}) mais activité réelle soutenue (score {fr(sc, 0)}/100 : {liste(hausse)} sur 12 mois)."}
    return None


def texte_pays(nom: str, res: dict, indicateurs: list[dict]) -> str:
    if res.get("score") is None:
        return f"{nom} : {res['raison']}."
    actifs = sorted((i for i in indicateurs if i.get("note") is not None and not i.get("perimee")), key=lambda i: -i["note"])
    detail = " ; ".join(f"{i['nom'].lower()} {fr(i.get('variation_12m'), 1, True)} % sur 12 mois" for i in actifs[:3])
    return f"{nom} : activité réelle « {res['lecture']} » (score {fr(res['score'], 0)}/100 sur {res['indicateurs_utilises']} indicateurs) — {detail}."


# ------------------------------------------------------------------ attention du public

def attention(wiki: dict | None, trends: list | None, cfg: dict) -> dict | None:
    """Variation de l'attention : 30 derniers jours contre la moyenne des 60 jours précédents (Wikipédia) ;
    4 dernières semaines contre les 8 précédentes (Google Trends). Information seulement."""
    res = {}
    if wiki and wiki.get("vues"):
        v = [x[1] for x in sorted(wiki["vues"])]
        if len(v) >= 90:
            recent, avant = sum(v[-30:]), sum(v[-90:-30]) / 2
            if avant >= cfg["vues_min"]:
                res["wikipedia"] = {"article": wiki.get("article"), "vues_30j": recent, "variation_pct": round(pct(recent, avant), 1)}
    if trends:
        v = [x[1] for x in sorted(trends)]
        if len(v) >= 60:
            recent, avant = mean(v[-28:]), mean(v[-84:-28])
            if avant > 0:
                res["trends"] = {"variation_pct": round(pct(recent, avant), 1), "niveau_recent": round(recent, 1)}
    if not res:
        return None
    var = [x["variation_pct"] for x in res.values()]
    m = mean(var)
    res["tendance"] = "en hausse" if m >= cfg["hausse_pct"] else "en baisse" if m <= -cfg["hausse_pct"] else "stable"
    res["variation_moyenne_pct"] = round(m, 1)
    return res


# ------------------------------------------------------------------ signaux pour le chef d'orchestre

def signaux(precedent: dict | None, donnees: dict, aujourdhui: date) -> list[dict]:
    """Accélération ou ralentissement marqué (nouveau), divergence avec l'officiel (nouvelle), attention en forte hausse."""
    anciens = {p["code"]: p for p in (precedent or {}).get("pays", [])}
    index = {i["cle"]: i for i in donnees.get("indicateurs", [])}
    res = []
    for p in donnees["pays"]:
        a = anciens.get(p["code"]) or {}
        utilises = [index[k] for k in p["indicateurs"] if k in index and index[k].get("note") is not None]
        src = "agent données alternatives (" + ", ".join(sorted({i["source_nom"].split(" (")[0] for i in utilises})) + ")"
        if p.get("marque") and (p["lecture"] != a.get("lecture") or not a.get("marque")):
            fort = p["lecture"] == "accélération"
            res.append({"date": aujourdhui.isoformat(), "type": "activite_acceleration" if fort else "activite_ralentissement",
                        "cle": p["code"], "pays": [p["code"]], "importance": "moyenne",
                        "titre": f"{p['nom']} : activité réelle en {'accélération' if fort else 'ralentissement'} marqué (score {fr(p['score'], 0)}/100)",
                        "explication": p["texte"] + f" Confiance {p['confiance']['niveau']}.", "source": src})
        d = p.get("divergence")
        if d and d["sens"] != (a.get("divergence") or {}).get("sens"):
            res.append({"date": aujourdhui.isoformat(), "type": "divergence_officielle", "cle": p["code"], "pays": [p["code"]],
                        "importance": "moyenne", "titre": f"{p['nom']} : données alternatives en désaccord avec les statistiques officielles",
                        "explication": d["texte"], "source": src})
    anciennes_att = {x["ticker"]: x for x in (precedent or {}).get("attention", [])}
    for x in donnees.get("attention", []):
        if x.get("signal") and not (anciennes_att.get(x["ticker"]) or {}).get("signal"):
            res.append({"date": aujourdhui.isoformat(), "type": "attention_forte_hausse", "cle": x["ticker"], "pays": [x["pays"]] if x.get("pays") else [],
                        "importance": "faible", "titre": f"{x['nom']} : attention du public en forte hausse ({fr(x['variation_moyenne_pct'], 0, True)} %)",
                        "explication": "Information seulement (pondération faible) : consultations Wikipédia et recherches Google en hausse ; une attention accrue ne dit rien du sens de l'évolution.",
                        "source": "Wikipédia (API Wikimedia) et Google Trends"})
    return res
