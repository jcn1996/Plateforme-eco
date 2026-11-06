"""Outils pour les tests : données de test isolées, sans jamais lire ni modifier les vrais config/ et data/.

Les tests qui ont besoin de data/pays.json et data/macro.json les obtiennent ici : ils sont
produits par les agents pays et macro eux-mêmes, en mode test (données enregistrées, sans réseau),
dans un dossier temporaire. Les résultats ne dépendent donc jamais de l'état réel de la plateforme.
"""
from __future__ import annotations

import atexit
import logging
import shutil
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
JOUR_TEST = "2026-11-02"
_CACHE: Path | None = None


def _generer() -> Path:
    from agents.macro.agent import main as macro
    from agents.pays.agent import main as pays

    d = Path(tempfile.mkdtemp(prefix="essais-"))
    atexit.register(shutil.rmtree, d, True)
    niveau = logging.getLogger().level
    logging.disable(logging.INFO)  # journaux des agents inutiles dans la sortie des tests
    try:
        code = pays(["--test", "--donnees-test", str(RACINE / "agents" / "pays" / "tests" / "donnees"),
                     "--sortie", str(d / "pays.json"), "--historique", str(d / "historique" / "pays"),
                     "--journal", str(d / "journal" / "agent-pays.json"),
                     "--recap", str(d / "recap"), "--date", JOUR_TEST])
        if code != 0:
            raise RuntimeError(f"agent pays (test) : code {code}")
        code = macro(["--test", "--data", str(d), "--date", JOUR_TEST])
        if code != 0:
            raise RuntimeError(f"agent macro (test) : code {code}")
    finally:
        logging.disable(logging.NOTSET)
        logging.getLogger().setLevel(niveau)
    return d


def copier_donnees_test(dossier: Path, fichiers=("pays.json", "macro.json")) -> None:
    """Copie dans `dossier` des fichiers pays.json / macro.json de test (générés une fois par exécution)."""
    global _CACHE
    if _CACHE is None or not _CACHE.exists():
        _CACHE = _generer()
    Path(dossier).mkdir(parents=True, exist_ok=True)
    for f in fichiers:
        shutil.copy(_CACHE / f, Path(dossier) / f)
