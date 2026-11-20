"""
Stratégie de l'agent trader (démo), méthode par combinaisons du backtest (règles : regles.md ; rapport de référence :
le dernier recalibrage validé, publié par le chef d'orchestre dans chef.json → selections → source). Aucun ETF monde.

1. Trois poches, 15 lignes au plus, 4 à 8 % par ligne ; le reste en liquidités s'il manque des candidats.
   - Entreprises (70 à 85 %) : sociétés retenues par les combinaisons en service (sélections du chef d'orchestre),
     25 % au plus par secteur.
   - Matières premières (0 à 20 %) : celles retenues par les combinaisons de matières premières en service.
   - ETF pays (0 à 15 %, 3 lignes au plus) : paris pays (tendance haussière et saine, valorisation non tendue).
2. Ni stop ni prise de bénéfices. Vente quand l'actif sort de sa combinaison (vérification mensuelle, au premier
   rééquilibrage du mois) ; un pari pays est vendu dès qu'un excès se déclenche ou que la tendance casse (vérifié à chaque
   exécution, dès que le chef d'orchestre le signale).
3. Les lignes déjà détenues et toujours retenues passent avant les nouvelles (moins de rotation, moins de frais).
4. Changement de méthode : au premier rééquilibrage, toutes les lignes qui ne respectent pas ces règles sont vendues, chaque
   ordre étant journalisé avec sa raison ; la date du changement est enregistrée (graphique de performance).
"""
from __future__ import annotations

import math
from datetime import datetime

from ..risque.calculs import fr
from . import portefeuille as P

CLASSE_DE = {"pays": "actions", "secteurs": "actions", "entreprises": "actions", "obligations": "obligations", "or": "or", "matieres": "matieres",
             "liquidites": "liquidites"}
POCHE_DE = {"entreprises": "entreprises", "matieres": "matieres", "or": "matieres", "pays": "pays"}
POCHES = ("entreprises", "matieres", "pays")
LIBELLES_POCHES = {"entreprises": "Entreprises", "matieres": "Matières premières", "pays": "ETF pays (paris)", "liquidites": "Liquidités",
                   "coeur": "Cœur (ancienne méthode)", "satellite": "Satellites (ancienne méthode)", "tendance": "Poche tendance (ancienne méthode)"}
LIBELLES_CLASSES = {"actions": "Actions", "obligations": "Obligations", "or": "Or", "matieres": "Matières premières", "liquidites": "Liquidités"}


def ent(x) -> str:
    return "n. d." if x is None else str(int(round(x)))


# ------------------------------------------------------------------ lignes et supports

def lignes_chef(chef: dict) -> dict[str, dict]:
    res = {}
    for t in ("pays", "secteurs", "matieres", "obligations", "liquidites", "entreprises"):
        for l in chef.get(t) or []:
            res[l["id"]] = l
    if chef.get("or"):
        res[chef["or"]["id"]] = chef["or"]
    return res


def supports_de(ligne: dict, config: dict) -> list[dict]:
    """Supports cotés d'une ligne (liste vide : aucun support coté)."""
    cfg = config["supports"].get(ligne["id"])
    if cfg is not None:
        return [dict(s) for s in cfg]
    s = ligne.get("symbole")
    if not s or s.endswith("=F") or s.startswith("^"):
        return []
    if ligne["type"] == "pays":
        return [{"symbole": s, "nom": f"ETF {ligne['nom']} ({s})", "devise": "USD", "part": 1}]
    return [{"symbole": s, "nom": ligne.get("nom") or s, "devise": ligne.get("devise"), "part": 1}]


def candidats(chef: dict) -> dict[str, list[dict]]:
    """Candidats de chaque poche : la liste unique du chef d'orchestre (chef.json → liste), la même que celle affichée
    dans l'appli ; à défaut (ancienne sortie du chef d'orchestre), ses sélections."""
    li = chef.get("liste") or {}
    if li.get("lignes") is not None:
        res = {"entreprises": [], "matieres": [], "pays": []}
        for l in li["lignes"]:
            raison = (f"liste du chef d'orchestre (entrée le {l.get('date_entree')}) : retenue par " + " ; ".join(l.get("combinaisons_libelles") or [])
                      + f", conviction {l.get('conviction')}")
            res[l["categorie"]].append({**l, "type": l.get("type") or l["categorie"], "poche": l["categorie"], "raison": raison})
        return res
    sel = chef.get("selections") or {}
    ent_ = [{**x, "type": "entreprises", "poche": "entreprises",
             "raison": "retenue par " + " ; ".join(x.get("combinaisons_libelles") or x.get("combinaisons") or [])}
            for x in (sel.get("entreprises") or {}).get("retenues") or []]
    mat = [{**x, "poche": "matieres", "raison": "retenue par Niveau historique + Positionnement CFTC (" + (x.get("texte") or "") + ")"}
           for x in (sel.get("matieres") or {}).get("retenues") or []]
    pays = [{"id": e["id"], "type": "pays", "poche": "pays", "nom": e["nom"], "symbole": e["symbole"], "cle": e.get("cle"), "pays": e.get("cle"),
             "force_relative": e.get("force_relative"),
             "raison": f"pari pays : tendance haussière et saine ({e.get('tendance') or 'suivi de tendance'}), valorisation relative non tendue "
                       f"({ent(e.get('valorisation_note'))}/100)"}
            for e in (sel.get("paris_pays") or {}).get("candidats") or []]
    return {"entreprises": ent_, "matieres": mat, "pays": pays}


def evaluation_pays(chef: dict | None) -> dict[str, dict]:
    """Évaluation de chaque ETF pays par le chef d'orchestre (entrée possible, sortie imposée et raisons), par symbole."""
    ev = (((chef or {}).get("selections") or {}).get("paris_pays") or {}).get("evaluation") or []
    return {e["symbole"]: e for e in ev if e.get("symbole")}


# ------------------------------------------------------------------ cibles

def _choisir(cands: list[dict], detenus: set[str], config: dict, max_n: int, limite_secteur: float | None = None, poids: float | None = None) -> tuple[list, list]:
    """Candidats retenus (détenus d'abord, puis dans l'ordre du chef d'orchestre), avec support coté, au plus `max_n`,
    et au plus floor(limite_secteur / poids) lignes par secteur. Renvoie (retenus [(ligne, support)], écartés)."""
    ordre = sorted(cands, key=lambda l: (0 if (supports_de(l, config) or [{}])[0].get("symbole") in detenus else 1))
    res, ecartes, par_secteur = [], [], {}
    for l in ordre:
        sups = supports_de(l, config)
        if not sups:
            ecartes.append({"id": l["id"], "nom": l["nom"], "raison": "aucun support coté"})
            continue
        if any(s["symbole"] in config["etf_monde"] for s in sups):
            ecartes.append({"id": l["id"], "nom": l["nom"], "raison": "ETF monde exclu"})
            continue
        if len(res) >= max_n:
            ecartes.append({"id": l["id"], "nom": l["nom"], "raison": f"poche complète ({max_n} lignes)"})
            continue
        sec = l.get("secteur")
        if limite_secteur and poids and sec:
            maxi = math.floor(limite_secteur / poids + 1e-9)
            if par_secteur.get(sec, 0) >= maxi:
                ecartes.append({"id": l["id"], "nom": l["nom"], "raison": f"secteur « {l.get('secteur_nom') or sec} » complet ({fr(limite_secteur, 0)} % au plus)"})
                continue
            par_secteur[sec] = par_secteur.get(sec, 0) + 1
        res.append((l, sups[0]))
    return res, ecartes


def cibles(chef: dict, etat: dict, config: dict) -> dict:
    """Poids cibles (% du portefeuille) par support. Renvoie {lignes: {symbole: {...}}, liquidites, poches, ecartees,
    exclusions: {symbole détenu hors cibles: raison}, avertissements}."""
    cm = config["methode"]
    lmin, lmax, nmax = cm["ligne_min"], cm["ligne_max"], cm["max_lignes"]
    detenus = set(etat["positions"])
    c = candidats(chef)
    # Pari pays en cours : gardé tant qu'aucun excès ni cassure de tendance n'est signalé, même si une condition d'entrée
    # manque désormais (la sortie ne se déclenche que sur excès ou tendance cassée)
    ev = evaluation_pays(chef)
    pris = {x["symbole"] for x in c["pays"]}
    for s, pos in etat["positions"].items():
        e = ev.get(s)
        if pos.get("poche") == "pays" and s not in pris and e and not e.get("sortie"):
            c["pays"].insert(0, {"id": e["id"], "type": "pays", "poche": "pays", "nom": e["nom"], "symbole": s, "cle": e.get("cle"), "pays": e.get("cle"),
                                 "raison": "pari en cours : ni excès ni tendance cassée (" + "; ".join(e.get("raisons_refus") or []) + ")"})
    ecartees, avert = [], []
    pays, e1 = _choisir(c["pays"], detenus, config, cm["pays"]["max_lignes"])
    mat, e2 = _choisir(c["matieres"], detenus, config, max(0, math.floor(cm["matieres"]["max_pct"] / lmin)))
    ecartees += e1 + e2
    # Entreprises : lignes laissées par les autres poches, au moins celles qu'il faut pour atteindre min_pct à 8 %
    besoin_ent = math.ceil(cm["entreprises"]["min_pct"] / lmax)
    places_ent = nmax - len(pays) - len(mat)
    while places_ent < min(besoin_ent, len(c["entreprises"])) and (pays or mat):
        (pays if len(pays) >= len(mat) and pays else mat).pop()  # les entreprises d'abord : on libère des lignes
        places_ent = nmax - len(pays) - len(mat)
    n_vise = min(len(c["entreprises"]), places_ent)
    w_e = min(lmax, cm["entreprises"]["max_pct"] / n_vise) if n_vise else lmax
    ents, e3 = _choisir(c["entreprises"], detenus, config, places_ent, cm["entreprises"]["max_secteur_pct"], w_e)
    ecartees += e3
    # Poids de chaque poche : entreprises de 70 à 85 % (8 % au plus par ligne), puis matières (20 % au plus), puis pays (15 %)
    cap = 100 - cm["tampon_liquidites_pct"]
    t_ent = min(cm["entreprises"]["max_pct"], len(ents) * lmax)
    t_mat = min(cm["matieres"]["max_pct"], len(mat) * lmax)
    t_pays = min(cm["pays"]["max_pct"], len(pays) * lmax)
    if t_ent + t_mat + t_pays > cap:  # entreprises ramenées vers 70 %, puis matières, puis pays réduits
        t_ent = min(t_ent, max(min(cm["entreprises"]["min_pct"], t_ent), cap - t_mat - t_pays))
        reste = cap - t_ent
        t_mat = min(t_mat, reste)
        t_pays = min(t_pays, max(0.0, reste - t_mat))

    def repartir(retenus, total, poche):
        while retenus and total / len(retenus) < lmin:  # une ligne sous 4 % : la dernière est écartée
            l, _ = retenus.pop()
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"poche « {poche} » : moins de {fr(lmin, 0)} % par ligne"})
        return {sup["symbole"]: (l, sup, min(lmax, total / len(retenus))) for l, sup in retenus} if retenus else {}
    res = {}
    for poche, retenus, total in (("entreprises", ents, t_ent), ("matieres", mat, t_mat), ("pays", pays, t_pays)):
        for s, (l, sup, w) in repartir(retenus, total, poche).items():
            res[s] = {"cible": w, "poche": poche, "classe": CLASSE_DE[l["type"]], "support": sup, "ligne": l,
                      "zone": config["regions"].get(l.get("pays"), "Matières premières" if poche == "matieres" else "Autres")}
    poches = {p: round(sum(e["cible"] for e in res.values() if e["poche"] == p), 2) for p in POCHES}
    if poches["entreprises"] < cm["entreprises"]["min_pct"]:
        avert.append(f"Entreprises à {fr(poches['entreprises'], 1)} % seulement ({len(ents)} société(s) retenue(s) par les combinaisons) : "
                     "la part non placée reste en liquidités.")
    # Lignes détenues hors cibles : raison de la vente
    cands = {(supports_de(l, config) or [{}])[0].get("symbole"): (p, l) for p, ls in c.items() for l in ls}
    exclusions = {}
    for s, pos in etat["positions"].items():
        if s in res:
            continue
        if pos.get("poche") not in POCHES:
            exclusions[s] = ("changement de méthode", f"ligne de l'ancienne méthode (poche « {LIBELLES_POCHES.get(pos.get('poche'), pos.get('poche'))} ») : "
                                                      "elle ne respecte pas les règles par combinaisons du backtest")
        elif s in cands:
            e = next((x for x in ecartees if x["id"] == cands[s][1]["id"]), None)
            exclusions[s] = ("concentration", f"toujours retenue, mais {e['raison'] if e else 'non retenue par les limites de la poche'}")
        elif pos.get("poche") == "pays":
            exclusions[s] = ("sortie de pari pays", "le pays ne remplit plus les conditions d'un pari (tendance haussière et saine, valorisation non tendue)")
        else:
            exclusions[s] = ("sortie de combinaison", "n'est plus retenue par sa combinaison (n'est plus dans les meilleurs 30 % sur chacun de ses signaux)")
    return {"lignes": res, "liquidites": round(100 - sum(e["cible"] for e in res.values()), 2), "poches": poches,
            "ecartees": ecartees, "exclusions": exclusions, "avertissements": avert,
            "candidats": {p: len(v) for p, v in c.items()}}


# ------------------------------------------------------------------ ordres

def _ordre(etat, sens, e_ou_pos, maintenant, config, montant=None, quantite=None, motif="", texte="", imposee=False, cible=0.0, actuel=0.0):
    l = e_ou_pos.get("ligne") or {}
    sup = e_ou_pos.get("support") or {}
    if sens == "achat":
        poche = e_ou_pos["poche"]
        extra = []
        if sup.get("contango"):
            texte += " Support adossé à des contrats à terme : coût de renouvellement (contango) à prévoir."
            extra.append(config["contango"])
        if (sup.get("devise") or l.get("devise")) not in (None, "EUR"):
            extra.append("Le change joue : une hausse de l'euro réduit la valeur en euros de ce support.")
        extra.append({"entreprises": "Combinaison jugée « Prometteuse » mais non significative par le backtest : elle peut ne pas tenir.",
                      "matieres": "Univers d'environ 16 matières : la combinaison repose sur peu de cas.",
                      "pays": "La note pays n'est pas prédictive d'après le backtest : ce pari ne repose que sur la tendance, qui peut casser."}[poche])
        devise = P.devise_de(sup["symbole"], sup.get("devise") or l.get("devise"), config, etat.get("devises", {}))
        return P.nouvel_ordre(etat, maintenant, config, sens="achat", symbole=sup["symbole"], nom=sup.get("nom") or l.get("nom"), ligne_id=l.get("id"),
                              poche=poche, classe=e_ou_pos["classe"], type=l.get("type"), pays=sup.get("pays") or l.get("pays"),
                              secteur=l.get("secteur_nom") or l.get("secteur"), devise=devise, montant_eur=round(montant, 2), motif=motif, imposee=imposee,
                              contango=bool(sup.get("contango")), familles={},
                              raison={"motif": motif, "texte": texte, "cible_pct": round(cible, 2), "poids_actuel_pct": round(actuel, 2),
                                      "combinaisons": l.get("combinaisons_libelles") or l.get("combinaisons")},
                              donner_tort=extra[:4])
    p = e_ou_pos
    o = P.nouvel_ordre(etat, maintenant, config, sens="vente", symbole=p["symbole"], nom=p["nom"], ligne_id=p.get("ligne_id"), poche=p.get("poche"),
                       classe=p.get("classe"), type=p.get("type"), devise=p["devise"], quantite=int(quantite), motif=motif, imposee=imposee,
                       raison={"motif": motif, "texte": texte, "cible_pct": round(cible, 2), "poids_actuel_pct": round(actuel, 2)},
                       donner_tort=["L'actif peut progresser après sa vente : la règle privilégie la discipline à la conviction."])
    o["_montant"] = quantite * (p.get("dernier_cours_eur") or p["prix_revient_eur"])
    return o


def generer_ordres(c: dict, etat: dict, valo: dict, config: dict, maintenant: datetime) -> tuple[list[dict], list[str], list[dict]]:
    """Ordres du rééquilibrage mensuel (ventes puis achats). Renvoie (ordres, notes, arbitrages expliqués)."""
    cm, cr = config["methode"], config["methode"]["reequilibrage"]
    val = valo["valeur"]
    cur = {s: p.get("poids", 0) for s, p in etat["positions"].items()}
    en_attente = {o["symbole"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "vente"}
    ventes, achats, notes, arbitrages = [], [], [], []

    def arbitrage(s, nom, action, raison):
        arbitrages.append({"symbole": s, "nom": nom, "action": action, "raison": raison})

    # 1. Lignes hors cibles : vendues en totalité (règles enfreintes), chaque ordre avec sa raison
    for s, p in etat["positions"].items():
        if s in c["lignes"] or s in en_attente:
            continue
        motif, raison = c["exclusions"].get(s, ("mise en conformité", "non retenue"))
        texte = f"Vente de {p['nom']} ({fr(cur.get(s, 0), 1)} % du portefeuille) : {raison}."
        ventes.append(_ordre(etat, "vente", p, maintenant, config, quantite=p["quantite"], motif=motif, texte=texte, actuel=cur.get(s, 0)))
        arbitrage(s, p["nom"], "vente totale", raison)

    # 2. Lignes cibles détenues : rééquilibrage au-delà du seuil ou hors de la fourchette 4-8 %
    for s, e in c["lignes"].items():
        p = etat["positions"].get(s)
        if p is None or s in en_attente:
            continue
        t, w = e["cible"], cur.get(s, 0)
        diff = t - w
        hors_fourchette = w < cm["ligne_min"] or w > cm["ligne_max"] + 0.5
        if abs(diff) < cr["seuil_points"] and not hors_fourchette:
            arbitrage(s, p["nom"], "conservée", f"toujours retenue ({e['ligne'].get('raison', '')}) ; poids {fr(w, 1)} % pour une cible de {fr(t, 1)} %")
            continue
        montant = abs(diff) * val / 100
        if montant < cr["ordre_min_eur"]:
            continue
        if diff > 0:
            achats.append(_ordre(etat, "achat", e, maintenant, config, montant=montant, motif="rééquilibrage",
                                 texte=f"Renforcement de {p['nom']} : poids {fr(w, 1)} % pour une cible de {fr(t, 1)} %.", cible=t, actuel=w))
            arbitrage(s, p["nom"], "renforcement", f"poids {fr(w, 1)} % pour une cible de {fr(t, 1)} %")
        else:
            q = math.floor(montant / (p.get("dernier_cours_eur") or p["prix_revient_eur"]))
            if q > 0:
                ventes.append(_ordre(etat, "vente", p, maintenant, config, quantite=min(q, p["quantite"]), motif="rééquilibrage",
                                     texte=f"Rééquilibrage de {p['nom']} : poids {fr(w, 1)} % pour une cible de {fr(t, 1)} %.", cible=t, actuel=w))
                arbitrage(s, p["nom"], "réduction", f"poids {fr(w, 1)} % pour une cible de {fr(t, 1)} % (8 % au plus par ligne)")

    # 3. Entrées : financées par les liquidités et le produit des ventes (estimé), entreprises d'abord
    dispo = valo["liquidites"] + sum(o["_montant"] for o in ventes) * 0.995 - cm["tampon_liquidites_pct"] / 100 * val \
        - sum(o["montant_eur"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "achat") \
        - sum(o["montant_eur"] for o in achats)
    ordre_poche = {p: i for i, p in enumerate(POCHES)}
    for s, e in sorted(c["lignes"].items(), key=lambda kv: (ordre_poche[kv[1]["poche"]], -kv[1]["cible"])):
        if s in etat["positions"]:
            continue
        nom = e["support"].get("nom") or e["ligne"].get("nom")
        montant = e["cible"] * val / 100
        if montant > dispo:
            if dispo >= cm["ligne_min"] / 100 * val:
                montant = dispo
            else:
                arbitrage(s, nom, "entrée reportée", f"cible {fr(e['cible'], 1)} % ; liquidités insuffisantes (ventes en attente d'exécution)")
                notes.append(f"Entrée de {nom} reportée au prochain rééquilibrage : liquidités insuffisantes.")
                continue
        texte = (f"Entrée {LIBELLES_POCHES[e['poche']].lower()} : {nom}. Cible {fr(e['cible'], 1)} % ; {e['ligne'].get('raison', '')}.")
        achats.append(_ordre(etat, "achat", e, maintenant, config, montant=montant, motif=f"entrée {e['poche']}", texte=texte, cible=e["cible"]))
        arbitrage(s, nom, "entrée", f"{LIBELLES_POCHES[e['poche']]} : cible {fr(e['cible'], 1)} %")
        dispo -= montant
    for o in ventes + achats:
        o.pop("_montant", None)
    return ventes + achats, notes, arbitrages


def iso_utc(t: datetime) -> str:
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ étiquettes de poche et compléments d'exécution

def cibles_en_cours(etat: dict) -> dict[str, dict]:
    """Cibles du dernier rééquilibrage (symbole → {poche, cible, ligne_id})."""
    lignes = (((etat.get("derniere_decision") or {}).get("cibles") or {}).get("lignes")) or []
    return {l["symbole"]: l for l in lignes if l.get("symbole")}


def reetiqueter(etat: dict, maintenant: datetime) -> list[dict]:
    """Positions héritées de l'ancienne méthode mais retenues par la méthode actuelle (ex. CNX « satellite », EWW « cœur ») :
    réétiquetées dans la poche de leur ligne cible (entreprises, matières, pays). Historique intact : la valeur change de
    poche comme un flux, et le changement est journalisé."""
    from .portefeuille import reetiqueter_position
    cibles = cibles_en_cours(etat)
    faits = []
    for s, p in etat["positions"].items():
        c = cibles.get(s)
        if not c or c.get("poche") not in POCHES or p.get("poche") == c["poche"]:
            continue
        reetiqueter_position(etat, p, c["poche"], c.get("ligne_id"), iso_utc(maintenant), "ligne retenue par la méthode actuelle (liste du chef d'orchestre)")
        faits.append(etat["reetiquetages"][-1])
    return faits


def detecter_complements(etat: dict, operations: list[dict], valo: dict, config: dict) -> None:
    """Achats d'entrée du dernier rééquilibrage exécutés en dessous de leur cible faute de liquidités (avant que le
    complément d'exécution existe) : manque noté une fois (ex. UNG le 16/11/2026, 3,8 % pour une cible de 8 %)."""
    mois = etat.get("dernier_reequilibrage")
    if not mois or etat.get("complements_verifies") == mois:
        return
    cibles = cibles_en_cours(etat)
    histo = etat.get("historique") or {}
    tol = config["methode"]["tolerance_cible_points"]
    for op in operations:
        r = op.get("raison") or {}
        if op.get("sens") != "achat" or not str(op.get("date", "")).startswith(mois) or not str(op.get("motif", "")).startswith("entrée"):
            continue
        s = op["symbole"]
        if s not in etat["positions"] or s not in cibles or not r.get("cible_pct"):
            continue
        valeur = (histo.get(op["date"][:10]) or {}).get("portefeuille") or valo["valeur"]
        obtenu = op.get("montant_eur", 0) / valeur * 100 if valeur else 0
        if r["cible_pct"] - obtenu > tol:
            etat.setdefault("complements", {}).setdefault(s, {"cible_pct": r["cible_pct"], "manque_eur": round((r["cible_pct"] - obtenu) / 100 * valeur, 2),
                                                             "le": op["date"], "ordre": op.get("id"),
                                                             "raison": "achat d'entrée exécuté en dessous de sa cible faute de liquidités"})
    etat["complements_verifies"] = mois


def completer_entrees(etat: dict, valo: dict, operations: list[dict], config: dict, maintenant: datetime) -> list[dict]:
    """Complète un achat d'entrée réduit faute de liquidités dès qu'elles sont disponibles (au-dessus du tampon), jusqu'à la
    cible du rééquilibrage. Ce n'est pas un rééquilibrage : seule la part non exécutée de l'ordre décidé est rachetée."""
    detecter_complements(etat, operations, valo, config)
    comp = etat.get("complements") or {}
    if not comp:
        return []
    cm = config["methode"]
    val = valo["valeur"] or 0
    attente = {o["symbole"] for o in etat.get("ordres", []) if o.get("statut") == "en attente"}
    achats_attente = sum(o["montant_eur"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "achat")
    dispo = valo["liquidites"] - cm["tampon_liquidites_pct"] / 100 * val - achats_attente
    if any(o["sens"] == "vente" for o in etat.get("ordres", []) if o.get("statut") == "en attente"):
        return []  # ventes encore en attente : leur produit arrivera à leur exécution
    ordres = []
    for s, c in sorted(comp.items()):
        p = etat["positions"].get(s)
        if p is None or s not in cibles_en_cours(etat):
            comp.pop(s, None)
            continue
        if s in attente:
            continue
        poids = (p.get("valeur_eur") or 0) / val * 100 if val else 0
        manque = min(c["cible_pct"], cm["ligne_max"]) - poids
        if manque <= cm["tolerance_cible_points"] / 2:
            comp.pop(s, None)
            continue
        montant = min(manque / 100 * val, dispo)
        if montant < cm["reequilibrage"]["ordre_min_eur"]:
            continue
        e = {"poche": p["poche"], "classe": p.get("classe"), "support": {"symbole": s, "nom": p["nom"], "devise": p["devise"]},
             "ligne": {"id": p.get("ligne_id"), "nom": p["nom"], "type": p.get("type")}}
        ordres.append(_ordre(etat, "achat", e, maintenant, config, montant=montant, motif="complément d'exécution",
                             texte=(f"Complément d'exécution de {p['nom']} : poids {fr(poids, 1)} % pour une cible de {fr(c['cible_pct'], 1)} % "
                                    f"(achat d'entrée réduit le {str(c['le'])[:10]} : {c['raison']})."), cible=c["cible_pct"], actuel=poids))
        dispo -= montant
        comp.pop(s, None)
    for o in ordres:
        o.pop("_montant", None)
    return ordres


def ecarts_aux_cibles(etat: dict, valo: dict, tolerance: float) -> list[dict]:
    """Lignes dont le poids s'écarte de la cible du dernier rééquilibrage de plus de `tolerance` points."""
    val = valo["valeur"] or 0
    res = []
    for s, c in cibles_en_cours(etat).items():
        p = etat["positions"].get(s)
        poids = (p.get("valeur_eur") or 0) / val * 100 if p and val else 0.0
        if abs(poids - c["cible"]) > tolerance:
            res.append({"symbole": s, "nom": c.get("nom"), "poids": round(poids, 2), "cible": c["cible"], "ecart": round(poids - c["cible"], 2)})
    return res


# ------------------------------------------------------------------ contrôles à chaque exécution : paris pays

def controler_liste(etat: dict, chef: dict | None, config: dict, maintenant: datetime) -> list[dict]:
    """Entreprise ou matière première sortie en cours de mois de la liste du chef d'orchestre (sortie de sa combinaison
    confirmée 5 jours de suite) : vendue sans attendre le rééquilibrage. Les paris pays suivent controler_paris_pays."""
    li = (chef or {}).get("liste") or {}
    if chef is None or li.get("lignes") is None or li.get("mois") != maintenant.date().isoformat()[:7]:
        return []
    dans = {l.get("symbole") for l in li["lignes"]} | {l["id"] for l in li["lignes"]}
    sorties = {m["id"]: m for m in li.get("mouvements") or [] if m.get("sens") == "sortie"}
    deja = {o["symbole"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "vente"}
    ordres = []
    for s, p in etat["positions"].items():
        if p.get("poche") not in ("entreprises", "matieres") or s in deja or s in dans or p.get("ligne_id") in dans:
            continue
        m = sorties.get(p.get("ligne_id"))
        if not m:
            continue
        texte = f"Sortie de la liste du chef d'orchestre le {m['date']} : {m['texte']}."
        o = _ordre(etat, "vente", p, maintenant, config, quantite=p["quantite"], motif="sortie de la liste", texte=texte, imposee=True, actuel=p.get("poids", 0))
        o.pop("_montant", None)
        ordres.append(o)
    return ordres


def controler_paris_pays(etat: dict, chef: dict | None, config: dict, maintenant: datetime) -> list[dict]:
    """Un pari pays est vendu dès que le chef d'orchestre signale un excès ou une tendance cassée. Sans données du chef
    à jour, rien n'est décidé."""
    if chef is None:
        return []
    ev = evaluation_pays(chef)
    deja = {o["symbole"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "vente"}
    ordres = []
    for s, p in etat["positions"].items():
        if p.get("poche") != "pays" or s in deja:
            continue
        e = ev.get(s)
        if not e or not e.get("sortie"):
            continue
        raisons = " ; ".join(e.get("raisons_sortie") or [])
        motif = "sortie de tendance" if any(r.startswith("tendance cassée") for r in e.get("raisons_sortie") or []) else "excès"
        texte = f"Pari pays clos : {e.get('nom') or p['nom']} — {raisons}."
        o = _ordre(etat, "vente", p, maintenant, config, quantite=p["quantite"], motif=motif, texte=texte, imposee=True, actuel=p.get("poids", 0))
        o.pop("_montant", None)
        ordres.append(o)
    return ordres
