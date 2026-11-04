/* ==========================================================================
   Écran « Géopolitique » (agent géopolitique, data/geopolitique.json)
   - fil des événements récents classés par gravité : résumé (faits sourcés),
     pays, actifs touchés et sens de l'impact (interprétation), confiance,
     « Ce qui pourrait me donner tort », sources cliquables ;
   - filtres par région et par catégorie ;
   - indice mondial de risque géopolitique (GPR) sur 12 mois, en petit graphique.
   Aussi : rubrique « Géopolitique » de la fiche pays et filtre du globe
   « Risque géopolitique » (score /100 : plus il est haut, plus le risque est élevé).
   ========================================================================== */

import { el, svg, nombre } from './outils.js';

const FICHIER = 'data/geopolitique.json';
export const SEUIL_RISQUE_ELEVE = 60;
export const SEUIL_RISQUE_MODERE = 35;

/** Charge data/geopolitique.json ; null si absent (l'appli continue). */
export async function chargerGeopolitique() {
  try {
    const r = await fetch(FICHIER, { cache: 'no-cache' });
    if (!r.ok) return null;
    const json = await r.json();
    return json?.donnees ? { meta: json.meta ?? {}, ...json.donnees } : null;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ globe */

/** Niveau de couleur du globe : rouge pour un risque élevé, vert pour un risque faible. */
export function niveauRisque(score) {
  if (score >= SEUIL_RISQUE_ELEVE) return 'defavorable';
  if (score >= SEUIL_RISQUE_MODERE) return 'neutre';
  return 'attractif';
}

/** Lecture de la métrique « Risque géopolitique » pour un pays (format du globe). */
export function lireRisque(geo, code) {
  const s = geo?.pays?.[code];
  if (!s || s.score == null) return null;
  return { valeur: s.score, note: s.score, niveau: niveauRisque(s.score), texte: nombre(s.score), unite: '/100' };
}

export const METRIQUE_RISQUE = { cle: 'risque_geo', libelle: 'Risque géopolitique', court: 'Risque géo.', source: 'geopolitique' };

/* ------------------------------------------------------------------ outils */

function dateHeure(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function dateCourte(iso) {
  return iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '';
}

const SENS = { hausse: { symbole: '▲', libelle: 'hausse', classe: 'hausse' }, baisse: { symbole: '▼', libelle: 'baisse', classe: 'baisse' }, incertain: { symbole: '◆', libelle: 'incertain', classe: 'geo-incertain' } };

/** Renvois vers les sources d'une affirmation : [1] [2] (numéros des sources de l'événement). */
function renvois(urls, sources) {
  return (urls ?? []).map((u) => {
    const i = sources.findIndex((s) => s.url === u);
    const s = sources[i];
    return el('a', { class: 'geo-renvoi', href: u, target: '_blank', rel: 'noopener noreferrer', title: s ? `${s.domaine} : ${s.titre}` : u },
      `[${i >= 0 ? i + 1 : '↗'}]`);
  });
}

function badgeGravite(g) {
  return el('span', { class: `geo-gravite geo-gravite--${g}`, title: `Gravité ${g} sur 5` }, `${g}/5`);
}

function badgeScore(s) {
  return el('span', { class: `geo-score note--${niveauRisque(s.score)}` }, el('strong', { class: 'mono' }, nombre(s.score)), '/100');
}

function variationTexte(v) {
  if (v == null) return 'variation sur 7 j : n. d.';
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${nombre(Math.abs(v), 1)} pt sur 7 j`;
}

/* ------------------------------------------------------------------ graphique GPR */

function graphiqueGpr(gpr) {
  const serie = gpr?.serie ?? [];
  if (serie.length < 2) return el('p', { class: 'macro-source' }, 'Indice indisponible.');
  const L = Math.round(Math.min(560, Math.max(280, innerWidth - 58))), H = 96;
  const m = { haut: 8, droite: 44, bas: 18, gauche: 8 };
  const vals = serie.map((p) => p[1]);
  const min = Math.min(...vals, 100) * 0.95, max = Math.max(...vals) * 1.05;
  const t0 = Date.parse(serie[0][0]), t1 = Date.parse(serie.at(-1)[0]);
  const x = (d) => m.gauche + ((Date.parse(d) - t0) / (t1 - t0)) * (L - m.gauche - m.droite);
  const y = (v) => H - m.bas - ((v - min) / (max - min)) * (H - m.haut - m.bas);
  const chemin = serie.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  const dernier = serie.at(-1);
  const axe = svg('g', { class: 'axe' },
    svg('text', { x: m.gauche, y: H - 4 }, dateCourte(serie[0][0]).slice(3)),
    svg('text', { x: L - m.droite, y: H - 4, 'text-anchor': 'end' }, dateCourte(dernier[0]).slice(3)));
  const reference = svg('line', { class: 'ligne-zero', x1: m.gauche, x2: L - m.droite, y1: y(100), y2: y(100) });
  const dessin = svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img',
    'aria-label': `Indice de risque géopolitique sur 12 mois : ${nombre(dernier[1])} au ${dateCourte(dernier[0])}` },
  svg('g', { class: 'grille' }, reference),
  svg('text', { class: 'geo-ref', x: L - m.droite + 4, y: y(100) + 3 }, '100'),
  axe,
  svg('path', { class: 'serie', d: chemin, stroke: 'var(--serie-indice)' }),
  svg('circle', { cx: x(dernier[0]), cy: y(dernier[1]), r: 3.5, fill: 'var(--serie-indice)' }),
  svg('text', { class: 'etiquette-serie', x: x(dernier[0]) + 6, y: y(dernier[1]) - 4 }, nombre(dernier[1])));
  return el('div', { class: 'graphique geo-graphique' }, dessin);
}

/* ------------------------------------------------------------------ événement */

function carteEvenement(e) {
  const srcs = e.sources ?? [];
  return el('article', { class: `carte geo-evenement geo-evenement--${e.gravite}` },
    el('div', { class: 'geo-evenement-tete' },
      badgeGravite(e.gravite),
      el('div', {},
        el('h3', { class: 'geo-titre' }, e.titre,
          // Titre d'origine (sans titre français de Gemini) : sa langue et « non traduit »
          e.mention ? el('span', { class: 'geo-mention' }, ` ${e.titre_langue ? `(${e.titre_langue}) · ` : ''}${e.mention}`) : null),
        el('div', { class: 'geo-meta' },
          e.theme ? el('span', { class: 'geo-theme', title: e.theme_confirme ? 'Regroupement confirmé par Gemini' : 'Regroupement par règles (Gemini indisponible)' },
            `Thème en cours · ${e.nb_evenements} faits · `) : null,
          el('span', { class: 'geo-categorie' }, e.categorie_libelle),
          ` · ${e.pays_noms?.length ? e.pays_noms.join(', ') : 'pays non déterminés'}`,
          // Pays seulement lieu d'une négociation ou d'un sommet : affiché à part
          e.lieux_noms?.length ? el('span', { class: 'geo-lieu' }, ` · lieu : ${e.lieux_noms.join(', ')}`) : null,
          ` · ${dateHeure(e.dernier)}`,
          e.ia ? null : el('span', { class: 'geo-sans-ia' }, 'sans IA'),
          e.ia && e.modele ? el('small', {}, ` · ${e.modele}`) : null)),
    ),
    e.resume?.length
      ? el('div', { class: 'geo-bloc' },
        el('div', { class: 'geo-etiquette' }, 'Faits'),
        el('p', { class: 'geo-texte' }, e.resume.flatMap((r) => [r.texte, ' ', ...renvois(r.sources, srcs), ' '])))
      : el('p', { class: 'geo-texte geo-texte--brut' }, `Événement repéré par ${e.nb_domaines} source${e.nb_domaines > 1 ? 's' : ''} distincte${e.nb_domaines > 1 ? 's' : ''} (${e.nb_articles} article${e.nb_articles > 1 ? 's' : ''})`,
        e.tonalite_gdelt != null ? ` ; tonalité GDELT des pays concernés : ${nombre(e.tonalite_gdelt, 1)}` : '',
        '. Gravité estimée par règles (au plus 3). Résumé non disponible : voir les sources.'),
    e.chronologie?.length > 1
      ? el('div', { class: 'geo-bloc' },
        el('div', { class: 'geo-etiquette' }, 'Chronologie'),
        el('ol', { class: 'geo-chronologie' }, e.chronologie.map((c) => el('li', {},
          el('span', { class: 'mono geo-chrono-date' }, dateHeure(c.date)),
          el('span', {}, badgeGravite(c.gravite), ' ',
            c.source ? el('a', { href: c.source, target: '_blank', rel: 'noopener noreferrer' }, c.titre) : c.titre,
            c.resume ? el('small', {}, ` — ${c.resume}`) : null)))))
      : null,
    e.actifs?.length
      ? el('div', { class: 'geo-bloc' },
        el('div', { class: 'geo-etiquette' }, 'Interprétation · actifs potentiellement touchés'),
        el('ul', { class: 'geo-actifs' }, e.actifs.map((a) => {
          const s = SENS[a.sens] ?? SENS.incertain;
          return el('li', {},
            el('span', { class: `geo-actif ${s.classe}` }, `${s.symbole} ${a.actif}`),
            el('span', { class: 'geo-actif-texte' }, `${s.libelle} — ${a.texte} `, ...renvois(a.sources, srcs)));
        })))
      : null,
    e.ia ? el('div', { class: 'geo-info' },
      e.horizon ? `Horizon : ${e.horizon}` : null, ` · confiance ${e.confiance}`,
      e.note_gravite ? ` · ${e.note_gravite}` : null) : null,
    e.contre?.length
      ? el('div', { class: 'geo-bloc' },
        el('div', { class: 'geo-etiquette' }, 'Ce qui pourrait me donner tort'),
        el('ul', { class: 'contre-scenario' }, e.contre.map((c) => el('li', {}, `${c.texte} `, ...renvois(c.sources, srcs)))))
      : null,
    el('details', { class: 'geo-sources' },
      el('summary', {}, `Sources (${srcs.length}${e.nb_domaines < srcs.length ? `, dont ${e.nb_domaines} indépendante${e.nb_domaines > 1 ? 's' : ''}` : ''}${e.officiel ? ', dont officielles' : ''})`),
      el('ol', {}, srcs.map((s) => el('li', {},
        el('a', { href: s.url, target: '_blank', rel: 'noopener noreferrer' }, s.titre),
        el('small', {}, ` ${s.domaine}${s.officiel ? ' · officielle' : ''} · ${dateHeure(s.date)}`))))),
  );
}

/* ------------------------------------------------------------------ écran */

const filtres = { region: 'toutes', categorie: 'toutes' };

function puces(options, actif, choisir, libelle) {
  return el('div', { class: 'geo-filtres', role: 'radiogroup', 'aria-label': libelle },
    options.map(([cle, texte]) => el('button', {
      class: 'puce', type: 'button', role: 'radio', 'aria-checked': String(cle === actif), onclick: () => choisir(cle),
    }, texte)));
}

export function ecranGeopolitique(geo) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Agent géopolitique · événements et impact possible sur les marchés'),
    el('h2', { class: 'fiche-titre' }, 'Géopolitique'),
  );
  if (!geo) {
    return [entete, el('p', { class: 'sante-ligne' }, 'Données de l’agent géopolitique indisponibles (data/geopolitique.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  }
  const liste = el('div', { class: 'geo-liste' });
  const zoneFiltres = el('div', {});
  const evenements = geo.evenements ?? [];
  const regions = Object.entries(geo.regions ?? {}).filter(([cle]) => evenements.some((e) => e.regions?.includes(cle)));
  const categories = Object.entries(geo.categories ?? {}).filter(([cle]) => evenements.some((e) => e.categorie === cle));

  const rendre = () => {
    zoneFiltres.replaceChildren(
      puces([['toutes', 'Toutes les régions'], ...regions], filtres.region, (c) => { filtres.region = c; rendre(); }, 'Filtrer par région'),
      puces([['toutes', 'Toutes les catégories'], ...categories], filtres.categorie, (c) => { filtres.categorie = c; rendre(); }, 'Filtrer par catégorie'),
    );
    const choisis = evenements.filter((e) => (filtres.region === 'toutes' || e.regions?.includes(filtres.region))
      && (filtres.categorie === 'toutes' || e.categorie === filtres.categorie));
    liste.replaceChildren(...(choisis.length
      ? choisis.map(carteEvenement)
      : [el('p', { class: 'sante-ligne' }, 'Aucun événement significatif pour ces filtres sur les 7 derniers jours.')]));
  };
  rendre();

  const gpr = geo.indices?.gpr, epu = geo.indices?.epu;
  const q = geo.quota_ia ?? {};
  const eleves = Object.values(geo.pays ?? {}).filter((p) => p.score != null).sort((a, b) => b.score - a.score).slice(0, 5);
  return [
    entete,
    geo.avertissement_ia ? el('p', { class: 'sante-alerte sante-alerte--retard' }, geo.avertissement_ia) : null,
    el('section', {},
      el('h3', { class: 'section-titre' }, 'Indice mondial de risque géopolitique', el('small', {}, '12 mois, moyenne sur 7 jours')),
      graphiqueGpr(gpr),
      gpr ? el('p', { class: 'macro-texte' }, `Moyenne sur 7 jours : ${nombre(gpr.moyenne_7j)} au ${dateCourte(gpr.date)} (valeur du jour : ${nombre(gpr.derniere)} ; moyenne sur 12 mois : ${nombre(gpr.moyenne_12m)}).`,
        epu ? ` Incertitude de politique économique (États-Unis) : ${nombre(epu.derniere)} au ${dateCourte(epu.date)} (moyenne 30 j : ${nombre(epu.moyenne_30j)}).` : '') : null,
      el('p', { class: 'macro-source' }, [gpr?.source, epu?.source].filter(Boolean).join(' · ')),
    ),
    eleves.length ? el('section', {},
      el('h3', { class: 'section-titre' }, 'Scores de risque les plus élevés', el('small', {}, '/100 · couleur du globe « Risque géopolitique »')),
      el('ul', { class: 'geo-scores' }, eleves.map((p) => el('li', {},
        el('span', {}, p.nom), badgeScore(p), el('small', {}, variationTexte(p.variation_7j))))),
    ) : null,
    el('section', {},
      el('h3', { class: 'section-titre' }, 'Événements récents', el('small', {}, '7 derniers jours, par gravité')),
      zoneFiltres,
      liste,
    ),
    el('p', { class: 'macro-source' }, geo.methode ?? ''),
    el('p', { class: 'fraicheur' }, `Mis à jour le ${dateHeure(geo.meta?.genere_le)} · ${geo.mode_ia === 'gemini' ? `analyse Gemini (${q.modele}), ${q.appels ?? 0}/${q.quota_jour ?? '?'} appels aujourd’hui` : 'version sans IA'}`),
    el('p', { class: 'mention-legale' }, 'Faits tirés des sources citées (chaque affirmation renvoie à au moins une source) ; impacts sur les marchés : interprétations. Ne constitue pas un conseil en investissement.'),
  ];
}

/* ------------------------------------------------------------------ fiche pays */

/** Rubrique « Géopolitique » de la fiche pays : score, variation, 3 derniers événements. */
export function sectionGeopolitiquePays(geo, code) {
  const s = geo?.pays?.[code];
  if (!s) return null;
  return el('section', {},
    el('h3', { class: 'section-titre' }, 'Géopolitique', el('small', {}, `mis à jour le ${dateHeure(geo.meta?.genere_le)}`)),
    s.score != null
      ? el('p', { class: 'geo-score-pays' }, 'Score de risque : ', badgeScore(s), ` · risque ${s.niveau} · ${variationTexte(s.variation_7j)}`)
      : el('p', { class: 'macro-texte' }, 'Score indisponible (données insuffisantes).'),
    s.derniers_evenements?.length
      ? el('ul', { class: 'geo-mini' }, s.derniers_evenements.map((e) => el('li', {},
        badgeGravite(e.gravite),
        el('div', {},
          e.source ? el('a', { href: e.source, target: '_blank', rel: 'noopener noreferrer' }, e.titre) : e.titre,
          e.mention ? el('span', { class: 'geo-mention' }, ` ${e.titre_langue ? `(${e.titre_langue}) · ` : ''}${e.mention}`) : null,
          el('small', {}, ` ${e.categorie_libelle} · ${dateHeure(e.date)}`),
          e.resume ? el('p', { class: 'geo-texte' }, e.resume) : null))))
      : el('p', { class: 'macro-texte' }, 'Aucun événement significatif récent.'),
    el('p', { class: 'macro-source' }, `Score /100 (plus il est haut, plus le risque est élevé) : événements récents pondérés par la gravité, tonalité GDELT, tendance sur 30 jours.${s.composantes_manquantes?.length ? ` Composantes manquantes : ${s.composantes_manquantes.join(', ')}.` : ''}`),
  );
}
