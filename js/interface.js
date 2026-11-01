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
 * Il réunit les alertes des agents et « Mes alertes » (règles personnelles déclenchées),
 * ces dernières en tête avec un badge.
 * @param {(route:object) => void} ouvrir  appelé quand on touche une alerte
 */
export function initialiserAlertes({ bouton, liste, compte, apercu }, paysParCode, ouvrir) {
  const replier = () => {
    bouton.setAttribute('aria-expanded', 'false');
    liste.hidden = true;
    apercu.hidden = false;
    document.body.classList.remove('alertes-ouvertes');
  };
  bouton.addEventListener('click', () => {
    const ouvert = bouton.getAttribute('aria-expanded') === 'true';
    bouton.setAttribute('aria-expanded', String(!ouvert));
    liste.hidden = ouvert;
    apercu.hidden = !ouvert;
    document.body.classList.toggle('alertes-ouvertes', !ouvert); // masque la barre du comparateur
  });

  /** (Re)construit la liste : mes alertes d'abord, puis celles des agents (plus récentes en premier). */
  function afficher(alertesAgents, mesAlertes = []) {
    const agents = [...alertesAgents].sort((a, b) => b.heure.localeCompare(a.heure));
    const toutes = [...mesAlertes, ...agents];
    compte.textContent = String(toutes.length);
    apercu.textContent = toutes[0] ? `${toutes[0].perso ? 'Mon alerte' : toutes[0].heure} · ${toutes[0].titre}` : '';

    const ligne = (a) => el('li', {},
      el('button', {
        class: `alerte ${classeNote(NOTE_NIVEAU[a.niveau] ?? 57)}${a.perso ? ' alerte--perso' : ''}`,
        type: 'button',
        onclick: () => { replier(); ouvrir(a.route ?? { type: 'pays', id: a.pays }); },
      },
        el('span', { class: 'alerte-heure mono' }, a.heure),
        el('span', { class: 'alerte-entete' },
          a.perso ? el('span', { class: 'badge-mon-alerte' }, 'Mon alerte') : el('span', {}, AGENTS[a.agent] ?? a.agent),
          a.perso ? null : el('span', {}, '·'),
          a.perso ? null : el('span', {}, paysParCode.get(a.pays)?.nom ?? a.pays),
        ),
        el('span', { class: 'alerte-titre' }, a.titre),
        el('span', { class: 'alerte-texte' }, a.texte),
      ),
    );
    liste.replaceChildren(
      el('li', { class: 'alertes-outils' },
        el('button', { class: 'bouton bouton--plein', type: 'button', onclick: () => { replier(); ouvrir({ type: 'mes-alertes' }); } },
          '🔔 Gérer mes alertes'),
      ),
      ...toutes.map(ligne),
    );
  }
  return { replier, afficher };
}

/* ---------- Filtres du globe (ce que représentent les couleurs) ---------- */
const CLE_METRIQUE = 'salle-controle:metrique';
const CLE_FLUX = 'salle-controle:flux';

export function lirePreference(cle, defaut) {
  try { return localStorage.getItem(cle) ?? defaut; } catch { return defaut; }
}
export function memoriserPreference(cle, valeur) {
  try { localStorage.setItem(cle, valeur); } catch { /* stockage indisponible */ }
}

/**
 * Puces horizontales défilantes : une par métrique, plus un bouton « Flux ».
 * Le choix est mémorisé sur l'appareil.
 */
export function initialiserFiltres({ puces, boutonFlux }, metriques, { surMetrique, surFlux }) {
  let active = lirePreference(CLE_METRIQUE, 'note');
  if (!metriques.some((m) => m.cle === active)) active = 'note';
  let flux = lirePreference(CLE_FLUX, '1') === '1';

  const boutons = metriques.map((m) => el('button', {
    class: 'puce', type: 'button', role: 'radio', 'data-cle': m.cle,
    onclick: () => choisir(m.cle),
  }, m.libelle));
  puces.replaceChildren(...boutons);

  function choisir(cle, initial = false) {
    active = cle;
    boutons.forEach((b) => b.setAttribute('aria-checked', String(b.dataset.cle === cle)));
    if (!initial) {
      memoriserPreference(CLE_METRIQUE, cle);
      boutons.find((b) => b.dataset.cle === cle)?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
    }
    surMetrique(cle, initial);
  }
  function basculerFlux(initial = false) {
    boutonFlux.setAttribute('aria-pressed', String(flux));
    if (!initial) memoriserPreference(CLE_FLUX, flux ? '1' : '0');
    surFlux(flux, initial);
  }
  boutonFlux.addEventListener('click', () => { flux = !flux; basculerFlux(); });
  choisir(active, true);
  basculerFlux(true);
  return { metriqueActive: () => active, fluxVisibles: () => flux };
}

/* ---------- Notification temporaire ---------- */
let minuterieNotification = null;
export function notifier(texte) {
  const n = document.getElementById('notification');
  n.textContent = texte;
  n.hidden = false;
  clearTimeout(minuterieNotification);
  minuterieNotification = setTimeout(() => { n.hidden = true; }, 3200);
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
