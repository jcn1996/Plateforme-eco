/* ==========================================================================
   Écran « Signaux en observation » (Menu → Suivi) : achats de dirigeants,
   révisions à la hausse des analystes et relèvements de guidance, enregistrés
   chaque jour par l'agent trader SANS ÊTRE UTILISÉS pour décider, avec la
   performance des actifs concernés à 1, 3 et 6 mois contre le MSCI World.
   Données : data/observation.json (agents/trader/observation.py).
   ========================================================================== */

import { el, nombre } from './outils.js';

export const TYPES_OBSERVATION = {
  achat_dirigeant: 'Achats de dirigeants', revision_analystes: 'Révisions à la hausse des analystes', relevement_guidance: 'Relèvements de guidance',
};

/** « +1,2 % », « −0,4 pt », « n. d. ». */
export function signeObs(x, d = 1, unite = ' %') {
  if (x === null || x === undefined || Number.isNaN(x)) return 'n. d.';
  return `${x > 0 ? '+' : x < 0 ? '−' : ''}${nombre(Math.abs(x), d)}${unite}`;
}

/** Signaux les plus récents d'abord, filtrés par type (« tous » : aucun filtre). */
export function signauxFiltres(signaux, type = 'tous', n = 60) {
  return [...(signaux ?? [])].filter((s) => type === 'tous' || s.type === type)
    .sort((a, b) => String(b.date_depart ?? b.date_signal).localeCompare(String(a.date_depart ?? a.date_signal))).slice(0, n);
}

export async function chargerObservation() {
  try {
    const r = await fetch('data/observation.json', { cache: 'no-cache' });
    if (!r.ok) return null;
    const j = await r.json();
    return j?.donnees ? { meta: j.meta ?? {}, ...j.donnees } : null;
  } catch {
    return null;
  }
}

const titre = (t, sous) => el('h3', { class: 'section-titre' }, t, sous ? el('small', {}, ` ${sous}`) : null);

export function ecranObservation(obs, nav) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Suivi · observation, sans décision'),
    el('h2', { class: 'fiche-titre' }, 'Signaux en observation'));
  if (obs === undefined) return [entete, el('p', { class: 'sante-ligne' }, 'Chargement…')];
  if (!obs) return [entete, el('p', { class: 'sante-ligne' }, 'Aucun signal enregistré pour l’instant (data/observation.json introuvable) : l’agent trader les enregistre une fois par jour.')];
  const horizons = obs.horizons_mois ?? [1, 3, 6];
  const conteneur = el('div', {});
  let filtre = 'tous';
  const rendre = () => conteneur.replaceChildren(
    el('div', { class: 'ini-onglets', role: 'tablist' }, [['tous', 'Tous'], ...Object.entries(TYPES_OBSERVATION)].map(([cle, lib]) =>
      el('button', { class: `ini-onglet${cle === filtre ? ' est-actif' : ''}`, type: 'button', role: 'tab', 'aria-selected': String(cle === filtre),
        onclick: () => { filtre = cle; rendre(); } }, lib))),
    el('ul', { class: 'pf-fil' }, signauxFiltres(obs.signaux, filtre).map((s) => el('li', {},
      el('div', { class: 'pf-op-tete' },
        el('span', { class: 'obs-type' }, TYPES_OBSERVATION[s.type] ?? s.type),
        s.type !== 'achat_dirigeant' && nav?.ouvrirEntreprise ? el('button', { class: 'lien', type: 'button', onclick: () => nav.ouvrirEntreprise(s.symbole) }, s.nom ?? s.symbole)
          : el('strong', {}, s.nom ?? s.symbole),
        el('span', { class: 'mono' }, s.symbole)),
      el('p', { class: 'chef-petit' }, `${s.date_signal}${s.cours_depart != null ? ` · cours de départ ${nombre(s.cours_depart, 2)} (${s.date_depart})` : ' · cours de départ à venir'} · ${s.texte ?? ''}`),
      el('p', { class: 'chef-petit mono' }, horizons.map((h) => {
        const p = s.performance?.[String(h)];
        return `${h} mois : ${p ? `${signeObs(p.pct)} (indice ${signeObs(p.msci_world_pct)}, écart ${signeObs(p.ecart_points, 1, ' pt')})` : 'à venir'}`;
      }).join(' · ')))))
  );
  rendre();
  const resume = obs.resume ?? {};
  return [
    entete,
    el('p', { class: 'chef-avertissement' }, obs.mention ?? 'Observation seulement : aucun ordre n’est passé sur ces signaux.'),
    el('p', { class: 'chef-petit' }, obs.regle ?? ''),
    titre('Bilan par type', `performance moyenne des actifs concernés, et écart moyen au MSCI World (${obs.indice ?? 'URTH'})`),
    el('table', { class: 'chef-table' },
      el('thead', {}, el('tr', {}, el('th', {}, 'Signal'), el('th', {}, 'Enregistrés'), horizons.map((h) => el('th', {}, `${h} mois`)))),
      el('tbody', {}, Object.entries(TYPES_OBSERVATION).map(([cle, lib]) => {
        const r = resume[cle] ?? {};
        return el('tr', {}, el('td', {}, lib), el('td', { class: 'mono' }, String(r.enregistres ?? 0)),
          horizons.map((h) => {
            const x = r.horizons?.[String(h)] ?? {};
            return el('td', { class: 'mono' }, x.n ? `${signeObs(x.moyenne_pct)} · ${signeObs(x.ecart_moyen_points, 1, ' pt')} · ${nombre(x.battent_indice_pct ?? 0, 0)} % (${x.n})` : '—');
          }));
      }))),
    el('p', { class: 'chef-petit' }, 'Lecture : performance moyenne · écart moyen à l’indice · part des actifs qui le battent (nombre de signaux mesurés). Performances en devise de cotation.'),
    titre('Derniers signaux'),
    conteneur,
  ];
}
