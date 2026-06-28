import json
from pathlib import Path
from datetime import datetime, timezone

from config import PRODUCT_TYPE, TIMEFRAME, CANDLE_LIMIT
from outcome_state import get_bitget_candles
from paper_positions import load_paper_positions, save_paper_positions

PAPER_POSITIONS_JOURNAL_FILE = Path("paper_positions_journal.jsonl")


def append_journal(event):
    with PAPER_POSITIONS_JOURNAL_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


from numeric_utils import safe_float


def parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def check_position_outcome(position, candles):
    side = str(position.get("side", "")).upper()
    opened_at = parse_time(position.get("opened_at", ""))

    entry = safe_float(position.get("entry"))
    stop_loss = safe_float(position.get("stop_loss"))
    take_profit = safe_float(position.get("take_profit"))

    if side not in {"LONG", "SHORT"}:
        return {
            "status": "OPEN",
            "reason": f"side non supporté: {side}",
            "last_close": None,
        }

    if opened_at is None:
        return {
            "status": "OPEN",
            "reason": "opened_at invalide",
            "last_close": None,
        }

    if None in (entry, stop_loss, take_profit):
        return {
            "status": "OPEN",
            "reason": "plan incomplet",
            "last_close": None,
        }

    future_candles = [c for c in candles if c["time"] > opened_at]

    if not future_candles:
        return {
            "status": "OPEN",
            "reason": "aucune bougie future disponible",
            "last_close": None,
        }

    for candle in future_candles:
        if side == "LONG":
            hit_tp = candle["high"] >= take_profit
            hit_sl = candle["low"] <= stop_loss
        else:
            hit_tp = candle["low"] <= take_profit
            hit_sl = candle["high"] >= stop_loss

        if hit_tp and hit_sl:
            return {
                "status": "AMBIGU",
                "reason": f"TP et SL touchés dans la même bougie {candle['time']}",
                "last_close": candle["close"],
                "closed_at": candle["time"].isoformat(),
            }

        if hit_tp:
            return {
                "status": "CLOSED_TP",
                "reason": f"TP touché à {candle['time']}",
                "last_close": candle["close"],
                "closed_at": candle["time"].isoformat(),
            }

        if hit_sl:
            return {
                "status": "CLOSED_SL",
                "reason": f"SL touché à {candle['time']}",
                "last_close": candle["close"],
                "closed_at": candle["time"].isoformat(),
            }

    last = future_candles[-1]
    return {
        "status": "OPEN",
        "reason": f"toujours ouvert, dernier close: {last['close']}",
        "last_close": last["close"],
    }


def reconcile():
    payload = load_paper_positions()
    positions = payload.get("positions", [])

    checked = 0
    closed = 0
    errors = 0

    print("=== PAPER POSITION RECONCILER ===")
    print("Mode: lecture seule / paper / aucun ordre réel")
    print(f"Positions totales: {len(positions)}")
    print()

    candles_cache = {}

    for position in positions:
        if position.get("status") != "OPEN":
            continue

        checked += 1

        symbol = str(position.get("symbol", "")).upper()

        try:
            if symbol not in candles_cache:
                candles_cache[symbol] = get_bitget_candles(
                    symbol,
                    product_type=PRODUCT_TYPE,
                    granularity=TIMEFRAME,
                    limit=CANDLE_LIMIT,
                )

            result = check_position_outcome(position, candles_cache[symbol])

            position["last_checked_at"] = datetime.now(timezone.utc).isoformat()
            position["last_close"] = result.get("last_close")
            position["last_reason"] = result.get("reason")

            if result["status"] in {"CLOSED_TP", "CLOSED_SL", "AMBIGU"}:
                old_status = position.get("status")
                position["status"] = result["status"]
                position["closed_at"] = result.get("closed_at") or datetime.now(timezone.utc).isoformat()
                position["close_reason"] = result.get("reason")
                position["real_order_sent"] = False
                closed += 1

                event = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": result["status"],
                    "source_order_id": position.get("source_order_id"),
                    "symbol": position.get("symbol"),
                    "side": position.get("side"),
                    "old_status": old_status,
                    "new_status": result["status"],
                    "reason": result.get("reason"),
                    "last_close": result.get("last_close"),
                    "real_order_sent": False,
                }
                append_journal(event)

            print(
                f"{symbol:<10} | {position.get('side'):<5} | "
                f"{position.get('status'):<10} | {result.get('reason')}"
            )

        except Exception as exc:
            errors += 1
            print(f"{symbol:<10} | ERREUR | {type(exc).__name__}: {exc}")

    save_paper_positions(payload)

    print()
    print(f"Positions vérifiées: {checked}")
    print(f"Positions fermées paper: {closed}")
    print(f"Erreurs: {errors}")
    print("Aucun ordre réel envoyé.")

    return checked, closed, errors


if __name__ == "__main__":
    reconcile()
