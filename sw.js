/* ==========================================================================
   Service worker : rend l'application utilisable hors ligne.
   - Fichiers de l'application : servis depuis le cache (mise à jour en fond)
   - Données (data/*.json) : réseau d'abord, pour toujours afficher les
     dernières sorties des agents ; cache en secours si pas de réseau
   - Ressources externes (Three.js, polices) : cache dès le premier chargement
   Pour forcer une mise à jour chez tous les utilisateurs, changer VERSION.
   ========================================================================== */

const VERSION = 'salle-controle-v2';

const FICHIERS_APPLI = [
  './',
  'index.html',
  'manifest.json',
  'css/style.css',
  'js/app.js',
  'js/donnees.js',
  'js/globe.js',
  'js/interface.js',
  'js/outils.js',
  'js/panneau-pays.js',
  'js/panneau-entreprise.js',
  'js/portefeuille.js',
  'js/classement.js',
  'assets/icone.svg',
  'assets/icone-192.png',
  'assets/icone-512.png',
  'data/pays.json',
  'data/secteurs.json',
  'data/entreprises.json',
  'data/alertes.json',
  'data/portefeuille.json',
  'data/marches.json',
  'data/countries-110m.json',
];

self.addEventListener('install', (evenement) => {
  evenement.waitUntil(
    caches.open(VERSION).then((cache) => cache.addAll(FICHIERS_APPLI)).then(() => self.skipWaiting()),
  );
});

// Suppression des anciens caches lors d'une nouvelle version
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

  if (url.origin === location.origin && url.pathname.includes('/data/')) {
    evenement.respondWith(reseauDAbord(requete));
  } else {
    evenement.respondWith(cacheEtMiseAJour(evenement, requete));
  }
});

/** Réseau d'abord, cache en secours. */
async function reseauDAbord(requete) {
  const cache = await caches.open(VERSION);
  try {
    const reponse = await fetch(requete);
    if (reponse.ok) cache.put(requete, reponse.clone());
    return reponse;
  } catch {
    return (await cache.match(requete, { ignoreSearch: true })) ?? Response.error();
  }
}

/** Cache d'abord (réponse immédiate), puis mise à jour du cache en arrière-plan. */
async function cacheEtMiseAJour(evenement, requete) {
  const cache = await caches.open(VERSION);
  const enCache = await cache.match(requete, { ignoreSearch: true });
  const telechargement = fetch(requete)
    .then((reponse) => {
      // On met en cache les réponses valides, y compris celles des CDN (« opaque »)
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
