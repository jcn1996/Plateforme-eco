"""
Récapitulatif de chaque exécution de l'agent pays : data/recap/pays-AAAA-MM-JJ.md

Contenu, rédigé de façon factuelle (ton contrôlé par textes.ton_conforme) :
1. ce qui a changé depuis l'exécution précédente ;
2. les principaux mouvements de notes ;
3. les divergences entre sources ;
4. les données manquantes ou anciennes ;
5. les sources en échec et les alertes « Qualité des données ».
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .notation import minuscule
from .textes import nb, ton_conforme

MOUVEMENT_MIN = 3  # écart de note (points) à partir duquel un mouvement est cité


def _indicateurs(p: dict) -> dict:
    return {**p.get("indicateurs", {}), **p.get("detail", {})}


def _valeur(ind: dict) -> str:
    v = ind.get("valeur")
    if v is None:
        return "n.d."
    unite = ind.get("unite") or ""
    return f"{nb(v)}{' ' + unite if unite else ''}"


def contenu(jour: date, objet: dict, ancien: dict | None, etats: dict) -> str:
    donnees = objet["donnees"]
    anciens = {p["code"]: p for p in (ancien or {}).get("donnees", [])}
    lignes = [f"# Agent pays : récapitulatif du {jour.strftime('%d/%m/%Y')}", "",
              f"- Exécution : {objet['meta']['genere_le']} (version {objet['meta'].get('version_agent', '?')})",
              f"- Pays suivis : {len(donnees)}",
              f"- Exécution précédente : {(ancien or {}).get('meta', {}).get('genere_le') or 'aucune (première exécution sur données réelles)'}",
              ""]

    # 1. Ce qui a changé
    lignes += ["## 1. Ce qui a changé", ""]
    changements = []
    if anciens:
        for p in donnees:
            a = _indicateurs(anciens.get(p["code"], {}))
            for cle, ind in _indicateurs(p).items():
                avant = a.get(cle, {})
                # Changement visible : valeur arrondie ou date de la donnée différente
                if (_valeur(ind), ind.get("date")) != (_valeur(avant), avant.get("date")) and \
                        (ind.get("valeur") is not None or avant.get("valeur") is not None):
                    changements.append(f"- {p['nom']}, {minuscule(ind['libelle'])} : {_valeur(avant)} → {_valeur(ind)}"
                                       f"{' (donnée du ' + str(ind['date']) + ')' if ind.get('date') else ''}")
    if not anciens:
        lignes.append("Première exécution comparable : aucun état antérieur sur données réelles.")
    elif changements:
        lignes.append(f"{len(changements)} valeurs modifiées.")
        lignes.append("")
        lignes += changements
    else:
        lignes.append("Aucune valeur modifiée.")
    lignes.append("")

    # 2. Mouvements de notes
    lignes += ["## 2. Principaux mouvements de notes", ""]
    mouvements = []
    for p in donnees:
        a = anciens.get(p["code"])
        if a and a.get("note") is not None and p.get("note") is not None and abs(p["note"] - a["note"]) >= MOUVEMENT_MIN:
            niveau = f", niveau {a.get('niveau')} → {p.get('niveau')}" if a.get("niveau") != p.get("niveau") else ""
            mouvements.append((abs(p["note"] - a["note"]), f"- {p['nom']} : {a['note']} → {p['note']} ({p['note'] - a['note']:+d} points{niveau})"))
    if mouvements:
        lignes += [m for _, m in sorted(mouvements, key=lambda x: -x[0])[:10]]
    else:
        lignes.append(f"Aucun mouvement de {MOUVEMENT_MIN} points ou plus." if anciens else "Sans objet (pas d'exécution précédente).")
    lignes.append("")

    # 3. Divergences entre sources
    lignes += ["## 3. Divergences entre sources", ""]
    divergences = []
    for p in donnees:
        for cle, ind in _indicateurs(p).items():
            if ind.get("verification") == "divergent" and ind.get("sources"):
                valeurs = " ; ".join(f"{s['nom'].split(',')[0]} {nb(s['valeur'])} ({s['date']})"
                                    for s in ind["sources"] if s["statut"] in ("retenue", "concorde", "diverge") and s.get("valeur") is not None)
                divergences.append(f"- {p['nom']}, {minuscule(ind['libelle'])} : {valeurs}. Valeur retenue : {_valeur(ind)} ; écart maximal {nb(ind.get('ecart_max') or 0, 2)} point(s).")
    lignes += divergences or ["Aucune divergence au-delà des tolérances."]
    lignes.append("")

    # 4. Données manquantes ou anciennes
    lignes += ["## 4. Données manquantes ou anciennes", ""]
    manquantes = []
    for p in donnees:
        absentes = [minuscule(ind["libelle"]) for cle, ind in p.get("indicateurs", {}).items() if ind.get("valeur") is None]
        anciennes = [minuscule(ind["libelle"]) for ind in _indicateurs(p).values() if ind.get("ancienne")]
        morceaux = []
        if absentes:
            morceaux.append("manquant : " + ", ".join(absentes))
        if anciennes:
            morceaux.append("valeur ancienne conservée : " + ", ".join(anciennes))
        if morceaux:
            manquantes.append(f"- {p['nom']} : " + " ; ".join(morceaux))
    lignes += manquantes or ["Aucune donnée principale manquante."]
    lignes.append("")

    # 5. Sources en échec et qualité des données
    lignes += ["## 5. Sources en échec et qualité des données", ""]
    erreurs = [f"- {k} : {v}" for k, v in etats.items() if v.startswith("erreur") or v == "vide" or v.startswith("partiel")]
    lignes += erreurs or ["Toutes les sources ont répondu."]
    lignes.append("")
    alertes = [p for p in donnees if p.get("qualite", {}).get("alerte")]
    if alertes:
        lignes.append("Alertes « Qualité des données » (plus d'un tiers des sources du pays en échec ou rejetées) :")
        lignes.append("")
        for p in alertes:
            q = p["qualite"]
            lignes.append(f"- {p['nom']} : {q['sources_en_echec']} sur {q['sources_consultees']} ({' ; '.join(q['details'])})")
    else:
        lignes.append("Aucune alerte « Qualité des données ».")
    lignes += ["", "_Document produit automatiquement par l'agent pays. Les notes sont des indicateurs de suivi, pas des recommandations._", ""]
    return "\n".join(lignes)


def ecrire(dossier: Path, jour: date, objet: dict, ancien: dict | None, etats: dict) -> Path:
    texte = contenu(jour, objet, ancien, etats)
    if not ton_conforme(texte):
        raise ValueError("Récapitulatif non conforme aux règles de conduite (mot interdit)")
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"pays-{jour.isoformat()}.md"
    chemin.write_text(texte, encoding="utf-8")
    return chemin
