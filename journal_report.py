import csv
from collections import Counter, defaultdict
from pathlib import Path


JOURNAL_FILE = Path("signals_journal.csv")


def load_journal():
    if not JOURNAL_FILE.exists():
        raise FileNotFoundError(f"Journal introuvable: {JOURNAL_FILE}")

    with JOURNAL_FILE.open("r", newline="") as csvfile:
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
    total = len(rows)

    status_counter = Counter(row["status"] for row in rows)
    symbol_counter = Counter(row["symbol"] for row in rows)
    accepted_by_symbol = Counter(
        row["symbol"] for row in rows if row["status"] == "ACCEPTÉ"
    )
    refused_by_symbol = Counter(
        row["symbol"] for row in rows if row["status"] == "REFUSÉ"
    )

    avg_rsi_by_symbol = defaultdict(list)
    avg_rank_by_symbol = defaultdict(list)

    for row in rows:
        symbol = row["symbol"]
        avg_rsi_by_symbol[symbol].append(safe_float(row["rsi"]))
        avg_rank_by_symbol[symbol].append(safe_float(row["ranking"]))

    return {
        "total": total,
        "status_counter": status_counter,
        "symbol_counter": symbol_counter,
        "accepted_by_symbol": accepted_by_symbol,
        "refused_by_symbol": refused_by_symbol,
        "avg_rsi_by_symbol": avg_rsi_by_symbol,
        "avg_rank_by_symbol": avg_rank_by_symbol,
    }


def print_summary(summary):
    print("=== JOURNAL REPORT ===")
    print(f"Nombre total de lignes: {summary['total']}")
    print()

    print("Statuts:")
    for status, count in summary["status_counter"].most_common():
        print(f"- {status}: {count}")

    print()
    print("Symboles scannés:")
    for symbol, count in summary["symbol_counter"].most_common():
        print(f"- {symbol}: {count}")

    print()
    print("Signaux acceptés par symbole:")
    if summary["accepted_by_symbol"]:
        for symbol, count in summary["accepted_by_symbol"].most_common():
            print(f"- {symbol}: {count}")
    else:
        print("- Aucun signal accepté")

    print()
    print("Signaux refusés par symbole:")
    if summary["refused_by_symbol"]:
        for symbol, count in summary["refused_by_symbol"].most_common():
            print(f"- {symbol}: {count}")
    else:
        print("- Aucun signal refusé")

    print()
    print("Moyennes par symbole:")
    for symbol in sorted(summary["symbol_counter"].keys()):
        rsi_values = summary["avg_rsi_by_symbol"][symbol]
        rank_values = summary["avg_rank_by_symbol"][symbol]

        avg_rsi = sum(rsi_values) / len(rsi_values)
        avg_rank = sum(rank_values) / len(rank_values)

        print(
            f"- {symbol:<10} "
            f"RSI moyen: {avg_rsi:>6.2f} | "
            f"Rank moyen: {avg_rank:>7.2f}"
        )


def print_recent_best(rows, limit=10):
    accepted_rows = [row for row in rows if row["status"] == "ACCEPTÉ"]

    accepted_rows.sort(
        key=lambda row: (
            safe_float(row["ranking"]),
            -safe_float(row["implied_leverage"]),
        ),
        reverse=True,
    )

    print()
    print(f"Top {limit} signaux acceptés récents:")

    if not accepted_rows:
        print("- Aucun signal accepté")
        return

    for row in accepted_rows[:limit]:
        print(
            f"{row['timestamp']} | "
            f"{row['symbol']:<10} | "
            f"{row['side']:<5} | "
            f"Rank: {row['ranking']:>4} | "
            f"Prix: {safe_float(row['price']):>12,.4f} | "
            f"SL: {safe_float(row['stop_loss']):>12,.4f} | "
            f"TP: {safe_float(row['take_profit']):>12,.4f} | "
            f"Lev: {safe_float(row['implied_leverage']):>5.2f}x"
        )


if __name__ == "__main__":
    rows = load_journal()
    summary = summarize(rows)

    print_summary(summary)
    print_recent_best(rows, limit=10)
