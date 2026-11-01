/* ==========================================================================
   Fiche pays et fiche secteur (contenu du panneau montant)
   + composants réutilisés par la fiche entreprise (jauge, indicateurs, agents).
   ========================================================================== */

import { el, svg, nombre, variation, classeNote, niveauNote, libelleNiveau, valeurIndicateur, AGENTS } from './outils.js';

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
export function enteteFiche({ note, surtitre, titre, verdict }) {
  return el('header', { class: 'fiche-entete' },
    jauge(note),
    el('div', { class: 'fiche-titres' },
      el('div', { class: 'fiche-surtitre' }, surtitre),
      el('h2', { class: 'fiche-titre' }, titre),
      verdict ? el('p', { class: 'fiche-verdict' }, verdict) : null,
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
    Object.entries(indicateurs).map(([cle, ind]) => el('li', {
      class: `ligne-indicateur ${classeNote(ind.note)}`,
      title: libelleNiveau(niveauNote(ind.note)),
    },
      el('span', { class: 'pastille', 'aria-hidden': 'true' }),
      el('span', { class: 'ligne-indicateur-libelle' }, ind.libelle),
      el('span', { class: 'ligne-indicateur-valeur' }, valeurIndicateur(cle, ind)),
      el('span', { class: 'ligne-indicateur-note' }, String(ind.note), el('small', {}, '/100')),
    )),
  );
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
    enteteFiche({ note: p.note, surtitre: `Pays · ${libelleNiveau(niveauNote(p.note))}`, titre: p.nom, verdict: p.verdict }),

    el('section', {},
      titreSection('Indicateurs clés'),
      listeIndicateurs(p.indicateurs),
    ),

    el('section', {},
      titreSection('Secteurs', 'taille = capitalisation · couleur = momentum 3 mois'),
      bullesSecteurs(secteurs, nav),
      el('div', { class: 'legende-bulles' },
        el('span', {}, el('span', { class: 'pastille pastille--vert' }), '≥ +2 %'),
        el('span', {}, el('span', { class: 'pastille pastille--orange' }), 'entre −2 et +2 %'),
        el('span', {}, el('span', { class: 'pastille pastille--rouge' }), '< −2 %'),
      ),
    ),

    el('section', {},
      titreSection('Lecture des agents'),
      el('div', { class: 'agents' },
        ['macro', 'sentiment', 'risque', 'donnees_alternatives']
          .filter((cle) => p.lectures_agents?.[cle])
          .map((cle) => carteAgent(cle, p.lectures_agents[cle])),
      ),
    ),

    el('p', { class: 'mention-legale' }, 'Données fictives à des fins de démonstration — ne constitue pas un conseil en investissement.'),
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
          el('span', { class: 'ligne-entreprise-note' }, nombre(e.note)),
        )),
      ),
    ),
  ];
}

function stat(libelle, valeur, classe = '') {
  return el('div', { class: `stat ${classe}` },
    el('div', { class: 'stat-libelle' }, libelle),
    el('div', { class: 'stat-valeur', style: classe ? { color: 'var(--c-note)' } : undefined }, valeur),
  );
}
