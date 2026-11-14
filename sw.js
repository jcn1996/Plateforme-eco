/* ==========================================================================
   Service worker : mise à jour automatique + usage hors ligne.
   - Page, JavaScript, CSS et données (même origine) : RÉSEAU D'ABORD.
     L'appli affiche donc toujours la dernière version dès l'ouverture ;
     le cache ne sert qu'en l'absence de réseau.
   - Icônes : cache d'abord (elles changent rarement ; une nouvelle VERSION
     les renouvelle). Le globe est 100 % vectoriel : aucune image de la Terre.
   - La carte détaillée data/countries-50m.json n'est pas préchargée : elle
     est mise en cache au premier zoom rapproché.
   - Ressources externes (Three.js, lignes épaisses, polices, Lightweight Charts) : cache dès
     le premier chargement, mis à jour en arrière-plan.
   - TradingView (scripts des widgets, cotations) : jamais mis en cache, le service
     worker laisse passer ces requêtes telles quelles.
   - Chef d'orchestre : data/chef.json préchargé ; briefing et suivi (data/chef/) lus à la demande.
   - Agent trader (démo) : data/portefeuille.json préchargé (réseau d'abord : valeur en direct) ;
     journal complet des opérations (data/trader/) non préchargé.
   - Séries de cours des graphiques (data/cours/), matières premières (data/matieres_premieres.json),
     initiés (data/inities.json), données alternatives (data/donnees_alternatives.json) et backtest
     (data/backtest/resultats.json) : non préchargés, lus à la demande.
   - Mes portefeuilles : les positions sont dans IndexedDB, jamais dans ce cache. Le fichier chiffré
     de synchronisation (requête « no-store » ou avec jeton) et la recherche ISIN → ticker
     (Yahoo Finance) ne passent pas par le cache. SheetJS (lecture Excel) est chargé à la demande.
   Changer VERSION vide les anciens caches chez tous les utilisateurs.
   ========================================================================== */

const VERSION = 'salle-controle-v52';

const FICHIERS_APPLI = [
  './',
  'index.html',
  'manifest.json',
  'css/style.css',
  'js/app.js',
  'js/donnees.js',
  'js/globe.js',
  'js/carte-vecteur.js',
  'js/interface.js',
  'js/outils.js',
  'js/panneau-pays.js',
  'js/panneau-entreprise.js',
  'js/portefeuille.js',
  'js/classement.js',
  'js/comparateur.js',
  'js/mes-alertes.js',
  'js/recherche.js',
  'js/sante.js',
  'js/planning.js',
  'js/macro.js',
  'js/geopolitique.js',
  'js/risque.js',
  'js/matieres-premieres.js',
  'js/inities.js',
  'js/pepites.js',
  'js/analyses.js',
  'js/graphiques.js',
  'js/symboles-tradingview.js',
  'js/flux-investissement.js',
  'js/pulsations.js',
  'js/dynamique-resultats.js',
  'js/analyse-financiere.js',
  'js/backtest.js',
  'js/chef.js',
  'js/donnees-alternatives.js',
  'js/menu.js',
  'js/mes-portefeuilles.js',
  'js/portefeuilles-donnees.js',
  'js/portefeuilles-chiffrement.js',
  'js/portefeuilles-import.js',
  'js/portefeuilles-analyse.js',
  'js/portefeuilles-exemple.js',
  'assets/icone.svg',
  'assets/icone-192.png',
  'assets/icone-512.png',
  'data/pays.json',
  'data/secteurs.json',
  'data/entreprises.json',
  'data/alertes.json',
  'data/portefeuille.json',
  'data/marches.json',
  'data/macro.json',
  'data/geopolitique.json',
  'data/risque.json',
  'data/pepites.json',
  'data/chef.json',
  'data/journal/index.json',
  'data/analyses/index.json',
  'data/countries-110m.json',
];

self.addEventListener('install', (evenement) => {
  evenement.waitUntil(
    caches.open(VERSION).then((cache) => cache.addAll(FICHIERS_APPLI)).then(() => self.skipWaiting()),
  );
});

// Suppression des anciens caches, puis prise de contrôle immédiate des pages ouvertes
self.addEventListener('activate', (evenement) => {
  evenement.waitUntil(
    caches.keys()
      .then((cles) => Promise.all(cles.filter((c) => c !== VERSION).map((c) => caches.delete(c))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (evenement) => {
  const requete = evenement.request;
  if (requete.method !== 'GET') return;
  const url = new URL(requete.url);

  // TradingView : scripts et données jamais mis en cache (réseau direct, sans passer par le service worker)
  if (/(^|\.)tradingview(-widget)?\.com$/.test(url.hostname)) return;

  // Mes portefeuilles : jamais de cache pour la synchronisation chiffrée (requête « no-store » ou
  // authentifiée) ni pour la recherche ISIN → ticker (Yahoo Finance)
  if (requete.cache === 'no-store' || requete.headers.has('Authorization')) return;
  if (/(^|\.)finance\.yahoo\.com$/.test(url.hostname)) return;

  if (url.origin !== location.origin) {
    evenement.respondWith(cacheEtMiseAJour(evenement, requete));
  } else if (/\/assets\/.+\.(jpg|png|svg)$/.test(url.pathname)) {
    evenement.respondWith(cacheDAbord(requete));
  } else {
    evenement.respondWith(reseauDAbord(requete));
  }
});

/** Réseau d'abord (sans cache HTTP intermédiaire), cache en secours hors ligne. */
async function reseauDAbord(requete) {
  const cache = await caches.open(VERSION);
  try {
    const reponse = await fetch(requete, { cache: 'no-cache' });
    if (reponse.ok) cache.put(requete, reponse.clone());
    return reponse;
  } catch {
    const enCache = await cache.match(requete, { ignoreSearch: true });
    if (enCache) return enCache;
    // Navigation hors ligne vers une adresse inconnue : on sert la page principale
    if (requete.mode === 'navigate') return (await cache.match('index.html')) ?? Response.error();
    return Response.error();
  }
}

/** Cache d'abord, réseau si absent. */
async function cacheDAbord(requete) {
  const cache = await caches.open(VERSION);
  const enCache = await cache.match(requete, { ignoreSearch: true });
  if (enCache) return enCache;
  const reponse = await fetch(requete);
  if (reponse.ok) cache.put(requete, reponse.clone());
  return reponse;
}

/** Cache d'abord (réponse immédiate), puis mise à jour du cache en arrière-plan. */
async function cacheEtMiseAJour(evenement, requete) {
  const cache = await caches.open(VERSION);
  const enCache = await cache.match(requete, { ignoreSearch: true });
  const telechargement = fetch(requete)
    .then((reponse) => {
      if (reponse.ok || reponse.type === 'opaque') cache.put(requete, reponse.clone());
      return reponse;
    })
    .catch(() => null);
  if (enCache) {
    evenement.waitUntil(telechargement);
    return enCache;
  }
  return (await telechargement) ?? Response.error();
}
