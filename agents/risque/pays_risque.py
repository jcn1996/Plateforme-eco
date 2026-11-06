"""
Score de risque /100 par pays suivi (100 = risque élevé), en cinq composantes :
- marché : baisse depuis le plus haut sur 12 mois et volatilité à 3 mois de l'ETF du pays (agent pays) ;
- devise : volatilité à 1 mois et variation sur 3 mois contre le dollar (devise suivie par l'agent pays,
  vérifiée avec la variation publiée dans data/pays.json) ;
- souverain : écart du taux à 10 ans avec l'Allemagne (zone euro) ou les États-Unis (autres pays) ;
- vulnérabilité macro : dette publique / PIB et solde courant (FMI), écart de l'inflation à la cible
  (agent pays, FMI en secours), réserves en mois d'importations (Banque mondiale) quand disponibles ;
- géopolitique : score de l'agent géopolitique (data/geopolitique.json).
Chaque mesure est ramenée sur 0-100 entre deux bornes de la config ; une composante absente est
retirée de la moyenne pondérée (signalée dans « composantes_manquantes »).
"""
from __future__ import annotations

from datetime import timedelta

from . import calculs as C

LIBELLES = {"marche": "marché", "devise": "devise", "souverain": "souverain", "macro": "vulnérabilité macro", "geopolitique": "géopolitique"}


def valeur_devise(serie, inverse: bool):
    """Valeur de la devise en dollars (Yahoo cote souvent le nombre d'unités pour un dollar)."""
    return [(d, 1 / v) for d, v in serie if v] if inverse else list(serie)


def dernier_annuel(valeurs: dict | None, annee: int):
    """Dernière année ≤ annee disponible d'une série annuelle {\"2026\": x}."""
    if not valeurs:
        return None
    annees = sorted(a for a in valeurs if a.isdigit() and int(a) <= annee and valeurs[a] is not None)
    return (annees[-1], float(valeurs[annees[-1]])) if annees else None


def composantes_pays(code: str, p: dict, ctx: dict, config: dict) -> dict:
    cp = config["pays"]
    b = cp["bornes"]
    aujourdhui = ctx["aujourdhui"]
    res = {}

    # Marché
    etf = ctx["cours"].get(p.get("etf"))
    if etf and len(etf) > 60:
        dd = C.baisse_plus_haut(etf, 252)
        vol = C.volatilite(etf, 63)
        notes = [x for x in (C.borne(dd, *b["baisse_plus_haut_12m"]), C.borne(vol, *b["volatilite_3m"])) if x is not None]
        if notes:
            res["marche"] = {"score": round(sum(notes) / len(notes), 1), "baisse_plus_haut_12m": dd, "volatilite_3m": vol,
                             "etf": p["etf"], "date": etf[-1][0],
                             "texte": f"ETF {p['etf']} à {C.fr(dd, 1)} % de son plus haut sur 12 mois, volatilité à 3 mois de {C.fr(vol, 1)} %",
                             "source": f"Yahoo Finance via yfinance, ETF {p['etf']}"}

    # Devise
    dv = p.get("devise") or {}
    brut = ctx["cours"].get(dv.get("symbole"))
    if brut and len(brut) > 70:
        serie = valeur_devise(brut, dv.get("inverse", False))
        vol1 = C.volatilite(serie, 21)
        var3 = C.variation_pct(serie, 63)
        var1 = C.variation_pct(serie, 21)
        notes = [x for x in (C.borne(vol1, *b["devise_volatilite_1m"]), C.borne(var3, *b["devise_variation_3m"])) if x is not None]
        # Vérification croisée avec la variation sur 3 mois publiée par l'agent pays
        pub = ((ctx["pays_json"].get(code) or {}).get("detail") or {}).get("devise_3m") or {}
        verification = "source_unique"
        if pub.get("valeur") is not None and var3 is not None:
            verification = "concordant" if abs(pub["valeur"] - var3) <= 1.5 else "divergent"
        if notes:
            res["devise"] = {"score": round(sum(notes) / len(notes), 1), "volatilite_1m": vol1, "variation_3m": var3, "variation_1m": var1,
                             "libelle": dv.get("libelle"), "date": serie[-1][0], "verification": verification,
                             "controle_agent_pays": pub.get("valeur"),
                             "texte": f"{dv.get('libelle') or 'devise'} : volatilité à 1 mois de {C.fr(vol1, 1)} %, {C.fr(var3, 1, True)} % contre le dollar sur 3 mois",
                             "source": f"Yahoo Finance via yfinance, {dv.get('symbole')} (devise suivie par l'agent pays)"}

    # Souverain : écart de taux à 10 ans
    taux = ctx["taux_10a"]
    ref = cp["reference_euro"] if code in cp["euro"] else cp["reference_autres"]
    t, tref = taux.get(code), taux.get(ref)
    if t and tref:
        pt, pr = t[-1], C.valeur_a(tref, t[-1][0], 45)
        if pr is not None and (C.jour(aujourdhui) - C.jour(pt[0])).days <= 120:
            ecart = round(pt[1] - pr[1], 2)
            controle = ctx["taux_10a_bce"].get(code)
            verification = "source_unique"
            if controle:
                pc = C.valeur_a(controle, pt[0], 20)
                if pc is not None:
                    verification = "concordant" if abs(pc[1] - pt[1]) <= cp["tolerance_taux_10a"] else "divergent"
            res["souverain"] = {"score": C.borne(ecart, *b["ecart_10a"]), "taux_10a": round(pt[1], 2), "ecart": ecart, "reference": ref,
                                "date": pt[0], "verification": verification,
                                "texte": (f"taux à 10 ans de {C.fr(pt[1], 2)} % ({pt[0][5:7]}/{pt[0][:4]})"
                                          + ("" if code == ref else f", écart de {C.fr(ecart, 2, True)} pt avec {ctx['noms'].get(ref, ref)}")),
                                "source": "OCDE via FRED (IRLTLT01…M156N), mensuel" + (" ; vérifié avec la BCE (IRS)" if verification != "source_unique" else "")}

    # Vulnérabilité macro
    iso3 = p.get("iso3")
    annee = C.jour(aujourdhui).year
    dette = dernier_annuel((ctx["fmi"].get("GGXWDG_NGDP") or {}).get(iso3), annee)
    solde = dernier_annuel((ctx["fmi"].get("BCA_NGDPD") or {}).get(iso3), annee)
    reserves = dernier_annuel((ctx["reserves"] or {}).get(iso3), annee)
    infl_pays = ((ctx["pays_json"].get(code) or {}).get("indicateurs") or {}).get("inflation") or {}
    inflation, source_infl = None, None
    if infl_pays.get("valeur") is not None:
        inflation, source_infl = infl_pays["valeur"], "agent pays"
    else:
        x = dernier_annuel((ctx["fmi"].get("PCPIPCH") or {}).get(iso3), annee)
        if x:
            inflation, source_infl = x[1], f"FMI ({x[0]})"
    cible = p.get("cible_inflation") or infl_pays.get("cible") or 2.0
    mesures, morceaux = [], []
    if dette:
        mesures.append(C.borne(dette[1], *b["dette_pib"]))
        morceaux.append(f"dette publique de {C.fr(dette[1], 0)} % du PIB ({dette[0]})")
    if solde:
        mesures.append(C.borne(solde[1], *b["solde_courant"]))
        morceaux.append(f"solde courant de {C.fr(solde[1], 1, True)} % du PIB")
    if inflation is not None:
        mesures.append(C.borne(abs(inflation - cible), *b["ecart_inflation_cible"]))
        morceaux.append(f"inflation à {C.fr(inflation, 1)} % pour une cible de {C.fr(cible, 1)} %")
    if reserves and "reserves_mois_importations" in b:
        mesures.append(C.borne(reserves[1], *b["reserves_mois_importations"]))
        morceaux.append(f"réserves de change de {C.fr(reserves[1], 1)} mois d'importations")
    if mesures:
        res["macro"] = {"score": round(sum(mesures) / len(mesures), 1), "dette_pib": dette[1] if dette else None,
                        "solde_courant": solde[1] if solde else None, "inflation": inflation, "cible_inflation": cible,
                        "reserves_mois": reserves[1] if reserves else None, "texte": ", ".join(morceaux),
                        "source": "FMI (GGXWDG_NGDP, BCA_NGDPD)" + (f", inflation : {source_infl}" if source_infl else "")
                                  + (", Banque mondiale (FI.RES.TOTL.MO)" if reserves else "")}

    # Géopolitique
    g = ((ctx["geopolitique"] or {}).get("pays") or {}).get(code) or {}
    if g.get("score") is not None:
        res["geopolitique"] = {"score": float(g["score"]), "texte": f"score de risque géopolitique de {C.fr(g['score'], 0)}/100",
                               "source": "agent géopolitique (data/geopolitique.json)"}
    return res


def niveau(score, config: dict) -> str | None:
    if score is None:
        return None
    cp = config["pays"]
    return "élevé" if score >= cp["seuil_eleve"] else "modéré" if score >= cp["seuil_modere"] else "faible"


def texte_pays(nom: str, s: dict) -> str:
    """Deux phrases factuelles : score et composante principale, puis composante la plus basse."""
    comp = s["composantes"]
    if s["score"] is None:
        return f"{nom} : score de risque non calculé (données insuffisantes). Composantes manquantes : {', '.join(LIBELLES[c] for c in s['composantes_manquantes'])}."
    v = s["variation_7j"]
    variation = "variation sur 7 jours non disponible" if v is None else f"{C.fr(v, 0, True)} pt sur 7 jours"
    ordre = sorted(comp.items(), key=lambda kv: -kv[1]["score"])
    haut, bas = ordre[0], ordre[-1]
    p1 = (f"{nom} : score de risque de {C.fr(s['score'], 0)}/100 ({variation}), porté surtout par la composante "
          f"{LIBELLES[haut[0]]} ({C.fr(haut[1]['score'], 0)}/100 : {haut[1]['texte']}).")
    if len(ordre) > 1:
        p2 = f"Composante la plus basse : {LIBELLES[bas[0]]} ({C.fr(bas[1]['score'], 0)}/100 : {bas[1]['texte']})"
    else:
        p2 = "Une seule composante disponible"
    if s["composantes_manquantes"]:
        p2 += f" ; non disponible{'s' if len(s['composantes_manquantes']) > 1 else ''} : {', '.join(LIBELLES[c] for c in s['composantes_manquantes'])}"
    return p1 + " " + p2 + "."


def scores(config: dict, ctx: dict, historique: dict) -> dict:
    """{code: {nom, score, niveau, variation_7j, composantes, composantes_manquantes, texte}}."""
    poids = config["pays"]["ponderations"]
    il_y_a_7j = (C.jour(ctx["aujourdhui"]) - timedelta(days=7)).isoformat()
    anciennes = sorted(d for d in historique if d <= il_y_a_7j)
    reference = historique[anciennes[-1]] if anciennes and (C.jour(il_y_a_7j) - C.jour(anciennes[-1])).days <= 3 else {}
    res = {}
    for code, p in ctx["pays_config"].items():
        comp = composantes_pays(code, p, ctx, config)
        dispo = {k: v["score"] for k, v in comp.items() if v.get("score") is not None}
        comp = {k: v for k, v in comp.items() if k in dispo}
        w = sum(poids[k] for k in dispo)
        score = round(sum(poids[k] * v for k, v in dispo.items()) / w, 1) if len(dispo) >= 2 else None
        ancien = reference.get(code)
        s = {"nom": p["nom"], "score": None if score is None else round(score), "score_precis": score, "niveau": niveau(score, config),
             "variation_7j": None if (score is None or ancien is None) else round(score - ancien, 1),
             "composantes": comp, "composantes_manquantes": [k for k in poids if k not in dispo],
             "ponderations": poids}
        s["texte"] = texte_pays(p["nom"], s)
        res[code] = s
    return res
