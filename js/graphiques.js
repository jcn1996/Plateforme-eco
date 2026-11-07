/* ==========================================================================
   Graphiques interactifs TradingView (widgets gratuits et officiels, sans compte ni clé)
   --------------------------------------------------------------------------
   - graphiqueAvance : bougies, période de 1 jour à 5 ans, moyennes mobiles 50 et
     200 jours, volume (fiche entreprise, fiche pays, panneau du bandeau des marchés) ;
   - graphiqueMini   : mini-graphique sur 12 mois (écrans Pépites et Mes analyses) ;
   - ouvrirGraphiqueMarche : panneau ouvert depuis la bulle du bandeau des marchés.

   Rien n'est chargé au démarrage : le script de TradingView est téléchargé quand un
   graphique devient visible à l'écran. En mode ⚡, ou si le widget gratuit n'affiche
   pas le symbole, un graphique simple est tracé avec Lightweight Charts (bibliothèque
   open source de TradingView) à partir des cours déjà récupérés par nos agents.
   ========================================================================== */

import { el } from './outils.js';
import {
  versTradingView, disponibleDansWidget, lienTradingView, SYMBOLES, CONTRATS_A_TERME, INDICES_BANDEAU, MENTION_CFD,
} from './symboles-tradingview.js';

const SCRIPT_TV = 'https://s3.tradingview.com/tv.js';
const SCRIPT_MINI = 'https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js';
// Lightweight Charts (licence Apache 2.0), version fixée
const SCRIPT_LWC = 'https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js';

/** Couleurs du thème « salle de contrôle » (identiques aux variables CSS). */
const THEME = {
  fond: '#0a1428',
  grille: 'rgba(0, 229, 255, 0.06)',
  bord: 'rgba(0, 229, 255, 0.16)',
  texte: '#8aa6ba',
  cyan: '#00e5ff',
  vert: '#2ee59d',
  rouge: '#ff4d6a',
  mm50: '#ffb547',
  mm200: '#9a78ee',
};

/** Périodes proposées : [code TradingView, libellé, intervalle des bougies]. */
const PERIODES = [
  ['1D', '1 J', '5'],
  ['5D', '5 J', '30'],
  ['1M', '1 M', 'D'],
  ['3M', '3 M', 'D'],
  ['6M', '6 M', 'D'],
  ['12M', '1 A', 'D'],
  ['60M', '5 A', 'D'],
];
/** Périodes couvertes par nos propres cours (environ un an) : graphique simple. */
const JOURS_SECOURS = { '1M': 31, '3M': 92, '6M': 183, '12M': 366 };

const MENTION = 'Graphique fourni par TradingView';

/* ------------------------------------------------------------------ outils */

const scripts = new Map();
/** Charge un script externe une seule fois (promesse partagée ; nouvel essai après un échec). */
function chargerScript(src) {
  if (!scripts.has(src)) {
    scripts.set(src, new Promise((resoudre, rejeter) => {
      const s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.onload = resoudre;
      s.onerror = () => { scripts.delete(src); s.remove(); rejeter(new Error(`script indisponible : ${src}`)); };
      document.head.append(s);
    }));
  }
  return scripts.get(src);
}

export const modeLeger = () => document.body.classList.contains('mode-leger');

/** Exécute `action` la première fois que le nœud devient visible (chargement paresseux). */
function quandVisible(noeud, action) {
  if (!('IntersectionObserver' in window)) { requestAnimationFrame(action); return; }
  const obs = new IntersectionObserver((entrees) => {
    if (entrees.some((e) => e.isIntersecting)) {
      obs.disconnect();
      action();
    }
  }, { rootMargin: '120px 0px' });
  obs.observe(noeud);
}

let compteur = 0;

function mention(tv) {
  return el('p', { class: 'graphique-mention' },
    el('a', { href: 'https://fr.tradingview.com/', target: '_blank', rel: 'noopener' }, MENTION),
    tv ? [' · ', el('a', { href: lienTradingView(tv), target: '_blank', rel: 'noopener' }, 'Ouvrir sur TradingView ↗')] : null);
}

/** Moyenne mobile simple d'une série [{time, value}]. */
function moyenneMobile(points, n) {
  const res = [];
  let somme = 0;
  points.forEach((p, i) => {
    somme += p.value;
    if (i >= n) somme -= points[i - n].value;
    if (i >= n - 1) res.push({ time: p.time, value: somme / n });
  });
  return res;
}

/* ------------------------------------------------------------------ graphique simple (secours) */

/**
 * Trace un graphique simple (aire + moyennes mobiles) avec Lightweight Charts.
 * @param {HTMLElement} zone
 * @param {() => Promise<Array<[string, number]>|null>} historique  clôtures [[date ISO, clôture]]
 * @param {{ raison: string, mini?: boolean, periode?: string }} options
 * @returns {Promise<{ definirPeriode(code: string): void } | null>}
 */
async function graphiqueSecours(zone, historique, { raison, mini = false, periode = '12M' }) {
  zone.classList.add('graphique-zone--secours');
  zone.replaceChildren(el('p', { class: 'graphique-attente' }, 'Chargement du graphique simple…'));
  let serie = null;
  try {
    [serie] = await Promise.all([historique?.(), chargerScript(SCRIPT_LWC)]);
  } catch {
    serie = null;
  }
  if (!zone.isConnected) return null;
  const points = (serie ?? []).filter((p) => p && p[1] > 0).map(([d, c]) => ({ time: d, value: c }));
  if (!points.length || !window.LightweightCharts) {
    zone.classList.add('graphique-zone--vide');
    zone.replaceChildren(el('p', { class: 'graphique-attente' },
      window.LightweightCharts ? 'Historique de cours pas encore disponible (il sera publié par la prochaine exécution de l’agent).'
        : 'Graphique indisponible hors connexion.'));
    return null;
  }
  const cadre = el('div', { class: 'graphique-lwc' });
  zone.replaceChildren(cadre, mini ? null : el('p', { class: 'graphique-note' }, raison));
  const LWC = window.LightweightCharts;
  const graphique = LWC.createChart(cadre, {
    autoSize: true,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: THEME.texte, fontFamily: 'IBM Plex Mono, monospace', fontSize: 11, attributionLogo: false },
    grid: { vertLines: { color: THEME.grille }, horzLines: { color: THEME.grille } },
    rightPriceScale: { borderColor: THEME.bord, visible: !mini },
    leftPriceScale: { visible: false },
    timeScale: { borderColor: THEME.bord, visible: !mini, fixLeftEdge: true, fixRightEdge: true },
    crosshair: { mode: 0 },
    localization: { locale: 'fr-FR', dateFormat: 'dd/MM/yy' },
    handleScroll: !mini, handleScale: !mini,
  });
  const hausse = points.at(-1).value >= points[0].value;
  const couleur = mini ? (hausse ? THEME.vert : THEME.rouge) : THEME.cyan;
  graphique.addAreaSeries({
    lineColor: couleur, lineWidth: 2, topColor: `${couleur}40`, bottomColor: `${couleur}00`,
    priceLineVisible: false, lastValueVisible: !mini,
  }).setData(points);
  if (!mini) {
    // Moyennes mobiles 50 et 200 jours (10 et 40 semaines pour une série hebdomadaire)
    const ecart = points.length > 1 ? (Date.parse(points.at(-1).time) - Date.parse(points[0].time)) / 86400000 / (points.length - 1) : 1;
    const hebdo = ecart > 4;
    for (const [jours, c] of [[50, THEME.mm50], [200, THEME.mm200]]) {
      const n = hebdo ? Math.round(jours / 5) : jours;
      if (points.length > n) {
        graphique.addLineSeries({ color: c, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
          .setData(moyenneMobile(points, n));
      }
    }
  }
  const definirPeriode = (code) => {
    const jours = JOURS_SECOURS[code];
    if (!jours) { graphique.timeScale().fitContent(); return; }
    const fin = points.at(-1).time;
    const debut = new Date(Date.parse(fin) - jours * 86400000).toISOString().slice(0, 10);
    graphique.timeScale().setVisibleRange({ from: debut < points[0].time ? points[0].time : debut, to: fin });
  };
  definirPeriode(periode);
  return { definirPeriode };
}

/* ------------------------------------------------------------------ graphique avancé */

/**
 * Graphique avancé TradingView : bougies, période de 1 jour à 5 ans, moyennes mobiles 50 et 200 jours, volume.
 * @param {object} o
 * @param {string} [o.yahoo]  symbole Yahoo (converti avec symboles-tradingview.js)
 * @param {string} [o.tv]     symbole TradingView déjà connu (prioritaire)
 * @param {string} [o.place]  place d'une action américaine (NASDAQ, NYSE…) selon l'agent entreprises
 * @param {() => Promise<Array>} [o.historique]  nos clôtures, pour le graphique simple
 * @param {string} [o.periode]  période initiale (12M par défaut)
 * @param {string} [o.classe]   classe CSS supplémentaire (hauteur)
 * @param {string} [o.note]     mention affichée sous le graphique (« graphique : équivalent CFD de l'indice »…)
 * @param {string} [o.secours]  raison d'un graphique simple imposé (pas de symbole TradingView utilisable)
 */
export function graphiqueAvance({ yahoo, tv, place, historique, periode = '12M', classe = '', note, secours: imposer }) {
  const symbole = imposer ? null : (tv ?? versTradingView(yahoo, place));
  const zone = el('div', { class: 'graphique-zone' }, el('p', { class: 'graphique-attente' }, 'Le graphique se charge à l’affichage…'));
  let actif = periode;
  let secours = null; // graphique simple en cours (mode ⚡ ou symbole indisponible)

  const boutons = PERIODES.map(([code, libelle]) => el('button', {
    type: 'button', class: 'graphique-periode', 'data-periode': code, 'aria-pressed': String(code === actif),
    onclick: () => choisir(code),
  }, libelle));
  const barre = el('div', { class: 'graphique-periodes', role: 'group', 'aria-label': 'Période du graphique' }, boutons);
  const bloc = el('div', { class: `graphique-tv ${classe}`.trim() }, barre, zone,
    note ? el('p', { class: 'graphique-note graphique-note--mention' }, note) : null, mention(symbole));

  const marquer = () => boutons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.periode === actif)));

  function choisir(code) {
    actif = code;
    marquer();
    if (secours) secours.definirPeriode(code);
    else if (window.TradingView) creerWidget();
  }

  function creerWidget() {
    const [, , intervalle] = PERIODES.find(([c]) => c === actif) ?? PERIODES[5];
    const id = `graphique-tv-${++compteur}`;
    zone.replaceChildren(el('div', { id, class: 'graphique-widget' }));
    // eslint-disable-next-line no-new
    new window.TradingView.widget({
      container_id: id,
      autosize: true,
      symbol: symbole,
      interval: intervalle,
      range: actif,
      timezone: 'Europe/Paris',
      theme: 'dark',
      style: '1', // bougies
      locale: 'fr',
      backgroundColor: THEME.fond,
      gridColor: THEME.grille,
      toolbar_bg: THEME.fond,
      hide_top_toolbar: true,
      hide_side_toolbar: true,
      hide_legend: false,
      withdateranges: false,
      allow_symbol_change: false,
      save_image: false,
      enable_publishing: false,
      details: false,
      calendar: false,
      // Moyennes mobiles 50 et 200 jours sur les bougies quotidiennes (le volume est affiché par défaut)
      studies: intervalle === 'D' ? [
        { id: 'MASimple@tv-basicstudies', inputs: { length: 50 } },
        { id: 'MASimple@tv-basicstudies', inputs: { length: 200 } },
      ] : [],
    });
  }

  async function basculerSecours(raison) {
    barre.querySelectorAll('.graphique-periode').forEach((b) => { b.hidden = !JOURS_SECOURS[b.dataset.periode]; });
    if (!JOURS_SECOURS[actif]) { actif = '12M'; marquer(); }
    secours = await graphiqueSecours(zone, historique, { raison, periode: actif });
  }

  quandVisible(bloc, () => {
    if (imposer) return basculerSecours(imposer);
    if (!symbole) return basculerSecours('Symbole inconnu de TradingView : graphique simple tracé avec nos cours (Yahoo Finance).');
    if (modeLeger()) return basculerSecours('Mode ⚡ : graphique simple tracé avec nos cours (Yahoo Finance), sans le widget TradingView.');
    if (!disponibleDansWidget(symbole)) {
      return basculerSecours('Ce symbole n’est pas affiché par le widget gratuit de TradingView : graphique simple tracé avec nos cours (Yahoo Finance).');
    }
    chargerScript(SCRIPT_TV).then(creerWidget)
      .catch(() => basculerSecours('TradingView injoignable : graphique simple tracé avec nos cours (Yahoo Finance).'));
    return undefined;
  });
  return bloc;
}

/* ------------------------------------------------------------------ mini-graphique */

/**
 * Mini-graphique sur 12 mois (widget « Mini Symbol Overview » de TradingView).
 * Mêmes paramètres que graphiqueAvance.
 */
export function graphiqueMini({ yahoo, tv, place, historique }) {
  const symbole = tv ?? versTradingView(yahoo, place);
  const zone = el('div', { class: 'graphique-zone graphique-zone--mini' });
  const bloc = el('div', { class: 'graphique-tv graphique-tv--mini' }, zone, mention(symbole));
  quandVisible(bloc, () => {
    if (!symbole || modeLeger() || !disponibleDansWidget(symbole)) {
      graphiqueSecours(zone, historique, { mini: true, raison: '' });
      return;
    }
    const conteneur = el('div', { class: 'tradingview-widget-container' }, el('div', { class: 'tradingview-widget-container__widget' }));
    const script = document.createElement('script');
    script.src = SCRIPT_MINI;
    script.async = true;
    script.textContent = JSON.stringify({
      symbol: symbole,
      width: '100%',
      height: '100%',
      locale: 'fr',
      dateRange: '12M',
      colorTheme: 'dark',
      isTransparent: true,
      autosize: true,
      largeChartUrl: '',
      noTimeScale: false,
      chartOnly: false,
      trendLineColor: THEME.cyan,
      underLineColor: 'rgba(0, 229, 255, 0.18)',
      underLineBottomColor: 'rgba(0, 229, 255, 0)',
    });
    script.onerror = () => graphiqueSecours(zone, historique, { mini: true, raison: '' });
    conteneur.append(script);
    zone.replaceChildren(conteneur);
  });
  return bloc;
}

/* ------------------------------------------------------------------ séries de nos agents */

const fichiersCours = new Map();
/** Clôtures d'un symbole dans data/cours/<fichier>.json (lu une seule fois, à la demande). */
export function historiqueFichier(fichier, symbole) {
  return async () => {
    if (!fichiersCours.has(fichier)) {
      fichiersCours.set(fichier, fetch(`data/cours/${fichier}.json`, { cache: 'no-cache' })
        .then((r) => (r.ok ? r.json() : null))
        .then((j) => j?.donnees ?? {})
        .catch(() => { fichiersCours.delete(fichier); return {}; }));
    }
    return (await fichiersCours.get(fichier))[symbole] ?? null;
  };
}

/* ------------------------------------------------------------------ panneau du bandeau des marchés */

/**
 * Symbole à afficher pour une cotation du bandeau. Indices d'INDICES_BANDEAU : l'indice officiel,
 * sa version TradingView ou un CFD équivalent (vérifiés pour le widget gratuit), à toute heure.
 * Autres cotations : l'actif pendant les heures de marché, son contrat à terme en dehors.
 */
export function symboleMarche(m) {
  const indice = INDICES_BANDEAU[m.symbole];
  if (indice?.tv) return { yahoo: m.symbole, tv: indice.tv, contrat: false, cfd: indice.type === 'cfd' };
  const enSeance = m.statut === 'ouvert';
  const contrat = m.contrat_a_terme?.symbole ?? CONTRATS_A_TERME[m.symbole];
  if (!enSeance && contrat && SYMBOLES[contrat]) {
    return { yahoo: contrat, tv: SYMBOLES[contrat], contrat: true };
  }
  return { yahoo: m.symbole, tv: versTradingView(m.symbole), contrat: false };
}

let dialogueOuvert = null;

/** Ouvre le panneau du graphique d'une cotation du bandeau (fermé = widget détruit). */
export function ouvrirGraphiqueMarche(m) {
  dialogueOuvert?.close();
  const s = symboleMarche(m);
  const fermer = () => dialogue.close();
  const dialogue = el('dialog', { class: 'panneau-graphique', 'aria-label': `Graphique : ${m.nom}` },
    el('header', { class: 'panneau-graphique-tete' },
      el('div', {},
        el('div', { class: 'panneau-graphique-nom' }, m.nom),
        el('div', { class: 'panneau-graphique-sous' }, s.contrat
          ? `Contrat à terme ${s.tv} · marché ${m.statut ?? 'fermé'}`
          : `${s.cfd ? `CFD ${s.tv}` : (s.tv ?? m.symbole)}${m.statut ? ` · marché ${m.statut}` : ''}`),
      ),
      el('button', { type: 'button', class: 'bouton bouton--icone', title: 'Fermer', onclick: fermer },
        el('span', { 'aria-hidden': 'true' }, '✕'), el('span', { class: 'visuellement-cache' }, 'Fermer')),
    ),
    graphiqueAvance({
      yahoo: s.yahoo, tv: s.tv, historique: historiqueFichier('marches', m.symbole), classe: 'graphique-tv--panneau',
      note: s.cfd ? MENTION_CFD : undefined,
    }),
  );
  dialogue.addEventListener('close', () => { dialogue.remove(); if (dialogueOuvert === dialogue) dialogueOuvert = null; });
  // Toucher le fond sombre ferme le panneau
  dialogue.addEventListener('click', (e) => { if (e.target === dialogue) fermer(); });
  document.body.append(dialogue);
  dialogueOuvert = dialogue;
  if (typeof dialogue.showModal === 'function') dialogue.showModal(); else dialogue.setAttribute('open', '');
  return dialogue;
}
