# Agent pays : sources, hiérarchie et vérification croisée

Ce document décrit d'où viennent les chiffres, comment l'agent choisit entre plusieurs sources et comment il contrôle leur qualité.
Le code correspondant se trouve dans `croisement.py` (choix et comparaison) et `agent.py` (candidats, contrôle de qualité, journal). Les paramètres (tolérances, bornes, couverture, séries nationales) sont dans `config.json`.

Toutes les sources sont **gratuites**. Une seule demande une clé, gratuite elle aussi : FRED. Si la clé est absente, la source est simplement ignorée.

## 1. Hiérarchie des sources

| Rang | Niveau | Exemples |
|---|---|---|
| 1 | **Source nationale officielle** | INSEE, Destatis, ONS, BLS, Statistics Bureau of Japan, IBGE, Statistique Canada ; banques centrales : BCE (zone euro), Banque du Canada, Banco Central do Brasil, Réserve fédérale |
| 2 | **Organisation internationale** | FMI, OCDE, BRI, Banque mondiale, Eurostat, cours de référence de la BCE |
| 3 | **Source de marché** | Yahoo Finance (yfinance) |

Règles de choix :
- la source du rang le plus élevé l'emporte ;
- à rang égal, une série mensuelle observée passe avant une estimation annuelle ;
- à fiabilité égale, **la donnée la plus récente l'emporte** ;
- en cas d'égalité complète, on suit l'ordre de la configuration.

## 2. Sources par indicateur

| Indicateur | Sources, dans l'ordre de priorité | Comparées entre elles |
|---|---|---|
| Croissance du PIB | FMI (WEO, année en cours) ; OCDE (Perspectives économiques, prévision de l'année) ; Banque mondiale (dernière année écoulée) | FMI et OCDE (même année) |
| Inflation | institut national (INSEE, Destatis, ONS, BLS, Japon, IBGE, Statistique Canada) ; OCDE (IPC) ; Eurostat (IPCH) ; FMI et Banque mondiale (annuels) | séries mensuelles entre elles (à deux mois près) |
| Indicateur avancé | OCDE (CLI), seule source | — |
| Taux directeur (taux réel) | banque centrale nationale (BCE pour la zone euro) ; BRI | séries mensuelles entre elles |
| Solde courant | FMI et Banque mondiale, dernière année écoulée | oui (même année) |
| Momentum 12 mois | Yahoo Finance (ETF pays) | — |
| Devise sur 3 mois | BCE (cours de référence, valeur en dollars recalculée) ; Yahoo Finance | oui (à 7 jours près) |
| Valorisation relative | Yahoo Finance (PER de l'ETF pays) | — |
| Flux étrangers (flux de l'ETF pays) | émetteur de l'ETF : iShares (page du fonds), SSGA (fichier des VL de SPY), VanEck (fichier des VL de VNM), Global X (page du fonds) ; Yahoo Finance (parts et VL) en secours | parts en circulation, à la même date (tolérance 2 %) ; parts × VL contre l'actif net publié (tolérance 1,5 %) |

Accès techniques :
- **BLS** (`api.bls.gov`, version 1 sans clé, série `CUUR0000SA0`, CPI-U) pour l'inflation américaine, en plus de FRED (`CPIAUCSL`, si `FRED_API_KEY` existe). La version 1 est limitée à 25 requêtes par jour et par adresse IP ; avec le secret facultatif `BLS_API_KEY`, l'agent passe à la version 2. La série BLS de DBnomics a été retirée : elle n'est plus mise à jour depuis 2025-01.
- **OCDE, IPC** : l'OCDE publie l'IPC des pays passés à la nomenclature COICOP 2018 (Suisse, Espagne, France, Italie, Pays-Bas, Pologne, Suède, Turquie…) dans un nouveau jeu, `DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL` ; les autres pays (États-Unis, Royaume-Uni, Allemagne, Corée…) restent à jour dans `DSD_PRICES@DF_PRICES_ALL`. L'agent interroge les deux et garde, pour chaque pays, la série la plus récente.
- **DBnomics** (`api.db.nomics.world`) pour les instituts nationaux. Exemples : `INSEE/IPC-2025/…`, `DESTATIS/61111BM001/DG.PREIS1`, `ONS/MM23/D7G7.M`, `STATJP/CPIm/001`.
- **Banque mondiale** : API v2, `api.worldbank.org`.
- **Eurostat** : jeu `prc_hicp_minr`.
- **BCE** : Data Portal, `data-api.ecb.europa.eu`, séries `FM` et `EXR`.
- **Banco Central do Brasil** : API SGS.
- **Banque du Canada** : API Valet.
- **FRED** : clé gratuite dans le secret GitHub `FRED_API_KEY`.
- **Émetteurs d'ETF** (flux d'investissement, `agents/pays/sources_flux.py`) : iShares, page du fonds (`www.ishares.com/us/products/…`, données `sharesOutstanding`, `navAmount`, `totalNetAssetsFundLevel`) ; SSGA, `navhist-us-en-spy.xlsx` (date, VL, parts, actif net) ; VanEck, `…/downloads/fundhistoprices/` (date, VL, actif net : parts = actif net / VL, arrondies au millier) ; Global X, page du fonds (`NAV … As of`, `Shares Outstanding`, `Net Assets`). Les adresses se règlent dans `config.json` (`flux_etf.emetteurs`). Un relevé de plus de 10 jours est rejeté.

Les séries nationales se règlent dans `config.json` (`sources_nationales`). Pour ajouter un pays, il suffit d'y ajouter l'identifiant DBnomics de la série. Indiquez `"transformation": "glissement"` pour un indice, et `"direct"` pour une série déjà en %.

## 3. Vérification croisée

Pour chaque indicateur, l'agent récupère la valeur auprès de chaque source disponible, puis :

1. **contrôle la qualité** de chaque valeur (section 4) ;
2. **retient** la valeur de la source prioritaire (section 1) ;
3. **compare** la valeur retenue aux autres sources *comparables* : même nature (mensuelle, annuelle ou quotidienne) et même période ;
4. publie le résultat.

| Cas | Statut publié | Effet |
|---|---|---|
| Écart inférieur ou égal à la tolérance | `concordant` | on garde la source prioritaire ; confiance de l'indicateur **élevée** |
| Écart supérieur à la tolérance | `divergent`, affiché « sources divergentes » | confiance de l'indicateur **faible** ; −0,1 sur le score de confiance du pays, dont le niveau est plafonné à « moyen » ; mention dans « Ce qui pourrait me donner tort » |
| Une seule source valable | `source_unique` | confiance de l'indicateur plafonnée à **moyen** |

Tolérances (`tolerances_divergence`, en points) :
- croissance : 0,5 ;
- inflation : 0,5 ;
- taux directeur : 0,25 ;
- solde courant : 1 ;
- devise sur 3 mois : 1 ;
- momentum : 3.

**Plafond au niveau du pays** : si plus de la moitié des indicateurs disponibles d'un pays reposent sur une seule source, sa confiance globale est plafonnée à « moyen ».

**Taux réel** : il combine deux indicateurs. Il est `divergent` si le taux directeur ou l'inflation l'est, et `concordant` seulement si les deux le sont.

La fiche pays affiche, pour chaque indicateur :
- les sources consultées, avec leur valeur et leur date ;
- la valeur retenue ;
- le statut de chaque source : retenue, concorde, diverge, non comparable, rejetée ou échec, avec la raison.

## 4. Contrôles de qualité

Une valeur est **rejetée** (statut `rejetée`) si elle est :
- **aberrante** : hors des bornes physiques de `bornes_aberrantes`, par exemple une inflation hors de −15 % à 300 % ou une croissance hors de −30 % à +30 % ;
- **trop ancienne** :
  - donnée mensuelle de plus de 6 mois ;
  - cours quotidien de plus de 10 jours ;
  - donnée annuelle antérieure à l'année dernière.

Ces bornes sont différentes des seuils « à vérifier » (`regles.md`, section 5). Ces seuils signalent une valeur possible mais inhabituelle. Une telle valeur n'est pas signalée si une seconde source la confirme.

Une source est **en échec** (statut `échec`) si elle n'a pas répondu ou si elle ne publie rien pour un pays qu'elle couvre normalement (`couverture` dans `config.json`).

**Alerte « Qualité des données »** :
- elle se déclenche si **plus d'un tiers des sources consultées pour un pays** sont en échec ou rejetées ;
- une source compte comme en échec quand toutes ses valeurs pour ce pays ont échoué ou ont été rejetées ;
- l'alerte s'affiche sur la fiche du pays et en tête du bandeau des alertes de l'appli.

**Valeur manquante** : la dernière valeur connue est conservée et marquée « ancienne », sauf si elle a elle-même plus de 6 mois (donnée mensuelle ou quotidienne).

## 5. Journal et récapitulatif

- **`data/journal/agent-pays.json`** : à chaque exécution où l'état change, l'agent écrit :
  - l'état de chaque source ;
  - les sources en erreur ;
  - les pays en alerte ;
  - la liste des échecs et des rejets (pays, indicateur, source, raison).

  Le journal garde les 90 dernières entrées.
- **`data/recap/pays-AAAA-MM-JJ.md`** : récapitulatif factuel de l'exécution :
  - ce qui a changé ;
  - les principaux mouvements de notes (3 points ou plus) ;
  - les divergences entre sources ;
  - les données manquantes ou anciennes ;
  - les sources en échec et les alertes « Qualité des données ».

  Son ton est contrôlé automatiquement, avec la même liste de mots interdits que les textes de l'appli.
