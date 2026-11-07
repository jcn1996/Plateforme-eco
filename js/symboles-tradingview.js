/* ==========================================================================
   Correspondance des symboles Yahoo Finance → TradingView
   --------------------------------------------------------------------------
   Fichier fait pour être complété à la main :
   - SYMBOLES      : indices, contrats à terme, matières premières, devises,
                     crypto et exceptions manuelles (prioritaires sur tout le reste) ;
   - INDICES_PAYS  : indice national de chaque fiche pays (graphique), avec le résultat
                     des vérifications pays par pays sur téléphone simulé ;
   - INDICES_BANDEAU : même logique pour les indices du bandeau des marchés ;
   - CONTRATS_A_TERME : contrat à terme affiché hors séance à la place d'un indice
                     (pour les cotations du bandeau absentes d'INDICES_BANDEAU) ;
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
  '^N225': 'INDEX:NKY', // TVC:NI225 refusé par le widget gratuit (vérifié le 07/11/2026)
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

  // ETF pays de l'agent pays (place exacte, pour éviter toute ambiguïté ; VNM sur NYSE Arca : NASDAQ:VNM refusé, vérifié le 07/11/2026)
  SPY: 'AMEX:SPY', EWC: 'AMEX:EWC', EWW: 'AMEX:EWW', EWZ: 'AMEX:EWZ', ARGT: 'AMEX:ARGT', EWU: 'AMEX:EWU',
  EWQ: 'AMEX:EWQ', EWG: 'AMEX:EWG', EWL: 'AMEX:EWL', KSA: 'AMEX:KSA', EZA: 'AMEX:EZA', INDA: 'BATS:INDA',
  MCHI: 'NASDAQ:MCHI', EWY: 'AMEX:EWY', EWJ: 'AMEX:EWJ', EWA: 'AMEX:EWA', EWI: 'AMEX:EWI', EWP: 'AMEX:EWP',
  EWN: 'AMEX:EWN', EWD: 'AMEX:EWD', EPOL: 'AMEX:EPOL', EWT: 'AMEX:EWT', ECH: 'AMEX:ECH', COLO: 'AMEX:COLO',
  EIDO: 'AMEX:EIDO', EWS: 'AMEX:EWS', THD: 'AMEX:THD', VNM: 'AMEX:VNM', TUR: 'NASDAQ:TUR', UAE: 'NASDAQ:UAE',
  EGPT: 'AMEX:EGPT',

  // Exceptions manuelles d'actions (exemples ; ajouter ici les cas que la règle automatique rate)
  'BRK-B': 'NYSE:BRK.B',
  'BF-B': 'NYSE:BF.B',
};

/* --------------------------------------------------------------------------
   Indices nationaux : ordre de tentative pour le widget gratuit
     a) l'indice officiel sur sa place (EURONEXT:PX1, XETR:DAX…) ;
     b) la version TradingView de l'indice (préfixes TVC: et INDEX:) ;
     c) un CFD équivalent accepté (« graphique : équivalent CFD de l'indice ») ;
     d) sinon, graphique simplifié tracé avec l'historique Yahoo de l'indice
        (data/cours/indices-pays.json, publié par l'agent pays) ;
     et si Yahoo ne publie pas non plus d'historique utilisable : graphique de l'ETF
     pays, avec la mention « indice indisponible, ETF affiché ».
   Vérifié le 07/11/2026 avec le widget gratuit (tv.js) sur iPhone 13 simulé :
   ✓ = graphique affiché avec des cours à jour ; ✗ = « Ce symbole n'existe pas » ;
   « arrêté » = graphique affiché mais cours figés (inutilisable).
   type : 'officiel' (a), 'tradingview' (b), 'cfd' (c), 'yahoo' (d).
   -------------------------------------------------------------------------- */
export const VERIFICATION_INDICES = '2026-11-07';

export const INDICES_PAYS = {
  US: { nom: 'S&P 500', tv: 'OANDA:SPX500USD', type: 'cfd',
    essais: 'a) SP:SPX ✗ · b) TVC:SPX ✗, INDEX:SPX ✗ · c) OANDA:SPX500USD ✓ (aussi FX:SPX500, CAPITALCOM:US500, PEPPERSTONE:US500)' },
  CA: { nom: 'S&P/TSX', tv: 'TSX:TSX', type: 'officiel', essais: 'a) TSX:TSX ✓' },
  MX: { nom: 'IPC (S&P/BMV)', tv: 'INDEX:ME', type: 'tradingview', essais: 'a) BMV:ME ✗ (place BMV refusée) · b) TVC:ME ✗, INDEX:ME ✓' },
  BR: { nom: 'Ibovespa', tv: 'BMFBOVESPA:IBOV', type: 'officiel', essais: 'a) BMFBOVESPA:IBOV ✓' },
  AR: { nom: 'S&P Merval', tv: null, type: 'yahoo',
    essais: 'a) BCBA:IMV ✗ · b) TVC:MERVAL ✗, INDEX:MERVAL ✗, INDEX:MERV arrêté (2019) · c) aucun CFD' },
  GB: { nom: 'FTSE 100', tv: 'OANDA:UK100GBP', type: 'cfd',
    essais: 'a) FTSE:UKX ✗ · b) TVC:UKX ✗, INDEX:UKX ✗ · c) OANDA:UK100GBP ✓ (aussi CAPITALCOM:UK100)' },
  FR: { nom: 'CAC 40', tv: 'EURONEXT:PX1', type: 'officiel', essais: 'a) EURONEXT:PX1 ✓' },
  DE: { nom: 'DAX 40', tv: 'XETR:DAX', type: 'officiel', essais: 'a) XETR:DAX ✓' },
  CH: { nom: 'SMI', tv: 'SIX:SMI', type: 'officiel', essais: 'a) SIX:SMI ✓' },
  SA: { nom: 'TASI', tv: null, type: 'yahoo', essais: 'a) TADAWUL:TASI ✗ · b) INDEX:TASI ✗ · c) aucun CFD' },
  ZA: { nom: 'JSE Top 40', tv: null, type: 'yahoo',
    essais: 'a) JSE:J200 ✗ · b) INDEX:J200 ✗, INDEX:SA40 ✗ · c) PEPPERSTONE:SA40 ✗, CAPITALCOM:ZA40 ✗, OANDA:ZA40ZAR ✗' },
  IN: { nom: 'Nifty 50', tv: null, type: 'yahoo',
    essais: 'a) NSE:NIFTY ✗, NSE:NIFTY50 ✗ · b) TVC:NIFTY ✗, INDEX:NIFTY ✗ · c) PEPPERSTONE:IND50 ✗, CAPITALCOM:IN50 ✗, OANDA:IN50USD ✗' },
  CN: { nom: 'Shanghai Composite', tv: 'SSE:000001', type: 'officiel',
    essais: 'a) SSE:000001 ✓ (SSE:000300 ✓ aussi, mais le CSI 300 n’a pas d’historique chez Yahoo pour le momentum)' },
  KR: { nom: 'KOSPI', tv: null, type: 'yahoo',
    essais: 'a) KRX:KOSPI ✗ · b) TVC:KOSPI ✗, INDEX:KOSPI ✗ · c) PEPPERSTONE:KOR200 ✗, CAPITALCOM:KR200 ✗, FOREXCOM:KOREA200 ✗' },
  JP: { nom: 'Nikkei 225', tv: 'INDEX:NKY', type: 'tradingview', essais: 'a) TSE:NI225 ✗ · b) TVC:NI225 ✗, INDEX:NKY ✓' },
  AU: { nom: 'S&P/ASX 200', tv: 'PEPPERSTONE:AUS200', type: 'cfd',
    essais: 'a) ASX:XJO ✗ · b) TVC:XJO ✗, INDEX:XJO ✗ · c) PEPPERSTONE:AUS200 ✓' },
  IT: { nom: 'FTSE MIB', tv: 'INDEX:FTSEMIB', type: 'tradingview', essais: 'a) MIL:FTSEMIB ✗ · b) TVC:FTSEMIB ✗, INDEX:FTSEMIB ✓' },
  ES: { nom: 'IBEX 35', tv: 'BME:IBC', type: 'officiel', essais: 'a) BME:IBC ✓' },
  NL: { nom: 'AEX', tv: 'EURONEXT:AEX', type: 'officiel', essais: 'a) EURONEXT:AEX ✓' },
  SE: { nom: 'OMX Stockholm 30', tv: 'OMXSTO:OMXS30', type: 'officiel', essais: 'a) OMXSTO:OMXS30 ✓' },
  PL: { nom: 'WIG20', tv: 'GPW:WIG20', type: 'officiel', essais: 'a) GPW:WIG20 ✓' },
  TW: { nom: 'TAIEX', tv: 'INDEX:TAIEX', type: 'tradingview', essais: 'a) TWSE:TAIEX ✗ · b) TVC:TAIEX ✗, INDEX:TAIEX ✓' },
  ID: { nom: 'IDX Composite', tv: 'IDX:COMPOSITE', type: 'officiel', essais: 'a) IDX:COMPOSITE ✓' },
  VN: { nom: 'VN-Index', tv: null, type: 'yahoo',
    essais: 'a) HOSE:VNINDEX ✗, HOSE:VN30 ✗ · b) TVC:VNINDEX ✗, INDEX:VNINDEX ✗, INDEX:VNI ✗ · c) aucun CFD' },
  SG: { nom: 'STI', tv: 'INDEX:STI', type: 'tradingview', essais: 'a) SGX:STI ✗ (place SGX refusée) · b) TVC:STI ✗, INDEX:STI ✓' },
  TH: { nom: 'SET', tv: null, type: 'yahoo', essais: 'a) SET:SET ✗ · b) INDEX:SET ✗, INDEX:SET50 ✗ · c) aucun CFD' },
  CL: { nom: 'S&P IPSA', tv: 'BCS:SP_IPSA', type: 'officiel', essais: 'a) BCS:SP_IPSA ✓' },
  CO: { nom: 'MSCI COLCAP', tv: 'BVC:COLCAP', type: 'officiel', essais: 'a) BVC:COLCAP ✓' },
  AE: { nom: 'FTSE ADX General', tv: null, type: 'yahoo', essais: 'a) ADX:FADGI ✗, DFM:DFMGI ✗ · b) aucun · c) aucun CFD' },
  TR: { nom: 'BIST 100', tv: null, type: 'yahoo',
    essais: 'a) BIST:XU100 ✗ · b) INDEX:XU100 ✗, INDEX:XU030 ✗ · c) CAPITALCOM:TR20 ✗' },
  EG: { nom: 'EGX 30', tv: 'EGX:EGX30', type: 'officiel', essais: 'a) EGX:EGX30 ✓' },
};

/** Indices du bandeau des marchés (clé = symbole Yahoo), même ordre de tentative, même date de vérification. */
export const INDICES_BANDEAU = {
  '^GSPC': { nom: 'S&P 500', tv: 'OANDA:SPX500USD', type: 'cfd', essais: INDICES_PAYS.US.essais },
  '^NDX': { nom: 'Nasdaq 100', tv: 'OANDA:NAS100USD', type: 'cfd',
    essais: 'a) NASDAQ:NDX ✗ · b) TVC:NDX ✗, INDEX:NDX ✗ · c) OANDA:NAS100USD ✓ (aussi CAPITALCOM:US100, PEPPERSTONE:NAS100)' },
  '^FCHI': { nom: 'CAC 40', tv: 'EURONEXT:PX1', type: 'officiel', essais: INDICES_PAYS.FR.essais },
};

/** Mention affichée sous un graphique tracé avec un CFD à la place de l'indice. */
export const MENTION_CFD = 'graphique : équivalent CFD de l’indice';

/** Hors séance, l'indice est remplacé par son contrat à terme (cotations du bandeau absentes d'INDICES_BANDEAU). */
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
  // Vérifié le 04/11/2026 : « Symbole disponible uniquement sur TradingView » (le 07/11/2026 : « Ce symbole n'existe pas »)
  symboles: new Set([
    'NASDAQ:NDX',
    'SP:SPX',
    'CME_MINI:NQ1!',
    'CME_MINI:ES1!',
    'COMEX:GC1!',
    'NYMEX:CL1!',
  ]),
  // Places entières refusées par le widget gratuit (vérifié le 04/11/2026 sur une action de chacune)
  places: new Set([
    'LSE', // Londres
    'HKEX', 'TSE', 'KRX', 'TWSE', // Hong Kong, Tokyo, Corée, Taïwan
    'NSE', 'BSE', // Inde
    'SGX', 'SET', // Singapour, Bangkok
    'TADAWUL', 'BIST', 'JSE', // Arabie saoudite, Istanbul, Johannesburg
    'BMV', // Mexique
  ]),
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
