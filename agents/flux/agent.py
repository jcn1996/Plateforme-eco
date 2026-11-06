"""
Agent flux commerciaux (sans IA) : commerce de biens entre les pays suivis, pour les arcs du globe.

Uniquement le commerce de marchandises : ni flux de capitaux, ni dette.

Sources (gratuites) :
  1. FMI, International Trade in Goods (IMTS, ex-DOTS), API SDMX : exportations (FAB) et
     importations (CAF) mensuelles en dollars, par pays partenaire, plus le total « Monde » ;
     valeurs en dollars (l'attribut SCALE n'est qu'une indication d'affichage), une série par sens ;
  2. UN Comtrade (aperçu public, sans clé) en secours si le FMI ne répond pas ;
  3. sinon, le dernier fichier est conservé tel quel et la panne est signalée dans l'écran Santé.
Contrôles (voir controles.py) : Census Bureau pour les flux des États-Unis (clé gratuite
CENSUS_API_KEY), total des exportations (FMI, à défaut Banque mondiale) pour les autres.

Calcul, pour chaque couple orienté A → B de pays suivis :
  - montant : pour un flux des États-Unis, la source officielle américaine (Census Bureau) ;
    sinon les exportations de A vers B déclarées par A, ou à défaut (ex. Taïwan, qui ne déclare
    pas au FMI) les importations de B en provenance de A déclarées par B (« miroir ») ;
  - date : le dernier mois disponible pour ce couple ;
  - variation sur 12 mois : même mois de l'année précédente, même déclarant ;
  - écart > 10 % avec une autre déclaration du même mois : « sources divergentes » ;
    variation au-delà de ±40 % non confirmée par une seconde source : « à vérifier ».

Lisibilité : on ne garde que
  - les 3 premiers clients et les 3 premiers fournisseurs de chaque pays (top_de / top_vers),
    affichés quand on touche ce pays ;
  - les 40 plus gros flux mondiaux (mondial), affichés sans sélection.

Sorties : data/flux.json (réécrit seulement si les flux ont changé) et data/journal/agent-flux.json
(écran « Santé des agents »). Mise à jour hebdomadaire (workflow agent-flux.yml, planificateur).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agents.commun import sante
from agents.commun.journal import journal
from agents.commun.sortie import enveloppe, ecrire_json, lire_json
from agents.commun.telechargement import ErreurSource, Telechargeur

from . import controles
from .controles import MONDE

LOG = journal("agent-flux")
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
CONFIG = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
DONNEES_TEST = DOSSIER / "tests" / "donnees"

FMI_URL = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,IMTS/{decl}.XG_FOB_USD+MG_CIF_USD.{part}.M"
FMI_CSV = {"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}
COMTRADE_URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
SOURCE_FMI = "FMI — International Trade in Goods (IMTS)"
SOURCE_COMTRADE = "UN Comtrade (secours)"
SOURCE_CENSUS = "Census Bureau (États-Unis)"
SOURCE_BANQUE_MONDIALE = "Banque mondiale (exportations totales)"
SOURCES_COURTES = {SOURCE_FMI: "FMI, International Trade in Goods", SOURCE_COMTRADE: "UN Comtrade",
                   SOURCE_CENSUS: "Census Bureau"}
MENTION = "Données mensuelles, décalées de 1 à 2 mois"
INDICATEURS_FMI = {"XG_FOB_USD": "X", "MG_CIF_USD": "M"}


# ------------------------------------------------------------------ mois

def mois_de(t: datetime) -> str:
    return f"{t.year:04d}-{t.month:02d}"


def decaler(periode: str, mois: int) -> str:
    """decaler("2026-07", -12) → "2025-07"."""
    a, m = (int(x) for x in periode.split("-"))
    n = a * 12 + (m - 1) + mois
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def ecart_mois(debut: str, fin: str) -> int:
    (a1, m1), (a2, m2) = ((int(x) for x in p.split("-")) for p in (debut, fin))
    return (a2 - a1) * 12 + (m2 - m1)


# ------------------------------------------------------------------ sources
# Séries : {(sens "X"|"M", déclarant ISO2, partenaire ISO2): {"AAAA-MM": valeur en dollars}}

def lire_fmi(lecteur, codes: list[str], debut: str, config: dict = CONFIG) -> dict:
    """Exportations et importations mensuelles entre les pays suivis (une seule requête)."""
    iso3 = {config["pays"][c]["iso3"]: c for c in codes}
    liste = "+".join(iso3)
    texte = lecteur.texte(FMI_URL.format(decl=liste, part=liste + "+G001"),  # G001 : total « Monde »
                          params={"startPeriod": debut, "detail": "dataonly"}, entetes=FMI_CSV)
    lignes = csv.DictReader(io.StringIO(texte))
    requis = {"COUNTRY", "INDICATOR", "COUNTERPART_COUNTRY", "TIME_PERIOD", "OBS_VALUE"}
    if not requis <= set(lignes.fieldnames or []):
        raise ErreurSource(f"FMI : format inattendu (colonnes {lignes.fieldnames})")
    series: dict = {}
    for r in lignes:
        part = MONDE if r["COUNTERPART_COUNTRY"] == "G001" else iso3.get(r["COUNTERPART_COUNTRY"])
        sens, decl = INDICATEURS_FMI.get(r["INDICATOR"]), iso3.get(r["COUNTRY"])
        periode = r["TIME_PERIOD"].replace("-M", "-")
        if not (sens and decl and part) or decl == part or len(periode) != 7:
            continue
        try:
            valeur = float(r["OBS_VALUE"])
        except ValueError:
            continue
        series.setdefault((sens, decl, part), {})[periode] = valeur
    if not series:
        raise ErreurSource("FMI : aucune donnée")
    return series


def lire_comtrade(lecteur, codes: list[str], maintenant: datetime, config: dict = CONFIG) -> dict:
    """Secours : aperçu public de UN Comtrade (un mois par appel, 500 lignes au plus).
    On cherche le mois le plus récent assez couvert, puis le même mois un an plus tôt."""
    reglages = config["comtrade"]
    m49 = {config["pays"][c]["m49"]: c for c in codes}
    partenaires = ",".join(map(str, sorted(m49) + [0]))  # 0 : total « Monde »

    def periode(p: str) -> dict:
        series, echecs, groupes = {}, 0, 0
        declarants = sorted(m49)
        for i in range(0, len(declarants), reglages["declarants_par_appel"]):
            groupes += 1
            try:
                reponse = lecteur.json(COMTRADE_URL, params={
                    "reporterCode": ",".join(map(str, declarants[i:i + reglages["declarants_par_appel"]])),
                    "period": p.replace("-", ""), "partnerCode": partenaires,
                    "flowCode": "X,M", "cmdCode": "TOTAL"})
            except (ErreurSource, ValueError) as e:
                LOG.warning("Comtrade %s : %s", p, e)
                echecs += 1
                continue
            for r in (reponse or {}).get("data") or []:
                if r.get("partner2Code", 0) != 0 or r.get("customsCode", "C00") != "C00" or r.get("motCode", 0) != 0:
                    continue  # on ne garde que les totaux
                decl = m49.get(r.get("reporterCode"))
                part = MONDE if r.get("partnerCode") == 0 else m49.get(r.get("partnerCode"))
                if decl and part and decl != part and r.get("flowCode") in ("X", "M") and r.get("primaryValue"):
                    series.setdefault((r["flowCode"], decl, part), {})[p] = float(r["primaryValue"])
        if groupes and echecs == groupes:
            raise ErreurSource(f"Comtrade : aucun appel n'a abouti pour {p}")
        return series

    courant = mois_de(maintenant)
    for k in range(2, 2 + reglages["mois_essayes"]):
        p = decaler(courant, -k)
        series = periode(p)
        couverts = {decl for (_, decl, _) in series}
        if len(couverts) >= reglages["couverture_min"] * len(codes):
            for cle, valeurs in periode(decaler(p, -12)).items():
                series.setdefault(cle, {}).update(valeurs)
            return series
        LOG.info("Comtrade %s : %d déclarants seulement, mois précédent essayé.", p, len(couverts))
    raise ErreurSource("Comtrade : aucun mois récent assez couvert")


# ------------------------------------------------------------------ calcul

def _declarations(a: str, b: str, series: dict, census: dict, nom_source: str) -> list[dict]:
    """Déclarations disponibles pour le flux A → B (une par source et par déclarant)."""
    res = [{"nom": nom_source, "declarant": a, "mesure": "exportations", "serie": series.get(("X", a, b))},
           {"nom": nom_source, "declarant": b, "mesure": "importations", "serie": series.get(("M", b, a))}]
    us = census.get(("X", "US", b)) if a == "US" else census.get(("M", "US", a)) if b == "US" else None
    if us:
        # Le Census Bureau remplace la déclaration des États-Unis relayée par le FMI (même origine)
        res = [d for d in res if d["declarant"] != "US"]
        res.append({"nom": SOURCE_CENSUS, "declarant": "US", "mesure": "exportations" if a == "US" else "importations", "serie": us})
    return [d for d in res if d["serie"] and any(v > 0 for v in d["serie"].values())]


def _derniere(d: dict) -> str:
    return max(p for p, v in d["serie"].items() if v > 0)


def calculer_flux(series: dict, codes: list[str], config: dict = CONFIG, census: dict | None = None,
                  totaux: list[dict] | None = None, nom_source: str = SOURCE_FMI) -> list[dict]:
    """Un flux par couple orienté A → B, avec ses contrôles croisés.
    Source retenue : pour un flux des États-Unis, la source officielle américaine (Census Bureau, à défaut la
    déclaration des États-Unis relayée par le FMI) ; sinon la déclaration la plus récente, à égalité celle de
    l'exportateur (miroir : importations déclarées par le pays de destination)."""
    census = census or {}
    seuil, ecart_max, variation_max = (config["seuil_variation_pct"], config["controles"]["ecart_max_pct"],
                                       config["controles"]["variation_max_pct"])
    depassements = {t["pays"]: t for t in totaux or [] if t.get("statut") == "somme supérieure au total"}
    res = []
    for a in codes:
        for b in codes:
            if a == b:
                continue
            decl = _declarations(a, b, series, census, nom_source)
            if not decl:
                continue
            officielles = [d for d in decl if "US" in (a, b) and d["declarant"] == "US"]
            retenue = max(officielles or decl, key=lambda d: (_derniere(d), d["nom"] == SOURCE_CENSUS, d["mesure"] == "exportations"))
            periode = _derniere(retenue)
            valeur = retenue["serie"][periode]
            var = controles.variation(retenue["serie"], periode)
            autres = [d for d in decl if d is not retenue and periode in d["serie"]]
            ecarts = [controles.ecart_pct(d["serie"][periode], valeur) for d in autres]
            raisons = []
            if any(e is not None and e > ecart_max for e in ecarts):
                raisons.append(f"écart de {max(ecarts):.0f} % entre les déclarations (seuil {ecart_max} %)".replace(".", ","))
            if retenue["mesure"] == "exportations" and retenue["declarant"] in depassements:
                t = depassements[retenue["declarant"]]
                raisons.append(f"exportations déclarées vers les pays suivis ({t['somme_partenaires_md']} Md$) supérieures "
                               f"au total ({t['total_md']} Md$, {t['source_total']})".replace(".", ","))
            statut = "sources divergentes" if raisons else "concordantes" if autres else "une seule source"
            fort = var is not None and abs(var) > variation_max
            confirme = controles.confirmee(var, [controles.variation(d["serie"], periode) for d in autres], variation_max) if fort else None
            res.append({
                "de": a, "vers": b, "montant_md": round(valeur / 1e9, 2), "devise": "USD", "periode": periode,
                "variation_12m_pct": var, "tendance": tendance(var, seuil),
                "mesure": retenue["mesure"], "declarant": retenue["declarant"], "source": retenue["nom"],
                "controle": statut, "ecart_max_pct": max((e for e in ecarts if e is not None), default=None),
                "raisons": raisons, "a_verifier": bool(fort and not confirme), "variation_confirmee": confirme,
                "sources": [{"nom": d["nom"], "declarant": d["declarant"], "mesure": d["mesure"],
                             "montant_md": round(d["serie"][periode] / 1e9, 2), "periode": periode,
                             "variation_12m_pct": controles.variation(d["serie"], periode), "retenue": d is retenue}
                            for d in [retenue, *autres]],
            })
    return res


def tendance(variation: float | None, seuil: float) -> str:
    if variation is None:
        return "inconnue"
    return "hausse" if variation >= seuil else "baisse" if variation <= -seuil else "stable"


def selectionner(flux: list[dict], codes: list[str], n: int = CONFIG["partenaires_par_pays"],
                 m: int = CONFIG["flux_mondiaux"]) -> list[dict]:
    """Garde les n premiers clients (top_de) et fournisseurs (top_vers) de chaque pays et les m plus gros flux (mondial)."""
    cle = lambda f: (-f["montant_md"], f["de"], f["vers"])
    choisis: dict[tuple, dict] = {}

    def marquer(f, champ):
        choisis.setdefault((f["de"], f["vers"]), {**f, "top_de": False, "top_vers": False, "mondial": False})[champ] = True

    for c in codes:
        for f in sorted((f for f in flux if f["de"] == c), key=cle)[:n]:
            marquer(f, "top_de")
        for f in sorted((f for f in flux if f["vers"] == c), key=cle)[:n]:
            marquer(f, "top_vers")
    for f in sorted(flux, key=cle)[:m]:
        marquer(f, "mondial")
    return sorted(choisis.values(), key=cle)


# ------------------------------------------------------------------ collecte et santé

def codes_suivis(dossier_data: Path, config: dict = CONFIG) -> list[str]:
    """Pays suivis par l'agent pays (data/pays.json), limités à ceux dont on connaît les codes."""
    pays = [p.get("code") for p in (lire_json(Path(dossier_data) / "pays.json") or {}).get("donnees", [])]
    if not pays:
        return list(config["pays"])
    inconnus = [c for c in pays if c not in config["pays"]]
    if inconnus:
        LOG.warning("Pays sans codes FMI / Comtrade dans agents/flux/config.json : %s", ", ".join(inconnus))
    return [c for c in pays if c in config["pays"]]


def collecter(lecteur, codes: list[str], maintenant: datetime, config: dict = CONFIG,
              cle_census: str | None = None) -> tuple[list[dict], list[dict], str | None, dict]:
    """Renvoie (flux retenus, états des sources pour l'écran Santé, source principale ou None, contrôles)."""
    debut = decaler(mois_de(maintenant), -config["historique_mois"])
    sources = []
    try:
        series, source = lire_fmi(lecteur, codes, debut, config), SOURCE_FMI
        sources.append({"nom": SOURCE_FMI, "etat": "ok"})
    except ErreurSource as e:
        LOG.error("FMI indisponible : %s", e)
        sources.append({"nom": SOURCE_FMI, "etat": "échec", "detail": str(e)[:300]})
        try:
            series, source = lire_comtrade(lecteur, codes, maintenant, config), SOURCE_COMTRADE
            sources.append({"nom": SOURCE_COMTRADE, "etat": "secours", "detail": "le FMI ne répond pas : données de UN Comtrade"})
        except ErreurSource as e2:
            LOG.error("Comtrade indisponible : %s", e2)
            sources.append({"nom": SOURCE_COMTRADE, "etat": "échec", "detail": str(e2)[:300]})
            return [], sources, None, {}

    # Contrôle 1 : Census Bureau pour les flux des États-Unis
    census = {}
    if not cle_census:
        sources.append({"nom": SOURCE_CENSUS, "etat": "non configurée",
                        "detail": "clé CENSUS_API_KEY absente : déclaration des États-Unis relayée par le FMI"})
    elif "US" in codes:
        try:
            census = controles.lire_census(lecteur, codes, maintenant, config, cle_census)
            sources.append({"nom": SOURCE_CENSUS, "etat": "ok"})
        except ErreurSource as e:
            LOG.warning("Census Bureau indisponible : %s", e)
            sources.append({"nom": SOURCE_CENSUS, "etat": "échec",
                            "detail": f"{str(e)[:200]} : déclaration des États-Unis relayée par le FMI"})

    # Contrôle 2 : somme des exportations vers les partenaires ≤ exportations totales (FMI, sinon Banque mondiale)
    sans_total = [c for c in codes if not series.get(("X", c, MONDE))
                  and any(series.get(("X", c, b)) for b in codes if b != c)]
    banque_mondiale = {}
    if sans_total:
        try:
            banque_mondiale = controles.totaux_banque_mondiale(lecteur, sans_total, config)
            sources.append({"nom": SOURCE_BANQUE_MONDIALE, "etat": "ok"})
        except (ErreurSource, ValueError) as e:
            LOG.warning("Banque mondiale indisponible : %s", e)
            sources.append({"nom": SOURCE_BANQUE_MONDIALE, "etat": "échec", "detail": str(e)[:300]})
    totaux = controles.controler_totaux(series, codes, banque_mondiale)

    tous = calculer_flux(series, codes, config, census, totaux, source)
    if tous:
        # Un couple sans donnée récente n'est pas affiché avec un mois trop ancien
        recente = max(f["periode"] for f in tous)
        anciens = [f for f in tous if ecart_mois(f["periode"], recente) > config["retard_max_flux_mois"]]
        if anciens:
            LOG.info("%d flux écartés : dernier mois plus ancien de %d mois que %s.", len(anciens), config["retard_max_flux_mois"], recente)
        tous = [f for f in tous if f not in anciens]
    flux = selectionner(tous, codes, config["partenaires_par_pays"], config["flux_mondiaux"])
    if flux:
        recente = max(f["periode"] for f in flux)
        retard = ecart_mois(recente, mois_de(maintenant))
        if retard > config["peremption_mois"]:
            principale = sources[0] if sources[0]["etat"] == "ok" else sources[1]
            principale.update({"etat": "périmée", "detail": f"dernier mois disponible : {recente} ({retard} mois de retard)"})
    return flux, sources, source, bilan_controles(flux, totaux, census, maintenant)


def bilan_controles(flux: list[dict], totaux: list[dict], census: dict, maintenant: datetime) -> dict:
    """Contrôles de l'exécution, pour data/journal/agent-flux.json."""
    detail = lambda f: {k: f[k] for k in ("de", "vers", "montant_md", "periode", "variation_12m_pct", "source", "declarant",
                                          "controle", "ecart_max_pct", "raisons", "a_verifier", "variation_confirmee", "sources")}
    return {
        "le": sante.iso(maintenant),
        "resume": {
            "flux": len(flux),
            "concordantes": sum(f["controle"] == "concordantes" for f in flux),
            "sources_divergentes": sum(f["controle"] == "sources divergentes" for f in flux),
            "une_seule_source": sum(f["controle"] == "une seule source" for f in flux),
            "a_verifier": sum(f["a_verifier"] for f in flux),
            "variations_fortes_confirmees": sum(bool(f["variation_confirmee"]) for f in flux),
            "census": "utilisé" if census else "non utilisé (déclaration des États-Unis relayée par le FMI)",
            "totaux_depasses": [t["pays"] for t in totaux if t.get("statut") == "somme supérieure au total"],
        },
        "totaux": totaux,
        "sources_divergentes": [detail(f) for f in flux if f["controle"] == "sources divergentes"],
        "a_verifier": [detail(f) for f in flux if f["a_verifier"]],
    }


def couverture(flux: list[dict], codes: list[str]) -> float:
    presents = {f["de"] for f in flux} | {f["vers"] for f in flux}
    return len(presents & set(codes)) / len(codes) if codes else 0.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent flux commerciaux : commerce de biens entre les pays suivis.")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier des données (flux.json, pays.json, journal/)")
    ap.add_argument("--test", action="store_true", help="données de test enregistrées, sans réseau")
    ap.add_argument("--donnees-test", default=str(DONNEES_TEST))
    ap.add_argument("--date", help="date simulée (AAAA-MM-JJ), avec --test")
    ap.add_argument("--census-cle", help="clé de l'API du Census Bureau (par défaut : variable CENSUS_API_KEY ; « test » en mode test)")
    args = ap.parse_args(argv)
    cle_census = args.census_cle if args.census_cle is not None else ("test" if args.test else os.environ.get("CENSUS_API_KEY"))

    data = Path(args.data)
    maintenant = (datetime.fromisoformat(args.date).replace(hour=12, tzinfo=timezone.utc) if args.date
                  else datetime.now(timezone.utc))
    lecteur = LecteurTest(Path(args.donnees_test)) if args.test else Telechargeur(RACINE / "agents" / ".cache" / "flux", delai_politesse=3.0)
    codes = codes_suivis(data)
    flux, sources, source, bilan = collecter(lecteur, codes, maintenant, cle_census=cle_census)

    chemin = data / "flux.json"
    precedent = lire_json(chemin) or {}
    raisons = []
    if flux:
        taux = couverture(flux, codes)
        if taux < CONFIG["couverture_min"]:
            raisons.append(f"Seulement {taux:.0%} des pays suivis ont des flux")
        for c in bilan["resume"]["totaux_depasses"]:
            raisons.append(f"{c} : exportations déclarées vers les pays suivis supérieures à son total")
        recente = max(f["periode"] for f in flux)
        nouveau = enveloppe(
            flux, source=source, source_courte=SOURCES_COURTES[source], fictif=False, producteur="agent-flux",
            nature="commerce de biens",
            description="Commerce de marchandises entre les pays suivis (ni flux de capitaux, ni dette). "
                        "top_de / top_vers : 3 premiers clients / fournisseurs de chaque pays ; mondial : 40 plus gros flux.",
            unite="milliards de dollars par mois", periode_recente=recente, mention=MENTION,
            seuil_variation_pct=CONFIG["seuil_variation_pct"],
            controles={"ecart_max_pct": CONFIG["controles"]["ecart_max_pct"],
                       "variation_max_pct": CONFIG["controles"]["variation_max_pct"],
                       "census": bilan["resume"]["census"]})
        sans_date = lambda m: {k: v for k, v in (m or {}).items() if k != "genere_le"}
        if flux != precedent.get("donnees") or sans_date(nouveau["meta"]) != sans_date(precedent.get("meta")):
            ecrire_json(chemin, nouveau)
            LOG.info("%s mis à jour : %d flux, dernier mois %s (%s).", chemin, len(flux), recente, source)
        else:
            LOG.info("Flux inchangés : fichier non réécrit.")
    else:
        LOG.error("Aucune donnée de commerce : %s conservé tel quel.", chemin)

    journal_chemin = data / "journal" / "agent-flux.json"
    j = lire_json(journal_chemin) or {"meta": {}, "donnees": []}
    ancien = (j.get("meta") or {}).get("sante")
    if bilan:
        # Contrôles : détail de la dernière exécution, et résumé des 52 dernières (un an d'exécutions hebdomadaires)
        j["controles"] = bilan
        j["donnees"] = [*[e for e in j.get("donnees", []) if e.get("le") != bilan["le"]],
                        {"le": bilan["le"], **bilan["resume"]}][-52:]
        ecrire_json(journal_chemin, j)
    bloc = sante.bloc_sante("flux", "Agent flux commerciaux", 8, "agent-flux.yml", sources, maintenant, ancien,
                            raisons_supplementaires=raisons)
    sante.enregistrer_sante(journal_chemin, bloc, forcer=True,
                            description="Santé de l'agent flux commerciaux (commerce de biens, FMI / UN Comtrade)")
    return 0


class LecteurTest:
    """Remplace le téléchargeur en mode test : réponses enregistrées dans tests/donnees/."""

    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def texte(self, url: str, params: dict | None = None, entetes: dict | None = None) -> str:
        params = params or {}
        if "api.imf.org" in url:
            chemin = self.dossier / "fmi_imts.csv"
        elif "api.census.gov" in url:
            chemin = self.dossier / f"census_{url.split('/')[-2]}_{params.get('time')}.json"
        elif "api.worldbank.org" in url:
            chemin = self.dossier / "banque_mondiale.json"
        elif "comtrade" in url:
            chemin = self.dossier / f"comtrade_{params.get('period')}.json"
        else:
            raise ErreurSource(f"{url} : pas de donnée de test")
        if not chemin.exists():
            raise ErreurSource(f"{url} : HTTP 503 (test)")
        return chemin.read_text(encoding="utf-8")

    def json(self, url: str, params: dict | None = None, entetes: dict | None = None):
        return json.loads(self.texte(url, params, entetes))
