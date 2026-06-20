import json
from pathlib import Path

PAPER_POSITIONS_FILE = Path("paper_positions.json")
PAPER_JOURNAL_FILE = Path("paper_positions_journal.jsonl")


def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def main():
    print("=== PAPER REPORT ===")
    print("Mode: PAPER_ONLY_NO_REAL_ORDER")
    print("Aucun ordre réel envoyé.")
    print()

    payload = load_json(PAPER_POSITIONS_FILE)

    if not payload:
        print("Positions paper ouvertes: 0")
    elif "error" in payload:
        print(f"Erreur lecture paper_positions.json: {payload['error']}")
    else:
        positions = payload.get("positions", [])
        opened = [p for p in positions if p.get("status") == "OPEN"]
        closed = [p for p in positions if p.get("status") != "OPEN"]

        print(f"Positions paper totales: {len(positions)}")
        print(f"Positions paper ouvertes: {len(opened)}")
        print(f"Positions paper fermées: {len(closed)}")
        print()

        if opened:
            print("Ouvertes:")
            for p in opened:
                print(
                    f"- {p.get('symbol')} {p.get('side')} | "
                    f"Entry: {p.get('entry')} | "
                    f"SL: {p.get('stop_loss')} | "
                    f"TP: {p.get('take_profit')} | "
                    f"Source: {p.get('source_order_id')}"
                )
        else:
            print("Aucune position paper ouverte.")

    print()
    print("Dernières fermetures paper:")

    if not PAPER_JOURNAL_FILE.exists():
        print("- aucune fermeture paper journalisée")
        return

    lines = PAPER_JOURNAL_FILE.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines()

    if not lines:
        print("- journal vide")
        return

    for line in lines[-5:]:
        try:
            event = json.loads(line)
            print(
                f"- {event.get('timestamp')} | "
                f"{event.get('symbol')} {event.get('side')} | "
                f"{event.get('action')} | "
                f"{event.get('reason')}"
            )
        except Exception:
            print(f"- {line[:300]}")


if __name__ == "__main__":
    main()
