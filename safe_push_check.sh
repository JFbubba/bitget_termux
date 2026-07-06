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

echo "[3/5] Recherche de secrets REELS (valeurs en dur)"
# Objectif : bloquer une vraie cle / un vrai token committe par accident.
# On AUTORISE explicitement :
#   - les references aux variables d'environnement : os.getenv("X"), os.environ[...]
#   - les listes de noms de variables (check_env.py)
#   - la documentation qui cite les noms (CLAUDE_BRIEF.md, README, ...)
# On ne bloque QUE des VALEURS de secret reellement presentes :
#   - token Telegram          : 123456789:AA....(35 car.)
#   - cle API Bitget          : bg_xxxxxxxx...
#   - assignation en dur       : SECRET = "valeur_longue"
#   - ligne style .env collee  : BITGET_API_SECRET=<valeur_collee>
SECRET_HITS=$(
  git grep -nIiE \
    -e '[0-9]{8,10}:[A-Za-z0-9_-]{35}' \
    -e 'bg_[0-9a-f]{20,}' \
    -e '(BITGET_API_KEY|BITGET_API_SECRET|BITGET_API_PASSPHRASE|TELEGRAM_BOT_TOKEN)=[A-Za-z0-9._:/+-]{12,}' \
    -e '(api[_-]?key|api[_-]?secret|secret[_-]?key|passphrase|bot[_-]?token|access[_-]?token|private[_-]?key)[[:space:]]*[:=][[:space:]]*["'\''][^"'\'' ]{12,}["'\'']' \
    -- . ':!*.lock' ':!package-lock.json' \
  | grep -ivE 'os\.(getenv|environ)|getenv\(|environ\[' \
  | grep -ivE '(your_|placeholder|example|changeme|dummy|fake_|<[^>]+>|xxxx)' \
  || true
)

if [ -n "$SECRET_HITS" ]; then
  echo "ERREUR: secret potentiel detecte (valeur en dur):"
  echo "$SECRET_HITS"
  exit 1
fi

echo "[4/5] Recherche de fonctions dangereuses (code operationnel)"
# On exclut l'outillage d'audit/securite qui ENUMERE volontairement ces
# mots-cles comme donnees de detection (meme exclusion que FILES_TO_SCAN
# dans security_agent.py). On exclut AUSSI spot_executor.py : c'est le module
# d'execution AUTORISE (achat spot BTC seul), audite a part par security_agent
# (scan_authorized_exec : aucun mot interdit + verrous MANDATE_LIVE/kill_switch).
# On exclut AUSSI futures_executor.py : 2e module d'execution BORNE (futures, §34),
# DRY-RUN a l'etape 1, audite a part par security_agent (scan_futures_exec : interdit dur
# retrait/transfert/levier-hors-mur/vente + verrous double-verrou/edge/kill_switch/confirm).
# Tout le reste du code operationnel reste scanne.
DANGER_HITS=$(
  git grep -nE 'place_order|open_long|open_short|close_position|cancel_order|change_leverage|transfer|withdraw|send_order|create_order|submit_order|set_leverage|market_order|limit_order|order/place|batch-place-order|place-order|close-positions' \
    -- '*.py' \
    ':!security_agent.py' ':!getagent_audit.py' ':!tests_audit.py' ':!spot_executor.py' ':!futures_executor.py' \
    ':!spot_trader.py' ':!margin_trader.py' ':!account_transfers.py' ':!earn_manager.py' ':!liquidity_manager.py' ':!alt_carry.py' ':!trading_status.py' \
  || true
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
