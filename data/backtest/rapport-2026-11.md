# Backtest des règles de notation — 2026-11

Rapport produit automatiquement par l'agent backtest (`agents/backtest/`, méthode : `agents/backtest/methode.md`). Rééquilibrage mensuel ; meilleurs 20 % contre pires 20 % et contre l'indice de référence ; coefficient d'information (IC, corrélation de rang entre le signal et la performance future) ; frais de transaction inclus dans l'écart annuel. Les verdicts se jugent hors échantillon (seconde moitié de l'historique).

**Rien n'est modifié automatiquement** : les nouvelles pondérations sont seulement proposées dans une pull request séparée.

## Synthèse

Alléger : 38 · Données insuffisantes : 4 · Garder : 2 · Supprimer : 27

## Pays

**Biais du survivant mesuré** : l'univers actuel, équipondéré et rejoué dans le passé, fait −3,6 pt/an par rapport à l'indice. Les pays suivis existent tous depuis le début : l'écart traduit surtout le poids des États-Unis dans l'indice, pas un biais du survivant ; les signaux se jugent entre pays.

Horizon de référence : 6 mois · indice : ACWI · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 30 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (6 m) | Meilleurs − indice (6 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Momentum 12 mois | **Alléger** | +0,002 | +0,063 (t = 1,4) | +0,43 % | −1,64 % | +1,2 % | 43 % | +0,033 / +0,025 | 53 % | 197 |
| Valorisation relative | **Alléger** | −0,006 | +0,039 (t = 0,7) | +0,50 % | −1,46 % | +4,6 % | 40 % | +0,019 / +0,003 | 53 % | 196 |
| Indicateur avancé (OCDE) — variation 3 mois | **Alléger** | +0,082 | −0,059 (t = −1,5) | +0,95 % | −2,00 % | +9,0 % | 42 % | +0,027 / −0,041 | 47 % | 195 |
| Inflation — variation 3 mois | **Alléger** | −0,023 | +0,057 (t = 2,2) | +0,53 % | −1,99 % | +2,5 % | 39 % | +0,005 / +0,058 | 47 % | 195 |
| Taux réel — variation 3 mois | **Alléger** | −0,026 | +0,010 (t = 0,3) | −0,18 % | −2,28 % | −3,0 % | 40 % | −0,008 / −0,009 | 35 % | 195 |
| Inflation — variation 6 mois | **Alléger** | −0,051 | +0,029 (t = 1,1) | +0,06 % | −2,60 % | +0,7 % | 40 % | −0,032 / +0,066 | 41 % | 192 |
| Taux réel — variation 6 mois | **Alléger** | −0,030 | +0,019 (t = 0,5) | −0,46 % | −2,33 % | +0,9 % | 41 % | −0,005 / −0,007 | 41 % | 192 |
| Croissance du PIB | **Supprimer** | −0,082 | −0,039 (t = −1,0) | −2,54 % | −3,58 % | −5,9 % | 36 % | −0,096 / +0,070 | 39 % | 198 |
| Devise sur 3 mois | **Supprimer** | −0,028 | −0,069 (t = −2,4) | −2,35 % | −2,89 % | −12,8 % | 38 % | −0,039 / −0,081 | 28 % | 198 |
| Indicateur avancé (OCDE) | **Supprimer** | −0,162 | −0,163 (t = −4,6) | −5,49 % | −5,68 % | −3,6 % | 33 % | −0,194 / −0,038 | 11 % | 198 |
| Inflation | **Supprimer** | +0,038 | −0,061 (t = −1,4) | −0,57 % | −2,07 % | −3,3 % | 41 % | −0,012 / −0,001 | 50 % | 198 |
| Taux réel | **Supprimer** | −0,069 | −0,075 (t = −1,4) | −1,90 % | −2,41 % | −8,7 % | 39 % | −0,070 / −0,081 | 28 % | 198 |
| Devise sur 3 mois — variation 3 mois | **Supprimer** | +0,017 | −0,039 (t = −1,4) | −1,00 % | −2,39 % | −6,7 % | 41 % | −0,001 / −0,046 | 41 % | 195 |
| Valorisation relative — variation 3 mois | **Supprimer** | +0,015 | −0,010 (t = −0,3) | +0,11 % | −1,60 % | −3,7 % | 42 % | +0,000 / +0,010 | 47 % | 193 |
| Croissance du PIB — variation 6 mois | **Supprimer** | −0,040 | −0,081 (t = −1,4) | −1,41 % | −3,31 % | −1,0 % | 37 % | −0,107 / +0,116 | 47 % | 96 |
| Devise sur 3 mois — variation 6 mois | **Supprimer** | +0,032 | −0,053 (t = −1,7) | −0,89 % | −2,18 % | −10,7 % | 41 % | −0,009 / −0,015 | 59 % | 192 |
| Indicateur avancé (OCDE) — variation 6 mois | **Supprimer** | −0,004 | −0,074 (t = −1,8) | −0,82 % | −3,00 % | −2,9 % | 38 % | −0,045 / −0,010 | 47 % | 192 |
| Valorisation relative — variation 6 mois | **Supprimer** | +0,017 | −0,006 (t = −0,1) | −0,55 % | −1,87 % | +0,7 % | 40 % | −0,002 / +0,035 | 47 % | 190 |
| Croissance du PIB — variation 3 mois | **Données insuffisantes** | −0,022 | −0,034 (t = −1,0) | −0,50 % | −3,56 % | +2,9 % | 36 % | −0,087 / +0,237 | 53 % | 49 |
| Note globale actuelle | **Supprimer** | −0,080 | −0,060 (t = −1,3) | −1,84 % | −2,77 % | −0,3 % | 36 % | −0,081 / −0,027 | 28 % | 198 |
| Note globale sans règle de prudence | **Supprimer** | −0,081 | −0,058 (t = −1,3) | −1,80 % | −2,74 % | −0,9 % | 36 % | −0,082 / −0,024 | 33 % | 198 |
| Note recalibrée | **Supprimer** | −0,062 | −0,063 (t = −1,4) | −1,91 % | −2,98 % | −1,6 % | 36 % | −0,074 / −0,018 | 39 % | 198 |

Raisons des verdicts :
- Momentum 12 mois — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 1,4).
- Valorisation relative — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,006), peu significatif hors échantillon (t = 0,7).
- Indicateur avancé (OCDE) — variation 3 mois — Alléger : signal faible ou instable : IC hors échantillon faible (−0,059).
- Inflation — variation 3 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,023).
- Taux réel — variation 3 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,026), IC hors échantillon faible (+0,010), écart effacé par les frais (−3,0 %/an).
- Inflation — variation 6 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,051), IC hors échantillon faible (+0,029).
- Taux réel — variation 6 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,030), IC hors échantillon faible (+0,019).
- Croissance du PIB — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,061 sur tout l'historique, −0,039 hors échantillon.
- Devise sur 3 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,047 sur tout l'historique, −0,069 hors échantillon.
- Indicateur avancé (OCDE) — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,162 sur tout l'historique, −0,163 hors échantillon.
- Inflation — Supprimer : aucun pouvoir prédictif : IC −0,010 sur tout l'historique, −0,061 hors échantillon.
- Taux réel — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,072 sur tout l'historique, −0,075 hors échantillon.
- Devise sur 3 mois — variation 3 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,010 sur tout l'historique, −0,039 hors échantillon.
- Valorisation relative — variation 3 mois — Supprimer : aucun pouvoir prédictif : IC +0,002 sur tout l'historique, −0,010 hors échantillon.
- Croissance du PIB — variation 6 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,060 sur tout l'historique, −0,081 hors échantillon.
- Devise sur 3 mois — variation 6 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,010 sur tout l'historique, −0,053 hors échantillon.
- Indicateur avancé (OCDE) — variation 6 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,038 sur tout l'historique, −0,074 hors échantillon.
- Valorisation relative — variation 6 mois — Supprimer : aucun pouvoir prédictif : IC +0,005 sur tout l'historique, −0,006 hors échantillon.
- Croissance du PIB — variation 3 mois — Données insuffisantes : 49 mois mesurés dont 23 hors échantillon, 30 actifs en moyenne : pas de conclusion (minimum 48 mois, 24 hors échantillon, 8 actifs).
- Note globale actuelle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,070 sur tout l'historique, −0,060 hors échantillon.
- Note globale sans règle de prudence — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,070 sur tout l'historique, −0,058 hors échantillon.
- Note recalibrée — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,062 sur tout l'historique, −0,063 hors échantillon.

### Cible et comparaison au « momentum seul »

Référence « momentum seul » (meilleurs 20 % sur 12 mois hors dernier mois, rééquilibrage mensuel, frais compris) hors échantillon : +11,4 %/an, soit +0,0 pt/an face à l'indice (+11,4 %/an) ; ses actifs retenus battent l'indice 45 % du temps à 3 mois, 43 % à 6 mois (gain / perte 0,80).

| Signal | Battent l'indice à 3 m | à 6 m | Gain / perte à 3 m | à 6 m | Panier − indice (/an, hors éch.) | Panier − momentum seul (/an, hors éch.) |
|---|---|---|---|---|---|---|
| **Note globale actuelle** | 40 % | 36 % | 0,94 | 0,85 | −5,8 pt | −5,9 pt |
| **Note recalibrée** | 41 % | 36 % | 0,88 | 0,82 | −6,8 pt | −6,8 pt |
| Momentum 12 mois | 46 % | 43 % | 0,98 | 0,95 | +0,5 pt | +0,5 pt |
| Valorisation relative | 44 % | 40 % | 1,06 | 1,06 | +0,3 pt | +0,3 pt |
| Indicateur avancé (OCDE) — variation 3 mois | 45 % | 42 % | 1,00 | 0,87 | −0,6 pt | −0,7 pt |
| Croissance du PIB — variation 3 mois | 40 % | 36 % | 0,79 | 0,75 | −2,3 pt | −2,3 pt |
| Valorisation relative — variation 6 mois | 45 % | 40 % | 1,01 | 0,98 | −2,5 pt | −2,5 pt |
| Inflation — variation 3 mois | 44 % | 39 % | 1,00 | 0,99 | −2,6 pt | −2,7 pt |
| Taux réel — variation 6 mois | 44 % | 41 % | 0,97 | 0,88 | −2,9 pt | −3,0 pt |
| Inflation — variation 6 mois | 44 % | 40 % | 0,93 | 0,85 | −3,4 pt | −3,4 pt |
| Inflation | 46 % | 41 % | 0,87 | 0,89 | −4,4 pt | −4,5 pt |
| Croissance du PIB — variation 6 mois | 39 % | 37 % | 0,82 | 0,79 | −5,2 pt | −5,2 pt |
| Note globale sans règle de prudence | 40 % | 36 % | 0,93 | 0,86 | −5,9 pt | −5,9 pt |
| Taux réel — variation 3 mois | 42 % | 40 % | 1,02 | 0,92 | −5,9 pt | −6,0 pt |
| Devise sur 3 mois — variation 3 mois | 44 % | 41 % | 0,84 | 0,82 | −6,4 pt | −6,5 pt |
| Devise sur 3 mois — variation 6 mois | 44 % | 41 % | 0,87 | 0,86 | −7,0 pt | −7,0 pt |
| Valorisation relative — variation 3 mois | 44 % | 42 % | 1,01 | 0,98 | −7,1 pt | −7,1 pt |
| Taux réel | 42 % | 39 % | 0,98 | 0,92 | −7,2 pt | −7,2 pt |
| Croissance du PIB | 40 % | 36 % | 0,88 | 0,85 | −7,7 pt | −7,8 pt |
| Indicateur avancé (OCDE) — variation 6 mois | 42 % | 38 % | 0,91 | 0,82 | −8,9 pt | −9,0 pt |
| Devise sur 3 mois | 43 % | 38 % | 0,79 | 0,78 | −9,0 pt | −9,1 pt |
| Indicateur avancé (OCDE) | 34 % | 33 % | 0,79 | 0,54 | −11,0 pt | −11,0 pt |

Gain / perte : gain moyen des actifs retenus qui battent l'indice ÷ perte moyenne de ceux qui font moins bien (au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).

### Combinaisons de signaux

Règle : actif retenu s'il est dans les meilleurs 30 % sur chaque signal combiné. Candidats (2) : Indicateur avancé (OCDE) — variation 3 mois, Momentum 12 mois. 1 paires et triplets essayés, classés sur l'apprentissage seulement ; seuil de Bonferroni pour 1 essais : t ≥ 1,64 (0 combinaison(s) le franchissent sur l'apprentissage). Les 0 meilleures sont jugées hors échantillon, avec une correction de Holm (seuil 0,05).

Aucune combinaison testable (pas assez de candidats ou d'actifs retenus).

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | −0,019 | −1,4 | +0,51 % | +0,70 % | +0,90 % | 43 % | 54 % |
| 3 mois | −0,043 | −2,1 | +1,54 % | +2,19 % | +2,74 % | 40 % | 54 % |
| 6 mois | −0,070 | −2,5 | +2,79 % | +4,63 % | +5,56 % | 36 % | 55 % |
| 12 mois | −0,082 | −2,0 | +5,84 % | +9,75 % | +11,43 % | 31 % | 60 % |

## Chef d'orchestre (rejoué sur les pays)

Familles reconstituées : fondamentaux, valorisation, tendance, cycle ; les familles sans historique (flux, risque, géopolitique, dynamique des résultats) sont retirées et les poids renormalisés. Régime de marché (VIX) → palier Calme ou Tension pour les multiplicateurs de poids.

Horizon de référence : 6 mois · indice : ACWI · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 30 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (6 m) | Meilleurs − indice (6 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Famille Tendance | **Alléger** | +0,002 | +0,063 (t = 1,4) | +0,43 % | −1,64 % | +1,2 % | 43 % | +0,033 / +0,025 | 53 % | 197 |
| Famille Valorisation | **Alléger** | −0,006 | +0,039 (t = 0,7) | +0,50 % | −1,46 % | +4,6 % | 40 % | +0,019 / +0,003 | 53 % | 196 |
| Famille Cycle | **Supprimer** | −0,058 | −0,056 (t = −1,1) | −1,08 % | −2,69 % | −5,7 % | 35 % | −0,043 / −0,109 | 35 % | 194 |
| Famille Fondamentaux | **Supprimer** | −0,127 | −0,137 (t = −3,4) | −4,34 % | −4,17 % | −8,0 % | 34 % | −0,146 / −0,079 | 22 % | 198 |
| Score du chef d'orchestre | **Supprimer** | −0,083 | −0,031 (t = −0,7) | −2,04 % | −2,99 % | +0,1 % | 36 % | −0,059 / −0,056 | 35 % | 197 |
| Familles équipondérées | **Supprimer** | −0,085 | −0,012 (t = −0,2) | −1,09 % | −2,41 % | +1,4 % | 38 % | −0,047 / −0,060 | 33 % | 198 |
| Score recalibré | **Supprimer** | −0,086 | −0,026 (t = −0,6) | −1,98 % | −2,79 % | −0,6 % | 38 % | −0,055 / −0,069 | 33 % | 198 |

Raisons des verdicts :
- Famille Tendance — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 1,4).
- Famille Valorisation — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,006), peu significatif hors échantillon (t = 0,7).
- Famille Cycle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,057 sur tout l'historique, −0,056 hors échantillon.
- Famille Fondamentaux — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,132 sur tout l'historique, −0,137 hors échantillon.
- Score du chef d'orchestre — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,058 sur tout l'historique, −0,031 hors échantillon.
- Familles équipondérées — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,050 sur tout l'historique, −0,012 hors échantillon.
- Score recalibré — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,058 sur tout l'historique, −0,026 hors échantillon.

### Cible et comparaison au « momentum seul »

Référence « momentum seul » (meilleurs 20 % sur 12 mois hors dernier mois, rééquilibrage mensuel, frais compris) hors échantillon : +11,4 %/an, soit +0,0 pt/an face à l'indice (+11,4 %/an) ; ses actifs retenus battent l'indice 45 % du temps à 3 mois, 43 % à 6 mois (gain / perte 0,80).

| Signal | Battent l'indice à 3 m | à 6 m | Gain / perte à 3 m | à 6 m | Panier − indice (/an, hors éch.) | Panier − momentum seul (/an, hors éch.) |
|---|---|---|---|---|---|---|
| **Score du chef d'orchestre** | 42 % | 36 % | 0,89 | 0,87 | −4,2 pt | −4,2 pt |
| **Score recalibré** | 42 % | 38 % | 0,92 | 0,86 | −4,8 pt | −4,8 pt |
| Famille Tendance | 46 % | 43 % | 0,98 | 0,95 | +0,5 pt | +0,5 pt |
| Famille Valorisation | 44 % | 40 % | 1,06 | 1,06 | +0,3 pt | +0,3 pt |
| Familles équipondérées | 43 % | 38 % | 0,96 | 0,92 | −4,4 pt | −4,4 pt |
| Famille Cycle | 39 % | 35 % | 0,99 | 0,97 | −9,6 pt | −9,6 pt |
| Famille Fondamentaux | 39 % | 34 % | 0,83 | 0,78 | −10,0 pt | −10,0 pt |

Gain / perte : gain moyen des actifs retenus qui battent l'indice ÷ perte moyenne de ceux qui font moins bien (au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).

### Règles testées

- **Seuils des verdicts** (6 mois) : Renforcer fortement −2,81 pt (400 cas, réussite 36 %) ; Renforcer −2,31 pt (1804 cas, réussite 41 %) ; Neutre −1,63 pt (2743 cas, réussite 44 %) ; Alléger −0,23 pt (589 cas, réussite 54 %) ; Éviter +1,15 pt (177 cas, réussite 48 %). Verdicts **non ordonnés** : les seuils ne séparent pas nettement les pays.
- **Conviction** (verdicts positifs) : forte : réussite 39 %, −2,26 pt (569 cas) ; moyenne : réussite 41 %, −2,22 pt (1290 cas) ; faible : réussite 39 %, −3,31 pt (345 cas).
- **Groupes concordants** (seuil actuel : 3 pour « forte », 2 pour « moyenne ») : 1 groupe(s) 39 % (241) ; 2 groupe(s) 40 % (1224) ; 3 groupe(s) 41 % (637) ; 4 groupe(s) 31 % (102).
- **Suivi de tendance** : tendances fortes saines −1,75 pt (794 cas), tendances fortes en excès −2,58 pt (524 cas), autres pays −1,58 pt (4395 cas). Les tendances fortes saines **n'ont pas mieux fini** que les autres pays sur cet horizon.
- **Concentration du trader** (cœur pays, plafond 15 % par ligne, règle actuelle : 12 lignes au plus ; hors échantillon) : 4 lignes +4,9 %/an, Sharpe 0,25, perte max −22 % ; 6 lignes +5,3 %/an, Sharpe 0,19, perte max −33 % ; 8 lignes +5,7 %/an, Sharpe 0,20, perte max −35 % ; 12 lignes +5,9 %/an, Sharpe 0,22, perte max −34 % ; 15 lignes +6,0 %/an, Sharpe 0,23, perte max −34 % ; toutes lignes +6,0 %/an, Sharpe 0,23, perte max −34 % ; pays équipondérés +8,4 %/an ; indice +11,4 %/an.

## Entreprises américaines

**Biais du survivant mesuré** : l'univers actuel, équipondéré et rejoué dans le passé, fait +10,5 pt/an par rapport à l'indice ; en ne gardant à chaque date que les sociétés valant déjà au moins 2 Md$ à cette date (univers testé, 164 sociétés en moyenne), +0,5 pt/an. Plus cet écart est grand, plus les signaux de qualité et de solidité sont faussés (les sociétés faibles d'hier encore cotées aujourd'hui sont surtout celles qui ont réussi).

Horizon de référence : 12 mois · indice : SPY · séparation apprentissage / vérification : 2018-07-31 · période 2009-12 → 2026-11, 289 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (12 m) | Meilleurs − indice (12 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| M-score de Beneish | **Garder** | +0,097 | +0,037 (t = 2,4) | +7,03 % | +6,32 % | +4,3 % | 52 % | +0,054 / +0,128 | 88 % | 190 |
| Bénéfices normalisés | **Alléger** | +0,031 | +0,007 (t = 0,5) | +0,31 % | −0,04 % | −1,5 % | 47 % | +0,026 / −0,004 | 56 % | 190 |
| Conversion du bénéfice en cash | **Alléger** | +0,050 | +0,016 (t = 0,5) | −0,44 % | +1,47 % | +0,2 % | 47 % | +0,030 / +0,048 | 56 % | 190 |
| Couverture des intérêts | **Alléger** | −0,015 | +0,034 (t = 0,8) | −3,08 % | +0,72 % | −2,7 % | 46 % | −0,005 / +0,054 | 56 % | 190 |
| Croissance du bénéfice | **Alléger** | −0,053 | +0,020 (t = 0,8) | −1,82 % | +0,23 % | +4,2 % | 43 % | −0,010 / −0,053 | 31 % | 190 |
| Croissance du CA | **Alléger** | −0,034 | +0,001 (t = 0,0) | −0,33 % | −0,33 % | +0,9 % | 43 % | −0,013 / −0,039 | 38 % | 190 |
| Current ratio | **Alléger** | +0,006 | +0,001 (t = 0,0) | +1,89 % | +1,68 % | +0,8 % | 46 % | −0,017 / +0,080 | 56 % | 190 |
| VE/EBITDA relatif au secteur | **Alléger** | −0,012 | +0,018 (t = 0,5) | −0,39 % | −0,38 % | +5,1 % | 44 % | +0,007 / −0,017 | 50 % | 190 |
| Évolution du nombre d'actions | **Alléger** | +0,056 | +0,055 (t = 2,3) | +1,91 % | +2,55 % | −0,0 % | 48 % | +0,057 / +0,048 | 73 % | 178 |
| Rendement du FCF | **Alléger** | +0,028 | +0,038 (t = 0,9) | +0,29 % | +1,01 % | +1,7 % | 46 % | +0,018 / +0,088 | 56 % | 190 |
| F-score de Piotroski | **Alléger** | +0,003 | +0,023 (t = 1,2) | −0,97 % | +1,89 % | −1,0 % | 48 % | +0,010 / +0,021 | 56 % | 190 |
| Goodwill / actif | **Alléger** | +0,040 | +0,001 (t = 0,1) | +0,74 % | +0,89 % | −0,3 % | 47 % | +0,018 / +0,035 | 62 % | 190 |
| Intensité en R&D | **Alléger** | +0,016 | +0,056 (t = 0,9) | +9,67 % | +9,98 % | +9,3 % | 51 % | +0,046 / −0,007 | 62 % | 187 |
| PER relatif au secteur | **Alléger** | −0,008 | +0,021 (t = 0,5) | −0,05 % | −0,40 % | +2,6 % | 46 % | −0,005 / +0,045 | 62 % | 190 |
| Régularité | **Alléger** | +0,027 | +0,017 (t = 0,5) | +0,92 % | +0,97 % | −1,5 % | 47 % | +0,036 / −0,039 | 60 % | 178 |
| Rendement pour l'actionnaire | **Alléger** | +0,084 | +0,058 (t = 1,6) | +1,65 % | +2,84 % | −0,5 % | 51 % | +0,073 / +0,069 | 88 % | 190 |
| ROIC | **Alléger** | +0,005 | +0,025 (t = 0,6) | −0,99 % | +0,95 % | −0,4 % | 47 % | +0,014 / +0,015 | 56 % | 190 |
| ROIC − coût du capital | **Alléger** | +0,006 | +0,031 (t = 0,7) | −1,41 % | +1,96 % | −0,3 % | 48 % | +0,017 / +0,021 | 56 % | 190 |
| Croissance du CA — accélération | **Alléger** | −0,029 | +0,039 (t = 2,4) | +1,67 % | +0,73 % | +1,6 % | 43 % | +0,014 / −0,041 | 56 % | 190 |
| Intensité en R&D — variation annuelle | **Alléger** | +0,057 | −0,013 (t = −0,5) | +0,77 % | +4,49 % | −6,1 % | 46 % | +0,014 / +0,066 | 56 % | 190 |
| Marge brute — variation annuelle | **Alléger** | −0,036 | +0,030 (t = 2,1) | +1,18 % | +1,85 % | +0,7 % | 44 % | −0,019 / +0,044 | 50 % | 190 |
| Marge opérationnelle — variation annuelle | **Alléger** | −0,045 | +0,038 (t = 2,0) | −0,06 % | +2,57 % | +7,5 % | 45 % | −0,004 / −0,017 | 50 % | 190 |
| Z-score d'Altman | **Supprimer** | +0,000 | −0,010 (t = −0,2) | −0,05 % | +0,43 % | −7,3 % | 44 % | +0,002 / −0,031 | 44 % | 190 |
| Capex / amortissements | **Supprimer** | +0,017 | −0,017 (t = −0,8) | −0,86 % | −0,85 % | −3,8 % | 43 % | +0,005 / −0,012 | 50 % | 190 |
| Cycle de conversion du cash | **Supprimer** | +0,017 | −0,043 (t = −1,1) | −3,59 % | +0,04 % | −6,7 % | 46 % | −0,014 / +0,001 | 56 % | 190 |
| Dette nette / EBITDA | **Supprimer** | +0,010 | −0,026 (t = −0,8) | +0,48 % | +1,53 % | +1,3 % | 46 % | −0,003 / −0,021 | 44 % | 190 |
| Marge brute | **Supprimer** | +0,019 | −0,071 (t = −2,2) | −4,08 % | −1,16 % | −4,2 % | 43 % | −0,000 / −0,106 | 38 % | 190 |
| Marge opérationnelle | **Supprimer** | −0,034 | −0,025 (t = −1,0) | −7,42 % | −3,13 % | −3,0 % | 42 % | −0,014 / −0,092 | 50 % | 190 |
| Momentum 12 mois | **Supprimer** | −0,007 | −0,007 (t = −0,2) | +1,31 % | +2,14 % | −3,1 % | 46 % | +0,011 / −0,074 | 31 % | 190 |
| Note globale actuelle | **Alléger** | +0,006 | +0,022 (t = 0,7) | −1,93 % | +0,23 % | −2,9 % | 44 % | +0,015 / +0,008 | 56 % | 190 |
| Note globale sans règle de prudence | **Alléger** | +0,005 | +0,022 (t = 0,7) | −2,15 % | +0,01 % | −3,3 % | 44 % | +0,015 / +0,008 | 56 % | 190 |
| Note recalibrée | **Alléger** | +0,026 | +0,022 (t = 0,7) | −1,14 % | +0,41 % | −3,1 % | 45 % | +0,028 / +0,013 | 62 % | 190 |

Raisons des verdicts :
- M-score de Beneish — Garder : prédictif dans les deux moitiés (IC +0,097 puis +0,037 hors échantillon, t = 2,4), écart meilleurs − pires de +4,3 %/an après frais hors échantillon.
- Bénéfices normalisés — Alléger : signal faible ou instable : IC hors échantillon faible (+0,007), écart effacé par les frais (−1,5 %/an).
- Conversion du bénéfice en cash — Alléger : signal faible ou instable : IC hors échantillon faible (+0,016).
- Couverture des intérêts — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,015), peu significatif hors échantillon (t = 0,8), écart effacé par les frais (−2,7 %/an).
- Croissance du bénéfice — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,053), IC hors échantillon faible (+0,020).
- Croissance du CA — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,034), IC hors échantillon faible (+0,001).
- Current ratio — Alléger : signal faible ou instable : IC hors échantillon faible (+0,001).
- VE/EBITDA relatif au secteur — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,012), IC hors échantillon faible (+0,018).
- Évolution du nombre d'actions — Alléger : signal faible ou instable : écart effacé par les frais (−0,0 %/an).
- Rendement du FCF — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 0,9).
- F-score de Piotroski — Alléger : signal faible ou instable : IC hors échantillon faible (+0,023), écart effacé par les frais (−1,0 %/an).
- Goodwill / actif — Alléger : signal faible ou instable : IC hors échantillon faible (+0,001), écart effacé par les frais (−0,3 %/an).
- Intensité en R&D — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 0,9).
- PER relatif au secteur — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,008), IC hors échantillon faible (+0,021).
- Régularité — Alléger : signal faible ou instable : IC hors échantillon faible (+0,017), écart effacé par les frais (−1,5 %/an).
- Rendement pour l'actionnaire — Alléger : signal faible ou instable : écart effacé par les frais (−0,5 %/an).
- ROIC — Alléger : signal faible ou instable : IC hors échantillon faible (+0,025), écart effacé par les frais (−0,4 %/an).
- ROIC − coût du capital — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 0,7), écart effacé par les frais (−0,3 %/an).
- Croissance du CA — accélération — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,029).
- Intensité en R&D — variation annuelle — Alléger : signal faible ou instable : IC hors échantillon faible (−0,013), écart effacé par les frais (−6,1 %/an).
- Marge brute — variation annuelle — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,036).
- Marge opérationnelle — variation annuelle — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,045).
- Z-score d'Altman — Supprimer : aucun pouvoir prédictif : IC −0,005 sur tout l'historique, −0,010 hors échantillon.
- Capex / amortissements — Supprimer : aucun pouvoir prédictif : IC +0,001 sur tout l'historique, −0,017 hors échantillon.
- Cycle de conversion du cash — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,011 sur tout l'historique, −0,043 hors échantillon.
- Dette nette / EBITDA — Supprimer : aucun pouvoir prédictif : IC −0,007 sur tout l'historique, −0,026 hors échantillon.
- Marge brute — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,022 sur tout l'historique, −0,071 hors échantillon.
- Marge opérationnelle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,030 sur tout l'historique, −0,025 hors échantillon.
- Momentum 12 mois — Supprimer : aucun pouvoir prédictif : IC −0,007 sur tout l'historique, −0,007 hors échantillon.
- Note globale actuelle — Alléger : signal faible ou instable : IC hors échantillon faible (+0,022), écart effacé par les frais (−2,9 %/an).
- Note globale sans règle de prudence — Alléger : signal faible ou instable : IC hors échantillon faible (+0,022), écart effacé par les frais (−3,3 %/an).
- Note recalibrée — Alléger : signal faible ou instable : IC hors échantillon faible (+0,022), écart effacé par les frais (−3,1 %/an).

### Cible et comparaison au « momentum seul »

Référence « momentum seul » (meilleurs 20 % sur 12 mois hors dernier mois, rééquilibrage mensuel, frais compris) hors échantillon : +12,0 %/an, soit −1,9 pt/an face à l'indice (+14,0 %/an) ; ses actifs retenus battent l'indice 48 % du temps à 3 mois, 47 % à 6 mois (gain / perte 1,23).

| Signal | Battent l'indice à 3 m | à 6 m | Gain / perte à 3 m | à 6 m | Panier − indice (/an, hors éch.) | Panier − momentum seul (/an, hors éch.) |
|---|---|---|---|---|---|---|
| **Note globale actuelle** | 48 % | 47 % | 1,09 | 1,08 | −1,1 pt | +0,8 pt |
| **Note recalibrée** | 49 % | 47 % | 1,06 | 1,08 | −2,3 pt | −0,4 pt |
| Intensité en R&D | 51 % | 52 % | 1,32 | 1,37 | +8,1 pt | +10,0 pt |
| Marge opérationnelle — variation annuelle | 48 % | 46 % | 1,21 | 1,32 | +4,6 pt | +6,5 pt |
| Croissance du bénéfice | 48 % | 46 % | 1,15 | 1,20 | +2,2 pt | +4,2 pt |
| Current ratio | 48 % | 48 % | 1,11 | 1,17 | +1,1 pt | +3,1 pt |
| F-score de Piotroski | 49 % | 49 % | 1,08 | 1,13 | +0,8 pt | +2,7 pt |
| Évolution du nombre d'actions | 50 % | 50 % | 1,07 | 1,12 | +0,1 pt | +2,0 pt |
| Conversion du bénéfice en cash | 49 % | 48 % | 1,06 | 1,12 | +0,1 pt | +2,0 pt |
| Dette nette / EBITDA | 49 % | 47 % | 1,10 | 1,17 | −0,2 pt | +1,8 pt |
| Rendement pour l'actionnaire | 50 % | 50 % | 1,04 | 1,06 | −0,5 pt | +1,5 pt |
| VE/EBITDA relatif au secteur | 47 % | 46 % | 1,10 | 1,11 | −0,6 pt | +1,3 pt |
| Rendement du FCF | 48 % | 48 % | 1,08 | 1,09 | −0,7 pt | +1,3 pt |
| M-score de Beneish | 51 % | 52 % | 1,14 | 1,22 | −0,8 pt | +1,2 pt |
| ROIC − coût du capital | 49 % | 48 % | 1,04 | 1,08 | −0,9 pt | +1,1 pt |
| ROIC | 49 % | 48 % | 1,03 | 1,06 | −1,2 pt | +0,8 pt |
| Croissance du CA | 47 % | 45 % | 1,11 | 1,16 | −1,3 pt | +0,6 pt |
| Marge brute — variation annuelle | 48 % | 46 % | 1,14 | 1,25 | −1,4 pt | +0,5 pt |
| Couverture des intérêts | 48 % | 47 % | 1,04 | 1,08 | −1,7 pt | +0,2 pt |
| Note globale sans règle de prudence | 48 % | 47 % | 1,07 | 1,06 | −1,8 pt | +0,2 pt |
| Bénéfices normalisés | 48 % | 48 % | 1,01 | 0,99 | −2,0 pt | −0,1 pt |
| Régularité | 49 % | 48 % | 1,02 | 1,05 | −2,1 pt | −0,1 pt |
| Momentum 12 mois | 48 % | 47 % | 1,15 | 1,26 | −2,3 pt | −0,3 pt |
| PER relatif au secteur | 48 % | 47 % | 1,05 | 1,03 | −2,5 pt | −0,6 pt |
| Goodwill / actif | 49 % | 48 % | 1,03 | 1,08 | −2,6 pt | −0,6 pt |
| Croissance du CA — accélération | 46 % | 44 % | 1,13 | 1,22 | −2,7 pt | −0,8 pt |
| Cycle de conversion du cash | 48 % | 46 % | 1,02 | 1,07 | −3,1 pt | −1,2 pt |
| Marge opérationnelle | 46 % | 45 % | 1,02 | 0,99 | −3,2 pt | −1,3 pt |
| Intensité en R&D — variation annuelle | 47 % | 47 % | 1,07 | 1,12 | −3,7 pt | −1,8 pt |
| Marge brute | 46 % | 45 % | 1,05 | 1,05 | −5,1 pt | −3,2 pt |
| Capex / amortissements | 48 % | 46 % | 1,02 | 1,00 | −5,1 pt | −3,2 pt |
| Z-score d'Altman | 47 % | 45 % | 1,00 | 1,05 | −9,3 pt | −7,4 pt |

Gain / perte : gain moyen des actifs retenus qui battent l'indice ÷ perte moyenne de ceux qui font moins bien (au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).

### Combinaisons de signaux

Règle : actif retenu s'il est dans les meilleurs 30 % sur chaque signal combiné. Candidats (8) : M-score de Beneish, Rendement pour l'actionnaire, Intensité en R&D — variation annuelle, Évolution du nombre d'actions, Conversion du bénéfice en cash, Goodwill / actif, Bénéfices normalisés, Rendement du FCF. 84 paires et triplets essayés, classés sur l'apprentissage seulement ; seuil de Bonferroni pour 84 essais : t ≥ 3,24 (5 combinaison(s) le franchissent sur l'apprentissage). Les 5 meilleures sont jugées hors échantillon, avec une correction de Holm (seuil 0,05).

| Combinaison | Verdict | t apprentissage | Panier − indice (/an, hors éch.) | Panier − momentum seul | p corrigée | Battent l'indice 3 m / 6 m | Gain / perte 3 m / 6 m | Actifs retenus |
|---|---|---|---|---|---|---|---|---|
| M-score de Beneish + Goodwill / actif | **Prometteuse (non significative)** | 4,5 | +4,6 pt | +6,5 pt | 0,736 | 50 % / 47 % | 1,06 / 1,30 | 6,9 (100 % des mois) |
| Goodwill / actif + Rendement du FCF | **Prometteuse (non significative)** | 3,6 | +2,2 pt | +4,1 pt | 0,764 | 48 % / 47 % | 1,18 / 1,26 | 11,1 (100 % des mois) |
| Rendement pour l'actionnaire + Conversion du bénéfice en cash | **Non confirmée** | 3,5 | −0,4 pt | +1,5 pt | 0,936 | 48 % / 46 % | 1,05 / 1,08 | 15,7 (99 % des mois) |
| Conversion du bénéfice en cash + Goodwill / actif + Rendement du FCF | **Prometteuse (non significative)** | 3,4 | +9,3 pt | +11,2 pt | 0,083 | 51 % / 50 % | 1,27 / 1,29 | 5,5 (99 % des mois) |
| Intensité en R&D — variation annuelle + Rendement du FCF | **Non confirmée** | 3,3 | −4,7 pt | −2,7 pt | 0,936 | 46 % / 44 % | 0,99 / 0,97 | 6,5 (99 % des mois) |

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | +0,005 | 0,6 | +1,34 % | +1,43 % | +1,19 % | 49 % | 50 % |
| 3 mois | +0,006 | 0,5 | +3,89 % | +4,07 % | +3,52 % | 48 % | 52 % |
| 6 mois | +0,009 | 0,6 | +7,58 % | +8,32 % | +7,31 % | 47 % | 53 % |
| 12 mois | +0,013 | 0,7 | +15,22 % | +17,15 % | +14,98 % | 44 % | 56 % |

### Règles du trader (satellites)

- **Stops et prise de bénéfices** (10 meilleures sociétés chaque mois, gardées 12 mois ; 870 positions hors échantillon) : avec les règles +4,10 % en moyenne (pire −37 %, réussite 49 %), sans +13,86 % (pire −78 %, réussite 63 %). Les stops **coûtent** du rendement moyen ; ils réduisent la dispersion (écart-type 27 % contre 39 %) — arbitrage à juger.
- Sorties : stop 727, stop suiveur 584, échéance 285, prise de bénéfices puis échéance 305.

## Matières premières

Horizon de référence : 3 mois · indice : moyenne équipondérée de l'univers · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 17 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (3 m) | Meilleurs − indice (3 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Niveau historique | **Garder** | +0,119 | +0,143 (t = 3,0) | +5,43 % | +3,07 % | +26,7 % | 54 % | +0,096 / +0,291 | 77 % | 152 |
| Structure de la courbe (portage) | **Alléger** | +0,011 | +0,000 (t = 0,0) | −0,69 % | −1,73 % | −18,6 % | 44 % | +0,013 / −0,035 | 50 % | 177 |
| Positionnement CFTC | **Alléger** | +0,066 | −0,039 (t = −0,9) | +0,01 % | −0,53 % | −1,2 % | 46 % | −0,004 / +0,088 | 56 % | 201 |
| Positionnement CFTC — variation 6 mois | **Alléger** | −0,054 | +0,017 (t = 0,5) | −0,23 % | −0,75 % | −3,3 % | 46 % | −0,005 / −0,071 | 53 % | 195 |
| Tendance | **Supprimer** | −0,065 | −0,035 (t = −0,7) | −1,94 % | +0,12 % | −3,4 % | 45 % | −0,028 / −0,136 | 44 % | 201 |
| Positionnement CFTC — variation 3 mois | **Supprimer** | −0,096 | −0,023 (t = −0,6) | −1,74 % | −1,59 % | −13,2 % | 41 % | −0,054 / −0,083 | 41 % | 198 |
| Stocks EIA | **Données insuffisantes** | n. d. | n. d. (t = n. d.) | n. d. | n. d. | n. d. | n. d. | n. d. / n. d. | n. d. | 0 |
| Stocks EIA — variation 3 mois | **Données insuffisantes** | n. d. | n. d. (t = n. d.) | n. d. | n. d. | n. d. | n. d. | n. d. / n. d. | n. d. | 0 |
| Stocks EIA — variation 6 mois | **Données insuffisantes** | n. d. | n. d. (t = n. d.) | n. d. | n. d. | n. d. | n. d. | n. d. / n. d. | n. d. | 0 |
| Note globale actuelle | **Supprimer** | +0,018 | −0,001 (t = −0,0) | +0,16 % | +1,55 % | +10,7 % | 48 % | −0,005 / +0,060 | 44 % | 201 |
| Note recalibrée | **Alléger** | +0,025 | +0,038 (t = 0,8) | +1,48 % | +2,54 % | +12,6 % | 52 % | +0,003 / +0,141 | 50 % | 201 |

Raisons des verdicts :
- Niveau historique — Garder : prédictif dans les deux moitiés (IC +0,119 puis +0,143 hors échantillon, t = 3,0), écart meilleurs − pires de +26,7 %/an après frais hors échantillon.
- Structure de la courbe (portage) — Alléger : signal faible ou instable : IC hors échantillon faible (+0,000), écart effacé par les frais (−18,6 %/an).
- Positionnement CFTC — Alléger : signal faible ou instable : IC hors échantillon faible (−0,039), écart effacé par les frais (−1,2 %/an).
- Positionnement CFTC — variation 6 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,054), IC hors échantillon faible (+0,017), écart effacé par les frais (−3,3 %/an).
- Tendance — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,050 sur tout l'historique, −0,035 hors échantillon.
- Positionnement CFTC — variation 3 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,060 sur tout l'historique, −0,023 hors échantillon.
- Stocks EIA — Données insuffisantes : 0 mois mesurés dont 0 hors échantillon, 3 actifs en moyenne : pas de conclusion (minimum 48 mois, 24 hors échantillon, 8 actifs).
- Stocks EIA — variation 3 mois — Données insuffisantes : 0 mois mesurés dont 0 hors échantillon, 3 actifs en moyenne : pas de conclusion (minimum 48 mois, 24 hors échantillon, 8 actifs).
- Stocks EIA — variation 6 mois — Données insuffisantes : 0 mois mesurés dont 0 hors échantillon, 3 actifs en moyenne : pas de conclusion (minimum 48 mois, 24 hors échantillon, 8 actifs).
- Note globale actuelle — Supprimer : aucun pouvoir prédictif : IC +0,009 sur tout l'historique, −0,001 hors échantillon.
- Note recalibrée — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 0,8).

### Cible et comparaison au « momentum seul »

Référence « momentum seul » (meilleurs 20 % sur 12 mois hors dernier mois, rééquilibrage mensuel, frais compris) hors échantillon : +8,7 %/an, soit −4,8 pt/an face à l'indice (+13,4 %/an) ; ses actifs retenus battent l'indice 46 % du temps à 3 mois, 45 % à 6 mois (gain / perte 1,40).

| Signal | Battent l'indice à 3 m | à 6 m | Gain / perte à 3 m | à 6 m | Panier − indice (/an, hors éch.) | Panier − momentum seul (/an, hors éch.) |
|---|---|---|---|---|---|---|
| **Note globale actuelle** | 48 % | 47 % | 1,43 | 1,61 | +13,7 pt | +18,4 pt |
| **Note recalibrée** | 52 % | 49 % | 1,50 | 1,65 | +16,0 pt | +20,7 pt |
| Niveau historique | 54 % | 58 % | 1,69 | 1,44 | +15,1 pt | +19,9 pt |
| Tendance | 45 % | 46 % | 1,26 | 1,28 | +2,0 pt | +6,7 pt |
| Stocks EIA — variation 3 mois | n. d. | n. d. | n. d. | n. d. | −0,1 pt | +4,7 pt |
| Stocks EIA | n. d. | n. d. | n. d. | n. d. | −3,4 pt | +1,4 pt |
| Positionnement CFTC | 46 % | 45 % | 1,05 | 1,04 | −5,5 pt | −0,7 pt |
| Positionnement CFTC — variation 6 mois | 46 % | 47 % | 1,02 | 1,15 | −6,0 pt | −1,3 pt |
| Positionnement CFTC — variation 3 mois | 41 % | 46 % | 1,00 | 1,06 | −11,0 pt | −6,3 pt |
| Stocks EIA — variation 6 mois | n. d. | n. d. | n. d. | n. d. | −12,9 pt | −8,2 pt |
| Structure de la courbe (portage) | 44 % | 38 % | 0,89 | 1,01 | −25,3 pt | −20,5 pt |

Gain / perte : gain moyen des actifs retenus qui battent l'indice ÷ perte moyenne de ceux qui font moins bien (au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).

### Combinaisons de signaux

Règle : actif retenu s'il est dans les meilleurs 30 % sur chaque signal combiné. Candidats (3) : Niveau historique, Positionnement CFTC, Structure de la courbe (portage). 4 paires et triplets essayés, classés sur l'apprentissage seulement ; seuil de Bonferroni pour 4 essais : t ≥ 2,24 (0 combinaison(s) le franchissent sur l'apprentissage). Les 2 meilleures sont jugées hors échantillon, avec une correction de Holm (seuil 0,05).

| Combinaison | Verdict | t apprentissage | Panier − indice (/an, hors éch.) | Panier − momentum seul | p corrigée | Battent l'indice 3 m / 6 m | Gain / perte 3 m / 6 m | Actifs retenus |
|---|---|---|---|---|---|---|---|---|
| Niveau historique + Positionnement CFTC | **Prometteuse (non significative)** | 1,7 | +5,8 pt | +10,6 pt | 0,250 | 48 % / 54 % | 1,49 / 1,32 | 2,6 (76 % des mois) |
| Positionnement CFTC + Structure de la courbe (portage) | **Non confirmée** | 0,2 | −6,5 pt | −1,8 pt | 0,705 | 45 % / 38 % | 1,16 / 1,11 | 1,3 (70 % des mois) |

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | +0,009 | 0,4 | +1,46 % | +1,01 % | +0,67 % | 51 % | 48 % |
| 3 mois | +0,009 | 0,3 | +3,65 % | +3,49 % | +2,10 % | 48 % | 48 % |
| 6 mois | −0,020 | −0,5 | +7,18 % | +8,07 % | +4,22 % | 47 % | 47 % |
| 12 mois | −0,032 | −0,5 | +14,55 % | +14,59 % | +8,40 % | 44 % | 49 % |

## Secteurs (États-Unis)

Horizon de référence : 3 mois · indice : SPY · séparation apprentissage / vérification : 2018-08-31 · période 2009-12 → 2026-11, 11 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (3 m) | Meilleurs − indice (3 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Phase du cycle (rotation) | **Alléger** | −0,102 | +0,169 (t = 3,0) | +1,11 % | −0,28 % | +10,9 % | 42 % | +0,002 / +0,137 | 65 % | 197 |
| Momentum 12 mois | **Alléger** | −0,031 | +0,044 (t = 0,9) | −0,12 % | −0,43 % | +3,0 % | 46 % | +0,032 / −0,099 | 59 % | 189 |
| Note de rotation (tendance et cycle) | **Alléger** | −0,067 | +0,104 (t = 1,9) | +0,78 % | −0,38 % | +8,9 % | 44 % | +0,018 / +0,013 | 59 % | 197 |

Raisons des verdicts :
- Phase du cycle (rotation) — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,102).
- Momentum 12 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,031), peu significatif hors échantillon (t = 0,9).
- Note de rotation (tendance et cycle) — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,067).

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | +0,014 | 0,5 | +0,99 % | +0,69 % | +1,17 % | 45 % | 57 % |
| 3 mois | +0,017 | 0,4 | +3,25 % | +2,47 % | +3,62 % | 44 % | 61 % |
| 6 mois | +0,031 | 0,5 | +6,78 % | +5,97 % | +7,42 % | 42 % | 59 % |
| 12 mois | −0,045 | −0,7 | +12,43 % | +12,96 % | +14,94 % | 37 % | 56 % |

Phases reconstituées (mois) : Surchauffe 66, Reprise 51, Expansion sans inflation 44, Ralentissement inflationniste 39.

## Suivi de tendance (ETF pays, secteurs, matières)

Seuils du suivi de tendance du chef d'orchestre et de la poche « tendance » du trader (agents/backtest/tendance.py).

Période : 2010-01-31 → 2026-11-30 (203 mois), coupure apprentissage / vérification au 2018-06-30. Univers : pays 30, secteurs 11, matieres 10 ETF.

**Périodes de momentum** (IC moyen dans chaque catégorie ; écart mensuel premier − dernier tiers) :

| Définition | IC 1 mois (appr. / vérif.) | IC 3 mois (appr. / vérif.) | Écart des tiers à 1 mois, % (appr. / vérif.) |
|---|---|---|---|
| 12 mois hors dernier mois (retenue) | +0,011 / +0,012 | +0,005 / +0,035 | +0,51 / +0,13 |
| 12 mois | +0,004 / +0,017 | +0,001 / +0,017 | +0,44 / +0,28 |
| 6 mois hors dernier mois | −0,024 / +0,011 | −0,034 / +0,055 | +0,05 / +0,30 |
| 6 mois | −0,032 / +0,027 | −0,033 / +0,045 | +0,19 / +0,35 |
| 3 mois hors dernier mois | +0,005 / −0,050 | −0,020 / −0,011 | −0,04 / −0,34 |

**Filtre de tendance** (rendement à 3 mois relatif à la catégorie, premier tiers de force relative) : tendance positive +0,17 % (2498 cas), tendance négative −0,38 % (901 cas). Rendement absolu à 3 mois : +1,88 % en tendance positive, +1,90 % sinon.

**Excès** (tendances fortes ; écart de rendement relatif à 3 mois, actifs en excès − autres) :

| Critère | Seuil | Cas (appr. / vérif.) | Écart appr. % | Écart vérif. % |
|---|---|---|---|---|
| parabolique | 1.5 | 126 / 154 | +1,06 | +0,31 |
| parabolique | 2.0 | 55 / 70 | +0,76 | +2,09 |
| parabolique | 2.5 ✔ | 21 / 28 | −0,11 | −2,38 |
| parabolique | 3.0 | 8 / 15 | −4,09 | −4,55 |
| valorisation | 70 ✔ | 268 / 316 | −0,48 | −0,77 |
| valorisation | 80 | 206 / 259 | −0,41 | −0,89 |
| valorisation | 90 | 126 / 181 | −0,23 | −0,76 |
| positionnement | 80 | 79 / 89 | −0,33 | −1,75 |
| positionnement | 90 ✔ | 56 / 50 | −0,83 | −0,48 |
| positionnement | 95 | 40 / 30 | −0,13 | −2,69 |

**Poche « tendance »** (6 lignes au plus, frais 0,14 % par ordre) :

| Momentum | Variante | Rendement annuel % (appr. / vérif.) | Sharpe (appr. / vérif.) | Perte max % (appr. / vérif.) | Ordres par an |
|---|---|---|---|---|---|
| 12-1 | sans stop (sortie sur la force relative) | +1,6 / +8,6 | −0,03 / +0,40 | −32,6 / −23,9 | 24 |
| 12-1 | moyenne 200 jours | +2,4 / +6,1 | +0,03 / +0,25 | −29,0 / −24,0 | 28 |
| 12-1 | −8 % du plus haut | +3,3 / +4,5 | +0,11 / +0,19 | −20,9 / −23,7 | 43 |
| 12-1 | −12 % du plus haut | +2,8 / +5,0 | +0,06 / +0,20 | −25,6 / −23,4 | 33 |
| 12-1 | −15 % du plus haut | +3,0 / +8,2 | +0,07 / +0,41 | −24,1 / −18,5 | 28 |
| 12-1 | −20 % du plus haut | +1,1 / +9,0 | −0,06 / +0,47 | −34,5 / −19,6 | 26 |
| 12-1 | moyenne 200 jours ou −12 % | +2,7 / +6,0 | +0,05 / +0,26 | −23,6 / −19,6 | 33 |
| 12-1 | −12 %, sortie sous la médiane | +6,0 / +3,4 | +0,32 / +0,10 | −24,1 / −23,5 | 27 |
| 12-1 | −12 %, filtre des excès | +4,9 / +6,1 | +0,23 / +0,27 | −25,6 / −20,2 | 32 |
| 12-1 | −15 %, filtre des excès (retenue) | +5,0 / +8,3 | +0,24 / +0,41 | −24,2 / −19,9 | 28 |
| 12-1 | sans stop, filtre des excès | +3,9 / +9,6 | +0,14 / +0,47 | −31,5 / −23,6 | 24 |
| 6-1 | sans stop (sortie sur la force relative) | +1,7 / +5,9 | −0,02 / +0,23 | −49,8 / −27,0 | 32 |
| 6-1 | moyenne 200 jours | +2,3 / +5,9 | +0,02 / +0,23 | −42,7 / −23,6 | 35 |
| 6-1 | −8 % du plus haut | +1,9 / +3,3 | −0,01 / +0,09 | −32,0 / −29,1 | 53 |
| 6-1 | −12 % du plus haut | +1,9 / +2,9 | −0,01 / +0,06 | −42,8 / −29,6 | 42 |
| 6-1 | −15 % du plus haut | +2,8 / +4,2 | +0,06 / +0,14 | −43,7 / −25,1 | 36 |
| 6-1 | −20 % du plus haut | +1,6 / +7,2 | −0,03 / +0,32 | −49,6 / −24,4 | 34 |
| 6-1 | moyenne 200 jours ou −12 % | +2,4 / +5,5 | +0,03 / +0,23 | −42,6 / −24,0 | 41 |
| 6-1 | −12 %, sortie sous la médiane | +4,5 / +4,8 | +0,20 / +0,19 | −30,5 / −26,6 | 33 |
| 6-1 | −12 %, filtre des excès | +3,3 / +5,3 | +0,11 / +0,23 | −32,2 / −28,2 | 42 |
| 6-1 | −15 %, filtre des excès | +3,0 / +5,6 | +0,08 / +0,24 | −39,5 / −25,1 | 38 |
| 6-1 | sans stop, filtre des excès | +2,0 / +8,2 | −0,00 / +0,41 | −43,9 / −25,0 | 35 |
| — | Univers équipondéré | +4,2 / +9,6 | +0,16 / +0,51 | −25,4 / −27,4 | — |
| — | Indice mondial (ACWI) | +9,5 / +11,7 | +0,56 / +0,62 | −21,9 / −25,7 | — |

## Note actuelle contre note recalibrée

Poids réglés sur la première moitié de l'historique seulement, jugés sur la seconde. Une proposition n'est retenue que si la note recalibrée fait mieux hors échantillon (IC et écart après frais).

| Agent | Section | IC hors échantillon actuel → recalibré | Écart après frais actuel → recalibré | Retenue | Raison |
|---|---|---|---|---|---|
| pays | ponderations | −0,060 → −0,063 | −0,3 % → −1,6 % | non | pas d'amélioration hors échantillon (IC -0,060 → -0,063, écart après frais -0,3 → -1,6 %/an) : pondérations actuelles conservées |
| chef | poids → pays | −0,031 → −0,026 | +0,1 % → −0,6 % | non | pas d'amélioration hors échantillon (IC -0,031 → -0,026, écart après frais +0,1 → -0,6 %/an) : pondérations actuelles conservées |
| entreprises | ponderations | +0,022 → +0,022 | −2,9 % → −3,1 % | non | pas d'amélioration hors échantillon (IC +0,022 → +0,022, écart après frais -2,9 → -3,1 %/an) : pondérations actuelles conservées |
| matieres_premieres | familles → metaux_precieux → ponderations | −0,001 → +0,038 | +10,7 % → +12,6 % | non | hors échantillon, IC -0,001 → +0,038 et écart après frais +10,7 → +12,6 %/an ; non proposée : ces pondérations ont déjà été recalibrées par le backtest de 2026-11 (proposition appliquée), pas de nouveau réglage sur presque les mêmes données avant 6 mois |
| matieres_premieres | familles → metaux_industriels → ponderations | −0,001 → +0,038 | +10,7 % → +12,6 % | non | hors échantillon, IC -0,001 → +0,038 et écart après frais +10,7 → +12,6 %/an ; non proposée : ces pondérations ont déjà été recalibrées par le backtest de 2026-11 (proposition appliquée), pas de nouveau réglage sur presque les mêmes données avant 6 mois |
| matieres_premieres | familles → energie → ponderations | −0,001 → +0,038 | +10,7 % → +12,6 % | non | hors échantillon, IC -0,001 → +0,038 et écart après frais +10,7 → +12,6 %/an ; non proposée : ces pondérations ont déjà été recalibrées par le backtest de 2026-11 (proposition appliquée), pas de nouveau réglage sur presque les mêmes données avant 6 mois |
| matieres_premieres | familles → agricoles → ponderations | −0,001 → +0,038 | +10,7 % → +12,6 % | non | hors échantillon, IC -0,001 → +0,038 et écart après frais +10,7 → +12,6 %/an ; non proposée : ces pondérations ont déjà été recalibrées par le backtest de 2026-11 (proposition appliquée), pas de nouveau réglage sur presque les mêmes données avant 6 mois |


## Non testables (faute d'historique)

- **Géopolitique** (géopolitique / chef d'orchestre) : pas d'historique gratuit et daté des événements tels qu'ils étaient connus (le score est construit à partir de dépêches et d'une lecture par Gemini).
- **Flux des ETF pays et sectoriels** (pays / chef d'orchestre) : pas d'historique gratuit du nombre de parts en circulation : l'agent l'accumule depuis sa mise en service (quelques mois seulement).
- **Guidance et révisions des estimations** (entreprises (dynamique des résultats)) : historique des estimations des analystes payant ; guidance extraite des 8-K par Gemini, non reproductible à l'identique sur 15 ans.
- **Textes rédigés par Gemini** (tous) : textes, sans valeur numérique à tester.
- **Activité réelle (données alternatives)** (données alternatives) : séries (Google Trends, satellites, trafic) sans historique homogène gratuit sur 10 ans.
- **Achats d'initiés (formulaires 4)** (initiés) : testable en principe (EDGAR depuis 2003), mais des centaines de milliers de formulaires à lire : non retenu pour tenir dans le temps de calcul d'un job GitHub ; option à ajouter en lot séparé.
- **Risque pays, contradicteur** (risque) : objections et paliers construits à partir de sources sans historique (actualité, écarts de crédit souverains payants) ; seul le régime calme / tension est reconstitué (VIX).
- **Hystérésis des verdicts** (chef d'orchestre) : règle quotidienne (3 jours de confirmation) : sans objet en rééquilibrage mensuel.

## Biais et limites

- **Biais du survivant** : l'univers est la liste actuelle (pays suivis, sociétés de l'agent entreprises). Les sociétés disparues, rachetées ou sorties de l'indice manquent, ce qui embellit surtout les signaux de qualité et de solidité (Z-score, F-score) et la performance absolue des paniers.
- **Sur-ajustement** : les poids recalibrés sont réglés sur la seule première moitié et retenus seulement s'ils font mieux sur la seconde ; le retrait vers les poids actuels limite les écarts. Un IC de 0,02 à 0,05 est habituel pour un signal utile ; au-delà de 0,10, se méfier d'une erreur de données.
- **Petits échantillons** : moins de 48 mois mesurés ou de 24 mois hors échantillon → « Données insuffisantes », sans conclusion. Les rendements à 6 et 12 mois se chevauchent d'un mois sur l'autre : la statistique t est corrigée (Newey-West).
- **Données révisées** : FMI, OCDE (inflation, indicateur avancé) publient des séries révisées, sans les millésimes d'origine ; un retard de publication est appliqué, mais une révision ultérieure peut subsister. Les comptes SEC sont, eux, datés par leur dépôt.
- **Approximations** : valorisation des pays par le rendement du dividende de l'ETF (le PER historique n'est pas gratuit), structure de la courbe par le portage des ETF à contrats, paliers de risque par le VIX.

## Sources

- FRED (CSV public) : 8 lecture(s) réussie(s), 0 en échec
- Yahoo Finance (yfinance) : 1717 lecture(s) réussie(s), 0 en échec
- OCDE (indicateur avancé) : 7 lecture(s) réussie(s), 0 en échec
- OCDE (inflation) : 7 lecture(s) réussie(s), 0 en échec
- BRI (taux directeurs) : 5 lecture(s) réussie(s), 0 en échec
- FMI (croissance du PIB) : 5 lecture(s) réussie(s), 0 en échec
- SEC (XBRL companyfacts) : 1160 lecture(s) réussie(s), 0 en échec
- CFTC (Commitments of Traders) : 4 lecture(s) réussie(s), 0 en échec
- EIA (fichiers historiques) : 9 lecture(s) réussie(s), 0 en échec

## En bref

1. **Ce qui anticipe** (« Garder », jugé hors échantillon) : Niveau historique (matières), M-score de Beneish (entreprises).
2. **Combinaisons** : 89 essais, confirmées après correction des essais multiples : aucune.
3. **Ce qui n'anticipe pas** (« Supprimer ») : Croissance du PIB — variation 6 mois (pays), Taux réel (pays), Indicateur avancé (OCDE) — variation 6 mois (pays), Inflation (pays), Note globale sans règle de prudence (pays), Devise sur 3 mois — variation 6 mois (pays), et 12 autres.
4. **Ce qui marche à l'envers**, nettement (t ≤ −2) : Indicateur avancé (OCDE) (pays), Marge brute (entreprises), Devise sur 3 mois (pays).
5. **Momentum seul** (meilleurs 20 % sur 12 mois hors dernier mois), face à l'indice hors échantillon : pays +0,0 pt/an, entreprises −1,9 pt/an, matières −4,8 pt/an.
6. **Bat le momentum seul** (après frais, hors échantillon) : Note globale actuelle entreprises (+0,8 pt/an, non significatif), Note globale actuelle matières (+18,4 pt/an, non significatif), Note recalibrée matières (+20,7 pt/an, non significatif), combinaison M-score de Beneish + Goodwill / actif (entreprises, +6,5 pt/an, non significatif), combinaison Goodwill / actif + Rendement du FCF (entreprises, +4,1 pt/an, non significatif).
7. **Ne bat pas le momentum seul** : Note globale actuelle pays (−5,9 pt/an, non significatif), Note recalibrée pays (−6,8 pt/an, non significatif), Score du chef d'orchestre pays (−4,2 pt/an, non significatif), Score recalibré pays (−4,8 pt/an, non significatif), Note recalibrée entreprises (−0,4 pt/an, non significatif).
8. Bilan : sur 8 notes, 3 font mieux que le momentum seul hors échantillon : la règle sans analyse reste la référence à battre.
9. Prudence : univers actuel (biais du survivant), petits univers pour les pays et les matières, écarts souvent non significatifs.
10. Rien n'est modifié automatiquement : toute nouvelle pondération passe par une pull request à valider.
