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
from pathlib import Path

from ..commun.journal import journal
from ..commun.telechargement import Telechargeur

LOG = journal("sources")

FMI_URL = "https://www.imf.org/external/datamapper/api/v1/{serie}"
OCDE_URL = "https://sdmx.oecd.org/public/rest/data/{flux}/{cle}"
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/{cle}"

# Libellés exacts des sources, recopiés dans chaque indicateur
SOURCES = {
    "fmi": "FMI, World Economic Outlook (API DataMapper, série {serie}), année {annee}",
    "ocde_cli": "OCDE, Composite Leading Indicator (DF_CLI, amplitude ajustée), mensuel",
    "ocde_inflation": "OCDE, indice des prix à la consommation (DF_PRICES_ALL), glissement annuel mensuel",
    "bis": "BIS, taux directeurs des banques centrales (WS_CBPOL), mensuel",
    "yahoo_prix": "Yahoo Finance via yfinance, cours de clôture de l'ETF {symbole}",
    "yahoo_per": "Yahoo Finance via yfinance, PER (trailing) de l'ETF {symbole}",
    "yahoo_devise": "Yahoo Finance via yfinance, cours {symbole}",
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
        cle = "+".join(iso3) + ".M.N.CPI.PA._T.N.GY"
        texte = self.t.texte(OCDE_URL.format(flux="OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0", cle=cle),
                             params={"startPeriod": debut, "format": "csvfilewithlabels"})
        return _series_par_zone(_csv(texte))

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
