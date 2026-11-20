"""
Fiches d'investissement lisibles de la liste unique (« Où investir », briefing), construites par règles à partir des
données existantes : fiche de l'agent entreprises, données de l'agent matières premières, lignes pays du chef
d'orchestre et agent pays, cours des ETF pays, portefeuille démo. Aucun appel à l'IA ; aucune donnée inventée : une
donnée manquante est indiquée comme telle.

Cinq blocs, plus la base statistique (repliée dans l'appli) :
1. en-tête : nom, symbole, conviction, poids dans le portefeuille démo, phrase-verdict (20 mots au plus) ;
2. pourquoi investir : 3 points au plus, chacun avec un chiffre concret en langage courant (jamais un percentile seul) ;
3. pourquoi pas : 1 à 3 points (contre-scénario, alertes, dette, dilution, Z-score d'Altman…) ;
4. momentum : favorable, neutre ou défavorable — « défavorable (retournement récent) » si la baisse dépasse 15 % sur 3 ou
   6 mois malgré un 12 mois positif —, performances à 3, 6 et 12 mois ; contradiction avec le dossier signalée ;
5. ce qui ferait sortir : une phrase.
Version courte pour le briefing : verdict, un « pour », un « contre », le momentum.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from ..commun.sortie import lire_json
from ..risque.calculs import fr

MOTS_VERDICT = 20
SEUIL_RETOURNEMENT = -15  # % sur 3 ou 6 mois
RETOURNEMENT = "défavorable (retournement récent)"


def est_defavorable(mot: str) -> bool:
    return mot.startswith("défavorable")
CONVICTIONS = {"forte": "conviction forte (3 combinaisons)", "moyenne": "conviction moyenne (2 combinaisons)",
               "faible": "conviction faible (1 combinaison)"}
INCONNU = "donnée manquante"


def phrase_verdict(pour: list, contre: list, momentum_negatif: bool, tag_momentum: str | None, defaut: str, suffixe: str = "") -> str:
    """« Atout, atout[ : suffixe] ; réserve : r1, r2. » — 20 mots au plus, sans troncature (on retire d'abord une réserve,
    puis un atout)."""
    atouts = [t for t in pour if t][:2]
    reserves = [t for t in contre if t][:2]
    if momentum_negatif and tag_momentum:
        reserves = (reserves[:1] + [tag_momentum])
    while True:
        tete = (" et ".join(atouts)) if atouts else defaut
        tete = tete[0].upper() + tete[1:] + (suffixe if atouts else "")
        phrase = tete + (f" ; réserve : {', '.join(reserves)}." if reserves else ".")
        if len(phrase.split()) <= MOTS_VERDICT or (len(reserves) <= 1 and len(atouts) <= 1):
            return limiter_mots(phrase)
        if len(reserves) > 1:
            reserves = reserves[:1]
        else:
            atouts = atouts[:1]


def limiter_mots(phrase: str, n: int = MOTS_VERDICT) -> str:
    mots = phrase.split()
    if len(mots) <= n:
        return phrase
    return " ".join(mots[:n]).rstrip(",;:") + "…"


def _pct(x, d=1, signe=True) -> str:
    return INCONNU if x is None else f"{fr(x, d, signe)} %"


def _val(ind: dict, cle: str):
    x = ind.get(cle)
    return x.get("valeur") if isinstance(x, dict) else None


# ------------------------------------------------------------------ momentum

def perf_serie(serie, mois: int) -> float | None:
    """Performance (%) sur `mois` mois d'une série [(date, cours)] quotidienne ou hebdomadaire."""
    pts = []
    for p in serie or []:
        try:
            pts.append((date.fromisoformat(str(p[0])[:10]), float(p[1])))
        except (TypeError, ValueError, IndexError):
            continue
    pts.sort()
    if len(pts) < 2:
        return None
    fin, dernier = pts[-1]
    cible = fin - timedelta(days=round(30.44 * mois))
    avant = [x for d, x in pts if d <= cible]
    if not avant or (cible - max(d for d, _ in pts if d <= cible)).days > 12:
        return None
    return round((dernier / avant[-1] - 1) * 100, 1)


def mot_momentum(m3, m6, m12) -> str:
    """Favorable / neutre / défavorable, d'après les performances à 3, 6 et 12 mois (12 mois prépondérant).
    Une baisse de plus de 15 % sur 3 ou 6 mois l'emporte, même si le 12 mois est positif : « défavorable (retournement
    récent) » ; une baisse déjà durable (règle de base défavorable) reste « défavorable »."""
    connus = [x for x in (m3, m6, m12) if x is not None]
    if not connus:
        return "inconnu"
    if (m12 is not None and m12 <= -10) or (len(connus) == 3 and all(x < 0 for x in connus)):
        return "défavorable"
    if any(x is not None and x < SEUIL_RETOURNEMENT for x in (m3, m6)):
        return RETOURNEMENT
    if (m12 is not None and m12 >= 10 and (m3 is None or m3 > -5)) or (len(connus) == 3 and all(x > 0 for x in connus)):
        return "favorable"
    return "neutre"


def momentum(m3, m6, m12, contradiction: str) -> dict:
    mot = mot_momentum(m3, m6, m12)
    texte = f"3 mois {_pct(m3)} · 6 mois {_pct(m6)} · 12 mois {_pct(m12)}"
    return {"mot": mot, "m3": m3, "m6": m6, "m12": m12, "texte": texte,
            "contradiction": contradiction if est_defavorable(mot) else None}


# ------------------------------------------------------------------ entreprises

def _points_entreprise(f: dict, combinaisons: list[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """([(étiquette courte, point)] pour, [(étiquette, point)] contre) : chiffres concrets, en langage courant."""
    ind = dict(f.get("indicateurs") or {})
    ind.update(((f.get("analyse_financiere") or {}).get("indicateurs")) or {})
    valo = f.get("valorisation") or {}
    signaux = {s for c in combinaisons for s in c.split("+")}
    pour, contre = [], []
    fcf = _val(ind, "fcf_yield")
    if fcf is not None and fcf > 0:
        pour.append(("fcf_yield", "cash abondant",
                     f"Le cash-flow disponible représente {fr(fcf, 1)} % de la valeur en Bourse par an."))
    conv = _val(ind, "conversion_cash")
    if conv is not None and conv >= 90:
        pour.append(("conversion_cash", "bénéfice bien encaissé",
                     (f"Le cash encaissé atteint {fr(conv / 100, 1)} fois le bénéfice comptable." if conv >= 150
                      else f"{fr(conv, 0)} % du bénéfice comptable est encaissé en cash.")))
    per, pct = valo.get("per"), valo.get("per_secteur")
    if per and per > 0 and pct is not None and pct < 0:
        med = per / (1 + pct / 100)
        pour.append(("per_secteur", "PER sous son secteur", f"PER de {fr(per, 1)} contre {fr(med, 1)} pour la médiane de son secteur."))
    fs = _val(ind, "fscore")
    if fs is not None and fs >= 7:
        pour.append(("fscore", "santé financière en progrès", f"F-score de Piotroski de {fr(fs, 0)} sur 9 : la santé financière s'améliore sur la plupart des critères."))
    ms = _val(ind, "mscore")
    if ms is not None and ms < -1.78:
        pour.append(("mscore", "comptes fiables",
                     f"M-score de Beneish de {fr(ms, 2)} : sous le seuil d'alerte de −1,78, pas de signe de comptes embellis."))
    gw = _val(ind, "goodwill_actif")
    if gw is not None and gw < 15:
        pour.append(("goodwill_actif", "peu de goodwill",
                     f"Le goodwill (écart d'acquisition) ne pèse que {fr(gw, 1)} % de l'actif : peu de valeur à risque de dépréciation."))
    roic = _val(ind, "roic")
    if roic is not None and roic >= 12:
        pour.append(("roic", "rentabilité élevée", f"Chaque euro investi rapporte {fr(roic, 1)} % par an (ROIC)."))
    # les critères des combinaisons qui retiennent la société d'abord
    pour.sort(key=lambda x: x[0] not in signaux)

    alt = _val(ind, "altman_z")
    if alt is not None and alt < 1.81:
        contre.append(("altman", "bilan fragile",
                       f"Z-score d'Altman de {fr(alt, 2)} : zone de détresse financière (sous 1,8)."))
    for a in f.get("alertes") or []:
        if a.get("cle") == "dilution":
            contre.append(("dilution", "dilution", f"Dilution : {a.get('texte') or a.get('titre')}."))
    evo = _val(ind, "evolution_actions")
    if evo is not None and evo >= 10 and not any(c[0] == "dilution" for c in contre):
        contre.append(("dilution", "dilution", f"Nombre d'actions en hausse de {fr(evo, 1)} % en 3 ans : les actionnaires sont dilués."))
    de = _val(ind, "dette_ebitda")
    cov = _val(ind, "couverture_interets")
    if de is not None and de >= 3:
        contre.append(("dette", "dette lourde", f"Dette nette égale à {fr(de, 1)} années de résultat d'exploitation (EBITDA)."))
    elif cov is not None and cov < 3:
        contre.append(("dette", "intérêts lourds", f"Le résultat d'exploitation ne couvre que {fr(cov, 1)} fois les intérêts de la dette."))
    for a in f.get("alertes") or []:
        if a.get("cle") != "dilution" and a.get("titre"):
            contre.append(("alerte", a["titre"].lower(), f"{a['titre']} : {a.get('texte') or 'alerte de l’agent entreprises'}."))
    reco = (f.get("recommandation") or {}).get("si_non_detenu")
    if reco in ("Éviter", "Attendre"):
        contre.append(("reco", f"avis « {reco} » de l'agent entreprises",
                       f"L'agent entreprises, sur l'ensemble de ses critères, recommande « {reco} » à 12 mois (note {fr(f.get('note'), 0)}/100)."))
    for t in f.get("contre_scenario") or []:
        contre.append(("scenario", None, t))
    return pour, contre


def fiche_entreprise(l: dict, f: dict | None, poids, cfg_tendance: dict) -> dict:
    f = f or {}
    pour, contre = _points_entreprise(f, l.get("combinaisons") or []) if f else ([], [])
    m = f.get("momentum") or {}
    mom = momentum(m.get("m3"), m.get("m6"), m.get("m12"),
                   "Le momentum contredit le dossier : le cours baisse alors que les critères comptables retenus sont favorables. "
                   "Le backtest ne garantit pas un rebond.")
    verdict = phrase_verdict([p[1] for p in pour], [c[1] for c in contre], est_defavorable(mom["mot"]), "cours en baisse",
                             "Retenue par le backtest, comptes détaillés manquants")
    signaux = {"fcf_yield": "rendement du cash-flow", "goodwill_actif": "poids du goodwill", "mscore": "M-score",
               "conversion_cash": "conversion du bénéfice en cash"}
    criteres = sorted({signaux.get(s, s) for c in l.get("combinaisons") or [] for s in c.split("+")})
    sortie = (f"Sortie si la société n'est plus parmi les 30 % meilleures sur ses critères ({', '.join(criteres)}) "
              "cinq jours de suite, ou à la révision mensuelle.")
    return _assembler(l, poids, verdict, [p[2] for p in pour], [c[2] for c in contre], mom, sortie,
                      manque="fiche de l'agent entreprises absente" if not f else None)


# ------------------------------------------------------------------ matières premières

def fiche_matiere(l: dict, m: dict | None, poids) -> dict:
    m = m or {}
    sn = m.get("sous_notes") or {}
    unite = m.get("unite") or ""
    pour, contre = [], []
    niv = sn.get("niveau") or {}
    if niv.get("percentile") is not None and m.get("cours") is not None:
        plus_bas = 100 - niv["percentile"]
        pour.append(("niveau", "prix au plus bas historique" if niv["percentile"] <= 10 else "prix bas sur 10 ans",
                     f"Prix de {fr(m['cours'], 2)} {unite} : {'inflation déduite, ' if niv.get('corrige_inflation') else ''}plus bas que "
                     f"{fr(plus_bas, 0)} % des cours des {niv.get('annees', 10)} dernières années (extrêmes en valeur nominale : "
                     f"{fr(niv.get('plus_bas'), 2)} et {fr(niv.get('plus_haut'), 2)})."))
    pos = sn.get("positionnement") or {}
    if pos.get("net") is not None:
        sens = "vendeurs" if pos["net"] < 0 else "acheteurs"
        rare = (100 - pos["percentile"]) if pos["net"] < 0 and pos.get("percentile") is not None else pos.get("percentile")
        pour.append(("positionnement", f"spéculateurs très {sens}",
                     f"Les spéculateurs sont nets {sens} de {fr(abs(pos['net']), 0)} contrats ({fr(pos.get('part_oi_pct'), 1, True)} % des positions ouvertes)"
                     + (f", une position plus extrême que {fr(rare, 0)} % des semaines sur 3 ans." if rare is not None else ".")))
    for cle in ("courbe", "stocks", "geopolitique", "flux"):
        x = sn.get(cle) or {}
        if x.get("note") is not None and x["note"] >= 60 and len(pour) < 3:
            pour.append((cle, {"courbe": "courbe favorable", "stocks": "stocks bas", "geopolitique": "tensions géopolitiques porteuses",
                               "flux": "flux d'investissement entrants"}[cle], x["texte"].rstrip(".") + "."))
    tend = sn.get("tendance") or {}
    if tend.get("note") is not None and tend["note"] < 40:
        contre.append(("tendance", "prix encore en baisse", (tend.get("texte") or "Tendance baissière").rstrip(".") + "."))
    crb = sn.get("courbe") or {}
    if crb.get("structure") == "contango" and crb.get("roulement_pct_an") is not None:
        contre.append(("courbe", "coût de détention", f"Courbe en contango : détenir via un ETF à contrats coûte environ {fr(abs(crb['roulement_pct_an']), 1)} % par an."))
    mac = sn.get("macro") or {}
    if mac.get("note") is not None and mac["note"] < 45:
        contre.append(("macro", "contexte macro peu porteur", mac["texte"].rstrip(".") + "."))
    for t in m.get("ce_qui_pourrait_me_donner_tort") or []:
        contre.append(("scenario", None, t))
    m3, m12 = tend.get("variation_3m"), tend.get("variation_12m", m.get("variation_12m"))
    mom = momentum(m3, perf_serie(m.get("serie"), 6), m12,
                   "Le momentum contredit le dossier : le prix baisse encore. La combinaison parie sur un rebond depuis un niveau bas, "
                   "sans signal de retournement à ce jour.")
    verdict = phrase_verdict([p[1] for p in pour], [c[1] for c in contre], False, None,
                             "Retenue par le backtest, détail manquant", suffixe=" : pari de rebond")
    sortie = ("Sortie si le prix n'est plus parmi les 30 % les plus bas de son histoire ou si les spéculateurs ne sont plus "
              "parmi les plus vendeurs, cinq jours de suite, ou à la révision mensuelle.")
    return _assembler(l, poids, verdict, [p[2] for p in pour], [c[2] for c in contre], mom, sortie,
                      manque="données de l'agent matières premières absentes" if not m else None)


# ------------------------------------------------------------------ paris pays

def fiche_pays(l: dict, o: dict | None, p: dict | None, serie, poids, cfg_tendance: dict, bt: list[dict]) -> dict:
    o, p = o or {}, p or {}
    st = o.get("suivi_tendance") or {}
    val = ((p.get("indicateurs") or {}).get("valorisation")) or {}
    pour, contre = [], []
    if st.get("perf_12_1") is not None:
        pour.append(("tendance", "tendance haussière saine",
                     f"Hausse de {fr(st['perf_12_1'], 1)} % sur 12 mois (hors dernier mois), cours au-dessus de sa moyenne 200 jours ({fr(st.get('mm200'), 2)})."))
    if val.get("per") and val.get("mediane"):
        pour.append(("valorisation", "valorisation basse" if val["per"] < val["mediane"] else "valorisation dans la norme",
                     f"PER de l'ETF {val.get('symbole') or l.get('symbole')} de {fr(val['per'], 1)} contre {fr(val['mediane'], 1)} pour la médiane des pays suivis."))
    if st.get("rang") and st.get("sur"):
        pour.append(("force", "parmi les tendances les plus fortes", f"{st['rang']}e pays sur {st['sur']} pour la force de la tendance sur 12 mois."))
    inv = (st.get("invalidation") or {})
    if inv.get("ecart_mm200_pct") is not None and inv["ecart_mm200_pct"] < 8:
        contre.append(("marge", "tendance proche du seuil",
                       f"Le cours n'est qu'à {fr(inv['ecart_mm200_pct'], 1)} % au-dessus de sa moyenne 200 jours : la tendance casserait sous {fr(inv.get('mm200'), 2)}."))
    if st.get("perf_1m") is not None and st["perf_1m"] <= -5:
        contre.append(("repli", "repli récent", f"Repli de {fr(abs(st['perf_1m']), 1)} % sur le dernier mois."))
    b = next((x for x in bt or [] if x.get("ecart_indice_pct") is not None), None)
    if b and b["ecart_indice_pct"] < 0:
        contre.append(("backtest", "règle peu payante au backtest",
                       f"Au backtest, les paris pays ont fait {fr(abs(b['ecart_indice_pct']), 1)} points par an de moins que l'indice mondial."))
    for t in p.get("contre_scenario") or []:
        contre.append(("scenario", None, t))
    mom = momentum(perf_serie(serie, 3), perf_serie(serie, 6), perf_serie(serie, 12),
                   "Le momentum contredit le dossier : un pari pays repose sur la tendance, qui faiblit ; la sortie est proche.")
    verdict = phrase_verdict([x[1] for x in pour], [x[1] for x in contre], est_defavorable(mom["mot"]), "tendance qui faiblit",
                             "Pari de tendance, détail manquant")
    ct = cfg_tendance
    sortie = (f"Sortie dès que le cours passe sous sa moyenne 200 jours ({fr(inv.get('mm200'), 2)}), que la hausse sur 12 mois devient négative, "
              f"ou qu'un excès apparaît (hausse d'un mois de plus de {fr(ct['parabole_k'], 1)} fois la volatilité habituelle, valorisation chère, "
              "spéculateurs très acheteurs).")
    return _assembler(l, poids, verdict, [x[2] for x in pour], [x[2] for x in contre], mom, sortie,
                      manque="suivi de tendance du pays absent" if not st else None)


# ------------------------------------------------------------------ assemblage

def _assembler(l: dict, poids, verdict: str, pour: list[str], contre: list[str], mom: dict, sortie: str, manque: str | None = None) -> dict:
    vus, contre_u = set(), []
    for c in contre:
        if c not in vus:
            vus.add(c)
            contre_u.append(c)
    if not contre_u:
        contre_u = ["Combinaison jugée « Prometteuse » mais non significative au backtest : elle peut ne pas tenir."]
    if not pour:
        pour = [f"Aucun chiffre détaillé disponible ({manque or INCONNU}) : seule la combinaison du backtest retient la ligne."]
    verdict = limiter_mots(verdict)
    base = [{"combinaison": b.get("combinaison"), "ecart_indice_pct": b.get("ecart_indice_pct"), "gagnants_pct": b.get("gagnants_pct"),
             "verdict": b.get("verdict"), "mois": b.get("mois")} for b in l.get("backtest") or []]
    return {
        "entete": {"nom": l["nom"], "symbole": l.get("symbole"), "conviction": l.get("conviction"),
                   "conviction_texte": CONVICTIONS.get(l.get("conviction"), l.get("conviction")),
                   "poids_pct": poids, "poids_texte": f"{fr(poids, 1)} % du portefeuille démo" if poids is not None else "non détenue par le portefeuille démo",
                   "verdict": verdict},
        "pour": pour[:3], "contre": contre_u[:3], "momentum": mom, "sortie": sortie,
        "base_statistique": {"combinaisons": base, "percentiles": l.get("percentiles"), "date_entree": l.get("date_entree"), "detail": l.get("detail")},
        "manque": manque,
        "courte": {"verdict": verdict, "pour": pour[0], "contre": contre_u[0],
                   "momentum": f"momentum {mom['mot']} ({mom['texte']})" + (" — contredit le dossier" if mom.get("contradiction") else "")},
    }


def poids_portefeuille(data: Path) -> dict[str, float]:
    """Poids (%) de chaque ligne du chef d'orchestre dans le portefeuille démo (data/portefeuille.json), par identifiant."""
    pf = (lire_json(Path(data) / "portefeuille.json") or {}).get("donnees") or {}
    res = {}
    for x in pf.get("positions") or []:
        if x.get("ligne_id") and x.get("poids") is not None:
            res[x["ligne_id"]] = res.get(x["ligne_id"], 0) + x["poids"]
    return res


def construire(lignes: list[dict], ctx, pays_opps: list[dict], series: dict, data: Path, config: dict) -> list[dict]:
    """Copie des lignes de la liste, chacune avec sa fiche (« fiche »)."""
    poids = poids_portefeuille(data)
    mp = {m.get("cle"): m for m in ctx.mp.get("matieres") or []}
    opps = {o["id"]: o for o in pays_opps}
    res = []
    for l in lignes:
        w = poids.get(l["id"])
        if l["categorie"] == "entreprises":
            f = fiche_entreprise(l, ctx.fiche(l.get("ticker") or l.get("cle")), w, config["suivi_tendance"])
        elif l["categorie"] == "matieres":
            f = fiche_matiere(l, mp.get(l.get("cle")), w)
        else:
            f = fiche_pays(l, opps.get(l["id"]), ctx.pays.get(l.get("cle")), series.get(l.get("symbole")), w,
                           config["suivi_tendance"], l.get("backtest"))
        res.append({**l, "fiche": f})
    return res
