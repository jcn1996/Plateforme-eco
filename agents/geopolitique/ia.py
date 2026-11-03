"""
Analyse des événements par Gemini, sous contraintes.

Quotas gratuits (config « gemini ») :
- au plus `quota_jour` appels par jour de quota (jour du Pacifique : Google remet les quotas à
  zéro à minuit, heure du Pacifique), comptés dans data/geopolitique/etat.json, donc d'une
  exécution à l'autre ;
- au plus `appels_max_par_execution` appels par exécution, et pas plus que la part du reste du
  jour qui revient à cette exécution (reste ÷ exécutions horaires restantes, arrondi au-dessus) :
  le budget n'est pas épuisé dès le matin ;
- au plus `quota_minute` appels sur 60 s et `intervalle_min_secondes` entre deux appels ;
- plusieurs événements par appel (`evenements_par_appel`) ; un événement déjà analysé n'est
  repris qu'après `reanalyse_apres_heures` et si ses sources ont été multipliées par
  `reanalyse_si_sources_multipliees_par` (cache) ;
- une réponse 429 (quota atteint) suspend les appels pendant une heure.

Anti-hallucination : Gemini ne reçoit que des sources numérotées (S1, S2…) avec leur URL ;
chaque affirmation qu'il renvoie doit citer au moins une de ces sources. Une affirmation sans
source valide est supprimée ; un événement sans résumé sourcé repasse en version sans IA.
Gravité 4 ou 5 seulement avec au moins 2 sources indépendantes citées (domaines différents, une
dépêche reprise mot pour mot sur plusieurs sites ne comptant qu'une fois).
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..commun.journal import journal
from ..pays.textes import MOTS_INTERDITS, _sans_accents, ton_conforme
from . import evenements as E

LOG = journal("agent-geopolitique")
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"

# Dramatisation interdite, en plus des mots d'emphase communs aux agents
MOTS_DRAMATISATION = ["catastrophe", "catastrophique", "chaos", "chaotique", "apocalypse", "apocalyptique", "panique",
                      "dramatique", "sans precedent", "terrifiant", "cataclysme", "dechainement", "brasier", "poudriere",
                      "effondrement total", "hecatombe"]
SENS = {"hausse", "baisse", "incertain"}
HORIZONS = {"jours", "semaines", "mois"}
CONFIANCES = {"faible", "moyenne", "élevée"}


class ErreurQuota(Exception):
    """Gemini a répondu 429 : quota atteint."""


class ErreurIA(Exception):
    """Gemini indisponible ou réponse inutilisable."""


def sobre(texte: str) -> bool:
    """Ton froid et factuel : ni mot d'emphase, ni mot de dramatisation."""
    t = _sans_accents(texte)
    return ton_conforme(texte) and not any(re.search(rf"\b{re.escape(m)}\b", t) for m in MOTS_DRAMATISATION)


# ------------------------------------------------------------------ quotas

class Quota:
    """Compteur d'appels persistant (etat["quota_gemini"]). `horloge` et `dormir` sont remplaçables (tests)."""

    def __init__(self, etat: dict, cfg: dict, horloge=None, dormir=time.sleep):
        self.cfg = cfg
        self.etat = etat.setdefault("quota_gemini", {"jour": None, "appels": 0, "recents": []})
        self.horloge = horloge or (lambda: datetime.now(timezone.utc))
        self.dormir = dormir
        self.appels_execution = 0
        self.quota_atteint = False

    def jour(self, t: datetime) -> str:
        return t.astimezone(ZoneInfo(self.cfg["fuseau_quota"])).date().isoformat()

    def _mise_a_jour(self, t: datetime) -> None:
        if self.etat.get("jour") != self.jour(t):
            self.etat.update({"jour": self.jour(t), "appels": 0})

    def restants(self, t: datetime | None = None) -> int:
        t = t or self.horloge()
        self._mise_a_jour(t)
        bloque = self.etat.get("bloque_jusqua")
        if bloque and t < datetime.fromisoformat(bloque):
            return 0
        return max(0, self.cfg["quota_jour"] - self.etat["appels"])

    def executions_restantes(self, t: datetime) -> int:
        """Exécutions horaires restantes avant la remise à zéro (celle-ci comprise)."""
        local = t.astimezone(ZoneInfo(self.cfg["fuseau_quota"]))
        minuit = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return max(1, math.ceil((minuit - local).total_seconds() / 3600))

    def autorises(self, t: datetime | None = None) -> int:
        """Appels permis pour cette exécution (avant le premier appel)."""
        t = t or self.horloge()
        reste = self.restants(t)
        if reste == 0:
            return 0
        part = math.ceil(reste / self.executions_restantes(t))
        return min(self.cfg["appels_max_par_execution"], reste, part)

    def attendre_creneau(self) -> None:
        """Respecte l'intervalle minimal et le plafond par minute."""
        while True:
            t = self.horloge()
            recents = [r for r in self.etat.get("recents", []) if t - datetime.fromisoformat(r) < timedelta(seconds=60)]
            self.etat["recents"] = recents
            attente = 0.0
            if recents:
                attente = self.cfg["intervalle_min_secondes"] - (t - datetime.fromisoformat(recents[-1])).total_seconds()
            if len(recents) >= self.cfg["quota_minute"]:
                attente = max(attente, 60 - (t - datetime.fromisoformat(recents[0])).total_seconds())
            if attente <= 0:
                return
            self.dormir(attente)

    def enregistrer(self) -> None:
        t = self.horloge()
        self._mise_a_jour(t)
        self.etat["appels"] += 1
        self.etat["recents"] = (self.etat.get("recents", []) + [t.isoformat()])[-self.cfg["quota_minute"]:]
        self.appels_execution += 1

    def marquer_atteint(self) -> None:
        """Réponse 429 : plus d'appel pendant une heure (quota par minute ou par jour atteint)."""
        self.quota_atteint = True
        self.etat["bloque_jusqua"] = (self.horloge() + timedelta(hours=1)).isoformat()


# ------------------------------------------------------------------ appel

def appeler(consigne: str, cfg: dict, cle: str, poster=None) -> str:
    import requests
    poster = poster or requests.post
    try:
        r = poster(URL_GEMINI.format(modele=cfg["modele"]), params={"key": cle}, timeout=cfg["delai_reponse_secondes"],
                   json={"contents": [{"parts": [{"text": consigne}]}],
                         "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}})
    except Exception as e:  # réseau
        raise ErreurIA(f"{type(e).__name__}: {str(e)[:120]}") from e
    if r.status_code == 429:
        raise ErreurQuota("HTTP 429 (quota atteint)")
    if r.status_code != 200:
        raise ErreurIA(f"HTTP {r.status_code} : {r.text[:160]}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as e:
        raise ErreurIA("réponse sans texte") from e


def sources_numerotees(e: dict) -> list[dict]:
    return [{**s, "id": f"S{i}"} for i, s in enumerate(E.sources_publiques(e, maxi=10), 1)]


def consigne(lot: list[dict], config: dict, sources: dict) -> str:
    """Prompt pour un lot d'événements : sources numérotées, contraintes, format JSON attendu."""
    blocs = []
    for e in lot:
        srcs = [{"id": s["id"], "titre": s["titre"], "domaine": s["domaine"], "date": s["date"], "url": s["url"],
                 "officielle": bool(s.get("officiel"))} for s in sources[e["id"]]]
        blocs.append({"evenement": e["id"], "categorie_detectee": e["categorie"], "pays_detectes": e["pays"], "sources": srcs})
    categories = ", ".join(config["categories"])
    actifs = ", ".join(config["actifs"])
    pays = ", ".join(sorted(set(config["pays"]) | {k for k in config["autres_pays"] if not k.startswith("_")}))
    return (
        "Tu es analyste géopolitique pour un suivi des marchés. Rédige en français, ton froid et factuel : "
        "pas de superlatifs, pas de dramatisation (mots interdits : " + ", ".join(MOTS_INTERDITS[:10] + MOTS_DRAMATISATION[:8]) + "). "
        "Distingue les faits (résumé, tirés des sources) des interprétations (impact sur les marchés). "
        "Règle absolue : chaque affirmation cite au moins une source par son identifiant (S1, S2…) parmi celles fournies "
        "pour CET événement ; n'utilise aucune autre connaissance que ces titres. Une affirmation sans source sera supprimée. "
        "Gravité de 1 (sans effet attendu sur les marchés) à 5 (choc majeur) ; 4 ou 5 seulement si au moins deux sources "
        "de domaines différents le confirment.\n"
        f"Catégories possibles : {categories}. Actifs possibles : {actifs}. Codes pays possibles : {pays}.\n"
        "Réponds uniquement en JSON : {\"analyses\": [{\"evenement\": \"id\", "
        "\"resume\": [{\"texte\": \"phrase factuelle\", \"sources\": [\"S1\"]}, {\"texte\": \"2e phrase\", \"sources\": [\"S2\"]}], "
        "\"pays\": [\"US\"], \"categorie\": \"sanctions\", \"gravite\": 3, "
        "\"actifs\": [{\"actif\": \"pétrole\", \"sens\": \"hausse|baisse|incertain\", \"texte\": \"raison en une phrase\", \"sources\": [\"S1\"]}], "
        "\"horizon\": \"jours|semaines|mois\", \"confiance\": \"faible|moyenne|élevée\", "
        "\"contre\": [{\"texte\": \"ce qui pourrait donner tort à cette lecture\", \"sources\": [\"S1\"]}]}]}\n"
        "Le résumé tient en 2 phrases. Événements :\n" + json.dumps(blocs, ensure_ascii=False)
    )


# ------------------------------------------------------------------ validation (anti-hallucination)

def _affirmations(liste, par_id: dict, maxi: int, supprimees: list) -> list[dict]:
    res = []
    for a in liste if isinstance(liste, list) else []:
        if not isinstance(a, dict) or not isinstance(a.get("texte"), str) or not a["texte"].strip():
            continue
        ids = [s for s in (a.get("sources") or []) if isinstance(s, str) and s.strip() in par_id]
        texte = a["texte"].strip()
        if not ids:
            supprimees.append(f"sans source : {texte[:80]}")
            continue
        if not sobre(texte) or len(texte) > 400:
            supprimees.append(f"ton non conforme : {texte[:80]}")
            continue
        res.append({**{k: v for k, v in a.items() if k not in ("texte", "sources")}, "texte": texte,
                    "sources": [par_id[s.strip()]["url"] for s in dict.fromkeys(ids)],
                    "_cites": [par_id[s.strip()] for s in dict.fromkeys(ids)]})
    return res[:maxi]


def valider(brut: dict, e: dict, config: dict, sources: list[dict]) -> tuple[dict | None, list[str]]:
    """Analyse validée pour l'événement e, ou None (version sans IA). Renvoie aussi les suppressions."""
    supprimees: list[str] = []
    par_id = {s["id"]: s for s in sources}
    resume = _affirmations(brut.get("resume"), par_id, 2, supprimees)
    if not resume:
        return None, supprimees + ["résumé sans affirmation sourcée : version sans IA"]
    actifs = []
    for a in _affirmations(brut.get("actifs"), par_id, 6, supprimees):
        if a.get("actif") in config["actifs"] and a.get("sens") in SENS:
            actifs.append(a)
        else:
            supprimees.append(f"actif ou sens inconnu : {a.get('actif')} / {a.get('sens')}")
    contre = _affirmations(brut.get("contre"), par_id, 3, supprimees)
    connus = set(config["pays"]) | {k for k in config["autres_pays"] if not k.startswith("_")}
    pays = [p for p in (brut.get("pays") or []) if p in connus] or e["pays"]
    categorie = brut.get("categorie") if brut.get("categorie") in config["categories"] else e["categorie"]
    try:
        gravite = max(1, min(5, int(brut.get("gravite"))))
    except (TypeError, ValueError):
        gravite = E.gravite_regles(e, config)
    cites = {s["id"]: s for a in resume + actifs + contre for s in a["_cites"]}
    independantes = E.independantes(list(cites.values()))
    note_gravite = None
    if gravite >= 4 and independantes < 2:
        note_gravite = f"gravité {gravite} proposée, plafonnée à 3 : une seule source indépendante citée"
        gravite = 3
    for a in resume + actifs + contre:
        a.pop("_cites", None)
    analyse = {
        "resume": resume, "pays": pays, "categorie": categorie, "gravite": gravite, "note_gravite": note_gravite,
        "actifs": [{"actif": a["actif"], "sens": a["sens"], "texte": a["texte"], "sources": a["sources"]} for a in actifs],
        "horizon": brut.get("horizon") if brut.get("horizon") in HORIZONS else "semaines",
        "confiance": brut.get("confiance") if brut.get("confiance") in CONFIANCES else "faible",
        "contre": contre, "sources_independantes": independantes,
    }
    return analyse, supprimees


# ------------------------------------------------------------------ analyse d'un ensemble d'événements

def a_analyser(e: dict, config: dict, maintenant: datetime) -> bool:
    """Cache : un événement analysé n'est repris que s'il a beaucoup grossi, et pas avant le délai."""
    a = e.get("analyse")
    if not a:
        return True
    cfg = config["gemini"]
    age = maintenant - datetime.fromisoformat(a["analyse_le"].replace("Z", "+00:00"))
    return (age >= timedelta(hours=cfg["reanalyse_apres_heures"])
            and len(e["articles"]) >= cfg["reanalyse_si_sources_multipliees_par"] * a.get("nb_articles", 1))


def analyser(candidats: list[dict], config: dict, quota: Quota, maintenant: datetime, cle: str | None = None,
             poster=None) -> dict:
    """Analyse les candidats (déjà triés par importance), dans la limite des quotas.
    Écrit e["analyse"] pour chaque événement validé. Renvoie le compte rendu de l'exécution."""
    cfg = config["gemini"]
    cle = cle if cle is not None else os.environ.get("GEMINI_API_KEY")
    rapport = {"modele": cfg["modele"], "appels": 0, "analyses": 0, "rejets": 0, "suppressions": [], "erreur": None,
               "quota_atteint": False, "cle": bool(cle)}
    if not cle or not candidats:
        rapport["autorises"] = 0
        return rapport
    autorises = quota.autorises(maintenant)
    rapport["autorises"] = autorises
    n = cfg["evenements_par_appel"]
    lots = [candidats[i:i + n] for i in range(0, len(candidats), n)][:autorises]
    for lot in lots:
        sources = {e["id"]: sources_numerotees(e) for e in lot}
        quota.attendre_creneau()
        quota.enregistrer()
        rapport["appels"] += 1
        try:
            texte = appeler(consigne(lot, config, sources), cfg, cle, poster)
            reponse = json.loads(texte)
            analyses = {a.get("evenement"): a for a in (reponse.get("analyses") or []) if isinstance(a, dict)}
        except ErreurQuota as err:
            quota.marquer_atteint()
            rapport.update(quota_atteint=True, erreur=str(err))
            LOG.warning("Gemini : quota atteint, fin des appels pour cette exécution")
            break
        except (ErreurIA, ValueError, AttributeError) as err:
            rapport["erreur"] = str(err)[:200]
            LOG.warning("Gemini indisponible (%s) : version sans IA", str(err)[:120])
            break
        for e in lot:
            brut = analyses.get(e["id"])
            analyse, supprimees = valider(brut, e, config, sources[e["id"]]) if isinstance(brut, dict) else (None, ["événement absent de la réponse"])
            rapport["suppressions"] += [f"{e['id']} : {s}" for s in supprimees]
            if analyse:
                e["analyse"] = {**analyse, "analyse_le": E.iso(maintenant), "nb_articles": len(e["articles"]), "modele": cfg["modele"]}
                rapport["analyses"] += 1
            else:
                rapport["rejets"] += 1
    return rapport
