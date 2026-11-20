/* ==========================================================================
   Écran « Bilan du mois » (lien depuis l'accueil, Menu → Suivi) : point mensuel
   écrit par l'agent trader à sa première exécution de chaque mois
   (data/bilan/index.json, data/bilan/AAAA-MM.json ; agents/trader/bilan.py) :
   performance du portefeuille démo, du MSCI World et du portefeuille
   « momentum seul » (mois et depuis le 16/11/2026), entrées et sorties de la
   liste, taux de réussite des signaux en observation.
   ========================================================================== */

import { el, nombre } from './outils.js';

const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
export const moisLong = (m) => (m ? `${MOIS[Number(m.slice(5, 7)) - 1]} ${m.slice(0, 4)}` : 'n. d.');
export const signeBilan = (x, unite = ' %') => (x == null ? 'n. d.' : `${x > 0 ? '+' : x < 0 ? '−' : ''}${nombre(Math.abs(x), 1)}${unite}`);

/** Écart (points) du portefeuille démo à chaque référence, sur le mois et depuis le début ; null si une valeur manque. */
export function ecarts(b) {
  const [pf, ...refs] = b?.performances ?? [];
  const d = (a, c) => (a == null || c == null ? null : Math.round((a - c) * 100) / 100);
  return refs.map((r) => ({ nom: r.nom, mois: d(pf?.mois_pct, r.mois_pct), depuis: d(pf?.depuis_debut_pct, r.depuis_debut_pct) }));
}

async function lire(chemin) {
  try {
    const r = await fetch(chemin, { cache: 'no-cache' });
    return r.ok ? (await r.json())?.donnees ?? null : null;
  } catch {
    return null;
  }
}

/** { mois: [AAAA-MM…], bilan: bilan du mois demandé (ou du plus récent) } ; null si aucun bilan. */
export async function chargerBilan(mois) {
  const index = await lire('data/bilan/index.json');
  if (!index?.length) return null;
  const m = mois && index.includes(mois) ? mois : index[0];
  return { mois: index, courant: m, bilan: await lire(`data/bilan/${m}.json`) };
}

const titre = (t, sous) => el('h3', { class: 'section-titre' }, t, sous ? el('small', {}, ` ${sous}`) : null);

export function ecranBilan(r, nav) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Suivi · point mensuel automatique'),
    el('h2', { class: 'fiche-titre' }, r?.bilan ? `Bilan du mois — ${moisLong(r.courant)}` : 'Bilan du mois'));
  if (r === undefined) return [entete, el('p', { class: 'sante-ligne' }, 'Chargement…')];
  if (!r?.bilan) return [entete, el('p', { class: 'sante-ligne' }, 'Aucun bilan pour l’instant : le premier sera écrit le 1er décembre 2026 (première exécution du trader du mois), pour novembre.')];
  const b = r.bilan;
  return [
    entete,
    r.mois.length > 1 ? el('div', { class: 'ini-onglets', role: 'tablist' }, r.mois.map((m) => el('button', {
      class: `ini-onglet${m === r.courant ? ' est-actif' : ''}`, type: 'button', onclick: () => nav.ouvrir({ type: 'bilan', id: m }),
    }, moisLong(m)))) : null,
    titre('Performances', `sur le mois et depuis le ${b.debut_reference?.split('-').reverse().join('/') ?? '16/11/2026'}`),
    el('table', { class: 'chef-table' },
      el('thead', {}, el('tr', {}, ['', 'Mois', 'Depuis le début'].map((t) => el('th', {}, t)))),
      el('tbody', {}, (b.performances ?? []).map((p) => el('tr', {}, el('td', {}, p.nom),
        el('td', { class: 'mono' }, signeBilan(p.mois_pct)), el('td', { class: 'mono' }, signeBilan(p.depuis_debut_pct)))))),
    el('ul', { class: 'chef-texte' }, ecarts(b).map((e) => el('li', {}, `Portefeuille démo face à ${e.nom} : ${signeBilan(e.mois, ' pt')} sur le mois, ${signeBilan(e.depuis, ' pt')} depuis le début.`))),
    titre('Liste d’investissement', 'entrées et sorties du mois'),
    b.liste?.disponible === false ? el('p', { class: 'chef-petit' }, b.liste.raison) : el('ul', { class: 'chef-texte chef-mouvements' },
      [...(b.liste?.entrees ?? []), ...(b.liste?.sorties ?? [])].map((m) => el('li', { class: `chef-mouvement--${m.sens === 'sortie' ? 'sortie' : 'entree'}` },
        `${m.date.split('-').reverse().join('/')} · ${m.texte}`))),
    !(b.liste?.entrees?.length || b.liste?.sorties?.length) && b.liste?.disponible !== false ? el('p', { class: 'chef-petit' }, 'Aucune entrée ni sortie ce mois-ci.') : null,
    titre('Signaux en observation', 'part des signaux mesurés à 1 mois qui battent le MSCI World'),
    el('ul', { class: 'chef-texte' }, Object.values(b.observation ?? {}).map((o) => el('li', {},
      `${o.libelle} : ${o.mesures_1m ? `${nombre(o.battent_indice_pct ?? 0, 0)} % (${o.mesures_1m} mesurés, écart moyen ${signeBilan(o.ecart_moyen_points, ' pt')})` : `pas encore mesurable (${o.enregistres ?? 0} enregistrés)`}`))),
    el('p', { class: 'chef-petit' }, b.methode ?? ''),
    el('p', { class: 'chef-mention' }, b.mention ?? ''),
  ];
}
