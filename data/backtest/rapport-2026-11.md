# Backtest des règles de notation — 2026-11

Rapport produit automatiquement par l'agent backtest (`agents/backtest/`, méthode : `agents/backtest/methode.md`). Rééquilibrage mensuel ; meilleurs 20 % contre pires 20 % et contre l'indice de référence ; coefficient d'information (IC, corrélation de rang entre le signal et la performance future) ; frais de transaction inclus dans l'écart annuel. Les verdicts se jugent hors échantillon (seconde moitié de l'historique).

**Rien n'est modifié automatiquement** : les nouvelles pondérations sont seulement proposées dans une pull request séparée.

## Synthèse

Alléger : 32 · Données insuffisantes : 1 · Garder : 2 · Supprimer : 16

## Pays

**Biais du survivant mesuré** : l'univers actuel, équipondéré et rejoué dans le passé, fait −3,6 pt/an par rapport à l'indice. Les pays suivis existent tous depuis le début : l'écart traduit surtout le poids des États-Unis dans l'indice, pas un biais du survivant ; les signaux se jugent entre pays.

Horizon de référence : 6 mois · indice : ACWI · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 30 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (6 m) | Meilleurs − indice (6 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Momentum 12 mois | **Alléger** | +0,002 | +0,063 (t = 1,4) | +0,43 % | −1,64 % | +1,2 % | 43 % | +0,033 / +0,025 | 53 % | 197 |
| Valorisation relative | **Alléger** | −0,006 | +0,039 (t = 0,7) | +0,50 % | −1,46 % | +4,6 % | 40 % | +0,019 / +0,003 | 53 % | 196 |
| Croissance du PIB | **Supprimer** | −0,082 | −0,039 (t = −1,0) | −2,54 % | −3,58 % | −5,9 % | 36 % | −0,096 / +0,070 | 39 % | 198 |
| Devise sur 3 mois | **Supprimer** | −0,028 | −0,069 (t = −2,4) | −2,35 % | −2,89 % | −12,8 % | 38 % | −0,039 / −0,081 | 28 % | 198 |
| Indicateur avancé (OCDE) | **Supprimer** | −0,162 | −0,163 (t = −4,6) | −5,49 % | −5,68 % | −3,6 % | 33 % | −0,194 / −0,038 | 11 % | 198 |
| Inflation | **Supprimer** | +0,038 | −0,061 (t = −1,4) | −0,57 % | −2,07 % | −3,3 % | 41 % | −0,012 / −0,001 | 50 % | 198 |
| Taux réel | **Supprimer** | −0,069 | −0,075 (t = −1,4) | −1,90 % | −2,41 % | −8,7 % | 39 % | −0,070 / −0,081 | 28 % | 198 |
| Note globale actuelle | **Supprimer** | −0,080 | −0,060 (t = −1,3) | −1,84 % | −2,77 % | −0,3 % | 36 % | −0,081 / −0,027 | 28 % | 198 |
| Note globale sans règle de prudence | **Supprimer** | −0,081 | −0,058 (t = −1,3) | −1,80 % | −2,74 % | −0,9 % | 36 % | −0,082 / −0,024 | 33 % | 198 |
| Note recalibrée | **Supprimer** | −0,062 | −0,063 (t = −1,4) | −1,91 % | −2,98 % | −1,6 % | 36 % | −0,074 / −0,018 | 39 % | 198 |

Raisons des verdicts :
- Momentum 12 mois — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 1,4).
- Valorisation relative — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,006), peu significatif hors échantillon (t = 0,7).
- Croissance du PIB — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,061 sur tout l'historique, −0,039 hors échantillon.
- Devise sur 3 mois — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,047 sur tout l'historique, −0,069 hors échantillon.
- Indicateur avancé (OCDE) — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,162 sur tout l'historique, −0,163 hors échantillon.
- Inflation — Supprimer : aucun pouvoir prédictif : IC −0,010 sur tout l'historique, −0,061 hors échantillon.
- Taux réel — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,072 sur tout l'historique, −0,075 hors échantillon.
- Note globale actuelle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,070 sur tout l'historique, −0,060 hors échantillon.
- Note globale sans règle de prudence — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,070 sur tout l'historique, −0,058 hors échantillon.
- Note recalibrée — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,062 sur tout l'historique, −0,063 hors échantillon.

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
| Score du chef d'orchestre | **Supprimer** | −0,086 | −0,030 (t = −0,7) | −2,17 % | −3,03 % | +0,1 % | 36 % | −0,060 / −0,056 | 35 % | 197 |
| Familles équipondérées | **Supprimer** | −0,085 | −0,012 (t = −0,2) | −1,09 % | −2,41 % | +1,4 % | 38 % | −0,047 / −0,060 | 33 % | 198 |
| Score recalibré | **Supprimer** | −0,086 | −0,026 (t = −0,6) | −1,98 % | −2,79 % | −0,6 % | 38 % | −0,055 / −0,069 | 33 % | 198 |

Raisons des verdicts :
- Famille Tendance — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 1,4).
- Famille Valorisation — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,006), peu significatif hors échantillon (t = 0,7).
- Famille Cycle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,057 sur tout l'historique, −0,056 hors échantillon.
- Famille Fondamentaux — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,132 sur tout l'historique, −0,137 hors échantillon.
- Score du chef d'orchestre — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,059 sur tout l'historique, −0,030 hors échantillon.
- Familles équipondérées — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,050 sur tout l'historique, −0,012 hors échantillon.
- Score recalibré — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,058 sur tout l'historique, −0,026 hors échantillon.

### Règles testées

- **Seuils des verdicts** (6 mois) : Renforcer fortement −2,86 pt (251 cas, réussite 34 %) ; Renforcer −2,41 pt (1866 cas, réussite 41 %) ; Neutre −1,59 pt (2827 cas, réussite 44 %) ; Alléger −0,27 pt (587 cas, réussite 54 %) ; Éviter +1,10 pt (182 cas, réussite 48 %). Verdicts **non ordonnés** : les seuils ne séparent pas nettement les pays.
- **Conviction** (verdicts positifs) : forte : réussite 38 %, −2,38 pt (420 cas) ; moyenne : réussite 40 %, −2,55 pt (1107 cas) ; faible : réussite 41 %, −2,36 pt (590 cas).
- **Groupes concordants** (seuil actuel : 3 pour « forte », 2 pour « moyenne ») : 1 groupe(s) 42 % (364) ; 2 groupe(s) 40 % (1175) ; 3 groupe(s) 40 % (502) ; 4 groupe(s) 33 % (76).
- **Règle anti-euphorie** : momentum extrême −0,95 pt (803 cas) contre −1,39 pt pour les autres tendances positives (1639 cas) ; valorisation tendue −1,24 pt (395), correcte −0,81 pt (391). Règle **non confirmée** : les hausses extrêmes n'ont pas moins bien fini que les autres (à alléger ou à revoir).
- **Concentration du trader** (cœur pays, plafond 15 % par ligne, règle actuelle : 12 lignes au plus ; hors échantillon) : 4 lignes +3,8 %/an, Sharpe 0,15, perte max −22 % ; 6 lignes +2,7 %/an, Sharpe 0,04, perte max −33 % ; 8 lignes +4,0 %/an, Sharpe 0,12, perte max −33 % ; 12 lignes +4,2 %/an, Sharpe 0,13, perte max −33 % ; 15 lignes +4,3 %/an, Sharpe 0,13, perte max −33 % ; toutes lignes +4,3 %/an, Sharpe 0,13, perte max −33 % ; pays équipondérés +8,4 %/an ; indice +11,4 %/an.

## Entreprises américaines

**Biais du survivant mesuré** : l'univers actuel, équipondéré et rejoué dans le passé, fait +6,3 pt/an par rapport à l'indice ; en ne gardant à chaque date que les sociétés valant déjà au moins 2 Md$ à cette date (univers testé, 159 sociétés en moyenne), +1,0 pt/an. Plus cet écart est grand, plus les signaux de qualité et de solidité sont faussés (les sociétés faibles d'hier encore cotées aujourd'hui sont surtout celles qui ont réussi).

Horizon de référence : 12 mois · indice : SPY · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 287 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (12 m) | Meilleurs − indice (12 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Intensité en R&D | **Garder** | +0,143 | +0,116 (t = 3,0) | +20,04 % | +13,96 % | +15,2 % | 52 % | +0,139 / +0,096 | 81 % | 190 |
| Z-score d'Altman | **Alléger** | +0,030 | +0,026 (t = 0,4) | +1,03 % | +3,04 % | +1,7 % | 48 % | +0,042 / −0,026 | 62 % | 190 |
| Bénéfices normalisés | **Alléger** | +0,007 | +0,038 (t = 1,7) | −1,15 % | −0,01 % | −2,3 % | 46 % | +0,036 / −0,032 | 50 % | 191 |
| Capex / amortissements | **Alléger** | −0,065 | +0,054 (t = 1,9) | +2,13 % | +2,76 % | +6,2 % | 45 % | −0,008 / −0,013 | 38 % | 190 |
| Conversion du bénéfice en cash | **Alléger** | +0,095 | +0,018 (t = 0,5) | +0,78 % | +1,66 % | −1,3 % | 48 % | +0,064 / +0,042 | 69 % | 191 |
| Couverture des intérêts | **Alléger** | −0,069 | +0,043 (t = 1,3) | −6,26 % | −0,05 % | −3,6 % | 45 % | −0,021 / +0,001 | 38 % | 190 |
| Croissance du bénéfice | **Alléger** | −0,024 | +0,014 (t = 0,5) | −2,69 % | +1,06 % | −0,3 % | 45 % | +0,002 / −0,037 | 50 % | 191 |
| Croissance du CA | **Alléger** | −0,041 | +0,012 (t = 0,3) | +0,60 % | +0,99 % | +4,6 % | 44 % | +0,001 / −0,082 | 50 % | 191 |
| Dette nette / EBITDA | **Alléger** | +0,055 | −0,014 (t = −0,6) | +3,73 % | +4,36 % | −1,8 % | 49 % | +0,038 / −0,034 | 50 % | 190 |
| VE/EBITDA relatif au secteur | **Alléger** | −0,086 | +0,005 (t = 0,1) | −2,07 % | +0,80 % | +1,3 % | 44 % | −0,041 / −0,052 | 50 % | 189 |
| Évolution du nombre d'actions | **Alléger** | +0,061 | +0,020 (t = 0,9) | +2,84 % | +0,80 % | −0,5 % | 45 % | +0,031 / +0,081 | 73 % | 178 |
| Rendement du FCF | **Alléger** | +0,017 | +0,017 (t = 0,3) | −2,76 % | −1,23 % | −2,3 % | 43 % | −0,009 / +0,113 | 62 % | 191 |
| F-score de Piotroski | **Alléger** | +0,021 | −0,002 (t = −0,1) | −1,10 % | +0,41 % | +1,0 % | 46 % | +0,021 / −0,029 | 56 % | 191 |
| Goodwill / actif | **Alléger** | −0,059 | +0,043 (t = 1,3) | +2,32 % | +1,78 % | +5,5 % | 44 % | −0,028 / +0,052 | 44 % | 190 |
| Marge brute | **Alléger** | +0,095 | −0,051 (t = −1,0) | +0,26 % | +3,46 % | −3,4 % | 48 % | +0,059 / −0,094 | 50 % | 190 |
| Momentum 12 mois | **Alléger** | +0,048 | +0,036 (t = 0,8) | +3,19 % | +3,38 % | −1,3 % | 46 % | +0,068 / −0,053 | 75 % | 191 |
| M-score de Beneish | **Alléger** | +0,053 | +0,005 (t = 0,3) | +3,56 % | +7,17 % | +5,7 % | 50 % | +0,040 / −0,003 | 62 % | 190 |
| PER relatif au secteur | **Alléger** | −0,071 | +0,002 (t = 0,1) | −2,87 % | −0,97 % | −1,7 % | 43 % | −0,052 / +0,019 | 38 % | 190 |
| Régularité | **Alléger** | +0,012 | +0,065 (t = 1,6) | +0,31 % | +1,03 % | −0,0 % | 48 % | +0,047 / +0,002 | 60 % | 178 |
| Rendement pour l'actionnaire | **Alléger** | −0,012 | +0,052 (t = 1,2) | +0,69 % | +0,96 % | +1,5 % | 47 % | +0,007 / +0,057 | 56 % | 191 |
| ROIC | **Alléger** | −0,004 | +0,043 (t = 1,8) | −1,69 % | +1,80 % | −0,3 % | 47 % | +0,026 / −0,011 | 62 % | 190 |
| ROIC − coût du capital | **Alléger** | −0,003 | +0,047 (t = 2,0) | −0,85 % | +1,93 % | +1,2 % | 47 % | +0,026 / +0,002 | 62 % | 190 |
| Current ratio | **Supprimer** | −0,030 | −0,045 (t = −1,2) | −0,03 % | +1,09 % | −2,8 % | 44 % | −0,053 / +0,025 | 50 % | 190 |
| Cycle de conversion du cash | **Supprimer** | +0,028 | −0,060 (t = −2,6) | −1,89 % | +2,89 % | −5,8 % | 47 % | −0,004 / −0,048 | 31 % | 190 |
| Marge opérationnelle | **Supprimer** | −0,032 | −0,009 (t = −0,2) | −6,27 % | −0,44 % | −3,2 % | 44 % | +0,004 / −0,116 | 44 % | 190 |
| Note globale actuelle | **Alléger** | −0,001 | +0,023 (t = 0,8) | −0,95 % | +0,21 % | −1,5 % | 45 % | +0,023 / −0,038 | 50 % | 191 |
| Note globale sans règle de prudence | **Alléger** | −0,001 | +0,023 (t = 0,8) | −1,09 % | +0,11 % | −1,5 % | 45 % | +0,023 / −0,038 | 50 % | 191 |
| Note recalibrée | **Alléger** | +0,032 | +0,020 (t = 0,6) | −0,63 % | +0,25 % | −0,1 % | 45 % | +0,046 / −0,045 | 56 % | 191 |

Raisons des verdicts :
- Intensité en R&D — Garder : prédictif dans les deux moitiés (IC +0,143 puis +0,116 hors échantillon, t = 3,0), écart meilleurs − pires de +15,2 %/an après frais hors échantillon.
- Z-score d'Altman — Alléger : signal faible ou instable : IC hors échantillon faible (+0,026).
- Bénéfices normalisés — Alléger : signal faible ou instable : écart effacé par les frais (−2,3 %/an).
- Capex / amortissements — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,065).
- Conversion du bénéfice en cash — Alléger : signal faible ou instable : IC hors échantillon faible (+0,018), écart effacé par les frais (−1,3 %/an).
- Couverture des intérêts — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,069), peu significatif hors échantillon (t = 1,3), écart effacé par les frais (−3,6 %/an).
- Croissance du bénéfice — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,024), IC hors échantillon faible (+0,014), écart effacé par les frais (−0,3 %/an).
- Croissance du CA — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,041), IC hors échantillon faible (+0,012).
- Dette nette / EBITDA — Alléger : signal faible ou instable : IC hors échantillon faible (−0,014), écart effacé par les frais (−1,8 %/an).
- VE/EBITDA relatif au secteur — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,086), IC hors échantillon faible (+0,005).
- Évolution du nombre d'actions — Alléger : signal faible ou instable : IC hors échantillon faible (+0,020), écart effacé par les frais (−0,5 %/an).
- Rendement du FCF — Alléger : signal faible ou instable : IC hors échantillon faible (+0,017), écart effacé par les frais (−2,3 %/an).
- F-score de Piotroski — Alléger : signal faible ou instable : IC hors échantillon faible (−0,002).
- Goodwill / actif — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,059), peu significatif hors échantillon (t = 1,3).
- Marge brute — Alléger : signal faible ou instable : IC hors échantillon faible (−0,051), écart effacé par les frais (−3,4 %/an).
- Momentum 12 mois — Alléger : signal faible ou instable : peu significatif hors échantillon (t = 0,8), écart effacé par les frais (−1,3 %/an).
- M-score de Beneish — Alléger : signal faible ou instable : IC hors échantillon faible (+0,005).
- PER relatif au secteur — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,071), IC hors échantillon faible (+0,002), écart effacé par les frais (−1,7 %/an).
- Régularité — Alléger : signal faible ou instable : écart effacé par les frais (−0,0 %/an).
- Rendement pour l'actionnaire — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,012), peu significatif hors échantillon (t = 1,2).
- ROIC — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,004), écart effacé par les frais (−0,3 %/an).
- ROIC − coût du capital — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,003).
- Current ratio — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,037 sur tout l'historique, −0,045 hors échantillon.
- Cycle de conversion du cash — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,013 sur tout l'historique, −0,060 hors échantillon.
- Marge opérationnelle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,021 sur tout l'historique, −0,009 hors échantillon.
- Note globale actuelle — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,001), IC hors échantillon faible (+0,023), écart effacé par les frais (−1,5 %/an).
- Note globale sans règle de prudence — Alléger : signal faible ou instable : IC négatif ou nul en apprentissage (−0,001), IC hors échantillon faible (+0,023), écart effacé par les frais (−1,5 %/an).
- Note recalibrée — Alléger : signal faible ou instable : IC hors échantillon faible (+0,020), écart effacé par les frais (−0,1 %/an).

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | −0,001 | −0,1 | +1,22 % | +1,44 % | +1,20 % | 49 % | 51 % |
| 3 mois | +0,002 | 0,1 | +3,60 % | +3,87 % | +3,56 % | 49 % | 53 % |
| 6 mois | +0,009 | 0,5 | +7,42 % | +7,73 % | +7,29 % | 47 % | 55 % |
| 12 mois | +0,010 | 0,6 | +15,23 % | +16,18 % | +15,02 % | 45 % | 57 % |

### Règles du trader (satellites)

- **Stops et prise de bénéfices** (10 meilleures sociétés chaque mois, gardées 12 mois ; 880 positions hors échantillon) : avec les règles +3,54 % en moyenne (pire −36 %, réussite 50 %), sans +14,72 % (pire −60 %, réussite 65 %). Les stops **coûtent** du rendement moyen ; ils réduisent la dispersion (écart-type 27 % contre 39 %) — arbitrage à juger.
- Sorties : échéance 368, stop 699, stop suiveur 577, prise de bénéfices puis échéance 259.

## Matières premières

Horizon de référence : 3 mois · indice : moyenne équipondérée de l'univers · séparation apprentissage / vérification : 2018-06-30 · période 2009-12 → 2026-11, 17 actifs.

| Signal | Verdict | IC apprentissage | IC hors échantillon | Meilleurs − pires (3 m) | Meilleurs − indice (3 m) | Écart après frais, hors échantillon (/an) | Réussite des meilleurs | IC calme / tension | Années positives | Mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Niveau historique | **Garder** | +0,119 | +0,143 (t = 3,0) | +5,43 % | +3,07 % | +26,7 % | 54 % | +0,096 / +0,291 | 77 % | 152 |
| Structure de la courbe (portage) | **Alléger** | +0,011 | +0,000 (t = 0,0) | −0,69 % | −1,73 % | −18,6 % | 44 % | +0,013 / −0,035 | 50 % | 177 |
| Positionnement CFTC | **Alléger** | +0,066 | −0,039 (t = −0,9) | +0,01 % | −0,53 % | −1,2 % | 46 % | −0,004 / +0,088 | 56 % | 201 |
| Tendance | **Supprimer** | −0,065 | −0,035 (t = −0,7) | −1,94 % | +0,12 % | −3,4 % | 45 % | −0,028 / −0,136 | 44 % | 201 |
| Stocks EIA | **Données insuffisantes** | n. d. | n. d. (t = n. d.) | n. d. | n. d. | n. d. | n. d. | n. d. / n. d. | n. d. | 0 |
| Note globale actuelle | **Supprimer** | +0,001 | −0,024 (t = −0,6) | +0,22 % | +0,82 % | +8,9 % | 47 % | −0,017 / +0,008 | 44 % | 201 |
| Note recalibrée | **Supprimer** | +0,018 | −0,001 (t = −0,0) | +0,16 % | +1,55 % | +10,7 % | 48 % | −0,005 / +0,060 | 44 % | 201 |

Raisons des verdicts :
- Niveau historique — Garder : prédictif dans les deux moitiés (IC +0,119 puis +0,143 hors échantillon, t = 3,0), écart meilleurs − pires de +26,7 %/an après frais hors échantillon.
- Structure de la courbe (portage) — Alléger : signal faible ou instable : IC hors échantillon faible (+0,000), écart effacé par les frais (−18,6 %/an).
- Positionnement CFTC — Alléger : signal faible ou instable : IC hors échantillon faible (−0,039), écart effacé par les frais (−1,2 %/an).
- Tendance — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,050 sur tout l'historique, −0,035 hors échantillon.
- Stocks EIA — Données insuffisantes : 0 mois mesurés dont 0 hors échantillon, 3 actifs en moyenne : pas de conclusion (minimum 48 mois, 24 hors échantillon, 8 actifs).
- Note globale actuelle — Supprimer : aucun pouvoir prédictif (de sens contraire) : IC −0,012 sur tout l'historique, −0,024 hors échantillon.
- Note recalibrée — Supprimer : aucun pouvoir prédictif : IC +0,009 sur tout l'historique, −0,001 hors échantillon.

Note globale actuelle, par horizon :

| Horizon | IC moyen | t | Meilleurs | Pires | Indice | Réussite meilleurs | Réussite pires |
|---|---|---|---|---|---|---|---|
| 1 mois | −0,001 | −0,0 | +1,17 % | +0,77 % | +0,67 % | 51 % | 51 % |
| 3 mois | −0,012 | −0,4 | +2,93 % | +2,71 % | +2,10 % | 47 % | 51 % |
| 6 mois | −0,044 | −1,2 | +5,81 % | +5,99 % | +4,22 % | 46 % | 51 % |
| 12 mois | −0,086 | −1,6 | +11,45 % | +12,64 % | +8,40 % | 40 % | 50 % |

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

## Note actuelle contre note recalibrée

Poids réglés sur la première moitié de l'historique seulement, jugés sur la seconde. Une proposition n'est retenue que si la note recalibrée fait mieux hors échantillon (IC et écart après frais).

| Agent | Section | IC hors échantillon actuel → recalibré | Écart après frais actuel → recalibré | Retenue | Raison |
|---|---|---|---|---|---|
| pays | ponderations | −0,060 → −0,063 | −0,3 % → −1,6 % | non | pas d'amélioration hors échantillon (IC -0,060 → -0,063, écart après frais -0,3 → -1,6 %/an) : pondérations actuelles conservées |
| chef | poids → pays | −0,030 → −0,026 | +0,1 % → −0,6 % | non | pas d'amélioration hors échantillon (IC -0,030 → -0,026, écart après frais +0,1 → -0,6 %/an) : pondérations actuelles conservées |
| entreprises | ponderations | +0,023 → +0,020 | −1,5 % → −0,1 % | non | pas d'amélioration hors échantillon (IC +0,023 → +0,020, écart après frais -1,5 → -0,1 %/an) : pondérations actuelles conservées |
| matieres_premieres | familles → metaux_precieux → ponderations | −0,024 → −0,001 | +8,9 % → +10,7 % | oui | hors échantillon, IC -0,024 → -0,001 et écart après frais +8,9 → +10,7 %/an |
| matieres_premieres | familles → metaux_industriels → ponderations | −0,024 → −0,001 | +8,9 % → +10,7 % | oui | hors échantillon, IC -0,024 → -0,001 et écart après frais +8,9 → +10,7 %/an |
| matieres_premieres | familles → energie → ponderations | −0,024 → −0,001 | +8,9 % → +10,7 % | oui | hors échantillon, IC -0,024 → -0,001 et écart après frais +8,9 → +10,7 %/an |
| matieres_premieres | familles → agricoles → ponderations | −0,024 → −0,001 | +8,9 % → +10,7 % | oui | hors échantillon, IC -0,024 → -0,001 et écart après frais +8,9 → +10,7 %/an |

- `agents/matieres_premieres/config.json` (familles → metaux_precieux → ponderations) : tendance 15 → 8, courbe 5 → 3, positionnement 15 → 18, niveau 10 → 16
- `agents/matieres_premieres/config.json` (familles → metaux_industriels → ponderations) : tendance 20 → 12, courbe 15 → 11, positionnement 15 → 20, niveau 10 → 17
- `agents/matieres_premieres/config.json` (familles → energie → ponderations) : tendance 15 → 10, courbe 20 → 15, positionnement 10 → 15, niveau 5 → 10
- `agents/matieres_premieres/config.json` (familles → agricoles → ponderations) : tendance 15 → 8, courbe 15 → 10, positionnement 15 → 20, niveau 10 → 17

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

- FRED (CSV public) : 6 lecture(s) réussie(s), 0 en échec
- Yahoo Finance (yfinance) : 1250 lecture(s) réussie(s), 0 en échec
- OCDE (indicateur avancé) : 5 lecture(s) réussie(s), 0 en échec
- OCDE (inflation) : 5 lecture(s) réussie(s), 0 en échec
- BRI (taux directeurs) : 4 lecture(s) réussie(s), 0 en échec
- FMI (croissance du PIB) : 4 lecture(s) réussie(s), 0 en échec
- SEC (XBRL companyfacts) : 864 lecture(s) réussie(s), 0 en échec
- CFTC (Commitments of Traders) : 2 lecture(s) réussie(s), 0 en échec
- EIA (fichiers historiques) : 6 lecture(s) réussie(s), 0 en échec
