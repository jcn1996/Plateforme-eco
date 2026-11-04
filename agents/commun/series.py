"""Séries de cours compactes pour les graphiques de secours de l'appli (Lightweight Charts).

Quand le widget gratuit de TradingView ne peut pas afficher un symbole (ou en mode ⚡), l'appli
trace un graphique simple à partir de ces séries, déjà récupérées par les agents :
[[date ISO, clôture], …] sur environ un an.
"""
from __future__ import annotations

from datetime import date, timedelta


def _jour(d) -> date:
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def serie_graphique(points, jours: int = 372, hebdo: bool = False, decimales: int = 4) -> list[list]:
    """Points [(date, clôture, …)] → [[\"AAAA-MM-JJ\", clôture]] sur les `jours` derniers jours.
    hebdo=True ne garde que la dernière clôture de chaque semaine (fiches des entreprises : ~53 points)."""
    propres = []
    for p in points or []:
        try:
            c = float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if c != c or c <= 0:  # NaN ou valeur aberrante
            continue
        propres.append((_jour(p[0]), c))
    if not propres:
        return []
    propres.sort()
    debut = propres[-1][0] - timedelta(days=jours)
    propres = [p for p in propres if p[0] >= debut]
    if hebdo:
        par_semaine = {}
        for d, c in propres:
            par_semaine[d.isocalendar()[:2]] = (d, c)  # la dernière séance de la semaine l'emporte
        propres = sorted(par_semaine.values())
    return [[d.isoformat(), round(c, decimales)] for d, c in propres]
