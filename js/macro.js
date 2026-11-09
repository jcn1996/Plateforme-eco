/* ==========================================================================
   Écran « Vue macro » (données réelles de l'agent macro, data/macro.json)
   - phase du cycle : schéma en 4 quadrants, un point par zone et une flèche
     depuis sa position du mois précédent ;
   - signaux de récession (pastilles vert, orange, rouge) ;
   - banques centrales (taux, dernier mouvement, prochaine réunion, compte à rebours) ;
   - taux réels États-Unis (passé : Fed − inflation ; attendu : obligations indexées,
     point mort d'inflation) ;
   - courbe des taux US sur 2 ans ;
   - marchés du cycle (cuivre, pétrole, dollar, or).
   Sources et dates sous chaque bloc.
   ========================================================================== */

import { el, svg, nombre, variation } from './outils.js';

const FICHIER = 'data/macro.json';

/** Charge data/macro.json ; renvoie null si le fichier manque (l'appli continue). */
export async function chargerMacro() {
  try {
    const r = await fetch(FICHIER, { cache: 'no-cache' });
    if (!r.ok) return null;
    const json = await r.json();
    return json?.donnees ? { meta: json.meta ?? {}, ...json.donnees } : null;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ outils */

const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

/** « 02/11/2026 », ou « sept. 2026 » pour une période mensuelle. */
function dateFr(d) {
  if (!d) return 'date inconnue';
  const s = String(d);
  if (s.length === 7) return `${MOIS[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)}`;
  return `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
}

const pts = (v, dec = 2) => variation(v, dec, ' pt');

function source(texte) {
  return el('p', { class: 'macro-source' }, texte);
}

function titre(texte, complement) {
  return el('h3', { class: 'section-titre' }, texte, complement ? el('small', {}, complement) : null);
}

const LIBELLE_NIVEAU = { vert: 'vert', orange: 'orange', rouge: 'rouge' };

/* ------------------------------------------------------------------ quadrants */

const PHASES = [
  // [phase, croissance, inflation, position du libellé]
  ['Surchauffe', 1, 1],
  ['Reprise', 1, -1],
  ['Ralentissement inflationniste', -1, 1],
  ['Expansion sans inflation', -1, -1],
];

function schemaQuadrants(zones) {
  const L = Math.round(Math.min(520, Math.max(300, innerWidth - 40)));
  const H = Math.round(L * 0.86);
  const m = { haut: 22, droite: 14, bas: 26, gauche: 26 };
  const toutes = zones.flatMap((z) => [z.position, z.position_precedente]).filter(Boolean);
  const ex = Math.max(0.3, ...toutes.map((p) => Math.abs(p.x))) * 1.25;
  const ey = Math.max(0.5, ...toutes.map((p) => Math.abs(p.y))) * 1.25;
  const x = (v) => m.gauche + ((v + ex) / (2 * ex)) * (L - m.gauche - m.droite);
  const y = (v) => H - m.bas - ((v + ey) / (2 * ey)) * (H - m.haut - m.bas);
  const cx = x(0), cy = y(0);

  const fond = svg('g', { class: 'quadrants' },
    svg('rect', { class: 'quadrant quadrant--surchauffe', x: cx, y: m.haut, width: L - m.droite - cx, height: cy - m.haut }),
    svg('rect', { class: 'quadrant quadrant--reprise', x: cx, y: cy, width: L - m.droite - cx, height: H - m.bas - cy }),
    svg('rect', { class: 'quadrant quadrant--ralentissement', x: m.gauche, y: m.haut, width: cx - m.gauche, height: cy - m.haut }),
    svg('rect', { class: 'quadrant quadrant--expansion', x: m.gauche, y: cy, width: cx - m.gauche, height: H - m.bas - cy }),
    svg('line', { class: 'axe-zero', x1: m.gauche, x2: L - m.droite, y1: cy, y2: cy }),
    svg('line', { class: 'axe-zero', x1: cx, x2: cx, y1: m.haut, y2: H - m.bas }),
  );
  // Noms des phases dans les coins
  const coins = svg('g', { class: 'quadrant-nom' },
    svg('text', { x: L - m.droite - 6, y: m.haut + 14, 'text-anchor': 'end' }, 'Surchauffe'),
    svg('text', { x: L - m.droite - 6, y: H - m.bas - 8, 'text-anchor': 'end' }, 'Reprise'),
    svg('text', { x: m.gauche + 6, y: m.haut + 14 }, 'Ralentissement inflationniste'),
    svg('text', { x: m.gauche + 6, y: H - m.bas - 8 }, 'Expansion sans inflation'),
  );
  // Axes : sens de lecture
  const axes = svg('g', { class: 'quadrant-axe' },
    svg('text', { x: L - m.droite, y: H - 6, 'text-anchor': 'end' }, 'croissance accélère →'),
    svg('text', { x: m.gauche, y: H - 6 }, '← ralentit'),
    svg('text', { x: m.gauche - 8, y: m.haut - 8 }, '↑ inflation accélère'),
  );

  const defs = svg('defs', {}, svg('marker', { id: 'fleche-macro', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse' },
    svg('path', { d: 'M0,0 L10,5 L0,10 z', class: 'fleche-pointe' })));

  const bulle = el('div', { class: 'infobulle', hidden: true });
  const points = svg('g', {});
  // Étiquettes : à droite du point, ou à gauche près du bord droit ; décalées si deux se chevauchent
  const places = [];
  for (const z of zones) {
    if (!z.position) continue;
    const px = x(z.position.x), py = y(z.position.y);
    if (z.position_precedente) {
      const ax = x(z.position_precedente.x), ay = y(z.position_precedente.y);
      if (Math.hypot(px - ax, py - ay) > 8) {
        // La flèche s'arrête au bord du point
        const k = 1 - 7 / Math.hypot(px - ax, py - ay);
        points.append(svg('line', { class: 'fleche', x1: ax, y1: ay, x2: ax + (px - ax) * k, y2: ay + (py - ay) * k, 'marker-end': 'url(#fleche-macro)' }));
      }
    }
    const monde = z.cle === 'monde';
    // Point creux : le signal du mois place la zone dans un autre quadrant que sa phase,
    // sans second signal concordant (la phase n'a donc pas changé)
    const attendu = { x: z.croissance?.direction === 'accélère' ? 1 : -1, y: z.inflation?.direction === 'accélère' ? 1 : -1 };
    const nonConfirme = Math.sign(z.position.x) * attendu.x < 0 || Math.sign(z.position.y) * attendu.y < 0;
    const point = svg('circle', { class: `point-zone${monde ? ' point-zone--monde' : ''}${nonConfirme ? ' point-zone--non-confirme' : ''}`, cx: px, cy: py, r: monde ? 6 : 4.5 });
    const aGauche = px > L - 90;
    let ly = py + 4;
    while (places.some((p) => Math.abs(p.y - ly) < 12 && Math.abs(p.x - px) < 80)) ly += 12;
    places.push({ x: px, y: ly });
    const etiquette = svg('text', { class: `etiquette-zone${monde ? ' etiquette-zone--monde' : ''}`, x: aGauche ? px - 9 : px + 9, y: ly, 'text-anchor': aGauche ? 'end' : 'start' }, z.nom);
    // Zone de toucher plus large que le point
    const cible = svg('circle', { cx: px, cy: py, r: 16, fill: 'transparent', class: 'cible' });
    const montrer = () => {
      bulle.replaceChildren(
        el('div', { class: 'infobulle-date' }, `${z.nom} · ${dateFr(z.date_donnees)}`),
        el('div', {}, el('strong', {}, z.phase)),
        el('div', { class: 'infobulle-ligne' }, el('span', {}, 'Indicateur avancé, 3 mois'), el('span', { class: 'mono' }, pts(z.position.x))),
        el('div', { class: 'infobulle-ligne' }, el('span', {}, 'Inflation, 3 mois'), el('span', { class: 'mono' }, pts(z.position.y))),
        nonConfirme ? el('div', { class: 'infobulle-note' }, `Signal du mois non confirmé par un second signal : la phase reste « ${z.phase} ».`) : null,
      );
      bulle.hidden = false;
      const boite = dessin.getBoundingClientRect();
      const bx = (px / L) * boite.width, by = (py / H) * boite.height;
      bulle.style.left = `${Math.min(Math.max(0, bx + 12), boite.width - bulle.offsetWidth)}px`;
      bulle.style.top = `${Math.max(0, by - bulle.offsetHeight - 10)}px`;
    };
    cible.addEventListener('pointerenter', montrer);
    cible.addEventListener('pointerdown', montrer);
    cible.addEventListener('pointerleave', () => { bulle.hidden = true; });
    points.append(point, etiquette, cible);
  }

  const dessin = svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img',
    'aria-label': `Phase du cycle : ${zones.map((z) => `${z.nom}, ${z.phase}`).join(' ; ')}` },
  defs, fond, coins, axes, points);
  return el('div', { class: 'graphique graphique--quadrants' }, dessin, bulle);
}

function listeZones(zones) {
  return el('ul', { class: 'macro-zones' }, zones.map((z) => el('li', {},
    el('div', { class: 'macro-zone-ligne' },
      el('span', { class: 'macro-zone-nom' }, z.nom),
      el('span', { class: `macro-phase macro-phase--${classePhase(z.phase)}` }, z.phase),
    ),
    el('div', { class: 'macro-zone-info' },
      z.phase_precedente ? `depuis ${dateFr(z.depuis)} · avant : ${z.phase_precedente}` : 'phase inchangée sur la période étudiée',
      ` · confiance ${z.confiance}`,
      z.ancienne ? ' · valeur ancienne (source indisponible)' : ''),
    z.changement_en_cours ? el('div', { class: 'macro-zone-info macro-confirmation' },
      `Changement de phase en cours de confirmation : « ${z.changement_en_cours.vers} » observée depuis le ${dateFr(z.changement_en_cours.depuis)} `
      + `(${z.changement_en_cours.jours} jour${z.changement_en_cours.jours > 1 ? 's' : ''} sur ${z.changement_en_cours.jours_requis} requis`
      + `${z.changement_en_cours.signaux_concordants === false ? ', deux signaux concordants pas encore réunis' : ''}).`) : null,
  )));
}

function classePhase(phase) {
  return { Reprise: 'reprise', Surchauffe: 'surchauffe', 'Ralentissement inflationniste': 'ralentissement', 'Expansion sans inflation': 'expansion' }[phase] ?? 'autre';
}

/* ------------------------------------------------------------------ récession */

function blocRecession(r) {
  return el('ul', { class: 'macro-signaux' }, r.signaux.map((s) => el('li', {},
    el('span', { class: `pastille pastille--${s.niveau ?? 'orange'}`, 'aria-hidden': 'true' }),
    el('div', {},
      el('div', { class: 'macro-signal-ligne' },
        el('span', { class: 'macro-signal-nom' }, s.libelle),
        el('span', { class: 'mono macro-signal-valeur' }, s.cle === 'sahm' || s.cle.startsWith('courbe') ? pts(s.valeur) : nombre(s.valeur, 1)),
      ),
      el('div', { class: 'macro-signal-texte' },
        el('span', { class: `macro-niveau macro-niveau--${s.niveau}` }, LIBELLE_NIVEAU[s.niveau] ?? '?'), ' · ', s.texte ?? '',
        s.ancienne ? ' · valeur ancienne' : ''),
      el('div', { class: 'macro-source' }, `${s.source} · ${dateFr(s.date)}`,
        s.verification === 'concordant' ? ` · vérifié : ${s.note_verification}` : s.verification === 'divergent' ? ` · divergence : ${s.note_verification}` : ''),
    ),
  )));
}

/* ------------------------------------------------------------------ banques centrales */

function tauxTexte(b) {
  return b.fourchette ? `${nombre(b.fourchette[0], 2)}–${nombre(b.fourchette[1], 2)}\u00a0%` : `${nombre(b.taux, 2)}\u00a0%`;
}

function blocBanques(banques) {
  return el('div', { class: 'macro-banques', role: 'table', 'aria-label': 'Banques centrales' },
    el('div', { class: 'macro-banque macro-banque--entete', role: 'row' },
      el('span', { role: 'columnheader' }, 'Banque'), el('span', { role: 'columnheader' }, 'Taux'),
      el('span', { role: 'columnheader' }, 'Dernier mouvement'), el('span', { role: 'columnheader' }, 'Prochaine réunion')),
    banques.map((b) => {
      const m = b.dernier_mouvement;
      const pr = b.prochaine_reunion ?? {};
      const t = b.tendance_12m ?? {};
      return el('div', { class: 'macro-banque', role: 'row' },
        el('span', { role: 'cell' }, el('strong', {}, b.nom), el('small', {}, b.pays)),
        el('span', { role: 'cell', class: 'mono' }, tauxTexte(b),
          el('small', {}, t.variation_pts == null ? '' : t.sens === 'stable' ? 'stable sur 12 mois' : `${pts(t.variation_pts)} sur 12 mois`)),
        el('span', { role: 'cell' }, m
          ? [el('span', { class: m.sens === 'hausse' ? 'hausse' : 'baisse' }, `${m.sens === 'hausse' ? '▲' : '▼'} ${variation(m.ampleur_pts, 2, ' pt')}`),
            el('small', {}, dateFr(m.date))]
          : el('small', {}, 'aucun dans la période')),
        el('span', { role: 'cell' }, pr.date
          ? [el('span', { class: 'mono' }, dateFr(pr.date)), el('small', { class: pr.jours <= 7 ? 'macro-bientot' : '' }, pr.jours === 0 ? "aujourd'hui" : `dans ${pr.jours} j`)]
          : el('small', {}, b.cle === 'pboc' ? 'pas de calendrier publié' : 'calendrier à compléter')),
      );
    }),
  );
}

/* ------------------------------------------------------------------ taux réels États-Unis */

/** Tendance sur 12 mois, en points (couleur neutre : une hausse n'est ni bonne ni mauvaise en soi). */
function tendance12m(x) {
  if (x?.variation_12m == null) return el('span', {}, 'n. d.');
  const fleche = x.sens === 'hausse' ? '▲' : x.sens === 'baisse' ? '▼' : '▬';
  return el('span', { class: 'mono' }, `${fleche} ${pts(x.variation_12m)}`);
}

function carteTauxReel(libelle, aide, x, complement) {
  return el('div', { class: 'carte macro-marche macro-taux-reel' },
    el('div', { class: 'macro-marche-nom' }, libelle),
    el('div', { class: 'macro-marche-valeur mono' }, x ? `${nombre(x.valeur, 2)}\u00a0${aide.unite}` : 'n. d.'),
    el('small', { class: 'macro-taux-reel-aide' }, aide.texte),
    el('div', { class: 'macro-marche-var' }, el('span', {}, '12 mois'), tendance12m(x)),
    complement ?? null,
    el('div', { class: 'macro-source' }, x ? `${dateFr(x.date_inflation ? x.date_taux : x.date)}${x.ancienne ? ' · valeur ancienne' : ''}` : 'indisponible'),
  );
}

function blocTauxReels(tr) {
  const us = tr?.etats_unis ?? {};
  const cinq = (x, libelle) => (x ? el('div', { class: 'macro-marche-var' }, el('span', {}, libelle), el('span', { class: 'mono' }, `${nombre(x.valeur, 2)} %`)) : null);
  const p = us.passe;
  const verif = us.attendu_10a?.verification;
  const ze = tr?.zone_euro ?? {};
  return [
    el('div', { class: 'macro-marches macro-taux-reels' },
      carteTauxReel('Taux réel passé', { unite: '%', texte: p ? `Fed ${nombre(p.taux_directeur, 2)} % − inflation ${nombre(p.inflation, 1)} % (${dateFr(p.date_inflation)})` : 'Fed − inflation sur 12 mois' }, p),
      carteTauxReel('Taux réel attendu à 10 ans', { unite: '%', texte: 'obligations du Trésor indexées sur l’inflation' }, us.attendu_10a,
        cinq(us.attendu_5a, 'à 5 ans')),
      carteTauxReel('Point mort d’inflation à 10 ans', { unite: '%', texte: 'inflation moyenne anticipée par le marché' }, us.point_mort_10a,
        cinq(us.point_mort_5a, 'à 5 ans')),
    ),
    us.texte ? el('p', { class: 'macro-texte' }, us.texte) : null,
    el('p', { class: 'macro-texte' }, el('strong', {}, 'Zone euro · point mort à 5 ans dans 5 ans : '),
      ze.disponible && ze.point_mort_5a5a != null ? `${nombre(ze.point_mort_5a5a.valeur, 2)} %` : 'non disponible',
      ze.disponible ? '' : el('small', { class: 'macro-taux-reel-aide macro-taux-reel-note' }, ze.note ?? '')),
    source([
      p?.source, us.attendu_10a?.source, us.attendu_5a?.source, us.point_mort_10a?.source, us.point_mort_5a?.source,
    ].filter(Boolean).join(' ; ') + (verif === 'concordant' ? `. Vérifié : ${us.attendu_10a.note_verification}.` : verif === 'divergent' ? `. Divergence : ${us.attendu_10a.note_verification}.` : '.')),
  ];
}

/* ------------------------------------------------------------------ courbe des taux US */

const SERIES_COURBE = [
  { cle: 'T10Y2Y', nom: '10 ans − 2 ans', couleur: 'var(--serie-portefeuille)' },
  { cle: 'T10Y3M', nom: '10 ans − 3 mois', couleur: 'var(--serie-indice)' },
];

function graphiqueCourbe(courbe) {
  const series = SERIES_COURBE.filter((s) => courbe.series?.[s.cle]?.length);
  if (!series.length) return el('p', { class: 'macro-source' }, 'Courbe indisponible.');
  const L = Math.round(Math.min(780, Math.max(300, innerWidth - 58))), H = 200;
  const m = { haut: 10, droite: 88, bas: 24, gauche: 40 };
  const dates = [...new Set(series.flatMap((s) => courbe.series[s.cle].map((p) => p[0])))].sort();
  const t0 = Date.parse(dates[0]), t1 = Date.parse(dates.at(-1));
  const vals = series.flatMap((s) => courbe.series[s.cle].map((p) => p[1]));
  const pas = 0.5;
  const yMin = Math.min(0, Math.floor(Math.min(...vals) / pas) * pas), yMax = Math.max(0.5, Math.ceil(Math.max(...vals) / pas) * pas);
  const x = (d) => m.gauche + ((Date.parse(d) - t0) / (t1 - t0)) * (L - m.gauche - m.droite);
  const y = (v) => H - m.bas - ((v - yMin) / (yMax - yMin)) * (H - m.haut - m.bas);

  const grille = svg('g', { class: 'grille' });
  const axe = svg('g', { class: 'axe' });
  for (let v = yMin; v <= yMax + 1e-9; v += pas) {
    grille.append(svg('line', { x1: m.gauche, x2: L - m.droite, y1: y(v), y2: y(v), class: Math.abs(v) < 1e-9 ? 'ligne-zero' : '' }));
    axe.append(svg('text', { x: m.gauche - 6, y: y(v) + 3, 'text-anchor': 'end' }, nombre(v, 1)));
  }
  // Repères : janvier et juillet
  const vus = new Set();
  for (const d of dates) {
    const cle = d.slice(0, 7);
    if ((d.slice(5, 7) === '01' || d.slice(5, 7) === '07') && !vus.has(cle)) {
      vus.add(cle);
      axe.append(svg('text', { x: x(d), y: H - 6, 'text-anchor': 'middle' }, `${MOIS[Number(d.slice(5, 7)) - 1]} ${d.slice(2, 4)}`));
    }
  }
  const courbes = svg('g', {});
  const fins = series.map((s) => ({ s, yFin: y(courbe.series[s.cle].at(-1)[1]) }));
  if (fins.length === 2 && Math.abs(fins[0].yFin - fins[1].yFin) < 14) {
    const [haut, bas] = fins[0].yFin < fins[1].yFin ? fins : [fins[1], fins[0]];
    haut.yFin -= 7; bas.yFin += 7;
  }
  for (const { s, yFin } of fins) {
    const d = courbe.series[s.cle].map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
    courbes.append(svg('path', { class: 'serie', d, stroke: s.couleur }));
    courbes.append(svg('text', { class: 'etiquette-serie', x: L - m.droite + 8, y: yFin + 4 }, s.nom));
  }
  // Curseur
  const ligne = svg('line', { y1: m.haut, y2: H - m.bas });
  const ronds = series.map((s) => svg('circle', { r: 4.5, fill: s.couleur }));
  const curseur = svg('g', { class: 'curseur', visibility: 'hidden' }, ligne, ...ronds);
  const zone = svg('rect', { x: m.gauche, y: 0, width: L - m.gauche - m.droite, height: H, fill: 'transparent' });
  const dessin = svg('svg', { viewBox: `0 0 ${L} ${H}`, role: 'img', 'aria-label': 'Écarts de taux américains sur 2 ans' }, grille, axe, courbes, curseur, zone);
  const bulle = el('div', { class: 'infobulle', hidden: true });
  const montrer = (ev) => {
    const boite = dessin.getBoundingClientRect();
    const xs = ((ev.clientX - boite.left) / boite.width) * L;
    const t = t0 + ((xs - m.gauche) / (L - m.gauche - m.droite)) * (t1 - t0);
    const d = dates.reduce((a, b) => (Math.abs(Date.parse(b) - t) < Math.abs(Date.parse(a) - t) ? b : a));
    ligne.setAttribute('x1', x(d)); ligne.setAttribute('x2', x(d));
    const lignes = [];
    series.forEach((s, k) => {
      const p = courbe.series[s.cle].find((q) => q[0] === d);
      ronds[k].setAttribute('visibility', p ? 'visible' : 'hidden');
      if (p) { ronds[k].setAttribute('cx', x(d)); ronds[k].setAttribute('cy', y(p[1])); }
      lignes.push(el('div', { class: 'infobulle-ligne' },
        el('span', {}, el('span', { class: 'trait', style: { background: s.couleur } }), s.nom),
        el('span', { class: 'mono' }, p ? pts(p[1]) : 'n. d.')));
    });
    curseur.setAttribute('visibility', 'visible');
    bulle.replaceChildren(el('div', { class: 'infobulle-date' }, `Semaine du ${dateFr(d)}`), ...lignes);
    bulle.hidden = false;
    const px = (x(d) / L) * boite.width;
    bulle.style.left = `${px + 12 + bulle.offsetWidth > boite.width ? Math.max(0, px - bulle.offsetWidth - 12) : px + 12}px`;
  };
  zone.addEventListener('pointermove', montrer);
  zone.addEventListener('pointerdown', montrer);
  zone.addEventListener('pointerleave', () => { curseur.setAttribute('visibility', 'hidden'); bulle.hidden = true; });
  return el('div', {},
    el('div', { class: 'legende-graphique' }, series.map((s) => el('span', {}, el('span', { class: 'trait', style: { background: s.couleur } }), s.nom))),
    el('div', { class: 'graphique' }, dessin, bulle),
  );
}

/* ------------------------------------------------------------------ marchés du cycle */

function blocMarches(marches) {
  const dec = (m) => (m.valeur >= 1000 ? 0 : 2);
  const v = (x) => (x == null ? el('span', {}, 'n. d.') : el('span', { class: `mono ${x >= 0 ? 'hausse' : 'baisse'}` }, variation(x, 1)));
  return el('div', { class: 'macro-marches' }, marches.map((m) => el('div', { class: 'carte macro-marche' },
    el('div', { class: 'macro-marche-nom' }, m.nom),
    el('div', { class: 'macro-marche-valeur mono' }, `${nombre(m.valeur, dec(m))}${m.unite === 'pts' ? '' : ` ${m.unite}`}`),
    el('div', { class: 'macro-marche-var' }, el('span', {}, '3 mois'), v(m.variation_3m)),
    el('div', { class: 'macro-marche-var' }, el('span', {}, '12 mois'), v(m.variation_12m)),
    el('div', { class: 'macro-source' }, `${dateFr(m.date)}${m.ancienne ? ' · valeur ancienne' : ''}`),
  )));
}

/* ------------------------------------------------------------------ écran */

export function ecranMacro(macro, nav = {}) {
  const entete = el('header', {},
    el('div', { class: 'fiche-surtitre' }, 'Agent macro · vue d’ensemble de l’économie mondiale'),
    el('h2', { class: 'fiche-titre' }, 'Vue macro'),
    // Accès à l'écran « Données alternatives » (pas de bouton supplémentaire dans l'en-tête de l'appli)
    nav.ouvrirAlternatives ? el('div', { class: 'fiche-actions' },
      el('button', { class: 'bouton bouton--accent alt-bouton', type: 'button', onclick: nav.ouvrirAlternatives }, 'Données alternatives : l’activité réelle ›')) : null,
  );
  if (!macro) {
    return [entete, el('p', { class: 'sante-ligne' }, 'Données de l’agent macro indisponibles (data/macro.json introuvable). Lancer l’agent depuis l’onglet Actions.')];
  }
  const zones = macro.cycle?.zones ?? [];
  const monde = zones.find((z) => z.cle === 'monde');
  return [
    entete,
    el('p', { class: 'macro-resume' }, monde
      ? [`Cycle mondial : `, el('strong', {}, monde.phase), ` · confiance ${macro.confiance}`]
      : 'Cycle mondial indisponible.'),

    el('section', {},
      titre('Phase du cycle', 'point = variations sur 3 mois · flèche = depuis le mois précédent · point creux = signal pas encore confirmé'),
      schemaQuadrants(zones),
      listeZones(zones),
      monde ? el('p', { class: 'macro-texte' }, monde.texte) : null,
      source(`${macro.cycle?.methode ?? ''} Sources : OCDE (indicateur avancé, IPC), Eurostat (IPCH), FMI (WEO). Données jusqu’à ${dateFr(macro.cycle?.date_donnees)}.`),
    ),

    el('section', {},
      titre('Signaux de récession', `confiance ${macro.recession?.confiance ?? '?'}`),
      el('p', { class: 'macro-texte' }, macro.recession?.synthese ?? ''),
      blocRecession(macro.recession ?? { signaux: [] }),
    ),

    el('section', {},
      titre('Banques centrales', 'dernier mouvement · prochaine réunion'),
      blocBanques(macro.banques_centrales ?? []),
      source(`Taux : BRI (WS_CBPOL, quotidien) et sources nationales (FRED pour la Fed, BCE, Banque du Canada, Banco Central do Brasil), la plus récente des deux. Calendriers : sites officiels des banques centrales, relevés le ${dateFr(macro.meta?.calendrier_releve_le)}.`),
    ),

    el('section', {},
      titre('Taux réels États-Unis', 'passé et attendu · tendance sur 12 mois'),
      ...blocTauxReels(macro.taux_reels),
    ),

    el('section', {},
      titre('Courbe des taux américains', 'écart en points, 2 ans'),
      graphiqueCourbe(macro.courbe_us ?? {}),
      source(`${macro.courbe_us?.source ?? 'FRED'}. Sous zéro : courbe inversée.`),
    ),

    el('section', {},
      titre('Marchés du cycle', 'variations sur 3 et 12 mois'),
      blocMarches(macro.marches ?? []),
      source('Yahoo Finance via yfinance, clôtures quotidiennes (cuivre HG=F, pétrole WTI CL=F, indice dollar DX-Y.NYB, or GC=F).'),
    ),

    macro.contre_scenario?.length ? el('section', {},
      titre('Ce qui pourrait me donner tort'),
      el('ul', { class: 'contre-scenario' }, macro.contre_scenario.map((t) => el('li', {}, t))),
    ) : null,

    el('p', { class: 'fraicheur' }, `Mis à jour le ${dateFr(macro.meta?.genere_le)} · Agent macro (règles, sans IA)`),
    el('p', { class: 'mention-legale' }, 'Données réelles issues de sources publiques, analysées automatiquement. Ne constitue pas un conseil en investissement.'),
  ];
}

/** Section « Agent macro » de la fiche pays : texte de l'agent et sa date. */
export function sectionMacroPays(macro, code) {
  const l = macro?.lectures_pays?.[code];
  if (!l) return null;
  return el('section', {},
    el('h3', { class: 'section-titre' }, 'Agent macro', el('small', {}, `mis à jour le ${dateFr(l.date)}`)),
    el('p', { class: 'macro-texte' }, l.texte),
    source(`Sources : ${l.sources.join(' ; ')}.`),
  );
}
