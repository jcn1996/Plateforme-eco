"""
Sources de l'agent données alternatives (toutes gratuites ; clés facultatives).

Chaque indicateur de config.json désigne une source (« source ») et ses paramètres. Le fournisseur
renvoie une série [(date AAAA-MM-JJ, valeur)] et un court détail ; None si la source n'est pas
configurée (clé ou adresse absente : la source est ignorée, ni comptée ni signalée).

- destatis_maut : Destatis, indice quotidien des kilomètres parcourus par les poids lourds sur les
  autoroutes allemandes (Lkw-Maut-Fahrleistungsindex), fichier xlsx du rapport statistique hebdomadaire ;
  série corrigée des variations saisonnières et des jours ouvrés (KSB, expérimentale).
- fred : FRED (Réserve fédérale de Saint-Louis) — API si FRED_API_KEY existe, sinon fichier CSV public.
- nbs : Bureau national des statistiques de Chine, API publique de data.stats.gov.cn (base mensuelle
  « hgyd ») ; souvent inaccessible depuis l'étranger : DBnomics en secours (« secours » en config).
- dbnomics : DBnomics (statistiques officielles : NBS, OMC…).
- douanes_taiwan : Administration des douanes de Taïwan, fichier CSV ouvert « 海關進出口貿易統計 »
  (exportations mensuelles, converties en milliards de dollars taïwanais, depuis 2014).
- usgs_ciment : USGS, « Mineral Industry Surveys — Cement » (PDF mensuels : expéditions de ciment).
- drewry : Drewry World Container Index (page publique hebdomadaire, US$ par conteneur de 40 pieds).
- yahoo : Yahoo Finance via yfinance (ex. ETF BDRY, approximation de l'indice Baltic Dry).
- indeed : Indeed Hiring Lab, offres d'emploi par pays (dépôt public GitHub hiring-lab/job_postings_tracker).
- tsa : TSA, passagers contrôlés dans les aéroports américains (page publique).
- eia : EIA (API v2, clé EIA_API_KEY) : demande d'électricité quotidienne des 48 États contigus.
- entsoe : ENTSO-E Transparency Platform (clé gratuite ENTSOE_API_KEY) : charge électrique réalisée.
- csv_url : fichier CSV « date,pays,indicateur,valeur » dont l'adresse est dans une variable
  d'environnement (agrégats satellitaires préparés hors de l'agent, exportations coréennes des
  20 premiers jours, commandes à l'export de Taïwan) ; sans adresse : source ignorée.
- Attention du public : Wikipédia (API Wikimedia des consultations, sans clé) et Google Trends
  (bibliothèque pytrends, non officielle : une seule requête par mot, échec toléré).

Mode test : FournisseurTest relit agents/donnees_alternatives/tests/donnees/<clé>.json.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource, Telechargeur

LOG = journal("agent-donnees-alternatives")

DESTATIS_PAGE = ("https://www.destatis.de/DE/Themen/Branchen-Unternehmen/Industrie-Verarbeitendes-Gewerbe/Publikationen/"
                 "Downloads-Konjunktur/statistischer-bericht-lkw-maut-fahrleistungsindex-5421901.html")
DESTATIS_XLSX = ("https://www.destatis.de/DE/Themen/Branchen-Unternehmen/Industrie-Verarbeitendes-Gewerbe/Publikationen/"
                 "Downloads-Konjunktur/statistischer-bericht-lkw-maut-fahrleistungsindex-5421901.xlsx?__blob=publicationFile")
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
DBNOMICS = "https://api.db.nomics.world/v22/series/{fournisseur}/{jeu}/{serie}"
NBS = "https://data.stats.gov.cn/easyquery.htm"
DOUANES_TAIWAN = "https://opendata.customs.gov.tw/data/6053/csv.csv"
USGS_PAGE = "https://www.usgs.gov/centers/national-minerals-information-center/cement-statistics-and-information"
DREWRY = "https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry"
INDEED = "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/{pays}/aggregate_job_postings_{pays}.csv"
TSA = "https://www.tsa.gov/travel/passenger-volumes"
EIA = "https://api.eia.gov/v2/electricity/rto/daily-region-data/data/"
ENTSOE = "https://web-api.tp.entsoe.eu/api"
WIKI_RECHERCHE = "https://en.wikipedia.org/w/api.php"
WIKI_VUES = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{article}/daily/{debut}/{fin}"
AGENT_HTTP = "SalleDeControle-AgentDonneesAlternatives/1.0 (+https://github.com/jcn1996/Plateforme-eco)"

Serie = list[tuple[str, float]]
MOIS_EN = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}
MOIS_COURTS = {m[:3]: i for m, i in MOIS_EN.items()}


def flottant(v) -> float | None:
    try:
        x = float(str(v).replace(",", "").replace(" ", "").strip())
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _propre(points) -> Serie:
    vus = {}
    for d, v in points:
        x = flottant(v)
        if d and x is not None:
            vus[str(d)[:10]] = x
    return sorted(vus.items())


# ------------------------------------------------------------------ lecture des formats (testées seules)

def lire_destatis(contenu: bytes) -> Serie:
    """Feuille « csv-42191-b01 » du rapport : lignes (…, Datum, …, Saisonbereinigung, Indexwert) ; on garde KSB."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
    feuille = next((n for n in wb.sheetnames if n.startswith("csv-")), None)
    if not feuille:
        raise ErreurSource("Destatis : feuille de données introuvable")
    points = []
    for r in wb[feuille].iter_rows(values_only=True):
        if len(r) < 7 or not isinstance(r[2], datetime):
            continue
        if "KSB" in str(r[5]):
            points.append((r[2].date().isoformat(), r[6]))
    return _propre(points)


def lire_csv_fred(texte: str) -> Serie:
    lignes = list(csv.reader(io.StringIO(texte)))
    return _propre((l[0], l[1]) for l in lignes[1:] if len(l) >= 2)


def lire_dbnomics(objet: dict) -> Serie:
    docs = ((objet or {}).get("series") or {}).get("docs") or []
    if not docs:
        raise ErreurSource("DBnomics : série introuvable")
    s = docs[0]
    return _propre((f"{p}-01" if len(str(p)) == 7 else p, v) for p, v in zip(s.get("period", []), s.get("value", [])) if v != "NA")


def lire_nbs(objet: dict, code: str) -> Serie:
    """Réponse de data.stats.gov.cn (m=QueryData) : nœuds « zb.<code>_sj.<AAAAMM> » → [(AAAA-MM-01, valeur)]."""
    rd = (objet or {}).get("returndata") or {}
    if (objet or {}).get("returncode") not in (200, None) or not rd.get("datanodes"):
        raise ErreurSource("NBS : réponse sans données")
    points = []
    for n in rd["datanodes"]:
        wds = {w.get("wdcode"): w.get("valuecode") for w in n.get("wds") or []}
        d = n.get("data") or {}
        if wds.get("zb") == code and d.get("hasdata") and len(str(wds.get("sj", ""))) == 6:
            sj = wds["sj"]
            points.append((f"{sj[:4]}-{sj[4:]}-01", d.get("data")))
    if not points:
        raise ErreurSource(f"NBS : série {code} absente de la réponse")
    return _propre(points)


def lire_douanes_taiwan(texte: str) -> Serie:
    """CSV des douanes de Taïwan : « 年度 » (année de la République de Chine, + 1911), « 月份 », « 出口總值 »
    (exportations totales, réexportations comprises, publiées en milliers de dollars taïwanais) → milliards de NT$."""
    lignes = list(csv.reader(io.StringIO(texte.lstrip("\ufeff"))))
    if not lignes:
        raise ErreurSource("Douanes de Taïwan : fichier vide")
    entete = [c.strip() for c in lignes[0]]
    try:
        ia, im = entete.index("年度"), entete.index("月份")
        iv = next(i for i, c in enumerate(entete) if c.startswith("出口總值"))
    except (ValueError, StopIteration):
        raise ErreurSource("Douanes de Taïwan : colonnes inattendues")
    points = []
    for l in lignes[1:]:
        if len(l) > max(ia, im, iv) and l[ia].strip().isdigit() and l[im].strip().isdigit():
            points.append((f"{int(l[ia]) + 1911}-{int(l[im]):02d}-01", l[iv]))
    return [(d, round(v / 1e6, 3)) for d, v in _propre(points)]  # milliers → milliards de dollars taïwanais


def lire_usgs(texte: str) -> dict | None:
    """Texte d'un PDF mensuel « Cement in <Mois> <Année> » : expéditions de ciment portland et composé (Mt)
    et variation sur un an publiée. Renvoie {mois AAAA-MM-01, valeur, variation_12m} ou None."""
    t = re.sub(r"\s+", " ", texte)
    m = re.search(r"Total shipments of portland and blended cement.*? in (\w+) (\d{4}) were an estimated ([\d.]+) million metric tons"
                  r".*?a ([\d.]+) percent (increase|decrease)", t, re.I)
    if not m or m.group(1).lower() not in MOIS_EN:
        return None
    var = float(m.group(4)) * (1 if m.group(5).lower() == "increase" else -1)
    return {"mois": f"{m.group(2)}-{MOIS_EN[m.group(1).lower()]:02d}-01", "valeur": float(m.group(3)), "variation_12m": var}


def lire_drewry(page: str) -> dict | None:
    """Page publique du WCI : date de l'évaluation, valeur composite (US$/40 pieds), variation annuelle publiée."""
    t = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", " ", page, flags=re.S))))
    m = re.search(r"assessment for \w+,? (\d{1,2}) (\w{3})\w* (\d{4}).*?\(WCI\).*?\$([\d,]+(?:\.\d+)?) per 40ft", t, re.I)
    if not m or m.group(2).lower() not in MOIS_COURTS:
        return None
    jour = date(int(m.group(3)), MOIS_COURTS[m.group(2).lower()], int(m.group(1)))
    a = re.search(r"WCI[^.]{0,80}?(\d+(?:\.\d+)?)% (higher|lower) YoY", t, re.I)
    var = (float(a.group(1)) * (1 if a.group(2).lower() == "higher" else -1)) if a else None
    return {"date": jour.isoformat(), "valeur": flottant(m.group(4)), "variation_12m": var}


def lire_indeed(texte: str) -> Serie:
    points = []
    for r in csv.DictReader(io.StringIO(texte)):
        if (r.get("variable") or "").strip() == "total postings":
            points.append((r.get("date"), r.get("indeed_job_postings_index_SA")))
    return _propre(points)


def lire_tsa(page: str) -> Serie:
    """Tableau de la page TSA : « 11/6/2026 | 2,345,678 »."""
    points = []
    for m in re.finditer(r"<td[^>]*>\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*</td>\s*<td[^>]*>\s*([\d,]+)\s*</td>", page):
        mo, j, a, v = m.groups()
        points.append((f"{a}-{int(mo):02d}-{int(j):02d}", v))
    return _propre(points)


def lire_eia(objet: dict) -> Serie:
    return _propre((r.get("period"), r.get("value")) for r in ((objet or {}).get("response") or {}).get("data") or [])


def lire_entsoe(xml: str) -> Serie:
    """GL_MarketDocument (A65) : moyenne journalière de la charge (MW), toutes résolutions confondues."""
    racine = ET.fromstring(xml)
    for e in racine.iter():  # espaces de noms retirés : seuls les noms locaux comptent
        e.tag = e.tag.split("}")[-1]
    jours: dict[str, list[float]] = {}
    for per in racine.iter("Period"):
        t0 = datetime.fromisoformat(per.findtext("timeInterval/start").replace("Z", "+00:00"))
        pas = {"PT15M": 15, "PT30M": 30, "PT60M": 60}.get(per.findtext("resolution"), 60)
        for pt in per.findall("Point"):
            q = flottant(pt.findtext("quantity"))
            if q is not None:
                jour = (t0 + timedelta(minutes=pas * (int(pt.findtext("position")) - 1))).date().isoformat()
                jours.setdefault(jour, []).append(q)
    return sorted((j, round(sum(v) / len(v), 1)) for j, v in jours.items() if len(v) >= 12)


def lire_csv_url(texte: str, pays: str, indicateur: str) -> Serie:
    points = []
    for r in csv.DictReader(io.StringIO(texte)):
        if (r.get("pays") or "").strip().upper() == pays and (r.get("indicateur") or "").strip() == indicateur:
            points.append((r.get("date"), r.get("valeur")))
    return _propre(points)


def nom_recherche(nom: str) -> str:
    """« Industrias Peñoles, S.A.B. de C.V. » → « Industrias Peñoles » (recherche d'article Wikipédia)."""
    n = re.split(r",| \(", nom or "")[0]
    n = re.sub(r"\b(Inc|Corp|Corporation|Ltd|Limited|plc|PLC|S\.?A\.?B?|SE|AG|N\.?V\.?|Co|Holdings?|Group|SpA|S\.p\.A)\.?$", "", n.strip()).strip()
    return n or nom


# ------------------------------------------------------------------ fournisseur réel

class FournisseurReel:
    def __init__(self, dossier_cache: Path):
        self.t = Telechargeur(dossier_cache, duree_cache_h=12, essais=3, delai_politesse=0.8, delai_max=60)
        self.t.session.headers["User-Agent"] = AGENT_HTTP
        # Wikipédia : requêtes espacées, sans reprise (la limite de débit est stricte)
        self.wiki = Telechargeur(dossier_cache, duree_cache_h=20, essais=1, delai_politesse=2.0, delai_max=30)
        self.wiki.session.headers["User-Agent"] = AGENT_HTTP

    def serie(self, ind: dict, aujourdhui: date) -> tuple[Serie, str] | None:
        """Source principale ; en cas d'échec, source de secours éventuelle (détail préfixé par « secours : »)."""
        try:
            return getattr(self, f"_{ind['source']}")(ind.get("params") or {}, aujourdhui)
        except Exception as e:
            sec = ind.get("secours")
            if not sec:
                raise
            LOG.warning("%s : source principale indisponible (%s), secours %s", ind["cle"], str(e)[:120], sec["source"])
            r = getattr(self, f"_{sec['source']}")(sec.get("params") or {}, aujourdhui)
            return (r[0], f"secours : {sec.get('nom', sec['source'])} (source principale indisponible : {str(e)[:100]})") if r else None

    def _nbs(self, p, aujourdhui):
        import time
        dfwds = json.dumps([{"wdcode": "zb", "valuecode": p["indicateur"]}, {"wdcode": "sj", "valuecode": f"LAST{p.get('mois', 72)}"}])
        objet = self.t.json(NBS, params={"m": "QueryData", "dbcode": "hgyd", "rowcode": "zb", "colcode": "sj", "wds": "[]",
                                         "dfwds": dfwds, "k1": str(int(time.time() * 1000) // 3_600_000)})
        return lire_nbs(objet, p["serie"]), "API data.stats.gov.cn (base mensuelle)"

    def _douanes_taiwan(self, p, aujourdhui):
        # Le serveur n'annonce pas de jeu de caractères : décodage UTF-8 explicite
        return lire_douanes_taiwan(self.t.octets(DOUANES_TAIWAN).decode("utf-8-sig")), "fichier CSV ouvert des douanes (exportations totales)"

    def _destatis_maut(self, p, aujourdhui):
        return lire_destatis(self.t.octets(DESTATIS_XLSX)), "rapport statistique hebdomadaire (xlsx)"

    def _fred(self, p, aujourdhui):
        cle = os.environ.get("FRED_API_KEY")
        depuis = (aujourdhui - timedelta(days=365 * p.get("annees", 12))).isoformat()
        if cle:
            d = self.t.json(FRED_API, params={"series_id": p["serie"], "api_key": cle, "file_type": "json", "observation_start": depuis})
            return _propre((o["date"], o["value"]) for o in d["observations"]), "API"
        return lire_csv_fred(self.t.texte(FRED_CSV, params={"id": p["serie"], "cosd": depuis})), "CSV public"

    def _dbnomics(self, p, aujourdhui):
        url = DBNOMICS.format(fournisseur=p["fournisseur"], jeu=p["jeu"], serie=p["serie"])
        return lire_dbnomics(self.t.json(url, params={"observations": 1})), "API DBnomics"

    def _usgs_ciment(self, p, aujourdhui):
        from pypdf import PdfReader
        page = self.t.texte(USGS_PAGE)
        liens = sorted(set(re.findall(r'href="([^"]+mis-(\d{6})-cemen\.pdf)"', page)), key=lambda x: x[1], reverse=True)
        points, derives = {}, {}
        for url, _ in liens[: p.get("rapports", 14)]:
            try:
                pdf = PdfReader(io.BytesIO(self.t.octets(url)))
                r = lire_usgs("\n".join((pdf.pages[i].extract_text() or "") for i in range(min(2, len(pdf.pages)))))
            except Exception as e:  # un rapport illisible n'arrête pas la source
                LOG.warning("USGS %s illisible : %s", url, str(e)[:120])
                continue
            if r:
                points[r["mois"]] = r["valeur"]
                a = date.fromisoformat(r["mois"])
                derives[f"{a.year - 1}-{a.month:02d}-01"] = round(r["valeur"] / (1 + r["variation_12m"] / 100), 3)
        for m, v in derives.items():
            points.setdefault(m, v)  # mois d'il y a un an : déduit de la variation publiée
        if not points:
            raise ErreurSource("USGS : aucun rapport mensuel lisible")
        return sorted(points.items()), f"{len(liens[: p.get('rapports', 14)])} rapports mensuels (PDF)"

    def _drewry(self, p, aujourdhui):
        r = lire_drewry(self.t.texte(DREWRY))
        if not r or r["valeur"] is None:
            raise ErreurSource("Drewry : valeur du WCI introuvable sur la page")
        points = [(r["date"], r["valeur"])]
        if r["variation_12m"] is not None:  # point d'il y a un an déduit de la variation publiée
            points.append(((date.fromisoformat(r["date"]) - timedelta(days=364)).isoformat(), round(r["valeur"] / (1 + r["variation_12m"] / 100), 1)))
        return sorted(points), "page publique hebdomadaire (dernière évaluation ; historique accumulé par l'agent)"

    def _yahoo(self, p, aujourdhui):
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        h = yf.Ticker(p["symbole"]).history(period=p.get("periode", "6y"), interval="1d", auto_adjust=False)
        points = _propre((d.strftime("%Y-%m-%d"), v) for d, v in h["Close"].dropna().items())
        if not points:
            raise ErreurSource(f"Yahoo {p['symbole']} : aucun cours")
        return points, "yfinance"

    def _indeed(self, p, aujourdhui):
        return lire_indeed(self.t.texte(INDEED.format(pays=p["pays"]))), "dépôt public GitHub (index corrigé des variations saisonnières)"

    def _tsa(self, p, aujourdhui):
        points = lire_tsa(self.t.texte(TSA))
        for a in range(aujourdhui.year - 1, aujourdhui.year - p.get("annees", 3) - 1, -1):
            try:
                points += lire_tsa(self.t.texte(f"{TSA}/{a}"))
            except ErreurSource as e:
                LOG.warning("TSA %s : %s", a, e)
        if not points:
            raise ErreurSource("TSA : tableau des passagers introuvable")
        return _propre(points), "page publique (passagers contrôlés par jour)"

    def _eia(self, p, aujourdhui):
        cle = os.environ.get("EIA_API_KEY")
        if not cle:
            return None
        params = {"api_key": cle, "frequency": "daily", "data[0]": "value", "facets[respondent][]": p.get("zone", "US48"),
                  "facets[type][]": "D", "facets[timezone][]": "Eastern", "start": (aujourdhui - timedelta(days=365 * 4)).isoformat(),
                  "sort[0][column]": "period", "sort[0][direction]": "asc", "length": 5000}
        return lire_eia(self.t.json(EIA, params=params)), "API v2 (demande quotidienne, MWh)"

    def _entsoe(self, p, aujourdhui):
        cle = os.environ.get("ENTSOE_API_KEY")
        if not cle:
            return None
        points = []
        for k in range(p.get("annees", 3), 0, -1):  # une requête par an au plus (limite de l'API)
            fin = aujourdhui - timedelta(days=365 * (k - 1))
            debut = fin - timedelta(days=365)
            xml = self.t.texte(ENTSOE, params={"securityToken": cle, "documentType": "A65", "processType": "A16",
                                               "outBiddingZone_Domain": p["zone"], "periodStart": debut.strftime("%Y%m%d0000"),
                                               "periodEnd": fin.strftime("%Y%m%d0000")})
            points += lire_entsoe(xml)
        return _propre(points), "Transparency Platform (charge réalisée, moyenne journalière en MW)"

    def _csv_url(self, p, aujourdhui):
        url = os.environ.get(p["variable"])
        if not url:
            return None
        return lire_csv_url(self.t.texte(url), p["pays"], p["indicateur"]), f"fichier CSV (variable {p['variable']})"

    # ---------------------------------------------------------------- attention du public

    def wikipedia(self, nom: str, aujourdhui: date) -> dict | None:
        r = self.wiki.json(WIKI_RECHERCHE, params={"action": "opensearch", "search": nom_recherche(nom), "limit": 1, "namespace": 0, "format": "json"})
        if not r or len(r) < 2 or not r[1]:
            return None
        article = r[1][0]
        fin = aujourdhui - timedelta(days=1)
        url = WIKI_VUES.format(article=quote(article.replace(" ", "_"), safe=""), debut=(fin - timedelta(days=119)).strftime("%Y%m%d"),
                               fin=fin.strftime("%Y%m%d"))
        items = self.wiki.json(url).get("items") or []
        return {"article": article, "vues": [[f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}", i["views"]] for i in items]}

    def trends(self, mot: str, aujourdhui: date) -> list | None:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            return None  # bibliothèque absente : source ignorée
        t = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        t.build_payload([mot], timeframe="today 3-m")
        df = t.interest_over_time()
        if df is None or df.empty or mot not in df:
            return []
        return [[d.strftime("%Y-%m-%d"), int(v)] for d, v in df[mot].items()]


# ------------------------------------------------------------------ fournisseur de test et capture

class FournisseurTest:
    """Relit agents/donnees_alternatives/tests/donnees/ : un fichier par indicateur ; fichier absent = source en panne,
    fichier {"non_configuree": true} = clé absente."""

    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def _lire(self, nom: str):
        chemin = self.dossier / f"{nom}.json"
        if not chemin.exists():
            raise ErreurSource(f"Donnée de test absente : {chemin.name} (simulation d'une source en panne)")
        return json.loads(chemin.read_text(encoding="utf-8"))

    def serie(self, ind, aujourdhui):
        if ind["source"] in ("eia", "entsoe", "csv_url") and not (self.dossier / f"{ind['cle']}.json").exists():
            return None  # comme sans clé : « non configurée »
        d = self._lire(ind["cle"])
        if d.get("non_configuree"):
            return None
        return [tuple(p) for p in d["points"]], d.get("detail", "données de test")

    def wikipedia(self, nom, aujourdhui):
        return (self._lire("attention_wikipedia").get(nom))

    def trends(self, mot, aujourdhui):
        chemin = self.dossier / "attention_trends.json"
        if not chemin.exists():
            return None
        return json.loads(chemin.read_text(encoding="utf-8")).get(mot)


class Capture:
    """Enveloppe le fournisseur réel et enregistre chaque réponse comme donnée de test
    (python -m agents.donnees_alternatives --capturer)."""

    def __init__(self, reel, dossier: Path):
        self.reel, self.dossier = reel, Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.attention = {"attention_wikipedia": {}, "attention_trends": {}}

    def _ecrire(self, nom, objet):
        (self.dossier / f"{nom}.json").write_text(json.dumps(objet, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def serie(self, ind, aujourdhui):
        r = self.reel.serie(ind, aujourdhui)
        if r is not None:
            self._ecrire(ind["cle"], {"points": r[0], "detail": r[1], "capture": datetime.now(timezone.utc).date().isoformat()})
        return r

    def wikipedia(self, nom, aujourdhui):
        r = self.reel.wikipedia(nom, aujourdhui)
        self.attention["attention_wikipedia"][nom] = r
        self._ecrire("attention_wikipedia", self.attention["attention_wikipedia"])
        return r

    def trends(self, mot, aujourdhui):
        r = self.reel.trends(mot, aujourdhui)
        if r is not None:
            self.attention["attention_trends"][mot] = r
            self._ecrire("attention_trends", self.attention["attention_trends"])
        return r
