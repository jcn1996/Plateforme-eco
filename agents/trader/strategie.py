"""
Stratégie de l'agent trader (démo) : cibles du portefeuille, ordres et règles de risque. Règles : regles.md.

1. Portefeuille diversifié mais concentré : 15 lignes au plus (liquidités exceptées), 4 % minimum par ligne.
2. Cœur : 8 à 12 positions choisies parmi les opportunités « Renforcer » / « Renforcer fortement » de conviction
   moyenne ou forte du chef d'orchestre (ETF pays, ETF sectoriels régionaux, or, matières premières), jamais d'ETF
   monde ni d'ETF pays « Neutre » ; au moins 4 classes ou zones différentes ; corrélation entre lignes vérifiée sur
   1 an d'historique (une ligne trop corrélée à une ligne déjà retenue est écartée). Obligations : poids fixé par le
   verdict du chef d'orchestre (« Neutre » = poids neutre).
3. Satellites : convictions fortes seulement (entreprises), signaux d'au moins 2 agents, taille ∝ conviction /
   volatilité, 4 à 8 % par ligne. Poche « tendance » (une part des satellites) : tendances fortes et saines du chef
   d'orchestre, à parts égales ; on laisse courir les gagnants (stop suiveur, sortie quand la force relative quitte le
   premier tiers ou que la tendance casse, jamais de prise de bénéfices).
4. Jamais d'achat d'une opportunité « À surveiller » ou sous objection du contradicteur.
5. Une seule série de décisions par jour ; détention minimale de 5 jours (sauf stop) ; pas de rachat d'un titre
   vendu depuis moins de 5 jours.
6. Les lignes qui ne respectent plus les règles sont soldées progressivement (sorties étalées), chaque arbitrage
   étant expliqué.
7. Risque (à chaque exécution) : stop des satellites, prise de bénéfices partielle, sortie sur « Alléger » /
   « Éviter », plancher de liquidités selon le palier de l'agent risque.
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
POCHES_MOTIF = {"satellite": "satellite", "tendance": "tendance", "coeur": "cœur"}
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


# ------------------------------------------------------------------ corrélation

def rendements(points: list) -> dict[str, float]:
    c = [(d, v) for d, v in (points or []) if v]
    return {d2: math.log(v2 / v1) for (d1, v1), (d2, v2) in zip(c, c[1:]) if v1 > 0 and v2 > 0}


def correlation(r1: dict, r2: dict, minimum: int = 120) -> float | None:
    """Corrélation des rendements quotidiens sur les dates communes (None si moins de `minimum` dates)."""
    dates = sorted(set(r1) & set(r2))
    if len(dates) < minimum:
        return None
    x, y = [r1[d] for d in dates], [r2[d] for d in dates]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sxy / (sx * sy) if sx and sy else None


# ------------------------------------------------------------------ éligibilité

def objection(ligne: dict | None) -> str | None:
    """Objection du contradicteur sur la ligne (sérieuse ou non) : aucun achat dans ce cas. La revue sans objection
    (« Pas d'objection spécifique. », ajustement « maintenir ») n'en est pas une."""
    o = (ligne or {}).get("objection") or {}
    texte = (o.get("objection") or "").strip()
    if not texte or texte.lower().startswith("pas d'objection"):
        return None
    return texte


def tendance_tient(ligne: dict | None, config: dict) -> tuple[bool, str | None]:
    """La tendance d'une ligne tient-elle encore ? (force relative dans le premier tiers, tendance 12-1 positive et cours
    au-dessus de la moyenne 200 jours). Sans suivi de tendance publié : on ne conclut pas (True)."""
    st = (ligne or {}).get("suivi_tendance")
    if not st:
        return True, None
    seuil = config["tendance"]["sortie_force_relative"]
    fr_ = st.get("force_relative")
    if fr_ is not None and fr_ < seuil:
        return False, f"force relative sortie du premier tiers ({ent(fr_)}e percentile, seuil {ent(seuil)})"
    if not st.get("positive"):
        return False, (f"tendance cassée : 12 mois hors dernier mois {fr(st.get('perf_12_1'), 1, True)} %, cours "
                       f"{'au-dessus' if st.get('au_dessus_mm200') else 'sous'} la moyenne 200 jours")
    return True, None


def zone_de(l: dict, config: dict) -> str:
    """Classe ou zone de diversification : zone géographique pour les actions, classe d'actifs sinon."""
    t = l.get("type")
    if t in ("pays", "entreprises"):
        return config["regions"].get(l.get("pays") or l.get("cle"), "Autres pays")
    if t == "secteurs":
        return config["zones_secteurs"].get(l.get("zone_secteur") or l.get("zone"), "Monde")
    return {"or": "Or", "matieres": "Matières premières", "obligations": "Obligations"}.get(t, t or "?")


def secteur_de(l: dict) -> str | None:
    return l.get("secteur") if l.get("type") in ("secteurs", "entreprises") else None


def exclusion(l: dict, convictions: tuple, surveiller: set, entrees_ko: set, etat: dict, config: dict, maintenant: datetime,
              deux_agents: bool = False) -> str | None:
    """Raison pour laquelle une ligne ne peut pas être achetée (None si elle le peut)."""
    v, conv = l.get("verdict"), l.get("conviction")
    if v not in ("Renforcer", "Renforcer fortement"):
        return f"verdict « {v} »" + (" : pas d'ETF pays « Neutre »" if l.get("type") == "pays" and v == "Neutre" else "")
    if conv not in convictions:
        return f"conviction {conv} (exigée : {' ou '.join(convictions)})"
    if objection(l):
        return f"objection du contradicteur : {objection(l)}"
    if l["id"] in surveiller:
        return "classée « À surveiller » par le chef d'orchestre"
    if l.get("type") == "secteurs" and (l.get("zone_secteur") or l.get("zone")) == "monde":
        return "ETF sectoriel mondial : pas d'ETF monde"
    sups = supports_de(l, config)
    if not sups:
        return "aucun support coté"
    if any(s["symbole"] in config["etf_monde"] for s in sups):
        return "ETF monde exclu"
    cs = config["satellites"]
    if deux_agents and len(agents_favorables(l, cs["note_famille_positive"])) < cs["sources_independantes_min"]:
        return f"signaux favorables de moins de {cs['sources_independantes_min']} agents indépendants (une seule source)"
    if {f.get("agent") for f in (l.get("familles") or {}).values()} & entrees_ko:
        return "données d'un agent utilisé périmées ou dégradées"
    interdit = (etat.get("interdits") or {}).get(sups[0]["symbole"])
    if interdit and interdit["jusqua"] > maintenant.date().isoformat() and sups[0]["symbole"] not in etat["positions"]:
        return f"vendue récemment ({interdit['motif']}) : pas de rachat avant le {interdit['jusqua']}"
    return None


# ------------------------------------------------------------------ cibles

def cibles(chef: dict, palier: str, etat: dict, valo: dict, series: dict, entrees_ko: set, config: dict, maintenant: datetime) -> dict:
    """Poids cibles (en % du portefeuille) par support, une seule fois par jour.
    Renvoie {lignes: {symbole: {...}}, liquidites, liquidites_min, exclusions: {symbole détenu: raison},
    ecartees: [{id, nom, raison}], diversification, avertissements}."""
    cc, cs, co = config["coeur"], config["satellites"], config["obligations"]
    lignes = lignes_chef(chef)
    surveiller = {x["id"] for x in ((chef.get("panorama") or {}).get("a_surveiller") or [])}
    avert, ecartees = [], []
    rend = {s: rendements(p) for s, p in (series or {}).items()}
    retenues: list[tuple[dict, dict, str]] = []  # (ligne, support, poche)

    def trop_correlee(sym):
        pire = None
        for l2, s2, _ in retenues:
            c = correlation(rend.get(sym, {}), rend.get(s2["symbole"], {}), cc["correlation_jours_min"])
            if c is not None and c > cc["correlation_max"] and (pire is None or c > pire[0]):
                pire = (c, l2["nom"])
        return pire

    def compte(cle_fn, valeur):
        return sum(1 for l2, _, _ in retenues if cle_fn(l2) == valeur)

    # 1. Obligations : poids fixé par le verdict
    poids_oblig = {}
    for l in sorted([l for l in lignes.values() if l["type"] == "obligations"], key=lambda l: -(l.get("score") or 0)):
        w = co["poids_par_verdict"].get(l.get("verdict"), 0)
        if l.get("conviction") == "faible":
            w = min(w, co["poids_par_verdict"]["Neutre"])
        if w <= 0:
            continue
        raison = None
        if objection(l):
            raison = f"objection du contradicteur : {objection(l)}"
        elif l["id"] in surveiller:
            raison = "classée « À surveiller » par le chef d'orchestre"
        elif not supports_de(l, config):
            raison = "aucun support coté"
        elif sum(poids_oblig.values()) + w > co["max_total"]:
            raison = f"obligations plafonnées à {co['max_total']} % au total"
        if raison:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": raison})
            continue
        sup = supports_de(l, config)[0]
        poids_oblig[sup["symbole"]] = w
        retenues.append((l, sup, "coeur"))

    # 2. Cœur : opportunités « Renforcer » de conviction moyenne ou forte, diversifiées et peu corrélées
    cands = []
    for l in lignes.values():
        if l["type"] not in cc["types"]:
            continue
        r = exclusion(l, tuple(cc["convictions"]), surveiller, entrees_ko, etat, config, maintenant)
        if r:
            if l.get("verdict") in ("Renforcer", "Renforcer fortement") or l["id"] in surveiller:
                ecartees.append({"id": l["id"], "nom": l["nom"], "raison": r})
            continue
        cands.append(l)
    detenues = {p.get("ligne_id") for p in etat["positions"].values()}
    bonus = cc["bonus_ligne_detenue"]  # préférence aux lignes déjà détenues et toujours éligibles : moins de rotation, moins de frais
    cands.sort(key=lambda l: (-RANG_CONVICTION.get(l.get("conviction"), 0), -((l.get("score") or 0) + (bonus if l["id"] in detenues else 0))))
    for l in cands:
        sup = supports_de(l, config)[0]
        if len(retenues) >= cc["max_lignes"]:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"cœur complet ({cc['max_lignes']} lignes au plus)"})
            continue
        z = zone_de(l, config)
        if compte(lambda x: zone_de(x, config), z) >= cc["max_par_zone"]:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"déjà {cc['max_par_zone']} lignes en « {z} » (diversification)"})
            continue
        sec = secteur_de(l)
        if sec and compte(secteur_de, sec) >= cc["max_par_secteur"]:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"déjà {cc['max_par_secteur']} lignes du secteur « {l.get('secteur_nom') or sec} »"})
            continue
        pire = trop_correlee(sup["symbole"])
        if pire:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"corrélation de {fr(pire[0], 2)} avec {pire[1]} sur 1 an (maximum {fr(cc['correlation_max'], 2)})"})
            continue
        retenues.append((l, sup, "coeur"))
    n_coeur = len(retenues)
    if n_coeur < cc["min_lignes"]:
        avert.append(f"Seulement {n_coeur} ligne(s) de cœur respectent les règles (minimum visé : {cc['min_lignes']}) : la part non placée reste en liquidités.")

    # 3. Poche « tendance » : tendances fortes et saines du chef d'orchestre (part des satellites, places réservées)
    ct = config["tendance"]
    tends = []
    pris = {sup["symbole"] for _, sup, _ in retenues}
    detenues_t = {p.get("ligne_id") for p in etat["positions"].values() if p.get("poche") == "tendance"}
    fortes = {x["id"]: x for x in chef.get("tendances_fortes") or []}
    ordre_t = sorted(fortes.values(), key=lambda x: (x["id"] not in detenues_t, not x.get("saine"), -(x.get("force_relative") or 0)))
    for x in ordre_t:
        l = lignes.get(x["id"])
        if l is None:
            continue
        detenue = x["id"] in detenues_t
        sups = supports_de(l, config)
        raison = None
        if l.get("verdict") in SORTIE:
            raison = f"verdict « {l.get('verdict')} »"
        elif not sups:
            raison = "aucun support coté"
        elif sups[0]["symbole"] in pris:
            raison = "support déjà retenu dans une autre poche"
        elif not detenue and not x.get("saine"):
            raison = "tendance forte mais en excès : " + " ; ".join(e.split(" : ")[0] for e in x.get("exces") or [])
        elif not detenue:
            raison = exclusion(dict(l, verdict="Renforcer", conviction="forte"), ("forte",), surveiller, entrees_ko, etat, config, maintenant)
        if raison is None and len(tends) >= ct["max_lignes"]:
            raison = f"poche « tendance » complète ({ct['max_lignes']} lignes au plus)"
        elif raison is None and len(retenues) >= config["max_lignes"]:
            raison = f"{config['max_lignes']} lignes au plus au total"
        if raison is None and not detenue:
            pire = trop_correlee(sups[0]["symbole"])
            if pire:
                raison = f"corrélation de {fr(pire[0], 2)} avec {pire[1]} sur 1 an"
        if raison:
            ecartees.append({"id": l["id"], "nom": f"{l['nom']} (tendance)", "raison": raison})
            continue
        retenues.append((l, sups[0], "tendance"))
        tends.append((l, sups[0]))
        pris.add(sups[0]["symbole"])

    # 4. Satellites : convictions fortes
    sats = []
    places = min(cs["max_lignes"], config["max_lignes"] - n_coeur - len(tends))
    for l in sorted(lignes.values(), key=lambda l: -((l.get("score") or 0) + (bonus if l["id"] in detenues else 0))):
        if l["type"] not in cs["types"]:
            continue
        r = exclusion(l, tuple(cs["convictions"]), surveiller, entrees_ko, etat, config, maintenant, deux_agents=True)
        if r:
            if l.get("conviction") == "forte" and l.get("verdict") in ("Renforcer", "Renforcer fortement"):
                ecartees.append({"id": l["id"], "nom": l["nom"], "raison": r})
            continue
        sup = supports_de(l, config)[0]
        z = zone_de(l, config)
        if len(sats) < places and compte(lambda x: zone_de(x, config), z) >= cs["max_par_zone_total"]:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"déjà {cs['max_par_zone_total']} lignes en « {z} » (cœur et satellites ; diversification)"})
            continue
        if len(sats) >= places:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"{config['max_lignes']} lignes au plus au total"})
            continue
        sec = secteur_de(l)
        if sec and compte(secteur_de, sec) >= cc["max_par_secteur"]:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"déjà {cc['max_par_secteur']} lignes du secteur « {l.get('secteur_nom') or sec} »"})
            continue
        pire = trop_correlee(sup["symbole"])
        if pire:
            ecartees.append({"id": l["id"], "nom": l["nom"], "raison": f"corrélation de {fr(pire[0], 2)} avec {pire[1]} sur 1 an"})
            continue
        retenues.append((l, sup, "satellite"))
        sats.append((l, sup))

    # 5. Poids
    mini_liq = palier_min(palier, config)
    lmin = config["ligne_min"]
    vols = {s: volatilite(p, cs["volatilite_jours"]) for s, p in (series or {}).items()}
    poids_sat = {}
    budget_t = cs["budget"] * ct["part_satellites"]
    budget_sat = cs["budget"] - budget_t
    if sats:
        brut = {sup["symbole"]: cs["convictions"][l["conviction"]] / max(vols.get(sup["symbole"]) or cs["volatilite_defaut"], cs["volatilite_plancher"])
                for l, sup in sats}
        budget = min(budget_sat, cs["max_ligne"] * len(sats))
        poids_sat = {k: min(cs["max_ligne"], max(lmin, budget * v / sum(brut.values()))) for k, v in brut.items()}
    for l, sup in tends:  # parts égales ; une ligne gagnante n'est jamais réduite (voir generer_ordres)
        poids_sat[sup["symbole"]] = min(ct["max_ligne"], max(lmin, budget_t / len(tends)))
    res = {}
    for l, sup, poche in retenues:
        if poche in ("satellite", "tendance"):
            w = poids_sat[sup["symbole"]]
        elif sup["symbole"] in poids_oblig:
            w = poids_oblig[sup["symbole"]]
        else:
            w = None
        res[sup["symbole"]] = {"cible": w, "poche": poche, "classe": CLASSE_DE[l["type"]], "support": sup, "ligne": l, "zone": zone_de(l, config),
                               "volatilite": vols.get(sup["symbole"])}
    libres = [k for k, e in res.items() if e["cible"] is None]
    budget = 100 - mini_liq - sum(e["cible"] for e in res.values() if e["cible"] is not None)
    while libres:
        fac = {k: cc["convictions"].get(res[k]["ligne"].get("conviction"), 1.0) for k in libres}
        tot = sum(fac.values())
        poids = {k: min(cc["max_ligne"], budget * f / tot) for k, f in fac.items()}
        # plafond par zone pour le cœur (excédent laissé en liquidités)
        for z in {res[k]["zone"] for k in libres}:
            membres = [k for k in libres if res[k]["zone"] == z]
            deja = sum(e["cible"] for k, e in res.items() if e["zone"] == z and k not in libres and e["poche"] == "coeur")
            s = sum(poids[k] for k in membres)
            if s + deja > cc["max_zone_pct"]:
                f = max(0.0, cc["max_zone_pct"] - deja) / s
                for k in membres:
                    poids[k] *= f
        trop_petites = [k for k in libres if poids[k] < lmin]
        if not trop_petites:
            for k in libres:
                res[k]["cible"] = poids[k]
            break
        k = min(trop_petites, key=lambda k: (k in etat["positions"], RANG_CONVICTION.get(res[k]["ligne"].get("conviction"), 0),
                                             res[k]["ligne"].get("score") or 0))
        ecartees.append({"id": res[k]["ligne"]["id"], "nom": res[k]["ligne"]["nom"], "raison": f"poids inférieur à {fr(lmin, 0)} % après les plafonds"})
        del res[k]
        libres.remove(k)
    total = sum(e["cible"] for e in res.values())
    if total > 100 - mini_liq:  # satellites et obligations au plancher : réduction proportionnelle
        k = (100 - mini_liq) / total
        for e in res.values():
            e["cible"] *= k
    cash = 100 - sum(e["cible"] for e in res.values())

    # 6. Diversification
    zones = sorted({e["zone"] for e in res.values()})
    corrs = []
    syms = sorted(res)
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            c = correlation(rend.get(a, {}), rend.get(b, {}), cc["correlation_jours_min"])
            if c is not None:
                corrs.append((c, a, b))
    if len(zones) < cc["zones_min"]:
        avert.append(f"Diversification : {len(zones)} classe(s) ou zone(s) seulement ({', '.join(zones)}), pour {cc['zones_min']} visées ; "
                     "aucune autre opportunité ne respecte les règles.")
    diversification = {"zones": zones, "nombre_zones": len(zones),
                       "correlation_moyenne": round(sum(c for c, _, _ in corrs) / len(corrs), 2) if corrs else None,
                       "correlation_max": ({"valeur": round(max(corrs)[0], 2), "entre": [max(corrs)[1], max(corrs)[2]]} if corrs else None),
                       "paires_mesurees": len(corrs), "paires_possibles": len(syms) * (len(syms) - 1) // 2}

    # 7. Lignes détenues hors cibles : raison
    exclusions = {}
    for s, p in etat["positions"].items():
        if s in res:
            continue
        l = lignes.get(p.get("ligne_id"))
        if l is None:
            exclusions[s] = (True, "ligne plus analysée par le chef d'orchestre")
            continue
        if l["type"] == "obligations":
            w = co["poids_par_verdict"].get(l.get("verdict"), 0)
            exclusions[s] = (True, f"obligations : verdict « {l.get('verdict')} », conviction {l.get('conviction')} → poids "
                                   + (f"neutre de {fr(w, 0)} % porté par un seul support" if w else "nul"))
            continue
        if p.get("poche") == "tendance":
            tient, pourquoi = tendance_tient(l, config)
            e = next((x for x in ecartees if x["id"] == l["id"]), None)
            exclusions[s] = (True, f"poche « tendance » : {pourquoi or (e['raison'] if e else 'plus parmi les tendances fortes du chef d’orchestre')}")
            continue
        sat = p.get("poche") == "satellite" and l["type"] == "entreprises"
        conv = cs["convictions"] if sat else cc["convictions"]
        r = exclusion(l, tuple(conv), surveiller, entrees_ko, {**etat, "interdits": {}}, config, maintenant, deux_agents=sat)
        if r:
            exclusions[s] = (True, r)
        else:
            e = next((x for x in ecartees if x["id"] == l["id"]), None)
            exclusions[s] = (False, f"non retenue : {e['raison']}" if e else "non retenue : concentration sur les meilleures opportunités")
    return {"lignes": res, "liquidites": cash, "liquidites_min": mini_liq, "exclusions": exclusions, "ecartees": ecartees,
            "diversification": diversification, "avertissements": avert}


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

def jours_detenus(p: dict, maintenant: datetime) -> int:
    t = lire_iso(p.get("dernier_achat_le") or p.get("ouverte_le"))
    return (maintenant.date() - t.date()).days if t else 999


def date_liberation(p: dict, config: dict) -> str:
    t = lire_iso(p.get("dernier_achat_le") or p.get("ouverte_le"))
    return (t + timedelta(days=config["detention_min_jours"])).date().isoformat() if t else "?"


def rotation_utilisee(operations: list[dict], maintenant: datetime, jours: int) -> float:
    debut = maintenant - timedelta(days=jours)
    return sum(o.get("montant_eur", 0) for o in operations if o["sens"] == "vente" and o.get("motif") == "rééquilibrage"
               and (lire_iso(o["date"]) or maintenant) >= debut)


def generer_ordres(c: dict, etat: dict, valo: dict, operations: list[dict], palier: str, config: dict, maintenant: datetime) -> tuple[list[dict], list[str], list[dict]]:
    """Ordres de la décision du jour (ventes puis achats). Renvoie (ordres, notes, arbitrages expliqués)."""
    cr = config["reequilibrage"]
    val = valo["valeur"]
    dmin = config["detention_min_jours"]
    notes, arbitrages = [], []
    cur = {s: p.get("poids", 0) for s, p in etat["positions"].items()}
    en_attente = {o["symbole"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "vente"}
    ventes, achats = [], []

    def arbitrage(s, nom, action, raison):
        arbitrages.append({"symbole": s, "nom": nom, "action": action, "raison": raison})

    # 1. Lignes hors cibles : soldées progressivement (règles enfreintes d'abord, puis les plus petites)
    hors = [(s, p) for s, p in etat["positions"].items() if s not in c["lignes"] and s not in en_attente]
    hors.sort(key=lambda sp: (not c["exclusions"].get(sp[0], (False, ""))[0], cur.get(sp[0], 0)))
    sorties = 0
    for s, p in hors:
        dure, raison = c["exclusions"].get(s, (False, "non retenue"))
        if jours_detenus(p, maintenant) < dmin:
            arbitrage(s, p["nom"], "conservée pour l'instant",
                      f"{raison}. Détention minimale de {dmin} jours : sortie possible à partir du {date_liberation(p, config)}.")
            continue
        if sorties >= config["transition"]["sorties_max_par_jour"]:
            arbitrage(s, p["nom"], "sortie reportée",
                      f"{raison}. Sorties étalées : {config['transition']['sorties_max_par_jour']} au plus par jour ; sortie lors d'une prochaine décision.")
            continue
        texte = f"Mise en conformité : {p['nom']} ({fr(cur.get(s, 0), 1)} % du portefeuille) est soldée. Motif : {raison}."
        ventes.append(_ordre_vente(etat, p, p["quantite"], "mise en conformité", texte, False, None, 0, cur.get(s, 0), palier, config, maintenant))
        arbitrage(s, p["nom"], "vente totale", raison + ("" if dure else " (règle de concentration : 15 lignes au plus, 4 % minimum)"))
        sorties += 1

    # 2. Lignes cibles déjà détenues : rééquilibrage au-delà du seuil
    for s, e in c["lignes"].items():
        p = etat["positions"].get(s)
        if p is None or s in en_attente:
            continue
        t, w = e["cible"], cur.get(s, 0)
        diff = t - w
        sous_minimum = w < config["ligne_min"] <= t
        if abs(diff) < cr["seuil_points"] and not sous_minimum:
            continue
        montant = abs(diff) * val / 100
        if montant < cr["ordre_min_eur"]:
            continue
        interdit = (etat.get("interdits") or {}).get(s)
        if diff > 0 and interdit and interdit["jusqua"] > maintenant.date().isoformat():
            arbitrage(s, p["nom"], "renforcement reporté", f"poids {fr(w, 1)} % pour une cible de {fr(t, 1)} % ; vente partielle récente "
                      f"({interdit['motif']}) : pas de rachat avant le {interdit['jusqua']}.")
        elif diff > 0:
            achats.append(_ordre_achat(etat, e, montant, t, w, palier, config, maintenant, "renforcement"))
            arbitrage(s, p["nom"], "renforcement", f"poids {fr(w, 1)} % pour une cible de {fr(t, 1)} %"
                      + (f" (minimum {fr(config['ligne_min'], 0)} % par ligne)" if sous_minimum else ""))
        elif e["poche"] == "tendance":
            arbitrage(s, p["nom"], "conservée", f"poche « tendance » : poids {fr(w, 1)} % pour une cible de {fr(t, 1)} % ; on laisse courir "
                      "les gagnants tant que la tendance tient (ni réduction ni prise de bénéfices).")
        elif jours_detenus(p, maintenant) < dmin:
            arbitrage(s, p["nom"], "réduction reportée", f"poids {fr(w, 1)} % pour une cible de {fr(t, 1)} % ; détention minimale de {dmin} jours "
                      f"(réduction possible à partir du {date_liberation(p, config)}).")
        else:
            q = math.floor(montant / (p.get("dernier_cours_eur") or p["prix_revient_eur"]))
            if q > 0:
                texte = f"Rééquilibrage : poids {fr(w, 1)} % pour une cible de {fr(t, 1)} % (écart {fr(diff, 1, True)} pt)."
                ventes.append(_ordre_vente(etat, p, min(q, p["quantite"]), "rééquilibrage", texte, False, e.get("ligne"), t, w, palier, config, maintenant))
                arbitrage(s, p["nom"], "réduction", f"poids {fr(w, 1)} % pour une cible de {fr(t, 1)} %")

    # 3. Rotation mensuelle : rééquilibrages plafonnés (les mises en conformité sont étalées par jour)
    rc = config["rotation"]
    budget = rc["max_mensuelle_pct"] / 100 * val - rotation_utilisee(operations, maintenant, rc["jours"])
    gardees = []
    for o in ventes:
        if o["motif"] == "rééquilibrage":
            if o["_montant"] > budget:
                notes.append(f"Réduction de {o['nom']} reportée : rotation mensuelle maximale ({rc['max_mensuelle_pct']} % sur {rc['jours']} jours) atteinte.")
                continue
            budget -= o["_montant"]
        gardees.append(o)
    ventes = gardees

    # 4. Entrées : jamais au-delà de 15 lignes (les lignes hors règles encore détenues comptent)
    nb_apres = len(etat["positions"]) - sum(1 for o in ventes if o["motif"] == "mise en conformité")
    places = config["max_lignes"] - nb_apres
    mini = c["liquidites_min"]
    dispo = valo["liquidites"] + sum(o["_montant"] for o in ventes) * 0.995 - mini / 100 * val \
        - sum(o["montant_eur"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "achat")
    besoin = sum(o["montant_eur"] for o in achats)  # renforcements de lignes déjà détenues, financés en premier
    if besoin > max(0.0, dispo):
        k = max(0.0, dispo) / besoin
        notes.append(f"Renforcements réduits à {fr(k * 100, 0)} % : liquidités disponibles au-dessus du plancher de {fr(mini, 0)} % insuffisantes.")
        for o in achats:
            o["montant_eur"] = round(o["montant_eur"] * k, 2)
        achats = [o for o in achats if o["montant_eur"] >= cr["ordre_min_eur"]]
    dispo -= sum(o["montant_eur"] for o in achats)
    for s, e in sorted(c["lignes"].items(), key=lambda kv: -kv[1]["cible"]):
        if s in etat["positions"]:
            continue
        nom = e["support"].get("nom") or e["ligne"].get("nom")
        montant = e["cible"] * val / 100
        if places <= 0:
            arbitrage(s, nom, "entrée reportée", f"cible {fr(e['cible'], 1)} % ; {config['max_lignes']} lignes au plus : entrée quand les lignes hors règles auront été soldées.")
            continue
        if montant > dispo:
            if dispo >= config["ligne_min"] / 100 * val:
                montant = dispo
            else:
                arbitrage(s, nom, "entrée reportée", f"cible {fr(e['cible'], 1)} % ; liquidités disponibles au-dessus du plancher de {fr(mini, 0)} % insuffisantes.")
                continue
        achats.append(_ordre_achat(etat, e, montant, e["cible"], 0.0, palier, config, maintenant, "entrée"))
        arbitrage(s, nom, "entrée", f"{e['poche'].replace('coeur', 'cœur')} : cible {fr(e['cible'], 1)} % ({e['zone']})")
        dispo -= montant
        places -= 1
    for o in ventes:
        o.pop("_montant", None)
    return ventes + achats, notes, arbitrages


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
    elif poche == "tendance":
        st = l.get("suivi_tendance") or {}
        ct = config["tendance"]
        texte = (f"{'Entrée' if nature == 'entrée' else 'Renforcement'} poche « tendance » : {sup.get('nom') or l.get('nom')} ({sup['symbole']}). "
                 f"Tendance forte et saine selon le chef d'orchestre : {st.get('texte') or 'premier tiers de force relative'}. "
                 f"Taille {fr(cible, 1)} % (parts égales de la poche). Stop suiveur à −{ct['stop_suiveur_pct']} % du plus haut depuis l'achat ; "
                 f"sortie si la force relative quitte le premier tiers ou si la tendance casse ; pas de prise de bénéfices tant que la tendance tient.")
        extra = [f"Les tendances se retournent parfois brutalement : le stop à −{ct['stop_suiveur_pct']} % du plus haut limite la perte, sans l'empêcher.",
                 "Sur 2010-2026, cette poche a fait moins bien que l'indice mondial (backtest) : elle reste une petite part des satellites."]
    else:
        if l.get("type") == "obligations":
            pourquoi = (f"poids fixé par le verdict du chef d'orchestre (« {l.get('verdict')} », conviction {l.get('conviction')}) : "
                        f"{fr(cible, 1)} %, pour la diversification et la faible corrélation aux actions.")
        else:
            pourquoi = (f"opportunité « {l.get('verdict')} » de conviction {l.get('conviction')}, score {ent(l.get('score'))}/100, "
                        f"zone « {e.get('zone')} » ; signaux favorables de {len(r['agents'])} agents ({', '.join(r['agents'])}).")
        texte = (f"{'Entrée' if nature == 'entrée' else 'Renforcement'} cœur : {sup['nom']} ({l.get('nom')}). Cible {fr(cible, 1)} % "
                 f"(poids actuel {fr(actuel, 1)} %) : {pourquoi}")
        extra = []
    if sup.get("contango"):
        texte += " Support adossé à des contrats à terme : coût de renouvellement (contango) à prévoir."
        extra.append(config["contango"])
    if sup.get("devise") not in (None, "EUR") or l.get("devise") not in (None, "EUR"):
        extra.append("Le change joue : une hausse de l'euro réduit la valeur en euros de ce support.")
    devise = P.devise_de(sup["symbole"], sup.get("devise") or l.get("devise"), config, etat.get("devises", {}))
    return P.nouvel_ordre(etat, maintenant, config, sens="achat", symbole=sup["symbole"], nom=sup.get("nom") or l.get("nom"), ligne_id=l.get("id"),
                          poche=poche, classe=e["classe"], type=l.get("type"), pays=sup.get("pays") or l.get("pays"), secteur=l.get("secteur_nom") or l.get("secteur"),
                          themes=l.get("themes") or [], devise=devise, montant_eur=round(montant, 2), motif=f"{nature} {POCHES_MOTIF.get(poche, 'cœur')}",
                          imposee=False, contango=bool(sup.get("contango")), familles=familles_resume(l),
                          raison={**r, "motif": f"{nature} {POCHES_MOTIF.get(poche, 'cœur')}", "texte": texte, "cible_pct": round(cible, 2),
                                  "poids_actuel_pct": round(actuel, 2), "palier": palier},
                          donner_tort=texte_donner_tort(l, extra))


def _ordre_vente(etat, p, quantite, motif, texte, imposee, ligne, cible, actuel, palier, config, maintenant) -> dict:
    r = raison_ligne(ligne, config) if ligne else {"verdict": p.get("verdict"), "conviction": p.get("conviction")}
    extra = {
        "sortie sur verdict": ["Le verdict peut remonter si les signaux défavorables se retournent ; la vente fige le résultat actuel."],
        "sortie sur objection": ["L'objection peut se révéler infondée : les autres signaux restaient favorables."],
        "stop": ["Le cours peut rebondir juste après le stop : la baisse peut n'être qu'un repli passager."],
        "prise de bénéfices": ["La tendance peut se prolonger : la partie vendue ne profitera pas d'une hausse supplémentaire."],
        "sortie de tendance": ["Le rang peut remonter vite : une sortie suivie d'un retour en tête coûterait des frais."],
        "plancher de liquidités": ["Si le stress du marché retombe vite, les liquidités supplémentaires coûteront du rendement."],
        "mise en conformité": ["La ligne peut progresser après sa vente : la règle de concentration privilégie la lisibilité et les meilleures convictions."],
    }.get(motif, ["La ligne pourrait revenir dans l'allocation : vente et rachat coûteraient des frais."])
    montant = quantite * (p.get("dernier_cours_eur") or p["prix_revient_eur"])
    o = P.nouvel_ordre(etat, maintenant, config, sens="vente", symbole=p["symbole"], nom=p["nom"], ligne_id=p.get("ligne_id"), poche=p.get("poche"),
                       classe=p.get("classe"), type=p.get("type"), devise=p["devise"], quantite=int(quantite), motif=motif, imposee=imposee,
                       raison={**r, "motif": motif, "texte": texte, "cible_pct": round(cible, 2), "poids_actuel_pct": round(actuel, 2), "palier": palier},
                       donner_tort=texte_donner_tort(ligne, extra))
    o["_montant"] = montant
    return o


# ------------------------------------------------------------------ contrôles de risque (à chaque exécution)

def _risques_tendance(etat: dict, p: dict, ligne: dict | None, chef_a_jour: bool, libre: bool, cours: float | None, palier, config: dict,
                      maintenant: datetime) -> dict | None:
    """Poche « tendance » : stop suiveur sous le plus haut depuis l'achat (quotidien), sortie quand la tendance ne tient
    plus (force relative hors du premier tiers, tendance cassée). Jamais de prise de bénéfices."""
    ct = config["tendance"]
    if cours:
        haut = max(p.get("plus_haut_local") or cours, cours)
        p["plus_haut_local"] = haut
        stop = haut * (1 - ct["stop_suiveur_pct"] / 100)
        if stop > (p.get("stop_local") or 0):
            p["stop_local"], p["stop_type"] = stop, "suiveur"
        if cours <= p["stop_local"]:
            if p.get("dernier_releve_stop") != p.get("dernier_cours_le"):
                p["confirmations_stop"] = p.get("confirmations_stop", 0) + 1
                p["dernier_releve_stop"] = p.get("dernier_cours_le")
            if p["confirmations_stop"] >= ct["confirmations"]:
                perf = (cours / p["prix_revient_local"] - 1) * 100
                texte = (f"Stop suiveur de la poche « tendance » atteint sur {p['nom']} : cours {fr(cours, 2)} {p['devise']} sous le stop "
                         f"{fr(p['stop_local'], 2)} (−{ct['stop_suiveur_pct']} % du plus haut {fr(haut, 2)} ; {fr(perf, 1, True)} % depuis le prix de revient).")
                return _ordre_vente(etat, p, p["quantite"], "stop", texte, True, ligne, 0, p.get("poids", 0), palier, config, maintenant)
        else:
            p["confirmations_stop"], p["dernier_releve_stop"] = 0, None
    if chef_a_jour and ligne is not None and libre:
        tient, pourquoi = tendance_tient(ligne, config)
        if not tient:
            texte = f"Sortie de la poche « tendance » : {ligne['nom']}, {pourquoi}. Les gagnants ne sont gardés que tant que la tendance tient."
            return _ordre_vente(etat, p, p["quantite"], "sortie de tendance", texte, True, ligne, 0, p.get("poids", 0), palier, config, maintenant)
    return None


def controler_risques(etat: dict, lignes: dict | None, palier: str | None, valo: dict, config: dict, maintenant: datetime) -> list[dict]:
    """Stops, prise de bénéfices, sorties sur verdict ou objection (si le chef d'orchestre est à jour), plancher de
    liquidités (si l'agent risque est à jour). Renvoie les nouveaux ordres (imposés)."""
    sp = config["stops"]
    ordres = []
    deja = {o["symbole"] for o in etat.get("ordres", []) if o.get("statut") == "en attente" and o["sens"] == "vente"}
    dmin = config["detention_min_jours"]
    for s, p in list(etat["positions"].items()):
        if s in deja:
            continue
        cours = p.get("dernier_cours_local")
        ligne = (lignes or {}).get(p.get("ligne_id")) if lignes is not None else None
        libre = jours_detenus(p, maintenant) >= dmin  # détention minimale : seul le stop peut l'écourter
        if lignes is not None and ligne is not None and libre:
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
        if p.get("poche") == "tendance":
            o = _risques_tendance(etat, p, ligne, lignes is not None, libre, cours, palier, config, maintenant)
            if o:
                ordres.append(o)
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
        if libre and not p.get("prise_benefices_faite") and cours >= revient * (1 + sp["prise_benefices_pct"] / 100):
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
            pos = [p for s, p in etat["positions"].items() if s not in vendus and p.get("valeur_eur") and jours_detenus(p, maintenant) >= dmin]
            total = sum(p["valeur_eur"] for p in pos) or 1
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
