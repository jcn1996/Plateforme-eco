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

Flux d'investissement des ETF pays (indicateur « Flux étrangers », voir flux_etf.py) : relevé quotidien
des parts en circulation et de la VL chez l'émetteur (Yahoo Finance en secours), historique jour par
jour dans data/historique/flux_etf/, signaux dans data/signaux/pays.json. Le mode « flux » (lancé en
soirée, heure de New York, après la publication des émetteurs) ne met à jour que cet indicateur.

Lancement : python -m agents.pays                (vraies sources, tous les indicateurs)
            python -m agents.pays --mode flux    (flux des ETF pays seulement)
            python -m agents.pays --test         (données de test, sans réseau)
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from ..commun import sante
from ..commun.journal import journal
from ..commun.series import serie_graphique
from ..commun.sortie import ecrire_json, enveloppe, lire_json, maintenant_iso
from . import croisement, flux_etf, notation, recap, textes
from .croisement import LIBELLES_NIVEAUX, date_periode
from .sources import SOURCES, FournisseurReel, FournisseurTest

LOG = journal("agent-pays")
RACINE = Path(__file__).resolve().parents[2]
DOSSIER_AGENT = Path(__file__).resolve().parent
VERSION_AGENT = "1.2"
CONFIG_FLUX: dict = json.loads((DOSSIER_AGENT / "config.json").read_text(encoding="utf-8"))["flux_etf"]
# Indice boursier national de référence de chaque pays (momentum 12 mois, graphique de la fiche pays)
FICHIER_INDICES = RACINE / "config" / "indices_pays.json"
FICHIER_INDICES_TEST = Path(__file__).resolve().parent / "tests" / "indices_pays.json"
MENTION_ETF = "indice indisponible, ETF affiché"

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
    "activite_reelle": "Activité réelle",
}
PRINCIPAUX = ["croissance_pib", "indicateur_avance", "inflation", "taux_reel", "valorisation", "momentum"]
DETAIL = ["devise_3m", "solde_courant", "flux_etrangers"]
# Indicateurs facultatifs : comptés dans la note quand ils existent (pondération en config), sans pénaliser
# la couverture ni la confiance quand ils manquent. « Activité réelle » : score de l'agent données alternatives.
FACULTATIFS = ["activite_reelle"]
AGE_MAX_ALTERNATIVES_JOURS = 4

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
    indices, changes_eur = symboles_indices(config)
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
        "yahoo_cours": lambda: fournisseur.cours(sorted(set(etfs + devises + indices + changes_eur))),
        "yahoo_per": lambda: fournisseur.per(etfs),
        **appels_flux(fournisseur, config),
    }
    for nom, serie in BM_SERIES.items():
        appels[nom] = (lambda s: lambda: fournisseur.banque_mondiale(s, aujourdhui.year))(serie)
    for code, liste in config["sources_nationales"].items():
        if code.startswith("_"):
            continue
        for s in liste:
            appels.setdefault(_cle_nationale(s), (lambda s: lambda: getattr(fournisseur, s["fournisseur"])(
                *((s["serie"],) if s["fournisseur"] == "dbnomics" else (s["serie"], depuis))))(s))

    return interroger(appels, {"yahoo_per": len(etfs), "yahoo_cours": len(set(etfs + devises + indices + changes_eur)),
                               **attendus_flux(config)})


def symboles_indices(config: dict) -> tuple[list[str], list[str]]:
    """Symboles Yahoo des indices nationaux, et cours de l'euro dans chaque monnaie (EURJPY=X…) pour la
    performance convertie en euros (USD compris : l'ETF pays de secours est coté en dollars)."""
    indices = config.get("indices") or {}
    symboles = sorted({i["yahoo"] for i in indices.values() if i.get("yahoo")})
    monnaies = {i["monnaie"] for i in indices.values() if i.get("monnaie")} | {"USD"}
    return symboles, sorted(f"EUR{m}=X" for m in monnaies if m != "EUR")


def appels_flux(fournisseur, config: dict) -> dict:
    """Sources des flux des ETF pays : une par émetteur (tous ses fonds en une fois), plus Yahoo Finance."""
    emetteurs = config["flux_etf"]["emetteurs"]
    suivis = {p["etf"] for p in config["pays"].values() if p.get("etf")}
    appels = {}
    for nom in sorted({e["emetteur"] for e in emetteurs.values()}):
        fonds = {etf: e for etf, e in emetteurs.items() if e["emetteur"] == nom and etf in suivis}
        if fonds:
            appels[f"flux_{nom}"] = (lambda n, f: lambda: fournisseur.emetteur(n, f))(nom, fonds)
    appels["flux_yahoo_parts"] = lambda: fournisseur.yahoo_parts(sorted(suivis))
    return appels


def attendus_flux(config: dict) -> dict:
    emetteurs = config["flux_etf"]["emetteurs"]
    suivis = {p["etf"] for p in config["pays"].values() if p.get("etf")}
    res = {"flux_yahoo_parts": len(suivis)}
    for etf in suivis:
        if etf in emetteurs:
            cle = f"flux_{emetteurs[etf]['emetteur']}"
            res[cle] = res.get(cle, 0) + 1
    return res


def interroger(appels: dict, attendus_par_source: dict) -> tuple[dict, dict]:
    """Lance chaque appel ; une source en panne vaut None (les autres continuent)."""
    resultats, etats = {}, {}
    for nom, appel in appels.items():
        try:
            resultats[nom] = appel()
            vide = not resultats[nom]
            etats[nom] = "vide" if vide else "ok"
            attendus = attendus_par_source.get(nom)
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


def etat_indice(serie, aujourdhui: date, fraicheur_jours: int = 10) -> tuple[tuple | None, str | None]:
    """((date, performance 12 mois en %), None) si l'historique de l'indice est utilisable, sinon (None, raison)."""
    if not serie:
        return None, "aucun cours publié par Yahoo Finance"
    if date_periode(serie[-1][0]) < aujourdhui - timedelta(days=fraicheur_jours):
        return None, f"cours arrêtés au {serie[-1][0]} chez Yahoo Finance"
    r = _variation_quotidienne(serie, 365)
    return (r, None) if r else (None, "moins de 12 mois d'historique chez Yahoo Finance")


def performance_euros(serie, monnaie: str, cours: dict, jours: int = 365, ecart_max: int = 7) -> float | None:
    """Performance sur `jours` jours convertie en euros : (P1 / E1) / (P0 / E0) − 1, E = cours de l'euro
    dans la monnaie de cotation (EURJPY=X : yens pour 1 euro), pris à la date de chaque clôture."""
    fin_d, fin = serie[-1]
    debut = _valeur_a_date(serie, date_periode(fin_d) - timedelta(days=jours))
    if not debut:
        return None
    if monnaie == "EUR":
        return (fin / debut[1] - 1) * 100
    change = (cours or {}).get(f"EUR{monnaie}=X")
    if not change:
        return None
    e1, e0 = _valeur_a_date(change, date_periode(fin_d)), _valeur_a_date(change, date_periode(debut[0]))
    if not e1 or not e0 or (date_periode(fin_d) - date_periode(e1[0])).days > ecart_max \
            or (date_periode(debut[0]) - date_periode(e0[0])).days > ecart_max:
        return None
    return ((fin / e1[1]) / (debut[1] / e0[1]) - 1) * 100


def _candidat_momentum(serie, r, nom, symbole, monnaie, cours, **extra) -> dict:
    eur = performance_euros(serie, monnaie, cours)
    return _cand("yahoo_cours", nom, "marche", r[1], r[0], "quotidienne", symbole=symbole, monnaie=monnaie,
                 performance_eur=round(eur, 2) if eur is not None else None,
                 effet_change=round(eur - r[1], 2) if eur is not None else None, **extra)


def candidats_momentum(cfg: dict, indice: dict | None, cours: dict | None, aujourdhui: date) -> list[dict]:
    """Momentum 12 mois : l'indice national en monnaie locale ; à défaut, l'ETF pays (en dollars),
    avec la mention « indice indisponible, ETF affiché »."""
    etf = cfg.get("etf")
    raison_indice = None
    if indice:
        if not indice.get("yahoo"):
            raison_indice = "indice non publié par Yahoo Finance"
        elif cours is not None:
            r, raison_indice = etat_indice(cours.get(indice["yahoo"]), aujourdhui)
            if r:
                nom = SOURCES["yahoo_indice"].format(indice=indice["nom"], symbole=indice["yahoo"], monnaie=indice["monnaie"])
                return [_candidat_momentum(cours[indice["yahoo"]], r, nom, indice["yahoo"], indice["monnaie"], cours,
                                           base="indice", indice=indice["nom"])]
    if not etf:
        return []
    extra = {"base": "etf"}
    if indice:
        extra.update(indice=indice["nom"], mention=MENTION_ETF, raison_indice=raison_indice or "source indisponible")
    nom = SOURCES["yahoo_prix"].format(symbole=etf)
    if cours is None:
        return [_echec("yahoo_cours", nom, "marche", "source indisponible lors de cette exécution")]
    if not cours.get(etf):
        return [_echec("yahoo_cours", nom, "marche", f"aucun cours pour {etf}")]
    r = _variation_quotidienne(cours[etf], 365)
    if not r:
        return [_echec("yahoo_cours", nom, "marche", "moins de 12 mois de cours")]
    return [_candidat_momentum(cours[etf], r, nom, etf, "USD", cours, **extra)]


def candidats_marche(cfg: dict, src: dict, config: dict, code: str | None = None, aujourdhui: date | None = None) -> dict:
    """Candidats des indicateurs de marché : Yahoo Finance, et la BCE pour les devises."""
    c = {"momentum": [], "devise_3m": [], "per": []}
    etf, devise = cfg.get("etf"), cfg.get("devise")
    cours, pers = src.get("yahoo_cours"), src.get("yahoo_per")
    indice = (config.get("indices") or {}).get(code) if code else None
    c["momentum"] = candidats_momentum(cfg, indice, cours, aujourdhui or date.today())

    if etf:
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
    cands = {**candidats_pays(code, cfg, src, config, aujourdhui), **candidats_marche(cfg, src, config, code, aujourdhui)}
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
                r = ch["retenu"]
                extra.update({k: r[k] for k in ("symbole", "base", "indice", "monnaie", "performance_eur", "effet_change",
                                                 "mention", "raison_indice") if r.get(k) is not None})
                if r.get("performance_eur") is not None and r.get("monnaie") != "EUR":
                    extra["source_change"] = SOURCES["yahoo_change"].format(symbole=f"EUR{r['monnaie']}=X")
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
    sortie["flux_etrangers"] = _absent("flux_etrangers", "calculé ensuite (flux des ETF pays)")
    return sortie, tentatives


def _raison_absence(choix: dict, cle: str, cfg: dict) -> str:
    if not choix["sources"]:
        return {"indicateur_avance": "non publié par l'OCDE pour ce pays", "momentum": "indice national sans historique chez Yahoo Finance et aucun ETF pays coté",
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
            "mention_source": f"calculée via l'ETF {v['_etf']} (le PER des indices n'est pas disponible gratuitement)",
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
    if cle == "flux_etrangers":
        return flux_etf.noter(ind, CONFIG_FLUX)
    if cle == "activite_reelle":
        return notation.note_activite_reelle(v)
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

def calculer_flux(src: dict, config: dict, historique: dict, aujourdhui: date) -> tuple[dict, set, list, list]:
    """Flux des ETF pays. Complète `historique` avec les relevés du jour.
    Renvoie ({code: indicateur flux_etrangers}, dates modifiées, signaux, échecs et rejets)."""
    cfg = config["flux_etf"]
    resultats, modifiees, nouveaux, echecs = {}, set(), [], []
    for code, p in config["pays"].items():
        etf = p.get("etf")
        emetteur = (cfg["emetteurs"].get(etf) or {}).get("emetteur") if etf else None
        choix = flux_etf.choisir_releve(etf, emetteur, src, cfg, aujourdhui) if emetteur else None
        if choix and choix["retenu"]:
            modifiees |= set(flux_etf.completer_historique(historique, etf, choix["retenu"], choix["verification"],
                                                           cfg["remplissage_jours"], aujourdhui))
        serie = historique.get(etf, []) if etf else []
        resultats[code] = flux_etf.indicateur(etf, emetteur, choix, serie, cfg, aujourdhui)
        if etf and serie:
            nouveaux += flux_etf.signaux(code, p["nom"], etf, serie, cfg, aujourdhui)
        echecs += [{"pays": code, "indicateur": "flux_etrangers", "source": s["nom"], "statut": s["statut"], "raison": s.get("raison"),
                    "date": s.get("date")} for s in (choix or {}).get("sources", []) if s["statut"] in ("échec", "rejetée")]
    return resultats, modifiees, nouveaux, echecs


def lire_alternatives(chemin: Path, aujourdhui: date) -> dict:
    """Scores d'activité réelle par pays (data/donnees_alternatives.json), s'ils sont récents."""
    objet = lire_json(chemin) or {}
    d = objet.get("donnees") or {}
    if (objet.get("meta") or {}).get("fictif") is not False or not d.get("date"):
        return {}
    if (aujourdhui - date.fromisoformat(d["date"])).days > AGE_MAX_ALTERNATIVES_JOURS:
        LOG.warning("Données alternatives du %s : trop anciennes, sous-note « Activité réelle » non utilisée.", d["date"])
        return {}
    index = {i["cle"]: i for i in d.get("indicateurs") or []}
    return {p["code"]: {**p, "_date": d["date"], "_indicateurs": [index[k] for k in p.get("indicateurs", []) if k in index]}
            for p in d.get("pays") or [] if p.get("score") is not None}


def indicateur_activite(alt: dict | None) -> dict | None:
    """Sous-note « Activité réelle » : score /100 de l'agent données alternatives (au moins 2 indicateurs)."""
    if not alt:
        return None
    utilises = [i for i in alt["_indicateurs"] if i.get("note") is not None and not i.get("perimee")]
    noms = ", ".join(sorted({i["nom"].lower() for i in utilises}))
    return {"libelle": LIBELLES["activite_reelle"], "valeur": round(alt["score"], 1), "unite": "/100", "date": alt["_date"],
            "source": f"agent données alternatives ({noms})", "source_courte": "les données alternatives", "niveau_source": "alternative",
            "frequence": "quotidienne", "verification": "concordant" if alt.get("indicateurs_utilises", 0) >= 3 else "source_unique",
            "ecart_max": None, "lecture": alt.get("lecture"), "indicateurs_utilises": alt.get("indicateurs_utilises"),
            "confiance_alternative": (alt.get("confiance") or {}).get("niveau"),
            "divergence": (alt.get("divergence") or {}).get("texte"),
            "affichage": f"{round(alt['score'])}/100 · {alt.get('lecture')}",
            "complement": f"{alt.get('indicateurs_utilises')} indicateurs alternatifs ({noms})"}


def preparer(cle: str, nouveau: dict, ancien: dict | None, aujourdhui: date, config: dict) -> dict:
    """Secours, note, contrôle « à vérifier », confiance et tendance d'un indicateur."""
    ind = secours(cle, nouveau, ancien, aujourdhui)
    ind["note"] = noter(cle, ind) if ind.get("valeur") is not None else None
    verifier(cle, ind, config["seuils_a_verifier"])
    if ind.get("valeur") is not None:
        ind["confiance"] = confiance_indicateur(ind)
    tendance(ind, ancien)
    return ind


def executer(fournisseur, config: dict, ancien: dict | None, aujourdhui: date, series: dict | None = None,
             flux: dict | None = None, series_indices: dict | None = None, alternatives: dict | None = None) -> tuple[list, dict, list]:
    """Renvoie (pays, états des sources, échecs et rejets). Si `series` est fourni, il reçoit les clôtures
    quotidiennes sur un an des ETF pays (graphique de secours de l'appli). `flux` : {"historique": {...}}
    (relevés passés des ETF) ; il reçoit aussi les dates modifiées et les signaux du jour. `series_indices` reçoit
    les clôtures des indices nationaux utilisables (graphique simple de la fiche pays)."""
    flux = flux if flux is not None else {"historique": {}}
    ancien_reel = bool(ancien) and ancien.get("meta", {}).get("fictif") is False
    anciens = {p["code"]: p for p in (ancien or {}).get("donnees", [])} if ancien_reel else {}
    src, etats = collecter(fournisseur, config, aujourdhui)
    if series is not None:
        etfs = {cfg["etf"] for cfg in config["pays"].values() if cfg.get("etf")}
        series.update({s: serie_graphique(v) for s, v in (src.get("yahoo_cours") or {}).items() if s in etfs and v})
    if series_indices is not None:
        indices = set(symboles_indices(config)[0])
        # Seules les séries utilisables (au moins 12 mois, cours récents) servent au graphique simple
        series_indices.update({s: serie_graphique(v) for s, v in (src.get("yahoo_cours") or {}).items()
                               if s in indices and etat_indice(v, aujourdhui)[0]})

    par_pays, tentatives = {}, {}
    for code, cfg in config["pays"].items():
        par_pays[code], tentatives[code] = indicateurs_pays(code, cfg, src, aujourdhui, config)
    completer_valorisation(par_pays, aujourdhui)
    resultats_flux, flux["modifiees"], flux["signaux"], echecs_flux = calculer_flux(src, config, flux["historique"], aujourdhui)
    for code, ind in resultats_flux.items():
        par_pays[code]["flux_etrangers"] = ind

    ponderations = config["ponderations"]
    sortie, textes_gemini, echecs = [], 0, []
    for code, cfg in config["pays"].items():
        a = anciens.get(code, {})
        anciens_ind = {**a.get("indicateurs", {}), **a.get("detail", {})}
        tous = {cle: preparer(cle, par_pays[code][cle], anciens_ind.get(cle), aujourdhui, config) for cle in PRINCIPAUX + DETAIL}
        indicateurs = {k: tous[k] for k in PRINCIPAUX}
        detail = {k: tous[k] for k in DETAIL}
        activite = indicateur_activite((alternatives or {}).get(code))
        if activite:
            indicateurs["activite_reelle"] = preparer("activite_reelle", activite, anciens_ind.get("activite_reelle"), aujourdhui, config)
        cles = PRINCIPAUX + [k for k in FACULTATIFS if k in indicateurs]

        globale = notation.note_globale(indicateurs, ponderations, FACULTATIFS)
        conf = notation.confiance(indicateurs, ponderations, globale["couverture"])
        note = globale["note"]
        verdict = textes.verdict(cfg["nom"], note, indicateurs, cles, globale["ramenee"], globale["brute"])
        contre = textes.contre_scenario(note, indicateurs, cles, conf)
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
            "etf": cfg.get("etf"),  # ETF pays : flux d'investissement et valorisation (plus affiché comme référence)
            "indice": indice_publie(config, code, indicateurs["momentum"]),
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

    echecs += echecs_flux
    etats["textes"] = f"Gemini pour {textes_gemini} pays" if textes_gemini else "règles (pas de clé GEMINI_API_KEY ou rédaction refusée)"
    return sortie, etats, echecs


def indice_publie(config: dict, code: str, momentum: dict) -> dict | None:
    """Indice national de la fiche pays : nom, symbole Yahoo, monnaie, et s'il a servi au momentum du jour."""
    i = (config.get("indices") or {}).get(code)
    if not i:
        return None
    utilise = momentum.get("base") == "indice" and not momentum.get("ancienne")
    sortie = {"nom": i["nom"], "yahoo": i.get("yahoo"), "monnaie": i.get("monnaie"), "historique": utilise}
    if not utilise:
        sortie["raison"] = momentum.get("raison_indice") or ("indice non publié par Yahoo Finance" if not i.get("yahoo") else
                                                              "historique de l'indice indisponible")
    return sortie


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


def executer_flux(fournisseur, config: dict, ancien: dict, aujourdhui: date, flux: dict) -> tuple[list, dict, list]:
    """Mode « flux » : seul l'indicateur « Flux étrangers » est recalculé ; le reste de data/pays.json est repris tel quel.
    Renvoie (pays, états des sources du jour, échecs et rejets du jour)."""
    src, etats = interroger(appels_flux(fournisseur, config), attendus_flux(config))
    resultats, flux["modifiees"], flux["signaux"], echecs = calculer_flux(src, config, flux["historique"], aujourdhui)
    sortie = []
    for p in json.loads(json.dumps(ancien.get("donnees", []))):  # copie profonde
        if p["code"] in resultats:
            p.setdefault("detail", {})
            p["detail"]["flux_etrangers"] = preparer("flux_etrangers", resultats[p["code"]], p["detail"].get("flux_etrangers"), aujourdhui, config)
            p["lecture"] = textes.lecture(p.get("indicateurs", {}), p["detail"])
            for t in p["lecture"].values():
                if not textes.ton_conforme(t):
                    raise ValueError(f"Texte non conforme aux règles de conduite ({p['code']}) : {t}")
        sortie.append(p)
    return sortie, etats, echecs


def ecrire_flux(args, flux: dict, aujourdhui: date, genere_le: str) -> None:
    """Historique jour par jour des relevés et signaux pour le chef d'orchestre."""
    ecrits = flux_etf.ecrire_historique(Path(args.historique_flux), flux["historique"], flux.get("modifiees") or set(),
                                        genere_le, VERSION_AGENT)
    if ecrits:
        LOG.info("Historique des flux ETF : %d fichier(s) écrit(s) dans %s", len(ecrits), args.historique_flux)
    for s in flux.get("signaux") or []:
        if not textes.ton_conforme(s["titre"] + " " + s["explication"]):
            raise ValueError(f"Signal non conforme aux règles de conduite : {s['titre']}")
    if flux_etf.ecrire_signaux(Path(args.signaux), flux.get("signaux") or [], aujourdhui, VERSION_AGENT):
        LOG.info("Signaux : %s (%d nouveau(x) candidat(s) du jour)", args.signaux, len(flux.get("signaux") or []))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Agent pays : met à jour data/pays.json avec des données réelles.")
    parser.add_argument("--mode", choices=["complet", "flux"], default="complet",
                        help="complet : tous les indicateurs ; flux : flux des ETF pays seulement (soirée, heure de New York)")
    parser.add_argument("--test", action="store_true", help="utilise les données de test (agents/pays/tests/donnees), sans réseau")
    parser.add_argument("--donnees-test", default=str(DOSSIER_AGENT / "tests" / "donnees"))
    parser.add_argument("--sortie", default=str(RACINE / "data" / "pays.json"))
    parser.add_argument("--historique", default=str(RACINE / "data" / "historique" / "pays"))
    parser.add_argument("--historique-flux", help="relevés quotidiens des ETF pays (défaut : flux_etf/ à côté de --historique)")
    parser.add_argument("--signaux", help="signaux pour le chef d'orchestre (défaut : signaux/pays.json à côté de --sortie)")
    parser.add_argument("--journal", default=str(RACINE / "data" / "journal" / "agent-pays.json"))
    parser.add_argument("--recap", default=str(RACINE / "data" / "recap"))
    parser.add_argument("--cours", help="clôtures des ETF pays pour les graphiques (défaut : cours/etf-pays.json à côté de --sortie)")
    parser.add_argument("--indices", help="indices nationaux de référence (défaut : config/indices_pays.json ; "
                                          "avec --test : copie de test agents/pays/tests/indices_pays.json)")
    parser.add_argument("--alternatives", help="scores d'activité réelle (défaut : donnees_alternatives.json à côté de --sortie)")
    parser.add_argument("--date", help="date du jour (AAAA-MM-JJ), utile pour les tests")
    args = parser.parse_args(argv)
    # Les chemins dérivés suivent --sortie et --historique : un essai dans un dossier temporaire n'écrit rien dans data/
    args.historique_flux = args.historique_flux or str(Path(args.historique).parent / "flux_etf")
    # Mode test : jamais le vrai config/ (il change avec la production) ; copie de test isolée
    args.indices = args.indices or str(FICHIER_INDICES_TEST if args.test else FICHIER_INDICES)
    args.signaux = args.signaux or str(Path(args.sortie).parent / "signaux" / "pays.json")

    config = json.loads((DOSSIER_AGENT / "config.json").read_text(encoding="utf-8"))
    config["indices"] = lire_indices(Path(args.indices))
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    sortie = Path(args.sortie)
    ancien = lire_json(sortie)
    ancien_reel = ancien if ancien and ancien.get("meta", {}).get("fictif") is False else None
    flux = {"historique": flux_etf.lire_historique(Path(args.historique_flux), aujourdhui, config["flux_etf"]["conservation_jours"])}

    fournisseur = FournisseurTest(Path(args.donnees_test)) if args.test else FournisseurReel(RACINE / "agents" / ".cache")
    if args.mode == "flux":
        if not ancien_reel:
            LOG.warning("Mode flux : pas encore de data/pays.json réel, exécution complète à la place.")
        else:
            return main_flux(args, fournisseur, config, ancien_reel, aujourdhui, flux)
    LOG.info("Agent pays %s — %s — %d pays", VERSION_AGENT, "données de test" if args.test else "sources réelles", len(config["pays"]))
    series, series_indices = {}, {}
    alternatives = lire_alternatives(Path(args.alternatives) if args.alternatives else sortie.parent / "donnees_alternatives.json", aujourdhui)
    donnees, etats, echecs = executer(fournisseur, config, ancien, aujourdhui, series, flux, series_indices, alternatives)
    dossier_cours = Path(args.cours).parent if args.cours else Path(args.sortie).parent / "cours"
    enregistrer_series(Path(args.cours) if args.cours else dossier_cours / "etf-pays.json", series)
    enregistrer_series(dossier_cours / "indices-pays.json", series_indices,
                       "Clôtures quotidiennes sur un an des indices nationaux (graphique simple de la fiche pays)")
    ecrire_flux(args, flux, aujourdhui, maintenant_iso())

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
        flux_etf_mis_a_jour_le=maintenant_iso(),
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


def main_flux(args, fournisseur, config: dict, ancien: dict, aujourdhui: date, flux: dict) -> int:
    """Mode « flux » : met à jour l'indicateur « Flux étrangers », l'historique des relevés et les signaux.
    Les états des autres sources (exécution complète du matin) sont conservés dans meta et dans le journal."""
    LOG.info("Agent pays %s — mode flux — %s", VERSION_AGENT, "données de test" if args.test else "sources réelles")
    donnees, etats_flux, echecs_flux = executer_flux(fournisseur, config, ancien, aujourdhui, flux)
    genere_le = maintenant_iso()
    ecrire_flux(args, flux, aujourdhui, genere_le)
    meta = ancien.get("meta", {})
    etats = {**{k: v for k, v in (meta.get("etat_des_sources") or {}).items() if not k.startswith("flux_")}, **etats_flux}
    journal_existant = lire_json(Path(args.journal)) or {}
    derniers = (journal_existant.get("donnees") or [{}])[-1].get("echecs_et_rejets") or []
    echecs = [e for e in derniers if e.get("indicateur") != "flux_etrangers"] + echecs_flux
    if donnees != ancien.get("donnees"):
        ecrire_json(Path(args.sortie), {**ancien, "meta": {**meta, "etat_des_sources": etats, "flux_etf_mis_a_jour_le": genere_le},
                                        "donnees": donnees})
        LOG.info("Flux étrangers mis à jour dans %s", args.sortie)
    else:
        LOG.info("Flux étrangers inchangés.")
    journaliser(Path(args.journal), genere_le, etats, echecs, donnees)
    enregistrer_sante(Path(args.journal), etats, echecs, donnees)
    return 0


def enregistrer_series(chemin: Path, series: dict,
                       description: str = "Clôtures quotidiennes sur un an des ETF pays (graphiques de secours de l'appli)") -> bool:
    """Clôtures quotidiennes sur un an (graphique de secours de l'appli, lu à la demande).
    Un symbole sans nouvelle série garde l'ancienne ; pas de réécriture si rien n'a changé."""
    ancien = (lire_json(chemin) or {}).get("donnees") or {}
    nouveau = {**ancien, **series}
    if not series or nouveau == ancien:
        return False
    ecrire_json(chemin, enveloppe(nouveau, "Yahoo Finance", fictif=False, producteur="agent-pays", description=description), compact=True)
    LOG.info("Séries écrites : %s (%d)", chemin, len(series))
    return True


def lire_indices(chemin: Path) -> dict:
    """Indices nationaux de référence par pays (fichier de configuration modifiable)."""
    contenu = lire_json(chemin) or {}
    return {code: i for code, i in (contenu.get("pays") or {}).items() if not code.startswith("_")}


def sources_publiees(config: dict) -> dict:
    """Liste des sources par niveau de la hiérarchie (affichée dans meta)."""
    nationales = sorted({s["nom"] for k, l in config["sources_nationales"].items() if not k.startswith("_") for s in l})
    return {
        LIBELLES_NIVEAUX["nationale"]: nationales + ["BCE (taux de la facilité de dépôt, pour la zone euro)"],
        LIBELLES_NIVEAUX["internationale"]: ["FMI (DataMapper)", "OCDE (SDMX : CLI, prix, Perspectives économiques)", "BRI (WS_CBPOL)",
                                             "Banque mondiale (API v2)", "Eurostat (IPCH)", "BCE (cours de référence de l'euro)"],
        LIBELLES_NIVEAUX["marche"]: ["Yahoo Finance (yfinance) : indices nationaux (momentum), ETF pays (valorisation), changes",
                                     "Émetteurs des ETF pays : iShares, SSGA, VanEck, Global X (parts en circulation et VL, flux des ETF)"],
    }
