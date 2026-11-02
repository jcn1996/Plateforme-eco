/* ==========================================================================
   Fiche pays et fiche secteur (contenu du panneau montant)
   + composants réutilisés par la fiche entreprise (jauge, indicateurs, agents).
   ========================================================================== */

import {
  el, svg, nombre, variation, classeNote, niveauNote, libelleNiveau, valeurIndicateur, AGENTS,
  complementIndicateur, badgeTendance, tendanceIndicateur, tendanceNote, texteFraicheur,
} from './outils.js';

/* ------------------------------ Composants ------------------------------ */

/** Jauge circulaire affichant une note sur 100. */
export function jauge(note) {
  const r = 32, circonference = 2 * Math.PI * r;
  const cercle = svg('circle', {
    class: 'jauge-valeur', cx: 37, cy: 37, r, fill: 'none', 'stroke-width': 6, 'stroke-linecap': 'round',
    'stroke-dasharray': circonference, 'stroke-dashoffset': circonference,
  });
  // Animation de remplissage juste après l'affichage
  requestAnimationFrame(() => requestAnimationFrame(() => {
    cercle.setAttribute('stroke-dashoffset', circonference * (1 - note / 100));
  }));
  return el('div', { class: `jauge ${classeNote(note)}`, role: 'img', 'aria-label': `Note ${note} sur 100, ${libelleNiveau(niveauNote(note))}` },
    svg('svg', { viewBox: '0 0 74 74' },
      svg('circle', { class: 'jauge-fond', cx: 37, cy: 37, r, fill: 'none', 'stroke-width': 6 }),
      cercle,
    ),
    el('div', { class: 'jauge-texte', 'aria-hidden': 'true' }, el('strong', {}, nombre(note)), el('small', {}, '/100')),
  );
}

/** En-tête de fiche : jauge + surtitre + titre + verdict. */
export function enteteFiche({ note, surtitre, titre, verdict, action, tendance }) {
  return el('header', { class: 'fiche-entete' },
    el('div', { class: 'fiche-note' },
      jauge(note),
      // Évolution de la note depuis la mise à jour précédente
      badgeTendance(tendance, 'depuis la mise à jour précédente'),
    ),
    el('div', { class: 'fiche-titres' },
      el('div', { class: 'fiche-surtitre' }, surtitre),
      el('h2', { class: 'fiche-titre' }, titre),
      verdict ? el('p', { class: 'fiche-verdict' }, verdict) : null,
      action ? el('div', { class: 'fiche-actions' }, action) : null,
    ),
  );
}

/** Titre de section (avec un petit complément facultatif à droite). */
export function titreSection(texte, complement) {
  return el('h3', { class: 'section-titre' }, texte, complement ? el('small', {}, complement) : null);
}

/**
 * Liste compacte d'indicateurs : une ligne par indicateur
 * (pastille de couleur, libellé, valeur, note). Les 5 tiennent sur un écran.
 */
export function listeIndicateurs(indicateurs) {
  return el('ul', { class: 'liste-indicateurs' },
    Object.entries(indicateurs).map(([cle, ind]) => {
      const disponible = ind.valeur !== null && ind.valeur !== undefined && ind.note !== null && ind.note !== undefined;
      return el('li', {
        class: `ligne-indicateur ${disponible ? classeNote(ind.note) : 'ligne-indicateur--absente'}`,
        title: disponible ? libelleNiveau(niveauNote(ind.note)) : (ind.raison ?? 'non disponible'),
      },
        el('span', { class: 'pastille', 'aria-hidden': 'true' }),
        el('span', { class: 'ligne-indicateur-libelle' },
          ind.libelle,
          // Signalements de l'agent : valeur ancienne (source en panne) ou inhabituelle
          ind.ancienne ? el('span', { class: 'drapeau drapeau--ancienne', title: ind.raison_ancienne }, 'ancienne') : null,
          ind.a_verifier ? el('span', { class: 'drapeau drapeau--verifier', title: ind.raison_a_verifier }, 'à vérifier') : null,
          // Petit complément : cible d'inflation, direction de la banque centrale…
          complementIndicateur(cle, ind) ? el('small', {}, complementIndicateur(cle, ind)) : null,
        ),
        el('span', { class: 'ligne-indicateur-valeur' },
          valeurIndicateur(cle, ind),
          disponible ? badgeTendance(tendanceIndicateur(cle, ind)) : null,
        ),
        el('span', { class: 'ligne-indicateur-note' }, disponible ? String(ind.note) : '—', disponible ? el('small', {}, '/100') : null),
      );
    }),
  );
}

/** Niveau de confiance de l'agent (faible / moyen / élevé) et ses raisons. */
function blocConfiance(confiance) {
  if (!confiance) return null;
  const cle = { 'élevé': 'eleve', moyen: 'moyen', faible: 'faible' }[confiance.niveau] ?? 'moyen';
  return el('div', { class: `confiance confiance--${cle}` },
    el('span', { class: 'confiance-titre' }, 'Confiance : ', el('strong', {}, confiance.niveau)),
    el('span', { class: 'confiance-raisons' }, confiance.raisons.join(' · ')),
  );
}

/** Dates et sources exactes de chaque valeur. */
function listeSources(p) {
  const tous = { ...p.indicateurs, ...p.detail };
  return el('details', { class: 'detail-repliable sources' },
    el('summary', {}, 'Sources et dates des données'),
    el('ul', { class: 'liste-sources' },
      Object.values(tous).map((ind) => el('li', {},
        el('strong', {}, ind.libelle), ' — ',
        ind.valeur === null || ind.valeur === undefined
          ? `non disponible (${ind.raison ?? 'pas de source'})`
          : `${ind.source} · donnée du ${ind.date}${ind.ancienne ? ' · valeur ancienne conservée' : ''}`,
      ))),
  );
}

/** Section repliable « Détail » (indicateurs secondaires). */
export function detailRepliable(indicateurs, titre = 'Détail') {
  if (!indicateurs || !Object.keys(indicateurs).length) return null;
  return el('details', { class: 'detail-repliable' },
    el('summary', {}, titre, el('small', {}, Object.values(indicateurs).map((i) => i.libelle.toLowerCase()).join(' · '))),
    listeIndicateurs(indicateurs),
  );
}

/** Pied de fiche : fraîcheur des données (date de mise à jour et source). */
export function piedFraicheur(meta) {
  const texte = texteFraicheur(meta);
  return texte ? el('p', { class: 'fraicheur' }, texte) : null;
}

/** Grille d'indicateurs colorés selon leur note (tuiles, conservée pour d'autres usages). */
export function grilleIndicateurs(indicateurs) {
  return el('div', { class: 'indicateurs' },
    Object.entries(indicateurs).map(([cle, ind]) => el('div', { class: `indicateur ${classeNote(ind.note)}` },
      el('div', { class: 'indicateur-libelle' }, ind.libelle),
      el('div', { class: 'indicateur-ligne' },
        el('span', { class: 'indicateur-valeur' }, valeurIndicateur(cle, ind)),
        el('span', { class: 'indicateur-note', title: libelleNiveau(niveauNote(ind.note)) }, `${ind.note}/100`),
      ),
      el('div', { class: 'barre', 'aria-hidden': 'true' }, el('span', { style: { width: `${ind.note}%` } })),
    )),
  );
}

/** Carte « lecture d'un agent » : nom, note, texte. */
export function carteAgent(cle, lecture) {
  return el('article', { class: `agent ${classeNote(lecture.note)}` },
    el('span', { class: 'agent-nom' }, AGENTS[cle] ?? cle),
    el('span', { class: 'agent-note' }, `${lecture.note}/100`),
    el('p', { class: 'agent-texte' }, lecture.texte),
  );
}

/** Niveau de couleur d'un momentum sur 3 mois (en %). */
export function niveauMomentum(momentum) {
  if (momentum >= 2) return 'attractif';
  if (momentum >= -2) return 'neutre';
  return 'defavorable';
}

/* ------------------------------ Fiche pays ------------------------------ */

/**
 * @param {object} d  données chargées (voir donnees.js)
 * @param {object} p  le pays
 * @param {object} nav  { ouvrirSecteur(id) }
 */
export function fichePays(d, p, nav) {
  const secteurs = d.secteursDuPays(p.code);
  return [
    enteteFiche({
      note: p.note, surtitre: `Pays · ${libelleNiveau(niveauNote(p.note))}`, titre: p.nom, verdict: p.verdict,
      action: nav.boutonComparer?.('pays', p.code),
      tendance: tendanceNote(p),
    }),

    blocConfiance(p.confiance),

    el('section', {},
      titreSection('Indicateurs clés', 'flèche = évolution depuis la mise à jour précédente'),
      listeIndicateurs(p.indicateurs),
      detailRepliable(p.detail),
    ),

    // « Ce qui pourrait me donner tort » : contre-scénario de l'agent
    p.contre_scenario?.length ? el('section', {},
      titreSection('Ce qui pourrait me donner tort'),
      el('ul', { class: 'contre-scenario' }, p.contre_scenario.map((t) => el('li', {}, t))),
    ) : null,

    el('section', {},
      titreSection('Secteurs', `${d.fictifPar?.pays === false ? 'données fictives · ' : ''}taille = capitalisation · couleur = momentum 3 mois`),
      bullesSecteurs(secteurs, nav),
      el('div', { class: 'legende-bulles' },
        el('span', {}, el('span', { class: 'pastille pastille--vert' }), '≥ +2 %'),
        el('span', {}, el('span', { class: 'pastille pastille--orange' }), 'entre −2 et +2 %'),
        el('span', {}, el('span', { class: 'pastille pastille--rouge' }), '< −2 %'),
      ),
    ),

    // Lecture de l'agent pays (données réelles) ou, à défaut, lectures fictives des autres agents
    p.lecture ? el('section', {},
      titreSection("Lecture de l'agent pays", p.textes === 'gemini' ? 'rédigée par Gemini' : 'rédigée par des règles'),
      el('div', { class: 'lecture' },
        [['activite_et_prix', 'Activité et prix'], ['politique_monetaire_et_risques', 'Politique monétaire et risques'], ['marches', 'Marchés']]
          .filter(([cle]) => p.lecture[cle])
          .map(([cle, titre]) => el('p', {}, el('strong', {}, `${titre}. `), p.lecture[cle]))),
    ) : el('section', {},
      titreSection('Lecture des agents'),
      el('div', { class: 'agents' },
        ['macro', 'sentiment', 'risque', 'donnees_alternatives']
          .filter((cle) => p.lectures_agents?.[cle])
          .map((cle) => carteAgent(cle, p.lectures_agents[cle])),
      ),
    ),

    p.indicateurs && p.confiance ? listeSources(p) : null,
    piedFraicheur(d.meta.pays),
    el('p', { class: 'mention-legale' }, d.fictifPar?.pays === false
      ? 'Données réelles issues de sources publiques (FMI, OCDE, BIS, Yahoo Finance), analysées automatiquement par l’agent pays. Les secteurs restent fictifs. Ne constitue pas un conseil en investissement.'
      : 'Données fictives à des fins de démonstration — ne constitue pas un conseil en investissement.'),
  ];
}

/** Bulles des secteurs : diamètre proportionnel à la racine de la capitalisation. */
function bullesSecteurs(secteurs, nav) {
  if (!secteurs.length) return el('p', { class: 'fiche-verdict' }, 'Aucun secteur suivi pour ce pays.');
  const racines = secteurs.map((s) => Math.sqrt(s.capitalisation_md));
  const min = Math.min(...racines), max = Math.max(...racines);
  const tailleMin = 84, tailleMax = 138;
  return el('div', { class: 'bulles' },
    secteurs
      .slice()
      .sort((a, b) => b.capitalisation_md - a.capitalisation_md)
      .map((s) => {
        const t = max === min ? 0.6 : (Math.sqrt(s.capitalisation_md) - min) / (max - min);
        const taille = Math.round(tailleMin + t * (tailleMax - tailleMin));
        return el('button', {
          class: `bulle note--${niveauMomentum(s.momentum_3m)}`,
          type: 'button',
          style: { width: `${taille}px` },
          'aria-label': `Secteur ${s.nom}, capitalisation ${nombre(s.capitalisation_md)} milliards d'euros, momentum 3 mois ${variation(s.momentum_3m, 1)}`,
          onclick: () => nav.ouvrirSecteur(s.id),
        },
          el('span', { class: 'bulle-nom' }, s.nom),
          el('span', { class: 'bulle-mom' }, variation(s.momentum_3m, 1)),
          el('span', { class: 'bulle-cap' }, `${nombre(s.capitalisation_md)} Md€`),
        );
      }),
  );
}

/* ------------------------------ Fiche secteur ------------------------------ */

export function ficheSecteur(d, s, nav) {
  const pays = d.paysParCode.get(s.pays);
  const entreprises = d.entreprisesDuSecteur(s.id).slice().sort((a, b) => b.note - a.note);
  return [
    enteteFiche({
      note: s.note,
      surtitre: `Secteur · ${pays?.nom ?? s.pays}`,
      titre: s.nom,
      verdict: `${entreprises.length} entreprise${entreprises.length > 1 ? 's' : ''} suivie${entreprises.length > 1 ? 's' : ''}, classées par note.`,
      tendance: tendanceNote(s),
    }),
    el('div', { class: 'stats' },
      stat('Capitalisation', `${nombre(s.capitalisation_md)} Md€`),
      stat('Momentum 3 mois', variation(s.momentum_3m, 1), `note--${niveauMomentum(s.momentum_3m)}`),
      stat('Note secteur', `${s.note}/100`, classeNote(s.note)),
    ),
    el('section', {},
      titreSection('Entreprises'),
      el('div', { class: 'liste-entreprises' },
        entreprises.map((e) => el('button', {
          class: `ligne-entreprise ${classeNote(e.note)}`,
          type: 'button',
          onclick: () => nav.ouvrirEntreprise(e.ticker),
        },
          el('span', { class: 'pastille', 'aria-hidden': 'true' }),
          el('span', { class: 'ligne-entreprise-textes' },
            el('span', { class: 'ligne-entreprise-nom' }, e.nom),
            el('br'),
            el('span', { class: 'ligne-entreprise-info mono' }, `${e.ticker} · ${nombre(e.capitalisation_md)} Md€ · ${libelleNiveau(e.niveau ?? niveauNote(e.note))}`),
          ),
          el('span', { class: 'ligne-entreprise-note' }, nombre(e.note), badgeTendance(tendanceNote(e))),
        )),
      ),
    ),
    piedFraicheur(d.meta.secteurs),
  ];
}

function stat(libelle, valeur, classe = '') {
  return el('div', { class: `stat ${classe}` },
    el('div', { class: 'stat-libelle' }, libelle),
    el('div', { class: 'stat-valeur', style: classe ? { color: 'var(--c-note)' } : undefined }, valeur),
  );
}
