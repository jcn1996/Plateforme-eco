/* ==========================================================================
   Écran « Pépites » : pépites candidates de l'agent entreprises (data/pepites.json).
   Filtres par région et par secteur ; pour chaque société : note, ajustement de
   contexte (pays et cycle, affiché à part), 3 indicateurs clés, verdict ; badge quand
   la guidance a été relevée ou abaissée récemment.
   Toucher une ligne ouvre la fiche entreprise. Mini-graphique TradingView sur 12 mois.
   ========================================================================== */

import { el, nombre, variation, classeNote } from './outils.js';
import { boutonAnalyser, pastilleReco } from './analyses.js';
import { graphiqueMini } from './graphiques.js';
import { historiqueEntreprise } from './panneau-entreprise.js';
import { badgeGuidance } from './dynamique-resultats.js';

const FICHIER = 'data/pepites.json';
const filtres = { liste: 'pepites', region: 'toutes', secteur: 'tous' }; // mémorisés pendant la session

const LISTES = {
  pepites: { titre: 'Pépites', aide: 'Capitalisation de 300 M$ à 20 Md$, peu suivies par les analystes' },
  qpr: { titre: 'Qualité à prix raisonnable', aide: 'Grandes sociétés (plus de 20 Md$) qui remplissent les mêmes critères' },
};

/** Charge data/pepites.json ; null si le fichier manque (l'appli continue). */
export async function chargerPepites() {
  try {
    const r = await fetch(FICHIER, { cache: 'no-cache' });
    if (!r.ok) return null;
    const j = await r.json();
    return Array.isArray(j?.donnees) ? { meta: j.meta ?? {}, liste: j.donnees } : null;
  } catch {
    return null;
  }
}

const LIBELLES_CLES = { croissance_ca: 'CA', marge_op: 'Marge op.', per_secteur: 'PER vs sect.', roe: 'ROE', fscore: 'F-score' };

function puces(titre, options, actif, choisir) {
  return el('div', { class: 'pepites-filtre', role: 'group', 'aria-label': titre },
    el('span', { class: 'pepites-filtre-titre' }, titre),
    el('div', { class: 'pepites-puces' }, options.map(([cle, libelle, n]) => el('button', {
      class: 'puce', type: 'button', 'aria-pressed': String(cle === actif), onclick: () => choisir(cle),
    }, libelle, n != null ? el('small', {}, ` ${n}`) : null))),
  );
}

export function ecranPepites(p, d, nav) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Agent entreprises · toutes régions'),
    el('h2', { class: 'fiche-titre' }, 'Pépites candidates'),
    el('div', { class: 'analyses-actions' }, boutonAnalyser(),
      nav.ouvrir ? el('button', { type: 'button', class: 'bouton', onclick: () => nav.ouvrir({ type: 'analyses' }) }, 'Mes analyses') : null),
  );
  if (!p) {
    return [entete, el('p', { class: 'sante-ligne' }, 'Données de l’agent entreprises indisponibles (data/pepites.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  }
  const regions = p.meta.regions ?? {};
  const conteneur = el('div', {});

  // Anciennes données (une seule liste, sans champ « liste ») : tout est dans « pepites »
  const dansListe = (x) => (x.liste ?? 'pepites') === filtres.liste;
  const onglets = el('div', { class: 'onglets', role: 'tablist', 'aria-label': 'Listes' });
  const rendre = () => {
    onglets.replaceChildren(...Object.entries(LISTES).map(([cle, l]) => el('button', {
      class: 'onglet', type: 'button', role: 'tab', 'aria-selected': String(filtres.liste === cle),
      onclick: () => { filtres.liste = cle; filtres.region = 'toutes'; filtres.secteur = 'tous'; rendre(); },
    }, `${l.titre} (${p.liste.filter((x) => (x.liste ?? 'pepites') === cle).length})`)));
    const liste = p.liste.filter(dansListe);
    const parRegion = liste.filter((x) => filtres.region === 'toutes' || x.region === filtres.region);
    const visibles = parRegion.filter((x) => filtres.secteur === 'tous' || x.secteur_gics === filtres.secteur);
    const compte = (liste, cle) => liste.reduce((m, x) => m.set(x[cle], (m.get(x[cle]) ?? 0) + 1), new Map());
    const nbRegions = compte(liste, 'region');
    const nbSecteurs = compte(parRegion, 'secteur_gics');
    const nomsSecteurs = new Map(p.liste.map((x) => [x.secteur_gics, x.secteur_nom]));
    conteneur.replaceChildren(
      el('p', { class: 'fiche-verdict' }, LISTES[filtres.liste].aide, ` · au plus ${p.meta.criteres?.plafond_par_secteur ?? 3} sociétés par secteur`),
      puces('Région', [['toutes', 'Toutes', liste.length], ...Object.entries(regions).filter(([k]) => nbRegions.has(k)).map(([k, v]) => [k, v, nbRegions.get(k)])],
        filtres.region, (c) => { filtres.region = c; filtres.secteur = 'tous'; rendre(); }),
      puces('Secteur', [['tous', 'Tous', parRegion.length], ...[...nbSecteurs].sort((a, b) => b[1] - a[1]).map(([k, n]) => [k, nomsSecteurs.get(k) ?? k, n])],
        filtres.secteur, (c) => { filtres.secteur = c; rendre(); }),
      visibles.length
        ? el('div', { class: 'pepites-liste' }, visibles.map((x) => ligne(x, d, nav)))
        : el('p', { class: 'fiche-verdict' }, 'Aucune société pour ce filtre.'),
    );
  };
  rendre();

  const crit = p.meta.criteres ?? {};
  return [
    entete,
    el('p', { class: 'macro-texte' },
      `${p.meta.candidats ?? p.liste.length} sociétés remplissent tous les critères ; ${p.liste.length} retenues dans les deux listes`,
      p.meta.holdings_exclues ? ` (${p.meta.holdings_exclues} holdings et sociétés d’investissement exclues)` : '',
      '. Note sur 100 ; l’ajustement de contexte (pays et cycle) est affiché à part.'),
    ...(p.meta.avertissements ?? []).map((a) => el('p', { class: 'pepites-avertissement', role: 'note' }, el('strong', {}, 'Concentration : '), a)),
    onglets,
    conteneur,
    el('details', { class: 'detail-repliable' },
      el('summary', {}, 'Critères (tous requis)'),
      el('ul', { class: 'contre-scenario' },
        el('li', {}, `Croissance du chiffre d’affaires d’au moins ${nombre(crit.croissance_ca_min ?? 10)} %`),
        el('li', {}, 'Marge opérationnelle en amélioration (bénéfice en hausse pour les financières)'),
        el('li', {}, 'Flux de trésorerie disponible positif (ROE > 10 % pour les financières)'),
        el('li', {}, `Dette nette / EBITDA d’au plus ${nombre(crit.dette_ebitda_max ?? 2, 1)}`),
        el('li', {}, `F-score de Piotroski d’au moins ${crit.fscore_min ?? 7}`),
        el('li', {}, `Valorisation au plus ${nombre(crit.valorisation_max_pct ?? 10)} % au-dessus de la médiane du secteur`),
        el('li', {}, 'Aucun signal d’alerte comptable (M-score de Beneish compris)'),
        crit.exclure_zscore_detresse !== false ? el('li', {}, 'Z-score d’Altman hors de la zone de détresse (sociétés non financières, quand il est calculable)') : null,
        crit.exclure_sommet_cycle !== false ? el('li', {}, 'Pas de sommet de cycle possible (bénéfice actuel au plus 1,5 fois sa moyenne sur 5 ans)') : null,
        el('li', {}, 'Holdings et sociétés d’investissement exclues (la décote sur l’actif net n’est pas mesurable avec des sources gratuites)'),
        el('li', {}, `Pépites : capitalisation de ${nombre((crit.cap_min_md ?? 0.3) * 1000)} M$ à ${nombre(crit.cap_max_md ?? 20)} Md$ et au plus ${crit.analystes_max ?? 8} analystes (quand Yahoo le fournit)`),
      )),
    el('p', { class: 'fraicheur' }, `Mis à jour le ${(p.meta.genere_le ?? '').slice(8, 10)}/${(p.meta.genere_le ?? '').slice(5, 7)}/${(p.meta.genere_le ?? '').slice(0, 4)} · Agent entreprises (règles ; guidance des communiqués lue par Gemini, citations vérifiées)`),
    el('p', { class: 'mention-legale' }, 'Liste de candidates à étudier : chaque fiche comporte une revue critique et des points à vérifier soi-même. Recommandations : avis indicatif généré automatiquement, sans prise en compte d’un profil ou d’une situation personnelle. Ne constitue pas un conseil en investissement.'),
  ];
}

function ligne(x, d, nav) {
  const pays = d.paysParCode.get(x.pays)?.nom ?? x.pays;
  const cles = Object.entries(x.cles ?? {}).slice(0, 3);
  const ctx = x.contexte?.ajustement ?? 0;
  const e = d.entrepriseParTicker?.get(x.ticker) ?? x;
  const bouton = el('button', { class: `ligne-pepite ${classeNote(x.note)}`, type: 'button', onclick: () => nav.ouvrirEntreprise(x.ticker),
    'aria-label': `${x.nom}, ${pays}, ${x.secteur_nom}, note ${x.note} sur 100, ajustement de contexte ${variation(ctx, 1, ' point')}` },
  el('div', { class: 'ligne-pepite-tete' },
    el('span', { class: 'ligne-pepite-nom' }, x.nom, x.guidance ? [' ', badgeGuidance(x.guidance.evolution, x.guidance.date)] : null),
    el('span', { class: 'ligne-pepite-note' }, nombre(x.note), el('small', {}, '/100'),
      el('small', { class: `ligne-pepite-ctx ${ctx > 0 ? 'hausse' : ctx < 0 ? 'baisse' : ''}` }, ` ${variation(ctx, 1, '')} contexte`)),
  ),
  el('div', { class: 'ligne-pepite-info' }, [x.ticker, pays, x.secteur_nom, x.capitalisation_md != null ? `${nombre(x.capitalisation_md, x.capitalisation_md < 10 ? 1 : 0)} Md$` : null,
    x.analystes != null ? `${x.analystes} analyste${x.analystes > 1 ? 's' : ''}` : null, `confiance ${x.confiance}`].filter(Boolean).join(' · ')),
  el('div', { class: 'ligne-pepite-cles' }, cles.map(([k, v]) => el('span', {}, el('small', {}, LIBELLES_CLES[k] ?? k), ' ', el('strong', { class: 'mono' }, v)))),
  x.recommandation ? el('div', { class: 'ligne-reco' }, el('small', {}, 'Non détenu'), pastilleReco(x.recommandation),
    el('small', {}, 'Détenu'), pastilleReco(x.recommandation, true)) : null,
  el('div', { class: 'ligne-pepite-verdict' }, x.verdict),
  );
  // Mini-graphique sur 12 mois, chargé quand la fiche apparaît à l'écran
  return el('div', { class: `ligne-pepite-bloc ${classeNote(x.note)}` }, bouton,
    graphiqueMini({ yahoo: x.ticker, place: e.place ?? x.place, historique: historiqueEntreprise(e) }));
}
