import csv
from collections import Counter
from pathlib import Path
from config import OPEN_STATE_FILE, FINAL_OUTCOMES_FILE


OPEN_FILE = Path(OPEN_STATE_FILE)
FINAL_FILE = Path(FINAL_OUTCOMES_FILE)


def load_csv(path):
    if not path.exists():
        return []

    with path.open("r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader)


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except ValueError:
        return default


def print_final_report(final_rows):
    print("=== FINAL OUTCOMES ===")
    print(f"Signaux finalisés: {len(final_rows)}")

    if not final_rows:
        print("- Aucun signal finalisé")
        return

    outcome_counter = Counter(row["outcome"] for row in final_rows)
    symbol_counter = Counter(row["symbol"] for row in final_rows)

    print()
    print("Résultats:")
    for outcome, count in outcome_counter.most_common():
        print(f"- {outcome}: {count}")

    print()
    print("Par symbole:")
    for symbol, count in symbol_counter.most_common():
        print(f"- {symbol}: {count}")

    print()
    print("Détail:")
    for row in final_rows:
        print(
            f"{row['signal_timestamp']} | "
            f"{row['symbol']:<10} | "
            f"{row['side']:<5} | "
            f"{row['outcome']:<10} | "
            f"Entry: {safe_float(row['entry'], 0):>12,.4f} | "
            f"SL: {safe_float(row['stop_loss'], 0):>12,.4f} | "
            f"TP: {safe_float(row['take_profit'], 0):>12,.4f}"
        )


def print_open_report(open_rows):
    print()
    print("=== OPEN OUTCOMES ===")
    print(f"Signaux ouverts: {len(open_rows)}")

    if not open_rows:
        print("- Aucun signal ouvert")
        return

    outcome_counter = Counter(row["outcome"] for row in open_rows)
    symbol_counter = Counter(row["symbol"] for row in open_rows)

    print()
    print("États:")
    for outcome, count in outcome_counter.most_common():
        print(f"- {outcome}: {count}")

    print()
    print("Par symbole:")
    for symbol, count in symbol_counter.most_common():
        print(f"- {symbol}: {count}")

    print()
    print("Détail:")
    for row in open_rows:
        entry = safe_float(row["entry"])
        last = safe_float(row["last_close"])

        if entry is None:
            entry_text = "N/A"
        else:
            entry_text = f"{entry:,.4f}"

        if last is None:
            last_text = "N/A"
            pnl_text = "N/A"
        else:
            last_text = f"{last:,.4f}"

            if entry and entry > 0:
                pnl_percent = ((last - entry) / entry) * 100
                pnl_text = f"{pnl_percent:>7.3f}%"
            else:
                pnl_text = "N/A"

        print(
            f"{row['signal_timestamp']} | "
            f"{row['symbol']:<10} | "
            f"{row['side']:<5} | "
            f"{row['outcome']:<10} | "
            f"Entry: {entry_text:>12} | "
            f"Last: {last_text:>12} | "
            f"PnL théorique: {pnl_text}"
        )


if __name__ == "__main__":
    final_rows = load_csv(FINAL_FILE)
    open_rows = load_csv(OPEN_FILE)

    print("=== STATE REPORT ===")
    print_final_report(final_rows)
    print_open_report(open_rows)