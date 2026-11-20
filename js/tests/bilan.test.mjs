// Bilan du mois et « Mes portefeuilles face à la liste » : logique sans navigateur.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ecarts, moisLong, signeBilan } from '../bilan.js';
import { faceALaListe } from '../portefeuilles-analyse.js';

test('bilan : mois en clair, écarts du portefeuille démo aux références', () => {
  assert.equal(moisLong('2026-11'), 'novembre 2026');
  const b = { performances: [{ nom: 'Démo', mois_pct: -5.68, depuis_debut_pct: -5.68 }, { nom: 'MSCI World', mois_pct: -5.1, depuis_debut_pct: -5.1 },
    { nom: 'Momentum seul', mois_pct: null, depuis_debut_pct: -4.92 }] };
  assert.deepEqual(ecarts(b), [{ nom: 'MSCI World', mois: -0.58, depuis: -0.58 }, { nom: 'Momentum seul', mois: null, depuis: -0.76 }]);
  assert.equal(signeBilan(null), 'n. d.');
  assert.equal(signeBilan(-0.58, ' pt'), '−0,6 pt');
});

const ligne = (ticker, valeur, profil) => ({ ligne: { ticker, nom: ticker }, valeur, poids: valeur, profil });

test('face à la liste : dans la liste (y compris par l’ETF du portefeuille démo), absentes, hors liste, concentration', () => {
  const chef = { liste: { lignes: [
    { id: 'selection-PTON', categorie: 'entreprises', nom: 'Peloton', symbole: 'PTON', ticker: 'PTON', conviction: 'forte' },
    { id: 'matiere-palladium', categorie: 'matieres', nom: 'Palladium', symbole: 'PA=F', conviction: 'faible' },
    { id: 'pays-PL', categorie: 'pays', nom: 'Pologne', symbole: 'EPOL', conviction: 'faible' }] } };
  const demo = { positions: [
    { symbole: 'PALL', ligne_id: 'matiere-palladium', poids: 8, classe: 'matieres' },
    { symbole: 'PTON', ligne_id: 'selection-PTON', poids: 7, pays: 'US', secteur: 'Consommation discrétionnaire' },
    { symbole: 'MSFT', ligne_id: 'x', poids: 5, pays: 'US', secteur: 'Technologies de l’information' }] };
  const enrichi = { lignes: [
    ligne('PALL', 20, { classe: 'matieres', pays: {}, devises: {}, themes: [] }),
    ligne('AAPL', 50, { classe: 'actions', pays: { US: 100 }, secteur: 'Information Technology', devises: {}, themes: [], opportunite: { verdict: 'Neutre', score: 52, nom: 'Apple' } }),
    ligne('XYZ', 30, { classe: 'actions', pays: { FR: 100 }, secteur: 'Industrials', devises: {}, themes: [] })], total: 100 };
  const r = faceALaListe(enrichi, chef, demo, { US: 'États-Unis', FR: 'France' });
  assert.deepEqual(r.dans.map((x) => x.id), ['matiere-palladium']);
  assert.deepEqual(r.absentes.map((x) => x.id), ['selection-PTON', 'pays-PL']);
  assert.deepEqual(r.hors.map((x) => [x.nom, x.verdict_contexte]), [['AAPL', 'Neutre'], ['XYZ', null]]);
  assert.deepEqual(r.concentration.tech_us, { moi: 50, demo: 5 });
  const us = r.concentration.pays.find((x) => x.libelle === 'États-Unis');
  assert.deepEqual([us.moi, us.demo], [50, 12]);
  const tech = r.concentration.secteurs.find((x) => /information/i.test(x.libelle));
  assert.deepEqual([tech.moi, tech.demo], [50, 5]);
  // Sans liste : rien n'est rapproché
  assert.equal(faceALaListe(enrichi, {}, demo).liste_disponible, false);
});
