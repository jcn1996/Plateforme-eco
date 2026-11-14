// Rubrique « Tendances fortes » du chef d'orchestre : regroupement par catégorie (logique sans navigateur).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { groupesTendances, ONGLETS_INVESTIR } from '../chef.js';

test('l’onglet « Tendances fortes » suit le panorama', () => {
  assert.deepEqual(Object.keys(ONGLETS_INVESTIR).slice(0, 2), ['panorama', 'tendances']);
});

test('tendances regroupées par catégorie, saines d’abord puis par force relative', () => {
  const tf = [
    { id: 'a', categorie: 'pays', saine: false, force_relative: 99 },
    { id: 'b', categorie: 'pays', saine: true, force_relative: 70 },
    { id: 'c', categorie: 'pays', saine: true, force_relative: 90 },
    { id: 'd', categorie: 'matieres', saine: true, force_relative: 80 },
    { id: 'e', categorie: 'entreprises', saine: true, force_relative: 75 },
  ];
  const g = groupesTendances(tf);
  assert.deepEqual(g.map(([k]) => k), ['pays', 'matieres', 'entreprises']);
  assert.deepEqual(g[0][1].map((x) => x.id), ['c', 'b', 'a']);
  assert.deepEqual(groupesTendances(undefined), []);
});
