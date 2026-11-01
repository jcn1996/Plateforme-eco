/* ==========================================================================
   Globe 3D (Three.js)
   --------------------------------------------------------------------------
   - Carte des pays (frontières Natural Earth 1:110m, fichier local
     data/countries-110m.json) dessinée sur une texture :
       · pays suivis remplis avec la couleur de leur note (vert/orange/rouge)
       · autres pays en gris bleu foncé
       · frontières fines cyan, avec un léger halo lumineux
   - Halo atmosphérique, méridiens discrets, arcs animés de flux de capitaux
   - Pour chaque pays suivi : fine colonne (hauteur + couleur = note),
     anneau qui pulse, étiquette HTML (nom + note)
   - Gestes : rotation au doigt avec inertie, rotation automatique au repos,
     pincement / molette / double-tap pour zoomer, toucher un pays pour
     ouvrir sa fiche
   - Mode léger : texture 4 fois plus légère, pas d'animation des flux ni de
     halo, 30 images/s, densité de pixels réduite
   ========================================================================== */

// Three.js r160, version fixée, servie par le CDN cdnjs.
import * as THREE from 'https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.module.min.js';
import { COULEURS, niveauNote, el, nombre } from './outils.js';

/* ---------------------------------------------------------------------------
   Lecture du fichier TopoJSON (format compact des frontières)
   Un TopoJSON stocke des « arcs » (morceaux de frontière) partagés entre pays,
   avec des coordonnées entières codées en différences. On les reconstitue ici
   en anneaux de points [longitude, latitude].
   --------------------------------------------------------------------------- */
function decoderTopoJSON(topo, nomObjet = 'countries') {
  const { scale: [sx, sy], translate: [tx, ty] } = topo.transform;
  const arcs = topo.arcs.map((arc) => {
    let x = 0, y = 0;
    return arc.map(([dx, dy]) => { x += dx; y += dy; return [x * sx + tx, y * sy + ty]; });
  });
  const anneau = (indices) => {
    const points = [];
    for (const i of indices) {
      const arc = i >= 0 ? arcs[i] : arcs[~i].slice().reverse();
      points.push(...(points.length ? arc.slice(1) : arc)); // le 1er point répète le dernier de l'arc précédent
    }
    return points;
  };
  const pays = new Map();
  for (const g of topo.objects[nomObjet].geometries) {
    const polygones = g.type === 'Polygon' ? [g.arcs] : g.type === 'MultiPolygon' ? g.arcs : [];
    const anneaux = polygones.flatMap((poly) => poly.map(anneau));
    pays.set(g.id, { id: g.id, nom: g.properties?.name, anneaux, boite: boiteEnglobante(anneaux), aire: aireApprochee(anneaux) });
  }
  return pays;
}

function boiteEnglobante(anneaux) {
  let g = 180, d = -180, b = 90, h = -90;
  for (const a of anneaux) for (const [lon, lat] of a) {
    g = Math.min(g, lon); d = Math.max(d, lon); b = Math.min(b, lat); h = Math.max(h, lat);
  }
  return { g, d, b, h };
}

/** Surface approximative (en « degrés carrés » corrigés de la latitude), pour classer les pays par taille. */
function aireApprochee(anneaux) {
  let total = 0;
  for (const a of anneaux) {
    let s = 0, latMoy = 0;
    for (let i = 0, j = a.length - 1; i < a.length; j = i++) {
      s += (a[j][0] - a[i][0]) * (a[j][1] + a[i][1]);
      latMoy += a[i][1];
    }
    total += Math.abs(s / 2) * Math.cos(THREE.MathUtils.degToRad(latMoy / a.length));
  }
  return total;
}

/** Test « point dans polygone » (règle pair/impair, gère trous et îles). */
function dansPays(lon, lat, pays) {
  const b = pays.boite;
  if (lon < b.g || lon > b.d || lat < b.b || lat > b.h) return false;
  let dedans = false;
  for (const a of pays.anneaux) {
    for (let i = 0, j = a.length - 1; i < a.length; j = i++) {
      const [xi, yi] = a[i], [xj, yj] = a[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) dedans = !dedans;
    }
  }
  return dedans;
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

/** Petite texture ronde et floue, utilisée pour les points lumineux. */
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

/** Couleurs de la carte (texture). */
const CARTE = {
  ocean: '#030b1a',
  paysNonSuivi: '#16253f',
  frontiere: 'rgba(0, 229, 255, 0.85)',
  halo: 'rgba(0, 229, 255, 0.16)',
  remplissage: { attractif: 'rgba(46, 229, 157, 0.62)', neutre: 'rgba(255, 181, 71, 0.6)', defavorable: 'rgba(255, 77, 106, 0.6)' },
  lueur: { attractif: 'rgba(46, 229, 157, 0.5)', neutre: 'rgba(255, 181, 71, 0.45)', defavorable: 'rgba(255, 77, 106, 0.45)' },
};

/* Réglages généraux */
const ROTATION_AUTO = 0.08;     // vitesse de rotation au repos (radians/seconde)
const DELAI_REPOS = 2500;       // délai avant reprise de la rotation automatique (ms)
const AMORTISSEMENT = 2.6;      // plus la valeur est grande, plus l'inertie s'arrête vite
const INCLINAISON_MAX = 1.15;   // limite d'inclinaison nord/sud (radians)
const INCLINAISON_REPOS = 0.3;  // inclinaison par défaut (on voit un peu plus l'hémisphère nord)
const ZOOM_MIN = 0.8;
const ZOOM_MAX = 4.5;
const DELAI_DOUBLE_TAP = 280;   // ms
/* Seuils d'affichage des étiquettes selon la taille du pays */
const SEUILS_ETIQUETTES = [1, 1.45, 2.1]; // grands pays, moyens, petits
const AIRE_GRAND = 120, AIRE_MOYEN = 25;

export class Globe {
  /**
   * @param {HTMLCanvasElement} toile  le canvas où dessiner
   * @param {HTMLElement} calqueEtiquettes  le conteneur des étiquettes HTML
   * @param {object} options  { pays, frontieres, leger, surSelection(code) }
   */
  constructor(toile, calqueEtiquettes, { pays, frontieres, leger = false, surSelection = () => {} }) {
    this.toile = toile;
    this.calque = calqueEtiquettes;
    this.pays = pays;
    this.surSelection = surSelection;
    this.leger = leger;
    this.actif = true;
    this.selection = null;

    // Frontières : décodage puis association avec les pays suivis (code ISO numérique)
    this.formes = frontieres ? decoderTopoJSON(frontieres) : new Map();
    this.formeDuPays = new Map(pays.map((p) => [p.code, this.formes.get(p.iso_num)]));

    // État de la rotation (lacet = gauche/droite, tangage = haut/bas) et du zoom
    this.lacet = -THREE.MathUtils.degToRad(15);
    this.tangage = INCLINAISON_REPOS;
    this.vitesseLacet = 0;
    this.vitesseTangage = 0;
    this.cible = null;                // { lacet, tangage } quand on pivote vers un point
    this.dernierContact = -Infinity;  // horodatage du dernier geste
    this.zoom = 1;
    this.zoomCible = 1;

    // Cadrage : centre et rayon du globe à l'écran (en pixels), animés en douceur
    this.cadrage = { cx: innerWidth / 2, cy: innerHeight / 2, rayon: Math.min(innerWidth, innerHeight) * 0.42 };
    this.cadrageCible = { ...this.cadrage };
    this.hautLibre = 0;

    // Moteur de rendu (peut échouer si WebGL n'est pas disponible)
    this.rendu = new THREE.WebGLRenderer({ canvas: toile, antialias: !leger, alpha: true, powerPreference: 'low-power' });
    this.rendu.setClearColor(0x000000, 0);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(36, innerWidth / innerHeight, 0.05, 100);
    this.camera.position.set(0, 0, 4);

    this.groupe = new THREE.Group(); // tout ce qui tourne avec la Terre
    this.scene.add(this.groupe);
    this.texture = texturePoint();

    this.#creerTerre();
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

  /** Sphère terrestre texturée avec la carte des pays. */
  #creerTerre() {
    this.materiauTerre = new THREE.MeshBasicMaterial({ map: this.#textureCarte() });
    this.terre = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), this.materiauTerre);
    this.groupe.add(this.terre);

    // Liseré lumineux sur le bord du globe (effet « écran de contrôle »)
    this.lisere = new THREE.Mesh(new THREE.SphereGeometry(1.002, 64, 48), new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormale;
        void main() {
          vNormale = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        varying vec3 vNormale;
        void main() {
          float i = pow(1.0 - max(0.0, dot(vNormale, vec3(0.0, 0.0, 1.0))), 3.0) * 0.55;
          gl_FragColor = vec4(vec3(0.0, 0.85, 1.0) * i, i);
        }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.lisere.visible = !this.leger;
    this.scene.add(this.lisere); // ne tourne pas : il suit le bord vu par la caméra
  }

  /**
   * Dessine la carte sur un canvas en projection équirectangulaire
   * (longitude → x, latitude → y), puis l'utilise comme texture.
   * Mode léger : texture 2048 × 1024 au lieu de 4096 × 2048 (4 fois moins de mémoire).
   */
  #textureCarte() {
    const L = this.leger ? 2048 : 4096, H = L / 2;
    const toile = document.createElement('canvas');
    toile.width = L; toile.height = H;
    const ctx = toile.getContext('2d');
    const px = (lon) => ((lon + 180) / 360) * L;
    const py = (lat) => ((90 - lat) / 180) * H;
    const echelle = L / 4096;

    // Trace le contour d'un pays (gère un éventuel passage de la ligne de changement de date)
    const tracer = (forme) => {
      ctx.beginPath();
      for (const anneau of forme.anneaux) {
        let decalage = 0, precedent = anneau[0][0];
        anneau.forEach(([lon, lat], i) => {
          if (i && Math.abs(lon - precedent) > 180) decalage += lon < precedent ? 360 : -360;
          precedent = lon;
          const x = px(lon + decalage), y = py(lat);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.closePath();
      }
    };

    ctx.fillStyle = CARTE.ocean;
    ctx.fillRect(0, 0, L, H);
    ctx.lineJoin = 'round';

    const niveauParIso = new Map(this.pays.map((p) => [p.iso_num, niveauNote(p.note)]));

    // 1) Remplissage de tous les pays
    for (const forme of this.formes.values()) {
      const niveau = niveauParIso.get(forme.id);
      tracer(forme);
      ctx.fillStyle = niveau ? CARTE.remplissage[niveau] : CARTE.paysNonSuivi;
      ctx.fill('evenodd');
    }
    // 2) Halo large et discret sous les frontières
    ctx.strokeStyle = CARTE.halo;
    ctx.lineWidth = 5 * echelle;
    for (const forme of this.formes.values()) { tracer(forme); ctx.stroke(); }
    // 3) Lueur colorée autour des pays suivis
    for (const forme of this.formes.values()) {
      const niveau = niveauParIso.get(forme.id);
      if (!niveau) continue;
      tracer(forme);
      ctx.strokeStyle = CARTE.lueur[niveau];
      ctx.lineWidth = 7 * echelle;
      ctx.stroke();
    }
    // 4) Frontières fines cyan
    ctx.strokeStyle = CARTE.frontiere;
    ctx.lineWidth = 1.3 * echelle;
    for (const forme of this.formes.values()) { tracer(forme); ctx.stroke(); }

    // 5) Pays trop petits pour l'échelle 1:110m (Singapour…) : disque coloré
    for (const p of this.pays) {
      if (this.formeDuPays.get(p.code)) continue;
      const niveau = niveauNote(p.note);
      ctx.beginPath();
      ctx.arc(px(p.lon), py(p.lat), 9 * echelle, 0, Math.PI * 2);
      ctx.fillStyle = CARTE.remplissage[niveau];
      ctx.fill();
      ctx.strokeStyle = CARTE.frontiere;
      ctx.lineWidth = 1.3 * echelle;
      ctx.stroke();
    }

    const texture = new THREE.CanvasTexture(toile);
    texture.colorSpace = THREE.SRGBColorSpace;
    // La sphère de Three.js commence sa texture à -90° de longitude dans notre convention :
    // on décale d'un quart de tour pour aligner la carte sur les positions des pays.
    texture.wrapS = THREE.RepeatWrapping;
    texture.offset.x = 0.25;
    texture.anisotropy = Math.min(this.leger ? 1 : 8, this.rendu?.capabilities.getMaxAnisotropy() ?? 1);
    return texture;
  }

  /** Halo atmosphérique cyan autour du globe. */
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
    this.halo = new THREE.Mesh(new THREE.SphereGeometry(1.2, 64, 48), mat);
    this.halo.visible = !this.leger;
    this.scene.add(this.halo); // le halo ne tourne pas (il est symétrique)
  }

  /** Méridiens (tous les 30°) et parallèles discrets. */
  #creerGrille() {
    const mat = new THREE.LineBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.06, depthWrite: false });
    for (let lon = -180; lon < 180; lon += 30) {
      const pts = [];
      for (let lat = -90; lat <= 90; lat += 3) pts.push(versVecteur(lat, lon, 1.003));
      this.groupe.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
    }
    for (const lat of [-60, -30, 0, 30, 60]) {
      const pts = [];
      for (let lon = -180; lon <= 180; lon += 3) pts.push(versVecteur(lat, lon, 1.003));
      this.groupe.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
    }
  }

  /** Fines colonnes, anneaux et étiquettes des pays suivis. */
  #creerPays() {
    this.objetsPays = [];
    const haut = new THREE.Vector3(0, 1, 0);
    const avant = new THREE.Vector3(0, 0, 1);
    this.calque.replaceChildren();

    this.pays.forEach((p, index) => {
      const normale = versVecteur(p.lat, p.lon).normalize();
      const couleur = new THREE.Color(COULEURS[niveauNote(p.note)]);
      const hauteur = 0.02 + (p.note / 100) * 0.1; // hauteur proportionnelle à la note

      // Colonne : un fin cylindre dont la base est posée sur la surface
      const geoColonne = new THREE.CylinderGeometry(0.004, 0.006, hauteur, 8, 1, true);
      geoColonne.translate(0, hauteur / 2, 0);
      const colonne = new THREE.Mesh(geoColonne, new THREE.MeshBasicMaterial({
        color: couleur, transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      colonne.position.copy(normale);
      colonne.quaternion.setFromUnitVectors(haut, normale);

      // Point lumineux au sommet
      const sommet = new THREE.Sprite(new THREE.SpriteMaterial({
        map: this.texture, color: couleur, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      sommet.scale.setScalar(0.04);
      sommet.position.copy(normale).multiplyScalar(1 + hauteur);

      // Anneau au pied de la colonne (il pulse)
      const anneau = new THREE.Mesh(new THREE.RingGeometry(0.014, 0.019, 40), new THREE.MeshBasicMaterial({
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

      // Les étiquettes des petits pays n'apparaissent qu'en zoomant
      const aire = this.formeDuPays.get(p.code)?.aire ?? 0;
      const rang = aire > AIRE_GRAND ? 0 : aire > AIRE_MOYEN ? 1 : 2;

      this.objetsPays.push({
        code: p.code, normale, hauteur, colonne, sommet, anneau, etiquette,
        zoomEtiquette: SEUILS_ETIQUETTES[rang],
        phase: index * 0.137, // décalage pour que les anneaux ne pulsent pas tous ensemble
        haut: normale.clone().multiplyScalar(1 + hauteur + 0.015),
        visible: false, x: 0, y: 0,
      });
    });
  }

  /** Arcs de flux de capitaux + points lumineux qui circulent dessus. */
  #creerFlux() {
    const parCode = new Map(this.pays.map((p) => [p.code, p]));
    this.arcs = [];
    const matArc = new THREE.LineBasicMaterial({
      color: 0x00e5ff, transparent: true, opacity: 0.35, depthWrite: false, blending: THREE.AdditiveBlending,
    });

    for (const p of this.pays) {
      for (const f of p.flux ?? []) {
        const cible = parCode.get(f.vers);
        if (!cible) continue;
        // Montant négatif = flux dans l'autre sens
        const [de, vers] = f.montant_md >= 0 ? [p, cible] : [cible, p];
        const a = versVecteur(de.lat, de.lon, 1.003);
        const b = versVecteur(vers.lat, vers.lon, 1.003);
        const altitude = 0.08 + a.angleTo(b) * 0.24; // les arcs longs montent plus haut
        const milieu = a.clone().add(b).normalize().multiplyScalar(1 + altitude);
        const courbe = new THREE.QuadraticBezierCurve3(a, milieu, b);
        this.groupe.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(courbe.getPoints(60)), matArc));
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
      size: 0.035, map: this.texture, color: 0xa8f7ff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.pointsFlux.frustumCulled = false;
    this.pointsFlux.visible = !this.leger;
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
    const pointeurs = new Map(); // doigts posés sur l'écran : id → {x, y}
    let depart = null;           // début du geste à un doigt
    let precedent = null;
    let pincement = null;        // { distance, zoom } au début d'un pincement
    let dernierTap = null;       // pour détecter le double-tap
    let tapEnAttente = null;     // minuterie du simple tap (annulée si double-tap)

    const ecart = () => {
      const [a, b] = [...pointeurs.values()];
      return Math.hypot(a.x - b.x, a.y - b.y);
    };

    this.toile.addEventListener('pointerdown', (e) => {
      this.toile.setPointerCapture(e.pointerId);
      pointeurs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      this.dernierContact = performance.now();
      this.vitesseLacet = this.vitesseTangage = 0;
      if (pointeurs.size === 2) {
        // Deux doigts : on passe en mode pincement (zoom)
        pincement = { distance: ecart(), zoom: this.zoomCible };
        this.glisse = false;
        depart = null;
        return;
      }
      if (pointeurs.size > 2) return;
      depart = { x: e.clientX, y: e.clientY, t: performance.now() };
      precedent = { ...depart };
      this.cible = null;
      this.glisse = true;
    });

    this.toile.addEventListener('pointermove', (e) => {
      if (!pointeurs.has(e.pointerId)) return;
      pointeurs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      this.dernierContact = performance.now();
      if (pincement && pointeurs.size === 2) {
        this.definirZoom(pincement.zoom * (ecart() / pincement.distance), true);
        return;
      }
      if (!depart) return;
      const maintenant = performance.now();
      const dt = Math.max(1, maintenant - precedent.t) / 1000;
      // Un pixel de déplacement ≈ un pixel de surface : le globe « colle » au doigt
      const k = 1 / Math.max(80, this.cadrage.rayon * this.zoom);
      const dLacet = (e.clientX - precedent.x) * k;
      const dTangage = (e.clientY - precedent.y) * k;
      this.lacet += dLacet;
      this.tangage = THREE.MathUtils.clamp(this.tangage + dTangage, -INCLINAISON_MAX, INCLINAISON_MAX);
      // Vitesse lissée, réutilisée pour l'inertie au lâcher
      this.vitesseLacet = this.vitesseLacet * 0.6 + (dLacet / dt) * 0.4;
      this.vitesseTangage = this.vitesseTangage * 0.6 + (dTangage / dt) * 0.4;
      precedent = { x: e.clientX, y: e.clientY, t: maintenant };
    });

    const relacher = (e) => {
      if (!pointeurs.has(e.pointerId)) return;
      pointeurs.delete(e.pointerId);
      this.dernierContact = performance.now();
      if (pincement) {
        if (pointeurs.size < 2) pincement = null;
        depart = null; // on ignore la fin du geste pour éviter un faux « toucher »
        this.glisse = false;
        return;
      }
      if (!depart) return;
      this.glisse = false;
      const distance = Math.hypot(e.clientX - depart.x, e.clientY - depart.y);
      // Si le doigt est resté immobile juste avant le lâcher, pas d'élan
      if (performance.now() - precedent.t > 80) this.vitesseLacet = this.vitesseTangage = 0;

      // Appui bref sans déplacement = un « toucher »
      if (e.type === 'pointerup' && distance < 10 && performance.now() - depart.t < 450) {
        this.vitesseLacet = this.vitesseTangage = 0;
        const x = e.clientX, y = e.clientY, t = performance.now();
        if (dernierTap && t - dernierTap.t < DELAI_DOUBLE_TAP && Math.hypot(x - dernierTap.x, y - dernierTap.y) < 40) {
          // Double-tap : zoom sur le point touché
          clearTimeout(tapEnAttente);
          dernierTap = null;
          this.#zoomerSur(x, y);
        } else {
          // Simple tap : on attend un peu pour être sûr que ce n'est pas un double-tap
          dernierTap = { x, y, t };
          clearTimeout(tapEnAttente);
          tapEnAttente = setTimeout(() => {
            const code = this.#paysTouche(x, y);
            if (code) this.surSelection(code);
          }, DELAI_DOUBLE_TAP);
        }
      }
      depart = null;
    };
    this.toile.addEventListener('pointerup', relacher);
    this.toile.addEventListener('pointercancel', relacher);

    // Molette (ordinateur) : zoom progressif
    this.toile.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.dernierContact = performance.now();
      this.definirZoom(this.zoomCible * Math.exp(-e.deltaY * 0.0015));
    }, { passive: false });
    // Sur ordinateur, le double-clic natif est remplacé par notre double-tap
    this.toile.addEventListener('dblclick', (e) => e.preventDefault());
  }

  /** Coordonnées (lat, lon) du point du globe situé sous l'écran (x, y), ou null. */
  #pointSurGlobe(x, y) {
    const ndc = new THREE.Vector2((x / this.largeur) * 2 - 1, -(y / this.hauteur) * 2 + 1);
    this.raycaster ??= new THREE.Raycaster();
    this.raycaster.setFromCamera(ndc, this.camera);
    const impact = this.raycaster.intersectObject(this.terre, false)[0];
    if (!impact) return null;
    const p = this.groupe.worldToLocal(impact.point.clone()).normalize();
    return { lat: THREE.MathUtils.radToDeg(Math.asin(p.y)), lon: THREE.MathUtils.radToDeg(Math.atan2(p.x, p.z)) };
  }

  /** Pays suivi situé sous le doigt : d'abord la surface du pays, sinon la colonne la plus proche. */
  #paysTouche(x, y) {
    const point = this.#pointSurGlobe(x, y);
    if (point) {
      for (const p of this.pays) {
        const forme = this.formeDuPays.get(p.code);
        if (forme ? dansPays(point.lon, point.lat, forme) : Math.hypot(point.lon - p.lon, point.lat - p.lat) < 1.5) return p.code;
      }
    }
    return this.#colonneProche(x, y);
  }

  /** Colonne visible la plus proche du point touché (tolérance généreuse pour les doigts). */
  #colonneProche(x, y) {
    let meilleur = null;
    let distanceMin = 30;
    const v = new THREE.Vector3();
    for (const o of this.objetsPays) {
      if (!o.visible) continue;
      for (const point of [o.normale, o.haut]) {
        v.copy(point).applyMatrix4(this.groupe.matrixWorld).project(this.camera);
        const d = Math.hypot(((v.x + 1) / 2) * this.largeur - x, ((1 - v.y) / 2) * this.hauteur - y);
        if (d < distanceMin) { distanceMin = d; meilleur = o.code; }
      }
    }
    return meilleur;
  }

  /** Double-tap : centre le point touché et zoome (ou revient au zoom normal si déjà au maximum). */
  #zoomerSur(x, y) {
    const point = this.#pointSurGlobe(x, y);
    if (this.zoomCible >= ZOOM_MAX * 0.95) { this.definirZoom(1); return; }
    if (point) {
      this.cible = {
        lacet: -THREE.MathUtils.degToRad(point.lon),
        tangage: THREE.MathUtils.clamp(THREE.MathUtils.degToRad(point.lat), -INCLINAISON_MAX, INCLINAISON_MAX),
        temporaire: true,
      };
    }
    this.definirZoom(this.zoomCible * 1.9);
  }

  /* ============================== API publique ============================== */

  /** Change le niveau de zoom (borné). « immediat » : suit le doigt sans lissage. */
  definirZoom(valeur, immediat = false) {
    this.zoomCible = THREE.MathUtils.clamp(valeur, ZOOM_MIN, ZOOM_MAX);
    if (immediat) { this.zoom = this.zoomCible; this.#appliquerCadrage(); }
  }

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

  /** Indique où placer le globe à l'écran : centre (px), rayon (px) et limite haute des étiquettes. */
  definirCadrage({ cx, cy, rayon, hautLibre = 0 }) {
    this.cadrageCible = { cx, cy, rayon: Math.max(60, rayon) };
    this.hautLibre = hautLibre;
  }

  /** Active ou désactive le mode léger (texture réduite, animations réduites). */
  definirLeger(leger) {
    if (leger === this.leger) return;
    this.leger = leger;
    const ancienne = this.materiauTerre.map;
    this.materiauTerre.map = this.#textureCarte();
    ancienne.dispose();
    this.pointsFlux.visible = !leger;
    this.lisere.visible = !leger;
    this.halo.visible = !leger;
    this.redimensionner();
  }

  /** Met en pause le rendu (écran plein, appli en arrière-plan…). */
  definirActif(actif) {
    this.actif = actif;
    this.calque.style.visibility = actif ? '' : 'hidden';
  }

  redimensionner() {
    this.largeur = innerWidth;
    this.hauteur = innerHeight;
    // Densité de pixels limitée : le mode léger épargne le processeur graphique
    this.rendu.setPixelRatio(Math.min(devicePixelRatio || 1, this.leger ? 1 : 2));
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
    // Repère de performance : premier affichage du globe (visible dans les outils du navigateur)
    if (!this.premierRendu) { this.premierRendu = true; performance.mark('globe-premier-rendu'); }
  }

  #majRotation(dt, maintenant) {
    if (this.glisse) return;
    if (this.cible) {
      // Pivot en douceur vers la cible, par le chemin le plus court
      const ecart = THREE.MathUtils.euclideanModulo(this.cible.lacet - this.lacet + Math.PI, Math.PI * 2) - Math.PI;
      const f = 1 - Math.exp(-dt * 4.5);
      this.lacet += ecart * f;
      this.tangage += (this.cible.tangage - this.tangage) * f;
      // Une cible « temporaire » (double-tap) est abandonnée une fois atteinte
      if (this.cible.temporaire && Math.abs(ecart) < 0.002 && Math.abs(this.cible.tangage - this.tangage) < 0.002) this.cible = null;
      return;
    }
    // Inertie : la vitesse décroît progressivement
    this.lacet += this.vitesseLacet * dt;
    this.tangage = THREE.MathUtils.clamp(this.tangage + this.vitesseTangage * dt, -INCLINAISON_MAX, INCLINAISON_MAX);
    const amorti = Math.exp(-dt * AMORTISSEMENT);
    this.vitesseLacet *= amorti;
    this.vitesseTangage *= amorti;

    // Rotation automatique au repos (sauf si un pays est sélectionné ou si l'on a zoomé)
    if (!this.selection && this.zoomCible < 1.3 && maintenant - this.dernierContact > DELAI_REPOS) {
      this.lacet += ROTATION_AUTO * dt;
      this.tangage += (INCLINAISON_REPOS - this.tangage) * (1 - Math.exp(-dt * 0.6));
    }
  }

  #majCadrage(dt) {
    const f = 1 - Math.exp(-dt * 6);
    const c = this.cadrage, cc = this.cadrageCible;
    const ecart = Math.abs(cc.cx - c.cx) + Math.abs(cc.cy - c.cy) + Math.abs(cc.rayon - c.rayon) + Math.abs(this.zoomCible - this.zoom) * 100;
    if (ecart < 0.3) return;
    c.cx += (cc.cx - c.cx) * f;
    c.cy += (cc.cy - c.cy) * f;
    c.rayon += (cc.rayon - c.rayon) * f;
    this.zoom += (this.zoomCible - this.zoom) * f;
    this.#appliquerCadrage();
  }

  /**
   * Place la caméra pour que le globe (rayon 1) apparaisse avec le rayon voulu
   * (multiplié par le zoom), puis décale l'image pour centrer le globe dans la
   * zone libre de l'écran.
   */
  #appliquerCadrage() {
    const { cx, cy } = this.cadrage;
    const rayon = this.cadrage.rayon * this.zoom;
    const demiFov = THREE.MathUtils.degToRad(this.camera.fov / 2);
    const q = (rayon * Math.tan(demiFov)) / (this.hauteur / 2);
    this.camera.position.z = Math.sqrt(1 + 1 / (q * q));
    this.camera.setViewOffset(this.largeur, this.hauteur, this.largeur / 2 - cx, this.hauteur / 2 - cy, this.largeur, this.hauteur);
    this.camera.updateProjectionMatrix();
  }

  #majPays(temps) {
    const intro = Math.min(1, temps / 1.4); // les colonnes « poussent » au démarrage
    const croissance = 1 - Math.pow(1 - intro, 3);
    const echelleZoom = 1 / Math.sqrt(this.zoom); // anneaux plus discrets quand on zoome
    for (const o of this.objetsPays) {
      const choisi = o.code === this.selection;
      const attenue = this.selection && !choisi;
      o.colonne.scale.set(choisi ? 1.6 : 1, Math.max(0.001, croissance), choisi ? 1.6 : 1);
      o.colonne.material.opacity = attenue ? 0.35 : 0.9;
      o.sommet.material.opacity = attenue ? 0.35 : 1;
      o.sommet.position.copy(o.normale).multiplyScalar(1 + o.hauteur * croissance);
      if (this.leger) {
        o.anneau.scale.setScalar((choisi ? 1.6 : 1) * echelleZoom);
        o.anneau.material.opacity = attenue ? 0.25 : 0.7;
      } else {
        // Pulsation : l'anneau grandit en s'estompant, puis recommence
        const cycle = (temps * (choisi ? 1 : 0.55) + o.phase) % 1;
        o.anneau.scale.setScalar((1 + cycle * (choisi ? 2.6 : 1.8)) * echelleZoom);
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
      // Visible si sur la face avant du globe et si le zoom suffit pour ce pays
      const visible = o.face > 0.18 && (this.zoom >= o.zoomEtiquette || o.code === this.selection);
      if (visible !== o.visible) {
        o.visible = visible;
        o.etiquette.classList.toggle('est-cachee', !visible);
      }
      const active = o.code === this.selection;
      if (active !== o.active) { o.active = active; o.etiquette.classList.toggle('est-active', active); }
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
   * Quand deux étiquettes se chevauchent, on n'affiche que la plus prioritaire :
   * le pays sélectionné, puis celui le plus en face de la caméra. Les autres
   * restent touchables sur le globe. Les étiquettes sous l'en-tête sont masquées.
   */
  #eviterChevauchements(visibles) {
    visibles.sort((a, b) => (b.code === this.selection) - (a.code === this.selection) || b.face - a.face);
    const placees = [];
    for (const o of visibles) {
      o.largeurEtiquette ||= o.etiquette.offsetWidth || 90;
      const r = { g: o.x - o.largeurEtiquette / 2, d: o.x + o.largeurEtiquette / 2, h: o.y - 24, b: o.y };
      const chevauche = r.h < this.hautLibre || r.b > this.hauteur
        || placees.some((p) => r.g < p.d + 2 && r.d > p.g - 2 && r.h < p.b + 2 && r.b > p.h - 2);
      if (!chevauche) placees.push(r);
      if (chevauche !== Boolean(o.masquee)) {
        o.masquee = chevauche;
        o.etiquette.classList.toggle('est-masquee', chevauche);
      }
    }
  }
}
