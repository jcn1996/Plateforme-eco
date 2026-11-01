/* ==========================================================================
   Globe 3D (Three.js)
   --------------------------------------------------------------------------
   Couches, de bas en haut :
   1. La Terre : texture NASA (Blue Marble + lumières de la Black Marble),
      2048 px, ou 1024 px en mode léger (assets/terre-*.jpg)
   2. Le « voile » : teintes translucides des pays suivis (émeraude, ambre,
      corail) + légère lueur des frontières, dessinés sur un canvas.
      Deux canvas alternent pour passer d'une coloration à l'autre en fondu.
   3. Les frontières : fines lignes jaune clair (géométrie 3D, nettes à tous
      les zooms), plus marquées autour du pays sélectionné
   4. Colonnes, anneaux et étiquettes des pays ; arcs des flux de capitaux
   5. Liseré et halo atmosphérique

   Gestes : rotation avec inertie, rotation automatique au repos, pincement,
   molette, double-tap ; toucher un pays ouvre sa fiche, toucher un arc
   affiche le détail du flux.
   ========================================================================== */

// Three.js r160, version fixée, servie par le CDN cdnjs.
import * as THREE from 'https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.module.min.js';
import { COULEURS, niveauNote, el, nombre } from './outils.js';

/* ---------------------------------------------------------------------------
   Lecture du fichier TopoJSON (format compact des frontières)
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
  return { pays, arcs };
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

/* Teintes translucides des pays (tons naturels) et frontières */
const TEINTES = {
  attractif: [16, 185, 129],   // vert émeraude
  neutre: [245, 166, 35],      // ambre
  defavorable: [255, 107, 91], // rouge corail
};
const FRONTIERE = 0xffe9a8;    // jaune clair
const LUEUR_FRONTIERE = 'rgba(255, 233, 168, 0.13)';

/** Opacité de la teinte : 30 à 40 % environ, plus soutenue pour les notes extrêmes. */
function opaciteTeinte(note) {
  const niveau = niveauNote(note);
  if (niveau === 'attractif') return 0.3 + Math.min(1, (note - 65) / 30) * 0.12;
  if (niveau === 'defavorable') return 0.3 + Math.min(1, (50 - note) / 30) * 0.12;
  return 0.32;
}

/* Couleurs des flux selon leur sens */
const COULEURS_FLUX = {
  entree: 0x34e3a4,  // entrées vers un pays bien noté
  sortie: 0xff6b5b,  // sorties d'un pays mal noté
  autre: 0x7fe8ff,   // autres flux
};

/* Réglages généraux */
const ROTATION_AUTO = 0.08;     // vitesse de rotation au repos (radians/seconde)
const DELAI_REPOS = 2500;       // délai avant reprise de la rotation automatique (ms)
const AMORTISSEMENT = 2.6;      // plus la valeur est grande, plus l'inertie s'arrête vite
const INCLINAISON_MAX = 1.15;   // limite d'inclinaison nord/sud (radians)
const INCLINAISON_REPOS = 0.3;  // inclinaison par défaut
const ZOOM_MIN = 0.8;
const ZOOM_MAX = 4.5;
const DELAI_DOUBLE_TAP = 280;   // ms
const DUREE_FONDU = 0.6;        // secondes, changement de coloration
const SEUILS_ETIQUETTES = [1, 1.45, 2.1]; // grands pays, moyens, petits
const AIRE_GRAND = 120, AIRE_MOYEN = 25;

export class Globe {
  /**
   * @param {HTMLCanvasElement} toile  le canvas où dessiner
   * @param {HTMLElement} calqueEtiquettes  le conteneur des étiquettes HTML
   * @param {object} options
   *   pays, frontieres, leger, afficherFlux,
   *   metrique : { cle, lire(pays) → { note, texte } }  (ce que représentent les couleurs)
   *   surSelection(code) : appelé quand on touche un pays
   *   formaterFlux(flux) : texte de la bulle d'un arc
   */
  constructor(toile, calqueEtiquettes, options) {
    const { pays, frontieres, leger = false, afficherFlux = true, metrique, surSelection = () => {}, formaterFlux } = options;
    this.toile = toile;
    this.calque = calqueEtiquettes;
    this.pays = pays;
    this.parCode = new Map(pays.map((p) => [p.code, p]));
    this.surSelection = surSelection;
    this.formaterFlux = formaterFlux ?? ((f) => `${f.de.nom} → ${f.vers.nom}`);
    this.leger = leger;
    this.afficherFlux = afficherFlux;
    this.metrique = metrique ?? { cle: 'note', lire: (p) => ({ note: p.note, texte: nombre(p.note) }) };
    this.actif = true;
    this.selection = null;

    // Frontières : décodage puis association avec les pays suivis (code ISO numérique)
    const topo = frontieres ? decoderTopoJSON(frontieres) : { pays: new Map(), arcs: [] };
    this.formes = topo.pays;
    this.arcsFrontieres = topo.arcs;
    this.formeDuPays = new Map(pays.map((p) => [p.code, this.formes.get(p.iso_num)]));

    // Rotation (lacet = gauche/droite, tangage = haut/bas) et zoom
    this.lacet = -THREE.MathUtils.degToRad(15);
    this.tangage = INCLINAISON_REPOS;
    this.vitesseLacet = 0;
    this.vitesseTangage = 0;
    this.cible = null;
    this.dernierContact = -Infinity;
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
    this.texturePoint = texturePoint();

    this.#creerTerre();
    this.#creerVoile();
    this.#creerFrontieres();
    this.#creerHalo();
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

  /** Sphère terrestre avec la texture NASA (chargée en arrière-plan). */
  #creerTerre() {
    this.materiauTerre = new THREE.MeshBasicMaterial({ color: 0x0a1a38 });
    this.terre = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), this.materiauTerre);
    this.groupe.add(this.terre);
    this.#chargerTextureTerre();

    // Liseré lumineux sur le bord du globe (effet « écran de contrôle »)
    this.lisere = new THREE.Mesh(new THREE.SphereGeometry(1.004, 64, 48), new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormale;
        void main() {
          vNormale = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        varying vec3 vNormale;
        void main() {
          float i = pow(1.0 - max(0.0, dot(vNormale, vec3(0.0, 0.0, 1.0))), 3.0) * 0.5;
          gl_FragColor = vec4(vec3(0.0, 0.8, 1.0) * i, i);
        }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.lisere.visible = !this.leger;
    this.scene.add(this.lisere); // ne tourne pas : il suit le bord vu par la caméra
  }

  #chargerTextureTerre() {
    const fichier = this.leger ? 'assets/terre-1024.jpg' : 'assets/terre-2048.jpg';
    new THREE.TextureLoader().load(fichier, (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      // La sphère de Three.js commence sa texture à -90° de longitude dans notre convention :
      // décalage d'un quart de tour pour aligner la carte sur les positions des pays.
      texture.wrapS = THREE.RepeatWrapping;
      texture.offset.x = 0.25;
      texture.anisotropy = Math.min(this.leger ? 1 : 4, this.rendu.capabilities.getMaxAnisotropy());
      this.materiauTerre.map?.dispose();
      this.materiauTerre.map = texture;
      this.materiauTerre.color.set(0xffffff);
      this.materiauTerre.needsUpdate = true;
    });
  }

  /**
   * Voile des teintes : sphère juste au-dessus de la Terre, dont la texture
   * mélange deux canvas (A et B) pour les transitions en fondu.
   */
  #creerVoile() {
    const creerCanvas = () => {
      const L = this.leger ? 1024 : 2048;
      const toile = document.createElement('canvas');
      toile.width = L; toile.height = L / 2;
      const texture = new THREE.CanvasTexture(toile);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      return { toile, texture };
    };
    this.calques = [creerCanvas(), creerCanvas()];
    this.calqueActif = 0;
    this.fondu = null; // { de, vers, t }
    this.materiauVoile = new THREE.ShaderMaterial({
      uniforms: {
        texA: { value: this.calques[0].texture },
        texB: { value: this.calques[1].texture },
        melange: { value: 0 },
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = vec2(uv.x + 0.25, uv.y); // même décalage que la texture de la Terre
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        uniform sampler2D texA;
        uniform sampler2D texB;
        uniform float melange;
        varying vec2 vUv;
        void main() {
          gl_FragColor = mix(texture2D(texA, vUv), texture2D(texB, vUv), melange);
          #include <colorspace_fragment>
        }`,
      transparent: true, depthWrite: false,
    });
    this.voile = new THREE.Mesh(new THREE.SphereGeometry(1.001, 96, 64), this.materiauVoile);
    this.groupe.add(this.voile);
    this.#dessinerVoile(this.calques[0]);
    this.calques[0].texture.needsUpdate = true;
  }

  /** Dessine teintes, lueur des frontières et mise en évidence du pays sélectionné. */
  #dessinerVoile({ toile }) {
    const L = toile.width, H = toile.height;
    const ctx = toile.getContext('2d');
    const px = (lon) => ((lon + 180) / 360) * L;
    const py = (lat) => ((90 - lat) / 180) * H;
    const echelle = L / 2048;
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
    ctx.clearRect(0, 0, L, H);
    ctx.lineJoin = 'round';

    // 1) Légère lueur jaune sous toutes les frontières
    ctx.strokeStyle = LUEUR_FRONTIERE;
    ctx.lineWidth = 4 * echelle;
    for (const forme of this.formes.values()) { tracer(forme); ctx.stroke(); }

    // 2) Teintes translucides des pays suivis (selon la métrique choisie)
    for (const p of this.pays) {
      const m = this.metrique.lire(p);
      if (!m) continue;
      const [r, v, b] = TEINTES[niveauNote(m.note)];
      const choisi = p.code === this.selection;
      const alpha = opaciteTeinte(m.note) + (choisi ? 0.22 : 0);
      const forme = this.formeDuPays.get(p.code);
      if (forme) {
        tracer(forme);
        ctx.fillStyle = `rgba(${r}, ${v}, ${b}, ${alpha.toFixed(3)})`;
        ctx.fill('evenodd');
        if (choisi) {
          // Le pays sélectionné « s'illumine » : halo coloré + contour jaune plus large
          ctx.strokeStyle = `rgba(${r}, ${v}, ${b}, 0.55)`;
          ctx.lineWidth = 10 * echelle;
          ctx.stroke();
          ctx.strokeStyle = 'rgba(255, 233, 168, 0.55)';
          ctx.lineWidth = 3.5 * echelle;
          ctx.stroke();
        }
      } else {
        // Pays trop petit pour l'échelle 1:110m (Singapour…) : disque teinté
        ctx.beginPath();
        ctx.arc(px(p.lon), py(p.lat), 5 * echelle, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r}, ${v}, ${b}, ${Math.min(0.9, alpha + 0.3).toFixed(3)})`;
        ctx.fill();
      }
    }
  }

  /**
   * Redessine le voile dans le canvas inactif puis lance un fondu.
   * En mode léger, le changement est immédiat (un seul dessin, pas de fondu).
   */
  #actualiserVoile(duree = DUREE_FONDU) {
    if (this.fondu) this.#terminerFondu();
    const cible = this.leger ? this.calqueActif : 1 - this.calqueActif;
    this.#dessinerVoile(this.calques[cible]);
    this.calques[cible].texture.needsUpdate = true;
    if (cible === this.calqueActif || duree === 0) {
      this.calqueActif = cible;
      this.materiauVoile.uniforms.melange.value = cible;
      return;
    }
    this.fondu = { vers: cible, t: 0, duree };
  }

  #terminerFondu() {
    this.calqueActif = this.fondu.vers;
    this.materiauVoile.uniforms.melange.value = this.fondu.vers;
    this.fondu = null;
  }

  /** Frontières : chaque arc TopoJSON est tracé une seule fois (frontières partagées). */
  #creerFrontieres() {
    const positions = [];
    const r = 1.0015;
    for (const arc of this.arcsFrontieres) {
      for (let i = 1; i < arc.length; i++) {
        const [lon1, lat1] = arc[i - 1], [lon2, lat2] = arc[i];
        if (Math.abs(lon2 - lon1) > 180) continue; // passage de la ligne de changement de date
        const a = versVecteur(lat1, lon1, r), b = versVecteur(lat2, lon2, r);
        positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    this.frontieres = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
      color: FRONTIERE, transparent: true, opacity: 0.5, depthWrite: false,
    }));
    this.groupe.add(this.frontieres);
    this.contourSelection = null; // contour renforcé du pays sélectionné
  }

  /** Contour jaune plus marqué autour du pays sélectionné. */
  #majContourSelection() {
    if (this.contourSelection) {
      this.groupe.remove(this.contourSelection);
      this.contourSelection.geometry.dispose();
      this.contourSelection = null;
    }
    const forme = this.selection && this.formeDuPays.get(this.selection);
    if (!forme) return;
    const positions = [];
    for (const anneau of forme.anneaux) {
      for (let i = 1; i < anneau.length; i++) {
        const [lon1, lat1] = anneau[i - 1], [lon2, lat2] = anneau[i];
        if (Math.abs(lon2 - lon1) > 180) continue;
        const a = versVecteur(lat1, lon1, 1.002), b = versVecteur(lat2, lon2, 1.002);
        positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    this.contourSelection = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
      color: 0xfff4d1, transparent: true, opacity: 1, depthWrite: false,
    }));
    this.groupe.add(this.contourSelection);
  }

  /** Halo atmosphérique cyan autour du globe. */
  #creerHalo() {
    const mat = new THREE.ShaderMaterial({
      uniforms: { couleur: { value: new THREE.Color(0x00b4ff) } },
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
          float intensite = pow(d, 2.2) * 1.0;
          gl_FragColor = vec4(couleur * intensite, intensite);
        }`,
      side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    this.halo = new THREE.Mesh(new THREE.SphereGeometry(1.2, 64, 48), mat);
    this.halo.visible = !this.leger;
    this.scene.add(this.halo);
  }

  /** Fines colonnes, anneaux et étiquettes des pays suivis. */
  #creerPays() {
    this.objetsPays = [];
    const haut = new THREE.Vector3(0, 1, 0);
    const avant = new THREE.Vector3(0, 0, 1);
    this.calque.replaceChildren();
    // Géométrie commune de hauteur 1, mise à l'échelle selon la note
    const geoColonne = new THREE.CylinderGeometry(0.004, 0.006, 1, 8, 1, true);
    geoColonne.translate(0, 0.5, 0);
    const geoAnneau = new THREE.RingGeometry(0.014, 0.019, 40);

    this.pays.forEach((p, index) => {
      const normale = versVecteur(p.lat, p.lon).normalize();
      const couleur = new THREE.Color(COULEURS[niveauNote(p.note)]);

      const colonne = new THREE.Mesh(geoColonne, new THREE.MeshBasicMaterial({
        color: couleur.clone(), transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      colonne.position.copy(normale);
      colonne.quaternion.setFromUnitVectors(haut, normale);

      const sommet = new THREE.Sprite(new THREE.SpriteMaterial({
        map: this.texturePoint, color: couleur.clone(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      sommet.scale.setScalar(0.04);

      const anneau = new THREE.Mesh(geoAnneau, new THREE.MeshBasicMaterial({
        color: couleur.clone(), transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      anneau.position.copy(normale).multiplyScalar(1.004);
      anneau.quaternion.setFromUnitVectors(avant, normale);

      this.groupe.add(colonne, sommet, anneau);

      // Étiquette HTML : nom + valeur de la métrique choisie (un vrai bouton)
      const valeur = el('span', { class: 'mono' });
      const etiquette = el('button', {
        class: 'etiquette est-cachee', type: 'button',
        onclick: () => this.surSelection(p.code),
      }, p.nom, ' ', valeur);
      this.calque.append(etiquette);

      const aire = this.formeDuPays.get(p.code)?.aire ?? 0;
      const rang = aire > AIRE_GRAND ? 0 : aire > AIRE_MOYEN ? 1 : 2;

      this.objetsPays.push({
        code: p.code, normale, colonne, sommet, anneau, etiquette, valeur,
        couleurCible: couleur.clone(),
        hauteur: 0, hauteurCible: 0,
        zoomEtiquette: SEUILS_ETIQUETTES[rang],
        phase: index * 0.137,
        haut: normale.clone(),
        visible: false, x: 0, y: 0,
      });
    });
    this.#appliquerMetriqueAuxPays(true);
  }

  /** Met à jour couleurs cibles, hauteurs cibles et textes des étiquettes selon la métrique. */
  #appliquerMetriqueAuxPays(immediat = false) {
    for (const o of this.objetsPays) {
      const p = this.parCode.get(o.code);
      const m = this.metrique.lire(p) ?? { note: 50, texte: '–' };
      const niveau = niveauNote(m.note);
      o.couleurCible.set(COULEURS[niveau]);
      o.hauteurCible = 0.02 + (m.note / 100) * 0.1;
      o.valeur.textContent = m.texte;
      o.etiquette.className = `etiquette note--${niveau}${o.visible ? '' : ' est-cachee'}${o.masquee ? ' est-masquee' : ''}${o.code === this.selection ? ' est-active' : ''}`;
      o.etiquette.setAttribute('aria-label', `${p.nom}, ${m.texte}`);
      o.largeurEtiquette = 0; // à remesurer (le texte a changé)
      if (immediat) {
        o.colonne.material.color.copy(o.couleurCible);
        o.sommet.material.color.copy(o.couleurCible);
        o.anneau.material.color.copy(o.couleurCible);
      }
    }
  }

  /** Arcs de flux de capitaux : épaisseur, vitesse et couleur selon montant et sens. */
  #creerFlux() {
    this.groupeFlux = new THREE.Group();
    this.groupe.add(this.groupeFlux);
    this.arcs = [];

    for (const p of this.pays) {
      for (const f of p.flux ?? []) {
        const cible = this.parCode.get(f.vers);
        if (!cible) continue;
        // Montant négatif = flux dans l'autre sens
        const [de, vers] = f.montant_md >= 0 ? [p, cible] : [cible, p];
        const montant = Math.abs(f.montant_md);
        const sens = vers.note >= 65 ? 'entree' : de.note < 50 ? 'sortie' : 'autre';
        const a = versVecteur(de.lat, de.lon, 1.003);
        const b = versVecteur(vers.lat, vers.lon, 1.003);
        const altitude = 0.08 + a.angleTo(b) * 0.24; // les arcs longs montent plus haut
        const milieu = a.clone().add(b).normalize().multiplyScalar(1 + altitude);
        const courbe = new THREE.QuadraticBezierCurve3(a, milieu, b);
        const t = Math.min(montant, 20) / 20;

        // Tube visible (épaisseur selon le montant)
        const tube = new THREE.Mesh(
          new THREE.TubeGeometry(courbe, 48, 0.0015 + t * 0.005, 5, false),
          new THREE.MeshBasicMaterial({ color: COULEURS_FLUX[sens], transparent: true, opacity: 0.5, depthWrite: false, blending: THREE.AdditiveBlending }),
        );
        // Tube invisible plus large pour faciliter le toucher
        const zoneToucher = new THREE.Mesh(new THREE.TubeGeometry(courbe, 24, 0.035, 4, false), new THREE.MeshBasicMaterial());
        zoneToucher.visible = false;
        this.groupeFlux.add(tube, zoneToucher);

        const arc = {
          de, vers, montant, devise: f.devise ?? 'USD', periode: f.periode ?? '1 mois', sens,
          courbe, tube, zoneToucher,
          vitesse: 0.08 + t * 0.22,
          nbPoints: 1 + Math.round(t * 3),
          couleur: new THREE.Color(COULEURS_FLUX[sens]),
        };
        zoneToucher.userData.arc = arc;
        this.arcs.push(arc);
      }
    }

    // Points lumineux qui circulent : une seule géométrie, couleurs par sommet
    const total = this.arcs.reduce((s, a) => s + a.nbPoints, 0);
    this.positionsFlux = new Float32Array(total * 3);
    const couleurs = new Float32Array(total * 3);
    let k = 0;
    for (const arc of this.arcs) for (let i = 0; i < arc.nbPoints; i++) { couleurs.set([arc.couleur.r, arc.couleur.g, arc.couleur.b], k); k += 3; }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.positionsFlux, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(couleurs, 3));
    this.pointsFlux = new THREE.Points(geo, new THREE.PointsMaterial({
      size: 0.04, map: this.texturePoint, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.pointsFlux.frustumCulled = false;
    this.pointsFlux.visible = !this.leger;
    this.groupeFlux.add(this.pointsFlux);
    this.#majVisibiliteFlux();
    this.#placerPointsFlux(0);
  }

  /** Quand un pays est sélectionné, seuls ses flux restent visibles. */
  #majVisibiliteFlux() {
    this.groupeFlux.visible = this.afficherFlux;
    for (const arc of this.arcs) {
      arc.visible = !this.selection || arc.de.code === this.selection || arc.vers.code === this.selection;
      arc.tube.visible = arc.visible;
    }
    if (!this.afficherFlux) this.#masquerBulleFlux();
  }

  #placerPointsFlux(temps) {
    const v = new THREE.Vector3();
    let k = 0;
    for (const arc of this.arcs) {
      for (let i = 0; i < arc.nbPoints; i++) {
        if (arc.visible) arc.courbe.getPoint((temps * arc.vitesse + i / arc.nbPoints) % 1, v);
        else v.set(0, 0, 0); // caché au centre de la Terre
        this.positionsFlux[k++] = v.x;
        this.positionsFlux[k++] = v.y;
        this.positionsFlux[k++] = v.z;
      }
    }
    this.pointsFlux.geometry.attributes.position.needsUpdate = true;
  }

  /** Bulle d'information d'un flux, affichée à l'endroit touché. */
  #afficherBulleFlux(arc, x, y) {
    this.#masquerBulleFlux();
    this.bulleFlux = el('div', { class: `bulle-flux bulle-flux--${arc.sens}`, role: 'status' }, this.formaterFlux(arc));
    this.calque.append(this.bulleFlux);
    const largeur = this.bulleFlux.offsetWidth;
    const gauche = Math.min(Math.max(8, x - largeur / 2), this.largeur - largeur - 8);
    this.bulleFlux.style.transform = `translate(${gauche}px, ${Math.max(this.hautLibre + 4, y - 56)}px)`;
    clearTimeout(this.minuterieBulle);
    this.minuterieBulle = setTimeout(() => this.#masquerBulleFlux(), 4500);
  }

  #masquerBulleFlux() {
    this.bulleFlux?.remove();
    this.bulleFlux = null;
  }

  /* ============================ Gestes tactiles ============================ */

  #brancherGestes() {
    const pointeurs = new Map();
    let depart = null;
    let precedent = null;
    let pincement = null;
    let dernierTap = null;
    let tapEnAttente = null;

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
      const k = 1 / Math.max(80, this.cadrage.rayon * this.zoom);
      const dLacet = (e.clientX - precedent.x) * k;
      const dTangage = (e.clientY - precedent.y) * k;
      this.lacet += dLacet;
      this.tangage = THREE.MathUtils.clamp(this.tangage + dTangage, -INCLINAISON_MAX, INCLINAISON_MAX);
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
        depart = null;
        this.glisse = false;
        return;
      }
      if (!depart) return;
      this.glisse = false;
      const distance = Math.hypot(e.clientX - depart.x, e.clientY - depart.y);
      if (performance.now() - precedent.t > 80) this.vitesseLacet = this.vitesseTangage = 0;

      if (e.type === 'pointerup' && distance < 10 && performance.now() - depart.t < 450) {
        this.vitesseLacet = this.vitesseTangage = 0;
        const x = e.clientX, y = e.clientY, t = performance.now();
        if (dernierTap && t - dernierTap.t < DELAI_DOUBLE_TAP && Math.hypot(x - dernierTap.x, y - dernierTap.y) < 40) {
          clearTimeout(tapEnAttente);
          dernierTap = null;
          this.#zoomerSur(x, y);
        } else {
          dernierTap = { x, y, t };
          clearTimeout(tapEnAttente);
          tapEnAttente = setTimeout(() => this.#toucher(x, y), DELAI_DOUBLE_TAP);
        }
      }
      depart = null;
    };
    this.toile.addEventListener('pointerup', relacher);
    this.toile.addEventListener('pointercancel', relacher);

    this.toile.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.dernierContact = performance.now();
      this.definirZoom(this.zoomCible * Math.exp(-e.deltaY * 0.0015));
    }, { passive: false });
    this.toile.addEventListener('dblclick', (e) => e.preventDefault());
  }

  /** Simple toucher : un arc de flux (bulle) ou un pays (fiche). */
  #toucher(x, y) {
    this.#lancerRayon(x, y);
    const impactTerre = this.raycaster.intersectObject(this.terre, false)[0];
    if (this.afficherFlux) {
      const zones = this.arcs.filter((a) => a.visible).map((a) => a.zoneToucher);
      const impactArc = this.raycaster.intersectObjects(zones, false)[0];
      // L'arc doit être devant la surface de la Terre (pas caché derrière)
      if (impactArc && (!impactTerre || impactArc.distance < impactTerre.distance + 0.01)) {
        this.#afficherBulleFlux(impactArc.object.userData.arc, x, y);
        return;
      }
    }
    this.#masquerBulleFlux();
    const code = this.#paysTouche(x, y, impactTerre);
    if (code) this.surSelection(code);
  }

  #lancerRayon(x, y) {
    const ndc = new THREE.Vector2((x / this.largeur) * 2 - 1, -(y / this.hauteur) * 2 + 1);
    this.raycaster ??= new THREE.Raycaster();
    this.raycaster.setFromCamera(ndc, this.camera);
  }

  /** Coordonnées (lat, lon) d'un point d'impact sur la Terre. */
  #latLon(impact) {
    const p = this.groupe.worldToLocal(impact.point.clone()).normalize();
    return { lat: THREE.MathUtils.radToDeg(Math.asin(p.y)), lon: THREE.MathUtils.radToDeg(Math.atan2(p.x, p.z)) };
  }

  /** Pays suivi sous le doigt : d'abord la surface du pays, sinon la colonne la plus proche. */
  #paysTouche(x, y, impactTerre) {
    if (impactTerre) {
      const point = this.#latLon(impactTerre);
      for (const p of this.pays) {
        const forme = this.formeDuPays.get(p.code);
        if (forme ? dansPays(point.lon, point.lat, forme) : Math.hypot(point.lon - p.lon, point.lat - p.lat) < 1.5) return p.code;
      }
    }
    return this.#colonneProche(x, y);
  }

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
    if (this.zoomCible >= ZOOM_MAX * 0.95) { this.definirZoom(1); return; }
    this.#lancerRayon(x, y);
    const impact = this.raycaster.intersectObject(this.terre, false)[0];
    if (impact) {
      const point = this.#latLon(impact);
      this.cible = {
        lacet: -THREE.MathUtils.degToRad(point.lon),
        tangage: THREE.MathUtils.clamp(THREE.MathUtils.degToRad(point.lat), -INCLINAISON_MAX, INCLINAISON_MAX),
        temporaire: true,
      };
    }
    this.definirZoom(this.zoomCible * 1.9);
  }

  /* ============================== API publique ============================== */

  definirZoom(valeur, immediat = false) {
    this.zoomCible = THREE.MathUtils.clamp(valeur, ZOOM_MIN, ZOOM_MAX);
    if (immediat) { this.zoom = this.zoomCible; this.#appliquerCadrage(); }
  }

  /** Change ce que représentent les couleurs (note globale, inflation…), avec un fondu. */
  definirMetrique(metrique) {
    this.metrique = metrique;
    this.#appliquerMetriqueAuxPays();
    this.#actualiserVoile();
  }

  /** Affiche ou masque les flux de capitaux. */
  definirAffichageFlux(afficher) {
    this.afficherFlux = afficher;
    this.#majVisibiliteFlux();
  }

  /** Fait pivoter le globe vers un pays et le met en évidence. */
  focaliser(code) {
    const p = this.parCode.get(code);
    if (!p) return;
    const change = code !== this.selection;
    this.selection = code;
    this.cible = {
      lacet: -THREE.MathUtils.degToRad(p.lon),
      tangage: THREE.MathUtils.clamp(THREE.MathUtils.degToRad(p.lat), -INCLINAISON_MAX, INCLINAISON_MAX),
    };
    this.vitesseLacet = this.vitesseTangage = 0;
    if (change) this.#selectionChangee();
  }

  deselectionner() {
    const change = this.selection !== null;
    this.selection = null;
    this.cible = null;
    this.dernierContact = performance.now() - DELAI_REPOS + 800;
    if (change) this.#selectionChangee();
  }

  #selectionChangee() {
    this.#masquerBulleFlux();
    this.#majContourSelection();
    this.#majVisibiliteFlux();
    this.#actualiserVoile(0.3);
  }

  definirCadrage({ cx, cy, rayon, hautLibre = 0, basLibre = innerHeight }) {
    this.cadrageCible = { cx, cy, rayon: Math.max(60, rayon) };
    this.hautLibre = hautLibre;
    this.basLibre = basLibre;
  }

  /** Mode léger : texture 1024 px, voile 1024 px sans fondu, pas de halo ni de points animés. */
  definirLeger(leger) {
    if (leger === this.leger) return;
    this.leger = leger;
    this.#chargerTextureTerre();
    // Nouveaux canvas du voile à la bonne taille
    for (const c of this.calques) c.texture.dispose();
    this.groupe.remove(this.voile);
    this.voile.geometry.dispose();
    this.#creerVoile();
    this.pointsFlux.visible = !leger;
    this.lisere.visible = !leger;
    this.halo.visible = !leger;
    this.redimensionner();
  }

  definirActif(actif) {
    this.actif = actif;
    this.calque.style.visibility = actif ? '' : 'hidden';
  }

  redimensionner() {
    this.largeur = innerWidth;
    this.hauteur = innerHeight;
    this.rendu.setPixelRatio(Math.min(devicePixelRatio || 1, this.leger ? 1 : 2));
    this.rendu.setSize(this.largeur, this.hauteur, false);
    this.camera.aspect = this.largeur / this.hauteur;
    this.#appliquerCadrage();
  }

  /* ============================ Boucle d'animation ============================ */

  #boucle(maintenant) {
    requestAnimationFrame(this.boucle);
    if (!this.actif || document.hidden) { this.horloge.getDelta(); return; }
    if (this.leger && maintenant - this.dernierRendu < 32) return; // ≈ 30 images/s en mode léger
    this.dernierRendu = maintenant;

    const dt = Math.min(this.horloge.getDelta(), 0.1);
    const temps = (maintenant - this.debut) / 1000;
    this.#majRotation(dt, maintenant);
    this.#majCadrage(dt);
    this.#majFondu(dt);
    this.#majPays(temps, dt);
    if (!this.leger && this.afficherFlux) this.#placerPointsFlux(temps);

    this.groupe.rotation.set(this.tangage, this.lacet, 0);
    this.groupe.updateMatrixWorld();
    this.#majEtiquettes();
    this.rendu.render(this.scene, this.camera);
    if (!this.premierRendu) { this.premierRendu = true; performance.mark('globe-premier-rendu'); }
  }

  #majFondu(dt) {
    if (!this.fondu) return;
    this.fondu.t = Math.min(1, this.fondu.t + dt / this.fondu.duree);
    const f = this.fondu.t * this.fondu.t * (3 - 2 * this.fondu.t); // départ et arrivée en douceur
    this.materiauVoile.uniforms.melange.value = this.fondu.vers === 1 ? f : 1 - f;
    if (this.fondu.t >= 1) this.#terminerFondu();
  }

  #majRotation(dt, maintenant) {
    if (this.glisse) return;
    if (this.cible) {
      const ecart = THREE.MathUtils.euclideanModulo(this.cible.lacet - this.lacet + Math.PI, Math.PI * 2) - Math.PI;
      const f = 1 - Math.exp(-dt * 4.5);
      this.lacet += ecart * f;
      this.tangage += (this.cible.tangage - this.tangage) * f;
      if (this.cible.temporaire && Math.abs(ecart) < 0.002 && Math.abs(this.cible.tangage - this.tangage) < 0.002) this.cible = null;
      return;
    }
    this.lacet += this.vitesseLacet * dt;
    this.tangage = THREE.MathUtils.clamp(this.tangage + this.vitesseTangage * dt, -INCLINAISON_MAX, INCLINAISON_MAX);
    const amorti = Math.exp(-dt * AMORTISSEMENT);
    this.vitesseLacet *= amorti;
    this.vitesseTangage *= amorti;
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

  #appliquerCadrage() {
    const { cx, cy } = this.cadrage;
    const rayon = this.cadrage.rayon * this.zoom;
    const demiFov = THREE.MathUtils.degToRad(this.camera.fov / 2);
    const q = (rayon * Math.tan(demiFov)) / (this.hauteur / 2);
    this.camera.position.z = Math.sqrt(1 + 1 / (q * q));
    this.camera.setViewOffset(this.largeur, this.hauteur, this.largeur / 2 - cx, this.hauteur / 2 - cy, this.largeur, this.hauteur);
    this.camera.updateProjectionMatrix();
  }

  #majPays(temps, dt) {
    const intro = Math.min(1, temps / 1.4);
    const croissance = 1 - Math.pow(1 - intro, 3);
    const lissage = 1 - Math.exp(-dt * 5); // transitions douces de couleur et de hauteur
    const echelleZoom = 1 / Math.sqrt(this.zoom);
    for (const o of this.objetsPays) {
      const choisi = o.code === this.selection;
      const attenue = this.selection && !choisi;
      o.hauteur += (o.hauteurCible - o.hauteur) * lissage;
      for (const m of [o.colonne.material, o.sommet.material, o.anneau.material]) m.color.lerp(o.couleurCible, lissage);
      const h = Math.max(0.001, o.hauteur * croissance);
      o.colonne.scale.set(choisi ? 1.6 : 1, h, choisi ? 1.6 : 1);
      o.colonne.material.opacity = attenue ? 0.35 : 0.9;
      o.sommet.material.opacity = attenue ? 0.35 : 1;
      o.sommet.position.copy(o.normale).multiplyScalar(1 + h);
      o.haut.copy(o.normale).multiplyScalar(1 + h + 0.015);
      if (this.leger) {
        o.anneau.scale.setScalar((choisi ? 1.6 : 1) * echelleZoom);
        o.anneau.material.opacity = attenue ? 0.25 : 0.7;
      } else {
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

  #eviterChevauchements(visibles) {
    visibles.sort((a, b) => (b.code === this.selection) - (a.code === this.selection) || b.face - a.face);
    const placees = [];
    const bas = this.basLibre ?? this.hauteur;
    for (const o of visibles) {
      o.largeurEtiquette ||= o.etiquette.offsetWidth || 90;
      const r = { g: o.x - o.largeurEtiquette / 2, d: o.x + o.largeurEtiquette / 2, h: o.y - 24, b: o.y };
      const chevauche = r.h < this.hautLibre || r.b > bas
        || placees.some((p) => r.g < p.d + 2 && r.d > p.g - 2 && r.h < p.b + 2 && r.b > p.h - 2);
      if (!chevauche) placees.push(r);
      if (chevauche !== Boolean(o.masquee)) {
        o.masquee = chevauche;
        o.etiquette.classList.toggle('est-masquee', chevauche);
      }
    }
  }
}
