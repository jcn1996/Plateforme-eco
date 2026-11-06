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
   - Séries de cours des graphiques (data/cours/) : non préchargées, lues à la demande.
   Changer VERSION vide les anciens caches chez tous les utilisateurs.
   ========================================================================== */

const VERSION = 'salle-controle-v27';

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
  'js/pepites.js',
  'js/analyses.js',
  'js/graphiques.js',
  'js/symboles-tradingview.js',
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
  'data/flux.json',
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
