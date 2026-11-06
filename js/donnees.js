/* ==========================================================================
   Chargement des données
   --------------------------------------------------------------------------
   C'est le SEUL endroit qui sait où se trouvent les fichiers JSON.
   Aujourd'hui ils sont fictifs ; demain, les agents IA écriront des fichiers
   de même structure (même enveloppe { meta, donnees }) et rien d'autre
   n'aura à changer dans l'application.
   ========================================================================== */

/** Liste des fichiers à charger (nom interne → chemin). */
const FICHIERS = {
  pays: 'data/pays.json',
  secteurs: 'data/secteurs.json',
  entreprises: 'data/entreprises.json',
  alertes: 'data/alertes.json',
  portefeuille: 'data/portefeuille.json',
  marches: 'data/marches.json',
};

/** Frontières des pays (Natural Earth 1:110m via world-atlas, domaine public). */
const FICHIER_FRONTIERES = 'data/countries-110m.json';

/** Charge un fichier JSON et vérifie qu'il respecte l'enveloppe attendue. */
async function chargerFichier(nom, chemin) {
  const reponse = await fetch(chemin, { cache: 'no-cache' });
  if (!reponse.ok) throw new Error(`Fichier ${chemin} introuvable (${reponse.status})`);
  const json = await reponse.json();
  if (!json || typeof json !== 'object' || !('donnees' in json)) {
    throw new Error(`Le fichier ${chemin} n'a pas la structure attendue { meta, donnees }`);
  }
  return { meta: json.meta ?? {}, donnees: json.donnees };
}

/**
 * Charge tous les fichiers en parallèle puis construit des index
 * pour retrouver rapidement un pays, un secteur ou une entreprise.
 */
export async function chargerDonnees() {
  const noms = Object.keys(FICHIERS);
  const promesseFrontieres = fetch(FICHIER_FRONTIERES).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const resultats = await Promise.all(noms.map((nom) => chargerFichier(nom, FICHIERS[nom])));
  const brut = Object.fromEntries(noms.map((nom, i) => [nom, resultats[i]]));

  // Frontières des pays (TopoJSON Natural Earth 1:110m, fichier tiers sans enveloppe)
  // Chargées en parallèle des autres, mais leur absence n'empêche pas l'appli de fonctionner.
  const frontieres = await promesseFrontieres;

  const pays = brut.pays.donnees;
  const secteurs = brut.secteurs.donnees;
  const entreprises = brut.entreprises.donnees;

  // Index : accès direct par identifiant
  const paysParCode = new Map(pays.map((p) => [p.code, p]));
  const secteurParId = new Map(secteurs.map((s) => [s.id, s]));
  const entrepriseParTicker = new Map(entreprises.map((e) => [e.ticker, e]));

  // Regroupements : secteurs d'un pays, entreprises d'un secteur
  const secteursParPays = grouper(secteurs, (s) => s.pays);
  const entreprisesParSecteur = grouper(entreprises, (e) => e.secteur);

  // Données fictives ? (si un seul fichier l'est, on affiche la mention)
  const fictif = resultats.some((r) => r.meta.fictif !== false);
  // Détail fichier par fichier (les pays sont réels, le reste encore fictif)
  const fictifPar = Object.fromEntries(noms.map((nom) => [nom, brut[nom].meta.fictif !== false]));

  return {
    meta: Object.fromEntries(noms.map((nom) => [nom, brut[nom].meta])),
    fictif,
    fictifPar,
    frontieres,
    pays,
    secteurs,
    entreprises,
    alertes: brut.alertes.donnees,
    portefeuille: brut.portefeuille.donnees,
    marches: brut.marches.donnees,
    paysParCode,
    secteurParId,
    entrepriseParTicker,
    secteursDuPays: (code) => secteursParPays.get(code) ?? [],
    entreprisesDuSecteur: (id) => entreprisesParSecteur.get(id) ?? [],
  };
}

function grouper(liste, cle) {
  const groupes = new Map();
  for (const element of liste) {
    const k = cle(element);
    if (!groupes.has(k)) groupes.set(k, []);
    groupes.get(k).push(element);
  }
  return groupes;
}
