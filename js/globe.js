/* ==========================================================================
   Globe 3D (Three.js)
   --------------------------------------------------------------------------
   - Sphère de points lumineux (continents brillants, océans discrets)
   - Halo atmosphérique, méridiens et parallèles discrets
   - Pour chaque pays : colonne (hauteur + couleur = note), anneau qui pulse,
     étiquette HTML (nom + note)
   - Arcs animés de flux de capitaux, avec points lumineux qui circulent
   - Rotation au doigt avec inertie, rotation automatique au repos,
     pivot automatique vers un pays sélectionné
   - Mode léger : moins de points, pas d'animation des flux, 30 images/s
   ========================================================================== */

// Three.js r160, version fixée, servie par le CDN cdnjs.
import * as THREE from 'https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.module.min.js';
import { COULEURS, niveauNote, el, nombre } from './outils.js';

/* --------------------------------------------------------------------------
   Contours très simplifiés des continents, en [longitude, latitude].
   Ils servent uniquement à décider si un point du globe est « terre » ou
   « mer » ; la précision d'une carte n'est pas nécessaire.
   Les deux derniers polygones (mer Noire, mer Caspienne) sont des « trous » :
   un point est sur terre s'il est à l'intérieur d'un nombre impair de polygones.
   -------------------------------------------------------------------------- */
const CONTINENTS = [
  // Amérique du Nord
  [[-168,66],[-162,70],[-156,71.5],[-140,70],[-128,70],[-115,68],[-95,72],[-85,70],[-80,64],[-95,59],[-90,57],[-82,55],[-79,52],[-77,59],[-70,61],[-64,60],[-60,55],[-56,52],[-60,47],[-66,45],[-70,42],[-74,40],[-76,35],[-81,31],[-80,26],[-82,27],[-84,30],[-89,30],[-94,29],[-97,27],[-97,22],[-95,19],[-91,19],[-90,21],[-87,21],[-88,16],[-84,15],[-83,10],[-79,9],[-78,7],[-81,8],[-86,11],[-92,14],[-96,16],[-105,20],[-109,25],[-112,29],[-115,32],[-118,34],[-121,36],[-124,40],[-124,46],[-125,49],[-130,54],[-135,58],[-140,60],[-148,61],[-152,59],[-158,57],[-164,55],[-158,59],[-162,60],[-166,62],[-165,64]],
  // Groenland
  [[-73,78],[-60,82],[-30,83],[-20,80],[-20,72],[-25,68],[-40,65],[-44,60],[-50,62],[-54,67],[-58,75]],
  // Amérique du Sud
  [[-80,9],[-75,11],[-72,12],[-62,11],[-58,7],[-52,5],[-50,1],[-44,-2],[-35,-5],[-35,-9],[-39,-14],[-40,-21],[-48,-26],[-53,-34],[-58,-38],[-62,-40],[-65,-45],[-68,-50],[-69,-54],[-73,-53],[-75,-46],[-73,-38],[-71,-30],[-70,-18],[-76,-14],[-81,-6],[-80,-1],[-77,4],[-78,8]],
  // Eurasie
  [[-9,37],[-9,43],[-2,43.5],[-1,46],[-4.5,48],[-1,49.5],[2,51],[5,53],[8,54],[8,57],[10,57.5],[10.5,54.5],[13,54.5],[18,55],[21,57],[24,59.5],[28,60],[22,60.5],[21,63],[25,65.5],[22,66],[17,62.5],[19,60],[16,56],[12.5,56],[11,59],[8,58],[5,59],[5,62],[10,64],[14,67],[17,69],[24,71],[30,70],[40,67],[44,68.5],[55,68],[60,69],[68,72],[75,72.5],[80,73.5],[87,75],[100,77],[105,78],[113,74],[120,73],[130,72],[140,72],[150,71],[160,70],[170,70],[180,69],[180,65],[178,64],[173,61],[163,60],[162,57],[156,51],[156,57],[160,61],[155,59.5],[143,59.5],[137,54],[141,52],[140,48],[135,43],[130,42.5],[129,35.5],[126.5,34.5],[126,37.5],[124.5,40],[121,41],[122,39],[118,38.5],[120,37],[122.5,37],[119,34.5],[121.5,31],[122,29],[119,25.5],[116,23],[110.5,21],[108,21.5],[106,19],[108.5,15],[109,11.5],[105,8.5],[104,10.5],[101,13],[99.5,10],[103.5,1.5],[101,3],[98.5,8],[98,16],[94.5,16.5],[94,19],[92,21.5],[90,22],[87,21.5],[86.5,20],[80,15.5],[80,10],[77.5,8],[76,10],[74,15],[72.8,19],[72.5,21.5],[70,22.5],[67,24.5],[61.5,25.2],[57,25.8],[56.5,27],[52,28],[50,30],[48,30],[48.5,28.5],[50,26],[51.5,24],[54,24],[56,24.5],[56.5,22.5],[59.8,22.5],[57,19],[55,17],[52,16],[45,13],[43,13],[43,16],[40,21],[39,22],[35,28],[34.5,29.5],[34.2,31.3],[35,33],[36,35.5],[34,36.5],[30,36.3],[27,37],[26.3,39.5],[26,40.8],[24,40.5],[23,39],[22.5,36.5],[21,38],[19.5,41.8],[16,43.5],[13.5,45.5],[12.3,44.5],[14,42],[16,41],[18.5,40.2],[16,38],[15.5,40],[12,41.8],[10.5,43],[8.5,44.3],[6.5,43.1],[4,43.5],[3,42],[0,39],[-0.5,38],[-2,36.8],[-5.5,36],[-7,37]],
  // Grande-Bretagne, Irlande, Islande
  [[-5.5,50],[1.5,51],[1.7,52.8],[0,53.5],[-1.5,55],[-2,56],[-1.8,57.5],[-3,58.6],[-5,58.6],[-6,57],[-5.5,55.3],[-4.8,54.8],[-3,54],[-3,53.3],[-4.5,52.8],[-5,51.6],[-3,51.4]],
  [[-10,51.6],[-6,52],[-6,53.9],[-5.8,55.2],[-8,55.2],[-10,54]],
  [[-24,65.5],[-22,66.5],[-15,66.5],[-13.5,65],[-18,63.4],[-22,63.8]],
  // Afrique et Madagascar
  [[-17,21],[-17,14.7],[-16.7,12.5],[-13,8],[-8,4.5],[-4,5.2],[2,6.2],[5,4.5],[7,4.4],[9.5,3.8],[9.5,1],[12,-5],[13.5,-11],[11.8,-17],[14.5,-22.5],[15.3,-27],[17,-29],[18.4,-34],[20,-34.8],[25,-34],[28,-33],[32.5,-28.5],[32.9,-25.8],[35.5,-24],[35.3,-22],[34.7,-19.8],[37,-17.5],[40.5,-15],[40.5,-10.5],[39.3,-7],[39.5,-4.5],[41,-2],[43.5,1],[46,2.5],[51,10.5],[51.2,12],[48.5,11.3],[44,10.5],[43.2,11.8],[42.5,15],[39.5,15.5],[38.5,18],[37,21],[36,24],[35,26.5],[33.5,28],[32.5,30],[31,31.5],[29,30.9],[25,31.8],[20,30.5],[19,30.3],[15.5,32],[11.5,33],[10,37],[3,36.8],[-1,35.5],[-5.9,35.8],[-9.7,30.5],[-13,27.5]],
  [[43.3,-22],[44,-25],[47,-25],[50.5,-15.5],[49.3,-12],[47,-15.5],[44,-16.8]],
  // Océanie
  [[113.5,-22],[114,-26],[115,-34],[118,-35],[123.5,-34],[129,-31.6],[134,-32.8],[138,-35.5],[140,-38],[146,-39],[150,-37.5],[153.5,-28],[153,-25],[149,-21],[146,-18.8],[145.3,-15],[142.5,-10.7],[141.5,-16.8],[139.3,-17.4],[136,-15],[137,-12],[132.5,-11.2],[130,-13],[126,-14],[122,-18],[121,-19.5],[117,-20.6]],
  [[144.5,-40.8],[148.3,-40.9],[148,-43.2],[146,-43.6],[144.7,-42]],
  [[172.7,-34.4],[175,-37],[178.5,-37.7],[176,-41.5],[174.7,-41.3],[173.8,-39.2]],
  [[172.7,-40.5],[174.3,-41.7],[171,-44.5],[169,-46.6],[166.5,-46],[168,-44]],
  [[131,-1],[134,-0.8],[138,-1.5],[141,-2.6],[145.5,-5],[150,-10.5],[146,-8.5],[143.5,-9],[141,-9.1],[138,-8.3],[137.5,-5],[133,-4],[132,-2.8]],
  // Asie insulaire
  [[130,31.3],[131.8,33.5],[135,33.5],[137,34.6],[140,35],[141,38],[142,40],[141.5,41.5],[140,41.5],[140,40],[139.8,38.5],[138.5,37.3],[136.8,37.2],[136,35.7],[133,35.5],[131,34.4],[129.7,33.3]],
  [[140,41.6],[141.5,42.5],[143.3,42],[145.5,43.3],[144,44.2],[141.7,45.4],[141.3,43.2],[140,42.5]],
  [[120.2,22.6],[120.9,21.9],[121.9,24.6],[121.5,25.3],[120.1,23.5]],
  [[79.8,9.8],[81.9,7.5],[81.2,6.1],[80,6.2]],
  [[95.3,5.6],[97.5,5.2],[104.5,-1.6],[106,-3.2],[105.8,-5.8],[102.3,-4],[100.3,-1],[98.7,1.7]],
  [[109,1.5],[109.7,-1.2],[110.2,-3],[114.5,-4],[116.5,-3.5],[118,1],[119,5],[117,7],[115.5,5],[113,3.2],[111,1.6]],
  [[105.2,-6.8],[108.5,-6.4],[112.5,-6.8],[114.5,-7.8],[110,-8.2],[105.5,-7.4]],
  [[119.5,-5.5],[120.5,-1],[121.5,1],[125,1.5],[120.5,0.5],[121.5,-1],[123,-1],[121,-2],[122,-5],[120.5,-5.6]],
  [[120,18.5],[122.2,18.5],[122,16],[124,13],[121.5,13.8],[120.6,14.5],[120,16]],
  [[122,7],[125.5,9.8],[126.6,7.2],[125.3,5.6],[123.6,7.6]],
  // Trous : mer Noire, mer Caspienne
  [[28,41.2],[28,43.5],[29.5,45.5],[33,46],[36.5,45.3],[39,47],[41.5,41.6],[36,41.5],[33,42]],
  [[47,44.5],[50,46.8],[53,46.8],[53,42],[54,37.5],[50,37],[49,40],[47,43]],
];

// Boîtes englobantes pré-calculées pour accélérer le test terre/mer
const BOITES = CONTINENTS.map((poly) => {
  let minLon = 180, maxLon = -180, minLat = 90, maxLat = -90;
  for (const [lon, lat] of poly) {
    minLon = Math.min(minLon, lon); maxLon = Math.max(maxLon, lon);
    minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
  }
  return { minLon, maxLon, minLat, maxLat };
});

/** Test « point dans polygone » par lancer de rayon. */
function dansPolygone(lon, lat, poly) {
  let dedans = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) dedans = !dedans;
  }
  return dedans;
}

/** Le point (lat, lon) est-il sur un continent ? */
function estTerre(lat, lon) {
  if (lat < -68) return true; // Antarctique, simplifié
  let compte = 0;
  for (let k = 0; k < CONTINENTS.length; k++) {
    const b = BOITES[k];
    if (lon < b.minLon || lon > b.maxLon || lat < b.minLat || lat > b.maxLat) continue;
    if (dansPolygone(lon, lat, CONTINENTS[k])) compte++;
  }
  return compte % 2 === 1;
}

/**
 * Convertit latitude/longitude (en degrés) en position 3D.
 * Convention : longitude 0 et latitude 0 face à la caméra (axe +Z), nord vers +Y.
 */
function versVecteur(lat, lon, rayon = 1) {
  const la = THREE.MathUtils.degToRad(lat);
  const lo = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(rayon * Math.cos(la) * Math.sin(lo), rayon * Math.sin(la), rayon * Math.cos(la) * Math.cos(lo));
}

/** Petite texture ronde et floue, utilisée pour tous les points lumineux. */
function texturePoint() {
  const taille = 64;
  const toile = document.createElement('canvas');
  toile.width = toile.height = taille;
  const ctx = toile.getContext('2d');
  const degrade = ctx.createRadialGradient(taille / 2, taille / 2, 0, taille / 2, taille / 2, taille / 2);
  degrade.addColorStop(0, 'rgba(255,255,255,1)');
  degrade.addColorStop(0.35, 'rgba(255,255,255,0.75)');
  degrade.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = degrade;
  ctx.fillRect(0, 0, taille, taille);
  const texture = new THREE.CanvasTexture(toile);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/* Réglages généraux */
const ROTATION_AUTO = 0.1;      // vitesse de rotation au repos (radians/seconde)
const DELAI_REPOS = 2500;       // délai avant reprise de la rotation automatique (ms)
const AMORTISSEMENT = 2.6;      // plus la valeur est grande, plus l'inertie s'arrête vite
const INCLINAISON_MAX = 1.15;   // limite d'inclinaison nord/sud (radians)
const INCLINAISON_REPOS = 0.32; // inclinaison par défaut (on voit un peu plus l'hémisphère nord)

export class Globe {
  /**
   * @param {HTMLCanvasElement} toile  le canvas où dessiner
   * @param {HTMLElement} calqueEtiquettes  le conteneur des étiquettes HTML
   * @param {object} options  { pays, leger, surSelection(code) }
   */
  constructor(toile, calqueEtiquettes, { pays, leger = false, surSelection = () => {} }) {
    this.toile = toile;
    this.calque = calqueEtiquettes;
    this.pays = pays;
    this.surSelection = surSelection;
    this.leger = leger;
    this.actif = true;
    this.selection = null;

    // État de la rotation (lacet = gauche/droite, tangage = haut/bas)
    this.lacet = -THREE.MathUtils.degToRad(15);
    this.tangage = INCLINAISON_REPOS;
    this.vitesseLacet = 0;
    this.vitesseTangage = 0;
    this.cible = null;                // { lacet, tangage } quand on pivote vers un pays
    this.dernierContact = -Infinity;  // horodatage du dernier geste

    // Cadrage : centre et rayon du globe à l'écran (en pixels), animés en douceur
    this.cadrage = { cx: innerWidth / 2, cy: innerHeight / 2, rayon: Math.min(innerWidth, innerHeight) * 0.38 };
    this.cadrageCible = { ...this.cadrage };

    // Moteur de rendu (peut échouer si WebGL n'est pas disponible)
    this.rendu = new THREE.WebGLRenderer({ canvas: toile, antialias: !leger, alpha: true, powerPreference: 'low-power' });
    this.rendu.setClearColor(0x000000, 0);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(36, innerWidth / innerHeight, 0.1, 100);
    this.camera.position.set(0, 0, 4);

    this.groupe = new THREE.Group(); // tout ce qui tourne avec la Terre
    this.scene.add(this.groupe);
    this.texture = texturePoint();

    this.#creerSphere();
    this.#creerPoints();
    this.#creerHalo();
    this.#creerGrille();
    this.#creerPays();
    this.#creerFlux();
    this.#brancherGestes();

    this.redimensionner();
    addEventListener('resize', () => this.redimensionner());

    this.horloge = new THREE.Clock();
    this.debut = performance.now();
    this.dernierRendu = 0;
    this.boucle = (t) => this.#boucle(t);
    requestAnimationFrame(this.boucle);
  }

  /* ======================= Construction de la scène ======================= */

  /** Sphère sombre intérieure : elle masque les points situés à l'arrière du globe. */
  #creerSphere() {
    const geo = new THREE.SphereGeometry(0.985, 64, 48);
    const mat = new THREE.MeshBasicMaterial({ color: 0x030916 });
    this.groupe.add(new THREE.Mesh(geo, mat));
  }

  /** Nuage de points répartis uniformément (spirale de Fibonacci). */
  #creerPoints() {
    if (this.nuages) {
      for (const n of this.nuages) { this.groupe.remove(n); n.geometry.dispose(); }
    }
    const total = this.leger ? 7000 : 16000;
    const terre = [], couleursTerre = [], mer = [];
    const angleOr = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < total; i++) {
      const y = 1 - (2 * (i + 0.5)) / total;
      const r = Math.sqrt(1 - y * y);
      const theta = angleOr * i;
      const x = r * Math.sin(theta);
      const z = r * Math.cos(theta);
      const lat = THREE.MathUtils.radToDeg(Math.asin(y));
      const lon = THREE.MathUtils.radToDeg(Math.atan2(x, z));
      if (estTerre(lat, lon)) {
        terre.push(x, y, z);
        const b = 0.55 + Math.random() * 0.45; // léger scintillement
        couleursTerre.push(0.2 * b, 0.85 * b, 1.0 * b);
      } else if (i % 5 === 0) {
        mer.push(x, y, z); // les océans ne gardent qu'un point sur cinq
      }
    }
    const geoTerre = new THREE.BufferGeometry();
    geoTerre.setAttribute('position', new THREE.Float32BufferAttribute(terre, 3));
    geoTerre.setAttribute('color', new THREE.Float32BufferAttribute(couleursTerre, 3));
    const nuageTerre = new THREE.Points(geoTerre, new THREE.PointsMaterial({
      size: this.leger ? 0.03 : 0.022, map: this.texture, vertexColors: true,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));

    const geoMer = new THREE.BufferGeometry();
    geoMer.setAttribute('position', new THREE.Float32BufferAttribute(mer, 3));
    const nuageMer = new THREE.Points(geoMer, new THREE.PointsMaterial({
      size: 0.014, map: this.texture, color: 0x1d5a8c, transparent: true, opacity: 0.55,
      depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.nuages = [nuageTerre, nuageMer];
    this.groupe.add(nuageTerre, nuageMer);
  }

  /** Halo atmosphérique cyan autour du globe (effet de « bord lumineux »). */
  #creerHalo() {
    const mat = new THREE.ShaderMaterial({
      uniforms: { couleur: { value: new THREE.Color(0x00c8ff) } },
      vertexShader: `
        varying vec3 vNormale;
        void main() {
          vNormale = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        uniform vec3 couleur;
        varying vec3 vNormale;
        void main() {
          float d = max(0.0, -dot(vNormale, vec3(0.0, 0.0, 1.0)));
          float intensite = pow(d, 2.2) * 1.1;
          gl_FragColor = vec4(couleur * intensite, intensite);
        }`,
      side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    this.halo = new THREE.Mesh(new THREE.SphereGeometry(1.22, 64, 48), mat);
    this.scene.add(this.halo); // le halo ne tourne pas (il est symétrique)
  }

  /** Méridiens (tous les 30°) et parallèles discrets. */
  #creerGrille() {
    const mat = new THREE.LineBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.07, depthWrite: false });
    for (let lon = -180; lon < 180; lon += 30) {
      const pts = [];
      for (let lat = -90; lat <= 90; lat += 3) pts.push(versVecteur(lat, lon, 1.002));
      this.groupe.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
    }
    for (const lat of [-60, -30, 0, 30, 60]) {
      const pts = [];
      for (let lon = -180; lon <= 180; lon += 3) pts.push(versVecteur(lat, lon, 1.002));
      this.groupe.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
    }
  }

  /** Colonnes, anneaux et étiquettes des pays. */
  #creerPays() {
    this.objetsPays = [];
    const haut = new THREE.Vector3(0, 1, 0);
    const avant = new THREE.Vector3(0, 0, 1);
    this.calque.replaceChildren();

    this.pays.forEach((p, index) => {
      const normale = versVecteur(p.lat, p.lon).normalize();
      const couleur = new THREE.Color(COULEURS[niveauNote(p.note)]);
      const hauteur = 0.06 + (p.note / 100) * 0.34; // hauteur proportionnelle à la note

      // Colonne : un cylindre dont la base est posée sur la surface
      const geoColonne = new THREE.CylinderGeometry(0.009, 0.013, hauteur, 10, 1, true);
      geoColonne.translate(0, hauteur / 2, 0);
      const colonne = new THREE.Mesh(geoColonne, new THREE.MeshBasicMaterial({
        color: couleur, transparent: true, opacity: 0.85, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      colonne.position.copy(normale);
      colonne.quaternion.setFromUnitVectors(haut, normale);

      // Point lumineux au sommet de la colonne
      const sommet = new THREE.Sprite(new THREE.SpriteMaterial({
        map: this.texture, color: couleur, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      sommet.scale.setScalar(0.075);
      sommet.position.copy(normale).multiplyScalar(1 + hauteur);

      // Anneau au pied de la colonne (il pulse)
      const anneau = new THREE.Mesh(new THREE.RingGeometry(0.022, 0.029, 40), new THREE.MeshBasicMaterial({
        color: couleur, transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      anneau.position.copy(normale).multiplyScalar(1.004);
      anneau.quaternion.setFromUnitVectors(avant, normale);

      this.groupe.add(colonne, sommet, anneau);

      // Étiquette HTML : nom + note (un vrai bouton, donc accessible au clavier)
      const etiquette = el('button', {
        class: `etiquette note--${niveauNote(p.note)} est-cachee`,
        type: 'button',
        'aria-label': `${p.nom}, note ${p.note} sur 100`,
        onclick: () => this.surSelection(p.code),
      }, p.nom, ' ', el('span', { class: 'mono' }, nombre(p.note)));
      this.calque.append(etiquette);

      this.objetsPays.push({
        code: p.code, normale, hauteur, colonne, sommet, anneau, etiquette,
        phase: index * 0.137, // décalage pour que les anneaux ne pulsent pas tous ensemble
        haut: normale.clone().multiplyScalar(1 + hauteur + 0.03),
        visible: false, x: 0, y: 0,
      });
    });
  }

  /** Arcs de flux de capitaux + points lumineux qui circulent dessus. */
  #creerFlux() {
    const parCode = new Map(this.pays.map((p) => [p.code, p]));
    this.arcs = [];
    const matArc = new THREE.LineBasicMaterial({
      color: 0x00e5ff, transparent: true, opacity: 0.3, depthWrite: false, blending: THREE.AdditiveBlending,
    });

    for (const p of this.pays) {
      for (const f of p.flux ?? []) {
        const cible = parCode.get(f.vers);
        if (!cible) continue;
        // Montant négatif = flux dans l'autre sens
        const [de, vers] = f.montant_md >= 0 ? [p, cible] : [cible, p];
        const a = versVecteur(de.lat, de.lon, 1.003);
        const b = versVecteur(vers.lat, vers.lon, 1.003);
        const altitude = 0.12 + a.angleTo(b) * 0.28; // les arcs longs montent plus haut
        const milieu = a.clone().add(b).normalize().multiplyScalar(1 + altitude);
        const courbe = new THREE.QuadraticBezierCurve3(a, milieu, b);
        const ligne = new THREE.Line(new THREE.BufferGeometry().setFromPoints(courbe.getPoints(60)), matArc);
        this.groupe.add(ligne);
        const montant = Math.abs(f.montant_md);
        this.arcs.push({
          courbe,
          vitesse: 0.12 + Math.min(montant, 20) * 0.006,
          nbPoints: Math.min(4, 1 + Math.round(montant / 6)),
        });
      }
    }

    // Tous les points circulants partagent une seule géométrie (plus économe)
    const total = this.arcs.reduce((s, a) => s + a.nbPoints, 0);
    this.positionsFlux = new Float32Array(total * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.positionsFlux, 3));
    this.pointsFlux = new THREE.Points(geo, new THREE.PointsMaterial({
      size: 0.045, map: this.texture, color: 0xa8f7ff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.pointsFlux.frustumCulled = false;
    this.groupe.add(this.pointsFlux);
    this.#placerPointsFlux(0);
  }

  #placerPointsFlux(temps) {
    const v = new THREE.Vector3();
    let k = 0;
    for (const arc of this.arcs) {
      for (let i = 0; i < arc.nbPoints; i++) {
        const t = (temps * arc.vitesse + i / arc.nbPoints) % 1;
        arc.courbe.getPoint(t, v);
        this.positionsFlux[k++] = v.x;
        this.positionsFlux[k++] = v.y;
        this.positionsFlux[k++] = v.z;
      }
    }
    this.pointsFlux.geometry.attributes.position.needsUpdate = true;
  }

  /* ============================ Gestes tactiles ============================ */

  #brancherGestes() {
    let doigt = null; // identifiant du pointeur suivi (on ignore les autres doigts)
    let depart = null;
    let precedent = null;

    this.toile.addEventListener('pointerdown', (e) => {
      if (doigt !== null) return;
      doigt = e.pointerId;
      this.toile.setPointerCapture(e.pointerId);
      depart = { x: e.clientX, y: e.clientY, t: performance.now() };
      precedent = { ...depart };
      this.vitesseLacet = this.vitesseTangage = 0;
      this.cible = null;
      this.glisse = true;
      this.dernierContact = performance.now();
    });

    this.toile.addEventListener('pointermove', (e) => {
      if (e.pointerId !== doigt) return;
      const maintenant = performance.now();
      const dt = Math.max(1, maintenant - precedent.t) / 1000;
      // Un pixel de déplacement ≈ un pixel de surface : le globe « colle » au doigt
      const k = 1 / Math.max(80, this.cadrage.rayon);
      const dLacet = (e.clientX - precedent.x) * k;
      const dTangage = (e.clientY - precedent.y) * k;
      this.lacet += dLacet;
      this.tangage = THREE.MathUtils.clamp(this.tangage + dTangage, -INCLINAISON_MAX, INCLINAISON_MAX);
      // Vitesse lissée, réutilisée pour l'inertie au lâcher
      this.vitesseLacet = this.vitesseLacet * 0.6 + (dLacet / dt) * 0.4;
      this.vitesseTangage = this.vitesseTangage * 0.6 + (dTangage / dt) * 0.4;
      precedent = { x: e.clientX, y: e.clientY, t: maintenant };
      this.dernierContact = maintenant;
    });

    const relacher = (e) => {
      if (e.pointerId !== doigt) return;
      doigt = null;
      this.glisse = false;
      this.dernierContact = performance.now();
      const distance = Math.hypot(e.clientX - depart.x, e.clientY - depart.y);
      // Si le doigt n'est pas resté immobile juste avant le lâcher, on garde l'élan
      if (performance.now() - precedent.t > 80) this.vitesseLacet = this.vitesseTangage = 0;
      // Un appui bref sans déplacement = un « toucher » : on cherche le pays le plus proche
      if (e.type === 'pointerup' && distance < 8 && performance.now() - depart.t < 450) {
        this.vitesseLacet = this.vitesseTangage = 0;
        const code = this.#paysSousLeDoigt(e.clientX, e.clientY);
        if (code) this.surSelection(code);
      }
    };
    this.toile.addEventListener('pointerup', relacher);
    this.toile.addEventListener('pointercancel', relacher);
  }

  /** Renvoie le code du pays visible le plus proche du point touché (ou null). */
  #paysSousLeDoigt(x, y) {
    let meilleur = null;
    let distanceMin = 36; // tolérance en pixels, généreuse pour les doigts
    const v = new THREE.Vector3();
    for (const o of this.objetsPays) {
      if (!o.visible) continue;
      for (const point of [o.normale, o.haut]) {
        v.copy(point).applyMatrix4(this.groupe.matrixWorld).project(this.camera);
        const px = ((v.x + 1) / 2) * this.largeur;
        const py = ((1 - v.y) / 2) * this.hauteur;
        const d = Math.hypot(px - x, py - y);
        if (d < distanceMin) { distanceMin = d; meilleur = o.code; }
      }
    }
    return meilleur;
  }

  /* ============================== API publique ============================== */

  /** Fait pivoter le globe vers un pays et le met en évidence. */
  focaliser(code) {
    const p = this.pays.find((x) => x.code === code);
    if (!p) return;
    this.selection = code;
    this.cible = {
      lacet: -THREE.MathUtils.degToRad(p.lon),
      tangage: THREE.MathUtils.clamp(THREE.MathUtils.degToRad(p.lat), -INCLINAISON_MAX, INCLINAISON_MAX),
    };
    this.vitesseLacet = this.vitesseTangage = 0;
  }

  /** Retire la mise en évidence ; la rotation automatique reprendra. */
  deselectionner() {
    this.selection = null;
    this.cible = null;
    this.dernierContact = performance.now() - DELAI_REPOS + 800;
  }

  /** Indique où placer le globe à l'écran : centre (px) et rayon (px). */
  definirCadrage({ cx, cy, rayon, hautLibre = 0 }) {
    this.cadrageCible = { cx, cy, rayon: Math.max(60, rayon) };
    this.hautLibre = hautLibre; // les étiquettes ne doivent pas passer sous l'en-tête
  }

  /** Active ou désactive le mode léger (moins de points, animations réduites). */
  definirLeger(leger) {
    if (leger === this.leger) return;
    this.leger = leger;
    this.#creerPoints();
    this.pointsFlux.visible = !leger;
    this.redimensionner();
  }

  /** Met en pause le rendu (écran portefeuille ouvert, appli en arrière-plan…). */
  definirActif(actif) {
    this.actif = actif;
    this.calque.style.visibility = actif ? '' : 'hidden';
  }

  redimensionner() {
    this.largeur = innerWidth;
    this.hauteur = innerHeight;
    // Densité de pixels limitée : le mode léger épargne le processeur graphique
    this.rendu.setPixelRatio(Math.min(devicePixelRatio || 1, this.leger ? 1.25 : 2));
    this.rendu.setSize(this.largeur, this.hauteur, false);
    this.camera.aspect = this.largeur / this.hauteur;
    this.#appliquerCadrage();
  }

  /* ============================ Boucle d'animation ============================ */

  #boucle(maintenant) {
    requestAnimationFrame(this.boucle);
    if (!this.actif || document.hidden) { this.horloge.getDelta(); return; }
    // En mode léger, on se limite à environ 30 images par seconde
    if (this.leger && maintenant - this.dernierRendu < 32) return;
    this.dernierRendu = maintenant;

    const dt = Math.min(this.horloge.getDelta(), 0.1);
    const temps = (maintenant - this.debut) / 1000;
    this.#majRotation(dt, maintenant);
    this.#majCadrage(dt);
    this.#majPays(temps);
    if (!this.leger) this.#placerPointsFlux(temps);

    this.groupe.rotation.set(this.tangage, this.lacet, 0);
    this.groupe.updateMatrixWorld();
    this.#majEtiquettes();
    this.rendu.render(this.scene, this.camera);
  }

  #majRotation(dt, maintenant) {
    if (this.glisse) return;
    if (this.cible) {
      // Pivot en douceur vers le pays choisi, par le chemin le plus court
      const ecart = THREE.MathUtils.euclideanModulo(this.cible.lacet - this.lacet + Math.PI, Math.PI * 2) - Math.PI;
      const f = 1 - Math.exp(-dt * 4.5);
      this.lacet += ecart * f;
      this.tangage += (this.cible.tangage - this.tangage) * f;
      return;
    }
    // Inertie : la vitesse décroît progressivement
    this.lacet += this.vitesseLacet * dt;
    this.tangage = THREE.MathUtils.clamp(this.tangage + this.vitesseTangage * dt, -INCLINAISON_MAX, INCLINAISON_MAX);
    const amorti = Math.exp(-dt * AMORTISSEMENT);
    this.vitesseLacet *= amorti;
    this.vitesseTangage *= amorti;

    // Rotation automatique au repos (sauf si un pays est sélectionné)
    if (!this.selection && maintenant - this.dernierContact > DELAI_REPOS) {
      this.lacet += ROTATION_AUTO * dt;
      this.tangage += (INCLINAISON_REPOS - this.tangage) * (1 - Math.exp(-dt * 0.6));
    }
  }

  #majCadrage(dt) {
    const f = 1 - Math.exp(-dt * 5);
    const c = this.cadrage, cc = this.cadrageCible;
    const ecart = Math.abs(cc.cx - c.cx) + Math.abs(cc.cy - c.cy) + Math.abs(cc.rayon - c.rayon);
    if (ecart < 0.3) return;
    c.cx += (cc.cx - c.cx) * f;
    c.cy += (cc.cy - c.cy) * f;
    c.rayon += (cc.rayon - c.rayon) * f;
    this.#appliquerCadrage();
  }

  /**
   * Place la caméra pour que le globe (rayon 1) apparaisse avec le rayon voulu,
   * puis décale l'image pour centrer le globe dans la zone libre de l'écran.
   */
  #appliquerCadrage() {
    const { cx, cy, rayon } = this.cadrage;
    const demiFov = THREE.MathUtils.degToRad(this.camera.fov / 2);
    const q = (rayon * Math.tan(demiFov)) / (this.hauteur / 2);
    this.camera.position.z = Math.sqrt(1 + 1 / (q * q));
    this.camera.setViewOffset(this.largeur, this.hauteur, this.largeur / 2 - cx, this.hauteur / 2 - cy, this.largeur, this.hauteur);
    this.camera.updateProjectionMatrix();
  }

  #majPays(temps) {
    const intro = Math.min(1, temps / 1.4); // les colonnes « poussent » au démarrage
    const croissance = 1 - Math.pow(1 - intro, 3);
    for (const o of this.objetsPays) {
      const choisi = o.code === this.selection;
      const attenue = this.selection && !choisi;
      o.colonne.scale.set(choisi ? 1.6 : 1, Math.max(0.001, croissance), choisi ? 1.6 : 1);
      o.colonne.material.opacity = attenue ? 0.35 : 0.9;
      o.sommet.material.opacity = attenue ? 0.35 : 1;
      o.sommet.position.copy(o.normale).multiplyScalar(1 + o.hauteur * croissance);
      if (this.leger) {
        o.anneau.scale.setScalar(choisi ? 1.6 : 1);
        o.anneau.material.opacity = attenue ? 0.25 : 0.7;
      } else {
        // Pulsation : l'anneau grandit en s'estompant, puis recommence
        const cycle = (temps * (choisi ? 1 : 0.55) + o.phase) % 1;
        o.anneau.scale.setScalar(1 + cycle * (choisi ? 2.6 : 1.8));
        o.anneau.material.opacity = (1 - cycle) * (attenue ? 0.35 : 0.9);
      }
    }
  }

  /** Positionne les étiquettes HTML au-dessus des colonnes visibles. */
  #majEtiquettes() {
    const v = new THREE.Vector3();
    const normaleMonde = new THREE.Vector3();
    const versCamera = new THREE.Vector3();
    const visibles = [];
    for (const o of this.objetsPays) {
      v.copy(o.haut).applyMatrix4(this.groupe.matrixWorld);
      normaleMonde.copy(o.normale).applyQuaternion(this.groupe.quaternion);
      versCamera.copy(this.camera.position).sub(v).normalize();
      o.face = normaleMonde.dot(versCamera);
      const visible = o.face > 0.18; // face visible du globe uniquement
      if (visible !== o.visible) {
        o.visible = visible;
        o.etiquette.classList.toggle('est-cachee', !visible);
      }
      o.etiquette.classList.toggle('est-active', o.code === this.selection);
      if (!visible) continue;
      visibles.push(o);
      v.project(this.camera);
      const x = ((v.x + 1) / 2) * this.largeur;
      const y = ((1 - v.y) / 2) * this.hauteur;
      if (Math.abs(x - o.x) > 0.3 || Math.abs(y - o.y) > 0.3) {
        o.x = x; o.y = y;
        o.etiquette.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translate(-50%, -100%)`;
      }
    }
    this.#eviterChevauchements(visibles);
  }

  /**
   * Quand deux étiquettes se chevauchent (pays proches, comme en Europe),
   * on n'affiche que la plus prioritaire : le pays sélectionné, puis celui
   * le plus en face de la caméra. Les autres restent touchables sur le globe.
   */
  #eviterChevauchements(visibles) {
    visibles.sort((a, b) => (b.code === this.selection) - (a.code === this.selection) || b.face - a.face);
    const placees = [];
    for (const o of visibles) {
      o.largeurEtiquette ||= o.etiquette.offsetWidth || 90;
      const r = { g: o.x - o.largeurEtiquette / 2, d: o.x + o.largeurEtiquette / 2, h: o.y - 24, b: o.y };
      const chevauche = r.h < (this.hautLibre ?? 0) || placees.some((p) => r.g < p.d + 2 && r.d > p.g - 2 && r.h < p.b + 2 && r.b > p.h - 2);
      if (!chevauche) placees.push(r);
      if (chevauche !== Boolean(o.masquee)) {
        o.masquee = chevauche;
        o.etiquette.classList.toggle('est-masquee', chevauche);
      }
    }
  }
}
