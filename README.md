# Salle de contrôle — plateforme de suivi économique mondial

Prototype d'une application personnelle de suivi économique mondial, pensée d'abord pour le téléphone.
**Toutes les données sont fictives.** Aucune vraie source de données n'est branchée et aucun agent IA n'existe encore.

## Ce que fait le prototype

- Un globe 3D plein écran, qu'on fait tourner au doigt (avec inertie). Il tourne tout seul au repos.
- 16 pays, chacun avec une colonne lumineuse : sa hauteur et sa couleur suivent la note sur 100.
  - vert : 65 et plus, attractif
  - orange : de 50 à 64, neutre
  - rouge : moins de 50, défavorable
- Des arcs animés qui représentent les flux de capitaux entre pays.
- Un bandeau défilant des marchés, une horloge et la légende des couleurs.
- Les alertes du jour : toucher une alerte ouvre le pays concerné.
- Une fiche pays avec 5 indicateurs, les secteurs en bulles et la lecture des agents.
- Une fiche secteur qui liste ses entreprises, et une fiche entreprise avec onglets par agent et étude complète.
- Un portefeuille démo de 100 000 €, en structure cœur-satellite, comparé au MSCI World.
- Un mode léger (bouton ⚡) qui économise la batterie.
- L'appli s'installe sur l'écran d'accueil (PWA) et fonctionne hors ligne une fois chargée.

## Structure

```
index.html            page unique
manifest.json, sw.js  PWA (installation, cache hors ligne)
css/style.css         thème « salle de contrôle »
js/app.js             démarrage, navigation, fil d'Ariane
js/donnees.js         chargement des JSON (seul fichier à modifier si les chemins changent)
js/globe.js           globe 3D (Three.js r160 via cdnjs)
js/interface.js       horloge, bandeau des marchés, alertes, mode léger
js/panneau-pays.js    fiches pays et secteur
js/panneau-entreprise.js  fiche entreprise
js/portefeuille.js    écran portefeuille
js/outils.js          couleurs des notes, formats français
data/*.json           données fictives
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

Chaque indicateur porte **sa propre note sur 100**, et c'est elle qui fixe la couleur affichée.
Un agent peut donc juger lui-même si une valeur est bonne ou mauvaise.

Quand **tous** les fichiers portent `"fictif": false` dans `meta`, la mention « Données fictives » disparaît d'elle-même.

## Tester en local

```
python3 -m http.server 8000
```

puis ouvrir http://localhost:8000. Il faut passer par un serveur : ouvrir directement le fichier `index.html` ne permet pas de charger les JSON.

## Mettre en ligne (GitHub Pages)

Dans **Settings → Pages**, choisir **Deploy from a branch**, puis la branche `main` et le dossier `/ (root)`.
