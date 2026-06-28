import csv
import os
from datetime import datetime
from pathlib import Path


SIGNALS_FILE = Path("signals_journal.csv")
OUTCOMES_FILE = Path("outcomes_journal.csv")


def parse_time(value):
    return datetime.fromisoformat(value)


from numeric_utils import safe_float


def signal_id_from_row(row):
    return "|".join([
        row.get("timestamp", ""),
        row.get("symbol", ""),
        row.get("side", ""),
        str(row.get("entry", "")),
    ])


def outcome_signal_id_from_row(row):
    return "|".join([
        row.get("signal_timestamp", ""),
        row.get("symbol", ""),
        row.get("side", ""),
        str(row.get("entry", "")),
    ])


def load_accepted_signals():
    if not SIGNALS_FILE.exists():
        raise FileNotFoundError(f"Journal introuvable: {SIGNALS_FILE}")

    with SIGNALS_FILE.open("r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        return [row for row in reader if row.get("status") == "ACCEPTÉ"]


def load_existing_finalized_signal_ids():
    if not OUTCOMES_FILE.exists():
        return set()

    finalized = set()

    with OUTCOMES_FILE.open("r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            outcome = row.get("outcome", "")

            if outcome in ["TP TOUCHÉ", "SL TOUCHÉ", "AMBIGU"]:
                finalized.add(outcome_signal_id_from_row(row))

    return finalized


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
            "last_close": "",
        }

    for candle in future_candles:
        hit_tp = candle["high"] >= take_profit
        hit_sl = candle["low"] <= stop_loss

        if hit_tp and hit_sl:
            return {
                "outcome": "AMBIGU",
                "reason": f"TP et SL touchés dans la même bougie {candle['time']}",
                "checked_candles": len(future_candles),
                "last_close": candle["close"],
            }

        if hit_tp:
            return {
                "outcome": "TP TOUCHÉ",
                "reason": f"TP touché à {candle['time']}",
                "checked_candles": len(future_candles),
                "last_close": candle["close"],
            }

        if hit_sl:
            return {
                "outcome": "SL TOUCHÉ",
                "reason": f"SL touché à {candle['time']}",
                "checked_candles": len(future_candles),
                "last_close": candle["close"],
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
        "last_close": last_close,
    }


def check_signal(signal):
    candles = get_bitget_candles(signal["symbol"], limit=100)

    if signal["side"] == "LONG":
        return check_long_outcome(signal, candles)

    return {
        "outcome": "NON SUPPORTÉ",
        "reason": f"side non supporté: {signal['side']}",
        "checked_candles": 0,
        "last_close": "",
    }


def append_outcomes(rows):
    if not rows:
        return

    file_exists = os.path.exists(OUTCOMES_FILE)

    fieldnames = [
        "checked_at",
        "signal_timestamp",
        "symbol",
        "side",
        "entry",
        "stop_loss",
        "take_profit",
        "outcome",
        "reason",
        "checked_candles",
        "last_close",
        "ranking",
        "score",
        "rsi",
        "implied_leverage",
        "signal_id",
    ]

    with OUTCOMES_FILE.open("a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for row in rows:
            writer.writerow(row)


def build_outcome_row(signal, result, signal_id):
    return {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "signal_timestamp": signal["timestamp"],
        "symbol": signal["symbol"],
        "side": signal["side"],
        "entry": signal["entry"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "outcome": result["outcome"],
        "reason": result["reason"],
        "checked_candles": result["checked_candles"],
        "last_close": result["last_close"],
        "ranking": signal["ranking"],
        "score": signal["score"],
        "rsi": signal["rsi"],
        "implied_leverage": signal["implied_leverage"],
        "signal_id": signal_id,
    }


if __name__ == "__main__":
    signals = load_accepted_signals()
    finalized_signal_ids = load_existing_finalized_signal_ids()

    outcome_rows = []
    skipped = 0

    print("=== OUTCOME LOGGER ===")
    print(f"Signaux acceptés trouvés: {len(signals)}")
    print(f"Signaux déjà finalisés ignorés: {len(finalized_signal_ids)}")
    print(f"Fichier résultat: {OUTCOMES_FILE}")
    print()

    for signal in signals:
        signal_id = signal_id_from_row(signal)

        if signal_id in finalized_signal_ids:
            skipped += 1
            continue

        result = check_signal(signal)
        row = build_outcome_row(signal, result, signal_id)
        outcome_rows.append(row)

        print(
            f"{signal['timestamp']} | "
            f"{signal['symbol']:<10} | "
            f"{signal['side']:<5} | "
            f"{result['outcome']:<10} | "
            f"{result['reason']}"
        )

    append_outcomes(outcome_rows)

    print()
    print(f"{len(outcome_rows)} lignes ajoutées à {OUTCOMES_FILE}")
    print(f"{skipped} signaux ignorés car déjà finalisés")
