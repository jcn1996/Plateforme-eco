/* ==========================================================================
   Outils partagés : couleurs des notes, formatage des nombres en français,
   création d'éléments HTML.
   ========================================================================== */

/** Seuils de couleur des notes (sur 100). */
export const SEUIL_ATTRACTIF = 65;
export const SEUIL_NEUTRE = 50;

/** Couleurs en hexadécimal (utilisées par Three.js). Identiques aux variables CSS. */
export const COULEURS = {
  attractif: 0x2ee59d,
  neutre: 0xffb547,
  defavorable: 0xff4d6a,
};

/** Noms lisibles des agents IA (clé utilisée dans les JSON → libellé affiché). */
export const AGENTS = {
  macro: 'Agent macro',
  pays: 'Agent pays',
  entreprises: 'Agent entreprises',
  donnees_alternatives: 'Agent données alternatives',
  sentiment: 'Agent sentiment',
  risque: 'Agent risque',
  chef_orchestre: "Chef d'orchestre",
  trader: 'Agent trader',
};

/** Renvoie le niveau d'une note : « attractif », « neutre » ou « defavorable ». */
export function niveauNote(note) {
  if (note >= SEUIL_ATTRACTIF) return 'attractif';
  if (note >= SEUIL_NEUTRE) return 'neutre';
  return 'defavorable';
}

/** Libellé affiché pour un niveau. */
export function libelleNiveau(niveau) {
  return { attractif: 'Attractif', neutre: 'Neutre', defavorable: 'Défavorable' }[niveau] ?? niveau;
}

/** Classe CSS qui fixe la variable --c-note selon la note. */
export function classeNote(note) {
  return `note--${niveauNote(note)}`;
}

/* ---------- Formatage des nombres (format français : virgule décimale, espace fine) ---------- */
const cacheFormats = new Map();
function formateur(decimales) {
  if (!cacheFormats.has(decimales)) {
    cacheFormats.set(decimales, new Intl.NumberFormat('fr-FR', {
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales,
    }));
  }
  return cacheFormats.get(decimales);
}

/** Formate un nombre avec un nombre fixe de décimales. */
export function nombre(valeur, decimales = 0) {
  return formateur(decimales).format(valeur);
}

/** Formate une variation avec son signe : +1,2 % ou −0,4 %. */
export function variation(valeur, decimales = 2, unite = ' %') {
  const signe = valeur > 0 ? '+' : valeur < 0 ? '−' : '';
  return `${signe}${nombre(Math.abs(valeur), decimales)}${unite}`;
}

/** Formate un montant en euros, sans décimale : 112 465 €. */
export function euros(valeur) {
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(valeur);
}

/**
 * Formate la valeur d'un indicateur en fonction de son unité.
 * Les indicateurs de variation (devise, PER relatif…) affichent leur signe.
 */
export function valeurIndicateur(cle, ind) {
  const signe = ['devise_3m', 'per_vs_secteur', 'croissance_ca', 'benefice', 'flux_etrangers'].includes(cle);
  switch (ind.unite) {
    case '%':
      return signe ? variation(ind.valeur, cle === 'per_vs_secteur' ? 0 : 1) : `${nombre(ind.valeur, 1)} %`;
    case 'x':
      return `${nombre(ind.valeur, 1)}×`;
    case 'Md€':
      return `${variation(ind.valeur, 1, '')} Md€`;
    default:
      return `${nombre(ind.valeur, 1)} ${ind.unite ?? ''}`.trim();
  }
}

/** Formate une date ISO (AAAA-MM-JJ) en « 30 oct. 2026 ». */
export function dateCourte(iso) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
}

/* ---------- Création d'éléments HTML ---------- */

/**
 * Crée un élément HTML.
 *   el('button', { class: 'bouton', onclick: f }, 'Texte', autreElement)
 * Le texte est toujours inséré comme texte (jamais interprété comme du HTML),
 * ce qui protège contre l'injection de code si les agents produisent du texte inattendu.
 */
export function el(balise, attributs = {}, ...enfants) {
  const noeud = document.createElement(balise);
  for (const [cle, valeur] of Object.entries(attributs ?? {})) {
    if (valeur === undefined || valeur === null || valeur === false) continue;
    if (cle.startsWith('on') && typeof valeur === 'function') {
      noeud.addEventListener(cle.slice(2), valeur);
    } else if (cle === 'style' && typeof valeur === 'object') {
      for (const [prop, v] of Object.entries(valeur)) {
        if (prop.startsWith('--')) noeud.style.setProperty(prop, v); // variable CSS
        else noeud.style[prop] = v;
      }
    } else if (valeur === true) {
      noeud.setAttribute(cle, '');
    } else {
      noeud.setAttribute(cle, valeur);
    }
  }
  ajouterEnfants(noeud, enfants);
  return noeud;
}

function ajouterEnfants(noeud, enfants) {
  for (const enfant of enfants.flat(Infinity)) {
    if (enfant === null || enfant === undefined || enfant === false) continue;
    noeud.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
}

/** Crée un élément SVG (même principe que el). */
export function svg(balise, attributs = {}, ...enfants) {
  const noeud = document.createElementNS('http://www.w3.org/2000/svg', balise);
  for (const [cle, valeur] of Object.entries(attributs ?? {})) {
    if (valeur !== undefined && valeur !== null) noeud.setAttribute(cle, valeur);
  }
  ajouterEnfants(noeud, enfants);
  return noeud;
}

/* ---------- Métriques (filtres du globe, comparateur, alertes personnalisées) ---------- */

/**
 * Ce que peuvent représenter les couleurs du globe.
 * « source » indique où lire la valeur dans un pays :
 *   - 'note' : la note globale
 *   - 'indicateur' : p.indicateurs[cle]
 *   - 'momentum' : p.momentum_boursier
 */
export const METRIQUES_PAYS = [
  { cle: 'note', libelle: 'Note globale', court: 'Note', source: 'note' },
  { cle: 'croissance_pib', libelle: 'Croissance PIB', court: 'PIB', source: 'indicateur' },
  { cle: 'inflation', libelle: 'Inflation', court: 'Inflation', source: 'indicateur' },
  { cle: 'per', libelle: 'Valorisation (PER)', court: 'PER', source: 'indicateur' },
  { cle: 'devise_3m', libelle: 'Devise 3 mois', court: 'Devise', source: 'indicateur' },
  { cle: 'flux_etrangers', libelle: 'Flux étrangers', court: 'Flux', source: 'indicateur' },
  { cle: 'momentum', libelle: 'Momentum boursier', court: 'Momentum', source: 'momentum' },
];

/** Indicateurs disponibles pour une entreprise (note globale + 5 indicateurs). */
export const METRIQUES_ENTREPRISE = [
  { cle: 'note', libelle: 'Note globale', source: 'note' },
  { cle: 'croissance_ca', libelle: 'Croissance du CA', source: 'indicateur' },
  { cle: 'benefice', libelle: 'Bénéfice (évol. 1 an)', source: 'indicateur' },
  { cle: 'marge', libelle: 'Marge opérationnelle', source: 'indicateur' },
  { cle: 'dette_ebitda', libelle: 'Dette nette / EBITDA', source: 'indicateur' },
  { cle: 'per_vs_secteur', libelle: 'PER vs secteur', source: 'indicateur' },
];

export function metrique(type, cle) {
  return (type === 'entreprise' ? METRIQUES_ENTREPRISE : METRIQUES_PAYS).find((m) => m.cle === cle);
}

/**
 * Lit une métrique sur un pays ou une entreprise.
 * Renvoie { valeur, note, texte, unite } ou null si absente.
 */
export function lireMetrique(element, cle) {
  if (cle === 'note') return { valeur: element.note, note: element.note, texte: nombre(element.note), unite: '/100' };
  if (cle === 'momentum') {
    const m = element.momentum_boursier;
    return m ? { valeur: m.valeur, note: m.note, texte: variation(m.valeur, 1), unite: '%' } : null;
  }
  const ind = element.indicateurs?.[cle];
  return ind ? { valeur: ind.valeur, note: ind.note, texte: valeurIndicateur(cle, ind), unite: ind.unite } : null;
}
