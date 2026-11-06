"""Calculs sur séries [(date ISO, valeur)] : valeur à une date, percentile, variations,
volatilité, corrélations, compactage pour l'état de l'agent."""
from __future__ import annotations

import bisect
import math
from datetime import date, timedelta


def jour(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def valeur_a(serie, d, age_max_jours: int | None = None):
    """Dernier point (date, valeur) à ou avant d ; None si absent ou trop ancien."""
    if not serie:
        return None
    cible = jour(d).isoformat()
    dates = [p[0] for p in serie]
    i = bisect.bisect_right(dates, cible) - 1
    if i < 0:
        return None
    p = serie[i]
    if age_max_jours is not None and (jour(cible) - jour(p[0])).days > age_max_jours:
        return None
    return p


def percentile(tries: list[float], x: float) -> float:
    """Rang centile de x dans une distribution triée (0-100, égalités comptées à moitié)."""
    n = len(tries)
    if not n:
        return 50.0
    bas = bisect.bisect_left(tries, x)
    haut = bisect.bisect_right(tries, x)
    return round(100 * (bas + 0.5 * (haut - bas)) / n, 1)


def depuis(serie, d):
    cible = jour(d).isoformat()
    return [p for p in serie if p[0] >= cible]


def variation_pct(serie, decalage: int):
    """Variation en % entre le dernier point et celui `decalage` séances plus tôt."""
    if len(serie) <= decalage:
        return None
    a, b = serie[-1 - decalage][1], serie[-1][1]
    return None if not a else round(100 * (b / a - 1), 2)


def serie_variation(serie, decalage: int):
    """Série des variations en % sur `decalage` séances."""
    return [(serie[i][0], round(100 * (serie[i][1] / serie[i - decalage][1] - 1), 3))
            for i in range(decalage, len(serie)) if serie[i - decalage][1]]


def rendements(serie):
    return [(serie[i][0], math.log(serie[i][1] / serie[i - 1][1])) for i in range(1, len(serie))
            if serie[i - 1][1] > 0 and serie[i][1] > 0]


def volatilite(serie, jours: int):
    """Volatilité annualisée (%) des rendements quotidiens sur les `jours` dernières séances."""
    r = [x[1] for x in rendements(serie)[-jours:]]
    if len(r) < max(10, jours // 2):
        return None
    m = sum(r) / len(r)
    v = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return round(100 * math.sqrt(v * 252), 2)


def baisse_plus_haut(serie, jours: int = 252):
    """Écart (%) entre le dernier cours et le plus haut des `jours` dernières séances (≤ 0)."""
    x = serie[-jours:]
    if len(x) < 20:
        return None
    haut = max(p[1] for p in x)
    return round(100 * (x[-1][1] / haut - 1), 2)


def correlation(a, b, jours: int):
    """Corrélation des rendements quotidiens de deux séries, sur les dates communes les plus récentes."""
    ra, rb = dict(rendements(a)), dict(rendements(b))
    communs = sorted(set(ra) & set(rb))[-jours:]
    if len(communs) < max(15, jours // 2):
        return None
    xa, xb = [ra[d] for d in communs], [rb[d] for d in communs]
    ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(xa, xb))
    va = math.sqrt(sum((x - ma) ** 2 for x in xa))
    vb = math.sqrt(sum((y - mb) ** 2 for y in xb))
    return None if not va or not vb else round(cov / (va * vb), 2)


def ecart_series(a, b, age_max_jours: int = 40):
    """a − b aux dates de a (b pris à la date la plus proche avant)."""
    res = []
    for d, v in a:
        p = valeur_a(b, d, age_max_jours)
        if p is not None:
            res.append((d, round(v - p[1], 4)))
    return res


def compacter(serie, aujourdhui, jours_quotidiens: int = 400):
    """Garde les points quotidiens récents et un point par semaine avant (état de l'agent)."""
    limite = (jour(aujourdhui) - timedelta(days=jours_quotidiens)).isoformat()
    anciens, vus = [], set()
    for d, v in serie:
        if d >= limite:
            break
        semaine = jour(d).isocalendar()[:2]
        if semaine in vus:
            anciens[-1] = [d, v]
        else:
            vus.add(semaine)
            anciens.append([d, v])
    return anciens + [[d, v] for d, v in serie if d >= limite]


def borne(x, bas, haut):
    """x ramené sur 0-100 entre bas (0) et haut (100), bornes dans un sens ou dans l'autre."""
    if x is None:
        return None
    t = (x - bas) / (haut - bas)
    return round(100 * min(1.0, max(0.0, t)), 1)


def fr(x, decimales: int = 1, signe: bool = False) -> str:
    """Nombre à la française : 1 234,5 ; −2,3 ; +1,0."""
    if x is None:
        return "n. d."
    texte = f"{abs(x):,.{decimales}f}".replace(",", " ").replace(".", ",")
    if x < 0 and float(texte.replace(" ", "").replace(",", ".")) != 0:
        return "−" + texte
    return ("+" if signe else "") + texte


def date_fr(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso and len(iso) >= 10 else (iso or "")
