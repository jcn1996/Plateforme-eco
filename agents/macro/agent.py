"""
Agent macro (sans IA) : vue d'ensemble de l'économie mondiale, complémentaire de l'agent pays.

Étapes :
1. interroge les sources gratuites (FRED, Bundesbank, BCE, BRI, OCDE, FMI, Eurostat, Banque du Canada,
   Banco Central do Brasil, Yahoo Finance) ; une source en panne n'arrête pas l'agent ;
2. calcule la phase du cycle (monde et 5 zones), les signaux de récession, l'état des banques
   centrales, les marchés du cycle et une lecture macro de chaque pays suivi ;
3. écrit data/macro.json, data/signaux/macro.json, data/historique/macro/AAAA-MM-JJ.json,
   data/recap/macro-AAAA-MM-JJ.md et le journal data/journal/agent-macro.json (santé).

Règles de conduite : voir agents/macro/regles.md.
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
from .sources import Capture, FournisseurReel, FournisseurTest

LOG = journal("agent-macro")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]

NOMS_SOURCES = {
    "fred_T10Y2Y": "FRED, écart 10 ans − 2 ans (T10Y2Y)",
    "fred_T10Y3M": "FRED, écart 10 ans − 3 mois (T10Y3M)",
    "fred_SAHMREALTIME": "FRED, règle de Sahm en temps réel (SAHMREALTIME)",
    "fred_UNRATE": "FRED, taux de chômage (UNRATE)",
    "fred_DFEDTARL": "FRED, borne basse de l'objectif de la Fed (DFEDTARL)",
    "fred_DFEDTARU": "FRED, borne haute de l'objectif de la Fed (DFEDTARU)",
    "bundesbank_R10XX": "Bundesbank, rendement de l'État fédéral à 10 ans",
    "bundesbank_R02XX": "Bundesbank, rendement de l'État fédéral à 2 ans",
    "bce_courbe_SR_10Y": "BCE Data Portal, courbe AAA de la zone euro, 10 ans",
    "bce_courbe_SR_2Y": "BCE Data Portal, courbe AAA de la zone euro, 2 ans",
    "bis_quotidien": "BRI, taux directeurs quotidiens (WS_CBPOL)",
    "fmi_NGDP_RPCH": "FMI, World Economic Outlook, croissance (NGDP_RPCH)",
    "fmi_PCPIPCH": "FMI, World Economic Outlook, inflation (PCPIPCH)",
    "ocde_cli": "OCDE, indicateur avancé (DF_CLI)",
    "ocde_inflation": "OCDE, prix à la consommation (DF_PRICES_C2018_ALL et DF_PRICES_ALL)",
    "eurostat_ipch": "Eurostat, IPCH de la zone euro (prc_hicp_minr)",
    "bce_taux": "BCE, taux de la facilité de dépôt",
    "boc_V39079": "Banque du Canada, taux cible (V39079)",
    "bcb_432": "Banco Central do Brasil, Selic cible (SGS 432)",
    "yahoo_cours": "Yahoo Finance via yfinance (cuivre, pétrole, dollar, or, taux US)",
}
NOMS_CYCLE = {"monde": "cycle mondial", "etats_unis": "cycle américain", "zone_euro": "cycle de la zone euro",
              "chine": "cycle chinois", "japon": "cycle japonais", "emergents": "cycle des pays émergents"}
SYMBOLES_TAUX = ["^TNX", "^IRX"]


# ------------------------------------------------------------------ collecte

def collecter(f, config: dict, pays: dict, aujourdhui: date):
    debut_m = (aujourdhui - timedelta(days=730)).strftime("%Y-%m")
    long = "2018-01-01"
    court = aujourdhui - timedelta(days=800)
    zones_cli = sorted(set(config["cli_suivis"]) | {p["iso3"] for p in pays.values()})
    zones_inf = sorted({c for z in config["zones"].values() for c in z["inflation"].get("ocde", [])})
    codes_bis = sorted({b["bis"] for b in config["banques_centrales"].values()} | {p["bis"] for p in pays.values()})
    symboles = [m["symbole"] for m in config["marches"]] + SYMBOLES_TAUX
    appels = {
        "fred_T10Y2Y": lambda: f.fred("T10Y2Y", long),
        "fred_T10Y3M": lambda: f.fred("T10Y3M", long),
        "fred_SAHMREALTIME": lambda: f.fred("SAHMREALTIME", long),
        "fred_UNRATE": lambda: f.fred("UNRATE", "2015-01-01"),
        "fred_DFEDTARL": lambda: f.fred("DFEDTARL", court.isoformat()),
        "fred_DFEDTARU": lambda: f.fred("DFEDTARU", court.isoformat()),
        "bundesbank_R10XX": lambda: f.bundesbank("R10XX", long),
        "bundesbank_R02XX": lambda: f.bundesbank("R02XX", long),
        "bce_courbe_SR_10Y": lambda: f.bce_courbe("SR_10Y", long),
        "bce_courbe_SR_2Y": lambda: f.bce_courbe("SR_2Y", long),
        "bis_quotidien": lambda: f.bis_quotidien(codes_bis, court.isoformat()),
        "fmi_NGDP_RPCH": lambda: f.fmi("NGDP_RPCH"),
        "fmi_PCPIPCH": lambda: f.fmi("PCPIPCH"),
        "ocde_cli": lambda: f.ocde_cli(zones_cli, debut_m),
        "ocde_inflation": lambda: f.ocde_inflation(zones_inf, debut_m),
        "eurostat_ipch": lambda: f.eurostat_ipch(["EA"], debut_m),
        "bce_taux": lambda: f.bce_taux(),
        "boc_V39079": lambda: f.boc("V39079", court),
        "bcb_432": lambda: f.bcb(432, court),
        "yahoo_cours": lambda: f.cours(symboles),
    }
    res, etats, modes = {}, {}, {}
    for nom, appel in appels.items():
        try:
            r = appel()
            if nom.startswith("fred_"):
                r, modes[nom] = r
            res[nom] = r
            etats[nom] = "ok" if r else "vide"
            LOG.info("Source %s : %s", nom, "ok" if r else "aucune donnée")
        except Exception as e:  # une source en panne : on continue
            res[nom] = None
            etats[nom] = f"erreur : {str(e)[:160]}"
            LOG.error("Source %s indisponible : %s", nom, str(e)[:200])
    return res, etats, modes


def _fred_source(nom: str, modes: dict) -> str:
    return f"{NOMS_SOURCES[nom]}, {modes.get(nom, 'CSV public')}"


# ------------------------------------------------------------------ analyse

def cycle(res: dict, config: dict, aujourdhui: date, precedent: dict | None) -> dict:
    an = aujourdhui.year
    anciennes = {z["cle"]: z for z in ((precedent or {}).get("cycle") or {}).get("zones", [])}
    cli, inf = res.get("ocde_cli") or {}, res.get("ocde_inflation") or {}
    euro = res.get("eurostat_ipch") or {}
    fmi_g, fmi_i = res.get("fmi_NGDP_RPCH") or {}, res.get("fmi_PCPIPCH") or {}
    zones = []
    for cle, zc in config["zones"].items():
        serie_cli = A.agreger([cli.get(c) for c in zc["cli"] if cli.get(c)]) if all(cli.get(c) for c in zc["cli"]) else []
        if "eurostat" in zc["inflation"]:
            serie_inf, source_inf = euro.get(zc["inflation"]["eurostat"], []), "Eurostat (IPCH, glissement annuel)"
        elif zc["inflation"].get("agregat") == "mediane":
            serie_inf = A.agreger([inf.get(c) for c in zc["inflation"]["ocde"] if inf.get(c)], "mediane")
            source_inf = "OCDE (IPC, médiane des pays de la zone)"
        else:
            serie_inf = next((inf[c] for c in zc["inflation"]["ocde"] if inf.get(c)), [])
            source_inf = "OCDE (IPC, glissement annuel)"

        def fmi(d):
            v = (d or {}).get(zc["fmi"], {})
            return (v[str(an - 1)], v[str(an)]) if str(an) in v and str(an - 1) in v else None
        fg, fi = fmi(fmi_g), fmi(fmi_i)
        z = A.phase_zone(serie_cli, serie_inf, fg, fi, config["seuils"])
        if z is None:
            if cle in anciennes:
                LOG.warning("Cycle %s : données insuffisantes, phase précédente conservée", cle)
                zones.append({**anciennes[cle], "ancienne": True})
            continue
        nom_cli = f"OCDE, {zc['cli_libelle']}"
        z.update({
            "cle": cle, "nom": zc["nom"],
            "texte": A.texte_zone(zc["nom"], z, zc["cli_libelle"], fg, fi, an),
            "confiance": A.confiance_zone(z, aujourdhui),
            "contre_scenario": A.contre_scenario_zone(z, zc["cli_libelle"]),
            "fmi": {"croissance": fg, "inflation": fi, "annees": [an - 1, an]},
            "sources": [f"Indicateur avancé : {nom_cli} (DF_CLI)", f"Inflation : {source_inf}",
                        "Prévisions : FMI, World Economic Outlook (NGDP_RPCH, PCPIPCH)"],
        })
        zones.append(z)
    return {"zones": zones, "date_donnees": max((z["date_donnees"] for z in zones), default=None),
            "methode": "Croissance : indicateur avancé de l'OCDE ; inflation : IPC mensuel. Chaque axe est tranché par 3 signaux "
                       "(variation sur 3 mois, la même un mois plus tôt, prévision du FMI) ; 2 signaux concordants au minimum "
                       "pour changer de direction. Position du point : variations sur 3 mois (indicateur avancé en abscisse, "
                       "inflation en ordonnée) ; la flèche part de la position du mois précédent."}


def recession(res: dict, modes: dict, config: dict, aujourdhui: date, precedent: dict | None) -> dict:
    cfg = config["recession"]
    anciens = {s["cle"]: s for s in ((precedent or {}).get("recession") or {}).get("signaux", [])}
    signaux = []

    def ajouter(cle, libelle, etat, source, verification="source_unique", note=None):
        if etat is None:
            if cle in anciens:
                signaux.append({**anciens[cle], "ancienne": True})
            return
        s = {"cle": cle, "libelle": libelle, **etat, "source": source, "verification": verification}
        if note:
            s["note_verification"] = note
        signaux.append(s)

    t10y2y, t10y3m = res.get("fred_T10Y2Y"), res.get("fred_T10Y3M")
    ajouter("courbe_us_10_2", "Courbe US 10 ans − 2 ans", A.etat_courbe(t10y2y, cfg, aujourdhui) if t10y2y else None,
            _fred_source("fred_T10Y2Y", modes))
    etat_3m = A.etat_courbe(t10y3m, cfg, aujourdhui) if t10y3m else None
    verif, note = "source_unique", None
    cours = res.get("yahoo_cours") or {}
    if etat_3m and cours.get("^TNX") and cours.get("^IRX"):
        yahoo = A.valeur_au(A.ecart(cours["^TNX"], cours["^IRX"]), A.jour(etat_3m["date"]))
        verif = A.verification(etat_3m["valeur"], yahoo, cfg["tolerance_courbe_us"])
        note = f"Yahoo Finance (^TNX − ^IRX) : {A.pts(yahoo)}" if yahoo is not None else None
    ajouter("courbe_us_10_3m", "Courbe US 10 ans − 3 mois", etat_3m, _fred_source("fred_T10Y3M", modes), verif, note)

    b10, b2 = res.get("bundesbank_R10XX"), res.get("bundesbank_R02XX")
    e10, e2 = res.get("bce_courbe_SR_10Y"), res.get("bce_courbe_SR_2Y")
    de = A.ecart(b10, b2) if b10 and b2 else None
    aaa = A.ecart(e10, e2) if e10 and e2 else None
    serie_de, source_de = (de, "Bundesbank, rendements de l'État fédéral à 10 et 2 ans") if de else \
        (aaa, "BCE Data Portal, courbe AAA de la zone euro (10 et 2 ans), en l'absence de la Bundesbank") if aaa else (None, None)
    etat_de = A.etat_courbe(serie_de, cfg, aujourdhui) if serie_de else None
    verif, note = "source_unique", None
    if etat_de and de and aaa:
        v_aaa = A.valeur_au(aaa, A.jour(etat_de["date"]))
        verif = A.verification(etat_de["valeur"], v_aaa, cfg["tolerance_courbe_de"])
        note = f"BCE, courbe AAA de la zone euro : {A.pts(v_aaa)}" if v_aaa is not None else None
    ajouter("courbe_allemagne_10_2", "Courbe Allemagne 10 ans − 2 ans", etat_de, source_de, verif, note)

    sahm, chomage = res.get("fred_SAHMREALTIME"), res.get("fred_UNRATE")
    etat_sahm = None
    verif, note = "source_unique", None
    if sahm:
        d, v = sorted(sahm)[-1]
        etat_sahm = {"valeur": round(v, 2), "date": d, "niveau": A.niveau_sahm(v, cfg)}
        texte = f"règle de Sahm à {A.pts(v)} ({A.date_fr(d[:7])}), seuil de déclenchement à 0,5"
        if chomage:
            dc, vc = sorted(chomage)[-1]
            v12 = A.valeur_au(chomage, A.jour(dc) - timedelta(days=360))
            texte += f" ; chômage à {A.nb(vc, 1)} % ({A.date_fr(dc[:7])})"
            if v12 is not None:
                texte += f", {A.pts(vc - v12, 1)} sur 12 mois"
            calc = dict(A.sahm_calculee(chomage)).get(d[:7])
            verif = A.verification(v, calc, cfg["tolerance_sahm"])
            note = f"recalculée à partir du chômage (UNRATE) : {A.pts(calc)}" if calc is not None else None
            etat_sahm["chomage"] = vc
        etat_sahm["texte"] = texte
    ajouter("sahm", "Règle de Sahm (États-Unis)", etat_sahm,
            f"{_fred_source('fred_SAHMREALTIME', modes)} ; {_fred_source('fred_UNRATE', modes)}", verif, note)

    cli = res.get("ocde_cli") or {}
    for cle, zone, libelle in (("cli_monde", "G20", "Indicateur avancé de l'OCDE, G20"), ("cli_etats_unis", "USA", "Indicateur avancé de l'OCDE, États-Unis")):
        m = A.mensuelle(cli.get(zone) or [])
        etat = None
        if len(m) >= 4:
            (d, v), v3 = m[-1], m[-1][1] - m[-4][1]
            etat = {"valeur": round(v, 2), "variation_3m": round(v3, 2), "date": d, "niveau": A.niveau_cli(v, v3),
                    "texte": f"{A.nb(v, 1)} ({A.date_fr(d)}), {'au-dessus' if v >= 100 else 'en dessous'} de 100 et "
                             f"{'en hausse' if v3 > 0 else 'en baisse' if v3 < 0 else 'stable'} sur 3 mois ({A.pts(v3)})"}
        ajouter(cle, libelle, etat, "OCDE, indicateur avancé (DF_CLI, amplitude ajustée)")

    rouges = [s for s in signaux if s.get("niveau") == "rouge"]
    oranges = [s for s in signaux if s.get("niveau") == "orange"]
    manquants = sum(1 for s in signaux if s.get("ancienne")) + (6 - len(signaux))
    divergents = [s for s in signaux if s.get("verification") == "divergent"]
    confiance = "faible" if manquants >= 2 else "moyen" if (manquants or divergents) else "élevé"
    synthese = (f"{len(rouges)} signal{'aux' if len(rouges) > 1 else ''} rouge{'s' if len(rouges) > 1 else ''}, "
                f"{len(oranges)} orange{'s' if len(oranges) > 1 else ''} sur {len(signaux)}.")
    if rouges:
        synthese += " En rouge : " + ", ".join(s["libelle"] for s in rouges) + "."
    return {"signaux": signaux, "synthese": synthese, "confiance": confiance}


def banques(res: dict, config: dict, calendrier: dict, aujourdhui: date, precedent: dict | None) -> list[dict]:
    bis = res.get("bis_quotidien") or {}
    anciennes = {b["cle"]: b for b in (precedent or {}).get("banques_centrales", [])}
    liste = []
    for cle, cfg in config["banques_centrales"].items():
        nat, nom_nat = None, None
        n = cfg.get("nationale")
        if n:
            nom_nat = n["nom"]
            if n["fournisseur"] == "fred_milieu":
                bas, haut = res.get("fred_DFEDTARL"), res.get("fred_DFEDTARU")
                if bas and haut:
                    h = dict(haut)
                    nat = [(d, (v + h[d]) / 2) for d, v in bas if d in h]
            elif n["fournisseur"] == "bce_taux":
                nat = res.get("bce_taux")
            elif n["fournisseur"] == "boc":
                nat = res.get("boc_V39079")
            elif n["fournisseur"] == "bcb":
                nat = res.get("bcb_432")
        b = A.banque_centrale(cle, cfg, bis.get(cfg["bis"]), sorted(nat) if nat else None, nom_nat,
                              calendrier["banques"].get(cle, {}), aujourdhui)
        if b is None and cle in anciennes:
            b = {**anciennes[cle], "ancienne": True, "prochaine_reunion": A.prochaine_reunion(calendrier["banques"].get(cle, {}), aujourdhui)}
        if b and cle == "fed" and res.get("fred_DFEDTARL") and res.get("fred_DFEDTARU"):
            b["fourchette"] = [sorted(res["fred_DFEDTARL"])[-1][1], sorted(res["fred_DFEDTARU"])[-1][1]]
        if b:
            b["calendrier_source"] = calendrier["banques"].get(cle, {}).get("source")
            liste.append(b)
    return liste


def marches(res: dict, config: dict, precedent: dict | None) -> list[dict]:
    cours = res.get("yahoo_cours") or {}
    anciens = {m["symbole"]: m for m in (precedent or {}).get("marches", [])}
    liste = []
    for m in config["marches"]:
        r = A.marche(cours.get(m["symbole"]), m)
        if r is None and m["symbole"] in anciens:
            r = {**anciens[m["symbole"]], "ancienne": True}
        if r:
            liste.append(r)
    return liste


def lectures_pays(res: dict, config: dict, pays: dict, cyc: dict, bcs: list[dict], aujourdhui: date) -> dict:
    bis = res.get("bis_quotidien") or {}
    cli = res.get("ocde_cli") or {}
    par_cle = {b["cle"]: b for b in bcs}
    zones = {z["cle"]: z for z in cyc["zones"]}
    sorties = {}
    for code, p in pays.items():
        cle_bc = config["banque_par_bis"].get(p["bis"])
        if cle_bc and cle_bc in par_cle:
            b, nom_b = par_cle[cle_bc], par_cle[cle_bc]["nom"]
        else:
            b = A.banque_centrale(p["bis"], {"nom": "", "pays": p["nom"]}, bis.get(p["bis"]), None, None, {"sans_calendrier": True}, aujourdhui)
            nom_b = None
        cle_zone = config["zone_par_pays"].get(code, "monde")
        texte = A.lecture_pays(code, p, b, nom_b, cli.get(p["iso3"]), zones.get(cle_zone), NOMS_CYCLE[cle_zone])
        sorties[code] = {"texte": texte, "date": aujourdhui.isoformat(),
                         "sources": ["BRI, taux directeurs" if not (cle_bc and cle_bc in par_cle) else par_cle[cle_bc]["source"],
                                     "OCDE, indicateur avancé (DF_CLI)", "Agent macro, phase du cycle"]}
    return sorties


# ------------------------------------------------------------------ écritures

def recap_markdown(jour: date, d: dict, signaux_jour: list[dict], etats: dict) -> str:
    l = [f"# Agent macro — récapitulatif du {A.date_fr(jour.isoformat())}", "",
         "## Phase du cycle", ""]
    for z in d["cycle"]["zones"]:
        change = f" (précédente : « {z['phase_precedente']} », depuis {A.date_fr(z['depuis'])})" if z.get("phase_precedente") else ""
        l.append(f"- **{z['nom']}** : « {z['phase']} »{change}, confiance {z.get('confiance', '?')}{' — valeur ancienne' if z.get('ancienne') else ''}")
    l += ["", "## Signaux de récession", "", d["recession"]["synthese"], ""]
    for s in d["recession"]["signaux"]:
        l.append(f"- {s['libelle']} : {s.get('niveau', '?')} — {s.get('texte', '')}")
    l += ["", "## Banques centrales", ""]
    for b in d["banques_centrales"]:
        pr = b["prochaine_reunion"]
        prochaine = f"{A.date_fr(pr['date'])} (dans {pr['jours']} jours)" if pr.get("date") else pr.get("note") or "inconnue"
        l.append(f"- {b['nom']} : {A.phrase_banque(b, b['nom'])} ; prochaine réunion : {prochaine}")
    l += ["", "## Signaux détectés aujourd'hui", ""]
    l += [f"- [{s['importance']}] {s['titre']}" for s in signaux_jour] or ["- aucun"]
    erreurs = [k for k, v in etats.items() if v != "ok"]
    l += ["", "## Sources en échec", ""] + ([f"- {NOMS_SOURCES.get(k, k)} : {etats[k]}" for k in erreurs] or ["- aucune"])
    return "\n".join(l) + "\n"


def sources_sante(etats: dict, modes: dict) -> list[dict]:
    res = []
    for nom, etat in etats.items():
        detail = modes.get(nom)
        if etat == "ok":
            res.append({"nom": NOMS_SOURCES.get(nom, nom), "etat": "ok", "detail": detail})
        elif etat == "vide":
            res.append({"nom": NOMS_SOURCES.get(nom, nom), "etat": "partielle", "detail": "aucune donnée reçue"})
        else:
            res.append({"nom": NOMS_SOURCES.get(nom, nom), "etat": "échec", "detail": etat.removeprefix("erreur : ")})
    return res


def indicateurs_sante(d: dict) -> dict:
    """Sources valides par indicateur (règle « dégradé » commune aux agents)."""
    ind = {}
    for s in d["recession"]["signaux"]:
        valides = [] if s.get("ancienne") else ["principale"] + (["vérification"] if s.get("verification") in ("concordant", "divergent") else [])
        ind[f"Récession · {s['libelle']}"] = {"valides": valides, "configurees": ["principale", "vérification"]}
    for z in d["cycle"]["zones"]:
        ok = [] if z.get("ancienne") else ["OCDE / Eurostat"] + (["FMI"] if (z.get("fmi") or {}).get("croissance") else [])
        ind[f"Cycle · {z['nom']}"] = {"valides": ok, "configurees": ["OCDE / Eurostat", "FMI"]}
    for b in d["banques_centrales"]:
        ok = [] if b.get("ancienne") else (["BRI", "nationale"] if b.get("verification") != "source_unique" else ["principale"])
        ind[f"Banque centrale · {b['nom']}"] = {"valides": ok, "configurees": ["BRI", "nationale", "principale"]}
    for m in d["marches"]:
        ind[f"Marché · {m['nom']}"] = {"valides": [] if m.get("ancienne") else ["Yahoo"], "configurees": ["Yahoo"]}
    return ind


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent macro : vue d'ensemble de l'économie mondiale (sans IA).")
    ap.add_argument("--test", action="store_true", help="données de test (agents/macro/tests/donnees), sans réseau")
    ap.add_argument("--capturer", action="store_true", help="enregistre les réponses réelles comme données de test")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier de sortie (data/)")
    ap.add_argument("--date", help="date du jour (AAAA-MM-JJ), utile pour les tests")
    args = ap.parse_args(argv)

    config = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
    pays = {k: v for k, v in json.loads((RACINE / "agents" / "pays" / "config.json").read_text(encoding="utf-8"))["pays"].items()}
    calendrier = json.loads((DOSSIER / "calendrier_banques_centrales.json").read_text(encoding="utf-8"))
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    data = Path(args.data)

    dossier_test = DOSSIER / "tests" / "donnees"
    if args.test:
        f = FournisseurTest(dossier_test)
    else:
        f = FournisseurReel(RACINE / "agents" / ".cache")
        if args.capturer:
            f = Capture(f, dossier_test, [z["fmi"] for z in config["zones"].values()])
    LOG.info("Agent macro %s — %s", VERSION_AGENT, "données de test" if args.test else "sources réelles")

    res, etats, modes = collecter(f, config, pays, aujourdhui)
    if all(v != "ok" for v in etats.values()):
        LOG.error("Aucune source n'a répondu : fichiers inchangés.")
        return 1

    ancien = lire_json(data / "macro.json")
    precedent = (ancien or {}).get("donnees") if ancien and (ancien.get("meta") or {}).get("fictif") is False else None

    cyc = cycle(res, config, aujourdhui, precedent)
    rec = recession(res, modes, config, aujourdhui, precedent)
    bcs = banques(res, config, calendrier, aujourdhui, precedent)
    mch = marches(res, config, precedent)
    depuis_graphique = aujourdhui - timedelta(days=730)
    courbe = {
        "series": {"T10Y2Y": A.hebdomadaire(res.get("fred_T10Y2Y") or [], depuis_graphique),
                   "T10Y3M": A.hebdomadaire(res.get("fred_T10Y3M") or [], depuis_graphique)},
        "libelles": {"T10Y2Y": "10 ans − 2 ans", "T10Y3M": "10 ans − 3 mois"},
        "source": f"FRED (T10Y2Y, T10Y3M), {modes.get('fred_T10Y2Y', 'CSV public')} ; dernier point de chaque semaine",
    }
    if not courbe["series"]["T10Y2Y"] and precedent:
        courbe = {**precedent.get("courbe_us", {}), "ancienne": True}
    monde = next((z for z in cyc["zones"] if z["cle"] == "monde"), None)
    donnees = {
        "date": aujourdhui.isoformat(),
        "cycle": cyc,
        "recession": rec,
        "banques_centrales": bcs,
        "courbe_us": courbe,
        "marches": mch,
        "confiance": monde["confiance"] if monde else "faible",
        "contre_scenario": (monde["contre_scenario"] if monde else []) + [
            "Un déclenchement de la règle de Sahm (0,5 pt) ou une nouvelle inversion de la courbe 10 ans − 3 mois "
            "contredirait une lecture favorable du cycle américain."],
    }
    donnees["lectures_pays"] = lectures_pays(res, config, pays, cyc, bcs, aujourdhui)

    # Contrôle du ton (pas de superlatifs) sur tous les textes produits
    textes = [z.get("texte") for z in cyc["zones"]] + [l["texte"] for l in donnees["lectures_pays"].values()] + donnees["contre_scenario"]
    if not A.conformes(textes):
        LOG.error("Un texte contient un mot interdit : vérifier les règles de rédaction.")

    # Signaux pour le futur chef d'orchestre
    nouveaux = A.signaux(precedent, donnees, aujourdhui)
    fichier_signaux = data / "signaux" / "macro.json"
    existants = ((lire_json(fichier_signaux) or {}).get("donnees") or [])
    vus = {(s["type"], s["cle"], s["date"]) for s in existants}
    tous = existants + [s for s in nouveaux if (s["type"], s["cle"], s["date"]) not in vus]
    limite = (aujourdhui - timedelta(days=180)).isoformat()
    tous = sorted((s for s in tous if s["date"] >= limite), key=lambda s: s["date"], reverse=True)
    ecrire_json(fichier_signaux, enveloppe(tous, "agent-macro", fictif=False, version_agent=VERSION_AGENT,
                                           description="Signaux candidats pour le chef d'orchestre (180 derniers jours)"))

    objet = enveloppe(donnees, "agent-macro", fictif=False, version_agent=VERSION_AGENT,
                      mise_a_jour_precedente=(ancien or {}).get("meta", {}).get("genere_le") if precedent else None,
                      etat_des_sources={NOMS_SOURCES.get(k, k): v for k, v in etats.items()},
                      calendrier_releve_le=max(b.get("releve_le", "") for b in calendrier["banques"].values()))
    ecrire_json(data / "macro.json", objet)
    ecrire_json(data / "historique" / "macro" / f"{aujourdhui.isoformat()}.json", {
        "meta": {"genere_le": objet["meta"]["genere_le"], "source": "agent-macro", "version_agent": VERSION_AGENT},
        "donnees": {"phases": {z["cle"]: {"phase": z["phase"], "position": z.get("position"), "confiance": z.get("confiance")} for z in cyc["zones"]},
                    "recession": {s["cle"]: {"niveau": s.get("niveau"), "valeur": s.get("valeur")} for s in rec["signaux"]},
                    "taux": {b["cle"]: b["taux"] for b in bcs},
                    "marches": {m["symbole"]: m["valeur"] for m in mch}}})
    (data / "recap").mkdir(parents=True, exist_ok=True)
    (data / "recap" / f"macro-{aujourdhui.isoformat()}.md").write_text(recap_markdown(aujourdhui, donnees, nouveaux, etats), encoding="utf-8")

    # Santé (écran « Santé des agents ») : sources, indicateurs, échéances des calendriers
    chemin_journal = data / "journal" / "agent-macro.json"
    journal_existant = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    entree = {"genere_le": objet["meta"]["genere_le"], "etat_des_sources": etats, "signaux": [s["titre"] for s in nouveaux]}
    journal_existant["donnees"] = (journal_existant.get("donnees", []) + [entree])[-90:]
    journal_existant["meta"] = {**journal_existant.get("meta", {}), "genere_le": objet["meta"]["genere_le"], "source": "agent-macro",
                                "version_agent": VERSION_AGENT, "description": "État des sources et signaux, à chaque exécution"}
    ecrire_json(chemin_journal, journal_existant)
    bloc = sante.bloc_sante("macro", "Agent macro", 3, "agent-macro.yml", sources_sante(etats, modes),
                            datetime.now(timezone.utc) if not args.date else datetime.combine(aujourdhui, datetime.min.time(), timezone.utc).replace(hour=6, minute=30),
                            ((journal_existant.get("meta") or {}).get("sante")), indicateurs=indicateurs_sante(donnees))
    bloc["echeances"] = [{"libelle": f"Calendrier des réunions : {b['nom']}", "jusqua": max(b["dates"]), "source": b["source"]}
                         for b in calendrier["banques"].values() if not b.get("sans_calendrier") and b.get("dates")]
    sante.enregistrer_sante(chemin_journal, bloc, forcer=True)

    LOG.info("Phases : %s", ", ".join(f"{z['nom']} « {z['phase']} »" for z in cyc["zones"]))
    LOG.info("Récession : %s", rec["synthese"])
    LOG.info("Signaux détectés : %d ; santé : %d/%d sources, %s", len(nouveaux), bloc["sources_ok"], bloc["sources_total"],
             "dégradé" if bloc["degrade"] else "aucun indicateur dégradé")
    return 0
