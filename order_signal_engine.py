import csv
from pathlib import Path
from datetime import datetime, timezone


SIGNALS_FILE = Path("signals_journal.csv")
OPEN_STATE_FILE = Path("open_outcomes_state.csv")
OUTPUT_FILE = Path("order_signals_report.txt")
MAX_SIGNAL_LEVERAGE = 2.0


SIDE_KEYWORDS = {
    "long": "LONG",
    "buy": "LONG",
    "short": "SHORT",
    "sell": "SHORT",
}


def read_csv_rows(path):
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def find_value(row, candidates):
    lower_map = {k.lower(): v for k, v in row.items()}

    for candidate in candidates:
        value = lower_map.get(candidate.lower())
        if value not in [None, ""]:
            return value

    return ""


def normalize_side(value):
    raw = str(value or "").lower()

    for key, side in SIDE_KEYWORDS.items():
        if key in raw:
            return side

    if "long" in raw:
        return "LONG"
    if "short" in raw:
        return "SHORT"

    return "UNKNOWN"


def safe_float(value):
    try:
        if value in [None, ""]:
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def latest_rows_by_symbol_side(rows):
    latest = {}

    for row in rows:
        symbol = find_value(row, ["symbol", "pair", "market"])
        side_raw = find_value(row, ["side", "direction", "signal", "decision"])
        side = normalize_side(side_raw)

        if not symbol or side == "UNKNOWN":
            continue

        key = (symbol.upper(), side)
        latest[key] = row

    return list(latest.values())



def portfolio_risk_mode():
    rows = read_csv_rows(OPEN_STATE_FILE)

    if not rows:
        return "NORMAL", "aucune position ouverte"

    negative = 0
    positive = 0

    for row in rows:
        status = find_value(row, ["status", "state", "outcome"])
        pnl = safe_float(find_value(row, ["pnl_percent", "pnl", "theoretical_pnl_percent"]))

        raw = str(status).lower()
        if "en cours -" in raw:
            negative += 1
        elif "en cours +" in raw:
            positive += 1
        elif pnl is not None:
            if pnl < 0:
                negative += 1
            elif pnl > 0:
                positive += 1

    if negative >= 3:
        return "OBSERVATION", f"{negative} positions ouvertes négatives"

    return "NORMAL", f"{positive} positives / {negative} négatives"

def build_signal_card(row, portfolio_mode="NORMAL", portfolio_reason=""):
    symbol = find_value(row, ["symbol", "pair", "market"]).upper()
    side = normalize_side(find_value(row, ["side", "direction", "signal", "decision"]))

    entry = find_value(row, ["entry", "entry_price", "planned_entry", "price", "last_close"])
    stop_loss = find_value(row, ["stop_loss", "sl", "sl_price", "planned_sl"])
    take_profit = find_value(row, ["take_profit", "tp", "tp_price", "planned_tp"])
    leverage = find_value(row, ["implied_leverage", "leverage", "levier"])
    risk = find_value(row, ["risk_amount", "risk_usdt", "risk", "risk_value"])
    rsi = find_value(row, ["rsi", "rsi14"])
    atr = find_value(row, ["atr", "atr14"])
    decision = find_value(row, ["decision", "signal", "status", "bias"])

    entry_f = safe_float(entry)
    sl_f = safe_float(stop_loss)
    tp_f = safe_float(take_profit)

    rr_text = "N/A"
    if entry_f and sl_f and tp_f:
        risk_distance = abs(entry_f - sl_f)
        reward_distance = abs(tp_f - entry_f)
        if risk_distance > 0:
            rr_text = f"1:{reward_distance / risk_distance:.2f}"

    emoji = "🟢" if side == "LONG" else "🔴" if side == "SHORT" else "⚪"

    confidence = "MOYENNE"
    status = "EXPLOITABLE"

    lev_f = safe_float(leverage)
    if lev_f is not None and lev_f > MAX_SIGNAL_LEVERAGE:
        confidence = "FAIBLE"
        status = "REJETÉ — levier implicite trop élevé"

    if side == "UNKNOWN":
        confidence = "FAIBLE"
        status = "REJETÉ — direction inconnue"

    if portfolio_mode == "OBSERVATION" and status == "EXPLOITABLE":
        confidence = "FAIBLE"
        status = f"OBSERVATION — ne pas augmenter l’exposition ({portfolio_reason})"

    if entry_f is None or sl_f is None or tp_f is None:
        confidence = "FAIBLE"
        status = "REJETÉ — plan incomplet"

    elif rr_text != "N/A" and not rr_text.startswith("1:0") and status == "EXPLOITABLE":
        confidence = "MOYENNE"

    lines = [
        f"{emoji} SIGNAL {side} — {symbol}",
        "",
        f"Entrée théorique : {entry or 'N/A'}",
        f"Stop-loss : {stop_loss or 'N/A'}",
        f"Take-profit : {take_profit or 'N/A'}",
        f"Risque : {risk or 'N/A'}",
        f"R/R : {rr_text}",
        f"Levier implicite : {leverage or 'N/A'}",
        f"RSI : {rsi or 'N/A'}",
        f"ATR : {atr or 'N/A'}",
        f"Confiance : {confidence}",
        f"Filtre sécurité : {status}",
        "",
        f"Décision source : {decision or 'N/A'}",
        "",
        "Statut : PROPOSITION UNIQUEMENT — aucun ordre envoyé.",
    ]

    return "\n".join(lines)


def main():
    rows = read_csv_rows(SIGNALS_FILE)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    report = [
        "=== ORDER SIGNAL ENGINE ===",
        f"Heure : {now}",
        "",
    ]

    if not rows:
        report.append("Aucun signal disponible.")
        report.append("Statut : aucun ordre proposé.")
        text = "\n".join(report)
        OUTPUT_FILE.write_text(text, encoding="utf-8")
        print(text)
        return

    latest = latest_rows_by_symbol_side(rows)

    if not latest:
        report.append("Aucun signal exploitable trouvé dans signals_journal.csv.")
        report.append("Statut : aucun ordre proposé.")
        text = "\n".join(report)
        OUTPUT_FILE.write_text(text, encoding="utf-8")
        print(text)
        return

    portfolio_mode, portfolio_reason = portfolio_risk_mode()

    report.append(f"Signaux exploitables détectés : {len(latest)}")
    report.append(f"Mode portefeuille : {portfolio_mode} — {portfolio_reason}")
    report.append("")

    for row in latest[-6:]:
        report.append(build_signal_card(row, portfolio_mode, portfolio_reason))
        report.append("")
        report.append("---")
        report.append("")

    text = "\n".join(report).strip()
    OUTPUT_FILE.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
