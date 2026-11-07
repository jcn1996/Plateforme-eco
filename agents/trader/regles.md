# Agent trader (démo) — règles

**Portefeuille fictif à but de démonstration, aucun ordre réel.** L'agent ne se connecte à aucun courtier et ne passe aucun ordre : chaque « ordre » est une ligne de `data/trader/etat.json`, exécutée sur le papier. Son seul but est de mesurer, en conditions réelles de marché, ce que valent les recommandations de la plateforme.

Paramètres : [`config.json`](config.json). Code : `agent.py` (orchestration), `strategie.py` (cibles, ordres, risque), `portefeuille.py` (exécution simulée, valorisation), `performance.py` (statistiques, attribution), `sources.py` (cours).

## 1. Stratégie

- **Départ** : 100 000 € en liquidités (`capital_initial`), profil « équilibré » de l'allocation modèle du chef d'orchestre (`profil` : `prudent`, `equilibre` ou `dynamique`). Le remplacement du profil s'applique à la décision suivante, sans remise à zéro.
- **Cœur (≈ 70 %, `poches.coeur`)** : lignes « cœur » de l'allocation modèle du chef d'orchestre, au prorata de leurs poids, chacune par son support coté :
  - pays : l'ETF pays déjà suivi (symbole de la ligne : EWJ, EWY, INDA…) ; un pays sans ETF (Égypte) est redistribué dans sa classe ;
  - or : GLD ; pétrole Brent : BNO ; WTI : USO ; gaz américain : UNG ; autres matières : ETF dédiés (`supports`) ;
  - obligations américaines : SHY (courtes), IEF et TLT à parts égales (longues) ; zone euro : IBGS.AS (1-3 ans) et EXX6.DE (Bund allemand 10,5 ans et plus) ;
  - liquidités : restent en euros sur le compte, non rémunérées (hypothèse prudente).
  - Une ligne « Alléger » ou « Éviter », ou sans support coté, est redistribuée dans sa classe, sinon placée en liquidités ; une ligne de moins de 1 % est redistribuée de même.
  - Le cœur suit l'allocation du chef d'orchestre, qui intègre déjà les objections du contradicteur dans la conviction : la règle « objection sérieuse » ne s'applique qu'aux satellites.
- **Satellites (≈ 30 %, `poches.satellite`)** : convictions « forte » et « moyenne » du chef d'orchestre à verdict « Renforcer » ou « Renforcer fortement » :
  - entreprises ; pays, matières et or seulement en conviction forte et hors du cœur (opportunités tactiques) ;
  - exclus : objection sérieuse du contradicteur ; signaux favorables (famille notée 60/100 ou plus) d'un seul agent (**aucune décision fondée sur une seule source**) ; famille venant d'un agent dont la donnée est périmée, manquante ou dégradée selon le chef d'orchestre ; ligne vendue sur stop, verdict ou objection depuis moins de 20 jours ;
  - 10 lignes au plus, classées par conviction puis score ;
  - taille ∝ conviction (forte 2, moyenne 1) ÷ volatilité annualisée sur 3 mois (plancher 15 % ; à défaut, valeur par défaut de sa classe), **8 % maximum par ligne**, 1 % minimum ;
  - plafonds par pays (40 %), secteur (12 %) et thème (20 %) repris de l'allocation du chef d'orchestre, en comptant le cœur ;
  - un satellite détenu dont le verdict devient « Neutre » ou la conviction « faible » est conservé tel quel (sans renforcement) ; une ligne qui n'est plus analysée est vendue après 10 jours ;
  - le budget satellite non utilisé est reversé au cœur.
- **Valorisation en euros** : chaque cours est converti au cours de change du jour (paires `EURXXX=X` ; Londres, Johannesburg et Tel-Aviv cotent en sous-unités : pence, cents, agorot).

## 2. Gestion du risque

- **Liquidités minimales selon le palier de l'agent risque** (`liquidites_min_par_palier`) : 5 % en « Calme », 10 % en « Vigilance », 20 % en « Tension », 35 % en « Crise ». À la décision, les cibles sont réduites en proportion ; à chaque exécution, si les liquidités (ordres d'achat en attente déduits) passent sous le plancher de plus d'un point, toutes les lignes sont allégées en proportion (vente imposée).
- **Stops des satellites** : −15 % sous le prix de revient (en devise de cotation) ; **suiveur** dès que le plus haut atteint +20 % : stop à 15 % sous le plus haut, jamais abaissé. Un stop n'est déclenché qu'après **2 relevés** de cours distincts sous le stop (protection contre un cours aberrant, pas de décision sur une seule lecture).
- **Prise de bénéfices partielle** : vente d'un tiers de la ligne à +30 %, une seule fois.
- **Sorties** : dès que le chef d'orchestre passe une ligne détenue à « Alléger » ou « Éviter », ou qu'une objection sérieuse du contradicteur apparaît sur un satellite. Vérifié à chaque exécution, seulement si le chef d'orchestre est à jour et sain.
- **Rééquilibrage** : une ligne du cœur n'est rééquilibrée que si son écart à la cible dépasse **3 points**, ou si l'écart de sa classe dépasse 3 points (les lignes de la classe à plus de 0,75 point de leur cible sont alors rééquilibrées). Entrées et sorties de lignes ne sont pas soumises au seuil ; aucun ordre de moins de 500 €.
- **Rotation mensuelle maximale** : 30 % de la valeur du portefeuille en ventes discrétionnaires (rééquilibrage, sortie de l'allocation) sur 30 jours glissants ; au-delà, la vente est reportée et notée. Les sorties imposées (stop, prise de bénéfices, verdict, objection, plancher de liquidités) ne sont jamais bloquées.
- **Aucune décision sur données périmées ou dégradées** : la décision quotidienne exige une sortie du chef d'orchestre de moins de 26 h, l'analyse complète du jour (`data/historique/chef/AAAA-MM-JJ.json`), le profil d'allocation présent, un agent risque de moins de 30 h, et aucun des deux agents « dégradé » dans l'écran Santé. Sinon, l'agent attend, note les raisons (journal, `statut` de `data/portefeuille.json`, écran Santé « dégradé ») et réessaie à l'exécution horaire suivante. Les stops et la valorisation, qui ne dépendent que des cours, continuent.

## 3. Exécution simulée

- **Jamais à un cours passé** : un ordre est exécuté au premier cours disponible *après* l'heure de sa décision (ouverture de la première barre de 5 minutes de Yahoo Finance ; à défaut, ouverture de la première séance qui suit le jour de la décision). Les décisions de 7 h 33 UTC sont donc exécutées à l'ouverture des marchés concernés (Tokyo le lendemain, Europe vers 8 h, New York à 14 h 30 UTC). Ordres non exécutés au bout de 5 jours : expirés. Les ordres discrétionnaires non exécutés sont remplacés par la décision du lendemain.
- **Ventes avant achats** ; achats limités aux liquidités disponibles au-dessus du plancher.
- **Frais** : 0,1 % du montant de chaque ordre (`execution.frais_pct`).
- **Écart achat/vente estimé** (`execution.ecart_achat_vente_pct`) : 0,04 % pour les grands ETF, 0,10 % pour les autres ETF, 0,06 % pour les actions américaines, 0,12 % européennes, 0,20 % asiatiques développées, 0,35 % émergentes ; la moitié est payée à chaque achat et à chaque vente.
- **Quantités entières** : un achat inférieur au prix d'une part est annulé et noté.
- **Contango** : BNO, USO, UNG et les fonds de matières agricoles sont adossés à des contrats à terme ; chaque achat le signale dans « Ce qui pourrait me donner tort ».
- **Journal** (`data/trader/operations.json`) : date d'exécution et de décision, sens, support, quantité, cours de marché, prix payé (écart compris) en devise et en euros, taux de change, frais, coût de l'écart, motif, raison détaillée (verdict, conviction, score, agents à l'origine, familles favorables, objection éventuelle, cible et poids), stop associé, « Ce qui pourrait me donner tort », et pour une vente le résultat (plus-value en euros et en %, durée de détention).

## 4. Suivi de performance

- Valeur et historique quotidien (dernière valorisation du jour), performance depuis le départ, sur 1 mois et sur 3 mois (« n. d. » tant que l'historique ne couvre pas la période).
- **Référence** : MSCI World en euros = ETF URTH ÷ EUR/USD, base 100 000 € à la première valorisation (agent marchés s'il est à jour, sinon Yahoo Finance).
- Ratio de Sharpe (taux sans risque 2 %), volatilité annualisée et perte maximale, du portefeuille et de la référence (à partir de 20 jours d'historique).
- Taux de réussite des opérations clôturées (chaque vente, comparée au prix de revient frais compris), gain moyen et perte moyenne.
- **Attribution** : plus-values réalisées et latentes (frais compris) par poche (cœur, satellites), par classe d'actifs et par famille de signaux du chef d'orchestre (fondamentaux, valorisation, tendance, flux, cycle, risque, géopolitique, initiés, dynamique des résultats), au prorata de (note − 50) des familles favorables au moment de l'achat. La somme des poches est égale au gain total. Approximation destinée au futur agent calibrateur.

## 5. Rythme

- Décision chaque jour de semaine à 7 h 33 UTC (workflow `agent-trader.yml`, lancé par le planificateur), après l'analyse complète du chef d'orchestre (7 h 15).
- Toutes les heures (minute 5) de 8 h à 21 h UTC en semaine : exécution des ordres, valorisation en direct (barres de 5 minutes de Yahoo Finance, différées d'environ 15 minutes), stops, prise de bénéfices, sorties, plancher de liquidités ; décision du jour si elle n'a pas pu être prise à 7 h 33.

## 6. Règles de conduite

- Ton froid et factuel ; chaque décision et chaque ordre disent aussi « Ce qui pourrait me donner tort ».
- Aucune décision fondée sur une seule source : verdicts du chef d'orchestre (plusieurs agents), au moins 2 agents favorables pour un satellite, stop confirmé par 2 relevés.
- Aucune donnée inventée : un cours manquant garde le dernier cours connu (signalé) ; une source indisponible fait attendre l'agent.

## Commandes

```
python -m agents.trader                                  # exécution horaire (décision du jour si due)
python -m agents.trader --mode decision                  # décision forcée (données à jour exigées)
python -m agents.trader --test --data /tmp/essai         # cours simulés, sans réseau (copie de data/ à fournir)
python -m agents.trader.tests.simulation                 # simulation de 3 mois sur données de test
python -m unittest discover -s agents/trader -t .        # tests
```
