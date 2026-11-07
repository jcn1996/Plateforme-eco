"""
Agent matières premières (sans IA) : est-il pertinent de s'exposer à chaque grande matière première
sur un horizon de 3 à 12 mois ?

Étapes :
1. interroge les sources gratuites (Yahoo Finance : cours, courbe des prix à terme, parts des ETF ;
   CFTC ; EIA si la clé EIA_API_KEY existe ; USDA PSD et WASDE ; FRED) et lit les données des autres
   agents (data/macro.json, data/geopolitique.json, data/risque.json, data/entreprises.json) ;
   une source en panne n'arrête pas l'agent ;
2. calcule 8 sous-notes /100 par matière première, une note globale pondérée par famille, un verdict
   (« Surpondérer », « Neutre », « Sous-pondérer ») avec confiance, arguments, conditions d'invalidation ;
   puis une synthèse par famille ;
3. écrit data/matieres_premieres.json, data/signaux/matieres_premieres.json,
   data/historique/matieres_premieres/AAAA-MM-JJ.json (notes et relevés des ETF),
   data/recap/matieres-premieres-AAAA-MM-JJ.md et le journal data/journal/agent-matieres-premieres.json.

Règles de conduite : voir agents/matieres_premieres/regles.md.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..commun import sante
from ..commun.journal import journal
from ..commun.series import serie_graphique
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from ..pays.flux_etf import _periode, flux_quotidiens
from . import analyse as A
from .sources import Capture, FournisseurReel, FournisseurTest, contrats_suivants

LOG = journal("agent-matieres-premieres")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
FICHIER_JOURNAL = "agent-matieres-premieres.json"

NOMS_SOURCES = {
    "yahoo_cours": "Yahoo Finance via yfinance (contrat le plus proche, 10 ans)",
    "yahoo_courbes": "Yahoo Finance via yfinance (contrats des échéances suivantes)",
    "yahoo_etf": "Yahoo Finance via yfinance (parts en circulation et VL des ETF)",
    "cftc": "CFTC, Commitments of Traders (API publique Socrata)",
    "eia": "EIA, stocks hebdomadaires (API v2, clé EIA_API_KEY)",
    "usda_psd": "USDA, base PSD (fichiers CSV publics)",
    "usda_wasde": "USDA, rapport WASDE (fichier texte mensuel)",
    "fred_DFII10": "FRED, taux réel américain à 10 ans (DFII10)",
    "fred_DTWEXBGS": "FRED, indice dollar large (DTWEXBGS)",
    "fred_CPIAUCSL": "FRED, prix à la consommation américains (CPIAUCSL)",
}
# Pays producteurs non suivis par l'agent pays (affichés sans surbrillance sur le globe)
NOMS_PAYS = {"RU": "Russie", "GH": "Ghana", "PE": "Pérou", "BO": "Bolivie", "ZW": "Zimbabwe", "CD": "RD Congo", "KZ": "Kazakhstan",
             "BH": "Bahreïn", "NO": "Norvège", "NA": "Namibie", "UZ": "Ouzbékistan", "NE": "Niger", "IQ": "Irak", "IR": "Iran",
             "KW": "Koweït", "QA": "Qatar", "DZ": "Algérie", "UA": "Ukraine", "PK": "Pakistan", "PY": "Paraguay", "ET": "Éthiopie",
             "HN": "Honduras", "CI": "Côte d'Ivoire", "EC": "Équateur", "CM": "Cameroun", "NG": "Nigeria"}
DUREE_HISTORIQUE_ETF = 120
SANS_COURBE = {"uranium", "gaz_europe"}  # pas de contrats d'échéance sur Yahoo ni de rapport CFTC


# ------------------------------------------------------------------ collecte

def contrats(config: dict, aujourdhui: date) -> dict[str, list[dict]]:
    return {m["cle"]: contrats_suivants(m["racine"], m["place"], m["mois"], aujourdhui, config["courbe_contrats"], config["mois_codes"])
            for m in config["matieres"] if m.get("racine")}


def collecter(f, config: dict, aujourdhui: date):
    symboles = [m["symbole"] for m in config["matieres"]] + [config["dollar_yahoo"]]
    tous_contrats = [c["symbole"] for liste in contrats(config, aujourdhui).values() for c in liste]
    codes = sorted({m["cftc"] for m in config["matieres"] if m.get("cftc")})
    fr = config["fred"]
    appels = {
        "yahoo_cours": lambda: f.cours(symboles, aujourdhui),
        "yahoo_courbes": lambda: f.courbes(tous_contrats),
        "yahoo_etf": lambda: f.etf_parts(sorted(config["etf_flux"])),
        "cftc": lambda: f.cftc(codes, aujourdhui - timedelta(days=3 * 365 + 45)),
        "eia": lambda: f.eia({k: v["serie"] for k, v in config["eia"].items()}, aujourdhui - timedelta(days=6 * 365 + 30)),
        "usda_psd": lambda: f.psd(config["usda"]),
        "usda_wasde": lambda: f.wasde(config["usda"], aujourdhui),
        **{f"fred_{s}": (lambda s=s, j=j: f.fred(s, (aujourdhui - timedelta(days=j)).isoformat()))
           for s, j in ((fr["taux_reel"], 800), (fr["dollar"], 800), (fr["inflation"], 4100))},
    }
    res, etats, modes = {}, {}, {}
    for nom, appel in appels.items():
        try:
            r = appel()
            if nom.startswith("fred_"):
                r, modes[nom] = r
            res[nom] = r
            etats[nom] = "non configurée" if r is None and nom == "eia" else ("ok" if r else "vide")
            LOG.info("Source %s : %s", nom, etats[nom])
        except Exception as e:  # une source en panne : on continue
            res[nom] = None
            etats[nom] = f"erreur : {str(e)[:160]}"
            LOG.error("Source %s indisponible : %s", nom, str(e)[:200])
    return res, etats, modes


# ------------------------------------------------------------------ contexte des autres agents

def contexte(data: Path) -> dict:
    def donnees(nom):
        j = lire_json(data / nom) or {}
        return j.get("donnees")
    m = donnees("macro.json") or {}
    monde = next((z for z in (m.get("cycle") or {}).get("zones", []) if z.get("cle") == "monde"), None) or {}
    r = donnees("risque.json") or {}
    port = donnees("portefeuille.json") or {}
    return {
        "cycle": {"cli": (monde.get("croissance") or {}).get("cli"), "cli_3m": (monde.get("croissance") or {}).get("cli_3m"),
                  "phase": monde.get("phase"), "date": monde.get("date_donnees")} if monde else {},
        "geopolitique": donnees("geopolitique.json"),
        "palier": (r.get("mondial") or {}).get("palier"),
        "entreprises": {e["ticker"]: e for e in (donnees("entreprises.json") or []) if isinstance(e, dict) and e.get("ticker")},
        "portefeuille": {p.get("ticker") for p in (port.get("positions") or []) if p.get("ticker")},
    }


def tickers_surveillance(chemin: Path) -> set[str]:
    return {s.get("ticker") for s in ((lire_json(chemin) or {}).get("societes") or []) if s.get("ticker")}


# ------------------------------------------------------------------ flux des ETF (historique accumulé)

def flux_etf(dossier_hist: Path, releves: dict | None, config: dict, aujourdhui: date) -> tuple[dict, dict]:
    """Séries des parts (historique des exécutions précédentes + relevé du jour) et périodes 1 et 3 mois.
    Renvoie ({etf: indicateur}, {etf: relevé du jour à enregistrer})."""
    limite = (aujourdhui - timedelta(days=DUREE_HISTORIQUE_ETF)).isoformat()
    series: dict[str, dict[str, dict]] = {}
    for chemin in sorted(Path(dossier_hist).glob("????-??-??.json")):
        if chemin.stem < limite:
            continue
        for etf, r in (((lire_json(chemin) or {}).get("donnees") or {}).get("etf") or {}).items():
            if r.get("date"):
                series.setdefault(etf, {})[r["date"]] = r
    du_jour = {}
    for etf, r in (releves or {}).items():
        if (aujourdhui - A.jour(r["date"])).days > 7 or not r.get("parts") or not r.get("vl"):
            continue
        # L'actif total publié par Yahoo est souvent en retard de plusieurs jours : l'encours retenu est parts × VL
        du_jour[etf] = {"date": r["date"], "parts": r["parts"], "vl": r["vl"], "encours": round(r["parts"] * r["vl"])}
        series.setdefault(etf, {})[r["date"]] = du_jour[etf]
    res = {}
    for etf, cfg in config["etf_flux"].items():
        serie = [series.get(etf, {})[d] for d in sorted(series.get(etf, {}))]
        if not serie:
            continue
        q = flux_quotidiens(serie)
        fin = A.jour(serie[-1]["date"])
        periodes = {k: {**_periode(serie, q, fin, j), "fin": serie[-1]["date"]} for k, j in (("1m", 30), ("3m", 91))}
        res[etf] = {"nom": cfg["nom"], "encours": serie[-1]["parts"] * serie[-1]["vl"], "date": serie[-1]["date"], "periodes": periodes,
                    "releves": len(serie)}
    return res, du_jour


# ------------------------------------------------------------------ analyse d'une matière première

def analyser(m: dict, res: dict, ctx: dict, flux_par_etf: dict, cfg: dict, courbes: dict, aujourdhui: date, precedent: dict | None,
             pays_suivis: dict, surveillance: set[str]) -> dict:
    seuils = cfg["seuils"]
    famille = cfg["familles"][m["famille"]]
    serie = ((res.get("yahoo_cours") or {}).get(m["symbole"])) or []
    if serie and (aujourdhui - A.jour(serie[-1][0])).days > seuils["fraicheur_cours_jours"]:
        LOG.warning("%s : dernier cours du %s, trop ancien", m["nom"], serie[-1][0])
    front = serie[-1][1] if serie else None
    sous: dict[str, dict | None] = {k: None for k in cfg["sous_notes"]}
    sous["tendance"] = A.tendance(serie)
    if m.get("racine") and res.get("yahoo_courbes"):
        sous["courbe"] = A.courbe(courbes.get(m["cle"], []), res["yahoo_courbes"], front, seuils["structure_pct_an"])
    verification_stocks = None
    if m.get("stocks") and res.get("eia"):
        sous["stocks"] = A.stocks_eia(res["eia"], m["stocks"], cfg["eia"], seuils)
    elif m.get("usda"):
        sous["stocks"], verification_stocks = A.stocks_usda(m["usda"], res.get("usda_psd"), res.get("usda_wasde"), seuils)
    if m.get("cftc") and res.get("cftc"):
        lignes = res["cftc"].get(m["cftc"]) or []
        if lignes and (aujourdhui - A.jour(sorted(l["date"] for l in lignes)[-1])).days <= seuils["fraicheur_cftc_jours"]:
            sous["positionnement"] = A.positionnement(lignes, aujourdhui, seuils)
    fr = cfg["fred"]
    sous["macro"] = A.macro(m["macro"], {"taux_reel": res.get(f"fred_{fr['taux_reel']}"), "dollar": res.get(f"fred_{fr['dollar']}"),
                                         "cycle": ctx["cycle"], "palier": ctx["palier"]})
    sous["geopolitique"] = A.geopolitique(m, ctx["geopolitique"], ctx["palier"], aujourdhui, seuils["geopolitique_jours"])
    if m.get("flux"):
        sous["flux"] = A.flux({e: flux_par_etf[e] for e in m["flux"] if e in flux_par_etf})
    sous["niveau"] = A.niveau(serie, res.get(f"fred_{fr['inflation']}"))

    ancien = {x["cle"]: x for x in (precedent or {}).get("matieres", [])}.get(m["cle"]) or {}
    note = A.note_globale(sous, famille["ponderations"])
    v, fav, defav = A.verdict(note, sous, cfg["verdicts"], ancien.get("verdict"))
    conf = A.confiance(sous, note, bool(m.get("indirect")))
    pour, contre = A.arguments(sous, cfg["sous_notes"])
    courbe = sous.get("courbe")

    supports = []
    for s in m.get("supports", []):
        x = dict(s)
        if "contrats à terme" in s["type"] and courbe:
            r = courbe["roulement_pct_an"]
            x["cout_roulement"] = (f"courbe en contango : coût de roulement estimé à {A.fr(abs(r), 1)} % par an" if r < 0
                                   else f"courbe en backwardation : gain de roulement estimé à {A.fr(r, 1)} % par an")
        supports.append(x)

    societes = []
    for t in m.get("societes", []):
        e = ctx["entreprises"].get(t)
        if not e:
            continue
        societes.append({"ticker": t, "nom": e.get("nom"), "pays": e.get("pays"), "note": e.get("note"),
                         "recommandation": (e.get("recommandation") or {}).get("n"), "fiche": e.get("fiche"),
                         "deja_detenue": t in ctx["portefeuille"] or t in surveillance})
    deja = [s["nom"] for s in societes if s["deja_detenue"]]
    producteurs = [{"code": c, "rang": r, "nom": pays_suivis.get(c) or NOMS_PAYS.get(c, c), "suivi": c in pays_suivis}
                   for c, r in m.get("producteurs", [])]

    sources = [{"sous_note": cfg["sous_notes"][k], "source": s["source"], "date": s.get("date")} for k, s in sous.items() if s]
    if verification_stocks:
        sous["stocks"]["verification"] = verification_stocks
    r1 = (sous["tendance"] or {}).get("variation_1m")
    r12 = (sous["tendance"] or {}).get("variation_12m")
    return {
        "cle": m["cle"], "nom": m["nom"], "famille": m["famille"], "symbole": m["symbole"], "unite": m.get("unite"),
        "indirect": bool(m.get("indirect")), "mention": m.get("mention"),
        "cours": front, "date_cours": serie[-1][0] if serie else None, "variation_1m": r1, "variation_12m": r12,
        "serie": serie_graphique(serie, hebdo=True),
        "note": note, "verdict": v, "horizon": cfg["horizon"], "confiance": conf,
        "signaux_favorables": [cfg["sous_notes"][k] for k in fav], "signaux_defavorables": [cfg["sous_notes"][k] for k in defav],
        "sous_notes": sous, "arguments_pour": pour, "arguments_contre": contre,
        "ce_qui_pourrait_me_donner_tort": A.donner_tort(v, m, sous, contre, pour),
        "invalidations": A.invalidations(v, m, sous, serie, seuils),
        "supports": supports, "societes": societes,
        "double_exposition": (f"Vous suivez ou détenez déjà {', '.join(deja)} : s'exposer aussi à la matière première "
                              f"concentrerait le même risque.") if deja else None,
        "producteurs": producteurs, "note_producteurs": m.get("note_producteurs"),
        "sources": sources,
        "precedent": {"note": ancien.get("note"), "verdict": ancien.get("verdict")} if ancien else None,
    }


def familles(matieres: list[dict], cfg: dict) -> list[dict]:
    res = []
    for cle, f in cfg["familles"].items():
        membres = [m for m in matieres if m["famille"] == cle and m["note"] is not None]
        notes = [m["note"] for m in membres]
        v = A.verdict_famille(notes, [m["verdict"] for m in membres], cfg["verdicts"])
        tri = sorted(membres, key=lambda m: m["note"], reverse=True)
        texte = (f"{f['nom']} : note moyenne {A.fr(sum(notes) / len(notes), 0)}/100 sur {len(notes)} matières premières"
                 + (f" ; la plus favorable : {tri[0]['nom']} ({A.fr(tri[0]['note'], 0)}), la moins favorable : {tri[-1]['nom']} ({A.fr(tri[-1]['note'], 0)})" if len(tri) > 1 else "")
                 + ".") if notes else f"{f['nom']} : données insuffisantes."
        res.append({"cle": cle, "nom": f["nom"], "note": round(sum(notes) / len(notes), 1) if notes else None, "verdict": v,
                    "texte": texte, "matieres": [m["cle"] for m in membres],
                    "repartition": {x: [m["verdict"] for m in membres].count(x) for x in A.VERDICTS}})
    return res


# ------------------------------------------------------------------ publications (rythmes hebdomadaires et mensuels)

def publications(res: dict, precedent: dict | None, cfg: dict) -> list[dict]:
    anciennes = {p["source"]: p for p in (precedent or {}).get("publications", [])}
    dates = {
        "EIA, stocks pétroliers hebdomadaires": max((s[-1][0] for k, s in (res.get("eia") or {}).items() if k != "gaz" and s), default=None),
        "EIA, stocks de gaz naturel": ((res.get("eia") or {}).get("gaz") or [[None]])[-1][0],
        "CFTC, Commitments of Traders": max((l["date"] for v in (res.get("cftc") or {}).values() for l in v), default=None),
        "USDA, WASDE et base PSD": (res.get("usda_wasde") or res.get("usda_psd") or {}).get("publication"),
    }
    liste = []
    for p in cfg["publications"]:
        d = dates.get(p["source"]) or (anciennes.get(p["source"]) or {}).get("derniere_donnee")
        liste.append({**p, "derniere_donnee": d, "nouvelle": bool(d and d != (anciennes.get(p["source"]) or {}).get("derniere_donnee"))})
    return liste


# ------------------------------------------------------------------ écritures

def recap_markdown(jour: date, d: dict, nouveaux: list[dict], etats: dict) -> str:
    l = [f"# Agent matières premières — récapitulatif du {A.date_fr(jour.isoformat())}", "", f"Horizon : {d['horizon']}.", "", "## Synthèse par famille", ""]
    l += [f"- **{f['nom']}** : « {f['verdict']} » — {f['texte']}" for f in d["familles"]]
    l += ["", "## Verdicts", ""]
    for m in d["matieres"]:
        p = m.get("precedent") or {}
        change = f" (précédent : « {p['verdict']} »)" if p.get("verdict") and p["verdict"] != m["verdict"] else ""
        l.append(f"- {m['nom']} : « {m['verdict']} »{change}, note {A.fr(m['note'], 0)}/100, confiance {m['confiance']}")
    l += ["", "## Publications prises en compte", ""]
    l += [f"- {p['source']} : " + (f"donnée du {A.date_fr(p['derniere_donnee'])}{' (nouvelle)' if p['nouvelle'] else ''}" if p["derniere_donnee"]
                                     else "aucune donnée (source indisponible ou non configurée)") for p in d["publications"]]
    l += ["", "## Signaux détectés aujourd'hui", ""] + ([f"- [{s['importance']}] {s['titre']}" for s in nouveaux] or ["- aucun"])
    erreurs = [k for k, v in etats.items() if v not in ("ok", "non configurée")]
    l += ["", "## Sources en échec", ""] + ([f"- {NOMS_SOURCES.get(k, k)} : {etats[k]}" for k in erreurs] or ["- aucune"])
    if etats.get("eia") == "non configurée":
        l += ["", "La source EIA est ignorée : secret EIA_API_KEY absent (stocks de pétrole et de gaz non notés)."]
    return "\n".join(l) + "\n"


def sources_sante(etats: dict, modes: dict) -> list[dict]:
    res = []
    for nom, etat in etats.items():
        n = NOMS_SOURCES.get(nom, nom)
        if etat == "ok":
            res.append({"nom": n, "etat": "ok", "detail": modes.get(nom)})
        elif etat == "non configurée":
            res.append({"nom": n, "etat": "non configurée", "detail": "secret EIA_API_KEY absent : source ignorée"})
        elif etat == "vide":
            res.append({"nom": n, "etat": "partielle", "detail": "aucune donnée reçue"})
        else:
            res.append({"nom": n, "etat": "échec", "detail": etat.removeprefix("erreur : ")})
    return res


def indicateurs_sante(matieres: list[dict]) -> dict:
    ind = {}
    for m in matieres:
        s = m["sous_notes"]
        ind[f"Cours · {m['nom']}"] = {"valides": ["Yahoo"] if s.get("tendance") else [], "configurees": ["Yahoo"]}
        if m["cle"] not in SANS_COURBE:
            ind[f"Courbe · {m['nom']}"] = {"valides": ["Yahoo contrats"] if s.get("courbe") else [], "configurees": ["Yahoo contrats"]}
        if m["cle"] not in SANS_COURBE:  # ni contrat coté sur Yahoo, ni rapport CFTC
            ind[f"Positionnement · {m['nom']}"] = {"valides": ["CFTC"] if s.get("positionnement") else [], "configurees": ["CFTC"]}
        st = s.get("stocks")
        if st and st.get("type") == "usda":
            valides = {"concordant": ["PSD", "WASDE"], "divergent": ["PSD", "WASDE"]}.get(st.get("verification"),
                                                                                      ["WASDE" if "WASDE" in st["source"] else "PSD"])
            ind[f"Stocks · {m['nom']}"] = {"valides": valides, "configurees": ["PSD", "WASDE"]}
        elif st:
            ind[f"Stocks · {m['nom']}"] = {"valides": ["EIA"], "configurees": ["EIA"]}
    return ind


def ecrire_signaux(chemin: Path, nouveaux: list[dict], aujourdhui: date) -> list[dict]:
    existants = (lire_json(chemin) or {}).get("donnees") or []
    vus = {(s["type"], s["cle"], s["date"]) for s in existants}
    tous = existants + [s for s in nouveaux if (s["type"], s["cle"], s["date"]) not in vus]
    limite = (aujourdhui - timedelta(days=180)).isoformat()
    tous = sorted((s for s in tous if s["date"] >= limite), key=lambda s: s["date"], reverse=True)
    ecrire_json(chemin, enveloppe(tous, "agent-matieres-premieres", fictif=False, version_agent=VERSION_AGENT,
                                  description="Signaux candidats pour le chef d'orchestre et le contradicteur (180 derniers jours)"))
    return tous


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent matières premières : faut-il s'exposer à chaque matière première sur 3 à 12 mois ? (sans IA)")
    ap.add_argument("--test", action="store_true", help="données de test (agents/matieres_premieres/tests/donnees), sans réseau")
    ap.add_argument("--donnees-test", help="dossier des données de test (par défaut tests/donnees)")
    ap.add_argument("--capturer", action="store_true", help="enregistre les réponses réelles comme données de test")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier data/ (lecture des autres agents et écriture)")
    ap.add_argument("--surveillance", default=str(RACINE / "config" / "surveillance.json"), help="liste de surveillance (double exposition)")
    ap.add_argument("--date", help="date du jour (AAAA-MM-JJ), utile pour les tests")
    args = ap.parse_args(argv)

    cfg = json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))
    pays_suivis = {k: v["nom"] for k, v in json.loads((RACINE / "agents" / "pays" / "config.json").read_text(encoding="utf-8"))["pays"].items()}
    aujourdhui = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    data = Path(args.data)
    dossier_test = Path(args.donnees_test) if args.donnees_test else DOSSIER / "tests" / "donnees"
    if args.test:
        f = FournisseurTest(dossier_test)
    else:
        f = FournisseurReel(RACINE / "agents" / ".cache")
        if args.capturer:
            f = Capture(f, dossier_test)
    LOG.info("Agent matières premières %s — %s", VERSION_AGENT, "données de test" if args.test else "sources réelles")

    res, etats, modes = collecter(f, cfg, aujourdhui)
    if not res.get("yahoo_cours"):
        LOG.error("Cours Yahoo Finance indisponibles : fichiers inchangés.")
        return 1

    ancien = lire_json(data / "matieres_premieres.json")
    precedent = (ancien or {}).get("donnees") if ancien and (ancien.get("meta") or {}).get("fictif") is False else None
    ctx = contexte(data)
    surveillance = tickers_surveillance(Path(args.surveillance))
    dossier_hist = data / "historique" / "matieres_premieres"
    flux_par_etf, releves_du_jour = flux_etf(dossier_hist, res.get("yahoo_etf"), cfg, aujourdhui)
    courbes = contrats(cfg, aujourdhui)

    matieres = [analyser(m, res, ctx, flux_par_etf, cfg, courbes, aujourdhui, precedent, pays_suivis, surveillance) for m in cfg["matieres"]]
    donnees = {
        "date": aujourdhui.isoformat(), "horizon": cfg["horizon"],
        "familles": familles(matieres, cfg), "matieres": matieres,
        "publications": publications(res, precedent, cfg),
        "flux_etf": flux_par_etf,
        "contexte": {"cycle": ctx["cycle"], "palier_risque": ctx["palier"]},
        "avertissement": "Analyse factuelle à titre informatif, sans conseil d'investissement ; les supports cités sont des exemples de types de produits.",
        "methode": ("8 sous-notes /100 (au-dessus de 50 : favorable à une exposition) ; note globale pondérée par famille ; "
                    f"« Surpondérer » à partir de {cfg['verdicts']['surponderer']} et « Sous-pondérer » jusqu'à {cfg['verdicts']['sous_ponderer']}, "
                    f"avec au moins {cfg['verdicts']['signaux_concordants_min']} sous-notes concordantes ; sinon « Neutre »."),
    }
    textes = [t for m in matieres for t in m["arguments_pour"] + m["arguments_contre"] + [m["ce_qui_pourrait_me_donner_tort"]] + m["invalidations"]]
    if not A.conformes(textes + [x["texte"] for x in donnees["familles"]]):
        LOG.error("Un texte contient un mot interdit : vérifier les règles de rédaction.")

    nouveaux = A.signaux(precedent, donnees, aujourdhui, cfg["seuils"])
    ecrire_signaux(data / "signaux" / "matieres_premieres.json", nouveaux, aujourdhui)
    objet = enveloppe(donnees, "agent-matieres-premieres", fictif=False, version_agent=VERSION_AGENT,
                      mise_a_jour_precedente=(ancien or {}).get("meta", {}).get("genere_le") if precedent else None,
                      etat_des_sources={NOMS_SOURCES.get(k, k): v for k, v in etats.items()})
    ecrire_json(data / "matieres_premieres.json", objet)
    ecrire_json(dossier_hist / f"{aujourdhui.isoformat()}.json", {
        "meta": {"genere_le": objet["meta"]["genere_le"], "source": "agent-matieres-premieres", "version_agent": VERSION_AGENT,
                 "description": "Notes et verdicts du jour ; « etf » : parts en circulation et VL des ETF de matières premières (historique des flux)"},
        "donnees": {"notes": {m["cle"]: {"note": m["note"], "verdict": m["verdict"], "confiance": m["confiance"], "cours": m["cours"],
                                         "sous_notes": {k: (s or {}).get("note") for k, s in m["sous_notes"].items()}} for m in matieres},
                    "familles": {x["cle"]: {"note": x["note"], "verdict": x["verdict"]} for x in donnees["familles"]},
                    "etf": releves_du_jour}})
    (data / "recap").mkdir(parents=True, exist_ok=True)
    (data / "recap" / f"matieres-premieres-{aujourdhui.isoformat()}.md").write_text(recap_markdown(aujourdhui, donnees, nouveaux, etats), encoding="utf-8")

    chemin_journal = data / "journal" / FICHIER_JOURNAL
    j = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    j["donnees"] = (j.get("donnees", []) + [{"genere_le": objet["meta"]["genere_le"], "etat_des_sources": etats,
                                             "signaux": [s["titre"] for s in nouveaux]}])[-90:]
    j["meta"] = {**j.get("meta", {}), "genere_le": objet["meta"]["genere_le"], "source": "agent-matieres-premieres",
                 "version_agent": VERSION_AGENT, "description": "État des sources et signaux, à chaque exécution"}
    ecrire_json(chemin_journal, j)
    maintenant = (datetime.combine(aujourdhui, datetime.min.time(), timezone.utc).replace(hour=22, minute=20) if args.date
                  else datetime.now(timezone.utc))
    bloc = sante.bloc_sante("matieres-premieres", "Agent matières premières", 8, "agent-matieres-premieres.yml", sources_sante(etats, modes),
                            maintenant, (j.get("meta") or {}).get("sante"), indicateurs=indicateurs_sante(matieres))
    sante.enregistrer_sante(chemin_journal, bloc, forcer=True)

    LOG.info("Verdicts : %s", ", ".join(f"{m['nom']} « {m['verdict']} » ({A.fr(m['note'], 0)})" for m in matieres))
    LOG.info("Signaux détectés : %d ; santé : %d/%d sources, %s", len(nouveaux), bloc["sources_ok"], bloc["sources_total"],
             "dégradé" if bloc["degrade"] else "aucun indicateur dégradé")
    return 0
