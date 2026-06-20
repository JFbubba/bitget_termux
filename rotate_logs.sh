#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# rotate_logs.sh — rotation avancee des journaux append-only.
#
# SAFE : ne touche QUE des journaux/log append-only. Ne touche JAMAIS les
# fichiers d'ETAT lus par le moteur (signals_journal.csv,
# open_outcomes_state.csv, final_outcomes_journal.csv). Aucun ordre, aucun
# trading.
#
# Comportement :
#   - si un journal depasse MAX_KB, il est archive (horodate puis gzip) et vide
#   - on conserve au plus KEEP archives par journal (les plus anciennes purgees)
#
# Config (variables d'environnement, valeurs par defaut) :
#   MAX_KB=512   taille seuil en Ko
#   KEEP=7       nombre d'archives conservees par journal
#
# Usage (Termux) :
#   bash rotate_logs.sh
#   MAX_KB=1024 KEEP=14 bash rotate_logs.sh

MAX_KB="${MAX_KB:-512}"
KEEP="${KEEP:-7}"
ARCHIVE_DIR="logs/archive"

# Journaux append-only uniquement (jamais les .csv d'etat).
LOG_FILES=(
  "agent_loop.log"
  "execution_dry_run_journal.jsonl"
  "preorder_approvals_journal.jsonl"
  "preorder_guard_journal.jsonl"
  "paper_positions_journal.jsonl"
)

mkdir -p "$ARCHIVE_DIR"

have_gzip=0
if command -v gzip >/dev/null 2>&1; then
  have_gzip=1
fi

rotated=0

file_size_kb() {
  du -k "$1" 2>/dev/null | cut -f1 || true
}

prune_archives() {
  base="$1"
  # Garder les KEEP archives les plus recentes, supprimer le reste.
  # shellcheck disable=SC2012
  ls -1t "$ARCHIVE_DIR/$base".* 2>/dev/null \
    | tail -n +"$((KEEP + 1))" \
    | while IFS= read -r old; do
        [ -n "$old" ] || continue
        rm -f "$old"
        echo "Purge archive: $old"
      done || true
}

rotate_one() {
  file="$1"
  base="$(basename "$file")"

  if [ ! -f "$file" ]; then
    return 0
  fi

  size_kb="$(file_size_kb "$file")"
  size_kb="${size_kb:-0}"

  if [ "$size_kb" -gt "$MAX_KB" ]; then
    ts="$(date +"%Y%m%d_%H%M%S")"
    archive="$ARCHIVE_DIR/${base}.${ts}"

    # Garde anti-collision (granularite de la date = 1s).
    n=1
    while [ -e "$archive" ] || [ -e "${archive}.gz" ]; do
      archive="$ARCHIVE_DIR/${base}.${ts}.${n}"
      n=$((n + 1))
    done

    mv "$file" "$archive"
    : > "$file"  # recree immediatement un journal vide

    if [ "$have_gzip" -eq 1 ]; then
      gzip -f "$archive"
      archive="${archive}.gz"
    fi

    echo "Rotated $file (${size_kb} Ko > ${MAX_KB} Ko) -> $archive"
    rotated=$((rotated + 1))
  fi

  prune_archives "$base"
}

echo "=== ROTATE LOGS (MAX_KB=${MAX_KB}, KEEP=${KEEP}) ==="

for f in "${LOG_FILES[@]}"; do
  rotate_one "$f"
done

if [ "$rotated" -eq 0 ]; then
  echo "Aucun journal a tourner (tous sous le seuil)."
else
  echo "Termine. Journaux tournes: ${rotated}."
fi
