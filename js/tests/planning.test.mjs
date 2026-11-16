// Tests du planning des agents (dates simulées) : node --test js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { situationPlanning, intervalleBase, heureParis, marge, MARGE_MIN, MARGE_MAX } from '../planning.js';

const MARCHES = { crons: ['7,22,37,52 7-21 * * 1-5', '7 22 * * 1-5', '7 * * * 0,6'], fuseau: 'UTC' };
const PAYS = { crons: ['11 6 * * *'], fuseau: 'UTC' };
const t = (iso) => Date.parse(iso);
const marches = (derniere) => ({ derniere_execution: derniere, planning: MARCHES });
const pays = (derniere) => ({ derniere_execution: derniere, planning: PAYS });

test('intervalle de base et marge propre à chaque agent', () => {
  assert.equal(intervalleBase(MARCHES.crons), 15);
  assert.equal(intervalleBase(PAYS.crons), 1440);
  // Exécution courte : marge minimale de 3 h
  assert.equal(marge(marches('2026-11-03T10:08:30Z')), MARGE_MIN);
  // Agent matières premières : créneau vendredi 22 h 15, fin samedi 2 h 32 (4 h 17) → 1,5 × 4 h 17 ≈ 6 h 25
  const MP = { crons: ['15 22 * * 1-5'] };
  assert.equal(marge({ derniere_execution: '2026-11-14T02:32:40Z', planning: MP }), 387);
  // Agent entreprises : créneau samedi 3 h 10, fin 10 h 37 → plafonné à 12 h au plus
  const ENT = { crons: ['30 22 * * 1-5', '10 3 * * 6'] };
  assert.equal(marge({ derniere_execution: '2026-11-14T10:37:27Z', planning: ENT }), 671);
  assert.equal(marge({ derniere_execution: '2026-11-14T23:37:27Z', planning: ENT }), MARGE_MAX);
});

test('journée : OK pendant la marge, en panne au-delà (pas d’état intermédiaire)', () => {
  // Mardi 3/11, dernière exécution 10 h 08 UTC
  assert.equal(situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T10:30:00Z')).etat, 'ok');
  const s = situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T12:00:00Z'));
  assert.equal(s.etat, 'ok'); // 10 h 22 manque depuis 1 h 38 : dans la marge de 3 h
  assert.equal(s.manquante, t('2026-11-03T10:22:00Z'));
  assert.equal(situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T13:21:00Z')).etat, 'ok');
  assert.equal(situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T13:23:00Z')).etat, 'panne');
});

test('nuit : en pause après 22 h 07 UTC, prochaine mise à jour le matin', () => {
  const s = situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T02:00:00Z'));
  assert.equal(s.etat, 'pause');
  assert.equal(s.prochaine, t('2026-11-04T07:07:00Z'));
  assert.equal(heureParis(s.prochaine), 'mer. 8 h 07');
  assert.equal(situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T07:06:00Z')).etat, 'pause');
  assert.equal(situationPlanning(marches('2026-11-04T07:08:00Z'), t('2026-11-04T07:10:00Z')).etat, 'ok');
  // L'exécution de 7 h 07 manque : en panne après 10 h 07
  assert.equal(situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T09:00:00Z')).etat, 'ok');
  assert.equal(situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T10:08:00Z')).etat, 'panne');
});

test('week-end : pas de fausse alarme ; nuit du dimanche en pause jusqu’à lundi 8 h 07 (Paris)', () => {
  assert.equal(situationPlanning(marches('2026-11-07T13:08:00Z'), t('2026-11-07T13:50:00Z')).etat, 'ok');
  assert.equal(situationPlanning(marches('2026-11-07T13:08:00Z'), t('2026-11-07T16:00:00Z')).etat, 'ok');
  assert.equal(situationPlanning(marches('2026-11-07T13:08:00Z'), t('2026-11-07T17:10:00Z')).etat, 'panne');
  assert.equal(situationPlanning(marches('2026-11-06T22:08:00Z'), t('2026-11-06T23:30:00Z')).etat, 'ok');
  const s = situationPlanning(marches('2026-11-08T23:08:00Z'), t('2026-11-09T03:00:00Z'));
  assert.equal(s.etat, 'pause');
  assert.equal(heureParis(s.prochaine), 'lun. 8 h 07');
});

test('agent quotidien : en panne 3 h après l’exécution manquée, jamais en pause', () => {
  assert.equal(situationPlanning(pays('2026-11-02T06:15:00Z'), t('2026-11-03T06:00:00Z')).etat, 'ok');
  assert.equal(situationPlanning(pays('2026-11-02T06:15:00Z'), t('2026-11-03T09:10:00Z')).etat, 'ok');
  assert.equal(situationPlanning(pays('2026-11-02T06:15:00Z'), t('2026-11-03T09:12:00Z')).etat, 'panne');
  // Lancé à la main dans l'après-midi : la prochaine prévue est le lendemain 6 h 11
  assert.equal(situationPlanning(pays('2026-11-02T18:25:00Z'), t('2026-11-03T07:00:00Z')).etat, 'ok');
});

test('agent de quelques exécutions par semaine : jamais en panne entre deux exécutions prévues', () => {
  const ENT = { crons: ['30 22 * * 1-5', '10 3 * * 6'] };
  const s = { derniere_execution: '2026-11-14T10:37:27Z', planning: ENT };
  // Lundi 16/11 à 17 h : 54 h sans exécution, mais la prochaine prévue est lundi 22 h 30 → à jour
  assert.notEqual(situationPlanning(s, t('2026-11-16T17:00:00Z')).etat, 'panne');
  // Mardi 17/11 à 8 h : exécution de lundi 22 h 30 en cours (marge 11 h 11) → à jour ; à 10 h, en panne
  assert.equal(situationPlanning(s, t('2026-11-17T08:00:00Z')).etat, 'ok');
  assert.equal(situationPlanning(s, t('2026-11-17T10:00:00Z')).etat, 'panne');
});

test('heure d’été à Paris', () => {
  assert.equal(heureParis(t('2026-06-01T07:07:00Z')), 'lun. 9 h 07');
});

test('ancien journal sans planning : prochaine_prevue', () => {
  const s = { derniere_execution: '2026-11-03T10:00:00Z', prochaine_prevue: '2026-11-03T10:15:00Z', intervalle_min: 15 };
  assert.equal(situationPlanning(s, t('2026-11-03T12:00:00Z')).etat, 'ok');
  assert.equal(situationPlanning(s, t('2026-11-03T13:16:00Z')).etat, 'panne');
  assert.equal(situationPlanning({}, t('2026-11-03T12:16:00Z')).etat, 'panne');
});

test('agent mensuel (backtest) : prochaine exécution le mois suivant', () => {
  const MENSUEL = { crons: ['17 4 3 * *'], fuseau: 'UTC' };
  const base = intervalleBase(MENSUEL.crons);
  assert.equal(base, 28 * 24 * 60);
  const ok = situationPlanning({ derniere_execution: '2026-11-03T07:40:00Z', planning: MENSUEL }, t('2026-11-20T12:00:00Z'));
  assert.equal(ok.prochaine, t('2026-12-03T04:17:00Z'));
  assert.equal(ok.etat, 'pause');
  // Exécution de plusieurs heures (3 h 23 la dernière fois → marge de 5 h 05)
  assert.equal(situationPlanning({ derniere_execution: '2026-11-03T07:40:00Z', planning: MENSUEL }, t('2026-12-03T09:00:00Z')).etat, 'ok');
  assert.equal(situationPlanning({ derniere_execution: '2026-11-03T07:40:00Z', planning: MENSUEL }, t('2026-12-03T09:30:00Z')).etat, 'panne');
});

test('panne prolongée : agent quotidien sans exécution réussie depuis plus de 24 h (alertes du chef)', async () => {
  const { panneProlongee, estQuotidien } = await import('../planning.js');
  const PAYS_REEL = { crons: ['11 6 * * *', '7 2 * * 2-6'], fuseau: 'UTC' };
  const s = { derniere_execution: '2026-11-09T16:05:36Z', planning: PAYS_REEL };
  assert.equal(estQuotidien(PAYS_REEL.crons, t('2026-11-09T16:05:36Z')), true);
  assert.equal(panneProlongee(s, t('2026-11-10T10:00:00Z')), null);
  assert.deepEqual(panneProlongee(s, t('2026-11-14T17:00:00Z')), { depuis: t('2026-11-09T16:05:36Z'), heures: 121 });
});
