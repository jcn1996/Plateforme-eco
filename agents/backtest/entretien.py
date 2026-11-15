"""
Entretien de la méthode du chef d'orchestre et du trader (sous validation humaine).

Chaque mois, le backtest compare les combinaisons en service (agents/chef/config.json → selections, lues par
agents/chef/selections.py ; l'agent trader prend ses candidats dans ces sélections) à son nouveau rapport :

1. dans le lot (entreprises, matières premières) : chaque combinaison en service est rejugée hors échantillon avec
   les règles du rapport (correction de Holm sur leur nombre) ; la meilleure combinaison du rapport qui n'est pas en
   service est retenue comme candidate si elle passe le seuil corrigé des essais (Bonferroni) sur l'apprentissage ET
   bat l'indice et le momentum seul hors échantillon ; le panier « union » (actif retenu par au moins une combinaison)
   est évalué pour chaque changement possible ;
2. à l'assemblage (`decider`) : garde-fous contre le sur-ajustement —
   - retrait seulement si la combinaison est « Non confirmée » deux mois de suite ;
   - ajout seulement d'une candidate, une seule nouvelle combinaison par trimestre (toutes poches confondues) ;
   - aucun changement si le panier proposé ne fait pas mieux hors échantillon que le panier actuel (écart à l'indice
     plus élevé, écart au momentum seul pas plus faible) ;
3. la proposition est écrite dans data/backtest/proposition-AAAA-MM.json (appliquée seulement par la pull request
   que le workflow ouvre) et l'historique dans data/backtest/recalibrages.json (date, changement, validé ou non).
"""
from __future__ import annotations

from itertools import combinations
from pathlib import Path

from ..commun import methode as M
from . import combinaisons as CB
from . import reference as RF

RIEN = "Recalibrage du mois : rien à modifier"
COURT = {"entreprises": "entreprises", "matieres": "matières premières"}
AGENTS = {"pays": "agent pays", "chef": "chef d'orchestre", "entreprises": "agent entreprises", "matieres_premieres": "agent matières premières"}
CLES_VERIF = ("mois", "rendement_annuel_pct", "vs_indice_annuel_pct", "t_vs_indice", "vs_momentum_annuel_pct", "t_vs_momentum")


def _verif(ev: dict) -> dict:
    v = ev["comparaison"].get("verification") or {}
    return {k: v.get(k) for k in CLES_VERIF}


def cle_de(signaux: list[str]) -> str:
    return "+".join(signaux)


def _n(x, d=1, unite=" pt/an") -> str:
    if x is None:
        return "n. d."
    return f"{'+' if x > 0 else ''}{x:.{d}f}".replace(".", ",").replace("-", "−") + unite


# ------------------------------------------------------------------ 1. dans le lot

def evaluer_lot(en_service: list[dict], combis: dict, signaux: dict, prix, indice, momentum_r, frais_pct: float, separation,
                cfg_comb: dict, cfg: dict, libelles: dict) -> dict:
    """Combinaisons en service rejugées, candidate à l'ajout, panier union de chaque changement possible."""
    seuil = cfg_comb["seuil_percentile"]
    indice_r = RF.indice_mensuel(prix, indice)

    def masque(sigs):
        return CB.masque_combine([signaux[k].reindex(index=prix.index, columns=prix.columns) for k in sigs], seuil)
    masques, essais, service = {}, [], []
    for c in en_service:
        manquants = [s for s in c["signaux"] if s not in signaux]
        if manquants:
            service.append({"cle": c["cle"], "libelle": c["libelle"], "signaux": c["signaux"], "verdict": "Non évaluable",
                            "raison": f"signal absent du backtest : {', '.join(manquants)}"})
            continue
        masques[c["cle"]] = masque(c["signaux"])
        ev = CB.evaluer(masques[c["cle"]], prix, indice, indice_r, momentum_r, frais_pct, separation)
        essais.append({"signaux": c["signaux"], "ev": ev, "t_app": ev["comparaison"].get("apprentissage", {}).get("t_vs_indice"), "_c": c})
    for e, j in zip(essais, CB.juger(essais, cfg_comb["alpha"], libelles)):
        service.append({"cle": e["_c"]["cle"], "libelle": e["_c"]["libelle"], "signaux": j["signaux"], "verdict": j["verdict"],
                        "t_apprentissage": j["t_apprentissage"], "p_holm": j["p_holm"], "taille_moyenne": j["taille_moyenne"],
                        "verification": _verif(e["ev"])})
    # Candidate à l'ajout : parmi les combinaisons retenues par le rapport, hors service
    seuil_t = combis.get("seuil_t_bonferroni")
    deja = {frozenset(c["signaux"]) for c in en_service}
    exclus = tuple(cfg.get("prefixes_exclus") or ())
    cands, ecartees = [], []
    for x in combis.get("retenues") or []:
        if frozenset(x["signaux"]) in deja:
            continue
        v = (x.get("comparaison") or {}).get("verification") or {}
        t = x.get("t_apprentissage")
        raisons = []
        if exclus and any(s.startswith(exclus) for s in x["signaux"]):
            raisons.append("signal en variation, non calculé au quotidien par les agents")
        if seuil_t is None or t is None or t < seuil_t:
            raisons.append(f"sous le seuil corrigé des essais sur l'apprentissage (t = {_n(t, 2, '')}, seuil {_n(seuil_t, 2, '')})")
        if not (v.get("vs_indice_annuel_pct") or 0) > 0:
            raisons.append("ne bat pas l'indice hors échantillon")
        if v.get("vs_momentum_annuel_pct") is None or v["vs_momentum_annuel_pct"] <= 0:
            raisons.append("ne bat pas le momentum seul hors échantillon")
        d = {"cle": cle_de(x["signaux"]), "signaux": x["signaux"], "libelle": x["libelle"], "verdict": x["verdict"], "t_apprentissage": t,
             "seuil_t": seuil_t, "verification": {k: v.get(k) for k in CLES_VERIF}}
        (ecartees if raisons else cands).append(d | ({"raisons": raisons} if raisons else {}))
    candidat = max(cands, key=lambda d: d["t_apprentissage"]) if cands else None
    # Panier union pour chaque changement possible (retraits parmi les « Non confirmée » de ce mois, ajout éventuel)
    if candidat:
        masques[candidat["cle"]] = masque(candidat["signaux"])
    en_place = [s["cle"] for s in service if s["cle"] in masques]
    nc = [s["cle"] for s in service if s["verdict"] == "Non confirmée"]
    scenarios = []
    for r in range(len(nc) + 1):
        for ret in combinations(nc, r):
            for aj in [None] + ([candidat["cle"]] if candidat else []):
                cles = [k for k in en_place if k not in ret] + ([aj] if aj else [])
                if not cles:
                    continue
                m = masques[cles[0]]
                for k in cles[1:]:
                    m = m | masques[k]
                ev = CB.evaluer(m, prix, indice, indice_r, momentum_r, frais_pct, separation)
                scenarios.append({"retire": sorted(ret), "ajoute": aj, "taille_moyenne": ev["taille_moyenne"], "verification": _verif(ev)})
    return {"en_service": service, "candidat": candidat, "ecartees": ecartees, "scenarios": scenarios,
            "regle": "panier union : actif retenu par au moins une combinaison, équipondéré, mensuel, frais compris"}


# ------------------------------------------------------------------ 2. décision (assemblage)

def mois_precedent(mois: str) -> str:
    a, m = int(mois[:4]), int(mois[5:7])
    return f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"


def trimestre(mois: str) -> tuple[int, int]:
    return int(mois[:4]), (int(mois[5:7]) - 1) // 3 + 1


def _scenario(ent: dict, retire: list[str], ajoute: str | None) -> dict | None:
    return next((s for s in ent.get("scenarios") or [] if s["retire"] == sorted(retire) and s["ajoute"] == ajoute), None)


def ameliore(sc: dict | None, base: dict | None) -> bool:
    if not sc or not base:
        return False
    a, b = sc["verification"], base["verification"]
    if a.get("vs_indice_annuel_pct") is None or b.get("vs_indice_annuel_pct") is None:
        return False
    if a["vs_indice_annuel_pct"] <= b["vs_indice_annuel_pct"]:
        return False
    am, bm = a.get("vs_momentum_annuel_pct"), b.get("vs_momentum_annuel_pct")
    return am is None or bm is None or am >= bm


def decider(sections: dict, historique: list[dict], mois: str, selections: dict, cfg: dict) -> dict:
    """Proposition de recalibrage des combinaisons : {"verdicts", "changements", "refus", "modifications", "effets"}."""
    prec = next((e for e in historique if e.get("mois") == mois_precedent(mois)), None)
    t = trimestre(mois)
    ajouts = [e for e in historique if e.get("mois") != mois and trimestre(e["mois"]) == t and e.get("statut") in ("à valider", "validé")
              and any(c.get("action") == "ajouter" for c in e.get("changements") or [])]
    verdicts, plans, refus = {}, {}, []
    for classe in cfg["classes"]:
        ent = (sections.get(classe) or {}).get("entretien")
        if not ent or not ent.get("en_service"):
            refus.append(f"{COURT.get(classe, classe)} : combinaisons non évaluées ce mois-ci (lot non calculé)")
            continue
        verdicts[classe] = {x["cle"]: x["verdict"] for x in ent["en_service"]}
        retirer = []
        for x in ent["en_service"]:
            if x["verdict"] != "Non confirmée":
                continue
            avant = ((prec or {}).get("verdicts") or {}).get(classe, {}).get(x["cle"])
            if avant == "Non confirmée":
                retirer.append(x)
            else:
                refus.append(f"{x['libelle']} « Non confirmée » ce mois-ci, pas le mois précédent : conservée (retrait seulement après deux mois de suite)")
        plans[classe] = {"ent": ent, "retirer": retirer}
    # Ajout : une seule nouvelle combinaison par trimestre, la candidate au meilleur t d'apprentissage d'abord
    cands = sorted(((c, p["ent"]["candidat"]) for c, p in plans.items() if p["ent"].get("candidat")), key=lambda x: -x[1]["t_apprentissage"])
    choisi = None
    if cands and len(ajouts) >= cfg.get("ajouts_par_trimestre", 1):
        refus.append(f"ajout de {cands[0][1]['libelle']} reporté : une nouvelle combinaison a déjà été proposée ce trimestre ({ajouts[-1]['mois']})")
    elif cands:
        for classe, c in cands:
            base = _scenario(plans[classe]["ent"], [], None)
            sc = _scenario(plans[classe]["ent"], [x["cle"] for x in plans[classe]["retirer"]], c["cle"])
            if ameliore(sc, base):
                choisi = classe
                break
            refus.append(f"ajout de {c['libelle']} écarté : le panier {COURT.get(classe, classe)} ne ferait pas mieux hors échantillon")
    changements, modifications, effets = [], [], {}
    for classe, p in plans.items():
        ent = p["ent"]
        ajout = ent["candidat"] if classe == choisi else None
        retirer = p["retirer"]
        evaluables = [x for x in ent["en_service"] if x["verdict"] != "Non évaluable"]
        if retirer and not ajout and len(retirer) >= len(evaluables):
            refus.append(f"{COURT.get(classe, classe)} : dernière combinaison de la poche conservée faute de remplaçante")
            retirer = []
        if not retirer and not ajout:
            continue
        base = _scenario(ent, [], None)
        sc = _scenario(ent, [x["cle"] for x in retirer], ajout["cle"] if ajout else None)
        if not ameliore(sc, base):
            refus.append(f"{COURT.get(classe, classe)} : le changement n'améliore pas le résultat hors échantillon "
                         f"({_n((base or {}).get('verification', {}).get('vs_indice_annuel_pct'))} → "
                         f"{_n((sc or {}).get('verification', {}).get('vs_indice_annuel_pct'))} face à l'indice) : rien à modifier")
            continue
        actuel = selections[classe]["combinaisons"]
        enleves = {x["cle"] for x in retirer}
        propose = [dict(c) for c in actuel if c["cle"] not in enleves]
        for x in retirer:
            changements.append({"classe": classe, "action": "retirer", "cle": x["cle"], "libelle": x["libelle"],
                                "raison": "« Non confirmée » hors échantillon deux mois de suite "
                                          f"(écart à l'indice {_n(x['verification'].get('vs_indice_annuel_pct'))})"})
        if ajout:
            propose.append({"cle": ajout["cle"], "signaux": ajout["signaux"], "libelle": ajout["libelle"]})
            v = ajout["verification"]
            changements.append({"classe": classe, "action": "ajouter", "cle": ajout["cle"], "libelle": ajout["libelle"], "signaux": ajout["signaux"],
                                "raison": (f"passe le seuil corrigé des essais sur l'apprentissage (t = {_n(ajout['t_apprentissage'], 2, '')}, "
                                           f"seuil {_n(ajout['seuil_t'], 2, '')}) et bat hors échantillon l'indice "
                                           f"({_n(v.get('vs_indice_annuel_pct'))}) et le momentum seul ({_n(v.get('vs_momentum_annuel_pct'))})")})
        effets[classe] = {"avant": base["verification"], "apres": sc["verification"]}
        modifications.append({"agent": "chef", "fichier": cfg["fichier"], "chemin": ["selections", classe, "combinaisons"], "type": "combinaisons",
                              "actuel": actuel, "propose": propose, "retenue": True,
                              "raison": " ; ".join(f"{c['action']} {c['libelle']} : {c['raison']}" for c in changements if c["classe"] == classe),
                              "effet": effets[classe]})
    return {"verdicts": verdicts, "changements": changements, "refus": refus, "modifications": modifications, "effets": effets}


# ------------------------------------------------------------------ 3. historique

def texte_changement(changements: list[dict]) -> str:
    if not changements:
        return "rien à modifier"
    morceaux = [f"{'retrait' if c['action'] == 'retirer' else 'ajout'} de « {c['libelle']} » ({COURT.get(c['classe'], c['classe'])})"
                for c in changements if c["action"] != "pondérations"]
    agents = []
    for c in changements:
        if c["action"] == "pondérations" and AGENTS.get(c["classe"], c["classe"]) not in agents:
            agents.append(AGENTS.get(c["classe"], c["classe"]))
    if agents:
        morceaux.append(f"nouvelles pondérations ({', '.join(agents)})")
    return " ; ".join(morceaux)


def entree(jour: str, decision: dict, ponderations: list[dict], rapport: str) -> dict:
    """Ligne d'historique du mois. `ponderations` : propositions de pondérations retenues (ancien mécanisme)."""
    changements = list(decision["changements"]) + [
        {"classe": p["agent"], "action": "pondérations", "libelle": f"{p['fichier']} → {' → '.join(p['chemin'])}", "raison": p.get("raison")}
        for p in ponderations]
    mods = [{"fichier": m["fichier"], "chemin": m["chemin"], "type": m.get("type", "ponderations"), "propose": m["propose"]}
            for m in decision["modifications"] + ponderations]
    statut = "à valider" if mods else "rien à modifier"
    return {"mois": jour[:7], "jour": jour, "rapport": rapport, "verdicts": decision["verdicts"], "changements": changements,
            "texte": RIEN if not mods else f"Recalibrage du mois à valider : {texte_changement(changements)}",
            "refus": decision["refus"], "effets": decision["effets"], "modifications": mods, "statut": statut, "pull_request": None,
            "valide_le": None}


def mettre_a_jour_statuts(historique: list[dict], racine: Path, jour: str) -> None:
    """Validé si les réglages proposés sont en service (pull request fusionnée) ; une proposition d'un mois antérieur
    toujours absente des réglages est « non validé »."""
    for e in historique:
        if e.get("statut") in ("à valider", "non validé"):
            if M.appliquee(e, racine):
                e["statut"], e["valide_le"] = "validé", jour
            elif e["mois"] < jour[:7]:
                e["statut"] = "non validé"


def enregistrer(historique: list[dict], e: dict) -> list[dict]:
    """Remplace la ligne du même mois (nouvelle exécution), en gardant le lien de pull request si la proposition est la même."""
    ancien = next((x for x in historique if x.get("mois") == e["mois"]), None)
    if ancien and ancien.get("pull_request") and ancien.get("modifications") == e["modifications"]:
        e["pull_request"] = ancien["pull_request"]
    return sorted([x for x in historique if x.get("mois") != e["mois"]] + [e], key=lambda x: x["mois"])


def noter_pull_request(historique: list[dict], mois: str, url: str) -> bool:
    for e in historique:
        if e.get("mois") == mois and e.get("statut") == "à valider":
            e["pull_request"] = url
            return True
    return False


# ------------------------------------------------------------------ 4. description de la pull request

def corps_pull_request(proposition: dict) -> str:
    """Dix lignes au plus, en langage simple : ce qui change, pourquoi, effet attendu, limites."""
    r = proposition.get("recalibrage") or {}
    mois = proposition["jour"][:7]
    ch = r.get("changements") or []
    lignes = [f"**Recalibrage du backtest de {mois}, à valider à la main** : rien n'est fusionné automatiquement ; tant que cette pull request "
              "n'est pas fusionnée, le chef d'orchestre et le trader gardent la méthode actuelle.",
              f"**Ce qui change** : {texte_changement(ch)}."]
    pourquoi = [f"{c['libelle']} : {c['raison']}" for c in ch if c.get("raison")]
    if pourquoi:
        lignes.append("**Pourquoi** : " + " ; ".join(pourquoi) + ".")
    eff = [f"panier {COURT.get(k, k)} {_n(v['avant'].get('vs_indice_annuel_pct'))} → {_n(v['apres'].get('vs_indice_annuel_pct'))} face à l'indice, "
           f"{_n(v['avant'].get('vs_momentum_annuel_pct'))} → {_n(v['apres'].get('vs_momentum_annuel_pct'))} face au momentum seul"
           for k, v in (r.get("effets") or {}).items()]
    if any(c["action"] == "pondérations" for c in ch):
        eff.append("pondérations : meilleure note hors échantillon (IC et écart après frais, détail dans le rapport)")
    lignes.append("**Effet attendu** (seconde moitié de l'historique, frais compris) : " + (" ; ".join(eff) or "voir le rapport") + ".")
    lignes.append("**Limites** : la seconde moitié de l'historique a déjà servi à juger, ce n'est pas un vrai test sur l'avenir ; univers actuel "
                  "(biais du survivant atténué, pas annulé) ; écarts souvent non significatifs ; garde-fous : retrait après deux mois "
                  "« Non confirmée », un ajout par trimestre au plus.")
    lignes.append(f"Détail : `data/backtest/rapport-{mois}.md` (section « Entretien de la méthode ») · méthode : `agents/backtest/methode.md`.")
    return "\n".join(lignes[:10]) + "\n"
