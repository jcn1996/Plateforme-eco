# Agent trader (démo) — règles

**Portefeuille fictif à but de démonstration, aucun ordre réel.** L'agent ne se connecte à aucun courtier et ne passe aucun ordre : chaque « ordre » est une ligne de `data/trader/etat.json`, exécutée sur le papier. Son seul but est de mesurer, en conditions réelles de marché, ce que valent les recommandations de la plateforme.

Paramètres : [`config.json`](config.json) (bloc `methode`). Code : `agent.py` (orchestration, journal des paris pays), `strategie.py` (poches, cibles, ordres, contrôle des paris pays), `portefeuille.py` (exécution simulée, valorisation, flux par poche), `performance.py` (statistiques, performance par poche, attribution), `observation.py` (signaux en observation), `sources.py` (cours).

## 1. Méthode par combinaisons du backtest (depuis novembre 2026)

Le backtest des règles de notation (rapport de référence : le **dernier recalibrage validé**, publié par le chef d'orchestre dans `chef.json` → `selections` → `source` ; au départ celui de novembre 2026) a montré que les notes et verdicts pays ne sont pas prédictifs et que les stops coûtaient du rendement. La méthode s'appuie désormais sur ce qui a le mieux tenu hors échantillon, sans jamais d'ETF monde :

Les candidats sont les lignes de la **liste d'investissement unique** du chef d'orchestre (`chef.json` → `liste`, `agents/chef/methode.md` § 4 ter), la même que celle affichée dans l'appli ; à défaut (ancienne sortie), ses sélections.

| Poche | Part du portefeuille | Candidats (liste unique du chef d'orchestre) |
|---|---|---|
| **Entreprises** | 70 à 85 % | sociétés retenues par une combinaison en service (au départ : M-score de Beneish + goodwill / actif ; goodwill / actif + rendement du FCF ; conversion du bénéfice en cash + goodwill / actif + rendement du FCF ; meilleurs 30 % sur chaque signal, univers du backtest : sociétés américaines non financières d'au moins 2 Md$). **25 % au plus par secteur.** |
| **Matières premières** | 0 à 20 % | celles retenues par les combinaisons de matières premières en service (au départ « Niveau historique + Positionnement CFTC » ; supports cotés : `supports` ; sans support coté, écartée) |
| **ETF pays (« paris pays »)** | 0 à 15 %, 3 lignes au plus | pays en tendance haussière et saine (suivi de tendance du chef d'orchestre : 12 mois hors dernier mois positive, cours au-dessus de la moyenne 200 jours, aucun excès) dont la valorisation relative n'est pas tendue ; les plus forts en premier |

- **15 lignes au plus, 4 à 8 % par ligne** ; le reste en liquidités s'il manque des candidats (petit tampon de 1 % pour les frais).
- **Ordre de priorité** : entreprises (au moins 70 % si les candidats le permettent), puis matières premières, puis paris pays ; à poids égal dans chaque poche.
- **Les lignes déjà détenues et toujours retenues passent avant les nouvelles** (moins de rotation, moins de frais).
- **Ni stop ni prise de bénéfices.** Une ligne est vendue quand elle **sort de la liste** : au rééquilibrage mensuel (premier jour de décision du mois, juste après la révision mensuelle de la liste), ou en cours de mois quand le chef d'orchestre l'en retire (sortie de sa combinaison confirmée 5 jours de suite ; motif « sortie de la liste », contrôlé à chaque exécution). Aucun achat en cours de mois.
- **Paris pays** : vendus **dès qu'un excès se déclenche** — accélération parabolique ≥ 2,5 fois la volatilité mensuelle, valorisation au-delà du 70e percentile, positionnement au 90e percentile — **ou que la tendance casse** ; contrôlé à chaque exécution horaire, dès que le chef d'orchestre le signale. Un pari dont une condition d'entrée manque désormais (sans excès ni cassure) est gardé.
- **Journal des paris pays** (`etat.json` → `paris_pays`, écran « Portefeuille démo ») : date et raison d'entrée, date et raison de sortie, performance du pari et du MSCI World en euros sur la même période, écart.
- **Combinaisons entretenues par le backtest mensuel** (`agents/backtest/entretien.py`, méthode : `agents/backtest/methode.md` § 6 bis) : retrait d'une combinaison « Non confirmée » deux mois de suite, une nouvelle combinaison par trimestre au plus, aucun changement s'il ne fait pas mieux hors échantillon ; un changement ne s'applique qu'une fois sa pull request validée à la main. Les lignes qui sortent d'une combinaison retirée sont vendues au rééquilibrage mensuel suivant, comme toute sortie de combinaison.
- **Plancher de liquidités par palier de risque : retiré** (la structure 70-85 % d'entreprises n'est pas compatible avec 20 à 35 % de liquidités en « Tension » ou en « Crise »). Le palier reste lu et affiché.

## 2. Changement de méthode (transition)

Au premier rééquilibrage de la nouvelle méthode, **toutes les lignes qui ne respectent pas ces règles sont vendues en une fois** (motif « changement de méthode »), chaque ordre étant journalisé avec sa raison dans `data/trader/operations.json`. L'historique de performance est conservé ; la date du changement est enregistrée (`etat.json` → `methode`, `changements_methode`) et marquée sur le graphique « Performance vs MSCI World ».

## 3. Exécution simulée

- **Jamais à un cours passé** : un ordre est exécuté au premier cours disponible *après* l'heure de sa décision (ouverture de la première barre de 5 minutes de Yahoo Finance ; à défaut, ouverture de la première séance qui suit le jour de la décision). Les décisions de 7 h 33 UTC sont donc exécutées à l'ouverture des marchés concernés. Ordres non exécutés au bout de 5 jours : expirés.
- **Ventes avant achats** ; achats limités aux liquidités disponibles (produit estimé des ventes compris).
- **Complément d'exécution** : un achat réduit faute de liquidités au moment de son exécution (les ventes sur une place asiatique, par exemple, ne s'exécutent qu'à l'ouverture de leur marché, dans la nuit) est noté (`etat.json` → `complements`) et complété dès que les liquidités le permettent, au-dessus du tampon de 1 % et une fois les ventes en attente exécutées, jusqu'à la cible du rééquilibrage (motif « complément d'exécution »). Ce n'est pas un rééquilibrage : seule la part non exécutée de l'ordre décidé est rachetée. Cas réel : UNG, acheté le 16/11/2026 pour 3 768 € (3,8 %) au lieu de 8 %, parce que le produit des ventes de 5108.T et 688235.SS (environ 5 150 €) n'était pas encore encaissé à 14 h 30 UTC ; complété à la première exécution suivant la mise en service. Contrôle publié : `ecarts_aux_cibles` (lignes à plus d'un point de leur cible, `methode.tolerance_cible_points`), affiché dans l'écran « Portefeuille démo ».
- **Frais** : 0,1 % du montant de chaque ordre (`execution.frais_pct`).
- **Écart achat/vente estimé** (`execution.ecart_achat_vente_pct`) : 0,04 % pour les grands ETF, 0,10 % pour les autres ETF, 0,06 % pour les actions américaines, 0,12 % européennes, 0,20 % asiatiques développées, 0,35 % émergentes ; la moitié est payée à chaque achat et à chaque vente.
- **Quantités entières** : un achat inférieur au prix d'une part est annulé et noté.
- **Contango** : les fonds de matières premières adossés à des contrats à terme le signalent dans « Ce qui pourrait me donner tort ».
- **Rééquilibrage mensuel** d'une ligne détenue et toujours retenue : seulement si son écart à la cible dépasse 3 points ou si elle sort de la fourchette 4-8 % ; aucun ordre de moins de 500 €.

## 4. Suivi de performance

- Valeur et historique quotidien, performance depuis le départ, sur 1 mois et sur 3 mois ; **référence** : MSCI World en euros (ETF URTH ÷ EUR/USD).
- **Étiquettes de poche** : une position héritée de l'ancienne méthode mais retenue par la méthode actuelle prend la poche de sa ligne cible (CNX : « satellite » → « entreprises » ; EWW, EPOL, COLO : « cœur » → « pays »), à chaque exécution et à chaque achat. L'historique n'est pas réécrit : la valeur passe d'une poche à l'autre comme un flux (sortie de l'ancienne, entrée dans la nouvelle), pour que la performance par poche reste juste, et le changement est journalisé (`etat.json` → `reetiquetages`, publié dans `portefeuille.json`).
- **Performance séparée de chaque poche** (entreprises, matières premières, ETF pays) depuis le changement de méthode, chacune contre le MSCI World (étalon, non détenu) : indice chaîné jour par jour, net des achats et des ventes (achats comptés en début de journée, ventes en fin de journée), frais compris.
- Ratio de Sharpe (taux sans risque 2 %), volatilité, perte maximale ; taux de réussite des opérations clôturées, gain moyen et perte moyenne ; attribution par poche et par classe d'actifs.

## 4 bis. Portefeuille « momentum seul » et bilan du mois

- **Momentum seul** (`agents/trader/bilan.py`) : étalon suivi depuis le 16/11/2026, rien n'est acheté. À chaque début de mois, les 20 % de sociétés les plus fortes sur 12 mois hors dernier mois, à parts égales, dans l'univers du backtest (sociétés américaines non financières, hors immobilier et holdings, d'au moins 2 Md$) ; cours hebdomadaires des fiches de l'agent entreprises, sans dividendes ni frais (`etat.json` → `momentum_seul`).
- **Bilan du mois** : à la première exécution du trader de chaque mois (en pratique le 1er, ou le premier jour ouvré), `data/bilan/AAAA-MM.json` pour le mois écoulé : performance du portefeuille démo, du MSCI World (en euros) et du momentum seul sur le mois et depuis le 16/11/2026 ; entrées et sorties de la liste du chef d'orchestre ; part des signaux en observation qui battent le MSCI World à 1 mois. Écran « Bilan du mois » (lien depuis l'accueil, Menu → Suivi). Une valeur manquante est publiée à null.

## 5. Signaux en observation

Chaque jour, l'agent **enregistre sans les utiliser** trois familles de signaux que le backtest n'a pas pu tester faute d'historique gratuit : achats de dirigeants (agent initiés), révisions à la hausse des analystes (bénéfice par action de l'exercice relevé d'au moins 3 % en 30 jours, plus de relèvements que de baisses, au moins 5 analystes) et relèvements de guidance (agent entreprises). Pour chacun : cours au jour de l'enregistrement, puis performance à 1, 3 et 6 mois, comparée au MSCI World (ETF URTH). Résultat : `data/observation.json`, écran « Signaux en observation » (Menu → Suivi). Une panne de ce suivi ne bloque jamais l'agent.

## 6. Rythme

- Décision chaque jour de semaine à 7 h 33 UTC (workflow `agent-trader.yml`, lancé par le planificateur), après l'analyse complète du chef d'orchestre (7 h 15) : rééquilibrage le premier jour de décision du mois, vérification les autres jours.
- Toutes les heures (minute 5) de 8 h à 21 h UTC en semaine : exécution des ordres, valorisation, contrôle des paris pays, signaux en observation (une fois par jour) ; décision du jour si elle n'a pas pu être prise à 7 h 33.
- **Aucune décision sur données périmées ou incomplètes** : sortie du chef d'orchestre de moins de 26 h avec l'analyse complète du jour, ses sélections et ses lignes pays, agent risque de moins de 30 h. Sinon, l'agent attend, note les raisons et réessaie à l'exécution horaire suivante.

## 7. Règles de conduite

- Ton froid et factuel ; chaque décision et chaque ordre disent aussi « Ce qui pourrait me donner tort » (combinaisons non significatives dans le backtest, biais du survivant, absence de stop).
- Aucune donnée inventée : un cours manquant garde le dernier cours connu (signalé) ; une source indisponible fait attendre l'agent.

## Commandes

```
python -m agents.trader                                  # exécution horaire (décision du jour si due)
python -m agents.trader --mode decision                  # décision du jour (ignorée si déjà prise ; --forcer pour la refaire)
python -m agents.trader --test --data /tmp/essai         # cours simulés, sans réseau (copie de data/ à fournir)
python -m agents.trader.tests.simulation                 # simulation de 3 mois sur données de test
python -m unittest discover -s agents/trader -t .        # tests
```
