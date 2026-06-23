#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# restart_agent.sh — arret propre + relance de agent_loop.py.
#
# SAFE : mode paper / dry-run uniquement.
#   - ne declenche AUCUN ordre, ne trade jamais
#   - ne fait que (re)demarrer la boucle de monitoring
#   - complement du watchdog : detection -> relance manuelle controlee
#
# Usage (Termux) :
#   bash restart_agent.sh

PID_FILE="agent_loop.pid"
LOG_FILE="agent_loop.log"
SCRIPT="agent_loop.py"
SELF_PID="$$"

echo "=== RESTART AGENT LOOP (paper / dry-run only) ==="

# Verifie qu'un PID correspond bien a "python ... agent_loop.py".
# Matching PRECIS (pas un simple substring) pour ne JAMAIS tuer un process
# tiers dont la ligne de commande contiendrait juste "agent_loop.py"
# (editeur, grep, pkill, le bot Telegram, ce script lui-meme...).
is_agent_loop() {
  cmdfile="/proc/$1/cmdline"
  [ -r "$cmdfile" ] || return 1

  argv=()
  mapfile -d '' -t argv < "$cmdfile" 2>/dev/null || return 1
  [ "${#argv[@]}" -ge 2 ] || return 1

  case "${argv[0]}" in
    *python*) ;;
    *) return 1 ;;
  esac

  for a in "${argv[@]}"; do
    case "$a" in
      agent_loop.py|*/agent_loop.py) return 0 ;;
    esac
  done
  return 1
}

# Arret propre d'un PID : SIGTERM, attente jusqu'a 10s, puis SIGKILL.
stop_pid() {
  pid="$1"
  [ -z "$pid" ] && return 0
  [ "$pid" = "$SELF_PID" ] && return 0

  if kill -0 "$pid" 2>/dev/null; then
    echo "Arret du process $pid (SIGTERM)..."
    kill -TERM "$pid" 2>/dev/null || true

    for _ in $(seq 1 10); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done

    if kill -0 "$pid" 2>/dev/null; then
      echo "Toujours vivant -> SIGKILL $pid"
      kill -KILL "$pid" 2>/dev/null || true
    fi
  fi
}

# 1. Arret de l'instance referencee par le PID file.
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  stop_pid "$OLD_PID"
fi

# 2. Filet de securite : tout agent_loop.py residuel via /proc (sans pkill).
if [ -d /proc ]; then
  for d in /proc/[0-9]*; do
    p="${d#/proc/}"
    [ "$p" = "$SELF_PID" ] && continue
    if is_agent_loop "$p"; then
      stop_pid "$p"
    fi
  done
fi

# 3. Nettoyer un PID file obsolete.
rm -f "$PID_FILE"

# 4. Relancer en arriere-plan, journalise.
echo "Relance de $SCRIPT en arriere-plan..."
nohup python "$SCRIPT" >> "$LOG_FILE" 2>&1 &
NEW_PID="$!"
echo "$NEW_PID" > "$PID_FILE"

sleep 2

# 5. Verifier que la nouvelle instance tourne.
if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "OK: agent_loop relance (PID $NEW_PID)."
  echo "Logs: $LOG_FILE"
  echo "Verifier l'etat: python watchdog.py"
else
  echo "ERREUR: la nouvelle instance ne tourne pas. Voir $LOG_FILE."
  exit 1
fi

echo "Restart termine. Aucun ordre reel. Mode paper / dry-run."
