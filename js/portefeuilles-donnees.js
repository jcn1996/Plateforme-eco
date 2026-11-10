/* ==========================================================================
   Mes portefeuilles : stockage sur l'appareil et données de référence.

   CONFIDENTIALITÉ
   - Les portefeuilles sont stockés UNIQUEMENT dans IndexedDB, sur cet appareil
     (base « salle-controle-portefeuilles »). Ils ne sont jamais écrits dans le dépôt,
     jamais envoyés à un serveur.
   - Les seules requêtes réseau liées à un titre portent sur son IDENTIFIANT public
     (ISIN ou ticker), jamais sur une quantité ni un montant :
       · résolution ISIN → ticker : d'abord SUR L'APPAREIL (rapprochement avec les
         sociétés publiques de l'agent entreprises), sinon Yahoo Finance ;
       · fiche publique de l'agent entreprises (data/entreprises/fiches/<ticker>.json).
     Elles peuvent être coupées dans les réglages (« Requêtes par titre »).
   - La synchronisation lit un fichier CHIFFRÉ (AES-256-GCM) produit par le dépôt
     privé de l'utilisateur ; il est déchiffré ici, avec une clé dérivée du mot de passe
     conservée sous forme non extractible.

   Format stocké (une seule entrée, clé « principal ») :
   {
     version: 1,
     portefeuilles: [{
       id, nom, type ('pea' | 'cto' | 'assurance_vie' | 'per' | 'crypto' | 'autre'),
       source ('manuel' | 'fichier' | 'synchro'), synchro_cle, cree_le, maj_le,
       reference: { date, valeur },          valeur à l'import (base de la performance)
       historique: [{ date, valeur }],       un point par jour (valeur en euros)
       lignes: [{ id, nom, isin, ticker, type, quantite, prix_revient, cours, devise,
                  valeur, date_valeur, source_valeur,
                  categorie: { classe, zone, secteur, themes: [], indice } }]
     }],
     reglages: { requetes_par_titre: true, synchro: { depot, chemin, branche, url, jeton, active } },
     cle_synchro: CryptoKey | null,        clé PBKDF2 non extractible (mot de passe jamais stocké)
     synchro: { derniere, erreur, genere_le },
     series_synchro: { symbole: [[date, cours]] },   historiques fournis par la synchronisation
     resolutions: { ISIN: { ticker, nom, type, source, date } }
   }
   ========================================================================== */

import { dechiffrer, cleDeBase } from './portefeuilles-chiffrement.js';
import { rapprocherParNom } from './portefeuilles-import.js';

const BASE = 'salle-controle-portefeuilles';
const MAGASIN = 'etat';
const CLE = 'principal';

export const TYPES_PORTEFEUILLE = {
  pea: 'PEA',
  cto: 'Compte-titres',
  assurance_vie: 'Assurance vie',
  per: 'PER',
  crypto: 'Cryptoactifs',
  autre: 'Autre',
};

export function etatVide() {
  return {
    version: 1,
    portefeuilles: [],
    reglages: { requetes_par_titre: true, synchro: { depot: '', chemin: 'portefeuilles.chiffre.json', branche: 'synchro', url: '', jeton: '', active: false } },
    cle_synchro: null,
    synchro: { derniere: null, erreur: null, genere_le: null },
    series_synchro: {},
    resolutions: {},
  };
}

export function nouvelId(prefixe = 'l') {
  return `${prefixe}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

/* ------------------------------- IndexedDB ------------------------------- */

let promesseBase = null;
function ouvrir() {
  if (!globalThis.indexedDB) return Promise.reject(new Error('Stockage local indisponible sur ce navigateur (navigation privée ?).'));
  promesseBase ??= new Promise((ok, ko) => {
    const r = indexedDB.open(BASE, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(MAGASIN);
    r.onsuccess = () => ok(r.result);
    r.onerror = () => { promesseBase = null; ko(r.error ?? new Error('Ouverture du stockage local impossible.')); };
  });
  return promesseBase;
}

export async function lireEtat() {
  const db = await ouvrir();
  const brut = await new Promise((ok, ko) => {
    const r = db.transaction(MAGASIN, 'readonly').objectStore(MAGASIN).get(CLE);
    r.onsuccess = () => ok(r.result);
    r.onerror = () => ko(r.error);
  });
  const vide = etatVide();
  if (!brut || brut.version !== 1) return vide;
  return { ...vide, ...brut, reglages: { ...vide.reglages, ...brut.reglages, synchro: { ...vide.reglages.synchro, ...brut.reglages?.synchro } } };
}

export async function enregistrerEtat(etat) {
  const db = await ouvrir();
  await new Promise((ok, ko) => {
    const t = db.transaction(MAGASIN, 'readwrite');
    t.objectStore(MAGASIN).put(etat, CLE);
    t.oncomplete = () => ok();
    t.onerror = () => ko(t.error);
  });
}

/** Efface tout (portefeuilles, réglages, clé de synchronisation) de cet appareil. */
export async function toutEffacer() {
  const db = await ouvrir();
  await new Promise((ok, ko) => {
    const t = db.transaction(MAGASIN, 'readwrite');
    t.objectStore(MAGASIN).delete(CLE);
    t.oncomplete = () => ok();
    t.onerror = () => ko(t.error);
  });
}

/** Contenu sauvegardable (sans la clé de synchronisation ni le jeton d'accès). */
export function contenuSauvegarde(etat) {
  return {
    version: 1,
    exporte_le: new Date().toISOString(),
    portefeuilles: etat.portefeuilles,
    resolutions: etat.resolutions,
    reglages: { requetes_par_titre: etat.reglages.requetes_par_titre, synchro: { ...etat.reglages.synchro, jeton: '' } },
  };
}

/* ------------------------------- Historique de valeur ------------------------------- */

/** Ajoute (ou remplace) le point du jour dans l'historique d'un portefeuille. */
export function noterValeur(pf, valeur, date = new Date().toISOString().slice(0, 10)) {
  if (!(valeur > 0)) return false;
  pf.historique ??= [];
  const dernier = pf.historique[pf.historique.length - 1];
  if (dernier?.date === date) {
    if (Math.abs(dernier.valeur - valeur) < 0.005) return false;
    dernier.valeur = valeur;
  } else pf.historique.push({ date, valeur });
  if (pf.historique.length > 1500) pf.historique.splice(0, pf.historique.length - 1500);
  return true;
}

/* ------------------------------- Données publiques ------------------------------- */

const cacheFiches = new Map();

/** Séries de cours publiques des agents (marchés, ETF pays, indices) : symbole → [[date, cours]]. */
export async function chargerSeriesPubliques() {
  const fichiers = ['data/cours/marches.json', 'data/cours/etf-pays.json', 'data/cours/indices-pays.json'];
  const series = {};
  await Promise.all(fichiers.map(async (f) => {
    try {
      const r = await fetch(f, { cache: 'no-cache' });
      if (!r.ok) return;
      const j = await r.json();
      for (const [s, v] of Object.entries(j.donnees ?? {})) if (Array.isArray(v)) series[s] = v;
    } catch { /* hors ligne */ }
  }));
  return series;
}

/** Fiche publique d'une société (data/entreprises/fiches/<ticker>.json), mise en cache pour la session. */
export async function chargerFichePublique(ticker) {
  if (cacheFiches.has(ticker)) return cacheFiches.get(ticker);
  const p = fetch(`data/entreprises/fiches/${encodeURIComponent(ticker)}.json`, { cache: 'no-cache' })
    .then((r) => (r.ok ? r.json() : null))
    .then((j) => j?.donnees ?? null)
    .catch(() => null);
  cacheFiches.set(ticker, p);
  return p;
}

/* ------------------------------- Résolution ISIN → ticker ------------------------------- */

/** Code de place (nomenclature Bloomberg) → suffixe Yahoo Finance. */
const SUFFIXES_FIGI = {
  US: '', UN: '', UW: '', UQ: '', UR: '', UA: '', UP: '', UV: '',
  FP: '.PA', NA: '.AS', BB: '.BR', PL: '.LS', ID: '.IR', GY: '.DE', GR: '.F', LN: '.L', SM: '.MC', IM: '.MI',
  SW: '.SW', SE: '.SW', VX: '.SW', SS: '.ST', DC: '.CO', FH: '.HE', NO: '.OL', AV: '.VI', JT: '.T', HK: '.HK',
  CN: '.TO', CT: '.TO', AU: '.AX', AT: '.AX', KS: '.KS', TT: '.TW', SP: '.SI', IN: '.NS', IB: '.NS',
};
/** Place préférée selon le pays de l'ISIN. */
const PLACE_PAYS = { FR: 'FP', NL: 'NA', BE: 'BB', PT: 'PL', DE: 'GY', GB: 'LN', ES: 'SM', IT: 'IM', CH: 'SW', SE: 'SS', DK: 'DC', FI: 'FH', NO: 'NO', AT: 'AV', JP: 'JT', HK: 'HK', CA: 'CN', AU: 'AU', US: 'US', IE: 'NA', LU: 'FP' };

const TYPES_YAHOO = { EQUITY: 'action', ETF: 'etf', MUTUALFUND: 'fonds', CRYPTOCURRENCY: 'crypto', INDEX: 'etf' };

async function rechercheYahoo(isin) {
  const u = `https://query2.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(isin)}&quotesCount=6&newsCount=0&listsCount=0`;
  const r = await fetch(u, { credentials: 'omit', referrerPolicy: 'no-referrer' });
  if (!r.ok) throw new Error(`Yahoo ${r.status}`);
  const j = await r.json();
  const q = (j.quotes ?? []).filter((x) => x.symbol);
  if (!q.length) return null;
  const pays = isin.slice(0, 2);
  const suffixe = SUFFIXES_FIGI[PLACE_PAYS[pays]] ?? null;
  const choisi = (suffixe != null && q.find((x) => (suffixe ? x.symbol.endsWith(suffixe) : !x.symbol.includes('.')))) || q[0];
  return { ticker: choisi.symbol, nom: choisi.longname ?? choisi.shortname ?? null, type: TYPES_YAHOO[choisi.quoteType] ?? 'autre', source: 'Yahoo Finance' };
}

/**
 * Cherche le ticker Yahoo d'un ISIN :
 * 1. SUR L'APPAREIL, sans requête : rapprochement du nom et du pays de l'ISIN avec les sociétés
 *    publiques de l'agent entreprises (environ 3 000) ;
 * 2. sinon Yahoo Finance (seul l'ISIN est transmis, jamais la quantité ni le montant). Yahoo
 *    n'autorise pas les appels depuis une page web : la plupart des navigateurs bloquent la réponse.
 *    (OpenFIGI refuse aussi les appels depuis une page web.)
 * Renvoie null si l'ISIN n'est pas reconnu : la ligne est classée « fonds », catégorie à saisir.
 */
export async function resoudreISIN(isin, { nom = '', entreprises = [], reseau = true } = {}) {
  const jour = new Date().toISOString().slice(0, 10);
  const e = rapprocherParNom(nom, isin, entreprises);
  if (e) return { ticker: e.ticker, nom: e.nom, type: 'action', source: 'rapprochement local (agent entreprises)', date: jour };
  if (!reseau) return null;
  try {
    const r = await rechercheYahoo(isin);
    if (r) return { ...r, date: jour };
  } catch { /* Yahoo injoignable depuis le navigateur */ }
  return null;
}

/* ------------------------------- Synchronisation ------------------------------- */

/** Adresse du fichier chiffré : API GitHub (dépôt privé, jeton en lecture seule) ou adresse directe. */
export function adresseSynchro(s) {
  if (s.url) return s.url.trim();
  if (!s.depot || !/^[\w.-]+\/[\w.-]+$/.test(s.depot.trim())) return null;
  const chemin = (s.chemin || 'portefeuilles.chiffre.json').replace(/^\/+/, '');
  return `https://api.github.com/repos/${s.depot.trim()}/contents/${chemin.split('/').map(encodeURIComponent).join('/')}?ref=${encodeURIComponent(s.branche || 'synchro')}`;
}

/** Enregistre la clé de déchiffrement dérivée du mot de passe (non extractible) : le mot de passe n'est pas stocké. */
export async function memoriserMotDePasse(etat, motDePasse) {
  etat.cle_synchro = await cleDeBase(motDePasse);
}

/**
 * Télécharge et déchiffre le fichier de synchronisation. Requête GET sans aucune donnée de
 * portefeuille : seul le jeton d'accès en lecture au dépôt privé est envoyé, à GitHub.
 */
export async function telechargerSynchro(etat) {
  const s = etat.reglages.synchro;
  const adresse = adresseSynchro(s);
  if (!adresse) throw new Error('Adresse de synchronisation incomplète (dépôt privé « propriétaire/nom » ou adresse directe).');
  if (!etat.cle_synchro) throw new Error('Mot de passe de synchronisation non saisi sur cet appareil.');
  const entetes = {};
  if (adresse.startsWith('https://api.github.com/')) {
    entetes.Accept = 'application/vnd.github.raw+json';
    entetes['X-GitHub-Api-Version'] = '2022-11-28';
  }
  if (s.jeton) entetes.Authorization = `Bearer ${s.jeton.trim()}`;
  const r = await fetch(adresse, { headers: entetes, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer' });
  if (r.status === 404) throw new Error('Fichier chiffré introuvable : vérifiez le dépôt, la branche « synchro » et le jeton (accès en lecture au dépôt privé).');
  if (r.status === 401 || r.status === 403) throw new Error('Accès refusé par GitHub : jeton absent, expiré ou sans accès en lecture au dépôt privé.');
  if (!r.ok) throw new Error(`Téléchargement impossible (${r.status}).`);
  return dechiffrer(await r.json(), etat.cle_synchro);
}

/** Clé d'appariement de deux lignes (même titre). */
const cleLigne = (l) => (l.isin || l.ticker || l.nom || '').toUpperCase();

/**
 * Intègre le contenu déchiffré de la synchronisation :
 * un portefeuille par compte synchronisé (créé au premier passage), lignes remplacées,
 * catégories saisies à la main conservées, point du jour ajouté à l'historique.
 */
export function integrerSynchro(etat, contenu) {
  if (!contenu || !Array.isArray(contenu.portefeuilles)) throw new Error('Contenu de synchronisation inattendu.');
  const aujourdhui = (contenu.genere_le ?? new Date().toISOString()).slice(0, 10);
  const bilan = [];
  for (const p of contenu.portefeuilles) {
    let pf = etat.portefeuilles.find((x) => x.synchro_cle === p.cle);
    if (!pf) {
      pf = { id: nouvelId('p'), nom: p.nom, type: p.type ?? 'cto', source: 'synchro', synchro_cle: p.cle, cree_le: new Date().toISOString(), lignes: [], historique: [], reference: null };
      etat.portefeuilles.push(pf);
    }
    const anciennes = new Map(pf.lignes.map((l) => [cleLigne(l), l]));
    pf.lignes = (p.lignes ?? []).map((l) => {
      const a = anciennes.get(cleLigne(l));
      return {
        id: a?.id ?? nouvelId(),
        nom: l.nom, isin: l.isin ?? null, ticker: l.ticker ?? a?.ticker ?? null, type: a?.type ?? l.type ?? 'action',
        quantite: l.quantite ?? null, prix_revient: l.prix_revient ?? null, cours: l.cours ?? null, devise: l.devise ?? null,
        valeur: l.valeur ?? null, date_valeur: l.date ?? aujourdhui, source_valeur: `synchronisation ${p.courtier ?? ''}`.trim(),
        categorie: a?.categorie ?? l.categorie ?? undefined,
      };
    });
    pf.maj_le = contenu.genere_le ?? new Date().toISOString();
    const total = pf.lignes.reduce((s, l) => s + (l.valeur ?? 0), 0);
    if (!pf.reference && total > 0) pf.reference = { date: aujourdhui, valeur: total };
    noterValeur(pf, total, aujourdhui);
    bilan.push({ nom: pf.nom, lignes: pf.lignes.length });
  }
  etat.series_synchro = { ...etat.series_synchro, ...(contenu.historiques ?? {}) };
  etat.synchro = { derniere: new Date().toISOString(), erreur: null, genere_le: contenu.genere_le ?? null };
  return bilan;
}
