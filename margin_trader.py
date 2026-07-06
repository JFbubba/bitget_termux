"""
margin_trader.py — EXÉCUTION RÉELLE bornée : trading MARGE (isolée ET croisée).

⚠️ MODULE D'EXÉCUTION AUTORISÉ. Ouvre/ferme des positions marge + emprunte/rembourse,
BORNÉ par caps durs + verrou LIVE `MARGIN_TRADE_LIVE` (défaut OFF) + kill-switch.
Jamais de retrait, jamais de virement.

Gardes (via bitget_execute) : verrou LIVE OFF par défaut · kill-switch fail-closed ·
plafond notionnel/opération + journalier (env relève SOUS le mur absolu) · levier borné ·
DRY par défaut. Retrait : INTERDIT.

CLI :
  python margin_trader.py order --type crossed --symbol BTCUSDT --side buy --usdt 10 [--confirm]
  python margin_trader.py borrow --type isolated --coin USDT --usdt 10 [--confirm]
  python margin_trader.py repay  --type isolated --coin USDT --usdt 10 [--confirm]
"""
import json

import bitget_execute as ex

LIVE_FLAG = "MARGIN_TRADE_LIVE"
SURFACE = "margin"
ABS_PER_OP_USDT = 200.0     # mur dur notionnel par opération
ABS_DAILY_USDT = 500.0      # mur dur notionnel journalier
ABS_MAX_LEVERAGE = 5.0      # mur dur de levier (jamais dépassé)
MARGIN_TYPES = ("crossed", "isolated")


def _price(symbol):
    try:
        import bitget_market_data as bmd
        return (bmd.mark_prices() or {}).get(symbol)
    except Exception:
        return None


def _caps():
    return (ex.capped("MARGIN_MAX_PER_OP_USDT", 10.0, ABS_PER_OP_USDT),
            ex.capped("MARGIN_MAX_DAILY_USDT", 50.0, ABS_DAILY_USDT))


def _check_type(margin_type):
    return [] if margin_type in MARGIN_TYPES else [f"marginType invalide '{margin_type}' (crossed|isolated)"]


def build_order_args(margin_type, symbol, side, usdt, oid, price=None):
    """Ordre marge marché borné. Taille BASE = usdt/price. PUR."""
    size = str(usdt) if not price else f"{round(float(usdt) / float(price), 6):.6f}"
    return ["margin", "margin_place_order", "--marginType", margin_type, "--symbol", symbol,
            "--side", side, "--orderType", "market", "--size", size, "--clientOid", str(oid)]


def order(symbol, side, usdt, margin_type="crossed", confirm=False, runner=None,
          live=None, kill=None, spent=None):
    """Ouvre/ferme une position marge (achat/vente) bornée. DRY par défaut."""
    symbol, side, margin_type = symbol.upper(), str(side).lower(), str(margin_type).lower()
    extra = _check_type(margin_type) + ([] if side in ("buy", "sell") else [f"side invalide '{side}'"])
    per_op, daily = _caps()
    ok, reasons = ex.guard(SURFACE, LIVE_FLAG, usdt, per_op, daily,
                           live=live, kill=kill, spent=spent, extra_reasons=extra)
    oid = ex.new_oid("mgn")
    args = build_order_args(margin_type, symbol, side, usdt, oid, price=_price(symbol))
    return ex.run(args, ok, reasons, SURFACE, usdt, oid, confirm=confirm, runner=runner,
                  meta={"symbol": symbol, "side": side, "margin_type": margin_type})


def _loan(action, margin_type, coin, usdt, confirm=False, runner=None, live=None, kill=None, spent=None):
    """Emprunt (borrow) ou remboursement (repay) borné par les mêmes caps notionnels."""
    margin_type = str(margin_type).lower()
    extra = _check_type(margin_type)
    per_op, daily = _caps()
    ok, reasons = ex.guard(SURFACE, LIVE_FLAG, usdt, per_op, daily,
                           live=live, kill=kill, spent=spent, extra_reasons=extra)
    oid = ex.new_oid("mgl")
    tool = "margin_borrow" if action == "borrow" else "margin_repay"
    args = ["margin", tool, "--marginType", margin_type, "--coin", coin.upper(), "--amount", str(usdt)]
    return ex.run(args, ok, reasons, SURFACE, usdt, oid, confirm=confirm, runner=runner,
                  meta={"coin": coin.upper(), "action": action, "margin_type": margin_type})


def borrow(coin, usdt, margin_type="crossed", **kw):
    return _loan("borrow", margin_type, coin, usdt, **kw)


def repay(coin, usdt, margin_type="crossed", **kw):
    return _loan("repay", margin_type, coin, usdt, **kw)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Trading marge borné (isolée/croisée).")
    sub = p.add_subparsers(dest="cmd", required=True)
    po = sub.add_parser("order"); po.add_argument("--type", default="crossed"); po.add_argument("--symbol", default="BTCUSDT")
    po.add_argument("--side", choices=["buy", "sell"], required=True); po.add_argument("--usdt", type=float, default=None)
    po.add_argument("--kelly", action="store_true", help="dimensionne par Kelly (borné)")
    po.add_argument("--confirm", action="store_true")
    for name in ("borrow", "repay"):
        sp = sub.add_parser(name); sp.add_argument("--type", default="crossed"); sp.add_argument("--coin", default="USDT")
        sp.add_argument("--usdt", type=float, required=True); sp.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    if a.cmd == "order":
        usdt = a.usdt
        if getattr(a, "kelly", False) or usdt is None:
            import kelly
            usdt, k = kelly.recommended_usdt(ex.capped("MARGIN_MAX_PER_OP_USDT", 10.0, ABS_PER_OP_USDT))
            print(f"[Kelly] f={k['f']} -> taille {usdt} USDT · {k['note']}")
        r = order(a.symbol, a.side, usdt, margin_type=a.type, confirm=a.confirm)
    else:
        r = (borrow if a.cmd == "borrow" else repay)(a.coin, a.usdt, margin_type=a.type, confirm=a.confirm)
    print("=== MARGIN TRADER (borné) ===")
    print("Commande :", r.get("preview"))
    print(("REFUSÉ : " + " ; ".join(r.get("reasons", []))) if not r.get("ok")
          else ("DRY — aucun ordre. " + r.get("note", "")) if r.get("dry")
          else ("✅ RÉEL exécuté : " + str(r.get("clientOid"))) if r.get("executed")
          else ("⚠️ échec : " + str(r.get("response"))))


if __name__ == "__main__":
    main()
