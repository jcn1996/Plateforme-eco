"""
Moteur de décision : score d'attractivité /100, verdict (avec hystérésis), conviction, arguments,
objections du contradicteur et concentrations thématiques. Méthode : agents/chef/methode.md.
"""
from __future__ import annotations

import math
import re

from ..risque.calculs import date_fr, fr

DIRECTION = {"Renforcer fortement": 1, "Renforcer": 1, "Neutre": 0, "Alléger": -1, "Éviter": -1}
NIVEAUX_CONVICTION = ["faible", "moyenne", "forte"]
GROUPES = {"fondamentaux": "fondamentaux", "valorisation": "valorisation", "marche": "tendance", "flux": "flux", "cycle": "cycle",
           "risque": "risque", "inities": "initiés"}


def ent(x) -> str:
    """Score arrondi à l'entier le plus proche (0,5 vers le haut, comme dans l'appli)."""
    return "n. d." if x is None else fr(math.floor(x + 0.5), 0)


# ------------------------------------------------------------------ score

def poids(type_: str, config: dict, palier: str) -> dict[str, float]:
    base = config["poids"][type_]
    mult = config["regimes"].get(palier) or {}
    return {f: w * mult.get(f, 1.0) for f, w in base.items()}


def scorer(o: dict, config: dict, palier: str) -> None:
    """Ajoute à l'opportunité : score, score_brut, qualite (part du poids réellement appuyée sur des données
    fraîches et fiables), familles manquantes et poids effectifs."""
    w = poids(o["type"], config, palier)
    dispo = {f: o["familles"][f] for f in w if f in o["familles"]}
    total = sum(w.values())
    num = sum(w[f] * x["coef"] * x["note"] for f, x in dispo.items())
    den = sum(w[f] * x["coef"] for f, x in dispo.items())
    o["familles_manquantes"] = [config["familles"][f]["libelle"] for f in w if f not in dispo]
    if den <= 0:
        o.update({"score": None, "score_brut": None, "qualite": 0.0})
        return
    brut = num / den
    # Qualité : poids des familles disponibles × fiabilité, rapporté au poids total prévu pour ce type
    qualite = den / total
    score = 50 + (brut - 50) * qualite if config.get("qualite_retrecit_vers_neutre", True) else brut
    o["score_brut"] = round(brut, 1)
    o["score"] = round(score, 1)
    o["qualite"] = round(qualite, 2)
    o["poids_effectifs"] = {f: round(w[f] * x["coef"] / den * 100, 1) for f, x in dispo.items()}


def verdict_de(score: float | None, config: dict) -> str:
    if score is None:
        return "Neutre"
    s = config["verdicts"]["seuils"]
    if score >= s["Renforcer fortement"]:
        return "Renforcer fortement"
    if score >= s["Renforcer"]:
        return "Renforcer"
    if score >= s["Neutre"]:
        return "Neutre"
    if score >= s["Alléger"]:
        return "Alléger"
    return "Éviter"


def rang(v: str, config: dict) -> int:
    return config["verdicts"]["ordre"].index(v)


# ------------------------------------------------------------------ conviction

def groupes_concordants(o: dict, direction: int, config: dict) -> list[str]:
    cc = config["conviction"]
    groupes = []
    for f, x in o["familles"].items():
        n = x["note"]
        ok = (direction > 0 and n >= cc["seuil_concordance_haut"]) or (direction < 0 and n <= cc["seuil_concordance_bas"]) \
            or (direction == 0 and cc["seuil_concordance_bas"] < n < cc["seuil_concordance_haut"])
        if ok:
            g = config["familles"][f]["groupe"]
            if g not in groupes:
                groupes.append(g)
    return groupes


def conviction(o: dict, verdict: str, objections: list[dict], fraicheur_min: float, config: dict) -> dict:
    cc = config["conviction"]
    d = DIRECTION[verdict]
    groupes = groupes_concordants(o, d, config)
    confiance_ok = o.get("qualite", 0) >= 0.6
    fraiche = fraicheur_min >= cc["fraicheur_min_forte"]
    serieuses = [x for x in objections if x.get("serieuse")]
    raisons = [f"{len(groupes)} groupe(s) de signaux indépendants concordants ({', '.join(GROUPES.get(g, g) for g in groupes) or 'aucun'})"]
    if d == 0:
        niveau = 1 if len(groupes) >= cc["groupes_forte"] else 0
        raisons.append("verdict neutre : conviction au plus moyenne")
    elif len(groupes) >= cc["groupes_forte"] and confiance_ok and fraiche:  # les objections sont retirées cran par cran ci-dessous
        niveau = 2
    elif len(groupes) >= cc["groupes_moyenne"] and confiance_ok:
        niveau = 1
    else:
        niveau = 0
    if d != 0 and len(groupes) >= cc["groupes_forte"]:
        if not confiance_ok:
            raisons.append(f"confiance des données insuffisante (qualité {fr(o.get('qualite'), 2)})")
        if not fraiche:
            raisons.append("au moins une donnée utilisée est périmée ou provient d'un agent dégradé")
    for x in serieuses:
        if niveau > 0:
            niveau -= 1
        raisons.append(f"objection du contradicteur retenue (« {x['ajustement']} ») : conviction abaissée d'un cran")
    return {"niveau": NIVEAUX_CONVICTION[niveau], "groupes": groupes, "raisons": raisons}


def plafonner_extreme(v: str, conv: dict, config: dict) -> tuple[str, str | None]:
    exige = config["verdicts"].get("fort_exige_conviction")
    if not exige or v not in ("Renforcer fortement", "Éviter"):
        return v, None
    if NIVEAUX_CONVICTION.index(conv["niveau"]) >= NIVEAUX_CONVICTION.index(exige):
        return v, None
    nouveau = "Renforcer" if v == "Renforcer fortement" else "Alléger"
    return nouveau, f"« {v} » ramené à « {nouveau} » : conviction {conv['niveau']} (au moins {exige} exigée)"


# ------------------------------------------------------------------ hystérésis (anti-girouette)

def appliquer_hysteresis(o: dict, v_brut: str, etat: dict, jour: str, config: dict) -> None:
    """Fixe o["verdict"] et o["changement"]. etat[id] = {verdict, depuis, score, candidat}."""
    cv = config["verdicts"]
    e = etat.get(o["id"])
    score = o["score"]
    if not e:
        o["verdict"] = v_brut
        o["changement"] = {"date": jour, "de": None, "vers": v_brut, "explication": f"Premier verdict : score {ent(score)}/100."}
        o["depuis"] = jour
        etat[o["id"]] = {"verdict": v_brut, "depuis": jour, "score": score, "candidat": None, "historique": [[jour, v_brut]]}
        return
    actuel = e["verdict"]
    if v_brut == actuel:
        e["candidat"] = None
        o["verdict"], o["changement"] = actuel, None
        o["depuis"] = e.get("depuis")
        e["score"] = score
        return
    monte = rang(v_brut, config) > rang(actuel, config)
    v_marge = verdict_de(score - cv["marge"] if monte else score + cv["marge"], config)
    franchi_marge = v_marge != actuel and (rang(v_marge, config) > rang(actuel, config)) == monte
    cand = e.get("candidat") or {}
    jours = sorted(set((cand.get("jours") or []) + [jour])) if cand.get("verdict") == v_brut else [jour]
    confirme = len(jours) >= cv["jours_confirmation"]
    if franchi_marge or confirme:
        cible = v_marge if franchi_marge and not confirme else v_brut
        raison = (f"le score a franchi le seuil avec une marge d'au moins {fr(cv['marge'], 0)} pts" if franchi_marge and not confirme
                  else f"le score reste au-delà du seuil depuis {len(jours)} jours")
        o["verdict"] = cible
        o["changement"] = {"date": jour, "de": actuel, "vers": cible,
                           "explication": f"De « {actuel} » à « {cible} » : score {ent(e.get('score'))} → {ent(score)}/100, {raison}."}
        e.update({"verdict": cible, "depuis": jour, "score": score, "candidat": None})
        e["historique"] = (e.get("historique") or [])[-30:] + [[jour, cible]]
    else:
        e["candidat"] = {"verdict": v_brut, "jours": jours}
        o["verdict"], o["changement"] = actuel, None
        o["en_attente"] = {"vers": v_brut, "jours": len(jours),
                           "texte": f"Score {ent(score)}/100 compatible avec « {v_brut} » : changement en attente de confirmation (marge de {fr(cv['marge'], 0)} pts ou {cv['jours_confirmation']} jours de suite)."}
        e["score"] = score
    o["depuis"] = e["depuis"]


# ------------------------------------------------------------------ arguments

def arguments(o: dict, config: dict) -> tuple[list[dict], list[dict]]:
    """Les 3 familles qui tirent le plus le score vers le haut (pour) et vers le bas (contre) : écart à 50 × poids effectif."""
    pe = o.get("poids_effectifs") or {}
    contribution = lambda kv: (kv[1]["note"] - 50) * pe.get(kv[0], 1)  # noqa: E731
    fams = sorted(o["familles"].items(), key=contribution, reverse=True)
    # Le texte et la source restent dans « familles » (référence par `cle`, pour ne pas dupliquer les textes)
    item = lambda f, x: {"cle": f, "famille": config["familles"][f]["libelle"], "note": x["note"]}  # noqa: E731
    pour = [item(f, x) for f, x in fams if x["note"] > 50][:3]
    contre = [item(f, x) for f, x in reversed(fams) if x["note"] < 50][:3]
    return pour, contre


def donner_tort(o: dict, contre: list[dict], pour: list[dict], objections: list[dict]) -> list[str]:
    d = DIRECTION.get(o.get("verdict"), 0)
    res = []
    opposes = contre if d >= 0 else pour
    if opposes:
        res.append(f"{opposes[0]['famille']} ({ent(opposes[0]['note'])}/100) : {o['familles'][opposes[0]['cle']]['texte']}")
    if objections:
        res.append(f"Contradicteur : {objections[0]['objection']}")
    res += [x for x in (o.get("invalidations") or []) if x][:2]
    if o.get("familles_manquantes"):
        res.append("Données manquantes : " + ", ".join(o["familles_manquantes"]) + " (non prises en compte, pas d'estimation).")
    return res[:4] or ["Aucun signal contraire marqué dans les données disponibles ; une rupture de tendance ou un choc non encore mesuré pourrait suffire."]


# ------------------------------------------------------------------ objections

def objections_par_cible(revues: list[dict], signaux: dict[str, list[dict]], zones_pays: dict, jour: str, config: dict) -> dict[str, list[dict]]:
    """{id d'opportunité: [objections]} à partir de data/signaux/revues.json."""
    from datetime import date, timedelta
    lim = (date.fromisoformat(jour) - timedelta(days=config["univers"]["objection_fenetre_jours"])).isoformat()
    seuils = set(config["conviction"]["objections_serieuses"])
    index = {(a, s.get("type"), s.get("cle"), s.get("date")): s for a, l in signaux.items() for s in l}
    res: dict[str, list[dict]] = {}
    for r in revues or []:
        s = r.get("signal") or {}
        if (s.get("date") or "") < lim:
            continue
        agent, cle = s.get("agent"), s.get("cle")
        orig = index.get((agent, s.get("type"), cle, s.get("date"))) or {}
        cibles = []
        if agent in ("pays", "risque") and cle and len(str(cle)) == 2:
            cibles.append(f"pays-{cle}")
        elif agent == "entreprises" or agent == "inities":
            cibles.append(f"entreprise-{cle}")
        elif agent == "matieres_premieres":
            cibles.append("or" if cle == "or" else f"matiere-{cle}")
        elif agent == "macro":
            cibles += [f"pays-{c}" for c, z in zones_pays.items() if z == cle]
            if cle == "etats_unis":
                cibles += ["oblig-us-longues", "oblig-us-courtes"]
            if cle == "zone_euro":
                cibles += ["oblig-euro-longues", "oblig-euro-courtes"]
        for c in orig.get("pays") or []:
            cibles.append(f"pays-{c}")
        x = {"objection": re.sub(r"\s*\[F\d+(?:\s*,\s*F\d+)*\]", "", r.get("objection") or "").strip(), "ajustement": r.get("ajustement"), "signal": s.get("titre"), "date": s.get("date"),
             "methode": r.get("methode"), "serieuse": bool(r.get("specifique")) and r.get("ajustement") in seuils}
        for c in dict.fromkeys(cibles):
            res.setdefault(c, []).append(x)
    for v in res.values():
        v.sort(key=lambda x: (not x["serieuse"], x["date"] or ""), reverse=False)
    return res


# ------------------------------------------------------------------ tendance et concentrations

def fleche(score: float | None, precedent: float | None, config: dict) -> str:
    if score is None or precedent is None:
        return "→"
    d = score - precedent
    s = config["tendance"]["seuil_pts"]
    return "↑" if d >= s else "↓" if d <= -s else "→"


def concentrations(opps: list[dict], config: dict) -> list[dict]:
    positifs = [o for o in opps if DIRECTION.get(o.get("verdict")) == 1]
    res = []
    if not positifs:
        return res
    for cle, th in config["themes"]["liste"].items():
        n = [o for o in positifs if cle in (o.get("themes") or [])]
        part = len(n) / len(positifs)
        if part >= config["themes"]["seuil_part"] and len(n) >= 2:
            res.append({"theme": cle, "libelle": th["libelle"], "part": round(part * 100), "nombre": len(n),
                        "texte": f"Thème « {th['libelle']} » : {len(n)} des {len(positifs)} recommandations positives ({round(part * 100)} %) ; risque de concentration.",
                        "lignes": [o["nom"] for o in n][:8]})
    return res


def ligne_publique(o: dict, objections: list[dict], config: dict) -> dict:
    """Ligne affichée dans l'écran « Où investir » (et fiche détaillée)."""
    pour, contre = arguments(o, config)
    garde = ("id", "type", "cle", "nom", "pays", "zone", "secteur", "secteur_nom", "symbole", "cours", "date_cours", "devise", "themes",
             "score", "score_brut", "qualite", "verdict", "verdict_brut", "plafond", "conviction", "fleche", "score_precedent", "depuis", "changement",
             "en_attente", "familles_manquantes", "poids_effectifs", "provenances", "societes", "note_agent", "verdict_agent", "recommandation_agent",
             "rendement_reel", "famille_mp")
    ligne = {k: o[k] for k in garde if k in o and o[k] is not None}
    ligne["familles"] = {f: {"libelle": config["familles"][f]["libelle"], **{k: v for k, v in x.items() if k != "percentile"}} for f, x in o["familles"].items()}
    ligne["pour"], ligne["contre"] = pour, contre
    ligne["objection"] = objections[0] if objections else None
    ligne["objections"] = objections[:3]
    ligne["donner_tort"] = donner_tort(o, contre, pour, objections)
    ligne["derniere_modification"] = (o.get("changement") or {}).get("date") or o.get("depuis")
    ligne["derniere_modification_texte"] = date_fr(ligne["derniere_modification"])
    return ligne
