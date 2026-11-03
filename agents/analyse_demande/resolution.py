"""
Résolution de la saisie (« ASML », « MC.PA », « 7203.T », « Hermès ») en symbole Yahoo Finance.

- Ticker reconnu tel quel dans la recherche Yahoo : retenu ; les autres cotations sont indiquées.
- Nom (ou ticker absent de la recherche) : actions proposées par la recherche Yahoo, et retenue la plus
  liquide (montant moyen échangé sur 3 mois, converti en dollars) ; les autres sont indiquées.
- Aucune action : « introuvable », avec des suggestions (autres résultats Yahoo, noms proches dans l'univers).
"""
from __future__ import annotations

import difflib
import re
import statistics
import unicodedata

from ..entreprises import comptes as C
from ..entreprises import univers as U

RE_TICKER = re.compile(r"^[A-Za-z0-9]{1,10}([.\-][A-Za-z0-9]{1,4})?$")
RE_TITRE = re.compile(r"^\s*analyse\s*:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)


def saisie(titre: str, longueur_max: int = 60) -> str | None:
    """Texte après « Analyse : » (None si le titre ne suit pas ce format)."""
    m = RE_TITRE.match((titre or "").replace(" ", " ").replace(" ", " "))
    if not m:
        return None
    t = " ".join(m.group(1).split())
    t = "".join(c for c in t if c.isprintable())
    return t[:longueur_max] or None


def normaliser(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


def ressemble_a_un_ticker(t: str) -> bool:
    return bool(RE_TICKER.match(t)) and " " not in t


def pays_du_symbole(symbole: str, suffixes: dict, pays_info: str | None = None) -> str:
    """Pays de la société : pays déclaré par Yahoo quand il est connu, sinon place de cotation (sans suffixe : États-Unis)."""
    if pays_info:
        code = U.PAYS_PAR_LOCALISATION.get(pays_info.strip().lower())
        if code:
            return code
    for suf in sorted(suffixes, key=len, reverse=True):
        if symbole.upper().endswith(suf.upper()):
            return suffixes[suf]
    return "US"


def liquidite_usd(points: list, devise: str | None, change: dict) -> float | None:
    """Montant moyen échangé par séance (63 dernières), en dollars."""
    majeure, centimes = C.devise_majeure(devise)
    echanges = [c * v for _, c, v in points[-63:] if v]
    fx = change.get(majeure)
    if not echanges or not fx:
        return None
    return statistics.fmean(echanges) / centimes * fx


def candidat(q: dict) -> dict:
    return {"symbole": q.get("symbol"), "nom": q.get("longname") or q.get("shortname") or q.get("symbol"),
            "place": q.get("exchDisp") or q.get("exchange"), "secteur": q.get("sector") or q.get("sectorDisp"),
            "industrie": q.get("industry") or q.get("industryDisp")}


def resoudre(texte: str, recherche, cours, change_fn, noms_univers: list[tuple[str, str]], candidats_max: int = 6) -> dict:
    """recherche(q) → résultats Yahoo (liste de « quotes ») ; cours(symbole) → (points [(date, clôture, volume)], devise) ;
    change_fn(devises) → {devise: dollars} ; noms_univers : [(ticker, nom)] des sociétés déjà analysées."""
    quotes = []
    # La recherche Yahoo ignore les mots accentués (« Hermès » ne donne rien, « Hermes » oui) : second essai sans accents
    sans_accents = "".join(ch for ch in unicodedata.normalize("NFD", texte) if unicodedata.category(ch) != "Mn")
    essais = [texte, *([sans_accents] if sans_accents != texte else []),
              *([texte.upper()] if ressemble_a_un_ticker(texte) and texte != texte.upper() else [])]
    for q in essais:
        try:
            quotes = recherche(q) or []
        except Exception:
            quotes = []
        if quotes:
            break
    actions = [q for q in quotes if q.get("quoteType") == "EQUITY" and q.get("symbol")]
    exact = next((q for q in actions if q["symbol"].upper() == texte.upper()), None)

    if ressemble_a_un_ticker(texte) and not exact:
        # Ticker absent de la recherche (fréquent pour certaines places) : interrogation directe
        try:
            points, devise = cours(texte.upper())
        except Exception:
            points, devise = [], None
        if points:
            exact = {"symbol": texte.upper(), "quoteType": "EQUITY", "longname": None}
    if exact:
        autres = [candidat(q) for q in actions if q["symbol"] != exact["symbol"]][:candidats_max - 1]
        return {"statut": "ok", "methode": "ticker", "choisi": candidat(exact), "autres": autres}

    if not actions:
        sugg = [f"{q.get('symbol')} ({q.get('longname') or q.get('shortname') or q.get('typeDisp') or '?'})"
                for q in quotes if q.get("symbol")][:3]
        cible = normaliser(texte)
        proches = difflib.get_close_matches(cible, [normaliser(n) for _, n in noms_univers], n=3, cutoff=0.6)
        for p in proches:
            t, n = next((t, n) for t, n in noms_univers if normaliser(n) == p)
            sugg.append(f"{t} ({n})")
        return {"statut": "introuvable", "suggestions": list(dict.fromkeys(sugg))[:5]}

    liste = actions[:candidats_max]
    mesures = []
    devises = set()
    for q in liste:
        try:
            points, devise = cours(q["symbol"])
        except Exception:
            points, devise = [], None
        mesures.append((q, points, devise))
        devises.add(C.devise_majeure(devise)[0])
    try:
        change = change_fn({d for d in devises if d})
    except Exception:
        change = {"USD": 1.0}
    notes = []
    for q, points, devise in mesures:
        c = candidat(q)
        liq = liquidite_usd(points, devise, change) if points else None
        c["liquidite_musd"] = round(liq / 1e6, 2) if liq else None
        notes.append(c)
    cotes = [c for c in notes if c["liquidite_musd"] is not None]
    if not cotes:
        return {"statut": "introuvable", "suggestions": [f"{c['symbole']} ({c['nom']})" for c in notes][:5]}
    choisi = max(cotes, key=lambda c: c["liquidite_musd"])
    autres = sorted((c for c in notes if c is not choisi), key=lambda c: -(c["liquidite_musd"] or 0))
    return {"statut": "ok", "methode": "nom", "choisi": choisi, "autres": autres}
