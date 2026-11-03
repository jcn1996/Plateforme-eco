"""
Agent géopolitique : événements géopolitiques et impact possible sur les marchés.

Étapes (toutes les heures, via le planificateur) :
1. collecte : GDELT (API DOC 2.0 par thème, fichiers d'événements géolocalisés à 15 min),
   Federal Register, OFAC, flux officiels (Maison-Blanche, Élysée, Commission et Conseil de l'UE,
   BRI), presse internationale (RSS), indices GPR (Caldara et Iacoviello) et EPU (FRED) ;
   une source en panne n'arrête pas l'agent ;
2. regroupement des articles par événement (evenements.py), gardés d'une heure à l'autre ;
3. analyse des événements significatifs par Gemini, dans la limite des quotas gratuits et avec
   contrôle des sources (ia.py) ; sans Gemini, version sans IA signalée ;
4. score de risque /100 par pays suivi et variation sur 7 jours (score.py) ;
5. écrit data/geopolitique.json, data/signaux/geopolitique.json,
   data/historique/geopolitique/AAAA-MM-JJ.json, l'état data/geopolitique/etat.json, le journal
   data/journal/agent-geopolitique.json (santé) et, une fois par jour après 6 h UTC (mode
   « quotidien » à 6 h), la synthèse data/recap/geopolitique-AAAA-MM-JJ.md.

Règles de conduite et méthode : agents/geopolitique/regles.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..commun import sante
from ..commun.journal import journal
from ..commun.sortie import ecrire_json, enveloppe, lire_json
from . import evenements as E
from . import ia
from . import score as S
from .sources import FournisseurReel, FournisseurTest

LOG = journal("agent-geopolitique")
VERSION_AGENT = "1.0"
DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
WORKFLOW = "agent-geopolitique.yml"
HEURE_SYNTHESE = 6  # UTC


def charger_config() -> dict:
    return json.loads((DOSSIER / "config.json").read_text(encoding="utf-8"))


def noms_pays(config: dict) -> dict:
    pays = json.loads((RACINE / "agents" / "pays" / "config.json").read_text(encoding="utf-8"))["pays"]
    noms = {k: v["nom"] for k, v in pays.items()}
    noms.update({k: v["nom"] for k, v in config["autres_pays"].items() if not k.startswith("_")})
    return noms


def _recent(date_iso: str | None, maintenant: datetime, heures: float) -> bool:
    if not date_iso:
        return False
    t = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
    return maintenant - timedelta(hours=heures) <= t <= maintenant + timedelta(hours=2)


# ------------------------------------------------------------------ collecte

def requetes_groupees(requetes: dict, longueur_max: int) -> list[str]:
    """Les thèmes regroupés en quelques requêtes (a OR b OR c…) d'au plus `longueur_max` caractères :
    GDELT refuse une requête trop longue (« Your query was too short or too long »)."""
    termes = []
    for r in requetes.values():
        termes += [t.strip() for t in r.strip().strip("()").split(" OR ") if t.strip()]
    groupes, courant = [], []
    for terme in dict.fromkeys(termes):
        if courant and len(" OR ".join(courant + [terme])) + 2 > longueur_max:
            groupes.append(courant)
            courant = []
        courant.append(terme)
    if courant:
        groupes.append(courant)
    return ["(" + " OR ".join(g) + ")" for g in groupes]


def gdelt_doc(f, config: dict, articles: list[dict], maintenant: datetime, garde: float) -> tuple[int, str, str]:
    """Requête groupée d'abord (une requête au lieu de six : moins de refus 429), puis, si GDELT la
    refuse pour une autre raison que la limite de débit, une requête par thème.
    Renvoie (articles retenus, détail, état de la source)."""
    g = config["gdelt"]
    n = 0
    if g.get("secondaire"):
        # Source secondaire : une seule requête groupée, un seul essai (limite de débit de GDELT)
        def garder(liste):
            nonlocal n
            for a in liste:
                if _recent(a["date"], maintenant, garde):
                    articles.append({**a, "indice": None, "source": "GDELT DOC 2.0", "officiel": False})
                    n += 1
        try:
            garder(f.gdelt_doc("groupe 1/1", g["requete_secondaire"], g["articles_max_requete_groupee"]))
            return n, "source secondaire : 1 requête groupée", "ok"
        except Exception as e:  # noqa: BLE001
            return 0, f"source secondaire (information) : {str(e)[:160]}", "échec"

    def ajouter(liste, indice):
        nonlocal n
        for a in liste:
            if _recent(a["date"], maintenant, garde):
                articles.append({**a, "indice": indice, "source": "GDELT DOC 2.0", "officiel": False})
                n += 1

    if g.get("requete_groupee"):
        groupes = requetes_groupees(g["requetes"], g["longueur_max_requete"])
        ok, echecs = 0, []
        for k, requete in enumerate(groupes, 1):
            try:
                ajouter(f.gdelt_doc(f"groupe {k}/{len(groupes)}", requete, g["articles_max_requete_groupee"]), None)
                ok += 1
            except Exception as e:  # noqa: BLE001
                texte = str(e)
                echecs.append(f"groupe {k} : {texte[:120]}")
                LOG.warning("GDELT DOC, groupe %d/%d : %s", k, len(groupes), texte[:200])
                if "429" in texte or "budget" in texte:  # limite de débit : les suivantes échoueraient aussi
                    break
        if ok or not echecs or any("429" in x or "budget" in x for x in echecs):
            detail = f"{ok}/{len(groupes)} requêtes groupées" + (f" ; échecs : {'; '.join(echecs)[:220]}" if echecs else "")
            return n, detail, "ok" if ok == len(groupes) else "partielle" if ok else "échec"
    ok, echecs, consecutifs = 0, [], 0
    for cat, requete in g["requetes"].items():
        if consecutifs >= 2:  # limite de débit : inutile d'insister (durée de l'exécution bornée)
            echecs.append(f"{cat} : non tentée (deux échecs consécutifs)")
            continue
        try:
            ajouter(f.gdelt_doc(cat, requete), cat)
            ok += 1
            consecutifs = 0
        except Exception as e:  # noqa: BLE001 - une requête en échec n'arrête pas les autres
            consecutifs += 1
            echecs.append(f"{cat} : {str(e)[:90]}")
    total = len(g["requetes"])
    detail = f"{ok}/{total} requêtes par thème" + (f" ; échecs : {'; '.join(echecs)[:220]}" if echecs else "")
    return n, detail, "ok" if ok == total else "partielle" if ok else "échec"

def collecter(f, config: dict, etat: dict, maintenant: datetime, mode: str) -> tuple[list[dict], dict]:
    """Renvoie (articles bruts, états des sources {cle: {nom, etat, detail, groupe}})."""
    articles, etats = [], {}
    garde_media, garde_off = config["articles_garde_heures"], 24 * config["officiel_garde_jours"]

    def noter(cle, nom, groupe, etat_s, detail=None):
        etats[cle] = {"nom": nom, "groupe": groupe, "etat": etat_s, "detail": detail}

    # GDELT, API DOC 2.0
    n, detail, etat_doc = gdelt_doc(f, config, articles, maintenant, garde_media)
    noter("gdelt_doc", "GDELT, API DOC 2.0 (articles par thème)", "presse", etat_doc, f"{n} articles ; {detail}")
    if config["gdelt"].get("secondaire"):
        etats["gdelt_doc"]["secondaire"] = True

    # GDELT, fichiers d'événements à 15 minutes (géolocalisés) : tonalité et volume par pays
    fips = {p["fips"] for p in config["pays"].values()}
    try:
        r = f.gdelt_evenements(fips, config["gdelt"]["fichiers_evenements_par_execution"])
        vus = set(etat.get("gdelt_vus", []))
        nouveaux = [h for h in r["horodatages"] if h not in vus]
        if nouveaux:
            # Les fichiers lus pour la première fois s'ajoutent aux agrégats du jour (sans double compte)
            jour = maintenant.date().isoformat()
            jours = etat.setdefault("gdelt_jours", {})
            cible = jours.setdefault(jour, {})
            part = len(nouveaux) / len(r["horodatages"])
            for code, a in r["pays"].items():
                c = cible.setdefault(code, {"evenements": 0, "articles": 0, "ton_pondere": 0.0, "conflits": 0})
                for k in c:
                    c[k] = round(c[k] + a[k] * part, 3)
            fichiers = etat.setdefault("gdelt_fichiers_par_jour", {})
            fichiers[jour] = fichiers.get(jour, 0) + len(nouveaux)
            etat["gdelt_vus"] = (list(etat.get("gdelt_vus", [])) + nouveaux)[-300:]
        noter("gdelt_evenements", "GDELT 2.0, fichiers d'événements géolocalisés (15 min)", "tonalite", "ok",
              f"{len(r['horodatages'])} fichiers ({len(nouveaux)} nouveaux), {len(r['pays'])} pays suivis présents")
    except Exception as e:  # noqa: BLE001
        noter("gdelt_evenements", "GDELT 2.0, fichiers d'événements géolocalisés (15 min)", "tonalite", "échec", str(e)[:200])

    # Federal Register : décrets présidentiels et mesures commerciales et de sanctions
    try:
        depuis = (maintenant - timedelta(days=config["federal_register"]["jours"])).date().isoformat()
        docs = f.federal_register(config["federal_register"]["agences"], depuis)
        for d in docs:
            if _recent(d["date"], maintenant, garde_off):
                ofac = any("Foreign Assets" in a for a in d.get("agences", []))
                articles.append({**d, "origine": "officiel", "source": "Federal Register", "officiel": True, "langue": "en",
                                 "categorie_par_defaut": "sanctions" if ofac else None})
        noter("federal_register", "Federal Register (API)", "officiel", "ok", f"{len(docs)} documents")
    except Exception as e:  # noqa: BLE001
        noter("federal_register", "Federal Register (API)", "officiel", "échec", str(e)[:200])

    # OFAC : actions récentes (sanctions américaines)
    try:
        actions = f.ofac()
        for a in actions:
            if _recent(a["date"], maintenant, garde_off):
                articles.append({**a, "origine": "officiel", "source": "OFAC", "officiel": True, "langue": "en",
                                 "categorie_par_defaut": "sanctions"})
        noter("ofac", "OFAC, actions récentes (Trésor américain)", "officiel", "ok" if actions else "partielle", f"{len(actions)} actions listées")
    except Exception as e:  # noqa: BLE001
        noter("ofac", "OFAC, actions récentes (Trésor américain)", "officiel", "échec", str(e)[:200])

    # Flux RSS officiels et de presse
    for s in config["sources_rss"]:
        groupe = "officiel" if s["type"] == "officiel" else "presse"
        if not s.get("url"):
            noter(s["cle"], s["nom"], groupe, "non configurée", s.get("_note"))
            continue
        try:
            items = f.rss(s["cle"], s["url"])
            garde = garde_off if s["type"] == "officiel" else garde_media
            filtre = re.compile(s["filtre"], re.I) if s.get("filtre") else None
            for it in items:
                if filtre and not filtre.search(f"{it['titre']} {it.get('description') or ''}"):
                    continue
                if _recent(it["date"], maintenant, garde):
                    articles.append({**it, "origine": "officiel" if s["type"] == "officiel" else "rss", "source": s["nom"],
                                     "langue": s.get("langue"),
                                     "officiel": s["type"] == "officiel",
                                     "categorie_par_defaut": "monetaire" if s["cle"] == "bri_discours" else None})
            noter(s["cle"], s["nom"], groupe, "ok" if items else "partielle", f"{len(items)} éléments")
        except Exception as e:  # noqa: BLE001
            noter(s["cle"], s["nom"], groupe, "échec", str(e)[:200])

    # Indices : relevés une fois par jour (ils sont publiés au plus une fois par jour)
    ind = etat.setdefault("indices", {})
    releve = ind.get("releve_le")
    du = mode == "quotidien" or not releve or maintenant - datetime.fromisoformat(releve.replace("Z", "+00:00")) > timedelta(hours=20)
    for cle, nom, appel in (("gpr", "Indice de risque géopolitique quotidien (Caldara et Iacoviello)", lambda: f.gpr()),
                            ("epu", "FRED, incertitude de politique économique (USEPUINDXD)",
                             lambda: f.epu((maintenant - timedelta(days=400)).date().isoformat())[0])):
        if not du and ind.get(cle):
            noter(cle, nom, "indices", "ok", f"relevé le {releve[:10]}")
            continue
        try:
            serie = appel()
            ind[cle] = serie[-400:]
            noter(cle, nom, "indices", "ok", f"dernière valeur au {serie[-1][0]}")
        except Exception as e:  # noqa: BLE001
            noter(cle, nom, "indices", "échec" if not ind.get(cle) else "périmée", str(e)[:200])
    if du and all(etats[c]["etat"] == "ok" for c in ("gpr", "epu")):
        ind["releve_le"] = E.iso(maintenant)
    return articles, etats


# ------------------------------------------------------------------ mise en forme

LANGUES = {"en": "anglais", "fr": "français", "es": "espagnol", "de": "allemand", "it": "italien", "pt": "portugais",
           "zh": "chinois", "ar": "arabe", "ru": "russe", "ja": "japonais"}


def publier(e: dict, config: dict, noms: dict, etat: dict, aujourdhui) -> dict:
    a = e.get("analyse") or {}
    pays = e.get("pays_principaux") or []
    tons = []
    for code in pays:
        p = config["pays"].get(code)
        if p:
            _, t = S.composante_tonalite(etat.get("gdelt_jours", {}), p["fips"], aujourdhui)
            if t is not None:
                tons.append(t)
    mondial = not pays and bool(a.get("mondial"))
    regions = sorted({(config["pays"].get(c) or config["autres_pays"].get(c) or {}).get("region", "monde") for c in pays}) or ["monde"]
    categorie = a.get("categorie") or e["categorie"]
    langue = E.langue_reference(e)
    # Titre : rédigé en français par Gemini ; sinon titre de l'article le plus repris, « non traduit »
    # s'il n'est pas en français
    titre_ia = a.get("titre")
    return {
        "id": e["id"], "titre": titre_ia or E.titre_reference(e), "titre_origine": E.titre_reference(e), "categorie": categorie,
        "titre_langue": None if titre_ia else LANGUES.get(langue or "", langue),
        "mention": None if (titre_ia or langue == "fr") else "non traduit",
        "categorie_libelle": config["categories"][categorie]["libelle"],
        "pays": pays, "pays_noms": ["Monde"] if mondial else [noms.get(c, c) for c in pays], "mondial": mondial,
        "pays_suivis": [c for c in pays if c in config["pays"]],
        "regions": regions, "gravite": e["gravite"], "note_gravite": a.get("note_gravite"),
        "ia": bool(a), "modele": a.get("modele"), "analyse_le": a.get("analyse_le"),
        "resume": a.get("resume", []), "actifs": a.get("actifs", []), "horizon": a.get("horizon"),
        "confiance": a.get("confiance", "faible"), "contre": a.get("contre", []),
        "sources_independantes": a.get("sources_independantes"),
        "sources": E.sources_publiques(e), "nb_articles": len(e["articles"]), "nb_domaines": E.independantes(e["articles"]),
        "officiel": E.officiel(e), "premier": e["premier"], "dernier": e["dernier"],
        "tonalite_gdelt": round(sum(tons) / len(tons), 2) if tons else None,
        "score_selection": E.score_selection(e, config),
    }


def serie_hebdo(serie: list[list], depuis: str, i_valeur: int = 1) -> list[list]:
    """Un point tous les 7 jours (dernier point toujours gardé)."""
    pts = [[x[0], x[i_valeur]] for x in serie if x[0] >= depuis and x[i_valeur] is not None]
    if not pts:
        return []
    res = pts[::-1][::7][::-1]
    return res


def indices(etat: dict, maintenant: datetime) -> dict:
    ind = etat.get("indices", {})
    depuis = (maintenant - timedelta(days=365)).date().isoformat()
    res = {}
    gpr = ind.get("gpr") or []
    if gpr:
        an = [x[1] for x in gpr if x[0] >= depuis]
        res["gpr"] = {"nom": "Indice de risque géopolitique (GPR)", "serie": serie_hebdo(gpr, depuis, 2),
                      "derniere": gpr[-1][1], "moyenne_7j": gpr[-1][2], "date": gpr[-1][0],
                      "moyenne_12m": round(sum(an) / len(an), 1) if an else None,
                      "source": "Caldara et Iacoviello, indice quotidien (matteoiacoviello.com), moyenne sur 7 jours ; 100 = moyenne 1985-2019"}
    epu = ind.get("epu") or []
    if epu:
        recents = [v for d, v in epu[-30:]]
        res["epu"] = {"nom": "Incertitude de politique économique (États-Unis)", "derniere": epu[-1][1], "date": epu[-1][0],
                      "moyenne_30j": round(sum(recents) / len(recents), 1),
                      "source": "FRED, Economic Policy Uncertainty Index for United States (USEPUINDXD), quotidien"}
    return res


# ------------------------------------------------------------------ signaux

def signaux(evts_publics: list[dict], scores: dict, nouveaux_ids: set, etat: dict, config: dict, maintenant: datetime, noms: dict) -> list[dict]:
    cfg = config["signaux"]
    deja = set(etat.get("signales", []))
    jour = maintenant.date().isoformat()
    res = []
    for e in evts_publics:
        if e["gravite"] >= cfg["gravite_min"] and f"gravite:{e['id']}" not in deja:
            res.append({"type": "evenement_grave", "cle": e["id"], "date": jour, "importance": "haute",
                        "titre": f"Événement de gravité {e['gravite']} : {e['titre']}", "pays": e["pays_suivis"],
                        "categorie": e["categorie"], "sources": [s["url"] for s in e["sources"][:3]]})
            deja.add(f"gravite:{e['id']}")
        if (e["officiel"] and e["categorie"] in ("sanctions", "commerce") and e["pays_suivis"]
                and e["id"] in nouveaux_ids and f"mesure:{e['id']}" not in deja):
            res.append({"type": "mesure_officielle", "cle": e["id"], "date": jour, "importance": "moyenne",
                        "titre": f"{e['categorie_libelle']} (source officielle) : {e['titre']}", "pays": e["pays_suivis"],
                        "categorie": e["categorie"], "sources": [s["url"] for s in e["sources"] if s.get("officiel")][:3]})
            deja.add(f"mesure:{e['id']}")
    for code, s in scores.items():
        v = s.get("variation_7j")
        if v is not None and v >= cfg["hausse_score_pts"] and f"score:{code}:{jour}" not in deja:
            res.append({"type": "hausse_score", "cle": code, "date": jour, "importance": "moyenne",
                        "titre": f"{noms.get(code, code)} : score de risque géopolitique {s['score']}/100, +{v} pts sur 7 jours",
                        "pays": [code], "score": s["score"], "variation_7j": v})
            deja.add(f"score:{code}:{jour}")
    etat["signales"] = sorted(deja)[-2000:]
    return res


# ------------------------------------------------------------------ synthèse quotidienne

def date_fr(iso_date: str) -> str:
    return f"{iso_date[8:10]}/{iso_date[5:7]}/{iso_date[:4]}"


def recap_markdown(jour, evts: list[dict], scores: dict, sig: list[dict], etats: dict, rapport_ia: dict, ind: dict, noms: dict, quota: dict) -> str:
    l = [f"# Agent géopolitique — synthèse du {date_fr(jour.isoformat())}", ""]
    l += ["Événements des dernières 24 heures, scores de risque par pays suivi et indices. Ton factuel : "
          "les résumés sont des faits sourcés, les impacts sur les marchés sont des interprétations.", ""]
    if not any(e["ia"] for e in evts):
        l += ["> Version sans IA : aucun événement n'a été analysé par Gemini (clé absente, quota atteint ou service indisponible). "
              "Les événements sont listés à partir des titres des sources, avec une gravité estimée par règles (au plus 3).", ""]
    l += ["## Événements des dernières 24 heures (par gravité)", ""]
    recents = [e for e in evts if e["dernier"] >= E.iso(datetime.combine(jour, datetime.min.time(), timezone.utc) - timedelta(hours=18))]
    for e in recents[:15]:
        suffixe = f" ({e['titre_langue']}, {e['mention']})" if e["mention"] else ""
        l.append(f"### [{e['gravite']}/5] {e['titre']}{suffixe}")
        l.append(f"- Catégorie : {e['categorie_libelle']} · pays : {', '.join(e['pays_noms']) or 'non déterminés'} · "
                 f"{'analyse Gemini, confiance ' + e['confiance'] if e['ia'] else 'sans IA'}")
        for r in e["resume"]:
            l.append(f"- Fait : {r['texte']} ({', '.join(r['sources'])})")
        for a in e["actifs"]:
            l.append(f"- Interprétation : {a['actif']}, {a['sens']} — {a['texte']} ({', '.join(a['sources'])})")
        if e["contre"]:
            l.append("- Ce qui pourrait me donner tort : " + " ; ".join(c["texte"] for c in e["contre"]))
        l.append(f"- Sources : {', '.join(s['url'] for s in e['sources'][:4])}")
        l.append("")
    if not recents:
        l += ["- aucun événement significatif", ""]
    l += ["## Scores de risque géopolitique (/100)", "", "| Pays | Score | Niveau | Variation 7 j |", "|---|---|---|---|"]
    for code, s in sorted(scores.items(), key=lambda x: -(x[1]["score"] or -1)):
        v = s["variation_7j"]
        l.append(f"| {noms.get(code, code)} | {s['score'] if s['score'] is not None else 'n. d.'} | {s['niveau'] or 'n. d.'} | "
                 f"{'n. d.' if v is None else f'{v:+.1f}'} |")
    l += ["", "## Indices", ""]
    if ind.get("gpr"):
        g = ind["gpr"]
        l.append(f"- {g['nom']} : {g['derniere']} au {date_fr(g['date'])} (moyenne 7 j : {g['moyenne_7j']}, moyenne 12 mois : {g['moyenne_12m']})")
    if ind.get("epu"):
        p = ind["epu"]
        l.append(f"- {p['nom']} : {p['derniere']} au {date_fr(p['date'])} (moyenne 30 j : {p['moyenne_30j']})")
    l += ["", "## Signaux", ""] + ([f"- [{s['importance']}] {s['titre']}" for s in sig] or ["- aucun"])
    l += ["", "## Analyse par IA", "",
          f"- Modèles : {', '.join(m['modele'] + ' ' + str(m['appels']) + '/' + str(m['limite_jour']) for m in quota.get('modeles', []))} "
          f"(appels du jour du Pacifique / limite avec marge de 20 %)"]
    erreurs = [v for v in etats.values() if v["etat"] in ("échec", "partielle", "périmée")]
    l += ["", "## Sources en échec", ""] + ([f"- {v['nom']} : {v['etat']} ({v.get('detail') or ''})" for v in erreurs] or ["- aucune"])
    return "\n".join(l) + "\n"


# ------------------------------------------------------------------ santé

def gemini_en_panne(rapport_ia: dict) -> bool:
    """Gemini n'a jamais répondu pendant l'exécution, pour une autre raison que les quotas."""
    return bool(rapport_ia["cle"] and rapport_ia["erreurs"] and not rapport_ia["reussites"]
                and not all("429" in e for e in rapport_ia["erreurs"]))


def sources_sante(etats: dict, rapport_ia: dict, quota: dict) -> list[dict]:
    res = [{"nom": v["nom"], "etat": v["etat"], "detail": v.get("detail"), **({"secondaire": True} if v.get("secondaire") else {})}
           for v in etats.values()]
    nom = "Gemini (analyse des événements)"
    if not rapport_ia["cle"]:
        res.append({"nom": nom, "etat": "non configurée", "detail": "secret GEMINI_API_KEY absent : version sans IA"})
    elif gemini_en_panne(rapport_ia):
        res.append({"nom": nom, "etat": "échec", "detail": "; ".join(rapport_ia["erreurs"])[-300:]})
    else:
        utilises = ", ".join(f"{m} ×{n}" for m, n in rapport_ia["modeles_utilises"].items()) or "aucun appel nécessaire"
        detail = f"{rapport_ia['appels']} appel(s) cette exécution ({utilises}) ; {quota['appels']} aujourd'hui (jour du Pacifique)"
        secours = [m for m in rapport_ia["modeles_utilises"] if m != quota["modele"]]
        if secours:
            detail += f" ; modèle de secours utilisé : {', '.join(secours)}"
        if rapport_ia.get("quota_atteint"):
            detail += " ; quota atteint (429) : modèle concerné suspendu jusqu'au lendemain"
        res.append({"nom": nom, "etat": "ok", "detail": detail})
    return res


def raisons_degradation(etats: dict, config: dict) -> list[str]:
    """Règle propre à l'agent : dégradé si les fichiers d'événements GDELT ne répondent pas, ou si moins
    de `sante.sources_min` autres sources répondent. Les sources secondaires (GDELT DOC) n'entrent pas
    dans le compte ; une source isolée en échec est compensée par les autres."""
    raisons = []
    if etats.get("gdelt_evenements", {}).get("etat") not in ("ok", "partielle"):
        raisons.append("Fichiers d'événements GDELT indisponibles (tonalité et volume par pays)")
    autres = [v for c, v in etats.items() if c != "gdelt_evenements" and not v.get("secondaire") and v["etat"] != "non configurée"]
    valides = [v for v in autres if v["etat"] in ("ok", "partielle")]
    mini = config["sante"]["sources_min"]
    if len(valides) < mini:
        raisons.append(f"{len(valides)} source{'s' if len(valides) > 1 else ''} répond{'ent' if len(valides) > 1 else ''} "
                       f"(hors GDELT), moins que le minimum de {mini}")
    return raisons


# ------------------------------------------------------------------ exécution

def synthese_due(mode: str, data: Path, maintenant: datetime) -> bool:
    if mode == "quotidien":
        return True
    return maintenant.hour >= HEURE_SYNTHESE and not (data / "recap" / f"geopolitique-{maintenant.date().isoformat()}.md").exists()


def executer(f, config: dict, data: Path, maintenant: datetime, mode: str = "horaire", cle_gemini: str | None = None,
             poster=None, horloge=None, dormir=None) -> dict:
    """Une exécution complète. Renvoie un compte rendu (utilisé par les tests)."""
    noms = noms_pays(config)
    chemin_etat = data / "geopolitique" / "etat.json"
    etat = lire_json(chemin_etat) or {}
    aujourdhui = maintenant.date()

    articles, etats = collecter(f, config, etat, maintenant, mode)
    if not any(v["etat"] in ("ok", "partielle") for v in etats.values()):
        LOG.error("Aucune source n'a répondu : fichiers inchangés.")
        return {"ok": False}

    # Articles déjà vus (exécutions précédentes) : ignorés
    vues = {u: d for u, d in (etat.get("urls_vues") or {}).items() if d >= E.iso(maintenant - timedelta(days=8))}
    det = E.Detecteur(config)
    prets = []
    for a in articles:
        if a["url"] in vues:
            continue
        vues[a["url"]] = a.get("date") or E.iso(maintenant)
        p = E.preparer(a, det)
        if p:
            prets.append(p)
    etat["urls_vues"] = vues

    evenements = etat.get("evenements", [])
    if evenements and etat.get("version_regroupement") != E.VERSION_REGROUPEMENT:
        LOG.info("Méthode de regroupement modifiée : %d événements refaits à partir de leurs articles", len(evenements))
        evenements = E.reconstruire(evenements, det, config, maintenant)
    etat["version_regroupement"] = E.VERSION_REGROUPEMENT
    avant = {e["id"] for e in evenements}
    touches = E.regrouper(prets, evenements, config, maintenant)
    evenements = E.nettoyer(evenements, maintenant, config["evenements_garde_jours"])
    # Doublons : événements qui décrivent le même fait (48 h, mêmes pays principaux, titres proches)
    evenements, fusions = E.fusionner(evenements, det)
    # Nouveaux : événements créés, ou qui reçoivent une source officielle, pendant cette exécution
    urls_neuves = {p["url"] for p in prets}
    absorbe_par = {autre: base for base, autre in fusions}
    ids_touches = {absorbe_par.get(e["id"], e["id"]) for e in touches}
    nouveaux_ids = {e["id"] for e in evenements if e["id"] in ids_touches and (
        e["id"] not in avant or any(a.get("officiel") and a["url"] in urls_neuves for a in e["articles"]))}

    # Analyse par Gemini des événements significatifs (gravité estimée 3 ou plus d'abord)
    limite_aff = E.iso(maintenant - timedelta(days=config["evenements_affiches_jours"]))
    significatifs = [e for e in evenements if e["dernier"] >= limite_aff and E.significatif(e, config)]
    candidats = [e for e in significatifs if ia.a_analyser(e, config, maintenant)]
    quotas = ia.Quotas(etat, config["gemini"], horloge=horloge, dormir=dormir or time.sleep)
    rapport_ia = ia.analyser(candidats, config, quotas, maintenant, cle=cle_gemini, poster=poster)
    if rapport_ia["fusions"]:  # regroupements confirmés par Gemini
        evenements, faites = E.fusionner(evenements, det, rapport_ia["fusions"])
        fusions += faites
        significatifs = [e for e in evenements if e["dernier"] >= limite_aff and E.significatif(e, config)]
        nouveaux_ids = {absorbe_par.get(i, i) for i in nouveaux_ids} | {b for b, a in faites if a in nouveaux_ids}
    for e in evenements:
        e["gravite"] = (e.get("analyse") or {}).get("gravite") or E.gravite_regles(e, config)
        resume = [r["texte"] for r in (e.get("analyse") or {}).get("resume", [])]
        e["pays_principaux"] = E.pays_principaux(e, det, resume)

    # Scores par pays
    scores = S.scores(config, significatifs, etat, maintenant)
    S.enregistrer_historique(etat, scores, aujourdhui)
    # Publiés : événements rattachés à au moins un pays, ou à portée mondiale explicite (affichés « Monde »)
    publics = sorted((x for x in (publier(e, config, noms, etat, aujourdhui) for e in significatifs) if x["pays"] or x["mondial"]),
                     key=lambda x: (x["gravite"], x["dernier"]), reverse=True)[:80]
    par_pays = {}
    for code, s in scores.items():
        derniers = sorted((x for x in publics if code in x["pays"]), key=lambda x: x["dernier"], reverse=True)[:3]
        par_pays[code] = {**s, "nom": noms.get(code, code), "region": config["pays"][code]["region"],
                          "derniers_evenements": [{"id": x["id"], "titre": x["titre"], "gravite": x["gravite"], "date": x["dernier"],
                                                   "categorie_libelle": x["categorie_libelle"], "titre_langue": x["titre_langue"],
                                                   "mention": x["mention"],
                                                   "resume": x["resume"][0]["texte"] if x["resume"] else None,
                                                   "source": x["sources"][0]["url"] if x["sources"] else None} for x in derniers]}
    ind = indices(etat, maintenant)
    q = quotas.resume()
    sans_ia = not rapport_ia["cle"] or (rapport_ia["erreur"] and not rapport_ia["reussites"])
    donnees = {
        "date": aujourdhui.isoformat(),
        "mode_ia": "sans IA" if not any(x["ia"] for x in publics) else "gemini",
        "avertissement_ia": ("Analyse par IA indisponible pour cette mise à jour (" +
                             ("clé GEMINI_API_KEY absente" if not rapport_ia["cle"] else (rapport_ia["erreur"] or "")[:120]) +
                             ") : les nouveaux événements sont présentés sans IA (titre de l'article le plus repris, avec sa langue et la mention « non traduit », "
                             "tonalité GDELT, gravité estimée par règles).")
        if sans_ia else None,
        "evenements": publics, "pays": par_pays, "indices": ind, "quota_ia": q,
        "regions": config["regions"], "categories": {k: v["libelle"] for k, v in config["categories"].items()},
        "methode": "Événements : articles GDELT, presse internationale et sources officielles regroupés par événement ; "
                   "analyse Gemini avec une source citée pour chaque affirmation (sinon supprimée), gravité 4 ou 5 seulement avec "
                   "2 sources indépendantes. Score /100 : événements récents pondérés par la gravité (50 %), tonalité GDELT (30 %), "
                   "tendance sur 30 jours (20 %).",
    }

    # Signaux pour le chef d'orchestre et le futur agent risque
    sig = signaux(publics, scores, nouveaux_ids, etat, config, maintenant, noms)
    fichier_signaux = data / "signaux" / "geopolitique.json"
    existants = (lire_json(fichier_signaux) or {}).get("donnees") or []
    limite = (aujourdhui - timedelta(days=config["signaux"]["garde_jours"])).isoformat()
    tous = sorted((s for s in existants + sig if s["date"] >= limite), key=lambda s: s["date"], reverse=True)
    ecrire_json(fichier_signaux, enveloppe(tous, "agent-geopolitique", fictif=False, version_agent=VERSION_AGENT,
                                           description="Signaux candidats pour le chef d'orchestre et l'agent risque (180 derniers jours)"))

    ancien = lire_json(data / "geopolitique.json")
    objet = enveloppe(donnees, "agent-geopolitique", fictif=False, version_agent=VERSION_AGENT,
                      mise_a_jour_precedente=(ancien or {}).get("meta", {}).get("genere_le"),
                      etat_des_sources={v["nom"]: v["etat"] for v in etats.values()})
    objet["meta"]["genere_le"] = E.iso(maintenant)
    ecrire_json(data / "geopolitique.json", objet)
    ecrire_json(data / "historique" / "geopolitique" / f"{aujourdhui.isoformat()}.json", {
        "meta": {"genere_le": E.iso(maintenant), "source": "agent-geopolitique", "version_agent": VERSION_AGENT},
        "donnees": {"scores": {c: {"score": s["score"], "niveau": s["niveau"], "composantes": s["composantes"]} for c, s in scores.items()},
                    "evenements": [{"id": x["id"], "titre": x["titre"], "gravite": x["gravite"], "categorie": x["categorie"],
                                    "pays": x["pays"], "ia": x["ia"], "actifs": [{"actif": a["actif"], "sens": a["sens"]} for a in x["actifs"]]}
                                   for x in publics if x["dernier"][:10] == aujourdhui.isoformat()],
                    "indices": {k: {"valeur": v["derniere"], "date": v["date"]} for k, v in ind.items()}}})
    recap = synthese_due(mode, data, maintenant)
    if recap:
        (data / "recap").mkdir(parents=True, exist_ok=True)
        (data / "recap" / f"geopolitique-{aujourdhui.isoformat()}.md").write_text(
            recap_markdown(aujourdhui, publics, scores, [s for s in tous if s["date"] == aujourdhui.isoformat()], etats, rapport_ia, ind, noms, q),
            encoding="utf-8")

    # Journal et santé (écran « Santé des agents »)
    chemin_journal = data / "journal" / "agent-geopolitique.json"
    j = lire_json(chemin_journal) or {"meta": {}, "donnees": []}
    entree = {"genere_le": E.iso(maintenant), "mode": mode, "synthese": recap,
              "articles_nouveaux": len(prets), "evenements_suivis": len(evenements), "evenements_significatifs": len(significatifs),
              "ia": {k: rapport_ia.get(k) for k in ("modele", "appels", "reussites", "analyses", "rejets", "quota_atteint", "modeles_utilises")}
              | {"erreurs": [e[:200] for e in rapport_ia["erreurs"]][:10], "appels_du_jour": q["appels"], "quota_jour": q["quota_jour"],
                 "suppressions": rapport_ia["suppressions"][:20]},
              "fusions": len(fusions),
              "etat_des_sources": {v["nom"]: v["etat"] for v in etats.values()}, "signaux": [s["titre"] for s in sig]}
    j["donnees"] = (j.get("donnees", []) + [entree])[-200:]
    j["meta"] = {**j.get("meta", {}), "genere_le": E.iso(maintenant), "source": "agent-geopolitique", "version_agent": VERSION_AGENT,
                 "description": "Sources, appels à Gemini (quota) et signaux, à chaque exécution"}
    ecrire_json(chemin_journal, j)
    raisons = []
    if gemini_en_panne(rapport_ia):
        raisons.append(f"Analyse sans IA : Gemini indisponible ({(rapport_ia['erreur'] or '')[:120]})")
    bloc = sante.bloc_sante("geopolitique", "Agent géopolitique", 6, WORKFLOW, sources_sante(etats, rapport_ia, q), maintenant,
                            (j.get("meta") or {}).get("sante"), indicateurs={}, raisons_supplementaires=raisons_degradation(etats, config) + raisons)
    bloc["ia"] = {"modele": q["modele"], "appels_du_jour": q["appels"], "quota_jour": q["quota_jour"], "jour_quota": q["jour"],
                  "mode": donnees["mode_ia"], "modeles": q["modeles"]}
    sante.enregistrer_sante(chemin_journal, bloc, forcer=True)

    etat["evenements"] = evenements
    etat["maj"] = E.iso(maintenant)
    ecrire_json(chemin_etat, etat, compact=True)

    LOG.info("%d articles nouveaux, %d événements suivis (%d fusions), %d significatifs ; Gemini : %d appel(s), %d analyse(s) ; "
             "%d signal(aux)%s", len(prets), len(evenements), len(fusions), len(significatifs), rapport_ia["appels"],
             rapport_ia["analyses"], len(sig), " ; synthèse écrite" if recap else "")
    for x in publics[:8]:
        LOG.info("  [%d/5] %s | %s | %s%s", x["gravite"], ", ".join(x["pays"]) or "-", f"{x['modele']}" if x["ia"] else "non analysé",
                 x["titre"][:90], f" — {x['resume'][0]['texte'][:140]}" if x["resume"] else "")
    LOG.info("Statut santé : %s%s", "DÉGRADÉ" if bloc["degrade"] else "OK", (" — " + " | ".join(bloc["raisons"])) if bloc["raisons"] else "")
    return {"ok": True, "rapport_ia": rapport_ia, "donnees": donnees, "signaux": sig, "etat": etat, "sante": bloc, "recap": recap}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent géopolitique : événements et impact possible sur les marchés.")
    ap.add_argument("--test", action="store_true", help="données de test (agents/geopolitique/tests/donnees), sans réseau ni Gemini")
    ap.add_argument("--data", default=str(RACINE / "data"), help="dossier de sortie (data/)")
    ap.add_argument("--mode", choices=["horaire", "quotidien"], default="horaire",
                    help="« quotidien » : écrit aussi la synthèse du jour (6 h UTC)")
    ap.add_argument("--maintenant", help="heure simulée (ISO, UTC), pour les tests")
    ap.add_argument("--sans-ia", action="store_true", help="n'appelle pas Gemini")
    args = ap.parse_args(argv)
    config = charger_config()
    maintenant = datetime.fromisoformat(args.maintenant.replace("Z", "+00:00")) if args.maintenant else datetime.now(timezone.utc)
    if args.test:
        f = FournisseurTest(DOSSIER / "tests" / "donnees")
    else:
        f = FournisseurReel(RACINE / "agents" / ".cache", config)
    cle = "" if (args.sans_ia or args.test) else os.environ.get("GEMINI_API_KEY", "")
    LOG.info("Agent géopolitique %s — %s, mode %s", VERSION_AGENT, "données de test" if args.test else "sources réelles", args.mode)
    r = executer(f, config, Path(args.data), maintenant, args.mode, cle_gemini=cle)
    return 0 if r["ok"] else 1
