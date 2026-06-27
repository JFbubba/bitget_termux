"""
outcome_state.py — version corrigée.

Classement : REVIEW_REQUIRED (corrige la logique de suivi des résultats ;
toujours AUCUN ordre réel — lecture marché seulement).

BUGS CORRIGÉS :
  1. [MAJEUR] Les signaux SHORT n'étaient JAMAIS évalués : check_signal()
     renvoyait "NON SUPPORTÉ" pour tout side != LONG. Conséquences :
       - aucun TP/SL détecté pour les shorts,
       - les shorts ne passaient jamais "EN COURS" -> jamais dédoublonnés
         par preorder_engine -> RISQUE DE DOUBLE EXÉCUTION (futur live),
       - statistiques finales faussées (aucun short).
     -> Ajout de check_short_outcome() + dispatch LONG/SHORT.
  2. [ROBUSTESSE] Un seul signal mal formé (timestamp ou prix invalide) faisait
     planter tout le run. -> chaque signal est désormais protégé par try/except.
  3. [ROBUSTESSE] Écriture ATOMIQUE de open_outcomes_state.csv (tmp + replace)
     pour éviter un fichier tronqué si le process est tué en plein écriture.

NB : la fenêtre de bougies reste limitée à CANDLE_LIMIT. Un signal plus vieux
que cette fenêtre peut ne jamais se finaliser (voir AUDIT_BITGET.md, §aging).
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from config import (
    SIGNALS_JOURNAL_FILE,
    OPEN_STATE_FILE,
    FINAL_OUTCOMES_FILE,
    PRODUCT_TYPE,
    TIMEFRAME,
    CANDLE_LIMIT,
)


SIGNALS_FILE = Path(SIGNALS_JOURNAL_FILE)
STATE_FILE = Path(OPEN_STATE_FILE)
FINAL_OUTCOMES_FILE = Path(FINAL_OUTCOMES_FILE)

FINAL_OUTCOMES = {"TP TOUCHÉ", "SL TOUCHÉ", "AMBIGU"}
SUPPORTED_SIDES = {"LONG", "SHORT"}


def parse_time(value):
    return datetime.fromisoformat(value)


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def signal_id_from_row(row):
    return "|".join([
        row.get("timestamp", ""),
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


def load_finalized_signal_ids():
    if not FINAL_OUTCOMES_FILE.exists():
        return set()
    with FINAL_OUTCOMES_FILE.open("r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        return {row["signal_id"] for row in reader if row.get("signal_id")}


from candle_reader import get_bitget_candles as _get_bitget_candles


def get_bitget_candles(symbol, product_type=PRODUCT_TYPE, granularity=TIMEFRAME, limit=CANDLE_LIMIT):
    """Délègue à la source durcie (candle_reader) en gardant les défauts config."""
    return _get_bitget_candles(symbol, product_type, granularity, limit)


def _running_status(side, last_close, entry):
    """EN COURS +/- du point de vue du SENS de la position."""
    if last_close == entry:
        return "EN COURS"
    if side == "LONG":
        return "EN COURS +" if last_close > entry else "EN COURS -"
    # SHORT : on gagne quand le prix baisse
    return "EN COURS +" if last_close < entry else "EN COURS -"


def check_outcome(signal, candles, side):
    """Évalue TP/SL pour un signal LONG ou SHORT."""
    signal_time = parse_time(signal["timestamp"])
    entry = safe_float(signal["entry"])
    stop_loss = safe_float(signal["stop_loss"])
    take_profit = safe_float(signal["take_profit"])

    if None in (entry, stop_loss, take_profit):
        return {"outcome": "EN COURS", "reason": "plan incomplet", "checked_candles": 0, "last_close": ""}

    future_candles = [c for c in candles if c["time"] > signal_time]
    if not future_candles:
        return {"outcome": "EN COURS", "reason": "aucune bougie future disponible",
                "checked_candles": 0, "last_close": ""}

    for candle in future_candles:
        if side == "LONG":
            hit_tp = candle["high"] >= take_profit
            hit_sl = candle["low"] <= stop_loss
        else:  # SHORT : TP sous l'entrée, SL au-dessus
            hit_tp = candle["low"] <= take_profit
            hit_sl = candle["high"] >= stop_loss

        if hit_tp and hit_sl:
            return {"outcome": "AMBIGU",
                    "reason": f"TP et SL touchés dans la même bougie {candle['time']}",
                    "checked_candles": len(future_candles), "last_close": candle["close"]}
        if hit_tp:
            return {"outcome": "TP TOUCHÉ", "reason": f"TP touché à {candle['time']}",
                    "checked_candles": len(future_candles), "last_close": candle["close"]}
        if hit_sl:
            return {"outcome": "SL TOUCHÉ", "reason": f"SL touché à {candle['time']}",
                    "checked_candles": len(future_candles), "last_close": candle["close"]}

    last_close = future_candles[-1]["close"]
    return {"outcome": _running_status(side, last_close, entry),
            "reason": f"dernier close: {last_close}",
            "checked_candles": len(future_candles), "last_close": last_close}


def check_signal(signal):
    side = signal.get("side")
    if side not in SUPPORTED_SIDES:
        return {"outcome": "NON SUPPORTÉ", "reason": f"side non supporté: {side}",
                "checked_candles": 0, "last_close": ""}
    candles = get_bitget_candles(signal["symbol"], limit=CANDLE_LIMIT)
    return check_outcome(signal, candles, side)


def build_row(signal, result, signal_id):
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
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
        "ranking": signal.get("ranking", ""),
        "score": signal.get("score", ""),
        "rsi": signal.get("rsi", ""),
        "implied_leverage": signal.get("implied_leverage", ""),
        "signal_id": signal_id,
    }


FIELDNAMES = [
    "updated_at", "signal_timestamp", "symbol", "side", "entry", "stop_loss",
    "take_profit", "outcome", "reason", "checked_candles", "last_close",
    "ranking", "score", "rsi", "implied_leverage", "signal_id",
]


def write_rows(path, rows):
    """Écriture atomique : on écrit dans un .tmp puis on remplace."""
    tmp = Path(str(path) + ".tmp")
    with tmp.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.replace(tmp, path)


def dedupe_open_rows(rows):
    latest = {}
    for row in rows:
        symbol = row.get("symbol")
        side = row.get("side")
        if not symbol or not side:
            continue
        key = (symbol, side)
        cur = latest.get(key)
        if cur is None or row.get("signal_timestamp", "") > cur.get("signal_timestamp", ""):
            latest[key] = row
    cleaned = list(latest.values())
    cleaned.sort(key=lambda r: (r.get("symbol", ""), r.get("side", ""), r.get("signal_timestamp", "")))
    return cleaned


def append_final_rows(rows):
    if not rows:
        return
    file_exists = FINAL_OUTCOMES_FILE.exists()
    with FINAL_OUTCOMES_FILE.open("a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    signals = load_accepted_signals()
    finalized_signal_ids = load_finalized_signal_ids()

    open_rows, final_rows, errors = [], [], 0

    print("=== OUTCOME STATE ===")
    print(f"Signaux acceptés trouvés: {len(signals)}")
    print(f"Signaux déjà finalisés: {len(finalized_signal_ids)}")
    print()

    for signal in signals:
        signal_id = signal_id_from_row(signal)
        if signal_id in finalized_signal_ids:
            continue
        try:
            result = check_signal(signal)
        except Exception as exc:  # robustesse : un signal cassé n'arrête pas le run
            errors += 1
            print(f"{signal.get('symbol','?'):<10} | ERREUR | {type(exc).__name__}: {exc}")
            continue

        row = build_row(signal, result, signal_id)
        target = final_rows if result["outcome"] in FINAL_OUTCOMES else open_rows
        target.append(row)
        print(f"{signal['symbol']:<10} | {result['outcome']:<12} | {result['reason']}")

    before = len(open_rows)
    open_rows = dedupe_open_rows(open_rows)
    write_rows(STATE_FILE, open_rows)
    append_final_rows(final_rows)

    print()
    print(f"Signaux ouverts mis à jour: {len(open_rows)} → {STATE_FILE}")
    if before != len(open_rows):
        print(f"Dédoublonnage hedge mode: {before} → {len(open_rows)}")
    print(f"Nouveaux signaux finalisés: {len(final_rows)} → {FINAL_OUTCOMES_FILE}")
    if errors:
        print(f"Signaux ignorés pour erreur: {errors}")


if __name__ == "__main__":
    main()
