"""
Méthode en service et dernier rapport de backtest validé.

Le backtest mensuel tient l'historique de ses recalibrages dans data/backtest/recalibrages.json. Un recalibrage
est « validé » quand une personne a fusionné sa pull request : les réglages qu'il proposait sont alors ceux des
fichiers de configuration. Le chef d'orchestre (et, à travers lui, l'agent trader) lit toujours le rapport du
dernier recalibrage validé : aucun nom de rapport n'est écrit en dur dans les réglages.
"""
from __future__ import annotations

import json
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
HISTORIQUE = Path("backtest") / "recalibrages.json"  # relatif au dossier data/


def lire_historique(chemin: Path) -> list[dict]:
    try:
        j = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    d = j.get("donnees", j) if isinstance(j, dict) else j
    h = d.get("historique", []) if isinstance(d, dict) else d
    return [e for e in h if isinstance(e, dict) and e.get("mois")]


def _valeur(racine: Path, fichier: str, chemin: list[str]):
    try:
        v = json.loads((Path(racine) / fichier).read_text(encoding="utf-8"))
        for cle in chemin:
            v = v[cle]
        return v
    except (OSError, ValueError, KeyError, TypeError):
        return None


def modification_appliquee(m: dict, racine: Path = RACINE) -> bool:
    """La configuration actuelle contient-elle ce réglage proposé ?"""
    v = _valeur(racine, m["fichier"], m["chemin"])
    if v is None:
        return False
    if m.get("type") == "combinaisons":
        return isinstance(v, list) and sorted(c.get("cle") for c in v) == sorted(c["cle"] for c in m["propose"])
    return isinstance(v, dict) and all(v.get(k) == x for k, x in m["propose"].items())


def appliquee(entree: dict, racine: Path = RACINE) -> bool:
    mods = entree.get("modifications") or []
    return bool(mods) and all(modification_appliquee(m, racine) for m in mods)


def est_validee(entree: dict, racine: Path = RACINE) -> bool:
    """Validé : noté comme tel, ou proposition dont les réglages sont désormais en service (pull request fusionnée
    depuis la dernière exécution du backtest)."""
    if entree.get("statut") == "validé":
        return True
    return entree.get("statut") in ("à valider", "non validé") and appliquee(entree, racine)


def dernier_valide(data: Path, racine: Path = RACINE) -> dict | None:
    """Dernier recalibrage validé ({mois, rapport, …}), ou None s'il n'y en a aucun."""
    for e in sorted(lire_historique(Path(data) / HISTORIQUE), key=lambda e: e["mois"], reverse=True):
        if e.get("rapport") and est_validee(e, racine):
            return e
    return None


def rapport_valide(data: Path, racine: Path = RACINE) -> str | None:
    e = dernier_valide(data, racine)
    return e["rapport"] if e else None
