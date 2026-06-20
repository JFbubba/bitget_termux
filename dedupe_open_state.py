import csv
from pathlib import Path
from datetime import datetime


OPEN_FILE = Path("open_outcomes_state.csv")
BACKUP_FILE = Path(f"open_outcomes_state_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
TIME_FIELD = "signal_timestamp"


def load_rows(path):
    if not path.exists():
        return []

    with path.open("r", newline="") as csvfile:
        return list(csv.DictReader(csvfile))


def save_rows(path, rows, fieldnames):
    with path.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def main():
    rows = load_rows(OPEN_FILE)

    if not rows:
        print("Aucun état ouvert à nettoyer.")
        return

    fieldnames = rows[0].keys()

    save_rows(BACKUP_FILE, rows, fieldnames)

    latest_by_symbol_side = {}

    for row in rows:
        symbol = row.get("symbol")
        side = row.get("side")
        signal_timestamp = row.get(TIME_FIELD, "")

        if not symbol or not side:
            continue

        key = (symbol, side)
        current = latest_by_symbol_side.get(key)

        if current is None:
            latest_by_symbol_side[key] = row
            continue

        current_timestamp = current.get(TIME_FIELD, "")

        if signal_timestamp > current_timestamp:
            latest_by_symbol_side[key] = row

    cleaned_rows = list(latest_by_symbol_side.values())
    cleaned_rows.sort(
        key=lambda row: (
            row.get("symbol", ""),
            row.get("side", ""),
            row.get(TIME_FIELD, ""),
        )
    )

    save_rows(OPEN_FILE, cleaned_rows, fieldnames)

    print("=== DEDUPE OPEN STATE ===")
    print(f"Champ temporel utilisé: {TIME_FIELD}")
    print(f"Backup créé: {BACKUP_FILE}")
    print(f"Lignes avant: {len(rows)}")
    print(f"Lignes après: {len(cleaned_rows)}")
    print()

    print("Positions ouvertes conservées:")

    for row in cleaned_rows:
        print(
            f"- {row.get('symbol')} {row.get('side')} | "
            f"{row.get('outcome')} | "
            f"Entry: {row.get('entry')} | "
            f"Last: {row.get('last_close')} | "
            f"Signal: {row.get(TIME_FIELD)} | "
            f"Update: {row.get('updated_at')}"
        )


if __name__ == "__main__":
    main()
