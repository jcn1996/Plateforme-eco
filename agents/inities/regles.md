# Agent initiés : règles

Code : `agents/inities/` (`sources.py` pour la collecte, `analyse.py` pour les calculs, `agent.py` pour
l'orchestration) · seuils : `agents/inities/config.json` · liste des super-investisseurs :
`config/super_investisseurs.json`. Sans IA.

L'agent suit trois familles d'initiés comme **signal supplémentaire** pour l'agent entreprises, et les élus du
Congrès **pour information seulement**. Il ne produit aucune recommandation par lui-même.

## 1. Dirigeants (signal principal)

**Sources**
- États-Unis : formulaires 4 de la SEC (déposés sous 2 jours ouvrés), repérés dans l'index quotidien d'EDGAR.
  Les sociétés suivies par l'agent entreprises sont lues en premier ; les autres le sont dans la limite de
  `edgar.form4_max_par_execution` par exécution (un formulaire non lu attend 30 jours pour une société suivie,
  7 jours sinon). Un même dépôt apparaît dans l'index sous le CIK de l'émetteur et de chaque déclarant : il
  n'est lu qu'une fois (numéro d'accession).
- France : déclarations des dirigeants de la base BDIF de l'AMF (PDF, partie française lue).
- Allemagne : base des « Directors' Dealings » de la BaFin (export CSV).
- Royaume-Uni : aucune source gratuite structurée exploitable (le NSM de la FCA ne publie que des communiqués
  au format libre) : non suivi.

**Opérations retenues** : achats sur le marché seulement (code P aux États-Unis, « Acquisition » d'actions
en France, « Kauf » d'actions en Allemagne). Exclus : exercices d'options (code M) et attributions (A),
donations (G), opérations programmées (case 10b5-1 cochée ou plan 10b5-1 cité dans une note de la transaction),
souscriptions et attributions gratuites (AMF), achats de moins de `achats.montant_min_usd` (10 000 $).

**Score « achats d'initiés » /100 par société** (achats des 60 derniers jours), moyenne pondérée de 5
composantes notées de 0 à 1 (`score.poids`) :

| Composante | Poids | Note |
|---|---|---|
| Achat opportuniste plutôt que routinier | 25 | 1 si le cours a baissé d'au moins 15 % sur les 3 mois précédant l'achat, ou si le dirigeant n'a fait aucun autre achat dans les 12 mois précédents (historique d'au moins un an) ; 0 s'il a fait au moins 3 achats dans les 12 mois précédents (achats réguliers) ; 0,5 sinon (historique trop court pour juger) |
| Achats groupés | 25 | acheteurs distincts sur 30 jours : 1 → 0,2 ; 2 → 0,6 ; 3 ou plus → 1 |
| Fonction | 20 | PDG ou directeur financier 1 ; autre dirigeant 0,7 ; administrateur 0,5 ; actionnaire de plus de 10 % ou autre 0,3 (meilleure fonction parmi les acheteurs) |
| Montant par rapport à ce que le dirigeant détient déjà | 20 | actions achetées ÷ actions détenues avant : ≥ 50 % → 1 ; ≥ 20 % → 0,7 ; ≥ 5 % → 0,4 ; sinon 0,15 ; première position → 1 ; inconnu (France, Allemagne) → 0,5 |
| Taille de la société | 10 | capitalisation (agent entreprises) : < 2 Md$ → 1 ; < 10 Md$ → 0,7 ; < 50 Md$ → 0,4 ; au-delà 0,2 ; inconnue 0,5 |

Le cours sur 6 mois vient de Yahoo Finance ; l'historique des achats (12 mois et plus) est accumulé par l'agent
dans `data/inities/etat.json` : au démarrage, le caractère « habituel » ne peut pas encore être jugé.

**Ventes** : les ventes des dirigeants ne sont **pas** un signal négatif, sauf **ventes massives et groupées**
(sociétés suivies par l'agent entreprises) : au moins 3 dirigeants vendent sur le marché (hors 10b5-1) en
30 jours, pour au moins 5 M$ au total, en cédant en moyenne au moins 20 % de ce qu'ils détenaient (`ventes`).

## 2. Activistes

Formulaires 13D (participation de plus de 5 % avec intention d'influencer), originaux et amendements, lus dans
l'index quotidien d'EDGAR (format XML depuis décembre 2024 ; en-tête SGML pour l'ancien format) : société,
investisseur, % détenu, date de l'événement, date de dépôt. Le déclarant est rapproché des super-investisseurs
suivis (noms des entités).

## 3. Super-investisseurs

**13F** (trimestriel) de chaque entité de `config/super_investisseurs.json` : vérification quotidienne du flux
« submissions » d'EDGAR ; un nouveau rapport est comparé au trimestre précédent. Pour chacun : nouvelles
positions, renforcements et allègements importants (variation d'au moins 25 % du nombre d'actions sur une
position d'au moins 1 %), positions soldées, principales positions (poids), date du trimestre et date de
dépôt. Les options (PUT, CALL) sont listées à part, hors poids. Un investisseur dont le dernier 13F couvre un
trimestre trop ancien est signalé « ne dépose plus » ; un 13F-NT (positions déclarées par une autre entité)
est signalé. Ticker des lignes : OpenFIGI (CUSIP), à défaut nom exact de la liste de la SEC.

Mention systématique : « 13F : positions américaines uniquement, avec jusqu'à 45 jours de retard ».

**CIK vérifiés le 07/11/2026** : voir `config/super_investisseurs.json`. Cas particuliers :
- Pershing Square (Ackman) : Pershing Square Capital Management dépose un 13F-NT depuis le 2e trimestre 2026,
  le 13F est déposé par Pershing Square Inc. (CIK 0002026053) ;
- Greenlight (Einhorn) : Greenlight Capital Inc. ne dépose plus depuis 2024 ; 13F de DME Capital Management ;
- Scion (Burry) : plus de 13F depuis le 3e trimestre 2025 (signalé « ne dépose plus ») ;
- Appaloosa (Tepper) : entité actuelle Appaloosa LP (l'ancienne Appaloosa Management LP ne dépose plus).

**Signal « conviction des super-investisseurs » /100 par société** : pour chaque investisseur qui détient le
titre, points selon le poids de la position (≥ 10 % → 3 ; ≥ 5 % → 2 ; ≥ 2 % → 1 ; sinon 0,5), + 1 si la
position est nouvelle ou renforcée ; score = min(100, points × 15). Une position très concentrée compte donc
plus qu'une ligne marginale, et plusieurs détenteurs plus qu'un seul.

**Positions hors États-Unis** (mention : « positions hors États-Unis visibles uniquement au-dessus des seuils
légaux ») : recherche des noms d'entités de chaque investisseur (`entites`, ex. Pabrai : Pabrai Investment
Funds, Dalal Street, Pabrai Wagons Fund) dans :
- France : franchissements de seuil (base BDIF de l'AMF, PDF) ;
- Corée : DART, déclarations de participation (règle des 5 %), secret `DART_API_KEY` facultatif ;
- Japon : EDINET, déclarations de grands actionnaires, secret `EDINET_API_KEY` facultatif ;
- Turquie : annonces KAP (seuils de 5 %) ;
- Inde : actionnaires de plus de 1 % de la répartition trimestrielle de l'actionnariat (BSE), pour les
  sociétés listées dans `hors_us.inde_bse` de chaque investisseur (pas de recherche globale par nom à la BSE).

## 4. Élus du Congrès (information seulement)

Déclarations de transactions (Periodic Transaction Reports) : index annuel et PDF du greffe de la Chambre ;
date de l'opération, date de déclaration et retard (la loi impose 45 jours). Sénat : le site
efdsearch.senate.gov impose d'accepter ses conditions d'utilisation avant toute consultation ; la source n'est
utilisée que si `elus.senat_actif` est mis à `true` dans la config. **Aucun effet sur les notes.**

## 5. Intégration

- **Agent entreprises** (section `recommandation.inities` de `agents/entreprises/config.json`) : deux
  signaux supplémentaires de la recommandation, chacun de pondération modérée (`poids` 0,5) dans la règle des
  3 signaux concordants : « Achats d'initiés » favorable à partir de 60/100, défavorable seulement en cas de
  ventes massives et groupées ; « Super-investisseurs » favorable à partir d'une conviction de 45/100. Ils ne
  sont pris en compte que si `data/inities.json` a moins de 10 jours.
- **Chef d'orchestre** (`data/signaux/inities.json`) : achats groupés de dirigeants (au moins 3 acheteurs en
  30 jours ; pas répété pendant 30 jours), nouvelle position d'un super-investisseur (d'au moins 1 % du
  portefeuille, 13F déposé depuis moins de 7 jours), nouveau 13D (déposé depuis moins de 3 jours ; importance
  forte si le déclarant est un super-investisseur suivi, moyenne si la société est suivie par l'agent
  entreprises, faible sinon). Le contradicteur de l'agent risque leur oppose les risques propres à la société.

## 6. Rythme

Du mardi au samedi à 6 h 35 UTC (mode « complet ») : formulaires 4 et 13D de la veille, AMF, BaFin,
franchissements de seuil hors États-Unis, 13F, élus. Dimanche et lundi (mode « leger ») : vérification des
nouveaux 13F et des élus. Les 13F sont vérifiés chaque jour (ils arrivent surtout dans les 45 jours après
chaque fin de trimestre).
