"""Capture des données de test de l'agent risque (réponses réelles, compactées).

    python -m agents.risque.tests.capturer_donnees_test

Enregistre dans agents/risque/tests/donnees/ les séries FRED, BCE, FMI, Banque mondiale et
Yahoo Finance utilisées par l'agent, pour les pays de PAYS_TEST seulement. Les séries longues
sont compactées (quotidien sur 400 jours, hebdomadaire avant) pour limiter la taille du dépôt.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .. import calculs as C
from ..agent import RACINE, charger_config, pays_suivis
from ..sources import FournisseurReel

PAYS_TEST = ["US", "FR", "DE", "IT", "ES", "BR", "TR", "JP", "MX"]
DOSSIER = Path(__file__).resolve().parent / "donnees"


def ecrire(nom: str, objet) -> None:
    (DOSSIER / f"{nom}.json").write_text(json.dumps(objet, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    config = charger_config()
    pays = {k: v for k, v in pays_suivis().items() if k in PAYS_TEST}
    f = FournisseurReel(RACINE / "agents" / ".cache")
    aujourdhui = date.today()
    debut = (aujourdhui - timedelta(days=365 * 6)).isoformat()
    for ci in config["indicateurs"].values():
        for s in ci["sources"]:
            if s["type"] == "fred":
                ecrire(f"fred_{s['serie']}", C.compacter(f.fred(s["serie"], debut), aujourdhui))
            elif s["type"] == "bce":
                ecrire(f"bce_{s['flux']}_{s['cle']}", C.compacter(f.bce(s["flux"], s["cle"], debut), aujourdhui))
    for code, serie in config["pays"]["taux_10a_fred"].items():
        if code in PAYS_TEST:
            ecrire(f"fred_{serie}", f.fred(serie, debut))
    for code, cle in config["pays"]["souverains_bce"].items():
        if code in PAYS_TEST:
            ecrire(f"bce_IRS_{cle}", f.bce("IRS", cle, debut[:7]))
    iso3 = {p["iso3"] for p in pays.values()}
    for serie in ("GGXWDG_NGDP", "BCA_NGDPD", "PCPIPCH"):
        ecrire(f"fmi_{serie}", {k: {a: v for a, v in x.items() if a >= "2018"} for k, x in f.fmi(serie).items() if k in iso3})
    ecrire("bm_FI.RES.TOTL.MO", {k: v for k, v in f.banque_mondiale("FI.RES.TOTL.MO", aujourdhui.year).items() if k in iso3})
    marches = []
    for ci in config["indicateurs"].values():
        marches += [s["symbole"] for s in ci["sources"] if s["type"] == "yahoo" and not ci.get("facultatif")]
    marches += [a["symbole"] for a in config["correlations"]["actifs"].values()]
    cours = {k: C.compacter(v, aujourdhui) for k, v in f.cours(list(dict.fromkeys(marches)), "6y").items()}
    symboles = [p["etf"] for p in pays.values()] + [p["devise"]["symbole"] for p in pays.values() if p.get("devise")]
    cours.update({k: [[d, round(v, 5)] for d, v in s] for k, s in f.cours(list(dict.fromkeys(symboles)), "13mo").items() if k not in cours})
    ecrire("cours", {k: [[d, round(v, 5)] for d, v in s] for k, s in cours.items()})
    print("Données de test écrites dans", DOSSIER)


if __name__ == "__main__":
    main()
