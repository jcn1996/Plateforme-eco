"""Données de test de l'agent trader, construites de toutes pièces (jamais lues dans les vrais config/ et data/) :
sortie réduite du chef d'orchestre, agent risque, agent marchés, journaux, et une simulation jour par jour."""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PAYS = [("US", "États-Unis", "SPY", 58, "Renforcer", "moyenne"), ("JP", "Japon", "EWJ", 62, "Renforcer", "forte"),
        ("KR", "Corée du Sud", "EWY", 63, "Renforcer", "forte"), ("DE", "Allemagne", "EWG", 52, "Neutre", "moyenne"),
        ("IN", "Inde", "INDA", 57, "Renforcer", "moyenne"), ("BR", "Brésil", "EWZ", 41, "Alléger", "moyenne"),
        ("EG", "Égypte", None, 55, "Renforcer", "faible")]
ENTREPRISES = [
    # ticker, nom, pays, secteur, score, verdict, conviction, objection sérieuse, agents favorables
    ("AAA", "Alpha Assurances", "US", "Financials", 72, "Renforcer fortement", "forte", False, ("entreprises", "pays", "inities")),
    ("BBB", "Beta Industrie", "US", "Industrials", 68, "Renforcer", "forte", False, ("entreprises", "pays")),
    ("CCC.T", "Gamma Japon", "JP", "Consumer Discretionary", 66, "Renforcer", "moyenne", False, ("entreprises", "macro")),
    ("DDD.L", "Delta Londres", "GB", "Energy", 65, "Renforcer", "moyenne", False, ("entreprises", "pays")),
    ("EEE", "Epsilon Momentum", "US", "Information Technology", 70, "Renforcer fortement", "moyenne", True, ("entreprises", "pays")),
    ("FFF", "Phi Source Unique", "US", "Health Care", 69, "Renforcer", "forte", False, ("entreprises",)),
    ("GGG", "Gamma Faible", "US", "Materials", 64, "Renforcer", "faible", False, ("entreprises", "pays")),
    ("HHH", "Eta Neutre", "US", "Utilities", 50, "Neutre", "moyenne", False, ("entreprises", "pays")),
]


def _familles(agents_pour, score):
    noms = {"entreprises": ("fondamentaux", "Fondamentaux"), "pays": ("flux", "Flux d'investissement"), "macro": ("cycle", "Adéquation au cycle"),
            "inities": ("inities", "Initiés et super-investisseurs"), "risque": ("risque", "Risque"), "geopolitique": ("geopolitique", "Géopolitique")}
    res = {}
    for a, (cle, lib) in noms.items():
        note = 75 if a in agents_pour else 45
        res[cle] = {"libelle": lib, "note": note, "agent": a, "texte": f"{lib} (test)", "source": f"agent {a}"}
    return res


def ligne(id_, type_, nom, score, verdict, conviction, symbole=None, objection=False, agents=("pays", "macro"), **extra):
    l = {"id": id_, "type": type_, "nom": nom, "score": score, "verdict": verdict, "conviction": conviction, "themes": [],
         "familles": _familles(agents, score), "pour": [{"cle": "fondamentaux", "famille": "Fondamentaux", "note": 75}],
         "objection": {"objection": f"Objection de test sur {nom}.", "serieuse": True} if objection else None,
         "donner_tort": [f"Réserve de test sur {nom}."]}
    if symbole:
        l["symbole"] = symbole
    l.update(extra)
    return l


def chef(jour: str, modifs: dict | None = None) -> dict:
    pays = [ligne(f"pays-{c}", "pays", n, s, v, cv, sym, cle=c, pays=c) for c, n, sym, s, v, cv in PAYS]
    ent = [ligne(f"entreprise-{t}", "entreprises", n, s, v, cv, t, obj, ag, cle=t, pays=p, secteur=sec, secteur_nom=sec,
                 devise={"US": "USD", "JP": "JPY", "GB": "GBP"}[p]) for t, n, p, sec, s, v, cv, obj, ag in ENTREPRISES]
    matieres = [ligne("matiere-brent", "matieres", "Pétrole Brent", 61, "Renforcer", "faible", "BZ=F", themes=["petrole"]),
                ligne("matiere-cacao", "matieres", "Cacao", 50, "Neutre", "faible", "CC=F")]
    or_ = ligne("or", "or", "Or", 55, "Neutre", "moyenne", "GC=F", themes=["or"])
    obligs = [ligne("oblig-us-courtes", "obligations", "Obligations US courtes", 50, "Neutre", "moyenne", "SHY"),
              ligne("oblig-us-longues", "obligations", "Obligations US longues", 53, "Neutre", "faible", "TLT"),
              ligne("oblig-euro-courtes", "obligations", "Obligations euro courtes", 48, "Neutre", "moyenne", "IBGS.AS"),
              ligne("oblig-euro-longues", "obligations", "Obligations euro longues", 35, "Alléger", "forte", "IBGL.AS")]
    liqs = [ligne("liquidites-eur", "liquidites", "Liquidités en euros", 50, "Neutre", "moyenne", "XEON.DE")]
    alloc_lignes = [
        ("pays-US", "actions", 14), ("pays-JP", "actions", 9), ("pays-KR", "actions", 8), ("pays-DE", "actions", 6), ("pays-IN", "actions", 5),
        ("pays-EG", "actions", 3), ("oblig-us-courtes", "obligations", 10), ("oblig-us-longues", "obligations", 10),
        ("oblig-euro-courtes", "obligations", 6), ("or", "or", 5), ("matiere-brent", "matieres", 3), ("matiere-cacao", "matieres", 1),
        ("liquidites-eur", "liquidites", 7), ("entreprise-AAA", "actions", 2.5), ("entreprise-BBB", "actions", 2.5)]
    d = {"date": jour, "mode": "complet", "maj": f"{jour}T07:15:00Z", "regime": {"palier": "Vigilance"},
         "pays": pays, "matieres": matieres, "or": or_, "obligations": obligs, "liquidites": liqs, "entreprises": ent,
         "entrees": [{"cle": a, "etat": "à jour", "degrade": False} for a in ("pays", "macro", "risque", "entreprises", "inities", "geopolitique")],
         "allocation": {"palier": "Vigilance", "contraintes": {"max_pays": 40, "max_secteur": 12, "max_theme": 20},
                        "profils": {"equilibre": {"libelle": "Équilibré", "lignes": [
                            {"id": i, "nom": i, "classe": c, "poche": "satellite" if i.startswith("entreprise") else "cœur", "poids": p}
                            for i, c, p in alloc_lignes]}}}}
    for (type_, id_), champs in (modifs or {}).items():
        cible = [d[type_]] if type_ == "or" else d[type_]
        for l in cible:
            if l["id"] == id_:
                l.update(champs)
    return d


def journal_sain(agent: str, maintenant: datetime, degrade: bool = False) -> dict:
    return {"meta": {"sante": {"agent": agent, "degrade": degrade, "raisons": ["source de test en échec"] if degrade else [],
                               "derniere_execution": maintenant.replace(microsecond=0).isoformat().replace("+00:00", "Z")}}, "donnees": []}


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def preparer(data: Path, maintenant: datetime, palier: str = "Vigilance", modifs: dict | None = None, age_chef_h: float = 0.3,
             chef_degrade: bool = False, analyse_du_jour: bool = True) -> None:
    """Écrit dans `data` les entrées de l'agent trader pour l'instant `maintenant`."""
    data.mkdir(parents=True, exist_ok=True)
    jour = maintenant.date().isoformat()
    c = {"meta": {"genere_le": iso(maintenant - timedelta(hours=age_chef_h)), "source": "agent-chef"}, "donnees": chef(jour, modifs)}
    (data / "chef.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    r = {"meta": {"genere_le": iso(maintenant - timedelta(hours=2)), "source": "agent-risque"},
         "donnees": {"mondial": {"palier": palier, "score": 60}}}
    (data / "risque.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    m = {"meta": {"genere_le": iso(maintenant - timedelta(hours=40))}, "donnees": []}  # agent marchés périmé : Yahoo (simulé) prend le relais
    (data / "marches.json").write_text(json.dumps(m), encoding="utf-8")
    (data / "journal").mkdir(parents=True, exist_ok=True)
    for a in ("chef", "risque", "marches"):
        j = journal_sain(a, maintenant, degrade=(a == "chef" and chef_degrade))
        (data / "journal" / f"agent-{a}.json").write_text(json.dumps(j), encoding="utf-8")
    h = data / "historique" / "chef" / f"{jour}.json"
    if analyse_du_jour:
        h.parent.mkdir(parents=True, exist_ok=True)
        h.write_text("{}", encoding="utf-8")
    elif h.exists():
        h.unlink()


def simuler(executer, f, config: dict, data: Path, debut: str, jours: int, heures=(15, 18, 21), evenements=None) -> list[dict]:
    """Simulation jour par jour : décision à 7 h 33 UTC puis contrôles horaires, chaque jour de semaine.
    evenements = {date ISO: {"palier": …, "modifs": {…}}} : changements appliqués ce jour-là et après."""
    etat_sim = {"palier": "Vigilance", "modifs": {}}
    res = []
    d = date.fromisoformat(debut)
    for _ in range(jours):
        if d.weekday() < 5:
            ev = (evenements or {}).get(d.isoformat()) or {}
            etat_sim["palier"] = ev.get("palier", etat_sim["palier"])
            etat_sim["modifs"] = {**etat_sim["modifs"], **ev.get("modifs", {})}
            t = datetime(d.year, d.month, d.day, 7, 33, tzinfo=timezone.utc)
            preparer(data, t, etat_sim["palier"], copy.deepcopy(etat_sim["modifs"]))
            res.append(executer(f, config, data, t, "decision"))
            for h in heures:
                t = datetime(d.year, d.month, d.day, h, 5, tzinfo=timezone.utc)
                preparer(data, t, etat_sim["palier"], copy.deepcopy(etat_sim["modifs"]))
                res.append(executer(f, config, data, t, "horaire"))
        d += timedelta(days=1)
    return res
