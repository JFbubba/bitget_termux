import csv
import json
from pathlib import Path
from datetime import datetime, timezone

from config import MAX_IMPLIED_LEVERAGE, RISK_PER_TRADE_PERCENT
from account_equity import get_account_equity_usdt
from paper_positions import open_symbol_sides_from_paper


SIGNALS_FILE = Path("signals_journal.csv")
OPEN_STATE_FILE = Path("open_outcomes_state.csv")
PENDING_ORDERS_FILE = Path("pending_orders.json")

MAX_PREORDERS = 5


def read_csv_rows(path):
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def safe_float(value):
    try:
        if value in [None, ""]:
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def find_value(row, candidates):
    lower_map = {k.lower(): v for k, v in row.items()}
    for candidate in candidates:
        value = lower_map.get(candidate.lower())
        if value not in [None, ""]:
            return value
    return ""


def normalize_side(value):
    raw = str(value or "").lower()

    if "long" in raw or "buy" in raw:
        return "LONG"

    if "short" in raw or "sell" in raw:
        return "SHORT"

    return "UNKNOWN"


def get_equity():
    try:
        info = get_account_equity_usdt()

        if isinstance(info, dict):
            equity = info.get("equity") or info.get("equity_usdt") or info.get("value")
            source = info.get("source", "UNKNOWN_DICT")
            return float(equity), source

        if isinstance(info, tuple) and len(info) >= 2:
            return float(info[0]), str(info[1])

        if isinstance(info, (int, float, str)):
            return float(info), "ACCOUNT_EQUITY_VALUE"

        return 100.0, f"FALLBACK_UNSUPPORTED_RETURN_{type(info).__name__}"

    except Exception as exc:
        return 100.0, f"FALLBACK_ERROR_{type(exc).__name__}"


def open_symbol_sides():
    """
    Positions paper réellement ouvertes.

    Important:
    - Ne lit plus open_outcomes_state.csv.
    - open_outcomes_state.csv suit les signaux.
    - paper_positions.json suit les positions paper réellement prises après dry-run.
    """
    return open_symbol_sides_from_paper()

def latest_signal_rows():
    rows = read_csv_rows(SIGNALS_FILE)
    latest = {}

    for row in rows:
        symbol = find_value(row, ["symbol", "pair", "market"]).upper()
        side = normalize_side(find_value(row, ["side", "direction", "signal", "decision"]))

        if not symbol or side == "UNKNOWN":
            continue

        latest[(symbol, side)] = row

    return list(latest.values())


def build_preorder(row, equity, equity_source, opened):
    symbol = find_value(row, ["symbol", "pair", "market"]).upper()
    side = normalize_side(find_value(row, ["side", "direction", "signal", "decision"]))

    decision = find_value(row, ["decision", "signal", "status", "bias"])
    entry = safe_float(find_value(row, ["entry", "entry_price", "planned_entry", "price", "last_close"]))
    stop_loss = safe_float(find_value(row, ["stop_loss", "sl", "sl_price", "planned_sl"]))
    take_profit = safe_float(find_value(row, ["take_profit", "tp", "tp_price", "planned_tp"]))
    leverage = safe_float(find_value(row, ["implied_leverage", "leverage", "levier"]))

    now = datetime.now(timezone.utc)
    order_id = f"{symbol}_{side}_{now.strftime('%Y%m%d_%H%M%S')}"

    reasons = []

    if not symbol:
        reasons.append("symbole manquant")

    if side == "UNKNOWN":
        reasons.append("direction inconnue")

    if entry is None or stop_loss is None or take_profit is None:
        reasons.append("plan incomplet")

    if leverage is None:
        reasons.append("levier implicite manquant")
    elif leverage > MAX_IMPLIED_LEVERAGE:
        reasons.append(f"levier implicite trop élevé ({leverage:.4f}x > {MAX_IMPLIED_LEVERAGE:.2f}x)")

    if (symbol, side) in opened:
        reasons.append("position déjà ouverte dans le même sens")

    if entry is not None and stop_loss is not None:
        sl_distance = abs(entry - stop_loss)
    else:
        sl_distance = None

    if not sl_distance or sl_distance <= 0:
        reasons.append("distance stop-loss invalide")

    risk_usdt = equity * (RISK_PER_TRADE_PERCENT / 100)

    if sl_distance and sl_distance > 0:
        size = risk_usdt / sl_distance
        notional = size * entry
        sl_distance_percent = (sl_distance / entry) * 100
    else:
        size = None
        notional = None
        sl_distance_percent = None

    status = "PENDING_APPROVAL" if not reasons else "REJECTED"

    return {
        "id": order_id,
        "created_at": now.isoformat(),
        "symbol": symbol,
        "side": side,
        "decision_source": decision,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_percent": RISK_PER_TRADE_PERCENT,
        "risk_usdt": round(risk_usdt, 4),
        "size": round(size, 8) if size is not None else None,
        "notional_usdt": round(notional, 4) if notional is not None else None,
        "sl_distance_percent": round(sl_distance_percent, 4) if sl_distance_percent is not None else None,
        "implied_leverage": leverage,
        "max_allowed_leverage": MAX_IMPLIED_LEVERAGE,
        "equity_used": equity,
        "equity_source": equity_source,
        "status": status,
        "reasons": reasons,
        "execution": "LOCKED_NO_REAL_ORDER",
    }


def _apply_portfolio_guards(preorders, opened):
    """Applique le KILL-SWITCH + les caps PORTEFEUILLE agrégés (risk_limits) aux
    pré-ordres : tout pré-ordre hors-cap passe en REJECTED avec ses raisons. PUR côté
    risk_limits, best-effort sur l'état. Réponse à l'audit (caps portefeuille morts)."""
    try:
        import risk_manager
        if risk_manager.kill_switch_active():
            for o in preorders:
                if o.get("status") == "PENDING_APPROVAL":
                    o["status"] = "REJECTED"
                    o.setdefault("reasons", []).append("KILL_SWITCH actif — tout trading arrêté")
            return
    except Exception:
        pass
    try:
        import risk_limits
        import risk_state
        open_count = risk_state.open_positions_count()
        extra = risk_limits.evaluate_portfolio_caps(preorders, open_count, RISK_PER_TRADE_PERCENT)
        for o in preorders:
            reasons = extra.get(o.get("id"))
            if reasons and o.get("status") == "PENDING_APPROVAL":
                o["status"] = "REJECTED"
                o.setdefault("reasons", []).extend(reasons)
    except Exception:
        pass


def main():
    equity, equity_source = get_equity()
    opened = open_symbol_sides()
    rows = latest_signal_rows()

    preorders = []

    for row in rows[-MAX_PREORDERS:]:
        preorders.append(build_preorder(row, equity, equity_source, opened))

    _apply_portfolio_guards(preorders, opened)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PREORDER_ONLY_NO_EXECUTION",
        "count": len(preorders),
        "orders": preorders,
    }

    PENDING_ORDERS_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=== PREORDER ENGINE ===")
    print(f"Fichier: {PENDING_ORDERS_FILE}")
    print(f"Pré-ordres générés: {len(preorders)}")
    print(f"Equity utilisée: {equity} USDT | Source: {equity_source}")
    print()

    accepted = [o for o in preorders if o["status"] == "PENDING_APPROVAL"]
    rejected = [o for o in preorders if o["status"] == "REJECTED"]

    print(f"En attente validation: {len(accepted)}")
    print(f"Rejetés: {len(rejected)}")
    print()

    for order in preorders:
        print(f"{order['id']} | {order['status']} | {order['symbol']} {order['side']} | Notionnel: {order['notional_usdt']} USDT | Risque: {order['risk_usdt']} USDT")
        if order["reasons"]:
            print("  Raisons:", "; ".join(order["reasons"]))


if __name__ == "__main__":
    main()
