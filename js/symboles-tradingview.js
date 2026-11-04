/* ==========================================================================
   Correspondance des symboles Yahoo Finance → TradingView
   --------------------------------------------------------------------------
   Fichier fait pour être complété à la main :
   - SYMBOLES      : indices, contrats à terme, matières premières, devises,
                     crypto et exceptions manuelles (prioritaires sur tout le reste) ;
   - CONTRATS_A_TERME : contrat à terme affiché hors séance à la place d'un indice ;
   - PLACES        : suffixe Yahoo (.PA, .DE…) → place TradingView ;
   - NON_DISPONIBLES : symboles ou places que le widget gratuit de TradingView
                     n'affiche pas : l'appli trace alors un graphique simple
                     (Lightweight Charts) avec nos propres cours.
   ========================================================================== */

/** Symboles fixes et exceptions manuelles (clé = symbole Yahoo, valeur = symbole TradingView). */
export const SYMBOLES = {
  // Indices
  '^NDX': 'NASDAQ:NDX',
  '^GSPC': 'SP:SPX',
  '^FCHI': 'EURONEXT:PX1',
  '^DJI': 'DJ:DJI',
  '^GDAXI': 'XETR:DAX',
  '^STOXX50E': 'TVC:SX5E',
  '^N225': 'TVC:NI225',
  // Contrats à terme
  'NQ=F': 'CME_MINI:NQ1!',
  'ES=F': 'CME_MINI:ES1!',
  'FCE=F': 'EURONEXT:FCE1!', // contrat à terme CAC 40 (absent de Yahoo, présent sur TradingView)
  'GC=F': 'COMEX:GC1!',
  'CL=F': 'NYMEX:CL1!',
  // ETF, crypto, devises
  URTH: 'AMEX:URTH',
  'BTC-USD': 'BITSTAMP:BTCUSD',
  'EURUSD=X': 'FX:EURUSD',

  // ETF pays de l'agent pays (place exacte, pour éviter toute ambiguïté)
  SPY: 'AMEX:SPY', EWC: 'AMEX:EWC', EWW: 'AMEX:EWW', EWZ: 'AMEX:EWZ', ARGT: 'AMEX:ARGT', EWU: 'AMEX:EWU',
  EWQ: 'AMEX:EWQ', EWG: 'AMEX:EWG', EWL: 'AMEX:EWL', KSA: 'AMEX:KSA', EZA: 'AMEX:EZA', INDA: 'BATS:INDA',
  MCHI: 'NASDAQ:MCHI', EWY: 'AMEX:EWY', EWJ: 'AMEX:EWJ', EWA: 'AMEX:EWA', EWI: 'AMEX:EWI', EWP: 'AMEX:EWP',
  EWN: 'AMEX:EWN', EWD: 'AMEX:EWD', EPOL: 'AMEX:EPOL', EWT: 'AMEX:EWT', ECH: 'AMEX:ECH', COLO: 'AMEX:COLO',
  EIDO: 'AMEX:EIDO', EWS: 'AMEX:EWS', THD: 'AMEX:THD', VNM: 'NASDAQ:VNM', TUR: 'NASDAQ:TUR', UAE: 'NASDAQ:UAE',
  EGPT: 'AMEX:EGPT',

  // Exceptions manuelles d'actions (exemples ; ajouter ici les cas que la règle automatique rate)
  'BRK-B': 'NYSE:BRK.B',
  'BF-B': 'NYSE:BF.B',
};

/** Hors séance, l'indice est remplacé par son contrat à terme (bandeau des marchés). */
export const CONTRATS_A_TERME = {
  '^NDX': 'NQ=F',
  '^GSPC': 'ES=F',
  '^FCHI': 'FCE=F',
};

/**
 * Suffixe Yahoo → place TradingView.
 * `format` adapte le code (TradingView n'écrit pas toujours les tickers comme Yahoo).
 */
const sansZeros = (t) => t.replace(/^0+(?=\d)/, '');
const tiretEnPoint = (t) => t.replace(/-/g, '.');
const tiretEnSouligne = (t) => t.replace(/-/g, '_');

export const PLACES = {
  '.PA': { place: 'EURONEXT' },
  '.AS': { place: 'EURONEXT' },
  '.BR': { place: 'EURONEXT' },
  '.LS': { place: 'EURONEXT' },
  '.IR': { place: 'EURONEXT' },
  '.DE': { place: 'XETR' },
  '.F': { place: 'FWB' },
  '.L': { place: 'LSE', format: (t) => tiretEnPoint(t).replace(/\.$/, '') },
  '.MI': { place: 'MIL' },
  '.MC': { place: 'BME' },
  '.SW': { place: 'SIX' },
  '.ST': { place: 'OMXSTO', format: tiretEnSouligne },
  '.CO': { place: 'OMXCOP', format: tiretEnSouligne },
  '.HE': { place: 'OMXHEX' },
  '.OL': { place: 'OSL' },
  '.WA': { place: 'GPW' },
  '.VI': { place: 'VIE' },
  '.T': { place: 'TSE' },
  '.KS': { place: 'KRX' },
  '.KQ': { place: 'KRX' },
  '.TW': { place: 'TWSE' },
  '.TWO': { place: 'TPEX' },
  '.HK': { place: 'HKEX', format: sansZeros },
  '.SS': { place: 'SSE' },
  '.SZ': { place: 'SZSE' },
  '.NS': { place: 'NSE', format: (t) => t.replace(/[-&]/g, '_') },
  '.BO': { place: 'BSE' },
  '.SA': { place: 'BMFBOVESPA' },
  '.MX': { place: 'BMV', format: (t) => t.replace(/\*$/, '') },
  '.TO': { place: 'TSX', format: tiretEnPoint },
  '.V': { place: 'TSXV', format: tiretEnPoint },
  '.AX': { place: 'ASX' },
  '.NZ': { place: 'NZX' },
  '.JO': { place: 'JSE' },
  '.SR': { place: 'TADAWUL' },
  '.AD': { place: 'ADX' },
  '.AE': { place: 'DFM' },
  '.IS': { place: 'BIST' },
  '.JK': { place: 'IDX' },
  '.SI': { place: 'SGX' },
  '.BK': { place: 'SET' },
  '.SN': { place: 'BCS' },
  '.CL': { place: 'BVC' },
  '.BA': { place: 'BCBA' },
  '.VN': { place: 'HOSE' },
  '.CA': { place: 'EGX' },
};

/**
 * Ce que le widget gratuit de TradingView refuse d'afficher (« ce symbole n'est disponible que sur
 * TradingView ») : symboles exacts, ou places entières. Vérifié sur téléphone simulé ; à compléter.
 */
export const NON_DISPONIBLES = {
  symboles: new Set([
    'NASDAQ:NDX',
    'SP:SPX',
    'CME_MINI:NQ1!',
    'CME_MINI:ES1!',
    'COMEX:GC1!',
    'NYMEX:CL1!',
    'EURONEXT:FCE1!',
  ]),
  places: new Set([]),
};

/**
 * Symbole Yahoo → symbole TradingView (« PLACE:CODE »), ou le code nu si la place est inconnue
 * (TradingView choisit alors la cotation principale).
 * @param {string} yahoo  symbole Yahoo Finance (AAPL, MC.PA, 7203.T, ^NDX…)
 * @param {string} [placeUS]  place indiquée par l'agent entreprises pour une action sans suffixe : NASDAQ, NYSE, AMEX…
 */
export function versTradingView(yahoo, placeUS) {
  if (!yahoo) return null;
  const s = String(yahoo).trim().toUpperCase();
  if (SYMBOLES[s]) return SYMBOLES[s];
  const point = s.lastIndexOf('.');
  if (point > 0) {
    const suffixe = s.slice(point);
    const regle = PLACES[suffixe];
    if (regle) {
      const code = s.slice(0, point);
      return `${regle.place}:${regle.format ? regle.format(code) : code}`;
    }
  }
  if (s.startsWith('^') || s.includes('=')) return null; // indice ou contrat inconnu : à ajouter dans SYMBOLES
  // Action américaine (pas de suffixe) : BRK-B → BRK.B
  const code = tiretEnPoint(s);
  return placeUS ? `${String(placeUS).toUpperCase()}:${code}` : code;
}

/** Le widget gratuit peut-il afficher ce symbole TradingView ? */
export function disponibleDansWidget(tv) {
  if (!tv) return false;
  if (NON_DISPONIBLES.symboles.has(tv)) return false;
  const place = tv.includes(':') ? tv.split(':')[0] : null;
  return !(place && NON_DISPONIBLES.places.has(place));
}

/** Adresse de la page TradingView du symbole (lien « Ouvrir sur TradingView »). */
export function lienTradingView(tv) {
  return `https://fr.tradingview.com/chart/?symbol=${encodeURIComponent(tv)}`;
}
