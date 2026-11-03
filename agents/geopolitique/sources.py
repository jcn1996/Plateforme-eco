"""
Sources de l'agent géopolitique (toutes gratuites, sans réseaux sociaux).

- GDELT : API DOC 2.0 (articles par thème, mode ArtList) et fichiers d'événements GDELT 2.0
  publiés toutes les 15 minutes (événements géolocalisés : pays, tonalité, volume). L'API GEO 2.0
  ne répond plus (404) : la géolocalisation vient de ces fichiers.
- Officiel : Federal Register (API), actions récentes de l'OFAC (page officielle), flux RSS de la
  Maison-Blanche, de l'Élysée, de la Commission européenne, du Conseil de l'UE (dont les
  sanctions de l'UE), discours des banquiers centraux (BRI).
- Indices : risque géopolitique quotidien de Caldara et Iacoviello (matteoiacoviello.com),
  incertitude de politique économique (FRED, USEPUINDXD).
- Presse : flux RSS de grands médias internationaux.

Les fonctions lire_* analysent les réponses brutes : elles servent aussi aux tests, qui relisent
des réponses réelles enregistrées dans tests/donnees/.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource, Telechargeur

LOG = journal("agent-geopolitique")

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_DERNIER = "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_EXPORT = "https://data.gdeltproject.org/gdeltv2/{horodatage}.export.CSV.zip"
FEDERAL_REGISTER = "https://www.federalregister.gov/api/v1/documents.json"
OFAC_ACTIONS = "https://ofac.treasury.gov/recent-actions"
GPR_QUOTIDIEN = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"

# Colonnes du fichier d'événements GDELT 2.0 (61 colonnes, séparées par des tabulations)
COL_QUAD, COL_GOLDSTEIN, COL_ARTICLES, COL_TON, COL_PAYS, COL_URL = 29, 30, 33, 34, 53, 60


LANGUES_GDELT = {"english": "en", "french": "fr", "spanish": "es", "german": "de", "italian": "it", "portuguese": "pt",
                 "chinese": "zh", "arabic": "ar", "russian": "ru", "japanese": "ja"}


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def domaine(url: str) -> str:
    """Domaine enregistré, sans « www. » ni sous-domaine courant (feeds., rss.)."""
    m = re.match(r"https?://([^/:?#]+)", url or "")
    if not m:
        return ""
    hote = m.group(1).lower()
    hote = re.sub(r"^(www|feeds|rss|m|amp|edition|english)\.", "", hote)
    morceaux = hote.split(".")
    # co.uk, com.au… : on garde trois morceaux
    if len(morceaux) >= 3 and morceaux[-2] in ("co", "com", "gov", "org", "ac", "net"):
        return ".".join(morceaux[-3:])
    return ".".join(morceaux[-2:])


# ------------------------------------------------------------------ analyse des réponses

def lire_doc(texte: str) -> list[dict]:
    """Réponse ArtList (JSON) de l'API DOC 2.0 de GDELT."""
    if not texte.strip().startswith("{"):
        raise ErreurSource(f"GDELT DOC : réponse inattendue ({texte.strip()[:80]})")
    d = json.loads(texte, strict=False)
    res = []
    for a in d.get("articles") or []:
        try:
            date = iso(datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc))
        except (KeyError, ValueError):
            continue
        if a.get("url") and a.get("title"):
            res.append({"titre": html.unescape(a["title"]).strip(), "url": a["url"], "domaine": domaine(a["url"]),
                        "date": date, "langue": LANGUES_GDELT.get((a.get("language") or "").lower(), (a.get("language") or "")[:2].lower() or None),
                        "pays_source": a.get("sourcecountry"),
                        "origine": "gdelt"})
    return res


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _date_flux(texte: str | None) -> str | None:
    if not texte:
        return None
    texte = texte.strip()
    try:
        return iso(parsedate_to_datetime(texte))
    except (TypeError, ValueError, IndexError):
        pass
    try:
        t = datetime.fromisoformat(texte.replace("Z", "+00:00"))
        return iso(t if t.tzinfo else t.replace(tzinfo=timezone.utc))
    except ValueError:
        return None


def _sans_balises(texte: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", texte or ""))).strip()


def lire_rss(texte: str) -> list[dict]:
    """Flux RSS 2.0, RSS 1.0 (RDF) ou Atom : [{titre, url, date, description, categories}]."""
    racine = ET.fromstring(texte.lstrip("﻿").strip().encode("utf-8"))
    res = []
    for e in racine.iter():
        if _local(e.tag) not in ("item", "entry"):
            continue
        champs = {}
        categories = []
        for f in e:
            nom = _local(f.tag)
            if nom == "link":
                champs.setdefault("url", (f.text or "").strip() or f.get("href"))
            elif nom == "category":
                categories.append((f.text or f.get("term") or "").strip())
            elif nom in ("title", "description", "summary", "pubDate", "date", "updated", "published"):
                champs.setdefault(nom, f.text)
        url = champs.get("url") or e.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about")
        titre = _sans_balises(champs.get("title"))
        if not url or not titre:
            continue
        date = _date_flux(champs.get("pubDate") or champs.get("date") or champs.get("updated") or champs.get("published"))
        res.append({"titre": titre, "url": url.strip(), "domaine": domaine(url), "date": date,
                    "description": _sans_balises(champs.get("description") or champs.get("summary"))[:400],
                    "categories": [c for c in categories if c]})
    return res


def lire_federal_register(texte: str) -> list[dict]:
    d = json.loads(texte)
    res = []
    for r in d.get("results") or []:
        res.append({"titre": r["title"].strip(), "url": r["html_url"], "domaine": "federalregister.gov",
                    "date": f"{r['publication_date']}T12:00:00Z", "type": r.get("type"),
                    "description": (r.get("abstract") or "")[:400],
                    "agences": [a.get("name") for a in r.get("agencies") or [] if a.get("name")]})
    return res


MOIS_EN = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], 1)}


def lire_ofac(texte: str) -> list[dict]:
    """Page « Recent Actions » de l'OFAC : [{titre, url, date}]."""
    res = []
    motif = re.compile(r'<a href="(/recent-actions/[0-9A-Za-z_-]+)"[^>]*>(.*?)</a>.*?([A-Z][a-z]+ \d{1,2}, \d{4})', re.S)
    for chemin, titre, date in motif.findall(texte):
        mois, jour, an = re.match(r"([A-Za-z]+) (\d+), (\d+)", date).groups()
        if mois.lower() not in MOIS_EN:
            continue
        res.append({"titre": _sans_balises(titre), "url": f"https://ofac.treasury.gov{chemin}", "domaine": "treasury.gov",
                    "date": f"{an}-{MOIS_EN[mois.lower()]:02d}-{int(jour):02d}T12:00:00Z", "description": ""})
    return res


def agreger_export(texte: str, fips_suivis: set[str]) -> dict[str, dict]:
    """Fichier d'événements GDELT 2.0 → agrégats par pays (code FIPS du lieu de l'action) :
    {fips: {evenements, articles, ton_pondere, conflits}}. conflits = QuadClass 3 et 4
    (conflit verbal et matériel)."""
    res: dict[str, dict] = {}
    for l in csv.reader(io.StringIO(texte), delimiter="\t", quoting=csv.QUOTE_NONE):
        if len(l) < 61:
            continue
        pays = l[COL_PAYS]
        if pays not in fips_suivis:
            continue
        try:
            articles = int(l[COL_ARTICLES] or 0)
            ton = float(l[COL_TON] or 0)
            quad = int(l[COL_QUAD] or 0)
        except ValueError:
            continue
        a = res.setdefault(pays, {"evenements": 0, "articles": 0, "ton_pondere": 0.0, "conflits": 0})
        a["evenements"] += 1
        a["articles"] += articles
        a["ton_pondere"] += ton * articles
        a["conflits"] += 1 if quad >= 3 else 0
    return res


def lire_gpr(contenu: bytes) -> list[list]:
    """Indice quotidien de risque géopolitique (fichier .xls) : [[AAAA-MM-JJ, GPRD, GPRD_MA7]]."""
    import xlrd
    feuille = xlrd.open_workbook(file_contents=contenu).sheet_by_index(0)
    entete = [str(c).strip() for c in feuille.row_values(0)]
    i_jour, i_val, i_ma7 = entete.index("DAY"), entete.index("GPRD"), entete.index("GPRD_MA7")
    res = []
    for r in range(1, feuille.nrows):
        ligne = feuille.row_values(r)
        jour = str(ligne[i_jour]).split(".")[0]
        if len(jour) != 8 or ligne[i_val] in ("", None):
            continue
        ma7 = ligne[i_ma7] if ligne[i_ma7] not in ("", None) else None
        res.append([f"{jour[:4]}-{jour[4:6]}-{jour[6:]}", round(float(ligne[i_val]), 2), round(float(ma7), 2) if ma7 is not None else None])
    if not res:
        raise ErreurSource("GPR : aucune donnée")
    return res


# ------------------------------------------------------------------ fournisseurs

class ClientGdelt:
    """API DOC 2.0 de GDELT : au moins `delai_entre_requetes_secondes` (≥ 5 s, consigne de GDELT)
    entre deux requêtes de l'exécution ; reprises sur 429 et 5xx avec attentes croissantes
    (`attentes_reprise_secondes`, ou l'en-tête Retry-After s'il est plus long) ; chaque échec est
    journalisé avec son code exact ; `budget_secondes` borne le temps total passé sur l'API
    (au-delà, les requêtes suivantes ne sont pas tentées)."""

    def __init__(self, cfg: dict, session, horloge=time.monotonic, dormir=time.sleep):
        self.cfg, self.session, self.horloge, self.dormir = cfg, session, horloge, dormir
        self.intervalle = max(5.0, float(cfg["delai_entre_requetes_secondes"]))
        self.debut = None
        self.derniere = None
        self.tentatives: list[dict] = []  # trace : {requete, essai, code, detail}

    def _reste(self) -> float:
        return self.cfg["budget_secondes"] - (self.horloge() - self.debut)

    def requete(self, cle: str, params: dict) -> str:
        import requests
        if self.debut is None:
            self.debut = self.horloge()
        attentes = self.cfg["attentes_reprise_secondes"]
        derniere = None
        for essai in range(1, self.cfg["essais"] + 1):
            if self.derniere is not None:
                pause = self.intervalle - (self.horloge() - self.derniere)
                if pause > 0:
                    self.dormir(pause)
            if self._reste() <= 0:
                raise ErreurSource(f"budget de {self.cfg['budget_secondes']} s épuisé" + (f" ; dernier échec : {derniere}" if derniere else ""))
            self.derniere = self.horloge()
            try:
                r = self.session.get(GDELT_DOC, params=params, timeout=25)
                code, corps, apres = r.status_code, r.text, r.headers.get("Retry-After")
            except requests.RequestException as e:
                code, corps, apres = None, f"{type(e).__name__}: {str(e)[:120]}", None
            if code == 200:
                self.tentatives.append({"requete": cle, "essai": essai, "code": 200})
                return corps
            extrait = re.sub(r"\s+", " ", corps or "")[:120]
            derniere = f"HTTP {code}" if code else "erreur réseau"
            self.tentatives.append({"requete": cle, "essai": essai, "code": code, "detail": extrait})
            LOG.warning("GDELT DOC %s : %s (essai %d/%d) %s", cle, derniere, essai, self.cfg["essais"], extrait)
            if code is not None and code not in (429, 500, 502, 503, 504):
                raise ErreurSource(f"{derniere} : {extrait}")
            if essai < self.cfg["essais"]:
                attente = attentes[min(essai - 1, len(attentes) - 1)]
                try:
                    attente = max(attente, float(apres)) if apres else attente
                except ValueError:
                    pass
                if attente > self._reste():
                    break
                self.dormir(attente)
        raise ErreurSource(f"{derniere} après {essai} essai(s)")


class FournisseurReel:
    def __init__(self, dossier_cache: Path, config: dict):
        self.config = config
        # Cache court : l'agent tourne toutes les heures
        self.t = Telechargeur(dossier_cache, duree_cache_h=0.25, essais=3, delai_max=30)
        self.gdelt = ClientGdelt(config["gdelt"], self.t.session)

    def gdelt_doc(self, cle: str, requete: str, maxi: int | None = None) -> list[dict]:
        g = self.config["gdelt"]
        langues = " OR ".join(f"sourcelang:{l}" for l in g["langues"])
        params = {"query": f"{requete} ({langues})" if len(g["langues"]) > 1 else f"{requete} {langues}",
                  "mode": "ArtList", "format": "json", "maxrecords": maxi or g["articles_max_par_requete"],
                  "timespan": g["fenetre_doc"], "sort": "DateDesc"}
        return lire_doc(self.gdelt.requete(cle, params))

    def gdelt_evenements(self, fips_suivis: set[str], n: int) -> dict:
        """Les n derniers fichiers d'événements (15 min chacun) : {horodatages, pays: agrégats}."""
        dernier = self.t.texte(GDELT_DERNIER)
        m = re.search(r"/(\d{14})\.export\.CSV\.zip", dernier)
        if not m:
            raise ErreurSource("GDELT : lastupdate.txt illisible")
        t = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
        total: dict[str, dict] = {}
        horodatages = []
        # Les n fichiers les plus récents disponibles : un fichier annoncé peut ne pas être encore
        # publié (404), on remonte alors jusqu'à 2 h en arrière ; si aucun ne répond, nouvel essai après 20 s
        for tour in range(2):
            for k in range(n + 8):
                if len(horodatages) >= n:
                    break
                h = (t - timedelta(minutes=15 * k)).strftime("%Y%m%d%H%M%S")
                if h in horodatages:
                    continue
                try:
                    contenu = self.t.octets(GDELT_EXPORT.format(horodatage=h))
                except ErreurSource as e:
                    LOG.warning("GDELT, fichier %s indisponible : %s", h, e)
                    continue
                with zipfile.ZipFile(io.BytesIO(contenu)) as z:
                    texte = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
                horodatages.append(h)
                for pays, a in agreger_export(texte, fips_suivis).items():
                    cumul = total.setdefault(pays, {"evenements": 0, "articles": 0, "ton_pondere": 0.0, "conflits": 0})
                    for c in cumul:
                        cumul[c] += a[c]
            if horodatages:
                break
            time.sleep(20)
        if not horodatages:
            raise ErreurSource("GDELT : aucun fichier d'événements lisible")
        return {"horodatages": horodatages, "pays": total}

    def federal_register(self, agences: list[str], depuis: str) -> list[dict]:
        champs = [("fields[]", c) for c in ("title", "html_url", "publication_date", "type", "abstract", "agencies")]
        base = [("per_page", "100"), ("order", "newest"), ("conditions[publication_date][gte]", depuis)] + champs
        presid = lire_federal_register(self.t.texte(FEDERAL_REGISTER, params=base + [("conditions[type][]", "PRESDOCU")]))
        agences_p = base + [("conditions[agencies][]", a) for a in agences]
        mesures = lire_federal_register(self.t.texte(FEDERAL_REGISTER, params=agences_p))
        vus, res = set(), []
        for d in presid + mesures:
            if d["url"] not in vus:
                vus.add(d["url"])
                res.append(d)
        return res

    def ofac(self) -> list[dict]:
        return lire_ofac(self.t.texte(OFAC_ACTIONS))

    def rss(self, cle: str, url: str) -> list[dict]:
        return lire_rss(self.t.texte(url, entetes={"User-Agent": "Mozilla/5.0 (compatible; SalleDeControle/1.0)"}))

    def gpr(self) -> list[list]:
        return lire_gpr(self.t.octets(GPR_QUOTIDIEN))

    def epu(self, depuis: str) -> tuple[list, str]:
        from ..macro.sources import FournisseurReel as FournisseurMacro
        f = FournisseurMacro(self.t.dossier_cache)
        f.t = self.t  # même téléchargeur (cache, reprises)
        points, mode = f.fred("USEPUINDXD", depuis)
        return [[d, v] for d, v in points], mode


class FournisseurTest:
    """Relit tests/donnees/ : réponses réelles enregistrées (RSS, Federal Register, OFAC, GDELT
    export) et, pour l'API DOC de GDELT, réponses au format ArtList."""

    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def _texte(self, nom: str) -> str:
        chemin = self.dossier / nom
        if not chemin.exists():
            raise ErreurSource(f"donnée de test absente : {nom} (simulation d'une source en panne)")
        return chemin.read_text(encoding="utf-8")

    def gdelt_doc(self, cle, requete, maxi=None):
        if cle.startswith("groupe"):  # requêtes groupées : la première renvoie les articles de tous les thèmes
            if not cle.startswith("groupe 1/"):
                return []
            res = []
            for chemin in sorted(self.dossier.glob("gdelt_doc_*.json")):
                res += lire_doc(chemin.read_text(encoding="utf-8"))
            if not res:
                raise ErreurSource("donnée de test absente : gdelt_doc_*.json")
            return res
        return lire_doc(self._texte(f"gdelt_doc_{cle}.json"))

    def gdelt_evenements(self, fips_suivis, n):
        return {"horodatages": ["20261103134500"], "pays": agreger_export(self._texte("gdelt_export.csv"), fips_suivis)}

    def federal_register(self, agences, depuis):
        return lire_federal_register(self._texte("federal_register.json"))

    def ofac(self):
        return lire_ofac(self._texte("ofac.html"))

    def rss(self, cle, url):
        return lire_rss(self._texte(f"rss_{cle}.xml"))

    def gpr(self):
        return json.loads(self._texte("gpr.json"))

    def epu(self, depuis):
        return json.loads(self._texte("epu.json")), "CSV public"
