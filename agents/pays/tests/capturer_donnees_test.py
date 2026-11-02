"""
Capture des données de test à partir des vraies sources (à lancer à la main, rarement) :
    python -m agents.pays.tests.capturer_donnees_test
Les cours quotidiens sont allégés (un point sur cinq + les derniers jours) pour garder des fichiers petits.
"""
import json
from pathlib import Path

from ..agent import RACINE, collecter
from ..sources import FournisseurReel

DOSSIER = Path(__file__).resolve().parent / "donnees"


def main():
    from datetime import date
    config = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
    src, etats = collecter(FournisseurReel(RACINE / "agents" / ".cache"), config, date.today())
    DOSSIER.mkdir(parents=True, exist_ok=True)
    iso3 = {p["iso3"] for p in config["pays"].values()}
    fichiers = {
        "fmi_NGDP_RPCH": src["fmi_croissance"], "fmi_PCPIPCH": src["fmi_inflation"], "fmi_BCA_NGDPD": src["fmi_solde_courant"],
        "ocde_cli": src["ocde_cli"], "ocde_inflation": src["ocde_inflation"], "bis": src["bis"],
        "cours": {k: v[::5] + v[-5:] for k, v in src["yahoo_cours"].items()}, "per": src["yahoo_per"],
    }
    for nom, contenu in fichiers.items():
        if nom.startswith("fmi_"):  # seulement les pays suivis, années récentes
            contenu = {k: {a: x for a, x in v.items() if a >= "2023"} for k, v in contenu.items() if k in iso3}
        (DOSSIER / f"{nom}.json").write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    print("Données de test écrites dans", DOSSIER, etats)


if __name__ == "__main__":
    main()
