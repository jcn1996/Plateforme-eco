# Agent macro — règles de conduite

Mêmes règles que l'agent pays (voir `agents/pays/regles.md`).

## Ton
- Analyse froide et factuelle, sans superlatifs : les textes passent le même contrôle des mots interdits que l'agent pays (`textes.ton_conforme`).
- Chaque chiffre est daté et sourcé. Aucune prévision propre : seules celles du FMI sont citées, comme telles.
- Pas d'IA : tous les textes sont produits par des règles.

## Phase du cycle
- Deux axes : la croissance (indicateur avancé de l'OCDE) et l'inflation (IPC mensuel ; IPCH d'Eurostat pour la zone euro). Pour chacun, on regarde si elle accélère ou ralentit.
- Correspondance des phases :

  | Croissance | Inflation | Phase |
  |---|---|---|
  | accélère | ralentit | Reprise |
  | accélère | accélère | Surchauffe |
  | ralentit | accélère | Ralentissement inflationniste |
  | ralentit | ralentit | Expansion sans inflation (l'activité se modère, l'inflation reflue) |

- **Deux signaux concordants au minimum** pour fixer la direction d'un axe. Les trois signaux sont :
  1. la variation sur 3 mois ;
  2. la même variation, un mois plus tôt ;
  3. la prévision du FMI pour l'année en cours, comparée à l'année précédente.

  Sans majorité, la direction précédente est conservée : aucun changement de phase n'est annoncé.
- La phase est reconstituée mois par mois sur les 18 derniers mois communs aux deux séries, ce qui donne la phase précédente et la date du changement.
- **Confirmation sur 3 semaines (anti-girouette)** : la phase calculée chaque jour (« phase brute ») n'est publiée qu'après avoir été observée sans interruption pendant 3 semaines (`confirmation_phase.semaines` dans `config.json`), avec au moins deux signaux concordants sur chaque axe qui change. Entre-temps, la phase publiée reste la précédente, et l'appli affiche « changement de phase en cours de confirmation » avec la phase observée, sa date de première observation et le nombre de jours écoulés. Un retour à la phase publiée remet le décompte à zéro. Au premier passage, l'historique `data/historique/macro/` est rejoué pour retrouver la phase confirmée. Le signal « changement de phase » n'est émis qu'à la confirmation. Motif : début novembre 2026, la phase du monde a alterné presque chaque jour entre « Expansion sans inflation » et « Ralentissement inflationniste », la variation de l'inflation mondiale passant d'un jour à l'autre de −0,27 à +0,26 point.
- Zones :
  - Monde : G20, faute d'agrégat « zone OCDE » dans le jeu de l'indicateur avancé.
  - États-Unis.
  - Zone euro : moyenne Allemagne, France, Italie, Espagne pour l'indicateur avancé ; IPCH d'Eurostat pour l'inflation.
  - Chine.
  - Japon.
  - Émergents : moyenne Brésil, Inde, Indonésie, Mexique, Afrique du Sud, Turquie pour l'indicateur avancé ; médiane pour l'inflation ; agrégat OEMDC du FMI.

## Confiance
Pour une zone :
- **élevé** : les 3 signaux concordent sur les deux axes ;
- **moyen** : au moins 2 signaux concordent sur chaque axe ;
- **faible** : un axe sans majorité, ou des données de plus de 4 mois.

Pour les signaux de récession, la confiance baisse si une source manque ou si une vérification croisée diverge.

## Ce qui pourrait me donner tort
Chaque zone porte un contre-scénario : ce qui ferait changer la phase, et les signaux qui votent dans l'autre sens.

## Signaux de récession
- **Courbes des taux** (US 10 ans − 2 ans, US 10 ans − 3 mois, Allemagne 10 ans − 2 ans) :
  - rouge si la courbe est inversée ;
  - orange si l'écart est sous 0,25 pt, ou si la courbe est désinversée depuis moins d'un an ;
  - vert sinon.
- **Règle de Sahm** : orange à partir de 0,3, rouge à partir de 0,5.
- **Indicateur avancé de l'OCDE** :
  - rouge s'il est sous 100 et en baisse ;
  - orange s'il est sous 100, ou en baisse ;
  - vert sinon.
- **Vérifications croisées** :
  - US 10 ans − 3 mois avec Yahoo (^TNX − ^IRX) ;
  - Allemagne avec la courbe AAA de la BCE ;
  - règle de Sahm recalculée à partir du chômage (UNRATE).

## Banques centrales
- Le taux retenu est le plus récent entre la BRI (quotidien) et la source nationale quand elle existe : FRED pour la Fed, BCE, Banque du Canada, BCB.
- Si la BRI n'intègre pas encore le dernier mouvement, la vérification est « non comparable », pas « divergente ».
- Le calendrier (`calendrier_banques_centrales.json`) contient les dates officielles relevées sur le site de chaque banque. L'écran « Santé des agents » signale une banque qui n'a plus de date future ; il prévient 60 jours avant. La PBoC ne publie pas de calendrier.

## Signaux pour le chef d'orchestre (`data/signaux/macro.json`)
- Changement de phase : importance forte pour le monde, moyenne pour les zones.
- Mouvement de banque centrale : forte pour la Fed et la BCE, moyenne pour les autres.
- Inversion ou désinversion d'une courbe.
- Franchissement du seuil de la règle de Sahm.

Chaque signal porte une date, une importance, une explication et sa source. Le fichier garde les 180 derniers jours.
