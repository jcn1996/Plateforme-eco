/* ==========================================================================
   Scène du réseau des agents (accueil)
   --------------------------------------------------------------------------
   - Version 3D (Three.js, déjà chargé pour le globe), rendu « verre lumineux » :
     · bulles = sphères lisses translucides (shader : intérieur presque transparent,
       contour plus intense sur les bords par effet Fresnel, léger noyau brillant) ;
       on voit les liens et les autres bulles à travers (tout est additif) ;
     · bulle centrale (chef d'orchestre) plus grande : noyau d'énergie qui « respire »
       et deux anneaux fins en rotation lente ;
     · chaque bulle flotte (dérive douce, désynchronisée) et réagit au toucher (onde
       lumineuse, léger grossissement avec rebond amorti) ;
     · liens courbes (shader : dégradé de lumière de l'agent vers le centre, épais =
       pèse dans la décision, pointillés = contexte), impulsions en forme de traînée
       vers le centre (depuis le centre pour le trader démo) ; en panne : lien rouge
       terne, interrompu, sans impulsion ; un agent dégradé garde son lien normal,
       seule une pastille orange discrète le signale sous son nom ;
     · profondeur : fond de particules très discret, bulles du fond plus petites et
       moins lumineuses, flou lumineux (bloom) maison qui garde la transparence du canevas ;
     · qualité adaptative : sous 40 images/s, bloom puis particules réduits automatiquement.
   - Version 2D à plat (SVG, sans impulsion) : mode léger, « réduire les animations »,
     ou WebGL indisponible.
   - Libellés en HTML, au-dessus du canevas (aucun effet ne passe devant), toujours face
     à l'écran, au pixel près (nets), jamais superposés ; chaque bulle est un vrai bouton
     (clavier, lecteur d'écran), zone tactile de 44 px au moins.
   - Gestes : rotation au doigt avec inertie, amplitude limitée et retour doux à la
     position de face ; pincer (ou molette) pour zoomer ; toucher une bulle = la caméra
     s'en approche (ressort critique, environ 400 ms, sans à-coup ; l'appli ouvre la synthèse).
   - Scène en pause quand l'onglet est caché ou l'écran masqué.
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
const RAYON_AGENT = 0.3, RAYON_CENTRE = 0.7; // rayons des sphères (unités de la scène)
const TACTILE = 44; // zone tactile minimale (px)
const MARGE_X = 50, MARGE_HAUT = 30, MARGE_BAS = 62; // place réservée aux libellés autour de l'ellipse (px)
const PULSATION_CAMERA = 11;  // ressort critique de la caméra (rad/s) : ~95 % du trajet en 400 ms, départ et arrivée doux
const RESSORT = { raideur: 170, amorti: 11 }; // rebond amorti d'une bulle touchée
const PARTICULES = 220;
const IMPULSIONS = [0, 0.5]; // phases des deux impulsions de chaque lien
const TRAINEE = 0.2;         // longueur de la traînée (fraction du lien)

/** Texture ronde et floue pour les noyaux et les têtes d'impulsion. */
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

/** Mélange additif qui laisse l'alpha intact (le canevas reste transparent, la lumière s'ajoute). */
function additif(THREE, m) {
  Object.assign(m, {
    transparent: true, depthWrite: false, blending: THREE.CustomBlending, blendEquation: THREE.AddEquation,
    blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneFactor, blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.OneFactor,
  });
  return m;
}

/* ------------------------------------------------------------------ shaders */

const VS_BULLE = /* glsl */`
  varying vec3 vNormale;
  varying vec3 vVue;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormale = normalize(normalMatrix * normal);
    vVue = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }`;

/** Verre lumineux : Fresnel sur les bords, noyau doux au centre, reflet, onde au toucher. */
const FS_BULLE = /* glsl */`
  uniform vec3 uCouleur;
  uniform float uBord;     // intensité du contour
  uniform float uNoyau;    // intensité du noyau
  uniform float uOnde;     // 0 = pas d'onde ; 0..1 = avancée de l'onde
  uniform float uLumiere;  // profondeur, focus, panne
  varying vec3 vNormale;
  varying vec3 vVue;
  void main() {
    vec3 n = normalize(vNormale);
    float nv = clamp(dot(n, normalize(vVue)), 0.0, 1.0);
    float fresnel = pow(1.0 - nv, 2.4);
    vec3 c = uCouleur * (0.03 + fresnel * 1.35 * uBord);
    c += mix(uCouleur, vec3(1.0), 0.55) * pow(nv, 9.0) * uNoyau * 0.4;
    c += vec3(0.85, 0.97, 1.0) * pow(max(dot(n, normalize(vec3(-0.45, 0.55, 0.7))), 0.0), 70.0) * 0.55;
    float d = sqrt(max(0.0, 1.0 - nv * nv));
    float onde = uOnde > 0.0 ? exp(-pow((d - uOnde) * 7.0, 2.0)) * (1.0 - uOnde) : 0.0;
    c += mix(uCouleur, vec3(1.0), 0.5) * onde * 1.8;
    gl_FragColor = vec4(c * uLumiere, 1.0);
    #include <colorspace_fragment>
  }`;

/** Noyau d'énergie du centre : bandes lumineuses qui tournent doucement, plus clair au cœur. */
const FS_ENERGIE = /* glsl */`
  uniform vec3 uCouleur;
  uniform float uTemps;
  uniform float uSouffle;
  varying vec3 vNormale;
  varying vec3 vVue;
  void main() {
    vec3 n = normalize(vNormale);
    float nv = clamp(dot(n, normalize(vVue)), 0.0, 1.0);
    float bandes = 0.5 + 0.5 * sin(n.y * 9.0 + sin(n.x * 4.0 + uTemps * 0.7) * 1.6 - uTemps * 0.9);
    float coeur = pow(nv, 2.2);
    vec3 c = mix(uCouleur, vec3(1.0), 0.45 * coeur) * (0.25 + 0.75 * coeur) * (0.55 + 0.45 * bandes);
    gl_FragColor = vec4(c * uSouffle, 1.0);
    #include <colorspace_fragment>
  }`;

/** Lien courbe (Bézier quadratique calculée sur la carte graphique, largeur en pixels). */
const VS_LIEN = /* glsl */`
  uniform vec3 uA;  // agent
  uniform vec3 uB;  // point de contrôle
  uniform vec3 uC;  // centre
  uniform float uLargeur;
  uniform vec2 uResolution;
  attribute float aU;
  attribute float aCote;
  varying float vU;
  varying float vCote;
  vec3 bezier(float t) { float m = 1.0 - t; return m * m * uA + 2.0 * m * t * uB + t * t * uC; }
  void main() {
    mat4 mvp = projectionMatrix * modelViewMatrix;
    vec4 c = mvp * vec4(bezier(aU), 1.0);
    vec4 c1 = mvp * vec4(bezier(max(aU - 0.01, 0.0)), 1.0);
    vec4 c2 = mvp * vec4(bezier(min(aU + 0.01, 1.0)), 1.0);
    vec2 d = (c2.xy / c2.w - c1.xy / c1.w) * uResolution;
    d = length(d) > 1e-5 ? normalize(d) : vec2(1.0, 0.0);
    c.xy += vec2(-d.y, d.x) * aCote * (uLargeur / uResolution) * c.w;
    gl_Position = c;
    vU = aU;
    vCote = aCote;
  }`;

const FS_LIEN = /* glsl */`
  uniform vec3 uCouleur;
  uniform vec3 uCouleurCentre;
  uniform float uOpacite;
  uniform float uLargeur;
  uniform float uTirets;     // 0 = trait plein ; sinon nombre de tirets
  uniform float uRemplissage;
  uniform float uActif;      // impulsions (0 en panne)
  uniform float uSens;       // 1 = vers le centre, -1 = depuis le centre
  uniform float uTemps;
  uniform float uVitesse;
  varying float vU;
  varying float vCote;
  void main() {
    float bord = 1.0 - smoothstep(max(0.0, 1.0 - 2.4 / uLargeur), 1.0, abs(vCote));
    float s = uSens > 0.0 ? vU : 1.0 - vU; // avancée dans le sens du trajet
    vec3 c = mix(uCouleur, uCouleurCentre, smoothstep(0.0, 1.0, vU) * 0.65 * uActif);
    float lum = mix(0.35, 1.0, vU) * uOpacite;
    if (uTirets > 0.0) {
      float f = fract(vU * uTirets);
      float w = fwidth(vU * uTirets);
      lum *= smoothstep(uRemplissage + w, uRemplissage - w, f) * smoothstep(0.0, w, f);
    }
    float trainee = 0.0;
    for (int i = 0; i < 2; i++) {
      float h = fract(uTemps * uVitesse + float(i) * 0.5);
      float e = h - s;
      float fondu = sin(3.14159 * h);
      if (e >= 0.0 && e < ${TRAINEE.toFixed(2)}) trainee += pow(1.0 - e / ${TRAINEE.toFixed(2)}, 1.8) * fondu;
    }
    vec3 lumiere = c * lum + mix(uCouleur, vec3(1.0), 0.35) * trainee * 1.6 * uActif;
    gl_FragColor = vec4(lumiere * bord, 1.0);
    #include <colorspace_fragment>
  }`;

const VS_PARTICULES = /* glsl */`
  attribute float aTaille;
  attribute float aPhase;
  uniform float uEchelle;
  uniform float uTemps;
  varying float vScintille;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = aTaille * uEchelle / -mv.z;
    vScintille = 0.65 + 0.35 * sin(uTemps * 0.6 + aPhase);
    gl_Position = projectionMatrix * mv;
  }`;

const FS_PARTICULES = /* glsl */`
  uniform float uOpacite;
  varying float vScintille;
  void main() {
    float a = smoothstep(0.5, 0.0, length(gl_PointCoord - 0.5));
    gl_FragColor = vec4(vec3(0.55, 0.82, 1.0) * a * uOpacite * vScintille, 1.0);
    #include <colorspace_fragment>
  }`;

const VS_ECRAN = /* glsl */`
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

/** Bloom : extraction des zones brillantes (avec réduction 4 points). */
const FS_SEUIL = /* glsl */`
  uniform sampler2D tSource;
  uniform vec2 uTexel;
  uniform float uSeuil;
  varying vec2 vUv;
  void main() {
    vec3 c = 0.25 * (texture2D(tSource, vUv + uTexel * vec2(-1.0, -1.0)).rgb + texture2D(tSource, vUv + uTexel * vec2(1.0, -1.0)).rgb
      + texture2D(tSource, vUv + uTexel * vec2(-1.0, 1.0)).rgb + texture2D(tSource, vUv + uTexel * vec2(1.0, 1.0)).rgb);
    float l = max(c.r, max(c.g, c.b));
    gl_FragColor = vec4(c * smoothstep(uSeuil, uSeuil + 0.35, l), 1.0);
  }`;

/** Bloom : flou gaussien séparable (9 points). */
const FS_FLOU = /* glsl */`
  uniform sampler2D tSource;
  uniform vec2 uPas;
  varying vec2 vUv;
  void main() {
    vec3 c = texture2D(tSource, vUv).rgb * 0.2270270270;
    c += (texture2D(tSource, vUv + uPas * 1.3846153846).rgb + texture2D(tSource, vUv - uPas * 1.3846153846).rgb) * 0.3162162162;
    c += (texture2D(tSource, vUv + uPas * 3.2307692308).rgb + texture2D(tSource, vUv - uPas * 3.2307692308).rgb) * 0.0702702703;
    gl_FragColor = vec4(c, 1.0);
  }`;

/** Composition finale : scène + bloom ; alpha = lumière (le fond de la page reste visible ailleurs). */
const FS_COMPOSITION = /* glsl */`
  uniform sampler2D tScene;
  uniform sampler2D tBloom;
  uniform float uBloom;
  varying vec2 vUv;
  void main() {
    vec3 c = texture2D(tScene, vUv).rgb + texture2D(tBloom, vUv).rgb * uBloom;
    gl_FragColor = vec4(c, 1.0);
    #include <colorspace_fragment>
    gl_FragColor.a = clamp(max(gl_FragColor.r, max(gl_FragColor.g, gl_FragColor.b)), 0.0, 1.0);
  }`;

/** Charge Three.js (null si indisponible : la version 2D prend le relais). */
async function chargerThree() {
  try {
    const THREE = await import('three');
    const essai = document.createElement('canvas');
    if (!(essai.getContext('webgl2') || essai.getContext('webgl'))) return null;
    return { THREE };
  } catch {
    return null;
  }
}

/** Point d'une Bézier quadratique (a, b, c : Vector3) dans `sortie`. */
function bezier(a, b, c, t, sortie) {
  const m = 1 - t;
  return sortie.set(
    m * m * a.x + 2 * m * t * b.x + t * t * c.x,
    m * m * a.y + 2 * m * t * b.y + t * t * c.y,
    m * m * a.z + 2 * m * t * b.z + t * t * c.z,
  );
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
      b.addEventListener('pointerdown', () => this.#appuyer(n.cle, true));
      for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) b.addEventListener(ev, () => this.#appuyer(n.cle, false));
      b.addEventListener('click', () => {
        this.#reagir(n.cle);
        if (n.centre) this.surCentre(); else this.surChoix(n.cle);
      });
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
      e.x = Math.round(e.x); e.y = Math.round(e.y); // au pixel près : texte net
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

  #construire3D({ THREE }) {
    const toile = document.createElement('canvas');
    toile.className = 'reseau-toile';
    toile.setAttribute('aria-hidden', 'true');
    this.fond.replaceChildren(toile);
    const rendu = new THREE.WebGLRenderer({ canvas: toile, antialias: false, alpha: true, premultipliedAlpha: true, powerPreference: 'default' });
    rendu.setClearColor(0x000000, 0);
    rendu.autoClear = true;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(CHAMP, 1, 0.1, 100);
    camera.position.set(0, 0, DISTANCE);
    const groupe = new THREE.Group();
    scene.add(groupe);
    const halo = textureHalo(THREE);
    const geoBulle = new THREE.SphereGeometry(1, 48, 32);
    const temps = { value: 0 };
    const resolution = { value: new THREE.Vector2(1, 1) };
    const t = {
      THREE, rendu, scene, camera, groupe, halo, geoBulle, toile, temps, resolution, noeuds: new Map(), liens: [],
      camPos: camera.position.clone(), camVit: new THREE.Vector3(), vise: new THREE.Vector3(), viseVit: new THREE.Vector3(),
      tmp: new THREE.Vector3(),
    };
    this.trois = t;
    this.qualite = 2;
    this.conteneur.dataset.qualite = '2';
    this.mesure = { debut: 0, images: 0, pire: 0 };

    const materiauBulle = (c, bord, noyau) => additif(THREE, new THREE.ShaderMaterial({
      vertexShader: VS_BULLE, fragmentShader: FS_BULLE,
      uniforms: { uCouleur: { value: new THREE.Color(c) }, uBord: { value: bord }, uNoyau: { value: noyau }, uOnde: { value: 0 }, uLumiere: { value: 1 } },
    }));
    const sprite = (c, opacite) => new THREE.Sprite(additif(THREE, new THREE.SpriteMaterial({ map: halo, color: c, opacity: opacite })));
    const noeud = (cle, rayon, c, bord, noyau, i) => {
      const racine = new THREE.Group();
      const verre = new THREE.Mesh(geoBulle, materiauBulle(c, bord, noyau));
      const coeur = sprite(c, 0.3);
      coeur.scale.setScalar(0.62);
      racine.add(verre, coeur);
      groupe.add(racine);
      const o = {
        cle, racine, verre, coeur, rayonBase: rayon, rayon, pos: new THREE.Vector3(), base: new THREE.Vector3(),
        phases: [i * 1.7, i * 2.3 + 1, i * 0.9 + 2], frequences: [0.31 + (i % 4) * 0.045, 0.26 + (i % 3) * 0.05, 0.22 + (i % 5) * 0.03],
        amplitude: 0.07, coeurBase: 0.3, echelle: 1, vEchelle: 0, cibleEchelle: 1, onde: -1, lumiere: 1, lumiereCible: 1, profondeur: 1,
      };
      t.noeuds.set(cle, o);
      return o;
    };

    // Bulle centrale : verre, noyau d'énergie qui respire, deux anneaux fins
    const centre = noeud(this.reseau.centre.cle, RAYON_CENTRE, COULEURS.centre, 1.1, 0.3, 0);
    centre.amplitude = 0.025;
    centre.coeur.material.color.setHex(0x8ff6ff);
    const energie = new THREE.Mesh(geoBulle, additif(THREE, new THREE.ShaderMaterial({
      vertexShader: VS_BULLE, fragmentShader: FS_ENERGIE,
      uniforms: { uCouleur: { value: new THREE.Color(0x38e8ff) }, uTemps: temps, uSouffle: { value: 1 } },
    })));
    energie.scale.setScalar(0.42);
    const anneaux = [[1.32, 0.011, [1.15, 0.2, 0]], [1.5, 0.007, [-0.5, 0.9, 0.3]]].map(([r, e, rot]) => {
      const a = new THREE.Mesh(new THREE.TorusGeometry(r, e, 6, 128), additif(THREE, new THREE.MeshBasicMaterial({ color: 0x7ff3ff, opacity: 0.55 })));
      a.rotation.set(...rot);
      centre.racine.add(a);
      return a;
    });
    centre.racine.add(energie);
    Object.assign(t, { centre, energie, anneaux });

    // Agents, liens courbes, têtes d'impulsion
    const N = 40;
    const u = new Float32Array((N + 1) * 2), cote = new Float32Array((N + 1) * 2), index = [];
    for (let i = 0; i <= N; i++) {
      u[2 * i] = u[2 * i + 1] = i / N;
      cote[2 * i] = -1; cote[2 * i + 1] = 1;
      if (i < N) index.push(2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 1, 2 * i + 3, 2 * i + 2);
    }
    const geoLien = new THREE.BufferGeometry();
    geoLien.setAttribute('position', new THREE.BufferAttribute(new Float32Array((N + 1) * 6), 3));
    geoLien.setAttribute('aU', new THREE.BufferAttribute(u, 1));
    geoLien.setAttribute('aCote', new THREE.BufferAttribute(cote, 1));
    geoLien.setIndex(index);
    t.geoLien = geoLien;

    this.reseau.agents.forEach((n, i) => {
      noeud(n.cle, RAYON_AGENT, COULEURS.ok, 1, 0.45, i + 1);
      const materiau = additif(THREE, new THREE.ShaderMaterial({
        vertexShader: VS_LIEN, fragmentShader: FS_LIEN, extensions: { derivatives: true }, side: THREE.DoubleSide,
        uniforms: {
          uA: { value: new THREE.Vector3() }, uB: { value: new THREE.Vector3() }, uC: { value: new THREE.Vector3() },
          uLargeur: { value: 3 }, uResolution: resolution, uCouleur: { value: new THREE.Color(COULEURS.ok) },
          uCouleurCentre: { value: new THREE.Color(COULEURS.centre) }, uOpacite: { value: 0.8 }, uTirets: { value: 0 },
          uRemplissage: { value: 0.55 }, uActif: { value: 1 }, uSens: { value: 1 }, uTemps: temps, uVitesse: { value: 0.4 },
        },
      }));
      const mesh = new THREE.Mesh(geoLien, materiau);
      mesh.frustumCulled = false; // la courbe est calculée par le shader
      mesh.renderOrder = -1;
      groupe.add(mesh);
      const tetes = IMPULSIONS.map(() => { const s = sprite(COULEURS.ok, 0.9); s.scale.setScalar(0.17); groupe.add(s); return s; });
      t.liens.push({ cle: n.cle, mesh, materiau, tetes, controle: new THREE.Vector3(), actif: true, sens: 1, vitesse: 0.4 });
    });

    // Fond de particules très discret (hors du groupe : il ne tourne pas avec le réseau)
    const pos = new Float32Array(PARTICULES * 3), taille = new Float32Array(PARTICULES), phase = new Float32Array(PARTICULES);
    let graine = 7;
    const hasard = () => ((graine = (graine * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < PARTICULES; i++) {
      pos[3 * i] = (hasard() - 0.5) * 22; pos[3 * i + 1] = (hasard() - 0.5) * 15; pos[3 * i + 2] = -2.5 - hasard() * 8;
      taille[i] = 1.2 + hasard() * 2.2; phase[i] = hasard() * 6.28;
    }
    const geoP = new THREE.BufferGeometry();
    geoP.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geoP.setAttribute('aTaille', new THREE.BufferAttribute(taille, 1));
    geoP.setAttribute('aPhase', new THREE.BufferAttribute(phase, 1));
    t.particules = new THREE.Points(geoP, additif(THREE, new THREE.ShaderMaterial({
      vertexShader: VS_PARTICULES, fragmentShader: FS_PARTICULES,
      uniforms: { uEchelle: { value: 10 }, uTemps: temps, uOpacite: { value: 0.32 } },
    })));
    t.particules.frustumCulled = false;
    t.particules.renderOrder = -2;
    scene.add(t.particules);

    // Bloom maison : scène dans une texture, zones brillantes floutées au quart de la résolution
    const ecran = new THREE.Mesh(new THREE.PlaneGeometry(2, 2));
    ecran.frustumCulled = false;
    const passe = (fs, uniforms) => new THREE.ShaderMaterial({ vertexShader: VS_ECRAN, fragmentShader: fs, uniforms, depthTest: false, depthWrite: false });
    t.post = {
      ecran, scene: new THREE.Scene().add(ecran), camera: new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1),
      seuil: passe(FS_SEUIL, { tSource: { value: null }, uTexel: { value: new THREE.Vector2() }, uSeuil: { value: 0.4 } }),
      flou: passe(FS_FLOU, { tSource: { value: null }, uPas: { value: new THREE.Vector2() } }),
      composition: passe(FS_COMPOSITION, { tScene: { value: null }, tBloom: { value: null }, uBloom: { value: 0.95 } }),
    };
    const flottant = rendu.capabilities.isWebGL2 && (rendu.extensions.has('EXT_color_buffer_float') || rendu.extensions.has('EXT_color_buffer_half_float'));
    const options = { type: flottant ? THREE.HalfFloatType : THREE.UnsignedByteType, depthBuffer: false };
    t.post.rtScene = new THREE.WebGLRenderTarget(1, 1, { ...options, depthBuffer: true, samples: rendu.capabilities.isWebGL2 ? 4 : 0 });
    t.post.rtA = new THREE.WebGLRenderTarget(1, 1, options);
    t.post.rtB = new THREE.WebGLRenderTarget(1, 1, options);
    this.#majStyles3D();
  }

  /** Positions de repos des sphères d'après la taille de la zone (l'ellipse remplit la scène). */
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
      const o = t.noeuds.get(n.cle);
      o.base.set((pos[i].x * rx * reduction) / pxParUnite, (pos[i].y * ry * reduction) / pxParUnite, pos[i].z * profondeur);
      // Bulles du fond un peu plus petites et moins lumineuses
      const fond = Math.max(0, -pos[i].z) / 0.55;
      o.rayon = o.rayonBase * (1 - 0.15 * fond);
      o.profondeur = 1 - 0.38 * fond;
    });
    this.#deriver(0);
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
      o.panne = panne;
      o.verre.material.uniforms.uCouleur.value.setHex(c);
      o.verre.material.uniforms.uBord.value = panne ? 0.55 : 1;
      o.verre.material.uniforms.uNoyau.value = panne ? 0.12 : 0.45;
      o.coeur.material.color.setHex(c);
      o.coeurBase = panne ? 0.08 : 0.3;
      const lien = t.liens.find((l) => l.cle === n.cle);
      if (!lien) continue;
      const dec = n.poids === 'decision';
      const u = lien.materiau.uniforms;
      u.uCouleur.value.setHex(c);
      u.uLargeur.value = (dec ? 3 : 1.7) + 2; // + 2 px de fondu (anticrénelage)
      u.uOpacite.value = panne ? 0.42 : dec ? 0.85 : 0.6; // rouge terne en panne
      // En panne : trait interrompu à longs tirets (l'état ne repose pas sur la couleur seule) ; contexte : pointillés
      u.uTirets.value = panne ? 9 : dec ? 0 : 26;
      u.uRemplissage.value = panne ? 0.72 : 0.5;
      u.uActif.value = panne ? 0 : 1;
      lien.actif = !panne;
      lien.sens = n.sens === 'depuis_centre' ? -1 : 1;
      lien.vitesse = dec ? 0.42 : 0.26;
      u.uSens.value = lien.sens;
      u.uVitesse.value = lien.vitesse;
      for (const s of lien.tetes) { s.visible = !panne; s.material.color.setHex(c); }
    }
  }

  /** Qualité : 2 = complète ; 1 = bloom allégé, moitié des particules ; 0 = sans bloom ni particules. */
  #appliquerQualite() {
    const t = this.trois;
    t.particules.visible = this.qualite > 0;
    t.particules.geometry.setDrawRange(0, this.qualite === 2 ? PARTICULES : PARTICULES / 2);
    this.#redimensionner3D();
  }

  #redimensionner3D() {
    const t = this.trois;
    const ratio = Math.min(devicePixelRatio || 1, this.qualite === 0 ? 1.5 : 2);
    t.rendu.setPixelRatio(ratio);
    t.rendu.setSize(this.largeur, this.hauteur, false);
    t.camera.aspect = this.largeur / this.hauteur;
    t.camera.updateProjectionMatrix();
    const L = Math.max(1, Math.round(this.largeur * ratio)), H = Math.max(1, Math.round(this.hauteur * ratio));
    t.post.rtScene.setSize(L, H);
    const l4 = Math.max(1, Math.round(L / 4)), h4 = Math.max(1, Math.round(H / 4));
    t.post.rtA.setSize(l4, h4);
    t.post.rtB.setSize(l4, h4);
    t.post.seuil.uniforms.uTexel.value.set(1 / L, 1 / H); // 4 lectures bilinéaires = moyenne 4 × 4
    t.post.l4 = l4; t.post.h4 = h4;
    t.resolution.value.set(this.largeur, this.hauteur);
    t.particules.material.uniforms.uEchelle.value = 9 * ratio;
    this.#positions3D();
  }

  /** Dérive douce et désynchronisée de chaque bulle ; liens et têtes d'impulsion suivent. */
  #deriver(s) {
    const t = this.trois;
    for (const o of t.noeuds.values()) {
      const [p1, p2, p3] = o.phases, [f1, f2, f3] = o.frequences;
      o.pos.set(
        o.base.x + Math.sin(s * f1 * 2 * Math.PI * 0.5 + p1) * o.amplitude,
        o.base.y + Math.sin(s * f2 * 2 * Math.PI * 0.5 + p2) * o.amplitude * 0.85,
        o.base.z + Math.sin(s * f3 * 2 * Math.PI * 0.5 + p3) * o.amplitude * 0.7,
      );
      o.racine.position.copy(o.pos);
      o.racine.scale.setScalar(o.rayon * o.echelle);
    }
    const c = t.centre.pos;
    for (const lien of t.liens) {
      const a = t.noeuds.get(lien.cle).pos;
      // Point de contrôle : milieu décalé perpendiculairement (tous dans le même sens) et un peu vers l'avant
      const dx = c.x - a.x, dy = c.y - a.y;
      lien.controle.set((a.x + c.x) / 2 - dy * 0.2, (a.y + c.y) / 2 + dx * 0.2, (a.z + c.z) / 2 + 0.25);
      const u = lien.materiau.uniforms;
      u.uA.value.copy(a); u.uB.value.copy(lien.controle); u.uC.value.copy(c);
      if (!lien.actif) continue;
      IMPULSIONS.forEach((phase, i) => {
        const h = (s * lien.vitesse + phase) % 1;
        const tete = lien.tetes[i];
        bezier(a, lien.controle, c, lien.sens > 0 ? h : 1 - h, tete.position);
        tete.material.opacity = Math.sin(Math.PI * h) * 0.9;
      });
    }
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
      // Positions arrondies au pixel : libellés nets
      res.push({ cle, x: Math.round((v.x + 1) / 2 * this.largeur), y: Math.round((1 - v.y) / 2 * this.hauteur), r: profondeur > 0.1 ? (o.rayon * o.echelle * f) / profondeur : 0, cache: profondeur <= 0.1 }); // derrière la caméra ; hors champ, la zone rogne (le bouton reste atteignable au clavier)
    }
    return res;
  }

  /** Réaction au toucher : appui = léger grossissement ; relâché = rebond amorti ; validation = onde lumineuse. */
  #appuyer(cle, appui) {
    const o = this.trois?.noeuds.get(cle);
    if (!o) return;
    o.cibleEchelle = appui ? 1.14 : 1;
    this.#demander(true);
  }

  #reagir(cle) {
    const o = this.trois?.noeuds.get(cle);
    if (!o) return;
    o.onde = performance.now();
    o.cibleEchelle = 1;
    o.vEchelle += 2.2; // petite impulsion : la bulle gonfle puis revient en rebondissant
    this.#demander(true);
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
      // Position de repos (sans la dérive) : la caméra ne tangue pas
      const p = (t.vf ??= new t.THREE.Vector3()).copy(o.base).applyMatrix4(t.groupe.matrixWorld);
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
        for (const cle of this.boutons.keys()) this.#appuyer(cle, false); // un glissement n'est pas un appui
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

  /** Demande une image (`interaction` : geste en cours, la rotation n'est pas rappelée). */
  #demander(interaction = false) {
    if (interaction) this.derniereInteraction = performance.now();
    this.#relancer();
  }

  /** Cadence mesurée sur 2 s ; sous 40 images/s, la qualité baisse d'un cran (bloom, puis particules). */
  #surveillerCadence(maintenant, ecart) {
    const m = this.mesure;
    if (!m.debut || ecart > 250) { m.debut = maintenant; m.images = 0; return; } // reprise après une pause : on ne compte pas
    m.images++;
    const duree = maintenant - m.debut;
    if (duree < 2000) return;
    const ips = (m.images * 1000) / duree;
    m.debut = maintenant; m.images = 0;
    if (ips < 40 && this.qualite > 0 && maintenant - this.debut > 1500) {
      this.qualite--;
      this.conteneur.dataset.qualite = String(this.qualite);
      this.#appliquerQualite();
    }
  }

  /** Ressort critique (sans dépassement) : départ et arrivée doux. */
  static #ressort(x, v, cible, ds) {
    const w = PULSATION_CAMERA;
    v.x += (w * w * (cible.x - x.x) - 2 * w * v.x) * ds; x.x += v.x * ds;
    v.y += (w * w * (cible.y - x.y) - 2 * w * v.y) * ds; x.y += v.y * ds;
    v.z += (w * w * (cible.z - x.z) - 2 * w * v.z) * ds; x.z += v.z * ds;
  }

  #image(maintenant) {
    this.raf = 0;
    if (!this.actif || document.hidden || !this.trois) return;
    this.raf = requestAnimationFrame(this.boucle);
    const ecart = maintenant - (this.dernierRendu || maintenant);
    this.dernierRendu = maintenant;
    this.#surveillerCadence(maintenant, ecart);
    const dt = Math.min(3, ecart / 16.7 || 1);
    const secondes = Math.min(0.05, ecart / 1000 || 1 / 60);
    const pas = Math.max(1, Math.ceil(secondes / (1 / 120))); // sous-pas : ressorts stables même à basse cadence
    const ds = secondes / pas;
    const t = this.trois;

    // Rotation : inertie, amplitude limitée, retour doux à la position de face
    if (!(this.pointeurs.size && this.aGlisse)) {
      this.vLacet += -this.lacet * RAPPEL * dt * (Math.abs(this.lacet) > LIMITE_LACET ? 6 : 1);
      this.vTangage += -this.tangage * RAPPEL * dt * (Math.abs(this.tangage) > LIMITE_TANGAGE ? 6 : 1);
      const a = AMORTI ** dt;
      this.vLacet *= a; this.vTangage *= a;
      this.lacet += this.vLacet * dt;
      this.tangage += this.vTangage * dt;
    }
    this.zoom += (this.zoomCible - this.zoom) * (1 - Math.exp(-secondes * 9));
    t.groupe.rotation.set(this.tangage, this.lacet, 0);
    t.groupe.updateMatrixWorld();

    // Caméra : ressort critique vers sa cible (vue d'ensemble ou bulle choisie), ~400 ms, sans à-coup
    const cible = this.#cibleCamera();
    for (let i = 0; i < pas; i++) {
      SceneReseau.#ressort(t.camPos, t.camVit, cible.pos, ds);
      SceneReseau.#ressort(t.vise, t.viseVit, cible.vise, ds);
    }
    t.camera.position.copy(t.camPos);
    t.camera.lookAt(t.vise);
    t.camera.updateMatrixWorld();

    // Bulles : rebond amorti, onde au toucher, lumière (profondeur, focus) en fondu de ~350 ms
    const s = (maintenant - this.debut) / 1000;
    t.temps.value = s;
    const fondu = 1 - Math.exp(-secondes / 0.11);
    for (const o of t.noeuds.values()) {
      for (let i = 0; i < pas; i++) {
        o.vEchelle += (RESSORT.raideur * (o.cibleEchelle - o.echelle) - RESSORT.amorti * o.vEchelle) * ds;
        o.echelle += o.vEchelle * ds;
      }
      const u = o.verre.material.uniforms;
      const onde = o.onde > 0 ? (maintenant - o.onde) / 750 : 2;
      u.uOnde.value = onde > 0 && onde < 1 ? Math.max(0.001, onde) : 0;
      if (onde >= 1) o.onde = -1;
      o.lumiereCible = this.focusCle && this.focusCle !== o.cle ? 0.3 : 1;
      o.lumiere += (o.lumiereCible - o.lumiere) * fondu;
      u.uLumiere.value = o.lumiere * o.profondeur;
      o.coeur.material.opacity = (o.coeurBase ?? 0.5) * o.lumiere * o.profondeur;
    }
    // Centre : noyau d'énergie qui respire (cycle de 4,5 s), anneaux en rotation lente
    const souffle = 0.5 + 0.5 * Math.sin((s * 2 * Math.PI) / 4.5);
    t.energie.scale.setScalar(0.38 + 0.07 * souffle);
    t.energie.material.uniforms.uSouffle.value = 0.7 + 0.4 * souffle;
    t.centre.coeur.scale.setScalar(0.7 + 0.2 * souffle);
    t.anneaux[0].rotation.z += 0.16 * secondes;
    t.anneaux[1].rotation.z -= 0.1 * secondes;
    t.anneaux[1].rotation.x += 0.035 * secondes;
    t.particules.rotation.y = Math.sin(s * 0.05) * 0.06;
    this.#deriver(s);
    this.#rendre();

    // Libellés : suivent les bulles (dérive comprise), au pixel près
    const vueEnsemble = !this.focusCle && this.zoom <= 1.02;
    this.#placer(this.#projeter3D(), vueEnsemble);
  }

  /** Scène dans une texture, bloom au quart de la résolution, composition sur le canevas transparent. */
  #rendre() {
    const t = this.trois, P = t.post, r = t.rendu;
    r.setRenderTarget(P.rtScene);
    r.render(t.scene, t.camera);
    if (this.qualite > 0) {
      P.ecran.material = P.seuil;
      P.seuil.uniforms.tSource.value = P.rtScene.texture;
      r.setRenderTarget(P.rtA);
      r.render(P.scene, P.camera);
      for (const k of this.qualite === 2 ? [1, 2.2] : [1.6]) {
        P.ecran.material = P.flou;
        P.flou.uniforms.tSource.value = P.rtA.texture;
        P.flou.uniforms.uPas.value.set(k / P.l4, 0);
        r.setRenderTarget(P.rtB);
        r.render(P.scene, P.camera);
        P.flou.uniforms.tSource.value = P.rtB.texture;
        P.flou.uniforms.uPas.value.set(0, k / P.h4);
        r.setRenderTarget(P.rtA);
        r.render(P.scene, P.camera);
      }
    }
    P.ecran.material = P.composition;
    P.composition.uniforms.tScene.value = P.rtScene.texture;
    P.composition.uniforms.tBloom.value = P.rtA.texture;
    P.composition.uniforms.uBloom.value = this.qualite === 2 ? 0.95 : this.qualite === 1 ? 0.7 : 0;
    r.setRenderTarget(null);
    r.render(P.scene, P.camera);
  }

  detruire() {
    this.actif = false;
    this.#relancer();
    this.observateur.disconnect();
    document.removeEventListener('visibilitychange', this.surVisibilite);
    if (this.trois) {
      const { rendu, scene, post, halo } = this.trois;
      scene.traverse((o) => { o.geometry?.dispose?.(); o.material?.dispose?.(); });
      post.ecran.geometry.dispose();
      [post.seuil, post.flou, post.composition].forEach((m) => m.dispose());
      [post.rtScene, post.rtA, post.rtB].forEach((rt) => rt.dispose());
      halo.dispose();
      rendu.dispose();
    }
    this.trois = null;
    this.svg = null;
    this.conteneur.replaceChildren();
  }
}
