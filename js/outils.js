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
  // « || 0 » évite l'affichage de « -0 » pour les très petites valeurs négatives arrondies
  return formateur(decimales).format(Number(Number(valeur).toFixed(decimales)) || 0);
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
  const signe = ['devise_3m', 'per_vs_secteur', 'croissance_ca', 'benefice', 'flux_etrangers', 'taux_reel', 'valorisation', 'momentum'].includes(cle);
  if (cle === 'pmi') return nombre(ind.valeur, 1);
  if (cle === 'valorisation') return variation(ind.valeur, 0);
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

/**
 * Petit complément affiché sous la valeur d'un indicateur :
 * cible d'inflation, direction de la banque centrale, PER et sa moyenne…
 */
export function complementIndicateur(cle, ind) {
  if (cle === 'inflation') return ind.cible != null ? `cible ${nombre(ind.cible, ind.cible % 1 ? 1 : 0)} %` : 'sans cible officielle';
  if (cle === 'taux_reel') return `taux directeur ${nombre(ind.taux_directeur, 2)} % · BC : ${ind.direction}`;
  if (cle === 'valorisation') return `PER ${nombre(ind.per, 1)} vs ${nombre(ind.moyenne_10ans, 1)} (10 ans)`;
  if (cle === 'pmi') return ind.valeur >= 50 ? 'expansion (> 50)' : 'contraction (< 50)';
  if (cle === 'momentum') return 'indice sur 12 mois';
  if (cle === 'croissance_pib') return 'sur un an';
  return '';
}

/**
 * Tendance depuis la mise à jour précédente : flèche ↑ ↓ → et écart.
 * La couleur suit l'évolution de la NOTE (vert = s'améliore, rouge = se dégrade),
 * car une hausse n'est pas toujours une bonne nouvelle (inflation…).
 * @returns {{ fleche, texte, sens }} ou null s'il n'y a pas de valeur précédente
 */
export function tendance(valeur, precedent, { decimales = 1, unite = '', noteActuelle, notePrecedente } = {}) {
  if (precedent === undefined || precedent === null) return null;
  const ecart = valeur - precedent;
  const seuil = 0.5 * 10 ** -decimales;
  const fleche = ecart > seuil ? '↑' : ecart < -seuil ? '↓' : '→';
  const deltaNote = noteActuelle !== undefined && notePrecedente !== undefined ? noteActuelle - notePrecedente : ecart;
  const sens = deltaNote > 0 ? 'mieux' : deltaNote < 0 ? 'moins-bien' : 'stable';
  const texte = fleche === '→' ? '=' : variation(ecart, decimales, unite);
  return { fleche, texte, sens };
}

/** Élément HTML d'une tendance (flèche + écart), ou rien. */
export function badgeTendance(t, titre = 'depuis la mise à jour précédente') {
  if (!t) return null;
  return el('span', { class: `tendance tendance--${t.sens}`, title: `${t.texte} ${titre}`, 'aria-label': `${t.fleche === '↑' ? 'en hausse' : t.fleche === '↓' ? 'en baisse' : 'stable'}, ${t.texte} ${titre}` },
    el('span', { 'aria-hidden': 'true' }, t.fleche), ` ${t.texte}`);
}

/** Tendance d'une note globale (pays, secteur, entreprise). */
export function tendanceNote(element) {
  return tendance(element.note, element.precedent?.note, { decimales: 0 });
}

/** Tendance d'un indicateur (valeur), colorée selon l'évolution de sa note. */
export function tendanceIndicateur(cle, ind) {
  if (!ind.precedent) return null;
  const decimales = ['valorisation', 'per_vs_secteur'].includes(cle) ? 0 : 1;
  // Pour un indicateur en %, l'écart s'exprime en points (pt)
  const unite = ind.unite === '%' ? ' pt' : ind.unite === 'x' ? '×' : ind.unite ? ` ${ind.unite}` : '';
  return tendance(ind.valeur, ind.precedent.valeur, { decimales, unite, noteActuelle: ind.note, notePrecedente: ind.precedent.note });
}

/** Ligne « Mis à jour le … · Source : … » à partir du bloc meta d'un fichier JSON. */
export function texteFraicheur(meta) {
  if (!meta?.genere_le) return '';
  const d = new Date(meta.genere_le);
  const date = d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
  const heure = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  return `Mis à jour le ${date} à ${heure} · Source : ${meta.source ?? 'inconnue'}`;
}

/** Texte sans accents ni majuscules, pour la recherche. */
export function normaliser(texte) {
  return String(texte).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
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
  { cle: 'pmi', libelle: 'PMI manufacturier', court: 'PMI', source: 'indicateur' },
  { cle: 'inflation', libelle: 'Inflation', court: 'Inflation', source: 'indicateur' },
  { cle: 'taux_reel', libelle: 'Taux réel', court: 'Taux réel', source: 'indicateur' },
  { cle: 'valorisation', libelle: 'Valorisation (PER vs 10 ans)', court: 'Valorisation', source: 'indicateur' },
  { cle: 'momentum', libelle: 'Momentum boursier 12 mois', court: 'Momentum', source: 'indicateur' },
];

/** Indicateurs secondaires d'un pays (section « Détail » des fiches). */
export const DETAIL_PAYS = [
  { cle: 'devise_3m', libelle: 'Devise sur 3 mois' },
  { cle: 'flux_etrangers', libelle: 'Flux étrangers' },
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
  if (cle === 'note') return { valeur: element.note, note: element.note, texte: nombre(element.note), unite: '/100', tendance: tendanceNote(element) };
  // Les indicateurs secondaires (devise, flux étrangers) restent lisibles, par ex. pour d'anciennes alertes
  const ind = element.indicateurs?.[cle] ?? element.detail?.[cle];
  return ind ? { valeur: ind.valeur, note: ind.note, texte: valeurIndicateur(cle, ind), unite: ind.unite, tendance: tendanceIndicateur(cle, ind) } : null;
}
