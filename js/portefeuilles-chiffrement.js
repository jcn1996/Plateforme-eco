/* ==========================================================================
   Mes portefeuilles : chiffrement local (WebCrypto, aucune bibliothèque).

   - AES-256-GCM, clé dérivée du mot de passe par PBKDF2-SHA-256 (600 000 itérations),
     sel aléatoire de 16 octets, vecteur d'initialisation aléatoire de 12 octets.
   - Même enveloppe pour la sauvegarde (export / import d'un fichier pour changer
     d'appareil) et pour la synchronisation automatique (fichier produit par le
     dépôt privé, voir outils/synchro-portefeuilles/) :

     {
       "format": "salle-controle/portefeuilles-chiffres",
       "version": 1,
       "kdf": { "nom": "PBKDF2", "hachage": "SHA-256", "iterations": 600000, "sel": "<base64>" },
       "chiffrement": { "nom": "AES-256-GCM", "iv": "<base64>" },
       "cree_le": "2026-11-10T06:00:00Z",
       "donnees": "<base64 : texte chiffré suivi de l'étiquette GCM de 16 octets>"
     }

   Rien ne quitte l'appareil : ce module ne fait aucune requête réseau.
   Fonctionne dans le navigateur et dans Node ≥ 20 (globalThis.crypto.subtle).
   ========================================================================== */

export const FORMAT_CHIFFRE = 'salle-controle/portefeuilles-chiffres';
export const ITERATIONS_PBKDF2 = 600000;

const sub = () => {
  const s = globalThis.crypto?.subtle;
  if (!s) throw new Error('Chiffrement indisponible : ce navigateur ne propose pas WebCrypto (page servie en HTTPS requise).');
  return s;
};

export function versBase64(octets) {
  const o = octets instanceof Uint8Array ? octets : new Uint8Array(octets);
  let s = '';
  for (let i = 0; i < o.length; i += 0x8000) s += String.fromCharCode(...o.subarray(i, i + 0x8000));
  return btoa(s);
}

export function depuisBase64(texte) {
  const s = atob(String(texte).replace(/\s+/g, ''));
  const o = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i += 1) o[i] = s.charCodeAt(i);
  return o;
}

/**
 * Clé de base PBKDF2 tirée du mot de passe, NON extractible : elle peut être conservée
 * dans IndexedDB (synchronisation : mot de passe saisi une seule fois sur l'appareil)
 * sans que le mot de passe lui-même y soit écrit ni puisse en être relu.
 */
export async function cleDeBase(motDePasse) {
  if (!motDePasse) throw new Error('Mot de passe vide.');
  return sub().importKey('raw', new TextEncoder().encode(motDePasse), 'PBKDF2', false, ['deriveKey']);
}

async function deriver(base, sel, iterations) {
  return sub().deriveKey(
    { name: 'PBKDF2', hash: 'SHA-256', salt: sel, iterations },
    base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'],
  );
}

/** Chiffre un objet JSON avec un mot de passe (ou une clé de base) : renvoie l'enveloppe. */
export async function chiffrer(objet, motDePasseOuCle, { iterations = ITERATIONS_PBKDF2 } = {}) {
  const base = typeof motDePasseOuCle === 'string' ? await cleDeBase(motDePasseOuCle) : motDePasseOuCle;
  const sel = globalThis.crypto.getRandomValues(new Uint8Array(16));
  const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const cle = await deriver(base, sel, iterations);
  const clair = new TextEncoder().encode(JSON.stringify(objet));
  const chiffre = await sub().encrypt({ name: 'AES-GCM', iv }, cle, clair);
  return {
    format: FORMAT_CHIFFRE,
    version: 1,
    kdf: { nom: 'PBKDF2', hachage: 'SHA-256', iterations, sel: versBase64(sel) },
    chiffrement: { nom: 'AES-256-GCM', iv: versBase64(iv) },
    cree_le: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    donnees: versBase64(new Uint8Array(chiffre)),
  };
}

/** Vérifie qu'un objet a la forme d'une enveloppe chiffrée connue. */
export function estEnveloppe(x) {
  return Boolean(x && x.format === FORMAT_CHIFFRE && x.version === 1 && x.kdf?.sel && x.chiffrement?.iv && x.donnees);
}

/**
 * Déchiffre une enveloppe. Lève une erreur lisible si le mot de passe est faux
 * (l'étiquette GCM ne correspond pas) ou si le fichier est altéré.
 */
export async function dechiffrer(enveloppe, motDePasseOuCle) {
  if (!estEnveloppe(enveloppe)) throw new Error('Fichier non reconnu : ce n’est pas une sauvegarde chiffrée de « Mes portefeuilles ».');
  if (enveloppe.kdf.nom !== 'PBKDF2' || enveloppe.kdf.hachage !== 'SHA-256' || enveloppe.chiffrement.nom !== 'AES-256-GCM') {
    throw new Error('Méthode de chiffrement non prise en charge.');
  }
  const iterations = Number(enveloppe.kdf.iterations);
  if (!Number.isInteger(iterations) || iterations < 100000 || iterations > 10000000) throw new Error('Paramètres de chiffrement invalides.');
  const base = typeof motDePasseOuCle === 'string' ? await cleDeBase(motDePasseOuCle) : motDePasseOuCle;
  const cle = await deriver(base, depuisBase64(enveloppe.kdf.sel), iterations);
  let clair;
  try {
    clair = await sub().decrypt({ name: 'AES-GCM', iv: depuisBase64(enveloppe.chiffrement.iv) }, cle, depuisBase64(enveloppe.donnees));
  } catch {
    throw new Error('Mot de passe incorrect ou fichier altéré.');
  }
  return JSON.parse(new TextDecoder().decode(clair));
}
