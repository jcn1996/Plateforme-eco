"""
Agent marchés (sans IA) : met à jour data/marches.json avec de vrais cours.

Pour chaque actif : dernier cours, variation du jour (%), variation sur 1 an (%),
heure du cours et statut « ouvert » / « fermé ».

Ordre des sources :
  1. Yahoo Finance (via yfinance) ;
  2. Stooq (CSV gratuit) si Yahoo échoue ;
  3. sinon, la dernière valeur connue est conservée avec son heure, marquée « ancienne ».

Le fichier n'est réécrit que si les données ont changé (pas de commit inutile).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.commun import sante
from agents.commun.journal import journal
from agents.commun.sortie import enveloppe, ecrire_json, lire_json
from agents.commun.telechargement import ErreurSource, Telechargeur

LOG = journal("agent-marches")
RACINE = Path(__file__).resolve().parents[2]
FICHIER = RACINE / "data" / "marches.json"
CACHE = RACINE / "agents" / ".cache" / "marches"

# Ordre exact d'affichage dans le bandeau
ACTIFS = [
    {"symbole": "^NDX", "stooq": "^ndx", "nom": "Nasdaq 100", "categorie": "indices", "unite": "pts",
     "hors_seance": {"type": "future", "symbole": "NQ=F", "calendrier": "XNYS"}},
    {"symbole": "^GSPC", "stooq": "^spx", "nom": "S&P 500", "categorie": "indices", "unite": "pts",
     "hors_seance": {"type": "future", "symbole": "ES=F", "calendrier": "XNYS"}},
    {"symbole": "GC=F", "stooq": "gc.f", "nom": "Or", "categorie": "matieres_premieres", "unite": "$/once"},
    {"symbole": "CL=F", "stooq": "cl.f", "nom": "Pétrole WTI", "categorie": "matieres_premieres", "unite": "$/baril"},
    {"symbole": "BTC-USD", "stooq": "btcusd", "nom": "Bitcoin", "categorie": "crypto", "unite": "$", "continu": True},
    {"symbole": "EURUSD=X", "stooq": "eurusd", "nom": "EUR/USD", "categorie": "devises", "unite": ""},
    # Pas de contrat à terme CAC 40 sur Yahoo (FCE=F vide ; CAFME.PA n'est calculé qu'en séance) : dernière clôture hors séance
    {"symbole": "^FCHI", "stooq": "^cac", "nom": "CAC 40", "categorie": "indices", "unite": "pts",
     "hors_seance": {"type": "cloture", "calendrier": "XPAR"}},
    {"symbole": "URTH", "stooq": "urth.us", "nom": "MSCI World (ETF URTH)", "categorie": "indices", "unite": "$",
     "hors_seance": {"type": "prepost", "calendrier": "XNYS"}},
]
# Un cours avant ouverture / après clôture plus ancien que ceci n'est plus affiché (on revient à la dernière clôture)
AGE_MAX_HORS_SEANCE = timedelta(hours=4)

# Au-delà de cet âge, un cours n'est plus considéré comme « en direct » (cours différés d'environ 15 min)
AGE_MAX_OUVERT = timedelta(minutes=45)
FUSEAU_STOOQ = ZoneInfo("Europe/Warsaw")  # Stooq horodate ses cours à l'heure polonaise


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def calculer(actif: dict, prix: float, heure: datetime, clotures: list[tuple[date, float]],
             ouvert: bool, source: str) -> dict:
    """Assemble une entrée du fichier à partir du dernier cours et des clôtures quotidiennes
    (triées, la dernière étant la séance du dernier cours)."""
    clotures = sorted(clotures)
    jour_cours = heure.date()
    # Clôture précédente : la dernière séance antérieure à celle du dernier cours
    precedentes = [c for d, c in clotures if d < jour_cours]
    veille = precedentes[-1] if precedentes else None
    # Il y a un an : dernière clôture à date ≤ (jour du cours − 365 jours)
    il_y_a_un_an = [c for d, c in clotures if d <= jour_cours - timedelta(days=365)]
    an = il_y_a_un_an[-1] if il_y_a_un_an else None

    def pct(ref):
        return round((prix / ref - 1) * 100, 2) if ref else None

    return {
        "categorie": actif["categorie"],
        "nom": actif["nom"],
        "symbole": actif["symbole"],
        "valeur": round(float(prix), 4 if actif["categorie"] == "devises" else 2),
        "unite": actif["unite"],
        "variation": pct(veille),
        "variation_1an": pct(an),
        "heure": iso(heure),
        "statut": "ouvert" if ouvert else "fermé",
        "source": source,
        "ancienne": False,
    }


def est_ouvert(actif: dict, heure: datetime, maintenant: datetime, debut=None, fin=None) -> bool:
    """Ouvert si l'on est dans la séance du jour (quand elle est connue) et que le cours est récent."""
    if actif.get("continu"):
        return maintenant - heure < timedelta(hours=2)  # le Bitcoin cote en continu
    if debut is not None and fin is not None and not (debut <= maintenant < fin):
        return False
    return maintenant - heure < AGE_MAX_OUVERT


# --------------------------- Heures de séance (jours fériés compris) ---------------------------

_CALENDRIERS = {}


def calendrier(code: str):
    """Calendrier d'une place (exchange_calendars : XNYS = New York, XPAR = Euronext Paris), ou None si indisponible."""
    if code not in _CALENDRIERS:
        try:
            import exchange_calendars as xc
            _CALENDRIERS[code] = xc.get_calendar(code)
        except Exception as e:  # bibliothèque absente : on retombe sur les horaires renvoyés par Yahoo
            LOG.warning("Calendrier %s indisponible (%s)", code, str(e)[:80])
            _CALENDRIERS[code] = None
    return _CALENDRIERS[code]


def marche_ouvert(code: str, t: datetime) -> bool | None:
    """Vrai pendant une séance de la place (jours fériés et demi-séances compris) ; None si inconnu."""
    cal = calendrier(code)
    if cal is None:
        return None
    import pandas as pd
    try:
        return bool(cal.is_open_on_minute(pd.Timestamp(t).tz_convert("UTC").floor("min"), ignore_breaks=True))
    except Exception:
        return None


def derniere_cloture_seance(code: str, t: datetime) -> datetime | None:
    """Heure de clôture de la dernière séance terminée avant t."""
    cal = calendrier(code)
    if cal is None:
        return None
    import pandas as pd
    try:
        return cal.previous_close(pd.Timestamp(t).tz_convert("UTC").floor("min")).to_pydatetime()
    except Exception:
        return None


def avec_contrat_a_terme(entree: dict, actif: dict, prix: float, heure: datetime, clotures: list[tuple[date, float]]) -> dict:
    """Hors séance : le contrat à terme remplace l'indice ; variations calculées par rapport à la dernière
    clôture de l'indice (tendance attendue à l'ouverture)."""
    clotures = sorted(clotures)
    ref_jour, ref = clotures[-1]
    an = [c for d, c in clotures if d <= ref_jour - timedelta(days=365)]
    hs = actif["hors_seance"]
    return {**entree, "valeur": round(float(prix), 2), "heure": iso(heure), "statut": "fermé",
            "variation": round((prix / ref - 1) * 100, 2) if ref else None,
            "variation_1an": round((prix / an[-1] - 1) * 100, 2) if an else None,
            "contrat_a_terme": {"symbole": hs["symbole"], "cloture_indice": round(ref, 2), "date_cloture": ref_jour.isoformat()},
            "source": "Yahoo Finance (contrat à terme)"}


def avec_hors_seance(entree: dict, prix: float, heure: datetime, clotures: list[tuple[date, float]]) -> dict:
    """Cours avant ouverture ou après clôture (URTH) : variation par rapport à la dernière clôture de séance."""
    ref_jour, ref = sorted(clotures)[-1]
    return {**entree, "valeur": round(float(prix), 2), "heure": iso(heure), "statut": "hors séance",
            "variation": round((prix / ref - 1) * 100, 2) if ref else None,
            "hors_seance": {"cloture": round(ref, 2), "date_cloture": ref_jour.isoformat()}}


def choisir_hors_seance(actif: dict, entree: dict, clotures, maintenant: datetime, cotation_future=None, barres=None) -> dict:
    """Décide l'affichage d'un indice selon l'heure : séance → indice ; hors séance → contrat à terme,
    cours hors séance (prepost) ou dernière clôture « fermé ». Fonction pure (testée avec des heures simulées)."""
    hs = actif.get("hors_seance")
    if not hs:
        return entree
    ouvert = marche_ouvert(hs["calendrier"], maintenant)
    if ouvert is None:
        return entree  # calendrier indisponible : statut d'après les horaires Yahoo
    if ouvert:
        return {**entree, "statut": "ouvert"}
    entree = {**entree, "statut": "fermé"}
    if hs["type"] == "future" and cotation_future:
        return avec_contrat_a_terme(entree, actif, cotation_future[0], cotation_future[1], clotures)
    if hs["type"] == "prepost" and barres:
        cloture = derniere_cloture_seance(hs["calendrier"], maintenant)
        heure, prix = barres[-1]
        if cloture and heure > cloture and maintenant - heure <= AGE_MAX_HORS_SEANCE:
            return avec_hors_seance(entree, prix, heure, clotures)
    return entree


# --------------------------- Source 1 : Yahoo Finance ---------------------------

def cotation_yahoo(symbole: str) -> tuple[float, datetime] | None:
    """Dernier cours (5 min) d'un contrat à terme."""
    import yfinance as yf
    h = yf.Ticker(symbole).history(period="5d", interval="5m")
    h = h["Close"].dropna() if not h.empty else h
    return (float(h.iloc[-1]), h.index[-1].to_pydatetime()) if len(h) else None


def barres_prepost(symbole: str) -> list[tuple[datetime, float]]:
    """Cours de 5 min, séances étendues comprises (avant ouverture, après clôture)."""
    import yfinance as yf
    h = yf.Ticker(symbole).history(period="2d", interval="5m", prepost=True)
    if h.empty:
        return []
    c = h["Close"].dropna()
    return [(i.to_pydatetime(), float(v)) for i, v in c.items()]


def via_yahoo(actif: dict, maintenant: datetime) -> dict:
    import warnings
    import yfinance as yf  # importé ici : inutile pour les tests
    warnings.filterwarnings("ignore")  # avertissements internes de yfinance / pandas sans intérêt ici
    t = yf.Ticker(actif["symbole"])
    h = t.history(period="13mo", interval="1d", auto_adjust=False)
    meta = t.history_metadata or {}
    if h.empty or "Close" not in h:
        raise ErreurSource(f"Yahoo : aucun cours pour {actif['symbole']}")
    serie = h["Close"].dropna()
    clotures = [(i.date(), float(v)) for i, v in serie.items()]
    prix = meta.get("regularMarketPrice") or clotures[-1][1]
    heure = meta.get("regularMarketTime")
    heure = heure.to_pydatetime() if heure is not None else serie.index[-1].to_pydatetime()
    periode = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    debut, fin = periode.get("start"), periode.get("end")
    ouvert = est_ouvert(actif, heure, maintenant,
                        debut.to_pydatetime() if debut is not None else None,
                        fin.to_pydatetime() if fin is not None else None)
    entree = calculer(actif, float(prix), heure, clotures, ouvert, "Yahoo Finance")
    hs = actif.get("hors_seance")
    if hs and marche_ouvert(hs["calendrier"], maintenant) is False:
        future, barres = None, None
        try:
            if hs["type"] == "future":
                future = cotation_yahoo(hs["symbole"])
            elif hs["type"] == "prepost":
                barres = barres_prepost(actif["symbole"])
        except Exception as e:  # contrat à terme ou cours hors séance indisponible : dernière clôture
            LOG.warning("%s hors séance indisponible : %s", actif["nom"], str(e)[:100])
        # Hors séance, la variation du jour se lit par rapport à la dernière clôture : on la recalcule sur la série
        return choisir_hors_seance(actif, entree, clotures, maintenant, future, barres)
    return choisir_hors_seance(actif, entree, clotures, maintenant)


# --------------------------- Source 2 : Stooq (CSV) ---------------------------

def lire_stooq_quotidien(texte: str) -> list[tuple[date, float]]:
    """CSV Stooq « Date,Open,High,Low,Close,Volume » → [(date, clôture)]."""
    res = []
    for ligne in csv.DictReader(io.StringIO(texte)):
        try:
            res.append((date.fromisoformat(ligne["Date"]), float(ligne["Close"])))
        except (KeyError, ValueError, TypeError):
            continue
    return res


def lire_stooq_cours(texte: str) -> tuple[float, datetime]:
    """CSV Stooq « Symbol,Date,Time,Open,High,Low,Close,Volume » → (cours, heure UTC)."""
    lignes = list(csv.DictReader(io.StringIO(texte)))
    if not lignes or lignes[0].get("Close") in (None, "", "N/D"):
        raise ErreurSource("Stooq : cours absent")
    l = lignes[0]
    heure = datetime.fromisoformat(f"{l['Date']}T{l['Time']}").replace(tzinfo=FUSEAU_STOOQ)
    return float(l["Close"]), heure.astimezone(timezone.utc)


def via_stooq(actif: dict, maintenant: datetime, t: Telechargeur) -> dict:
    s = actif["stooq"]
    prix, heure = lire_stooq_cours(t.texte("https://stooq.com/q/l/", {"s": s, "f": "sd2t2ohlcv", "h": "", "e": "csv"}))
    debut = (maintenant - timedelta(days=400)).strftime("%Y%m%d")
    clotures = lire_stooq_quotidien(t.texte("https://stooq.com/q/d/l/", {"s": s, "i": "d", "d1": debut}))
    ouvert = est_ouvert(actif, heure, maintenant)
    return calculer(actif, prix, heure, clotures, ouvert, "Stooq")


# --------------------------- Assemblage ---------------------------

def ancienne(actif: dict, precedentes: dict) -> dict | None:
    """Dernière valeur connue, conservée avec son heure et marquée « ancienne »."""
    p = precedentes.get(actif["nom"])
    if not p or p.get("valeur") is None:
        return None
    return {**p, "symbole": actif["symbole"], "statut": "fermé", "ancienne": True}


def collecter(maintenant: datetime, precedentes: dict, yahoo=via_yahoo, stooq=via_stooq) -> list[dict]:
    t = Telechargeur(CACHE, duree_cache_h=0.05, essais=2, delai_politesse=0.3, delai_max=20)
    resultat = []
    for actif in ACTIFS:
        entree = None
        for nom, source in (("Yahoo", lambda a: yahoo(a, maintenant)), ("Stooq", lambda a: stooq(a, maintenant, t))):
            try:
                entree = source(actif)
                break
            except Exception as e:  # source indisponible : on passe à la suivante
                LOG.warning("%s : %s indisponible (%s)", actif["nom"], nom, str(e)[:160])
        if entree is None:
            entree = ancienne(actif, precedentes)
            if entree:
                LOG.warning("%s : dernière valeur conservée (%s)", actif["nom"], entree.get("heure"))
            else:
                LOG.error("%s : aucune valeur disponible", actif["nom"])
                continue
        LOG.info("%-22s %12s  jour %6s %%  1 an %6s %%  %s  %s", entree["nom"], entree["valeur"],
                 entree.get("variation"), entree.get("variation_1an"), entree.get("statut"), entree.get("source"))
        resultat.append(entree)
    return resultat


# Au-delà de cet âge, le cours d'un actif est signalé « périmé » dans la santé des agents
# (marchés fermés le week-end et les jours fériés : jusqu'à 4 jours sans cotation)
PEREMPTION = timedelta(days=4)
PEREMPTION_CONTINU = timedelta(hours=3)
JOURNAL = RACINE / "data" / "journal" / "agent-marches.json"


def etat_des_sources(donnees: list[dict], maintenant: datetime) -> list[dict]:
    """Une « source » par actif : ok (Yahoo), secours (Stooq), échec (valeur ancienne ou absente), périmée."""
    par_nom = {d["nom"]: d for d in donnees}
    etats = []
    for a in ACTIFS:
        d = par_nom.get(a["nom"])
        nom = f"{a['nom']} ({a['symbole']})"
        if d is None:
            etats.append({"nom": nom, "etat": "échec", "detail": "Yahoo Finance et Stooq indisponibles, aucune valeur connue"})
            continue
        heure = d.get("heure")
        if d.get("ancienne"):
            etats.append({"nom": nom, "etat": "échec", "derniere_donnee_valide": heure,
                          "detail": "Yahoo Finance et Stooq indisponibles : dernière valeur conservée"})
            continue
        t = datetime.fromisoformat(heure.replace("Z", "+00:00")) if heure else None
        limite = PEREMPTION_CONTINU if a.get("continu") else PEREMPTION
        if t and maintenant - t > limite:
            etats.append({"nom": nom, "etat": "périmée", "derniere_donnee_valide": heure,
                          "detail": f"dernier cours fourni par {d.get('source')} trop ancien"})
        elif d.get("source") == "Stooq":
            etats.append({"nom": nom, "etat": "secours", "derniere_donnee_valide": heure,
                          "detail": "Yahoo Finance indisponible : cours de Stooq"})
        else:
            etats.append({"nom": nom, "etat": "ok", "derniere_donnee_valide": heure})
    return etats


def enregistrer_sante(donnees: list[dict], maintenant: datetime, change: bool) -> None:
    precedent = ((lire_json(JOURNAL) or {}).get("meta") or {}).get("sante")
    etats = etat_des_sources(donnees, maintenant)
    # Un actif garde sa source tant qu'un cours à jour arrive (Yahoo, ou Stooq en secours)
    indicateurs = {e["nom"]: {"valides": ["cours à jour"] if e["etat"] in ("ok", "secours") else [],
                              "configurees": ["cours à jour"]} for e in etats}
    bloc = sante.bloc_sante("marches", "Agent marchés", 2, "agent-marches.yml", etats, maintenant, precedent,
                            indicateurs=indicateurs)
    # Battement de 30 min : si les cours ne bougent pas, on ne commite pas plus d'une fois par
    # demi-heure (sous le seuil « en retard » de 45 min de l'écran Santé)
    if sante.enregistrer_sante(JOURNAL, bloc, forcer=change, battement=timedelta(minutes=30),
                               description="Santé de l'agent marchés (dernière exécution réussie, état des sources)"):
        LOG.info("Journal de santé mis à jour : %d/%d sources répondent.", bloc["sources_ok"], bloc["sources_total"])


def main() -> int:
    maintenant = datetime.now(timezone.utc)
    precedent = lire_json(FICHIER, {}) or {}
    # Dernières valeurs connues (ignorées si le fichier contient encore les données fictives)
    anciennes = {d["nom"]: d for d in precedent.get("donnees", []) if not (precedent.get("meta") or {}).get("fictif")}
    donnees = collecter(maintenant, anciennes)
    if not donnees:
        LOG.error("Aucun cours récupéré : fichier inchangé.")
        return 1
    change = donnees != precedent.get("donnees")
    if change:
        sources = sorted({d["source"] for d in donnees})
        ecrire_json(FICHIER, enveloppe(donnees, source=" + ".join(sources), fictif=False,
                                       producteur="agent-marches", differe_min=15))
        LOG.info("data/marches.json mis à jour (%d actifs).", len(donnees))
    else:
        LOG.info("Valeurs inchangées : fichier non réécrit.")
    enregistrer_sante(donnees, maintenant, change)
    return 0
