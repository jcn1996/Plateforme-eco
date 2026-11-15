"""
Signaux en observation (écran « Signaux en observation ») : enregistrés chaque jour, JAMAIS utilisés pour décider.

Trois familles de signaux que le backtest n'a pas pu tester faute d'historique gratuit, observées en conditions réelles :
- achats de dirigeants sur le marché (agent initiés : formulaires 4 de la SEC, AMF, BaFin) ;
- révisions à la hausse des analystes (agent entreprises, dynamique des résultats : bénéfice par action de l'exercice
  relevé d'au moins `revision_min_pct` % sur 30 jours, plus de relèvements que de baisses, au moins `analystes_min`
  analystes ; une seule révision enregistrée par société sur `delai_revision_jours` jours) ;
- relèvements de guidance (agent entreprises : dernier communiqué de résultats au statut « relevée »).

Pour chaque signal : cours de l'actif au jour de l'enregistrement, puis performance à 1, 3 et 6 mois, comparée au MSCI
World (ETF URTH) sur la même période. Les performances sont en devise de cotation (l'ETF URTH en dollars).
Sortie : data/observation.json.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json

LOG = journal("agent-trader")
TYPES = {"achat_dirigeant": "Achats de dirigeants", "revision_analystes": "Révisions à la hausse des analystes",
         "relevement_guidance": "Relèvements de guidance"}


def _symbole_us(ticker: str) -> str:
    return ticker.replace(".", "-")


def collecter(data, cfg: dict, existants: list[dict], jour: str) -> list[dict]:
    """Nouveaux signaux du jour (déjà enregistrés ignorés)."""
    deja = {s["id"] for s in existants}
    fenetre = (date.fromisoformat(jour) - timedelta(days=7)).isoformat()  # pas de rattrapage d'anciens signaux
    nouveaux = []
    ini = (lire_json(data / "inities.json") or {}).get("donnees") or {}
    for a in ((ini.get("dirigeants") or {}).get("achats") or []):
        d = (a.get("depot") or a.get("date") or "")[:10]
        if not a.get("ticker") or d < fenetre:
            continue
        sid = f"achat|{a.get('acc') or d}|{a['ticker']}|{a.get('declarant')}"
        if sid in deja:
            continue
        sym = _symbole_us(a["ticker"]) if a.get("pays", "US") == "US" else a["ticker"]
        nouveaux.append({"id": sid, "type": "achat_dirigeant", "date_signal": d, "symbole": sym, "nom": a.get("societe"), "pays": a.get("pays"),
                         "texte": f"{a.get('declarant')} ({a.get('titre') or a.get('fonction')}) : achat de {round(a.get('montant') or 0):,} "
                                  f"{a.get('devise') or ''}".replace(",", " ") + (f" — {a['caractere_raison']}" if a.get("caractere_raison") else "")})
        deja.add(sid)
    dyn = (lire_json(data / "entreprises" / "dynamique.json") or {}).get("societes") or {}
    recentes = {}
    for s in existants:
        if s["type"] == "revision_analystes":
            recentes[s["symbole"]] = max(recentes.get(s["symbole"], ""), s["date_signal"])
    limite_rev = (date.fromisoformat(jour) - timedelta(days=cfg["delai_revision_jours"])).isoformat()
    for t, x in dyn.items():
        est = (((x.get("analystes") or {}).get("estimations") or {}).get("0y")) or {}
        bpa, rev = est.get("bpa") or {}, est.get("revisions") or {}
        a0, a30 = bpa.get("actuel"), bpa.get("30j")
        if a0 is not None and a30 and a30 > 0 and (est.get("analystes") or 0) >= cfg["analystes_min"]:
            hausse = (a0 / a30 - 1) * 100
            if hausse >= cfg["revision_min_pct"] and (rev.get("hausse_30j") or 0) > (rev.get("baisse_30j") or 0) \
                    and recentes.get(t, "") < limite_rev:
                sid = f"revision|{t}|{jour}"
                if sid not in deja:
                    nouveaux.append({"id": sid, "type": "revision_analystes", "date_signal": jour, "symbole": t, "nom": t,
                                     "texte": f"bénéfice par action attendu sur l'exercice relevé de {hausse:+.1f} % en 30 jours".replace(".", ",")
                                              + f" ({rev.get('hausse_30j')} relèvement(s), {rev.get('baisse_30j') or 0} baisse(s), {est.get('analystes')} analystes)"})
                    deja.add(sid)
                    recentes[t] = jour
        g = ((x.get("guidance") or {}).get("dernier")) or {}
        if str(g.get("statut") or "").lower().startswith("relev") and (g.get("date") or "")[:10] >= fenetre:
            sid = f"guidance|{t}|{g.get('accession') or g.get('date')}"
            if sid not in deja:
                nouveaux.append({"id": sid, "type": "relevement_guidance", "date_signal": g["date"][:10], "symbole": t, "nom": t,
                                 "texte": "prévisions relevées dans le communiqué de résultats" + (f" ({g['raison']})" if g.get("raison") else ""),
                                 "url": g.get("url_communique") or g.get("url_depot")})
                deja.add(sid)
    return nouveaux


def mesurer(signaux: list[dict], cours: dict, indice: float | None, jour: str, horizons: list[int]) -> None:
    """Cours de départ (au premier cours connu) et performance à chaque horizon échu."""
    j = date.fromisoformat(jour)
    for s in signaux:
        c = (cours.get(s["symbole"]) or {}).get("cours")
        if s.get("cours_depart") is None:
            if c:
                s.update({"cours_depart": c, "date_depart": jour, "indice_depart": indice})
            continue
        age = (j - date.fromisoformat(s["date_depart"])).days
        for h in horizons:
            cle = str(h)
            if cle in (s.get("performance") or {}) or age < round(30.44 * h) or not c:
                continue
            perf = (c / s["cours_depart"] - 1) * 100
            perf_i = (indice / s["indice_depart"] - 1) * 100 if indice and s.get("indice_depart") else None
            s.setdefault("performance", {})[cle] = {"date": jour, "pct": round(perf, 2), "msci_world_pct": None if perf_i is None else round(perf_i, 2),
                                                    "ecart_points": None if perf_i is None else round(perf - perf_i, 2)}


def resume(signaux: list[dict], horizons: list[int]) -> dict:
    res = {}
    for t, lib in TYPES.items():
        par_h = {}
        for h in horizons:
            mes = [s["performance"][str(h)] for s in signaux if s["type"] == t and str(h) in (s.get("performance") or {})]
            rel = [m["ecart_points"] for m in mes if m.get("ecart_points") is not None]
            par_h[str(h)] = {"n": len(mes), "moyenne_pct": round(sum(m["pct"] for m in mes) / len(mes), 2) if mes else None,
                             "ecart_moyen_points": round(sum(rel) / len(rel), 2) if rel else None,
                             "battent_indice_pct": round(100 * sum(1 for x in rel if x > 0) / len(rel), 1) if rel else None}
        res[t] = {"libelle": lib, "enregistres": sum(1 for s in signaux if s["type"] == t), "horizons": par_h}
    return res


def mettre_a_jour(f, data, config: dict, maintenant: datetime) -> dict | None:
    """Une fois par jour : nouveaux signaux, cours de départ, performances échues. Renvoie un résumé (None si déjà fait)."""
    cfg = config["observation"]
    chemin = data / "observation.json"
    obj = lire_json(chemin) or {}
    d = obj.get("donnees") or {}
    jour = maintenant.date().isoformat()
    if d.get("dernier_jour") == jour:
        return None
    signaux = d.get("signaux") or []
    nouveaux = collecter(data, cfg, signaux, jour)
    signaux += nouveaux
    limite = (maintenant.date() - timedelta(days=round(30.44 * max(cfg["horizons_mois"])) + 10)).isoformat()
    a_suivre = [s for s in signaux if s.get("cours_depart") is None or (s.get("date_depart") or jour) >= limite]
    symboles = sorted({s["symbole"] for s in a_suivre} | {cfg["indice"]})
    lire = getattr(f, "clotures", None) or f.derniers_cours
    cours = lire(symboles) if symboles else {}
    indice = (cours.get(cfg["indice"]) or {}).get("cours")
    mesurer(a_suivre, cours, indice, jour, cfg["horizons_mois"])
    signaux = signaux[-cfg["max_signaux"]:]
    donnees = {"dernier_jour": jour, "horizons_mois": cfg["horizons_mois"], "indice": cfg["indice"],
               "resume": resume(signaux, cfg["horizons_mois"]), "signaux": signaux,
               "regle": ("Signaux enregistrés chaque jour, jamais utilisés pour décider : ils n'ont pas pu être testés par le backtest faute "
                         "d'historique gratuit. Performance de l'actif à 1, 3 et 6 mois après l'enregistrement, comparée au MSCI World (ETF URTH)."),
               "mention": "Observation seulement : aucun ordre n'est passé sur ces signaux."}
    ecrire_json(chemin, enveloppe(donnees, "agent-trader (observation)", fictif=False,
                                  description="Signaux en observation : achats de dirigeants, révisions des analystes, relèvements de guidance"))
    return {"nouveaux": len(nouveaux), "suivis": len(a_suivre), "cours": len(cours)}
