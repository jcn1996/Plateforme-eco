/* ==========================================================================
   Écran « Santé des agents »
   --------------------------------------------------------------------------
   Lit data/journal/index.json puis chaque journal (bloc meta.sante écrit par
   les agents). Pour chaque agent : dernière exécution réussie, statut,
   sources qui répondent, sources en échec ou périmées.

   Statut (calculé ici, car il dépend de l'heure) :
   - « en panne »  : dernière exécution réussie plus ancienne que 2 × l'intervalle prévu
                     (ou journal illisible) ;
   - « dégradé »   : un indicateur a perdu une source qu'il devrait avoir (champ `degrade`
                     calculé par l'agent ; voir agents/commun/sante.py) ;
   - « OK »        : sinon.
   ========================================================================== */

import { el } from './outils.js';

const INDEX = 'data/journal/index.json';
const ETATS_PROBLEME = new Set(['secours', 'partielle', 'échec', 'périmée']);
const LIBELLES_ETAT = {
  'échec': 'en échec', 'périmée': 'périmée', secours: 'secours utilisé', partielle: 'réponse partielle',
};
export const STATUTS = {
  ok: { libelle: 'OK', classe: 'sante--ok' },
  degrade: { libelle: 'Dégradé', classe: 'sante--degrade' },
  panne: { libelle: 'En panne', classe: 'sante--panne' },
};

async function lireJson(chemin) {
  const r = await fetch(chemin, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${chemin} : ${r.status}`);
  return r.json();
}

/** Charge l'index puis chaque journal. Ne lève jamais : un journal illisible donne un agent « en panne ». */
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
      return { ...entree, sante: journal.meta?.sante ?? null };
    } catch {
      return { ...entree, sante: null };
    }
  }));
}

/** Statut d'un agent à l'instant `maintenant`. */
export function statutAgent(agent, maintenant = Date.now()) {
  const s = agent.sante;
  if (!s?.derniere_execution) return 'panne';
  const age = maintenant - Date.parse(s.derniere_execution);
  if (s.intervalle_min && age > 2 * s.intervalle_min * 60_000) return 'panne';
  // Règle de l'agent (sources attendues par indicateur) ; à défaut, toute source en difficulté
  const degrade = typeof s.degrade === 'boolean' ? s.degrade : (s.sources ?? []).some((src) => ETATS_PROBLEME.has(src.etat));
  if (degrade) return 'degrade';
  return 'ok';
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

/** Vrai si au moins un agent n'est pas « OK » ou si un calendrier n'a plus de date future (pastille rouge). */
export function problemeDetecte(agents, maintenant = Date.now()) {
  return agents.some((a) => statutAgent(a, maintenant) !== 'ok' || echeances(a, maintenant).some((e) => e.etat === 'expiree'));
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
  const age = (maintenant - Date.parse(s.derniere_execution)) / 60_000;
  const problemes = (s.sources ?? []).filter((src) => ETATS_PROBLEME.has(src.etat));
  const alertes = echeances(agent, maintenant).filter((e) => e.etat !== 'ok');
  return el('article', { class: `carte sante-carte ${classe}` },
    enTete,
    el('dl', { class: 'sante-details' },
      el('dt', {}, 'Dernière exécution réussie'),
      el('dd', {}, `${dateLisible(s.derniere_execution)} (il y a ${duree(age)})`),
      el('dt', {}, 'Sources qui répondent'),
      el('dd', { class: 'mono' }, `${s.sources_ok ?? '?'} / ${s.sources_total ?? '?'}`),
      el('dt', {}, 'Intervalle prévu'),
      el('dd', {}, s.intervalle_min ? `${duree(s.intervalle_min)} (panne au-delà de ${duree(2 * s.intervalle_min)})` : 'inconnu'),
    ),
    statut === 'panne'
      ? el('p', { class: 'sante-alerte' }, `Aucune exécution réussie depuis plus de 2 fois l’intervalle prévu. Vérifier l’onglet Actions (workflow ${s.workflow ?? ''}).`)
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
        el('h4', { class: 'sante-sous-titre' }, 'Indicateurs dégradés'),
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
  );
}

export function ecranSante(agents) {
  const maintenant = Date.now();
  const nb = { ok: 0, degrade: 0, panne: 0 };
  agents.forEach((a) => { nb[statutAgent(a, maintenant)] += 1; });
  return [
    el('header', {},
      el('div', { class: 'fiche-surtitre' }, 'Surveillance des agents automatiques'),
      el('h2', { class: 'fiche-titre' }, 'Santé des agents'),
    ),
    agents.length
      ? el('p', { class: 'sante-resume' }, `${nb.ok} OK · ${nb.degrade} dégradé${nb.degrade > 1 ? 's' : ''} · ${nb.panne} en panne`)
      : el('p', { class: 'sante-ligne' }, 'Aucun journal d’agent disponible (data/journal/index.json introuvable).'),
    ...agents.map((a) => carteAgent(a, maintenant)),
    el('p', { class: 'mention-legale' }, 'Lu dans data/journal/*.json. « En panne » : dernière exécution réussie plus ancienne que 2 fois l’intervalle prévu par le workflow.'),
  ];
}
