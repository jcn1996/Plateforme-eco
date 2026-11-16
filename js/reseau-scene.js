/* ==========================================================================
   Scène du réseau des agents (accueil)
   --------------------------------------------------------------------------
   - Version 3D (Three.js, déjà chargé pour le globe) : sphère centrale lumineuse
     (chef d'orchestre) et une sphère par agent, disposées en profondeur ; liens
     lumineux (épais = pèse dans la décision, pointillés = contexte ; rouge sans
     impulsion = en panne ; un agent dégradé garde son lien normal, seule une
     pastille orange discrète le signale sous son nom) ; impulsions
     qui voyagent vers le centre (depuis le centre pour le trader démo).
   - Version 2D à plat (SVG, sans impulsion) : mode léger, « réduire les animations »,
     ou WebGL indisponible.
   - Libellés en HTML, toujours face à l'écran, jamais superposés (séparation à
     chaque image où la scène bouge) ; chaque bulle est un vrai bouton (clavier,
     lecteur d'écran), zone tactile de 44 px au moins.
   - Gestes : rotation au doigt avec inertie, amplitude limitée et retour doux à la
     position de face ; pincer (ou molette) pour zoomer ; toucher une bulle = la caméra
     s'en approche (l'appli ouvre la synthèse de l'agent).
   - Scène en pause quand l'onglet est caché ou l'écran masqué ; 30 images/s au repos,
     pleine cadence pendant un geste.
   ========================================================================== */

import { disposition, separerEtiquettes, texteAccessible, ETATS_RESEAU } from './reseau.js';

const COULEURS = { ok: 0x00e5ff, degrade: 0xffb547, panne: 0xff4d6a, centre: 0xbff6ff };
/** Couleur du lien, de la sphère et des impulsions : un agent dégradé (source secondaire) garde la couleur normale. */
const couleur = (etat) => (etat === 'panne' ? COULEURS.panne : COULEURS.ok);
const css = (n) => `#${n.toString(16).padStart(6, '0')}`;
const LIMITE_LACET = 0.55;   // rotation horizontale maximale (radians)
const LIMITE_TANGAGE = 0.32; // rotation verticale maximale
const RAPPEL = 0.0035;       // force de retour à la position de face
const AMORTI = 0.9;          // inertie (par image à 60 images/s)
const ZOOM_MIN = 0.75, ZOOM_MAX = 2.2;
const DISTANCE = 10, CHAMP = 40; // caméra : distance au centre, champ vertical (degrés)
const RAYON_AGENT = 0.3, RAYON_CENTRE = 0.56; // rayons des sphères (unités de la scène)
const TACTILE = 44; // zone tactile minimale (px)
const MARGE_X = 50, MARGE_HAUT = 30, MARGE_BAS = 62; // place réservée aux libellés autour de l'ellipse (px)

/** Texture ronde et floue pour les halos et les impulsions. */
function textureHalo(THREE) {
  const t = 64;
  const toile = document.createElement('canvas');
  toile.width = toile.height = t;
  const ctx = toile.getContext('2d');
  const g = ctx.createRadialGradient(t / 2, t / 2, 0, t / 2, t / 2, t / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.3, 'rgba(255,255,255,0.55)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, t, t);
  const texture = new THREE.CanvasTexture(toile);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** Charge Three.js et les lignes épaisses (null si indisponible : la version 2D prend le relais). */
async function chargerThree() {
  try {
    const THREE = await import('three');
    let lignes = null;
    try {
      const [{ LineSegments2 }, { LineSegmentsGeometry }, { LineMaterial }] = await Promise.all([
        import('three/addons/lines/LineSegments2.js'), import('three/addons/lines/LineSegmentsGeometry.js'), import('three/addons/lines/LineMaterial.js'),
      ]);
      lignes = { LineSegments2, LineSegmentsGeometry, LineMaterial };
    } catch { /* lignes de 1 px en secours */ }
    const essai = document.createElement('canvas');
    if (!(essai.getContext('webgl2') || essai.getContext('webgl'))) return null;
    return { THREE, lignes };
  } catch {
    return null;
  }
}

export class SceneReseau {
  /**
   * @param {HTMLElement} conteneur  zone de la scène (taille fixée par la feuille de style)
   * @param {object} options  { reseau: { centre, agents }, mode: '3d' | '2d', surChoix(cle), surCentre(),
   *   focus: hauteur visée pour la bulle choisie (fraction de la scène depuis le haut, ou fonction qui la renvoie) }
   */
  constructor(conteneur, { reseau, mode = '3d', surChoix = () => {}, surCentre = () => {}, focus = 0.3 }) {
    this.conteneur = conteneur;
    this.surChoix = surChoix;
    this.surCentre = surCentre;
    this.fractionFocus = focus;
    this.mode = mode;
    this.actif = false;
    this.reseau = reseau;
    this.lacet = 0; this.tangage = 0; this.vLacet = 0; this.vTangage = 0;
    this.zoom = 1; this.zoomCible = 1;
    this.focusCle = null;
    this.pointeurs = new Map();
    this.boucle = (t) => this.#image(t);
    this.raf = 0;
    this.signature = '';
    this.debut = performance.now();
    this.dernierRendu = 0;
    this.derniereInteraction = 0;

    conteneur.classList.add('reseau-scene');
    this.fond = document.createElement('div');
    this.fond.className = 'reseau-fond';
    this.calque = document.createElement('div');
    this.calque.className = 'reseau-calque';
    this.calque.setAttribute('role', 'group');
    this.calque.setAttribute('aria-label', 'Réseau des agents : chaque bulle ouvre la synthèse de l’agent');
    conteneur.replaceChildren(this.fond, this.calque);
    this.#creerBoutons();
    this.#brancherGestes();
    this.observateur = new ResizeObserver(() => this.redimensionner());
    this.observateur.observe(conteneur);
    this.surVisibilite = () => this.#relancer();
    document.addEventListener('visibilitychange', this.surVisibilite);
  }

  /** Démarre la scène (3D si possible). Renvoie le mode effectif. */
  async demarrer() {
    if (this.mode === '3d') {
      const three = await chargerThree();
      if (three) this.#construire3D(three);
      else this.mode = '2d';
    }
    if (this.mode === '2d') this.#construire2D();
    this.conteneur.dataset.mode = this.mode;
    this.redimensionner();
    return this.mode;
  }

  /* ============================== Boutons et libellés ============================== */

  #noeuds() { return [this.reseau.centre, ...this.reseau.agents]; }

  #creerBoutons() {
    this.boutons = new Map();
    for (const n of this.#noeuds()) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'reseau-noeud';
      b.dataset.cle = n.cle;
      const lib = document.createElement('span');
      lib.className = 'reseau-libelle';
      lib.setAttribute('aria-hidden', 'true');
      b.append(lib);
      b.addEventListener('click', () => (n.centre ? this.surCentre() : this.surChoix(n.cle)));
      this.calque.append(b);
      this.boutons.set(n.cle, { bouton: b, libelle: lib, l: 0, h: 0, x: 0, y: 0, cle: n.cle });
    }
    this.#majBoutons();
  }

  #majBoutons() {
    for (const n of this.#noeuds()) {
      const e = this.boutons.get(n.cle);
      if (!e) continue;
      const etat = ETATS_RESEAU[n.etat]?.court;
      e.libelle.replaceChildren(
        Object.assign(document.createElement('span'), { className: 'reseau-nom', textContent: n.nom }),
        Object.assign(document.createElement('span'), { className: 'reseau-info', textContent: n.info }),
        ...(etat ? [Object.assign(document.createElement('span'), { className: 'reseau-etat', textContent: etat })] : []),
      );
      e.bouton.className = `reseau-noeud reseau-noeud--${n.etat} reseau-noeud--${n.centre ? 'centre' : n.poids}${this.focusCle === n.cle ? ' est-focus' : ''}`;
      e.bouton.setAttribute('aria-label', texteAccessible(n));
      e.l = 0; // à mesurer
    }
    this.signature = '';
  }

  /** Nouvelles données (infos, états) : libellés, couleurs et liens mis à jour. */
  maj(reseau) {
    this.reseau = reseau;
    this.#majBoutons();
    if (this.trois) this.#majStyles3D();
    if (this.svg) this.#construire2D();
    this.#demander();
  }

  /** Mesure les libellés (après un changement de texte). */
  #mesurer() {
    for (const e of this.boutons.values()) {
      if (e.l) continue;
      e.l = Math.ceil(e.libelle.offsetWidth);
      e.h = Math.ceil(e.libelle.offsetHeight);
    }
  }

  /** Place libellés et boutons d'après les positions des bulles à l'écran. */
  #placer(projections, borner) {
    this.#mesurer();
    const etiquettes = [];
    const obstacles = [];
    for (const p of projections) {
      const e = this.boutons.get(p.cle);
      obstacles.push({ cle: p.cle, proprietaire: p.cle, x: p.x - p.r, y: p.y - p.r, l: 2 * p.r, h: 2 * p.r });
      etiquettes.push(Object.assign(e, { x: p.x - e.l / 2, y: p.y + p.r + 3 }));
    }
    separerEtiquettes(etiquettes, obstacles, borner ? { l: this.largeur, h: this.hauteur } : null);
    for (const p of projections) {
      const e = this.boutons.get(p.cle);
      const R = Math.max(TACTILE / 2, p.r);
      const x0 = Math.min(p.x - R, e.x), y0 = Math.min(p.y - R, e.y);
      const x1 = Math.max(p.x + R, e.x + e.l), y1 = Math.max(p.y + R, e.y + e.h);
      const cle = `${x0.toFixed(1)},${y0.toFixed(1)},${(x1 - x0).toFixed(1)},${(y1 - y0).toFixed(1)},${(e.x - x0).toFixed(1)},${(e.y - y0).toFixed(1)},${p.cache ? 1 : 0}`;
      if (e.place === cle) continue;
      e.place = cle;
      const s = e.bouton.style;
      s.transform = `translate(${x0.toFixed(1)}px, ${y0.toFixed(1)}px)`;
      s.width = `${(x1 - x0).toFixed(1)}px`;
      s.height = `${(y1 - y0).toFixed(1)}px`;
      e.libelle.style.transform = `translate(${(e.x - x0).toFixed(1)}px, ${(e.y - y0).toFixed(1)}px)`;
      e.bouton.classList.toggle('est-loin', Boolean(p.cache));
    }
  }

  /* ============================== Géométrie commune ============================== */

  /** Rayons de l'ellipse (px) et centre de la scène, d'après la taille de la zone. */
  #cadre() {
    const rx = Math.max(60, this.largeur / 2 - MARGE_X);
    const ry = Math.max(60, (this.hauteur - MARGE_HAUT - MARGE_BAS) / 2);
    return { rx, ry, cx: this.largeur / 2, cy: MARGE_HAUT + ry };
  }

  redimensionner() {
    const r = this.conteneur.getBoundingClientRect();
    if (!r.width || !r.height) return;
    this.largeur = r.width;
    this.hauteur = r.height;
    if (this.trois) this.#redimensionner3D();
    if (this.svg) this.#construire2D();
    this.signature = '';
    this.#demander();
  }

  /* ============================== Version 2D (SVG, à plat) ============================== */

  #construire2D() {
    if (!this.largeur) { const r = this.conteneur.getBoundingClientRect(); this.largeur = r.width; this.hauteur = r.height; }
    const NS = 'http://www.w3.org/2000/svg';
    const mk = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };
    const { rx, ry, cx, cy } = this.#cadre();
    const pos = disposition(this.reseau.agents.length);
    this.svg ??= mk('svg', { class: 'reseau-svg', 'aria-hidden': 'true' });
    this.svg.setAttribute('viewBox', `0 0 ${this.largeur} ${this.hauteur}`);
    const defs = mk('defs', {});
    const grad = (id, c) => {
      const g = mk('radialGradient', { id, cx: '40%', cy: '35%', r: '65%' });
      g.append(mk('stop', { offset: '0%', 'stop-color': '#ffffff', 'stop-opacity': '0.95' }), mk('stop', { offset: '45%', 'stop-color': c }), mk('stop', { offset: '100%', 'stop-color': c, 'stop-opacity': '0.35' }));
      return g;
    };
    Object.entries(COULEURS).forEach(([k, c]) => defs.append(grad(`reseau-g-${k}`, css(c))));
    const liens = mk('g', { class: 'reseau-liens' });
    const bulles = mk('g', {});
    const projections = [{ cle: this.reseau.centre.cle, x: cx, y: cy, r: 26 }];
    this.reseau.agents.forEach((n, i) => {
      const x = cx + pos[i].x * rx, y = cy - pos[i].y * ry;
      const panne = n.etat === 'panne';
      liens.append(mk('line', {
        x1: x, y1: y, x2: cx, y2: cy, stroke: css(couleur(n.etat)),
        'stroke-width': n.poids === 'decision' ? 3 : 1.6, 'stroke-dasharray': n.poids === 'decision' ? (panne ? '10 4' : 'none') : '4 5',
        'stroke-opacity': panne ? 0.85 : n.poids === 'decision' ? 0.8 : 0.6, 'stroke-linecap': 'round',
      }));
      bulles.append(mk('circle', { cx: x, cy: y, r: 14, fill: `url(#reseau-g-${n.etat === 'panne' ? 'panne' : 'ok'})`, stroke: css(couleur(n.etat)), 'stroke-width': 1.2 }));
      projections.push({ cle: n.cle, x, y, r: 14 });
    });
    bulles.prepend(mk('circle', { cx, cy, r: 26, fill: 'url(#reseau-g-centre)', stroke: '#eaffff', 'stroke-width': 1.5 }));
    this.svg.replaceChildren(defs, liens, bulles);
    if (!this.svg.isConnected) this.fond.replaceChildren(this.svg);
    this.projections2D = projections;
    this.#placer(projections, true);
  }

  /* ============================== Version 3D (Three.js) ============================== */

  #construire3D({ THREE, lignes }) {
    const toile = document.createElement('canvas');
    toile.className = 'reseau-toile';
    toile.setAttribute('aria-hidden', 'true');
    this.fond.replaceChildren(toile);
    const rendu = new THREE.WebGLRenderer({ canvas: toile, antialias: true, alpha: true, powerPreference: 'low-power' });
    rendu.setClearColor(0x000000, 0);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(CHAMP, 1, 0.1, 100);
    camera.position.set(0, 0, DISTANCE);
    scene.add(new THREE.AmbientLight(0x6f8fb0, 0.9));
    const soleil = new THREE.DirectionalLight(0xffffff, 1.1);
    soleil.position.set(-3, 4, 6);
    scene.add(soleil);
    const lumiereCentre = new THREE.PointLight(0x7ff3ff, 18, 12, 1.6);
    const groupe = new THREE.Group();
    scene.add(groupe);
    groupe.add(lumiereCentre);
    const halo = textureHalo(THREE);
    const geo = new THREE.IcosahedronGeometry(1, 3);
    const t = { THREE, lignes, rendu, scene, camera, groupe, halo, geo, toile, noeuds: new Map(), liens: [], impulsions: [], materiauxLignes: [] };
    this.trois = t;

    // Sphère centrale lumineuse
    const centre = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: COULEURS.centre, emissive: 0x38e8ff, emissiveIntensity: 0.9, roughness: 0.35, metalness: 0.1 }));
    centre.scale.setScalar(RAYON_CENTRE);
    const haloCentre = new THREE.Sprite(new THREE.SpriteMaterial({ map: halo, color: 0x5ff0ff, transparent: true, opacity: 0.75, blending: THREE.AdditiveBlending, depthWrite: false }));
    haloCentre.scale.setScalar(RAYON_CENTRE * 5);
    groupe.add(centre, haloCentre);
    t.noeuds.set(this.reseau.centre.cle, { mesh: centre, halo: haloCentre, rayon: RAYON_CENTRE, pos: new THREE.Vector3() });
    t.haloCentre = haloCentre;

    // Agents, liens et impulsions
    this.reseau.agents.forEach((n) => {
      const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: COULEURS.ok, emissive: COULEURS.ok, emissiveIntensity: 0.35, roughness: 0.4, metalness: 0.15 }));
      mesh.scale.setScalar(RAYON_AGENT);
      const h = new THREE.Sprite(new THREE.SpriteMaterial({ map: halo, color: COULEURS.ok, transparent: true, opacity: 0.45, blending: THREE.AdditiveBlending, depthWrite: false }));
      h.scale.setScalar(RAYON_AGENT * 4.2);
      groupe.add(mesh, h);
      t.noeuds.set(n.cle, { mesh, halo: h, rayon: RAYON_AGENT, pos: new THREE.Vector3() });
      const pulses = [0, 0.5].map((phase) => {
        const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: halo, color: COULEURS.ok, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false }));
        s.scale.setScalar(0.2);
        groupe.add(s);
        return { sprite: s, phase, cle: n.cle };
      });
      t.impulsions.push(...pulses);
    });
    this.#majStyles3D();
  }

  /** Positions des sphères d'après la taille de la zone (l'ellipse remplit la scène). */
  #positions3D() {
    const t = this.trois;
    const { rx, ry, cy } = this.#cadre();
    const pxParUnite = (this.hauteur / 2) / (DISTANCE * Math.tan((CHAMP * Math.PI) / 360));
    const profondeur = 1.5;
    const reduction = DISTANCE / (DISTANCE + 0.55 * profondeur); // les bulles proches paraissent plus écartées
    t.groupe.position.y = (this.hauteur / 2 - cy) / pxParUnite;
    t.pxParUnite = pxParUnite;
    const pos = disposition(this.reseau.agents.length);
    this.reseau.agents.forEach((n, i) => {
      const x = (pos[i].x * rx * reduction) / pxParUnite, y = (pos[i].y * ry * reduction) / pxParUnite, z = pos[i].z * profondeur;
      const o = t.noeuds.get(n.cle);
      o.pos.set(x, y, z);
      o.mesh.position.copy(o.pos);
      o.halo.position.copy(o.pos);
    });
    // Liens : reconstruits (épaisseur en pixels, pointillés pour le contexte)
    for (const l of t.liens) { t.groupe.remove(l.objet); l.objet.geometry.dispose(); l.objet.material.dispose(); }
    t.liens = [];
    t.materiauxLignes = [];
    for (const n of this.reseau.agents) {
      const o = t.noeuds.get(n.cle);
      const p = [o.pos.x, o.pos.y, o.pos.z, 0, 0, 0];
      let objet;
      const dec = n.poids === 'decision';
      if (t.lignes) {
        const { LineSegments2, LineSegmentsGeometry, LineMaterial } = t.lignes;
        const g = new LineSegmentsGeometry();
        g.setPositions(p);
        const m = new LineMaterial({ linewidth: dec ? 3 : 1.6, transparent: true, depthWrite: false, dashed: !dec, dashSize: 0.14, gapSize: 0.12 });
        m.resolution.set(this.largeur, this.hauteur);
        t.materiauxLignes.push(m);
        objet = new LineSegments2(g, m);
        objet.computeLineDistances();
      } else {
        const g = new t.THREE.BufferGeometry().setAttribute('position', new t.THREE.Float32BufferAttribute(p, 3));
        objet = new t.THREE.LineSegments(g, dec ? new t.THREE.LineBasicMaterial({ transparent: true }) : new t.THREE.LineDashedMaterial({ transparent: true, dashSize: 0.14, gapSize: 0.12 }));
        objet.computeLineDistances();
      }
      objet.renderOrder = -1;
      t.groupe.add(objet);
      t.liens.push({ cle: n.cle, objet });
    }
    this.#majStyles3D();
  }

  /** Couleurs selon l'état ; pas d'impulsion pour un agent en panne ; un agent dégradé garde ses couleurs. */
  #majStyles3D() {
    const t = this.trois;
    if (!t) return;
    for (const n of this.reseau.agents) {
      const c = couleur(n.etat);
      const o = t.noeuds.get(n.cle);
      if (!o) continue;
      const panne = n.etat === 'panne';
      o.mesh.material.color.setHex(c);
      o.mesh.material.emissive.setHex(c);
      o.mesh.material.emissiveIntensity = panne ? 0.18 : 0.38;
      o.halo.material.color.setHex(c);
      o.halo.material.opacity = panne ? 0.2 : 0.45;
      const lien = t.liens.find((l) => l.cle === n.cle);
      if (lien) {
        lien.objet.material.color.setHex(c);
        lien.objet.material.opacity = panne ? 0.75 : n.poids === 'decision' ? 0.85 : 0.6;
        // En panne : trait épais interrompu (l'état ne repose pas sur la couleur seule)
        const m = lien.objet.material;
        if (t.lignes) {
          const pointille = n.poids !== 'decision' || panne;
          if (m.dashed !== pointille) { m.dashed = pointille; m.needsUpdate = true; }
          m.dashSize = panne && n.poids === 'decision' ? 0.3 : 0.14;
          m.gapSize = panne && n.poids === 'decision' ? 0.1 : 0.12;
        }
      }
    }
    for (const imp of t.impulsions) {
      const n = this.reseau.agents.find((a) => a.cle === imp.cle);
      imp.actif = Boolean(n) && n.etat !== 'panne';
      imp.sprite.visible = imp.actif;
      imp.sens = n?.sens;
      imp.vitesse = n?.poids === 'decision' ? 0.42 : 0.26;
      imp.sprite.material.color.setHex(couleur(n?.etat));
    }
  }

  #redimensionner3D() {
    const t = this.trois;
    t.rendu.setPixelRatio(Math.min(devicePixelRatio || 1, 2.5));
    t.rendu.setSize(this.largeur, this.hauteur, false);
    t.camera.aspect = this.largeur / this.hauteur;
    t.camera.updateProjectionMatrix();
    this.#positions3D();
  }

  /** Position à l'écran (px) et rayon apparent de chaque sphère. */
  #projeter3D() {
    const t = this.trois;
    const v = (t.v ??= new t.THREE.Vector3());
    const vc = (t.vc ??= new t.THREE.Vector3());
    const f = (this.hauteur / 2) / Math.tan((CHAMP * Math.PI) / 360);
    const res = [];
    for (const [cle, o] of t.noeuds) {
      v.copy(o.pos).applyMatrix4(t.groupe.matrixWorld);
      vc.copy(v).applyMatrix4(t.camera.matrixWorldInverse);
      const profondeur = -vc.z;
      v.project(t.camera);
      res.push({ cle, x: (v.x + 1) / 2 * this.largeur, y: (1 - v.y) / 2 * this.hauteur, r: profondeur > 0.1 ? (o.rayon * f) / profondeur : 0, cache: profondeur <= 0.1 }); // derrière la caméra ; hors champ, la zone rogne (le bouton reste atteignable au clavier)
    }
    return res;
  }

  /* ============================== Focus (caméra vers une bulle) ============================== */

  /** La caméra s'approche d'une bulle (null : retour à la vue d'ensemble). */
  focaliser(cle) {
    this.focusCle = cle && this.boutons.has(cle) ? cle : null;
    for (const [c, e] of this.boutons) e.bouton.classList.toggle('est-focus', c === this.focusCle);
    this.calque.classList.toggle('a-un-focus', Boolean(this.focusCle));
    if (this.svg) return;
    if (this.focusCle) this.zoomCible = 1;
    this.#demander(true);
  }

  #cibleCamera() {
    const t = this.trois;
    const cible = (t.cible ??= { pos: new t.THREE.Vector3(), vise: new t.THREE.Vector3() });
    if (this.focusCle && t.noeuds.has(this.focusCle)) {
      const o = t.noeuds.get(this.focusCle);
      const p = (t.vf ??= new t.THREE.Vector3()).copy(o.pos).applyMatrix4(t.groupe.matrixWorld);
      const d = 6;
      const demi = d * Math.tan((CHAMP * Math.PI) / 360);
      const fraction = typeof this.fractionFocus === 'function' ? this.fractionFocus() : this.fractionFocus;
      const decalage = (0.5 - fraction) * 2 * demi; // la bulle au-dessus du panneau de synthèse
      cible.pos.set(p.x, p.y - decalage, p.z + d);
      cible.vise.set(p.x, p.y - decalage, p.z);
    } else {
      cible.pos.set(0, 0, DISTANCE / this.zoom);
      cible.vise.set(0, 0, 0);
    }
    return cible;
  }

  /* ============================== Gestes ============================== */

  #brancherGestes() {
    const c = this.conteneur;
    let depart = null; // premier pointeur : position de départ
    let dernier = null;
    let pince = null;
    this.aGlisse = false;
    c.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      this.pointeurs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (this.pointeurs.size === 1) {
        depart = { x: e.clientX, y: e.clientY, id: e.pointerId };
        dernier = { x: e.clientX, y: e.clientY, t: performance.now() };
        this.aGlisse = false;
        this.vLacet = 0; this.vTangage = 0;
      } else if (this.pointeurs.size === 2 && this.mode === '3d') {
        const [a, b] = [...this.pointeurs.values()];
        pince = { d: Math.hypot(a.x - b.x, a.y - b.y), zoom: this.zoom };
        this.aGlisse = true;
        try { c.setPointerCapture(e.pointerId); } catch { /* pointeur déjà relâché */ }
      }
      this.#demander(true);
    });
    c.addEventListener('pointermove', (e) => {
      if (!this.pointeurs.has(e.pointerId)) return;
      this.pointeurs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (this.mode !== '3d') return;
      if (pince && this.pointeurs.size >= 2) {
        const [a, b] = [...this.pointeurs.values()];
        this.zoom = this.zoomCible = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, pince.zoom * (Math.hypot(a.x - b.x, a.y - b.y) / Math.max(1, pince.d))));
        this.#demander(true);
        return;
      }
      if (!depart || e.pointerId !== depart.id || this.focusCle) return;
      if (!this.aGlisse && Math.hypot(e.clientX - depart.x, e.clientY - depart.y) > 7) {
        this.aGlisse = true;
        try { c.setPointerCapture(e.pointerId); } catch { /* idem */ }
      }
      if (!this.aGlisse) return;
      const t = performance.now();
      const dx = e.clientX - dernier.x, dy = e.clientY - dernier.y;
      const resiste = (val, lim, d) => (Math.abs(val) > lim && Math.sign(d) === Math.sign(val) ? d * 0.3 : d);
      const dl = resiste(this.lacet, LIMITE_LACET, dx * 0.006);
      const dt = resiste(this.tangage, LIMITE_TANGAGE, dy * 0.005);
      this.lacet = Math.max(-LIMITE_LACET * 1.35, Math.min(LIMITE_LACET * 1.35, this.lacet + dl));
      this.tangage = Math.max(-LIMITE_TANGAGE * 1.35, Math.min(LIMITE_TANGAGE * 1.35, this.tangage + dt));
      const ms = Math.max(8, t - dernier.t);
      this.vLacet = (dl / ms) * 16.7;
      this.vTangage = (dt / ms) * 16.7;
      dernier = { x: e.clientX, y: e.clientY, t };
      this.#demander(true);
    });
    const fin = (e) => {
      if (!this.pointeurs.delete(e.pointerId)) return;
      if (this.pointeurs.size < 2) pince = null;
      if (depart && e.pointerId === depart.id) {
        if (performance.now() - (dernier?.t ?? 0) > 90) { this.vLacet = 0; this.vTangage = 0; } // doigt arrêté avant le lâcher
        depart = null;
      }
      this.#demander(true);
    };
    c.addEventListener('pointerup', fin);
    c.addEventListener('pointercancel', fin);
    // Un glissement ne doit pas ouvrir la bulle sous le doigt
    c.addEventListener('click', (e) => {
      if (this.aGlisse) { e.stopPropagation(); e.preventDefault(); this.aGlisse = false; }
    }, true);
    c.addEventListener('wheel', (e) => {
      if (this.mode !== '3d' || this.focusCle) return;
      e.preventDefault();
      this.zoomCible = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, this.zoomCible * Math.exp(-e.deltaY * 0.0015)));
      this.#demander(true);
    }, { passive: false });
  }

  /* ============================== Boucle ============================== */

  definirActif(actif) {
    this.actif = actif;
    if (actif) { this.signature = ''; this.redimensionner(); }
    this.#relancer();
  }

  #relancer() {
    if (this.actif && !document.hidden && this.trois) { if (!this.raf) this.raf = requestAnimationFrame(this.boucle); }
    else if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
    if (this.actif && !document.hidden && this.svg) this.#placer(this.projections2D ?? [], true);
  }

  /** Demande une image (pleine cadence si `interaction`). */
  #demander(interaction = false) {
    if (interaction) this.derniereInteraction = performance.now();
    this.#relancer();
  }

  #image(maintenant) {
    this.raf = 0;
    if (!this.actif || document.hidden || !this.trois) return;
    this.raf = requestAnimationFrame(this.boucle);
    const enGeste = this.pointeurs.size > 0 || maintenant - this.derniereInteraction < 1500;
    // Au repos : 30 images/s (les impulsions continuent) ; pendant un geste : pleine cadence
    if (!enGeste && maintenant - this.dernierRendu < 32) return;
    const dt = Math.min(3, (maintenant - (this.dernierRendu || maintenant)) / 16.7 || 1);
    this.dernierRendu = maintenant;
    const t = this.trois;

    // Rotation : inertie, amplitude limitée, retour doux à la position de face
    if (!(this.pointeurs.size && this.aGlisse)) {
      const cibleL = 0, cibleT = 0;
      this.vLacet += (cibleL - this.lacet) * RAPPEL * dt * (Math.abs(this.lacet) > LIMITE_LACET ? 6 : 1);
      this.vTangage += (cibleT - this.tangage) * RAPPEL * dt * (Math.abs(this.tangage) > LIMITE_TANGAGE ? 6 : 1);
      const a = AMORTI ** dt;
      this.vLacet *= a; this.vTangage *= a;
      this.lacet += this.vLacet * dt;
      this.tangage += this.vTangage * dt;
    }
    this.zoom += (this.zoomCible - this.zoom) * Math.min(1, 0.15 * dt);
    t.groupe.rotation.set(this.tangage, this.lacet, 0);
    t.groupe.updateMatrixWorld();

    // Caméra : approche douce de sa cible (vue d'ensemble ou bulle choisie)
    const cible = this.#cibleCamera();
    const k = Math.min(1, 0.09 * dt);
    t.camera.position.lerp(cible.pos, k);
    t.vise = (t.vise ??= new t.THREE.Vector3()).lerp(cible.vise, k);
    t.camera.lookAt(t.vise);
    t.camera.updateMatrixWorld();

    // Impulsions le long des liens ; la sphère centrale « respire »
    const s = (maintenant - this.debut) / 1000;
    t.haloCentre.scale.setScalar(RAYON_CENTRE * (4.8 + 0.5 * Math.sin(s * 1.6)));
    for (const imp of t.impulsions) {
      if (!imp.actif) continue;
      const o = t.noeuds.get(imp.cle);
      let u = (s * imp.vitesse + imp.phase) % 1;
      if (imp.sens === 'depuis_centre') u = 1 - u;
      imp.sprite.position.copy(o.pos).multiplyScalar(1 - u);
      imp.sprite.material.opacity = Math.sin(Math.PI * u) * 0.95;
    }
    t.rendu.render(t.scene, t.camera);

    // Libellés : recalculés seulement si la vue a bougé
    const sig = `${this.lacet.toFixed(4)}|${this.tangage.toFixed(4)}|${t.camera.position.x.toFixed(3)},${t.camera.position.y.toFixed(3)},${t.camera.position.z.toFixed(3)}|${this.largeur}x${this.hauteur}`;
    if (sig !== this.signature) {
      this.signature = sig;
      const vueEnsemble = !this.focusCle && this.zoom <= 1.02;
      this.#placer(this.#projeter3D(), vueEnsemble);
    }
  }

  detruire() {
    this.actif = false;
    this.#relancer();
    this.observateur.disconnect();
    document.removeEventListener('visibilitychange', this.surVisibilite);
    if (this.trois) {
      this.trois.rendu.dispose();
      this.trois.scene.traverse((o) => { o.geometry?.dispose?.(); o.material?.dispose?.(); });
      this.trois.halo.dispose();
    }
    this.trois = null;
    this.svg = null;
    this.conteneur.replaceChildren();
  }
}
