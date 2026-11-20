// Liste unique du chef d'orchestre : onglets de « Où investir », regroupement par catégorie, résultat au backtest.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ONGLETS_INVESTIR, lignesListe, texteBacktest, moisFr } from '../chef.js';

test('« Où investir » : la liste d’abord, puis les entrées et sorties du mois, puis le contexte', () => {
  assert.deepEqual(Object.keys(ONGLETS_INVESTIR), ['liste', 'mouvements', 'contexte']);
});

test('lignes regroupées : entreprises, matières premières, paris pays', () => {
  const chef = { liste: { lignes: [
    { id: 'pays-PL', categorie: 'pays', nom: 'Pologne' }, { id: 'selection-A', categorie: 'entreprises', nom: 'Alpha' },
    { id: 'matiere-cuivre', categorie: 'matieres', nom: 'Cuivre' }, { id: 'selection-B', categorie: 'entreprises', nom: 'Bêta' }] } };
  const g = lignesListe(chef);
  assert.deepEqual(g.map(([k]) => k), ['entreprises', 'matieres', 'pays']);
  assert.deepEqual(g[0][2].map((x) => x.nom), ['Alpha', 'Bêta']);
  assert.deepEqual(lignesListe(null), []);
});

test('résultat au backtest : écart contre l’indice et part des gagnants', () => {
  const t = texteBacktest({ combinaison: 'Goodwill / actif + Rendement du FCF', ecart_indice_pct: 2.2, gagnants_pct: 46.8 });
  assert.match(t, /Goodwill \/ actif \+ Rendement du FCF : \+2,2 pt\/an contre l’indice, 47 % des actifs retenus ont battu l’indice \(hors échantillon\)/);
  assert.match(texteBacktest({ combinaison: 'X', ecart_indice_pct: -3.36 }), /−3,4 pt\/an.*part des gagnants n\. d\./);
});

test('mois en clair', () => {
  assert.equal(moisFr('2026-12'), 'décembre 2026');
  assert.equal(moisFr(null), 'n. d.');
});

test('fiche lisible : 5 blocs de la fiche du chef, repli sans rien inventer pour une ancienne sortie', async () => {
  const { contenuFiche } = await import('../chef.js');
  const l = { id: 'selection-A', nom: 'Alpha', conviction: 'forte', fiche: {
    entete: { verdict: 'Cash abondant ; réserve : bilan fragile.', poids_texte: '6,7 % du portefeuille démo', conviction_texte: 'conviction forte (3 combinaisons)' },
    pour: ['Le cash-flow disponible représente 16,9 % de la valeur en Bourse par an.'], contre: ['Z-score d’Altman de −1,07.'],
    momentum: { mot: 'défavorable', texte: '3 mois −2,3 % · 6 mois −0,8 % · 12 mois −27,3 %', contradiction: 'Le momentum contredit le dossier.' },
    sortie: 'Sortie si…', base_statistique: { combinaisons: [{ combinaison: 'X', ecart_indice_pct: 2.2 }] } } };
  const c = contenuFiche(l);
  assert.equal(c.verdict, 'Cash abondant ; réserve : bilan fragile.');
  assert.equal(c.momentum.mot, 'défavorable');
  assert.ok(c.momentum.contradiction);
  assert.equal(c.base.combinaisons.length, 1);
  const ancien = contenuFiche({ nom: 'B', combinaisons_libelles: ['Niveau historique + Positionnement CFTC'], sortie_si: 'x' });
  assert.match(ancien.verdict, /Niveau historique/);
  assert.equal(ancien.momentum.mot, 'inconnu');
  assert.deepEqual(ancien.contre, ['Donnée manquante.']);
});
