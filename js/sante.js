/* ==========================================================================
   Écran « Santé des agents »
   --------------------------------------------------------------------------
   Lit data/journal/index.json puis chaque journal (bloc meta.sante écrit par
   les agents). Pour chaque agent : dernière exécution réussie, statut,
   sources qui répondent, sources en échec ou périmées.

   Statut (calculé ici, car il dépend de l'heure), d'après le planning cron (UTC) que
   chaque agent déclare dans son journal (voir js/planning.js) :
   - « en panne »  : la première exécution prévue après la dernière exécution réussie
                     manque depuis plus de 2 h (agent à 15 min) ou 26 h (agent quotidien),
                     ou journal illisible ;
   - « en retard » : elle manque depuis plus de 45 min (agent à 15 min) ou 2 h (quotidien) ;
   - « dégradé »   : un indicateur a perdu une source qu'il devrait avoir (champ `degrade`
                     calculé par l'agent ; voir agents/commun/sante.py) ;
   - « en pause »  : hors des heures prévues (nuit), rien ne manque ;
   - « OK »        : sinon.
   ========================================================================== */

import { el } from './outils.js';
import { situationPlanning, heureParis } from './planning.js';

const INDEX = 'data/journal/index.json';
const ETATS_PROBLEME = new Set(['secours', 'partielle', 'échec', 'périmée']);
const LIBELLES_ETAT = {
  'échec': 'en échec', 'périmée': 'périmée', secours: 'secours utilisé', partielle: 'réponse partielle',
};
export const STATUTS = {
  ok: { libelle: 'OK', classe: 'sante--ok' },
  pause: { libelle: 'En pause', classe: 'sante--pause' },
  retard: { libelle: 'En retard', classe: 'sante--retard' },
  degrade: { libelle: 'Dégradé', classe: 'sante--degrade' },
  panne: { libelle: 'En panne', classe: 'sante--panne' },
};

async function lireJson(chemin) {
  const r = await fetch(chemin, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${chemin} : ${r.status}`);
  return r.json();
}

const CHAMPS_PREMIER_NIVEAU = ['derniere_execution', 'prochaine_prevue', 'intervalle_min', 'planning'];

/** Bloc meta.sante complété par les champs du premier niveau du journal (prioritaires s'ils sont renseignés). */
export function fusionnerSante(journal) {
  const sante = journal?.meta?.sante;
  if (!sante) return null;
  const fusion = { ...sante };
  CHAMPS_PREMIER_NIVEAU.forEach((c) => { if (journal[c] != null) fusion[c] = journal[c]; });
  // Par prudence, la plus récente des deux dates d'exécution
  const enMeta = Date.parse(sante.derniere_execution ?? '');
  if (enMeta > (Date.parse(fusion.derniere_execution ?? '') || 0)) fusion.derniere_execution = sante.derniere_execution;
  return fusion;
}

/** Charge l'index puis chaque journal. Ne lève jamais : un journal illisible donne un agent « en panne ». */
/* Planificateur (réveil externe) : dernier appel lu en direct sur l'API publique de GitHub
   (dernière exécution du workflow), au plus toutes les 5 minutes ; à défaut, dans son journal
   (mis à jour au moins toutes les 20 minutes). */
const API_PLANIFICATEUR = 'https://api.github.com/repos/jcn1996/Plateforme-eco/actions/workflows/planificateur.yml/runs?per_page=1';
let appelEnDirect = { lu: 0, date: null };

async function dernierAppelEnDirect() {
  if (Date.now() - appelEnDirect.lu < 5 * 60_000) return appelEnDirect.date;
  appelEnDirect.lu = Date.now();
  try {
    const r = await fetch(API_PLANIFICATEUR, { headers: { Accept: 'application/vnd.github+json' } });
    if (r.ok) appelEnDirect.date = (await r.json()).workflow_runs?.[0]?.created_at ?? null;
  } catch {
    /* dépôt privé, limite de l'API ou hors ligne : on garde le journal */
  }
  return appelEnDirect.date;
}

export async function chargerSante() {
  let index;
  try {
    index = (await lireJson(INDEX)).donnees ?? [];
  } catch {
    return [];
  }
  return Promise.all(index.map(async (entree) => {
    try {
      const journal = await lireJson(`data/journal/${entree.fichier}`);
      const s = fusionnerSante(journal);
      if (s?.appel_externe) {
        const direct = await dernierAppelEnDirect();
        if (direct && (!s.derniere_execution || Date.parse(direct) > Date.parse(s.derniere_execution))) {
          s.derniere_execution = direct;
          s.appel_lu_en_direct = true;
        }
      }
      return { ...entree, sante: s };
    } catch {
      return { ...entree, sante: null };
    }
  }));
}

/** Statut d'un agent à l'instant `maintenant`. */
export function statutAgent(agent, maintenant = Date.now()) {
  const s = agent.sante;
  // Analyse à la demande : pas de planning ; dégradée si la dernière exécution a échoué
  if (s?.a_la_demande) return s.dernier_statut === 'echec' ? 'degrade' : 'ok';
  if (!s?.derniere_execution) return 'panne';
  if (s.appel_externe) {
    // Planificateur : appelé toutes les 15 min par le réveil externe ; en panne sans appel depuis 45 min
    if (maintenant - Date.parse(s.derniere_execution) > (s.panne_minutes ?? 45) * 60_000) return 'panne';
    return s.degrade ? 'degrade' : 'ok';
  }
  const { etat } = situationPlanning(s, maintenant);
  if (etat === 'panne' || etat === 'retard') return etat;
  // Règle de l'agent (sources attendues par indicateur) ; à défaut, toute source en difficulté
  const degrade = typeof s.degrade === 'boolean' ? s.degrade : (s.sources ?? []).some((src) => ETATS_PROBLEME.has(src.etat));
  if (degrade) return 'degrade';
  return etat === 'pause' ? 'pause' : 'ok';
}

/** Date du jour (AAAA-MM-JJ, heure locale). */
function aujourdhuiIso(maintenant) {
  const d = new Date(maintenant);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * Échéances d'un agent (ex. calendrier des réunions des banques centrales) :
 * « expiree » quand plus aucune date future n'est connue, « proche » à moins de 60 jours.
 */
export function echeances(agent, maintenant = Date.now()) {
  const jour = aujourdhuiIso(maintenant);
  return (agent.sante?.echeances ?? []).map((e) => {
    const jours = Math.round((Date.parse(e.jusqua) - Date.parse(jour)) / 86_400_000);
    return { ...e, jours, etat: e.jusqua < jour ? 'expiree' : jours <= 60 ? 'proche' : 'ok' };
  });
}

/** Vrai si au moins un agent n'est ni « OK » ni « En pause » ou si un calendrier n'a plus de date future (pastille rouge). */
export function problemeDetecte(agents, maintenant = Date.now()) {
  return agents.some((a) => !['ok', 'pause'].includes(statutAgent(a, maintenant)) || echeances(a, maintenant).some((e) => e.etat === 'expiree'));
}

/** « 02/11 17:34 » (heure locale), ou une période brute (« 2025-01 ») si ce n'est pas une date complète. */
function dateLisible(valeur) {
  if (!valeur) return 'inconnue';
  if (!/T/.test(valeur)) return valeur;
  const d = new Date(valeur);
  if (Number.isNaN(d.getTime())) return valeur;
  return d.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Durée lisible : « 12 min », « 3 h », « 2 j ». */
function duree(minutes) {
  if (minutes == null) return 'inconnu';
  if (minutes < 90) return `${Math.round(minutes)}\u00a0min`;
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)}\u00a0h`;
  return `${Math.round(minutes / 1440)}\u00a0j`;
}

/** Carte du planificateur (réveil externe) : dernier appel reçu, dernier lancement d'agent. */
function cartePlanificateur(agent, s, statut, classe, enTete, age) {
  return el('article', { class: `carte sante-carte ${classe}` },
    enTete,
    el('dl', { class: 'sante-details' },
      el('dt', {}, 'Dernier appel reçu'),
      el('dd', {}, `${dateLisible(s.derniere_execution)} (il y a ${duree(age)})${s.appel_lu_en_direct ? ' · lu sur GitHub' : ''}`),
      el('dt', {}, 'Appels attendus'),
      el('dd', {}, `toutes les 15 min (panne au-delà de ${duree(s.panne_minutes ?? 45)})`),
      el('dt', {}, 'Dernier lancement d’agent'),
      el('dd', {}, s.dernier_lancement ? dateLisible(s.dernier_lancement) : 'aucun'),
    ),
    statut === 'panne'
      ? el('p', { class: 'sante-alerte' }, `Aucun appel du réveil externe depuis plus de ${duree(s.panne_minutes ?? 45)}. `
        + 'Vérifier la tâche sur cron-job.org et son jeton GitHub (voir le README, « Réveil externe »). Les plannings GitHub restent actifs en secours.')
      : null,
    s.raisons?.length ? el('ul', { class: 'sante-sources' }, s.raisons.map((r) => el('li', { class: 'sante-source-info' }, r))) : null,
  );
}

/** Carte de l'analyse à la demande : dernière analyse réussie, dernière tentative, échecs récents. */
function carteALaDemande(s, statut, classe, enTete) {
  const r = s.derniere_reussite;
  const libelleStatut = { ok: 'réussie', introuvable: 'société introuvable', insuffisant: 'données insuffisantes', echec: 'échec', refus: 'refusée' };
  return el('article', { class: `carte sante-carte ${classe}` },
    enTete,
    el('dl', { class: 'sante-details' },
      el('dt', {}, 'Dernière analyse réussie'),
      el('dd', {}, r ? `${dateLisible(r.date)} · ${r.ticker}${r.issue ? ` (issue #${r.issue})` : ''}` : 'aucune pour l’instant'),
      el('dt', {}, 'Dernière demande'),
      el('dd', {}, s.derniere_tentative ? `${dateLisible(s.derniere_tentative)} · ${libelleStatut[s.dernier_statut] ?? s.dernier_statut ?? ''}` : 'aucune'),
      el('dt', {}, 'Analyses réussies'),
      el('dd', { class: 'mono' }, `${s.analyses_reussies ?? 0} / ${s.executions ?? 0} demandes`),
      el('dt', {}, 'Déclenchement'),
      el('dd', {}, 'à la demande (issue « Analyse : … »), sans planning'),
    ),
    s.echecs_recents?.length
      ? el('div', {},
        el('h4', { class: 'sante-sous-titre' }, statut === 'degrade' ? 'Dernière analyse en échec' : 'Échecs récents'),
        el('ul', { class: 'sante-sources' }, s.echecs_recents.map((e) => el('li', {},
          el('div', { class: 'sante-source-ligne' },
            el('span', { class: 'sante-source-nom' }, `« ${e.texte ?? '?'} »${e.issue ? ` · issue #${e.issue}` : ''}`),
            el('span', { class: 'sante-source-etat sante-etat--echec' }, dateLisible(e.date))),
          el('div', { class: 'sante-source-info' }, e.detail ?? ''))))) : el('p', { class: 'sante-ligne' }, 'Aucun échec enregistré.'),
    statut === 'degrade' ? el('p', { class: 'sante-alerte sante-alerte--retard' }, `Vérifier l’onglet Actions (workflow ${s.workflow ?? 'analyse-demande.yml'}), puis relancer avec une nouvelle issue.`) : null,
  );
}

function carteAgent(agent, maintenant) {
  const s = agent.sante;
  const statut = statutAgent(agent, maintenant);
  const { libelle, classe } = STATUTS[statut];
  const enTete = el('div', { class: 'sante-entete' },
    el('h3', { class: 'sante-nom' }, agent.libelle ?? agent.agent),
    el('span', { class: `sante-statut ${classe}` }, libelle),
  );
  if (!s) {
    return el('article', { class: `carte sante-carte ${classe}` }, enTete,
      el('p', { class: 'sante-ligne' }, 'Journal introuvable ou illisible : aucune exécution réussie connue.'));
  }
  if (s.a_la_demande) return carteALaDemande(s, statut, classe, enTete);
  const age = (maintenant - Date.parse(s.derniere_execution)) / 60_000;
  if (s.appel_externe) return cartePlanificateur(agent, s, statut, classe, enTete, age);
  const plan = situationPlanning(s, maintenant);
  // Sources secondaires (ex. GDELT DOC pour l'agent géopolitique) : affichées pour information
  const secondaires = (s.sources ?? []).filter((src) => src.secondaire);
  const problemes = (s.sources ?? []).filter((src) => ETATS_PROBLEME.has(src.etat) && !src.secondaire);
  // Clés facultatives absentes : affichées pour information, sans compter comme un échec
  const nonConfigurees = (s.sources ?? []).filter((src) => src.etat === 'non configurée');
  // Services accessoires (ex. rédaction par Gemini) : leur échec est une information, sans effet sur le statut
  const informations = (s.sources ?? []).filter((src) => src.etat === 'information');
  // Listes manuelles vérifiées (composition impossible à récupérer automatiquement) : information
  const manuelles = (s.sources ?? []).filter((src) => src.manuelle && src.etat === 'ok');
  const alertes = echeances(agent, maintenant).filter((e) => e.etat !== 'ok');
  return el('article', { class: `carte sante-carte ${classe}` },
    enTete,
    el('dl', { class: 'sante-details' },
      el('dt', {}, 'Dernière exécution réussie'),
      el('dd', {}, `${dateLisible(s.derniere_execution)} (il y a ${duree(age)})`),
      el('dt', {}, 'Sources qui répondent'),
      el('dd', { class: 'mono' }, `${s.sources_ok ?? '?'} / ${s.sources_total ?? '?'}`),
      el('dt', {}, 'Prochaine mise à jour'),
      el('dd', {}, plan.prochaine != null ? `${heureParis(plan.prochaine)} (heure de Paris)` : 'inconnue'),
      el('dt', {}, 'Intervalle prévu'),
      el('dd', {}, plan.base ? `${duree(plan.base)} (retard au-delà de ${duree(plan.seuils.retard)}, panne au-delà de ${duree(plan.seuils.panne)})` : 'inconnu'),
      // Agents qui appellent une IA sous quota gratuit (agent géopolitique) : consommation du jour
      s.ia ? el('dt', {}, 'Analyse par IA') : null,
      s.ia ? el('dd', {}, `${s.ia.mode === 'gemini' ? 'Gemini' : 'sans IA'} · jour du Pacifique ${s.ia.jour_quota ?? ''} : `,
        (s.ia.modeles ?? [{ modele: s.ia.modele, appels: s.ia.appels_du_jour, limite_jour: s.ia.quota_jour }])
          .map((m) => `${m.modele} ${m.appels ?? 0}/${m.limite_jour ?? '?'}${m.epuise ? ' (quota atteint)' : ''}`).join(' · ')) : null,
    ),
    statut === 'pause'
      ? el('p', { class: 'sante-ligne' }, `Hors des heures prévues. Prochaine mise à jour : ${heureParis(plan.prochaine)}.`)
      : null,
    plan.manquante != null && plan.etat !== 'ok'
      ? el('p', { class: plan.etat === 'panne' ? 'sante-alerte' : 'sante-alerte sante-alerte--retard' },
        `Exécution prévue ${heureParis(plan.manquante)} (heure de Paris) manquante depuis ${duree(plan.retardMin)}. `
        + `Le workflow « Rattrapage » la relance après 1 h ; sinon, vérifier l’onglet Actions (workflow ${s.workflow ?? ''}).`)
      : null,
    alertes.length
      ? el('div', {},
        el('h4', { class: 'sante-sous-titre' }, 'Calendriers à compléter'),
        el('ul', { class: 'sante-sources' }, alertes.map((e) => el('li', {},
          el('div', { class: 'sante-source-ligne' },
            el('span', { class: 'sante-source-nom' }, e.libelle),
            el('span', { class: `sante-source-etat sante-etat--${e.etat === 'expiree' ? 'echec' : 'autre'}` },
              e.etat === 'expiree' ? 'plus de date future' : `dernière date dans ${e.jours} j`),
          ),
          el('div', { class: 'sante-source-info' }, `Dernière date connue : ${e.jusqua} · à compléter dans agents/macro/calendrier_banques_centrales.json`),
        ))))
      : null,
    statut === 'degrade' && s.raisons?.length
      ? el('div', {},
        el('h4', { class: 'sante-sous-titre' }, 'Causes de la dégradation'),
        el('ul', { class: 'sante-sources' }, s.raisons.map((r) => el('li', { class: 'sante-source-info' }, r))))
      : null,
    problemes.length
      ? el('div', {},
        el('h4', { class: 'sante-sous-titre' }, statut === 'ok' ? 'Sources en échec ou périmées (compensées par d’autres sources)' : 'Sources en échec ou périmées'),
        el('ul', { class: 'sante-sources' }, problemes.map((src) => el('li', {},
          el('div', { class: 'sante-source-ligne' },
            el('span', { class: 'sante-source-nom' }, src.nom),
            el('span', { class: `sante-source-etat sante-etat--${src.etat === 'échec' ? 'echec' : 'autre'}` }, LIBELLES_ETAT[src.etat] ?? src.etat),
          ),
          el('div', { class: 'sante-source-info' },
            `Dernière donnée valide : ${dateLisible(src.derniere_donnee_valide)}`,
            src.detail ? ` · ${src.detail}` : null),
        ))))
      : el('p', { class: 'sante-ligne' }, 'Toutes les sources répondent.'),
    manuelles.length
      ? el('p', { class: 'sante-source-info' }, 'Listes manuelles (information) : ',
        manuelles.map((src) => `${(src.nom.match(/^Composition (\w+)/) ?? [])[1] ?? src.nom} (vérifiée le ${src.manuelle.slice(8, 10)}/${src.manuelle.slice(5, 7)}/${src.manuelle.slice(0, 4)})`).join(', '),
        '. Revérification nécessaire après 6 mois (config/compositions_manuelles.json).')
      : null,
    informations.length
      ? el('p', { class: 'sante-source-info' }, 'Information (sans effet sur le statut) : ',
        informations.map((src) => `${src.nom}${src.detail ? ` : ${src.detail}` : ''}`).join(' ; '), '.')
      : null,
    nonConfigurees.length
      ? el('p', { class: 'sante-source-info' }, 'Non configurées (facultatives, non comptées) : ',
        nonConfigurees.map((src) => src.nom).join(', '), '.')
      : null,
    secondaires.length
      ? el('p', { class: 'sante-source-info' }, 'Sources secondaires (information, sans effet sur le statut) : ',
        secondaires.map((src) => `${src.nom} : ${LIBELLES_ETAT[src.etat] ?? src.etat}${src.detail ? ` (${src.detail})` : ''}`).join(' ; '), '.')
      : null,
  );
}

export function ecranSante(agents) {
  const maintenant = Date.now();
  const nb = { ok: 0, pause: 0, retard: 0, degrade: 0, panne: 0 };
  agents.forEach((a) => { nb[statutAgent(a, maintenant)] += 1; });
  return [
    el('header', {},
      el('div', { class: 'fiche-surtitre' }, 'Surveillance des agents automatiques'),
      el('h2', { class: 'fiche-titre' }, 'Santé des agents'),
    ),
    agents.length
      ? el('p', { class: 'sante-resume' }, [`${nb.ok} OK`, nb.pause ? `${nb.pause} en pause` : null, nb.retard ? `${nb.retard} en retard` : null,
        `${nb.degrade} dégradé${nb.degrade > 1 ? 's' : ''}`, `${nb.panne} en panne`].filter(Boolean).join(' · '))
      : el('p', { class: 'sante-ligne' }, 'Aucun journal d’agent disponible (data/journal/index.json introuvable).'),
    ...agents.map((a) => carteAgent(a, maintenant)),
    el('p', { class: 'mention-legale' }, 'Lu dans data/journal/*.json (planning cron en UTC déclaré par chaque agent). « En retard » : exécution prévue manquante depuis plus de 45 min (agent à 15 min) ou 2 h (agent quotidien) ; « En panne » : depuis plus de 2 h ou 26 h ; « En pause » : hors des heures prévues.'),
  ];
}
