/* ==========================================================================
   Réseau des agents (accueil) : logique sans affichage, testée avec node --test.
   - lecture de la table de correspondance config/reseau_agents.json :
     une information par bulle, lue dans les données existantes ;
   - état de chaque agent (OK, dégradé, en panne ou données périmées) d'après son
     journal (data/journal/*.json, statut calculé comme l'écran « Santé des agents »)
     et le bloc « entrees » de data/chef.json ;
   - disposition des bulles et séparation des libellés (jamais superposés) ;
   - contenu de la carte « À retenir aujourd'hui » (sélections du chef d'orchestre).
   ========================================================================== */

export const CONFIG_RESEAU = 'config/reseau_agents.json';

/** États d'un agent : libellé lisible (les états ne reposent jamais sur la couleur seule). */
export const ETATS_RESEAU = {
  ok: { libelle: 'OK', court: '' },
  degrade: { libelle: 'Dégradé', court: '⚠ dégradé' },
  panne: { libelle: 'En panne', court: '✕ en panne' },
  perimee: { libelle: 'Données périmées', court: '✕ périmé' },
};

/* ------------------------------------------------------------------ table de correspondance */

/** Valeur au bout d'un chemin « a.b.0.c » (un nombre = rang dans une liste) ; chemin vide = l'objet entier. */
export function lireChemin(objet, chemin) {
  if (!chemin) return objet;
  let x = objet;
  for (const segment of String(chemin).split('.')) {
    if (x == null) return undefined;
    x = Array.isArray(x) && /^\d+$/.test(segment) ? x[Number(segment)] : x[segment];
  }
  return x;
}

const fr = (n, dec = 0) => new Intl.NumberFormat('fr-FR', { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(n);

/** Applique le modèle (« {} » remplacé ; [singulier, pluriel] accordé selon le nombre). */
function appliquerModele(modele, texte, nombreAccord) {
  const m = Array.isArray(modele) ? modele[nombreAccord != null && Math.abs(nombreAccord) < 2 ? 0 : modele.length - 1] : (modele ?? '{}');
  return m.replace('{}', texte);
}

/**
 * Information d'une bulle d'après sa ligne de la table de correspondance et les données du fichier.
 * Retourne { texte, valeur } ; texte null si la donnée manque (fichier absent ou chemin introuvable).
 */
export function lireInfo(spec, donnees) {
  if (!spec || donnees == null) return { texte: null, valeur: null };
  const brute = lireChemin(donnees, spec.chemin);
  if (brute == null) return { texte: null, valeur: null };
  switch (spec.mesure) {
    case 'longueur': {
      const n = Array.isArray(brute) ? brute.length : typeof brute === 'object' ? Object.keys(brute).length : null;
      return n == null ? { texte: null, valeur: null } : { texte: appliquerModele(spec.modele, fr(n), n), valeur: n };
    }
    case 'compte': {
      if (!Array.isArray(brute)) return { texte: null, valeur: null };
      const n = brute.filter((x) => (spec.champ ? x?.[spec.champ] != null : x != null)).length;
      return { texte: appliquerModele(spec.modele, fr(n), n), valeur: n };
    }
    case 'pourcentage': {
      const v = Number(brute);
      if (!Number.isFinite(v)) return { texte: null, valeur: null };
      const signe = v > 0 ? '+' : v < 0 ? '−' : '';
      return { texte: appliquerModele(spec.modele, `${signe}${fr(Math.abs(v), spec.decimales ?? 1)} %`, null), valeur: v };
    }
    default: {
      const texte = typeof brute === 'number' ? fr(brute, spec.decimales ?? 0) : String(brute);
      return { texte: appliquerModele(spec.modele, texte, typeof brute === 'number' ? brute : null), valeur: brute };
    }
  }
}

/** Fichiers de données cités par la table de correspondance (sans doublon). */
export function fichiersReseau(config) {
  return [...new Set([config?.centre, ...(config?.agents ?? [])].map((a) => a?.info?.fichier).filter(Boolean))];
}

/* ------------------------------------------------------------------ état des agents */

const dateHeure = (iso) => {
  const t = Date.parse(iso ?? '');
  if (!Number.isFinite(t)) return null;
  return new Date(t).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Paris' });
};

/**
 * État d'un agent.
 * - statutJournal : statut calculé par l'écran « Santé des agents » (ok, pause, retard, degrade, panne) ou undefined ;
 * - journal : bloc santé fusionné (derniere_execution, raisons…) ou null ;
 * - entrees : lignes du bloc « entrees » de data/chef.json pour cet agent.
 * Priorité : en panne > données périmées > dégradé > OK.
 */
export function etatAgent({ statutJournal, journal, entrees = [] } = {}) {
  const raisons = [];
  let etat = 'ok';
  const derniere = dateHeure(journal?.derniere_execution);
  if (statutJournal === 'panne') {
    etat = 'panne';
    raisons.push(derniere ? `Pas d’exécution réussie attendue depuis le ${derniere}.` : 'Journal illisible ou sans exécution réussie.');
  }
  const perimees = entrees.filter((e) => e?.etat === 'périmée' || e?.etat === 'manquante');
  if (perimees.length) {
    if (etat === 'ok') etat = 'perimee';
    perimees.forEach((e) => raisons.push(e.etat === 'manquante'
      ? `${e.libelle ?? e.cle} : données manquantes pour le chef d’orchestre.`
      : `${e.libelle ?? e.cle} : données de ${fr(e.age_h ?? 0)} h, périmées pour le chef d’orchestre (elles pèsent moins).`));
  }
  const degradees = entrees.filter((e) => e?.degrade);
  if (etat === 'ok' && (statutJournal === 'degrade' || statutJournal === 'retard' || degradees.length)) etat = 'degrade';
  if (statutJournal === 'retard') raisons.push('Exécution en retard sur le planning.');
  if (statutJournal === 'degrade') (journal?.raisons ?? []).slice(0, 3).forEach((r) => raisons.push(String(r)));
  degradees.forEach((e) => (e.raisons_degrade ?? []).slice(0, 3).forEach((r) => { if (!raisons.includes(r)) raisons.push(r); }));
  return { etat, raisons, derniere };
}

/**
 * Nœuds du réseau : centre (chef d'orchestre) puis les agents, dans l'ordre de la configuration.
 * - sources : { 'data/chef.json': donnees, … } (bloc « donnees », undefined = pas encore lu) ;
 * - sante : { cleJournal: { statut, journal } } ;
 * - entrees : bloc « entrees » de data/chef.json.
 */
export function calculerReseau(config, { sources = {}, sante = {}, entrees = [] } = {}) {
  const parCle = new Map((entrees ?? []).map((e) => [e.cle, e]));
  const noeud = (a, centre) => {
    const donnees = sources[a.info?.fichier];
    const info = lireInfo(a.info, donnees);
    const s = sante[a.journal] ?? {};
    const etat = etatAgent({ statutJournal: s.statut, journal: s.journal, entrees: (a.entrees ?? []).map((c) => parCle.get(c)).filter(Boolean) });
    return {
      cle: a.cle, nom: a.nom, role: a.role ?? null, centre,
      poids: centre ? 'decision' : (a.poids === 'decision' ? 'decision' : 'contexte'),
      sens: a.sens === 'depuis_centre' ? 'depuis_centre' : 'vers_centre',
      route: a.route ?? null, action: a.action ?? null, description: a.description ?? '',
      info: info.texte ?? (donnees === undefined ? '…' : 'n. d.'), valeur: info.valeur,
      chargee: donnees !== undefined,
      ...etat,
    };
  };
  return { centre: noeud(config.centre, true), agents: (config.agents ?? []).map((a) => noeud(a, false)) };
}

/** Texte lisible d'un nœud pour un lecteur d'écran (le bouton porte ce nom). */
export function texteAccessible(n) {
  const parties = [n.centre ? `${n.nom}, ${n.role ?? 'chef d’orchestre'}` : n.nom, n.info];
  if (!n.centre) parties.push(n.poids === 'decision' ? 'pèse dans la décision' : 'contexte');
  parties.push(`état : ${ETATS_RESEAU[n.etat]?.libelle ?? n.etat}`);
  return `${parties.filter(Boolean).join(' · ')}. ${n.centre ? 'Ouvrir « Où investir »' : 'Ouvrir la synthèse de l’agent'}.`;
}

/* ------------------------------------------------------------------ disposition */

/**
 * Position des agents autour du centre, en profondeur (style « neurones ») : ellipse dans le plan
 * de l'écran, en commençant en haut, dans le sens des aiguilles d'une montre ; profondeur alternée.
 * Coordonnées normalisées (x et y entre −1 et 1, y vers le haut ; z entre −1 et 1).
 */
export function disposition(n) {
  return Array.from({ length: n }, (_, i) => {
    const angle = Math.PI / 2 - (i * 2 * Math.PI) / n;
    const z = i % 2 === 0 ? 0.55 : -0.55;
    return { x: Math.cos(angle), y: Math.sin(angle), z: i % 3 === 2 ? z * 0.4 : z };
  });
}

const chevauche = (a, b, marge) => a.x < b.x + b.l + marge && b.x < a.x + a.l + marge && a.y < b.y + b.h + marge && b.y < a.y + a.h + marge;

/**
 * Sépare les libellés (rectangles { x, y, l, h, ax, ay }, ax/ay = position souhaitée) pour qu'aucun ne
 * se superpose à un autre ni à une bulle (obstacles { x, y, l, h, proprietaire } : la bulle de son
 * propre libellé est ignorée). Les libellés restent dans le cadre { l, h } s'il est donné.
 * Modifie et renvoie la liste.
 */
export function separerEtiquettes(etiquettes, obstacles = [], cadre = null, { marge = 2, iterations = 120 } = {}) {
  const borner = (e) => {
    if (!cadre) return;
    e.x = Math.min(Math.max(e.x, 2), Math.max(2, cadre.l - e.l - 2));
    e.y = Math.min(Math.max(e.y, 2), Math.max(2, cadre.h - e.h - 2));
  };
  /** Écarte a de b (b fixe si `seul`) selon l'axe du plus petit recouvrement, l'autre axe si le cadre bloque. */
  const ecarter = (a, b, seul) => {
    const dx = Math.min(a.x + a.l, b.x + b.l) - Math.max(a.x, b.x) + marge;
    const dy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) + marge;
    const axes = dy <= dx ? ['y', 'x'] : ['x', 'y'];
    for (const axe of axes) {
      const taille = axe === 'y' ? 'h' : 'l';
      const d = axe === 'y' ? dy : dx;
      const sens = a[axe] + a[taille] / 2 <= b[axe] + b[taille] / 2 ? -1 : 1;
      const avant = [a.x, a.y, b.x, b.y];
      if (seul) a[axe] += sens * (d + 0.5);
      else { a[axe] += sens * (d / 2 + 0.5); b[axe] -= sens * (d / 2 + 0.5); }
      borner(a); if (!seul) borner(b);
      if (!chevauche(a, b, marge - 0.01)) return;
      // Bloqué par le bord du cadre : on annule et on essaie l'autre axe
      [a.x, a.y, b.x, b.y] = avant;
    }
    // Les deux axes sont bloqués : on pousse quand même sur l'axe principal (le cadre l'emporte)
    const axe = axes[0], taille = axe === 'y' ? 'h' : 'l', d = axe === 'y' ? dy : dx;
    const sens = a[axe] + a[taille] / 2 <= b[axe] + b[taille] / 2 ? -1 : 1;
    if (seul) a[axe] += sens * (d + 0.5); else { a[axe] += sens * (d / 2 + 0.5); b[axe] -= sens * (d / 2 + 0.5); }
    borner(a); if (!seul) borner(b);
  };
  etiquettes.forEach(borner);
  for (let k = 0; k < iterations; k++) {
    let bouge = false;
    // Les bulles des autres agents sont évitées pendant les deux premiers tiers ; ensuite seuls
    // les libellés comptent (ils ne doivent jamais se superposer entre eux).
    if (k < (iterations * 2) / 3) {
      for (const a of etiquettes) {
        for (const o of obstacles) {
          if (o.proprietaire === a.cle || !chevauche(a, o, marge)) continue;
          bouge = true;
          ecarter(a, o, true);
        }
      }
    }
    for (let i = 0; i < etiquettes.length; i++) {
      for (let j = i + 1; j < etiquettes.length; j++) {
        if (!chevauche(etiquettes[i], etiquettes[j], marge)) continue;
        bouge = true;
        ecarter(etiquettes[i], etiquettes[j], false);
      }
    }
    if (!bouge) break;
  }
  // Repli (cas serrés où la relaxation se bloque) : chaque libellé encore superposé cherche, en
  // spirale autour de sa position, la place libre la plus proche. Garantit l'absence de superposition
  // dès qu'il reste de la place.
  if (chevauchements(etiquettes).length) {
    const places = [];
    for (const e of etiquettes) {
      if (places.some((p) => chevauche(e, p, marge))) {
        const x0 = e.x, y0 = e.y;
        trouve: for (let r = 4; r < 2000; r += 4) {
          for (let k = 0; k < 24; k++) {
            const angle = (k / 24) * 2 * Math.PI + Math.PI / 2; // d'abord vers le bas
            e.x = x0 + r * Math.cos(angle);
            e.y = y0 + r * Math.sin(angle);
            borner(e);
            if (!places.some((p) => chevauche(e, p, marge))) break trouve;
          }
        }
      }
      places.push(e);
    }
  }
  return etiquettes;
}

/** Vrai si deux libellés au moins se superposent (sert aux tests et à la vérification). */
export function chevauchements(etiquettes) {
  const paires = [];
  for (let i = 0; i < etiquettes.length; i++) {
    for (let j = i + 1; j < etiquettes.length; j++) if (chevauche(etiquettes[i], etiquettes[j], 0)) paires.push([etiquettes[i].cle, etiquettes[j].cle]);
  }
  return paires;
}

/* ------------------------------------------------------------------ carte « À retenir aujourd'hui » */

/**
 * Contenu de la carte « À retenir aujourd'hui », tiré des sélections du chef d'orchestre :
 * entreprises et matières premières retenues (à acheter), paris pays, lignes à revendre, alerte du jour.
 */
export function aRetenir(chef, alertes = [], { max = 5 } = {}) {
  const alerte = [...(alertes ?? [])].sort((a, b) => (a.rang ?? 99) - (b.rang ?? 99))[0] ?? null;
  const li = chef?.liste;
  let entreprises, matieres, paris, sorties;
  if (li?.lignes) {
    // Liste unique du chef d'orchestre (révisée une fois par mois) : même ordre que « Où investir »
    const de = (k) => li.lignes.filter((l) => l.categorie === k);
    entreprises = de('entreprises');
    matieres = de('matieres');
    paris = de('pays');
    sorties = (li.mouvements ?? []).filter((m) => m.sens === 'sortie').map((m) => ({ ...m, cle: m.categorie === 'pays' ? m.id.replace(/^pays-/, '') : null }));
  } else {
    // Ancienne sortie du chef d'orchestre (sans liste unique) : sélections du jour
    const sel = chef?.selections ?? {};
    const parScore = (l) => [...(l ?? [])].sort((a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity));
    entreprises = parScore(sel.entreprises?.retenues);
    matieres = parScore(sel.matieres?.retenues);
    paris = (sel.paris_pays?.candidats ?? []).filter((c) => c.entree_ok !== false && !c.sortie);
    sorties = sel.paris_pays?.a_revendre ?? [];
  }
  return {
    date: li?.revise_le ?? chef?.selections?.date ?? chef?.date ?? null,
    entreprises: { lignes: entreprises.slice(0, max).map((e) => ({ id: e.id, nom: e.nom, ticker: e.ticker ?? e.symbole, pays: e.pays })), total: entreprises.length },
    matieres: { lignes: matieres.slice(0, max).map((m) => ({ id: m.id, nom: m.nom, cle: m.cle })), total: matieres.length },
    paris: { lignes: paris.slice(0, max).map((p) => ({ id: p.id, nom: p.nom, code: p.cle, symbole: p.symbole })), total: paris.length },
    aRevendre: { lignes: sorties.slice(0, max).map((p) => ({ id: p.id, nom: p.nom, code: p.cle, symbole: p.symbole, texte: p.texte })), total: sorties.length },
    alerte: alerte ? { titre: alerte.titre, texte: alerte.texte || null, route: alerte.route ?? (alerte.pays ? { type: 'pays', id: alerte.pays } : null) } : null,
  };
}
