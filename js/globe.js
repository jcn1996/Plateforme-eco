/* ==========================================================================
   Globe 3D (Three.js)
   --------------------------------------------------------------------------
   Couches, de bas en haut :
   Globe 100 % vectoriel, aucune image :
   1. L'océan : sphère de couleur unie bleu nuit
   2. La carte (js/carte-vecteur.js) : tous les pays en polygones 3D opaques
      (pays suivis colorés selon leur note, autres pays gris bleu), un seul
      trait de frontière jaune clair très fin, plus épais autour du pays
      sélectionné. Natural Earth 1:110m, puis 1:50m quand on zoome de près.
   3. Colonnes, anneaux et étiquettes des pays ; pulsations des flux d'investissement
      (ETF pays) : halo vert qui s'étend (entrées nettes), halo rouge qui se contracte (sorties)
   4. Liseré et halo atmosphérique

   Gestes : rotation avec inertie, rotation automatique au repos, pincement,
   molette, double-tap ; toucher un pays ouvre sa fiche ; toucher le halo d'un
   pays qui pulse affiche une bulle (montant, % de l'encours, période, date).
   ========================================================================== */

// Three.js r160, version fixée. « three » et « three/addons/ » sont définis par
// l'import map de index.html (cdnjs pour le cœur, jsDelivr pour les lignes épaisses).
import * as THREE from 'three';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { NiveauCarte, ligneEpaisse, versVecteur, materiauPays } from './carte-vecteur.js';
import { COULEURS, niveauNote, el, nombre } from './outils.js';

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

/* Couleurs de la carte (pleines et opaques, sans dégradé) */
const OCEAN = 0x0a1a2f;      // bleu nuit
const NON_SUIVI = 0x1e3048;  // gris bleu
const TEINTES = {
  attractif: 0x1fbf7a,       // vert émeraude
  neutre: 0xf2a93b,          // ambre
  defavorable: 0xf0564a,     // rouge corail
};
/* Halos des flux d'investissement : vert émeraude (entrées), rouge corail (sorties) */
const COULEUR_ENTREES = 0x2ee59d;
const COULEUR_SORTIES = 0xff4d6a;
const HALO_MIN = 0.012, HALO_MAX = 0.03, HALO_AMPLITUDE = 0.07; // rayons (rayon de la Terre = 1)
const ANNEAUX_PAR_HALO = 2;     // deux anneaux décalés d'un demi-cycle
const ECLAIRCISSEMENT = 0.3; // pays sélectionné : couleur mélangée à 30 % de blanc
const FRONTIERE = 0xffe9a8;  // jaune clair
const BLANC = new THREE.Color(0xffffff);

/* Réglages généraux */
const ROTATION_AUTO = 0.08;     // vitesse de rotation au repos (radians/seconde)
const DELAI_REPOS = 2500;       // délai avant reprise de la rotation automatique (ms)
const AMORTISSEMENT = 2.6;      // plus la valeur est grande, plus l'inertie s'arrête vite
const INCLINAISON_MAX = 1.15;   // limite d'inclinaison nord/sud (radians)
const INCLINAISON_REPOS = 0.3;  // inclinaison par défaut
const ZOOM_MIN = 0.8;
const ZOOM_MAX = 4.5;
const DELAI_DOUBLE_TAP = 280;   // ms
const ZOOM_DETAIL = 1.6;        // à partir de ce zoom, carte 1:50m (retour au 1:110m sous 1,4)
const SEUILS_ETIQUETTES = [1, 1.45, 2.1]; // grands pays, moyens, petits
const AIRE_GRAND = 120, AIRE_MOYEN = 25;

export class Globe {
  /**
   * @param {HTMLCanvasElement} toile  le canvas où dessiner
   * @param {HTMLElement} calqueEtiquettes  le conteneur des étiquettes HTML
   * @param {object} options
   *   pays, frontieres, leger,
   *   metrique : { cle, lire(pays) → { note, texte, niveau?, couleur? } }  (ce que représentent les couleurs ;
   *              « couleur » : teinte continue imposée, ex. flux d'investissement)
   *   surSelection(code) : appelé quand on touche un pays
   *   pulsations : [{ code, sens: 'entrees' | 'sorties', amplitude (0 à 1), vitesse (cycles/s), … }]
   *                (flux d'investissement des ETF pays, voir js/pulsations.js)
   *   afficherPulsations : pulsations visibles (bouton de l'appli)
   *   formaterPulsation(pulsation) : lignes de texte de la bulle d'un pays qui pulse
   */
  constructor(toile, calqueEtiquettes, options) {
    const { pays, frontieres, leger = false, metrique, surSelection = () => {},
      pulsations = [], afficherPulsations = true, formaterPulsation } = options;
    this.toile = toile;
    this.calque = calqueEtiquettes;
    this.pays = pays;
    this.parCode = new Map(pays.map((p) => [p.code, p]));
    this.surSelection = surSelection;
    this.leger = leger;
    this.metrique = metrique ?? { cle: 'note', lire: (p) => ({ note: p.note, texte: nombre(p.note) }) };
    this.actif = true;
    this.selection = null;
    this.afficherPulsations = afficherPulsations;
    this.formaterPulsation = formaterPulsation ?? ((x) => [x.nom ?? x.code]);
    // Réglage « réduire les animations » de l'appareil : pas de pulsations
    this.mouvementReduit = matchMedia('(prefers-reduced-motion: reduce)');
    this.mouvementReduit.addEventListener?.('change', () => this.#majVisibilitePulsations());

    // Carte vectorielle : 1:110m tout de suite, 1:50m chargée à la demande
    this.topo110 = frontieres;
    this.niveaux = {};
    this.niveauActif = null;

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
    this.rendu = new THREE.WebGLRenderer({ canvas: toile, antialias: true, alpha: true, powerPreference: 'low-power' });
    this.rendu.setClearColor(0x000000, 0);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(36, innerWidth / innerHeight, 0.05, 100);
    this.camera.position.set(0, 0, 4);

    this.groupe = new THREE.Group(); // tout ce qui tourne avec la Terre
    this.scene.add(this.groupe);
    this.texturePoint = texturePoint();

    this.#creerTerre();
    this.#creerCarte();
    this.#creerHalo();
    this.#creerPays();
    this.groupePulsations = new THREE.Group();
    this.groupe.add(this.groupePulsations);
    this.definirPulsations(pulsations);
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

  /** L'océan : sphère unie bleu nuit, légèrement repoussée en profondeur (pas de scintillement). */
  #creerTerre() {
    this.terre = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), new THREE.MeshBasicMaterial({
      color: OCEAN, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 2,
    }));
    this.groupe.add(this.terre);

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

  /** Matériaux partagés par les deux niveaux de détail, puis carte 1:110m. */
  #creerCarte() {
    this.materiauxLignes = [];
    const ligne = (params) => {
      // Décalage de profondeur : les traits passent toujours devant les pays
      const m = new LineMaterial({ transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4, ...params });
      m.resolution.set(innerWidth, innerHeight);
      this.materiauxLignes.push(m);
      return m;
    };
    // Couleur courante de chaque pays suivi (indice = position dans this.pays), puis celle
    // des pays non suivis en dernier ; elles glissent vers leurs cibles (fondu des filtres)
    this.couleursPays = [...this.pays.map(() => new THREE.Color(NON_SUIVI)), new THREE.Color(NON_SUIVI)];
    this.materiaux = {
      pays: materiauPays(this.couleursPays),
      frontiere: ligne({ color: FRONTIERE, linewidth: 0.7, opacity: 0.85 }), // un seul trait, très fin
    };
    this.materiauSelection = ligne({ color: FRONTIERE, linewidth: 1.5, opacity: 1 });
    this.contourSelection = null;
    if (this.topo110) {
      NiveauCarte.construire(this.topo110, this.pays, this.materiaux)
        .then((niveau) => this.#ajouterNiveau('110m', niveau))
        .catch((e) => console.error('Carte 1:110m', e));
    }
  }

  #ajouterNiveau(nom, niveau) {
    this.niveaux[nom] = niveau;
    if (nom === '110m') this.#majRangsEtiquettes(niveau);
    niveau.groupe.visible = false;
    this.groupe.add(niveau.groupe);
    if (!this.niveauActif) this.#activerNiveau(nom);
  }

  #activerNiveau(nom) {
    for (const [cle, niveau] of Object.entries(this.niveaux)) niveau.groupe.visible = cle === nom;
    this.niveauActif = nom;
    this.#majContourSelection();
  }

  /** Niveau de détail selon le zoom (avec une marge pour éviter les allers-retours). */
  #majNiveauCarte() {
    if (!this.niveaux['110m']) return;
    const detail = this.zoom >= (this.niveauActif === '50m' ? 1.4 : ZOOM_DETAIL);
    if (detail && !this.niveaux['50m']) { this.#chargerDetail(); return; }
    const nom = detail ? '50m' : '110m';
    if (nom !== this.niveauActif) this.#activerNiveau(nom);
  }

  /** Charge la carte 1:50m (une seule fois, à la première demande). */
  #chargerDetail() {
    if (this.chargementDetail) return;
    this.chargementDetail = fetch('data/countries-50m.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`carte 1:50m : ${r.status}`))))
      .then((topo) => {
        // Construit par petites étapes : l'écran reste fluide pendant la préparation
        return NiveauCarte.construire(topo, this.pays, this.materiaux, { pasCases: 30, etapes: true });
      })
      .then((niveau) => this.#ajouterNiveau('50m', niveau))
      .catch((e) => console.warn('Carte détaillée indisponible, on garde le 1:110m', e));
  }

  /** Contour jaune plus épais autour du pays sélectionné. */
  #majContourSelection() {
    if (this.contourSelection) {
      this.groupe.remove(this.contourSelection);
      this.contourSelection.geometry.dispose();
      this.contourSelection = null;
    }
    const positions = this.selection && this.niveaux[this.niveauActif]?.contourDe(this.selection);
    if (!positions?.length) return;
    this.contourSelection = ligneEpaisse(positions, this.materiauSelection, 5);
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


      this.objetsPays.push({
        code: p.code, indice: index, normale, colonne, sommet, anneau, etiquette, valeur,
        couleurCible: couleur.clone(),
        hauteur: 0, hauteurCible: 0,
        zoomEtiquette: SEUILS_ETIQUETTES[0], // ajusté selon la taille du pays quand la carte est prête
        phase: index * 0.137,
        haut: normale.clone(),
        visible: false, x: 0, y: 0,
      });
    });
    this.#appliquerMetriqueAuxPays(true);
  }

  /** Les étiquettes des petits pays n'apparaissent qu'en zoomant (taille lue sur la carte 1:110m). */
  #majRangsEtiquettes(niveau) {
    for (const o of this.objetsPays ?? []) {
      const aire = niveau.formeDuPays.get(o.code)?.aire ?? 0;
      o.zoomEtiquette = SEUILS_ETIQUETTES[aire > AIRE_GRAND ? 0 : aire > AIRE_MOYEN ? 1 : 2];
    }
  }

  /** Met à jour couleurs cibles, hauteurs cibles et textes des étiquettes selon la métrique. */
  #appliquerMetriqueAuxPays(immediat = false) {
    for (const o of this.objetsPays) {
      const p = this.parCode.get(o.code);
      const m = this.metrique.lire(p);
      const absente = !m || m.note === null || m.note === undefined; // donnée non disponible pour ce pays
      // Une métrique peut imposer son niveau de couleur (risque géopolitique : haut = rouge)
      const niveau = absente ? 'neutre' : (m.niveau ?? niveauNote(m.note));
      const continue_ = !absente && m.couleur != null; // teinte continue (intensité selon l'ampleur)
      o.couleurCible.set(absente ? NON_SUIVI : continue_ ? m.couleur : COULEURS[niveau]);
      o.teinteCible = new THREE.Color(absente ? NON_SUIVI : continue_ ? m.couleur : TEINTES[niveau]);
      o.teinteEclaircie = o.teinteCible.clone().lerp(BLANC, ECLAIRCISSEMENT);
      o.hauteurCible = absente ? 0.01 : 0.02 + (m.note / 100) * 0.1;
      o.valeur.textContent = absente ? 'n.d.' : m.texte;
      o.etiquette.className = `etiquette note--${niveau}${o.visible ? '' : ' est-cachee'}${o.masquee ? ' est-masquee' : ''}${o.code === this.selection ? ' est-active' : ''}`;
      o.etiquette.setAttribute('aria-label', `${p.nom}, ${absente ? 'donnée non disponible' : m.texte}`);
      o.largeurEtiquette = 0; // à remesurer (le texte a changé)
      if (immediat) {
        this.couleursPays[o.indice].copy(o.teinteCible);
        o.colonne.material.color.copy(o.couleurCible);
        o.sommet.material.color.copy(o.couleurCible);
        o.anneau.material.color.copy(o.couleurCible);
      }
    }
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

  /** Simple toucher : le halo d'un pays qui pulse (bulle), sinon un pays (fiche). */
  #toucher(x, y) {
    const bulleOuverte = Boolean(this.bulle);
    this.#masquerBulle();
    const halo = this.#haloTouche(x, y);
    if (halo) {
      if (!bulleOuverte || this.bulleCode !== halo.code) this.#afficherBulle(halo, x, y);
      return;
    }
    this.#lancerRayon(x, y);
    const impactTerre = this.raycaster.intersectObject(this.terre, false)[0];
    const code = this.#paysTouche(x, y, impactTerre);
    if (code) this.surSelection(code);
  }

  /* ======================= Pulsations des flux d'investissement ======================= */

  /** Pulsations actives : bouton activé, ni mode léger, ni « réduire les animations ». */
  pulsationsActives() {
    return this.afficherPulsations && !this.leger && !this.mouvementReduit.matches && this.halos.length > 0;
  }

  /** Remplace les pays qui pulsent (changement de période du filtre). */
  definirPulsations(liste) {
    for (const h of this.halos ?? []) for (const a of h.anneaux) a.material.dispose(); // géométrie commune conservée
    this.groupePulsations.clear();
    this.#masquerBulle();
    const avant = new THREE.Vector3(0, 0, 1);
    this.geoHalo ??= new THREE.RingGeometry(0.8, 1, 64);
    this.halos = (liste ?? []).filter((x) => this.parCode.has(x.code)).map((x, i) => {
      const p = this.parCode.get(x.code);
      const normale = versVecteur(p.lat, p.lon).normalize();
      const anneaux = Array.from({ length: ANNEAUX_PAR_HALO }, () => {
        const m = new THREE.Mesh(this.geoHalo, new THREE.MeshBasicMaterial({
          color: x.sens === 'entrees' ? COULEUR_ENTREES : COULEUR_SORTIES, transparent: true, opacity: 0,
          // Mélange normal : le vert reste vert sur un pays orange (l'additif le ferait virer au jaune)
          side: THREE.DoubleSide, depthWrite: false,
        }));
        m.position.copy(normale).multiplyScalar(1.003);
        m.quaternion.setFromUnitVectors(avant, normale);
        this.groupePulsations.add(m);
        return m;
      });
      // Rayon extérieur : selon l'amplitude (flux en % de l'encours)
      return { ...x, normale, anneaux, rayon: HALO_MAX + HALO_AMPLITUDE * x.amplitude, phase: (i * 0.29) % 1 };
    });
    this.#majVisibilitePulsations();
  }

  /** Bouton « pulsations » de l'appli. */
  definirAffichagePulsations(afficher) {
    this.afficherPulsations = afficher;
    this.#majVisibilitePulsations();
  }

  #majVisibilitePulsations() {
    this.groupePulsations.visible = this.pulsationsActives();
    if (!this.groupePulsations.visible) this.#masquerBulle();
  }

  /**
   * Animation d'un halo : entrées = anneau qui naît au centre et s'étend en s'effaçant ;
   * sorties = anneau qui naît au bord et se contracte vers le centre.
   */
  #majPulsations(temps) {
    if (!this.groupePulsations.visible) return;
    const echelleZoom = 1 / Math.sqrt(this.zoom);
    for (const h of this.halos) {
      const attenue = this.selection && this.selection !== h.code ? 0.4 : 1;
      h.anneaux.forEach((a, k) => {
        const c = (temps * h.vitesse + h.phase + k / ANNEAUX_PAR_HALO) % 1;
        let r, opacite;
        if (h.sens === 'entrees') {
          const e = 1 - Math.pow(1 - c, 2); // ralentit en s'éloignant
          r = HALO_MIN + (h.rayon - HALO_MIN) * e;
          opacite = Math.pow(1 - c, 1.3);
        } else {
          const e = c * c; // accélère vers le centre
          r = h.rayon - (h.rayon - HALO_MIN) * e;
          opacite = c < 0.8 ? 0.3 + 0.7 * (c / 0.8) : (1 - c) / 0.2;
        }
        a.scale.setScalar(r * echelleZoom);
        a.material.opacity = 0.85 * opacite * attenue;
      });
    }
  }

  /** Halo sous le doigt : distance au centre du pays inférieure au rayon du halo à l'écran (22 px au moins). */
  #haloTouche(x, y) {
    if (!this.pulsationsActives()) return null;
    const centre = new THREE.Vector3(), bord = new THREE.Vector3(), tangente = new THREE.Vector3();
    const normaleMonde = new THREE.Vector3(), versCamera = new THREE.Vector3();
    const ecran = (v) => [((v.x + 1) / 2) * this.largeur, ((1 - v.y) / 2) * this.hauteur];
    let meilleur = null, distanceMin = Infinity;
    for (const h of this.halos) {
      normaleMonde.copy(h.normale).applyQuaternion(this.groupe.quaternion);
      centre.copy(h.normale).applyMatrix4(this.groupe.matrixWorld);
      versCamera.copy(this.camera.position).sub(centre).normalize();
      if (normaleMonde.dot(versCamera) < 0.15) continue; // face cachée de la Terre
      tangente.set(0, 1, 0).cross(h.normale).normalize();
      if (tangente.lengthSq() < 0.5) tangente.set(1, 0, 0);
      bord.copy(h.normale).addScaledVector(tangente, h.rayon / Math.sqrt(this.zoom)).applyMatrix4(this.groupe.matrixWorld).project(this.camera);
      const [cx, cy] = ecran(centre.clone().project(this.camera));
      const [bx, by] = ecran(bord);
      const rayon = Math.max(22, Math.hypot(bx - cx, by - cy));
      const d = Math.hypot(x - cx, y - cy);
      if (d <= rayon && d < distanceMin) { distanceMin = d; meilleur = h; }
    }
    return meilleur;
  }

  /** Bulle d'un pays qui pulse : montant, % de l'encours, période, date ; bouton vers la fiche. */
  #afficherBulle(halo, x, y) {
    const lignes = this.formaterPulsation(halo);
    this.bulle = el('div', { class: `bulle-pulsation bulle-pulsation--${halo.sens}`, role: 'status' },
      ...(Array.isArray(lignes) ? lignes : [lignes]).map((l, i) => el('span', { class: i ? 'bulle-pulsation-detail' : 'bulle-pulsation-titre' }, l)),
      el('button', { type: 'button', class: 'bouton bouton--petit bulle-pulsation-fiche', onclick: () => { this.#masquerBulle(); this.surSelection(halo.code); } },
        'Voir la fiche'),
    );
    this.bulleCode = halo.code;
    this.calque.append(this.bulle);
    const largeur = this.bulle.offsetWidth, hauteur = this.bulle.offsetHeight;
    const gauche = Math.min(Math.max(8, x - largeur / 2), this.largeur - largeur - 8);
    const haut = y - hauteur - 16 < this.hautLibre + 4 ? y + 16 : y - hauteur - 16;
    this.bulle.style.transform = `translate(${gauche.toFixed(0)}px, ${haut.toFixed(0)}px)`;
    this.minuterieBulle = setTimeout(() => this.#masquerBulle(), 8000);
  }

  #masquerBulle() {
    clearTimeout(this.minuterieBulle);
    this.bulle?.remove();
    this.bulle = null;
    this.bulleCode = null;
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
      const code = this.niveaux[this.niveauActif]?.paysEn(point.lat, point.lon);
      if (code) return code;
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
    this.#appliquerMetriqueAuxPays(); // les couleurs glissent en douceur dans #majPays
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
    this.#masquerBulle();
    this.#majContourSelection();
  }

  definirCadrage({ cx, cy, rayon, hautLibre = 0, basLibre = innerHeight }) {
    this.cadrageCible = { cx, cy, rayon: Math.max(60, rayon) };
    this.hautLibre = hautLibre;
    this.basLibre = basLibre;
  }

  /** Mode léger : texture 1024 px, densité de pixels 2, pas de halo. */
  definirLeger(leger) {
    if (leger === this.leger) return;
    this.leger = leger;
    this.lisere.visible = !leger;
    this.halo.visible = !leger;
    this.#majVisibilitePulsations(); // pas de pulsations en mode léger
    this.redimensionner();
  }

  definirActif(actif) {
    this.actif = actif;
    this.calque.style.visibility = actif ? '' : 'hidden';
  }

  redimensionner() {
    this.largeur = innerWidth;
    this.hauteur = innerHeight;
    // Netteté : jusqu'à 3 pixels physiques par pixel sur les écrans haute résolution (2 en mode léger)
    this.rendu.setPixelRatio(Math.min(devicePixelRatio || 1, this.leger ? 2 : 3));
    this.rendu.setSize(this.largeur, this.hauteur, false);
    // Les lignes épaisses ont besoin de la taille de l'écran pour garder leur épaisseur en pixels
    for (const m of this.materiauxLignes ?? []) m.resolution.set(this.largeur, this.hauteur);
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
    this.#majNiveauCarte();
    this.#majPays(temps, dt);
    this.#majPulsations(temps);

    this.groupe.rotation.set(this.tangage, this.lacet, 0);
    this.groupe.updateMatrixWorld();
    // Seuls les morceaux de carte face à la caméra sont dessinés
    this.versCamera ??= new THREE.Vector3();
    this.niveaux[this.niveauActif]?.majVisibilite(this.groupe.quaternion, this.versCamera.copy(this.camera.position).normalize());
    this.#majEtiquettes();
    this.rendu.render(this.scene, this.camera);
    if (!this.premierRendu) { this.premierRendu = true; performance.mark('globe-premier-rendu'); }
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
    const pulsations = this.groupePulsations?.visible;
    for (const o of this.objetsPays) {
      const choisi = o.code === this.selection;
      const attenue = this.selection && !choisi;
      o.hauteur += (o.hauteurCible - o.hauteur) * lissage;
      for (const m of [o.colonne.material, o.sommet.material, o.anneau.material]) m.color.lerp(o.couleurCible, lissage);
      // Fondu des couleurs de la carte (changement de filtre ou de sélection)
      this.couleursPays[o.indice].lerp(choisi ? o.teinteEclaircie : o.teinteCible, lissage);
      const h = Math.max(0.001, o.hauteur * croissance);
      o.colonne.scale.set(choisi ? 1.6 : 1, h, choisi ? 1.6 : 1);
      o.colonne.material.opacity = attenue ? 0.35 : 0.9;
      o.sommet.material.opacity = attenue ? 0.35 : 1;
      o.sommet.position.copy(o.normale).multiplyScalar(1 + h);
      o.haut.copy(o.normale).multiplyScalar(1 + h + 0.015);
      // Anneau immobile en mode léger, ou quand les halos des flux pulsent (pour ne pas les confondre)
      if (this.leger || pulsations) {
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
