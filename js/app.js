/* ==========================================================================
   Point d'entrée de l'application
   --------------------------------------------------------------------------
   - charge les données (data/*.json)
   - démarre le globe, l'horloge, le bandeau des marchés et les alertes
   - gère la navigation : Globe › Pays › Secteur › Entreprise, Portefeuille et Classement
     L'adresse de la page reflète l'écran affiché (#/pays/FR…), ce qui fait
     fonctionner le bouton « retour » du téléphone.
   ========================================================================== */

import { chargerDonnees } from './donnees.js';
import { el, nombre, variation, lireMetrique, METRIQUES_PAYS } from './outils.js';
import {
  demarrerHorloge, remplirBandeau, initialiserAlertes, initialiserFiltres, lireModeLeger, memoriserModeLeger, lirePreference, memoriserPreference,
} from './interface.js';
import { initialiserComparateur, boutonComparer, majBarre, ecranComparaison } from './comparateur.js';
import { evaluerRegles, ecranMesAlertes } from './mes-alertes.js';
import { initialiserRecherche } from './recherche.js';
import { fichePays, ficheSecteur } from './panneau-pays.js';
import { ficheEntreprise, chargerFiche } from './panneau-entreprise.js';
import { ecranPortefeuille } from './portefeuille.js';
import { ecranClassement } from './classement.js';
import { chargerSante, ecranSante, problemeDetecte } from './sante.js';
import { chargerMacro, ecranMacro } from './macro.js';
import { chargerGeopolitique, ecranGeopolitique, lireRisque, METRIQUE_RISQUE } from './geopolitique.js';
import { chargerRisque, ecranRisque, lireRisquePays, majPastilleRisque, METRIQUE_RISQUE_PAYS } from './risque.js';
import { chargerPepites, ecranPepites } from './pepites.js';
import { METRIQUE_FLUX, lireFlux, initialiserPeriodeFlux, periodeFlux } from './flux-investissement.js';
import { choisirPulsations, bilanPulsations, libellePeriode } from './pulsations.js';
import { chargerAnalyses, chargerEnCours, chargerAnalyse, chargerRecommandations, ecranAnalyses, ecranFiabilite } from './analyses.js';

const $ = (sel) => document.querySelector(sel);
const dom = {
  panneau: $('#panneau'),
  panneauContenu: $('#panneau-contenu'),
  poignee: $('#panneau-poignee'),
  ecranPortefeuille: $('#ecran-portefeuille'),
  portefeuilleContenu: $('#portefeuille-contenu'),
  ecranClassement: $('#ecran-classement'),
  classementContenu: $('#classement-contenu'),
  btnLegende: $('#btn-legende'),
  filtres: $('#filtres'),
  barreComparaison: $('#barre-comparaison'),
  legende: $('#legende'),
  entete: $('.entete'),
  alertes: $('#alertes'),
  message: $('#message'),
  btnLeger: $('#btn-leger'),
};

let d = null;      // données chargées
let globe = null;  // instance du globe 3D (null si WebGL indisponible)
let alertes = null;
let recherche = null;
let routeActuelle = { type: 'globe' };

/*
 * Hauteurs du panneau sur téléphone (fractions de la hauteur d'écran).
 * La poignée permet de passer de l'une à l'autre.
 */
const ETATS_PANNEAU = ['reduit', 'normal', 'plein'];
const HAUTEURS_PANNEAU = { reduit: 0.34, normal: 0.58, plein: 1 };
let etatPanneau = 'normal';

function hauteurPanneau(etat = etatPanneau) {
  return etat === 'plein' ? innerHeight - 6 : Math.round(innerHeight * HAUTEURS_PANNEAU[etat]);
}
function estLarge() {
  return matchMedia('(min-width: 960px)').matches;
}

/* ========================== Santé des agents ========================== */

let agentsSante = [];
let macro = null; // données de l'agent macro (data/macro.json), ou null
let geopolitique = null; // données de l'agent géopolitique (data/geopolitique.json), ou null
let risque = null; // données de l'agent risque (data/risque.json), ou null
let pepites = null; // pépites candidates de l'agent entreprises (data/pepites.json), ou null
let analyses = { liste: [] }; // analyses à la demande (data/analyses/index.json)
let enCours; // demandes d'analyse en cours (issues ouvertes) : undefined = pas encore lues, null = GitHub injoignable
let recommandations; // historique des recommandations : undefined = pas encore lu
const fichesAnalyses = new Map(); // ticker → fiche d'analyse chargée (null si introuvable)

/** Recharge les journaux des agents, met à jour la pastille de l'en-tête et l'écran s'il est ouvert. */
async function majSante() {
  agentsSante = await chargerSante();
  const probleme = problemeDetecte(agentsSante);
  const bouton = $('#btn-sante');
  bouton.classList.toggle('a-un-probleme', probleme);
  bouton.title = probleme ? 'Santé des agents : problème détecté' : 'Santé des agents';
  $('#btn-sante .visuellement-cache').textContent = bouton.title;
  if (routeActuelle?.type === 'sante') $('#sante-contenu').replaceChildren(...ecranSante(agentsSante));
}

/**
 * Mention « Données fictives » : affichée seulement là où l'écran montre des données fictives
 * (portefeuille démo, alertes), et plus là où les agents produisent des données réelles.
 */
function majBadgesFictifs(route) {
  const f = d.fictifPar ?? {};
  const fictif = {
    globe: f.alertes !== false,
    pays: f.pays !== false || f.secteurs !== false,
    secteur: f.secteurs !== false || f.entreprises !== false,
    entreprise: f.entreprises !== false,
    portefeuille: f.portefeuille !== false,
    classement: f.pays !== false || f.entreprises !== false,
    comparaison: f.pays !== false || f.entreprises !== false,
  }[route.type] ?? false;
  document.querySelectorAll('.badge-fictif').forEach((b) => { b.hidden = !fictif; });
}

/* ============================== Démarrage ============================== */

async function demarrer() {
  demarrerHorloge($('#horloge'));
  enregistrerServiceWorker();

  try {
    // data/macro.json est facultatif : son absence n'empêche pas l'appli de démarrer
    [d, macro, pepites, analyses, geopolitique, risque] = await Promise.all([chargerDonnees(), chargerMacro(), chargerPepites(), chargerAnalyses(), chargerGeopolitique(), chargerRisque()]);
    d.macro = macro;
    d.geopolitique = geopolitique;
    d.risque = risque;
    d.analyses = analyses.liste;
  } catch (erreur) {
    console.error(erreur);
    afficherMessage('Impossible de charger les données. Vérifiez votre connexion puis rechargez la page.');
    return;
  }

  // La mention « Données fictives » disparaît quand plus aucun fichier n'est fictif
  majBadgesFictifs({ type: 'globe' });
  remplirBandeau($('#bandeau-piste'), d.marches);
  alertes = initialiserAlertes(
    { bouton: $('#alertes-bascule'), liste: $('#alertes-liste'), compte: $('#alertes-compte'), apercu: $('#alertes-apercu') },
    d.paysParCode, naviguer,
  );
  majAlertes(); // alertes des agents + mes alertes (règles vérifiées à chaque chargement)
  initialiserComparateur(d, { barre: dom.barreComparaison, ouvrir: () => naviguer({ type: 'comparaison' }) });

  // Filtres : ce que représentent les couleurs du globe (choix mémorisé)
  let metriqueInitiale = 'note';
  // Filtres « Flux d'investissement » (ETF pays), « Risque » (agent risque) et « Risque géopolitique » :
  // seulement pour le globe (pas dans le comparateur ni les alertes)
  const avecFlux = d.pays.some((p) => p.detail?.flux_etrangers?.periodes);
  const metriquesGlobe = [...METRIQUES_PAYS, ...(avecFlux ? [METRIQUE_FLUX] : []), ...(risque ? [METRIQUE_RISQUE_PAYS] : []), ...(geopolitique ? [METRIQUE_RISQUE] : [])];
  const estRisque = (cle) => cle === METRIQUE_RISQUE.cle || cle === METRIQUE_RISQUE_PAYS.cle;
  const estFlux = (cle) => cle === METRIQUE_FLUX.cle;
  // Sélecteur 1 semaine / 1 mois / 3 mois, visible seulement avec le filtre « Flux d'investissement » ;
  // il règle aussi la période des pulsations du globe
  initialiserPeriodeFlux($('#flux-periode'), () => {
    globe?.definirMetrique(objetMetrique(METRIQUE_FLUX.cle));
    globe?.definirPulsations(choisirPulsations(d.pays, periodeFlux()));
    majLegendePulsations();
  });
  initialiserBoutonPulsations(avecFlux);
  initialiserFiltres({ puces: $('#filtres-puces') }, metriquesGlobe, {
    surMetrique: (cle, initial) => {
      $('#legende-metrique').textContent = metriquesGlobe.find((m) => m.cle === cle).libelle;
      $('#legende-notes').hidden = estRisque(cle) || estFlux(cle);
      $('#legende-risque').hidden = !estRisque(cle);
      $('#legende-flux').hidden = !estFlux(cle);
      $('#flux-periode').hidden = !estFlux(cle);
      if (initial) metriqueInitiale = cle; else globe?.definirMetrique(objetMetrique(cle));
    },
  });

  // Mode léger
  let leger = lireModeLeger();
  appliquerModeLeger(leger);
  dom.btnLeger.addEventListener('click', () => {
    leger = !leger;
    memoriserModeLeger(leger);
    appliquerModeLeger(leger);
  });

  $('#btn-portefeuille').addEventListener('click', () => naviguer({ type: 'portefeuille' }));
  $('#btn-classement').addEventListener('click', () => naviguer({ type: 'classement' }));
  $('#btn-sante').addEventListener('click', () => naviguer({ type: 'sante' }));
  $('#btn-macro').addEventListener('click', () => naviguer({ type: 'macro' }));
  $('#btn-geopolitique').addEventListener('click', () => naviguer({ type: 'geopolitique' }));
  // Pastille permanente du palier de risque mondial : ouvre l'écran « Risque »
  majPastilleRisque($('#btn-risque'), risque);
  $('#btn-risque').addEventListener('click', () => naviguer({ type: 'risque' }));
  $('#btn-pepites').addEventListener('click', () => naviguer({ type: 'pepites' }));
  $('#btn-analyses').addEventListener('click', () => naviguer({ type: 'analyses' }));
  // Santé des agents : chargée à part (un journal manquant ne bloque pas l'appli),
  // puis recalculée chaque minute, car le statut « en panne » dépend de l'heure
  majSante();
  setInterval(majSante, 60_000);
  // Recherche : toucher un résultat ouvre la fiche (le globe se centre sur le pays)
  recherche = initialiserRecherche(d, {
    bouton: $('#btn-recherche'), panneau: $('#recherche'), champ: $('#recherche-champ'),
    liste: $('#recherche-resultats'), fermer: $('#recherche-fermer'),
  }, naviguer);
  brancherLegende();
  document.querySelectorAll('.js-retour').forEach((b) => b.addEventListener('click', retour));
  document.querySelectorAll('.js-fermer').forEach((b) => b.addEventListener('click', () => allerVers({ type: 'globe' })));
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (recherche?.ouverte()) recherche.fermer();
    else if (routeActuelle.type !== 'globe') retour();
  });
  brancherGlissementPanneau();

  // Le globe est chargé à part : si Three.js ou WebGL est indisponible,
  // le reste de l'application continue de fonctionner.
  try {
    const { Globe } = await import('./globe.js');
    globe = new Globe($('#globe'), $('#etiquettes'), {
      pays: d.pays,
      frontieres: d.frontieres,
      leger,
      metrique: objetMetrique(metriqueInitiale),
      pulsations: avecFlux ? choisirPulsations(d.pays, periodeFlux()) : [],
      afficherPulsations: pulsationsVisibles,
      formaterPulsation: textePulsation,
      surSelection: (code) => naviguer({ type: 'pays', id: code }),
    });
  } catch (erreur) {
    console.error(erreur);
    afficherSecours();
  }
  // Accès au globe pour les tests automatiques uniquement (adresse avec ?test)
  if (new URLSearchParams(location.search).has('test')) window.__globe = globe;

  addEventListener('resize', () => { appliquerEtatPanneau(); majCadrage(); });
  addEventListener('hashchange', surChangementAdresse);
  pile = [location.hash || '#/'];
  afficher(lireAdresse());
}

/** Métrique au format attendu par le globe : note et texte de chaque pays. */
function objetMetrique(cle) {
  if (cle === METRIQUE_RISQUE.cle) return { cle, lire: (p) => lireRisque(geopolitique, p.code) };
  if (cle === METRIQUE_RISQUE_PAYS.cle) return { cle, lire: (p) => lireRisquePays(risque, p.code) };
  if (cle === METRIQUE_FLUX.cle) return { cle, lire: (p) => lireFlux(p) };
  return { cle, lire: (p) => lireMetrique(p, cle) };
}

/** Bandeau des alertes : « Qualité des données » et mes alertes en tête, puis celles des agents. */
function majAlertes() {
  alertes.afficher(d.alertes, evaluerRegles(d), alertesQualite());
}

/** Pays dont plus d'un tiers des sources ont échoué lors de la dernière exécution de l'agent pays. */
function alertesQualite() {
  return d.pays.filter((p) => p.qualite?.alerte).map((p) => ({
    qualite: true, agent: 'pays', pays: p.code, niveau: 'defavorable', heure: '⚠',
    titre: `${p.nom} : données incomplètes`,
    texte: `${p.qualite.sources_en_echec} source${p.qualite.sources_en_echec > 1 ? 's' : ''} sur ${p.qualite.sources_consultees} en échec ou rejetée${p.qualite.sources_en_echec > 1 ? 's' : ''} lors de la dernière mise à jour.`,
  }));
}

function appliquerModeLeger(actif) {
  document.body.classList.toggle('mode-leger', actif);
  dom.btnLeger.setAttribute('aria-pressed', String(actif));
  dom.btnLeger.title = actif ? 'Mode léger activé (cliquer pour le désactiver)' : 'Activer le mode léger (économie de batterie)';
  globe?.definirLeger(actif);
  majLegendePulsations();
}

/* ================= Pulsations du globe : flux d'investissement des ETF pays ================= */

const CLE_PULSATIONS = 'salle-controle:pulsations';
let pulsationsVisibles = lirePreference(CLE_PULSATIONS, '1') === '1';
const mouvementReduit = matchMedia('(prefers-reduced-motion: reduce)');

/** Bouton « Flux ETF » (à côté des filtres) : masque ou affiche les pulsations ; choix mémorisé. */
function initialiserBoutonPulsations(avecFlux) {
  const bouton = $('#btn-pulsations');
  bouton.hidden = !avecFlux;
  $('#legende-pulsations').hidden = !avecFlux;
  const maj = () => {
    bouton.setAttribute('aria-pressed', String(pulsationsVisibles));
    bouton.title = pulsationsVisibles ? 'Masquer les pulsations des flux d’investissement' : 'Afficher les pulsations des flux d’investissement';
  };
  bouton.addEventListener('click', () => {
    pulsationsVisibles = !pulsationsVisibles;
    memoriserPreference(CLE_PULSATIONS, pulsationsVisibles ? '1' : '0');
    maj();
    globe?.definirAffichagePulsations(pulsationsVisibles);
    majLegendePulsations();
  });
  mouvementReduit.addEventListener?.('change', majLegendePulsations);
  maj();
  majLegendePulsations();
}

/** Ligne d'état de la légende : nombre de pays qui pulsent, historique en cours de constitution, désactivation. */
function majLegendePulsations() {
  const noeud = $('#legende-pulsations-etat');
  if (!noeud || !d) return;
  const periode = periodeFlux();
  const n = choisirPulsations(d.pays, periode).length;
  const { constitution } = bilanPulsations(d.pays, periode);
  const morceaux = [];
  if (document.body.classList.contains('mode-leger')) morceaux.push('Pulsations désactivées en mode ⚡.');
  else if (mouvementReduit.matches) morceaux.push('Pulsations désactivées : l’appareil demande de réduire les animations.');
  else if (!pulsationsVisibles) morceaux.push('Pulsations masquées (bouton « Flux ETF »).');
  else morceaux.push(n ? `${n} pays pulse${n > 1 ? 'nt' : ''} (${libellePeriode(periode)}).` : 'Aucun flux assez marqué pour pulser.');
  if (constitution) morceaux.push(`${constitution} pays en cours de constitution (historique insuffisant).`);
  noeud.textContent = morceaux.join(' ');
}

/** Bulle d'un pays qui pulse : montant, % de l'encours, période et date de la donnée. */
function textePulsation(x) {
  const date = x.date ? new Date(`${x.date}T12:00:00Z`).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }) : null;
  const m = x.flux_musd;
  const montant = `${m > 0 ? '+' : m < 0 ? '−' : ''}${nombre(Math.abs(m), Math.abs(m) >= 100 ? 0 : 1)} M$`;
  return [
    `${x.nom} · ETF ${x.symbole}`,
    `${x.sens === 'entrees' ? 'Entrées' : 'Sorties'} nettes : ${montant} · ${variation(x.pct, 2)} de l’encours`,
    `Sur ${libellePeriode(x.periode)}${x.repli ? ` (${libellePeriode(x.demandee)} en cours de constitution)` : ''} · donnée du ${date ?? 'n.d.'}`,
    'ETF cotés aux États-Unis uniquement',
  ];
}

/* ============================== Navigation ============================== */

/** Transforme une route en adresse (#/pays/FR) et inversement. */
function versAdresse(route) {
  // Lien direct vers une analyse à la demande : #analyse-TICKER (adresse donnée dans la réponse de l'issue)
  if (route.type === 'analyse') return `#analyse-${encodeURIComponent(route.id)}`;
  return route.type === 'globe' ? '#/' : route.id ? `#/${route.type}/${encodeURIComponent(route.id)}` : `#/${route.type}`;
}
function lireAdresse() {
  const analyse = location.hash.match(/^#analyse-(.+)$/);
  if (analyse) return { type: 'analyse', id: decodeURIComponent(analyse[1]) };
  const [type, id] = location.hash.replace(/^#\/?/, '').split('/');
  if (!type) return { type: 'globe' };
  return { type, id: id ? decodeURIComponent(id) : undefined };
}

/*
 * On garde une copie de l'historique de navigation interne (« pile »)
 * pour que le bouton retour et le fil d'Ariane remontent réellement
 * dans l'historique du navigateur au lieu d'empiler de nouvelles pages.
 */
let pile = [];
let mouvementAttendu = null; // 'avant' quand on navigue nous-mêmes, sinon on suppose un retour

function naviguer(route) {
  const adresse = versAdresse(route);
  if (adresse === location.hash) return afficher(route);
  mouvementAttendu = 'avant';
  location.hash = adresse;
}

function surChangementAdresse() {
  const adresse = location.hash || '#/';
  const index = pile.lastIndexOf(adresse);
  if (mouvementAttendu === 'avant' || index === -1) pile.push(adresse);
  else pile.length = index + 1; // retour (bouton du téléphone ou de l'appli)
  mouvementAttendu = null;
  afficher(lireAdresse());
}

/** Va vers une route « ancêtre » en remontant l'historique si possible. */
function allerVers(route) {
  const adresse = versAdresse(route);
  const index = pile.lastIndexOf(adresse);
  if (index !== -1 && index < pile.length - 1) {
    history.go(index - (pile.length - 1));
  } else if (pile.length <= 1) {
    // Arrivée directe sur une page profonde : on remplace l'entrée actuelle
    pile = [adresse];
    history.replaceState(null, '', adresse);
    afficher(route);
  } else {
    naviguer(route);
  }
}

/** Bouton retour : niveau précédent. */
function retour() {
  if (pile.length > 1) history.back();
  else {
    const chemin = filAriane(routeActuelle);
    allerVers(chemin.length > 1 ? chemin[chemin.length - 2].route : { type: 'globe' });
  }
}

/**
 * Fil d'Ariane d'une route : liste des niveaux depuis le globe.
 * Chaque entrée : { libelle, route }.
 */
function filAriane(route) {
  const racine = { libelle: 'Globe', route: { type: 'globe' } };
  const niveauPays = (code) => ({ libelle: d.paysParCode.get(code)?.nom ?? code, route: { type: 'pays', id: code } });
  const niveauSecteur = (s) => ({ libelle: s.nom, route: { type: 'secteur', id: s.id } });
  switch (route.type) {
    case 'pays': return [racine, niveauPays(route.id)];
    case 'secteur': {
      const s = d.secteurParId.get(route.id);
      return [racine, niveauPays(s.pays), niveauSecteur(s)];
    }
    case 'entreprise': {
      const e = d.entrepriseParTicker.get(route.id);
      const s = d.secteurParId.get(e.secteur);
      return [racine, niveauPays(e.pays), niveauSecteur(s), { libelle: e.nom, route }];
    }
    case 'portefeuille': return [racine, { libelle: 'Portefeuille démo', route }];
    case 'classement': return [racine, { libelle: 'Classement', route }];
    case 'comparaison': return [racine, { libelle: 'Comparaison', route }];
    case 'mes-alertes': return [racine, { libelle: 'Mes alertes', route }];
    case 'sante': return [racine, { libelle: 'Santé des agents', route }];
    case 'macro': return [racine, { libelle: 'Vue macro', route }];
    case 'geopolitique': return [racine, { libelle: 'Géopolitique', route }];
    case 'risque': return [racine, { libelle: 'Risque', route }];
    case 'pepites': return [racine, { libelle: 'Pépites', route }];
    case 'analyses': return [racine, { libelle: 'Mes analyses', route }];
    case 'fiabilite': return [racine, { libelle: 'Mes analyses', route: { type: 'analyses' } }, { libelle: 'Fiabilité', route }];
    case 'analyse': {
      const nom = fichesAnalyses.get(route.id)?.nom ?? analyses.liste.find((a) => a.ticker === route.id)?.nom ?? route.id;
      return [racine, { libelle: 'Mes analyses', route: { type: 'analyses' } }, { libelle: nom, route }];
    }
    default: return [racine];
  }
}

function majAriane(route) {
  const chemin = filAriane(route);
  document.querySelectorAll('.js-ariane').forEach((ol) => {
    ol.replaceChildren(...chemin.map((niveau, i) => el('li', {},
      i < chemin.length - 1
        ? el('button', { type: 'button', onclick: () => allerVers(niveau.route) }, niveau.libelle)
        : el('span', { 'aria-current': 'page' }, niveau.libelle),
    )));
  });
}

/** Vérifie qu'une route désigne bien un élément existant. */
function routeValide(route) {
  switch (route.type) {
    case 'globe': case 'portefeuille': case 'classement': case 'comparaison': case 'mes-alertes': case 'sante': case 'macro': case 'geopolitique': case 'risque': case 'pepites':
    case 'analyses': case 'fiabilite': return true;
    case 'analyse': return Boolean(route.id);
    case 'pays': return d.paysParCode.has(route.id);
    case 'secteur': return d.secteurParId.has(route.id);
    case 'entreprise': return d.entrepriseParTicker.has(route.id);
    default: return false;
  }
}

/* ============================== Affichage ============================== */

function afficher(route) {
  if (!routeValide(route)) {
    history.replaceState(null, '', '#/');
    pile[pile.length - 1] = '#/';
    route = { type: 'globe' };
  }
  routeActuelle = route;
  const navigateurPanneau = {
    ouvrirPays: (code) => naviguer({ type: 'pays', id: code }),
    ouvrirSecteur: (id) => naviguer({ type: 'secteur', id }),
    ouvrirEntreprise: (ticker) => naviguer({ type: 'entreprise', id: ticker }),
    ouvrirFiabilite: () => naviguer({ type: 'fiabilite' }),
    ouvrir: naviguer,
    boutonComparer,
  };

  // Contenu du panneau montant
  let contenu = null, codePays = null, titre = 'Salle de contrôle';
  if (route.type === 'pays') {
    const p = d.paysParCode.get(route.id);
    contenu = fichePays(d, p, navigateurPanneau); codePays = p.code; titre = `${p.nom} — Salle de contrôle`;
  } else if (route.type === 'secteur') {
    const s = d.secteurParId.get(route.id);
    contenu = ficheSecteur(d, s, navigateurPanneau); codePays = s.pays; titre = `${s.nom} — Salle de contrôle`;
  } else if (route.type === 'entreprise') {
    const e = d.entrepriseParTicker.get(route.id);
    contenu = ficheEntreprise(d, e, navigateurPanneau); codePays = e.pays; titre = `${e.nom} — Salle de contrôle`;
    // Le détail (F-score, montants, revue critique, sources…) est dans une fiche séparée, chargée à la demande
    if (e.fiche && !e.detailCharge) {
      chargerFiche(e).then((ok) => {
        if (ok && routeActuelle.type === 'entreprise' && routeActuelle.id === e.ticker) {
          const defilement = dom.panneauContenu.scrollTop;
          dom.panneauContenu.replaceChildren(...ficheEntreprise(d, e, navigateurPanneau).filter(Boolean));
          dom.panneauContenu.scrollTop = defilement;
        }
      });
    }
  } else if (route.type === 'analyse') {
    // Analyse à la demande : fiche chargée à la demande (data/analyses/<ticker>.json)
    const rendre = (e) => (e
      ? ficheEntreprise(d, e, navigateurPanneau)
      : [el('h2', { class: 'fiche-titre' }, route.id), el('p', { class: 'fiche-verdict' }, 'Analyse introuvable : elle est peut-être encore en cours (résultat dans 2 à 5 minutes après la demande).')]);
    const connue = fichesAnalyses.get(route.id);
    contenu = connue !== undefined ? rendre(connue) : [el('h2', { class: 'fiche-titre' }, route.id), el('p', { class: 'fiche-verdict' }, 'Chargement de l’analyse…')];
    codePays = connue?.pays ?? null;
    titre = `${connue?.nom ?? route.id} — Salle de contrôle`;
    if (connue === undefined) {
      chargerAnalyse(route.id).then((e) => {
        fichesAnalyses.set(route.id, e);
        if (routeActuelle.type === 'analyse' && routeActuelle.id === route.id) afficher(route);
      });
    }
  }

  const panneauOuvert = Boolean(contenu);
  // À l'ouverture, le panneau part de sa hauteur normale ; ensuite il garde la hauteur choisie
  if (panneauOuvert && !dom.panneau.classList.contains('est-ouvert')) etatPanneau = 'normal';
  if (contenu) {
    dom.panneauContenu.replaceChildren(...contenu.filter(Boolean));
    dom.panneauContenu.scrollTop = 0;
  }
  dom.panneau.classList.toggle('est-ouvert', panneauOuvert);
  dom.panneau.setAttribute('aria-hidden', String(!panneauOuvert));
  dom.panneau.inert = !panneauOuvert;
  document.body.classList.toggle('panneau-ouvert', panneauOuvert);
  if (panneauOuvert) { alertes?.replier(); fermerLegende(); }
  appliquerEtatPanneau();

  // Écrans plein écran (portefeuille, classement, comparaison, mes alertes)
  const ECRANS = {
    portefeuille: { section: '#ecran-portefeuille', contenu: '#portefeuille-contenu', titre: 'Portefeuille démo', rendu: () => ecranPortefeuille(d, navigateurPanneau) },
    classement: { section: '#ecran-classement', contenu: '#classement-contenu', titre: 'Classement', rendu: () => ecranClassement(d, navigateurPanneau) },
    comparaison: { section: '#ecran-comparaison', contenu: '#comparaison-contenu', titre: 'Comparaison', rendu: () => ecranComparaison(d, navigateurPanneau) },
    'mes-alertes': { section: '#ecran-mes-alertes', contenu: '#mes-alertes-contenu', titre: 'Mes alertes', rendu: () => ecranMesAlertes(d, { surChangement: majAlertes, ouvrir: naviguer }) },
    sante: { section: '#ecran-sante', contenu: '#sante-contenu', titre: 'Santé des agents', rendu: () => ecranSante(agentsSante) },
    macro: { section: '#ecran-macro', contenu: '#macro-contenu', titre: 'Vue macro', rendu: () => ecranMacro(macro) },
    geopolitique: { section: '#ecran-geopolitique', contenu: '#geopolitique-contenu', titre: 'Géopolitique', rendu: () => ecranGeopolitique(geopolitique) },
    risque: { section: '#ecran-risque', contenu: '#risque-contenu', titre: 'Risque', rendu: () => ecranRisque(risque, navigateurPanneau) },
    pepites: { section: '#ecran-pepites', contenu: '#pepites-contenu', titre: 'Pépites', rendu: () => ecranPepites(pepites, d, navigateurPanneau) },
    analyses: { section: '#ecran-analyses', contenu: '#analyses-contenu', titre: 'Mes analyses', rendu: () => ecranAnalyses({ analyses, enCours }, navigateurPanneau) },
    fiabilite: { section: '#ecran-fiabilite', contenu: '#fiabilite-contenu', titre: 'Fiabilité des recommandations', rendu: () => ecranFiabilite(recommandations, navigateurPanneau) },
  };
  // Données lues à l'ouverture de l'écran, puis nouveau rendu s'il est toujours affiché
  if (route.type === 'analyses') {
    Promise.all([chargerAnalyses(), chargerEnCours()]).then(([a, c]) => {
      analyses = a; enCours = c; d.analyses = a.liste;
      if (routeActuelle.type === 'analyses') $('#analyses-contenu').replaceChildren(...ecranAnalyses({ analyses, enCours }, navigateurPanneau).filter(Boolean));
    });
  }
  if (route.type === 'fiabilite' && recommandations === undefined) {
    chargerRecommandations().then((h) => {
      recommandations = h;
      if (routeActuelle.type === 'fiabilite') $('#fiabilite-contenu').replaceChildren(...ecranFiabilite(recommandations, navigateurPanneau).filter(Boolean));
    });
  }
  for (const [type, ecran] of Object.entries(ECRANS)) {
    const visible = route.type === type;
    if (visible) {
      $(ecran.contenu).replaceChildren(...ecran.rendu().filter(Boolean));
      $(ecran.contenu).scrollTop = 0;
      titre = `${ecran.titre} — Salle de contrôle`;
    }
    $(ecran.section).hidden = !visible;
  }
  majBarre(route.type === 'comparaison');
  // Les pays sont produits par l'agent pays (données réelles) : pas de badge « Données fictives » sur leur fiche
  majBadgesFictifs(route);
  document.body.classList.toggle('ecran-ouvert', route.type in ECRANS);

  // Globe : pivot vers le pays concerné, pause quand il est masqué
  if (globe) {
    majActiviteGlobe();
    if (codePays) globe.focaliser(codePays);
    else if (route.type === 'globe') globe.deselectionner();
  }

  majAriane(route);
  document.title = titre;
  majCadrage();
}

/** Le globe ne se dessine que s'il est visible (économie de batterie). */
function majActiviteGlobe() {
  const masque = ['portefeuille', 'classement', 'comparaison', 'mes-alertes', 'sante', 'macro', 'geopolitique', 'risque', 'pepites', 'analyses', 'fiabilite'].includes(routeActuelle.type)
    || (dom.panneau.classList.contains('est-ouvert') && etatPanneau === 'plein' && !estLarge());
  globe?.definirActif(!masque);
}

/** Applique la hauteur du panneau (réduit, normal ou plein écran). */
function appliquerEtatPanneau() {
  if (estLarge()) { dom.panneau.style.height = ''; return; }
  dom.panneau.style.height = `${hauteurPanneau()}px`;
  dom.panneau.classList.toggle('est-plein', etatPanneau === 'plein');
}

function changerEtatPanneau(etat) {
  etatPanneau = etat;
  appliquerEtatPanneau();
  majActiviteGlobe();
  majCadrage();
}

/* ---------- Légende repliée derrière le bouton « ? » ---------- */
function brancherLegende() {
  dom.btnLegende.addEventListener('click', (e) => {
    e.stopPropagation();
    const ouvrir = dom.legende.hidden;
    dom.legende.hidden = !ouvrir;
    dom.btnLegende.setAttribute('aria-expanded', String(ouvrir));
  });
  // Un toucher ailleurs referme la légende
  document.addEventListener('pointerdown', (e) => {
    if (!dom.legende.hidden && !dom.legende.contains(e.target) && e.target !== dom.btnLegende && !dom.btnLegende.contains(e.target)) fermerLegende();
  });
}
function fermerLegende() {
  dom.legende.hidden = true;
  dom.btnLegende.setAttribute('aria-expanded', 'false');
}

/**
 * Calcule la zone de l'écran laissée libre par l'en-tête, les alertes et le
 * panneau, et y centre le globe.
 */
function majCadrage() {
  if (!globe) return;
  const L = innerWidth, H = innerHeight;
  const haut = dom.entete.getBoundingClientRect().bottom;
  const large = estLarge();
  const ouvert = dom.panneau.classList.contains('est-ouvert');
  // Bas de la zone libre : au-dessus des filtres (eux-mêmes au-dessus des alertes)
  let bas = dom.filtres.getBoundingClientRect().top - 4;
  let droite = L;
  const facteur = 0.94; // le globe occupe presque toute la zone libre (les colonnes sont courtes)

  if (ouvert && large) {
    droite = L - dom.panneau.offsetWidth - 32;
    bas = H;
  } else if (ouvert) {
    // Hauteur visée (et non la hauteur en cours d'animation)
    bas = H - Math.min(hauteurPanneau(), H - haut - 120);
  }
  const largeurZone = Math.max(100, droite);
  const hauteurZone = Math.max(100, bas - haut);
  globe.definirCadrage({
    cx: droite / 2,
    cy: haut + hauteurZone / 2,
    rayon: (Math.min(largeurZone, hauteurZone) / 2) * facteur,
    hautLibre: haut,
    basLibre: bas,
  });
}

/* ---------- Poignée du panneau : tirer vers le haut (plein écran) ou vers le bas (réduit, puis fermé) ---------- */
function brancherGlissementPanneau() {
  let depart = null, hauteurDepart = 0, id = null, dernier = null, vitesse = 0;
  const zones = [dom.poignee, dom.panneau.querySelector('.navigation')];
  for (const zone of zones) {
    zone.addEventListener('pointerdown', (e) => {
      if (e.target.closest('button') || estLarge()) return;
      id = e.pointerId; depart = e.clientY; hauteurDepart = dom.panneau.offsetHeight;
      dernier = { y: e.clientY, t: performance.now() }; vitesse = 0;
      zone.setPointerCapture(id);
      dom.panneau.classList.add('est-glisse');
    });
    zone.addEventListener('pointermove', (e) => {
      if (e.pointerId !== id) return;
      const h = Math.min(innerHeight - 6, Math.max(60, hauteurDepart - (e.clientY - depart)));
      dom.panneau.style.height = `${h}px`;
      const t = performance.now();
      vitesse = (e.clientY - dernier.y) / Math.max(1, t - dernier.t); // px/ms, positif vers le bas
      dernier = { y: e.clientY, t };
    });
    const fin = (e) => {
      if (e.pointerId !== id) return;
      id = null;
      dom.panneau.classList.remove('est-glisse');
      const deplacement = e.clientY - depart;
      if (performance.now() - dernier.t > 120) vitesse = 0; // doigt arrêté avant le lâcher : pas d'élan
      const h = dom.panneau.offsetHeight;
      const rang = ETATS_PANNEAU.indexOf(etatPanneau);
      if (Math.abs(deplacement) < 6) {
        // Simple toucher sur la poignée : bascule normal ↔ plein écran
        changerEtatPanneau(etatPanneau === 'plein' ? 'normal' : 'plein');
      } else if (vitesse > 0.6) {
        // Geste rapide vers le bas : un cran plus bas, ou fermeture
        if (rang === 0) allerVers({ type: 'globe' }); else changerEtatPanneau(ETATS_PANNEAU[rang - 1]);
      } else if (vitesse < -0.6) {
        changerEtatPanneau(ETATS_PANNEAU[Math.min(2, rang + 1)]);
      } else if (h < hauteurPanneau('reduit') * 0.6) {
        allerVers({ type: 'globe' });
      } else {
        // Sinon : la hauteur la plus proche
        const plusProche = ETATS_PANNEAU.reduce((a, b) => (Math.abs(hauteurPanneau(b) - h) < Math.abs(hauteurPanneau(a) - h) ? b : a));
        changerEtatPanneau(plusProche);
      }
    };
    zone.addEventListener('pointerup', fin);
    zone.addEventListener('pointercancel', fin);
  }
}

/* ---------- Messages et solution de secours ---------- */
function afficherMessage(texte, ...enfants) {
  dom.message.replaceChildren(el('p', {}, texte), ...enfants);
  dom.message.hidden = false;
}

/** Sans globe 3D : on propose la liste des pays pour continuer à naviguer. */
function afficherSecours() {
  const liste = el('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '6px', justifyContent: 'center', marginTop: '12px' } },
    d.pays.map((p) => el('button', {
      class: 'bouton', type: 'button',
      onclick: () => { dom.message.hidden = true; naviguer({ type: 'pays', id: p.code }); },
    }, `${p.nom} · ${p.note}`)));
  afficherMessage("Le globe 3D n'a pas pu démarrer sur cet appareil. Choisissez un pays :", liste);
}

/* ---------- PWA : service worker (mise en cache pour un usage hors ligne) ---------- */
function enregistrerServiceWorker() {
  if (!('serviceWorker' in navigator) || location.protocol === 'file:') return;
  // Quand une nouvelle version du service worker prend le relais, on recharge une fois
  // pour afficher immédiatement la dernière version de l'appli.
  const avaitUnControleur = Boolean(navigator.serviceWorker.controller);
  let recharge = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!avaitUnControleur || recharge) return;
    recharge = true;
    location.reload();
  });
  addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js')
      .then((inscription) => inscription?.update())
      .catch((e) => console.warn('Service worker non enregistré', e));
  });
}

demarrer();
