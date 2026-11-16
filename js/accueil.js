/* ==========================================================================
   Accueil : réseau des agents (premier écran)
   --------------------------------------------------------------------------
   Sous l'en-tête et le bandeau des marchés (inchangés) :
   - la scène du réseau (js/reseau-scene.js) : le chef d'orchestre au centre,
     11 agents autour, une information par bulle (config/reseau_agents.json) ;
   - une légende discrète des liens ;
   - la carte repliable « À retenir aujourd'hui » (liste unique du chef d'orchestre, révisée chaque mois) ;
   - le panneau de synthèse d'un agent, ouvert en touchant sa bulle (#/accueil/<agent>).
   Le globe reste accessible par la bulle « Pays » et par le Menu.
   ========================================================================== */

import { el } from './outils.js';
import { lirePreference, memoriserPreference } from './interface.js';
import { statutAgent } from './sante.js';
import { CONFIG_RESEAU, ETATS_RESEAU, calculerReseau, fichiersReseau, aRetenir } from './reseau.js';
import { SceneReseau } from './reseau-scene.js';

const CLE_CARTE = 'salle-controle:a-retenir';
const mouvementReduit = matchMedia('(prefers-reduced-motion: reduce)');

async function chargerConfig() {
  try {
    const r = await fetch(CONFIG_RESEAU, { cache: 'no-cache' });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

/** Lecture par défaut d'un fichier de données : bloc « donnees » (null si absent). */
async function lireDonnees(fichier) {
  try {
    const r = await fetch(fichier, { cache: 'no-cache' });
    if (!r.ok) return null;
    const j = await r.json();
    if (Array.isArray(j?.donnees)) return j.donnees;
    return j?.donnees ? { meta: j.meta ?? {}, ...j.donnees } : null;
  } catch {
    return null;
  }
}

/**
 * Crée l'accueil.
 * - section : élément #accueil ;
 * - sources : données déjà chargées par l'appli { 'data/chef.json': chef, … } ;
 * - chargeurs : lecteurs à utiliser pour les autres fichiers { 'data/inities.json': () => … } ;
 * - contexte() : { chef, alertes, entrepriseExiste(ticker), paysExiste(code) } ;
 * - naviguer(route), fermer() : navigation de l'appli.
 */
export function creerAccueil({ section, sources = {}, chargeurs = {}, contexte, naviguer, fermer, leger = false }) {
  let config = null;
  let scene = null;
  let reseau = null;
  let sante = {};
  let actif = false;
  let agentOuvert = null;
  let modeLeger = leger;
  const donnees = { ...sources };
  let demarrage = null;

  // Structure de l'écran
  const zone = el('div', { class: 'reseau-zone', id: 'reseau-zone' });
  const legende = el('ul', { class: 'reseau-legende', 'aria-label': 'Légende des liens du réseau' },
    el('li', {}, trait('decision'), 'pèse dans la décision'),
    el('li', {}, trait('contexte'), 'contexte'),
    el('li', {}, trait('decision', 'panne'), 'rouge sans impulsion : en panne (✕)'),
    el('li', {}, el('span', { class: 'reseau-etat reseau-pastille-degrade', 'aria-hidden': 'true' }, '●'), ' sous le nom : dégradé, une source secondaire manque'),
  );
  const etatScene = el('p', { class: 'reseau-mode', 'aria-live': 'polite' });
  const carte = el('section', { class: 'carte a-retenir', 'aria-labelledby': 'a-retenir-titre' });
  const defilement = el('div', { class: 'accueil-defilement' },
    el('h2', { class: 'visuellement-cache' }, 'Réseau des agents'), zone, legende, etatScene, carte);
  const panneau = el('aside', { class: 'synthese-agent', id: 'synthese-agent', hidden: true, 'aria-labelledby': 'synthese-agent-titre' });
  section.replaceChildren(defilement, panneau);

  /* ---------------------------------------------------------------- données */

  function reconstruire() {
    if (!config) return;
    reseau = calculerReseau(config, { sources: donnees, sante, entrees: donnees['data/chef.json']?.entrees ?? contexte().chef?.entrees ?? [] });
    scene?.maj(reseau);
    if (agentOuvert) remplirPanneau(agentOuvert);
  }

  /** Fichiers que l'appli n'a pas encore lus : chargés après le premier affichage. */
  function chargerManquants() {
    const manquants = fichiersReseau(config).filter((f) => donnees[f] === undefined);
    const lancer = () => manquants.forEach((f) => {
      (chargeurs[f] ?? (() => lireDonnees(f)))().then((x) => { donnees[f] = x ?? null; reconstruire(); });
    });
    if ('requestIdleCallback' in window) requestIdleCallback(lancer, { timeout: 2500 }); else setTimeout(lancer, 600);
  }

  async function demarrer() {
    config = await chargerConfig();
    if (!config) {
      zone.replaceChildren(el('p', { class: 'reseau-erreur' }, 'Réseau des agents indisponible (configuration illisible). Le globe et tous les écrans restent accessibles par le Menu.'));
      return;
    }
    reconstruire();
    await lancerScene();
    remplirCarte();
    chargerManquants();
  }

  const modeVoulu = () => (modeLeger || mouvementReduit.matches ? '2d' : '3d');

  async function lancerScene() {
    scene?.detruire();
    scene = new SceneReseau(zone, {
      reseau, mode: modeVoulu(),
      // Téléphone : la bulle au-dessus du panneau de synthèse (en bas) ; grand écran : panneau à droite
      focus: () => (matchMedia('(min-width: 960px)').matches ? 0.42 : 0.3),
      surChoix: (cle) => naviguer({ type: 'accueil', id: cle }),
      surCentre: () => naviguer({ type: 'investir' }),
    });
    const mode = await scene.demarrer();
    etatScene.textContent = mode === '2d'
      ? (modeLeger ? 'Version à plat (mode léger), sans impulsions.' : mouvementReduit.matches ? 'Version à plat : l’appareil demande de réduire les animations.' : 'Version à plat : la 3D n’est pas disponible sur cet appareil.')
      : 'Faites tourner le réseau du doigt, pincez pour zoomer, touchez une bulle pour sa synthèse.';
    scene.focaliser(agentOuvert);
    scene.definirActif(actif);
  }

  mouvementReduit.addEventListener?.('change', () => { if (scene) lancerScene(); });

  /* ---------------------------------------------------------------- carte « À retenir aujourd'hui » */

  function remplirCarte() {
    const { chef, alertes, entrepriseExiste, paysExiste } = contexte();
    const r = aRetenir(chef, alertes);
    const ouvert = lirePreference(CLE_CARTE, '1') === '1';
    const corps = el('div', { class: 'a-retenir-corps', id: 'a-retenir-corps', hidden: !ouvert });
    const bascule = el('button', {
      class: 'a-retenir-bascule', type: 'button', 'aria-expanded': String(ouvert), 'aria-controls': 'a-retenir-corps',
      onclick: () => {
        const o = bascule.getAttribute('aria-expanded') !== 'true';
        bascule.setAttribute('aria-expanded', String(o));
        corps.hidden = !o;
        memoriserPreference(CLE_CARTE, o ? '1' : '0');
      },
    }, el('h2', { id: 'a-retenir-titre' }, 'À retenir aujourd’hui'),
    r.date ? el('span', { class: 'a-retenir-date mono' }, `${r.date.slice(8, 10)}/${r.date.slice(5, 7)}`) : null,
    el('span', { class: 'chevron', 'aria-hidden': 'true' }));

    const lien = (texte, route) => (route ? el('button', { class: 'a-retenir-lien', type: 'button', onclick: () => naviguer(route) }, texte) : el('span', { class: 'a-retenir-lien a-retenir-lien--texte' }, texte));
    const rubrique = (titre, bloc, route, vide) => el('div', { class: 'a-retenir-rubrique' },
      el('h3', {}, titre, bloc.total ? el('span', { class: 'mono' }, ` · ${bloc.total}`) : null),
      bloc.lignes.length
        ? el('p', { class: 'a-retenir-lignes' }, bloc.lignes.map((x) => lien(x.nom, route(x))),
          bloc.total > bloc.lignes.length ? el('span', { class: 'a-retenir-plus' }, `et ${bloc.total - bloc.lignes.length} autre${bloc.total - bloc.lignes.length > 1 ? 's' : ''}`) : null)
        : el('p', { class: 'a-retenir-vide' }, vide));
    corps.replaceChildren(
      rubrique('Liste · entreprises', r.entreprises, (x) => (entrepriseExiste(x.ticker) ? { type: 'entreprise', id: x.ticker } : { type: 'investir' }), 'Aucune entreprise dans la liste.'),
      rubrique('Liste · matières premières', r.matieres, (x) => ({ type: 'matieres', id: x.cle }), 'Aucune matière première dans la liste.'),
      rubrique('Paris pays', r.paris, (x) => (paysExiste(x.code) ? { type: 'pays', id: x.code } : { type: 'investir' }), 'Aucun pari pays dans la liste.'),
      rubrique('Sorties du mois', r.aRevendre, (x) => (x.code && paysExiste(x.code) ? { type: 'pays', id: x.code } : { type: 'investir', id: 'mouvements' }), 'Aucune sortie ce mois-ci.'),
      el('div', { class: 'a-retenir-rubrique a-retenir-alerte' },
        el('h3', {}, 'Alerte du jour'),
        r.alerte ? lien(r.alerte.titre, r.alerte.route) : el('p', { class: 'a-retenir-vide' }, 'Aucune alerte aujourd’hui.')),
      el('button', { class: 'bouton bouton--accent a-retenir-detail', type: 'button', onclick: () => naviguer({ type: 'investir' }) }, 'Voir le détail'),
    );
    carte.replaceChildren(bascule, chef ? corps : el('p', { class: 'a-retenir-vide' }, 'Sélections du chef d’orchestre indisponibles.'));
  }

  /* ---------------------------------------------------------------- panneau de synthèse d'un agent */

  function detailsAgent(cle) {
    const chef = donnees['data/chef.json'] ?? contexte().chef;
    const r = aRetenir(chef, contexte().alertes, { max: 4 });
    const noms = (bloc) => (bloc.lignes.length ? `${bloc.lignes.map((x) => x.nom).join(', ')}${bloc.total > bloc.lignes.length ? '…' : ''}` : null);
    switch (cle) {
      case 'entreprises': return noms(r.entreprises) && `Meilleures retenues : ${noms(r.entreprises)}`;
      case 'matieres': return noms(r.matieres) && `Retenues : ${noms(r.matieres)}`;
      case 'pays': return noms(r.paris) && `Paris pays : ${noms(r.paris)}${r.aRevendre.total ? ` ; sorties du mois : ${noms(r.aRevendre)}` : ''}`;
      case 'risque': {
        const m = donnees['data/risque.json']?.mondial;
        return m ? `Stress financier ${Math.round(m.score)}/100, palier « ${m.palier} » depuis le ${String(m.depuis ?? '').split('-').reverse().join('/')}.` : null;
      }
      case 'macro': return donnees['data/macro.json']?.recession?.synthese ? `Signaux de récession : ${donnees['data/macro.json'].recession.synthese}` : null;
      case 'marches': {
        const m = donnees['data/marches.json'];
        return Array.isArray(m) && m.length ? m.slice(0, 8).map((x) => `${x.nom} ${x.variation > 0 ? '+' : x.variation < 0 ? '−' : ''}${Math.abs(x.variation ?? 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} %`).join(' · ') : null;
      }
      case 'trader': {
        const p = donnees['data/portefeuille.json'];
        return p?.valeur_actuelle != null ? `Valeur : ${Math.round(p.valeur_actuelle).toLocaleString('fr-FR')} € (départ ${Number(p.capital_initial ?? 100000).toLocaleString('fr-FR')} € le ${String(p.date_debut ?? '').split('-').reverse().join('/')}). Fictif, aucun ordre réel.` : null;
      }
      case 'backtest': {
        const v = donnees['data/backtest/resultats.json']?.verdicts;
        return v ? Object.entries(v).map(([k, n]) => `${k} : ${n}`).join(' · ') : null;
      }
      default: return null;
    }
  }

  function remplirPanneau(cle) {
    const n = reseau?.agents.find((a) => a.cle === cle);
    if (!n) return;
    const entrees = (config.agents.find((a) => a.cle === cle)?.entrees ?? [])
      .map((c) => (donnees['data/chef.json']?.entrees ?? []).find((e) => e.cle === c)).filter(Boolean);
    const coef = entrees.length ? Math.min(...entrees.map((e) => e.coef ?? 1)) : null;
    const detail = detailsAgent(cle);
    panneau.replaceChildren(...[
      el('div', { class: 'synthese-agent-tete' },
        el('div', {},
          el('p', { class: 'synthese-agent-sur' }, 'Synthèse de l’agent'),
          el('h2', { id: 'synthese-agent-titre', tabindex: '-1' }, n.nom)),
        el('button', { class: 'bouton bouton--icone', type: 'button', title: 'Fermer la synthèse', onclick: fermer },
          el('span', { 'aria-hidden': 'true' }, '✕'), el('span', { class: 'visuellement-cache' }, 'Fermer la synthèse'))),
      el('p', { class: 'synthese-agent-info mono' }, n.info),
      el('p', { class: `synthese-agent-etat synthese-agent-etat--${n.etat}` },
        el('strong', {}, `État : ${ETATS_RESEAU[n.etat]?.libelle ?? n.etat}`),
        n.derniere ? ` · dernière exécution le ${n.derniere}` : null),
      n.raisons.length ? el('ul', { class: 'synthese-agent-raisons' }, n.raisons.slice(0, 4).map((x) => el('li', {}, x))) : null,
      el('p', { class: 'synthese-agent-role' },
        n.poids === 'decision' ? 'Pèse dans la décision du chef d’orchestre (trait épais).' : 'Contexte : éclaire la décision sans la déterminer (trait pointillé).',
        n.sens === 'depuis_centre' ? ' Il applique les décisions du chef d’orchestre.' : '',
        coef != null && coef < 1 ? ` Ses données pèsent ${Math.round(coef * 100)} % de leur poids normal aujourd’hui.` : ''),
      el('p', { class: 'synthese-agent-texte' }, n.description),
      detail ? el('p', { class: 'synthese-agent-detail' }, detail) : null,
      n.route ? el('button', { class: 'bouton bouton--accent synthese-agent-action', type: 'button', onclick: () => naviguer(n.route) }, n.action ?? 'Ouvrir') : null,
    ].filter(Boolean));
  }

  function ouvrirPanneau(cle) {
    const premiere = agentOuvert !== cle;
    agentOuvert = cle;
    remplirPanneau(cle);
    panneau.hidden = false;
    section.classList.add('a-un-agent');
    defilement.scrollTo?.({ top: 0, behavior: 'smooth' });
    scene?.focaliser(cle);
    if (premiere) requestAnimationFrame(() => panneau.querySelector('#synthese-agent-titre')?.focus({ preventScroll: true }));
  }

  function fermerPanneau() {
    if (!agentOuvert) return;
    const cle = agentOuvert;
    agentOuvert = null;
    panneau.hidden = true;
    section.classList.remove('a-un-agent');
    scene?.focaliser(null);
    // Le focus revient sur la bulle de l'agent
    if (panneau.contains(document.activeElement) || document.activeElement === document.body) section.querySelector(`.reseau-noeud[data-cle="${cle}"]`)?.focus({ preventScroll: true });
  }

  /* ---------------------------------------------------------------- interface publique */

  return {
    /** Affiche l'accueil, avec la synthèse d'un agent si `cle` est donné. */
    afficher(cle) {
      demarrage ??= demarrer();
      demarrage.then(() => { if (cle) ouvrirPanneau(cle); else fermerPanneau(); });
    },
    agentExiste: (cle) => !config || Boolean(config.agents.some((a) => a.cle === cle)),
    definirActif(a) {
      actif = a;
      section.hidden = !a;
      scene?.definirActif(a);
    },
    definirLeger(l) {
      if (l === modeLeger) return;
      modeLeger = l;
      if (scene) lancerScene();
    },
    /** Journaux des agents (écran « Santé des agents ») : états recalculés. */
    majSante(agents) {
      sante = Object.fromEntries((agents ?? []).map((a) => [a.agent, { statut: statutAgent(a), journal: a.sante }]));
      reconstruire();
    },
    /** Nouvelles données lues par l'appli (ex. portefeuille démo relu toutes les 5 minutes). */
    majSource(fichier, valeur) {
      donnees[fichier] = valeur;
      reconstruire();
      if (fichier === 'data/chef.json') remplirCarte();
    },
  };
}

/** Petit échantillon de trait pour la légende (épaisseur et pointillés, couleur de l'état). */
function trait(poids, etat = 'ok') {
  const NS = 'http://www.w3.org/2000/svg';
  const s = document.createElementNS(NS, 'svg');
  s.setAttribute('viewBox', '0 0 28 8');
  s.setAttribute('class', `reseau-trait reseau-trait--${etat}`);
  s.setAttribute('aria-hidden', 'true');
  const l = document.createElementNS(NS, 'line');
  Object.entries({ x1: 2, y1: 4, x2: 26, y2: 4, 'stroke-width': poids === 'decision' ? 3 : 1.6, 'stroke-linecap': 'round', 'stroke-dasharray': poids === 'decision' ? (etat === 'panne' ? '7 3' : 'none') : '3 4' })
    .forEach(([k, v]) => l.setAttribute(k, v));
  s.append(l);
  return s;
}
