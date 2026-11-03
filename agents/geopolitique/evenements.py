"""
Regroupement des articles par événement, sans IA.

- Pays : noms reconnus dans le titre et la description (config « pays » et « autres_pays ») ;
  les sigles en majuscules (US, UK, EU…) ne sont reconnus qu'en majuscules.
- Catégorie : mots-clés (config « categories ») ; une expression de plusieurs mots pèse plus
  qu'un mot seul (« trade war » l'emporte sur « war »). La requête GDELT qui a trouvé l'article
  compte comme un indice.
- Événement : articles qui partagent au moins un pays (ou aucun pays des deux côtés), à moins de
  48 h d'écart, et des mots significatifs : au moins 2 avec un recouvrement de similarite_min pour
  une même catégorie, au moins 3 avec un recouvrement de 50 % sinon. La catégorie de l'événement
  est la plus fréquente parmi ses articles. Les événements sont gardés d'une exécution à l'autre
  (data/geopolitique/etat.json) : un nouvel article rejoint son événement au lieu d'en créer un.
- Sélection : score fondé sur le nombre de domaines distincts (volume de couverture), la
  présence d'une source officielle et les pays suivis concernés.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone

MOTS_VIDES = set("""
the and for with from that this have has had will would could should into over after before about amid
says said say new news live latest update updates more than they their them its his her who what when where
why how also been being were was are not but all any can may might just year years week day days today
time first last next back still says report reports official officials minister government president state
les des une pour avec dans sur par aux est sont qui que quoi dont mais plus moins leur leurs ses son sa
cette ces entre apres avant selon contre sans sous vers chez deux trois face fait faire
""".split())


def normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFD", (texte or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _motif(nom: str) -> re.Pattern:
    return re.compile(rf"(?<![\w.]){re.escape(nom)}(?![\w])")


class Detecteur:
    """Reconnaissance des pays et des catégories (motifs compilés une fois)."""

    def __init__(self, config: dict):
        self.pays: list[tuple[str, re.Pattern, bool]] = []
        for groupe in ("pays", "autres_pays"):
            for code, p in config[groupe].items():
                if code.startswith("_"):
                    continue
                for nom in p["noms"]:
                    sensible = nom.upper() == nom and any(c.isalpha() for c in nom)
                    self.pays.append((code, _motif(nom if sensible else normaliser(nom)), sensible))
        self.categories = [(cle, [(normaliser(m), _motif(normaliser(m)), len(m.split())) for m in c["mots"]])
                           for cle, c in config["categories"].items()]

    def pays_de(self, texte: str) -> list[str]:
        brut, norm = texte or "", normaliser(texte)
        trouves = []
        for code, motif, sensible in self.pays:
            if code not in trouves and motif.search(brut if sensible else norm):
                trouves.append(code)
        return trouves

    def categorie_de(self, texte: str, indice: str | None = None) -> str | None:
        norm = normaliser(texte)
        meilleurs = {}
        for cle, mots in self.categories:
            poids = sum(n for _, motif, n in mots if motif.search(norm))
            if indice == cle and poids:
                poids += 1
            if poids:
                meilleurs[cle] = poids
        return max(meilleurs, key=lambda c: meilleurs[c]) if meilleurs else None


def jetons(texte: str, exclus: set[str] = frozenset()) -> set[str]:
    res = set()
    for m in re.findall(r"[a-z0-9][a-z0-9-]{3,}", normaliser(texte)):
        m = racine(m)
        if m not in MOTS_VIDES and m not in exclus and not m.isdigit():
            res.add(m)
    return res


def racine(m: str) -> str:
    """Racinisation légère (anglais et français) : bombing, bombs, bombed → bomb."""
    for fin in ("ing", "ed", "es", "s", "e"):
        if len(m) > len(fin) + 3 and m.endswith(fin):
            m = m[: -len(fin)]
            break
    if len(m) > 4 and m[-1] == m[-2]:  # « bomb » mais « kill » → « kil » des deux côtés
        m = m[:-1]
    return m


def recouvrement(a: set[str], b: set[str]) -> tuple[int, float]:
    if not a or not b:
        return 0, 0.0
    commun = len(a & b)
    return commun, commun / min(len(a), len(b))


def _date(texte: str) -> datetime:
    return datetime.fromisoformat(texte.replace("Z", "+00:00"))


def identifiant(article: dict) -> str:
    return "evt-" + hashlib.sha256(article["url"].encode()).hexdigest()[:12]


def preparer(article: dict, det: Detecteur) -> dict | None:
    """Ajoute pays, catégorie et mots significatifs ; None si l'article n'est pas géopolitique."""
    texte = f"{article['titre']}. {article.get('description') or ''}"
    categorie = det.categorie_de(" ".join([texte, *article.get("categories", [])]), article.get("indice"))
    if article.get("categorie_par_defaut") and not categorie:
        categorie = article["categorie_par_defaut"]
    if not categorie:
        return None
    pays = det.pays_de(texte)
    # Les pays détectés comptent comme des mots (« Russian » et « Russia » → @RU)
    return {**article, "pays": pays, "categorie": categorie,
            "jetons": sorted(jetons(article["titre"]) | {f"@{c}" for c in det.pays_de(article["titre"])})}


def regrouper(articles: list[dict], evenements: list[dict], config: dict, maintenant: datetime) -> list[dict]:
    """Rattache chaque article à un événement existant ou en crée un. Renvoie les événements
    créés ou modifiés pendant cet appel (la liste `evenements` est mise à jour en place)."""
    seuil = config["selection"]["similarite_min"]
    touches = {}
    for a in sorted(articles, key=lambda x: x.get("date") or ""):
        ja = set(a["jetons"])
        date_a = _date(a["date"]) if a.get("date") else maintenant
        meilleur, score_meilleur = None, 0.0
        for e in evenements:
            if abs((date_a - _date(e["dernier"])).total_seconds()) > 48 * 3600:
                continue
            if a["pays"] and e["pays"] and not set(a["pays"]) & set(e["pays"]):
                continue
            if bool(a["pays"]) != bool(e["pays"]):
                continue
            commun, r = recouvrement(ja, set(e["noyau"]))
            mots = len({j for j in ja & set(e["noyau"]) if not j.startswith("@")})
            # Même catégorie : recouvrement suffisant ; autre catégorie : recouvrement fort
            proche = (commun >= 2 and mots >= 1 and r >= seuil) if e["categorie"] == a["categorie"] else (commun >= 3 and mots >= 2 and r >= 0.5)
            if proche and r > score_meilleur:
                meilleur, score_meilleur = e, r
        if meilleur is None:
            meilleur = {"id": identifiant(a), "categorie": a["categorie"], "pays": [], "noyau": sorted(ja),
                        "premier": a.get("date") or iso(maintenant), "dernier": a.get("date") or iso(maintenant),
                        "articles": [], "cree_le": iso(maintenant)}
            evenements.append(meilleur)
        if any(x["url"] == a["url"] for x in meilleur["articles"]):
            continue
        meilleur["articles"].append({k: a.get(k) for k in ("titre", "url", "domaine", "date", "origine", "source", "officiel", "description")})
        meilleur["pays"] = list(dict.fromkeys(meilleur["pays"] + a["pays"]))
        # Catégorie de l'événement : la plus fréquente parmi ses articles (la première en cas d'égalité)
        votes = meilleur.setdefault("votes", {})
        votes[a["categorie"]] = votes.get(a["categorie"], 0) + 1
        meilleur["categorie"] = max(votes, key=lambda c: (votes[c], c == meilleur["categorie"]))
        if len(meilleur["articles"]) <= 3:  # le noyau : les premiers articles
            meilleur["noyau"] = sorted(set(meilleur["noyau"]) | ja)
        meilleur["dernier"] = max(meilleur["dernier"], a.get("date") or meilleur["dernier"])
        meilleur["premier"] = min(meilleur["premier"], a.get("date") or meilleur["premier"])
        touches[meilleur["id"]] = meilleur
    return list(touches.values())


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def domaines(e: dict) -> list[str]:
    return sorted({a["domaine"] for a in e["articles"] if a.get("domaine")})


def titre_normalise(titre: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normaliser(titre)).strip()


def independantes(articles: list[dict]) -> int:
    """Sources indépendantes : domaines distincts, une dépêche reprise mot pour mot sur plusieurs
    sites (syndication AP, NPR…) ne comptant qu'une fois."""
    domaines_vus, titres_vus, n = set(), set(), 0
    for a in articles:
        d, t = a.get("domaine"), titre_normalise(a.get("titre") or "")
        if d in domaines_vus or t in titres_vus:
            domaines_vus.add(d)
            titres_vus.add(t)
            continue
        domaines_vus.add(d)
        titres_vus.add(t)
        n += 1
    return n


def officiel(e: dict) -> bool:
    return any(a.get("officiel") for a in e["articles"])


CATEGORIES_A_ENJEU = {"sanctions", "commerce", "conflit", "coup", "maritime"}


def score_selection(e: dict, config: dict) -> float:
    """Volume de couverture (domaines distincts), source officielle (+3 pour une mesure ou un conflit,
    +1 pour un communiqué protocolaire), pays suivis (+1,5 chacun, au plus 3), présence dans GDELT (+1)."""
    suivis = [p for p in e["pays"] if p in config["pays"]]
    gdelt = any(a.get("origine") == "gdelt" for a in e["articles"])
    bonus = (3 if e["categorie"] in CATEGORIES_A_ENJEU else 1) if officiel(e) else 0
    return round(2 * math.log2(1 + independantes(e["articles"])) + bonus + 1.5 * min(3, len(suivis)) + (1 if gdelt else 0), 2)


def significatif(e: dict, config: dict) -> bool:
    s = config["selection"]
    return score_selection(e, config) >= s["score_min"] and (officiel(e) or independantes(e["articles"]) >= s["domaines_min_sans_officiel"])


def gravite_regles(e: dict, config: dict) -> int:
    """Gravité sans IA : base de la catégorie, +1 si la couverture est large (8 domaines ou plus).
    Plafonnée à 3 : une gravité de 4 ou 5 demande l'analyse et au moins 2 sources indépendantes."""
    g = config["categories"][e["categorie"]]["gravite_base"] + (1 if independantes(e["articles"]) >= 8 else 0)
    return max(1, min(3, g))


def sources_publiques(e: dict, maxi: int = 12) -> list[dict]:
    """Sources affichées : officielles d'abord, puis un article par domaine, du plus récent au plus ancien."""
    tri = sorted(e["articles"], key=lambda a: (not a.get("officiel"), (a.get("date") or "")), reverse=False)
    officielles = [a for a in tri if a.get("officiel")]
    autres = sorted((a for a in e["articles"] if not a.get("officiel")), key=lambda a: a.get("date") or "", reverse=True)
    res, vus, titres = list(officielles), set(), set()
    for a in autres:  # un article par domaine, et une seule copie d'une dépêche reprise à l'identique
        t = titre_normalise(a.get("titre") or "")
        if a["domaine"] not in vus and t not in titres:
            vus.add(a["domaine"])
            titres.add(t)
            res.append(a)
    return [{k: a.get(k) for k in ("titre", "url", "domaine", "date", "officiel", "source")} for a in res[:maxi]]


def titre_reference(e: dict) -> str:
    srcs = sources_publiques(e)
    return srcs[0]["titre"] if srcs else e["articles"][0]["titre"]


def nettoyer(evenements: list[dict], maintenant: datetime, garde_jours: int, max_articles: int = 40) -> list[dict]:
    limite = iso(maintenant - timedelta(days=garde_jours))
    res = [e for e in evenements if e["dernier"] >= limite]
    for e in res:
        if len(e["articles"]) > max_articles:  # on garde les officiels et les plus récents
            e["articles"] = sorted(e["articles"], key=lambda a: (bool(a.get("officiel")), a.get("date") or ""), reverse=True)[:max_articles]
    return res
