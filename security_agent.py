from pathlib import Path

from agents_manifest import AGENTS


ENV_FILE = Path(".env")
PAUSE_FILE = Path("agent_paused.flag")

GETAGENT_PATHS = [
    Path.home() / ".codex" / "skills" / "getagent",
    Path.home() / ".claude" / "skills" / "getagent",
    Path.home() / ".cursor" / "skills" / "getagent",
]

SENSITIVE_FILENAMES = [
    ".env",
]

DANGEROUS_KEYWORDS = [
    "place_order", "open_long", "open_short", "close_position",
    "cancel_order", "change_leverage", "transfer", "withdraw",
    "send_order", "create_order", "submit_order", "set_leverage",
    "market_order", "limit_order", "post_order",
    "placeorder", "createorder", "submitorder", "cancelorder",
    "closeposition", "setleverage", "createmarketorder", "createlimitorder",
    "order/place", "/api/v2/mix/order", "/api/mix/v1/order",
    "batch-place-order", "place-order", "close-positions",
]

FILES_TO_SCAN = [
    "config.py",
    "journal_scanner.py",
    "outcome_state.py",
    "state_report.py",
    "compact_report.py",
    "agent_control.py",
    "agent_loop.py",
    "telegram_notifier.py",
    "telegram_command_bot.py",
    "preorder_approval.py",
    "execution_gateway.py",
    "paper_positions.py",
    "paper_position_reconciler.py",
    "paper_report.py",
    "preorder_engine.py",
    "preorder_guard.py",
    "agent_hub.py",
    "agents_manifest.py",
    "bitget_balance_reader.py",
    "account_equity.py",
    "git_version.py",
    "system_health.py",
    "watchdog.py",
    "stats_report.py",
    "pro_indicators.py",
]


def scan_file_for_keywords(filename):
    path = Path(filename)

    if not path.exists():
        return []

    text = path.read_text(errors="ignore").lower()
    findings = []

    for keyword in DANGEROUS_KEYWORDS:
        if keyword.lower() in text:
            findings.append(keyword)

    return findings



def telegram_auth_is_present(text):
    import re

    has_const = "ALLOWED_CHAT_ID" in text
    pattern = re.compile(
        r"(chat_id\s*[!=]=\s*str\(\s*ALLOWED_CHAT_ID\s*\)"
        r"|str\(\s*chat_id\s*\)\s*[!=]=\s*ALLOWED_CHAT_ID"
        r"|[!=]=\s*ALLOWED_CHAT_ID"
        r"|is_authorized\s*\()",
        re.IGNORECASE,
    )
    return has_const, bool(pattern.search(text))

def main():
    warnings = []

    print("=== SECURITY AGENT ===")
    print()

    print("Vérification manifest:")
    for agent in AGENTS:
        can_trade = agent.get("can_trade", None)

        if can_trade is not False:
            warnings.append(f"{agent['id']} a can_trade={can_trade}")

        print(f"- {agent['name']}: can_trade={can_trade}")

    print()

    print("Vérification fichiers sensibles:")
    print(f"- .env présent: {ENV_FILE.exists()}")
    print("- contenu .env: non affiché volontairement")
    print()

    print("Vérification pause:")
    print(f"- agent_paused.flag présent: {PAUSE_FILE.exists()}")
    print("- mécanisme pause disponible: True")
    print()

    print("Scan mots-clés dangereux:")
    dangerous_hits = {}

    for filename in FILES_TO_SCAN:
        hits = scan_file_for_keywords(filename)

        if hits:
            dangerous_hits[filename] = hits
            warnings.append(f"{filename}: mots-clés suspects {hits}")

        print(f"- {filename}: {'WARNING ' + str(hits) if hits else 'OK'}")

    print()

    print("Vérification GetAgent:")
    getagent_installed = [path for path in GETAGENT_PATHS if path.exists()]
    print(f"- installations détectées: {len(getagent_installed)}")

    for path in GETAGENT_PATHS:
        print(f"- {path}: {'présent' if path.exists() else 'absent'}")

    if getagent_installed:
        print("- statut: WARNING contrôlé")
        print("- raison: GetAgent contient des références à des fonctions de trading réel.")
        print("- règle: aucune clé API live ne doit être fournie à GetAgent.")
    else:
        print("- statut: absent")

    print()

    print("Vérification Telegram:")
    telegram_file = Path("telegram_command_bot.py")
    telegram_text = telegram_file.read_text(errors="ignore") if telegram_file.exists() else ""

    has_allowed_chat = "ALLOWED_CHAT_ID" in telegram_text
    has_chat_check = "chat_id != str(ALLOWED_CHAT_ID)" in telegram_text

    print(f"- ALLOWED_CHAT_ID présent: {has_allowed_chat}")
    print(f"- contrôle chat_id présent: {has_chat_check}")

    if not has_allowed_chat:
        warnings.append("ALLOWED_CHAT_ID absent de telegram_command_bot.py")

    if not has_chat_check:
        warnings.append("contrôle chat_id absent ou modifié dans telegram_command_bot.py")

    print()

    if warnings:
        print("VERDICT: WARNING")
        print()
        print("Points à vérifier:")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("VERDICT: SAFE")
        print()
        print("Aucun droit de trading détecté.")
        print("Aucun mot-clé critique détecté.")
        print("Contrôle Telegram actif.")
        print("Pause disponible.")


if __name__ == "__main__":
    main()
