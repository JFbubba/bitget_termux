import csv
from datetime import datetime
from pathlib import Path


JOURNAL_FILE = Path("signals_journal.csv")


def parse_time(value):
    return datetime.fromisoformat(value)


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except ValueError:
        return default


def load_accepted_signals():
    if not JOURNAL_FILE.exists():
        raise FileNotFoundError(f"Journal introuvable: {JOURNAL_FILE}")

    with JOURNAL_FILE.open("r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        rows = []

        for row in reader:
            if row.get("status") == "ACCEPTÉ":
                rows.append(row)

        return rows


from candle_reader import get_bitget_candles


def check_long_outcome(signal, candles):
    signal_time = parse_time(signal["timestamp"])
    entry = safe_float(signal["entry"])
    stop_loss = safe_float(signal["stop_loss"])
    take_profit = safe_float(signal["take_profit"])

    future_candles = [
        candle for candle in candles
        if candle["time"] > signal_time
    ]

    if not future_candles:
        return {
            "outcome": "EN COURS",
            "reason": "aucune bougie future disponible",
            "checked_candles": 0,
        }

    for candle in future_candles:
        hit_tp = candle["high"] >= take_profit
        hit_sl = candle["low"] <= stop_loss

        if hit_tp and hit_sl:
            return {
                "outcome": "AMBIGU",
                "reason": f"TP et SL touchés dans la même bougie {candle['time']}",
                "checked_candles": len(future_candles),
            }

        if hit_tp:
            return {
                "outcome": "TP TOUCHÉ",
                "reason": f"TP touché à {candle['time']}",
                "checked_candles": len(future_candles),
            }

        if hit_sl:
            return {
                "outcome": "SL TOUCHÉ",
                "reason": f"SL touché à {candle['time']}",
                "checked_candles": len(future_candles),
            }

    last_close = future_candles[-1]["close"]

    if last_close > entry:
        status = "EN COURS +"
    elif last_close < entry:
        status = "EN COURS -"
    else:
        status = "EN COURS"

    return {
        "outcome": status,
        "reason": f"dernier close: {last_close}",
        "checked_candles": len(future_candles),
    }


def check_signal(signal):
    symbol = signal["symbol"]
    side = signal["side"]

    candles = get_bitget_candles(symbol, limit=100)

    if side == "LONG":
        return check_long_outcome(signal, candles)

    return {
        "outcome": "NON SUPPORTÉ",
        "reason": f"side non supporté pour l’instant: {side}",
        "checked_candles": 0,
    }


if __name__ == "__main__":
    signals = load_accepted_signals()

    print("=== OUTCOME CHECKER ===")
    print(f"Signaux acceptés trouvés: {len(signals)}")
    print()

    if not signals:
        print("Aucun signal accepté à vérifier.")
    else:
        for signal in signals:
            result = check_signal(signal)

            print(
                f"{signal['timestamp']} | "
                f"{signal['symbol']:<10} | "
                f"{signal['side']:<5} | "
                f"Entry: {safe_float(signal['entry']):>12,.4f} | "
                f"SL: {safe_float(signal['stop_loss']):>12,.4f} | "
                f"TP: {safe_float(signal['take_profit']):>12,.4f} | "
                f"{result['outcome']:<10} | "
                f"{result['reason']}"
            )
