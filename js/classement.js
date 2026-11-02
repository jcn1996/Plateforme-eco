/* ==========================================================================
   Écran « Classement » : deux onglets
   - Pays : tous les pays suivis, triés par note
   - Entreprises : les 20 meilleures notes, tous pays confondus
   Toucher une ligne ouvre la fiche correspondante.
   ========================================================================== */

import { el, nombre, classeNote, libelleNiveau, niveauNote, badgeTendance, tendanceNote } from './outils.js';

const NB_ENTREPRISES = 20;

/** Onglet affiché (mémorisé pendant la session pour le retour depuis une fiche). */
let ongletActif = 'pays';

export function ecranClassement(d, nav) {
  const conteneur = el('div', {});
  const onglets = [
    { cle: 'pays', libelle: `Pays (${d.pays.length})` },
    { cle: 'entreprises', libelle: `Entreprises (top ${NB_ENTREPRISES})` },
  ];
  const boutons = onglets.map((o) => el('button', {
    class: 'onglet', type: 'button', role: 'tab', id: `classement-${o.cle}`,
    'aria-controls': 'classement-liste',
    onclick: () => choisir(o.cle),
  }, o.libelle));
  const liste = el('div', { class: 'classement', id: 'classement-liste', role: 'tabpanel' });

  function choisir(cle) {
    ongletActif = cle;
    boutons.forEach((b, i) => b.setAttribute('aria-selected', String(onglets[i].cle === cle)));
    liste.setAttribute('aria-labelledby', `classement-${cle}`);
    liste.replaceChildren(...(cle === 'pays' ? lignesPays(d, nav) : lignesEntreprises(d, nav)));
  }
  choisir(ongletActif);

  conteneur.append(
    el('div', { class: 'onglets', role: 'tablist', 'aria-label': 'Type de classement' }, boutons),
    liste,
  );
  return [
    el('header', {},
      el('div', { class: 'fiche-surtitre' }, 'Classement par note sur 100'),
      el('h2', { class: 'fiche-titre' }, 'Classement'),
    ),
    conteneur,
    el('p', { class: 'mention-legale' }, d.fictifPar?.pays === false
      ? 'Pays : données réelles analysées par l’agent pays · entreprises : notes fictives (démonstration).'
      : 'Notes fictives — démonstration uniquement.'),
  ];
}

function ligne({ rang, note, nom, info, surClic, tendance }) {
  return el('button', { class: `ligne-classement ${classeNote(note)}`, type: 'button', onclick: surClic,
    'aria-label': `${rang}. ${nom}, ${info}, note ${note} sur 100, ${libelleNiveau(niveauNote(note))}` },
    el('span', { class: 'ligne-classement-rang', 'aria-hidden': 'true' }, String(rang)),
    el('span', { class: 'pastille', 'aria-hidden': 'true' }),
    el('span', { class: 'ligne-classement-textes', 'aria-hidden': 'true' },
      el('span', { class: 'ligne-classement-nom' }, nom),
      el('span', { class: 'ligne-classement-info' }, info),
    ),
    el('span', { class: 'ligne-classement-note' }, el('span', { 'aria-hidden': 'true' }, nombre(note)), badgeTendance(tendance)),
  );
}

function lignesPays(d, nav) {
  return [...d.pays]
    .sort((a, b) => b.note - a.note || a.nom.localeCompare(b.nom, 'fr'))
    .map((p, i) => ligne({
      rang: i + 1, note: p.note, nom: p.nom, info: p.verdict, tendance: tendanceNote(p),
      surClic: () => nav.ouvrirPays(p.code),
    }));
}

function lignesEntreprises(d, nav) {
  return [...d.entreprises]
    .sort((a, b) => b.note - a.note || a.nom.localeCompare(b.nom, 'fr'))
    .slice(0, NB_ENTREPRISES)
    .map((e, i) => ligne({
      rang: i + 1, note: e.note, nom: e.nom, tendance: tendanceNote(e),
      info: `${d.secteurParId.get(e.secteur)?.nom ?? ''} · ${d.paysParCode.get(e.pays)?.nom ?? e.pays}`,
      surClic: () => nav.ouvrirEntreprise(e.ticker),
    }));
}
