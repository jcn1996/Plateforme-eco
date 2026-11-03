# Salle de contrôle — plateforme de suivi économique mondial

Prototype d'une application personnelle de suivi économique mondial, pensée d'abord pour le téléphone.
**Les données des pays sont réelles** : elles sont produites chaque jour par l'**agent pays** (instituts statistiques nationaux, banques centrales, FMI, OCDE, BRI, Banque mondiale, Eurostat, BCE, Yahoo Finance, avec vérification croisée), qui tourne gratuitement avec GitHub Actions.
**Les cours du bandeau des marchés sont réels** : l'**agent marchés** (sans IA) les met à jour toutes les 15 minutes en semaine.
**Les secteurs et les entreprises sont réels** (agent entreprises). Le reste (alertes, flux de capitaux, portefeuille) est encore **fictif**, en attendant les autres agents.

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
- **Bandeau des marchés** (cours réels, différés d'environ 15 min) : Nasdaq 100, S&P 500, Or, Pétrole WTI, Bitcoin, EUR/USD, CAC 40, MSCI World (ETF URTH).
  - Chaque cotation porte une pastille « ouvert » ou « fermé ».
  - Il défile tout seul, se glisse au doigt ou à la souris avec inertie, et se met en pause au toucher (reprise 4 s après le relâchement) ou au survol.
  - Toucher une cotation affiche son cours, sa variation du jour, sa variation sur 1 an, l'heure du cours et la source.
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
- Il interroge des sources gratuites : instituts statistiques nationaux (INSEE, Destatis, ONS, BLS, Japon, IBGE, Statistique Canada, via DBnomics ou leur banque centrale), BCE, FMI, OCDE, BRI, Banque mondiale, Eurostat et Yahoo Finance.
- **Vérification croisée** : chaque indicateur est récupéré auprès de plusieurs sources quand c'est possible. L'ordre de priorité est le suivant : source nationale officielle, puis organisation internationale, puis source de marché. Si deux sources s'écartent trop, l'indicateur est marqué « sources divergentes » et la confiance baisse. Une valeur aberrante ou trop ancienne est rejetée. Tout est décrit dans [`agents/pays/sources.md`](agents/pays/sources.md).
- Il note chaque indicateur sur 100, puis calcule une note globale pondérée et un niveau de confiance.
- Il écrit des textes factuels et met à jour `data/pays.json`.
- Les règles de notation et de conduite sont décrites dans [`agents/pays/regles.md`](agents/pays/regles.md). Les pondérations se modifient dans `agents/pays/config.json`.

**Exécution** : le workflow `.github/workflows/agent-pays.yml` lance l'agent chaque jour à 6 h 11 UTC ; on peut aussi le lancer à la main.
- Il commite sur `main` avec le message « Agent pays : mise à jour du JJ/MM/AAAA ». Même quand les données n'ont pas changé, la date de dernière exécution est enregistrée dans son journal (pour l'écran « Santé des agents »).
- Chaque jour, il garde ses notes dans `data/historique/pays/AAAA-MM-JJ.json`.
- Il écrit un récapitulatif factuel dans `data/recap/pays-AAAA-MM-JJ.md` : ce qui a changé, les divergences entre sources, les données manquantes et les mouvements de notes.
- Il tient le journal des sources en échec dans `data/journal/agent-pays.json`.

**Pannes de source** : si une source ne répond pas, l'agent ne s'arrête pas. Il garde la dernière valeur connue avec sa date et la signale comme « ancienne ». Si plus d'un tiers des sources d'un pays échouent, l'appli affiche une alerte « Qualité des données » sur la fiche du pays et en tête du bandeau des alertes.

**Textes** : par défaut, ils sont rédigés par des règles. Si le secret GitHub `GEMINI_API_KEY` est créé (Settings → Secrets and variables → Actions), l'API gratuite Gemini les rédige, sous les mêmes contraintes. Un texte non conforme est remplacé par la version par règles.

**BLS (facultatif)** : l'inflation américaine vient aussi de l'API publique du BLS (version 1, sans clé, limitée à 25 requêtes par jour et par adresse IP). Avec le secret GitHub `BLS_API_KEY` (clé gratuite sur data.bls.gov), l'agent utilise la version 2, plus généreuse.

**FRED (facultatif)** : avec le secret GitHub `FRED_API_KEY` (clé gratuite sur fred.stlouisfed.org), l'agent ajoute l'inflation et le taux de la Réserve fédérale publiés par FRED. Sans ce secret, il s'en passe.

Pour lancer l'agent sur un ordinateur :

```
pip install -r agents/requirements.txt
python -m agents.pays            # vraies sources
python -m agents.pays --test     # données de test, sans réseau
python -m unittest discover -s agents -t .   # tests
```

## Agent marchés (cours réels, sans IA)

L'agent marchés se trouve dans `agents/marches/`, en Python 3.12. Il met à jour `data/marches.json`.
- Actifs, dans l'ordre : Nasdaq 100 (`^NDX`), S&P 500 (`^GSPC`), Or (`GC=F`, $/once), Pétrole WTI (`CL=F`, $/baril), Bitcoin (`BTC-USD`), EUR/USD (`EURUSD=X`), CAC 40 (`^FCHI`), MSCI World (ETF `URTH`).
- Pour chacun : dernier cours, variation du jour (%), variation sur 1 an (%), heure du cours, statut « ouvert » ou « fermé ».
- Sources : Yahoo Finance (via yfinance) ; Stooq (CSV gratuit) en secours ; sinon la dernière valeur est conservée avec son heure et marquée « ancienne ».
- Le fichier n'est réécrit que si les valeurs ont changé.

**Exécution** : le workflow `.github/workflows/agent-marches.yml` tourne toutes les 15 minutes du lundi au vendredi de 7 h 07 à 22 h 07 UTC (minutes 7, 22, 37, 52), et toutes les heures (minute 7) le week-end (pour le Bitcoin). Il ne commite que si les valeurs ont changé, avec le message « Marchés : HH:MM » (heure de Paris). On peut aussi le lancer à la main : onglet **Actions** → **Agent marchés** → **Run workflow**.

```
python -m agents.marches
```

## Agent macro (vue d'ensemble, sans IA)

L'agent macro se trouve dans `agents/macro/`, en Python 3.12. Il complète l'agent pays, qui note chaque pays, par une vue de l'économie mondiale.

**Sources** (gratuites ; croisées quand c'est possible) :
- FRED : courbe des taux US (T10Y2Y, T10Y3M), règle de Sahm (SAHMREALTIME), chômage (UNRATE), fourchette de la Fed. Avec le secret `FRED_API_KEY`, FRED est lu par son API ; sinon par son fichier CSV public, sans clé.
- Bundesbank : rendements allemands à 2 et 10 ans, vérifiés avec la courbe AAA de la zone euro (BCE Data Portal).
- OCDE (indicateur avancé, IPC), Eurostat (IPCH), FMI (WEO).
- BRI (taux directeurs quotidiens) et sources nationales (FRED, BCE, Banque du Canada, Banco Central do Brasil).
- Yahoo Finance : cuivre, pétrole WTI, indice dollar, or ; taux US à 10 ans et 13 semaines, pour la vérification croisée.

**Analyse** :
- phase du cycle pour le monde, les États-Unis, la zone euro, la Chine, le Japon et les émergents ;
- signaux de récession ;
- banques centrales : taux, dernier mouvement, tendance sur 12 mois, prochaine réunion ;
- marchés du cycle ;
- deux phrases de lecture macro par pays suivi.

Les règles sont détaillées dans [`agents/macro/regles.md`](agents/macro/regles.md) : correspondance des phases, deux signaux concordants pour changer de phase, confiance, « Ce qui pourrait me donner tort ».

**Calendrier des banques centrales** : `agents/macro/calendrier_banques_centrales.json` contient les dates officielles relevées sur le site de chaque banque. Quand une banque n'a plus de date future, l'écran « Santé des agents » affiche une alerte, avec un avertissement 60 jours avant. Il faut alors ajouter les nouvelles dates à la main.

**Sorties** :
- `data/macro.json` ;
- `data/signaux/macro.json` : signaux candidats pour le futur chef d'orchestre ;
- `data/historique/macro/AAAA-MM-JJ.json` ;
- `data/recap/macro-AAAA-MM-JJ.md` ;
- `data/journal/agent-macro.json`.

**Exécution** : le workflow `.github/workflows/agent-macro.yml` tourne chaque jour à 6 h 41 UTC. On peut aussi le lancer à la main : onglet **Actions** → **Agent macro** → **Run workflow**.

```
python -m agents.macro             # vraies sources
python -m agents.macro --test      # données de test (captures réelles), sans réseau
python -m agents.macro --capturer  # met à jour les données de test
```

**Dans l'appli** :
- le bouton « Macro » de l'en-tête ouvre l'écran **Vue macro** : schéma du cycle en 4 quadrants, signaux de récession, banques centrales, courbe des taux US sur 2 ans, marchés du cycle ;
- la fiche pays affiche la rubrique « Agent macro », avec sa date.

## Agent entreprises (environ 1 200 sociétés, sans IA)

L'agent entreprises se trouve dans `agents/entreprises/`. Les règles de conduite sont les mêmes que pour l'agent pays.

**Univers** : S&P 500 et les 150 plus grandes valeurs du S&P 400, puis les plus grosses positions des ETF iShares MSCI de chaque pays suivi, avec un plafond par pays (`config.json`) ; à cela s'ajoute la liste de surveillance personnelle (`config/surveillance.json`).
- Filtre : capitalisation d'au moins 300 M$ et volume suffisant.
- Doublons écartés : catégories d'actions (GOOGL / GOOG) et doubles cotations.
- Si une source de composition échoue :
  1. secours : SSGA SPY / MDY pour les États-Unis, filtre d'actions Yahoo ailleurs ;
  2. sinon, dernière liste connue (`data/entreprises/univers.json`).

**Comptes** :
- États-Unis : SEC (API XBRL et flux des publications ; secret `SEC_USER_AGENT`).
- Europe : rapports annuels ESEF sur filings.xbrl.org, le LEI étant trouvé via GLEIF.
- Japon et Corée : EDINET (`EDINET_API_KEY`) et DART (`DART_API_KEY`), facultatifs.
- Partout : yfinance pour les cours et les états financiers annuels et trimestriels.

Quand la source officielle et Yahoo s'écartent de plus de 5 %, la source officielle est retenue et l'écart signalé. Sans source officielle, la confiance est plafonnée à « moyen ».

**Analyse** :
- croissance du CA (sur un an et tendance sur 3 ans) et du bénéfice ;
- marge opérationnelle et son évolution ;
- conversion du bénéfice en cash ;
- dette nette / EBITDA, couverture des intérêts ;
- ROIC, ou ROE pour les financières ;
- PER et VE/EBITDA comparés à la médiane du secteur (régionale, à défaut mondiale) ;
- momentum sur 6 et 12 mois ;
- F-score de Piotroski ;
- signaux d'alerte comptables ;
- critères adaptés aux banques et assurances.

Chaque société reçoit une note sur 100 (pondérations dans `config.json`), un verdict, un niveau de confiance et une rubrique « Ce qui pourrait me donner tort ».

**Pépites candidates** (`data/pepites.json`) : sociétés qui remplissent tous les critères de `config.json`. Elles sont classées par note ajustée selon le contexte : note du pays et phase du cycle de sa zone, un ajustement modéré affiché à part. Chacune a une revue critique : risques, piège de valeur possible, risque de change, risque pays, points à vérifier soi-même et lien vers le dernier rapport officiel.

**Exécution** (`.github/workflows/agent-entreprises.yml`) :
- en semaine à 22 h 30 UTC : cours, momentum, valorisation, et révision des sociétés ayant publié ;
- le samedi : révision complète en 6 lots parallèles, puis assemblage ;
- à la main : onglet **Actions** → **Agent entreprises** → **Run workflow** (mode `quotidien`, `complet` ou `echantillon`).

```
python -m agents.entreprises --mode complet --echantillon 60   # essai sur 60 sociétés
python -m agents.entreprises --mode complet --lot europe --sortie-lot lot.json
python -m agents.entreprises --mode assembler --lots lot*.json
python -m agents.entreprises --mode quotidien
```

**Liste de surveillance** : ajouter une ligne dans `config/surveillance.json`, par exemple `{"ticker": "ASML.AS", "pays": "NL"}`. Le ticker est le symbole Yahoo Finance ; le pays, le code à 2 lettres d'un pays suivi. La société est analysée à la révision suivante, même hors de l'univers et quelle que soit sa taille.

## Santé des agents

L'icône en forme de pouls, dans l'en-tête, ouvre l'écran **Santé des agents**. Une pastille rouge s'y affiche dès qu'un agent n'est pas « OK ».
Pour chaque agent (pays, marchés, puis les suivants), l'écran affiche :
- la date et l'heure de la dernière exécution réussie ;
- le statut :
  - calculé à partir du **planning** que chaque agent déclare dans son journal (champ `planning` : expressions `cron`, fuseau UTC) : l'appli en déduit la première exécution prévue après la dernière exécution réussie ;
  - **en panne** (rouge) si cette exécution prévue manque depuis plus de 2 h pour un agent à 15 min (marchés), ou 26 h pour un agent quotidien (pays, macro) ;
  - **en retard** (orange) si elle manque depuis plus de 45 min (agent à 15 min) ou 2 h (agent quotidien) ;
  - **en pause** (gris) hors des heures prévues, par exemple la nuit pour l'agent marchés (après 22 h 07 UTC en semaine), avec l'heure de la prochaine mise à jour, en heure de Paris (« Prochaine mise à jour : lun. 8 h 07 ») ;
  - **dégradé** si un indicateur a perdu une source qu'il devrait avoir, c'est-à-dire qu'il a moins de sources valides que lors de la dernière exécution saine (par exemple, deux sources puis une seule). Une source retirée de la configuration n'est plus attendue ; une source périmée remplacée par une source à jour ne compte pas ;
  - **OK** sinon ;
- le nombre de sources qui répondent sur le total ;
- les sources en échec ou périmées, avec la date de leur dernière donnée valide.

Les données viennent de `data/journal/*.json` (bloc `meta.sante` ; `derniere_execution`, `prochaine_prevue`, `intervalle_min` et `planning` sont aussi recopiés au premier niveau du journal, écrit par `agents/commun/sante.py`). `data/journal/index.json` liste les journaux à lire. Un nouvel agent n'a qu'à appeler `sante.bloc_sante(...)` puis `sante.enregistrer_sante(...)` pour apparaître dans l'écran.

Tests de la logique du planning (nuit, week-end, journée, avec des dates simulées) : `node --test js/tests/*.test.mjs`.

## Fiabilité des exécutions planifiées

GitHub retarde, voire saute, souvent les tâches planifiées aux minutes rondes. Les agents tournent donc à des minutes décalées : marchés à 7, 22, 37 et 52 (de 7 h 07 à 22 h 07 UTC en semaine, à la minute 7 de chaque heure le week-end), pays à 6 h 11 UTC, macro à 6 h 41 UTC.

Le workflow `.github/workflows/rattrapage.yml` tourne toutes les heures (minute 29). Il lit `data/journal/*.json` et relance (`gh workflow run`, déclencheur `workflow_dispatch`) chaque agent dont une exécution prévue manque depuis plus d'une heure, au plus une fois par agent et par heure, et jamais si une exécution est déjà en cours ou en attente. Chaque relance est tracée dans `data/journal/rattrapage.json`.

Chaque workflow a un groupe `concurrency` (jamais deux exécutions simultanées du même agent) et refait jusqu'à 3 tentatives de `git pull --rebase` + `git push` en cas de conflit de commit.

## Maintien

Le workflow `.github/workflows/maintien.yml` tourne chaque lundi (et à la main).
- Il vérifie que les workflows planifiés sont actifs et réactive ceux que GitHub a mis en pause pour inactivité. Un workflow désactivé à la main est seulement signalé.
- Si le dépôt n'a reçu aucun commit depuis 30 jours, il fait un commit léger (`.github/maintien.txt`), pour éviter la mise en pause automatique des workflows planifiés.

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
js/sante.js           écran « Santé des agents »
js/planning.js        planning cron des agents : statut (OK, en pause, en retard, en panne)
js/macro.js           écran « Vue macro » et rubrique « Agent macro » de la fiche pays
js/pepites.js         écran « Pépites »
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
data/recap/           récapitulatif de chaque exécution de l'agent pays
data/journal/         journal des sources en échec
data/flux.json        flux de capitaux entre pays (fictifs)
data/*.json           autres données (fictives pour l'instant)
agents/               agents Python (agents/commun : téléchargement, cache, journal, écriture ; agents/pays : agent pays ; agents/marches : agent marchés ; agents/macro : agent macro ; agents/rattrapage : relance des exécutions manquées)
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
| `marches.json` | agent marchés | cours réels : indices, devises, matières premières, Bitcoin |
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

Le bloc `detail` contient `devise_3m`, `solde_courant` et `flux_etrangers`. `marches.json` donne pour chaque cotation `symbole`, `valeur`, `variation` (jour, en %), `variation_1an`, `heure` (UTC), `statut` (« ouvert » ou « fermé »), `source` et `ancienne`.

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
