"""
Contrôle de la gravité (config « controle_gravite »).

1. Niveau des règles, à partir des repères :
   - base selon le type d'événement (catégorie) ;
   - 3 si un marqueur de « mesure importante ou tension notable » est présent (frappes, morts,
     sanctions visant un pays, droits de douane sur un pays…) ;
   - 4 si un marqueur de « conflit armé, sanctions majeures, rupture commerciale » est présent ET
     qu'il y a un effet direct sur un marché (pétrole, gaz, détroit d'Ormuz, semi-conducteurs…,
     dans les sources ou le résumé, ou actif touché de cette liste) ;
   - un cran de moins si aucun pays principal n'est un pays suivi et qu'il n'y a pas d'effet direct
     sur un marché.
2. Gravité retenue : celle de Gemini, sans dépasser le niveau des règles + 1 (relevement_max) ;
   sans IA, le niveau des règles, 3 au plus. Plafond « élection » ensuite (ia.plafonner).
3. Distribution cible sur 24 h : au-delà de part_max_4 d'événements en 4 (au moins min_4 permis),
   les moins étayés repassent en 3 ; de même pour la gravité 3 (part_max_3, ramenés à 2).
"""
from __future__ import annotations

import math
import re

from . import evenements as E


def _contient(texte: str, mots: list[str]) -> list[str]:
    return [m for m in mots if re.search(rf"(?<![\w]){re.escape(m)}(?![\w])", texte)]


def textes(e: dict) -> str:
    """Cœur de l'événement : titre de référence, titre français et résumé de Gemini (pas tous les
    articles, qui évoquent souvent d'autres faits)."""
    a = e.get("analyse") or {}
    morceaux = [E.titre_reference(e), a.get("titre") or ""] + [r["texte"] for r in a.get("resume", [])]
    return E.normaliser(" ".join(morceaux)).replace("’", "'")


def niveau_regles(e: dict, config: dict, pays: list[str] | None = None) -> tuple[int, list[str]]:
    """(niveau des règles, justification)."""
    c = config["controle_gravite"]
    a = e.get("analyse") or {}
    categorie = a.get("categorie") or e["categorie"]
    t = textes(e)
    niveau, raisons = c["base"].get(categorie, 1), [f"base {categorie} : {c['base'].get(categorie, 1)}"]
    m3 = _contient(t, c["niveau_3"].get(categorie, []))
    if m3 and niveau < 3:
        niveau, raisons = 3, raisons + [f"tension notable ({', '.join(m3[:3])})"]
    effet = _contient(t, c["effet_marche"]) + [x["actif"] for x in a.get("actifs", []) if x.get("actif") in c["actifs_marche"]]
    m4 = _contient(t, c["niveau_4"].get(categorie, []))
    if m4 and effet:
        niveau, raisons = 4, raisons + [f"repère 4 ({', '.join(m4[:2])}) avec effet direct sur un marché ({', '.join(dict.fromkeys(effet[:3]))})"]
    pays = pays if pays is not None else (e.get("pays_principaux") or e.get("pays") or [])
    if not any(p in config["pays"] for p in pays) and not effet and niveau > 1:
        niveau += c["sans_pays_suivi"]
        raisons.append("aucun pays suivi directement concerné")
    return max(1, min(5, niveau)), raisons


def gravite_finale(e: dict, config: dict, pays: list[str] | None = None) -> tuple[int, int, str | None]:
    """(gravité retenue, niveau des règles, note). La valeur de Gemini ne relève le niveau des règles
    que d'un cran au plus ; elle peut l'abaisser."""
    regle, raisons = niveau_regles(e, config, pays)
    a = e.get("analyse") or {}
    proposee = a.get("gravite")  # proposée par Gemini, après le contrôle des sources indépendantes
    if proposee is None:
        return min(regle, 3), regle, None
    maxi = regle + config["controle_gravite"]["relevement_max"]
    if proposee > maxi:
        return maxi, regle, f"gravité {proposee} proposée par Gemini, ramenée à {maxi} (repères : {'; '.join(raisons)})"
    return proposee, regle, None


def calibrer(publics: list[dict], config: dict, limite_iso: str) -> list[str]:
    """Distribution cible sur les événements publiés des dernières 24 h. Modifie `gravite` et
    `note_gravite` ; renvoie la liste des ajustements."""
    d = config["controle_gravite"]["distribution"]
    recents = [x for x in publics if x["dernier"] >= limite_iso]
    ajustements = []
    for niveau, part, mini, vers in ((4, d["part_max_4"], d["min_4"], 3), (3, d["part_max_3"], d["min_3"], 2)):
        concernes = [x for x in recents if x["gravite"] == niveau]
        permis = max(mini, math.floor(part * len(recents)))
        if len(concernes) <= permis:
            continue
        # Les plus étayés gardent leur gravité : niveau des règles, sources indépendantes, nombre d'articles
        concernes.sort(key=lambda x: (x.get("gravite_regles") or 0, x.get("nb_domaines") or 0, x.get("nb_articles") or 0), reverse=True)
        for x in concernes[permis:]:
            x["gravite"] = vers
            note = f"ramené à {vers} : distribution cible (au plus {permis} événement{'s' if permis > 1 else ''} en {niveau} sur 24 h)"
            x["note_gravite"] = f"{x['note_gravite']} ; {note}" if x.get("note_gravite") else note
            ajustements.append(f"{x['id']} : {niveau} → {vers}")
    return ajustements
