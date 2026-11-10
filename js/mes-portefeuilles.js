/* ==========================================================================
   Écran « Mes portefeuilles » (Menu › Suivi) : portefeuilles RÉELS de l'utilisateur.

   Confidentialité : les positions restent sur l'appareil (IndexedDB) ; elles ne
   sont jamais envoyées ni écrites dans le dépôt. Voir js/portefeuilles-donnees.js.

   - vue globale et vue par portefeuille (PEA, compte-titres, assurance vie…) ;
   - saisie manuelle, import CSV / Excel avec écran de correspondance des colonnes ;
   - résolution ISIN → ticker ; fonds non reconnus classés « fonds », catégorie à saisir ;
   - analyses : expositions, corrélations, crible des agents, cohérence avec le chef
     d'orchestre, pistes de décorrélation, performance vs MSCI World en euros ;
   - sauvegarde chiffrée par mot de passe, synchronisation chiffrée facultative.
   ========================================================================== */

import { el, svg, nombre, variation } from './outils.js';
import { titreSection } from './panneau-pays.js';
import {
  lireEtat, enregistrerEtat, toutEffacer, etatVide, nouvelId, noterValeur, contenuSauvegarde, TYPES_PORTEFEUILLE,
  chargerSeriesPubliques, chargerFichePublique, resoudreISIN, adresseSynchro, memoriserMotDePasse, telechargerSynchro, integrerSynchro,
} from './portefeuilles-donnees.js';
import { chiffrer, dechiffrer, estEnveloppe } from './portefeuilles-chiffrement.js';
import { lireFichier, detecterColonnes, construireLignes, correspondanceSuffisante, CHAMPS, isinValide } from './portefeuilles-import.js';
import {
  MENTION_ANALYSE, CLASSES, TYPES_LIGNE, ZONES, SECTEURS, THEMES, construireReferences, enrichir, expositions, correlations,
  crible, coherence, decorrelation, performance, symboleLigne,
} from './portefeuilles-analyse.js';
import { portefeuillesExemple } from './portefeuilles-exemple.js';

const MENTION_CONFIDENTIALITE = 'Vos positions restent sur cet appareil : stockage local (IndexedDB), jamais envoyées sur Internet ni enregistrées dans le dépôt.';
const DETAIL_CONFIDENTIALITE = 'Les tickers sont d’abord retrouvés sur l’appareil. Seuls les identifiants publics des titres (ISIN, ticker) peuvent être demandés à Yahoo Finance et aux fiches publiques de l’appli, jamais les quantités ni les montants. Ces requêtes se désactivent dans « Sauvegarde, synchronisation et réglages ».';

const ONGLETS = {
  positions: 'Positions',
  expositions: 'Expositions',
  correlation: 'Corrélation',
  crible: 'Crible des agents',
  chef: 'Chef d’orchestre',
  performance: 'Performance',
};

let etat = null;
let erreurChargement = null;
let seriesPubliques = {};
const fiches = {};
let seriesOpp = null;
let conteneur = null;
let ctx = null;
let vue = 'global';
let onglet = 'positions';
let action = null; // panneau d'action ouvert : { type: 'import' | 'ligne' | 'nouveau' | 'renommer', … }
let message = null; // { texte, type: 'ok' | 'erreur' }
let resolutionEnCours = 0;
let synchroEnCours = false;
let fichesPretes = false; // fiches publiques des sociétés détenues chargées : valeurs stables, historique enregistrable
let ouvrirReglages = false; // section « Sauvegarde, synchronisation et réglages » dépliée

/* ============================== Point d'entrée ============================== */

export function ecranMesPortefeuilles(d, nav) {
  conteneur ??= el('div', { class: 'mpf' });
  ctx = { d, nav };
  if (!etat && !erreurChargement) {
    conteneur.replaceChildren(el('p', { class: 'chef-petit' }, 'Ouverture du stockage local…'));
    demarrer();
  } else dessiner();
  return [conteneur];
}

async function demarrer() {
  try {
    [etat, seriesPubliques] = await Promise.all([lireEtat(), chargerSeriesPubliques()]);
  } catch (e) {
    erreurChargement = e.message;
    etat = null;
  }
  dessiner();
  if (!etat) return;
  chargerFichesDetenues();
  const s = etat.reglages.synchro;
  if (s.active && etat.cle_synchro && (!etat.synchro.derniere || Date.now() - Date.parse(etat.synchro.derniere) > 12 * 3600e3)) synchroniser(true);
}

async function sauver() {
  try { await enregistrerEtat(etat); } catch (e) { afficherMessage(`Enregistrement impossible : ${e.message}`, 'erreur'); }
}

function afficherMessage(texte, type = 'ok') {
  message = { texte, type };
  dessiner();
}

/* ============================== Données de référence ============================== */

function seriesConnues() {
  const s = { ...seriesPubliques };
  for (const [t, f] of Object.entries(fiches)) if (f?.cours_hebdo?.length) s[t] = f.cours_hebdo;
  return { ...s, ...(etat?.series_synchro ?? {}) };
}

function references() {
  const series = seriesConnues();
  const fx = series['EURUSD=X'];
  return construireReferences({
    entreprises: ctx.d.entreprises, pays: ctx.d.pays, chef: ctx.d.chef, series, fiches,
    eurusd: fx?.length ? fx[fx.length - 1][1] : null,
  });
}

/** Fiches publiques des sociétés détenues (note, alertes, recommandation, cours sur 1 an). */
async function chargerFichesDetenues() {
  const tickers = new Set();
  if (etat?.reglages.requetes_par_titre) {
    for (const pf of etat.portefeuilles) for (const l of pf.lignes) {
      const e = ctx.d.entrepriseParTicker.get(symboleLigne(l) ?? '');
      if (e && !(e.ticker in fiches)) tickers.add(e.ticker);
    }
  }
  if (!tickers.size) {
    if (!fichesPretes) { fichesPretes = true; dessiner(); }
    return;
  }
  // Tant que les cours des sociétés ne sont pas chargés, la valeur n'est pas enregistrée dans l'historique
  fichesPretes = false;
  await Promise.all([...tickers].slice(0, 80).map(async (t) => { fiches[t] = await chargerFichePublique(t); }));
  fichesPretes = true;
  dessiner();
}

/** Séries des opportunités bien notées du chef d'orchestre (pistes de décorrélation). */
async function chargerSeriesOpportunites() {
  if (seriesOpp) return;
  seriesOpp = {};
  const chef = ctx.d.chef;
  if (!chef) return;
  const positives = (o) => ['Renforcer', 'Renforcer fortement'].includes(o.verdict);
  const series = seriesConnues();
  const autres = [...(chef.pays ?? []), ...(chef.secteurs ?? []), ...(chef.matieres ?? []), ...(chef.obligations ?? []), ...(chef.or ? [chef.or] : [])].filter(positives);
  for (const o of autres) if (o.symbole && series[o.symbole]) seriesOpp[o.id] = series[o.symbole];
  // Sociétés : fiches publiques (liste du chef d'orchestre, identique pour tous : ne révèle rien du portefeuille)
  const societes = (chef.entreprises ?? []).filter(positives).sort((a, b) => b.score - a.score).slice(0, 30);
  await Promise.all(societes.map(async (o) => {
    const f = fiches[o.cle] ?? await chargerFichePublique(o.cle);
    if (f?.cours_hebdo?.length) seriesOpp[o.id] = f.cours_hebdo;
  }));
  if (onglet === 'correlation') dessiner();
}

/* ============================== Rendu principal ============================== */

function dessiner() {
  if (!conteneur) return;
  if (erreurChargement) {
    conteneur.replaceChildren(entete(), el('p', { class: 'chef-avertissement' }, `Stockage local indisponible : ${erreurChargement}. Les portefeuilles ne peuvent pas être enregistrés sur ce navigateur (navigation privée ?).`), mention());
    return;
  }
  if (!etat) return;
  if (vue !== 'global' && !etat.portefeuilles.some((p) => p.id === vue)) vue = 'global';
  const pf = vue === 'global' ? null : etat.portefeuilles.find((p) => p.id === vue);
  const refs = references();
  const enrichi = enrichir(lignesDeLaVue(pf), refs);
  majHistoriques(refs);

  conteneur.replaceChildren(...[
    entete(),
    bandeauConfidentialite(),
    message ? el('p', { class: `mpf-message mpf-message--${message.type}`, role: 'status' }, message.texte, el('button', { class: 'bouton bouton--petit', type: 'button', onclick: () => { message = null; dessiner(); } }, 'OK')) : null,
    selecteurVues(),
    action ? panneauAction() : null,
    etat.portefeuilles.length ? null : accueil(),
    etat.portefeuilles.length ? resume(enrichi, refs, pf) : null,
    etat.portefeuilles.length ? barreOnglets() : null,
    etat.portefeuilles.length ? contenuOnglet(enrichi, refs, pf) : null,
    pf ? actionsPortefeuille(pf) : null,
    reglages(),
    mention(),
  ].filter(Boolean));
}

function lignesDeLaVue(pf) {
  if (pf) return pf.lignes.map((l) => ({ ...l, _pf: pf.id }));
  return etat.portefeuilles.flatMap((p) => p.lignes.map((l) => ({ ...l, _pf: p.id })));
}

/** Point du jour de chaque portefeuille (valeur en euros), et valeur de référence au premier passage. */
function majHistoriques(refs) {
  if (!fichesPretes || resolutionEnCours) return;
  let change = false;
  const jour = new Date().toISOString().slice(0, 10);
  for (const p of etat.portefeuilles) {
    const total = enrichir(p.lignes, refs).total;
    if (!(total > 0)) continue;
    if (!p.reference) { p.reference = { date: jour, valeur: total }; change = true; }
    if (noterValeur(p, total, jour)) change = true;
  }
  if (change) sauver();
}

function entete() {
  return el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Portefeuilles réels · sur cet appareil uniquement'),
    el('h2', { class: 'fiche-titre' }, 'Mes portefeuilles'),
  );
}

function bandeauConfidentialite() {
  return el('div', { class: 'mpf-confidentialite' },
    el('p', {}, el('span', { 'aria-hidden': 'true' }, '🔒 '), el('strong', {}, MENTION_CONFIDENTIALITE)),
    el('p', { class: 'chef-petit' }, DETAIL_CONFIDENTIALITE),
  );
}

function mention() {
  return el('p', { class: 'chef-mention' }, `${MENTION_ANALYSE} Ne constitue pas un conseil en investissement.`);
}

function selecteurVues() {
  if (!etat.portefeuilles.length) return null;
  const onglets = [{ id: 'global', libelle: 'Vue globale' }, ...etat.portefeuilles.map((p) => ({ id: p.id, libelle: p.nom }))];
  return el('div', { class: 'onglets mpf-vues', role: 'tablist', 'aria-label': 'Portefeuilles' },
    onglets.map((o) => el('button', {
      class: 'onglet', type: 'button', role: 'tab', 'aria-selected': String(vue === o.id),
      onclick: () => { vue = o.id; action = null; dessiner(); },
    }, o.libelle)),
    el('button', { class: 'onglet mpf-nouveau', type: 'button', onclick: () => { action = { type: 'nouveau' }; dessiner(); } }, '+ Nouveau'),
  );
}

function barreOnglets() {
  return el('div', { class: 'onglets mpf-onglets', role: 'tablist', 'aria-label': 'Analyses' },
    Object.entries(ONGLETS).map(([cle, libelle]) => el('button', {
      class: 'onglet', type: 'button', role: 'tab', 'aria-selected': String(onglet === cle),
      onclick: () => { onglet = cle; if (cle === 'correlation') chargerSeriesOpportunites(); dessiner(); },
    }, libelle)));
}

function contenuOnglet(enrichi, refs, pf) {
  if (!enrichi.lignes.length) {
    return el('section', { class: 'carte' }, el('p', { class: 'chef-petit' }, pf ? 'Ce portefeuille est vide : ajoutez une ligne ou importez un fichier.' : 'Aucune ligne pour le moment.'));
  }
  switch (onglet) {
    case 'expositions': return ongletExpositions(enrichi);
    case 'correlation': return ongletCorrelation(enrichi, refs);
    case 'crible': return ongletCrible(enrichi, refs);
    case 'chef': return ongletChef(enrichi, refs);
    case 'performance': return ongletPerformance(enrichi, refs, pf);
    default: return ongletPositions(enrichi, pf);
  }
}

/* ============================== Accueil (aucun portefeuille) ============================== */

function accueil() {
  return el('section', { class: 'carte mpf-accueil' },
    titreSection('Commencer'),
    el('p', { class: 'chef-texte' }, 'Créez vos portefeuilles (PEA, compte-titres, assurance vie…), puis saisissez vos lignes ou importez le fichier exporté de votre courtier (CSV ou Excel).'),
    el('div', { class: 'mpf-boutons' },
      el('button', { class: 'bouton bouton--accent', type: 'button', onclick: () => { action = { type: 'nouveau' }; dessiner(); } }, 'Créer un portefeuille'),
      el('button', { class: 'bouton', type: 'button', onclick: () => { action = { type: 'import', etape: 'fichier' }; dessiner(); } }, 'Importer un fichier'),
      el('button', { class: 'bouton', type: 'button', onclick: () => { ouvrirReglages = true; dessiner(); } }, 'Restaurer une sauvegarde'),
      el('button', { class: 'bouton', type: 'button', onclick: chargerExemple }, 'Charger l’exemple fictif'),
    ),
  );
}

async function chargerExemple() {
  const jour = new Date().toISOString().slice(0, 10);
  for (const p of portefeuillesExemple(jour)) {
    etat.portefeuilles.push({
      id: nouvelId('p'), nom: p.nom, type: p.type, source: 'exemple', cree_le: new Date().toISOString(), historique: [], reference: null,
      lignes: p.lignes.map((l) => ({ ...l, id: nouvelId(), date_valeur: l.valeur != null ? jour : null })),
    });
  }
  await sauver();
  chargerFichesDetenues();
  afficherMessage('Portefeuilles d’exemple fictifs ajoutés (vous pouvez les supprimer à tout moment).');
}

/* ============================== Résumé ============================== */

function eur(v, dec = 0) {
  if (v == null || !Number.isFinite(v)) return 'n. d.';
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v);
}
const classeSigne = (v) => (v > 0 ? 'hausse' : v < 0 ? 'baisse' : '');
const pct = (v, d = 1) => (v == null ? 'n. d.' : variation(v, d));

function stat(libelle, valeur, detail, signe) {
  return el('div', { class: 'stat' },
    el('div', { class: 'stat-libelle' }, libelle),
    el('div', { class: `stat-valeur ${signe == null ? '' : classeSigne(signe)}` }, valeur),
    detail ? el('div', { class: 'kpi-comparaison' }, detail) : null);
}

function referenceVue(pf, enrichi) {
  if (pf) return { reference: pf.reference, historique: pf.historique ?? [] };
  // Vue globale : somme des historiques, à partir de la date d'import la plus récente
  const refs = etat.portefeuilles.map((p) => p.reference).filter(Boolean);
  if (!refs.length) return { reference: null, historique: [] };
  const depart = refs.map((r) => r.date).sort().pop();
  const valeurA = (p, date) => {
    let v = null;
    for (const h of p.historique ?? []) { if (h.date <= date) v = h.valeur; else break; }
    return v ?? (p.reference && p.reference.date <= date ? p.reference.valeur : null);
  };
  const dates = [...new Set(etat.portefeuilles.flatMap((p) => (p.historique ?? []).map((h) => h.date)))].filter((x) => x > depart).sort();
  const total = (date) => etat.portefeuilles.reduce((s, p) => s + (valeurA(p, date) ?? 0), 0);
  return { reference: { date: depart, valeur: total(depart) || enrichi.total }, historique: dates.map((date) => ({ date, valeur: total(date) })) };
}

function resume(enrichi, refs, pf) {
  const { reference, historique } = referenceVue(pf, enrichi);
  const perf = performance(enrichi, refs, reference, historique);
  const ecart = perf.depuis_import != null && perf.msci_depuis_import != null ? perf.depuis_import - perf.msci_depuis_import : null;
  const n = enrichi.lignes.length;
  return el('section', { class: 'carte' },
    el('div', { class: 'fiche-surtitre' }, pf ? `${TYPES_PORTEFEUILLE[pf.type] ?? 'Portefeuille'} · ${n} ligne${n > 1 ? 's' : ''}${pf.source === 'synchro' ? ` · synchronisé le ${dateHeure(pf.maj_le)}` : ''}` : `${etat.portefeuilles.length} portefeuille${etat.portefeuilles.length > 1 ? 's' : ''} · ${n} ligne${n > 1 ? 's' : ''}`),
    el('div', { class: 'valeur-heros' }, eur(perf.valeur)),
    el('div', { class: 'kpis' },
      stat('Plus-values latentes', perf.plus_value == null ? 'n. d.' : `${perf.plus_value >= 0 ? '+' : '−'}${eur(Math.abs(perf.plus_value))}`,
        perf.plus_value_pct == null ? 'prix de revient manquants' : `${pct(perf.plus_value_pct)} sur le prix de revient${perf.couverture_cout < 99 ? ` (${nombre(perf.couverture_cout, 0)} % de la valeur)` : ''}`, perf.plus_value),
      stat('Depuis l’import', pct(perf.depuis_import, 2),
        perf.date_import ? `le ${dateFr(perf.date_import)} · MSCI World en € : ${pct(perf.msci_depuis_import, 2)}${ecart == null ? '' : ` (${ecart >= 0 ? '+' : '−'}${nombre(Math.abs(ecart), 2)} pt)`}` : 'en attente d’une première valeur', perf.depuis_import),
    ),
  );
}

const dateFr = (iso) => (iso ? new Date(`${String(iso).slice(0, 10)}T12:00:00`).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }) : '');
const dateHeure = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'n. d.');

/* ============================== Onglet Positions ============================== */

function ongletPositions(enrichi, pf) {
  const nomPf = (id) => etat.portefeuilles.find((p) => p.id === id)?.nom ?? '';
  const lignes = [...enrichi.lignes].sort((a, b) => (b.valeur ?? 0) - (a.valeur ?? 0));
  return el('section', { class: 'carte' },
    titreSection('Positions', 'valeur en euros, poids dans la vue'),
    resolutionEnCours ? el('p', { class: 'chef-petit' }, `Recherche des tickers en cours (${resolutionEnCours} ISIN)…`) : null,
    el('div', { class: 'tableau-defilant' }, el('table', { class: 'chef-table mpf-positions' },
      el('thead', {}, el('tr', {}, el('th', {}, 'Ligne'), el('th', { class: 'nombre' }, 'Valeur'), el('th', { class: 'nombre' }, '+/− latente'), pf ? el('th', {}, '') : null)),
      el('tbody', {}, lignes.map((x) => {
        const l = x.ligne;
        const pv = x.cout != null && x.valeur != null ? x.valeur - x.cout : null;
        const e = ctx.d.entrepriseParTicker.get(symboleLigne(l) ?? '');
        return el('tr', {},
          el('td', {},
            e ? el('button', { class: 'lien', type: 'button', onclick: () => ctx.nav.ouvrirEntreprise(e.ticker) }, l.nom) : el('strong', {}, l.nom),
            el('div', { class: 'mpf-sous' },
              [l.ticker, l.isin, TYPES_LIGNE[l.type] ?? l.type, l.quantite != null ? `${nombre(l.quantite, l.quantite % 1 ? 4 : 0)} part(s)` : null, pf ? null : nomPf(l._pf)].filter(Boolean).join(' · ')),
            x.profil.nonClasse ? el('span', { class: 'mpf-pastille mpf-pastille--ambre' }, 'catégorie à saisir') : null,
            el('div', { class: 'mpf-sous mpf-source' }, x.sourceValeur)),
          el('td', { class: 'nombre' }, eur(x.valeur), el('div', { class: 'mpf-sous' }, `${nombre(x.poids, 1)} %`)),
          el('td', { class: `nombre ${classeSigne(pv)}` }, pv == null ? '—' : `${pv >= 0 ? '+' : '−'}${eur(Math.abs(pv))}`,
            pv == null || !x.cout ? null : el('div', { class: 'mpf-sous' }, pct((pv / x.cout) * 100))),
          pf ? el('td', { class: 'mpf-actions-ligne' },
            el('button', { class: 'bouton bouton--icone bouton--petit', type: 'button', title: 'Modifier', 'aria-label': `Modifier ${l.nom}`, onclick: () => { action = { type: 'ligne', ligne: pf.lignes.find((y) => y.id === l.id) }; dessiner(); conteneur.scrollIntoView?.({ block: 'start' }); } }, '✎'),
            el('button', { class: 'bouton bouton--icone bouton--petit bouton--danger', type: 'button', title: 'Supprimer', 'aria-label': `Supprimer ${l.nom}`, onclick: () => supprimerLigne(pf, l.id) }, '🗑')) : null,
        );
      })),
    )),
  );
}

async function supprimerLigne(pf, id) {
  const l = pf.lignes.find((x) => x.id === id);
  if (!l || !confirm(`Supprimer la ligne « ${l.nom} » ?`)) return;
  pf.lignes = pf.lignes.filter((x) => x.id !== id);
  await sauver();
  dessiner();
}

/* ============================== Onglet Expositions ============================== */

function barres(liste, max = 10) {
  if (!liste.length) return el('p', { class: 'chef-petit' }, 'Rien à afficher.');
  const haut = Math.max(...liste.map((x) => x.pct), 1);
  return el('ul', { class: 'pf-barres' }, liste.slice(0, max).map((x) => el('li', {},
    el('span', { class: 'pf-barres-nom' }, x.libelle),
    el('span', { class: 'pf-barres-jauge' }, el('span', { style: { width: `${(x.pct / haut) * 100}%` } })),
    el('span', { class: 'mono' }, `${nombre(x.pct, 1)} %`))));
}

function ongletExpositions(enrichi) {
  const noms = Object.fromEntries(ctx.d.pays.map((p) => [p.code, p.nom]));
  const exp = expositions(enrichi, noms);
  const nonClasses = enrichi.lignes.filter((x) => x.profil.nonClasse).length;
  return el('div', { class: 'mpf-pile' },
    el('section', { class: 'carte' },
      titreSection('Alertes de concentration', `seuils : ${nombre(10)} % par titre, 50 % par pays, 30 % par secteur, 20 % par thème`),
      exp.alertes.length
        ? el('ul', { class: 'mpf-alertes' }, exp.alertes.map((a) => el('li', { class: `mpf-alerte mpf-alerte--${a.niveau}` }, a.texte)))
        : el('p', { class: 'chef-petit' }, 'Aucune concentration au-delà des seuils.'),
      nonClasses ? el('p', { class: 'chef-avertissement' }, `${nonClasses} ligne(s) sans catégorie : elles comptent dans « Non classé ». Modifiez-les pour préciser zone, classe et secteur.`) : null,
    ),
    el('section', { class: 'carte' }, titreSection('Classes d’actifs'), barres(exp.classes)),
    el('section', { class: 'carte' }, titreSection('Pays', 'actions ; fonds répartis selon leur zone (approximation)'), barres(exp.pays, 12)),
    el('section', { class: 'carte' }, titreSection('Secteurs', 'actions'), barres(exp.secteurs, 12)),
    el('section', { class: 'carte' }, titreSection('Devises', 'devise de cotation ; fonds selon leurs pays'), barres(exp.devises)),
    el('section', { class: 'carte' }, titreSection('Thèmes', 'une ligne peut relever de plusieurs thèmes'), barres(exp.themes)),
  );
}

/* ============================== Onglet Corrélation ============================== */

const corrTexte = (c) => (c == null ? '—' : nombre(c, 2));
const classeCorr = (c) => (c == null ? '' : c >= 0.7 ? 'mpf-corr--forte' : c <= 0.3 ? 'mpf-corr--faible' : '');

function ongletCorrelation(enrichi, refs) {
  const c = correlations(enrichi, refs);
  if (!c.portefeuille) {
    return el('section', { class: 'carte' }, titreSection('Corrélation'),
      el('p', { class: 'chef-petit' }, 'Pas assez d’historique de cours pour calculer les corrélations. Les cours sur 1 an viennent des fiches publiques des sociétés suivies, des séries des agents (indices, ETF pays) ou de la synchronisation.'));
  }
  const p = c.portefeuille;
  const pistes = seriesOpp ? decorrelation(c.rendements, refs, seriesOpp) : null;
  return el('div', { class: 'mpf-pile' },
    el('section', { class: 'carte' },
      titreSection('Diversification effective', `rendements hebdomadaires sur 1 an · ${nombre(c.couverture, 0)} % de la valeur couverte`),
      el('div', { class: 'kpis' },
        stat('Volatilité annualisée', `${nombre(p.vol, 1)} %`, 'du portefeuille'),
        stat('Corrélation au Nasdaq 100', corrTexte(p.corr_nasdaq), p.corr_nasdaq >= 0.8 ? 'le portefeuille suit de près le Nasdaq' : 'sur 1 an'),
        stat('Paris de risque effectifs', p.n_effectif_risque == null ? 'n. d.' : nombre(p.n_effectif_risque, 1), `pour ${p.n_lignes} lignes (${nombre(p.n_effectif_lignes, 1)} en poids)`),
        stat('Ratio de diversification', p.ratio_diversification == null ? 'n. d.' : nombre(p.ratio_diversification, 2), '1 = aucune diversification ; plus c’est haut, mieux c’est'),
      ),
      c.non_couvertes.length ? el('p', { class: 'chef-petit' }, `Sans historique de cours (exclues) : ${c.non_couvertes.join(', ')}.`) : null,
    ),
    el('section', { class: 'carte' },
      titreSection('Par ligne', 'part du risque : contribution à la variance du portefeuille'),
      el('div', { class: 'tableau-defilant' }, el('table', { class: 'chef-table mpf-corr' },
        el('thead', {}, el('tr', {}, ['Ligne', 'Poids', 'Part du risque', 'Corr. reste', 'Corr. Nasdaq', 'Volatilité'].map((t, i) => el('th', { class: i ? 'nombre' : null }, t)))),
        el('tbody', {}, c.lignes.map((l) => el('tr', {},
          el('td', {}, l.nom, l.approximation ? el('div', { class: 'mpf-sous' }, `approximation : indice ${l.approximation}`) : null),
          el('td', { class: 'nombre' }, `${nombre(l.poids, 1)} %`),
          el('td', { class: `nombre ${l.part_risque > l.poids * 1.3 ? 'baisse' : ''}` }, l.part_risque == null ? '—' : `${nombre(l.part_risque, 1)} %`),
          el('td', { class: `nombre ${classeCorr(l.corr_reste)}` }, corrTexte(l.corr_reste)),
          el('td', { class: `nombre ${classeCorr(l.corr_nasdaq)}` }, corrTexte(l.corr_nasdaq)),
          el('td', { class: 'nombre' }, l.vol == null ? '—' : `${nombre(l.vol, 0)} %`)))),
      )),
      el('p', { class: 'chef-petit' }, 'Corrélations en devise de cotation, sur les semaines communes (20 au minimum). Une ligne dont la part du risque dépasse nettement son poids (en rouge) pèse plus qu’il n’y paraît. Pour un fonds sans historique, l’indice de sa zone sert d’approximation.'),
    ),
    el('section', { class: 'carte' },
      titreSection('Pistes de décorrélation', 'opportunités « Renforcer » du chef d’orchestre peu corrélées au portefeuille'),
      pistes == null ? el('p', { class: 'chef-petit' }, 'Chargement des cours des opportunités…')
        : pistes.length ? el('ul', { class: 'mpf-liste' }, pistes.map((o) => el('li', {},
          el('button', { class: 'lien', type: 'button', onclick: () => ctx.nav.ouvrir({ type: 'investir', id: `o-${o.id}` }) }, o.nom),
          el('span', { class: 'mpf-sous' }, ` ${o.verdict} (conviction ${o.conviction}, ${nombre(o.score, 0)}/100) · corrélation ${corrTexte(o.corr)}`))))
          : el('p', { class: 'chef-petit' }, 'Aucune opportunité bien notée nettement décorrélée du portefeuille actuel.'),
    ),
  );
}

/* ============================== Onglet Crible ============================== */

function ongletCrible(enrichi, refs) {
  const res = crible(enrichi, refs).sort((a, b) => b.alertes.length - a.alertes.length || b.poids - a.poids);
  return el('section', { class: 'carte' },
    titreSection('Chaque ligne passée au crible', 'agent entreprises ou agent pays, contradicteur, chef d’orchestre'),
    el('ul', { class: 'mpf-crible' }, res.map((r) => el('li', { class: r.alertes.length ? 'a-alerte' : '' },
      el('div', { class: 'mpf-crible-tete' },
        r.lien ? el('button', { class: 'lien', type: 'button', onclick: () => (r.lien.type === 'entreprise' ? ctx.nav.ouvrirEntreprise(r.lien.id) : ctx.nav.ouvrirPays(r.lien.id)) }, r.nom) : el('strong', {}, r.nom),
        r.note != null ? el('span', { class: 'mpf-note', title: `Note de l’${r.source_note}` }, `${nombre(r.note, 0)}/100`) : el('span', { class: 'mpf-sous' }, 'non suivi par les agents'),
      ),
      el('div', { class: 'mpf-sous' }, [
        r.source_note ? `note : ${r.source_note}` : null,
        r.si_detenu ? `si détenu : ${r.si_detenu}` : null,
        r.verdict_chef ? `chef d’orchestre : ${r.verdict_chef.verdict} (${r.verdict_chef.conviction})` : null,
        `${nombre(r.poids, 1)} % de la vue`,
      ].filter(Boolean).join(' · ')),
      r.alertes.length ? el('ul', { class: 'mpf-signaux' }, r.alertes.map((t) => el('li', {}, `⚠ ${t}`))) : null,
      r.objections.length ? el('p', { class: 'chef-petit' }, el('strong', {}, 'Contradicteur : '), r.objections.join(' ')) : null,
      r.donner_tort.length ? el('details', {}, el('summary', {}, 'Ce qui pourrait donner tort'), el('ul', { class: 'chef-texte' }, r.donner_tort.map((t) => el('li', {}, t)))) : null,
    ))),
  );
}

/* ============================== Onglet Chef d'orchestre ============================== */

function ongletChef(enrichi, refs) {
  if (!ctx.d.chef) return el('section', { class: 'carte' }, el('p', { class: 'chef-petit' }, 'Chef d’orchestre indisponible pour le moment.'));
  const exp = expositions(enrichi, {});
  const co = coherence(enrichi, refs, exp);
  const ouvrir = (id) => ctx.nav.ouvrir({ type: 'investir', id: `o-${id}` });
  return el('div', { class: 'mpf-pile' },
    el('section', { class: 'carte' },
      titreSection('Positions sur des opportunités « Alléger » ou « Éviter »'),
      co.a_alleger.length ? el('ul', { class: 'mpf-liste' }, co.a_alleger.map((x) => el('li', { class: 'mpf-alerte mpf-alerte--forte' },
        `${x.nom} (${nombre(x.poids, 1)} % de la vue) : « ${x.verdict} », conviction ${x.conviction}, score ${nombre(x.score, 0)}/100${x.raison ? ` ; point faible : ${x.raison}` : ''}.`)))
        : el('p', { class: 'chef-petit' }, 'Aucune ligne reconnue sur une opportunité « Alléger » ou « Éviter ».'),
    ),
    el('section', { class: 'carte' },
      titreSection('Opportunités « Renforcer » absentes du portefeuille', 'pays déjà représentés à plus de 3 % exclus'),
      co.absentes.length ? el('ul', { class: 'mpf-liste' }, co.absentes.map((o) => el('li', {},
        el('button', { class: 'lien', type: 'button', onclick: () => ouvrir(o.id) }, o.nom),
        el('span', { class: 'mpf-sous' }, ` ${o.verdict} (conviction ${o.conviction}, ${nombre(o.score, 0)}/100)${o.symbole ? ` · ${o.symbole}` : ''}${o.exposition_actuelle ? ` · exposition actuelle ${nombre(o.exposition_actuelle, 1)} %` : ''}`))))
        : el('p', { class: 'chef-petit' }, 'Toutes les opportunités « Renforcer » sont déjà représentées.'),
      el('p', { class: 'chef-petit' }, 'Rapprochement par ticker (sociétés, ETF pays et sectoriels, or, matières) : un fonds sans ticker n’est pas rapproché.'),
    ),
  );
}

/* ============================== Onglet Performance ============================== */

function ongletPerformance(enrichi, refs, pf) {
  const { reference, historique } = referenceVue(pf, enrichi);
  const perf = performance(enrichi, refs, reference, historique);
  const parPf = pf ? null : etat.portefeuilles.map((p) => {
    const e = enrichir(p.lignes, refs);
    return { p, perf: performance(e, refs, p.reference, p.historique ?? []) };
  });
  return el('div', { class: 'mpf-pile' },
    el('section', { class: 'carte' },
      titreSection('Performance depuis l’import', 'base 100, comparée au MSCI World en euros (ETF URTH ÷ EUR/USD)'),
      perf.historique.length >= 2 ? courbe(perf.historique)
        : el('p', { class: 'chef-petit' }, 'Un point par jour d’ouverture de l’écran (ou de synchronisation) : la courbe apparaît dès le deuxième jour.'),
      el('p', { class: 'chef-petit' }, 'Apports et retraits ne sont pas distingués : un ajout de ligne ou un nouvel import fait varier la valeur. Réimporter un portefeuille ne remet pas la référence à zéro.'),
    ),
    parPf ? el('section', { class: 'carte' },
      titreSection('Par portefeuille'),
      el('table', { class: 'tableau' },
        el('thead', {}, el('tr', {}, el('th', {}, 'Portefeuille'), el('th', { class: 'nombre' }, 'Valeur'), el('th', { class: 'nombre' }, '+/− latente'), el('th', { class: 'nombre' }, 'Depuis import'))),
        el('tbody', {}, parPf.map(({ p, perf: x }) => el('tr', { class: 'cliquable', onclick: () => { vue = p.id; dessiner(); } },
          el('td', {}, p.nom),
          el('td', { class: 'nombre' }, eur(x.valeur)),
          el('td', { class: `nombre ${classeSigne(x.plus_value)}` }, x.plus_value == null ? '—' : `${x.plus_value >= 0 ? '+' : '−'}${eur(Math.abs(x.plus_value))}`),
          el('td', { class: `nombre ${classeSigne(x.depuis_import)}` }, pct(x.depuis_import, 2)))))),
    ) : null,
  );
}

function courbe(points) {
  const L = 320; const H = 140; const m = { g: 34, d: 8, h: 8, b: 20 };
  const valeurs = points.flatMap((p) => [p.portefeuille, p.msci]).filter((v) => v != null);
  const min = Math.min(...valeurs); const max = Math.max(...valeurs);
  const ecart = max - min || 1;
  const x = (i) => m.g + (i / (points.length - 1)) * (L - m.g - m.d);
  const y = (v) => m.h + (1 - (v - min) / ecart) * (H - m.h - m.b);
  const trace = (cle) => points.map((p, i) => (p[cle] == null ? null : `${x(i).toFixed(1)},${y(p[cle]).toFixed(1)}`)).filter(Boolean).join(' ');
  return el('figure', { class: 'mpf-courbe' },
    svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img', 'aria-label': 'Performance base 100 du portefeuille et du MSCI World en euros' },
      svg('line', { x1: m.g, x2: L - m.d, y1: y(100), y2: y(100), class: 'mpf-courbe-ref' }),
      svg('text', { x: 2, y: y(max) + 4, class: 'mpf-courbe-axe' }, nombre(max, 0)),
      svg('text', { x: 2, y: y(min) + 4, class: 'mpf-courbe-axe' }, nombre(min, 0)),
      svg('polyline', { points: trace('msci'), class: 'mpf-courbe-msci' }),
      svg('polyline', { points: trace('portefeuille'), class: 'mpf-courbe-pf' }),
      svg('text', { x: m.g, y: H - 4, class: 'mpf-courbe-axe' }, dateFr(points[0].date)),
      svg('text', { x: L - m.d, y: H - 4, class: 'mpf-courbe-axe', 'text-anchor': 'end' }, dateFr(points[points.length - 1].date)),
    ),
    el('figcaption', { class: 'chef-repartition' },
      el('span', {}, el('span', { class: 'chef-pastille mpf-pastille-pf' }), `Portefeuille ${nombre(points[points.length - 1].portefeuille, 1)}`),
      el('span', {}, el('span', { class: 'chef-pastille mpf-pastille-msci' }), `MSCI World (€) ${points[points.length - 1].msci == null ? 'n. d.' : nombre(points[points.length - 1].msci, 1)}`)),
  );
}

/* ============================== Actions sur un portefeuille ============================== */

function actionsPortefeuille(pf) {
  return el('section', { class: 'carte' },
    titreSection('Gérer ce portefeuille', pf.source === 'synchro' ? 'synchronisé : les lignes sont remplacées à chaque synchronisation' : null),
    el('div', { class: 'mpf-boutons' },
      el('button', { class: 'bouton bouton--accent', type: 'button', onclick: () => { action = { type: 'ligne', ligne: null }; dessiner(); conteneur.scrollIntoView?.({ block: 'start' }); } }, '+ Ajouter une ligne'),
      el('button', { class: 'bouton', type: 'button', onclick: () => { action = { type: 'import', etape: 'fichier', cible: pf.id }; dessiner(); conteneur.scrollIntoView?.({ block: 'start' }); } }, 'Importer un fichier'),
      el('button', { class: 'bouton', type: 'button', onclick: () => { action = { type: 'renommer' }; dessiner(); conteneur.scrollIntoView?.({ block: 'start' }); } }, 'Renommer'),
      el('button', { class: 'bouton bouton--danger', type: 'button', onclick: () => supprimerPortefeuille(pf) }, 'Supprimer'),
    ),
  );
}

async function supprimerPortefeuille(pf) {
  if (!confirm(`Supprimer le portefeuille « ${pf.nom} » et ses ${pf.lignes.length} ligne(s) de cet appareil ?`)) return;
  etat.portefeuilles = etat.portefeuilles.filter((p) => p.id !== pf.id);
  vue = 'global';
  await sauver();
  afficherMessage(`Portefeuille « ${pf.nom} » supprimé.`);
}

function panneauAction() {
  const fermer = () => { action = null; dessiner(); };
  const cadre = (titre, ...contenu) => el('section', { class: 'carte mpf-action' },
    el('div', { class: 'mpf-action-tete' }, el('h3', { class: 'section-titre' }, titre),
      el('button', { class: 'bouton bouton--icone bouton--petit', type: 'button', title: 'Fermer', 'aria-label': 'Fermer', onclick: fermer }, '×')),
    ...contenu);
  switch (action.type) {
    case 'nouveau': return cadre('Nouveau portefeuille', formulairePortefeuille());
    case 'renommer': return cadre('Renommer le portefeuille', formulairePortefeuille(etat.portefeuilles.find((p) => p.id === vue)));
    case 'ligne': return cadre(action.ligne ? 'Modifier la ligne' : 'Nouvelle ligne', formulaireLigne(action.ligne));
    case 'import': return cadre('Importer un fichier du courtier', ...panneauImport());
    default: return null;
  }
}

const champ = (libelle, controle, aide) => el('label', { class: 'champ' }, el('span', {}, libelle), controle, aide ? el('small', { class: 'mpf-aide' }, aide) : null);
const options = (table, choisi, vide) => [vide != null ? el('option', { value: '' }, vide) : null, ...Object.entries(table).map(([v, t]) => el('option', { value: v, selected: v === choisi }, t))];

function formulairePortefeuille(pf = null) {
  const nom = el('input', { type: 'text', required: true, maxlength: 60, value: pf?.nom ?? '', placeholder: 'ex. PEA Bourse' });
  const type = el('select', {}, options(TYPES_PORTEFEUILLE, pf?.type ?? 'pea'));
  return el('form', {
    class: 'mpf-formulaire',
    onsubmit: async (e) => {
      e.preventDefault();
      const n = nom.value.trim();
      if (!n) return;
      if (pf) { pf.nom = n; pf.type = type.value; } else {
        const nouveau = { id: nouvelId('p'), nom: n, type: type.value, source: 'manuel', cree_le: new Date().toISOString(), lignes: [], historique: [], reference: null };
        etat.portefeuilles.push(nouveau);
        vue = nouveau.id;
        onglet = 'positions';
      }
      action = null;
      await sauver();
      dessiner();
    },
  },
  el('div', { class: 'champs' }, champ('Nom', nom), champ('Type', type)),
  el('button', { class: 'bouton bouton--accent bouton--plein', type: 'submit' }, pf ? 'Enregistrer' : 'Créer'));
}

const nombreSaisi = (v) => {
  const t = String(v ?? '').replace(/\s/g, '').replace(',', '.');
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

function formulaireLigne(ligne) {
  const pf = etat.portefeuilles.find((p) => p.id === vue);
  const l = ligne ?? { type: 'action', categorie: {} };
  const cat = l.categorie ?? {};
  const nom = el('input', { type: 'text', required: true, value: l.nom ?? '' });
  const ticker = el('input', { type: 'text', value: l.ticker ?? '', placeholder: 'ex. MC.PA, AAPL', autocapitalize: 'characters' });
  const isin = el('input', { type: 'text', value: l.isin ?? '', placeholder: 'ex. FR0000121014', autocapitalize: 'characters', maxlength: 12 });
  const type = el('select', {}, options(TYPES_LIGNE, l.type ?? 'action'));
  const quantite = el('input', { type: 'text', inputmode: 'decimal', value: l.quantite ?? '' });
  const pru = el('input', { type: 'text', inputmode: 'decimal', value: l.prix_revient ?? '' });
  const devise = el('input', { type: 'text', value: l.devise ?? '', placeholder: 'EUR, USD…', maxlength: 3, autocapitalize: 'characters' });
  const valeur = el('input', { type: 'text', inputmode: 'decimal', value: l.valeur ?? '' });
  const classe = el('select', {}, options(CLASSES, cat.classe ?? '', 'automatique'));
  const zonesEtPays = { ...Object.fromEntries(Object.entries(ZONES).map(([k, z]) => [k, z.libelle])), ...Object.fromEntries([...ctx.d.pays].sort((a, b) => a.nom.localeCompare(b.nom, 'fr')).map((p) => [p.code, p.nom])) };
  const zone = el('select', {}, options(zonesEtPays, cat.zone ?? '', 'non précisée'));
  const secteur = el('select', {}, options(SECTEURS, cat.secteur ?? '', 'non précisé'));
  const indice = el('input', { type: 'text', value: cat.indice ?? '', placeholder: 'ex. URTH, ^NDX (facultatif)' });
  const themes = Object.entries(THEMES).map(([k, t]) => el('label', { class: 'mpf-case' }, el('input', { type: 'checkbox', value: k, checked: (cat.themes ?? []).includes(k) }), t.libelle));

  return el('form', {
    class: 'mpf-formulaire',
    onsubmit: async (e) => {
      e.preventDefault();
      const codeIsin = isin.value.trim().toUpperCase();
      if (codeIsin && !isinValide(codeIsin)) { isin.setCustomValidity('ISIN invalide (12 caractères, clé de contrôle)'); isin.reportValidity(); return; }
      const v = {
        nom: nom.value.trim(), ticker: ticker.value.trim().toUpperCase() || null, isin: codeIsin || null, type: type.value,
        quantite: nombreSaisi(quantite.value), prix_revient: nombreSaisi(pru.value), devise: devise.value.trim().toUpperCase() || null,
        valeur: nombreSaisi(valeur.value),
        categorie: {
          classe: classe.value || undefined, zone: zone.value || undefined, secteur: secteur.value || undefined, indice: indice.value.trim().toUpperCase() || undefined,
          themes: themes.map((t) => t.querySelector('input')).filter((i) => i.checked).map((i) => i.value),
        },
      };
      if (!Object.values(v.categorie).some((x) => (Array.isArray(x) ? x.length : x))) delete v.categorie;
      if (v.valeur != null && v.valeur !== ligne?.valeur) { v.date_valeur = new Date().toISOString().slice(0, 10); v.source_valeur = 'valeur saisie'; }
      if (ligne) Object.assign(ligne, v); else pf.lignes.push({ id: nouvelId(), ...v, cours: null, date_valeur: v.date_valeur ?? null });
      action = null;
      await sauver();
      dessiner();
      if (!v.ticker && v.isin) resoudreLignes(pf);
      chargerFichesDetenues();
    },
  },
  el('div', { class: 'champs' },
    champ('Nom', nom),
    champ('Type', type),
    champ('Ticker (Yahoo)', ticker, 'laisser vide : recherché à partir de l’ISIN'),
    champ('ISIN', isin),
    champ('Quantité', quantite),
    champ('Prix de revient unitaire', pru, 'dans la devise de cotation'),
    champ('Devise de cotation', devise),
    champ('Valeur actuelle (€)', valeur, 'facultatif : utilisée si aucun cours n’est connu'),
  ),
  el('details', { class: 'mpf-categorie', open: ['fonds', 'etf'].includes(l.type) || Boolean(l.categorie) },
    el('summary', {}, 'Catégorie (fonds, ETF, unités de compte)'),
    el('div', { class: 'champs' },
      champ('Classe d’actifs', classe),
      champ('Zone ou pays', zone),
      champ('Secteur', secteur),
      champ('Indice de référence', indice, 'pour les corrélations d’un fonds sans historique'),
    ),
    el('div', { class: 'mpf-cases' }, themes),
  ),
  el('button', { class: 'bouton bouton--accent bouton--plein', type: 'submit' }, ligne ? 'Enregistrer' : 'Ajouter la ligne'));
}

/* ============================== Import ============================== */

function panneauImport() {
  const a = action;
  if (a.etape === 'fichier') {
    const entree = el('input', { type: 'file', accept: '.csv,.txt,.tsv,.xlsx,.xls,.xlsm,.ods,text/csv' });
    entree.addEventListener('change', async () => {
      const f = entree.files?.[0];
      if (!f) return;
      try {
        const lignes = await lireFichier(f);
        if (!lignes.length) throw new Error('fichier vide');
        const det = detecterColonnes(lignes);
        action = { ...a, nomFichier: f.name, lignes, det, etape: correspondanceSuffisante(det.correspondance) ? 'apercu' : 'correspondance' };
      } catch (e) {
        action = { ...a, erreur: `Lecture impossible : ${e.message}` };
      }
      dessiner();
    });
    return [
      el('p', { class: 'chef-texte' }, 'Exportez vos positions depuis l’espace client du courtier (CSV ou Excel), puis choisissez le fichier. Il est lu sur cet appareil et n’est envoyé nulle part.'),
      a.erreur ? el('p', { class: 'chef-avertissement' }, a.erreur) : null,
      el('label', { class: 'champ' }, el('span', {}, 'Fichier'), entree),
      el('p', { class: 'chef-petit' }, 'BoursoBank : Mon portefeuille › Positions › Exporter (CSV). Colonnes reconnues : nom ou libellé, ISIN, ticker, quantité, prix de revient, cours, valeur ou valorisation, devise.'),
    ];
  }
  if (a.etape === 'correspondance') return correspondanceColonnes();
  return apercuImport();
}

function correspondanceColonnes() {
  const a = action;
  const entete = a.det.indice >= 0 ? a.lignes[a.det.indice] : a.lignes[0].map((_, j) => `Colonne ${j + 1}`);
  const ligneEntete = el('input', { type: 'number', min: 0, max: Math.min(a.lignes.length - 1, 30), value: Math.max(a.det.indice, -1) + 1 });
  const selects = Object.fromEntries(Object.entries(CHAMPS).map(([cle, c]) => [cle, el('select', { 'aria-label': c.libelle },
    el('option', { value: '' }, '—'),
    entete.map((t, j) => el('option', { value: String(j), selected: a.det.correspondance[cle] === j }, `${j + 1}. ${t || '(sans titre)'}`)))]));
  const apercu = a.lignes.slice(Math.max(a.det.indice, 0), Math.max(a.det.indice, 0) + 5);
  return [
    el('p', { class: 'chef-avertissement' }, 'Colonnes non reconnues automatiquement : indiquez lesquelles correspondent à chaque information (au minimum un nom, un ISIN ou un ticker, et une quantité ou une valeur).'),
    champ('Numéro de la ligne d’en-tête (0 = aucune)', ligneEntete),
    el('div', { class: 'tableau-defilant' }, el('table', { class: 'tableau mpf-apercu' }, el('tbody', {}, apercu.map((l) => el('tr', {}, l.map((c) => el('td', {}, c))))))),
    el('div', { class: 'champs' }, Object.entries(CHAMPS).map(([cle, c]) => champ(c.libelle, selects[cle]))),
    el('button', {
      class: 'bouton bouton--accent bouton--plein', type: 'button',
      onclick: () => {
        const correspondance = {};
        for (const [cle, s] of Object.entries(selects)) if (s.value !== '') correspondance[cle] = Number(s.value);
        const indice = Math.max(Number(ligneEntete.value) - 1, -1);
        if (!correspondanceSuffisante(correspondance)) { afficherMessage('Correspondance incomplète : il faut un nom, un ISIN ou un ticker, et une quantité ou une valeur.', 'erreur'); return; }
        action = { ...a, det: { indice, correspondance }, etape: 'apercu' };
        dessiner();
      },
    }, 'Continuer'),
  ];
}

function apercuImport() {
  const a = action;
  const lignes = construireLignes(a.lignes, a.det);
  const cible = el('select', {},
    el('option', { value: '' }, 'Nouveau portefeuille…'),
    etat.portefeuilles.map((p) => el('option', { value: p.id, selected: p.id === (a.cible ?? vue) }, p.nom)));
  const nomNouveau = el('input', { type: 'text', value: (a.nomFichier ?? 'Import').replace(/\.[^.]+$/, '').slice(0, 40) });
  const typeNouveau = el('select', {}, options(TYPES_PORTEFEUILLE, 'cto'));
  const mode = el('select', {}, el('option', { value: 'remplacer' }, 'Remplacer les lignes existantes'), el('option', { value: 'ajouter' }, 'Ajouter aux lignes existantes'));
  const blocNouveau = el('div', { class: 'champs' }, champ('Nom du nouveau portefeuille', nomNouveau), champ('Type', typeNouveau));
  const majCible = () => { blocNouveau.hidden = Boolean(cible.value); mode.disabled = !cible.value; };
  cible.addEventListener('change', majCible);
  majCible();
  const valeurTotale = lignes.reduce((s, l) => s + (l.valeur ?? 0), 0);
  return [
    el('p', { class: 'chef-texte' }, `${lignes.length} ligne(s) reconnue(s) dans « ${a.nomFichier} »${valeurTotale ? `, ${eur(valeurTotale)} au total` : ''}.`),
    el('div', { class: 'tableau-defilant' }, el('table', { class: 'tableau mpf-apercu' },
      el('thead', {}, el('tr', {}, ['Nom', 'ISIN / ticker', 'Quantité', 'PRU', 'Valeur'].map((t) => el('th', {}, t)))),
      el('tbody', {}, lignes.slice(0, 8).map((l) => el('tr', {},
        el('td', {}, l.nom), el('td', {}, l.isin ?? l.ticker ?? '—'),
        el('td', { class: 'nombre' }, l.quantite == null ? '—' : nombre(l.quantite, l.quantite % 1 ? 4 : 0)),
        el('td', { class: 'nombre' }, l.prix_revient == null ? '—' : nombre(l.prix_revient, 2)),
        el('td', { class: 'nombre' }, l.valeur == null ? '—' : nombre(l.valeur, 2))))))),
    lignes.length > 8 ? el('p', { class: 'chef-petit' }, `… et ${lignes.length - 8} autre(s).`) : null,
    el('div', { class: 'champs' }, champ('Portefeuille', cible), champ('Mode', mode)),
    blocNouveau,
    el('p', { class: 'chef-petit' }, 'La valeur du fichier est considérée en euros. Les ISIN sans ticker sont recherchés ensuite ; les fonds non reconnus sont classés « fonds », catégorie à saisir.'),
    el('div', { class: 'mpf-boutons' },
      el('button', { class: 'bouton', type: 'button', onclick: () => { action = { ...a, etape: 'correspondance' }; dessiner(); } }, 'Corriger les colonnes'),
      el('button', {
        class: 'bouton bouton--accent', type: 'button', disabled: !lignes.length,
        onclick: async () => {
          let pf = etat.portefeuilles.find((p) => p.id === cible.value);
          if (!pf) {
            pf = { id: nouvelId('p'), nom: nomNouveau.value.trim() || 'Import', type: typeNouveau.value, source: 'fichier', cree_le: new Date().toISOString(), lignes: [], historique: [], reference: null };
            etat.portefeuilles.push(pf);
          }
          const jour = new Date().toISOString().slice(0, 10);
          const anciennes = new Map(pf.lignes.map((l) => [(l.isin || l.ticker || l.nom).toUpperCase(), l]));
          const nouvelles = lignes.map((l) => {
            const avant = anciennes.get((l.isin || l.ticker || l.nom).toUpperCase());
            return {
              id: avant?.id ?? nouvelId(), ...l, ticker: l.ticker ?? avant?.ticker ?? null, type: avant?.type ?? (l.ticker ? 'action' : l.isin ? 'action' : 'fonds'),
              categorie: avant?.categorie, date_valeur: l.valeur != null ? jour : null, source_valeur: l.valeur != null ? `fichier du ${dateFr(jour)}` : null,
            };
          });
          pf.lignes = mode.value === 'ajouter' && cible.value ? [...pf.lignes, ...nouvelles] : nouvelles;
          pf.maj_le = new Date().toISOString();
          vue = pf.id;
          onglet = 'positions';
          action = null;
          await sauver();
          afficherMessage(`${nouvelles.length} ligne(s) importée(s) dans « ${pf.nom} ».`);
          resoudreLignes(pf);
          chargerFichesDetenues();
        },
      }, 'Importer'),
    ),
  ];
}

/**
 * Résout les ISIN sans ticker : d'abord sur l'appareil, puis Yahoo (ISIN seulement, jamais les montants).
 * Les titres non reconnus restent des « fonds » dont la catégorie se saisit à la main.
 */
async function resoudreLignes(pf) {
  const aResoudre = pf.lignes.filter((l) => l.isin && !l.ticker);
  if (!aResoudre.length) return;
  const reseau = etat.reglages.requetes_par_titre;
  resolutionEnCours = aResoudre.length;
  dessiner();
  for (const l of aResoudre) {
    let r = etat.resolutions[l.isin];
    if (!r) {
      r = await resoudreISIN(l.isin, { nom: l.nom, entreprises: ctx.d.entreprises, reseau: reseau && r === undefined });
      if (r || reseau) etat.resolutions[l.isin] = r; // null = non reconnu (mémorisé : pas de nouvelle requête)
    }
    if (r?.ticker && r.type !== 'fonds') { l.ticker = r.ticker; l.type = r.type === 'autre' ? 'action' : r.type; } else l.type = 'fonds';
    resolutionEnCours -= 1;
  }
  resolutionEnCours = 0;
  await sauver();
  chargerFichesDetenues();
  dessiner();
}

/* ============================== Sauvegarde, synchronisation, réglages ============================== */

function telecharger(nom, contenu) {
  const url = URL.createObjectURL(new Blob([contenu], { type: 'application/json' }));
  const a = el('a', { href: url, download: nom });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function reglages() {
  const s = etat.reglages.synchro;
  return el('details', { class: 'carte mpf-reglages', open: ouvrirReglages, ontoggle: (e) => { ouvrirReglages = e.target.open; } },
    el('summary', { class: 'section-titre' }, 'Sauvegarde, synchronisation et réglages'),
    blocSauvegarde(),
    blocSynchro(s),
    el('section', { class: 'mpf-bloc' },
      el('h4', {}, 'Requêtes par titre'),
      el('label', { class: 'mpf-case' },
        el('input', { type: 'checkbox', checked: etat.reglages.requetes_par_titre, onchange: async (e) => { etat.reglages.requetes_par_titre = e.target.checked; await sauver(); if (e.target.checked) chargerFichesDetenues(); dessiner(); } }),
        'Autoriser la recherche des tickers sur Yahoo Finance (ISIN seulement) et le chargement des fiches publiques des sociétés détenues'),
      el('p', { class: 'chef-petit' }, 'Désactivé : aucune requête ne mentionne un titre détenu ; les ISIN ne sont rapprochés que sur l’appareil et le crible des sociétés est réduit à la note de l’agent.'),
    ),
    el('section', { class: 'mpf-bloc' },
      el('h4', {}, 'Effacer'),
      el('button', {
        class: 'bouton bouton--danger', type: 'button',
        onclick: async () => {
          if (!confirm('Effacer de cet appareil tous les portefeuilles, réglages et la clé de synchronisation ?')) return;
          await toutEffacer();
          etat = etatVide();
          vue = 'global';
          afficherMessage('Tout a été effacé de cet appareil.');
        },
      }, 'Tout effacer de cet appareil'),
    ),
  );
}

function blocSauvegarde() {
  const mdp = el('input', { type: 'password', autocomplete: 'new-password', minlength: 10, placeholder: '10 caractères minimum' });
  const mdp2 = el('input', { type: 'password', autocomplete: 'new-password', placeholder: 'confirmation' });
  const fichier = el('input', { type: 'file', accept: '.json,application/json' });
  const mdpImport = el('input', { type: 'password', autocomplete: 'current-password' });
  return el('section', { class: 'mpf-bloc' },
    el('h4', {}, 'Sauvegarde chiffrée (changer d’appareil)'),
    el('p', { class: 'chef-petit' }, 'Fichier chiffré AES-256-GCM avec votre mot de passe (PBKDF2, 600 000 itérations). Sans le mot de passe, il est illisible et impossible à récupérer. Ne le déposez jamais dans le dépôt de l’appli.'),
    el('div', { class: 'champs' }, champ('Mot de passe', mdp), champ('Confirmer', mdp2)),
    el('button', {
      class: 'bouton bouton--accent', type: 'button',
      onclick: async () => {
        if (mdp.value.length < 10) { afficherMessage('Mot de passe trop court (10 caractères minimum).', 'erreur'); return; }
        if (mdp.value !== mdp2.value) { afficherMessage('Les deux mots de passe diffèrent.', 'erreur'); return; }
        try {
          const env = await chiffrer(contenuSauvegarde(etat), mdp.value);
          telecharger(`mes-portefeuilles-${new Date().toISOString().slice(0, 10)}.chiffre.json`, JSON.stringify(env));
          afficherMessage('Sauvegarde chiffrée téléchargée.');
        } catch (e) { afficherMessage(e.message, 'erreur'); }
      },
    }, 'Exporter la sauvegarde chiffrée'),
    el('div', { class: 'champs mpf-espace' }, champ('Fichier de sauvegarde', fichier), champ('Mot de passe', mdpImport)),
    el('button', {
      class: 'bouton', type: 'button',
      onclick: async () => {
        const f = fichier.files?.[0];
        if (!f) { afficherMessage('Choisissez d’abord le fichier de sauvegarde.', 'erreur'); return; }
        try {
          const env = JSON.parse(await f.text());
          if (!estEnveloppe(env)) throw new Error('Ce fichier n’est pas une sauvegarde chiffrée de « Mes portefeuilles ».');
          const c = await dechiffrer(env, mdpImport.value);
          if (!Array.isArray(c.portefeuilles)) throw new Error('Contenu inattendu.');
          if (etat.portefeuilles.length && !confirm(`Remplacer les ${etat.portefeuilles.length} portefeuille(s) de cet appareil par les ${c.portefeuilles.length} de la sauvegarde ?`)) return;
          etat.portefeuilles = c.portefeuilles;
          etat.resolutions = { ...etat.resolutions, ...(c.resolutions ?? {}) };
          if (c.reglages) etat.reglages = { ...etat.reglages, requetes_par_titre: c.reglages.requetes_par_titre ?? true, synchro: { ...etat.reglages.synchro, ...c.reglages.synchro, jeton: etat.reglages.synchro.jeton } };
          vue = 'global';
          await sauver();
          chargerFichesDetenues();
          afficherMessage(`${c.portefeuilles.length} portefeuille(s) restauré(s).`);
        } catch (e) { afficherMessage(e.message, 'erreur'); }
      },
    }, 'Restaurer'),
  );
}

function blocSynchro(s) {
  const depot = el('input', { type: 'text', value: s.depot, placeholder: 'propriétaire/depot-prive' });
  const branche = el('input', { type: 'text', value: s.branche, placeholder: 'synchro' });
  const chemin = el('input', { type: 'text', value: s.chemin, placeholder: 'portefeuilles.chiffre.json' });
  const jeton = el('input', { type: 'password', value: s.jeton, autocomplete: 'off', placeholder: 'github_pat_… (lecture seule)' });
  const url = el('input', { type: 'url', value: s.url, placeholder: 'facultatif : adresse directe du fichier chiffré' });
  const mdp = el('input', { type: 'password', autocomplete: 'off', placeholder: etat.cle_synchro ? 'déjà saisi sur cet appareil' : 'mot de passe du secret PORTEFEUILLE_MOT_DE_PASSE' });
  const active = el('input', { type: 'checkbox', checked: s.active });
  const enregistrer = async () => {
    etat.reglages.synchro = { depot: depot.value.trim(), branche: branche.value.trim() || 'synchro', chemin: chemin.value.trim() || 'portefeuilles.chiffre.json', jeton: jeton.value.trim(), url: url.value.trim(), active: active.checked };
    if (mdp.value) await memoriserMotDePasse(etat, mdp.value);
    await sauver();
  };
  const etatSynchro = etat.synchro.erreur ? `Dernier essai en échec : ${etat.synchro.erreur}`
    : etat.synchro.derniere ? `Dernière synchronisation : ${dateHeure(etat.synchro.derniere)} (fichier produit le ${dateHeure(etat.synchro.genere_le)}).` : 'Jamais synchronisé.';
  return el('section', { class: 'mpf-bloc' },
    el('h4', {}, 'Synchronisation automatique (facultative)'),
    el('p', { class: 'chef-petit' }, 'Un dépôt GitHub PRIVÉ récupère chaque jour vos positions (Interactive Brokers, eToro), les chiffre avec votre mot de passe et publie le fichier chiffré. L’appli le télécharge avec un jeton en lecture seule et le déchiffre ici. Mode d’emploi : outils/synchro-portefeuilles/README.md. BoursoBank n’a pas d’API : import CSV manuel.'),
    el('div', { class: 'champs' },
      champ('Dépôt privé', depot), champ('Branche', branche), champ('Fichier', chemin),
      champ('Jeton GitHub (lecture seule)', jeton, 'conservé sur cet appareil uniquement'),
      champ('Adresse directe (sinon)', url),
      champ('Mot de passe de chiffrement', mdp, 'saisi une fois : seule une clé dérivée non extractible est conservée'),
    ),
    el('label', { class: 'mpf-case' }, active, 'Synchroniser automatiquement à l’ouverture de l’écran (au plus deux fois par jour)'),
    el('p', { class: 'chef-petit' }, adresseSynchro({ depot: depot.value, branche: branche.value, chemin: chemin.value, url: url.value }) ? etatSynchro : 'Renseignez le dépôt privé (ou une adresse directe).'),
    el('div', { class: 'mpf-boutons' },
      el('button', { class: 'bouton', type: 'button', onclick: async () => { await enregistrer(); afficherMessage('Réglages de synchronisation enregistrés sur cet appareil.'); } }, 'Enregistrer'),
      el('button', { class: 'bouton bouton--accent', type: 'button', disabled: synchroEnCours, onclick: async () => { await enregistrer(); synchroniser(false); } }, synchroEnCours ? 'Synchronisation…' : 'Synchroniser maintenant'),
      etat.cle_synchro ? el('button', { class: 'bouton', type: 'button', onclick: async () => { etat.cle_synchro = null; await sauver(); afficherMessage('Mot de passe de synchronisation oublié sur cet appareil.'); } }, 'Oublier le mot de passe') : null,
    ),
  );
}

async function synchroniser(silencieux) {
  if (synchroEnCours) return;
  synchroEnCours = true;
  if (!silencieux) dessiner();
  try {
    const contenu = await telechargerSynchro(etat);
    const bilan = integrerSynchro(etat, contenu);
    await sauver();
    chargerFichesDetenues();
    synchroEnCours = false;
    if (contenu.erreurs?.length) afficherMessage(`Synchronisation partielle : ${bilan.map((b) => `${b.nom} (${b.lignes} lignes)`).join(', ')}. ${contenu.erreurs.join(' ; ')}`, 'erreur');
    else if (!silencieux) afficherMessage(`Synchronisé : ${bilan.map((b) => `${b.nom} (${b.lignes} lignes)`).join(', ')}.`);
    else dessiner();
  } catch (e) {
    synchroEnCours = false;
    etat.synchro = { ...etat.synchro, erreur: e.message };
    await sauver();
    if (!silencieux) afficherMessage(`Synchronisation impossible : ${e.message}`, 'erreur');
    else dessiner();
  }
}
