"""
Sources de l'agent matières premières (toutes gratuites).

- Yahoo Finance (yfinance) : cours du contrat le plus proche (10 ans d'historique), contrats des
  échéances suivantes (courbe des prix à terme), indice dollar DX-Y.NYB, parts et valeur liquidative
  des ETF de matières premières (GLD, IAU, SLV, USO, CPER, DBA).
- CFTC, Commitments of Traders (API publique Socrata, rapport « disaggregated », contrats à terme
  seuls) : positions des « managed money ».
- EIA (API v2, clé gratuite dans le secret EIA_API_KEY ; sans clé, la source est ignorée) : stocks
  hebdomadaires de pétrole brut, Cushing, essence, distillats, gaz naturel.
- USDA : base PSD (fichiers CSV publics, totaux mondiaux recalculés) et rapport WASDE (fichier texte
  mensuel, tableaux « World … Supply and Use ») pour le blé, le maïs et le soja.
- FRED : taux réel à 10 ans (DFII10), dollar large (DTWEXBGS), inflation américaine (CPIAUCSL) ;
  API si FRED_API_KEY existe, sinon fichier CSV public.

Mode test : FournisseurTest relit agents/matieres_premieres/tests/donnees/ (captures réelles).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..commun.journal import journal
from ..commun.telechargement import ErreurSource, Telechargeur

LOG = journal("agent-matieres-premieres")

CFTC_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
EIA_URL = "https://api.eia.gov/v2/seriesid/{serie}"
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
PSD_URL = {"grains": "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip",
           "oleagineux": "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip"}
WASDE_URL = "https://www.usda.gov/oce/commodity/wasde/wasde{mm}{aa}.txt"
JOURS_QUOTIDIENS = 430  # au-delà, l'historique des cours est gardé à la semaine (niveau sur 10 ans)

Serie = list[tuple[str, float]]


def _flottant(v) -> float | None:
    try:
        x = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def compacter(points: Serie, aujourdhui: date, jours: int = JOURS_QUOTIDIENS) -> Serie:
    """Cours quotidiens sur les `jours` derniers jours, dernière clôture de chaque semaine avant."""
    limite = (aujourdhui - timedelta(days=jours)).isoformat()
    semaines, recents = {}, []
    for d, v in sorted(points):
        if d >= limite:
            recents.append((d, v))
        else:
            semaines[date.fromisoformat(d).isocalendar()[:2]] = (d, v)
    return sorted(semaines.values()) + recents


def contrats_suivants(racine: str, place: str, mois: str, aujourdhui: date, n: int, codes: str = "FGHJKMNQUVXZ") -> list[dict]:
    """Les n prochains contrats cotés (mois suivant le mois en cours d'abord) : [{symbole, echeance AAAA-MM}]."""
    res = []
    a, m = aujourdhui.year, aujourdhui.month
    for _ in range(40):
        m += 1
        if m > 12:
            a, m = a + 1, 1
        lettre = codes[m - 1]
        if lettre in mois:
            res.append({"symbole": f"{racine}{lettre}{a % 100:02d}.{place}", "echeance": f"{a}-{m:02d}"})
        if len(res) >= n:
            break
    return res


# ------------------------------------------------------------------ WASDE (texte)

_ANNEE = re.compile(r"^\s+(\d{4}/\d{2})\s*(Est\.|Proj\.)?\s*$")
_NOMBRES = re.compile(r"-?\d+(?:\.\d+)?")


def lire_wasde(texte: str, titre: str) -> dict | None:
    """Ligne « World » du tableau `titre` pour la campagne la plus récente (projection du mois et,
    si publiée, du mois précédent). Renvoie {campagne, stocks_fin, consommation, precedent: {…}}."""
    lignes = texte.splitlines()
    campagne, res = None, None
    dans = False
    i = 0
    while i < len(lignes):
        l = lignes[i]
        if titre in l:
            dans = True
        elif dans and "Supply and Use" in l and titre not in l:
            dans = False
        if dans:
            m = _ANNEE.match(l)
            if m:
                campagne = m.group(1)
            elif re.match(r"^World\s", l) and not l.startswith("World Less"):
                nombres = _NOMBRES.findall(re.sub(r"^World\s+\d/", "", l).replace("World", ""))
                valeurs = []
                if len(nombres) >= 7:
                    valeurs = [("", [float(x) for x in nombres[-7:]])]
                else:  # projection : une ligne par mois de publication (ex. « Sep », « Oct »)
                    j = i + 1
                    while j < len(lignes) and re.match(r"^\s+[A-Z][a-z]{2}\s+[\d.]", lignes[j]):
                        mois, *_ = lignes[j].split()
                        valeurs.append((mois, [float(x) for x in _NOMBRES.findall(lignes[j])[-7:]]))
                        j += 1
                if valeurs and campagne:
                    dernier = valeurs[-1][1]
                    res = {"campagne": campagne, "mois": valeurs[-1][0] or None, "stocks_fin": dernier[6], "consommation": dernier[4]}
                    if len(valeurs) > 1:
                        p = valeurs[-2]
                        res["precedent"] = {"mois": p[0], "stocks_fin": p[1][6], "consommation": p[1][4]}
        i += 1
    return res


# ------------------------------------------------------------------ fournisseur réel

class FournisseurReel:
    def __init__(self, dossier_cache: Path):
        self.t = Telechargeur(dossier_cache, duree_cache_h=3)

    # --- Yahoo Finance ---
    def cours(self, symboles: list[str], aujourdhui: date) -> dict[str, Serie]:
        """Clôtures quotidiennes sur 11 ans (compactées : quotidiennes sur 14 mois, hebdomadaires avant)."""
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        brut = yf.download(symboles, period="11y", interval="1d", progress=False, auto_adjust=False, threads=False)
        cloture = brut["Close"]
        res = {}
        for s in symboles:
            if s in cloture:
                serie = cloture[s].dropna()
                if len(serie):
                    res[s] = compacter([(d.strftime("%Y-%m-%d"), round(float(v), 4)) for d, v in serie.items()], aujourdhui)
        if not res:
            raise ErreurSource("Yahoo Finance : aucun cours reçu")
        return res

    def courbes(self, contrats: list[str]) -> dict[str, list]:
        """Dernière clôture de chaque contrat d'échéance : {symbole: [date, clôture]}."""
        import warnings
        import yfinance as yf
        warnings.filterwarnings("ignore")
        brut = yf.download(contrats, period="10d", interval="1d", progress=False, auto_adjust=False, threads=False)
        cloture = brut["Close"]
        res = {}
        for s in contrats:
            if s in cloture:
                serie = cloture[s].dropna()
                if len(serie):
                    res[s] = [serie.index[-1].strftime("%Y-%m-%d"), round(float(serie.iloc[-1]), 4)]
        if not res:
            raise ErreurSource("Yahoo Finance : aucun contrat d'échéance reçu")
        return res

    def etf_parts(self, symboles: list[str]) -> dict:
        """Parts en circulation et VL des ETF de matières premières (Yahoo Finance)."""
        import time
        import yfinance as yf
        res = {}
        for s in symboles:
            try:
                info = yf.Ticker(s).info
                parts, vl = info.get("sharesOutstanding"), info.get("navPrice") or info.get("previousClose")
                quand = info.get("regularMarketTime")
                if parts and vl and quand:
                    res[s] = {"date": datetime.fromtimestamp(int(quand), timezone.utc).date().isoformat(),
                              "parts": float(parts), "vl": float(vl),
                              "encours": float(info["totalAssets"]) if info.get("totalAssets") else None}
            except Exception as e:  # Yahoo refuse parfois ces requêtes (401, 429)
                LOG.warning("Parts Yahoo indisponibles pour %s (%s)", s, str(e)[:120])
            time.sleep(0.7)
        if not res:
            raise ErreurSource("Yahoo Finance : aucune part d'ETF reçue")
        return res

    # --- CFTC (Socrata) ---
    def cftc(self, codes: list[str], depuis: date) -> dict[str, list[dict]]:
        liste = ",".join(f"'{c}'" for c in codes)
        params = {"$where": f"cftc_contract_market_code in({liste}) and report_date_as_yyyy_mm_dd >= '{depuis.isoformat()}'",
                  "$select": "cftc_contract_market_code,market_and_exchange_names,report_date_as_yyyy_mm_dd,"
                             "m_money_positions_long_all,m_money_positions_short_all,open_interest_all",
                  "$order": "report_date_as_yyyy_mm_dd", "$limit": "50000"}
        lignes = self.t.json(CFTC_URL, params=params)
        res: dict[str, list[dict]] = {}
        for l in lignes:
            lg, ct, oi = (_flottant(l.get(k)) for k in ("m_money_positions_long_all", "m_money_positions_short_all", "open_interest_all"))
            if lg is None or ct is None:
                continue
            res.setdefault(l["cftc_contract_market_code"], []).append(
                {"date": l["report_date_as_yyyy_mm_dd"][:10], "long": lg, "short": ct, "oi": oi, "marche": l.get("market_and_exchange_names")})
        if not res:
            raise ErreurSource("CFTC : aucune position reçue")
        return res

    # --- EIA ---
    def eia(self, series: dict[str, str], depuis: date) -> dict[str, Serie] | None:
        """None si la clé EIA_API_KEY est absente (source « non configurée »)."""
        cle = os.environ.get("EIA_API_KEY")
        if not cle:
            return None
        res = {}
        for nom, serie in series.items():
            d = self.t.json(EIA_URL.format(serie=serie), params={"api_key": cle, "start": depuis.isoformat(), "length": "5000"})
            points = [(str(o["period"])[:10], _flottant(o.get("value"))) for o in (d.get("response") or {}).get("data", [])]
            points = sorted((p, v) for p, v in points if v is not None)
            if points:
                res[nom] = points
        if not res:
            raise ErreurSource("EIA : aucune série reçue")
        return res

    # --- USDA PSD : totaux mondiaux (somme des pays) ---
    def psd(self, produits: dict[str, dict]) -> dict:
        """{cle: {campagne: {stocks_fin, consommation}}, "publication": "AAAA-MM"} (milliers de tonnes)."""
        res, publication = {}, None
        par_fichier = defaultdict(dict)
        for cle, p in produits.items():
            par_fichier[p["fichier"]][p["psd"]] = cle
        for fichier, codes in par_fichier.items():
            contenu = self.t.octets(PSD_URL[fichier])
            with zipfile.ZipFile(io.BytesIO(contenu)) as z:
                nom = next(n for n in z.namelist() if n.endswith(".csv"))
                with z.open(nom) as f:
                    totaux = defaultdict(lambda: defaultdict(float))
                    for l in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                        cle = codes.get(l["Commodity_Code"])
                        attr = {"Ending Stocks": "stocks_fin", "Domestic Consumption": "consommation"}.get(l["Attribute_Description"])
                        if not cle or not attr or int(l["Market_Year"]) < 1995:
                            continue
                        totaux[cle][(l["Market_Year"], attr)] += float(l["Value"] or 0)
                        mois = f"{l['Calendar_Year']}-{int(l['Month']):02d}"
                        publication = max(publication or mois, mois)
            for cle, t in totaux.items():
                annees = sorted({a for a, _ in t})
                res[cle] = {a: {"stocks_fin": round(t[(a, "stocks_fin")], 1), "consommation": round(t[(a, "consommation")], 1)}
                            for a in annees if t[(a, "consommation")] > 0}
        if not res:
            raise ErreurSource("USDA PSD : aucune donnée")
        return {"produits": res, "publication": publication}

    # --- USDA WASDE : rapport du mois (ou du mois précédent s'il n'est pas encore publié) ---
    def wasde(self, produits: dict[str, dict], aujourdhui: date) -> dict:
        derniere = None
        for decalage in range(3):
            a, m = aujourdhui.year, aujourdhui.month - decalage
            while m <= 0:
                a, m = a - 1, m + 12
            try:
                texte = self.t.texte(WASDE_URL.format(mm=f"{m:02d}", aa=f"{a % 100:02d}"))
            except ErreurSource as e:
                derniere = e
                continue
            res = {cle: lire_wasde(texte, p["wasde"]) for cle, p in produits.items()}
            res = {k: v for k, v in res.items() if v}
            if res:
                return {"produits": res, "publication": f"{a}-{m:02d}", "fichier": WASDE_URL.format(mm=f"{m:02d}", aa=f"{a % 100:02d}")}
        raise ErreurSource(f"USDA WASDE : rapport introuvable ({derniere})")

    # --- FRED ---
    def fred(self, serie: str, depuis: str) -> tuple[Serie, str]:
        cle = os.environ.get("FRED_API_KEY")
        if cle:
            d = self.t.json(FRED_API, params={"series_id": serie, "api_key": cle, "file_type": "json", "observation_start": depuis})
            points, mode = [(o["date"], _flottant(o["value"])) for o in d["observations"]], "API"
        else:
            lignes = list(csv.reader(io.StringIO(self.t.texte(FRED_CSV, params={"id": serie, "cosd": depuis}))))
            points, mode = [(l[0], _flottant(l[1])) for l in lignes[1:] if len(l) >= 2], "CSV public"
        points = [(d, v) for d, v in points if v is not None]
        if not points:
            raise ErreurSource(f"FRED {serie} : aucune donnée")
        return points, mode


# ------------------------------------------------------------------ fournisseur de test et capture

class FournisseurTest:
    """Relit les fichiers de agents/matieres_premieres/tests/donnees/ (captures réelles)."""

    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def _lire(self, nom: str):
        chemin = self.dossier / f"{nom}.json"
        if not chemin.exists():
            raise FileNotFoundError(f"Donnée de test absente : {chemin.name} (simulation d'une source en panne)")
        return json.loads(chemin.read_text(encoding="utf-8"))

    def cours(self, symboles, aujourdhui):
        d = self._lire("cours")
        return {s: [tuple(p) for p in d[s]] for s in symboles if s in d}

    def courbes(self, contrats):
        d = self._lire("courbes")
        return {s: d[s] for s in contrats if s in d}

    def etf_parts(self, symboles):
        d = self._lire("etf_parts")
        return {s: d[s] for s in symboles if s in d}

    def cftc(self, codes, depuis):
        d = self._lire("cftc")
        return {c: d[c] for c in codes if c in d}

    def eia(self, series, depuis):
        if not (self.dossier / "eia.json").exists():
            return None  # comme sans clé : source « non configurée »
        d = self._lire("eia")
        return {k: [tuple(p) for p in d[k]] for k in series if k in d}

    def psd(self, produits):
        return self._lire("psd")

    def wasde(self, produits, aujourdhui):
        return self._lire("wasde")

    def fred(self, serie, depuis):
        d = self._lire(f"fred_{serie}")
        return [tuple(p) for p in d["points"]], d["mode"]


class Capture:
    """Enveloppe le fournisseur réel et enregistre chaque réponse comme donnée de test
    (python -m agents.matieres_premieres --capturer)."""

    def __init__(self, reel, dossier: Path):
        self.reel, self.dossier = reel, Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)

    def _ecrire(self, nom, objet):
        (self.dossier / f"{nom}.json").write_text(json.dumps(objet, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def __getattr__(self, nom):
        methode = getattr(self.reel, nom)

        def appel(*args):
            res = methode(*args)
            if nom == "fred":
                self._ecrire(f"fred_{args[0]}", {"points": res[0], "mode": res[1]})
            elif res is not None:
                self._ecrire(nom, res)
            return res
        return appel
