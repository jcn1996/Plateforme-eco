"""Lecture et écriture des fichiers JSON de l'application (enveloppe { meta, donnees })."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def maintenant_iso() -> str:
    """Date et heure UTC au format ISO, à la seconde (ex. 2026-11-03T06:00:12Z)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def enveloppe(donnees, source: str, fictif: bool = False, **meta_supplementaire) -> dict:
    """Enveloppe habituelle des fichiers de data/ : { meta, donnees }."""
    meta = {"version": 1, "genere_le": maintenant_iso(), "source": source, "fictif": fictif}
    meta.update(meta_supplementaire)
    return {"meta": meta, "donnees": donnees}


def lire_json(chemin: Path, defaut=None):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defaut


def ecrire_json(chemin: Path, objet, compact: bool = False) -> None:
    """Écriture atomique : on écrit un fichier temporaire puis on le renomme
    (un fichier à moitié écrit ne peut jamais être publié)."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, temporaire = tempfile.mkstemp(dir=chemin.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        if compact:  # gros fichiers (agent entreprises) : sans indentation
            json.dump(objet, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(objet, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temporaire, chemin)
