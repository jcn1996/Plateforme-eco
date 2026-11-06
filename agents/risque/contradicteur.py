"""
Rôle de contradicteur : pour chaque signal d'importance moyenne ou forte des autres agents
(data/signaux/*.json), l'agent risque cherche les données qui le contredisent ou le nuancent.

Chaque revue contient une « objection » chiffrée et sourcée (faits numérotés, avec leur source)
et un ajustement de confiance proposé : « maintenir », « abaisser » ou « signal fragile ».

Par défaut, les objections sont écrites par des règles (réaction des marchés depuis le signal,
alternance des signaux, environnement de risque, risque du pays). Si Gemini est disponible
(budget d'appels propre à l'agent risque, en config), il rédige l'objection à partir des mêmes
faits ; une réponse qui cite un chiffre absent des faits, ou un ajustement inconnu, est rejetée
et remplacée par la version par règles.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

from ..commun.journal import journal
from ..commun.sortie import lire_json
from . import calculs as C

LOG = journal("agent-risque")
AJUSTEMENTS = ("maintenir", "abaisser", "signal fragile")
NEGATIFS = re.compile(r"ralentissement|récession|recession|contraction|stagflation|repli", re.I)
POSITIFS = re.compile(r"expansion|reprise|accélération|acceleration", re.I)


def id_signal(fichier: str, s: dict) -> str:
    return f"{fichier.removesuffix('.json')}|{s.get('type')}|{s.get('cle')}|{s.get('date')}"


def lire_signaux(dossier, config: dict, aujourdhui) -> dict[str, list[dict]]:
    """{fichier: [signaux]} des autres agents (risque.json et revues.json exclus)."""
    cfg = config["contradicteur"]
    res = {}
    for chemin in sorted(dossier.glob("*.json")) if dossier.exists() else []:
        if chemin.name in cfg["ignores"]:
            continue
        res[chemin.name] = ((lire_json(chemin) or {}).get("donnees") or [])
    return res


def a_revoir(signaux: dict[str, list[dict]], deja: set, config: dict, aujourdhui) -> list[tuple[str, dict]]:
    cfg = config["contradicteur"]
    limite = (C.jour(aujourdhui) - timedelta(days=cfg["fenetre_jours"])).isoformat()
    res = []
    for fichier, liste in signaux.items():
        for s in liste:
            if s.get("importance") in cfg["importances"] and (s.get("date") or "") >= limite and id_signal(fichier, s) not in deja:
                res.append((fichier, s))
    return sorted(res, key=lambda x: (x[1].get("date") or "", x[0]), reverse=True)


# ------------------------------------------------------------------ faits

class Faits:
    def __init__(self):
        self.liste = []

    def ajouter(self, texte: str, source: str) -> str:
        i = f"F{len(self.liste) + 1}"
        self.liste.append({"id": i, "texte": texte, "source": source})
        return i


def reaction(serie, date_signal: str):
    """(valeur au moment du signal, dernière valeur, date) ; le point de départ est la dernière
    clôture avant le jour du signal."""
    if not serie:
        return None
    avant = C.valeur_a(serie, C.jour(date_signal) - timedelta(days=1))
    if avant is None or serie[-1][0] < date_signal:
        return None
    return avant, serie[-1]


def faits_communs(f: Faits, ctx: dict, date_signal: str) -> dict:
    m = ctx["mondial"]
    res = {}
    res["palier"] = f.ajouter(f"Palier de risque mondial « {m['palier']} » (score de stress {C.fr(m['score'], 0)}/100)", "agent risque (data/risque.json)")
    vix = ctx["indicateurs"].get("vix") or {}
    if vix.get("disponible"):
        r = reaction(vix["_serie"], date_signal)
        texte = f"VIX à {C.fr(vix['valeur'], 1)} (percentile {C.fr(vix['percentile'], 0)} sur {C.fr(vix['historique_annees'], 0)} ans)"
        res["vix_variation"] = None
        if r:
            res["vix_variation"] = round(r[1][1] - r[0][1], 2)
            texte += f", {C.fr(res['vix_variation'], 1, True)} pts depuis la veille du signal ({C.date_fr(r[0][0])})"
        res["vix"] = f.ajouter(texte, vix["source"])
    hy = ctx["indicateurs"].get("hy_us") or {}
    if hy.get("disponible"):
        serie = hy["_serie"]
        v20 = round(serie[-1][1] - serie[-21][1], 2) if len(serie) > 21 else None
        res["hy_variation"] = v20
        res["hy"] = f.ajouter(f"Écart high yield américain à {C.fr(hy['valeur'], 2)} pt"
                              + (f", {C.fr(v20, 2, True)} pt sur 20 séances" if v20 is not None else ""), hy["source"])
    return res


def faits_pays(f: Faits, ctx: dict, codes: list[str], date_signal: str) -> dict:
    res = {"etf": [], "risque": []}
    for code in codes[:3]:
        p = ctx["pays_config"].get(code)
        if not p:
            continue
        serie = ctx["cours"].get(p.get("etf"))
        r = reaction(serie, date_signal)
        if r:
            perf = round(100 * (r[1][1] / r[0][1] - 1), 2)
            res["etf"].append((code, perf, f.ajouter(f"ETF {p['etf']} ({p['nom']}) : {C.fr(perf, 1, True)} % depuis la veille du signal", f"Yahoo Finance via yfinance, {p['etf']}")))
        s = ctx["pays_scores"].get(code) or {}
        if s.get("score") is not None:
            res["risque"].append((code, s["score"], f.ajouter(f"{p['nom']} : score de risque de l'agent risque {C.fr(s['score'], 0)}/100", "agent risque (data/risque.json)")))
    return res


# ------------------------------------------------------------------ règles

def _cite(*ids):
    return " [" + ", ".join(i for i in ids if i) + "]"


def regles(fichier: str, s: dict, ctx: dict, config: dict) -> dict:
    cfg = config["contradicteur"]
    f = Faits()
    d = s.get("date") or ctx["aujourdhui"]
    com = faits_communs(f, ctx, d)
    palier = ctx["mondial"]["palier"]
    agent = fichier.removesuffix(".json")
    t = s.get("type") or ""
    ajust, objection = "maintenir", None

    if agent == "geopolitique":
        fp = faits_pays(f, ctx, s.get("pays") or [], d)
        nsrc = len(s.get("sources") or [])
        fsrc = f.ajouter(f"{nsrc} source{'s' if nsrc > 1 else ''} citée{'s' if nsrc > 1 else ''} par le signal", "data/signaux/geopolitique.json")
        dvix = com.get("vix_variation")
        pire = min(fp["etf"], key=lambda x: x[1]) if fp["etf"] else None
        if nsrc < 2:
            ajust = "signal fragile"
            objection = f"Le signal ne repose que sur {nsrc} source{_cite(fsrc)}."
        elif dvix is None and not pire:
            objection = "Trop tôt pour mesurer la réaction des marchés : aucune séance n'a encore suivi le signal." + _cite(com.get("palier"))
        elif (dvix is None or dvix < cfg["reaction_vix_pts"]) and (pire is None or pire[1] > cfg["reaction_etf_pct"]):
            ajust = "abaisser"
            morceaux = []
            if dvix is not None:
                morceaux.append(f"le VIX a varié de {C.fr(dvix, 1, True)} pts{_cite(com.get('vix'))}")
            if pire:
                morceaux.append(f"l'ETF le plus touché varie de {C.fr(pire[1], 1, True)} %{_cite(pire[2])}")
            objection = ("Les marchés ne confirment pas l'impact financier : " + " et ".join(morceaux)
                         + f" depuis le signal ; l'environnement reste au palier « {palier} »{_cite(com.get('palier'))}.")
        else:
            morceaux = []
            if dvix is not None:
                morceaux.append(f"VIX {C.fr(dvix, 1, True)} pts{_cite(com.get('vix'))}")
            if pire:
                morceaux.append(f"ETF le plus touché {C.fr(pire[1], 1, True)} %{_cite(pire[2])}")
            objection = "Les marchés réagissent dans le sens du signal (" + ", ".join(morceaux) + ") : pas d'objection sur le fond, l'ampleur reste à suivre."

    elif agent == "macro" and t == "changement_de_phase":
        cle = s.get("cle")
        debut = (C.jour(d) - timedelta(days=cfg["alternance_jours"])).isoformat()
        changements = sorted({x.get("date") for x in ctx["signaux"].get(fichier, [])
                              if x.get("type") == t and x.get("cle") == cle and debut <= (x.get("date") or "") <= d})
        falt = f.ajouter(f"{len(changements)} changement(s) de phase pour « {cle} » en {cfg['alternance_jours']} jours ({', '.join(C.date_fr(x) for x in changements)})",
                         "data/signaux/macro.json")
        m = re.search(r"([−+-]?\d+(?:,\d+)?) pt sur 3 mois", s.get("explication") or "")
        pente = float(m.group(1).replace("−", "-").replace(",", ".")) if m else None
        fpente = f.ajouter(f"Indicateur avancé : {m.group(1)} pt sur 3 mois (explication du signal)", "data/signaux/macro.json") if m else None
        titre = s.get("titre") or ""
        vers = titre.split("à «")[-1] if "à «" in titre else titre
        if len(changements) >= 2:
            ajust = "signal fragile"
            objection = (f"La phase a changé {len(changements)} fois en {cfg['alternance_jours']} jours{_cite(falt)}"
                         + (f", sur une pente de l'indicateur avancé de seulement {m.group(1)} pt sur 3 mois{_cite(fpente)}" if pente is not None and abs(pente) < 0.1 else "")
                         + " : le signal alterne autour d'un seuil.")
        elif NEGATIFS.search(vers) and palier == config["paliers"][0] and (com.get("hy_variation") or 0) <= 0:
            ajust = "abaisser"
            objection = (f"Les marchés financiers ne reflètent pas ce ralentissement : palier « {palier} »{_cite(com.get('palier'))}, "
                         f"écart high yield américain stable ou en baisse{_cite(com.get('hy'))}.")
        elif POSITIFS.search(vers) and palier in config["paliers"][2:]:
            ajust = "abaisser"
            objection = f"Une amélioration du cycle est annoncée alors que le stress financier est au palier « {palier} »{_cite(com.get('palier'))}."
        else:
            objection = ("Pas de contradiction dans les données de marché" + _cite(com.get("palier"), com.get("hy"))
                         + (f" ; nuance : pente de l'indicateur avancé faible ({m.group(1)} pt sur 3 mois){_cite(fpente)}" if pente is not None and abs(pente) < 0.1 else "") + ".")
            if pente is not None and abs(pente) < 0.1:
                ajust = "abaisser"

    elif agent == "entreprises" and t == "nouvelle_pepite":
        m = re.search(r"momentum 12 mois : ([−+-]?\d+(?:,\d+)?) %", s.get("explication") or "")
        momentum = float(m.group(1).replace("−", "-").replace(",", ".")) if m else None
        fmom = f.ajouter(f"Momentum sur 12 mois de {m.group(1)} % (explication du signal)", "data/signaux/entreprises.json") if m else None
        code = ctx["entreprises_pays"].get(s.get("cle"))
        fp = faits_pays(f, ctx, [code] if code else [], d)
        risque_pays = fp["risque"][0] if fp["risque"] else None
        raisons = []
        if momentum is not None and momentum < cfg["momentum_pepite_min"]:
            raisons.append(f"le cours a baissé de {C.fr(abs(momentum), 1)} % sur 12 mois{_cite(fmom)} : le marché ne valide pas la qualité affichée")
        if palier in config["paliers"][2:]:
            raisons.append(f"le stress financier est au palier « {palier} »{_cite(com.get('palier'))}, défavorable aux actifs risqués")
        if risque_pays and risque_pays[1] >= config["pays"]["seuil_eleve"]:
            raisons.append(f"le pays de l'entreprise a un score de risque de {C.fr(risque_pays[1], 0)}/100{_cite(risque_pays[2])}")
        if raisons:
            ajust = "abaisser"
            objection = "Nuance : " + " ; ".join(raisons) + "."
        else:
            objection = (f"Pas de contradiction dans l'environnement de risque : palier « {palier} »{_cite(com.get('palier'))}"
                         + (f", momentum sur 12 mois de {m.group(1)} %{_cite(fmom)}" if m else "")
                         + (f", score de risque du pays de {C.fr(risque_pays[1], 0)}/100{_cite(risque_pays[2])}" if risque_pays else "") + ".")

    else:
        fp = faits_pays(f, ctx, s.get("pays") or ([s["cle"]] if s.get("cle") in ctx["pays_config"] else []), d)
        eleves = [r for r in fp["risque"] if r[1] >= config["pays"]["seuil_eleve"]]
        objection = ("Contexte de risque : palier « " + palier + " »" + _cite(com.get("palier"), com.get("vix"))
                     + ("" if not eleves else f" ; score de risque élevé pour {', '.join(ctx['pays_config'][c]['nom'] for c, _, _ in eleves)}"
                        + _cite(*[x[2] for x in eleves])) + " : rien ne contredit ce signal dans les données suivies.")

    nb_chiffres = sum(1 for x in f.liste if re.search(r"\d", x["texte"]))
    return {"objection": objection, "faits": f.liste, "ajustement": ajust, "methode": "règles",
            "confiance": "moyen" if nb_chiffres >= 3 else "faible"}


# ------------------------------------------------------------------ Gemini

def consigne(lot: list[tuple[str, dict, dict]]) -> str:
    blocs = []
    for i, (fichier, s, r) in enumerate(lot, 1):
        blocs.append({"id": f"S{i}", "agent": fichier.removesuffix(".json"), "type": s.get("type"), "date": s.get("date"),
                      "titre": s.get("titre"), "explication": s.get("explication"),
                      "faits": [{"id": x["id"], "texte": x["texte"], "source": x["source"]} for x in r["faits"]],
                      "ajustement_par_regles": r["ajustement"]})
    return (
        "Tu es l'agent risque d'une plateforme de suivi économique, dans un rôle de contradicteur. Pour chaque signal ci-dessous, "
        "écris en français une objection froide et factuelle (une ou deux phrases, sans alarmisme) qui contredit ou nuance le signal, "
        "en n'utilisant QUE les faits fournis : chaque chiffre de l'objection doit figurer dans un fait cité, et tu cites les faits par leur id "
        "entre crochets, par exemple [F2]. Si rien ne contredit le signal, dis-le. Propose un ajustement de confiance parmi "
        "« maintenir », « abaisser », « signal fragile ».\n"
        "Réponds uniquement en JSON : {\"revues\": [{\"id\": \"S1\", \"objection\": \"…\", \"faits\": [\"F1\"], \"ajustement\": \"maintenir\"}]}\n\n"
        + json.dumps(blocs, ensure_ascii=False)
    )


def _nombres(texte: str) -> set[str]:
    return {n.replace(",", ".").lstrip("0") or "0" for n in re.findall(r"\d+(?:[.,]\d+)?", texte or "")}


def valider(brut: dict, s: dict, r: dict) -> tuple[dict | None, str | None]:
    if not isinstance(brut, dict):
        return None, "format"
    objection = (brut.get("objection") or "").strip()
    ajust = brut.get("ajustement")
    if not objection or ajust not in AJUSTEMENTS:
        return None, "objection vide ou ajustement inconnu"
    par_id = {x["id"]: x for x in r["faits"]}
    cites = [i for i in (brut.get("faits") or []) if i in par_id] + [i for i in re.findall(r"F\d+", objection) if i in par_id]
    cites = list(dict.fromkeys(cites))
    if not cites:
        return None, "aucun fait cité"
    permis = set()
    for i in cites:
        permis |= _nombres(par_id[i]["texte"])
    permis |= _nombres(s.get("titre")) | _nombres(s.get("explication"))
    hors = [n for n in _nombres(re.sub(r"\[[^\]]*\]", "", objection)) if n not in permis]
    if hors:
        return None, f"chiffres absents des faits : {', '.join(hors[:4])}"
    return {"objection": objection, "faits": r["faits"], "faits_cites": cites, "ajustement": ajust, "methode": "gemini",
            "confiance": r["confiance"]}, None


def rediger_gemini(lot, quotas, cfg: dict, cle: str, poster, rapport: dict) -> dict[int, dict]:
    from ..geopolitique import ia
    texte, modele = ia.appel_chaine(consigne(lot), quotas, cfg, cle, poster, rapport)
    if texte is None:
        return {}
    try:
        reponse = json.loads(texte)
    except ValueError:
        rapport["rejets"].append("réponse JSON illisible")
        return {}
    res = {}
    for x in (reponse.get("revues") or []) if isinstance(reponse, dict) else []:
        m = re.fullmatch(r"S(\d+)", str(x.get("id", "")))
        if not m or not 1 <= int(m.group(1)) <= len(lot):
            continue
        k = int(m.group(1)) - 1
        v, raison = valider(x, lot[k][1], lot[k][2])
        if v:
            res[k] = {**v, "modele": modele}
            rapport["reussites"] += 1
        else:
            rapport["rejets"].append(f"{id_signal(lot[k][0], lot[k][1])} : {raison}")
    return res


def revoir(signaux: dict[str, list[dict]], existantes: list[dict], ctx: dict, config: dict, etat: dict,
           cle_gemini: str | None, poster=None, horloge=None, dormir=None) -> tuple[list[dict], dict]:
    """Nouvelles revues (signaux pas encore revus) et compte rendu (Gemini)."""
    import time
    from ..geopolitique import ia
    deja = {r["id"] for r in existantes}
    candidats = a_revoir(signaux, deja, config, ctx["aujourdhui"])[:config["contradicteur"]["revues_max_par_execution"]]
    rapport = {"cle": bool(cle_gemini), "appels": 0, "reussites": 0, "rejets": [], "erreurs": [], "quota_atteint": False,
               "candidats": len(candidats)}
    prepares = [(fichier, s, regles(fichier, s, ctx, config)) for fichier, s in candidats]
    redige = {}
    cfg = config["gemini"]
    quotas = ia.Quotas(etat, cfg, horloge=horloge, dormir=dormir or time.sleep)
    if cle_gemini and prepares:
        n = cfg["signaux_par_appel"]
        for k in range(0, len(prepares), n):
            if quotas.appels_execution() >= cfg["appels_max_par_execution"]:
                break
            lot = prepares[k:k + n]
            for j, v in rediger_gemini(lot, quotas, cfg, cle_gemini, poster, rapport).items():
                redige[k + j] = v
    rapport["quota"] = quotas.resume()
    revues = []
    for k, (fichier, s, r) in enumerate(prepares):
        v = redige.get(k, r)
        revues.append({"id": id_signal(fichier, s), "revu_le": ctx["maintenant_iso"],
                       "signal": {"agent": fichier.removesuffix(".json"), "type": s.get("type"), "cle": s.get("cle"), "date": s.get("date"),
                                  "importance": s.get("importance"), "titre": s.get("titre")},
                       **v})
    return revues, rapport
