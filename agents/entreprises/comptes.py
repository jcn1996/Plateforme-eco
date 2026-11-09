"""
Comptes des sociétés : yfinance partout, sources officielles quand elles existent.

- yfinance : cours (13 mois), états financiers annuels (4 exercices) et trimestriels, devise, secteur.
- SEC (États-Unis) : API XBRL companyfacts + flux submissions (nouvelles publications).
  User-Agent lu dans SEC_USER_AGENT ; au plus 8 requêtes par seconde ; sans ce secret, source ignorée.
- ESEF (Union européenne, Royaume-Uni) : rapports annuels sur filings.xbrl.org (LEI trouvé via GLEIF).
- EDINET (Japon, clé EDINET_API_KEY) et DART (Corée, clé DART_API_KEY) : facultatifs.

Toutes les valeurs sont ramenées au même format (dictionnaire par exercice), dans la devise des comptes.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import unicodedata
import zipfile
from datetime import date, timedelta

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource

LOG = journal("agent-entreprises")

# Lignes yfinance recherchées, dans l'ordre de préférence
LIGNES = {
    "ca": ["Total Revenue", "Operating Revenue"],
    "ebit": ["Operating Income", "EBIT"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "resultat_net": ["Net Income Common Stockholders", "Net Income", "Net Income From Continuing Operation Net Minority Interest"],
    "interets": ["Interest Expense", "Interest Expense Non Operating"],
    "marge_brute": ["Gross Profit"],
    "taux_impot": ["Tax Rate For Calcs"],
    "charges_exploitation": ["Non Interest Expense", "Total Expenses", "Operating Expense"],
    "primes": ["Total Premiums Earned", "Net Premiums Written"],
    "cfo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure"],
    "fcf": ["Free Cash Flow"],
    "dette_totale": ["Total Debt"],
    "tresorerie": ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"],
    "capitaux_propres": ["Stockholders Equity", "Common Stock Equity"],
    "actifs": ["Total Assets"],
    "actifs_courants": ["Current Assets"],
    "passifs_courants": ["Current Liabilities"],
    "dette_lt": ["Long Term Debt"],
    "actions": ["Ordinary Shares Number", "Share Issued"],
    "creances": ["Accounts Receivable", "Receivables"],
    "stocks": ["Inventory"],
    "capital_investi": ["Invested Capital"],
    "depots": ["Total Deposits", "Deposits"],
    # Analyse approfondie (financier.py)
    "benefices_non_distribues": ["Retained Earnings"],
    "passifs_totaux": ["Total Liabilities Net Minority Interest"],
    "goodwill": ["Goodwill"],
    "goodwill_incorporels": ["Goodwill And Other Intangible Assets"],
    "amortissements": ["Depreciation And Amortization", "Reconciled Depreciation", "Depreciation Amortization Depletion"],
    "rd": ["Research And Development"],
    "dividendes": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "rachats": ["Repurchase Of Capital Stock", "Common Stock Payments"],
    "emissions": ["Issuance Of Capital Stock", "Common Stock Issuance"],
    "cout_ventes": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "fournisseurs": ["Accounts Payable", "Payables"],
    "sga": ["Selling General And Administration"],
    "immobilisations": ["Net PPE"],
}
DEVISES_CENTIEMES = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ZAc": ("ZAR", 100), "ILA": ("ILS", 100)}


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _exercices(*tableaux) -> list[dict]:
    """DataFrames yfinance (lignes = postes, colonnes = dates de clôture) → [{fin, poste: valeur}] du plus récent au plus ancien."""
    par_date = {}
    for df in tableaux:
        if df is None or getattr(df, "empty", True):
            continue
        for col in df.columns:
            fin = str(col)[:10]
            e = par_date.setdefault(fin, {"fin": fin})
            for cle, lignes in LIGNES.items():
                if e.get(cle) is not None:
                    continue
                for l in lignes:
                    if l in df.index:
                        v = _num(df.at[l, col])
                        if v is not None:
                            e[cle] = v
                            break
    res = []
    for fin, e in sorted(par_date.items(), reverse=True):
        if e.get("capex") is not None:
            e["capex"] = abs(e["capex"])
        if e.get("interets") is not None:
            e["interets"] = abs(e["interets"])
        if e.get("fcf") is None and e.get("cfo") is not None and e.get("capex") is not None:
            e["fcf"] = e["cfo"] - e["capex"]
        if len(e) > 3:  # un exercice avec quelques postes seulement est ignoré
            res.append(e)
    return res


def devise_majeure(devise: str | None) -> tuple[str | None, float]:
    if devise in DEVISES_CENTIEMES:
        return DEVISES_CENTIEMES[devise]
    return devise, 1.0


class Yahoo:
    """Accès yfinance (importé à la demande : inutile en mode test)."""

    def __init__(self, pause: float = 0.3):
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        self.yf = yf
        self.pause = pause

    def societe(self, ticker: str) -> dict:
        t = self.yf.Ticker(ticker)
        h = t.history(period="13mo", interval="1d", auto_adjust=True)
        meta = t.history_metadata or {}
        if h.empty:
            raise ErreurSource(f"Yahoo : aucun cours pour {ticker}")
        cours = [(i.strftime("%Y-%m-%d"), float(c), float(v or 0)) for i, c, v in zip(h.index, h["Close"], h["Volume"]) if c == c]
        annuel = _exercices(t.income_stmt, t.balance_sheet, t.cashflow)[:5]  # 5 exercices : moyennes et régularité sur 5 ans
        trimestres = _exercices(t.quarterly_income_stmt, t.quarterly_cashflow)[:8]
        info = {}
        try:  # .info peut être refusé (401) selon le réseau : on s'en passe
            brut = t.info or {}
            info = {k: brut.get(k) for k in ("longName", "shortName", "sector", "industry", "financialCurrency", "currency",
                                               "marketCap", "sharesOutstanding", "trailingPE", "enterpriseToEbitda", "country",
                                               "numberOfAnalystOpinions", "heldPercentInsiders", "beta")}
        except Exception as e:
            LOG.debug("info Yahoo indisponible pour %s : %s", ticker, str(e)[:80])
        devise_comptes = info.get("financialCurrency")
        if not devise_comptes:
            try:
                devise_comptes = self.devise_comptes(t, ticker)
            except Exception as e:
                LOG.debug("devise des comptes inconnue pour %s : %s", ticker, str(e)[:80])
        time.sleep(self.pause)
        return {"cours": cours, "devise_cours": meta.get("currency") or info.get("currency"), "devise_comptes": devise_comptes,
                "nom": meta.get("longName") or info.get("longName") or meta.get("shortName"),
                "annuel": annuel, "trimestriel": trimestres, "info": info}

    def analystes(self, ticker: str) -> dict | None:
        """Estimations des analystes, révisions, surprises et objectifs de cours : une seule requête quoteSummary
        (modules earningsTrend, earningsHistory, financialData) ; à défaut, propriétés publiques de yfinance."""
        t = self.yf.Ticker(ticker)
        modules = ["earningsTrend", "earningsHistory", "financialData"]
        try:
            d = t._analysis._fetch(modules)
            r = ((d or {}).get("quoteSummary") or {}).get("result") or []
            return r[0] if r else None
        except AttributeError:  # API interne de yfinance modifiée : propriétés publiques (plusieurs requêtes)
            return self._analystes_public(t)

    @staticmethod
    def _analystes_public(t) -> dict:
        def lignes(df):
            return {} if df is None or getattr(df, "empty", True) else {str(i): r.to_dict() for i, r in df.iterrows()}
        tendance, revisions, estimations = lignes(t.eps_trend), lignes(t.eps_revisions), lignes(t.earnings_estimate)
        trend = [{"period": p, "epsTrend": {k: v for k, v in tendance.get(p, {}).items() if k != "currency"},
                  "epsRevisions": {k: v for k, v in revisions.get(p, {}).items() if k != "currency"},
                  "earningsEstimate": {"numberOfAnalysts": estimations.get(p, {}).get("numberOfAnalysts")}} for p in tendance]
        hist = [{"quarter": q[:10], **{k: v for k, v in r.items()}} for q, r in lignes(t.earnings_history).items()]
        o = t.analyst_price_targets or {}
        fd = {"currentPrice": o.get("current"), "targetMeanPrice": o.get("mean"), "targetHighPrice": o.get("high"),
              "targetLowPrice": o.get("low"), "targetMedianPrice": o.get("median")}
        return {"earningsTrend": {"trend": trend}, "earningsHistory": {"history": hist}, "financialData": fd}

    def secteur(self, ticker: str) -> tuple[str | None, str | None]:
        """Secteur et industrie selon la recherche Yahoo (classification Yahoo, proche de GICS), quand
        ni le fichier de composition ni .info ne les donnent."""
        r = self.yf.Search(ticker, max_results=5, news_count=0)
        for q in r.quotes or []:
            if q.get("symbol", "").upper() == ticker.upper():
                return q.get("sector") or q.get("sectorDisp"), q.get("industry") or q.get("industryDisp")
        return None, None

    @staticmethod
    def devise_comptes(t, ticker: str) -> str | None:
        """Devise des états financiers (champ currencyCode du flux de séries financières de Yahoo,
        celui-là même qui fournit les comptes) : indispensable pour les sociétés qui publient en dollars
        mais cotent en devise locale (BHP, Shell…)."""
        maintenant = int(time.time())
        url = f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{ticker}"
        j = t._data.get_raw_json(url, params={"symbol": ticker, "type": "annualTotalRevenue,annualNetIncome",
                                              "period1": maintenant - 5 * 365 * 86400, "period2": maintenant})
        for r in j.get("timeseries", {}).get("result", []):
            for cle, points in r.items():
                if cle.startswith("annual") and isinstance(points, list):
                    for p in reversed(points):
                        if p and p.get("currencyCode"):
                            return p["currencyCode"]
        return None

    def cours_groupes(self, tickers: list[str], periode: str = "13mo") -> dict[str, list]:
        """Clôtures et volumes de nombreux tickers en peu de requêtes (mode quotidien)."""
        res = {}
        for k in range(0, len(tickers), 100):
            lot = tickers[k:k + 100]
            brut = self.yf.download(lot, period=periode, interval="1d", progress=False, auto_adjust=True, threads=True, group_by="column")
            if brut.empty:
                continue
            for s in lot:
                try:
                    c, v = brut["Close"][s], brut["Volume"][s]
                except KeyError:
                    continue
                points = [(i.strftime("%Y-%m-%d"), float(x), float(y or 0)) for i, x, y in zip(c.index, c, v) if x == x]
                if points:
                    res[s] = points
            time.sleep(1)
        return res

    def taux_change(self, devises: set[str]) -> dict[str, float]:
        """Taux pour convertir 1 unité de devise en dollars."""
        res = {"USD": 1.0}
        paires = {d: f"{d}USD=X" for d in devises if d and d != "USD"}
        if not paires:
            return res
        brut = self.yf.download(list(paires.values()), period="5d", interval="1d", progress=False, auto_adjust=True)["Close"]
        for d, p in paires.items():
            try:
                serie = (brut[p] if p in brut else brut).dropna()
                if len(serie):
                    res[d] = float(serie.iloc[-1])
            except (KeyError, AttributeError):
                continue
        return res


# ------------------------------------------------------------------ SEC (États-Unis)

class Sec:
    CONCEPTS = {
        "ca": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenuesNetOfInterestExpense"],
        "resultat_net": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
        "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
        "ebit": ["OperatingIncomeLoss"],
        "marge_brute": ["GrossProfit"],
    }

    def __init__(self, telechargeur, requetes_par_seconde: float = 8):
        self.ua = os.environ.get("SEC_USER_AGENT", "").strip()
        self.t = telechargeur
        self.intervalle = 1 / requetes_par_seconde
        self._dernier = 0.0
        self._ciks = None

    @property
    def actif(self) -> bool:
        return bool(self.ua)

    def _get(self, url: str):
        if not self.actif:
            raise ErreurSource("secret SEC_USER_AGENT absent : source ignorée")
        attente = self.intervalle - (time.monotonic() - self._dernier)
        if attente > 0:
            time.sleep(attente)
        self._dernier = time.monotonic()
        return self.t.json(url, entetes={"User-Agent": self.ua, "Accept-Encoding": "gzip, deflate"})

    def cik(self, ticker: str) -> str | None:
        if self._ciks is None:
            d = self._get("https://www.sec.gov/files/company_tickers.json")
            self._ciks = {v["ticker"].upper().replace(".", "-"): str(v["cik_str"]).zfill(10) for v in d.values()}
        return self._ciks.get(ticker.upper())

    def publications(self, cik: str) -> list[dict]:
        """Dernières publications 10-K / 10-Q / 20-F / 40-F (date et lien)."""
        d = self._get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        r = d.get("filings", {}).get("recent", {})
        res = []
        for form, date_dep, acc, doc, periode in zip(r.get("form", []), r.get("filingDate", []), r.get("accessionNumber", []),
                                                     r.get("primaryDocument", []), r.get("reportDate", [])):
            if form in ("10-K", "10-Q", "20-F", "40-F", "10-K/A"):
                res.append({"formulaire": form, "date": date_dep, "periode": periode,
                            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"})
        return res

    def resultats_8k(self, cik: str, fenetre_jours: int, aujourdhui: date) -> list[dict]:
        """Dépôts 8-K « Item 2.02 Results of Operations » (communiqués de résultats) des `fenetre_jours` derniers jours,
        du plus récent au plus ancien. Même flux submissions que publications() (réponse en cache)."""
        d = self._get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        r = d.get("filings", {}).get("recent", {})
        limite = (aujourdhui - timedelta(days=fenetre_jours)).isoformat()
        res = []
        for form, date_dep, acc, items, periode in zip(r.get("form", []), r.get("filingDate", []), r.get("accessionNumber", []),
                                                       r.get("items", []), r.get("reportDate", [])):
            if form not in ("8-K", "8-K/A") or "2.02" not in [i.strip() for i in (items or "").split(",")] or date_dep < limite:
                continue
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
            res.append({"cik": cik, "accession": acc, "date": date_dep, "formulaire": form, "periode": periode or None,
                        "url_depot": f"{base}/{acc}-index.htm", "base": base})
        return sorted(res, key=lambda x: x["date"], reverse=True)

    def pieces_jointes(self, depot: dict) -> list[dict]:
        """Pièces d'un dépôt (type et lien), lues dans sa page d'index."""
        h = self._texte(depot["url_depot"])
        res = []
        for ligne in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S | re.I):
            cellules = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", ligne, re.S | re.I)]
            lien = re.search(r'href="([^"]+\.(?:htm|html|txt))"', ligne, re.I)
            if len(cellules) >= 4 and lien and not lien.group(1).startswith("/ix?"):
                url = lien.group(1)
                res.append({"type": cellules[3], "url": url if url.startswith("http") else f"https://www.sec.gov{url}"})
        return res

    def document(self, url: str) -> str:
        return self._texte(url)

    def _texte(self, url: str) -> str:
        if not self.actif:
            raise ErreurSource("secret SEC_USER_AGENT absent : source ignorée")
        attente = self.intervalle - (time.monotonic() - self._dernier)
        if attente > 0:
            time.sleep(attente)
        self._dernier = time.monotonic()
        return self.t.texte(url, entetes={"User-Agent": self.ua, "Accept-Encoding": "gzip, deflate"})

    def comptes(self, cik: str) -> list[dict]:
        """Exercices annuels (10-K) : chiffre d'affaires, résultat net, flux de trésorerie d'exploitation, résultat opérationnel."""
        d = self._get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        gaap = d.get("facts", {}).get("us-gaap", {})
        par_fin = {}
        for cle, concepts in self.CONCEPTS.items():
            for c in concepts:
                points = (gaap.get(c) or {}).get("units", {}).get("USD", [])
                annuels = [p for p in points if p.get("form") in ("10-K", "10-K/A") and p.get("start") and p.get("end")
                           and 330 <= (date.fromisoformat(p["end"]) - date.fromisoformat(p["start"])).days <= 400]
                if not annuels:
                    continue
                for p in sorted(annuels, key=lambda p: p.get("filed", "")):  # la dernière publication l'emporte
                    e = par_fin.setdefault(p["end"], {"fin": p["end"], "devise": "USD"})
                    if cle not in e or e.get(f"_{cle}") == c:
                        e[cle] = float(p["val"])
                        e[f"_{cle}"] = c
                break
        res = []
        for fin, e in sorted(par_fin.items(), reverse=True)[:6]:  # 6 exercices : moyennes et régularité sur 5 ans
            res.append({k: v for k, v in e.items() if not k.startswith("_")})
        return res


# ------------------------------------------------------------------ ESEF (filings.xbrl.org)

def _mots(nom: str) -> set[str]:
    t = "".join(c for c in unicodedata.normalize("NFD", nom.lower()) if unicodedata.category(c) != "Mn")
    vides = {"sa", "se", "ag", "nv", "plc", "spa", "ab", "the", "group", "holding", "holdings", "de", "la", "et", "and", "co",
             "company", "societe", "europeenne", "asa", "oyj", "publ", "bv", "ltd", "limited", "inc", "corp", "corporation",
             # formes juridiques longues (ex. « Hermès International Société en commandite par actions »)
             "en", "commandite", "par", "actions", "anonyme", "sca", "kgaa", "aktiengesellschaft", "societas", "europaea", "nv"}
    return {m for m in re.findall(r"[a-z0-9]+", t) if m not in vides and len(m) > 1}


class Esef:
    PAYS = {"FR", "DE", "IT", "ES", "NL", "SE", "PL", "GB"}
    CONCEPTS = {
        "ca": ["ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers"],
        "resultat_net": ["ifrs-full:ProfitLossAttributableToOwnersOfParent", "ifrs-full:ProfitLoss"],
        "cfo": ["ifrs-full:CashFlowsFromUsedInOperatingActivities"],
    }

    def __init__(self, telechargeur):
        self.t = telechargeur

    def lei(self, nom: str, pays: str) -> str | None:
        """LEI d'une société via GLEIF (recherche par nom, même pays, au moins la moitié des mots en commun)."""
        cibles = _mots(nom)
        if not cibles:
            return None
        # Nom complet, puis ses premiers mots significatifs (les noms Yahoo sont souvent plus longs que les noms légaux)
        requetes = [nom, " ".join(sorted(cibles, key=nom.lower().find)[:2])]
        for q in dict.fromkeys(requetes):
            d = self.t.json("https://api.gleif.org/api/v1/lei-records",
                            params={"filter[fulltext]": q, "filter[entity.legalAddress.country]": pays, "page[size]": "10"})
            meilleur, score = None, 0.0
            for r in d.get("data", []):
                ent = r["attributes"]["entity"]
                if ent.get("status") != "ACTIVE":
                    continue
                m = _mots(ent["legalName"]["name"])
                s = len(cibles & m) / max(1, len(cibles), len(m))
                if s > score:
                    meilleur, score = r["id"], s
            if score >= 0.6:
                return meilleur
        return None

    def dernier_rapport(self, lei: str) -> dict | None:
        if not lei or not re.fullmatch(r"[A-Z0-9]{20}", lei):
            return None
        d = self.t.json("https://filings.xbrl.org/api/filings",
                        params={"filter[entity.identifier]": lei, "sort": "-period_end", "page[size]": "5"})
        for f in d.get("data", []):
            a = f["attributes"]
            if a.get("json_url"):
                return {"fin": a["period_end"], "json_url": "https://filings.xbrl.org" + a["json_url"],
                        "url": "https://filings.xbrl.org" + (a.get("viewer_url") or a.get("report_url") or ""),
                        "publie": (a.get("published") or a.get("date_added") or "")[:10]}
        return None

    def comptes(self, rapport: dict) -> dict:
        d = self.t.json(rapport["json_url"])
        fin = date.fromisoformat(rapport["fin"])
        res = {"fin": rapport["fin"], "url": rapport["url"], "publie": rapport["publie"]}
        for cle, concepts in self.CONCEPTS.items():
            for c in concepts:
                for fait in d.get("facts", {}).values():
                    dim = fait.get("dimensions", {})
                    if dim.get("concept") != c or set(dim) - {"concept", "entity", "period", "unit"}:
                        continue
                    periode = dim.get("period", "")
                    if "/" not in periode:
                        continue
                    debut, fin_p = (date.fromisoformat(x[:10]) for x in periode.split("/"))
                    if abs((fin_p - timedelta(days=1) - fin).days) <= 2 and 330 <= (fin_p - debut).days <= 400:
                        res[cle] = float(fait["value"])
                        res["devise"] = dim.get("unit", "").replace("iso4217:", "") or None
                        break
                if cle in res:
                    break
        return res


# ------------------------------------------------------------------ EDINET (Japon) et DART (Corée), facultatifs

class Edinet:
    URL = "https://api.edinet-fsa.go.jp/api/v2"
    ELEMENTS = {
        "ca": ["jpcrp_cor:NetSalesSummaryOfBusinessResults", "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults", "jpcrp_cor:OperatingRevenue1SummaryOfBusinessResults"],
        "resultat_net": ["jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults", "jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults", "jpcrp_cor:NetIncomeLossSummaryOfBusinessResults"],
        "cfo": ["jpcrp_cor:NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults", "jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults"],
    }

    def __init__(self, telechargeur):
        self.cle = os.environ.get("EDINET_API_KEY", "").strip()
        self.t = telechargeur
        self._index = None

    @property
    def actif(self) -> bool:
        return bool(self.cle)

    def index(self, jours: int = 400) -> dict[str, dict]:
        """Code de valeur (4 chiffres) → dernier rapport annuel (docTypeCode 120), sur les `jours` derniers jours."""
        if self._index is not None:
            return self._index
        idx = {}
        for k in range(jours):
            j = (date.today() - timedelta(days=k)).isoformat()
            try:
                d = self.t.json(f"{self.URL}/documents.json", params={"date": j, "type": "2", "Subscription-Key": self.cle})
            except ErreurSource:
                continue
            for doc in d.get("results") or []:
                code = (doc.get("secCode") or "")[:4]
                if doc.get("docTypeCode") == "120" and code and code not in idx:
                    idx[code] = {"doc": doc["docID"], "fin": doc.get("periodEnd"), "publie": j}
        self._index = idx
        return idx

    def comptes(self, code: str) -> dict | None:
        doc = self.index().get(code)
        if not doc:
            return None
        r = self.t.session.get(f"{self.URL}/documents/{doc['doc']}", params={"type": "5", "Subscription-Key": self.cle}, timeout=60)
        r.raise_for_status()
        res = {"fin": doc["fin"], "devise": "JPY", "publie": doc["publie"],
               "url": f"https://disclosure2.edinet-fsa.go.jp/WEEK0010.aspx?docID={doc['doc']}"}
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for nom in z.namelist():
                if not nom.endswith(".csv") or "jpcrp" not in nom:
                    continue
                texte = z.read(nom).decode("utf-16", errors="ignore")
                for ligne in texte.splitlines()[1:]:
                    col = [c.strip('"') for c in ligne.split("\t")]
                    if len(col) < 9 or col[2] != "CurrentYearDuration":
                        continue
                    for cle, elements in self.ELEMENTS.items():
                        if col[0] in elements and cle not in res and _num(col[8]) is not None:
                            res[cle] = _num(col[8])
        return res if "ca" in res else None


class Dart:
    URL = "https://opendart.fss.or.kr/api"

    def __init__(self, telechargeur):
        self.cle = os.environ.get("DART_API_KEY", "").strip()
        self.t = telechargeur
        self._codes = None

    @property
    def actif(self) -> bool:
        return bool(self.cle)

    def code(self, ticker: str) -> str | None:
        if self._codes is None:
            r = self.t.session.get(f"{self.URL}/corpCode.xml", params={"crtfc_key": self.cle}, timeout=60)
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                xml = z.read(z.namelist()[0]).decode("utf-8", errors="ignore")
            self._codes = {s: c for c, s in re.findall(r"<corp_code>(\d+)</corp_code>.*?<stock_code>(\d{6})</stock_code>", xml, re.S)}
        return self._codes.get(ticker.split(".")[0])

    def comptes(self, ticker: str) -> dict | None:
        corp = self.code(ticker)
        if not corp:
            return None
        for annee in (date.today().year - 1, date.today().year - 2):
            d = self.t.json(f"{self.URL}/fnlttSinglAcnt.json",
                            params={"crtfc_key": self.cle, "corp_code": corp, "bsns_year": str(annee), "reprt_code": "11011"})
            lignes = [l for l in d.get("list", []) if l.get("fs_div") == "CFS"] or d.get("list", [])
            if not lignes:
                continue
            res = {"fin": f"{annee}-12-31", "devise": "KRW", "publie": None,
                   "url": f"https://dart.fss.or.kr/dsab007/main.do?rcpNo={lignes[0].get('rcept_no', '')}"}
            for l in lignes:
                v = _num(str(l.get("thstrm_amount", "")).replace(",", ""))
                nom = l.get("account_nm", "")
                if v is None:
                    continue
                if nom in ("매출액", "수익(매출액)", "영업수익") and "ca" not in res:
                    res["ca"] = v
                elif nom in ("당기순이익", "당기순이익(손실)", "지배기업 소유주지분 순이익") and "resultat_net" not in res:
                    res["resultat_net"] = v
            if "ca" in res:
                return res
        return None


def exercice_correspondant(annuel: list[dict], fin: str, tolerance_jours: int = 45) -> dict | None:
    """Exercice yfinance qui correspond à une date de clôture officielle."""
    cible = date.fromisoformat(fin[:10])
    for e in annuel:
        if abs((date.fromisoformat(e["fin"]) - cible).days) <= tolerance_jours:
            return e
    return None


def verifier(officiel: dict, annuel: list[dict], seuil_pct: float) -> dict:
    """Compare chiffre d'affaires et résultat net officiels et yfinance sur le même exercice."""
    e = exercice_correspondant(annuel, officiel["fin"]) if officiel.get("fin") else None
    if e is None:
        return {"statut": "non comparable", "detail": "exercice officiel absent des données Yahoo"}
    ecarts = {}
    for cle in ("ca", "resultat_net"):
        a, b = officiel.get(cle), e.get(cle)
        if a and b:
            ecarts[cle] = round((b / a - 1) * 100, 1)
    if not ecarts:
        return {"statut": "non comparable", "detail": "postes absents"}
    hors = {k: v for k, v in ecarts.items() if abs(v) > seuil_pct}
    return {"statut": "divergent" if hors else "concordant", "ecarts_pct": ecarts, "exercice": officiel["fin"]}


def json_compact(o) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))
