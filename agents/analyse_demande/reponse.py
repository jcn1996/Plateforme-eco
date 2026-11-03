"""Textes des commentaires d'issue (français, ton froid et factuel, mêmes règles que les autres agents)."""
from __future__ import annotations

from urllib.parse import quote

from ..entreprises.recommandation import MENTION, prix_texte
from ..pays.textes import nb

NIVEAUX = {"attractif": "attractif", "neutre": "neutre", "defavorable": "défavorable"}


def lien_fiche(url_appli: str, ticker: str) -> str:
    return f"{url_appli.rstrip('/')}/#analyse-{quote(ticker, safe='.-_')}"


def date_fr(iso: str | None) -> str:
    if not iso:
        return "date inconnue"
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def indicateurs_cles(e: dict, cfg: dict, n: int = 5) -> list[dict]:
    ordre = cfg["indicateurs_cles"]["financier" if e.get("financier") else "non_financier"]
    ind = e.get("indicateurs") or {}
    choisis = [ind[k] for k in ordre if k in ind][:n]
    if len(choisis) < n:
        choisis += [v for k, v in ind.items() if v not in choisis][: n - len(choisis)]
    return choisis


def rang_texte(r: dict | None) -> str | None:
    if not r or not r.get("monde"):
        return None
    m = r["monde"]
    t = f"{m['rang']}{'re' if m['rang'] == 1 else 'e'} sur {m['total']} sociétés du secteur {r['secteur_nom']} déjà analysées (note médiane {m['note_mediane']}/100)"
    reg = r.get("region")
    if reg and reg["total"] > 1:
        t += f" ; {reg['rang']}{'re' if reg['rang'] == 1 else 'e'} sur {reg['total']} en {reg['nom']}"
    return t + "."


def reponse_ok(e: dict, resolution: dict, cfg: dict, avertissement_sources: str | None = None) -> str:
    r = e.get("recommandation") or {}
    v = r.get("valeur") or {}
    devise = r.get("devise")
    lignes = [f"## Analyse : {e['nom']} ({e['ticker']})", "",
              f"**Note : {e['note']}/100** ({NIVEAUX.get(e.get('niveau'), e.get('niveau'))}) · confiance : **{e['confiance']['niveau']}**"
              + (f" · ajustement de contexte (pays et cycle, non inclus) : {nb(e['contexte']['ajustement'], 1, signe=True)} pt" if e.get("contexte") else ""),
              "", f"**Verdict.** {e['verdict']}", ""]
    if r:
        lignes += [f"### Recommandation (horizon {r['horizon_mois']} mois)", "",
                   f"- Si non détenu : **{r['si_non_detenu']}**",
                   f"- Si détenu : **{r['si_detenu']}**",
                   f"- Cours : {prix_texte(r.get('cours'), devise)} au {date_fr(r.get('date_cours'))}"]
        if v:
            lignes.append(f"- Valeur estimée : {prix_texte(v['bas'], devise)} à {prix_texte(v['haut'], devise)} (centrale {prix_texte(v['centrale'], devise)}),"
                          f" écart au cours {nb(v['ecart_pct'], 1, signe=True)} %" + ("" if v.get("fiable") else f" — estimation non exploitable : {v.get('reserve')}"))
            for mth in v.get("methodes", []):
                h = mth["hypotheses"]
                detail = ", ".join(h["references"]) if mth["cle"] == "multiples" else \
                    f"croissance {nb(h['croissance'], 1)} % ramenée à {nb(h['croissance_terminale'], 1)} % en {h['annees']} ans, taux d'actualisation {nb(h['taux_actualisation'], 1)} %"
                lignes.append(f"  - {mth['nom']} : {prix_texte(mth['bas'], devise)} à {prix_texte(mth['haut'], devise)} ({detail})")
        else:
            lignes.append("- Valeur estimée : non calculable (multiples du secteur et flux de trésorerie indisponibles)")
        if r.get("prix_repli") and r["si_non_detenu"] == "Acheter sur repli":
            lignes.append(f"- Passerait à « Acheter » sous {prix_texte(r['prix_repli'], devise)}")
        lignes += [f"- {r['justification']}", "", "Conditions qui invalideraient la recommandation :"]
        lignes += [f"- {c}" for c in r.get("conditions_invalidation", [])]
        lignes.append("")
    lignes += ["### 5 indicateurs clés", "", "| Indicateur | Valeur | Note /100 |", "|---|---|---|"]
    for i in indicateurs_cles(e, cfg):
        lignes.append(f"| {i['libelle']} | {i['affichage']}{(' (' + i['complement'] + ')') if i.get('complement') else ''} | {i['note']} |")
    risques = (r.get("risques") or (e.get("revue_critique") or {}).get("risques") or [])[:3]
    if e.get("alertes"):
        risques = [f"Signal d'alerte comptable : {a['titre'].lower()} ({a['texte']})" for a in e["alertes"]] + risques
    lignes += ["", "### Principaux risques", ""] + [f"- {t}" for t in risques[:4]]
    rt = rang_texte(e.get("rang_secteur"))
    if rt:
        lignes += ["", f"**Rang dans le secteur.** {rt}"]
    lignes += ["", f"**Niveau de confiance : {e['confiance']['niveau']}.** " + ("; ".join(e["confiance"].get("raisons") or []) or "aucune réserve") + "."]
    if resolution.get("autres"):
        autres = ", ".join(f"{c['symbole']} ({c['nom']}{', ' + c['place'] if c.get('place') else ''}"
                           + (f", {nb(c['liquidite_musd'], 1)} M$ échangés par jour" if c.get("liquidite_musd") is not None else "") + ")"
                           for c in resolution["autres"][:5])
        regle = "cotation la plus liquide retenue" if resolution.get("methode") == "nom" else "ticker saisi retenu"
        lignes += ["", f"Autres correspondances ({regle}) : {autres}. Pour en analyser une : nouvelle issue « Analyse : <ticker> »."]
    if avertissement_sources:
        lignes += ["", avertissement_sources]
    lignes += ["", f"Fiche complète : {lien_fiche(cfg['url_appli'], e['ticker'])}", "",
               f"<sub>Sources : {e['sources']['comptes']} ; cours Yahoo Finance du {date_fr(e['sources'].get('date_cours'))}. "
               f"Même grille que l'agent entreprises (règles, sans IA). {MENTION} Ne constitue pas un conseil en investissement.</sub>"]
    return "\n".join(lignes) + "\n"


def reponse_introuvable(texte: str, suggestions: list[str]) -> str:
    l = [f"## Analyse : « {texte} » introuvable", "",
         "Aucune action cotée ne correspond à cette saisie dans la recherche Yahoo Finance."]
    if suggestions:
        l += ["", "Suggestions :"] + [f"- {s}" for s in suggestions]
    l += ["", "Pour relancer : nouvelle issue « Analyse : <ticker Yahoo> », par exemple « Analyse : MC.PA », « Analyse : 7203.T » ou « Analyse : ASML »."]
    return "\n".join(l) + "\n"


def reponse_insuffisant(texte: str, ticker: str, raison: str) -> str:
    return (f"## Analyse : {ticker}\n\nSociété trouvée pour « {texte} », mais données insuffisantes pour l'analyser : {raison}.\n\n"
            "Les comptes annuels publiés sur Yahoo Finance sont nécessaires (au moins deux exercices pour la plupart des indicateurs).\n")


def reponse_refus() -> str:
    return ("Merci pour cette demande. Les analyses à la demande sont réservées au propriétaire du dépôt : "
            "cette issue est fermée sans qu'aucune analyse ne soit lancée.\n")


def reponse_echec(texte: str, detail: str, url_execution: str | None) -> str:
    return (f"## Analyse : échec pour « {texte} »\n\nL'analyse n'a pas pu aboutir : {detail}.\n\n"
            + (f"Détail de l'exécution : {url_execution}\n\n" if url_execution else "")
            + "L'échec est visible dans l'écran Santé de l'appli. Pour relancer : nouvelle issue avec le même titre.\n")
