"""
Capture des données de test à partir des vraies sources (à lancer à la main, rarement) :
    python -m agents.pays.tests.capturer_donnees_test
Les séries sont allégées (pays suivis, années récentes, cours un point sur cinq + les derniers jours)
pour garder des fichiers petits. Une source en échec lors de la capture n'écrit pas de fichier :
le test correspondant la verra alors « en panne ».
"""
import json
from datetime import date
from pathlib import Path

from ..agent import BM_SERIES, RACINE, _cle_nationale, collecter
from ..sources import FournisseurReel

DOSSIER = Path(__file__).resolve().parent / "donnees"


def main():
    config = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
    aujourdhui = date.today()
    src, etats = collecter(FournisseurReel(RACINE / "agents" / ".cache"), config, aujourdhui)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    iso3 = {p["iso3"] for p in config["pays"].values()}
    recent = str(aujourdhui.year - 3)
    annuel = lambda d: {k: {a: x for a, x in v.items() if a >= recent} for k, v in d.items() if k in iso3}
    quotidien = lambda v: sorted(dict(v[::5] + v[-5:]).items())  # sans doublon, dans l'ordre
    fichiers = {
        "fmi_NGDP_RPCH": ("fmi_croissance", annuel), "fmi_PCPIPCH": ("fmi_inflation", annuel), "fmi_BCA_NGDPD": ("fmi_solde_courant", annuel),
        "ocde_cli": ("ocde_cli", None), "ocde_inflation": ("ocde_inflation", None), "ocde_eo": ("ocde_eo", None), "bis": ("bis", None),
        "eurostat": ("eurostat", None), "bce_taux": ("bce_taux", None),
        "bce_change": ("bce_change", lambda d: {k: quotidien(v) for k, v in d.items()}),
        "cours": ("yahoo_cours", lambda d: {k: quotidien(v) for k, v in d.items()}), "per": ("yahoo_per", None),
        "flux_yahoo_parts": ("flux_yahoo_parts", None),
    }
    # Flux des ETF pays : relevés des émetteurs (historiques publiés limités aux 70 derniers relevés)
    court = lambda d: {k: {**r, "historique": (r.get("historique") or [])[-70:]} if r.get("historique") else r for k, r in d.items()}
    for emetteur in ("ishares", "ssga", "vaneck", "globalx"):
        fichiers[f"flux_{emetteur}"] = (f"flux_{emetteur}", court)
    for nom, serie in BM_SERIES.items():
        fichiers[f"bm_{serie}"] = (nom, annuel)
    for code, liste in config["sources_nationales"].items():
        for s in ([] if code.startswith("_") else liste):
            nom = f"{s['fournisseur']}_{str(s['serie']).replace('/', '_')}"
            fichiers[nom] = (_cle_nationale(s), lambda v: [x for x in v if str(x[0]) >= recent])
    for nom, (cle, alleger) in fichiers.items():
        if src.get(cle) is None:
            print("Source en échec, fichier non écrit :", nom)
            continue
        contenu = alleger(src[cle]) if alleger else src[cle]
        (DOSSIER / f"{nom}.json").write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    print("Données de test écrites dans", DOSSIER, etats)


if __name__ == "__main__":
    main()
