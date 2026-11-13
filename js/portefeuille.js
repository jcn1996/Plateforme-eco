/* ==========================================================================
   Écran « Portefeuille démo » : portefeuille VIRTUEL de 100 000 € géré par
   l'agent trader à partir des recommandations du chef d'orchestre (aucun ordre
   réel). Valeur en direct, performance comparée au MSCI World en euros,
   indicateurs de risque, répartitions, positions, ordres en attente et fil
   des opérations avec leur justification.
   Données : data/portefeuille.json (agent trader, agents/trader/regles.md).
   ========================================================================== */

import { el, svg, nombre, variation, dateCourte } from './outils.js';
import { titreSection } from './panneau-pays.js';

const MENTION = 'Portefeuille fictif à but de démonstration, aucun ordre réel.';

function eurosPrecis(v, dec = 0) {
  if (v == null || Number.isNaN(v)) return 'n. d.';
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v);
}
const pct = (v, d = 2) => (v == null ? 'n. d.' : variation(v, d));
const classeSigne = (v) => (v > 0 ? 'hausse' : v < 0 ? 'baisse' : '');
const heureParis = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Paris' }) : '');

/** Texte court pour le bouton de l'en-tête : performance réelle depuis le départ. */
export function performanceEnTete(pf) {
  const p = pf?.statistiques?.performance?.depuis_debut;
  return p == null ? null : variation(p, 2);
}

export function ecranPortefeuille(d, nav) {
  const pf = d.portefeuille;
  if (!pf || pf.capital_initial == null || !pf.statistiques) {
    return [el('p', { class: 'chef-avertissement' }, 'Portefeuille démo indisponible : l’agent trader n’a pas encore produit de données.'),
      el('p', { class: 'chef-mention' }, MENTION)];
  }
  const st = pf.statistiques;
  const perf = st.performance ?? {};
  const ref = st.performance_msci_world ?? {};
  const ecart = perf.depuis_debut != null && ref.depuis_debut != null ? perf.depuis_debut - ref.depuis_debut : null;

  return [
    el('p', { class: 'pf-mention' }, MENTION),
    statut(pf),
    el('section', { class: 'carte' },
      el('div', { class: 'fiche-surtitre' }, `Valeur du portefeuille · départ ${eurosPrecis(pf.capital_initial)} le ${dateCourte(pf.date_debut)}`),
      el('div', { class: 'valeur-heros' }, eurosPrecis(pf.valeur_actuelle, 2)),
      el('p', { class: 'sous-heros' },
        el('span', { class: `mono ${classeSigne(pf.gain_eur)}` }, `${pf.gain_eur >= 0 ? '+' : '−'}${eurosPrecis(Math.abs(pf.gain_eur), 2)} (${pct(perf.depuis_debut)})`),
        ecart == null ? ' · MSCI World : référence en cours de constitution'
          : ` · ${ecart >= 0 ? 'devant' : 'derrière'} le MSCI World en euros de ${nombre(Math.abs(ecart), 2)} pt`,
      ),
      el('p', { class: 'chef-petit' }, `Mis à jour ${heureParis(pf.maj)} (heure de Paris) · palier de risque « ${pf.palier ?? 'n. d.'} » · profil « ${pf.profil_libelle ?? pf.profil} »`
        + (pf.cours_manquants?.length ? ` · dernier cours connu conservé pour ${pf.cours_manquants.join(', ')}` : '')),
    ),

    el('section', { class: 'kpis' },
      kpi('Depuis le départ', pct(perf.depuis_debut), `MSCI World : ${pct(ref.depuis_debut)}`, perf.depuis_debut),
      kpi('1 mois', pct(perf.un_mois), `MSCI World : ${pct(ref.un_mois)}`, perf.un_mois),
      kpi('3 mois', pct(perf.trois_mois), `MSCI World : ${pct(ref.trois_mois)}`, perf.trois_mois),
      kpi('Liquidités', `${nombre(pf.liquidites_pct ?? 0, 1)} %`, `minimum ${pf.liquidites_min ?? 'n. d.'} % (palier « ${pf.palier ?? 'n. d.'} »)`),
    ),

    el('section', { class: 'carte' },
      titreSection('Performance vs MSCI World', 'valeur de 100 000 € investis, en euros'),
      pf.historique?.length >= 2 ? graphiquePerformance(pf.historique)
        : el('p', { class: 'chef-petit' }, 'Historique en cours de constitution : un point par jour de valorisation. Le graphique apparaît dès le deuxième jour.'),
      el('p', { class: 'chef-petit' }, `Référence : ${pf.indice?.nom ?? 'MSCI World'} (source du jour : ${pf.indice?.source ?? 'n. d.'}).`),
    ),

    carteRisque(st),
    carteRepartition(pf),
    carteAttribution(st.attribution),

    el('section', { class: 'carte' },
      titreSection('Positions', `${pf.positions.length} ligne(s) · liquidités ${eurosPrecis(pf.liquidites)}`),
      pf.positions.length ? tableauPositions(pf.positions, d, nav) : el('p', { class: 'chef-petit' }, 'Aucune position pour l’instant.'),
    ),

    pf.ordres_en_attente?.length ? el('section', { class: 'carte' },
      titreSection('Ordres en attente', 'exécutés au premier cours disponible après la décision'),
      el('ul', { class: 'pf-fil' }, pf.ordres_en_attente.map((o) => el('li', {},
        el('div', { class: 'pf-op-tete' },
          el('span', { class: `pf-sens pf-sens--${o.sens}` }, o.sens === 'achat' ? 'Achat' : 'Vente'),
          el('strong', {}, o.nom),
          el('span', { class: 'mono' }, o.sens === 'achat' ? eurosPrecis(o.montant_eur) : `${o.quantite} part(s)`)),
        el('p', { class: 'chef-petit' }, `${o.motif}${o.imposee ? ' (imposé)' : ''} · décidé ${heureParis(o.cree_le)}`),
        justification(o.texte, o.donner_tort)))),
    ) : null,

    el('section', { class: 'carte' },
      titreSection('Dernières opérations', 'journal complet : data/trader/operations.json'),
      pf.operations?.length ? el('ul', { class: 'pf-fil' }, pf.operations.map(operation))
        : el('p', { class: 'chef-petit' }, 'Aucune opération exécutée pour l’instant.'),
    ),

    carteDecision(pf.derniere_decision),

    el('section', { class: 'carte' },
      titreSection('Règles de l’agent trader', 'agents/trader/regles.md'),
      el('ul', { class: 'chef-texte' }, (pf.regles ?? []).map((r) => el('li', {}, r))),
    ),
    el('p', { class: 'chef-mention' }, `${MENTION} Les performances passées ne préjugent pas des performances futures.`),
  ].filter(Boolean);
}

function statut(pf) {
  const s = pf.statut;
  const t = pf.transition?.lignes_hors_regles ? pf.transition : null;
  if ((!s || s.etat === 'actif') && !t) return null;
  return el('div', { class: 'chef-avertissement' },
    s && s.etat !== 'actif' ? el('p', {}, s.etat === 'en attente' ? `⏸ ${s.texte}` : `⏳ ${s.texte}`) : null,
    s?.depuis && s.etat !== 'actif' ? el('p', {}, `Depuis ${heureParis(s.depuis)}.`) : null,
    t ? el('p', {}, `↻ ${t.texte}`) : null);
}

function kpi(libelle, valeur, comparaison, signe) {
  return el('div', { class: 'stat' },
    el('div', { class: 'stat-libelle' }, libelle),
    el('div', { class: `stat-valeur ${signe == null ? '' : classeSigne(signe)}` }, valeur),
    el('div', { class: 'kpi-comparaison' }, comparaison),
  );
}

function carteRisque(st) {
  const r = st.risque ?? {};
  const m = st.risque_msci_world ?? {};
  const o = st.operations ?? {};
  const ligne = (lib, a, b) => el('tr', {}, el('td', {}, lib), el('td', { class: 'nombre' }, a), el('td', { class: 'nombre' }, b));
  return el('section', { class: 'carte' },
    titreSection('Indicateurs de risque'),
    el('table', { class: 'tableau' },
      el('thead', {}, el('tr', {}, el('th', {}, ''), el('th', { class: 'nombre' }, 'Portefeuille'), el('th', { class: 'nombre' }, 'MSCI World'))),
      el('tbody', {},
        ligne('Ratio de Sharpe', r.sharpe == null ? 'n. d.' : nombre(r.sharpe, 2), m.sharpe == null ? 'n. d.' : nombre(m.sharpe, 2)),
        ligne('Volatilité annualisée', r.volatilite == null ? 'n. d.' : `${nombre(r.volatilite, 1)} %`, m.volatilite == null ? 'n. d.' : `${nombre(m.volatilite, 1)} %`),
        ligne('Perte maximale', pct(r.perte_max, 1), pct(m.perte_max, 1)),
      )),
    r.raison ? el('p', { class: 'chef-petit' }, `Sharpe et volatilité : ${r.raison}.`) : null,
    el('div', { class: 'kpis pf-kpis-ops' },
      kpi('Opérations clôturées', String(o.cloturees ?? 0), `${o.achats ?? 0} achat(s), ${o.ventes ?? 0} vente(s)`),
      kpi('Taux de réussite', o.taux_reussite == null ? 'n. d.' : `${nombre(o.taux_reussite, 0)} %`, `${o.gagnantes ?? 0} gagnante(s), ${o.perdantes ?? 0} perdante(s)`),
      kpi('Gain moyen', pct(o.gain_moyen_pct, 1), 'ventes gagnantes', o.gain_moyen_pct),
      kpi('Perte moyenne', pct(o.perte_moyenne_pct, 1), 'ventes perdantes', o.perte_moyenne_pct),
    ),
    el('p', { class: 'chef-petit' }, o.definition ?? ''),
  );
}

function barre(liste, prefixe) {
  const total = liste.reduce((s, x) => s + x.pct, 0) || 1;
  return el('div', { class: 'chef-classes' }, liste.map((x) => el('span', {
    class: `chef-classe ${prefixe}${x.cle}`, style: { flexGrow: String(x.pct / total) }, title: `${x.libelle} : ${nombre(x.pct, 1)} %`,
  }, `${nombre(x.pct, 0)} %`)));
}

function listeBarres(liste, max = 8) {
  const haut = Math.max(...liste.map((x) => x.pct), 1);
  return el('ul', { class: 'pf-barres' }, liste.slice(0, max).map((x) => el('li', {},
    el('span', { class: 'pf-barres-nom' }, x.libelle),
    el('span', { class: 'pf-barres-jauge' }, el('span', { style: { width: `${(x.pct / haut) * 100}%` } })),
    el('span', { class: 'mono' }, `${nombre(x.pct, 1)} %`))));
}

function carteRepartition(pf) {
  const r = pf.repartition ?? {};
  const cibles = pf.cibles;
  return el('section', { class: 'carte' },
    titreSection('Répartition', 'en % de la valeur du portefeuille'),
    el('div', { class: 'fiche-surtitre' }, 'Cœur, satellites et liquidités'),
    barre(r.poches ?? [], 'pf-poche--'),
    el('p', { class: 'chef-repartition' }, (r.poches ?? []).map((x) => el('span', {}, el('span', { class: `chef-pastille pf-poche--${x.cle}` }), `${x.libelle} ${nombre(x.pct, 1)} %`))),
    cibles ? el('p', { class: 'chef-petit' }, `Cibles de la dernière décision : cœur ${nombre(cibles.coeur, 1)} %, satellites ${nombre(cibles.satellite, 1)} %, liquidités ${nombre(cibles.liquidites, 1)} %.`) : null,
    el('div', { class: 'fiche-surtitre' }, 'Classes d’actifs'),
    barre(r.classes ?? [], 'chef-classe--'),
    el('p', { class: 'chef-repartition' }, (r.classes ?? []).map((x) => el('span', {}, el('span', { class: `chef-pastille chef-classe--${x.cle}` }), `${x.libelle} ${nombre(x.pct, 1)} %`))),
    el('div', { class: 'pf-deux' },
      el('div', {}, el('div', { class: 'fiche-surtitre' }, 'Par pays'), listeBarres(r.pays ?? [])),
      el('div', {}, el('div', { class: 'fiche-surtitre' }, 'Par secteur'), listeBarres(r.secteurs ?? [])),
    ),
  );
}

function carteAttribution(a) {
  if (!a) return null;
  const tableau = (liste) => el('table', { class: 'tableau' }, el('tbody', {}, liste.map((x) => el('tr', {},
    el('td', {}, x.libelle),
    el('td', { class: `nombre ${classeSigne(x.eur)}` }, `${x.eur >= 0 ? '+' : '−'}${eurosPrecis(Math.abs(x.eur))}`),
    el('td', { class: `nombre ${classeSigne(x.points)}` }, `${x.points >= 0 ? '+' : '−'}${nombre(Math.abs(x.points), 2)} pt`)))));
  return el('section', { class: 'carte' },
    titreSection('Attribution de la performance', 'plus-values réalisées et latentes, frais compris'),
    a.poches?.length ? tableau(a.poches) : el('p', { class: 'chef-petit' }, 'Rien à attribuer tant qu’aucune position n’est ouverte.'),
    a.familles?.length ? el('div', {}, el('div', { class: 'fiche-surtitre' }, 'Par famille de signaux du chef d’orchestre'), tableau(a.familles)) : null,
    el('p', { class: 'chef-petit' }, `Frais payés : ${eurosPrecis(a.frais_eur, 2)} · coût estimé des écarts achat/vente : ${eurosPrecis(a.ecarts_eur, 2)}. ${a.methode ?? ''}`),
  );
}

function tableauPositions(positions, d, nav) {
  return el('table', { class: 'chef-table pf-positions' },
    el('thead', {}, el('tr', {}, ['Ligne', 'Revient / cours', 'Plus-value', 'Poids', 'Stop'].map((t) => el('th', {}, t)))),
    el('tbody', {}, positions.map((p) => {
      const lien = p.ticker && d.entrepriseParTicker?.has(p.ticker);
      return el('tr', {},
        el('td', {},
          lien ? el('button', { class: 'lien', type: 'button', onclick: () => nav.ouvrirEntreprise(p.ticker) }, p.nom) : el('span', {}, p.nom),
          el('br'), el('span', { class: 'poche' }, `${p.poche === 'satellite' ? 'Satellite' : 'Cœur'} · ${p.symbole}${p.contango ? ' · contango' : ''}`)),
        el('td', { class: 'mono' }, `${nombre(p.prix_revient_local, 2)}`, el('br'), p.cours_local == null ? 'n. d.' : `${nombre(p.cours_local, 2)}`,
          el('br'), el('span', { class: 'poche pf-devise' }, `${p.quantite} × · ${p.devise}`)),
        el('td', { class: `mono ${classeSigne(p.plus_value_eur)}` }, `${p.plus_value_eur >= 0 ? '+' : '−'}${eurosPrecis(Math.abs(p.plus_value_eur))}`, el('br'), pct(p.plus_value_pct, 1)),
        el('td', { class: 'mono' }, `${nombre(p.poids, 1)} %`, el('br'), eurosPrecis(p.valeur)),
        el('td', { class: 'mono' }, p.stop_local == null ? '—' : `${nombre(p.stop_local, 2)}`,
          p.stop_local == null ? null : el('br'), p.stop_local == null ? null : el('span', { class: 'poche' }, `${p.stop_type ?? ''} ${pct(p.stop_distance_pct, 1)}`)),
      );
    })),
  );
}

function justification(texte, donnerTort) {
  return el('details', { class: 'pf-justif' },
    el('summary', {}, 'Justification'),
    texte ? el('p', {}, texte) : null,
    donnerTort?.length ? el('div', {}, el('div', { class: 'fiche-surtitre' }, 'Ce qui pourrait me donner tort'),
      el('ul', { class: 'chef-texte' }, donnerTort.map((x) => el('li', {}, x)))) : null,
  );
}

function operation(o) {
  const r = o.raison ?? {};
  const res = o.resultat;
  const details = [
    r.verdict ? `verdict « ${r.verdict} »` : null,
    r.conviction ? `conviction ${r.conviction}` : null,
    r.score != null ? `score ${nombre(r.score, 0)}/100` : null,
    r.agents?.length ? `agents : ${r.agents.join(', ')}` : null,
  ].filter(Boolean).join(' · ');
  return el('li', {},
    el('div', { class: 'pf-op-tete' },
      el('span', { class: `pf-sens pf-sens--${o.sens}` }, o.sens === 'achat' ? 'Achat' : 'Vente'),
      el('strong', {}, o.nom),
      el('span', { class: 'mono' }, eurosPrecis(o.montant_eur))),
    el('p', { class: 'chef-petit' },
      `${heureParis(o.date)} · ${o.quantite} × ${nombre(o.prix_local, 2)} ${o.devise} (cours ${nombre(o.cours_marche, 2)}) · frais ${eurosPrecis(o.frais_eur, 2)} · ${o.motif}`
      + (o.stop ? ` · stop ${nombre(o.stop, 2)}` : '')),
    res ? el('p', { class: `chef-petit ${classeSigne(res.plus_value_eur)}` }, `Résultat : ${res.plus_value_eur >= 0 ? '+' : '−'}${eurosPrecis(Math.abs(res.plus_value_eur), 2)} (${pct(res.plus_value_pct, 1)})${res.duree_jours != null ? ` en ${res.duree_jours} j` : ''}`) : null,
    details ? el('p', { class: 'chef-petit' }, details) : null,
    r.objection ? el('p', { class: 'chef-petit' }, `Objection du contradicteur${r.objection_serieuse ? ' (sérieuse)' : ''} : ${r.objection}`) : null,
    justification(r.texte, o.donner_tort),
  );
}

function carteDecision(dec) {
  if (!dec) return null;
  return el('section', { class: 'carte decision' },
    el('div', { class: 'decision-entete' }, el('span', {}, 'Dernière décision · agent trader'), el('span', { class: 'mono' }, heureParis(dec.le))),
    el('p', {}, dec.resume),
    dec.notes?.length || dec.avertissements?.length ? el('ul', { class: 'chef-texte' }, [...(dec.notes ?? []), ...(dec.avertissements ?? [])].map((x) => el('li', {}, x))) : null,
    diversification(dec),
    dec.cibles?.lignes?.length ? el('details', { class: 'pf-justif' }, el('summary', {}, `Cibles (${dec.cibles.lignes.length} lignes)`),
      el('ul', { class: 'chef-texte' }, dec.cibles.lignes.map((x) => el('li', {},
        `${x.nom} — ${x.poche === 'satellite' ? 'satellite' : 'cœur'}, ${x.zone ?? x.classe} : ${nombre(x.cible, 1)} %`
        + (x.verdict ? ` (« ${x.verdict} », conviction ${x.conviction})` : ''))))) : null,
    dec.arbitrages?.length ? el('details', { class: 'pf-justif', open: true }, el('summary', {}, `Arbitrages expliqués (${dec.arbitrages.length})`),
      el('ul', { class: 'chef-texte' }, dec.arbitrages.map((a) => el('li', {}, el('strong', {}, `${a.nom} — ${a.action}`), ` : ${a.raison}`)))) : null,
    dec.satellites_ecartes?.length ? el('details', { class: 'pf-justif' }, el('summary', {}, `Opportunités écartées (${dec.satellites_ecartes.length})`),
      el('ul', { class: 'chef-texte' }, dec.satellites_ecartes.map((x) => el('li', {}, `${x.nom} : ${x.raison}`)))) : null,
    dec.donner_tort?.length ? el('div', {}, el('div', { class: 'fiche-surtitre' }, 'Ce qui pourrait me donner tort'),
      el('ul', { class: 'chef-texte' }, dec.donner_tort.map((x) => el('li', {}, x)))) : null,
  );
}

function diversification(dec) {
  const dv = dec.diversification;
  if (!dv) return null;
  const cm = dv.correlation_max;
  return el('p', { class: 'chef-petit' },
    `Diversification : ${dv.nombre_zones} classes ou zones (${(dv.zones ?? []).join(', ')})`
    + (dv.correlation_moyenne == null ? ' ; corrélations non mesurables (historique insuffisant).'
      : ` ; corrélation moyenne sur 1 an ${nombre(dv.correlation_moyenne, 2)}, maximum ${nombre(cm.valeur, 2)} (${cm.entre.join(' / ')}) ;`
        + ` ${dv.paires_mesurees} paires mesurées sur ${dv.paires_possibles}.`));
}

/* ---------------- Graphique linéaire (SVG, sans bibliothèque) ---------------- */

const SERIES = [
  { cle: 'portefeuille', nom: 'Portefeuille', couleur: 'var(--serie-portefeuille)' },
  { cle: 'msci_world', nom: 'MSCI World', couleur: 'var(--serie-indice)' },
];

function graphiquePerformance(historique) {
  const L = Math.round(Math.min(780, Math.max(300, innerWidth - 58))), H = 240;
  const m = { haut: 12, droite: 78, bas: 26, gauche: 50 };
  const n = historique.length;
  const series = SERIES.filter((s) => historique.some((h) => h[s.cle] != null));
  const valeurs = historique.flatMap((h) => series.map((s) => h[s.cle])).filter((v) => v != null);
  const ampleur = Math.max(...valeurs) - Math.min(...valeurs);
  const pas = [250, 500, 1000, 2500, 5000, 10000, 25000].find((p) => ampleur / p <= 6) ?? 50000;
  const yMin = Math.floor(Math.min(...valeurs) / pas) * pas;
  const yMax = Math.max(Math.ceil(Math.max(...valeurs) / pas) * pas, yMin + pas);
  const x = (i) => m.gauche + (i / (n - 1)) * (L - m.gauche - m.droite);
  const y = (v) => H - m.bas - ((v - yMin) / (yMax - yMin)) * (H - m.haut - m.bas);

  const grille = svg('g', { class: 'grille' });
  const axe = svg('g', { class: 'axe' });
  for (let v = yMin; v <= yMax; v += pas) {
    grille.append(svg('line', { x1: m.gauche, x2: L - m.droite, y1: y(v), y2: y(v) }));
    axe.append(svg('text', { x: m.gauche - 8, y: y(v) + 3, 'text-anchor': 'end' }, `${nombre(v / 1000, pas % 1000 ? (pas % 100 ? 2 : 1) : 0)} k€`));
  }
  const reperes = Math.min(L < 500 ? 4 : 6, n);
  for (let k = 0; k < reperes; k += 1) {
    const i = Math.round((k / Math.max(1, reperes - 1)) * (n - 1));
    axe.append(svg('text', { x: x(i), y: H - 6, 'text-anchor': 'middle' },
      new Date(`${historique[i].date}T12:00:00`).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })));
  }

  const courbes = svg('g', {});
  const dernier = (cle) => [...historique].reverse().find((h) => h[cle] != null)?.[cle];
  const etiquettes = series.map((s) => ({ s, yFin: y(dernier(s.cle)) }));
  if (etiquettes.length === 2 && Math.abs(etiquettes[0].yFin - etiquettes[1].yFin) < 14) {
    const [haut, bas] = etiquettes[0].yFin < etiquettes[1].yFin ? etiquettes : [etiquettes[1], etiquettes[0]];
    haut.yFin -= 7; bas.yFin += 7;
  }
  for (const { s, yFin } of etiquettes) {
    let d = '';
    historique.forEach((h, i) => { if (h[s.cle] != null) d += `${d ? 'L' : 'M'}${x(i).toFixed(1)},${y(h[s.cle]).toFixed(1)}`; });
    courbes.append(svg('path', { class: 'serie', d, stroke: s.couleur }));
    courbes.append(svg('text', { class: 'etiquette-serie', x: L - m.droite + 8, y: yFin + 4 }, s.nom));
  }

  const ligneCurseur = svg('line', { y1: m.haut, y2: H - m.bas });
  const points = series.map((s) => svg('circle', { r: 4.5, fill: s.couleur }));
  const curseur = svg('g', { class: 'curseur', visibility: 'hidden' }, ligneCurseur, ...points);
  const zone = svg('rect', { x: m.gauche, y: 0, width: L - m.gauche - m.droite, height: H, fill: 'transparent' });
  const dessin = svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img', 'aria-label': 'Évolution du portefeuille démo comparée au MSCI World en euros' },
    grille, axe, courbes, curseur, zone);
  const bulle = el('div', { class: 'infobulle', hidden: true });

  const montrer = (ev) => {
    const boite = dessin.getBoundingClientRect();
    const xSvg = ((ev.clientX - boite.left) / boite.width) * L;
    const i = Math.round(((xSvg - m.gauche) / (L - m.gauche - m.droite)) * (n - 1));
    if (i < 0 || i >= n) return;
    const h = historique[i];
    ligneCurseur.setAttribute('x1', x(i));
    ligneCurseur.setAttribute('x2', x(i));
    series.forEach((s, k) => {
      points[k].setAttribute('visibility', h[s.cle] == null ? 'hidden' : 'visible');
      if (h[s.cle] != null) { points[k].setAttribute('cx', x(i)); points[k].setAttribute('cy', y(h[s.cle])); }
    });
    curseur.setAttribute('visibility', 'visible');
    bulle.replaceChildren(
      el('div', { class: 'infobulle-date' }, dateCourte(h.date)),
      ...series.map((s) => el('div', { class: 'infobulle-ligne' },
        el('span', {}, el('span', { class: 'trait', style: { background: s.couleur } }), s.nom),
        el('span', { class: 'mono' }, h[s.cle] == null ? 'n. d.' : eurosPrecis(h[s.cle])))),
    );
    bulle.hidden = false;
    const px = (x(i) / L) * boite.width;
    const largeurBulle = bulle.offsetWidth;
    bulle.style.left = `${Math.min(Math.max(0, px + 12), boite.width - largeurBulle)}px`;
    if (px + 12 + largeurBulle > boite.width) bulle.style.left = `${Math.max(0, px - largeurBulle - 12)}px`;
  };
  const cacher = () => { curseur.setAttribute('visibility', 'hidden'); bulle.hidden = true; };
  zone.addEventListener('pointermove', montrer);
  zone.addEventListener('pointerdown', montrer);
  zone.addEventListener('pointerleave', cacher);

  return el('div', {},
    el('div', { class: 'legende-graphique' },
      series.map((s) => el('span', {}, el('span', { class: 'trait', style: { background: s.couleur } }), s.nom))),
    el('div', { class: 'graphique' }, dessin, bulle),
  );
}
