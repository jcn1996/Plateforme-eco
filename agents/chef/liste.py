"""
Liste d'investissement unique du chef d'orchestre (« entonnoir unique »).

Une seule liste est publiée (data/chef.json → liste) et affichée partout : « Où investir », le top 3, la carte
« À retenir », la bulle centrale de l'accueil et le briefing. Elle est tirée des sélections du dernier recalibrage validé
(agents/chef/selections.py), les mêmes que celles de l'agent trader, qui n'achète que dans cette liste.

1. Au plus `max_lignes` (15) lignes, classées : entreprises, matières premières, paris pays. Au plus `max_matieres`
   matières premières et `max_pays` paris pays ; les entreprises gardent au moins `min_entreprises` lignes quand il y en a.
2. Révision une fois par mois seulement, au rééquilibrage (première analyse complète du mois, juste avant la décision
   mensuelle du trader) : les lignes encore retenues restent, les places libres vont aux nouvelles.
3. Entre deux révisions, aucune entrée. Sorties possibles :
   - pari pays : dès qu'un excès se déclenche ou que la tendance casse (évaluation du jour des sélections) ;
   - entreprise ou matière première : sortie de sa combinaison confirmée `jours_confirmation` (5) jours de suite.
4. Conviction fondée sur le backtest, pas sur la note : retenue par 3 combinaisons (forte), par 2 (moyenne), par 1
   (faible).
5. Journal « entrées et sorties du mois », une ligne par mouvement, avec sa raison.
"""
from __future__ import annotations

from pathlib import Path

from ..commun.sortie import lire_json
from .moteur import ent, fr

CATEGORIES = ("entreprises", "matieres", "pays")
LIBELLES_CATEGORIES = {"entreprises": "Entreprises", "matieres": "Matières premières", "pays": "Paris pays"}
CONVICTIONS = {3: "forte", 2: "moyenne", 1: "faible"}
COMBI_PAYS = "Tendance saine + valorisation non tendue"
SIGNAUX = {"mscore": "M-score", "goodwill_actif": "goodwill / actif", "fcf_yield": "rendement du FCF", "conversion_cash": "conversion en cash",
           "niveau": "niveau historique", "positionnement": "positionnement CFTC"}


def conviction(n: int) -> str:
    return CONVICTIONS[max(1, min(3, n))]


# ------------------------------------------------------------------ résultats du backtest

def resultats_backtest(data: Path, cfg: dict) -> dict:
    """Résultat hors échantillon de chaque combinaison (écart annuel contre l'indice, part des actifs qui battent
    l'indice), lu dans data/backtest/resultats.json : {classe: {frozenset(signaux): {...}}, "pays": {...}}."""
    r = (lire_json(Path(data) / "backtest" / "resultats.json") or {}).get("donnees") or {}
    sections = r.get("sections") or {}
    h = str(cfg["horizon_gagnants_mois"])
    res = {"jour": r.get("jour")}
    for classe in ("entreprises", "matieres"):
        d = {}
        for c in ((sections.get(classe) or {}).get("combinaisons") or {}).get("retenues") or []:
            v = (c.get("comparaison") or {}).get("verification") or {}
            cible = (c.get("cible_verification") or {}).get(h) or {}
            d[frozenset(c.get("signaux") or [])] = {"ecart_indice_pct": v.get("vs_indice_annuel_pct"), "gagnants_pct": cible.get("battent_indice_pct"),
                                                    "verdict": c.get("verdict"), "mois": v.get("mois")}
        res[classe] = d
    t = (sections.get("tendance") or {}).get("suivi_tendance") or {}
    poche = t.get("poche") or {}
    ret = poche.get("retenue") or {}
    v = next((x for x in poche.get("variantes") or [] if x.get("definition") == ret.get("definition") and x.get("variante") == ret.get("variante")), None)
    ind = ((poche.get("references") or {}).get("indice") or {}).get("verification") or {}
    filtre = ((t.get("filtre") or {}).get("3m") or {}).get("premier_tiers_tendance_positive") or {}
    ecart = None
    if v and v["verification"].get("rendement_annuel_pct") is not None and ind.get("rendement_annuel_pct") is not None:
        ecart = round(v["verification"]["rendement_annuel_pct"] - ind["rendement_annuel_pct"], 2)
    res["pays"] = {"ecart_indice_pct": ecart, "gagnants_pct": filtre.get("reussite_pct"), "verdict": "suivi de tendance (lot « tendance »)",
                   "mois": (v or {}).get("verification", {}).get("mois")}
    return res


def _backtest_de(classe: str, combis: list[dict], bt: dict) -> list[dict]:
    res = []
    for c in combis:
        x = (bt.get(classe) or {}).get(frozenset(c.get("signaux") or []))
        res.append({"combinaison": c["libelle"], **(x or {"ecart_indice_pct": None, "gagnants_pct": None, "verdict": None, "mois": None})})
    return res


# ------------------------------------------------------------------ candidats du jour

def candidats(selections: dict, config: dict, bt: dict) -> dict[str, list[dict]]:
    """Candidats de chaque catégorie, dans l'ordre de préférence (conviction, puis score), sous forme de lignes publiables."""
    cfg = config["selections"]
    res = {k: [] for k in CATEGORIES}
    for classe, cle_combis in (("entreprises", "entreprises"), ("matieres", "matieres")):
        bloc = selections.get(classe) or {}
        combis = {c["cle"]: c for c in (cfg.get(cle_combis) or {}).get("combinaisons") or []}
        for x in bloc.get("retenues") or []:
            cs = [combis[k] for k in x.get("combinaisons") or [] if k in combis]
            n = len(cs) or 1
            pct = x.get("percentiles") or {}
            seuil = cfg["seuil_percentile"]
            detail = ", ".join(f"{SIGNAUX.get(s, s)} {ent(v)}e percentile" for s, v in pct.items())
            sortie = (f"plus aucune de ses combinaisons ne la retient (un signal sous le {seuil}e percentile : "
                      f"{', '.join(f'{SIGNAUX.get(s, s)} {ent(v)}e' for s, v in pct.items())}), confirmé {config['liste']['jours_confirmation']} jours de suite, "
                      "ou à la révision mensuelle.")
            res[classe].append({
                "id": x["id"], "categorie": classe, "type": x.get("type") or classe, "nom": x["nom"], "symbole": x.get("symbole"),
                "ticker": x.get("ticker"), "cle": x.get("cle") or x.get("ticker"), "pays": x.get("pays"), "secteur": x.get("secteur"),
                "secteur_nom": x.get("secteur_nom"), "devise": x.get("devise"),
                "combinaisons": [c["cle"] for c in cs] or list(x.get("combinaisons") or []),
                "combinaisons_libelles": [c["libelle"] for c in cs] or list(x.get("combinaisons_libelles") or []),
                "nb_combinaisons": n, "conviction": conviction(n), "backtest": _backtest_de(classe, cs, bt),
                "score_selection": x.get("score"), "percentiles": pct, "detail": detail, "sortie_si": sortie})
        res[classe].sort(key=lambda l: (-l["nb_combinaisons"], -(l["score_selection"] or 0), l["nom"]))
    ct = config["suivi_tendance"]
    for e in ((selections.get("paris_pays") or {}).get("candidats") or []):
        res["pays"].append({
            "id": e["id"], "categorie": "pays", "type": "pays", "nom": e["nom"], "symbole": e.get("symbole"), "cle": e.get("cle"), "pays": e.get("cle"),
            "combinaisons": ["tendance+valorisation"], "combinaisons_libelles": [COMBI_PAYS], "nb_combinaisons": 1, "conviction": conviction(1),
            "backtest": [{"combinaison": COMBI_PAYS, **(bt.get("pays") or {})}], "score_selection": e.get("force_relative"),
            "detail": (f"{e.get('tendance') or 'tendance saine'} ; valorisation {ent(e.get('valorisation_note'))}/100"),
            "sortie_si": (f"dès qu'un excès se déclenche (accélération ≥ {fr(ct['parabole_k'], 1)} fois la volatilité mensuelle, valorisation au-delà "
                          f"du {ct['valorisation_percentile']}e percentile, positionnement au {ct['cftc_percentile']}e percentile) ou que la tendance casse "
                          f"(performance 12 mois hors dernier mois négative ou cours sous la moyenne 200 jours"
                          + (f", soit {fr(e['mm200'], 2)}" if e.get("mm200") else "") + ")."),
            "force_relative": e.get("force_relative")})
    return res


def evaluations_pays(selections: dict) -> dict[str, dict]:
    return {e["id"]: e for e in ((selections.get("paris_pays") or {}).get("evaluation") or [])}


# ------------------------------------------------------------------ révision mensuelle

def reviser(cands: dict[str, list[dict]], anciennes: dict[str, dict], config: dict, detenus: set[str] | None = None) -> list[dict]:
    """Nouvelle liste : lignes encore retenues et déjà dans la liste d'abord, puis celles que le portefeuille démo détient
    déjà (stabilité, moins de rotation), puis les meilleures nouvelles, dans les limites."""
    cl = config["liste"]
    detenus = detenus or set()

    def ordonner(xs):  # tri stable : l'ordre de préférence (conviction, score) est conservé à rang égal
        return sorted(xs, key=lambda l: (l["id"] not in anciennes, l.get("symbole") not in detenus))

    ent_, mat, pays = (ordonner(cands[k]) for k in CATEGORIES)
    n_mat = min(len(mat), cl["max_matieres"])
    n_pays = min(len(pays), cl["max_pays"])
    n_ent = min(len(ent_), cl["max_lignes"] - n_mat - n_pays)
    besoin = min(len(ent_), cl["min_entreprises"])
    while n_ent < besoin and (n_mat or n_pays):  # les entreprises d'abord : on libère des places
        if n_pays >= n_mat and n_pays:
            n_pays -= 1
        else:
            n_mat -= 1
        n_ent = min(len(ent_), cl["max_lignes"] - n_mat - n_pays)
    return ent_[:n_ent] + mat[:n_mat] + pays[:n_pays]


def _mouvement(jour: str, sens: str, l: dict, raison: str) -> dict:
    return {"date": jour, "sens": sens, "id": l["id"], "nom": l["nom"], "categorie": l["categorie"],
            "texte": f"{'Entrée' if sens == 'entrée' else 'Sortie'} · {l['nom']} — {raison}"}


def _raison_entree(l: dict) -> str:
    b = next((x for x in l.get("backtest") or [] if x.get("ecart_indice_pct") is not None), None)
    return ("retenue par " + " ; ".join(l["combinaisons_libelles"])
            + (f" (backtest hors échantillon : {fr(b['ecart_indice_pct'], 1, True)} pt/an contre l'indice)" if b else ""))


# ------------------------------------------------------------------ mise à jour quotidienne

def symboles_detenus(data: Path) -> set[str]:
    """Supports détenus par le portefeuille démo (data/portefeuille.json)."""
    pf = (lire_json(Path(data) / "portefeuille.json") or {}).get("donnees") or {}
    return {p["symbole"] for p in pf.get("positions") or [] if p.get("symbole")}


def mettre_a_jour(etat: dict | None, selections: dict | None, jour: str, config: dict, bt: dict,
                  detenus: set[str] | None = None) -> tuple[dict, dict]:
    """Renvoie (liste publiée, nouvel état). `etat` = état précédent de la liste (data/chef/etat.json → liste)."""
    cl = config["liste"]
    etat = dict(etat or {})
    mois = jour[:7]
    lignes = {l["id"]: dict(l) for l in etat.get("lignes") or []}
    mouvements = [m for m in etat.get("mouvements") or [] if m["date"][:7] == mois]
    if selections:
        cands = candidats(selections, config, bt)
        par_id = {l["id"]: l for k in CATEGORIES for l in cands[k]}
        revision = etat.get("mois") != mois
        if revision:
            nouvelle = reviser(cands, lignes, config, detenus)
            ids = {l["id"] for l in nouvelle}
            for i, l in lignes.items():
                if i not in ids:
                    raison = ("n'est plus retenue par ses combinaisons" if i not in par_id
                              else f"liste complète ({cl['max_lignes']} lignes au plus) : place laissée à une ligne mieux classée")
                    if l["categorie"] == "pays" and i not in par_id:
                        raison = "pari pays : n'en remplit plus les conditions"
                    mouvements.append(_mouvement(jour, "sortie", l, f"révision mensuelle : {raison}"))
            res = {}
            for l in nouvelle:
                ancienne = lignes.get(l["id"])
                res[l["id"]] = {**l, "date_entree": ancienne["date_entree"] if ancienne else jour, "jours_hors": 0, "dernier_jour_hors": None}
                if not ancienne:
                    mouvements.append(_mouvement(jour, "entrée", l, f"révision mensuelle : {_raison_entree(l)}"))
            lignes = res
            etat["mois"], etat["revise_le"] = mois, jour
        else:
            ev = evaluations_pays(selections)
            for i, l in list(lignes.items()):
                if l["categorie"] == "pays":
                    e = ev.get(i)
                    if e and e.get("sortie"):
                        mouvements.append(_mouvement(jour, "sortie", l, " ; ".join(e.get("raisons_sortie") or ["excès ou tendance cassée"])))
                        del lignes[i]
                    elif i in par_id:
                        lignes[i] = {**l, **{k: v for k, v in par_id[i].items() if k not in ("conviction", "nb_combinaisons")}}
                    continue
                if i in par_id:  # toujours retenue : compteur remis à zéro, informations du jour
                    lignes[i] = {**l, **par_id[i], "date_entree": l["date_entree"], "jours_hors": 0, "dernier_jour_hors": None}
                    continue
                if l.get("dernier_jour_hors") != jour:
                    l["jours_hors"] = (l.get("jours_hors") or 0) + 1
                    l["dernier_jour_hors"] = jour
                if l["jours_hors"] >= cl["jours_confirmation"]:
                    mouvements.append(_mouvement(jour, "sortie", l, f"sortie de sa combinaison confirmée {cl['jours_confirmation']} jours de suite"))
                    del lignes[i]
                else:
                    lignes[i] = l
    ordre = {k: i for i, k in enumerate(CATEGORIES)}
    publiees = sorted(lignes.values(), key=lambda l: (ordre[l["categorie"]], -l["nb_combinaisons"], -(l.get("score_selection") or 0), l["nom"]))
    for l in publiees:
        l["alerte_sortie"] = (f"hors de sa combinaison depuis {l['jours_hors']} jour(s) sur {cl['jours_confirmation']} : sortie si cela continue"
                              if l.get("jours_hors") else None)
    etat["lignes"] = publiees
    etat["mouvements"] = mouvements
    top3 = sorted(publiees, key=lambda l: (-l["nb_combinaisons"], ordre[l["categorie"]],
                                            -max([b.get("ecart_indice_pct") or -99 for b in l.get("backtest") or []] or [-99])))[:3]
    liste = {"mois": etat.get("mois"), "revise_le": etat.get("revise_le"), "prochaine_revision": _mois_suivant(etat.get("mois")),
             "lignes": publiees, "nombre": len(publiees), "max_lignes": cl["max_lignes"],
             "par_categorie": {k: sum(1 for l in publiees if l["categorie"] == k) for k in CATEGORIES},
             "top3": [{"id": l["id"], "nom": l["nom"], "categorie": l["categorie"], "conviction": l["conviction"],
                       "nb_combinaisons": l["nb_combinaisons"], "combinaisons_libelles": l["combinaisons_libelles"]} for l in top3],
             "mouvements": list(reversed(mouvements)), "source_backtest": bt.get("jour"),
             "regle": (f"Liste unique issue du dernier recalibrage validé (les mêmes sélections que le trader), {cl['max_lignes']} lignes au plus : "
                       "entreprises, matières premières, paris pays. Révisée une fois par mois, au rééquilibrage ; entre deux, aucune entrée, "
                       f"et seules sorties : excès ou tendance cassée pour un pari pays, sortie de la combinaison confirmée {cl['jours_confirmation']} jours "
                       "de suite pour les autres. Conviction : retenue par 3 combinaisons (forte), 2 (moyenne) ou 1 (faible)."),
             "mention_note": config["selections"]["mention_pays"]}
    return liste, etat


def _mois_suivant(mois: str | None) -> str | None:
    if not mois:
        return None
    a, m = int(mois[:4]), int(mois[5:7])
    return f"{a + (m == 12)}-{1 if m == 12 else m + 1:02d}"
