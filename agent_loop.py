import subprocess
import time
from config import LOOP_INTERVAL_SECONDS
from datetime import datetime




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
    print("=== BITGET LOCAL AI AGENT LOOP ===")
    print("Mode: scan + journal + outcome + rapport")
    print("Aucun ordre envoyé")
    print("Aucune clé API utilisée")
    print(f"Intervalle: {LOOP_INTERVAL_SECONDS // 60} minutes")
    print("Arrêt manuel: CTRL + C")

    try:
        while True:
            run_agent_cycle()
            print(f"Prochain cycle dans {LOOP_INTERVAL_SECONDS // 60} minutes.")
            time.sleep(LOOP_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print()
        print("Arrêt manuel détecté.")
        print("Agent arrêté proprement.")
        print("Aucun ordre n’a été envoyé.")
