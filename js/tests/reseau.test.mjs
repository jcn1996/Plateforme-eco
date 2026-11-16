// Tests de l'accueil « réseau d'agents » (logique sans affichage) : node --test js/tests/
// Données de test uniquement (jamais les vrais config/ et data/).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  lireChemin, lireInfo, fichiersReseau, etatAgent, calculerReseau, texteAccessible, disposition,
  separerEtiquettes, chevauchements, aRetenir,
} from '../reseau.js';

const CONFIG = {
  centre: { cle: 'chef', nom: 'Où investir', role: 'Chef d’orchestre', journal: 'chef', entrees: [], route: { type: 'investir' },
    info: { fichier: 'data/portefeuille.json', chemin: 'derniere_decision.cibles.lignes', mesure: 'longueur', modele: ['{} ligne cible', '{} lignes cibles'] } },
  agents: [
    { cle: 'risque', nom: 'Risque', journal: 'risque', entrees: ['risque'], poids: 'decision', route: { type: 'risque' },
      info: { fichier: 'data/risque.json', chemin: 'mondial.palier', mesure: 'valeur', modele: 'Palier {}' } },
    { cle: 'entreprises', nom: 'Entreprises', journal: 'entreprises', entrees: ['entreprises', 'pepites'], poids: 'decision',
      info: { fichier: 'data/chef.json', chemin: 'selections.entreprises.retenues', mesure: 'longueur', modele: ['{} retenue', '{} retenues'] } },
    { cle: 'trader', nom: 'Trader démo', journal: 'trader', poids: 'contexte', sens: 'depuis_centre',
      info: { fichier: 'data/portefeuille.json', chemin: 'statistiques.performance.depuis_debut', mesure: 'pourcentage', modele: '{}' } },
    { cle: 'alternatives', nom: 'Données alternatives', journal: 'donnees-alternatives', poids: 'contexte',
      info: { fichier: 'data/donnees_alternatives.json', chemin: 'pays', mesure: 'compte', champ: 'score', modele: ['{} pays lu', '{} pays lus'] } },
  ],
};

const CHEF = {
  date: '2026-11-16',
  entrees: [
    { cle: 'risque', libelle: 'Agent risque', etat: 'à jour', degrade: false, raisons_degrade: [] },
    { cle: 'entreprises', libelle: 'Agent entreprises', etat: 'en panne', age_h: 60.8, degrade: false, raisons_degrade: [], panne: { raison: 'exécution prévue le 2026-11-16 22:30 UTC manquée (marge de 11,2 h)' } },
    { cle: 'pepites', libelle: 'Agent entreprises (pépites)', etat: 'dégradé', degrade: true, raisons_degrade: ['Source X : perdue'], raisons_depuis: { 'Source X': '2026-11-14T15:37:00Z' } },
  ],
  selections: {
    date: '2026-11-16',
    entreprises: { retenues: [{ id: 's-A', nom: 'Alpha', ticker: 'A', score: 70 }, { id: 's-B', nom: 'Bêta', ticker: 'B', score: 95 }, { id: 's-C', nom: 'Gamma', ticker: 'C', score: 80 }] },
    matieres: { retenues: [{ id: 'matiere-or', cle: 'or', nom: 'Or', score: 90 }] },
    paris_pays: {
      candidats: [{ id: 'pays-PL', cle: 'PL', nom: 'Pologne', entree_ok: true, sortie: false }, { id: 'pays-CO', cle: 'CO', nom: 'Colombie', entree_ok: true, sortie: true }],
      a_revendre: [{ id: 'pays-JP', cle: 'JP', nom: 'Japon' }],
    },
  },
};

test('lireChemin : objets, rangs de liste, chemin vide', () => {
  const o = { a: { b: [{ c: 3 }] } };
  assert.equal(lireChemin(o, 'a.b.0.c'), 3);
  assert.equal(lireChemin(o, 'a.x.y'), undefined);
  assert.equal(lireChemin(o, ''), o);
  assert.equal(lireChemin(null, 'a'), undefined);
});

test('lireInfo : longueur, compte, pourcentage, valeur, accord singulier/pluriel', () => {
  assert.equal(lireInfo({ chemin: 'l', mesure: 'longueur', modele: ['{} retenue', '{} retenues'] }, { l: [1] }).texte, '1 retenue');
  assert.equal(lireInfo({ chemin: 'l', mesure: 'longueur', modele: ['{} retenue', '{} retenues'] }, { l: [1, 2] }).texte, '2 retenues');
  assert.equal(lireInfo({ chemin: 'l', mesure: 'longueur', modele: ['{} retenue', '{} retenues'] }, { l: [] }).texte, '0 retenue');
  assert.equal(lireInfo({ chemin: '', mesure: 'longueur', modele: '{} cotations' }, [1, 2, 3]).texte, '3 cotations');
  assert.equal(lireInfo({ chemin: 'p', mesure: 'compte', champ: 'score', modele: ['{} pays lu', '{} pays lus'] }, { p: [{ score: 1 }, { score: null }, { score: 0 }] }).texte, '2 pays lus');
  assert.equal(lireInfo({ chemin: 'v', mesure: 'pourcentage', modele: '{}' }, { v: 1.63 }).texte, '+1,6 %');
  assert.equal(lireInfo({ chemin: 'v', mesure: 'pourcentage', modele: '{}' }, { v: -2.04 }).texte, '−2,0 %');
  assert.equal(lireInfo({ chemin: 'v', mesure: 'valeur', modele: 'Palier {}' }, { v: 'Vigilance' }).texte, 'Palier Vigilance');
  assert.equal(lireInfo({ chemin: 'v', mesure: 'valeur', modele: ['{} signal gardé', '{} signaux gardés'] }, { v: 2 }).texte, '2 signaux gardés');
  // Donnée absente : pas de texte (la bulle affiche « n. d. »)
  assert.equal(lireInfo({ chemin: 'x', mesure: 'valeur' }, {}).texte, null);
  assert.equal(lireInfo({ chemin: 'x', mesure: 'pourcentage' }, { x: 'abc' }).texte, null);
});

test('fichiersReseau : fichiers cités, sans doublon', () => {
  assert.deepEqual(fichiersReseau(CONFIG), ['data/portefeuille.json', 'data/risque.json', 'data/chef.json', 'data/donnees_alternatives.json']);
});

test('etatAgent : trois états (en panne > dégradé > OK), avec la raison et la date pour chacun', () => {
  assert.equal(etatAgent({ statutJournal: 'ok' }).etat, 'ok');
  assert.equal(etatAgent({ statutJournal: 'pause' }).etat, 'ok');
  const panne = etatAgent({ statutJournal: 'panne', journal: { derniere_execution: '2026-11-14T10:37:27Z' }, entrees: [{ cle: 'x', etat: 'en panne', panne: { raison: 'exécution prévue manquée' } }] });
  assert.equal(panne.etat, 'panne');
  assert.equal(panne.raisons.length, 2);
  const echec = etatAgent({ statutJournal: 'panne', journal: { derniere_execution: '2026-11-14T10:37:27Z', derniere_tentative: { date: '2026-11-15T10:00:00Z', statut: 'echec', raison: 'HTTP 500' } } });
  assert.match(echec.raisons[0], /en échec.*HTTP 500/);
  // Entrée du chef en panne (exécution prévue manquée) ou manquante : en panne, plus d'état « périmé »
  const ep = etatAgent({ statutJournal: 'ok', entrees: [{ cle: 'x', libelle: 'Agent X', etat: 'en panne', panne: { raison: 'exécution prévue le 2026-11-16 22:30 UTC manquée' } }] });
  assert.equal(ep.etat, 'panne');
  assert.match(ep.raisons[0], /Agent X : exécution prévue le 2026-11-16 22:30 UTC manquée/);
  assert.equal(etatAgent({ entrees: [{ cle: 'x', etat: 'manquante' }] }).etat, 'panne');
  // Dégradé : quelle source, depuis quand
  const degrade = etatAgent({ statutJournal: 'ok', entrees: [{ cle: 'x', etat: 'dégradé', degrade: true, raisons_degrade: ['Argentine · Flux : perdue globalx'], raisons_depuis: { 'Argentine · Flux': '2026-11-14T15:00:00Z' } }] });
  assert.equal(degrade.etat, 'degrade');
  assert.deepEqual(degrade.raisons, ['Argentine · Flux : perdue globalx — depuis le 14/11']);
  assert.equal(etatAgent({ statutJournal: 'degrade', journal: { raisons: ['Indicateur sans source'] } }).raisons[0], 'Indicateur sans source');
});

test('calculerReseau : infos lues dans les données, états, poids et sens des liens', () => {
  const r = calculerReseau(CONFIG, {
    sources: {
      'data/chef.json': CHEF,
      'data/risque.json': { mondial: { palier: 'Vigilance' } },
      'data/portefeuille.json': { derniere_decision: { cibles: { lignes: Array(15).fill({}) } }, statistiques: { performance: { depuis_debut: 1.63 } } },
      'data/donnees_alternatives.json': null, // fichier absent
    },
    sante: { risque: { statut: 'ok' }, trader: { statut: 'panne', journal: null } },
    entrees: CHEF.entrees,
  });
  assert.equal(r.centre.info, '15 lignes cibles');
  assert.equal(r.centre.centre, true);
  const par = Object.fromEntries(r.agents.map((a) => [a.cle, a]));
  assert.equal(par.risque.info, 'Palier Vigilance');
  assert.equal(par.risque.etat, 'ok');
  assert.equal(par.risque.poids, 'decision');
  assert.equal(par.entreprises.info, '3 retenues');
  assert.equal(par.entreprises.etat, 'panne'); // exécution prévue manquée (et pépites dégradée)
  assert.ok(par.entreprises.raisons.some((r) => /depuis le 14\/11/.test(r)));
  assert.equal(par.trader.info, '+1,6 %');
  assert.equal(par.trader.etat, 'panne');
  assert.equal(par.trader.sens, 'depuis_centre');
  assert.equal(par.trader.poids, 'contexte');
  assert.equal(par.alternatives.info, 'n. d.');
  // Fichier pas encore lu : « … »
  const avant = calculerReseau(CONFIG, { sources: {} });
  assert.equal(avant.agents[0].info, '…');
  assert.equal(avant.agents[0].chargee, false);
});

test('texteAccessible : nom, information, poids et état en toutes lettres', () => {
  const r = calculerReseau(CONFIG, { sources: { 'data/risque.json': { mondial: { palier: 'Tension' } } }, sante: { risque: { statut: 'degrade' } } });
  const t = texteAccessible(r.agents[0]);
  assert.match(t, /Risque · Palier Tension · pèse dans la décision · état : Dégradé/);
  assert.match(texteAccessible(r.centre), /Où investir, Chef d’orchestre/);
});

test('disposition : 11 agents sur une ellipse, le premier en haut, profondeur alternée', () => {
  const p = disposition(11);
  assert.equal(p.length, 11);
  assert.ok(Math.abs(p[0].x) < 1e-9 && Math.abs(p[0].y - 1) < 1e-9);
  p.forEach((q) => assert.ok(Math.abs(Math.hypot(q.x, q.y) - 1) < 1e-9));
  assert.ok(p.some((q) => q.z > 0) && p.some((q) => q.z < 0));
});

test('separerEtiquettes : aucun libellé superposé, bulles évitées, cadre de 390 px respecté', () => {
  // 12 libellés de 94 × 56 px serrés au centre d'une scène de 390 × 500 px (pire cas)
  const libelles = Array.from({ length: 12 }, (_, i) => ({ cle: `n${i}`, x: 150 + (i % 3) * 8, y: 200 + (i % 4) * 6, l: 94, h: 56 }));
  const bulles = [{ proprietaire: 'n0', x: 180, y: 120, l: 30, h: 30 }, { proprietaire: 'autre', x: 40, y: 40, l: 30, h: 30 }];
  separerEtiquettes(libelles, bulles, { l: 390, h: 500 });
  assert.deepEqual(chevauchements(libelles), []);
  libelles.forEach((e) => assert.ok(e.x >= 2 && e.x + e.l <= 388 && e.y >= 2 && e.y + e.h <= 498, `${e.cle} hors du cadre`));
  // Disposition réelle : ellipse de la scène, libellés sous leur bulle
  const pos = disposition(11);
  const reel = [{ cle: 'chef', x: 195 - 59, y: 260 + 40, l: 118, h: 45 }, ...pos.map((q, i) => ({ cle: `a${i}`, x: 195 + q.x * 145 - 47, y: 230 - q.y * 200 + 20, l: 94, h: 56 }))];
  separerEtiquettes(reel, [], { l: 390, h: 520 });
  assert.deepEqual(chevauchements(reel), []);
});

test('aRetenir (ancienne sortie, sans liste unique) : sélections par score, paris pays, à revendre, alerte du jour', () => {
  const r = aRetenir(CHEF, [{ rang: 2, titre: 'Deuxième' }, { rang: 1, titre: 'Événement grave', pays: 'US' }], { max: 2 });
  assert.equal(r.date, '2026-11-16');
  assert.deepEqual(r.entreprises.lignes.map((x) => x.nom), ['Bêta', 'Gamma']);
  assert.equal(r.entreprises.total, 3);
  assert.deepEqual(r.matieres.lignes.map((x) => x.cle), ['or']);
  assert.deepEqual(r.paris.lignes.map((x) => x.code), ['PL']); // la Colombie est en sortie
  assert.deepEqual(r.aRevendre.lignes.map((x) => x.nom), ['Japon']);
  assert.equal(r.alerte.titre, 'Événement grave');
  assert.deepEqual(r.alerte.route, { type: 'pays', id: 'US' });
  // Liste unique : seules ses lignes, dans son ordre ; sorties du mois
  const avecListe = { ...CHEF, liste: { revise_le: '2026-11-02', lignes: [
    { id: 'selection-B', categorie: 'entreprises', nom: 'Bêta', ticker: 'B' }, { id: 'matiere-cuivre', categorie: 'matieres', nom: 'Cuivre', cle: 'cuivre' },
    { id: 'pays-PL', categorie: 'pays', nom: 'Pologne', cle: 'PL', symbole: 'EPOL' }],
  mouvements: [{ date: '2026-11-10', sens: 'sortie', id: 'pays-CO', nom: 'Colombie', categorie: 'pays', texte: 'Sortie · Colombie — tendance cassée' },
    { date: '2026-11-02', sens: 'entrée', id: 'selection-B', nom: 'Bêta', categorie: 'entreprises', texte: 'Entrée · Bêta' }] } };
  const l = aRetenir(avecListe, []);
  assert.equal(l.date, '2026-11-02');
  assert.deepEqual(l.entreprises.lignes.map((x) => x.nom), ['Bêta']);
  assert.deepEqual(l.matieres.lignes.map((x) => x.cle), ['cuivre']);
  assert.deepEqual(l.paris.lignes.map((x) => x.code), ['PL']);
  assert.deepEqual(l.aRevendre.lignes.map((x) => [x.nom, x.code]), [['Colombie', 'CO']]);
  // Sans chef d'orchestre ni alerte : listes vides
  const vide = aRetenir(null, []);
  assert.equal(vide.entreprises.total, 0);
  assert.equal(vide.alerte, null);
});

test('calculerReseau : teinte propre de chaque agent (format #rrggbb), null sinon', () => {
  const config = {
    centre: { ...CONFIG.centre, couleur: '#00E5FF' },
    agents: [{ ...CONFIG.agents[0], couleur: '#ff3fd2' }, { ...CONFIG.agents[1], couleur: 'bleu' }, { ...CONFIG.agents[2] }],
  };
  const r = calculerReseau(config, { sources: {} });
  assert.equal(r.centre.couleur, '#00e5ff');
  assert.deepEqual(r.agents.map((a) => a.couleur), ['#ff3fd2', null, null]);
});
