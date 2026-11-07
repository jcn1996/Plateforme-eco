"""
Allocation modèle indicative (trois profils, structure cœur-satellite). Méthode : methode.md, § Allocation.

1. Répartition par classe : cible du profil, infléchie selon le score moyen de la classe (± inflexion_max),
   avec une part minimale de liquidités fixée par le palier de risque.
2. Satellites : convictions fortes à verdict positif, prélevées sur les classes risquées (actions, or, matières).
3. Cœur : lignes de chaque classe pondérées par leur score (verdicts « Alléger » et « Éviter » exclus).
4. Contraintes : maximum par pays, par secteur, par thème et par ligne (redistribution itérative).
5. Rotation limitée : un écart de moins de `rotation_seuil` point avec l'allocation précédente est ignoré.
"""
from __future__ import annotations

from ..risque.calculs import fr

CLASSE_DE = {"pays": "actions", "entreprises": "actions", "obligations": "obligations", "or": "or", "matieres": "matieres", "liquidites": "liquidites"}
LIBELLES = {"actions": "Actions", "obligations": "Obligations", "or": "Or", "matieres": "Matières premières", "liquidites": "Liquidités"}


def _moyenne(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def repartir(lignes: list[dict], total: float, plancher: float) -> dict[str, float]:
    """Poids ∝ (score − plancher), au moins 1 point de score."""
    if not lignes or total <= 0:
        return {}
    p = {l["id"]: max(1.0, (l.get("score") or 50) - plancher) for l in lignes}
    s = sum(p.values())
    return {k: total * v / s for k, v in p.items()}


def plafonner(poids: dict[str, float], plafond_de, groupes_de=None, max_groupe: dict | None = None, iterations: int = 20) -> dict[str, float]:
    """Plafonne chaque ligne (plafond_de(id)) et chaque groupe, puis redistribue l'excédent aux lignes non plafonnées."""
    poids = dict(poids)
    total = sum(poids.values())
    for _ in range(iterations):
        exces, bloques = 0.0, set()
        for k, v in poids.items():
            cap = plafond_de(k)
            if cap is not None and v > cap:
                exces += v - cap
                poids[k] = cap
                bloques.add(k)
        if groupes_de and max_groupe:
            somme = {}
            for k, v in poids.items():
                for g in groupes_de(k):
                    somme[g] = somme.get(g, 0) + v
            for g, v in somme.items():
                cap = max_groupe.get(g)
                if cap is not None and v > cap:
                    membres = [k for k in poids if g in groupes_de(k)]
                    f = cap / v
                    for k in membres:
                        exces += poids[k] * (1 - f)
                        poids[k] *= f
                        bloques.add(k)
        if exces < 1e-6:
            break
        libres = {k: v for k, v in poids.items() if k not in bloques and v > 0}
        if not libres:
            break
        s = sum(libres.values())
        for k, v in libres.items():
            poids[k] += exces * v / s
    # garde le total (arrondis)
    s = sum(poids.values())
    return {k: v * total / s for k, v in poids.items()} if s else poids


def construire(lignes: list[dict], palier: str, precedente: dict | None, config: dict) -> dict:
    ca = config["allocation"]
    par_classe = {}
    for l in lignes:
        if l.get("score") is None:
            continue
        par_classe.setdefault(CLASSE_DE[l["type"]], []).append(l)
    scores_classe = {c: _moyenne([l["score"] for l in ls if l["type"] != "entreprises"] or [l["score"] for l in ls]) for c, ls in par_classe.items()}
    liq_min = ca["liquidites_min_par_palier"].get(palier, 5)
    res = {}
    for cle, prof in ca["profils"].items():
        res[cle] = profil(cle, prof, par_classe, scores_classe, liq_min, (precedente or {}).get(cle), config)
    return {"profils": res, "palier": palier, "liquidites_min": liq_min,
            "scores_classes": {c: round(s, 1) for c, s in scores_classe.items() if s is not None},
            "contraintes": {k: ca[k] for k in ("max_pays", "max_secteur", "max_theme", "max_ligne", "max_ligne_satellite", "rotation_seuil")}}


def profil(cle: str, prof: dict, par_classe: dict, scores_classe: dict, liq_min: float, precedent: dict | None, config: dict) -> dict:
    ca = config["allocation"]
    avert = []
    # 1. classes
    classes = {}
    for c, base in prof["classes"].items():
        s = scores_classe.get(c)
        adj = 0 if s is None else max(-prof["inflexion_max"], min(prof["inflexion_max"], (s - 50) / 50 * prof["inflexion_max"] * 2))
        classes[c] = max(0.0, base + adj) if par_classe.get(c) else 0.0
    if classes.get("liquidites", 0) < liq_min:
        classes["liquidites"] = liq_min
    autres = sum(v for c, v in classes.items() if c != "liquidites")
    for c in classes:
        if c != "liquidites" and autres:
            classes[c] = classes[c] * (100 - classes["liquidites"]) / autres
    # 2. satellites
    toutes = [l for ls in par_classe.values() for l in ls]
    sat = [l for l in toutes if l.get("conviction") == "forte" and l.get("verdict") in ("Renforcer", "Renforcer fortement") and CLASSE_DE[l["type"]] in ("actions", "or", "matieres")]
    sat.sort(key=lambda l: -l["score"])
    sat = sat[:ca["satellites_max"]]
    budget = prof["satellite"] if sat else 0
    poids_sat = {}
    if sat:
        par = min(ca["max_ligne_satellite"], budget / len(sat))
        poids_sat = {l["id"]: par for l in sat}
        budget = sum(poids_sat.values())
        risquees = sum(classes[c] for c in ("actions", "or", "matieres") if c in classes)
        for c in ("actions", "or", "matieres"):
            if c in classes and risquees:
                classes[c] -= budget * classes[c] / risquees
    else:
        avert.append("Aucune conviction forte à verdict positif : pas de satellite, tout est dans le cœur.")
    # 3. cœur
    coeur = {}
    exclus = ("Alléger", "Éviter")
    for c, total in classes.items():
        cands = [l for l in par_classe.get(c, []) if l["type"] != "entreprises" and l.get("verdict") not in exclus and l["id"] not in poids_sat]
        if c == "actions":
            cands = sorted(cands, key=lambda l: -l["score"])[:ca["pays_coeur_max"]]
        if c == "matieres":
            cands = sorted(cands, key=lambda l: -l["score"])[:3]
        if not cands and total > 0:
            # aucune ligne éligible : la part passe en liquidités
            avert.append(f"{LIBELLES[c]} : aucune ligne éligible (toutes « Alléger » ou « Éviter ») ; la part passe en liquidités.")
            classes["liquidites"] = classes.get("liquidites", 0) + total
            classes[c] = 0
            continue
        coeur.update(repartir(cands, total, 40 if c != "liquidites" else 0))
    if classes.get("liquidites") and not any(l["id"] in coeur for l in par_classe.get("liquidites", [])):
        coeur.update(repartir(par_classe.get("liquidites", []), classes["liquidites"], 0))
    poids = {**coeur, **poids_sat}
    lignes = {l["id"]: l for l in toutes}
    # 4. contraintes
    themes_cfg = config["themes"]["liste"]

    def groupes(k):
        l = lignes[k]
        g = [f"theme:{t}" for t in (l.get("themes") or [])]
        if l.get("pays") and l["type"] in ("pays", "entreprises"):
            g.append(f"pays:{l['pays']}")
        if l.get("secteur"):
            g.append(f"secteur:{l['secteur']}")
        return g
    max_groupe = {}
    for k in poids:
        for g in groupes(k):
            max_groupe[g] = ca["max_theme"] if g.startswith("theme:") else ca["max_pays"] if g.startswith("pays:") else ca["max_secteur"]

    def cap(k):
        if k in poids_sat:
            return ca["max_ligne_satellite"]
        t = lignes[k]["type"]
        return None if t == "liquidites" else ca["max_ligne_obligations"] if t == "obligations" else ca["max_pays"] if t == "pays" else ca["max_ligne"]
    poids = plafonner(poids, cap, groupes, max_groupe)
    # 5. rotation limitée
    anciens = {l["id"]: l["poids"] for l in (precedent or {}).get("lignes", [])}
    stables = {k: anciens[k] for k, v in poids.items() if k in anciens and abs(v - anciens[k]) < ca["rotation_seuil"]}
    mobiles = {k: v for k, v in poids.items() if k not in stables}
    reste = 100 - sum(stables.values())
    s = sum(mobiles.values())
    if s > 0 and reste > 0:
        mobiles = {k: v * reste / s for k, v in mobiles.items()}
    poids = {**stables, **mobiles}
    poids = {k: v for k, v in poids.items() if v >= ca["ligne_min"]}
    s = sum(poids.values())
    poids = {k: v * 100 / s for k, v in poids.items()} if s else poids
    sortie = []
    for k, v in sorted(poids.items(), key=lambda kv: -kv[1]):
        l = lignes[k]
        ancien = anciens.get(k)
        var = None if ancien is None else round(v - ancien, 1)
        if ancien is None:
            just = f"Nouvelle ligne : verdict « {l['verdict']} », score {fr(l['score'], 0)}/100, conviction {l.get('conviction')}."
        elif abs(v - ancien) < 0.05:
            just = "Inchangée (écart inférieur au seuil de rotation)."
        else:
            just = f"{'Renforcée' if var > 0 else 'Allégée'} : verdict « {l['verdict']} », score {fr(l['score'], 0)}/100" + (
                f" (précédent {fr(l.get('score_precedent'), 0)})" if l.get("score_precedent") is not None else "") + "."
        sortie.append({"id": k, "nom": l["nom"], "type": l["type"], "classe": CLASSE_DE[l["type"]], "poche": "satellite" if k in poids_sat else "cœur",
                       "poids": round(v, 1), "variation": var, "verdict": l["verdict"], "conviction": l.get("conviction"), "justification": just})
    for k, ancien in anciens.items():
        if k not in poids:
            l = lignes.get(k)
            sortie.append({"id": k, "nom": (l or {}).get("nom", k), "type": (l or {}).get("type"), "classe": CLASSE_DE.get((l or {}).get("type"), "?"),
                           "poche": "sortie", "poids": 0.0, "variation": round(-ancien, 1), "verdict": (l or {}).get("verdict"),
                           "justification": f"Sortie de l'allocation : verdict « {(l or {}).get('verdict', 'n. d.')} »." if l else "Sortie de l'allocation : ligne plus analysée."})
    par_cl = {}
    for x in sortie:
        if x["poids"]:
            par_cl[x["classe"]] = round(par_cl.get(x["classe"], 0) + x["poids"], 1)
    # thèmes dominants
    for t, th in themes_cfg.items():
        part = sum(x["poids"] for x in sortie if t in (lignes.get(x["id"], {}).get("themes") or []))
        if part > ca["max_theme"] + 0.5:
            avert.append(f"Thème « {th['libelle']} » à {fr(part, 1)} % malgré le plafond de {ca['max_theme']} %.")
        elif part >= ca["max_theme"] * 0.8:
            avert.append(f"Thème « {th['libelle']} » proche du plafond : {fr(part, 1)} % (plafond {ca['max_theme']} %).")
    return {"libelle": prof["libelle"], "classes": par_cl, "classes_libelles": LIBELLES, "satellite_pct": round(sum(x["poids"] for x in sortie if x["poche"] == "satellite"), 1),
            "lignes": sortie, "avertissements": avert}
