"""
Santé des agents : bloc « sante » écrit dans data/journal/<agent>.json et lu par l'écran
« Santé des agents » de l'appli.

    meta.sante = {
      "agent": "marches", "libelle": "Agent marchés", "ordre": 2,
      "workflow": "agent-marches.yml",
      "derniere_execution": "2026-11-02T17:34:18Z",    # dernière exécution réussie
      "prochaine_prevue":   "2026-11-02T17:45:00Z",    # d'après la planification du workflow
      "intervalle_min": 15,        # écart entre deux exécutions planifiées (celle à laquelle se
                                   # rattache la dernière exécution et la suivante)
      "sources_total": 8, "sources_ok": 8,
      "sources": [ {"nom", "etat", "derniere_donnee_valide", "detail"} ],
      "degrade": false, "raisons": [],
      "references": { "<indicateur>": ["<source>", …] }   # sources valides attendues par indicateur
    }

États d'une source : « ok », « secours » (la source principale a échoué, une autre a répondu),
« partielle », « échec », « périmée » (elle répond, mais sa donnée est trop ancienne),
« non configurée » (clé absente : ni comptée, ni signalée).

L'appli calcule elle-même le statut à l'ouverture :
« en panne » si la dernière exécution réussie date de plus de 2 × intervalle_min,
« dégradé » si `degrade` est vrai, sinon « OK ».

Règle « dégradé » : un indicateur est dégradé quand il a moins de sources valides que sa
référence, c'est-à-dire les sources valides lors de la dernière exécution saine, limitées à
celles encore configurées. Conséquences :
- une source retirée volontairement de la configuration n'est plus attendue ;
- une source périmée remplacée par une source à jour ne déclenche rien (le nombre est le même) ;
- un indicateur qui passe de deux sources valides à une seule est dégradé, et le reste tant
  que la source perdue n'est pas revenue (ou retirée de la configuration).

data/journal/index.json liste les journaux à lire (l'appli ne peut pas lister un dossier).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .sortie import ecrire_json, lire_json

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_JOURNAL = RACINE / "data" / "journal"
DOSSIER_WORKFLOWS = RACINE / ".github" / "workflows"
ETATS_PROBLEME = {"secours", "partielle", "échec", "périmée"}


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def lire_iso(texte: str | None) -> datetime | None:
    if not texte:
        return None
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError:
        return None


# ------------------------- Planification (cron, en UTC) -------------------------

def _champ(expr: str, mini: int, maxi: int) -> set[int]:
    valeurs = set()
    for morceau in expr.split(","):
        pas = 1
        if "/" in morceau:
            morceau, p = morceau.split("/")
            pas = int(p)
        if morceau == "*":
            debut, fin = mini, maxi
        elif "-" in morceau:
            debut, fin = (int(x) for x in morceau.split("-"))
        else:
            debut = fin = int(morceau)
            if pas > 1:
                fin = maxi
        valeurs.update(range(debut, fin + 1, pas))
    return valeurs


def _correspond(cron: str, t: datetime) -> bool:
    minute, heure, jour, mois, jour_sem = cron.split()
    jours_sem = {0 if j == 7 else j for j in _champ(jour_sem, 0, 7)}
    return (t.minute in _champ(minute, 0, 59) and t.hour in _champ(heure, 0, 23)
            and t.month in _champ(mois, 1, 12) and t.day in _champ(jour, 1, 31)
            and (t.isoweekday() % 7) in jours_sem)


def precedente_execution(crons: list[str], avant: datetime) -> datetime | None:
    """Dernière minute planifiée (UTC) à ou avant `avant`, dans les 8 jours."""
    t = avant.astimezone(timezone.utc).replace(second=0, microsecond=0)
    for _ in range(8 * 24 * 60):
        if any(_correspond(c, t) for c in crons):
            return t
        t -= timedelta(minutes=1)
    return None


def prochaine_execution(crons: list[str], apres: datetime) -> datetime | None:
    """Prochaine minute (UTC) qui correspond à l'une des expressions cron, dans les 8 jours."""
    t = apres.astimezone(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(8 * 24 * 60):
        if any(_correspond(c, t) for c in crons):
            return t
        t += timedelta(minutes=1)
    return None


def crons_du_workflow(fichier: str) -> list[str]:
    """Expressions cron d'un workflow (lignes « - cron: "..." »)."""
    try:
        texte = (DOSSIER_WORKFLOWS / fichier).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return re.findall(r"""^\s*-\s*cron:\s*["']([^"']+)["']""", texte, re.MULTILINE)


# ------------------------- Écriture du bloc « sante » -------------------------

def degradation(indicateurs: dict[str, dict], references: dict[str, list[str]]) -> tuple[list[str], dict]:
    """indicateurs : {nom: {"valides": [sources valides], "configurees": [sources prévues]}}.
    Renvoie (raisons de dégradation, nouvelles références)."""
    raisons, nouvelles = [], {}
    for nom, ind in indicateurs.items():
        valides = sorted(set(ind.get("valides", [])))
        configurees = set(ind.get("configurees", [])) | set(valides)
        attendues = sorted(set(references.get(nom, [])) & configurees)  # sources retirées : plus attendues
        if len(valides) < len(attendues):
            perdues = [s for s in attendues if s not in valides]
            raisons.append(f"{nom} : {len(valides)} source{'s' if len(valides) > 1 else ''} valide"
                           f"{'s' if len(valides) > 1 else ''} au lieu de {len(attendues)} (perdue : {', '.join(perdues)})")
            nouvelles[nom] = attendues
        else:
            nouvelles[nom] = valides
    return raisons, nouvelles


def bloc_sante(agent: str, libelle: str, ordre: int, workflow: str, sources: list[dict],
               maintenant: datetime, precedent: dict | None = None, crons: list[str] | None = None,
               indicateurs: dict[str, dict] | None = None) -> dict:
    """Construit le bloc « sante ». Pour une source en échec, la date de sa dernière donnée
    valide est reprise du bloc précédent quand l'agent ne la connaît pas.
    Avec `indicateurs`, l'état « dégradé » suit la règle des sources attendues (voir en tête) ;
    sans, il est dégradé dès qu'une source est en échec, de secours, partielle ou périmée."""
    anciennes = {s["nom"]: s for s in (precedent or {}).get("sources", [])}
    liste = []
    for s in sources:
        s = {"nom": s["nom"], "etat": s["etat"], "derniere_donnee_valide": s.get("derniere_donnee_valide"),
             "detail": s.get("detail")}
        if s["etat"] in ("ok", "secours", "partielle") and not s["derniere_donnee_valide"]:
            s["derniere_donnee_valide"] = iso(maintenant)
        if s["etat"] == "échec" and not s["derniere_donnee_valide"]:
            s["derniere_donnee_valide"] = anciennes.get(s["nom"], {}).get("derniere_donnee_valide")
        liste.append(s)
    comptees = [s for s in liste if s["etat"] != "non configurée"]
    crons = crons_du_workflow(workflow) if crons is None else crons
    prochaine = prochaine_execution(crons, maintenant) if crons else None
    # Intervalle prévu : de l'exécution planifiée à laquelle se rattache celle-ci (même lancée
    # en retard ou à la main) jusqu'à la suivante. Ex. : quotidien à 6 h → 24 h.
    rattachee = precedente_execution(crons, maintenant) if crons else None
    intervalle = round((prochaine - rattachee).total_seconds() / 60) if prochaine and rattachee else None
    if indicateurs is not None:
        raisons, references = degradation(indicateurs, (precedent or {}).get("references") or {})
    else:
        raisons = [f"{s['nom']} : {s['etat']}" for s in liste if s["etat"] in ETATS_PROBLEME]
        references = None
    bloc = {
        "agent": agent, "libelle": libelle, "ordre": ordre, "workflow": workflow,
        "derniere_execution": iso(maintenant),
        "prochaine_prevue": iso(prochaine) if prochaine else None,
        "intervalle_min": intervalle,
        "sources_total": len(comptees),
        "sources_ok": sum(1 for s in comptees if s["etat"] in ("ok", "secours", "partielle", "périmée")),
        "sources": liste,
        "degrade": bool(raisons),
        "raisons": raisons,
    }
    if references is not None:
        bloc["references"] = references
    return bloc


def _sans_horaires(sante: dict | None) -> dict:
    """Bloc sans ce qui change à chaque exécution (pour savoir si l'état a vraiment changé)."""
    if not sante:
        return {}
    return {**{k: v for k, v in sante.items() if k not in ("derniere_execution", "prochaine_prevue", "intervalle_min")},
            "sources": [{k: v for k, v in s.items() if k != "derniere_donnee_valide"} for s in sante.get("sources", [])]}


def enregistrer_sante(chemin: Path, sante: dict, forcer: bool = False, battement: timedelta = timedelta(0),
                      description: str | None = None) -> bool:
    """Écrit meta.sante dans le journal de l'agent (le reste du journal est conservé) et
    inscrit le journal dans data/journal/index.json.
    On n'écrit (donc on ne commite) que si `forcer`, si l'état des sources a changé, ou si
    la dernière exécution enregistrée date de plus de `battement`."""
    chemin = Path(chemin)
    journal = lire_json(chemin) or {"meta": {}, "donnees": []}
    meta = journal.setdefault("meta", {})
    ancien = meta.get("sante")
    derniere = lire_iso((ancien or {}).get("derniere_execution"))
    maintenant = lire_iso(sante["derniere_execution"])
    a_jour = (ancien and not forcer and _sans_horaires(ancien) == _sans_horaires(sante)
              and derniere and maintenant - derniere < battement)
    if a_jour:
        return False
    meta["sante"] = sante
    meta.setdefault("source", f"agent-{sante['agent']}")
    if description and "description" not in meta:
        meta["description"] = description
    journal.setdefault("donnees", [])
    ecrire_json(chemin, journal)
    inscrire_dans_index(chemin, sante)
    return True


def inscrire_dans_index(chemin: Path, sante: dict) -> None:
    index_chemin = chemin.parent / "index.json"
    index = lire_json(index_chemin) or {"meta": {"description": "Journaux lus par l'écran « Santé des agents »"}, "donnees": []}
    fichier = chemin.name
    entree = {"agent": sante["agent"], "libelle": sante["libelle"], "ordre": sante["ordre"], "fichier": fichier}
    autres = [e for e in index.get("donnees", []) if e.get("fichier") != fichier]
    nouvelles = sorted(autres + [entree], key=lambda e: (e.get("ordre", 99), e["fichier"]))
    if nouvelles != index.get("donnees"):
        index["donnees"] = nouvelles
        ecrire_json(index_chemin, index)
