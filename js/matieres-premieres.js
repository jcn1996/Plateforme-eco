/* ==========================================================================
   Écran « Matières premières » (données réelles de l'agent matières premières,
   data/matieres_premieres.json, chargé à la première ouverture de l'écran).
   - en haut : synthèse par famille (métaux précieux, métaux industriels, énergie, agricoles) ;
   - puis une ligne par matière première : cours, variation 1 mois et 12 mois, mini-graphique,
     note, verdict (badge de couleur), confiance ;
   - toucher une ligne ouvre sa fiche : sous-notes, courbe des prix à terme, positionnement CFTC,
     stocks par rapport à la moyenne sur 5 ans, arguments, moyens de s'exposer, sources et dates,
     et le bouton « Voir les pays producteurs » (surbrillance sur le globe).
   ========================================================================== */

import { el, svg, nombre, variation } from './outils.js';

const FICHIER = 'data/matieres_premieres.json';
let cache; // undefined : pas encore chargé ; null : indisponible

/** Charge data/matieres_premieres.json (une fois) ; null si le fichier manque. */
export async function chargerMatieres(forcer = false) {
  if (cache !== undefined && !forcer) return cache;
  try {
    const r = await fetch(FICHIER, { cache: 'no-cache' });
    if (!r.ok) { cache = null; return cache; }
    const json = await r.json();
    cache = json?.donnees ? { meta: json.meta ?? {}, ...json.donnees } : null;
  } catch {
    cache = null;
  }
  return cache;
}
export const matieresChargees = () => cache;

/* ------------------------------------------------------------------ outils */

const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
function dateFr(d) {
  if (!d) return 'date inconnue';
  const s = String(d);
  if (s.length === 7) return `${MOIS[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)}`;
  return `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
}
const titre = (texte, complement) => el('h3', { class: 'section-titre' }, texte, complement ? el('small', {}, complement) : null);
const source = (texte) => el('p', { class: 'macro-source' }, texte);
const CLASSE_VERDICT = {
  'Surpondérer': 'mp-verdict--sur', 'Neutre (biais positif)': 'mp-verdict--neutre mp-verdict--biais-pos',
  'Neutre': 'mp-verdict--neutre', 'Neutre (biais négatif)': 'mp-verdict--neutre mp-verdict--biais-neg', 'Sous-pondérer': 'mp-verdict--sous',
};
const badgeVerdict = (v) => el('span', { class: `mp-verdict ${CLASSE_VERDICT[v] ?? ''}` }, v ?? 'n. d.');
const classeNoteMp = (n) => (n == null ? '' : n >= 60 ? 'hausse' : n <= 40 ? 'baisse' : '');
const decimales = (v) => (v == null ? 0 : Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 1 : 2);
const varTexte = (x) => (x == null ? el('span', { class: 'mono' }, 'n. d.') : el('span', { class: `mono ${x >= 0 ? 'hausse' : 'baisse'}` }, variation(x, 1)));

/** Mini-graphique (ligne) d'une série [[date, valeur]]. */
function sparkline(serie, { L = 96, H = 30, classe = 'mp-spark' } = {}) {
  if (!serie?.length) return el('span', { class: classe });
  const vals = serie.map((p) => p[1]);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const x = (i) => (i / Math.max(1, serie.length - 1)) * (L - 2) + 1;
  const y = (v) => H - 2 - ((v - mn) / (mx - mn || 1)) * (H - 4);
  const d = serie.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  const hausse = vals.at(-1) >= vals[0];
  return svg('svg', { class: classe, viewBox: `0 0 ${L} ${H}`, width: L, height: H, 'aria-hidden': 'true' },
    svg('path', { d, class: `mp-spark-ligne ${hausse ? 'mp-spark--hausse' : 'mp-spark--baisse'}` }));
}

/* ------------------------------------------------------------------ liste */

function carteFamille(f) {
  return el('div', { class: 'carte mp-famille' },
    el('div', { class: 'mp-famille-tete' }, el('span', { class: 'mp-famille-nom' }, f.nom), badgeVerdict(f.verdict)),
    el('div', { class: `mp-famille-note mono ${classeNoteMp(f.note)}` }, f.note == null ? 'n. d.' : `${nombre(f.note, 0)}/100`),
    el('div', { class: 'mp-famille-texte' }, f.texte),
  );
}

function ligneMatiere(m, ouvrir) {
  return el('button', { class: 'mp-ligne', type: 'button', onclick: () => ouvrir(m.cle), 'aria-label': `${m.nom} : ${m.verdict}, note ${nombre(m.note ?? 0, 0)} sur 100` },
    el('span', { class: 'mp-ligne-nom' }, m.nom, m.indirect ? el('small', {}, 'indicateur indirect') : null,
      el('small', { class: 'mono' }, m.cours == null ? 'n. d.' : `${nombre(m.cours, decimales(m.cours))} ${m.unite ?? ''}`),
      // Téléphone : variations sous le nom (la colonne dédiée est masquée)
      el('small', { class: 'mp-ligne-var-court' }, '1 m ', varTexte(m.variation_1m), ' · 12 m ', varTexte(m.variation_12m))),
    el('span', { class: 'mp-ligne-var' }, el('small', {}, '1 mois'), varTexte(m.variation_1m), el('small', {}, '12 mois'), varTexte(m.variation_12m)),
    sparkline(m.serie),
    el('span', { class: 'mp-ligne-verdict' },
      el('span', { class: `mono mp-ligne-note ${classeNoteMp(m.note)}` }, m.note == null ? 'n. d.' : nombre(m.note, 0)),
      badgeVerdict(m.verdict),
      el('small', {}, `confiance ${m.confiance}`)),
  );
}

export function ecranMatieres(donnees, nav, cle) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Agent matières premières · horizon de 3 à 12 mois'),
    el('h2', { class: 'fiche-titre' }, 'Matières premières'),
  );
  if (donnees === undefined) return [entete, el('p', { class: 'sante-ligne' }, 'Chargement…')];
  if (!donnees) {
    return [entete, el('p', { class: 'sante-ligne' }, 'Données de l’agent matières premières indisponibles (data/matieres_premieres.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  }
  if (cle) {
    const m = donnees.matieres.find((x) => x.cle === cle);
    if (m) return ficheMatiere(m, donnees, nav);
  }
  const familles = donnees.familles ?? [];
  return [
    entete,
    el('section', {},
      titre('Synthèse par famille', 'note moyenne et verdict de famille'),
      el('div', { class: 'mp-familles' }, familles.map(carteFamille)),
    ),
    ...familles.map((f) => el('section', {},
      titre(f.nom),
      el('div', { class: 'mp-liste' }, donnees.matieres.filter((m) => m.famille === f.cle).map((m) => ligneMatiere(m, (c) => nav.ouvrir({ type: 'matieres', id: c })))),
    )),
    el('section', {},
      titre('Publications prises en compte'),
      el('ul', { class: 'mp-publications' }, (donnees.publications ?? []).map((p) => el('li', {},
        el('strong', {}, p.source), ` · ${p.rythme} · `,
        p.derniere_donnee ? `dernière donnée : ${dateFr(p.derniere_donnee)}` : 'non disponible (source absente ou non configurée)'))),
      source(donnees.methode ?? ''),
    ),
    el('p', { class: 'fraicheur' }, `Mis à jour le ${dateFr(donnees.meta?.genere_le)} · Agent matières premières (règles, sans IA)`),
    el('p', { class: 'mention-legale' }, donnees.avertissement ?? 'Ne constitue pas un conseil en investissement.'),
  ];
}

/* ------------------------------------------------------------------ fiche */

const ORDRE = ['tendance', 'courbe', 'stocks', 'positionnement', 'macro', 'geopolitique', 'flux', 'niveau'];
const LIBELLES = { tendance: 'Tendance et momentum', courbe: 'Structure de la courbe', stocks: 'Stocks par rapport à la normale', positionnement: 'Positionnement des investisseurs',
  macro: 'Moteurs macro', geopolitique: 'Contexte géopolitique', flux: 'Flux des ETF', niveau: 'Niveau historique' };

function sousNotes(m) {
  return el('ul', { class: 'mp-sous-notes' }, ORDRE.map((k) => {
    const s = m.sous_notes?.[k];
    const note = s?.note;
    return el('li', {},
      el('div', { class: 'mp-sous-ligne' }, el('span', {}, LIBELLES[k]),
        el('span', { class: `mono ${classeNoteMp(note)}` }, note == null ? 'n. d.' : `${note}/100`)),
      el('div', { class: 'mp-barre' }, el('span', { style: { width: `${note ?? 0}%` }, class: classeNoteMp(note) })),
      el('div', { class: 'mp-sous-texte' }, s ? s.texte : 'Donnée non disponible pour cette matière première : pondération répartie sur les autres sous-notes.'),
    );
  }));
}

/** Courbe des prix à terme : prix par échéance. */
function graphiqueCourbe(c, unite) {
  const pts = c?.points ?? [];
  if (pts.length < 2) return el('p', { class: 'macro-source' }, 'Courbe des prix à terme indisponible.');
  const L = Math.round(Math.min(640, Math.max(300, innerWidth - 58))), H = 170;
  const m = { haut: 14, droite: 14, bas: 26, gauche: 52 };
  const vals = pts.map((p) => p.prix);
  const mn = Math.min(...vals), mx = Math.max(...vals), marge = (mx - mn || mx * 0.02) * 0.15;
  const x = (i) => m.gauche + (i / (pts.length - 1)) * (L - m.gauche - m.droite);
  const y = (v) => H - m.bas - ((v - (mn - marge)) / (mx - mn + 2 * marge)) * (H - m.haut - m.bas);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.prix).toFixed(1)}`).join('');
  const axe = svg('g', { class: 'axe' },
    ...[mn, mx].map((v) => svg('text', { x: m.gauche - 6, y: y(v) + 3, 'text-anchor': 'end' }, nombre(v, decimales(v)))),
    // Au plus 4 ou 5 échéances écrites (lisible sur téléphone) : la première, la dernière et quelques-unes entre les deux
    ...pts.map((p, i) => {
      const pas = Math.ceil(pts.length / 4), dernier = pts.length - 1;
      if (i !== dernier && (i % pas || dernier - i < pas)) return null;
      return svg('text', { x: x(i), y: H - 8, 'text-anchor': i === 0 ? 'start' : i === dernier ? 'end' : 'middle' }, `${MOIS[Number(p.echeance.slice(5, 7)) - 1]} ${p.echeance.slice(2, 4)}`);
    }).filter(Boolean));
  const grille = svg('g', { class: 'grille' }, ...[mn, mx].map((v) => svg('line', { x1: m.gauche, x2: L - m.droite, y1: y(v), y2: y(v) })));
  const points = pts.map((p, i) => svg('circle', { cx: x(i), cy: y(p.prix), r: 3.5, class: 'mp-point' }, svg('title', {}, `${p.symbole} : ${nombre(p.prix, decimales(p.prix))} ${unite ?? ''} (${dateFr(p.date)})`)));
  return el('div', { class: 'graphique' },
    svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img', 'aria-label': `Courbe des prix à terme : ${c.structure}` }, grille, axe,
      svg('path', { d, class: `serie mp-courbe--${c.structure}` }), ...points));
}

/** Barres de la position nette des gérants (52 dernières semaines). */
function graphiquePositions(p) {
  const h = p?.historique ?? [];
  if (!h.length) return null;
  const L = Math.round(Math.min(640, Math.max(300, innerWidth - 58))), H = 120, m = { haut: 8, bas: 18, gauche: 8, droite: 8 };
  const vals = h.map((x) => x[1]);
  const ext = Math.max(...vals.map(Math.abs)) || 1;
  const zero = m.haut + (H - m.haut - m.bas) / 2;
  const larg = (L - m.gauche - m.droite) / h.length;
  const barres = h.map((x, i) => {
    const haut = (Math.abs(x[1]) / ext) * ((H - m.haut - m.bas) / 2);
    return svg('rect', { x: m.gauche + i * larg + 0.5, width: Math.max(1, larg - 1), y: x[1] >= 0 ? zero - haut : zero, height: Math.max(0.5, haut),
      class: x[1] >= 0 ? 'mp-barre-pos' : 'mp-barre-neg' }, svg('title', {}, `${dateFr(x[0])} : ${nombre(x[1], 0)} contrats`));
  });
  return el('div', { class: 'graphique' }, svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img', 'aria-label': 'Position nette des gérants sur 52 semaines' },
    svg('line', { x1: m.gauche, x2: L - m.droite, y1: zero, y2: zero, class: 'mp-ligne-zero' }), ...barres,
    svg('text', { x: m.gauche, y: H - 4, class: 'mp-axe-texte' }, dateFr(h[0][0])),
    svg('text', { x: L - m.droite, y: H - 4, 'text-anchor': 'end', class: 'mp-axe-texte' }, dateFr(h.at(-1)[0]))));
}

function blocStocks(s) {
  if (!s) return el('p', { class: 'macro-texte' }, 'Pas de donnée de stocks pour cette matière première (EIA : pétrole et gaz américains, si la clé est configurée ; USDA : blé, maïs, soja).');
  if (s.type === 'eia') {
    return el('div', { class: 'mp-stocks' }, s.series.map((x) => el('div', { class: 'carte mp-stock' },
      el('div', { class: 'macro-marche-nom' }, x.libelle),
      el('div', { class: 'macro-marche-valeur mono' }, `${nombre(x.valeur, 1)} ${x.unite}`),
      el('div', { class: 'macro-marche-var' }, el('span', {}, 'moyenne 5 ans'), el('span', { class: 'mono' }, `${nombre(x.moyenne_5_ans, 1)} ${x.unite}`)),
      el('div', { class: 'macro-marche-var' }, el('span', {}, 'écart'), varTexte(x.ecart_pct)),
      el('div', { class: 'macro-marche-var' }, el('span', {}, 'semaine'), el('span', { class: 'mono' }, `${variation(x.variation_hebdo, 1, '')} ${x.unite}`)),
      sparkline(x.historique, { L: 140, H: 32 }),
      el('div', { class: 'macro-source' }, `Semaine du ${dateFr(x.date)}${x.choc ? ' · variation inhabituelle' : ''}`),
    )));
  }
  return el('div', {},
    el('p', { class: 'macro-texte' }, s.texte + '.'),
    s.historique?.length ? el('div', { class: 'mp-usda' }, el('small', {}, 'Stocks / consommation, % (campagnes passées)'), sparkline(s.historique, { L: 220, H: 40 })) : null,
    s.verification === 'concordant' || s.verification === 'divergent'
      ? source(`${s.verification === 'concordant' ? 'Vérifié' : 'Divergence'} : ${s.note_verification}.`) : null);
}

function blocSupports(m, nav) {
  return el('div', {},
    el('ul', { class: 'mp-supports' }, (m.supports ?? []).map((s) => el('li', {}, el('strong', {}, s.type), ` : ${s.detail}`, s.cout_roulement ? el('small', {}, s.cout_roulement) : null))),
    m.societes?.length ? el('div', {},
      el('p', { class: 'macro-texte' }, 'Producteurs déjà analysés par l’agent entreprises :'),
      el('div', { class: 'mp-societes' }, m.societes.map((s) => el('button', {
        class: 'mp-societe', type: 'button', disabled: !nav.entrepriseExiste?.(s.ticker),
        onclick: () => nav.ouvrirEntreprise(s.ticker),
      }, el('span', {}, s.nom, el('small', {}, s.ticker)), el('span', { class: `mono ${classeNoteMp(s.note)}` }, s.note == null ? '' : `${s.note}/100`),
      el('small', {}, s.recommandation ?? ''), s.deja_detenue ? el('small', { class: 'mp-deja' }, 'déjà suivie') : null)))) : null,
    m.double_exposition ? el('p', { class: 'mp-alerte' }, m.double_exposition) : null,
    el('p', { class: 'mention-legale' }, 'À titre informatif : types de supports et exemples, sans recommandation de produit.'));
}

function ficheMatiere(m, donnees, nav) {
  const s = m.sous_notes ?? {};
  const p = s.positionnement;
  const suivis = (m.producteurs ?? []).filter((x) => x.suivi);
  return [
    el('header', {},
      el('div', { class: 'fiche-surtitre' }, `${donnees.familles.find((f) => f.cle === m.famille)?.nom ?? ''} · ${m.symbole}`),
      el('h2', { class: 'fiche-titre' }, m.nom),
      m.mention ? el('p', { class: 'mp-alerte' }, `Mention : ${m.mention}.`) : null,
    ),
    // Recommandation non retenue (confiance « faible » ou moins de deux signaux concordants)
    m.verdict_non_retenu ? el('p', { class: 'mp-alerte' }, `${m.verdict_non_retenu}.`) : null,
    el('div', { class: 'mp-resume' },
      el('div', {}, el('small', {}, 'Cours'), el('strong', { class: 'mono' }, m.cours == null ? 'n. d.' : `${nombre(m.cours, decimales(m.cours))} ${m.unite ?? ''}`), el('small', {}, dateFr(m.date_cours))),
      el('div', {}, el('small', {}, 'Note'), el('strong', { class: `mono ${classeNoteMp(m.note)}` }, m.note == null ? 'n. d.' : `${nombre(m.note, 0)}/100`),
        m.precedent?.note != null ? el('small', {}, `précédente ${nombre(m.precedent.note, 0)}`) : null),
      el('div', {}, el('small', {}, 'Verdict'), badgeVerdict(m.verdict), el('small', {}, `${m.horizon} · confiance ${m.confiance}`)),
    ),
    sparkline(m.serie, { L: 320, H: 60, classe: 'mp-spark mp-spark--grand' }),
    suivis.length ? el('button', { class: 'bouton bouton--accent mp-producteurs-btn', type: 'button', onclick: () => nav.voirProducteurs(m) }, 'Voir les pays producteurs') : null,
    el('p', { class: 'macro-source' }, 'Principaux producteurs : ', (m.producteurs ?? []).map((x) => `${x.rang}. ${x.nom}${x.suivi ? '' : ' (non suivi)'}`).join(', '),
      m.note_producteurs ? ` — ${m.note_producteurs}` : ''),

    el('section', {}, titre('Sous-notes', 'au-dessus de 50 : favorable à une exposition'), sousNotes(m)),
    el('section', {}, titre('Arguments pour'), el('ul', { class: 'contre-scenario' }, m.arguments_pour.map((t) => el('li', {}, t)))),
    el('section', {}, titre('Arguments contre'), el('ul', { class: 'contre-scenario' }, m.arguments_contre.map((t) => el('li', {}, t)))),
    el('section', {}, titre('Ce qui pourrait me donner tort'), el('p', { class: 'macro-texte' }, m.ce_qui_pourrait_me_donner_tort),
      el('p', { class: 'macro-texte' }, el('strong', {}, 'Le verdict serait invalidé par :')),
      el('ul', { class: 'contre-scenario' }, m.invalidations.map((t) => el('li', {}, t)))),

    el('section', {}, titre('Courbe des prix à terme', s.courbe ? `${s.courbe.structure} · roulement ${variation(s.courbe.roulement_pct_an, 1)} par an` : null),
      graphiqueCourbe(s.courbe, m.unite),
      source('Contango : prix futurs plus élevés (marché détendu, coût de roulement pour les supports à base de contrats). Backwardation : prix futurs plus bas (marché tendu).')),
    el('section', {}, titre('Positionnement CFTC', p ? `percentile ${nombre(p.percentile, 0)} sur 3 ans` : null),
      p ? el('p', { class: 'macro-texte' }, p.texte + '.') : el('p', { class: 'macro-texte' }, 'Pas de rapport CFTC pour ce marché.'),
      graphiquePositions(p),
      p ? source(`${p.marche ?? ''} · positions du ${dateFr(p.date)} · managed money (gérants), position nette = acheteurs − vendeurs.`) : null),
    el('section', {}, titre('Stocks', s.stocks?.type === 'eia' ? 'par rapport à la moyenne sur 5 ans' : null), blocStocks(s.stocks)),
    el('section', {}, titre('Moyens de s’exposer'), blocSupports(m, nav)),
    el('section', {}, titre('Sources et dates'),
      el('ul', { class: 'mp-publications' }, m.sources.map((x) => el('li', {}, el('strong', {}, x.sous_note), ` : ${x.source}${x.date ? ` (${dateFr(x.date)})` : ''}`)))),
    el('p', { class: 'fraicheur' }, `Mis à jour le ${dateFr(donnees.meta?.genere_le)} · Agent matières premières (règles, sans IA)`),
    el('p', { class: 'mention-legale' }, donnees.avertissement ?? ''),
  ];
}

/** Métrique temporaire du globe : principaux producteurs suivis, plus intenses selon le rang. */
export function metriqueProducteurs(m) {
  const rangs = new Map((m.producteurs ?? []).filter((p) => p.suivi).map((p) => [p.code, p.rang]));
  return {
    cle: 'producteurs',
    lire: (p) => {
      const r = rangs.get(p.code);
      if (!r) return null;
      const intensite = Math.max(0.35, 1 - (r - 1) * 0.07);
      const c = [0xff, 0xc0, 0x62].map((v, i) => Math.round(v * intensite + [0x0a, 0x14, 0x28][i] * (1 - intensite)));
      return { note: 100 - r * 4, texte: `n° ${r}`, couleur: (c[0] << 16) | (c[1] << 8) | c[2] };
    },
  };
}
