import csv
from collections import Counter, defaultdict
from pathlib import Path


OUTCOMES_FILE = Path("outcomes_journal.csv")


def load_outcomes():
    if not OUTCOMES_FILE.exists():
        raise FileNotFoundError(f"Fichier introuvable: {OUTCOMES_FILE}")

    with OUTCOMES_FILE.open("r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader)


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except ValueError:
        return default


def summarize(rows):
    outcome_counter = Counter(row["outcome"] for row in rows)
    symbol_counter = Counter(row["symbol"] for row in rows)

    outcome_by_symbol = defaultdict(Counter)

    for row in rows:
        outcome_by_symbol[row["symbol"]][row["outcome"]] += 1

    return {
        "total": len(rows),
        "outcome_counter": outcome_counter,
        "symbol_counter": symbol_counter,
        "outcome_by_symbol": outcome_by_symbol,
    }


def print_report(summary):
    print("=== OUTCOME REPORT ===")
    print(f"Nombre total de vérifications: {summary['total']}")
    print()

    print("Résultats globaux:")
    for outcome, count in summary["outcome_counter"].most_common():
        print(f"- {outcome}: {count}")

    print()
    print("Vérifications par symbole:")
    for symbol, count in summary["symbol_counter"].most_common():
        print(f"- {symbol}: {count}")

    print()
    print("Résultats par symbole:")
    for symbol in sorted(summary["outcome_by_symbol"].keys()):
        print(f"- {symbol}")

        for outcome, count in summary["outcome_by_symbol"][symbol].most_common():
            print(f"  - {outcome}: {count}")


def print_last_checks(rows, limit=10):
    print()
    print(f"Dernières {limit} vérifications:")

    for row in rows[-limit:]:
        print(
            f"{row['checked_at']} | "
            f"{row['symbol']:<10} | "
            f"{row['side']:<5} | "
            f"Entry: {safe_float(row['entry']):>12,.4f} | "
            f"Last: {safe_float(row['last_close']):>12,.4f} | "
            f"{row['outcome']}"
        )


if __name__ == "__main__":
    rows = load_outcomes()
    summary = summarize(rows)

    print_report(summary)
    print_last_checks(rows, limit=10)
