"""agent_loop.py — LEGACY (SUPERSEDED, revue backlog 19/07). Ancienne boucle persistante (PID file +
subprocess) de l'ère « paper dry-run agent » (juin 2026). REMPLACÉE par l'architecture à TIMERS
systemd : le cerveau tourne via `brain_cycle.py` (bitget-brain.timer) et le scan via `scan_paper.py`
(bitget-scan.timer) — cf. `watchdog.py` (« la boucle persistante agent_loop.py a été remplacée par
les timers »). N'est LANCÉ par AUCUN service/cron. Conservé UNIQUEMENT pour des références de FALLBACK
vestigiales (watchdog/system_health scannent son PID ; agents_manifest/agent_hub le listent).

NE PAS relancer. Retrait propre = tâche DÉDIÉE et RÉVISÉE (touche watchdog/liveness -> risque de faux
kill-switch, cf. mémoire watchdog-liveness) : mettre à jour watchdog + system_health + agents_manifest
+ agent_hub + restart_agent.sh AVANT de supprimer ce fichier.
"""
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from config import LOOP_INTERVAL_SECONDS

PID_FILE = Path("agent_loop.pid")


def write_pid_file():
    """Ecrit le PID courant (utilise par watchdog.py et restart_agent.sh)."""
    PID_FILE.write_text(str(os.getpid()))


def remove_pid_file():
    """Supprime le PID file seulement s'il nous appartient (arret propre)."""
    try:
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()
    except OSError:
        pass


def _graceful_shutdown(signum, frame):
    """SIGTERM -> arret propre (declenche le bloc finally)."""
    raise KeyboardInterrupt


def run_agent_cycle():
    print()
    print("=" * 70)
    print(f"Cycle agent lancé à {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)

    result = subprocess.run(
        ["python", "agent_control.py"],
        capture_output=True,
        text=True
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print("ERREUR:")
        print(result.stderr)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    print("=== BITGET LOCAL AI AGENT LOOP ===")
    print("Mode: scan + journal + outcome + rapport")
    print("Aucun ordre envoyé")
    print("Aucune clé API utilisée")
    print(f"Intervalle: {LOOP_INTERVAL_SECONDS // 60} minutes")
    print(f"PID: {os.getpid()} (agent_loop.pid)")
    print("Arrêt manuel: CTRL + C")

    write_pid_file()

    try:
        while True:
            run_agent_cycle()
            print(f"Prochain cycle dans {LOOP_INTERVAL_SECONDS // 60} minutes.")
            time.sleep(LOOP_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print()
        print("Arrêt détecté.")
        print("Agent arrêté proprement.")
        print("Aucun ordre n’a été envoyé.")

    finally:
        remove_pid_file()
