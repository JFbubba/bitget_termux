#!/usr/bin/env python3
"""
scan_paper.py — un cycle de monitoring PAPER, sans la moindre action reelle.

= les etapes de agent_control.COMMANDS (SOURCE DE VERITE) SANS l'accumulation
(qui passe par le chemin d'achat spot BTC REEL quand le double verrou est arme),
mais avec un lanceur PROPRE, robuste pour l'execution non surveillee (systemd) :

  - RESILIENT : un echec isole n'arrete pas le cycle (on journalise et on continue).
  - TIMEOUT par etape : une etape bloquee est tuee (pas de hang infini).
  - sortie 0 tant que le cycle a tourne (systemd reste vert) ; detail dans les logs.

L'accumulation reelle reste pilotee par sa tache dediee (cron quotidien), inchangee.
Concu pour systemd (bitget-scan.timer). Aucun ordre, aucun verrou leve. SAFE.
"""
import subprocess
from datetime import datetime

import agent_control as ac

SKIP = (
    "accumulation_engine",    # chemin d'achat REEL -> pilote a part (cron quotidien)
    "telegram_notifier",      # notifications -> timer dedie bitget-notify (espacees)
    "brain_cycle",            # cerveau -> timer dedie bitget-brain (1 min PRECISE, §63)
)
STEP_TIMEOUT = 90              # s max par etape (une etape bloquee est tuee)


def run_step(name, command):
    print("\n" + "=" * 70)
    print(name)
    print(f"Heure: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=STEP_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT (>{STEP_TIMEOUT}s) — etape tuee, on continue.")
        return 124
    if r.stdout:
        print(r.stdout)
    if r.stderr:
        print("ERREUR:\n" + r.stderr)
    return r.returncode


def main():
    if ac.PAUSE_FILE.exists():
        print("⏸ Agent en pause: scan paper non execute.")
        return 0
    ok, failed = 0, []
    for item in ac.COMMANDS:
        cmd = " ".join(item["command"])
        if any(s in cmd for s in SKIP):
            print(f"(saute: {item['name']} — pilote hors du scan)")
            continue
        if run_step(item["name"], item["command"]) == 0:
            ok += 1
        else:
            failed.append(item["command"][1] if len(item["command"]) > 1 else cmd)
    print("\n" + "=" * 70)
    summary = f"Cycle PAPER termine. {ok} etapes OK"
    if failed:
        summary += f", echecs non bloquants: {', '.join(failed)}"
    summary += ". Aucun ordre, aucune accumulation reelle."
    print(summary)
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
