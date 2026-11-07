"""
Sources de données gratuites, sans clé API.

Chaque fonction renvoie des séries brutes ; la transformation en indicateurs
se fait dans agent.py. Deux « fournisseurs » :
- FournisseurReel : interroge les vraies sources (FMI, OCDE, BIS, Yahoo Finance) ;
- FournisseurTest : relit des données de test (agents/pays/tests/donnees),
  pour vérifier la logique sans réseau.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource, Telechargeur

LOG = journal("sources")

FMI_URL = "https://www.imf.org/external/datamapper/api/v1/{serie}"
OCDE_URL = "https://sdmx.oecd.org/public/rest/data/{flux}/{cle}"
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/{cle}"
BM_URL = "https://api.worldbank.org/v2/country/all/indicator/{indicateur}"
EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{jeu}"
BCE_URL = "https://data-api.ecb.europa.eu/service/data/{flux}/{cle}"
BCB_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
BOC_URL = "https://www.bankofcanada.ca/valet/observations/{serie}/json"
DBNOMICS_URL = "https://api.db.nomics.world/v22/series/{identifiant}"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
BLS_URL = "https://api.bls.gov/publicAPI/{version}/timeseries/data/{serie}"
# L'OCDE publie désormais l'IPC de certains pays (passés à la nomenclature COICOP 2018)
# dans un nouveau jeu ; les autres restent à jour dans l'ancien. On interroge les deux.
OCDE_FLUX_INFLATION = ["OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0", "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"]

# Libellés exacts des sources, recopiés dans chaque indicateur
SOURCES = {
    "fmi": "FMI, World Economic Outlook (API DataMapper, série {serie}), année {annee}",
    "ocde_cli": "OCDE, Composite Leading Indicator (DF_CLI, amplitude ajustée), mensuel",
    "ocde_inflation": "OCDE, indice des prix à la consommation (DF_PRICES_C2018_ALL ou DF_PRICES_ALL, la plus récente), glissement annuel mensuel",
    "bis": "BIS, taux directeurs des banques centrales (WS_CBPOL), mensuel",
    "yahoo_prix": "Yahoo Finance via yfinance, cours de clôture de l'ETF {symbole}",
    "yahoo_per": "Yahoo Finance via yfinance, PER (trailing) de l'ETF {symbole}",
    "yahoo_devise": "Yahoo Finance via yfinance, cours {symbole}",
    "yahoo_indice": "Yahoo Finance via yfinance, clôtures de l'indice {indice} ({symbole}), en monnaie locale ({monnaie})",
    "yahoo_change": "Yahoo Finance via yfinance, cours {symbole} (conversion en euros)",
    "ocde_eo": "OCDE, Perspectives économiques (DF_EO, GDPV_ANNPCT), prévision {annee}",
    "bm": "Banque mondiale, {indicateur}, année {annee}",
    "eurostat": "Eurostat, IPCH (prc_hicp_minr, glissement annuel), mensuel",
    "bce_taux": "BCE, taux de la facilité de dépôt (FM, Data Portal)",
    "bce_change": "BCE, cours de référence de l'euro (EXR, Data Portal)",
}


def _csv(texte: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(texte)))


def _series_par_zone(lignes: list[dict], champ_zone: str = "REF_AREA") -> dict[str, list[tuple[str, float]]]:
    series: dict[str, list[tuple[str, float]]] = {}
    for l in lignes:
        valeur = l.get("OBS_VALUE")
        if valeur in (None, "", "NaN"):
            continue
        series.setdefault(l[champ_zone], []).append((l["TIME_PERIOD"], float(valeur)))
    return {zone: sorted(obs) for zone, obs in series.items()}


class FournisseurReel:
    def __init__(self, dossier_cache: Path):
        self.t = Telechargeur(dossier_cache)

    # --- FMI : estimations annuelles (toutes les économies en une requête) ---
    def fmi(self, serie: str) -> dict[str, dict[str, float]]:
        donnees = self.t.json(FMI_URL.format(serie=serie))
        return donnees["values"][serie]

    # --- OCDE : indicateur avancé (CLI) ---
    def ocde_cli(self, iso3: list[str], debut: str) -> dict[str, list[tuple[str, float]]]:
        cle = "+".join(iso3) + ".M.LI...AA...H"
        texte = self.t.texte(OCDE_URL.format(flux="OECD.SDD.STES,DSD_STES@DF_CLI,4.1", cle=cle),
                             params={"startPeriod": debut, "format": "csvfilewithlabels"})
        return _series_par_zone(_csv(texte))

    # --- OCDE : inflation mensuelle (glissement annuel de l'IPC) ---
    def ocde_inflation(self, iso3: list[str], debut: str) -> dict[str, list[tuple[str, float]]]:
        """Pour chaque pays, la série la plus récente parmi le jeu COICOP 2018 et l'ancien jeu."""
        cle = "+".join(iso3) + ".M.N.CPI.PA._T.N.GY"
        jeux, erreurs = [], []
        for flux in OCDE_FLUX_INFLATION:
            try:
                texte = self.t.texte(OCDE_URL.format(flux=flux, cle=cle), params={"startPeriod": debut, "format": "csvfilewithlabels"})
                jeux.append(_series_par_zone(_csv(texte)))
            except ErreurSource as e:  # un jeu peut ne contenir aucun des pays demandés (404) : on garde l'autre
                erreurs.append(str(e))
        if not jeux:
            raise ErreurSource(" ; ".join(erreurs))
        return fusionner_plus_recent(jeux)

    # --- BIS : taux directeurs mensuels ---
    def bis_taux(self, codes: list[str], debut: str) -> dict[str, list[tuple[str, float]]]:
        cle = "M." + "+".join(codes)
        texte = self.t.texte(BIS_URL.format(cle=cle), params={"startPeriod": debut, "format": "csv"})
        return _series_par_zone(_csv(texte))

    # --- Yahoo Finance : cours des ETF pays et des devises (13 mois quotidiens) ---
    def cours(self, symboles: list[str]) -> dict[str, list[tuple[str, float]]]:
        import warnings
        import yfinance as yf  # importé ici : inutile en mode test
        warnings.filterwarnings("ignore", module="yfinance")  # avertissements internes de yfinance sans intérêt ici
        brut = yf.download(symboles, period="13mo", interval="1d", progress=False, auto_adjust=True, threads=False)
        cloture = brut["Close"]
        resultat = {}
        for s in symboles:
            if s not in cloture:
                continue
            serie = cloture[s].dropna()
            if len(serie):
                resultat[s] = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in serie.items()]
        return resultat

    # --- Yahoo Finance : PER des ETF (peut être refusé selon le réseau) ---
    def per(self, symboles: list[str]) -> dict[str, float]:
        import time
        import yfinance as yf
        resultat = {}
        for s in symboles:
            for essai in range(2):  # une reprise par ETF, avec une pause (Yahoo limite le rythme)
                try:
                    per = yf.Ticker(s).info.get("trailingPE")
                    if per and 0 < float(per) < 200:
                        resultat[s] = float(per)
                    break
                except Exception as e:  # Yahoo refuse parfois ces requêtes (401, 429) : on continue
                    if essai:
                        LOG.warning("PER indisponible pour %s (%s)", s, str(e)[:120])
                    time.sleep(3)
            time.sleep(0.7)
        return resultat


def fusionner_plus_recent(jeux: list[dict[str, list[tuple[str, float]]]]) -> dict[str, list[tuple[str, float]]]:
    """Pour chaque zone, garde la série dont la dernière période est la plus récente
    (à égalité, le premier jeu de la liste l'emporte)."""
    resultat = {}
    for jeu in jeux:
        for zone, serie in jeu.items():
            if serie and (zone not in resultat or max(serie)[0] > max(resultat[zone])[0]):
                resultat[zone] = serie
    return resultat


def _jsonstat_par_geo(donnees: dict) -> dict[str, list[tuple[str, float]]]:
    """Lecture d'un jeu Eurostat (JSON-stat) : {pays: [(période, valeur)]}."""
    ids, tailles = donnees["id"], donnees["size"]
    pas = [1] * len(ids)
    for i in range(len(ids) - 2, -1, -1):
        pas[i] = pas[i + 1] * tailles[i + 1]
    index = {k: donnees["dimension"][k]["category"]["index"] for k in ids}
    i_geo, i_temps = ids.index("geo"), ids.index("time")
    resultat = {}
    for geo, g in index["geo"].items():
        for periode, t in index["time"].items():
            v = donnees["value"].get(str(g * pas[i_geo] + t * pas[i_temps]))
            if v is not None:
                resultat.setdefault(geo, []).append((periode, float(v)))
    return {k: sorted(v) for k, v in resultat.items()}


def _methodes_supplementaires(cls):
    """Nouvelles sources (vérification croisée), ajoutées au fournisseur réel."""

    def ocde_eo(self, iso3, annee):
        cle = "+".join(iso3) + ".GDPV_ANNPCT.A"
        texte = self.t.texte(OCDE_URL.format(flux="OECD.ECO.MAD,DSD_EO@DF_EO,1.2", cle=cle),
                             params={"startPeriod": str(annee - 1), "endPeriod": str(annee), "format": "csvfilewithlabels"})
        resultat = {}
        for l in _csv(texte):
            if l.get("OBS_VALUE") not in (None, ""):
                resultat.setdefault(l["REF_AREA"], {})[l["TIME_PERIOD"]] = float(l["OBS_VALUE"])
        return resultat

    def banque_mondiale(self, indicateur, annee):
        donnees = self.t.json(BM_URL.format(indicateur=indicateur),
                              params={"format": "json", "date": f"{annee - 3}:{annee}", "per_page": "20000"})
        resultat = {}
        for x in donnees[1] or []:
            if x.get("value") is not None and x.get("countryiso3code"):
                resultat.setdefault(x["countryiso3code"], {})[x["date"]] = float(x["value"])
        return resultat

    def eurostat_ipch(self, geos, debut):
        texte = self.t.texte(EUROSTAT_URL.format(jeu="prc_hicp_minr"),
                             params={"unit": "RCH_A", "coicop18": "TOTAL", "sinceTimePeriod": debut, "geo": list(geos)})
        return _jsonstat_par_geo(json.loads(texte))

    def bce_taux(self):
        texte = self.t.texte(BCE_URL.format(flux="FM", cle="D.U2.EUR.4F.KR.DFR.LEV"), params={"lastNObservations": "400", "format": "csvdata"})
        return [(l["TIME_PERIOD"], float(l["OBS_VALUE"])) for l in _csv(texte) if l.get("OBS_VALUE")]

    def bce_change(self, devises):
        cle = "D." + "+".join(devises) + ".EUR.SP00.A"
        texte = self.t.texte(BCE_URL.format(flux="EXR", cle=cle), params={"lastNObservations": "120", "format": "csvdata"})
        resultat = {}
        for l in _csv(texte):
            if l.get("OBS_VALUE"):
                resultat.setdefault(l["CURRENCY"], []).append((l["TIME_PERIOD"], float(l["OBS_VALUE"])))
        return {k: sorted(v) for k, v in resultat.items()}

    def bcb(self, serie, depuis):
        donnees = self.t.json(BCB_URL.format(serie=serie), params={"formato": "json", "dataInicial": depuis.strftime("%d/%m/%Y")})
        return [(f"{x['data'][6:10]}-{x['data'][3:5]}-{x['data'][0:2]}", float(x["valor"])) for x in donnees]

    def boc(self, serie, depuis):
        donnees = self.t.json(BOC_URL.format(serie=serie), params={"start_date": depuis.isoformat()})
        return [(o["d"], float(o[serie]["v"])) for o in donnees["observations"] if o.get(serie, {}).get("v") not in (None, "")]

    def dbnomics(self, identifiant):
        donnees = self.t.json(DBNOMICS_URL.format(identifiant=identifiant), params={"observations": "1", "format": "json"})
        doc = donnees["series"]["docs"][0]
        return [(p, float(v)) for p, v in zip(doc["period"], doc["value"]) if v not in ("NA", None)]

    def bls(self, serie, depuis):
        """API publique du BLS : version 1 sans clé (25 requêtes par jour et par adresse IP),
        ou version 2 si la clé facultative BLS_API_KEY est fournie."""
        import os
        cle = os.environ.get("BLS_API_KEY")
        params = {"startyear": str(depuis.year), "endyear": str(date.today().year)}
        if cle:
            params["registrationkey"] = cle
        donnees = self.t.json(BLS_URL.format(version="v2" if cle else "v1", serie=serie), params=params)
        if donnees.get("status") != "REQUEST_SUCCEEDED":
            raise ErreurSource(f"BLS : {donnees.get('status')} ({' '.join(donnees.get('message') or [])[:120]})")
        series = (donnees.get("Results") or {}).get("series") or []
        points = series[0].get("data", []) if series else []
        return sorted((f"{x['year']}-{x['period'][1:]}", float(x["value"])) for x in points
                      if x.get("period", "").startswith("M") and x["period"] != "M13" and x.get("value") not in ("-", ""))

    def fred(self, serie, depuis):
        import os
        cle = os.environ.get("FRED_API_KEY")
        if not cle:
            raise RuntimeError("clé FRED_API_KEY absente : source ignorée")
        donnees = self.t.json(FRED_URL, params={"series_id": serie, "api_key": cle, "file_type": "json",
                                                "observation_start": depuis.isoformat()})
        return [(o["date"], float(o["value"])) for o in donnees["observations"] if o["value"] not in (".", "")]

    for nom, f in list(locals().items()):
        if callable(f) and nom != "cls":
            setattr(cls, nom, f)
    return cls


class FournisseurTest:
    """Relit les fichiers de agents/pays/tests/donnees/ (mêmes structures que FournisseurReel)."""

    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def _lire(self, nom: str):
        chemin = self.dossier / f"{nom}.json"
        if not chemin.exists():
            raise FileNotFoundError(f"Donnée de test absente : {chemin.name} (simulation d'une source en panne)")
        return json.loads(chemin.read_text(encoding="utf-8"))

    def fmi(self, serie):
        return self._lire(f"fmi_{serie}")

    def ocde_cli(self, iso3, debut):
        return {k: [tuple(x) for x in v] for k, v in self._lire("ocde_cli").items()}

    def ocde_inflation(self, iso3, debut):
        return {k: [tuple(x) for x in v] for k, v in self._lire("ocde_inflation").items()}

    def bis_taux(self, codes, debut):
        return {k: [tuple(x) for x in v] for k, v in self._lire("bis").items()}

    def cours(self, symboles):
        return {k: [tuple(x) for x in v] for k, v in self._lire("cours").items()}

    def per(self, symboles):
        return self._lire("per")

    # Nouvelles sources : mêmes structures que le fournisseur réel
    def ocde_eo(self, iso3, annee):
        return self._lire("ocde_eo")

    def banque_mondiale(self, indicateur, annee):
        return self._lire(f"bm_{indicateur}")

    def eurostat_ipch(self, geos, debut):
        return {k: [tuple(x) for x in v] for k, v in self._lire("eurostat").items()}

    def bce_taux(self):
        return [tuple(x) for x in self._lire("bce_taux")]

    def bce_change(self, devises):
        return {k: [tuple(x) for x in v] for k, v in self._lire("bce_change").items()}

    def bcb(self, serie, depuis):
        return [tuple(x) for x in self._lire(f"bcb_{serie}")]

    def boc(self, serie, depuis):
        return [tuple(x) for x in self._lire(f"boc_{serie}")]

    def dbnomics(self, identifiant):
        return [tuple(x) for x in self._lire("dbnomics_" + identifiant.replace("/", "_"))]

    def fred(self, serie, depuis):
        return [tuple(x) for x in self._lire(f"fred_{serie}")]

    def bls(self, serie, depuis):
        return [tuple(x) for x in self._lire(f"bls_{serie}")]


_methodes_supplementaires(FournisseurReel)

# Flux d'investissement des ETF pays : émetteurs (iShares, SSGA, VanEck, Global X) et Yahoo Finance
from .sources_flux import _methodes_reelles, _methodes_test  # noqa: E402

_methodes_reelles(FournisseurReel)
_methodes_test(FournisseurTest)
