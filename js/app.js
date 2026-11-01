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
import { el } from './outils.js';
import { demarrerHorloge, remplirBandeau, initialiserAlertes, lireModeLeger, memoriserModeLeger } from './interface.js';
import { fichePays, ficheSecteur } from './panneau-pays.js';
import { ficheEntreprise } from './panneau-entreprise.js';
import { ecranPortefeuille } from './portefeuille.js';
import { ecranClassement } from './classement.js';

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
  legende: $('#legende'),
  entete: $('.entete'),
  alertes: $('#alertes'),
  message: $('#message'),
  btnLeger: $('#btn-leger'),
};

let d = null;      // données chargées
let globe = null;  // instance du globe 3D (null si WebGL indisponible)
let alertes = null;
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

/* ============================== Démarrage ============================== */

async function demarrer() {
  demarrerHorloge($('#horloge'));
  enregistrerServiceWorker();

  try {
    d = await chargerDonnees();
  } catch (erreur) {
    console.error(erreur);
    afficherMessage('Impossible de charger les données. Vérifiez votre connexion puis rechargez la page.');
    return;
  }

  // La mention « Données fictives » disparaît quand plus aucun fichier n'est fictif
  document.querySelectorAll('.badge-fictif').forEach((b) => { b.hidden = !d.fictif; });
  remplirBandeau($('#bandeau-piste'), d.marches);
  alertes = initialiserAlertes(
    { bouton: $('#alertes-bascule'), liste: $('#alertes-liste'), compte: $('#alertes-compte'), apercu: $('#alertes-apercu') },
    d.alertes, d.paysParCode, (code) => naviguer({ type: 'pays', id: code }),
  );

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
  brancherLegende();
  document.querySelectorAll('.js-retour').forEach((b) => b.addEventListener('click', retour));
  document.querySelectorAll('.js-fermer').forEach((b) => b.addEventListener('click', () => allerVers({ type: 'globe' })));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && routeActuelle.type !== 'globe') retour(); });
  brancherGlissementPanneau();

  // Le globe est chargé à part : si Three.js ou WebGL est indisponible,
  // le reste de l'application continue de fonctionner.
  try {
    const { Globe } = await import('./globe.js');
    globe = new Globe($('#globe'), $('#etiquettes'), {
      pays: d.pays,
      frontieres: d.frontieres,
      leger,
      surSelection: (code) => naviguer({ type: 'pays', id: code }),
    });
  } catch (erreur) {
    console.error(erreur);
    afficherSecours();
  }

  addEventListener('resize', () => { appliquerEtatPanneau(); majCadrage(); });
  addEventListener('hashchange', surChangementAdresse);
  pile = [location.hash || '#/'];
  afficher(lireAdresse());
}

function appliquerModeLeger(actif) {
  document.body.classList.toggle('mode-leger', actif);
  dom.btnLeger.setAttribute('aria-pressed', String(actif));
  dom.btnLeger.title = actif ? 'Mode léger activé (cliquer pour le désactiver)' : 'Activer le mode léger (économie de batterie)';
  globe?.definirLeger(actif);
}

/* ============================== Navigation ============================== */

/** Transforme une route en adresse (#/pays/FR) et inversement. */
function versAdresse(route) {
  return route.type === 'globe' ? '#/' : route.id ? `#/${route.type}/${encodeURIComponent(route.id)}` : `#/${route.type}`;
}
function lireAdresse() {
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
    case 'globe': case 'portefeuille': case 'classement': return true;
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
    contenu = ficheEntreprise(d, e); codePays = e.pays; titre = `${e.nom} — Salle de contrôle`;
  }

  const panneauOuvert = Boolean(contenu);
  // À l'ouverture, le panneau part de sa hauteur normale ; ensuite il garde la hauteur choisie
  if (panneauOuvert && !dom.panneau.classList.contains('est-ouvert')) etatPanneau = 'normal';
  if (contenu) {
    dom.panneauContenu.replaceChildren(...contenu);
    dom.panneauContenu.scrollTop = 0;
  }
  dom.panneau.classList.toggle('est-ouvert', panneauOuvert);
  dom.panneau.setAttribute('aria-hidden', String(!panneauOuvert));
  dom.panneau.inert = !panneauOuvert;
  document.body.classList.toggle('panneau-ouvert', panneauOuvert);
  if (panneauOuvert) { alertes?.replier(); fermerLegende(); }
  appliquerEtatPanneau();

  // Écran portefeuille
  const portefeuille = route.type === 'portefeuille';
  if (portefeuille) {
    dom.portefeuilleContenu.replaceChildren(...ecranPortefeuille(d, navigateurPanneau));
    dom.portefeuilleContenu.scrollTop = 0;
    titre = 'Portefeuille démo — Salle de contrôle';
  }
  dom.ecranPortefeuille.hidden = !portefeuille;

  // Écran classement
  const classement = route.type === 'classement';
  if (classement) {
    dom.classementContenu.replaceChildren(...ecranClassement(d, navigateurPanneau));
    dom.classementContenu.scrollTop = 0;
    titre = 'Classement — Salle de contrôle';
  }
  dom.ecranClassement.hidden = !classement;

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
  const masque = ['portefeuille', 'classement'].includes(routeActuelle.type)
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
  let bas = H - dom.alertes.querySelector('.alertes-bascule').offsetHeight - 14;
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
  if ('serviceWorker' in navigator && location.protocol !== 'file:') {
    addEventListener('load', () => {
      navigator.serviceWorker.register('sw.js').catch((e) => console.warn('Service worker non enregistré', e));
    });
  }
}

demarrer();
