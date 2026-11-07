# Agent matières premières — règles

Question posée : est-il pertinent de s'exposer à chaque grande matière première sur un horizon de 3 à 12 mois ?

## Périmètre

| Famille | Matières premières (symbole Yahoo) |
|---|---|
| Métaux précieux | or (GC=F), argent (SI=F), platine (PL=F), palladium (PA=F) |
| Métaux industriels | cuivre (HG=F), aluminium (ALI=F), uranium (ETF URA, **indicateur indirect**) |
| Énergie | pétrole WTI (CL=F), Brent (BZ=F), gaz naturel américain (NG=F), gaz européen TTF (TTF=F) |
| Agricoles | blé (ZW=F), maïs (ZC=F), soja (ZS=F), café (KC=F), sucre (SB=F), cacao (CC=F), coton (CT=F) |

## Sources (gratuites, croisées quand c'est possible)

| Donnée | Source | Rythme |
|---|---|---|
| Cours (10 ans) et courbe des prix à terme | Yahoo Finance (yfinance) : contrat le plus proche et 8 contrats suivants (ex. CLZ26.NYM, CLF27.NYM) | chaque soir |
| Positionnement | CFTC, Commitments of Traders « disaggregated » (API Socrata) : position nette des managed money | vendredi soir (positions du mardi) |
| Stocks d'énergie | EIA, API v2 (secret `EIA_API_KEY` ; sans clé : source « non configurée », sous-note absente) : brut hors réserve stratégique, Cushing, essence, distillats, gaz | mercredi (pétrole), jeudi (gaz) |
| Stocks agricoles | USDA : rapport WASDE (texte mensuel) et base PSD (totaux mondiaux recalculés) ; les deux sont comparés (tolérance 3 %) | mensuel |
| Moteurs macro | FRED : DFII10 (taux réel à 10 ans), DTWEXBGS (dollar), CPIAUCSL (inflation) ; agent macro (indicateur avancé de l'OCDE G20, phase du cycle) ; agent risque (palier) | chaque soir |
| Géopolitique | agent géopolitique (data/geopolitique.json) | chaque soir |
| Flux des ETF | GLD, IAU, SLV, USO, CPER, DBA : variation des parts en circulation × VL (méthode des ETF pays), historique accumulé par l'agent | chaque soir |

## Sous-notes (/100 ; au-dessus de 50 : favorable à une exposition)

1. **Tendance et momentum** : 50 + 0,8 × variation sur 3 mois + 0,3 × variation sur 12 mois, ± 5 selon la position par rapport à la moyenne 200 jours.
2. **Structure de la courbe** : rendement de roulement annualisé entre le premier contrat et celui d'environ 12 mois plus loin. Positif = backwardation (prix futurs plus bas : marché tendu) ; négatif = contango (prix futurs plus élevés : marché détendu). Note = 50 + 2,5 × rendement (10 à 90). « Plate » entre −2 % et +2 % par an.
3. **Stocks par rapport à la normale** : énergie, écart à la moyenne des 5 années précédentes à la même semaine (note = 50 − 2,5 × écart) ; agricoles, percentile du ratio stocks de fin de campagne / consommation mondiale depuis 1995 (note = 85 − 0,7 × percentile). Stocks bas = favorable.
4. **Positionnement (lecture à contre-courant aux extrêmes)** : percentile de la position nette sur 3 ans. Au-delà du percentile 90 (position encombrée, risque de retournement) : 25 ; en dessous du percentile 10 : 75 ; entre les deux, 50 + 0,2 × (50 − percentile).
5. **Moteurs macro** : or, 50 − 30 × variation du taux réel sur 3 mois (pt) − 3 × variation du dollar sur 3 mois (%) ; argent, 60 % or et 40 % cycle ; métaux industriels, platine, palladium, uranium et énergie, indicateur avancé de l'OCDE (niveau et variation sur 3 mois), phase du cycle, dollar, palier de risque (« Tension » −4, « Crise » −8) ; agricoles, dollar.
6. **Contexte géopolitique** : événements de gravité 3 ou plus sur 14 jours, de catégorie pertinente, touchant les 5 premiers producteurs ou une zone sensible pour l'approvisionnement (config « zones ») : 50 + 3 × Σ(gravité − 2), plafonné à 75. Métaux refuges (or, argent) : + 3 / 8 / 15 selon le palier de risque « Vigilance » / « Tension » / « Crise ».
7. **Flux des ETF** : flux nets sur 1 mois en % de l'encours : 50 + 6 × part (15 à 85). « En cours de constitution » tant que l'historique ne couvre pas un mois (pas de note).
8. **Niveau historique** : percentile du cours sur 10 ans, corrigé de l'inflation américaine : 80 − 0,6 × percentile (niveau bas = favorable).

Une sous-note sans donnée n'est pas comptée : sa pondération est répartie sur les autres.

## Note globale et verdict

- Pondérations par famille dans `config.json` (les stocks pèsent plus pour l'énergie et les agricoles, les moteurs macro — taux réels et dollar — pour les métaux précieux).
- **Surpondérer** : note ≥ 60 **et** au moins 2 sous-notes ≥ 60 (deux signaux concordants minimum) **et** une confiance « moyen » ou « élevé ».
- **Sous-pondérer** : note ≤ 40 **et** au moins 2 sous-notes ≤ 40 **et** une confiance « moyen » ou « élevé ».
- Seuil atteint sans l'une de ces deux conditions : **Neutre (biais positif)** ou **Neutre (biais négatif)**, avec la raison (`verdict_non_retenu`), affichée dans la fiche.
- Sinon **Neutre**. Hystérésis de 2 points pour éviter les allers-retours autour des seuils (elle ne lève jamais la condition de confiance).
- Contrôle final : avant d'écrire, l'agent vérifie la règle sur toutes les matières premières ; une anomalie arrête l'exécution sans rien écrire.
- **Confiance** : « élevé » avec au moins 6 sous-notes, une note éloignée d'au moins 12 points de 50 et des sous-notes peu dispersées (écart type < 20) ; « faible » avec 3 sous-notes ou moins, ou pour un indicateur indirect (uranium) ; sinon « moyen ».
- Chaque fiche donne 3 arguments pour, 3 arguments contre, « Ce qui pourrait me donner tort » et 2 conditions précises d'invalidation (moyenne 200 jours, structure de la courbe, percentile de positionnement, stocks, plus haut ou plus bas de 3 mois).
- Synthèse par famille : note moyenne ; « Surpondérer » ou « Sous-pondérer » si la moyenne est à moins de 5 points du seuil et que la moitié au moins des matières premières (2 au minimum) a ce verdict ; moyenne au-delà du seuil sans assez de recommandations retenues : neutre avec biais.

## Moyens de s'exposer (à titre informatif)

Types de supports (ETC physique, ETF ou ETC de contrats à terme avec le coût du contango chiffré à partir de la courbe, actions de producteurs) et sociétés productrices déjà analysées par l'agent entreprises (note, recommandation, lien vers la fiche). Si l'une d'elles figure dans le portefeuille ou la liste de surveillance (`config/surveillance.json`), la fiche signale la double exposition.

## Signaux (data/signaux/matieres_premieres.json)

- `changement_verdict` (importance forte) ;
- `positionnement_extreme` : passage au-delà du percentile 90 ou en dessous du percentile 10 ;
- `retournement_courbe` : passage de contango à backwardation, ou l'inverse ;
- `choc_stocks` : variation hebdomadaire EIA à plus de 2 écarts types, écart à la moyenne sur 5 ans qui franchit ±10 %, ou révision WASDE des stocks mondiaux de plus de 3 %.

## Règles de conduite

- Ton froid et factuel, sans euphorie (contrôle automatique des mots interdits).
- Deux signaux concordants au minimum et une confiance « moyen » ou « élevé » pour « Surpondérer » ou « Sous-pondérer ».
- Toujours citer la source et la date de chaque donnée ; l'uranium porte la mention « indicateur indirect ».
- Une source en panne n'arrête pas l'agent : la sous-note concernée est absente et l'écran Santé le signale.
