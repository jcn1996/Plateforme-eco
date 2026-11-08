"""Seules sources externes du chef d'orchestre (tout le reste vient des autres agents) :
- cours ajustés Yahoo Finance des verdicts arrivés à échéance et des indices de référence (suivi de performance) ;
- dates de publication des résultats des sociétés de la liste de surveillance (agenda).
FournisseurTest lit des réponses enregistrées (tests, sans réseau)."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


class FournisseurReel:
    def series(self, symboles: list[str]) -> dict:
        from ..entreprises.comptes import Yahoo
        return Yahoo().cours_groupes(sorted(set(symboles)), periode="2y")

    def resultats(self, societes: list[dict]) -> list[dict]:
        import yfinance as yf
        res = []
        for s in societes:
            try:
                cal = yf.Ticker(s["ticker"]).calendar or {}
                dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
                for d in dates or []:
                    d = d.date() if isinstance(d, datetime) else d
                    if isinstance(d, date):
                        res.append({"ticker": s["ticker"], "nom": s["nom"], "date": d.isoformat()})
                        break
            except Exception:  # noqa: BLE001 — date inconnue : rien d'affiché
                continue
        return res


    def flux_secteurs(self, emetteurs: dict) -> dict:
        """Relevés des ETF sectoriels, comme pour les ETF pays : fichier d'historique SSGA, page iShares, puis Yahoo
        Finance (parts en circulation, VL) en secours et en vérification. Renvoie {flux_ssga, flux_ishares, flux_yahoo_parts}."""
        import time
        import warnings
        from ..commun.telechargement import Telechargeur
        from ..pays.sources_flux import ISHARES, NAVIGATEUR, SSGA, lire_ishares, lire_ssga
        warnings.filterwarnings("ignore")
        t = Telechargeur(Path(__file__).resolve().parents[1] / ".cache" / "chef", duree_cache_h=12, delai_politesse=0.5)
        src = {"flux_ssga": {}, "flux_ishares": {}, "flux_yahoo_parts": {}}
        erreurs = []
        for etf, em in emetteurs.items():
            try:
                if em["emetteur"] == "ssga":
                    src["flux_ssga"][etf] = lire_ssga(t.octets(SSGA + em["fichier"], entetes={"User-Agent": NAVIGATEUR}))
                elif em["emetteur"] == "ishares":
                    src["flux_ishares"][etf] = lire_ishares(t.texte(ISHARES + em["page"], entetes={"User-Agent": NAVIGATEUR}))
            except Exception as e:  # noqa: BLE001 — un fonds en échec n'empêche pas les autres
                erreurs.append(f"{etf} : {str(e)[:80]}")
        import yfinance as yf
        for etf in emetteurs:
            try:
                info = yf.Ticker(etf).info
                parts, vl, quand = info.get("sharesOutstanding"), info.get("navPrice") or info.get("previousClose"), info.get("regularMarketTime")
                if parts and vl and quand:
                    from datetime import timezone
                    src["flux_yahoo_parts"][etf] = {"date": datetime.fromtimestamp(int(quand), timezone.utc).date().isoformat(),
                                                    "parts": float(parts), "vl": float(vl),
                                                    "encours": float(info["totalAssets"]) if info.get("totalAssets") else None}
            except Exception as e:  # noqa: BLE001
                erreurs.append(f"Yahoo {etf} : {str(e)[:60]}")
            time.sleep(0.5)
        if erreurs and not any(src.values()):
            raise RuntimeError(" ; ".join(erreurs[:4]))
        return src


class FournisseurTest:
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def _lire(self, nom):
        try:
            return json.loads((self.dossier / nom).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def series(self, symboles: list[str]) -> dict:
        tout = self._lire("series.json") or {}
        return {s: [tuple(x) for x in tout[s]] for s in symboles if s in tout}

    def flux_secteurs(self, emetteurs: dict) -> dict:
        tout = self._lire("flux_secteurs.json") or {}
        return {k: {e: v[e] for e in emetteurs if e in v} for k, v in tout.items()}

    def resultats(self, societes: list[dict]) -> list[dict]:
        tout = self._lire("resultats.json") or []
        tickers = {s["ticker"] for s in societes}
        return [x for x in tout if x["ticker"] in tickers]
