import json
import sys
from pathlib import Path
from datetime import datetime, timezone

PENDING_ORDERS_FILE = Path("pending_orders.json")
APPROVAL_JOURNAL_FILE = Path("preorder_approvals_journal.jsonl")


def load_payload():
    if not PENDING_ORDERS_FILE.exists():
        raise FileNotFoundError("pending_orders.json introuvable")

    return json.loads(PENDING_ORDERS_FILE.read_text(encoding="utf-8"))


def save_payload(payload):
    PENDING_ORDERS_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def append_journal(event):
    with APPROVAL_JOURNAL_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def approve_preorder(order_id):
    payload = load_payload()
    orders = payload.get("orders", [])

    for order in orders:
        if order.get("id") != order_id:
            continue

        current_status = order.get("status")

        if current_status != "PENDING_APPROVAL":
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "APPROVE_REJECTED",
                "order_id": order_id,
                "reason": f"statut non approuvable: {current_status}",
                "execution": "NO_REAL_ORDER",
            }
            append_journal(event)

            return (
                False,
                f"❌ Pré-ordre non approuvable.\n"
                f"ID: {order_id}\n"
                f"Statut actuel: {current_status}\n"
                f"Aucun ordre réel envoyé."
            )

        order["status"] = "APPROVED_SIMULATION"
        order["approved_at"] = datetime.now(timezone.utc).isoformat()
        order["execution"] = "APPROVED_SIMULATION_NO_REAL_ORDER"

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "APPROVED_SIMULATION",
            "order_id": order_id,
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "entry": order.get("entry"),
            "stop_loss": order.get("stop_loss"),
            "take_profit": order.get("take_profit"),
            "risk_usdt": order.get("risk_usdt"),
            "notional_usdt": order.get("notional_usdt"),
            "execution": "NO_REAL_ORDER",
        }

        append_journal(event)
        save_payload(payload)

        return (
            True,
            f"✅ Pré-ordre approuvé en simulation.\n"
            f"ID: {order_id}\n"
            f"{order.get('symbol')} {order.get('side')}\n"
            f"Entrée: {order.get('entry')}\n"
            f"SL: {order.get('stop_loss')}\n"
            f"TP: {order.get('take_profit')}\n"
            f"Risque: {order.get('risk_usdt')} USDT\n"
            f"Notionnel: {order.get('notional_usdt')} USDT\n\n"
            f"Statut: APPROVED_SIMULATION\n"
            f"Aucun ordre réel envoyé."
        )

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "APPROVE_NOT_FOUND",
        "order_id": order_id,
        "execution": "NO_REAL_ORDER",
    }
    append_journal(event)

    return (
        False,
        f"❌ Pré-ordre introuvable.\n"
        f"ID: {order_id}\n"
        f"Aucun ordre réel envoyé."
    )


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("python preorder_approval.py approve ORDER_ID")
        raise SystemExit(1)

    action = sys.argv[1]
    order_id = sys.argv[2]

    if action != "approve":
        print(f"Action inconnue: {action}")
        raise SystemExit(1)

    ok, message = approve_preorder(order_id)
    print(message)

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
