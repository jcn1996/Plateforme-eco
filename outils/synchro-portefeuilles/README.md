# Synchronisation automatique de « Mes portefeuilles » (facultative)

Ce dossier contient de quoi créer un **second dépôt GitHub, PRIVÉ**, qui récupère chaque jour vos positions réelles et les publie **sous forme chiffrée** pour l'appli.

> **Ne copiez jamais vos positions, vos clés ni ce mot de passe dans le dépôt public `Plateforme-eco`.**
> Ici, il n'y a que du code et des exemples fictifs.

## Fonctionnement

```
Interactive Brokers (Flex Web Service) ─┐
eToro (API officielle, clés « Read ») ──┼─► workflow quotidien du dépôt PRIVÉ
                                        │     · positions + cours sur 1 an (Yahoo)
                                        │     · secteur et pays des actions (Yahoo, symbole seul)
                                        │     · chiffrement AES-256-GCM (PBKDF2-SHA-256, 600 000 itérations)
                                        │       avec VOTRE mot de passe (secret GitHub)
                                        └─► branche « synchro » : portefeuilles.chiffre.json (illisible sans le mot de passe)
                                                   │
                     appli (téléphone) ◄───────────┘ téléchargé avec un jeton en lecture seule,
                                                     déchiffré SUR L'APPAREIL, stocké dans IndexedDB
```

- Le fichier n'existe jamais en clair : ni sur disque, ni dans les journaux du workflow (qui n'affichent que des nombres de lignes).
- Le numéro de compte IBKR est masqué (`U***1234`).
- La branche `synchro` est réécrite chaque jour (un seul commit) : aucun historique de vos positions ne s'accumule.
- Dans l'appli, le mot de passe est saisi une fois ; seule une clé dérivée **non extractible** est conservée sur l'appareil.
- **BoursoBank** n'a pas d'API : exportez le CSV des positions et importez-le dans l'appli (Mes portefeuilles › Importer un fichier).

## 1. Créer le dépôt privé

1. Sur GitHub : **+** (en haut à droite) › **New repository**.
2. Nom : par exemple `portefeuilles-synchro`. Cochez **Private**. Laissez « Add a README » coché. **Create repository**.
3. Ajoutez-y, à la racine, les fichiers de ce dossier :
   - `synchro_portefeuilles.py`
   - `requirements.txt`
   - `workflow-synchro.yml`, **renommé et placé** sous `.github/workflows/synchro.yml`.

   Le plus simple : **Add file › Upload files** pour les deux premiers ; pour le workflow, **Add file › Create new file**, tapez le nom `.github/workflows/synchro.yml` et collez le contenu.
4. **Settings › Actions › General** : vérifiez que les actions sont autorisées et, sous « Workflow permissions », choisissez **Read and write permissions** (le workflow doit pouvoir écrire la branche `synchro`).

## 2. Choisir le mot de passe de chiffrement

- Au moins 12 caractères ; idéalement 5 ou 6 mots tirés au hasard (`marmotte-cadran-velours-tilleul-orbite`).
- Notez-le dans votre gestionnaire de mots de passe : **sans lui, le fichier est irrécupérable**.
- Dans le dépôt privé : **Settings › Secrets and variables › Actions › New repository secret**
  - Nom : `PORTEFEUILLE_MOT_DE_PASSE` ; valeur : le mot de passe.

## 3. Interactive Brokers : requête Flex et jeton

**Créer la requête Flex**

1. Connectez-vous au **Client Portal** (portail web IBKR).
2. Menu **Performance & Reports › Flex Queries**.
3. Section **Activity Flex Query**, bouton **+** (Create).
4. Nom : `Positions appli`.
5. Sections à cocher :
   - **Open Positions** — Options : **Summary** ; champs : *Account ID, Currency, FX Rate To Base, Asset Class, Sub Category, Symbol, Description, ISIN, Listing Exchange, Quantity, Mark Price, Position Value, Cost Basis Price, Cost Basis Money, Level Of Detail*, **Multiplier**, et pour les options *Underlying Symbol, Expiry, Strike, Put/Call* (ou « Select All »).
     - **Ajoutez le champ Multiplier** à une requête existante (Flex Queries › icône crayon de la requête › Open Positions) : sans lui, le script suppose **100** pour une option (contrat standard sur actions américaines) ; un contrat d'une autre taille (mini-options, options sur indices ou contrats européens) aurait alors un prix de revient faux.
     - *Cost Basis Money* sert de secours quand *Cost Basis Price* est vide (certaines lignes transférées ou issues d'opérations sur titres) : prix de revient = Cost Basis Money ÷ (quantité × multiplicateur). Si les deux sont vides, l'appli affiche « prix de revient inconnu ».
   - **Cash Report** (facultatif, pour les liquidités) — champs *Currency, Ending Cash*.
   - **Account Information** — champ *Currency* (devise de base).
6. Delivery Configuration : **Format XML**, **Period : Last Business Day**.
7. **Save**. Dans la liste, l'icône d'information de la requête donne son **Query ID** (un nombre) : notez-le.

**Activer le Flex Web Service**

1. Toujours dans **Performance & Reports › Flex Queries**, encadré **Flex Web Service Configuration** (icône d'engrenage).
2. Activez le service et **générez le jeton** (Current Token). Choisissez la durée de validité maximale proposée (jusqu'à 1 an) et notez la date d'expiration.
3. Ne restreignez pas par adresse IP : les machines de GitHub Actions changent d'adresse.

**Secrets du dépôt privé**

- `IBKR_FLEX_TOKEN` : le jeton.
- `IBKR_FLEX_QUERY_ID` : le Query ID.

> Conseil : réglez la devise de base du compte IBKR en **EUR** (Settings › Account Settings › Base Currency). Les valeurs publiées sont exprimées dans la devise de base.

**Options** (Asset Class `OPT`) : publiées avec le type « option », le multiplicateur du contrat, le sous-jacent, l'échéance, le prix d'exercice et le sens (call ou put). Leur valeur (Position Value) inclut déjà le multiplicateur ; l'appli multiplie quantité × multiplicateur × prix de revient pour le coût, d'où un gain juste en euros et en %. Elles forment la catégorie « Options » de la répartition (ni pays ni secteur) et ne sont jamais rattachées à la fiche du sous-jacent. Si les champs *Underlying Symbol, Expiry, Strike, Put/Call* manquent, le script les lit dans le symbole OCC (`AAPL  261218C00200000`) ou la description (`AAPL 18DEC26 200 C`).

## 4. eToro : clés de l'API officielle (lecture seule)

eToro propose une API publique officielle qui donne accès au portefeuille réel (`GET /api/v1/trading/info/real/pnl` sur `public-api.etoro.com`, positions copiées incluses). Vérifié le 10/11/2026 dans la documentation (api-portal.etoro.com). L'API demande deux clés :

- **clé utilisateur** (`x-user-key`) :
  1. Sur eToro : **Settings › Trading › API Key Management › Create New Key**.
  2. Key Name : `appli portefeuilles` ; Environment : **Real** ; Permissions : **Read** (lecture seule, aucun ordre possible) ; facultatif : date d'expiration.
  3. **Generate Key**, puis code reçu par SMS.
  4. Copiez la clé **immédiatement** : elle n'est affichée qu'une fois.
- **clé d'application** (`x-api-key`, clé publique) : elle se trouve dans le portail développeurs eToro (api-portal.etoro.com). La documentation lue ne détaille pas l'écran exact : si elle n'apparaît pas à côté de la clé utilisateur, cherchez la rubrique « Authentication » du portail.

**Secrets du dépôt privé** : `ETORO_API_KEY` (clé d'application) et `ETORO_USER_KEY` (clé utilisateur).

Notes :
- Les positions à effet de levier (CFD) sont signalées ; leur « valeur » est le montant investi plus la plus-value latente.
- Le script accepte les deux casses de champs que la documentation mélange (`instrumentID` / `instrumentId`). Si eToro modifie son format, le workflow l'indique (« eToro : … ») sans bloquer IBKR.
- **Symboles** : ceux d'eToro sont convertis vers ceux de Yahoo Finance, utilisés par les fiches de l'appli :
  - classes d'actions : `GOOG` → `GOOGL`, `BRK.B` → `BRK-B`… ;
  - suffixes de place : `.ZU` → `.SW` (Zurich), `.NV` → `.AS` (Amsterdam), `.LSB` → `.LS` (Lisbonne), `.ASX` → `.AX` ; `.L`, `.PA`, `.DE`, `.MI`, `.MC`, `.AS`, `.HK` (complété à 4 chiffres : `700.HK` → `0700.HK`), `.ST`, `.CO`, `.OL`, `.HE`, `.BR` sont conservés ;
  - cryptoactifs (Bitcoin `BTC` et les autres) : `BTC-USD`, classés « Cryptoactifs ».

  L'appli applique la même conversion aux lignes déjà synchronisées.

## Secteur et pays des actions sans fiche

Pour chaque action détenue, le script demande à Yahoo Finance son secteur et son pays (`yfinance`, **seul le symbole est envoyé**, jamais une quantité ni un montant). L'appli s'en sert uniquement pour les actions sans fiche (introduction en Bourse récente, petite capitalisation hors univers) : elles sont alors classées sans saisie. Option `--sans-profils` pour désactiver ces requêtes.

Les lignes qui restent non classées portent l'étiquette **« catégorie à saisir »** : touchez-la pour choisir catégorie, secteur et pays. Ce choix est mémorisé sur l'appareil (IndexedDB) et réappliqué à chaque synchronisation, même si la ligne disparaît puis revient.

## 5. Premier lancement

1. Dépôt privé › **Actions › Synchro portefeuilles › Run workflow**.
2. Le journal doit finir par `Fichier chiffré écrit : N portefeuille(s), M ligne(s)…`.
3. La branche **synchro** contient alors `portefeuilles.chiffre.json` (illisible : c'est normal).

Ensuite, le workflow tourne seul chaque jour à 5 h 17 UTC.

## 6. Jeton d'accès en lecture pour l'appli

L'appli doit lire le fichier chiffré du dépôt privé. Créez un **jeton à portée fine**, limité à ce dépôt et à la lecture :

1. GitHub › photo de profil › **Settings › Developer settings › Personal access tokens › Fine-grained tokens › Generate new token**.
2. Nom : `appli portefeuilles (lecture)` ; expiration : 1 an maximum.
3. **Repository access : Only select repositories** › votre dépôt privé.
4. **Permissions › Repository permissions › Contents : Read-only** (rien d'autre).
5. **Generate token** et copiez-le.

Ce jeton ne permet que de lire ce dépôt, qui ne contient que du code et un fichier chiffré.

## 7. Réglage dans l'appli

Menu › Suivi › **Mes portefeuilles** › **Sauvegarde, synchronisation et réglages** › *Synchronisation automatique* :

- **Dépôt privé** : `votre-compte/portefeuilles-synchro` ;
- **Branche** : `synchro` ; **Fichier** : `portefeuilles.chiffre.json` ;
- **Jeton GitHub** : le jeton de l'étape 6 ;
- **Mot de passe de chiffrement** : celui de l'étape 2 (saisi une seule fois sur l'appareil) ;
- cochez **Synchroniser automatiquement**, puis **Synchroniser maintenant**.

Un portefeuille par compte apparaît (« Interactive Brokers U***1234 », « eToro »). Les catégories que vous saisissez à la main (pour les fonds) sont conservées d'une synchronisation à l'autre.

## Tester sans données réelles

```bash
pip install -r requirements.txt
python -m unittest discover -s outils/synchro-portefeuilles -t outils/synchro-portefeuilles
```

Les tests utilisent des relevés **fictifs** (`tests/ibkr_fictif.xml`, `tests/etoro_fictif.json`) : une option (call avec champs Flex, put vendu sans multiplicateur), une ligne sans Cost Basis Price, une sans aucun prix de revient, `GOOG`, `ZURN.ZU`, `FIG` (secteur et pays par une réponse Yahoo simulée, sans réseau) et `BTC`. Le fichier `js/tests/donnees/synchro-exemple.chiffre.json` (contenu fictif, mot de passe `exemple-fictif-ne-pas-utiliser`) vérifie que l'appli déchiffre bien ce que produit le script.

## En cas de problème

| Message | Cause probable |
| --- | --- |
| `IBKR : demande refusée (code 1012…)` | jeton expiré : régénérez-le (étape 3) |
| `IBKR : demande refusée (code 1014…)` | Query ID invalide |
| Appli : option avec un gain aberrant (×100 ou ÷100) | champ **Multiplier** absent de la requête Flex et contrat non standard : ajoutez-le (étape 3) |
| Appli : « prix de revient inconnu » | Cost Basis Price et Cost Basis Money vides dans le relevé IBKR (ajoutez Cost Basis Money à la requête) |
| `eToro : HTTP 401/403` | clés erronées, expirées ou sans droit « Read » sur l'environnement **Real** |
| Appli : « Accès refusé par GitHub » | jeton expiré ou sans accès « Contents : Read-only » au dépôt |
| Appli : « Mot de passe incorrect » | mot de passe différent du secret `PORTEFEUILLE_MOT_DE_PASSE` |
