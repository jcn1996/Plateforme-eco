"""
Score de risque géopolitique /100 par pays suivi (plus il est haut, plus le risque est élevé).

score = Σ poids × composante, sur les composantes disponibles (poids repondérés) :
- événements (0,5) : 100 × (1 − exp(−S / échelle)), S = Σ gravité² × 0,5^(âge / demi-vie)
  sur les événements des `fenetre_jours` derniers jours qui concernent le pays ;
- tonalité (0,3) : fichiers d'événements GDELT des 48 dernières heures, lieu de l'action dans le
  pays. Moitié tonalité moyenne pondérée par le nombre d'articles (−1 → 0, −8 ou moins → 100),
  moitié part des événements de conflit (QuadClass 3 et 4 : 10 % → 0, 50 % ou plus → 100) ;
- tendance (0,2) : événements de conflit par fichier, 7 derniers jours rapportés aux 30 derniers
  (rapport 1 → 50, 2 → 100, 0 → 0) ; au moins 10 jours de données.
Variation sur 7 jours : écart avec le score enregistré 7 jours plus tôt (ou le plus proche avant).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta


def _borne(x: float) -> float:
    return max(0.0, min(100.0, x))


def composante_evenements(code: str, evenements: list[dict], maintenant: datetime, cfg: dict) -> tuple[float, int]:
    s, n = 0.0, 0
    limite = maintenant - timedelta(days=cfg["fenetre_jours"])
    for e in evenements:
        pays = e.get("pays_principaux") or []
        if code not in pays:
            continue
        dernier = datetime.fromisoformat(e["dernier"].replace("Z", "+00:00"))
        if dernier < limite:
            continue
        age = max(0.0, (maintenant - dernier).total_seconds() / 86400)
        s += e["gravite"] ** 2 * 0.5 ** (age / cfg["demi_vie_jours"])
        n += 1
    return round(100 * (1 - math.exp(-s / cfg["echelle_evenements"])), 1), n


def composante_tonalite(jours: dict, fips: str, aujourdhui: date) -> tuple[float | None, float | None]:
    """jours : {AAAA-MM-JJ: {fips: agrégat}}. Renvoie (composante, tonalité moyenne)."""
    agg = {"evenements": 0, "articles": 0, "ton_pondere": 0.0, "conflits": 0}
    for j in (aujourdhui.isoformat(), (aujourdhui - timedelta(days=1)).isoformat()):
        a = (jours.get(j) or {}).get(fips)
        if a:
            for k in agg:
                agg[k] += a.get(k, 0)
    if agg["articles"] < 20 or agg["evenements"] < 10:
        return None, None
    ton = agg["ton_pondere"] / agg["articles"]
    part = agg["conflits"] / agg["evenements"]
    c = 0.5 * _borne((-ton - 1) / 7 * 100) + 0.5 * _borne((part - 0.1) / 0.4 * 100)
    return round(c, 1), round(ton, 2)


def composante_tendance(jours: dict, fichiers: dict, fips: str, aujourdhui: date) -> float | None:
    """fichiers : {AAAA-MM-JJ: nombre de fichiers GDELT lus ce jour-là}."""
    def par_fichier(depuis: int) -> list[float]:
        res = []
        for k in range(depuis):
            j = (aujourdhui - timedelta(days=k)).isoformat()
            if fichiers.get(j):
                res.append(((jours.get(j) or {}).get(fips) or {}).get("conflits", 0) / fichiers[j])
        return res
    trente = par_fichier(30)
    if len(trente) < 10:
        return None
    sept = par_fichier(7)
    moyenne30 = sum(trente) / len(trente)
    if not sept or moyenne30 <= 0:
        return None
    r = (sum(sept) / len(sept)) / moyenne30
    return round(_borne(50 + 50 * (r - 1)), 1)


def variation_7j(historique: list[list], score: float, aujourdhui: date) -> float | None:
    cible = (aujourdhui - timedelta(days=7)).isoformat()
    anciens = [s for d, s in historique if d <= cible]
    return round(score - anciens[-1], 1) if anciens else None


def niveau(score: float, cfg: dict) -> str:
    return "élevé" if score >= cfg["seuil_eleve"] else "modéré" if score >= cfg["seuil_modere"] else "faible"


def scores(config: dict, evenements: list[dict], etat: dict, maintenant: datetime) -> dict:
    cfg = config["score"]
    aujourdhui = maintenant.date()
    jours, fichiers = etat.get("gdelt_jours", {}), etat.get("gdelt_fichiers_par_jour", {})
    res = {}
    for code, p in config["pays"].items():
        ev, n = composante_evenements(code, evenements, maintenant, cfg)
        ton_c, ton = composante_tonalite(jours, p["fips"], aujourdhui)
        tend = composante_tendance(jours, fichiers, p["fips"], aujourdhui)
        comp = {"evenements": ev, "tonalite": ton_c, "tendance": tend}
        dispo = {k: v for k, v in comp.items() if v is not None}
        poids = sum(cfg["poids"][k] for k in dispo)
        score = round(sum(cfg["poids"][k] * v for k, v in dispo.items()) / poids) if poids else None
        hist = etat.get("scores", {}).get(code, [])
        res[code] = {
            "score": score, "niveau": niveau(score, cfg) if score is not None else None,
            "variation_7j": variation_7j(hist, score, aujourdhui) if score is not None else None,
            "composantes": comp, "tonalite_gdelt": ton, "evenements_14j": n,
            "composantes_manquantes": [k for k, v in comp.items() if v is None],
        }
    return res


def enregistrer_historique(etat: dict, res: dict, aujourdhui: date, garde_jours: int = 400) -> None:
    """Un score par jour et par pays (le dernier calculé dans la journée)."""
    hist = etat.setdefault("scores", {})
    limite = (aujourdhui - timedelta(days=garde_jours)).isoformat()
    for code, r in res.items():
        if r["score"] is None:
            continue
        serie = [x for x in hist.get(code, []) if x[0] != aujourdhui.isoformat() and x[0] >= limite]
        hist[code] = sorted(serie + [[aujourdhui.isoformat(), r["score"]]])
