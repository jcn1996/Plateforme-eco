/* ==========================================================================
   Fiche entreprise (données réelles de l'agent entreprises) :
   note et verdict, confiance, indicateurs, montants (devise locale et dollars),
   F-score, signaux d'alerte, revue critique (pépites), contexte pays,
   « Ce qui pourrait me donner tort », lecture des agents, étude complète, sources.
   Les anciennes données fictives restent affichables (champs absents ignorés).
   ========================================================================== */

import { el, nombre, AGENTS, tendanceNote, variation } from './outils.js';
import { pastilleReco, fichierAnalyse } from './analyses.js';
import { graphiqueAvance } from './graphiques.js';
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

/** Clôtures hebdomadaires publiées par l'agent entreprises (fiche ou analyse à la demande), pour le graphique simple. */
export function historiqueEntreprise(e) {
  return async () => {
    if (e.cours_hebdo?.length) return e.cours_hebdo;
    const chemin = e.fiche ?? (e.analyseDemande || e.demande ? fichierAnalyse(e.ticker) : null);
    if (!chemin) return null;
    try {
      const r = await fetch(chemin, { cache: 'no-cache' });
      return r.ok ? ((await r.json()).donnees?.cours_hebdo ?? null) : null;
    } catch {
      return null;
    }
  };
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
    blocRecommandation(e.recommandation, nav),
    blocContexte(e.contexte),
    blocRang(e.rang_secteur),

    el('section', {},
      titreSection('Indicateurs clés', e.financier ? `critères adaptés (${e.financier === 'banque' ? 'banque' : e.financier === 'assurance' ? 'assurance' : 'société financière'})` : 'note sur 100 par indicateur'),
      listeIndicateurs(e.indicateurs),
    ),

    // Graphique TradingView (chargé quand il apparaît à l'écran, une fois le détail de la fiche lu)
    e.fiche && !e.detailCharge ? null : el('section', {},
      titreSection('Graphique', 'bougies · moyennes mobiles 50 et 200 jours · volume'),
      graphiqueAvance({ yahoo: e.ticker, place: e.place, historique: historiqueEntreprise(e) }),
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
    e.analyseDemande
      ? el('p', { class: 'fraicheur' }, `Analyse à la demande du ${dateFr(e.demande?.date)}${e.demande?.issue ? ` · issue #${e.demande.issue}` : ''} · même grille que l’agent entreprises (règles, sans IA)`,
        e.demande?.url_issue ? [' · ', el('a', { href: e.demande.url_issue, target: '_blank', rel: 'noopener' }, 'demande ↗')] : null)
      : piedFraicheur(d.meta.entreprises),

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

function prix(v, devise) {
  if (v == null) return 'n. d.';
  return `${nombre(v, Math.abs(v) < 1000 ? 2 : 0)} ${devise ?? ''}`.trim();
}

/** Recommandation à 12 mois : deux lectures, fourchette de valeur (deux méthodes), signaux, conditions d'invalidation, risques. */
function blocRecommandation(r, nav = {}) {
  if (!r) return null;
  // Résumé de data/entreprises.json ({n, d, e}) tant que la fiche détaillée n'est pas chargée
  if (!r.signaux) {
    return el('section', { class: 'carte recommandation' }, titreSection('Recommandation', 'horizon 12 mois'),
      el('div', { class: 'reco-lectures' },
        el('div', {}, el('small', {}, 'Si non détenu'), pastilleReco(r)),
        el('div', {}, el('small', {}, 'Si détenu'), pastilleReco(r, true))));
  }
  const v = r.valeur;
  const sens = (s) => (s > 0 ? 'favorable' : s < 0 ? 'défavorable' : 'neutre');
  return el('section', { class: 'carte recommandation' },
    titreSection('Recommandation', `horizon ${r.horizon_mois} mois`),
    el('div', { class: 'reco-lectures' },
      el('div', {}, el('small', {}, 'Si non détenu'), pastilleReco({ n: r.si_non_detenu })),
      el('div', {}, el('small', {}, 'Si détenu'), pastilleReco({ d: r.si_detenu }, true)),
    ),
    el('dl', { class: 'reco-valeur' },
      el('dt', {}, 'Cours'), el('dd', { class: 'mono' }, `${prix(r.cours, r.devise)}`, el('small', {}, ` au ${dateFr(r.date_cours)}`)),
      v ? [el('dt', {}, 'Valeur estimée'), el('dd', { class: 'mono' }, `${prix(v.bas, r.devise)} – ${prix(v.haut, r.devise)}`,
        el('small', {}, ` centrale ${prix(v.centrale, r.devise)}`))] : [el('dt', {}, 'Valeur estimée'), el('dd', {}, 'non calculable')],
      v?.ecart_pct != null ? [el('dt', {}, 'Écart au cours'), el('dd', { class: `mono ${v.ecart_pct > 0 ? 'hausse' : 'baisse'}` }, variation(v.ecart_pct, 1))] : null,
      r.prix_repli ? [el('dt', {}, 'Passerait à « Acheter »'), el('dd', { class: 'mono' }, `sous ${prix(r.prix_repli, r.devise)}`)] : null,
    ),
    v && !v.fiable ? el('p', { class: 'reco-reserve' }, `Estimation non exploitable pour le signal de valorisation : ${v.reserve}.`) : null,
    el('p', { class: 'fiche-verdict' }, r.justification),
    el('ul', { class: 'reco-signaux' }, r.signaux.map((s) => el('li', { class: `reco-signal reco-signal--${s.sens > 0 ? 'pos' : s.sens < 0 ? 'neg' : 'neutre'}` },
      el('span', { 'aria-hidden': 'true' }, s.sens > 0 ? '▲' : s.sens < 0 ? '▼' : '•'), el('strong', {}, s.libelle), ` : ${s.texte}`,
      el('span', { class: 'visuellement-cache' }, ` (${sens(s.sens)})`)))),
    el('h4', {}, 'Ce qui invaliderait la recommandation'),
    el('ul', { class: 'contre-scenario' }, r.conditions_invalidation.map((c) => el('li', {}, c))),
    r.risques?.length ? [el('h4', {}, 'Principaux risques'), el('ul', { class: 'contre-scenario' }, r.risques.map((c) => el('li', {}, c)))] : null,
    v?.methodes?.length ? el('details', { class: 'detail-repliable' },
      el('summary', {}, 'Méthodes et hypothèses'),
      el('ul', { class: 'liste-sources' }, v.methodes.map((m) => el('li', {}, el('strong', {}, `${m.nom} : `), `${prix(m.bas, r.devise)} – ${prix(m.haut, r.devise)}`,
        el('br', {}),
        m.cle === 'dcf'
          ? `Croissance initiale ${nombre(m.hypotheses.croissance, 1)} % ramenée à ${nombre(m.hypotheses.croissance_terminale, 1)} % en ${m.hypotheses.annees} ans ; taux d’actualisation ${nombre(m.hypotheses.taux_actualisation, 1)} % ; fourchette : ${m.hypotheses.fourchette}.`
          : `${(m.hypotheses.references ?? []).join(' ; ')} (${m.hypotheses.base}).`)))) : null,
    nav.ouvrirFiabilite ? el('button', { type: 'button', class: 'lien', onclick: nav.ouvrirFiabilite }, 'Fiabilité des recommandations passées ›') : null,
    el('p', { class: 'reco-mention' }, r.mention),
  );
}

/** Rang dans le secteur (analyses à la demande). */
function blocRang(r) {
  if (!r?.monde) return null;
  const rang = (x) => `${x.rang}${x.rang === 1 ? 're' : 'e'} sur ${x.total}`;
  return el('section', { class: 'carte' },
    titreSection('Rang dans le secteur', `${r.secteur_nom} · sociétés déjà analysées`),
    el('dl', { class: 'reco-valeur' },
      el('dt', {}, 'Monde'), el('dd', { class: 'mono' }, rang(r.monde), el('small', {}, ` note médiane ${r.monde.note_mediane}/100`)),
      r.region ? [el('dt', {}, r.region.nom), el('dd', { class: 'mono' }, rang(r.region), el('small', {}, ` note médiane ${r.region.note_mediane}/100`))] : null,
    ),
    r.meilleures?.length ? el('p', { class: 'fiche-verdict' }, 'Mieux notées du secteur : ', r.meilleures.map((m) => `${m.nom} (${m.note})`).join(', '), '.') : null,
  );
}
