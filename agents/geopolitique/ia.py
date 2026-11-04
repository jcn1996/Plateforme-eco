"""
Analyse des événements par Gemini, sous contraintes.

Modèles : chaîne configurable (config « gemini.modeles ») ; le premier qui répond est utilisé.
Sur une erreur 5xx (modèle surchargé, 503) ou réseau : nouvelles tentatives avec attente
progressive (`essais`, `attentes_reprise_secondes`), puis modèle suivant de la chaîne.

Quotas gratuits, par modèle (chaque modèle a son propre quota, par projet ; Google les remet à
zéro à minuit, heure du Pacifique) :
- limites rpm et rpd de la configuration, moins une marge (20 %) ; elles ne sont plus publiées
  en chiffres et doivent être confirmées dans AI Studio ;
- au plus `appels_max_par_execution` appels par exécution, et pas plus que la part du reste du
  jour qui revient à cette exécution (reste ÷ exécutions horaires restantes, arrondi au-dessus) ;
- intervalle minimal entre deux appels (60 s ÷ rpm effectif) ;
- adaptation aux réponses 429 : quota par minute → attente (retryDelay, au plus 60 s) puis
  un nouvel essai ; quota du jour (ou 429 répété) → plus d'appel à ce modèle jusqu'au lendemain,
  et, si le message indique le quota du jour, limite apprise pour les jours suivants ;
- plusieurs événements par appel ; cache : un événement analysé n'est repris qu'après
  `reanalyse_apres_heures` et si ses sources ont été multipliées par `reanalyse_si_sources_multipliees_par`.
Les événements de gravité estimée 3 ou plus passent en premier.

Anti-hallucination : Gemini ne reçoit que des sources numérotées (S1, S2…) avec leur URL ;
chaque affirmation qu'il renvoie doit citer au moins une de ces sources, être en français et
sobre. Une affirmation qui ne remplit pas ces conditions est supprimée ; un événement sans
résumé valide repasse en version sans IA. Gravité 4 ou 5 seulement avec au moins 2 sources
indépendantes citées (domaines différents, une dépêche reprise mot pour mot ne comptant qu'une fois).
Gemini peut aussi signaler que deux événements du lot décrivent le même fait (« meme_que ») :
l'agent les fusionne.
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
MOTS_FR = set("le la les des du de un une et est en au aux à pour par sur avec dans qui que ont sont été son sa ses leur cette ce ne pas plus".split())
MOTS_EN = set("the and of to in is are was were has have with for on by that from this its their been will would".split())


class ErreurQuota(Exception):
    """Gemini a répondu 429 : quota atteint (`jour` : quota du jour)."""

    def __init__(self, message: str, jour: bool):
        super().__init__(message)
        self.jour = jour


class ErreurIA(Exception):
    """Gemini indisponible (après les reprises) ou réponse inutilisable."""


def sobre(texte: str) -> bool:
    """Ton froid et factuel : ni mot d'emphase, ni mot de dramatisation."""
    t = _sans_accents(texte)
    return ton_conforme(texte) and not any(re.search(rf"\b{re.escape(m)}\b", t) for m in MOTS_DRAMATISATION)


def en_francais(texte: str) -> bool:
    """Contrôle simple de la langue : plus de mots outils français qu'anglais, et au moins un."""
    mots = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", texte.lower())
    fr = sum(1 for m in mots if m in MOTS_FR or m.startswith(("l'", "d'", "qu'")))
    en = sum(1 for m in mots if m in MOTS_EN)
    return fr >= 1 and fr > en


def plafonner(gravite: int, categorie: str, textes: list[str], config: dict) -> tuple[int, str | None]:
    """Plafonds par catégorie (ex. élection qui se déroule normalement : 3 au plus), sauf exception
    (contestation, violences…) présente dans les titres des sources ou dans le résumé."""
    plafond = config["gravite"]["plafonds"].get(categorie)
    if not plafond or gravite <= plafond["max"]:
        return gravite, None
    texte = E.normaliser(" ".join(textes))
    if any(re.search(rf"\b{re.escape(m)}", texte) for m in plafond["exceptions"]):
        return gravite, None
    return plafond["max"], f"gravité {gravite} proposée, ramenée à {plafond['max']} : {categorie} sans contestation ni violences"


def sans_accents(texte: str) -> bool:
    """Français écrit sans accents (« Le president de la Cour penale… ») : refusé à partir de 6 mots,
    car une phrase française de cette longueur contient presque toujours un accent."""
    mots = re.findall(r"[A-Za-zÀ-ÿ']+", texte)
    return len(mots) >= 6 and not re.search(r"[àâçéèêëîïôûùüÿœÀÂÇÉÈÊËÎÏÔÛÙÜŸŒ]", texte)


def en_francais_titre(titre: str) -> bool:
    """Titre court : peu de mots outils ; on accepte aussi les accents ou l'absence de mots outils anglais."""
    mots = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", titre.lower())
    en = sum(1 for m in mots if m in MOTS_EN)
    fr = sum(1 for m in mots if m in MOTS_FR or m.startswith(("l'", "d'", "qu'")))
    return (fr > en) or (en == 0 and bool(re.search(r"[àâçéèêëîïôûùüÿœ]", titre))) or (en == 0 and fr == 0 and len(mots) <= 4)


# ------------------------------------------------------------------ quotas

def _jour(t: datetime, fuseau: str) -> str:
    return t.astimezone(ZoneInfo(fuseau)).date().isoformat()


class QuotaModele:
    """Compteur persistant d'un modèle (etat["quota_gemini"]["modeles"][nom])."""

    def __init__(self, etat_modeles: dict, modele: dict, cfg: dict, horloge, dormir):
        self.nom, self.modele, self.cfg = modele["nom"], modele, cfg
        self.e = etat_modeles.setdefault(self.nom, {"jour": None, "appels": 0, "recents": []})
        self.horloge, self.dormir = horloge, dormir
        self.autorises_execution = None  # fixé au premier usage de l'exécution
        self.appels_execution = 0
        self.hors_service = False  # en panne pendant cette exécution (5xx après reprises, 4xx) : modèle suivant

    # Limites effectives (marge, limite apprise)
    def rpd(self) -> int:
        limite = min(self.modele["rpd"], self.e.get("limite_apprise") or self.modele["rpd"])
        return max(1, math.floor(limite * (1 - self.cfg["marge"])))

    def rpm(self) -> int:
        return max(1, math.floor(self.modele["rpm"] * (1 - self.cfg["marge"])))

    def _jour_courant(self, t: datetime) -> None:
        j = _jour(t, self.cfg["fuseau_quota"])
        if self.e.get("jour") != j:
            self.e.update({"jour": j, "appels": 0, "plafond_jour": None})

    def restants(self, t: datetime | None = None) -> int:
        t = t or self.horloge()
        self._jour_courant(t)
        plafond = self.rpd() if self.e.get("plafond_jour") is None else min(self.rpd(), self.e["plafond_jour"])
        return max(0, plafond - self.e["appels"])

    def executions_restantes(self, t: datetime) -> int:
        local = t.astimezone(ZoneInfo(self.cfg["fuseau_quota"]))
        minuit = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return max(1, math.ceil((minuit - local).total_seconds() / 3600))

    def disponibles(self) -> int:
        """Appels encore permis à ce modèle pendant cette exécution."""
        if self.hors_service:
            return 0
        t = self.horloge()
        reste = self.restants(t)
        if self.autorises_execution is None:
            self.autorises_execution = min(self.cfg["appels_max_par_execution"], reste,
                                           math.ceil(reste / self.executions_restantes(t)))
        return max(0, min(reste, self.autorises_execution - self.appels_execution))

    def attendre_creneau(self) -> None:
        intervalle = 60 / self.rpm()
        while True:
            t = self.horloge()
            recents = [r for r in self.e.get("recents", []) if t - datetime.fromisoformat(r) < timedelta(seconds=60)]
            self.e["recents"] = recents
            attente = 0.0
            if recents:
                attente = intervalle - (t - datetime.fromisoformat(recents[-1])).total_seconds()
            if len(recents) >= self.rpm():
                attente = max(attente, 60 - (t - datetime.fromisoformat(recents[0])).total_seconds())
            if attente <= 0:
                return
            self.dormir(attente)

    def enregistrer(self) -> None:
        t = self.horloge()
        self._jour_courant(t)
        self.e["appels"] += 1
        self.e["recents"] = (self.e.get("recents", []) + [t.isoformat()])[-self.rpm():]
        self.appels_execution += 1

    def epuise_jusqua_demain(self, apprendre: bool) -> None:
        """429 : plus d'appel à ce modèle avant le prochain jour de quota. Si le message indique
        le quota du jour, la limite observée est retenue pour les jours suivants."""
        self.e["plafond_jour"] = self.e["appels"]
        if apprendre and self.e["appels"] > 0:
            self.e["limite_apprise"] = min(self.e.get("limite_apprise") or 10 ** 6, self.e["appels"])

    def resume(self) -> dict:
        self.restants()
        return {"modele": self.nom, "appels": self.e["appels"], "limite_jour": self.rpd(), "limite_minute": self.rpm(),
                "epuise": self.e.get("plafond_jour") is not None, "limite_apprise": self.e.get("limite_apprise")}


class Quotas:
    """Quotas de tous les modèles de la chaîne, et plafond de l'exécution."""

    def __init__(self, etat: dict, cfg: dict, horloge=None, dormir=time.sleep):
        self.cfg = cfg
        self.horloge = horloge or (lambda: datetime.now(timezone.utc))
        base = etat.get("quota_gemini") or {}
        if "modeles" not in base:  # ancien format (un seul compteur) : on repart de zéro
            base = {"modeles": {}}
        etat["quota_gemini"] = base
        self.modeles = [QuotaModele(base["modeles"], m, cfg, self.horloge, dormir) for m in cfg["modeles"]]
        self.dormir = dormir

    def jour(self, t: datetime | None = None) -> str:
        return _jour(t or self.horloge(), self.cfg["fuseau_quota"])

    def appels_execution(self) -> int:
        return sum(q.appels_execution for q in self.modeles)

    def resume(self) -> dict:
        modeles = [q.resume() for q in self.modeles]
        return {"jour": self.jour(), "appels": sum(m["appels"] for m in modeles),
                "quota_jour": sum(m["limite_jour"] for m in modeles), "modeles": modeles,
                "modele": self.modeles[0].nom}


# ------------------------------------------------------------------ appel

def _type_429(texte: str) -> str:
    t = texte.lower()
    if re.search(r"per ?day|perday|daily|quota_exceeded|requests per day", t):
        return "jour"
    if re.search(r"per ?minute|perminute|rate_limit_exceeded|retrydelay", t):
        return "minute"
    return "inconnu"


def _retry_delay(texte: str) -> float | None:
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', texte)
    return float(m.group(1)) if m else None


def appeler(consigne: str, q: QuotaModele, cfg: dict, cle: str, poster=None) -> str:
    """Un appel au modèle de q, avec reprises (5xx, réseau, 429 par minute). Chaque essai compte dans le quota."""
    import requests
    poster = poster or requests.post
    attentes = cfg["attentes_reprise_secondes"]
    essais_429 = 0
    derniere = None
    for essai in range(1, cfg["essais"] + 1):
        q.attendre_creneau()
        q.enregistrer()
        try:
            r = poster(URL_GEMINI.format(modele=q.nom), params={"key": cle}, timeout=cfg["delai_reponse_secondes"],
                       json={"contents": [{"parts": [{"text": consigne}]}],
                             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}})
            code, corps = r.status_code, r.text or ""
        except Exception as e:  # réseau
            code, corps = None, f"{type(e).__name__}: {str(e)[:120]}"
        if code == 200:
            try:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, ValueError) as e:
                raise ErreurIA(f"{q.nom} : réponse sans texte") from e
        extrait = re.sub(r"\s+", " ", corps)[:160]
        LOG.warning("Gemini %s : %s (essai %d/%d) %s", q.nom, f"HTTP {code}" if code else "erreur réseau", essai, cfg["essais"], extrait)
        derniere = f"{q.nom} : {'HTTP ' + str(code) if code else 'réseau'} : {extrait}"
        if code == 429:
            nature = _type_429(corps)
            essais_429 += 1
            if nature == "minute" and essais_429 == 1 and essai < cfg["essais"]:
                q.dormir(min(cfg["attente_429_minute_max_secondes"], _retry_delay(corps) or 30))
                continue
            raise ErreurQuota(derniere, jour=nature == "jour")
        if code is None or code >= 500:
            if essai < cfg["essais"]:
                q.dormir(attentes[min(essai - 1, len(attentes) - 1)])
                continue
            raise ErreurIA(f"{derniere} (après {cfg['essais']} essais)")
        raise ErreurIA(derniere)  # 400, 403, 404 (modèle inconnu)… : inutile d'insister
    raise ErreurIA(derniere or f"{q.nom} : échec")


# ------------------------------------------------------------------ prompt

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
    reperes = " ; ".join(f"{k} = {v}" for k, v in config["gravite"]["reperes"].items())
    regles_plafonds = " ".join(f"Catégorie « {c} » : {p['texte']}." for c, p in config["gravite"]["plafonds"].items())
    pays = ", ".join(sorted(set(config["pays"]) | {k for k in config["autres_pays"] if not k.startswith("_")}))
    return (
        "Tu es analyste géopolitique pour un suivi des marchés. Rédige TOUS les textes en français (les sources peuvent "
        "être en anglais : traduis), ton froid et factuel : pas de superlatifs, pas de dramatisation (mots interdits : "
        + ", ".join(MOTS_INTERDITS[:10] + MOTS_DRAMATISATION[:8]) + "). "
        "Distingue les faits (résumé, tirés des sources) des interprétations (impact sur les marchés). "
        "Règle absolue : chaque affirmation cite au moins une source par son identifiant (S1, S2…) parmi celles fournies "
        "pour CET événement ; n'utilise aucune autre connaissance que ces titres. Une affirmation sans source sera supprimée. "
        "Gravité de 1 à 5, avec ces repères : " + reperes + ". 4 ou 5 seulement si au moins deux sources de domaines "
        "différents le confirment. " + regles_plafonds + " "
        "Titre : un titre en français, factuel, de 12 mots au plus, qui nomme l'acteur et le fait (pas de « en direct », "
        "« en images », « ce qu'il faut savoir »). "
        "Écris un français correct, avec tous les accents (é, è, à, ç…). "
        "Pays (\"pays\") : seulement les pays ACTEURS ou DIRECTEMENT TOUCHÉS. Le pays qui accueille une négociation, un "
        "sommet ou une réunion va dans \"lieux\" (ex. pourparlers sur l'Ukraine à Abou Dabi : pays UA, RU, et US s'ils "
        "participent ; lieux AE) ; un pays dont un dirigeant commente seulement n'est ni l'un ni l'autre. "
        "S'il n'y a pas de pays acteur et que le "
        "thème est mondial (économie mondiale, climat, système financier international), indique \"portee\": \"mondiale\". "
        "Si deux événements de la liste décrivent le même fait, indique pour le second \"meme_que\": \"identifiant du premier\".\n"
        f"Catégories possibles : {categories}. Actifs possibles : {actifs}. Codes pays possibles : {pays}.\n"
        "Réponds uniquement en JSON : {\"analyses\": [{\"evenement\": \"id\", \"meme_que\": null, "
        "\"titre\": \"titre en français\", \"portee\": \"pays|mondiale\", \"lieux\": [], "
        "\"resume\": [{\"texte\": \"phrase factuelle en français\", \"sources\": [\"S1\"]}, {\"texte\": \"2e phrase\", \"sources\": [\"S2\"]}], "
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
        # Renvois laissés dans le texte (« … [S10]. ») : retirés, les sources sont déjà reliées
        texte = re.sub(r"\s*[\[(]S\d+(?:\s*[,;]\s*S\d+)*[\])]", "", a["texte"]).strip()
        if not ids:
            supprimees.append(f"sans source : {texte[:80]}")
            continue
        if not sobre(texte) or len(texte) > 400:
            supprimees.append(f"ton non conforme : {texte[:80]}")
            continue
        if not en_francais(texte):
            supprimees.append(f"pas en français : {texte[:80]}")
            continue
        if sans_accents(texte):
            supprimees.append(f"français sans accents : {texte[:80]}")
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
        return None, supprimees + ["résumé sans affirmation sourcée en français : version sans IA"]
    actifs = []
    for a in _affirmations(brut.get("actifs"), par_id, 6, supprimees):
        if a.get("actif") in config["actifs"] and a.get("sens") in SENS:
            actifs.append(a)
        else:
            supprimees.append(f"actif ou sens inconnu : {a.get('actif')} / {a.get('sens')}")
    contre = _affirmations(brut.get("contre"), par_id, 3, supprimees)
    connus = set(config["pays"]) | {k for k in config["autres_pays"] if not k.startswith("_")}
    pays = [p for p in (brut.get("pays") or []) if p in connus]
    categorie = brut.get("categorie") if brut.get("categorie") in config["categories"] else e["categorie"]
    try:
        gravite = max(1, min(5, int(brut.get("gravite"))))
    except (TypeError, ValueError):
        gravite = E.gravite_regles(e, config)
    gravite_ia = gravite  # avant les plafonds : le contrôle (gravite.py) part de la valeur de Gemini
    cites = {s["id"]: s for a in resume + actifs + contre for s in a["_cites"]}
    independantes = E.independantes(list(cites.values()))
    note_gravite = None
    if gravite >= 4 and independantes < 2:
        note_gravite = f"gravité {gravite} proposée, plafonnée à 3 : une seule source indépendante citée"
        gravite = 3
    gravite, note = plafonner(gravite, categorie, [s["titre"] for s in sources] + [a["texte"] for a in resume], config)
    note_gravite = note or note_gravite
    titre = None
    if isinstance(brut.get("titre"), str):
        t = re.sub(r"\s*[\[(]S\d+(?:\s*[,;]\s*S\d+)*[\])]", "", brut["titre"]).strip().rstrip(".")
        if 8 <= len(t) <= 160 and sobre(t) and en_francais_titre(t) and not sans_accents(t) and not E.format_exclu(t):
            titre = t
        else:
            supprimees.append(f"titre refusé : {t[:80]}")
    for a in resume + actifs + contre:
        a.pop("_cites", None)
    analyse = {
        "titre": titre, "mondial": brut.get("portee") == "mondiale",
        "lieux_ia": [p for p in (brut.get("lieux") or []) if p in connus], "gravite_ia": gravite_ia,
        "resume": resume, "pays_ia": pays, "categorie": categorie, "gravite": gravite, "note_gravite": note_gravite,
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
        return e.get("essais_ia", 0) < ESSAIS_IA_MAX
    if "titre" not in a or "lieux_ia" not in a:  # analyse d'avant les titres en français et les lieux : refaite une fois
        return True
    cfg = config["gemini"]
    age = maintenant - datetime.fromisoformat(a["analyse_le"].replace("Z", "+00:00"))
    return (age >= timedelta(hours=cfg["reanalyse_apres_heures"])
            and len(e["articles"]) >= cfg["reanalyse_si_sources_multipliees_par"] * a.get("nb_articles", 1))


def priorite(e: dict, config: dict) -> tuple:
    """Ordre d'analyse : gravité estimée 3 ou plus d'abord, puis score de sélection, puis le plus récent."""
    gravite = (e.get("analyse") or {}).get("gravite") or E.gravite_regles(e, config)
    return (gravite >= 3, E.score_selection(e, config), e["dernier"])


ESSAIS_IA_MAX = 3


def appel_chaine(prompt: str, quotas: Quotas, cfg: dict, cle: str, poster, rapport: dict) -> tuple[str | None, str | None]:
    """Un appel, en descendant la chaîne de modèles (quotas, pannes) ; (texte, modèle) ou (None, None)."""
    for q in quotas.modeles:
        if q.disponibles() <= 0 or quotas.appels_execution() >= cfg["appels_max_par_execution"]:
            continue
        avant = q.appels_execution
        try:
            return appeler(prompt, q, cfg, cle, poster), q.nom
        except ErreurQuota as err:
            q.epuise_jusqua_demain(apprendre=err.jour)
            rapport["quota_atteint"] = True
            rapport["erreurs"].append(f"{err} → {q.nom} suspendu jusqu'au lendemain (jour du Pacifique)")
        except ErreurIA as err:
            q.hors_service = True
            rapport["erreurs"].append(str(err))
        finally:
            rapport["appels"] += q.appels_execution - avant
    return None, None


def former_lots(candidats: list[dict], n: int) -> list[list[dict]]:
    """Lots de n événements, dans l'ordre de priorité ; chaque lot est complété d'abord par les
    événements qui ont les mêmes pays et la même catégorie que son premier, pour que Gemini puisse
    signaler les doublons (« meme_que »)."""
    restants, lots = list(candidats), []
    cle = lambda e: (tuple(sorted(e.get("pays_principaux") or e["pays"])), e["categorie"])
    while restants:
        tete = restants.pop(0)
        proches = [e for e in restants if cle(e) == cle(tete) or set(cle(e)[0]) & set(cle(tete)[0]) and cle(e)[1] == cle(tete)[1]]
        lot = [tete] + proches[: n - 1]
        for e in lot[1:]:
            restants.remove(e)
        while len(lot) < n and restants:
            lot.append(restants.pop(0))
        lots.append(lot)
    return lots


def analyser(candidats: list[dict], config: dict, quotas: Quotas, maintenant: datetime, cle: str | None = None,
             poster=None) -> dict:
    """Analyse les candidats (dans l'ordre de priorité), dans la limite des quotas, en descendant la
    chaîne de modèles si besoin. Écrit e["analyse"] pour chaque événement validé."""
    cfg = config["gemini"]
    cle = cle if cle is not None else os.environ.get("GEMINI_API_KEY")
    rapport = {"modele": cfg["modeles"][0]["nom"], "appels": 0, "analyses": 0, "rejets": 0, "suppressions": [],
               "erreur": None, "erreurs": [], "quota_atteint": False, "cle": bool(cle), "modeles_utilises": {},
               "reussites": 0, "fusions": []}
    if not cle or not candidats:
        return rapport
    candidats = sorted(candidats, key=lambda e: priorite(e, config), reverse=True)
    lots = former_lots(candidats, cfg["evenements_par_appel"])
    for lot in lots:
        if quotas.appels_execution() >= cfg["appels_max_par_execution"]:
            break
        sources = {e["id"]: sources_numerotees(e) for e in lot}
        texte, modele = appel_chaine(consigne(lot, config, sources), quotas, cfg, cle, poster, rapport)
        if texte is None:
            if not any(q.disponibles() > 0 for q in quotas.modeles):
                break
            continue
        try:
            reponse = json.loads(texte)
            analyses = {a.get("evenement"): a for a in (reponse.get("analyses") or []) if isinstance(a, dict)}
        except (ValueError, AttributeError) as err:
            rapport["erreurs"].append(f"{modele} : réponse illisible ({str(err)[:80]})")
            continue
        rapport["reussites"] += 1
        rapport["modeles_utilises"][modele] = rapport["modeles_utilises"].get(modele, 0) + 1
        ids = {e["id"] for e in lot}
        for e in lot:
            brut = analyses.get(e["id"])
            if isinstance(brut, dict) and brut.get("meme_que") in ids - {e["id"]}:
                rapport["fusions"].append((brut["meme_que"], e["id"]))
            analyse, supprimees = valider(brut, e, config, sources[e["id"]]) if isinstance(brut, dict) else (None, ["événement absent de la réponse"])
            rapport["suppressions"] += [f"{e['id']} : {s}" for s in supprimees]
            if analyse:
                e["analyse"] = {**analyse, "analyse_le": E.iso(maintenant), "nb_articles": len(e["articles"]), "modele": modele}
                e.pop("essais_ia", None)
                rapport["analyses"] += 1
            else:
                e["essais_ia"] = e.get("essais_ia", 0) + 1  # au plus ESSAIS_IA_MAX analyses refusées par événement
                rapport["rejets"] += 1
    if rapport["erreurs"] and not rapport["reussites"]:
        rapport["erreur"] = rapport["erreurs"][-1][:240]
    return rapport


# ------------------------------------------------------------------ thèmes et traductions

def _valide_titre(t, supprimees: list) -> str | None:
    if not isinstance(t, str):
        return None
    t = re.sub(r"\s*[\[(]S\d+(?:\s*[,;]\s*S\d+)*[\])]", "", t).strip().rstrip(".")
    if 8 <= len(t) <= 160 and sobre(t) and en_francais_titre(t) and not sans_accents(t) and not E.format_exclu(t):
        return t
    supprimees.append(f"titre refusé : {t[:80]}")
    return None


def confirmer_themes(groupes: list[list[dict]], config: dict, quotas: Quotas, cle: str | None, poster, rapport: dict) -> dict:
    """Demande à Gemini de confirmer les regroupements en thème (plusieurs thèmes par appel).
    Renvoie {clé du thème : {"membres": [ids confirmés], "titre": titre français ou None}}."""
    res: dict[str, dict] = {}
    if not cle or not groupes:
        return res
    n = config["themes"]["confirmation_par_appel"]
    for i in range(0, len(groupes), n):
        lot = groupes[i:i + n]
        blocs = [{"theme": k, "evenements": [{"id": e["id"], "date": e["dernier"][:10],
                                              "titre": (e.get("analyse") or {}).get("titre") or E.titre_reference(e)} for e in g]}
                 for k, g in enumerate(lot)]
        prompt = ("Tu regroupes des événements géopolitiques en « thèmes en cours ». Pour chaque thème proposé ci-dessous, "
                  "indique les événements qui relèvent bien du même sujet suivi dans le temps (mêmes acteurs, même situation : "
                  "par exemple des frappes successives dans un même conflit), et écarte les autres. Donne aussi un titre de thème "
                  "en français correct, avec les accents, factuel, de 10 mots au plus, sans superlatif. "
                  "Réponds uniquement en JSON : {\"themes\": [{\"theme\": 0, \"membres\": [\"id\", \"id\"], \"titre\": \"…\"}]}\n"
                  "Thèmes proposés :\n" + json.dumps(blocs, ensure_ascii=False))
        texte, _ = appel_chaine(prompt, quotas, config["gemini"], cle, poster, rapport)
        if texte is None:
            break
        try:
            reponses = json.loads(texte).get("themes") or []
        except (ValueError, AttributeError):
            rapport["erreurs"].append("confirmation des thèmes : réponse illisible")
            continue
        rapport["reussites"] += 1
        for r in reponses:
            try:
                g = lot[int(r.get("theme"))]
            except (TypeError, ValueError, IndexError):
                continue
            ids = {e["id"] for e in g}
            membres = [m for m in (r.get("membres") or []) if m in ids]
            res[E.cle_theme(g)] = {"membres": membres, "titre": _valide_titre(r.get("titre"), rapport["suppressions"])}
    return res


def traduire_titres(titres: list[str], config: dict, quotas: Quotas, cle: str | None, poster, rapport: dict) -> dict:
    """Traduit en français des titres d'articles (un appel pour 40 titres au plus). {titre : traduction}."""
    res: dict[str, str] = {}
    if not cle or not titres:
        return res
    for i in range(0, len(titres), 40):
        lot = titres[i:i + 40]
        prompt = ("Traduis ces titres d'articles en français correct, avec les accents, en gardant le sens exact, sans rien "
                  "ajouter ni dramatiser. Réponds uniquement en JSON : {\"traductions\": [\"…\", …]} dans le même ordre.\n"
                  + json.dumps(lot, ensure_ascii=False))
        texte, _ = appel_chaine(prompt, quotas, config["gemini"], cle, poster, rapport)
        if texte is None:
            break
        try:
            traductions = json.loads(texte).get("traductions") or []
        except (ValueError, AttributeError):
            rapport["erreurs"].append("traduction des titres : réponse illisible")
            continue
        rapport["reussites"] += 1
        for origine, t in zip(lot, traductions):
            t = _valide_titre(t, rapport["suppressions"])
            if t:
                res[origine] = t
    return res
