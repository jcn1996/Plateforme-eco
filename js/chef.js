/* ==========================================================================
   Chef d'orchestre (data/chef.json, data/chef/briefing-AAAA-MM-JJ.json, data/chef/suivi.json)
   Une seule liste d'investissement (chef.json → liste), tirée du dernier recalibrage validé du backtest, la même
   que celle du portefeuille démo, révisée une fois par mois :
   - panneau « Synthèse » : palier de risque, cycle, top 3 de la liste, alertes du jour, briefing ;
   - écran « Où investir » : la liste (entreprises, matières premières, paris pays ; combinaison, résultat au
     backtest, date d'entrée, ce qui la ferait sortir), les entrées et sorties du mois, et le contexte (notes du
     chef d'orchestre, non prédictives d'après le backtest, sans verdict) ;
   - écran « Fiabilité du chef d'orchestre » (suivi de performance des anciens verdicts) ;
   - filtre du globe « Note de contexte ».
   ========================================================================== */

import { el, nombre, classeNote } from './outils.js';

const FICHIER = 'data/chef.json';
const MENTION = 'Avis indicatif généré automatiquement, sans prise en compte d’un profil ou d’une situation personnelle.';
export const ONGLETS_INVESTIR = { liste: 'Liste d’investissement', mouvements: 'Entrées et sorties du mois', contexte: 'Contexte (notes)' };
export const CATEGORIES_LISTE = { entreprises: 'Entreprises', matieres: 'Matières premières', pays: 'Paris pays' };
const NIVEAUX_CONVICTION = { forte: 'retenue par 3 combinaisons', moyenne: 'retenue par 2 combinaisons', faible: 'retenue par 1 combinaison' };
/** Mention des notes et verdicts pays : ils restent affichés, mais le backtest les juge non prédictifs. */
export const MENTION_PAYS = 'contexte économique, non prédictif d’après le backtest';
const SIGNAUX = { mscore: 'M-score', goodwill_actif: 'goodwill / actif', fcf_yield: 'rendement du FCF', conversion_cash: 'conversion en cash',
  niveau: 'niveau historique', positionnement: 'positionnement CFTC' };

/** Paris pays du chef d'orchestre : pays en tendance saine (candidats) et pays détenus passés en excès (« à revendre »). */
export function lignesParisPays(chef) {
  const pp = chef?.selections?.paris_pays ?? {};
  return { candidats: pp.candidats ?? [], aRevendre: pp.a_revendre ?? [], detenus: pp.detenus ?? [], regle: pp.regle };
}

/** Pays présentés sans classement (ordre alphabétique) : la note pays n'est pas prédictive. */
export function paysSansClassement(lignes) {
  return [...(lignes ?? [])].sort((a, b) => String(a.nom).localeCompare(String(b.nom), 'fr'));
}
const TYPES = { pays: 'Actions · pays', secteurs: 'Secteur', matieres: 'Matière première', or: 'Or · valeur refuge', obligations: 'Obligations', liquidites: 'Liquidités', entreprises: 'Entreprise' };
const AGENTS = {
  pays: 'Agent pays', macro: 'Agent macro', entreprises: 'Agent entreprises', geopolitique: 'Agent géopolitique', risque: 'Agent risque',
  matieres_premieres: 'Matières premières', inities: 'Agent initiés', chef: 'Chef d’orchestre', backtest: 'Backtest',
};

/** Charge data/chef.json ; null si absent (l'appli continue). */
export async function chargerChef() {
  try {
    const r = await fetch(FICHIER, { cache: 'no-cache' });
    if (!r.ok) return null;
    const json = await r.json();
    return json?.donnees ? { meta: json.meta ?? {}, ...json.donnees } : null;
  } catch {
    return null;
  }
}

async function chargerJson(chemin) {
  try {
    const r = await fetch(chemin, { cache: 'no-cache' });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ outils */

const dateFr = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : 'n. d.');

/** Couleur d'un score selon les seuils de verdict du chef d'orchestre (≥ 58 : renforcer ; ≥ 43 : neutre). */
const classeScore = (s) => `note--${s >= 58 ? 'attractif' : s >= 43 ? 'neutre' : 'defavorable'}`;

function badgeScore(score) {
  if (score == null) return el('span', { class: 'chef-score' }, 'n. d.');
  return el('span', { class: `chef-score ${classeScore(score)}` }, el('strong', { class: 'mono' }, nombre(score)), '/100');
}
const pastilleConviction = (c) => el('span', { class: `chef-conviction chef-conviction--${c}`, title: NIVEAUX_CONVICTION[c] ?? '' }, `conviction ${c}`);
const mention = () => el('p', { class: 'chef-mention' }, MENTION);

/** Toutes les opportunités, à plat. */
function toutes(chef) {
  if (!chef) return [];
  return [...(chef.pays ?? []), ...(chef.secteurs ?? []), ...(chef.matieres ?? []), ...(chef.or ? [chef.or] : []), ...(chef.obligations ?? []), ...(chef.liquidites ?? []), ...(chef.entreprises ?? [])];
}

/* ------------------------------------------------------------------ globe */

export const METRIQUE_ATTRACTIVITE = { cle: 'attractivite', libelle: 'Note de contexte (chef d’orchestre)', court: 'Note (contexte)', source: 'chef' };

/** Filtre du globe « Note de contexte » : score du chef d'orchestre (non prédictif d'après le backtest), sans verdict. */
export function lireAttractivite(chef, code) {
  const l = chef?.pays?.find((p) => p.cle === code);
  if (!l || l.score == null) return null;
  return { valeur: l.score, note: l.score, niveau: l.score >= 58 ? 'attractif' : l.score >= 43 ? 'neutre' : 'defavorable', texte: nombre(l.score), unite: '/100' };
}

/* ------------------------------------------------------------------ panneau « Synthèse » */

const NOTE_NIVEAU = { attractif: 80, neutre: 57, defavorable: 30 };

/**
 * Panneau « Synthèse » repliable en bas du globe. Même interface que l'ancien bandeau des alertes
 * (afficher(alertesAgents, mesAlertes, alertesQualite), replier()), plus definirChef(chef).
 */
export function initialiserSynthese({ bouton, liste, compte, apercu, titre }, paysParCode, ouvrir) {
  let chef = null;
  let briefing; // undefined = pas chargé ; null = indisponible
  let briefingOuvert = false;
  let derniers = [[], [], []];
  const replier = () => {
    bouton.setAttribute('aria-expanded', 'false');
    liste.hidden = true;
    apercu.hidden = false;
    document.body.classList.remove('alertes-ouvertes');
  };
  bouton.addEventListener('click', () => {
    const ouvert = bouton.getAttribute('aria-expanded') === 'true';
    bouton.setAttribute('aria-expanded', String(!ouvert));
    liste.hidden = ouvert;
    apercu.hidden = !ouvert;
    document.body.classList.toggle('alertes-ouvertes', !ouvert);
  });
  const aller = (route) => { replier(); ouvrir(route); };

  function ligneAlerte(a) {
    const prefixe = a.qualite ? el('span', { class: 'badge-qualite' }, 'Qualité des données')
      : a.perso ? el('span', { class: 'badge-mon-alerte' }, 'Mon alerte') : el('span', {}, AGENTS[a.agent] ?? a.agent);
    const classe = `alerte ${classeNote(NOTE_NIVEAU[a.niveau] ?? 57)}${a.perso ? ' alerte--perso' : ''}${a.qualite ? ' alerte--qualite' : ''}`;
    // Alerte avec lien externe (ex. « Recalibrage à valider » → pull request) : un vrai lien, ouvert dans un nouvel onglet
    return el('li', {}, el(a.lien ? 'a' : 'button', a.lien ? { class: classe, href: a.lien, target: '_blank', rel: 'noopener' } : {
      class: classe, type: 'button', onclick: () => aller(a.route ?? (a.pays ? { type: 'pays', id: a.pays } : { type: 'investir' })),
    },
    el('span', { class: 'alerte-heure mono' }, a.heure ?? ''),
    el('span', { class: 'alerte-entete' }, prefixe, a.pays && !a.perso ? ['·', paysParCode.get(a.pays)?.nom ?? a.pays] : null),
    el('span', { class: 'alerte-titre' }, a.titre),
    a.texte ? el('span', { class: 'alerte-texte' }, a.texte) : null));
  }

  function blocBriefing() {
    if (!briefingOuvert) return null;
    if (briefing === undefined) return el('li', { class: 'synthese-briefing' }, 'Chargement du briefing…');
    if (!briefing) return el('li', { class: 'synthese-briefing' }, 'Briefing indisponible (pas encore d’analyse complète aujourd’hui).');
    return el('li', { class: 'synthese-briefing' }, briefingComplet(briefing, aller));
  }

  function rendre() {
    const [alertesAgents, mesAlertes, qualite] = derniers;
    const toutesAlertes = [...qualite, ...mesAlertes, ...alertesAgents];
    compte.textContent = String(toutesAlertes.length);
    const top = chef?.synthese?.top3 ?? [];
    const regime = chef?.regime;
    titre.textContent = chef ? 'Synthèse' : 'Alertes du jour';
    apercu.replaceChildren(...(chef ? [
      regime?.palier ? el('span', { class: `synthese-palier risque-palier--${(regime.palier ?? 'inconnu').toLowerCase()}` }, regime.palier) : null,
      top.length ? `Liste : ${top.map((t) => t.nom).join(' · ')}` : 'Liste d’investissement vide',
    ] : [toutesAlertes[0] ? `${toutesAlertes[0].heure ?? ''} · ${toutesAlertes[0].titre}` : 'Aucune alerte notable']).filter(Boolean));
    const blocs = [];
    if (chef) {
      blocs.push(el('li', { class: 'synthese-regime' },
        el('div', {}, el('span', { class: 'synthese-etiquette' }, 'Risque'), ' ',
          el('span', { class: `synthese-palier risque-palier--${(regime?.palier ?? 'inconnu').toLowerCase()}` }, regime?.palier ?? 'n. d.'),
          regime?.score_risque != null ? el('small', {}, ` stress ${nombre(regime.score_risque)}/100`) : null),
        el('div', {}, el('span', { class: 'synthese-etiquette' }, 'Cycle'), ` ${regime?.phase_monde ?? 'n. d.'}`)));
      blocs.push(el('li', { class: 'synthese-top' },
        el('div', { class: 'synthese-etiquette' }, 'Où investir · top 3 de la liste'),
        top.length ? el('ol', {}, top.map((t) => el('li', {}, el('button', { class: 'lien', type: 'button', onclick: () => aller({ type: 'investir', id: `o-${t.id}` }) },
          t.nom), ' ', pastilleConviction(t.conviction), el('small', { class: 'chef-petit' }, ` ${CATEGORIES_LISTE[t.categorie] ?? ''} · ${(t.combinaisons_libelles ?? []).join(' ; ')}`))))
          : el('p', {}, 'Aucune ligne dans la liste d’investissement.')));
      blocs.push(el('li', { class: 'alertes-outils synthese-boutons' },
        el('button', { class: 'bouton bouton--plein', type: 'button', onclick: () => basculerBriefing() }, briefingOuvert ? 'Masquer le briefing' : '📋 Briefing complet'),
        el('button', { class: 'bouton bouton--plein', type: 'button', onclick: () => aller({ type: 'investir' }) }, '🧭 Où investir'),
        el('button', { class: 'bouton bouton--plein', type: 'button', onclick: () => aller({ type: 'mes-alertes' }) }, '🔔 Mes alertes')));
      blocs.push(blocBriefing());
    } else {
      blocs.push(el('li', { class: 'alertes-outils' },
        el('button', { class: 'bouton bouton--plein', type: 'button', onclick: () => aller({ type: 'mes-alertes' }) }, '🔔 Gérer mes alertes')));
    }
    blocs.push(el('li', { class: 'synthese-etiquette synthese-sous-titre' }, 'Alertes du jour'));
    if (toutesAlertes.length) blocs.push(...toutesAlertes.map(ligneAlerte));
    else blocs.push(el('li', { class: 'synthese-vide' }, 'Aucune alerte notable.'));
    if (chef) blocs.push(el('li', {}, mention()));
    liste.replaceChildren(...blocs.filter(Boolean));
  }

  function basculerBriefing() {
    briefingOuvert = !briefingOuvert;
    if (briefingOuvert && briefing === undefined && chef?.synthese?.briefing) {
      chargerJson(chef.synthese.briefing).then((j) => { briefing = j?.donnees ?? null; rendre(); });
    } else if (briefingOuvert && !chef?.synthese?.briefing) briefing = null;
    rendre();
  }

  return {
    replier,
    afficher(alertesAgents, mesAlertes = [], alertesQualite = []) {
      // L'ordre des alertes des agents est celui du chef d'orchestre (rang) ; à défaut, les plus récentes d'abord
      const agents = [...alertesAgents].sort((a, b) => (a.rang ?? 99) - (b.rang ?? 99) || String(b.date ?? b.heure).localeCompare(String(a.date ?? a.heure)));
      derniers = [agents, mesAlertes, alertesQualite];
      rendre();
    },
    definirChef(c) { chef = c; rendre(); },
    /** Déplie le panneau et ouvre le briefing complet (entrée « Briefing » du Menu). */
    ouvrirBriefing() {
      bouton.setAttribute('aria-expanded', 'true');
      liste.hidden = false;
      apercu.hidden = true;
      document.body.classList.add('alertes-ouvertes');
      if (!briefingOuvert) basculerBriefing();
      liste.querySelector('.synthese-briefing')?.scrollIntoView({ block: 'start' });
    },
  };
}

/** Contenu du briefing complet (dans le panneau « Synthèse »). */
function briefingComplet(b, aller) {
  const section = (t, ...enfants) => el('section', { class: 'chef-briefing-section' }, el('h4', {}, t), ...enfants);
  const liste = (xs) => el('ul', {}, xs.map((x) => el('li', {}, x)));
  return el('div', { class: 'chef-briefing' },
    el('p', { class: 'chef-briefing-tete' }, `Briefing du ${dateFr(b.date)} · rédaction : ${b.mode === 'gemini' ? 'Gemini (affirmations vérifiées contre les données)' : 'règles'}`),
    section('L’essentiel', liste((b.essentiel ?? []).map((x) => x.texte))),
    section('Où investir : la liste', b.liste?.lignes?.length ? el('ol', {}, b.liste.lignes.map((x) => {
      const c = contenuFiche(x);
      return el('li', {},
        el('button', { class: 'lien', type: 'button', onclick: () => aller({ type: 'investir', id: `o-${x.id}` }) }, x.nom), ' ', pastilleConviction(x.conviction),
        el('div', { class: 'chef-petit' }, c.verdict),
        el('div', { class: 'chef-petit' }, `+ ${c.pour[0] ?? 'donnée manquante'}`),
        el('div', { class: 'chef-petit' }, `− ${c.contre[0] ?? 'donnée manquante'}`),
        el('div', { class: 'chef-petit' }, `Momentum ${c.momentum.mot} : ${c.momentum.texte}${c.momentum.contradiction ? ' — contredit le dossier' : ''}`));
    })) : el('p', {}, 'Liste vide.')),
    section('Entrées et sorties du mois', liste((b.mouvements ?? []).length ? b.mouvements.map((m) => `${dateFr(m.date)} · ${m.texte}`) : ['Aucune entrée ni sortie ce mois-ci.'])),
    section('Points de vigilance', liste(b.vigilance?.length ? b.vigilance.map((v) => v.texte) : ['Aucun.'])),
    ...['central', 'alternatif'].map((k) => {
      const s = b.scenarios?.[k];
      return s ? section(`Scénario ${k} : ${s.titre}`, el('p', {}, s.texte), el('p', { class: 'chef-petit' }, 'Déclencheurs :'), liste(s.declencheurs ?? [])) : null;
    }),
    section('Agenda des 7 prochains jours', liste(b.agenda?.length ? b.agenda.map((x) => `${x.jour} : ${x.libelle}${x.indicative ? ' (date indicative)' : ''}`) : ['Rien de prévu dans les sources suivies.'])),
    section('Ce qui pourrait me donner tort', liste(b.donner_tort ?? [])),
    b.affirmations_supprimees?.length ? el('p', { class: 'chef-petit' }, `${b.affirmations_supprimees.length} affirmation(s) de Gemini supprimée(s) faute de source.`) : null,
  );
}

/* ------------------------------------------------------------------ écran « Où investir » : la liste unique */

function barreOnglets(actif, nav) {
  return el('div', { class: 'ini-onglets', role: 'tablist' }, Object.entries(ONGLETS_INVESTIR).map(([cle, libelle]) =>
    el('button', { class: `ini-onglet${cle === actif ? ' est-actif' : ''}`, type: 'button', role: 'tab', 'aria-selected': String(cle === actif),
      onclick: () => nav.ouvrir({ type: 'investir', id: cle }) }, libelle)));
}

/** Texte d'un argument pour / contre : celui de sa famille de signaux. */
const texteArgument = (l, a) => l.familles?.[a.cle]?.texte ?? a.texte ?? '';

function signeFr(x, d = 1) {
  return x == null ? 'n. d.' : `${x > 0 ? '+' : x < 0 ? '−' : ''}${nombre(Math.abs(x), d)}`;
}

const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
/** « 2026-12 » → « décembre 2026 ». */
export const moisFr = (m) => (m ? `${MOIS[Number(m.slice(5, 7)) - 1] ?? m.slice(5, 7)} ${m.slice(0, 4)}` : 'n. d.');

function titre(t, sous) {
  return el('h3', { class: 'section-titre' }, t, sous ? el('small', {}, ` ${sous}`) : null);
}

/** Lignes de la liste unique regroupées par catégorie, dans l'ordre : entreprises, matières premières, paris pays. */
export function lignesListe(chef) {
  const ls = chef?.liste?.lignes ?? [];
  return Object.keys(CATEGORIES_LISTE).map((k) => [k, CATEGORIES_LISTE[k], ls.filter((l) => l.categorie === k)]).filter(([, , xs]) => xs.length);
}

/** Résultat au backtest d'une combinaison : écart annuel contre l'indice et part des actifs gagnants (hors échantillon). */
export function texteBacktest(b) {
  const ecart = b?.ecart_indice_pct != null ? `${signeFr(b.ecart_indice_pct, 1)} pt/an contre l’indice` : 'écart contre l’indice n. d.';
  const gagnants = b?.gagnants_pct != null ? `${nombre(b.gagnants_pct, 0)} % des actifs retenus ont battu l’indice` : 'part des gagnants n. d.';
  return `${b?.combinaison ?? 'Combinaison'} : ${ecart}, ${gagnants} (hors échantillon)`;
}

const MOTS_MOMENTUM = { favorable: 'favorable', neutre: 'neutre', 'défavorable': 'défavorable', inconnu: 'inconnu' };

/**
 * Contenu lisible d'une ligne de la liste : la fiche en 5 blocs construite par le chef d'orchestre (agents/chef/fiches.py) ;
 * à défaut (ancienne sortie), un repli tiré des champs de la ligne, sans rien inventer.
 */
export function contenuFiche(l) {
  const f = l?.fiche;
  if (f) {
    return {
      verdict: f.entete?.verdict ?? '', poids: f.entete?.poids_texte ?? 'poids dans le portefeuille démo inconnu',
      conviction: f.entete?.conviction_texte ?? l.conviction, pour: f.pour ?? [], contre: f.contre ?? [],
      momentum: { mot: MOTS_MOMENTUM[f.momentum?.mot] ?? 'inconnu', texte: f.momentum?.texte ?? 'performances : donnée manquante', contradiction: f.momentum?.contradiction ?? null },
      sortie: f.sortie ?? l.sortie_si ?? 'donnée manquante', base: f.base_statistique ?? {}, manque: f.manque ?? null,
    };
  }
  return {
    verdict: `Retenue par ${(l?.combinaisons_libelles ?? []).join(' ; ') || 'le backtest'}.`, poids: 'poids dans le portefeuille démo inconnu',
    conviction: l?.conviction, pour: ['Fiche détaillée pas encore calculée (prochaine analyse complète).'], contre: ['Donnée manquante.'],
    momentum: { mot: 'inconnu', texte: 'performances : donnée manquante', contradiction: null },
    sortie: l?.sortie_si ?? 'donnée manquante', base: { combinaisons: l?.backtest ?? [], date_entree: l?.date_entree, detail: l?.detail }, manque: 'fiche absente',
  };
}

function blocFiche(l, nav, detail = false) {
  const c = contenuFiche(l);
  const bloc = (titreBloc, ...enfants) => el('section', { class: 'chef-fiche-bloc' }, el('h4', {}, titreBloc), ...enfants);
  return el('article', { class: `chef-fiche chef-liste--${l.categorie}` },
    el('header', { class: 'chef-fiche-tete' },
      el('div', { class: 'chef-ligne-tete' }, el('strong', { class: 'chef-ligne-nom' }, l.nom), l.symbole ? el('small', { class: 'mono' }, ` ${l.symbole}`) : null,
        pastilleConviction(l.conviction)),
      el('div', { class: 'chef-petit' }, `${c.conviction ?? ''} · ${c.poids}`),
      el('p', { class: 'chef-fiche-verdict' }, c.verdict)),
    l.alerte_sortie ? el('p', { class: 'chef-petit chef-attente' }, `⚠ ${l.alerte_sortie}`) : null,
    bloc('Pourquoi investir', el('ul', { class: 'chef-texte chef-pour' }, c.pour.map((x) => el('li', {}, x)))),
    bloc('Pourquoi pas', el('ul', { class: 'chef-texte chef-contre' }, c.contre.map((x) => el('li', {}, x)))),
    bloc('Momentum', el('p', {}, el('span', { class: `chef-momentum chef-momentum--${c.momentum.mot === 'défavorable' ? 'defavorable' : c.momentum.mot}` }, c.momentum.mot), ` ${c.momentum.texte}`),
      c.momentum.contradiction ? el('p', { class: 'chef-petit chef-attente' }, c.momentum.contradiction) : null),
    bloc('Ce qui ferait sortir', el('p', {}, c.sortie)),
    el('details', { class: 'chef-fiche-base' }, el('summary', {}, 'Base statistique (backtest)'),
      el('ul', { class: 'chef-texte chef-backtest' }, (c.base.combinaisons ?? []).map((b) => el('li', {}, texteBacktest(b)))),
      el('p', { class: 'chef-petit' }, `Dans la liste depuis le ${dateFr(c.base.date_entree ?? l.date_entree)}${c.base.detail ? ` · ${c.base.detail}` : ''}`),
      c.manque ? el('p', { class: 'chef-petit' }, `Donnée manquante : ${c.manque}.`) : null),
    detail ? null : el('button', { class: 'bouton bouton--petit', type: 'button', onclick: () => nav.ouvrir({ type: 'investir', id: `o-${l.id}` }) }, 'Ouvrir la fiche'));
}

function ligneListe(l, nav) {
  return el('li', {}, blocFiche(l, nav));
}

function ongletListe(chef, nav) {
  const li = chef.liste;
  if (!li) return [el('p', { class: 'sante-ligne' }, 'Liste pas encore calculée (prochaine analyse complète).')];
  const groupes = lignesListe(chef);
  return [
    titre('Liste d’investissement', `${li.nombre ?? 0} ligne${(li.nombre ?? 0) > 1 ? 's' : ''} sur ${li.max_lignes ?? 15} au plus · révisée le ${dateFr(li.revise_le)} · prochaine révision : ${moisFr(li.prochaine_revision)}`),
    el('p', { class: 'chef-petit' }, li.regle ?? ''),
    ...(groupes.length ? groupes.flatMap(([, libelle, xs]) => [titre(libelle, `${xs.length}`), el('ul', { class: 'chef-liste' }, xs.map((l) => ligneListe(l, nav)))])
      : [el('p', { class: 'sante-ligne' }, 'Aucune ligne retenue par les combinaisons du backtest.')]),
    el('p', { class: 'chef-petit' }, `Conviction : ${Object.entries(NIVEAUX_CONVICTION).map(([k, v]) => `${k} = ${v}`).join(' ; ')}. Elle repose sur le backtest, pas sur la note.`),
  ];
}

function ongletMouvements(chef) {
  const ms = chef.liste?.mouvements ?? [];
  return [titre('Entrées et sorties du mois', moisFr(chef.liste?.mois)),
    ms.length ? el('ul', { class: 'chef-texte chef-mouvements' }, ms.map((m) => el('li', { class: `chef-mouvement--${m.sens === 'sortie' ? 'sortie' : 'entree'}` }, `${dateFr(m.date)} · ${m.texte}`)))
      : el('p', { class: 'chef-petit' }, 'Aucune entrée ni sortie ce mois-ci.'),
    el('p', { class: 'chef-petit' }, 'Aucune entrée en cours de mois : la liste n’est révisée qu’au rééquilibrage mensuel. Entre deux, seules sorties : excès ou tendance cassée pour un pari pays, sortie de la combinaison confirmée 5 jours de suite pour les autres.')];
}

/* ------------------------------------------------------------------ contexte : notes du chef d'orchestre, sans verdict */

const CONTEXTES = { pays: 'Pays', secteurs: 'Secteurs', matieres: 'Matières premières et or', obligations: 'Obligations et liquidités', entreprises: 'Entreprises' };
let contexteActif = 'pays';

function lignesContexte(chef, k) {
  if (k === 'matieres') return [...(chef.or ? [chef.or] : []), ...(chef.matieres ?? [])];
  if (k === 'obligations') return [...(chef.obligations ?? []), ...(chef.liquidites ?? [])];
  if (k === 'pays') return paysSansClassement(chef.pays);
  return chef[k] ?? [];
}

function ligneContexte(l, nav) {
  return el('li', {}, el('button', { class: 'chef-ligne chef-ligne--compacte', type: 'button', onclick: () => nav.ouvrir({ type: 'investir', id: `o-${l.id}` }) },
    el('div', { class: 'chef-ligne-tete' }, el('strong', { class: 'chef-ligne-nom' }, l.nom), badgeScore(l.score), el('small', { class: 'chef-petit' }, ' contexte'))));
}

/** Puces de filtre ; `choisir` redessine le contenu sans quitter l'onglet. */
function puces(options, actif, choisir) {
  return el('div', { class: 'ini-onglets chef-filtre', role: 'group' }, options.map(([cle, libelle, n]) => el('button', {
    class: `ini-onglet${cle === actif ? ' est-actif' : ''}`, type: 'button', 'aria-pressed': String(cle === actif), onclick: () => choisir(cle),
  }, libelle, n != null ? el('small', {}, ` ${n}`) : null)));
}

function ongletContexte(chef, nav) {
  const conteneur = el('div', {});
  const rendre = () => {
    const xs = lignesContexte(chef, contexteActif);
    conteneur.replaceChildren(
      puces(Object.entries(CONTEXTES).map(([k, v]) => [k, v, lignesContexte(chef, k).length]), contexteActif, (k) => { contexteActif = k; rendre(); }),
      xs.length ? el('ul', { class: 'chef-liste' }, xs.map((l) => ligneContexte(l, nav))) : el('p', { class: 'chef-petit' }, 'Aucune donnée.'));
  };
  rendre();
  return [titre('Contexte', `notes du chef d’orchestre : ${MENTION_PAYS}`),
    el('p', { class: 'chef-avertissement' }, `Ces notes ne servent pas à décider : le backtest les juge non prédictives. Elles ne portent plus de verdict « Renforcer » ou « Alléger ». Seule la liste d’investissement est investie.`),
    conteneur];
}

export function ecranInvestir(chef, nav, id) {
  const entete = el('header', { class: 'chef-entete' },
    el('div', { class: 'fiche-surtitre' }, 'Chef d’orchestre · liste issue du backtest'),
    el('h2', { class: 'fiche-titre' }, 'Où investir'),
    chef ? el('p', { class: 'chef-regime' },
      el('span', { class: `synthese-palier risque-palier--${(chef.regime?.palier ?? 'inconnu').toLowerCase()}` }, `Risque : ${chef.regime?.palier ?? 'n. d.'}`), ' ',
      `Cycle mondial : ${chef.regime?.phase_monde ?? 'n. d.'} · analyse du ${dateFr(chef.date)}`) : null);
  if (!chef) return [entete, el('p', { class: 'sante-ligne' }, 'Données du chef d’orchestre indisponibles (data/chef.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  if (id?.startsWith('o-')) {
    const cle = id.slice(2);
    const l = (chef.liste?.lignes ?? []).find((x) => x.id === cle);
    if (l) return ficheListe(l, chef, nav);
    const o = toutes(chef).find((x) => x.id === cle);
    if (o) return ficheOpportunite(o, chef, nav);
  }
  const onglet = ONGLETS_INVESTIR[id] ? id : 'liste';
  const corps = onglet === 'mouvements' ? ongletMouvements(chef) : onglet === 'contexte' ? ongletContexte(chef, nav) : ongletListe(chef, nav);
  return [
    entete,
    barreOnglets(onglet, nav),
    ...corps,
    blocEntrees(chef),
    mention(),
    el('p', { class: 'fraicheur' }, `Mis à jour le ${new Date(chef.meta?.genere_le ?? chef.maj).toLocaleString('fr-FR')} · Chef d’orchestre (${chef.mode === 'leger' ? 'mise à jour légère' : 'analyse complète'})`),
  ];
}

function blocEntrees(chef) {
  return el('details', { class: 'chef-entrees' },
    el('summary', {}, 'Données utilisées (fraîcheur et santé des agents)'),
    el('ul', {}, (chef.entrees ?? []).map((e) => el('li', { class: e.etat !== 'à jour' || e.degrade ? 'chef-entree--alerte' : '' },
      `${e.libelle} : ${e.etat}${e.age_h != null ? ` (${nombre(e.age_h, 0)} h)` : ''}${e.degrade ? ' · agent dégradé' : ''} · poids ${nombre((e.coef ?? 0) * 100, 0)} %`))));
}

function blocSuiviTendance(st) {
  const inv = st.invalidation ?? {};
  return el('section', {}, titre('Suivi de tendance', st.forte ? (st.exces?.length ? 'tendance forte, mais en excès' : 'tendance forte et saine') : st.positive ? 'tendance positive' : 'pas de tendance positive'),
    el('ul', { class: 'chef-texte' },
      el('li', {}, `Performance sur 12 mois hors dernier mois : ${signeFr(st.perf_12_1, 1)} %${st.perf_1m != null ? ` ; sur 1 mois : ${signeFr(st.perf_1m, 1)} %` : ''}`),
      el('li', {}, `Cours ${nombre(st.cours, 2)} le ${dateFr(st.date)}, ${st.au_dessus_mm200 ? 'au-dessus' : 'en dessous'} de la moyenne 200 jours (${nombre(st.mm200, 2)}${inv.ecart_mm200_pct != null ? `, écart ${signeFr(inv.ecart_mm200_pct, 1)} %` : ''})`),
      st.force_relative != null ? el('li', {}, `Force relative : ${nombre(st.force_relative, 0)}e percentile (${st.rang}e sur ${st.sur})`) : null,
      ...(st.exces ?? []).map((x) => el('li', { class: 'chef-objection--serieuse' }, `Excès : ${x}`))));
}

/* ------------------------------------------------------------------ fiches */

function lienSource(l, nav) {
  const type = l.type ?? l.categorie;
  if (type === 'pays') return el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrirPays(l.cle) }, 'Voir la fiche pays');
  if (type === 'matieres' || type === 'or') return el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'matieres', id: l.cle }) }, 'Voir la fiche matière première');
  const t = l.ticker ?? l.cle;
  if (type === 'entreprises' && nav.entrepriseExiste?.(t)) return el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrirEntreprise(t) }, 'Voir la fiche entreprise');
  if (type === 'obligations' || type === 'liquidites') return el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'macro' }) }, 'Voir la vue macro');
  return null;
}

/** Ligne de la liste : pourquoi elle est retenue, son résultat au backtest, depuis quand, ce qui la ferait sortir. */
function ficheListe(l, chef, nav) {
  const ctx = toutes(chef).find((x) => x.id === l.id || (l.categorie === 'entreprises' && x.type === 'entreprises' && (x.cle === l.ticker || x.symbole === l.symbole)));
  return [
    el('header', { class: 'chef-entete' },
      el('div', { class: 'fiche-surtitre' }, `Liste d’investissement · ${CATEGORIES_LISTE[l.categorie] ?? l.categorie}${l.symbole ? ` · ${l.symbole}` : ''}`),
      el('h2', { class: 'fiche-titre' }, l.nom),
      el('div', { class: 'chef-ligne-tete' }, pastilleConviction(l.conviction), el('small', { class: 'chef-petit' }, ` ${NIVEAUX_CONVICTION[l.conviction] ?? ''}`)),
      el('div', { class: 'chef-actions' }, lienSource(l, nav), el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'investir' }) }, '‹ Retour à la liste'))),
    blocFiche(l, nav, true),
    ctx?.score != null ? el('section', {}, titre('Note du chef d’orchestre', MENTION_PAYS),
      el('p', {}, badgeScore(ctx.score), ' ', el('button', { class: 'lien', type: 'button', onclick: () => nav.ouvrir({ type: 'investir', id: `o-${ctx.id}` }) }, 'détail des signaux'))) : null,
    mention(),
  ];
}

/** Fiche de contexte : note et familles de signaux, sans verdict (non prédictif d'après le backtest). */
function ficheOpportunite(l, chef, nav) {
  const familles = Object.entries(l.familles ?? {}).sort((a, b) => (l.poids_effectifs?.[b[0]] ?? 0) - (l.poids_effectifs?.[a[0]] ?? 0));
  const dansListe = (chef.liste?.lignes ?? []).find((x) => x.id === l.id || (l.type === 'entreprises' && x.ticker === l.cle));
  return [
    el('header', { class: 'chef-entete' },
      el('div', { class: 'fiche-surtitre' }, `${TYPES[l.type] ?? l.type} · contexte`),
      el('h2', { class: 'fiche-titre' }, l.nom),
      el('div', { class: 'chef-ligne-tete' }, badgeScore(l.score), el('small', { class: 'chef-petit' }, ` Note : ${MENTION_PAYS}`)),
      el('div', { class: 'chef-actions' }, lienSource(l, nav), el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'investir', id: 'contexte' }) }, '‹ Contexte'))),
    el('p', { class: 'chef-avertissement' }, dansListe ? `Dans la liste d’investissement (${NIVEAUX_CONVICTION[dansListe.conviction] ?? ''}) : c’est la liste, pas cette note, qui décide.`
      : 'Hors de la liste d’investissement. La note ci-dessous est un contexte, non prédictif d’après le backtest.'),
    l.suivi_tendance ? blocSuiviTendance(l.suivi_tendance) : null,
    el('section', {}, titre('Familles de signaux', 'score /100 · poids effectif dans la note'),
      el('ul', { class: 'chef-familles' }, familles.map(([cle, f]) => el('li', {},
        el('div', { class: 'chef-famille-tete' }, el('strong', {}, f.libelle), badgeScore(f.note),
          el('small', {}, `poids ${nombre(l.poids_effectifs?.[cle] ?? 0, 0)} %${f.percentile_classe != null ? ` · percentile ${nombre(f.percentile_classe, 0)} dans la classe` : ''}`)),
        el('div', { class: 'chef-barre' }, el('span', { class: classeScore(f.note), style: { width: `${Math.max(2, f.note)}%` } })),
        el('div', { class: 'chef-petit' }, f.texte),
        el('div', { class: 'chef-source' }, `Source : ${f.source}`)))),
      l.familles_manquantes?.length ? el('p', { class: 'chef-petit' }, `Données manquantes (non estimées) : ${l.familles_manquantes.join(', ')}.`) : null),
    el('section', {}, titre('Arguments pour'), el('ul', { class: 'chef-texte chef-pour' }, (l.pour ?? []).length ? l.pour.map((a) => el('li', {}, `${a.famille} (${nombre(a.note)}/100) : ${texteArgument(l, a)}`)) : el('li', {}, 'Aucun argument nettement favorable.'))),
    el('section', {}, titre('Arguments contre'), el('ul', { class: 'chef-texte chef-contre' }, (l.contre ?? []).length ? l.contre.map((a) => el('li', {}, `${a.famille} (${nombre(a.note)}/100) : ${texteArgument(l, a)}`)) : el('li', {}, 'Aucun argument nettement défavorable.'))),
    el('section', {}, titre('Objections du contradicteur', 'agent risque, 7 derniers jours'),
      l.objections?.length ? el('ul', { class: 'chef-texte' }, l.objections.map((o) => el('li', {}, `${dateFr(o.date)} · « ${o.ajustement} » — ${o.objection}`))) : el('p', { class: 'chef-petit' }, 'Aucune objection.')),
    mention(),
  ];
}

/* ------------------------------------------------------------------ fiabilité */

export async function chargerSuiviChef() {
  const j = await chargerJson('data/chef/suivi.json');
  return j ? { meta: j.meta ?? {}, donnees: j.donnees ?? [] } : null;
}

export function ecranFiabiliteChef(suivi, nav) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Chef d’orchestre · suivi de performance'),
    el('h2', { class: 'fiche-titre' }, 'Fiabilité du chef d’orchestre'),
    el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'investir' }) }, '‹ Où investir'));
  if (suivi === undefined) return [entete, el('p', { class: 'sante-ligne' }, 'Chargement…')];
  if (!suivi) return [entete, el('p', { class: 'sante-ligne' }, 'Aucun suivi encore (data/chef/suivi.json introuvable).')];
  const m = suivi.meta;
  const horizons = m.horizons_mois ?? [1, 3, 6, 12];
  const fia = m.fiabilite ?? {};
  const tableau = (bloc, libelleCle) => el('table', { class: 'chef-table' },
    el('thead', {}, el('tr', {}, el('th', {}, libelleCle), el('th', {}, 'Verdicts'), horizons.map((h) => el('th', {}, `${h} mois`)))),
    el('tbody', {}, Object.entries(bloc ?? {}).map(([cle, b]) => el('tr', {},
      el('td', {}, TYPES[cle] ?? cle), el('td', { class: 'mono' }, String(b.total)),
      horizons.map((h) => {
        const x = b[String(h)] ?? {};
        return el('td', { class: 'mono' }, x.n ? `${x.taux_pct} % (${x.n}) · ${x.relative_moyenne_pct > 0 ? '+' : ''}${nombre(x.relative_moyenne_pct, 1)} pt` : '—');
      })))));
  const mesurees = suivi.donnees.filter((h) => Object.values(h.suivi ?? {}).some((s) => s.relative_pct != null));
  return [
    entete,
    el('p', { class: 'chef-petit' }, `${m.nombre ?? suivi.donnees.length} verdicts enregistrés (premier verdict et chaque changement), ${mesurees.length} déjà mesurés. Performance à ${horizons.join(', ')} mois contre l’indice de la classe : ${Object.values(m.indices_noms ?? {}).join(' ; ')}.`),
    el('section', {}, titre('Calibration de la conviction', 'une conviction forte doit réussir plus souvent qu’une faible'),
      el('ul', { class: 'chef-texte' }, horizons.map((h) => {
        const c = fia.calibration?.[String(h)];
        if (!c) return null;
        if (c.statut === 'insuffisant') return el('li', {}, `${h} mois : pas encore mesurable. ${c.texte}`);
        const taux = ['forte', 'moyenne', 'faible'].map((k) => `${k} ${c.taux?.[k] ?? '—'}${c.taux?.[k] != null ? ' %' : ''} (${c.n?.[k] ?? 0})`).join(' · ');
        return el('li', { class: c.statut === 'à revoir' ? 'chef-entree--alerte' : '' }, `${h} mois : ${c.statut} — ${taux}. ${c.texte}`);
      }))),
    el('section', {}, titre('Par niveau de conviction', 'taux de réussite (nombre) · performance relative moyenne'), tableau(fia.par_conviction, 'Conviction')),
    el('section', {}, titre('Par verdict'), tableau(fia.par_verdict, 'Verdict')),
    el('section', {}, titre('Par type d’opportunité'), tableau(fia.par_type, 'Type')),
    el('section', {}, titre('Derniers verdicts enregistrés'),
      el('ul', { class: 'chef-texte' }, [...suivi.donnees].reverse().slice(0, 40).map((h) => el('li', {},
        `${dateFr(h.date)} · ${h.nom} : « ${h.verdict} », conviction ${h.conviction}, ${nombre(h.score)}/100${h.cours != null ? ` · cours ${nombre(h.cours, 2)}` : ''} (${h.symbole} contre ${h.indice})`,
        ...horizons.map((m2) => {
          const s = h.suivi?.[String(m2)];
          return s?.relative_pct != null ? el('span', { class: `chef-petit ${s.reussite ? 'chef-ok' : 'chef-ko'}` }, ` · ${m2} mois : ${s.relative_pct > 0 ? '+' : ''}${nombre(s.relative_pct, 1)} pt ${s.reussite ? '✓' : '✗'}`) : null;
        }))))),
    el('p', { class: 'chef-petit' }, 'Règles de réussite : « Renforcer » et « Renforcer fortement » si la performance relative est positive ; « Alléger » et « Éviter » si elle est négative ; « Neutre » si elle reste dans ± 5 points. Ces résultats alimenteront l’agent calibrateur.'),
    mention(),
  ];
}
