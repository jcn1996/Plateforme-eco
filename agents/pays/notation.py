"""
Notation des pays (/100). Les règles sont décrites en détail dans regles.md.

Principes :
- chaque indicateur reçoit une note /100 par une règle explicite (seuils et sens) ;
- la note globale est la moyenne pondérée des indicateurs disponibles
  (pondérations dans config.json) ; un indicateur manquant est exclu ;
- pas de conclusion forte sans au moins deux indicateurs concordants ;
- le niveau de confiance dépend de la couverture, de la fraîcheur et de la
  concordance des données.
"""
from __future__ import annotations

from statistics import pstdev



def minuscule(libelle: str) -> str:
    """« Croissance du PIB » → « croissance du PIB » (sigles conservés)."""
    return libelle[:1].lower() + libelle[1:]

def borner(x: float, mini: float = 0, maxi: float = 100) -> int:
    return int(round(max(mini, min(maxi, x))))


def note_croissance(pib: float) -> int:
    """Croissance du PIB réel (% sur un an). 0 % → 35 ; 2 % → 51 ; 4 % → 67 ; 6 % → 83."""
    return borner(35 + 8 * pib)


def note_indicateur_avance(cli: float, cli_3_mois: float | None) -> int:
    """CLI de l'OCDE (base 100). Le niveau compte (au-dessus de 100 = accélération),
    la pente sur 3 mois aussi. 100 et stable → 50 ; 101 et +0,3 → 64,5."""
    pente = (cli - cli_3_mois) if cli_3_mois is not None else 0
    return borner(50 + 10 * (cli - 100) + 15 * pente)


def note_inflation(inflation: float, cible: float | None) -> int:
    """Inflation : proche de la cible = bon. Chaque point d'écart (au-dessus ou en
    dessous, déflation comprise) coûte 15 points. Au-delà de 15 % : 10 au plus."""
    c = 2.0 if cible is None else cible
    note = 90 - 15 * abs(inflation - c)
    if inflation > 15:
        note = min(note, 10)
    return borner(note)


def note_taux_reel(reel: float, direction: str | None) -> int:
    """Taux réel = taux directeur − inflation. Zone saine : de +0,5 à +2,5 pts (80).
    Très négatif = inflation mal tenue (risque) : −12 points par point sous +0,5.
    Très positif = politique très restrictive : −7 points par point au-dessus de +2,5.
    Banque centrale qui baisse ses taux : +4 ; qui monte : −4."""
    if reel < 0.5:
        note = 80 - 12 * (0.5 - reel)
    elif reel > 2.5:
        note = 80 - 7 * (reel - 2.5)
    else:
        note = 80
    note += {"baisse": 4, "hausse": -4}.get(direction or "stable", 0)
    return borner(note)


def note_valorisation(ecart_pct: float) -> int:
    """PER de l'ETF comparé à la médiane des pays suivis (%). Moins cher = mieux :
    à la médiane → 60 ; 20 % plus cher → 40 ; 20 % moins cher → 80."""
    return borner(60 - ecart_pct)


def note_momentum(perf_12m: float) -> int:
    """Performance de l'ETF pays sur 12 mois (en dollars). 0 % → 50 ; +20 % → 74 ; −20 % → 26."""
    return borner(50 + 1.2 * perf_12m)


def note_devise(variation_3m: float) -> int:
    """Variation de la devise contre le dollar sur 3 mois (positif = appréciation)."""
    return borner(55 + 4 * variation_3m)


def note_solde_courant(solde_pct_pib: float) -> int:
    """Solde courant (% du PIB) : un excédent protège des chocs financiers."""
    return borner(55 + 4 * solde_pct_pib)


# ---------------------------------------------------------------------------
# Note globale et confiance
# ---------------------------------------------------------------------------

def niveau(note: float) -> str:
    return "attractif" if note >= 65 else "neutre" if note >= 50 else "defavorable"


def note_globale(indicateurs: dict, ponderations: dict) -> dict:
    """
    Moyenne pondérée des indicateurs disponibles.
    Règle de prudence : une note « attractive » (≥ 65) exige au moins deux
    indicateurs attractifs ; une note « défavorable » (< 50) exige au moins
    deux indicateurs défavorables (les valeurs « à vérifier » ne comptent pas).
    Sinon la note est ramenée dans la zone neutre (64 ou 50).
    """
    presents = {k: v for k, v in indicateurs.items() if k in ponderations and v.get("note") is not None}
    poids_total = sum(ponderations.values())
    poids_presents = sum(ponderations[k] for k in presents)
    if not presents:
        return {"note": None, "couverture": 0.0, "brute": None, "ramenee": False}
    brute = sum(ponderations[k] * v["note"] for k, v in presents.items()) / poids_presents
    note = brute
    # Une valeur « à vérifier » (isolée et inhabituelle) ne suffit pas à confirmer une conclusion
    fiables = [v for v in presents.values() if not v.get("a_verifier")]
    nb_attractifs = sum(1 for v in fiables if v["note"] >= 65)
    nb_defavorables = sum(1 for v in fiables if v["note"] < 50)
    ramenee = False
    if note >= 65 and nb_attractifs < 2:
        note, ramenee = 64, True
    elif note < 50 and nb_defavorables < 2:
        note, ramenee = 50, True
    return {"note": borner(note), "brute": round(brute, 1), "couverture": round(poids_presents / poids_total, 2), "ramenee": ramenee}


def confiance(indicateurs: dict, ponderations: dict, couverture: float) -> dict:
    """
    Niveau de confiance (faible / moyen / élevé) :
    - couverture : part des pondérations dont l'indicateur est disponible ;
    - fraîcheur : chaque valeur « ancienne » (source en panne) retire 0,1 ;
    - concordance : si les notes des indicateurs divergent fortement
      (écart-type > 22), on retire 0,15 ; chaque valeur « à vérifier » retire 0,1 ;
    - vérification croisée : chaque indicateur aux sources divergentes retire 0,1 ;
      si plus de la moitié des indicateurs disponibles reposent sur une seule source,
      le niveau est plafonné à « moyen ».
    Score ≥ 0,8 → élevé ; ≥ 0,55 → moyen ; sinon faible.
    """
    principaux = {k: v for k, v in indicateurs.items() if k in ponderations}
    notes = [v["note"] for v in principaux.values() if v.get("note") is not None]
    score = couverture
    raisons = []
    if couverture < 1:
        manquants = [v["libelle"] for v in principaux.values() if v.get("note") is None]
        raisons.append("données manquantes : " + ", ".join(map(minuscule, manquants)))
    anciennes = [v["libelle"] for v in principaux.values() if v.get("ancienne")]
    if anciennes:
        score -= 0.1 * len(anciennes)
        raisons.append("valeurs anciennes (source indisponible) : " + ", ".join(map(minuscule, anciennes)))
    a_verifier = [v["libelle"] for v in principaux.values() if v.get("a_verifier")]
    if a_verifier:
        score -= 0.1 * len(a_verifier)
        raisons.append("valeurs à vérifier : " + ", ".join(map(minuscule, a_verifier)))
    divergents = [v for v in principaux.values() if v.get("verification") == "divergent"]
    if divergents:
        score -= 0.1 * len(divergents)
        raisons.append("sources divergentes : " + ", ".join(
            minuscule(v["libelle"]) + (f" (écart de {v['ecart_max']:.2f} pt)".replace(".", ",") if v.get("ecart_max") is not None else "")
            for v in divergents))
    if len(notes) >= 3 and pstdev(notes) > 22:
        score -= 0.15
        raisons.append("indicateurs peu concordants")
    # Plafond : si la majorité des indicateurs disponibles ne repose que sur une seule source
    disponibles = [v for v in principaux.values() if v.get("note") is not None]
    uniques = [v["libelle"] for v in disponibles if v.get("verification") == "source_unique"]
    plafond = bool(disponibles) and len(uniques) * 2 > len(disponibles)
    if plafond and score >= 0.8:
        raisons.append("confiance plafonnée à « moyen » : une seule source pour " + ", ".join(map(minuscule, uniques)))
    if not raisons:
        raisons.append("données complètes, récentes et confirmées par plusieurs sources")
    score = max(0.0, round(score, 2))
    niveau = "élevé" if score >= 0.8 else "moyen" if score >= 0.55 else "faible"
    if plafond and niveau == "élevé":
        niveau = "moyen"
    return {"niveau": niveau, "score": score, "raisons": raisons, "plafonnee": plafond and score >= 0.8}
