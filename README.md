# Salle de contrôle — plateforme de suivi économique mondial

Prototype d'une application personnelle de suivi économique mondial, pensée d'abord pour le téléphone.
**Toutes les données sont fictives.** Aucune vraie source de données n'est branchée et aucun agent IA n'existe encore.

## Ce que fait le prototype

- **Globe 100 % vectoriel** (aucune image), net à tous les niveaux de zoom.
  - L'océan est une sphère bleu nuit unie.
  - Tous les pays sont des polygones 3D opaques :
    - pays suivis en couleur pleine selon leur note : vert émeraude, ambre ou rouge corail ;
    - pays non suivis en gris bleu ;
    - le pays sélectionné est éclairci.
  - Les frontières forment un seul trait jaune clair de 0,7 px (1,5 px autour du pays sélectionné).
  - Côtes et frontières détaillées : Natural Earth au 1:110m au démarrage, puis au 1:50m quand on zoome de près (chargé à la demande).
- **Flux de capitaux (fictifs)**
  - Épaisseur et vitesse selon le montant.
  - Couleur selon le sens : vert pour les entrées vers un pays bien noté, rouge pour les sorties d'un pays mal noté.
  - Toucher un arc affiche une bulle, par exemple « États-Unis → Brésil : 4,2 Md$ sur 1 mois ».
  - Quand un pays est sélectionné, seuls ses flux restent visibles.
  - Bouton « Flux » pour les masquer ou les afficher.
- **Filtres du globe** (puces en bas de l'écran) : note globale, croissance du PIB, inflation, valorisation (PER), devise sur 3 mois, flux étrangers, momentum boursier.
  - Le globe se recolore en fondu, et les étiquettes affichent la valeur choisie.
  - Le choix est mémorisé sur l'appareil.
- **Gestes** :
  - rotation au doigt avec inertie ; le globe tourne seul au repos ;
  - zoom par pincement, molette ou double-tap ;
  - toucher un pays ouvre sa fiche.
- **Fiches** pays, secteur et entreprise, dans un panneau à trois hauteurs (réduit, normal, plein écran).
- **Comparateur** : le bouton « + Comparer » des fiches permet de sélectionner 2 ou 3 pays, ou 2 ou 3 entreprises.
  - Une barre flottante montre la sélection, avec le bouton « Voir la comparaison ».
  - L'écran de comparaison place les éléments côte à côte ; la meilleure valeur de chaque ligne est mise en évidence.
- **Mes alertes**, accessible depuis le bandeau des alertes : règles personnelles vérifiées à chaque chargement des données.
  - Les alertes déclenchées apparaissent en tête du bandeau, avec le badge « Mon alerte ».
- **Classement** des pays et des 20 meilleures entreprises.
- **Portefeuille démo** de 100 000 €.
- **Netteté** : antialiasing, densité de pixels jusqu'à 3 sur les écrans haute résolution.
- **Mode léger** (⚡) : densité de pixels limitée à 2, sans halo, sans animation des flux, 30 images/s.
- **PWA** : l'appli s'installe sur l'écran d'accueil. Le service worker charge l'appli « réseau d'abord », donc la dernière version s'affiche dès l'ouverture ; elle reste utilisable hors ligne.

## Structure

```
index.html            page unique
manifest.json, sw.js  PWA (installation, cache hors ligne)
css/style.css         thème « salle de contrôle »
js/app.js             démarrage, navigation, fil d'Ariane
js/donnees.js         chargement des JSON (seul fichier à modifier si les chemins changent)
js/globe.js           globe 3D (Three.js r160), gestes, zoom, flux, étiquettes
js/carte-vecteur.js   carte vectorielle : pays triangulés, trait de frontière, niveaux 110m / 50m
js/interface.js       horloge, bandeau des marchés, alertes, mode léger
js/panneau-pays.js    fiches pays et secteur
js/panneau-entreprise.js  fiche entreprise
js/portefeuille.js    écran portefeuille
js/classement.js      écran classement
js/comparateur.js     comparateur (sélection, barre flottante, écran)
js/mes-alertes.js     règles d'alertes personnelles
js/outils.js          couleurs des notes, formats français
data/*.json           données fictives
data/countries-110m.json, countries-50m.json  frontières des pays (voir data/LICENCE-countries-110m.txt)
outils/generer_donnees_fictives.py  régénère les données fictives
```

## Format des données (pour les futurs agents)

Chaque fichier de `data/` a la même enveloppe :

```json
{
  "meta": { "version": 1, "genere_le": "2026-11-01T07:00:00Z", "source": "agent-macro", "fictif": true },
  "donnees": [ ... ]
}
```

Les fichiers sont reliés par des identifiants :
- le code pays ISO (`FR`)
- l'identifiant de secteur (`FR-luxe`)
- le ticker de l'entreprise (`MAIS`)

| Fichier | Futur agent | Contenu |
|---|---|---|
| `pays.json` | pays + macro | note, verdict, 5 indicateurs (valeur + note), lectures des agents, flux |
| `secteurs.json` | pays | capitalisation, momentum 3 mois, note, entreprises |
| `entreprises.json` | entreprises | 5 indicateurs, verdict, lecture de chaque agent, étude complète |
| `alertes.json` | chef d'orchestre | heure, agent, pays, niveau, titre, texte |
| `marches.json` | macro | indices, taux, devises, matières premières |
| `portefeuille.json` | trader | valeur, statistiques, allocation, positions, historique, dernière décision |

Chaque flux de `pays.json` indique son montant, sa devise et sa période (`montant_md`, `devise`, `periode`).
Le champ `momentum_boursier` d'un pays alimente le filtre « Momentum boursier ».

Chaque pays a aussi un champ `iso_num` : son code ISO numérique, qui le relie à sa forme dans `countries-110m.json`.
Singapour, trop petit pour l'échelle 1:110m, est dessiné comme un disque.

Chaque indicateur porte **sa propre note sur 100**, et c'est elle qui fixe la couleur affichée.
Un agent peut donc juger lui-même si une valeur est bonne ou mauvaise.

Quand **tous** les fichiers portent `"fictif": false` dans `meta`, la mention « Données fictives » disparaît d'elle-même.

## Format des règles « Mes alertes »

Les règles sont stockées sur l'appareil (`localStorage`, clé `salle-controle:mes-alertes`).
Le serveur des agents pourra les relire telles quelles :

```json
{
  "version": 1,
  "regles": [
    {
      "id": "r-mvydfjboiw6",
      "active": true,
      "cree_le": "2026-11-01T21:57:52.404Z",
      "cible": { "type": "pays", "id": "BR" },
      "indicateur": "inflation",
      "condition": "passe_sous",
      "seuil": 4,
      "derniere_verification": "2026-11-01T21:57:58.292Z",
      "declenchee": true,
      "elements_declenches": ["BR"]
    }
  ]
}
```

- `cible.type` vaut `pays` ou `entreprise`. `cible.id` est le code pays ou le ticker, ou `null` pour « tous ».
- `indicateur` vaut `note`, ou la clé d'un indicateur (`croissance_pib`, `inflation`, `per`, `devise_3m`, `flux_etrangers`, `momentum` ; pour une entreprise : `croissance_ca`, `benefice`, `marge`, `dette_ebitda`, `per_vs_secteur`).
- `condition` vaut `depasse` (valeur > seuil) ou `passe_sous` (valeur < seuil).
- « Une entreprise passe au rouge » s'écrit : note `passe_sous` 50.

## Sources

Les frontières (`data/countries-110m.json` et `data/countries-50m.json`) viennent de [world-atlas](https://github.com/topojson/world-atlas) 2.0.2, dérivé de Natural Earth (domaine public).
Three.js r160 est chargé depuis cdnjs ; ses modules de lignes épaisses (`examples/jsm/lines`) viennent de jsDelivr, dans la même version, via l'import map de `index.html`.
La licence ISC de world-atlas est reproduite dans `data/LICENCE-countries-110m.txt`.

## Tester en local

```
python3 -m http.server 8000
```

puis ouvrir http://localhost:8000. Il faut passer par un serveur : ouvrir directement le fichier `index.html` ne permet pas de charger les JSON.

## Mettre en ligne (GitHub Pages)

Dans **Settings → Pages**, choisir **Deploy from a branch**, puis la branche `main` et le dossier `/ (root)`.
