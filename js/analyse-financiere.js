/* ==========================================================================
   Bloc « Analyse financière approfondie » de la fiche entreprise (agent entreprises) :
   sous-notes par famille (valeur et cycle, solidité et fiabilité, qualité,
   alignement), indicateurs de chaque famille, hypothèses du coût du capital,
   composantes du Z-score d'Altman et variables du M-score de Beneish.
   Données : e.analyse_financiere (fiche data/entreprises/fiches/<ticker>.json).
   ========================================================================== */

import { el, nombre, classeNote } from './outils.js';
import { listeIndicateurs, titreSection } from './panneau-pays.js';

const AIDES = {
  valeur_cycle: 'rendement du flux de trésorerie disponible, bénéfices normalisés, ROIC − coût du capital, régularité, rendement pour l’actionnaire',
  solidite: 'Z-score d’Altman, M-score de Beneish, goodwill, current ratio, dette nette / EBITDA, couverture des intérêts',
  qualite: 'marge brute, cycle de conversion du cash, capex / amortissements, R&D, F-score, conversion en cash',
  alignement: 'capital détenu par les dirigeants, évolution du nombre d’actions sur 3 ans',
};

function pct(v, d = 1) {
  return v == null ? 'n. d.' : `${nombre(v, d)} %`;
}

export function blocAnalyseFinanciere(af) {
  if (!af?.sous_notes) return null;
  const ind = af.indicateurs ?? {};
  const d = af.details ?? {};
  return el('section', { class: 'analyse-financiere' },
    titreSection('Analyse financière approfondie', 'sous-notes par famille · note sur 100'),
    af.sommet_cycle ? el('p', { class: 'reco-reserve' },
      `Sommet de cycle possible : bénéfice actuel égal à ${nombre(d.normalisation?.ratio, 2)} fois sa moyenne sur ${d.normalisation?.annees ?? '?'} ans ; la valorisation retient le bénéfice moyen.`) : null,
    // Familles sans indicateur (banques et assurances : solidité et qualité non pertinentes) masquées
    el('div', { class: 'sous-notes' }, Object.entries(af.sous_notes).filter(([, f]) => f.indicateurs > 0).map(([cle, f]) => el('div', {
      class: `sous-note ${f.note != null ? classeNote(f.note) : 'sous-note--absente'}`, title: AIDES[cle] ?? '',
    },
    el('small', {}, f.nom),
    el('strong', { class: 'mono' }, f.note != null ? String(f.note) : '—', f.note != null ? el('small', {}, '/100') : null),
    el('small', {}, `${f.indicateurs} indicateur${f.indicateurs > 1 ? 's' : ''}`)))),
    Object.entries(af.sous_notes).map(([cle, f]) => {
      const propres = Object.fromEntries((f.cles ?? []).filter((k) => ind[k]).map((k) => [k, ind[k]]));
      if (!Object.keys(propres).length) return null;
      return el('div', { class: 'analyse-famille' }, el('h4', {}, f.nom, f.note != null ? el('small', {}, ` · ${f.note}/100`) : null), listeIndicateurs(propres));
    }),
    af.sous_notes.solidite?.indicateurs === 0 && af.sous_notes.qualite?.indicateurs === 0
      ? el('p', { class: 'fiche-verdict' }, 'Banque ou assurance : Z-score, M-score et ratios d’exploitation non pertinents, non calculés.') : null,
    blocHypotheses(d),
    el('p', { class: 'fraicheur' }, 'Sources : SEC (XBRL, jusqu’à 6 exercices) pour les sociétés américaines, ESEF et Yahoo Finance (5 exercices, détention des dirigeants, bêta). Un indicateur dont une donnée manque n’est pas calculé. Les sous-notes reprennent aussi les indicateurs clés de leur famille.'),
  );
}

function blocHypotheses(d) {
  const lignes = [];
  if (d.wacc) {
    const w = d.wacc;
    lignes.push(el('li', {}, el('strong', {}, 'Coût du capital estimé : '),
      `${pct(w.wacc)} = fonds propres ${pct(w.cout_fonds_propres)} (taux sans risque et prime du pays ${pct(w.taux_sans_risque)} + bêta ${nombre(w.beta, 2)} [${w.beta_source}] × prime de marché ${pct(w.prime_marche)}) et dette ${pct(w.cout_dette)} avant impôt (impôt ${pct(w.impot)}), dette = ${pct(w.part_dette)} du financement.`));
  }
  if (d.altman) {
    const c = d.altman.composantes;
    lignes.push(el('li', {}, el('strong', {}, 'Z-score d’Altman : '),
      `${nombre(d.altman.z, 2)} (zone ${d.altman.zone} ; sûre au-dessus de 2,99, détresse sous 1,81) = 1,2 × fonds de roulement ${nombre(c.fonds_roulement, 2)} + 1,4 × bénéfices non distribués ${nombre(c.benefices_non_distribues, 2)} + 3,3 × EBIT ${nombre(c.ebit, 2)} + 0,6 × capitalisation / passifs ${nombre(c.capitalisation_passifs, 2)} + 1,0 × rotation des actifs ${nombre(c.rotation_actifs, 2)} (chaque terme rapporté à l’actif total).`));
  }
  if (d.beneish) {
    const v = d.beneish.variables;
    lignes.push(el('li', {}, el('strong', {}, 'M-score de Beneish : '),
      `${nombre(d.beneish.m, 2)} (${d.beneish.suspect ? 'au-dessus' : 'en dessous'} du seuil de −1,78) ; ${Object.entries(v).map(([k, x]) => `${k} ${nombre(x, 2)}`).join(', ')}`,
      d.beneish.neutres?.length ? ` ; ${d.beneish.neutres.join(', ')} fixés à 1 (données manquantes)` : ''));
  }
  if (d.normalisation) {
    const n = d.normalisation;
    lignes.push(el('li', {}, el('strong', {}, 'Bénéfices normalisés : '),
      `moyenne sur ${n.annees} ans, rapport ${n.ratio != null ? `${nombre(n.ratio, 2)}×` : 'non significatif (bénéfice négatif)'}${n.exces_marge != null ? `, ${nombre(n.exces_marge, 2)}× une fois corrigé de la croissance du CA` : ''} ; sommet de cycle possible au-delà de 1,5× si l’écart ne vient pas de la croissance du CA (plus de 1,25× une fois corrigé) et si la marge nette est au plus haut des exercices étudiés (4 au moins).${n.sommet_cycle ? ' Ici : sommet de cycle possible, valorisation sur le bénéfice moyen.' : ''}`));
  }
  if (!lignes.length) return null;
  return el('details', { class: 'detail-repliable' }, el('summary', {}, 'Hypothèses et calculs'), el('ul', { class: 'liste-sources' }, lignes));
}
