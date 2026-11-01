/* ==========================================================================
   Éléments fixes de l'interface : horloge, bandeau des marchés,
   bandeau des alertes du jour, bouton du mode léger.
   ========================================================================== */

import { el, nombre, variation, classeNote, AGENTS } from './outils.js';

/** Horloge en haut à droite, mise à jour chaque seconde. */
export function demarrerHorloge(noeud) {
  // Sur les petits écrans, on n'affiche pas les secondes pour gagner de la place
  const avecSecondes = matchMedia('(min-width: 400px)');
  const formats = {
    long: new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    court: new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' }),
  };
  const maj = () => {
    const d = new Date();
    noeud.textContent = (avecSecondes.matches ? formats.long : formats.court).format(d);
    noeud.dateTime = d.toISOString();
  };
  maj();
  setInterval(maj, 1000);
}

const CATEGORIES = { indices: 'Indice', taux: 'Taux', devises: 'Devise', matieres_premieres: 'Mat. 1res' };

/** Bandeau défilant : le contenu est dupliqué pour une boucle sans à-coup. */
export function remplirBandeau(piste, marches) {
  const cotation = (m) => {
    const decimales = m.categorie === 'devises' ? 4 : m.categorie === 'taux' ? 2 : m.valeur > 1000 ? 1 : 2;
    const unite = m.unite === '%' ? ' %' : m.unite && m.unite !== 'pts' ? ` ${m.unite}` : '';
    // Pour les taux, la variation est exprimée en points (pas en %)
    const varTexte = m.categorie === 'taux' ? variation(m.variation, 2, ' pt') : variation(m.variation, 2);
    return el('span', { class: 'cotation' },
      el('span', { class: 'cotation-cat' }, CATEGORIES[m.categorie] ?? ''),
      el('span', { class: 'cotation-nom' }, m.nom),
      el('span', { class: 'cotation-valeur mono' }, nombre(m.valeur, decimales) + unite),
      el('span', { class: `mono ${m.variation >= 0 ? 'hausse' : 'baisse'}` }, `${m.variation >= 0 ? '▲' : '▼'} ${varTexte}`),
    );
  };
  const serie = marches.map(cotation);
  const copie = marches.map(cotation);
  copie.forEach((c) => c.setAttribute('aria-hidden', 'true')); // la copie n'est pas lue deux fois
  piste.replaceChildren(...serie, ...copie);
}

/** Note « équivalente » à un niveau d'alerte, pour réutiliser les couleurs. */
const NOTE_NIVEAU = { attractif: 80, neutre: 57, defavorable: 30 };

/**
 * Bandeau « Alertes du jour » repliable en bas de l'écran.
 * @param {(code:string) => void} ouvrirPays  appelé quand on touche une alerte
 */
export function initialiserAlertes({ bouton, liste, compte, apercu }, alertes, paysParCode, ouvrirPays) {
  const triees = [...alertes].sort((a, b) => b.heure.localeCompare(a.heure));
  compte.textContent = String(triees.length);
  apercu.textContent = triees[0] ? `${triees[0].heure} · ${triees[0].titre}` : '';

  liste.replaceChildren(...triees.map((a) => el('li', {},
    el('button', {
      class: `alerte ${classeNote(NOTE_NIVEAU[a.niveau] ?? 57)}`,
      type: 'button',
      onclick: () => { replier(); ouvrirPays(a.pays); },
    },
      el('span', { class: 'alerte-heure mono' }, a.heure),
      el('span', { class: 'alerte-entete' },
        el('span', {}, AGENTS[a.agent] ?? a.agent),
        el('span', {}, '·'),
        el('span', {}, paysParCode.get(a.pays)?.nom ?? a.pays),
      ),
      el('span', { class: 'alerte-titre' }, a.titre),
      el('span', { class: 'alerte-texte' }, a.texte),
    ),
  )));

  const replier = () => {
    bouton.setAttribute('aria-expanded', 'false');
    liste.hidden = true;
    apercu.hidden = false;
  };
  bouton.addEventListener('click', () => {
    const ouvert = bouton.getAttribute('aria-expanded') === 'true';
    bouton.setAttribute('aria-expanded', String(!ouvert));
    liste.hidden = ouvert;
    apercu.hidden = !ouvert;
  });
  return { replier };
}

/* ---------- Mode léger (mémorisé sur l'appareil) ---------- */
const CLE_LEGER = 'salle-controle:mode-leger';

/** Lit la préférence : choix mémorisé, sinon réglage « réduire les animations » du téléphone. */
export function lireModeLeger() {
  try {
    const memorise = localStorage.getItem(CLE_LEGER);
    if (memorise !== null) return memorise === '1';
  } catch { /* stockage indisponible (navigation privée) : on ignore */ }
  return matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function memoriserModeLeger(actif) {
  try { localStorage.setItem(CLE_LEGER, actif ? '1' : '0'); } catch { /* ignoré */ }
}
