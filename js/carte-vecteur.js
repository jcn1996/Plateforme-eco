/* ==========================================================================
   Carte vectorielle du globe (aucune image : tout est géométrie)
   --------------------------------------------------------------------------
   - Tous les pays (suivis ou non) sont des polygones 3D : chaque polygone est
     découpé le long de toutes les lignes d'une grille de 3°, chaque morceau est
     triangulé (earcut, intégré à Three.js via ShapeUtils) puis projeté
     juste au-dessus de la sphère de l'océan. Les petits triangles épousent
     la courbure de la Terre.
   - Un seul trait de frontière, jaune clair, d'épaisseur constante à l'écran
     (Line2 / LineMaterial de Three.js).
   - Deux niveaux de détail : Natural Earth 1:110m au démarrage, 1:50m quand
     on zoome de près (construit par petites étapes pour ne pas figer l'écran).
   ========================================================================== */

import * as THREE from 'three';
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js';

/* Rayons des couches (océan = 1) */
export const RAYON_PAYS = 1.0012;
export const RAYON_LIGNES = 1.0022;
const PAS_GRILLE = 3; // degrés

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
    pays.set(g.id ?? g.properties?.name, creerForme(g.id, g.properties?.name, polygones));
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
   Triangulation des pays
   --------------------------------------------------------------------------- */

/** Rend un anneau continu en longitude (pas de saut de 360° à la ligne de changement de date). */
function deroulerAnneau(anneau, reference) {
  let decalage = reference !== undefined ? Math.round((reference - anneau[0][0]) / 360) * 360 : 0;
  let precedent = anneau[0][0];
  const points = anneau.map(([lon, lat], i) => {
    if (i && Math.abs(lon - precedent) > 180) decalage += lon < precedent ? 360 : -360;
    precedent = lon;
    return new THREE.Vector2(lon + decalage, lat);
  });
  if (points.length > 1 && points[0].equals(points[points.length - 1])) points.pop(); // earcut n'attend pas le point de fermeture
  return points;
}

/**
 * Coupe un anneau par une droite verticale (axe 'x', longitude) ou horizontale
 * (axe 'y', latitude) et garde la partie inférieure ou supérieure
 * (algorithme de Sutherland-Hodgman, une seule arête de coupe).
 */
function couperAnneau(anneau, axe, valeur, garderInferieur) {
  const dedans = (p) => (garderInferieur ? p[axe] <= valeur : p[axe] >= valeur);
  const intersection = (p, q) => {
    const t = (valeur - p[axe]) / (q[axe] - p[axe]);
    return axe === 'x' ? new THREE.Vector2(valeur, p.y + (q.y - p.y) * t) : new THREE.Vector2(p.x + (q.x - p.x) * t, valeur);
  };
  const sortie = [];
  for (let i = 0; i < anneau.length; i++) {
    const p = anneau[(i + anneau.length - 1) % anneau.length], q = anneau[i];
    const pIn = dedans(p), qIn = dedans(q);
    if (qIn) {
      if (!pIn) sortie.push(intersection(p, q));
      sortie.push(q);
    } else if (pIn) {
      sortie.push(intersection(p, q));
    }
  }
  return sortie;
}

function boite2D(anneau) {
  let g = Infinity, d = -Infinity, b = Infinity, h = -Infinity;
  for (const p of anneau) { g = Math.min(g, p.x); d = Math.max(d, p.x); b = Math.min(b, p.y); h = Math.max(h, p.y); }
  return { g, d, b, h };
}

/** Ligne de la grille strictement à l'intérieur de [min, max] (la plus centrale), ou null. */
function ligneGrilleInterieure(min, max) {
  const premiere = Math.floor(min / PAS_GRILLE) + 1;
  const derniere = Math.ceil(max / PAS_GRILLE) - 1;
  if (premiere > derniere) return null;
  return Math.round((premiere + derniere) / 2) * PAS_GRILLE;
}

/**
 * Découpe un polygone (extérieur + trous) le long de TOUTES les lignes d'une
 * grille mondiale de PAS_GRILLE degrés qu'il traverse : d'abord les
 * longitudes, puis les latitudes. Règle stricte, identique pour tous les
 * morceaux et tous les pays : de part et d'autre d'une ligne de coupe, les
 * deux morceaux ont exactement les mêmes sommets. Le maillage est donc
 * étanche (aucune fissure, aucun liseré parasite), y compris entre deux pays
 * voisins. Chaque découpe ne traite que le morceau concerné (rapide).
 */
function trianguler(exterieur, trous, sortie, versPosition) {
  if (exterieur.length < 3) return;
  const { g, d, b, h } = boite2D(exterieur);
  let axe = 'x', coupe = ligneGrilleInterieure(g, d);
  if (coupe === null) { axe = 'y'; coupe = ligneGrilleInterieure(b, h); }
  if (coupe !== null) {
    for (const inferieur of [true, false]) {
      const ext = couperAnneau(exterieur, axe, coupe, inferieur);
      if (ext.length < 3) continue;
      const tr = trous.map((t) => couperAnneau(t, axe, coupe, inferieur)).filter((t) => t.length >= 3);
      trianguler(ext, tr, sortie, versPosition);
    }
    return;
  }
  const sommets = [...exterieur, ...trous.flat()];
  for (const triangle of THREE.ShapeUtils.triangulateShape(exterieur, trous)) {
    for (const k of triangle) versPosition(sommets[k], sortie);
  }
}

/** Positions des triangles d'un pays, projetées sur la sphère. */
export function trianglesPays(forme) {
  const positions = [];
  const v = new THREE.Vector3();
  const versPosition = (p, sortie) => {
    versVecteur(p.y, p.x, RAYON_PAYS, v);
    sortie.push(v.x, v.y, v.z);
  };
  for (const [exterieur, ...trous] of forme.polygones) {
    const ext = deroulerAnneau(exterieur);
    if (ext.length < 3) continue;
    trianguler(ext, trous.map((t) => deroulerAnneau(t, ext[0].x)), positions, versPosition);
  }
  return positions;
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

/** Centre (direction unitaire) et rayon approché d'un nuage de points sur la sphère. */
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
   Matériau des pays : un seul maillage pour TOUS les pays, opaque.
   Chaque sommet porte l'indice de son pays ; la couleur de chaque pays est un
   tableau de « uniforms » mis à jour à chaque image (fondu des filtres,
   sélection) sans reconstruire la géométrie. Le dernier indice sert à tous
   les pays non suivis.
   --------------------------------------------------------------------------- */
export function materiauPays(couleurs) {
  return new THREE.ShaderMaterial({
    uniforms: { couleurs: { value: couleurs } },
    defines: { NB_COULEURS: couleurs.length },
    vertexShader: `
      attribute float indice;
      uniform vec3 couleurs[NB_COULEURS];
      varying vec3 vCouleur;
      void main() {
        vCouleur = couleurs[int(indice + 0.5)];
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      varying vec3 vCouleur;
      void main() {
        gl_FragColor = vec4(vCouleur, 1.0);
        #include <colorspace_fragment>
      }`,
    // Décalage de profondeur : les pays passent toujours devant l'océan, sans scintillement
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -2,
  });
}

/* ---------------------------------------------------------------------------
   Un niveau de détail complet de la carte (110m ou 50m)
   --------------------------------------------------------------------------- */
export class NiveauCarte {
  /**
   * Construit un niveau. Le travail est découpé en petites étapes (« await »)
   * pour que l'écran reste fluide pendant la construction du 1:50m.
   * @param {object} topo  TopoJSON des pays
   * @param {Array} pays  pays suivis ({ code, iso_num, lat, lon }), dans l'ordre des indices
   * @param {object} materiaux  { pays, frontiere }
   * @param {object} options  { pasCases : découpage des frontières (degrés, 0 = aucun), etapes : true pour céder la main }
   */
  static async construire(topo, pays, materiaux, { pasCases = 0, etapes = false } = {}) {
    const niveau = new NiveauCarte();
    const { pays: formes, arcs } = decoderTopoJSON(topo);
    niveau.formes = formes;
    niveau.formeDuPays = new Map(pays.map((p) => [p.code, formes.get(p.iso_num) ?? formeCercle(p.iso_num, p.lat, p.lon)]));
    niveau.groupe = new THREE.Group();
    niveau.morceaux = [];
    const pause = () => new Promise((ok) => setTimeout(ok, 0));

    // 1) Tous les pays : un seul maillage, attribut « indice » = numéro du pays (dernier = non suivi)
    const indiceNonSuivi = pays.length;
    const indiceParIso = new Map(pays.map((p, i) => [p.iso_num, i]));
    const positions = [], indices = [];
    const ajouter = (forme, indice) => {
      const pos = trianglesPays(forme);
      for (let k = 0; k < pos.length; k++) positions.push(pos[k]);
      for (let k = 0; k < pos.length / 3; k++) indices.push(indice);
    };
    let debut = performance.now();
    for (const forme of formes.values()) {
      ajouter(forme, indiceParIso.get(forme.id) ?? indiceNonSuivi);
      if (etapes && performance.now() - debut > 12) { await pause(); debut = performance.now(); }
    }
    // Pays suivis absents de la carte (Singapour au 1:110m) : disque
    pays.forEach((p, i) => { if (!formes.has(p.iso_num)) ajouter(niveau.formeDuPays.get(p.code), i); });

    const geoPays = new THREE.BufferGeometry();
    geoPays.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geoPays.setAttribute('indice', new THREE.Float32BufferAttribute(indices, 1));
    const maillage = new THREE.Mesh(geoPays, materiaux.pays);
    maillage.renderOrder = 1;
    niveau.groupe.add(maillage);
    if (etapes) await pause();

    // 2) Frontières : un seul trait fin, chaque arc tracé une seule fois.
    //    Au 1:50m, découpe en cases : seules celles face à la caméra sont dessinées.
    const cases = pasCases ? segmentsParCase(arcs, pasCases) : [arcs];
    for (const lignes of cases) {
      const pos = segmentsLignes(lignes);
      if (!pos.length) continue;
      const trait = ligneEpaisse(pos, materiaux.frontiere, 3);
      niveau.groupe.add(trait);
      if (pasCases) niveau.morceaux.push({ objets: [trait], ...etendue(pos) });
    }
    return niveau;
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

  /** Segments du contour d'un pays (pour le trait renforcé de la sélection). */
  contourDe(code) {
    const forme = this.formeDuPays.get(code);
    return forme ? segmentsLignes(forme.anneaux, RAYON_LIGNES + 0.0003) : null;
  }

  /** Pays suivi qui contient le point (lat, lon), ou null. */
  paysEn(lat, lon) {
    for (const [code, forme] of this.formeDuPays) if (dansPays(lon, lat, forme)) return code;
    return null;
  }
}
