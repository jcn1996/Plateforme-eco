"""
Agent trader (démo) : gère un portefeuille VIRTUEL de 100 000 € à partir des recommandations du chef d'orchestre,
pour mesurer en conditions réelles ce que vaut la plateforme. Aucun ordre réel, jamais.

Règles : agents/trader/regles.md ; paramètres : agents/trader/config.json.

À chaque exécution :
1. exécution des ordres en attente au premier cours disponible après leur décision (frais, écart achat/vente,
   change du jour) ;
2. valorisation (Yahoo Finance ; agent marchés pour l'indice de référence et l'euro-dollar quand il est à jour) et
   point quotidien de l'historique, comparé au MSCI World en euros ;
3. contrôles de risque : stops des satellites, prise de bénéfices partielle, sorties sur « Alléger » / « Éviter » ou
   objection sérieuse, plancher de liquidités selon le palier de l'agent risque ;
4. décision (mode « decision », vers 7 h 30 UTC, ou première exécution horaire du jour où les données sont prêtes) :
   cibles cœur-satellites et ordres, exécutés à l'ouverture des marchés concernés. Aucune décision si les données
   du chef d'orchestre ou de l'agent risque sont périmées ou dégradées : l'agent attend et le note.

Sorties : data/portefeuille.json (écran « Portefeuille démo »), data/trader/operations.json (journal des
opérations), data/trader/etat.json (positions, ordres en attente, historique), data/journal/agent-trader.json
(écran « Santé »).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from ..risque.calculs import date_fr, fr
from . import performance as F
from . import portefeuille as P
from . import strategie as S

LOG = journal("agent-trader")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
WORKFLOW = "agent-trader.yml"
LIBELLES_POCHES = {"coeur": "Cœur", "satellite": "Satellites", "liquidites": "Liquidités"}


def charger_config() -> dict:
    return json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))


def iso(t: datetime) -> str:
    return sante.iso(t)


# ------------------------------------------------------------------ entrées

def verifier_entree(nom: str, objet: dict | None, journal_agent: dict | None, age_max_h: float, maintenant: datetime) -> dict:
    """État d'une entrée : à jour et saine, sinon raisons (absente, périmée, agent dégradé)."""
    raisons = []
    meta = (objet or {}).get("meta") or {}
    genere = sante.lire_iso(meta.get("genere_le"))
    age = round((maintenant - genere).total_seconds() / 3600, 1) if genere else None
    if not objet or objet.get("donnees") is None:
        raisons.append(f"{nom} : fichier absent ou illisible")
    elif age is None:
        raisons.append(f"{nom} : date de génération inconnue")
    elif age > age_max_h:
        raisons.append(f"{nom} : données de {fr(age, 0)} h (au-delà de {age_max_h} h)")
    s = ((journal_agent or {}).get("meta") or {}).get("sante") or {}
    if s.get("degrade"):
        raisons.append(f"{nom} : agent dégradé ({'; '.join((s.get('raisons') or [])[:2]) or 'sans détail'})")
    return {"ok": not raisons, "raisons": raisons, "age_h": age, "genere_le": meta.get("genere_le")}


def valeur_indice(marches: dict | None, cours: dict, taux: dict, config: dict, maintenant: datetime) -> tuple[float | None, str]:
    """Cours de l'ETF URTH (MSCI World) en euros : agent marchés s'il est à jour (moins de 26 h), sinon Yahoo Finance."""
    ci = config["performance"]["indice"]
    urth = eurusd = None
    source = "Yahoo Finance"
    for m in ((marches or {}).get("donnees") or []):
        t = sante.lire_iso(m.get("heure"))
        if not t or m.get("ancienne") or (maintenant - t).total_seconds() > 26 * 3600:
            continue
        if m.get("symbole") == ci["symbole"]:
            urth = m.get("valeur")
        elif m.get("symbole") == ci["change"]:
            eurusd = m.get("valeur")
    if urth and eurusd:
        source = "agent marchés"
    urth = urth or (cours.get(ci["symbole"]) or {}).get("cours")
    eurusd = eurusd or taux.get("USD")
    if not urth or not eurusd:
        return None, "indisponible"
    return urth / eurusd, source


# ------------------------------------------------------------------ décision

def decider(f, etat: dict, chef: dict, palier: str, valo: dict, operations: list, config: dict, maintenant: datetime) -> dict:
    jour = maintenant.date().isoformat()
    annules = []
    for o in etat.get("ordres", []):
        if o.get("statut") == "en attente" and not o.get("imposee"):
            o["statut"] = "annulé"
            o["note"] = "remplacé par la décision du jour"
            annules.append(o)
    etat["ordres"] = [o for o in etat.get("ordres", []) if o.get("statut") == "en attente"]
    libelle = ((((chef.get("allocation") or {}).get("profils") or {}).get(config["profil"])) or {}).get("libelle", config["profil"])
    config = {**config, "profil_libelle": libelle}
    etat["profil_libelle"] = libelle
    entrees_ko = {e["cle"] for e in chef.get("entrees") or [] if e.get("etat") in ("périmée", "manquante") or e.get("degrade")}
    lignes = S.lignes_chef(chef)
    cs = config["satellites"]
    # volatilités des candidats satellites (et devises de cotation des nouvelles sociétés)
    cand = [l for l in lignes.values() if l["type"] in cs["types"] and l.get("verdict") in cs["verdicts"] and l.get("conviction") in cs["convictions"]]
    symboles = sorted({s["symbole"] for l in cand for s in S.supports_de(l, config)})
    vols, erreurs = {}, []
    try:
        series = f.series(symboles, 190) if symboles else {}
        vols = {s: S.volatilite(p, cs["volatilite_jours"]) for s, p in series.items()}
        vols = {s: v for s, v in vols.items() if v is not None}
    except Exception as e:  # noqa: BLE001 — volatilité par défaut de la classe
        erreurs.append(f"séries de cours : {type(e).__name__}: {str(e)[:120]}")
    inconnues = [s for l in cand if l["type"] == "entreprises" for s in [l.get("symbole")] if s and s not in etat.setdefault("devises", {})]
    if inconnues:
        try:
            etat["devises"].update(f.devises(inconnues))
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"devises : {type(e).__name__}: {str(e)[:120]}")
    c = S.cibles(chef, palier, etat, valo, vols, entrees_ko, config, maintenant)
    ordres, notes = S.generer_ordres(c, etat, valo, operations, palier, config, maintenant)
    etat["ordres"].extend(ordres)
    poches = {"coeur": 0.0, "satellite": 0.0}
    classes = {}
    for e in c["lignes"].values():
        poches[e["poche"]] += e["cible"]
        classes[e["classe"]] = classes.get(e["classe"], 0) + e["cible"]
    poches["liquidites"] = c["liquidites"]
    classes["liquidites"] = c["liquidites"]
    sats = sorted([e for e in c["lignes"].values() if e["poche"] == "satellite"], key=lambda e: -e["cible"])
    achats = [o for o in ordres if o["sens"] == "achat"]
    ventes = [o for o in ordres if o["sens"] == "vente"]
    resume = (f"Décision du {date_fr(jour)} : palier « {palier} », liquidités minimales {fr(c['liquidites_min'], 0)} %. Cibles : cœur {fr(poches['coeur'], 1)} %, "
              f"satellites {fr(poches['satellite'], 1)} % ({len(sats)} ligne(s)), liquidités {fr(c['liquidites'], 1)} %. "
              f"{len(achats)} achat(s) et {len(ventes)} vente(s) à exécuter au premier cours disponible"
              + (f" ; {len(annules)} ordre(s) non exécuté(s) de la veille remplacé(s)." if annules else "."))
    donner_tort = [f"Le palier de risque peut monter : en « Tension », la part minimale de liquidités passerait à "
                   f"{fr(config['liquidites_min_par_palier'].get('Tension'), 0)} % et des ventes seraient imposées."]
    if sats:
        l0 = sats[0].get("ligne") or {}
        if l0.get("donner_tort"):
            donner_tort.append(f"{l0.get('nom')} (premier satellite) : {l0['donner_tort'][0]}")
    donner_tort.append("Le cœur suit l'allocation modèle du chef d'orchestre : si ses verdicts se révèlent mal calibrés (écran « Fiabilité du chef "
                       "d'orchestre »), l'écart au MSCI World le montrera.")
    decision = {"date": jour, "le": iso(maintenant), "palier": palier, "profil": config["profil"], "liquidites_min": c["liquidites_min"],
                "cibles": {"poches": {k: round(v, 2) for k, v in poches.items()}, "classes": {k: round(v, 2) for k, v in classes.items()},
                           "lignes": [{"symbole": k, "nom": e["support"].get("nom"), "poche": e["poche"], "classe": e["classe"], "cible": round(e["cible"], 2),
                                       "ligne_id": (e.get("ligne") or {}).get("id"), "tenue": bool(e.get("tenue"))}
                                      for k, e in sorted(c["lignes"].items(), key=lambda kv: -kv[1]["cible"])]},
                "ordres": [o["id"] for o in ordres], "achats": len(achats), "ventes": len(ventes), "annules": len(annules),
                "resume": resume, "notes": notes, "avertissements": c["avertissements"], "satellites_ecartes": c["satellites_ecartes"][:20],
                "donner_tort": donner_tort, "erreurs": erreurs, "chef_date": chef.get("date"), "chef_maj": chef.get("maj")}
    etat["derniere_decision"] = decision
    etat["derniere_decision_jour"] = jour
    etat["attente"] = None
    return decision


# ------------------------------------------------------------------ sortie

def repartition(etat: dict, valo: dict, noms_pays: dict) -> dict:
    val = valo["valeur"] or 1
    poches, classes, pays, secteurs = {"liquidites": valo["liquidites"]}, {"liquidites": valo["liquidites"]}, {}, {}
    for p in etat["positions"].values():
        v = p.get("valeur_eur", 0)
        poches[p.get("poche")] = poches.get(p.get("poche"), 0) + v
        classes[p.get("classe")] = classes.get(p.get("classe"), 0) + v
        if p.get("classe") in ("or", "matieres"):
            pa = "Monde (or, matières premières)"
        else:
            pa = noms_pays.get(p.get("pays"), p.get("pays") or "Autre")
        pays[pa] = pays.get(pa, 0) + v
        if p.get("type") == "entreprises":
            se = p.get("secteur") or "Autre"
        else:
            se = {"pays": "ETF pays (multisectoriel)", "obligations": "Obligations d'État", "or": "Or", "matieres": "Matières premières"}.get(p.get("type"), "Autre")
        secteurs[se] = secteurs.get(se, 0) + v
    pays["Liquidités (euros)"] = valo["liquidites"]
    secteurs["Liquidités (euros)"] = valo["liquidites"]

    def liste(d, lib=None):
        return sorted([{"cle": k, "libelle": (lib or {}).get(k, k), "eur": round(v, 2), "pct": round(v / val * 100, 2)} for k, v in d.items() if v > 0.005],
                      key=lambda x: -x["eur"])
    return {"poches": liste(poches, LIBELLES_POCHES), "classes": liste(classes, S.LIBELLES_CLASSES), "pays": liste(pays), "secteurs": liste(secteurs)}


def position_publique(p: dict, noms_pays: dict) -> dict:
    valeur = p.get("valeur_eur", 0)
    pv = valeur - p["cout_total_eur"]
    cours = p.get("dernier_cours_local")
    stop = p.get("stop_local")
    return {"symbole": p["symbole"], "nom": p["nom"], "poche": p.get("poche"), "classe": p.get("classe"), "type": p.get("type"),
            "pays": p.get("pays"), "pays_nom": noms_pays.get(p.get("pays")), "secteur": p.get("secteur"), "ligne_id": p.get("ligne_id"),
            "ticker": p["symbole"] if p.get("type") == "entreprises" else None,
            "quantite": p["quantite"], "devise": p["devise"], "prix_revient_local": round(p["prix_revient_local"], 4),
            "prix_revient_eur": round(p["prix_revient_eur"], 4), "cours_local": round(cours, 4) if cours else None,
            "cours_eur": round(p.get("dernier_cours_eur") or 0, 4), "cours_le": p.get("dernier_cours_le"), "valeur": round(valeur, 2),
            "plus_value_eur": round(pv, 2), "plus_value_pct": round(pv / p["cout_total_eur"] * 100, 2) if p["cout_total_eur"] else None,
            "realise_eur": round(p.get("realise_eur", 0), 2), "poids": round(p.get("poids", 0), 2),
            "stop_local": round(stop, 4) if stop else None, "stop_type": p.get("stop_type"),
            "stop_distance_pct": round((stop / cours - 1) * 100, 1) if stop and cours else None,
            "prise_benefices_faite": p.get("prise_benefices_faite", False), "verdict": p.get("verdict"), "conviction": p.get("conviction"),
            "ouverte_le": p.get("ouverte_le"), "contango": p.get("contango", False)}


def sortie(etat: dict, valo: dict, stats: dict, operations: list, chef: dict | None, palier: str | None, config: dict, maintenant: datetime,
           attente: dict | None, indice_source: str) -> dict:
    noms_pays = {"EZ": "Zone euro", "DE": "Allemagne", "US": "États-Unis"}
    for l in (chef or {}).get("pays") or []:
        noms_pays[l["cle"]] = l["nom"]
    hist = [{"date": d, "portefeuille": round(h["portefeuille"], 2), "msci_world": round(h["msci_world"], 2) if h.get("msci_world") else None}
            for d, h in sorted((etat.get("historique") or {}).items())]
    ordres = [{"id": o["id"], "sens": o["sens"], "symbole": o["symbole"], "nom": o["nom"], "poche": o.get("poche"), "motif": o.get("motif"),
               "montant_eur": o.get("montant_eur"), "quantite": o.get("quantite"), "cree_le": o["cree_le"], "imposee": o.get("imposee"),
               "texte": (o.get("raison") or {}).get("texte"), "donner_tort": o.get("donner_tort", [])} for o in etat.get("ordres", [])]
    val = valo["valeur"]
    statut = ({"etat": "en attente", "texte": "Aucune décision : " + " ; ".join(attente["raisons"]), "depuis": attente.get("depuis")} if attente
              else {"etat": "actif", "texte": "Données à jour : décisions prises chaque jour de semaine vers 7 h 30 UTC."})
    if not etat["positions"] and not operations and etat.get("ordres"):
        statut = {"etat": "démarrage", "texte": f"{len(etat['ordres'])} ordre(s) en attente de l'ouverture des marchés concernés."}
    return {
        "capital_initial": etat["capital_initial"], "devise": "EUR", "date_debut": etat["date_debut"], "maj": iso(maintenant),
        "valeur_actuelle": round(val, 2), "liquidites": round(valo["liquidites"], 2), "liquidites_pct": round(valo["liquidites"] / val * 100, 2) if val else None,
        "investi": round(valo["positions"], 2), "gain_eur": round(val - etat["capital_initial"], 2),
        "statut": statut, "profil": config["profil"], "profil_libelle": etat.get("profil_libelle", config["profil"]), "palier": palier,
        "liquidites_min": S.palier_min(palier, config) if palier else None,
        "indice": {"nom": config["performance"]["indice"]["nom"], "source": indice_source, "reference": etat.get("reference_indice")},
        "statistiques": stats, "repartition": repartition(etat, valo, noms_pays),
        "cibles": (etat.get("derniere_decision") or {}).get("cibles", {}).get("poches"),
        "positions": sorted([position_publique(p, noms_pays) for p in etat["positions"].values()], key=lambda x: -x["valeur"]),
        "ordres_en_attente": ordres, "operations": list(reversed(operations[-30:])),
        "derniere_decision": etat.get("derniere_decision"), "historique": hist,
        "cours_manquants": valo.get("manquants", []),
        "regles": [f"Cœur ≈ {config['poches']['coeur']} % : allocation modèle « {etat.get('profil_libelle', config['profil'])} » du chef d'orchestre, rééquilibrée au-delà de "
                   f"{config['reequilibrage']['seuil_points']} points d'écart.",
                   f"Satellites ≈ {config['poches']['satellite']} % : convictions fortes et moyennes, {config['satellites']['max_ligne']} % maximum par ligne, "
                   "taille selon la conviction et la volatilité.",
                   "Liquidités minimales selon le palier de risque : " + ", ".join(f"{k} {v} %" for k, v in config["liquidites_min_par_palier"].items()) + ".",
                   f"Stop −{config['stops']['stop_pct']} % sur les satellites (suiveur dès +{config['stops']['suiveur_declenchement_pct']} %), "
                   f"prise de bénéfices partielle à +{config['stops']['prise_benefices_pct']} %.",
                   f"Exécution au premier cours après la décision ; frais {fr(config['execution']['frais_pct'], 1)} % et écart achat/vente estimé ; change du jour.",
                   "Aucune décision sur données périmées ou dégradées ; aucune décision fondée sur une seule source."],
        "methode": "agents/trader/regles.md", "mention": config["mention"],
    }


def sources_sante(chef_e: dict, risque_e: dict, marches_e: dict, err_cours: str | None, manquants: list, nb_positions: int, err_exec: str | None) -> list[dict]:
    res = []
    for nom, e, fichier in (("Chef d'orchestre", chef_e, "chef.json"), ("Agent risque (palier)", risque_e, "risque.json")):
        etat = "ok" if e["ok"] else ("échec" if e["age_h"] is None else "périmée")
        res.append({"nom": f"{nom} (data/{fichier})", "etat": etat, "detail": "; ".join(e["raisons"]) or (f"{fr(e['age_h'], 0)} h" if e["age_h"] is not None else None),
                    "derniere_donnee_valide": e["genere_le"]})
    res.append({"nom": "Agent marchés (indice de référence, EUR/USD ; facultatif)", "etat": "ok" if marches_e["ok"] else "périmée",
                "detail": "; ".join(marches_e["raisons"]) or "à jour", "derniere_donnee_valide": marches_e["genere_le"]})
    if err_cours or err_exec:
        etat, detail = "échec", "; ".join(x for x in (err_cours, err_exec) if x)
    elif manquants:
        etat, detail = "partielle", f"cours manquants : {', '.join(manquants[:8])} (dernier cours connu conservé)"
    else:
        etat, detail = "ok", f"{nb_positions} position(s) valorisée(s)"
    res.append({"nom": "Yahoo Finance via yfinance (cours, change, exécution)", "etat": etat, "detail": detail})
    return res


# ------------------------------------------------------------------ exécution

def executer(f, config: dict, data: Path, maintenant: datetime, mode: str = "horaire") -> dict:
    f.maintenant = maintenant
    jour = maintenant.date().isoformat()
    d_trader = data / "trader"
    chemin_etat = d_trader / "etat.json"
    etat = lire_json(chemin_etat) or P.etat_initial(config, maintenant)
    ops_obj = lire_json(d_trader / "operations.json") or {"meta": {}, "donnees": []}
    operations = ops_obj.get("donnees") or []
    fr_ = config["fraicheur"]
    chef_obj, risque_obj, marches_obj = lire_json(data / "chef.json"), lire_json(data / "risque.json"), lire_json(data / "marches.json")
    chef_e = verifier_entree("chef d'orchestre", chef_obj, lire_json(data / "journal" / "agent-chef.json"), fr_["chef_h"], maintenant)
    risque_e = verifier_entree("agent risque", risque_obj, lire_json(data / "journal" / "agent-risque.json"), fr_["risque_h"], maintenant)
    marches_e = verifier_entree("agent marchés", marches_obj, lire_json(data / "journal" / "agent-marches.json"), 26, maintenant)
    chef = (chef_obj or {}).get("donnees") if chef_e["ok"] else None
    palier = (((risque_obj or {}).get("donnees") or {}).get("mondial") or {}).get("palier") if risque_e["ok"] else None
    lignes = S.lignes_chef(chef) if chef else None

    # 1. ordres en attente
    executees, annulees, err_exec = P.executer_ordres(etat, f, maintenant, config)
    operations.extend(executees)
    for op in executees:
        LOG.info("Exécuté : %s %d × %s à %s %s (%s)", op["sens"], op["quantite"], op["symbole"], fr(op["prix_local"], 2), op["devise"], op["motif"])

    # 2. valorisation
    ci = config["performance"]["indice"]
    err_cours, cours, taux = None, {}, {"EUR": 1.0}
    try:
        cours = f.derniers_cours(sorted(set(etat["positions"]) | {ci["symbole"]}))
        taux = f.change({P.devise_iso(p["devise"])[0] for p in etat["positions"].values()} | {"USD"})
    except Exception as e:  # noqa: BLE001 — derniers cours connus conservés
        err_cours = f"{type(e).__name__}: {str(e)[:150]}"
        LOG.warning("Cours indisponibles : %s", err_cours)
    valo = P.valoriser(etat, cours, taux)
    indice, indice_source = valeur_indice(marches_obj if marches_e["ok"] else None, cours, taux, config, maintenant)
    if indice and not etat.get("reference_indice"):
        etat["reference_indice"] = {"date": jour, "cours_eur": round(indice, 6), "parts": etat["capital_initial"] / indice,
                                    "note": "MSCI World (ETF URTH) converti en euros, base 100 000 € à la première valorisation."}
    ref = etat.get("reference_indice")
    etat.setdefault("historique", {})[jour] = {
        "portefeuille": round(valo["valeur"], 2), "msci_world": round(ref["parts"] * indice, 2) if ref and indice else (etat["historique"].get(jour) or {}).get("msci_world"),
        "liquidites_pct": round(valo["liquidites"] / valo["valeur"] * 100, 2) if valo["valeur"] else None}

    # 3. contrôles de risque
    nouveaux = S.controler_risques(etat, lignes, palier, valo, config, maintenant)
    etat.setdefault("ordres", []).extend(nouveaux)
    for o in nouveaux:
        LOG.info("Ordre imposé : %s %s — %s", o["sens"], o["symbole"], o["motif"])

    # 4. décision
    h, m = (int(x) for x in config["decision_heure_utc"].split(":"))
    du = mode == "decision" or (mode == "horaire" and etat.get("derniere_decision_jour") != jour and maintenant.weekday() < 5
                                and (maintenant.hour, maintenant.minute) >= (h, m))
    decision, bloquants = None, []
    if du:
        bloquants = list(chef_e["raisons"]) + list(risque_e["raisons"])
        if chef and not (data / "historique" / "chef" / f"{jour}.json").exists():
            bloquants.append("analyse complète du jour du chef d'orchestre pas encore disponible")
        if chef and not (((chef.get("allocation") or {}).get("profils") or {}).get(config["profil"])):
            bloquants.append(f"allocation modèle « {config['profil']} » absente de la sortie du chef d'orchestre")
        if err_cours and etat["positions"]:
            bloquants.append("cours indisponibles : portefeuille non valorisé")
        if not palier and not risque_e["raisons"]:
            bloquants.append("palier de l'agent risque inconnu")
        if bloquants:
            ancien = etat.get("attente") or {}
            etat["attente"] = {"le": iso(maintenant), "depuis": ancien.get("depuis") or iso(maintenant), "raisons": bloquants}
            LOG.warning("Aucune décision, l'agent attend : %s", " | ".join(bloquants))
        else:
            decision = decider(f, etat, chef, palier, valo, operations, config, maintenant)
            LOG.info("%s", decision["resume"])
    elif etat.get("attente") and etat.get("derniere_decision_jour") == jour:
        etat["attente"] = None

    # 5. sorties
    stats = F.statistiques(etat, operations, config)
    donnees = sortie(etat, valo, stats, operations, chef or (chef_obj or {}).get("donnees"), palier, config, maintenant, etat.get("attente"), indice_source)
    precedent = lire_json(data / "portefeuille.json") or {}
    objet = enveloppe(donnees, "agent-trader", fictif=False, version_agent=VERSION_AGENT, demo=True,
                      mise_a_jour_precedente=(precedent.get("meta") or {}).get("genere_le"),
                      description="Portefeuille virtuel de l'agent trader (démo) : aucun ordre réel")
    objet["meta"]["genere_le"] = iso(maintenant)
    ecrire_json(data / "portefeuille.json", objet)
    ops_obj = enveloppe(operations[-config["historique_operations_max"]:], "agent-trader", fictif=False, version_agent=VERSION_AGENT, demo=True,
                        description="Journal des opérations simulées (aucun ordre réel) : date, sens, support, quantité, prix, frais, raison, stop")
    ops_obj["meta"]["genere_le"] = iso(maintenant)
    ecrire_json(d_trader / "operations.json", ops_obj)
    etat["maj"] = iso(maintenant)
    ecrire_json(chemin_etat, etat)

    chemin_journal = data / "journal" / "agent-trader.json"
    jrn = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    entree = {"genere_le": iso(maintenant), "mode": mode, "valeur": round(valo["valeur"], 2), "liquidites_pct": donnees["liquidites_pct"],
              "palier": palier, "executees": [f"{o['sens']} {o['quantite']} {o['symbole']} ({o['motif']})" for o in executees],
              "annulees": [f"{o['sens']} {o['symbole']} : {o.get('note', o.get('statut'))}" for o in annulees],
              "ordres_imposes": [f"{o['sens']} {o['symbole']} ({o['motif']})" for o in nouveaux],
              "decision": (decision or {}).get("resume"), "attente": bloquants if du and bloquants else None,
              "ordres_en_attente": len(etat.get("ordres", [])), "cours_manquants": valo["manquants"][:10]}
    jrn["donnees"] = (jrn.get("donnees", []) + [entree])[-300:]
    jrn["meta"] = {**jrn.get("meta", {}), "genere_le": iso(maintenant), "source": "agent-trader", "version_agent": VERSION_AGENT,
                   "description": "Ordres exécutés, ordres imposés, décisions et attentes de l'agent trader (démo), à chaque exécution"}
    ecrire_json(chemin_journal, jrn)
    raisons = [f"décision en attente : {r}" for r in (etat.get("attente") or {}).get("raisons", [])]
    bloc = sante.bloc_sante("trader", "Agent trader (démo)", 11, WORKFLOW,
                            sources_sante(chef_e, risque_e, marches_e, err_cours, valo["manquants"], len(etat["positions"]), err_exec),
                            maintenant, (jrn.get("meta") or {}).get("sante"), raisons_supplementaires=raisons)
    sante.enregistrer_sante(chemin_journal, bloc, forcer=True)
    LOG.info("Valeur %s € (%s %% depuis le départ) ; liquidités %s %% ; %d position(s) ; %d ordre(s) en attente ; santé %s",
             fr(valo["valeur"], 0), fr(stats["performance"]["depuis_debut"], 2, True), fr(donnees["liquidites_pct"], 1), len(etat["positions"]),
             len(etat.get("ordres", [])), "DÉGRADÉ" if bloc["degrade"] else "OK")
    return {"ok": True, "donnees": donnees, "decision": decision, "executees": executees, "annulees": annulees, "imposes": nouveaux,
            "attente": etat.get("attente"), "sante": bloc, "etat": etat, "valo": valo}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent trader (démo) : portefeuille virtuel, aucun ordre réel.")
    ap.add_argument("--test", action="store_true", help="cours simulés (sans réseau) ; à utiliser avec une copie de data/ (--data)")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier des données (data/)")
    ap.add_argument("--mode", choices=["decision", "horaire"], default="horaire")
    ap.add_argument("--maintenant", help="heure simulée (ISO, UTC)")
    args = ap.parse_args(argv)
    config = charger_config()
    maintenant = sante.lire_iso(args.maintenant) if args.maintenant else datetime.now(timezone.utc)
    if args.test:
        from .sources import FournisseurSimule
        f = FournisseurSimule()
    else:
        from .sources import FournisseurReel
        f = FournisseurReel()
    LOG.info("Agent trader %s (démo, aucun ordre réel) — %s, mode %s", VERSION_AGENT, "cours simulés" if args.test else "cours réels", args.mode)
    r = executer(f, config, Path(args.data), maintenant, args.mode)
    return 0 if r["ok"] else 1
