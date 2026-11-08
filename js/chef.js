/* ==========================================================================
   Chef d'orchestre (data/chef.json, data/chef/briefing-AAAA-MM-JJ.json, data/chef/suivi.json)
   - panneau « Synthèse » repliable en bas du globe (à la place du bandeau des alertes) :
     palier de risque, phase du cycle, top 3 « Où investir », alertes du jour ; toucher pour
     déplier, puis « Briefing complet » ;
   - écran « Où investir » à onglets : Pays, Matières premières, Obligations et liquidités,
     Entreprises, Allocation ; chaque ligne ouvre la fiche détaillée de l'opportunité ;
   - écran « Fiabilité du chef d'orchestre » (suivi de performance des verdicts) ;
   - filtre du globe « Attractivité » (score du chef d'orchestre).
   ========================================================================== */

import { el, nombre, classeNote } from './outils.js';

const FICHIER = 'data/chef.json';
const MENTION = 'Avis indicatif généré automatiquement, sans prise en compte d’un profil ou d’une situation personnelle.';
export const ONGLETS_INVESTIR = {
  panorama: 'Panorama', pays: 'Pays', secteurs: 'Secteurs', matieres: 'Matières premières', obligations: 'Obligations et liquidités', entreprises: 'Entreprises', allocation: 'Allocation',
};
const TYPES = { pays: 'Actions · pays', secteurs: 'Secteur', matieres: 'Matière première', or: 'Or · valeur refuge', obligations: 'Obligations', liquidites: 'Liquidités', entreprises: 'Entreprise' };
const AGENTS = {
  pays: 'Agent pays', macro: 'Agent macro', entreprises: 'Agent entreprises', geopolitique: 'Agent géopolitique', risque: 'Agent risque',
  matieres_premieres: 'Matières premières', inities: 'Agent initiés', chef: 'Chef d’orchestre',
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
const classeVerdict = (v) => ({
  'Renforcer fortement': 'verdict--fort', Renforcer: 'verdict--pos', Neutre: 'verdict--neutre', Alléger: 'verdict--neg', Éviter: 'verdict--tres-neg',
}[v] ?? 'verdict--neutre');
const niveauVerdict = (v) => ((v === 'Renforcer' || v === 'Renforcer fortement') ? 'attractif' : v === 'Neutre' ? 'neutre' : 'defavorable');

/** Couleur d'un score selon les seuils de verdict du chef d'orchestre (≥ 58 : renforcer ; ≥ 43 : neutre). */
const classeScore = (s) => `note--${s >= 58 ? 'attractif' : s >= 43 ? 'neutre' : 'defavorable'}`;

function badgeScore(score) {
  if (score == null) return el('span', { class: 'chef-score' }, 'n. d.');
  return el('span', { class: `chef-score ${classeScore(score)}` }, el('strong', { class: 'mono' }, nombre(score)), '/100');
}
const pastilleVerdict = (v) => el('span', { class: `chef-verdict ${classeVerdict(v)}` }, v);
const pastilleConviction = (c) => el('span', { class: `chef-conviction chef-conviction--${c}` }, `conviction ${c}`);
const fleche = (f) => el('span', { class: `chef-fleche chef-fleche--${f === '↑' ? 'haut' : f === '↓' ? 'bas' : 'stable'}`, title: 'Évolution du score depuis l’analyse complète précédente' }, f ?? '→');
const mention = () => el('p', { class: 'chef-mention' }, MENTION);

/** Toutes les opportunités, à plat. */
function toutes(chef) {
  if (!chef) return [];
  return [...(chef.pays ?? []), ...(chef.secteurs ?? []), ...(chef.matieres ?? []), ...(chef.or ? [chef.or] : []), ...(chef.obligations ?? []), ...(chef.liquidites ?? []), ...(chef.entreprises ?? [])];
}

/* ------------------------------------------------------------------ globe */

export const METRIQUE_ATTRACTIVITE = { cle: 'attractivite', libelle: 'Attractivité', court: 'Attractivité', source: 'chef' };

/** Filtre du globe « Attractivité » : score du chef d'orchestre, couleur selon le verdict. */
export function lireAttractivite(chef, code) {
  const l = chef?.pays?.find((p) => p.cle === code);
  if (!l || l.score == null) return null;
  return { valeur: l.score, note: l.score, niveau: niveauVerdict(l.verdict), texte: nombre(l.score), unite: '/100' };
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
    return el('li', {}, el('button', {
      class: `alerte ${classeNote(NOTE_NIVEAU[a.niveau] ?? 57)}${a.perso ? ' alerte--perso' : ''}${a.qualite ? ' alerte--qualite' : ''}`,
      type: 'button', onclick: () => aller(a.route ?? (a.pays ? { type: 'pays', id: a.pays } : { type: 'investir' })),
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
      top.length ? `Où investir : ${top.map((t) => t.nom).join(' · ')}` : 'Aucune opportunité à verdict positif',
    ] : [toutesAlertes[0] ? `${toutesAlertes[0].heure ?? ''} · ${toutesAlertes[0].titre}` : 'Aucune alerte notable']).filter(Boolean));
    const blocs = [];
    if (chef) {
      blocs.push(el('li', { class: 'synthese-regime' },
        el('div', {}, el('span', { class: 'synthese-etiquette' }, 'Risque'), ' ',
          el('span', { class: `synthese-palier risque-palier--${(regime?.palier ?? 'inconnu').toLowerCase()}` }, regime?.palier ?? 'n. d.'),
          regime?.score_risque != null ? el('small', {}, ` stress ${nombre(regime.score_risque)}/100`) : null),
        el('div', {}, el('span', { class: 'synthese-etiquette' }, 'Cycle'), ` ${regime?.phase_monde ?? 'n. d.'}`)));
      blocs.push(el('li', { class: 'synthese-top' },
        el('div', { class: 'synthese-etiquette' }, 'Où investir'),
        top.length ? el('ol', {}, top.map((t) => el('li', {}, el('button', { class: 'lien', type: 'button', onclick: () => aller({ type: 'investir', id: `o-${t.id}` }) },
          t.nom), ' ', pastilleVerdict(t.verdict), ' ', pastilleConviction(t.conviction), ' ', badgeScore(t.score))))
          : el('p', {}, 'Aucune opportunité à verdict positif aujourd’hui.')));
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
    section('Où investir : top 5', b.ou_investir?.length ? el('ol', {}, b.ou_investir.map((x) => el('li', {},
      el('button', { class: 'lien', type: 'button', onclick: () => aller({ type: 'investir', id: `o-${x.id}` }) }, x.nom), ' ',
      pastilleVerdict(x.verdict), ' ', pastilleConviction(x.conviction), ' ', badgeScore(x.score),
      x.argument ? el('div', { class: 'chef-petit' }, x.argument) : null))) : el('p', {}, 'Aucune opportunité à verdict positif sans objection à lever.')),
    b.panorama ? section('Panorama par catégorie', el('ul', {}, [
      ['Pays', b.panorama.pays], ['Matières premières', b.panorama.matieres], ['Or', b.panorama.or ? [b.panorama.or] : []],
      ['Obligations et liquidités', [...(b.panorama.obligations ?? []), ...(b.panorama.liquidites ?? [])]], ['Entreprises', b.panorama.entreprises],
    ].map(([t, xs]) => el('li', {}, el('strong', {}, `${t} : `), (xs ?? []).map((x) => `${x.nom} (${x.verdict.toLowerCase()})`).join(', ') || 'aucune donnée'))),
    b.panorama.a_surveiller?.length ? el('p', { class: 'chef-petit' }, `À surveiller : ${b.panorama.a_surveiller.map((x) => x.nom).join(', ')}`) : null) : null,
    section('Ce qui a changé depuis hier', liste(b.changements?.length ? b.changements.map((c) => c.texte) : ['Aucun verdict modifié.'])),
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

/* ------------------------------------------------------------------ écran « Où investir » */

function barreOnglets(actif, nav) {
  return el('div', { class: 'ini-onglets', role: 'tablist' }, Object.entries(ONGLETS_INVESTIR).map(([cle, libelle]) =>
    el('button', { class: `ini-onglet${cle === actif ? ' est-actif' : ''}`, type: 'button', role: 'tab', 'aria-selected': String(cle === actif),
      onclick: () => nav.ouvrir({ type: 'investir', id: cle }) }, libelle)));
}

/** Texte d'un argument pour / contre : celui de sa famille de signaux. */
const texteArgument = (l, a) => l.familles?.[a.cle]?.texte ?? a.texte ?? '';

function resume(t, n = 110) {
  return t && t.length > n ? `${t.slice(0, n - 1)}…` : t;
}

/** Une ligne de la liste : score, verdict, conviction, flèche, 3 pour, 3 contre, objection, date du dernier changement. */
function ligneOpportunite(l, nav) {
  return el('li', {}, el('button', { class: `chef-ligne ${classeVerdict(l.verdict)}`, type: 'button', onclick: () => nav.ouvrir({ type: 'investir', id: `o-${l.id}` }) },
    el('div', { class: 'chef-ligne-tete' },
      el('strong', { class: 'chef-ligne-nom' }, l.nom),
      badgeScore(l.score), fleche(l.fleche), pastilleVerdict(l.verdict), pastilleConviction(l.conviction)),
    l.en_attente ? el('div', { class: 'chef-petit chef-attente' }, `En attente : vers « ${l.en_attente.vers} »`) : null,
    el('div', { class: 'chef-args' },
      el('ul', { class: 'chef-pour' }, (l.pour ?? []).map((a) => el('li', {}, `${a.famille} : ${resume(texteArgument(l, a))}`))),
      el('ul', { class: 'chef-contre' }, (l.contre ?? []).map((a) => el('li', {}, `${a.famille} : ${resume(texteArgument(l, a))}`)))),
    l.objection ? el('div', { class: `chef-objection${l.objection.serieuse ? ' chef-objection--serieuse' : ''}` }, `Contradicteur (${l.objection.ajustement}) : ${resume(l.objection.objection, 160)}`) : null,
    el('div', { class: 'chef-petit' }, `Dernier changement de verdict : ${dateFr(l.derniere_modification)}`)));
}

function liste(lignes, nav) {
  return lignes?.length ? el('ul', { class: 'chef-liste' }, lignes.map((l) => ligneOpportunite(l, nav))) : el('p', { class: 'sante-ligne' }, 'Aucune donnée.');
}

function titre(t, sous) {
  return el('h3', { class: 'section-titre' }, t, sous ? el('small', {}, ` ${sous}`) : null);
}

export function ecranInvestir(chef, nav, id) {
  const entete = el('header', { class: 'chef-entete' },
    el('div', { class: 'fiche-surtitre' }, 'Chef d’orchestre · tous les agents réunis'),
    el('h2', { class: 'fiche-titre' }, 'Où investir'),
    chef ? el('p', { class: 'chef-regime' },
      el('span', { class: `synthese-palier risque-palier--${(chef.regime?.palier ?? 'inconnu').toLowerCase()}` }, `Risque : ${chef.regime?.palier ?? 'n. d.'}`), ' ',
      `Cycle mondial : ${chef.regime?.phase_monde ?? 'n. d.'} · analyse du ${dateFr(chef.date)}`,
      chef.mode === 'leger' && chef.declencheurs?.length ? ` · mise à jour légère (${chef.declencheurs.join(' ; ')})` : null) : null,
    el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'fiabilite-chef' }) }, '📈 Fiabilité du chef d’orchestre'));
  if (!chef) return [entete, el('p', { class: 'sante-ligne' }, 'Données du chef d’orchestre indisponibles (data/chef.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  if (id?.startsWith('o-')) {
    const l = toutes(chef).find((x) => x.id === id.slice(2));
    if (l) return ficheOpportunite(l, chef, nav);
  }
  const onglet = ONGLETS_INVESTIR[id] ? id : 'panorama';
  let corps;
  if (onglet === 'panorama') corps = ongletPanorama(chef, nav);
  else if (onglet === 'pays') corps = [titre('Actions par pays', `${chef.pays?.length ?? 0} pays suivis`), liste(chef.pays, nav)];
  else if (onglet === 'matieres') {
    corps = [titre('Or', 'valeur refuge, traité à part'), liste(chef.or ? [chef.or] : [], nav),
      titre('Matières premières', 'agent matières premières, horizon 3 à 12 mois'), liste(chef.matieres, nav)];
  } else if (onglet === 'obligations') {
    corps = [titre('Obligations d’État', 'États-Unis et zone euro, courtes et longues'), liste(chef.obligations, nav),
      titre('Liquidités', 'rendement monétaire réel = taux court − inflation'), liste(chef.liquidites, nav)];
  } else if (onglet === 'secteurs') {
    corps = ongletSecteurs(chef, nav);
  } else if (onglet === 'entreprises') {
    corps = ongletEntreprises(chef, nav);
  } else corps = ongletAllocation(chef, nav);
  return [
    entete,
    barreOnglets(onglet, nav),
    chef.concentrations?.length ? el('div', { class: 'chef-avertissement' }, chef.concentrations.map((c) => el('p', {}, `⚠ ${c.texte}`))) : null,
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
      `${e.libelle} : ${e.etat}${e.age_h != null ? ` (${nombre(e.age_h, 0)} h)` : ''}${e.degrade ? ' · agent dégradé' : ''} · poids ${nombre((e.coef ?? 0) * 100, 0)} %`))),
    el('p', { class: 'chef-petit' }, chef.methode ?? ''));
}

/* ------------------------------------------------------------------ panorama */

/** Ligne compacte du panorama : nom, score, verdict, conviction, justification ; ouvre la fiche. */
function lignePanorama(x, nav, raison) {
  return el('li', {}, el('button', { class: `chef-ligne chef-ligne--compacte ${classeVerdict(x.verdict)}`, type: 'button', onclick: () => nav.ouvrir({ type: 'investir', id: `o-${x.id}` }) },
    el('div', { class: 'chef-ligne-tete' }, el('strong', { class: 'chef-ligne-nom' }, x.nom), badgeScore(x.score), fleche(x.fleche), pastilleVerdict(x.verdict), pastilleConviction(x.conviction)),
    raison ? el('div', { class: 'chef-petit chef-attente' }, raison) : null,
    !raison && x.argument ? el('div', { class: 'chef-petit' }, `+ ${resume(x.argument, 140)}`) : null,
    !raison && x.contre ? el('div', { class: 'chef-petit' }, `− ${resume(x.contre, 140)}`) : null));
}

function ongletPanorama(chef, nav) {
  const p = chef.panorama;
  if (!p) return [el('p', { class: 'sante-ligne' }, 'Panorama pas encore calculé (prochaine analyse complète).')];
  const bloc = (t, sous, xs, vide) => [titre(t, sous), xs?.length ? el('ul', { class: 'chef-liste' }, xs.map((x) => lignePanorama(x, nav))) : el('p', { class: 'chef-petit' }, vide ?? 'Aucune donnée.')];
  return [
    ...bloc('Top 5', 'verdict positif au-dessus du seuil, sans objection à lever ; une ligne par catégorie d’abord', p.top, 'Aucune opportunité à verdict positif sans objection à lever.'),
    ...bloc('Pays', 'top 5', p.pays),
    ...bloc('Secteurs', 'top 3, une zone par secteur', p.secteurs),
    ...bloc('Matières premières', 'top 3', p.matieres),
    ...bloc('Or', 'valeur refuge', p.or ? [p.or] : []),
    ...bloc('Obligations et liquidités', 'position sur chaque ligne', [...(p.obligations ?? []), ...(p.liquidites ?? [])]),
    ...bloc('Entreprises', p.entreprises_bilan?.texte, p.entreprises),
    titre('À surveiller', 'proches du seuil, ou bien notées avec une objection à lever'),
    p.a_surveiller?.length ? el('ul', { class: 'chef-liste' }, p.a_surveiller.map((x) => lignePanorama(x, nav, x.raison))) : el('p', { class: 'chef-petit' }, 'Rien de proche du seuil.'),
    chef.exclues?.length ? el('p', { class: 'chef-petit' }, `Écartées (holdings, sociétés d’investissement, fonds, BDC, SPAC : la décote sur l’actif net n’est pas mesurable avec des sources gratuites) : ${chef.exclues.map((x) => x.nom).join(', ')}.`) : null,
  ];
}

/* ------------------------------------------------------------------ fiche détaillée */

function lienSource(l, nav) {
  if (l.type === 'pays') return el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrirPays(l.cle) }, 'Voir la fiche pays');
  if (l.type === 'matieres' || l.type === 'or') return el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'matieres', id: l.cle }) }, 'Voir la fiche matière première');
  if (l.type === 'entreprises' && nav.entrepriseExiste?.(l.cle)) return el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrirEntreprise(l.cle) }, 'Voir la fiche entreprise');
  if (l.type === 'secteurs') return el('button', { class: 'bouton', type: 'button', onclick: () => { zoneSecteurs = l.zone_secteur ?? 'monde'; nav.ouvrir({ type: 'investir', id: 'secteurs' }); } }, 'Voir les secteurs de la zone');
  if (l.type === 'obligations' || l.type === 'liquidites') return el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'macro' }) }, 'Voir la vue macro');
  return null;
}

function ficheOpportunite(l, chef, nav) {
  const familles = Object.entries(l.familles ?? {}).sort((a, b) => (l.poids_effectifs?.[b[0]] ?? 0) - (l.poids_effectifs?.[a[0]] ?? 0));
  return [
    el('header', { class: 'chef-entete' },
      el('div', { class: 'fiche-surtitre' }, `${TYPES[l.type] ?? l.type}${l.provenances?.length ? ` · ${l.provenances.join(', ')}` : ''}${l.type === 'secteurs' ? ` · ${l.nb_societes} sociétés analysées${l.symbole ? ` · ETF ${l.symbole}` : ''}${l.etf_approche ? ` (${l.etf_approche})` : ''}` : ''}`),
      el('h2', { class: 'fiche-titre' }, l.nom),
      el('div', { class: 'chef-ligne-tete' }, badgeScore(l.score), fleche(l.fleche), pastilleVerdict(l.verdict), pastilleConviction(l.conviction)),
      el('p', { class: 'chef-petit' }, `Verdict depuis le ${dateFr(l.depuis)}${l.score_precedent != null ? ` · score précédent ${nombre(l.score_precedent)}/100` : ''}${l.qualite != null ? ` · qualité des données ${nombre(l.qualite * 100)} %` : ''}`),
      el('div', { class: 'chef-actions' }, lienSource(l, nav), el('button', { class: 'bouton', type: 'button', onclick: () => nav.ouvrir({ type: 'investir', id: l.type === 'or' ? 'matieres' : l.type === 'liquidites' ? 'obligations' : l.type }) }, '‹ Retour à la liste'))),
    l.changement ? el('p', { class: 'chef-changement' }, l.changement.explication) : null,
    l.en_attente ? el('p', { class: 'chef-changement chef-attente' }, l.en_attente.texte) : null,
    l.plafond ? el('p', { class: 'chef-changement' }, l.plafond) : null,
    l.verification_momentum ? el('section', {}, titre('Vérification du momentum', l.verification_momentum.ok ? 'valorisation et positionnement vérifiés' : 'points à lever'),
      el('ul', { class: 'chef-texte' }, l.verification_momentum.points.map((x) => el('li', {}, x)))) : null,
    el('section', {}, titre('Conviction', l.conviction), el('ul', { class: 'chef-texte' }, (l.conviction_raisons ?? []).map((r) => el('li', {}, r)))),
    el('section', {}, titre('Familles de signaux', 'score /100 · poids effectif dans le score'),
      el('ul', { class: 'chef-familles' }, familles.map(([cle, f]) => el('li', {},
        el('div', { class: 'chef-famille-tete' }, el('strong', {}, f.libelle), badgeScore(f.note),
          el('small', {}, `poids ${nombre(l.poids_effectifs?.[cle] ?? 0, 0)} %${f.percentile_classe != null ? ` · percentile ${nombre(f.percentile_classe, 0)} dans la classe` : ''}${f.coef < 0.95 ? ` · fiabilité ${nombre(f.coef * 100, 0)} %` : ''}`)),
        el('div', { class: 'chef-barre' }, el('span', { class: classeScore(f.note), style: { width: `${Math.max(2, f.note)}%` } })),
        el('div', { class: 'chef-petit' }, f.texte),
        el('div', { class: 'chef-source' }, `Source : ${f.source}`)))),
      l.familles_manquantes?.length ? el('p', { class: 'chef-petit' }, `Données manquantes (non estimées) : ${l.familles_manquantes.join(', ')}.`) : null),
    el('section', {}, titre('Arguments pour'), el('ul', { class: 'chef-texte chef-pour' }, (l.pour ?? []).length ? l.pour.map((a) => el('li', {}, `${a.famille} (${nombre(a.note)}/100) : ${texteArgument(l, a)}`)) : el('li', {}, 'Aucun argument nettement favorable.'))),
    el('section', {}, titre('Arguments contre'), el('ul', { class: 'chef-texte chef-contre' }, (l.contre ?? []).length ? l.contre.map((a) => el('li', {}, `${a.famille} (${nombre(a.note)}/100) : ${texteArgument(l, a)}`)) : el('li', {}, 'Aucun argument nettement défavorable.'))),
    el('section', {}, titre('Objections du contradicteur', 'agent risque, 7 derniers jours'),
      l.objections?.length ? el('ul', { class: 'chef-texte' }, l.objections.map((o) => el('li', { class: o.serieuse ? 'chef-objection--serieuse' : '' },
        `${dateFr(o.date)} · « ${o.ajustement} »${o.serieuse ? ' (retenue : conviction abaissée)' : ''} — ${o.objection}`, el('div', { class: 'chef-source' }, `Signal : ${o.signal}`)))) : el('p', { class: 'chef-petit' }, 'Aucune objection.')),
    el('section', {}, titre('Ce qui pourrait me donner tort'), el('ul', { class: 'chef-texte' }, (l.donner_tort ?? []).map((x) => el('li', {}, x)))),
    l.societes?.length ? el('section', {}, titre('Meilleures sociétés du pays', 'agent entreprises'),
      el('ul', { class: 'chef-texte' }, l.societes.map((s) => el('li', {},
        nav.entrepriseExiste?.(s.ticker) ? el('button', { class: 'lien', type: 'button', onclick: () => nav.ouvrirEntreprise(s.ticker) }, s.nom ?? s.ticker) : (s.nom ?? s.ticker),
        ` (${s.ticker}) · note ${s.note ?? 'n. d.'}/100 · ${s.recommandation ?? ''}`)))) : null,
    mention(),
  ];
}

/* ------------------------------------------------------------------ allocation */

/* ------------------------------------------------------------------ secteurs et filtres */

let zoneSecteurs = 'monde';
let filtreSecteur = 'tous';

/** Puces de filtre (zone, secteur) ; `choisir` redessine le contenu sans quitter l'onglet. */
function puces(options, actif, choisir) {
  return el('div', { class: 'ini-onglets chef-filtre', role: 'group' }, options.map(([cle, libelle, n]) => el('button', {
    class: `ini-onglet${cle === actif ? ' est-actif' : ''}`, type: 'button', 'aria-pressed': String(cle === actif), onclick: () => choisir(cle),
  }, libelle, n != null ? el('small', {}, ` ${n}`) : null)));
}

function ongletSecteurs(chef, nav) {
  const zones = chef.zones_secteurs ?? { monde: 'Monde' };
  const conteneur = el('div', {});
  const rendre = () => {
    const lignes = (chef.secteurs ?? []).filter((l) => l.zone_secteur === zoneSecteurs).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    conteneur.replaceChildren(
      puces(Object.entries(zones).map(([k, v]) => [k, v, (chef.secteurs ?? []).filter((l) => l.zone_secteur === k).length]), zoneSecteurs, (k) => { zoneSecteurs = k; rendre(); }),
      lignes.length ? liste(lignes, nav) : el('p', { class: 'chef-petit' }, 'Pas assez de sociétés analysées dans cette zone pour noter les secteurs.'),
    );
  };
  rendre();
  return [titre('Secteurs', '11 secteurs GICS ; signaux agrégés des sociétés, ETF sectoriels, cycle, initiés, risque'), conteneur,
    el('p', { class: 'chef-petit' }, 'Momentum et flux : ETF sectoriels (XLK… aux États-Unis, iShares Global… dans le monde, iShares STOXX Europe 600 en Europe, secteurs ICB approchés). Émergents : pas d’ETF sectoriel exploitable, momentum tiré des sociétés.')];
}

function ongletEntreprises(chef, nav) {
  const conteneur = el('div', {});
  const rendre = () => {
    const toutes = chef.entreprises ?? [];
    const secteurs = [...new Set(toutes.map((l) => l.secteur_nom).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'));
    const lignes = filtreSecteur === 'tous' ? toutes : toutes.filter((l) => l.secteur_nom === filtreSecteur);
    conteneur.replaceChildren(
      puces([['tous', 'Tous les secteurs', toutes.length], ...secteurs.map((s) => [s, s, toutes.filter((l) => l.secteur_nom === s).length])], filtreSecteur, (k) => { filtreSecteur = k; rendre(); }),
      liste(lignes, nav),
    );
  };
  rendre();
  return [titre('Entreprises', 'pépites, qualité à prix raisonnable, liste de surveillance, meilleures sociétés des pays attractifs et de chaque secteur'), conteneur];
}

let profilActif = 'equilibre';

function ongletAllocation(chef, nav) {
  const a = chef.allocation;
  if (!a?.profils) return [el('p', { class: 'sante-ligne' }, 'Allocation pas encore calculée (analyse complète de 7 h 15 UTC).')];
  const conteneur = el('div', {});
  const rendre = () => {
    const p = a.profils[profilActif] ?? Object.values(a.profils)[0];
    const total = Object.values(p.classes ?? {}).reduce((s, v) => s + v, 0) || 1;
    conteneur.replaceChildren(...[
      el('div', { class: 'ini-onglets' }, Object.entries(a.profils).map(([cle, x]) => el('button', {
        class: `ini-onglet${cle === profilActif ? ' est-actif' : ''}`, type: 'button', onclick: () => { profilActif = cle; rendre(); },
      }, x.libelle))),
      el('div', { class: 'chef-classes' }, Object.entries(p.classes ?? {}).sort((x, y) => y[1] - x[1]).map(([c, v]) => el('span', {
        class: `chef-classe chef-classe--${c}`, style: { flexGrow: String(v / total) }, title: `${p.classes_libelles?.[c] ?? c} : ${nombre(v, 1)} %`,
      }, `${nombre(v, 0)} %`))),
      el('p', { class: 'chef-repartition' }, Object.entries(p.classes ?? {}).sort((x, y) => y[1] - x[1]).map(([c, v]) => el('span', {},
        el('span', { class: `chef-pastille chef-classe--${c}` }), `${p.classes_libelles?.[c] ?? c} ${nombre(v, 1)} %`))),
      el('p', { class: 'chef-petit' }, `Cœur ${nombre(100 - (p.satellite_pct ?? 0), 0)} % · satellites ${nombre(p.satellite_pct ?? 0, 0)} % (convictions fortes) · liquidités minimales au palier « ${a.palier} » : ${a.liquidites_min} %`),
      p.avertissements?.length ? el('div', { class: 'chef-avertissement' }, p.avertissements.map((x) => el('p', {}, `⚠ ${x}`))) : null,
      el('table', { class: 'chef-table' },
        el('thead', {}, el('tr', {}, ['Ligne', 'Poche', 'Poids', 'Variation', 'Justification'].map((t) => el('th', {}, t)))),
        el('tbody', {}, p.lignes.map((x) => el('tr', { class: x.poche === 'sortie' ? 'chef-sortie' : '' },
          el('td', {}, el('button', { class: 'lien', type: 'button', onclick: () => nav.ouvrir({ type: 'investir', id: `o-${x.id}` }) }, x.nom)),
          el('td', {}, x.poche), el('td', { class: 'mono' }, `${nombre(x.poids, 1)} %`),
          el('td', { class: 'mono' }, x.variation == null ? 'nouvelle' : `${x.variation > 0 ? '+' : x.variation < 0 ? '−' : ''}${nombre(Math.abs(x.variation), 1)} pt`),
          el('td', { class: 'chef-petit' }, x.justification))))),
      el('p', { class: 'chef-petit' }, `Contraintes : ${a.contraintes?.max_pays} % par pays, ${a.contraintes?.max_secteur} % par secteur, ${a.contraintes?.max_theme} % par thème, ${a.contraintes?.max_ligne} % par ligne ; écart minimal de ${a.contraintes?.rotation_seuil} pt pour modifier une ligne. Base du futur agent trader démo.`),
    ].filter(Boolean));
  };
  rendre();
  return [titre('Allocation modèle', 'indicative, cœur-satellite'), conteneur];
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
