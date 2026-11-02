"""
Agent pays : remplace les données fictives de data/pays.json par de vraies données gratuites.

Déroulé :
1. lit l'ancien data/pays.json (pour les champs « precedent » et les valeurs de secours) ;
2. interroge les sources (FMI, OCDE, BIS, Yahoo Finance) — une source en panne ne bloque pas l'agent ;
3. calcule les indicateurs, leurs notes /100, la note globale et le niveau de confiance ;
4. rédige verdict, lecture et « Ce qui pourrait me donner tort » (règles, ou Gemini si une clé est fournie) ;
5. écrit data/pays.json et data/historique/pays/AAAA-MM-JJ.json, seulement si quelque chose a changé.

Lancement : python -m agents.pays            (vraies sources)
            python -m agents.pays --test     (données de test, sans réseau)
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from . import notation, textes
from .sources import SOURCES, FournisseurReel, FournisseurTest

LOG = journal("agent-pays")
RACINE = Path(__file__).resolve().parents[2]
DOSSIER_AGENT = Path(__file__).resolve().parent
VERSION_AGENT = "1.0"

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


# ---------------------------------------------------------------------------
# Petits outils
# ---------------------------------------------------------------------------

def _indicateur(cle, valeur, unite, date_valeur, source, **extra) -> dict:
    return {"libelle": LIBELLES[cle], "valeur": round(valeur, 2), "unite": unite, "date": date_valeur, "source": source, **extra}


def _absent(cle, raison) -> dict:
    return {"libelle": LIBELLES[cle], "valeur": None, "unite": "", "note": None, "disponible": False, "raison": raison}


def _date_periode(periode: str) -> date:
    """'2026-09' → 30/09 approx. ; '2026-09-15' → date ; '2026' → 31/12."""
    morceaux = [int(x) for x in periode.split("-")]
    if len(morceaux) == 1:
        return date(morceaux[0], 12, 31)
    if len(morceaux) == 2:
        return date(morceaux[0], morceaux[1], 28)
    return date(*morceaux)


def _valeur_a_date(serie: list[tuple[str, float]], limite: date):
    """Dernière observation à la date limite ou avant."""
    candidates = [(d, v) for d, v in serie if _date_periode(d) <= limite]
    return candidates[-1] if candidates else None


def _recente(periode: str, aujourdhui: date, max_jours: int) -> bool:
    return (aujourdhui - _date_periode(periode)).days <= max_jours


# ---------------------------------------------------------------------------
# Collecte des sources (chaque source peut échouer sans faire tomber l'agent)
# ---------------------------------------------------------------------------

def collecter(fournisseur, config: dict, aujourdhui: date) -> tuple[dict, dict]:
    pays = config["pays"]
    iso3 = sorted({p["iso3"] for p in pays.values()})
    bis = sorted({p["bis"] for p in pays.values()})
    etfs = sorted({p["etf"] for p in pays.values() if p.get("etf")})
    devises = sorted({p["devise"]["symbole"] for p in pays.values() if p.get("devise")})
    debut = (aujourdhui - timedelta(days=400)).strftime("%Y-%m")

    appels = {
        "fmi_croissance": lambda: fournisseur.fmi("NGDP_RPCH"),
        "fmi_inflation": lambda: fournisseur.fmi("PCPIPCH"),
        "fmi_solde_courant": lambda: fournisseur.fmi("BCA_NGDPD"),
        "ocde_cli": lambda: fournisseur.ocde_cli(iso3, debut),
        "ocde_inflation": lambda: fournisseur.ocde_inflation(iso3, debut),
        "bis": lambda: fournisseur.bis_taux(bis, debut),
        "yahoo_cours": lambda: fournisseur.cours(etfs + devises),
        "yahoo_per": lambda: fournisseur.per(etfs),
    }
    resultats, etats = {}, {}
    for nom, appel in appels.items():
        try:
            resultats[nom] = appel()
            vide = not resultats[nom]
            etats[nom] = "vide" if vide else "ok"
            (LOG.warning if vide else LOG.info)("Source %s : %s", nom, "aucune donnée" if vide else f"{len(resultats[nom])} séries")
        except Exception as e:  # une source en panne : on continue avec les autres
            resultats[nom] = {}
            etats[nom] = f"erreur : {str(e)[:160]}"
            LOG.error("Source %s indisponible : %s", nom, str(e)[:200])
    return resultats, etats


# ---------------------------------------------------------------------------
# Calcul des indicateurs d'un pays
# ---------------------------------------------------------------------------

def indicateurs_pays(code: str, cfg: dict, src: dict, aujourdhui: date, config: dict) -> dict:
    iso3, annee = cfg["iso3"], aujourdhui.year
    fraicheur = config["fraicheur_max_jours"]
    sortie = {}

    def fmi(nom, serie):
        valeurs = src[nom].get(iso3, {})
        for a in (annee, annee - 1):
            if valeurs.get(str(a)) is not None:
                return float(valeurs[str(a)]), str(a), SOURCES["fmi"].format(serie=serie, annee=a)
        return None

    # Croissance du PIB (FMI, année en cours)
    r = fmi("fmi_croissance", "NGDP_RPCH")
    sortie["croissance_pib"] = _indicateur("croissance_pib", r[0], "%", r[1], r[2]) if r else _absent("croissance_pib", "absent des données du FMI")

    # Inflation : mensuelle (OCDE) si récente, sinon annuelle (FMI)
    cible = cfg.get("cible_inflation")
    serie = src["ocde_inflation"].get(iso3)
    if serie and _recente(serie[-1][0], aujourdhui, fraicheur["mensuel"]):
        sortie["inflation"] = _indicateur("inflation", serie[-1][1], "%", serie[-1][0], SOURCES["ocde_inflation"], cible=cible, frequence="mensuelle")
    else:
        r = fmi("fmi_inflation", "PCPIPCH")
        sortie["inflation"] = (_indicateur("inflation", r[0], "%", r[1], r[2], cible=cible, frequence="annuelle")
                               if r else _absent("inflation", "absente des données de l'OCDE et du FMI"))

    # Indicateur avancé de l'OCDE (CLI), avec sa pente sur 3 mois
    serie = src["ocde_cli"].get(iso3)
    if serie and _recente(serie[-1][0], aujourdhui, fraicheur["mensuel"]):
        pente = round(serie[-1][1] - serie[-4][1], 2) if len(serie) >= 4 else None
        sortie["indicateur_avance"] = _indicateur("indicateur_avance", serie[-1][1], "", serie[-1][0], SOURCES["ocde_cli"],
                                                  pente_3_mois=pente, valeur_3_mois=round(serie[-4][1], 2) if len(serie) >= 4 else None)
    else:
        sortie["indicateur_avance"] = _absent("indicateur_avance", "non publié par l'OCDE pour ce pays" if not serie else f"dernière donnée trop ancienne ({serie[-1][0]})")

    # Taux réel = taux directeur (BIS) − inflation ; direction sur 6 mois
    serie = src["bis"].get(cfg["bis"])
    inflation = sortie["inflation"].get("valeur")
    if serie and _recente(serie[-1][0], aujourdhui, fraicheur["mensuel"]) and inflation is not None:
        periode, taux = serie[-1]
        il_y_a_6_mois = _valeur_a_date(serie, _date_periode(periode) - timedelta(days=182))
        ecart = taux - il_y_a_6_mois[1] if il_y_a_6_mois else 0
        direction = "baisse" if ecart <= -0.25 else "hausse" if ecart >= 0.25 else "stable"
        sortie["taux_reel"] = _indicateur("taux_reel", taux - inflation, "%", periode, SOURCES["bis"] + " ; inflation : voir ci-dessus",
                                          taux_directeur=taux, direction=direction, variation_6_mois=round(ecart, 2))
    else:
        raison = ("taux directeur non publié par la BIS" if not serie else
                  f"dernier taux BIS trop ancien ({serie[-1][0]})" if not _recente(serie[-1][0], aujourdhui, fraicheur["mensuel"]) else "inflation indisponible")
        sortie["taux_reel"] = _absent("taux_reel", raison)

    # Momentum : performance de l'ETF pays sur 12 mois
    etf = cfg.get("etf")
    serie = src["yahoo_cours"].get(etf) if etf else None
    if serie and _recente(serie[-1][0], aujourdhui, fraicheur["quotidien"]):
        derniere_date, dernier = serie[-1]
        il_y_a_un_an = _valeur_a_date(serie, _date_periode(derniere_date) - timedelta(days=365))
        if il_y_a_un_an:
            sortie["momentum"] = _indicateur("momentum", (dernier / il_y_a_un_an[1] - 1) * 100, "%", derniere_date,
                                             SOURCES["yahoo_prix"].format(symbole=etf), symbole=etf)
    sortie.setdefault("momentum", _absent("momentum", "aucun ETF pays coté" if not etf else "cours de l'ETF indisponibles"))

    # Valorisation : PER de l'ETF (l'écart à la médiane est calculé ensuite, pour tous les pays)
    per = src["yahoo_per"].get(etf) if etf else None
    sortie["valorisation"] = ({"_per": per, "_etf": etf} if per else
                              _absent("valorisation", "aucun ETF pays coté" if not etf else "PER de l'ETF indisponible"))

    # --- Détail ---
    devise = cfg.get("devise")
    serie = src["yahoo_cours"].get(devise["symbole"]) if devise else None
    if serie and _recente(serie[-1][0], aujourdhui, fraicheur["quotidien"]):
        derniere_date, dernier = serie[-1]
        avant = _valeur_a_date(serie, _date_periode(derniere_date) - timedelta(days=91))
        if avant:
            # « inverse » : la paire est cotée en devise locale pour 1 dollar (hausse = la devise faiblit)
            variation = (avant[1] / dernier - 1) * 100 if devise["inverse"] else (dernier / avant[1] - 1) * 100
            sortie["devise_3m"] = _indicateur("devise_3m", variation, "%", derniere_date, SOURCES["yahoo_devise"].format(symbole=devise["symbole"]),
                                              devise=devise["libelle"])
    sortie.setdefault("devise_3m", _absent("devise_3m", "cours de change indisponible"))

    r = fmi("fmi_solde_courant", "BCA_NGDPD")
    sortie["solde_courant"] = _indicateur("solde_courant", r[0], "% du PIB", r[1], r[2]) if r else _absent("solde_courant", "absent des données du FMI")
    sortie["flux_etrangers"] = _absent("flux_etrangers", "non disponible : aucune source gratuite fiable identifiée pour l'instant")
    return sortie


def completer_valorisation(par_pays: dict, aujourdhui: date) -> None:
    """Valorisation relative = PER de l'ETF comparé à la médiane des pays suivis (en %)."""
    pers = [ind["valorisation"]["_per"] for ind in par_pays.values() if "_per" in ind["valorisation"]]
    if len(pers) < 5:
        for ind in par_pays.values():
            if "_per" in ind["valorisation"]:
                ind["valorisation"] = _absent("valorisation", "trop peu de PER disponibles pour calculer une médiane")
        return
    med = median(pers)
    for ind in par_pays.values():
        v = ind["valorisation"]
        if "_per" in v:
            ind["valorisation"] = _indicateur("valorisation", (v["_per"] / med - 1) * 100, "%", aujourdhui.isoformat(),
                                              SOURCES["yahoo_per"].format(symbole=v["_etf"]) + " ; médiane des pays suivis",
                                              per=round(v["_per"], 1), mediane=round(med, 1), symbole=v["_etf"])


# ---------------------------------------------------------------------------
# Notes, secours, tendances
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
    on la garde avec sa date, marquée « ancienne »."""
    if nouveau.get("valeur") is not None or not ancien or ancien.get("valeur") is None or not ancien.get("source"):
        return nouveau
    garde = {k: v for k, v in ancien.items() if k not in ("precedent", "a_verifier", "raison_a_verifier")}
    garde["ancienne"] = True
    garde["raison_ancienne"] = f"source indisponible le {aujourdhui.strftime('%d/%m/%Y')} ({nouveau.get('raison', 'erreur')}) : dernière valeur connue conservée"
    return garde


def verifier(cle: str, ind: dict, seuils: dict) -> None:
    """Valeur hors de la plage habituelle → « à vérifier » (donnée isolée inhabituelle)."""
    if ind.get("valeur") is None or cle not in seuils:
        return
    bas, haut = seuils[cle]
    if not bas <= ind["valeur"] <= haut:
        ind["a_verifier"] = True
        ind["raison_a_verifier"] = f"valeur inhabituelle (hors de l'intervalle {bas} à {haut}) : à vérifier avant d'en tirer une conclusion"


def tendance(nouveau: dict, ancien: dict | None) -> None:
    """Champ « precedent » : l'ancienne valeur et l'ancienne note, si elles ont changé
    (sinon on conserve le « precedent » déjà connu, pour garder la flèche)."""
    if not ancien or not ancien.get("source") or ancien.get("valeur") is None or nouveau.get("valeur") is None:
        return
    if ancien.get("valeur") != nouveau.get("valeur") or ancien.get("date") != nouveau.get("date"):
        nouveau["precedent"] = {"valeur": ancien["valeur"], "note": ancien.get("note"), "date": ancien.get("date")}
    elif ancien.get("precedent"):
        nouveau["precedent"] = ancien["precedent"]


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def executer(fournisseur, config: dict, ancien: dict | None, aujourdhui: date) -> tuple[list, dict]:
    ancien_reel = bool(ancien) and ancien.get("meta", {}).get("fictif") is False
    anciens = {p["code"]: p for p in (ancien or {}).get("donnees", [])} if ancien_reel else {}
    src, etats = collecter(fournisseur, config, aujourdhui)

    par_pays = {code: indicateurs_pays(code, cfg, src, aujourdhui, config) for code, cfg in config["pays"].items()}
    completer_valorisation(par_pays, aujourdhui)

    ponderations = config["ponderations"]
    sortie, textes_gemini = [], 0
    for code, cfg in config["pays"].items():
        a = anciens.get(code, {})
        anciens_ind = {**a.get("indicateurs", {}), **a.get("detail", {})}
        tous = {}
        for cle in PRINCIPAUX + DETAIL:
            ind = secours(cle, par_pays[code][cle], anciens_ind.get(cle), aujourdhui)
            ind["note"] = noter(cle, ind) if ind.get("valeur") is not None else None
            verifier(cle, ind, config["seuils_a_verifier"])
            tendance(ind, anciens_ind.get(cle))
            tous[cle] = ind
        indicateurs = {k: tous[k] for k in PRINCIPAUX}
        detail = {k: tous[k] for k in DETAIL}

        globale = notation.note_globale(indicateurs, ponderations)
        conf = notation.confiance(indicateurs, ponderations, globale["couverture"])
        note = globale["note"]
        verdict = textes.verdict(cfg["nom"], note, indicateurs, PRINCIPAUX, globale["ramenee"])
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

    etats["textes"] = f"Gemini pour {textes_gemini} pays" if textes_gemini else "règles (pas de clé GEMINI_API_KEY ou rédaction refusée)"
    return sortie, etats


def historiser(dossier: Path, donnees: list, jour: date, meta: dict) -> Path:
    """Notes du jour conservées dans data/historique/pays/AAAA-MM-JJ.json (pour mesurer plus tard la justesse)."""
    resume = [{
        "code": p["code"], "note": p["note"], "niveau": p["niveau"], "confiance": p["confiance"]["niveau"],
        "verdict": p["verdict"],
        "indicateurs": {k: {"valeur": v.get("valeur"), "note": v.get("note"), "date": v.get("date")} for k, v in p["indicateurs"].items()},
    } for p in donnees]
    chemin = dossier / f"{jour.isoformat()}.json"
    ecrire_json(chemin, {"meta": {"genere_le": meta["genere_le"], "source": "agent-pays", "version_agent": VERSION_AGENT}, "donnees": resume})
    return chemin


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
    parser.add_argument("--date", help="date du jour (AAAA-MM-JJ), utile pour les tests")
    args = parser.parse_args(argv)

    config = json.loads((DOSSIER_AGENT / "config.json").read_text(encoding="utf-8"))
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    sortie = Path(args.sortie)
    ancien = lire_json(sortie)
    extraire_flux_fictifs(ancien, Path(args.flux))

    fournisseur = FournisseurTest(Path(args.donnees_test)) if args.test else FournisseurReel(RACINE / "agents" / ".cache")
    LOG.info("Agent pays %s — %s — %d pays", VERSION_AGENT, "données de test" if args.test else "sources réelles", len(config["pays"]))
    donnees, etats = executer(fournisseur, config, ancien, aujourdhui)

    # Pas d'écriture si rien n'a changé (donc pas de commit)
    if ancien and ancien.get("meta", {}).get("fictif") is False and ancien.get("donnees") == donnees:
        LOG.info("Aucun changement depuis la dernière exécution : fichiers inchangés.")
        return 0

    meta_ancienne = (ancien or {}).get("meta", {})
    objet = enveloppe(
        donnees, "agent-pays", fictif=False,
        mise_a_jour_precedente=meta_ancienne.get("genere_le") if meta_ancienne.get("fictif") is False else None,
        version_agent=VERSION_AGENT,
        sources=["FMI (DataMapper)", "OCDE (SDMX : CLI, prix)", "BIS (WS_CBPOL)", "Yahoo Finance (yfinance)"],
        etat_des_sources=etats,
        ponderations=config["ponderations"],
    )
    ecrire_json(sortie, objet)
    chemin = historiser(Path(args.historique), donnees, aujourdhui, objet["meta"])
    notes = sorted(((p["note"] or 0, p["nom"]) for p in donnees), reverse=True)
    LOG.info("Écrit : %s et %s", sortie, chemin)
    LOG.info("Notes : %s", ", ".join(f"{n} {s}" for s, n in notes))
    erreurs = [k for k, v in etats.items() if v.startswith("erreur")]
    if erreurs:
        LOG.warning("Sources en erreur : %s (dernières valeurs connues conservées)", ", ".join(erreurs))
    return 0
