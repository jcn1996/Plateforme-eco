"""
Analyse à la demande d'une entreprise (sans IA), déclenchée par une issue GitHub « Analyse : <ticker ou nom> ».

    python -m agents.analyse_demande --evenement "$GITHUB_EVENT_PATH" --sortie DOSSIER [--data DIR] [--test]
    python -m agents.analyse_demande --evenement … --sortie DOSSIER --echec "raison"   (échec avant l'analyse)

Même grille que l'agent entreprises (mêmes sources, dans le même ordre : SEC, ESEF, EDINET, DART, Yahoo ;
mêmes indicateurs, F-score, alertes, notes, verdict, confiance, contre-scénario, revue critique, contexte
pays et macro, recommandation), comparaison avec les sociétés du même secteur déjà analysées.

Écrit : data/analyses/<TICKER>.json, data/analyses/index.json, config/surveillance.json (société ajoutée),
data/journal/analyse-demande.json (santé) ; dans DOSSIER : reponse.md (commentaire) et resultat.json
({statut, ticker, fermeture}) lus par le workflow, qui commente et ferme l'issue.
Sécurité : l'auteur de l'issue doit être le propriétaire du dépôt (vérifié aussi par le workflow).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import date, datetime, timezone
from pathlib import Path

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from ..entreprises import agent as E
from ..entreprises import analyse as A
from ..entreprises import comptes as C
from ..entreprises import dynamique as D
from ..entreprises import recommandation as R
from ..entreprises import univers as U
from . import reponse as T
from .resolution import pays_du_symbole, resoudre, saisie

LOG = journal("analyse-demande")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
CFG = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
CFG_E = json.loads((RACINE / "agents" / "entreprises" / "config.json").read_text(encoding="utf-8"))
WORKFLOW = "analyse-demande.yml"


def maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ accès réseau (recherche et liquidité)

class Reseau:
    def __init__(self):
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        self.yf = yf

    def recherche(self, q: str) -> list[dict]:
        return self.yf.Search(q, max_results=8, news_count=0).quotes or []

    def cours(self, symbole: str) -> tuple[list, str | None]:
        t = self.yf.Ticker(symbole)
        h = t.history(period="3mo", interval="1d", auto_adjust=True)
        if h.empty:
            return [], None
        meta = t.history_metadata or {}
        return [(i.strftime("%Y-%m-%d"), float(c), float(v or 0)) for i, c, v in zip(h.index, h["Close"], h["Volume"]) if c == c], meta.get("currency")


class ReseauTest:
    """Recherche enregistrée (tests/donnees/recherche.json) et cours des données de test de l'agent entreprises."""

    def __init__(self, f_test):
        self.q = json.loads((DOSSIER / "tests" / "donnees" / "recherche.json").read_text(encoding="utf-8"))
        self.f = f_test

    def recherche(self, q):
        return self.q.get(q.lower(), [])

    def cours(self, symbole):
        y = self.f.d["yahoo"].get(symbole)
        return (y["cours"], y["devise_cours"]) if y else ([], None)


class FournisseurMemo:
    """Fournisseur de l'agent entreprises dont les réponses Yahoo par société sont gardées en mémoire
    (la fiche Yahoo est lue une fois pour connaître le pays, puis réutilisée pour l'analyse)."""

    class _Yahoo:
        def __init__(self, y):
            self.y, self.memo = y, {}

        def societe(self, t):
            if t not in self.memo:
                self.memo[t] = self.y.societe(t)
            return self.memo[t]

        def __getattr__(self, nom):
            return getattr(self.y, nom)

    def __init__(self, f):
        self.f, self.yahoo, self.sec = f, self._Yahoo(f.yahoo), f.sec

    def officiel(self, s, ids):
        return self.f.officiel(s, ids)


# ------------------------------------------------------------------ événement

def lire_evenement(chemin: Path) -> dict:
    ev = json.loads(Path(chemin).read_text(encoding="utf-8"))
    issue = ev.get("issue") or {}
    proprietaire = ((ev.get("repository") or {}).get("owner") or {}).get("login") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    return {"numero": issue.get("number"), "titre": issue.get("title") or "", "auteur": (issue.get("user") or {}).get("login"),
            "proprietaire": proprietaire, "url": issue.get("html_url")}


def url_execution() -> str | None:
    if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_REPOSITORY"):
        return f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return None


# ------------------------------------------------------------------ univers déjà analysé

def univers(data: Path) -> tuple[list[dict], list[dict]]:
    """Sociétés de l'agent entreprises (données réelles) et analyses à la demande déjà publiées."""
    ent = lire_json(data / "entreprises.json") or {}
    societes = ent.get("donnees") or [] if (ent.get("meta") or {}).get("fictif") is False else []
    analyses = (lire_json(data / "analyses" / "index.json") or {}).get("donnees") or []
    return societes, analyses


def medianes_univers(data: Path, societes: list[dict]) -> dict:
    """Médianes du PER et du VE/EBITDA par secteur (mondiales et régionales), comme l'agent entreprises :
    lues dans meta.medianes quand elles y sont toutes, sinon recalculées à partir des fiches."""
    meta = ((lire_json(data / "entreprises.json") or {}).get("meta") or {}).get("medianes") or {}
    if any(not k.endswith("|monde") for k in meta):
        return {(k.split("|")[0], None if k.split("|")[1] == "monde" else k.split("|")[1]): v for k, v in meta.items()}
    pseudo = []
    for e in societes:
        if not e.get("secteur_gics"):
            continue
        fiche = (lire_json(data / "entreprises" / "fiches" / E.fichier_fiche(e["ticker"])) or {}).get("donnees") or {}
        v = fiche.get("valorisation") or {}
        pseudo.append({"secteur_gics": e["secteur_gics"], "region": e.get("region"), "mesures": {"per": v.get("per"), "ev_ebitda": v.get("ev_ebitda")}})
    return A.medianes_sectorielles(pseudo)


def rang_secteur(e: dict, societes: list[dict], analyses: list[dict], regions: dict) -> dict | None:
    """Rang de la société par note parmi les sociétés du même secteur GICS déjà analysées (monde et région)."""
    exclus = {e["ticker"], *(c["ticker"] for c in e.get("autres_cotations") or [])}
    pairs = [{"ticker": x["ticker"], "nom": x["nom"], "note": x["note"], "region": x.get("region"), "pays": x.get("pays")}
             for x in societes if x.get("secteur_gics") == e["secteur_gics"] and x["ticker"] not in exclus and x.get("note") is not None]
    connus = {p["ticker"] for p in pairs}
    pairs += [{"ticker": a["ticker"], "nom": a["nom"], "note": a["note"], "region": a.get("region"), "pays": a.get("pays")}
              for a in analyses if a.get("secteur_gics") == e["secteur_gics"] and a["ticker"] not in exclus | connus and a.get("note") is not None]
    if not e.get("secteur_gics") or not pairs:
        return None

    def classement(groupe):
        notes = [p["note"] for p in groupe] + [e["note"]]
        return {"rang": 1 + sum(1 for p in groupe if p["note"] > e["note"]), "total": len(notes),
                "note_mediane": round(statistics.median(notes)), "percentile": round(100 * sum(1 for n in notes if n <= e["note"]) / len(notes))}
    reg = [p for p in pairs if p["region"] == e["region"]]
    meilleures = sorted(pairs, key=lambda p: -p["note"])[:3]
    return {"secteur_gics": e["secteur_gics"], "secteur_nom": e["secteur_nom"], "monde": classement(pairs),
            "region": {**classement(reg), "nom": regions.get(e["region"], e["region"])} if reg else None,
            "meilleures": [{k: p[k] for k in ("ticker", "nom", "note", "pays")} for p in meilleures]}


# ------------------------------------------------------------------ écritures

def ajouter_surveillance(chemin: Path, ticker: str, pays: str, jour: date, issue: int | None) -> bool:
    """Ajoute la société à config/surveillance.json si elle n'y est pas (une société par ligne, comme le fichier d'origine)."""
    d = lire_json(chemin) or {"_commentaire": "Liste de surveillance personnelle.", "societes": []}
    if any(str(s.get("ticker", "")).upper() == ticker.upper() for s in d.get("societes", [])):
        return False
    d.setdefault("societes", []).append({"ticker": ticker, "pays": pays,
                                          "note": f"ajoutée par l'analyse à la demande du {jour.strftime('%d/%m/%Y')}" + (f" (issue #{issue})" if issue else "")})
    autres = {k: v for k, v in d.items() if k not in ("_commentaire", "societes")}
    lignes = ["{", f'  "_commentaire": {json.dumps(d.get("_commentaire", ""), ensure_ascii=False)},']
    lignes += [f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}," for k, v in autres.items()]
    lignes += ['  "societes": [', ",\n".join(f"    {json.dumps(s, ensure_ascii=False)}" for s in d["societes"]), "  ]", "}"]
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return True


def maj_index(data: Path, e: dict, demande: dict) -> None:
    chemin = data / "analyses" / "index.json"
    idx = lire_json(chemin) or {"meta": {}, "donnees": []}
    ancien = next((x for x in idx["donnees"] if x["ticker"] == e["ticker"]), None)
    precedentes = ((ancien or {}).get("precedentes") or [])
    if ancien:
        precedentes = [{k: ancien.get(k) for k in ("date", "note", "recommandation", "issue")}, *precedentes][:10]
    ligne = {"ticker": e["ticker"], "nom": e["nom"], "pays": e["pays"], "region": e["region"], "secteur_gics": e["secteur_gics"],
             "secteur_nom": e["secteur_nom"], "date": demande["date"], "note": e["note"], "niveau": e["niveau"], "verdict": e["verdict"],
             "recommandation": R.resume(e.get("recommandation")), "confiance": e["confiance"]["niveau"],
             "issue": demande.get("issue"), "texte": demande["texte"], "statut": "ok",
             "fichier": f"data/analyses/{E.fichier_fiche(e['ticker'])}", "precedentes": precedentes}
    donnees = sorted([x for x in idx["donnees"] if x["ticker"] != e["ticker"]] + [ligne], key=lambda x: x["date"], reverse=True)
    ecrire_json(chemin, enveloppe(donnees, "analyse-demande", fictif=False, version_agent=VERSION_AGENT,
                                  description="Analyses à la demande (dernière analyse par société ; détail dans data/analyses/<ticker>.json)"))


def enregistrer_journal(data: Path, execution: dict, quand: datetime, sources: list[dict] | None = None) -> dict:
    """Journal des exécutions et bloc santé (agent sans planning : « à la demande »)."""
    chemin = data / "journal" / "analyse-demande.json"
    j = lire_json(chemin) or {"meta": {}, "donnees": []}
    j["donnees"] = (j.get("donnees") or []) + [execution]
    j["donnees"] = j["donnees"][-CFG["journal_max"]:]
    precedent = (j.get("meta") or {}).get("sante") or {}
    reussites = [x for x in j["donnees"] if x["statut"] == "ok"]
    echecs = [x for x in j["donnees"] if x["statut"] == "echec"]
    if execution["statut"] == "ok" and sources is not None:
        bloc = sante.bloc_sante("analyse-demande", "Analyse à la demande", 5, WORKFLOW, sources, quand, precedent, crons=[])
    else:
        # Pas d'analyse réussie à cette exécution : la dernière exécution réussie reste celle du bloc précédent
        bloc = {**({"agent": "analyse-demande", "libelle": "Analyse à la demande", "ordre": 5, "workflow": WORKFLOW,
                    "derniere_execution": None, "prochaine_prevue": None, "intervalle_min": None,
                    "planning": {"crons": [], "fuseau": "UTC"}, "sources_total": 0, "sources_ok": 0, "sources": []}), **precedent}
    dernier = execution["statut"]
    bloc.update({
        "a_la_demande": True, "dernier_statut": dernier, "derniere_tentative": execution["date"],
        "derniere_reussite": reussites[-1] if reussites else None, "dernier_echec": echecs[-1] if echecs else None,
        "echecs_recents": echecs[-5:][::-1], "analyses_reussies": len(reussites), "executions": len(j["donnees"]),
        "degrade": dernier == "echec",
        "raisons": [f"Dernière analyse en échec (issue #{execution.get('issue')}, « {execution.get('texte')} ») : {execution.get('detail')}"] if dernier == "echec" else [],
    })
    if not reussites:
        bloc["derniere_execution"] = None
    j["meta"] = {**(j.get("meta") or {}), "source": "analyse-demande", "version_agent": VERSION_AGENT,
                 "description": "Analyses à la demande : une ligne par exécution (ok, introuvable, insuffisant, refus, echec)"}
    ecrire_json(chemin, j)
    sante.enregistrer_sante(chemin, bloc, forcer=True)
    if not reussites:  # enregistrer_sante recopie derniere_execution au premier niveau
        j = lire_json(chemin)
        j["derniere_execution"] = None
        ecrire_json(chemin, j)
    return bloc


def ecrire_sortie(sortie: Path, statut: str, texte_reponse: str, ticker: str | None = None) -> None:
    sortie.mkdir(parents=True, exist_ok=True)
    (sortie / "reponse.md").write_text(texte_reponse, encoding="utf-8")
    (sortie / "resultat.json").write_text(json.dumps({"statut": statut, "ticker": ticker,
                                                      "fermeture": "not planned" if statut == "refus" else "completed"},
                                                     ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ analyse

def analyser(texte: str, demande: dict, data: Path, surveillance: Path, f, reseau, aujourdhui: date) -> tuple[str, str, str | None, dict]:
    """Renvoie (statut, réponse, ticker, détail pour le journal)."""
    societes, analyses = univers(data)
    noms = [(x["ticker"], x["nom"]) for x in societes] + [(a["ticker"], a["nom"]) for a in analyses]
    res = resoudre(texte, reseau.recherche, reseau.cours, f.yahoo.taux_change, noms, CFG["candidats_max"])
    if res["statut"] == "introuvable":
        return "introuvable", T.reponse_introuvable(texte, res["suggestions"]), None, {"suggestions": res["suggestions"]}
    c = res["choisi"]
    ticker = c["symbole"]
    LOG.info("« %s » → %s (%s) ; autres : %s", texte, ticker, res["methode"], [a["symbole"] for a in res["autres"]])

    base = ((lire_json(data / "entreprises" / "comptes.json") or {}).get("societes")) or {}
    ancien = base.get(ticker)
    fm = FournisseurMemo(f)
    try:
        y = fm.yahoo.societe(ticker)
    except C.ErreurSource as err:
        return "insuffisant", T.reponse_insuffisant(texte, ticker, str(err)), ticker, {}
    # Pays : celui de la base, sinon celui que déclare Yahoo (ex. ASML cotée au Nasdaq : Pays-Bas), sinon la place de cotation.
    # Il détermine la source officielle consultée (SEC, ESEF, EDINET, DART).
    pays = (ancien or {}).get("pays") or pays_du_symbole(ticker, CFG["suffixes_pays"], (y.get("info") or {}).get("country"))
    s0 = {"ticker": ticker, "nom": y.get("nom") or c.get("nom") or ticker, "pays": pays, "surveillance": True,
          "secteur": (ancien or {}).get("secteur_gics") or U.secteur_gics(c.get("secteur")), "source_composition": "analyse à la demande"}
    r = E.collecter_societe(fm, s0, ancien, CFG_E["ecart_officiel_max_pct"])
    if not r.get("annuel") or not r.get("cours"):
        return "insuffisant", T.reponse_insuffisant(texte, ticker, "comptes annuels ou cours absents sur Yahoo Finance"), ticker, {}
    devises = {d for d in (r.get("devise_cours"), r.get("devise_comptes")) if d}
    change = f.yahoo.taux_change(devises)
    s = E.mesurer(r, change, CFG_E["univers"])
    med = medianes_univers(data, societes)
    pays_json = {p["code"]: p for p in ((lire_json(data / "pays.json") or {}).get("donnees") or [])}
    macro = (lire_json(data / "macro.json") or {}).get("donnees") or {}
    zones = {z["cle"]: z["phase"] for z in (macro.get("cycle") or {}).get("zones", [])}
    zone_par_pays = json.loads((RACINE / "agents" / "macro" / "config.json").read_text(encoding="utf-8"))["zone_par_pays"]
    dyn = D.donnees_demande(f.yahoo, ticker, s["pays"], data, aujourdhui)  # dynamique des résultats (analystes, guidance connue)
    a = E.analyser_societe(s, med, CFG_E, pays_json, zones, zone_par_pays, aujourdhui, revue=True, dyn=dyn)
    if not a:
        return "insuffisant", T.reponse_insuffisant(texte, ticker, "trop peu d'indicateurs calculables pour une note"), ticker, {}
    e = a[0]
    e["rang_secteur"] = rang_secteur(e, societes, analyses, CFG_E["regions"])
    e["demande"] = {**demande, "resolution": res}
    e["sources"]["composition"] = "analyse à la demande"
    nom_fichier = E.fichier_fiche(ticker)
    ecrire_json(data / "analyses" / nom_fichier, {"meta": {"genere_le": maintenant(), "source": "analyse-demande", "version_agent": VERSION_AGENT,
                                                           "fictif": False}, "donnees": e})
    maj_index(data, e, demande)
    ajoute = ajouter_surveillance(surveillance, ticker, e["pays"], aujourdhui, demande.get("issue"))
    avert = None
    if e["pays"] == "US" and not getattr(f.sec, "actif", False):
        avert = "Comptes officiels SEC non lus (secret SEC_USER_AGENT absent) : comptes Yahoo Finance seuls, confiance plafonnée à « moyen »."
    texte_r = T.reponse_ok(e, res, CFG, avert)
    if ajoute:
        texte_r = texte_r.replace("\nFiche complète", "\nSociété ajoutée à la liste de surveillance (config/surveillance.json) : elle sera suivie par l'agent entreprises.\n\nFiche complète", 1)
    return "ok", texte_r, ticker, {"note": e["note"], "recommandation": R.resume(e.get("recommandation")),
                                    "source_officielle": e["sources"]["officielle"], "methode": res["methode"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Analyse à la demande d'une entreprise")
    ap.add_argument("--evenement", required=True, help="fichier JSON de l'événement GitHub (GITHUB_EVENT_PATH)")
    ap.add_argument("--sortie", required=True, help="dossier où écrire reponse.md et resultat.json")
    ap.add_argument("--data", default=str(RACINE / "data"))
    ap.add_argument("--surveillance", default=str(RACINE / "config" / "surveillance.json"))
    ap.add_argument("--test", action="store_true", help="données de test enregistrées, sans réseau")
    ap.add_argument("--echec", help="enregistre un échec survenu avant l'analyse (raison)")
    ap.add_argument("--date")
    args = ap.parse_args(argv)
    data, sortie = Path(args.data), Path(args.sortie)
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    quand = datetime.now(timezone.utc)
    ev = lire_evenement(Path(args.evenement))
    texte = saisie(ev["titre"], CFG["longueur_max_saisie"])
    execution = {"date": maintenant(), "issue": ev["numero"], "texte": texte, "auteur": ev["auteur"]}

    if ev["auteur"] != ev["proprietaire"] or not ev["auteur"]:
        LOG.warning("Issue #%s ouverte par %s (propriétaire : %s) : refusée", ev["numero"], ev["auteur"], ev["proprietaire"])
        ecrire_sortie(sortie, "refus", T.reponse_refus())
        return 0
    if args.echec:
        enregistrer_journal(data, {**execution, "statut": "echec", "detail": args.echec}, quand)
        ecrire_sortie(sortie, "echec", T.reponse_echec(texte or ev["titre"], args.echec, url_execution()))
        return 0
    if not texte:
        ecrire_sortie(sortie, "introuvable", T.reponse_introuvable(ev["titre"], []))
        return 0

    debut = time.monotonic()
    demande = {"texte": texte, "issue": ev["numero"], "url_issue": ev["url"], "date": maintenant(), "auteur": ev["auteur"]}
    try:
        if args.test:
            f = E.FournisseurTest(RACINE / "agents" / "entreprises" / "tests" / "donnees")
            reseau = ReseauTest(f)
        else:
            f = E.Fournisseur(CFG_E)
            reseau = Reseau()
        statut, texte_r, ticker, detail = analyser(texte, demande, data, Path(args.surveillance), f, reseau, aujourdhui)
    except Exception as e:  # erreur technique : enregistrée, puis signalée dans l'issue
        LOG.exception("Analyse de « %s » en échec", texte)
        raison = f"{type(e).__name__} : {str(e)[:200]}"
        enregistrer_journal(data, {**execution, "statut": "echec", "detail": raison, "duree_s": round(time.monotonic() - debut)}, quand)
        ecrire_sortie(sortie, "echec", T.reponse_echec(texte, raison, url_execution()))
        return 1
    sources = None
    if statut == "ok":
        off = detail.get("source_officielle")
        sources = [{"nom": "Recherche Yahoo Finance", "etat": "ok"}, {"nom": "Yahoo Finance (comptes et cours)", "etat": "ok"}]
        if off:
            sources.append({"nom": off, "etat": "ok"})
    enregistrer_journal(data, {**execution, "statut": statut, "ticker": ticker, "duree_s": round(time.monotonic() - debut), **detail}, quand, sources)
    ecrire_sortie(sortie, statut, texte_r, ticker)
    LOG.info("Issue #%s : %s (%s)", ev["numero"], statut, ticker)
    return 0
