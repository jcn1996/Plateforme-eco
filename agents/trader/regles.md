# Agent trader (démo) — règles

**Portefeuille fictif à but de démonstration, aucun ordre réel.** L'agent ne se connecte à aucun courtier et ne passe aucun ordre : chaque « ordre » est une ligne de `data/trader/etat.json`, exécutée sur le papier. Son seul but est de mesurer, en conditions réelles de marché, ce que valent les recommandations de la plateforme.

Paramètres : [`config.json`](config.json). Code : `agent.py` (orchestration), `strategie.py` (cibles, ordres, risque), `portefeuille.py` (exécution simulée, valorisation), `performance.py` (statistiques, attribution), `sources.py` (cours).

## 1. Stratégie : diversifiée mais concentrée

- **Départ** : 100 000 € en liquidités (`capital_initial`). Le portefeuille ne copie plus l'allocation modèle du chef d'orchestre : il en reprend les verdicts et les convictions pour choisir peu de lignes.
- **Concentration** : **15 lignes au plus** (`max_lignes`, liquidités exceptées), **4 % minimum par ligne** (`ligne_min`) ; une ligne qui tomberait sous 4 % après les plafonds est écartée (les lignes déjà détenues en dernier).
- **Cœur : 8 à 12 positions** (`coeur`) choisies parmi les opportunités « Renforcer » ou « Renforcer fortement » de conviction **moyenne ou forte** : ETF pays, ETF sectoriels régionaux (États-Unis, Europe), or (GLD), matières premières (BNO, USO… avec le contango signalé).
  - **Jamais d'ETF monde** (secteurs « Monde », URTH, ACWI…) **ni d'ETF pays « Neutre »**.
  - Classement par conviction puis score (+3 points pour une ligne déjà détenue et toujours éligible : moins de rotation, moins de frais).
  - **Diversification** : au moins 4 classes ou zones (Asie, Europe, Amérique du Nord, Amérique latine, Moyen-Orient et Afrique, Océanie, Émergents, or, matières premières, obligations), 3 lignes de cœur au plus par zone et 35 % au plus du portefeuille par zone pour le cœur, 2 lignes au plus par secteur (ETF sectoriels et sociétés confondus).
  - **Faible corrélation, vérifiée sur 1 an** de cours quotidiens : une ligne dont la corrélation avec une ligne déjà retenue dépasse 0,80 (sur au moins 120 séances communes) est écartée. La décision publie la corrélation moyenne et la plus forte paire.
  - Poids ∝ conviction (forte 1,5, moyenne 1), 15 % au plus par ligne ; l'excédent des plafonds reste en liquidités.
- **Obligations : poids fixé par le verdict** du chef d'orchestre (`obligations.poids_par_verdict`) : « Renforcer fortement » 15 %, « Renforcer » 10 %, « Neutre » 5 % (poids neutre), « Alléger » et « Éviter » 0 ; une conviction faible plafonne au poids neutre ; 20 % au total au plus ; un seul support par ligne (SHY, IEF, IBGS.AS, EXX6.DE). Elles comptent parmi les lignes du cœur.
- **Satellites : convictions fortes seulement** (entreprises), signaux favorables (famille notée 60/100 ou plus) d'au moins 2 agents indépendants (**aucune décision fondée sur une seule source**), 4 au plus dans la limite des 15 lignes et de 5 lignes par zone (cœur compris) ; taille ∝ conviction ÷ volatilité sur 3 mois, **4 à 8 %** par ligne. Le budget non utilisé revient au cœur.
- **Jamais d'achat** d'une opportunité classée « À surveiller » par le chef d'orchestre ni **sous objection du contradicteur** (sérieuse ou non ; seule la revue « Pas d'objection spécifique » n'en est pas une).
- Les liquidités restent en euros, non rémunérées. **Valorisation en euros** au change du jour (Londres, Johannesburg et Tel-Aviv cotent en sous-unités : pence, cents, agorot).

## 2. Gestion du risque

- **Une seule série de décisions par jour**, calculée une fois puis exécutée : une seconde demande de décision le même jour est ignorée (sauf `--forcer`, usage manuel). Pas d'achat puis de vente du même titre le même jour.
- **Détention minimale de 5 jours** (`detention_min_jours`) avant toute vente ou réduction, **sauf stop-loss** ; pas de rachat d'un titre vendu depuis moins de 5 jours (20 jours après un stop, un verdict « Alléger » / « Éviter » ou une objection).
- **Liquidités minimales selon le palier de l'agent risque** (`liquidites_min_par_palier`) : 5 % en « Calme », 10 % en « Vigilance », 20 % en « Tension », 35 % en « Crise ». À la décision, les cibles en tiennent compte ; à chaque exécution, si les liquidités (achats en attente déduits) passent sous le plancher de plus d'un point, les lignes détenues depuis 5 jours au moins sont allégées en proportion.
- **Stops des satellites** : −15 % sous le prix de revient ; **suiveur** dès +20 % (15 % sous le plus haut, jamais abaissé) ; déclenché après **2 relevés** distincts sous le stop.
- **Prise de bénéfices partielle** : un tiers de la ligne à +30 %, une fois.
- **Sorties imposées** (après la détention minimale) : verdict « Alléger » ou « Éviter » sur une ligne détenue, objection sérieuse sur un satellite. Vérifiées à chaque exécution si le chef d'orchestre est à jour et sain.
- **Rééquilibrage** : une ligne cible déjà détenue n'est rééquilibrée que si son écart dépasse **3 points**, ou si elle est sous 4 % ; aucun ordre de moins de 500 €. Réductions plafonnées à 30 % de la valeur sur 30 jours glissants.
- **Lignes hors règles : réduction progressive** (`transition`). L'écran « Portefeuille démo » et `data/portefeuille.json` (`transition`) indiquent le nombre de lignes à solder, la date des premières sorties possibles et la fin estimée. Une ligne détenue qui ne respecte plus les règles (règle enfreinte, ou non retenue par la concentration) est soldée après la détention minimale, **5 sorties au plus par décision**, les règles enfreintes d'abord puis les plus petites lignes. Aucune nouvelle ligne n'est ouverte tant que le portefeuille dépasse 15 lignes. Chaque cas figure dans les **arbitrages expliqués** de la décision : vente, conservée (et jusqu'à quand), sortie ou entrée reportée, renforcement, réduction.
- **Aucune décision sur données périmées ou incomplètes** : sortie du chef d'orchestre de moins de 26 h avec l'analyse complète du jour et des données complètes (lignes pays, obligations et entreprises présentes, 20 % au plus sans score ni verdict, entrées pays, macro, risque et entreprises disponibles : `fraicheur.chef_complet`), agent risque de moins de 30 h avec un palier. Seul compte l'état des **données** : la santé des agents (écran Santé) n'est pas lue, si bien qu'un chef d'orchestre « dégradé » pour une raison étrangère à ses données (rédaction par Gemini, dépôt sur Google Drive) ne bloque rien. Sinon, l'agent attend, note les raisons et réessaie à l'exécution horaire suivante ; stops et valorisation continuent.

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
- Aucune décision fondée sur une seule source : convictions moyennes ou fortes du chef d'orchestre (plusieurs groupes de signaux concordants) pour le cœur, au moins 2 agents favorables pour un satellite, stop confirmé par 2 relevés.
- Aucune donnée inventée : un cours manquant garde le dernier cours connu (signalé) ; une source indisponible fait attendre l'agent.

## Commandes

```
python -m agents.trader                                  # exécution horaire (décision du jour si due)
python -m agents.trader --mode decision                  # décision du jour (ignorée si déjà prise ; --forcer pour la refaire)
python -m agents.trader --test --data /tmp/essai         # cours simulés, sans réseau (copie de data/ à fournir)
python -m agents.trader.tests.simulation                 # simulation de 3 mois sur données de test
python -m unittest discover -s agents/trader -t .        # tests
```
