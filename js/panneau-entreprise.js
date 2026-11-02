/* ==========================================================================
   Fiche entreprise : 5 indicateurs, verdict de l'agent, onglets par agent,
   étude complète dépliable.
   ========================================================================== */

import { el, nombre, AGENTS, tendanceNote } from './outils.js';
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

export function ficheEntreprise(d, e, nav = {}) {
  const secteur = d.secteurParId.get(e.secteur);
  const pays = d.paysParCode.get(e.pays);

  return [
    enteteFiche({
      note: e.note,
      surtitre: `${e.ticker} · ${secteur?.nom ?? ''} · ${pays?.nom ?? ''} · ${nombre(e.capitalisation_md)} Md€`,
      titre: e.nom,
      verdict: e.verdict, // verdict de l'agent entreprises, tout en haut
      action: nav.boutonComparer?.('entreprise', e.ticker),
      tendance: tendanceNote(e),
    }),

    el('section', {},
      titreSection('Indicateurs clés'),
      listeIndicateurs(e.indicateurs),
    ),

    el('section', {},
      titreSection('Lecture par agent'),
      ongletsAgents(e),
    ),

    etudeComplete(e),

    piedFraicheur(d.meta.entreprises),

    el('p', { class: 'mention-legale' }, 'Entreprise et chiffres inventés — démonstration uniquement, ne constitue pas un conseil en investissement.'),
  ];
}

/** Onglets accessibles (rôles ARIA tablist / tab / tabpanel). */
function ongletsAgents(e) {
  const cles = ORDRE_AGENTS.filter((cle) => e.agents?.[cle]);
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
    panneau.replaceChildren(carteAgent(cle, e.agents[cle]));
  }
  if (cles.length) choisir(cles[0]);

  return el('div', {}, el('div', { class: 'onglets', role: 'tablist', 'aria-label': 'Agents' }, boutons), panneau);
}

/** Bouton « Voir l'étude complète » qui déplie l'analyse détaillée. */
function etudeComplete(e) {
  const corps = el('div', { class: 'etude-corps', id: `etude-${e.ticker}`, hidden: true },
    (e.etude_complete ?? []).map((partie) => [el('h4', {}, partie.titre), el('p', {}, partie.texte)]),
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
