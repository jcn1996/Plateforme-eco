# Chef d'orchestre — méthode

Le chef d'orchestre réunit les sorties de tous les agents pour répondre à une question : **« Où investir maintenant, et avec quelle conviction ? »**
Il ne collecte presque rien lui-même : il lit les fichiers des autres agents, les pondère, décide, explique et suit ses propres résultats.
Tous les poids et seuils cités ici sont dans [`config.json`](config.json) ; les changer ne demande aucune modification du code.

Règles de conduite : ton froid et factuel, sans euphorie ni alarmisme ; toujours « Ce qui pourrait me donner tort » ; faits et interprétations distingués ; une donnée manquante est signalée, jamais inventée.
Chaque recommandation porte la mention : « Avis indicatif généré automatiquement, sans prise en compte d'un profil ou d'une situation personnelle. »

## 1. Entrées

| Entrée | Fichier | Âge maximal avant « périmée » |
|---|---|---|
| Agent pays | `data/pays.json` | 30 h |
| Agent macro | `data/macro.json` | 30 h |
| Agent marchés | `data/marches.json` | 72 h (week-end) |
| Agent risque | `data/risque.json` (et `data/risque/etat.json` pour le Bund à 10 ans) | 30 h |
| Agent géopolitique | `data/geopolitique.json` | 6 h |
| Agent matières premières | `data/matieres_premieres.json` | 80 h |
| Agent entreprises | `data/entreprises.json`, fiches, `data/pepites.json` | 30 h |
| Agent initiés | `data/inities.json` | 80 h |
| Analyses à la demande | `data/analyses/index.json` | — |
| Contradicteur | `data/signaux/revues.json` | 30 h |
| Signaux | `data/signaux/*.json` | (fenêtre propre à chaque usage) |

**Pondération de chaque entrée** (`entrees` dans la configuration) :
- fraîcheur : coefficient 1 jusqu'à l'âge maximal, puis décroissance linéaire jusqu'à 0,4 à trois fois cet âge ;
- agent dégradé (bloc « santé » de son journal) : × 0,8 ;
- fichier absent : l'entrée ne pèse rien et les familles qui en dépendent sont « manquantes » ;
- confiance de chaque valeur (« élevé » 1, « moyen » 0,85, « faible » 0,6).

Le coefficient d'une famille de signaux = coefficient de l'entrée × confiance de la valeur. Toutes les entrées et leur état sont publiés (`entrees` dans `data/chef.json`, écran « Santé », rubrique « Données » du briefing).

## 2. Univers des opportunités

- **Actions par pays** : les 31 pays suivis par l'agent pays. Pour chaque pays au verdict positif, les 3 meilleures sociétés (recommandation de l'agent entreprises, puis note).
- **Matières premières** : les 17 matières premières de l'agent matières premières (hors or), avec leur famille.
- **Or** : traité à part, comme valeur refuge.
- **Obligations** : États-Unis et zone euro, courtes (2 ans) et longues (10 ans).
- **Liquidités** : dollar et euro (rendement monétaire réel = taux directeur − inflation).
- **Entreprises** : pépites, « qualité à prix raisonnable », liste de surveillance, analyses à la demande, meilleures sociétés des pays attractifs et 3 meilleures sociétés de chaque secteur (au plus 130 ; une société cotée plusieurs fois n'apparaît qu'une fois).
- **Exclusions** : holdings, sociétés d'investissement (ex. Investor AB), fonds fermés, BDC, véhicules de crédit et SPAC sont écartés du classement, des « meilleures sociétés » des pays et des alertes. Leur valeur se lit sur la décote par rapport à l'actif net, que les sources gratuites ne donnent pas ; une conviction ne peut donc jamais s'appuyer sur leur PER. Détection : drapeau « holding » de l'agent entreprises (industries exclues, mots du nom, fonds et BDC, SPAC : `pepites` dans `agents/entreprises/config.json`). L'agent entreprises applique la même règle : ces sociétés sont exclues des pépites et ne reçoivent jamais « Acheter » ni « Renforcer ». La liste des sociétés écartées est publiée (`exclues` dans `data/chef.json`).

### Secteurs

Les 11 secteurs GICS au niveau mondial et par grande zone (États-Unis, Europe, émergents), quand au moins 5 sociétés analysées par l'agent entreprises le permettent (`secteurs` dans la configuration ; holdings, fonds, BDC et SPAC exclus des agrégats).

| Famille | Signal |
|---|---|
| Fondamentaux | note médiane des sociétés du secteur dans la zone |
| Valorisation | rendement des bénéfices médian (100 / PER médian) + 0,25 × croissance médiane des bénéfices (bornée entre −20 et +30 %), comparé à la médiane des secteurs de la zone : note = 50 + 4 × écart |
| Dynamique des résultats | note médiane « Dynamique des résultats » (guidance, révisions des analystes, surprises) |
| Tendance | performance sur 12 mois de l'ETF sectoriel (50 + 1,2 × performance) ; sans ETF : momentum médian des sociétés |
| Flux | flux de l'ETF sectoriel, même méthode et même note que les ETF pays (parts en circulation × VL ; SSGA pour les XL*, avec leur historique publié ; iShares pour les ETF mondiaux ; Yahoo Finance en secours et en vérification) ; historique dans `data/chef/flux_secteurs/` |
| Adéquation au cycle | tableau de rotation sectorielle selon la phase de l'agent macro (zone du secteur) |
| Initiés | sociétés avec achats de dirigeants (score ≥ 60) ou conviction des super-investisseurs (≥ 50), moins les ventes massives : 50 + 6 × solde (30 à 80) |
| Risque | sensibilité défensive, cyclique ou neutre, selon le palier de risque (ex. défensif : 45 en Calme, 80 en Crise) |
| Géopolitique | exposition aux actifs cités par les événements de gravité ≥ 3 des 14 derniers jours (pétrole, gaz et énergie pour l'énergie ; défense pour l'industrie ; pétrole en hausse défavorable à la consommation discrétionnaire…) |

ETF : États-Unis XLK, XLV, XLE, XLF, XLI, XLB, XLY, XLP, XLU, XLRE, XLC ; monde iShares Global (IXN, IXJ, IXC, IXG, EXI, MXI, RXI, KXI, JXI, REET, IXP) ; Europe iShares STOXX Europe 600 (Xetra), dont certains secteurs ICB ne recouvrent qu'en partie le secteur GICS (banques pour la finance, automobile pour la consommation discrétionnaire, alimentation et boissons pour la consommation de base…) : c'est indiqué sur la fiche. Émergents : pas d'ETF sectoriel exploitable.

Rotation sectorielle (score /100 de la famille « Adéquation au cycle », adaptée de l'horloge des investissements et de l'approche par le cycle économique) :

| Secteur | Reprise | Surchauffe | Ralentissement inflationniste | Expansion sans inflation |
|---|---|---|---|---|
| Technologies de l'information | 70 | 50 | 35 | 72 |
| Santé | 45 | 55 | 72 | 65 |
| Énergie | 45 | 82 | 70 | 32 |
| Finance | 72 | 55 | 40 | 50 |
| Industrie | 72 | 62 | 38 | 48 |
| Matériaux | 65 | 78 | 50 | 35 |
| Consommation discrétionnaire | 78 | 42 | 28 | 55 |
| Consommation de base | 35 | 50 | 78 | 62 |
| Services aux collectivités | 35 | 45 | 72 | 66 |
| Immobilier | 65 | 40 | 35 | 62 |
| Services de communication | 60 | 45 | 48 | 66 |

Les secteurs suivent les mêmes règles que les autres catégories (percentiles dans la zone, pondérations selon le palier, verdict, conviction, hystérésis, momentum extrême, contrôle de cohérence) ; un verdict positif exige une famille motrice (fondamentaux, valorisation, tendance, flux ou résultats). Dans l'allocation modèle, 30 % de la part « cœur » des actions va aux secteurs à verdict positif dotés d'un ETF (une zone par secteur, la mieux notée ; 4 secteurs au plus), le reste aux pays ; les secteurs ne sont pas des satellites.

## 3. Moteur de décision

### Familles de signaux

| Famille | Pays | Matières premières / or | Obligations / liquidités | Entreprises |
|---|---|---|---|---|
| Fondamentaux | notes croissance, indicateur avancé, inflation, taux réel (agent pays) | courbe des prix à terme et stocks ; pour l'or : taux réel attendu à 10 ans (niveau et variation sur 12 mois) | inflation par rapport à la cible, pente de la courbe 10 ans − 2 ans | note de l'agent entreprises |
| Valorisation | PER de l'ETF pays contre la médiane | niveau historique (corrigé de l'inflation) | rendement réel (taux − inflation) | PER et VE/EBITDA contre le secteur |
| Tendance et momentum | momentum 12 mois de l'indice | tendance (3 et 12 mois, moyenne 200 jours) | variation des taux sur 12 mois ; direction de la banque centrale | momentum 12 mois |
| Flux d'investissement | flux des ETF pays | flux des ETF et positionnement CFTC | — | flux de l'ETF du pays |
| Adéquation au cycle | tableau des phases (ci-dessous) | tableau + moteurs macro de l'agent | tableau | tableau + inflexion sectorielle |
| Risque | 100 − score de risque pays | palier de risque (tableau par palier) | palier de risque (refuge) | risque du pays − signaux d'alerte comptables |
| Géopolitique | 100 − score géopolitique | sous-note géopolitique | — | géopolitique du pays |
| Initiés et super-investisseurs | — | — | — | achats de dirigeants, conviction des super-investisseurs (ventes massives : 30/100) |
| Dynamique des résultats | médiane des notes des sociétés du pays (5 au moins) | — | — | guidance, révisions des analystes, surprises |

**Normalisation en percentiles** : dans une classe d'au moins 8 éléments (pays, matières premières, entreprises), le score d'une famille = 0,5 × percentile dans la classe + 0,5 × note absolue de l'agent. Le percentile seul rendrait toujours « attractifs » les premiers, même quand tous sont mauvais ; la note seule ignorerait le classement relatif. Les entreprises sont classées contre tout l'univers de l'agent entreprises (environ 1 500 sociétés). Les obligations, les liquidités et l'or (classes trop petites) gardent des échelles absolues documentées dans la configuration (`obligations`, `liquidites`, `or`).

### Adéquation au cycle

Tableau inspiré de « l'horloge des investissements » (Merrill Lynch, 2004), adapté aux quatre phases de l'agent macro (score /100) :

| Phase (croissance / inflation) | Actions | Oblig. longues | Oblig. courtes | Matières | Or | Liquidités |
|---|---|---|---|---|---|---|
| Reprise (↑ / ↓) | 85 | 55 | 45 | 55 | 45 | 30 |
| Surchauffe (↑ / ↑) | 60 | 25 | 40 | 85 | 60 | 45 |
| Ralentissement inflationniste (↓ / ↑) | 25 | 30 | 60 | 60 | 85 | 75 |
| Expansion sans inflation (↓ / ↓) | 55 | 85 | 65 | 30 | 55 | 50 |

La phase utilisée est celle de la zone du pays (États-Unis, zone euro, Chine, Japon, émergents ; « Monde » sinon). Pour les entreprises, une inflexion sectorielle de quelques points s'ajoute (ex. énergie + 10 en surchauffe ; consommation de base + 8 en ralentissement inflationniste).

### Pondérations conditionnées au régime

Poids de base par type d'opportunité (`poids`), multipliés selon le palier de risque de l'agent risque (`regimes`) :

| Palier | Tendance | Flux | Risque | Fondamentaux (qualité) | Géopolitique |
|---|---|---|---|---|---|
| Calme | × 1,3 | × 1,1 | × 0,8 | × 0,9 | × 1 |
| Vigilance | × 1 | × 1 | × 1 | × 1 | × 1 |
| Tension | × 0,7 | × 0,9 | × 1,4 | × 1,3 | × 1,2 |
| Crise | × 0,5 | × 0,8 | × 1,7 | × 1,5 | × 1,3 |

### Score d'attractivité /100

1. score brut = moyenne des familles disponibles, pondérée par poids × coefficient de fiabilité ;
2. qualité = (somme des poids × coefficients des familles disponibles) / (somme des poids prévus) ;
3. **score = 50 + (score brut − 50) × qualité** : une opportunité mal documentée (familles manquantes, données périmées, agent dégradé) est ramenée vers le neutre. Les familles manquantes sont affichées.

### Le risque est un frein, pas un moteur

Pour les pays, les entreprises et les matières premières (`risque_frein`) :
- les familles « Risque » et « Géopolitique » sont plafonnées à 55/100 : un risque faible lève un frein mais ne porte pas la note (pour l'or, les obligations et les liquidités, le palier de risque reste un moteur, puisqu'il mesure leur rôle de refuge) ;
- un verdict positif exige au moins une famille motrice (fondamentaux, valorisation, tendance ou flux) à 60/100 ou plus ; sinon le verdict est « Neutre », même si l'hystérésis l'aurait maintenu, et la raison est affichée.

### Momentum extrême

Une hausse passée au-delà du 90e percentile de sa classe, ou d'au moins 40 % sur 12 mois (le percentile est grossier dans une petite classe comme les matières premières), est traitée à part (`momentum`) :
- elle ne compte pas dans la concordance de la conviction : elle ne peut pas porter seule une conviction forte ;
- elle déclenche une vérification : valorisation (au moins 45/100) et positionnement ou flux (au moins 40/100, pour écarter une position encombrée) ; pour une matière première, un contexte géopolitique fort est signalé comme réversible ;
- elle déclenche une objection systématique (règle du contradicteur appliquée par le chef d'orchestre), qui abaisse la conviction d'un cran. L'opportunité va dans « À surveiller », pas dans le top 5.

### Verdict

| Score | Verdict |
|---|---|
| ≥ 70 | Renforcer fortement |
| 58 à 70 | Renforcer |
| 43 à 58 | Neutre |
| 33 à 43 | Alléger |
| < 33 | Éviter |

« Renforcer fortement » et « Éviter » exigent au moins une conviction moyenne ; sinon le verdict est ramené d'un cran (« Renforcer », « Alléger ») et la raison est affichée.

**Anti-girouette (hystérésis)** : un verdict ne change que si le score franchit le seuil d'au moins 5 points, ou reste au-delà du seuil 3 jours de suite (`verdicts.marge` et `verdicts.jours_confirmation`). Rejeu des exécutions du 07 au 09/11/2026 : le 09/11, 1 verdict sectoriel change au lieu de 7 avec l'ancien réglage (3 points, 2 jours). Sinon le changement est « en attente » et affiché comme tel. Chaque changement est expliqué (ancien et nouveau verdict, scores, règle appliquée) et daté.

### Conviction (faible / moyenne / forte)

Les familles sont regroupées en groupes indépendants (fondamentaux et dynamique des résultats = un groupe ; risque et géopolitique = un groupe ; valorisation, tendance, flux, cycle, initiés = un groupe chacun). Un groupe est concordant quand l'une de ses familles est ≥ 60 (verdict positif) ou ≤ 40 (verdict négatif).

- **forte** : au moins 3 groupes concordants, qualité des données ≥ 0,6 (confiance moyenne ou élevée), toutes les entrées utilisées fraîches et d'agents sains (coefficient ≥ 0,95), et aucune objection sérieuse du contradicteur ;
- **signal solide exigé** : une conviction forte exige en plus au moins une famille parmi la valorisation, la dynamique des résultats (révisions, guidance) et les flux d'investissement, nettement dans le sens du verdict et jugée sur sa **note absolue** (≥ 65 pour un verdict positif, ≤ 35 pour un négatif), avant le mélange avec le percentile de la classe : un bon rang parmi des opportunités médiocres ne suffit pas. Le cycle et le momentum ne suffisent jamais seuls ; sinon la conviction est plafonnée à « moyenne », et la raison est affichée. Exemple : « Technologies de l'information — Émergents » (09/11/2026), dont la valorisation n'est qu'à 56 en absolu (percentile 86 dans la zone) et la dynamique des résultats à 64 ;
- **moyenne** : au moins 2 groupes concordants et qualité ≥ 0,6 ;
- **faible** : sinon ;
- verdict « Neutre » : au plus moyenne (3 groupes neutres ou plus) ;
- **contrôle de cohérence avant publication** : une conviction forte doit lister au moins 3 familles de signaux dans le sens du verdict (≥ 60 pour un verdict positif, hors risque et géopolitique ; ≤ 40 pour un verdict négatif) ; sinon elle est ramenée à « moyenne », et c'est affiché ;
- **objections rattachées à la bonne entité** : quand un signal touche plusieurs pays (ex. un événement géopolitique concernant l'Allemagne et les Émirats), le contradicteur publie une objection par entité (`par_entite`, règles v3 de l'agent risque) ; le chef n'attache à chaque pays que la sienne, plus les points communs au signal. Pour une revue plus ancienne, seuls les points qui citent l'entité sont gardés ;
- **chaque objection sérieuse** du contradicteur (revue spécifique avec l'ajustement « abaisser » ou « signal fragile », moins de 7 jours) abaisse la conviction d'un cran. Les objections sont rattachées aux opportunités : pays (signaux pays, risque, géopolitique), zone (pays de la zone et obligations), entreprise, matière première.

### Tendance et concentrations

- Flèche ↑ / ↓ / → : variation du score d'au moins 2 points depuis l'analyse complète précédente.
- Concentrations thématiques (`themes`) : IA, semi-conducteurs, or, pétrole (tickers, industries, matières premières, pays). Avertissement quand un thème représente au moins 30 % des recommandations positives, ou approche son plafond dans l'allocation.

## 4. Allocation modèle (indicative)

Trois profils (prudent, équilibré, dynamique), structure cœur-satellite (`allocation`) :
1. cible par classe (actions, obligations, or, matières premières, liquidités), infléchie selon le score moyen de la classe (± 6 à 10 points selon le profil) ;
2. part minimale de liquidités selon le palier de risque : Calme 2 %, Vigilance 5 %, Tension 10 %, Crise 20 % ;
3. **satellites** (10 %, 20 %, 30 % selon le profil) : convictions fortes à verdict positif (8 au plus, 4 % par ligne au plus), prélevés sur les classes risquées ;
4. **cœur** : lignes de chaque classe pondérées par leur score (verdicts « Alléger » et « Éviter » exclus ; 10 pays au plus) ; une classe sans ligne éligible passe en liquidités ;
5. contraintes : 40 % par pays, 12 % par secteur, 20 % par thème, 8 % par ligne (25 % pour une ligne obligataire) ; l'excédent est redistribué ;
6. rotation limitée : un écart de moins de 1,5 point avec l'allocation de la veille est ignoré ; chaque variation est justifiée.

Cette allocation servira de base au futur agent trader démo.

## 5. Synthèse et alertes

**Panorama « Où investir »** (`panorama`) : un tour d'horizon large et équilibré plutôt qu'une seule pépite.
- Top 5 : verdicts positifs dont le score dépasse le seuil « Renforcer » (pas seulement maintenus par l'hystérésis), sans objection sérieuse à lever ni momentum extrême ; d'abord une ligne par catégorie (pays, entreprises, matières premières, or, obligations, liquidités), puis deux, puis trois en dernier recours quand les autres catégories n'ont aucune ligne éligible.
- Listes par catégorie triées par score.
- Par catégorie : top 5 des pays, top 3 des secteurs (une zone par secteur), top 3 des matières premières, position sur l'or, sur chaque ligne obligataire et sur les liquidités.
- Entreprises : au moins 10 quand les données le permettent (verdicts positifs d'abord, puis meilleurs « Neutre »), au plus 2 par secteur et 3 par pays, au moins 4 secteurs et 4 pays ; un écart à ces objectifs est signalé.
- « À surveiller » (8 au plus, 3 par catégorie) : opportunités à moins de 4 points du seuil « Renforcer », verdict maintenu par l'hystérésis sous le seuil, ou bien notées mais avec une objection sérieuse à lever ou un momentum extrême.

**Briefing quotidien** (`data/chef/briefing-AAAA-MM-JJ.md` et `.json`) : l'essentiel en 5 lignes, une par catégorie (risque et cycle ; pays ; matières premières et or ; obligations et liquidités ; secteurs et entreprises) ; le panorama complet ; « Ce qui a changé depuis hier » ; points de vigilance ; scénario central et scénario alternatif avec leurs déclencheurs ; agenda des 7 prochains jours ; « Ce qui pourrait me donner tort » ; état des données ; liste des faits utilisés.

- Version par règles toujours produite. Avec `GEMINI_API_KEY`, Gemini reformule « l'essentiel » et la vigilance (budget propre : 4 appels par exécution au plus), avec la même chaîne de modèles de secours que l'agent géopolitique (Flash le plus récent, Flash-Lite, Flash précédent : quota du jour atteint ou panne, modèle suivant). Quand le briefing reste par règles, la raison est affichée dans le briefing et journalisée : clé absente, budget épuisé, Gemini indisponible sur toute la chaîne, réponse rejetée. Chaque phrase doit citer un fait fourni (`[F3]`) et ne contenir que des chiffres présents dans les faits cités ; sinon elle est supprimée (liste publiée). Une rubrique avec trop peu de phrases valides reprend la version par règles.
- **Gemini ne sert qu'à la rédaction** : son échec (erreur, réponse rejetée, quota) n'est jamais une dégradation du chef d'orchestre, dont les données (scores, verdicts, allocation) n'en dépendent pas. L'écran Santé l'affiche en information (« rédaction par règles », état `information` : ni comptée, ni dégradante). Après une erreur ou une réponse rejetée, une **nouvelle tentative de rédaction a lieu 30 minutes plus tard** (mode `redaction`, créneau de 7 h 45 UTC ; à défaut, mise à jour légère suivante), deux au plus (`gemini.reprise`) : seuls « l'essentiel » et la vigilance du briefing du jour changent, les données et la date de `data/chef.json` restent celles de l'analyse complète. Pas de reprise sans clé ni quand le budget du jour est épuisé. Le dépôt facultatif sur Google Drive suit la même règle (information).
- Agenda : réunions des banques centrales (agent macro, calendriers officiels), publications de résultats des sociétés de la liste de surveillance (Yahoo Finance), EIA (mercredi, jeudi), WASDE (entre le 9 et le 12), emploi américain (premier vendredi), inflation américaine (10 à 15), inflation de la zone euro (fin de mois). Les dates tirées d'une règle de calendrier sont marquées « indicatives ».
- Dépôt facultatif sur Google Drive : secrets `GOOGLE_SERVICE_ACCOUNT_JSON` et `DRIVE_FOLDER_ID` ; ignoré s'ils sont absents.

**Alertes** (`data/alertes.json`, remplace définitivement le fichier fictif) : signaux de moins de 48 h (`data/signaux/*.json`) et changements de verdict importants du chef ; une alerte d'initiés ou d'entreprise ne passe que pour une société de l'univers analysé et notée, qui n'est ni une holding, ni un fonds, ni un véhicule de crédit ou une SPAC ; les déclarations 13D/13G internes (un gestionnaire qui déclare détenir 99 % ou plus de son propre véhicule) sont écartées ; les alertes écartées sont listées (`alertes_ecartees`) ; un signal jugé « signal fragile » par le contradicteur est écarté, « abaisser » réduit son importance d'un cran ; importance moyenne au moins ; 4 alertes au plus, diversifiées (un signal par agent et par type d'abord, deux par agent au plus, titres en double écartés). Sans alerte : « Aucune alerte notable ».

## 6. Suivi de performance

`data/chef/suivi.json` : chaque verdict (premier verdict et chaque changement) est enregistré avec la date, le score, la conviction, le symbole suivi (ETF pays, contrat à terme, ETF obligataire ou monétaire, action) et son prix de référence quand il est connu. Performance à 1, 3, 6 et 12 mois (cours ajustés Yahoo Finance) contre l'indice de la classe :

| Classe | Indice de référence |
|---|---|
| Pays, secteurs, entreprises, liquidités | MSCI World (ETF URTH) |
| Matières premières, or | indice large des matières premières (ETF DBC) |
| Obligations américaines | ETF AGG |
| Obligations en euros | ETF IEAG |

Réussite : « Renforcer » et « Renforcer fortement » si la performance relative est positive ; « Alléger » et « Éviter » si elle est négative ; « Neutre » si elle reste dans ± 5 points. Taux de réussite par type, par verdict et par conviction ; **calibration** : une conviction forte doit réussir plus souvent qu'une moyenne, elle-même plus qu'une faible (mesurée à partir de 10 verdicts par niveau). Écran « Fiabilité du chef d'orchestre ». Ces résultats alimenteront l'agent calibrateur.

## 7. Rythme

- **Analyse complète** chaque jour à 7 h 15 UTC, après les agents du matin (pays 6 h 11, géopolitique 6 h 03, inities 6 h 35, macro 6 h 41).
- **Mise à jour légère** toutes les heures (minute 50) de 8 h à 21 h UTC en semaine : alertes à chaque fois ; recalcul des verdicts touchés seulement en cas de changement de palier de risque (tous), de choc de marché (variation du jour d'au moins 3 % d'un indice suivi : actions et matières premières) ou d'événement géopolitique de gravité ≥ 4 (pays concernés et matières premières).
- **Revue hebdomadaire** le samedi, avec l'analyse complète : `data/recap/chef-hebdo-AAAA-MM-JJ.md` (verdicts modifiés, verdicts positifs, performance, évolution de l'allocation).

## 8. Limites connues

- Les flux d'investissement ne couvrent que les ETF cotés aux États-Unis ; beaucoup de pays sont encore « en cours de constitution ».
- Le rendement allemand à 10 ans est une moyenne mensuelle (OCDE via FRED) ; le 2 ans est estimé par la pente 10 ans − 2 ans de la Bundesbank.
- Le rendement américain à 10 ans est reconstitué (taux réel DFII10 + point mort T10YIE) ; le 2 ans par la pente T10Y2Y.
- Les dates indicatives de l'agenda suivent une règle de calendrier, pas un calendrier officiel.
