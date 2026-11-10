/* ==========================================================================
   Menu : panneau qui regroupe tous les écrans de l'appli, classés.
   Sur téléphone, l'en-tête ne garde que le titre, la pastille de risque, la recherche,
   le portefeuille démo et le bouton « Menu » ; sur grand écran, d'autres raccourcis
   s'ajoutent à l'en-tête, mais tout reste accessible ici.
   ========================================================================== */

import { el } from './outils.js';

/**
 * Sections du menu. Chaque entrée : libellé, description courte, et soit une route
 * (ouverte par `ouvrir(route)`), soit une action nommée (fournie par l'appli).
 */
export const SECTIONS_MENU = [
  { titre: 'Synthèse', entrees: [
    { libelle: 'Où investir', detail: 'chef d’orchestre : verdicts et allocation', route: { type: 'investir' } },
    { libelle: 'Briefing', detail: 'briefing complet du jour', action: 'briefing' },
  ] },
  { titre: 'Analyses', entrees: [
    { libelle: 'Vue macro', detail: 'cycle, récession, banques centrales', route: { type: 'macro' } },
    { libelle: 'Pays · Classement', detail: 'notes des pays suivis', route: { type: 'classement' } },
    { libelle: 'Pépites', detail: 'sociétés candidates', route: { type: 'pepites' } },
    { libelle: 'Matières premières', detail: 'faut-il s’exposer sur 3 à 12 mois ?', route: { type: 'matieres' } },
    { libelle: 'Géopolitique', detail: 'événements et risque par pays', route: { type: 'geopolitique' } },
    { libelle: 'Risque', detail: 'stress financier et contradicteur', route: { type: 'risque' } },
    { libelle: 'Initiés', detail: 'dirigeants, super-investisseurs, activistes', route: { type: 'inities' } },
    { libelle: 'Données alternatives', detail: 'l’activité réelle avant l’officiel', route: { type: 'alternatives' } },
  ] },
  { titre: 'Outils', entrees: [
    { libelle: 'Analyser une entreprise', detail: 'analyse à la demande', action: 'analyser' },
    { libelle: 'Mes analyses', detail: 'résultats des analyses demandées', route: { type: 'analyses' } },
    { libelle: 'Comparateur', detail: 'pays ou entreprises côte à côte', route: { type: 'comparaison' } },
    { libelle: 'Mes alertes', detail: 'règles personnelles', route: { type: 'mes-alertes' } },
  ] },
  { titre: 'Suivi', entrees: [
    { libelle: 'Mes portefeuilles', detail: 'vos portefeuilles réels, sur cet appareil uniquement', route: { type: 'mes-portefeuilles' } },
    { libelle: 'Portefeuille démo', detail: 'agent trader, 100 000 € virtuels', route: { type: 'portefeuille' } },
    { libelle: 'Fiabilité du chef d’orchestre', detail: 'performance des verdicts', route: { type: 'fiabilite-chef' } },
    { libelle: 'Fiabilité des recommandations', detail: 'analyses à la demande', route: { type: 'fiabilite' } },
    { libelle: 'Santé des agents', detail: 'exécutions et sources', route: { type: 'sante' }, sante: true },
  ] },
  { titre: 'Affichage', entrees: [
    { libelle: 'Légende des couleurs', detail: 'ce que représentent les couleurs du globe', action: 'legende' },
    { libelle: 'Mode léger', detail: 'économie de batterie', action: 'leger', bascule: true },
  ] },
];

/**
 * Branche le menu.
 * - elements : { bouton, menu, contenu }
 * - ouvrir(route) : navigation ;
 * - actions : { briefing(), analyser(), legende(), leger() } ;
 * - etat() : { routeType, probleme (santé), leger (bool) } pour l'état affiché à l'ouverture.
 */
export function initialiserMenu({ bouton, menu, contenu }, ouvrir, actions, etat) {
  let dernierFocus = null;

  function rendre() {
    const e = etat();
    contenu.replaceChildren(...SECTIONS_MENU.map((s) => el('section', { class: 'menu-section' },
      el('h2', { class: 'menu-titre' }, s.titre),
      el('ul', { class: 'menu-liste' }, s.entrees.map((x) => {
        const actif = x.route && x.route.type === e.routeType;
        return el('li', {}, el('button', {
          class: `menu-entree${actif ? ' est-actif' : ''}${x.sante && e.probleme ? ' a-un-probleme' : ''}`,
          type: 'button', 'aria-current': actif ? 'page' : null, 'aria-pressed': x.bascule ? String(Boolean(e[x.action])) : null,
          onclick: () => choisir(x),
        },
        el('span', { class: 'menu-entree-libelle' }, x.libelle,
          x.sante && e.probleme ? el('span', { class: 'menu-alerte' }, 'problème détecté') : null,
          x.bascule ? el('span', { class: 'menu-bascule' }, e[x.action] ? 'activé' : 'désactivé') : null),
        el('span', { class: 'menu-entree-detail' }, x.detail)));
      })))));
  }

  function choisir(x) {
    fermer(false);
    if (x.route) ouvrir(x.route);
    else actions[x.action]?.();
  }

  function ouvrirMenu() {
    dernierFocus = document.activeElement;
    rendre();
    menu.hidden = false;
    bouton.setAttribute('aria-expanded', 'true');
    document.body.classList.add('menu-ouvert');
    menu.querySelector('.menu-entree')?.focus({ preventScroll: true });
  }

  function fermer(rendreFocus = true) {
    if (menu.hidden) return;
    menu.hidden = true;
    bouton.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('menu-ouvert');
    if (rendreFocus) dernierFocus?.focus?.({ preventScroll: true });
  }

  bouton.addEventListener('click', () => (menu.hidden ? ouvrirMenu() : fermer()));
  menu.querySelectorAll('.js-menu-fermer').forEach((b) => b.addEventListener('click', () => fermer()));

  return { ouvert: () => !menu.hidden, fermer, ouvrir: ouvrirMenu };
}
