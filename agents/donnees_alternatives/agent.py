"""
Agent données alternatives (sans IA) : des indicateurs avancés qui montrent l'activité réelle avant les
statistiques officielles (camions, fret, ciment, électricité, exportations, offres d'emploi, aéroports,
satellites ; attention du public pour les sociétés suivies).

Étapes :
1. interroge les sources gratuites (voir sources.py) ; une source en panne n'arrête pas l'agent, une source
   à clé absente (EIA_API_KEY, ENTSOE_API_KEY) ou à adresse absente (SATELLITES_URL…) est ignorée ;
2. pour chaque indicateur : dernière valeur, variations sur 1 et 12 mois, écart à la tendance et à la
   normale saisonnière, percentile historique, note d'activité /100 ;
3. par pays (au moins 2 indicateurs à jour) : score d'activité /100, lecture « accélération », « stable »
   ou « ralentissement », confiance, « Ce qui pourrait me donner tort », divergence avec les statistiques
   officielles de l'agent pays (data/pays.json) ;
4. attention du public (Wikipédia, Google Trends) pour la liste de surveillance et les pépites (information) ;
5. écrit data/donnees_alternatives.json (lu par l'appli et par l'agent pays : sous-note « Activité réelle »),
   data/signaux/donnees_alternatives.json (chef d'orchestre), data/historique/donnees_alternatives/
   (scores du jour et valeurs accumulées des sources sans historique), data/recap/ et le journal
   data/journal/agent-donnees-alternatives.json (écran « Santé des agents »).

Règles de conduite : voir agents/donnees_alternatives/regles.md.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from . import analyse as A
from .sources import Capture, FournisseurReel, FournisseurTest, nom_recherche

LOG = journal("agent-donnees-alternatives")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
FICHIER_JOURNAL = "agent-donnees-alternatives.json"
APPROCHES = {"fret_vrac", "camions_de"}  # approximation (ETF) ou série expérimentale : confiance réduite
NOMS_PAYS_HORS_SUIVI = {"monde": "Monde"}


# ------------------------------------------------------------------ configuration

def indicateurs_config(cfg: dict) -> list[dict]:
    """Liste complète : indicateurs déclarés + offres d'emploi Indeed + agrégats satellitaires."""
    liste = [dict(i) for i in cfg["indicateurs"]]
    ind = cfg["indeed"]
    for p in ind["pays"]:
        liste.append({"cle": f"offres_emploi_{p.lower()}", "nom": ind["nom"], "pays": p, "categorie": "emploi", "source": "indeed",
                      "params": {"pays": p}, "frequence": "quotidienne", "unite": ind["unite"], "poids": ind["poids"], "sens": 1,
                      "source_nom": "Indeed Hiring Lab (dépôt public GitHub, corrigé des variations saisonnières)",
                      "mention": "offres publiées sur Indeed seulement ; reflète la demande de travail, pas l'emploi"})
    sat = cfg["satellites"]
    for p in sat["pays"]:
        for k, s in sat["indicateurs"].items():
            liste.append({"cle": f"{k}_{p.lower()}", "nom": s["nom"], "pays": p, "categorie": "satellites", "source": "csv_url",
                          "params": {"variable": sat["variable"], "pays": p, "indicateur": k}, "frequence": "mensuelle", "unite": s["unite"],
                          "poids": s["poids"], "sens": 1, "source_nom": s["source_nom"], "mention": s.get("mention")})
    return liste


# ------------------------------------------------------------------ collecte

def collecter(f, inds: list[dict], aujourdhui: date) -> tuple[dict, dict, dict]:
    series, etats, details = {}, {}, {}
    for ind in inds:
        try:
            r = f.serie(ind, aujourdhui)
            if r is None:
                etats[ind["cle"]] = "non configurée"
                continue
            series[ind["cle"]], details[ind["cle"]] = list(r[0]), r[1]
            etats[ind["cle"]] = "ok" if r[0] else "vide"
        except Exception as e:  # une source en panne : on continue
            etats[ind["cle"]] = f"erreur : {str(e)[:160]}"
            LOG.error("Source %s indisponible : %s", ind["cle"], str(e)[:200])
    LOG.info("Sources : %d ok, %d non configurées, %d en échec", sum(v == "ok" for v in etats.values()),
             sum(v == "non configurée" for v in etats.values()), sum(v.startswith("erreur") or v == "vide" for v in etats.values()))
    return series, etats, details


def accumuler(dossier_hist: Path, inds: list[dict], series: dict, aujourdhui: date) -> dict:
    """Sources qui ne publient que la dernière valeur (« accumuler » : WCI) : fusion avec les valeurs
    gardées lors des exécutions précédentes (data/historique/donnees_alternatives/accumule.json)."""
    chemin = dossier_hist / "accumule.json"
    memo = ((lire_json(chemin) or {}).get("donnees")) or {}
    change = False
    for ind in inds:
        if not ind.get("accumuler"):
            continue
        connus = {d: v for d, v in memo.get(ind["cle"], [])}
        for d, v in series.get(ind["cle"], []):
            if connus.get(d) != v:
                connus[d], change = v, True
        if connus:
            memo[ind["cle"]] = sorted([d, v] for d, v in connus.items())
            series[ind["cle"]] = [tuple(x) for x in memo[ind["cle"]]]
    if change:
        ecrire_json(chemin, {"meta": {"source": "agent-donnees-alternatives", "genere_le": A.date_fr(aujourdhui.isoformat()),
                                      "description": "Valeurs accumulées des sources qui ne publient que leur dernière valeur (ex. Drewry WCI)"},
                             "donnees": memo})
    return series


# ------------------------------------------------------------------ analyse

def analyser_indicateurs(inds: list[dict], series: dict, etats: dict, cfg: dict, aujourdhui: date) -> list[dict]:
    res = []
    for ind in inds:
        if etats.get(ind["cle"]) == "non configurée":
            continue
        pts = series.get(ind["cle"]) or []
        a = A.analyser_serie(pts, ind["frequence"], aujourdhui, ind.get("sens", 1), ind.get("fraicheur_jours") or cfg["fraicheur_jours"][ind["frequence"]]) if pts else None
        x = {k: ind.get(k) for k in ("cle", "nom", "pays", "categorie", "frequence", "unite", "poids", "source_nom", "mention")}
        x["categorie_nom"] = cfg["categories"].get(ind["categorie"], ind["categorie"])
        x["mention_proxy"] = ind["cle"] in APPROCHES
        if a:
            x.update(a)
            x["lecture"] = A.lecture_indicateur(ind["nom"], a) + (" Donnée ancienne : exclue du score." if a["perimee"] else "")
            x["serie"] = A.serie_graphique(pts, ind["frequence"], aujourdhui, cfg["historique_points"])
        else:
            x.update({"note": None, "valeur": None, "date": None, "serie": [],
                      "lecture": f"{ind['nom']} : source indisponible ({etats.get(ind['cle'], 'aucune donnée')})."})
        x["etat_source"] = etats.get(ind["cle"])
        res.append(x)
    return res


def analyser_pays(indicateurs: list[dict], pays_cfg: dict, pays_officiels: dict, cfg: dict, precedent: dict | None) -> list[dict]:
    anciens = {p["code"]: p for p in (precedent or {}).get("pays", [])}
    par_pays: dict[str, list[dict]] = {}
    for i in indicateurs:
        if i["pays"] != "monde":
            par_pays.setdefault(i["pays"], []).append(i)
    res = []
    for code, liste in sorted(par_pays.items()):
        if not any(i.get("valeur") is not None for i in liste):
            continue
        nom = (pays_cfg.get(code) or {}).get("nom") or code
        r = A.score_pays(liste, cfg)
        off = A.officiel(pays_officiels.get(code))
        p = {"code": code, "nom": nom, "suivi": code in pays_cfg, **r,
             "texte": A.texte_pays(nom, r, liste),
             "indicateurs": [i["cle"] for i in liste],
             "officiel": off}
        if r.get("score") is not None:
            p["ce_qui_pourrait_me_donner_tort"] = A.donner_tort(r, liste)
            p["divergence"] = A.divergence(r, off, liste, cfg)
        a = anciens.get(code) or {}
        if a.get("score") is not None and r.get("score") is not None:
            p["precedent"] = {"score": a["score"], "lecture": a.get("lecture")}
        res.append(p)
    return res


def analyser_attention(f, societes: list[dict], cfg: dict, aujourdhui: date, precedent: dict | None) -> tuple[list[dict], dict]:
    """Attention du public (information). Google Trends : `max_trends` requêtes par exécution, en rotation."""
    c = cfg["attention"]
    etats = {"wikipedia": "ok", "trends": "ok"}
    erreurs = {"wikipedia": 0, "trends": 0}
    anciens = {x["ticker"]: x for x in (precedent or {}).get("attention", [])}
    res = []
    rotation = aujourdhui.toordinal() % max(1, len(societes))
    ordre = societes[rotation:] + societes[:rotation]
    trends_faits, refus_wiki = 0, 0
    for s in ordre[: c["max_societes"]]:
        wiki = trends = None
        if refus_wiki < 3:  # trois refus de suite (limite de débit) : plus de requête Wikipédia pour cette exécution
            try:
                wiki = f.wikipedia(s["nom"], aujourdhui)
                refus_wiki = 0
            except Exception as e:
                erreurs["wikipedia"] += 1
                refus_wiki += 1
                LOG.warning("Wikipédia %s : %s", s["nom"], str(e)[:120])
        if trends_faits < c["max_trends"] and etats["trends"] != "non configurée":
            try:
                trends = f.trends(nom_recherche(s["nom"]), aujourdhui)
                trends_faits += 1
                if trends is None:
                    etats["trends"] = "non configurée"
            except Exception as e:  # limites de Google : on arrête les requêtes pour cette exécution
                erreurs["trends"] += 1
                trends_faits = c["max_trends"]
                LOG.warning("Google Trends %s : %s", s["nom"], str(e)[:120])
        a = A.attention(wiki, trends, c)
        if a is None:
            ancien = anciens.get(s["ticker"])
            if ancien and wiki is None:  # non relu aujourd'hui (refus ou rotation) : dernier résultat connu, sans signal
                res.append({**ancien, "ancienne": True, "signal": False})
            continue
        if "trends" not in a and (anciens.get(s["ticker"]) or {}).get("trends"):
            a["trends"] = {**anciens[s["ticker"]]["trends"], "ancienne": True}  # résultat d'une exécution précédente (rotation)
        res.append({"ticker": s["ticker"], "nom": s["nom"], "pays": s.get("pays"), "liste": s["liste"], **a,
                    "signal": a["variation_moyenne_pct"] >= c["signal_pct"]})
    for k in etats:
        if erreurs[k] and etats[k] == "ok":
            etats[k] = f"erreur : {erreurs[k]} échec(s)"
    res.sort(key=lambda x: -x["variation_moyenne_pct"])
    return res, etats


def societes_suivies(chemin_surveillance: Path, data: Path) -> list[dict]:
    noms = {e.get("ticker"): e for e in ((lire_json(data / "entreprises.json") or {}).get("donnees") or []) if isinstance(e, dict)}
    res, vus = [], set()
    for s in ((lire_json(chemin_surveillance) or {}).get("societes") or []):
        e = noms.get(s.get("ticker")) or {}
        if s.get("ticker") and e.get("nom") and s["ticker"] not in vus:
            res.append({"ticker": s["ticker"], "nom": e["nom"], "pays": s.get("pays") or e.get("pays"), "liste": "surveillance"})
            vus.add(s["ticker"])
    for p in ((lire_json(data / "pepites.json") or {}).get("donnees") or []):
        if isinstance(p, dict) and p.get("ticker") and p.get("nom") and p["ticker"] not in vus:
            res.append({"ticker": p["ticker"], "nom": p["nom"], "pays": p.get("pays"), "liste": "pepites"})
            vus.add(p["ticker"])
    return res


def tableau_mondial(indicateurs: list[dict]) -> list[str]:
    """Indicateurs du tableau de bord mondial (écran « Données alternatives »), dans l'ordre d'affichage."""
    ordre = ["camions_de", "exportations_kr", "exportations_kr_20j", "commandes_export_tw", "ciment_cn", "electricite_cn", "fret_conteneurs",
             "fret_vrac", "camions_us", "tsa_us", "mises_en_chantier_us", "ciment_us"]
    presents = {i["cle"] for i in indicateurs if i.get("valeur") is not None}
    return [k for k in ordre if k in presents]


# ------------------------------------------------------------------ écritures

def recap_markdown(jour: date, d: dict, nouveaux: list[dict], etats: dict) -> str:
    l = [f"# Agent données alternatives — récapitulatif du {A.date_fr(jour.isoformat())}", "",
         "Indicateurs avancés de l'activité réelle. Aucune conclusion n'est tirée d'un seul indicateur.", "", "## Activité réelle par pays", ""]
    for p in d["pays"]:
        if p.get("score") is None:
            l.append(f"- {p['nom']} : pas de score ({p['raison']})")
            continue
        l.append(f"- **{p['nom']}** : « {p['lecture']} », score {A.fr(p['score'], 0)}/100, confiance {p['confiance']['niveau']}"
                 + (f" — divergence : {p['divergence']['texte']}" if p.get("divergence") else ""))
    l += ["", "## Indicateurs mondiaux", ""]
    par_cle = {i["cle"]: i for i in d["indicateurs"]}
    l += [f"- {par_cle[k]['lecture']} (donnée du {A.date_fr(par_cle[k]['date'])})" for k in d["tableau_mondial"]]
    l += ["", "## Signaux détectés aujourd'hui", ""] + ([f"- [{s['importance']}] {s['titre']}" for s in nouveaux] or ["- aucun"])
    erreurs = [k for k, v in etats.items() if v not in ("ok", "non configurée")]
    l += ["", "## Sources en échec", ""] + ([f"- {k} : {etats[k]}" for k in erreurs] or ["- aucune"])
    ignores = sorted(k for k, v in etats.items() if v == "non configurée")
    if ignores:
        l += ["", f"Sources ignorées (clé ou adresse absente) : {', '.join(ignores)}."]
    return "\n".join(l) + "\n"


def sources_sante(inds: list[dict], etats: dict, etats_attention: dict) -> list[dict]:
    """Une ligne par source (et non par indicateur) : les indicateurs d'une même source sont regroupés."""
    groupes: dict[str, list[str]] = {}
    noms = {}
    for ind in inds:
        g = ind["source"] if ind["source"] not in ("csv_url",) else f"csv_url:{ind['params']['variable']}"
        if ind["source"] in ("fred", "dbnomics"):
            g = f"{ind['source']}:{ind['cle']}"
        groupes.setdefault(g, []).append(ind["cle"])
        noms[g] = ind["source_nom"].split(" (")[0] + (f" — {ind['nom']}" if ind["source"] in ("fred", "dbnomics") else "")
    res = []
    for g, cles in groupes.items():
        e = [etats.get(k, "échec") for k in cles]
        if all(x == "non configurée" for x in e):
            variable = {"eia": "EIA_API_KEY", "entsoe": "ENTSOE_API_KEY"}.get(g, g.split(":")[-1])
            res.append({"nom": noms[g], "etat": "non configurée", "detail": f"{variable} absente : source ignorée"})
            continue
        ok = sum(x == "ok" for x in e)
        if ok == len(e):
            res.append({"nom": noms[g], "etat": "ok", "detail": f"{ok} série{'s' if ok > 1 else ''}"})
        elif ok:
            res.append({"nom": noms[g], "etat": "partielle", "detail": f"{ok}/{len(e)} séries : " + "; ".join(f"{k} {etats.get(k)}" for k in cles if etats.get(k) != "ok")[:200]})
        else:
            res.append({"nom": noms[g], "etat": "échec", "detail": "; ".join(str(x).removeprefix("erreur : ") for x in e)[:200]})
    for k, nom in (("wikipedia", "Wikipédia (API Wikimedia des consultations)"), ("trends", "Google Trends (pytrends, non officiel)")):
        v = etats_attention.get(k)
        if v is None:
            continue
        res.append({"nom": nom, "etat": "ok" if v == "ok" else "non configurée" if v == "non configurée" else "partielle",
                    "detail": "information seulement" if v == "ok" else ("bibliothèque pytrends absente : source ignorée" if v == "non configurée" else v)})
    return res


def indicateurs_sante(indicateurs: list[dict]) -> dict:
    """Un indicateur est « valide » quand sa donnée est à jour : une source qui tombe en panne ou devient
    périmée après avoir été valide rend l'agent « dégradé » (règle commune, voir agents/commun/sante.py)."""
    return {f"{i['nom']} ({i['pays']})": {"valides": ["source"] if i.get("valeur") is not None and not i.get("perimee") else [],
                                          "configurees": ["source"]} for i in indicateurs}


def ecrire_signaux(chemin: Path, nouveaux: list[dict], aujourdhui: date) -> list[dict]:
    existants = (lire_json(chemin) or {}).get("donnees") or []
    vus = {(s["type"], s["cle"], s["date"]) for s in existants}
    tous = existants + [s for s in nouveaux if (s["type"], s["cle"], s["date"]) not in vus]
    limite = (aujourdhui - timedelta(days=180)).isoformat()
    tous = sorted((s for s in tous if s["date"] >= limite), key=lambda s: s["date"], reverse=True)
    ecrire_json(chemin, enveloppe(tous, "agent-donnees-alternatives", fictif=False, version_agent=VERSION_AGENT,
                                  description="Signaux candidats pour le chef d'orchestre et le contradicteur (180 derniers jours)"))
    return tous


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent données alternatives : indicateurs avancés de l'activité réelle (sans IA)")
    ap.add_argument("--test", action="store_true", help="données de test (agents/donnees_alternatives/tests/donnees), sans réseau")
    ap.add_argument("--donnees-test", help="dossier des données de test (par défaut tests/donnees)")
    ap.add_argument("--capturer", action="store_true", help="enregistre les réponses réelles comme données de test")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier data/ (lecture des autres agents et écriture)")
    ap.add_argument("--surveillance", default=str(RACINE / "config" / "surveillance.json"), help="liste de surveillance")
    ap.add_argument("--sans-attention", action="store_true", help="ne pas interroger Wikipédia ni Google Trends")
    ap.add_argument("--date", help="date du jour (AAAA-MM-JJ), utile pour les tests")
    args = ap.parse_args(argv)

    cfg = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
    pays_cfg = json.loads((RACINE / "agents" / "pays" / "config.json").read_text(encoding="utf-8"))["pays"]
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    data = Path(args.data)
    dossier_test = Path(args.donnees_test) if args.donnees_test else DOSSIER / "tests" / "donnees"
    if args.test:
        f = FournisseurTest(dossier_test)
    else:
        f = FournisseurReel(RACINE / "agents" / ".cache")
        if args.capturer:
            f = Capture(f, dossier_test)
    LOG.info("Agent données alternatives %s — %s", VERSION_AGENT, "données de test" if args.test else "sources réelles")

    inds = indicateurs_config(cfg)
    series, etats, details = collecter(f, inds, aujourdhui)
    if not any(v == "ok" for v in etats.values()):
        LOG.error("Aucune source disponible : fichiers inchangés.")
        return 1
    dossier_hist = data / "historique" / "donnees_alternatives"
    series = accumuler(dossier_hist, inds, series, aujourdhui)

    ancien = lire_json(data / "donnees_alternatives.json")
    precedent = (ancien or {}).get("donnees") if ancien and (ancien.get("meta") or {}).get("fictif") is False else None
    officiels = {p["code"]: p for p in ((lire_json(data / "pays.json") or {}).get("donnees") or []) if isinstance(p, dict) and p.get("code")}
    indicateurs = analyser_indicateurs(inds, series, etats, cfg, aujourdhui)
    for i in indicateurs:
        if details.get(i["cle"]):
            i["detail_source"] = details[i["cle"]]
    pays = analyser_pays(indicateurs, pays_cfg, officiels, cfg, precedent)

    attention, etats_att = ([], {})
    if not args.sans_attention:
        attention, etats_att = analyser_attention(f, societes_suivies(Path(args.surveillance), data), cfg, aujourdhui, precedent)

    donnees = {
        "date": aujourdhui.isoformat(),
        "categories": cfg["categories"],
        "pays": pays,
        "indicateurs": indicateurs,
        "tableau_mondial": tableau_mondial(indicateurs),
        "attention": attention,
        "sources_ignorees": sorted({i["source_nom"] for i in inds if etats.get(i["cle"]) == "non configurée"}),
        "avertissement": "Indicateurs indirects, souvent révisés ou approchés : à lire ensemble, jamais un seul à la fois. Analyse factuelle, sans conseil d'investissement.",
        "methode": ("Note d'un indicateur /100 : 60 % percentile de sa variation sur 12 mois et 40 % percentile de son écart à la tendance "
                    "(moyenne 3 mois contre 12 mois), dans son propre historique (échelle fixe si l'historique est court). "
                    f"Score pays : moyenne pondérée des indicateurs à jour, au moins {cfg['score']['indicateurs_min']} ; "
                    f"« accélération » à partir de {cfg['score']['acceleration']} et « ralentissement » jusqu'à {cfg['score']['ralentissement']}, "
                    f"avec au moins {cfg['score']['concordants_min']} indicateurs dans le même sens, sinon « stable ». "
                    "Attention du public (Wikipédia, Google Trends) : information seulement, hors score."),
    }
    textes = [p["texte"] for p in pays] + [t for p in pays for t in p.get("ce_qui_pourrait_me_donner_tort", [])] + [i["lecture"] for i in indicateurs]
    if not A.conformes(textes):
        LOG.error("Un texte contient un mot interdit : vérifier les règles de rédaction.")
        return 1

    nouveaux = A.signaux(precedent, donnees, aujourdhui)
    ecrire_signaux(data / "signaux" / "donnees_alternatives.json", nouveaux, aujourdhui)
    tous_etats = {**etats, **{f"attention_{k}": v for k, v in etats_att.items()}}
    objet = enveloppe(donnees, "agent-donnees-alternatives", fictif=False, version_agent=VERSION_AGENT,
                      mise_a_jour_precedente=(ancien or {}).get("meta", {}).get("genere_le") if precedent else None,
                      etat_des_sources=tous_etats)
    ecrire_json(data / "donnees_alternatives.json", objet)
    ecrire_json(dossier_hist / f"{aujourdhui.isoformat()}.json", {
        "meta": {"genere_le": objet["meta"]["genere_le"], "source": "agent-donnees-alternatives", "version_agent": VERSION_AGENT,
                 "description": "Scores d'activité par pays et notes des indicateurs du jour"},
        "donnees": {"pays": {p["code"]: {"score": p.get("score"), "lecture": p.get("lecture")} for p in pays},
                    "indicateurs": {i["cle"]: {"valeur": i.get("valeur"), "date": i.get("date"), "note": i.get("note")} for i in indicateurs}}})
    (data / "recap").mkdir(parents=True, exist_ok=True)
    (data / "recap" / f"donnees-alternatives-{aujourdhui.isoformat()}.md").write_text(recap_markdown(aujourdhui, donnees, nouveaux, tous_etats), encoding="utf-8")

    chemin_journal = data / "journal" / FICHIER_JOURNAL
    j = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    j["donnees"] = (j.get("donnees", []) + [{"genere_le": objet["meta"]["genere_le"], "etat_des_sources": tous_etats,
                                             "signaux": [s["titre"] for s in nouveaux]}])[-90:]
    j["meta"] = {**j.get("meta", {}), "genere_le": objet["meta"]["genere_le"], "source": "agent-donnees-alternatives",
                 "version_agent": VERSION_AGENT, "description": "État des sources et signaux, à chaque exécution"}
    ecrire_json(chemin_journal, j)
    maintenant = (datetime.combine(aujourdhui, datetime.min.time(), timezone.utc).replace(hour=5, minute=40) if args.date
                  else datetime.now(timezone.utc))
    bloc = sante.bloc_sante("donnees-alternatives", "Agent données alternatives", 12, "agent-donnees-alternatives.yml",
                            sources_sante(inds, etats, etats_att), maintenant, (j.get("meta") or {}).get("sante"),
                            indicateurs=indicateurs_sante(indicateurs))
    sante.enregistrer_sante(chemin_journal, bloc, forcer=True)

    LOG.info("Pays : %s", ", ".join(f"{p['nom']} « {p['lecture']} » ({A.fr(p['score'], 0)})" for p in pays if p.get("score") is not None) or "aucun score")
    LOG.info("Signaux : %d ; santé : %d/%d sources, %s", len(nouveaux), bloc["sources_ok"], bloc["sources_total"],
             "dégradé" if bloc["degrade"] else "aucun indicateur dégradé")
    return 0
