"""
Suivi de performance des verdicts du chef d'orchestre : data/chef/suivi.json.

- Chaque verdict (pays, matières premières, or, obligations, liquidités, entreprises) est enregistré au
  premier verdict et à chaque changement, avec la date, le score, la conviction, le symbole suivi et son
  prix de référence quand il est connu (données des agents) ;
- à 1, 3, 6 et 12 mois : performance du symbole et de l'indice de référence de sa classe (MSCI World pour
  les actions, indice large des matières premières, obligations américaines ou en euros), cours ajustés
  lus sur Yahoo Finance (rendement total), performance relative et réussite selon le verdict ;
- taux de réussite par type d'opportunité, par verdict et par niveau de conviction, et calibration :
  une conviction forte doit réussir plus souvent qu'une moyenne, elle-même plus qu'une faible.
Ces résultats alimenteront l'agent calibrateur.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from ..commun.sortie import lire_json, maintenant_iso

JOURS_PAR_MOIS = 30.44
CONVICTIONS = ["faible", "moyenne", "forte"]


def indice_de(o: dict, cfg: dict) -> str:
    return cfg["indices"].get(o.get("indice_suivi") or o["type"], cfg["indices"]["pays"])


def enregistrer(historique: list[dict], lignes: list[dict], jour: str, cfg: dict) -> int:
    """Ajoute une entrée pour chaque premier verdict ou changement de verdict du jour."""
    deja = {(h["opportunite"], h["date"]) for h in historique}
    dernier = {}
    for h in historique:
        dernier[h["opportunite"]] = h
    n = 0
    for l in lignes:
        if not l.get("symbole") or l.get("score") is None:
            continue
        prec = dernier.get(l["id"])
        if prec and prec["verdict"] == l["verdict"]:
            continue
        if (l["id"], jour) in deja:
            # même jour : on remplace l'entrée (verdict révisé par une mise à jour légère)
            for h in historique:
                if h["opportunite"] == l["id"] and h["date"] == jour:
                    h.update({"verdict": l["verdict"], "conviction": l.get("conviction"), "score": l["score"]})
            continue
        historique.append({"id": f"{l['id']}:{jour}", "opportunite": l["id"], "type": l["type"], "nom": l["nom"], "date": jour,
                           "verdict": l["verdict"], "conviction": l.get("conviction"), "score": l["score"], "symbole": l["symbole"],
                           "indice": indice_de(l, cfg), "cours": l.get("cours"), "date_cours": l.get("date_cours") or jour, "suivi": {}})
        n += 1
    return n


def echeance(h: dict, mois: int) -> date:
    return date.fromisoformat(h["date"]) + timedelta(days=round(mois * JOURS_PAR_MOIS))


def cours_a(serie: list, jour: date) -> float | None:
    avant = [c for d, c, *_ in serie if d <= jour.isoformat()]
    return avant[-1] if avant else None


def a_mesurer(historique: list[dict], jour: date, cfg: dict) -> list[dict]:
    return [h for h in historique if any(str(m) not in h["suivi"] and echeance(h, m) <= jour for m in cfg["horizons_mois"])]


def reussite(verdict: str, rel: float, regles: dict) -> bool | None:
    r = regles.get(verdict)
    if not r:
        return None
    if "relative_min" in r:
        return rel > r["relative_min"]
    if "relative_max" in r:
        return rel < r["relative_max"]
    if "absolue_max" in r:
        return abs(rel) <= r["absolue_max"]
    return None


def mesurer(historique: list[dict], series: dict, jour: date, cfg: dict) -> int:
    n = 0
    for h in historique:
        for m in cfg["horizons_mois"]:
            cle, fin = str(m), echeance(h, m)
            if cle in h["suivi"] or fin > jour:
                continue
            debut = date.fromisoformat(h["date"])
            s, si = series.get(h["symbole"]) or [], series.get(h["indice"]) or []
            p0, p1, i0, i1 = cours_a(s, debut), cours_a(s, fin), cours_a(si, debut), cours_a(si, fin)
            if not all((p0, p1, i0, i1)):
                if (jour - fin).days > cfg["abandon_jours"]:
                    h["suivi"][cle] = {"date": fin.isoformat(), "statut": "cours indisponibles"}
                    n += 1
                continue
            perf, perf_i = (p1 / p0 - 1) * 100, (i1 / i0 - 1) * 100
            rel = perf - perf_i
            h["suivi"][cle] = {"date": fin.isoformat(), "perf_pct": round(perf, 1), "indice_pct": round(perf_i, 1), "relative_pct": round(rel, 1),
                               "reussite": reussite(h["verdict"], rel, cfg["reussite"])}
            n += 1
    return n


def _bloc(cfg):
    return {"total": 0, **{str(m): {"n": 0, "reussites": 0, "rel": []} for m in cfg["horizons_mois"]}}


def fiabilite(historique: list[dict], cfg: dict) -> dict:
    res = {"par_type": {}, "par_verdict": {}, "par_conviction": {}}
    for h in historique:
        for axe, cle in (("par_type", h["type"]), ("par_verdict", h["verdict"]), ("par_conviction", h.get("conviction") or "faible")):
            b = res[axe].setdefault(cle, _bloc(cfg))
            b["total"] += 1
            for m in cfg["horizons_mois"]:
                s = h["suivi"].get(str(m))
                if s and s.get("reussite") is not None:
                    b[str(m)]["n"] += 1
                    b[str(m)]["reussites"] += 1 if s["reussite"] else 0
                    b[str(m)]["rel"].append(s["relative_pct"])
    for axe in res.values():
        for b in axe.values():
            for m in cfg["horizons_mois"]:
                x = b[str(m)]
                rel = x.pop("rel")
                x["taux_pct"] = round(x["reussites"] / x["n"] * 100) if x["n"] else None
                x["relative_moyenne_pct"] = round(sum(rel) / len(rel), 1) if rel else None
    res["calibration"] = calibration(res["par_conviction"], cfg)
    return res


def calibration(par_conviction: dict, cfg: dict) -> dict:
    """Pour chaque horizon : taux de réussite par conviction et verdict « correcte » si forte ≥ moyenne ≥ faible
    (seulement quand chaque niveau a au moins `min_mesures_calibration` mesures)."""
    res = {}
    mini = cfg["min_mesures_calibration"]
    for m in cfg["horizons_mois"]:
        taux = {c: (par_conviction.get(c) or {}).get(str(m), {}).get("taux_pct") for c in CONVICTIONS}
        n = {c: (par_conviction.get(c) or {}).get(str(m), {}).get("n", 0) for c in CONVICTIONS}
        presents = [c for c in CONVICTIONS if n[c] >= mini and taux[c] is not None]
        if len(presents) < 2:
            statut, texte = "insuffisant", f"Moins de {mini} mesures pour au moins deux niveaux de conviction : calibration non mesurable."
        else:
            ordre = [taux[c] for c in presents]
            ok = all(a <= b for a, b in zip(ordre, ordre[1:]))
            statut = "correcte" if ok else "à revoir"
            texte = ("Une conviction plus forte réussit plus souvent : calibration correcte." if ok
                     else "Une conviction plus forte ne réussit pas plus souvent : calibration à revoir (agent calibrateur).")
        res[str(m)] = {"taux": taux, "n": n, "statut": statut, "texte": texte}
    return res


def lire(chemin: Path) -> list[dict]:
    return (lire_json(chemin) or {}).get("donnees") or []


def ecrire(chemin: Path, historique: list[dict], cfg: dict) -> dict:
    fia = fiabilite(historique, cfg)
    meta = {"version": 1, "genere_le": maintenant_iso(), "source": "agent-chef", "fictif": False,
            "description": "Verdicts du chef d'orchestre (premier verdict et chaque changement) et leur performance à 1, 3, 6 et 12 mois contre l'indice de référence de leur classe",
            "horizons_mois": cfg["horizons_mois"], "indices": cfg["indices"], "indices_noms": cfg["indices_noms"],
            "regles_reussite": cfg["reussite"], "nombre": len(historique), "fiabilite": fia}
    lignes = ",\n".join(json.dumps(h, ensure_ascii=False, separators=(",", ":")) for h in historique)
    texte = '{"meta":' + json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + ',\n"donnees":[\n' + lignes + "\n]}\n"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texte)
    os.replace(tmp, chemin)
    return fia


def executer(data: Path, lignes: list[dict], jour: str, cfg: dict, series_fn=None) -> dict:
    chemin = data / "chef" / "suivi.json"
    historique = lire(chemin)
    ajout = enregistrer(historique, lignes, jour, cfg)
    mesures, erreur = 0, None
    attente = a_mesurer(historique, date.fromisoformat(jour), cfg)
    if attente and series_fn:
        try:
            symboles = sorted({h["symbole"] for h in attente} | {h["indice"] for h in attente})
            mesures = mesurer(historique, series_fn(symboles), date.fromisoformat(jour), cfg)
        except Exception as e:  # noqa: BLE001 — Yahoo indisponible : nouvel essai au prochain passage
            erreur = str(e)[:200]
    fia = ecrire(chemin, historique, cfg)
    return {"ajoutes": ajout, "mesures": mesures, "en_attente": len(attente), "total": len(historique), "erreur": erreur, "fiabilite": fia}
