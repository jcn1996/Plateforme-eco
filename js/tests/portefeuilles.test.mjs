// Tests de « Mes portefeuilles » (import, chiffrement, analyses) avec un portefeuille FICTIF : node --test js/tests/
// Aucune donnée réelle : les sociétés, cours et quantités ci-dessous sont inventés.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  lireCSV, lireNombre, isinValide, detecterColonnes, construireLignes, correspondanceSuffisante, rapprocherParNom, nomCompare,
} from '../portefeuilles-import.js';
import { chiffrer, dechiffrer, cleDeBase } from '../portefeuilles-chiffrement.js';
import {
  construireReferences, enrichir, expositions, correlations, crible, coherence, decorrelation, performance,
  rendementsHebdo, correlation, cleSemaine, deviseSymbole, profilLigne,
} from '../portefeuilles-analyse.js';
import { portefeuillesExemple, CSV_EXEMPLE } from '../portefeuilles-exemple.js';
import { integrerSynchro, etatVide, noterValeur } from '../portefeuilles-donnees.js';

/* ------------------------------- Import ------------------------------- */

test('nombres français et anglais', () => {
  assert.equal(lireNombre('1 234,56'), 1234.56);
  assert.equal(lireNombre('1.234,56'), 1234.56);
  assert.equal(lireNombre('1,234.56'), 1234.56);
  assert.equal(lireNombre('1 234,5 €'), 1234.5);
  assert.equal(lireNombre('−12,5 %'), -12.5);
  assert.equal(lireNombre('(3,10)'), -3.1);
  assert.equal(lireNombre('12'), 12);
  assert.equal(lireNombre('1,234,567'), 1234567);
  assert.equal(lireNombre('abc'), null);
  assert.equal(lireNombre(''), null);
});

test('ISIN : clé de contrôle', () => {
  assert.equal(isinValide('FR0000120271'), true);
  assert.equal(isinValide('US0378331005'), true);
  assert.equal(isinValide('IE00B4L5Y983'), true);
  assert.equal(isinValide('FR0000120272'), false);
  assert.equal(isinValide('FR0000000000'), false);
  assert.equal(isinValide('TTE.PA'), false);
});

test('CSV d’un courtier français : lignes d’introduction, en-tête, total ignoré', () => {
  const lignes = lireCSV(CSV_EXEMPLE);
  const det = detecterColonnes(lignes);
  assert.equal(det.indice, 2); // la ligne vide est ignorée à la lecture
  assert.deepEqual(
    { nom: det.correspondance.nom, isin: det.correspondance.isin, quantite: det.correspondance.quantite, prix_revient: det.correspondance.prix_revient, cours: det.correspondance.cours, valeur: det.correspondance.valeur },
    { nom: 0, isin: 1, quantite: 2, prix_revient: 3, cours: 4, valeur: 5 },
  );
  assert.ok(correspondanceSuffisante(det.correspondance));
  const res = construireLignes(lignes, det);
  assert.equal(res.length, 3);
  assert.deepEqual(res[0], { nom: 'TOTALENERGIES', isin: 'FR0000120271', ticker: null, quantite: 120, prix_revient: 54.2, cours: 58.1, valeur: 6972, devise: null });
  assert.equal(res[2].isin, null, 'ISIN fictif invalide écarté');
});

test('CSV anglais à virgules, guillemets et ticker', () => {
  const csv = 'Symbol,Description,Quantity,"Cost Basis Price",Market Value,Currency\nAAPL,"Apple, Inc.",10,"150.5","2,345.10",USD\nMSFT,Microsoft,5,300,"1,800.00",USD\n';
  const lignes = lireCSV(csv);
  const det = detecterColonnes(lignes);
  assert.equal(det.correspondance.ticker, 0);
  assert.equal(det.correspondance.nom, 1);
  const res = construireLignes(lignes, det);
  assert.equal(res[0].nom, 'Apple, Inc.');
  assert.equal(res[0].valeur, 2345.1);
  assert.equal(res[0].devise, 'USD');
  assert.equal(res[1].prix_revient, 300);
});

test('export BoursoBank (intitulés anglais compacts)', () => {
  const csv = 'name;isin;quantity;buyingPrice;lastPrice;intradayVariation;amount;amountVariation;variation\n"AIR LIQUIDE";FR0000120073;30;158,00;175,20;0,5;5256,00;516,00;10,9\n';
  const lignes = lireCSV(csv);
  const det = detecterColonnes(lignes);
  const res = construireLignes(lignes, det);
  assert.equal(res.length, 1);
  assert.equal(res[0].isin, 'FR0000120073');
  assert.equal(res[0].prix_revient, 158);
  assert.equal(res[0].cours, 175.2);
  assert.equal(res[0].valeur, 5256);
});

test('correspondance insuffisante détectée (écran de correspondance)', () => {
  const lignes = lireCSV('A;B;C\nfoo;12;bar\n');
  assert.equal(correspondanceSuffisante(detecterColonnes(lignes).correspondance), false);
});

test('rapprochement local ISIN → ticker par le nom (sans réseau)', () => {
  const societes = [
    { ticker: 'TTE.PA', nom: 'TotalEnergies SE', pays: 'FR', capitalisation_md: 140 },
    { ticker: 'MC.PA', nom: 'LVMH Moët Hennessy - Louis Vuitton, Société Européenne', pays: 'FR', capitalisation_md: 300 },
    { ticker: 'TOT.XX', nom: 'Totalement Autre Inc.', pays: 'US', capitalisation_md: 999 },
    { ticker: 'AAPL', nom: 'Apple Inc.', pays: 'US', capitalisation_md: 3000 },
  ];
  assert.equal(nomCompare('TotalEnergies SE'), 'totalenergies');
  assert.equal(rapprocherParNom('TOTALENERGIES', 'FR0000120271', societes)?.ticker, 'TTE.PA');
  assert.equal(rapprocherParNom('LVMH', 'FR0000121014', societes)?.ticker, 'MC.PA');
  assert.equal(rapprocherParNom('APPLE INC', 'US0378331005', societes)?.ticker, 'AAPL');
  assert.equal(rapprocherParNom('LVMH', 'US0000000000', societes), null, 'pays de l’ISIN différent');
  assert.equal(rapprocherParNom('FONDS EXEMPLE ACTIONS MONDE (FICTIF)', 'LU0000000000', societes), null);
});

/* ------------------------------- Chiffrement ------------------------------- */

test('chiffrement AES-256-GCM : aller-retour, mauvais mot de passe refusé', async () => {
  const contenu = { portefeuilles: portefeuillesExemple() };
  const env = await chiffrer(contenu, 'mot de passe fictif', { iterations: 100000 });
  assert.equal(env.chiffrement.nom, 'AES-256-GCM');
  assert.ok(!JSON.stringify(env).includes('TTE.PA'), 'aucune donnée en clair');
  assert.deepEqual(await dechiffrer(env, 'mot de passe fictif'), contenu);
  await assert.rejects(() => dechiffrer(env, 'mauvais'), /Mot de passe incorrect/);
  // clé de base non extractible (mémorisée sur l'appareil pour la synchronisation)
  const cle = await cleDeBase('mot de passe fictif');
  assert.equal(cle.extractable, false);
  assert.deepEqual(await dechiffrer(env, cle), contenu);
});

test('fichier chiffré par le script Python de synchronisation (vecteur de test fictif)', async () => {
  const chemin = fileURLToPath(new URL('./donnees/synchro-exemple.chiffre.json', import.meta.url));
  const env = JSON.parse(readFileSync(chemin, 'utf8'));
  const contenu = await dechiffrer(env, 'exemple-fictif-ne-pas-utiliser');
  assert.equal(contenu.format, 'salle-controle/synchro-portefeuilles');
  assert.equal(contenu.portefeuilles.length, 2);
  const etat = etatVide();
  const bilan = integrerSynchro(etat, contenu);
  assert.equal(bilan.length, 2);
  assert.equal(etat.portefeuilles[0].source, 'synchro');
  assert.ok(etat.portefeuilles[0].reference.valeur > 0);
  // 2e passage : même portefeuille, catégorie saisie conservée
  etat.portefeuilles[0].lignes[0].categorie = { classe: 'actions', zone: 'monde' };
  integrerSynchro(etat, contenu);
  assert.equal(etat.portefeuilles.length, 2);
  assert.deepEqual(etat.portefeuilles[0].lignes[0].categorie, { classe: 'actions', zone: 'monde' });
});

test('historique : un point par jour', () => {
  const pf = { historique: [] };
  noterValeur(pf, 100, '2026-11-01');
  noterValeur(pf, 101, '2026-11-01');
  noterValeur(pf, 102, '2026-11-02');
  assert.deepEqual(pf.historique, [{ date: '2026-11-01', valeur: 101 }, { date: '2026-11-02', valeur: 102 }]);
});

/* ------------------------------- Analyses ------------------------------- */

// Séries hebdomadaires synthétiques sur 1 an (déterministes) : deux « facteurs » indépendants
function generateur(graine) {
  let s = graine;
  return () => { s = (s * 16807) % 2147483647; return s / 2147483647 - 0.5; };
}
const DATES = Array.from({ length: 53 }, (_, i) => new Date(Date.UTC(2025, 10, 14) + i * 7 * 864e5).toISOString().slice(0, 10));
function serie(depart, chocs) {
  let c = depart;
  return DATES.map((d, i) => { c *= 1 + chocs[i]; return [d, Math.round(c * 100) / 100]; });
}
const fa = generateur(7); const fb = generateur(99); const fc = generateur(1234);
const TECH = DATES.map(() => fa() * 0.08);
const DEFENSIF = DATES.map(() => fb() * 0.04);
const BRUIT = () => DATES.map(() => fc() * 0.01);
const SERIES = {
  '^NDX': serie(20000, TECH),
  NVDA: serie(100, TECH.map((x, i) => x * 1.6 + BRUIT()[i])),
  MSFT: serie(400, TECH.map((x, i) => x * 0.9 + BRUIT()[i])),
  'SAN.PA': serie(90, DEFENSIF.map((x, i) => x + BRUIT()[i])),
  'GC=F': serie(3000, DATES.map(() => fb() * 0.03)),
  URTH: serie(150, TECH.map((x) => x * 0.6)),
  'EURUSD=X': DATES.map((d) => [d, 1.1]),
  EWJ: serie(70, DEFENSIF.map((x) => -x)),
};

const ENTREPRISES = [
  { ticker: 'NVDA', nom: 'Société fictive A', pays: 'US', devise: 'USD', secteur_gics: 'Information Technology', note: 71, recommandation: { d: 'Alléger' } },
  { ticker: 'MSFT', nom: 'Société fictive B', pays: 'US', devise: 'USD', secteur_gics: 'Information Technology', note: 74, recommandation: { d: 'Renforcer' } },
  { ticker: 'SAN.PA', nom: 'Société fictive C', pays: 'FR', devise: 'EUR', secteur_gics: 'Health Care', note: 70, recommandation: { d: 'Renforcer' } },
];
const PAYS = [{ code: 'US', nom: 'États-Unis', note: 60 }, { code: 'FR', nom: 'France', note: 55 }, { code: 'JP', nom: 'Japon', note: 62 }];
const CHEF = {
  pays: [{ id: 'pays-JP', type: 'pays', cle: 'JP', nom: 'Japon', symbole: 'EWJ', verdict: 'Renforcer', conviction: 'moyenne', score: 64, themes: [] }],
  entreprises: [
    { id: 'entreprise-NVDA', type: 'entreprises', cle: 'NVDA', nom: 'Société fictive A', symbole: 'NVDA', verdict: 'Alléger', conviction: 'faible', score: 40, themes: ['semi'], objections: [{ objection: 'Momentum extrême (fictif).' }], donner_tort: [] },
    { id: 'entreprise-MSFT', type: 'entreprises', cle: 'MSFT', nom: 'Société fictive B', symbole: 'MSFT', verdict: 'Renforcer', conviction: 'forte', score: 69, themes: [], objections: [] },
  ],
  secteurs: [], matieres: [], obligations: [], liquidites: [],
  or: { id: 'or', type: 'or', cle: 'or', nom: 'Or', symbole: 'GC=F', verdict: 'Renforcer', conviction: 'faible', score: 60, themes: ['or'] },
};

const LIGNES = [
  { id: 'a', nom: 'Fictive A', ticker: 'NVDA', type: 'action', quantite: 100, prix_revient: 50, devise: 'USD' },
  { id: 'b', nom: 'Fictive B', ticker: 'MSFT', type: 'action', quantite: 10, prix_revient: 300, devise: 'USD' },
  { id: 'c', nom: 'Fictive C', ticker: 'SAN.PA', type: 'action', quantite: 50, prix_revient: 80 },
  { id: 'd', nom: 'Fonds monde (fictif)', type: 'fonds', valeur: 5000, categorie: { classe: 'actions', zone: 'monde', secteur: 'diversifie', themes: [] } },
  { id: 'e', nom: 'Liquidités', type: 'liquidites', valeur: 1000, devise: 'EUR' },
];

function refs() {
  return construireReferences({ entreprises: ENTREPRISES, pays: PAYS, chef: CHEF, series: SERIES, eurusd: 1.1 });
}

test('devise de cotation déduite du suffixe', () => {
  assert.equal(deviseSymbole('MC.PA'), 'EUR');
  assert.equal(deviseSymbole('AAPL'), 'USD');
  assert.equal(deviseSymbole('VOD.L'), 'GBp');
  assert.equal(deviseSymbole('7203.T'), 'JPY');
});

test('clé hebdomadaire : vendredi de la semaine ISO', () => {
  assert.equal(cleSemaine('2026-11-09'), '2026-11-13'); // lundi
  assert.equal(cleSemaine('2026-11-13'), '2026-11-13'); // vendredi
  assert.equal(cleSemaine('2026-11-15'), '2026-11-13'); // dimanche
});

test('valeurs : dernier cours public converti en euros, sinon valeur du courtier', () => {
  const e = enrichir(LIGNES, refs());
  const a = e.lignes[0];
  const dernier = SERIES.NVDA[SERIES.NVDA.length - 1][1];
  assert.ok(Math.abs(a.valeur - (100 * dernier) / 1.1) < 1e-6);
  assert.equal(e.lignes[3].valeur, 5000);
  assert.ok(Math.abs(e.lignes.reduce((s, x) => s + x.poids, 0) - 100) < 1e-9);
});

test('expositions et alertes de concentration', () => {
  const r = refs();
  const e = enrichir(LIGNES, r);
  const exp = expositions(e, { US: 'États-Unis', FR: 'France' });
  const us = exp.pays.find((p) => p.cle === 'US');
  assert.ok(us.pct > 50, 'États-Unis majoritaires (actions + 72 % du fonds monde)');
  assert.ok(exp.classes.find((c) => c.cle === 'liquidites'));
  assert.ok(exp.themes.find((t) => t.cle === 'semi'), 'thème semi-conducteurs repris du chef d’orchestre');
  assert.ok(exp.themes.find((t) => t.cle === 'ia'), 'thème IA (liste de tickers)');
  assert.ok(exp.alertes.some((a) => a.type === 'ligne'));
  assert.ok(exp.alertes.some((a) => a.type === 'pays'));
  // fonds non classé signalé
  const p = profilLigne({ nom: 'Fonds inconnu', type: 'fonds' }, r);
  assert.equal(p.nonClasse, true);
});

test('corrélations, part du risque et diversification', () => {
  const r = refs();
  const e = enrichir(LIGNES, r);
  const c = correlations(e, r, { aujourdhui: new Date('2026-11-13T12:00:00Z') });
  const a = c.lignes.find((l) => l.id === 'a');
  const sanofi = c.lignes.find((l) => l.id === 'c');
  assert.ok(a.corr_nasdaq > 0.9, `NVDA suit le Nasdaq (${a.corr_nasdaq})`);
  assert.ok(Math.abs(sanofi.corr_nasdaq) < 0.5, `ligne défensive peu corrélée (${sanofi.corr_nasdaq})`);
  const parts = c.lignes.reduce((s, l) => s + (l.part_risque ?? 0), 0);
  assert.ok(Math.abs(parts - 100) < 0.5, `parts du risque ≈ 100 % (${parts})`);
  assert.ok(a.part_risque > a.poids, 'la ligne la plus volatile apporte plus de risque que son poids');
  assert.equal(c.lignes.find((l) => l.id === 'd').approximation, 'URTH', 'fonds : indice de référence approché');
  assert.ok(c.portefeuille.ratio_diversification >= 1);
  assert.ok(c.portefeuille.n_effectif_risque < c.portefeuille.n_effectif_lignes);
});

test('crible, cohérence avec le chef d’orchestre et pistes de décorrélation', () => {
  const r = refs();
  const e = enrichir(LIGNES, r);
  const cr = crible(e, r);
  const a = cr.find((x) => x.id === 'a');
  assert.equal(a.note, 71);
  assert.equal(a.si_detenu, 'Alléger');
  assert.ok(a.objections[0].includes('Momentum'));
  assert.ok(a.alertes.some((t) => t.includes('Alléger')));
  const exp = expositions(e, {});
  const co = coherence(e, r, exp);
  assert.deepEqual(co.a_alleger.map((x) => x.nom), ['Fictive A']);
  assert.deepEqual(co.absentes.map((x) => x.id).sort(), ['or', 'pays-JP']);
  const c = correlations(e, r, { aujourdhui: new Date('2026-11-13T12:00:00Z') });
  const pistes = decorrelation(c.rendements, r, { 'pays-JP': SERIES.EWJ, or: SERIES['GC=F'], 'entreprise-MSFT': SERIES.MSFT }, { aujourdhui: new Date('2026-11-13T12:00:00Z') });
  assert.ok(pistes.length >= 1);
  assert.ok(!pistes.some((p) => p.id === 'entreprise-MSFT'), 'MSFT, très corrélée, n’est pas une piste de décorrélation');
  assert.ok(pistes.every((p, i) => i === 0 || p.corr >= pistes[i - 1].corr));
});

test('performance depuis l’import comparée au MSCI World en euros', () => {
  const r = refs();
  const e = enrichir(LIGNES, r);
  const ref = { date: DATES[0], valeur: e.total * 0.9 };
  const p = performance(e, r, ref, [{ date: DATES[30], valeur: e.total * 0.95 }]);
  assert.ok(Math.abs(p.depuis_import - 11.11) < 0.01);
  assert.ok(p.msci_depuis_import != null);
  assert.equal(p.historique[0].portefeuille, 100);
  assert.ok(p.plus_value != null && p.cout > 0);
});

test('portefeuille d’exemple fictif : analyse complète sans erreur', () => {
  const r = refs();
  const lignes = portefeuillesExemple().flatMap((p) => p.lignes.map((l, i) => ({ ...l, id: `${p.nom}-${i}` })));
  const e = enrichir(lignes, r);
  assert.ok(e.total > 0);
  const exp = expositions(e, {});
  assert.ok(exp.classes.length >= 3);
  crible(e, r);
  coherence(e, r, exp);
  correlations(e, r);
  assert.equal(correlation({}, {}), null);
  assert.deepEqual(rendementsHebdo([]), {});
});
