/* ==========================================================================
   Données alternatives (agent données alternatives, data/donnees_alternatives.json,
   chargé à la première ouverture de l'écran ou d'une fiche pays).
   - écran « Données alternatives » (ouvert depuis « Vue macro ») : tableau de bord des
     indicateurs mondiaux (camions allemands, exportations coréennes, ciment chinois, fret,
     TSA…), activité réelle par pays, attention du public pour les sociétés suivies ;
   - fiche pays : bloc « Activité réelle » (score, lecture, indicateurs avec mini-graphiques,
     divergence éventuelle avec les statistiques officielles) ;
   - filtre du globe « Activité réelle » : sous-note de l'agent pays (data/pays.json).
   ========================================================================== */

import { el, svg, nombre, variation } from './outils.js';

const FICHIER = 'data/donnees_alternatives.json';
let cache; // undefined : pas encore chargé ; null : indisponible

export async function chargerAlternatives(forcer = false) {
  if (cache !== undefined && !forcer) return cache;
  try {
    const r = await fetch(FICHIER, { cache: 'no-cache' });
    if (!r.ok) { cache = null; return cache; }
    const json = await r.json();
    cache = json?.donnees ? { meta: json.meta ?? {}, ...json.donnees } : null;
  } catch {
    cache = null;
  }
  return cache;
}
export const alternativesChargees = () => cache;

/** Filtre du globe : score d'activité réelle repris par l'agent pays (au moins 2 indicateurs). */
export const METRIQUE_ACTIVITE = { cle: 'activite_reelle', libelle: 'Activité réelle', court: 'Activité', source: 'indicateur' };
export function lireActivite(p) {
  const ind = p?.indicateurs?.activite_reelle;
  if (!ind || ind.valeur == null) return null;
  return { valeur: ind.valeur, note: ind.note, texte: nombre(ind.valeur, 0), unite: '/100' };
}

/* ------------------------------------------------------------------ outils */

const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
function dateFr(d, frequence) {
  if (!d) return 'date inconnue';
  const s = String(d);
  if (frequence === 'mensuelle') return `${MOIS[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)}`;
  return `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
}
const titre = (texte, complement) => el('h3', { class: 'section-titre' }, texte, complement ? el('small', {}, complement) : null);
const source = (texte) => el('p', { class: 'macro-source' }, texte);
const varTexte = (x) => (x == null ? el('span', { class: 'mono' }, 'n. d.') : el('span', { class: `mono ${x >= 0 ? 'hausse' : 'baisse'}` }, variation(x, 1)));
const CLASSE_LECTURE = { 'accélération': 'mp-verdict--sur', stable: 'mp-verdict--neutre', ralentissement: 'mp-verdict--sous' };
const badgeLecture = (l) => el('span', { class: `mp-verdict ${CLASSE_LECTURE[l] ?? ''}` }, l ?? 'pas de score');
const classeNote = (n) => (n == null ? '' : n >= 60 ? 'hausse' : n <= 40 ? 'baisse' : '');

function valeurTexte(i) {
  if (i.valeur == null) return 'n. d.';
  const v = Math.abs(i.valeur);
  if (v >= 1e9) return `${nombre(i.valeur / 1e9, 1)} Md`;
  if (v >= 1e6) return `${nombre(i.valeur / 1e6, 2)} M`;
  return nombre(i.valeur, v >= 1000 ? 0 : v >= 100 ? 1 : 2);
}

/** Mini-graphique (ligne) d'une série [[date, valeur]]. */
function sparkline(serie, { L = 96, H = 30 } = {}) {
  if (!serie || serie.length < 2) return el('span', { class: 'mp-spark' });
  const vals = serie.map((p) => p[1]);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const x = (i) => (i / (serie.length - 1)) * (L - 2) + 1;
  const y = (v) => H - 2 - ((v - mn) / (mx - mn || 1)) * (H - 4);
  const d = serie.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  return svg('svg', { class: 'mp-spark', viewBox: `0 0 ${L} ${H}`, width: L, height: H, 'aria-hidden': 'true' },
    svg('path', { d, class: `mp-spark-ligne ${vals.at(-1) >= vals[0] ? 'mp-spark--hausse' : 'mp-spark--baisse'}` }));
}

function ligneIndicateur(i, { avecPays = false, nomsPays = {} } = {}) {
  const nomPays = i.pays === 'monde' ? 'Monde' : (nomsPays[i.pays] ?? i.pays);
  return el('div', { class: `alt-ligne${i.perimee ? ' alt-ligne--perimee' : ''}`, title: i.lecture ?? '' },
    el('span', { class: 'alt-ligne-nom' },
      avecPays ? `${nomPays} · ${i.nom}` : i.nom,
      el('small', {}, i.perimee
        ? `dernière donnée : ${dateFr(i.date, i.frequence)} (${i.age_jours} j) · trop ancienne, hors score`
        : `${valeurTexte(i)} ${i.unite ?? ''} · ${dateFr(i.date, i.frequence)}${i.etat_source === 'secours' ? ' · source de secours' : ''}`)),
    el('span', { class: 'mp-ligne-var' }, el('small', {}, '1 mois'), varTexte(i.variation_1m), el('small', {}, '12 mois'), varTexte(i.variation_12m)),
    sparkline(i.serie),
    el('span', { class: `alt-ligne-note mono ${classeNote(i.note)}`, title: i.percentile_12m != null ? `percentile ${nombre(i.percentile_12m, 0)} de l'historique` : (i.methode_note ?? '') },
      i.note == null ? 'n. d.' : `${nombre(i.note, 0)}`),
  );
}

function detailIndicateur(i) {
  const morceaux = [];
  if (i.ecart_tendance != null) morceaux.push(`écart à la tendance ${variation(i.ecart_tendance, 1)}`);
  if (i.ecart_saisonnier != null) morceaux.push(`écart à la normale saisonnière ${variation(i.ecart_saisonnier, 1)}`);
  if (i.percentile_12m != null) morceaux.push(`percentile ${nombre(i.percentile_12m, 0)} de l'historique`);
  const secours = i.etat_source === 'secours' && i.detail_source ? ` ${i.detail_source[0].toUpperCase()}${i.detail_source.slice(1)}.` : '';
  return el('p', { class: 'alt-detail' }, `${morceaux.join(' · ')}${morceaux.length ? ' — ' : ''}${i.source_nom}${i.mention ? ` (${i.mention})` : ''}.${secours}`);
}

function blocPays(p, index, { complet = true } = {}) {
  const inds = (p.indicateurs ?? []).map((k) => index[k]).filter(Boolean);
  return el('div', { class: 'alt-pays' },
    el('div', { class: 'alt-pays-tete' },
      el('strong', {}, p.nom),
      p.score != null ? el('span', { class: `mono ${classeNote(p.score)}` }, `${nombre(p.score, 0)}/100`) : null,
      badgeLecture(p.lecture),
      p.confiance ? el('small', {}, `confiance ${p.confiance.niveau}`) : null),
    el('p', { class: 'alt-texte' }, p.texte),
    p.lecture_non_retenue ? el('p', { class: 'alt-detail' }, `Note : ${p.lecture_non_retenue}.`) : null,
    p.divergence ? el('p', { class: 'alt-divergence' }, el('strong', {}, 'Divergence avec l’officiel. '), p.divergence.texte) : null,
    complet ? el('div', { class: 'alt-liste' }, inds.map((i) => [ligneIndicateur(i), detailIndicateur(i)])) : null,
    complet && p.ce_qui_pourrait_me_donner_tort?.length ? el('div', {},
      el('h4', { class: 'alt-sous-titre' }, 'Ce qui pourrait me donner tort'),
      el('ul', { class: 'contre-scenario' }, p.ce_qui_pourrait_me_donner_tort.map((t) => el('li', {}, t)))) : null,
  );
}

/* ------------------------------------------------------------------ fiche pays */

/** Bloc « Activité réelle » de la fiche pays ; null si l'agent ne suit pas ce pays. */
export function sectionActivitePays(alt, code) {
  if (alt === undefined) return el('section', {}, titre('Activité réelle'), el('p', { class: 'alt-detail' }, 'Chargement des données alternatives…'));
  const p = alt?.pays?.find((x) => x.code === code);
  if (!p) return null;
  const index = Object.fromEntries((alt.indicateurs ?? []).map((i) => [i.cle, i]));
  return el('section', {},
    titre('Activité réelle', 'données alternatives · au moins 2 indicateurs pour conclure'),
    blocPays(p, index),
    source(`Agent données alternatives, données du ${dateFr(alt.date)}. ${alt.avertissement ?? ''}`),
  );
}

/* ------------------------------------------------------------------ écran */

export function ecranAlternatives(alt, nav, nomsPays = {}) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Agent données alternatives · l’activité réelle avant les statistiques officielles'),
    el('h2', { class: 'fiche-titre' }, 'Données alternatives'),
  );
  if (alt === undefined) return [entete, el('p', { class: 'sante-ligne' }, 'Chargement…')];
  if (!alt) return [entete, el('p', { class: 'sante-ligne' }, 'Données de l’agent indisponibles (data/donnees_alternatives.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  const index = Object.fromEntries((alt.indicateurs ?? []).map((i) => [i.cle, i]));
  const mondiaux = (alt.tableau_mondial ?? []).map((k) => index[k]).filter(Boolean);
  const avecScore = (alt.pays ?? []).filter((p) => p.score != null);
  const sansScore = (alt.pays ?? []).filter((p) => p.score == null);
  const parCategorie = {};
  for (const i of alt.indicateurs ?? []) if (i.valeur != null && !mondiaux.includes(i)) (parCategorie[i.categorie_nom] ??= []).push(i);
  return [
    entete,
    el('p', { class: 'macro-resume' }, alt.avertissement),

    el('section', {},
      titre('Tableau de bord mondial', 'note /100 : rang de la variation dans l’historique de l’indicateur'),
      el('div', { class: 'alt-liste' }, mondiaux.map((i) => ligneIndicateur(i, { avecPays: true, nomsPays }))),
      source('Survoler une ligne pour le détail. Les données mensuelles sont publiées avec retard ; une donnée ancienne est affichée mais exclue des scores.'),
    ),

    el('section', {},
      titre('Activité réelle par pays', `${avecScore.length} pays avec un score`),
      avecScore.length ? el('div', { class: 'alt-pays-liste' }, avecScore.map((p) => el('div', {},
        blocPays(p, index, { complet: false }),
        el('button', { class: 'bouton bouton--accent alt-bouton', type: 'button', onclick: () => nav.ouvrirPays?.(p.code) }, `Fiche ${p.nom} ›`)))) : el('p', { class: 'alt-detail' }, 'Aucun pays n’a encore deux indicateurs à jour.'),
      sansScore.length ? source(`Sans score (moins de 2 indicateurs à jour) : ${sansScore.map((p) => p.nom).join(', ')}.`) : null,
    ),

    Object.keys(parCategorie).length ? el('section', {},
      titre('Autres indicateurs'),
      ...Object.entries(parCategorie).map(([cat, liste]) => el('div', {},
        el('h4', { class: 'alt-sous-titre' }, cat),
        el('div', { class: 'alt-liste' }, liste.map((i) => ligneIndicateur(i, { avecPays: true, nomsPays }))))),
    ) : null,

    alt.attention?.length ? el('section', {},
      titre('Attention du public', 'information seulement, hors score'),
      el('ul', { class: 'alt-attention' }, alt.attention.slice(0, 15).map((a) => el('li', {},
        el('span', {}, a.nom, el('small', {}, ` · ${a.liste === 'pepites' ? 'pépite' : 'surveillance'}${a.ancienne ? ' · relevé précédent' : ''}`)),
        el('span', { class: `mono ${a.variation_moyenne_pct >= 0 ? 'hausse' : 'baisse'}` }, variation(a.variation_moyenne_pct, 0)),
        el('small', {}, [a.wikipedia ? `Wikipédia ${nombre(a.wikipedia.vues_30j, 0)} vues en 30 j` : null, a.trends ? `Google Trends ${variation(a.trends.variation_pct, 0)}` : null].filter(Boolean).join(' · '))))),
      source('Consultations Wikipédia (30 derniers jours contre les 60 précédents) et Google Trends (4 dernières semaines contre les 8 précédentes). Une attention accrue ne dit rien du sens de l’évolution.'),
    ) : null,

    el('section', {},
      titre('Méthode'),
      el('p', { class: 'alt-detail' }, alt.methode),
      alt.sources_ignorees?.length ? source(`Sources ignorées faute de clé ou d’adresse : ${alt.sources_ignorees.join(' ; ')}.`) : null,
      source(`Mis à jour le ${dateFr(alt.date)}.`),
    ),
  ];
}
