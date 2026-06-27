import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from paper_positions import add_paper_position_from_order

PENDING_ORDERS_FILE = Path("pending_orders.json")
EXECUTION_JOURNAL_FILE = Path("execution_dry_run_journal.jsonl")

EXECUTION_MODE = "DRY_RUN_ONLY"


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
    with EXECUTION_JOURNAL_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _risk_gate(order):
    """Vérifie kill-switch + caps durs (risk_manager) pour un ordre. Best-effort mais
    FAIL-SAFE : le kill-switch (lu en premier dans check_trade) est robuste même si la
    lecture de l'état paper échoue. Retourne (autorisé, raison)."""
    try:
        import risk_manager
        import risk_state
        st = risk_state.snapshot()
        proposed = {"notional_usd": order.get("notional_usdt", 0) or 0,
                    "leverage": order.get("implied_leverage", 1) or 1}
        return risk_manager.check_trade(
            proposed, open_positions=st["open_positions"],
            daily_loss_usd=st["daily_loss_usd"])
    except Exception as exc:
        # même en cas d'erreur, on respecte le kill-switch (garde minimale)
        try:
            import risk_manager
            if risk_manager.kill_switch_active():
                return False, "KILL_SWITCH actif"
        except Exception:
            pass
        return True, f"garde risque indisponible ({type(exc).__name__})"


def dry_run_execute(order_id):
    payload = load_payload()
    orders = payload.get("orders", [])

    for order in orders:
        if order.get("id") != order_id:
            continue

        status = order.get("status")

        if status != "APPROVED_SIMULATION":
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "EXECUTION_DRY_RUN_REJECTED",
                "order_id": order_id,
                "reason": f"statut non exécutable: {status}",
                "execution_mode": EXECUTION_MODE,
                "real_order_sent": False,
            }
            append_journal(event)

            return (
                False,
                f"❌ Dry-run refusé.\n"
                f"ID: {order_id}\n"
                f"Statut actuel: {status}\n"
                f"Aucun ordre réel envoyé."
            )

        # GARDE-FOU DUR : kill-switch + caps risque AVANT toute transition (même en
        # dry-run, pour valider le câblage et garantir qu'un KILL_SWITCH bloque tout).
        ok_risk, risk_reason = _risk_gate(order)
        if not ok_risk:
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "EXECUTION_BLOCKED_RISK",
                "order_id": order_id,
                "symbol": order.get("symbol"),
                "reason": risk_reason,
                "execution_mode": EXECUTION_MODE,
                "real_order_sent": False,
            }
            append_journal(event)
            return (
                False,
                f"⛔ Bloqué par le risk-manager.\n"
                f"ID: {order_id}\n"
                f"Raison: {risk_reason}\n"
                f"Aucun ordre réel envoyé."
            )

        order["status"] = "EXECUTION_DRY_RUN"
        order["dry_run_executed_at"] = datetime.now(timezone.utc).isoformat()
        order["execution"] = "DRY_RUN_ONLY_NO_REAL_ORDER"

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "EXECUTION_DRY_RUN",
            "order_id": order_id,
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "entry": order.get("entry"),
            "stop_loss": order.get("stop_loss"),
            "take_profit": order.get("take_profit"),
            "risk_usdt": order.get("risk_usdt"),
            "notional_usdt": order.get("notional_usdt"),
            "implied_leverage": order.get("implied_leverage"),
            "execution_mode": EXECUTION_MODE,
            "real_order_sent": False,
        }

        paper_added, paper_reason = add_paper_position_from_order(order)
        event["paper_position_added"] = paper_added
        event["paper_position_reason"] = paper_reason

        append_journal(event)
        save_payload(payload)

        return (
            True,
            f"🧪 EXECUTION DRY-RUN validée.\n"
            f"ID: {order_id}\n"
            f"{order.get('symbol')} {order.get('side')}\n"
            f"Entrée: {order.get('entry')}\n"
            f"SL: {order.get('stop_loss')}\n"
            f"TP: {order.get('take_profit')}\n"
            f"Risque: {order.get('risk_usdt')} USDT\n"
            f"Notionnel: {order.get('notional_usdt')} USDT\n\n"
            f"Mode: DRY_RUN_ONLY\n"
            f"Position paper: {paper_reason}\n"
            f"Aucun ordre réel envoyé."
        )

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "EXECUTION_DRY_RUN_NOT_FOUND",
        "order_id": order_id,
        "execution_mode": EXECUTION_MODE,
        "real_order_sent": False,
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
        print("python execution_gateway.py dry_run ORDER_ID")
        raise SystemExit(1)

    action = sys.argv[1]
    order_id = sys.argv[2]

    if action != "dry_run":
        print(f"Action inconnue: {action}")
        raise SystemExit(1)

    ok, message = dry_run_execute(order_id)
    print(message)

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
