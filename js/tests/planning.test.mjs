// Tests du planning des agents (dates simulées) : node --test js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { situationPlanning, intervalleBase, heureParis, seuils } from '../planning.js';

const MARCHES = { crons: ['7,22,37,52 7-21 * * 1-5', '7 22 * * 1-5', '7 * * * 0,6'], fuseau: 'UTC' };
const PAYS = { crons: ['11 6 * * *'], fuseau: 'UTC' };
const t = (iso) => Date.parse(iso);
const marches = (derniere) => ({ derniere_execution: derniere, planning: MARCHES });
const pays = (derniere) => ({ derniere_execution: derniere, planning: PAYS });

test('intervalle de base et seuils', () => {
  assert.equal(intervalleBase(MARCHES.crons), 15);
  assert.equal(intervalleBase(PAYS.crons), 1440);
  assert.deepEqual(seuils(15), { retard: 45, panne: 120 });
  assert.deepEqual(seuils(1440), { retard: 120, panne: 1560 });
});

test('journée : OK, en retard après 45 min, en panne après 2 h', () => {
  // Mardi 3/11, dernière exécution 10 h 08 UTC
  assert.equal(situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T10:30:00Z')).etat, 'ok');
  // 10 h 22 manque depuis 40 min : encore OK (retards habituels de GitHub)
  assert.equal(situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T11:02:00Z')).etat, 'ok');
  const retard = situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T11:10:00Z'));
  assert.equal(retard.etat, 'retard');
  assert.equal(retard.manquante, t('2026-11-03T10:22:00Z'));
  assert.equal(situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T12:21:00Z')).etat, 'retard');
  assert.equal(situationPlanning(marches('2026-11-03T10:08:30Z'), t('2026-11-03T12:23:00Z')).etat, 'panne');
});

test('nuit : en pause après 22 h 07 UTC, prochaine mise à jour le matin', () => {
  const s = situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T02:00:00Z'));
  assert.equal(s.etat, 'pause');
  assert.equal(s.prochaine, t('2026-11-04T07:07:00Z'));
  assert.equal(heureParis(s.prochaine), 'mer. 8 h 07');
  // Encore en pause juste avant 7 h 07, puis OK si l'exécution arrive
  assert.equal(situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T07:06:00Z')).etat, 'pause');
  assert.equal(situationPlanning(marches('2026-11-04T07:08:00Z'), t('2026-11-04T07:10:00Z')).etat, 'ok');
  // L'exécution de 7 h 07 manque : en retard à 7 h 53, en panne à 9 h 08
  assert.equal(situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T07:30:00Z')).etat, 'ok');
  assert.equal(situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T07:53:00Z')).etat, 'retard');
  assert.equal(situationPlanning(marches('2026-11-03T22:08:00Z'), t('2026-11-04T09:08:00Z')).etat, 'panne');
  // L'exécution de 22 h 07 a manqué : pas de pause, le retard est signalé
  assert.equal(situationPlanning(marches('2026-11-03T21:53:00Z'), t('2026-11-03T23:00:00Z')).etat, 'retard');
});

test('week-end : horaire, pas de fausse alarme ; nuit du dimanche en pause jusqu’à lundi 8 h 07 (Paris)', () => {
  // Samedi 7/11 à 13 h 50 UTC, dernière exécution 13 h 08 : OK (rythme horaire)
  assert.equal(situationPlanning(marches('2026-11-07T13:08:00Z'), t('2026-11-07T13:50:00Z')).etat, 'ok');
  // Ancienne règle (2 × 15 min) : aurait affiché « en panne »
  assert.equal(situationPlanning(marches('2026-11-07T13:08:00Z'), t('2026-11-07T14:06:00Z')).etat, 'ok');
  assert.equal(situationPlanning(marches('2026-11-07T13:08:00Z'), t('2026-11-07T15:00:00Z')).etat, 'retard');
  // Vendredi soir 22 h 07 → samedi 0 h 07 : 2 h d'écart, pas une pause
  assert.equal(situationPlanning(marches('2026-11-06T22:08:00Z'), t('2026-11-06T23:30:00Z')).etat, 'ok');
  // Dimanche 23 h 07 → lundi 7 h 07 : pause
  const s = situationPlanning(marches('2026-11-08T23:08:00Z'), t('2026-11-09T03:00:00Z'));
  assert.equal(s.etat, 'pause');
  assert.equal(heureParis(s.prochaine), 'lun. 8 h 07');
});

test('agent quotidien : en retard après 2 h, en panne après 26 h, jamais en pause', () => {
  assert.equal(situationPlanning(pays('2026-11-02T06:15:00Z'), t('2026-11-03T06:00:00Z')).etat, 'ok');
  assert.equal(situationPlanning(pays('2026-11-02T06:15:00Z'), t('2026-11-03T08:00:00Z')).etat, 'ok');
  assert.equal(situationPlanning(pays('2026-11-02T06:15:00Z'), t('2026-11-03T08:12:00Z')).etat, 'retard');
  assert.equal(situationPlanning(pays('2026-11-02T06:15:00Z'), t('2026-11-04T08:10:00Z')).etat, 'retard');
  assert.equal(situationPlanning(pays('2026-11-02T06:15:00Z'), t('2026-11-04T08:12:00Z')).etat, 'panne');
  // Lancé à la main dans l'après-midi : la prochaine prévue est le lendemain 6 h 11
  assert.equal(situationPlanning(pays('2026-11-02T18:25:00Z'), t('2026-11-03T07:00:00Z')).etat, 'ok');
});

test('heure d’été à Paris', () => {
  assert.equal(heureParis(t('2026-06-01T07:07:00Z')), 'lun. 9 h 07');
});

test('ancien journal sans planning : prochaine_prevue', () => {
  const s = { derniere_execution: '2026-11-03T10:00:00Z', prochaine_prevue: '2026-11-03T10:15:00Z', intervalle_min: 15 };
  assert.equal(situationPlanning(s, t('2026-11-03T10:40:00Z')).etat, 'ok');
  assert.equal(situationPlanning(s, t('2026-11-03T11:01:00Z')).etat, 'retard');
  assert.equal(situationPlanning(s, t('2026-11-03T12:16:00Z')).etat, 'panne');
  assert.equal(situationPlanning({}, t('2026-11-03T12:16:00Z')).etat, 'panne');
});
