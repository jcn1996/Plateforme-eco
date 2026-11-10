/* ==========================================================================
   Mes portefeuilles : import d'un fichier exporté du courtier (CSV ou Excel).

   1. lecture du fichier (CSV : séparateur ; , ou tabulation détecté, guillemets ;
      Excel : première feuille, via SheetJS chargé à la demande) ;
   2. repérage de la ligne d'en-tête (les exports ont souvent quelques lignes
      d'introduction avant le tableau) ;
   3. détection des colonnes (nom, ISIN, ticker, quantité, prix de revient, cours,
      valeur, devise) par leurs intitulés usuels, en français et en anglais ;
   4. si la détection échoue, l'écran propose une correspondance manuelle des colonnes.

   Tout se fait sur l'appareil : le contenu du fichier n'est jamais envoyé.
   Fonctions pures (sauf lireFichier) : testées par js/tests/portefeuilles.test.mjs.
   ========================================================================== */

/** Champs reconnus, avec leurs intitulés usuels (comparés sans accents ni casse). */
export const CHAMPS = {
  nom: { libelle: 'Nom', synonymes: ['nom', 'libelle', 'libelle valeur', 'name', 'description', 'instrument', 'titre', 'produit', 'support', 'designation', 'intitule', 'financial instrument', 'security', 'valeur mobiliere'] },
  isin: { libelle: 'ISIN', synonymes: ['isin', 'code isin', 'isin code', 'code'] },
  ticker: { libelle: 'Ticker', synonymes: ['ticker', 'symbole', 'symbol', 'mnemo', 'mnemonique', 'code mnemonique', 'tickersymbol'] },
  quantite: { libelle: 'Quantité', synonymes: ['quantite', 'qte', 'qty', 'quantity', 'nombre', 'nombre de parts', 'nb parts', 'nb de parts', 'parts', 'units', 'unites', 'position', 'nominal', 'quantite detenue'] },
  prix_revient: { libelle: 'Prix de revient unitaire', synonymes: ['prix de revient', 'pru', 'prix revient', 'prix de revient unitaire', 'pr unitaire', 'cours moyen', 'prix moyen', "prix moyen d'achat", 'prix d achat', "prix d'achat", 'cout moyen', 'cost basis price', 'average cost', 'avg price', 'average price', 'buyingprice', 'buying price', 'open rate', 'pmp'] },
  cours: { libelle: 'Dernier cours', synonymes: ['cours', 'dernier cours', 'cours actuel', 'last', 'last price', 'lastprice', 'price', 'mark price', 'markprice', 'current price', 'valeur liquidative', 'vl'] },
  valeur: { libelle: 'Valeur actuelle', synonymes: ['valeur', 'valorisation', 'valeur actuelle', 'montant', 'montant eur', 'montant (eur)', 'evaluation', 'market value', 'position value', 'positionvalue', 'amount', 'valeur de marche', 'encours', 'montant net', 'valorisation eur', 'value'] },
  devise: { libelle: 'Devise', synonymes: ['devise', 'currency', 'monnaie', 'ccy'] },
};

/** Libellé sans accents, en minuscules, espaces réduits ; « (EUR) » et ponctuation conservés seulement entre parenthèses. */
export function normaliserIntitule(t) {
  return String(t ?? '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[_.:/\\-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Découpe un texte CSV (séparateur détecté) en tableau de lignes. */
export function lireCSV(texte) {
  const t = String(texte ?? '').replace(/^﻿/, '');
  const lignesBrutes = t.split(/\r?\n/).filter((l) => l.trim()).slice(0, 40);
  const compter = (sep) => {
    const c = lignesBrutes.map((l) => decouperLigne(l, sep).length);
    // séparateur retenu : celui qui donne le plus de colonnes, de façon stable, sur les lignes du tableau
    const max = Math.max(0, ...c);
    return max > 1 ? max * 10 + c.filter((n) => n === max).length : 0;
  };
  const sep = [';', '\t', ',', '|'].reduce((a, s) => (compter(s) > compter(a) ? s : a), ';');
  const resultat = [];
  // Analyse complète (gère les retours à la ligne entre guillemets)
  let ligne = [];
  let champ = '';
  let guillemets = false;
  for (let i = 0; i < t.length; i += 1) {
    const c = t[i];
    if (guillemets) {
      if (c === '"' && t[i + 1] === '"') { champ += '"'; i += 1; } else if (c === '"') guillemets = false;
      else champ += c;
    } else if (c === '"' && champ.trim() === '') { champ = ''; guillemets = true; } else if (c === sep) { ligne.push(champ.trim()); champ = ''; } else if (c === '\n' || c === '\r') {
      if (c === '\r' && t[i + 1] === '\n') i += 1;
      ligne.push(champ.trim());
      if (ligne.some((x) => x !== '')) resultat.push(ligne);
      ligne = []; champ = '';
    } else champ += c;
  }
  ligne.push(champ.trim());
  if (ligne.some((x) => x !== '')) resultat.push(ligne);
  return resultat;
}

function decouperLigne(l, sep) {
  const r = [];
  let champ = '';
  let g = false;
  for (let i = 0; i < l.length; i += 1) {
    const c = l[i];
    if (g) { if (c === '"' && l[i + 1] === '"') { champ += '"'; i += 1; } else if (c === '"') g = false; else champ += c; } else if (c === '"') g = true;
    else if (c === sep) { r.push(champ); champ = ''; } else champ += c;
  }
  r.push(champ);
  return r;
}

/**
 * Nombre écrit à la française ou à l'anglaise : « 1 234,56 », « 1.234,56 », « 1,234.56 »,
 * « 12,5 % », « 1 234,56 € », « (12,30) » (négatif). Renvoie null si illisible.
 */
export function lireNombre(v) {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (v == null) return null;
  let s = String(v).trim();
  if (!s) return null;
  let negatif = false;
  if (/^\(.*\)$/.test(s)) { negatif = true; s = s.slice(1, -1); }
  s = s.replace(/[\s  ']/g, '').replace(/[€$£¥%]|EUR|USD|GBP|CHF/gi, '');
  s = s.replace(/^[−–]/, '-');
  if (s.startsWith('-')) { negatif = !negatif; s = s.slice(1); }
  if (s.startsWith('+')) s = s.slice(1);
  if (!/^[\d.,]+$/.test(s)) return null;
  const virgule = s.lastIndexOf(',');
  const point = s.lastIndexOf('.');
  if (virgule >= 0 && point >= 0) {
    // le dernier séparateur rencontré est le séparateur décimal
    s = virgule > point ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
  } else if (virgule >= 0) {
    const parties = s.split(',');
    // « 1,234,567 » : séparateurs de milliers anglais ; sinon virgule décimale
    s = parties.length > 2 && parties.slice(1).every((p) => p.length === 3) ? parties.join('') : s.replace(',', '.');
  } else if (point >= 0) {
    const parties = s.split('.');
    if (parties.length > 2) s = parties.join(''); // « 1.234.567 »
  }
  const n = Number(s);
  if (!Number.isFinite(n)) return null;
  return negatif ? -n : n;
}

/** Vérifie un code ISIN (format et clé de contrôle de Luhn). */
export function isinValide(code) {
  const c = String(code ?? '').trim().toUpperCase();
  if (!/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(c)) return false;
  const chiffres = c.split('').map((ch) => (/\d/.test(ch) ? ch : String(ch.charCodeAt(0) - 55))).join('');
  let somme = 0;
  for (let i = 0; i < chiffres.length; i += 1) {
    let n = Number(chiffres[chiffres.length - 1 - i]);
    if (i % 2 === 1) { n *= 2; if (n > 9) n -= 9; }
    somme += n;
  }
  return somme % 10 === 0;
}

function scoreIntitule(intitule, champ) {
  const n = normaliserIntitule(intitule);
  if (!n) return 0;
  let meilleur = 0;
  for (const s of CHAMPS[champ].synonymes) {
    if (n === s) return 100;
    // « montant (eur) », « quantite totale »… : le synonyme est un mot entier de l'intitulé
    const re = new RegExp(`(^|\\s|\\()${s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|\\s|\\))`);
    if (s.length >= 3 && re.test(n)) meilleur = Math.max(meilleur, 50 + s.length);
  }
  return meilleur;
}

/**
 * Repère la ligne d'en-tête parmi les 20 premières lignes : celle qui reconnaît le
 * plus de champs. Renvoie { indice, correspondance } ; correspondance : champ → n° de colonne.
 */
export function detecterColonnes(lignes) {
  let meilleur = { indice: -1, correspondance: {}, score: 0 };
  lignes.slice(0, 20).forEach((ligne, indice) => {
    const correspondance = attribuer(ligne);
    const score = Object.keys(correspondance).length;
    if (score > meilleur.score) meilleur = { indice, correspondance, score };
  });
  // Pas d'en-tête trouvée : on tente de reconnaître les colonnes par leur contenu (ISIN…)
  if (meilleur.score < 2) return { indice: -1, correspondance: deviner(lignes), score: 0 };
  // Colonne ISIN non nommée mais présente dans les données
  const c = meilleur.correspondance;
  if (c.isin == null) {
    const donnees = lignes.slice(meilleur.indice + 1, meilleur.indice + 30);
    const n = Math.max(...donnees.map((l) => l.length), 0);
    for (let j = 0; j < n; j += 1) {
      if (Object.values(c).includes(j)) continue;
      const vals = donnees.map((l) => l[j]).filter(Boolean);
      if (vals.length && vals.filter(isinValide).length >= vals.length * 0.6) { c.isin = j; break; }
    }
  }
  return meilleur;
}

function attribuer(ligne) {
  const candidats = [];
  ligne.forEach((intitule, j) => {
    for (const champ of Object.keys(CHAMPS)) {
      const s = scoreIntitule(intitule, champ);
      if (s) candidats.push({ champ, j, s });
    }
  });
  candidats.sort((a, b) => b.s - a.s);
  const correspondance = {};
  const prises = new Set();
  for (const { champ, j } of candidats) {
    if (champ in correspondance || prises.has(j)) continue;
    correspondance[champ] = j;
    prises.add(j);
  }
  // « code » seul : ISIN si les valeurs ressemblent à des ISIN (sinon on laisse tomber)
  return correspondance;
}

function deviner(lignes) {
  const c = {};
  const n = Math.max(...lignes.slice(0, 30).map((l) => l.length), 0);
  for (let j = 0; j < n; j += 1) {
    const vals = lignes.slice(0, 30).map((l) => l[j]).filter(Boolean);
    if (!vals.length) continue;
    if (c.isin == null && vals.filter(isinValide).length >= vals.length * 0.6) c.isin = j;
    else if (c.nom == null && vals.filter((v) => lireNombre(v) == null && /[a-z]{3}/i.test(v)).length >= vals.length * 0.8) c.nom = j;
  }
  return c;
}

/** La correspondance suffit-elle pour importer ? (un identifiant et une quantité ou une valeur) */
export function correspondanceSuffisante(c) {
  return (c.nom != null || c.isin != null || c.ticker != null) && (c.quantite != null || c.valeur != null);
}

/**
 * Construit les lignes de portefeuille à partir du tableau et de la correspondance.
 * Ignore les lignes de total, les lignes vides et les lignes sans identifiant.
 */
export function construireLignes(lignes, { indice, correspondance: c }) {
  const resultat = [];
  const valeurDe = (l, champ) => (c[champ] == null ? '' : String(l[c[champ]] ?? '').trim());
  for (const l of lignes.slice(indice + 1)) {
    const nom = valeurDe(l, 'nom');
    const isinBrut = valeurDe(l, 'isin').toUpperCase();
    const isin = isinValide(isinBrut) ? isinBrut : '';
    let ticker = valeurDe(l, 'ticker').toUpperCase();
    // colonne « Code » qui contient en fait des tickers
    if (!ticker && isinBrut && !isin && !/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(isinBrut) && /^[A-Z0-9.=^-]{1,15}$/.test(isinBrut)) ticker = isinBrut;
    if (!nom && !isin && !ticker) continue;
    if (/^(total|sous[- ]total|solde|totaux)\b/i.test(normaliserIntitule(nom))) continue;
    const quantite = lireNombre(valeurDe(l, 'quantite'));
    const valeur = lireNombre(valeurDe(l, 'valeur'));
    if (quantite == null && valeur == null) continue;
    const devise = (valeurDe(l, 'devise').toUpperCase().match(/[A-Z]{3}/) ?? [''])[0];
    resultat.push({
      nom: nom || ticker || isin,
      isin: isin || null,
      ticker: ticker || null,
      quantite: quantite ?? null,
      prix_revient: lireNombre(valeurDe(l, 'prix_revient')),
      cours: lireNombre(valeurDe(l, 'cours')),
      valeur: valeur ?? null,
      devise: devise || null,
    });
  }
  return resultat;
}

/* --------------------------- Lecture des fichiers --------------------------- */

const SHEETJS = 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js';
let promesseSheetJS = null;

/** Charge SheetJS (lecture Excel) à la demande, une seule fois. */
function chargerSheetJS() {
  if (globalThis.XLSX) return Promise.resolve(globalThis.XLSX);
  promesseSheetJS ??= new Promise((ok, ko) => {
    const s = document.createElement('script');
    s.src = SHEETJS;
    s.crossOrigin = 'anonymous';
    s.onload = () => (globalThis.XLSX ? ok(globalThis.XLSX) : ko(new Error('Lecteur Excel indisponible.')));
    s.onerror = () => { promesseSheetJS = null; ko(new Error('Lecteur Excel injoignable : vérifiez la connexion, ou exportez le fichier en CSV.')); };
    document.head.append(s);
  });
  return promesseSheetJS;
}

/** Lit un fichier choisi par l'utilisateur et renvoie un tableau de lignes (tableaux de textes). */
export async function lireFichier(fichier) {
  const nom = fichier.name.toLowerCase();
  if (/\.(xlsx|xlsm|xls|ods)$/.test(nom)) {
    const XLSX = await chargerSheetJS();
    const classeur = XLSX.read(await fichier.arrayBuffer(), { type: 'array' });
    const feuille = classeur.Sheets[classeur.SheetNames[0]];
    return XLSX.utils.sheet_to_json(feuille, { header: 1, raw: false, defval: '' })
      .map((l) => l.map((x) => String(x ?? '').trim()))
      .filter((l) => l.some((x) => x));
  }
  const octets = new Uint8Array(await fichier.arrayBuffer());
  let texte = new TextDecoder('utf-8').decode(octets);
  // Export Windows (ISO-8859-1 / Windows-1252) : caractères de remplacement en UTF-8
  if (texte.includes('�')) texte = new TextDecoder('windows-1252').decode(octets);
  return lireCSV(texte);
}

/* --------------------------- Rapprochement local par le nom --------------------------- */

const FORMES_JURIDIQUES = new Set(['sa', 'se', 'nv', 'ag', 'plc', 'inc', 'corp', 'corporation', 'ltd', 'limited', 'co', 'company', 'the', 'spa', 'ab', 'asa', 'as', 'oyj', 'kgaa', 'societe', 'europeenne', 'group', 'groupe', 'holding', 'holdings', 'cie', 'et', 'and', 'de', 'la', 'le', 'les', 'class', 'cl', 'a', 'b', 'adr', 'reg', 'ord', 'shs', 'sca', 'bv', 'ltda', 'nom', 'act', 'action', 'actions', 'port']);

/** Nom réduit à ses mots distinctifs : « TotalEnergies SE » → « totalenergies ». */
export function nomCompare(nom) {
  return normaliserIntitule(nom)
    .replace(/[^a-z0-9 ]+/g, ' ')
    .split(' ')
    .filter((m) => m && !FORMES_JURIDIQUES.has(m))
    .join(' ');
}

/**
 * Cherche, SANS AUCUNE REQUÊTE, la société de l'agent entreprises qui correspond à une ligne
 * importée : même pays que l'ISIN, nom identique ou de même premier mot distinctif.
 * entreprises : [{ ticker, nom, pays, capitalisation_md }]. Renvoie l'entreprise ou null.
 */
export function rapprocherParNom(nom, isin, entreprises) {
  const n = nomCompare(nom);
  if (n.length < 3) return null;
  const pays = isin && /^[A-Z]{2}/.test(isin) ? isin.slice(0, 2) : null;
  const premier = n.split(' ')[0];
  let meilleur = null;
  for (const e of entreprises) {
    if (pays && !['IE', 'LU', 'XS', 'AN', 'BM', 'KY', 'JE', 'GG'].includes(pays) && e.pays !== pays) continue;
    const m = nomCompare(e.nom);
    if (!m) continue;
    let score = 0;
    if (m === n) score = 3;
    else if (premier.length >= 4 && m.split(' ')[0] === premier) score = 2;
    else if (n.length >= 6 && (m.startsWith(n) || n.startsWith(m))) score = 1;
    if (!score) continue;
    if (!pays && score < 3) continue; // sans pays, seule une égalité exacte est retenue
    const cle = score * 1e6 + (e.capitalisation_md ?? 0);
    if (!meilleur || cle > meilleur.cle) meilleur = { e, cle };
  }
  return meilleur?.e ?? null;
}
