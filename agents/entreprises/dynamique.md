# Dynamique des résultats

Code : `agents/entreprises/dynamique.py` · paramètres : section `dynamique` de `agents/entreprises/config.json`
(modifiables sans toucher au code) · tests : `agents/entreprises/tests/test_dynamique.py`.

Bloc de signaux supplémentaire de l'agent entreprises : **guidance** de la direction, **révisions** des
estimations des analystes, **surprises** de résultats et **objectifs de cours**. Il reçoit une note sur 100,
pèse modérément dans la note globale et compte comme un signal de la recommandation.

## 1. Guidance (États-Unis)

- **Détection** : à chaque exécution quotidienne, le flux `submissions` de la SEC (déjà lu pour les 10-K et
  10-Q) donne les dépôts **8-K « Item 2.02 Results of Operations »** des `sec.fenetre_jours` (120) derniers
  jours ; le plus récent (`sec.communiques_par_societe`) est analysé s'il ne l'a pas déjà été.
- **Communiqué** : pièce jointe EX-99.1 (et EX-99.2 s'il existe, souvent les commentaires du directeur
  financier), lue dans la page d'index du dépôt.
- **Passages de prévision** (règles, sans IA) : section qui suit un titre « Outlook » ou « Guidance »,
  puis phrases au futur ou de guidance (expects, anticipates, reaffirms, raises its outlook…) ; mentions
  juridiques (forward-looking statements…) écartées ; au plus `sec.caracteres_max` caractères.
  **Sans passage, le communiqué est classé « aucune guidance » sans appel à Gemini** (Apple, Mastercard,
  Caterpillar, par exemple, donnent leurs prévisions lors de la conférence et non dans le communiqué).
- **Extraction par Gemini** (secret `GEMINI_API_KEY`, un communiqué par appel) : indicateur (chiffre
  d'affaires, BPA, marge, autre), période, valeur ou fourchette, évolution par rapport à la guidance
  précédente : **relevée, maintenue, abaissée, initiée** (première guidance pour cet indicateur et cette
  période) ou **retirée**. La guidance précédente connue est fournie à Gemini.
- **Anti-hallucination** :
  - chaque élément cite mot pour mot une phrase ou une ligne du communiqué ; la citation doit être retrouvée
    dans le texte téléchargé à la SEC (casse, espaces, apostrophes et tirets près ; fragments séparés par
    « … » acceptés dans l'ordre) : sinon l'élément est écarté. La fiche affiche la citation et le lien SEC ;
  - les nombres de la valeur et de la fourchette doivent figurer dans la citation ;
  - quand une guidance précédente chiffrée existe pour le même indicateur, la même période et la même unité,
    l'évolution est **recalculée à partir des fourchettes** (milieu en hausse ou en baisse de plus de
    `seuil_evolution_pct` %, sinon « maintenue »), l'avis de Gemini étant gardé à part.
- **Évolution d'un communiqué** : celle du chiffre d'affaires et du BPA en priorité ; la plus défavorable
  l'emporte (retirée, puis abaissée, relevée, initiée, maintenue).
- **Gemini indisponible** (clé absente, quota du jour atteint, panne) : le communiqué est marqué
  **« non analysé »** et repris à l'exécution suivante (au plus `sec.tentatives_max` tentatives). Gemini a
  répondu mais aucune citation n'a été retrouvée : « aucune guidance » (rien n'est retenu).
- **Budget** (`gemini`) : budget propre à l'agent entreprises, compté à part des agents géopolitique et
  risque (état : `data/entreprises/etat_dynamique.json`), sans dépasser les quotas gratuits par projet :
  Flash-Lite 800 (géopolitique) + 40 (risque) + 60 (entreprises) = 900 ≤ 1 000 appels par jour ; Flash de la
  génération précédente 200 + 20 = 220 ≤ 250. Les communiqués les plus récents passent en premier ; le reste
  attend le lendemain.
- **Historique** : `data/historique/guidance/TICKER.json` (12 derniers communiqués : date, liens, statut,
  guidances, citations, éléments écartés et raison).

**Hors États-Unis** : pas de source structurée gratuite des communiqués ; la fiche affiche « guidance non
disponible » (à étendre si une source fiable apparaît).

## 2. Analystes (Yahoo Finance, toutes régions quand disponible)

Une requête par société et par jour (modules `earningsTrend`, `earningsHistory`, `financialData`) :

- tendance des estimations de BPA (actuelle, il y a 7, 30, 60 et 90 jours) pour le trimestre et l'exercice
  en cours et suivants ; nombre de révisions à la hausse et à la baisse sur 7 et 30 jours ;
- objectifs de cours (moyen, haut, bas, médian), écart au cours, nombre d'analystes ;
- surprises de résultats (BPA publié contre estimation) des 4 derniers trimestres.

Révision sur 30 (ou 90) jours = moyenne, sur les exercices en cours et suivant, de la variation de
l'estimation de BPA (estimation de départ inférieure à 0,01 en valeur absolue : non calculée).

**Moins de `analystes_min` (3) analystes** : ces données sont affichées à titre indicatif seulement (faible
fiabilité) et n'entrent pas dans la note.

## 3. Note du bloc et signal

| Composante | Poids | Barème |
|---|---|---|
| Guidance (moins de `guidance_validite_jours` = 120 jours) | 0,35 | relevée 85, initiée 60, maintenue 55, abaissée 20, retirée 15 |
| Révisions sur 30 jours | 0,25 | −10 % → 10 ; −3 % → 30 ; 0 → 50 ; +3 % → 70 ; +10 % → 90 |
| Révisions sur 90 jours | 0,20 | −20 % → 10 ; −6 % → 30 ; 0 → 50 ; +6 % → 70 ; +20 % → 90 |
| Surprises (écart moyen, chaque trimestre borné à ±50 %, 2 trimestres au moins) | 0,20 | −15 % → 10 ; −3 % → 35 ; 0 → 45 ; +3 % → 60 ; +10 % → 80 ; +25 % → 90 |

Note = moyenne pondérée des composantes disponibles. Signal : favorable à partir de `signal_positif` (65),
défavorable sous `signal_negatif` (40), neutre sinon ou sans note.

**Note globale** : le bloc y pèse `poids_note_globale` (8 %) des pondérations disponibles ; la règle des deux
signaux concordants s'applique comme aux autres indicateurs ; la couverture (et donc la confiance) reste celle
des indicateurs comptables et de marché. La fiche garde aussi la note sans ce bloc (`note_sans_dynamique`).

**Confiance du bloc** : élevée (États-Unis, guidance retenue, au moins 3 composantes et 3 analystes), moyenne
(au moins 2 composantes et 3 analystes), faible sinon. Chaque bloc a sa rubrique « Ce qui pourrait me donner
tort ».

## 4. Recommandation

- Le bloc est un **cinquième signal** de la règle des « 3 signaux concordants » (`recommandation.md`).
- Une **guidance abaissée ou retirée depuis moins de `guidance_negative_jours` (90) jours interdit « Acheter »**
  (et « Renforcer ») : au mieux « Acheter sur repli » ou « Attendre ». **Exception** (`exception_guidance`),
  quand la valorisation intègre déjà une forte baisse : valeur estimée fiable au moins 30 % au-dessus du cours
  **et** momentum 12 mois inférieur ou égal à −15 % ; la justification le dit en chiffres.
- Les objectifs de cours des analystes sont affichés pour information : ils ne remplacent pas la fourchette
  de valeur calculée par l'agent.

## 5. Appli et signaux

- Fiche entreprise : bloc « Dynamique des résultats » (dernière guidance avec badge, citations et liens SEC ;
  graphique de l'évolution des estimations sur 90 jours ; révisions ; surprises des 4 derniers trimestres ;
  objectifs de cours).
- Écran Pépites : badge quand la guidance a été relevée, abaissée ou retirée il y a moins de `badge_jours`
  (45) jours.
- `data/signaux/entreprises.json` (chef d'orchestre) : `guidance_relevee`, `guidance_abaissee` (importance
  moyenne), `forte_revision` (révision sur 30 jours d'au moins 10 % en valeur absolue, au franchissement du
  seuil) et `grosse_surprise` (écart d'au moins 20 % sur un nouveau trimestre), seulement pour les sociétés
  suivies par au moins 3 analystes pour les deux derniers.

## 6. Rythme

- Quotidien (22 h 30 UTC, en semaine) : nouveaux 8-K, communiqués en attente, analystes de toutes les sociétés.
- Samedi (assemblage de la révision complète) : tout est recalculé (analystes, communiqués en attente, note).
- Analyse à la demande : analystes lus en direct ; guidance reprise de l'agent entreprises si la société est
  suivie, sinon « non analysée ».
