/* ==========================================================================
   Pulsations du globe : flux d'investissement des ETF pays (cotés aux États-Unis)
   --------------------------------------------------------------------------
   Logique pure (sans DOM ni Three.js, testable sous Node) :
   - pour chaque pays, flux nets de l'ETF sur la période choisie dans le filtre,
     ou sur 1 semaine tant que cette période est « en cours de constitution » ;
   - seuil minimal (flux négligeables : pas de pulsation) ;
   - seuls les 10 flux les plus marqués (entrées ou sorties) pulsent ;
   - amplitude et vitesse proportionnelles au flux en % de l'encours, rapporté
     à l'échelle de la période (2 % sur une semaine ≈ 5 % sur un mois ≈ 10 % sur 3 mois).
   Données : p.detail.flux_etrangers.periodes (data/pays.json, agent pays).
   ========================================================================== */

/** Flux (en % de l'encours) donnant l'amplitude maximale, selon la période. */
export const ECHELLE_PULSATION = { '1s': 2, '1m': 5, '3m': 10 };
/** En dessous de ce flux (en % de l'encours), pas de pulsation. */
export const SEUIL_PULSATION = { '1s': 0.3, '1m': 0.75, '3m': 1.5 };
export const MAX_PULSATIONS = 10;
/** Vitesse d'un cycle (cycles par seconde) : de la plus lente (flux au seuil) à la plus rapide. */
export const VITESSE_MIN = 0.3, VITESSE_MAX = 1.1;

const LIBELLES = { '1s': '1 semaine', '1m': '1 mois', '3m': '3 mois' };
export const libellePeriode = (cle) => LIBELLES[cle] ?? cle;

/**
 * Flux d'un pays pour les pulsations :
 *   { etat: 'pret', periode, demandee, repli, pct, flux_musd, date, symbole }
 *   { etat: 'constitution', demandee, jours_disponibles, symbole }   historique insuffisant
 *   null                                                              pas d'ETF ni de relevé
 */
export function fluxPourPulsation(p, periode) {
  const f = p?.detail?.flux_etrangers;
  const periodes = f?.periodes;
  if (!periodes) return null;
  const demandee = periodes[periode]?.complet ? periode : null;
  const utilisee = demandee ?? (periodes['1s']?.complet ? '1s' : null);
  if (!utilisee || periodes[utilisee].pct_encours == null) {
    return { etat: 'constitution', demandee: periode, jours_disponibles: periodes[periode]?.jours_disponibles ?? 0, symbole: f.symbole };
  }
  const per = periodes[utilisee];
  return {
    etat: 'pret', periode: utilisee, demandee: periode, repli: utilisee !== periode,
    pct: per.pct_encours, flux_musd: per.flux_musd, date: f.date, debut: per.debut, symbole: f.symbole,
  };
}

/**
 * Les pays qui pulsent : au-dessus du seuil, les MAX_PULSATIONS flux les plus marqués
 * (en valeur absolue, rapportés à l'échelle de leur période).
 * Renvoie [{ code, nom, sens: 'entrees' | 'sorties', amplitude (0,25 à 1), vitesse, ...flux }].
 */
export function choisirPulsations(pays, periode, max = MAX_PULSATIONS) {
  const candidats = [];
  for (const p of pays ?? []) {
    const f = fluxPourPulsation(p, periode);
    if (f?.etat !== 'pret' || Math.abs(f.pct) < SEUIL_PULSATION[f.periode]) continue;
    candidats.push({ code: p.code, nom: p.nom, ...f, force: Math.abs(f.pct) / ECHELLE_PULSATION[f.periode] });
  }
  candidats.sort((a, b) => b.force - a.force || a.code.localeCompare(b.code));
  return candidats.slice(0, max).map((c) => {
    const t = Math.min(1, c.force);
    return { ...c, sens: c.pct > 0 ? 'entrees' : 'sorties', amplitude: 0.25 + 0.75 * t, vitesse: VITESSE_MIN + (VITESSE_MAX - VITESSE_MIN) * t };
  });
}

/** Pour la légende : combien de pays ont des flux, combien sont encore en cours de constitution. */
export function bilanPulsations(pays, periode) {
  let prets = 0, constitution = 0;
  for (const p of pays ?? []) {
    const f = fluxPourPulsation(p, periode);
    if (f?.etat === 'pret') prets += 1;
    else if (f?.etat === 'constitution') constitution += 1;
  }
  return { prets, constitution };
}
