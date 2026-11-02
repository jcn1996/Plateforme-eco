"""
Sources de l'agent macro (toutes gratuites).

- FRED (Réserve fédérale de Saint-Louis) : API officielle si FRED_API_KEY existe, sinon
  le fichier CSV public fredgraph.csv (même série, sans clé).
- Bundesbank (API SDMX) : rendements de l'État fédéral allemand à 2 et 10 ans.
- BCE Data Portal : courbe des taux de la zone euro, obligations d'État notées AAA (vérification).
- BRI (WS_CBPOL, quotidien) : taux directeurs de toutes les banques centrales.
- OCDE, FMI, Eurostat, BCE, Banque du Canada, Banco Central do Brasil : réutilise
  le fournisseur de l'agent pays (agents/pays/sources.py).
- Yahoo Finance (yfinance) : cuivre, pétrole, dollar, or ; taux US à 10 ans et 13 semaines.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import date
from pathlib import Path

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource, Telechargeur
from ..pays.sources import FournisseurReel as FournisseurPays

LOG = journal("agent-macro")

FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
BUNDESBANK_URL = "https://api.statistiken.bundesbank.de/rest/data/BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.{echeance}.R.A.A._Z._Z.A"
BCE_YC_URL = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.{maturite}"
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/{cle}"

Serie = list[tuple[str, float]]


def _flottant(v) -> float | None:
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return None if x != x else x  # NaN


class FournisseurReel:
    def __init__(self, dossier_cache: Path):
        self.t = Telechargeur(dossier_cache, duree_cache_h=3)
        self.pays = FournisseurPays(dossier_cache)
        self.pays.t = self.t

    # --- FRED : API avec clé, sinon CSV public ---
    def fred(self, serie: str, depuis: str) -> tuple[Serie, str]:
        cle = os.environ.get("FRED_API_KEY")
        if cle:
            d = self.t.json(FRED_API, params={"series_id": serie, "api_key": cle, "file_type": "json", "observation_start": depuis})
            points = [(o["date"], _flottant(o["value"])) for o in d["observations"]]
            mode = "API"
        else:
            texte = self.t.texte(FRED_CSV, params={"id": serie, "cosd": depuis})
            lignes = list(csv.reader(io.StringIO(texte)))
            points = [(l[0], _flottant(l[1])) for l in lignes[1:] if len(l) >= 2]
            mode = "CSV public"
        points = [(d, v) for d, v in points if v is not None]
        if not points:
            raise ErreurSource(f"FRED {serie} : aucune donnée")
        return points, mode

    # --- Bundesbank : rendement des emprunts d'État allemands (R02XX = 2 ans, R10XX = 10 ans) ---
    def bundesbank(self, echeance: str, depuis: str) -> Serie:
        texte = self.t.texte(BUNDESBANK_URL.format(echeance=echeance), params={"startPeriod": depuis, "format": "csv"},
                             entetes={"Accept": "text/csv"})
        res = []
        for ligne in texte.splitlines():
            morceaux = ligne.split(";")
            if len(morceaux) >= 2 and len(morceaux[0]) == 10 and morceaux[0][4] == "-":
                v = _flottant(morceaux[1])
                if v is not None:
                    res.append((morceaux[0], v))
        if not res:
            raise ErreurSource(f"Bundesbank {echeance} : aucune donnée")
        return res

    # --- BCE : courbe AAA de la zone euro (SR_2Y, SR_10Y) ---
    def bce_courbe(self, maturite: str, depuis: str) -> Serie:
        texte = self.t.texte(BCE_YC_URL.format(maturite=maturite), params={"startPeriod": depuis, "format": "csvdata"})
        return [(l["TIME_PERIOD"], float(l["OBS_VALUE"])) for l in csv.DictReader(io.StringIO(texte)) if _flottant(l.get("OBS_VALUE")) is not None]

    # --- BRI : taux directeurs quotidiens ---
    def bis_quotidien(self, codes: list[str], depuis: str) -> dict[str, Serie]:
        texte = self.t.texte(BIS_URL.format(cle="D." + "+".join(codes)), params={"startPeriod": depuis, "format": "csv"})
        res: dict[str, Serie] = {}
        for l in csv.DictReader(io.StringIO(texte)):
            v = _flottant(l.get("OBS_VALUE"))
            if v is not None:
                res.setdefault(l["REF_AREA"], []).append((l["TIME_PERIOD"], v))
        return {k: sorted(v) for k, v in res.items()}

    # --- Sources reprises de l'agent pays ---
    def fmi(self, serie: str):
        return self.pays.fmi(serie)

    def ocde_cli(self, zones: list[str], debut: str) -> dict[str, Serie]:
        return self.pays.ocde_cli(zones, debut)

    def ocde_inflation(self, zones: list[str], debut: str) -> dict[str, Serie]:
        return self.pays.ocde_inflation(zones, debut)

    def eurostat_ipch(self, geos: list[str], debut: str) -> dict[str, Serie]:
        return self.pays.eurostat_ipch(geos, debut)

    def bce_taux(self) -> Serie:
        return self.pays.bce_taux()

    def boc(self, serie: str, depuis: date) -> Serie:
        return self.pays.boc(serie, depuis)

    def bcb(self, serie, depuis: date) -> Serie:
        return self.pays.bcb(serie, depuis)

    # --- Yahoo Finance : clôtures quotidiennes ---
    def cours(self, symboles: list[str]) -> dict[str, Serie]:
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        brut = yf.download(symboles, period="26mo", interval="1d", progress=False, auto_adjust=True, threads=False)
        cloture = brut["Close"]
        res = {}
        for s in symboles:
            if s in cloture:
                serie = cloture[s].dropna()
                if len(serie):
                    res[s] = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in serie.items()]
        return res


class FournisseurTest:
    """Relit les fichiers de agents/macro/tests/donnees/ (captures réelles, mêmes structures)."""

    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def _lire(self, nom: str):
        chemin = self.dossier / f"{nom}.json"
        if not chemin.exists():
            raise FileNotFoundError(f"Donnée de test absente : {chemin.name} (simulation d'une source en panne)")
        return json.loads(chemin.read_text(encoding="utf-8"))

    @staticmethod
    def _serie(x):
        return [tuple(p) for p in x]

    def _dict(self, x):
        return {k: self._serie(v) for k, v in x.items()}

    def fred(self, serie, depuis):
        d = self._lire(f"fred_{serie}")
        return self._serie(d["points"]), d["mode"]

    def bundesbank(self, echeance, depuis):
        return self._serie(self._lire(f"bundesbank_{echeance}"))

    def bce_courbe(self, maturite, depuis):
        return self._serie(self._lire(f"bce_courbe_{maturite}"))

    def bis_quotidien(self, codes, depuis):
        return self._dict(self._lire("bis_quotidien"))

    def fmi(self, serie):
        return self._lire(f"fmi_{serie}")

    def ocde_cli(self, zones, debut):
        return self._dict(self._lire("ocde_cli"))

    def ocde_inflation(self, zones, debut):
        return self._dict(self._lire("ocde_inflation"))

    def eurostat_ipch(self, geos, debut):
        return self._dict(self._lire("eurostat_ipch"))

    def bce_taux(self):
        return self._serie(self._lire("bce_taux"))

    def boc(self, serie, depuis):
        return self._serie(self._lire(f"boc_{serie}"))

    def bcb(self, serie, depuis):
        return self._serie(self._lire(f"bcb_{serie}"))

    def cours(self, symboles):
        return self._dict(self._lire("cours"))


class Capture:
    """Enveloppe un fournisseur réel et enregistre chaque réponse comme donnée de test
    (python -m agents.macro --capturer)."""

    NOMS = {"fred": lambda a: f"fred_{a[0]}", "bundesbank": lambda a: f"bundesbank_{a[0]}",
            "bce_courbe": lambda a: f"bce_courbe_{a[0]}", "bis_quotidien": lambda a: "bis_quotidien",
            "fmi": lambda a: f"fmi_{a[0]}", "ocde_cli": lambda a: "ocde_cli", "ocde_inflation": lambda a: "ocde_inflation",
            "eurostat_ipch": lambda a: "eurostat_ipch", "bce_taux": lambda a: "bce_taux",
            "boc": lambda a: f"boc_{a[0]}", "bcb": lambda a: f"bcb_{a[0]}", "cours": lambda a: "cours"}

    def __init__(self, reel, dossier: Path, zones_fmi: list[str]):
        self.reel, self.dossier, self.zones_fmi = reel, Path(dossier), zones_fmi
        self.dossier.mkdir(parents=True, exist_ok=True)

    def __getattr__(self, nom):
        methode = getattr(self.reel, nom)

        def appel(*args):
            res = methode(*args)
            a_ecrire = res
            if nom == "fred":
                a_ecrire = {"points": res[0], "mode": res[1]}
            elif nom == "fmi":  # on ne garde que les zones utiles (fichier complet trop lourd)
                a_ecrire = {k: v for k, v in res.items() if k in self.zones_fmi}
            (self.dossier / f"{self.NOMS[nom](args)}.json").write_text(json.dumps(a_ecrire, ensure_ascii=False), encoding="utf-8")
            return res
        return appel
