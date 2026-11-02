/* ==========================================================================
   Recherche : pays, secteurs et entreprises, par nom ou ticker,
   sans tenir compte des accents ni des majuscules.
   Toucher un résultat ouvre la fiche (le globe se centre sur le pays).
   ========================================================================== */

import { el, nombre, classeNote, normaliser } from './outils.js';

const MAX_RESULTATS = 25;
const TYPES = { pays: 'Pays', secteur: 'Secteur', entreprise: 'Entreprise' };

/** Index de recherche : un élément par pays, secteur et entreprise. */
function construireIndex(d) {
  const nomPays = (code) => d.paysParCode.get(code)?.nom ?? code;
  return [
    ...d.pays.map((p) => ({
      type: 'pays', route: { type: 'pays', id: p.code }, nom: p.nom, note: p.note,
      info: `Pays · ${p.code}`, cles: [p.nom, p.code],
    })),
    ...d.secteurs.map((s) => ({
      type: 'secteur', route: { type: 'secteur', id: s.id }, nom: s.nom, note: s.note,
      info: `Secteur · ${nomPays(s.pays)}`, cles: [s.nom, `${s.nom} ${nomPays(s.pays)}`],
    })),
    ...d.entreprises.map((e) => ({
      type: 'entreprise', route: { type: 'entreprise', id: e.ticker }, nom: e.nom, note: e.note,
      info: `${e.ticker} · ${d.secteurParId.get(e.secteur)?.nom ?? ''} · ${nomPays(e.pays)}`, cles: [e.nom, e.ticker],
    })),
  ].map((x) => ({ ...x, cles: x.cles.map(normaliser) }));
}

/** Pertinence : début du nom > début d'un mot > contenu ; 0 = pas de correspondance. */
function score(element, requete) {
  let meilleur = 0;
  for (const cle of element.cles) {
    if (cle === requete) meilleur = Math.max(meilleur, 4);
    else if (cle.startsWith(requete)) meilleur = Math.max(meilleur, 3);
    else if (cle.split(/[\s\-&'’()]+/).some((mot) => mot.startsWith(requete))) meilleur = Math.max(meilleur, 2);
    else if (cle.includes(requete)) meilleur = Math.max(meilleur, 1);
  }
  return meilleur;
}

/**
 * @param {object} d  données chargées
 * @param {object} elements  { bouton, panneau, champ, liste, fermer }
 * @param {(route:object) => void} ouvrir
 */
export function initialiserRecherche(d, { bouton, panneau, champ, liste, fermer }, ouvrir) {
  const index = construireIndex(d);
  let resultats = [];

  const afficher = () => {
    const requete = normaliser(champ.value);
    if (!requete) {
      resultats = [];
      liste.replaceChildren(el('li', { class: 'recherche-aide' }, 'Tapez un pays, un secteur, une entreprise ou un ticker (ex. « bresil », « semi », « HANB »).'));
      return;
    }
    const ordreType = { pays: 0, secteur: 1, entreprise: 2 };
    resultats = index
      .map((x) => ({ x, s: score(x, requete) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s || ordreType[a.x.type] - ordreType[b.x.type] || a.x.nom.localeCompare(b.x.nom, 'fr'))
      .slice(0, MAX_RESULTATS)
      .map((r) => r.x);
    liste.replaceChildren(...(resultats.length
      ? resultats.map((r, i) => el('li', {},
        el('button', {
          class: `resultat ${classeNote(r.note)}`, type: 'button', 'data-index': i,
          onclick: () => choisir(r),
        },
          el('span', { class: 'resultat-type' }, TYPES[r.type]),
          el('span', { class: 'resultat-textes' },
            el('span', { class: 'resultat-nom' }, r.nom),
            el('span', { class: 'resultat-info' }, r.info),
          ),
          el('span', { class: 'resultat-note mono' }, nombre(r.note)),
        )))
      : [el('li', { class: 'recherche-aide' }, `Aucun résultat pour « ${champ.value.trim()} ».`)]));
  };

  function choisir(r) {
    fermerRecherche();
    ouvrir(r.route);
  }

  function ouvrirRecherche() {
    panneau.hidden = false;
    bouton.setAttribute('aria-expanded', 'true');
    document.body.classList.add('recherche-ouverte');
    afficher();
    // Petit délai : le clavier du téléphone s'ouvre une fois le champ visible
    requestAnimationFrame(() => champ.focus());
  }
  function fermerRecherche() {
    panneau.hidden = true;
    bouton.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('recherche-ouverte');
    champ.blur();
  }

  bouton.addEventListener('click', () => (panneau.hidden ? ouvrirRecherche() : fermerRecherche()));
  fermer.addEventListener('click', fermerRecherche);
  champ.addEventListener('input', afficher);
  champ.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && resultats[0]) { e.preventDefault(); choisir(resultats[0]); }
    if (e.key === 'Escape') { e.stopPropagation(); fermerRecherche(); }
  });
  return { ouverte: () => !panneau.hidden, fermer: fermerRecherche };
}
