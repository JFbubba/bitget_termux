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
