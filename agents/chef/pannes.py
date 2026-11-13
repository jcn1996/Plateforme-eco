"""
Agents en panne : un agent dont aucune exécution n'a réussi depuis plus de `seuil_heures` (24 h par défaut) au-delà
de l'exécution prévue qui suit sa dernière réussite. Les pauses prévues (nuit, week-end, agent hebdomadaire) ne
comptent donc pas : on mesure le retard sur le planning (lignes cron déclarées dans le journal de l'agent), pas
l'ancienneté brute de la dernière exécution.

Le chef d'orchestre met ces pannes en tête des alertes du jour (data/alertes.json), du briefing et des points de
vigilance : les données de l'agent ne sont plus à jour, et ses signaux pèsent moins dans les verdicts.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..commun import sante
from ..commun.sortie import lire_json
from ..risque.calculs import date_fr, fr


def agents_en_panne(dossier_journal: Path, maintenant: datetime, seuil_heures: float = 24, exclus=("chef",)) -> list[dict]:
    index = (lire_json(Path(dossier_journal) / "index.json") or {}).get("donnees") or []
    res = []
    for e in index:
        if e.get("agent") in exclus:
            continue
        j = lire_json(Path(dossier_journal) / e["fichier"]) or {}
        s = (j.get("meta") or {}).get("sante") or {}
        derniere = sante.lire_iso(j.get("derniere_execution") or s.get("derniere_execution"))
        if derniere is None:
            continue
        if s.get("appel_externe"):  # planificateur : appelé de l'extérieur toutes les 15 minutes, sans planning cron
            attendue = derniere
        else:
            crons = (j.get("planning") or s.get("planning") or {}).get("crons") or []
            if not crons:
                continue
            attendue = sante.prochaine_execution(crons, derniere)
            if attendue is None:
                continue
        retard = (maintenant - attendue).total_seconds() / 3600
        if retard <= seuil_heures:
            continue
        depuis = (maintenant - derniere).total_seconds() / 3600
        libelle = s.get("libelle") or e.get("libelle") or e.get("agent")
        res.append({"agent": e.get("agent"), "libelle": libelle, "workflow": s.get("workflow"),
                    "derniere_execution": sante.iso(derniere), "prevue": sante.iso(attendue),
                    "depuis_h": round(depuis, 1), "retard_h": round(retard, 1),
                    "texte": (f"{libelle} en panne : aucune exécution réussie depuis le {date_fr(sante.iso(derniere))} à "
                              f"{sante.iso(derniere)[11:16]} UTC ({fr(depuis / 24, 1)} jour(s)) ; l'exécution prévue le "
                              f"{date_fr(sante.iso(attendue))} à {sante.iso(attendue)[11:16]} UTC n'a pas abouti. Ses données ne sont "
                              "plus à jour : les signaux qui en dépendent pèsent moins dans les verdicts (écran Santé).")})
    res.sort(key=lambda x: -x["retard_h"])
    return res


def alertes_de_panne(pannes: list[dict], maintenant: datetime) -> list[dict]:
    """Alertes au format de data/alertes.json, à placer en tête."""
    jour = maintenant.date().isoformat()
    return [{"id": f"chef-panne-{p['agent']}-{jour}", "rang": 0, "heure": date_fr(jour)[:5], "date": jour, "agent": "chef", "pays": None,
             "niveau": "defavorable", "importance": "forte", "panne": True,
             "titre": f"{p['libelle']} en panne depuis {fr(p['depuis_h'] / 24, 1)} jour(s)", "texte": p["texte"],
             "route": {"type": "sante"}} for p in pannes]
