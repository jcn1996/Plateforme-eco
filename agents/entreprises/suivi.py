"""
Suivi des recommandations : data/historique/recommandations.json.

    python -m agents.entreprises.suivi [--data DIR] [--date AAAA-MM-JJ] [--sans-reseau]

1. Enregistre les nouvelles recommandations :
   - agent entreprises (data/entreprises.json et fiches) : seulement quand la recommandation d'une société
     change, au plus une fois tous les « intervalle_min_jours » jours ;
   - analyses à la demande (data/analyses/index.json) : chaque analyse.
2. Calcule la performance à 3, 6 et 12 mois de chaque recommandation arrivée à échéance, comparée à l'ETF
   MSCI World (URTH) : cours ajustés des dividendes lus sur Yahoo Finance, sur une même série (rendement total).
3. Calcule le taux de réussite par type de recommandation (règles dans config.json, « recommandation.suivi »).

Ce script est le seul à écrire recommandations.json. Les workflows le lancent juste avant de pousser, sur
l'état le plus récent du dépôt : deux workflows ne peuvent donc pas se contredire sur ce fichier.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..commun.journal import journal
from ..commun.sortie import lire_json

LOG = journal("suivi-recommandations")
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
JOURS_PAR_MOIS = 30.44


def maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fichier_fiche(ticker: str) -> str:
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in ticker) + ".json"


# ------------------------------------------------------------------ enregistrement

def entree(e: dict, source: str, jour: date, issue: int | None = None) -> dict | None:
    """Ligne d'historique à partir d'une fiche (agent entreprises ou analyse à la demande)."""
    r = e.get("recommandation")
    if not r:
        return None
    v = r.get("valeur") or {}
    return {
        "id": f"{source}:{e['ticker']}:{jour.isoformat()}", "date": jour.isoformat(), "source": source,
        "ticker": e["ticker"], "nom": e.get("nom"), "pays": e.get("pays"), "secteur_gics": e.get("secteur_gics"),
        "liste": "pepites" if e.get("pepite") else "qpr" if e.get("qpr") else None, "issue": issue,
        "date_cours": r.get("date_cours") or jour.isoformat(), "cours": r.get("cours"), "devise": r.get("devise"),
        "recommandation": r["si_non_detenu"], "detenu": r["si_detenu"],
        "fourchette": {k: v.get(k) for k in ("bas", "centrale", "haut")} if v else None,
        "ecart_pct": r.get("ecart_pct"), "prix_repli": r.get("prix_repli"),
        "confiance": r.get("confiance"), "note": e.get("note"), "suivi": {},
    }


def enregistrer(historique: list[dict], data: Path, jour: date, cfg: dict) -> int:
    """Ajoute les nouvelles recommandations. Renvoie le nombre d'entrées ajoutées."""
    ids = {h["id"] for h in historique}
    dernieres = {}
    for h in historique:
        if h["source"] == "entreprises":
            dernieres[h["ticker"]] = h
    ajout = []
    legeres = (lire_json(data / "entreprises.json") or {})
    if (legeres.get("meta") or {}).get("fictif") is False:
        for e in legeres.get("donnees") or []:
            r = e.get("recommandation")
            if not r:
                continue
            d = dernieres.get(e["ticker"])
            if d and d["recommandation"] == r.get("n") and d["detenu"] == r.get("d"):
                continue
            if d and (jour - date.fromisoformat(d["date"])).days < cfg["intervalle_min_jours"]:
                continue
            fiche = (lire_json(data / "entreprises" / "fiches" / fichier_fiche(e["ticker"])) or {}).get("donnees")
            x = entree({**(fiche or {}), **e, "recommandation": (fiche or {}).get("recommandation")}, "entreprises", jour)
            if x and x["id"] not in ids:
                ajout.append(x)
                ids.add(x["id"])
    for a in (lire_json(data / "analyses" / "index.json") or {}).get("donnees") or []:
        if a.get("statut", "ok") != "ok" or not a.get("date"):
            continue
        jour_a = date.fromisoformat(a["date"][:10])
        ident = f"demande:{a['ticker']}:{jour_a.isoformat()}"
        if ident in ids:
            continue
        fiche = (lire_json(data / "analyses" / fichier_fiche(a["ticker"])) or {}).get("donnees")
        # La fiche peut avoir été remplacée par une analyse plus récente : on n'enregistre que celle du jour
        if not fiche or (fiche.get("demande") or {}).get("date", "")[:10] != jour_a.isoformat():
            continue
        x = entree(fiche, "demande", jour_a, (fiche.get("demande") or {}).get("issue"))
        if x:
            ajout.append(x)
            ids.add(x["id"])
    historique.extend(ajout)
    return len(ajout)


# ------------------------------------------------------------------ performance

def echeance(h: dict, mois: int) -> date:
    return date.fromisoformat(h["date_cours"]) + timedelta(days=round(mois * JOURS_PAR_MOIS))


def cours_a(serie: list, jour: date) -> float | None:
    """Dernière clôture à la date `jour` ou avant (série [(AAAA-MM-JJ, clôture), …] triée)."""
    avant = [c for d, c, *_ in serie if d <= jour.isoformat()]
    return avant[-1] if avant else None


def a_suivre(historique: list[dict], jour: date, horizons: list[int]) -> list[dict]:
    return [h for h in historique if any(str(m) not in h["suivi"] and echeance(h, m) <= jour for m in horizons)]


def reussite(type_reco: str, perf: float, relative: float, regles: dict) -> bool | None:
    r = regles.get(type_reco)
    if not r:
        return None
    if "relative_min" in r:
        return relative > r["relative_min"]
    if "relative_max" in r:
        return relative < r["relative_max"]
    if "absolue_max" in r:
        return abs(relative) <= r["absolue_max"]
    return None


def mettre_a_jour(historique: list[dict], series: dict, indice: str, jour: date, cfg: dict) -> int:
    """Complète le suivi des recommandations arrivées à échéance. Renvoie le nombre de mesures ajoutées."""
    n = 0
    serie_i = series.get(indice) or []
    for h in historique:
        for m in cfg["horizons_mois"]:
            cle = str(m)
            fin = echeance(h, m)
            if cle in h["suivi"] or fin > jour:
                continue
            debut = date.fromisoformat(h["date_cours"])
            serie = series.get(h["ticker"]) or []
            p0, p1 = cours_a(serie, debut), cours_a(serie, fin)
            i0, i1 = cours_a(serie_i, debut), cours_a(serie_i, fin)
            if not all((p0, p1, i0, i1)):
                if (jour - fin).days > 30:  # cours introuvables un mois après l'échéance : mesure abandonnée
                    h["suivi"][cle] = {"date": fin.isoformat(), "statut": "cours indisponibles"}
                    n += 1
                continue
            perf, perf_i = (p1 / p0 - 1) * 100, (i1 / i0 - 1) * 100
            rel = perf - perf_i
            h["suivi"][cle] = {"date": fin.isoformat(), "perf_pct": round(perf, 1), "indice_pct": round(perf_i, 1),
                               "relative_pct": round(rel, 1),
                               "reussite": reussite(h["recommandation"], perf, rel, cfg["reussite"]),
                               "reussite_detenu": reussite(h["detenu"], perf, rel, cfg["reussite"])}
            n += 1
    return n


def fiabilite(historique: list[dict], cfg: dict) -> dict:
    """Taux de réussite et performance relative moyenne, par type de recommandation et par horizon."""
    res = {"si_non_detenu": {}, "si_detenu": {}, "par_source": {}}
    for lecture, champ, cle_r in (("si_non_detenu", "recommandation", "reussite"), ("si_detenu", "detenu", "reussite_detenu")):
        for h in historique:
            bloc = res[lecture].setdefault(h[champ], {"total": 0, **{str(m): {"n": 0, "reussites": 0, "relatives": []} for m in cfg["horizons_mois"]}})
            bloc["total"] += 1
            for m in cfg["horizons_mois"]:
                s = h["suivi"].get(str(m))
                if s and s.get(cle_r) is not None:
                    b = bloc[str(m)]
                    b["n"] += 1
                    b["reussites"] += 1 if s[cle_r] else 0
                    b["relatives"].append(s["relative_pct"])
    for h in historique:
        b = res["par_source"].setdefault(h["source"], {"total": 0, "mesurees": 0})
        b["total"] += 1
        b["mesurees"] += 1 if any("relative_pct" in s for s in h["suivi"].values()) else 0
    for lecture in ("si_non_detenu", "si_detenu"):
        for bloc in res[lecture].values():
            for m in cfg["horizons_mois"]:
                b = bloc[str(m)]
                rel = b.pop("relatives")
                b["taux_pct"] = round(b["reussites"] / b["n"] * 100) if b["n"] else None
                b["relative_moyenne_pct"] = round(sum(rel) / len(rel), 1) if rel else None
    return res


# ------------------------------------------------------------------ fichier

def lire(chemin: Path) -> list[dict]:
    return (lire_json(chemin) or {}).get("donnees") or []


def ecrire(chemin: Path, historique: list[dict], cfg: dict) -> None:
    """Une recommandation par ligne (différences lisibles dans git), écriture atomique."""
    meta = {"version": 1, "genere_le": maintenant(), "source": "suivi-recommandations", "fictif": False,
            "description": "Recommandations enregistrées (agent entreprises : à chaque changement ; analyses à la demande : chaque analyse) "
                           "et leur performance à 3, 6 et 12 mois comparée au MSCI World",
            "indice": cfg["indice"], "indice_nom": cfg["indice_nom"], "horizons_mois": cfg["horizons_mois"],
            "regles_reussite": cfg["reussite"], "intervalle_min_jours": cfg["intervalle_min_jours"],
            "nombre": len(historique), "fiabilite": fiabilite(historique, cfg)}
    lignes = ",\n".join(json.dumps(h, ensure_ascii=False, separators=(",", ":")) for h in historique)
    texte = '{"meta":' + json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + ',\n"donnees":[\n' + lignes + "\n]}\n"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texte)
    os.replace(tmp, chemin)


def series_yahoo(tickers: list[str]) -> dict:
    from .comptes import Yahoo
    return Yahoo().cours_groupes(sorted(set(tickers)), periode="2y")


def executer(data: Path, jour: date, reseau: bool = True, series_fn=None) -> dict:
    cfg = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))["recommandation"]["suivi"]
    chemin = data / "historique" / "recommandations.json"
    historique = lire(chemin)
    ajout = enregistrer(historique, data, jour, cfg)
    mesures = 0
    attente = a_suivre(historique, jour, cfg["horizons_mois"])
    if attente and (reseau or series_fn):
        try:
            series = (series_fn or series_yahoo)([h["ticker"] for h in attente] + [cfg["indice"]])
            mesures = mettre_a_jour(historique, series, cfg["indice"], jour, cfg)
        except Exception as e:  # Yahoo indisponible : nouvelle tentative au prochain passage
            LOG.warning("Cours de suivi indisponibles : %s", str(e)[:150])
    if ajout or mesures or not chemin.exists():
        ecrire(chemin, historique, cfg)
    LOG.info("Recommandations : %d ajoutées, %d mesures de performance, %d au total", ajout, mesures, len(historique))
    return {"ajoutees": ajout, "mesures": mesures, "total": len(historique)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Suivi des recommandations")
    ap.add_argument("--data", default=str(RACINE / "data"))
    ap.add_argument("--date")
    ap.add_argument("--sans-reseau", action="store_true")
    a = ap.parse_args(argv)
    jour = date.fromisoformat(a.date) if a.date else datetime.now(timezone.utc).date()
    executer(Path(a.data), jour, reseau=not a.sans_reseau)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
