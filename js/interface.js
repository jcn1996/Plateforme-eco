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

const CATEGORIES = { indices: 'Indice', taux: 'Taux', devises: 'Devise', matieres_premieres: 'Mat. 1res', crypto: 'Crypto' };

/** Nombre de décimales selon le type de cotation. */
function decimalesMarche(m) {
  if (m.categorie === 'devises') return 4;
  if (m.categorie === 'crypto') return 0;
  return m.valeur > 1000 ? 1 : 2;
}

/** Valeur formatée avec son unité : « 2 684,5 $/once », « 1,0912 », « 22 840,5 ». */
function valeurMarche(m) {
  const unite = !m.unite || m.unite === 'pts' ? '' : ` ${m.unite}`;
  return nombre(m.valeur, decimalesMarche(m)) + unite;
}

/** Variation signée, ou « n. d. » si elle n'est pas connue. */
function texteVariation(v, decimales) {
  return v == null ? 'n. d.' : variation(v, decimales);
}

/** Heure d'un cours : « 17:34 » si c'est aujourd'hui, sinon « 31/10 17:34 » (heure locale). */
function heureCours(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const heure = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  return d.toDateString() === new Date().toDateString()
    ? heure : `${d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })} ${heure}`;
}

/* Réglages du bandeau */
const VITESSE_AUTO = 32;      // défilement automatique, en pixels par seconde
const REPRISE_APRES = 4000;   // reprise du défilement auto après un toucher (ms)

/**
 * Bandeau des marchés : défilement automatique, mais manipulable au doigt
 * (glisser à gauche ou à droite, avec inertie) et à la souris (pause au
 * survol, glisser possible). Toucher une cotation affiche une petite bulle
 * (cours, variation du jour, variation sur 1 an, heure, source et statut du marché).
 * Le contenu est dupliqué pour boucler sans à-coup.
 */
export function remplirBandeau(piste, marches) {
  const bandeau = piste.parentElement;
  const ouvert = (m) => m.statut === 'ouvert';
  const cotation = (m, copie) => el('button', {
    class: 'cotation', type: 'button', tabindex: copie ? '-1' : undefined, 'aria-hidden': copie ? 'true' : undefined,
    'data-nom': m.nom,
    'aria-label': `${m.nom} : ${valeurMarche(m)}, ${texteVariation(m.variation, 2)} aujourd'hui, ${texteVariation(m.variation_1an, 1)} sur un an`
      + (m.statut ? `, marché ${m.statut}` : ''),
  },
    el('span', { class: 'cotation-cat' }, CATEGORIES[m.categorie] ?? ''),
    el('span', { class: 'cotation-nom' }, m.nom),
    m.statut ? el('span', { class: `cotation-statut${ouvert(m) ? ' cotation-statut--ouvert' : ''}` }, ouvert(m) ? 'ouvert' : 'fermé') : null,
    el('span', { class: 'cotation-valeur mono' }, valeurMarche(m)),
    m.variation == null ? null
      : el('span', { class: `mono ${m.variation >= 0 ? 'hausse' : 'baisse'}` }, `${m.variation >= 0 ? '▲' : '▼'} ${variation(m.variation, 2)}`),
  );
  piste.replaceChildren(...marches.map((m) => cotation(m, false)), ...marches.map((m) => cotation(m, true)));
  const parNom = new Map(marches.map((m) => [m.nom, m]));

  // --- État du défilement ---
  let decalage = 0;            // en pixels (la piste est translatée vers la gauche)
  let elan = 0;                // vitesse d'inertie après un glisser (px/s)
  let glisse = null;           // { x, t, depart, cible, deplace } pendant un glisser
  let pauseJusqua = 0;         // horodatage de reprise du défilement auto
  let survol = false;          // souris au-dessus du bandeau
  let precedent = performance.now();
  const reduireAnimations = matchMedia('(prefers-reduced-motion: reduce)');
  const largeurSerie = () => piste.scrollWidth / 2;

  const boucle = (maintenant) => {
    requestAnimationFrame(boucle);
    const dt = Math.min(0.5, (maintenant - precedent) / 1000);
    precedent = maintenant;
    if (document.hidden || !bandeau.offsetParent) return; // bandeau masqué : rien à faire
    if (!glisse) {
      if (Math.abs(elan) > 8) {
        decalage += elan * dt;                // inertie après un glisser
        elan *= Math.exp(-dt * 3.2);
      } else if (!survol && maintenant > pauseJusqua && !reduireAnimations.matches) {
        decalage += VITESSE_AUTO * dt;        // défilement automatique
      }
    }
    const L = largeurSerie();
    if (L > 0) decalage = ((decalage % L) + L) % L;
    piste.style.transform = `translate3d(${-decalage.toFixed(1)}px, 0, 0)`;
  };
  requestAnimationFrame(boucle);

  bandeau.addEventListener('pointerdown', (e) => {
    if (e.button > 0) return;
    glisse = { x: e.clientX, t: performance.now(), depart: e.clientX, cible: e.target.closest('.cotation'), deplace: false, id: e.pointerId };
    elan = 0;
    pauseJusqua = Infinity;
    bandeau.setPointerCapture(e.pointerId);
  });
  bandeau.addEventListener('pointermove', (e) => {
    if (!glisse || e.pointerId !== glisse.id) return;
    const maintenant = performance.now();
    const dx = e.clientX - glisse.x;
    if (Math.abs(e.clientX - glisse.depart) > 6) glisse.deplace = true;
    decalage -= dx;
    const vitesse = (-dx / Math.max(1, maintenant - glisse.t)) * 1000;
    elan = elan * 0.5 + vitesse * 0.5;
    glisse.x = e.clientX;
    glisse.t = maintenant;
  });
  const relacher = (e) => {
    if (!glisse || e.pointerId !== glisse.id) return;
    if (performance.now() - glisse.t > 90) elan = 0; // doigt arrêté avant le lâcher : pas d'élan
    const { cible, deplace } = glisse;
    glisse = null;
    pauseJusqua = performance.now() + REPRISE_APRES;
    if (!deplace && cible && e.type === 'pointerup') afficherBulle(cible);
  };
  bandeau.addEventListener('pointerup', relacher);
  bandeau.addEventListener('pointercancel', relacher);
  bandeau.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') survol = true; });
  bandeau.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') survol = false; });
  // Clavier : Entrée ou Espace sur une cotation affiche aussi la bulle
  bandeau.addEventListener('click', (e) => { if (e.detail === 0 && e.target.closest('.cotation')) afficherBulle(e.target.closest('.cotation')); });

  // --- Bulle d'information ---
  let bulle = null, minuterie = null;
  const fermerBulle = () => { bulle?.remove(); bulle = null; clearTimeout(minuterie); };
  function afficherBulle(element) {
    const m = parNom.get(element.dataset.nom);
    if (!m) return;
    fermerBulle();
    const ligne = (libelle, v, decimales) => el('div', { class: 'bulle-marche-ligne' },
      el('span', {}, libelle),
      el('span', { class: v == null ? 'mono' : `mono ${v >= 0 ? 'hausse' : 'baisse'}` }, texteVariation(v, decimales)));
    bulle = el('div', { class: 'bulle-marche', role: 'status' },
      el('div', { class: 'bulle-marche-nom' }, m.nom),
      el('div', { class: 'bulle-marche-valeur mono' }, valeurMarche(m)),
      ligne('Aujourd’hui', m.variation, 2),
      ligne('Sur 1 an', m.variation_1an, 1),
      m.heure || m.source ? el('div', { class: 'bulle-marche-pied' },
        m.heure ? `Cours de ${heureCours(m.heure)}` : null,
        m.heure && m.source ? ' · ' : null,
        m.source ?? null,
        m.statut ? ` · marché ${m.statut}` : null,
        m.ancienne ? el('div', { class: 'bulle-marche-ancienne' }, 'Valeur ancienne : sources indisponibles') : null,
      ) : null,
    );
    document.body.append(bulle);
    const r = element.getBoundingClientRect();
    const largeur = bulle.offsetWidth;
    bulle.style.left = `${Math.min(Math.max(8, r.left + r.width / 2 - largeur / 2), innerWidth - largeur - 8)}px`;
    bulle.style.top = `${r.bottom + 6}px`;
    minuterie = setTimeout(fermerBulle, 5000);
  }
  document.addEventListener('pointerdown', (e) => { if (bulle && !bandeau.contains(e.target)) fermerBulle(); });
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

  /**
   * (Re)construit la liste : alertes « Qualité des données » d'abord, puis mes alertes,
   * puis celles des agents (plus récentes en premier).
   */
  function afficher(alertesAgents, mesAlertes = [], alertesQualite = []) {
    const agents = [...alertesAgents].sort((a, b) => b.heure.localeCompare(a.heure));
    const toutes = [...alertesQualite, ...mesAlertes, ...agents];
    compte.textContent = String(toutes.length);
    const prefixe = (a) => (a.qualite ? 'Qualité des données' : a.perso ? 'Mon alerte' : a.heure);
    apercu.textContent = toutes[0] ? `${prefixe(toutes[0])} · ${toutes[0].titre}` : '';

    const ligne = (a) => el('li', {},
      el('button', {
        class: `alerte ${classeNote(NOTE_NIVEAU[a.niveau] ?? 57)}${a.perso ? ' alerte--perso' : ''}${a.qualite ? ' alerte--qualite' : ''}`,
        type: 'button',
        onclick: () => { replier(); ouvrir(a.route ?? { type: 'pays', id: a.pays }); },
      },
        el('span', { class: 'alerte-heure mono' }, a.heure),
        el('span', { class: 'alerte-entete' },
          a.qualite ? el('span', { class: 'badge-qualite' }, 'Qualité des données')
            : a.perso ? el('span', { class: 'badge-mon-alerte' }, 'Mon alerte') : el('span', {}, AGENTS[a.agent] ?? a.agent),
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
