"""
Rôle de contradicteur : pour chaque signal encore valide des autres agents (data/signaux/*.json),
l'agent risque cherche les données propres à ce signal qui le contredisent ou le nuancent.

1. Validité : un signal n'est examiné que s'il a moins de `fenetre_jours` jours, une importance
   moyenne ou forte, et s'il est toujours présent dans les données de l'agent émetteur
   (pépite toujours dans la liste, alerte comptable toujours dans la fiche, phase toujours en
   cours, événement toujours suivi…). Les revues des signaux qui ne sont plus valides sont
   retirées de data/signaux/revues.json.
2. Objections spécifiques :
   - entreprise : ses propres risques (valorisation, dette, devise de cotation, risque du pays,
     sensibilité de son secteur, signaux d'alerte, momentum) ; pour une alerte, ce qui la nuance ;
   - pays : ses vulnérabilités (ou, pour un signal de risque, ce qui le nuance : réaction de son
     marché, solidité de ses comptes) ;
   - zone (agent macro) : la robustesse du changement de phase dans les données de la zone ;
   - banque centrale : cohérence du mouvement avec la tendance sur 12 mois.
   Le contexte mondial n'est ajouté qu'en complément, en une phrase au plus.
3. Sans objection spécifique, la revue l'écrit (« Pas d'objection spécifique. ») et propose
   « maintenir ».

Chaque objection est chiffrée et cite ses faits numérotés (F1, F2…), chacun avec sa source.
Ajustement proposé : « maintenir », « abaisser » ou « signal fragile ». Si Gemini est disponible
(budget propre à l'agent risque), il reformule l'objection à partir des mêmes faits ; une réponse
qui cite un chiffre absent des faits, ne cite aucun fait propre au signal ou invente une objection
là où les règles n'en trouvent pas est rejetée (version par règles).
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path

from ..commun.journal import journal
from ..commun.sortie import lire_json
from . import calculs as C

LOG = journal("agent-risque")
AJUSTEMENTS = ("maintenir", "abaisser", "signal fragile")
VERSION_REGLES = 2  # revues d'une version antérieure : refaites
PAS_D_OBJECTION = "Pas d'objection spécifique."
NEGATIFS = re.compile(r"ralentissement|récession|recession|contraction|stagflation|repli", re.I)
SECTEURS_CYCLIQUES = {"Energy": "énergie", "Materials": "matériaux", "Industrials": "industrie", "Consumer Discretionary": "consommation discrétionnaire",
                      "Financials": "finance", "Real Estate": "immobilier"}


def id_signal(fichier: str, s: dict) -> str:
    return f"{fichier.removesuffix('.json')}|{s.get('type')}|{s.get('cle')}|{s.get('date')}"


def lire_signaux(dossier, config: dict, aujourdhui=None) -> dict[str, list[dict]]:
    """{fichier: [signaux]} des autres agents (risque.json et revues.json exclus)."""
    cfg = config["contradicteur"]
    res = {}
    for chemin in sorted(dossier.glob("*.json")) if dossier.exists() else []:
        if chemin.name in cfg["ignores"]:
            continue
        res[chemin.name] = ((lire_json(chemin) or {}).get("donnees") or [])
    return res


# ------------------------------------------------------------------ données des agents émetteurs

class Sources:
    """Données des autres agents, lues dans data/ à la demande (validité et objections)."""

    def __init__(self, data: Path):
        self.data = Path(data)
        self._cache = {}

    def _json(self, nom):
        if nom not in self._cache:
            self._cache[nom] = (lire_json(self.data / nom) or {}).get("donnees")
        return self._cache[nom]

    def entreprises(self) -> dict | None:
        d = self._json("entreprises.json")
        return None if d is None else {e["ticker"]: e for e in d if isinstance(e, dict) and e.get("ticker")}

    def fiche(self, e: dict) -> dict:
        chemin = (e or {}).get("fiche")
        if not chemin:
            return {}
        cle = "fiche:" + chemin
        if cle not in self._cache:
            self._cache[cle] = (lire_json(self.data / chemin.removeprefix("data/")) or {}).get("donnees") or {}
        return self._cache[cle]

    def pepites(self) -> set | None:
        d = self._json("pepites.json")
        return None if d is None else {c.get("ticker") for c in d if isinstance(c, dict)}

    def macro(self) -> dict | None:
        return self._json("macro.json")

    def geopolitique(self) -> dict | None:
        return self._json("geopolitique.json")

    def matieres_premieres(self) -> dict | None:
        d = self._json("matieres_premieres.json")
        return None if d is None else {m["cle"]: m for m in d.get("matieres", []) if isinstance(m, dict)}

    def pays(self) -> dict | None:
        d = self._json("pays.json")
        return None if d is None else {p["code"]: p for p in d if isinstance(p, dict)}


def _phase_cible(titre: str) -> str | None:
    m = re.search(r"à «\s*([^»]+?)\s*»\s*$", titre or "")
    return m.group(1) if m else None


def _nom_alerte(titre: str) -> str:
    return (titre or "").split(" : ", 1)[-1].strip().lower()


def valide(fichier: str, s: dict, src: Sources, config: dict, aujourdhui: str) -> tuple[bool, str]:
    """(valide, raison). Moins de `fenetre_jours` jours et toujours présent chez l'agent émetteur.
    Quand les données de l'émetteur sont absentes, seul l'âge est vérifié."""
    cfg = config["contradicteur"]
    if s.get("importance") not in cfg["importances"]:
        return False, "importance faible"
    try:
        age = (C.jour(aujourdhui) - C.jour(s.get("date"))).days
    except (TypeError, ValueError):
        return False, "date illisible"
    if not 0 <= age < cfg["fenetre_jours"]:
        return False, f"signal de plus de {cfg['fenetre_jours']} jours"
    agent, t, cle = fichier.removesuffix(".json"), s.get("type"), s.get("cle")
    if agent == "entreprises":
        ents = src.entreprises()
        if ents is None:
            return True, "données de l'agent entreprises absentes : âge seul vérifié"
        e = ents.get(cle)
        if e is None:
            return False, "entreprise absente des données de l'agent entreprises"
        if t == "nouvelle_pepite":
            liste = src.pepites()
            dedans = (cle in liste) if liste is not None else bool(e.get("pepite") or e.get("qpr"))
            return (True, "toujours dans la liste") if dedans else (False, "n'est plus dans la liste des pépites")
        if t == "alerte_comptable":
            alertes = src.fiche(e).get("alertes")
            if alertes is None:
                return True, "fiche absente : âge seul vérifié"
            nom = _nom_alerte(s.get("titre"))
            if any((a.get("titre") or "").strip().lower() == nom for a in alertes):
                return True, "alerte toujours présente"
            return False, "alerte absente de la fiche actuelle"
        return True, "entreprise toujours suivie"
    if agent == "macro":
        m = src.macro()
        if m is None:
            return True, "données de l'agent macro absentes : âge seul vérifié"
        if t == "changement_de_phase":
            zone = next((z for z in (m.get("cycle") or {}).get("zones", []) if z.get("cle") == cle), None)
            cible = _phase_cible(s.get("titre"))
            if zone is None:
                return False, "zone absente des données de l'agent macro"
            if cible and zone.get("phase") != cible:
                return False, f"phase actuelle « {zone.get('phase')} », plus « {cible} »"
            return True, "phase toujours en cours"
        if t == "mouvement_banque_centrale":
            bc = next((b for b in m.get("banques_centrales", []) if b.get("cle") == cle), None)
            if bc is None:
                return False, "banque centrale absente des données de l'agent macro"
            d = (bc.get("dernier_mouvement") or {}).get("date")
            if d and abs((C.jour(d) - C.jour(s["date"])).days) > 3:
                return False, "un mouvement plus récent a eu lieu"
            return True, "mouvement toujours le dernier"
        return True, "âge seul vérifié"
    if agent == "geopolitique":
        g = src.geopolitique()
        if g is None:
            return True, "données de l'agent géopolitique absentes : âge seul vérifié"
        if t in ("evenement_grave", "mesure_officielle"):
            ids = set()
            for e in g.get("evenements", []):
                ids.add(e.get("id"))
                ids.update(c.get("id") for c in e.get("chronologie") or [])
            ids.update(i.removeprefix("theme-") for i in list(ids) if i)
            return (True, "événement toujours suivi") if (cle in ids or str(cle).removeprefix("theme-") in ids) else (False, "événement plus suivi par l'agent géopolitique")
        if t == "hausse_score":
            p = (g.get("pays") or {}).get(cle) or {}
            v = p.get("variation_7j")
            return (True, "hausse toujours visible") if v is not None and v > 0 else (False, "le score géopolitique ne monte plus")
        return True, "âge seul vérifié"
    if agent == "matieres_premieres":
        mp = src.matieres_premieres()
        if mp is None:
            return True, "données de l'agent matières premières absentes : âge seul vérifié"
        m = mp.get(str(cle).split("-")[0] if t == "choc_stocks" else cle)
        if m is None:
            return False, "matière première absente des données de l'agent"
        if t == "changement_verdict":
            cible = _phase_cible(s.get("titre"))
            if cible and m.get("verdict") != cible:
                return False, f"verdict actuel « {m.get('verdict')} », plus « {cible} »"
            return True, "verdict toujours en vigueur"
        return True, "matière première toujours suivie"
    if agent == "inities":
        ini = src._json("inities.json")
        if ini is None:
            return True, "données de l'agent initiés absentes : âge seul vérifié"
        soc = (ini.get("societes") or {}).get(cle) if isinstance(ini, dict) else None
        if t == "achats_groupes":
            if not soc or not soc.get("acheteurs_30j"):
                return False, "plus d'achats de dirigeants sur 30 jours"
            return True, f"{soc['acheteurs_30j']} acheteurs sur 30 jours"
        return True, "âge seul vérifié"
    if agent == "pays":
        p = src.pays()
        if p is not None and cle not in p and not s.get("pays"):
            return False, "pays absent des données de l'agent pays"
    return True, "âge seul vérifié"


# ------------------------------------------------------------------ faits et objections

class Faits:
    def __init__(self):
        self.liste = []

    def ajouter(self, texte: str, source: str, contexte: bool = False) -> str:
        i = f"F{len(self.liste) + 1}"
        self.liste.append({"id": i, "texte": texte, "source": source, **({"contexte": True} if contexte else {})})
        return i


class Objections:
    """Points spécifiques au signal : (texte avec renvoi, gravité 1 = nuance, 2 = sérieuse)."""

    def __init__(self, faits: Faits):
        self.f = faits
        self.points = []

    def ajouter(self, texte: str, fait: str, source: str, gravite: int = 1) -> None:
        i = self.f.ajouter(fait, source)
        self.points.append((f"{texte} [{i}]", gravite))


def reaction(serie, date_signal: str):
    """(point avant le signal, dernier point) ; départ = dernière clôture avant le jour du signal."""
    if not serie:
        return None
    avant = C.valeur_a(serie, C.jour(date_signal) - timedelta(days=1))
    if avant is None or serie[-1][0] < date_signal:
        return None
    return avant, serie[-1]


def _ind(e: dict, cle: str):
    return ((e.get("indicateurs") or {}).get(cle) or {})


def vulnerabilites_pays(o: Objections, code: str, ctx: dict, config: dict) -> None:
    """Points faibles propres au pays (composantes du score de risque)."""
    s = ctx["pays_scores"].get(code) or {}
    nom = ctx["noms"].get(code, code)
    comp = s.get("composantes") or {}
    src = "agent risque (data/risque.json)"
    m = comp.get("macro") or {}
    if m.get("dette_pib") is not None and m["dette_pib"] >= 90:
        o.ajouter(f"{nom} : dette publique de {C.fr(m['dette_pib'], 0)} % du PIB", f"{nom} : dette publique de {C.fr(m['dette_pib'], 0)} % du PIB", "FMI (GGXWDG_NGDP)", 1)
    if m.get("solde_courant") is not None and m["solde_courant"] <= -3:
        o.ajouter(f"déficit courant de {C.fr(abs(m['solde_courant']), 1)} % du PIB", f"{nom} : solde courant de {C.fr(m['solde_courant'], 1, True)} % du PIB", "FMI (BCA_NGDPD)", 1)
    if m.get("inflation") is not None and abs(m["inflation"] - (m.get("cible_inflation") or 2)) >= 3:
        o.ajouter(f"inflation à {C.fr(m['inflation'], 1)} % pour une cible de {C.fr(m['cible_inflation'], 1)} %",
                  f"{nom} : inflation à {C.fr(m['inflation'], 1)} %, cible de {C.fr(m['cible_inflation'], 1)} %", "agent pays / FMI", 1)
    if m.get("reserves_mois") is not None and m["reserves_mois"] < 3:
        o.ajouter(f"réserves de change de {C.fr(m['reserves_mois'], 1)} mois d'importations seulement",
                  f"{nom} : réserves de {C.fr(m['reserves_mois'], 1)} mois d'importations", "Banque mondiale (FI.RES.TOTL.MO)", 2)
    d = comp.get("devise") or {}
    if d.get("variation_3m") is not None and (d["variation_3m"] <= -5 or (d.get("volatilite_1m") or 0) >= 12):
        o.ajouter(f"devise à {C.fr(d['variation_3m'], 1, True)} % contre le dollar sur 3 mois (volatilité à 1 mois de {C.fr(d['volatilite_1m'], 1)} %)",
                  f"{nom} : {d['texte']}", d["source"], 2 if d["variation_3m"] <= -10 else 1)
    sv = comp.get("souverain") or {}
    if sv.get("ecart") is not None and sv["ecart"] >= 2.5:
        o.ajouter(f"taux à 10 ans de {C.fr(sv['taux_10a'], 2)} %, écart de {C.fr(sv['ecart'], 2, True)} pt avec la référence",
                  f"{nom} : {sv['texte']}", sv["source"], 1)
    mk = comp.get("marche") or {}
    if mk.get("baisse_plus_haut_12m") is not None and mk["baisse_plus_haut_12m"] <= -15:
        o.ajouter(f"ETF {mk['etf']} à {C.fr(mk['baisse_plus_haut_12m'], 1)} % de son plus haut sur 12 mois",
                  f"{nom} : {mk['texte']}", mk["source"], 1)
    if s.get("score") is not None and s["score"] >= config["pays"]["seuil_eleve"]:
        o.ajouter(f"score de risque du pays de {C.fr(s['score'], 0)}/100", f"{nom} : score de risque {C.fr(s['score'], 0)}/100", src, 2)


def objections_entreprise(o: Objections, s: dict, ctx: dict, config: dict) -> bool:
    """Objections propres à l'entreprise. Renvoie False si l'entreprise est introuvable."""
    e = (ctx["entreprises"] or {}).get(s.get("cle"))
    if not e:
        return False
    fiche = ctx["sources"].fiche(e)
    t = s.get("type")
    src = "agent entreprises (data/entreprises.json)"
    nom = e.get("nom") or s.get("cle")
    if t == "alerte_comptable":
        # Signal négatif : ce qui le nuance dans les comptes de l'entreprise
        cc = _ind(e, "conversion_cash")
        if cc.get("valeur") is not None and cc["valeur"] >= 90:
            o.ajouter(f"la conversion du bénéfice en cash reste de {cc['affichage']}", f"{nom} : conversion du bénéfice en cash de {cc['affichage']}", src, 1)
        fs = _ind(e, "fscore")
        if fs.get("valeur") is not None and fs["valeur"] >= 7:
            o.ajouter(f"F-score de Piotroski de {fs['affichage']}", f"{nom} : F-score de {fs['affichage']}", src, 1)
        if e.get("financier") and re.search(r"créances", s.get("titre") or "", re.I):
            o.ajouter(f"entreprise financière ({e['financier']}) : ses créances ne suivent pas le chiffre d'affaires comme celles d'une entreprise industrielle",
                      f"{nom} : entreprise financière ({e['financier']})", src, 2)
        return True
    # Signal positif (pépite, hausse de note…) : les risques propres à l'entreprise
    per = _ind(e, "per_secteur")
    if per.get("valeur") is not None and per["valeur"] >= 20:
        comp = f" ({per['complement']})" if per.get("complement") else ""
        o.ajouter(f"valorisation supérieure de {C.fr(per['valeur'], 0)} % à la médiane du secteur{comp}",
                  f"{nom} : PER vs secteur {per['affichage']}{comp}", src, 2 if per["valeur"] >= 50 else 1)
    ev = _ind(e, "ev_ebitda_secteur")
    if ev.get("valeur") is not None and ev["valeur"] >= 30 and not (per.get("valeur") or 0) >= 20:
        o.ajouter(f"VE/EBITDA supérieur de {C.fr(ev['valeur'], 0)} % à la médiane du secteur", f"{nom} : VE/EBITDA vs secteur {ev['affichage']}", src, 1)
    dette = _ind(e, "dette_ebitda")
    if not e.get("financier") and dette.get("valeur") is not None and dette["valeur"] >= 3:
        o.ajouter(f"dette nette de {dette['affichage']} l'EBITDA", f"{nom} : dette nette / EBITDA de {dette['affichage']}", src, 2 if dette["valeur"] >= 4 else 1)
    cv = _ind(e, "couverture_interets")
    if not e.get("financier") and cv.get("valeur") is not None and cv["valeur"] < 4:
        o.ajouter(f"couverture des intérêts de {cv['affichage']} seulement", f"{nom} : couverture des intérêts de {cv['affichage']}", src, 2 if cv["valeur"] < 2 else 1)
    mom = _ind(e, "momentum_12m")
    if mom.get("valeur") is not None and mom["valeur"] <= config["contradicteur"]["momentum_pepite_min"]:
        o.ajouter(f"cours à {mom['affichage']} sur 12 mois : le marché ne valide pas la qualité affichée", f"{nom} : momentum 12 mois {mom['affichage']}", src, 2)
    elif fiche.get("momentum"):
        # Repli récent du cours (3 ou 6 mois), même si le momentum sur 12 mois reste positif
        mm = fiche["momentum"]
        pire = min(((k, v) for k, v in (("3 mois", mm.get("m3")), ("6 mois", mm.get("m6"))) if v is not None), key=lambda kv: kv[1], default=None)
        if pire and pire[1] <= -15:
            o.ajouter(f"cours à {C.fr(pire[1], 1, True)} % sur {pire[0]}", f"{nom} : cours {C.fr(mm.get('m3'), 1, True)} % sur 3 mois, "
                      f"{C.fr(mm.get('m6'), 1, True)} % sur 6 mois, {C.fr(mm.get('m12'), 1, True)} % sur 12 mois", "agent entreprises (fiche)",
                      2 if pire[1] <= -30 else 1)
    cb = _ind(e, "croissance_benefice")
    if cb.get("valeur") is not None and cb["valeur"] <= -20:
        o.ajouter(f"bénéfice en baisse de {C.fr(abs(cb['valeur']), 0)} %", f"{nom} : croissance du bénéfice {cb['affichage']}", src, 1)
    ca = _ind(e, "croissance_ca")
    if cb.get("valeur") is not None and cb["valeur"] >= 100:
        o.ajouter(f"bénéfice en hausse de {C.fr(cb['valeur'], 0)} % sur un exercice, difficilement reproductible",
                  f"{nom} : croissance du bénéfice {cb['affichage']}", src, 1)
    elif ca.get("valeur") is not None and ca["valeur"] >= 50:
        comp = f" ({ca['complement']})" if ca.get("complement") else ""
        o.ajouter(f"chiffre d'affaires en hausse de {C.fr(ca['valeur'], 0)} % sur un exercice{comp} : à vérifier (acquisition, élément non récurrent)",
                  f"{nom} : croissance du CA {ca['affichage']}{comp}", src, 1)
    elif ca.get("valeur") is not None and ca["valeur"] <= -10:
        o.ajouter(f"chiffre d'affaires en baisse de {C.fr(abs(ca['valeur']), 0)} %", f"{nom} : croissance du CA {ca['affichage']}", src, 1)
    cc = _ind(e, "conversion_cash")
    if cc.get("valeur") is not None and cc["valeur"] < 70:
        o.ajouter(f"bénéfice converti en cash à {cc['affichage']} seulement", f"{nom} : conversion du bénéfice en cash de {cc['affichage']}", src, 1)
    rc = ctx.get("revues_critiques", {}).get(s.get("cle")) or {}
    if (rc.get("piege_de_valeur") or "").startswith("possible"):
        o.ajouter(f"piège de valeur {rc['piege_de_valeur']}", f"{nom} : piège de valeur {rc['piege_de_valeur']} (revue critique)", "agent entreprises (data/pepites.json)", 1)
    for a in (fiche.get("alertes") or [])[:2]:
        o.ajouter(f"signal d'alerte comptable : {a.get('titre', '').lower()} ({a.get('texte')})", f"{nom} : alerte « {a.get('titre')} » : {a.get('texte')}",
                  "agent entreprises (fiche)", 2)
    # Devise de cotation et risque du pays
    code = e.get("pays")
    devise = fiche.get("devise_cours") or e.get("devise")
    dv = ((ctx["pays_scores"].get(code) or {}).get("composantes") or {}).get("devise") or {}
    if devise and devise != "USD" and dv.get("variation_3m") is not None and (dv["variation_3m"] <= -5 or (dv.get("volatilite_1m") or 0) >= 12):
        o.ajouter(f"cotée en {devise}, devise à {C.fr(dv['variation_3m'], 1, True)} % contre le dollar sur 3 mois",
                  f"{ctx['noms'].get(code, code)} : {dv['texte']}", dv["source"], 1)
    sp = ctx["pays_scores"].get(code) or {}
    if sp.get("score") is not None and sp["score"] >= config["pays"]["seuil_modere"] + 10:
        haut = max((sp.get("composantes") or {}).items(), key=lambda kv: kv[1]["score"], default=(None, None))
        o.ajouter(f"pays ({ctx['noms'].get(code, code)}) noté {C.fr(sp['score'], 0)}/100 en risque"
                  + (f", porté par la composante {haut[0]} ({C.fr(haut[1]['score'], 0)}/100)" if haut[0] else ""),
                  f"{ctx['noms'].get(code, code)} : score de risque {C.fr(sp['score'], 0)}/100", "agent risque (data/risque.json)",
                  2 if sp["score"] >= config["pays"]["seuil_eleve"] else 1)
    # Sensibilité du secteur à la phase du cycle de sa zone (agent macro)
    secteur = SECTEURS_CYCLIQUES.get(e.get("secteur_gics"))
    phase = ctx.get("phase_zone", {}).get(code) or ctx.get("phase_zone", {}).get("*")
    if secteur and phase and NEGATIFS.search(phase[1]):
        o.ajouter(f"secteur cyclique ({secteur}) alors que la zone {phase[0]} est en phase « {phase[1]} »",
                  f"Zone {phase[0]} : phase « {phase[1]} » (agent macro)", "agent macro (data/macro.json)", 1)
    return True


def objections_zone(o: Objections, s: dict, ctx: dict, config: dict) -> None:
    """Changement de phase d'une zone : robustesse dans les données de la zone elle-même."""
    zone = next((z for z in ((ctx["macro"] or {}).get("cycle") or {}).get("zones", []) if z.get("cle") == s.get("cle")), None)
    if not zone:
        return
    src = "agent macro (data/macro.json)"
    nom = zone.get("nom") or s.get("cle")
    hist = zone.get("historique") or []
    recents = [p for _, p in hist[-6:]]
    changements = sum(1 for a, b in zip(recents, recents[1:]) if a != b)
    if changements >= 2:
        o.ajouter(f"{changements} changements de phase en 6 mois pour la zone {nom}",
                  f"{nom} : phases sur 6 mois : {' → '.join(dict.fromkeys(recents))} ({changements} changements)", src, 2)
    cr = zone.get("croissance") or {}
    if cr.get("cli_3m") is not None and abs(cr["cli_3m"]) < 0.1:
        o.ajouter(f"indicateur avancé quasi stable ({C.fr(cr['cli_3m'], 2, True)} pt sur 3 mois)",
                  f"{nom} : indicateur avancé à {C.fr(cr.get('cli'), 1)}, {C.fr(cr['cli_3m'], 2, True)} pt sur 3 mois", src, 1)
    for cle, lib in (("croissance", "croissance"), ("inflation", "inflation")):
        x = zone.get(cle) or {}
        votes = x.get("votes") or []
        if votes and x.get("concordants") is not None and x["concordants"] < len(votes):
            o.ajouter(f"direction de l'{lib} confirmée par {x['concordants']} sources sur {len(votes)}",
                      f"{nom} : {lib}, {x['concordants']} vote(s) concordant(s) sur {len(votes)}", src, 1)


def objections_banque(o: Objections, s: dict, ctx: dict) -> None:
    bc = next((b for b in (ctx["macro"] or {}).get("banques_centrales", []) if b.get("cle") == s.get("cle")), None)
    if not bc:
        return
    dm, t12 = bc.get("dernier_mouvement") or {}, bc.get("tendance_12m") or {}
    if dm.get("sens") and t12.get("sens") and t12["sens"] not in (dm["sens"],) and t12["variation_pts"] is not None:
        o.ajouter(f"mouvement isolé : {C.fr(t12['variation_pts'], 2, True)} pt sur 12 mois malgré la {dm['sens']} de {C.fr(dm.get('ampleur_pts'), 2)} pt",
                  f"{bc['nom']} : {dm['sens']} de {C.fr(dm.get('ampleur_pts'), 2)} pt le {C.date_fr(dm.get('date'))}, {C.fr(t12['variation_pts'], 2, True)} pt sur 12 mois",
                  bc.get("source") or "agent macro", 1)


def objections_evenement(o: Objections, s: dict, ctx: dict, config: dict) -> None:
    """Événement géopolitique (signal de risque) : ce qui le nuance pour les pays concernés."""
    cfg = config["contradicteur"]
    nsrc = len(s.get("sources") or [])
    if s.get("type") == "evenement_grave" and nsrc < 2:
        o.ajouter(f"le signal ne repose que sur {nsrc} source", f"{nsrc} source citée par le signal", "data/signaux/geopolitique.json", 3)
    for code in (s.get("pays") or [])[:3]:
        p = ctx["pays_config"].get(code)
        if not p:
            continue
        r = reaction(ctx["cours"].get(p.get("etf")), s["date"])
        if r:
            perf = round(100 * (r[1][1] / r[0][1] - 1), 2)
            if perf > cfg["reaction_etf_pct"]:
                o.ajouter(f"le marché ne confirme pas pour {p['nom']} (ETF {p['etf']} à {C.fr(perf, 1, True)} % depuis la veille du signal)",
                          f"ETF {p['etf']} ({p['nom']}) : {C.fr(perf, 1, True)} % depuis la veille du signal", f"Yahoo Finance via yfinance, {p['etf']}", 2)
        m = ((ctx["pays_scores"].get(code) or {}).get("composantes") or {}).get("macro") or {}
        if m.get("reserves_mois") is not None and m["reserves_mois"] >= 6 and (m.get("dette_pib") or 0) < 60:
            o.ajouter(f"{p['nom']} dispose d'amortisseurs (réserves de {C.fr(m['reserves_mois'], 1)} mois d'importations, dette publique de {C.fr(m['dette_pib'], 0)} % du PIB)",
                      f"{p['nom']} : réserves de {C.fr(m['reserves_mois'], 1)} mois, dette de {C.fr(m['dette_pib'], 0)} % du PIB", "FMI, Banque mondiale", 1)


def contexte(f: Faits, ctx: dict, s: dict, config: dict, positif: bool) -> str | None:
    """Une phrase au plus sur le contexte mondial, seulement quand elle complète l'objection."""
    m = ctx["mondial"]
    paliers = config["paliers"]
    if positif and m["palier"] in paliers[2:]:
        i = f.ajouter(f"Palier de risque mondial « {m['palier']} » (score de stress {C.fr(m['score'], 0)}/100)", "agent risque (data/risque.json)", contexte=True)
        return f"Contexte : palier de risque mondial « {m['palier']} » [{i}]."
    if not positif and s.get("type") == "evenement_grave":
        vix = ctx["indicateurs"].get("vix") or {}
        r = reaction(vix.get("_serie"), s["date"]) if vix.get("disponible") else None
        if r and r[1][1] - r[0][1] < config["contradicteur"]["reaction_vix_pts"]:
            d = round(r[1][1] - r[0][1], 2)
            i = f.ajouter(f"VIX : {C.fr(d, 1, True)} pts depuis la veille du signal ({C.date_fr(r[0][0])})", vix["source"], contexte=True)
            return f"Contexte : le VIX a varié de {C.fr(d, 1, True)} pts depuis le signal [{i}]."
    return None


def regles(fichier: str, s: dict, ctx: dict, config: dict) -> dict:
    agent, t = fichier.removesuffix(".json"), s.get("type") or ""
    f = Faits()
    o = Objections(f)
    positif = True
    if agent == "entreprises":
        positif = t != "alerte_comptable"
        objections_entreprise(o, s, ctx, config)
    elif agent == "inities":
        # Achats de dirigeants, nouvelle position d'un super-investisseur, 13D : signaux positifs sur une société
        objections_entreprise(o, s, ctx, config)
    elif agent == "macro" and t == "changement_de_phase":
        objections_zone(o, s, ctx, config)
        positif = not NEGATIFS.search(_phase_cible(s.get("titre")) or "")
    elif agent == "macro" and t == "mouvement_banque_centrale":
        objections_banque(o, s, ctx)
    elif agent == "geopolitique":
        positif = False
        if t == "hausse_score":
            for code in (s.get("pays") or [s.get("cle")])[:1]:
                objections_evenement(o, {**s, "pays": [code]}, ctx, config)
        else:
            objections_evenement(o, s, ctx, config)
    else:
        codes = s.get("pays") or ([s["cle"]] if s.get("cle") in ctx["pays_config"] else [])
        for code in codes[:2]:
            vulnerabilites_pays(o, code, ctx, config)
    total = sum(g for _, g in o.points)
    if not o.points:
        texte, ajust = PAS_D_OBJECTION, "maintenir"
    else:
        texte = "Objections spécifiques : " + " ; ".join(p for p, _ in o.points) + "."
        ajust = "signal fragile" if total >= 4 or any(g >= 3 for _, g in o.points) else "abaisser" if total >= 2 else "maintenir"
    phrase = contexte(f, ctx, s, config, positif) if o.points else None
    if phrase:
        texte += " " + phrase
    return {"objection": texte, "faits": f.liste, "ajustement": ajust, "specifique": bool(o.points), "methode": "règles",
            "confiance": "moyen" if len(o.points) >= 2 else "faible" if o.points else "moyen", "version_regles": VERSION_REGLES}


# ------------------------------------------------------------------ Gemini

def consigne(lot: list[tuple[str, dict, dict]]) -> str:
    blocs = []
    for i, (fichier, s, r) in enumerate(lot, 1):
        blocs.append({"id": f"S{i}", "agent": fichier.removesuffix(".json"), "type": s.get("type"), "date": s.get("date"),
                      "titre": s.get("titre"), "explication": s.get("explication"),
                      "faits": [{"id": x["id"], "texte": x["texte"], "source": x["source"], "contexte_mondial": bool(x.get("contexte"))} for x in r["faits"]],
                      "ajustement_par_regles": r["ajustement"]})
    return (
        "Tu es l'agent risque d'une plateforme de suivi économique, dans un rôle de contradicteur. Pour chaque signal ci-dessous, "
        "écris en français une objection froide et factuelle (deux phrases au plus, sans alarmisme), PROPRE à ce signal : pour une entreprise, "
        "ses propres risques ; pour un pays, ses vulnérabilités ; pour une zone, la robustesse du changement de phase. "
        "N'utilise QUE les faits fournis : chaque chiffre doit figurer dans un fait cité, cité par son id entre crochets, par exemple [F2]. "
        "Les faits marqués contexte_mondial ne peuvent servir qu'en complément, en une phrase au plus. "
        "Propose un ajustement de confiance parmi « maintenir », « abaisser », « signal fragile ».\n"
        "Réponds uniquement en JSON : {\"revues\": [{\"id\": \"S1\", \"objection\": \"…\", \"faits\": [\"F1\"], \"ajustement\": \"maintenir\"}]}\n\n"
        + json.dumps(blocs, ensure_ascii=False)
    )


def _nombres(texte: str) -> set[str]:
    return {n.replace(",", ".").lstrip("0") or "0" for n in re.findall(r"\d+(?:[.,]\d+)?", texte or "")}


def valider(brut: dict, s: dict, r: dict) -> tuple[dict | None, str | None]:
    if not isinstance(brut, dict):
        return None, "format"
    objection = (brut.get("objection") or "").strip()
    ajust = brut.get("ajustement")
    if not objection or ajust not in AJUSTEMENTS:
        return None, "objection vide ou ajustement inconnu"
    par_id = {x["id"]: x for x in r["faits"]}
    cites = [i for i in (brut.get("faits") or []) if i in par_id] + [i for i in re.findall(r"F\d+", objection) if i in par_id]
    cites = list(dict.fromkeys(cites))
    if not any(not par_id[i].get("contexte") for i in cites):
        return None, "aucun fait propre au signal cité"
    permis = set()
    for i in cites:
        permis |= _nombres(par_id[i]["texte"])
    permis |= _nombres(s.get("titre")) | _nombres(s.get("explication"))
    hors = [n for n in _nombres(re.sub(r"\[[^\]]*\]", "", objection)) if n not in permis]
    if hors:
        return None, f"chiffres absents des faits : {', '.join(hors[:4])}"
    return {**r, "objection": objection, "faits_cites": cites, "ajustement": ajust, "methode": "gemini"}, None


def rediger_gemini(lot, quotas, cfg: dict, cle: str, poster, rapport: dict) -> dict[int, dict]:
    from ..geopolitique import ia
    texte, modele = ia.appel_chaine(consigne(lot), quotas, cfg, cle, poster, rapport)
    if texte is None:
        return {}
    try:
        reponse = json.loads(texte)
    except ValueError:
        rapport["rejets"].append("réponse JSON illisible")
        return {}
    res = {}
    for x in (reponse.get("revues") or []) if isinstance(reponse, dict) else []:
        m = re.fullmatch(r"S(\d+)", str(x.get("id", "")))
        if not m or not 1 <= int(m.group(1)) <= len(lot):
            continue
        k = int(m.group(1)) - 1
        v, raison = valider(x, lot[k][1], lot[k][2])
        if v:
            res[k] = {**v, "modele": modele}
            rapport["reussites"] += 1
        else:
            rapport["rejets"].append(f"{id_signal(lot[k][0], lot[k][1])} : {raison}")
    return res


# ------------------------------------------------------------------ revue

def revoir(signaux: dict[str, list[dict]], existantes: list[dict], ctx: dict, config: dict, etat: dict,
           cle_gemini: str | None, poster=None, horloge=None, dormir=None) -> tuple[list[dict], list[dict], dict]:
    """Renvoie (revues à garder, dont les nouvelles ; nouvelles revues ; compte rendu).
    Les revues des signaux qui ne sont plus valides (ou d'une version antérieure des règles) sont retirées."""
    import time
    from ..geopolitique import ia
    src = ctx["sources"]
    valides, invalides = {}, {}
    for fichier, liste in signaux.items():
        for s in liste:
            ok, raison = valide(fichier, s, src, config, ctx["aujourdhui"])
            (valides if ok else invalides)[id_signal(fichier, s)] = (fichier, s) if ok else raison
    # Un signal répété (même agent, type et clé) : seul le plus récent reste valide
    recents = {}
    for k, (fichier, s) in valides.items():
        g = (fichier, s.get("type"), s.get("cle"))
        if g not in recents or (s.get("date") or "") > (valides[recents[g]][1].get("date") or ""):
            recents[g] = k
    for k in [k for k in valides if k not in set(recents.values())]:
        invalides[k] = "remplacé par un signal plus récent"
        del valides[k]
    gardees = [r for r in existantes if r.get("id") in valides and r.get("version_regles") == VERSION_REGLES]
    deja = {r["id"] for r in gardees}
    candidats = sorted((v for k, v in valides.items() if k not in deja), key=lambda x: (x[1].get("date") or "", x[0]), reverse=True)
    candidats = candidats[:config["contradicteur"]["revues_max_par_execution"]]
    rapport = {"cle": bool(cle_gemini), "appels": 0, "reussites": 0, "rejets": [], "erreurs": [], "quota_atteint": False,
               "candidats": len(candidats), "valides": len(valides), "retirees": len(existantes) - len(gardees),
               "ecartes": dict(sorted(((k, v) for k, v in invalides.items() if v != "importance faible"), reverse=True)[:30])}
    prepares = [(fichier, s, regles(fichier, s, ctx, config)) for fichier, s in candidats]
    redige = {}
    cfg = config["gemini"]
    quotas = ia.Quotas(etat, cfg, horloge=horloge, dormir=dormir or time.sleep)
    # Gemini ne reformule que les revues qui ont une objection spécifique (sinon : « Pas d'objection spécifique »)
    a_rediger = [k for k, p in enumerate(prepares) if p[2]["specifique"]]
    if cle_gemini and a_rediger:
        n = cfg["signaux_par_appel"]
        for k in range(0, len(a_rediger), n):
            if quotas.appels_execution() >= cfg["appels_max_par_execution"]:
                break
            indices = a_rediger[k:k + n]
            for j, v in rediger_gemini([prepares[i] for i in indices], quotas, cfg, cle_gemini, poster, rapport).items():
                redige[indices[j]] = v
    rapport["quota"] = quotas.resume()
    nouvelles = []
    for k, (fichier, s, r) in enumerate(prepares):
        v = redige.get(k, r)
        nouvelles.append({"id": id_signal(fichier, s), "revu_le": ctx["maintenant_iso"],
                          "signal": {"agent": fichier.removesuffix(".json"), "type": s.get("type"), "cle": s.get("cle"), "date": s.get("date"),
                                     "importance": s.get("importance"), "titre": s.get("titre")},
                          **v})
    return gardees + nouvelles, nouvelles, rapport
