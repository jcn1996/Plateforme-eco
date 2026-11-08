# Salle de contrôle — plateforme de suivi économique mondial

Prototype d'une application personnelle de suivi économique mondial, pensée d'abord pour le téléphone.
**Les données des pays sont réelles** : elles sont produites chaque jour par l'**agent pays** (instituts statistiques nationaux, banques centrales, FMI, OCDE, BRI, Banque mondiale, Eurostat, BCE, Yahoo Finance, avec vérification croisée), qui tourne gratuitement avec GitHub Actions.
**Les cours du bandeau des marchés sont réels** : l'**agent marchés** (sans IA) les met à jour toutes les 15 minutes en semaine.
**Les secteurs et les entreprises sont réels** (agent entreprises). **Les flux d'investissement sont réels** : flux des ETF pays cotés aux États-Unis, relevés chaque soir chez les émetteurs (agent pays). **Les alertes du jour sont réelles** : le **chef d'orchestre** retient les signaux les plus importants de tous les agents. Le **portefeuille démo** est géré par l'**agent trader** : 100 000 € virtuels investis selon les recommandations du chef d'orchestre, aux cours réels, pour mesurer ce que vaut la plateforme (aucun ordre réel).

## Ce que fait le prototype

- **Globe 100 % vectoriel** (aucune image), net à tous les niveaux de zoom.
  - L'océan est une sphère bleu nuit unie.
  - Tous les pays sont des polygones 3D opaques :
    - pays suivis en couleur pleine selon leur note : vert émeraude, ambre ou rouge corail ;
    - pays non suivis en gris bleu ;
    - le pays sélectionné est éclairci.
  - Les frontières forment un seul trait jaune clair de 0,7 px (1,5 px autour du pays sélectionné).
  - Côtes et frontières détaillées : Natural Earth au 1:110m au démarrage, puis au 1:50m quand on zoome de près (chargé à la demande).
- **Flux d'investissement** (filtre « Flux d'investissement » du globe, agent pays) : flux nets de l'ETF pays coté aux États-Unis (EWJ, EWY, EWZ, INDA, MCHI, EWG, EWQ, ARGT, VNM, COLO… ; SPY pour les États-Unis).
  - Couleur selon les flux nets en % de l'encours de l'ETF : vert = entrées, rouge = sorties, intensité selon l'ampleur.
  - Sélecteur 1 semaine / 1 mois / 3 mois à côté des filtres ; une période dont l'historique est trop court apparaît « en constitution ».
  - Ces flux ne couvrent que les ETF cotés aux États-Unis.
- **Pulsations des flux d'investissement**, visibles sur la vue par défaut du globe (`js/pulsations.js`) :
  - entrées nettes : halo vert qui s'étend ; sorties nettes : halo rouge qui se contracte vers le centre ;
  - amplitude et vitesse proportionnelles aux flux nets en % de l'encours de l'ETF, sur la période du filtre « Flux d'investissement » (1 semaine tant que la période choisie est en cours de constitution) ;
  - seuil minimal (0,3 % sur une semaine, 0,75 % sur un mois, 1,5 % sur 3 mois) et seulement les 10 flux les plus marqués, pour garder le globe lisible ;
  - toucher un halo affiche une bulle (montant, % de l'encours, période, date) avec un bouton vers la fiche ;
  - bouton « Flux ETF » pour les masquer (choix mémorisé) ; légende « Flux d'investissement (ETF) », avec le nombre de pays encore en cours de constitution ;
  - désactivées en mode ⚡ et quand l'appareil demande de réduire les animations ; tant qu'elles sont actives, l'anneau habituel des pays reste immobile, pour ne pas les confondre.
- **Bandeau des marchés** (cours réels, différés d'environ 15 min) : Nasdaq 100, S&P 500, Or, Pétrole WTI, Bitcoin, EUR/USD, CAC 40, MSCI World (ETF URTH).
  - Chaque cotation porte une pastille « ouvert » ou « fermé ».
  - Il défile tout seul, se glisse au doigt ou à la souris avec inertie, et se met en pause au toucher (reprise 4 s après le relâchement) ou au survol.
  - Toucher une cotation affiche son cours, sa variation du jour, sa variation sur 1 an, l'heure du cours et la source.
- **Graphiques interactifs TradingView** (widgets gratuits et officiels, sans compte ni clé) :
  - fiche entreprise : graphique avancé sous les indicateurs clés (bougies, période de 1 jour à 5 ans, moyennes mobiles 50 et 200 jours, volume) ;
  - bandeau des marchés : la bulle d'une cotation propose « Voir le graphique ». Pour les indices, même ordre de tentative que les fiches pays (`INDICES_BANDEAU`) : CAC 40 = EURONEXT:PX1 ; S&P 500 et Nasdaq 100 = CFD OANDA (les symboles officiels et TVC sont refusés par le widget gratuit). Les autres cotations affichent l'actif pendant les heures de marché, son contrat à terme en dehors ;
  - fiche pays : graphique de l'**indice national de référence** (CAC 40, Nikkei 225, Ibovespa…). Ordre de tentative, vérifié pays par pays sur téléphone simulé et enregistré dans `INDICES_PAYS` (`js/symboles-tradingview.js`) : a) l'indice officiel sur sa place (EURONEXT:PX1, XETR:DAX, BMFBOVESPA:IBOV…) ; b) la version TradingView de l'indice (TVC:, INDEX: — INDEX:NKY pour le Nikkei) ; c) un CFD équivalent accepté (S&P 500, FTSE 100, ASX 200), avec la mention « graphique : équivalent CFD de l'indice » ; d) un graphique simplifié tracé avec l'historique Yahoo de l'indice (KOSPI, Nifty 50, JSE Top 40, BIST 100). Si Yahoo ne publie pas non plus d'historique utilisable (TASI, ADX, SET, VN-Index, Merval en ce moment), l'ETF pays est affiché avec la mention « indice indisponible, ETF affiché » ;
  - écrans Pépites et « Mes analyses » : mini-graphique sur 12 mois dans chaque fiche.

  Réglages : thème sombre, français, fuseau Europe/Paris, hauteur adaptée au téléphone. Le script de TradingView n'est chargé qu'à l'affichage d'un graphique, jamais au démarrage, et le service worker ne le met pas en cache.
  La correspondance des symboles Yahoo → TradingView se complète dans [`js/symboles-tradingview.js`](js/symboles-tradingview.js) (exceptions manuelles, places, symboles refusés par le widget gratuit).
  Quand le widget gratuit n'affiche pas un symbole (Nasdaq 100, S&P 500, contrats à terme…), et toujours en mode ⚡, un graphique simple est tracé avec [Lightweight Charts](https://github.com/tradingview/lightweight-charts) à partir des cours de nos agents (`data/cours/`, fiches des entreprises), avec un lien « Ouvrir sur TradingView ».
- **Indicateurs des pays** (6, données réelles) :
  - croissance du PIB (FMI) ;
  - indicateur avancé (OCDE, au-dessus de 100 = accélération) ;
  - inflation, avec la cible de la banque centrale ;
  - taux réel (taux directeur de la BIS moins l'inflation), avec la direction de la banque centrale ;
  - valorisation relative (PER de l'ETF pays comparé à la médiane des pays suivis) ;
  - momentum boursier sur 12 mois : indice national en monnaie locale, avec à côté la performance convertie en euros et l'effet de change ; à défaut d'historique de l'indice chez Yahoo, l'ETF pays (« indice indisponible, ETF affiché »).

  L'indice de référence de chaque pays et son symbole Yahoo se modifient dans [`config/indices_pays.json`](config/indices_pays.json). La valorisation relative reste calculée avec le PER de l'ETF pays (le PER des indices n'est pas disponible gratuitement), source indiquée sous la valeur. Les ETF pays ne sont plus affichés comme référence de la fiche pays : ils n'apparaissent que dans le bloc « Flux d'investissement ».

  La devise sur 3 mois, le solde courant et les flux étrangers (flux de l'ETF pays, note /100 et tendance) sont dans la section repliable « Détail ».
  Chaque fiche pays affiche aussi :
  - le bloc « Flux d'investissement » : flux nets sur 1 semaine, 1 mois et 3 mois (M$ et % de l'encours), série de jours consécutifs d'entrées ou de sorties, petit graphique des flux cumulés, source et date ;
  - le niveau de confiance de l'agent ;
  - la rubrique « Ce qui pourrait me donner tort » ;
  - la lecture de l'agent ;
  - les sources et les dates exactes de chaque valeur.
- **Tendances** : une flèche ↑ ↓ → indique l'évolution depuis la mise à jour précédente, sur chaque indicateur et chaque note (pays, secteur, entreprise). Le vert signale une note qui s'améliore, le rouge une note qui se dégrade.
- **En-tête et Menu** : sur téléphone et tablette, l'en-tête ne garde que le titre, la pastille du palier de risque, la recherche, le portefeuille démo (avec sa performance) et le bouton **Menu**. Le Menu ouvre un panneau qui regroupe tous les écrans, classés : *Synthèse* (Où investir, Briefing), *Analyses* (Vue macro, Pays · Classement, Pépites, Matières premières, Géopolitique, Risque, Initiés, Données alternatives), *Outils* (Analyser une entreprise, Mes analyses, Comparateur, Mes alertes), *Suivi* (Portefeuille démo, Fiabilité, Santé des agents) et *Affichage* (Légende des couleurs, Mode léger). Une pastille rouge sur « Menu » signale un problème dans la santé des agents. Sur grand écran (à partir de 1 280 px), des raccourcis supplémentaires s'ajoutent à l'en-tête (icônes, libellé au survol), mais tout reste accessible par le Menu. Les bandeaux et onglets qui défilent horizontalement se font glisser au doigt.
- **Recherche** (loupe dans l'en-tête) : pays, secteurs et entreprises, par nom ou ticker, sans tenir compte des accents. Toucher un résultat ouvre la fiche et centre le globe.
- **Fraîcheur des données** : sous chaque fiche, « Mis à jour le … · Source : … », lu dans le bloc `meta` des JSON.
- **Filtres du globe** (puces en bas de l'écran) : la note globale, les 6 indicateurs des pays, les flux d'investissement et les risques.
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
- **Panneau « Synthèse »** (chef d'orchestre), repliable en bas du globe : palier de risque, phase du cycle, top 3 « Où investir », alertes du jour ; le déplier donne accès au briefing complet.
- **Écran « Où investir »** (bouton boussole de l'en-tête) et filtre du globe **« Attractivité »** : voir la section « Chef d'orchestre » plus bas.
- **Mes alertes**, accessible depuis le panneau « Synthèse » : règles personnelles vérifiées à chaque chargement des données.
  - Les alertes déclenchées apparaissent en tête du bandeau, avec le badge « Mon alerte ».
- **Classement** des pays et des 20 meilleures entreprises.
- **Portefeuille démo** de 100 000 €.
- **Netteté** : antialiasing, densité de pixels jusqu'à 3 sur les écrans haute résolution.
- **Mode léger** (⚡) : densité de pixels limitée à 2, sans halo, 30 images/s ; graphiques simples à la place des widgets TradingView.
- **PWA** : l'appli s'installe sur l'écran d'accueil. Le service worker charge l'appli « réseau d'abord », donc la dernière version s'affiche dès l'ouverture ; elle reste utilisable hors ligne.

## Agent pays (données réelles)

L'agent pays se trouve dans `agents/`, en Python 3.12.
- Il interroge des sources gratuites : instituts statistiques nationaux (INSEE, Destatis, ONS, BLS, Japon, IBGE, Statistique Canada, via DBnomics ou leur banque centrale), BCE, FMI, OCDE, BRI, Banque mondiale, Eurostat et Yahoo Finance.
- **Vérification croisée** : chaque indicateur est récupéré auprès de plusieurs sources quand c'est possible. L'ordre de priorité est le suivant : source nationale officielle, puis organisation internationale, puis source de marché. Si deux sources s'écartent trop, l'indicateur est marqué « sources divergentes » et la confiance baisse. Une valeur aberrante ou trop ancienne est rejetée. Tout est décrit dans [`agents/pays/sources.md`](agents/pays/sources.md).
- Il note chaque indicateur sur 100, puis calcule une note globale pondérée et un niveau de confiance.
- Il écrit des textes factuels et met à jour `data/pays.json`.
- Les règles de notation et de conduite sont décrites dans [`agents/pays/regles.md`](agents/pays/regles.md). Les pondérations se modifient dans `agents/pays/config.json`.

**Exécution** : le workflow `.github/workflows/agent-pays.yml` lance l'agent chaque jour à 6 h 11 UTC, et en mode « flux » du mardi au samedi à 2 h 07 UTC (soirée à New York) ; on peut aussi le lancer à la main.
- Il commite sur `main` avec le message « Agent pays : mise à jour du JJ/MM/AAAA ». Même quand les données n'ont pas changé, la date de dernière exécution est enregistrée dans son journal (pour l'écran « Santé des agents »).
- Chaque jour, il garde ses notes dans `data/historique/pays/AAAA-MM-JJ.json`.
- Il écrit un récapitulatif factuel dans `data/recap/pays-AAAA-MM-JJ.md` : ce qui a changé, les divergences entre sources, les données manquantes et les mouvements de notes.
- Il tient le journal des sources en échec dans `data/journal/agent-pays.json`.

**Flux d'investissement des ETF pays** (indicateur « Flux étrangers », `agents/pays/flux_etf.py`) :
- pour chaque pays, l'ETF pays déjà utilisé pour la valorisation (et pour le momentum quand l'indice national n'a pas d'historique) (SPY pour les États-Unis ; l'Égypte n'a plus d'ETF coté aux États-Unis depuis la liquidation de VanEck EGPT en 2024) ;
- flux du jour = variation du nombre de parts en circulation × valeur liquidative (VL) du jour ;
- sources : l'émetteur (page du fonds iShares et Global X ; fichier des VL quotidiennes de SSGA et VanEck), Yahoo Finance (yfinance) en secours. Quand les deux répondent pour la même date, les parts sont comparées (tolérance 2 %) : « concordant » ou « sources divergentes ». Un relevé dont parts × VL s'écarte de l'actif net publié est rejeté ;
- historique jour par jour dans `data/historique/flux_etf/AAAA-MM-JJ.json` (date de la VL). Il n'existe pas d'historique gratuit des parts pour la plupart des ETF : l'agent l'accumule depuis sa mise en service. Seuls SSGA (SPY) et VanEck (VNM) publient un historique, qui sert à remplir les 100 derniers jours. Tant que l'historique ne remonte pas au début d'une période, ses cumuls sont « en cours de constitution » ;
- indicateurs : flux nets sur 1 semaine, 1 mois et 3 mois en M$ et en % de l'encours, série de jours consécutifs d'entrées ou de sorties, note /100 et tendance (règles dans `regles.md`) ;
- prudence : un afflux très fort par rapport aux semaines précédentes est signalé « position possiblement encombrée » (note plafonnée à 60) ; l'agent rappelle toujours que les flux ne couvrent que les ETF cotés aux États-Unis ;
- signaux pour le futur chef d'orchestre dans `data/signaux/pays.json` : inversion de tendance des flux, entrées ou sorties inhabituelles ;
- mise à jour une fois par jour, en soirée à New York après la publication des émetteurs (`python -m agents.pays --mode flux`, lancé par le planificateur) ; l'exécution complète du matin les recalcule aussi.

**Pannes de source** : si une source ne répond pas, l'agent ne s'arrête pas. Il garde la dernière valeur connue avec sa date et la signale comme « ancienne ». Si plus d'un tiers des sources d'un pays échouent, l'appli affiche une alerte « Qualité des données » sur la fiche du pays et en tête du bandeau des alertes.

**Textes** : par défaut, ils sont rédigés par des règles. Si le secret GitHub `GEMINI_API_KEY` est créé (Settings → Secrets and variables → Actions), l'API gratuite Gemini les rédige, sous les mêmes contraintes. Un texte non conforme est remplacé par la version par règles.

**BLS (facultatif)** : l'inflation américaine vient aussi de l'API publique du BLS (version 1, sans clé, limitée à 25 requêtes par jour et par adresse IP). Avec le secret GitHub `BLS_API_KEY` (clé gratuite sur data.bls.gov), l'agent utilise la version 2, plus généreuse.

**FRED (facultatif)** : avec le secret GitHub `FRED_API_KEY` (clé gratuite sur fred.stlouisfed.org), l'agent ajoute l'inflation et le taux de la Réserve fédérale publiés par FRED. Sans ce secret, il s'en passe.

Pour lancer l'agent sur un ordinateur :

```
pip install -r agents/requirements.txt
python -m agents.pays                 # vraies sources
python -m agents.pays --mode flux     # flux des ETF pays seulement
python -m agents.pays --test          # données de test, sans réseau
python -m unittest discover -s agents/pays -t .   # tests de l'agent
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

## Agent géopolitique (événements, avec Gemini sous quotas gratuits)

L'agent suit les événements géopolitiques et leur impact possible sur les marchés. Il tourne toutes les heures.

**Sources** : GDELT (fichiers d'événements géolocalisés publiés toutes les 15 minutes ; API DOC 2.0 en source secondaire), Google Actualités par thème, Federal Register, OFAC, flux officiels (Maison-Blanche, Élysée, Commission européenne, Conseil de l'UE, BRI), presse internationale (RSS), indice de risque géopolitique de Caldara et Iacoviello, indice d'incertitude de politique économique (FRED). Pas de réseaux sociaux.

**Analyse** :
- les articles sont regroupés par événement ;
- les événements significatifs sont analysés par Gemini (secret `GEMINI_API_KEY`, modèle réglable dans `agents/geopolitique/config.json`). L'agent produit un résumé, les pays, la catégorie, la gravité de 1 à 5, les actifs touchés et le sens de l'impact, l'horizon, la confiance et « Ce qui pourrait me donner tort » ;
- chaque affirmation doit citer une source fournie à Gemini, sinon elle est supprimée ;
- une gravité de 4 ou 5 exige 2 sources indépendantes ;
- les quotas gratuits sont respectés, avec une chaîne de modèles (Flash le plus récent, Flash-Lite, Flash précédent) et des limites par modèle avec une marge de 20 %. Ces limites sont à confirmer dans AI Studio : l'agent apprend aussi la vraie limite des réponses 429. Les reprises suivent une attente progressive (503) et les gravités 3 et plus passent en priorité ;
- les doublons sont fusionnés, seuls les pays acteurs ou directement touchés sont retenus, et tous les résumés sont en français ;
- sans Gemini, l'agent publie une version sans IA, signalée dans l'appli.

**Score** : un score de risque /100 par pays suivi, avec sa variation sur 7 jours.

Détails : [`agents/geopolitique/regles.md`](agents/geopolitique/regles.md).

**Sorties** :
- `data/geopolitique.json` ;
- `data/signaux/geopolitique.json` : signaux pour le chef d'orchestre et le futur agent risque ;
- `data/historique/geopolitique/AAAA-MM-JJ.json` ;
- `data/recap/geopolitique-AAAA-MM-JJ.md` : synthèse du jour, à 6 h UTC ;
- `data/geopolitique/etat.json` : événements suivis, cache, quota ;
- `data/journal/agent-geopolitique.json`.

**Appli** :
- bouton « Géopolitique » dans l'en-tête ;
- filtre du globe « Risque géopolitique » (rouge = risque élevé) ;
- rubrique « Géopolitique » dans la fiche pays.

**Exécution** : le workflow `.github/workflows/agent-geopolitique.yml` est lancé chaque heure (minute 3) par le planificateur. Ses plannings GitHub restent en secours. Le créneau de 6 h 03 UTC est en mode « quotidien », pour la synthèse.

```
python -m agents.geopolitique                     # vraies sources (Gemini si GEMINI_API_KEY existe)
python -m agents.geopolitique --mode quotidien    # écrit aussi la synthèse du jour
python -m agents.geopolitique --test --data /tmp/essai   # données de test, sans réseau ni Gemini
python -m agents.geopolitique.tests.capturer_donnees_test # met à jour les données de test
```

**Essai d'une correction** : onglet **Actions** → **Agent géopolitique** → **Run workflow**, choisir la branche et cocher « essai ». Le code de la branche tourne alors sur une copie des données de `main`, avec les vrais secrets, sans rien commiter. Le statut santé est affiché à la fin du journal.

## Agent risque (stress financier et contradicteur)

L'agent mesure le stress financier mondial et par pays, et joue le rôle de **contradicteur** des signaux des autres agents. Il tourne toutes les heures pendant les heures de marché, et fait une analyse complète chaque jour à 22 h 45 UTC.

**Sources** (gratuites, croisées quand c'est possible) :
- volatilité : VIX (vérifié avec FRED `VIXCLS`), VSTOXX (si Yahoo le publie), indice MOVE ;
- crédit : écarts high yield et investment grade américains, high yield européen (FRED) ;
- indices officiels de stress : STLFSI4 et NFCI (FRED), CISS de la BCE ;
- écarts souverains : taux à 10 ans de l'OCDE via FRED, vérifiés avec la BCE pour la zone euro ;
- devises : volatilité à 1 mois et variation sur 3 mois des devises suivies par l'agent pays ; indice dollar (vérifié avec FRED `DTWEXBGS`) ;
- vulnérabilité : dette publique / PIB, solde courant et inflation (FMI ; inflation de l'agent pays en priorité), réserves de change (Banque mondiale) ;
- géopolitique : score par pays de `data/geopolitique.json` ;
- marchés : baisse depuis le plus haut sur 12 mois et volatilité des ETF pays ; corrélations à 3 mois entre actions, obligations, or et dollar.

**Analyse** :
- score mondial /100 : moyenne pondérée des percentiles des indicateurs sur 10 ans (pondérations dans `agents/risque/config.json`) ;
- 4 paliers : « Calme », « Vigilance », « Tension », « Crise ». Les seuils sont calés sur les percentiles 60, 85 et 97 du score sur 10 ans ;
- il faut deux familles d'indicateurs concordantes pour changer de palier ; sinon le changement est affiché « en attente » ;
- l'appli affiche le palier précédent, la date du changement et les 3 indicateurs qui pèsent le plus ;
- score /100 par pays (marché, devise, souverain, vulnérabilité macro, géopolitique), avec sa variation sur 7 jours et un texte de deux phrases.

**Contradicteur** : à chaque exécution, il lit `data/signaux/*.json` et n'examine que les signaux **encore valides** : importance moyenne ou forte, moins de 7 jours, toujours présents dans les données de l'agent émetteur (pépite toujours dans la liste, alerte toujours dans la fiche, phase toujours en cours, événement toujours suivi). Les revues des autres signaux sont retirées de `data/signaux/revues.json`.

Chaque objection est **propre au signal** :
- pour une entreprise, ses risques : valorisation, dette, cours, qualité du bénéfice, devise, risque pays, sensibilité du secteur, signaux d'alerte ;
- pour un pays, ses vulnérabilités ;
- pour une zone, la robustesse du changement de phase.

Le contexte mondial tient en une phrase au plus. Sans objection spécifique, la revue l'indique : « Pas d'objection spécifique ».

L'ajustement proposé est « maintenir », « abaisser » ou « signal fragile ». Les objections sont rédigées par règles, ou par Gemini avec un budget d'appels propre à l'agent risque. Une réponse de Gemini qui cite un chiffre absent des faits est rejetée.

Détails : [`agents/risque/regles.md`](agents/risque/regles.md).

**Sorties** :
- `data/risque.json` ;
- `data/signaux/risque.json` : changement de palier, écart de crédit en forte hausse, devise en décrochage, rupture de corrélation ;
- `data/signaux/revues.json` : objections du contradicteur ;
- `data/historique/risque/AAAA-MM-JJ.json` ;
- `data/recap/risque-AAAA-MM-JJ.md` : récapitulatif de l'analyse complète ;
- `data/risque/etat.json` : séries des sources lentes, palier, historique, budget Gemini ;
- `data/journal/agent-risque.json` : écran « Santé ».

**Appli** :
- pastille permanente du palier dans l'en-tête, qui ouvre l'écran « Risque ». Cet écran affiche la jauge, le palier et l'explication (faits et interprétations), la confiance, « Ce qui pourrait me donner tort », les indicateurs (valeur, percentile, tendance), le graphique sur 12 mois, les pays les plus à risque et les dernières objections ;
- filtre du globe « Risque » ;
- rubrique « Agent risque » dans la fiche pays, avec la décomposition du score.

**Exécution** : le workflow `.github/workflows/agent-risque.yml` est lancé par le planificateur. Il tourne toutes les heures à la minute 17, de 7 h à 21 h UTC en semaine (mode « horaire » : marchés, score, signaux, objections), et à 22 h 45 UTC (mode « complet » : toutes les sources et le récapitulatif). Le workflow ne lance que ses propres tests et ceux du module commun.

```
python -m agents.risque                      # vraies sources (Gemini si GEMINI_API_KEY existe)
python -m agents.risque --mode complet       # toutes les sources et récapitulatif du jour
python -m agents.risque --test --data /tmp/essai   # données de test, sans réseau ni Gemini
python -m agents.risque.tests.capturer_donnees_test # met à jour les données de test
```

## Agent matières premières (sans IA)

L'agent dit s'il est pertinent de s'exposer à chaque grande matière première sur un horizon de 3 à 12 mois : « Surpondérer », « Neutre » ou « Sous-pondérer ». Il tourne en semaine à 22 h 15 UTC.

**Périmètre** : or, argent, platine, palladium ; cuivre, aluminium, uranium (ETF URA, « indicateur indirect ») ; pétrole WTI et Brent, gaz naturel américain, gaz européen TTF ; blé, maïs, soja, café, sucre, cacao, coton.

**Sources** (gratuites, croisées quand c'est possible) :
- Yahoo Finance : cours sur 10 ans et courbe des prix à terme (contrat le plus proche et 8 échéances suivantes, ex. `CLZ26.NYM`, `CLF27.NYM`) : contango ou backwardation, rendement de roulement ;
- CFTC, Commitments of Traders (API Socrata, sans clé) : position nette des « managed money » et son percentile sur 3 ans ;
- EIA (secret facultatif `EIA_API_KEY`, voir ci-dessous) : stocks hebdomadaires de brut, Cushing, essence, distillats et gaz, comparés à la moyenne sur 5 ans ;
- USDA : rapport WASDE et base PSD (comparés entre eux) : ratio stocks / consommation mondiale du blé, du maïs et du soja ;
- FRED : taux réel à 10 ans (DFII10), dollar (DTWEXBGS), inflation (CPIAUCSL, pour le niveau corrigé de l'inflation) ;
- autres agents : indicateur avancé de l'OCDE et phase du cycle (`data/macro.json`), événements (`data/geopolitique.json`), palier de risque (`data/risque.json`), sociétés productrices (`data/entreprises.json`) ;
- flux des ETF GLD, IAU, SLV, USO, CPER et DBA (variation des parts × VL, méthode des ETF pays ; historique accumulé, « en cours de constitution » le premier mois).

**Analyse** : 8 sous-notes /100 (tendance et momentum, courbe, stocks, positionnement lu à contre-courant aux extrêmes, moteurs macro, géopolitique, flux des ETF, niveau historique), note globale pondérée par famille (`agents/matieres_premieres/config.json`), verdict avec deux signaux concordants au minimum et une confiance « moyen » ou « élevé » (sinon « Neutre (biais positif) » ou « Neutre (biais négatif) », raison affichée dans la fiche ; règle contrôlée sur toutes les matières premières avant chaque écriture), confiance, 3 arguments pour, 3 contre, « Ce qui pourrait me donner tort » et 2 conditions d'invalidation. Synthèse par famille. Moyens de s'exposer (ETC physique, ETF de contrats à terme avec le coût du contango, producteurs analysés par l'agent entreprises, double exposition signalée). Détails : [`agents/matieres_premieres/regles.md`](agents/matieres_premieres/regles.md).

**Sorties** :
- `data/matieres_premieres.json` ;
- `data/signaux/matieres_premieres.json` : changement de verdict, positionnement extrême, retournement de la courbe, choc de stocks (lus par le contradicteur de l'agent risque) ;
- `data/historique/matieres_premieres/AAAA-MM-JJ.json` : notes du jour et relevés des ETF ;
- `data/recap/matieres-premieres-AAAA-MM-JJ.md` ;
- `data/journal/agent-matieres-premieres.json` : écran « Santé ».

**Appli** : bouton « Matières » dans l'en-tête → écran « Matières premières » (synthèse par famille, une ligne par matière première avec cours, variations, mini-graphique, note, verdict et confiance) ; toucher une ligne ouvre sa fiche (sous-notes, courbe des prix à terme, positionnement CFTC, stocks, arguments, moyens de s'exposer, sources et dates). Le bouton « Voir les pays producteurs » met en surbrillance sur le globe les principaux producteurs parmi les pays suivis (liste statique dans la configuration) ; la puce « Producteurs : … ✕ » revient au filtre choisi.

**Clé EIA (facultative, gratuite)** : sans elle, les stocks de pétrole et de gaz ne sont pas notés (source « non configurée » dans l'écran Santé, sans alerte).
1. Demander une clé sur [eia.gov/opendata/register.php](https://www.eia.gov/opendata/register.php) (nom et adresse e-mail) ; elle arrive par e-mail en quelques minutes.
2. Dans le dépôt GitHub : **Settings** → **Secrets and variables** → **Actions** → **New repository secret** ; nom `EIA_API_KEY`, valeur : la clé reçue.
3. Elle est utilisée dès l'exécution suivante (ou onglet **Actions** → **Agent matières premières** → **Run workflow**).

**Exécution** : `.github/workflows/agent-matieres-premieres.yml`, lancé par le planificateur, en semaine à 22 h 15 UTC. Les publications hebdomadaires (EIA le mercredi, gaz le jeudi, CFTC le vendredi soir) et mensuelles (WASDE) sont prises en compte à l'exécution qui suit leur parution ; le récapitulatif indique les nouvelles. Le workflow ne lance que ses propres tests et ceux du module commun.

```
python -m agents.matieres_premieres                       # vraies sources (EIA si EIA_API_KEY existe)
python -m agents.matieres_premieres --test --data /tmp/essai   # données de test, sans réseau
python -m agents.matieres_premieres --capturer --data /tmp/essai   # met à jour les données de test
```

## Agent données alternatives (sans IA)

L'activité réelle avant les statistiques officielles, à partir d'indicateurs indirects gratuits. Aucune conclusion sur un seul indicateur.

**Indicateurs** (`agents/donnees_alternatives/config.json`) :
- transport : kilomètres parcourus par les poids lourds sur les autoroutes allemandes (Destatis, indice quotidien Lkw-Maut) ; tonnage du transport routier américain (FRED) ; fret vrac sec (ETF BDRY, approximation de l'indice Baltic Dry, non diffusé gratuitement) ; fret conteneurs (Drewry WCI, page publique hebdomadaire, historique accumulé par l'agent) ;
- construction : ciment en Chine (API du Bureau national des statistiques, data.stats.gov.cn ; DBnomics en secours, date de la dernière donnée affichée) et aux États-Unis (USGS, rapports mensuels) ; mises en chantier (FRED) ;
- commerce : exportations mensuelles de la Corée (FRED, secours OMC via DBnomics) et de Taïwan (CSV ouvert des douanes, secours OMC), avec la mention « mensuel, pas de donnée anticipée gratuite » ; en option, CSV externes pour les exportations coréennes des 20 premiers jours et les commandes à l'export de Taïwan (variables `COREE_EXPORTS_20J_URL`, `TAIWAN_COMMANDES_URL`) ;
- énergie : électricité en Chine (NBS, secours DBnomics), en Europe (ENTSO-E, clé `ENTSOE_API_KEY`), aux États-Unis (EIA, clé `EIA_API_KEY`) ;
- emploi : offres d'emploi Indeed Hiring Lab (9 pays, dépôt public GitHub) ; mobilité : passagers TSA ;
- satellites : NO2 (Sentinel-5P) et lumières nocturnes (Black Marble) — **désactivés par défaut** (`"actif": false` dans la configuration) ; une fois réactivés, CSV mensuel (variable `SATELLITES_URL`, script `outils/satellites_gee.js` pour Google Earth Engine) ;
- attention du public : Wikipédia et Google Trends (pytrends, non officiel, échec toléré) pour la liste de surveillance et les pépites — information seulement, hors score.

**Analyse** : par indicateur, dernière valeur, variations sur 1 et 12 mois, écart à la tendance et à la normale saisonnière, percentile historique, note /100. Par pays (au moins 2 indicateurs à jour) : score /100, lecture « accélération », « stable » ou « ralentissement » (deux indicateurs concordants exigés), confiance, « Ce qui pourrait me donner tort », divergence avec les statistiques officielles de l'agent pays. Détails : [`agents/donnees_alternatives/regles.md`](agents/donnees_alternatives/regles.md).

**Sorties** : `data/donnees_alternatives.json` ; `data/signaux/donnees_alternatives.json` (accélération ou ralentissement marqué, divergence avec l'officiel, attention en forte hausse) pour le chef d'orchestre ; `data/historique/donnees_alternatives/` ; `data/recap/donnees-alternatives-AAAA-MM-JJ.md` ; `data/journal/agent-donnees-alternatives.json` (écran « Santé »). L'agent pays reprend le score comme sous-note « Activité réelle » (pondération 0,10, seulement pour les pays qui en ont un).

**Appli** : bouton « Données alternatives » en haut de l'écran « Vue macro » (tableau de bord mondial, activité par pays, attention du public) ; bloc « Activité réelle » de la fiche pays ; filtre du globe « Activité réelle ».

**Clés et adresses facultatives** (sans elles, la source est ignorée, sans alerte) : dans **Settings** → **Secrets and variables** → **Actions** :
- secret `ENTSOE_API_KEY` : créer un compte sur [transparency.entsoe.eu](https://transparency.entsoe.eu/), puis écrire à transparency@entsoe.eu (objet « Restful API access », avec l'adresse du compte) ; le jeton apparaît ensuite dans **My Account Settings** → **Web API Security Token** ;
- secret `EIA_API_KEY` : déjà utilisé par l'agent matières premières (voir ci-dessus) ;
- variables (onglet **Variables**) `SATELLITES_URL`, `COREE_EXPORTS_20J_URL`, `TAIWAN_COMMANDES_URL` : adresses de CSV « date,pays,indicateur,valeur ».

**Exécution** : `.github/workflows/agent-donnees-alternatives.yml`, lancé par le planificateur chaque jour à 5 h 40 UTC (avant l'agent pays) ; les publications mensuelles sont prises en compte à l'exécution qui suit leur parution. Le workflow ne lance que ses propres tests et ceux du module commun.

```
python -m agents.donnees_alternatives                          # vraies sources
python -m agents.donnees_alternatives --test --data /tmp/essai  # données de test, sans réseau
python -m agents.donnees_alternatives --capturer --data /tmp/essai   # met à jour les données de test
```

## Agent initiés (sans IA)

L'agent suit les achats des dirigeants, les activistes et les super-investisseurs, comme signal supplémentaire pour l'agent entreprises, et les transactions des élus du Congrès pour information. Règles détaillées : [`agents/inities/regles.md`](agents/inities/regles.md).

**Sources** (gratuites) :
- dirigeants : formulaires 4 de la SEC (index quotidien EDGAR ; secret `SEC_USER_AGENT`, déjà utilisé par l'agent entreprises), déclarations des dirigeants de l'AMF (base BDIF) et de la BaFin ; pas de source gratuite exploitable pour le Royaume-Uni ;
- activistes : formulaires 13D (EDGAR) ;
- super-investisseurs : rapports 13F (EDGAR) des investisseurs de `config/super_investisseurs.json` (CIK vérifiés ; Scion ne dépose plus de 13F depuis fin 2025, signalé), tickers par OpenFIGI ; hors États-Unis, recherche par nom d'entité (rattrapage progressif de l'historique, journal de ce qui a été cherché et trouvé) : NSE (Inde : déclarations SAST et actionnaires de plus de 1 %), DART (Corée, `DART_API_KEY` facultatif), EDINET (Japon, `EDINET_API_KEY` facultatif), KAP (Turquie, source secondaire), AMF ;
- élus : déclarations de transactions de la Chambre (index et PDF du greffe) ; Sénat désactivé par défaut (le site impose d'accepter ses conditions d'utilisation : `elus.senat_actif` dans `agents/inities/config.json`).

**Analyse** : achats sur le marché seulement (code P ; exercices d'options, donations et opérations programmées 10b5-1 exclus) ; score « achats d'initiés » /100 par société (achat opportuniste plutôt que routinier, achats groupés sur 30 jours, fonction, montant par rapport à ce que le dirigeant détient déjà, taille de la société) ; ventes massives et groupées (seul cas négatif) ; pour chaque super-investisseur, nouvelles positions, renforcements, allègements et principales positions ; signal « conviction des super-investisseurs » /100 par société.

**Intégration** : les deux signaux « Achats d'initiés » et « Super-investisseurs » entrent dans la recommandation de l'agent entreprises avec une pondération modérée (0,5 chacun dans la règle des 3 signaux concordants, section `recommandation.inities` de `agents/entreprises/config.json`). Signaux pour le chef d'orchestre : achats groupés de dirigeants, nouvelle position d'un super-investisseur, nouveau 13D.

**Sorties** :
- `data/inities.json` (lu par l'appli et par l'agent entreprises) ;
- `data/signaux/inities.json` ;
- `data/inities/etat.json` : dépôts déjà lus, file d'attente, historique des achats, derniers 13F, tickers des CUSIP ;
- `data/historique/inities/AAAA-MM-JJ.json` : scores du jour ;
- `data/recap/inities-AAAA-MM-JJ.md` ;
- `data/journal/agent-inities.json` : écran « Santé ».

**Appli** : bouton « Initiés » dans l'en-tête → écran « Initiés » avec quatre onglets : « Dirigeants » (scores, achats récents, ventes massives), « Super-investisseurs » (une page par investisseur : dernières opérations, principales positions, positions hors États-Unis ; conviction par société), « Activistes » (13D), « Élus » (opération, déclaration, retard). La fiche entreprise affiche un bloc « Initiés » (achats récents des dirigeants, super-investisseurs présents, 13D éventuel).

**Exécution** : `.github/workflows/agent-inities.yml`, lancé par le planificateur : du mardi au samedi à 6 h 35 UTC (mode « complet » : formulaires 4, 13D, AMF, BaFin de la veille, 13F, élus) ; dimanche et lundi (mode « leger » : 13F et élus). Le workflow ne lance que ses propres tests et ceux du module commun.

```
python -m agents.inities                                  # vraies sources (EDGAR si SEC_USER_AGENT existe)
python -m agents.inities --mode leger                     # 13F et élus seulement
python -m agents.inities --test --data /tmp/essai         # données de test, sans réseau
```

## Chef d'orchestre (« Où investir maintenant, et avec quelle conviction ? »)

Le chef d'orchestre réunit les sorties de tous les agents. Méthode complète : [`agents/chef/methode.md`](agents/chef/methode.md) ; tous les poids et seuils : [`agents/chef/config.json`](agents/chef/config.json).

**Entrées** : `data/pays.json`, `macro.json`, `marches.json`, `risque.json`, `geopolitique.json`, `matieres_premieres.json`, `entreprises.json` (et fiches), `pepites.json`, `inities.json`, flux des ETF (dans `pays.json`), analyses à la demande, `data/signaux/*.json` et `revues.json` (objections du contradicteur). Chaque entrée est pondérée par sa fraîcheur, la santé de son agent et sa confiance ; une donnée périmée ou d'un agent dégradé pèse moins, et c'est signalé.

**Univers** : actions des 31 pays suivis (avec les 3 meilleures sociétés de chaque pays attractif), les 11 secteurs GICS dans le monde, aux États-Unis, en Europe et dans les émergents (signaux agrégés des sociétés, ETF sectoriels XLK…, iShares Global…, iShares STOXX Europe 600 : momentum et flux, rotation sectorielle selon le cycle, initiés, risque et géopolitique), matières premières, or (à part, valeur refuge), obligations d'État américaines et de la zone euro (courtes et longues), liquidités en dollars et en euros (rendement réel), entreprises (pépites, qualité à prix raisonnable, liste de surveillance, analyses à la demande, meilleures sociétés des pays attractifs).

**Moteur** :
- familles de signaux normalisées (percentiles dans la classe, mélangés à la note absolue de l'agent) : fondamentaux, valorisation, tendance, flux, adéquation au cycle (tableau des phases), risque, géopolitique, initiés, dynamique des résultats ;
- pondérations selon le palier de risque (en « Tension » ou « Crise », le risque et la qualité pèsent plus, le momentum moins ; l'inverse en « Calme ») ;
- score /100 (ramené vers 50 quand les données manquent ou sont peu fiables) et verdict : « Renforcer fortement », « Renforcer », « Neutre », « Alléger », « Éviter » ;
- conviction faible, moyenne ou forte (forte : 3 groupes de signaux indépendants concordants, données fiables et fraîches, aucune objection sérieuse ; chaque objection retenue du contradicteur l'abaisse d'un cran) ;
- anti-girouette : un verdict ne change que si le score franchit le seuil de 3 points ou y reste 2 jours de suite ; chaque changement est expliqué ;
- concentrations thématiques (IA, semi-conducteurs, or, pétrole) signalées ;
- garde-fous : holdings, sociétés d'investissement, fonds fermés, BDC et SPAC exclus (aussi des pépites, et jamais « Acheter » dans l'agent entreprises) ; le risque est un frein, pas un moteur (pas de « Renforcer » sans signal positif de fondamentaux, valorisation, tendance ou flux) ; une hausse passée extrême ne porte jamais seule une conviction forte (vérification de valorisation et de positionnement, objection systématique) ; contrôle de cohérence avant publication (3 familles positives listées pour une conviction forte) ; objections du contradicteur rattachées à la bonne entité.

**Allocation modèle** (indicative) : profils prudent, équilibré et dynamique, cœur-satellite (satellites = convictions fortes), plafonds par pays, secteur, thème et ligne, liquidités minimales selon le palier de risque, rotation limitée (écart minimal de 1,5 point), variations justifiées. Base de l'agent trader démo.

**Synthèse et alertes** :
- briefing quotidien `data/chef/briefing-AAAA-MM-JJ.md` et `.json` : l'essentiel en 5 lignes, « Où investir » (top 5 avec conviction), ce qui a changé depuis hier, points de vigilance, scénarios central et alternatif avec leurs déclencheurs, agenda des 7 prochains jours (banques centrales, résultats des sociétés de la liste de surveillance, EIA, WASDE, grandes statistiques ; dates tirées d'une règle de calendrier marquées « indicatives »). Rédigé par règles ; avec `GEMINI_API_KEY`, Gemini reformule l'essentiel et la vigilance sous contrôle (budget propre ; toute phrase sans fait cité ou avec un chiffre absent des faits est supprimée) ;
- `data/alertes.json` (remplace le fichier fictif) : les 3 ou 4 signaux les plus importants de moins de 48 h, filtrés par les objections du contradicteur ; « Aucune alerte notable » sinon ;
- dépôt facultatif du briefing sur Google Drive : secrets `GOOGLE_SERVICE_ACCOUNT_JSON` (clé JSON d'un compte de service) et `DRIVE_FOLDER_ID` (dossier partagé avec l'adresse du compte de service, en éditeur). Sans eux, le dépôt est ignoré.

**Suivi de performance** : `data/chef/suivi.json` enregistre chaque verdict (date, score, conviction, symbole suivi, prix de référence) et mesure sa performance à 1, 3, 6 et 12 mois contre l'indice de sa classe (MSCI World, indice large des matières premières DBC, obligations AGG ou IEAG) ; taux de réussite par type, verdict et conviction, et calibration (une conviction forte doit réussir plus souvent qu'une faible). Écran « Fiabilité du chef d'orchestre ». Ces résultats alimenteront l'agent calibrateur.

**Sorties** : `data/chef.json`, `data/chef/` (briefings, suivi, état de l'hystérésis et du budget Gemini), `data/alertes.json`, `data/historique/chef/AAAA-MM-JJ.json`, `data/recap/chef-hebdo-AAAA-MM-JJ.md` (le samedi), `data/journal/agent-chef.json` (écran « Santé »).

**Appli** :
- le globe reste le premier écran ; le panneau « Synthèse » remplace le bandeau des alertes ;
- écran « Où investir » à onglets : « Panorama » (top 5 diversifié, top 5 des pays, top 3 des secteurs, top 3 des matières premières, or, obligations et liquidités, au moins 10 entreprises sur 4 secteurs et 4 pays au minimum, liste « À surveiller »), puis Pays, Secteurs (choix de la zone), Matières premières, Obligations et liquidités, Entreprises, Allocation) : pour chaque ligne, score, verdict, conviction, flèche de tendance, 3 arguments pour, 3 contre, objection du contradicteur et date du dernier changement ; toucher une ligne ouvre sa fiche détaillée (familles de signaux et leurs sources, conviction, objections, « Ce qui pourrait me donner tort ») ;
- filtre du globe « Attractivité » ;
- sous chaque recommandation : « Avis indicatif généré automatiquement, sans prise en compte d'un profil ou d'une situation personnelle. »

**Exécution** : `.github/workflows/agent-chef.yml`, lancé par le planificateur : analyse complète chaque jour à 7 h 15 UTC (après les agents du matin ; le samedi, revue hebdomadaire) ; mise à jour légère toutes les heures (minute 50) de 8 h à 21 h UTC en semaine : alertes, et recalcul seulement des verdicts touchés par un changement de palier de risque, un choc de marché (variation du jour d'au moins 3 %) ou un événement géopolitique de gravité 4 ou plus. Le workflow ne lance que ses propres tests et ceux du module commun.

```
python -m agents.chef                                   # analyse complète (Gemini si GEMINI_API_KEY existe)
python -m agents.chef --mode leger                      # mise à jour légère
python -m agents.chef --test --data /tmp/essai          # sans réseau ni Gemini (copie de data/ à fournir)
python -m agents.chef.tests.capturer_donnees_test       # met à jour les données de test
```

## Agent trader (démo : portefeuille virtuel, aucun ordre réel)

**Portefeuille fictif à but de démonstration, aucun ordre réel.** L'agent trader gère 100 000 € virtuels à partir des recommandations du chef d'orchestre, aux cours réels (Yahoo Finance), pour mesurer en conditions réelles ce que vaut la plateforme. Règles complètes : [`agents/trader/regles.md`](agents/trader/regles.md) ; paramètres : [`agents/trader/config.json`](agents/trader/config.json).

- **Stratégie** : cœur (≈ 70 %) = allocation modèle du chef d'orchestre (profil « équilibré » par défaut, modifiable), chaque ligne par son support coté (ETF pays, GLD, BNO/USO avec le coût du contango signalé, SHY/IEF/TLT, IBGS.AS et EXX6.DE pour le Bund), rééquilibré seulement au-delà de 3 points d'écart ; satellites (≈ 30 %) = convictions fortes et moyennes du chef d'orchestre sans objection sérieuse du contradicteur et avec des signaux d'au moins 2 agents, 8 % maximum par ligne, taille ∝ conviction ÷ volatilité ; plafonds par pays, secteur et thème repris du chef d'orchestre ; tout est valorisé en euros au change du jour.
- **Risque** : liquidités minimales selon le palier de l'agent risque (5 % en « Calme », 10 % en « Vigilance », 20 % en « Tension », 35 % en « Crise ») ; stop −15 % sur les satellites (suiveur dès +20 %, confirmé par 2 relevés), prise de bénéfices d'un tiers à +30 % ; sortie sur « Alléger » / « Éviter » ou objection sérieuse ; rotation mensuelle plafonnée à 30 % (sorties imposées exceptées) ; **aucune décision si le chef d'orchestre ou l'agent risque sont périmés ou dégradés** : l'agent attend et le note.
- **Exécution simulée** : premier cours disponible après la décision (jamais un cours passé), frais 0,1 %, écart achat/vente estimé, quantités entières, change du jour. Chaque opération est journalisée avec sa raison (verdict, conviction, agents, objection), son stop et « Ce qui pourrait me donner tort ».
- **Suivi** : valeur et historique quotidien, performance depuis le départ, sur 1 et 3 mois, comparée au MSCI World en euros (URTH ÷ EUR/USD) ; Sharpe, volatilité, perte maximale ; taux de réussite, gain et perte moyens ; attribution par poche, classe d'actifs et famille de signaux (pour le futur agent calibrateur).
- **Sorties** : `data/portefeuille.json` (remplace le fichier fictif), `data/trader/operations.json` (journal des opérations), `data/trader/etat.json` (positions, ordres en attente, historique), `data/journal/agent-trader.json` (écran « Santé »).
- **Appli** : écran « Portefeuille démo » (valeur en direct, graphique contre le MSCI World, risque, répartitions cœur/satellites, classes, pays et secteurs, positions avec prix de revient, cours, plus-value, poids et stop, ordres en attente, fil des opérations justifiées, dernière décision) ; le bouton de l'en-tête affiche la performance depuis le départ.
- **Exécution** : `.github/workflows/agent-trader.yml`, lancé par le planificateur : décision chaque jour de semaine à 7 h 33 UTC (après l'analyse complète du chef d'orchestre), exécutée à l'ouverture des marchés concernés ; toutes les heures (minute 5) de 8 h à 21 h UTC en semaine : ordres, valorisation, stops (et décision du jour si elle n'a pas pu être prise à 7 h 33). Le workflow ne lance que ses propres tests et ceux du module commun.

```
python -m agents.trader                                  # exécution horaire (décision du jour si due)
python -m agents.trader --mode decision                  # décision forcée
python -m agents.trader --test --data /tmp/essai         # cours simulés, sans réseau (copie de data/ à fournir)
python -m agents.trader.tests.simulation                 # simulation de 3 mois sur données de test
```

## Agent entreprises (environ 3 000 sociétés ; Gemini seulement pour lire la guidance)

L'agent entreprises se trouve dans `agents/entreprises/`. Les règles de conduite sont les mêmes que pour l'agent pays.

**Univers** : S&P 500 et S&P 400 complet, puis les plus grosses positions des ETF iShares MSCI de chaque pays suivi, avec un plafond par pays (`config.json`) ; à cela s'ajoute la liste de surveillance personnelle (`config/surveillance.json`).
- **Petites et moyennes valeurs** (`univers.petites_valeurs`) : S&P 600 (iShares IJR) et ETF iShares de petites capitalisations, avec un plafond par pays : Japon (SCJ), Inde (SMIN), Chine (ECNS), Brésil (EWZS), Royaume-Uni (EWUS), Europe continentale (IEUS, réparti par pays : France, Allemagne, Suisse, Italie, Espagne, Pays-Bas, Suède, Pologne). Identifiants vérifiés dans le sélecteur de produits iShares. Corée : pas de source gratuite exploitable pour les petites valeurs. Un fonds en échec n'empêche pas l'analyse des grandes valeurs du pays.
- Filtre : capitalisation d'au moins 300 M$ et volume suffisant.
- Doublons écartés : catégories d'actions (GOOGL / GOOG) et doubles cotations.
- Ordre des sources de composition :
  1. fichiers iShares (point d'accès CSV officiel de la page du fonds) ;
  2. membres de l'indice national sur Wikipédia (CAC 40, DAX, FTSE 100, Nikkei 225, KOSPI 200…), classés par montant échangé ;
  3. filtre d'actions Yahoo (désactivable : `"filtre_yahoo": false` dans `config.json`) ;
  4. liste manuelle vérifiée (`config/compositions_manuelles.json`, avec sa date de vérification) : affichée en information dans l'écran Santé, sans dégradation tant qu'elle a moins de 6 mois ;
  5. dernière liste connue (`data/entreprises/univers.json`), puis liste de départ, signalées « périmées » (l'agent passe alors « dégradé »).
- ETF qui ne sont pas des iShares : Colombie, Global X COLO (ex-GXG), fichier CSV du jour sur globalxetfs.com ; Vietnam et Égypte, VanEck VNM et EGPT (fichier de positions de vaneck.com, souvent refusé aux robots : la liste manuelle prend alors le relais).
- Émirats : iShares UAE. Les sociétés cotées à Abu Dhabi n'ont pas de cours sur Yahoo Finance : seules celles de Dubaï sont analysées.
- Mettre à jour une liste manuelle : remplacer les sociétés de `config/compositions_manuelles.json` (symboles Yahoo), changer `verifie_le`, puis lancer l'agent en mode `pays` (Actions → Agent entreprises → Run workflow, mode `pays`, pays `VN,EG`).
- États-Unis : SSGA SPY / MDY en secours d'iShares.
- Une société cotée plusieurs fois n'apparaît qu'une fois : la cotation la plus liquide est gardée, les autres sont indiquées sur la fiche.

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

**Dynamique des résultats** (règles : [`agents/entreprises/dynamique.md`](agents/entreprises/dynamique.md)) :
- guidance de la direction (États-Unis) : à chaque nouveau 8-K « Item 2.02 » déposé à la SEC, le communiqué de résultats (EX-99.1) est lu et Gemini en extrait la guidance (chiffre d'affaires, BPA, marge, autre), sa période et son évolution (relevée, maintenue, abaissée, initiée, retirée) ; chaque élément cite mot pour mot le communiqué, citation vérifiée dans le texte de la SEC, sinon il est écarté ; sans Gemini (secret `GEMINI_API_KEY` absent, quota atteint), « guidance non analysée », reprise le lendemain ; hors États-Unis, « guidance non disponible » ; historique dans `data/historique/guidance/TICKER.json` ;
- analystes (Yahoo Finance, toutes régions) : estimations de BPA et leur évolution sur 7, 30, 60 et 90 jours, révisions à la hausse et à la baisse, objectifs de cours, surprises des 4 derniers trimestres ; moins de 3 analystes : affichage à titre indicatif, hors note ;
- note du bloc sur 100, qui pèse 8 % dans la note globale et compte comme cinquième signal de la recommandation ; une guidance abaissée ou retirée depuis moins de 90 jours interdit « Acheter » (sauf baisse déjà intégrée dans la valorisation, justifiée) ;
- budget Gemini propre à l'agent entreprises, à l'intérieur des quotas gratuits partagés avec les agents géopolitique et risque.

**Pépites candidates** (`data/pepites.json`) : sociétés qui remplissent tous les critères de `config.json`, réparties en deux listes :
- « Pépites » : capitalisation de 300 M$ à 20 Md$, peu suivies (au plus 8 analystes quand Yahoo le fournit) ; au plus 3 par secteur et 5 par pays dans chaque liste ; objectif d'au moins 15 pépites par révision, avec les mêmes critères stricts et la revue critique (un avertissement est publié quand l'objectif n'est pas atteint) ;
- « Qualité à prix raisonnable » : grandes sociétés.

Au plus 3 sociétés par secteur dans chaque liste ; un avertissement apparaît quand une industrie ou un secteur est surreprésenté parmi les candidates. Les holdings et sociétés d'investissement sont exclues. Elles sont classées par note ajustée selon le contexte : note du pays et phase du cycle de sa zone, un ajustement modéré affiché à part. Chacune a une revue critique : risques, piège de valeur possible, risque de change, risque pays, points à vérifier soi-même et lien vers le dernier rapport officiel.

**Exécution** (`.github/workflows/agent-entreprises.yml`) :
- en semaine à 22 h 30 UTC : cours, momentum, valorisation, révision des sociétés ayant publié, nouveaux communiqués de résultats (guidance) et révisions des analystes ;
- le samedi : révision complète en 10 lots (4 parallèles au plus : États-Unis en 4 tranches, Europe et Asie-Pacifique en 2), puis assemblage (qui recalcule aussi la dynamique des résultats) ;
- à la main : onglet **Actions** → **Agent entreprises** → **Run workflow** (mode `quotidien`, `complet` ou `echantillon`).

```
python -m agents.entreprises --mode complet --echantillon 60   # essai sur 60 sociétés
python -m agents.entreprises --mode complet --lot europe --sortie-lot lot.json
python -m agents.entreprises --mode assembler --lots lot*.json
python -m agents.entreprises --mode quotidien
```

**Liste de surveillance** : chaque analyse à la demande y ajoute la société ; on peut aussi ajouter une ligne dans `config/surveillance.json`, par exemple `{"ticker": "ASML.AS", "pays": "NL"}`. Le ticker est le symbole Yahoo Finance ; le pays, le code à 2 lettres d'un pays suivi. La société est analysée à la révision suivante, même hors de l'univers et quelle que soit sa taille.

## Analyse à la demande

Analyse d'une société précise avec la même grille que l'agent entreprises (mêmes sources dans le même ordre : SEC, ESEF, EDINET, DART, Yahoo ; mêmes indicateurs, F-score, signaux d'alerte, notes, verdict, confiance, « Ce qui pourrait me donner tort », revue critique, ajustement de contexte), plus le rang dans le secteur parmi les sociétés déjà analysées et la recommandation.

**Lancer une analyse.** Dans l'appli : bouton **Analyser une entreprise** (écran Pépites, écran Mes analyses, ou recherche sans résultat) → saisir un ticker Yahoo (`ASML`, `MC.PA`, `7203.T`) ou un nom (« Hermès ») → la page GitHub de nouvelle issue s'ouvre, titre prérempli « Analyse : … » → **Submit**. Résultat dans 2 à 5 minutes. On peut aussi ouvrir l'issue à la main.

**Ce que fait le workflow** (`.github/workflows/analyse-demande.yml`, déclenché par `issues: opened` quand le titre commence par « Analyse ») :
- si l'auteur de l'issue n'est pas le propriétaire du dépôt : commentaire poli, fermeture, rien n'est lancé ;
- résolution de la saisie avec la recherche Yahoo : ticker exact retenu tel quel ; pour un nom, cotation la plus liquide (montant moyen échangé sur 3 mois), les autres candidates sont citées ; aucune action : « introuvable » avec des suggestions ;
- analyse (`python -m agents.analyse_demande`), écriture de `data/analyses/<TICKER>.json` et `data/analyses/index.json`, ajout de la société à `config/surveillance.json` (elle est ensuite suivie par l'agent entreprises) ;
- commentaire en français sur l'issue (note /100, verdict, recommandation, 5 indicateurs clés, principaux risques, niveau de confiance, lien `https://jcn1996.github.io/Plateforme-eco/#analyse-TICKER`), puis fermeture ;
- en cas d'erreur : échec enregistré (écran Santé, carte « Analyse à la demande »), signalé dans l'issue, issue fermée.

**Dans l'appli** : icône « document » de l'en-tête → **Mes analyses** (date, note, verdict, recommandation ; les demandes dont l'issue est encore ouverte s'affichent « en cours ») ; toucher une ligne ouvre la fiche complète. Lien direct : `#analyse-TICKER`.

Test sans réseau, avec des événements simulés : `python -m unittest agents.analyse_demande.tests.test_agent`. Essai réel : écrire un fichier d'événement (`{"issue": {"number": 1, "title": "Analyse : ASML", "user": {"login": "jcn1996"}}, "repository": {"owner": {"login": "jcn1996"}}}`) puis `python -m agents.analyse_demande --evenement evenement.json --sortie /tmp/sortie`.

## Recommandations et fiabilité

Chaque fiche (agent entreprises, pépites, analyses à la demande) porte une recommandation à 12 mois, en deux lectures : **si non détenu** (Acheter / Acheter sur repli / Attendre / Éviter) et **si détenu** (Renforcer / Conserver / Alléger / Vendre), avec une fourchette de valeur estimée par deux méthodes (multiples comparés à la médiane du secteur ; flux de trésorerie disponibles actualisés, hypothèses affichées), l'écart au cours, le prix de repli, 2 ou 3 conditions précises qui invalideraient la recommandation et les principaux risques. « Acheter » ou « Vendre » exigent une confiance « moyen » ou « élevé » et au moins 3 signaux concordants (note, valorisation, momentum, qualité comptable, dynamique des résultats ; achats d'initiés et super-investisseurs, de pondération modérée) ; un signal d'alerte comptable interdit « Acheter », de même qu'une guidance abaissée ou retirée depuis moins de 90 jours (sauf baisse déjà intégrée dans la valorisation, justifiée). Règles et seuils : `agents/entreprises/recommandation.md` et section `recommandation` de `agents/entreprises/config.json`.

Suivi : `data/historique/recommandations.json` (date, cours, recommandation, fourchette), écrit par `python -m agents.entreprises.suivi`, lancé juste avant chaque poussée par les workflows « Agent entreprises » et « Analyse à la demande » (`outils/pousser_avec_suivi.sh`). Performance à 3, 6 et 12 mois comparée au MSCI World (ETF URTH) et taux de réussite par type, affichés dans l'écran **Fiabilité des recommandations** (depuis Mes analyses ou une fiche).

## Réveil externe (cron-job.org)

Les tâches planifiées de GitHub (`schedule`) peuvent être retardées, voire sautées sans erreur. Un service externe appelle donc toutes les 15 minutes le workflow **Planificateur** (`.github/workflows/planificateur.yml`, déclenché uniquement par `workflow_dispatch`).

À chaque appel, le planificateur (`agents/planificateur/`) :
- lit l'heure UTC et les plannings (lignes `cron`) des workflows des agents ;
- lance (`gh workflow run`) chaque agent dont le dernier créneau prévu n'est pas encore fait :
  - agent marchés : selon son créneau ;
  - agents pays, macro et entreprises : une fois par jour à leur heure ; agent pays en mode « flux » en soirée à New York (2 h 07 UTC, du mardi au samedi) ;
  - agent géopolitique : toutes les heures ; agent risque : toutes les heures en séance et analyse complète à 22 h 45 UTC ;
  - agent trader (démo) : décision à 7 h 33 UTC en semaine, puis toutes les heures (minute 5) de 8 h à 21 h UTC ;
  - révision complète du samedi ;
  - maintien du lundi.
- ne lance jamais deux fois le même créneau : il se fonde sur `derniere_execution` des journaux. Une nouvelle tentative a lieu après 60 min sans résultat, deux tentatives au plus, et rien n'est lancé si une exécution est déjà en cours.
- trace ses lancements dans `data/journal/planificateur.json`. Ce fichier n'est commité que s'il y a eu un lancement, ou au plus toutes les 20 min pour indiquer le dernier appel.

Les plannings GitHub restent actifs en secours ; la `concurrency` de chaque workflow évite les doublons. L'écran Santé affiche le dernier appel reçu, et le planificateur passe « en panne » sans appel depuis plus de 45 minutes.

**Mise en place** :
1. **Jeton GitHub** : GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
   - Accès : *Only select repositories* → `Plateforme-eco`.
   - Permission : **Actions : Read and write**.
   - Note la date d'expiration : il faudra renouveler le jeton.
2. **Tâche sur cron-job.org** (Create cronjob) :
   - **URL** : `https://api.github.com/repos/jcn1996/Plateforme-eco/actions/workflows/planificateur.yml/dispatches`
   - **Planning** : toutes les 15 minutes.
   - **Méthode** (onglet *Advanced*) : `POST`.
   - **En-têtes** :
     ```
     Authorization: Bearer <token>
     Accept: application/vnd.github+json
     X-GitHub-Api-Version: 2022-11-28
     ```
   - **Corps** : `{"ref":"main"}`
   - Réponse attendue : **204 No Content**. Un code 401 ou 403 signale un jeton invalide, expiré ou sans la permission Actions ; un 404, une URL ou un nom de workflow erroné.
3. Vérifier dans l'onglet **Actions** qu'une exécution « Planificateur » apparaît après le premier appel.

## Santé des agents

Menu → **Santé des agents** (sur grand écran, aussi l'icône en forme de pouls de l'en-tête). Une pastille rouge s'affiche sur le bouton « Menu » (et sur l'icône) dès qu'un agent n'est pas « OK ».
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

## Tests

Chaque agent ne lance, avant de tourner, que ses propres tests et ceux du module commun (`agents/commun`) : un test d'un autre agent ne peut pas le bloquer en production.

Le workflow `.github/workflows/tests.yml` (« Tests ») lance l'ensemble des tests sur chaque pull request (et à la main). Il échoue aussi si un test modifie ou lit les vrais dossiers `config/` et `data/` : les tests sont relancés avec ces deux dossiers retirés.

Règle : un test ne lit ni ne modifie jamais les vrais `config/` et `data/` (ils changent avec la production, par exemple la liste de surveillance). Il travaille dans un dossier temporaire, avec des copies de test (`agents/<agent>/tests/donnees/`) ; `agents/commun/essais.py` fournit des `pays.json` et `macro.json` de test, produits par les agents pays et macro en mode test.

```
python -m unittest discover -s agents -t .   # tous les tests
```

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
js/risque.js          pastille et écran « Risque », rubrique « Agent risque » de la fiche pays, filtre du globe
js/matieres-premieres.js  écran « Matières premières » (liste, fiches, pays producteurs sur le globe)
js/chef.js            chef d'orchestre : panneau « Synthèse », écran « Où investir », fiche d'opportunité, allocation, écran « Fiabilité du chef d'orchestre », filtre « Attractivité »
js/inities.js         écran « Initiés » (dirigeants, super-investisseurs, activistes, élus) et bloc de la fiche entreprise
js/pepites.js         écran « Pépites »
js/analyses.js        analyse à la demande (bouton, « Mes analyses »), écran « Fiabilité des recommandations »
js/panneau-pays.js    fiches pays et secteur
js/panneau-entreprise.js  fiche entreprise
js/portefeuille.js    écran « Portefeuille démo » (agent trader : valeur, performance contre le MSCI World, risque, répartitions, positions, opérations)
js/classement.js      écran classement
js/comparateur.js     comparateur (sélection, barre flottante, écran)
js/recherche.js       recherche de pays, secteurs et entreprises
js/mes-alertes.js     règles d'alertes personnelles
js/outils.js          couleurs des notes, formats français
data/pays.json        données réelles des pays (produites par l'agent pays)
data/historique/pays/ historique quotidien des notes de l'agent pays
data/recap/           récapitulatif de chaque exécution de l'agent pays
data/journal/         journal des sources en échec
data/analyses/        analyses à la demande (index.json et une fiche par société)
data/historique/recommandations.json  recommandations enregistrées et leur performance
data/historique/guidance/  guidances extraites des communiqués de résultats (8-K Item 2.02), une fiche par société
config/surveillance.json  liste de surveillance (complétée par les analyses à la demande)
config/super_investisseurs.json  super-investisseurs suivis par l'agent initiés (CIK, noms des entités hors États-Unis)
data/historique/flux_etf/  relevés quotidiens des ETF pays (parts en circulation, VL), flux d'investissement
data/signaux/pays.json     signaux de l'agent pays (flux des ETF) pour le futur chef d'orchestre
data/chef.json        sortie du chef d'orchestre (opportunités, verdicts, allocation) ; data/chef/ : briefings, suivi de performance, état
data/alertes.json     alertes du jour (chef d'orchestre)
data/portefeuille.json  portefeuille démo (agent trader, aucun ordre réel) ; data/trader/ : journal des opérations et état
data/*.json           autres données
agents/               agents Python (agents/commun : téléchargement, cache, journal, écriture ; agents/pays : agent pays ; agents/marches : agent marchés ; agents/macro : agent macro ; agents/rattrapage : relance des exécutions manquées ; agents/entreprises : agent entreprises, recommandation et suivi ; agents/analyse_demande : analyse à la demande ; agents/risque : agent risque et contradicteur ; agents/matieres_premieres : agent matières premières ; agents/inities : agent initiés ; agents/donnees_alternatives : agent données alternatives ; agents/chef : chef d'orchestre ; agents/trader : agent trader démo)
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
| `portefeuille.json` | agent trader (réel) | valeur, statistiques, répartitions, positions, ordres en attente, opérations, historique, dernière décision |

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
- `valorisation` porte le `per` de l'ETF, la `mediane` des pays suivis et `mention_source` ;
- `momentum` porte `base` (« indice » ou « etf »), `indice`, `symbole`, `monnaie`, `performance_eur`, `effet_change` (en points) et, pour l'ETF de secours, `mention` (« indice indisponible, ETF affiché ») et `raison_indice`.

Chaque pays porte aussi `indice` (`nom`, `yahoo`, `monnaie`, `historique` : l'indice a-t-il servi au momentum du jour, sinon `raison`). Les clôtures des indices utilisables sont dans `data/cours/indices-pays.json` (graphique simplifié).

Chaque pays porte aussi :
- `confiance` (`niveau`, `score`, `raisons`) ;
- `contre_scenario` (« Ce qui pourrait me donner tort ») ;
- `lecture`.

Le bloc `detail` contient `devise_3m`, `solde_courant` et `flux_etrangers`. `marches.json` donne pour chaque cotation `symbole`, `valeur`, `variation` (jour, en %), `variation_1an`, `heure` (UTC), `statut` (« ouvert » ou « fermé »), `source` et `ancienne`.

`detail.flux_etrangers` (flux de l'ETF pays) : `valeur` (flux nets sur 1 mois en % de l'encours, ou 1 semaine tant que le mois est en cours de constitution ; `periode_valeur`), `note`, `symbole`, `emetteur`, `date` (date de la VL), `periodes` (`1s`, `1m`, `3m` : `flux_musd`, `pct_encours`, `complet`, `statut`, `jours_disponibles`), `serie_consecutive`, `encours_musd`, `cumul` (flux cumulés en M$, jour par jour sur 3 mois), `tendance_flux`, `encombrement` (s'il y a lieu), `avertissement`, `sources` et `verification`.

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
