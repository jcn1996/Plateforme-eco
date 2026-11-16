"""
Synthèse : briefing quotidien (règles, ou Gemini sous contrôle), alertes du jour, agenda des 7 prochains
jours, revue hebdomadaire.

Briefing rédigé par Gemini : chaque phrase doit citer au moins un fait fourni ([F3]) et ne contenir que des
chiffres présents dans les faits cités ; sinon elle est supprimée. Si une rubrique n'a plus assez de phrases
valides, la version par règles est utilisée pour cette rubrique (signalé dans le briefing).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from ..risque.calculs import date_fr, fr
from .moteur import DIRECTION, ent

PHASES = {("accélère", "ralentit"): "Reprise", ("accélère", "accélère"): "Surchauffe",
          ("ralentit", "accélère"): "Ralentissement inflationniste", ("ralentit", "ralentit"): "Expansion sans inflation"}
PALIERS = ["Calme", "Vigilance", "Tension", "Crise"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class Faits:
    def __init__(self):
        self.liste = []

    def ajouter(self, texte: str, source: str) -> str:
        i = f"F{len(self.liste) + 1}"
        self.liste.append({"id": i, "texte": texte, "source": source})
        return i


def libelle_ligne(l: dict) -> str:
    return f"{l['nom']} : « {l['verdict']} », conviction {l['conviction']}, {ent(l['score'])}/100"


def top(lignes: list[dict], n: int = 5, positif: bool = True, par_type: int = 2) -> list[dict]:
    """Meilleures (ou pires) opportunités, par conviction puis score ; au plus `par_type` lignes d'un même type
    (pays, entreprises, matières premières…) pour garder une vue diversifiée."""
    rangs = {"forte": 2, "moyenne": 1, "faible": 0}
    s = 1 if positif else -1
    c = sorted((l for l in lignes if DIRECTION.get(l["verdict"]) == s and l.get("score") is not None),
               key=lambda l: (-rangs.get(l["conviction"], 0), -s * l["score"]))
    res, par = [], {}
    for l in c:
        if par.get(l["type"], 0) >= par_type:
            continue
        par[l["type"]] = par.get(l["type"], 0) + 1
        res.append(l)
    return res[:n]


# ------------------------------------------------------------------ agenda

def agenda(jour: date, macro: dict, config: dict, resultats: list[dict] | None = None) -> list[dict]:
    ca = config["agenda"]
    fin = jour + timedelta(days=ca["jours"])
    res = []
    for b in macro.get("banques_centrales") or []:
        r = b.get("prochaine_reunion") or {}
        if r.get("date") and jour.isoformat() <= r["date"] <= fin.isoformat():
            res.append({"date": r["date"], "libelle": f"{b['nom']} : décision de politique monétaire (taux actuel {fr(b.get('taux'), 2)} %)",
                        "source": "agent macro (calendriers officiels des banques centrales)", "indicative": False, "categorie": "banque centrale"})
    for x in resultats or []:
        if x.get("date") and jour.isoformat() <= x["date"] <= fin.isoformat():
            res.append({"date": x["date"], "libelle": f"{x['nom']} ({x['ticker']}) : publication des résultats", "source": "Yahoo Finance (calendrier des résultats)",
                        "indicative": True, "categorie": "résultats"})
    d = jour
    while d <= fin:
        for e in ca["eia"]:
            if d.weekday() == e["jour_semaine"]:
                res.append({"date": d.isoformat(), "libelle": e["libelle"], "source": "EIA (rythme hebdomadaire ; décalé d'un jour en cas de jour férié)", "indicative": True, "categorie": "matières premières"})
        a, b = ca["wasde"]["jour_du_mois_approx"]
        if d.day == a:
            res.append({"date": d.isoformat(), "libelle": f"{ca['wasde']['libelle']} — entre le {a} et le {b} (date exacte : calendrier de l'USDA)",
                        "source": "USDA (rythme mensuel)", "indicative": True, "categorie": "matières premières"})
        for m in ca["macro"]:
            ok = False
            if m["regle"] == "premier_vendredi":
                ok = d.weekday() == 4 and d.day <= 7
                texte = m["libelle"]
            elif m["regle"] in ("jours_du_mois", "fin_de_mois"):
                ok = d.day == m["jours"][0]
                texte = f"{m['libelle']} — entre le {m['jours'][0]} et le {m['jours'][1]}" if m["regle"] == "jours_du_mois" else f"{m['libelle']} — fin du mois"
            if ok:
                res.append({"date": d.isoformat(), "libelle": texte, "source": "règle de calendrier (date à confirmer auprès de la source)", "indicative": True, "categorie": "statistique macro"})
        d += timedelta(days=1)
    res.sort(key=lambda x: (x["date"], x["categorie"]))
    for x in res:
        dd = date.fromisoformat(x["date"])
        x["jour"] = f"{JOURS[dd.weekday()]} {dd.day:02d}/{dd.month:02d}"
    return res


# ------------------------------------------------------------------ scénarios

def scenarios(macro: dict, risque: dict) -> dict:
    zones = {z.get("cle"): z for z in ((macro.get("cycle") or {}).get("zones") or [])}
    m = zones.get("monde") or {}
    phase = m.get("phase")
    mondial = (risque or {}).get("mondial") or {}
    palier = mondial.get("palier")
    seuils = (risque or {}).get("seuils") or {}
    cr, inf = (m.get("croissance") or {}).get("direction"), (m.get("inflation") or {}).get("direction")
    inverse = {"accélère": "ralentit", "ralentit": "accélère"}
    alt_phase = PHASES.get((inverse.get(cr), inf)) if cr and inf else None
    suivant = PALIERS[min(3, PALIERS.index(palier) + 1)] if palier in PALIERS else None
    central = {"titre": f"Le cycle mondial reste en « {phase or 'n. d.'} » et le risque en « {palier or 'n. d.'} »",
               "texte": "Scénario central : les tendances mesurées se prolongent ; les verdicts et l'allocation actuels restent valables.",
               "declencheurs": [x for x in (m.get("contre_scenario") or macro.get("contre_scenario") or [])][:2]
               + [x for x in (mondial.get("contre") or [])][:1]}
    declencheurs = []
    if alt_phase:
        declencheurs.append(f"Croissance qui {inverse.get(cr)} (indicateur avancé de l'OCDE, deux signaux concordants) : passage en « {alt_phase} ».")
    if suivant and suivant != palier and seuils.get(suivant) is not None:
        declencheurs.append(f"Score de stress financier au-dessus de {fr(seuils[suivant], 0)}/100 avec deux familles d'indicateurs concordantes : palier « {suivant} ».")
    declencheurs += [x for x in (macro.get("contre_scenario") or []) if "Sahm" in x or "inversion" in x][:1]
    alternatif = {"titre": f"Bascule vers « {alt_phase or 'une autre phase'} »" + (f" et risque « {suivant} »" if suivant and suivant != palier else ""),
                  "texte": "Scénario alternatif : retournement de la croissance mondiale ou montée du stress financier ; les actifs refuges (or, obligations d'État, liquidités) seraient favorisés.",
                  "declencheurs": declencheurs or ["Aucun déclencheur mesurable disponible (données macro manquantes)."]}
    return {"central": central, "alternatif": alternatif}


# ------------------------------------------------------------------ briefing par règles

RANGS = {"forte": 2, "moyenne": 1, "faible": 0}
CATEGORIES = {"pays": "Pays", "secteurs": "Secteurs", "entreprises": "Entreprises", "matieres": "Matières premières", "or": "Or",
              "obligations": "Obligations", "liquidites": "Liquidités"}


def _argument(l: dict, sens: str = "pour") -> str | None:
    a = (l.get(sens) or [None])[0]
    return (l.get("familles") or {}).get(a["cle"], {}).get("texte") if a else None


def a_surveiller(l: dict) -> bool:
    """Ligne bien notée mais avec une réserve à lever : objection sérieuse ou tendance forte en excès."""
    return bool((l.get("objection") or {}).get("serieuse") or l.get("tendance_excessive"))


def resume_ligne(l: dict) -> dict:
    return {"id": l["id"], "nom": l["nom"], "type": l["type"], "verdict": l["verdict"], "conviction": l["conviction"], "score": l.get("score"),
            "zone_secteur": l.get("zone_secteur"), "a_surveiller": a_surveiller(l),
            "fleche": l.get("fleche"), "pays": l.get("pays"), "secteur": l.get("secteur_nom") or l.get("secteur"),
            "argument": _argument(l, "pour"), "contre": _argument(l, "contre"),
            "objection": (l.get("objection") or {}).get("objection") if (l.get("objection") or {}).get("serieuse") else None}


def _cle_tri(l: dict):
    return (-DIRECTION.get(l["verdict"], 0), -RANGS.get(l["conviction"], 0), -(l.get("score") or 0))


def selection_entreprises(lignes: list[dict], cp: dict) -> tuple[list[dict], dict]:
    """Entreprises du panorama : verdicts positifs d'abord (conviction puis score), au plus `max_par_secteur` par secteur
    et `max_par_pays` par pays ; complétées par les meilleurs « Neutre » si les verdicts positifs ne suffisent pas."""
    cands = sorted((l for l in lignes if l["type"] == "entreprises" and l.get("score") is not None and DIRECTION.get(l["verdict"]) >= 0), key=_cle_tri)
    choix, par_s, par_p = [], {}, {}
    for l in cands:
        s, p = l.get("secteur") or "?", l.get("pays") or "?"
        if par_s.get(s, 0) >= cp["max_par_secteur"] or par_p.get(p, 0) >= cp["max_par_pays"]:
            continue
        if DIRECTION.get(l["verdict"]) == 0 and len(choix) >= cp["entreprises_min"]:
            break
        choix.append(l)
        par_s[s] = par_s.get(s, 0) + 1
        par_p[p] = par_p.get(p, 0) + 1
        if len(choix) >= cp["entreprises_max"]:
            break
    bilan = {"nombre": len(choix), "secteurs": len(par_s), "pays": len(par_p), "positifs": sum(1 for l in choix if DIRECTION.get(l["verdict"]) == 1)}
    manques = []
    if bilan["nombre"] < cp["entreprises_min"]:
        manques.append(f"{bilan['nombre']} entreprises seulement (minimum visé : {cp['entreprises_min']})")
    if bilan["secteurs"] < cp["min_secteurs"]:
        manques.append(f"{bilan['secteurs']} secteurs (minimum visé : {cp['min_secteurs']})")
    if bilan["pays"] < cp["min_pays"]:
        manques.append(f"{bilan['pays']} pays (minimum visé : {cp['min_pays']})")
    bilan["respecte"] = not manques
    bilan["texte"] = (f"{bilan['nombre']} entreprises sur {bilan['secteurs']} secteurs et {bilan['pays']} pays "
                      f"(au plus {cp['max_par_secteur']} par secteur et {cp['max_par_pays']} par pays)"
                      + (" ; données insuffisantes : " + ", ".join(manques) if manques else ""))
    return choix, bilan


def panorama(lignes: list[dict], config: dict) -> dict:
    """Tour d'horizon par catégorie, top 5 diversifié et liste « À surveiller »."""
    cp = config["panorama"]
    seuil = config["verdicts"]["seuils"]["Renforcer"]
    # Listes par catégorie : par score, les lignes « à surveiller » (objection sérieuse, tendance en excès) après les autres
    par = {t: sorted((l for l in lignes if l["type"] == t and l.get("score") is not None), key=lambda l: (a_surveiller(l), -l["score"])) for t in CATEGORIES}
    ent, bilan = selection_entreprises(lignes, cp)
    # Top 5 : verdicts positifs ; d'abord une ligne par catégorie, puis les suivantes (au plus 2 par catégorie)
    # Top 5 : verdict positif, score au-dessus du seuil (pas seulement maintenu par l'hystérésis), aucune objection
    # sérieuse à lever ni tendance en excès (celles-là vont dans « À surveiller »)
    # Pays exclus : le backtest juge la note pays non prédictive (contexte économique seulement ; paris pays à part)
    positifs = sorted((l for l in lignes if l["type"] != "pays" and DIRECTION.get(l["verdict"]) == 1 and l.get("score") is not None and l["score"] >= seuil
                       and not (l.get("objection") or {}).get("serieuse") and not l.get("tendance_excessive")
                       and (l["type"] != "entreprises" or l in ent)), key=_cle_tri)
    top5, compte = [], {}
    for limite in (1, 2, 3):  # une ligne par catégorie d'abord, puis deux, puis trois en dernier recours
        for l in positifs:
            if len(top5) >= cp["top"]:
                break
            if l in top5 or compte.get(l["type"], 0) >= limite:
                continue
            top5.append(l)
            compte[l["type"]] = compte.get(l["type"], 0) + 1
    top5.sort(key=_cle_tri)
    ids_top = {l["id"] for l in top5}
    surveiller = []
    for l in sorted(lignes, key=lambda l: -(l.get("score") or 0)):
        if l["id"] in ids_top or l.get("score") is None or l["type"] == "pays":
            continue
        raison = None
        if DIRECTION.get(l["verdict"]) == 1 and l["score"] < seuil:
            raison = f"verdict « {l['verdict']} » maintenu par l'hystérésis, mais score repassé sous le seuil ({ent_(l['score'])}/100 pour {seuil})"
        elif l["verdict"] == "Neutre" and l["score"] >= seuil - cp["ecart_seuil"]:
            raison = f"proche du seuil « Renforcer » ({ent_(l['score'])}/100 pour un seuil de {seuil})"
            if l.get("en_attente"):
                raison += f", changement en attente vers « {l['en_attente']['vers']} »"
        elif DIRECTION.get(l["verdict"]) == 1 and (l.get("objection") or {}).get("serieuse"):
            raison = f"bien noté ({ent_(l['score'])}/100) mais objection à lever : {l['objection']['objection'][:220]}"
        elif DIRECTION.get(l["verdict"]) == 1 and l.get("tendance_excessive"):
            raison = (f"bien noté ({ent_(l['score'])}/100), tendance forte mais en excès : "
                      + " ; ".join(x.split(" : ")[0] for x in (l.get("suivi_tendance") or {}).get("exces") or []))
        elif l.get("plafond") and DIRECTION.get(l.get("verdict_brut")) == 1:
            raison = f"score de {ent_(l['score'])}/100, mais {l['plafond']}"
        if raison and sum(1 for x in surveiller if x["type"] == l["type"]) < cp["a_surveiller_par_type"]:
            surveiller.append({**resume_ligne(l), "raison": raison})
        if len(surveiller) >= cp["a_surveiller_max"]:
            break
    return {"top": [resume_ligne(l) for l in top5],
            "pays": [resume_ligne(l) for l in par["pays"][:cp["pays"]]],
            "matieres": [resume_ligne(l) for l in par["matieres"][:cp["matieres"]]],
            "secteurs": [resume_ligne(l) for l in secteurs_distincts(par["secteurs"], cp["secteurs"])],
            "or": resume_ligne(par["or"][0]) if par["or"] else None,
            "obligations": [resume_ligne(l) for l in par["obligations"]],
            "liquidites": [resume_ligne(l) for l in par["liquidites"]],
            "entreprises": [resume_ligne(l) for l in ent], "entreprises_bilan": bilan,
            "a_surveiller": surveiller}


def secteurs_distincts(lignes: list[dict], n: int) -> list[dict]:
    """Meilleurs secteurs (déjà triés par score), une seule zone par secteur GICS."""
    res, vus = [], set()
    for l in lignes:
        if l.get("secteur") in vus:
            continue
        vus.add(l.get("secteur"))
        res.append(l)
        if len(res) >= n:
            break
    return res


LIB_CAT = {"entreprises": "Entreprise", "matieres": "Matière première", "pays": "Pari pays"}


def ent_(x) -> str:
    return ent(x)


def _liste_courte(items: list[dict], n: int) -> str:
    return ", ".join(f"{x['nom']} ({x['verdict'].lower()}, {ent(x['score'])}/100{', à surveiller' if x.get('a_surveiller') else ''})" for x in items[:n])


def _noms(lignes: list[dict], n: int = 6) -> str:
    return ", ".join(f"{l['nom']} ({l['nb_combinaisons']} comb.)" if l.get("nb_combinaisons", 1) > 1 else l["nom"] for l in lignes[:n]) + (
        f" et {len(lignes) - n} autre(s)" if len(lignes) > n else "")


def briefing_regles(ctx: dict) -> dict:
    """Briefing par règles : seule la liste d'investissement (sélections du dernier recalibrage validé) est présentée ;
    les notes et verdicts issus du score, non prédictifs d'après le backtest, n'y figurent plus."""
    f = Faits()
    pal = ctx["palier"]
    mondial = ctx["risque_mondial"]
    phase = ctx["phase_monde"]
    li = ctx.get("liste") or {}
    lignes = li.get("lignes") or []
    par = {k: [l for l in lignes if l["categorie"] == k] for k in ("entreprises", "matieres", "pays")}
    i_pal = f.ajouter(f"Palier de risque mondial « {pal} » (score de stress {fr(mondial.get('score'), 0)}/100)", "agent risque")
    i_phase = f.ajouter(f"Phase du cycle mondial : « {phase or 'n. d.'} »", "agent macro")
    i_liste = f.ajouter(f"Liste d'investissement : {len(lignes)} ligne(s) (révisée le {date_fr(li.get('revise_le')) if li.get('revise_le') else 'n. d.'})", "chef d'orchestre")
    i_cat = {k: [f.ajouter(f"{LIB_CAT[k]} : {l['nom']}, retenue par {' ; '.join(l['combinaisons_libelles'])}", "chef d'orchestre (sélections du backtest)")
                 for l in xs] for k, xs in par.items()}
    fortes = [l for l in lignes if l.get("nb_combinaisons", 1) >= 2]
    mvts = [m for m in li.get("mouvements") or []]
    i_mvt = [f.ajouter(m["texte"], "chef d'orchestre") for m in mvts[:10]]
    vig = ctx["vigilance"]
    i_vig = [f.ajouter(v, "chef d'orchestre") for v in vig[:6]]
    essentiel = [
        {"texte": f"Risque mondial « {pal} » (stress {fr(mondial.get('score'), 0)}/100) ; cycle mondial en « {phase or 'n. d.'} » (contexte).", "faits": [i_pal, i_phase]},
        {"texte": f"Liste d'investissement : {len(lignes)} ligne(s) issues du dernier recalibrage validé, révisée une fois par mois"
                  + (f" (le {date_fr(li['revise_le'])})" if li.get("revise_le") else "") + ".", "faits": [i_liste]},
        {"texte": "Entreprises : " + (_noms(par["entreprises"]) or "aucune retenue") + ".", "faits": i_cat["entreprises"][:6]},
        {"texte": "Matières premières : " + (_noms(par["matieres"]) or "aucune retenue") + " ; paris pays : " + (_noms(par["pays"]) or "aucun") + ".",
         "faits": i_cat["matieres"][:6] + i_cat["pays"][:3]},
        {"texte": ("Convictions les plus fortes (2 ou 3 combinaisons) : " + _noms(fortes, 5) + ".") if fortes
         else "Aucune ligne retenue par plusieurs combinaisons : convictions faibles.", "faits": [i_liste]},
        {"texte": ("Entrées et sorties du mois : " + " ; ".join(m["texte"] for m in mvts[:4]) + ("…" if len(mvts) > 4 else "") + ".") if mvts
         else "Aucune entrée ni sortie ce mois-ci.", "faits": i_mvt[:4] or [i_liste]},
    ]
    return {"essentiel": essentiel, "vigilance": [{"texte": v, "faits": [i]} for v, i in zip(vig, i_vig)],
            "faits": f.liste, "faits_changements": i_mvt, "mode": "règles"}


# ------------------------------------------------------------------ Gemini

def _nombres(texte: str) -> set[str]:
    return {n.replace(",", ".").lstrip("0") or "0" for n in re.findall(r"\d+(?:[.,]\d+)?", (texte or "").replace(" ", "").replace(" ", ""))}


def valider_phrase(x, faits: dict) -> tuple[dict | None, str | None]:
    if not isinstance(x, dict) or not (x.get("texte") or "").strip():
        return None, "phrase vide"
    texte = x["texte"].strip()
    cites = [i for i in (x.get("faits") or []) if i in faits] + [i for i in re.findall(r"F\d+", texte) if i in faits]
    cites = list(dict.fromkeys(cites))
    if not cites:
        return None, "aucun fait cité"
    permis = set()
    for i in cites:
        permis |= _nombres(faits[i]["texte"])
    hors = [n for n in _nombres(re.sub(r"\[[^\]]*\]", "", texte)) if n not in permis]
    if hors:
        return None, f"chiffres absents des faits cités : {', '.join(hors[:4])}"
    return {"texte": re.sub(r"\s*\[(F\d+(?:\s*,\s*F\d+)*)\]", "", texte).strip(), "faits": cites}, None


def consigne(regles: dict, sc: dict) -> str:
    return (
        "Tu es le chef d'orchestre d'une plateforme personnelle de suivi économique. Rédige en français le briefing du jour, "
        "sur un ton froid et factuel, sans euphorie ni alarmisme, en distinguant les faits des interprétations. "
        "N'utilise QUE les faits fournis : chaque phrase cite au moins un fait par son id entre crochets, par exemple [F2], et ne contient "
        "aucun chiffre absent des faits cités. Signale une donnée manquante au lieu de l'inventer. "
        "« L'essentiel » ne présente QUE la liste d'investissement (sélections du backtest), jamais de note ni de verdict issus d'un score : "
        "1 : risque et cycle (contexte) ; 2 : la liste et sa révision mensuelle ; 3 : entreprises retenues ; 4 : matières premières et paris pays ; "
        "5 : convictions (nombre de combinaisons) ; 6 : entrées et sorties du mois.\n"
        "Réponds uniquement en JSON : {\"essentiel\": [{\"texte\": \"…\", \"faits\": [\"F1\"]}, … exactement 6 phrases], "
        "\"vigilance\": [{\"texte\": \"…\", \"faits\": [\"F7\"]}]}\n\n"
        + json.dumps({"faits": regles["faits"], "scenarios": sc}, ensure_ascii=False)
    )


def briefing_gemini(regles: dict, sc: dict, quotas, cfg: dict, cle: str, poster, rapport: dict) -> dict | None:
    from ..geopolitique import ia
    texte, modele = ia.appel_chaine(consigne(regles, sc), quotas, cfg, cle, poster, rapport)
    if texte is None:
        return None
    try:
        rep = json.loads(texte)
    except ValueError:
        rapport["rejets"].append("réponse JSON illisible")
        return None
    faits = {x["id"]: x for x in regles["faits"]}
    res = {"mode": "gemini", "modele": modele, "supprimees": []}
    for rub, mini in (("essentiel", 4), ("vigilance", 1)):
        ok = []
        for x in (rep.get(rub) or []) if isinstance(rep, dict) else []:
            v, raison = valider_phrase(x, faits)
            if v:
                ok.append(v)
            else:
                res["supprimees"].append(f"{rub} : {raison}")
        if len(ok) >= mini:
            res[rub] = ok[:6]
        else:
            res[rub] = regles[rub]
            res.setdefault("rubriques_regles", []).append(rub)
    rapport["reussites"] += 1
    rapport["rejets"] += res["supprimees"]
    return res


# ------------------------------------------------------------------ markdown

def briefing_markdown(b: dict) -> str:
    l = [f"# Briefing du chef d'orchestre — {date_fr(b['date'])}", "",
         f"Rédaction : {'Gemini (affirmations vérifiées contre les données sources)' if b['mode'] == 'gemini' else 'règles (' + (b.get('raison_regles') or 'n. d.') + ')'} · "
         f"palier de risque « {b['palier']} » · cycle mondial « {b.get('phase_monde') or 'n. d.'} »", "",
         "## L'essentiel", ""]
    l += [f"- {x['texte']}" for x in b["essentiel"]]
    li = b.get("liste") or {}
    l += ["", "## Où investir : la liste", "",
          (li.get("regle") or ""), "",
          "| Ligne | Catégorie | Combinaison(s) | Conviction | Backtest (écart / indice, gagnants) | Entrée | Ce qui la ferait sortir |",
          "|---|---|---|---|---|---|---|"]
    for x in li.get("lignes") or []:
        bt = " ; ".join(f"{fr(r.get('ecart_indice_pct'), 1, True)} pt/an, {ent(r.get('gagnants_pct'))} %" for r in x.get("backtest") or [])
        l.append(f"| {x['nom']} | {x['categorie']} | {' ; '.join(x['combinaisons_libelles'])} | {x['conviction']} ({x['nb_combinaisons']}) | {bt} | "
                 f"{date_fr(x['date_entree'])} | {x['sortie_si']} |")
    if not li.get("lignes"):
        l.append("| Aucune ligne | | | | | | |")
    l += ["", "## Entrées et sorties du mois", ""] + ([f"- {date_fr(m['date'])} · {m['texte']}" for m in b.get("mouvements") or []] or ["- Aucune."])
    l += ["", "## Points de vigilance", ""] + ([f"- {v['texte']}" for v in b["vigilance"]] or ["- Aucun."])
    for cle, nom in (("central", "Scénario central"), ("alternatif", "Scénario alternatif")):
        s = b["scenarios"][cle]
        l += ["", f"## {nom} : {s['titre']}", "", s["texte"], "", "Déclencheurs :", ""] + [f"- {d}" for d in s["declencheurs"]]
    l += ["", "## Agenda des 7 prochains jours", ""]
    l += [f"- {x['jour']} : {x['libelle']}{' (date indicative)' if x['indicative'] else ''}" for x in b["agenda"]] or ["- Rien de prévu dans les sources suivies."]
    l += ["", "## Ce qui pourrait me donner tort", ""] + [f"- {x}" for x in b["donner_tort"]]
    l += ["", "## Données", ""] + [f"- {x}" for x in b["donnees"]]
    l += ["", "## Faits utilisés", ""] + [f"- [{x['id']}] {x['texte']} ({x['source']})" for x in b["faits"]]
    l += ["", f"_{b['mention']}_", ""]
    return "\n".join(l)


# ------------------------------------------------------------------ alertes

def alertes(signaux: dict[str, list[dict]], revues: list[dict], changements: list[dict], maintenant: datetime, config: dict, tickers_appli: set,
            admissible=None) -> list[dict]:
    """`admissible(agent, signal)` : (bool, raison) — écarte les signaux hors univers, fonds, holdings, déclarations internes."""
    ca = config["alertes"]
    lim = (maintenant - timedelta(hours=ca["fenetre_heures"])).date().isoformat()
    ajust = {r.get("id"): r for r in revues or []}
    cands = []
    for agent, liste in signaux.items():
        for s in liste:
            if (s.get("date") or "") < lim:
                continue
            if admissible and not admissible(agent, s)[0]:
                continue
            imp = ca["importances"].get(s.get("importance"), 1)
            r = ajust.get(f"{agent}|{s.get('type')}|{s.get('cle')}|{s.get('date')}")
            note = None
            if r and r.get("specifique"):
                if r.get("ajustement") == "signal fragile":
                    continue
                if r.get("ajustement") == "abaisser":
                    imp -= 1
                    note = f"Contradicteur : {r.get('objection')}"
            if imp < ca["importance_min"]:
                continue
            cands.append((imp, s.get("date") or "", agent, s, note))
    for c in changements:
        if c.get("important"):
            cands.append((2, c["date"], "chef", {"type": c.get("type", "verdict_chef"), "cle": c["id"], "titre": c["texte"], "explication": c.get("explication", ""),
                                                  "pays": [c["pays"]] if c.get("pays") else []}, None))
    cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
    # Diversité : d'abord un signal par agent et par type, puis au plus deux par agent ; titres en double écartés
    choisis, vus_titres = [], set()
    for passe in (1, 2):
        par_cle = {}
        for c in choisis:
            par_cle[(c[2], c[3].get("type"))] = par_cle.get((c[2], c[3].get("type")), 0) + 1
            par_cle[c[2]] = par_cle.get(c[2], 0) + 1
        for c in cands:
            if len(choisis) >= ca["nombre"] or c in choisis:
                continue
            imp, d, agent, s, note = c
            mots = frozenset(re.findall(r"\w{5,}", (s.get("titre") or "").lower()))
            if any(len(mots & v) >= max(2, len(mots) // 2) for v in vus_titres):
                continue
            if (passe == 1 and par_cle.get((agent, s.get("type")), 0) >= 1) or par_cle.get(agent, 0) >= 2:
                continue
            choisis.append(c)
            vus_titres.add(mots)
            par_cle[(agent, s.get("type"))] = par_cle.get((agent, s.get("type")), 0) + 1
            par_cle[agent] = par_cle.get(agent, 0) + 1
    choisis.sort(key=lambda x: (x[0], x[1]), reverse=True)
    res = []
    for imp, d, agent, s, note in choisis:
        pays = (s.get("pays") or [None])[0] if isinstance(s.get("pays"), list) else None
        cle = s.get("cle")
        if agent in ("pays", "risque", "donnees_alternatives") and cle and len(str(cle)) == 2:
            pays = pays or cle
        route = None
        if agent == "matieres_premieres":
            route = {"type": "matieres", "id": cle}
        elif agent in ("entreprises", "inities") and cle in tickers_appli:
            route = {"type": "entreprise", "id": cle}
        elif agent == "geopolitique" and not pays:
            route = {"type": "geopolitique"}
        elif agent == "risque" and not pays:
            route = {"type": "risque"}
        elif agent == "macro":
            route = {"type": "macro"}
        elif agent == "chef":
            route = {"type": "investir", "id": f"o-{cle}"}
        elif not pays:
            route = {"type": "investir"}
        texte = (s.get("explication") or "")[:300]
        if note:
            texte += f" {note[:200]}"
        res.append({"id": f"{agent}-{s.get('type')}-{cle}-{d}", "rang": len(res) + 1, "heure": date_fr(d)[:5], "date": d, "agent": agent,
                    "pays": pays, "niveau": ca["niveau_par_type"].get(s.get("type"), "neutre"),
                    "importance": "forte" if imp >= 3 else "moyenne", "titre": s.get("titre"), "texte": texte.strip(), "route": route})
        if len(res) >= ca["nombre"]:
            break
    return res


# ------------------------------------------------------------------ revue hebdomadaire

def hebdo_markdown(jour: str, historique: dict[str, dict], lignes: list[dict], allocation: dict, fia: dict, suivi_cfg: dict) -> str:
    """historique : {AAAA-MM-JJ: données du jour (data/historique/chef)} sur 7 jours."""
    dates = sorted(historique)
    l = [f"# Chef d'orchestre — revue de la semaine au {date_fr(jour)}", "",
         "Bilan factuel : verdicts modifiés, performance mesurée des verdicts passés, évolution de l'allocation modèle.", "",
         "## Verdicts modifiés dans la semaine", ""]
    chg = []
    for d in dates:
        chg += [f"- {date_fr(d)} : {c}" for c in historique[d].get("changements", [])]
    l += chg or ["- Aucun."]
    l += ["", "## Verdicts actuels (positifs)", ""]
    pos = [x for x in lignes if DIRECTION.get(x["verdict"]) == 1]
    l += [f"- {libelle_ligne(x)}" for x in sorted(pos, key=lambda x: -x["score"])[:15]] or ["- Aucun verdict positif."]
    l += ["", "## Performance des verdicts", ""]
    for m in suivi_cfg["horizons_mois"]:
        lignes_m = []
        for v, b in (fia.get("par_verdict") or {}).items():
            x = b.get(str(m)) or {}
            if x.get("n"):
                lignes_m.append(f"{v} : {x['taux_pct']} % de réussite sur {x['n']} ({fr(x['relative_moyenne_pct'], 1, True)} pt contre l'indice)")
        l.append(f"- {m} mois : " + ("; ".join(lignes_m) if lignes_m else "pas encore de verdict arrivé à échéance"))
    cal = (fia.get("calibration") or {}).get("3") or {}
    if cal:
        l.append(f"- Calibration à 3 mois : {cal.get('texte')}")
    l += ["", "## Allocation modèle (évolutions sur la semaine)", ""]
    debut = historique[dates[0]].get("allocation") if dates else None
    for cle, p in (allocation.get("profils") or {}).items():
        avant = (debut or {}).get(cle) or {}
        diff = []
        for c, v in p["classes"].items():
            a = avant.get(c)
            diff.append(f"{c} {fr(v, 1)} %" + (f" ({fr(v - a, 1, True)} pt)" if a is not None and abs(v - a) >= 0.1 else ""))
        l.append(f"- {p['libelle']} : " + ", ".join(diff))
    l += ["", "_Avis indicatif généré automatiquement, sans prise en compte d'un profil ou d'une situation personnelle._", ""]
    return "\n".join(l)
