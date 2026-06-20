import csv
from collections import Counter, defaultdict
from pathlib import Path

from config import OPEN_STATE_FILE, FINAL_OUTCOMES_FILE


OPEN_FILE = Path(OPEN_STATE_FILE)
FINAL_FILE = Path(FINAL_OUTCOMES_FILE)


def load_csv(path):
    if not path.exists():
        return []

    with path.open("r", newline="") as csvfile:
        return list(csv.DictReader(csvfile))


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except ValueError:
        return default


def calculate_pnl(row):
    entry = safe_float(row.get("entry"))
    last = safe_float(row.get("last_close"))

    if entry is None or last is None or entry <= 0:
        return None

    side = row.get("side", "")

    if side == "SHORT":
        return ((entry - last) / entry) * 100

    return ((last - entry) / entry) * 100


def calculate_stop_distance(row):
    entry = safe_float(row.get("entry"))
    last = safe_float(row.get("last_close"))
    stop_loss = safe_float(row.get("stop_loss"))

    if entry is None or last is None or stop_loss is None:
        return None

    side = row.get("side", "")

    if side == "SHORT":
        total_risk = stop_loss - entry
        remaining_risk = stop_loss - last
    else:
        total_risk = entry - stop_loss
        remaining_risk = last - stop_loss

    if total_risk <= 0:
        return None

    return (remaining_risk / total_risk) * 100


def format_pnl_value(pnl):
    if pnl is None:
        return "N/A"

    return f"{pnl:+.3f}%"


def suggested_action(risk_level):
    actions = {
        "FAIBLE": "CONTINUER",
        "MOYEN": "SURVEILLER",
        "ÉLEVÉ": "RÉDUIRE RISQUE",
        "AUCUN": "ATTENDRE SIGNAL",
        "INCONNU": "VÉRIFIER DONNÉES",
    }

    return actions.get(risk_level, "VÉRIFIER")


def classify_risk(open_rows, pnl_items):
    if not open_rows:
        return "AUCUN", "Aucune position ouverte"

    if not pnl_items:
        return "INCONNU", "Aucun PnL calculable"

    pnl_values = [item["pnl"] for item in pnl_items]
    avg_pnl = sum(pnl_values) / len(pnl_values)
    worst_pnl = min(pnl_values)
    negative_count = sum(1 for pnl in pnl_values if pnl < 0)

    stop_distances = [
        item["stop_distance"]
        for item in pnl_items
        if item["stop_distance"] is not None
    ]

    min_stop_distance = min(stop_distances) if stop_distances else None

    reasons = []

    if len(open_rows) >= 6:
        reasons.append("beaucoup de positions ouvertes")

    if negative_count >= 3:
        reasons.append("plusieurs positions négatives")

    if avg_pnl < 0:
        reasons.append("PnL moyen négatif")

    if worst_pnl <= -0.75:
        reasons.append("pire position sous -0.75%")

    if min_stop_distance is not None and min_stop_distance <= 25:
        reasons.append("une position proche du stop-loss")

    if worst_pnl <= -1.25 or avg_pnl <= -0.50 or (min_stop_distance is not None and min_stop_distance <= 10):
        level = "ÉLEVÉ"
    elif reasons:
        level = "MOYEN"
    else:
        level = "FAIBLE"
        reasons.append("portefeuille ouvert globalement sain")

    return level, "; ".join(reasons)


def main():
    open_rows = load_csv(OPEN_FILE)
    final_rows = load_csv(FINAL_FILE)

    final_counter = Counter(row.get("outcome", "") for row in final_rows)
    open_counter = Counter(row.get("outcome", "") for row in open_rows)

    open_by_symbol = defaultdict(list)
    pnl_items = []

    for row in open_rows:
        symbol = row.get("symbol", "N/A")
        side = row.get("side", "N/A")
        pnl = calculate_pnl(row)
        stop_distance = calculate_stop_distance(row)

        open_by_symbol[symbol].append((side, pnl, stop_distance))

        if pnl is not None:
            pnl_items.append({
                "symbol": symbol,
                "side": side,
                "pnl": pnl,
                "entry": row.get("entry"),
                "last": row.get("last_close"),
                "stop_distance": stop_distance,
            })

    print("=== COMPACT AGENT REPORT ===")
    print()

    print("Finalisés:")
    print(f"- TP: {final_counter.get('TP TOUCHÉ', 0)}")
    print(f"- SL: {final_counter.get('SL TOUCHÉ', 0)}")
    print(f"- Ambigu: {final_counter.get('AMBIGU', 0)}")
    print()

    print("Ouverts:")
    print(f"- Total: {len(open_rows)}")
    print(f"- En cours +: {open_counter.get('EN COURS +', 0)}")
    print(f"- En cours -: {open_counter.get('EN COURS -', 0)}")
    print(f"- En cours neutre/N/A: {open_counter.get('EN COURS', 0)}")
    print()

    if pnl_items:
        pnl_values = [item["pnl"] for item in pnl_items]
        avg_pnl = sum(pnl_values) / len(pnl_values)

        positive_count = sum(1 for pnl in pnl_values if pnl > 0)
        negative_count = sum(1 for pnl in pnl_values if pnl < 0)
        neutral_count = sum(1 for pnl in pnl_values if pnl == 0)

        best = max(pnl_items, key=lambda item: item["pnl"])
        worst = min(pnl_items, key=lambda item: item["pnl"])

        risk_level, risk_reason = classify_risk(open_rows, pnl_items)

        action = suggested_action(risk_level)

        print("Décision rapide:")
        print(
            f"- DÉCISION: {action} | "
            f"Risque {risk_level} | "
            f"PnL moyen {avg_pnl:+.3f}% | "
            f"Meilleur {best['symbol']} {best['side']} {best['pnl']:+.3f}% | "
            f"Pire {worst['symbol']} {worst['side']} {worst['pnl']:+.3f}%"
        )
        print()

        print("Score portefeuille ouvert:")
        print(f"- PnL moyen: {avg_pnl:+.3f}%")
        print(f"- Positions positives: {positive_count}")
        print(f"- Positions négatives: {negative_count}")
        print(f"- Positions neutres: {neutral_count}")
        print(
            f"- Meilleur: {best['symbol']} {best['side']} "
            f"{best['pnl']:+.3f}%"
        )
        print(
            f"- Pire: {worst['symbol']} {worst['side']} "
            f"{worst['pnl']:+.3f}%"
        )
        print()

        print("Alerte risque:")
        print(f"- Niveau: {risk_level}")
        print(f"- Raison: {risk_reason}")
        print(f"- Action suggérée: {action}")
        print()
    else:
        print("Score portefeuille ouvert:")
        print("- Aucun PnL calculable")
        print()

        risk_level, risk_reason = classify_risk(open_rows, pnl_items)
        print("Alerte risque:")
        print(f"- Niveau: {risk_level}")
        print(f"- Raison: {risk_reason}")
        print(f"- Action suggérée: {suggested_action(risk_level)}")
        print()

    print("Détail ouvert par symbole:")

    if not open_by_symbol:
        print("- Aucun signal ouvert")
        return

    for symbol in sorted(open_by_symbol.keys()):
        parts = []

        for side, pnl, stop_distance in open_by_symbol[symbol]:
            if stop_distance is None:
                stop_text = "SL distance N/A"
            else:
                stop_text = f"SL distance {stop_distance:.1f}%"

            parts.append(f"{side} {format_pnl_value(pnl)} ({stop_text})")

        print(f"- {symbol}: {', '.join(parts)}")


if __name__ == "__main__":
    main()
