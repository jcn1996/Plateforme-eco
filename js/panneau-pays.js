/* ==========================================================================
   Fiche pays et fiche secteur (contenu du panneau montant)
   + composants réutilisés par la fiche entreprise (jauge, indicateurs, agents).
   ========================================================================== */

import {
  el, svg, nombre, variation, classeNote, niveauNote, libelleNiveau, valeurIndicateur, AGENTS,
  complementIndicateur, badgeTendance, tendanceIndicateur, tendanceNote, texteFraicheur,
} from './outils.js';
import { sectionMacroPays } from './macro.js';

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
          // Vérification croisée : les sources comparables ne s'accordent pas
          ind.verification === 'divergent'
            ? el('span', { class: 'drapeau drapeau--divergent', title: resumeSources(ind) }, 'sources divergentes') : null,
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

/** Statuts des sources (vérification croisée), dans l'ordre d'affichage. */
const STATUTS = {
  retenue: { texte: 'retenue', classe: 'retenue' },
  concorde: { texte: 'concorde', classe: 'concorde' },
  diverge: { texte: 'diverge', classe: 'diverge' },
  'non comparable': { texte: 'non comparable', classe: 'neutre' },
  'rejetée': { texte: 'rejetée', classe: 'rejetee' },
  'échec': { texte: 'échec', classe: 'rejetee' },
};
const VERIFICATIONS = {
  concordant: 'sources concordantes',
  divergent: 'sources divergentes',
  source_unique: 'une seule source',
  ancienne: 'valeur ancienne conservée',
  aucune_source: 'aucune source valable',
};

/** « FMI 0,4 · OCDE 1,0 » : résumé des valeurs, pour l'infobulle du drapeau. */
function resumeSources(ind) {
  return (ind.sources ?? [])
    .filter((s) => s.valeur !== null && s.valeur !== undefined && ['retenue', 'concorde', 'diverge'].includes(s.statut))
    .map((s) => `${s.nom.split(',')[0]} ${nombre(s.valeur, 1)}`).join(' · ');
}

/** Une source consultée : statut, nom, valeur, date, et la raison d'un rejet ou d'un échec. */
function ligneSource(s, unite) {
  const st = STATUTS[s.statut] ?? { texte: s.statut, classe: 'neutre' };
  const valeur = s.valeur === null || s.valeur === undefined ? null : `${nombre(s.valeur, 2)}${unite ? ` ${unite}` : ''}`;
  return el('li', { class: `source source--${st.classe}` },
    el('span', { class: 'source-statut' }, st.texte),
    el('span', { class: 'source-nom' }, s.nom),
    el('span', { class: 'source-valeur mono' }, valeur ?? '—', s.date ? el('small', {}, ` · ${s.date}`) : null),
    s.raison && s.statut !== 'non comparable' ? el('span', { class: 'source-raison' }, s.raison) : null,
    s.ecart !== undefined && s.statut !== 'retenue' ? el('span', { class: 'source-raison' }, `écart : ${nombre(s.ecart, 2)} pt`) : null,
  );
}

/**
 * Sources et vérification croisée : pour chaque indicateur, les sources consultées,
 * leurs valeurs, leurs dates, leur statut et la valeur retenue.
 */
function listeSources(p) {
  const tous = { ...p.indicateurs, ...p.detail };
  return el('details', { class: 'detail-repliable sources' },
    el('summary', {}, 'Sources et vérification croisée', el('small', {}, 'valeurs, dates, valeur retenue')),
    el('ul', { class: 'liste-sources' },
      Object.entries(tous).map(([cle, ind]) => {
        const disponible = ind.valeur !== null && ind.valeur !== undefined;
        const unite = ind.unite === '% du PIB' ? '%' : ind.unite;
        return el('li', { class: 'source-indicateur' },
          el('div', { class: 'source-entete' },
            el('strong', {}, ind.libelle),
            disponible
              ? el('span', {}, 'retenu : ', el('b', { class: 'mono' }, valeurIndicateur(cle, ind)), ` · donnée du ${ind.date}`)
              : el('span', {}, `non disponible (${ind.raison ?? 'pas de source'})`),
          ),
          disponible && (ind.verification || ind.confiance) ? el('div', { class: `source-verif source-verif--${ind.verification ?? 'inconnue'}` },
            VERIFICATIONS[ind.verification] ?? '',
            ind.confiance ? ` · confiance : ${ind.confiance}` : '',
            ind.ancienne ? ` · ${ind.raison_ancienne}` : '',
          ) : null,
          ind.sources?.length
            ? el('ul', { class: 'liste-sources-detail' }, ind.sources.map((s) => ligneSource(s, unite)))
            : (disponible ? el('p', { class: 'source-raison' }, ind.source) : null),
        );
      })),
  );
}

/** Alerte « Qualité des données » : plus d'un tiers des sources du pays en échec ou rejetées. */
function blocQualite(q) {
  if (!q?.alerte) return null;
  return el('div', { class: 'alerte-qualite', role: 'status' },
    el('strong', {}, '⚠ Qualité des données'),
    el('span', {}, `${q.sources_en_echec} source${q.sources_en_echec > 1 ? 's' : ''} sur ${q.sources_consultees} en échec ou rejetée${q.sources_en_echec > 1 ? 's' : ''} : les conclusions de cette fiche sont fragiles.`),
    q.details?.length ? el('small', {}, q.details.join(' · ')) : null,
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

    blocQualite(p.qualite),
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

    // Rubrique « Agent macro » : texte réel de l'agent macro (data/macro.json), avec sa date
    sectionMacroPays(d.macro, p.code),

    p.indicateurs && p.confiance ? listeSources(p) : null,
    piedFraicheur(d.meta.pays),
    el('p', { class: 'mention-legale' }, d.fictifPar?.pays === false
      ? 'Données réelles issues de sources publiques (instituts statistiques nationaux, banques centrales, FMI, OCDE, BRI, Banque mondiale, Eurostat, BCE, Yahoo Finance), vérifiées entre elles et analysées automatiquement par l’agent pays. Les secteurs restent fictifs. Ne constitue pas un conseil en investissement.'
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
