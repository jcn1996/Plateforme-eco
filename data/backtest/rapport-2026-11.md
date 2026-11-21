# Backtest des règles de notation — 2026-11

Rapport produit automatiquement par l'agent backtest (`agents/backtest/`, méthode : `agents/backtest/methode.md`). Rééquilibrage mensuel ; meilleurs 20 % contre pires 20 % et contre l'indice de référence ; coefficient d'information (IC, corrélation de rang entre le signal et la performance future) ; frais de transaction inclus dans l'écart annuel. Les verdicts se jugent hors échantillon (seconde moitié de l'historique).

**Rien n'est modifié automatiquement** : les nouvelles pondérations sont seulement proposées dans une pull request séparée.

## Synthèse

Alléger : 15 · Données insuffisantes : 3 · Garder : 1 · Supprimer : 18

## Pays

**Biais du survivant mesuré** : l'univers actuel, équipondéré et rejoué dans le passé, fait −3,6 pt/an par rapport à l'indice. Les pays suivis existent tous depuis le début : l'écart traduit surtout le poids des États-Unis dans l'indice, pas un biais du survivant ; les signaux se jugent entre pays.

Horizon de référence : 6 mois · indice : ACWI · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 30 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (6 m) | Meilleurs − indice (6 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Momentum 12 mois | **Alléger** | +0,002 | +0,062 (t = 1,4) | +0,40 % | −1,65 % | +0,4 % | 43 % | +0,033 / +0,025 | 53 % | 197 |
| Valorisation relative | **Alléger** | −0,006 | +0,038 (t = 0,7) | +0,49 % | −1,46 % | +4,6 % | 40 % | +0,019 / +0,003 | 53 % | 196 |
| Indicateur avancé (OCDE) — variation 3 mois | **Alléger** | +0,082 | −0,059 (t = −1,5) | +0,94 % | −2,01 % | +9,2 % | 42 % | +0,027 / −0,041 | 47 % | 195 |
| Inflation — variation 3 mois | **Alléger** | −0,023 | +0,057 (t = 2,2) | +0,53 % | −1,98 % | +2,3 % | 39 % | +0,005 / +0,058 | 47 % | 195 |
| Taux réel — variation 3 mois | **Alléger** | −0,026 | +0,011 (t = 0,3) | −0,18 % | −2,28 % | −3,0 % | 39 % | −0,008 / −0,009 | 35 % | 195 |
| Inflation — variation 6 mois | **Alléger** | −0,051 | +0,029 (t = 1,1) | +0,08 % | −2,57 % | +0,4 % | 40 % | −0,031 / +0,066 | 41 % | 192 |
| Taux réel — variation 6 mois | **Alléger** | −0,030 | +0,019 (t = 0,5) | −0,45 % | −2,33 % | +0,7 % | 41 % | −0,005 / −0,007 | 41 % | 192 |
| Devise sur 3 mois | **Supprimer** | −0,028 | −0,069 (t = −2,4) | −2,36 % | −2,89 % | −12,6 % | 38 % | −0,039 / −0,081 | 28 % | 198 |
| Indicateur avancé (OCDE) | **Supprimer** | −0,162 | −0,163 (t = −4,6) | −5,51 % | −5,68 % | −3,9 % | 33 % | −0,195 / −0,038 | 11 % | 198 |
| Inflation | **Supprimer** | +0,038 | −0,061 (t = −1,4) | −0,54 % | −2,04 % | −3,1 % | 41 % | −0,012 / −0,001 | 50 % | 198 |
| Taux réel | **Supprimer** | −0,069 | −0,074 (t = −1,3) | −1,89 % | −2,40 % | −8,4 % | 39 % | −0,069 / −0,081 | 28 % | 198 |
| Devise sur 3 mois — variation 3 mois | **Supprimer** | +0,017 | −0,040 (t = −1,4) | −1,01 % | −2,40 % | −6,7 % | 41 % | −0,002 / −0,046 | 41 % | 195 |
| Valorisation relative — variation 3 mois | **Supprimer** | +0,015 | −0,009 (t = −0,3) | +0,14 % | −1,58 % | −3,2 % | 42 % | +0,001 / +0,010 | 47 % | 193 |
| Devise sur 3 mois — variation 6 mois | **Supprimer** | +0,032 | −0,054 (t = −1,7) | −0,91 % | −2,18 % | −10,4 % | 41 % | −0,009 / −0,015 | 59 % | 192 |
| Indicateur avancé (OCDE) — variation 6 mois | **Supprimer** | −0,004 | −0,074 (t = −1,8) | −0,84 % | −3,00 % | −3,0 % | 38 % | −0,046 / −0,010 | 47 % | 192 |
| Valorisation relative — variation 6 mois | **Supprimer** | +0,017 | −0,008 (t = −0,2) | −0,56 % | −1,86 % | +1,1 % | 40 % | −0,003 / +0,035 | 47 % | 190 |
| Note globale actuelle | **Supprimer** | −0,041 | −0,037 (t = −0,7) | −1,09 % | −2,60 % | +0,8 % | 37 % | −0,034 / −0,059 | 39 % | 198 |
| Note globale sans règle de prudence | **Supprimer** | −0,052 | −0,029 (t = −0,5) | −0,99 % | −2,64 % | +1,9 % | 37 % | −0,040 / −0,047 | 33 % | 198 |
| Note recalibrée | **Supprimer** | −0,028 | −0,046 (t = −0,9) | −1,35 % | −2,98 % | −1,2 % | 36 % | −0,031 / −0,057 | 50 % | 198 |

Raisons des verdicts :
- Momentum 12 mois — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 1,4).
- Valorisation relative — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,006), peu significatif hors échantillon (t = 0,7).
- Indicateur avancé (OCDE) — variation 3 mois — Alléger : signal faible ou instable : IC hors échantillon faible (−0,059).
- Inflation — variation 3 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,023).
- Taux réel — variation 3 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,026), IC hors échantillon faible (+0,011), écart effacé par les frais (−3,0 %/an).
- Inflation — variation 6 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,051), IC hors échantillon faible (+0,029).
- Taux réel — variation 6 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,030), IC hors échantillon faible (+0,019).
- Devise sur 3 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,048 sur tout l'historique, −0,069 hors échantillon.
- Indicateur avancé (OCDE) — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,162 sur tout l'historique, −0,163 hors échantillon.
- Inflation — Supprimer : aucun pouvoir prédictif : IC −0,009 sur tout l'historique, −0,061 hors échantillon.
- Taux réel — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,071 sur tout l'historique, −0,074 hors échantillon.
- Devise sur 3 mois — variation 3 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,011 sur tout l'historique, −0,040 hors échantillon.
- Valorisation relative — variation 3 mois — Supprimer : aucun pouvoir prédictif : IC +0,003 sur tout l'historique, −0,009 hors échantillon.
- Devise sur 3 mois — variation 6 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,011 sur tout l'historique, −0,054 hors échantillon.
- Indicateur avancé (OCDE) — variation 6 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,039 sur tout l'historique, −0,074 hors échantillon.
- Valorisation relative — variation 6 mois — Supprimer : aucun pouvoir prédictif : IC +0,004 sur tout l'historique, −0,008 hors échantillon.
- Note globale actuelle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,039 sur tout l'historique, −0,037 hors échantillon.
- Note globale sans règle de prudence — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,041 sur tout l'historique, −0,029 hors échantillon.
- Note recalibrée — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,036 sur tout l'historique, −0,046 hors échantillon.

### Cible et comparaison au « momentum seul »

Référence « momentum seul » (meilleurs 20 % sur 12 mois hors dernier mois, rééquilibrage mensuel, frais compris) hors échantillon : +9,7 %/an, soit −0,6 pt/an face à l'indice (+10,2 %/an) ; ses actifs retenus battent l'indice 45 % du temps à 3 mois, 43 % à 6 mois (gain / perte 0,80).

| Signal | Battent l'indice à 3 m | à 6 m | Gain / perte à 3 m | à 6 m | Panier − indice (/an, hors éch.) | Panier − momentum seul (/an, hors éch.) |
|---|---|---|---|---|---|---|
| **Note globale actuelle** | 42 % | 37 % | 0,96 | 0,90 | −5,2 pt | −4,6 pt |
| **Note recalibrée** | 41 % | 36 % | 0,93 | 0,86 | −5,0 pt | −4,5 pt |
| Valorisation relative | 44 % | 40 % | 1,06 | 1,06 | +0,3 pt | +0,8 pt |
| Momentum 12 mois | 46 % | 43 % | 0,98 | 0,95 | +0,1 pt | +0,6 pt |
| Indicateur avancé (OCDE) — variation 3 mois | 45 % | 42 % | 1,00 | 0,87 | −0,5 pt | +0,1 pt |
| Valorisation relative — variation 6 mois | 45 % | 40 % | 1,01 | 0,99 | −2,2 pt | −1,7 pt |
| Inflation — variation 3 mois | 44 % | 39 % | 1,00 | 0,98 | −2,5 pt | −2,0 pt |
| Taux réel — variation 6 mois | 44 % | 41 % | 0,97 | 0,88 | −3,1 pt | −2,5 pt |
| Inflation — variation 6 mois | 44 % | 40 % | 0,92 | 0,85 | −3,3 pt | −2,8 pt |
| Inflation | 46 % | 41 % | 0,86 | 0,89 | −4,2 pt | −3,6 pt |
| Note globale sans règle de prudence | 41 % | 37 % | 0,94 | 0,89 | −4,6 pt | −4,1 pt |
| Taux réel — variation 3 mois | 42 % | 39 % | 1,02 | 0,93 | −5,8 pt | −5,3 pt |
| Devise sur 3 mois — variation 3 mois | 44 % | 41 % | 0,84 | 0,82 | −6,5 pt | −6,0 pt |
| Devise sur 3 mois — variation 6 mois | 44 % | 41 % | 0,88 | 0,86 | −6,7 pt | −6,1 pt |
| Taux réel | 42 % | 39 % | 0,99 | 0,92 | −6,8 pt | −6,2 pt |
| Valorisation relative — variation 3 mois | 44 % | 42 % | 1,00 | 0,99 | −6,8 pt | −6,3 pt |
| Indicateur avancé (OCDE) — variation 6 mois | 42 % | 38 % | 0,91 | 0,82 | −8,7 pt | −8,2 pt |
| Devise sur 3 mois | 43 % | 38 % | 0,79 | 0,77 | −8,8 pt | −8,2 pt |
| Indicateur avancé (OCDE) | 34 % | 33 % | 0,79 | 0,54 | −11,0 pt | −10,4 pt |

Gain / perte : gain moyen des actifs retenus qui battent l'indice ÷ perte moyenne de ceux qui font moins bien (au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).

### Combinaisons de signaux

Règle : actif retenu s'il est dans les meilleurs 30 % sur chaque signal combiné. Candidats (2) : Indicateur avancé (OCDE) — variation 3 mois, Momentum 12 mois. 1 paires et triplets essayés, classés sur l'apprentissage seulement ; seuil de Bonferroni pour 1 essais : t ≥ 1,64 (0 combinaison(s) le franchissent sur l'apprentissage). Les 0 meilleures sont jugées hors échantillon, avec une correction de Holm (seuil 0,05).

Aucune combinaison testable (pas assez de candidats ou d'actifs retenus).

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | −0,004 | −0,3 | +0,56 % | +0,55 % | +0,85 % | 46 % | 56 % |
| 3 mois | −0,016 | −0,7 | +1,62 % | +1,72 % | +2,69 % | 42 % | 56 % |
| 6 mois | −0,039 | −1,1 | +2,91 % | +4,01 % | +5,51 % | 37 % | 57 % |
| 12 mois | −0,055 | −1,2 | +5,92 % | +8,32 % | +11,38 % | 33 % | 63 % |

## Chef d'orchestre (rejoué sur les pays)

Familles reconstituées : fondamentaux, valorisation, tendance, cycle ; les familles sans historique (flux, risque, géopolitique, dynamique des résultats) sont retirées et les poids renormalisés. Régime de marché (VIX) → palier Calme ou Tension pour les multiplicateurs de poids.

Horizon de référence : 6 mois · indice : ACWI · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 30 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (6 m) | Meilleurs − indice (6 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Famille Tendance | **Alléger** | +0,002 | +0,062 (t = 1,4) | +0,40 % | −1,65 % | +0,4 % | 43 % | +0,033 / +0,025 | 53 % | 197 |
| Famille Valorisation | **Alléger** | −0,006 | +0,038 (t = 0,7) | +0,49 % | −1,46 % | +4,6 % | 40 % | +0,019 / +0,003 | 53 % | 196 |
| Famille Cycle | **Supprimer** | −0,058 | −0,057 (t = −1,2) | −1,10 % | −2,70 % | −5,8 % | 34 % | −0,044 / −0,109 | 35 % | 194 |
| Famille Fondamentaux | **Supprimer** | −0,063 | −0,116 (t = −2,8) | −2,90 % | −3,81 % | −4,1 % | 36 % | −0,098 / −0,054 | 28 % | 198 |
| Score du chef d'orchestre | **Supprimer** | −0,058 | −0,014 (t = −0,3) | −1,09 % | −2,49 % | +3,6 % | 38 % | −0,029 / −0,066 | 35 % | 197 |
| Familles équipondérées | **Supprimer** | −0,044 | −0,009 (t = −0,2) | −0,24 % | −1,97 % | +2,0 % | 40 % | −0,023 / −0,042 | 50 % | 198 |
| Score recalibré | **Supprimer** | −0,044 | −0,015 (t = −0,3) | −0,39 % | −1,88 % | +2,4 % | 40 % | −0,028 / −0,040 | 44 % | 198 |

Raisons des verdicts :
- Famille Tendance — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 1,4).
- Famille Valorisation — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,006), peu significatif hors échantillon (t = 0,7).
- Famille Cycle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,058 sur tout l'historique, −0,057 hors échantillon.
- Famille Fondamentaux — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,088 sur tout l'historique, −0,116 hors échantillon.
- Score du chef d'orchestre — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,036 sur tout l'historique, −0,014 hors échantillon.
- Familles équipondérées — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,027 sur tout l'historique, −0,009 hors échantillon.
- Score recalibré — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,030 sur tout l'historique, −0,015 hors échantillon.

### Cible et comparaison au « momentum seul »

Référence « momentum seul » (meilleurs 20 % sur 12 mois hors dernier mois, rééquilibrage mensuel, frais compris) hors échantillon : +9,7 %/an, soit −0,6 pt/an face à l'indice (+10,2 %/an) ; ses actifs retenus battent l'indice 45 % du temps à 3 mois, 43 % à 6 mois (gain / perte 0,80).

| Signal | Battent l'indice à 3 m | à 6 m | Gain / perte à 3 m | à 6 m | Panier − indice (/an, hors éch.) | Panier − momentum seul (/an, hors éch.) |
|---|---|---|---|---|---|---|
| **Score du chef d'orchestre** | 43 % | 38 % | 0,92 | 0,88 | −3,6 pt | −3,1 pt |
| **Score recalibré** | 44 % | 40 % | 0,95 | 0,94 | −4,2 pt | −3,7 pt |
| Famille Valorisation | 44 % | 40 % | 1,06 | 1,06 | +0,3 pt | +0,8 pt |
| Famille Tendance | 46 % | 43 % | 0,98 | 0,95 | +0,1 pt | +0,6 pt |
| Familles équipondérées | 44 % | 40 % | 0,95 | 0,92 | −4,3 pt | −3,8 pt |
| Famille Fondamentaux | 40 % | 36 % | 0,85 | 0,73 | −7,4 pt | −6,8 pt |
| Famille Cycle | 39 % | 34 % | 0,99 | 0,98 | −9,5 pt | −8,9 pt |

Gain / perte : gain moyen des actifs retenus qui battent l'indice ÷ perte moyenne de ceux qui font moins bien (au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).

### Règles testées

- **Seuils des verdicts** (6 mois) : Renforcer fortement −2,17 pt (386 cas, réussite 39 %) ; Renforcer −2,04 pt (1838 cas, réussite 41 %) ; Neutre −1,63 pt (2604 cas, réussite 44 %) ; Alléger −1,39 pt (673 cas, réussite 58 %) ; Éviter +0,73 pt (178 cas, réussite 48 %). Verdicts **non ordonnés** : les seuils ne séparent pas nettement les pays.
- **Conviction** (verdicts positifs) : forte : réussite 39 %, −2,23 pt (577 cas) ; moyenne : réussite 41 %, −2,38 pt (1021 cas) ; faible : réussite 42 %, −1,38 pt (626 cas).
- **Groupes concordants** (seuil actuel : 3 pour « forte », 2 pour « moyenne ») : 1 groupe(s) 41 % (354) ; 2 groupe(s) 41 % (1083) ; 3 groupe(s) 42 % (642) ; 4 groupe(s) 30 % (145).
- **Suivi de tendance** : tendances fortes saines −1,75 pt (790 cas), tendances fortes en excès −2,57 pt (524 cas), autres pays −1,58 pt (4365 cas). Les tendances fortes saines **n'ont pas mieux fini** que les autres pays sur cet horizon.
- **Concentration du trader, ancienne méthode** (cœur pays, plafond 15 % par ligne, règle d'alors : 12 lignes au plus ; hors échantillon) : 4 lignes +4,8 %/an, Sharpe 0,23, perte max −22 % ; 6 lignes +5,6 %/an, Sharpe 0,23, perte max −32 % ; 8 lignes +5,8 %/an, Sharpe 0,22, perte max −34 % ; 12 lignes +5,8 %/an, Sharpe 0,22, perte max −34 % ; 15 lignes +5,7 %/an, Sharpe 0,21, perte max −34 % ; toutes lignes +5,7 %/an, Sharpe 0,21, perte max −34 % ; pays équipondérés +7,3 %/an ; indice +10,2 %/an.

## Entreprises

Lot non calculé (source indisponible ou erreur : voir le journal du workflow).

## Matières premières

Horizon de référence : 3 mois · indice : moyenne équipondérée de l'univers · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 16 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (3 m) | Meilleurs − indice (3 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Niveau historique | **Garder** | +0,128 | +0,126 (t = 2,6) | +5,38 % | +2,99 % | +22,6 % | 53 % | +0,090 / +0,274 | 85 % | 152 |
| Structure de la courbe (portage) | **Alléger** | −0,017 | +0,009 (t = 0,2) | −1,37 % | −1,97 % | −18,5 % | 43 % | +0,013 / −0,077 | 62 % | 177 |
| Positionnement CFTC — variation 6 mois | **Alléger** | −0,055 | +0,019 (t = 0,5) | +0,04 % | −0,21 % | −0,9 % | 45 % | −0,009 / −0,054 | 53 % | 195 |
| Positionnement CFTC | **Supprimer** | +0,053 | −0,055 (t = −1,2) | +0,01 % | −0,39 % | −6,1 % | 46 % | −0,017 / +0,068 | 50 % | 201 |
| Tendance | **Supprimer** | −0,062 | −0,015 (t = −0,3) | −1,40 % | +0,40 % | +4,0 % | 45 % | −0,016 / −0,129 | 44 % | 201 |
| Positionnement CFTC — variation 3 mois | **Supprimer** | −0,099 | −0,018 (t = −0,5) | −1,67 % | −1,44 % | −10,9 % | 40 % | −0,055 / −0,074 | 35 % | 198 |
| Stocks EIA | **Données insuffisantes** | n. d. | n. d. (t = n. d.) | n. d. | n. d. | n. d. | n. d. | n. d. / n. d. | n. d. | 0 |
| Stocks EIA — variation 3 mois | **Données insuffisantes** | n. d. | n. d. (t = n. d.) | n. d. | n. d. | n. d. | n. d. | n. d. / n. d. | n. d. | 0 |
| Stocks EIA — variation 6 mois | **Données insuffisantes** | n. d. | n. d. (t = n. d.) | n. d. | n. d. | n. d. | n. d. | n. d. / n. d. | n. d. | 0 |
| Note globale actuelle | **Alléger** | +0,023 | −0,003 (t = −0,1) | +0,54 % | +1,63 % | +11,7 % | 47 % | −0,003 / +0,061 | 44 % | 201 |
| Note recalibrée | **Alléger** | +0,033 | +0,040 (t = 0,8) | +1,20 % | +2,32 % | +12,9 % | 51 % | +0,006 / +0,153 | 50 % | 201 |

Raisons des verdicts :
- Niveau historique — Garder : prédictif dans les deux moitiés (IC +0,128 puis +0,126 hors échantillon, t = 2,6), écart meilleurs − pires de +22,6 %/an après frais hors échantillon.
- Structure de la courbe (portage) — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,017), IC hors échantillon faible (+0,009), écart effacé par les frais (−18,5 %/an).
- Positionnement CFTC — variation 6 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,055), IC hors échantillon faible (+0,019), écart effacé par les frais (−0,9 %/an).
- Positionnement CFTC — Supprimer : aucun pouvoir prédictif : IC +0,001 sur tout l'historique, −0,055 hors échantillon.
- Tendance — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,039 sur tout l'historique, −0,015 hors échantillon.
- Positionnement CFTC — variation 3 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,059 sur tout l'historique, −0,018 hors échantillon.
- Stocks EIA — Données insuffisantes : 0 mois mesurés dont 0 hors échantillon, 2 actifs en moyenne : pas de conclusion (minimum 48 mois, 24 hors échantillon, 8 actifs).
- Stocks EIA — variation 3 mois — Données insuffisantes : 0 mois mesurés dont 0 hors échantillon, 2 actifs en moyenne : pas de conclusion (minimum 48 mois, 24 hors échantillon, 8 actifs).
- Stocks EIA — variation 6 mois — Données insuffisantes : 0 mois mesurés dont 0 hors échantillon, 2 actifs en moyenne : pas de conclusion (minimum 48 mois, 24 hors échantillon, 8 actifs).
- Note globale actuelle — Alléger : signal faible ou instable : IC hors échantillon faible (−0,003).
- Note recalibrée — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 0,8).

### Cible et comparaison au « momentum seul »

Référence « momentum seul » (meilleurs 20 % sur 12 mois hors dernier mois, rééquilibrage mensuel, frais compris) hors échantillon : +9,7 %/an, soit −3,1 pt/an face à l'indice (+12,8 %/an) ; ses actifs retenus battent l'indice 45 % du temps à 3 mois, 43 % à 6 mois (gain / perte 1,49).

| Signal | Battent l'indice à 3 m | à 6 m | Gain / perte à 3 m | à 6 m | Panier − indice (/an, hors éch.) | Panier − momentum seul (/an, hors éch.) |
|---|---|---|---|---|---|---|
| **Note globale actuelle** | 47 % | 46 % | 1,54 | 1,66 | +14,9 pt | +17,9 pt |
| **Note recalibrée** | 51 % | 50 % | 1,56 | 1,68 | +16,8 pt | +19,9 pt |
| Niveau historique | 53 % | 55 % | 1,65 | 1,40 | +13,5 pt | +16,6 pt |
| Tendance | 45 % | 45 % | 1,34 | 1,48 | +6,0 pt | +9,1 pt |
| Stocks EIA — variation 3 mois | n. d. | n. d. | n. d. | n. d. | +1,3 pt | +4,4 pt |
| Stocks EIA | n. d. | n. d. | n. d. | n. d. | −3,4 pt | −0,3 pt |
| Positionnement CFTC — variation 6 mois | 45 % | 46 % | 1,17 | 1,24 | −5,2 pt | −2,1 pt |
| Positionnement CFTC | 46 % | 43 % | 1,04 | 1,09 | −6,4 pt | −3,3 pt |
| Positionnement CFTC — variation 3 mois | 40 % | 45 % | 1,07 | 1,21 | −10,7 pt | −7,6 pt |
| Stocks EIA — variation 6 mois | n. d. | n. d. | n. d. | n. d. | −12,9 pt | −9,8 pt |
| Structure de la courbe (portage) | 43 % | 36 % | 0,88 | 1,27 | −21,1 pt | −18,0 pt |

Gain / perte : gain moyen des actifs retenus qui battent l'indice ÷ perte moyenne de ceux qui font moins bien (au-dessus de 1, les gagnants gagnent plus que les perdants ne perdent).

### Combinaisons de signaux

Règle : actif retenu s'il est dans les meilleurs 30 % sur chaque signal combiné. Candidats (1) : Niveau historique. 0 paires et triplets essayés, classés sur l'apprentissage seulement ; seuil de Bonferroni pour 0 essais : t ≥ n. d. (0 combinaison(s) le franchissent sur l'apprentissage). Les 0 meilleures sont jugées hors échantillon, avec une correction de Holm (seuil 0,05).

Aucune combinaison testable (pas assez de candidats ou d'actifs retenus).

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | +0,009 | 0,5 | +1,36 % | +0,87 % | +0,64 % | 50 % | 49 % |
| 3 mois | +0,010 | 0,3 | +3,68 % | +3,14 % | +2,06 % | 47 % | 50 % |
| 6 mois | −0,016 | −0,4 | +6,96 % | +7,47 % | +4,24 % | 46 % | 49 % |
| 12 mois | −0,028 | −0,5 | +14,30 % | +14,46 % | +8,45 % | 43 % | 51 % |

## Secteurs (États-Unis)

Horizon de référence : 3 mois · indice : SPY · séparation apprentissage / vérification : 2018-08-31 · période 2009-12 → 2026-11, 11 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (3 m) | Meilleurs − indice (3 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Phase du cycle (rotation) | **Alléger** | −0,102 | +0,168 (t = 3,0) | +1,11 % | −0,27 % | +10,1 % | 42 % | +0,002 / +0,137 | 65 % | 197 |
| Momentum 12 mois | **Alléger** | −0,031 | +0,044 (t = 0,9) | −0,13 % | −0,44 % | +3,2 % | 46 % | +0,031 / −0,099 | 59 % | 189 |
| Note de rotation (tendance et cycle) | **Alléger** | −0,067 | +0,103 (t = 1,9) | +0,77 % | −0,37 % | +8,5 % | 44 % | +0,017 / +0,013 | 59 % | 197 |

Raisons des verdicts :
- Phase du cycle (rotation) — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,102).
- Momentum 12 mois — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,031), peu significatif hors échantillon (t = 0,9).
- Note de rotation (tendance et cycle) — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,067).

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | +0,013 | 0,4 | +0,94 % | +0,66 % | +1,12 % | 45 % | 57 % |
| 3 mois | +0,016 | 0,3 | +3,21 % | +2,44 % | +3,58 % | 44 % | 61 % |
| 6 mois | +0,030 | 0,5 | +6,74 % | +5,95 % | +7,37 % | 42 % | 59 % |
| 12 mois | −0,047 | −0,7 | +12,37 % | +12,94 % | +14,89 % | 37 % | 55 % |

Phases reconstituées (mois) : Surchauffe 66, Reprise 51, Expansion sans inflation 44, Ralentissement inflationniste 39.

## Note actuelle contre note recalibrée

Poids réglés sur la première moitié de l'historique seulement, jugés sur la seconde. Une proposition n'est retenue que si la note recalibrée fait mieux hors échantillon (IC et écart après frais).

| Agent | Section | IC hors échantillon actuel → recalibré | Écart après frais actuel → recalibré | Retenue | Raison |
|---|---|---|---|---|---|
| pays | ponderations | −0,037 → −0,046 | +0,8 % → −1,2 % | non | pas d'amélioration hors échantillon (IC -0,037 → -0,046, écart après frais +0,8 → -1,2 %/an) : pondérations actuelles conservées |
| chef | poids → pays | −0,014 → −0,015 | +3,6 % → +2,4 % | non | pas d'amélioration hors échantillon (IC -0,014 → -0,015, écart après frais +3,6 → +2,4 %/an) : pondérations actuelles conservées |
| matieres_premieres | familles → metaux_precieux → ponderations | −0,003 → +0,040 | +11,7 % → +12,9 % | non | hors échantillon, IC -0,003 → +0,040 et écart après frais +11,7 → +12,9 %/an ; non proposée : ces pondérations ont déjà été recalibrées par le backtest de 2026-11 (proposition appliquée), pas de nouveau réglage sur presque les mêmes données avant 6 mois |
| matieres_premieres | familles → metaux_industriels → ponderations | −0,003 → +0,040 | +11,7 % → +12,9 % | non | hors échantillon, IC -0,003 → +0,040 et écart après frais +11,7 → +12,9 %/an ; non proposée : ces pondérations ont déjà été recalibrées par le backtest de 2026-11 (proposition appliquée), pas de nouveau réglage sur presque les mêmes données avant 6 mois |
| matieres_premieres | familles → energie → ponderations | −0,003 → +0,040 | +11,7 % → +12,9 % | non | hors échantillon, IC -0,003 → +0,040 et écart après frais +11,7 → +12,9 %/an ; non proposée : ces pondérations ont déjà été recalibrées par le backtest de 2026-11 (proposition appliquée), pas de nouveau réglage sur presque les mêmes données avant 6 mois |
| matieres_premieres | familles → agricoles → ponderations | −0,003 → +0,040 | +11,7 % → +12,9 % | non | hors échantillon, IC -0,003 → +0,040 et écart après frais +11,7 → +12,9 %/an ; non proposée : ces pondérations ont déjà été recalibrées par le backtest de 2026-11 (proposition appliquée), pas de nouveau réglage sur presque les mêmes données avant 6 mois |


## Entretien de la méthode (chef d'orchestre et trader)

Combinaisons en service (agents/chef/config.json → selections) rejugées hors échantillon avec les règles de ce rapport. Garde-fous : retrait seulement après deux mois « Non confirmée » de suite ; ajout seulement si la combinaison passe le seuil corrigé des essais sur l'apprentissage et bat l'indice et le momentum seul hors échantillon, une seule par trimestre ; aucun changement si le panier proposé (union des combinaisons) ne fait pas mieux hors échantillon.

### Matières premières

| Combinaison en service | Verdict | Écart à l'indice (hors échantillon) | Écart au momentum seul |
|---|---|---|---|
| Niveau historique + Positionnement CFTC | Prometteuse (non significative) | +1,4 pt/an | +4,5 pt/an |

Candidate à l'ajout : aucune (aucune combinaison retenue hors service).

**Recalibrage du mois : rien à modifier**

Non proposé :
- entreprises : combinaisons non évaluées ce mois-ci (lot non calculé)


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

- FRED (CSV public) : 5 lecture(s) réussie(s), 0 en échec
- Yahoo Finance (yfinance) : 118 lecture(s) réussie(s), 1 en échec (BZ=F : 'BZ=F')
- OCDE (indicateur avancé) : 2 lecture(s) réussie(s), 0 en échec
- OCDE (inflation) : 2 lecture(s) réussie(s), 0 en échec
- BRI (taux directeurs) : 1 lecture(s) réussie(s), 0 en échec
- FMI (croissance du PIB) : 0 lecture(s) réussie(s), 1 en échec (https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH : HTTP 404)
- CFTC (Commitments of Traders) : 1 lecture(s) réussie(s), 0 en échec
- EIA (fichiers historiques) : 3 lecture(s) réussie(s), 0 en échec

## En bref

1. **Ce qui anticipe** (« Garder », jugé hors échantillon) : Niveau historique (matières).
2. **Combinaisons** : 1 essais, confirmées après correction des essais multiples : aucune.
3. **Ce qui n'anticipe pas** (« Supprimer ») : Indicateur avancé (OCDE) — variation 6 mois (pays), Taux réel (pays), Inflation (pays), Positionnement CFTC (matières), Devise sur 3 mois — variation 6 mois (pays), Devise sur 3 mois — variation 3 mois (pays), et 5 autres.
4. **Ce qui marche à l'envers**, nettement (t ≤ −2) : Indicateur avancé (OCDE) (pays), Devise sur 3 mois (pays).
5. **Momentum seul** (meilleurs 20 % sur 12 mois hors dernier mois), face à l'indice hors échantillon : pays −0,6 pt/an, matières −3,1 pt/an.
6. **Bat le momentum seul** (après frais, hors échantillon) : Note globale actuelle matières (+17,9 pt/an, non significatif), Note recalibrée matières (+19,9 pt/an, non significatif).
7. **Ne bat pas le momentum seul** : Note globale actuelle pays (−4,6 pt/an, non significatif), Note recalibrée pays (−4,5 pt/an, non significatif), Score du chef d'orchestre pays (−3,1 pt/an, non significatif), Score recalibré pays (−3,7 pt/an, non significatif).
8. Bilan : sur 6 notes, 2 font mieux que le momentum seul hors échantillon : la règle sans analyse reste la référence à battre.
9. Prudence : univers actuel (biais du survivant), petits univers pour les pays et les matières, écarts souvent non significatifs.
10. **Recalibrage du mois : rien à modifier**.
