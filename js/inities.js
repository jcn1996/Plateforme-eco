/* ==========================================================================
   Écran « Initiés » (données de l'agent initiés, data/inities.json, chargé à la
   première ouverture de l'écran ou d'une fiche entreprise) :
   - onglet « Dirigeants » : score « achats d'initiés » par société, achats récents
     sur le marché (États-Unis, France, Allemagne), ventes massives et groupées ;
   - onglet « Super-investisseurs » : une carte par investisseur (page dédiée :
     dernières opérations et principales positions), conviction par société ;
   - onglet « Activistes » : formulaires 13D ;
   - onglet « Élus » : transactions déclarées par les élus du Congrès (information seulement).
   Aussi : bloc « Initiés » de la fiche entreprise.
   ========================================================================== */

import { el, nombre } from './outils.js';

const FICHIER = 'data/inities.json';
let cache; // undefined : pas encore chargé ; null : indisponible

/** Charge data/inities.json (une fois) ; null si le fichier manque. */
export async function chargerInities(forcer = false) {
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
export const initiesCharges = () => cache;

/* ------------------------------------------------------------------ outils */

export const ONGLETS_INITIES = { dirigeants: 'Dirigeants', super: 'Super-investisseurs', activistes: 'Activistes', elus: 'Élus' };
const FONCTIONS = { pdg_daf: 'PDG / directeur financier', dirigeant: 'Dirigeant', administrateur: 'Administrateur', actionnaire_10pct: 'Actionnaire > 10 %', autre: 'Autre initié' };
const PAYS = { US: 'États-Unis', FR: 'France', DE: 'Allemagne', IN: 'Inde', TR: 'Turquie', KR: 'Corée', JP: 'Japon' };
const STATUTS = { actif: 'à jour', inactif: 'ne dépose plus', '13F-NT': '13F-NT (déclaré par une autre entité)', 'aucun 13F': 'aucun 13F', 'non lu': 'non lu' };
const MOUVEMENTS = { nouvelle: 'Nouvelle position', renforcement: 'Renforcement', 'allègement': 'Allègement' };

function dateFr(d) {
  if (!d) return 'n. d.';
  const s = String(d);
  return `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
}
function montant(v, devise = 'USD') {
  if (v == null) return 'n. d.';
  const sym = devise === 'USD' ? '$' : devise === 'EUR' ? '€' : ` ${devise}`;
  const a = Math.abs(v);
  if (a >= 1e9) return `${nombre(v / 1e9, 2)} Md${sym}`;
  if (a >= 1e6) return `${nombre(v / 1e6, 1)} M${sym}`;
  if (a >= 1e3) return `${nombre(v / 1e3, 0)} k${sym}`;
  return `${nombre(v, 0)} ${sym}`;
}
const titre = (texte, complement) => el('h3', { class: 'section-titre' }, texte, complement ? el('small', {}, complement) : null);
const mention = (texte) => el('p', { class: 'ini-mention' }, texte);
const classeScore = (n) => (n == null ? '' : n >= 60 ? 'hausse' : '');
const pastilleScore = (n, suffixe = '/100') => el('span', { class: `ini-score mono ${classeScore(n)}` }, n == null ? '—' : `${n}${suffixe}`);
const lien = (url, texte = 'source ↗') => (url ? el('a', { href: url, target: '_blank', rel: 'noopener' }, texte) : null);

/** Nom de société cliquable quand l'agent entreprises la suit. */
function societe(nav, ticker, nom) {
  const texte = nom ?? ticker ?? 'n. d.';
  if (ticker && nav.entrepriseExiste?.(ticker)) {
    return el('button', { class: 'lien', type: 'button', onclick: () => nav.ouvrirEntreprise(ticker) }, texte);
  }
  return el('span', {}, texte);
}

function ongletsBarre(actif, nav) {
  return el('div', { class: 'ini-onglets', role: 'tablist' }, Object.entries(ONGLETS_INITIES).map(([cle, libelle]) =>
    el('button', { class: `ini-onglet${cle === actif ? ' est-actif' : ''}`, type: 'button', role: 'tab', 'aria-selected': String(cle === actif),
      onclick: () => nav.ouvrir({ type: 'inities', id: cle }) }, libelle)));
}

/* ------------------------------------------------------------------ écran */

export function ecranInities(donnees, nav, id) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Agent initiés · dirigeants, activistes, super-investisseurs, élus'),
    el('h2', { class: 'fiche-titre' }, 'Initiés'),
  );
  if (donnees === undefined) return [entete, el('p', { class: 'sante-ligne' }, 'Chargement…')];
  if (!donnees) {
    return [entete, el('p', { class: 'sante-ligne' }, 'Données de l’agent initiés indisponibles (data/inities.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  }
  if (id?.startsWith('si-')) {
    const inv = donnees.super_investisseurs?.find((x) => x.cle === id.slice(3));
    if (inv) return pageInvestisseur(inv, donnees, nav);
  }
  const onglet = ONGLETS_INITIES[id] ? id : 'dirigeants';
  const corps = { dirigeants: ongletDirigeants, super: ongletSuper, activistes: ongletActivistes, elus: ongletElus }[onglet](donnees, nav);
  return [
    entete,
    ongletsBarre(onglet, nav),
    ...corps,
    el('p', { class: 'fraicheur' }, `Mis à jour le ${dateFr(donnees.meta?.genere_le)} · Agent initiés (règles, sans IA)`),
    el('p', { class: 'mention-legale' }, donnees.avertissement ?? 'Ne constitue pas un conseil en investissement.'),
  ];
}

/* ------------------------------------------------------------------ dirigeants */

function ongletDirigeants(d, nav) {
  const g = d.dirigeants ?? {};
  return [
    mention(d.mentions?.dirigeants ?? ''),
    el('section', {},
      titre('Score « achats d’initiés »', 'par société, sur 100'),
      g.societes?.length ? el('ul', { class: 'ini-liste' }, g.societes.slice(0, 60).map((s) => el('li', { class: 'ini-ligne' },
        pastilleScore(s.score),
        el('div', { class: 'ini-ligne-corps' },
          el('div', { class: 'ini-ligne-tete' }, societe(nav, s.ticker, s.nom), el('small', {}, [s.ticker, PAYS[s.pays] ?? s.pays].filter(Boolean).join(' · ')),
            s.acheteurs_30j >= 3 ? el('span', { class: 'ini-badge ini-badge--fort' }, `${s.acheteurs_30j} acheteurs en 30 j`) : null),
          el('div', { class: 'ini-ligne-texte' }, s.texte),
        )))) : el('p', { class: 'sante-ligne' }, 'Aucun achat de dirigeant retenu sur les 60 derniers jours.'),
      el('p', { class: 'macro-source' }, d.methode ?? ''),
    ),
    el('section', {},
      titre('Achats récents sur le marché', '60 derniers jours'),
      g.achats?.length ? el('div', { class: 'ini-tableau', role: 'table' },
        el('div', { class: 'ini-tr ini-tr--tete', role: 'row' }, ['Date', 'Société', 'Dirigeant', 'Montant', ''].map((x) => el('span', { role: 'columnheader' }, x))),
        g.achats.slice(0, 120).map((a) => el('div', { class: 'ini-tr', role: 'row' },
          el('span', { class: 'mono' }, dateFr(a.date)),
          el('span', {}, societe(nav, a.ticker, a.societe), el('small', {}, [a.ticker, PAYS[a.pays] ?? a.pays].filter(Boolean).join(' · '))),
          el('span', {}, a.declarant ?? 'n. d.', el('small', {}, a.titre || FONCTIONS[a.fonction] || ''),
            a.caractere === 'opportuniste' ? el('small', { class: 'hausse' }, 'achat opportuniste') : a.caractere === 'routinier' ? el('small', {}, 'achat routinier') : null),
          el('span', { class: 'mono' }, montant(a.montant, a.devise)),
          el('span', {}, lien(a.url))))) : el('p', { class: 'sante-ligne' }, 'Aucun achat récent.'),
    ),
    el('section', {},
      titre('Ventes massives et groupées', 'seul cas où les ventes des dirigeants sont un signal négatif'),
      g.ventes_massives?.length ? el('ul', { class: 'ini-liste' }, g.ventes_massives.map((v) => el('li', { class: 'ini-ligne' },
        el('span', { class: 'ini-badge ini-badge--neg' }, 'ventes'),
        el('div', { class: 'ini-ligne-corps' }, el('div', { class: 'ini-ligne-tete' }, societe(nav, v.ticker, v.nom), el('small', {}, v.ticker)),
          el('div', { class: 'ini-ligne-texte' }, v.texte))))) : el('p', { class: 'sante-ligne' }, 'Aucune vente massive et groupée détectée (sociétés suivies par l’agent entreprises).'),
    ),
  ];
}

/* ------------------------------------------------------------------ super-investisseurs */

function ongletSuper(d, nav) {
  return [
    mention(`${d.mentions?.['13f'] ?? ''}. Hors États-Unis : ${d.mentions?.hors_us ?? ''}.`),
    el('section', {},
      titre('Super-investisseurs suivis', 'toucher une carte pour le détail'),
      el('div', { class: 'ini-cartes' }, (d.super_investisseurs ?? []).map((i) => el('button', { class: 'carte ini-carte', type: 'button', onclick: () => nav.ouvrir({ type: 'inities', id: `si-${i.cle}` }) },
        el('div', { class: 'ini-ligne-tete' }, el('strong', {}, i.nom), el('span', { class: `ini-badge ${i.statut === 'actif' ? '' : 'ini-badge--neutre'}` }, STATUTS[i.statut] ?? i.statut)),
        el('small', {}, i.societe),
        el('div', { class: 'ini-carte-chiffres' },
          el('span', {}, el('small', {}, 'Trimestre'), i.trimestre_texte),
          el('span', {}, el('small', {}, 'Positions'), i.nb_positions ?? '—'),
          el('span', {}, el('small', {}, 'Nouvelles'), i.nouvelles?.length ?? 0)),
        i.hors_us?.length ? el('small', { class: 'hausse' }, `${i.hors_us.length} déclaration(s) hors États-Unis`) : null))),
    ),
    el('section', {},
      titre('Conviction des super-investisseurs', 'par société : nombre de détenteurs et poids dans leurs portefeuilles'),
      d.conviction?.length ? el('ul', { class: 'ini-liste' }, d.conviction.slice(0, 50).map((c) => el('li', { class: 'ini-ligne' },
        pastilleScore(c.score),
        el('div', { class: 'ini-ligne-corps' },
          el('div', { class: 'ini-ligne-tete' }, societe(nav, c.ticker, c.nom), el('small', {}, c.ticker)),
          el('div', { class: 'ini-ligne-texte' }, c.texte))))) : el('p', { class: 'sante-ligne' }, 'Aucune donnée.'),
    ),
  ];
}

function lignesPositions(liste, nav, { poids = true, variationActions = false } = {}) {
  if (!liste?.length) return el('p', { class: 'sante-ligne' }, 'Aucune.');
  return el('ul', { class: 'ini-positions' }, liste.map((p) => el('li', {},
    el('div', { class: 'ini-ligne-tete' }, societe(nav, p.ticker, p.nom), el('small', {}, p.ticker ?? p.cusip),
      p.mouvement ? el('span', { class: `ini-badge ${p.mouvement === 'allègement' ? 'ini-badge--neg' : ''}` }, MOUVEMENTS[p.mouvement]) : null),
    poids ? el('div', { class: 'ini-poids' },
      el('div', { class: 'mp-barre' }, el('span', { style: { width: `${Math.min(100, p.poids ?? p.poids_precedent ?? 0)}%` } })),
      el('span', { class: 'mono' }, `${nombre(p.poids ?? p.poids_precedent ?? 0, 1)} %`),
      p.valeur != null ? el('small', { class: 'mono' }, montant(p.valeur)) : null,
      variationActions && p.variation_actions_pct != null ? el('small', { class: 'mono' }, `${p.variation_actions_pct > 0 ? '+' : ''}${nombre(p.variation_actions_pct, 0)} % d’actions`) : null) : null)));
}

function pageInvestisseur(i, d, nav) {
  return [
    el('header', {},
      el('div', { class: 'fiche-surtitre' }, `Super-investisseur · ${i.societe} · CIK ${i.cik}`),
      el('h2', { class: 'fiche-titre' }, i.nom),
      el('p', { class: 'fiche-verdict' }, `Rapport 13F du ${i.trimestre_texte} (fin de trimestre ${dateFr(i.trimestre)}), déposé le ${dateFr(i.date_depot)}`
        + (i.valeur_totale ? ` · ${i.nb_positions} positions américaines, ${montant(i.valeur_totale)}` : '') + ` · statut : ${STATUTS[i.statut] ?? i.statut}.`),
    ),
    ongletsBarre('super', nav),
    mention(d.mentions?.['13f'] ?? ''),
    i.note ? el('p', { class: 'reco-reserve' }, i.note) : null,
    el('section', {},
      titre('Dernières opérations', i.trimestre_precedent ? `par rapport au ${dateFr(i.trimestre_precedent)}` : 'premier rapport lu'),
      el('h4', {}, 'Nouvelles positions'), lignesPositions(i.nouvelles, nav),
      el('h4', {}, 'Renforcements importants'), lignesPositions(i.renforcements, nav, { variationActions: true }),
      el('h4', {}, 'Allègements importants'), lignesPositions(i.allegements, nav, { variationActions: true }),
      el('h4', {}, 'Positions soldées'), lignesPositions(i.sorties, nav),
    ),
    el('section', {},
      titre('Principales positions', 'poids dans le portefeuille américain déclaré'),
      lignesPositions(i.principales, nav),
      i.options?.length ? el('p', { class: 'macro-source' }, `Options déclarées (hors poids) : ${i.options.map((o) => `${o.nom} (${o.option === 'PUT' ? 'vente' : 'achat'}, ${montant(o.valeur)})`).join(', ')}.`) : null,
    ),
    el('section', {},
      titre('Positions hors États-Unis', d.mentions?.hors_us),
      i.hors_us?.length ? el('ul', { class: 'ini-liste' }, i.hors_us.map((h) => el('li', { class: 'ini-ligne' },
        el('span', { class: 'ini-badge' }, PAYS[h.pays] ?? h.pays),
        el('div', { class: 'ini-ligne-corps' },
          el('div', { class: 'ini-ligne-tete' }, el('strong', {}, h.societe ?? 'Société n. d.'), h.pct != null ? el('span', { class: 'mono' }, `${nombre(h.pct, 2)} %`) : null),
          el('div', { class: 'ini-ligne-texte' }, `${h.titre ?? ''} · ${h.source} · ${dateFr(h.date)} `, lien(h.url)))))) : el('p', { class: 'sante-ligne' }, 'Aucune déclaration de franchissement de seuil relevée.'),
    ),
    el('p', { class: 'fraicheur' }, 'Source : SEC EDGAR (13F) ', lien(i.url, 'dépôts ↗')),
  ];
}

/* ------------------------------------------------------------------ activistes */

function ligne13d(a, nav) {
  return el('div', { class: 'ini-tr', role: 'row' },
    el('span', { class: 'mono' }, dateFr(a.depot)),
    el('span', {}, societe(nav, a.ticker, a.societe), el('small', {}, a.ticker ?? '')),
    el('span', {}, a.investisseur ?? 'n. d.', a.super_investisseur ? el('small', { class: 'hausse' }, 'super-investisseur suivi') : null),
    el('span', { class: 'mono' }, a.pct != null ? `${nombre(a.pct, 1)} %` : 'n. d.'),
    el('span', {}, lien(a.url)));
}

function ongletActivistes(d, nav) {
  const tous = d.activistes ?? [];
  const tete = el('div', { class: 'ini-tr ini-tr--tete', role: 'row' }, ['Dépôt', 'Société', 'Investisseur', '% détenu', ''].map((x) => el('span', { role: 'columnheader' }, x)));
  const originaux = tous.filter((a) => a.formulaire === '13D');
  const suivies = originaux.filter((a) => a.suivie || a.super_investisseur);
  return [
    mention('Formulaire 13D : participation de plus de 5 % avec l’intention d’influencer la société (déposé sous 5 jours ouvrés). Les amendements (13D/A) suivent l’évolution de la participation.'),
    suivies.length ? el('section', {}, titre('Sociétés suivies ou super-investisseurs'), el('div', { class: 'ini-tableau', role: 'table' }, tete.cloneNode(true), suivies.map((a) => ligne13d(a, nav)))) : null,
    el('section', {}, titre('Nouveaux 13D', `${originaux.length} sur 180 jours`),
      originaux.length ? el('div', { class: 'ini-tableau', role: 'table' }, tete.cloneNode(true), originaux.slice(0, 120).map((a) => ligne13d(a, nav))) : el('p', { class: 'sante-ligne' }, 'Aucun.')),
    el('section', {}, titre('Amendements récents (13D/A)', '60 derniers jours'),
      el('div', { class: 'ini-tableau', role: 'table' }, tete.cloneNode(true), tous.filter((a) => a.formulaire === '13D/A').slice(0, 60).map((a) => ligne13d(a, nav)))),
  ];
}

/* ------------------------------------------------------------------ élus */

function ongletElus(d, nav) {
  const liste = d.elus ?? [];
  return [
    mention(`${d.mentions?.elus ?? ''}. La loi (STOCK Act) impose de déclarer une opération sous 45 jours : un retard plus long est signalé.`),
    el('section', {},
      titre('Transactions déclarées', `${liste.length} opération(s), 120 derniers jours`),
      liste.length ? el('div', { class: 'ini-tableau ini-tableau--elus', role: 'table' },
        el('div', { class: 'ini-tr ini-tr--tete', role: 'row' }, ['Opération', 'Élu', 'Titre', 'Montant', 'Déclarée'].map((x) => el('span', { role: 'columnheader' }, x))),
        liste.slice(0, 250).map((e) => el('div', { class: 'ini-tr', role: 'row' },
          el('span', { class: 'mono' }, dateFr(e.date_operation), el('small', { class: e.type?.startsWith('achat') ? 'hausse' : e.type?.startsWith('vente') ? 'baisse' : '' }, e.type)),
          el('span', {}, e.elu, el('small', {}, `${e.chambre}${e.circonscription ? ` · ${e.circonscription}` : ''}`)),
          el('span', {}, e.ticker ? societe(nav, e.ticker, e.ticker) : '—', el('small', {}, e.actif ?? '')),
          el('span', { class: 'mono' }, e.montant ?? 'n. d.'),
          el('span', { class: 'mono' }, dateFr(e.date_declaration),
            el('small', { class: e.retard_jours > 45 ? 'baisse' : '' }, `${e.retard_jours} j de retard`), lien(e.url))))) : el('p', { class: 'sante-ligne' }, 'Aucune déclaration lue.'),
    ),
  ];
}

/* ------------------------------------------------------------------ fiche entreprise */

/** Bloc « Initiés » de la fiche entreprise (null tant que data/inities.json n'est pas chargé ou sans donnée). */
export function blocInities(ticker, nav = {}) {
  const d = cache;
  if (!d || !ticker) return null;
  const s = d.societes?.[ticker];
  const ouvrir = el('button', { class: 'lien', type: 'button', onclick: () => nav.ouvrir?.({ type: 'inities', id: 'dirigeants' }) }, 'Écran « Initiés » ›');
  if (!s) {
    return el('section', { class: 'carte ini-bloc' },
      el('h3', { class: 'section-titre' }, 'Initiés', el('small', {}, 'agent initiés')),
      el('p', { class: 'fiche-verdict' }, 'Aucun achat récent des dirigeants, aucun super-investisseur suivi et aucun 13D sur cette société.'), ouvrir);
  }
  return el('section', { class: 'carte ini-bloc' },
    el('h3', { class: 'section-titre' }, 'Initiés', el('small', {}, 'achats des dirigeants · super-investisseurs · activistes')),
    el('div', { class: 'ini-carte-chiffres' },
      el('span', {}, el('small', {}, 'Achats d’initiés'), pastilleScore(s.score_achats)),
      el('span', {}, el('small', {}, 'Conviction des super-investisseurs'), pastilleScore(s.conviction))),
    s.ventes_massives ? el('p', { class: 'reco-reserve' }, `Ventes massives et groupées : ${s.ventes_massives.texte}`) : null,
    s.texte_achats ? el('p', { class: 'ini-ligne-texte' }, s.texte_achats) : null,
    s.achats_recents?.length ? [el('h4', {}, 'Achats récents des dirigeants'), el('ul', { class: 'ini-mini' }, s.achats_recents.slice(0, 4).map((a) =>
      el('li', {}, el('span', { class: 'mono' }, dateFr(a.date)), ` ${a.declarant ?? ''} (${a.titre || FONCTIONS[a.fonction] || ''}) : `, el('strong', { class: 'mono' }, montant(a.montant, a.devise)))))] : null,
    s.super_investisseurs?.length ? [el('h4', {}, 'Super-investisseurs présents'), el('ul', { class: 'ini-mini' }, s.super_investisseurs.map((x) =>
      el('li', {}, el('button', { class: 'lien', type: 'button', onclick: () => nav.ouvrir?.({ type: 'inities', id: `si-${x.cle}` }) }, x.nom),
        x.poids != null ? ` : ${nombre(x.poids, 1)} % du portefeuille` : x.pct_capital != null ? ` : ${nombre(x.pct_capital, 2)} % du capital (hors États-Unis)` : '',
        x.mouvement ? ` · ${MOUVEMENTS[x.mouvement]?.toLowerCase()}` : ''))), mention(d.mentions?.['13f'] ?? '')] : null,
    s.activiste ? [el('h4', {}, 'Formulaire 13D'), el('p', { class: 'ini-ligne-texte' },
      `${s.activiste.investisseur ?? 'Un investisseur'} : ${s.activiste.pct != null ? `${nombre(s.activiste.pct, 1)} %` : 'plus de 5 %'}, ${s.activiste.formulaire} déposé le ${dateFr(s.activiste.depot)} `, lien(s.activiste.url))] : null,
    ouvrir,
  );
}
