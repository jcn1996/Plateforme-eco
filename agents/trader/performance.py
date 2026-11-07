"""
Suivi de performance de l'agent trader (démo) : valeur quotidienne, performance depuis le départ, sur 1 et 3 mois,
comparaison au MSCI World en euros (ETF URTH converti au cours EUR/USD du jour), ratio de Sharpe, volatilité, perte
maximale, taux de réussite des ventes, gain et perte moyens, attribution (cœur, satellites, classes, familles de
signaux du chef d'orchestre).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from . import portefeuille as P

LIBELLES_FAMILLES = {"fondamentaux": "Fondamentaux", "valorisation": "Valorisation", "tendance": "Tendance et momentum", "flux": "Flux d'investissement",
                     "cycle": "Adéquation au cycle", "risque": "Risque", "geopolitique": "Géopolitique", "inities": "Initiés et super-investisseurs",
                     "resultats": "Dynamique des résultats", "autres": "Sans famille dominante"}


def _r(x, n=2):
    return None if x is None else round(x, n)


def serie(historique: dict, cle: str) -> list[tuple[str, float]]:
    return [(d, h[cle]) for d, h in sorted(historique.items()) if h.get(cle) is not None]


def perf_periode(points: list[tuple[str, float]], jours: int | None) -> float | None:
    """Performance (%) sur la période ; None si l'historique ne couvre pas la période."""
    if len(points) < 2:
        return None
    fin_d, fin_v = points[-1]
    if jours is None:
        return (fin_v / points[0][1] - 1) * 100
    limite = (date.fromisoformat(fin_d) - timedelta(days=jours)).isoformat()
    avant = [p for p in points if p[0] <= limite]
    if not avant:
        return None
    return (fin_v / avant[-1][1] - 1) * 100


def risque(points: list[tuple[str, float]], config: dict) -> dict:
    cp = config["performance"]
    v = [p[1] for p in points]
    perte_max, haut = 0.0, None
    for x in v:
        haut = x if haut is None else max(haut, x)
        perte_max = min(perte_max, (x / haut - 1) * 100)
    r = [b / a - 1 for a, b in zip(v, v[1:]) if a > 0]
    if len(r) + 1 < cp["points_min_statistiques"]:
        return {"volatilite": None, "sharpe": None, "perte_max": _r(perte_max), "points": len(v),
                "raison": f"historique trop court ({len(v)} jour(s), {cp['points_min_statistiques']} requis)"}
    m = sum(r) / len(r)
    ec = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
    vol = ec * math.sqrt(cp["jours_par_an"]) * 100
    rf = cp["taux_sans_risque_pct"] / 100 / cp["jours_par_an"]
    sharpe = (m - rf) / ec * math.sqrt(cp["jours_par_an"]) if ec > 0 else None
    return {"volatilite": _r(vol), "sharpe": _r(sharpe), "perte_max": _r(perte_max), "points": len(v), "raison": None}


def stats_operations(operations: list[dict]) -> dict:
    ventes = [o for o in operations if o["sens"] == "vente" and (o.get("resultat") or {}).get("plus_value_eur") is not None]
    gains = [o["resultat"]["plus_value_pct"] for o in ventes if o["resultat"]["plus_value_eur"] > 0 and o["resultat"].get("plus_value_pct") is not None]
    pertes = [o["resultat"]["plus_value_pct"] for o in ventes if o["resultat"]["plus_value_eur"] <= 0 and o["resultat"].get("plus_value_pct") is not None]
    n = len(gains) + len(pertes)
    return {"cloturees": len(ventes), "gagnantes": len(gains), "perdantes": len(pertes),
            "taux_reussite": _r(len(gains) / n * 100, 1) if n else None,
            "gain_moyen_pct": _r(sum(gains) / len(gains)) if gains else None, "perte_moyenne_pct": _r(sum(pertes) / len(pertes)) if pertes else None,
            "achats": sum(1 for o in operations if o["sens"] == "achat"), "ventes": sum(1 for o in operations if o["sens"] == "vente"),
            "definition": "Opération clôturée : chaque vente (totale ou partielle), comparée au prix de revient frais compris."}


def attribution(etat: dict, capital: float) -> dict:
    """Plus-values réalisées + latentes, en euros et en points de performance (% du capital initial)."""
    cumul = {k: dict(v) for k, v in (etat.get("attribution") or {}).items()}
    for p in etat["positions"].values():
        latente = p.get("valeur_eur", 0) - p["cout_total_eur"]
        P.attribuer(cumul, p, latente)

    def bloc(d, libelles=None):
        return sorted([{"cle": k, "libelle": (libelles or {}).get(k, k), "eur": round(v, 2), "points": round(v / capital * 100, 3)}
                       for k, v in (d or {}).items()], key=lambda x: -abs(x["eur"]))
    return {"poches": bloc(cumul.get("poches"), {"coeur": "Cœur", "satellite": "Satellites"}),
            "classes": bloc(cumul.get("classes"), {"actions": "Actions", "obligations": "Obligations", "or": "Or", "matieres": "Matières premières"}),
            "familles": bloc(cumul.get("familles"), LIBELLES_FAMILLES),
            "frais_eur": round(etat.get("frais_total", 0), 2), "ecarts_eur": round(etat.get("ecarts_total", 0), 2),
            "methode": "Plus-values réalisées et latentes de chaque ligne (frais compris), réparties entre les familles de signaux favorables "
                       "du chef d'orchestre au moment de l'achat, au prorata de (note − 50). Approximation destinée à l'agent calibrateur."}


def statistiques(etat: dict, operations: list[dict], config: dict) -> dict:
    h = etat.get("historique") or {}
    pf, ind = serie(h, "portefeuille"), serie(h, "msci_world")
    capital = etat["capital_initial"]

    def perfs(points, depart):
        tot = (points[-1][1] / depart - 1) * 100 if points else None
        return {"depuis_debut": _r(tot), "un_mois": _r(perf_periode(points, 30)), "trois_mois": _r(perf_periode(points, 91))}
    ref = (etat.get("reference_indice") or {})
    return {"performance": perfs(pf, capital), "performance_msci_world": perfs(ind, capital) if ref else {"depuis_debut": None, "un_mois": None, "trois_mois": None},
            "risque": risque(pf, config), "risque_msci_world": risque(ind, config) if ind else None,
            "operations": stats_operations(operations), "attribution": attribution(etat, capital)}
