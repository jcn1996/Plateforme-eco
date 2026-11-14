"""
Textes de l'agent pays : verdict (une phrase), lecture, « Ce qui pourrait me donner tort ».

Version 1 : textes produits par des règles (modèles de phrases à partir des chiffres).
Option : rédaction par l'API gratuite Gemini si la clé GEMINI_API_KEY est présente ;
en cas d'absence, d'erreur ou de texte non conforme, on garde les textes par règles.

Règles de conduite (vérifiées automatiquement) :
- analyse froide et factuelle, sans mots d'emphase (liste MOTS_INTERDITS) ;
- pas de conclusion forte sans au moins deux indicateurs concordants ;
- une donnée isolée et inhabituelle est signalée « à vérifier ».
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

from ..commun.journal import journal
from .notation import minuscule

LOG = journal("textes")

MOTS_INTERDITS = [
    "exceptionnel", "exceptionnelle", "exceptionnels", "exceptionnelles", "incontournable", "incontournables",
    "explosion", "explose", "exploser", "euphorie", "euphorique", "envolee", "flambee", "fulgurant", "fulgurante",
    "pepite", "garanti", "garantie", "a ne pas manquer", "historique", "spectaculaire", "formidable", "incroyable",
]


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")


def ton_conforme(texte: str) -> bool:
    """Vrai si le texte ne contient aucun mot interdit (accents et majuscules ignorés)."""
    t = _sans_accents(texte)
    return not any(re.search(rf"\b{re.escape(m)}\b", t) for m in MOTS_INTERDITS)


MOT_RETIRE = "[mot retiré]"


def neutraliser(texte: str) -> str:
    """Remplace chaque mot interdit par « [mot retiré] » (filet de sécurité : un texte généré non conforme
    ne doit jamais faire échouer tout l'agent). Les positions sont calculées caractère par caractère."""
    plat = "".join(_sans_accents(c)[:1] or c for c in texte)  # même longueur que le texte d'origine
    morceaux, pos = [], 0
    motif = re.compile(r"\b(" + "|".join(re.escape(m) for m in sorted(MOTS_INTERDITS, key=len, reverse=True)) + r")\b")
    for m in motif.finditer(plat):
        morceaux += [texte[pos:m.start()], MOT_RETIRE]
        pos = m.end()
    return "".join(morceaux) + texte[pos:]


def nb(x: float, decimales: int = 1, signe: bool = False) -> str:
    """Nombre au format français : 2,3 ; +4,1 ; −0,8."""
    texte = f"{abs(x):.{decimales}f}".replace(".", ",")
    if signe:
        return ("+" if x > 0 else "−" if x < 0 else "") + texte
    return ("−" if x < 0 else "") + texte


# ---------------------------------------------------------------------------
# Description courte d'un indicateur (utilisée dans les phrases)
# ---------------------------------------------------------------------------

def description(cle: str, ind: dict) -> str:
    v = ind["valeur"]
    if cle == "croissance_pib":
        selon = ind.get("source_courte", "le FMI")
        return f"croissance du PIB de {nb(v)} % en {ind.get('date', '')} selon {selon}" if v >= 0 else f"contraction du PIB de {nb(abs(v))} % en {ind.get('date', '')} selon {selon}"
    if cle == "indicateur_avance":
        pente = ind.get("pente_3_mois")
        sens = "" if pente is None else " et en hausse" if pente > 0.05 else " et en baisse" if pente < -0.05 else " et stable"
        return f"indicateur avancé de l'OCDE {'au-dessus' if v >= 100 else 'en dessous'} de 100 ({nb(v)}{sens})"
    if cle == "inflation":
        cible = ind.get("cible")
        return f"inflation à {nb(v)} %" + (f" pour une cible de {nb(cible)} %" if cible is not None else "")
    if cle == "taux_reel":
        direction = {"baisse": "qui baisse ses taux", "hausse": "qui relève ses taux", "stable": "aux taux stables"}.get(ind.get("direction"), "")
        return f"taux réel de {nb(v, signe=True)} pt (banque centrale {direction})"
    if cle == "valorisation":
        return f"PER {'supérieur' if v > 0 else 'inférieur'} de {nb(abs(v), 0)} % à la médiane des pays suivis"
    if cle == "momentum":
        if ind.get("base") == "indice":
            eur = ind.get("performance_eur")
            return (f"{ind.get('indice', 'indice national')} à {nb(v, signe=True)} % sur 12 mois en monnaie locale"
                    + (f" ({nb(eur, signe=True)} % en euros)" if eur is not None and ind.get("monnaie") != "EUR" else ""))
        return f"marché à {nb(v, signe=True)} % sur 12 mois (ETF en dollars)"
    if cle == "devise_3m":
        return f"devise à {nb(v, signe=True)} % contre le dollar sur 3 mois"
    if cle == "solde_courant":
        return f"solde courant de {nb(v, signe=True)} % du PIB"
    if cle == "flux_etrangers":
        periode = {"1m": "un mois", "1s": "une semaine"}.get(ind.get("periode_valeur"), "la période")
        sens = "entrées" if v > 0 else "sorties"
        texte = f"{sens} nettes sur l'ETF {ind.get('symbole', '')} de {nb(abs(v))} % de l'encours sur {periode} (ETF cotés aux États-Unis)"
        return texte + (" ; position possiblement encombrée" if ind.get("encombrement") else "")
    if cle == "activite_reelle":
        return (f"activité réelle « {ind.get('lecture')} » selon {ind.get('indicateurs_utilises')} indicateurs alternatifs "
                f"(score {nb(v, 0)}/100)")
    return ind.get("libelle", cle)


def _classer(indicateurs: dict, cles: list[str]):
    disponibles = [(k, indicateurs[k]) for k in cles if indicateurs.get(k, {}).get("note") is not None]
    forces = sorted([x for x in disponibles if x[1]["note"] >= 65], key=lambda x: -x[1]["note"])
    faiblesses = sorted([x for x in disponibles if x[1]["note"] < 50], key=lambda x: x[1]["note"])
    return forces, faiblesses


# ---------------------------------------------------------------------------
# Textes par règles
# ---------------------------------------------------------------------------

def verdict(nom: str, note: int, indicateurs: dict, cles: list[str], ramenee: bool, brute: float | None = None) -> str:
    forces, faiblesses = _classer(indicateurs, cles)
    f = [description(k, i) for k, i in forces]
    d = [description(k, i) for k, i in faiblesses]
    if note is None:
        return f"{nom} : données insuffisantes pour conclure."
    if note >= 65:
        vigilance = d[0] if d else "aucun indicateur défavorable à ce stade"
        return f"{nom} : {f[0]} et {f[1]} soutiennent la note ; point de vigilance : {vigilance}."
    if note < 50:
        appui = f" ; appui : {f[0]}" if f else ""
        return f"{nom} : {d[0]} et {d[1]} pèsent sur la note{appui}."
    if ramenee:
        negatif = brute is not None and brute < 50
        isole = ((d if negatif else f) or f or d or ["un seul indicateur marqué"])[0]
        sens = "défavorable" if negatif else "favorable"
        return f"{nom} : un seul signal {sens} net, {isole}, sans confirmation par un second indicateur ; note maintenue en zone neutre."
    pour = f[0] if f else "aucun indicateur nettement favorable"
    contre = d[0] if d else "aucun point faible marqué"
    return f"{nom} : signaux partagés, avec d'un côté {pour}, de l'autre {contre}."


def lecture(indicateurs: dict, detail: dict) -> dict:
    """Trois paragraphes courts et factuels."""
    def phrase(cles, source):
        morceaux = [description(k, source[k]) for k in cles if source.get(k, {}).get("valeur") is not None]
        return (morceaux[0][0].upper() + " ; ".join(morceaux)[1:] + ".") if morceaux else "Données indisponibles."
    tout = {**indicateurs, **detail}
    return {
        "activite_et_prix": phrase(["croissance_pib", "indicateur_avance", "activite_reelle", "inflation"], tout),
        "politique_monetaire_et_risques": phrase(["taux_reel", "devise_3m", "solde_courant"], tout),
        "marches": phrase(["momentum", "valorisation", "flux_etrangers"], tout),
    }


CONTRE_SI_FORCE = {
    "croissance_pib": "une révision en baisse de la croissance par le FMI",
    "indicateur_avance": "un passage de l'indicateur avancé de l'OCDE sous 100",
    "inflation": "un nouvel écart de l'inflation par rapport à la cible",
    "taux_reel": "un retournement de la politique de la banque centrale",
    "valorisation": "une décote qui refléterait en fait une baisse des bénéfices attendus",
    "momentum": "un repli du marché qui effacerait la performance des 12 derniers mois",
    "activite_reelle": "un retournement des indicateurs d'activité réelle (transport, énergie, emploi) lors des prochains relevés",
}
CONTRE_SI_FAIBLESSE = {
    "croissance_pib": "une reprise de l'activité plus rapide que les prévisions du FMI",
    "indicateur_avance": "un redressement de l'indicateur avancé au-dessus de 100",
    "inflation": "un retour de l'inflation vers la cible plus rapide que prévu",
    "taux_reel": "un ajustement de la politique monétaire qui ramènerait le taux réel en zone neutre",
    "valorisation": "des bénéfices supérieurs aux attentes qui justifieraient la prime de valorisation",
    "momentum": "un rebond du marché après la baisse des 12 derniers mois",
    "activite_reelle": "un redressement des indicateurs d'activité réelle (transport, énergie, emploi) lors des prochains relevés",
}


def contre_scenario(note: int, indicateurs: dict, cles: list[str], confiance: dict) -> list[str]:
    """« Ce qui pourrait me donner tort » : 2 à 3 éléments concrets."""
    forces, faiblesses = _classer(indicateurs, cles)
    points = []
    if note is not None and note >= 50:
        points += [CONTRE_SI_FORCE[k] for k, _ in forces[:2]]
    if note is not None and note < 65:
        points += [CONTRE_SI_FAIBLESSE[k] for k, _ in faiblesses[:2]]
    for k in cles:
        ind = indicateurs.get(k, {})
        if ind.get("a_verifier"):
            points.insert(0, f"la valeur « {minuscule(ind['libelle'])} » ({nb(ind['valeur'])}) est inhabituelle et reste à vérifier")
        if ind.get("verification") == "divergent" and ind.get("valeur") is not None:
            autres = [s for s in ind.get("sources", []) if s.get("statut") == "diverge" and s.get("valeur") is not None]
            detail = f" ({autres[0]['nom'].split(',')[0]} : {nb(autres[0]['valeur'])})" if autres else ""
            points.insert(0, f"les sources divergent sur « {minuscule(ind['libelle'])} »{detail} : la valeur retenue ({nb(ind['valeur'])}) pourrait être révisée")
    manquants = [minuscule(indicateurs[k]["libelle"]) for k in cles if indicateurs.get(k, {}).get("note") is None]
    if manquants:
        points.append("des données manquantes (" + ", ".join(manquants) + ") qui pourraient modifier l'analyse")
    if not points:
        points.append("un changement simultané de plusieurs indicateurs lors des prochaines publications")
    # Sans doublon, 3 au plus
    vus, resultat = set(), []
    for p in points:
        if p not in vus:
            vus.add(p)
            resultat.append(p[0].upper() + p[1:] + ".")
    return resultat[:3]


# ---------------------------------------------------------------------------
# Option : rédaction par Gemini (si la clé GEMINI_API_KEY est fournie)
# ---------------------------------------------------------------------------

def rediger_avec_gemini(nom: str, note: int, indicateurs: dict, confiance: dict, modele: str) -> dict | None:
    """Demande à Gemini un verdict et un contre-scénario à partir des chiffres.
    Renvoie None (on garde les textes par règles) si la clé manque, en cas
    d'erreur, ou si le texte ne respecte pas les règles de conduite."""
    cle = os.environ.get("GEMINI_API_KEY")
    if not cle:
        return None
    import requests
    chiffres = {k: {"libelle": v["libelle"], "valeur": v.get("valeur"), "note": v.get("note"), "date": v.get("date")}
                for k, v in indicateurs.items()}
    consigne = (
        "Tu es un analyste macroéconomique prudent. Rédige en français, ton froid et factuel, sans emphase "
        f"(mots interdits : {', '.join(MOTS_INTERDITS[:12])}…). Ne conclus fortement que si deux indicateurs au moins concordent. "
        "Réponds uniquement en JSON : {\"verdict\": \"une seule phrase\", \"contre_scenario\": [\"2 ou 3 éléments\"]}.\n"
        f"Pays : {nom}. Note globale : {note}/100. Confiance : {confiance['niveau']}. Indicateurs : {json.dumps(chiffres, ensure_ascii=False)}"
    )
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent",
            params={"key": cle}, timeout=30,
            json={"contents": [{"parts": [{"text": consigne}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}},
        )
        r.raise_for_status()
        texte = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        resultat = json.loads(texte)
        v, c = resultat.get("verdict"), resultat.get("contre_scenario")
        valide = (isinstance(v, str) and 20 < len(v) < 260 and isinstance(c, list) and 1 <= len(c) <= 3
                  and all(isinstance(x, str) for x in c) and ton_conforme(v) and all(ton_conforme(x) for x in c))
        if not valide:
            LOG.warning("Texte Gemini non conforme pour %s : textes par règles conservés", nom)
            return None
        return {"verdict": v.strip(), "contre_scenario": [x.strip() for x in c]}
    except Exception as e:
        LOG.warning("Gemini indisponible pour %s (%s) : textes par règles conservés", nom, str(e)[:120])
        return None
