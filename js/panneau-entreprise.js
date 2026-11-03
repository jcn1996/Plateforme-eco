/* ==========================================================================
   Fiche entreprise (données réelles de l'agent entreprises) :
   note et verdict, confiance, indicateurs, montants (devise locale et dollars),
   F-score, signaux d'alerte, revue critique (pépites), contexte pays,
   « Ce qui pourrait me donner tort », lecture des agents, étude complète, sources.
   Les anciennes données fictives restent affichables (champs absents ignorés).
   ========================================================================== */

import { el, nombre, AGENTS, tendanceNote, variation } from './outils.js';
import { enteteFiche, listeIndicateurs, titreSection, carteAgent, piedFraicheur } from './panneau-pays.js';

/** Ordre d'affichage des onglets. */
const ORDRE_AGENTS = ['entreprises', 'macro', 'sentiment', 'risque', 'donnees_alternatives'];

/** Libellés courts pour les onglets (l'écran d'un téléphone est étroit). */
const ONGLETS = {
  entreprises: 'Entreprises',
  macro: 'Macro',
  sentiment: 'Sentiment',
  risque: 'Risque',
  donnees_alternatives: 'Données alt.',
};

const LIBELLES_MONTANTS = { ca: "Chiffre d'affaires", resultat_net: 'Résultat net', fcf: 'Flux de trésorerie disponible', dette_nette: 'Dette nette' };

function dateFr(d) {
  if (!d) return 'date inconnue';
  const s = String(d);
  return `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
}

/** Charge la fiche détaillée d'une société (data/entreprises/fiches/<ticker>.json) et la fusionne. */
export async function chargerFiche(e) {
  try {
    const r = await fetch(e.fiche, { cache: 'no-cache' });
    if (!r.ok) return false;
    const j = await r.json();
    Object.assign(e, j.donnees ?? {}, { detailCharge: true });
    return true;
  } catch {
    return false;
  }
}

export function ficheEntreprise(d, e, nav = {}) {
  const secteur = d.secteurParId.get(e.secteur);
  const pays = d.paysParCode.get(e.pays);
  const reel = d.fictifPar?.entreprises === false;
  const cap = e.capitalisation_md != null ? `${nombre(e.capitalisation_md, e.capitalisation_md < 10 ? 1 : 0)} Md${reel ? '$' : '€'}` : '';
  // Lecture macro du pays (agent macro), affichée comme second onglet
  const agents = { ...(e.agents ?? {}) };
  const lectureMacro = d.macro?.lectures_pays?.[e.pays];
  if (reel && lectureMacro) agents.macro = { texte: lectureMacro.texte, note: null, date: lectureMacro.date };

  return [
    enteteFiche({
      note: e.note,
      surtitre: [e.ticker, e.secteur_nom ?? secteur?.nom, pays?.nom ?? e.pays, cap].filter(Boolean).join(' · '),
      titre: e.nom,
      verdict: e.verdict,
      action: nav.boutonComparer?.('entreprise', e.ticker),
      tendance: tendanceNote(e),
    }),

    e.fiche && !e.detailCharge ? el('p', { class: 'fiche-verdict' }, 'Chargement du détail…') : null,
    e.pepite || e.qpr ? el('p', { class: 'pepite-bandeau' }, el('strong', {}, e.pepite ? 'Pépite candidate' : 'Qualité à prix raisonnable'), ' · tous les critères sont remplis ; revue critique ci-dessous') : null,
    e.autres_cotations?.length ? el('p', { class: 'entreprise-cotations' },
      `Autres cotations : ${e.autres_cotations.map((c) => `${c.ticker} (${d.paysParCode.get(c.pays)?.nom ?? c.pays})`).join(', ')} · cotation retenue : la plus liquide`) : null,
    e.holding ? el('p', { class: 'entreprise-cotations' }, 'Holding ou société d’investissement : exclue des pépites (la décote sur l’actif net n’est pas mesurée).') : null,
    blocConfiance(e.confiance),
    blocContexte(e.contexte),

    el('section', {},
      titreSection('Indicateurs clés', e.financier ? `critères adaptés (${e.financier === 'banque' ? 'banque' : e.financier === 'assurance' ? 'assurance' : 'société financière'})` : 'note sur 100 par indicateur'),
      listeIndicateurs(e.indicateurs),
    ),

    blocMontants(e),
    blocFscore(e.fscore),
    blocAlertes(e.alertes),
    blocRevue(e.revue_critique),

    e.contre_scenario?.length ? el('section', {},
      titreSection('Ce qui pourrait me donner tort'),
      el('ul', { class: 'contre-scenario' }, e.contre_scenario.map((t) => el('li', {}, t))),
    ) : null,

    Object.keys(agents).length ? el('section', {},
      titreSection('Lecture par agent'),
      ongletsAgents(e, agents),
    ) : null,

    etudeComplete(e),
    blocSources(e),
    piedFraicheur(d.meta.entreprises),

    el('p', { class: 'mention-legale' }, reel
      ? 'Données réelles issues de sources publiques (sources officielles et Yahoo Finance), analysées automatiquement par l’agent entreprises. Ne constitue pas un conseil en investissement.'
      : 'Entreprise et chiffres inventés — démonstration uniquement, ne constitue pas un conseil en investissement.'),
  ];
}

function blocConfiance(c) {
  if (!c) return null;
  const cle = { 'élevé': 'eleve', moyen: 'moyen', faible: 'faible' }[c.niveau] ?? 'moyen';
  return el('div', { class: `confiance confiance--${cle}` },
    el('span', { class: 'confiance-titre' }, 'Confiance : ', el('strong', {}, c.niveau)),
    c.raisons?.length ? el('span', { class: 'confiance-raisons' }, c.raisons.join(' · ')) : null,
  );
}

/** Ajustement de contexte (pays et cycle), affiché à part de la note. */
function blocContexte(ctx) {
  if (!ctx) return null;
  return el('div', { class: 'carte entreprise-contexte' },
    el('div', { class: 'entreprise-contexte-ligne' },
      el('span', {}, 'Ajustement de contexte'),
      el('strong', { class: `mono ${ctx.ajustement > 0 ? 'hausse' : ctx.ajustement < 0 ? 'baisse' : ''}` }, variation(ctx.ajustement, 1, ' pt')),
    ),
    el('div', { class: 'entreprise-contexte-detail' },
      `Note ajustée : ${nombre(ctx.note_ajustee, 1)}/100`, ctx.details?.length ? ` · ${ctx.details.join(' · ')}` : '',
      ' · la note de la société ne l’inclut pas'),
  );
}

function blocMontants(e) {
  const m = e.montants;
  if (!m || !Object.keys(m).length) return null;
  return el('section', {},
    titreSection('Montants du dernier exercice', `${e.devise ?? ''} et dollars${e.sources?.exercice ? ` · clos le ${dateFr(e.sources.exercice)}` : ''}`),
    el('dl', { class: 'entreprise-montants' },
      Object.entries(m).map(([cle, v]) => [
        el('dt', {}, LIBELLES_MONTANTS[cle] ?? cle),
        el('dd', {}, el('span', { class: 'mono' }, v.local_texte), el('small', {}, v.usd_texte)),
      ])),
  );
}

function blocFscore(f) {
  if (!f) return null;
  return el('section', {},
    titreSection('F-score de Piotroski', `${f.score}/9${f.calcules < 9 ? ` · ${f.calcules} critères calculables sur 9, score ramené sur 9` : ''}`),
    el('ul', { class: 'fscore' }, f.criteres.map((c) => el('li', { class: c.ok === null ? 'fscore--na' : c.ok ? 'fscore--ok' : 'fscore--ko' },
      el('span', { 'aria-hidden': 'true' }, c.ok === null ? '–' : c.ok ? '✓' : '✗'),
      el('span', {}, c.libelle),
      el('span', { class: 'visuellement-cache' }, c.ok === null ? 'non calculable' : c.ok ? 'rempli' : 'non rempli'),
    ))),
  );
}

function blocAlertes(a) {
  if (!a) return null;
  return el('section', {},
    titreSection('Signaux d’alerte comptables'),
    a.length
      ? el('ul', { class: 'entreprise-alertes' }, a.map((x) => el('li', {}, el('strong', {}, x.titre), ` : ${x.texte}.`)))
      : el('p', { class: 'fiche-verdict' }, 'Aucun signal relevé (écart bénéfice/cash, dilution, créances, stocks).'),
  );
}

function blocRevue(r) {
  if (!r) return null;
  return el('section', { class: 'revue-critique' },
    titreSection('Revue critique', 'obligatoire pour chaque pépite'),
    el('h4', {}, 'Risques'), el('ul', {}, r.risques.map((t) => el('li', {}, t))),
    el('p', {}, el('strong', {}, 'Piège de valeur : '), r.piege_de_valeur),
    el('p', {}, el('strong', {}, 'Risque de change : '), r.risque_change),
    el('p', {}, el('strong', {}, 'Risque pays : '), r.risque_pays),
    el('h4', {}, 'À vérifier soi-même'), el('ul', {}, r.a_verifier.map((t) => el('li', {}, t))),
    r.rapport_officiel
      ? el('p', {}, el('a', { href: r.rapport_officiel, target: '_blank', rel: 'noopener' }, 'Dernier rapport officiel ↗'))
      : el('p', { class: 'fiche-verdict' }, 'Pas de rapport officiel exploité par l’agent pour cette société.'),
  );
}

function blocSources(e) {
  const s = e.sources;
  if (!s) return null;
  const v = s.verification;
  const verif = !v ? 'pas de source officielle exploitée'
    : v.statut === 'concordant' ? `concordant avec Yahoo Finance sur l’exercice clos le ${dateFr(v.exercice)}`
      : v.statut === 'divergent' ? `écart avec Yahoo Finance (${Object.entries(v.ecarts_pct ?? {}).map(([k, x]) => `${k === 'ca' ? 'CA' : 'résultat net'} ${variation(x, 1)}`).join(', ')}) : la source officielle est retenue`
        : v.detail ?? 'non comparable';
  return el('details', { class: 'detail-repliable sources' },
    el('summary', {}, 'Sources et dates', el('small', {}, s.officielle ? 'source officielle + Yahoo' : 'Yahoo Finance')),
    el('ul', { class: 'liste-sources' },
      el('li', {}, el('strong', {}, 'Comptes : '), s.comptes),
      el('li', {}, el('strong', {}, 'Vérification croisée : '), verif),
      el('li', {}, el('strong', {}, 'Dernier exercice : '), dateFr(s.exercice), s.maj_comptes ? ` · comptes relus le ${dateFr(s.maj_comptes)}` : ''),
      el('li', {}, el('strong', {}, 'Cours : '), `Yahoo Finance, ${dateFr(s.date_cours)}`),
      s.rapport_officiel ? el('li', {}, el('a', { href: s.rapport_officiel, target: '_blank', rel: 'noopener' }, 'Rapport officiel ↗')) : null,
      s.composition ? el('li', {}, el('strong', {}, 'Univers : '), s.composition) : null,
      s.ancienne ? el('li', {}, 'Dernière analyse connue conservée : les sources n’ont pas répondu lors de la dernière révision.') : null,
    ),
  );
}

/** Onglets accessibles (rôles ARIA tablist / tab / tabpanel). */
function ongletsAgents(e, agents) {
  const cles = ORDRE_AGENTS.filter((cle) => agents[cle]);
  const idBase = `onglets-${e.ticker}`;
  const panneau = el('div', { class: 'onglet-panneau', role: 'tabpanel', id: `${idBase}-panneau` });
  const boutons = cles.map((cle, i) => el('button', {
    class: 'onglet', type: 'button', role: 'tab', id: `${idBase}-${cle}`,
    'aria-selected': i === 0 ? 'true' : 'false', 'aria-controls': `${idBase}-panneau`,
    title: AGENTS[cle],
    onclick: () => choisir(cle),
  }, ONGLETS[cle] ?? cle));

  function choisir(cle) {
    boutons.forEach((b, i) => b.setAttribute('aria-selected', String(cles[i] === cle)));
    panneau.setAttribute('aria-labelledby', `${idBase}-${cle}`);
    const a = agents[cle];
    panneau.replaceChildren(a.note == null
      ? el('article', { class: 'agent' }, el('span', { class: 'agent-nom' }, AGENTS[cle] ?? cle),
        el('p', { class: 'agent-texte' }, a.texte), a.date ? el('small', { class: 'fiche-verdict' }, `mis à jour le ${dateFr(a.date)}`) : null)
      : carteAgent(cle, a));
  }
  if (cles.length) choisir(cles[0]);

  return el('div', {}, el('div', { class: 'onglets', role: 'tablist', 'aria-label': 'Agents' }, boutons), panneau);
}

/** Bouton « Voir l'étude complète » qui déplie l'analyse détaillée. */
function etudeComplete(e) {
  if (!e.etude_complete?.length) return null;
  const corps = el('div', { class: 'etude-corps', id: `etude-${e.ticker}`, hidden: true },
    e.etude_complete.map((partie) => [el('h4', {}, partie.titre), el('p', {}, partie.texte)]),
  );
  const bouton = el('button', {
    class: 'bouton bouton--accent bouton--plein', type: 'button',
    'aria-expanded': 'false', 'aria-controls': `etude-${e.ticker}`,
    onclick: () => {
      const ouvert = bouton.getAttribute('aria-expanded') === 'true';
      bouton.setAttribute('aria-expanded', String(!ouvert));
      bouton.textContent = ouvert ? "Voir l'étude complète" : "Masquer l'étude complète";
      corps.hidden = ouvert;
      if (!ouvert) requestAnimationFrame(() => corps.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    },
  }, "Voir l'étude complète");
  return el('section', { class: 'etude' }, bouton, corps);
}
