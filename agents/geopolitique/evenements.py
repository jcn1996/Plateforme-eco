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

import functools
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


# Noms de pays d'un seul mot (racines) : exclus des mots significatifs, car les pays sont déjà
# représentés par leur code (« Iranian » et « Iran » → @IR). Rempli par Detecteur.
MOTS_PAYS: set[str] = set()
# Formats exclus comme titre de référence (galeries photo, directs, « ce qu'il faut savoir »…) : config « titres_exclus »
TITRES_EXCLUS: list[re.Pattern] = []


def format_exclu(titre: str) -> bool:
    t = normaliser(titre)
    return any(m.search(t) for m in TITRES_EXCLUS)


class Detecteur:
    """Reconnaissance des pays et des catégories (motifs compilés une fois)."""

    def __init__(self, config: dict):
        self.pays: list[tuple[str, re.Pattern, bool]] = []
        self.noms: dict[str, list[str]] = {}  # noms normalisés (minuscules), pour les lieux et les commentateurs
        lieux = config.get("lieux", {})
        self.mots_reunion = [normaliser(m) for m in lieux.get("mots_reunion", [])]
        self.prepositions = lieux.get("prepositions", ["in", "at", "a", "au", "aux", "en"])
        for groupe in ("pays", "autres_pays"):
            for code, p in config[groupe].items():
                if code.startswith("_"):
                    continue
                self.noms[code] = [normaliser(n) for n in p["noms"] if len(n) > 3]
                for nom in p["noms"]:
                    if " " not in nom and "." not in nom:
                        MOTS_PAYS.add(racine(normaliser(nom)))
                    sensible = nom.upper() == nom and any(c.isalpha() for c in nom)
                    self.pays.append((code, _motif(nom if sensible else normaliser(nom)), sensible))
        # Lieux (« talks … in Abu Dhabi », « pourparlers … à Abou Dabi », « Abu Dhabi talks », « pourparlers d'Abou Dabi »,
        # « UAE hosts talks » : le mot de réunion et le lieu sont proches) et commentateurs (« Germany's Merz says »)
        reunion = "|".join(re.escape(m) for m in self.mots_reunion) or "(?!)"
        preps = "|".join(self.prepositions)
        self.motif_reunion = re.compile(rf"(?<![\w])(?:{reunion})")
        self.motifs_lieu, self.motifs_commentateur = {}, {}
        for code, noms in self.noms.items():
            if not noms:
                continue
            n = "(?:" + "|".join(re.escape(x) for x in noms) + ")"
            self.motifs_lieu[code] = re.compile(
                rf"(?:{reunion})(?: [\w'-]+){{0,4}} (?:{preps}) (?:the )?{n}(?![\w])|(?<![\w]){n} (?:{reunion})"
                rf"|(?:{reunion}) (?:de |d'){n}(?![\w])|(?<![\w]){n} (?:hosts|accueille)")
            self.motifs_commentateur[code] = re.compile(rf"(?<![\w]){n}'s \w+(?: \w+)? (?:says|said|warns|urges|calls|insists)\b")
        TITRES_EXCLUS[:] = [re.compile(rf"(?<![\w]){re.escape(normaliser(m))}(?![\w])") for m in config.get("titres_exclus", [])]
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
        if m not in MOTS_VIDES and m not in exclus and m not in MOTS_PAYS and not m.isdigit():
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


def nettoyer_titre(titre: str) -> str:
    """Titres de GDELT : ponctuation détachée (« U . S . Carries Out… », « It Election Day . »)."""
    t = re.sub(r"\b([A-Z]) \. ([A-Z]) \.", r"\1.\2.", titre or "")
    t = re.sub(r"\s+([.,;:!?)])", r"\1", t)
    t = re.sub(r"\s+'\s*s\b", "'s", t)
    return re.sub(r"\s{2,}", " ", t).strip()


FR = set("le la les des du un une et est en au aux pour par sur avec dans qui que son sa ses ce cette".split())
EN = set("the and of to in is are was were has have with for on by that from as at after".split())


def langue_probable(texte: str) -> str:
    """fr ou en, d'après les mots outils (titres sans langue connue)."""
    mots = re.findall(r"[a-zà-ÿ']+", (texte or "").lower())
    return "fr" if sum(m in FR for m in mots) > sum(m in EN for m in mots) or re.search(r"[éèàçê]", texte or "") else "en"


def preparer(article: dict, det: Detecteur) -> dict | None:
    """Ajoute pays, catégorie et mots significatifs ; None si l'article n'est pas géopolitique."""
    article = {**article, "titre": nettoyer_titre(article["titre"])}
    if not article.get("langue"):
        article["langue"] = langue_probable(f"{article['titre']} {article.get('description') or ''}")
    texte = f"{article['titre']}. {article.get('description') or ''}"
    categorie = det.categorie_de(" ".join([texte, *article.get("categories", [])]), article.get("indice"))
    if article.get("categorie_par_defaut") and not categorie:
        categorie = article["categorie_par_defaut"]
    if not categorie:
        return None
    pays = det.pays_de(texte)
    pays_titre = det.pays_de(article["titre"])
    # Les pays détectés dans le titre comptent comme des mots (« Russian » et « Russia » → @RU)
    return {**article, "pays": pays, "pays_titre": pays_titre, "categorie": categorie,
            "jetons": sorted(jetons(article["titre"]) | {f"@{c}" for c in pays_titre})}


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
            mots_a = {j for j in ja if not j.startswith("@")}
            mots, r_mots = recouvrement(mots_a, {j for j in e["noyau"] if not j.startswith("@")})
            # Même catégorie : recouvrement suffisant ; autre catégorie : au moins 3 mots (hors pays) en commun,
            # la moitié des mots du titre (« US strikes Iranian island ahead of midterm elections » ne rejoint
            # pas les élections pour deux mots)
            proche = (commun >= 2 and mots >= 1 and r >= seuil) if e["categorie"] == a["categorie"] else (mots >= 3 and r_mots >= 0.5)
            if proche and r > score_meilleur:
                meilleur, score_meilleur = e, r
        if meilleur is None:
            meilleur = {"id": identifiant(a), "categorie": a["categorie"], "pays": [], "noyau": sorted(ja),
                        "premier": a.get("date") or iso(maintenant), "dernier": a.get("date") or iso(maintenant),
                        "articles": [], "cree_le": iso(maintenant)}
            evenements.append(meilleur)
        if any(x["url"] == a["url"] for x in meilleur["articles"]):
            continue
        meilleur["articles"].append({k: a.get(k) for k in ("titre", "url", "domaine", "date", "origine", "source", "officiel",
                                                            "description", "langue", "pays", "pays_titre")})
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


# ------------------------------------------------------------------ pays principaux

def pays_principaux(e: dict, det: Detecteur, resume: list[str] | None = None) -> list[str]:
    """Pays acteurs ou directement touchés : cités dans le titre de référence ou dans le résumé,
    ou présents dans plus de la moitié des articles (titre et description, au moins 2 articles).
    Un pays cité une fois dans un article parmi d'autres n'est pas retenu."""
    res = det.pays_de(titre_reference(e))
    if resume:
        # Pays du résumé : retenus s'ils sont aussi cités dans au moins un tiers des articles (un
        # résumé qui évoque l'Ukraine à propos des élections américaines ne rattache pas l'événement à
        # l'Ukraine) ; si aucun article ne nomme de pays (« Control of Congress… »), ceux du résumé
        du_resume = det.pays_de(" ".join(resume))
        presents = pays_presents(e, det, 1 / 3)
        res += [c for c in du_resume if c in presents] if (presents or res) else du_resume
    res += pays_majoritaires(e, det)
    return list(dict.fromkeys(res))


def _texte_norm(t: str) -> str:
    return normaliser(t or "").replace("’", "'")


def lieux_de(textes: list[str], det: Detecteur) -> list[str]:
    """Pays seulement lieu d'une négociation, d'un sommet ou d'une réunion : « talks … in Abu Dhabi »,
    « pourparlers à Abou Dabi »."""
    res = []
    for t in (_texte_norm(x) for x in textes if x):
        if not det.motif_reunion.search(t):
            continue
        for code, motif in det.motifs_lieu.items():
            if code not in res and motif.search(t):
                res.append(code)
    return res


def commentateurs_de(titre: str, det: Detecteur) -> list[str]:
    """Pays seulement cités comme auteur d'un commentaire : « …, Germany's Merz says »."""
    t = _texte_norm(titre)
    return [code for code, motif in det.motifs_commentateur.items() if motif.search(t)]


def pays_et_lieux(e: dict, det: Detecteur) -> tuple[list[str], list[str]]:
    """(pays principaux, lieux). Pays principaux : acteurs ou directement touchés (avec analyse : ceux
    que Gemini désigne comme acteurs, s'ils sont cités dans les articles ; sans analyse : titre de
    référence, résumé, majorité des articles). Le pays d'accueil d'une négociation n'est qu'un « lieu »,
    et un pays seulement commentateur n'est pas retenu."""
    a = e.get("analyse") or {}
    resume = [r["texte"] for r in a.get("resume", [])]
    cites = set(pays_presents(e, det, 0.0001)) | set(det.pays_de(" ".join(resume)))
    if a.get("pays_ia"):
        base = [c for c in a["pays_ia"] if c in cites]
    else:
        base = pays_principaux(e, det, resume)
    textes = [titre_reference(e), a.get("titre") or "", *resume]
    lieux = [c for c in dict.fromkeys(list(a.get("lieux_ia") or []) + lieux_de(textes, det)) if c in cites]
    # Un pays qui agit (sujet d'une phrase du résumé de Gemini) reste acteur même s'il accueille
    exclus = set(lieux) | set(commentateurs_de(titre_reference(e), det))
    principaux = [c for c in base if c not in exclus]
    return principaux, [c for c in lieux if c not in principaux]


# ------------------------------------------------------------------ thèmes en cours

def mots_theme(e: dict) -> set[str]:
    """Mots-clés de l'événement (titres des articles) et mots du titre français de Gemini."""
    titre_fr = (e.get("analyse") or {}).get("titre") or ""
    return set(mots_cles(e)) | set(_mots_titre(titre_fr))


def former_themes(evenements: list[dict], config: dict) -> list[list[dict]]:
    """Thèmes en cours (config « themes ») : événements à moins de `jours` jours d'écart (de proche en
    proche), mêmes pays principaux (ou l'un contenant l'autre, 2 pays communs au moins), même famille de
    catégories et au moins `mots_communs_min` mots-clés communs. Renvoie des groupes ; un événement
    seul forme un groupe d'un élément."""
    cfg = config["themes"]
    famille = lambda e: cfg["familles"].get((e.get("analyse") or {}).get("categorie") or e["categorie"], e["categorie"])
    parent = list(range(len(evenements)))

    def racine_uf(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    mots = [mots_theme(e) for e in evenements]
    for i, e1 in enumerate(evenements):
        p1 = set(e1.get("pays_principaux") or [])
        if not p1:
            continue
        for j in range(i + 1, len(evenements)):
            e2 = evenements[j]
            p2 = set(e2.get("pays_principaux") or [])
            # Mêmes pays principaux : identiques, ou l'un contient l'autre avec au moins 2 pays en commun
            # ({US, IR} et {US, IR, QA}) ; un seul pays commun ne suffit pas s'ils diffèrent
            memes = p1 == p2 or ((p1 <= p2 or p2 <= p1) and len(p1 & p2) >= 2)
            if not memes or famille(e1) != famille(e2):
                continue
            if abs((_date(e1["dernier"]) - _date(e2["dernier"])).total_seconds()) > cfg["jours"] * 86400:
                continue
            if len(mots[i] & mots[j]) >= cfg["mots_communs_min"]:
                parent[racine_uf(j)] = racine_uf(i)
    groupes: dict[int, list[dict]] = {}
    for i, e in enumerate(evenements):
        groupes.setdefault(racine_uf(i), []).append(e)
    return [sorted(g, key=lambda e: e["dernier"]) for g in groupes.values()]


def cle_theme(groupe: list[dict]) -> str:
    return "+".join(sorted(e["id"] for e in groupe))


def pays_majoritaires(e: dict, det: Detecteur | None = None) -> list[str]:
    """Pays présents (titre ou description) dans plus de la moitié des articles (au moins 2 articles)."""
    if len(e["articles"]) < 2:
        return []
    return pays_presents(e, det, 0.5, strict=True)


def pays_presents(e: dict, det: Detecteur | None, part: float, strict: bool = False) -> list[str]:
    """Pays cités (titre ou description) dans au moins `part` des articles (plus de `part` si `strict`)."""
    n = len(e["articles"])
    compte: dict[str, int] = {}
    for a in e["articles"]:
        presents = a.get("pays")
        if presents is None:
            presents = det.pays_de(f"{a.get('titre')}. {a.get('description') or ''}") if det else []
        for c in set(presents):
            compte[c] = compte.get(c, 0) + 1
    return [c for c, k in sorted(compte.items(), key=lambda x: -x[1]) if (k > part * n if strict else k >= part * n)]


# ------------------------------------------------------------------ fusion des doublons

@functools.lru_cache(maxsize=20000)
def _mots_titre(titre: str) -> frozenset[str]:
    return frozenset(jetons(nettoyer_titre(titre)))


def mots_cles(e: dict, part: float = 0.4) -> set[str]:
    """Mots de l'événement : présents dans au moins 40 % de ses titres distincts (une dépêche reprise
    mot pour mot ne compte qu'une fois). Un article qui mélange deux sujets ne suffit pas à les relier."""
    titres = {titre_normalise(a["titre"]): a["titre"] for a in e["articles"]}
    compte: dict[str, int] = {}
    for t in titres.values():
        for m in _mots_titre(t):
            compte[m] = compte.get(m, 0) + 1
    seuil = max(1, math.ceil(part * len(titres)))
    return {m for m, k in compte.items() if k >= seuil}


def titres_proches(e1: dict, e2: dict, souple: bool) -> bool:
    """Mots-clés des deux événements proches (part rapportée à l'événement qui en a le moins) :
    3 en commun et 35 % au moins ; ou 2 en commun et 50 % au moins si `souple` (même catégorie ou
    mêmes pays principaux)."""
    k1, k2 = mots_cles(e1), mots_cles(e2)
    if not k1 or not k2:
        return False
    commun = len(k1 & k2)
    part = commun / min(len(k1), len(k2))
    return (commun >= 3 and part >= 0.35) or (souple and commun >= 2 and part >= 0.5)


def _ecart_heures(e1: dict, e2: dict) -> float:
    """Écart entre les périodes de couverture des deux événements (0 si elles se chevauchent)."""
    d1, f1, d2, f2 = (_date(x) for x in (e1["premier"], e1["dernier"], e2["premier"], e2["dernier"]))
    if d1 <= f2 and d2 <= f1:
        return 0.0
    return min(abs((d2 - f1).total_seconds()), abs((d1 - f2).total_seconds())) / 3600


def fondre(base: dict, autre: dict) -> None:
    """Ajoute les articles de `autre` à `base` (l'analyse la plus fournie est gardée)."""
    urls = {a["url"] for a in base["articles"]}
    base["articles"] += [a for a in autre["articles"] if a["url"] not in urls]
    base["pays"] = list(dict.fromkeys(base["pays"] + autre["pays"]))
    votes = base.setdefault("votes", {base["categorie"]: 1})
    for c, k in (autre.get("votes") or {autre["categorie"]: 1}).items():
        votes[c] = votes.get(c, 0) + k
    base["categorie"] = max(votes, key=lambda c: (votes[c], c == base["categorie"]))
    base["noyau"] = sorted(set(base["noyau"]) | set(autre["noyau"]))
    base["premier"], base["dernier"] = min(base["premier"], autre["premier"]), max(base["dernier"], autre["dernier"])
    a1, a2 = base.get("analyse"), autre.get("analyse")
    if a2 and (not a1 or a2.get("nb_articles", 0) > a1.get("nb_articles", 0)):
        base["analyse"] = a2
    base["fusionnes"] = sorted(set(base.get("fusionnes", [])) | {autre["id"]} | set(autre.get("fusionnes", [])))


def fusionner(evenements: list[dict], det: Detecteur, paires_imposees: list[tuple[str, str]] = ()) -> tuple[list[dict], list[tuple[str, str]]]:
    """Regroupe les événements qui décrivent le même fait : couverture à moins de 48 h, mêmes pays
    principaux et titres proches ; plus les paires confirmées par Gemini (`paires_imposees`).
    Le plus fourni des deux absorbe l'autre. Renvoie (événements, fusions faites)."""
    par_id = {e["id"]: e for e in evenements}
    principaux = {e["id"]: set(pays_principaux(e, det, [r["texte"] for r in (e.get("analyse") or {}).get("resume", [])])) for e in evenements}
    fusions = []

    def absorber(i1: str, i2: str) -> None:
        e1, e2 = par_id.get(i1), par_id.get(i2)
        if not e1 or not e2 or e1 is e2:
            return
        base, autre = (e1, e2) if len(e1["articles"]) >= len(e2["articles"]) else (e2, e1)
        fondre(base, autre)
        principaux[base["id"]] |= principaux.pop(autre["id"], set())
        par_id.pop(autre["id"])
        for k, v in list(par_id.items()):  # les références vers l'absorbé désignent désormais la base
            if v is autre:
                par_id[k] = base
        fusions.append((base["id"], autre["id"]))

    for i1, i2 in paires_imposees:
        absorber(i1, i2)
    change = True
    while change:
        change = False
        liste = sorted({id(e): e for e in par_id.values()}.values(), key=lambda e: e["premier"])
        for i, e1 in enumerate(liste):
            for e2 in liste[i + 1:]:
                if _ecart_heures(e1, e2) > 48:
                    continue
                p1, p2 = principaux.get(e1["id"], set()), principaux.get(e2["id"], set())
                if (p1 or p2) and not p1 & p2:
                    continue
                if titres_proches(e1, e2, e1["categorie"] == e2["categorie"] or (p1 and p1 == p2)):
                    absorber(e1["id"], e2["id"])
                    change = True
                    break
            if change:
                break
    restants = list({id(e): e for e in par_id.values()}.values())
    return [e for e in evenements if any(e is r for r in restants)], fusions


VERSION_REGROUPEMENT = 2


def reconstruire(evenements: list[dict], det: Detecteur, config: dict, maintenant: datetime) -> list[dict]:
    """Changement de méthode de regroupement : les événements sont refaits à partir de leurs articles
    (les analyses sont abandonnées et seront refaites, dans la limite des quotas)."""
    articles, vus = [], set()
    for e in evenements:
        for a in e["articles"]:
            if a["url"] in vus:
                continue
            vus.add(a["url"])
            defaut = "sanctions" if a.get("source") == "OFAC" else "monetaire" if "BRI" in (a.get("source") or "") else None
            p = preparer({**a, "categorie_par_defaut": defaut}, det)
            if p:
                articles.append(p)
    neufs: list[dict] = []
    regrouper(articles, neufs, config, maintenant)
    return neufs


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
    """Gravité sans IA : niveau des repères (gravite.py), plafonné à 3 (une gravité de 4 ou 5 demande
    l'analyse et au moins 2 sources indépendantes)."""
    from .gravite import niveau_regles
    return min(3, niveau_regles(e, config)[0])


def sources_publiques(e: dict, maxi: int = 12) -> list[dict]:
    """Sources affichées : officielles d'abord, puis un article par domaine, du plus récent au plus ancien."""
    tri = sorted(e["articles"], key=lambda a: (not a.get("officiel"), (a.get("date") or "")), reverse=False)
    officielles = [a for a in tri if a.get("officiel")]
    autres = sorted((a for a in e["articles"] if not a.get("officiel")), key=lambda a: a.get("date") or "", reverse=True)
    res, vus = list(officielles), set()
    for a in autres:  # un article par domaine (les reprises d'une même dépêche restent listées, mais ne
        if a["domaine"] not in vus:  # comptent qu'une fois comme sources indépendantes)
            vus.add(a["domaine"])
            res.append(a)
    return [{k: a.get(k) for k in ("titre", "url", "domaine", "date", "officiel", "source")} for a in res[:maxi]]


def article_reference(e: dict) -> dict:
    """Article de référence : source officielle s'il y en a ; sinon l'article le plus repris (même titre
    sur le plus de sites), puis le plus centré sur l'événement. Les galeries photo, directs et pages
    « ce qu'il faut savoir » (config « titres_exclus ») ne sont pas retenus, sauf s'il n'y a qu'eux."""
    officiels = [a for a in e["articles"] if a.get("officiel")]
    if officiels:
        return officiels[0]
    candidats = [a for a in e["articles"] if not format_exclu(a["titre"])] or e["articles"]
    reprises: dict[str, set] = {}
    for a in e["articles"]:
        reprises.setdefault(titre_normalise(a["titre"]), set()).add(a.get("domaine"))
    cles = mots_cles(e)
    majoritaires = set(pays_majoritaires(e))

    def pertinence(a):
        # Mots-clés présents, moins la moitié des mots hors sujet, moins 1 par pays du titre qui n'est pas
        # majoritaire dans l'événement : un titre centré sur l'événement, pas sur un pays seulement cité
        mots = _mots_titre(a["titre"])
        hors = [c for c in (a.get("pays_titre") or []) if c not in majoritaires]
        return len(mots & cles) - 0.5 * len(mots - cles) - len(hors)
    return max(sorted(candidats, key=lambda a: a.get("date") or ""),
               key=lambda a: (len(reprises[titre_normalise(a["titre"])]), pertinence(a)))


def titre_reference(e: dict) -> str:
    return nettoyer_titre(article_reference(e)["titre"])


def langue_reference(e: dict) -> str | None:
    """Langue du titre de référence (code : en, fr…)."""
    return article_reference(e).get("langue")


def nettoyer(evenements: list[dict], maintenant: datetime, garde_jours: int, max_articles: int = 40) -> list[dict]:
    limite = iso(maintenant - timedelta(days=garde_jours))
    res = [e for e in evenements if e["dernier"] >= limite]
    for e in res:
        if len(e["articles"]) > max_articles:  # on garde les officiels et les plus récents
            e["articles"] = sorted(e["articles"], key=lambda a: (bool(a.get("officiel")), a.get("date") or ""), reverse=True)[:max_articles]
    return res
