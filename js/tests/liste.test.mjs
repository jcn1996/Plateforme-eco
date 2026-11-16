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
