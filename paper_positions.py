import json
from pathlib import Path
from datetime import datetime, timezone

PAPER_POSITIONS_FILE = Path("paper_positions.json")


def load_paper_positions():
    if not PAPER_POSITIONS_FILE.exists():
        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "PAPER_ONLY_NO_REAL_ORDER",
            "positions": [],
        }

    try:
        return json.loads(PAPER_POSITIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "PAPER_ONLY_NO_REAL_ORDER",
            "positions": [],
            "warning": "paper_positions.json illisible, état réinitialisé en mémoire",
        }


def save_paper_positions(payload):
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = Path(str(PAPER_POSITIONS_FILE) + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PAPER_POSITIONS_FILE)


def open_symbol_sides_from_paper():
    payload = load_paper_positions()
    opened = set()

    for pos in payload.get("positions", []):
        if pos.get("status") != "OPEN":
            continue

        symbol = str(pos.get("symbol", "")).upper()
        side = str(pos.get("side", "")).upper()

        if symbol and side:
            opened.add((symbol, side))

    return opened


def add_paper_position_from_order(order):
    payload = load_paper_positions()
    positions = payload.setdefault("positions", [])

    order_id = order.get("id")

    for pos in positions:
        if pos.get("source_order_id") == order_id:
            return False, "position paper déjà existante"

    positions.append({
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "source_order_id": order_id,
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "entry": order.get("entry"),
        "stop_loss": order.get("stop_loss"),
        "take_profit": order.get("take_profit"),
        "risk_usdt": order.get("risk_usdt"),
        "notional_usdt": order.get("notional_usdt"),
        "implied_leverage": order.get("implied_leverage"),
        "status": "OPEN",
        "mode": "PAPER_ONLY_NO_REAL_ORDER",
        "real_order_sent": False,
    })

    save_paper_positions(payload)
    return True, "position paper ajoutée"


def main():
    payload = load_paper_positions()
    positions = payload.get("positions", [])
    opened = [p for p in positions if p.get("status") == "OPEN"]

    print("=== PAPER POSITIONS ===")
    print(f"Fichier: {PAPER_POSITIONS_FILE}")
    print(f"Positions totales: {len(positions)}")
    print(f"Positions ouvertes: {len(opened)}")
    print("Mode: PAPER_ONLY_NO_REAL_ORDER")
    print()

    for pos in opened:
        print(
            f"- {pos.get('symbol')} {pos.get('side')} | "
            f"Entry: {pos.get('entry')} | "
            f"SL: {pos.get('stop_loss')} | "
            f"TP: {pos.get('take_profit')} | "
            f"Source: {pos.get('source_order_id')}"
        )


if __name__ == "__main__":
    main()
