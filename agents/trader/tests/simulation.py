"""Simulation de l'agent trader sur des données de test (cours simulés, sans réseau, dossier temporaire) :
    python -m agents.trader.tests.simulation [--jours 92]
Trois mois de séances, méthode par combinaisons : rééquilibrage mensuel, contrôles horaires des paris pays, chocs de
cours, une société qui sort de sa combinaison, un pari pays en excès. Affiche la performance (globale et par poche),
le risque, les opérations, les paris pays et l'attribution."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from agents.trader.agent import charger_config, executer
from agents.trader.sources import FournisseurSimule
from agents.trader.tests.fabrique import PARIS, SELECTION_ENTREPRISES, evaluation, simuler


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jours", type=int, default=92)
    args = ap.parse_args(argv)
    logging.disable(logging.INFO)
    d = Path(tempfile.mkdtemp(prefix="simulation-trader-"))
    try:
        f = FournisseurSimule(debut="2025-06-01", chocs={"S05": [("2026-09-15", 0.8)], "S06": [("2026-09-20", 1.35)]})
        moins_s07 = [x for x in SELECTION_ENTREPRISES if x[0] != "S07"]
        exces = ["accélération parabolique (simulation)"]
        paris = [evaluation(c, n, e, fo, ok, so, r) for c, n, e, fo, ok, so, r in PARIS]
        for p in paris:
            if p["cle"] == "KR":
                p.update({"entree_ok": False, "sortie": True, "raisons_sortie": exces, "raisons_refus": exces})
        ev = {"2026-10-12": {"modifs": {("selections", None): {"entreprises": moins_s07}}},
              "2026-10-20": {"modifs": {("selections", None): {"entreprises": moins_s07, "evaluations": paris}}}}
        simuler(executer, f, charger_config(), d / "data", "2026-09-01", args.jours, heures=(15, 21), evenements=ev)
        pf = json.loads((d / "data" / "portefeuille.json").read_text(encoding="utf-8"))["donnees"]
        ops = json.loads((d / "data" / "trader" / "operations.json").read_text(encoding="utf-8"))["donnees"]
        st = pf["statistiques"]
        print(f"Valeur finale : {pf['valeur_actuelle']:,.2f} € ; liquidités {pf['liquidites_pct']} % ; {len(pf['positions'])} positions")
        print("Performance :", st["performance"], "| MSCI World :", st["performance_msci_world"])
        print("Risque :", st["risque"], "| MSCI World :", st["risque_msci_world"])
        print("Opérations :", {k: v for k, v in st["operations"].items() if k != "definition"})
        print("Motifs :", dict(Counter(o["motif"] for o in ops)))
        print("Attribution (poches) :", [(x["libelle"], x["eur"]) for x in st["attribution"]["poches"]])
        print("Poches contre le MSCI World :", {k: (v.get("performance"), v.get("msci_world")) for k, v in st["poches"].items()})
        print("Paris pays :", [(p["symbole"], p["statut"], p.get("performance_pct"), p.get("msci_world_pct")) for p in pf["paris_pays"]])
        print("Frais :", st["attribution"]["frais_eur"], "€ ; écarts achat/vente :", st["attribution"]["ecarts_eur"], "€")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
