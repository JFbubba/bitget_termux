import os
import json
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CHUNK_SIZE = 3900


def run_script(script):
    try:
        result = subprocess.run(
            ["python", script],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0:
            return f"=== {script} ===\nERREUR:\n{result.stderr[-1500:]}"
        return result.stdout.strip()
    except Exception as exc:
        return f"=== {script} ===\nERREUR: {type(exc).__name__}: {exc}"


def read_file(path, title):
    p = Path(path)
    if not p.exists():
        return f"=== {title} ===\nFichier absent: {path}"
    return p.read_text(encoding="utf-8", errors="ignore").strip()


def preorders_report():
    path = Path("pending_orders.json")
    if not path.exists():
        return "=== PREORDERS ===\npending_orders.json absent"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"=== PREORDERS ===\nErreur JSON: {type(exc).__name__}: {exc}"

    if isinstance(data, dict):
        orders = data.get("orders") or data.get("preorders") or []
    elif isinstance(data, list):
        orders = data
    else:
        orders = []

    lines = [
        "=== PREORDERS ===",
        f"Total: {len(orders)}",
        f"En attente: {sum(1 for o in orders if o.get('status') == 'PENDING_APPROVAL')}",
        f"Approuvés: {sum(1 for o in orders if o.get('status') == 'APPROVED_SIMULATION')}",
        f"Dry-run: {sum(1 for o in orders if o.get('status') == 'EXECUTION_DRY_RUN')}",
        f"Rejetés: {sum(1 for o in orders if o.get('status') == 'REJECTED')}",
        "",
    ]

    for o in orders[:8]:
        lines.append(
            f"- {o.get('id')} | {o.get('status')} | "
            f"{o.get('symbol')} {o.get('side')} | "
            f"Notionnel: {o.get('notional_usdt')} | Risque: {o.get('risk_usdt')}"
        )
        reasons = o.get("reasons") or []
        if reasons:
            lines.append("  Raisons: " + "; ".join(reasons))

    return "\n".join(lines)


def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram non configuré: token ou chat_id absent.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    for i in range(0, len(text), CHUNK_SIZE):
        chunk = text[i:i + CHUNK_SIZE]
        r = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": chunk},
            timeout=15,
        )
        r.raise_for_status()

    return True



def send_telegram_message(text):
    """
    Alias de compatibilité pour telegram_command_bot.py.
    Ne change rien à la logique : envoie Telegram uniquement.
    Aucun ordre réel.
    """
    return send_telegram(text)

def main():
    blocks = [
        "=== BITGET LOCAL AGENT ===\nMode: PAPER / DRY_RUN_ONLY\nAucun ordre réel envoyé.",
        run_script("compact_report.py"),
        read_file("order_signals_report.txt", "ORDER SIGNALS"),
        preorders_report(),
        run_script("paper_report.py"),
    ]

    message = "\n\n".join(b for b in blocks if b)
    ok = send_telegram(message)

    if ok:
        print("Rapport compact + signaux + pré-ordres + paper report envoyé sur Telegram.")
    else:
        print("Rapport construit mais Telegram non configuré.")


if __name__ == "__main__":
    main()
