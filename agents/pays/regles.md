# Agent pays : règles de notation et de conduite

Ce document décrit **exactement** comment l'agent pays note chaque pays.
Le code correspondant se trouve dans `notation.py`. Les pondérations et les seuils « à vérifier » sont dans `config.json` et peuvent être modifiés sans toucher au code.

## 1. Sources

Les sources, leur hiérarchie (source nationale officielle > organisation internationale > source de marché) et la vérification croisée sont décrites dans **`sources.md`**.

En résumé :
- chaque indicateur est récupéré auprès de plusieurs sources quand c'est possible ;
- la valeur de la source prioritaire est retenue ;
- un écart supérieur à la tolérance marque l'indicateur « sources divergentes ».

| Indicateur | Définition | Fréquence |
|---|---|---|
| Croissance du PIB | croissance réelle de l'année en cours (FMI, comparé à l'OCDE) | annuelle (estimation) |
| Inflation | glissement annuel des prix à la consommation (institut national, OCDE ou Eurostat) | mensuelle |
| Indicateur avancé (OCDE) | Composite Leading Indicator (`DF_CLI`, amplitude ajustée) | mensuelle |
| Taux réel | taux directeur (banque centrale ou BRI) moins l'inflation retenue | mensuelle |
| Valorisation relative | PER (trailing) de l'ETF pays (Yahoo Finance), comparé à la médiane des pays suivis | quotidienne |
| Momentum boursier | performance de l'ETF pays sur 12 mois (en dollars) | quotidienne |
| Devise sur 3 mois (détail) | variation contre le dollar (BCE, sinon Yahoo Finance) ; indice DXY pour les États-Unis | quotidienne |
| Solde courant (détail) | % du PIB, dernière année écoulée (FMI et Banque mondiale) | annuelle |
| Flux étrangers (détail) | non disponible pour l'instant | — |

Chaque valeur publiée porte sa date, sa source exacte et la liste des sources consultées.

## 2. Notes par indicateur (/100)

| Indicateur | Règle | Repères |
|---|---|---|
| Croissance du PIB | `35 + 8 × croissance` | 0 % → 35 ; 2 % → 51 ; 4 % → 67 ; 6 % → 83 |
| Indicateur avancé | `50 + 10 × (CLI − 100) + 15 × pente sur 3 mois` | 100 et stable → 50 ; au-dessus de 100 et en hausse → au-dessus de 60 |
| Inflation | `90 − 15 × |inflation − cible|`, plafond 10 au-delà de 15 % | à la cible → 90 ; 2 pts d'écart → 60. La déflation est pénalisée comme l'excès. Cible par défaut : 2 %. |
| Taux réel | 80 entre +0,5 et +2,5 pts ; −12 par point en dessous de +0,5 ; −7 par point au-dessus de +2,5 ; +4 si la banque centrale baisse ses taux, −4 si elle les monte | Un taux réel très négatif signale une inflation mal tenue, donc un risque. Un taux très élevé signale une politique très restrictive. |
| Valorisation relative | `60 − écart` (écart du PER à la médiane, en %) | à la médiane → 60 ; 20 % plus cher → 40 ; 20 % moins cher → 80 |
| Momentum 12 mois | `50 + 1,2 × performance` | 0 % → 50 ; +20 % → 74 ; −20 % → 26 |
| Devise sur 3 mois | `55 + 4 × variation` (positif = appréciation contre le dollar) | — |
| Solde courant | `55 + 4 × solde (% du PIB)` | un excédent protège des chocs |

Toutes les notes sont bornées entre 0 et 100.

**Direction de la banque centrale** : on compare le taux directeur au taux d'il y a 6 mois.
- Écart de −0,25 pt ou plus bas : « baisse ».
- Écart de +0,25 pt ou plus haut : « hausse ».
- Entre les deux : « stable ».

## 3. Note globale

- La note globale est la moyenne pondérée des 6 indicateurs principaux. Pondérations par défaut (`config.json`) :
  - croissance 0,20 ;
  - indicateur avancé 0,15 ;
  - inflation 0,20 ;
  - taux réel 0,15 ;
  - valorisation 0,15 ;
  - momentum 0,15.
- Un indicateur manquant est **exclu** du calcul, et les autres sont repondérés. Son absence baisse le niveau de confiance.
- **Pas de conclusion forte sans deux indicateurs concordants** :
  - une note ≥ 65 (attractif) exige au moins deux indicateurs notés ≥ 65 ;
  - une note < 50 (défavorable) exige au moins deux indicateurs notés < 50 ;
  - sinon, la note est ramenée à 64 ou à 50, en zone neutre, et le verdict le dit ;
  - une valeur « à vérifier » ne compte pas comme confirmation.
- Les indicateurs du détail (devise, solde courant, flux étrangers) sont affichés mais n'entrent pas dans la note globale.

## 4. Niveau de confiance

Le score de départ est la **couverture**, c'est-à-dire la part des pondérations dont l'indicateur est disponible. On retire ensuite :
- 0,10 par valeur « ancienne » (source en panne, dernière valeur connue conservée) ;
- 0,10 par valeur « à vérifier » ;
- 0,10 par indicateur aux sources divergentes (vérification croisée, voir `sources.md`) ;
- 0,15 si les notes des indicateurs divergent fortement (écart-type supérieur à 22).

Le niveau est ensuite fixé ainsi :
- score ≥ 0,80 : **élevé** ;
- score ≥ 0,55 : **moyen** ;
- en dessous : **faible**.

Si plus de la moitié des indicateurs disponibles ne reposent que sur une seule source, le niveau est **plafonné à « moyen »**.

Chaque indicateur a aussi son propre niveau :
- **élevé** si ses sources concordent ;
- **moyen** s'il n'a qu'une source ;
- **faible** si ses sources divergent, ou si sa valeur est ancienne ou à vérifier.

Les raisons sont publiées avec le niveau.

## 5. Valeurs « à vérifier »

Une valeur est signalée « à vérifier » quand elle sort de l'intervalle habituel défini dans `config.json` (`seuils_a_verifier`), par exemple une croissance hors de −3 % à +8 %, ou une inflation hors de −2 % à 20 %.

Si une seconde source indépendante confirme la valeur, elle n'est **pas** signalée : elle n'est plus isolée. Par exemple, une inflation mensuelle confirmée par l'estimation annuelle du FMI.

## 6. Sources en panne

- Si une source échoue, l'agent ne s'arrête pas. Il garde la dernière valeur réelle connue avec sa date d'origine et la marque `"ancienne": true`, en précisant la raison.
- Les données fictives d'avant le premier passage de l'agent ne sont jamais réutilisées.
- Exception : une valeur mensuelle de plus de 6 mois n'est pas réutilisée.
- L'état de chaque source est publié dans `meta.etat_des_sources`.
- Les échecs et les rejets sont consignés dans `data/journal/agent-pays.json`.

## 7. Règles de conduite des textes

- **Ton** : analyse froide et factuelle. Les mots d'emphase sont interdits (« exceptionnel », « incontournable », « explosion », « euphorie », « spectaculaire »…). Ce contrôle est automatique : un texte non conforme est refusé.
- **Contenu** : pour chaque pays, l'agent publie :
  - un **verdict** en une phrase ;
  - un **niveau de confiance** ;
  - la rubrique **« Ce qui pourrait me donner tort »** (2 à 3 éléments concrets) ;
  - une **lecture** en trois paragraphes : activité et prix, politique monétaire et risques, marchés.
- **Rédaction** : la version 1 utilise des modèles de phrases à partir des chiffres. Si le secret GitHub `GEMINI_API_KEY` existe, l'API Gemini rédige le verdict et le contre-scénario, sous les mêmes contraintes. Un texte non conforme, une erreur ou une clé absente : on garde les textes par règles.

## 8. Historique

Chaque exécution qui change les données écrit `data/historique/pays/AAAA-MM-JJ.json`. Ce fichier contient la note, le niveau, la confiance, le verdict, ainsi que la valeur, la note et la date de chaque indicateur.

Il servira plus tard à mesurer si l'agent avait raison.
