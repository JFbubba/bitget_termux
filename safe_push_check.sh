#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

echo "=== SAFE PUSH CHECK ==="

echo "[1/5] Verification Git status"
git status --short

echo "[2/5] Recherche fichiers interdits suivis par Git"
FORBIDDEN_TRACKED=$(
  git ls-files | grep -E '(^|/)(\.env|.*\.log|.*\.jsonl|.*\.csv|agent_loop\.pid|paper_positions\.json|pending_orders\.json|telegram_offset\.txt)$' || true
)

if [ -n "$FORBIDDEN_TRACKED" ]; then
  echo "ERREUR: fichiers interdits suivis par Git:"
  echo "$FORBIDDEN_TRACKED"
  exit 1
fi

echo "[3/5] Recherche secrets potentiels"
SECRET_HITS=$(
  git grep -n -E 'BITGET_API_SECRET|BITGET_API_PASSPHRASE|TELEGRAM_BOT_TOKEN|x-cg-pro-api-key|PRIVATE_KEY|apiSecret|passphrase' -- . ':!README.md' ':!ROADMAP.md' || true
)

if [ -n "$SECRET_HITS" ]; then
  echo "ERREUR: secret potentiel detecte:"
  echo "$SECRET_HITS"
  exit 1
fi

echo "[4/5] Recherche fonctions dangereuses"
DANGER_HITS=$(
  git grep -n -E 'place_order|open_long|open_short|close_position|cancel_order|change_leverage|transfer|withdraw|send_order|create_order|submit_order|set_leverage|market_order|limit_order|order/place|batch-place-order|place-order|close-positions' -- '*.py' || true
)

if [ -n "$DANGER_HITS" ]; then
  echo "ERREUR: fonction dangereuse detectee:"
  echo "$DANGER_HITS"
  exit 1
fi

echo "[5/5] Tests audit"
python tests_audit.py
python security_agent.py

echo "SAFE PUSH CHECK OK"
