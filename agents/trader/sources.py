"""
Sources de cours de l'agent trader.

- FournisseurReel : Yahoo Finance via yfinance (cours différés d'environ 15 minutes) :
  * premiers_cours : premier cours disponible APRÈS l'heure de décision (barres de 5 minutes ; à défaut, ouverture
    de la première séance qui suit le jour de la décision) — jamais un cours passé ;
  * derniers_cours : dernier cours connu (barre de 5 minutes la plus récente, sinon dernière clôture) ;
  * series : clôtures quotidiennes (volatilité, indice de référence) ;
  * change : unités de devise pour 1 euro (paires EURXXX=X), cours du jour ;
  * devises : devise de cotation (fast_info), mise en cache dans l'état de l'agent.
- FournisseurSimule : cours synthétiques déterministes (marche aléatoire par symbole, graine fixe), avec des chocs
  imposés ; ne renvoie jamais une barre postérieure à son horloge `maintenant`. Sert aux tests et au mode --test.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import date, datetime, timedelta, timezone

from ..commun.sante import iso


def _utc(t) -> datetime:
    t = t.to_pydatetime() if hasattr(t, "to_pydatetime") else t
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)


class FournisseurReel:
    simule = False

    def __init__(self):
        import logging
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        self.yf = yf
        self.maintenant = None

    def _download(self, symboles, **kw):
        if not symboles:
            return None
        brut = self.yf.download(sorted(set(symboles)), progress=False, auto_adjust=True, threads=True, group_by="column", **kw)
        return None if brut is None or brut.empty else brut

    @staticmethod
    def _colonne(brut, champ, s):
        try:
            col = brut[champ]
        except KeyError:
            return None
        if hasattr(col, "columns"):
            return col[s].dropna() if s in col.columns else None
        return col.dropna()

    def premiers_cours(self, demandes: dict[str, datetime]) -> dict:
        res = {}
        if not demandes:
            return res
        debut = min(demandes.values()).date()
        brut = self._download(list(demandes), start=debut.isoformat(), interval="5m")
        for s, apres in demandes.items():
            o = self._colonne(brut, "Open", s) if brut is not None else None
            if o is None:
                continue
            for t, v in o.items():
                t = _utc(t)
                if t >= apres and v == v and v > 0:
                    res[s] = {"prix": float(v), "le": iso(t), "barre": "5 min"}
                    break
        manquants = [s for s in demandes if s not in res]
        if manquants:  # pas de barres intrajournalières : ouverture de la première séance après le jour de la décision
            brut = self._download(manquants, start=debut.isoformat(), interval="1d")
            for s in manquants:
                o = self._colonne(brut, "Open", s) if brut is not None else None
                if o is None:
                    continue
                for t, v in o.items():
                    if _utc(t).date() > demandes[s].date() and v == v and v > 0:
                        res[s] = {"prix": float(v), "le": iso(_utc(t)), "barre": "ouverture de séance"}
                        break
        return res

    def derniers_cours(self, symboles: list[str]) -> dict:
        res = {}
        if not symboles:
            return res
        brut = self._download(symboles, period="5d", interval="5m")
        for s in set(symboles):
            c = self._colonne(brut, "Close", s) if brut is not None else None
            if c is not None and len(c):
                res[s] = {"cours": float(c.iloc[-1]), "le": iso(_utc(c.index[-1]))}
        manquants = [s for s in set(symboles) if s not in res]
        if manquants:
            brut = self._download(manquants, period="10d", interval="1d")
            for s in manquants:
                c = self._colonne(brut, "Close", s) if brut is not None else None
                if c is not None and len(c):
                    res[s] = {"cours": float(c.iloc[-1]), "le": iso(_utc(c.index[-1]))}
        return res

    def series(self, symboles: list[str], jours: int = 190) -> dict:
        res = {}
        brut = self._download(symboles, period=f"{jours}d", interval="1d")
        for s in set(symboles):
            c = self._colonne(brut, "Close", s) if brut is not None else None
            if c is not None and len(c):
                res[s] = [(_utc(t).date().isoformat(), float(v)) for t, v in c.items() if v == v and v > 0]
        return res

    def change(self, devises: set[str]) -> dict:
        res = {"EUR": 1.0}
        paires = {d: f"EUR{d}=X" for d in devises if d and d != "EUR"}
        if not paires:
            return res
        brut = self._download(list(paires.values()), period="5d", interval="1d")
        for d, p in paires.items():
            c = self._colonne(brut, "Close", p) if brut is not None else None
            if c is not None and len(c):
                res[d] = float(c.iloc[-1])
        return res

    def devises(self, symboles: list[str]) -> dict:
        res = {}
        for s in symboles:
            try:
                d = self.yf.Ticker(s).fast_info.get("currency")
                if d:
                    res[s] = d
            except Exception:  # noqa: BLE001 — devise déduite du suffixe à défaut
                continue
        return res


# ------------------------------------------------------------------ simulation

TAUX_SIMULES = {"USD": 1.10, "JPY": 165.0, "KRW": 1500.0, "TWD": 35.0, "SEK": 11.3, "VND": 28000.0, "CHF": 0.94, "CAD": 1.52,
                "SGD": 1.45, "THB": 37.0, "ARS": 1300.0, "PLN": 4.3, "GBP": 0.86, "AED": 4.04, "CNY": 7.9, "HKD": 8.6, "MXN": 20.5,
                "INR": 95.0, "BRL": 6.1, "IDR": 18000.0, "ZAR": 20.0, "DKK": 7.46, "NOK": 11.6, "AUD": 1.68, "CLP": 1040.0, "COP": 4500.0,
                "TRY": 45.0, "EGP": 55.0, "MYR": 4.9, "SAR": 4.12, "QAR": 4.0, "ILS": 4.1}


def _graine(texte: str) -> int:
    return int(hashlib.sha256(texte.encode()).hexdigest()[:12], 16)


class FournisseurSimule:
    """Cours synthétiques. Séances du lundi au vendredi, barres horaires de 14 h 30 à 20 h 30 UTC (clôture 21 h).
    chocs = {symbole: [(date ISO, facteur), …]} : le cours est multiplié par le facteur à partir de cette date (incluse).
    tendances = {symbole: rendement quotidien moyen imposé}. echecs = symboles sans cours.
    jumeaux = {symbole: symbole de référence} : mêmes chocs aléatoires quotidiens que la référence (corrélation ≈ 1)."""
    simule = True

    def __init__(self, debut: str = "2026-06-01", chocs: dict | None = None, tendances: dict | None = None, echecs: set | None = None,
                 graine: str = "trader", jumeaux: dict | None = None):
        self.debut = date.fromisoformat(debut)
        self.chocs = chocs or {}
        self.tendances = tendances or {}
        self.echecs = set(echecs or ())
        self.graine = graine
        self.jumeaux = jumeaux or {}
        self._dernier = {}
        self.maintenant: datetime | None = None
        self._cache = {}
        self.appels = []

    # --- trajectoire quotidienne
    def _jours(self, jusqua: date) -> list[date]:
        res, d = [], self.debut
        while d <= jusqua:
            if d.weekday() < 5:
                res.append(d)
            d += timedelta(days=1)
        return res

    def _cloture(self, s: str, d: date) -> float:
        cle = (s, d)
        if cle in self._cache:
            return self._cache[cle]
        ref = self.jumeaux.get(s, s)
        dernier = self._dernier.get(s)
        if dernier is None:
            rng = random.Random(_graine(f"{self.graine}:{s}"))
            base = 20 + rng.random() * 180
            vol = 0.12 + random.Random(_graine(f"{self.graine}:{ref}")).random() * 0.33 if s in self.jumeaux else 0.12 + rng.random() * 0.33
            dernier = (self.debut - timedelta(days=1), base, vol)
        jour, prix, vol = dernier
        mu = self.tendances.get(s, 0.0003)
        while jour < d:
            jour += timedelta(days=1)
            if jour.weekday() < 5:
                r = random.Random(_graine(f"{self.graine}:{ref}:{jour.isoformat()}")).gauss(0, 1)
                prix *= math.exp(mu + vol / math.sqrt(252) * r)
            self._cache[(s, jour)] = prix
        if jour > self._dernier.get(s, (date.min,))[0]:
            self._dernier[s] = (jour, prix, vol)
        return self._cache.get(cle, prix)

    def _facteur(self, s: str, d: date) -> float:
        f = 1.0
        for jour, k in self.chocs.get(s, []):
            if d >= date.fromisoformat(jour):
                f *= k
        return f

    def _barres(self, s: str, d: date) -> list[tuple[datetime, float]]:
        """Barres horaires (heure, cours) d'une séance : interpolation de la clôture précédente à la clôture du jour."""
        prec = d - timedelta(days=1)
        while prec.weekday() >= 5:
            prec -= timedelta(days=1)
        if prec < self.debut:
            prec = None
        f1 = self._facteur(s, d)
        # le choc éventuel du jour se lit dès l'ouverture (écart à l'ouverture)
        c0 = (self._cloture(s, prec) * f1) if prec else self._cloture(s, d) * f1
        c1 = self._cloture(s, d) * f1
        heures = [datetime(d.year, d.month, d.day, 14, 30, tzinfo=timezone.utc) + timedelta(hours=h) for h in range(7)]
        return [(t, c0 * (c1 / c0) ** (i / (len(heures) - 1))) for i, t in enumerate(heures)]

    def _horloge(self) -> datetime:
        return self.maintenant or datetime.now(timezone.utc)

    def premiers_cours(self, demandes: dict[str, datetime]) -> dict:
        self.appels.append(("premiers_cours", sorted(demandes)))
        res = {}
        fin = self._horloge()
        for s, apres in demandes.items():
            if s in self.echecs:
                continue
            d = apres.date()
            while d <= fin.date() and s not in res:
                if d.weekday() < 5 and d >= self.debut:
                    for t, v in self._barres(s, d):
                        if apres <= t <= fin:
                            res[s] = {"prix": v, "le": iso(t), "barre": "1 h (simulée)"}
                            break
                d += timedelta(days=1)
        return res

    def derniers_cours(self, symboles: list[str]) -> dict:
        self.appels.append(("derniers_cours", sorted(set(symboles))))
        res = {}
        fin = self._horloge()
        for s in set(symboles):
            if s in self.echecs:
                continue
            d = fin.date()
            for _ in range(10):
                if d.weekday() < 5 and d >= self.debut:
                    barres = [(t, v) for t, v in self._barres(s, d) if t <= fin]
                    if barres:
                        res[s] = {"cours": barres[-1][1], "le": iso(barres[-1][0])}
                        break
                d -= timedelta(days=1)
        return res

    def series(self, symboles: list[str], jours: int = 190) -> dict:
        fin = self._horloge()
        res = {}
        for s in set(symboles):
            if s in self.echecs:
                continue
            pts = []
            d = max(self.debut, fin.date() - timedelta(days=jours))
            while d < fin.date():
                if d.weekday() < 5:
                    pts.append((d.isoformat(), self._cloture(s, d) * self._facteur(s, d)))
                d += timedelta(days=1)
            if pts:
                res[s] = pts
        return res

    def change(self, devises: set[str]) -> dict:
        res = {"EUR": 1.0}
        fin = self._horloge()
        for d in devises:
            if d in TAUX_SIMULES:
                derive = 1 + 0.01 * math.sin((fin.date() - self.debut).days / 20)
                res[d] = TAUX_SIMULES[d] * derive
        return res

    def devises(self, symboles: list[str]) -> dict:
        return {}
