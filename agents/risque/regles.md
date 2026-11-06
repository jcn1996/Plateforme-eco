# Agent risque — méthode et règles de conduite

## Rôle

1. Mesurer le **stress financier mondial** (score /100 et palier) et le **risque par pays** (score /100).
2. Jouer le **contradicteur** des signaux des autres agents : chercher les données qui les contredisent
   ou les nuancent, et proposer un ajustement de confiance.

## Sources (gratuites, croisées quand c'est possible)

| Famille | Indicateur | Source principale | Vérification |
|---|---|---|---|
| Volatilité | VIX | Yahoo Finance `^VIX` | FRED `VIXCLS` (même date) |
| Volatilité | VSTOXX | Yahoo Finance `^V2TX` (facultatif, souvent absent) | — |
| Volatilité | MOVE | Yahoo Finance `^MOVE` | — |
| Crédit | High yield américain | FRED `BAMLH0A0HYM2` | — |
| Crédit | Investment grade américain | FRED `BAMLC0A0CM` | — |
| Crédit | High yield européen | FRED `BAMLHE00EHYIOAS` | — |
| Stress | STLFSI4, NFCI (hebdomadaires) | FRED | — |
| Stress | CISS (zone euro) | BCE Data Portal | — |
| Souverain | Italie − Allemagne à 10 ans | OCDE via FRED (mensuel) | BCE, IRS (mensuel) |
| Devises | Indice dollar, variation sur 3 mois | Yahoo Finance `DX-Y.NYB` | FRED `DTWEXBGS` |

Par pays : ETF et devise suivis par l'agent pays (Yahoo Finance), taux à 10 ans (OCDE via FRED,
BCE pour la zone euro), dette publique / PIB, solde courant et inflation (FMI ; inflation de
l'agent pays en priorité), réserves en mois d'importations (Banque mondiale), score géopolitique
(`data/geopolitique.json`).

Corrélations sur 3 et 12 mois des rendements quotidiens : actions (ACWI), obligations (TLT), or (GLD), dollar (DXY).

Les écarts de crédit ICE BofA ne sont publiés par FRED que sur environ 3 ans : leur percentile porte
sur cette période (l'appli et le récapitulatif indiquent la profondeur d'historique de chaque indicateur).

## Score mondial et paliers

- Score d'un indicateur = son percentile dans sa distribution historique (jusqu'à 10 ans).
- Score mondial = moyenne pondérée (pondérations dans `config.json`), ramenée aux indicateurs disponibles.
- Seuils des paliers « Vigilance », « Tension », « Crise » : percentiles 60, 85 et 97 du score
  mondial recalculé chaque semaine sur 10 ans (au moins 5 ans d'historique), sinon seuils fixes.
- **Deux signaux concordants minimum pour changer de palier** : au moins deux familles
  d'indicateurs doivent être elles-mêmes au niveau du nouveau palier. Sinon, le palier est
  conservé et le changement est affiché « en attente ».
- L'appli affiche le palier précédent, la date du changement et les trois indicateurs qui pèsent le plus
  (poids × écart du percentile à 50).

## Score par pays

Cinq composantes notées de 0 (risque faible) à 100 (risque élevé) entre deux bornes de la config :
marché (25 %), devise (20 %), souverain (20 %), vulnérabilité macro (20 %), géopolitique (15 %).
Une composante absente est retirée de la moyenne ; il en faut au moins deux. Variation sur 7 jours
d'après l'historique de l'agent. Texte de deux phrases, factuel : composante la plus haute, puis la plus basse.

## Signaux (`data/signaux/risque.json`)

- `changement_de_palier` (forte) ;
- `ecart_credit_hausse` : hausse de plus de 0,75 pt en 20 séances (1,5 pt : forte ; seuils divisés par deux pour l'investment grade) ;
- `devise_decrochage` : −10 % sur 3 mois ou −6 % sur 1 mois contre le dollar ;
- `rupture_correlation` : écart d'au moins 0,6 entre corrélations à 3 et 12 mois, ou corrélation actions / obligations
  qui devient positive (≥ 0,3) alors qu'elle était négative sur 12 mois.

## Contradicteur (`data/signaux/revues.json`)

Chaque signal d'importance moyenne ou forte des 7 derniers jours est revu une fois :
- faits numérotés (F1, F2…), chacun avec sa source ; l'objection cite ses faits ;
- ajustement proposé : « maintenir », « abaisser » ou « signal fragile ».

Règles :
- géopolitique : une seule source → « signal fragile » ; VIX en hausse de moins de 2 pts et ETF des pays
  concernés en baisse de moins de 2 % depuis la veille du signal → « abaisser » (le marché ne confirme pas) ;
- macro (changement de phase) : deux changements ou plus en 30 jours → « signal fragile » ; ralentissement
  annoncé alors que le palier est « Calme » et que le high yield ne monte pas → « abaisser » ; pente de
  l'indicateur avancé inférieure à 0,1 pt sur 3 mois → « abaisser » ;
- entreprises (nouvelle pépite) : momentum sur 12 mois inférieur à −20 %, palier « Tension » ou « Crise »,
  ou pays de l'entreprise à risque élevé → « abaisser » ;
- autres : contexte de risque, « maintenir ».

Gemini (facultatif, secret `GEMINI_API_KEY`) rédige l'objection à partir des mêmes faits, avec un budget
d'appels propre à l'agent risque (`gemini` dans `config.json`, compté dans `data/risque/etat.json`,
séparé de celui de l'agent géopolitique). Une réponse rejetée (chiffre absent des faits, aucun fait cité,
ajustement inconnu) est remplacée par la version par règles.

## Règles de conduite

- Ton froid et factuel, sans alarmisme.
- Niveau de confiance (indicateurs disponibles, sources divergentes, familles discordantes, changement en attente).
- Rubrique « Ce qui pourrait me donner tort ».
- Faits et interprétations séparés (`faits`, `interpretations`).
- Deux signaux concordants minimum pour changer de palier.
