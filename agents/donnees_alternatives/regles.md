# Agent données alternatives — règles

## Objet

Repérer l'activité réelle avant les statistiques officielles, à partir d'indicateurs indirects publiés
gratuitement : kilomètres parcourus par les poids lourds (Allemagne, États-Unis), fret vrac et conteneurs,
ciment (Chine, États-Unis), mises en chantier, exportations coréennes, commandes à l'export de Taïwan,
électricité (Chine, Europe, États-Unis), offres d'emploi (Indeed), passagers aériens (TSA), satellites
(dioxyde d'azote, lumières nocturnes) ; attention du public (Wikipédia, Google Trends) pour les sociétés
suivies, en information seulement.

## Sources

Gratuites uniquement. Clés et adresses facultatives : sans elles, la source est « non configurée »,
ignorée, ni comptée ni signalée comme en panne (écran « Santé des agents »).

| Secret ou variable | Source | Où l'obtenir |
|---|---|---|
| `ENTSOE_API_KEY` (secret) | ENTSO-E, consommation d'électricité en Europe | compte gratuit sur transparency.entsoe.eu, puis demande d'accès à l'API (« Restful API access ») par courriel à transparency@entsoe.eu ; le jeton apparaît ensuite dans « My Account Settings » |
| `EIA_API_KEY` (secret, déjà utilisé) | EIA, demande d'électricité américaine | eia.gov/opendata |
| `FRED_API_KEY` (secret, facultatif) | FRED (sinon fichier CSV public) | fred.stlouisfed.org |
| `SATELLITES_URL` (variable) | CSV « date,pays,indicateur,valeur » (no2, lumieres) | voir outils/satellites_gee.js |
| `COREE_EXPORTS_20J_URL`, `TAIWAN_COMMANDES_URL` (variables) | CSV au même format | toute source publique que vous maintenez |

## Calculs (analyse.py)

- Chaque série est ramenée à des moyennes mensuelles ; pour les séries quotidiennes et hebdomadaires, les
  variations sur 1 et 12 mois comparent les 28 derniers jours aux 28 jours précédents et aux mêmes 28 jours
  un an plus tôt (décalage de 364 jours, mêmes jours de la semaine).
- Écart à la tendance : moyenne des 3 derniers mois contre celle des 12 derniers.
- Écart à la normale saisonnière : dernier mois contre (moyenne des 12 mois précédents × facteur saisonnier
  moyen de ce mois calendaire les années passées), à partir de 3 ans d'historique.
- Percentile historique : rang de la variation sur 12 mois parmi toutes les variations sur 12 mois passées.
- Note d'activité /100 : 60 % percentile de la variation sur 12 mois + 40 % percentile de l'écart à la
  tendance ; historique trop court : échelle fixe (50 + 50 × tanh(variation / 12)), signalée.
- Donnée périmée (au-delà de 21 jours pour une série quotidienne ou hebdomadaire, 110 jours pour une série
  mensuelle, 150 pour l'USGS) : affichée, exclue du score.

## Score par pays

- Au moins 2 indicateurs à jour, sinon pas de score : **aucune conclusion sur un seul indicateur**.
- Score = moyenne pondérée des notes (poids en config).
- « accélération » : score ≥ 60 et au moins 2 indicateurs ≥ 55 ; « ralentissement » : score ≤ 40 et au
  moins 2 indicateurs ≤ 45 ; sinon « stable ».
- Confiance : réduite avec deux indicateurs seulement, des notes peu concordantes, une série approchée
  (ETF BDRY) ou expérimentale (indice quotidien des camions allemands), un historique court, des données
  périmées. « élevé » exige au moins 3 indicateurs.
- « Ce qui pourrait me donner tort » : indicateurs à contre-sens, faible nombre d'indicateurs, sensibilité
  de l'électricité aux températures, révisions des données mensuelles.
- Divergence avec l'officiel : note moyenne de la croissance du PIB et de l'indicateur avancé de l'OCDE
  (agent pays) ≥ 60 alors que le score alternatif ≤ 40 avec 2 indicateurs en baisse, ou l'inverse
  (officiel ≤ 45, alternatif ≥ 60 avec 2 indicateurs en hausse).

## Signaux (data/signaux/donnees_alternatives.json)

- `activite_acceleration` / `activite_ralentissement` : lecture marquée (score ≥ 70 ou ≤ 30) nouvelle.
- `divergence_officielle` : nouvelle divergence avec les statistiques officielles.
- `attention_forte_hausse` (importance faible) : attention du public doublée — information seulement.

## Agent pays

Le score devient la sous-note « Activité réelle » (pondération 0,10 dans agents/pays/config.json), comptée
seulement pour les pays qui en ont une, sans réduire la couverture des autres. Fichier de plus de 4 jours :
ignoré.

## Rédaction

Ton froid et factuel, chiffres datés, source citée ; pas de superlatif ni d'injonction d'achat ou de vente.
