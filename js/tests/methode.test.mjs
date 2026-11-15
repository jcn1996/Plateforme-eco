// Nouvelle méthode (backtest) : paris pays et pays sans classement (Où investir), marqueur du changement de méthode
// (Portefeuille démo), écran « Signaux en observation ». Logique testée sans navigateur.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { lignesParisPays, paysSansClassement, MENTION_PAYS } from '../chef.js';
import { indiceChangement, POCHES } from '../portefeuille.js';
import { signauxFiltres, signeObs, TYPES_OBSERVATION } from '../observation.js';

test('paris pays : candidats et pays détenus « à revendre »', () => {
  const chef = { selections: { paris_pays: { candidats: [{ id: 'pays-JP' }], a_revendre: [{ id: 'pays-BR' }], regle: 'r' } } };
  const r = lignesParisPays(chef);
  assert.deepEqual(r.candidats.map((x) => x.id), ['pays-JP']);
  assert.deepEqual(r.aRevendre.map((x) => x.id), ['pays-BR']);
  assert.deepEqual(lignesParisPays(undefined), { candidats: [], aRevendre: [], detenus: [], regle: undefined });
});

test('pays présentés sans classement, avec la mention du backtest', () => {
  const l = [{ nom: 'Japon', score: 80 }, { nom: 'Allemagne', score: 40 }, { nom: 'Égypte', score: 60 }];
  assert.deepEqual(paysSansClassement(l).map((x) => x.nom), ['Allemagne', 'Égypte', 'Japon']);
  assert.equal(l[0].nom, 'Japon', 'la liste d’origine n’est pas modifiée');
  assert.equal(MENTION_PAYS, 'contexte économique, non prédictif d’après le backtest');
});

test('marqueur du changement de méthode sur le graphique', () => {
  const h = [{ date: '2026-11-05' }, { date: '2026-11-06' }, { date: '2026-11-09' }, { date: '2026-11-10' }];
  assert.equal(indiceChangement(h, '2026-11-09'), 2);
  assert.equal(indiceChangement(h, '2026-11-07'), 2, 'week-end : premier jour valorisé après le changement');
  assert.equal(indiceChangement(h, '2026-12-01'), null);
  assert.equal(indiceChangement([], '2026-11-09'), null);
  assert.equal(POCHES.pays, 'ETF pays (paris)');
});

test('signaux en observation : filtre par type, plus récents d’abord', () => {
  const s = [{ type: 'achat_dirigeant', date_signal: '2026-11-01' }, { type: 'revision_analystes', date_signal: '2026-11-03' },
    { type: 'achat_dirigeant', date_signal: '2026-11-05', date_depart: '2026-11-06' }];
  assert.deepEqual(signauxFiltres(s).map((x) => x.date_signal), ['2026-11-05', '2026-11-03', '2026-11-01']);
  assert.deepEqual(signauxFiltres(s, 'achat_dirigeant').map((x) => x.date_signal), ['2026-11-05', '2026-11-01']);
  assert.equal(signauxFiltres(undefined).length, 0);
  assert.equal(Object.keys(TYPES_OBSERVATION).length, 3);
  assert.equal(signeObs(null), 'n. d.');
  assert.match(signeObs(-2.25, 1, ' pt'), /^−2,3 pt$|^−2,2 pt$/);
});
