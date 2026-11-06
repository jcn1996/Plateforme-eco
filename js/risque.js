/* ==========================================================================
   Agent risque (data/risque.json)
   - pastille permanente du palier de risque dans l'en-tête ;
   - écran « Risque » : jauge du score mondial, palier et explication, faits et
     interprétations, indicateurs (valeur, percentile, tendance), graphique sur
     12 mois, pays les plus à risque, dernières objections du contradicteur ;
   - rubrique « Agent risque » de la fiche pays (décomposition du score) ;
   - filtre du globe « Risque » (score /100 : plus il est haut, plus le risque est élevé).
   ========================================================================== */

import { el, svg, nombre } from './outils.js';

const FICHIER = 'data/risque.json';
const SEUIL_ELEVE = 60;
const SEUIL_MODERE = 35;
const COMPOSANTES = { marche: 'Marché', devise: 'Devise', souverain: 'Souverain', macro: 'Vulnérabilité macro', geopolitique: 'Géopolitique' };
const AGENTS = { pays: 'Agent pays', macro: 'Agent macro', entreprises: 'Agent entreprises', geopolitique: 'Agent géopolitique' };

/** Charge data/risque.json ; null si absent (l'appli continue). */
export async function chargerRisque() {
  try {
    const r = await fetch(FICHIER, { cache: 'no-cache' });
    if (!r.ok) return null;
    const json = await r.json();
    return json?.donnees ? { meta: json.meta ?? {}, ...json.donnees } : null;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ outils */

const classePalier = (p) => `risque-palier--${(p ?? 'inconnu').toLowerCase()}`;

function dateHeure(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const dateCourte = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '');

function variationTexte(v) {
  if (v == null) return 'variation sur 7 j : n. d.';
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${nombre(Math.abs(v), 1)} pt sur 7 j`;
}

/** Niveau de couleur d'un score de risque : rouge si élevé, vert si faible. */
export function niveauRisquePays(score) {
  if (score >= SEUIL_ELEVE) return 'defavorable';
  if (score >= SEUIL_MODERE) return 'neutre';
  return 'attractif';
}

function badgeScore(score) {
  return el('span', { class: `geo-score note--${niveauRisquePays(score)}` }, el('strong', { class: 'mono' }, nombre(score)), '/100');
}

/* ------------------------------------------------------------------ globe */

export const METRIQUE_RISQUE_PAYS = { cle: 'risque_pays', libelle: 'Risque', court: 'Risque', source: 'risque' };

/** Lecture de la métrique « Risque » pour un pays (format du globe). */
export function lireRisquePays(risque, code) {
  const s = risque?.pays?.[code];
  if (!s || s.score == null) return null;
  return { valeur: s.score, note: s.score, niveau: niveauRisquePays(s.score), texte: nombre(s.score), unite: '/100' };
}

/* ------------------------------------------------------------------ en-tête */

/** Met à jour la pastille permanente du palier de risque (bouton de l'en-tête). */
export function majPastilleRisque(bouton, risque) {
  if (!bouton) return;
  const m = risque?.mondial;
  bouton.hidden = !m;
  if (!m) return;
  bouton.className = `bouton pastille-risque ${classePalier(m.palier)}`;
  bouton.title = `Risque mondial : ${m.palier} (score ${nombre(m.score)}/100). Ouvrir l’écran « Risque »`;
  bouton.replaceChildren(
    el('span', { class: 'pastille-risque-point', 'aria-hidden': 'true' }),
    el('span', { class: 'pastille-risque-texte' }, m.palier),
    el('span', { class: 'visuellement-cache' }, ` : risque mondial, score ${nombre(m.score)} sur 100`),
  );
}

/* ------------------------------------------------------------------ composants de l'écran */

function jaugeRisque(m) {
  const r = 32, circonference = 2 * Math.PI * r;
  const cercle = svg('circle', {
    class: 'jauge-valeur', cx: 37, cy: 37, r, fill: 'none', 'stroke-width': 6, 'stroke-linecap': 'round',
    'stroke-dasharray': circonference, 'stroke-dashoffset': circonference,
  });
  requestAnimationFrame(() => requestAnimationFrame(() => cercle.setAttribute('stroke-dashoffset', circonference * (1 - m.score / 100))));
  return el('div', { class: `jauge risque-jauge ${classePalier(m.palier)}`, role: 'img', 'aria-label': `Score de stress mondial ${m.score} sur 100, palier ${m.palier}` },
    svg('svg', { viewBox: '0 0 74 74' }, svg('circle', { class: 'jauge-fond', cx: 37, cy: 37, r, fill: 'none', 'stroke-width': 6 }), cercle),
    el('div', { class: 'jauge-texte', 'aria-hidden': 'true' }, el('strong', {}, nombre(m.score)), el('small', {}, '/100')));
}

function echelle(r) {
  const s = r.seuils ?? {};
  const paliers = r.paliers ?? [];
  return el('ol', { class: 'risque-echelle', 'aria-label': 'Paliers de risque' }, paliers.map((p, i) => {
    const bas = i === 0 ? 0 : s[p];
    const haut = i < paliers.length - 1 ? s[paliers[i + 1]] : 100;
    return el('li', { class: `${classePalier(p)}${p === r.mondial.palier ? ' est-actif' : ''}` },
      el('span', {}, p), el('small', { class: 'mono' }, `${nombre(bas)}–${nombre(haut)}`));
  }));
}

const FLECHES = { hausse: ['↑', 'tendance--hausse-risque'], baisse: ['↓', 'tendance--baisse-risque'], stable: ['→', 'tendance--stable'] };

function tableauIndicateurs(indicateurs) {
  return el('table', { class: 'tableau risque-tableau' },
    el('thead', {}, el('tr', {}, el('th', {}, 'Indicateur'), el('th', { class: 'nombre' }, 'Valeur'), el('th', { class: 'nombre' }, 'Percentile'), el('th', { class: 'nombre' }, '1 mois'))),
    el('tbody', {}, indicateurs.map((i) => {
      if (!i.disponible) {
        return el('tr', { class: 'risque-ligne--absente' }, el('td', {}, i.nom, el('small', {}, i.facultatif ? 'facultatif, non disponible' : 'non disponible')), el('td', { class: 'nombre' }, '—'), el('td', { class: 'nombre' }, '—'), el('td', { class: 'nombre' }, '—'));
      }
      const [fleche, classe] = FLECHES[i.tendance] ?? ['', ''];
      return el('tr', { title: `${i.source} · au ${dateCourte(i.date)}${i.verification === 'divergent' ? ' · sources divergentes' : ''}` },
        el('td', {}, i.nom,
          el('small', {}, `${dateCourte(i.date)} · ${nombre(i.historique_annees)} an${i.historique_annees >= 2 ? 's' : ''} d’historique`,
            i.verification === 'concordant' ? ' · vérifié' : '', i.secours ? ' · source de secours' : ''),
          i.verification === 'divergent' ? el('span', { class: 'drapeau drapeau--divergent' }, 'sources divergentes') : null),
        el('td', { class: 'nombre' }, i.texte),
        el('td', { class: 'nombre' }, el('span', { class: `risque-percentile ${classePalier(i.palier)}` }, nombre(i.percentile))),
        el('td', { class: `nombre ${classe}` }, fleche));
    })));
}

function graphique12Mois(r) {
  const serie = r.historique ?? [];
  if (serie.length < 2) return el('p', { class: 'macro-source' }, 'Historique indisponible.');
  const L = Math.round(Math.min(560, Math.max(280, innerWidth - 58))), H = 120;
  const m = { haut: 8, droite: 66, bas: 18, gauche: 8 };
  const t0 = Date.parse(serie[0][0]), t1 = Date.parse(serie.at(-1)[0]);
  const x = (d) => m.gauche + ((Date.parse(d) - t0) / Math.max(1, t1 - t0)) * (L - m.gauche - m.droite);
  const y = (v) => H - m.bas - (v / 100) * (H - m.haut - m.bas);
  const chemin = serie.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  const dernier = serie.at(-1);
  const seuils = (r.paliers ?? []).slice(1).map((p) => svg('g', { class: classePalier(p) },
    svg('line', { class: 'risque-seuil', x1: m.gauche, x2: L - m.droite, y1: y(r.seuils[p]), y2: y(r.seuils[p]) }),
    svg('text', { class: 'risque-seuil-texte', x: L - m.droite + 4, y: y(r.seuils[p]) + 3 }, p)));
  return el('div', { class: 'graphique geo-graphique' },
    svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img', 'aria-label': `Score de stress mondial sur 12 mois : ${nombre(dernier[1])} au ${dateCourte(dernier[0])}` },
      svg('g', {}, ...seuils),
      svg('g', { class: 'axe' },
        svg('text', { x: m.gauche, y: H - 4 }, dateCourte(serie[0][0]).slice(3)),
        svg('text', { x: L - m.droite, y: H - 4, 'text-anchor': 'end' }, dateCourte(dernier[0]).slice(3))),
      svg('path', { class: 'serie', d: chemin, stroke: 'var(--cyan)' }),
      svg('circle', { cx: x(dernier[0]), cy: y(dernier[1]), r: 3.5, fill: 'var(--cyan)' })));
}

const AJUSTEMENTS = { maintenir: 'maintenir', abaisser: 'abaisser', 'signal fragile': 'signal fragile' };

function carteObjection(o) {
  const cles = { maintenir: 'maintenir', abaisser: 'abaisser', 'signal fragile': 'fragile' };
  return el('article', { class: `carte risque-objection risque-objection--${cles[o.ajustement] ?? 'maintenir'}` },
    el('div', { class: 'geo-meta' },
      `${AGENTS[o.signal.agent] ?? o.signal.agent} · signal du ${dateCourte(o.signal.date)} · importance ${o.signal.importance}`,
      o.methode === 'gemini' ? el('small', {}, ` · rédigée par Gemini${o.modele ? ` (${o.modele})` : ''}`) : el('small', {}, ' · règles')),
    el('h4', { class: 'geo-titre' }, o.signal.titre),
    el('div', { class: 'geo-bloc' },
      el('div', { class: 'geo-etiquette' }, 'Objection'),
      el('p', { class: 'geo-texte' }, o.objection)),
    el('p', { class: 'risque-ajustement' }, 'Ajustement de confiance proposé : ', el('strong', {}, AJUSTEMENTS[o.ajustement] ?? o.ajustement)),
    o.faits?.length ? el('details', { class: 'geo-sources' },
      el('summary', {}, `Faits utilisés (${o.faits.length})`),
      el('ol', {}, o.faits.map((f) => el('li', {}, el('span', { class: 'mono' }, `${f.id} `), f.texte, el('small', {}, ` — ${f.source}`))))) : null);
}

/* ------------------------------------------------------------------ écran */

export function ecranRisque(r, { ouvrirPays } = {}) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Agent risque · stress financier mondial et par pays, contradicteur des signaux'),
    el('h2', { class: 'fiche-titre' }, 'Risque'),
  );
  if (!r?.mondial) {
    return [entete, el('p', { class: 'sante-ligne' }, 'Données de l’agent risque indisponibles (data/risque.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  }
  const m = r.mondial;
  const eleves = Object.entries(r.pays ?? {}).filter(([, p]) => p.score != null).sort((a, b) => b[1].score - a[1].score).slice(0, 8);
  const ordre = [...(r.indicateurs ?? [])].sort((a, b) => (b.disponible - a.disponible) || (b.poids - a.poids));
  return [
    entete,
    el('section', { class: 'risque-synthese' },
      el('div', { class: 'risque-tete' },
        jaugeRisque(m),
        el('div', {},
          el('div', { class: `risque-palier ${classePalier(m.palier)}` }, m.palier),
          el('p', { class: 'macro-texte' },
            m.palier_precedent ? `Depuis le ${dateCourte(m.depuis)} (palier précédent : « ${m.palier_precedent} »).` : `Depuis le ${dateCourte(m.depuis)}.`,
            ` Confiance : ${m.confiance?.niveau ?? 'n. d.'}.`),
          m.changement_en_attente ? el('p', { class: 'risque-attente' },
            `Changement vers « ${m.changement_en_attente.vers} » en attente : deux familles d’indicateurs concordantes sont nécessaires (${m.changement_en_attente.familles_concordantes.length} aujourd’hui).`) : null)),
      echelle(r),
    ),
    el('section', {},
      el('h3', { class: 'section-titre' }, 'Explication', el('small', {}, `données au ${dateCourte(m.date_donnees)}`)),
      el('div', { class: 'geo-bloc' }, el('div', { class: 'geo-etiquette' }, 'Faits'), ...m.faits.map((t) => el('p', { class: 'geo-texte' }, t))),
      m.interpretations?.length ? el('div', { class: 'geo-bloc' }, el('div', { class: 'geo-etiquette' }, 'Interprétation'), ...m.interpretations.map((t) => el('p', { class: 'geo-texte' }, t))) : null,
      el('div', { class: 'geo-bloc' }, el('div', { class: 'geo-etiquette' }, 'Indicateurs qui pèsent le plus'),
        el('ul', { class: 'geo-scores' }, m.principaux.map((p) => el('li', {},
          el('span', {}, p.nom), el('span', { class: 'mono' }, `percentile ${nombre(p.percentile)}`),
          el('small', {}, `${p.contribution > 0 ? '+' : p.contribution < 0 ? '−' : ''}${nombre(Math.abs(p.contribution), 1)} pt`))))),
      m.confiance?.raisons?.length ? el('p', { class: 'macro-source' }, `Confiance ${m.confiance.niveau} : ${m.confiance.raisons.join(' ; ')}.`) : null,
    ),
    m.contre?.length ? el('section', {},
      el('h3', { class: 'section-titre' }, 'Ce qui pourrait me donner tort'),
      el('ul', { class: 'contre-scenario' }, m.contre.map((t) => el('li', {}, t)))) : null,
    el('section', {},
      el('h3', { class: 'section-titre' }, 'Indicateurs', el('small', {}, 'percentile sur l’historique disponible (jusqu’à 10 ans)')),
      tableauIndicateurs(ordre),
    ),
    el('section', {},
      el('h3', { class: 'section-titre' }, 'Score mondial sur 12 mois', el('small', {}, 'hebdomadaire · seuils des paliers')),
      graphique12Mois(r),
      el('p', { class: 'macro-source' }, `Seuils : ${(r.paliers ?? []).slice(1).map((p) => `${p} ≥ ${nombre(r.seuils[p], 1)}`).join(' · ')} (${r.seuils.methode}).`),
    ),
    eleves.length ? el('section', {},
      el('h3', { class: 'section-titre' }, 'Pays les plus à risque', el('small', {}, '/100 · couleur du globe « Risque »')),
      el('ul', { class: 'geo-scores risque-pays' }, eleves.map(([code, p]) => el('li', {},
        ouvrirPays ? el('button', { type: 'button', class: 'lien', onclick: () => ouvrirPays(code) }, p.nom) : el('span', {}, p.nom),
        badgeScore(p.score), el('small', {}, variationTexte(p.variation_7j)))))) : null,
    el('section', {},
      el('h3', { class: 'section-titre' }, 'Dernières objections du contradicteur',
        el('small', {}, `${r.contradicteur?.revues_7j ?? 0} signal(aux) revu(s) sur 7 jours`)),
      r.objections?.length
        ? el('div', { class: 'geo-liste' }, r.objections.slice(0, 8).map(carteObjection))
        : el('p', { class: 'sante-ligne' }, 'Aucun signal récent d’importance moyenne ou forte à revoir.'),
    ),
    el('p', { class: 'macro-source' }, r.methode ?? ''),
    el('p', { class: 'fraicheur' }, `Mis à jour le ${dateHeure(r.meta?.genere_le)} · objections : ${r.contradicteur?.mode === 'gemini' ? 'Gemini (budget propre à l’agent risque)' : 'règles'}`),
    el('p', { class: 'mention-legale' }, 'Faits chiffrés tirés des sources citées ; les interprétations et les objections sont des lectures de l’agent. Ne constitue pas un conseil en investissement.'),
  ];
}

/* ------------------------------------------------------------------ fiche pays */

/** Rubrique « Agent risque » de la fiche pays : score, variation, texte, décomposition. */
export function sectionRisquePays(r, code) {
  const s = r?.pays?.[code];
  if (!s) return null;
  const poids = s.ponderations ?? {};
  return el('section', {},
    el('h3', { class: 'section-titre' }, 'Agent risque', el('small', {}, `mis à jour le ${dateHeure(r.meta?.genere_le)}`)),
    s.score != null
      ? el('p', { class: 'geo-score-pays' }, 'Score de risque : ', badgeScore(s.score), ` · risque ${s.niveau} · ${variationTexte(s.variation_7j)}`)
      : el('p', { class: 'macro-texte' }, 'Score indisponible (données insuffisantes).'),
    el('p', { class: 'macro-texte' }, s.texte),
    el('ul', { class: 'risque-decomposition' }, Object.keys(COMPOSANTES).map((cle) => {
      const c = s.composantes?.[cle];
      if (!c) {
        return el('li', { class: 'risque-composante--absente' },
          el('div', { class: 'risque-composante-tete' }, el('span', {}, COMPOSANTES[cle]), el('small', {}, `poids ${poids[cle] ?? '?'} % · non disponible`)));
      }
      return el('li', { class: `note--${niveauRisquePays(c.score)}` },
        el('div', { class: 'risque-composante-tete' },
          el('span', {}, COMPOSANTES[cle]),
          el('span', { class: 'mono risque-composante-note' }, `${nombre(c.score)}/100`),
          el('small', {}, `poids ${poids[cle] ?? '?'} %`)),
        el('div', { class: 'barre', role: 'img', 'aria-label': `${COMPOSANTES[cle]} : ${nombre(c.score)} sur 100` }, el('span', { style: { width: `${c.score}%` } })),
        el('small', { class: 'risque-composante-texte' }, `${c.texte} · ${c.source}${c.verification === 'divergent' ? ' · sources divergentes' : c.verification === 'concordant' ? ' · vérifié' : ''}`));
    })),
    el('p', { class: 'macro-source' }, 'Score /100 (plus il est haut, plus le risque est élevé) : moyenne pondérée des composantes disponibles. Agent risque : stress financier, devises, écarts souverains, vulnérabilité macro, géopolitique.'),
  );
}
