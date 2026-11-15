// Écran « Backtest » : logique sans navigateur (tri des signaux, verdicts, nombres).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { trierSignaux, classeVerdict, classeCombinaison, sansGras, signe, numeroPullRequest, statutRecalibrage, alerteRecalibrage } from '../backtest.js';

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

test('verdicts des combinaisons et résumé sans gras', () => {
  assert.equal(classeCombinaison('Confirmée'), 'bt-verdict--garder');
  assert.equal(classeCombinaison('Prometteuse (non significative)'), 'bt-verdict--alleger');
  assert.equal(classeCombinaison('Non confirmée'), 'bt-verdict--supprimer');
  assert.equal(sansGras('1. **Ce qui anticipe** : rien.'), '1. Ce qui anticipe : rien.');
  assert.equal(sansGras(undefined), '');
});

const PR = 'https://github.com/jcn1996/Plateforme-eco/pull/70';
const hist = [
  { mois: '2027-01', jour: '2027-01-03', statut: 'à valider', pull_request: PR, texte: 'Recalibrage du mois à valider : retrait de « A + B » (entreprises)' },
  { mois: '2026-12', jour: '2026-12-03', statut: 'rien à modifier', pull_request: null, texte: 'Recalibrage du mois : rien à modifier' },
  { mois: '2026-11', jour: '2026-11-15', statut: 'validé', pull_request: 'https://github.com/jcn1996/Plateforme-eco/pull/62', texte: 'Mise en service' },
];

test('numéro de pull request : seulement pour le dépôt de la plateforme', () => {
  assert.equal(numeroPullRequest(PR), 70);
  assert.equal(numeroPullRequest('https://github.com/autre/depot/pull/3'), null);
  assert.equal(numeroPullRequest(null), null);
});

test('statut d’un recalibrage corrigé par l’état de sa pull request', () => {
  assert.equal(statutRecalibrage(hist[0]), 'à valider');
  assert.equal(statutRecalibrage(hist[0], 'ouverte'), 'à valider');
  assert.equal(statutRecalibrage(hist[0], 'fusionnée'), 'validé');
  assert.equal(statutRecalibrage(hist[0], 'fermée'), 'non validé');
  assert.equal(statutRecalibrage(hist[1], 'fusionnée'), 'rien à modifier', 'seuls les recalibrages en attente changent de statut');
});

test('alerte « Recalibrage à valider » avec le lien de la pull request, et plus d’alerte une fois fusionnée', () => {
  const a = alerteRecalibrage(hist);
  assert.equal(a.titre, 'Recalibrage à valider');
  assert.equal(a.lien, PR);
  assert.match(a.texte, /retrait de « A \+ B »/);
  assert.equal(alerteRecalibrage(hist, { [PR]: 'fusionnée' }), null);
  assert.equal(alerteRecalibrage(hist.slice(1)), null, 'rien à modifier : pas d’alerte');
  assert.equal(alerteRecalibrage([{ ...hist[0], pull_request: null }]), null, 'pas encore de pull request : pas d’alerte');
});
