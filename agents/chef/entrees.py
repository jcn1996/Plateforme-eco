"""
Entrées du chef d'orchestre : sorties de tous les agents (data/*.json), avec pour chacune un
coefficient de fiabilité = fraîcheur × (dégradation de l'agent).

Trois états, même règle que l'écran « Santé des agents » et le réseau de l'accueil (agents/commun/sante.py,
etat_execution ; js/planning.js) :
- « à jour » ;
- « dégradé » : l'agent a tourné, mais une source secondaire manque (raisons et date d'apparition affichées) :
  × `coef_degrade` ;
- « en panne » : une exécution prévue par le planning de l'agent a été manquée (au-delà d'une marge de 3 à 12 h,
  selon la durée observée de ses exécutions) ou la dernière a échoué : la fraîcheur décroît de 1 à
  `coef_perime_min` en `decroissance_h` heures après l'exécution manquée.
Un agent qui ne tourne que quelques fois par semaine n'est donc plus « périmé » entre deux exécutions prévues.
Sans planning dans le journal (cas ancien), l'âge maximal `age_max_h` sert de repli.
Fichier absent : coefficient 0, entrée « manquante » (signalée, jamais inventée).
La confiance propre à chaque valeur (« élevé », « moyen », « faible ») est appliquée famille par famille
dans univers.py (coef_confiance).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from ..commun.sante import etat_execution, lire_iso
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
        depuis = sante.get("raisons_depuis") or {}
        self.degrade_depuis = min(depuis.values()) if depuis else None
        self.raisons_depuis = depuis
        genere = lire_iso(self.meta.get("genere_le"))
        self.genere_le = self.meta.get("genere_le")
        self.age_h = round((maintenant - genere).total_seconds() / 3600, 1) if genere else None
        self.panne = None
        mini = regles["coef_perime_min"]
        planifie = bool((sante.get("planning") or {}).get("crons")) or sante.get("a_la_demande") or sante.get("appel_externe")
        if objet is None:
            self.fraicheur, self.etat = 0.0, "manquante"
        elif planifie:
            ex = etat_execution(sante, maintenant)
            if ex["etat"] == "en panne":
                self.panne = {"raison": ex["raison"], "manquante": ex["manquante"], "marge_h": ex["marge_h"]}
                debut = lire_iso(ex["manquante"]) + timedelta(hours=ex["marge_h"]) if ex["manquante"] else maintenant
                t = min(1.0, max(0.0, (maintenant - debut).total_seconds() / 3600) / regles["decroissance_h"])
                self.fraicheur, self.etat = round(1 - (1 - mini) * t, 2), "en panne"
            else:
                self.fraicheur, self.etat = 1.0, "dégradé" if self.degrade else "à jour"
        elif self.age_h is None:
            self.fraicheur, self.etat = 0.8, "date inconnue"
        elif self.age_h <= cfg["age_max_h"]:
            self.fraicheur, self.etat = 1.0, "dégradé" if self.degrade else "à jour"
        else:  # repli sans planning : âge maximal
            t = min(1.0, (self.age_h - cfg["age_max_h"]) / (2 * cfg["age_max_h"]))
            self.fraicheur, self.etat = round(1 - (1 - mini) * t, 2), "en panne"
            self.panne = {"raison": f"donnée de {round(self.age_h)} h, au-delà de {cfg['age_max_h']} h (journal sans planning)", "manquante": None, "marge_h": None}
        self.coef = round(self.fraicheur * (regles["coef_degrade"] if self.degrade else 1.0), 2)

    @property
    def disponible(self) -> bool:
        return self.objet is not None and self.donnees is not None

    def resume(self) -> dict:
        return {"cle": self.cle, "libelle": self.libelle, "etat": self.etat, "genere_le": self.genere_le, "age_h": self.age_h,
                "degrade": self.degrade, "raisons_degrade": self.raisons_degrade[:3], "degrade_depuis": self.degrade_depuis,
                "raisons_depuis": {r.split(" : ")[0]: self.raisons_depuis.get(r.split(" : ")[0]) for r in self.raisons_degrade[:3]},
                "panne": self.panne, "fraicheur": self.fraicheur, "coef": self.coef}


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
