"""
Note recalibrée et proposition de nouvelles pondérations.

Les poids sont réglés sur la première moitié de l'historique seulement (apprentissage), puis la note
recalibrée est comparée à la note actuelle sur la seconde moitié (hors échantillon). Rien n'est appliqué
automatiquement : `appliquer()` ne sert qu'à préparer la pull request séparée, validée à la main.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def recalibrer(resultats: dict[str, dict], poids: dict[str, float], cfg_rec: dict, decimales: int = 3) -> tuple[dict, dict]:
    """Nouveaux poids : facteur = IC d'apprentissage ÷ ic_reference (borné à [0, facteur_max]), mélangé au poids
    actuel (retrait). Un signal non testé ou aux données insuffisantes garde exactement son poids ; les signaux testés
    se répartissent leur total actuel (la somme de tous les poids est donc conservée)."""
    facteurs, detail = {}, {}
    for k, w in poids.items():
        r = resultats.get(k)
        if not r or r["verdict"] == "Données insuffisantes":
            detail[k] = "non testé ou données insuffisantes : poids inchangé"
            continue
        ic = r["echantillons"]["apprentissage"]["ic_moyen"] or 0.0
        f = max(0.0, min(cfg_rec["facteur_max"], ic / cfg_rec["ic_reference"]))
        facteurs[k] = cfg_rec["retrait"] + (1 - cfg_rec["retrait"]) * f
        detail[k] = f"IC d'apprentissage {ic:+.3f} → facteur {facteurs[k]:.2f}".replace(".", ",")
    brut = {k: poids[k] * f for k, f in facteurs.items()}
    somme, somme_b = sum(poids[k] for k in facteurs), sum(brut.values())
    if somme_b <= 0:
        return dict(poids), detail
    testes = {k: round(v * somme / somme_b, decimales) for k, v in brut.items()}
    # Arrondi : l'écart est reporté sur le plus gros poids testé, pour garder exactement la même somme
    ecart = round(somme - sum(testes.values()), decimales)
    if ecart:
        k = max(testes, key=testes.get)
        testes[k] = round(testes[k] + ecart, decimales)
    nouveaux = {k: testes.get(k, v) for k, v in poids.items()}
    if decimales == 0:
        nouveaux = {k: int(round(v)) for k, v in nouveaux.items()}
    return nouveaux, detail


def meilleure(actuelle: dict, recalibree: dict) -> tuple[bool, str]:
    """La note recalibrée n'est proposée que si elle fait mieux hors échantillon (IC et écart après frais)."""
    va, vr = actuelle["echantillons"]["verification"], recalibree["echantillons"]["verification"]
    ic_a, ic_r = va["ic_moyen"] or 0, vr["ic_moyen"] or 0
    n_a, n_r = va.get("ecart_net_annuel_pct") or 0, vr.get("ecart_net_annuel_pct") or 0
    if recalibree["verdict"] == "Données insuffisantes":
        return False, "données insuffisantes pour conclure"
    if ic_r > ic_a and n_r >= n_a:
        return True, (f"hors échantillon, IC {ic_a:+.3f} → {ic_r:+.3f} et écart après frais {n_a:+.1f} → {n_r:+.1f} %/an").replace(".", ",")
    return False, (f"pas d'amélioration hors échantillon (IC {ic_a:+.3f} → {ic_r:+.3f}, écart après frais "
                   f"{n_a:+.1f} → {n_r:+.1f} %/an) : pondérations actuelles conservées").replace(".", ",")


# ------------------------------------------------------------------ écriture dans les fichiers de configuration

def _fin_objet(texte: str, ouv: int) -> int:
    """Indice de l'accolade fermante de l'objet ouvert en `ouv` (chaînes JSON prises en compte)."""
    niveau, i, chaine = 0, ouv, False
    while i < len(texte):
        ch = texte[i]
        if chaine:
            if ch == "\\":
                i += 1
            elif ch == '"':
                chaine = False
        elif ch == '"':
            chaine = True
        elif ch == "{" or ch == "[":
            niveau += 1
        elif ch == "}" or ch == "]":
            niveau -= 1
            if niveau == 0:
                return i
        i += 1
    raise ValueError("JSON mal formé")


def _cle_directe(texte: str, ouv: int, fin: int, cle: str) -> int | None:
    """Position de l'accolade ouvrante de la valeur de `cle`, clé directe de l'objet [ouv, fin] (pas d'un objet imbriqué)."""
    motif = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*')
    i = ouv + 1
    while i < fin:
        m = motif.match(texte, i)
        if not m:
            i += 1
            continue
        j = m.end()
        if m.group(1) == cle and texte[j] == "{":
            return j
        # sauter la valeur : objet, tableau, chaîne ou scalaire
        if texte[j] in "{[":
            i = _fin_objet(texte, j) + 1
        elif texte[j] == '"':
            k = j + 1
            while texte[k] != '"':
                k += 2 if texte[k] == "\\" else 1
            i = k + 1
        else:
            i = j + 1
    return None


def _bloc(texte: str, chemin: list[str]) -> tuple[int, int]:
    """Position (accolade ouvrante, accolade fermante) de l'objet atteint par la suite de clés `chemin`, depuis la racine."""
    ouv = texte.index("{")
    fin = _fin_objet(texte, ouv)
    for cle in chemin:
        pos = _cle_directe(texte, ouv, fin, cle)
        if pos is None:
            raise KeyError(f"clé introuvable : {' → '.join(chemin)}")
        ouv, fin = pos, _fin_objet(texte, pos)
    return ouv, fin


def remplacer_valeurs(texte: str, chemin: list[str], valeurs: dict[str, float]) -> str:
    """Remplace les valeurs numériques des clés directes de l'objet `chemin`, sans toucher au reste du fichier
    (mise en forme, commentaires « _commentaire » et ordre conservés)."""
    a, b = _bloc(texte, chemin)
    morceau = texte[a:b]
    for cle, v in valeurs.items():
        motif = re.compile(r'("' + re.escape(cle) + r'"\s*:\s*)(-?\d+(?:\.\d+)?)')
        if not motif.search(morceau):
            raise KeyError(f"{cle} absent de {' → '.join(chemin)}")
        morceau = motif.sub(lambda m: m.group(1) + (str(v) if isinstance(v, int) else repr(float(v))), morceau, count=1)
    nouveau = texte[:a] + morceau + texte[b:]
    json.loads(nouveau)  # le fichier doit rester du JSON valide
    return nouveau


def appliquer(proposition: dict, racine: Path) -> list[str]:
    """Écrit les pondérations proposées (et retenues) dans les fichiers de configuration des agents.
    Utilisé seulement pour préparer la pull request séparée de proposition."""
    modifies = []
    for p in proposition.get("propositions", []):
        if not p.get("retenue"):
            continue
        chemin = Path(racine) / p["fichier"]
        texte = chemin.read_text(encoding="utf-8")
        changes = {k: v for k, v in p["propose"].items() if p["actuel"].get(k) != v}
        if not changes:
            continue
        nouveau = remplacer_valeurs(texte, p["chemin"], changes)
        verif = json.loads(nouveau)
        for cle in p["chemin"]:
            verif = verif[cle]
        if any(verif.get(k) != v for k, v in changes.items()):  # garde-fou : la bonne section a bien été modifiée
            raise ValueError(f"{p['fichier']} : section {' → '.join(p['chemin'])} mal repérée")
        chemin.write_text(nouveau, encoding="utf-8")
        modifies.append(p["fichier"])
    return sorted(set(modifies))
