# Agent géopolitique : méthode et règles de conduite

Code : `agent.py` (étapes), `sources.py`, `evenements.py` (regroupement, sans IA), `ia.py` (Gemini, quotas, contrôle des sources), `score.py`. Réglages : `config.json`.

## 1. Sources (toutes gratuites)

| Source | Usage | Rythme |
|---|---|---|
| GDELT, API DOC 2.0 | **source secondaire** : les adresses de GitHub, partagées, reçoivent presque toujours HTTP 429. Une seule requête groupée par exécution, un seul essai. Son échec est affiché pour information dans l'écran Santé et ne rend pas l'agent dégradé | chaque heure |
| Google Actualités (RSS) | recherches par thème (sanctions, droits de douane, conflits, élections), en anglais et en français. Le domaine retenu est celui du site d'origine (balise `source`), pas celui de Google | chaque heure |
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

### Santé de l'agent

L'agent est **OK** tant que deux conditions sont remplies :
- les fichiers d'événements GDELT répondent ;
- au moins 5 autres sources répondent (`sante.sources_min`), hors sources secondaires.

Une source isolée en échec (un flux RSS en 404, par exemple) est affichée, compensée par les autres. L'agent est aussi dégradé si Gemini ne répond pas, pour une autre raison que les quotas.

## 2. Événements

- Un article est retenu s'il relève d'une catégorie (mots-clés de `config.json`). Les pays sont reconnus par leurs noms, en anglais et en français. Les sigles (US, UK, EU…) ne comptent qu'en majuscules.
- Les articles sont regroupés par événement : pays communs, moins de 48 h d'écart et mots significatifs partagés. Les noms de pays ne comptent pas comme mots significatifs : ils sont représentés par leur code (« Iranian » et « Iran » → IR). Les titres de GDELT sont nettoyés (« U . S . » → « U.S. »).
- **Doublons** : à chaque exécution, deux événements sont fusionnés s'ils remplissent trois conditions :
  - leurs couvertures sont à moins de 48 h ;
  - ils ont les mêmes pays principaux ;
  - leurs mots-clés sont proches. Les mots-clés sont les mots présents dans au moins 40 % des titres. Il faut 3 mots en commun et 35 %, ou 2 mots et 50 % si la catégorie ou les pays principaux sont les mêmes.

  Un article qui mélange deux sujets (« US strikes Iranian island ahead of midterm elections ») ne suffit donc pas à relier les frappes et les élections. Gemini peut aussi confirmer qu'un événement du lot est le même qu'un autre (« meme_que ») : ils sont fusionnés.
- **Lieux** : le pays qui accueille une négociation, un sommet ou une réunion est affiché à part, comme « lieu », et n'est pas un pays principal. Exemple : pourparlers sur l'Ukraine à Abou Dabi → pays principaux Ukraine, Russie (et États-Unis s'ils participent), lieu Émirats.
  - Avec Gemini, ce sont ses champs « pays » et « lieux ».
  - Sans IA, des motifs simples : « talks … in Abu Dhabi », « pourparlers à Abou Dabi », « Abu Dhabi talks », « X hosts ».
  - Un pays seulement commentateur (« …, Germany's Merz says ») n'est pas retenu.
- **Thèmes en cours** (`themes`) : sur 7 jours glissants, les événements sont regroupés en un seul élément publié, avec la chronologie des faits, s'ils remplissent trois conditions :
  - mêmes pays principaux (ou l'un contient l'autre, avec 2 pays communs) ;
  - même famille de catégories (conflit, routes maritimes et coups d'État forment la famille « sécurité ») ;
  - au moins un mot-clé commun.

  Gemini confirme chaque regroupement : il écarte les événements hors sujet et rédige un titre de thème en français. Sans Gemini, le regroupement par règles est publié et signalé comme tel. Les pays d'un thème sont ceux qui sont principaux dans au moins la moitié de ses faits.
- **Pays principaux** (affichés et comptés dans le score) : seuls les pays acteurs ou directement touchés sont retenus. Ce sont les pays cités dans le titre de référence ou dans le résumé, ou présents dans plus de la moitié des articles. Un pays cité une fois parmi d'autres n'est pas retenu.
- **Titre affiché** : Gemini rédige un titre en français, factuel, de 12 mots au plus. Il est refusé s'il n'est pas en français ou n'est pas sobre.
- **Titre de référence**, utilisé sans IA : la source officielle s'il y en a une, sinon l'article le plus repris. En cas d'égalité, c'est le plus centré sur l'événement. Il porte sa langue et la mention « non traduit » s'il n'est pas en français.
- **Formats exclus du titre de référence** (`titres_exclus`) : galeries photo, directs, pages « ce qu'il faut savoir » (« In Pictures », « Live », « What to know », « En direct »…).
- **Publication** : un événement sans pays rattaché n'est pas publié dans l'appli. Seule exception : Gemini lui donne une portée mondiale explicite, et il est alors affiché « Monde ».
- Les événements sont gardés 30 jours dans `data/geopolitique/etat.json`.
- **Sources indépendantes** : domaines distincts. Une dépêche reprise mot pour mot sur plusieurs sites (syndication AP, NPR…) ne compte qu'une fois.
- **Événement significatif** : score de sélection ≥ 6, avec au moins 3 sources indépendantes ou une source officielle. Le score de sélection est calculé ainsi :
  - 2 × log2(1 + sources indépendantes) ;
  - + 3 pour une source officielle de sanction, de commerce, de conflit, de coup d'État ou de route maritime (+ 1 pour un communiqué protocolaire) ;
  - + 1,5 par pays suivi (au plus 3 pays) ;
  - + 1 si l'événement est couvert par GDELT.

## 3. Analyse par Gemini

- **Modèles** : chaîne `gemini.modeles`. Par défaut :
  - `gemini-flash-latest` (alias du modèle Flash le plus récent) ;
  - puis `gemini-3.5-flash-lite` ;
  - puis `gemini-3.6-flash` (génération Flash précédente).

  Clé : secret `GEMINI_API_KEY`. Sur une erreur 5xx (dont 503, modèle surchargé) ou une erreur réseau, l'agent fait 3 essais, après 5 puis 15 s d'attente. Il passe ensuite au modèle suivant, qui est aussi utilisé pour le reste de l'exécution. Un 400 ou un 404 (modèle inconnu) fait passer directement au modèle suivant.
- **Priorité** : les événements de gravité estimée 3 ou plus sont analysés en premier.
- **Contrôle de la gravité** (`controle_gravite`, gravite.py). Après l'analyse, la gravité est recalculée par règles à partir des repères :
  - le type d'événement donne la base ;
  - le niveau 3 exige un marqueur de tension notable (frappes, morts, sanctions visant un pays, droits de douane sur un pays…) ;
  - le niveau 4 exige un marqueur de conflit armé, de sanctions majeures ou de rupture commerciale, ET un effet direct sur un marché (pétrole, gaz, détroit, semi-conducteurs…) ;
  - un cran de moins si aucun pays suivi n'est concerné et qu'il n'y a pas d'effet sur un marché.

  La gravité de Gemini peut abaisser ce niveau, mais ne le relève que d'un cran. Sans IA, c'est le niveau des règles, 3 au plus. Les marqueurs sont recherchés dans le titre de référence, le titre français et le résumé, pas dans tous les articles.
- **Distribution cible** sur 24 h : la majorité en 1-2, au plus 35 % en 3 et 15 % en 4 (au moins 2 et 1 permis). Au-delà, les moins étayés (niveau des règles, sources indépendantes) descendent d'un cran, avec une note.
- **Repères de gravité** (`gravite.reperes`, donnés à Gemini) :
  - 1 = déclaration ou procédure de routine ;
  - 2 = mesure ciblée ;
  - 3 = mesure importante ou tension notable ;
  - 4 = conflit armé, sanctions majeures, rupture commerciale ;
  - 5 = choc systémique.

  **Plafonds** (`gravite.plafonds`), appliqués après la réponse : une élection est au plus en 3. L'exception joue si les titres des sources ou le résumé mentionnent une contestation, une fraude, des violences ou une annulation.
- **Langue** : tous les titres et résumés sont en français, avec les accents.
  - Une affirmation en anglais, ou en français sans aucun accent (6 mots ou plus), est supprimée.
  - Un événement dont l'analyse est refusée est retenté 3 fois au plus.
  - Les titres d'origine restés en langue étrangère sont traduits par Gemini (un appel pour 40 titres au plus, mis en cache). La mention « non traduit » ne reste que si Gemini est indisponible.
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
- **Gravité 4 ou 5** : seulement si au moins 2 sources indépendantes sont citées.
- **Version de la méthode** : quand la méthode de regroupement change (`VERSION_REGROUPEMENT`), les événements sont refaits une fois à partir de leurs articles. Sinon, elle est plafonnée à 3, et le plafonnement est indiqué.
- **Sans Gemini** (clé absente, quota atteint, panne) : l'agent publie les événements sans IA. Chacun garde son titre d'origine, non traduit, avec sa langue et la mention « non analysé ». S'y ajoutent les sources, la tonalité GDELT des pays concernés et une gravité estimée par règles (au plus 3). L'appli et la synthèse le signalent.

### Quotas gratuits

Chaque modèle a son propre quota gratuit, par projet. Il est remis à zéro à minuit, heure du Pacifique. Google ne publie plus ces limites en chiffres : elles se lisent dans AI Studio, connecté, sur https://aistudio.google.com/rate-limit (vérifié le 03/11/2026). Les valeurs de `gemini.modeles` (`rpm`, `rpd`) sont les dernières valeurs publiques connues :

| Modèle | rpm | rpd | Effectif (marge de 20 %) |
|---|---|---|---|
| gemini-flash-latest | 10 | 250 | 8 par minute, 200 par jour |
| gemini-3.5-flash-lite | 15 | 1 000 | 12 par minute, 800 par jour |
| gemini-3.6-flash | 10 | 250 | 8 par minute, 200 par jour |

**À confirmer dans AI Studio**, puis à corriger dans `config.json` si besoin. L'agent s'adapte aussi seul aux réponses 429 :
- **quota par minute** (message « per minute » ou `retryDelay`) : il attend le délai indiqué (60 s au plus), puis fait un nouvel essai ;
- **quota du jour**, ou 429 répété : plus d'appel à ce modèle jusqu'au lendemain (jour du Pacifique), et passage au modèle suivant. Si le message indique le quota du jour, le nombre d'appels réussis est retenu comme limite, puis la marge de 20 % s'applique les jours suivants.

Autres garde-fous :
- au plus 10 appels par exécution, et pas plus que la part du reste du jour qui revient à l'exécution : le budget couvre toute la journée ;
- au moins 60 s ÷ rpm effectif entre deux appels à un même modèle ;
- 3 événements par appel ;
- cache : un événement n'est réanalysé qu'après 24 h et s'il a doublé de sources.

Les tests (`tests/test_agent.py`, classe `TestQuotasJournee`) simulent trois situations :
- 48 exécutions horaires ;
- une journée avec 12 lancements manuels en plus ;
- un modèle dont la vraie limite est plus basse que la configuration.

Ils vérifient :
- les plafonds par modèle, par jour du Pacifique, par minute et par exécution ;
- la répartition des appels sur la journée ;
- l'apprentissage de la limite après un 429.

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
