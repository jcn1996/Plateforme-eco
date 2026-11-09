# Analyse financière approfondie

Code : `agents/entreprises/financier.py` (fonctions pures) · paramètres : section `analyse_financiere` de
`agents/entreprises/config.json` (barèmes, familles, coût du capital) et pondérations dans `ponderations` ·
tests : `agents/entreprises/tests/test_financier.py`.

## Données

- **Yahoo Finance** : 5 exercices annuels (compte de résultat, bilan, flux de trésorerie), détention des
  dirigeants (`heldPercentInsiders`) et bêta.
- **SEC (XBRL companyfacts)**, sociétés américaines : jusqu'à 6 exercices de chiffre d'affaires, résultat net,
  résultat opérationnel, marge brute et flux d'exploitation. La SEC l'emporte sur Yahoo pour l'exercice commun ;
  ses exercices plus anciens complètent la série jusqu'à 5 ans.
- **ESEF** : comptes officiels du dernier exercice (vérification croisée, comme avant).
- Un indicateur dont une donnée manque **n'est pas calculé** : jamais d'hypothèse silencieuse. Deux exceptions
  documentées : stocks absents = 0 dans le cycle de conversion du cash (services) ; DEPI et SGAI fixés à 1
  (neutres) dans le M-score quand amortissements ou frais commerciaux manquent (indiqué sur la fiche).

## Indicateurs

### Valeur et cycle

| Indicateur | Calcul |
|---|---|
| Rendement du FCF | flux de trésorerie disponible du dernier exercice / capitalisation (devise des comptes) |
| Bénéfices normalisés | bénéfice actuel (4 derniers trimestres, à défaut dernier exercice) / moyenne des résultats nets sur 5 ans (3 au moins) |
| ROIC − WACC | ROIC (résultat opérationnel après impôt / capital investi) moins le coût du capital estimé (voir ci-dessous) |
| Régularité sur 5 ans | moyenne de deux notes : part des années de hausse du CA ; écart-type de la marge opérationnelle (4 exercices au moins) |
| Rendement pour l'actionnaire | (dividendes versés + rachats d'actions − émissions d'actions) / capitalisation |

**Sommet de cycle possible** (`normalisation`) : rapport bénéfice actuel / moyenne au-dessus de 1,5 **et**
écart non expliqué par la croissance du chiffre d'affaires (rapport des bénéfices ÷ rapport CA du dernier
exercice / CA moyen au-dessus de 1,25, c'est-à-dire une marge nette nettement au-dessus de sa moyenne) **et**
marge nette au plus haut des exercices étudiés, avec au moins 4 exercices. Une société en croissance régulière à
marge stable (Microsoft) ou qui sort d'un creux (restructuration) n'est donc pas signalée. Conséquences :

- **valorisation** : la méthode des multiples utilise le bénéfice moyen, le DCF le plus bas du flux de trésorerie
  disponible actuel et moyen ; la justification de la recommandation le dit ;
- **recommandation** : risque listé (« Ce qui pourrait me donner tort », piège de valeur possible) ;
- **pépites** : exclusion (`pepites.exclure_sommet_cycle`).

La note de l'indicateur se lit sur le rapport corrigé de la croissance du CA (bénéfice actuel négatif : 30/100).

**Coût du capital estimé** (`wacc`) : fonds propres = taux sans risque (4 %) + prime de la région (celle du DCF :
0 à 3 points) + bêta (Yahoo, borné entre 0,5 et 2 ; 1 s'il manque) × prime de marché (5 %) ; dette = intérêts /
dette totale, borné entre le taux sans risque (avec prime) et 8 points de plus (à défaut + 2 points) ; après
impôt (taux effectif, à défaut 25 %) ; pondération capitalisation / dette totale. Toutes les hypothèses sont
affichées sur la fiche (« Hypothèses et calculs »).

### Solidité et fiabilité

| Indicateur | Calcul |
|---|---|
| Z-score d'Altman | 1,2 × fonds de roulement + 1,4 × bénéfices non distribués + 3,3 × EBIT + 0,6 × capitalisation / passifs totaux + 1,0 × CA, chaque terme rapporté à l'actif total (sauf le 4e). Zones : sûre > 2,99 ; grise ; détresse < 1,81 |
| M-score de Beneish | 8 variables : −4,84 + 0,920 DSRI + 0,528 GMI + 0,404 AQI + 0,892 SGI + 0,115 DEPI − 0,172 SGAI + 4,679 TATA − 0,327 LVGI. Au-dessus de −1,78 : **signal d'alerte comptable** |
| Goodwill / actif total | goodwill (à défaut goodwill et incorporels, indiqué) / actif total |
| Current ratio | actifs courants / passifs courants |

- **Banques et assurances** : Z-score, M-score, current ratio, ratios d'exploitation, rendement du FCF et ROIC −
  WACC ne sont pas calculés (non pertinents).
- **M-score suspect** : signal d'alerte comptable, avec les mêmes effets que les autres (interdit « Acheter » et
  « Renforcer », exclut des pépites, signal de qualité défavorable). Limite connue : une croissance très rapide
  (SGI élevé) le fait monter.
- **Z-score en zone de détresse** : exclusion des pépites (`pepites.exclure_zscore_detresse`). Dans la
  recommandation, signal de qualité défavorable **seulement s'il est confirmé** par un autre signe de fragilité
  (couverture des intérêts sous 3, flux de trésorerie disponible négatif ou current ratio sous 1) : le Z-score
  seul pénalise les sociétés à filiale de financement (Toyota) et celles qui ont beaucoup racheté leurs actions
  (bénéfices non distribués faibles, voire négatifs).

### Qualité

| Indicateur | Calcul |
|---|---|
| Marge brute | marge brute / CA ; note ajustée de +5 si son écart-type sur 5 ans ≤ 2 points, −5 s'il ≥ 8 points |
| Cycle de conversion du cash | jours de créances + jours de stocks − jours de fournisseurs (créances / CA ; stocks et fournisseurs / coût des ventes ; × 365) |
| Capex / amortissements | investissements / dotations aux amortissements |
| Intensité en R&D | R&D / CA, technologies de l'information et santé seulement (`secteurs_rd`) |

### Alignement

| Indicateur | Calcul |
|---|---|
| Capital détenu par les dirigeants | part détenue par les dirigeants et administrateurs (Yahoo Finance) |
| Nombre d'actions sur 3 ans | variation du nombre d'actions entre le dernier exercice et celui d'il y a 3 ans (baisse = rachats nets) |

## Notes, sous-notes et note globale

- Chaque indicateur reçoit une note sur 100 (barèmes `baremes`, interpolation linéaire bornée).
- **Sous-notes** : moyenne des notes disponibles de chaque famille (`familles`), en reprenant aussi les
  indicateurs de base de la famille (dette nette / EBITDA et couverture des intérêts en solidité ; F-score et
  conversion en cash en qualité).
- **Note globale** : moyenne pondérée de tous les indicateurs disponibles (`ponderations`, somme 1 ; analyse
  approfondie environ 40 % pour les sociétés non financières, 20 % pour les financières), puis bloc « Dynamique des
  résultats » (8 %). La règle des deux signaux concordants s'applique comme avant.
- **Couverture et confiance** : la couverture se mesure sur les indicateurs de base seulement
  (`couverture_sur`) ; un indicateur approfondi absent ne fait pas baisser la confiance.
- **Changement de méthode** : quand la fiche précédente a été notée sans l'analyse approfondie, ou avec d'autres
  indicateurs approfondis (comptes relus au samedi), aucune tendance de note n'est affichée et aucun signal
  « variation de note » ni « alerte comptable » (M-score) n'est émis pour ce seul changement.

## Fiche entreprise

Bloc « Analyse financière approfondie » : quatre sous-notes, indicateurs par famille (valeur, note, complément),
mention du sommet de cycle possible, et « Hypothèses et calculs » (coût du capital, composantes du Z-score,
variables du M-score, normalisation). L'étude complète a un paragraphe « Cycle, solidité et alignement ».
