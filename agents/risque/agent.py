"""
Agent risque : stress financier mondial et par pays, et contradicteur des signaux des autres agents.

Étapes :
1. collecte : Yahoo Finance à chaque exécution (VIX, VSTOXX si disponible, MOVE, dollar, ACWI, TLT,
   GLD sur 10 ans ; ETF pays et devises sur 13 mois) ; sources lentes (FRED, BCE, FMI, Banque
   mondiale) relevées en mode « complet » ou si le dernier relevé a plus de 20 h, gardées dans
   data/risque/etat.json ; une source en panne n'arrête pas l'agent ;
2. niveau de risque mondial : percentiles sur 10 ans, score /100, palier (« Calme », « Vigilance »,
   « Tension », « Crise »), deux signaux concordants minimum pour en changer (mondial.py) ;
3. score de risque /100 par pays et variation sur 7 jours (pays_risque.py) ;
4. signaux pour le chef d'orchestre (data/signaux/risque.json) ;
5. contradicteur : objections propres à chaque signal encore valide des autres agents
   (data/signaux/revues.json, purgé des signaux périmés ; contradicteur.py) ;
6. écrit data/risque.json, data/historique/risque/AAAA-MM-JJ.json, le journal
   data/journal/agent-risque.json (santé) et, en mode « complet » (22 h 45 UTC), le récapitulatif
   data/recap/risque-AAAA-MM-JJ.md.

Règles de conduite et méthode : agents/risque/regles.md.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from . import calculs as C
from . import contradicteur as K
from . import mondial as M
from . import pays_risque as P
from .sources import FournisseurReel, FournisseurTest

LOG = journal("agent-risque")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
WORKFLOW = "agent-risque.yml"
HEURE_COMPLETE = (22, 45)  # UTC
RELEVE_LENT_HEURES = 20


def charger_config() -> dict:
    return json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))


def pays_suivis() -> dict:
    return json.loads((RACINE / "agents" / "pays" / "config.json").read_text(encoding="utf-8"))["pays"]


def iso(t: datetime) -> str:
    return sante.iso(t)


# ------------------------------------------------------------------ collecte

def _noter(etats: dict, cle: str, nom: str, etat: str, detail: str | None = None, **autres) -> None:
    etats[cle] = {"nom": nom, "etat": etat, "detail": detail, **autres}


def series_lentes(f, config: dict, pays: dict, debut: str, etats: dict) -> dict:
    """FRED, BCE, FMI et Banque mondiale. Renvoie {series, fmi, reserves} (ce qui a répondu)."""
    series, fmi, reserves = {}, {}, None
    for ci in config["indicateurs"].values():
        for s in ci["sources"]:
            if s["type"] == "fred":
                try:
                    series[f"fred:{s['serie']}"] = f.fred(s["serie"], debut)
                    _noter(etats, f"fred:{s['serie']}", s["nom"], "ok", f"dernière valeur au {series[f'fred:' + s['serie']][-1][0]}")
                except Exception as e:  # noqa: BLE001
                    _noter(etats, f"fred:{s['serie']}", s["nom"], "échec", str(e)[:200])
            elif s["type"] == "bce":
                try:
                    series[M.id_source(s)] = f.bce(s["flux"], s["cle"], debut)
                    _noter(etats, M.id_source(s), s["nom"], "ok", f"dernière valeur au {series[M.id_source(s)][-1][0]}")
                except Exception as e:  # noqa: BLE001
                    _noter(etats, M.id_source(s), s["nom"], "échec", str(e)[:200])
    cp = config["pays"]
    ok, echecs = 0, []
    for code, serie in cp["taux_10a_fred"].items():
        try:
            series[f"taux:{code}"] = f.fred(serie, debut)
            ok += 1
        except Exception as e:  # noqa: BLE001
            echecs.append(f"{code} ({str(e)[:60]})")
    _noter(etats, "taux_10a_fred", "OCDE via FRED, taux à 10 ans (IRLTLT01…M156N), mensuel",
           "ok" if not echecs else "partielle" if ok else "échec",
           f"{ok}/{len(cp['taux_10a_fred'])} pays" + (f" ; échecs : {', '.join(echecs)[:200]}" if echecs else ""))
    ok, echecs = 0, []
    for code, cle in cp["souverains_bce"].items():
        try:
            series[f"taux_bce:{code}"] = f.bce("IRS", cle, debut[:7])
            ok += 1
        except Exception as e:  # noqa: BLE001
            echecs.append(f"{code} ({str(e)[:60]})")
    _noter(etats, "bce_irs", "BCE Data Portal, taux à 10 ans de la zone euro (IRS), mensuel",
           "ok" if not echecs else "partielle" if ok else "échec", f"{ok}/{len(cp['souverains_bce'])} pays" + (f" ; échecs : {', '.join(echecs)[:200]}" if echecs else ""))
    iso3 = {p["iso3"] for p in pays.values()}
    ok, echecs = 0, []
    for serie in ("GGXWDG_NGDP", "BCA_NGDPD", "PCPIPCH"):
        try:
            brut = f.fmi(serie)
            fmi[serie] = {k: v for k, v in brut.items() if k in iso3}
            ok += 1
        except Exception as e:  # noqa: BLE001
            echecs.append(f"{serie} ({str(e)[:60]})")
    _noter(etats, "fmi", "FMI, DataMapper (dette publique GGXWDG_NGDP, solde courant BCA_NGDPD, inflation PCPIPCH)",
           "ok" if not echecs else "partielle" if ok else "échec", f"{ok}/3 séries" + (f" ; échecs : {', '.join(echecs)}" if echecs else ""))
    try:
        brut = f.banque_mondiale("FI.RES.TOTL.MO", int(debut[:4]) + config["historique_annees"])
        reserves = {k: v for k, v in brut.items() if k in iso3}
        _noter(etats, "banque_mondiale", "Banque mondiale, réserves en mois d'importations (FI.RES.TOTL.MO)", "ok", f"{len(reserves)} pays")
    except Exception as e:  # noqa: BLE001
        _noter(etats, "banque_mondiale", "Banque mondiale, réserves en mois d'importations (FI.RES.TOTL.MO)", "échec", str(e)[:200])
    return {"series": series, "fmi": fmi, "reserves": reserves}


def collecter(f, config: dict, etat: dict, pays: dict, maintenant: datetime, mode: str) -> tuple[dict, dict, dict]:
    """Renvoie (séries par identifiant, cours Yahoo par symbole, états des sources)."""
    etats = {}
    aujourdhui = maintenant.date()
    debut = (aujourdhui - timedelta(days=365 * config["historique_annees"] + 10)).isoformat()

    # Sources lentes : relevées une fois par jour (ou en mode complet), gardées dans l'état
    lentes = etat.setdefault("lentes", {"series": {}, "fmi": {}, "reserves": None, "releve_le": None, "etats": {}})
    releve = sante.lire_iso(lentes.get("releve_le"))
    du = mode == "complet" or releve is None or maintenant - releve > timedelta(hours=RELEVE_LENT_HEURES)
    if du:
        nouveaux = {}
        r = series_lentes(f, config, pays, debut, nouveaux)
        for cle, s in r["series"].items():
            lentes["series"][cle] = C.compacter(s, aujourdhui)
        lentes["fmi"].update(r["fmi"])
        if r["reserves"] is not None:
            lentes["reserves"] = r["reserves"]
        for cle, e in nouveaux.items():
            if e["etat"] == "échec" and (cle in lentes["series"] or (cle == "fmi" and lentes["fmi"]) or (cle == "banque_mondiale" and lentes["reserves"])):
                e = {**e, "etat": "périmée", "detail": f"dernière valeur gardée ; {e['detail']}"}
            etats[cle] = e
        lentes["etats"] = {k: {**v} for k, v in etats.items()}
        if any(e["etat"] == "ok" for e in nouveaux.values()):
            lentes["releve_le"] = iso(maintenant)
    else:
        for cle, e in (lentes.get("etats") or {}).items():
            etats[cle] = {**e, "detail": f"relevé le {C.date_fr(lentes['releve_le'])} ; {e.get('detail') or ''}".strip(" ;")}
    series = {k: [tuple(x) for x in v] for k, v in lentes["series"].items()}

    # Yahoo Finance : à chaque exécution
    cours = {}
    marches = []
    for ci in config["indicateurs"].values():
        marches += [s["symbole"] for s in ci["sources"] if s["type"] == "yahoo"]
    marches += [a["symbole"] for a in config["correlations"]["actifs"].values()]
    marches = list(dict.fromkeys(marches))
    facultatifs = {s["symbole"] for ci in config["indicateurs"].values() if ci.get("facultatif") for s in ci["sources"] if s["type"] == "yahoo"}
    try:
        r = f.cours(marches, f"{config['historique_annees']}y")
        cours.update(r)
        manquants = [s for s in marches if s not in r and s not in facultatifs]
        _noter(etats, "yahoo_marches", "Yahoo Finance via yfinance : VIX, MOVE, dollar, ACWI, TLT, GLD (10 ans)",
               "ok" if not manquants else "partielle", f"{len(r)}/{len(marches)} symboles" + (f" ; absents : {', '.join(manquants)}" if manquants else ""))
    except Exception as e:  # noqa: BLE001
        _noter(etats, "yahoo_marches", "Yahoo Finance via yfinance : VIX, MOVE, dollar, ACWI, TLT, GLD (10 ans)", "échec", str(e)[:200])
    for s in facultatifs:
        _noter(etats, f"yahoo:{s}", f"Yahoo Finance, {s} (facultatif)", "ok" if s in cours else "non configurée",
               None if s in cours else "symbole indisponible sur Yahoo Finance : indicateur ignoré")
    symboles_pays = list(dict.fromkeys([p["etf"] for p in pays.values() if p.get("etf")]
                                       + [p["devise"]["symbole"] for p in pays.values() if p.get("devise")]))
    try:
        r = f.cours(symboles_pays, "13mo")
        cours.update({k: v for k, v in r.items() if k not in cours})
        manquants = [s for s in symboles_pays if s not in r]
        _noter(etats, "yahoo_pays", "Yahoo Finance via yfinance : ETF pays et devises suivies (agent pays, 13 mois)",
               "ok" if not manquants else "partielle", f"{len(r)}/{len(symboles_pays)} symboles" + (f" ; absents : {', '.join(manquants)[:150]}" if manquants else ""))
    except Exception as e:  # noqa: BLE001
        _noter(etats, "yahoo_pays", "Yahoo Finance via yfinance : ETF pays et devises suivies (agent pays, 13 mois)", "échec", str(e)[:200])
    for sym, serie in cours.items():
        series[f"yahoo:{sym}"] = serie

    # Écarts souverains (pays − Allemagne)
    for ci in config["indicateurs"].values():
        for s in ci["sources"]:
            if s["type"] == "ecart_souverain":
                a, b = series.get(f"taux:{s['pays']}"), series.get("taux:DE")
                if a and b:
                    series[f"ecart:{s['pays']}"] = C.ecart_series(a, b)
                a, b = series.get(f"taux_bce:{s['pays']}"), series.get("taux_bce:DE")
                if a and b:
                    series[f"ecart_bce:{s['pays']}"] = C.ecart_series(a, b)
    return series, cours, etats


# ------------------------------------------------------------------ signaux

def semaine(d) -> str:
    a, s, _ = C.jour(d).isocalendar()
    return f"{a}-S{s:02d}"


def signaux(etat_palier: dict, change: bool, inds: dict, pays_scores: dict, corr: dict, config: dict, etat: dict, aujourdhui: str, score) -> list[dict]:
    cfg = config["signaux"]
    deja = set(etat.get("signales", []))
    res = []

    def ajouter(cle_dedup, signal):
        if cle_dedup not in deja:
            deja.add(cle_dedup)
            res.append({"date": aujourdhui, **signal})

    if change:
        ajouter(f"palier:{aujourdhui}:{etat_palier['actuel']}", {
            "type": "changement_de_palier", "cle": "monde", "importance": "forte",
            "titre": f"Risque mondial : passage de « {etat_palier['precedent']} » à « {etat_palier['actuel']} »",
            "explication": f"Score de stress financier mondial de {C.fr(score, 0)}/100 ; indicateurs concordants : "
                           + ", ".join(inds[c]["nom"] for c in etat_palier.get("concordants", [])[:5]) + ".",
            "source": "agent risque (FRED, BCE, Yahoo Finance)"})
    for cle in ("hy_us", "ig_us", "hy_eu"):
        i = inds.get(cle) or {}
        if not i.get("disponible") or len(i["_serie"]) < 22:
            continue
        v20 = round(i["_serie"][-1][1] - i["_serie"][-21][1], 2)
        seuil = cfg["credit_hausse_pts_20j"] * (0.5 if cle == "ig_us" else 1)
        if v20 >= seuil:
            forte = v20 >= cfg["credit_hausse_forte_pts_20j"] * (0.5 if cle == "ig_us" else 1)
            ajouter(f"credit:{cle}:{semaine(aujourdhui)}", {
                "type": "ecart_credit_hausse", "cle": cle, "importance": "forte" if forte else "moyenne",
                "titre": f"{i['nom']} : {C.fr(v20, 2, True)} pt sur 20 séances, à {C.fr(i['valeur'], 2)} pt",
                "explication": f"{i['nom']} à {C.fr(i['valeur'], 2)} pt au {C.date_fr(i['date'])} (percentile {C.fr(i['percentile'], 0)} sur {C.fr(i['historique_annees'], 0)} ans), "
                               f"en hausse de {C.fr(v20, 2)} pt sur 20 séances.",
                "source": i["source"]})
    for code, s in pays_scores.items():
        dv = s["composantes"].get("devise")
        if not dv:
            continue
        v3, v1 = dv.get("variation_3m"), dv.get("variation_1m")
        if (v3 is not None and v3 <= cfg["devise_baisse_3m"]) or (v1 is not None and v1 <= cfg["devise_baisse_1m"]):
            ajouter(f"devise:{code}:{semaine(aujourdhui)}", {
                "type": "devise_decrochage", "cle": code, "pays": [code], "importance": "moyenne",
                "titre": f"{s['nom']} : la devise décroche ({C.fr(v3, 1, True)} % sur 3 mois, {C.fr(v1, 1, True)} % sur 1 mois contre le dollar)",
                "explication": dv["texte"] + ".", "source": dv["source"]})
    for p in corr.get("paires", []):
        rupture = p["ecart"] is not None and abs(p["ecart"]) >= cfg["rupture_correlation_ecart"]
        if p["a"] == "actions" and p["b"] == "obligations" and p["correlation_3m"] >= 0.3 and (p["correlation_12m"] or 0) < 0:
            rupture = True
        if rupture:
            ajouter(f"correlation:{p['a']}-{p['b']}:{aujourdhui[:7]}", {
                "type": "rupture_correlation", "cle": f"{p['a']}-{p['b']}", "importance": "moyenne",
                "titre": f"Rupture de corrélation {p['nom']} : {C.fr(p['correlation_3m'], 2, True)} sur 3 mois contre {C.fr(p['correlation_12m'], 2, True)} sur 12 mois",
                "explication": "Corrélation des rendements quotidiens ; une corrélation actions / obligations positive réduit la diversification.",
                "source": corr["source"]})
    etat["signales"] = sorted(deja)[-2000:]
    return res


# ------------------------------------------------------------------ sorties

def indicateur_public(i: dict, s: dict, paliers: list) -> dict:
    return {k: v for k, v in i.items() if not k.startswith("_") and k not in ("sources_valides", "sources_configurees")} | (
        {"texte": M.texte_valeur(i), "palier": M.palier_de(i["score"], s, paliers)} if i["disponible"] else {})


def recap_markdown(jour: str, donnees: dict, sig: list, revues: list, etats: dict, config: dict) -> str:
    m = donnees["mondial"]
    l = [f"# Agent risque — récapitulatif du {C.date_fr(jour)}", "",
         "Stress financier mondial et par pays, et revue contradictoire des signaux des autres agents. "
         "Faits chiffrés et sourcés ; les interprétations sont signalées comme telles.", "",
         "## Niveau de risque mondial", "",
         f"- Score : {C.fr(m['score'], 0)}/100 · palier « {m['palier']} » depuis le {C.date_fr(m['depuis'])}"
         + (f" (précédent : « {m['palier_precedent']} »)" if m.get("palier_precedent") else ""),
         f"- Confiance : {m['confiance']['niveau']} ({'; '.join(m['confiance']['raisons'])})",
         f"- Seuils : {', '.join(f'{p} ≥ {donnees['seuils'][p]}' for p in config['paliers'][1:])} ({donnees['seuils']['methode']})"]
    if m.get("changement_en_attente"):
        a = m["changement_en_attente"]
        l.append(f"- Changement en attente vers « {a['vers']} » : {len(a['familles_concordantes'])} famille(s) concordante(s)")
    l += ["", "Faits :", ""] + [f"- {x}" for x in m["faits"]]
    l += ["", "Interprétations :", ""] + [f"- {x}" for x in m["interpretations"]]
    l += ["", "Ce qui pourrait me donner tort :", ""] + [f"- {x}" for x in m["contre"]]
    l += ["", "## Indicateurs", "", "| Indicateur | Valeur | Date | Percentile | Tendance 1 mois | Source |", "|---|---|---|---|---|---|"]
    for i in donnees["indicateurs"]:
        if i["disponible"]:
            l.append(f"| {i['nom']} | {i['texte']} | {C.date_fr(i['date'])} | {C.fr(i['percentile'], 0)} | {i['tendance'] or 'n. d.'} | {i['source']} |")
        else:
            l.append(f"| {i['nom']} | n. d. | | | | indisponible |")
    l += ["", "## Pays les plus à risque", "", "| Pays | Score | Variation 7 j |", "|---|---|---|"]
    for code, s in sorted(donnees["pays"].items(), key=lambda kv: -(kv[1]["score"] if kv[1]["score"] is not None else -1))[:10]:
        v = s["variation_7j"]
        l.append(f"| {s['nom']} | {s['score'] if s['score'] is not None else 'n. d.'} | {'n. d.' if v is None else C.fr(v, 1, True)} |")
    l += ["", "## Signaux", ""] + ([f"- [{s['importance']}] {s['titre']}" for s in sig] or ["- aucun"])
    l += ["", "## Objections du contradicteur (signaux encore valides)", ""]
    for r in revues:
        l.append(f"- {r['signal']['agent']} · {r['signal']['titre']} → **{r['ajustement']}** ({r['methode']}) : {r['objection']}")
    if not revues:
        l.append("- aucune")
    erreurs = [v for v in etats.values() if v["etat"] in ("échec", "partielle", "périmée")]
    l += ["", "## Sources en échec", ""] + ([f"- {v['nom']} : {v['etat']} ({v.get('detail') or ''})" for v in erreurs] or ["- aucune"])
    return "\n".join(l) + "\n"


def recap_du(mode: str, data: Path, maintenant: datetime) -> bool:
    if mode == "complet":
        return True
    return (maintenant.hour, maintenant.minute) >= HEURE_COMPLETE and not (data / "recap" / f"risque-{maintenant.date().isoformat()}.md").exists()


def sources_sante(etats: dict, pays_ok: bool, geo_ok: bool, rapport: dict) -> list[dict]:
    res = [{"nom": v["nom"], "etat": v["etat"], "detail": v.get("detail")} for v in etats.values()]
    res.append({"nom": "Agent pays (data/pays.json : devises, inflation)", "etat": "ok" if pays_ok else "échec",
                "detail": None if pays_ok else "fichier absent ou illisible"})
    res.append({"nom": "Agent géopolitique (data/geopolitique.json : score par pays)", "etat": "ok" if geo_ok else "échec",
                "detail": None if geo_ok else "fichier absent ou illisible"})
    nom = "Gemini (objections du contradicteur)"
    if not rapport["cle"]:
        res.append({"nom": nom, "etat": "non configurée", "detail": "secret GEMINI_API_KEY absent : objections par règles"})
    elif rapport["erreurs"] and not rapport["reussites"] and not all("429" in e for e in rapport["erreurs"]):
        res.append({"nom": nom, "etat": "échec", "detail": "; ".join(rapport["erreurs"])[-300:]})
    else:
        q = rapport.get("quota") or {}
        res.append({"nom": nom, "etat": "ok", "detail": f"{rapport['appels']} appel(s) cette exécution ; {q.get('appels', 0)}/{q.get('quota_jour', '?')} aujourd'hui (budget propre à l'agent risque)"})
    return res


def executer(f, config: dict, data: Path, maintenant: datetime, mode: str = "horaire", cle_gemini: str | None = None,
             poster=None, horloge=None, dormir=None, pays: dict | None = None) -> dict:
    pays = pays or pays_suivis()
    chemin_etat = data / "risque" / "etat.json"
    etat = lire_json(chemin_etat) or {}
    aujourdhui = maintenant.date().isoformat()

    series, cours, etats = collecter(f, config, etat, pays, maintenant, mode)
    inds = M.construire_indicateurs(series, config, aujourdhui)
    actifs = [i for i in inds.values() if i["disponible"]]
    if not actifs:
        LOG.error("Aucun indicateur de stress disponible : fichiers inchangés.")
        return {"ok": False, "etats": etats}

    # Score mondial, historique sur 10 ans, seuils et palier
    hist = M.historique_score(inds, aujourdhui, config["historique_annees"])
    s = M.seuils(hist, config)
    score = M.score_pondere({k: i["score"] for k, i in inds.items() if i["disponible"]}, {k: i["poids"] for k, i in inds.items() if i["disponible"]}, 0)
    date_calcul = max(i["date"] for i in actifs)
    brut = M.palier_de(score, s, config["paliers"])
    ancien_palier = etat.get("palier")
    etat_palier, attente = M.decider_palier(ancien_palier, brut, inds, s, config, aujourdhui)
    change = bool(ancien_palier) and etat_palier.get("changement_le") == aujourdhui and etat_palier is not ancien_palier
    etat["palier"] = etat_palier
    syn = M.synthese(score, etat_palier, attente, inds, s, config, date_calcul)
    corr = M.correlations(cours, config)

    # Scores par pays
    pays_json_brut = lire_json(data / "pays.json")
    pays_json = {p["code"]: p for p in ((pays_json_brut or {}).get("donnees") or [])}
    geo = lire_json(data / "geopolitique.json")
    noms = {k: v["nom"] for k, v in pays.items()}
    taux = {k.split(":", 1)[1]: v for k, v in series.items() if k.startswith("taux:")}
    taux_bce = {k.split(":", 1)[1]: v for k, v in series.items() if k.startswith("taux_bce:")}
    lentes = etat["lentes"]
    ctx = {"aujourdhui": aujourdhui, "cours": cours, "pays_json": pays_json, "geopolitique": (geo or {}).get("donnees"),
           "taux_10a": taux, "taux_10a_bce": taux_bce, "fmi": lentes.get("fmi") or {}, "reserves": lentes.get("reserves"),
           "pays_config": pays, "noms": noms}
    historique_pays = etat.setdefault("historique_pays", {})
    scores_pays = P.scores(config, ctx, historique_pays)
    historique_pays[aujourdhui] = {c: v["score_precis"] for c, v in scores_pays.items() if v["score_precis"] is not None}
    limite = (maintenant.date() - timedelta(days=40)).isoformat()
    etat["historique_pays"] = {d: v for d, v in historique_pays.items() if d >= limite}
    hm = etat.setdefault("historique_mondial", {})
    hm[aujourdhui] = {"score": score, "palier": etat_palier["actuel"]}
    etat["historique_mondial"] = {d: v for d, v in hm.items() if d >= (maintenant.date() - timedelta(days=400)).isoformat()}

    # Signaux de l'agent risque
    sig = signaux(etat_palier, change, inds, scores_pays, corr, config, etat, aujourdhui, score)
    fichier_signaux = data / "signaux" / "risque.json"
    existants = (lire_json(fichier_signaux) or {}).get("donnees") or []
    lim = (maintenant.date() - timedelta(days=config["signaux"]["garde_jours"])).isoformat()
    tous = sorted((x for x in existants + sig if x["date"] >= lim), key=lambda x: x["date"], reverse=True)
    ecrire_json(fichier_signaux, enveloppe(tous, "agent-risque", fictif=False, version_agent=VERSION_AGENT,
                                           description="Signaux candidats pour le chef d'orchestre (180 derniers jours)"))

    # Contradicteur : seulement les signaux encore valides, objections propres à chaque signal
    signaux_autres = K.lire_signaux(data / "signaux", config, aujourdhui)
    sources_agents = K.Sources(data)
    macro = sources_agents.macro()
    zones = {z.get("cle"): z for z in ((macro or {}).get("cycle") or {}).get("zones", [])}
    zone_par_pays = json.loads((RACINE / "agents" / "macro" / "config.json").read_text(encoding="utf-8")).get("zone_par_pays", {})
    phase_zone = {c: (zones[z].get("nom") or z, zones[z].get("phase")) for c, z in zone_par_pays.items() if z in zones and zones[z].get("phase")}
    if zones.get("monde", {}).get("phase"):  # pays sans zone propre : zone « Monde »
        phase_zone["*"] = (zones["monde"].get("nom") or "Monde", zones["monde"]["phase"])
    pep = (lire_json(data / "pepites.json") or {}).get("donnees") or []
    revues_critiques = {c.get("ticker"): c.get("revue_critique") for c in pep if isinstance(c, dict) and c.get("revue_critique")}
    chemin_revues = data / "signaux" / "revues.json"
    revues_existantes = (lire_json(chemin_revues) or {}).get("donnees") or []
    mondial_ctx = {"score": score, "palier": etat_palier["actuel"]}
    ctx_k = {**ctx, "aujourdhui": aujourdhui, "maintenant_iso": iso(maintenant), "mondial": mondial_ctx, "indicateurs": inds,
             "pays_scores": scores_pays, "signaux": signaux_autres, "sources": sources_agents,
             "entreprises": sources_agents.entreprises(), "macro": macro, "phase_zone": phase_zone,
             "revues_critiques": revues_critiques}
    cle = cle_gemini if cle_gemini is not None else os.environ.get("GEMINI_API_KEY", "")
    revues, nouvelles, rapport = K.revoir(signaux_autres, revues_existantes, ctx_k, config, etat, cle, poster, horloge, dormir)
    revues = sorted(revues, key=lambda r: (r["signal"].get("date") or "", r["revu_le"]), reverse=True)
    ecrire_json(chemin_revues, enveloppe(revues, "agent-risque", fictif=False, version_agent=VERSION_AGENT,
                                         description="Objections de l'agent risque (contradicteur) aux signaux des autres agents, avec ajustement de confiance proposé"))

    # data/risque.json
    hist_12m = [x for x in hist if x[0] >= (maintenant.date() - timedelta(days=372)).isoformat()]
    if not hist_12m or hist_12m[-1][0] != aujourdhui:
        hist_12m.append([aujourdhui, score])
    paliers = config["paliers"]
    pays_publics = {c: {k: v for k, v in x.items() if k != "score_precis"} for c, x in scores_pays.items()}
    donnees = {
        "date": aujourdhui, "mode": mode,
        "mondial": {"score": round(score), "score_precis": score, "palier": etat_palier["actuel"], "palier_brut": brut,
                    "palier_precedent": etat_palier.get("precedent"), "depuis": etat_palier["depuis"],
                    "changement_le": etat_palier.get("changement_le"), "changement_en_attente": attente,
                    "date_donnees": date_calcul, "explication": syn["explication"], "faits": syn["faits"],
                    "interpretations": syn["interpretations"], "confiance": syn["confiance"], "contre": syn["contre"],
                    "principaux": syn["principaux"], "familles": syn["familles"]},
        "paliers": paliers, "seuils": s,
        "indicateurs": [indicateur_public(i, s, paliers) for i in inds.values()],
        "historique": hist_12m,
        "correlations": corr,
        "pays": pays_publics,
        "objections": revues[:12],
        "contradicteur": {"revues_7j": len(revues), "sans_objection": sum(1 for r in revues if not r.get("specifique")),
                          "par_ajustement": {a: sum(1 for r in revues[:50] if r["ajustement"] == a) for a in K.AJUSTEMENTS},
                          "mode": "gemini" if any(r["methode"] == "gemini" for r in nouvelles) else "règles"},
        "methode": ("Score mondial /100 : moyenne pondérée des percentiles sur 10 ans de la volatilité (VIX, VSTOXX, MOVE), des écarts de crédit "
                    "(high yield et investment grade américains, high yield européen), des indices officiels de stress (STLFSI4, NFCI, CISS), "
                    "de l'écart Italie – Allemagne à 10 ans et de la variation du dollar sur 3 mois. Paliers : seuils aux percentiles 60, 85 et 97 "
                    "du score sur 10 ans ; deux familles d'indicateurs concordantes au moins pour changer de palier. Score pays /100 : marché, devise, "
                    "souverain, vulnérabilité macro, géopolitique."),
    }
    ancien = lire_json(data / "risque.json")
    objet = enveloppe(donnees, "agent-risque", fictif=False, version_agent=VERSION_AGENT,
                      mise_a_jour_precedente=(ancien or {}).get("meta", {}).get("genere_le"),
                      etat_des_sources={v["nom"]: v["etat"] for v in etats.values()})
    objet["meta"]["genere_le"] = iso(maintenant)
    ecrire_json(data / "risque.json", objet)
    ecrire_json(data / "historique" / "risque" / f"{aujourdhui}.json", {
        "meta": {"genere_le": iso(maintenant), "source": "agent-risque", "version_agent": VERSION_AGENT},
        "donnees": {"mondial": {"score": score, "palier": etat_palier["actuel"], "palier_brut": brut},
                    "indicateurs": {i["cle"]: {"valeur": i["valeur"], "percentile": i["percentile"], "date": i["date"]} for i in actifs},
                    "pays": {c: {"score": x["score"], "composantes": {k: v["score"] for k, v in x["composantes"].items()}} for c, x in scores_pays.items()},
                    "signaux": [x["titre"] for x in sig]}})
    recap = recap_du(mode, data, maintenant)
    if recap:
        (data / "recap").mkdir(parents=True, exist_ok=True)
        (data / "recap" / f"risque-{aujourdhui}.md").write_text(
            recap_markdown(aujourdhui, donnees, [x for x in tous if x["date"] == aujourdhui],
                           revues, etats, config), encoding="utf-8")

    # Journal et santé
    chemin_journal = data / "journal" / "agent-risque.json"
    j = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    entree = {"genere_le": iso(maintenant), "mode": mode, "recap": recap, "score": score, "palier": etat_palier["actuel"],
              "palier_brut": brut, "indicateurs_disponibles": len(actifs), "signaux": [x["titre"] for x in sig],
              "revues": len(nouvelles), "contradicteur": {k: rapport.get(k) for k in ("appels", "reussites", "quota_atteint", "candidats", "valides", "retirees")}
              | {"rejets": rapport["rejets"][:10], "erreurs": [e[:200] for e in rapport["erreurs"]][:5]},
              "etat_des_sources": {v["nom"]: v["etat"] for v in etats.values()}}
    j["donnees"] = (j.get("donnees", []) + [entree])[-200:]
    j["meta"] = {**j.get("meta", {}), "genere_le": iso(maintenant), "source": "agent-risque", "version_agent": VERSION_AGENT,
                 "description": "Sources, score mondial, signaux et revues du contradicteur, à chaque exécution"}
    ecrire_json(chemin_journal, j)
    indicateurs_sante = {i["nom"]: {"valides": i["sources_valides"], "configurees": i["sources_configurees"]}
                         for i in inds.values() if not i["facultatif"]}
    raisons = []
    mini = config["sante"]["sources_min"]
    if len([i for i in actifs if not i["facultatif"]]) < mini:
        raisons.append(f"{len(actifs)} indicateurs de stress disponibles, moins que le minimum de {mini}")
    bloc = sante.bloc_sante("risque", "Agent risque", 7, WORKFLOW, sources_sante(etats, bool(pays_json), bool(geo), rapport), maintenant,
                            (j.get("meta") or {}).get("sante"), indicateurs=indicateurs_sante, raisons_supplementaires=raisons)
    bloc["palier"] = etat_palier["actuel"]
    sante.enregistrer_sante(chemin_journal, bloc, forcer=True)

    etat["maj"] = iso(maintenant)
    ecrire_json(chemin_etat, etat, compact=True)
    LOG.info("Score mondial %s/100, palier « %s » (brut « %s »)%s ; %d indicateurs ; %d signal(aux) ; %d revue(s) (%d par Gemini)",
             score, etat_palier["actuel"], brut, f", en attente vers « {attente['vers']} »" if attente else "", len(actifs), len(sig),
             len(nouvelles), sum(1 for r in nouvelles if r["methode"] == "gemini"))
    LOG.info("Statut santé : %s%s", "DÉGRADÉ" if bloc["degrade"] else "OK", (" — " + " | ".join(bloc["raisons"])) if bloc["raisons"] else "")
    return {"ok": True, "donnees": donnees, "signaux": sig, "revues": nouvelles, "rapport": rapport, "sante": bloc, "etat": etat,
            "recap": recap, "indicateurs": inds}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent risque : stress financier mondial et par pays, contradicteur des signaux.")
    ap.add_argument("--test", action="store_true", help="données de test (agents/risque/tests/donnees), sans réseau ni Gemini")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier des données (data/)")
    ap.add_argument("--mode", choices=["horaire", "complet"], default="horaire",
                    help="« complet » : relève toutes les sources et écrit le récapitulatif du jour (22 h 45 UTC)")
    ap.add_argument("--maintenant", help="heure simulée (ISO, UTC)")
    ap.add_argument("--sans-ia", action="store_true", help="n'appelle pas Gemini")
    args = ap.parse_args(argv)
    config = charger_config()
    maintenant = sante.lire_iso(args.maintenant) if args.maintenant else datetime.now(timezone.utc)
    f = FournisseurTest(DOSSIER / "tests" / "donnees") if args.test else FournisseurReel(RACINE / "agents" / ".cache")
    cle = "" if (args.sans_ia or args.test) else os.environ.get("GEMINI_API_KEY", "")
    LOG.info("Agent risque %s — %s, mode %s", VERSION_AGENT, "données de test" if args.test else "sources réelles", args.mode)
    r = executer(f, config, Path(args.data), maintenant, args.mode, cle_gemini=cle)
    return 0 if r["ok"] else 1
