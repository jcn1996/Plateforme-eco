"""
Analyse de l'agent initiés (fonctions pures, testables sans réseau) : lecture des formulaires 4, 13D et 13F
de la SEC, des déclarations des dirigeants de l'AMF et de la BaFin, des déclarations des élus du Congrès ;
score « achats d'initiés » /100 par société, ventes massives et groupées, conviction des super-investisseurs,
signaux pour le chef d'orchestre. Règles détaillées : agents/inities/regles.md.
"""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta

MOIS_FR = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
           "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
LIBELLES_FONCTION = {"pdg_daf": "PDG ou directeur financier", "dirigeant": "dirigeant", "administrateur": "administrateur",
                     "actionnaire_10pct": "actionnaire de plus de 10 %", "autre": "autre initié"}
PAYS_FR = {"IN": "Inde", "TR": "Turquie", "KR": "Corée", "JP": "Japon", "FR": "France", "DE": "Allemagne", "US": "États-Unis"}
MENTION_13F = "13F : positions américaines uniquement, avec jusqu'à 45 jours de retard"
MENTION_HORS_US = "positions hors États-Unis visibles uniquement au-dessus des seuils légaux"
MENTION_ELUS = "Élus du Congrès : affiché pour information, sans effet sur les notes"


# ------------------------------------------------------------------ outils

def jour(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def fr(x: float | None, dec: int = 1) -> str:
    if x is None:
        return "n. d."
    s = f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def montant_fr(v: float | None, devise: str = "$") -> str:
    if v is None:
        return "n. d."
    a = abs(v)
    if a >= 1e9:
        return f"{fr(v / 1e9, 2)} Md{devise}"
    if a >= 1e6:
        return f"{fr(v / 1e6, 1)} M{devise}"
    if a >= 1e3:
        return f"{fr(v / 1e3, 0)} k{devise}"
    return f"{fr(v, 0)} {devise}"


def date_fr(d: str | None) -> str:
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d and len(d) >= 10 else (d or "n. d.")


def normaliser_nom(nom: str | None) -> str:
    """Nom de société simplifié pour les rapprochements (sans accents, ponctuation ni forme juridique)."""
    if not nom:
        return ""
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    mots = [m for m in s.split() if m not in {
        "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "sa", "se", "ag", "nv", "the",
        "group", "groupe", "holding", "holdings", "cl", "class", "a", "b", "com", "new", "de", "et", "kgaa", "sca", "spa", "llc", "lp"}]
    return " ".join(mots)


def trimestre_fr(periode: str | None) -> str:
    if not periode:
        return "n. d."
    m = int(periode[5:7])
    return f"T{(m - 1) // 3 + 1} {periode[:4]}"


def _texte(e, chemin: str) -> str | None:
    x = e.find(chemin)
    if x is None:
        return None
    v = x.find("value")
    t = (v.text if v is not None else x.text) or ""
    return t.strip() or None


def _nombre(t) -> float | None:
    try:
        return float(str(t).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _xml_dans(texte: str, balise: str) -> ET.Element | None:
    m = re.search(rf"<{balise}[\s>].*?</{balise}>", texte, re.S)
    if not m:
        return None
    brut = re.sub(r"\sxmlns(:\w+)?=\"[^\"]*\"", "", m.group(0))
    brut = re.sub(r"<(/?)\w+:", r"<\1", brut)  # préfixes d'espaces de noms (ns1:infoTable)
    brut = re.sub(r"&(?!\w+;|#\d+;)", "&amp;", brut)  # « S&P » non échappé
    try:
        return ET.fromstring(brut)
    except ET.ParseError:
        return None


# ------------------------------------------------------------------ formulaire 4

def fonction(d: dict) -> str:
    """Catégorie de fonction d'un déclarant de formulaire 4 (le PDG et le directeur financier pèsent plus)."""
    titre = (d.get("titre") or "").lower()
    if re.search(r"\bceo\b|chief executive|\bcfo\b|chief financial|principal financial|principal executive|président-directeur|pdg|directeur financier", titre):
        return "pdg_daf"
    if d.get("dirigeant"):
        return "dirigeant"
    if d.get("administrateur"):
        return "administrateur"
    if d.get("dix_pct"):
        return "actionnaire_10pct"
    return "autre"


def lire_form4(texte: str) -> dict | None:
    """Formulaire 4 (texte complet du dépôt EDGAR) → émetteur, déclarants, transactions non dérivées."""
    doc = _xml_dans(texte, "ownershipDocument")
    if doc is None:
        return None
    em = doc.find("issuer")
    declarants = []
    for r in doc.findall("reportingOwner"):
        rel = r.find("reportingOwnerRelationship")

        def drapeau(n, rel=rel):
            return (_texte(rel, n) or "0").lower() in ("1", "true") if rel is not None else False
        declarants.append({"cik": _texte(r, "reportingOwnerId/rptOwnerCik"), "nom": _texte(r, "reportingOwnerId/rptOwnerName"),
                           "administrateur": drapeau("isDirector"), "dirigeant": drapeau("isOfficer"), "dix_pct": drapeau("isTenPercentOwner"),
                           "titre": _texte(rel, "officerTitle") if rel is not None else None})
    notes = {f.get("id"): (f.text or "").strip() for f in doc.findall("footnotes/footnote")}
    transactions = []
    for t in doc.findall("nonDerivativeTable/nonDerivativeTransaction"):
        ids = [x.get("id") for x in t.iter("footnoteId")]
        transactions.append({
            "titre": _texte(t, "securityTitle"), "date": _texte(t, "transactionDate"), "code": _texte(t, "transactionCoding/transactionCode"),
            "actions": _nombre(_texte(t, "transactionAmounts/transactionShares")),
            "prix": _nombre(_texte(t, "transactionAmounts/transactionPricePerShare")),
            "sens": _texte(t, "transactionAmounts/transactionAcquiredDisposedCode"),
            "apres": _nombre(_texte(t, "postTransactionAmounts/sharesOwnedFollowingTransaction")),
            "direct": _texte(t, "ownershipNature/directOrIndirectOwnership") != "I",
            "notes": [notes[i] for i in ids if notes.get(i)],
        })
    programme = (_texte(doc, "aff10b5One") or "0").lower() in ("1", "true")
    remarques = _texte(doc, "remarks") or ""
    return {"type": _texte(doc, "documentType"),
            "emetteur": {"cik": _texte(em, "issuerCik") if em is not None else None, "nom": _texte(em, "issuerName") if em is not None else None,
                         "ticker": (_texte(em, "issuerTradingSymbol") or "").upper().replace(".", "-") or None if em is not None else None},
            "declarants": declarants, "programme_10b5_1": programme, "remarques": remarques, "transactions": transactions}


def _programme(f4: dict, t: dict) -> bool:
    """Opération programmée : case 10b5-1 cochée, ou plan 10b5-1 cité dans une note de la transaction."""
    return f4["programme_10b5_1"] or any(re.search(r"10b5-?1", n, re.I) for n in t["notes"])


def operations(f4: dict, accession: str, depot: str) -> list[dict]:
    """Achats sur le marché (code P) et ventes sur le marché (code S) d'un formulaire 4, une ligne par déclarant
    principal et par sens. Exclus : exercices d'options (M), attributions (A), donations (G), opérations programmées
    (10b5-1, pour les achats ; pour les ventes, la mention est conservée)."""
    if not f4 or f4.get("type") not in ("4", None) or not f4["declarants"]:
        return []
    d = f4["declarants"][0]
    res = []
    for code, sens, genre in (("P", "A", "achat"), ("S", "D", "vente")):
        lignes = [t for t in f4["transactions"] if t["code"] == code and t["sens"] == sens and t["actions"]]
        if genre == "achat":
            lignes = [t for t in lignes if not _programme(f4, t)]
        if not lignes:
            continue
        actions = sum(t["actions"] for t in lignes)
        montant = sum(t["actions"] * (t["prix"] or 0) for t in lignes)
        directes = [t for t in lignes if t["direct"]] or lignes
        apres = directes[-1]["apres"]
        if genre == "achat":
            avant = None if apres is None else max(0.0, apres - sum(t["actions"] for t in directes))
        else:
            avant = None if apres is None else apres + sum(t["actions"] for t in directes)
        res.append({
            "acc": accession, "depot": depot, "date": min(t["date"] for t in lignes if t["date"]) if any(t["date"] for t in lignes) else depot,
            "pays": "US", "ticker": f4["emetteur"]["ticker"], "cik": (f4["emetteur"]["cik"] or "").lstrip("0") or None,
            "societe": f4["emetteur"]["nom"], "declarant": d["nom"], "cik_declarant": (d["cik"] or "").lstrip("0") or None,
            "fonction": fonction(d), "titre": d.get("titre") or ("Administrateur" if d["administrateur"] else None),
            "type": genre, "actions": round(actions, 4), "prix": round(montant / actions, 4) if actions and montant else None,
            "montant": round(montant, 2) if montant else None, "avant": avant, "apres": apres,
            "programme": any(_programme(f4, t) for t in lignes), "devise": "USD",
        })
    return res


# ------------------------------------------------------------------ score « achats d'initiés »

def palier(v: float, paliers: list[list[float]]) -> float:
    for seuil, note in paliers:
        if v >= seuil:
            return note
    return paliers[-1][1]


def caractere(a: dict, historique: list[dict], cours: list | None, cfg: dict, debut_historique: str | None) -> tuple[str, str]:
    """« opportuniste », « routinier » ou « inconnu », avec la raison. Opportuniste : le dirigeant n'achète pas
    habituellement (aucun autre achat dans les 12 mois précédents, historique suffisant), ou il achète après une baisse
    du cours d'au moins baisse_cours_pct % sur 3 mois. Routinier : au moins routinier_achats_min achats dans les
    12 mois précédents."""
    s = cfg["score"]
    d = jour(a["date"])
    baisse = None
    if cours:
        avant = [c for dd, c in cours if jour(dd) <= d - timedelta(days=91)]
        au_jour = [c for dd, c in cours if jour(dd) <= d]
        if avant and au_jour:
            baisse = (au_jour[-1] / avant[-1] - 1) * 100
    if baisse is not None and baisse <= -s["baisse_cours_pct"]:
        return "opportuniste", f"achat après une baisse du cours de {fr(abs(baisse), 0)} % sur 3 mois"
    cle = a.get("cik_declarant") or a.get("declarant")
    precedents = [h for h in historique if (h.get("cik_declarant") or h.get("declarant")) == cle and h.get("ticker") == a.get("ticker")
                  and d - timedelta(days=365) <= jour(h["date"]) < d - timedelta(days=31)]
    if len(precedents) >= s["routinier_achats_min"]:
        return "routinier", f"{len(precedents)} autres achats dans les 12 mois précédents (achats réguliers)"
    suffisant = debut_historique and (d - jour(debut_historique)).days >= s["historique_min_jours"]
    if not precedents and suffisant:
        return "opportuniste", "aucun autre achat de ce dirigeant dans les 12 mois précédents"
    if precedents:
        return "inconnu", f"{len(precedents)} autre{'s' if len(precedents) > 1 else ''} achat{'s' if len(precedents) > 1 else ''} dans les 12 mois précédents"
    return "inconnu", "historique des achats de ce dirigeant encore trop court pour juger"


def score_societe(achats: list[dict], historique: list[dict], cours: list | None, cap_md: float | None, cfg: dict,
                  aujourdhui: date, debut_historique: str | None) -> dict | None:
    """Score « achats d'initiés » /100 d'une société, à partir de ses achats des fenetre_score_jours derniers jours."""
    ca, s = cfg["achats"], cfg["score"]
    recents = [a for a in achats if (aujourdhui - jour(a["date"])).days <= ca["fenetre_score_jours"]]
    if not recents:
        return None
    detail = []
    note_opp = 0.0
    for a in recents:
        nature, raison = caractere(a, historique, cours, cfg, debut_historique)
        a["caractere"], a["caractere_raison"] = nature, raison
        note_opp = max(note_opp, {"opportuniste": 1.0, "inconnu": 0.5, "routinier": 0.0}[nature])
    groupe_debut = aujourdhui - timedelta(days=ca["fenetre_groupe_jours"])
    acheteurs_30 = {a.get("cik_declarant") or a["declarant"] for a in recents if jour(a["date"]) >= groupe_debut}
    n = len(acheteurs_30)
    note_groupe = s["groupe"][str(min(3, n))] if n else 0.0
    note_fonction = max(s["fonction"].get(a["fonction"], s["fonction"]["autre"]) for a in recents)
    relatifs = []
    for a in recents:
        if a.get("avant") == 0 and a.get("apres"):
            relatifs.append(100.0)  # premier achat : toute la position
        elif a.get("avant") and a.get("actions"):
            relatifs.append(a["actions"] / a["avant"] * 100)
    note_montant = palier(max(relatifs), s["montant_relatif"]) if relatifs else 0.5
    # Taille : signal plus fort sur les petites et moyennes valeurs (capitalisation en milliards de dollars)
    note_taille = (next((n for seuil, n in s["taille_md"] if cap_md < seuil), s["taille_md"][-1][1]) if cap_md
                   else s["taille_inconnue"])
    comp = {"opportuniste": note_opp, "groupe": note_groupe, "fonction": note_fonction, "montant_relatif": note_montant, "taille": note_taille}
    poids = s["poids"]
    score = round(100 * sum(poids[k] * v for k, v in comp.items()) / sum(poids.values()))
    total = sum(a.get("montant") or 0 for a in recents)
    fonctions = sorted({LIBELLES_FONCTION[a["fonction"]] for a in recents})
    detail.append(f"{len(recents)} achat{'s' if len(recents) > 1 else ''} sur le marché en {ca['fenetre_score_jours']} jours"
                  f" ({montant_fr(total, '$' if recents[0].get('devise', 'USD') == 'USD' else ' ' + recents[0]['devise'])})")
    if n >= 2:
        detail.append(f"{n} acheteurs distincts en {ca['fenetre_groupe_jours']} jours (achats groupés)")
    detail.append("fonctions : " + ", ".join(fonctions))
    if relatifs:
        r = min(999, max(relatifs))
        detail.append(f"jusqu'à {fr(r, 0 if r >= 1 else 1)} % de ce que le dirigeant détenait déjà")
    opp = [a for a in recents if a["caractere"] == "opportuniste"]
    if opp:
        detail.append(opp[0]["caractere_raison"])
    elif all(a["caractere"] == "routinier" for a in recents):
        detail.append("achats routiniers")
    return {"score": score, "composantes": {k: round(v, 2) for k, v in comp.items()}, "acheteurs_30j": n, "achats": len(recents),
            "montant_total": round(total, 2) if total else None, "dernier_achat": max(a["date"] for a in recents),
            "texte": " ; ".join(detail) + "."}


def ventes_massives(ventes: list[dict], cfg: dict, aujourdhui: date) -> dict | None:
    """Ventes massives et groupées (seul cas où les ventes des dirigeants sont un signal négatif)."""
    cv = cfg["ventes"]
    recentes = [v for v in ventes if (aujourdhui - jour(v["date"])).days <= cv["fenetre_jours"] and not v.get("programme")]
    par_vendeur = defaultdict(list)
    for v in recentes:
        par_vendeur[v.get("cik_declarant") or v["declarant"]].append(v)
    if len(par_vendeur) < cv["vendeurs_min"]:
        return None
    total = sum(v.get("montant") or 0 for v in recentes)
    parts = []
    for lst in par_vendeur.values():
        avant = max((v.get("avant") or 0) for v in lst)
        vendu = sum(v["actions"] for v in lst)
        if avant > 0:
            parts.append(min(100.0, vendu / avant * 100))
    part = sum(parts) / len(parts) if parts else 0.0
    if total < cv["montant_min_usd"] or part < cv["part_moyenne_min_pct"]:
        return None
    return {"vendeurs": len(par_vendeur), "montant_total": round(total, 2), "part_moyenne_pct": round(part, 1),
            "texte": f"{len(par_vendeur)} dirigeants ont vendu {montant_fr(total)} en {cv['fenetre_jours']} jours, "
                     f"soit en moyenne {fr(part, 0)} % de ce qu'ils détenaient (hors ventes programmées)."}


# ------------------------------------------------------------------ 13F

def lire_13f(texte: str) -> dict:
    """Rapport 13F (texte complet du dépôt) → période et positions agrégées par CUSIP (actions ordinaires et options séparées)."""
    periode = re.search(r"<(?:\w+:)?periodOfReport>\s*(\d\d)-(\d\d)-(\d{4})", texte)
    positions: dict[str, dict] = {}
    for bloc in re.findall(r"<(?:\w+:)?infoTable>.*?</(?:\w+:)?infoTable>", texte, re.S):
        e = _xml_dans(re.sub(r"<(/?)\w+:", r"<\1", bloc), "infoTable")
        if e is None:
            continue
        cusip = (_texte(e, "cusip") or "").upper()
        option = (_texte(e, "putCall") or "").upper() or None
        cle = f"{cusip}|{option}" if option else cusip
        p = positions.setdefault(cle, {"cusip": cusip, "nom": _texte(e, "nameOfIssuer"), "classe": _texte(e, "titleOfClass"),
                                       "valeur": 0.0, "actions": 0.0, "option": option})
        p["valeur"] += _nombre(_texte(e, "value")) or 0.0
        p["actions"] += _nombre(_texte(e, "shrsOrPrnAmt/sshPrnamt")) or 0.0
    return {"periode": f"{periode.group(3)}-{periode.group(1)}-{periode.group(2)}" if periode else None, "positions": positions}


def comparer_13f(actuel: dict, precedent: dict | None, cfg: dict) -> dict:
    """Poids, principales positions, nouvelles positions, renforcements, allègements et sorties d'un 13F."""
    c = cfg["super_investisseurs"]
    pos = {k: p for k, p in actuel["positions"].items() if not p["option"]}
    total = sum(p["valeur"] for p in pos.values()) or 1.0
    prec = {k: p for k, p in ((precedent or {}).get("positions") or {}).items() if not p["option"]}
    total_prec = sum(p["valeur"] for p in prec.values()) or 1.0
    lignes = []
    for k, p in pos.items():
        poids = p["valeur"] / total * 100
        a = prec.get(k)
        if precedent is None:
            mouvement, var = None, None
        elif a is None:
            mouvement, var = "nouvelle", None
        else:
            var = (p["actions"] / a["actions"] - 1) * 100 if a["actions"] else None
            mouvement = ("renforcement" if var is not None and var >= c["mouvement_min_pct"] else
                         "allègement" if var is not None and var <= -c["mouvement_min_pct"] else None)
        lignes.append({"cusip": p["cusip"], "nom": p["nom"], "classe": p["classe"], "valeur": round(p["valeur"]), "actions": p["actions"],
                       "poids": round(poids, 2), "mouvement": mouvement, "variation_actions_pct": round(var, 1) if var is not None else None})
    lignes.sort(key=lambda x: x["valeur"], reverse=True)
    sorties = [{"cusip": a["cusip"], "nom": a["nom"], "poids_precedent": round(a["valeur"] / total_prec * 100, 2)}
               for k, a in prec.items() if k not in pos]
    sorties.sort(key=lambda x: x["poids_precedent"], reverse=True)
    importants = [x for x in lignes if x["poids"] >= c["poids_min_mouvement_pct"] or x["mouvement"] == "nouvelle"]
    options = [{"cusip": p["cusip"], "nom": p["nom"], "option": p["option"], "valeur": round(p["valeur"])}
               for p in actuel["positions"].values() if p["option"]]
    return {
        "valeur_totale": round(total), "nb_positions": len(pos), "positions": lignes,
        "nouvelles": [x for x in lignes if x["mouvement"] == "nouvelle"],
        "renforcements": [x for x in importants if x["mouvement"] == "renforcement"],
        "allegements": [x for x in importants if x["mouvement"] == "allègement"],
        "sorties": [x for x in sorties if x["poids_precedent"] >= c["poids_min_mouvement_pct"]] or sorties[:5],
        "options": sorted(options, key=lambda x: x["valeur"], reverse=True)[:10],
    }


def points_poids(poids: float, cfg: dict) -> float:
    return palier(poids, cfg["super_investisseurs"]["paliers_poids_pct"])


def conviction(detentions: dict[str, list[dict]], cfg: dict) -> dict[str, dict]:
    """detentions : {ticker: [{cle, nom, poids, mouvement}]} → signal « conviction des super-investisseurs » par société :
    nombre de super-investisseurs qui détiennent (ou ont acheté) le titre et poids dans leurs portefeuilles."""
    c = cfg["super_investisseurs"]
    res = {}
    for t, lst in detentions.items():
        pts = 0.0
        for x in lst:
            pts += points_poids(x.get("poids") or 0, cfg) if x.get("poids") is not None else 1.0
            if x.get("mouvement") in ("nouvelle", "renforcement"):
                pts += c["bonus_achat"]
        score = min(100, round(pts * c["points_vers_score"]))
        tri = sorted(lst, key=lambda x: x.get("poids") or 0, reverse=True)
        noms = ", ".join(f"{x['nom']} ({fr(x['poids'], 1)} %)" if x.get("poids") is not None else f"{x['nom']} (hors États-Unis)" for x in tri[:4])
        achats = [x for x in lst if x.get("mouvement") in ("nouvelle", "renforcement")]
        res[t] = {"score": score, "nombre": len({x["cle"] for x in lst}), "poids_max": max((x.get("poids") or 0) for x in lst),
                  "investisseurs": tri,
                  "texte": f"{len({x['cle'] for x in lst})} super-investisseur{'s' if len(lst) > 1 else ''} : {noms}"
                           + (f" ; achat récent : {', '.join(x['nom'] for x in achats)}" if achats else "") + "."}
    return res


def statut_13f(periode: str | None, aujourdhui: date, cfg: dict) -> str:
    """« actif » ou « inactif » (dernier 13F trop ancien : l'entité ne dépose plus)."""
    if not periode:
        return "inactif"
    retard = (aujourdhui.year - int(periode[:4])) * 4 + ((aujourdhui.month - 1) // 3 - (int(periode[5:7]) - 1) // 3)
    return "inactif" if retard > cfg["super_investisseurs"]["inactif_trimestres"] + 1 else "actif"


# ------------------------------------------------------------------ 13D

def lire_13d(texte: str) -> dict | None:
    """Schedule 13D (XML depuis décembre 2024 ; ancien format texte : en-tête SGML seulement)."""
    em_nom = re.search(r"<issuerName>\s*([^<]+)", texte)
    em_cik = re.search(r"<issuerCIK>\s*(\d+)", texte)
    personnes = re.findall(r"<reportingPersonName>\s*([^<]+)", texte)
    pcts = [_nombre(x) for x in re.findall(r"<percentOfClass>\s*([^<]+)", texte)]
    evt = re.search(r"<dateOfEvent>\s*(\d\d)/(\d\d)/(\d{4})", texte)
    cusip = re.search(r"<issuerCusipNumber>\s*([0-9A-Z]{6,9})", texte)
    if not em_nom:  # ancien format : en-tête SGML
        sujet = re.search(r"SUBJECT COMPANY:.*?COMPANY CONFORMED NAME:\s*([^\n]+).*?CENTRAL INDEX KEY:\s*(\d+)", texte, re.S)
        par = re.search(r"FILED BY:.*?COMPANY CONFORMED NAME:\s*([^\n]+)", texte, re.S)
        if not sujet:
            return None
        return {"societe": sujet.group(1).strip(), "cik": sujet.group(2).lstrip("0"), "investisseur": par.group(1).strip() if par else None,
                "personnes": [], "pct": None, "date_evenement": None, "cusip": None}
    par = re.search(r"FILED BY:.*?COMPANY CONFORMED NAME:\s*([^\n]+)", texte, re.S)
    pcts = [p for p in pcts if p is not None]
    return {"societe": em_nom.group(1).strip(), "cik": em_cik.group(1).lstrip("0") if em_cik else None,
            "investisseur": (par.group(1).strip() if par else (personnes[0].strip() if personnes else None)),
            "personnes": [p.strip() for p in personnes][:6], "pct": max(pcts) if pcts else None,
            "date_evenement": f"{evt.group(3)}-{evt.group(1)}-{evt.group(2)}" if evt else None,
            "cusip": cusip.group(1) if cusip and cusip.group(1).strip("0") else None}


# ------------------------------------------------------------------ France (AMF) et Allemagne (BaFin)

def _date_fr_texte(t: str | None) -> str | None:
    if not t:
        return None
    m = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", t.lower())
    if m and m.group(2) in MOIS_FR:
        return f"{m.group(3)}-{MOIS_FR[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{2})[./](\d{2})[./](\d{4})", t)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def fonction_texte(t: str | None) -> str:
    s = (t or "").lower()
    if re.search(r"directeur g[ée]n[ée]ral|pdg|pr[ée]sident[- ]directeur|chief executive|\bceo\b|directeur financier|chief financial|\bcfo\b"
                 r"|vorstandsvorsitz|finanzvorstand|\bcfo\b", s):
        return "pdg_daf"
    if re.search(r"administrat|conseil de surveillance|aufsichtsrat|membre du conseil|board", s):
        return "administrateur"
    if re.search(r"directeur|dirigeant|g[ée]rant|vorstand|pr[ée]sident|executive|officer", s):
        return "dirigeant"
    if re.search(r"li[ée]e|associ|beziehung", s):
        return "autre"
    return "autre"


def lire_dd_amf(texte: str, numero: str, publication: str) -> dict | None:
    """Déclaration des dirigeants (PDF de la base BDIF, partie française) → acquisition d'actions, ou None
    (cession, options ou attribution gratuite, autre instrument)."""
    fr_part = texte.split("Individual notification")[0]
    nature = re.search(r"NATURE DE LA TRANSACTION\s*:\s*([^\n]+)", fr_part)
    instrument = re.search(r"DESCRIPTION DE L.INSTRUMENT FINANCIER\s*:\s*([^\n]+)", fr_part)
    options = re.search(r"ACTIONS GRATUITES OU DE PERFORMANCES\s*:\s*(\w+)", fr_part)
    personne = re.search(r"PERSONNE ETROITEMENT LIEE\s*:\s*\n?([^\n]+)", fr_part)
    nom = re.search(r"COORDONNEES DE L.EMETTEUR\s*\nNOM\s*:\s*([^\n]+)", fr_part)
    date_t = re.search(r"DATE DE LA TRANSACTION\s*:\s*([^\n]+)", fr_part)
    agr = re.search(r"INFORMATIONS AGREGEES\s*\nPRIX\s*:\s*([\d.,\s]+)\s*([A-Za-z]+)\s*\nVOLUME\s*:\s*([\d.,\s]+)", fr_part)
    isin = re.search(r"\b([A-Z]{2}[0-9A-Z]{9}\d)\b", fr_part)
    if not (nature and nom and agr):
        return None
    est_achat = re.search(r"acquisition|achat|souscription", nature.group(1), re.I) and not re.search(r"cession|vente", nature.group(1), re.I)
    if not est_achat or not re.search(r"action", (instrument.group(1) if instrument else ""), re.I):
        return None
    if options and options.group(1).upper().startswith("OUI"):
        return None
    if re.search(r"souscription|attribution|exercice", nature.group(1), re.I):
        return None
    prix = _nombre(agr.group(1).replace(" ", "").replace(",", "."))
    volume = _nombre(agr.group(3).replace(" ", "").replace(",", "."))
    qui, _, role = (personne.group(1).strip() if personne else "").partition(",")
    return {"acc": numero, "depot": publication[:10], "date": _date_fr_texte(date_t.group(1) if date_t else None) or publication[:10],
            "pays": "FR", "ticker": None, "isin": isin.group(1) if isin else None, "societe": nom.group(1).strip(),
            "declarant": qui.strip() or None, "cik_declarant": None, "fonction": fonction_texte(role or qui), "titre": role.strip().capitalize() or None,
            "type": "achat", "actions": volume, "prix": prix, "montant": round(prix * volume, 2) if prix and volume else None,
            "avant": None, "apres": None, "programme": False, "devise": "EUR" if agr.group(2).lower().startswith("eur") else agr.group(2)}


def lire_bafin(csv_texte: str) -> list[dict]:
    """Export CSV des « Directors' Dealings » de la BaFin → achats d'actions (Kauf)."""
    res = []
    lignes = [l for l in csv_texte.lstrip("﻿").splitlines() if l.strip()]
    if not lignes:
        return res
    tete = [x.strip() for x in lignes[0].split(";")]

    def col(v, nom):
        try:
            return v[tete.index(nom)].strip()
        except (ValueError, IndexError):
            return ""

    def montant(t):
        m = re.match(r"([\d.,]+)\s*(\w+)?", t.strip())
        if not m:
            return None, None
        return _nombre(m.group(1).replace(".", "").replace(",", ".")), (m.group(2) or "EUR")
    for l in lignes[1:]:
        v = l.split(";")
        if col(v, "Art des Geschäfts").lower() != "kauf" or col(v, "Art des Instruments").lower() not in ("aktie", "share", "aktien"):
            continue
        prix, devise = montant(col(v, "Durchschnittspreis"))
        volume_eur, _ = montant(col(v, "Aggregiertes Volumen"))
        d = _date_fr_texte(col(v, "Datum des Geschäfts")) or _date_fr_texte(col(v, "Mitteilungsdatum"))
        dep = _date_fr_texte(col(v, "Mitteilungsdatum")) or d
        position = col(v, "Position / Status")
        res.append({"acc": f"bafin-{col(v, 'ISIN')}-{col(v, 'Meldepflichtiger')}-{d}-{volume_eur}", "depot": dep, "date": d, "pays": "DE",
                    "ticker": None, "isin": col(v, "ISIN") or None, "societe": col(v, "Emittent"), "declarant": col(v, "Meldepflichtiger"),
                    "cik_declarant": None, "fonction": fonction_texte(position), "titre": position or None, "type": "achat",
                    "actions": round(volume_eur / prix, 2) if prix and volume_eur else None, "prix": prix, "montant": volume_eur,
                    "avant": None, "apres": None, "programme": False, "devise": devise})
    return res


# ------------------------------------------------------------------ franchissements de seuil (hors États-Unis)

def chercher_entites(texte: str, alias: list[str]) -> tuple[str, float | None] | None:
    """Une entité de l'investisseur citée dans un document, avec le pourcentage le plus proche après la mention."""
    bas = texte.lower()
    for a in sorted(alias, key=len, reverse=True):
        i = bas.find(a.lower())
        if i < 0:
            continue
        apres = texte[i:i + 600]
        # « 5,12 % » ou, en turc, « %5,40 » ; on préfère le pourcentage détenu au seuil franchi
        trouves = [(m.start(), _nombre((m.group(1) or m.group(2)).replace(",", ".")))
                   for m in re.finditer(r"(\d{1,2}(?:[.,]\d{1,4})?)\s*%|%\s*(\d{1,2}(?:[.,]\d{1,4})?)", apres)]
        trouves = [(p, v) for p, v in trouves if v is not None and v <= 100]
        if not trouves:
            return a, None
        detenus = [v for p, v in trouves if re.search(r"d[ée]ten|holds?|holding|repr[ée]sent|soit|oran", apres[max(0, p - 40):p], re.I)]
        return a, (detenus[-1] if detenus else max(v for _, v in trouves))
    return None


def nom_correspond(nom: str | None, alias: list[str]) -> str | None:
    """Alias de l'investisseur contenu dans un nom de déclarant ou d'actionnaire (casse et espaces ignorés).
    Comparaison sur le seul nom, jamais sur une adresse (« Dalal Street » est aussi l'adresse de la BSE)."""
    n = re.sub(r"\s+", " ", (nom or "").lower())
    return next((a for a in sorted(alias, key=len, reverse=True) if re.sub(r"\s+", " ", a.lower()) in n), None)


def lire_actionnariat_xbrl(xml: str) -> dict:
    """Répartition trimestrielle de l'actionnariat (XBRL de la NSE / BSE, taxonomie in-bse-shp) : date de fin de
    trimestre et actionnaires nommés (plus de 1 % pour les actionnaires publics, et promoteurs), avec leur part en %.
    Le nom est porté par le contexte « D_<x> », les nombres par le contexte « <x> » ; la part est une fraction."""
    fin = re.search(r"<xbrli:endDate>(\d{4}-\d\d-\d\d)</xbrli:endDate>", xml) or re.search(r"<xbrli:instant>(\d{4}-\d\d-\d\d)</xbrli:instant>", xml)
    valeurs: dict[str, dict] = defaultdict(dict)
    for m in re.finditer(r'<in-bse-shp:(NameOfTheShareholder|ShareholdingAsAPercentageOfTotalNumberOfShares|NumberOfShares)\s+contextRef="([^"]+)"[^>]*>([^<]*)<', xml):
        champ, ctx, v = m.groups()
        valeurs[ctx.removeprefix("D_")][champ] = v.strip()
    res = []
    for ctx, v in valeurs.items():
        nom = v.get("NameOfTheShareholder")
        pct = _nombre(v.get("ShareholdingAsAPercentageOfTotalNumberOfShares"))
        if not nom or pct is None:
            continue
        res.append({"nom": nom, "pct": round(pct * 100, 2) if pct <= 1 else round(pct, 2), "actions": _nombre(v.get("NumberOfShares")),
                    "categorie": re.sub(r"_Context\d+$", "", ctx)})
    return {"date": fin.group(1) if fin else None, "actionnaires": res}


def pct_kap(texte: str) -> float | None:
    """Pourcentage détenu après l'opération dans une notification turque (« … %6,25 sınırına ulaşmıştır »,
    « sermayedeki payım %5,40 »)."""
    for motif in (r"%\.?\s*(\d{1,2}(?:[.,]\d+)?)\s*(?:sınır|oran|seviye)", r"(\d{1,2}(?:[.,]\d+)?)\s*%?\s*(?:sınırına|oranına|seviyesine)",
                  r"%\.?\s*(\d{1,2}(?:[.,]\d+)?)"):
        trouves = re.findall(motif, texte, re.I)
        if trouves:
            return _nombre(trouves[-1].replace(",", "."))
    return None


def positions_hors_us(evenements: list[dict]) -> list[dict]:
    """Dernière déclaration connue par investisseur et par société : position visible au-dessus des seuils légaux,
    ou passée sous le seuil (cession sous 5 %, absente de la liste des actionnaires de plus de 1 %)."""
    dernier: dict[tuple, dict] = {}
    for e in sorted(evenements, key=lambda e: (e.get("date") or "", e.get("priorite", 0))):
        cle = (e["investisseur"], e["pays"], e.get("ticker") or normaliser_nom(e.get("societe")))
        dernier[cle] = e
    res = []
    for e in dernier.values():
        sous = e.get("type") == "sortie" or (e.get("pct") is not None and e.get("seuil") is not None and e["pct"] < e["seuil"])
        res.append({**e, "statut": "sous le seuil" if sous else "détenue"})
    return sorted(res, key=lambda e: (e["statut"] != "détenue", -(e.get("pct") or 0)))


# ------------------------------------------------------------------ élus du Congrès

def lire_index_chambre(xml: str) -> list[dict]:
    """Index annuel du greffe de la Chambre → déclarations de transactions (FilingType P)."""
    res = []
    for bloc in re.findall(r"<Member>(.*?)</Member>", xml, re.S):
        c = dict(re.findall(r"<(\w+)>([^<]*)</\1>", bloc))
        if c.get("FilingType") != "P" or not c.get("DocID"):
            continue
        try:
            depot = datetime.strptime(c["FilingDate"], "%m/%d/%Y").date().isoformat()
        except (KeyError, ValueError):
            continue
        nom = " ".join(x for x in (c.get("First"), c.get("Last"), c.get("Suffix")) if x)
        res.append({"doc": c["DocID"], "annee": c.get("Year"), "elu": nom, "circonscription": c.get("StateDst"), "depot": depot})
    return res


_PTR = re.compile(r"\(([A-Z][A-Z.\-]{0,6})\)\s*(?:\[(\w+)\])?\s*(P|S \(partial\)|S|E)\s+(\d\d/\d\d/\d{4})\s+(\d\d/\d\d/\d{4})\s+"
                  r"(\$[\d,]+(?:\s*-\s*\$[\d,]+)?|Over \$[\d,]+|Spouse/DC Over \$[\d,]+)", re.S)


def lire_ptr_chambre(texte: str) -> list[dict]:
    """Déclaration de transactions (PDF électronique, texte extrait) → opérations sur titres cotés."""
    res = []
    types = {"P": "achat", "S": "vente", "S (partial)": "vente partielle", "E": "échange"}
    for m in _PTR.finditer(texte):
        # Nom de l'actif : jusqu'à 2 lignes avant le ticker (le nom est souvent coupé en deux dans le PDF)
        lignes = [l.strip() for l in texte[max(0, m.start() - 200):m.start()].split("\n")]
        nom = []
        for l in reversed(lignes):
            if not l or re.search(r"\$|\d\d/\d\d/\d{4}|Gains|Type|\[|:", l) or len(nom) >= 2:
                break
            nom.insert(0, l)
        actif = re.sub(r"^(SP|JT|DC)\s+", "", " ".join(nom)).strip(" -") or None
        res.append({"ticker": m.group(1).replace(".", "-"), "actif": actif, "type": types[m.group(3)],
                    "date_operation": datetime.strptime(m.group(4), "%m/%d/%Y").date().isoformat(),
                    "date_notification": datetime.strptime(m.group(5), "%m/%d/%Y").date().isoformat(),
                    "montant": re.sub(r"\s+", " ", m.group(6))})
    return res


def lire_ptr_senat(html: str) -> list[dict]:
    """Déclaration de transactions électronique du Sénat (tableau HTML) → opérations."""
    res = []
    for ligne in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", ligne, re.S | re.I)]
        if len(c) < 8 or not re.match(r"\d\d/\d\d/\d{4}", c[1]):
            continue
        ticker = c[3] if c[3] not in ("--", "") else None
        sens = c[6].lower()
        res.append({"ticker": ticker, "actif": c[4], "type": "achat" if "purchase" in sens else "vente" if "sale" in sens else c[6],
                    "date_operation": datetime.strptime(c[1], "%m/%d/%Y").date().isoformat(), "date_notification": None, "montant": c[7]})
    return res


# ------------------------------------------------------------------ signaux

def signaux(scores: dict, nouveaux_13f: list[dict], nouveaux_13d: list[dict], cfg: dict, aujourdhui: date,
            emis: dict) -> list[dict]:
    """Signaux pour le chef d'orchestre : achats groupés de dirigeants, nouvelle position d'un super-investisseur,
    nouveau 13D. `emis` ({type|cle: date}) évite de répéter un signal d'achats groupés pendant 30 jours."""
    cs = cfg["signaux"]
    res = []
    d = aujourdhui.isoformat()
    for t, s in scores.items():
        if s["acheteurs_30j"] >= cs["acheteurs_min"]:
            cle = f"achats_groupes|{t}"
            if cle in emis and (aujourdhui - jour(emis[cle])).days < 30:
                continue
            emis[cle] = d
            res.append({"date": d, "type": "achats_groupes", "cle": t, "importance": "forte" if s["score"] >= 80 else "moyenne",
                        "titre": f"{s.get('nom') or t} : {s['acheteurs_30j']} dirigeants achètent sur le marché en 30 jours (score {s['score']}/100)",
                        "explication": s["texte"], "source": s.get("source") or "SEC EDGAR, formulaires 4"})
    for n in nouveaux_13f:
        res.append({"date": d, "type": "nouvelle_position_super_investisseur", "cle": n.get("ticker") or n["cusip"],
                    "importance": "forte" if n["poids"] >= 5 else "moyenne",
                    "titre": f"{n['investisseur']} ouvre une position dans {n['nom']} ({fr(n['poids'], 1)} % du portefeuille, {trimestre_fr(n['periode'])})",
                    "explication": f"Rapport 13F déposé le {date_fr(n['depot'])}. {MENTION_13F}.", "source": "SEC EDGAR, rapports 13F",
                    "investisseur": n["cle"]})
    for x in nouveaux_13d:
        res.append({"date": d, "type": "nouveau_13d", "cle": x.get("ticker") or x.get("cik") or x["societe"],
                    # Société suivie par l'agent entreprises ou super-investisseur : examiné par le contradicteur
                    "importance": "forte" if x.get("super_investisseur") else "moyenne" if x.get("suivie") else "faible",
                    "titre": f"{x['investisseur'] or 'Un investisseur'} déclare {fr(x['pct'], 1) + ' % de ' if x.get('pct') is not None else 'plus de 5 % de '}"
                             f"{x['societe']} (13D, intention d'influencer)",
                    "explication": f"Formulaire 13D déposé le {date_fr(x['depot'])}" + (f", événement du {date_fr(x['date_evenement'])}" if x.get("date_evenement") else "") + ".",
                    "source": "SEC EDGAR, formulaires 13D"})
    return res
