"""Rapport mensuel du backtest (data/backtest/rapport-AAAA-MM.md)."""
from __future__ import annotations


def n(x, d: int = 2, signe: bool = False, unite: str = "") -> str:
    if x is None:
        return "n. d."
    s = f"{x:+.{d}f}" if signe else f"{x:.{d}f}"
    return s.replace(".", ",").replace("-", "−") + unite


def _ligne_signal(r: dict) -> str:
    h = str(r["horizon_reference"])
    e, x = r["echantillons"], r["horizons"].get(h, {})
    reg = r.get("regimes") or {}
    return (f"| {r['libelle']} | **{r['verdict']}** | {n(e['apprentissage']['ic_moyen'], 3, True)} | {n(e['verification']['ic_moyen'], 3, True)} "
            f"(t = {n(e['verification']['ic_t'], 1)}) | {n(x.get('ecart_pct'), 2, True, ' %')} | {n(x.get('haut_vs_indice_pct'), 2, True, ' %')} "
            f"| {n(e['verification'].get('ecart_net_annuel_pct'), 1, True, ' %')} | {n(x.get('reussite_haut_pct'), 0, unite=' %')} "
            f"| {n((reg.get('calme') or {}).get('ic_moyen'), 3, True)} / {n((reg.get('tension') or {}).get('ic_moyen'), 3, True)} "
            f"| {n(r['stabilite'].get('annees_positives_pct'), 0, unite=' %')} | {e['total']['mois']} |")


def _tableau(section: dict) -> list[str]:
    h = section["horizon_reference"]
    lignes = [f"Horizon de référence : {h} mois · indice : {section.get('indice')} · séparation apprentissage / vérification : "
              f"{section.get('separation') or 'n. d.'} · période {section['periode']['debut']} → {section['periode']['fin']}, "
              f"{section['periode']['actifs']} actifs.", "",
              f"| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires ({h} m) | Meilleurs − indice ({h} m) "
              "| Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    ordre = {"Garder": 0, "Alléger": 1, "Supprimer": 2, "Données insuffisantes": 3}
    notes = [k for k in section["signaux"] if k.startswith(("note_", "score_")) or k == "equipondere"]
    autres = sorted((k for k in section["signaux"] if k not in notes), key=lambda k: (ordre.get(section["signaux"][k]["verdict"], 9), k))
    for k in autres + notes:
        lignes.append(_ligne_signal(section["signaux"][k]))
    lignes.append("")
    lignes.append("Raisons des verdicts :")
    for k in autres + notes:
        r = section["signaux"][k]
        lignes.append(f"- {r['libelle']} — {r['verdict']} : {r['raison']}.")
    return lignes


def _horizons(r: dict) -> list[str]:
    hs = list(r["horizons"])
    return ["| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |", "|---|---|---|---|---|---|---|---|"] + [
        f"| {h} mois | {n(r['horizons'][h]['ic_moyen'], 3, True)} | {n(r['horizons'][h]['ic_t'], 1)} | {n(r['horizons'][h]['haut_pct'], 2, True, ' %')} "
        f"| {n(r['horizons'][h]['bas_pct'], 2, True, ' %')} | {n(r['horizons'][h]['indice_pct'], 2, True, ' %')} "
        f"| {n(r['horizons'][h]['reussite_haut_pct'], 0, unite=' %')} | {n(r['horizons'][h]['reussite_bas_pct'], 0, unite=' %')} |" for h in hs]


NOTES_PRINCIPALES = ("note_globale", "note_recalibree", "score_chef", "score_recalibre")


def _v(r: dict, *chemin):
    for c in chemin:
        r = (r or {}).get(c)
    return r


def _cible_et_reference(section: dict) -> list[str]:
    """Pour chaque signal : part des actifs retenus (meilleurs 20 %) qui battent l'indice à 3 et 6 mois, rapport gain moyen /
    perte moyenne, et panier comparé à l'indice et au momentum seul hors échantillon."""
    ref = section.get("reference_momentum")
    if not ref:
        return []
    rv = ref.get("verification") or {}
    L = ["### Cible et comparaison au « momentum seul »", "",
         f"Référence « momentum seul » ({ref.get('regle')}) hors échantillon : {n(rv.get('rendement_annuel_pct'), 1, True, ' %/an')}, "
         f"soit {n(rv.get('vs_indice_annuel_pct'), 1, True, ' pt/an')} face à l'indice ({n(rv.get('indice_annuel_pct'), 1, True, ' %/an')}) ; "
         f"ses actifs retenus battent l'indice {n(_v(ref, 'cible', '3', 'battent_indice_pct'), 0, unite=' %')} du temps à 3 mois, "
         f"{n(_v(ref, 'cible', '6', 'battent_indice_pct'), 0, unite=' %')} à 6 mois (gain / perte {n(_v(ref, 'cible', '6', 'gain_perte'), 2)}).", "",
         "| Signal | Battent l'indice à 3 m | à 6 m | Gain / perte à 3 m | à 6 m | Panier − indice (/an, hors éch.) | Panier − momentum seul (/an, hors éch.) |",
         "|---|---|---|---|---|---|---|"]
    notes = [k for k in NOTES_PRINCIPALES if k in section["signaux"]]
    autres = sorted((k for k in section["signaux"] if k not in notes),
                    key=lambda k: -(_v(section["signaux"][k], "portefeuille", "verification", "vs_momentum_annuel_pct") or -99))
    for k in notes + autres:
        r = section["signaux"][k]
        h3, h6 = r["horizons"].get("3", {}), r["horizons"].get("6", {})
        pv = _v(r, "portefeuille", "verification") or {}
        gras = "**" if k in notes else ""
        L.append(f"| {gras}{r['libelle']}{gras} | {n(h3.get('battent_indice_pct'), 0, unite=' %')} | {n(h6.get('battent_indice_pct'), 0, unite=' %')} "
                 f"| {n(h3.get('gain_perte'), 2)} | {n(h6.get('gain_perte'), 2)} | {n(pv.get('vs_indice_annuel_pct'), 1, True, ' pt')} "
                 f"| {n(pv.get('vs_momentum_annuel_pct'), 1, True, ' pt')} |")
    return L + ["", "Gain / perte : gain moyen des actifs retenus qui battent l'indice ÷ perte moyenne de ceux qui font moins bien "
                "(au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).", ""]


def _combinaisons(section: dict) -> list[str]:
    c = section.get("combinaisons")
    if not c:
        return []
    L = ["### Combinaisons de signaux", "",
         f"Règle : {c['regle']}. Candidats ({len(c['candidats'])}) : " + (", ".join(x["libelle"] for x in c["candidats"]) or "aucun") + ". "
         f"{c['essais']} paires et triplets essayés, classés sur l'apprentissage seulement ; seuil de Bonferroni pour {c['essais']} essais : "
         f"t ≥ {n(c.get('seuil_t_bonferroni'), 2)} ({c.get('passent_bonferroni_apprentissage', 0)} combinaison(s) le franchissent sur l'apprentissage). "
         f"Les {len(c['retenues'])} meilleures sont jugées hors échantillon, avec une correction de Holm (seuil {n(c['alpha'], 2)}).", ""]
    if not c["retenues"]:
        return L + ["Aucune combinaison testable (pas assez de candidats ou d'actifs retenus).", ""]
    L += ["| Combinaison | Verdict | t apprentissage | Panier − indice (/an, hors éch.) | Panier − momentum seul | p corrigée | Battent l'indice 3 m / 6 m | Gain / perte 3 m / 6 m | Actifs retenus |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in c["retenues"]:
        v = _v(r, "comparaison", "verification") or {}
        cv = r.get("cible_verification") or r.get("cible") or {}
        L.append(f"| {r['libelle']} | **{r['verdict']}** | {n(r.get('t_apprentissage'), 1)} | {n(v.get('vs_indice_annuel_pct'), 1, True, ' pt')} "
                 f"| {n(v.get('vs_momentum_annuel_pct'), 1, True, ' pt')} | {n(r.get('p_holm'), 3)} "
                 f"| {n(_v(cv, '3', 'battent_indice_pct'), 0, unite=' %')} / {n(_v(cv, '6', 'battent_indice_pct'), 0, unite=' %')} "
                 f"| {n(_v(cv, '3', 'gain_perte'), 2)} / {n(_v(cv, '6', 'gain_perte'), 2)} | {n(r.get('taille_moyenne'), 1)} ({n(r.get('mois_avec_actifs_pct'), 0)} % des mois) |")
    return L + [""]


COURT = {"pays": "pays", "chef": "pays", "entreprises": "entreprises", "matieres": "matières", "secteurs": "secteurs"}


def resume_simple(res: dict) -> list[str]:
    """Résumé de dix lignes au plus, en langage simple, entièrement tiré des résultats."""
    sec = res["sections"]
    garder, envers, faibles = [], [], []
    for nom in ("pays", "chef", "entreprises", "matieres", "secteurs"):
        for k, r in (sec.get(nom) or {}).get("signaux", {}).items():
            if k in NOTES_PRINCIPALES or k == "equipondere" or k.startswith("famille_"):
                continue
            ic = _v(r, "echantillons", "verification", "ic_moyen") or 0
            nomme = f"{r['libelle']} ({COURT[nom]})"
            if r["verdict"] == "Garder":
                garder.append((ic, nomme))
            elif r["verdict"] == "Supprimer":
                t = _v(r, "echantillons", "verification", "ic_t") or 0
                (envers if t <= -2 else faibles).append((-ic, nomme))
    combis = [(nom, x) for nom in ("pays", "entreprises", "matieres") for x in ((sec.get(nom) or {}).get("combinaisons") or {}).get("retenues", [])]
    essais = sum(((sec.get(nom) or {}).get("combinaisons") or {}).get("essais", 0) for nom in ("pays", "entreprises", "matieres"))
    confirmees = [f"{x['libelle']} ({COURT[nom]})" for nom, x in combis if x["verdict"] == "Confirmée"]

    def ecart(vm, t):
        return n(vm, 1, True, " pt/an") + (", net" if t is not None and abs(t) >= 2 else ", non significatif")
    battent, battues = [], []
    for nom in ("pays", "chef", "entreprises", "matieres"):
        for k in NOTES_PRINCIPALES:
            r = (sec.get(nom) or {}).get("signaux", {}).get(k)
            pv = _v(r, "portefeuille", "verification") or {}
            vm = pv.get("vs_momentum_annuel_pct")
            if vm is not None:
                (battent if vm > 0 else battues).append(f"{r['libelle']} {COURT[nom]} ({ecart(vm, pv.get('t_vs_momentum'))})")
    n_notes = len(battent) + len(battues)
    for nom, x in combis:
        v = _v(x, "comparaison", "verification") or {}
        if (v.get("vs_momentum_annuel_pct") or 0) > 0 and x["verdict"] != "Non confirmée":
            battent.append(f"combinaison {x['libelle']} ({COURT[nom]}, {ecart(v['vs_momentum_annuel_pct'], v.get('t_vs_momentum'))})")
    mom = []
    for nom in ("pays", "entreprises", "matieres"):
        rv = _v(sec.get(nom), "reference_momentum", "verification")
        if rv and rv.get("vs_indice_annuel_pct") is not None:
            mom.append(f"{COURT[nom]} {n(rv['vs_indice_annuel_pct'], 1, True, ' pt/an')}")
    noms = lambda xs, k=5: ", ".join(x for _, x in sorted(xs, reverse=True)[:k]) or "rien"  # noqa: E731
    n_bat = n_notes - len(battues)
    bilan = (f"sur {n_notes} notes, {n_bat} font mieux que le momentum seul hors échantillon"
             + (" : la règle sans analyse reste la référence à battre." if n_bat * 2 < n_notes else " : les notes apportent quelque chose au-delà de la tendance.")) if n_notes else "pas de comparaison possible."
    return ["## En bref", "",
            f"1. **Ce qui anticipe** (« Garder », jugé hors échantillon) : {noms(garder)}.",
            f"2. **Combinaisons** : {essais} essais, confirmées après correction des essais multiples : {', '.join(confirmees) or 'aucune'}.",
            f"3. **Ce qui n'anticipe pas** (« Supprimer ») : {noms(faibles, 6)}" + (f", et {len(faibles) - 6} autres" if len(faibles) > 6 else "") + ".",
            f"4. **Ce qui marche à l'envers**, nettement (t ≤ −2) : {noms(envers, 4)}.",
            f"5. **Momentum seul** (meilleurs 20 % sur 12 mois hors dernier mois), face à l'indice hors échantillon : {', '.join(mom) or 'n. d.'}.",
            f"6. **Bat le momentum seul** (après frais, hors échantillon) : {', '.join(battent[:5]) or 'aucune note ni combinaison'}.",
            f"7. **Ne bat pas le momentum seul** : {', '.join(battues[:5]) or 'aucune note'}.",
            f"8. Bilan : {bilan}",
            "9. Prudence : univers actuel (biais du survivant), petits univers pour les pays et les matières, écarts souvent non significatifs.",
            "10. Rien n'est modifié automatiquement : toute nouvelle pondération passe par une pull request à valider."]


def conclusions_regles(chef: dict) -> list[str]:
    """Conclusions chiffrées sur les règles du chef d'orchestre et du trader (pays)."""
    rg = chef.get("regles") or {}
    h = str(rg.get("horizon_reference", 6))
    out = []
    v = (rg.get("verdicts") or {}).get("par_verdict", {}).get(h, {})
    if v:
        out.append(f"- **Seuils des verdicts** ({h} mois) : " + " ; ".join(
            f"{k} {n(x.get('relative_moyenne_pct'), 2, True, ' pt')} ({x.get('n', 0)} cas, réussite {n(x.get('reussite_pct'), 0, unite=' %')})"
            for k, x in v.items() if not k.startswith("_")) + (". Verdicts **ordonnés** (la performance relative croît avec le verdict)."
                                                              if v.get("_ordonne") else ". Verdicts **non ordonnés** : les seuils ne séparent pas nettement les pays."))
    c = (rg.get("verdicts") or {}).get("par_conviction", {}).get(h, {})
    if c:
        out.append("- **Conviction** (verdicts positifs) : " + " ; ".join(
            f"{k} : réussite {n(x.get('reussite_pct'), 0, unite=' %')}, {n(x.get('relative_moyenne_pct'), 2, True, ' pt')} ({x.get('n', 0)} cas)"
            for k, x in c.items()) + ".")
    g = (rg.get("verdicts") or {}).get("par_groupes", {}).get(h, {})
    if g:
        out.append("- **Groupes concordants** (seuil actuel : 3 pour « forte », 2 pour « moyenne ») : " + " ; ".join(
            f"{k} {n(x.get('reussite_pct'), 0, unite=' %')} ({x.get('n', 0)})" for k, x in g.items() if x.get("n")) + ".")
    td = (rg.get("tendance") or {}).get("horizons", {}).get(h)
    if td:
        sa, ex, au = td["forte_saine"], td["forte_en_exces"], td["autres"]
        ok = sa.get("relative_moyenne_pct") is not None and au.get("relative_moyenne_pct") is not None and sa["relative_moyenne_pct"] > au["relative_moyenne_pct"]
        out.append(f"- **Suivi de tendance** : tendances fortes saines {n(sa.get('relative_moyenne_pct'), 2, True, ' pt')} ({sa.get('n')} cas), "
                   f"tendances fortes en excès {n(ex.get('relative_moyenne_pct'), 2, True, ' pt')} ({ex.get('n')} cas), autres pays "
                   f"{n(au.get('relative_moyenne_pct'), 2, True, ' pt')} ({au.get('n')} cas). "
                   + ("Les tendances fortes saines **ont mieux fini** que les autres pays." if ok else
                      "Les tendances fortes saines **n'ont pas mieux fini** que les autres pays sur cet horizon."))
    co = rg.get("concentration") or {}
    if co.get("lignes"):
        out.append(f"- **Concentration du trader** (cœur pays, plafond {co.get('plafond_ligne_pct')} % par ligne, règle actuelle : "
                   f"{co.get('regle_actuelle')} lignes au plus ; hors échantillon) : " + " ; ".join(
                       f"{k} lignes {n(x['verification'].get('rendement_annuel_pct'), 1, True, ' %/an')}, Sharpe {n(x['verification'].get('sharpe'), 2)}, "
                       f"perte max {n(x['verification'].get('perte_max_pct'), 0, unite=' %')}" for k, x in co["lignes"].items())
                   + f" ; pays équipondérés {n(co['equipondere']['verification'].get('rendement_annuel_pct'), 1, True, ' %/an')}"
                   + (f" ; indice {n(co['indice']['verification'].get('rendement_annuel_pct'), 1, True, ' %/an')}" if co.get("indice") else "") + ".")
    return out


def conclusion_stops(st: dict) -> list[str]:
    if not st or not st.get("total", {}).get("positions"):
        return ["- Stops : pas assez de positions simulées."]
    v = st["verification"] if st["verification"].get("positions") else st["total"]
    aide = (v["moyenne_avec_pct"] or 0) >= (v["moyenne_sans_pct"] or 0)
    return [f"- **Stops et prise de bénéfices** ({st['lignes']} meilleures sociétés chaque mois, gardées {st['detention_mois']} mois ; "
            f"{v['positions']} positions hors échantillon) : avec les règles {n(v['moyenne_avec_pct'], 2, True, ' %')} en moyenne "
            f"(pire {n(v['pire_avec_pct'], 0, unite=' %')}, réussite {n(v['reussite_avec_pct'], 0, unite=' %')}), sans "
            f"{n(v['moyenne_sans_pct'], 2, True, ' %')} (pire {n(v['pire_sans_pct'], 0, unite=' %')}, réussite {n(v['reussite_sans_pct'], 0, unite=' %')}). "
            + ("Les stops **préservent ou améliorent** le rendement moyen." if aide else
               "Les stops **coûtent** du rendement moyen ; ils réduisent la dispersion "
               f"(écart-type {n(v['ecart_type_avec_pct'], 0, unite=' %')} contre {n(v['ecart_type_sans_pct'], 0, unite=' %')}) — arbitrage à juger."),
            "- Sorties : " + ", ".join(f"{k} {x}" for k, x in st.get("motifs", {}).items()) + "."]


def rapport_markdown(res: dict, prop: dict) -> str:
    L = [f"# Backtest des règles de notation — {res['jour'][:7]}", "",
         "Rapport produit automatiquement par l'agent backtest (`agents/backtest/`, méthode : `agents/backtest/methode.md`). "
         "Rééquilibrage mensuel ; meilleurs 20 % contre pires 20 % et contre l'indice de référence ; coefficient d'information "
         "(IC, corrélation de rang entre le signal et la performance future) ; frais de transaction inclus dans l'écart annuel. "
         "Les verdicts se jugent hors échantillon (seconde moitié de l'historique).", "",
         "**Rien n'est modifié automatiquement** : les nouvelles pondérations sont seulement proposées dans une pull request séparée.", "",
         "## Synthèse", ""]
    L.append(" · ".join(f"{k} : {v}" for k, v in sorted(res["verdicts"].items())) or "aucun signal mesuré")
    L.append("")
    for nom in ("pays", "entreprises", "matieres", "secteurs"):
        s = res["sections"].get(nom)
        if not s:
            L += [f"## {nom.capitalize()}", "", "Lot non calculé (source indisponible ou erreur : voir le journal du workflow).", ""]
            continue
        L += [f"## {s['titre']}", ""]
        b = s.get("biais_survivant") or {}
        if b.get("univers_complet_vs_indice_pct") is not None:
            texte = (f"**Biais du survivant mesuré** : l'univers actuel, équipondéré et rejoué dans le passé, fait "
                     f"{n(b['univers_complet_vs_indice_pct'], 1, True, ' pt/an')} par rapport à l'indice")
            if b.get("univers_retenu_vs_indice_pct") is not None:
                texte += (f" ; en ne gardant à chaque date que les sociétés valant déjà au moins {n(b['seuil_capitalisation_usd'] / 1e9, 0)} Md$ "
                          f"à cette date (univers testé, {n(b.get('societes_retenues_moyenne'), 0)} sociétés en moyenne), "
                          f"{n(b['univers_retenu_vs_indice_pct'], 1, True, ' pt/an')}")
            if nom == "entreprises":
                texte += (". Plus cet écart est grand, plus les signaux de qualité et de solidité sont faussés (les sociétés "
                          "faibles d'hier encore cotées aujourd'hui sont surtout celles qui ont réussi)")
            else:
                texte += (". Les pays suivis existent tous depuis le début : l'écart traduit surtout le poids des États-Unis dans "
                          "l'indice, pas un biais du survivant ; les signaux se jugent entre pays")
            L += [texte + ".", ""]
        L += _tableau(s) + [""] + _cible_et_reference(s) + _combinaisons(s)
        ng = s["signaux"].get("note_globale")
        if ng:
            L += ["Note globale actuelle, par horizon :", ""] + _horizons(ng) + [""]
        if nom == "entreprises":
            L += ["### Règles du trader (satellites)", ""] + conclusion_stops((s.get("regles") or {}).get("stops")) + [""]
        if nom == "secteurs" and s.get("phases"):
            L += ["Phases reconstituées (mois) : " + ", ".join(f"{k} {v}" for k, v in s["phases"].items()) + ".", ""]
        if nom == "pays" and res["sections"].get("chef"):
            ch = res["sections"]["chef"]
            L += ["## Chef d'orchestre (rejoué sur les pays)", "",
                  "Familles reconstituées : fondamentaux, valorisation, tendance, cycle ; les familles sans historique (flux, risque, "
                  "géopolitique, dynamique des résultats) sont retirées et les poids renormalisés. Régime de marché (VIX) → palier "
                  "Calme ou Tension pour les multiplicateurs de poids.", ""] + _tableau(ch) + [""] + _cible_et_reference(ch) + ["### Règles testées", ""] + conclusions_regles(ch) + [""]
    st = res["sections"].get("tendance")
    if st:
        from .tendance import resume
        L += [f"## {st['titre']}", "", "Seuils du suivi de tendance du chef d'orchestre et de la poche « tendance » du trader "
              "(agents/backtest/tendance.py).", ""] + resume(st.get("suivi_tendance")) + [""]
    L += ["## Note actuelle contre note recalibrée", "",
          "Poids réglés sur la première moitié de l'historique seulement, jugés sur la seconde. Une proposition n'est retenue que si la "
          "note recalibrée fait mieux hors échantillon (IC et écart après frais).", "",
          "| Agent | Section | IC hors échantillon actuel → recalibré | Écart après frais actuel → recalibré | Retenue | Raison |", "|---|---|---|---|---|---|"]
    for p in prop["propositions"]:
        a, r = p.get("note_actuelle") or {}, p.get("note_recalibree") or {}
        L.append(f"| {p['agent']} | {' → '.join(p['chemin'])} | {n(a.get('ic_verification'), 3, True)} → {n(r.get('ic_verification'), 3, True)} "
                 f"| {n(a.get('ecart_net_verification_pct'), 1, True, ' %')} → {n(r.get('ecart_net_verification_pct'), 1, True, ' %')} "
                 f"| {'oui' if p.get('retenue') else 'non'} | {p.get('raison', '')} |")
    L.append("")
    for p in prop["propositions"]:
        if p.get("retenue"):
            L.append(f"- `{p['fichier']}` ({' → '.join(p['chemin'])}) : " + ", ".join(
                f"{k} {p['actuel'].get(k)} → {v}" for k, v in p["propose"].items() if p["actuel"].get(k) != v))
    L += ["", "## Non testables (faute d'historique)", ""] + [f"- **{x['signal']}** ({x['agent']}) : {x['raison']}." for x in res["non_testables"]]
    L += ["", "## Biais et limites", "",
          "- **Biais du survivant** : l'univers est la liste actuelle (pays suivis, sociétés de l'agent entreprises). Les sociétés "
          "disparues, rachetées ou sorties de l'indice manquent, ce qui embellit surtout les signaux de qualité et de solidité "
          "(Z-score, F-score) et la performance absolue des paniers.",
          "- **Sur-ajustement** : les poids recalibrés sont réglés sur la seule première moitié et retenus seulement s'ils font mieux "
          "sur la seconde ; le retrait vers les poids actuels limite les écarts. Un IC de 0,02 à 0,05 est habituel pour un signal "
          "utile ; au-delà de 0,10, se méfier d'une erreur de données.",
          "- **Petits échantillons** : moins de 48 mois mesurés ou de 24 mois hors échantillon → « Données insuffisantes », sans conclusion. "
          "Les rendements à 6 et 12 mois se chevauchent d'un mois sur l'autre : la statistique t est corrigée (Newey-West).",
          "- **Données révisées** : FMI, OCDE (inflation, indicateur avancé) publient des séries révisées, sans les millésimes d'origine ; "
          "un retard de publication est appliqué, mais une révision ultérieure peut subsister. Les comptes SEC sont, eux, datés par leur dépôt.",
          "- **Approximations** : valorisation des pays par le rendement du dividende de l'ETF (le PER historique n'est pas gratuit), "
          "structure de la courbe par le portage des ETF à contrats, paliers de risque par le VIX.", "",
          "## Sources", ""] + [f"- {s['nom']} : {s['ok']} lecture(s) réussie(s), {s['echecs']} en échec" + (f" ({s['detail']})" if s.get("detail") else "")
                               for s in res["sources"]] + [""]
    L += resume_simple(res) + [""]
    return "\n".join(L)
