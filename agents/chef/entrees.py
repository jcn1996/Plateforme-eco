"""
Entrées du chef d'orchestre : sorties de tous les agents (data/*.json), avec pour chacune un
coefficient de fiabilité = fraîcheur × (dégradation de l'agent).

- fraîcheur : 1 tant que la donnée a moins de `age_max_h` heures, puis décroissance linéaire jusqu'à
  `coef_perime_min` à 3 × `age_max_h` (donnée « périmée », signalée) ;
- agent dégradé (bloc santé de son journal) : × `coef_degrade` (signalé) ;
- fichier absent : coefficient 0, entrée « manquante » (signalée, jamais inventée).
La confiance propre à chaque valeur (« élevé », « moyen », « faible ») est appliquée famille par famille
dans univers.py (coef_confiance).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..commun.sante import lire_iso
from ..commun.sortie import lire_json


class Entree:
    def __init__(self, cle: str, cfg: dict, objet: dict | None, journal: dict | None, maintenant: datetime, regles: dict):
        self.cle, self.cfg = cle, cfg
        self.libelle = cfg["libelle"]
        self.objet = objet
        self.meta = (objet or {}).get("meta") or {}
        self.donnees = (objet or {}).get("donnees") if objet else None
        sante = ((journal or {}).get("meta") or {}).get("sante") or {}
        self.degrade = bool(sante.get("degrade"))
        self.raisons_degrade = sante.get("raisons") or []
        genere = lire_iso(self.meta.get("genere_le")) or lire_iso((self.meta or {}).get("genere_le"))
        self.genere_le = self.meta.get("genere_le")
        self.age_h = round((maintenant - genere).total_seconds() / 3600, 1) if genere else None
        age_max = cfg["age_max_h"]
        if objet is None:
            self.fraicheur, self.etat = 0.0, "manquante"
        elif self.age_h is None:
            self.fraicheur, self.etat = 0.8, "date inconnue"
        elif self.age_h <= age_max:
            self.fraicheur, self.etat = 1.0, "à jour"
        else:
            mini = regles["coef_perime_min"]
            t = min(1.0, (self.age_h - age_max) / (2 * age_max))
            self.fraicheur, self.etat = round(1 - (1 - mini) * t, 2), "périmée"
        self.coef = round(self.fraicheur * (regles["coef_degrade"] if self.degrade else 1.0), 2)

    @property
    def disponible(self) -> bool:
        return self.objet is not None and self.donnees is not None

    def resume(self) -> dict:
        return {"cle": self.cle, "libelle": self.libelle, "etat": self.etat, "genere_le": self.genere_le, "age_h": self.age_h,
                "degrade": self.degrade, "raisons_degrade": self.raisons_degrade[:3], "fraicheur": self.fraicheur, "coef": self.coef}


def charger(data: Path, config: dict, maintenant: datetime) -> dict[str, Entree]:
    regles = config["entrees"]
    res = {}
    for cle, cfg in regles["fichiers"].items():
        objet = lire_json(data / cfg["fichier"])
        if objet is not None and not isinstance(objet, dict):
            objet = None
        journal = lire_json(data / "journal" / cfg["journal"])
        res[cle] = Entree(cle, cfg, objet, journal, maintenant, regles)
    return res


def coef_confiance(niveau, config: dict) -> float:
    if isinstance(niveau, dict):
        niveau = niveau.get("niveau")
    return config["entrees"]["confiance"].get(str(niveau or "moyen"), 0.85)


def signaux(data: Path) -> dict[str, list[dict]]:
    """data/signaux/*.json sauf revues.json : {agent: [signaux]}."""
    res = {}
    dossier = data / "signaux"
    if not dossier.exists():
        return res
    for chemin in sorted(dossier.glob("*.json")):
        if chemin.name in ("revues.json", "chef.json"):
            continue
        d = (lire_json(chemin) or {}).get("donnees") or []
        res[chemin.stem] = [s for s in d if isinstance(s, dict)]
    return res
