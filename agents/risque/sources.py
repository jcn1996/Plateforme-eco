"""
Sources de l'agent risque (toutes gratuites).

- Yahoo Finance (yfinance) : VIX, VSTOXX (si disponible), MOVE, indice dollar, ETF de corrélation
  (ACWI, TLT, GLD) sur 10 ans ; ETF pays et devises des pays suivis (agent pays) sur 13 mois.
- FRED : écarts de crédit (BAMLH0A0HYM2, BAMLC0A0CM, BAMLHE00EHYIOAS), STLFSI4, NFCI, VIXCLS
  et DTWEXBGS (vérification), taux à 10 ans de l'OCDE (IRLTLT01…M156N). API avec FRED_API_KEY,
  sinon fichier CSV public (fournisseur de l'agent macro).
- BCE Data Portal : CISS (stress systémique) ; taux à 10 ans des pays de la zone euro (IRS, vérification).
- FMI (DataMapper) : dette publique / PIB (GGXWDG_NGDP), solde courant (BCA_NGDPD), inflation (PCPIPCH).
- Banque mondiale : réserves en mois d'importations (FI.RES.TOTL.MO).

Toutes les séries sont rendues sous la forme [(date ISO, valeur)], triées.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource, Telechargeur

LOG = journal("agent-risque")
BCE_URL = "https://data-api.ecb.europa.eu/service/data/{flux}/{cle}"

Serie = list[tuple[str, float]]


def _flottant(v) -> float | None:
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def lire_bce_csv(texte: str) -> Serie:
    res = []
    for l in csv.DictReader(io.StringIO(texte)):
        v = _flottant(l.get("OBS_VALUE"))
        if v is not None and l.get("TIME_PERIOD"):
            d = l["TIME_PERIOD"]
            res.append((d + "-01" if len(d) == 7 else d, v))
    if not res:
        raise ErreurSource("BCE : aucune donnée")
    return sorted(res)


class FournisseurReel:
    def __init__(self, dossier_cache: Path):
        from ..macro.sources import FournisseurReel as FournisseurMacro
        self.t = Telechargeur(dossier_cache, duree_cache_h=0.5, essais=3, delai_max=40)
        self.macro = FournisseurMacro(dossier_cache)
        self.macro.t = self.t
        self.macro.pays.t = self.t

    def fred(self, serie: str, depuis: str) -> Serie:
        points, _ = self.macro.fred(serie, depuis)
        res = []
        for d, v in points:
            res.append((d + "-01" if len(d) == 7 else d, v))
        return sorted(res)

    def bce(self, flux: str, cle: str, depuis: str) -> Serie:
        return lire_bce_csv(self.t.texte(BCE_URL.format(flux=flux, cle=cle), params={"startPeriod": depuis, "format": "csvdata"}))

    def fmi(self, serie: str) -> dict[str, dict[str, float]]:
        return self.macro.pays.fmi(serie)

    def banque_mondiale(self, indicateur: str, annee: int) -> dict[str, dict[str, float]]:
        return self.macro.pays.banque_mondiale(indicateur, annee)

    def cours(self, symboles: list[str], periode: str) -> dict[str, Serie]:
        """Clôtures quotidiennes (Yahoo Finance), en une requête groupée."""
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        brut = yf.download(symboles, period=periode, interval="1d", progress=False, auto_adjust=True, threads=False)
        if brut is None or len(brut) == 0:
            raise ErreurSource("Yahoo Finance : aucune donnée")
        cloture = brut["Close"]
        res = {}
        for s in symboles:
            if s in cloture:
                x = cloture[s].dropna()
                if len(x):
                    res[s] = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in x.items()]
        if not res:
            raise ErreurSource("Yahoo Finance : aucun symbole lisible")
        return res


class FournisseurTest:
    """Relit agents/risque/tests/donnees/ (mêmes structures que FournisseurReel).
    Un fichier absent simule une source en panne."""

    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def _lire(self, nom: str):
        chemin = self.dossier / f"{nom}.json"
        if not chemin.exists():
            raise ErreurSource(f"donnée de test absente : {chemin.name} (simulation d'une source en panne)")
        return json.loads(chemin.read_text(encoding="utf-8"))

    def fred(self, serie, depuis):
        return [tuple(x) for x in self._lire(f"fred_{serie}") if x[0] >= depuis]

    def bce(self, flux, cle, depuis):
        return [tuple(x) for x in self._lire(f"bce_{flux}_{cle}") if x[0] >= depuis]

    def fmi(self, serie):
        return self._lire(f"fmi_{serie}")

    def banque_mondiale(self, indicateur, annee):
        return self._lire(f"bm_{indicateur}")

    def cours(self, symboles, periode):
        tout = self._lire("cours")
        res = {s: [tuple(x) for x in tout[s]] for s in symboles if s in tout}
        if not res:
            raise ErreurSource("Yahoo Finance (test) : aucun symbole")
        return res
