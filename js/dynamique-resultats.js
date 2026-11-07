/* ==========================================================================
   Bloc « Dynamique des résultats » de la fiche entreprise (agent entreprises) :
   dernière guidance de la direction (badge, citation, liens SEC), évolution des
   estimations de BPA sur 90 jours (petit graphique), révisions, surprises des
   4 derniers trimestres, objectifs de cours des analystes (pour information).
   Données : e.dynamique (fiche data/entreprises/fiches/<ticker>.json).
   Aussi : badge « guidance relevée / abaissée » de l'écran Pépites.
   ========================================================================== */

import { el, svg, nombre, variation } from './outils.js';
import { titreSection } from './panneau-pays.js';

const PERIODES = { '0q': 'Trimestre en cours', '+1q': 'Trimestre suivant', '0y': 'Exercice en cours', '+1y': 'Exercice suivant' };
const PERIODES_COURTES = { '0q': 'Trim. en cours', '+1q': 'Trim. suivant', '0y': 'Exercice en cours', '+1y': 'Exercice suivant' };
const POINTS = [['90j', -90], ['60j', -60], ['30j', -30], ['7j', -7], ['actuel', 0]];
const SENS_EVOLUTION = { 'relevée': 'pos', 'initiée': 'neutre', 'maintenue': 'neutre', 'abaissée': 'neg', 'retirée': 'neg' };
const STATUTS = {
  'non disponible': 'Guidance non disponible : pas de source structurée gratuite hors États-Unis.',
  'non analysée': 'Guidance non analysée : le dernier communiqué de résultats sera analysé à la prochaine exécution.',
  'aucune guidance': 'Aucune guidance dans le dernier communiqué de résultats déposé à la SEC.',
};

function dateFr(d) {
  if (!d) return 'date inconnue';
  const s = String(d);
  return `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
}

/** Badge d'évolution de la guidance (relevée, maintenue, abaissée, initiée, retirée). */
export function badgeGuidance(evolution, date) {
  if (!evolution) return null;
  return el('span', { class: `badge-guidance badge-guidance--${SENS_EVOLUTION[evolution] ?? 'neutre'}`, title: date ? `Communiqué du ${dateFr(date)}` : null },
    `Guidance ${evolution}`);
}

export function blocDynamique(b) {
  if (!b) return null;
  return el('section', { class: 'carte dynamique' },
    titreSection('Dynamique des résultats', b.note != null ? `${b.note}/100 · confiance ${b.confiance}` : 'non disponible'),
    el('p', { class: 'fiche-verdict' }, b.texte),
    b.fiabilite === 'indicative' ? el('p', { class: 'reco-reserve' },
      `Suivie par moins de 3 analystes (${b.analystes ?? 0}) : estimations, révisions et surprises affichées à titre indicatif seulement (faible fiabilité), hors note.`) : null,
    blocGuidance(b.guidance),
    blocEstimations(b),
    blocSurprises(b.surprises),
    blocObjectifs(b.objectifs),
    b.contre?.length ? [el('h4', {}, 'Ce qui pourrait me donner tort'), el('ul', { class: 'contre-scenario' }, b.contre.map((t) => el('li', {}, t)))] : null,
    el('p', { class: 'fraicheur' },
      'Sources : ', b.guidance?.statut === 'non disponible' ? '' : 'SEC (communiqués 8-K Item 2.02, extraction par Gemini avec citation obligatoire) ; ',
      `Yahoo Finance (analystes${b.maj_analystes ? `, relevé du ${dateFr(b.maj_analystes)}` : ''}).`),
  );
}

function blocGuidance(g) {
  if (!g) return null;
  const r = g.retenue;
  const d = g.dernier;
  const liens = (c) => [
    c?.url_communique ? el('a', { href: c.url_communique, target: '_blank', rel: 'noopener' }, 'Communiqué (SEC) ↗') : null,
    c?.url_depot ? el('a', { href: c.url_depot, target: '_blank', rel: 'noopener' }, 'Dépôt 8-K ↗') : null,
  ].filter(Boolean);
  const enAttente = d && d.statut !== 'analysée' && (!r || d.date > r.date);
  return el('div', { class: 'dynamique-guidance' },
    el('h4', {}, 'Guidance de la direction', r ? [' ', badgeGuidance(r.evolution, r.date)] : null),
    r ? [
      el('p', { class: 'fiche-verdict' }, `Communiqué de résultats du ${dateFr(r.date)}`, r.modele ? ' · extraction automatique, citations vérifiées dans le texte' : ''),
      el('ul', { class: 'liste-guidances' }, (r.guidances ?? []).map((x) => el('li', {},
        el('div', { class: 'guidance-ligne' },
          el('strong', {}, x.libelle), x.periode ? ` · ${x.periode}` : '', ' : ', el('span', { class: 'mono' }, x.valeur || '—'), ' ',
          badgeGuidance(x.evolution)),
        x.precedente ? el('small', {}, `Précédente (${dateFr(x.precedente.date)}) : ${x.precedente.valeur ?? 'n. d.'}`) : null,
        el('blockquote', { class: 'guidance-citation', lang: 'en' }, `« ${x.citation} »`,
          x.url ? [' ', el('a', { href: x.url, target: '_blank', rel: 'noopener' }, 'source ↗')] : null),
      ))),
      el('p', { class: 'liens-sec' }, liens(r)),
    ] : el('p', { class: 'fiche-verdict' }, STATUTS[g.statut] ?? g.raison ?? 'Guidance non disponible.',
      g.raison && STATUTS[g.statut] && g.statut !== 'non disponible' ? ` (${g.raison})` : ''),
    enAttente && r ? el('p', { class: 'reco-reserve' }, `Communiqué plus récent (${dateFr(d.date)}) : ${d.statut}${d.raison ? ` (${d.raison})` : ''}.`) : null,
    !r && d ? el('p', { class: 'liens-sec' }, liens(d)) : null,
  );
}

/** Estimations de BPA : variation par rapport à il y a 90 jours, pour chaque période (petit graphique), puis tableau. */
function blocEstimations(b) {
  const est = b.estimations ?? {};
  const periodes = Object.keys(PERIODES).filter((p) => est[p]);
  if (!periodes.length) return null;
  const r = b.revisions ?? {};
  return el('div', {},
    el('h4', {}, 'Estimations de BPA des analystes'),
    graphiqueEstimations(est, periodes),
    el('div', { class: 'tableau-defilant' }, el('table', { class: 'tableau-fiabilite' },
      el('thead', {}, el('tr', {}, el('th', {}, 'Période'), el('th', {}, 'BPA estimé'), el('th', {}, '30 j'), el('th', {}, '90 j'), el('th', {}, '↑ / ↓', el('small', {}, '7 j (30 j)')))),
      el('tbody', {}, periodes.map((p) => {
        const x = est[p];
        const v = (a, c) => (a != null && c != null && Math.abs(c) >= 0.01 ? ((a - c) / Math.abs(c)) * 100 : null);
        const v30 = v(x.bpa.actuel, x.bpa['30j']);
        const v90 = v(x.bpa.actuel, x.bpa['90j']);
        const rv = x.revisions ?? {};
        return el('tr', {},
          el('td', {}, PERIODES_COURTES[p], x.fin ? el('small', {}, `fin ${dateFr(x.fin)}`) : null),
          el('td', { class: 'mono' }, x.bpa.actuel != null ? nombre(x.bpa.actuel, 2) : 'n. d.', x.analystes != null ? el('small', {}, `${x.analystes} analystes`) : null),
          el('td', { class: `mono ${v30 > 0 ? 'hausse' : v30 < 0 ? 'baisse' : ''}` }, v30 != null ? variation(v30, 1) : '—'),
          el('td', { class: `mono ${v90 > 0 ? 'hausse' : v90 < 0 ? 'baisse' : ''}` }, v90 != null ? variation(v90, 1) : '—'),
          el('td', { class: 'mono' }, `${rv.hausse_7j ?? '–'} / ${rv.baisse_7j ?? '–'}`, el('small', {}, `(${rv.hausse_30j ?? '–'} / ${rv.baisse_30j ?? '–'})`)),
        );
      })))),
    r['30j_pct'] != null || r['90j_pct'] != null ? el('p', { class: 'fiche-verdict' },
      `Exercices en cours et suivant : ${r['30j_pct'] != null ? variation(r['30j_pct'], 1) : 'n. d.'} sur 30 jours, ${r['90j_pct'] != null ? variation(r['90j_pct'], 1) : 'n. d.'} sur 90 jours.`) : null,
  );
}

function graphiqueEstimations(est, periodes) {
  const series = periodes.map((p) => {
    const base = est[p].bpa['90j'];
    const pts = POINTS.map(([cle, x]) => {
      const v = est[p].bpa[cle];
      return v != null && base != null && Math.abs(base) >= 0.01 ? [x, ((v - base) / Math.abs(base)) * 100] : null;
    }).filter(Boolean);
    return { p, pts };
  }).filter((s) => s.pts.length >= 2);
  if (!series.length) return null;
  const L = 320; const H = 140; const mg = { g: 40, d: 10, h: 10, b: 22 };
  const ys = series.flatMap((s) => s.pts.map(([, y]) => y));
  let ymin = Math.min(0, ...ys); let ymax = Math.max(0, ...ys);
  if (ymax - ymin < 2) { ymax += 1; ymin -= 1; }
  const x = (v) => mg.g + ((v + 90) / 90) * (L - mg.g - mg.d);
  const y = (v) => mg.h + (1 - (v - ymin) / (ymax - ymin)) * (H - mg.h - mg.b);
  const graduations = [ymin, 0, ymax].filter((v, i, t) => t.indexOf(v) === i);
  return el('figure', { class: 'dynamique-graphique' },
    svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img', 'aria-label': 'Évolution des estimations de BPA sur 90 jours, en % par rapport à il y a 90 jours' },
      graduations.map((v) => [
        svg('line', { class: v === 0 ? 'dyn-zero' : 'dyn-grille', x1: mg.g, x2: L - mg.d, y1: y(v), y2: y(v) }),
        svg('text', { class: 'dyn-axe', x: mg.g - 4, y: y(v) + 3, 'text-anchor': 'end' }, `${v > 0 ? '+' : ''}${nombre(v, 1)} %`),
      ]),
      POINTS.filter(([, v]) => v !== -7).map(([, v]) => svg('text', { class: 'dyn-axe', x: x(v), y: H - 6, 'text-anchor': 'middle' }, v === 0 ? 'auj.' : `${v} j`)),
      series.map((s) => [
        svg('path', { class: `dyn-ligne dyn-ligne--${s.p.replace('+', 'p')}`, d: s.pts.map(([a, b], i) => `${i ? 'L' : 'M'}${x(a).toFixed(1)},${y(b).toFixed(1)}`).join(' ') }),
        ...s.pts.map(([a, b]) => svg('circle', { class: `dyn-point dyn-ligne--${s.p.replace('+', 'p')}`, cx: x(a), cy: y(b), r: 2.5 })),
      ]),
    ),
    el('figcaption', { class: 'dyn-legende' }, series.map((s) => el('span', { class: `dyn-ligne--${s.p.replace('+', 'p')}` }, '● ', PERIODES[s.p]))),
  );
}

function blocSurprises(s) {
  if (!s?.length) return null;
  return el('div', {},
    el('h4', {}, 'Surprises de résultats', el('small', {}, ' · 4 derniers trimestres')),
    el('div', { class: 'tableau-defilant' }, el('table', { class: 'tableau-fiabilite' },
      el('thead', {}, el('tr', {}, el('th', {}, 'Trimestre clos'), el('th', {}, 'BPA publié'), el('th', {}, 'Estimé'), el('th', {}, 'Écart'))),
      el('tbody', {}, [...s].reverse().map((x) => el('tr', {},
        el('td', {}, dateFr(x.trimestre)),
        el('td', { class: 'mono' }, nombre(x.publie, 2)),
        el('td', { class: 'mono' }, nombre(x.estime, 2)),
        el('td', { class: `mono ${x.surprise_pct > 0 ? 'hausse' : x.surprise_pct < 0 ? 'baisse' : ''}` }, x.surprise_pct != null ? variation(x.surprise_pct, 1) : '—'),
      ))))),
  );
}

function blocObjectifs(o) {
  if (!o) return null;
  return el('div', {},
    el('h4', {}, 'Objectifs de cours des analystes', el('small', {}, ' · pour information')),
    el('dl', { class: 'reco-valeur' },
      el('dt', {}, 'Moyen'), el('dd', { class: 'mono' }, nombre(o.moyen, 2),
        o.ecart_pct != null ? el('small', { class: o.ecart_pct > 0 ? 'hausse' : 'baisse' }, ` ${variation(o.ecart_pct, 1)} par rapport au cours`) : null),
      el('dt', {}, 'Fourchette'), el('dd', { class: 'mono' }, `${o.bas != null ? nombre(o.bas, 2) : 'n. d.'} – ${o.haut != null ? nombre(o.haut, 2) : 'n. d.'}`),
      o.analystes != null ? [el('dt', {}, 'Analystes'), el('dd', { class: 'mono' }, String(o.analystes))] : null,
    ),
    el('p', { class: 'fiche-verdict' }, 'Objectifs publiés par les analystes (devise de cotation) : ils ne remplacent pas la fourchette de valeur calculée par l’agent (bloc Recommandation).'),
  );
}
