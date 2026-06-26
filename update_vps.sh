#!/usr/bin/env bash
# update_vps.sh — met a jour le VPS depuis GitHub et relance les services.
#
# Perimetre SUR : lecture seule / paper. N'execute AUCUN ordre, n'expose aucun
# secret. A lancer DEPUIS le dossier du depot sur le VPS :
#   cd ~/bitget_termux_repo && bash update_vps.sh
#
# Etapes : pull -> dependances (numpy inclus) -> tests + securite (GATE) ->
# redemarrage des services systemd s'ils existent. Idempotent.

set -uo pipefail

echo "=== MISE A JOUR VPS — bitget_termux (paper / lecture seule) ==="
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
echo "Depot   : $(pwd)"
echo "Branche : $BRANCH"
echo

# 1. Recuperer le code (fast-forward de la branche courante)
echo "[1/5] git pull..."
if ! git pull --ff-only origin "$BRANCH"; then
  echo "  ECHEC du pull (conflit local ou reseau). Resoudre puis relancer."
  echo "  Astuce : 'git status' ; en cas de modifs locales non voulues : 'git stash'."
  exit 1
fi
echo

# 2. Dependances Python (numpy est requis par les agents quantitatifs)
echo "[2/5] Dependances (pip)..."
if python -c "import sys; sys.exit(0)" 2>/dev/null; then
  python -m pip install -r requirements.txt 2>/dev/null \
    || pip install -r requirements.txt 2>/dev/null \
    || echo "  (pip indisponible — installer numpy/requests/python-dotenv manuellement)"
fi
python -c "import numpy, requests, dotenv" 2>/dev/null \
  && echo "  OK: numpy + requests + python-dotenv importables." \
  || echo "  ATTENTION: une dependance manque -> certains agents resteront neutres."
echo

# 3. Tests d'integrite
echo "[3/5] Tests..."
TESTS_LINE="$(python tests_audit.py 2>/dev/null | tail -1)"
echo "  ${TESTS_LINE:-(tests indisponibles)}"
echo

# 4. GATE securite : on NE redemarre PAS si le verdict n'est pas SAFE
echo "[4/5] Securite (gate)..."
if python security_agent.py 2>/dev/null | grep -q 'VERDICT: SAFE'; then
  echo "  VERDICT: SAFE"
else
  echo "  VERDICT NON-SAFE ou indisponible -> redemarrage ANNULE par securite."
  echo "  Verifier : python security_agent.py"
  exit 2
fi
echo

# 5. Redemarrage des services systemd (s'ils existent)
echo "[5/5] Redemarrage des services..."
restarted=0
if command -v systemctl >/dev/null 2>&1; then
  for svc in bitget-dashboard bitget-bot; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^${svc}.service"; then
      sudo systemctl restart "$svc" && echo "  redemarre: $svc" && restarted=1
    fi
  done
fi
if [ "$restarted" -eq 0 ]; then
  echo "  Aucun service systemd detecte. Lancement manuel possible :"
  echo "    python dashboard/server.py        # dashboard lecture seule (127.0.0.1:8787)"
  echo "    python telegram_command_bot.py    # bot Telegram (lecture seule)"
  echo "  (ou 'bash restart_agent.sh' pour la boucle de signaux agent_loop.py)"
fi
echo

echo "=== Mise a jour terminee. Aucun ordre reel. Mode paper / dry-run. ==="
echo "Etat des services : sudo systemctl status bitget-dashboard bitget-bot"
