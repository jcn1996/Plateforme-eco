/* ==========================================================================
   Analyses à la demande et fiabilité des recommandations
   --------------------------------------------------------------------------
   - Bouton « Analyser une entreprise » : champ de saisie, puis ouverture d'une
     nouvelle issue GitHub « Analyse : <saisie> » (le workflow analyse-demande.yml
     fait l'analyse et répond dans l'issue).
   - Écran « Mes analyses » : data/analyses/index.json, plus les demandes en cours
     (issues ouvertes « Analyse : … » lues sur l'API publique de GitHub).
   - Fiche d'une analyse : data/analyses/<ticker>.json, lien direct #analyse-TICKER.
   - Écran « Fiabilité des recommandations » : data/historique/recommandations.json.
   ========================================================================== */

import { el, nombre, variation, classeNote } from './outils.js';
import { graphiqueMini } from './graphiques.js';

const DEPOT = 'jcn1996/Plateforme-eco';
const INDEX = 'data/analyses/index.json';
const HISTORIQUE = 'data/historique/recommandations.json';
const API_ISSUES = `https://api.github.com/repos/${DEPOT}/issues?state=open&per_page=30`;
const EXPLICATION = 'Touchez Submit pour lancer l’analyse, résultat dans 2 à 5 minutes.';

/** Nom du fichier d'une analyse (même règle que l'agent : caractères hors [A-Za-z0-9._-] remplacés par « _ »). */
export function fichierAnalyse(ticker) {
  return `data/analyses/${String(ticker).replace(/[^A-Za-z0-9._-]/g, '_')}.json`;
}

/** Adresse de la nouvelle issue GitHub préremplie. */
export function urlNouvelleAnalyse(saisie) {
  const titre = `Analyse : ${saisie.trim()}`;
  const corps = `${EXPLICATION}\n\nLa réponse (note, verdict, recommandation, indicateurs clés, risques) sera publiée ici en commentaire, puis l’issue sera fermée.`;
  return `https://github.com/${DEPOT}/issues/new?title=${encodeURIComponent(titre)}&body=${encodeURIComponent(corps)}`;
}

async function lireJson(chemin) {
  const r = await fetch(chemin, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${chemin} : ${r.status}`);
  return r.json();
}

/* ------------------------------------------------------------------ données */

/** Index des analyses à la demande ; liste vide si le fichier manque. */
export async function chargerAnalyses() {
  try {
    const j = await lireJson(INDEX);
    return { meta: j.meta ?? {}, liste: Array.isArray(j.donnees) ? j.donnees : [] };
  } catch {
    return { meta: {}, liste: [] };
  }
}

/** Demandes en cours : issues ouvertes « Analyse : … » (null si l'API est injoignable). */
export async function chargerEnCours() {
  try {
    const r = await fetch(API_ISSUES, { headers: { Accept: 'application/vnd.github+json' } });
    if (!r.ok) return null;
    return (await r.json())
      .filter((i) => !i.pull_request && /^\s*analyse\s*:/i.test(i.title ?? ''))
      .map((i) => ({ numero: i.number, saisie: i.title.replace(/^\s*analyse\s*:\s*/i, '').trim(), date: i.created_at, url: i.html_url }));
  } catch {
    return null;
  }
}

/** Fiche complète d'une analyse (ou null). */
export async function chargerAnalyse(ticker) {
  try {
    const j = await lireJson(fichierAnalyse(ticker));
    return j.donnees ? { ...j.donnees, meta: j.meta, analyseDemande: true } : null;
  } catch {
    return null;
  }
}

/** Historique des recommandations (ou null). */
export async function chargerRecommandations() {
  try {
    const j = await lireJson(HISTORIQUE);
    return { meta: j.meta ?? {}, liste: j.donnees ?? [] };
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ bouton et dialogue */

let dialogue = null;

export function ouvrirDialogue(texteInitial = '') {
  if (!dialogue) {
    const champ = el('input', { type: 'text', class: 'analyse-champ', placeholder: 'Ticker ou nom : ASML, MC.PA, 7203.T, Hermès',
      autocomplete: 'off', autocapitalize: 'characters', spellcheck: 'false', maxlength: '60', 'aria-label': 'Société à analyser' });
    const erreur = el('p', { class: 'analyse-erreur', hidden: true }, 'Saisir un ticker ou un nom de société.');
    const valider = (e) => {
      e?.preventDefault();
      const saisie = champ.value.trim();
      if (!saisie) { erreur.hidden = false; champ.focus(); return; }
      window.open(urlNouvelleAnalyse(saisie), '_blank', 'noopener');
      dialogue.close();
    };
    dialogue = el('dialog', { class: 'dialogue-analyse', 'aria-labelledby': 'dialogue-analyse-titre' },
      el('form', { method: 'dialog', onsubmit: valider },
        el('h3', { id: 'dialogue-analyse-titre' }, 'Analyser une entreprise'),
        el('p', { class: 'analyse-aide' }, 'Même grille que l’agent entreprises : note, verdict, recommandation, indicateurs clés, risques, rang dans le secteur. '
          + 'La demande ouvre une issue GitHub (compte propriétaire du dépôt requis).'),
        champ, erreur,
        el('p', { class: 'analyse-explication' }, 'Sur la page GitHub qui s’ouvre : ', el('strong', {}, EXPLICATION)),
        el('div', { class: 'analyse-actions' },
          el('button', { type: 'button', class: 'bouton', onclick: () => dialogue.close() }, 'Annuler'),
          el('button', { type: 'submit', class: 'bouton bouton--accent' }, 'Préparer la demande'),
        ),
      ));
    dialogue.champ = champ;
    dialogue.erreur = erreur;
    document.body.append(dialogue);
  }
  dialogue.champ.value = texteInitial;
  dialogue.erreur.hidden = true;
  if (typeof dialogue.showModal === 'function') dialogue.showModal(); else dialogue.setAttribute('open', '');
  requestAnimationFrame(() => dialogue.champ.focus());
}

/** Bouton « Analyser une entreprise » (saisie préremplie facultative). */
export function boutonAnalyser(texteInitial = '', libelle = 'Analyser une entreprise') {
  return el('button', { type: 'button', class: 'bouton bouton--accent bouton-analyser', onclick: () => ouvrirDialogue(texteInitial) },
    el('span', { 'aria-hidden': 'true' }, '＋ '), libelle);
}

/* ------------------------------------------------------------------ écran « Mes analyses » */

function dateHeure(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export function pastilleReco(r, detenu = false) {
  if (!r) return null;
  const v = detenu ? r.d : r.n;
  const sens = { Acheter: 'pos', Renforcer: 'pos', 'Acheter sur repli': 'mi', Attendre: 'neutre', Conserver: 'neutre', Alléger: 'mi-neg', Éviter: 'neg', Vendre: 'neg' }[v] ?? 'neutre';
  return el('span', { class: `pastille-reco pastille-reco--${sens}`, title: detenu ? 'Si détenu' : 'Si non détenu' }, v);
}

/** Clôtures hebdomadaires d'une analyse à la demande (graphique simple). */
function historiqueAnalyse(ticker) {
  return async () => (await chargerAnalyse(ticker))?.cours_hebdo ?? null;
}

function ligneAnalyse(a, ouvrir) {
  const bouton = el('button', { type: 'button', class: `ligne-pepite ${classeNote(a.note)}`, onclick: () => ouvrir(a.ticker),
    'aria-label': `${a.nom}, note ${a.note} sur 100, ${a.recommandation?.n ?? ''}` },
  el('div', { class: 'ligne-pepite-tete' },
    el('span', { class: 'ligne-pepite-nom' }, a.nom),
    el('span', { class: 'ligne-pepite-note' }, nombre(a.note), el('small', {}, '/100'))),
  el('div', { class: 'ligne-pepite-info' }, [a.ticker, a.secteur_nom, dateHeure(a.date), `confiance ${a.confiance}`, a.issue ? `issue #${a.issue}` : null].filter(Boolean).join(' · ')),
  el('div', { class: 'ligne-reco' }, el('small', {}, 'Non détenu'), pastilleReco(a.recommandation), el('small', {}, 'Détenu'), pastilleReco(a.recommandation, true),
    a.recommandation?.e != null ? el('small', { class: 'mono' }, `valeur estimée ${variation(a.recommandation.e, 1)}`) : null),
  el('div', { class: 'ligne-pepite-verdict' }, a.verdict),
  );
  // Mini-graphique sur 12 mois, chargé quand la fiche apparaît à l'écran
  return el('div', { class: `ligne-pepite-bloc ${classeNote(a.note)}` }, bouton,
    graphiqueMini({ yahoo: a.ticker, place: a.place, historique: historiqueAnalyse(a.ticker) }));
}

/** etat : { analyses: {liste}, enCours: [..] | null | undefined (chargement) } */
export function ecranAnalyses(etat, nav) {
  const { liste } = etat.analyses ?? { liste: [] };
  // Issue ouverte sans résultat publié = en cours (une issue dont l'analyse est publiée est en train d'être fermée)
  const publiees = new Set(liste.flatMap((a) => [a.issue, ...(a.precedentes ?? []).map((p) => p.issue)]));
  const enCours = (etat.enCours ?? []).filter((i) => !publiees.has(i.numero));
  return [
    el('header', {},
      el('div', { class: 'fiche-surtitre' }, 'Analyse à la demande · même grille que l’agent entreprises'),
      el('h2', { class: 'fiche-titre' }, 'Mes analyses'),
    ),
    el('div', { class: 'analyses-actions' }, boutonAnalyser(), el('button', { type: 'button', class: 'bouton', onclick: () => nav.ouvrir({ type: 'fiabilite' }) }, 'Fiabilité des recommandations')),
    etat.enCours === undefined ? el('p', { class: 'fiche-verdict' }, 'Recherche des demandes en cours…')
      : etat.enCours === null ? el('p', { class: 'fiche-verdict' }, 'Demandes en cours non vérifiables (GitHub injoignable).')
        : enCours.length ? el('section', {},
          el('h3', { class: 'section-titre' }, 'En cours'),
          el('ul', { class: 'analyses-en-cours' }, enCours.map((i) => el('li', {},
            el('span', { class: 'pastille-reco pastille-reco--neutre' }, 'en cours'),
            el('span', {}, ` « ${i.saisie} » · demandée le ${dateHeure(i.date)} · `),
            el('a', { href: i.url, target: '_blank', rel: 'noopener' }, `issue #${i.numero} ↗`))))) : null,
    liste.length
      ? el('div', { class: 'pepites-liste' }, liste.map((a) => ligneAnalyse(a, (t) => nav.ouvrir({ type: 'analyse', id: t }))))
      : el('p', { class: 'fiche-verdict' }, 'Aucune analyse à la demande pour l’instant.'),
    el('p', { class: 'mention-legale' }, 'Avis indicatif généré automatiquement, sans prise en compte d’un profil ou d’une situation personnelle. Ne constitue pas un conseil en investissement.'),
  ];
}

/* ------------------------------------------------------------------ écran « Fiabilité des recommandations » */

const ORDRE_ND = ['Acheter', 'Acheter sur repli', 'Attendre', 'Éviter'];
const ORDRE_D = ['Renforcer', 'Conserver', 'Alléger', 'Vendre'];

function tableau(titre, ordre, bloc, horizons) {
  return el('section', {},
    el('h3', { class: 'section-titre' }, titre, el('small', {}, ' taux de réussite · écart moyen avec l’indice')),
    el('div', { class: 'tableau-defilant' }, el('table', { class: 'tableau-fiabilite' },
      el('thead', {}, el('tr', {}, el('th', {}, 'Recommandation'), el('th', {}, 'Émises'),
        horizons.map((m) => el('th', {}, `${m} mois`)))),
      el('tbody', {}, ordre.map((type) => {
        const b = bloc?.[type];
        return el('tr', {}, el('th', { scope: 'row' }, type), el('td', { class: 'mono' }, b ? nombre(b.total) : '0'),
          horizons.map((m) => {
            const h = b?.[String(m)];
            return el('td', { class: 'mono' }, h?.n
              ? [`${h.taux_pct} %`, el('small', {}, ` sur ${h.n} · ${variation(h.relative_moyenne_pct, 1)}`)]
              : el('small', {}, 'pas encore d’échéance'));
          }));
      })))),
  );
}

export function ecranFiabilite(h, nav) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Suivi automatique des recommandations'),
    el('h2', { class: 'fiche-titre' }, 'Fiabilité des recommandations'));
  if (h === undefined) return [entete, el('p', { class: 'fiche-verdict' }, 'Chargement…')];
  if (!h) return [entete, el('p', { class: 'fiche-verdict' }, 'Historique indisponible (data/historique/recommandations.json introuvable).')];
  const m = h.meta;
  const horizons = m.horizons_mois ?? [3, 6, 12];
  const f = m.fiabilite ?? {};
  const mesurees = h.liste.filter((x) => Object.values(x.suivi ?? {}).some((s) => s.relative_pct != null));
  const demandes = h.liste.filter((x) => x.source === 'demande').slice(-15).reverse();
  return [
    entete,
    el('p', { class: 'macro-texte' }, `${nombre(h.liste.length)} recommandations enregistrées, dont ${nombre(mesurees.length)} arrivées à au moins une échéance. `
      + `Performance comparée à l’indice ${m.indice_nom ?? 'MSCI World'} sur la même période (cours ajustés des dividendes).`),
    tableau('Si non détenu', ORDRE_ND, f.si_non_detenu, horizons),
    tableau('Si détenu', ORDRE_D, f.si_detenu, horizons),
    el('details', { class: 'detail-repliable' },
      el('summary', {}, 'Règles de réussite'),
      el('ul', { class: 'contre-scenario' },
        el('li', {}, 'Acheter, Renforcer : performance supérieure à l’indice.'),
        el('li', {}, 'Acheter sur repli, Conserver : pas plus de 5 points sous l’indice.'),
        el('li', {}, 'Attendre : écart avec l’indice compris entre −10 et +10 points.'),
        el('li', {}, 'Alléger : pas plus de 5 points au-dessus de l’indice.'),
        el('li', {}, 'Éviter, Vendre : performance inférieure à l’indice.'),
        el('li', {}, `Agent entreprises : une ligne quand la recommandation d’une société change (au plus une fois tous les ${m.intervalle_min_jours ?? 7} jours) ; analyses à la demande : chaque analyse.`),
      )),
    demandes.length ? el('section', {},
      el('h3', { class: 'section-titre' }, 'Dernières analyses à la demande'),
      el('ul', { class: 'liste-suivi' }, demandes.map((x) => el('li', {},
        el('button', { type: 'button', class: 'lien', onclick: () => nav.ouvrir({ type: 'analyse', id: x.ticker }) }, `${x.nom} (${x.ticker})`),
        ` · ${x.date.slice(8, 10)}/${x.date.slice(5, 7)}/${x.date.slice(0, 4)} · ${x.recommandation} / ${x.detenu} · cours ${nombre(x.cours, 2)} ${x.devise ?? ''}`,
        ...horizons.map((mm) => {
          const s = x.suivi?.[String(mm)];
          return s?.relative_pct != null ? el('small', { class: s.reussite ? 'hausse' : 'baisse' }, ` · ${mm} mois : ${variation(s.perf_pct, 1)} (${variation(s.relative_pct, 1)} vs indice)`) : null;
        }))))) : null,
    el('p', { class: 'mention-legale' }, 'Les performances passées ne préjugent pas des performances futures. Avis indicatifs générés automatiquement, sans prise en compte d’un profil ou d’une situation personnelle.'),
  ];
}
