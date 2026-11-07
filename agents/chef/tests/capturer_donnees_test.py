"""Met à jour les données de test du chef d'orchestre à partir des vrais fichiers data/ (copie allégée).

    python -m agents.chef.tests.capturer_donnees_test

Seul ce script lit les vrais data/ : les tests, eux, n'utilisent que agents/chef/tests/donnees/.
La copie garde tous les pays, matières premières, signaux et revues, mais seulement une partie des entreprises
(pépites, liste de surveillance, analyses, 6 meilleures de chaque pays, sociétés citées dans les revues) et des
fiches réduites aux champs lus par le chef d'orchestre.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
SOURCE = RACINE / "data"
CIBLE = Path(__file__).resolve().parent / "donnees" / "data"
CHAMPS_FICHE = ("dynamique", "recommandation", "alertes", "contre_scenario", "industrie")


def lire(chemin):
    return json.loads(chemin.read_text(encoding="utf-8"))


def ecrire(chemin, objet):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main():
    if CIBLE.exists():
        shutil.rmtree(CIBLE)
    for nom in ("pays.json", "macro.json", "marches.json", "risque.json", "pepites.json", "analyses/index.json"):
        ecrire(CIBLE / nom, lire(SOURCE / nom))
    geo = lire(SOURCE / "geopolitique.json")
    geo["donnees"]["evenements"] = geo["donnees"]["evenements"][:20]
    ecrire(CIBLE / "geopolitique.json", geo)
    mp = lire(SOURCE / "matieres_premieres.json")
    for m in mp["donnees"]["matieres"]:
        m.pop("serie", None)
        if (m.get("sous_notes") or {}).get("positionnement"):
            m["sous_notes"]["positionnement"].pop("historique", None)
    ecrire(CIBLE / "matieres_premieres.json", mp)
    etat = lire(SOURCE / "risque" / "etat.json")
    ecrire(CIBLE / "risque" / "etat.json", {"lentes": {"series": {k: v for k, v in etat["lentes"]["series"].items() if k in ("taux:DE", "taux:US")}}})
    for f in (SOURCE / "signaux").glob("*.json"):
        ecrire(CIBLE / "signaux" / f.name, lire(f))
    ent = lire(SOURCE / "entreprises.json")
    pep = {x["ticker"] for x in lire(SOURCE / "pepites.json")["donnees"]}
    ana = {x["ticker"] for x in lire(SOURCE / "analyses" / "index.json")["donnees"]}
    revues = {r["signal"]["cle"] for r in lire(SOURCE / "signaux" / "revues.json")["donnees"]}
    garde = set(pep | ana | revues)
    par_pays = {}
    for e in sorted(ent["donnees"], key=lambda e: -(e.get("note") or 0)):
        par_pays.setdefault(e["pays"], []).append(e["ticker"])
        if e.get("surveillance"):
            garde.add(e["ticker"])
    for l in par_pays.values():
        garde |= set(l[:6])
    ent["donnees"] = [e for e in ent["donnees"] if e["ticker"] in garde]
    ecrire(CIBLE / "entreprises.json", ent)
    for e in ent["donnees"]:
        chemin = SOURCE / e["fiche"].removeprefix("data/")
        if chemin.exists():
            f = lire(chemin)
            f["donnees"] = {k: f["donnees"].get(k) for k in CHAMPS_FICHE}
            r = f["donnees"].get("recommandation") or {}
            f["donnees"]["recommandation"] = {k: r.get(k) for k in ("cours", "devise", "date_cours", "ecart_pct")} | {"valeur": {"fiable": (r.get("valeur") or {}).get("fiable")}}
            d = f["donnees"].get("dynamique") or {}
            f["donnees"]["dynamique"] = {k: d.get(k) for k in ("note", "fiabilite", "texte")} if d else None
            ecrire(CIBLE / e["fiche"].removeprefix("data/"), f)
    ini = lire(SOURCE / "inities.json")
    ini["donnees"] = {"societes": {k: v for k, v in ini["donnees"]["societes"].items() if k in garde}}
    ecrire(CIBLE / "inities.json", ini)
    for f in ("agent-pays.json", "agent-macro.json", "agent-marches.json", "agent-risque.json", "agent-geopolitique.json",
              "agent-matieres-premieres.json", "agent-entreprises.json", "agent-inities.json", "analyse-demande.json"):
        j = lire(SOURCE / "journal" / f)
        ecrire(CIBLE / "journal" / f, {"meta": {"sante": (j.get("meta") or {}).get("sante")}, "donnees": []})
    print(f"{len(ent['donnees'])} entreprises ; données de test dans {CIBLE}")


if __name__ == "__main__":
    main()
