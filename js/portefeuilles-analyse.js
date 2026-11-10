/* ==========================================================================
   Mes portefeuilles : analyses, calculées entièrement sur l'appareil.

   Entrées : les lignes du portefeuille (stockées localement) et les données
   PUBLIQUES des agents (entreprises, pays, chef d'orchestre, séries de cours).
   Aucune fonction de ce module ne fait de requête réseau : tout est pur,
   et testé par js/tests/portefeuilles.test.mjs.

   - profilLigne : classe d'actifs, pays, secteur, devise, thèmes d'une ligne ;
   - valeurLigne : valeur en euros (dernier cours connu, sinon valeur du courtier) ;
   - expositions + alertes de concentration ;
   - correlations : corrélation sur 1 an (rendements hebdomadaires) de chaque ligne
     avec le reste du portefeuille et avec le Nasdaq 100, part du risque, diversification ;
   - crible : note de l'agent, recommandation « si détenu », signaux d'alerte, contradicteur ;
   - coherence : lignes « Alléger » / « Éviter », opportunités « Renforcer » absentes ;
   - decorrelation : opportunités bien notées peu corrélées au portefeuille ;
   - performance : valeur, plus-values, performance depuis l'import vs MSCI World en euros.
   ========================================================================== */

export const MENTION_ANALYSE = 'Analyse indicative, sans prise en compte de votre situation personnelle.';

/* ------------------------------- Référentiels ------------------------------- */

export const CLASSES = {
  actions: 'Actions',
  obligations: 'Obligations',
  or: 'Or',
  matieres: 'Matières premières',
  immobilier: 'Immobilier',
  crypto: 'Cryptoactifs',
  liquidites: 'Liquidités',
  diversifie: 'Diversifié',
};

export const TYPES_LIGNE = {
  action: 'Action',
  etf: 'ETF / tracker',
  fonds: 'Fonds (OPCVM, unité de compte)',
  obligation: 'Obligation',
  liquidites: 'Liquidités',
  crypto: 'Cryptoactif',
  autre: 'Autre',
};

/** Zones utilisables pour un fonds, avec une répartition géographique approchée (en %). */
export const ZONES = {
  monde: { libelle: 'Monde (développés)', pays: { US: 72, JP: 5.5, GB: 3.5, CA: 3, FR: 2.8, CH: 2.4, DE: 2.2, AU: 1.7, NL: 1.2, autres: 5.7 }, indice: 'URTH' },
  monde_tous: { libelle: 'Monde (développés et émergents)', pays: { US: 64, JP: 5, CN: 2.8, GB: 3.2, CA: 2.7, FR: 2.5, IN: 2, TW: 2, CH: 2.1, DE: 2, autres: 11.7 }, indice: 'URTH' },
  etats_unis: { libelle: 'États-Unis', pays: { US: 100 }, indice: '^GSPC' },
  nasdaq: { libelle: 'États-Unis (Nasdaq 100)', pays: { US: 100 }, indice: '^NDX' },
  europe: { libelle: 'Europe', pays: { GB: 22, FR: 17, CH: 15, DE: 14, NL: 7, SE: 5, IT: 4.5, ES: 4.5, autres: 11 }, indice: 'EWQ' },
  zone_euro: { libelle: 'Zone euro', pays: { FR: 32, DE: 28, NL: 13, ES: 9, IT: 8, autres: 10 }, indice: '^FCHI' },
  emergents: { libelle: 'Émergents', pays: { CN: 26, IN: 19, TW: 19, KR: 10, BR: 4.5, SA: 3.5, ZA: 3, MX: 2, autres: 13 }, indice: 'MCHI' },
  asie: { libelle: 'Asie-Pacifique', pays: { JP: 38, CN: 15, AU: 12, TW: 10, KR: 8, IN: 8, autres: 9 }, indice: 'EWJ' },
};

/** Devise principale d'un pays (pour l'exposition aux devises des fonds diversifiés). */
const DEVISE_PAYS = {
  US: 'USD', JP: 'JPY', GB: 'GBP', CA: 'CAD', CH: 'CHF', AU: 'AUD', CN: 'CNY', IN: 'INR', TW: 'TWD', KR: 'KRW', BR: 'BRL',
  SA: 'SAR', ZA: 'ZAR', MX: 'MXN', SE: 'SEK', HK: 'HKD', SG: 'SGD', NO: 'NOK', DK: 'DKK', PL: 'PLN', TR: 'TRY', ID: 'IDR',
  TH: 'THB', VN: 'VND', CL: 'CLP', CO: 'COP', AR: 'ARS', AE: 'AED', EG: 'EGP',
  FR: 'EUR', DE: 'EUR', NL: 'EUR', IT: 'EUR', ES: 'EUR', BE: 'EUR', PT: 'EUR', IE: 'EUR', FI: 'EUR', AT: 'EUR', LU: 'EUR', GR: 'EUR',
};

/** Secteurs (clés GICS utilisées par l'agent entreprises → libellé). */
export const SECTEURS = {
  'Information Technology': 'Technologies de l’information',
  Communication: 'Communication',
  'Consumer Discretionary': 'Consommation discrétionnaire',
  'Consumer Staples': 'Consommation de base',
  'Health Care': 'Santé',
  Financials: 'Finance',
  Industrials: 'Industrie',
  Energy: 'Énergie',
  Materials: 'Matériaux',
  Utilities: 'Services aux collectivités',
  'Real Estate': 'Immobilier',
  diversifie: 'Diversifié',
};

/** Thèmes suivis (mêmes clés que le chef d'orchestre, plus « énergie »). */
export const THEMES = {
  ia: {
    libelle: 'Intelligence artificielle',
    tickers: ['NVDA', 'MSFT', 'GOOGL', 'GOOG', 'META', 'AMZN', 'AVGO', 'AMD', 'TSM', '2330.TW', 'ORCL', 'PLTR', 'SMCI', 'ARM', 'ANET', 'VRT', 'DELL', 'BOTZ', 'AIQ'],
    nom: /\b(ai|artificial intelligence|intelligence artificielle|robotics?|robotique)\b/i,
  },
  semi: {
    libelle: 'Semi-conducteurs',
    tickers: ['NVDA', 'AMD', 'AVGO', 'TSM', '2330.TW', 'ASML', 'ASML.AS', 'INTC', 'QCOM', 'MU', 'TXN', 'STMPA.PA', 'STM', 'IFX.DE', '005930.KS', '000660.KS', 'ARM', 'AMAT', 'LRCX', 'KLAC', 'SMH', 'SOXX', 'ADI', 'NXPI', 'MRVL', 'ON'],
    industrie: /semiconductor/i,
    nom: /semi-?conduct|semiconductor|semicon\b/i,
  },
  or: {
    libelle: 'Or',
    tickers: ['GC=F', 'GLD', 'IAU', 'PHAU.L', 'SGLD.L', 'GOLD', 'NEM', 'AEM', 'GDX', 'GDXJ', '4GLD.DE'],
    industrie: /gold/i,
    nom: /\b(gold|or physique|mines? d.or|aurifère)\b/i,
  },
  energie: {
    libelle: 'Énergie (pétrole, gaz, uranium)',
    tickers: ['CL=F', 'BZ=F', 'NG=F', 'XLE', 'TTE.PA', 'XOM', 'CVX', 'SHEL', 'SHEL.L', 'BP', 'BP.L', 'ENI.MI', 'CCJ', 'URA'],
    secteur: 'Energy',
    industrie: /oil|gas|uranium|coal/i,
    nom: /\b(energy|énergie|energie|oil|pétrole|petrole|uranium)\b/i,
  },
};

/** Thèmes du chef d'orchestre → thèmes de l'écran. */
const THEMES_CHEF = { ia: 'ia', semi: 'semi', or: 'or', petrole: 'energie' };

/** Seuils des alertes de concentration (part de la valeur du portefeuille, en %). */
export const SEUILS_CONCENTRATION = { ligne: 10, pays: 50, secteur: 30, devise: 60, theme: 20, classe: 85 };

const VERDICTS_POSITIFS = ['Renforcer', 'Renforcer fortement'];
const VERDICTS_NEGATIFS = ['Alléger', 'Éviter'];

/* ------------------------------- Utilitaires ------------------------------- */

const normaliserDevise = (d) => ({ GBp: 'GBP', GBX: 'GBP', ZAc: 'ZAR' }[d] ?? d);
const somme = (l) => l.reduce((s, x) => s + x, 0);
const arrondi = (v, d = 1) => (v == null || !Number.isFinite(v) ? null : Math.round(v * 10 ** d) / 10 ** d);
export const symboleLigne = (l) => (l.ticker || '').toUpperCase() || null;

/** Devise de cotation déduite du suffixe Yahoo (MC.PA → EUR, AAPL → USD). */
const DEVISES_SUFFIXE = {
  PA: 'EUR', AS: 'EUR', DE: 'EUR', F: 'EUR', MI: 'EUR', MC: 'EUR', BR: 'EUR', LS: 'EUR', HE: 'EUR', VI: 'EUR', IR: 'EUR',
  L: 'GBp', SW: 'CHF', T: 'JPY', HK: 'HKD', TO: 'CAD', AX: 'AUD', KS: 'KRW', TW: 'TWD', ST: 'SEK', CO: 'DKK', OL: 'NOK',
  SI: 'SGD', NS: 'INR', SA: 'BRL', MX: 'MXN', WA: 'PLN', IS: 'TRY', JO: 'ZAc', SR: 'SAR',
};
export function deviseSymbole(sym) {
  if (!sym) return null;
  if (/=X$/.test(sym)) return null;
  if (/-USD$/.test(sym) || /=F$/.test(sym) || sym.startsWith('^')) return 'USD';
  const m = sym.match(/\.([A-Z]{1,2})$/);
  return m ? (DEVISES_SUFFIXE[m[1]] ?? null) : 'USD';
}

/** Devise de cotation d'une ligne : saisie, sinon fiche de l'agent, sinon suffixe du ticker. */
export function deviseLigne(ligne, refs) {
  const sym = symboleLigne(ligne);
  const e = sym ? refs.entrepriseParTicker.get(sym) : null;
  const fiche = e ? refs.fiches?.[e.ticker] : null;
  return ligne.devise || fiche?.devise_cours || deviseSymbole(sym) || 'EUR';
}

/**
 * Index des données publiques utiles aux analyses, construit une fois.
 * d : données de l'appli (entreprises, pays…) ; chef : data/chef.json (donnees) ; series : symbole → [[date, cours]].
 */
export function construireReferences({ entreprises = [], pays = [], chef = null, series = {}, eurusd = null, fiches = {} } = {}) {
  const entrepriseParTicker = new Map(entreprises.map((e) => [e.ticker.toUpperCase(), e]));
  // autres cotations (ex. 0R2V.L pour Apple) → même société
  for (const e of entreprises) for (const a of e.autres_cotations ?? []) if (!entrepriseParTicker.has(a.ticker.toUpperCase())) entrepriseParTicker.set(a.ticker.toUpperCase(), e);
  const paysParCode = new Map(pays.map((p) => [p.code, p]));
  const opportunites = chef ? [
    ...(chef.pays ?? []), ...(chef.secteurs ?? []), ...(chef.entreprises ?? []), ...(chef.matieres ?? []),
    ...(chef.obligations ?? []), ...(chef.liquidites ?? []), ...(chef.or ? [chef.or] : []),
  ] : [];
  const opportuniteParSymbole = new Map();
  for (const o of opportunites) {
    if (o.symbole) opportuniteParSymbole.set(o.symbole.toUpperCase(), o);
    if (o.type === 'entreprises' && o.cle) opportuniteParSymbole.set(o.cle.toUpperCase(), o);
  }
  // ETF pays (EWJ, EWQ…) → code pays
  const paysParEtf = new Map((chef?.pays ?? []).filter((o) => o.symbole).map((o) => [o.symbole.toUpperCase(), o.cle]));
  return { entrepriseParTicker, paysParCode, chef, opportunites, opportuniteParSymbole, paysParEtf, series, eurusd, fiches };
}

/* ------------------------------- Profil d'une ligne ------------------------------- */

/**
 * Profil d'exposition d'une ligne : classe, répartition par pays (%), secteur, devises (%), thèmes,
 * et d'où vient l'information (agent entreprises, ETF pays, saisie manuelle…).
 */
export function profilLigne(ligne, refs) {
  const sym = symboleLigne(ligne);
  const cat = ligne.categorie ?? {};
  const e = sym ? refs.entrepriseParTicker.get(sym) : null;
  const opp = sym ? refs.opportuniteParSymbole.get(sym) : null;
  const fiche = e ? refs.fiches?.[e.ticker] : null;
  const themes = new Set(cat.themes ?? []);
  for (const t of opp?.themes ?? []) if (THEMES_CHEF[t]) themes.add(THEMES_CHEF[t]);
  const industrie = fiche?.industrie ?? opp?.industrie ?? '';
  for (const [cle, t] of Object.entries(THEMES)) {
    if (sym && t.tickers.includes(sym)) themes.add(cle);
    if (t.industrie && industrie && t.industrie.test(industrie)) themes.add(cle);
    if (t.secteur && e?.secteur_gics === t.secteur) themes.add(cle);
    if (t.nom && t.nom.test(ligne.nom ?? '')) themes.add(cle);
  }

  // Liquidités, cryptoactifs : évident
  if (ligne.type === 'liquidites') {
    const dev = ligne.devise || 'EUR';
    return { classe: 'liquidites', pays: {}, secteur: null, devises: { [dev]: 100 }, themes: [], source: 'saisie' };
  }
  if (ligne.type === 'crypto') return { classe: 'crypto', pays: {}, secteur: null, devises: { USD: 100 }, themes: [...themes], source: 'saisie' };

  // Action suivie par l'agent entreprises
  if (e && ligne.type !== 'fonds') {
    return {
      classe: cat.classe || 'actions',
      pays: { [e.pays]: 100 },
      secteur: e.secteur_gics ?? cat.secteur ?? null,
      devises: { [normaliserDevise(deviseLigne(ligne, refs))]: 100 },
      themes: [...themes],
      source: 'agent entreprises',
      entreprise: e,
      opportunite: opp,
    };
  }

  // ETF pays suivi par le chef d'orchestre (EWJ, EWQ…)
  const paysEtf = sym ? refs.paysParEtf.get(sym) : null;
  if (paysEtf) {
    return {
      classe: 'actions', pays: { [paysEtf]: 100 }, secteur: 'diversifie', devises: { [DEVISE_PAYS[paysEtf] ?? 'USD']: 100 },
      themes: [...themes], source: 'ETF pays (chef d’orchestre)', opportunite: opp,
    };
  }

  // Autres opportunités du chef (or, matières, obligations, ETF sectoriels)
  if (opp && !cat.classe) {
    const classe = { or: 'or', matieres: 'matieres', obligations: 'obligations', liquidites: 'liquidites' }[opp.type] ?? 'actions';
    const zone = ZONES[opp.zone_secteur ?? opp.zone];
    return {
      classe,
      pays: classe === 'actions' && zone ? { ...zone.pays } : opp.pays ? { [opp.pays]: 100 } : {},
      secteur: opp.secteur ?? (classe === 'actions' ? 'diversifie' : null),
      devises: { [opp.devise ?? 'USD']: 100 },
      themes: [...themes],
      source: 'chef d’orchestre',
      opportunite: opp,
    };
  }

  // Fonds, ETF ou titre non reconnu : catégorie saisie à la main
  const zone = ZONES[cat.zone];
  const pays = zone ? { ...zone.pays } : cat.zone && /^[A-Z]{2}$/.test(cat.zone) ? { [cat.zone]: 100 } : {};
  const devises = {};
  const classe = cat.classe || (ligne.type === 'obligation' ? 'obligations' : 'actions');
  if (['actions', 'immobilier'].includes(classe) && Object.keys(pays).length) {
    for (const [p, pct] of Object.entries(pays)) {
      const dev = p === 'autres' ? 'autres' : (DEVISE_PAYS[p] ?? 'autres');
      devises[dev] = (devises[dev] ?? 0) + pct;
    }
  } else if (classe === 'or' || classe === 'matieres') devises.USD = 100;
  else devises[ligne.devise || 'EUR'] = 100;
  return {
    classe,
    pays,
    secteur: cat.secteur || (classe === 'actions' ? 'diversifie' : null),
    devises,
    themes: [...themes],
    source: Object.keys(cat).length ? 'catégorie saisie' : 'non classé',
    nonClasse: !Object.keys(cat).length && !e,
    opportunite: opp,
  };
}

/* ------------------------------- Valeur d'une ligne ------------------------------- */

/** Dernier cours public connu d'un symbole : séries des agents, opportunités du chef, fiches. */
export function dernierCours(sym, refs) {
  if (!sym) return null;
  const serie = refs.series?.[sym];
  const candidats = [];
  if (serie?.length) candidats.push({ cours: serie[serie.length - 1][1], date: serie[serie.length - 1][0], devise: null, source: 'séries des agents' });
  const opp = refs.opportuniteParSymbole.get(sym);
  if (opp?.cours != null) candidats.push({ cours: opp.cours, date: opp.date_cours, devise: opp.devise ?? null, source: 'chef d’orchestre' });
  const e = refs.entrepriseParTicker.get(sym);
  const fiche = e && e.ticker === sym ? refs.fiches?.[e.ticker] : null;
  if (fiche?.recommandation?.cours != null) candidats.push({ cours: fiche.recommandation.cours, date: fiche.recommandation.date_cours, devise: fiche.recommandation.devise, source: 'agent entreprises' });
  if (!candidats.length) return null;
  candidats.sort((a, b) => String(b.date ?? '').localeCompare(String(a.date ?? '')));
  return candidats[0];
}

/**
 * Convertit un montant en euros. eurusd : nombre de dollars pour 1 euro.
 * Renvoie null si la devise n'est pas convertible (autres devises : valeur du courtier utilisée).
 */
export function enEuros(montant, devise, eurusd) {
  if (montant == null) return null;
  const d = (devise || 'EUR').toUpperCase();
  if (d === 'EUR') return montant;
  if (d === 'USD' && eurusd) return montant / eurusd;
  return null;
}

/**
 * Valeur actuelle en euros d'une ligne :
 * 1. quantité × dernier cours public (si plus récent que la valeur du courtier et convertible) ;
 * 2. sinon la valeur indiquée par le courtier (import, synchronisation, saisie) ;
 * 3. sinon quantité × prix de revient.
 */
export function valeurLigne(ligne, refs) {
  const sym = symboleLigne(ligne);
  const devise = deviseLigne(ligne, refs);
  const c = ligne.quantite != null && ligne.type !== 'fonds' ? dernierCours(sym, refs) : null;
  if (c && (!ligne.date_valeur || String(c.date ?? '') > ligne.date_valeur)) {
    const v = enEuros(ligne.quantite * c.cours, c.devise ?? devise, refs.eurusd);
    if (v != null) return { valeur: v, source: `${c.source}, cours du ${c.date}`, date: c.date };
  }
  if (ligne.valeur != null) return { valeur: ligne.valeur, source: ligne.source_valeur ?? 'valeur du courtier', date: ligne.date_valeur ?? null };
  if (ligne.quantite != null && ligne.cours != null) {
    const v = enEuros(ligne.quantite * ligne.cours, devise, refs.eurusd);
    if (v != null) return { valeur: v, source: 'quantité × cours saisi', date: ligne.date_valeur ?? null };
  }
  if (ligne.quantite != null && ligne.prix_revient != null) {
    const v = enEuros(ligne.quantite * ligne.prix_revient, devise, refs.eurusd);
    if (v != null) return { valeur: v, source: 'prix de revient (aucun cours connu)', date: null };
  }
  return { valeur: null, source: 'valeur inconnue', date: null };
}

/** Coût d'acquisition en euros (quantité × prix de revient), si calculable. */
export function coutLigne(ligne, refs) {
  if (ligne.quantite == null || ligne.prix_revient == null) return null;
  return enEuros(ligne.quantite * ligne.prix_revient, deviseLigne(ligne, refs), refs.eurusd);
}

/** Lignes enrichies (valeur, poids, profil) d'un ou plusieurs portefeuilles. */
export function enrichir(lignes, refs) {
  const res = lignes.map((l) => {
    const v = valeurLigne(l, refs);
    return { ligne: l, valeur: v.valeur, sourceValeur: v.source, cout: coutLigne(l, refs), profil: profilLigne(l, refs) };
  });
  const total = somme(res.map((x) => x.valeur ?? 0));
  for (const x of res) x.poids = total > 0 && x.valeur != null ? (x.valeur / total) * 100 : 0;
  return { lignes: res, total };
}

/* ------------------------------- Expositions ------------------------------- */

function ajouter(table, cle, pct) {
  if (!cle || !pct) return;
  table[cle] = (table[cle] ?? 0) + pct;
}

const trier = (table, libelles = {}) => Object.entries(table)
  .map(([cle, pct]) => ({ cle, libelle: libelles[cle] ?? cle, pct: arrondi(pct, 2) }))
  .filter((x) => x.pct > 0)
  .sort((a, b) => b.pct - a.pct);

/**
 * Expositions par pays, secteur, devise, classe d'actifs et thème (en % de la valeur totale)
 * et alertes de concentration. nomsPays : code → nom.
 */
export function expositions(enrichi, nomsPays = {}) {
  const pays = {}; const secteurs = {}; const devises = {}; const classes = {}; const themes = {};
  for (const x of enrichi.lignes) {
    const w = x.poids;
    if (!w) continue;
    const p = x.profil;
    ajouter(classes, p.classe, w);
    if (['actions', 'immobilier'].includes(p.classe)) {
      const totalPays = somme(Object.values(p.pays));
      if (totalPays) for (const [c, pct] of Object.entries(p.pays)) ajouter(pays, c, (w * pct) / totalPays);
      else ajouter(pays, 'non_classe', w);
      ajouter(secteurs, p.secteur ?? 'non_classe', w);
    }
    const totalDev = somme(Object.values(p.devises));
    if (totalDev) for (const [c, pct] of Object.entries(p.devises)) ajouter(devises, c, (w * pct) / totalDev);
    for (const t of p.themes) ajouter(themes, t, w);
  }
  const libPays = { ...nomsPays, autres: 'Autres pays', non_classe: 'Non classé' };
  const libSecteurs = { ...SECTEURS, non_classe: 'Non classé' };
  const libThemes = Object.fromEntries(Object.entries(THEMES).map(([k, t]) => [k, t.libelle]));
  const r = {
    pays: trier(pays, libPays),
    secteurs: trier(secteurs, libSecteurs),
    devises: trier(devises, { autres: 'Autres devises' }),
    classes: trier(classes, CLASSES),
    themes: trier(themes, libThemes),
  };
  r.alertes = alertesConcentration(enrichi, r);
  return r;
}

export function alertesConcentration(enrichi, exp, seuils = SEUILS_CONCENTRATION) {
  const a = [];
  const f = (v) => String(arrondi(v, 1)).replace('.', ',');
  for (const x of enrichi.lignes) {
    if (x.poids > seuils.ligne && x.profil.classe !== 'liquidites' && !['etf', 'fonds'].includes(x.ligne.type)) {
      a.push({ type: 'ligne', niveau: x.poids > seuils.ligne * 2 ? 'forte' : 'moderee', texte: `${x.ligne.nom} pèse ${f(x.poids)} % du portefeuille (seuil : ${seuils.ligne} % par titre).` });
    }
  }
  for (const p of exp.pays) if (p.cle !== 'autres' && p.cle !== 'non_classe' && p.pct > seuils.pays) a.push({ type: 'pays', niveau: p.pct > 75 ? 'forte' : 'moderee', texte: `${p.libelle} : ${f(p.pct)} % du portefeuille (seuil : ${seuils.pays} %).` });
  for (const s of exp.secteurs) if (s.cle !== 'diversifie' && s.cle !== 'non_classe' && s.pct > seuils.secteur) a.push({ type: 'secteur', niveau: s.pct > seuils.secteur * 1.5 ? 'forte' : 'moderee', texte: `Secteur ${s.libelle} : ${f(s.pct)} % (seuil : ${seuils.secteur} %).` });
  for (const d of exp.devises) if (d.cle !== 'EUR' && d.cle !== 'autres' && d.pct > seuils.devise) a.push({ type: 'devise', niveau: 'moderee', texte: `Devise ${d.cle} : ${f(d.pct)} % (seuil : ${seuils.devise} %) : le portefeuille dépend fortement du change contre l’euro.` });
  for (const t of exp.themes) if (t.pct > seuils.theme) a.push({ type: 'theme', niveau: t.pct > seuils.theme * 1.5 ? 'forte' : 'moderee', texte: `Thème « ${t.libelle} » : ${f(t.pct)} % (seuil : ${seuils.theme} %, comme le chef d’orchestre).` });
  for (const c of exp.classes) if (c.cle !== 'diversifie' && c.pct > seuils.classe) a.push({ type: 'classe', niveau: 'moderee', texte: `${c.libelle} : ${f(c.pct)} % du portefeuille : peu de diversification entre classes d’actifs.` });
  const ordre = { forte: 0, moderee: 1 };
  return a.sort((x, y) => ordre[x.niveau] - ordre[y.niveau]);
}

/* ------------------------------- Corrélations ------------------------------- */

/** Vendredi de la semaine (ISO) d'une date « AAAA-MM-JJ » : clé hebdomadaire commune à toutes les séries. */
export function cleSemaine(date) {
  const d = new Date(`${String(date).slice(0, 10)}T12:00:00Z`);
  const jour = (d.getUTCDay() + 6) % 7; // lundi = 0
  d.setUTCDate(d.getUTCDate() - jour + 4);
  return d.toISOString().slice(0, 10);
}

/** Série [[date, cours]] (quotidienne ou hebdomadaire) → rendements hebdomadaires { semaine: r }. */
export function rendementsHebdo(serie, { depuis = null } = {}) {
  if (!serie?.length) return {};
  const parSemaine = new Map();
  for (const [date, c] of [...serie].sort((a, b) => String(a[0]).localeCompare(String(b[0])))) {
    if (c == null || !(c > 0)) continue;
    parSemaine.set(cleSemaine(date), c); // dernier cours de la semaine
  }
  const semaines = [...parSemaine.keys()].sort();
  const r = {};
  for (let i = 1; i < semaines.length; i += 1) {
    if (depuis && semaines[i] < depuis) continue;
    r[semaines[i]] = parSemaine.get(semaines[i]) / parSemaine.get(semaines[i - 1]) - 1;
  }
  return r;
}

function covariance(a, b) {
  const cles = Object.keys(a).filter((k) => k in b);
  if (cles.length < 3) return { cov: null, n: cles.length };
  const ma = somme(cles.map((k) => a[k])) / cles.length;
  const mb = somme(cles.map((k) => b[k])) / cles.length;
  return { cov: somme(cles.map((k) => (a[k] - ma) * (b[k] - mb))) / (cles.length - 1), n: cles.length };
}

/** Corrélation de Pearson entre deux séries de rendements (semaines communes, au moins `min`). */
export function correlation(a, b, min = 20) {
  const cles = Object.keys(a).filter((k) => k in b);
  if (cles.length < min) return null;
  const x = cles.map((k) => a[k]);
  const y = cles.map((k) => b[k]);
  const mx = somme(x) / x.length;
  const my = somme(y) / y.length;
  let sxy = 0; let sxx = 0; let syy = 0;
  for (let i = 0; i < x.length; i += 1) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2; }
  if (!sxx || !syy) return null;
  return sxy / Math.sqrt(sxx * syy);
}

/** Rendements d'un panier pondéré (poids renormalisés chaque semaine sur les lignes disponibles). */
export function rendementsPanier(elements) {
  const semaines = new Set();
  for (const e of elements) for (const k of Object.keys(e.r)) semaines.add(k);
  const r = {};
  for (const s of semaines) {
    let num = 0; let den = 0;
    for (const e of elements) if (s in e.r) { num += e.w * e.r[s]; den += e.w; }
    const total = somme(elements.map((e) => e.w));
    if (den > 0 && den >= total * 0.5) r[s] = num / den; // au moins la moitié du panier couverte cette semaine
  }
  return r;
}

/**
 * Série de cours utilisée pour une ligne : la sienne si elle est connue (synchronisation,
 * fiche de l'agent entreprises, séries des agents), sinon un indice de référence approché
 * selon sa catégorie (fonds, ETF) — signalé « approximation ».
 */
export function serieLigne(ligne, profil, refs) {
  const sym = symboleLigne(ligne);
  if (sym && refs.series?.[sym]?.length) return { serie: refs.series[sym], approximation: null, symbole: sym };
  const cat = ligne.categorie ?? {};
  let proxy = cat.indice || null;
  if (!proxy) {
    if (profil.classe === 'or') proxy = 'GC=F';
    else if (profil.classe === 'matieres') proxy = 'CL=F';
    else if (['actions', 'immobilier'].includes(profil.classe)) {
      const pays = Object.keys(profil.pays);
      if (ZONES[cat.zone]) proxy = ZONES[cat.zone].indice;
      else if (pays.length === 1) proxy = refs.chef?.pays?.find((o) => o.cle === pays[0])?.symbole ?? null;
    }
  }
  if (proxy && refs.series?.[proxy]?.length) return { serie: refs.series[proxy], approximation: proxy, symbole: proxy };
  return { serie: null, approximation: null, symbole: null };
}

/**
 * Corrélations et contributions au risque, sur 1 an de rendements hebdomadaires.
 * Renvoie { lignes: [{ id, nom, poids, corr_reste, corr_nasdaq, vol, part_risque, approximation }],
 *           portefeuille: { vol, corr_nasdaq, n_effectif_lignes, n_effectif_risque, ratio_diversification },
 *           couverture (% de la valeur couverte), non_couvertes: [noms] }
 */
export function correlations(enrichi, refs, { nasdaq = '^NDX', aujourdhui = new Date() } = {}) {
  const depuis = cleSemaine(new Date(aujourdhui.getTime() - 366 * 864e5).toISOString().slice(0, 10));
  const rNdx = rendementsHebdo(refs.series?.[nasdaq], { depuis });
  const elements = [];
  const nonCouvertes = [];
  for (const x of enrichi.lignes) {
    if (!x.poids) continue;
    if (x.profil.classe === 'liquidites') { elements.push({ x, r: null, liquidites: true }); continue; }
    const s = serieLigne(x.ligne, x.profil, refs);
    const r = s.serie ? rendementsHebdo(s.serie, { depuis }) : {};
    if (Object.keys(r).length < 20) { nonCouvertes.push(x.ligne.nom); continue; }
    elements.push({ x, r, approximation: s.approximation });
  }
  // Liquidités : rendement nul chaque semaine (volatilité nulle, corrélation non définie)
  const semaines = new Set(elements.flatMap((e) => (e.r ? Object.keys(e.r) : [])));
  for (const e of elements) if (e.liquidites) e.r = Object.fromEntries([...semaines].map((s) => [s, 0]));
  const actifs = elements.filter((e) => Object.keys(e.r).length);
  const totalPoids = somme(actifs.map((e) => e.x.poids));
  if (actifs.length < 1 || !totalPoids) return { lignes: [], portefeuille: null, couverture: 0, non_couvertes: nonCouvertes };
  for (const e of actifs) e.w = e.x.poids / totalPoids;

  // Matrice de covariance (paires de semaines communes)
  const n = actifs.length;
  const cov = Array.from({ length: n }, () => new Array(n).fill(0));
  for (let i = 0; i < n; i += 1) for (let j = i; j < n; j += 1) {
    const c = covariance(actifs[i].r, actifs[j].r).cov ?? 0;
    cov[i][j] = c; cov[j][i] = c;
  }
  const sigmaW = actifs.map((_, i) => somme(actifs.map((e, j) => e.w * cov[i][j])));
  const varP = somme(actifs.map((e, i) => e.w * sigmaW[i]));
  const rP = rendementsPanier(actifs.map((e) => ({ r: e.r, w: e.w })));

  const lignes = actifs.map((e, i) => {
    const reste = actifs.filter((_, j) => j !== i).map((o) => ({ r: o.r, w: o.w }));
    const rReste = reste.length ? rendementsPanier(reste) : {};
    const vol = Math.sqrt(Math.max(cov[i][i], 0) * 52) * 100;
    return {
      id: e.x.ligne.id,
      nom: e.x.ligne.nom,
      poids: arrondi(e.x.poids, 2),
      corr_reste: e.liquidites ? null : arrondi(correlation(e.r, rReste), 2),
      corr_nasdaq: e.liquidites ? null : arrondi(correlation(e.r, rNdx), 2),
      vol: arrondi(vol, 1),
      part_risque: varP > 0 ? arrondi(((e.w * sigmaW[i]) / varP) * 100, 1) : null,
      approximation: e.approximation ?? null,
    };
  }).sort((a, b) => (b.part_risque ?? -1) - (a.part_risque ?? -1));

  const parts = lignes.map((l) => (l.part_risque ?? 0) / 100).filter((p) => p > 0);
  const volP = Math.sqrt(Math.max(varP, 0) * 52) * 100;
  const sommeVol = somme(actifs.map((e, i) => e.w * Math.sqrt(Math.max(cov[i][i], 0) * 52) * 100));
  return {
    lignes,
    portefeuille: {
      vol: arrondi(volP, 1),
      corr_nasdaq: arrondi(correlation(rP, rNdx), 2),
      n_lignes: actifs.length,
      n_effectif_lignes: arrondi(1 / somme(actifs.map((e) => e.w ** 2)), 1),
      n_effectif_risque: parts.length ? arrondi(1 / somme(parts.map((p) => p ** 2)), 1) : null,
      ratio_diversification: volP > 0 ? arrondi(sommeVol / volP, 2) : null,
    },
    rendements: rP,
    couverture: arrondi((totalPoids / somme(enrichi.lignes.map((x) => x.poids))) * 100, 1),
    non_couvertes: nonCouvertes,
  };
}

/* ------------------------------- Crible de chaque ligne ------------------------------- */

/**
 * Passe chaque ligne au crible des agents : note (agent entreprises ou pays), recommandation
 * « si détenu », signaux d'alerte, verdict et objections du contradicteur (chef d'orchestre).
 */
export function crible(enrichi, refs) {
  return enrichi.lignes.map((x) => {
    const p = x.profil;
    const e = p.entreprise;
    const fiche = e ? refs.fiches?.[e.ticker] : null;
    const opp = p.opportunite;
    const r = { id: x.ligne.id, nom: x.ligne.nom, poids: x.poids, note: null, source_note: null, si_detenu: null, alertes: [], objections: [], verdict_chef: null, donner_tort: [] };
    if (e) {
      r.note = e.note;
      r.source_note = 'agent entreprises';
      r.si_detenu = fiche?.recommandation?.si_detenu ?? e.recommandation?.d ?? null;
      r.lien = { type: 'entreprise', id: e.ticker };
      for (const a of fiche?.alertes ?? []) r.alertes.push(`${a.titre}${a.texte ? ` : ${a.texte}` : ''}`);
      if (e.surveillance) r.alertes.push('Société placée sous surveillance par l’agent entreprises.');
      if (e.holding) r.alertes.push('Holding : la note des comptes est moins représentative.');
      for (const c of (fiche?.recommandation?.conditions_invalidation ?? []).slice(0, 2)) r.donner_tort.push(typeof c === 'string' ? c : c.texte ?? JSON.stringify(c));
    } else {
      const paysCodes = Object.keys(p.pays).filter((c) => c !== 'autres');
      const principal = paysCodes.length === 1 ? refs.paysParCode.get(paysCodes[0]) : null;
      if (principal && principal.note != null) {
        r.note = principal.note;
        r.source_note = `agent pays (${principal.nom})`;
        r.lien = { type: 'pays', id: principal.code };
      }
    }
    if (opp) {
      r.verdict_chef = { verdict: opp.verdict, conviction: opp.conviction, score: opp.score };
      for (const o of opp.objections ?? []) if (o?.objection) r.objections.push(o.objection);
      for (const t of (opp.donner_tort ?? []).slice(0, 3)) if (!r.donner_tort.includes(t)) r.donner_tort.push(t);
    }
    if (r.si_detenu === 'Vendre' || r.si_detenu === 'Alléger') r.alertes.unshift(`Recommandation « si détenu » : ${r.si_detenu}.`);
    if (r.verdict_chef && VERDICTS_NEGATIFS.includes(r.verdict_chef.verdict)) r.alertes.unshift(`Chef d’orchestre : « ${r.verdict_chef.verdict} ».`);
    if (p.nonClasse) r.alertes.push('Ligne non classée : précisez sa catégorie (zone, classe, secteur) pour fiabiliser les expositions.');
    return r;
  });
}

/* ------------------------------- Cohérence avec le chef d'orchestre ------------------------------- */

/**
 * - positions sur des opportunités « Alléger » ou « Éviter » ;
 * - opportunités « Renforcer » ou « Renforcer fortement » absentes du portefeuille.
 */
export function coherence(enrichi, refs, exp, { max = 8 } = {}) {
  const detenus = new Set();
  const aAlleger = [];
  for (const x of enrichi.lignes) {
    const opp = x.profil.opportunite;
    if (!opp) continue;
    detenus.add(opp.id);
    if (VERDICTS_NEGATIFS.includes(opp.verdict)) aAlleger.push({ nom: x.ligne.nom, poids: arrondi(x.poids, 1), verdict: opp.verdict, conviction: opp.conviction, score: opp.score, raison: opp.contre?.[0]?.famille ?? null });
  }
  const paysExposes = new Map((exp?.pays ?? []).map((p) => [p.cle, p.pct]));
  const absentes = refs.opportunites
    .filter((o) => VERDICTS_POSITIFS.includes(o.verdict) && !detenus.has(o.id))
    .filter((o) => !(o.type === 'pays' && (paysExposes.get(o.cle) ?? 0) >= 3)) // pays déjà représenté par d'autres lignes
    .sort((a, b) => (b.verdict === 'Renforcer fortement') - (a.verdict === 'Renforcer fortement') || b.score - a.score)
    .slice(0, max)
    .map((o) => ({ id: o.id, nom: o.nom, type: o.type, verdict: o.verdict, conviction: o.conviction, score: o.score, symbole: o.symbole, exposition_actuelle: o.type === 'pays' ? arrondi(paysExposes.get(o.cle) ?? 0, 1) : null }));
  return { a_alleger: aAlleger, absentes };
}

/* ------------------------------- Pistes de décorrélation ------------------------------- */

/**
 * Opportunités bien notées par le chef d'orchestre (verdict positif) dont la corrélation sur 1 an
 * avec le portefeuille actuel est faible. seriesOpp : id → série de cours de l'opportunité.
 */
export function decorrelation(rPortefeuille, refs, seriesOpp, { max = 6, seuil = 0.5, aujourdhui = new Date() } = {}) {
  if (!rPortefeuille || Object.keys(rPortefeuille).length < 20) return [];
  const depuis = cleSemaine(new Date(aujourdhui.getTime() - 366 * 864e5).toISOString().slice(0, 10));
  return refs.opportunites
    .filter((o) => VERDICTS_POSITIFS.includes(o.verdict) && seriesOpp[o.id]?.length)
    .map((o) => ({ id: o.id, nom: o.nom, type: o.type, verdict: o.verdict, conviction: o.conviction, score: o.score, symbole: o.symbole, corr: arrondi(correlation(rendementsHebdo(seriesOpp[o.id], { depuis }), rPortefeuille), 2) }))
    .filter((o) => o.corr != null && o.corr < seuil)
    .sort((a, b) => a.corr - b.corr || b.score - a.score)
    .slice(0, max);
}

/* ------------------------------- Performance ------------------------------- */

/** Valeur du MSCI World en euros (ETF URTH en dollars ÷ EUR/USD) à une date (dernier cours connu à cette date). */
export function msciEuros(refs, date) {
  const urth = refs.series?.URTH;
  const fx = refs.series?.['EURUSD=X'];
  if (!urth?.length || !fx?.length) return null;
  const aLaDate = (s) => {
    let v = null;
    for (const [d, c] of s) { if (d <= date) v = c; else break; }
    return v;
  };
  const u = aLaDate(urth);
  const f = aLaDate(fx);
  return u && f ? u / f : null;
}

/**
 * Performance d'un ensemble de lignes : valeur, coût, plus-values latentes,
 * performance depuis l'import (valeur de référence enregistrée à l'import) comparée au MSCI World en euros.
 * reference : { date, valeur } ; historique : [{ date, valeur }] (un point par jour, sur l'appareil).
 */
export function performance(enrichi, refs, reference, historique = []) {
  const valeur = enrichi.total;
  const avecCout = enrichi.lignes.filter((x) => x.cout != null && x.valeur != null);
  const cout = somme(avecCout.map((x) => x.cout));
  const plusValue = avecCout.length ? somme(avecCout.map((x) => x.valeur)) - cout : null;
  const res = {
    valeur: arrondi(valeur, 2),
    cout: avecCout.length ? arrondi(cout, 2) : null,
    plus_value: arrondi(plusValue, 2),
    plus_value_pct: cout > 0 && plusValue != null ? arrondi((plusValue / cout) * 100, 2) : null,
    couverture_cout: valeur > 0 ? arrondi((somme(avecCout.map((x) => x.valeur)) / valeur) * 100, 1) : 0,
    depuis_import: null,
    msci_depuis_import: null,
    date_import: reference?.date ?? null,
    historique: [],
  };
  if (reference?.valeur > 0 && valeur > 0) {
    res.depuis_import = arrondi((valeur / reference.valeur - 1) * 100, 2);
    const m0 = msciEuros(refs, reference.date);
    const m1 = msciEuros(refs, '9999-12-31');
    if (m0 && m1) res.msci_depuis_import = arrondi((m1 / m0 - 1) * 100, 2);
  }
  // Courbe base 100 : portefeuille et MSCI World en euros
  if (reference?.valeur > 0) {
    const points = [{ date: reference.date, valeur: reference.valeur }, ...historique.filter((h) => h.date > reference.date)];
    const m0 = msciEuros(refs, reference.date);
    res.historique = points.map((h) => ({
      date: h.date,
      portefeuille: arrondi((h.valeur / reference.valeur) * 100, 2),
      msci: m0 ? arrondi(((msciEuros(refs, h.date) ?? m0) / m0) * 100, 2) : null,
    }));
  }
  return res;
}
