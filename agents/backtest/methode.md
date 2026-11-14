# Backtest des règles de notation — méthode

Objectif : savoir **quels signaux des agents sont réellement prédictifs**, lesquels garder, alléger ou supprimer, et si les règles du chef d'orchestre et du trader tiennent sur 10 à 15 ans d'historique. Le backtest **ne modifie aucun réglage** : il publie un rapport, un écran et une proposition de pondérations, à valider à la main dans une pull request séparée.

Code : `agents/backtest/` · paramètres : [`config.json`](config.json) · résultats : `data/backtest/` · workflow : `.github/workflows/backtest.yml` (manuel et mensuel).

## 1. Principe : rejouer les règles telles qu'elles sont

Chaque fin de mois depuis 2010, les notes sont **recalculées avec les fonctions mêmes des agents**, à partir des seules données publiées à cette date :

| Lot | Fonctions réutilisées | Univers |
|---|---|---|
| Pays | `agents/pays/notation.py` (barèmes, note globale, règle de prudence) | pays suivis par l'agent pays |
| Chef d'orchestre | `agents/chef/moteur.py` (score, verdicts, conviction, règle de momentum, conviction exigée pour « Renforcer fortement ») | pays |
| Entreprises | `agents/entreprises/analyse.py` et `financier.py` (mesures, barèmes, médianes sectorielles, note globale) | sociétés américaines non financières de l'agent entreprises |
| Matières premières | `agents/matieres_premieres/analyse.py` (tendance, stocks, positionnement, niveau, note par famille) | matières de l'agent (contrat le plus proche) |
| Secteurs | `agents/macro/analyse.py` (phase du cycle), `agents/chef/config.json` (inflexions sectorielles) | ETF sectoriels SPDR |

Une règle modifiée dans un agent est donc testée telle quelle au backtest suivant.

## 2. Données historiques (gratuites) et dates de publication

| Donnée | Source | Depuis | Date utilisée |
|---|---|---|---|
| Cours, dividendes, divisions | Yahoo Finance (yfinance) | 1993–2010 selon l'actif | clôture de fin de mois |
| Indicateur avancé (CLI) | OCDE (SDMX) | 2008 | publication + 2 mois |
| Inflation | OCDE (IPC, glissement annuel) | 2008 | publication + 1 mois |
| Taux directeurs | BRI (WS_CBPOL) | 2008 | + 1 mois |
| Croissance du PIB | FMI (DataMapper) | annuel | année écoulée, connue après la publication d'avril |
| Comptes des sociétés | SEC XBRL (companyfacts) | 2009 | **date de dépôt réelle** de chaque 10-K |
| Positionnement | CFTC, désagrégé (gérants) | juin 2006 | rapport du mardi + 3 jours |
| Stocks de brut et de gaz | EIA (fichiers historiques publics, sans clé) | 1982 / 2010 | relevé + 7 jours |
| Régime de marché | FRED (VIX) | 1990 | moyenne du mois |

**Comptes SEC « tels qu'ils étaient connus »** : chaque valeur garde sa date de dépôt (`filed`). À une date t, seuls les 10-K déposés au plus tard à t sont lus ; un retraitement n'est visible qu'après son propre dépôt ; la capitalisation est calculée avec le nombre d'actions déposé le plus récent (corrigé des divisions d'actions survenues depuis). Aucune donnée n'est donc connue après coup.

**Approximations** (signalées dans le rapport) :
- valorisation des pays : le PER historique des ETF n'est pas gratuit ; il est remplacé par le **rendement du dividende sur 12 mois de l'ETF pays** (PER implicite = 1 ÷ rendement), comparé à la médiane des pays avec le barème de l'agent pays ;
- structure de la courbe des matières : l'historique des échéances n'est pas gratuit ; elle est remplacée par le **rendement de portage** = performance de l'ETF à contrats (USO, UNG, CPER…) − performance du contrat le plus proche sur 3 mois, annualisée (positif = déport), avec le barème de l'agent ;
- paliers de risque : le VIX remplace les paliers de l'agent risque (sans historique) : « calme » sous 22, « tension » au-dessus ; ils pilotent les multiplicateurs de poids du chef d'orchestre (Calme / Tension) ;
- phase du cycle : règle de l'agent macro, sans la prévision du FMI (pas de millésimes datés) ;
- les séries de l'OCDE et du FMI sont les séries révisées (pas de millésimes d'origine) : malgré les retards appliqués, une révision ultérieure peut subsister.

## 3. Mesures, pour chaque signal et chaque note

Rééquilibrage **mensuel**. Rendements avec dividendes réinvestis, en dollars.

- **Meilleurs 20 % contre pires 20 %** : performance moyenne des deux paniers à 1, 3, 6 et 12 mois, et écart entre les deux.
- **Meilleurs 20 % contre l'indice de référence** : ACWI pour les pays (URTH n'existe que depuis 2012), SPY pour les entreprises et les secteurs, moyenne équipondérée de l'univers pour les matières premières.
- **Taux de réussite** : part des actifs du panier haut qui battent l'indice sur l'horizon (et du panier bas qui font moins bien) ; part des mois où le panier haut bat le panier bas.
- **Coefficient d'information (IC)** : corrélation de rang (Spearman) entre le signal et la performance future, date par date ; moyenne et statistique t de **Newey-West** (les rendements à 6 et 12 mois se chevauchent d'un mois sur l'autre : sans correction, la significativité serait surestimée).
- **Frais de transaction** : aller-retour par classe d'actifs (`config.json → frais`, d'après les frais et écarts achat/vente de l'agent trader), payé chaque mois sur la part renouvelée des deux paniers. L'**écart après frais** est annualisé.
- **Stabilité** : IC par année civile et part des années positives.
- **Régimes** : IC en mois calmes et en mois de tension.

## 4. Séparation stricte apprentissage / vérification

L'historique de chaque lot est coupé en deux à mi-parcours (ou à `periode.separation`) :
- **apprentissage** (première moitié) : seul usage permis pour régler les poids recalibrés ;
- **vérification hors échantillon** (seconde moitié) : juge les verdicts et les propositions.

### Verdict de chaque signal (horizon de référence : 6 mois pays et chef, 12 mois entreprises, 3 mois matières et secteurs)

| Verdict | Règle |
|---|---|
| **Données insuffisantes** | moins de 48 mois mesurés, ou de 24 mois hors échantillon, ou moins de 8 actifs par date : **aucune conclusion** |
| **Garder** | IC positif en apprentissage, IC ≥ 0,03 sur tout l'historique et hors échantillon, statistique t hors échantillon ≥ 1,5, écart meilleurs − pires positif après frais hors échantillon |
| **Supprimer** | IC hors échantillon ≤ 0 et IC sur tout l'historique ≤ 0,01 (aucun pouvoir prédictif, ou de sens contraire) |
| **Alléger** | les autres cas : signal faible, instable, peu significatif ou effacé par les frais |

Seuils dans `config.json → verdicts`. Un IC de 0,02 à 0,05 est courant pour un signal utile ; au-delà de 0,10, vérifier d'abord les données.

## 5. Règles du chef d'orchestre et du trader

Le chef d'orchestre est rejoué sur les pays avec les familles reconstituables : **fondamentaux** (moyenne des notes croissance, indicateur avancé, inflation, taux réel), **valorisation**, **tendance**, **cycle** (phase du pays, tableau `cycle.phases`). Le mélange percentile / note absolue, les multiplicateurs de régime, le score, les seuils des verdicts, l'exigence d'une famille motrice, la conviction (groupes concordants, famille solide), la règle de momentum extrême et le plafonnement de « Renforcer fortement » sont ceux de `agents/chef/moteur.py`. Les familles sans historique (flux, risque, géopolitique, dynamique des résultats) sont retirées et les poids renormalisés.

Tests :
- **pondérations** : score du chef contre chaque famille seule et contre les familles équipondérées ;
- **seuils des verdicts** : performance relative et réussite par verdict (règles de réussite de `chef.suivi`) ; les verdicts doivent être ordonnés ;
- **seuils de conviction** : réussite par niveau de conviction et par nombre de groupes concordants (seuils actuels : 3 pour « forte », 2 pour « moyenne ») ;
- **règle anti-euphorie** : après un momentum extrême (≥ 90e percentile ou ≥ +40 % sur 12 mois), la suite est-elle moins bonne que pour les autres tendances positives ? La valorisation tendue aggrave-t-elle le risque ?
- **concentration du trader** : cœur pays (verdicts positifs de conviction moyenne ou forte, poids ∝ conviction, 15 % au plus par ligne, excédent en liquidités) avec 4, 6, 8, 12 et 15 lignes et sans limite ; rendement, volatilité, ratio de Sharpe, perte maximale, frais compris ;
- **stops et prise de bénéfices** : chaque mois, les 10 sociétés les mieux notées sont gardées 12 mois, avec et sans les règles du trader (stop −15 %, suiveur 15 % sous le plus haut dès +20 %, 2 relevés de confirmation, un tiers vendu à +30 %) sur cours quotidiens.

Non testée : l'hystérésis (règle quotidienne, sans objet en rééquilibrage mensuel).

## 6. Note recalibrée et proposition de pondérations

- Facteur de chaque signal = IC d'apprentissage ÷ 0,05, borné entre 0 et 2, mélangé à parts égales avec 1 (**retrait vers le poids actuel**, contre le sur-ajustement) ; la somme des poids est conservée ; un signal non testé garde son poids.
- La note recalibrée est comparée à la note actuelle **hors échantillon** ; la proposition n'est **retenue** que si elle améliore à la fois l'IC et l'écart après frais.
- Fichiers concernés : `agents/pays/config.json` (`ponderations`), `agents/entreprises/config.json` (`ponderations`), `agents/matieres_premieres/config.json` (`familles.*.ponderations`), `agents/chef/config.json` (`poids.pays`, familles reconstituables seulement).
- Le workflow ouvre une **pull request séparée** (branche `backtest/proposition-AAAA-MM`) avec ces seules valeurs modifiées ; rien n'est fusionné automatiquement. Pour la préparer à la main : `python -m agents.backtest --appliquer-proposition data/backtest/proposition-AAAA-MM.json`.

## 7. Biais et garde-fous

- **Biais du survivant** : univers actuel (pays suivis, sociétés de la liste actuelle). Les sociétés disparues manquent : les signaux de solidité (Z-score, F-score, dette) et la performance absolue des paniers sont embellis. Les écarts entre signaux restent comparables entre eux.
- **Sur-ajustement** : réglage sur la première moitié seulement, retrait vers l'existant, adoption seulement si meilleur hors échantillon, validation humaine.
- **Petits échantillons** : verdict « Données insuffisantes » sans conclusion (seuils au § 4).
- **Non testables** faute d'historique, listés dans le rapport : géopolitique, flux des ETF, guidance et révisions, textes Gemini, activité réelle, risque pays et contradicteur ; achats d'initiés (formulaires 4) possibles en option dans un lot séparé si le temps de calcul le permet.

## 8. Exécution

- Workflow `backtest.yml` : à la main (onglet Actions → « Backtest » → « Run workflow ») et chaque mois (le 3 à 4 h 17 UTC). Lots en parallèle : SEC en 4 tranches (8 requêtes par seconde au plus), pays, matières premières, secteurs ; puis entreprises (comptes des 4 tranches), puis le rapport, commité sur `main`, et la pull request de proposition.
- Secrets : `SEC_USER_AGENT` (déjà utilisé par l'agent entreprises ; sans lui, le lot entreprises est signalé « non calculé »). Pour la pull request de proposition : réglage du dépôt « Allow GitHub Actions to create and approve pull requests » (Settings → Actions → General).
- Santé : `data/journal/agent-backtest.json` (écran « Santé des agents »).

```
pip install -r agents/requirements.txt
python -m agents.backtest                      # tout (vraies sources ; SEC_USER_AGENT pour les entreprises)
python -m agents.backtest --lot pays           # un lot
python -m agents.backtest --test --sortie /tmp/bt   # données synthétiques, sans réseau
python -m unittest discover -s agents/backtest -t . # tests
```
