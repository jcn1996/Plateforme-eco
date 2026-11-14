"""
Flux d'investissement des ETF pays (cotés aux États-Unis) : indicateur « Flux étrangers » de la fiche pays.

Calcul : flux du jour = (parts en circulation du jour − parts du relevé précédent) × VL du jour.
Il n'existe pas d'historique gratuit des parts en circulation pour la plupart des ETF : l'agent accumule
lui-même un relevé par jour de bourse dans data/historique/flux_etf/AAAA-MM-JJ.json (date = date de la VL).
SSGA (SPY) et VanEck (VNM) publient un historique : il sert à compléter les jours manquants.

Indicateurs par pays : flux nets sur 1 semaine, 1 mois et 3 mois (M$ et % de l'encours au début de la
période), série de jours consécutifs d'entrées ou de sorties, cumul quotidien (graphique de la fiche).
Une période est « en cours de constitution » tant que l'historique ne remonte pas jusqu'à son début.

Règles de conduite :
- un afflux très fort par rapport aux semaines précédentes est signalé « position possiblement encombrée »
  (et la note est plafonnée) ;
- l'agent rappelle toujours que ces flux ne couvrent que les ETF cotés aux États-Unis.
Les règles chiffrées sont décrites dans regles.md, les seuils dans config.json (bloc « flux_etf »).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from statistics import mean, pstdev

from ..commun.journal import journal
from ..commun.sortie import ecrire_json, lire_json
from . import notation
from .sources_flux import COURTS, NOMS
from .textes import nb

LOG = journal("flux-etf")
AVERTISSEMENT = ("Flux des ETF pays cotés aux États-Unis uniquement : ils ne couvrent ni les ETF cotés ailleurs, "
                 "ni les fonds non cotés, ni les achats directs d'actions par les étrangers.")
LIBELLE = "Flux étrangers"


def _j(texte: str) -> date:
    return date.fromisoformat(str(texte)[:10])


# ------------------------------------------------------------------ relevé du jour : choix et vérification croisée

def choisir_releve(etf: str, emetteur: str, src: dict, config_flux: dict, aujourdhui: date) -> dict:
    """Relevé retenu pour un ETF : l'émetteur d'abord, Yahoo Finance en secours.
    Renvoie {retenu: relevé | None, sources: [...], verification}."""
    tol_parts, tol_encours = config_flux["tolerance_parts_pct"], config_flux["tolerance_encours_pct"]
    fraicheur = config_flux["fraicheur_max_jours"]
    sources = []
    for cle in (emetteur, "yahoo_parts"):
        nom = NOMS[cle].format(etf=etf)
        donnees = src.get(f"flux_{cle}")
        if donnees is None:
            sources.append({"source": cle, "nom": nom, "statut": "échec", "raison": "source indisponible lors de cette exécution"})
            continue
        r = donnees.get(etf)
        if not r:
            sources.append({"source": cle, "nom": nom, "statut": "échec", "raison": f"aucune donnée pour {etf}"})
            continue
        ligne = {"source": cle, "nom": nom, "valeur": round(r["parts"] / 1e6, 4), "date": r["date"], "releve": r}
        age = (aujourdhui - _j(r["date"])).days
        if age > fraicheur:
            ligne |= {"statut": "rejetée", "raison": f"trop ancienne (relevé du {r['date']}, plus de {fraicheur} jours)"}
        elif r.get("encours") and abs(r["parts"] * r["vl"] / r["encours"] - 1) * 100 > tol_encours:
            ligne |= {"statut": "rejetée", "raison": "incohérent : parts × VL éloigné de l'actif net publié"}
        else:
            ligne["statut"] = "valable"
        sources.append(ligne)

    valables = [s for s in sources if s["statut"] == "valable"]
    retenu = valables[0] if valables else None
    verification = "aucune_source" if not retenu else "source_unique"
    if retenu:
        retenu["statut"] = "retenue"
        for s in valables[1:]:
            if s["date"] != retenu["date"]:
                s |= {"statut": "non comparable", "raison": f"relevé d'une autre date ({s['date']})"}
                continue
            ecart = abs(s["releve"]["parts"] / retenu["releve"]["parts"] - 1) * 100
            s["ecart"] = round(ecart, 2)
            s["statut"] = "concorde" if ecart <= tol_parts else "diverge"
            verification = "divergent" if s["statut"] == "diverge" else "concordant"
    publiees = [{k: v for k, v in s.items() if k != "releve"} for s in sources]
    return {"retenu": dict(retenu["releve"], source=retenu["source"]) if retenu else None,
            "sources": publiees, "verification": verification}


# ------------------------------------------------------------------ historique jour par jour

def lire_historique(dossier: Path, aujourdhui: date, conservation_jours: int) -> dict[str, list[dict]]:
    """{etf: [relevé, …] triés par date} à partir des fichiers AAAA-MM-JJ.json."""
    limite = (aujourdhui - timedelta(days=conservation_jours)).isoformat()
    series: dict[str, dict[str, dict]] = {}
    for chemin in sorted(Path(dossier).glob("????-??-??.json")):
        if chemin.stem < limite:
            continue
        for etf, r in ((lire_json(chemin) or {}).get("donnees") or {}).items():
            # flux_musd est recalculé à chaque fois (il dépend du relevé précédent)
            series.setdefault(etf, {})[chemin.stem] = {**{k: v for k, v in r.items() if k != "flux_musd"}, "date": chemin.stem}
    return {etf: [s[d] for d in sorted(s)] for etf, s in series.items()}


def completer_historique(historique: dict, etf: str, releve: dict, verification: str, remplissage_jours: int,
                         aujourdhui: date) -> list[str]:
    """Ajoute le relevé du jour (et, s'il existe, l'historique publié par l'émetteur pour les jours absents).
    Renvoie les dates ajoutées ou modifiées."""
    serie = {r["date"]: r for r in historique.get(etf, [])}
    modifiees = []
    limite = (aujourdhui - timedelta(days=remplissage_jours)).isoformat()
    for d, parts, vl, encours in releve.get("historique") or []:
        if d >= limite and d not in serie and d != releve["date"]:
            serie[d] = {"date": d, "parts": parts, "vl": vl, "encours": encours, "source": releve["source"],
                        "verification": "historique_emetteur"}
            modifiees.append(d)
    nouveau = {"date": releve["date"], "parts": releve["parts"], "vl": releve["vl"], "encours": releve.get("encours"),
               "source": releve["source"], "verification": verification}
    if serie.get(releve["date"]) != nouveau:
        serie[releve["date"]] = nouveau
        modifiees.append(releve["date"])
    historique[etf] = [serie[d] for d in sorted(serie)]
    return modifiees


def ecrire_historique(dossier: Path, historique: dict, dates: set[str], genere_le: str, version: str) -> list[Path]:
    """Réécrit les fichiers des dates modifiées (un fichier par jour de VL, tous les ETF de ce jour)."""
    ecrits = []
    for d in sorted(dates):
        chemin = Path(dossier) / f"{d}.json"
        existant = (lire_json(chemin) or {}).get("donnees") or {}
        jour = dict(existant)
        for etf, serie in historique.items():
            precedent = None
            for r in serie:
                if r["date"] == d:
                    ligne = {k: r[k] for k in ("parts", "vl", "encours", "source", "verification") if k in r}
                    flux = flux_du_jour(precedent, r)
                    if flux is not None:
                        ligne["flux_musd"] = round(flux / 1e6, 3)
                    jour[etf] = ligne
                    break
                precedent = r
        if jour != existant:
            ecrire_json(chemin, {"meta": {"genere_le": genere_le, "source": "agent-pays", "version_agent": version,
                                          "description": "Parts en circulation et VL des ETF pays (date = date de la VL) ; "
                                                         "flux_musd = variation des parts depuis le relevé précédent × VL, en M$"},
                                 "donnees": dict(sorted(jour.items()))})
            ecrits.append(chemin)
    return ecrits


# ------------------------------------------------------------------ calculs

def flux_du_jour(precedent: dict | None, r: dict, variation_max_pct: float = 50) -> float | None:
    """(parts − parts précédentes) × VL, en dollars. Division ou regroupement de parts (parts et VL
    varient en sens inverse, actif stable) : flux nul. Variation aberrante : None."""
    if not precedent:
        return None
    ratio = r["parts"] / precedent["parts"]
    if abs(ratio - 1) > 0.2:
        actif = (r["parts"] * r["vl"]) / (precedent["parts"] * precedent["vl"])
        if abs(actif - 1) < 0.1:
            return 0.0  # division ou regroupement de parts
        if abs(ratio - 1) * 100 > variation_max_pct:
            return None
    return (r["parts"] - precedent["parts"]) * r["vl"]


def flux_quotidiens(serie: list[dict], variation_max_pct: float = 50) -> list[dict]:
    """[{date, flux (en $), pct (en % de l'encours de la veille)}] à partir du 2e relevé."""
    res = []
    for avant, r in zip(serie, serie[1:]):
        f = flux_du_jour(avant, r, variation_max_pct)
        if f is None:
            continue
        base = avant["parts"] * avant["vl"]
        res.append({"date": r["date"], "flux": f, "pct": f / base * 100 if base else 0.0})
    return res


def _periode(serie: list[dict], quotidiens: list[dict], fin: date, jours: int) -> dict:
    debut = fin - timedelta(days=jours)
    bases = [r for r in serie if _j(r["date"]) <= debut]
    complet = bool(bases)
    base = bases[-1] if complet else serie[0]
    flux = sum(q["flux"] for q in quotidiens if q["date"] > base["date"])
    encours_base = base["parts"] * base["vl"]
    return {"jours": jours, "complet": complet, "debut": base["date"],
            "jours_disponibles": (fin - _j(serie[0]["date"])).days,
            "flux_musd": round(flux / 1e6, 2), "pct_encours": round(flux / encours_base * 100, 3) if encours_base else None,
            "statut": "complet" if complet else "en cours de constitution"}


def serie_consecutive(quotidiens: list[dict]) -> dict | None:
    """Jours de bourse consécutifs d'entrées (ou de sorties), à partir du dernier jour avec un flux.
    Les jours sans création ni rachat de parts ne comptent pas et n'interrompent pas la série."""
    non_nuls = [q for q in quotidiens if abs(q["flux"]) > 0]
    if not non_nuls:
        return None
    signe = non_nuls[-1]["flux"] > 0
    n = 0
    for q in reversed(non_nuls):
        if (q["flux"] > 0) != signe:
            break
        n += 1
    return {"sens": "entrées" if signe else "sorties", "jours": n, "depuis": non_nuls[-n]["date"]}


def _sommes_glissantes(serie: list[dict], quotidiens: list[dict], jours: int) -> list[float]:
    """Flux sur « jours » jours (en % de l'encours de début), pour chaque relevé assez ancien (le dernier exclu)."""
    res = []
    for r in serie[:-1]:
        fin = _j(r["date"])
        if (fin - _j(serie[0]["date"])).days < jours:
            continue
        p = _periode([x for x in serie if x["date"] <= r["date"]], [q for q in quotidiens if q["date"] <= r["date"]], fin, jours)
        if p["pct_encours"] is not None:
            res.append(p["pct_encours"])
    return res


def encombrement(serie: list[dict], quotidiens: list[dict], semaine: dict, cfg: dict) -> dict | None:
    """Afflux très fort sur une semaine par rapport aux semaines précédentes : « position possiblement encombrée »."""
    pct = semaine.get("pct_encours")
    if pct is None or pct <= 0:
        return None
    passees = _sommes_glissantes(serie, quotidiens, 7)
    if len(passees) >= cfg["releves_min"]:
        seuil = max(cfg["seuil_min_pct"], mean(passees) + cfg["ecarts_types"] * pstdev(passees))
        base = f"au-delà de la moyenne des semaines précédentes plus {cfg['ecarts_types']} écarts-types ({nb(seuil, 1)} %)"
    else:
        seuil = cfg["seuil_absolu_pct"]
        base = f"au-delà du seuil fixe de {nb(seuil, 1)} % (trop peu de semaines relevées pour une comparaison)"
    if pct <= seuil:
        return None
    return {"signale": True, "pct_semaine": round(pct, 2), "seuil_pct": round(seuil, 2),
            "texte": f"Position possiblement encombrée : entrées de {nb(pct, 1)} % de l'encours en une semaine, {base}. "
                     "Un afflux rapide peut se retourner aussi vite."}


def tendance_flux(pct: float | None, seuil_stable: float) -> str | None:
    if pct is None:
        return None
    return "stable" if abs(pct) < seuil_stable else "entrées nettes" if pct > 0 else "sorties nettes"


def cumul(serie: list[dict], quotidiens: list[dict], fin: date, jours: int = 91) -> list[list]:
    """Flux cumulés (M$) jour par jour sur les « jours » derniers jours, à partir de 0 au premier relevé
    de la période : graphique de la fiche pays."""
    debut = (fin - timedelta(days=jours)).isoformat()
    bases = [r["date"] for r in serie if r["date"] <= debut]
    depart = bases[-1] if bases else serie[0]["date"]
    total, res = 0.0, [[depart, 0.0]]
    for q in quotidiens:
        if q["date"] > depart:
            total += q["flux"]
            res.append([q["date"], round(total / 1e6, 2)])
    return res if len(res) > 1 else []


# ------------------------------------------------------------------ indicateur « Flux étrangers » d'un pays

def indicateur(etf: str | None, emetteur: str | None, choix: dict | None, serie: list[dict], config_flux: dict,
               aujourdhui: date) -> dict:
    """Bloc detail.flux_etrangers d'un pays (valeur = flux sur 1 mois en % de l'encours, ou 1 semaine
    tant que le mois est en cours de constitution)."""
    base = {"libelle": LIBELLE, "unite": "%", "avertissement": AVERTISSEMENT}
    if not etf:
        return {**base, "valeur": None, "note": None, "disponible": False,
                "raison": "aucun ETF pays coté aux États-Unis pour ce pays"}
    if not emetteur:
        return {**base, "valeur": None, "note": None, "disponible": False, "symbole": etf,
                "raison": f"émetteur de {etf} non configuré"}
    sources = (choix or {}).get("sources", [])
    if not serie:
        return {**base, "valeur": None, "note": None, "disponible": False, "symbole": etf, "sources": sources,
                "verification": "aucune_source", "raison": "aucun relevé des parts en circulation"}
    fin = _j(serie[-1]["date"])
    if (aujourdhui - fin).days > config_flux["fraicheur_max_jours"]:
        return {**base, "valeur": None, "note": None, "disponible": False, "symbole": etf, "sources": sources,
                "verification": "aucune_source", "raison": f"dernier relevé trop ancien ({serie[-1]['date']})"}
    quotidiens = flux_quotidiens(serie, config_flux["variation_parts_max_pct"])
    periodes = {cle: {"libelle": p["libelle"], **_periode(serie, quotidiens, fin, p["jours"])}
                for cle, p in config_flux["periodes"].items()}
    dernier = serie[-1]
    retenu_auj = (choix or {}).get("retenu") or {}
    source = retenu_auj.get("source") or dernier.get("source") or emetteur
    commun = {**base, "symbole": etf, "emetteur": COURTS.get(emetteur, emetteur), "date": dernier["date"],
              "source": NOMS.get(source, "{etf}").format(etf=etf) + " ; relevés jour par jour accumulés par l'agent",
              "source_courte": COURTS.get(source, source), "niveau_source": "marche", "frequence": "quotidienne",
              "sources": sources, "verification": (choix or {}).get("verification") or "source_unique", "ecart_max": None,
              "periodes": periodes, "releves": len(serie), "premier_releve": serie[0]["date"],
              "encours_musd": round(dernier["parts"] * dernier["vl"] / 1e6, 1), "parts": dernier["parts"], "vl": round(dernier["vl"], 4),
              "serie_consecutive": serie_consecutive(quotidiens), "cumul": cumul(serie, quotidiens, fin),
              "flux_dernier_jour_musd": round(quotidiens[-1]["flux"] / 1e6, 2) if quotidiens and quotidiens[-1]["date"] == dernier["date"] else None}
    if commun["verification"] == "aucune_source":
        commun["verification"] = "source_unique"  # valeur issue de l'historique (relevés passés)
    choisie = next((k for k in ("1m", "1s") if periodes.get(k, {}).get("complet")), None)
    if not choisie:
        jours = periodes["1s"]["jours_disponibles"] if "1s" in periodes else 0
        # La fiche montre quand même les cumuls partiels, marqués « en cours de constitution »
        return {**commun, "valeur": None, "note": None, "disponible": False, "periode_valeur": None,
                "raison": f"relevés en cours de constitution ({len(serie)} relevé{'s' if len(serie) > 1 else ''}, "
                          f"{jours} jour{'s' if jours > 1 else ''} ; une semaine complète est nécessaire)"}
    p = periodes[choisie]
    enc = encombrement(serie, quotidiens, periodes["1s"], config_flux["encombrement"]) if "1s" in periodes else None
    ind = {**commun, "valeur": p["pct_encours"], "periode_valeur": choisie, "flux_musd": p["flux_musd"],
           "tendance_flux": tendance_flux(p["pct_encours"], config_flux["seuil_stable_pct"])}
    if enc:
        ind["encombrement"] = enc
    return ind


def noter(ind: dict, config_flux: dict) -> int | None:
    if ind.get("valeur") is None:
        return None
    note = notation.note_flux(ind["valeur"], ind.get("periode_valeur") or "1m")
    if ind.get("encombrement"):
        note = min(note, config_flux["encombrement"]["plafond_note"])
    return note


# ------------------------------------------------------------------ signaux pour le chef d'orchestre

def signaux(code: str, nom: str, etf: str, serie: list[dict], config_flux: dict, aujourdhui: date) -> list[dict]:
    """Inversion de tendance des flux ; entrées ou sorties inhabituelles le dernier jour."""
    cfg = config_flux["signaux"]
    if len(serie) < 2 or (aujourdhui - _j(serie[-1]["date"])).days > config_flux["fraicheur_max_jours"]:
        return []
    quotidiens = flux_quotidiens(serie, config_flux["variation_parts_max_pct"])
    if not quotidiens:
        return []
    fin = _j(serie[-1]["date"])
    res = []
    source = f"{COURTS.get(serie[-1].get('source'), serie[-1].get('source'))} (ETF {etf}, cotés aux États-Unis)"

    # Inversion : dernière semaine contre les trois précédentes
    if (fin - _j(serie[0]["date"])).days >= cfg["inversion_jours_min"]:
        bascule = fin - timedelta(days=7)
        avant = [r for r in serie if _j(r["date"]) <= bascule]
        p_recent = _periode(serie, quotidiens, fin, 7)
        p_avant = _periode(avant, [q for q in quotidiens if _j(q["date"]) <= bascule], bascule, 21) if avant else None
        if p_avant and p_avant["complet"] and p_recent["complet"]:
            a, r = p_avant["pct_encours"], p_recent["pct_encours"]
            if a is not None and r is not None and abs(a) >= cfg["inversion_min_pct"] and abs(r) >= cfg["inversion_min_pct"] and (a > 0) != (r > 0):
                vers = "entrées" if r > 0 else "sorties"
                res.append({"date": serie[-1]["date"], "type": "inversion_flux", "cle": code, "importance": "moyenne",
                            "titre": f"{nom} : les flux de l'ETF {etf} passent des {'sorties' if r > 0 else 'entrées'} aux {vers}",
                            "explication": f"{nb(r, 1, True)} % de l'encours sur la dernière semaine, après {nb(a, 1, True)} % "
                                           f"sur les trois semaines précédentes. {AVERTISSEMENT}",
                            "source": source})

    # Flux du dernier jour inhabituel
    q = quotidiens[-1]
    if q["date"] == serie[-1]["date"]:
        passes = [x["pct"] for x in quotidiens[:-1]]
        if len(passes) >= cfg["jour_releves_min"]:
            seuil = max(cfg["jour_min_pct"], abs(mean(passes)) + cfg["jour_ecarts_types"] * pstdev(passes))
            comparaison = f"au-delà de {nb(seuil, 1)} % (moyenne des jours précédents plus {cfg['jour_ecarts_types']} écarts-types)"
        else:
            seuil = cfg["jour_absolu_pct"]
            comparaison = f"au-delà du seuil fixe de {nb(seuil, 1)} % (trop peu de jours relevés pour une comparaison)"
        if abs(q["pct"]) > seuil:
            entree = q["pct"] > 0
            res.append({"date": q["date"], "type": "entrees_inhabituelles" if entree else "sorties_inhabituelles", "cle": code,
                        "importance": "forte" if abs(q["pct"]) > 2 * seuil else "moyenne",
                        "titre": f"{nom} : {'entrées' if entree else 'sorties'} inhabituelles sur l'ETF {etf}",
                        "explication": f"{nb(q['flux'] / 1e6, 1, True)} M$ en une séance, soit {nb(q['pct'], 1, True)} % de l'encours, "
                                       f"{comparaison}." + (" Un afflux très fort peut signaler une position encombrée." if entree else "")
                                       + f" {AVERTISSEMENT}",
                        "source": source})
    return res


def ecrire_signaux(chemin: Path, nouveaux: list[dict], aujourdhui: date, version: str) -> bool:
    """data/signaux/pays.json : signaux candidats pour le chef d'orchestre (180 derniers jours, sans doublon)."""
    from ..commun.sortie import enveloppe
    existant = lire_json(chemin) or {}
    anciens = existant.get("donnees") or []
    vus = {(s["type"], s["cle"], s["date"]) for s in anciens}
    limite = (aujourdhui - timedelta(days=180)).isoformat()
    tous = sorted((s for s in anciens + [s for s in nouveaux if (s["type"], s["cle"], s["date"]) not in vus] if s["date"] >= limite),
                  key=lambda s: (s["date"], s["cle"], s["type"]), reverse=True)
    if existant and tous == anciens:
        return False
    ecrire_json(chemin, enveloppe(tous, "agent-pays", fictif=False, version_agent=version,
                                  description="Signaux candidats pour le chef d'orchestre (180 derniers jours) : "
                                              "flux d'investissement des ETF pays cotés aux États-Unis"))
    return True
