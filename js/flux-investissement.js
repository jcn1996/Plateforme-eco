/* ==========================================================================
   Flux d'investissement des ETF pays (cotés aux États-Unis), agent pays
   --------------------------------------------------------------------------
   - filtre du globe « Flux d'investissement » : couleur selon les flux nets
     de la période choisie, en % de l'encours de l'ETF (vert = entrées,
     rouge = sorties, intensité selon l'ampleur), sélecteur 1 sem. / 1 mois / 3 mois ;
   - bloc « Flux d'investissement » de la fiche pays : trois périodes, flux
     cumulés (petit graphique), série de jours, source et date.
   Données : p.detail.flux_etrangers (data/pays.json).
   ========================================================================== */

import { el, svg, nombre, variation } from './outils.js';
import { lirePreference, memoriserPreference } from './interface.js';

export const PERIODES_FLUX = [
  { cle: '1s', libelle: '1 sem.', long: '1 semaine' },
  { cle: '1m', libelle: '1 mois', long: '1 mois' },
  { cle: '3m', libelle: '3 mois', long: '3 mois' },
];
export const METRIQUE_FLUX = { cle: 'flux_investissement', libelle: 'Flux d’investissement', court: 'Flux', source: 'flux' };

/** Ampleur (en % de l'encours) qui donne la couleur la plus intense, selon la période. */
const ECHELLE = { '1s': 2, '1m': 5, '3m': 10 };
/* Teintes de la carte (mêmes que js/globe.js) : neutre gris bleu au milieu, vert et rouge aux extrémités */
const NEUTRE = [0x2a, 0x42, 0x58];
const ENTREES = [0x1f, 0xbf, 0x7a];
const SORTIES = [0xf0, 0x56, 0x4a];
const CLE_PERIODE = 'salle-controle:flux-periode';
const SEUIL_STABLE = 0.25; // en % de l'encours : en dessous, flux « stables » (même seuil que l'agent)

let periode = lirePreference(CLE_PERIODE, '1m');
if (!PERIODES_FLUX.some((p) => p.cle === periode)) periode = '1m';
export const periodeFlux = () => periode;

const melange = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
const versHex = ([r, g, b]) => (r << 16) | (g << 8) | b;

/** Couleur d'un pays : intensité proportionnelle à l'ampleur, plafonnée à l'échelle de la période. */
export function couleurFlux(pct, cle = periode) {
  const t = Math.min(1, Math.abs(pct) / ECHELLE[cle]);
  return versHex(melange(NEUTRE, pct >= 0 ? ENTREES : SORTIES, 0.25 + 0.75 * t));
}

/** Lecture pour le globe : { note, texte, couleur } ou null (pas d'ETF, pas de relevé). */
export function lireFlux(p, cle = periode) {
  const f = p.detail?.flux_etrangers;
  const per = f?.periodes?.[cle];
  if (!per || per.pct_encours == null) return null;
  if (!per.complet) return { valeur: null, note: 50, niveau: 'neutre', texte: 'en constitution', couleur: versHex(NEUTRE) };
  const pct = per.pct_encours;
  // Étiquette : verte pour des entrées, rouge pour des sorties, ambre si presque nul
  const niveau = pct >= SEUIL_STABLE ? 'attractif' : pct <= -SEUIL_STABLE ? 'defavorable' : 'neutre';
  return { valeur: pct, note: Math.max(0, Math.min(100, 50 + 10 * pct)), niveau, texte: variation(pct, 1), couleur: couleurFlux(pct, cle) };
}

/** Sélecteur de période du filtre (puces 1 sem. / 1 mois / 3 mois), choix mémorisé sur l'appareil. */
export function initialiserPeriodeFlux(noeud, surChangement) {
  const boutons = PERIODES_FLUX.map((p) => el('button', {
    type: 'button', role: 'radio', 'data-cle': p.cle, 'aria-label': `Flux sur ${p.long}`,
    onclick: () => choisir(p.cle),
  }, p.libelle));
  noeud.replaceChildren(...boutons);
  function choisir(cle, initial = false) {
    periode = cle;
    boutons.forEach((b) => b.setAttribute('aria-checked', String(b.dataset.cle === cle)));
    if (!initial) { memoriserPreference(CLE_PERIODE, cle); surChangement(cle); }
  }
  choisir(periode, true);
}

/* ------------------------------------------------------------------ fiche pays */

const dateFr = (d) => (d ? new Date(`${d}T12:00:00Z`).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }) : '');
const millions = (m) => `${variation(m, Math.abs(m) >= 100 ? 0 : 1, '')} M$`;

/** Une période : flux en M$ et en % de l'encours, ou « en cours de constitution ». */
function tuilePeriode(cle, per) {
  const lib = PERIODES_FLUX.find((p) => p.cle === cle)?.long ?? cle;
  if (!per) return null;
  const complet = per.complet;
  const sens = per.pct_encours > 0 ? 'hausse' : per.pct_encours < 0 ? 'baisse' : '';
  return el('div', { class: `flux-periode-tuile${complet ? '' : ' flux-periode-tuile--partielle'}` },
    el('div', { class: 'stat-libelle' }, lib),
    complet
      ? el('div', { class: `flux-periode-valeur mono ${sens}` }, variation(per.pct_encours, 2))
      : el('div', { class: 'flux-periode-valeur flux-periode-valeur--attente' }, 'en cours de constitution'),
    el('div', { class: 'flux-periode-detail mono' }, complet
      ? millions(per.flux_musd)
      : `${per.jours_disponibles} j de relevés sur ${per.jours}`),
  );
}

/**
 * Petit graphique des flux cumulés (M$), une seule série : ligne de 2 px, ligne du zéro,
 * réticule et valeur au survol ou au toucher.
 */
function graphiqueCumul(points) {
  if (!points || points.length < 2) return null;
  const L = 320, H = 96, mg = { g: 4, d: 4, h: 8, b: 8 };
  const valeurs = points.map((p) => p[1]);
  const min = Math.min(0, ...valeurs), max = Math.max(0, ...valeurs);
  const ecart = max - min || 1;
  const x = (i) => mg.g + (i / (points.length - 1)) * (L - mg.g - mg.d);
  const y = (v) => mg.h + (1 - (v - min) / ecart) * (H - mg.h - mg.b);
  const trace = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
  const dernier = valeurs.at(-1);
  const reticule = svg('line', { class: 'flux-graphique-reticule', y1: mg.h, y2: H - mg.b, x1: -10, x2: -10 });
  const point = svg('circle', { class: 'flux-graphique-point', r: 4, cx: -10, cy: -10 });
  const bulle = el('div', { class: 'flux-graphique-bulle mono', hidden: true });
  const zone = svg('rect', { x: 0, y: 0, width: L, height: H, fill: 'transparent' });
  const graphique = svg('svg', { viewBox: `0 0 ${L} ${H}`, class: 'flux-graphique-svg', role: 'img',
    'aria-label': `Flux cumulés de ${dateFr(points[0][0])} à ${dateFr(points.at(-1)[0])} : ${millions(dernier)}` },
    svg('line', { class: 'flux-graphique-zero', x1: mg.g, x2: L - mg.d, y1: y(0), y2: y(0) }),
    svg('path', { class: `flux-graphique-ligne ${dernier >= 0 ? 'flux-graphique-ligne--entrees' : 'flux-graphique-ligne--sorties'}`, d: trace }),
    reticule, point, zone,
  );
  const montrer = (e) => {
    const r = graphique.getBoundingClientRect();
    const i = Math.max(0, Math.min(points.length - 1, Math.round(((e.clientX - r.left) / r.width * L - mg.g) / (L - mg.g - mg.d) * (points.length - 1))));
    const px = x(i), py = y(points[i][1]);
    reticule.setAttribute('x1', px); reticule.setAttribute('x2', px);
    point.setAttribute('cx', px); point.setAttribute('cy', py);
    bulle.textContent = `${dateFr(points[i][0])} · ${millions(points[i][1])}`;
    bulle.hidden = false;
    bulle.style.left = `${Math.min(Math.max(0, (px / L) * r.width - 60), r.width - 150)}px`;
  };
  const cacher = () => { bulle.hidden = true; reticule.setAttribute('x1', -10); reticule.setAttribute('x2', -10); point.setAttribute('cx', -10); };
  graphique.addEventListener('pointermove', montrer);
  graphique.addEventListener('pointerdown', montrer);
  graphique.addEventListener('pointerleave', cacher);
  return el('figure', { class: 'flux-graphique' },
    el('figcaption', {}, 'Flux cumulés depuis le ', dateFr(points[0][0]), ' : ', el('strong', { class: 'mono' }, millions(dernier))),
    el('div', { class: 'flux-graphique-cadre' }, graphique, bulle),
  );
}

/** Bloc « Flux d'investissement » de la fiche pays. */
export function sectionFluxPays(p) {
  const f = p.detail?.flux_etrangers;
  if (!f) return null;
  const titre = el('h3', { class: 'section-titre' }, 'Flux d’investissement',
    el('small', {}, f.symbole ? `ETF ${f.symbole}${f.emetteur ? ` (${f.emetteur})` : ''} · % de l’encours` : 'ETF pays coté aux États-Unis'));
  if (!f.periodes) {
    return el('section', { class: 'flux-pays' }, titre, el('p', { class: 'fiche-verdict' }, `Non disponible : ${f.raison ?? 'pas de relevé'}.`),
      el('p', { class: 'flux-avertissement' }, f.avertissement ?? ''));
  }
  const serie = f.serie_consecutive;
  return el('section', { class: 'flux-pays' },
    titre,
    f.ancienne ? el('p', { class: 'flux-alerte' }, f.raison_ancienne) : null,
    el('div', { class: 'stats flux-periodes' }, PERIODES_FLUX.map((x) => tuilePeriode(x.cle, f.periodes[x.cle]))),
    f.encombrement?.signale ? el('p', { class: 'flux-alerte', role: 'status' }, '⚠ ', f.encombrement.texte) : null,
    el('p', { class: 'flux-resume' },
      serie ? `${serie.jours} jour${serie.jours > 1 ? 's' : ''} de bourse consécutif${serie.jours > 1 ? 's' : ''} de ${serie.sens} (depuis le ${dateFr(serie.depuis)})`
        : f.releves > 1 ? 'Aucune création ni aucun rachat de parts relevé' : 'Premier relevé : les flux se calculent à partir du jour de bourse suivant',
      f.encours_musd != null ? ` · encours ${nombre(f.encours_musd >= 1000 ? f.encours_musd / 1000 : f.encours_musd, 1)} ${f.encours_musd >= 1000 ? 'Md$' : 'M$'}` : '',
      f.note != null ? ` · note ${f.note}/100` : '',
      f.tendance_flux ? ` · ${f.tendance_flux}` : ''),
    graphiqueCumul(f.cumul),
    el('p', { class: 'source-raison' },
      `Source : ${f.source ?? f.source_courte ?? 'émetteur'}. Relevé du ${dateFr(f.date)} (${f.releves} relevé${f.releves > 1 ? 's' : ''} depuis le ${dateFr(f.premier_releve)}). `
      + 'Flux = variation du nombre de parts en circulation × valeur liquidative du jour.'),
    el('p', { class: 'flux-avertissement' }, f.avertissement ?? ''),
  );
}
