"""
spot_trader.py — EXÉCUTION RÉELLE bornée : trading SPOT libre (achat ET vente).

⚠️ MODULE D'EXÉCUTION AUTORISÉ (distinct de spot_executor.py qui, lui, reste limité à
l'accumulation BTC ≤5 $/j). Ici : achat/vente spot sur l'univers, BORNÉ par des caps
durs et le verrou LIVE `SPOT_TRADE_LIVE` (défaut OFF). Jamais de retrait.

Gardes (via bitget_execute) : verrou LIVE OFF par défaut · kill-switch fail-closed ·
plafond/opération + plafond journalier (env peut relever SOUS le mur absolu) · DRY par
défaut (confirm=True requis pour le réel). Retrait de fonds : INTERDIT (hors périmètre).

CLI : python spot_trader.py --symbol BTCUSDT --side buy --usdt 5   [--confirm]
"""
import json

import bitget_execute as ex

LIVE_FLAG = "SPOT_TRADE_LIVE"
SURFACE = "spot"
# Murs ABSOLUS en dur (tier ceiling) — env/config peuvent ABAISSER, jamais dépasser.
ABS_PER_OP_USDT = 200.0
ABS_DAILY_USDT = 500.0


def _price(symbol):
    """Dernier prix spot (lecture seule, best-effort None)."""
    try:
        import bitget_market_data as bmd
        return (bmd.mark_prices() or {}).get(symbol)
    except Exception:
        return None


def _spot_free(coin):
    """Solde spot LIBRE d'un coin (best-effort None)."""
    try:
        import bitget_balance_reader as br
        for row in (br.get_spot_assets(coin).get("data") or []):
            if str(row.get("coin", "")).upper() == coin.upper():
                return float(row.get("available"))
    except Exception:
        pass
    return None


def _base_size(symbol, side, usdt, price):
    """Taille de l'ordre. Achat marché : size = USDT (quote) dépensés. Vente marché :
    size = quantité BASE = usdt/price. Notation décimale (jamais scientifique)."""
    if side == "buy":
        return str(usdt)
    if not price:
        return None
    return f"{round(float(usdt) / float(price), 6):.6f}"


def build_args(symbol, side, usdt, oid, price=None):
    """Arguments bgc pour un ordre spot marché borné. PUR."""
    size = _base_size(symbol, side, usdt, price)
    order = {"symbol": symbol, "side": side, "orderType": "market",
             "size": size, "clientOid": str(oid)}
    return ["spot", "spot_place_order", "--orders", json.dumps([order])]


def execute(symbol, side, usdt, confirm=False, runner=None, live=None, kill=None, spent=None, balance=None):
    """Achat/vente spot RÉEL SI confirm=True ET gardes vertes. Sinon DRY. `usdt` = notionnel
    (base des caps). Retourne le dict de résultat homogène du noyau."""
    symbol = symbol.upper()
    side = str(side).lower()
    reasons = [] if side in ("buy", "sell") else [f"side invalide '{side}' (buy|sell)"]
    per_op = ex.capped("SPOT_TRADE_MAX_PER_OP_USDT", 10.0, ABS_PER_OP_USDT)
    daily = ex.capped("SPOT_TRADE_MAX_DAILY_USDT", 50.0, ABS_DAILY_USDT)
    price = _price(symbol)
    ok, reasons = ex.guard(SURFACE, LIVE_FLAG, usdt, per_op, daily,
                           live=live, kill=kill, spent=spent, balance=balance, extra_reasons=reasons)
    oid = ex.new_oid("spt")
    args = build_args(symbol, side, usdt, oid, price=price)
    return ex.run(args, ok, reasons, SURFACE, usdt, oid, confirm=confirm, runner=runner,
                  meta={"symbol": symbol, "side": side})


def main():
    import argparse
    p = argparse.ArgumentParser(description="Trading spot borné (achat/vente).")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--side", choices=["buy", "sell"], required=True)
    p.add_argument("--usdt", type=float, required=True, help="notionnel USDT")
    p.add_argument("--confirm", action="store_true", help="exécute le VRAI ordre (sinon DRY)")
    a = p.parse_args()
    r = execute(a.symbol, a.side, a.usdt, confirm=a.confirm)
    print("=== SPOT TRADER (borné) ===")
    print("Commande :", r.get("preview"))
    if not r.get("ok"):
        print("REFUSÉ :", " ; ".join(r.get("reasons", [])))
    elif r.get("dry"):
        print("DRY — aucun ordre. " + r.get("note", ""))
    elif r.get("executed"):
        print("✅ ordre RÉEL exécuté :", r.get("clientOid"), "·", r.get("response"))
    else:
        print("⚠️ échec :", r.get("response"))


if __name__ == "__main__":
    main()
