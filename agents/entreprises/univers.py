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


# --------------------------------------------------------------- composition

class Composition:
    def __init__(self, telechargeur, config: dict):
        self.t = telechargeur
        self.cfg = config["univers"]

    def etf_ishares(self, etf: str, pays: str) -> list[dict]:
        info = self.cfg["ishares"].get(etf)
        if not info:
            raise ValueError(f"URL iShares inconnue pour {etf}")
        url = self.cfg["url_ishares"].format(id=info["id"], slug=info["slug"], t=etf)
        return lire_ishares(self.t.texte(url), pays)

    def etf_ssga(self, etf: str) -> list[dict]:
        url = self.cfg["ssga"][etf]
        r = self.t.session.get(url, timeout=60)
        r.raise_for_status()
        return lire_ssga(r.content)

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

    def pays(self, code: str, plafond: int | None) -> tuple[list[dict], str]:
        """Liste des sociétés d'un pays et source utilisée. Lève une erreur si toutes les sources échouent."""
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
            try:
                return self.etf_ishares(etf, code)[:plafond], f"iShares {etf}"
            except Exception as e:
                erreurs.append(f"iShares {etf} : {str(e)[:120]}")
        try:
            return self.filtre_yahoo(code, plafond)[:plafond], "filtre d'actions Yahoo (plus grosses capitalisations)"
        except Exception as e:
            erreurs.append(f"filtre Yahoo : {str(e)[:120]}")
        raise RuntimeError(" ; ".join(erreurs))


def construire(composition: Composition | None, config: dict, connu: dict | None, depart: list[dict],
               surveillance: list[dict], pays_demandes: list[str] | None = None) -> tuple[list[dict], dict]:
    """Univers complet (avant filtre de capitalisation et de liquidité) et état des sources par pays."""
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
            if anciens.get(code):
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
    # Doublons (une société présente dans deux fichiers) : on garde la première occurrence
    uniques, vus = [], set()
    for s in societes:
        if s["ticker"] not in vus:
            vus.add(s["ticker"])
            uniques.append(s)
    return uniques, etats


def lire_surveillance(chemin: Path) -> list[dict]:
    try:
        d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        LOG.warning("Liste de surveillance illisible (%s) : ignorée", e)
        return []
    return [{**s, "ticker": str(s["ticker"]).strip().upper()} for s in d.get("societes", [])
            if isinstance(s, dict) and re.match(r"^[A-Z0-9.\-^=]+$", str(s.get("ticker", "")).strip().upper())]
