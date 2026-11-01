/* ==========================================================================
   Écran « Portefeuille démo » : 100 000 € fictifs, structure cœur-satellite,
   performance comparée au MSCI World, ratio de Sharpe, perte maximale,
   positions et dernière décision de l'agent trader.
   ========================================================================== */

import { el, svg, euros, nombre, variation, dateCourte, AGENTS } from './outils.js';
import { titreSection } from './panneau-pays.js';

export function ecranPortefeuille(d, nav) {
  const pf = d.portefeuille;
  const st = pf.statistiques;
  const gain = pf.valeur_actuelle - pf.capital_initial;
  const ecart = st.performance_totale - st.performance_msci_world;

  return [
    el('section', { class: 'carte' },
      el('div', { class: 'fiche-surtitre' }, `Valeur du portefeuille · départ ${euros(pf.capital_initial)} le ${dateCourte(pf.date_debut)}`),
      el('div', { class: 'valeur-heros' }, euros(pf.valeur_actuelle)),
      el('p', { class: 'sous-heros' },
        el('span', { class: `mono ${gain >= 0 ? 'hausse' : 'baisse'}` }, `${gain >= 0 ? '+' : '−'}${euros(Math.abs(gain))} (${variation(st.performance_totale, 2)})`),
        ` · ${ecart >= 0 ? 'devant' : 'derrière'} le MSCI World de ${nombre(Math.abs(ecart), 2)} pt`,
      ),
    ),

    el('section', { class: 'kpis' },
      kpi('Performance', variation(st.performance_totale, 2), `MSCI World : ${variation(st.performance_msci_world, 2)}`, st.performance_totale >= 0),
      kpi('Écart vs indice', variation(ecart, 2, ' pt'), 'surperformance', ecart >= 0),
      kpi('Ratio de Sharpe', nombre(st.sharpe, 2), `MSCI World : ${nombre(st.sharpe_msci_world, 2)}`),
      kpi('Perte maximale', variation(st.perte_max, 1), `MSCI World : ${variation(st.perte_max_msci_world, 1)}`, false),
    ),

    el('section', { class: 'carte' },
      titreSection('Performance vs MSCI World', 'valeur de 100 000 € investis'),
      graphiquePerformance(pf.historique),
    ),

    el('section', { class: 'carte' },
      titreSection('Structure cœur-satellite'),
      el('div', { class: 'allocation', role: 'img', 'aria-label': `Cœur ${pf.allocation.coeur} %, satellite ${pf.allocation.satellite} %` },
        el('span', { class: 'allocation-coeur', style: { width: `${pf.allocation.coeur}%` } }),
        el('span', { class: 'allocation-satellite', style: { width: `${pf.allocation.satellite}%` } }),
      ),
      el('div', { class: 'allocation-legende' },
        el('span', {}, el('span', { class: 'carre allocation-coeur' }), `Cœur ${pf.allocation.coeur} % — ETF larges et diversifiés`),
        el('span', {}, el('span', { class: 'carre allocation-satellite' }), `Satellite ${pf.allocation.satellite} % — convictions des agents`),
      ),
    ),

    el('section', { class: 'carte' },
      titreSection('Positions'),
      tableauPositions(pf.positions, d, nav),
    ),

    el('section', { class: 'carte decision' },
      el('div', { class: 'decision-entete' },
        el('span', {}, `Dernière décision · ${AGENTS[pf.derniere_decision.agent] ?? pf.derniere_decision.agent}`),
        el('span', { class: 'mono' }, `${dateCourte(pf.derniere_decision.date)} · ${pf.derniere_decision.heure}`),
      ),
      el('h3', { class: 'decision-titre' }, pf.derniere_decision.titre),
      el('p', {}, pf.derniere_decision.texte),
    ),

    el('p', { class: 'mention-legale' }, 'Portefeuille entièrement fictif géré par un agent de démonstration. Les performances passées ne préjugent pas des performances futures.'),
  ];
}

function kpi(libelle, valeur, comparaison, positif) {
  const couleur = positif === undefined ? '' : positif ? 'hausse' : 'baisse';
  return el('div', { class: 'stat' },
    el('div', { class: 'stat-libelle' }, libelle),
    el('div', { class: `stat-valeur ${couleur}` }, valeur),
    el('div', { class: 'kpi-comparaison' }, comparaison),
  );
}

function tableauPositions(positions, d, nav) {
  return el('table', { class: 'tableau' },
    el('thead', {}, el('tr', {},
      el('th', {}, 'Ligne'),
      el('th', { class: 'nombre' }, 'Poids'),
      el('th', { class: 'nombre' }, 'Valeur'),
      el('th', { class: 'nombre' }, 'Perf.'),
    )),
    el('tbody', {}, positions.map((p) => {
      // Les positions liées à une entreprise suivie ouvrent sa fiche
      const lien = p.ticker && d.entrepriseParTicker.has(p.ticker);
      return el('tr', {
        class: lien ? 'cliquable' : undefined,
        tabindex: lien ? '0' : undefined,
        role: lien ? 'link' : undefined,
        onclick: lien ? () => nav.ouvrirEntreprise(p.ticker) : undefined,
        onkeydown: lien ? (ev) => { if (ev.key === 'Enter') nav.ouvrirEntreprise(p.ticker); } : undefined,
      },
        el('td', {}, p.nom, el('br'), el('span', { class: 'poche' }, p.poche === 'coeur' ? 'Cœur' : 'Satellite')),
        el('td', { class: 'nombre' }, `${nombre(p.poids)} %`),
        el('td', { class: 'nombre' }, euros(p.valeur)),
        el('td', { class: `nombre ${p.performance > 0 ? 'hausse' : p.performance < 0 ? 'baisse' : ''}` }, variation(p.performance, 1)),
      );
    })),
  );
}

/* ---------------- Graphique linéaire (SVG, sans bibliothèque) ---------------- */

const SERIES = [
  { cle: 'portefeuille', nom: 'Portefeuille', couleur: 'var(--serie-portefeuille)' },
  { cle: 'msci_world', nom: 'MSCI World', couleur: 'var(--serie-indice)' },
];

function graphiquePerformance(historique) {
  // Largeur du dessin = largeur réelle à l'écran, pour garder des textes lisibles sur téléphone
  const L = Math.round(Math.min(780, Math.max(300, innerWidth - 58))), H = 240;
  const m = { haut: 12, droite: 78, bas: 26, gauche: 46 };
  const n = historique.length;
  const valeurs = historique.flatMap((h) => SERIES.map((s) => h[s.cle]));
  const pas = 5000;
  const yMin = Math.floor(Math.min(...valeurs) / pas) * pas;
  const yMax = Math.ceil(Math.max(...valeurs) / pas) * pas;
  const x = (i) => m.gauche + (i / (n - 1)) * (L - m.gauche - m.droite);
  const y = (v) => H - m.bas - ((v - yMin) / (yMax - yMin)) * (H - m.haut - m.bas);

  // Grille horizontale et graduations
  const grille = svg('g', { class: 'grille' });
  const axe = svg('g', { class: 'axe' });
  for (let v = yMin; v <= yMax; v += pas) {
    grille.append(svg('line', { x1: m.gauche, x2: L - m.droite, y1: y(v), y2: y(v) }));
    axe.append(svg('text', { x: m.gauche - 8, y: y(v) + 3, 'text-anchor': 'end' }, `${nombre(v / 1000)} k€`));
  }
  // Un repère par trimestre (premier point de janvier, avril, juillet, octobre)
  let moisPrecedent = -1;
  historique.forEach((h, i) => {
    const mois = new Date(h.date).getMonth();
    if (mois !== moisPrecedent && mois % 3 === 0) {
      axe.append(svg('text', { x: x(i), y: H - 6, 'text-anchor': 'middle' },
        new Date(`${h.date}T12:00:00`).toLocaleDateString('fr-FR', { month: 'short' })));
    }
    moisPrecedent = mois;
  });

  // Courbes + étiquettes directes en bout de ligne
  const courbes = svg('g', {});
  const etiquettes = SERIES.map((s) => ({ s, yFin: y(historique[n - 1][s.cle]) }));
  // Évite que les deux étiquettes se chevauchent
  if (Math.abs(etiquettes[0].yFin - etiquettes[1].yFin) < 14) {
    const [haut, bas] = etiquettes[0].yFin < etiquettes[1].yFin ? etiquettes : [etiquettes[1], etiquettes[0]];
    haut.yFin -= 7; bas.yFin += 7;
  }
  for (const { s, yFin } of etiquettes) {
    const d = historique.map((h, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(h[s.cle]).toFixed(1)}`).join('');
    courbes.append(svg('path', { class: 'serie', d, stroke: s.couleur }));
    courbes.append(svg('text', { class: 'etiquette-serie', x: L - m.droite + 8, y: yFin + 4 }, s.nom));
  }

  // Curseur (ligne verticale + points) et zone de survol
  const ligneCurseur = svg('line', { y1: m.haut, y2: H - m.bas });
  const points = SERIES.map((s) => svg('circle', { r: 4.5, fill: s.couleur }));
  const curseur = svg('g', { class: 'curseur', visibility: 'hidden' }, ligneCurseur, ...points);
  const zone = svg('rect', { x: m.gauche, y: 0, width: L - m.gauche - m.droite, height: H, fill: 'transparent' });

  const dessin = svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img', 'aria-label': 'Évolution du portefeuille comparée au MSCI World' },
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
    SERIES.forEach((s, k) => { points[k].setAttribute('cx', x(i)); points[k].setAttribute('cy', y(h[s.cle])); });
    curseur.setAttribute('visibility', 'visible');
    bulle.replaceChildren(
      el('div', { class: 'infobulle-date' }, `Semaine du ${dateCourte(h.date)}`),
      ...SERIES.map((s) => el('div', { class: 'infobulle-ligne' },
        el('span', {}, el('span', { class: 'trait', style: { background: s.couleur } }), s.nom),
        el('span', { class: 'mono' }, euros(h[s.cle])),
      )),
    );
    bulle.hidden = false;
    const px = (x(i) / L) * boite.width;
    const largeurBulle = bulle.offsetWidth;
    bulle.style.left = `${Math.min(Math.max(0, px + 12), boite.width - largeurBulle) }px`;
    if (px + 12 + largeurBulle > boite.width) bulle.style.left = `${Math.max(0, px - largeurBulle - 12)}px`;
  };
  const cacher = () => { curseur.setAttribute('visibility', 'hidden'); bulle.hidden = true; };
  zone.addEventListener('pointermove', montrer);
  zone.addEventListener('pointerdown', montrer);
  zone.addEventListener('pointerleave', cacher);

  return el('div', {},
    el('div', { class: 'legende-graphique' },
      SERIES.map((s) => el('span', {}, el('span', { class: 'trait', style: { background: s.couleur } }), s.nom))),
    el('div', { class: 'graphique' }, dessin, bulle),
  );
}
