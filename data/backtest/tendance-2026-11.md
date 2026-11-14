# Backtest du suivi de tendance — 2026-11

Lot « tendance » de l'agent backtest (`python -m agents.backtest --lot tendance`, code : `agents/backtest/tendance.py`), calculé le 14/11/2026 sur les cours Yahoo Finance (ajustés des dividendes) et le CFTC. Ces résultats fixent les seuils du suivi de tendance du chef d'orchestre (`agents/chef/config.json`, bloc `suivi_tendance`) et de la poche « tendance » du trader (`agents/trader/config.json`, bloc `tendance`).

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

**Règle du chef d'orchestre rejouée sur les pays** (lot « pays », 2010-2026, rendement relatif à l'ACWI ; tendance reconstituée sur les cours mensuels de l'ETF, moyenne 10 mois à la place de la moyenne 200 jours) :

| Horizon | Tendances fortes saines | Tendances fortes en excès | Autres pays |
|---|---|---|---|
| 1 mois | −0,18 pt (829 cas) | −0,35 pt (530) | −0,26 pt (4 504) |
| 3 mois | −0,82 pt (817) | −1,18 pt (529) | −0,77 pt (4 457) |
| 6 mois | −1,75 pt (794) | −2,58 pt (524) | −1,58 pt (4 395) |
| 12 mois | −3,64 pt (761) | −6,17 pt (498) | −3,30 pt (4 274) |

Lecture : les excès sont bien pénalisants (les tendances fortes en excès font nettement moins bien, surtout à 6 et 12 mois) ; en revanche, sur les seuls pays, une tendance forte saine ne fait pas mieux que les autres pays au-delà d'un mois. Le momentum est un signal faible (IC de 0,01 à 0,03) : il est traité comme un signal parmi d'autres, jamais seul suffisant à une conviction forte, et la poche « tendance » du trader reste une petite part des satellites.
