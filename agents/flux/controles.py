"""
Contrôles croisés de l'agent flux commerciaux.

1. États-Unis : statistiques officielles du Census Bureau (API « International Trade », échanges par
   pays partenaire). L'API exige une clé gratuite (secret GitHub CENSUS_API_KEY, demandée sur
   api.census.gov/data/key_signup.html). Sans clé, la déclaration des États-Unis relayée par le FMI
   (elle-même tirée du Census Bureau) sert de source officielle américaine.
2. Autres pays : la somme des exportations déclarées par un pays vers ses partenaires suivis ne doit
   jamais dépasser ses exportations totales (FMI, partenaire « Monde » ; à défaut Banque mondiale,
   total annuel comparé à la somme des 12 mois de la même année).
3. Écart > 10 % entre deux déclarations d'un même flux : « sources divergentes », la source officielle
   nationale est retenue (Census Bureau pour les flux des États-Unis).
   Variation sur 12 mois au-delà de ±40 % : « à vérifier », sauf si une seconde source donne une
   variation de même sens, elle aussi au-delà de ±40 %.

Séries : même format que agent.py, {(sens "X"|"M", déclarant ISO2, partenaire ISO2): {"AAAA-MM": dollars}}.
"""
from __future__ import annotations

from datetime import datetime

from agents.commun.journal import journal
from agents.commun.telechargement import ErreurSource

LOG = journal("agent-flux")
CENSUS_URL = "https://api.census.gov/data/timeseries/intltrade/{flux}/hs"
# Exportations : valeur FAS totale (ALL_VAL_MO) ; importations : importations générales, valeur en douane (GEN_VAL_MO)
CENSUS_CHAMPS = {"X": ("exports", "ALL_VAL_MO", "E_COMMODITY"), "M": ("imports", "GEN_VAL_MO", "I_COMMODITY")}
BANQUE_MONDIALE_URL = "https://api.worldbank.org/v2/country/{pays}/indicator/TX.VAL.MRCH.CD.WT"
MONDE = "_MONDE"


def _decaler(periode: str, mois: int) -> str:
    a, m = (int(x) for x in periode.split("-"))
    n = a * 12 + (m - 1) + mois
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


# ------------------------------------------------------------------ Census Bureau

def lire_census_mois(lecteur, sens: str, periode: str, codes: list[str], config: dict, cle: str) -> dict:
    """Un mois d'exportations (X) ou d'importations (M) des États-Unis par pays partenaire suivi."""
    flux, champ, commodite = CENSUS_CHAMPS[sens]
    par_code = {str(config["pays"][c]["census"]): c for c in codes if "census" in config["pays"][c]}
    lignes = lecteur.json(CENSUS_URL.format(flux=flux),
                          params={"get": f"CTY_CODE,CTY_NAME,{champ},{commodite}", "time": periode, "key": cle})
    if not isinstance(lignes, list) or len(lignes) < 2:
        raise ErreurSource(f"Census {flux} {periode} : réponse vide")
    entete = lignes[0]
    try:
        i_code, i_val, i_comm = entete.index("CTY_CODE"), entete.index(champ), entete.index(commodite)
    except ValueError as e:
        raise ErreurSource(f"Census {flux} : format inattendu ({entete})") from e
    res = {}
    for ligne in lignes[1:]:
        c = par_code.get(str(ligne[i_code]))
        if not c or str(ligne[i_comm]) not in ("-", "TOTAL", ""):
            continue  # on ne garde que le total tous produits
        try:
            res[(sens, "US", c)] = {periode: float(ligne[i_val])}
        except (TypeError, ValueError):
            continue
    return res


def lire_census(lecteur, codes: list[str], maintenant: datetime, config: dict, cle: str | None) -> dict:
    """Dernier mois publié par le Census Bureau (et le même mois un an plus tôt), exportations et importations."""
    if not cle:
        raise ErreurSource("clé CENSUS_API_KEY absente")
    courant = f"{maintenant.year:04d}-{maintenant.month:02d}"
    for k in range(1, 1 + config["controles"]["census_mois_essayes"]):
        p = _decaler(courant, -k)
        try:
            series = {**lire_census_mois(lecteur, "X", p, codes, config, cle), **lire_census_mois(lecteur, "M", p, codes, config, cle)}
        except ErreurSource as e:
            LOG.info("Census %s : %s", p, e)
            continue
        if len(series) < len(codes):  # pas encore publié pour l'essentiel des partenaires
            continue
        avant = _decaler(p, -12)
        for sens in ("X", "M"):
            for cle_serie, valeurs in lire_census_mois(lecteur, sens, avant, codes, config, cle).items():
                series.setdefault(cle_serie, {}).update(valeurs)
        return series
    raise ErreurSource("Census : aucun mois récent publié")


# ------------------------------------------------------------------ totaux

def totaux_banque_mondiale(lecteur, codes: list[str], config: dict) -> dict:
    """Exportations annuelles de marchandises (Banque mondiale, TX.VAL.MRCH.CD.WT) : {pays: {annee: dollars}}."""
    iso3 = {config["pays"][c]["iso3"]: c for c in codes}
    reponse = lecteur.json(BANQUE_MONDIALE_URL.format(pays=";".join(iso3)), params={"format": "json", "mrv": "3", "per_page": "500"})
    res: dict = {}
    for r in (reponse[1] if isinstance(reponse, list) and len(reponse) > 1 and reponse[1] else []):
        c = iso3.get(r.get("countryiso3code"))
        if c and r.get("value"):
            res.setdefault(c, {})[str(r["date"])] = float(r["value"])
    return res


def controler_totaux(series: dict, codes: list[str], banque_mondiale: dict | None = None) -> list[dict]:
    """Pour chaque pays déclarant : somme de ses exportations vers les partenaires suivis ≤ exportations totales.
    Total du FMI (partenaire « Monde ») au dernier mois déclaré ; à défaut, total annuel de la Banque mondiale
    comparé à la somme des 12 mois de la même année."""
    res = []
    for c in codes:
        vers = {b: series.get(("X", c, b)) or {} for b in codes if b != c}
        mois = sorted({p for s in vers.values() for p in s})
        if not mois:
            continue
        total_fmi = (series.get(("X", c, MONDE)) or {})
        p = mois[-1]
        if p in total_fmi:
            somme, total, source, periode = sum(s.get(p, 0) for s in vers.values()), total_fmi[p], "FMI (partenaire Monde)", p
        else:
            annees = sorted(a for a in (banque_mondiale or {}).get(c, {})
                            if all(f"{a}-{m:02d}" in mois for m in range(1, 13)))
            if not annees:
                res.append({"pays": c, "periode": p, "statut": "total indisponible"})
                continue
            a = annees[-1]
            somme = sum(s.get(f"{a}-{m:02d}", 0) for s in vers.values() for m in range(1, 13))
            total, source, periode = banque_mondiale[c][a], "Banque mondiale (total annuel)", a
        res.append({"pays": c, "periode": periode, "somme_partenaires_md": round(somme / 1e9, 2), "total_md": round(total / 1e9, 2),
                    "part_pct": round(somme / total * 100, 1) if total else None, "source_total": source,
                    "statut": "ok" if somme <= total else "somme supérieure au total"})
    return res


# ------------------------------------------------------------------ comparaisons

def ecart_pct(valeur: float, reference: float) -> float:
    return round(abs(valeur - reference) / reference * 100, 1) if reference else None


def variation(serie: dict, periode: str) -> float | None:
    avant = serie.get(_decaler(periode, -12))
    return round((serie[periode] / avant - 1) * 100, 1) if periode in serie and avant and avant > 0 else None


def confirmee(v: float, autres: list[float | None], seuil: float) -> bool:
    """Une forte variation est confirmée si une autre source va dans le même sens, elle aussi au-delà du seuil."""
    return any(a is not None and abs(a) > seuil and (a > 0) == (v > 0) for a in autres)
