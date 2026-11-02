# Salle de contrôle — plateforme de suivi économique mondial

Prototype d'une application personnelle de suivi économique mondial, pensée d'abord pour le téléphone.
**Les données des pays sont réelles** : elles sont produites chaque jour par l'**agent pays** (FMI, OCDE, BIS, Yahoo Finance), qui tourne gratuitement avec GitHub Actions.
Le reste (secteurs, entreprises, alertes, flux de capitaux, portefeuille, marchés) est encore **fictif**, en attendant les autres agents.

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
- **Bandeau des marchés** : Nasdaq 100, S&P 500, Or, Pétrole WTI, Bitcoin, EUR/USD, CAC 40, MSCI World.
  - Il défile tout seul, se glisse au doigt ou à la souris avec inertie, et se met en pause au toucher (reprise 4 s après le relâchement) ou au survol.
  - Toucher une cotation affiche sa valeur, sa variation du jour et sa variation sur 1 an.
- **Indicateurs des pays** (6, données réelles) :
  - croissance du PIB (FMI) ;
  - indicateur avancé (OCDE, au-dessus de 100 = accélération) ;
  - inflation, avec la cible de la banque centrale ;
  - taux réel (taux directeur de la BIS moins l'inflation), avec la direction de la banque centrale ;
  - valorisation relative (PER de l'ETF pays comparé à la médiane des pays suivis) ;
  - momentum boursier sur 12 mois (ETF pays).

  La devise sur 3 mois, le solde courant et les flux étrangers (non disponibles pour l'instant) sont dans la section repliable « Détail ».
  Chaque fiche pays affiche aussi :
  - le niveau de confiance de l'agent ;
  - la rubrique « Ce qui pourrait me donner tort » ;
  - la lecture de l'agent ;
  - les sources et les dates exactes de chaque valeur.
- **Tendances** : une flèche ↑ ↓ → indique l'évolution depuis la mise à jour précédente, sur chaque indicateur et chaque note (pays, secteur, entreprise). Le vert signale une note qui s'améliore, le rouge une note qui se dégrade.
- **Recherche** (loupe dans l'en-tête) : pays, secteurs et entreprises, par nom ou ticker, sans tenir compte des accents. Toucher un résultat ouvre la fiche et centre le globe.
- **Fraîcheur des données** : sous chaque fiche, « Mis à jour le … · Source : … », lu dans le bloc `meta` des JSON.
- **Filtres du globe** (puces en bas de l'écran) : la note globale et les 6 indicateurs des pays.
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

## Agent pays (données réelles)

L'agent pays se trouve dans `agents/`, en Python 3.12.
- Il interroge des sources gratuites et sans clé API : FMI, OCDE, BIS et Yahoo Finance.
- Il note chaque indicateur sur 100, puis calcule une note globale pondérée et un niveau de confiance.
- Il écrit des textes factuels et met à jour `data/pays.json`.
- Les règles de notation et de conduite sont décrites dans [`agents/pays/regles.md`](agents/pays/regles.md). Les pondérations se modifient dans `agents/pays/config.json`.

**Exécution** : le workflow `.github/workflows/agent-pays.yml` lance l'agent chaque jour à 6 h UTC ; on peut aussi le lancer à la main.
- Il ne commite sur `main` que si les données ont changé, avec le message « Agent pays : mise à jour du JJ/MM/AAAA ».
- Chaque jour, il garde ses notes dans `data/historique/pays/AAAA-MM-JJ.json`.

**Pannes de source** : si une source ne répond pas, l'agent ne s'arrête pas. Il garde la dernière valeur connue avec sa date et la signale comme « ancienne ».

**Textes** : par défaut, ils sont rédigés par des règles. Si le secret GitHub `GEMINI_API_KEY` est créé (Settings → Secrets and variables → Actions), l'API gratuite Gemini les rédige, sous les mêmes contraintes. Un texte non conforme est remplacé par la version par règles.

Pour lancer l'agent sur un ordinateur :

```
pip install -r agents/requirements.txt
python -m agents.pays            # vraies sources
python -m agents.pays --test     # données de test, sans réseau
python -m unittest discover -s agents -t .   # tests
```

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
js/recherche.js       recherche de pays, secteurs et entreprises
js/mes-alertes.js     règles d'alertes personnelles
js/outils.js          couleurs des notes, formats français
data/pays.json        données réelles des pays (produites par l'agent pays)
data/historique/pays/ historique quotidien des notes de l'agent pays
data/flux.json        flux de capitaux entre pays (fictifs)
data/*.json           autres données (fictives pour l'instant)
agents/               agents Python (agents/commun : téléchargement, cache, journal, écriture ; agents/pays : agent pays)
.github/workflows/    exécution planifiée des agents (GitHub Actions)
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

Le bloc `meta` de chaque fichier contient :
- `genere_le` : date de la mise à jour, affichée sous les fiches ;
- `mise_a_jour_precedente` ;
- `source` : pour l'instant « fictive » ;
- `producteur_futur` : l'agent qui produira ce fichier.

Chaque note et chaque indicateur a un champ `precedent` (valeur et note de la mise à jour précédente), qui alimente les flèches de tendance :

```json
"inflation": { "libelle": "Inflation", "valeur": 3.9, "unite": "%", "note": 76, "cible": 3.0,
               "precedent": { "valeur": 4.1, "note": 74 } }
```

Les pays ont 6 indicateurs (`croissance_pib`, `indicateur_avance`, `inflation`, `taux_reel`, `valorisation`, `momentum`). Chacun porte sa `date` et sa `source` exacte. Il peut aussi porter :
- `ancienne` : source en panne, la dernière valeur connue est conservée ;
- `a_verifier` : valeur inhabituelle non confirmée.

Un indicateur indisponible a `"valeur": null` et une `raison`.
- `inflation` porte en plus la `cible` de la banque centrale et sa `frequence` ;
- `taux_reel` porte le `taux_directeur` et la `direction` (« baisse », « stable » ou « hausse ») ;
- `valorisation` porte le `per` de l'ETF et la `mediane` des pays suivis.

Chaque pays porte aussi :
- `confiance` (`niveau`, `score`, `raisons`) ;
- `contre_scenario` (« Ce qui pourrait me donner tort ») ;
- `lecture`.

Le bloc `detail` contient `devise_3m`, `solde_courant` et `flux_etrangers`. `marches.json` donne pour chaque cotation `variation` (jour, en %) et `variation_1an`.

Les flux de capitaux (fictifs) sont dans `data/flux.json` (`de`, `vers`, `montant_md`, `devise`, `periode`).

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
- `indicateur` vaut `note`, ou la clé d'un indicateur :
  - pour un pays : `croissance_pib`, `pmi`, `inflation`, `taux_reel`, `valorisation`, `momentum` (et, pour d'anciennes règles, `devise_3m` ou `flux_etrangers`) ;
  - pour une entreprise : `croissance_ca`, `benefice`, `marge`, `dette_ebitda`, `per_vs_secteur`.
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
