"""
Sources des flux d'investissement des ETF pays (cotés aux États-Unis).

Chaque émetteur publie chaque jour le nombre de parts en circulation et la valeur liquidative (VL) :
- iShares : page du fonds (données « sharesOutstanding », « navAmount », « totalNetAssetsFundLevel ») ;
- SSGA (SPY) : fichier Excel de l'historique des VL (date, VL, parts, actif net), avec plusieurs mois d'historique ;
- VanEck : fichier Excel de l'historique des VL (date, VL, actif net) ; parts = actif net / VL ;
- Global X : page du fonds (« NAV … As of », « Shares Outstanding », « Net Assets ») ;
- Yahoo Finance (yfinance) : secours et vérification croisée (parts, VL, actif total).

Un relevé : {"date": "AAAA-MM-JJ", "parts": float, "vl": float, "encours": float | None,
             "historique": [[date, parts, vl, encours], ...] (facultatif)}.
Les fonctions lire_* sont pures (testées sur des extraits des vraies réponses).
"""
from __future__ import annotations

import html
import io
import json
import re
from datetime import datetime

from ..commun.journal import journal

LOG = journal("sources-flux")

ISHARES = "https://www.ishares.com"
SSGA = "https://www.ssga.com"
VANECK_HISTO = "https://www.vaneck.com/us/en/investments/{slug}/downloads/fundhistoprices/"
GLOBALX = "https://www.globalxetfs.com"
NAVIGATEUR = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Libellés exacts des sources (recopiés dans chaque indicateur)
NOMS = {
    "ishares": "iShares, page du fonds {etf} (parts en circulation et VL du jour)",
    "ssga": "SSGA, fichier des VL quotidiennes du fonds {etf} (parts en circulation et VL)",
    "vaneck": "VanEck, fichier des VL quotidiennes du fonds {etf} (VL et actif net ; parts = actif net / VL)",
    "globalx": "Global X, page du fonds {etf} (parts en circulation et VL du jour)",
    "yahoo_parts": "Yahoo Finance via yfinance, parts en circulation et VL de {etf}",
}
COURTS = {"ishares": "iShares", "ssga": "SSGA", "vaneck": "VanEck", "globalx": "Global X", "yahoo_parts": "Yahoo Finance"}


def _nombre(texte) -> float:
    return float(str(texte).replace(",", "").replace("$", "").strip())


def _date_us(texte: str) -> str:
    """« Nov 05, 2026 », « Nov 5, 2026 », « 05-Nov-2026 », « 11/05/2026 », « November 05, 2026 » → « 2026-11-05 »."""
    t = re.sub(r"\s+", " ", str(texte).strip().replace(",", ""))
    for fmt in ("%b %d %Y", "%B %d %Y", "%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"date illisible : {texte!r}")


def _verifier(r: dict, nom: str) -> dict:
    if not r.get("parts") or r["parts"] <= 0 or not r.get("vl") or r["vl"] <= 0:
        raise ValueError(f"{nom} : parts ou VL absentes ou nulles")
    return r


# ------------------------------------------------------------------ iShares

def _objet_json(texte: str, cle: str) -> dict | None:
    """Objet JSON {...} qui suit « "cle": » dans la page (premier trouvé)."""
    m = re.search(r'"' + re.escape(cle) + r'"\s*:\s*\{', texte)
    if not m:
        return None
    debut, profondeur = m.end() - 1, 0
    for i in range(debut, min(len(texte), debut + 20000)):
        c = texte[i]
        if c == "{":
            profondeur += 1
        elif c == "}":
            profondeur -= 1
            if profondeur == 0:
                try:
                    return json.loads(texte[debut:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def lire_ishares(page: str) -> dict:
    """Page d'un fonds iShares (données JSON intégrées, entités HTML échappées)."""
    t = html.unescape(page)
    parts = _objet_json(t, "sharesOutstanding")
    vl = _objet_json(t, "navAmount")
    actif = _objet_json(t, "totalNetAssetsFundLevel")
    if not parts or not vl or "value" not in vl:
        raise ValueError("iShares : parts en circulation ou VL absentes de la page")
    date_vl = _date_us(vl.get("formattedAsOfDate") or str(vl.get("asOfDate")))
    date_parts = _date_us(parts["formattedAsOfDate"])
    if date_parts != date_vl:
        raise ValueError(f"iShares : dates différentes pour les parts ({date_parts}) et la VL ({date_vl})")
    r = {"date": date_vl, "parts": _nombre(parts["formattedValue"]), "vl": float(vl["value"]),
         "encours": _nombre(actif["formattedValue"]) if actif and actif.get("formattedValue") else None}
    return _verifier(r, "iShares")


# ------------------------------------------------------------------ Global X

def _texte_visible(page: str) -> str:
    t = re.sub(r"<script\b.*?</script>", " ", page, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", html.unescape(t))
    return re.sub(r"\s+", " ", t)


def _montant(texte: str, unite: str | None) -> float:
    return _nombre(texte) * {"million": 1e6, "m": 1e6, "billion": 1e9, "b": 1e9}.get((unite or "").lower(), 1)


def lire_globalx(page: str) -> dict:
    """Page d'un fonds Global X : « NAV $74.14 As of Nov 5, 2026 », « Shares Outstanding 7,634,975 »,
    « Net Assets $566.04 million »."""
    t = _texte_visible(page)
    vl = re.search(r"\bNAV \$([\d,.]+) As of ([A-Z][a-z]{2,8} \d{1,2}, \d{4})", t)
    parts = re.search(r"Shares Outstanding ([\d,]+)\b", t)
    actif = re.search(r"Net Assets \$([\d,.]+) ?(million|billion|M|B)?\b", t)
    if not vl or not parts:
        raise ValueError("Global X : VL ou parts en circulation absentes de la page")
    r = {"date": _date_us(vl.group(2)), "parts": _nombre(parts.group(1)), "vl": _nombre(vl.group(1)),
         "encours": _montant(actif.group(1), actif.group(2)) if actif else None}
    return _verifier(r, "Global X")


# ------------------------------------------------------------------ fichiers Excel (SSGA, VanEck)

def _lignes_excel(contenu: bytes) -> list[tuple]:
    import warnings
    import openpyxl
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # « Workbook contains no default style »
        classeur = openpyxl.load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
    return [tuple(r) for r in classeur.active.iter_rows(values_only=True)]


def _historique(lignes: list[tuple], colonnes: dict[str, str], nom: str) -> dict:
    """Lit un tableau « Date / NAV / … » ; renvoie le dernier relevé et l'historique (plus récent en dernier)."""
    entete, idx = None, {}
    for i, l in enumerate(lignes):
        valeurs = [str(x).strip() if x is not None else "" for x in l]
        if "Date" in valeurs and "NAV" in valeurs:
            entete = i
            idx = {k: valeurs.index(v) for k, v in colonnes.items() if v in valeurs}
            break
    if entete is None or "vl" not in idx:
        raise ValueError(f"{nom} : en-tête « Date / NAV » introuvable")
    histo = {}
    for l in lignes[entete + 1:]:
        try:
            d = l[idx["date"]]
            jour = d.date().isoformat() if hasattr(d, "date") else _date_us(d)
            vl = _nombre(l[idx["vl"]])
            encours = _nombre(l[idx["encours"]]) if "encours" in idx and l[idx["encours"]] not in (None, "") else None
            parts = _nombre(l[idx["parts"]]) if "parts" in idx and l[idx["parts"]] not in (None, "") else (encours / vl if encours and vl else None)
        except (ValueError, TypeError, IndexError):
            continue
        if parts and vl and parts > 0 and vl > 0:
            histo[jour] = [jour, parts, vl, encours]
    if not histo:
        raise ValueError(f"{nom} : aucune ligne valable")
    serie = [histo[d] for d in sorted(histo)]
    dernier = serie[-1]
    return _verifier({"date": dernier[0], "parts": dernier[1], "vl": dernier[2], "encours": dernier[3], "historique": serie}, nom)


def lire_ssga(contenu: bytes) -> dict:
    """Fichier SSGA navhist : « Date, NAV, Shares Outstanding, Total Net Assets »."""
    return _historique(_lignes_excel(contenu), {"date": "Date", "vl": "NAV", "parts": "Shares Outstanding", "encours": "Total Net Assets"}, "SSGA")


def lire_vaneck(contenu: bytes) -> dict:
    """Fichier VanEck fundhistoprices : « Date, NAV, …, AUM ». Les jours fériés répètent la veille :
    on ne garde qu'un relevé par couple (VL, actif net) identique consécutif."""
    r = _historique(_lignes_excel(contenu), {"date": "Date", "vl": "NAV", "encours": "AUM"}, "VanEck")
    serie, precedent = [], None
    for x in r["historique"]:
        if precedent and (x[2], x[3]) == (precedent[2], precedent[3]):
            continue  # week-end ou jour férié : même ligne recopiée
        serie.append(x)
        precedent = x
    # Parts déduites (actif net / VL arrondie à 4 décimales) : arrondi au millier pour effacer le bruit de calcul
    serie = [[d, round(p / 1000) * 1000, vl, e] for d, p, vl, e in serie]
    r["historique"] = serie
    r["date"], r["parts"], r["vl"], r["encours"] = serie[-1]
    return r


# ------------------------------------------------------------------ fournisseurs

def _methodes_reelles(cls):
    """Ajoutées à FournisseurReel (agents/pays/sources.py)."""

    def _page(self, url):
        return self.t.texte(url, entetes={"User-Agent": NAVIGATEUR})

    def emetteur(self, nom: str, etfs: dict) -> dict:
        """Relevés d'un émetteur pour plusieurs ETF ; un ETF en échec est sauté (journalisé)."""
        res, erreurs = {}, []
        for etf, cfg in etfs.items():
            try:
                if nom == "ishares":
                    res[etf] = lire_ishares(self._page(ISHARES + cfg["page"]))
                elif nom == "globalx":
                    res[etf] = lire_globalx(self._page(GLOBALX + cfg["page"]))
                elif nom == "ssga":
                    res[etf] = lire_ssga(self.t.octets(SSGA + cfg["fichier"], entetes={"User-Agent": NAVIGATEUR}))
                elif nom == "vaneck":
                    # VanEck dépose un cookie puis redirige : la session de téléchargement les suit
                    contenu = self.t.octets(VANECK_HISTO.format(slug=cfg["slug"]), entetes={"User-Agent": NAVIGATEUR})
                    if contenu[:2] != b"PK":
                        raise ValueError("fichier VanEck non servi (vérification par cookie)")
                    res[etf] = lire_vaneck(contenu)
            except Exception as e:  # un fonds en échec n'empêche pas les autres
                erreurs.append(f"{etf} : {str(e)[:120]}")
                LOG.warning("Flux %s %s indisponible : %s", nom, etf, str(e)[:160])
        if not res and erreurs:
            raise RuntimeError(" ; ".join(erreurs[:3]))
        return res

    def yahoo_parts(self, symboles: list[str]) -> dict:
        """Parts en circulation, VL et actif total (Yahoo Finance) ; date = dernière séance cotée."""
        import time
        import yfinance as yf
        res = {}
        for s in symboles:
            try:
                info = yf.Ticker(s).info
                parts, vl = info.get("sharesOutstanding"), info.get("navPrice") or info.get("previousClose")
                quand = info.get("regularMarketTime")
                if parts and vl and quand:
                    from datetime import timezone
                    res[s] = {"date": datetime.fromtimestamp(int(quand), timezone.utc).date().isoformat(),
                              "parts": float(parts), "vl": float(vl), "encours": float(info["totalAssets"]) if info.get("totalAssets") else None}
            except Exception as e:  # Yahoo refuse parfois ces requêtes (401, 429)
                LOG.warning("Parts Yahoo indisponibles pour %s (%s)", s, str(e)[:120])
            time.sleep(0.7)
        return res

    cls._page = _page
    cls.emetteur = emetteur
    cls.yahoo_parts = yahoo_parts
    return cls


def _methodes_test(cls):
    """Ajoutées à FournisseurTest : flux_<émetteur>.json et flux_yahoo_parts.json dans les données de test."""

    def emetteur(self, nom: str, etfs: dict) -> dict:
        donnees = self._lire(f"flux_{nom}")
        return {etf: donnees[etf] for etf in etfs if etf in donnees}

    def yahoo_parts(self, symboles):
        donnees = self._lire("flux_yahoo_parts")
        return {s: donnees[s] for s in symboles if s in donnees}

    cls.emetteur = emetteur
    cls.yahoo_parts = yahoo_parts
    return cls
