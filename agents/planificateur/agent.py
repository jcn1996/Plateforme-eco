"""
Planificateur des agents, réveillé de l'extérieur.

Les tâches planifiées de GitHub (schedule) sont parfois retardées ou sautées. Un service externe
(cron-job.org) appelle toutes les 15 minutes le workflow « Planificateur » (workflow_dispatch).
À chaque appel, ce module :
1. liste les tâches : une par ligne « cron » des workflows d'agents (.github/workflows/*.yml),
   avec ses paramètres de lancement (ex. mode « complet » pour la révision du samedi) ;
2. pour chacune, prend le dernier créneau prévu (≤ maintenant, marge de 2 min) ;
3. la lance (gh workflow run) si ce créneau n'est pas encore fait :
   - fait = l'agent a une exécution réussie (derniere_execution de son journal) postérieure au créneau ;
   - pour un workflow sans journal (maintien), fait = déjà lancé par le planificateur pour ce créneau ;
   - jamais deux fois le même créneau : un créneau déjà lancé n'est relancé qu'après 60 min sans
     résultat, au plus 2 tentatives ; rien n'est lancé si une exécution du workflow est en cours.
Les plannings GitHub restent actifs en secours : la « concurrency » de chaque workflow évite les doublons.

Trace : data/journal/planificateur.json (décisions de lancement, dernier appel, bloc santé).
Le fichier n'est réécrit (donc commité) que s'il y a eu un lancement, ou si le dernier appel
enregistré date de plus de 20 min (battement, pour l'écran Santé).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.commun import sante
from agents.commun.journal import journal
from agents.commun.sortie import ecrire_json, lire_json

LOG = journal("planificateur")
DOSSIER = Path(__file__).resolve().parent
CONFIG = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
MAXIMUM = 300


# ------------------------------------------------------------------ tâches

def taches(dossier_workflows: Path = sante.DOSSIER_WORKFLOWS, dossier_journal: Path = sante.DOSSIER_JOURNAL,
           config: dict = CONFIG) -> list[dict]:
    """Une tâche par ligne cron de chaque workflow d'agent :
    {cle, workflow, cron, parametres, journal (dernière exécution réussie ou None)}."""
    # Dernière exécution réussie de chaque workflow, d'après les journaux des agents
    derniere = {}
    for chemin in sorted(Path(dossier_journal).glob("*.json")):
        j = lire_json(chemin) or {}
        s = (j.get("meta") or {}).get("sante") or {}
        if s.get("workflow"):
            derniere[s["workflow"]] = j.get("derniere_execution") or s.get("derniere_execution")
    res = []
    for chemin in sorted(Path(dossier_workflows).glob("*.yml")):
        if chemin.name in config["ignores"]:
            continue
        params = config["parametres"].get(chemin.name, {})
        for cron in _crons(chemin):
            res.append({"cle": f"{chemin.name}|{cron}", "workflow": chemin.name, "cron": cron,
                        "parametres": params.get(cron, params.get("*", {})),
                        "a_un_journal": chemin.name in derniere, "derniere_execution": derniere.get(chemin.name)})
    return res


def _crons(chemin: Path) -> list[str]:
    import re
    return re.findall(r"""^\s*-\s*cron:\s*["']([^"']+)["']""", chemin.read_text(encoding="utf-8"), re.MULTILINE)


# ------------------------------------------------------------------ décision

def decider(tache: dict, maintenant: datetime, lancements: list[dict], config: dict = CONFIG) -> dict:
    """Décision pour une tâche : {lancer: bool, raison, creneau}."""
    creneau = sante.precedente_execution([tache["cron"]], maintenant - timedelta(minutes=config["marge_minutes"]))
    if creneau is None:
        return {"lancer": False, "raison": "aucun créneau passé", "creneau": None}
    iso_creneau = sante.iso(creneau)
    if tache["a_un_journal"]:
        derniere = sante.lire_iso(tache.get("derniere_execution"))
        if derniere and derniere >= creneau:
            return {"lancer": False, "raison": "déjà fait", "creneau": iso_creneau}
    # Un lancement du même workflow pour ce créneau ou un créneau plus récent le couvre
    deja = [l for l in lancements if l.get("workflow") == tache["workflow"] and (l.get("creneau") or "") >= iso_creneau
            and l.get("statut") == "lancé"]
    if deja:
        if not tache["a_un_journal"]:
            return {"lancer": False, "raison": "déjà lancé pour ce créneau", "creneau": iso_creneau}
        dernier = max(sante.lire_iso(l["le"]) for l in deja)
        if len(deja) >= config["tentatives_max"]:
            return {"lancer": False, "raison": f"{len(deja)} tentatives déjà faites pour ce créneau", "creneau": iso_creneau}
        if maintenant - dernier < timedelta(minutes=config["nouvelle_tentative_minutes"]):
            return {"lancer": False, "raison": "lancé, en attente du résultat", "creneau": iso_creneau}
        return {"lancer": True, "raison": "lancé il y a plus d'une heure sans résultat : nouvelle tentative", "creneau": iso_creneau}
    return {"lancer": True, "raison": "créneau dû, pas encore fait", "creneau": iso_creneau}


# ------------------------------------------------------------------ actions GitHub

def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)


def execution_en_cours(workflow: str) -> bool:
    r = gh("run", "list", "--workflow", workflow, "--limit", "10", "--json", "status")
    if r.returncode != 0:
        LOG.warning("gh run list %s : %s", workflow, r.stderr.strip())
        return False
    return any(x.get("status") != "completed" for x in json.loads(r.stdout or "[]"))


def lancer(workflow: str, parametres: dict) -> tuple[bool, str]:
    args = ["workflow", "run", workflow, "--ref", os.environ.get("BRANCHE", "main")]
    for k, v in parametres.items():
        args += ["-f", f"{k}={v}"]
    r = gh(*args)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


# ------------------------------------------------------------------ appel

def planifier(maintenant: datetime, dossier_journal: Path = sante.DOSSIER_JOURNAL, dossier_workflows: Path = sante.DOSSIER_WORKFLOWS,
              en_cours=execution_en_cours, lanceur=lancer, config: dict = CONFIG) -> dict:
    """Un appel du planificateur. Renvoie {decisions, lancements, ecrit}."""
    chemin = Path(dossier_journal) / "planificateur.json"
    j = lire_json(chemin) or {"meta": {}, "donnees": []}
    historique = j.get("donnees", [])
    decisions, nouveaux = [], []
    a_lancer = {}
    for t in taches(dossier_workflows, dossier_journal, config):
        d = decider(t, maintenant, historique, config)
        decisions.append({"tache": t["cle"], **d})
        LOG.info("%-55s %s", t["cle"], d["raison"])
        # Un seul lancement par workflow : le créneau dû le plus récent (ex. révision du samedi plutôt que la quotidienne de vendredi)
        if d["lancer"] and (t["workflow"] not in a_lancer or d["creneau"] > a_lancer[t["workflow"]][1]["creneau"]):
            a_lancer[t["workflow"]] = (t, d)
    for t, d in a_lancer.values():
        entree = {"cle": t["cle"], "workflow": t["workflow"], "parametres": t["parametres"], "creneau": d["creneau"],
                  "le": sante.iso(maintenant), "raison": d["raison"]}
        if en_cours(t["workflow"]):
            entree |= {"statut": "ignoré", "detail": "une exécution du workflow est déjà en cours ou en attente"}
        else:
            ok, detail = lanceur(t["workflow"], t["parametres"])
            entree |= {"statut": "lancé" if ok else "échec", "detail": detail or None}
        LOG.info("→ %s : %s", t["workflow"], entree["statut"])
        nouveaux.append(entree)

    # Battement : le dernier appel n'est enregistré que toutes les 20 min s'il n'y a eu aucun lancement
    dernier_appel = sante.lire_iso((j.get("meta") or {}).get("dernier_appel"))
    battement = dernier_appel is None or maintenant - dernier_appel >= timedelta(minutes=config["battement_minutes"])
    ecrit = bool([n for n in nouveaux if n["statut"] != "ignoré"]) or battement
    if ecrit:
        lances = [n for n in nouveaux if n["statut"] == "lancé"]
        echecs = [n for n in nouveaux if n["statut"] == "échec"]
        bloc = {
            "agent": "planificateur", "libelle": "Planificateur (réveil externe)", "ordre": 0, "workflow": "planificateur.yml",
            "derniere_execution": sante.iso(maintenant), "appel_externe": True, "panne_minutes": config["panne_minutes"],
            "prochaine_prevue": None, "intervalle_min": 15,
            "sources_total": 1, "sources_ok": 0 if echecs else 1,
            "sources": [{"nom": "gh workflow run (lancement des agents)", "etat": "échec" if echecs else "ok",
                         "detail": "; ".join(f"{e['workflow']} : {e['detail']}" for e in echecs)[:300] or None}],
            "degrade": bool(echecs), "raisons": [f"Lancement de {e['workflow']} en échec" for e in echecs],
            "dernier_lancement": lances[-1]["le"] if lances else ((j.get("meta") or {}).get("sante") or {}).get("dernier_lancement"),
        }
        j["meta"] = {**j.get("meta", {}), "genere_le": sante.iso(maintenant), "source": "planificateur",
                     "description": "Appels du réveil externe (cron-job.org) et lancements d'agents décidés par le planificateur",
                     "dernier_appel": sante.iso(maintenant), "sante": bloc}
        j["derniere_execution"] = sante.iso(maintenant)
        j["donnees"] = (historique + nouveaux)[-MAXIMUM:]
        ecrire_json(chemin, j)
        sante.inscrire_dans_index(chemin, bloc)
    return {"decisions": decisions, "lancements": nouveaux, "ecrit": ecrit}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Planificateur des agents (réveil externe).")
    ap.add_argument("--simulation", action="store_true", help="affiche les décisions sans rien lancer ni écrire")
    ap.add_argument("--maintenant", help="heure simulée (ISO, UTC), avec --simulation")
    args = ap.parse_args(argv)
    maintenant = sante.lire_iso(args.maintenant) if args.maintenant else datetime.now(timezone.utc)
    if args.simulation:
        j = lire_json(sante.DOSSIER_JOURNAL / "planificateur.json") or {}
        for t in taches():
            d = decider(t, maintenant, j.get("donnees", []))
            print(f"{'LANCER ' if d['lancer'] else '       '} {t['cle']:55} créneau {d['creneau']} : {d['raison']}")
        return 0
    r = planifier(maintenant)
    echecs = [n for n in r["lancements"] if n["statut"] == "échec"]
    LOG.info("%d lancement(s), %d échec(s), journal %s.", sum(n["statut"] == "lancé" for n in r["lancements"]), len(echecs),
             "mis à jour" if r["ecrit"] else "inchangé")
    return 1 if echecs else 0
