"""
Stratégie de l'agent trader (démo) : cibles du portefeuille, ordres et règles de risque. Règles : regles.md.

1. Cœur (≈ 70 %) : allocation modèle du chef d'orchestre (profil de config.json), lignes « cœur » seulement, chaque
   ligne passant par son support coté (ETF pays, GLD, BNO/USO, SHY/IEF/TLT, ETF d'obligations européennes) ; les
   liquidités restent en euros.
2. Satellites (≈ 30 %) : convictions « forte » et « moyenne » à verdict positif (entreprises ; pays, matières et or
   seulement en conviction forte et hors du cœur), sans objection sérieuse du contradicteur, avec des signaux
   favorables d'au moins 2 agents indépendants ; taille ∝ conviction / volatilité, 8 % maximum par ligne ; plafonds
   par pays, secteur et thème repris du chef d'orchestre. Budget non utilisé : reversé au cœur.
3. Part minimale de liquidités selon le palier de l'agent risque.
4. Ordres : entrées et sorties de lignes, rééquilibrage seulement au-delà du seuil ; rotation mensuelle plafonnée
   (sorties imposées exceptées).
5. Risque (à chaque exécution) : stop des satellites (−15 %, suiveur une fois +20 % atteint, confirmé par 2 relevés),
   prise de bénéfices partielle à +30 %, sortie sur « Alléger » / « Éviter » ou objection sérieuse, plancher de
   liquidités.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..commun.sante import lire_iso
from ..risque.calculs import fr
from . import portefeuille as P

SORTIE = ("Alléger", "Éviter")
RANG_CONVICTION = {"forte": 3, "moyenne": 2, "faible": 1}
CLASSE_DE = {"pays": "actions", "secteurs": "actions", "entreprises": "actions", "obligations": "obligations", "or": "or", "matieres": "matieres", "liquidites": "liquidites"}
LIBELLES_CLASSES = {"actions": "Actions", "obligations": "Obligations", "or": "Or", "matieres": "Matières premières", "liquidites": "Liquidités"}


def ent(x) -> str:
    return "n. d." if x is None else str(int(round(x)))


# ------------------------------------------------------------------ lignes du chef d'orchestre

def lignes_chef(chef: dict) -> dict[str, dict]:
    res = {}
    for t in ("pays", "secteurs", "matieres", "obligations", "liquidites", "entreprises"):
        for l in chef.get(t) or []:
            res[l["id"]] = l
    if chef.get("or"):
        res[chef["or"]["id"]] = chef["or"]
    return res


def supports_de(ligne: dict, config: dict) -> list[dict]:
    """Supports cotés d'une ligne (liste vide : liquidités ou aucun support coté)."""
    cfg = config["supports"].get(ligne["id"])
    if cfg is not None:
        return [dict(s) for s in cfg]
    s = ligne.get("symbole")
    if not s or s.endswith("=F") or s.startswith("^"):
        return []
    if ligne["type"] == "pays":
        return [{"symbole": s, "nom": f"ETF {ligne['nom']} ({s})", "devise": "USD", "part": 1}]
    return [{"symbole": s, "nom": ligne.get("nom") or s, "devise": ligne.get("devise"), "part": 1}]


def agents_favorables(ligne: dict, seuil: float) -> list[str]:
    return sorted({f.get("agent") for f in (ligne.get("familles") or {}).values() if (f.get("note") or 0) >= seuil and f.get("agent")})


def objection_serieuse(ligne: dict | None) -> str | None:
    o = (ligne or {}).get("objection") or {}
    return o.get("objection") if o.get("serieuse") else None


def familles_resume(ligne: dict) -> dict:
    return {k: {"libelle": f.get("libelle", k), "note": f.get("note"), "agent": f.get("agent")} for k, f in (ligne.get("familles") or {}).items()}


def palier_min(palier: str, config: dict) -> float:
    return config["liquidites_min_par_palier"].get(palier, config["liquidites_min_par_palier"][config["palier_defaut"]])


# ------------------------------------------------------------------ volatilité

def volatilite(points: list, jours: int) -> float | None:
    """Volatilité annualisée (%) des rendements quotidiens sur les `jours` dernières séances."""
    c = [p[1] for p in points or [] if p[1]][-(jours + 1):]
    if len(c) < 20:
        return None
    r = [math.log(b / a) for a, b in zip(c, c[1:]) if a > 0 and b > 0]
    m = sum(r) / len(r)
    var = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(var) * math.sqrt(252) * 100


# ------------------------------------------------------------------ cibles

def cibles(chef: dict, palier: str, etat: dict, valo: dict, vols: dict, entrees_ko: set, config: dict, maintenant: datetime) -> dict:
    """Poids cibles (en % du portefeuille) par support, et sorties imposées.
    Renvoie {lignes: {symbole: {...}}, liquidites, sorties: {symbole: (motif, texte, imposée)}, satellites_ecartes, avertissements}."""
    lignes = lignes_chef(chef)
    avert, ecartes = [], []
    prof = ((chef.get("allocation") or {}).get("profils") or {}).get(config["profil"])
    if not prof:
        raise ValueError(f"profil « {config['profil']} » absent de l'allocation modèle du chef d'orchestre")
    contraintes = (chef.get("allocation") or {}).get("contraintes") or {}
    lim = {k: contraintes.get(k, v) for k, v in config["limites"].items() if not k.startswith("_")}
    res: dict[str, dict] = {}
    sorties: dict[str, tuple] = {}

    # 1. Cœur
    coeur_brut, cash, non_places = {}, 0.0, {}
    total_prof = 0.0
    for x in prof.get("lignes") or []:
        if x.get("poche") != "cœur" or not x.get("poids"):
            continue
        total_prof += x["poids"]
        l = lignes.get(x["id"])
        classe = x.get("classe") or CLASSE_DE.get((l or {}).get("type"), "?")
        if classe == "liquidites" or l is None:
            cash += x["poids"]
            if l is None:
                avert.append(f"{x.get('nom', x['id'])} : ligne de l'allocation absente des analyses ; part laissée en liquidités.")
            continue
        if l.get("verdict") in SORTIE:
            non_places[classe] = non_places.get(classe, 0) + x["poids"]
            continue
        sups = supports_de(l, config)
        if not sups:
            non_places[classe] = non_places.get(classe, 0) + x["poids"]
            avert.append(f"{l['nom']} : aucun support coté ; part redistribuée dans sa classe ({LIBELLES_CLASSES.get(classe, classe)}).")
            continue
        for s in sups:
            e = coeur_brut.setdefault(s["symbole"], {"poids": 0.0, "support": s, "ligne": l, "classe": classe})
            e["poids"] += x["poids"] * s.get("part", 1)
    for classe, v in non_places.items():
        membres = [k for k, e in coeur_brut.items() if e["classe"] == classe]
        s = sum(coeur_brut[k]["poids"] for k in membres)
        if s > 0:
            for k in membres:
                coeur_brut[k]["poids"] += v * coeur_brut[k]["poids"] / s
        else:
            cash += v
            avert.append(f"{LIBELLES_CLASSES.get(classe, classe)} : aucune ligne avec support coté ; part placée en liquidités.")
    facteur = config["poches"]["coeur"] / total_prof if total_prof else 0
    for k, e in coeur_brut.items():
        res[k] = {"cible": e["poids"] * facteur, "poche": "coeur", "classe": e["classe"], "support": e["support"], "ligne": e["ligne"]}
    cash *= facteur
    # lignes trop petites (sous le minimum) : redistribuées dans leur classe, sinon en liquidités
    mini_ligne = config["reequilibrage"]["ligne_min"]
    for k in sorted(res, key=lambda k: res[k]["cible"]):
        e = res[k]
        if e["cible"] >= mini_ligne:
            continue
        autres = [x for x in res if x != k and res[x]["classe"] == e["classe"] and res[x]["cible"] >= mini_ligne]
        s = sum(res[x]["cible"] for x in autres)
        if s:
            for x in autres:
                res[x]["cible"] += e["cible"] * res[x]["cible"] / s
        else:
            cash += e["cible"]
        avert.append(f"{e['support']['nom']} : cible de {fr(e['cible'], 2)} % sous le minimum de {fr(mini_ligne, 1)} % par ligne ; part redistribuée.")
        del res[k]

    # 2. Satellites : positions existantes
    cs = config["satellites"]
    budget = config["poches"]["satellite"]
    tenues = {}
    for s, p in etat["positions"].items():
        if p.get("poche") != "satellite":
            continue
        l = lignes.get(p.get("ligne_id"))
        if l is None:
            absent = p.setdefault("absent_depuis", maintenant.date().isoformat())
            jours = (maintenant.date() - datetime.fromisoformat(absent).date()).days
            if jours >= cs.get("absence_max_jours", 10):
                sorties[s] = ("sortie de l'analyse", f"{p['nom']} n'est plus analysée par le chef d'orchestre depuis {jours} jours : sortie.", False)
            else:
                tenues[s] = p.get("poids", 0)
            continue
        p.pop("absent_depuis", None)
        if l.get("verdict") in SORTIE:
            sorties[s] = ("sortie sur verdict", f"Le chef d'orchestre est passé à « {l['verdict']} » sur {l['nom']} (score {ent(l.get('score'))}/100).", True)
        elif objection_serieuse(l):
            sorties[s] = ("sortie sur objection", f"Objection sérieuse du contradicteur sur {l['nom']} : {objection_serieuse(l)}", True)
    # candidats
    cand = []
    for l in lignes.values():
        if l["type"] not in cs["types"] or l.get("verdict") not in cs["verdicts"]:
            continue
        conv = l.get("conviction")
        if conv not in cs["convictions"]:
            continue
        if l["type"] != "entreprises" and RANG_CONVICTION.get(conv, 0) < RANG_CONVICTION[cs["conviction_tactique_min"]]:
            continue
        sups = supports_de(l, config)
        if len(sups) != 1 or sups[0]["symbole"] in res:
            continue
        sym = sups[0]["symbole"]
        if sym in sorties:
            continue
        raison = None
        interdit = (etat.get("interdits") or {}).get(sym)
        if interdit and interdit["jusqua"] >= maintenant.date().isoformat() and sym not in etat["positions"]:
            raison = f"sortie récente ({interdit['motif']}) : pas de rachat avant le {interdit['jusqua']}"
        elif objection_serieuse(l):
            raison = "objection sérieuse du contradicteur"
        elif len(agents_favorables(l, cs["note_famille_positive"])) < cs["sources_independantes_min"]:
            raison = f"signaux favorables de moins de {cs['sources_independantes_min']} agents indépendants (une seule source)"
        elif {f.get("agent") for f in (l.get("familles") or {}).values()} & entrees_ko:
            raison = "données d'un agent utilisé périmées ou dégradées"
        if raison:
            if conv == "forte" or sym in etat["positions"]:
                ecartes.append({"id": l["id"], "nom": l["nom"], "raison": raison})
            if sym in etat["positions"] and sym not in sorties:
                tenues[sym] = etat["positions"][sym].get("poids", 0)
            continue
        cand.append((l, sups[0]))
    for s, p in etat["positions"].items():  # satellite tenu, verdict neutre ou conviction abaissée : conservé tel quel
        if p.get("poche") == "satellite" and s not in sorties and s not in tenues and not any(c[1]["symbole"] == s for c in cand):
            tenues[s] = p.get("poids", 0)
    cand.sort(key=lambda c: (-(RANG_CONVICTION.get(c[0].get("conviction"), 0)), -(c[0].get("score") or 0)))
    places = max(0, cs["max_lignes"] - len(tenues))
    for l, sup in cand[places:]:
        if l.get("conviction") == "forte":
            ecartes.append({"id": l["id"], "nom": l["nom"], "raison": f"nombre maximal de satellites atteint ({cs['max_lignes']})"})
    cand = cand[:places]

    # tailles : conviction / volatilité
    budget_libre = max(0.0, budget - sum(tenues.values()))
    brut = {}
    for l, sup in cand:
        v = vols.get(sup["symbole"])
        if v is None:
            v = cs["volatilite_par_type_defaut"].get(l["type"], cs["volatilite_defaut"])
        brut[sup["symbole"]] = cs["convictions"][l["conviction"]] / max(v, cs["volatilite_plancher"])
    poids = _plafonner({k: budget_libre * v / sum(brut.values()) for k, v in brut.items()} if brut else {}, cs["max_ligne"])
    # plafonds par pays, secteur et thème (expositions du cœur et des satellites conservés comprises)
    expo = {}

    def groupes(l, classe):
        g = [f"theme:{t}" for t in (l.get("themes") or [])]
        if l.get("pays") and l["type"] in ("pays", "entreprises"):
            g.append(f"pays:{l['pays']}")
        if l.get("secteur"):
            g.append(f"secteur:{l['secteur']}")
        return g

    def cap(g):
        return lim["max_theme"] if g.startswith("theme:") else lim["max_pays"] if g.startswith("pays:") else lim["max_secteur"]
    for k, e in res.items():
        for g in groupes(e["ligne"], e["classe"]):
            expo[g] = expo.get(g, 0) + e["cible"]
    for s in tenues:
        p = etat["positions"][s]
        l = lignes.get(p.get("ligne_id")) or {"type": p.get("type"), "pays": p.get("pays"), "secteur": p.get("secteur"), "themes": p.get("themes")}
        for g in groupes(l, p.get("classe")):
            expo[g] = expo.get(g, 0) + tenues[s]
    infos_vol = {}
    for l, sup in cand:
        k = sup["symbole"]
        w = poids.get(k, 0)
        gs = groupes(l, CLASSE_DE[l["type"]])
        libre = min([cap(g) - expo.get(g, 0) for g in gs] or [w])
        if libre < w:
            limite = min(gs, key=lambda g: cap(g) - expo.get(g, 0))
            avert.append(f"{l['nom']} : taille ramenée de {fr(w, 1)} à {fr(max(0, libre), 1)} % (plafond {limite.split(':')[0]} « {limite.split(':')[1]} » de {cap(limite)} %).")
            w = max(0.0, libre)
        if w < cs["ligne_min"]:
            if poids.get(k):
                ecartes.append({"id": l["id"], "nom": l["nom"], "raison": "taille inférieure au minimum après les plafonds"})
            continue
        for g in gs:
            expo[g] = expo.get(g, 0) + w
        v = vols.get(k)
        infos_vol[k] = v
        res[k] = {"cible": w, "poche": "satellite", "classe": CLASSE_DE[l["type"]], "support": sup, "ligne": l, "volatilite": v}
    for s, w in tenues.items():
        p = etat["positions"][s]
        res[s] = {"cible": w, "poche": "satellite", "classe": p.get("classe"), "support": {"symbole": s, "nom": p["nom"], "devise": p["devise"]},
                  "ligne": lignes.get(p.get("ligne_id")), "tenue": True}
    sat_total = sum(e["cible"] for e in res.values() if e["poche"] == "satellite")
    reste = budget - sat_total
    if reste > 0.05:
        coeur_risque = {k: e for k, e in res.items() if e["poche"] == "coeur"}
        s = sum(e["cible"] for e in coeur_risque.values())
        if s > 0:
            for e in coeur_risque.values():
                e["cible"] += reste * e["cible"] / s
            avert.append(f"Satellites : {fr(sat_total, 1)} % placés sur {fr(budget, 0)} % ; le solde ({fr(reste, 1)} pt) est reversé au cœur.")
        else:
            cash += reste

    # 3. Plancher de liquidités
    mini = palier_min(palier, config)
    if cash < mini:
        k = (100 - mini) / (100 - cash) if cash < 100 else 0
        for e in res.values():
            e["cible"] *= k
        cash = mini
    return {"lignes": res, "liquidites": cash, "liquidites_min": mini, "sorties": sorties, "satellites_ecartes": ecartes,
            "avertissements": avert, "limites": lim}


def _plafonner(poids: dict, maximum: float, iterations: int = 20) -> dict:
    """Plafonne chaque ligne et redistribue l'excédent aux lignes non plafonnées (sans dépasser le total)."""
    poids = dict(poids)
    for _ in range(iterations):
        exces = sum(max(0, v - maximum) for v in poids.values())
        if exces < 1e-9:
            break
        libres = {k: v for k, v in poids.items() if v < maximum - 1e-9}
        poids = {k: min(v, maximum) for k, v in poids.items()}
        s = sum(libres.values())
        if not s:
            break
        for k, v in libres.items():
            poids[k] += exces * v / s
    return {k: min(v, maximum) for k, v in poids.items()}


# ------------------------------------------------------------------ textes

def texte_donner_tort(ligne: dict | None, extra: list[str]) -> list[str]:
    res = list(extra)
    for t in ((ligne or {}).get("donner_tort") or [])[:2]:
        if t not in res:
            res.append(t)
    return res[:4] or ["Aucune réserve particulière relevée par les agents ; le risque de marché reste entier."]


def raison_ligne(ligne: dict | None, config: dict) -> dict:
    l = ligne or {}
    return {"verdict": l.get("verdict"), "conviction": l.get("conviction"), "score": l.get("score"),
            "agents": agents_favorables(l, config["satellites"]["note_famille_positive"]),
            "familles_pour": [p.get("famille") for p in (l.get("pour") or [])][:3],
            "objection": ((l.get("objection") or {}).get("objection")), "objection_serieuse": bool((l.get("objection") or {}).get("serieuse"))}


# ------------------------------------------------------------------ ordres de la décision

def rotation_utilisee(operations: list[dict], maintenant: datetime, jours: int) -> float:
    debut = maintenant - timedelta(days=jours)
    return sum(o.get("montant_eur", 0) for o in operations if o["sens"] == "vente" and not o.get("imposee")
               and (lire_iso(o["date"]) or maintenant) >= debut)


def generer_ordres(c: dict, etat: dict, valo: dict, operations: list[dict], palier: str, config: dict, maintenant: datetime) -> tuple[list[dict], list[str]]:
    """Ordres de la décision du jour (ventes puis achats). Renvoie (ordres, notes)."""
    cr = config["reequilibrage"]
    val = valo["valeur"]
    notes = []
    cur = {s: p.get("poids", 0) for s, p in etat["positions"].items()}
    cib = {s: e["cible"] for s, e in c["lignes"].items()}
    # dérive par classe
    classes_cur, classes_cib = {}, {}
    for s, p in etat["positions"].items():
        classes_cur[p.get("classe")] = classes_cur.get(p.get("classe"), 0) + cur[s]
    for s, e in c["lignes"].items():
        classes_cib[e["classe"]] = classes_cib.get(e["classe"], 0) + e["cible"]
    derive = {k for k in set(classes_cur) | set(classes_cib) if abs(classes_cur.get(k, 0) - classes_cib.get(k, 0)) > cr["seuil_points"]}
    en_attente = {o["symbole"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "vente"}
    ventes, achats = [], []
    for s in sorted(set(cur) | set(cib)):
        if s in en_attente:
            continue
        t, w = cib.get(s, 0.0), cur.get(s, 0.0)
        e = c["lignes"].get(s)
        p = etat["positions"].get(s)
        if s in c["sorties"]:
            motif, texte, imposee = c["sorties"][s]
            ventes.append(_ordre_vente(etat, p, p["quantite"], motif, texte, imposee, (e or {}).get("ligne"), t, w, palier, config, maintenant))
            continue
        if e and e.get("tenue"):
            continue
        if p is None:
            if t >= (cr["ligne_min"] if e["poche"] == "coeur" else config["satellites"]["ligne_min"]) and t * val / 100 >= cr["ordre_min_eur"]:
                achats.append(_ordre_achat(etat, e, t * val / 100, t, 0.0, palier, config, maintenant, "entrée"))
            continue
        if t <= 0:
            texte = f"{p['nom']} ne figure plus dans les cibles (allocation modèle du chef d'orchestre ou satellites retenus)."
            ventes.append(_ordre_vente(etat, p, p["quantite"], "sortie de l'allocation", texte, False, (e or {}).get("ligne"), t, w, palier, config, maintenant))
            continue
        diff = t - w
        if abs(diff) < cr["seuil_points"] and not (p.get("classe") in derive and abs(diff) >= cr["seuil_ligne_classe"]):
            continue
        montant = abs(diff) * val / 100
        if montant < cr["ordre_min_eur"]:
            continue
        if diff > 0:
            achats.append(_ordre_achat(etat, e, montant, t, w, palier, config, maintenant, "renforcement"))
        else:
            q = math.floor(montant / (p.get("dernier_cours_eur") or p["prix_revient_eur"]))
            if q > 0:
                texte = f"Rééquilibrage : poids {fr(w, 1)} % pour une cible de {fr(t, 1)} % (écart {fr(diff, 1, True)} pt)."
                ventes.append(_ordre_vente(etat, p, min(q, p["quantite"]), "rééquilibrage", texte, False, e.get("ligne"), t, w, palier, config, maintenant))
    # rotation mensuelle : ventes discrétionnaires plafonnées
    rc = config["rotation"]
    budget = rc["max_mensuelle_pct"] / 100 * val - rotation_utilisee(operations, maintenant, rc["jours"])
    gardees = []
    for o in sorted(ventes, key=lambda o: (not o["imposee"], -o["_montant"])):
        if not o["imposee"]:
            if o["_montant"] > budget:
                notes.append(f"Vente de {o['nom']} reportée : rotation mensuelle maximale ({rc['max_mensuelle_pct']} % sur {rc['jours']} jours) atteinte.")
                continue
            budget -= o["_montant"]
        gardees.append(o)
    ventes = gardees
    # financement des achats : liquidités + ventes, au-dessus du plancher
    mini = c["liquidites_min"]
    dispo = valo["liquidites"] + sum(o["_montant"] for o in ventes) * 0.995 - mini / 100 * val \
        - sum(o["montant_eur"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "achat")
    besoin = sum(o["montant_eur"] for o in achats)
    if besoin > dispo:
        k = max(0.0, dispo) / besoin if besoin else 0
        if k < 0.999:
            notes.append(f"Achats réduits à {fr(k * 100, 0)} % : liquidités disponibles au-dessus du plancher de {fr(mini, 0)} % insuffisantes.")
        for o in achats:
            o["montant_eur"] = round(o["montant_eur"] * k, 2)
        achats = [o for o in achats if o["montant_eur"] >= config["reequilibrage"]["ordre_min_eur"]]
    for o in ventes:
        o.pop("_montant", None)
    return ventes + achats, notes


def _ordre_achat(etat, e, montant, cible, actuel, palier, config, maintenant, nature) -> dict:
    l, sup = e.get("ligne") or {}, e["support"]
    sp = config["stops"]
    poche = e["poche"]
    r = raison_ligne(l, config)
    if poche == "satellite":
        vol = e.get("volatilite")
        texte = (f"{'Entrée' if nature == 'entrée' else 'Renforcement'} satellite : {l.get('nom')} ({sup['symbole']}). Verdict « {l.get('verdict')} », "
                 f"conviction {l.get('conviction')}, score {ent(l.get('score'))}/100 ; signaux favorables de {len(r['agents'])} agents indépendants "
                 f"({', '.join(r['agents'])}). Taille {fr(cible, 1)} % : conviction {l.get('conviction')}, volatilité "
                 + (f"{fr(vol, 0)} % sur 3 mois." if vol is not None else "inconnue (valeur par défaut de sa classe).")
                 + f" Stop initial à −{sp['stop_pct']} %.")
        extra = [f"Une baisse de {sp['stop_pct']} % déclencherait le stop : la perte serait alors réalisée."]
    else:
        texte = (f"{'Entrée' if nature == 'entrée' else 'Renforcement'} cœur : {sup['nom']} pour la ligne « {l.get('nom')} » de l'allocation modèle "
                 f"« {config.get('profil_libelle', config['profil'])} » du chef d'orchestre. Cible {fr(cible, 1)} % (poids actuel {fr(actuel, 1)} %). "
                 f"Verdict « {l.get('verdict')} », conviction {l.get('conviction')}, score {ent(l.get('score'))}/100.")
        extra = []
    if sup.get("contango"):
        texte += " Support adossé à des contrats à terme : coût de renouvellement (contango) à prévoir."
        extra.append(config["contango"])
    if sup.get("devise") not in (None, "EUR") or l.get("devise") not in (None, "EUR"):
        extra.append("Le change joue : une hausse de l'euro réduit la valeur en euros de ce support.")
    devise = P.devise_de(sup["symbole"], sup.get("devise") or l.get("devise"), config, etat.get("devises", {}))
    return P.nouvel_ordre(etat, maintenant, config, sens="achat", symbole=sup["symbole"], nom=sup.get("nom") or l.get("nom"), ligne_id=l.get("id"),
                          poche=poche, classe=e["classe"], type=l.get("type"), pays=sup.get("pays") or l.get("pays"), secteur=l.get("secteur_nom") or l.get("secteur"),
                          themes=l.get("themes") or [], devise=devise, montant_eur=round(montant, 2), motif=f"{nature} {'satellite' if poche == 'satellite' else 'cœur'}",
                          imposee=False, contango=bool(sup.get("contango")), familles=familles_resume(l),
                          raison={**r, "motif": f"{nature} {'satellite' if poche == 'satellite' else 'cœur'}", "texte": texte, "cible_pct": round(cible, 2),
                                  "poids_actuel_pct": round(actuel, 2), "palier": palier},
                          donner_tort=texte_donner_tort(l, extra))


def _ordre_vente(etat, p, quantite, motif, texte, imposee, ligne, cible, actuel, palier, config, maintenant) -> dict:
    r = raison_ligne(ligne, config) if ligne else {"verdict": p.get("verdict"), "conviction": p.get("conviction")}
    extra = {
        "sortie sur verdict": ["Le verdict peut remonter si les signaux défavorables se retournent ; la vente fige le résultat actuel."],
        "sortie sur objection": ["L'objection peut se révéler infondée : les autres signaux restaient favorables."],
        "stop": ["Le cours peut rebondir juste après le stop : la baisse peut n'être qu'un repli passager."],
        "prise de bénéfices": ["La tendance peut se prolonger : la partie vendue ne profitera pas d'une hausse supplémentaire."],
        "plancher de liquidités": ["Si le stress du marché retombe vite, les liquidités supplémentaires coûteront du rendement."],
    }.get(motif, ["La ligne pourrait revenir dans l'allocation : vente et rachat coûteraient des frais."])
    montant = quantite * (p.get("dernier_cours_eur") or p["prix_revient_eur"])
    o = P.nouvel_ordre(etat, maintenant, config, sens="vente", symbole=p["symbole"], nom=p["nom"], ligne_id=p.get("ligne_id"), poche=p.get("poche"),
                       classe=p.get("classe"), type=p.get("type"), devise=p["devise"], quantite=int(quantite), motif=motif, imposee=imposee,
                       raison={**r, "motif": motif, "texte": texte, "cible_pct": round(cible, 2), "poids_actuel_pct": round(actuel, 2), "palier": palier},
                       donner_tort=texte_donner_tort(ligne, extra))
    o["_montant"] = montant
    return o


# ------------------------------------------------------------------ contrôles de risque (à chaque exécution)

def controler_risques(etat: dict, lignes: dict | None, palier: str | None, valo: dict, config: dict, maintenant: datetime) -> list[dict]:
    """Stops, prise de bénéfices, sorties sur verdict ou objection (si le chef d'orchestre est à jour), plancher de
    liquidités (si l'agent risque est à jour). Renvoie les nouveaux ordres (imposés)."""
    sp = config["stops"]
    ordres = []
    deja = {o["symbole"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "vente"}
    for s, p in list(etat["positions"].items()):
        if s in deja:
            continue
        cours = p.get("dernier_cours_local")
        ligne = (lignes or {}).get(p.get("ligne_id")) if lignes is not None else None
        if lignes is not None and ligne is not None:
            if ligne.get("verdict") in SORTIE:
                ordres.append(_ordre_vente(etat, p, p["quantite"], "sortie sur verdict",
                                           f"Le chef d'orchestre est passé à « {ligne['verdict']} » sur {ligne['nom']} (score {ent(ligne.get('score'))}/100).",
                                           True, ligne, 0, p.get("poids", 0), palier, config, maintenant))
                continue
            if p.get("poche") == "satellite" and objection_serieuse(ligne):
                ordres.append(_ordre_vente(etat, p, p["quantite"], "sortie sur objection",
                                           f"Objection sérieuse du contradicteur sur {ligne['nom']} : {objection_serieuse(ligne)}",
                                           True, ligne, 0, p.get("poids", 0), palier, config, maintenant))
                continue
        if p.get("poche") != "satellite" or not cours:
            continue
        revient = p["prix_revient_local"]
        haut = max(p.get("plus_haut_local") or cours, cours)
        if haut >= revient * (1 + sp["suiveur_declenchement_pct"] / 100):
            suiveur = haut * (1 - sp["suiveur_pct"] / 100)
            if suiveur > (p.get("stop_local") or 0):
                p["stop_local"], p["stop_type"] = suiveur, "suiveur"
        if p.get("stop_local") and cours <= p["stop_local"]:
            if p.get("dernier_releve_stop") != p.get("dernier_cours_le"):
                p["confirmations_stop"] = p.get("confirmations_stop", 0) + 1
                p["dernier_releve_stop"] = p.get("dernier_cours_le")
            if p["confirmations_stop"] >= sp["confirmations"]:
                perf = (cours / revient - 1) * 100
                texte = (f"Stop {'suiveur' if p['stop_type'] == 'suiveur' else 'initial'} atteint sur {p['nom']} : cours {fr(cours, 2)} {p['devise']} sous le stop "
                         f"{fr(p['stop_local'], 2)} ({fr(perf, 1, True)} % depuis le prix de revient), confirmé par {p['confirmations_stop']} relevés.")
                ordres.append(_ordre_vente(etat, p, p["quantite"], "stop", texte, True, ligne, 0, p.get("poids", 0), palier, config, maintenant))
                continue
        else:
            p["confirmations_stop"], p["dernier_releve_stop"] = 0, None
        if not p.get("prise_benefices_faite") and cours >= revient * (1 + sp["prise_benefices_pct"] / 100):
            q = math.floor(p["quantite"] * sp["prise_benefices_part"])
            if q > 0:
                texte = (f"Prise de bénéfices partielle sur {p['nom']} : +{fr((cours / revient - 1) * 100, 1)} % depuis le prix de revient "
                         f"(seuil +{sp['prise_benefices_pct']} %) ; vente d'un tiers de la ligne ({q} sur {p['quantite']}).")
                ordres.append(_ordre_vente(etat, p, q, "prise de bénéfices", texte, True, ligne, 0, p.get("poids", 0), palier, config, maintenant))
    # plancher de liquidités
    if palier and valo["valeur"] > 0:
        mini = palier_min(palier, config)
        achats = sum(o["montant_eur"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "achat")
        ventes = sum(o.get("_montant", 0) for o in ordres)
        cash_pct = (valo["liquidites"] - achats + ventes) / valo["valeur"] * 100
        if cash_pct < mini - config["tolerance_plancher_points"]:
            manque = (mini - cash_pct) / 100 * valo["valeur"]
            vendus = {o["symbole"] for o in ordres} | deja
            pos = [p for s, p in etat["positions"].items() if s not in vendus and p.get("valeur_eur")]
            total = sum(p["valeur_eur"] for p in pos)
            for p in pos:
                part = manque * p["valeur_eur"] / total
                q = min(p["quantite"], math.ceil(part / (p.get("dernier_cours_eur") or p["prix_revient_eur"])))
                if q > 0 and part >= 50:
                    texte = (f"Plancher de liquidités : palier « {palier} » de l'agent risque, minimum {fr(mini, 0)} % ; liquidités à {fr(cash_pct, 1)} %. "
                             f"Allègement proportionnel de {p['nom']}.")
                    ordres.append(_ordre_vente(etat, p, q, "plancher de liquidités", texte, True, (lignes or {}).get(p.get("ligne_id")), 0, p.get("poids", 0),
                                               palier, config, maintenant))
    for o in ordres:
        o.pop("_montant", None)
    return ordres
