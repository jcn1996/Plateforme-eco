"""
Agent initiés (sans IA) : achats des dirigeants, activistes et super-investisseurs, comme signal supplémentaire
pour l'agent entreprises.

Étapes :
1. collecte (une source en panne n'arrête pas l'agent ; ce qui a déjà été lu est gardé dans data/inities/etat.json) :
   - mode « complet » (en semaine) : formulaires 4 et 13D de la SEC (index quotidien EDGAR), déclarations des
     dirigeants de l'AMF et de la BaFin, franchissements de seuil hors États-Unis (AMF, DART, EDINET, KAP, BSE) ;
   - dans les deux modes (« complet » et « leger », le week-end) : nouveaux rapports 13F des super-investisseurs
     (config/super_investisseurs.json) et déclarations des élus du Congrès ;
2. calcule le score « achats d'initiés » /100 par société, repère les ventes massives et groupées, le signal
   « conviction des super-investisseurs » par société, les mouvements des 13F ;
3. écrit data/inities.json, data/signaux/inities.json, data/historique/inities/AAAA-MM-JJ.json,
   data/recap/inities-AAAA-MM-JJ.md, data/inities/etat.json et le journal data/journal/agent-inities.json.

L'agent entreprises lit data/inities.json : le score « achats d'initiés » et la conviction des super-investisseurs
y deviennent deux signaux (pondération modérée) de la recommandation. Règles : agents/inities/regles.md.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from . import analyse as A
from . import hors_us as H
from .sources import Capture, FournisseurReel, FournisseurTest

LOG = journal("agent-inities")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
FICHIER_JOURNAL = "agent-inities.json"

NOMS_SOURCES = {
    "sec_tickers": "SEC EDGAR, correspondance ticker ↔ CIK",
    "edgar_index": "SEC EDGAR, index quotidiens des dépôts",
    "edgar_form4": "SEC EDGAR, formulaires 4 (dirigeants)",
    "edgar_13d": "SEC EDGAR, formulaires 13D (activistes)",
    "edgar_13f": "SEC EDGAR, rapports 13F (super-investisseurs)",
    "openfigi": "OpenFIGI (CUSIP → ticker des 13F)",
    "yahoo_cours": "Yahoo Finance via yfinance (cours sur 6 mois des sociétés achetées)",
    "amf_dirigeants": "AMF, base BDIF : déclarations des dirigeants",
    "bafin": "BaFin, base des « Directors' Dealings »",
    "amf_seuils": "AMF, base BDIF : franchissements de seuil",
    "dart": "DART (Corée), déclarations de participation (clé DART_API_KEY)",
    "edinet": "EDINET (Japon), déclarations de grands actionnaires (clé EDINET_API_KEY)",
    "kap": "KAP (Turquie), notifications de franchissement de seuil (source secondaire)",
    "nse_sast": "NSE (Inde), déclarations SAST (franchissements de 5 %)",
    "nse_actionnariat": "NSE (Inde), répartition de l'actionnariat (actionnaires de plus de 1 %)",
    "chambre": "Chambre des représentants, déclarations de transactions",
    "senat": "Sénat, déclarations de transactions (efdsearch)",
}
SOURCES_COMPLET = ("sec_tickers", "edgar_index", "edgar_form4", "edgar_13d", "amf_dirigeants", "bafin")


# ------------------------------------------------------------------ outils

class Collecte:
    """Appels aux sources : un échec est noté (état de la source), jamais propagé."""

    def __init__(self):
        self.etats: dict[str, str] = {}
        self.details: dict[str, str] = {}

    def appel(self, nom: str, fn, vide_ok: bool = True):
        try:
            r = fn()
        except Exception as e:  # une source en panne : on continue
            self.etats[nom] = f"erreur : {str(e)[:160]}"
            LOG.error("Source %s indisponible : %s", nom, str(e)[:200])
            return None
        if r is None:
            self.etats.setdefault(nom, "non configurée")
        elif self.etats.get(nom, "").startswith("erreur"):
            pass  # une erreur plus tôt dans la même source l'emporte
        else:
            self.etats[nom] = "ok" if (r or vide_ok) else "vide"
        return r

    def erreur(self, nom: str, message: str):
        self.etats[nom] = f"erreur : {message[:160]}"

    def partielle(self, nom: str, message: str):
        if not self.etats.get(nom, "").startswith("erreur"):
            self.etats[nom] = f"partielle : {message[:160]}"


def acces(fichier: str) -> str:
    """Numéro d'accession d'un dépôt EDGAR (edgar/data/<cik>/<accession>.txt)."""
    return fichier.rsplit("/", 1)[-1].removesuffix(".txt")


def jours_ouvres(debut: date, fin: date) -> list[date]:
    res, d = [], debut
    while d <= fin:
        if d.weekday() < 5:
            res.append(d)
        d += timedelta(days=1)
    return res


def contexte_entreprises(data: Path) -> dict:
    """Sociétés de l'agent entreprises : {ticker: {nom, pays, cap}}, et noms normalisés des sociétés européennes."""
    ents = (lire_json(data / "entreprises.json") or {}).get("donnees") or []
    par_ticker = {e["ticker"]: {"nom": e.get("nom"), "pays": e.get("pays"), "cap": e.get("capitalisation_md")}
                  for e in ents if isinstance(e, dict) and e.get("ticker")}
    noms = defaultdict(dict)
    for t, e in par_ticker.items():
        if e["pays"] in ("FR", "DE") and e["nom"]:
            noms[e["pays"]].setdefault(A.normaliser_nom(e["nom"]), t)
    return {"par_ticker": par_ticker, "noms": noms}


def ticker_europe(societe: str | None, pays: str, ctx: dict) -> str | None:
    n = A.normaliser_nom(societe)
    if not n:
        return None
    noms = ctx["noms"].get(pays, {})
    if n in noms:
        return noms[n]
    for cle, t in noms.items():  # « LVMH Moet Hennessy Louis Vuitton » ↔ « LVMH »
        if cle and (n.startswith(cle + " ") or cle.startswith(n + " ")):
            return t
    return None


def correspond(texte: str | None, alias: list[str]) -> bool:
    bas = (texte or "").lower()
    return any(a.lower() in bas for a in alias)


# ------------------------------------------------------------------ dirigeants (formulaires 4, AMF, BaFin)

def collecter_form4(f, col: Collecte, etat: dict, cfg: dict, aujourdhui: date, ciks_univers: set[str], par_cik: dict,
                    tickers_univers: set[str]) -> tuple[list[dict], list[dict]]:
    """Index quotidiens → file d'attente des formulaires 4 et 13D → lecture (bornée). Renvoie (nouveaux achats/ventes, nouveaux 13D)."""
    ce = cfg["edgar"]
    dernier = etat.get("dernier_index")
    debut = (A.jour(dernier) - timedelta(days=ce["jours_relus"])) if dernier else aujourdhui - timedelta(days=int(ce["jours_rattrapage"] * 1.45))
    # Un même dépôt figure dans l'index sous le CIK de l'émetteur et sous celui de chaque déclarant : clé = numéro d'accession
    file4 = {acces(x[0]): x for x in etat.get("form4_a_lire", [])}
    lus4 = etat.setdefault("form4_lus", {})
    lus13 = etat.setdefault("d13_lus", {})
    a_lire13: dict[str, list] = {}
    erreurs_index = 0
    jours = jours_ouvres(debut, aujourdhui)
    for j in jours:
        lignes = col.appel("edgar_index", lambda j=j: f.index_quotidien(j.isoformat()))
        if lignes is None:
            erreurs_index += 1
            continue
        for cik, _nom, form, depot, fichier in lignes:
            acc = acces(fichier)
            dep = f"{depot[:4]}-{depot[4:6]}-{depot[6:8]}" if len(depot) == 8 else depot
            if form == "4":
                if acc in lus4:
                    continue
                prio = 1 if cik in ciks_univers else 0
                ancien = file4.get(acc)
                file4[acc] = [fichier, dep, max(prio, ancien[2] if ancien else 0)]
            elif acc not in lus13 and acc not in a_lire13:
                a_lire13[acc] = [fichier, dep, form]
    if erreurs_index and erreurs_index < len(jours):
        col.partielle("edgar_index", f"{erreurs_index} index quotidien(s) sur {len(jours)} illisibles")
    if erreurs_index == 0:
        etat["dernier_index"] = aujourdhui.isoformat()

    # Formulaires 4 : sociétés de l'univers d'abord, puis les plus récents. En attente : 30 jours pour l'univers,
    # 7 jours pour les autres sociétés (au-delà, le retard ne se rattrape pas : ils sont abandonnés)
    limites = {1: (aujourdhui - timedelta(days=30)).isoformat(), 0: (aujourdhui - timedelta(days=7)).isoformat()}
    file = sorted((x for x in file4.values() if x[1] >= limites[x[2]]), key=lambda x: (x[2], x[1]), reverse=True)
    a_lire, reste = file[:ce["form4_max_par_execution"]], file[ce["form4_max_par_execution"]:]
    operations, echecs = [], 0
    for fichier, dep, _prio in a_lire:
        acc = acces(fichier)
        try:
            texte = f.depot(fichier)
        except Exception as e:  # noqa: BLE001
            echecs += 1
            if echecs <= 3:
                LOG.warning("Formulaire 4 %s illisible : %s", acc, str(e)[:120])
            reste.append([fichier, dep, _prio])
            continue
        lus4[acc] = dep
        for op in A.operations(A.lire_form4(texte), acc, dep):
            if op["type"] == "vente" and op["ticker"] not in tickers_univers:
                continue
            operations.append(op)
    if a_lire:
        if echecs == len(a_lire):
            col.erreur("edgar_form4", f"aucun des {len(a_lire)} formulaires 4 n'a pu être lu")
        elif echecs:
            col.partielle("edgar_form4", f"{echecs} formulaire(s) 4 illisible(s) sur {len(a_lire)}, relus à la prochaine exécution")
        else:
            col.etats.setdefault("edgar_form4", "ok")
    else:
        col.etats.setdefault("edgar_form4", "ok")
    etat["form4_a_lire"] = sorted(reste, key=lambda x: x[1], reverse=True)
    # Déjà lus : utile seulement pour les jours d'index relus à la prochaine exécution
    garde = (aujourdhui - timedelta(days=ce["jours_relus"] + 4)).isoformat()
    etat["form4_lus"] = {k: v for k, v in lus4.items() if v >= garde}
    LOG.info("Formulaires 4 : %d lus, %d achats ou ventes retenus, %d en attente", len(a_lire) - echecs, len(operations), len(reste))

    # 13D
    nouveaux13 = []
    echecs13 = 0
    a_lire13 = list(a_lire13.items())[:300]
    for acc, (fichier, dep, form) in a_lire13:
        try:
            x = A.lire_13d(f.depot(fichier))
        except Exception:  # noqa: BLE001
            echecs13 += 1
            continue
        lus13[acc] = dep
        if not x:
            continue
        x.update({"acc": acc, "depot": dep, "formulaire": "13D/A" if form.endswith("/A") else "13D",
                  "ticker": par_cik.get(x.get("cik") or ""), "url": f"https://www.sec.gov/Archives/{fichier}"})
        nouveaux13.append(x)
    if a_lire13:
        if echecs13 == len(a_lire13):
            col.erreur("edgar_13d", "aucun formulaire 13D lisible")
        elif echecs13:
            col.partielle("edgar_13d", f"{echecs13} formulaire(s) 13D illisible(s)")
    col.etats.setdefault("edgar_13d", "ok")
    etat["d13_lus"] = {k: v for k, v in lus13.items() if v >= (aujourdhui - timedelta(days=ce["jours_relus"] + 4)).isoformat()}
    return operations, nouveaux13


def collecter_amf_dd(f, col: Collecte, etat: dict, cfg: dict, aujourdhui: date, ctx: dict) -> list[dict]:
    ce = cfg["europe"]
    lus = etat.setdefault("amf_lus", {})
    depuis = (aujourdhui - timedelta(days=ce["jours_rattrapage"] if not lus else 5)).isoformat()
    liste = []
    for page in range(12):
        r = col.appel("amf_dirigeants", lambda p=page: f.amf_liste("DD", depuis, p))
        if not r:
            break
        liste += r
        if len(r) < 50:
            break
    nouveaux = [x for x in liste if x.get("numero") and x["numero"] not in lus and x.get("chemin")][:ce["amf_max_par_execution"]]
    res, echecs = [], 0
    for x in nouveaux:
        try:
            texte = f.amf_pdf(x["chemin"])
        except Exception:  # noqa: BLE001
            echecs += 1
            continue
        lus[x["numero"]] = x["publication"]
        a = A.lire_dd_amf(texte, x["numero"], x["publication"])
        if a:
            a["ticker"] = ticker_europe(a["societe"], "FR", ctx)
            a["url"] = f"https://bdif.amf-france.org/back/api/v1/documents/{x['chemin']}"
            res.append(a)
    if nouveaux and echecs:
        (col.erreur if echecs == len(nouveaux) else col.partielle)("amf_dirigeants", f"{echecs} déclaration(s) illisible(s) sur {len(nouveaux)}")
    etat["amf_lus"] = {k: v for k, v in lus.items() if v >= (aujourdhui - timedelta(days=60)).isoformat()}
    return res


def collecter_bafin(f, col: Collecte, cfg: dict, aujourdhui: date, ctx: dict, etat: dict) -> list[dict]:
    depuis = (aujourdhui - timedelta(days=cfg["europe"]["jours_rattrapage"] if not etat.get("bafin_lu") else 7)).isoformat()
    csv = col.appel("bafin", lambda: f.bafin(depuis, aujourdhui.isoformat()))
    if csv is None:
        return []
    etat["bafin_lu"] = aujourdhui.isoformat()
    res = A.lire_bafin(csv)
    for a in res:
        a["ticker"] = ticker_europe(a["societe"], "DE", ctx)
        a["url"] = "https://portal.mvp.bafin.de/database/DealingsInfo/"
    return res


# ------------------------------------------------------------------ super-investisseurs (13F)

def compacter_13f(c: dict, cfg: dict) -> dict:
    """Garde les positions d'au moins poids_min_affiche_pct % et tous les mouvements (fichier d'état raisonnable)."""
    seuil = cfg["super_investisseurs"]["poids_min_affiche_pct"]
    return {**c, "positions": [p for p in c["positions"] if p["poids"] >= seuil or p["mouvement"]]}


def collecter_13f(f, col: Collecte, etat: dict, si: list[dict], cfg: dict, aujourdhui: date) -> list[dict]:
    """Nouveaux rapports 13F : relit le dernier et le précédent, calcule les mouvements. Renvoie les nouvelles positions."""
    f13 = etat.setdefault("f13", {})
    nouvelles = []
    echecs = 0
    for inv in si:
        try:
            s = f.soumissions(inv["cik"])
        except Exception as e:  # noqa: BLE001
            echecs += 1
            LOG.warning("13F %s : %s", inv["nom"], str(e)[:160])
            continue
        depots = s.get("depots") or []
        hr = [d for d in depots if d["formulaire"] == "13F-HR"]
        dernier_tout = depots[0] if depots else None
        ancien = f13.get(inv["cle"]) or {}
        info = {"nom_sec": s.get("nom"), "dernier_formulaire": dernier_tout["formulaire"] if dernier_tout else None,
                "dernier_depot_tout": dernier_tout["depot"] if dernier_tout else None}
        if not hr:
            f13[inv["cle"]] = {**ancien, **info, "statut": "aucun 13F"}
            continue
        actuel = hr[0]
        if ancien.get("accession") == actuel["accession"]:
            f13[inv["cle"]] = {**ancien, **info, "statut": A.statut_13f(ancien.get("periode"), aujourdhui, cfg)}
            continue
        if A.statut_13f(actuel["periode"], aujourdhui, cfg) == "inactif":
            # L'entité ne dépose plus (ex. Scion depuis fin 2025) : rien à relire
            f13[inv["cle"]] = {**info, "accession": actuel["accession"], "periode": actuel["periode"], "depot": actuel["depot"], "statut": "inactif",
                               "positions": [], "nouvelles": [], "renforcements": [], "allegements": [], "sorties": [], "options": []}
            continue
        precedent = next((d for d in hr[1:] if d["periode"] != actuel["periode"]), None)
        try:
            cik = str(int(inv["cik"]))
            texte = f.depot(f"edgar/data/{cik}/{actuel['accession']}.txt")
            prec = A.lire_13f(f.depot(f"edgar/data/{cik}/{precedent['accession']}.txt")) if precedent else None
        except Exception as e:  # noqa: BLE001
            echecs += 1
            LOG.warning("13F %s illisible : %s", inv["nom"], str(e)[:160])
            continue
        lu = A.lire_13f(texte)
        comp = compacter_13f(A.comparer_13f(lu, prec, cfg), cfg)
        f13[inv["cle"]] = {**info, "accession": actuel["accession"], "periode": lu["periode"] or actuel["periode"], "depot": actuel["depot"],
                           "periode_precedente": precedent["periode"] if precedent else None, "statut": A.statut_13f(lu["periode"] or actuel["periode"], aujourdhui, cfg),
                           "lu_le": aujourdhui.isoformat(), **comp}
        LOG.info("13F %s : trimestre %s, %d positions, %d nouvelles", inv["nom"], actuel["periode"], comp["nb_positions"], len(comp["nouvelles"]))
        # Signal seulement pour un dépôt récent (pas au premier lancement de l'agent)
        if ancien and (aujourdhui - A.jour(actuel["depot"])).days <= 7:
            for p in comp["nouvelles"]:
                if p["poids"] >= cfg["super_investisseurs"]["poids_min_mouvement_pct"]:
                    nouvelles.append({**p, "investisseur": f"{inv['nom']} ({inv['societe']})", "cle": inv["cle"], "periode": lu["periode"],
                                      "depot": actuel["depot"]})
    if echecs == len(si):
        col.erreur("edgar_13f", "aucun super-investisseur n'a pu être lu")
    elif echecs:
        col.partielle("edgar_13f", f"{echecs} super-investisseur(s) sur {len(si)} illisible(s)")
    else:
        col.etats["edgar_13f"] = "ok"
    return nouvelles


def tickers_13f(f, col: Collecte, etat: dict, cfg: dict, par_nom: dict) -> None:
    """CUSIP → ticker : d'abord le cache, puis le nom exact de la liste SEC, enfin OpenFIGI (borné)."""
    cache = etat.setdefault("cusip", {})
    manquants = []
    for x in etat.get("f13", {}).values():
        for cle in ("positions", "nouvelles", "renforcements", "allegements", "sorties"):
            for p in x.get(cle) or []:
                c = p.get("cusip")
                if c and c not in cache and c not in manquants:
                    manquants.append(c)
    if manquants:
        trouves = col.appel("openfigi", lambda: f.openfigi(manquants[:cfg["super_investisseurs"]["openfigi_max_par_execution"]])) or {}
        cache.update(trouves)
    for x in etat.get("f13", {}).values():
        for cle in ("positions", "nouvelles", "renforcements", "allegements", "sorties"):
            for p in x.get(cle) or []:
                p["ticker"] = cache.get(p.get("cusip")) or par_nom.get(A.normaliser_nom(p.get("nom")))


# ------------------------------------------------------------------ élus

def collecter_elus(f, col: Collecte, etat: dict, cfg: dict, aujourdhui: date) -> None:
    ce = cfg["elus"]
    lus = etat.setdefault("chambre_lus", {})
    elus = etat.setdefault("elus", [])
    limite = (aujourdhui - timedelta(days=ce["conservation_jours"])).isoformat()
    annees = [aujourdhui.year] + ([aujourdhui.year - 1] if aujourdhui.month <= 2 else [])
    declarations = []
    for a in annees:
        xml = col.appel("chambre", lambda a=a: f.chambre_index(a))
        if xml:
            declarations += A.lire_index_chambre(xml)
    nouvelles = sorted((d for d in declarations if d["doc"] not in lus and d["depot"] >= limite), key=lambda d: d["depot"], reverse=True)
    echecs = 0
    for d in nouvelles[:ce["pdf_max_par_execution"]]:
        try:
            texte = f.chambre_ptr(d["annee"], d["doc"])
        except Exception:  # noqa: BLE001
            echecs += 1
            continue
        lus[d["doc"]] = d["depot"]
        url = f"https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{d['annee']}/{d['doc']}.pdf"
        for op in A.lire_ptr_chambre(texte):
            elus.append({**op, "chambre": "Chambre", "elu": d["elu"], "circonscription": d["circonscription"], "date_declaration": d["depot"],
                         "retard_jours": (A.jour(d["depot"]) - A.jour(op["date_operation"])).days, "url": url, "id": d["doc"]})
    if nouvelles and echecs:
        (col.erreur if echecs == min(len(nouvelles), ce["pdf_max_par_execution"]) else col.partielle)("chambre", f"{echecs} déclaration(s) illisible(s)")
    if ce.get("senat_actif"):
        vus = {x.get("url") for x in elus if x.get("chambre") == "Sénat"}
        r = col.appel("senat", lambda: f.senat((aujourdhui - timedelta(days=10)).isoformat()))
        for d in r or []:
            if d["url"] in vus:
                continue
            for op in A.lire_ptr_senat(d["html"]):
                elus.append({**op, "chambre": "Sénat", "elu": d["elu"], "circonscription": None, "date_declaration": d["depot"],
                             "retard_jours": (A.jour(d["depot"]) - A.jour(op["date_operation"])).days, "url": d["url"], "id": d["url"]})
    else:
        col.etats["senat"] = "non configurée"
    etat["chambre_lus"] = {k: v for k, v in lus.items() if v >= limite}
    etat["elus"] = sorted((x for x in elus if x["date_declaration"] >= limite), key=lambda x: (x["date_declaration"], x["date_operation"]), reverse=True)


# ------------------------------------------------------------------ calculs

def cle_societe(a: dict) -> str:
    return a.get("ticker") or f"{a['pays']}:{A.normaliser_nom(a.get('societe'))}"


def scores_dirigeants(etat: dict, cours: dict, ctx: dict, cfg: dict, aujourdhui: date) -> dict:
    achats = etat.get("achats", [])
    par_soc = defaultdict(list)
    fen = cfg["achats"]["fenetre_score_jours"]
    for a in achats:
        if (aujourdhui - A.jour(a["date"])).days <= fen:
            par_soc[cle_societe(a)].append(a)
    res = {}
    for cle, lst in par_soc.items():
        t = lst[0].get("ticker")
        cap = (ctx["par_ticker"].get(t) or {}).get("cap") if t else None
        s = A.score_societe(lst, achats, cours.get(t) if t else None, cap, cfg, aujourdhui, etat.get("debut_historique"))
        if s:
            e = ctx["par_ticker"].get(t) or {}
            s.update({"cle": cle, "ticker": t, "nom": e.get("nom") or lst[0].get("societe"), "pays": e.get("pays") or lst[0]["pays"],
                      "capitalisation_md": cap, "suivie": t in ctx["par_ticker"],
                      "source": {"US": "SEC EDGAR, formulaires 4", "FR": "AMF, déclarations des dirigeants", "DE": "BaFin, Directors' Dealings"}[lst[0]["pays"]]})
            res[cle] = s
    return res


def detentions(etat: dict, si: list[dict]) -> dict[str, list[dict]]:
    noms = {inv["cle"]: inv["nom"] for inv in si}
    res = defaultdict(list)
    for cle, x in etat.get("f13", {}).items():
        if cle not in noms or x.get("statut") == "inactif":
            continue
        for p in x.get("positions") or []:
            if p.get("ticker"):
                res[p["ticker"]].append({"cle": cle, "nom": noms[cle], "poids": p["poids"], "mouvement": p["mouvement"], "trimestre": x.get("periode")})
    for h in A.positions_hors_us(etat.get("hors_us", [])):
        if h["statut"] != "détenue" or not h.get("ticker") or h["investisseur"] not in noms:
            continue
        if not any(y["cle"] == h["investisseur"] for y in res[h["ticker"]]):
            res[h["ticker"]].append({"cle": h["investisseur"], "nom": noms[h["investisseur"]], "poids": None, "mouvement": None, "pct_capital": h.get("pct")})
    return res


def vue_investisseurs(etat: dict, si: list[dict], cfg: dict) -> list[dict]:
    n = cfg["super_investisseurs"]["principales_positions"]
    res = []
    for inv in si:
        x = etat.get("f13", {}).get(inv["cle"]) or {}
        statut = x.get("statut") or "non lu"
        if x.get("dernier_formulaire") == "13F-NT" and statut != "inactif":
            statut = "13F-NT"
        principales = [p for p in (x.get("positions") or [])][:n]
        res.append({
            "cle": inv["cle"], "nom": inv["nom"], "societe": inv["societe"], "cik": inv["cik"], "note": inv.get("note"),
            "nom_sec": x.get("nom_sec"), "statut": statut, "trimestre": x.get("periode"), "trimestre_texte": A.trimestre_fr(x.get("periode")),
            "date_depot": x.get("depot"), "trimestre_precedent": x.get("periode_precedente"),
            "valeur_totale": x.get("valeur_totale"), "nb_positions": x.get("nb_positions"),
            "principales": principales, "nouvelles": x.get("nouvelles", [])[:25], "renforcements": x.get("renforcements", [])[:25],
            "allegements": x.get("allegements", [])[:25], "sorties": x.get("sorties", [])[:25], "options": x.get("options", []),
            "positions_hors_us": [h for h in A.positions_hors_us(etat.get("hors_us", [])) if h["investisseur"] == inv["cle"]][:40],
            "hors_us": [h for h in etat.get("hors_us", []) if h["investisseur"] == inv["cle"]][:40],
            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={inv['cik']}&type=13F-HR",
        })
    return res


def societes(scores: dict, conv: dict, activistes: list[dict], ventes: dict, etat: dict) -> dict:
    """Vue par ticker lue par l'agent entreprises et la fiche entreprise de l'appli."""
    res = {}
    for t in set(s["ticker"] for s in scores.values() if s.get("ticker")) | set(conv) | {a["ticker"] for a in activistes if a.get("ticker")} | set(ventes):
        s = next((x for x in scores.values() if x.get("ticker") == t), None)
        recents = sorted((a for a in etat.get("achats", []) if a.get("ticker") == t), key=lambda a: a["date"], reverse=True)[:5]
        act = [a for a in activistes if a.get("ticker") == t]
        res[t] = {
            "score_achats": s["score"] if s else None, "texte_achats": s["texte"] if s else None, "acheteurs_30j": s["acheteurs_30j"] if s else 0,
            "achats_recents": [{k: a.get(k) for k in ("date", "declarant", "fonction", "titre", "montant", "devise", "actions", "prix", "caractere")} for a in recents],
            "conviction": conv[t]["score"] if t in conv else None, "texte_conviction": conv[t]["texte"] if t in conv else None,
            "super_investisseurs": [{k: x.get(k) for k in ("cle", "nom", "poids", "mouvement", "pct_capital")} for x in conv[t]["investisseurs"]] if t in conv else [],
            "activiste": ({k: act[0].get(k) for k in ("investisseur", "pct", "depot", "date_evenement", "formulaire", "url")} if act else None),
            "ventes_massives": ventes.get(t),
        }
    return res


# ------------------------------------------------------------------ écritures

def ecrire_signaux(chemin: Path, nouveaux: list[dict], aujourdhui: date) -> None:
    existants = (lire_json(chemin) or {}).get("donnees") or []
    vus = {(s["type"], s["cle"], s["date"]) for s in existants}
    tous = existants + [s for s in nouveaux if (s["type"], s["cle"], s["date"]) not in vus]
    limite = (aujourdhui - timedelta(days=180)).isoformat()
    tous = sorted((s for s in tous if s["date"] >= limite), key=lambda s: s["date"], reverse=True)
    ecrire_json(chemin, enveloppe(tous, "agent-inities", fictif=False, version_agent=VERSION_AGENT,
                                  description="Signaux candidats pour le chef d'orchestre et le contradicteur (180 derniers jours) : achats groupés de dirigeants, nouvelle position d'un super-investisseur, nouveau 13D"))


def recap_markdown(jour: date, d: dict, nouveaux: list[dict], etats: dict) -> str:
    l = [f"# Agent initiés — récapitulatif du {A.date_fr(jour.isoformat())}", "", "## Achats des dirigeants (meilleurs scores)", ""]
    l += [f"- {s['nom']} ({s['ticker'] or s['pays']}) : {s['score']}/100 — {s['texte']}" for s in d["dirigeants"]["societes"][:15]] or ["- aucun achat retenu"]
    l += ["", "## Ventes massives et groupées", ""] + ([f"- {v['nom']} ({v['ticker']}) : {v['texte']}" for v in d["dirigeants"]["ventes_massives"]] or ["- aucune"])
    l += ["", "## Super-investisseurs", "", f"_{A.MENTION_13F}._", ""]
    for i in d["super_investisseurs"]:
        l.append(f"- {i['nom']} ({i['societe']}) : {i['statut']}, {i['trimestre_texte']}, déposé le {A.date_fr(i['date_depot'])}, "
                 f"{i['nb_positions'] or 0} positions, {len(i['nouvelles'])} nouvelles")
    l += ["", "## Positions hors États-Unis", "", f"_{A.MENTION_HORS_US}._", ""]
    l += [f"- {x['nom']} — {x['societe']} ({A.PAYS_FR.get(x['pays'], x['pays'])}) : {A.fr(x['pct'], 2) + ' %' if x.get('pct') is not None else 'n. d.'}, "
          f"{x['statut']}, {x['source']} du {A.date_fr(x.get('date'))} ({x.get('entite') or '—'})" for x in d["positions_hors_us"]] or ["- aucune"]
    l += ["", "### Recherche effectuée", ""]
    for cle, s in (d.get("recherche_hors_us") or {}).get("sources", {}).items():
        per = f"du {A.date_fr(s['periodes'][0])} au {A.date_fr(s['periodes'][1])}" if s.get("periodes") else "aucune période"
        l.append(f"- {s['source']} : {s['etat']} ; {per} ; {s['documents_examines']} document(s) examiné(s)"
                 + (f" ; {s['detail']}" if s.get("detail") else "") + f" ; trouvé : {'; '.join(s['trouves']) or 'rien'}")
    l += ["", "## Nouveaux 13D (7 derniers jours)", ""]
    recents = [a for a in d["activistes"] if (jour - A.jour(a["depot"])).days <= 7 and a["formulaire"] == "13D"]
    l += [f"- {a['societe']} : {a['investisseur']} ({A.fr(a['pct'], 1)} %)" for a in recents[:20]] or ["- aucun"]
    l += ["", "## Signaux détectés aujourd'hui", ""] + ([f"- [{s['importance']}] {s['titre']}" for s in nouveaux] or ["- aucun"])
    erreurs = [k for k, v in etats.items() if v not in ("ok", "non configurée")]
    l += ["", "## Sources en échec ou partielles", ""] + ([f"- {NOMS_SOURCES.get(k, k)} : {etats[k]}" for k in erreurs] or ["- aucune"])
    return "\n".join(l) + "\n"


def sources_sante(etats: dict, secondaires: tuple = ()) -> list[dict]:
    res = []
    for nom, etat in etats.items():
        if nom in secondaires and etat != "non configurée":
            # Source secondaire (KAP) : affichée pour information, sans effet sur le statut de l'agent
            res.append({"nom": NOMS_SOURCES.get(nom, nom), "etat": "ok" if etat == "ok" else "échec" if etat.startswith("erreur") else "partielle",
                        "detail": None if etat == "ok" else etat.split(" : ", 1)[-1], "secondaire": True})
            continue
        n = NOMS_SOURCES.get(nom, nom)
        if etat == "ok":
            res.append({"nom": n, "etat": "ok", "detail": None})
        elif etat == "non configurée":
            detail = {"dart": "clé non configurée (secret DART_API_KEY absent) : source ignorée",
                      "edinet": "clé non configurée (secret EDINET_API_KEY absent) : source ignorée",
                      "senat": "désactivée (elus.senat_actif) : le site impose d'accepter ses conditions d'utilisation"}.get(nom, "secret SEC_USER_AGENT absent : source ignorée")
            res.append({"nom": n, "etat": "non configurée", "detail": detail})
        elif etat == "vide":
            res.append({"nom": n, "etat": "partielle", "detail": "aucune donnée reçue"})
        elif etat.startswith("partielle"):
            res.append({"nom": n, "etat": "partielle", "detail": etat.removeprefix("partielle : ")})
        else:
            res.append({"nom": n, "etat": "échec", "detail": etat.removeprefix("erreur : ")})
    return res


def indicateurs_sante(etats: dict, secondaires: tuple = ()) -> dict:
    """Une source = un indicateur : l'agent n'est dégradé que si une source qui fonctionnait lors de la dernière
    exécution saine est perdue (une source jamais joignable, comme KAP, ne le rend pas dégradé)."""
    return {NOMS_SOURCES.get(k, k): {"valides": [k] if v in ("ok",) or v.startswith("partielle") else [], "configurees": [k]}
            for k, v in etats.items() if v != "non configurée" and k not in secondaires}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent initiés : dirigeants, activistes, super-investisseurs, élus (sans IA)")
    ap.add_argument("--mode", choices=("complet", "leger"), default="complet",
                    help="complet (en semaine) : toutes les sources ; leger (week-end) : 13F et élus seulement")
    ap.add_argument("--test", action="store_true", help="données de test (agents/inities/tests/donnees), sans réseau")
    ap.add_argument("--donnees-test", help="dossier des données de test (par défaut tests/donnees)")
    ap.add_argument("--capturer", action="store_true", help="enregistre les réponses réelles comme données de test")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier data/ (lecture de l'agent entreprises et écriture)")
    ap.add_argument("--super-investisseurs", default=str(RACINE / "config" / "super_investisseurs.json"))
    ap.add_argument("--config", default=str(DOSSIER / "config.json"), help="configuration de l'agent (par défaut agents/inities/config.json)")
    ap.add_argument("--date", help="date du jour (AAAA-MM-JJ), utile pour les tests")
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    si = (lire_json(Path(args.super_investisseurs)) or {}).get("investisseurs") or []
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    data = Path(args.data)
    dossier_test = Path(args.donnees_test) if args.donnees_test else DOSSIER / "tests" / "donnees"
    if args.test:
        f = FournisseurTest(dossier_test)
    else:
        f = FournisseurReel(RACINE / "agents" / ".cache", cfg["edgar"]["requetes_par_seconde"])
        if args.capturer:
            f = Capture(f, dossier_test)
    LOG.info("Agent initiés %s — mode %s — %s", VERSION_AGENT, args.mode, "données de test" if args.test else "sources réelles")

    chemin_etat = data / "inities" / "etat.json"
    etat = lire_json(chemin_etat) or {}
    etat.setdefault("debut_historique", aujourdhui.isoformat())
    ctx = contexte_entreprises(data)
    col = Collecte()
    tickers_univers_us = {t for t, e in ctx["par_ticker"].items() if e["pays"] == "US"}

    # 1. Collecte
    sec_ok = f.sec_actif
    tick = col.appel("sec_tickers", f.tickers_sec) if sec_ok else None
    par_cik, par_ticker = (tick or {}).get("par_cik", {}), (tick or {}).get("par_ticker", {})
    par_nom = {A.normaliser_nom(n): t for t, n in (tick or {}).get("titres", {}).items()}
    if args.mode == "complet":
        if sec_ok and tick is not None:
            ciks = {par_ticker[t] for t in tickers_univers_us if t in par_ticker}
            ops, n13 = collecter_form4(f, col, etat, cfg, aujourdhui, ciks, par_cik, tickers_univers_us)
        else:
            ops, n13 = [], []
            for s in ("edgar_index", "edgar_form4", "edgar_13d"):
                col.etats[s] = "non configurée" if not sec_ok else "erreur : correspondance ticker ↔ CIK indisponible"
        ops += collecter_amf_dd(f, col, etat, cfg, aujourdhui, ctx)
        ops += collecter_bafin(f, col, cfg, aujourdhui, ctx, etat)
    else:
        ops, n13 = [], []
    # Positions hors États-Unis : dans les deux modes (le week-end avance le rattrapage de l'historique)
    recherche = H.collecter(f, col, etat, si, cfg, aujourdhui, ctx)
    if sec_ok:
        nouveaux_13f = collecter_13f(f, col, etat, si, cfg, aujourdhui)
        tickers_13f(f, col, etat, cfg, par_nom)
        for n in nouveaux_13f:
            n["ticker"] = etat.get("cusip", {}).get(n["cusip"]) or par_nom.get(A.normaliser_nom(n["nom"]))
    else:
        nouveaux_13f = []
        col.etats["edgar_13f"] = col.etats["sec_tickers"] = "non configurée"
    collecter_elus(f, col, etat, cfg, aujourdhui)

    # 2. Mise à jour de l'historique (achats, ventes, 13D)
    ca = cfg["achats"]
    vus = {(a["acc"], a["type"]) for a in etat.get("achats", [])}
    nouveaux_achats = [o for o in ops if o["type"] == "achat" and (o.get("montant") or 0) >= ca["montant_min_usd"] * (0.9 if o["devise"] == "EUR" else 1)
                       and (o["acc"], "achat") not in vus]
    limite_achats = (aujourdhui - timedelta(days=ca["conservation_jours"])).isoformat()
    detail = (aujourdhui - timedelta(days=ca["fenetre_score_jours"] + 10)).isoformat()
    # Au-delà de la fenêtre du score, un achat ne sert plus qu'à juger si un dirigeant achète habituellement : version réduite
    etat["achats"] = sorted(({k: a.get(k) for k in ("acc", "type", "date", "pays", "ticker", "societe", "declarant", "cik_declarant")} if a["date"] < detail else a
                             for a in etat.get("achats", []) + nouveaux_achats if a["date"] >= limite_achats), key=lambda a: a["date"], reverse=True)
    vus_v = {v["acc"] for v in etat.get("ventes", [])}
    limite_v = (aujourdhui - timedelta(days=cfg["ventes"]["fenetre_jours"] + 15)).isoformat()
    etat["ventes"] = [v for v in etat.get("ventes", []) + [o for o in ops if o["type"] == "vente" and o["acc"] not in vus_v] if v["date"] >= limite_v]
    alias_si = {inv["cle"]: (inv.get("entites") or []) + [inv["societe"]] for inv in si}
    for x in n13:
        x["super_investisseur"] = next((c for c, al in alias_si.items() if correspond(" ".join([x.get("investisseur") or ""] + x.get("personnes", [])), al)), None)
    vus13 = {x["acc"] for x in etat.get("activistes", [])}
    c13 = cfg["activistes"]
    limites13 = {"13D": (aujourdhui - timedelta(days=c13["conservation_jours"])).isoformat(),
                 "13D/A": (aujourdhui - timedelta(days=c13["conservation_amendements_jours"])).isoformat()}
    etat["activistes"] = sorted((x for x in etat.get("activistes", []) + [x for x in n13 if x["acc"] not in vus13] if x["depot"] >= limites13[x["formulaire"]]),
                                key=lambda x: x["depot"], reverse=True)
    for x in etat["activistes"]:
        x["ticker"] = x.get("ticker") or par_cik.get(x.get("cik") or "")
        x["suivie"] = x.get("ticker") in ctx["par_ticker"]
    nouveaux_13d = [x for x in n13 if x["formulaire"] == "13D" and (aujourdhui - A.jour(x["depot"])).days <= 3 and x["acc"] not in vus13]

    # 3. Cours des sociétés achetées (achat après une baisse du cours ?)
    fen = ca["fenetre_score_jours"]
    a_coter = sorted({a["ticker"] for a in etat["achats"] if a.get("ticker") and a["pays"] == "US" and (aujourdhui - A.jour(a["date"])).days <= fen})[:200]
    cours = col.appel("yahoo_cours", lambda: f.cours(a_coter)) if a_coter else {}

    # 4. Calculs
    scores = scores_dirigeants(etat, cours or {}, ctx, cfg, aujourdhui)
    ventes = {}
    par_t = defaultdict(list)
    for v in etat["ventes"]:
        par_t[v["ticker"]].append(v)
    for t, lst in par_t.items():
        vm = A.ventes_massives(lst, cfg, aujourdhui)
        if vm:
            ventes[t] = {**vm, "ticker": t, "nom": (ctx["par_ticker"].get(t) or {}).get("nom") or lst[0].get("societe")}
    conv = A.conviction(detentions(etat, si), cfg)
    for t, c in conv.items():
        c["nom"] = (ctx["par_ticker"].get(t) or {}).get("nom") or next(
            (p["nom"] for x in etat.get("f13", {}).values() for p in x.get("positions") or [] if p.get("ticker") == t), t)
        c["suivie"] = t in ctx["par_ticker"]
    emis = etat.setdefault("signaux_emis", {})
    nouveaux = A.signaux(scores, nouveaux_13f, nouveaux_13d, cfg, aujourdhui, emis)
    etat["signaux_emis"] = {k: v for k, v in emis.items() if (aujourdhui - A.jour(v)).days < 60}

    fen_aff = (aujourdhui - timedelta(days=fen)).isoformat()
    achats_aff = [{k: a.get(k) for k in ("date", "depot", "pays", "ticker", "societe", "declarant", "fonction", "titre", "actions", "prix", "montant",
                                         "devise", "avant", "caractere", "caractere_raison", "acc", "url")} for a in etat["achats"] if a["date"] >= fen_aff][:400]
    for a in achats_aff:
        if a["pays"] == "US" and not a.get("url") and a.get("acc"):
            a["url"] = f"https://www.sec.gov/Archives/edgar/data/{a['acc'].split('-')[0].lstrip('0') or '0'}/{a['acc'].replace('-', '')}/{a['acc']}-index.htm"
        a["suivie"] = a.get("ticker") in ctx["par_ticker"]
    for x in etat["activistes"]:
        x["suivie"] = x.get("ticker") in ctx["par_ticker"]
    donnees = {
        "date": aujourdhui.isoformat(), "mode": args.mode,
        "mentions": {"13f": A.MENTION_13F, "hors_us": A.MENTION_HORS_US, "elus": A.MENTION_ELUS,
                     "dirigeants": "Achats sur le marché (code P) seulement : exercices d'options, attributions, donations et opérations programmées (10b5-1) exclus. France : AMF ; Allemagne : BaFin ; Royaume-Uni : pas de source gratuite exploitable."},
        "dirigeants": {
            "achats": achats_aff,
            "societes": sorted(scores.values(), key=lambda s: (s["score"], s["dernier_achat"]), reverse=True)[:200],
            "ventes_massives": sorted(ventes.values(), key=lambda v: v["montant_total"], reverse=True),
        },
        "super_investisseurs": vue_investisseurs(etat, si, cfg),
        "conviction": sorted(({"ticker": t, **c} for t, c in conv.items()), key=lambda c: (c["score"], c["nombre"]), reverse=True)[:200],
        "activistes": [{k: x.get(k) for k in ("depot", "formulaire", "societe", "ticker", "cik", "investisseur", "personnes", "pct", "date_evenement",
                                              "url", "super_investisseur", "suivie")} for x in etat["activistes"]][:300],
        "hors_us": etat.get("hors_us", [])[:200],
        "positions_hors_us": A.positions_hors_us(etat.get("hors_us", [])),
        "recherche_hors_us": recherche,
        "elus": etat.get("elus", [])[:500],
        "societes": societes(scores, conv, etat["activistes"], ventes, etat),
        "methode": ("Score « achats d'initiés » /100 : achat opportuniste plutôt que routinier (25), achats groupés sur 30 jours (25), "
                    "fonction de l'acheteur (20), montant par rapport à ce qu'il détenait (20), taille de la société (10). "
                    "Conviction des super-investisseurs /100 : poids de la position dans chaque portefeuille, bonus pour un achat récent."),
        "avertissement": "Informations publiques à titre informatif, sans conseil d'investissement.",
    }

    # 5. Écritures
    ecrire_signaux(data / "signaux" / "inities.json", nouveaux, aujourdhui)
    objet = enveloppe(donnees, "agent-inities", fictif=False, version_agent=VERSION_AGENT,
                      etat_des_sources={NOMS_SOURCES.get(k, k): v for k, v in col.etats.items()})
    ecrire_json(data / "inities.json", objet, compact=True)
    etat["meta"] = {"genere_le": objet["meta"]["genere_le"], "source": "agent-inities", "version_agent": VERSION_AGENT,
                    "description": "État de l'agent initiés : dépôts déjà lus, file d'attente, historique des achats, derniers 13F, tickers des CUSIP"}
    ecrire_json(chemin_etat, etat, compact=True)
    ecrire_json(data / "historique" / "inities" / f"{aujourdhui.isoformat()}.json", {
        "meta": {"genere_le": objet["meta"]["genere_le"], "source": "agent-inities", "version_agent": VERSION_AGENT,
                 "description": "Scores du jour : achats d'initiés et conviction des super-investisseurs par société"},
        "donnees": {"achats": {s["cle"]: s["score"] for s in scores.values()}, "conviction": {t: c["score"] for t, c in conv.items()}}})
    (data / "recap").mkdir(parents=True, exist_ok=True)
    (data / "recap" / f"inities-{aujourdhui.isoformat()}.md").write_text(recap_markdown(aujourdhui, donnees, nouveaux, col.etats), encoding="utf-8")

    chemin_journal = data / "journal" / FICHIER_JOURNAL
    j = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    j["donnees"] = (j.get("donnees", []) + [{"genere_le": objet["meta"]["genere_le"], "mode": args.mode, "etat_des_sources": col.etats,
                                             "achats_retenus": len(nouveaux_achats), "signaux": [s["titre"] for s in nouveaux],
                                             "recherche_hors_us": recherche}])[-90:]
    j["meta"] = {**j.get("meta", {}), "genere_le": objet["meta"]["genere_le"], "source": "agent-inities", "version_agent": VERSION_AGENT,
                 "description": "État des sources et signaux, à chaque exécution"}
    ecrire_json(chemin_journal, j)
    maintenant = (datetime.combine(aujourdhui, datetime.min.time(), timezone.utc).replace(hour=6, minute=40) if args.date
                  else datetime.now(timezone.utc))
    secondaires = tuple(cfg["hors_us"]["sources_secondaires"])
    bloc = sante.bloc_sante("inities", "Agent initiés", 9, "agent-inities.yml", sources_sante(col.etats, secondaires), maintenant,
                            (j.get("meta") or {}).get("sante"), indicateurs=indicateurs_sante(col.etats, secondaires))
    sante.enregistrer_sante(chemin_journal, bloc, forcer=True)

    LOG.info("Achats retenus : %d nouveaux ; %d sociétés notées ; %d super-investisseurs ; %d 13D ; %d opérations d'élus",
             len(nouveaux_achats), len(scores), len(si), len(etat["activistes"]), len(etat.get("elus", [])))
    LOG.info("Signaux détectés : %d ; santé : %d/%d sources, %s", len(nouveaux), bloc["sources_ok"], bloc["sources_total"],
             "dégradé" if bloc["degrade"] else "aucun indicateur dégradé")
    return 0
