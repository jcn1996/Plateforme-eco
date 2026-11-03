#!/usr/bin/env bash
# Commit des fichiers indiqués puis poussée sur main, avec enregistrement du suivi des recommandations
# (python -m agents.entreprises.suivi) sur l'état le plus récent du dépôt, juste avant chaque essai.
# Ce script est le seul chemin d'écriture de data/historique/recommandations.json : deux workflows
# qui poussent en même temps ne peuvent pas entrer en conflit sur ce fichier (le perdant recommence).
#   usage : outils/pousser_avec_suivi.sh "message de commit" chemin [chemin…]
set -u
message="$1"; shift
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -- "$@"
git restore --staged data/historique/recommandations.json 2>/dev/null || true
if ! git diff --cached --quiet; then git commit -q -m "$message"; fi
git checkout -q -- data/historique/recommandations.json 2>/dev/null || true
for essai in 1 2 3 4; do
  if ! git pull -q --rebase --autostash origin main; then
    git rebase --abort 2>/dev/null
    echo "Conflit lors de la mise à jour depuis main."
    exit 1
  fi
  suivi=0
  if python -m agents.entreprises.suivi; then
    git add data/historique/recommandations.json
    if ! git diff --cached --quiet; then
      git commit -q -m "Recommandations : suivi du $(date -u +%d/%m/%Y)"
      suivi=1
    fi
  else
    echo "Suivi des recommandations en échec : poussée sans suivi (nouvelle tentative au prochain passage)."
    git checkout -q -- data/historique/recommandations.json 2>/dev/null || true
  fi
  if git push -q origin HEAD:main; then exit 0; fi
  # Poussée refusée (un autre workflow vient de pousser) : le suivi sera recalculé sur le nouvel état
  if [ "$suivi" = 1 ]; then git reset -q --hard HEAD~1; fi
  sleep $((essai * 5))
done
exit 1
