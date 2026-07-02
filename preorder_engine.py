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


from csv_utils import read_csv_rows, find_value
from numeric_utils import safe_float as _safe_float


def safe_float(value):
    # tolérance virgule décimale conservée (journaux potentiellement localisés).
    return _safe_float(value, decimal_comma=True)


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


def brain_adjustment(side, bias, conviction, oppose_floor=0.3, min_factor=0.4):
    """Module un pré-ordre par le biais du CERVEAU (essaim). PUR, testable.
      • s'OPPOSE avec conviction ≥ oppose_floor -> GATE (rejet) ;
      • d'ACCORD -> facteur de taille croissant avec la conviction ∈ [min_factor, 1] ;
      • NEUTRE / opposition faible -> taille réduite (0.6).
    NE PEUT QUE réduire la taille, jamais l'augmenter. Retourne (action, factor, note).
    action ∈ {'scale', 'gate'}."""
    b, s = str(bias).upper(), str(side).upper()
    c = max(0.0, min(1.0, float(conviction or 0)))
    agree = (s == "LONG" and b == "LONG") or (s == "SHORT" and b == "SHORT")
    oppose = (s == "LONG" and b == "SHORT") or (s == "SHORT" and b == "LONG")
    if oppose and c >= oppose_floor:
        return ("gate", 0.0, f"cerveau s'oppose (bias {b}, conv {c:.2f})")
    if agree:
        return ("scale", max(min_factor, min(1.0, min_factor + (1 - min_factor) * c)),
                f"cerveau d'accord (conv {c:.2f})")
    return ("scale", 0.6, f"cerveau neutre/faible (bias {b}, conv {c:.2f})")


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

    # CERVEAU (essaim, 13 agents) en GATE + MULTIPLICATEUR de taille. Fail-safe NEUTRE :
    # si le cerveau s'oppose au signal -> rejet ; sinon il REDUIT la taille selon la
    # conviction (jamais ne l'augmente). Indisponible -> facteur 1.0 (aucun changement).
    brain_bias, brain_conv, brain_note, brain_factor = None, None, None, 1.0
    if side in ("LONG", "SHORT") and size is not None:
        try:
            import swarm_brain
            r = swarm_brain.peek(symbol)
            brain_bias = r.get("bias", "NEUTRE")
            brain_conv = round(float(r.get("adjusted_conviction", r.get("conviction", 0)) or 0), 3)
            action, brain_factor, brain_note = brain_adjustment(side, brain_bias, brain_conv)
            if action == "gate":
                reasons.append("cerveau: " + brain_note)
                brain_factor = 1.0
        except Exception:
            brain_factor = 1.0                       # fail-safe NEUTRE
    if brain_factor != 1.0 and size is not None:
        size *= brain_factor
        notional *= brain_factor
        risk_usdt *= brain_factor

    # VOL-TARGETING (mandate) : plafond de levier AUTO-IMPOSE = levier vise selon la
    # conviction de l'essaim ET la vol conditionnelle (GARCH), borne par le mur dur.
    # Effet : risk-off automatique quand la vol monte (le levier autorise baisse) ;
    # un levier implicite au-dessus de ce plafond passe en REJECTED. Best-effort (paper).
    vol_target_lev = None
    if leverage is not None and side in ("LONG", "SHORT"):
        try:
            import market_sources as _ms
            import mandate as _mdt
            _closes = _ms.closes(symbol, limit=120) or []
            _conv = brain_conv if brain_conv is not None else 0.0
            if _closes:
                vol_target_lev = _mdt.leverage_for(_conv, _closes)
                if leverage > vol_target_lev:
                    reasons.append(
                        f"levier implicite {leverage:.2f}x > plafond vol-target "
                        f"{vol_target_lev:.2f}x (conviction {_conv:.2f}, vol elevee -> risk-off)")
        except Exception:
            vol_target_lev = None

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
        "risk_percent": round(RISK_PER_TRADE_PERCENT * brain_factor, 4),
        "risk_usdt": round(risk_usdt, 4),
        "size": round(size, 8) if size is not None else None,
        "notional_usdt": round(notional, 4) if notional is not None else None,
        "sl_distance_percent": round(sl_distance_percent, 4) if sl_distance_percent is not None else None,
        "implied_leverage": leverage,
        "max_allowed_leverage": MAX_IMPLIED_LEVERAGE,
        "vol_target_leverage": round(vol_target_lev, 2) if vol_target_lev is not None else None,
        "brain_bias": brain_bias,
        "brain_conviction": brain_conv,
        "brain_size_factor": round(brain_factor, 3),
        "brain_note": brain_note,
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
    # Halte DRAWDOWN (MDD) : si le drawdown realise (courbe d'equity paper) depasse le
    # seuil tolere (mandate, defaut 20%), on coupe TOUT nouveau risque -- comme le
    # kill-switch. Branche drawdown_halt() qui etait code mais sans courbe a manger.
    try:
        import equity_curve
        _dd = equity_curve.drawdown_state()
        if _dd.get("halt"):
            for o in preorders:
                if o.get("status") == "PENDING_APPROVAL":
                    o["status"] = "REJECTED"
                    o.setdefault("reasons", []).append(
                        f"halte drawdown : MDD {_dd['dd_pct']:.1f}% >= seuil tolere (risk-off)")
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
