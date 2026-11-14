"""
Données historiques gratuites du backtest, avec cache disque (agents/.cache/backtest, jamais commité).

- Yahoo Finance (yfinance) : cours quotidiens (ajustés des dividendes et non ajustés), dividendes, divisions.
- FRED (CSV public, sans clé) : VIX, inflation américaine (CPI), taux réels.
- OCDE (SDMX) : indicateur avancé (CLI), inflation (IPC, glissement annuel).
- BRI (WS_CBPOL) : taux directeurs mensuels.
- FMI (DataMapper) : croissance du PIB réel annuelle.
- SEC (XBRL companyfacts) : comptes des sociétés américaines, avec la date de dépôt de chaque valeur.
- CFTC (Socrata, désagrégé) : positionnement des gérants depuis juin 2006.
- EIA (fichiers historiques .xls publics, sans clé) : stocks hebdomadaires.

`FournisseurTest` produit des données synthétiques déterministes (aucun réseau) pour les tests.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import time
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource, Telechargeur

LOG = journal("backtest")
RACINE = Path(__file__).resolve().parents[2]
CACHE = RACINE / "agents" / ".cache" / "backtest"

OCDE_URL = "https://sdmx.oecd.org/public/rest/data/{flux}/{cle}"
OCDE_FLUX_INFLATION = ["OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0", "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"]
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/{cle}"
FMI_URL = "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
CFTC_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_FAITS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Postes comptables (clés de l'agent entreprises) → concepts us-gaap, par ordre de préférence.
# « flux » : montants d'un exercice (durée d'environ un an) ; « stock » : montants à la date de clôture.
CONCEPTS = {
    "ca": ("flux", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                    "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"]),
    "resultat_net": ("flux", ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]),
    "ebit": ("flux", ["OperatingIncomeLoss"]),
    "cfo": ("flux", ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
    "capex": ("flux", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]),
    "marge_brute": ("flux", ["GrossProfit"]),
    "cout_ventes": ("flux", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]),
    "interets": ("flux", ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"]),
    "amortissements": ("flux", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"]),
    "rd": ("flux", ["ResearchAndDevelopmentExpense"]),
    "sga": ("flux", ["SellingGeneralAndAdministrativeExpense"]),
    "impot": ("flux", ["IncomeTaxExpenseBenefit"]),
    "resultat_avant_impot": ("flux", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    "dividendes": ("flux", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]),
    "rachats": ("flux", ["PaymentsForRepurchaseOfCommonStock"]),
    "emissions": ("flux", ["ProceedsFromIssuanceOfCommonStock"]),
    "actions": ("flux", ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"]),
    "actifs": ("stock", ["Assets"]),
    "actifs_courants": ("stock", ["AssetsCurrent"]),
    "passifs_courants": ("stock", ["LiabilitiesCurrent"]),
    "passifs_totaux": ("stock", ["Liabilities"]),
    "capitaux_propres": ("stock", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "tresorerie": ("stock", ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    "dette_lt": ("stock", ["LongTermDebtNoncurrent", "LongTermDebt"]),
    "dette_ct": ("stock", ["LongTermDebtCurrent", "DebtCurrent"]),
    "emprunts_ct": ("stock", ["ShortTermBorrowings", "CommercialPaper"]),
    "creances": ("stock", ["AccountsReceivableNetCurrent"]),
    "stocks": ("stock", ["InventoryNet"]),
    "fournisseurs": ("stock", ["AccountsPayableCurrent"]),
    "benefices_non_distribues": ("stock", ["RetainedEarningsAccumulatedDeficit"]),
    "goodwill": ("stock", ["Goodwill"]),
    "immobilisations": ("stock", ["PropertyPlantAndEquipmentNet"]),
}


def _fred_csv(texte: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(texte))
    col = [c for c in df.columns if c.lower() not in ("date", "observation_date")][0]
    d = df.columns[0]
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = pd.to_datetime(df[d])
    return s.dropna()


def _sdmx_csv(texte: str) -> dict[str, pd.Series]:
    df = pd.read_csv(io.StringIO(texte), dtype=str)
    res = {}
    for zone, g in df.groupby("REF_AREA"):
        v = pd.to_numeric(g["OBS_VALUE"], errors="coerce")
        idx = pd.PeriodIndex(g["TIME_PERIOD"], freq="M").to_timestamp(how="end").normalize()
        s = pd.Series(v.to_numpy(), index=idx).dropna().sort_index()
        res[zone] = s[~s.index.duplicated(keep="last")]
    return res


class FournisseurReel:
    def __init__(self, cache: Path = CACHE, duree_cache_h: float = 24 * 20):
        self.cache = Path(cache)
        self.t = Telechargeur(self.cache / "http", duree_cache_h=duree_cache_h, delai_politesse=0.3, delai_max=90)
        self.ua = os.environ.get("SEC_USER_AGENT")  # exigé par la SEC (contact) ; sans lui, le lot entreprises est ignoré
        self._sec_dernier = 0.0
        self.sources: dict[str, dict] = {}  # état de chaque source (santé, rapport)

    def _etat(self, nom: str, ok: bool, detail: str | None = None):
        e = self.sources.setdefault(nom, {"nom": nom, "ok": 0, "echecs": 0, "detail": None})
        e["ok" if ok else "echecs"] += 1
        if detail and not ok:
            e["detail"] = detail[:200]

    # --- Yahoo Finance ---
    def cours(self, symboles: list[str], debut: str) -> dict[str, pd.DataFrame]:
        """{'ajuste', 'cloture', 'dividendes', 'divisions'} : DataFrames quotidiens (colonnes = symboles)."""
        import yfinance as yf
        warnings.filterwarnings("ignore")
        symboles = sorted(set(s for s in symboles if s))
        chemin = self.cache / "yahoo"
        chemin.mkdir(parents=True, exist_ok=True)
        morceaux = {k: [] for k in ("ajuste", "cloture", "dividendes", "divisions")}
        a_lire = []
        for s in symboles:
            f = chemin / f"{s.replace('^', '_').replace('=', '_').replace('/', '_')}.pkl.gz"
            if f.exists() and time.time() - f.stat().st_mtime < 20 * 86400:
                df = pd.read_pickle(f)
                for k in morceaux:
                    morceaux[k].append(df[k].rename(s))
                self._etat("Yahoo Finance (yfinance)", True)  # lu dans le cache local (moins de 20 jours)
            else:
                a_lire.append(s)
        for i in range(0, len(a_lire), 50):
            lot = a_lire[i:i + 50]
            brut = None
            for essai in range(3):
                try:
                    brut = yf.download(lot, start=debut, auto_adjust=False, actions=True, progress=False, threads=True, group_by="column")
                    break
                except Exception as e:  # Yahoo limite parfois le rythme : nouvelle tentative
                    LOG.warning("Yahoo (%s…) : %s", lot[0], str(e)[:120])
                    time.sleep(10 * (essai + 1))
            for s in lot:
                try:
                    df = pd.DataFrame({
                        "ajuste": brut["Adj Close"][s], "cloture": brut["Close"][s],
                        "dividendes": brut["Dividends"][s] if "Dividends" in brut else 0.0,
                        "divisions": brut["Stock Splits"][s] if "Stock Splits" in brut else 0.0,
                    })
                    df = df[df["cloture"].notna()]
                    if df.empty:
                        raise KeyError("aucun cours")
                    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
                    df.to_pickle(chemin / f"{s.replace('^', '_').replace('=', '_').replace('/', '_')}.pkl.gz")
                    for k in morceaux:
                        morceaux[k].append(df[k].rename(s))
                    self._etat("Yahoo Finance (yfinance)", True)
                except Exception as e:
                    self._etat("Yahoo Finance (yfinance)", False, f"{s} : {e}")
            time.sleep(1)
        return {k: (pd.concat(v, axis=1).sort_index() if v else pd.DataFrame()) for k, v in morceaux.items()}

    # --- FRED ---
    def fred(self, serie: str) -> pd.Series:
        try:
            s = _fred_csv(self.t.texte(FRED_URL, params={"id": serie}))
            self._etat("FRED (CSV public)", True)
            return s
        except (ErreurSource, Exception) as e:
            self._etat("FRED (CSV public)", False, f"{serie} : {e}")
            return pd.Series(dtype=float)

    # --- OCDE ---
    def ocde_cli(self, iso3: list[str], debut: str) -> dict[str, pd.Series]:
        try:
            texte = self.t.texte(OCDE_URL.format(flux="OECD.SDD.STES,DSD_STES@DF_CLI,4.1", cle="+".join(iso3) + ".M.LI...AA...H"),
                                 params={"startPeriod": debut[:7], "format": "csvfilewithlabels"})
            self._etat("OCDE (indicateur avancé)", True)
            return _sdmx_csv(texte)
        except Exception as e:
            self._etat("OCDE (indicateur avancé)", False, str(e))
            return {}

    def ocde_inflation(self, iso3: list[str], debut: str) -> dict[str, pd.Series]:
        res, erreurs = {}, []
        for flux in reversed(OCDE_FLUX_INFLATION):  # ancien jeu puis nouveau : le plus récent l'emporte, l'ancien comble le début
            try:
                texte = self.t.texte(OCDE_URL.format(flux=flux, cle="+".join(iso3) + ".M.N.CPI.PA._T.N.GY"),
                                     params={"startPeriod": debut[:7], "format": "csvfilewithlabels"})
                for z, s in _sdmx_csv(texte).items():
                    res[z] = s.combine_first(res[z]) if z in res else s
            except Exception as e:  # un jeu peut ne contenir aucun des pays demandés (404) : l'autre suffit
                erreurs.append(str(e))
        self._etat("OCDE (inflation)", bool(res), " ; ".join(erreurs))
        return res

    # --- BRI ---
    def bis_taux(self, codes: list[str], debut: str) -> dict[str, pd.Series]:
        try:
            texte = self.t.texte(BIS_URL.format(cle="M." + "+".join(codes)), params={"startPeriod": debut[:7], "format": "csv"})
            self._etat("BRI (taux directeurs)", True)
            return _sdmx_csv(texte)
        except Exception as e:
            self._etat("BRI (taux directeurs)", False, str(e))
            return {}

    # --- FMI ---
    def fmi_croissance(self) -> dict[str, dict[int, float]]:
        try:
            d = self.t.json(FMI_URL)["values"]["NGDP_RPCH"]
            self._etat("FMI (croissance du PIB)", True)
            return {z: {int(a): float(v) for a, v in x.items() if v is not None} for z, x in d.items()}
        except Exception as e:
            self._etat("FMI (croissance du PIB)", False, str(e))
            return {}

    # --- SEC ---
    def _sec(self, url: str):
        """Lecture directe, sans le cache texte du téléchargeur : une réponse brute pèse plusieurs Mo
        et seul son format compact est gardé. Au plus 8 requêtes par seconde, reprises sur 429 et 5xx."""
        if not self.ua:
            raise ErreurSource("secret SEC_USER_AGENT absent : comptes SEC ignorés")
        erreur = None
        for essai in range(4):
            attente = 0.13 - (time.monotonic() - self._sec_dernier)
            if attente > 0:
                time.sleep(attente)
            self._sec_dernier = time.monotonic()
            try:
                r = self.t.session.get(url, headers={"User-Agent": self.ua, "Accept-Encoding": "gzip, deflate"}, timeout=90)
                if r.status_code == 200:
                    return r.json()
                erreur = f"HTTP {r.status_code}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
            except Exception as e:  # réseau
                erreur = f"{type(e).__name__}: {e}"
            time.sleep(2 * 2 ** essai)
        raise ErreurSource(f"{url} : {erreur}")

    def sec_ciks(self) -> dict[str, str]:
        d = self._sec(SEC_TICKERS)
        return {x["ticker"].upper().replace(".", "-"): str(x["cik_str"]).zfill(10) for x in d.values()}

    def sec_faits(self, cik: str) -> dict | None:
        """Faits compacts d'une société : {cle: [[debut|None, fin, depot, valeur], …]}, actions_circulation, devise.
        Gardés dans le cache (agents/.cache/backtest/sec/), partagés entre les lots du workflow."""
        f = self.cache / "sec" / f"{cik}.json.gz"
        if f.exists() and time.time() - f.stat().st_mtime < 25 * 86400:
            self._etat("SEC (XBRL companyfacts)", True)  # lu dans le cache (tranche téléchargée par le workflow)
            return json.loads(gzip.decompress(f.read_bytes()))
        try:
            brut = self._sec(SEC_FAITS.format(cik=cik))
            self._etat("SEC (XBRL companyfacts)", True)
        except Exception as e:
            self._etat("SEC (XBRL companyfacts)", False, f"{cik} : {e}")
            return None
        compact = compacter_faits_sec(brut)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(gzip.compress(json.dumps(compact, separators=(",", ":")).encode()))
        return compact

    # --- CFTC ---
    def cftc(self, codes: list[str], depuis: str) -> dict[str, pd.DataFrame]:
        liste = ",".join(f"'{c}'" for c in codes)
        try:
            lignes = self.t.json(CFTC_URL, params={
                "$where": f"cftc_contract_market_code in({liste}) and report_date_as_yyyy_mm_dd >= '{depuis}'",
                "$select": "cftc_contract_market_code,report_date_as_yyyy_mm_dd,m_money_positions_long_all,m_money_positions_short_all,open_interest_all",
                "$order": "report_date_as_yyyy_mm_dd", "$limit": "200000"})
            self._etat("CFTC (Commitments of Traders)", True)
        except Exception as e:
            self._etat("CFTC (Commitments of Traders)", False, str(e))
            return {}
        res = {}
        for l in lignes:
            try:
                res.setdefault(l["cftc_contract_market_code"], []).append(
                    {"date": l["report_date_as_yyyy_mm_dd"][:10], "long": float(l["m_money_positions_long_all"]),
                     "short": float(l["m_money_positions_short_all"]), "oi": float(l.get("open_interest_all") or 0) or None})
            except (KeyError, TypeError, ValueError):
                continue
        return {k: pd.DataFrame(v) for k, v in res.items()}

    # --- EIA ---
    def eia_xls(self, url: str) -> pd.Series:
        try:
            contenu = self.t.octets(url)
            s = lire_xls_eia(contenu)
            self._etat("EIA (fichiers historiques)", True)
            return s.sort_index()
        except Exception as e:
            self._etat("EIA (fichiers historiques)", False, f"{url.rsplit('/', 1)[-1]} : {e}")
            return pd.Series(dtype=float)


def lire_xls_eia(contenu: bytes) -> pd.Series:
    """Feuille « Data 1 » d'un fichier historique de l'EIA (.xls) : dates en colonne A, valeurs en colonne B.
    Lue avec xlrd directement (déjà requis par l'agent pays ; pandas exige une version plus récente)."""
    import xlrd
    livre = xlrd.open_workbook(file_contents=contenu)
    f = livre.sheet_by_name("Data 1")
    dates, valeurs = [], []
    for i in range(3, f.nrows):
        d, v = f.cell_value(i, 0), f.cell_value(i, 1)
        if isinstance(d, float) and isinstance(v, float):
            dates.append(xlrd.xldate_as_datetime(d, livre.datemode))
            valeurs.append(v)
    return pd.Series(valeurs, index=pd.DatetimeIndex(dates), dtype=float).sort_index()


def compacter_faits_sec(brut: dict) -> dict:
    """Garde, pour chaque poste, les valeurs annuelles des 10-K (flux d'environ un an, stocks à la clôture)
    et toutes les publications du nombre d'actions en circulation, avec leur date de dépôt."""
    gaap = (brut.get("facts") or {}).get("us-gaap") or {}
    dei = (brut.get("facts") or {}).get("dei") or {}
    res = {"faits": {}}
    for cle, (nature, concepts) in CONCEPTS.items():
        lignes = []
        for rang, c in enumerate(concepts):
            unites = (gaap.get(c) or {}).get("units") or {}
            points = unites.get("USD") or unites.get("shares") or []
            for p in points:
                if p.get("form") not in ("10-K", "10-K/A", "10-KT") or not p.get("filed") or p.get("val") is None:
                    continue
                if nature == "flux":
                    if not p.get("start"):
                        continue
                    duree = (date.fromisoformat(p["end"]) - date.fromisoformat(p["start"])).days
                    if not 330 <= duree <= 400:
                        continue
                elif p.get("start"):
                    continue
                lignes.append([rang, p["end"], p["filed"], float(p["val"])])
        if lignes:
            res["faits"][cle] = lignes
    actions = []
    for p in ((dei.get("EntityCommonStockSharesOutstanding") or {}).get("units") or {}).get("shares", []):
        if p.get("filed") and p.get("val"):
            actions.append([p["filed"], float(p["val"])])
    res["actions_circulation"] = sorted(actions)
    return res


# ------------------------------------------------------------------ données de test (synthétiques)

class FournisseurTest:
    """Historiques synthétiques et déterministes, construits pour que certains signaux soient prédictifs
    (le momentum et la valorisation des pays, la marge des sociétés) et d'autres non : les tests vérifient
    que le backtest les distingue. Aucune donnée réelle, aucun réseau."""

    def __init__(self, graine: int = 7, debut: str = "2009-01-01", fin: str = "2026-10-31", n_pays: int = 14, n_societes: int = 40):
        self.r = np.random.default_rng(graine)
        self.jours = pd.bdate_range(debut, fin)
        self.n_pays, self.n_societes = n_pays, n_societes
        self.sources = {"Données de test (synthétiques)": {"nom": "Données de test (synthétiques)", "ok": 1, "echecs": 0, "detail": None}}
        self._cours = None

    # Pays de test : codes ISO fictifs PA, PB…
    def pays_test(self) -> dict:
        res = {}
        for i in range(self.n_pays):
            c = "P" + chr(65 + i)
            res[c] = {"nom": f"Pays {c}", "iso3": f"P{chr(65 + i)}X", "bis": c, "etf": f"ETF{c}",
                      "devise": {"symbole": f"FX{c}=X", "inverse": True}, "cible_inflation": 2.0}
        return res

    def societes_test(self) -> list[dict]:
        secteurs = ["Information Technology", "Health Care", "Industrials", "Energy", "Consumer Staples"]
        return [{"ticker": f"S{i:02d}", "nom": f"Société {i}", "pays": "US", "secteur": secteurs[i % 5], "cik": f"{i:010d}"}
                for i in range(self.n_societes)]

    def _construire(self):
        n = len(self.jours)
        cours = {}
        # Pays : rendement mensuel lié à un « facteur qualité » persistant (momentum prédictif)
        self.qualite = {}
        for c in self.pays_test():
            q = np.cumsum(self.r.normal(0, 0.02, n)) * 0.02
            self.qualite[c] = pd.Series(q, index=self.jours)
            r = self.r.normal(0.0002, 0.012, n) + 0.0004 * np.sign(pd.Series(q).rolling(250, min_periods=20).mean().fillna(0).to_numpy())
            cours[f"ETF{c}"] = 50 * np.exp(np.cumsum(r))
            cours[f"FX{c}=X"] = 3 * np.exp(np.cumsum(self.r.normal(0, 0.004, n)))
        for s in self.societes_test():
            r = self.r.normal(0.0003, 0.018, n)
            cours[s["ticker"]] = 30 * np.exp(np.cumsum(r))
        for s in ("ACWI", "SPY", "XLK", "XLV", "XLI", "XLE", "XLP", "XLU", "XLB", "XLY", "XLF", "USO", "GLD"):
            cours[s] = 100 * np.exp(np.cumsum(self.r.normal(0.0003, 0.01, n)))
        for s in ("CL=F", "GC=F", "SI=F", "HG=F", "NG=F", "ZW=F", "ZC=F", "ZS=F", "SB=F", "KC=F"):
            cours[s] = 60 * np.exp(np.cumsum(self.r.normal(0.0001, 0.017, n)))
        self._cours = pd.DataFrame(cours, index=self.jours)
        # Sociétés : la marge opérationnelle prédit (faiblement) le rendement de l'année suivante
        self.marges = {}
        for s in self.societes_test():
            m = self.r.uniform(2, 30)
            self.marges[s["ticker"]] = m
            ajout = np.where(self.jours.year >= 2010, (m - 16) * 0.00004, 0)
            self._cours[s["ticker"]] = self._cours[s["ticker"]] * np.exp(np.cumsum(ajout))

    def cours(self, symboles: list[str], debut: str) -> dict[str, pd.DataFrame]:
        if self._cours is None:
            self._construire()
        cols = [s for s in symboles if s in self._cours.columns]
        c = self._cours[cols]
        div = pd.DataFrame(0.0, index=c.index, columns=cols)
        div[(div.index.month % 3 == 0) & (div.index.day >= 25)] = 0
        for s in cols:  # un dividende trimestriel par ETF pays (rendement variable selon le pays)
            if s.startswith("ETF"):
                taux = 0.005 + 0.01 * (ord(s[-1]) % 5) / 5
                fins = c.index[c.index.is_month_end | (c.index.to_series().shift(-1).dt.month != c.index.month)]
                fins = [d for d in fins if d.month % 3 == 0]
                div.loc[fins, s] = c.loc[fins, s] * taux / 4
        return {"ajuste": c, "cloture": c, "dividendes": div, "divisions": pd.DataFrame(0.0, index=c.index, columns=cols)}

    def fred(self, serie: str) -> pd.Series:
        idx = pd.bdate_range(self.jours[0], self.jours[-1])
        if serie == "VIXCLS":
            v = 18 + 6 * np.sin(np.arange(len(idx)) / 300) + self.r.normal(0, 2, len(idx))
            return pd.Series(v, index=idx)
        if serie == "CPIAUCSL":
            m = pd.date_range(self.jours[0], self.jours[-1], freq="ME")
            return pd.Series(200 * 1.002 ** np.arange(len(m)), index=m)
        return pd.Series(dtype=float)

    def _mensuelle(self, base: float, ecart: float) -> pd.Series:
        m = pd.date_range(self.jours[0], self.jours[-1], freq="ME")
        return pd.Series(base + np.cumsum(self.r.normal(0, ecart, len(m))) * 0.3, index=m)

    def ocde_cli(self, iso3: list[str], debut: str) -> dict[str, pd.Series]:
        return {z: self._mensuelle(100, 0.3) for z in iso3}

    def ocde_inflation(self, iso3: list[str], debut: str) -> dict[str, pd.Series]:
        return {z: self._mensuelle(2.5, 0.3) for z in iso3}

    def bis_taux(self, codes: list[str], debut: str) -> dict[str, pd.Series]:
        return {z: self._mensuelle(2.0, 0.2).clip(lower=0) for z in codes}

    def fmi_croissance(self) -> dict[str, dict[int, float]]:
        return {v["iso3"]: {a: float(self.r.normal(2.5, 1.5)) for a in range(2005, 2027)} for v in self.pays_test().values()}

    def sec_ciks(self) -> dict[str, str]:
        return {s["ticker"]: s["cik"] for s in self.societes_test()}

    def sec_faits(self, cik: str) -> dict | None:
        s = next(x for x in self.societes_test() if x["cik"] == cik)
        marge = self.marges[s["ticker"]] if self._cours is not None else (self._construire() or self.marges[s["ticker"]])
        faits = {k: [] for k in ("ca", "resultat_net", "ebit", "cfo", "capex", "marge_brute", "actifs", "actifs_courants",
                                 "passifs_courants", "capitaux_propres", "tresorerie", "dette_lt", "actions", "benefices_non_distribues",
                                 "passifs_totaux", "amortissements", "interets")}
        ca = 1000.0
        for annee in range(2006, 2026):
            ca *= 1 + self.r.normal(0.05, 0.08)
            fin, depot = f"{annee}-12-31", f"{annee + 1}-02-{self.r.integers(10, 28):02d}"
            ebit = ca * marge / 100
            valeurs = {"ca": ca, "ebit": ebit, "resultat_net": ebit * 0.75, "cfo": ebit * 0.9, "capex": ca * 0.04, "marge_brute": ca * 0.4,
                       "actifs": ca * 1.2, "actifs_courants": ca * 0.5, "passifs_courants": ca * 0.3, "capitaux_propres": ca * 0.6,
                       "tresorerie": ca * 0.1, "dette_lt": ca * 0.3, "actions": 100.0, "benefices_non_distribues": ca * 0.3,
                       "passifs_totaux": ca * 0.6, "amortissements": ca * 0.03, "interets": ca * 0.01}
            for k, v in valeurs.items():
                faits[k].append([0, fin, depot, v])
        return {"faits": faits, "actions_circulation": [[f"{a}-02-15", 100.0] for a in range(2007, 2027)]}

    def cftc(self, codes: list[str], depuis: str) -> dict[str, pd.DataFrame]:
        sem = pd.date_range("2006-06-13", self.jours[-1], freq="W-TUE")
        return {c: pd.DataFrame({"date": sem.strftime("%Y-%m-%d"), "long": 1e5 + np.cumsum(self.r.normal(0, 3e3, len(sem))),
                                 "short": 6e4 + np.cumsum(self.r.normal(0, 2e3, len(sem))), "oi": 5e5}) for c in codes}

    def eia_xls(self, url: str) -> pd.Series:
        sem = pd.date_range("2004-01-02", self.jours[-1], freq="W-FRI")
        saison = 20 * np.sin(2 * np.pi * sem.dayofyear / 365)
        return pd.Series(400 + saison + np.cumsum(self.r.normal(0, 2, len(sem))), index=sem)
