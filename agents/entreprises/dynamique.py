"""
Dynamique des résultats : guidance de la direction, révisions des analystes, objectifs de cours et
surprises de résultats. Bloc noté sur 100, pris en compte (pondération modérée) dans la note globale
et compté comme un signal de la recommandation. Règles : agents/entreprises/dynamique.md ;
paramètres : section « dynamique » de agents/entreprises/config.json.

1. Guidance (États-Unis seulement)
   - Détection des dépôts 8-K « Item 2.02 Results of Operations » (flux submissions de la SEC) ;
   - communiqué de résultats en pièce jointe (EX-99.1, et EX-99.2 s'il existe) ;
   - passages de prévision repérés par règles (sans IA) ; sans passage, « aucune guidance » sans appel à Gemini ;
   - extraction par Gemini (budget d'appels propre à l'agent entreprises, compté à part des agents
     géopolitique et risque, sans dépasser les quotas gratuits) : indicateur, période, valeur, évolution
     (relevée, maintenue, abaissée, initiée, retirée) ;
   - anti-hallucination : chaque élément cite mot pour mot une phrase du communiqué, retrouvée dans le
     texte téléchargé (lien SEC conservé) ; sans citation retrouvée, l'élément est écarté. Les chiffres
     annoncés doivent figurer dans la citation. Quand une guidance précédente chiffrée existe pour le même
     indicateur et la même période, l'évolution est recalculée à partir des chiffres ;
   - Gemini indisponible (clé absente, quota, panne) : communiqué « non analysé », repris à l'exécution suivante ;
   - historique par société : data/historique/guidance/TICKER.json.
   Hors États-Unis : « guidance non disponible » (pas de source structurée gratuite).

2. Analystes (yfinance, toutes régions quand Yahoo les publie) : tendance des estimations de BPA (actuelle,
   7, 30, 60 et 90 jours) pour le trimestre et l'exercice en cours et suivants, révisions à la hausse et à
   la baisse sur 7 et 30 jours, objectifs de cours (moyen, haut, bas), surprises des 4 derniers trimestres.
   Moins de `analystes_min` analystes : données affichées à titre indicatif, exclues de la note.

Stockage : data/entreprises/dynamique.json (données brutes par société), data/entreprises/etat_dynamique.json
(compteurs du quota Gemini). La note du bloc est calculée à la publication (fonction bloc, pure).
"""
from __future__ import annotations

import html as html_lib
import json
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from ..commun.journal import journal
from ..commun.sortie import ecrire_json, lire_json
from ..pays.textes import nb
from . import analyse as A

LOG = journal("agent-entreprises")

EVOLUTIONS = ("relevée", "maintenue", "abaissée", "initiée", "retirée")
NEGATIVES = ("abaissée", "retirée")
INDICATEURS = {"chiffre_affaires": "Chiffre d'affaires", "bpa": "Bénéfice par action", "marge": "Marge", "autre": "Autre"}
PERIODES = {"0q": "Trimestre en cours", "+1q": "Trimestre suivant", "0y": "Exercice en cours", "+1y": "Exercice suivant"}
# Priorité pour l'évolution d'ensemble d'un communiqué : la plus défavorable l'emporte
PRIORITE_EVOLUTION = ("retirée", "abaissée", "relevée", "initiée", "maintenue")


def maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def date_fr(d: str | None) -> str:
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d and len(d) >= 10 else "date inconnue"


def fichier_ticker(ticker: str) -> str:
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in ticker) + ".json"


# ================================================================== analystes (yfinance)

def _v(x):
    """Valeur brute d'un champ quoteSummary ({"raw": …, "fmt": …} ou nombre)."""
    if isinstance(x, dict):
        x = x.get("raw")
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _date_trimestre(q) -> str | None:
    if isinstance(q, dict):
        if q.get("fmt"):
            return str(q["fmt"])[:10]
        q = q.get("raw")
    if isinstance(q, (int, float)):
        return datetime.fromtimestamp(q, timezone.utc).date().isoformat()
    return str(q)[:10] if q else None


def lire_analystes(brut: dict | None) -> dict | None:
    """Résultat quoteSummary (modules earningsTrend, earningsHistory, financialData) → données normalisées."""
    if not brut:
        return None
    est = {}
    nb_max = 0
    for t in (brut.get("earningsTrend") or {}).get("trend") or []:
        p = t.get("period")
        if p not in PERIODES:
            continue
        tr = t.get("epsTrend") or {}
        rv = t.get("epsRevisions") or {}
        ee = t.get("earningsEstimate") or {}
        n = _v(ee.get("numberOfAnalysts"))
        nb_max = max(nb_max, int(n or 0))
        bpa = {k: _v(tr.get(src)) for k, src in (("actuel", "current"), ("7j", "7daysAgo"), ("30j", "30daysAgo"),
                                                  ("60j", "60daysAgo"), ("90j", "90daysAgo"))}
        if all(v is None for v in bpa.values()):
            continue
        est[p] = {"fin": t.get("endDate"), "bpa": bpa, "analystes": int(n) if n is not None else None,
                  "devise": tr.get("epsTrendCurrency") or ee.get("earningsCurrency"),
                  "revisions": {k: (int(_v(rv.get(src))) if _v(rv.get(src)) is not None else None)
                                for k, src in (("hausse_7j", "upLast7days"), ("hausse_30j", "upLast30days"),
                                               ("baisse_7j", "downLast7Days"), ("baisse_30j", "downLast30days"))}}
    surprises = []
    for h in (brut.get("earningsHistory") or {}).get("history") or []:
        pub, est_q = _v(h.get("epsActual")), _v(h.get("epsEstimate"))
        sp = _v(h.get("surprisePercent"))
        if pub is None or est_q is None:
            continue
        if sp is None and est_q:
            sp = (pub - est_q) / abs(est_q)
        surprises.append({"trimestre": _date_trimestre(h.get("quarter")), "publie": round(pub, 4), "estime": round(est_q, 4),
                          "surprise_pct": round(sp * 100, 1) if sp is not None else None})
    surprises = sorted((s for s in surprises if s["trimestre"]), key=lambda s: s["trimestre"])[-4:]
    fd = brut.get("financialData") or {}
    cours, moyen = _v(fd.get("currentPrice")), _v(fd.get("targetMeanPrice"))
    n_obj = _v(fd.get("numberOfAnalystOpinions"))
    objectifs = None
    if moyen:
        objectifs = {"moyen": round(moyen, 4), "haut": _v(fd.get("targetHighPrice")), "bas": _v(fd.get("targetLowPrice")),
                     "median": _v(fd.get("targetMedianPrice")), "cours": cours,
                     "ecart_pct": round((moyen / cours - 1) * 100, 1) if cours else None,
                     "analystes": int(n_obj) if n_obj is not None else None}
    analystes = max(nb_max, int(n_obj or 0)) or None
    if not est and not surprises and not objectifs:
        return None
    return {"estimations": est, "surprises": surprises, "objectifs": objectifs, "analystes": analystes}


def variation_pct(actuel, ancien) -> float | None:
    if actuel is None or ancien is None or abs(ancien) < 0.01:
        return None
    return (actuel - ancien) / abs(ancien) * 100


def revisions(an: dict | None) -> dict:
    """Évolution des estimations de BPA des exercices en cours et suivant (moyenne des deux), sur 30 et 90 jours."""
    res = {"30j_pct": None, "90j_pct": None, "hausse_30j": None, "baisse_30j": None, "hausse_7j": None, "baisse_7j": None}
    est = (an or {}).get("estimations") or {}
    for cle, src in (("30j_pct", "30j"), ("90j_pct", "90j")):
        v = [variation_pct(est[p]["bpa"].get("actuel"), est[p]["bpa"].get(src)) for p in ("0y", "+1y") if p in est]
        v = [x for x in v if x is not None]
        res[cle] = round(sum(v) / len(v), 1) if v else None
    for k in ("hausse_30j", "baisse_30j", "hausse_7j", "baisse_7j"):
        v = [est[p]["revisions"].get(k) for p in ("0y", "+1y") if p in est and est[p]["revisions"].get(k) is not None]
        res[k] = sum(v) if v else None
    return res


# ================================================================== communiqués (texte, passages, validation)

class _Texte(HTMLParser):
    BLOCS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.morceaux, self._ignorer = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "title"):
            self._ignorer += 1
        elif tag in self.BLOCS:
            self.morceaux.append("\n")
        elif tag in ("td", "th"):
            self.morceaux.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title"):
            self._ignorer = max(0, self._ignorer - 1)
        elif tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, data):
        if not self._ignorer:
            self.morceaux.append(data)


def html_en_texte(h: str) -> str:
    """Communiqué HTML → texte, une ligne par paragraphe ou ligne de tableau."""
    p = _Texte()
    try:
        p.feed(h)
        p.close()
        brut = "".join(p.morceaux)
    except Exception:  # HTML très mal formé : balises retirées grossièrement
        brut = re.sub(r"<[^>]+>", "\n", h)
    brut = html_lib.unescape(brut).replace("\xa0", " ")
    lignes = []
    for l in brut.split("\n"):
        l = re.sub(r"[ \t\r\f\v]+", " ", l).strip(" |")
        l = re.sub(r"(\s*\|\s*)+", " | ", l).strip()
        if l and not re.fullmatch(r"[|\s$%()—–-]*", l):
            lignes.append(l)
    return "\n".join(lignes)


def normaliser(t: str) -> str:
    """Comparaison tolérante des citations : casse, espaces, apostrophes, guillemets et tirets unifiés."""
    t = unicodedata.normalize("NFKC", t or "")
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    t = t.replace("|", " ")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\$ (?=\d)", "$", t)
    t = re.sub(r"(?<=\d) %", "%", t)
    t = re.sub(r"\( ", "(", re.sub(r" \)", ")", t))
    return t.strip().lower()


TITRE_PREVISION = re.compile(r"\b(outlook|guidance|forecast)\b", re.I)
MOTS_PREVISION = re.compile(
    r"\b(outlook|guidance|guides?|guided|reaffirm\w*|reiterat\w*|withdr[ae]w\w*|suspend\w*|narrow\w*|"
    r"expects?|expected to|anticipates?|projected to|forecasts?|"
    r"rais(e|es|ed|ing) (its |the |our )?(full[- ]year|annual|fiscal|\d{4}|outlook|guidance)|"
    r"lower(s|ed|ing)? (its |the |our )?(full[- ]year|annual|fiscal|\d{4}|outlook|guidance))\b", re.I)
MOTS_FORTS = re.compile(r"\b(outlook|guidance|guides?|reaffirm\w*|reiterat\w*|withdr[ae]w\w*|expects?|anticipates?|forecasts?)\b", re.I)
BOILERPLATE = re.compile(r"forward[- ]looking|safe harbor|private securities litigation|risks and uncertainties|undue reliance|"
                         r"webcast|conference call|non-gaap financial measures? (are|is) (not|in addition)|"
                         r"actual results (may|could) differ|we undertake no|assumes no obligation", re.I)
LIGNES_SECTION = 15  # lignes reprises après un titre « Outlook » / « Guidance »


def extraire_passages(textes: list[tuple[str, str]], caracteres_max: int) -> list[dict]:
    """Passages de prévision des communiqués, par priorité : 1) section qui suit un titre « Outlook »/« Guidance »
    (tableaux compris) ; 2) phrases au futur ou de guidance (expects, reaffirms, raises its outlook…), avec la ligne
    suivante quand la phrase est coupée. Lignes juridiques écartées. Ordre du communiqué conservé, dans la limite
    de caracteres_max. Vide si aucun passage ne contient de mot de prévision (pas d'appel à Gemini)."""
    candidats = []  # (priorité, n° de pièce, n° de ligne, texte, url)
    for k, (url, texte) in enumerate(textes):
        lignes = texte.split("\n")
        suite = 0
        for n, l in enumerate(lignes):
            juridique = bool(BOILERPLATE.search(l))
            titre = len(l) < 80 and TITRE_PREVISION.search(l) and not juridique
            if titre:
                candidats.append((0, k, n, l, url))
                suite = LIGNES_SECTION
                continue
            if suite > 0 and not juridique:
                candidats.append((1, k, n, l, url))
            elif len(l) >= 25 and not juridique and MOTS_PREVISION.search(l):
                candidats.append((2, k, n, l, url))
                if n + 1 < len(lignes) and not re.search(r"[.!?:;”\"]$", l) and not BOILERPLATE.search(lignes[n + 1]):
                    candidats.append((2, k, n + 1, lignes[n + 1], url))  # phrase coupée sur deux lignes
            suite = max(0, suite - 1)
    if not any(MOTS_FORTS.search(c[3]) for c in candidats):
        return []
    choisis, total, vus = [], 0, set()
    for c in sorted(candidats, key=lambda c: (c[0], c[1], c[2])):
        cle = (c[1], c[2])
        if cle in vus or c[3] in {x[3] for x in choisis}:
            continue
        if total + min(len(c[3]), 1500) > caracteres_max:
            continue
        vus.add(cle)
        choisis.append(c)
        total += min(len(c[3]), 1500)
    choisis.sort(key=lambda c: (c[1], c[2]))
    return [{"id": f"P{i}", "texte": c[3][:1500], "url": c[4]} for i, c in enumerate(choisis, 1)]


def _nombres(texte: str) -> set[float]:
    """Nombres d'un texte (anglais : 1,250.5 ; français : 1 250,5 ou 10,2)."""
    res = set()
    t = re.sub(r"(?<=\d)[  ](?=\d{3}\b)", "", texte or "")
    for n in re.findall(r"\d[\d,.]*", t):
        n = n.rstrip(".,")
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", n):  # séparateur de milliers anglais
            n = n.replace(",", "")
        elif "," in n and "." not in n:  # virgule décimale française
            n = n.replace(",", ".")
        else:
            n = n.replace(",", "")
        try:
            res.add(round(float(n), 6))
        except ValueError:
            continue
    return res


def citation_retrouvee(citation: str, textes: list[tuple[str, str]]) -> str | None:
    """URL de la pièce qui contient la citation (fragments séparés par des points de suspension acceptés, dans l'ordre)."""
    fragments = [normaliser(f) for f in re.split(r"\.\.\.|…", citation or "")]
    fragments = [f for f in fragments if f]
    if not fragments or sum(len(f) for f in fragments) < 20 or any(len(f) < 8 for f in fragments):
        return None
    for url, texte in textes:
        t, pos = normaliser(texte), 0
        for f in fragments:
            i = t.find(f, pos)
            if i < 0:
                break
            pos = i + len(f)
        else:
            return url
    return None


def cle_periode(p: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", normaliser(p or ""))


def comparer_chiffres(nouvelle: dict, ancienne: dict, seuil_pct: float) -> str | None:
    """Évolution recalculée à partir des fourchettes (même indicateur, période et unité), ou None."""
    def milieu(g):
        v = [x for x in (g.get("bas"), g.get("haut")) if isinstance(x, (int, float))]
        return sum(v) / len(v) if v else None
    a, b = milieu(nouvelle), milieu(ancienne)
    if a is None or b is None or b == 0 or (nouvelle.get("unite") or "") != (ancienne.get("unite") or ""):
        return None
    e = (a - b) / abs(b) * 100
    return "relevée" if e > seuil_pct else "abaissée" if e < -seuil_pct else "maintenue"


def valider_guidances(brut, textes: list[tuple[str, str]], precedentes: list[dict], cfg: dict) -> tuple[list[dict], list[str]]:
    """Garde les éléments dont la citation est retrouvée mot pour mot et dont les chiffres figurent dans la citation."""
    gardes, rejets = [], []
    liste = brut.get("guidances") if isinstance(brut, dict) else None
    if not isinstance(liste, list):
        return [], ["format de réponse inattendu"]
    par_cle = {(g["indicateur"], cle_periode(g.get("periode"))): g for g in precedentes}
    for x in liste[:12]:
        if not isinstance(x, dict):
            continue
        ind, ev, cit = x.get("indicateur"), x.get("evolution"), (x.get("citation") or "").strip()
        nom = x.get("libelle") or ind
        if ind not in INDICATEURS or ev not in EVOLUTIONS:
            rejets.append(f"{nom} : indicateur ou évolution inconnus")
            continue
        url = citation_retrouvee(cit, textes)
        if not url:
            rejets.append(f"{nom} : citation introuvable dans le communiqué")
            continue
        chiffres_cit = _nombres(cit)
        valeur = str(x.get("valeur") or "").strip()
        bas, haut = (x.get(k) if isinstance(x.get(k), (int, float)) and not isinstance(x.get(k), bool) else None for k in ("bas", "haut"))
        hors = [n for n in _nombres(valeur) | {v for v in (bas, haut) if v is not None} if round(abs(float(n)), 6) not in chiffres_cit]  # signe porté par les mots (decline…)
        if hors:
            rejets.append(f"{nom} : chiffres absents de la citation ({', '.join(nb(h, 2) for h in sorted(hors)[:3])})")
            continue
        g = {"indicateur": ind, "libelle": str(x.get("libelle") or INDICATEURS[ind])[:80], "periode": str(x.get("periode") or "")[:60],
             "valeur": valeur[:120], "bas": bas, "haut": haut, "unite": str(x.get("unite") or "")[:20] or None,
             "evolution": ev, "citation": cit[:600], "url": url}
        p = par_cle.get((ind, cle_periode(g["periode"])))
        if p and ev != "retirée":
            calc = comparer_chiffres(g, p, cfg["seuil_evolution_pct"])
            if calc and calc != ev:
                g["evolution_gemini"], g["evolution"] = ev, calc
            g["precedente"] = {"valeur": p.get("valeur"), "date": p.get("date")}
        gardes.append(g)
    return gardes, rejets


def evolution_ensemble(guidances: list[dict]) -> str | None:
    """Évolution d'un communiqué : chiffre d'affaires et BPA en priorité ; la plus défavorable l'emporte."""
    principales = [g for g in guidances if g["indicateur"] in ("chiffre_affaires", "bpa")] or guidances
    evs = {g["evolution"] for g in principales}
    return next((e for e in PRIORITE_EVOLUTION if e in evs), None)


def consigne(nom: str, ticker: str, passages: list[dict], precedentes: list[dict]) -> str:
    prec = [{k: g.get(k) for k in ("indicateur", "periode", "valeur", "date")} for g in precedentes] or "aucune connue"
    return (
        f"Tu analyses le communiqué de résultats de {nom} ({ticker}), déposé à la SEC (extraits numérotés ci-dessous, en anglais). "
        "Relève UNIQUEMENT la guidance : les prévisions chiffrées ou qualitatives de la direction pour une période en cours ou "
        "future (chiffre d'affaires, bénéfice par action, marge, autre indicateur comme le flux de trésorerie ou les ventes "
        "comparables). Les résultats passés, les objectifs d'analystes et les phrases juridiques ne sont pas de la guidance. "
        "Règle absolue : chaque élément recopie MOT POUR MOT, en anglais et sans rien changer, la phrase ou la ligne du "
        "communiqué qui l'énonce (\"citation\"). Sans phrase à citer, n'inclus pas l'élément. N'invente aucun chiffre : "
        "\"valeur\", \"bas\" et \"haut\" reprennent les nombres tels qu'écrits dans la citation (ex. « 10.2 to 10.4 billion » : "
        "bas 10.2, haut 10.4, unite \"Md$\"). "
        "Évolution par rapport à la guidance précédente (liste ci-dessous si connue) : « relevée », « maintenue », « abaissée », "
        "« initiée » (première guidance pour cet indicateur et cette période) ou « retirée » (guidance retirée ou suspendue). "
        "Si le communiqué emploie raise, reaffirm, reiterate, lower, withdraw, suis-le. "
        "libelle et periode en français (ex. « exercice 2026 », « T4 2026 »).\n"
        "Réponds uniquement en JSON : {\"guidances\": [{\"indicateur\": \"chiffre_affaires|bpa|marge|autre\", \"libelle\": \"…\", "
        "\"periode\": \"…\", \"valeur\": \"…\", \"bas\": 0.0, \"haut\": 0.0, \"unite\": \"Md$|M$|$|%|autre\", "
        "\"evolution\": \"relevée|maintenue|abaissée|initiée|retirée\", \"citation\": \"…\", \"passage\": \"P1\"}]} ; "
        "{\"guidances\": []} s'il n'y a pas de guidance.\n"
        f"Guidance précédente : {json.dumps(prec, ensure_ascii=False)}\n"
        "Extraits : " + json.dumps([{"id": p["id"], "texte": p["texte"]} for p in passages], ensure_ascii=False)
    )


# ================================================================== historique de guidance

def lire_historique(dossier: Path, ticker: str) -> dict:
    h = (lire_json(dossier / fichier_ticker(ticker)) or {}).get("donnees")
    return h or {"ticker": ticker, "communiques": []}


def ecrire_historique(dossier: Path, h: dict, maxi: int) -> None:
    h["communiques"] = sorted(h["communiques"], key=lambda c: (c.get("date") or "", c.get("accession") or ""), reverse=True)[:maxi]
    ecrire_json(dossier / fichier_ticker(h["ticker"]), {"meta": {"genere_le": maintenant(), "source": "agent-entreprises",
                                                                  "description": "Guidances extraites des communiqués de résultats (8-K Item 2.02, SEC)"},
                                                         "donnees": h})


def precedentes(h: dict, avant: str | None) -> list[dict]:
    """Guidances du communiqué analysé le plus récent avant la date `avant`."""
    for c in sorted(h["communiques"], key=lambda c: c.get("date") or "", reverse=True):
        if c.get("statut") == "analysée" and (avant is None or (c.get("date") or "") < avant) and c.get("guidances"):
            return [{**g, "date": c["date"]} for g in c["guidances"]]
    return []


def resume_guidance(h: dict | None, pays: str, sec_actif: bool = True) -> dict:
    """Résumé stocké dans dynamique.json : dernier communiqué (tout statut) et dernière guidance retenue."""
    if pays != "US":
        return {"statut": "non disponible", "raison": "pas de source structurée gratuite hors États-Unis"}
    comm = sorted((h or {}).get("communiques") or [], key=lambda c: c.get("date") or "", reverse=True)
    if not comm:
        return {"statut": "non analysée", "raison": "secret SEC_USER_AGENT absent" if not sec_actif
                else "aucun communiqué de résultats (8-K Item 2.02) récent détecté"}
    d = comm[0]
    r = next((c for c in comm if c.get("statut") == "analysée" and c.get("guidances")), None)
    champs = ("date", "accession", "statut", "raison", "evolution", "url_depot", "url_communique", "guidances", "modele", "periode_resultats")
    return {"statut": d.get("statut"), "dernier": {k: d.get(k) for k in champs if d.get(k) is not None},
            "retenue": {k: r.get(k) for k in champs if r.get(k) is not None} if r else None}


# ================================================================== collecte (réseau)

def analyser_communique(sec, depot: dict, nom: str, ticker: str, h: dict, cfg: dict, quotas, cle: str | None,
                        poster, rapport: dict) -> dict:
    """Analyse un dépôt 8-K Item 2.02 ; renvoie l'entrée d'historique (statut « analysée », « aucune guidance »
    ou « non analysée »)."""
    from ..geopolitique import ia
    c = {"date": depot["date"], "accession": depot["accession"], "url_depot": depot["url_depot"],
         "periode_resultats": depot.get("periode"), "analyse_le": maintenant()}
    try:
        pieces = sec.pieces_jointes(depot)
    except Exception as e:
        return {**c, "statut": "non analysée", "raison": f"index du dépôt illisible ({str(e)[:80]})"}
    ex = [p for p in pieces if p["type"].upper().startswith("EX-99")]
    ex.sort(key=lambda p: (p["type"].upper() != "EX-99.1", p["type"]))
    if not ex:
        return {**c, "statut": "aucune guidance", "raison": "pas de communiqué en pièce jointe (EX-99)"}
    textes = []
    for p in ex[:cfg["sec"]["pieces_max"]]:
        try:
            textes.append((p["url"], html_en_texte(sec.document(p["url"]))))
        except Exception as e:
            LOG.warning("%s : pièce %s illisible (%s)", ticker, p["url"], str(e)[:80])
    if not textes:
        return {**c, "statut": "non analysée", "raison": "communiqué illisible"}
    c["url_communique"] = textes[0][0]
    passages = extraire_passages(textes, cfg["sec"]["caracteres_max"])
    if not passages:
        return {**c, "statut": "aucune guidance", "raison": "aucun passage de prévision dans le communiqué"}
    if not cle:
        return {**c, "statut": "non analysée", "raison": "secret GEMINI_API_KEY absent"}
    prec = precedentes(h, depot["date"])
    texte, modele = ia.appel_chaine(consigne(nom, ticker, passages, prec), quotas, cfg["gemini"], cle, poster, rapport)
    if texte is None:
        return {**c, "statut": "non analysée", "raison": "Gemini indisponible ou budget du jour atteint"}
    try:
        brut = json.loads(texte)
    except ValueError:
        rapport["rejets"].append(f"{ticker} : réponse JSON illisible")
        return {**c, "statut": "non analysée", "raison": "réponse de Gemini illisible", "modele": modele}
    gardes, rejets = valider_guidances(brut, textes, prec, cfg)
    rapport["rejets"] += [f"{ticker} : {r}" for r in rejets]
    rapport["reussites"] += 1
    if not gardes:
        return {**c, "statut": "aucune guidance", "modele": modele, "rejets": rejets[:6],
                "raison": "aucune prévision citée dans le communiqué" if not rejets else "aucune citation retrouvée mot pour mot : rien n'est retenu"}
    return {**c, "statut": "analysée", "modele": modele, "guidances": gardes, "evolution": evolution_ensemble(gardes), "rejets": rejets[:6]}


def collecter_guidance(f, base: dict, soc: dict, cfg: dict, data: Path, aujourdhui: date, cle: str | None, etat: dict,
                       poster=None, horloge=None, dormir=None) -> dict:
    from ..geopolitique import ia
    dossier = data / "historique" / "guidance"
    sec = getattr(f, "sec", None)
    sec_actif = bool(getattr(sec, "actif", False)) and hasattr(sec, "resultats_8k")
    rapport = {"cle": bool(cle), "sec": sec_actif, "appels": 0, "reussites": 0, "rejets": [], "erreurs": [], "quota_atteint": False,
               "detectes": 0, "analyses": 0, "aucune": 0, "en_attente": 0}
    historiques = {}
    a_traiter = []
    for t, r in base.items():
        if r.get("pays") != "US":
            continue
        h = historiques[t] = lire_historique(dossier, t)
        cik = (r.get("ids") or {}).get("cik")
        if not sec_actif or not cik:
            continue
        try:
            depots = sec.resultats_8k(cik, cfg["sec"]["fenetre_jours"], aujourdhui)[:cfg["sec"]["communiques_par_societe"]]
        except Exception as e:
            rapport["erreurs"].append(f"{t} : {str(e)[:80]}")
            continue
        connus = {c["accession"]: c for c in h["communiques"]}
        for d in depots:
            c = connus.get(d["accession"])
            if c is None or (c.get("statut") == "non analysée" and c.get("tentatives", 0) < cfg["sec"]["tentatives_max"]):
                a_traiter.append((d["date"], t, d))
    a_traiter.sort(key=lambda x: (x[0], x[1]), reverse=True)
    rapport["detectes"] = len(a_traiter)
    quotas = ia.Quotas(etat, cfg["gemini"], horloge=horloge, dormir=dormir or time.sleep)
    modifies = set()
    for k, (_, t, d) in enumerate(a_traiter):
        h = historiques[t]
        ancien = next((c for c in h["communiques"] if c["accession"] == d["accession"]), None)
        if k >= cfg["sec"]["communiques_max_par_execution"]:
            c = {"date": d["date"], "accession": d["accession"], "url_depot": d["url_depot"], "periode_resultats": d.get("periode"),
                 "statut": "non analysée", "raison": "en file d'attente (plafond de communiqués par exécution)"}
        else:
            c = analyser_communique(sec, d, base[t].get("nom") or t, t, h, cfg, quotas, cle, poster, rapport)
        if c["statut"] == "non analysée":
            c["tentatives"] = (ancien or {}).get("tentatives", 0) + (0 if "file d'attente" in c.get("raison", "") else 1)
            rapport["en_attente"] += 1
        else:
            rapport["analyses" if c["statut"] == "analysée" else "aucune"] += 1
        h["communiques"] = [x for x in h["communiques"] if x["accession"] != d["accession"]] + [c]
        modifies.add(t)
    for t in modifies:
        ecrire_historique(dossier, historiques[t], cfg["sec"]["historique_max"])
    for t, r in base.items():
        soc.setdefault(t, {})["guidance"] = resume_guidance(historiques.get(t), r.get("pays"), sec_actif)
    rapport["quota"] = quotas.resume()
    return rapport


def collecter_analystes(yahoo, tickers: list[str], soc: dict, cfg: dict, aujourdhui: date) -> dict:
    ok, echecs = 0, []
    if not hasattr(yahoo, "analystes"):
        return {"ok": 0, "echecs": 0, "absent": True}
    # Les données d'analystes les plus anciennes d'abord : avec un univers plus grand que le plafond par exécution,
    # chaque société est rafraîchie à tour de rôle
    tickers = sorted(tickers, key=lambda t: ((soc.get(t) or {}).get("analystes") or {}).get("maj") or "")
    for k, t in enumerate(tickers[:cfg["yahoo"]["societes_max_par_execution"]], 1):
        try:
            a = lire_analystes(yahoo.analystes(t))
            entree = soc.setdefault(t, {})
            if a:
                entree["analystes"] = {**a, "maj": aujourdhui.isoformat()}
            else:
                # Réponse vide : erreur passagère (crumb refusé…) ou société sans couverture. La dernière donnée
                # est gardée une semaine, puis retirée.
                ancienne = (entree.get("analystes") or {}).get("maj")
                if not ancienne or (aujourdhui - date.fromisoformat(ancienne)).days > cfg["yahoo"]["conservation_jours"]:
                    entree.pop("analystes", None)
            ok += 1
        except Exception as e:  # dernière donnée connue conservée (date de mise à jour inchangée)
            echecs.append(f"{t} : {str(e)[:80]}")
        if k % 200 == 0:
            LOG.info("Analystes : %d / %d sociétés", k, len(tickers))
        if cfg["yahoo"]["pause_secondes"] and hasattr(yahoo, "yf"):  # vraie source Yahoo seulement
            time.sleep(cfg["yahoo"]["pause_secondes"])
    return {"ok": ok, "echecs": len(echecs), "exemples_echecs": echecs[:10]}


def executer(f, base: dict, config: dict, data: Path, aujourdhui: date, cle_gemini: str | None,
             poster=None, horloge=None, dormir=None) -> dict:
    """Met à jour data/entreprises/dynamique.json (analystes de toutes les sociétés, guidance des sociétés américaines)."""
    cfg = config["dynamique"]
    chemin = data / "entreprises" / "dynamique.json"
    chemin_etat = data / "entreprises" / "etat_dynamique.json"
    soc = (lire_json(chemin) or {}).get("societes") or {}
    soc = {t: v for t, v in soc.items() if t in base}  # sociétés sorties de l'univers
    etat = lire_json(chemin_etat) or {}
    analystes = collecter_analystes(f.yahoo, list(base), soc, cfg, aujourdhui)
    guidance = collecter_guidance(f, base, soc, cfg, data, aujourdhui, cle_gemini, etat, poster, horloge, dormir)
    etat["derniere_execution"] = maintenant()
    ecrire_json(chemin_etat, etat)
    ecrire_json(chemin, {"meta": {"genere_le": maintenant(), "source": "agent-entreprises",
                                  "description": "Guidance (8-K Item 2.02, SEC + Gemini) et données des analystes (Yahoo Finance) par société"},
                         "societes": soc}, compact=True)
    LOG.info("Dynamique des résultats : analystes %d ok / %d échecs ; guidance : %d communiqué(s) détecté(s), %d analysé(s), "
             "%d sans guidance, %d en attente ; %d appel(s) Gemini", analystes["ok"], analystes["echecs"], guidance["detectes"],
             guidance["analyses"], guidance["aucune"], guidance["en_attente"], guidance["appels"])
    return {"analystes": analystes, "guidance": {k: v for k, v in guidance.items() if k != "rejets"} | {"rejets": guidance["rejets"][:20]}}


def lire_stock(data: Path) -> dict:
    return (lire_json(Path(data) / "entreprises" / "dynamique.json") or {}).get("societes") or {}


# ================================================================== note du bloc (fonction pure)

def _age(d: str | None, aujourdhui: date) -> int | None:
    try:
        return (aujourdhui - date.fromisoformat(d[:10])).days
    except (TypeError, ValueError):
        return None


def bloc(donnees: dict | None, pays: str, cfg: dict, aujourdhui: date) -> dict:
    """Bloc « Dynamique des résultats » : note /100, sens du signal, textes, données affichées."""
    donnees = donnees or {}
    an = donnees.get("analystes")
    g = donnees.get("guidance") or resume_guidance(None, pays)
    n_an = (an or {}).get("analystes")
    fiable = bool(n_an and n_an >= cfg["analystes_min"])
    rev = revisions(an)
    comp = []
    # Guidance retenue (récente)
    retenue = g.get("retenue")
    age_g = _age((retenue or {}).get("date"), aujourdhui)
    guidance_negative = None
    if retenue and retenue.get("evolution") and age_g is not None and age_g <= cfg["guidance_validite_jours"]:
        ev = retenue["evolution"]
        comp.append({"cle": "guidance", "libelle": "Guidance", "note": cfg["scores_guidance"][ev],
                     "texte": f"guidance {ev} le {date_fr(retenue['date'])}"})
        if ev in NEGATIVES and age_g <= cfg["guidance_negative_jours"]:
            guidance_negative = {"evolution": ev, "date": retenue["date"], "jours": age_g}
    # Révisions et surprises : seulement si au moins `analystes_min` analystes
    if fiable:
        if rev["30j_pct"] is not None:
            comp.append({"cle": "revisions_30j", "libelle": "Révisions sur 30 jours", "note": A.lin(rev["30j_pct"], cfg["bareme_revisions_30j"]),
                         "texte": f"estimations de BPA {nb(rev['30j_pct'], 1, signe=True)} % sur 30 jours"})
        if rev["90j_pct"] is not None:
            comp.append({"cle": "revisions_90j", "libelle": "Révisions sur 90 jours", "note": A.lin(rev["90j_pct"], cfg["bareme_revisions_90j"]),
                         "texte": f"{nb(rev['90j_pct'], 1, signe=True)} % sur 90 jours"})
        sp = [s["surprise_pct"] for s in (an or {}).get("surprises") or [] if s.get("surprise_pct") is not None]
        if len(sp) >= 2:
            moy = sum(max(-50.0, min(50.0, x)) for x in sp) / len(sp)
            au_dessus = sum(1 for x in sp if x > 0)
            comp.append({"cle": "surprises", "libelle": "Surprises de résultats", "note": A.lin(moy, cfg["bareme_surprises"]),
                         "texte": f"BPA publié au-dessus de l'estimation sur {au_dessus} des {len(sp)} derniers trimestres (écart moyen {nb(moy, 1, signe=True)} %)"})
    poids = cfg["poids"]
    note = None
    if comp:
        tot = sum(poids[c["cle"]] for c in comp)
        note = round(sum(c["note"] * poids[c["cle"]] for c in comp) / tot)
    sens = 0 if note is None else 1 if note >= cfg["signal_positif"] else -1 if note < cfg["signal_negatif"] else 0
    # Confiance du bloc
    if note is None:
        conf = "faible"
    elif fiable and len(comp) >= 3 and (pays != "US" or retenue):
        conf = "élevé" if pays == "US" else "moyen"
    elif fiable and len(comp) >= 2:
        conf = "moyen"
    else:
        conf = "faible"
    # Textes
    if note is None:
        texte = "non disponible" + ("" if an else " (pas de données d'analystes)") + (" ; analystes peu nombreux : données indicatives" if an and not fiable else "")
    else:
        texte = f"{note}/100 : " + " ; ".join(c["texte"] for c in comp)
    contre = []
    if guidance_negative:
        contre.append("Une guidance abaissée peut être prudente ; le cours a pu intégrer la baisse avant la publication.")
    elif retenue and retenue.get("evolution") == "relevée":
        contre.append("La guidance est une prévision de la direction, révisable à tout moment ; un relèvement peut déjà être intégré dans le cours.")
    if rev["30j_pct"] is not None and fiable and abs(rev["30j_pct"]) >= 3:
        contre.append("Les révisions des analystes suivent souvent la guidance et le cours ; elles peuvent s'inverser au trimestre suivant.")
    if any(c["cle"] == "surprises" and c["note"] >= 60 for c in comp):
        contre.append("Des résultats régulièrement supérieurs aux estimations peuvent traduire des estimations prudentes plutôt qu'une accélération.")
    if an and not fiable:
        contre.append(f"Moins de {cfg['analystes_min']} analystes : estimations peu représentatives, affichées à titre indicatif.")
    if pays != "US":
        contre.append("Guidance non disponible hors États-Unis : le bloc repose sur les seules estimations des analystes.")
    elif g.get("statut") == "non analysée":
        contre.append("Dernier communiqué de résultats non encore analysé : la guidance la plus récente peut manquer.")
    return {"note": note, "sens": sens, "confiance": conf, "fiabilite": "normale" if fiable else "indicative",
            "texte": texte, "composantes": comp, "contre": contre[:3], "guidance": g, "guidance_negative": guidance_negative,
            "estimations": (an or {}).get("estimations") or {}, "revisions": rev, "objectifs": (an or {}).get("objectifs"),
            "surprises": (an or {}).get("surprises") or [], "analystes": n_an, "maj_analystes": (an or {}).get("maj")}


def badge_guidance(b: dict | None, cfg: dict, aujourdhui: date) -> dict | None:
    """Badge de l'écran Pépites : guidance relevée, abaissée ou retirée il y a moins de `badge_jours` jours."""
    r = ((b or {}).get("guidance") or {}).get("retenue")
    if not r or r.get("evolution") not in ("relevée", "abaissée", "retirée"):
        return None
    age = _age(r.get("date"), aujourdhui)
    if age is None or age > cfg["badge_jours"]:
        return None
    return {"evolution": r["evolution"], "date": r["date"]}


def signaux(e: dict, p: dict | None, cfg: dict, aujourdhui: date, source: str) -> list[dict]:
    """Signaux pour le chef d'orchestre : guidance relevée ou abaissée, forte révision des estimations, grosse surprise.
    Seulement par rapport à une publication précédente qui avait déjà ce bloc (pas d'avalanche au premier passage),
    et pour une guidance publiée depuis moins de `signaux.guidance_recente_jours` jours (rattrapage d'anciens communiqués)."""
    res = []
    b, pb = e.get("dynamique") or {}, (p or {}).get("dynamique")
    if not pb:
        return res
    jour = aujourdhui.isoformat()
    r = (b.get("guidance") or {}).get("retenue") or {}
    pr = (pb.get("guidance") or {}).get("retenue") or {}
    s = cfg["signaux"]
    age = _age(r.get("date"), aujourdhui)
    if (r.get("accession") and r.get("accession") != pr.get("accession") and r.get("evolution") in ("relevée", "abaissée", "retirée")
            and age is not None and age <= s["guidance_recente_jours"]):
        cit = next((g for g in r.get("guidances") or [] if g["evolution"] == r["evolution"]), None)
        res.append({"date": jour, "type": "guidance_relevee" if r["evolution"] == "relevée" else "guidance_abaissee", "cle": e["ticker"],
                    "importance": "moyenne", "titre": f"{e['nom']} : guidance {r['evolution']} ({date_fr(r.get('date'))})",
                    "explication": (f"{cit['libelle']} {cit['periode']} : {cit['valeur']}. Citation : « {cit['citation'][:240]} »" if cit else
                                    "Communiqué de résultats déposé à la SEC."),
                    "source": r.get("url_communique") or r.get("url_depot") or source})
    v, pv = (b.get("revisions") or {}).get("30j_pct"), (pb.get("revisions") or {}).get("30j_pct")
    if b.get("fiabilite") == "normale" and v is not None and abs(v) >= s["forte_revision_pct"] and (pv is None or abs(pv) < s["forte_revision_pct"]):
        res.append({"date": jour, "type": "forte_revision", "cle": e["ticker"], "importance": "faible",
                    "titre": f"{e['nom']} : estimations de BPA {nb(v, 1, signe=True)} % sur 30 jours",
                    "explication": f"Moyenne des exercices en cours et suivant, {b.get('analystes')} analystes (Yahoo Finance).",
                    "source": "Yahoo Finance (estimations des analystes)"})
    sp = (b.get("surprises") or [])[-1:] or [None]
    psp = (pb.get("surprises") or [])[-1:] or [None]
    x, px = sp[0], psp[0]
    if (x and x.get("surprise_pct") is not None and abs(x["surprise_pct"]) >= s["grosse_surprise_pct"]
            and b.get("fiabilite") == "normale" and (not px or px.get("trimestre") != x.get("trimestre"))):
        res.append({"date": jour, "type": "grosse_surprise", "cle": e["ticker"], "importance": "faible",
                    "titre": f"{e['nom']} : BPA publié {nb(x['surprise_pct'], 1, signe=True)} % par rapport à l'estimation",
                    "explication": f"Trimestre clos le {date_fr(x['trimestre'])} : {nb(x['publie'], 2)} publié contre {nb(x['estime'], 2)} estimé.",
                    "source": "Yahoo Finance (surprises de résultats)"})
    return res


def donnees_demande(yahoo, ticker: str, pays: str, data: Path, aujourdhui: date) -> dict:
    """Analyse à la demande : données des analystes lues en direct (Yahoo) ; guidance reprise de l'agent entreprises
    (dynamique.json ou historique) quand la société est suivie, sinon « non analysée »."""
    d = dict(lire_stock(data).get(ticker) or {})
    if hasattr(yahoo, "analystes"):
        try:
            a = lire_analystes(yahoo.analystes(ticker))
            if a:
                d["analystes"] = {**a, "maj": aujourdhui.isoformat()}
        except Exception as e:
            LOG.warning("%s : analystes indisponibles (%s)", ticker, str(e)[:80])
    if "guidance" not in d:
        h = lire_historique(Path(data) / "historique" / "guidance", ticker)
        if pays == "US" and not h["communiques"]:
            d["guidance"] = {"statut": "non analysée",
                             "raison": "analyse à la demande : guidance extraite seulement pour les sociétés suivies par l'agent entreprises"}
        else:
            d["guidance"] = resume_guidance(h, pays)
    return d
