import subprocess
from pathlib import Path
from datetime import datetime

PAUSE_FILE = Path("agent_paused.flag")


COMMANDS = [
    {
        "name": "Préparer l’état TP / SL avant scan",
        "command": ["python", "outcome_state.py"],
    },
    {
        "name": "Univers d'analyse (dynamique top-N si activé)",
        "command": ["python", "universe.py"],
    },
    {
        "name": "Apprentissage du cerveau (essaim) : journaliser votes + poids EARCP",
        "command": ["python", "brain_cycle.py"],
    },
    {
        "name": "Scanner les marchés et journaliser les nouveaux signaux",
        "command": ["python", "journal_scanner.py"],
    },
    {
        "name": "Mettre à jour l’état TP / SL après scan",
        "command": ["python", "outcome_state.py"],
    },
    {
        "name": "Réconcilier les positions paper TP / SL",
        "command": ["python", "paper_position_reconciler.py"],
    },
    {
        "name": "Afficher le rapport open/final détaillé",
        "command": ["python", "state_report.py"],
    },
    {
        "name": "Afficher le résumé compact",
        "command": ["python", "compact_report.py"],
    },
    {
        "name": "Générer les signaux d’ordres proposés",
        "command": ["python", "order_signal_engine.py"],
    },
    {
        "name": "Générer les pré-ordres verrouillés",
        "command": ["python", "preorder_engine.py"],
    },
    {
        "name": "Appliquer le garde-fou pré-ordres observation",
        "command": ["python", "preorder_guard.py"],
    },
    {
        "name": "Envoyer le résumé compact et les signaux sur Telegram",
        "command": ["python", "telegram_notifier.py"],
    },
    # Validation T5 : SORTIE du cycle de scan — §41 l'a rendue TRANSVERSALE (univers
    # complet, n effectif), donc lourde : le STEP_TIMEOUT=90s de scan_paper la tuerait
    # à chaque tentative dès le rapport périmé (90s brûlées par cycle, rapport jamais
    # rafraîchi). Elle tourne sur son timer dédié : deploy/bitget-validation.timer
    # (6h, TimeoutStartSec=1500).
    {
        "name": "Moniteur carry non-directionnel (PAPER, journal auto-throttlé ~1h)",
        "command": ["python", "carry_monitor.py"],
    },
    {
        "name": "Mandat de gestion : règles dures + agents autorisés en réel",
        "command": ["python", "mandate.py"],
    },
    {
        "name": "Échelle d'edge : palier paper/réel par agent (mesuré)",
        "command": ["python", "edge_ladder.py"],
    },
    {
        "name": "Pont Agent Hub <-> bot (lecture seule + garde de mandat)",
        "command": ["python", "bitget_hub_bridge.py"],
    },
    {
        "name": "Accumulation BTC (spot DCA paper, ne vend jamais)",
        "command": ["python", "accumulation_engine.py", "BTCUSDT"],
    },
]


def run_command(name, command):
    print()
    print("=" * 70)
    print(name)
    print(f"Heure: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print("ERREUR:")
        print(result.stderr)

    return result.returncode


if __name__ == "__main__":
    print("=== BITGET LOCAL AI AGENT CONTROL ===")
    print("Mode: état hedge → scan → état hedge → rapport → résumé")
    print("Aucun ordre envoyé")
    print("Aucune clé API utilisée pour trader")
    print()

    if PAUSE_FILE.exists():
        print("⏸ Agent en pause: scan non exécuté.")
        print("Pour relancer: /resume dans Telegram ou supprimer agent_paused.flag")
        print()
        run_command("Afficher le résumé compact", ["python", "compact_report.py"])
        run_command("Générer les signaux d’ordres proposés", ["python", "order_signal_engine.py"])
        run_command("Générer les pré-ordres verrouillés", ["python", "preorder_engine.py"])
        run_command("Envoyer le résumé compact et les signaux sur Telegram", ["python", "telegram_notifier.py"])
        raise SystemExit(0)

    for item in COMMANDS:
        returncode = run_command(item["name"], item["command"])

        if returncode != 0:
            print()
            print("Arrêt du contrôleur : une commande a échoué.")
            break

    print()
    print("=" * 70)
    print("Cycle terminé.")
    print("Statut: aucun ordre envoyé.")
    print("=" * 70)
