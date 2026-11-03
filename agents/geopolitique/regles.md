# Agent géopolitique : méthode et règles de conduite

Code : `agent.py` (étapes), `sources.py`, `evenements.py` (regroupement, sans IA), `ia.py` (Gemini, quotas, contrôle des sources), `score.py`. Réglages : `config.json`.

## 1. Sources (toutes gratuites)

| Source | Usage | Rythme |
|---|---|---|
| GDELT, API DOC 2.0 | articles par thème : sanctions, droits de douane, conflits, élections, coups d'État, routes maritimes | chaque heure (une requête toutes les 6 s) |
| GDELT 2.0, fichiers d'événements (15 min) | événements géolocalisés : tonalité, volume, part des conflits par pays | chaque heure (les 4 derniers fichiers) |
| Federal Register (API) | décrets et proclamations présidentiels ; mesures de l'OFAC, du BIS et de l'USTR | chaque heure |
| OFAC, « Recent Actions » | sanctions américaines | chaque heure |
| Conseil de l'UE (RSS) | communiqués, dont les sanctions de l'UE (catégorie « Sanctions ») | chaque heure |
| Maison-Blanche, Élysée, Commission européenne (RSS) | communiqués officiels | chaque heure |
| BRI (RSS) | discours des banquiers centraux, retenus seulement s'ils traitent de géopolitique, de commerce ou de sanctions | chaque heure |
| Presse (RSS) | France 24 (dépêches AFP), BBC, Le Monde, Financial Times, The Guardian, Deutsche Welle, Al Jazeera | chaque heure |
| Caldara et Iacoviello | indice quotidien de risque géopolitique (GPR) | une fois par jour |
| FRED (USEPUINDXD) | incertitude de politique économique, États-Unis | une fois par jour |

Absentes, et indiquées « non configurée » dans l'écran Santé : Reuters et AP (plus de flux RSS public ; leurs articles arrivent par GDELT), le ministère chinois du Commerce (pas de flux public ; ses annonces arrivent par la presse). L'API GEO 2.0 de GDELT ne répond plus (404) : la géolocalisation vient des fichiers d'événements. Pas de réseaux sociaux : les déclarations des dirigeants sont captées par la presse et les communiqués officiels.

## 2. Événements

- Un article est retenu s'il relève d'une catégorie (mots-clés de `config.json`). Les pays sont reconnus par leurs noms, en anglais et en français. Les sigles (US, UK, EU…) ne comptent qu'en majuscules.
- Les articles sont regroupés par événement : pays communs, moins de 48 h d'écart et mots significatifs partagés. Les événements sont gardés 30 jours dans `data/geopolitique/etat.json`.
- **Sources indépendantes** : domaines distincts. Une dépêche reprise mot pour mot sur plusieurs sites (syndication AP, NPR…) ne compte qu'une fois.
- **Événement significatif** : score de sélection ≥ 6, avec au moins 3 sources indépendantes ou une source officielle. Le score de sélection est calculé ainsi :
  - 2 × log2(1 + sources indépendantes) ;
  - + 3 pour une source officielle de sanction, de commerce, de conflit, de coup d'État ou de route maritime (+ 1 pour un communiqué protocolaire) ;
  - + 1,5 par pays suivi (au plus 3 pays) ;
  - + 1 si l'événement est couvert par GDELT.

## 3. Analyse par Gemini

- Modèle : `gemini.modele`. Par défaut, `gemini-flash-latest`, l'alias du modèle Flash le plus récent. Clé : secret `GEMINI_API_KEY`.
- Pour chaque événement significatif, l'agent produit :
  - un résumé factuel en 2 phrases ;
  - les pays et la catégorie ;
  - la gravité (de 1 à 5) ;
  - les actifs et secteurs touchés, avec le sens probable de l'impact (hausse, baisse, incertain) ;
  - l'horizon (jours, semaines, mois) et la confiance ;
  - la rubrique « Ce qui pourrait me donner tort ».
- **Anti-hallucination** :
  - Gemini ne reçoit que les sources numérotées de l'événement (S1, S2…), avec leur URL ;
  - chaque affirmation doit citer au moins une de ces sources, sinon elle est supprimée ;
  - un actif hors de la liste, un pays ou une catégorie inconnus sont écartés ;
  - un événement sans résumé sourcé reste en version sans IA.
- **Gravité 4 ou 5** : seulement si au moins 2 sources indépendantes sont citées. Sinon, elle est plafonnée à 3, et le plafonnement est indiqué.
- **Sans Gemini** (clé absente, quota atteint, panne) : l'agent publie les événements sans IA, avec les titres des sources, la tonalité GDELT des pays concernés et une gravité estimée par règles (au plus 3). L'appli et la synthèse le signalent.

### Quotas gratuits

Google ne publie plus les quotas gratuits en chiffres : ils se consultent dans AI Studio, par projet. Ils se remettent à zéro à minuit, heure du Pacifique. Valeurs prudentes par défaut :

| Réglage | Valeur | Effet |
|---|---|---|
| `quota_jour` | 20 | appels au plus par jour du Pacifique, comptés d'une exécution à l'autre |
| `appels_max_par_execution` | 2 | et pas plus que (reste du jour ÷ exécutions horaires restantes), arrondi au-dessus : le budget couvre toute la journée |
| `quota_minute`, `intervalle_min_secondes` | 10, 7 s | au plus 10 appels par minute, 7 s entre deux appels |
| `evenements_par_appel` | 3 | jusqu'à 60 événements analysés par jour |
| cache | 24 h et sources × 2 | un événement analysé n'est repris que s'il a doublé de sources, et pas avant 24 h |

Une réponse 429 suspend les appels pendant une heure. Les tests (`tests/test_agent.py`, classe `TestQuotasJournee`) simulent 48 exécutions horaires, puis une journée avec 12 lancements manuels en plus, avec toujours plus d'événements que le quota n'en permet. Ils vérifient :
- le plafond par jour du Pacifique ;
- le plafond par exécution ;
- le plafond par minute ;
- l'intervalle entre deux appels ;
- la répartition des appels sur toute la journée.

## 4. Score de risque géopolitique (/100, par pays suivi)

Plus le score est haut, plus le risque est élevé. Il pondère trois composantes. Une composante indisponible est exclue, et les autres sont repondérées.

| Composante | Poids | Calcul |
|---|---|---|
| Événements | 0,5 | 100 × (1 − exp(−S / 25)), S = Σ gravité² × 0,5^(âge en jours / 3), événements significatifs des 14 derniers jours qui concernent le pays |
| Tonalité GDELT | 0,3 | événements dont l'action a lieu dans le pays, 48 dernières heures : moitié tonalité moyenne (−1 → 0, −8 → 100), moitié part des conflits (10 % → 0, 50 % → 100) |
| Tendance | 0,2 | conflits par fichier GDELT, moyenne des 7 derniers jours rapportée à celle des 30 derniers (rapport 1 → 50, 2 → 100) ; au moins 10 jours de données |

Niveaux : élevé à partir de 60, modéré de 35 à 59, faible en dessous de 35. La variation sur 7 jours compare le score à celui d'il y a 7 jours (historique dans l'état de l'agent).

## 5. Signaux (`data/signaux/geopolitique.json`)

Les signaux sont destinés au chef d'orchestre et au futur agent risque. Il y en a trois sortes :
- `evenement_grave` : nouvel événement de gravité 4 ou plus ;
- `hausse_score` : score d'un pays en hausse d'au moins 10 points sur 7 jours (au plus une fois par jour et par pays) ;
- `mesure_officielle` : sanction ou mesure commerciale d'une source officielle qui touche un pays suivi.

Chaque signal n'est émis qu'une fois.

## 6. Règles de conduite

- **Ton** : froid et factuel. Pas de superlatifs ni de dramatisation. Les mots interdits sont communs aux agents, avec en plus « catastrophe », « chaos », « sans précédent », « panique »… Une affirmation non conforme est supprimée.
- **Faits et interprétations** : le résumé contient les faits ; les impacts sur les marchés sont des interprétations. L'appli les présente sous des rubriques séparées.
- **Sources** : chaque affirmation renvoie à au moins une source cliquable.

## 7. Rythme et fichiers

- Toutes les heures (minute 3), via le planificateur, avec les plannings GitHub en secours. À 6 h 03 UTC, le mode « quotidien » écrit aussi la synthèse `data/recap/geopolitique-AAAA-MM-JJ.md`. Si l'exécution de 6 h manque, la première exécution suivante écrit la synthèse.
- Sorties :
  - `data/geopolitique.json` : appli ;
  - `data/historique/geopolitique/AAAA-MM-JJ.json` : scores et événements du jour ;
  - `data/geopolitique/etat.json` : événements suivis, cache des analyses, compteur de quota, agrégats GDELT ;
  - `data/journal/agent-geopolitique.json` : santé et appels à Gemini.
