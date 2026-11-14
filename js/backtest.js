/* ==========================================================================
   Écran « Backtest » (Menu → Suivi) : quels signaux des agents sont réellement
   prédictifs ? Lit data/backtest/resultats.json (agent backtest, mensuel ;
   méthode : agents/backtest/methode.md). Lecture seule : rien n'est modifié
   automatiquement, les nouvelles pondérations sont proposées dans une pull request.
   ========================================================================== */

import { el, nombre } from './outils.js';

const ORDRE = { Garder: 0, 'Alléger': 1, Supprimer: 2, 'Données insuffisantes': 3 };
const SECTIONS = ['pays', 'chef', 'entreprises', 'matieres', 'secteurs', 'tendance'];
const NOTES = ['note_globale', 'note_globale_brute', 'note_recalibree', 'score_chef', 'equipondere', 'score_recalibre'];

/** Classe CSS du badge d'un verdict. */
export function classeVerdict(v) {
  return { Garder: 'bt-verdict--garder', 'Alléger': 'bt-verdict--alleger', Supprimer: 'bt-verdict--supprimer' }[v] ?? 'bt-verdict--insuffisant';
}

/** Signaux d'une section : d'abord les indicateurs (Garder, Alléger, Supprimer, insuffisant), puis les notes. */
export function trierSignaux(signaux = {}) {
  const cles = Object.keys(signaux);
  const notes = NOTES.filter((k) => cles.includes(k));
  const autres = cles.filter((k) => !NOTES.includes(k))
    .sort((a, b) => (ORDRE[signaux[a].verdict] ?? 9) - (ORDRE[signaux[b].verdict] ?? 9)
      || (signaux[b].echantillons?.verification?.ic_moyen ?? -9) - (signaux[a].echantillons?.verification?.ic_moyen ?? -9));
  return [...autres, ...notes];
}

/** Classe CSS du verdict d'une combinaison de signaux. */
export function classeCombinaison(v) {
  if (v === 'Confirmée') return 'bt-verdict--garder';
  if ((v ?? '').startsWith('Prometteuse')) return 'bt-verdict--alleger';
  return 'bt-verdict--supprimer';
}

/** Texte du rapport sans le gras Markdown (« **Ce qui anticipe** » → « Ce qui anticipe »). */
export function sansGras(t) {
  return String(t ?? '').replace(/\*\*/g, '');
}

/** Nombre signé à la française : +0,034 ; n. d. si absent. */
export function signe(x, d = 2, unite = '') {
  if (x === null || x === undefined || Number.isNaN(x)) return 'n. d.';
  const s = x > 0 ? '+' : x < 0 ? '−' : '';
  return `${s}${nombre(Math.abs(x), d)}${unite}`;
}

export async function chargerBacktest() {
  try {
    const r = await fetch('data/backtest/resultats.json', { cache: 'no-cache' });
    if (!r.ok) return null;
    const j = await r.json();
    return j?.donnees ? { meta: j.meta ?? {}, ...j.donnees } : null;
  } catch {
    return null;
  }
}

const titre = (t, sous) => el('h3', { class: 'section-titre' }, t, sous ? el('small', {}, ` ${sous}`) : null);
const badge = (v) => el('span', { class: `bt-verdict ${classeVerdict(v)}` }, v);

function detailSignal(r) {
  const e = r.echantillons ?? {};
  const h = String(r.horizon_reference);
  const reg = r.regimes ?? {};
  const annees = Object.entries(r.stabilite?.par_annee ?? {});
  return el('div', { class: 'bt-detail' },
    el('p', { class: 'chef-petit' }, `${r.verdict} : ${r.raison}.`),
    el('table', { class: 'chef-table' },
      el('thead', {}, el('tr', {}, ['Horizon', 'IC', 't', 'Meilleurs 20 %', 'Pires 20 %', 'Indice', 'Réussite'].map((x) => el('th', {}, x)))),
      el('tbody', {}, Object.entries(r.horizons ?? {}).map(([k, x]) => el('tr', { class: k === h ? 'bt-ligne-ref' : '' },
        el('td', {}, `${k} mois`), el('td', { class: 'mono' }, signe(x.ic_moyen, 3)), el('td', { class: 'mono' }, x.ic_t != null ? nombre(x.ic_t, 1) : 'n. d.'),
        el('td', { class: 'mono' }, signe(x.haut_pct, 1, ' %')), el('td', { class: 'mono' }, signe(x.bas_pct, 1, ' %')),
        el('td', { class: 'mono' }, signe(x.indice_pct, 1, ' %')),
        el('td', { class: 'mono' }, x.reussite_haut_pct != null ? `${nombre(x.reussite_haut_pct, 0)} %` : 'n. d.'))))),
    el('p', { class: 'chef-petit' },
      `Apprentissage (jusqu’à ${e.separation ?? 'n. d.'}) : IC ${signe(e.apprentissage?.ic_moyen, 3)} sur ${e.apprentissage?.mois ?? 0} mois · `
      + `hors échantillon : IC ${signe(e.verification?.ic_moyen, 3)} (t = ${e.verification?.ic_t != null ? nombre(e.verification.ic_t, 1) : 'n. d.'}) sur ${e.verification?.mois ?? 0} mois, `
      + `écart après frais ${signe(e.verification?.ecart_net_annuel_pct, 1, ' %/an')}. `
      + `Mois calmes : IC ${signe(reg.calme?.ic_moyen, 3)} (${reg.calme?.mois ?? 0}) · tension : ${signe(reg.tension?.ic_moyen, 3)} (${reg.tension?.mois ?? 0}). `
      + `Frais : rotation ${nombre(r.frais?.rotation_mensuelle_pct ?? 0, 0)} %/mois, coût ${signe(r.frais?.cout_annuel_pct, 1, ' %/an')}.`),
    annees.length ? el('p', { class: 'chef-petit' }, 'IC par année : ' + annees.map(([a, v]) => `${a} ${signe(v, 2)}`).join(' · ')) : null,
    cible(r.horizons?.['3'], r.horizons?.['6'], r.portefeuille?.verification));
}

const pct = (x) => (x != null ? `${nombre(x, 0)} %` : 'n. d.');
const ratio = (x) => (x != null ? nombre(x, 2) : 'n. d.');

/** Cible : part des actifs retenus qui battent l'indice à 3 et 6 mois, gain moyen / perte moyenne ; panier face à
 *  l'indice et au « momentum seul », hors échantillon. */
function cible(h3, h6, pv) {
  return el('p', { class: 'chef-petit' },
    `Cible : battent l’indice ${pct(h3?.battent_indice_pct)} à 3 mois, ${pct(h6?.battent_indice_pct)} à 6 mois · `
    + `gain / perte ${ratio(h3?.gain_perte)} à 3 mois, ${ratio(h6?.gain_perte)} à 6 mois.`
    + (pv ? ` Panier des meilleurs, hors échantillon : ${signe(pv.vs_indice_annuel_pct, 1, ' pt/an')} face à l’indice, `
      + `${signe(pv.vs_momentum_annuel_pct, 1, ' pt/an')} face au momentum seul.` : ''));
}

function ligneSignal(r) {
  const v = r.echantillons?.verification ?? {};
  const h = r.horizons?.[String(r.horizon_reference)] ?? {};
  return el('details', { class: 'bt-signal' },
    el('summary', {},
      el('span', { class: 'bt-signal-nom' }, r.libelle), badge(r.verdict),
      el('span', { class: 'bt-signal-chiffres mono' },
        `hors échantillon : IC ${signe(v.ic_moyen, 3)} · après frais ${signe(v.ecart_net_annuel_pct, 1, ' %/an')} · meilleurs − pires à ${r.horizon_reference} mois ${signe(h.ecart_pct, 1, ' %')}`
        + (r.portefeuille?.verification?.vs_momentum_annuel_pct != null ? ` · face au momentum seul ${signe(r.portefeuille.verification.vs_momentum_annuel_pct, 1, ' pt/an')}` : ''))),
    detailSignal(r));
}

function biais(s) {
  const b = s.biais_survivant;
  // Pays : tous existent depuis le début (l'écart à l'indice traduit le poids des États-Unis, pas un biais du survivant)
  if (!b || b.univers_complet_vs_indice_pct == null || b.univers_retenu_vs_indice_pct == null) return null;
  return el('p', { class: 'chef-petit bt-alerte' },
    `Biais du survivant mesuré : l’univers actuel rejoué dans le passé fait ${signe(b.univers_complet_vs_indice_pct, 1, ' pt/an')} par rapport à l’indice`
    + ` ; univers testé (sociétés valant déjà au moins ${nombre(b.seuil_capitalisation_usd / 1e9, 0)} Md$ à chaque date) : ${signe(b.univers_retenu_vs_indice_pct, 1, ' pt/an')}.`);
}

function blocRegles(s) {
  const rg = s.regles ?? {};
  const h = String(rg.horizon_reference ?? s.horizon_reference);
  const blocs = [];
  const v = rg.verdicts?.par_verdict?.[h];
  if (v) {
    blocs.push(titre('Seuils des verdicts', `${h} mois, performance relative à l’indice`),
      el('table', { class: 'chef-table' },
        el('thead', {}, el('tr', {}, ['Verdict', 'Cas', 'Relatif moyen', 'Réussite'].map((x) => el('th', {}, x)))),
        el('tbody', {}, Object.entries(v).filter(([k]) => !k.startsWith('_')).map(([k, x]) => el('tr', {},
          el('td', {}, k), el('td', { class: 'mono' }, String(x.n ?? 0)), el('td', { class: 'mono' }, signe(x.relative_moyenne_pct, 2, ' pt')),
          el('td', { class: 'mono' }, x.reussite_pct != null ? `${nombre(x.reussite_pct, 0)} %` : 'n. d.'))))),
      el('p', { class: `chef-petit ${v._ordonne ? 'chef-ok' : 'chef-ko'}` }, v._ordonne ? 'Verdicts ordonnés : la performance croît avec le verdict.' : 'Verdicts non ordonnés : les seuils ne séparent pas nettement les pays.'));
  }
  const c = rg.verdicts?.par_conviction?.[h];
  if (c) {
    blocs.push(titre('Conviction', 'verdicts positifs'), el('ul', { class: 'chef-texte' }, Object.entries(c).map(([k, x]) =>
      el('li', {}, `${k} : réussite ${x.reussite_pct != null ? nombre(x.reussite_pct, 0) + ' %' : 'n. d.'}, ${signe(x.relative_moyenne_pct, 2, ' pt')} (${x.n ?? 0} cas)`))));
  }
  const ae = rg.anti_euphorie?.horizons?.[h];
  if (ae) {
    blocs.push(titre('Règle anti-euphorie', `momentum extrême, ${h} mois`), el('ul', { class: 'chef-texte' },
      el('li', {}, `Après un momentum extrême : ${signe(ae.extreme.relative_moyenne_pct, 2, ' pt')} (${ae.extreme.n} cas)`),
      el('li', {}, `Autres tendances positives : ${signe(ae.tendance_positive_non_extreme.relative_moyenne_pct, 2, ' pt')} (${ae.tendance_positive_non_extreme.n} cas)`),
      el('li', {}, `Extrême et valorisation tendue : ${signe(ae.extreme_valorisation_tendue.relative_moyenne_pct, 2, ' pt')} · valorisation correcte : ${signe(ae.extreme_valorisation_correcte.relative_moyenne_pct, 2, ' pt')}`)));
  }
  const td = rg.tendance?.horizons?.[h];
  if (td) {
    blocs.push(titre('Suivi de tendance', `chef d'orchestre, ${h} mois`), el('ul', { class: 'chef-texte' },
      el('li', {}, `Tendances fortes saines : ${signe(td.forte_saine.relative_moyenne_pct, 2, ' pt')} (${td.forte_saine.n} cas)`),
      el('li', {}, `Tendances fortes en excès : ${signe(td.forte_en_exces.relative_moyenne_pct, 2, ' pt')} (${td.forte_en_exces.n} cas)`),
      el('li', {}, `Autres pays : ${signe(td.autres.relative_moyenne_pct, 2, ' pt')} (${td.autres.n} cas)`)));
  }
  const co = rg.concentration;
  if (co?.lignes) {
    const ligne = (nom, x) => el('tr', {}, el('td', {}, nom), el('td', { class: 'mono' }, signe(x?.rendement_annuel_pct, 1, ' %')),
      el('td', { class: 'mono' }, x?.volatilite_pct != null ? `${nombre(x.volatilite_pct, 1)} %` : 'n. d.'),
      el('td', { class: 'mono' }, signe(x?.sharpe, 2)), el('td', { class: 'mono' }, signe(x?.perte_max_pct, 0, ' %')));
    blocs.push(titre('Concentration du trader', `hors échantillon ; règle actuelle : ${co.regle_actuelle} lignes au plus`),
      el('table', { class: 'chef-table' },
        el('thead', {}, el('tr', {}, ['Lignes', 'Rendement /an', 'Volatilité', 'Sharpe', 'Perte max'].map((x) => el('th', {}, x)))),
        el('tbody', {}, ...Object.entries(co.lignes).map(([k, x]) => ligne(k === 'toutes' ? 'sans limite' : `${k} lignes`, x.verification)),
          ligne('pays équipondérés', co.equipondere?.verification), co.indice ? ligne(`indice (${s.indice})`, co.indice.verification) : null)));
  }
  const st = rg.stops;
  if (st?.total?.positions) {
    const x = st.verification?.positions ? st.verification : st.total;
    blocs.push(titre('Stops et prise de bénéfices du trader', `${st.lignes} meilleures sociétés par mois, gardées ${st.detention_mois} mois`),
      el('ul', { class: 'chef-texte' },
        el('li', {}, `Avec les règles : ${signe(x.moyenne_avec_pct, 1, ' %')} en moyenne, pire ${signe(x.pire_avec_pct, 0, ' %')}, réussite ${nombre(x.reussite_avec_pct ?? 0, 0)} %`),
        el('li', {}, `Sans : ${signe(x.moyenne_sans_pct, 1, ' %')}, pire ${signe(x.pire_sans_pct, 0, ' %')}, réussite ${nombre(x.reussite_sans_pct ?? 0, 0)} %`),
        el('li', { class: 'chef-petit' }, `${x.positions} positions · sorties : ${Object.entries(st.motifs ?? {}).map(([k, n]) => `${k} ${n}`).join(', ')}`)));
  }
  return blocs;
}

// Lot « tendance » : périodes de momentum, excès, poche « tendance » du trader
export function blocTendance(t) {
  if (!t) return [];
  const defs = t.periodes?.definitions ?? {};
  const poche = t.poche ?? {};
  const ret = (poche.variantes ?? []).find((v) => v.definition === poche.retenue?.definition && v.variante === poche.retenue?.variante);
  const ligneP = (nom, x) => el('tr', {}, el('td', {}, nom),
    el('td', { class: 'mono' }, `${signe(x?.apprentissage?.rendement_annuel_pct, 1, ' %')} / ${signe(x?.verification?.rendement_annuel_pct, 1, ' %')}`),
    el('td', { class: 'mono' }, `${signe(x?.apprentissage?.sharpe, 2)} / ${signe(x?.verification?.sharpe, 2)}`),
    el('td', { class: 'mono' }, `${signe(x?.apprentissage?.perte_max_pct, 0, ' %')} / ${signe(x?.verification?.perte_max_pct, 0, ' %')}`));
  const exces = ['parabolique', 'valorisation', 'positionnement'].filter((k) => t.exces?.[k]);
  return [
    titre('Périodes de momentum', `IC moyen dans chaque catégorie, apprentissage / vérification ; retenue : ${defs[t.definition]?.libelle ?? t.definition}`),
    el('table', { class: 'chef-table' },
      el('thead', {}, el('tr', {}, ['Période', 'IC 1 mois', 'IC 3 mois'].map((x) => el('th', {}, x)))),
      el('tbody', {}, Object.entries(defs).map(([k, d]) => el('tr', { class: k === t.definition ? 'chef-ok' : '' }, el('td', {}, d.libelle),
        el('td', { class: 'mono' }, `${signe(d.ic_1m?.apprentissage, 3)} / ${signe(d.ic_1m?.verification, 3)}`),
        el('td', { class: 'mono' }, `${signe(d.ic_3m?.apprentissage, 3)} / ${signe(d.ic_3m?.verification, 3)}`))))),
    titre('Excès retenus', 'tendances fortes : écart de rendement à 3 mois, en excès − autres'),
    el('ul', { class: 'chef-texte' }, exces.map((k) => {
      const e = t.exces[k];
      const d = e.retenu != null ? e.seuils[e.retenu]['3m'] : null;
      return el('li', {}, `${k} : ${e.retenu != null ? `seuil ${e.retenu}, ${signe(d.ecart_apprentissage_pct, 2, ' pt')} / ${signe(d.ecart_verification_pct, 2, ' pt')}${e.confirme ? ' (confirmé hors échantillon)' : ' (non confirmé)'}` : 'aucun seuil ne pénalise les excès'}`);
    })),
    titre('Poche « tendance »', `${poche.lignes ?? '?'} lignes au plus ; rendement, Sharpe, perte max : apprentissage / vérification`),
    el('table', { class: 'chef-table' },
      el('thead', {}, el('tr', {}, ['Règle', 'Rendement annuel', 'Sharpe', 'Perte max'].map((x) => el('th', {}, x)))),
      el('tbody', {}, ret ? ligneP(`Retenue : ${ret.definition}, ${ret.variante}`, ret) : null,
        ...Object.entries(poche.references ?? {}).map(([k, x]) => ligneP(k === 'indice' ? 'Indice mondial (ACWI)' : 'Univers équipondéré', x)))),
  ];
}

function blocReference(s) {
  const ref = s.reference_momentum;
  if (!ref?.verification) return [];
  const v = ref.verification;
  return [titre('Référence « momentum seul »', ref.regle ?? ''),
    el('p', { class: 'chef-petit' },
      `Hors échantillon : ${signe(v.rendement_annuel_pct, 1, ' %/an')} (${signe(v.vs_indice_annuel_pct, 1, ' pt/an')} face à l’indice), Sharpe ${signe(v.sharpe, 2)}, `
      + `perte max ${signe(v.perte_max_pct, 0, ' %')}. Ses actifs battent l’indice ${pct(ref.cible?.['3']?.battent_indice_pct)} à 3 mois, `
      + `${pct(ref.cible?.['6']?.battent_indice_pct)} à 6 mois (gain / perte ${ratio(ref.cible?.['6']?.gain_perte)}). `
      + 'Chaque signal est comparé à cette règle sans analyse.')];
}

function blocCombinaisons(s) {
  const c = s.combinaisons;
  if (!c) return [];
  return [titre('Combinaisons de signaux', `${c.essais} essais · seuil t ≥ ${c.seuil_t_bonferroni != null ? nombre(c.seuil_t_bonferroni, 2) : 'n. d.'} (Bonferroni)`),
    el('p', { class: 'chef-petit' }, `Règle : ${c.regle}. Combinaisons choisies sur l’apprentissage, jugées hors échantillon (correction de Holm). `
      + `${c.passent_bonferroni_apprentissage ?? 0} combinaison(s) passent le seuil corrigé sur l’apprentissage.`),
    c.retenues?.length ? el('ul', { class: 'chef-texte bt-combinaisons' }, c.retenues.map((r) => {
      const v = r.comparaison?.verification ?? {};
      const cv = r.cible_verification ?? r.cible ?? {};
      return el('li', {}, el('span', { class: `bt-verdict ${classeCombinaison(r.verdict)}` }, r.verdict), ' ', el('strong', {}, r.libelle),
        el('span', { class: 'chef-petit' }, ` · face à l’indice ${signe(v.vs_indice_annuel_pct, 1, ' pt/an')}, au momentum seul ${signe(v.vs_momentum_annuel_pct, 1, ' pt/an')}`
          + ` · p corrigée ${r.p_holm != null ? nombre(r.p_holm, 3) : 'n. d.'} · battent l’indice ${pct(cv['3']?.battent_indice_pct)} / ${pct(cv['6']?.battent_indice_pct)} (3 / 6 mois)`
          + ` · gain / perte ${ratio(cv['6']?.gain_perte)} · ${r.taille_moyenne != null ? nombre(r.taille_moyenne, 1) : '?'} actif(s) en moyenne`));
    })) : el('p', { class: 'chef-petit' }, 'Aucune combinaison testable.')];
}

function section(s) {
  if (s.suivi_tendance) {
    const p = s.suivi_tendance.periode ?? {};
    return el('section', { class: 'bt-section' }, titre(s.titre, `${p.debut ?? '?'} → ${p.fin ?? '?'} · coupure au ${s.separation ?? '?'}`),
      ...blocTendance(s.suivi_tendance));
  }
  const p = s.periode ?? {};
  return el('section', { class: 'bt-section' },
    titre(s.titre, `${p.debut ?? '?'} → ${p.fin ?? '?'} · ${p.actifs ?? 0} actifs · horizon ${s.horizon_reference} mois · indice ${s.indice ?? 'n. d.'}`),
    biais(s),
    ...trierSignaux(s.signaux).map((k) => ligneSignal(s.signaux[k])),
    ...blocReference(s),
    ...blocCombinaisons(s),
    ...blocRegles(s));
}

function propositions(res) {
  const ps = res.propositions ?? [];
  if (!ps.length) return null;
  return el('section', { class: 'bt-section' }, titre('Note actuelle contre note recalibrée', 'jugées hors échantillon'),
    el('table', { class: 'chef-table' },
      el('thead', {}, el('tr', {}, ['Réglage', 'IC actuel → recalibré', 'Après frais', 'Proposée'].map((x) => el('th', {}, x)))),
      el('tbody', {}, ps.map((p) => el('tr', {},
        el('td', {}, `${p.agent} · ${p.chemin.join(' → ')}`),
        el('td', { class: 'mono' }, `${signe(p.note_actuelle?.ic_verification, 3)} → ${signe(p.note_recalibree?.ic_verification, 3)}`),
        el('td', { class: 'mono' }, `${signe(p.note_actuelle?.ecart_net_verification_pct, 1, ' %')} → ${signe(p.note_recalibree?.ecart_net_verification_pct, 1, ' %')}`),
        el('td', { class: p.retenue ? 'chef-ok' : '' }, p.retenue ? 'oui' : 'non'))))),
    el('p', { class: 'chef-petit' }, 'Une proposition retenue est ouverte dans une pull request séparée, à valider à la main : aucune pondération n’est modifiée automatiquement.'));
}

export function ecranBacktest(res) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Suivi · agent backtest'),
    el('h2', { class: 'fiche-titre' }, 'Backtest des règles de notation'));
  if (res === undefined) return [entete, el('p', { class: 'sante-ligne' }, 'Chargement…')];
  if (!res) return [entete, el('p', { class: 'sante-ligne' }, 'Aucun backtest encore (data/backtest/resultats.json introuvable). Il tourne chaque mois, ou à la main : Actions → « Backtest ».')];
  const m = res.methode ?? {};
  return [
    entete,
    res.meta?.fictif ? el('p', { class: 'chef-petit bt-alerte' }, 'Données de test (synthétiques) : aucun résultat réel.') : null,
    el('p', { class: 'chef-petit' },
      `Backtest du ${res.jour ?? 'n. d.'} · rééquilibrage mensuel · meilleurs ${m.quantile_pct ?? 20} % contre pires ${m.quantile_pct ?? 20} % et contre l’indice · `
      + `horizons ${(m.horizons_mois ?? []).join(', ')} mois · frais inclus · verdict jugé hors échantillon (seconde moitié de l’historique). `
      + `Rapport complet : ${res.meta?.rapport ?? 'data/backtest/'}.`),
    res.en_bref?.length ? el('section', { class: 'bt-section' }, titre('En bref'),
      el('ul', { class: 'chef-texte bt-en-bref' }, res.en_bref.map((l) => el('li', {}, sansGras(l).replace(/^\d+\.\s*/, ''))))) : null,
    el('p', { class: 'bt-synthese' }, Object.entries(res.verdicts ?? {}).sort((a, b) => (ORDRE[a[0]] ?? 9) - (ORDRE[b[0]] ?? 9))
      .map(([v, n]) => el('span', { class: `bt-verdict ${classeVerdict(v)}` }, `${v} : ${n}`))),
    ...SECTIONS.filter((k) => res.sections?.[k]).map((k) => section(res.sections[k])),
    propositions(res),
    el('section', { class: 'bt-section' }, titre('Non testables', 'faute d’historique gratuit'),
      el('ul', { class: 'chef-texte' }, (res.non_testables ?? []).map((x) => el('li', {}, el('strong', {}, x.signal), ` (${x.agent}) : ${x.raison}.`)))),
    el('p', { class: 'chef-petit' }, 'Limites : biais du survivant (univers actuel), séries macro révisées, approximations (valorisation des pays par le rendement du dividende, courbe des matières par le portage, paliers de risque par le VIX). Un IC de 0,02 à 0,05 est courant pour un signal utile.'),
  ];
}
