import csv
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from config import OPEN_STATE_FILE

PENDING_ORDERS_FILE = Path("pending_orders.json")
PREORDER_GUARD_JOURNAL_FILE = Path("preorder_guard_journal.jsonl")

OBSERVATION_NEGATIVE_THRESHOLD = 3
BLOCK_REASON = (
    "portefeuille en OBSERVATION: au moins 3 positions ouvertes négatives; "
    "ne pas augmenter l’exposition"
)


def append_journal(event):
    with PREORDER_GUARD_JOURNAL_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_open_outcomes():
    path = Path(OPEN_STATE_FILE)
    if not path.exists():
        return []

    with path.open("r", newline="", encoding="utf-8", errors="ignore") as f:
        return list(csv.DictReader(f))


def portfolio_observation_mode():
    rows = load_open_outcomes()

    negative = [
        r for r in rows
        if str(r.get("outcome", "")).strip().upper() == "EN COURS -"
    ]

    positive = [
        r for r in rows
        if str(r.get("outcome", "")).strip().upper() == "EN COURS +"
    ]

    return {
        "mode": "OBSERVATION" if len(negative) >= OBSERVATION_NEGATIVE_THRESHOLD else "NORMAL",
        "negative_count": len(negative),
        "positive_count": len(positive),
        "open_count": len(rows),
    }


def load_orders_payload():
    if not PENDING_ORDERS_FILE.exists():
        return {"orders": []}

    try:
        data = json.loads(PENDING_ORDERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"orders": [], "warning": "pending_orders.json illisible"}

    if isinstance(data, dict):
        if "orders" not in data:
            data["orders"] = data.get("preorders") or []
        return data

    if isinstance(data, list):
        return {"orders": data}

    return {"orders": []}


def save_orders_payload(payload):
    tmp = Path(str(PENDING_ORDERS_FILE) + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, PENDING_ORDERS_FILE)


def apply_guard():
    state = portfolio_observation_mode()
    payload = load_orders_payload()
    orders = payload.get("orders", [])

    blocked = []

    print("=== PREORDER GUARD ===")
    print(f"Mode portefeuille: {state['mode']}")
    print(f"Ouvertes: {state['open_count']} | Positives: {state['positive_count']} | Négatives: {state['negative_count']}")
    print("Aucun ordre réel envoyé.")
    print()

    if state["mode"] != "OBSERVATION":
        print("Aucun blocage: portefeuille en mode NORMAL.")
        return state, blocked

    for order in orders:
        if order.get("status") != "PENDING_APPROVAL":
            continue

        order["status"] = "REJECTED"
        order["guard_status"] = "OBSERVATION_BLOCKED"
        reasons = order.setdefault("reasons", [])

        if BLOCK_REASON not in reasons:
            reasons.append(BLOCK_REASON)

        order["guarded_at"] = datetime.now(timezone.utc).isoformat()
        order["real_order_sent"] = False

        blocked.append(order.get("id"))

    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["portfolio_guard"] = {
        "mode": state["mode"],
        "negative_count": state["negative_count"],
        "positive_count": state["positive_count"],
        "open_count": state["open_count"],
        "blocked_count": len(blocked),
        "real_order_sent": False,
    }

    save_orders_payload(payload)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "PREORDER_OBSERVATION_GUARD",
        "mode": state["mode"],
        "negative_count": state["negative_count"],
        "positive_count": state["positive_count"],
        "open_count": state["open_count"],
        "blocked_count": len(blocked),
        "blocked_order_ids": blocked,
        "real_order_sent": False,
    }
    append_journal(event)

    print(f"Pré-ordres bloqués: {len(blocked)}")
    for oid in blocked:
        print(f"- {oid}")

    return state, blocked


if __name__ == "__main__":
    apply_guard()
