# Salle de contrôle — plateforme de suivi économique mondial

Prototype d'une application personnelle de suivi économique mondial, pensée d'abord pour le téléphone.
**Toutes les données sont fictives.** Aucune vraie source de données n'est branchée et aucun agent IA n'existe encore.

## Ce que fait le prototype

- **Globe 3D** avec la vraie carte des pays (frontières Natural Earth au 1:110m, stockées dans le dépôt).
  - Les 31 pays suivis sont colorés selon leur note sur 100 :
    - vert : 65 et plus, attractif
    - orange : de 50 à 64, neutre
    - rouge : moins de 50, défavorable
  - Les autres pays restent gris bleu foncé, avec des frontières fines cyan.
  - Chaque pays suivi porte une fine colonne lumineuse, un anneau qui pulse et une étiquette.
  - Des arcs animés représentent les flux de capitaux.
- **Gestes** :
  - tourner au doigt (avec inertie) ; le globe tourne seul au repos ;
  - zoomer par pincement, molette ou double-tap ;
  - toucher un pays ouvre sa fiche.

  Les étiquettes des petits pays n'apparaissent qu'en zoomant.
- **En-tête compact sur une ligne** : titre, horloge, légende (bouton « ? »), mode léger (⚡), Classement, Portefeuille démo.
- **Alertes du jour** : toucher une alerte ouvre le pays concerné.
- **Panneau des fiches**, à trois hauteurs (réduit, normal, plein écran) réglables avec la poignée.
  - Fiche pays et fiche entreprise : le verdict est tout en haut, suivi des 5 indicateurs en liste compacte.
  - Fiche pays : secteurs en bulles et lecture des agents.
  - Fiche entreprise : onglets par agent et étude complète.
- **Classement** : les pays triés par note, et les 20 meilleures entreprises tous pays confondus.
- **Portefeuille démo** : 100 000 € en structure cœur-satellite, comparés au MSCI World.
- **Mode léger** : texture plus petite, pas d'animation des flux, 30 images/s.
- **PWA** : l'appli s'installe sur l'écran d'accueil et fonctionne hors ligne une fois chargée.

## Structure

```
index.html            page unique
manifest.json, sw.js  PWA (installation, cache hors ligne)
css/style.css         thème « salle de contrôle »
js/app.js             démarrage, navigation, fil d'Ariane
js/donnees.js         chargement des JSON (seul fichier à modifier si les chemins changent)
js/globe.js           globe 3D (Three.js r160 via cdnjs), carte, gestes, zoom
js/interface.js       horloge, bandeau des marchés, alertes, mode léger
js/panneau-pays.js    fiches pays et secteur
js/panneau-entreprise.js  fiche entreprise
js/portefeuille.js    écran portefeuille
js/classement.js      écran classement
js/outils.js          couleurs des notes, formats français
data/*.json           données fictives
data/countries-110m.json  frontières des pays (voir data/LICENCE-countries-110m.txt)
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

Chaque pays a aussi un champ `iso_num` : son code ISO numérique, qui le relie à sa forme dans `countries-110m.json`.
Singapour, trop petit pour l'échelle 1:110m, est dessiné comme un disque.

Chaque indicateur porte **sa propre note sur 100**, et c'est elle qui fixe la couleur affichée.
Un agent peut donc juger lui-même si une valeur est bonne ou mauvaise.

Quand **tous** les fichiers portent `"fictif": false` dans `meta`, la mention « Données fictives » disparaît d'elle-même.

## Sources

Les frontières (`data/countries-110m.json`) viennent de [world-atlas](https://github.com/topojson/world-atlas) 2.0.2, dérivé de Natural Earth (domaine public).
La licence ISC de world-atlas est reproduite dans `data/LICENCE-countries-110m.txt`.

## Tester en local

```
python3 -m http.server 8000
```

puis ouvrir http://localhost:8000. Il faut passer par un serveur : ouvrir directement le fichier `index.html` ne permet pas de charger les JSON.

## Mettre en ligne (GitHub Pages)

Dans **Settings → Pages**, choisir **Deploy from a branch**, puis la branche `main` et le dossier `/ (root)`.
