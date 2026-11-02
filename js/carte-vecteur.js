/* ==========================================================================
   Carte vectorielle du globe
   --------------------------------------------------------------------------
   Tout est en géométrie 3D, donc net à tous les niveaux de zoom :
   - teintes des pays suivis : polygones découpés en cases de 3°, triangulés
     (earcut, intégré à Three.js via ShapeUtils) puis projetés juste au-dessus
     de la sphère, ce qui épouse la courbure de la Terre ;
   - frontières : lignes d'épaisseur constante à l'écran (Line2 / LineMaterial
     de Three.js), avec une lueur ;
   - contour coloré des pays suivis, contour renforcé du pays sélectionné.
   Deux niveaux de détail : Natural Earth 1:110m au démarrage, 1:50m quand on
   zoome de près (chargé à la demande).
   ========================================================================== */

import * as THREE from 'three';
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js';

/* Rayons des couches (la Terre a un rayon de 1) */
export const RAYON_TEINTES = 1.0012;
export const RAYON_LIGNES = 1.0022;

/** Latitude/longitude (degrés) → position 3D. Longitude 0 face à la caméra (+Z), nord vers +Y. */
export function versVecteur(lat, lon, rayon = 1, cible = new THREE.Vector3()) {
  const la = THREE.MathUtils.degToRad(lat);
  const lo = THREE.MathUtils.degToRad(lon);
  return cible.set(rayon * Math.cos(la) * Math.sin(lo), rayon * Math.sin(la), rayon * Math.cos(la) * Math.cos(lo));
}

/* ---------------------------------------------------------------------------
   Lecture du TopoJSON : arcs partagés, codés en différences entières
   --------------------------------------------------------------------------- */
export function decoderTopoJSON(topo, nomObjet = 'countries') {
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
    const brut = g.type === 'Polygon' ? [g.arcs] : g.type === 'MultiPolygon' ? g.arcs : [];
    const polygones = brut.map((poly) => poly.map(anneau)); // [ [extérieur, trou, trou…], … ]
    pays.set(g.id, creerForme(g.id, g.properties?.name, polygones));
  }
  return { pays, arcs };
}

function creerForme(id, nom, polygones) {
  const anneaux = polygones.flat();
  return { id, nom, polygones, anneaux, boite: boiteEnglobante(anneaux), aire: aireApprochee(anneaux) };
}

/** Pays trop petit pour la carte (Singapour au 1:110m) : petit disque. */
export function formeCercle(id, lat, lon, rayonDeg = 0.35) {
  const anneau = [];
  for (let i = 0; i <= 24; i++) {
    const a = (i / 24) * Math.PI * 2;
    anneau.push([lon + (rayonDeg * Math.cos(a)) / Math.cos(THREE.MathUtils.degToRad(lat)), lat + rayonDeg * Math.sin(a)]);
  }
  return creerForme(id, id, [[anneau]]);
}

function boiteEnglobante(anneaux) {
  let g = 180, d = -180, b = 90, h = -90;
  for (const a of anneaux) for (const [lon, lat] of a) {
    g = Math.min(g, lon); d = Math.max(d, lon); b = Math.min(b, lat); h = Math.max(h, lat);
  }
  return { g, d, b, h };
}

/** Surface approximative en « degrés carrés » corrigés de la latitude (pour classer les pays par taille). */
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

/** Test « point dans polygone » (règle pair/impair : gère trous et îles). */
export function dansPays(lon, lat, forme) {
  const b = forme.boite;
  if (lon < b.g || lon > b.d || lat < b.b || lat > b.h) return false;
  let dedans = false;
  for (const a of forme.anneaux) {
    for (let i = 0, j = a.length - 1; i < a.length; j = i++) {
      const [xi, yi] = a[i], [xj, yj] = a[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) dedans = !dedans;
    }
  }
  return dedans;
}

/* ---------------------------------------------------------------------------
   Géométries
   --------------------------------------------------------------------------- */

/** Rend un anneau continu en longitude (pas de saut de 360° à la ligne de changement de date). */
function deroulerAnneau(anneau, reference) {
  let decalage = reference !== undefined ? Math.round((reference - anneau[0][0]) / 360) * 360 : 0;
  let precedent = anneau[0][0];
  return anneau.map(([lon, lat], i) => {
    if (i && Math.abs(lon - precedent) > 180) decalage += lon < precedent ? 360 : -360;
    precedent = lon;
    return new THREE.Vector2(lon + decalage, lat);
  });
}

/**
 * Découpe un anneau par un rectangle [g, d] × [b, h] (algorithme de Sutherland-Hodgman).
 * Deux cases voisines calculent exactement les mêmes points sur leur bord commun :
 * le maillage final n'a donc ni trou ni recouvrement (pas de liseré parasite).
 */
function decouperAnneau(anneau, g, d, b, h) {
  const plans = [
    (p) => p.x >= g, (p) => p.x <= d, (p) => p.y >= b, (p) => p.y <= h,
  ];
  const coupes = [
    (p, q) => new THREE.Vector2(g, p.y + ((q.y - p.y) * (g - p.x)) / (q.x - p.x)),
    (p, q) => new THREE.Vector2(d, p.y + ((q.y - p.y) * (d - p.x)) / (q.x - p.x)),
    (p, q) => new THREE.Vector2(p.x + ((q.x - p.x) * (b - p.y)) / (q.y - p.y), b),
    (p, q) => new THREE.Vector2(p.x + ((q.x - p.x) * (h - p.y)) / (q.y - p.y), h),
  ];
  let sortie = anneau;
  for (let k = 0; k < 4 && sortie.length; k++) {
    const entree = sortie;
    sortie = [];
    for (let i = 0; i < entree.length; i++) {
      const p = entree[(i + entree.length - 1) % entree.length], q = entree[i];
      const pDedans = plans[k](p), qDedans = plans[k](q);
      if (qDedans) {
        if (!pDedans) sortie.push(coupes[k](p, q));
        sortie.push(q);
      } else if (pDedans) {
        sortie.push(coupes[k](p, q));
      }
    }
  }
  return sortie;
}

/**
 * Teinte d'un pays : chaque polygone (avec ses trous) est découpé en cases de
 * « pas » degrés, chaque case est triangulée (earcut via ShapeUtils), puis les
 * sommets sont projetés sur la sphère. Les petits triangles épousent la courbure.
 */
export function geometrieRemplissage(forme, pas = 3) {
  const positions = [];
  const v = new THREE.Vector3();
  for (const polygone of forme.polygones) {
    const [exterieur, ...trous] = polygone;
    const contour = deroulerAnneau(exterieur);
    const lonRef = contour[0].x;
    const trousV = trous.map((t) => deroulerAnneau(t, lonRef));
    for (const anneau of [contour, ...trousV]) {
      if (anneau.length > 1 && anneau[0].equals(anneau[anneau.length - 1])) anneau.pop();
    }
    if (contour.length < 3) continue;
    let g = Infinity, d = -Infinity, b = Infinity, h = -Infinity;
    for (const p of contour) { g = Math.min(g, p.x); d = Math.max(d, p.x); b = Math.min(b, p.y); h = Math.max(h, p.y); }

    for (let i = Math.floor(g / pas); i * pas < d; i++) {
      for (let j = Math.floor(b / pas); j * pas < h; j++) {
        const [cg, cd, cb, ch] = [i * pas, (i + 1) * pas, j * pas, (j + 1) * pas];
        const ext = decouperAnneau(contour, cg, cd, cb, ch);
        if (ext.length < 3) continue;
        const tr = trousV.map((t) => decouperAnneau(t, cg, cd, cb, ch)).filter((t) => t.length >= 3);
        const sommets = [...ext, ...tr.flat()];
        for (const triangle of THREE.ShapeUtils.triangulateShape(ext, tr)) {
          for (const k of triangle) {
            versVecteur(sommets[k].y, sommets[k].x, RAYON_TEINTES, v);
            positions.push(v.x, v.y, v.z);
          }
        }
      }
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  return geo;
}

/** Segments [x1,y1,z1,x2,y2,z2,…] d'une liste de polylignes [[lon, lat], …]. */
export function segmentsLignes(polylignes, rayon = RAYON_LIGNES) {
  const positions = [];
  const a = new THREE.Vector3(), b = new THREE.Vector3();
  for (const ligne of polylignes) {
    for (let i = 1; i < ligne.length; i++) {
      const [lon1, lat1] = ligne[i - 1], [lon2, lat2] = ligne[i];
      if (Math.abs(lon2 - lon1) > 180) continue; // passage de la ligne de changement de date
      versVecteur(lat1, lon1, rayon, a);
      versVecteur(lat2, lon2, rayon, b);
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
  }
  return new Float32Array(positions);
}

/** Ligne d'épaisseur constante à l'écran (en pixels, réglée par le matériau). */
export function ligneEpaisse(positions, materiau, ordre, geometrie = null) {
  let geo = geometrie;
  if (!geo) {
    geo = new LineSegmentsGeometry();
    geo.setPositions(positions);
  }
  const ligne = new LineSegments2(geo, materiau);
  ligne.renderOrder = ordre;
  return ligne;
}

/** Centre (direction unitaire) et rayon angulaire approché d'un nuage de points sur la sphère. */
function etendue(positions) {
  const centre = new THREE.Vector3();
  for (let i = 0; i < positions.length; i += 3) centre.x += positions[i], centre.y += positions[i + 1], centre.z += positions[i + 2];
  centre.normalize();
  let rayon = 0;
  const p = new THREE.Vector3();
  for (let i = 0; i < positions.length; i += 3) {
    p.set(positions[i], positions[i + 1], positions[i + 2]).normalize();
    rayon = Math.max(rayon, p.distanceTo(centre));
  }
  return { centre, rayon };
}

/** Répartit des segments par cases de « pas » degrés (selon le milieu du segment). */
function segmentsParCase(polylignes, pas) {
  const cases = new Map();
  for (const ligne of polylignes) {
    for (let i = 1; i < ligne.length; i++) {
      const [lon1, lat1] = ligne[i - 1], [lon2, lat2] = ligne[i];
      if (Math.abs(lon2 - lon1) > 180) continue;
      const cle = `${Math.floor((lon1 + lon2) / 2 / pas)}:${Math.floor((lat1 + lat2) / 2 / pas)}`;
      if (!cases.has(cle)) cases.set(cle, []);
      cases.get(cle).push([[lon1, lat1], [lon2, lat2]]);
    }
  }
  return [...cases.values()];
}

/* ---------------------------------------------------------------------------
   Matériau des teintes : un seul maillage pour tous les pays suivis.
   Chaque sommet porte l'indice de son pays ; la couleur et l'opacité de
   chaque pays sont des tableaux de « uniforms » mis à jour à chaque image
   (fondu des filtres, sélection) sans reconstruire la géométrie.
   --------------------------------------------------------------------------- */
export function materiauTeintes(couleurs, opacites) {
  return new THREE.ShaderMaterial({
    uniforms: { couleurs: { value: couleurs }, opacites: { value: opacites } },
    defines: { NB_PAYS: couleurs.length },
    vertexShader: `
      attribute float indice;
      uniform vec3 couleurs[NB_PAYS];
      uniform float opacites[NB_PAYS];
      varying vec4 vCouleur;
      void main() {
        int i = int(indice + 0.5);
        vCouleur = vec4(couleurs[i], opacites[i]);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      varying vec4 vCouleur;
      void main() {
        gl_FragColor = vCouleur;
        #include <colorspace_fragment>
      }`,
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
  });
}

/* ---------------------------------------------------------------------------
   Un niveau de détail complet de la carte (110m ou 50m)
   Peu d'objets à dessiner : 1 maillage pour toutes les teintes, 1 ligne pour
   tous les contours colorés, et les frontières découpées en cases
   géographiques (seules celles face à la caméra sont dessinées).
   --------------------------------------------------------------------------- */
export class NiveauCarte {
  /**
   * @param {object} topo  TopoJSON des pays
   * @param {Array} pays  pays suivis ({ code, iso_num, lat, lon }), dans l'ordre des indices
   * @param {object} materiaux  { lueur, frontiere, contour, teintes }
   * @param {number} pasCases  taille des cases de découpage des frontières (degrés) ; 0 = une seule case
   */
  constructor(topo, pays, materiaux, pasCases = 0) {
    const { pays: formes, arcs } = decoderTopoJSON(topo);
    this.formes = formes;
    this.formeDuPays = new Map(pays.map((p) => [p.code, formes.get(p.iso_num) ?? formeCercle(p.iso_num, p.lat, p.lon)]));
    this.groupe = new THREE.Group();
    this.morceaux = []; // { objets, centre, rayon } : frontières masquables quand elles sont derrière la Terre

    // 1) Teintes : un seul maillage, attribut « indice » = numéro du pays
    const positions = [], indices = [];
    pays.forEach((p, i) => {
      const geo = geometrieRemplissage(this.formeDuPays.get(p.code));
      const pos = geo.attributes.position.array;
      for (let k = 0; k < pos.length; k++) positions.push(pos[k]);
      for (let k = 0; k < pos.length / 3; k++) indices.push(i);
      geo.dispose();
    });
    const geoTeintes = new THREE.BufferGeometry();
    geoTeintes.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geoTeintes.setAttribute('indice', new THREE.Float32BufferAttribute(indices, 1));
    const teintes = new THREE.Mesh(geoTeintes, materiaux.teintes);
    teintes.renderOrder = 1;
    this.groupe.add(teintes);

    // 2) Contours colorés des pays suivis : une seule ligne, couleur par segment
    const segments = [];
    this.plagesContours = []; // [début, fin) en nombre de segments, par pays
    for (const p of pays) {
      const pos = segmentsLignes(this.formeDuPays.get(p.code).anneaux, RAYON_LIGNES - 0.0002);
      const debut = segments.length / 6;
      for (let k = 0; k < pos.length; k++) segments.push(pos[k]);
      this.plagesContours.push([debut, segments.length / 6]);
    }
    const geoContours = new LineSegmentsGeometry();
    geoContours.setPositions(new Float32Array(segments));
    this.couleursContours = new Float32Array(segments.length); // r,g,b de début et de fin de chaque segment
    geoContours.setColors(this.couleursContours);
    this.geoContours = geoContours;
    this.groupe.add(ligneEpaisse(null, materiaux.contour, 3, geoContours));

    // 3) Frontières de tous les pays (chaque arc une seule fois) : lueur + trait fin, même géométrie
    const cases = pasCases ? segmentsParCase(arcs, pasCases) : [arcs];
    for (const lignes of cases) {
      const pos = segmentsLignes(lignes);
      if (!pos.length) continue;
      const geo = new LineSegmentsGeometry();
      geo.setPositions(pos);
      const lueur = ligneEpaisse(null, materiaux.lueur, 2, geo);
      const trait = ligneEpaisse(null, materiaux.frontiere, 4, geo);
      this.groupe.add(lueur, trait);
      if (pasCases) this.morceaux.push({ objets: [lueur, trait], ...etendue(pos) });
    }
  }

  /** Recopie les couleurs actuelles des contours (pendant un fondu seulement). */
  majCouleursContours(couleurs) {
    const c = this.couleursContours;
    this.plagesContours.forEach(([debut, fin], i) => {
      const { r, g, b } = couleurs[i];
      for (let s = debut; s < fin; s++) {
        const k = s * 6;
        c[k] = c[k + 3] = r; c[k + 1] = c[k + 4] = g; c[k + 2] = c[k + 5] = b;
      }
    });
    this.geoContours.attributes.instanceColorStart.data.needsUpdate = true;
  }

  /**
   * Masque les cases de frontières situées à l'arrière du globe.
   * @param {THREE.Quaternion} rotation  rotation actuelle de la Terre
   * @param {THREE.Vector3} versCamera  direction (unitaire) du centre de la Terre vers la caméra
   */
  majVisibilite(rotation, versCamera) {
    const n = new THREE.Vector3();
    for (const m of this.morceaux) {
      n.copy(m.centre).applyQuaternion(rotation);
      const visible = n.dot(versCamera) > -m.rayon - 0.15;
      for (const o of m.objets) o.visible = visible;
    }
  }

  /** Segments du contour d'un pays (pour le contour renforcé de la sélection). */
  contourDe(code) {
    const forme = this.formeDuPays.get(code);
    return forme ? segmentsLignes(forme.anneaux, RAYON_LIGNES + 0.0004) : null;
  }

  /** Pays suivi qui contient le point (lat, lon), ou null. */
  paysEn(lat, lon) {
    for (const [code, forme] of this.formeDuPays) if (dansPays(lon, lat, forme)) return code;
    return null;
  }
}
