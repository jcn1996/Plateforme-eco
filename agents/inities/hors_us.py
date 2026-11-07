"""
Positions hors États-Unis des super-investisseurs (visibles uniquement au-dessus des seuils légaux).

Recherche par nom d'entité (config/super_investisseurs.json, « entites » : Pabrai Investment Funds, Dalal Street,
Pabrai Wagons Fund, Dhandho India Zero Fee Fund…), comparé au seul nom du déclarant ou de l'actionnaire :
- Inde (NSE) :
  · déclarations SAST (acquisition ou cession franchissant 5 %, puis variations de 2 %), toutes sociétés, nom de
    l'acquéreur : rattrapage de l'historique depuis nse.rattrapage_depuis, puis les jours récents ;
  · répartition trimestrielle de l'actionnariat (XBRL, actionnaires de plus de 1 %) des sociétés repérées par les
    déclarations SAST, de celles listées dans la config (« inde_nse ») et des sociétés indiennes de l'agent
    entreprises ; une société n'est relue qu'une fois par semaine, le XBRL seulement s'il est nouveau ;
- Corée (DART) et Japon (EDINET) : toutes les déclarations de participation, rattrapage progressif de
  l'historique ; « clé non configurée » sans DART_API_KEY / EDINET_API_KEY ;
- Turquie (KAP, source secondaire : son échec ne dégrade pas l'agent) : notifications « Pay Alım Satım Bildirimi »
  transmises par le dépositaire central (classe DKB), pièce jointe PDF lue ; rattrapage progressif ;
- France (AMF) : franchissements de seuil récents.

Chaque exécution journalise ce qui a été cherché (sources, périodes, documents examinés, noms cherchés) et trouvé
(« recherche_hors_us » de data/inities.json et du journal de l'agent).
"""
from __future__ import annotations

from datetime import date, timedelta

from ..commun.journal import journal
from . import analyse as A

LOG = journal("agent-inities")


class Recherche:
    """Journal de la recherche hors États-Unis : pour chaque source, périodes couvertes, documents examinés, trouvés."""

    def __init__(self, alias: dict[str, list[str]]):
        self.alias = alias
        self.sources: dict[str, dict] = {}

    def source(self, cle: str, nom: str) -> dict:
        return self.sources.setdefault(cle, {"source": nom, "etat": "ok", "periodes": [], "documents_examines": 0, "trouves": [], "detail": None})

    def periode(self, cle: str, debut, fin, n: int = 0):
        s = self.sources[cle]
        s["periodes"].append([str(debut), str(fin)])
        s["documents_examines"] += n

    def trouve(self, cle: str, e: dict):
        self.sources[cle]["trouves"].append(f"{e['nom']} : {e.get('societe') or '?'}" + (f" {A.fr(e['pct'], 2)} %" if e.get("pct") is not None else "")
                                            + f" ({e.get('entite')}, {A.date_fr(e.get('date'))})")

    def resume(self) -> dict:
        res = {}
        for cle, s in self.sources.items():
            p = s["periodes"]
            res[cle] = {**s, "periodes": [min(x[0] for x in p), max(x[1] for x in p)] if p else None, "nb_periodes": len(p)}
        return {"noms_cherches": self.alias, "sources": res}


def fenetres(debut: date, fin: date, pas: int) -> list[tuple[date, date]]:
    """Périodes de `pas` jours, de la plus récente à la plus ancienne, couvrant [debut, fin]."""
    res = []
    while fin >= debut:
        d = max(debut, fin - timedelta(days=pas - 1))
        res.append((d, fin))
        fin = d - timedelta(days=1)
    return res


def a_couvrir(etat: dict, cle: str, aujourdhui: date, recent: int, profondeur_jours: int | None, depuis: str | None, pas: int) -> list[tuple]:
    """Périodes à examiner : les `recent` derniers jours, puis l'historique non encore couvert (curseur de
    rattrapage dans etat["curseurs_hors_us"], qui recule à chaque période examinée en entier)."""
    limite = date.fromisoformat(depuis) if depuis else aujourdhui - timedelta(days=profondeur_jours or 0)
    res = [("recent", d, f) for d, f in fenetres(aujourdhui - timedelta(days=recent), aujourdhui, pas)]
    curseur = (etat.get("curseurs_hors_us") or {}).get(cle)
    fin = date.fromisoformat(curseur) - timedelta(days=1) if curseur else aujourdhui - timedelta(days=recent + 1)
    res += [("rattrapage", d, f) for d, f in fenetres(limite, fin, pas)]
    return res


def avancer(etat: dict, cle: str, debut: date):
    etat.setdefault("curseurs_hors_us", {})[cle] = debut.isoformat()


def collecter(f, col, etat: dict, si: list[dict], cfg: dict, aujourdhui: date, ctx: dict) -> dict:
    """Collecte des déclarations hors États-Unis. Ajoute les nouvelles dans etat["hors_us"] ; renvoie le journal de la recherche."""
    ch = cfg["hors_us"]
    alias = {inv["cle"]: inv.get("entites") or [inv["societe"]] for inv in si}
    noms = {inv["cle"]: inv["nom"] for inv in si}
    rech = Recherche(alias)
    liste = etat.setdefault("hors_us", [])
    vus = {x["id"] for x in liste}

    def ajouter(cle_source, cle_inv, pays, source, x, pct=None, **k):
        ident = f"{source}|{x.get('id')}|{cle_inv}"
        if ident in vus:
            return
        vus.add(ident)
        e = {"id": ident, "investisseur": cle_inv, "nom": noms[cle_inv], "pays": pays, "societe": x.get("societe"), "ticker": x.get("ticker"),
             "pct": pct, "date": x.get("date"), "titre": x.get("titre"), "source": source, "url": x.get("url"), "entite": x.get("entite"), **k}
        liste.append(e)
        rech.trouve(cle_source, e)
        LOG.info("Hors États-Unis : %s — %s, %s %s (%s)", source, noms[cle_inv], e["societe"], f"{pct} %" if pct is not None else "", x.get("entite"))

    def qui(nom):
        for cle_inv, al in alias.items():
            a = A.nom_correspond(nom, al)
            if a:
                return cle_inv, a
        return None, None

    inde(f, col, etat, cfg, si, aujourdhui, ctx, rech, qui, ajouter)
    coree(f, col, etat, ch, aujourdhui, rech, qui, ajouter)
    japon(f, col, etat, ch, aujourdhui, rech, qui, ajouter)
    turquie(f, col, etat, ch, aujourdhui, rech, alias, ajouter)
    france(f, col, etat, cfg, aujourdhui, rech, alias, ajouter)

    limite = (aujourdhui - timedelta(days=ch["conservation_jours"])).isoformat()
    etat["hors_us"] = sorted((x for x in liste if (x.get("date") or "") >= limite), key=lambda x: x.get("date") or "", reverse=True)
    for cle, s in rech.sources.items():
        s["etat"] = col.etats.get(cle, s["etat"])
        LOG.info("Recherche hors États-Unis — %s : %s ; %d document(s) examiné(s) ; trouvé : %s", s["source"], s["etat"],
                 s["documents_examines"], "; ".join(s["trouves"]) or "rien")
    return rech.resume()


# ------------------------------------------------------------------ Inde (NSE)

def _date_nse(t: str | None) -> str | None:
    """« 26-Jun-2023 17:16 » ou « 30-SEP-2026 » → AAAA-MM-JJ."""
    from datetime import datetime
    try:
        return datetime.strptime((t or "").strip()[:11].title(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def inde(f, col, etat, cfg, si, aujourdhui, ctx, rech, qui, ajouter):
    cn = cfg["hors_us"]["nse"]
    rech.source("nse_sast", "NSE, déclarations SAST (franchissements de 5 %, nom de l'acquéreur)")
    suivies = etat.setdefault("nse_suivies", {})
    budget = cn["requetes_sast_max_par_execution"]
    for genre, debut, fin in a_couvrir(etat, "nse_sast", aujourdhui, cn["recent_jours"], None, cn["rattrapage_depuis"], cn["fenetre_jours"]):
        if budget <= 0:
            break
        budget -= 1
        r = col.appel("nse_sast", lambda d=debut, fi=fin: f.nse_sast(d.isoformat(), fi.isoformat()))
        if r is None:
            break  # source en panne : le rattrapage reprendra à la prochaine exécution
        rech.periode("nse_sast", debut, fin, len(r))
        for x in r:
            cle_inv, entite = qui(x.get("acquereur"))
            if not cle_inv:
                continue
            sym = x.get("symbole")
            if sym:
                suivies[sym] = cle_inv
            cession = (x.get("sens") or "").lower().startswith("sale")
            ajouter("nse_sast", cle_inv, "IN", "NSE (SAST)", {
                "id": x.get("id") or f"{sym}-{x.get('date')}", "societe": x.get("societe"), "ticker": f"{sym}.NS" if sym else None,
                "date": _date_nse(x.get("date")), "url": x.get("url"), "entite": x.get("acquereur"),
                "titre": f"{'Cession' if cession else 'Acquisition'} déclarée (SAST) : {A.fr(A._nombre(x.get('pct_apres')), 2)} % du capital après l'opération"},
                A._nombre(x.get("pct_apres")), seuil=5.0, type="cession" if cession else "acquisition")
        if genre == "rattrapage":
            avancer(etat, "nse_sast", debut)

    # Répartition trimestrielle de l'actionnariat : actionnaires de plus de 1 %
    rech.source("nse_actionnariat", "NSE, répartition trimestrielle de l'actionnariat (actionnaires de plus de 1 %)")
    symboles = dict(suivies)
    for inv in si:  # sociétés listées dans config/super_investisseurs.json (« hors_us » → « inde_nse »)
        for s_ in (inv.get("hors_us") or {}).get("inde_nse", []):
            symboles.setdefault(s_, inv["cle"])
    if cn.get("inclure_univers"):
        for t, e in ctx["par_ticker"].items():
            if e.get("pays") == "IN" and t.endswith(".NS"):
                symboles.setdefault(t[:-3], None)
    verifie = etat.setdefault("nse_verifie", {})
    lus = etat.setdefault("nse_lus", {})
    a_lire = sorted(symboles, key=lambda s_: (symboles[s_] is None, verifie.get(s_, "")))
    budget, examines, echecs = cn["actionnariat_max_par_execution"], 0, 0
    for sym in a_lire:
        if budget <= 0:
            break
        if (verifie.get(sym) and (aujourdhui - date.fromisoformat(verifie[sym])).days < cn["actionnariat_intervalle_jours"]):
            continue
        budget -= 1
        try:
            depots = f.nse_actionnariat(sym)
        except Exception as e:  # noqa: BLE001
            echecs += 1
            if echecs <= 2:
                LOG.warning("NSE, actionnariat de %s : %s", sym, str(e)[:120])
            continue
        verifie[sym] = aujourdhui.isoformat()
        if not depots or not depots[0].get("xbrl"):
            continue
        dernier = depots[0]
        if lus.get(sym) == dernier["id"]:
            continue
        budget -= 1
        try:
            shp = A.lire_actionnariat_xbrl(f.nse_xbrl(dernier["xbrl"]))
        except Exception as e:  # noqa: BLE001
            echecs += 1
            LOG.warning("NSE, XBRL de %s : %s", sym, str(e)[:120])
            continue
        lus[sym] = dernier["id"]
        examines += 1
        trouves = set()
        for a in shp["actionnaires"]:
            cle_inv, entite = qui(a["nom"])
            if not cle_inv:
                continue
            trouves.add(cle_inv)
            ajouter("nse_actionnariat", cle_inv, "IN", "NSE (actionnariat)", {
                "id": f"{sym}-{shp['date']}-{a['nom']}", "societe": dernier.get("societe") or sym, "ticker": f"{sym}.NS", "date": shp["date"],
                "url": dernier["xbrl"], "entite": a["nom"], "titre": f"Actionnaire de plus de 1 % au {A.date_fr(shp['date'])} : {a['nom']}"},
                a["pct"], seuil=1.0, type="actionnariat", priorite=1)
        # Investisseur connu sur cette société (répartition précédente ou déclaration SAST plus ancienne) qui ne figure
        # plus parmi les actionnaires de plus de 1 % : passé sous 1 % à la date de cette répartition
        derniers: dict[str, dict] = {}
        for x in sorted((x for x in etat.get("hors_us", []) if x.get("ticker") == f"{sym}.NS"), key=lambda x: x.get("date") or ""):
            derniers[x["investisseur"]] = x
        avant = {c for c, x in derniers.items() if x.get("type") != "sortie" and (x.get("date") or "") < (shp["date"] or "")}
        for cle_inv in avant - trouves:
            ajouter("nse_actionnariat", cle_inv, "IN", "NSE (actionnariat)", {
                "id": f"{sym}-{shp['date']}-absent", "societe": dernier.get("societe") or sym, "ticker": f"{sym}.NS", "date": shp["date"],
                "url": dernier["xbrl"], "entite": None, "titre": f"Absent des actionnaires de plus de 1 % au {A.date_fr(shp['date'])}"},
                None, seuil=1.0, type="sortie", priorite=1)
    rech.periode("nse_actionnariat", min(verifie.values(), default=aujourdhui.isoformat()), aujourdhui.isoformat(), examines)
    rech.sources["nse_actionnariat"]["detail"] = (f"{len(symboles)} société(s) suivie(s) (repérées par SAST : {len(suivies)}) ; "
                                                  f"{examines} nouvelle(s) répartition(s) lue(s)")
    if echecs:
        if examines == 0 and echecs >= min(3, len(a_lire)):
            col.erreur("nse_actionnariat", f"{echecs} société(s) illisible(s)")
        else:
            col.partielle("nse_actionnariat", f"{echecs} société(s) illisible(s), relues à la prochaine exécution")
    else:
        col.etats.setdefault("nse_actionnariat", "ok")


# ------------------------------------------------------------------ Corée (DART) et Japon (EDINET)

def coree(f, col, etat, ch, aujourdhui, rech, qui, ajouter):
    c = ch["dart"]
    rech.source("dart", "DART (Corée), déclarations de participation (règle des 5 %)")
    budget = c["periodes_max_par_execution"]
    for genre, debut, fin in a_couvrir(etat, "dart", aujourdhui, c["recent_jours"], c["rattrapage_jours"], None, c["fenetre_jours"]):
        if budget <= 0:
            break
        budget -= 1
        r = col.appel("dart", lambda d=debut, fi=fin: f.dart(d.isoformat(), fi.isoformat()))
        if r is None:
            if col.etats.get("dart") == "non configurée":
                rech.sources["dart"]["detail"] = "clé non configurée (secret DART_API_KEY absent) : aucune recherche"
            break
        rech.periode("dart", debut, fin, len(r))
        for x in r:
            cle_inv, entite = qui(x.get("declarant"))
            if cle_inv:
                ajouter("dart", cle_inv, "KR", "DART", {**x, "entite": x.get("declarant"),
                                                        "ticker": f"{x['code']}.KS" if x.get("code") else None}, None, seuil=5.0, type="franchissement")
        if genre == "rattrapage":
            avancer(etat, "dart", debut)


def japon(f, col, etat, ch, aujourdhui, rech, qui, ajouter):
    c = ch["edinet"]
    rech.source("edinet", "EDINET (Japon), déclarations de grands actionnaires (5 %)")
    budget = c["jours_max_par_execution"]
    for genre, debut, fin in a_couvrir(etat, "edinet", aujourdhui, c["recent_jours"], c["rattrapage_jours"], None, 1):
        if budget <= 0:
            break
        if debut.weekday() >= 5:
            if genre == "rattrapage":
                avancer(etat, "edinet", debut)
            continue
        budget -= 1
        r = col.appel("edinet", lambda d=debut: f.edinet(d.isoformat()))
        if r is None:
            if col.etats.get("edinet") == "non configurée":
                rech.sources["edinet"]["detail"] = "clé non configurée (secret EDINET_API_KEY absent) : aucune recherche"
            break
        rech.periode("edinet", debut, fin, len(r))
        for x in r:
            cle_inv, entite = qui(x.get("declarant"))
            if cle_inv:
                ajouter("edinet", cle_inv, "JP", "EDINET", {**x, "entite": x.get("declarant")}, None, seuil=5.0, type="franchissement")
        if genre == "rattrapage":
            avancer(etat, "edinet", debut)


# ------------------------------------------------------------------ Turquie (KAP, source secondaire)

def turquie(f, col, etat, ch, aujourdhui, rech, alias, ajouter):
    c = ch["kap"]
    rech.source("kap", "KAP (Turquie), notifications « Pay Alım Satım Bildirimi » (source secondaire)")
    lus = etat.setdefault("kap_lus", {})
    budget_pdf, budget_listes = c["pdf_max_par_execution"], c["listes_max_par_execution"]
    tous_alias = [(cle, a) for cle, al in alias.items() for a in al]
    for genre, debut, fin in a_couvrir(etat, "kap", aujourdhui, c["recent_jours"], c["rattrapage_jours"], None, c["fenetre_jours"]):
        if budget_listes <= 0 or budget_pdf <= 0:
            break
        budget_listes -= 1
        r = col.appel("kap", lambda d=debut, fi=fin: f.kap_liste(d.isoformat(), fi.isoformat()))
        if r is None:
            break
        candidates = [x for x in r if x.get("sujet") in c["sujets"] and x.get("classe") in c["classes"]]
        complet = True
        n = 0
        for x in candidates:
            if str(x["id"]) in lus:
                continue
            if budget_pdf <= 0:
                complet = False
                break
            budget_pdf -= 1
            try:
                texte = f.kap_texte(x["id"])
            except Exception:  # noqa: BLE001
                complet = False
                continue
            lus[str(x["id"])] = x["date"]
            n += 1
            bas = texte.lower()
            for cle_inv, a in tous_alias:
                if a.lower() in bas:
                    titres = (x.get("titres") or "").split(",")[0].strip()
                    ajouter("kap", cle_inv, "TR", "KAP", {
                        "id": x["id"], "societe": titres or x.get("emetteur"), "ticker": f"{titres}.IS" if titres else None, "date": x["date"],
                        "url": f"https://www.kap.org.tr/tr/Bildirim/{x['id']}", "entite": a, "titre": x.get("resume") or x.get("sujet")},
                        A.pct_kap(texte), seuil=5.0, type="franchissement")
                    break
        rech.periode("kap", debut, fin, n)
        if genre == "rattrapage" and complet:
            avancer(etat, "kap", debut)
        elif not complet:
            break
    limite = (aujourdhui - timedelta(days=c["rattrapage_jours"] + 30)).isoformat()
    etat["kap_lus"] = {k: v for k, v in lus.items() if (v or "") >= limite}


# ------------------------------------------------------------------ France (AMF)

def france(f, col, etat, cfg, aujourdhui, rech, alias, ajouter):
    rech.source("amf_seuils", "AMF, franchissements de seuil")
    depuis = (aujourdhui - timedelta(days=cfg["hors_us"]["jours"])).isoformat()
    lus = etat.setdefault("spde_lus", {})
    pages = []
    for page in range(6):
        r = col.appel("amf_seuils", lambda p=page: f.amf_liste("SPDE", depuis, p))
        if not r:
            break
        pages += r
        if len(r) < 50:
            break
    n = 0
    for x in [x for x in pages if x.get("numero") not in lus and x.get("chemin")][:cfg["europe"]["franchissements_max_par_execution"]]:
        try:
            texte = f.amf_pdf(x["chemin"])
        except Exception:  # noqa: BLE001
            continue
        lus[x["numero"]] = x["publication"]
        n += 1
        for cle_inv, al in alias.items():
            trouve = A.chercher_entites(texte, al)
            if trouve:
                ajouter("amf_seuils", cle_inv, "FR", "AMF", {"id": x["numero"], "societe": ", ".join(x["societes"]) or None, "date": x["publication"],
                                                             "titre": f"Franchissement de seuil déclaré par {trouve[0]}", "entite": trouve[0],
                                                             "url": f"https://bdif.amf-france.org/back/api/v1/documents/{x['chemin']}"},
                        trouve[1], type="franchissement")
    rech.periode("amf_seuils", depuis, aujourdhui.isoformat(), n)
    etat["spde_lus"] = {k: v for k, v in lus.items() if v >= (aujourdhui - timedelta(days=30)).isoformat()}
