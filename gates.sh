#!/usr/bin/env bash
# gates.sh — LES 3 PORTES avant tout push, avec codes de sortie STRICTS.
# Usage : bash gates.sh && git add ... && git commit ... && git push ...
#
# Né de deux incidents (03/07) où un push est parti avec un test rouge :
#   1. `python tests_audit.py | tail -1 && git ...` — le code de sortie du pipe
#      est celui de tail (0), pas celui des tests ;
#   2. un heredoc suivi d'un SAUT DE LIGNE sortait `git commit` de la chaîne &&.
# Ici chaque porte est vérifiée explicitement ; la moindre rouge -> exit 1.
set -uo pipefail

echo "— porte 1/3 : tests_audit —"
python tests_audit.py | tail -1 || { echo "❌ tests rouges"; exit 1; }

echo "— porte 2/3 : security_agent —"
out=$(python security_agent.py) || { echo "❌ security_agent en erreur"; exit 1; }
echo "$out" | grep "VERDICT:" | tail -1
echo "$out" | grep -q "VERDICT: SAFE" || { echo "❌ VERDICT non SAFE"; exit 1; }

echo "— porte 3/3 : safe_push_check —"
bash safe_push_check.sh | tail -1 || { echo "❌ safe_push_check rouge"; exit 1; }

echo "=== 3 PORTES VERTES ==="
