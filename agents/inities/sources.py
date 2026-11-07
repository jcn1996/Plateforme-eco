"""
Sources de l'agent initiés (toutes gratuites).

- SEC EDGAR (User-Agent identifiant dans le secret SEC_USER_AGENT ; sans lui, les sources EDGAR sont ignorées) :
  index quotidien des dépôts (formulaires 4 et 13D), texte complet des dépôts, flux « submissions » des
  super-investisseurs (rapports 13F), correspondance ticker ↔ CIK (company_tickers.json).
- OpenFIGI (sans clé) : ticker des lignes des 13F (CUSIP → ticker), mis en cache dans data/inities/etat.json.
- Yahoo Finance (yfinance) : cours sur 6 mois des sociétés achetées (achat après une baisse du cours).
- AMF, base BDIF : déclarations des dirigeants (PDF) et franchissements de seuil.
- BaFin : base des « Directors' Dealings » (export CSV).
- Hors États-Unis : DART (Corée, secret DART_API_KEY facultatif), EDINET (Japon, secret EDINET_API_KEY facultatif),
  KAP (Turquie), BSE (Inde, actionnaires de plus de 1 %, sociétés listées dans config/super_investisseurs.json).
- Congrès : greffe de la Chambre (index annuel zippé + PDF des déclarations) ; Sénat (efdsearch.senate.gov,
  seulement si elus.senat_actif est vrai dans la config : le site impose d'accepter ses conditions d'utilisation).

Mode test : FournisseurTest relit agents/inities/tests/donnees/<méthode>.json ({clé des arguments: réponse}).
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource, Telechargeur

LOG = journal("agent-inities")
SEC = "https://www.sec.gov"
AMF_API = "https://bdif.amf-france.org/back/api/v1"
BAFIN_CSV = "https://portal.mvp.bafin.de/database/DealingsInfo/sucheForm.do"
CHAMBRE_ZIP = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{annee}FD.zip"
CHAMBRE_PTR = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{annee}/{doc}.pdf"
SENAT = "https://efdsearch.senate.gov"
DART_LIST = "https://opendart.fss.or.kr/api/list.json"
EDINET_LIST = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
KAP_LIST = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"
BSE_ACTIONNAIRES = "https://api.bseindia.com/BseIndiaAPI/api/ShareholdingPattern/w"
OPENFIGI = "https://api.openfigi.com/v3/mapping"
NAVIGATEUR = "Mozilla/5.0 (X11; Linux x86_64) SalleDeControle-AgentInities/1.0 (+https://github.com/jcn1996/Plateforme-eco)"


def cle_args(*args) -> str:
    return "|".join(str(a) for a in args)


def texte_pdf(octets: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(octets)).pages)


class FournisseurReel:
    def __init__(self, dossier_cache: Path, requetes_par_seconde: float = 8):
        self.t = Telechargeur(Path(dossier_cache) / "inities", duree_cache_h=6, delai_politesse=0.12)
        self.ua_sec = os.environ.get("SEC_USER_AGENT", "").strip()
        self.cle_dart = os.environ.get("DART_API_KEY", "").strip()
        self.cle_edinet = os.environ.get("EDINET_API_KEY", "").strip()
        self.intervalle = 1 / requetes_par_seconde
        self._dernier = 0.0

    # ---------------------------------------------------------------- EDGAR
    @property
    def sec_actif(self) -> bool:
        return bool(self.ua_sec)

    def _sec(self, url: str, binaire: bool = False):
        if not self.sec_actif:
            raise ErreurSource("secret SEC_USER_AGENT absent : source ignorée")
        attente = self.intervalle - (time.monotonic() - self._dernier)
        if attente > 0:
            time.sleep(attente)
        self._dernier = time.monotonic()
        entetes = {"User-Agent": self.ua_sec, "Accept-Encoding": "gzip, deflate"}
        return self.t.octets(url, entetes=entetes) if binaire else self.t.texte(url, entetes=entetes)

    def tickers_sec(self) -> dict:
        """{cik sans zéros: ticker} (premier ticker de chaque CIK), {ticker: cik} et {ticker: nom de la société}."""
        d = json.loads(self._sec(f"{SEC}/files/company_tickers.json"))
        par_cik, par_ticker, titres = {}, {}, {}
        for v in d.values():
            t = v["ticker"].upper().replace(".", "-")
            par_cik.setdefault(str(v["cik_str"]), t)
            par_ticker[t] = str(v["cik_str"])
            if par_cik[str(v["cik_str"])] == t:
                titres[t] = v.get("title")
        return {"par_cik": par_cik, "par_ticker": par_ticker, "titres": titres}

    def index_quotidien(self, jour: str) -> list[list[str]]:
        """Lignes [cik, nom, formulaire, date, fichier] de l'index quotidien EDGAR (formulaires 4 et 13D seulement).
        Jour sans index (week-end, jour férié, pas encore publié) : liste vide."""
        d = date.fromisoformat(jour)
        url = f"{SEC}/Archives/edgar/daily-index/{d.year}/QTR{(d.month - 1) // 3 + 1}/master.{d:%Y%m%d}.idx"
        try:
            texte = self._sec(url)
        except ErreurSource as e:
            if "HTTP 404" in str(e) or "HTTP 403" in str(e):
                return []
            raise
        res = []
        for l in texte.splitlines():
            p = l.split("|")
            if len(p) == 5 and p[2] in ("4", "SC 13D", "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13D/A"):
                res.append(p)
        return res

    def depot(self, fichier: str) -> str:
        """Texte complet d'un dépôt (edgar/data/…/accession.txt)."""
        return self._sec(f"{SEC}/Archives/{fichier}")

    def soumissions(self, cik: str) -> dict:
        """Dépôts récents d'une entité (formulaire, date de dépôt, période, numéro d'accession) : 13F seulement."""
        d = json.loads(self._sec(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))
        r = d.get("filings", {}).get("recent", {})
        depots = [{"formulaire": f, "depot": dd, "periode": p, "accession": a}
                  for f, dd, p, a in zip(r.get("form", []), r.get("filingDate", []), r.get("reportDate", []), r.get("accessionNumber", []))
                  if f.startswith("13F")]
        return {"nom": d.get("name"), "depots": depots[:12]}

    # ---------------------------------------------------------------- OpenFIGI, Yahoo
    def openfigi(self, cusips: list[str]) -> dict:
        """{cusip: ticker Yahoo ou None}, par lots de 10 (limite sans clé : 25 requêtes par minute)."""
        import requests
        res = {}
        for i in range(0, len(cusips), 10):
            lot = cusips[i:i + 10]
            for essai in range(3):
                r = requests.post(OPENFIGI, json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in lot], timeout=30)
                if r.status_code == 429:
                    time.sleep(20 * (essai + 1))
                    continue
                r.raise_for_status()
                for c, x in zip(lot, r.json()):
                    donnees = [y for y in (x.get("data") or []) if y.get("ticker")]
                    res[c] = donnees[0]["ticker"].replace("/", "-").replace(".", "-").upper() if donnees else None
                break
            else:
                raise ErreurSource("OpenFIGI : trop de requêtes (429)")
            time.sleep(2.5)
        return res

    def cours(self, tickers: list[str]) -> dict:
        """{ticker: [[date, clôture]]} sur 6 mois."""
        if not tickers:
            return {}
        import yfinance as yf
        df = yf.download(tickers, period="6mo", interval="1d", auto_adjust=True, progress=False, group_by="ticker", threads=True)
        res = {}
        for t in tickers:
            try:
                s = (df[t]["Close"] if len(tickers) > 1 else df["Close"]).dropna()
                if hasattr(s, "columns"):
                    s = s.iloc[:, 0]
                res[t] = [[d.date().isoformat(), round(float(v), 4)] for d, v in s.items()]
            except (KeyError, TypeError):
                continue
        return res

    # ---------------------------------------------------------------- France et Allemagne
    def amf_liste(self, type_info: str, depuis: str, page: int) -> list[dict]:
        """Publications BDIF récentes d'un type (DD : déclarations des dirigeants ; SPDE : franchissements de seuil),
        les plus récentes d'abord, 50 par page. Champs utiles seulement."""
        d = self.t.json(f"{AMF_API}/informations", params={"typesInformation": type_info, "from": page * 50, "size": 50},
                        entetes={"User-Agent": NAVIGATEUR})
        res = []
        for x in d.get("result", []):
            if (x.get("datePublication") or "")[:10] < depuis:
                continue
            doc = next((y for y in x.get("documents") or [] if y.get("accessible") and y.get("path")), None)
            res.append({"numero": x.get("numero"), "publication": (x.get("datePublication") or "")[:10],
                        "types": x.get("typesDocument") or [], "societes": [s.get("raisonSociale") for s in x.get("societes") or []],
                        "chemin": doc["path"] if doc else None})
        return res

    def amf_pdf(self, chemin: str) -> str:
        return texte_pdf(self.t.octets(f"{AMF_API}/documents/{chemin}", entetes={"User-Agent": NAVIGATEUR}))

    def bafin(self, depuis: str, jusqua: str) -> str:
        """Export CSV (séparateur « ; ») des déclarations publiées entre deux dates (AAAA-MM-JJ)."""
        f = lambda d: f"{d[8:10]}.{d[5:7]}.{d[:4]}"  # noqa: E731
        return self.t.texte(BAFIN_CSV, params={"meldepflichtigerName": "", "zeitraum": "0", "zeitraumVon": f(depuis), "zeitraumBis": f(jusqua),
                                               "emittentName": "", "emittentIsin": "", "emittentButton": "Suche Emittent",
                                               "d-4000784-e": "1", "6578706f7274": "1"}, entetes={"User-Agent": NAVIGATEUR})

    # ---------------------------------------------------------------- hors États-Unis
    def dart(self, depuis: str, jusqua: str) -> list[dict] | None:
        """Déclarations de participation (지분공시, type D) de toutes les sociétés coréennes sur la période. None sans clé."""
        if not self.cle_dart:
            return None
        res, page = [], 1
        while page <= 10:
            d = self.t.json(DART_LIST, params={"crtfc_key": self.cle_dart, "pblntf_ty": "D", "bgn_de": depuis.replace("-", ""),
                                               "end_de": jusqua.replace("-", ""), "page_no": page, "page_count": 100})
            if d.get("status") not in ("000", "013"):
                raise ErreurSource(f"DART : {d.get('status')} {d.get('message')}")
            for x in d.get("list") or []:
                res.append({"societe": x.get("corp_name"), "code": x.get("stock_code"), "declarant": x.get("flr_nm"), "titre": x.get("report_nm"),
                            "date": f"{x['rcept_dt'][:4]}-{x['rcept_dt'][4:6]}-{x['rcept_dt'][6:]}", "id": x.get("rcept_no"),
                            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={x.get('rcept_no')}"})
            if page >= int(d.get("total_page") or 1):
                break
            page += 1
        return res

    def edinet(self, jour: str) -> list[dict] | None:
        """Déclarations de grands actionnaires (大量保有報告書 et rapports de modification) du jour. None sans clé."""
        if not self.cle_edinet:
            return None
        d = self.t.json(EDINET_LIST, params={"date": jour, "type": 2, "Subscription-Key": self.cle_edinet})
        return [{"societe": x.get("issuerEdinetCode") or x.get("subjectEdinetCode"), "declarant": x.get("filerName"), "titre": x.get("docDescription"),
                 "date": (x.get("submitDateTime") or jour)[:10], "id": x.get("docID"),
                 "url": f"https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?{x.get('docID')}"}
                for x in d.get("results") or [] if x.get("docTypeCode") in ("350", "360")]

    def kap(self, depuis: str, jusqua: str) -> list[dict]:
        """Annonces publiées sur KAP (Turquie) sur la période : titre, société, résumé."""
        import requests
        r = requests.post(KAP_LIST, json={"fromDate": depuis, "toDate": jusqua, "year": "", "prd": "", "term": "", "ruleType": "", "bdkReview": "",
                                          "disclosureClass": "", "index": "", "market": "", "isLate": "", "subjectList": [], "mkkMemberOidList": [],
                                          "inactiveMkkMemberOidList": [], "bdkMemberOidList": [], "mainSector": "", "sector": "", "subSector": "",
                                          "memberType": "IGS", "fromSrc": "N", "srcCategory": "", "discIndex": []},
                          headers={"User-Agent": NAVIGATEUR}, timeout=40)
        r.raise_for_status()
        return [{"societe": x.get("kapTitle") or x.get("companyName"), "titre": x.get("subject"), "resume": x.get("summary"),
                 "date": (x.get("publishDate") or "")[:10], "id": x.get("disclosureIndex"),
                 "url": f"https://www.kap.org.tr/tr/Bildirim/{x.get('disclosureIndex')}"} for x in r.json()]

    def bse(self, code: str) -> str:
        """Répartition de l'actionnariat (dernier trimestre) d'une société cotée à la BSE : texte brut de la réponse."""
        return self.t.texte(BSE_ACTIONNAIRES, params={"scripcode": code, "qtrid": "", "Flag": "S"},
                            entetes={"User-Agent": NAVIGATEUR, "Referer": "https://www.bseindia.com/"})

    # ---------------------------------------------------------------- Congrès
    def chambre_index(self, annee: int) -> str:
        z = zipfile.ZipFile(io.BytesIO(self.t.octets(CHAMBRE_ZIP.format(annee=annee), entetes={"User-Agent": NAVIGATEUR})))
        nom = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        return z.read(nom).decode("utf-8-sig", "replace")

    def chambre_ptr(self, annee: str, doc: str) -> str:
        return texte_pdf(self.t.octets(CHAMBRE_PTR.format(annee=annee, doc=doc), entetes={"User-Agent": NAVIGATEUR}))

    def senat(self, depuis: str) -> list[dict]:
        """Déclarations de transactions électroniques du Sénat depuis une date. Appelée seulement si elus.senat_actif
        est vrai : le site exige d'accepter ses conditions d'utilisation (case « prohibition agreement »)."""
        import requests
        s = requests.Session()
        s.headers["User-Agent"] = NAVIGATEUR
        r = s.get(f"{SENAT}/search/home/", timeout=40)
        jeton = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        if not jeton:
            raise ErreurSource("Sénat : formulaire d'accueil illisible")
        s.post(f"{SENAT}/search/home/", data={"prohibition_agreement": "1", "csrfmiddlewaretoken": jeton.group(1)},
               headers={"Referer": f"{SENAT}/search/home/"}, timeout=40)
        csrf = s.cookies.get("csrftoken")
        d = s.post(f"{SENAT}/search/report/data/", headers={"Referer": f"{SENAT}/search/", "X-CSRFToken": csrf}, timeout=40,
                   data={"start": "0", "length": "100", "report_types": "[11]", "filer_types": "[]",
                         "submitted_start_date": f"{depuis[5:7]}/{depuis[8:10]}/{depuis[:4]} 00:00:00", "submitted_end_date": "",
                         "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "", "last_name": "",
                         "csrfmiddlewaretoken": csrf, "order[0][column]": "4", "order[0][dir]": "desc"}).json()
        res = []
        for prenom, nom, _, lien, depot in (x[:5] for x in d.get("data", [])):
            url = re.search(r'href="([^"]+)"', lien)
            if not url or "/ptr/" not in url.group(1):
                continue  # déclaration papier (image) : non lisible
            page = s.get(SENAT + url.group(1), timeout=40).text
            res.append({"elu": f"{prenom} {nom}".strip(), "depot": f"{depot[6:10]}-{depot[0:2]}-{depot[3:5]}", "url": SENAT + url.group(1), "html": page})
        return res


class FournisseurTest:
    """Relit agents/inities/tests/donnees/<méthode>.json : {clé des arguments: réponse}. Un fichier absent simule
    une source en panne ; une clé absente, une réponse vide."""

    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.sec_actif = True

    def _lire(self, nom: str) -> dict:
        chemin = self.dossier / f"{nom}.json"
        if not chemin.exists():
            raise FileNotFoundError(f"Donnée de test absente : {chemin.name} (simulation d'une source en panne)")
        return json.loads(chemin.read_text(encoding="utf-8"))

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)

        def appel(*args):
            d = self._lire(nom)
            if nom in ("dart", "edinet") and d.get("_non_configuree"):
                return None
            if nom in ("openfigi", "cours"):
                return {k: d[k] for k in args[0] if k in d}
            if nom == "tickers_sec":
                return d
            v = d.get(cle_args(*args))
            if v is None and nom in ("depot", "amf_pdf", "chambre_ptr", "bse"):
                raise ErreurSource(f"{nom} {cle_args(*args)} : HTTP 404 (test)")
            return v if v is not None else ([] if nom not in ("soumissions", "bafin", "chambre_index") else
                                           {"nom": None, "depots": []} if nom == "soumissions" else "")
        return appel


class Capture:
    """Enveloppe le fournisseur réel et enregistre chaque réponse comme donnée de test (python -m agents.inities --capturer)."""

    def __init__(self, reel, dossier: Path):
        self.reel, self.dossier = reel, Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)

    @property
    def sec_actif(self):
        return self.reel.sec_actif

    def __getattr__(self, nom):
        methode = getattr(self.reel, nom)

        def appel(*args):
            res = methode(*args)
            chemin = self.dossier / f"{nom}.json"
            d = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}
            if nom in ("openfigi", "cours", "tickers_sec"):
                d.update(res or {})
            elif res is None and nom in ("dart", "edinet"):
                d["_non_configuree"] = True
            else:
                d[cle_args(*args)] = res
            chemin.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            return res
        return appel
