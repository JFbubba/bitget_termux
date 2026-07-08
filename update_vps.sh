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

# 2. Dependances Python (numpy requis par les agents quantitatifs)
#    Ubuntu 24.04 bloque pip system-wide (PEP 668 « externally-managed-environment »).
#    Strategie : si deja importables -> rien ; sinon APT (propre), puis pip, puis
#    pip --break-system-packages en dernier recours.
echo "[2/5] Dependances..."
if python -c "import numpy, requests, dotenv" 2>/dev/null; then
  echo "  OK: numpy + requests + python-dotenv deja presents (rien a installer)."
else
  echo "  Installation des dependances manquantes..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y python3-numpy python3-requests python3-dotenv 2>/dev/null || true
  fi
  if ! python -c "import numpy, requests, dotenv" 2>/dev/null; then
    # deps-syst-ok : dernier recours seulement si import KO ; requirements borne numpy<2 (ERR-004)
    python -m pip install -r requirements.txt 2>/dev/null \
      || python -m pip install --break-system-packages -r requirements.txt 2>/dev/null \
      || true
  fi
  python -c "import numpy, requests, dotenv" 2>/dev/null \
    && echo "  OK: dependances importables." \
    || echo "  ATTENTION: dependance manquante -> certains agents resteront neutres."
fi
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
  for svc in bitget-dashboard bitget-bot bitget-microstructure bitget-stop-guardian; do
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
