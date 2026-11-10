/* ==========================================================================
   Mes portefeuilles : portefeuilles d'EXEMPLE, entièrement FICTIFS.
   Quantités, prix de revient et valeurs inventés pour la démonstration et
   les tests ; aucune donnée réelle. Le bouton « Charger l'exemple fictif »
   de l'écran les ajoute sur l'appareil, avec la mention « exemple fictif ».
   ========================================================================== */

const L = (nom, ticker, type, quantite, prix_revient, extra = {}) => ({ nom, ticker, type, quantite, prix_revient, isin: null, devise: null, valeur: null, ...extra });

export function portefeuillesExemple(dateReference = '2026-01-02') {
  return [
    {
      nom: 'PEA (exemple fictif)', type: 'pea', exemple: true,
      lignes: [
        L('TotalEnergies', 'TTE.PA', 'action', 120, 54.2),
        L('LVMH', 'MC.PA', 'action', 9, 610),
        L('Air Liquide', 'AI.PA', 'action', 30, 158),
        L('Sanofi', 'SAN.PA', 'action', 45, 88.5),
        L('ASML', 'ASML.AS', 'action', 6, 640),
        L('ETF MSCI World (exemple)', null, 'etf', 40, 480, { valeur: 21500, categorie: { classe: 'actions', zone: 'monde', secteur: 'diversifie', themes: [] } }),
      ],
    },
    {
      nom: 'Compte-titres (exemple fictif)', type: 'cto', exemple: true,
      lignes: [
        L('NVIDIA', 'NVDA', 'action', 60, 118, { devise: 'USD' }),
        L('Microsoft', 'MSFT', 'action', 18, 395, { devise: 'USD' }),
        L('Apple', 'AAPL', 'action', 25, 205, { devise: 'USD' }),
        L('iShares MSCI Japan', 'EWJ', 'etf', 80, 66, { devise: 'USD' }),
        L('Liquidités', null, 'liquidites', null, null, { valeur: 3200, devise: 'EUR' }),
      ],
    },
    {
      nom: 'Assurance vie (exemple fictif)', type: 'assurance_vie', exemple: true,
      lignes: [
        L('Fonds en euros (exemple)', null, 'fonds', null, null, { valeur: 30000, categorie: { classe: 'obligations', zone: 'zone_euro', secteur: '', themes: [] } }),
        L('UC Actions Europe (exemple)', null, 'fonds', 150, 95, { valeur: 15200, categorie: { classe: 'actions', zone: 'europe', secteur: 'diversifie', themes: [] } }),
        L('UC Or (exemple)', null, 'fonds', 50, 110, { valeur: 6900, categorie: { classe: 'or', zone: '', secteur: '', themes: ['or'] } }),
      ],
    },
  ].map((p) => ({ ...p, date_reference: dateReference }));
}

/** Export CSV fictif, au format d'un courtier français (séparateur « ; », virgule décimale, lignes d'introduction). */
export const CSV_EXEMPLE = [
  'Export des positions — exemple fictif',
  'Compte : 00000000000 (fictif)',
  '',
  'Libellé;Code ISIN;Quantité;Prix de revient;Cours;Valorisation (EUR)',
  'TOTALENERGIES;FR0000120271;120;54,20;58,10;6 972,00',
  'LVMH;FR0000121014;9;610,00;640,50;5 764,50',
  'FONDS EXEMPLE ACTIONS MONDE (FICTIF);FR0000000000;150;95,00;101,30;15 195,00',
  'Total;;;;;27 931,50',
].join('\n');
