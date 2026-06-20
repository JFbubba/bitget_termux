#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

mkdir -p logs/archive

rotate_if_big() {
  file="$1"
  max_kb="${2:-512}"

  if [ -f "$file" ]; then
    size_kb=$(du -k "$file" | cut -f1)
    if [ "$size_kb" -gt "$max_kb" ]; then
      ts=$(date +"%Y%m%d_%H%M%S")
      mv "$file" "logs/archive/${file}.${ts}.bak"
      touch "$file"
      echo "Rotated $file"
    fi
  fi
}

rotate_if_big "agent_loop.log" 512
rotate_if_big "execution_dry_run_journal.jsonl" 512
rotate_if_big "preorder_approvals_journal.jsonl" 512
rotate_if_big "preorder_guard_journal.jsonl" 512
