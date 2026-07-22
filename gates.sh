#!/usr/bin/env bash
# gates.sh — LES PORTES avant tout push, avec codes de sortie STRICTS.
# Les 3 portes constitutionnelles (CLAUDE.md §5) + la porte 4 : banc pytest tests/
# (unitaire dev, venv .venv — FAIL-CLOSED si pytest indisponible).
# Usage : bash gates.sh && git add ... && git commit ... && git push ...
#
# Né de deux incidents (03/07) où un push est parti avec un test rouge :
#   1. `python tests_audit.py | tail -1 && git ...` — le code de sortie du pipe
#      est celui de tail (0), pas celui des tests ;
#   2. un heredoc suivi d'un SAUT DE LIGNE sortait `git commit` de la chaîne &&.
# Ici chaque porte est vérifiée explicitement ; la moindre rouge -> exit 1.
set -uo pipefail

echo "— porte 1/4 : tests_audit —"
python tests_audit.py | tail -1 || { echo "❌ tests rouges"; exit 1; }

echo "— porte 2/4 : security_agent —"
out=$(python security_agent.py) || { echo "❌ security_agent en erreur"; exit 1; }
echo "$out" | grep "VERDICT:" | tail -1
echo "$out" | grep -q "VERDICT: SAFE" || { echo "❌ VERDICT non SAFE"; exit 1; }

echo "— porte 3/4 : safe_push_check —"
bash safe_push_check.sh | tail -1 || { echo "❌ safe_push_check rouge"; exit 1; }

echo "— porte 4/4 : pytest (banc unitaire tests/) —"
if [ -x .venv/bin/pytest ]; then
  PYTEST=".venv/bin/pytest"
elif command -v pytest >/dev/null 2>&1; then
  PYTEST="pytest"
else
  # FAIL-CLOSED : une porte qui saute en silence n'est pas une porte.
  echo "❌ pytest introuvable — créer le venv : python3 -m venv --system-site-packages .venv && .venv/bin/pip install pytest"
  exit 1
fi
"$PYTEST" | tail -1 || { echo "❌ pytest rouge"; exit 1; }

echo "=== 4 PORTES VERTES ==="
