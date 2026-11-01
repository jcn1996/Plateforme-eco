/* ==========================================================================
   Comparateur : 2 ou 3 pays, ou 2 ou 3 entreprises, côte à côte.
   - Bouton « Comparer » sur chaque fiche (ajoute / retire de la sélection)
   - Barre flottante avec la sélection et « Voir la comparaison »
   - Écran de comparaison : note, verdict, chaque indicateur sur une ligne,
     meilleure valeur mise en évidence (celle qui a la meilleure note)
   La sélection est gardée sur l'appareil.
   ========================================================================== */

import { el, nombre, classeNote, niveauNote, libelleNiveau, lireMetrique, METRIQUES_PAYS, METRIQUES_ENTREPRISE } from './outils.js';
import { notifier } from './interface.js';

const CLE = 'salle-controle:comparaison';
const MAX = 3;

let selection = lire();           // { type: 'pays' | 'entreprise', ids: [] }
let d = null;                     // données chargées
let barre = null;                 // barre flottante
let ouvrirComparaison = () => {};
const abonnes = new Set();        // boutons « Comparer » à mettre à jour

function lire() {
  try {
    const s = JSON.parse(localStorage.getItem(CLE));
    if (s && ['pays', 'entreprise'].includes(s.type) && Array.isArray(s.ids)) return s;
  } catch { /* rien */ }
  return { type: null, ids: [] };
}
function enregistrer() {
  try { localStorage.setItem(CLE, JSON.stringify(selection)); } catch { /* rien */ }
}

/** Trouve un élément (pays ou entreprise) par son identifiant. */
function element(type, id) {
  return type === 'pays' ? d.paysParCode.get(id) : d.entrepriseParTicker.get(id);
}

export function initialiserComparateur(donnees, { barre: noeud, ouvrir }) {
  d = donnees;
  barre = noeud;
  ouvrirComparaison = ouvrir;
  // On écarte les éléments qui n'existent plus dans les données
  selection.ids = selection.ids.filter((id) => element(selection.type, id));
  majBarre();
}

export function selectionComparaison() {
  return { type: selection.type, elements: selection.ids.map((id) => element(selection.type, id)).filter(Boolean) };
}

function estSelectionne(type, id) {
  return selection.type === type && selection.ids.includes(id);
}

function basculer(type, id) {
  if (estSelectionne(type, id)) {
    selection.ids = selection.ids.filter((x) => x !== id);
  } else {
    if (selection.type !== type && selection.ids.length) {
      notifier(`Comparaison réinitialisée : on compare ${type === 'pays' ? 'des pays entre eux' : 'des entreprises entre elles'}.`);
      selection = { type, ids: [] };
    }
    if (selection.ids.length >= MAX) { notifier(`${MAX} éléments maximum dans une comparaison.`); return; }
    selection.type = type;
    selection.ids.push(id);
  }
  if (!selection.ids.length) selection.type = null;
  enregistrer();
  majBarre();
  abonnes.forEach((f) => f());
}

/** Bouton « Comparer » d'une fiche (pays ou entreprise). */
export function boutonComparer(type, id) {
  const bouton = el('button', { class: 'bouton bouton--petit', type: 'button', onclick: () => basculer(type, id) });
  let premiere = true;
  const maj = () => {
    // Bouton retiré de la page (fiche fermée) : on se désabonne
    if (!premiere && !bouton.isConnected) { abonnes.delete(maj); return; }
    premiere = false;
    const choisi = estSelectionne(type, id);
    bouton.setAttribute('aria-pressed', String(choisi));
    bouton.textContent = choisi ? '✓ Dans la comparaison' : '+ Comparer';
  };
  abonnes.add(maj);
  maj();
  return bouton;
}

/** Barre flottante : sélection en cours + « Voir la comparaison ». */
export function majBarre(masquee = false) {
  if (!barre) return;
  const { type, elements } = selectionComparaison();
  barre.hidden = masquee || !elements.length;
  document.body.classList.toggle('comparaison-active', !barre.hidden); // réserve de la place sous les contenus
  if (barre.hidden) return;
  barre.replaceChildren(
    el('div', { class: 'barre-comparaison-elements' },
      elements.map((e) => el('span', { class: `puce-selection ${classeNote(e.note)}` },
        el('span', { class: 'pastille', 'aria-hidden': 'true' }),
        e.nom,
        el('button', { type: 'button', class: 'puce-retirer', 'aria-label': `Retirer ${e.nom}`, onclick: () => basculer(type, type === 'pays' ? e.code : e.ticker) }, '×'),
      )),
      elements.length < 2 ? el('span', { class: 'barre-comparaison-aide' }, `Ajoutez ${type === 'pays' ? 'un autre pays' : 'une autre entreprise'}`) : null,
    ),
    el('button', {
      class: 'bouton bouton--accent', type: 'button', disabled: elements.length < 2,
      onclick: () => ouvrirComparaison(),
    }, 'Voir la comparaison'),
  );
}

/* ------------------------------ Écran de comparaison ------------------------------ */

export function ecranComparaison(donnees, nav) {
  const { type, elements } = selectionComparaison();
  if (elements.length < 2) {
    return [el('p', { class: 'fiche-verdict' }, 'Sélectionnez au moins deux pays ou deux entreprises avec le bouton « + Comparer » de leur fiche.')];
  }
  const id = (e) => (type === 'pays' ? e.code : e.ticker);
  const metriques = (type === 'pays' ? METRIQUES_PAYS : METRIQUES_ENTREPRISE).filter((m) => m.cle !== 'note');
  const colonnes = { style: { '--n': elements.length } };

  // Meilleur = meilleure note pour cette ligne (en cas d'égalité, tous sont mis en évidence)
  const meilleurs = (lectures) => {
    const max = Math.max(...lectures.map((l) => l?.note ?? -1));
    return lectures.map((l) => l && l.note === max);
  };
  const notes = elements.map((e) => ({ note: e.note }));
  const meilleureNote = meilleurs(notes);

  const sousTitre = (e) => (type === 'pays'
    ? libelleNiveau(niveauNote(e.note))
    : `${donnees.secteurParId.get(e.secteur)?.nom ?? ''} · ${donnees.paysParCode.get(e.pays)?.nom ?? ''}`);

  return [
    el('header', {},
      el('div', { class: 'fiche-surtitre' }, `Comparaison · ${elements.length} ${type === 'pays' ? 'pays' : 'entreprises'}`),
      el('h2', { class: 'fiche-titre' }, elements.map((e) => e.nom).join(' / ')),
    ),

    // En-têtes : nom, sous-titre, note
    el('div', { class: 'comparaison-grille', ...colonnes },
      elements.map((e, i) => el('button', {
        class: `comparaison-tete ${classeNote(e.note)}${meilleureNote[i] ? ' est-meilleur' : ''}`, type: 'button',
        onclick: () => (type === 'pays' ? nav.ouvrirPays(id(e)) : nav.ouvrirEntreprise(id(e))),
      },
        el('span', { class: 'comparaison-nom' }, e.nom),
        el('span', { class: 'comparaison-sous-titre' }, sousTitre(e)),
        el('span', { class: 'comparaison-note' }, nombre(e.note), el('small', {}, '/100')),
        meilleureNote[i] ? el('span', { class: 'comparaison-etoile' }, '★ meilleure note') : null,
      )),
    ),

    // Verdicts
    el('section', {},
      el('h3', { class: 'section-titre' }, 'Verdict'),
      el('div', { class: 'comparaison-grille', ...colonnes },
        elements.map((e) => el('p', { class: 'comparaison-verdict' }, e.verdict))),
    ),

    // Indicateurs : une ligne par indicateur
    el('section', {},
      el('h3', { class: 'section-titre' }, 'Indicateurs', el('small', {}, '★ = meilleure note de la ligne')),
      metriques.map((m) => {
        const lectures = elements.map((e) => lireMetrique(e, m.cle));
        const best = meilleurs(lectures);
        return el('div', { class: 'comparaison-ligne' },
          el('div', { class: 'comparaison-libelle' }, m.libelle),
          el('div', { class: 'comparaison-grille', ...colonnes },
            lectures.map((l, i) => el('div', {
              class: `comparaison-cellule ${l ? classeNote(l.note) : ''}${best[i] ? ' est-meilleur' : ''}`,
              'aria-label': l ? `${elements[i].nom} : ${l.texte}, note ${l.note} sur 100${best[i] ? ', meilleure valeur' : ''}` : 'non disponible',
            },
              el('span', { class: 'comparaison-valeur' }, l ? l.texte : '–'),
              l ? el('span', { class: 'comparaison-note-ind' }, best[i] ? '★ ' : '', `${l.note}/100`) : null,
            ))),
        );
      }),
    ),

    el('p', { class: 'mention-legale' }, 'Données fictives — démonstration uniquement.'),
  ];
}
