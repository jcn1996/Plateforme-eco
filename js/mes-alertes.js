/* ==========================================================================
   « Mes alertes » : règles personnelles vérifiées à chaque chargement.

   Format stocké sur l'appareil (localStorage, clé « salle-controle:mes-alertes »),
   pensé pour être relu plus tard par le serveur des agents :

   {
     "version": 1,
     "regles": [
       {
         "id": "r-lx3k9a",                      identifiant unique
         "active": true,                         règle activée ou non
         "cree_le": "2026-11-01T21:30:00.000Z",
         "cible": { "type": "pays", "id": "BR" },  type « pays » ou « entreprise » ;
                                                   id null = tous
         "indicateur": "inflation",              « note » ou clé d'indicateur
         "condition": "passe_sous",              « depasse » ou « passe_sous »
         "seuil": 4,                             nombre, dans l'unité de l'indicateur
         "derniere_verification": "…",           mis à jour à chaque vérification
         "declenchee": true,
         "elements_declenches": ["BR"]
       }
     ]
   }
   ========================================================================== */

import { el, nombre, niveauNote, lireMetrique, metrique, METRIQUES_PAYS, METRIQUES_ENTREPRISE } from './outils.js';

const CLE = 'salle-controle:mes-alertes';

/* ------------------------------ Stockage ------------------------------ */

export function lireRegles() {
  try {
    const s = JSON.parse(localStorage.getItem(CLE));
    if (s?.version === 1 && Array.isArray(s.regles)) return s.regles;
  } catch { /* rien */ }
  return [];
}

function enregistrerRegles(regles) {
  try { localStorage.setItem(CLE, JSON.stringify({ version: 1, regles }, null, 2)); } catch { /* rien */ }
}

function nouvelId() {
  return `r-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
}

/* ------------------------------ Évaluation ------------------------------ */

function elementsCibles(d, cible) {
  const tous = cible.type === 'pays' ? d.pays : d.entreprises;
  if (!cible.id) return tous;
  return tous.filter((e) => (cible.type === 'pays' ? e.code : e.ticker) === cible.id);
}

/** Texte lisible d'une règle : « L'inflation du Brésil passe sous 4 % ». */
export function libelleRegle(d, r) {
  const m = metrique(r.cible.type, r.indicateur);
  const nomIndicateur = (m?.libelle ?? r.indicateur).toLowerCase();
  let sujet;
  if (r.cible.id) {
    const e = elementsCibles(d, r.cible)[0];
    sujet = r.indicateur === 'note' ? `${e?.nom ?? r.cible.id} (note)` : `${m?.libelle ?? r.indicateur} : ${e?.nom ?? r.cible.id}`;
  } else {
    sujet = r.cible.type === 'pays' ? 'Un pays' : 'Une entreprise';
    if (r.indicateur !== 'note') sujet += ` (${nomIndicateur})`;
  }
  const verbe = r.condition === 'depasse' ? 'dépasse' : 'passe sous';
  return `${sujet} ${verbe} ${nombre(r.seuil, Number.isInteger(r.seuil) ? 0 : 1)}${uniteSeuil(d, r)}`;
}

function uniteSeuil(d, r) {
  if (r.indicateur === 'note') return '/100';
  if (r.indicateur === 'momentum') return ' %';
  const exemple = (r.cible.type === 'pays' ? d.pays : d.entreprises)[0]?.indicateurs?.[r.indicateur];
  return exemple?.unite === '%' ? ' %' : exemple?.unite === 'x' ? '×' : exemple?.unite ? ` ${exemple.unite}` : '';
}

/**
 * Vérifie toutes les règles actives sur les données chargées.
 * Renvoie les alertes à afficher en tête du bandeau (badge « Mon alerte »).
 */
export function evaluerRegles(d) {
  const regles = lireRegles();
  const maintenant = new Date();
  const heure = maintenant.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  const alertes = [];
  for (const r of regles) {
    if (!r.active) continue;
    const touches = [];
    for (const e of elementsCibles(d, r.cible)) {
      const m = lireMetrique(e, r.indicateur);
      if (!m) continue;
      const ok = r.condition === 'depasse' ? m.valeur > r.seuil : m.valeur < r.seuil;
      if (ok) touches.push({ e, m });
    }
    r.derniere_verification = maintenant.toISOString();
    r.declenchee = touches.length > 0;
    r.elements_declenches = touches.map(({ e }) => (r.cible.type === 'pays' ? e.code : e.ticker));
    if (!touches.length) continue;
    touches.sort((a, b) => (r.condition === 'depasse' ? b.m.valeur - a.m.valeur : a.m.valeur - b.m.valeur));
    const premiers = touches.slice(0, 4).map(({ e, m }) => `${e.nom} (${m.texte})`).join(', ');
    const premier = touches[0];
    alertes.push({
      id: `perso-${r.id}`,
      perso: true,
      heure,
      niveau: niveauNote(premier.m.note),
      titre: libelleRegle(d, r),
      texte: premiers + (touches.length > 4 ? ` et ${touches.length - 4} autre${touches.length > 5 ? 's' : ''}` : ''),
      route: { type: r.cible.type, id: r.cible.type === 'pays' ? premier.e.code : premier.e.ticker },
    });
  }
  enregistrerRegles(regles);
  return alertes;
}

/* ------------------------------ Écran « Mes alertes » ------------------------------ */

/** Exemples proposés en un toucher. */
const EXEMPLES = [
  { libelle: 'Un pays dépasse 75', regle: { cible: { type: 'pays', id: null }, indicateur: 'note', condition: 'depasse', seuil: 75 } },
  { libelle: "L'inflation du Brésil passe sous 4 %", regle: { cible: { type: 'pays', id: 'BR' }, indicateur: 'inflation', condition: 'passe_sous', seuil: 4 } },
  { libelle: 'Une entreprise passe au rouge', regle: { cible: { type: 'entreprise', id: null }, indicateur: 'note', condition: 'passe_sous', seuil: 50 } },
];

/**
 * @param {object} d  données chargées
 * @param {object} rappels  { surChangement() : les règles ont changé, ouvrir(route) }
 */
export function ecranMesAlertes(d, rappels) {
  const conteneur = el('div', { class: 'mes-alertes' });

  const ajouter = (regle) => {
    const regles = lireRegles();
    regles.push({ id: nouvelId(), active: true, cree_le: new Date().toISOString(), ...structuredClone(regle) });
    enregistrerRegles(regles);
    dessiner();
  };

  function dessiner() {
    rappels.surChangement(); // réévalue (met à jour l'état « déclenchée »)
    const regles = lireRegles();
    conteneur.replaceChildren(
      el('header', {},
        el('div', { class: 'fiche-surtitre' }, 'Règles vérifiées à chaque chargement des données'),
        el('h2', { class: 'fiche-titre' }, 'Mes alertes'),
      ),
      formulaire(d, ajouter),
      el('section', {},
        el('h3', { class: 'section-titre' }, 'Exemples', el('small', {}, 'un toucher pour ajouter')),
        el('div', { class: 'exemples' }, EXEMPLES.map((x) => el('button', { class: 'puce', type: 'button', onclick: () => ajouter(x.regle) }, `+ ${x.libelle}`))),
      ),
      el('section', {},
        el('h3', { class: 'section-titre' }, `Mes règles (${regles.length})`),
        regles.length
          ? el('ul', { class: 'liste-regles' }, regles.map((r) => ligneRegle(d, r, { dessiner, rappels })))
          : el('p', { class: 'fiche-verdict' }, 'Aucune règle pour le moment.'),
      ),
      el('details', { class: 'format-json' },
        el('summary', {}, 'Format des règles (JSON, pour le serveur des agents)'),
        el('pre', {}, JSON.stringify({ version: 1, regles }, null, 2)),
      ),
      el('p', { class: 'mention-legale' }, 'Les règles sont enregistrées sur cet appareil uniquement.'),
    );
  }
  dessiner();
  return [conteneur];
}

function ligneRegle(d, r, { dessiner, rappels }) {
  const modifier = (changement) => {
    const regles = lireRegles().map((x) => (x.id === r.id ? { ...x, ...changement } : x));
    enregistrerRegles(regles);
    dessiner();
  };
  const supprimer = () => {
    enregistrerRegles(lireRegles().filter((x) => x.id !== r.id));
    dessiner();
  };
  const etat = !r.active ? 'Désactivée'
    : r.declenchee ? `Déclenchée : ${r.elements_declenches.length} élément${r.elements_declenches.length > 1 ? 's' : ''}` : 'Non déclenchée';
  return el('li', { class: `regle${r.active ? '' : ' regle--inactive'}${r.active && r.declenchee ? ' regle--declenchee' : ''}` },
    el('label', { class: 'interrupteur', title: r.active ? 'Désactiver' : 'Activer' },
      el('input', { type: 'checkbox', checked: r.active, onchange: (e) => modifier({ active: e.target.checked }), 'aria-label': `Activer la règle « ${libelleRegle(d, r)} »` }),
      el('span', { 'aria-hidden': 'true' }),
    ),
    el('div', { class: 'regle-textes' },
      el('span', { class: 'regle-libelle' }, libelleRegle(d, r)),
      el('span', { class: 'regle-etat' }, etat),
    ),
    r.active && r.declenchee
      ? el('button', { class: 'bouton bouton--petit', type: 'button', onclick: () => rappels.ouvrir({ type: r.cible.type, id: r.elements_declenches[0] }) }, 'Voir')
      : null,
    el('button', { class: 'bouton bouton--icone bouton--danger', type: 'button', title: 'Supprimer', 'aria-label': 'Supprimer la règle', onclick: supprimer }, '🗑'),
  );
}

/** Formulaire de création : type, cible, indicateur, condition, seuil. */
function formulaire(d, ajouter) {
  const champ = (libelle, controle) => el('label', { class: 'champ' }, el('span', {}, libelle), controle);
  const type = el('select', {}, el('option', { value: 'pays' }, 'Pays'), el('option', { value: 'entreprise' }, 'Entreprise'));
  const cible = el('select', {});
  const indicateur = el('select', {});
  const condition = el('select', {}, el('option', { value: 'depasse' }, 'dépasse'), el('option', { value: 'passe_sous' }, 'passe sous'));
  const seuil = el('input', { type: 'number', inputmode: 'decimal', step: 'any', value: '75', required: true });
  const unite = el('span', { class: 'champ-unite' });

  const remplir = () => {
    const estPays = type.value === 'pays';
    const liste = [...(estPays ? d.pays : d.entreprises)].sort((a, b) => a.nom.localeCompare(b.nom, 'fr'));
    cible.replaceChildren(
      el('option', { value: '' }, estPays ? 'Tous les pays' : 'Toutes les entreprises'),
      ...liste.map((e) => el('option', { value: estPays ? e.code : e.ticker }, e.nom)),
    );
    indicateur.replaceChildren(...(estPays ? METRIQUES_PAYS : METRIQUES_ENTREPRISE).map((m) => el('option', { value: m.cle }, m.libelle)));
    majUnite();
  };
  const majUnite = () => {
    unite.textContent = uniteSeuil(d, { cible: { type: type.value }, indicateur: indicateur.value }).trim() || '';
  };
  type.addEventListener('change', remplir);
  indicateur.addEventListener('change', majUnite);
  remplir();

  return el('form', {
    class: 'carte formulaire-regle',
    onsubmit: (e) => {
      e.preventDefault();
      const valeur = Number(String(seuil.value).replace(',', '.'));
      if (!Number.isFinite(valeur)) { seuil.focus(); return; }
      ajouter({ cible: { type: type.value, id: cible.value || null }, indicateur: indicateur.value, condition: condition.value, seuil: valeur });
    },
  },
    el('h3', { class: 'section-titre' }, 'Nouvelle règle'),
    el('div', { class: 'champs' },
      champ('Type', type),
      champ('Qui', cible),
      champ('Indicateur', indicateur),
      champ('Condition', condition),
      champ('Seuil', el('span', { class: 'champ-seuil' }, seuil, unite)),
    ),
    el('button', { class: 'bouton bouton--accent bouton--plein', type: 'submit' }, 'Ajouter la règle'),
  );
}

