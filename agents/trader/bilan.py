"""
Point mensuel automatique (« Bilan du mois ») et portefeuille de référence « momentum seul ».

- Momentum seul : référence simple du backtest (agents/backtest/reference.py), suivie en conditions réelles depuis le
  16/11/2026 : à chaque début de mois, les 20 % de sociétés les plus fortes sur 12 mois hors dernier mois, à parts
  égales, dans l'univers du backtest (sociétés américaines non financières, hors immobilier et holdings, capitalisation
  d'au moins 2 Md$ ; liste de l'agent entreprises). Cours hebdomadaires des fiches de l'agent entreprises (dividendes non
  réinvestis), sans frais. Rien n'est acheté : c'est un étalon.
- Bilan du mois (data/bilan/AAAA-MM.json et data/bilan/index.json), écrit à la première exécution du trader de chaque
  mois pour le mois écoulé : performance du portefeuille démo, du MSCI World (en euros) et du portefeuille momentum seul,
  sur le mois et depuis le 16/11/2026 ; entrées et sorties de la liste du chef d'orchestre ; taux de réussite des signaux
  en observation (part qui bat le MSCI World à 1 mois).
Aucune donnée inventée : une valeur manquante est publiée à null avec la raison.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from ..commun.sortie import ecrire_json, enveloppe, lire_json

DEBUT = "2026-11-16"
QUANTILE = 0.2


# ------------------------------------------------------------------ cours hebdomadaires

def _points(serie) -> list[tuple[str, float]]:
    res = []
    for p in serie or []:
        try:
            res.append((str(p[0])[:10], float(p[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return sorted(res)


def cours_au(serie, jour: str) -> float | None:
    """Dernier cours connu au plus tard à `jour` (AAAA-MM-JJ)."""
    v = None
    for d, x in _points(serie):
        if d > jour:
            break
        v = x
    return v


def momentum_12_1(serie, jour: str) -> float | None:
    t = date.fromisoformat(jour)
    debut = cours_au(serie, (t - timedelta(days=365)).isoformat())
    fin = cours_au(serie, (t - timedelta(days=30)).isoformat())
    pts = _points(serie)
    if not debut or not fin or not pts or pts[0][0] > (t - timedelta(days=358)).isoformat():
        return None
    return fin / debut - 1


# ------------------------------------------------------------------ univers et portefeuille momentum seul

def univers(data: Path, cfg_sel: dict) -> list[dict]:
    ce = cfg_sel["entreprises"]
    res = []
    for e in (lire_json(Path(data) / "entreprises.json") or {}).get("donnees") or []:
        if not isinstance(e, dict) or e.get("pays") not in ce["pays"] or e.get("financier") or e.get("holding"):
            continue
        if e.get("secteur_gics") in ce["secteurs_exclus"] or (e.get("capitalisation_md") or 0) < ce["capitalisation_min_md"]:
            continue
        res.append(e)
    return res


def series(data: Path, societes: list[dict]) -> dict[str, list]:
    res = {}
    for e in societes:
        chemin = e.get("fiche")
        f = (lire_json(Path(data) / chemin.removeprefix("data/")) or {}).get("donnees") if chemin else None
        if f and f.get("cours_hebdo"):
            res[e["ticker"]] = f["cours_hebdo"]
    return res


def composer(series_: dict[str, list], jour: str) -> dict[str, float]:
    """Meilleurs 20 % sur 12 mois hors dernier mois au `jour` : {ticker: cours de départ}."""
    moms = {t: m for t, s in series_.items() if (m := momentum_12_1(s, jour)) is not None and cours_au(s, jour)}
    if not moms:
        return {}
    n = max(1, int(len(moms) * QUANTILE))
    retenus = sorted(moms, key=lambda t: -moms[t])[:n]
    return {t: cours_au(series_[t], jour) for t in retenus}


def valeur_panier(compo: dict[str, float], series_: dict[str, list], jour: str) -> float | None:
    """Rendement moyen (parts égales) du panier depuis sa composition, au `jour`."""
    r = [cours_au(series_.get(t), jour) / p - 1 for t, p in compo.items() if p and cours_au(series_.get(t), jour)]
    return sum(r) / len(r) if r else None


def suivre_momentum(etat: dict, data: Path, cfg_sel: dict, jour: str) -> dict:
    """Met à jour etat["momentum_seul"] : {debut, base, mois: {AAAA-MM: {date, valeur_depart, composition}}, historique}."""
    if jour < DEBUT:
        return etat.get("momentum_seul") or {}
    m = etat.setdefault("momentum_seul", {"debut": DEBUT, "base": 100.0, "mois": {}, "historique": {}})
    s = None
    mois = jour[:7]
    if mois not in m["mois"]:
        s = series(data, univers(data, cfg_sel))
        depart_jour = DEBUT if not m["mois"] else jour
        precedent = m["historique"][max(m["historique"])] if m["historique"] else m["base"]
        compo = composer(s, depart_jour)
        m["mois"][mois] = {"date": depart_jour, "valeur_depart": precedent, "composition": compo, "societes": len(compo),
                           "univers": len(s)}
    courant = m["mois"][mois]
    if courant["composition"]:
        if s is None:
            s = series(data, [{"ticker": t, "fiche": f"data/entreprises/fiches/{t}.json"} for t in courant["composition"]])
        r = valeur_panier(courant["composition"], s, jour)
        if r is not None:
            m["historique"][jour] = round(courant["valeur_depart"] * (1 + r), 4)
    return m


# ------------------------------------------------------------------ bilan du mois

def _perf(historique: dict[str, float], debut: str, fin: str) -> float | None:
    """Performance (%) entre la dernière valeur connue au plus tard à `debut` (ou la première après) et à `fin`."""
    dates = sorted(d for d, v in historique.items() if v is not None)
    if not dates:
        return None
    avant = [d for d in dates if d <= debut]
    d0 = avant[-1] if avant else next((d for d in dates if d >= debut), None)
    fins = [d for d in dates if d <= fin]
    if not d0 or not fins or fins[-1] <= d0:
        return None
    return round((historique[fins[-1]] / historique[d0] - 1) * 100, 2)


def _fin_mois(mois: str) -> str:
    a, m = int(mois[:4]), int(mois[5:7])
    suivant = date(a + (m == 12), 1 if m == 12 else m + 1, 1)
    return (suivant - timedelta(days=1)).isoformat()


def mouvements_du_mois(chef: dict | None, mois: str) -> list[dict] | None:
    li = (chef or {}).get("liste") or {}
    if li.get("mois") == mois:
        return [m for m in li.get("mouvements") or [] if m.get("date", "")[:7] == mois]
    p = li.get("mois_precedent") or {}
    if p.get("mois") == mois:
        return p.get("mouvements") or []
    return None


def reussite_observation(obs: dict | None) -> dict:
    res = {}
    for cle, r in ((obs or {}).get("resume") or {}).items():
        h = (r.get("horizons") or {}).get("1") or {}
        res[cle] = {"libelle": r.get("libelle", cle), "enregistres": r.get("enregistres"), "mesures_1m": h.get("n", 0),
                    "battent_indice_pct": h.get("battent_indice_pct"), "ecart_moyen_points": h.get("ecart_moyen_points")}
    return res


def construire_bilan(etat: dict, chef: dict | None, obs: dict | None, mois: str, genere_le: str) -> dict:
    fin = _fin_mois(mois)
    debut_mois = (date.fromisoformat(f"{mois}-01") - timedelta(days=1)).isoformat()  # dernière valeur du mois précédent
    h = etat.get("historique") or {}
    pf = {d: x.get("portefeuille") for d, x in h.items()}
    msci = {d: x.get("msci_world") for d, x in h.items()}
    mom = (etat.get("momentum_seul") or {}).get("historique") or {}
    if mom:
        mom = {DEBUT: (etat.get("momentum_seul") or {}).get("base", 100.0), **mom}

    def bloc(serie, nom):
        return {"nom": nom, "mois_pct": _perf(serie, max(debut_mois, DEBUT), fin), "depuis_debut_pct": _perf(serie, DEBUT, fin)}
    mvts = mouvements_du_mois(chef, mois)
    return {
        "mois": mois, "genere_le": genere_le, "debut_reference": DEBUT,
        "performances": [bloc(pf, "Portefeuille démo (trader)"), bloc(msci, "MSCI World (en euros)"),
                         bloc(mom, "Portefeuille « momentum seul »")],
        "liste": {"entrees": [m for m in mvts or [] if m.get("sens") == "entrée"], "sorties": [m for m in mvts or [] if m.get("sens") == "sortie"],
                  "disponible": mvts is not None,
                  "raison": None if mvts is not None else "mouvements du mois introuvables dans la sortie du chef d'orchestre"},
        "observation": reussite_observation(obs),
        "momentum_seul": {k: v for k, v in ((etat.get("momentum_seul") or {}).get("mois") or {}).get(mois, {}).items() if k != "composition"},
        "methode": ("Performances sur le mois (de la dernière valeur du mois précédent à la dernière du mois) et depuis le 16/11/2026. "
                    "Momentum seul : 20 % de sociétés les plus fortes sur 12 mois hors dernier mois, parts égales, recomposé chaque "
                    "mois, cours hebdomadaires sans dividendes ni frais (étalon, rien n'est acheté). Signaux en observation : part "
                    "des signaux mesurés à 1 mois qui battent le MSCI World."),
        "mention": "Portefeuille fictif à but de démonstration, aucun ordre réel.",
    }


def ecrire_bilan_si_du(etat: dict, data: Path, chef: dict | None, obs: dict | None, maintenant: datetime) -> Path | None:
    """À la première exécution d'un nouveau mois : bilan du mois écoulé (une seule fois)."""
    jour = maintenant.date().isoformat()
    mois_ecoule = (date.fromisoformat(f"{jour[:7]}-01") - timedelta(days=1)).isoformat()[:7]
    if mois_ecoule < DEBUT[:7] or etat.get("bilan_dernier_mois") == mois_ecoule:
        return None
    if not any(d[:7] == mois_ecoule for d in etat.get("historique") or {}):
        return None
    b = construire_bilan(etat, chef, obs, mois_ecoule, maintenant.replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    dossier = Path(data) / "bilan"
    chemin = dossier / f"{mois_ecoule}.json"
    ecrire_json(chemin, enveloppe(b, "agent-trader", fictif=False, description="Bilan du mois (portefeuille démo, MSCI World, momentum seul, liste, signaux en observation)"))
    index = (lire_json(dossier / "index.json") or {}).get("donnees") or []
    index = sorted({*index, mois_ecoule}, reverse=True)
    ecrire_json(dossier / "index.json", enveloppe(index, "agent-trader", fictif=False, description="Mois disponibles dans data/bilan/"))
    etat["bilan_dernier_mois"] = mois_ecoule
    return chemin


def config_selections(racine: Path) -> dict:
    return json.loads((Path(racine) / "agents" / "chef" / "config.json").read_text(encoding="utf-8"))["selections"]
