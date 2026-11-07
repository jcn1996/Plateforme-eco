"""
État du portefeuille virtuel, exécution simulée des ordres et valorisation (agent trader, démo).

Aucun ordre réel n'est jamais passé : un « ordre » est une ligne de data/trader/etat.json, exécutée sur le papier
au premier cours disponible après la décision (jamais à un cours passé), avec :
- l'écart achat/vente estimé : la moitié de l'écart est payée à l'achat (cours × (1 + ½ écart)) et à la vente
  (cours × (1 − ½ écart)) ;
- des frais de courtage (0,1 % du montant par défaut) ;
- la conversion en euros au cours de change du jour (paires EURXXX=X ; pence et cents convertis).
Les quantités sont entières (pas de fraction de part) ; un achat dont le montant n'atteint pas le prix d'une part est
annulé, et noté.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..commun.sante import iso, lire_iso

SOUS_UNITES = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}


def devise_iso(brute: str | None) -> tuple[str, float]:
    """« GBp » → (« GBP », 0,01) : devise ISO et facteur du cours coté vers cette devise."""
    if not brute:
        return "USD", 1.0
    return SOUS_UNITES.get(brute, (brute.upper(), 1.0))


def devise_de(symbole: str, devise_ligne: str | None, config: dict, cache: dict) -> str:
    """Devise de cotation : ligne du chef d'orchestre ou support configuré, sinon cache (yfinance), sinon suffixe."""
    if symbole in cache:
        return cache[symbole]
    par_suffixe = None
    for suffixe, dev in sorted(config["devises_suffixes"].items(), key=lambda kv: -len(kv[0])):
        if symbole.upper().endswith(suffixe.upper()):
            par_suffixe = dev
            break
    # Londres, Johannesburg, Tel-Aviv : cotation en sous-unités (pence, cents, agorot), quelle que soit la devise des comptes
    if par_suffixe in SOUS_UNITES:
        return par_suffixe
    return devise_ligne or par_suffixe or "USD"


def en_euros(prix_local: float, devise: str, taux: dict) -> float | None:
    dev, facteur = devise_iso(devise)
    t = taux.get(dev)
    if not t:
        return None
    return prix_local * facteur / t


def categorie_ecart(symbole: str, type_ligne: str | None, config: dict) -> str:
    ex = config["execution"]
    if symbole in config["etf_larges"]:
        return "etf_large"
    if type_ligne and type_ligne != "entreprises":
        return "etf"
    s = symbole.upper()
    if any(s.endswith(x) for x in ex["suffixes_emergents"]):
        return "action_emergente"
    if any(s.endswith(x) for x in ex["suffixes_asie"]):
        return "action_asie"
    if any(s.endswith(x) for x in ex["suffixes_europe"]):
        return "action_europe"
    return "action_us"


def demi_ecart(symbole: str, type_ligne: str | None, config: dict) -> float:
    """Moitié de l'écart achat/vente estimé, en fraction (0,0005 = 0,05 %)."""
    return config["execution"]["ecart_achat_vente_pct"][categorie_ecart(symbole, type_ligne, config)] / 200


def frais(montant: float, config: dict) -> float:
    ex = config["execution"]
    return max(ex["frais_min_eur"], montant * ex["frais_pct"] / 100)


def etat_initial(config: dict, maintenant: datetime) -> dict:
    return {"version": 1, "date_debut": maintenant.date().isoformat(), "debut_le": iso(maintenant), "capital_initial": config["capital_initial"],
            "liquidites": float(config["capital_initial"]), "positions": {}, "ordres": [], "historique": {}, "devises": {},
            "reference_indice": None, "attribution": {"poches": {}, "familles": {}, "classes": {}}, "frais_total": 0.0, "ecarts_total": 0.0,
            "compteur": 0, "derniere_decision": None, "derniere_decision_jour": None, "attente": None}


# ------------------------------------------------------------------ attribution

def parts_familles(familles: dict) -> dict:
    """Parts de chaque famille de signaux dans la décision d'achat : ∝ (note − 50) pour les familles favorables."""
    pos = {k: (f.get("note") or 0) - 50 for k, f in (familles or {}).items() if (f.get("note") or 0) > 50}
    s = sum(pos.values())
    if not s:
        return {"autres": 1.0}
    return {k: v / s for k, v in pos.items()}


def attribuer(cumul: dict, position: dict, montant: float) -> None:
    """Ajoute `montant` (plus-value en euros) à l'attribution par poche, classe et famille de signaux."""
    for cle, valeur in (("poches", position.get("poche")), ("classes", position.get("classe"))):
        cumul.setdefault(cle, {})
        cumul[cle][valeur or "?"] = cumul[cle].get(valeur or "?", 0.0) + montant
    cumul.setdefault("familles", {})
    for k, p in parts_familles(position.get("familles")).items():
        cumul["familles"][k] = cumul["familles"].get(k, 0.0) + montant * p


# ------------------------------------------------------------------ ordres

def nouvel_ordre(etat: dict, maintenant: datetime, config: dict, **champs) -> dict:
    etat["compteur"] = etat.get("compteur", 0) + 1
    o = {"id": f"o{etat['compteur']:05d}", "cree_le": iso(maintenant),
         "expire_le": iso(maintenant + timedelta(days=config["execution"]["expiration_jours"])), "statut": "en attente"}
    o.update(champs)
    return o


def executer_ordres(etat: dict, f, maintenant: datetime, config: dict) -> tuple[list[dict], list[dict], str | None]:
    """Exécute les ordres en attente au premier cours disponible après leur décision.
    Renvoie (opérations exécutées, ordres annulés ou expirés, erreur de source éventuelle)."""
    ordres = [o for o in etat.get("ordres", []) if o.get("statut") == "en attente"]
    if not ordres:
        return [], [], None
    demandes = {}
    for o in ordres:
        t = lire_iso(o["cree_le"])
        demandes[o["symbole"]] = min(demandes.get(o["symbole"], t), t)
    erreur = None
    try:
        barres = f.premiers_cours(demandes)
    except Exception as e:  # noqa: BLE001 — source indisponible : les ordres restent en attente
        barres, erreur = {}, f"{type(e).__name__}: {str(e)[:150]}"
    devises = {devise_iso(o["devise"])[0] for o in ordres if o["symbole"] in barres}
    try:
        taux = f.change(devises) if devises else {"EUR": 1.0}
    except Exception as e:  # noqa: BLE001
        taux, erreur = {"EUR": 1.0}, f"change : {type(e).__name__}: {str(e)[:150]}"
    executees, annulees = [], []
    # ventes d'abord (elles financent les achats), puis dans l'ordre chronologique des cours
    pretes = [o for o in ordres if o["symbole"] in barres and lire_iso(barres[o["symbole"]]["le"]) >= lire_iso(o["cree_le"])]
    pretes.sort(key=lambda o: (0 if o["sens"] == "vente" else 1, barres[o["symbole"]]["le"]))
    for o in pretes:
        b = barres[o["symbole"]]
        prix_eur_brut = en_euros(b["prix"], o["devise"], taux)
        if prix_eur_brut is None:
            continue  # taux de change indisponible : l'ordre attend
        op = _vendre(etat, o, b, taux, config) if o["sens"] == "vente" else _acheter(etat, o, b, taux, config)
        if op is None:
            o["statut"] = "annulé"
            annulees.append(o)
            continue
        o["statut"] = "exécuté"
        executees.append(op)
    for o in ordres:
        if o["statut"] == "en attente" and maintenant >= lire_iso(o["expire_le"]):
            o["statut"] = "expiré"
            o["note"] = "aucun cours disponible avant l'expiration"
            annulees.append(o)
    etat["ordres"] = [o for o in etat["ordres"] if o.get("statut") == "en attente"]
    return executees, annulees, erreur


def _operation(etat: dict, o: dict, b: dict, taux: dict, **champs) -> dict:
    dev, facteur = devise_iso(o["devise"])
    return {"id": o["id"], "date": b["le"], "decide_le": o["cree_le"], "sens": o["sens"], "symbole": o["symbole"], "nom": o["nom"],
            "ligne_id": o.get("ligne_id"), "poche": o.get("poche"), "classe": o.get("classe"), "devise": o["devise"],
            "cours_marche": round(b["prix"], 6), "barre": b.get("barre"), "taux_change": round(taux.get(dev, 1.0), 6),
            "motif": o.get("motif"), "imposee": bool(o.get("imposee")), "raison": o.get("raison"), "donner_tort": o.get("donner_tort", []), **champs}


def _acheter(etat: dict, o: dict, b: dict, taux: dict, config: dict) -> dict | None:
    de = demi_ecart(o["symbole"], o.get("type"), config)
    prix_local = b["prix"] * (1 + de)
    prix_eur = en_euros(prix_local, o["devise"], taux)
    montant = min(o["montant_eur"], etat["liquidites"])
    taux_frais = config["execution"]["frais_pct"] / 100
    q = math.floor(montant / (prix_eur * (1 + taux_frais)))
    while q > 0 and q * prix_eur + frais(q * prix_eur, config) > etat["liquidites"] + 1e-9:
        q -= 1
    if q <= 0:
        o["note"] = (f"montant ({montant:.0f} €) inférieur au prix d'une part ({prix_eur:.2f} €) ou liquidités insuffisantes")
        return None
    cout = q * prix_eur
    fr_ = frais(cout, config)
    ecart_eur = q * (prix_local - b["prix"]) * devise_iso(o["devise"])[1] / taux[devise_iso(o["devise"])[0]]
    etat["liquidites"] -= cout + fr_
    etat["frais_total"] = etat.get("frais_total", 0.0) + fr_
    etat["ecarts_total"] = etat.get("ecarts_total", 0.0) + ecart_eur
    p = etat["positions"].get(o["symbole"])
    sp = config["stops"]
    if p is None:
        p = {"symbole": o["symbole"], "nom": o["nom"], "ligne_id": o.get("ligne_id"), "poche": o.get("poche"), "classe": o.get("classe"),
             "type": o.get("type"), "pays": o.get("pays"), "secteur": o.get("secteur"), "themes": o.get("themes") or [], "devise": o["devise"],
             "quantite": 0, "cout_total_eur": 0.0, "prix_revient_local": 0.0, "ouverte_le": b["le"], "familles": o.get("familles") or {},
             "conviction": (o.get("raison") or {}).get("conviction"), "verdict": (o.get("raison") or {}).get("verdict"),
             "plus_haut_local": prix_local, "stop_local": None, "stop_type": None, "confirmations_stop": 0, "prise_benefices_faite": False,
             "contango": o.get("contango", False), "realise_eur": 0.0, "frais_eur": 0.0}
        etat["positions"][o["symbole"]] = p
    p["prix_revient_local"] = (p["prix_revient_local"] * p["quantite"] + prix_local * q) / (p["quantite"] + q)
    p["quantite"] += q
    p["cout_total_eur"] += cout + fr_
    p["frais_eur"] += fr_
    p["prix_revient_eur"] = p["cout_total_eur"] / p["quantite"]
    p["dernier_cours_local"], p["dernier_cours_le"] = b["prix"], b["le"]
    p["dernier_cours_eur"] = en_euros(b["prix"], o["devise"], taux)
    if p["poche"] == "satellite":
        initial = p["prix_revient_local"] * (1 - sp["stop_pct"] / 100)
        if p["stop_type"] != "suiveur" or (p["stop_local"] or 0) < initial:
            p["stop_local"], p["stop_type"] = initial, "initial"
    return _operation(etat, o, b, taux, quantite=q, prix_local=round(prix_local, 6), prix_eur=round(prix_eur, 6), montant_eur=round(cout, 2),
                      frais_eur=round(fr_, 2), ecart_eur=round(ecart_eur, 2), stop=round(p["stop_local"], 6) if p.get("stop_local") else None)


def _vendre(etat: dict, o: dict, b: dict, taux: dict, config: dict) -> dict | None:
    p = etat["positions"].get(o["symbole"])
    if not p or p["quantite"] <= 0:
        o["note"] = "position déjà soldée"
        return None
    q = min(o["quantite"], p["quantite"])
    de = demi_ecart(o["symbole"], p.get("type"), config)
    prix_local = b["prix"] * (1 - de)
    prix_eur = en_euros(prix_local, p["devise"], taux)
    produit = q * prix_eur
    fr_ = frais(produit, config)
    ecart_eur = q * (b["prix"] - prix_local) * devise_iso(p["devise"])[1] / taux[devise_iso(p["devise"])[0]]
    revient = q * p["prix_revient_eur"]
    pv = produit - fr_ - revient
    etat["liquidites"] += produit - fr_
    etat["frais_total"] = etat.get("frais_total", 0.0) + fr_
    etat["ecarts_total"] = etat.get("ecarts_total", 0.0) + ecart_eur
    attribuer(etat.setdefault("attribution", {}), p, pv)
    p["quantite"] -= q
    p["cout_total_eur"] -= revient
    p["realise_eur"] += pv
    p["frais_eur"] += fr_
    if o.get("motif") == "prise de bénéfices":
        p["prise_benefices_faite"] = True
    if o.get("motif") in ("stop", "sortie sur verdict", "sortie sur objection"):
        # pas de rachat immédiat d'une ligne sortie sur une règle de risque (évite les allers-retours)
        fin = (lire_iso(b["le"]) + timedelta(days=config["stops"]["delai_rachat_jours"])).date().isoformat()
        etat.setdefault("interdits", {})[o["symbole"]] = {"jusqua": fin, "motif": o["motif"]}
    stop = p.get("stop_local")
    duree = (lire_iso(b["le"]) - lire_iso(p["ouverte_le"])).days if p.get("ouverte_le") else None
    op = _operation(etat, o, b, taux, quantite=q, prix_local=round(prix_local, 6), prix_eur=round(prix_eur, 6), montant_eur=round(produit, 2),
                    frais_eur=round(fr_, 2), ecart_eur=round(ecart_eur, 2), stop=round(stop, 6) if stop else None,
                    resultat={"plus_value_eur": round(pv, 2), "plus_value_pct": round(pv / revient * 100, 2) if revient else None,
                              "prix_revient_eur": round(p["prix_revient_eur"], 6), "duree_jours": duree, "solde": p["quantite"] == 0,
                              "poche": p.get("poche"), "familles": {k: v.get("note") for k, v in (p.get("familles") or {}).items()}})
    if p["quantite"] == 0:
        del etat["positions"][o["symbole"]]
    return op


# ------------------------------------------------------------------ valorisation

def valoriser(etat: dict, cours: dict, taux: dict) -> dict:
    """Met à jour les cours des positions (cours connus) et renvoie la valorisation en euros."""
    total_positions = 0.0
    manquants = []
    for s, p in etat["positions"].items():
        c = cours.get(s)
        if c:
            eur = en_euros(c["cours"], p["devise"], taux)
            if eur is not None:
                p["dernier_cours_local"], p["dernier_cours_le"], p["dernier_cours_eur"] = c["cours"], c["le"], eur
                p["plus_haut_local"] = max(p.get("plus_haut_local") or 0, c["cours"])
        if p.get("dernier_cours_eur") is None:
            p["dernier_cours_eur"] = p["prix_revient_eur"]
            manquants.append(s)
        elif not c:
            manquants.append(s)
        p["valeur_eur"] = p["quantite"] * p["dernier_cours_eur"]
        total_positions += p["valeur_eur"]
    valeur = etat["liquidites"] + total_positions
    for p in etat["positions"].values():
        p["poids"] = p["valeur_eur"] / valeur * 100 if valeur else 0
    return {"valeur": valeur, "positions": total_positions, "liquidites": etat["liquidites"], "manquants": manquants}
