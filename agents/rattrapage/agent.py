"""
Rattrapage des exécutions planifiées manquées.

GitHub retarde, voire saute, les tâches planifiées (surtout aux minutes rondes). Toutes les
heures, ce module lit data/journal/*.json et, pour chaque agent :
1. prend son planning (lignes « cron » de son workflow ; à défaut, le planning déclaré dans
   son journal) et sa dernière exécution réussie ;
2. calcule la première exécution prévue après celle-ci ;
3. si elle manque depuis plus d'une heure, relance le workflow (gh workflow run, déclencheur
   workflow_dispatch), sauf :
   - si l'agent a déjà été relancé dans l'heure (au plus une relance par agent et par heure) ;
   - si une exécution du workflow est déjà en cours ou en attente.
Chaque décision de relance est tracée dans data/journal/rattrapage.json (200 dernières).
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.commun import sante
from agents.commun.journal import journal
from agents.commun.sortie import ecrire_json, lire_json

LOG = journal("rattrapage")
DOSSIER = sante.DOSSIER_JOURNAL
FICHIER = DOSSIER / "rattrapage.json"
IGNORES = {"index.json", "rattrapage.json"}
DELAI = timedelta(hours=1)          # retard au-delà duquel on relance
UNE_RELANCE_PAR = timedelta(hours=1)
MAXIMUM = 200


def lire_agents(dossier: Path = DOSSIER) -> list[dict]:
    """Agents connus : {agent, workflow, derniere_execution, crons}."""
    agents = []
    for chemin in sorted(Path(dossier).glob("*.json")):
        if chemin.name in IGNORES:
            continue
        j = lire_json(chemin) or {}
        s = (j.get("meta") or {}).get("sante")
        if not s or not s.get("workflow"):
            continue
        crons = sante.crons_du_workflow(s["workflow"]) or ((j.get("planning") or s.get("planning") or {}).get("crons") or [])
        agents.append({"agent": s.get("agent", chemin.stem), "workflow": s["workflow"],
                       "derniere_execution": j.get("derniere_execution") or s.get("derniere_execution"),
                       "crons": crons})
    return agents


def a_relancer(agent: dict, maintenant: datetime, relances: list[dict]) -> tuple[bool, str, datetime | None]:
    """(relancer ?, raison, exécution prévue manquante)."""
    if not agent["crons"]:
        return False, "aucun planning connu", None
    derniere = sante.lire_iso(agent.get("derniere_execution"))
    if derniere is None or maintenant - derniere > timedelta(days=7):
        manquante = sante.precedente_execution(agent["crons"], maintenant)
    else:
        manquante = sante.prochaine_execution(agent["crons"], derniere)
    if manquante is None or maintenant - manquante <= DELAI:
        return False, "à jour", manquante
    for r in relances:
        if r.get("agent") == agent["agent"] and r.get("statut") == "relancé":
            t = sante.lire_iso(r.get("relance_le"))
            if t and maintenant - t < UNE_RELANCE_PAR:
                return False, "déjà relancé dans l'heure", manquante
    return True, f"exécution prévue {sante.iso(manquante)} manquante depuis {int((maintenant - manquante).total_seconds() // 60)} min", manquante


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)


def execution_en_cours(workflow: str) -> bool:
    r = gh("run", "list", "--workflow", workflow, "--limit", "10", "--json", "status")
    if r.returncode != 0:
        LOG.warning("gh run list %s : %s", workflow, r.stderr.strip())
        return False
    return any(x.get("status") != "completed" for x in json.loads(r.stdout or "[]"))


def lancer(workflow: str) -> tuple[bool, str]:
    r = gh("workflow", "run", workflow, "--ref", os.environ.get("BRANCHE", "main"))
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def rattraper(maintenant: datetime, dossier: Path = DOSSIER, en_cours=execution_en_cours, lanceur=lancer) -> list[dict]:
    """Relance les agents en retard ; renvoie les nouvelles entrées du journal de rattrapage."""
    chemin = Path(dossier) / "rattrapage.json"
    historique = lire_json(chemin) or {"meta": {}, "donnees": []}
    relances = historique.get("donnees", [])
    nouvelles = []
    for agent in lire_agents(dossier):
        relancer, raison, manquante = a_relancer(agent, maintenant, relances)
        LOG.info("%s : %s", agent["agent"], raison)
        if not relancer:
            continue
        entree = {"agent": agent["agent"], "workflow": agent["workflow"], "relance_le": sante.iso(maintenant),
                  "execution_manquante": sante.iso(manquante), "derniere_execution": agent.get("derniere_execution"),
                  "raison": raison}
        if en_cours(agent["workflow"]):
            entree |= {"statut": "ignoré", "detail": "une exécution est déjà en cours ou en attente"}
        else:
            ok, detail = lanceur(agent["workflow"])
            entree |= {"statut": "relancé" if ok else "échec", "detail": detail or None}
        LOG.info("%s : %s (%s)", agent["agent"], entree["statut"], entree["detail"])
        nouvelles.append(entree)
    if nouvelles:
        historique["meta"] = {**historique.get("meta", {}), "genere_le": sante.iso(maintenant), "source": "rattrapage",
                              "description": "Relances des agents dont une exécution planifiée manquait depuis plus d'une heure"}
        historique["donnees"] = (relances + nouvelles)[-MAXIMUM:]
        ecrire_json(chemin, historique)
    return nouvelles


def main() -> int:
    nouvelles = rattraper(datetime.now(timezone.utc))
    echecs = [e for e in nouvelles if e["statut"] == "échec"]
    LOG.info("%d relance(s), %d échec(s).", sum(e["statut"] == "relancé" for e in nouvelles), len(echecs))
    return 1 if echecs else 0
