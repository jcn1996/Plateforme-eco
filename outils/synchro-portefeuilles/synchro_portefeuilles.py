"""Synchronisation quotidienne des portefeuilles réels, CHIFFRÉE de bout en bout.

À copier dans un dépôt GitHub PRIVÉ (voir README.md de ce dossier), jamais dans le
dépôt public de l'appli. Le workflow quotidien (workflow-synchro.yml) :

1. récupère les positions :
   - Interactive Brokers : Flex Web Service (secrets IBKR_FLEX_TOKEN, IBKR_FLEX_QUERY_ID) ;
   - eToro : API publique officielle, clés en lecture seule (secrets ETORO_API_KEY, ETORO_USER_KEY) ;
   - BoursoBank : pas d'API, import CSV manuel dans l'appli ;
2. ajoute les cours hebdomadaires sur 1 an des titres détenus (Yahoo Finance, pour
   les corrélations calculées dans l'appli) ;
3. chiffre le tout en AES-256-GCM, clé dérivée par PBKDF2-SHA-256 (600 000 itérations)
   du mot de passe connu seulement de l'utilisateur (secret PORTEFEUILLE_MOT_DE_PASSE) ;
4. écrit le fichier chiffré (portefeuilles.chiffre.json), publié sur la branche « synchro »
   du dépôt privé. L'appli le télécharge avec un jeton en lecture seule et le déchiffre
   sur l'appareil.

Rien n'est jamais écrit en clair : ni sur disque, ni dans les journaux du workflow
(seuls des nombres de lignes y apparaissent).

Usage : python synchro_portefeuilles.py --sortie portefeuilles.chiffre.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

FORMAT_CHIFFRE = "salle-controle/portefeuilles-chiffres"
FORMAT_CONTENU = "salle-controle/synchro-portefeuilles"
ITERATIONS = 600_000
AGENT = "salle-controle-synchro/1.0 (Python urllib)"

IBKR_ENVOI = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
IBKR_RELEVE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
ETORO_API = "https://public-api.etoro.com"


# ------------------------------------------------------------------ chiffrement

def chiffrer(objet: dict, mot_de_passe: str, iterations: int = ITERATIONS) -> dict:
    """Même enveloppe que js/portefeuilles-chiffrement.js (WebCrypto)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    if not mot_de_passe:
        raise ValueError("mot de passe vide")
    sel = os.urandom(16)
    iv = os.urandom(12)
    cle = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sel, iterations=iterations).derive(mot_de_passe.encode("utf-8"))
    clair = json.dumps(objet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    chiffre = AESGCM(cle).encrypt(iv, clair, None)  # texte chiffré + étiquette de 16 octets, comme WebCrypto
    b64 = lambda o: base64.b64encode(o).decode("ascii")  # noqa: E731
    return {
        "format": FORMAT_CHIFFRE,
        "version": 1,
        "kdf": {"nom": "PBKDF2", "hachage": "SHA-256", "iterations": iterations, "sel": b64(sel)},
        "chiffrement": {"nom": "AES-256-GCM", "iv": b64(iv)},
        "cree_le": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "donnees": b64(chiffre),
    }


def dechiffrer(enveloppe: dict, mot_de_passe: str) -> dict:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = enveloppe["kdf"]
    cle = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(kdf["sel"]), iterations=int(kdf["iterations"])).derive(mot_de_passe.encode("utf-8"))
    clair = AESGCM(cle).decrypt(base64.b64decode(enveloppe["chiffrement"]["iv"]), base64.b64decode(enveloppe["donnees"]), None)
    return json.loads(clair)


# ------------------------------------------------------------------ outils

def nombre(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None  # NaN → None


def masquer(compte: str) -> str:
    """U1234567 → U***4567 : l'identifiant complet du compte n'est jamais publié."""
    c = str(compte or "")
    return f"{c[:1]}***{c[-4:]}" if len(c) > 5 else "***"


def http(url: str, entetes: dict | None = None, delai: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, **(entetes or {})})
    with urllib.request.urlopen(req, timeout=delai) as r:  # noqa: S310 (adresses fixes en https)
        return r.read()


# Place IBKR → suffixe Yahoo Finance
SUFFIXES_IBKR = {
    "SBF": ".PA", "AEB": ".AS", "ENEXT.BE": ".BR", "BVL": ".LS", "IBIS": ".DE", "IBIS2": ".DE", "XETRA": ".DE", "FWB": ".F", "FWB2": ".F",
    "LSE": ".L", "LSEETF": ".L", "BVME": ".MI", "BVME.ETF": ".MI", "BM": ".MC", "EBS": ".SW", "SWX": ".SW", "VIRTX": ".SW",
    "SFB": ".ST", "KFB": ".CO", "HEX": ".HE", "OSE": ".OL", "VSE": ".VI", "ISED": ".IR", "TSEJ": ".T", "SEHK": ".HK",
    "TSE": ".TO", "VENTURE": ".V", "ASX": ".AX", "SGX": ".SI", "KSE": ".KS", "NSE": ".NS",
    "NASDAQ": "", "NYSE": "", "ARCA": "", "AMEX": "", "BATS": "", "ISLAND": "", "PINK": "", "IEX": "",
}
TYPES_IBKR = {"STK": "action", "ETF": "etf", "FUND": "fonds", "BOND": "obligation", "CASH": "liquidites", "CRYPTO": "crypto", "OPT": "autre", "FUT": "autre", "WAR": "autre"}


def symbole_yahoo_ibkr(symbole: str, place: str) -> str | None:
    if not symbole:
        return None
    s = symbole.strip().replace(" ", "-").replace("/", "-")
    suffixe = SUFFIXES_IBKR.get((place or "").upper())
    if suffixe is None:
        return s if not place else None
    return f"{s}{suffixe}"


# ------------------------------------------------------------------ Interactive Brokers

def ibkr_telecharger(jeton: str, requete: str, tentatives: int = 12) -> bytes:
    """Flex Web Service : demande du relevé, puis récupération (le relevé peut prendre quelques secondes)."""
    q = urllib.parse.urlencode({"t": jeton, "q": requete, "v": "3"})
    racine = ET.fromstring(http(f"{IBKR_ENVOI}?{q}"))
    if racine.findtext("Status") != "Success":
        raise RuntimeError(f"IBKR : demande refusée (code {racine.findtext('ErrorCode')} : {racine.findtext('ErrorMessage')})")
    reference = racine.findtext("ReferenceCode")
    base = racine.findtext("Url") or IBKR_RELEVE
    for i in range(tentatives):
        time.sleep(5 if i == 0 else 10)
        brut = http(f"{base}?{urllib.parse.urlencode({'t': jeton, 'q': reference, 'v': '3'})}")
        if b"<FlexQueryResponse" in brut[:500] or b"<FlexStatements" in brut[:500]:
            return brut
        r = ET.fromstring(brut)
        code = r.findtext("ErrorCode")
        if code in ("1019", "1018", "1021"):  # relevé en cours de génération / trop de requêtes / réessayer
            continue
        raise RuntimeError(f"IBKR : relevé indisponible (code {code} : {r.findtext('ErrorMessage')})")
    raise RuntimeError("IBKR : relevé toujours en cours de génération, réessayer plus tard")


def ibkr_positions(xml: bytes) -> list[dict]:
    """Relevé Flex (XML) → un portefeuille par compte. Section requise : « Open Positions » (niveau Summary)."""
    racine = ET.fromstring(xml)
    resultat = []
    for releve in racine.iter("FlexStatement"):
        compte = releve.get("accountId", "")
        info = releve.find("AccountInformation")
        devise_base = (info.get("currency") if info is not None else None) or "EUR"
        date = releve.get("toDate") or releve.get("whenGenerated", "")[:8]
        if date and len(date) == 8 and date.isdigit():
            date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        lignes = []
        for p in releve.iter("OpenPosition"):
            if (p.get("levelOfDetail") or "SUMMARY").upper() not in ("SUMMARY", ""):
                continue
            quantite = nombre(p.get("position"))
            if not quantite:
                continue
            fx = nombre(p.get("fxRateToBase")) or 1.0
            valeur = nombre(p.get("positionValue"))
            categorie = (p.get("assetCategory") or "STK").upper()
            sous = (p.get("subCategory") or "").upper()
            type_ligne = "etf" if sous == "ETF" else TYPES_IBKR.get(categorie, "autre")
            lignes.append({
                "nom": p.get("description") or p.get("symbol"),
                "isin": p.get("isin") or None,
                "ticker": symbole_yahoo_ibkr(p.get("symbol", ""), p.get("listingExchange", "")),
                "type": type_ligne,
                "quantite": quantite,
                "prix_revient": nombre(p.get("costBasisPrice")),
                "cours": nombre(p.get("markPrice")),
                "devise": p.get("currency") or None,
                # valeur dans la devise de base du compte (à régler en EUR dans IBKR)
                "valeur": round(valeur * fx, 2) if valeur is not None else None,
                "date": date or None,
            })
        # Liquidités (section « Cash Report », ligne de synthèse en devise de base)
        for c in releve.iter("CashReportCurrency"):
            if c.get("currency") == "BASE_SUMMARY":
                cash = nombre(c.get("endingCash"))
                if cash:
                    lignes.append({"nom": "Liquidités", "isin": None, "ticker": None, "type": "liquidites", "quantite": None, "prix_revient": None, "cours": None, "devise": devise_base, "valeur": round(cash, 2), "date": date or None})
        resultat.append({"cle": f"ibkr-{masquer(compte)}", "nom": f"Interactive Brokers {masquer(compte)}", "courtier": "IBKR", "type": "cto", "devise_base": devise_base, "lignes": lignes})
    return resultat


# ------------------------------------------------------------------ eToro

def etoro_get(chemin: str, cle_api: str, cle_utilisateur: str) -> dict:
    entetes = {"x-api-key": cle_api, "x-user-key": cle_utilisateur, "x-request-id": str(uuid.uuid4()), "Accept": "application/json"}
    return json.loads(http(f"{ETORO_API}{chemin}", entetes))


def _champ(d: dict, *noms):
    """L'API eToro mélange les casses (instrumentID / instrumentId) : on accepte les deux."""
    for n in noms:
        if n in d and d[n] is not None:
            return d[n]
    return None


def etoro_positions(portefeuille: dict, instruments: dict, eurusd: float | None, date: str) -> list[dict]:
    """Réponse de /api/v1/trading/info/real/pnl → lignes agrégées par instrument (copies de traders incluses)."""
    cp = portefeuille.get("clientPortfolio") or portefeuille
    positions = list(cp.get("positions") or [])
    for m in cp.get("mirrors") or []:
        positions.extend(m.get("positions") or [])
    agregat: dict[int, dict] = {}
    for p in positions:
        iid = _champ(p, "instrumentID", "instrumentId")
        if iid is None:
            continue
        sens = 1 if _champ(p, "isBuy") in (True, None) else -1
        unites = (nombre(_champ(p, "units")) or 0) * sens
        investi = nombre(_champ(p, "amount", "initialAmountInDollars")) or 0
        pnl_obj = _champ(p, "unrealizedPnL") or {}
        pnl = nombre(pnl_obj.get("pnL")) if isinstance(pnl_obj, dict) else nombre(_champ(p, "pnL", "netProfit"))
        a = agregat.setdefault(int(iid), {"unites": 0.0, "investi": 0.0, "pnl": 0.0, "cout": 0.0, "cours": None, "levier": False})
        a["unites"] += unites
        a["investi"] += investi
        a["pnl"] += pnl or 0
        a["cout"] += (nombre(_champ(p, "openRate")) or 0) * abs(unites)
        if isinstance(pnl_obj, dict) and pnl_obj.get("closeRate") is not None:
            a["cours"] = nombre(pnl_obj.get("closeRate"))
        if (nombre(_champ(p, "leverage")) or 1) > 1:
            a["levier"] = True
    lignes = []
    for iid, a in agregat.items():
        inst = instruments.get(iid, {})
        symbole = inst.get("symbolFull") or str(iid)
        type_inst = inst.get("instrumentTypeID")
        valeur_usd = a["investi"] + a["pnl"]
        crypto = type_inst == 10
        lignes.append({
            "nom": inst.get("instrumentDisplayName") or symbole,
            "isin": None,
            "ticker": f"{symbole}-USD" if crypto and "-" not in symbole else symbole,
            "type": "crypto" if crypto else ("etf" if type_inst == 6 else "action"),
            "quantite": round(a["unites"], 8),
            "prix_revient": round(a["cout"] / abs(a["unites"]), 6) if a["unites"] else None,
            "cours": a["cours"],
            "devise": "USD",
            "valeur": round(valeur_usd / eurusd, 2) if eurusd else None,
            "date": date,
            **({"note": "position à effet de levier (CFD)"} if a["levier"] else {}),
        })
    return lignes


def etoro(cle_api: str, cle_utilisateur: str, eurusd: float | None) -> list[dict]:
    portefeuille = etoro_get("/api/v1/trading/info/real/pnl", cle_api, cle_utilisateur)
    cp = portefeuille.get("clientPortfolio") or portefeuille
    ids = {int(_champ(p, "instrumentID", "instrumentId")) for p in (cp.get("positions") or []) + [x for m in cp.get("mirrors") or [] for x in m.get("positions") or []] if _champ(p, "instrumentID", "instrumentId") is not None}
    instruments = {}
    liste = sorted(ids)
    for i in range(0, len(liste), 50):
        q = urllib.parse.urlencode({"instrumentIds": ",".join(map(str, liste[i:i + 50]))})
        r = etoro_get(f"/api/v1/market-data/instruments?{q}", cle_api, cle_utilisateur)
        for x in r.get("instrumentDisplayDatas") or []:
            instruments[int(_champ(x, "instrumentID", "instrumentId"))] = x
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lignes = etoro_positions(portefeuille, instruments, eurusd, date)
    credit = nombre(cp.get("credit"))
    if credit and eurusd:
        lignes.append({"nom": "Liquidités", "isin": None, "ticker": None, "type": "liquidites", "quantite": None, "prix_revient": None, "cours": None, "devise": "EUR", "valeur": round(credit / eurusd, 2), "date": date})
    return [{"cle": "etoro", "nom": "eToro", "courtier": "eToro", "type": "cto", "devise_base": "USD", "lignes": lignes}]


# ------------------------------------------------------------------ cours (Yahoo Finance)

def eurusd_du_jour() -> float | None:
    try:
        import yfinance as yf
        h = yf.Ticker("EURUSD=X").history(period="5d")
        return float(h["Close"].dropna().iloc[-1])
    except Exception:  # noqa: BLE001
        return None


def historiques(symboles: list[str]) -> dict:
    """Cours hebdomadaires sur 1 an : [[date, clôture]] par symbole (pour les corrélations dans l'appli)."""
    res = {}
    try:
        import yfinance as yf
    except ImportError:
        return res
    for s in sorted(set(x for x in symboles if x)):
        try:
            h = yf.Ticker(s).history(period="1y", interval="1wk", auto_adjust=True)
            serie = [[d.strftime("%Y-%m-%d"), round(float(c), 4)] for d, c in h["Close"].dropna().items()]
            if len(serie) >= 20:
                res[s] = serie
        except Exception:  # noqa: BLE001
            continue
    return res


# ------------------------------------------------------------------ programme

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sortie", default="portefeuilles.chiffre.json")
    ap.add_argument("--sans-historiques", action="store_true", help="ne pas télécharger les cours sur 1 an")
    args = ap.parse_args(argv)

    mot_de_passe = os.environ.get("PORTEFEUILLE_MOT_DE_PASSE", "")
    if len(mot_de_passe) < 12:
        print("::error::Secret PORTEFEUILLE_MOT_DE_PASSE absent ou trop court (12 caractères minimum).")
        return 1

    portefeuilles, erreurs = [], []
    eurusd = eurusd_du_jour()

    if os.environ.get("IBKR_FLEX_TOKEN") and os.environ.get("IBKR_FLEX_QUERY_ID"):
        try:
            portefeuilles += ibkr_positions(ibkr_telecharger(os.environ["IBKR_FLEX_TOKEN"], os.environ["IBKR_FLEX_QUERY_ID"]))
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"IBKR : {e}")
    if os.environ.get("ETORO_API_KEY") and os.environ.get("ETORO_USER_KEY"):
        try:
            portefeuilles += etoro(os.environ["ETORO_API_KEY"], os.environ["ETORO_USER_KEY"], eurusd)
        except urllib.error.HTTPError as e:
            erreurs.append(f"eToro : HTTP {e.code} (clés ou droits « Read » à vérifier)")
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"eToro : {e}")

    for e in erreurs:
        print(f"::warning::{e}")
    if not portefeuilles:
        print("::error::Aucun portefeuille récupéré : fichier chiffré inchangé.")
        return 1

    symboles = [l["ticker"] for p in portefeuilles for l in p["lignes"] if l.get("ticker") and l.get("type") != "liquidites"]
    contenu = {
        "format": FORMAT_CONTENU,
        "version": 1,
        "genere_le": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "eurusd": eurusd,
        "portefeuilles": portefeuilles,
        "historiques": {} if args.sans_historiques else historiques(symboles),
        "erreurs": erreurs,
    }
    with open(args.sortie, "w", encoding="utf-8") as f:
        json.dump(chiffrer(contenu, mot_de_passe), f)
    # Journal : uniquement des nombres, jamais de noms, quantités ni montants
    print(f"Fichier chiffré écrit : {len(portefeuilles)} portefeuille(s), {sum(len(p['lignes']) for p in portefeuilles)} ligne(s), {len(contenu['historiques'])} historique(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
