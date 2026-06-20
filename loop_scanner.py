import subprocess
import time
from datetime import datetime


INTERVAL_SECONDS = 15 * 60


def run_scan():
    print()
    print("=" * 60)
    print(f"Scan lancé à {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 60)

    result = subprocess.run(
        ["python", "journal_scanner.py"],
        capture_output=True,
        text=True
    )

    print(result.stdout)

    if result.stderr:
        print("ERREUR:")
        print(result.stderr)


if __name__ == "__main__":
    print("=== BITGET LOOP SCANNER ===")
    print("Mode: analyse + journal uniquement")
    print("Aucun ordre envoyé")
    print(f"Intervalle: {INTERVAL_SECONDS // 60} minutes")
    print("Arrêt manuel: CTRL + C")

    try:
        while True:
            run_scan()
            print(f"Prochain scan dans {INTERVAL_SECONDS // 60} minutes.")
            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print()
        print("Arrêt manuel détecté.")
        print("Scanner arrêté proprement.")
        print("Aucun ordre n’a été envoyé.")
