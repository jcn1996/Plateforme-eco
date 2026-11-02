"""
Vérification croisée des sources (voir sources.md).

Chaque indicateur reçoit une liste de « candidats », un par source :
    {"source": "fmi", "nom": "FMI, World Economic Outlook…", "niveau": "internationale",
     "valeur": 1.2, "date": "2026", "nature": "annuelle", "serie": [...]?}

1. Contrôle de qualité : rejet des valeurs aberrantes (hors bornes physiques)
   et trop anciennes (donnée mensuelle de plus de 6 mois, quotidienne de plus
   de 10 jours, annuelle antérieure à l'an dernier).
2. Choix : source nationale officielle > organisation internationale > marché ;
   à fiabilité égale, la donnée la plus récente l'emporte (puis l'ordre de la
   configuration).
3. Comparaison avec les autres sources comparables (même nature, même période) :
   écart supérieur à la tolérance → « sources divergentes ».
"""
from __future__ import annotations

from datetime import date, timedelta

NIVEAUX = {"nationale": 1, "internationale": 2, "marche": 3}
LIBELLES_NIVEAUX = {"nationale": "source nationale officielle", "internationale": "organisation internationale", "marche": "source de marché"}
# Pour un même niveau, une série mensuelle observée passe avant une estimation annuelle
RANG_NATURE = {"quotidienne": 0, "mensuelle": 0, "annuelle": 1}


def date_periode(periode: str) -> date:
    """'2026-09' → 28/09 ; '2026-09-15' → date ; '2026' → 31/12."""
    morceaux = [int(x) for x in str(periode).split("-")]
    if len(morceaux) == 1:
        return date(morceaux[0], 12, 31)
    if len(morceaux) == 2:
        return date(morceaux[0], morceaux[1], 28)
    return date(*morceaux)


def controler(cand: dict, bornes: list[float] | None, aujourdhui: date) -> str | None:
    """Renvoie la raison du rejet, ou None si la valeur est acceptée."""
    v = cand.get("valeur")
    if v is None:
        return "valeur absente"
    if bornes and not bornes[0] <= v <= bornes[1]:
        return f"valeur aberrante ({v:g}, hors de l'intervalle {bornes[0]:g} à {bornes[1]:g})"
    nature, periode = cand.get("nature"), cand.get("date")
    if nature == "mensuelle" and (aujourdhui - date_periode(periode)).days > 183:
        return f"trop ancienne (donnée mensuelle de {periode}, plus de 6 mois)"
    if nature == "quotidienne" and (aujourdhui - date_periode(periode)).days > 10:
        return f"trop ancienne (cours du {periode}, plus de 10 jours)"
    if nature == "annuelle" and int(str(periode)[:4]) < aujourdhui.year - 1:
        return f"trop ancienne (année {periode})"
    return None


def comparables(a: dict, b: dict) -> bool:
    """Deux valeurs se comparent si elles mesurent la même chose sur la même période."""
    if a.get("nature") != b.get("nature"):
        return False
    if a["nature"] == "annuelle":
        return str(a["date"])[:4] == str(b["date"])[:4]
    ecart = abs((date_periode(a["date"]) - date_periode(b["date"])).days)
    return ecart <= (62 if a["nature"] == "mensuelle" else 7)


def choisir(candidats: list[dict], bornes: list[float] | None, tolerance: float | None, aujourdhui: date) -> dict:
    """
    Choisit la valeur retenue et décrit chaque source.
    Renvoie {"retenu": candidat | None, "sources": [...], "verification": statut, "ecart_max": float | None}
    statut : "concordant" | "divergent" | "source_unique" | "aucune_source"
    """
    valides, rapport = [], []
    for ordre, c in enumerate(candidats):
        if c.get("echec"):
            rapport.append({**_public(c), "statut": "échec", "raison": c["echec"]})
            continue
        raison = controler(c, bornes, aujourdhui)
        if raison:
            rapport.append({**_public(c), "statut": "rejetée", "raison": raison})
        else:
            valides.append((ordre, c))

    if not valides:
        return {"retenu": None, "sources": rapport, "verification": "aucune_source", "ecart_max": None}

    valides.sort(key=lambda oc: (NIVEAUX[oc[1]["niveau"]], RANG_NATURE.get(oc[1].get("nature"), 2),
                                 -date_periode(oc[1]["date"]).toordinal(), oc[0]))
    retenu = valides[0][1]
    ecart_max, nb_comparables, divergent = None, 0, False
    for _, c in valides:
        if c is retenu:
            rapport.append({**_public(c), "statut": "retenue"})
            continue
        if not comparables(retenu, c):
            rapport.append({**_public(c), "statut": "non comparable", "raison": "période ou nature différente"})
            continue
        nb_comparables += 1
        ecart = abs(c["valeur"] - retenu["valeur"])
        ecart_max = ecart if ecart_max is None else max(ecart_max, ecart)
        if tolerance is not None and ecart > tolerance:
            divergent = True
            rapport.append({**_public(c), "statut": "diverge", "ecart": round(ecart, 2)})
        else:
            rapport.append({**_public(c), "statut": "concorde", "ecart": round(ecart, 2)})

    statut = "divergent" if divergent else "concordant" if nb_comparables else "source_unique"
    # Ordre d'affichage : retenue d'abord, puis les autres sources valides, puis rejets et échecs
    ordre_statut = {"retenue": 0, "concorde": 1, "diverge": 1, "non comparable": 2, "rejetée": 3, "échec": 4}
    rapport.sort(key=lambda s: ordre_statut[s["statut"]])
    return {"retenu": retenu, "sources": rapport, "verification": statut,
            "ecart_max": round(ecart_max, 2) if ecart_max is not None else None}


def _public(c: dict) -> dict:
    """Ce qui est publié pour une source (sans la série complète)."""
    v = c.get("valeur")
    return {"source": c["source"], "nom": c["nom"], "niveau": c["niveau"],
            "valeur": round(v, 2) if isinstance(v, (int, float)) else None, "date": c.get("date")}


def derniere_par_mois(serie: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Série quotidienne → dernière valeur de chaque mois ('AAAA-MM')."""
    mois = {}
    for d, v in serie:
        mois[d[:7]] = v
    return sorted(mois.items())


def glissement_annuel(serie: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Indice mensuel → glissement annuel en % ('AAAA-MM')."""
    valeurs = dict(serie)
    resultat = []
    for periode, v in serie:
        a, m = int(periode[:4]), periode[5:7]
        avant = valeurs.get(f"{a - 1}-{m}")
        if avant:
            resultat.append((periode, (v / avant - 1) * 100))
    return resultat


def il_y_a(jours: int, depuis: str) -> date:
    return date_periode(depuis) - timedelta(days=jours)
