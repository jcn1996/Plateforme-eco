"""
Téléchargement avec reprises, délais et cache disque.

- Reprises : en cas d'erreur réseau, de code 429 (trop de requêtes) ou 5xx,
  on réessaie avec une attente croissante (2 s, 4 s, 8 s…).
- Délai de politesse entre deux requêtes vers les sources publiques.
- Cache : chaque réponse est gardée sur disque (agents/.cache) pendant
  quelques heures, ce qui évite de solliciter les sources lors de
  plusieurs essais successifs. Le cache n'est jamais commité.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

from .journal import journal

LOG = journal("telechargement")
AGENT_HTTP = "SalleDeControle-AgentPays/1.0 (+https://github.com/jcn1996/Plateforme-eco)"


class ErreurSource(Exception):
    """Une source n'a pas pu être lue (après toutes les reprises)."""


class Telechargeur:
    def __init__(self, dossier_cache: Path, duree_cache_h: float = 6, essais: int = 4,
                 attente_initiale: float = 2.0, delai_politesse: float = 0.5, delai_max: float = 45):
        self.dossier_cache = Path(dossier_cache)
        self.dossier_cache.mkdir(parents=True, exist_ok=True)
        self.duree_cache = duree_cache_h * 3600
        self.essais = essais
        self.attente_initiale = attente_initiale
        self.delai_politesse = delai_politesse
        self.delai_max = delai_max
        self.session = requests.Session()
        self.session.headers["User-Agent"] = AGENT_HTTP
        self._derniere_requete = 0.0

    def _chemin_cache(self, url: str, params: dict | None) -> Path:
        cle = url + "?" + json.dumps(params or {}, sort_keys=True)
        return self.dossier_cache / (hashlib.sha256(cle.encode()).hexdigest()[:32] + ".txt")

    def texte(self, url: str, params: dict | None = None, entetes: dict | None = None) -> str:
        """Renvoie le corps de la réponse (texte). Lève ErreurSource après échec des reprises."""
        cache = self._chemin_cache(url, params)
        if cache.exists() and time.time() - cache.stat().st_mtime < self.duree_cache:
            return cache.read_text(encoding="utf-8")

        derniere_erreur = None
        for essai in range(1, self.essais + 1):
            # Délai de politesse entre deux requêtes
            attente = self.delai_politesse - (time.monotonic() - self._derniere_requete)
            if attente > 0:
                time.sleep(attente)
            self._derniere_requete = time.monotonic()
            try:
                r = self.session.get(url, params=params, headers=entetes, timeout=self.delai_max)
                if r.status_code == 200:
                    cache.write_text(r.text, encoding="utf-8")
                    return r.text
                derniere_erreur = f"HTTP {r.status_code}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break  # erreur définitive (404…) : inutile d'insister
            except requests.RequestException as e:
                derniere_erreur = f"{type(e).__name__}: {e}"
            if essai < self.essais:
                pause = self.attente_initiale * 2 ** (essai - 1)
                LOG.warning("Échec %s (%s), nouvel essai dans %.0f s", url, derniere_erreur, pause)
                time.sleep(pause)
        raise ErreurSource(f"{url} : {derniere_erreur}")

    def octets(self, url: str, params: dict | None = None, entetes: dict | None = None) -> bytes:
        """Comme texte(), pour un fichier binaire (zip, xls). Même cache, mêmes reprises."""
        cache = self._chemin_cache(url, params).with_suffix(".bin")
        if cache.exists() and time.time() - cache.stat().st_mtime < self.duree_cache:
            return cache.read_bytes()
        derniere_erreur = None
        for essai in range(1, self.essais + 1):
            attente = self.delai_politesse - (time.monotonic() - self._derniere_requete)
            if attente > 0:
                time.sleep(attente)
            self._derniere_requete = time.monotonic()
            try:
                r = self.session.get(url, params=params, headers=entetes, timeout=self.delai_max)
                if r.status_code == 200:
                    cache.write_bytes(r.content)
                    return r.content
                derniere_erreur = f"HTTP {r.status_code}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
            except requests.RequestException as e:
                derniere_erreur = f"{type(e).__name__}: {e}"
            if essai < self.essais:
                pause = self.attente_initiale * 2 ** (essai - 1)
                LOG.warning("Échec %s (%s), nouvel essai dans %.0f s", url, derniere_erreur, pause)
                time.sleep(pause)
        raise ErreurSource(f"{url} : {derniere_erreur}")

    def json(self, url: str, params: dict | None = None, entetes: dict | None = None):
        return json.loads(self.texte(url, params, entetes))
