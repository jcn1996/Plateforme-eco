"""
Agent pays : remplace les données fictives de data/pays.json par de vraies données gratuites.

Déroulé :
1. lit l'ancien data/pays.json (pour les champs « precedent » et les valeurs de secours) ;
2. interroge les sources (instituts nationaux, banques centrales, FMI, OCDE, BRI, Banque mondiale,
   Eurostat, BCE, Yahoo Finance) ; une source en panne ne bloque pas l'agent ;
3. pour chaque indicateur, contrôle la qualité de chaque source, choisit la valeur retenue
   selon la hiérarchie des sources et la compare aux autres (vérification croisée, voir sources.md) ;
4. calcule les notes /100, la note globale et les niveaux de confiance ;
5. rédige verdict, lecture et « Ce qui pourrait me donner tort » (règles, ou Gemini si une clé est fournie) ;
6. écrit data/pays.json, data/historique/pays/AAAA-MM-JJ.json, le journal des sources
   (data/journal/agent-pays.json) et le récapitulatif (data/recap/pays-AAAA-MM-JJ.md),
   seulement si quelque chose a changé.

Lancement : python -m agents.pays            (vraies sources)
            python -m agents.pays --test     (données de test, sans réseau)
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json, maintenant_iso
from . import croisement, notation, recap, textes
from .croisement import LIBELLES_NIVEAUX, date_periode
from .sources import SOURCES, FournisseurReel, FournisseurTest

LOG = journal("agent-pays")
RACINE = Path(__file__).resolve().parents[2]
DOSSIER_AGENT = Path(__file__).resolve().parent
VERSION_AGENT = "1.1"

LIBELLES = {
    "croissance_pib": "Croissance du PIB",
    "indicateur_avance": "Indicateur avancé (OCDE)",
    "inflation": "Inflation",
    "taux_reel": "Taux réel",
    "valorisation": "Valorisation relative",
    "momentum": "Momentum boursier 12 mois",
    "devise_3m": "Devise sur 3 mois",
    "solde_courant": "Solde courant",
    "flux_etrangers": "Flux étrangers",
}
PRINCIPAUX = ["croissance_pib", "indicateur_avance", "inflation", "taux_reel", "valorisation", "momentum"]
DETAIL = ["devise_3m", "solde_courant", "flux_etrangers"]

# Indicateurs de la Banque mondiale (API v2)
BM_SERIES = {"bm_croissance": "NY.GDP.MKTP.KD.ZG", "bm_inflation": "FP.CPI.TOTL.ZG", "bm_solde_courant": "BN.CAB.XOKA.GD.ZS"}
# Nom court de la source, utilisé dans les phrases (« selon le FMI »)
COURTS = {"fmi": "le FMI", "ocde_eo": "l'OCDE", "bm": "la Banque mondiale", "ocde_inflation": "l'OCDE", "eurostat": "Eurostat",
          "bis": "la BRI", "bce_taux": "la BCE", "bce_change": "la BCE"}


# ---------------------------------------------------------------------------
# Petits outils
# ---------------------------------------------------------------------------

def _absent(cle, raison, rapport=None) -> dict:
    ind = {"libelle": LIBELLES[cle], "valeur": None, "unite": "", "note": None, "disponible": False, "raison": raison}
    if rapport is not None:
        ind["sources"] = rapport
        ind["verification"] = "aucune_source"
    return ind


def _valeur_a_date(serie: list[tuple[str, float]], limite: date):
    """Dernière observation à la date limite ou avant."""
    candidates = [(d, v) for d, v in serie if date_periode(d) <= limite]
    return candidates[-1] if candidates else None


def _mensuelle(serie: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Normalise une série mensuelle : dates 'AAAA-MM-JJ' → 'AAAA-MM' (dernière valeur du mois)."""
    return croisement.derniere_par_mois([(str(d)[:7], v) for d, v in serie])


def _cand(source, nom, niveau, valeur, periode, nature, **extra) -> dict:
    return {"source": source, "nom": nom, "niveau": niveau, "valeur": valeur, "date": periode, "nature": nature, **extra}


def _echec(source, nom, niveau, raison) -> dict:
    return {"source": source, "nom": nom, "niveau": niveau, "echec": raison}


# ---------------------------------------------------------------------------
# Collecte des sources (chaque source peut échouer sans faire tomber l'agent)
# ---------------------------------------------------------------------------

def collecter(fournisseur, config: dict, aujourdhui: date) -> tuple[dict, dict]:
    """Renvoie (résultats, états). Une source en erreur vaut None dans les résultats."""
    pays = config["pays"]
    couverture = config["couverture"]
    iso3 = sorted({p["iso3"] for p in pays.values()})
    iso3_eo = sorted({pays[c]["iso3"] for c in couverture["ocde_eo"] if c in pays})
    bis = sorted({p["bis"] for p in pays.values()})
    etfs = sorted({p["etf"] for p in pays.values() if p.get("etf")})
    devises = sorted({p["devise"]["symbole"] for p in pays.values() if p.get("devise")})
    debut = (aujourdhui - timedelta(days=400)).strftime("%Y-%m")
    depuis = aujourdhui - timedelta(days=800)

    appels = {
        "fmi_croissance": lambda: fournisseur.fmi("NGDP_RPCH"),
        "fmi_inflation": lambda: fournisseur.fmi("PCPIPCH"),
        "fmi_solde_courant": lambda: fournisseur.fmi("BCA_NGDPD"),
        "ocde_cli": lambda: fournisseur.ocde_cli(iso3, debut),
        "ocde_inflation": lambda: fournisseur.ocde_inflation(iso3, debut),
        "ocde_eo": lambda: fournisseur.ocde_eo(iso3_eo, aujourdhui.year),
        "bis": lambda: fournisseur.bis_taux(bis, debut),
        "eurostat": lambda: fournisseur.eurostat_ipch(sorted(set(couverture["eurostat"].values())), debut),
        "bce_taux": lambda: fournisseur.bce_taux(),
        "bce_change": lambda: fournisseur.bce_change(config["devises_bce"]),
        "yahoo_cours": lambda: fournisseur.cours(etfs + devises),
        "yahoo_per": lambda: fournisseur.per(etfs),
    }
    for nom, serie in BM_SERIES.items():
        appels[nom] = (lambda s: lambda: fournisseur.banque_mondiale(s, aujourdhui.year))(serie)
    for code, liste in config["sources_nationales"].items():
        if code.startswith("_"):
            continue
        for s in liste:
            appels.setdefault(_cle_nationale(s), (lambda s: lambda: getattr(fournisseur, s["fournisseur"])(
                *((s["serie"],) if s["fournisseur"] == "dbnomics" else (s["serie"], depuis))))(s))

    resultats, etats = {}, {}
    for nom, appel in appels.items():
        try:
            resultats[nom] = appel()
            vide = not resultats[nom]
            etats[nom] = "vide" if vide else "ok"
            attendus = {"yahoo_per": len(etfs), "yahoo_cours": len(etfs) + len(devises)}.get(nom)
            if attendus and not vide and len(resultats[nom]) < attendus:
                etats[nom] = f"partiel ({len(resultats[nom])}/{attendus})"
            (LOG.warning if vide else LOG.info)("Source %s : %s", nom, "aucune donnée" if vide else f"{len(resultats[nom])} séries ou valeurs")
        except Exception as e:  # une source en panne : on continue avec les autres
            resultats[nom] = None
            etats[nom] = f"erreur : {str(e)[:160]}"
            (LOG.warning if "FRED_API_KEY" in str(e) else LOG.error)("Source %s indisponible : %s", nom, str(e)[:200])
    return resultats, etats


def _cle_nationale(s: dict) -> str:
    return f"national_{s['fournisseur']}_{str(s['serie']).replace('/', '_')}"


# ---------------------------------------------------------------------------
# Candidats : une valeur par source, pour chaque indicateur
# ---------------------------------------------------------------------------

def _annuel(src, cle, iso3, annees, source, nom_modele, niveau="internationale", **format_nom):
    """Candidat annuel (FMI, OCDE EO, Banque mondiale) : première année disponible parmi « annees »."""
    donnees = src.get(cle)
    if donnees is None:
        return _echec(source, nom_modele.format(annee=annees[0], **format_nom), niveau, "source indisponible lors de cette exécution")
    valeurs = donnees.get(iso3, {})
    for a in annees:
        if valeurs.get(str(a)) is not None:
            return _cand(source, nom_modele.format(annee=a, **format_nom), niveau, float(valeurs[str(a)]), str(a), "annuelle")
    return _echec(source, nom_modele.format(annee=annees[0], **format_nom), niveau, "aucune donnée publiée pour ce pays")


def _mensuel(src, cle, zone, source, nom, niveau="internationale", **extra):
    donnees = src.get(cle)
    if donnees is None:
        return _echec(source, nom, niveau, "source indisponible lors de cette exécution")
    serie = donnees.get(zone) if isinstance(donnees, dict) else donnees
    if not serie:
        return _echec(source, nom, niveau, "aucune donnée publiée pour ce pays")
    serie = _mensuelle(serie)
    return _cand(source, nom, niveau, serie[-1][1], serie[-1][0], "mensuelle", serie=serie, **extra)


def _national(src, s: dict):
    """Source nationale officielle : série déjà en %, indice à transformer en glissement annuel, ou taux quotidien."""
    cle, nom = _cle_nationale(s), s["nom"]
    serie = src.get(cle)
    if serie is None:
        return _echec(cle, nom, "nationale", "source indisponible lors de cette exécution")
    if not serie:
        return _echec(cle, nom, "nationale", "aucune donnée")
    serie = _mensuelle(serie)
    if s["transformation"] == "glissement":
        serie = croisement.glissement_annuel(serie)
        if not serie:
            return _echec(cle, nom, "nationale", "série trop courte pour calculer un glissement annuel")
    return _cand(cle, nom, "nationale", serie[-1][1], serie[-1][0], "mensuelle", serie=serie)


def candidats_pays(code: str, cfg: dict, src: dict, config: dict, aujourdhui: date) -> dict:
    """Candidats des indicateurs macroéconomiques d'un pays, dans l'ordre de la configuration."""
    iso3, annee = cfg["iso3"], aujourdhui.year
    couv = config["couverture"]
    nationales = config["sources_nationales"].get(code, [])
    dans_eo = code in couv["ocde_eo"]
    dans_bm = code not in couv.get("banque_mondiale_absents", [])
    zone_euro = code in couv["zone_euro"]
    c = {k: [] for k in ("croissance_pib", "inflation", "indicateur_avance", "taux_directeur", "solde_courant")}

    # Croissance du PIB : FMI (année en cours), OCDE (prévision de l'année), Banque mondiale (dernière année)
    c["croissance_pib"].append(_annuel(src, "fmi_croissance", iso3, (annee, annee - 1), "fmi", SOURCES["fmi"], serie="NGDP_RPCH"))
    if dans_eo:
        c["croissance_pib"].append(_annuel(src, "ocde_eo", iso3, (annee,), "ocde_eo", SOURCES["ocde_eo"]))
    if dans_bm:
        c["croissance_pib"].append(_annuel(src, "bm_croissance", iso3, (annee - 1,), "bm", SOURCES["bm"],
                                           indicateur="croissance du PIB (NY.GDP.MKTP.KD.ZG)"))

    # Inflation : institut national, OCDE (IPC), Eurostat (IPCH), FMI et Banque mondiale (annuels)
    for s in nationales:
        if s["indicateur"] == "inflation":
            c["inflation"].append(_national(src, s))
    if code in couv["ocde_inflation"]:
        c["inflation"].append(_mensuel(src, "ocde_inflation", iso3, "ocde_inflation", SOURCES["ocde_inflation"]))
    if code in couv["eurostat"]:
        c["inflation"].append(_mensuel(src, "eurostat", couv["eurostat"][code], "eurostat", SOURCES["eurostat"]))
    c["inflation"].append(_annuel(src, "fmi_inflation", iso3, (annee, annee - 1), "fmi", SOURCES["fmi"], serie="PCPIPCH"))
    if dans_bm:
        c["inflation"].append(_annuel(src, "bm_inflation", iso3, (annee - 1,), "bm", SOURCES["bm"],
                                      indicateur="inflation (FP.CPI.TOTL.ZG)"))

    # Indicateur avancé : seule l'OCDE le publie
    if code in couv["ocde_cli"]:
        c["indicateur_avance"].append(_mensuel(src, "ocde_cli", iso3, "ocde_cli", SOURCES["ocde_cli"]))

    # Taux directeur : banque centrale nationale (BCE pour la zone euro), BRI
    for s in nationales:
        if s["indicateur"] == "taux_directeur":
            c["taux_directeur"].append(_national(src, s))
    if zone_euro:
        c["taux_directeur"].append(_mensuel(src, "bce_taux", None, "bce_taux", SOURCES["bce_taux"], niveau="nationale"))
    c["taux_directeur"].append(_mensuel(src, "bis", cfg["bis"], "bis", SOURCES["bis"]))

    # Solde courant : FMI et Banque mondiale, sur la dernière année écoulée (comparable)
    c["solde_courant"].append(_annuel(src, "fmi_solde_courant", iso3, (annee - 1, annee), "fmi", SOURCES["fmi"], serie="BCA_NGDPD"))
    if dans_bm:
        c["solde_courant"].append(_annuel(src, "bm_solde_courant", iso3, (annee - 1,), "bm", SOURCES["bm"],
                                          indicateur="solde courant (BN.CAB.XOKA.GD.ZS)"))
    return c


def _variation_quotidienne(serie, jours: int, inverse: bool = False):
    """(date, variation en %) entre la dernière observation et celle d'il y a « jours » jours."""
    derniere_date, dernier = serie[-1]
    avant = _valeur_a_date(serie, date_periode(derniere_date) - timedelta(days=jours))
    if not avant:
        return None
    return derniere_date, ((avant[1] / dernier - 1) if inverse else (dernier / avant[1] - 1)) * 100


def candidats_marche(cfg: dict, src: dict, config: dict) -> dict:
    """Candidats des indicateurs de marché : Yahoo Finance, et la BCE pour les devises."""
    c = {"momentum": [], "devise_3m": [], "per": []}
    etf, devise = cfg.get("etf"), cfg.get("devise")
    cours, pers = src.get("yahoo_cours"), src.get("yahoo_per")

    if etf:
        nom = SOURCES["yahoo_prix"].format(symbole=etf)
        if cours is None:
            c["momentum"].append(_echec("yahoo_cours", nom, "marche", "source indisponible lors de cette exécution"))
        elif not cours.get(etf):
            c["momentum"].append(_echec("yahoo_cours", nom, "marche", f"aucun cours pour {etf}"))
        else:
            r = _variation_quotidienne(cours[etf], 365)
            c["momentum"].append(_cand("yahoo_cours", nom, "marche", r[1], r[0], "quotidienne", symbole=etf) if r else
                                 _echec("yahoo_cours", nom, "marche", "moins de 12 mois de cours"))
        nom = SOURCES["yahoo_per"].format(symbole=etf)
        if pers is None:
            c["per"].append(_echec("yahoo_per", nom, "marche", "source indisponible lors de cette exécution"))
        elif not pers.get(etf):
            c["per"].append(_echec("yahoo_per", nom, "marche", f"PER de {etf} non publié"))
        else:
            c["per"].append(_cand("yahoo_per", nom, "marche", float(pers[etf]), None, "quotidienne", symbole=etf))

    if devise:
        # Cours de référence de la BCE : la valeur en dollars d'une devise = (USD/EUR) / (devise/EUR)
        code_devise = devise["libelle"]
        bce = src.get("bce_change")
        if code_devise == "EUR" or code_devise in config["devises_bce"]:
            nom = SOURCES["bce_change"]
            if bce is None:
                c["devise_3m"].append(_echec("bce_change", nom, "internationale", "source indisponible lors de cette exécution"))
            elif not bce.get("USD") or (code_devise != "EUR" and not bce.get(code_devise)):
                c["devise_3m"].append(_echec("bce_change", nom, "internationale", f"cours {code_devise} absent"))
            else:
                usd = dict(bce["USD"])
                autre = dict(bce[code_devise]) if code_devise != "EUR" else None
                serie = [(d, usd[d] / autre[d] if autre else usd[d]) for d in sorted(usd) if not autre or d in autre]
                r = _variation_quotidienne(serie, 91) if serie else None
                if r:
                    c["devise_3m"].append(_cand("bce_change", nom, "internationale", r[1], r[0], "quotidienne"))
        nom = SOURCES["yahoo_devise"].format(symbole=devise["symbole"])
        if cours is None:
            c["devise_3m"].append(_echec("yahoo_cours", nom, "marche", "source indisponible lors de cette exécution"))
        elif not cours.get(devise["symbole"]):
            c["devise_3m"].append(_echec("yahoo_cours", nom, "marche", f"aucun cours pour {devise['symbole']}"))
        else:
            # « inverse » : la paire est cotée en devise locale pour 1 dollar (hausse = la devise faiblit)
            r = _variation_quotidienne(cours[devise["symbole"]], 91, devise["inverse"])
            if r:
                c["devise_3m"].append(_cand("yahoo_cours", nom, "marche", r[1], r[0], "quotidienne"))
    return c


# ---------------------------------------------------------------------------
# Indicateurs d'un pays : vérification croisée et valeur retenue
# ---------------------------------------------------------------------------

def _publier(cle: str, choix: dict, unite: str, **extra) -> dict:
    r = choix["retenu"]
    return {"libelle": LIBELLES[cle], "valeur": round(r["valeur"], 2), "unite": unite, "date": r["date"], "source": r["nom"],
            "source_courte": COURTS.get(r["source"], "la source nationale" if r["niveau"] == "nationale" else "le marché"),
            "niveau_source": r["niveau"], "frequence": r["nature"], "sources": choix["sources"],
            "verification": choix["verification"], "ecart_max": choix["ecart_max"], **extra}


def indicateurs_pays(code: str, cfg: dict, src: dict, aujourdhui: date, config: dict) -> tuple[dict, list]:
    """Renvoie (indicateurs, tentatives). Les tentatives listent chaque source essayée et son statut."""
    bornes, tol = config["bornes_aberrantes"], config["tolerances_divergence"]
    cands = {**candidats_pays(code, cfg, src, config, aujourdhui), **candidats_marche(cfg, src, config)}
    choix = {}
    for cle, liste in cands.items():
        if cle == "per":  # le PER n'a pas de date : contrôlé seulement contre les bornes
            for x in liste:
                x["date"] = aujourdhui.isoformat()
        choix[cle] = croisement.choisir(liste, bornes.get(cle), tol.get(cle), aujourdhui)
    tentatives = [{"indicateur": cle, **s} for cle, ch in choix.items() for s in ch["sources"]]

    sortie = {}
    for cle, unite in (("croissance_pib", "%"), ("solde_courant", "% du PIB"), ("momentum", "%"), ("devise_3m", "%")):
        ch = choix[cle]
        if ch["retenu"]:
            extra = {}
            if cle == "momentum":
                extra["symbole"] = ch["retenu"].get("symbole")
            if cle == "devise_3m":
                extra["devise"] = cfg["devise"]["libelle"]
            sortie[cle] = _publier(cle, ch, unite, **extra)
        else:
            sortie[cle] = _absent(cle, _raison_absence(ch, cle, cfg), ch["sources"])

    ch = choix["inflation"]
    cible = cfg.get("cible_inflation")
    sortie["inflation"] = (_publier("inflation", ch, "%", cible=cible) if ch["retenu"] else
                           _absent("inflation", _raison_absence(ch, "inflation", cfg), ch["sources"]))

    ch = choix["indicateur_avance"]
    if ch["retenu"]:
        serie = ch["retenu"]["serie"]
        trois = serie[-4][1] if len(serie) >= 4 else None
        sortie["indicateur_avance"] = _publier("indicateur_avance", ch, "", pente_3_mois=round(serie[-1][1] - trois, 2) if trois else None,
                                               valeur_3_mois=round(trois, 2) if trois else None)
    else:
        sortie["indicateur_avance"] = _absent("indicateur_avance", _raison_absence(ch, "indicateur_avance", cfg), ch["sources"])

    # Taux réel = taux directeur retenu − inflation retenue ; direction de la banque centrale sur 6 mois
    ch, inflation = choix["taux_directeur"], sortie["inflation"]
    if ch["retenu"] and inflation.get("valeur") is not None:
        r = ch["retenu"]
        il_y_a_6_mois = _valeur_a_date(r["serie"], date_periode(r["date"]) - timedelta(days=182))
        ecart = r["valeur"] - il_y_a_6_mois[1] if il_y_a_6_mois else 0
        direction = "baisse" if ecart <= -0.25 else "hausse" if ecart >= 0.25 else "stable"
        verif = ("divergent" if "divergent" in (ch["verification"], inflation["verification"]) else
                 "concordant" if ch["verification"] == inflation["verification"] == "concordant" else "source_unique")
        sortie["taux_reel"] = {**_publier("taux_reel", {**ch, "retenu": {**r, "valeur": r["valeur"] - inflation["valeur"]}}, "%",
                                          taux_directeur=round(r["valeur"], 2), direction=direction, variation_6_mois=round(ecart, 2)),
                               "source": r["nom"] + " ; inflation : voir ci-dessus", "verification": verif,
                               "verification_taux_directeur": ch["verification"], "verification_inflation": inflation["verification"]}
    else:
        raison = "inflation indisponible" if ch["retenu"] else _raison_absence(ch, "taux_reel", cfg)
        sortie["taux_reel"] = _absent("taux_reel", raison, ch["sources"])

    # Valorisation : PER de l'ETF (l'écart à la médiane est calculé ensuite, pour tous les pays)
    ch = choix["per"]
    sortie["valorisation"] = ({"_per": ch["retenu"]["valeur"], "_etf": cfg["etf"], "_sources": ch["sources"]} if ch["retenu"] else
                              _absent("valorisation", "aucun ETF pays coté" if not cfg.get("etf") else _raison_absence(ch, "valorisation", cfg), ch["sources"]))
    sortie["flux_etrangers"] = _absent("flux_etrangers", "non disponible : aucune source gratuite fiable identifiée pour l'instant")
    return sortie, tentatives


def _raison_absence(choix: dict, cle: str, cfg: dict) -> str:
    if not choix["sources"]:
        return {"indicateur_avance": "non publié par l'OCDE pour ce pays", "momentum": "aucun ETF pays coté",
                "devise_3m": "cours de change indisponible"}.get(cle, "aucune source ne couvre ce pays")
    raisons = sorted({f"{s['nom'].split(',')[0]} : {s['raison']}" for s in choix["sources"] if s.get("raison")})
    return "aucune valeur valable (" + " ; ".join(raisons) + ")"


def completer_valorisation(par_pays: dict, aujourdhui: date) -> None:
    """Valorisation relative = PER de l'ETF comparé à la médiane des pays suivis (en %)."""
    pers = [ind["valorisation"]["_per"] for ind in par_pays.values() if "_per" in ind["valorisation"]]
    for ind in par_pays.values():
        v = ind["valorisation"]
        if "_per" not in v:
            continue
        if len(pers) < 5:
            ind["valorisation"] = _absent("valorisation", "trop peu de PER disponibles pour calculer une médiane", v["_sources"])
            continue
        med = median(pers)
        ind["valorisation"] = {
            "libelle": LIBELLES["valorisation"], "valeur": round((v["_per"] / med - 1) * 100, 2), "unite": "%", "date": aujourdhui.isoformat(),
            "source": SOURCES["yahoo_per"].format(symbole=v["_etf"]) + " ; médiane des pays suivis", "source_courte": "le marché",
            "niveau_source": "marche", "frequence": "quotidienne", "sources": v["_sources"], "verification": "source_unique", "ecart_max": None,
            "per": round(v["_per"], 1), "mediane": round(med, 1), "symbole": v["_etf"],
        }


# ---------------------------------------------------------------------------
# Notes, secours, contrôles, tendances
# ---------------------------------------------------------------------------

def noter(cle: str, ind: dict) -> int | None:
    v = ind.get("valeur")
    if v is None:
        return None
    if cle == "croissance_pib":
        return notation.note_croissance(v)
    if cle == "indicateur_avance":
        return notation.note_indicateur_avance(v, ind.get("valeur_3_mois"))
    if cle == "inflation":
        return notation.note_inflation(v, ind.get("cible"))
    if cle == "taux_reel":
        return notation.note_taux_reel(v, ind.get("direction"))
    if cle == "valorisation":
        return notation.note_valorisation(v)
    if cle == "momentum":
        return notation.note_momentum(v)
    if cle == "devise_3m":
        return notation.note_devise(v)
    if cle == "solde_courant":
        return notation.note_solde_courant(v)
    return None


def secours(cle: str, nouveau: dict, ancien: dict | None, aujourdhui: date) -> dict:
    """Si la valeur manque mais qu'une valeur réelle est connue (exécution précédente),
    on la garde avec sa date, marquée « ancienne » — sauf si elle a elle-même plus de 6 mois
    (donnée mensuelle) : elle est alors trop ancienne pour être affichée."""
    if nouveau.get("valeur") is not None or not ancien or ancien.get("valeur") is None or not ancien.get("source"):
        return nouveau
    if ancien.get("frequence") in ("mensuelle", "quotidienne") and ancien.get("date") and \
            (aujourdhui - date_periode(ancien["date"])).days > 183:
        return nouveau
    garde = {k: v for k, v in ancien.items() if k not in ("precedent", "a_verifier", "raison_a_verifier", "confirmee", "confiance")}
    garde["ancienne"] = True
    garde["raison_ancienne"] = f"source indisponible le {aujourdhui.strftime('%d/%m/%Y')} ({nouveau.get('raison', 'erreur')}) : dernière valeur connue conservée"
    garde["verification"] = "ancienne"
    if "sources" in nouveau:  # on montre l'état des sources de ce jour
        garde["sources"] = nouveau["sources"]
    return garde


def verifier(cle: str, ind: dict, seuils: dict) -> None:
    """Valeur hors de la plage habituelle et non confirmée par une seconde source
    → « à vérifier » (donnée isolée inhabituelle)."""
    if ind.get("valeur") is None or cle not in seuils:
        return
    bas, haut = seuils[cle]
    if bas <= ind["valeur"] <= haut:
        return
    # Confirmation : une autre source valable, elle aussi hors de la plage habituelle
    autres = [s for s in ind.get("sources", []) if s["statut"] in ("concorde", "non comparable") and s.get("valeur") is not None]
    confirmation = next((s for s in autres if not bas <= s["valeur"] <= haut), None) if cle != "taux_reel" else None
    if confirmation or (cle == "taux_reel" and ind.get("verification") == "concordant"):
        nom = confirmation["nom"].split(",")[0] if confirmation else "sources concordantes"
        ind["confirmee"] = f"valeur inhabituelle mais confirmée par une seconde source ({nom})"
        return
    ind["a_verifier"] = True
    ind["raison_a_verifier"] = f"valeur inhabituelle (hors de l'intervalle {bas} à {haut}) : à vérifier avant d'en tirer une conclusion"


def confiance_indicateur(ind: dict) -> str | None:
    """Confiance dans un indicateur : élevé (sources concordantes), moyen (une seule source),
    faible (sources divergentes, valeur ancienne ou à vérifier)."""
    if ind.get("valeur") is None:
        return None
    if ind.get("ancienne") or ind.get("a_verifier") or ind.get("verification") == "divergent":
        return "faible"
    return "élevé" if ind.get("verification") == "concordant" else "moyen"


def tendance(nouveau: dict, ancien: dict | None) -> None:
    """Champ « precedent » : l'ancienne valeur et l'ancienne note, si elles ont changé
    (sinon on conserve le « precedent » déjà connu, pour garder la flèche)."""
    if not ancien or not ancien.get("source") or ancien.get("valeur") is None or nouveau.get("valeur") is None:
        return
    if ancien.get("valeur") != nouveau.get("valeur") or ancien.get("date") != nouveau.get("date"):
        nouveau["precedent"] = {"valeur": ancien["valeur"], "note": ancien.get("note"), "date": ancien.get("date")}
    elif ancien.get("precedent"):
        nouveau["precedent"] = ancien["precedent"]


def qualite(tentatives: list, seuil: float = 1 / 3) -> dict:
    """Contrôle de qualité d'un pays : une source est « en échec » si toutes ses tentatives
    ont échoué ou ont été rejetées. Alerte si plus d'un tiers des sources consultées sont en échec."""
    par_source = {}
    for t in tentatives:
        par_source.setdefault(t["source"], []).append(t)
    echecs = {s: l for s, l in par_source.items() if all(t["statut"] in ("échec", "rejetée") for t in l)}
    n = len(par_source)
    part = round(len(echecs) / n, 2) if n else 0.0
    details = sorted({f"{l[0]['nom'].split(',')[0]} : {l[0]['raison']}" for l in echecs.values()})
    return {"sources_consultees": n, "sources_en_echec": len(echecs), "part_en_echec": part, "alerte": n > 0 and part > seuil, "details": details}


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def executer(fournisseur, config: dict, ancien: dict | None, aujourdhui: date) -> tuple[list, dict, list]:
    """Renvoie (pays, états des sources, échecs et rejets)."""
    ancien_reel = bool(ancien) and ancien.get("meta", {}).get("fictif") is False
    anciens = {p["code"]: p for p in (ancien or {}).get("donnees", [])} if ancien_reel else {}
    src, etats = collecter(fournisseur, config, aujourdhui)

    par_pays, tentatives = {}, {}
    for code, cfg in config["pays"].items():
        par_pays[code], tentatives[code] = indicateurs_pays(code, cfg, src, aujourdhui, config)
    completer_valorisation(par_pays, aujourdhui)

    ponderations = config["ponderations"]
    sortie, textes_gemini, echecs = [], 0, []
    for code, cfg in config["pays"].items():
        a = anciens.get(code, {})
        anciens_ind = {**a.get("indicateurs", {}), **a.get("detail", {})}
        tous = {}
        for cle in PRINCIPAUX + DETAIL:
            ind = secours(cle, par_pays[code][cle], anciens_ind.get(cle), aujourdhui)
            ind["note"] = noter(cle, ind) if ind.get("valeur") is not None else None
            verifier(cle, ind, config["seuils_a_verifier"])
            if ind.get("valeur") is not None:
                ind["confiance"] = confiance_indicateur(ind)
            tendance(ind, anciens_ind.get(cle))
            tous[cle] = ind
        indicateurs = {k: tous[k] for k in PRINCIPAUX}
        detail = {k: tous[k] for k in DETAIL}

        globale = notation.note_globale(indicateurs, ponderations)
        conf = notation.confiance(indicateurs, ponderations, globale["couverture"])
        note = globale["note"]
        verdict = textes.verdict(cfg["nom"], note, indicateurs, PRINCIPAUX, globale["ramenee"], globale["brute"])
        contre = textes.contre_scenario(note, indicateurs, PRINCIPAUX, conf)
        origine_textes = "règles"
        redige = textes.rediger_avec_gemini(cfg["nom"], note, indicateurs, conf, config["gemini"]["modele"]) if note is not None else None
        if redige:
            verdict, contre, origine_textes = redige["verdict"], redige["contre_scenario"], "gemini"
            textes_gemini += 1
        for t in [verdict, *contre]:
            if not textes.ton_conforme(t):
                raise ValueError(f"Texte non conforme aux règles de conduite ({code}) : {t}")

        p = {
            "code": code, "iso_num": cfg["iso_num"], "nom": cfg["nom"], "lat": cfg["lat"], "lon": cfg["lon"],
            "note": note, "niveau": notation.niveau(note) if note is not None else None,
            "note_brute": globale["brute"], "note_ramenee_en_zone_neutre": globale["ramenee"],
            "verdict": verdict,
            "confiance": conf,
            "qualite": qualite(tentatives[code]),
            "contre_scenario": contre,
            "lecture": textes.lecture(indicateurs, detail),
            "textes": origine_textes,
            "indicateurs": indicateurs,
            "detail": detail,
        }
        if a.get("note") is not None and note is not None:
            if a["note"] != note:
                p["precedent"] = {"note": a["note"], "date": (ancien.get("meta", {}).get("genere_le") or "")[:10]}
            elif a.get("precedent"):
                p["precedent"] = a["precedent"]
        sortie.append(p)
        echecs += [{"pays": code, "indicateur": t["indicateur"], "source": t["nom"], "statut": t["statut"], "raison": t.get("raison"),
                    "date": t.get("date")}
                   for t in tentatives[code] if t["statut"] in ("échec", "rejetée")]

    etats["textes"] = f"Gemini pour {textes_gemini} pays" if textes_gemini else "règles (pas de clé GEMINI_API_KEY ou rédaction refusée)"
    return sortie, etats, echecs


def historiser(dossier: Path, donnees: list, jour: date, meta: dict) -> Path:
    """Notes du jour conservées dans data/historique/pays/AAAA-MM-JJ.json (pour mesurer plus tard la justesse)."""
    resume = [{
        "code": p["code"], "note": p["note"], "niveau": p["niveau"], "confiance": p["confiance"]["niveau"],
        "verdict": p["verdict"],
        "indicateurs": {k: {"valeur": v.get("valeur"), "note": v.get("note"), "date": v.get("date"), "verification": v.get("verification")}
                        for k, v in p["indicateurs"].items()},
    } for p in donnees]
    chemin = dossier / f"{jour.isoformat()}.json"
    ecrire_json(chemin, {"meta": {"genere_le": meta["genere_le"], "source": "agent-pays", "version_agent": VERSION_AGENT}, "donnees": resume})
    return chemin


def journaliser(chemin: Path, genere_le: str, etats: dict, echecs: list, donnees: list, maximum: int = 90) -> bool:
    """Journal des sources en échec : data/journal/agent-pays.json (90 dernières entrées).
    Une entrée n'est ajoutée que si son contenu diffère de la précédente (pas de commit inutile)."""
    entree = {
        "genere_le": genere_le,
        "etat_des_sources": etats,
        "sources_en_erreur": sorted(k for k, v in etats.items() if v.startswith("erreur")),
        "alertes_qualite": [p["code"] for p in donnees if p["qualite"]["alerte"]],
        "echecs_et_rejets": echecs,
    }
    journal_existant = lire_json(chemin) or {"meta": {}, "donnees": []}
    entrees = journal_existant.get("donnees", [])
    sans_date = lambda e: {k: v for k, v in e.items() if k != "genere_le"}
    if entrees and sans_date(entrees[-1]) == sans_date(entree):
        return False
    entrees = (entrees + [entree])[-maximum:]
    meta = {**journal_existant.get("meta", {}),  # conserve le bloc « sante »
            "genere_le": genere_le, "source": "agent-pays", "version_agent": VERSION_AGENT,
            "description": "Sources en échec et valeurs rejetées, à chaque exécution où elles changent"}
    ecrire_json(chemin, {**journal_existant, "meta": meta, "donnees": entrees})  # garde le premier niveau
    return True


def _date_dans_raison(raison: str | None) -> str | None:
    """« trop ancienne (donnée mensuelle de 2025-01, …) » → « 2025-01 » (anciennes entrées du journal)."""
    import re
    m = re.search(r"\b(\d{4}(?:-\d{2}){0,2})\b", raison or "")
    return m.group(1) if m else None


def sources_sante(etats: dict, echecs: list, journal_existant: dict | None) -> list[dict]:
    """État de chaque source pour l'écran « Santé des agents »."""
    historique = (journal_existant or {}).get("donnees", [])

    def dernier_ok(nom):
        for e in reversed(historique):
            if (e.get("etat_des_sources") or {}).get(nom) == "ok":
                return e.get("genere_le")
        return None

    res = []
    for nom, etat in etats.items():
        if nom == "textes":
            continue
        if etat == "ok":
            res.append({"nom": nom, "etat": "ok"})
        elif etat == "vide" or etat.startswith("partiel"):
            res.append({"nom": nom, "etat": "partielle", "detail": "aucune donnée reçue" if etat == "vide" else etat})
        elif "absente" in etat:  # clé d'API non fournie : source volontairement ignorée
            res.append({"nom": nom, "etat": "non configurée", "detail": etat.removeprefix("erreur : ")})
        else:
            res.append({"nom": nom, "etat": "échec", "derniere_donnee_valide": dernier_ok(nom),
                        "detail": etat.removeprefix("erreur : ")})
    # Sources qui répondent, mais dont la donnée est trop ancienne pour être retenue
    perimees = {}
    for e in echecs:
        if e.get("statut") == "rejetée" and str(e.get("raison", "")).startswith("trop ancienne"):
            p = perimees.setdefault(e["source"], {"nom": e["source"], "etat": "périmée", "dates": [], "pays": []})
            p["pays"].append(f"{e['pays']} ({e['indicateur']})")
            date_donnee = e.get("date") or _date_dans_raison(e.get("raison"))
            if date_donnee:
                p["dates"].append(str(date_donnee))
    for p in perimees.values():
        res.append({"nom": p["nom"], "etat": "périmée", "derniere_donnee_valide": max(p["dates"]) if p["dates"] else None,
                    "detail": "donnée trop ancienne pour " + ", ".join(sorted(set(p["pays"])))})
    return res


def indicateurs_sante(donnees: list) -> dict:
    """Pour chaque pays et indicateur : sources valides et sources prévues (règle « dégradé »)."""
    res = {}
    for p in donnees:
        blocs = {**p.get("indicateurs", {}), **p.get("detail", {})}
        for ind in blocs.values():
            sources = ind.get("sources") if isinstance(ind, dict) else None
            if not sources:
                continue
            res[f"{p['nom']} · {ind.get('libelle', '?')}"] = {
                "valides": [s["source"] for s in sources if s.get("statut") not in ("rejetée", "échec")],
                "configurees": [s["source"] for s in sources],
            }
    return res


def enregistrer_sante(chemin: Path, etats: dict, echecs: list, donnees: list) -> None:
    journal_existant = lire_json(chemin)
    precedent = ((journal_existant or {}).get("meta") or {}).get("sante")
    bloc = sante.bloc_sante("pays", "Agent pays", 1, "agent-pays.yml",
                            sources_sante(etats, echecs, journal_existant), datetime.now(timezone.utc), precedent,
                            indicateurs=indicateurs_sante(donnees))
    # Une exécution par jour : la date de dernière exécution est toujours enregistrée
    sante.enregistrer_sante(chemin, bloc, forcer=True)
    LOG.info("Santé : %d/%d sources répondent ; %s.", bloc["sources_ok"], bloc["sources_total"],
             "dégradé : " + " ; ".join(bloc["raisons"]) if bloc["degrade"] else "aucun indicateur dégradé")


def extraire_flux_fictifs(ancien: dict | None, chemin_flux: Path) -> None:
    """Les arcs de flux de capitaux restent fictifs : on les déplace dans data/flux.json
    (une seule fois), pour que data/pays.json ne contienne que des données réelles."""
    if chemin_flux.exists() or not ancien:
        return
    flux = [{"de": p["code"], **f} for p in ancien.get("donnees", []) for f in p.get("flux", [])]
    if flux:
        ecrire_json(chemin_flux, enveloppe(flux, "fictive", fictif=True, producteur_futur="agent-macro"))
        LOG.info("Flux de capitaux fictifs déplacés dans %s (%d arcs)", chemin_flux, len(flux))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Agent pays : met à jour data/pays.json avec des données réelles.")
    parser.add_argument("--test", action="store_true", help="utilise les données de test (agents/pays/tests/donnees), sans réseau")
    parser.add_argument("--donnees-test", default=str(DOSSIER_AGENT / "tests" / "donnees"))
    parser.add_argument("--sortie", default=str(RACINE / "data" / "pays.json"))
    parser.add_argument("--historique", default=str(RACINE / "data" / "historique" / "pays"))
    parser.add_argument("--flux", default=str(RACINE / "data" / "flux.json"))
    parser.add_argument("--journal", default=str(RACINE / "data" / "journal" / "agent-pays.json"))
    parser.add_argument("--recap", default=str(RACINE / "data" / "recap"))
    parser.add_argument("--date", help="date du jour (AAAA-MM-JJ), utile pour les tests")
    args = parser.parse_args(argv)

    config = json.loads((DOSSIER_AGENT / "config.json").read_text(encoding="utf-8"))
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    sortie = Path(args.sortie)
    ancien = lire_json(sortie)
    extraire_flux_fictifs(ancien, Path(args.flux))

    fournisseur = FournisseurTest(Path(args.donnees_test)) if args.test else FournisseurReel(RACINE / "agents" / ".cache")
    LOG.info("Agent pays %s — %s — %d pays", VERSION_AGENT, "données de test" if args.test else "sources réelles", len(config["pays"]))
    donnees, etats, echecs = executer(fournisseur, config, ancien, aujourdhui)
    ancien_reel = ancien if ancien and ancien.get("meta", {}).get("fictif") is False else None

    # Pas d'écriture si rien n'a changé (donc pas de commit)
    if ancien_reel and ancien_reel.get("donnees") == donnees:
        if journaliser(Path(args.journal), maintenant_iso(), etats, echecs, donnees):
            LOG.info("Données inchangées ; journal des sources mis à jour (état des sources différent).")
        else:
            LOG.info("Aucun changement dans les données depuis la dernière exécution.")
        enregistrer_sante(Path(args.journal), etats, echecs, donnees)
        return 0

    meta_ancienne = (ancien or {}).get("meta", {})
    objet = enveloppe(
        donnees, "agent-pays", fictif=False,
        mise_a_jour_precedente=meta_ancienne.get("genere_le") if meta_ancienne.get("fictif") is False else None,
        version_agent=VERSION_AGENT,
        sources=sources_publiees(config),
        hierarchie_des_sources=[LIBELLES_NIVEAUX[n] for n in ("nationale", "internationale", "marche")],
        etat_des_sources=etats,
        ponderations=config["ponderations"],
        alertes_qualite=[p["code"] for p in donnees if p["qualite"]["alerte"]],
    )
    ecrire_json(sortie, objet)
    chemin = historiser(Path(args.historique), donnees, aujourdhui, objet["meta"])
    journaliser(Path(args.journal), objet["meta"]["genere_le"], etats, echecs, donnees)
    enregistrer_sante(Path(args.journal), etats, echecs, donnees)
    chemin_recap = recap.ecrire(Path(args.recap), aujourdhui, objet, ancien_reel, etats)
    notes = sorted(((p["note"] or 0, p["nom"]) for p in donnees), reverse=True)
    LOG.info("Écrit : %s, %s et %s", sortie, chemin, chemin_recap)
    LOG.info("Notes : %s", ", ".join(f"{n} {s}" for s, n in notes))
    erreurs = [k for k, v in etats.items() if v.startswith("erreur")]
    if erreurs:
        LOG.warning("Sources en erreur : %s (dernières valeurs connues conservées)", ", ".join(erreurs))
    return 0


def sources_publiees(config: dict) -> dict:
    """Liste des sources par niveau de la hiérarchie (affichée dans meta)."""
    nationales = sorted({s["nom"] for k, l in config["sources_nationales"].items() if not k.startswith("_") for s in l})
    return {
        LIBELLES_NIVEAUX["nationale"]: nationales + ["BCE (taux de la facilité de dépôt, pour la zone euro)"],
        LIBELLES_NIVEAUX["internationale"]: ["FMI (DataMapper)", "OCDE (SDMX : CLI, prix, Perspectives économiques)", "BRI (WS_CBPOL)",
                                             "Banque mondiale (API v2)", "Eurostat (IPCH)", "BCE (cours de référence de l'euro)"],
        LIBELLES_NIVEAUX["marche"]: ["Yahoo Finance (yfinance)"],
    }
