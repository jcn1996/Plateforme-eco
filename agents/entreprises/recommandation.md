# Recommandation à 12 mois

Code : `agents/entreprises/recommandation.py` · seuils : section `recommandation` de
`agents/entreprises/config.json` (modifiables sans toucher au code) · suivi : `agents/entreprises/suivi.py`.

Calculée pour chaque société notée par l'agent entreprises (fiches, pépites, liste « qualité à prix
raisonnable ») et pour chaque analyse à la demande. Horizon : 12 mois (`horizon_mois`).

Chaque recommandation porte la mention : « Avis indicatif généré automatiquement, sans prise en compte
d'un profil ou d'une situation personnelle. »

## 1. Fourchette de valeur estimée

Valeurs par action, converties dans la devise de cotation (taux de change Yahoo Finance).

**Multiples comparés au secteur.** Valeur qu'aurait l'action si la société se payait au multiple médian
de son secteur (médiane régionale du secteur, à défaut mondiale ; au moins 5 sociétés) :

- PER : médiane du PER × résultat net (4 derniers trimestres, à défaut dernier exercice) ÷ nombre d'actions ;
- VE/EBITDA (sociétés non financières) : (médiane × EBITDA − dette nette) ÷ nombre d'actions.

Fourchette : de la plus basse à la plus haute des deux estimations (± 10 % s'il n'y en a qu'une).

**Flux de trésorerie disponibles actualisés (DCF simplifié).** Sociétés non financières dont le flux de
trésorerie disponible (FCF) du dernier exercice est positif :

- croissance initiale = tendance du chiffre d'affaires sur 3 ans (à défaut 1 an), bornée entre
  `croissance_min` (0 %) et `croissance_max` (10 %) ; 3 % si inconnue ;
- ramenée linéairement à la croissance terminale (`croissance_terminale`, 2 %) en `annees` (5) ans ;
- taux d'actualisation = `taux_base` (8 %) + prime de la région (`primes_region` : 0 pt Amérique du Nord,
  0,5 pt Europe, 1,5 pt Asie-Pacifique, 3 pts Amérique latine et Moyen-Orient–Afrique) ;
- valeur terminale de Gordon-Shapiro, dette nette déduite ;
- fourchette : taux ± `ecart_taux` (1 pt) et croissance ∓ `ecart_croissance` (2 pts).

Les hypothèses retenues sont affichées sur la fiche. Banques et assurances : multiples (PER) seulement.

**Synthèse.** Valeur centrale, bas et haut = moyennes des méthodes disponibles. Écart au cours
= valeur centrale ÷ cours − 1. L'estimation est déclarée **non exploitable** pour le signal de
valorisation (mais reste affichée) quand les deux méthodes divergent de plus d'un facteur
`divergence_max` (3) ou quand l'écart sort de la plage `ecart_plausible` (−80 % à +300 %).

## 2. Cinq signaux

| Signal | Favorable | Défavorable | Seuils |
|---|---|---|---|
| Note globale | ≥ 65/100 | < 50/100 | `note_positive`, `note_negative` |
| Valorisation | valeur estimée ≥ cours + 15 % | ≤ cours − 15 % | `valorisation_positive`, `valorisation_negative` |
| Momentum 12 mois | ≥ +5 % | ≤ −10 % | `momentum_positif`, `momentum_negatif` |
| Qualité comptable | F-score ≥ 6 sans alerte (financières : ROE ≥ 10 % sans alerte) | signal d'alerte comptable, ou F-score ≤ 3 | `fscore_positif`, `fscore_negatif`, `roe_financier_min` |
| Dynamique des résultats | note du bloc ≥ 65/100 | < 40/100 | section `dynamique` (voir `dynamique.md`) |

Un signal non calculable est neutre.

## 3. Règles

Section `regles` ; « concordants » = de même sens.

**Si non détenu**

- **Acheter** : au moins `signaux_concordants_min` (3) signaux favorables, aucun défavorable, confiance
  « moyen » ou « élevé » (`confiances_tranchees`), **aucun signal d'alerte comptable**, **aucune guidance
  abaissée ou retirée depuis moins de 90 jours** (sauf si la valorisation intègre déjà une forte baisse :
  valeur estimée au moins 30 % au-dessus du cours et momentum 12 mois ≤ −15 %, exception justifiée en
  chiffres ; section `dynamique.exception_guidance`).
- **Acheter sur repli** : toutes les conditions d'« Acheter » sont réunies sauf la valorisation
  (2 autres signaux favorables, aucun défavorable, confiance suffisante, pas d'alerte, estimation
  exploitable). Le **prix de repli** est le cours à partir duquel la valorisation deviendrait favorable,
  donc la recommandation passerait à « Acheter » : valeur centrale ÷ 1,15. Ce prix doit être au plus
  `repli_max_pct` (25 %) sous le cours ; plus loin, la recommandation est « Attendre » (le niveau reste indiqué).
- **Éviter** : au moins `eviter_negatifs_min` (2) signaux défavorables, plus nombreux que les favorables.
- **Attendre** : dans les autres cas.

**Si détenu**

- **Renforcer** : mêmes conditions qu'« Acheter ».
- **Vendre** : au moins 3 signaux défavorables, aucun favorable, confiance « moyen » ou « élevé ».
- **Alléger** : au moins `alleger_negatifs_min` (2) signaux défavorables, plus nombreux que les favorables ;
  ou valeur estimée inférieure d'au moins `alleger_survalorisation_pct` (40 %) au cours avec une note
  globale sous 65.
- **Conserver** : dans les autres cas.

Quand « Acheter » ou « Vendre » sont écartés par la règle de confiance ou par un signal d'alerte, la
justification l'indique.

## 4. Conditions d'invalidation et risques

Toujours 2 ou 3 conditions précises, chiffrées, qui invalideraient la recommandation :

- recommandation favorable : ce qui annulerait chacun des signaux favorables (ex. « Cours au-dessus de
  X : l'écart à la valeur estimée passerait sous +15 % », « Note globale sous 65/100 à la prochaine
  révision des comptes ») ;
- recommandation défavorable : ce qui retournerait les signaux défavorables ;
- « Attendre », « Conserver », « Acheter sur repli » : ce qui ferait apparaître les signaux manquants.

Principaux risques : les indicateurs les plus faibles (revue critique) puis « Ce qui pourrait me donner
tort », 3 au plus.

## 5. Suivi et fiabilité

`python -m agents.entreprises.suivi` écrit `data/historique/recommandations.json` (une recommandation
par ligne) : date, cours, devise, recommandations (non détenu et détenu), fourchette, écart, prix de
repli, confiance, note.

- Agent entreprises : une ligne quand la recommandation d'une société change, au plus une fois tous
  les `suivi.intervalle_min_jours` (7) jours. Analyses à la demande : chaque analyse.
- Performance à 3, 6 et 12 mois : cours ajustés des dividendes (Yahoo Finance), comparée à l'ETF
  iShares MSCI World (URTH) sur la même période ; performance relative = société − indice.
- Réussite (`suivi.reussite`), sur la performance relative :
  Acheter, Renforcer > 0 ; Acheter sur repli, Conserver > −5 % ; Attendre : entre −10 % et +10 % ;
  Alléger < +5 % ; Éviter, Vendre < 0.
- Taux de réussite par type et par horizon, et performance relative moyenne : `meta.fiabilite`,
  affichés dans l'écran « Fiabilité des recommandations » de l'appli.

Le script est lancé par les workflows « Agent entreprises » et « Analyse à la demande » juste avant de
pousser, sur l'état le plus récent du dépôt : c'est le seul à écrire ce fichier.
