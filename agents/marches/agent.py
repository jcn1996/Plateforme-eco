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
    {"symbole": "^NDX", "stooq": "^ndx", "nom": "Nasdaq 100", "categorie": "indices", "unite": "pts"},
    {"symbole": "^GSPC", "stooq": "^spx", "nom": "S&P 500", "categorie": "indices", "unite": "pts"},
    {"symbole": "GC=F", "stooq": "gc.f", "nom": "Or", "categorie": "matieres_premieres", "unite": "$/once"},
    {"symbole": "CL=F", "stooq": "cl.f", "nom": "Pétrole WTI", "categorie": "matieres_premieres", "unite": "$/baril"},
    {"symbole": "BTC-USD", "stooq": "btcusd", "nom": "Bitcoin", "categorie": "crypto", "unite": "$", "continu": True},
    {"symbole": "EURUSD=X", "stooq": "eurusd", "nom": "EUR/USD", "categorie": "devises", "unite": ""},
    {"symbole": "^FCHI", "stooq": "^cac", "nom": "CAC 40", "categorie": "indices", "unite": "pts"},
    {"symbole": "URTH", "stooq": "urth.us", "nom": "MSCI World (ETF URTH)", "categorie": "indices", "unite": "$"},
]

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


# --------------------------- Source 1 : Yahoo Finance ---------------------------

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
    return calculer(actif, float(prix), heure, clotures, ouvert, "Yahoo Finance")


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
    bloc = sante.bloc_sante("marches", "Agent marchés", 2, "agent-marches.yml",
                            etat_des_sources(donnees, maintenant), maintenant, precedent)
    # Battement d'une heure : si les cours ne bougent pas, on ne commite pas plus d'une fois par heure
    if sante.enregistrer_sante(JOURNAL, bloc, forcer=change, battement=timedelta(hours=1),
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
