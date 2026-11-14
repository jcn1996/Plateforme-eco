# Backtest des règles de notation — méthode

Objectif : savoir **quels signaux des agents sont réellement prédictifs**, lesquels garder, alléger ou supprimer, et si les règles du chef d'orchestre et du trader tiennent sur 10 à 15 ans d'historique. Le backtest **ne modifie aucun réglage** : il publie un rapport, un écran et une proposition de pondérations, à valider à la main dans une pull request séparée.

Code : `agents/backtest/` · paramètres : [`config.json`](config.json) · résultats : `data/backtest/` · workflow : `.github/workflows/backtest.yml` (manuel et mensuel).

## 1. Principe : rejouer les règles telles qu'elles sont

Chaque fin de mois depuis 2010, les notes sont **recalculées avec les fonctions mêmes des agents**, à partir des seules données publiées à cette date :

| Lot | Fonctions réutilisées | Univers |
|---|---|---|
| Pays | `agents/pays/notation.py` (barèmes, note globale, règle de prudence) | pays suivis par l'agent pays |
| Chef d'orchestre | `agents/chef/moteur.py` (score, verdicts, conviction, suivi de tendance, conviction exigée pour « Renforcer fortement ») | pays |
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
- **Cible** (à 3 et 6 mois, pour chaque signal et chaque combinaison) : part des actifs retenus qui battent l'indice, gain moyen de ceux qui le battent, perte moyenne des autres et **rapport gain / perte** (au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).
- **Panier des meilleurs 20 %** de chaque signal et de chaque note, rééquilibré chaque mois, frais compris : rendement annuel, comparé à l'indice **et au « momentum seul »** (§ 3 bis), sur l'apprentissage et hors échantillon.

### 3 bis. Référence simple : « momentum seul »

Pour les pays, les entreprises et les matières premières : à chaque fin de mois, les **meilleurs 20 % sur 12 mois hors dernier mois** (cours de t − 12 à t − 1 ; le dernier mois, souvent en retournement, est exclu), équipondérés, rééquilibrés chaque mois, **frais compris** (même coût que les autres paniers). Pour les entreprises, même univers que les notes (sociétés valant au moins 2 Md$ à la date). C'est la règle sans analyse qu'une note doit battre pour être utile : le rapport compare chaque note et chaque combinaison à l'indice et à cette référence (`reference.py`).

### 3 ter. Signaux en variation

Chaque signal de niveau a aussi sa **variation**, testée comme un signal distinct (mêmes mesures, même verdict) et calculée sur des séries déjà décalées de leur délai de publication, donc **sans donnée connue après coup** :
- **pays** : variation sur 3 et 6 mois de la note de la croissance, de l'indicateur avancé, de l'inflation, du taux réel, de la devise et de la valorisation (`var3_…`, `var6_…`). La note porte le sens des barèmes de l'agent pays : une hausse est une amélioration (pour l'inflation et le taux réel, un rapprochement de la zone jugée saine) ;
- **entreprises** : variation entre les **deux derniers exercices déposés** de la marge opérationnelle, de la marge brute et de l'intensité en R&D (en points de chiffre d'affaires), et accélération de la croissance du CA (croissance du dernier exercice − celle du précédent). Les 10-K étant annuels, une variation « sur 3 ou 6 mois » d'un chiffre annuel serait presque toujours nulle ; chaque variation n'est connue qu'après le dépôt de l'exercice le plus récent ;
- **matières premières** : variation sur 3 et 6 mois des stocks (écart à la moyenne sur 5 ans ; une **baisse** est comptée favorable) et du positionnement des gérants (position nette en % de l'intérêt ouvert ; des **achats** sont comptés favorables). Décalages : EIA + 7 jours, CFTC + 3 jours.

Les variations ne changent pas les notes des agents ni les propositions de pondérations (elles n'existent dans aucun réglage) : elles disent seulement si une évolution anticipe mieux qu'un niveau.

### 3 quater. Combinaisons de signaux (`combinaisons.py`)

- **Règle** : un actif est retenu seulement s'il est dans les **meilleurs 30 %** (percentile > 70 dans sa classe, date par date) sur **chacun** des signaux combinés ; panier équipondéré, rééquilibrage mensuel, frais compris ; un mois sans aucun actif retenu, le panier reste dans l'indice.
- **Candidats** : signaux classés « Garder » ou « Alléger », avec un IC positif sur l'apprentissage, au plus 8 (les meilleurs IC d'apprentissage), notes exclues ; deux variations du même indicateur ne sont pas combinées entre elles. D'où **au plus 28 paires et 56 triplets** par lot.
- **Choix sur l'apprentissage seulement** : les combinaisons sont classées par la statistique t de leur écart à l'indice sur la première moitié (au moins 36 mois, et des actifs retenus au moins un mois sur deux). Le rapport indique le **seuil de Bonferroni** pour le nombre d'essais (t ≈ 3,2 pour 84 essais au lieu de 1,65 pour un seul) et combien de combinaisons le franchissent : sans cette correction, sur 84 essais, environ 4 « réussiraient » par pur hasard.
- **Jugement hors échantillon** : les 5 meilleures de l'apprentissage seulement sont mesurées sur la seconde moitié ; p-value unilatérale de leur écart à l'indice, **corrigée par la méthode de Holm** sur ces 5 essais.
- **Verdict** : « Confirmée » si la p-value corrigée est sous 5 % et que l'écart hors échantillon est positif face à l'indice **et** au momentum seul ; « Prometteuse (non significative) » si l'écart à l'indice est positif sans être significatif ; « Non confirmée » sinon.
- **Limite assumée** : la liste des candidats s'appuie sur le verdict de chaque signal, qui regarde aussi la seconde moitié ; l'exigence d'un IC d'apprentissage positif et les deux corrections (Bonferroni pour classer, Holm pour juger) sont là pour compenser. Une combinaison « Prometteuse » n'est pas une preuve.

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

Le chef d'orchestre est rejoué sur les pays avec les familles reconstituables : **fondamentaux** (moyenne des notes croissance, indicateur avancé, inflation, taux réel), **valorisation**, **tendance**, **cycle** (phase du pays, tableau `cycle.phases`). Le mélange percentile / note absolue, les multiplicateurs de régime, le score, les seuils des verdicts, l'exigence d'une famille motrice, la conviction (groupes concordants, famille solide), le suivi de tendance (`agents/chef/tendance.py`, reconstitué sur les cours mensuels de l'ETF : 12-1, moyenne 10 mois à la place de la moyenne 200 jours, accélération sur 1 mois) et le plafonnement de « Renforcer fortement » sont ceux de `agents/chef/moteur.py`. Les familles sans historique (flux, risque, géopolitique, dynamique des résultats) sont retirées et les poids renormalisés.

Tests :
- **pondérations** : score du chef contre chaque famille seule et contre les familles équipondérées ;
- **seuils des verdicts** : performance relative et réussite par verdict (règles de réussite de `chef.suivi`) ; les verdicts doivent être ordonnés ;
- **seuils de conviction** : réussite par niveau de conviction et par nombre de groupes concordants (seuils actuels : 3 pour « forte », 2 pour « moyenne ») ;
- **suivi de tendance** : les tendances fortes saines (premier tiers de force relative, tendance positive, sans excès) font-elles mieux ensuite que les autres pays ? Les tendances fortes en excès font-elles moins bien ?
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

## 7 bis. Résumé du rapport

Le rapport se termine par **« En bref »**, dix lignes au plus en langage simple, entièrement tirées des chiffres : ce qui anticipe (verdict « Garder »), les combinaisons confirmées, ce qui n'anticipe pas (« Supprimer »), ce qui marche à l'envers (t ≤ −2), le momentum seul face à l'indice, les notes et combinaisons qui battent (ou non) le momentum seul hors échantillon, un bilan et les précautions. Le même résumé s'affiche en tête de l'écran « Backtest ».

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

## Lot « tendance » (suivi de tendance)

`agents/backtest/tendance.py`, `python -m agents.backtest --lot tendance`. Univers : ETF pays (agent pays), ETF sectoriels américains (SPDR) et ETF de matières premières (`matieres.etf_portage`, rendements investissables sans saut de changement d'échéance). Cours ajustés quotidiens (Yahoo Finance) ; ordres passés à la clôture du jour de bourse qui suit la décision ; frais de la moitié d'un aller-retour par ordre.

1. **Périodes de momentum** : 12-1, 12, 6-1, 6 et 3-1 mois ; IC de Spearman dans chaque catégorie à 1 et 3 mois, écart premier − dernier tiers. Période retenue : meilleur IC moyen sur l'apprentissage.
2. **Filtre de tendance** : premier tiers de force relative avec ou sans tendance positive (12-1 > 0 et cours > moyenne 200 jours).
3. **Excès** parmi les tendances fortes, pour chaque seuil d'une grille (`tendance.grilles`) : accélération parabolique (hausse sur 1 mois > k × écart-type mensuel des 12 mois précédents), valorisation tendue (pays : rendement du dividende sous le (100 − p)e percentile de ses 5 dernières années), positionnement encombré (matières : percentile CFTC sur 3 ans ≥ p). Seuil retenu : écart le plus défavorable aux actifs en excès sur l'apprentissage (20 cas au moins) ; « confirmé » s'il garde son signe hors échantillon.
4. **Poche « tendance »** : simulation quotidienne de 6 lignes au plus, achetées en fin de mois parmi les tendances fortes (parts égales de la poche à l'achat, gagnants jamais allégés), avec plusieurs stops (aucun, moyenne 200 jours, −8 à −20 % du plus haut, combinaisons, filtre des excès) et sortie quand la force relative quitte le premier tiers ou que la tendance casse. Variante retenue : meilleur ratio de Sharpe sur l'apprentissage parmi celles qui ne font pas moins bien hors échantillon que la sortie sur la force relative seule (garde-fou contre une variante réglée sur le hasard de la première moitié). Références : univers équipondéré et indice mondial (ACWI).

Résultats du 14/11/2026 : `data/backtest/tendance-2026-11.md` ; seuils reportés dans `agents/chef/config.json` (`suivi_tendance`) et `agents/trader/config.json` (`tendance`).
