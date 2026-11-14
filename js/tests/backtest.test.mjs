// Écran « Backtest » : logique sans navigateur (tri des signaux, verdicts, nombres).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { trierSignaux, classeVerdict, signe } from '../backtest.js';

const sig = (verdict, ic) => ({ verdict, echantillons: { verification: { ic_moyen: ic } } });

test('les indicateurs sont triés par verdict puis par IC hors échantillon, les notes à la fin', () => {
  const signaux = {
    note_globale: sig('Alléger', 0.01),
    taux_reel: sig('Supprimer', -0.05),
    momentum: sig('Garder', 0.04),
    inflation: sig('Alléger', 0.02),
    devise_3m: sig('Alléger', 0.03),
    croissance_pib: sig('Données insuffisantes', null),
    note_recalibree: sig('Garder', 0.05),
  };
  assert.deepEqual(trierSignaux(signaux), ['momentum', 'devise_3m', 'inflation', 'taux_reel', 'croissance_pib', 'note_globale', 'note_recalibree']);
  assert.deepEqual(trierSignaux(undefined), []);
});

test('classe CSS de chaque verdict', () => {
  assert.equal(classeVerdict('Garder'), 'bt-verdict--garder');
  assert.equal(classeVerdict('Alléger'), 'bt-verdict--alleger');
  assert.equal(classeVerdict('Supprimer'), 'bt-verdict--supprimer');
  assert.equal(classeVerdict('Données insuffisantes'), 'bt-verdict--insuffisant');
});

test('nombres signés à la française', () => {
  assert.equal(signe(null), 'n. d.');
  assert.equal(signe(undefined), 'n. d.');
  assert.match(signe(0.0345, 3), /^\+0,0(34|35)$/);
  assert.match(signe(-1.5, 1, ' %'), /^−1,5 %$/);
  assert.equal(signe(0, 1), '0,0');
});
