"""
Agent entreprises (sans IA) : environ 1 200 sociétés cotées dans les pays suivis.

Modes :
  --mode complet --lot <nom>   révision complète d'un lot (samedi) → fichier de lot (--sortie-lot)
  --mode assembler             fusionne les lots dans data/entreprises/comptes.json puis publie
  --mode quotidien             cours, momentum, valorisation ; sociétés ayant publié de nouveaux comptes
  --mode complet --echantillon N   révision complète d'un échantillon puis publication (essai local)
  --test                       données de test enregistrées (sans réseau)

Fichiers écrits : data/entreprises.json, data/secteurs.json, data/pepites.json,
data/signaux/entreprises.json, data/historique/entreprises/AAAA-MM-JJ.json,
data/recap/entreprises-AAAA-MM-JJ.md, data/journal/agent-entreprises.json ;
stockage : data/entreprises/univers.json (dernière liste connue), data/entreprises/comptes.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from ..commun.telechargement import Telechargeur
from . import analyse as A
from . import comptes as C
from . import univers as U

LOG = journal("agent-entreprises")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
DEVISE_PAYS = {"US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL", "AR": "ARS", "CL": "CLP", "CO": "COP", "GB": "GBP", "FR": "EUR",
               "DE": "EUR", "IT": "EUR", "ES": "EUR", "NL": "EUR", "CH": "CHF", "SE": "SEK", "PL": "PLN", "JP": "JPY", "CN": "HKD",
               "IN": "INR", "KR": "KRW", "TW": "TWD", "AU": "AUD", "ID": "IDR", "SG": "SGD", "TH": "THB", "VN": "VND", "SA": "SAR",
               "AE": "AED", "TR": "TRY", "ZA": "ZAR", "EG": "EGP"}


def maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ fournisseurs

class Fournisseur:
    """Accès réseau réel (Yahoo, SEC, ESEF, EDINET, DART)."""

    def __init__(self, config: dict):
        self.t = Telechargeur(RACINE / "agents" / ".cache" / "entreprises", duree_cache_h=20, delai_politesse=0.2)
        self.yahoo = C.Yahoo()
        self.sec = C.Sec(self.t, config["sec"]["requetes_par_seconde"])
        self.esef = C.Esef(self.t)
        self.edinet = C.Edinet(self.t)
        self.dart = C.Dart(self.t)
        self.composition = U.Composition(self.t, config, self.yahoo)

    def officiel(self, s: dict, ids: dict) -> tuple[dict | None, str | None, dict]:
        """Comptes officiels de la société (ou None) et nom de la source ; complète les identifiants (LEI, CIK)."""
        pays = s["pays"]
        if pays == "US" and self.sec.actif:
            cik = ids.get("cik") or self.sec.cik(s["ticker"])
            if not cik:
                return None, None, ids
            ids["cik"] = cik
            annuels = self.sec.comptes(cik)
            pubs = self.sec.publications(cik)
            ids["publications"] = pubs[:3]
            if annuels:
                dix_k = next((p for p in pubs if p["formulaire"] in ("10-K", "20-F", "40-F")), None)
                return {**annuels[0], "url": dix_k["url"] if dix_k else None, "publie": dix_k["date"] if dix_k else None}, "SEC (XBRL companyfacts)", ids
        if pays in C.Esef.PAYS:
            lei = ids.get("lei") or self.esef.lei(s["nom"], pays)
            ids["lei"] = lei
            r = self.esef.dernier_rapport(lei) if lei else None
            if r:
                return {**self.esef.comptes(r)}, "ESEF (filings.xbrl.org)", ids
        if pays == "JP" and self.edinet.actif:
            r = self.edinet.comptes(s["ticker"].split(".")[0])
            if r:
                return r, "EDINET", ids
        if pays == "KR" and self.dart.actif:
            r = self.dart.comptes(s["ticker"])
            if r:
                return r, "DART", ids
        return None, None, ids


class Capture:
    """Enregistre les réponses de quelques sociétés comme données de test (--capturer N)."""

    def __init__(self, f, nombre: int):
        self.f, self.nombre = f, nombre
        self.d = {"yahoo": {}, "officiel": {}, "change": {}}
        self.composition, self.sec = f.composition, f.sec
        self.edinet, self.dart = f.edinet, f.dart
        capture = self

        class _Y:
            def societe(self, t):
                r = f.yahoo.societe(t)
                if len(capture.d["yahoo"]) < capture.nombre:
                    capture.d["yahoo"][t] = r
                return r

            def taux_change(self, devises):
                capture.d["change"] = f.yahoo.taux_change(devises)
                return capture.d["change"]

            def cours_groupes(self, tickers, periode="13mo"):
                return f.yahoo.cours_groupes(tickers, periode)
        self.yahoo = _Y()

    def officiel(self, s, ids):
        r = self.f.officiel(s, ids)
        if s["ticker"] in self.d["yahoo"] and r[0]:
            self.d["officiel"][s["ticker"]] = {"comptes": r[0], "source": r[1]}
        return r

    def ecrire(self, dossier: Path):
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "societes.json").write_text(json.dumps(self.d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


class FournisseurTest:
    """Rejoue les réponses enregistrées dans agents/entreprises/tests/donnees/ (sans réseau)."""

    def __init__(self, dossier: Path):
        self.d = json.loads((Path(dossier) / "societes.json").read_text(encoding="utf-8"))
        self.composition = None
        self.sec = type("SecAbsente", (), {"actif": False})()

    class _Yahoo:
        def __init__(self, d):
            self.d = d

        def societe(self, t):
            if t not in self.d["yahoo"]:
                raise C.ErreurSource(f"donnée de test absente : {t}")
            return self.d["yahoo"][t]

        def taux_change(self, devises):
            return self.d["change"]

        def cours_groupes(self, tickers, periode="13mo"):
            return {t: self.d["yahoo"][t]["cours"] for t in tickers if t in self.d["yahoo"]}

    @property
    def yahoo(self):
        return self._Yahoo(self.d)

    def officiel(self, s, ids):
        o = self.d["officiel"].get(s["ticker"])
        return (o["comptes"], o["source"], ids) if o else (None, None, ids)


# ------------------------------------------------------------------ collecte d'une société

def cours_compacts(cours: list) -> list:
    """Stockage léger : dernier cours, cours d'il y a 3, 6 et 12 mois, et montant moyen échangé sur 63 séances
    (dans la devise de cotation) porté par le dernier point. Suffit pour le momentum et la liquidité."""
    if not cours:
        return []
    fin = date.fromisoformat(cours[-1][0])
    points = {}
    for jours in (365, 182, 91):
        avant = [p for p in cours if date.fromisoformat(p[0]) <= fin - timedelta(days=jours)]
        if avant:
            points[avant[-1][0]] = [avant[-1][0], round(avant[-1][1], 4), 0]
    echanges = [c * v for _, c, v in cours[-63:] if v]
    moyenne = round(statistics.fmean(echanges)) if echanges else 0
    points[cours[-1][0]] = [cours[-1][0], round(cours[-1][1], 4), moyenne]
    return [points[k] for k in sorted(points)]


def collecter_societe(f, s: dict, ancien: dict | None, seuil_ecart: float) -> dict:
    y = f.yahoo.societe(s["ticker"])
    ids = dict((ancien or {}).get("ids") or {})
    officiel, source_off, verification = None, None, None
    try:
        officiel, source_off, ids = f.officiel({**s, "nom": y.get("nom") or s["nom"]}, ids)
    except Exception as e:  # source officielle en panne : la société reste analysée avec Yahoo
        LOG.warning("%s : source officielle indisponible (%s)", s["ticker"], str(e)[:120])
    annuel = y["annuel"]
    if officiel:
        verification = C.verifier(officiel, annuel, seuil_ecart)
        # La source officielle est retenue sur l'exercice commun (chiffre d'affaires, résultat net, flux d'exploitation)
        e = C.exercice_correspondant(annuel, officiel["fin"])
        if e:
            for cle in ("ca", "resultat_net", "cfo"):
                if officiel.get(cle) is not None:
                    e[f"{cle}_yahoo"] = e.get(cle)
                    e[cle] = officiel[cle]
    info = y.get("info") or {}
    devise_cours, centimes = C.devise_majeure(y.get("devise_cours"))
    devise_comptes = y.get("devise_comptes") or info.get("financialCurrency") or (officiel or {}).get("devise") or devise_cours
    secteur = s.get("secteur") or U.secteur_gics(info.get("sector"))
    industrie = info.get("industry")
    if not secteur and hasattr(f.yahoo, "secteur"):
        try:
            brut, industrie = f.yahoo.secteur(s["ticker"])
            secteur = U.secteur_gics(brut)
        except Exception as e:
            LOG.debug("secteur Yahoo indisponible pour %s : %s", s["ticker"], str(e)[:80])
    trim = y.get("trimestriel") or []
    ttm = None
    if len(trim) >= 4 and all(t.get("resultat_net") is not None for t in trim[:4]) and annuel and trim[0]["fin"] > annuel[0]["fin"]:
        ttm = sum(t["resultat_net"] for t in trim[:4])
    return {
        "ticker": s["ticker"], "nom": y.get("nom") or s["nom"], "pays": s["pays"],
        "secteur_gics": secteur, "industrie": industrie,
        "devise_cours": devise_cours, "centimes": centimes, "devise_comptes": devise_comptes,
        "actions": info.get("sharesOutstanding") or (annuel[0].get("actions") if annuel else None),
        "cours": cours_compacts(y["cours"]), "annuel": annuel,
        "trimestre": {"fin": trim[0]["fin"], "resultat_net_ttm": ttm} if trim else None,
        "officiel": officiel, "source_officielle": source_off, "verification": verification, "ids": ids,
        "surveillance": bool(s.get("surveillance")), "source_composition": s.get("source_composition"),
        "analystes": info.get("numberOfAnalystOpinions"),
        "maj_comptes": date.today().isoformat(), "tentative": date.today().isoformat(),
    }


# ------------------------------------------------------------------ révision complète et quotidienne

def tranche(liste: list, t: list | None) -> list:
    if not t:
        return liste
    i, n = t
    return liste[i::n]


def reviser(f, societes: list[dict], anciens: dict, config: dict) -> tuple[dict, dict]:
    res, etats = {}, {"ok": 0, "echec": 0, "officiel": 0, "echecs": []}
    for k, s in enumerate(societes, 1):
        try:
            r = collecter_societe(f, s, anciens.get(s["ticker"]), config["ecart_officiel_max_pct"])
            res[s["ticker"]] = r
            etats["ok"] += 1
            etats["officiel"] += 1 if r["officiel"] else 0
        except Exception as e:
            etats["echec"] += 1
            etats["echecs"].append(f"{s['ticker']} : {str(e)[:100]}")
            if s["ticker"] in anciens:  # dernière analyse connue conservée
                res[s["ticker"]] = {**anciens[s["ticker"]], "tentative": date.today().isoformat(), "ancienne": True}
        if k % 25 == 0:
            LOG.info("%d / %d sociétés traitées (%d échecs)", k, len(societes), etats["echec"])
    return res, etats


def mise_a_jour_quotidienne(f, base: dict, config: dict, aujourdhui: date) -> dict:
    """Cours de toutes les sociétés ; nouvelles publications (SEC) ; comptes anciens rafraîchis par petits groupes."""
    tickers = list(base)
    cours = f.yahoo.cours_groupes(tickers)
    for t, c in cours.items():
        base[t]["cours"] = cours_compacts(c)
    a_revoir = []
    for t, r in base.items():
        pubs = (r.get("ids") or {}).get("publications") or []
        if r["pays"] == "US" and f.sec.actif and r.get("ids", {}).get("cik"):
            try:
                nouvelles = f.sec.publications(r["ids"]["cik"])
                if nouvelles and (not pubs or nouvelles[0]["date"] > pubs[0]["date"]):
                    a_revoir.append(t)
            except Exception as e:
                LOG.warning("SEC submissions %s : %s", t, str(e)[:100])
        else:
            fin = (r.get("trimestre") or {}).get("fin") or ((r.get("annuel") or [{}])[0]).get("fin")
            essai = r.get("tentative") or "2000-01-01"
            if fin and (aujourdhui - date.fromisoformat(fin)).days > 120 and (aujourdhui - date.fromisoformat(essai)).days >= 7:
                a_revoir.append(t)
    a_revoir = a_revoir[:150]
    # Sociétés américaines sans comptes SEC (secret absent lors de leur révision, CIK introuvable, panne) :
    # mises en file pour la prochaine révision complète, qui les relira avec la SEC
    file_sec = 0
    for r in base.values():
        if r["pays"] == "US" and not (r.get("source_officielle") or "").startswith("SEC"):
            r["file_sec"] = True
            file_sec += 1
        else:
            r.pop("file_sec", None)
    LOG.info("Sociétés américaines sans comptes SEC, en file pour la prochaine révision complète : %d", file_sec)
    # Rattrapage : sociétés sans secteur (fichier de composition sans secteur, .info refusé)
    if hasattr(f.yahoo, "secteur"):
        for t, r in base.items():
            if not r.get("secteur_gics"):
                try:
                    brut, industrie = f.yahoo.secteur(t)
                    r["secteur_gics"], r["industrie"] = U.secteur_gics(brut), r.get("industrie") or industrie
                except Exception as e:
                    LOG.debug("secteur Yahoo indisponible pour %s : %s", t, str(e)[:80])
    LOG.info("Nouvelles publications ou comptes anciens : %d sociétés révisées", len(a_revoir))
    revus, _ = reviser(f, [{"ticker": t, "nom": base[t]["nom"], "pays": base[t]["pays"], "secteur": base[t].get("secteur_gics"),
                            "surveillance": base[t].get("surveillance"), "source_composition": base[t].get("source_composition")}
                           for t in a_revoir], base, config)
    base.update(revus)
    return {"cours": len(cours), "revues": len(a_revoir), "en_file_sec": file_sec}


def echantillon(liste: list[dict], n: int, config: dict) -> list[dict]:
    """Échantillon réparti : environ un tiers aux États-Unis, le reste réparti entre les pays (plus grosses positions d'abord)."""
    par_pays = {}
    for s in liste:
        par_pays.setdefault(s["pays"], []).append(s)
    us = par_pays.pop("US", [])[: max(1, n // 3)]
    res, k = list(us), 0
    pays = list(par_pays)
    while len(res) < n and any(par_pays.values()):
        p = pays[k % len(pays)]
        if par_pays[p]:
            res.append(par_pays[p].pop(0))
        k += 1
    return res


# ------------------------------------------------------------------ publication

def publier(base: dict, config: dict, change: dict, data: Path, aujourdhui: date, etats_sources: dict) -> dict:
    cfg_u = config["univers"]
    pays_json = {p["code"]: p for p in ((lire_json(data / "pays.json") or {}).get("donnees") or [])}
    macro = (lire_json(data / "macro.json") or {}).get("donnees") or {}
    zones = {z["cle"]: z["phase"] for z in (macro.get("cycle") or {}).get("zones", [])}
    zone_par_pays = json.loads((RACINE / "agents" / "macro" / "config.json").read_text(encoding="utf-8"))["zone_par_pays"]
    ancien = lire_json(data / "entreprises.json")
    precedentes = {e["ticker"]: e for e in (ancien or {}).get("donnees", [])} if ancien and (ancien.get("meta") or {}).get("fictif") is False else {}
    # Détail précédent (alertes, exercice) lu dans les fiches, avant qu'elles soient réécrites
    for t, e in precedentes.items():
        fiche = lire_json(data / "entreprises" / "fiches" / fichier_fiche(t))
        if fiche and fiche.get("donnees"):
            precedentes[t] = {**fiche["donnees"], **e}

    # 1. Mesures, capitalisation en dollars, filtre de taille et de liquidité
    societes = []
    for t, r in base.items():
        if not r.get("annuel") or not r.get("cours"):
            continue
        prix = r["cours"][-1][1] / (r.get("centimes") or 1)
        fx_c = change.get(r["devise_cours"])
        cap = r["actions"] * prix * fx_c if r.get("actions") and fx_c else None
        echange = r["cours"][-1][2] if len(r["cours"][-1]) > 2 else 0
        liquidite = echange / (r.get("centimes") or 1) * fx_c / 1e6 if echange and fx_c else None
        if not r.get("surveillance") and ((cap or 0) < cfg_u["capitalisation_min_musd"] * 1e6 or (liquidite is not None and liquidite < cfg_u["volume_min_musd_jour"])):
            continue
        region = cfg_u["pays"].get(r["pays"], {}).get("region", "autre")
        s = {**r, "region": region, "capitalisation_usd": cap, "liquidite_musd": liquidite,
             "fx_comptes": change.get(r["devise_comptes"]), "resultat_net_ttm": (r.get("trimestre") or {}).get("resultat_net_ttm")}
        s["mesures"] = A.mesures(s)
        s["financier"] = A.type_financier(s.get("secteur_gics"), {"industry": r.get("industrie")}, r["annuel"][0])
        societes.append(s)
    # Une société cotée plusieurs fois n'apparaît qu'une fois (cotation la plus liquide)
    avant = len(societes)
    societes = A.regrouper_cotations(societes, U.cle_societe)
    if len(societes) < avant:
        LOG.info("Cotations multiples regroupées : %d cotations secondaires écartées", avant - len(societes))
    med = A.medianes_sectorielles([s for s in societes if s.get("secteur_gics")])

    # 2. Notes, textes, pépites
    entreprises, candidats = [], []
    for s in societes:
        m = s["mesures"]
        m.update(A.comparer(m, s.get("secteur_gics"), s["region"], med))
        n = A.notes(m, s["financier"])
        g = A.note_globale(n, config["ponderations_financieres"] if s["financier"] else config["ponderations"])
        if g["note"] is None:
            continue
        ind = A.indicateurs_affiches(m, n)
        conf = A.confiance(s, g, aujourdhui)
        a0 = s["annuel"][0]
        fx = s["fx_comptes"]
        montants = {}
        for cle, v in (("ca", a0.get("ca")), ("resultat_net", a0.get("resultat_net")), ("fcf", a0.get("fcf")), ("dette_nette", m.get("dette_nette"))):
            if v is not None:
                montants[cle] = {"local": v, "usd": v * fx if fx else None, "local_texte": A.montant_texte(v, s["devise_comptes"]),
                                 "usd_texte": A.montant_texte(v * fx, "$") if fx else "n. d."}
        secteur_gics = s.get("secteur_gics")
        nom_s, slug = U.GICS.get(secteur_gics, ("Non classé", "non-classe"))
        pays_j = pays_json.get(s["pays"])
        phase = zones.get(zone_par_pays.get(s["pays"], "monde"))
        ctx = A.ajustement_contexte(pays_j.get("note") if pays_j else None, phase, config["contexte"])
        crit = A.criteres_pepite(m, n, s["financier"], config["pepites"])
        verdict = A.verdict(ind, g["note"])
        off = s.get("officiel") or {}
        e = {
            "ticker": s["ticker"], "nom": s["nom"], "pays": s["pays"], "region": s["region"],
            "secteur": f"{s['pays']}-{slug}", "secteur_gics": secteur_gics, "secteur_nom": nom_s,
            "financier": s["financier"], "devise": s["devise_comptes"], "devise_cours": s["devise_cours"],
            "capitalisation_md": round(s["capitalisation_usd"] / 1e9, 2) if s.get("capitalisation_usd") else None,
            "liquidite_musd": round(s["liquidite_musd"], 1) if s.get("liquidite_musd") is not None else None,
            "note": g["note"], "niveau": A.niveau(g["note"]), "note_brute": g["brute"], "couverture": g["couverture"],
            "verdict": verdict, "confiance": conf, "indicateurs": ind,
            "fscore": m.get("fscore"), "alertes": m.get("alertes", []),
            "momentum": {"m3": m.get("momentum_3m"), "m6": m.get("momentum_6m"), "m12": m.get("momentum_12m")},
            "valorisation": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()
                             if k.startswith(("per", "ev_ebitda")) and not k.endswith("_negatif")},
            "contre_scenario": A.contre_scenario(m, ind), "montants": montants,
            "contexte": {"ajustement": ctx["points"], "details": ctx["details"], "note_ajustee": round(g["note"] + ctx["points"], 1),
                         "phase": phase, "note_pays": pays_j.get("note") if pays_j else None},
            "pepite": False, "qpr": False, "criteres_pepite": crit["criteres"],
            "holding": A.est_holding(s["nom"], s.get("industrie"), s["ticker"], config["pepites"]),
            "industrie": s.get("industrie"), "analystes": s.get("analystes"),
            "autres_cotations": s.get("autres_cotations", []),
            "sources": {
                "comptes": f"{s['source_officielle']} + Yahoo Finance" if s.get("source_officielle") else "Yahoo Finance (yfinance)",
                "officielle": s.get("source_officielle"), "verification": s.get("verification"),
                "rapport_officiel": off.get("url"), "exercice": a0.get("fin"),
                "date_cours": s["cours"][-1][0], "maj_comptes": s.get("maj_comptes"), "ancienne": bool(s.get("ancienne")),
                "composition": s.get("source_composition"),
            },
            "agents": {"entreprises": {"note": g["note"], "texte": verdict}},
            "etude_complete": A.etude(s["nom"], m, ind, montants, s["devise_comptes"]),
            "surveillance": s.get("surveillance", False),
        }
        p = precedentes.get(s["ticker"])
        if p and p.get("note") is not None and p["note"] != e["note"]:
            e["precedent"] = {"note": p["note"]}
        elif p and p.get("precedent"):
            e["precedent"] = p["precedent"]
        entreprises.append(e)
        if crit["ok"] and not e["holding"]:
            candidats.append((e, s, m, ind))

    # 3. Deux listes : « pépites » (300 M$ à 20 Md$, peu suivies) et « qualité à prix raisonnable » (grandes sociétés),
    #    classées par note ajustée selon le contexte, au plus N sociétés par secteur dans chaque liste
    cfg_p = config["pepites"]
    par_ticker = {e["ticker"]: (e, s, m, ind) for e, s, m, ind in candidats}
    resume_candidats = [{"ticker": e["ticker"], "cap": e["capitalisation_md"], "analystes": e["analystes"], "secteur": e["secteur_gics"],
                         "secteur_nom": e["secteur_nom"], "industrie": e["industrie"], "note_ajustee": e["contexte"]["note_ajustee"]}
                        for e, *_ in candidats]
    listes = A.selection_listes(resume_candidats, cfg_p)
    avertissements = A.concentration(resume_candidats, cfg_p)
    pepites = []
    for nom_liste, choisis in listes.items():
        for c in choisis:
            e, s, m, ind = par_ticker[c["ticker"]]
            e["pepite" if nom_liste == "pepites" else "qpr"] = True
            pj = pays_json.get(s["pays"])
            devise_3m = (((pj or {}).get("detail") or {}).get("devise_3m") or {}).get("valeur")
            e["revue_critique"] = A.revue_critique(s, m, ind, pj, devise_3m)
            pepites.append({"liste": nom_liste, "ticker": e["ticker"], "nom": e["nom"], "pays": e["pays"], "region": e["region"],
                            "secteur": e["secteur"], "secteur_gics": e["secteur_gics"], "secteur_nom": e["secteur_nom"],
                            "industrie": e["industrie"], "capitalisation_md": e["capitalisation_md"], "analystes": e["analystes"],
                            "note": e["note"], "contexte": e["contexte"], "verdict": e["verdict"], "confiance": e["confiance"]["niveau"],
                            "cles": {k: ind[k]["affichage"] for k in ("croissance_ca", "marge_op", "per_secteur", "roe", "fscore") if k in ind},
                            "autres_cotations": e["autres_cotations"], "revue_critique": e["revue_critique"]})

    # 4. Secteurs par pays (bulles des fiches pays)
    secteurs = {}
    for e in entreprises:
        sec = secteurs.setdefault(e["secteur"], {"id": e["secteur"], "pays": e["pays"], "nom": e["secteur_nom"], "secteur_gics": e["secteur_gics"],
                                                 "capitalisation_md": 0.0, "_m": [], "_n": [], "entreprises": []})
        cap = e["capitalisation_md"] or 0
        sec["capitalisation_md"] += cap
        if e["momentum"]["m3"] is not None:
            sec["_m"].append((e["momentum"]["m3"], cap))
        sec["_n"].append((e["note"], cap))
        sec["entreprises"].append((cap, e["ticker"]))
    anciens_sect = {s["id"]: s for s in ((lire_json(data / "secteurs.json") or {}).get("donnees") or [])}
    liste_secteurs = []
    for sec in secteurs.values():
        def moyenne_ponderee(v):
            tot = sum(w for _, w in v)
            return sum(x * w for x, w in v) / tot if tot else (statistics.fmean(x for x, _ in v) if v else None)
        note = round(moyenne_ponderee(sec["_n"]))
        s_out = {k: v for k, v in sec.items() if not k.startswith("_")}
        s_out.update({"capitalisation_md": round(sec["capitalisation_md"], 1), "momentum_3m": round(moyenne_ponderee(sec["_m"]) or 0, 1),
                      "note": note, "niveau": A.niveau(note), "entreprises": [t for _, t in sorted(sec["entreprises"], reverse=True)]})
        a = anciens_sect.get(sec["id"])
        if a and a.get("note") is not None and a["note"] != note and a.get("entreprises") and not a.get("fictif"):
            s_out["precedent"] = {"note": a["note"]}
        liste_secteurs.append(s_out)

    # 5. Signaux pour le chef d'orchestre
    signaux = []
    anciennes_pepites = {t for t, e in precedentes.items() if e.get("pepite") or e.get("qpr")}
    for e in entreprises:
        p = precedentes.get(e["ticker"])
        if (e["pepite"] or e["qpr"]) and e["ticker"] not in anciennes_pepites:
            signaux.append({"date": aujourdhui.isoformat(), "type": "nouvelle_pepite", "cle": e["ticker"], "importance": "moyenne",
                            "titre": f"{e['nom']} entre dans la liste « {'Pépites' if e['pepite'] else 'Qualité à prix raisonnable'} »",
                            "explication": e["verdict"], "source": e["sources"]["comptes"]})
        if p and e["alertes"] and not p.get("alertes"):
            signaux.append({"date": aujourdhui.isoformat(), "type": "alerte_comptable", "cle": e["ticker"], "importance": "moyenne",
                            "titre": f"{e['nom']} : {e['alertes'][0]['titre'].lower()}", "explication": e["alertes"][0]["texte"], "source": e["sources"]["comptes"]})
        if p and p.get("note") is not None and abs(e["note"] - p["note"]) >= 10:
            signaux.append({"date": aujourdhui.isoformat(), "type": "variation_de_note", "cle": e["ticker"], "importance": "faible",
                            "titre": f"{e['nom']} : note de {p['note']} à {e['note']}", "explication": e["verdict"], "source": e["sources"]["comptes"]})
        if p and (p.get("sources") or {}).get("exercice") != e["sources"]["exercice"]:
            signaux.append({"date": aujourdhui.isoformat(), "type": "nouveaux_comptes", "cle": e["ticker"], "importance": "faible",
                            "titre": f"{e['nom']} : comptes de l'exercice clos le {e['sources']['exercice']}", "explication": e["verdict"], "source": e["sources"]["comptes"]})
    for t in anciennes_pepites - {e["ticker"] for e in entreprises if e["pepite"] or e["qpr"]}:
        p = precedentes[t]
        signaux.append({"date": aujourdhui.isoformat(), "type": "sortie_pepite", "cle": t, "importance": "faible",
                        "titre": f"{p['nom']} sort des pépites candidates", "explication": "Au moins un critère n'est plus rempli.", "source": "agent entreprises"})
    fichier_sig = data / "signaux" / "entreprises.json"
    existants = (lire_json(fichier_sig) or {}).get("donnees") or []
    vus = {(s["type"], s["cle"], s["date"]) for s in existants}
    tous = sorted([*existants, *[s for s in signaux if (s["type"], s["cle"], s["date"]) not in vus]], key=lambda s: s["date"], reverse=True)
    tous = [s for s in tous if s["date"] >= (aujourdhui - timedelta(days=180)).isoformat()]

    # 6. Écritures : liste légère (globe, classements, recherche, comparateur) + une fiche détaillée par société
    entreprises.sort(key=lambda e: -(e["capitalisation_md"] or 0))
    dossier_fiches = data / "entreprises" / "fiches"
    dossier_fiches.mkdir(parents=True, exist_ok=True)
    attendues = set()
    for e in entreprises:
        nom_fichier = fichier_fiche(e["ticker"])
        attendues.add(nom_fichier)
        ecrire_json(dossier_fiches / nom_fichier, {"meta": {"genere_le": maintenant(), "source": "agent-entreprises"}, "donnees": e}, compact=True)
    for ancien_fichier in dossier_fiches.glob("*.json"):  # sociétés sorties de l'univers
        if ancien_fichier.name not in attendues:
            ancien_fichier.unlink()
    legeres = [leger(e) for e in entreprises]
    sources_utilisees = sorted({e["sources"]["comptes"] for e in entreprises})
    meta = dict(version_agent=VERSION_AGENT, mise_a_jour_precedente=(ancien or {}).get("meta", {}).get("genere_le") if precedentes else None,
                sources=sources_utilisees, nombre=len(entreprises), devise_capitalisation="USD",
                fiches="data/entreprises/fiches/<ticker>.json",
                medianes={f"{k[0]}|{k[1] or 'monde'}": v for k, v in med.items() if k[1] is None})
    ecrire_json(data / "entreprises.json", enveloppe(legeres, "agent-entreprises", fictif=False, **meta), compact=True)
    ecrire_json(data / "secteurs.json", enveloppe(sorted(liste_secteurs, key=lambda s: (s["pays"], -s["capitalisation_md"])), "agent-entreprises",
                                                  fictif=False, version_agent=VERSION_AGENT, classification="GICS (11 secteurs)", devise_capitalisation="USD"))
    ecrire_json(data / "pepites.json", enveloppe(pepites, "agent-entreprises", fictif=False, version_agent=VERSION_AGENT,
                                                 criteres={k: v for k, v in cfg_p.items() if not k.startswith("_")},
                                                 candidats=len(candidats), regions=config["regions"],
                                                 listes={"pepites": "Pépites", "qpr": "Qualité à prix raisonnable"},
                                                 nombres={k: len(v) for k, v in listes.items()},
                                                 avertissements=avertissements,
                                                 holdings_exclues=sum(1 for e in entreprises if e["holding"])))
    ecrire_json(fichier_sig, enveloppe(tous, "agent-entreprises", fictif=False, version_agent=VERSION_AGENT,
                                       description="Signaux candidats pour le chef d'orchestre (180 derniers jours)"))
    ecrire_json(data / "historique" / "entreprises" / f"{aujourdhui.isoformat()}.json",
                {"meta": {"genere_le": maintenant(), "source": "agent-entreprises", "version_agent": VERSION_AGENT},
                 "donnees": {e["ticker"]: {"note": e["note"], "pepite": e["pepite"], "qpr": e["qpr"], "cap": e["capitalisation_md"]} for e in entreprises}})
    recap = recap_markdown(aujourdhui, entreprises, pepites, signaux, etats_sources, len(candidats), cfg_p)
    (data / "recap").mkdir(parents=True, exist_ok=True)
    (data / "recap" / f"entreprises-{aujourdhui.isoformat()}.md").write_text(recap, encoding="utf-8")
    return {"entreprises": len(entreprises), "pepites": len(pepites), "candidats": len(candidats), "signaux": len(signaux),
            "secteurs": len(liste_secteurs), "officielles": sum(1 for e in entreprises if e["sources"]["officielle"]),
            "divergences": sum(1 for e in entreprises if (e["sources"]["verification"] or {}).get("statut") == "divergent")}


CHAMPS_LEGERS = ("ticker", "nom", "pays", "region", "secteur", "secteur_gics", "secteur_nom", "financier", "devise",
                 "capitalisation_md", "note", "niveau", "verdict", "indicateurs", "pepite", "qpr", "precedent", "surveillance",
                 "autres_cotations")


def fichier_fiche(ticker: str) -> str:
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in ticker) + ".json"


def leger(e: dict) -> dict:
    """Version légère d'une société pour data/entreprises.json (le détail est dans sa fiche)."""
    r = {k: e[k] for k in CHAMPS_LEGERS if k in e}
    r["confiance"] = {"niveau": e["confiance"]["niveau"]}
    r["contexte"] = {"ajustement": e["contexte"]["ajustement"], "note_ajustee": e["contexte"]["note_ajustee"]}
    r["fiche"] = f"data/entreprises/fiches/{fichier_fiche(e['ticker'])}"
    return r


def recap_markdown(jour, entreprises, pepites, signaux, etats, candidats, cfg_p) -> str:
    l = [f"# Agent entreprises — récapitulatif du {jour.strftime('%d/%m/%Y')}", "",
         f"- Sociétés analysées : {len(entreprises)}",
         f"- Comptes vérifiés avec une source officielle : {sum(1 for e in entreprises if e['sources']['officielle'])}",
         f"- Écarts entre source officielle et Yahoo : {sum(1 for e in entreprises if (e['sources']['verification'] or {}).get('statut') == 'divergent')}",
         f"- Sociétés remplissant tous les critères : {candidats} ; retenues : {sum(1 for p in pepites if p['liste'] == 'pepites')} pépites "
         f"(300 M$ à {cfg_p['cap_max_md']:g} Md$, peu suivies) et {sum(1 for p in pepites if p['liste'] == 'qpr')} en « qualité à prix raisonnable »"
         f" ; au plus {cfg_p['plafond_par_secteur']} par secteur", "",
         "## Pépites candidates", ""]
    l += [f"- [{'pépite' if p['liste'] == 'pepites' else 'QPR'}] {p['nom']} ({p['ticker']}, {p['pays']}) : {p['note']}/100, ajustement de contexte {p['contexte']['ajustement']:+} — {p['verdict']}" for p in pepites] or ["- aucune"]
    l += ["", "## Signaux du jour", ""] + ([f"- [{s['importance']}] {s['titre']}" for s in signaux] or ["- aucun"])
    l += ["", "## Sources", ""] + [f"- {k} : {v}" for k, v in etats.items()]
    return "\n".join(l) + "\n"


def enregistrer_sante(data: Path, etats_compo: dict, etats_rev: dict | None, f, publication: dict, base: dict, quand: datetime):
    sources, raisons = [], []
    for code, e in etats_compo.items():
        etat = {"ok": "ok", "ancienne": "périmée", "depart": "périmée", "échec": "échec"}[e["etat"]]
        sources.append({"nom": f"Composition {code} ({e.get('source') or 'aucune'})", "etat": etat, "detail": e.get("detail")})
        if etat != "ok":  # une composition utile qui n'a pas pu être relue rend l'agent « dégradé »
            raisons.append(f"Composition {code} : {e.get('source') or 'aucune liste'} (sources de composition en échec)")
    sec_actif = getattr(f.sec, "actif", False)
    # SEC_USER_AGENT est obligatoire : son absence est un échec (et non une clé facultative non configurée)
    sources.append({"nom": "SEC (XBRL companyfacts, submissions)", "etat": "ok" if sec_actif else "échec",
                    "detail": None if sec_actif else "secret SEC_USER_AGENT absent : comptes officiels américains non lus"})
    if not sec_actif:
        raisons.append("SEC : secret SEC_USER_AGENT absent")
    for nom, actif in (("EDINET (Japon)", getattr(getattr(f, "edinet", None), "actif", False)), ("DART (Corée)", getattr(getattr(f, "dart", None), "actif", False))):
        sources.append({"nom": nom, "etat": "ok" if actif else "non configurée", "detail": None if actif else "clé absente : source ignorée"})
    if etats_rev:
        total = etats_rev["ok"] + etats_rev["echec"]
        sources.append({"nom": "Yahoo Finance (comptes et cours)", "etat": "ok" if etats_rev["echec"] <= 0.1 * max(1, total) else "partielle",
                        "detail": f"{etats_rev['echec']} échec(s) sur {total}" if etats_rev["echec"] else None})
    indicateurs = {}
    for t, r in base.items():
        cle = f"Comptes · {r['pays']}"
        ind = indicateurs.setdefault(cle, {"valides": [], "configurees": []})
        ind["configurees"].append(t)
        if not r.get("ancienne"):
            ind["valides"].append(t)
    # Comptage par pays (et non par société) : un pays est dégradé si moins de 90 % de ses sociétés sont à jour
    resume = {k: {"valides": ["à jour"] if len(v["valides"]) >= 0.9 * len(v["configurees"]) else [], "configurees": ["à jour"]}
              for k, v in indicateurs.items()}
    chemin = data / "journal" / "agent-entreprises.json"
    journal_e = lire_json(chemin) or {"meta": {}, "donnees": []}
    officiels = {}
    for r in base.values():
        cle = (r.get("source_officielle") or "aucune").split(" ")[0]
        officiels[cle] = officiels.get(cle, 0) + 1
    us = [r for r in base.values() if r["pays"] == "US"]
    resume_officiel = {"par_source": officiels, "us_total": len(us),
                       "us_avec_sec": sum(1 for r in us if (r.get("source_officielle") or "").startswith("SEC")),
                       "us_en_file_sec": sum(1 for r in us if r.get("file_sec"))}
    journal_e["donnees"] = (journal_e.get("donnees", []) + [{"genere_le": maintenant(), "composition": etats_compo,
                                                              "comptes_officiels": resume_officiel,
                                                              "revision": {k: v for k, v in (etats_rev or {}).items() if k != "echecs"},
                                                              "echecs": (etats_rev or {}).get("echecs", [])[:50], "publication": publication}])[-60:]
    journal_e["meta"] = {**journal_e.get("meta", {}), "genere_le": maintenant(), "source": "agent-entreprises", "version_agent": VERSION_AGENT,
                         "description": "Composition, révision des comptes et publication, à chaque exécution"}
    ecrire_json(chemin, journal_e)
    precedent = (journal_e.get("meta") or {}).get("sante")
    bloc = sante.bloc_sante("entreprises", "Agent entreprises", 4, "agent-entreprises.yml", sources, quand, precedent, indicateurs=resume,
                            raisons_supplementaires=raisons)
    bloc["comptes_officiels"] = resume_officiel
    sante.enregistrer_sante(chemin, bloc, forcer=True)
    return bloc


# ------------------------------------------------------------------ point d'entrée

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent entreprises (sans IA).")
    ap.add_argument("--mode", choices=["complet", "quotidien", "assembler"], default="quotidien")
    ap.add_argument("--lot", help="lot de la révision complète (voir config.json, « lots »)")
    ap.add_argument("--sortie-lot", help="fichier où écrire le résultat d'un lot (révision complète en plusieurs jobs)")
    ap.add_argument("--lots", nargs="*", default=[], help="fichiers de lots à assembler")
    ap.add_argument("--echantillon", type=int, help="révision complète d'un échantillon de N sociétés, puis publication")
    ap.add_argument("--test", action="store_true", help="données de test enregistrées, sans réseau")
    ap.add_argument("--capturer", type=int, help="enregistre les N premières sociétés comme données de test")
    ap.add_argument("--data", default=str(RACINE / "data"))
    ap.add_argument("--date")
    args = ap.parse_args(argv)

    config = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    quand = datetime.combine(aujourdhui, datetime.min.time(), timezone.utc).replace(hour=22, minute=30) if args.date else datetime.now(timezone.utc)
    data = Path(args.data)
    f = FournisseurTest(DOSSIER / "tests" / "donnees") if args.test else Fournisseur(config)
    if args.capturer and not args.test:
        f = Capture(f, args.capturer)
    fichier_base = data / "entreprises" / "comptes.json"
    base = ((lire_json(fichier_base) or {}).get("societes")) or {}
    etats_compo, etats_rev = {}, None
    LOG.info("Agent entreprises %s — mode %s%s", VERSION_AGENT, args.mode, " (test)" if args.test else "")

    if args.mode == "complet":
        lot = config["lots"].get(args.lot) if args.lot else None
        pays = lot["pays"] if lot else None
        connu = lire_json(data / "entreprises" / "univers.json")
        depart = json.loads((DOSSIER / "univers_depart.json").read_text(encoding="utf-8"))["societes"]
        surveillance = U.lire_surveillance(RACINE / "config" / "surveillance.json")
        if args.test:
            depart = [s for s in depart if s["ticker"] in f.d["yahoo"]]
            surveillance = [s for s in surveillance if s["ticker"] in f.d["yahoo"]]
        liste, etats_compo = U.construire(f.composition, config, connu, depart, surveillance, pays)
        if args.echantillon:
            liste = echantillon(liste, args.echantillon, config)
        liste = tranche(liste, (lot or {}).get("tranche"))
        # Sociétés en file (comptes SEC manquants) traitées en premier
        liste.sort(key=lambda x: 0 if (base.get(x["ticker"]) or {}).get("file_sec") else 1)
        LOG.info("Révision complète : %d sociétés (%s)", len(liste), args.lot or ("échantillon" if args.echantillon else "toutes"))
        revus, etats_rev = reviser(f, liste, base, config)
        univers_lot = {"societes": [{k: s.get(k) for k in ("ticker", "nom", "pays", "secteur", "poids", "source_composition")} for s in liste
                                    if s.get("source_composition") != "liste de surveillance"]}
        if args.sortie_lot:
            ecrire_json(Path(args.sortie_lot), {"lot": args.lot, "date": aujourdhui.isoformat(), "composition": etats_compo,
                                                "revision": etats_rev, "univers": univers_lot, "societes": revus})
            LOG.info("Lot %s écrit : %d sociétés", args.lot, len(revus))
            return 0
        base.update(revus)
        _sauver_univers(data, univers_lot["societes"], etats_compo)
    elif args.mode == "assembler":
        etats_rev = {"ok": 0, "echec": 0, "officiel": 0, "echecs": []}
        for chemin in args.lots:
            lot = lire_json(Path(chemin))
            if not lot:
                LOG.error("Lot illisible : %s", chemin)
                continue
            base.update(lot["societes"])
            etats_compo.update(lot["composition"])
            for k in ("ok", "echec", "officiel"):
                etats_rev[k] += lot["revision"][k]
            etats_rev["echecs"] += lot["revision"]["echecs"]
            _sauver_univers(data, lot["univers"]["societes"], lot["composition"])
    else:
        if not base:
            LOG.error("Aucune base de comptes : lancer d'abord une révision complète.")
            return 1
        LOG.info("Mise à jour quotidienne : %s", mise_a_jour_quotidienne(f, base, config, aujourdhui))
        etats_compo = ((lire_json(data / "entreprises" / "univers.json") or {}).get("meta") or {}).get("etats", {})

    devises = {r.get("devise_cours") for r in base.values()} | {r.get("devise_comptes") for r in base.values()}
    change = f.yahoo.taux_change({d for d in devises if d})
    ecrire_json(fichier_base, compact=True, objet={"meta": {"genere_le": maintenant(), "source": "agent-entreprises", "version_agent": VERSION_AGENT,
                                        "description": "Comptes normalisés par société (base de travail de l'agent entreprises)"},
                               "societes": base})
    publication = publier(base, config, change, data, aujourdhui,
                          {k: f"{v['source'] or 'aucune'} ({v['nombre']})" for k, v in etats_compo.items()})
    bloc = enregistrer_sante(data, etats_compo, etats_rev, f, publication, base, quand)
    if isinstance(f, Capture):
        f.ecrire(DOSSIER / "tests" / "donnees")
    LOG.info("Publication : %s ; santé : %s", publication, "dégradé" if bloc["degrade"] else "OK")
    return 0


def _sauver_univers(data: Path, societes: list[dict], etats: dict) -> None:
    """Dernière liste connue, pays par pays : un pays dont la composition a échoué garde son ancienne liste."""
    chemin = data / "entreprises" / "univers.json"
    connu = lire_json(chemin) or {"meta": {}, "societes": []}
    pays_ok = {p for p, e in etats.items() if e["etat"] == "ok"}
    garder = [s for s in connu.get("societes", []) if s["pays"] not in pays_ok]
    nouveaux = [s for s in societes if s["pays"] in pays_ok]
    meta = {**connu.get("meta", {}), "genere_le": maintenant(), "etats": {**(connu.get("meta") or {}).get("etats", {}), **etats}}
    ecrire_json(chemin, {"meta": meta, "societes": garder + nouveaux})
