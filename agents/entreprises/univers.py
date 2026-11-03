"""
Univers de l'agent entreprises (environ 1 200 sociétés).

Ordre des sources de composition, pays par pays :
  1. fichiers de composition iShares (IVV, IJH et ETF MSCI par pays) ;
  2. secours : SSGA SPY / MDY (mêmes indices S&P 500 / S&P 400) pour les États-Unis,
     filtre d'actions Yahoo (plus grosses capitalisations du pays) ailleurs ;
  3. dernière liste connue (data/entreprises/univers.json) ;
  4. liste de départ (agents/entreprises/univers_depart.json), utilisée seulement au tout premier lancement.
La liste de surveillance personnelle (config/surveillance.json) est toujours ajoutée.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from ..commun.journal import journal

LOG = journal("agent-entreprises")

# 11 secteurs GICS : clé anglaise → (libellé français, identifiant court)
GICS = {
    "Energy": ("Énergie", "energie"),
    "Materials": ("Matériaux", "materiaux"),
    "Industrials": ("Industrie", "industrie"),
    "Consumer Discretionary": ("Consommation discrétionnaire", "conso-discretionnaire"),
    "Consumer Staples": ("Consommation de base", "conso-base"),
    "Health Care": ("Santé", "sante"),
    "Financials": ("Finance", "finance"),
    "Information Technology": ("Technologies de l'information", "technologie"),
    "Communication": ("Services de communication", "communication"),
    "Utilities": ("Services aux collectivités", "services-collectivites"),
    "Real Estate": ("Immobilier", "immobilier"),
}
# Synonymes (libellés iShares, SSGA et Yahoo) → clé GICS
SYNONYMES = {
    "energy": "Energy", "materials": "Materials", "basic materials": "Materials",
    "industrials": "Industrials", "consumer discretionary": "Consumer Discretionary", "consumer cyclical": "Consumer Discretionary",
    "consumer staples": "Consumer Staples", "consumer defensive": "Consumer Staples",
    "health care": "Health Care", "healthcare": "Health Care",
    "financials": "Financials", "financial services": "Financials", "financial": "Financials",
    "information technology": "Information Technology", "technology": "Information Technology",
    "communication": "Communication", "communication services": "Communication", "telecommunication services": "Communication",
    "utilities": "Utilities", "real estate": "Real Estate",
}

# Place de cotation (colonne « Exchange » des fichiers iShares) → suffixe Yahoo Finance
SUFFIXES = [
    ("tokyo", ".T"), ("kosdaq", ".KQ"), ("korea", ".KS"), ("gretai", ".TWO"), ("taipei exchange", ".TWO"), ("taiwan", ".TW"),
    ("national stock exchange of india", ".NS"), ("bse", ".BO"), ("sao paulo", ".SA"), ("b3", ".SA"), ("bovespa", ".SA"),
    ("mexicana", ".MX"), ("hong kong", ".HK"), ("shanghai", ".SS"), ("shenzhen", ".SZ"), ("xetra", ".DE"), ("deutsche", ".DE"),
    ("paris", ".PA"), ("london", ".L"), ("italiana", ".MI"), ("madrid", ".MC"), ("mercado continuo", ".MC"),
    ("amsterdam", ".AS"), ("stockholm", ".ST"), ("nasdaq omx nordic", ".ST"), ("warsaw", ".WA"), ("six swiss", ".SW"),
    ("asx", ".AX"), ("australian", ".AX"), ("toronto", ".TO"), ("johannesburg", ".JO"), ("saudi", ".SR"),
    ("abu dhabi", ".AD"), ("dubai", ".AE"), ("istanbul", ".IS"), ("indonesia", ".JK"), ("singapore", ".SI"),
    ("thailand", ".BK"), ("santiago", ".SN"), ("colombia", ".CL"), ("buenos aires", ".BA"), ("ho chi minh", ".VN"),
    ("hanoi", ".VN"), ("egypt", ".CA"), ("nasdaq", ""), ("new york", ""), ("nyse", ""), ("cboe", ""),
]
PAYS_PAR_LOCALISATION = {
    "united states": "US", "canada": "CA", "mexico": "MX", "brazil": "BR", "argentina": "AR", "chile": "CL", "colombia": "CO",
    "united kingdom": "GB", "france": "FR", "germany": "DE", "switzerland": "CH", "italy": "IT", "spain": "ES",
    "netherlands": "NL", "sweden": "SE", "poland": "PL", "japan": "JP", "china": "CN", "india": "IN", "korea (south)": "KR",
    "korea": "KR", "taiwan": "TW", "australia": "AU", "indonesia": "ID", "singapore": "SG", "thailand": "TH", "vietnam": "VN",
    "saudi arabia": "SA", "united arab emirates": "AE", "turkey": "TR", "south africa": "ZA", "egypt": "EG",
}


def secteur_gics(libelle: str | None) -> str | None:
    if not libelle:
        return None
    if libelle in GICS:
        return libelle
    return SYNONYMES.get(str(libelle).strip().lower())


def symbole_yahoo(ticker: str, place: str, pays: str) -> str | None:
    """Ticker d'un fichier de composition → symbole Yahoo Finance."""
    t = str(ticker).strip().upper()
    if not t or t in ("-", "CASH", "USD"):
        return None
    place = (place or "").lower()
    suffixe = next((s for cle, s in SUFFIXES if cle in place), None)
    if suffixe is None:
        return None
    if suffixe == "":
        return t.replace(".", "-").replace("/", "-")
    if suffixe == ".HK":
        t = t.lstrip("0").zfill(4)
    if suffixe in (".L", ".PA", ".AS", ".MI", ".MC", ".ST", ".SW", ".DE"):
        t = t.replace(" ", "-").replace("/", "-").rstrip(".")
    return f"{t}{suffixe}"


# --------------------------------------------------------------- lecteurs de fichiers

def lire_ishares(texte: str, pays_defaut: str) -> list[dict]:
    """CSV iShares : quelques lignes d'en-tête, puis « Ticker,Name,Sector,Asset Class,Market Value,Weight (%),… »."""
    lignes = texte.splitlines()
    debut = next((i for i, l in enumerate(lignes) if l.startswith("Ticker,")), None)
    if debut is None:
        raise ValueError("fichier iShares sans tableau de composition (page HTML reçue ?)")
    res = []
    for l in csv.DictReader(io.StringIO("\n".join(lignes[debut:]))):
        if (l.get("Asset Class") or "").strip() != "Equity":
            continue
        pays = PAYS_PAR_LOCALISATION.get((l.get("Location") or "").strip().lower(), pays_defaut)
        sym = symbole_yahoo(l.get("Ticker"), l.get("Exchange"), pays)
        if not sym:
            continue
        try:
            poids = float(str(l.get("Weight (%)", "0")).replace(",", ""))
        except ValueError:
            poids = 0.0
        res.append({"ticker": sym, "nom": (l.get("Name") or "").strip().title(), "pays": pays,
                    "secteur": secteur_gics(l.get("Sector")), "poids": poids})
    if not res:
        raise ValueError("aucune action dans le fichier iShares")
    return sorted(res, key=lambda x: -x["poids"])


def lire_positions_globalx(texte: str) -> list[dict]:
    """CSV Global X : 2 lignes de titre, puis « % of Net Assets,Ticker,Name,SEDOL,… » ; lignes sans code
    (liquidités, devises) ignorées."""
    lignes = texte.splitlines()
    debut = next((i for i, l in enumerate(lignes) if l.startswith("% of Net Assets")), None)
    if debut is None:
        raise ValueError("fichier Global X sans tableau de positions")
    res = []
    for l in csv.DictReader(io.StringIO("\n".join(lignes[debut:]))):
        code = (l.get("Ticker") or "").strip()
        if not code:
            continue
        try:
            poids = float(str(l.get("% of Net Assets", "0")).replace(",", ""))
        except ValueError:
            poids = 0.0
        res.append({"code": code, "nom": (l.get("Name") or code).strip(), "poids": poids})
    if not res:
        raise ValueError("aucune position dans le fichier Global X")
    return res


def lire_positions_vaneck(contenu: bytes) -> list[dict]:
    """Fichier Excel de positions VanEck : colonnes « Ticker » et « Holding Name » (ou « Name »), « % of Net Assets »."""
    import openpyxl
    lignes = list(openpyxl.load_workbook(io.BytesIO(contenu), read_only=True, data_only=True).active.iter_rows(values_only=True))
    debut = next(i for i, l in enumerate(lignes) if l and "Ticker" in [str(c).strip() for c in l if c])
    entete = [str(c).strip() if c else "" for c in lignes[debut]]
    i_t = entete.index("Ticker")
    i_n = next(i for i, h in enumerate(entete) if h in ("Holding Name", "Name", "Security Name"))
    i_p = next((i for i, h in enumerate(entete) if "% of Net Assets" in h or h == "Weight"), None)
    res = []
    for l in lignes[debut + 1:]:
        if not l or not l[i_t] or not l[i_n]:
            continue
        try:
            poids = float(str(l[i_p]).replace("%", "")) if i_p is not None and l[i_p] is not None else 0.0
        except ValueError:
            poids = 0.0
        res.append({"code": str(l[i_t]).strip(), "nom": str(l[i_n]).strip(), "poids": poids})
    if not res:
        raise ValueError("aucune position dans le fichier VanEck")
    return res


def lire_ssga(contenu: bytes) -> list[dict]:
    """Fichier Excel SSGA (SPY, MDY) : « Name, Ticker, Identifier, SEDOL, Weight, Sector, Shares Held, Local Currency »."""
    import openpyxl
    classeur = openpyxl.load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
    lignes = list(classeur.active.iter_rows(values_only=True))
    debut = next(i for i, l in enumerate(lignes) if l and l[0] == "Name" and "Ticker" in l)
    entete = list(lignes[debut])
    res = []
    for l in lignes[debut + 1:]:
        d = dict(zip(entete, l))
        t = d.get("Ticker")
        if not t or not d.get("Name") or str(t).strip() in ("-", "CASH_USD") or d.get("Weight") in (None, "-"):
            continue
        res.append({"ticker": str(t).strip().replace(".", "-").replace("/", "-"), "nom": str(d["Name"]).strip().title(),
                    "pays": "US", "secteur": secteur_gics(d.get("Sector")), "poids": float(d.get("Weight") or 0)})
    return sorted(res, key=lambda x: -x["poids"])


# --------------------------------------------------------------- Wikipédia (secours)

# Libellés de secteurs rencontrés sur Wikipédia (GICS, ICB, Prime Standard, SET…) → clé GICS, par mots-clés
MOTS_SECTEURS = [
    (("bank", "banking", "insurance", "financ", "asset management", "capital markets"), "Financials"),
    (("oil", "gas", "energy", "petrol", "coal"), "Energy"),
    (("mining", "metal", "chemical", "material", "steel", "paper", "gold", "construction material"), "Materials"),
    (("software", "technolog", "semiconductor", "electronic", "it services", "computer"), "Information Technology"),
    (("telecom", "media", "communication", "entertainment", "interactive"), "Communication"),
    (("pharma", "health", "medical", "biotech", "drug"), "Health Care"),
    (("utilit", "electric", "power", "water"), "Utilities"),
    (("real estate", "property", "propert", "reit"), "Real Estate"),
    (("food", "beverage", "tobacco", "personal", "household", "drink", "agricult", "staples", "commerce"), "Consumer Staples"),
    (("retail", "automobile", "auto", "apparel", "luxury", "consumer", "travel", "leisure", "hotel", "textile"), "Consumer Discretionary"),
    (("industr", "aerospace", "defen", "transport", "construction", "engineering", "machinery", "logistic", "airline", "shipping"), "Industrials"),
]


def secteur_wikipedia(libelle: str | None) -> str | None:
    if not libelle:
        return None
    direct = secteur_gics(libelle)
    if direct:
        return direct
    t = libelle.lower()
    for mots, cle in MOTS_SECTEURS:
        if any(m in t for m in mots):
            return cle
    return None


SUFFIXES_CONNUS = {sfx for _, sfx in SUFFIXES if sfx} | {".OL", ".HE", ".CO", ".BR", ".LS", ".VI", ".IR"}
EN_TETES_TICKER = ("ticker", "symbol", "code", "stock symbol", "ticker symbol", "stock code")
EN_TETES_NOM = ("company", "name", "company name", "securities name", "constituent", "constituent name")
EN_TETES_SECTEUR = ("sector", "industry", "segment", "sub-index", "gics")


def ticker_wikipedia(cellule: str, suffixe: str, zero_pad: int = 0) -> str | None:
    """« SEHK: 5 » → 0005.HK ; « BT.A » → BT-A.L ; « AI.PA » (déjà suffixé) → AI.PA ; « AIR.PA » sur le DAX → None."""
    t = (cellule or "").strip().split("\n")[0].strip()
    if ":" in t:
        t = t.split(":")[-1].strip()
    t = t.split()[0] if t.split() else ""
    t = t.upper().strip(".,;")
    if not t or not re.fullmatch(r"[A-Z0-9.\-&]+", t):
        return None
    if t.endswith(suffixe.upper()):
        racine = t[: -len(suffixe)]
    elif "." in t and "." + t.rsplit(".", 1)[1] in SUFFIXES_CONNUS:
        return None  # valeur cotée sur une autre place (ex. Airbus dans le tableau du DAX)
    else:
        racine = t.replace(".", "-")
    if zero_pad and racine.isdigit():
        racine = racine.zfill(zero_pad)
    return f"{racine}{suffixe}"


def lire_wikipedia(html: str, pays: str, cfg: dict) -> list[dict]:
    """Tableau des membres d'un indice (en-têtes Ticker / Symbol / Code…), ou liste à puces « (TYO: 7203) »
    pour le Nikkei 225. Lève ValueError si rien d'exploitable n'est trouvé."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    suffixe, pad = cfg["suffixe"], cfg.get("zero_pad", 0)
    suffixes_par_prefixe = cfg.get("prefixes", {})
    res = []
    if cfg.get("mode") == "liste":
        motif = re.compile(cfg["motif"])
        secteur = None
        for el in soup.find_all(["h2", "h3", "h4", "li"]):
            if el.name in ("h2", "h3", "h4"):
                secteur = el.get_text(" ", strip=True)
                continue
            texte = el.get_text(" ", strip=True)
            m = motif.search(texte)
            if m:
                code = m.group(1)
                nom = texte[: m.start()].strip(" (")
                res.append({"ticker": f"{code.zfill(pad) if pad and code.isdigit() else code}{suffixe}", "nom": nom,
                            "pays": pays, "secteur": secteur_wikipedia(secteur), "poids": 0.0})
    else:
        for table in soup.select("table.wikitable"):
            lignes = table.find_all("tr")
            if not lignes:
                continue
            entetes = [c.get_text(" ", strip=True).lower() for c in lignes[0].find_all(["th", "td"])]

            def colonne(noms, exact=True):
                for i, h in enumerate(entetes):
                    if (h in noms) if exact else any(n in h for n in noms):
                        return i
                return None
            i_t = colonne(EN_TETES_TICKER)
            if i_t is None:
                i_t = colonne(("ticker", "symbol"), exact=False)
            i_n = colonne(EN_TETES_NOM) if colonne(EN_TETES_NOM) is not None else colonne(("company", "name"), exact=False)
            i_s = colonne(EN_TETES_SECTEUR, exact=False)
            if i_t is None or i_n is None:
                continue
            for tr in lignes[1:]:
                cellules = tr.find_all(["td", "th"])
                if len(cellules) <= max(i_t, i_n):
                    continue
                brut = cellules[i_t].get_text("\n", strip=True)
                prefixe = brut.split(":")[0].strip().upper() if ":" in brut else None
                sfx = suffixes_par_prefixe.get(prefixe, suffixe) if prefixe else suffixe
                t = ticker_wikipedia(brut, sfx, pad)
                if not t:
                    continue
                sect = cellules[i_s].get_text(" ", strip=True) if i_s is not None and len(cellules) > i_s else None
                res.append({"ticker": t, "nom": cellules[i_n].get_text(" ", strip=True), "pays": pays,
                            "secteur": secteur_wikipedia(sect), "poids": 0.0})
            if res:
                break
    uniques = list({s["ticker"]: s for s in res}.values())
    if len(uniques) < cfg.get("minimum", 5):
        raise ValueError(f"tableau des membres introuvable ou trop court ({len(uniques)} lignes)")
    return uniques


# --------------------------------------------------------------- composition

NAVIGATEUR = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
AGENT_WIKIPEDIA = "Plateforme-eco/1.0 (https://github.com/jcn1996/Plateforme-eco; agent entreprises)"


class Composition:
    def __init__(self, telechargeur, config: dict, yahoo=None):
        self.t = telechargeur
        self.cfg = config["univers"]
        self.yahoo = yahoo  # pour classer les membres d'un indice par montant échangé

    def etf_ishares(self, etf: str, pays: str) -> list[dict]:
        """Point d'accès CSV officiel des fonds iShares (lien « Download holdings » de la page du fonds)."""
        info = self.cfg["ishares"].get(etf)
        if not info:
            raise ValueError(f"{etf} n'est pas un ETF iShares (ou URL inconnue)")
        page = f"https://www.ishares.com/us/products/{info['id']}/{info['slug']}"
        entetes = {"User-Agent": NAVIGATEUR, "Accept": "text/csv,*/*", "Referer": page}
        erreurs = []
        # Fichier « latest-holdings.csv » (lien de la page du fonds), puis point d'accès .ajax
        for url in (f"{page}/latest-holdings.csv", self.cfg["url_ishares"].format(id=info["id"], slug=info["slug"], t=etf)):
            try:
                return lire_ishares(self.t.texte(url, entetes=entetes), pays)
            except Exception as e:
                erreurs.append(f"{url.rsplit('/', 1)[-1][:40]} : {str(e)[:80]}")
        raise ValueError(" ; ".join(erreurs))

    # --- Global X et VanEck : fichiers de positions publiés par le fournisseur de l'ETF ---
    def etf_globalx(self, etf: str, pays: str) -> list[dict]:
        """CSV « <etf>_full-holdings_AAAAMMJJ.csv » (dernier jour ouvré, jusqu'à 7 jours en arrière)."""
        from datetime import date, timedelta
        erreurs = []
        for k in range(8):
            jour = date.today() - timedelta(days=k)
            if jour.weekday() >= 5:
                continue
            url = f"https://assets.globalxetfs.com/funds/holdings/{etf.lower()}_full-holdings_{jour:%Y%m%d}.csv"
            try:
                return self.resoudre(lire_positions_globalx(self.t.texte(url)), pays)
            except Exception as e:
                erreurs.append(f"{jour:%d/%m} : {str(e)[:40]}")
        raise ValueError("fichier Global X introuvable (" + " ; ".join(erreurs[:3]) + ")")

    def etf_vaneck(self, etf: str, pays: str) -> list[dict]:
        info = self.cfg["fournisseurs"][etf]
        url = f"https://www.vaneck.com/us/en/investments/{info['slug']}/downloads/holdings/"
        r = self.t.session.get(url, headers={"User-Agent": NAVIGATEUR}, timeout=60, allow_redirects=False)
        if r.status_code != 200 or b"PK" not in r.content[:4]:
            raise ValueError(f"VanEck {etf} : fichier non servi (HTTP {r.status_code}, vérification par cookie)")
        return self.resoudre(lire_positions_vaneck(r.content), pays)

    def resoudre(self, positions: list[dict], pays: str) -> list[dict]:
        """Codes Bloomberg (« ECOPETL CB ») → symboles Yahoo, par recherche du nom sur Yahoo
        (on garde le symbole de la place du pays ; à défaut, la racine du code + le suffixe du pays)."""
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        suffixe = self.cfg["suffixes_pays"].get(pays, "")
        res = []
        for p in positions:
            racine = p["code"].split()[0].upper()
            symbole = None
            try:
                quotes = [q.get("symbol", "") for q in yf.Search(p["nom"], max_results=8, news_count=0).quotes or []]
                locaux = [q for q in quotes if suffixe and q.upper().endswith(suffixe.upper())]
                symbole = next((q for q in locaux if q.upper().startswith(racine)), locaux[0] if locaux else None)
            except Exception as e:
                LOG.debug("recherche Yahoo %s : %s", p["nom"], str(e)[:60])
            res.append({"ticker": symbole or f"{racine}{suffixe}", "nom": p["nom"].title(), "pays": pays,
                        "secteur": secteur_gics(p.get("secteur")), "poids": p["poids"]})
        return sorted(res, key=lambda x: -x["poids"])

    def etf_ssga(self, etf: str) -> list[dict]:
        url = self.cfg["ssga"][etf]
        r = self.t.session.get(url, timeout=60)
        r.raise_for_status()
        return lire_ssga(r.content)

    def wikipedia(self, pays: str) -> tuple[list[dict], str]:
        """Membres de l'indice national selon Wikipédia (API MediaWiki), essayés page par page."""
        cfg = self.cfg["wikipedia"].get(pays)
        if not cfg:
            raise ValueError("pas d'indice exploitable sur Wikipédia pour ce pays")
        erreurs = []
        for page in cfg["pages"]:
            try:
                d = self.t.json("https://en.wikipedia.org/w/api.php",
                                params={"action": "parse", "page": page, "prop": "text", "format": "json",
                                        "formatversion": "2", "redirects": "1"},
                                entetes={"User-Agent": AGENT_WIKIPEDIA})
                if "error" in d:
                    raise ValueError(d["error"].get("info", "page introuvable"))
                return lire_wikipedia(d["parse"]["text"], pays, cfg), page
            except Exception as e:
                erreurs.append(f"{page} : {str(e)[:80]}")
        raise RuntimeError(" ; ".join(erreurs))

    def filtre_yahoo(self, pays: str, nombre: int) -> list[dict]:
        """Plus grosses capitalisations cotées dans le pays (filtre d'actions Yahoo)."""
        import warnings
        import yfinance as yf
        from yfinance import EquityQuery
        warnings.filterwarnings("ignore")
        q = EquityQuery("and", [EquityQuery("eq", ["region", pays.lower()]),
                                EquityQuery("gt", ["intradaymarketcap", self.cfg["capitalisation_min_musd"] * 1e6])])
        r = yf.screen(q, sortField="intradaymarketcap", sortAsc=False, size=min(250, nombre * 2))
        res = [{"ticker": x["symbol"], "nom": x.get("longName") or x.get("shortName") or x["symbol"], "pays": pays,
                "secteur": secteur_gics(x.get("sector")), "poids": float(x.get("marketCap") or 0)} for x in r.get("quotes", [])
               if x.get("quoteType", "EQUITY") == "EQUITY"]
        if not res:
            raise ValueError(f"filtre Yahoo vide pour {pays}")
        return res

    def classer(self, liste: list[dict]) -> list[dict]:
        """Classe les membres d'un indice (Wikipédia les liste par ordre alphabétique) par montant moyen
        échangé sur 3 mois, à partir des cours téléchargés par lots (peu de requêtes)."""
        if not self.yahoo:
            return liste
        cours = self.yahoo.cours_groupes([s["ticker"] for s in liste], periode="3mo")
        for s in liste:
            points = cours.get(s["ticker"]) or []
            s["poids"] = sum(c * v for _, c, v in points) / len(points) if points else -1.0
        return sorted([s for s in liste if s["poids"] >= 0], key=lambda x: -x["poids"])

    def pays(self, code: str, plafond: int | None) -> tuple[list[dict], str]:
        """Liste des sociétés d'un pays et source utilisée. Ordre : iShares, puis Wikipédia, puis (si activé)
        filtre d'actions Yahoo. Lève une erreur si toutes échouent (la dernière liste connue prend alors le relais)."""
        p = self.cfg["pays"][code]
        erreurs = []
        if code == "US":
            societes, sources = [], []
            for etf, limite in (("IVV", None), ("IJH", self.cfg["sp400_max"])):
                liste = None
                for nom, f in ((f"iShares {etf}", lambda: self.etf_ishares(etf, "US")),
                               (f"SSGA {'SPY' if etf == 'IVV' else 'MDY'}", lambda: self.etf_ssga(etf))):
                    try:
                        liste = f()
                        sources.append(nom)
                        break
                    except Exception as e:
                        erreurs.append(f"{nom} : {str(e)[:120]}")
                if liste is None:
                    raise RuntimeError(" ; ".join(erreurs))
                societes += liste[:limite] if limite else liste
            return societes, " + ".join(sources)
        for etf in p["etf"]:
            fournisseur = self.cfg.get("fournisseurs", {}).get(etf, {}).get("type", "ishares")
            try:
                if fournisseur == "globalx":
                    return self.etf_globalx(etf, code)[:plafond], f"Global X {etf}"
                if fournisseur == "vaneck":
                    return self.etf_vaneck(etf, code)[:plafond], f"VanEck {etf}"
                return self.etf_ishares(etf, code)[:plafond], f"iShares {etf}"
            except Exception as e:
                erreurs.append(f"{fournisseur} {etf} : {str(e)[:120]}")
        try:
            membres, page = self.wikipedia(code)
            classes = self.classer(membres)
            if classes:
                return classes[:plafond], f"Wikipédia ({page}), classé par montant échangé"
            erreurs.append("Wikipédia : aucun membre coté sur Yahoo")
        except Exception as e:
            erreurs.append(f"Wikipédia : {str(e)[:160]}")
        if self.cfg.get("filtre_yahoo", True):
            try:
                return self.filtre_yahoo(code, plafond)[:plafond], "filtre d'actions Yahoo (plus grosses capitalisations)"
            except Exception as e:
                erreurs.append(f"filtre Yahoo : {str(e)[:120]}")
        raise RuntimeError(" ; ".join(erreurs))


def construire(composition: Composition | None, config: dict, connu: dict | None, depart: list[dict],
               surveillance: list[dict], pays_demandes: list[str] | None = None,
               manuelles: dict | None = None) -> tuple[list[dict], dict]:
    """Univers complet (avant filtre de capitalisation et de liquidité) et état des sources par pays.
    Ordre : sources automatiques (fournisseur de l'ETF, Wikipédia, filtre Yahoo), liste manuelle vérifiée
    (config/compositions_manuelles.json), dernière liste connue, liste de départ."""
    manuelles = manuelles or {}
    cfg = config["univers"]["pays"]
    anciens = {}
    for s in (connu or {}).get("societes", []):
        anciens.setdefault(s["pays"], []).append(s)
    par_depart = {}
    for s in depart:
        par_depart.setdefault(s["pays"], []).append(s)
    societes, etats = [], {}
    for code in pays_demandes or list(cfg):
        plafond = cfg[code]["plafond"]
        try:
            if composition is None:
                raise RuntimeError("composition non interrogée (mode test)")
            liste, source = composition.pays(code, plafond)
            etats[code] = {"etat": "ok", "source": source, "nombre": len(liste)}
        except Exception as e:
            m = manuelles.get(code)
            if m and m.get("societes"):
                liste = [{"ticker": x["ticker"], "nom": x.get("nom") or x["ticker"], "pays": code,
                          "secteur": secteur_gics(x.get("secteur")), "poids": 0.0} for x in m["societes"]]
                liste = liste[:plafond] if plafond else liste
                source = f"liste manuelle (vérifiée le {m['verifie_le'][8:10]}/{m['verifie_le'][5:7]}/{m['verifie_le'][:4]})"
                etats[code] = {"etat": "manuelle", "source": source, "nombre": len(liste), "verifie_le": m["verifie_le"],
                               "detail": str(e)[:200]}
                LOG.info("Composition %s : %s", code, source)
            elif anciens.get(code):
                liste, source = anciens[code], "dernière liste connue"
                etats[code] = {"etat": "ancienne", "source": source, "nombre": len(liste), "detail": str(e)[:200]}
            elif par_depart.get(code):
                liste, source = par_depart[code][:plafond] if plafond else par_depart[code], "liste de départ"
                etats[code] = {"etat": "depart", "source": source, "nombre": len(liste), "detail": str(e)[:200]}
            else:
                liste, source = [], None
                etats[code] = {"etat": "échec", "source": None, "nombre": 0, "detail": str(e)[:200]}
            LOG.warning("Composition %s : %s (%s)", code, source or "aucune liste", str(e)[:160])
        for s in liste:
            societes.append({**s, "source_composition": source})
    # Liste de surveillance : toujours analysée
    vus = {s["ticker"] for s in societes}
    for s in surveillance:
        if s["ticker"] not in vus and (not pays_demandes or s.get("pays") in pays_demandes):
            societes.append({"ticker": s["ticker"], "nom": s.get("nom") or s["ticker"], "pays": s.get("pays"),
                             "secteur": secteur_gics(s.get("secteur")), "poids": 0, "source_composition": "liste de surveillance",
                             "surveillance": True})
        elif s["ticker"] in vus:
            next(x for x in societes if x["ticker"] == s["ticker"])["surveillance"] = True
    # Doublons : même ticker, catégories d'actions (GOOGL / GOOG) ou double cotation (BHP à Sydney et
    # à Johannesburg) : on garde la première occurrence (ordre des pays de la configuration)
    uniques, vus, noms = [], set(), {}
    for s in societes:
        cle_nom = cle_societe(s.get("nom") or "")
        if s["ticker"] in vus:
            continue
        if cle_nom and cle_nom in noms and not s.get("surveillance"):
            LOG.info("Doublon écarté : %s (%s), déjà présent sous %s", s["ticker"], s.get("nom"), noms[cle_nom])
            continue
        vus.add(s["ticker"])
        if cle_nom:
            noms[cle_nom] = s["ticker"]
        uniques.append(s)
    return uniques, etats


MOTS_VIDES = {"sa", "se", "ag", "nv", "plc", "spa", "ab", "the", "de", "la", "et", "and", "co", "inc", "corp", "corporation",
              "ltd", "limited", "holding", "holdings", "group", "class", "cl", "shs", "ord", "adr", "registered", "pref", "pn",
              "on", "pna", "pnb", "unit", "units", "non", "voting", "series", "common", "stock", "tbk", "pcl", "nvdr", "bhd", "asa", "oyj", "publ",
              "ser", "cdi", "cdr", "drc", "gdr", "ads", "adr", "depositary", "receipt", "receipts", "shares", "share", "sa", "nv"}


def cle_societe(nom: str) -> str:
    """Nom normalisé (sans accents, formes juridiques ni catégories d'actions) pour repérer les doublons."""
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", nom.lower()) if unicodedata.category(c) != "Mn")
    mots = sorted({m for m in re.findall(r"[a-z0-9]+", t) if m not in MOTS_VIDES and len(m) > 1})
    return " ".join(mots)


def lire_surveillance(chemin: Path) -> list[dict]:
    try:
        d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        LOG.warning("Liste de surveillance illisible (%s) : ignorée", e)
        return []
    return [{**s, "ticker": str(s["ticker"]).strip().upper()} for s in d.get("societes", [])
            if isinstance(s, dict) and re.match(r"^[A-Z0-9.\-^=]+$", str(s.get("ticker", "")).strip().upper())]
