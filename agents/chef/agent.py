"""
Chef d'orchestre : « Où investir maintenant, et avec quelle conviction ? »

Étapes (méthode complète : agents/chef/methode.md ; poids et seuils : agents/chef/config.json) :
1. entrées : sorties de tous les agents, pondérées par leur fraîcheur, la santé de l'agent et leur confiance
   (entrees.py) ;
2. univers : actions par pays, matières premières, or, obligations (États-Unis, zone euro ; courtes et longues),
   liquidités, puis entreprises (pépites, qualité à prix raisonnable, liste de surveillance, analyses à la
   demande, meilleures sociétés des pays attractifs) (univers.py) ;
3. moteur : familles de signaux normalisées, pondérations selon le palier de risque, score /100, verdict avec
   hystérésis, conviction, objections du contradicteur, concentrations thématiques (moteur.py) ;
4. allocation modèle indicative, trois profils, cœur-satellite (allocation.py) ;
5. synthèse : briefing quotidien (règles ou Gemini contrôlé), alertes du jour (data/alertes.json), agenda,
   revue hebdomadaire du samedi (synthese.py) ; dépôt facultatif sur Google Drive (drive.py) ;
6. suivi de performance des verdicts et calibration de la conviction (suivi.py).

Modes : « complet » (7 h 15 UTC, après les agents du matin) ; « leger » (toutes les heures pendant les marchés :
alertes, et verdicts touchés par un changement de palier de risque, un choc de marché ou un événement
géopolitique de gravité ≥ 4).
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
from ..risque.calculs import date_fr, fr
from . import allocation as A
from . import drive
from . import entrees as E
from . import moteur as M
from . import suivi as S
from . import synthese as Y
from . import univers as U
from .sources import FournisseurReel, FournisseurTest

LOG = journal("agent-chef")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
WORKFLOW = "agent-chef.yml"
TYPES_CHOC = ("pays", "entreprises", "matieres", "or")


def charger_config() -> dict:
    return json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))


def iso(t: datetime) -> str:
    return sante.iso(t)


# ------------------------------------------------------------------ déclencheurs du mode léger

def declencheurs(ctx: U.Contexte, entrees: dict, signaux: dict, etat: dict, config: dict, jour: str) -> tuple[list[str], set | None]:
    """Renvoie (raisons, identifiants touchés ; None = tout)."""
    cl = config["leger"]
    raisons, touches = [], set()
    tout = False
    if etat.get("palier") and ctx.palier != etat["palier"]:
        raisons.append(f"palier de risque : « {etat['palier']} » → « {ctx.palier} »")
        tout = True
    marches = entrees["marches"].donnees if entrees["marches"].disponible else []
    for m in marches or []:
        if m.get("symbole") in cl["indices_choc"] and m.get("variation") is not None and abs(m["variation"]) >= cl["choc_marche_pct"] and not m.get("ancienne"):
            cle = f"{m['symbole']}:{(m.get('heure') or '')[:10]}"
            if cle not in etat.get("chocs_vus", []):
                raisons.append(f"choc de marché : {m['nom']} {fr(m['variation'], 1, True)} %")
                etat.setdefault("chocs_vus", []).append(cle)
                touches.add("__choc__")
    vus = set(etat.get("evenements_vus", []))
    for s in signaux.get("geopolitique", []):
        if s.get("type") != "evenement_grave" or (s.get("date") or "") < jour:
            continue
        import re
        g = re.search(r"gravité (\d)", s.get("titre") or "")
        if g and int(g.group(1)) < cl["gravite_min"]:
            continue
        if s.get("cle") in vus:
            continue
        vus.add(s.get("cle"))
        raisons.append(f"événement géopolitique : {s.get('titre')}")
        for c in s.get("pays") or []:
            touches.add(f"pays-{c}")
        touches.add("__matieres__")
    etat["evenements_vus"] = sorted(vus)[-500:]
    etat["chocs_vus"] = (etat.get("chocs_vus") or [])[-200:]
    return raisons, (None if tout else touches)


def est_touche(o: dict, touches: set | None) -> bool:
    if touches is None:
        return True
    if o["id"] in touches:
        return True
    if "__choc__" in touches and o["type"] in TYPES_CHOC:
        return True
    if "__matieres__" in touches and o["type"] in ("matieres", "or"):
        return True
    if o["type"] == "entreprises" and f"pays-{o.get('pays')}" in touches:
        return True
    return False


# ------------------------------------------------------------------ décision

def decider(opps: list[dict], ctx: U.Contexte, objections: dict, entrees: dict, etat: dict, jour: str, config: dict) -> None:
    hyst = etat.setdefault("verdicts", {})
    for o in opps:
        M.scorer(o, config, ctx.palier)
        objs = objections.get(o["id"], [])
        agents = {x["agent"] for x in o["familles"].values()}
        frais = min([entrees[a].coef for a in agents if a in entrees] or [0])
        v_brut = M.verdict_de(o["score"], config)
        conv0 = M.conviction(o, v_brut, objs, frais, config)
        v_cap, plafond = M.plafonner_extreme(v_brut, conv0, config)
        o["verdict_brut"] = v_brut
        o["plafond"] = plafond
        if o["score"] is None:
            o.update({"verdict": "Neutre", "changement": None, "depuis": jour})
        else:
            M.appliquer_hysteresis(o, v_cap, hyst, jour, config)
        c = M.conviction(o, o["verdict"], objs, frais, config)
        if o["score"] is None:
            c = {"niveau": "faible", "groupes": [], "raisons": ["aucune donnée disponible"]}
        o["conviction"] = c["niveau"]
        o["conviction_detail"] = c
        o["_objections"] = objs


def ligne(o: dict, etat: dict, config: dict) -> dict:
    prec = (etat.get("scores_precedents") or {}).get(o["id"])
    o["score_precedent"] = prec
    o["fleche"] = M.fleche(o.get("score"), prec, config)
    l = M.ligne_publique(o, o.get("_objections", []), config)
    l["conviction_raisons"] = o["conviction_detail"]["raisons"]
    return l


def changements(lignes: list[dict]) -> list[dict]:
    res = []
    for l in lignes:
        c = l.get("changement")
        if not c or not c.get("de"):
            continue
        important = c["vers"] in ("Renforcer fortement", "Éviter") or c["de"] in ("Renforcer fortement", "Éviter") \
            or M.DIRECTION[c["vers"]] != M.DIRECTION[c["de"]]
        res.append({"id": l["id"], "date": c["date"], "pays": l.get("pays") if l["type"] == "pays" else None, "important": important,
                    "texte": f"{l['nom']} : « {c['de']} » → « {c['vers']} »", "explication": c["explication"]})
    return res


def vigilance(lignes: list[dict], conc: list[dict], entrees: dict, ctx: U.Contexte, jour: str) -> list[str]:
    res = [c["texte"] for c in conc]
    for x in entrees.values():
        if x.etat in ("périmée", "manquante") or x.degrade:
            res.append(f"Données : {x.libelle} {x.etat}{' et dégradé' if x.degrade else ''} — ses signaux pèsent moins.")
    att = ((ctx.risque.get("mondial") or {}).get("changement_en_attente") or {})
    if att.get("vers"):
        res.append(f"Agent risque : changement de palier en attente vers « {att['vers']} ».")
    lim = jour
    for e in (ctx.geo.get("evenements") or [])[:80]:
        if (e.get("gravite") or 0) >= 4 and (e.get("dernier") or "")[:10] >= lim:
            res.append(f"Géopolitique : {e.get('titre')} (gravité {e.get('gravite')}).")
            if sum(1 for x in res if x.startswith("Géopolitique")) >= 2:
                break
    for l in lignes:
        if M.DIRECTION.get(l["verdict"]) == 1 and l.get("objection") and l["objection"].get("serieuse"):
            res.append(f"{l['nom']} ({l['verdict'].lower()}) : objection du contradicteur — {l['objection']['objection']}")
    return res[:12]


# ------------------------------------------------------------------ exécution

def executer(f, config: dict, data: Path, maintenant: datetime, mode: str = "complet", cle_gemini: str | None = None,
             poster=None, horloge=None, dormir=None, deposer=True) -> dict:
    jour = maintenant.date().isoformat()
    entrees = E.charger(data, config, maintenant)
    disponibles = [x for x in entrees.values() if x.disponible]
    chemin_etat = data / "chef" / "etat.json"
    etat = lire_json(chemin_etat) or {}
    chemin_journal = data / "journal" / "agent-chef.json"
    jrn = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    raisons_sante = []
    if len(disponibles) < config["sante"]["entrees_min"]:
        raisons_sante.append(f"{len(disponibles)} entrées disponibles, moins que le minimum de {config['sante']['entrees_min']}")
        LOG.error("Trop peu d'entrées disponibles (%d) : fichiers inchangés.", len(disponibles))
        bloc = sante.bloc_sante("chef", "Chef d'orchestre", 10, WORKFLOW, sources_sante(entrees, None, None, None), maintenant,
                                (jrn.get("meta") or {}).get("sante"), raisons_supplementaires=raisons_sante)
        sante.enregistrer_sante(chemin_journal, bloc, forcer=True)
        return {"ok": False, "sante": bloc}

    ctx = U.Contexte(entrees, config, data)
    signaux = E.signaux(data)
    revues = (entrees["revues"].donnees or []) if entrees["revues"].disponible else []
    precedent = lire_json(data / "chef.json")
    prec_donnees = (precedent or {}).get("donnees") or {}
    raisons_leger, touches = [], None
    # Déclencheurs : évalués à chaque exécution, pour que la mise à jour légère ne réagisse qu'aux nouveautés
    raisons_d, touches_d = declencheurs(ctx, entrees, signaux, etat, config, jour)
    if mode == "leger":
        raisons_leger, touches = raisons_d, touches_d
        if not precedent:
            touches = None  # pas d'analyse précédente : analyse complète
    recalcul = mode == "complet" or not precedent or bool(raisons_leger)

    lignes, alloc, conc, chg = [], prec_donnees.get("allocation"), prec_donnees.get("concentrations") or [], []
    rapport_gemini = {"cle": bool(cle_gemini), "appels": 0, "reussites": 0, "rejets": [], "erreurs": [], "quota_atteint": False}
    briefing, suivi_r = None, None
    if recalcul:
        objections = M.objections_par_cible(revues, signaux, ctx.zones_pays, jour, config)
        pays = U.opportunites_pays(ctx)
        U.normaliser(pays, config)
        matieres, or_ = U.opportunites_matieres(ctx)
        U.normaliser(matieres, config)
        obligs, liqs = U.opportunites_obligations(ctx)
        etat_travail = json.loads(json.dumps(etat))  # l'hystérésis n'est validée que pour les opportunités touchées
        premiers = pays + matieres + ([or_] if or_ else []) + obligs + liqs
        decider(premiers, ctx, objections, entrees, etat_travail, jour, config)
        attractifs = [o["cle"] for o in pays if M.DIRECTION.get(o["verdict"]) == 1]
        for o in pays:
            if o["cle"] in attractifs:
                o["societes"] = [{"ticker": e["ticker"], "nom": e.get("nom"), "note": e.get("note"),
                                  "recommandation": (e.get("recommandation") or {}).get("n")} for e in U.meilleures_du_pays(ctx, o["cle"])]
        fam_pays = {o["cle"]: o["familles"] for o in pays}
        selection = U.selection_entreprises(ctx, attractifs)
        entreprises = U.opportunites_entreprises(ctx, selection, fam_pays)
        decider(entreprises, ctx, objections, entrees, etat_travail, jour, config)
        anciennes = {l["id"]: l for t in ("pays", "matieres", "obligations", "liquidites", "entreprises") for l in (prec_donnees.get(t) or [])}
        if prec_donnees.get("or"):
            anciennes["or"] = prec_donnees["or"]
        for o in premiers + entreprises:
            if mode == "leger" and not est_touche(o, touches) and o["id"] in anciennes:
                lignes.append(anciennes[o["id"]])
                continue
            if o["id"] in etat_travail.get("verdicts", {}):
                etat.setdefault("verdicts", {})[o["id"]] = etat_travail["verdicts"][o["id"]]
            lignes.append(ligne(o, etat, config))
        conc = M.concentrations(lignes, config)
        chg = changements([l for l in lignes if (l.get("changement") or {}).get("date") == jour])
        if mode == "complet" or touches is None:
            # Rotation mesurée par rapport à l'allocation de la veille (plusieurs exécutions le même jour : même référence)
            if prec_donnees.get("date") != jour:
                etat["allocation_veille"] = (prec_donnees.get("allocation") or {}).get("profils")
            alloc = A.construire(lignes, ctx.palier, etat.get("allocation_veille"), config)
        if mode == "complet":
            etat["scores_precedents"] = {l["id"]: l.get("score") for l in lignes}
        etat["palier"] = ctx.palier
    else:
        for t in ("pays", "matieres", "obligations", "liquidites", "entreprises"):
            lignes += prec_donnees.get(t) or []
        if prec_donnees.get("or"):
            lignes.append(prec_donnees["or"])

    lignes_par = {t: [l for l in lignes if l["type"] == t] for t in ("pays", "matieres", "obligations", "liquidites", "entreprises", "or")}
    for t in lignes_par:
        lignes_par[t].sort(key=lambda l: -(l.get("score") or 0))
    vig = vigilance(lignes, conc, entrees, ctx, jour)
    phase_monde = ctx.phase("monde")
    mondial = ctx.risque.get("mondial") or {}

    # Alertes : à chaque exécution
    tickers_appli = set(ctx.par_ticker)
    al = Y.alertes(signaux, revues, chg, maintenant, config, tickers_appli)
    ecrire_json(data / "alertes.json", enveloppe(al, "agent-chef", fictif=False, version_agent=VERSION_AGENT,
                                                 aucune="Aucune alerte notable" if not al else None,
                                                 description="Les 3 ou 4 signaux les plus importants des agents (moins de 48 h), filtrés par les objections du contradicteur"))

    # Briefing quotidien (analyse complète)
    if mode == "complet":
        sc = Y.scenarios(ctx.macro, ctx.risque)
        tops = Y.top(lignes)
        ctx_b = {"lignes": lignes, "palier": ctx.palier, "risque_mondial": mondial, "phase_monde": phase_monde, "changements": chg, "vigilance": vig}
        regles = Y.briefing_regles(ctx_b)
        redige = None
        if cle_gemini:
            from ..geopolitique import ia
            import time
            quotas = ia.Quotas(etat, config["gemini"], horloge=horloge, dormir=dormir or time.sleep)
            redige = Y.briefing_gemini(regles, sc, quotas, config["gemini"], cle_gemini, poster, rapport_gemini)
            rapport_gemini["quota"] = quotas.resume()
        b = {**regles, **(redige or {})}
        surveillance = [{"ticker": e["ticker"], "nom": e.get("nom")} for e in ctx.entreprises if e.get("surveillance")]
        resultats = []
        if config["agenda"]["resultats_surveillance"] and surveillance:
            try:
                resultats = f.resultats(surveillance)
            except Exception as e:  # noqa: BLE001
                LOG.warning("Dates de résultats indisponibles : %s", str(e)[:120])
        donnees_b = [f"{x.libelle} : {x.etat}" + (f" ({fr(x.age_h, 0)} h)" if x.age_h is not None else "") + (" — dégradé" if x.degrade else "") for x in entrees.values()]
        briefing = {"date": jour, "genere_le": iso(maintenant), "mode": b["mode"], "modele": b.get("modele"), "palier": ctx.palier, "phase_monde": phase_monde,
                    "essentiel": b["essentiel"], "vigilance": b["vigilance"], "rubriques_regles": b.get("rubriques_regles", []),
                    "affirmations_supprimees": b.get("supprimees", []),
                    "ou_investir": [{"id": l["id"], "nom": l["nom"], "type": l["type"], "verdict": l["verdict"], "conviction": l["conviction"], "score": l["score"],
                                     "argument": (l["pour"][0]["texte"] if l.get("pour") else None)} for l in tops],
                    "changements": chg, "scenarios": sc, "agenda": Y.agenda(maintenant.date(), ctx.macro, config, resultats),
                    "donner_tort": ([tops[0]["donner_tort"][0]] if tops and tops[0].get("donner_tort") else []) + sc["alternatif"]["declencheurs"][:2],
                    "donnees": donnees_b, "faits": regles["faits"], "mention": config["mention"]}
        d_chef = data / "chef"
        d_chef.mkdir(parents=True, exist_ok=True)
        (d_chef / f"briefing-{jour}.md").write_text(Y.briefing_markdown(briefing), encoding="utf-8")
        ecrire_json(d_chef / f"briefing-{jour}.json", enveloppe(briefing, "agent-chef", fictif=False, version_agent=VERSION_AGENT))
        briefing["drive"] = drive.deposer([d_chef / f"briefing-{jour}.md", d_chef / f"briefing-{jour}.json"]) if deposer else {"etat": "non configurée", "detail": "désactivé"}
        # Suivi de performance
        suivi_r = S.executer(data, lignes, jour, config["suivi"], series_fn=f.series)
    else:
        briefing = (lire_json(data / "chef" / f"briefing-{jour}.json") or {}).get("donnees")
    if suivi_r is None:
        suivi_meta = (lire_json(data / "chef" / "suivi.json") or {}).get("meta") or {}
        suivi_r = {"fiabilite": suivi_meta.get("fiabilite"), "total": suivi_meta.get("nombre", 0)}

    # data/chef.json
    top5 = Y.top(lignes)
    donnees = {
        "date": jour if recalcul else prec_donnees.get("date", jour), "mode": mode, "maj": iso(maintenant),
        "declencheurs": raisons_leger,
        "regime": {"palier": ctx.palier, "score_risque": mondial.get("score"), "phase_monde": phase_monde,
                   "phases": {z: ctx.phase(z) for z in ("monde", "etats_unis", "zone_euro", "chine", "japon", "emergents")},
                   "poids": M.poids("pays", config, ctx.palier), "multiplicateurs": config["regimes"].get(ctx.palier) or {}},
        "synthese": {"top3": [{"id": l["id"], "nom": l["nom"], "type": l["type"], "verdict": l["verdict"], "conviction": l["conviction"], "score": l["score"]} for l in top5[:3]],
                     "essentiel": [x["texte"] for x in (briefing or {}).get("essentiel", [])], "briefing": f"data/chef/briefing-{(briefing or {}).get('date', jour)}.json" if briefing else None,
                     "alertes": len(al)},
        "pays": lignes_par["pays"], "matieres": lignes_par["matieres"], "or": (lignes_par["or"] or [None])[0],
        "obligations": lignes_par["obligations"], "liquidites": lignes_par["liquidites"], "entreprises": lignes_par["entreprises"],
        "concentrations": conc, "changements": chg if recalcul else prec_donnees.get("changements", []), "vigilance": vig, "allocation": alloc,
        "entrees": [x.resume() for x in entrees.values()],
        "fiabilite": {"total": suivi_r.get("total"), "fiabilite": suivi_r.get("fiabilite")},
        "verdicts": config["verdicts"]["ordre"], "seuils": config["verdicts"]["seuils"],
        "methode": "Score /100 : moyenne des familles de signaux (fondamentaux, valorisation, tendance, flux, cycle, risque, géopolitique, initiés, "
                   "dynamique des résultats), normalisées en percentiles dans leur classe et pondérées selon le palier de risque, la fraîcheur et la "
                   "confiance des données ; verdict avec hystérésis ; conviction forte = au moins 3 groupes de signaux indépendants concordants, "
                   "données fiables et fraîches, sans objection sérieuse du contradicteur. Détails : agents/chef/methode.md.",
        "mention": config["mention"],
    }
    ancien_meta = (precedent or {}).get("meta") or {}
    objet = enveloppe(donnees, "agent-chef", fictif=False, version_agent=VERSION_AGENT, mise_a_jour_precedente=ancien_meta.get("genere_le"))
    objet["meta"]["genere_le"] = iso(maintenant)
    ecrire_json(data / "chef.json", objet)
    if mode == "complet":
        ecrire_json(data / "historique" / "chef" / f"{jour}.json", {
            "meta": {"genere_le": iso(maintenant), "source": "agent-chef", "version_agent": VERSION_AGENT},
            "donnees": {"palier": ctx.palier, "phase_monde": phase_monde,
                        "lignes": {l["id"]: {"score": l.get("score"), "verdict": l["verdict"], "conviction": l["conviction"]} for l in lignes},
                        "changements": [c["texte"] for c in chg],
                        "allocation": {k: p["classes"] for k, p in ((alloc or {}).get("profils") or {}).items()}}})
        if maintenant.weekday() == 5:
            hist = {}
            for i in range(7):
                d = (maintenant.date() - timedelta(days=i)).isoformat()
                h = lire_json(data / "historique" / "chef" / f"{d}.json")
                if h:
                    hist[d] = h.get("donnees") or {}
            (data / "recap").mkdir(parents=True, exist_ok=True)
            (data / "recap" / f"chef-hebdo-{jour}.md").write_text(
                Y.hebdo_markdown(jour, hist, lignes, alloc or {}, suivi_r.get("fiabilite") or {}, config["suivi"]), encoding="utf-8")

    # Journal et santé
    entree = {"genere_le": iso(maintenant), "mode": mode, "recalcul": recalcul, "declencheurs": raisons_leger, "palier": ctx.palier,
              "opportunites": len(lignes), "changements": [c["texte"] for c in chg], "alertes": len(al),
              "briefing": (briefing or {}).get("mode") if mode == "complet" else None,
              "gemini": {k: rapport_gemini.get(k) for k in ("appels", "reussites", "quota_atteint")} | {"rejets": rapport_gemini["rejets"][:10], "erreurs": [e[:200] for e in rapport_gemini["erreurs"]][:5]},
              "suivi": {k: suivi_r.get(k) for k in ("ajoutes", "mesures", "en_attente", "total", "erreur")},
              "entrees": {x.cle: x.etat + (" (dégradé)" if x.degrade else "") for x in entrees.values()}}
    jrn = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    jrn["donnees"] = (jrn.get("donnees", []) + [entree])[-200:]
    jrn["meta"] = {**jrn.get("meta", {}), "genere_le": iso(maintenant), "source": "agent-chef", "version_agent": VERSION_AGENT,
                   "description": "Entrées, recalcul, changements de verdict, alertes et briefing, à chaque exécution"}
    ecrire_json(chemin_journal, jrn)
    bloc = sante.bloc_sante("chef", "Chef d'orchestre", 10, WORKFLOW,
                            sources_sante(entrees, rapport_gemini if mode == "complet" else None, (briefing or {}).get("drive") if mode == "complet" else None,
                                          suivi_r if mode == "complet" else None),
                            maintenant, (jrn.get("meta") or {}).get("sante"), raisons_supplementaires=raisons_sante)
    bloc["palier"] = ctx.palier
    sante.enregistrer_sante(chemin_journal, bloc, forcer=True)

    etat["maj"] = iso(maintenant)
    ecrire_json(chemin_etat, etat, compact=True)
    LOG.info("Mode %s%s ; palier « %s » ; %d opportunités ; %d changement(s) ; %d alerte(s) ; briefing : %s",
             mode, f" (recalcul : {', '.join(raisons_leger)})" if raisons_leger else (" (sans recalcul)" if not recalcul else ""),
             ctx.palier, len(lignes), len(chg), len(al), (briefing or {}).get("mode") if mode == "complet" else "inchangé")
    LOG.info("Statut santé : %s%s", "DÉGRADÉ" if bloc["degrade"] else "OK", (" — " + " | ".join(bloc["raisons"])) if bloc["raisons"] else "")
    return {"ok": True, "donnees": donnees, "lignes": lignes, "alertes": al, "briefing": briefing, "sante": bloc, "etat": etat,
            "recalcul": recalcul, "changements": chg, "suivi": suivi_r, "gemini": rapport_gemini}


def sources_sante(entrees: dict, gemini: dict | None, depot: dict | None, suivi_r: dict | None) -> list[dict]:
    res = []
    for x in entrees.values():
        if x.etat == "manquante":
            etat, detail = "échec", "fichier absent ou illisible"
        elif x.etat == "périmée":
            etat, detail = "périmée", f"donnée de {fr(x.age_h, 0)} h (au-delà de {x.cfg['age_max_h']} h) : pèse moins"
        else:
            etat, detail = "ok", f"{x.etat} ({fr(x.age_h, 0)} h)" if x.age_h is not None else x.etat
        if x.degrade and etat == "ok":
            detail += " ; agent dégradé : pèse moins"
        res.append({"nom": f"{x.libelle} (data/{x.cfg['fichier']})", "etat": etat, "detail": detail, "derniere_donnee_valide": x.genere_le})
    if gemini is not None:
        nom = "Gemini (rédaction du briefing)"
        if not gemini["cle"]:
            res.append({"nom": nom, "etat": "non configurée", "detail": "secret GEMINI_API_KEY absent : briefing par règles"})
        elif gemini["erreurs"] and not gemini["reussites"] and not all("429" in e for e in gemini["erreurs"]):
            res.append({"nom": nom, "etat": "échec", "detail": "; ".join(gemini["erreurs"])[-300:]})
        else:
            q = gemini.get("quota") or {}
            res.append({"nom": nom, "etat": "ok", "detail": f"{gemini['appels']} appel(s) ; {q.get('appels', 0)}/{q.get('quota_jour', '?')} aujourd'hui (budget propre au chef d'orchestre)"})
    if depot is not None:
        res.append({"nom": "Google Drive (dépôt du briefing, facultatif)", "etat": depot["etat"], "detail": depot["detail"]})
    if suivi_r is not None:
        res.append({"nom": "Yahoo Finance (suivi de performance des verdicts)", "etat": "échec" if suivi_r.get("erreur") else "ok",
                    "detail": suivi_r.get("erreur") or f"{suivi_r.get('mesures', 0)} mesure(s) ; {suivi_r.get('en_attente', 0)} verdict(s) arrivé(s) à échéance"})
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chef d'orchestre : où investir maintenant, et avec quelle conviction ?")
    ap.add_argument("--test", action="store_true", help="réponses Yahoo enregistrées (agents/chef/tests/donnees), sans réseau ni Gemini")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier des données (data/)")
    ap.add_argument("--mode", choices=["complet", "leger"], default="complet")
    ap.add_argument("--maintenant", help="heure simulée (ISO, UTC)")
    ap.add_argument("--sans-ia", action="store_true", help="n'appelle pas Gemini")
    args = ap.parse_args(argv)
    config = charger_config()
    maintenant = sante.lire_iso(args.maintenant) if args.maintenant else datetime.now(timezone.utc)
    f = FournisseurTest(DOSSIER / "tests" / "donnees") if args.test else FournisseurReel()
    cle = "" if (args.sans_ia or args.test) else os.environ.get("GEMINI_API_KEY", "")
    LOG.info("Chef d'orchestre %s — %s, mode %s", VERSION_AGENT, "données de test" if args.test else "sources réelles", args.mode)
    r = executer(f, config, Path(args.data), maintenant, args.mode, cle_gemini=cle, deposer=not args.test)
    return 0 if r["ok"] else 1
