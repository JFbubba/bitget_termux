from pathlib import Path
from datetime import datetime

import config
from agents_manifest import AGENTS, agent_file_exists


FILES = {
    "Config centrale": "config.py",
    "Scanner marché": "journal_scanner.py",
    "Suivi TP/SL": "outcome_state.py",
    "Rapport détaillé": "state_report.py",
    "Rapport compact": "compact_report.py",
    "Contrôleur agent": "agent_control.py",
    "Lecture solde Bitget": "bitget_balance_reader.py",
    "Equity dynamique": "account_equity.py",
    "Telegram notifier": "telegram_notifier.py",
    "Telegram command bot": "telegram_command_bot.py",
    "Agents manifest": "agents_manifest.py",
    "Signaux d’ordres proposés": "order_signal_engine.py",
    "Pré-ordres verrouillés": "preorder_engine.py",
}

PAUSE_FILE = Path("agent_paused.flag")
ENV_FILE = Path(".env")

JOURNALS = {
    "Journal signaux": config.SIGNALS_JOURNAL_FILE,
    "État positions ouvertes": config.OPEN_STATE_FILE,
    "Résultats finalisés": config.FINAL_OUTCOMES_FILE,
}


def status_icon(condition):
    return "✅" if condition else "❌"


def count_csv_rows(path):
    p = Path(path)

    if not p.exists():
        return 0

    lines = p.read_text().splitlines()

    if len(lines) <= 1:
        return 0

    return len(lines) - 1


def main():
    print("=== BITGET AI AGENT HUB LOCAL ===")
    print(f"Heure: {datetime.now().isoformat(timespec='seconds')}")
    print()

    print("État global:")
    print(f"- Agent actif: {status_icon(not PAUSE_FILE.exists())}")
    print(f"- Agent en pause: {status_icon(PAUSE_FILE.exists())}")
    print(f"- Fichier .env présent: {status_icon(ENV_FILE.exists())}")
    print()

    print("Configuration trading:")
    print(f"- Product type: {config.PRODUCT_TYPE}")
    print(f"- Timeframe: {config.TIMEFRAME}")
    print(f"- Symboles: {', '.join(config.SYMBOLS)}")
    print(f"- Risque par trade: {config.RISK_PER_TRADE_PERCENT}%")
    print(f"- Levier implicite max: {config.MAX_IMPLIED_LEVERAGE}x")
    print(f"- Hedge mode: {config.HEDGE_MODE}")
    print(f"- Intervalle boucle: {config.LOOP_INTERVAL_SECONDS // 60} min")
    print()

    print("Modules installés:")
    for name, filename in FILES.items():
        print(f"- {status_icon(Path(filename).exists())} {name}: {filename}")
    print()

    print("Agents déclarés:")
    for agent in AGENTS:
        exists = agent_file_exists(agent)
        print(
            f"- {status_icon(exists)} {agent['name']} "
            f"| id={agent['id']} "
            f"| risque={agent['risk_level']} "
            f"| trade={agent['can_trade']}"
        )
    print()

    print("Journaux:")
    for name, filename in JOURNALS.items():
        rows = count_csv_rows(filename)
        print(f"- {status_icon(Path(filename).exists())} {name}: {filename} ({rows} lignes)")
    print()

    print("Commandes utiles:")
    print("- Cycle manuel local: python agent_control.py")
    print("- Boucle auto: timers systemd (bitget-brain / bitget-scan)")
    print("- Bot Telegram commandes: python telegram_command_bot.py")
    print("- Rapport compact: python compact_report.py")
    print("- Hub local: python agent_hub.py")
    print("- Manifest agents: python agents_manifest.py")
    print()

    print("Commandes Telegram:")
    print("- /status")
    print("- /config")
    print("- /config_guard")
    print("- /hub")
    print("- /agents")
    print("- /security")
    print("- /getagent_audit")
    print("- /signals")
    print("- /run_once")
    print("- /pause")
    print("- /resume")
    print("- /pause_status")
    print("- /help")
    print()

    print("Sécurité:")
    print("- Aucun ordre réel envoyé")
    print("- Lecture Bitget uniquement")
    print("- Telegram limité au chat_id configuré")
    print("- Pause possible via agent_paused.flag")
    print("- Tous les agents déclarés ont can_trade=False")


if __name__ == "__main__":
    main()
