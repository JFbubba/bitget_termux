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


# ---------- cotations MAKER (market making §94) — surface ledger "mm" ----------
# Le module de DÉCISION market_maker.py délègue ici. Caps DÉDIÉS : le notionnel COTÉ
# (placé puis souvent annulé sans fill) n'a pas le même sens que le notionnel ACHETÉ —
# le risque réel du MM est borné côté décision (inventaire max + stop journalier local)
# et côté surface par ces murs (per-quote + total coté/jour, anti-boucle folle).

MM_SURFACE = "mm"
ABS_MM_PER_QUOTE_USDT = 25.0      # mur ABSOLU par cotation
ABS_MM_DAILY_QUOTED_USDT = 2000.0  # mur ABSOLU de notionnel coté par jour


def _decimal(x, decimals=6):
    """Notation DÉCIMALE (jamais scientifique) — Bitget rejette '8.3e-05'."""
    return f"{round(float(x), decimals):.{decimals}f}"


def build_quote_args(symbol, side, usdt, price, oid, price_decimals=2, size_decimals=6):
    """Arguments bgc pour UNE cotation limit POST-ONLY (maker, jamais taker). PUR.
    size en BASE = usdt/price. Retourne None si prix invalide."""
    try:
        px = float(price)
    except (TypeError, ValueError):
        return None
    if px <= 0:
        return None
    order = {"symbol": symbol, "side": side, "orderType": "limit", "force": "post_only",
             "price": _decimal(px, price_decimals), "size": _decimal(float(usdt) / px, size_decimals),
             "clientOid": str(oid)}
    return ["spot", "spot_place_order", "--orders", json.dumps([order])]


def quote(symbol, side, usdt, price, confirm=False, runner=None, live=None, kill=None,
          spent=None, balance=None, price_decimals=2):
    """Cotation maker RÉELLE SI confirm=True ET gardes vertes, sinon DRY. Post-only :
    l'ordre est REJETÉ par l'exchange s'il croiserait le carnet (jamais preneur).
    Verrou surface SPOT_TRADE_LIVE + kill-switch fail-closed + caps mm dédiés."""
    symbol = symbol.upper()
    side = str(side).lower()
    reasons = [] if side in ("buy", "sell") else [f"side invalide '{side}' (buy|sell)"]
    per_op = ex.capped("MM_MAX_PER_QUOTE_USDT", 5.0, ABS_MM_PER_QUOTE_USDT)
    daily = ex.capped("MM_MAX_DAILY_QUOTED_USDT", 400.0, ABS_MM_DAILY_QUOTED_USDT)
    oid = ex.new_oid("mmq")
    args = build_quote_args(symbol, side, usdt, price, oid, price_decimals=price_decimals)
    if args is None:
        reasons.append(f"prix invalide '{price}'")
        args = ["spot", "spot_place_order", "--orders", "[]"]
    ok, reasons = ex.guard(MM_SURFACE, LIVE_FLAG, usdt, per_op, daily,
                           live=live, kill=kill, spent=spent, balance=balance,
                           extra_reasons=reasons)
    return ex.run(args, ok, reasons, MM_SURFACE, usdt, oid, confirm=confirm, runner=runner,
                  meta={"symbol": symbol, "side": side, "maker": True, "price": str(price)})


def build_cancel_args(symbol, order_id=None, cancel_all=False):
    """Arguments bgc pour ANNULER une cotation (ou toutes celles du symbole). PUR.
    Le hub n'accepte QUE orderId/orderIds/cancelAll (pas de clientOid)."""
    base = ["spot", "spot_cancel_orders", "--symbol", symbol]
    if order_id:
        return base + ["--orderId", str(order_id)]
    if cancel_all:
        return base + ["--cancelAll", "true"]
    return None


def cancel(symbol, order_id=None, cancel_all=False, confirm=False, runner=None):
    """Annule une cotation ouverte. Une annulation RETIRE du risque : elle reste possible
    verrou LIVE coupé ET kill-switch actif (fail-safe inverse — pouvoir toujours retirer
    ses cotations du carnet). DRY par défaut : confirm=True requis pour le réel.
    Aucun montant engagé -> pas de caps ; rien n'est journalisé au ledger."""
    symbol = symbol.upper()
    args = build_cancel_args(symbol, order_id=order_id, cancel_all=cancel_all)
    if args is None:
        return {"ok": False, "executed": False,
                "reasons": ["préciser order_id ou cancel_all=True"], "preview": None}
    preview = "bgc " + " ".join(str(a) for a in args)
    if not confirm:
        return {"ok": True, "executed": False, "dry": True, "preview": preview,
                "note": "DRY — relance avec confirm=True pour annuler réellement"}
    out = ex._run_bgc(args, runner=runner)
    return {"ok": True, "executed": ex._ok_response(out), "preview": preview, "response": out}


def open_orders(symbol, runner=None):
    """Cotations spot OUVERTES du symbole (lecture seule via le hub).
    Liste (peut être vide) ; None si illisible (≠ vide : fail-closed chez l'appelant)."""
    try:
        import bitget_hub_bridge as hub
        if runner is not None:
            d = runner(["spot", "spot_get_orders", "--symbol", symbol.upper(), "--status", "open"])
        else:
            d = hub._read(["spot", "spot_get_orders", "--symbol", symbol.upper(), "--status", "open"])
        data = (d or {}).get("data") if isinstance(d, dict) else None
        return data if isinstance(data, list) else None
    except Exception:
        return None


def order_info(symbol, order_id, runner=None):
    """Détail d'une cotation par orderId (lecture seule). Dict ou None si illisible."""
    try:
        import bitget_hub_bridge as hub
        args = ["spot", "spot_get_orders", "--orderId", str(order_id)]
        d = runner(args) if runner is not None else hub._read(args)
        data = (d or {}).get("data") if isinstance(d, dict) else None
        if isinstance(data, list):
            return data[0] if data else None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def kelly_usdt():
    """Taille recommandée par le critère de Kelly, rebornée par le cap/opération spot.
    0 si edge négatif (cas actuel). Retourne (montant, détail_kelly)."""
    import kelly
    per_op = ex.capped("SPOT_TRADE_MAX_PER_OP_USDT", 10.0, ABS_PER_OP_USDT)
    return kelly.recommended_usdt(per_op)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Trading spot borné (achat/vente).")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--side", choices=["buy", "sell"], required=True)
    p.add_argument("--usdt", type=float, default=None, help="notionnel USDT (ou --kelly)")
    p.add_argument("--kelly", action="store_true", help="dimensionne par le critère de Kelly (borné)")
    p.add_argument("--confirm", action="store_true", help="exécute le VRAI ordre (sinon DRY)")
    a = p.parse_args()
    usdt = a.usdt
    if a.kelly or usdt is None:
        usdt, k = kelly_usdt()
        print(f"[Kelly] f={k['f']} (complet {k['f_full']}) -> taille {usdt} USDT · {k['note']}")
    r = execute(a.symbol, a.side, usdt, confirm=a.confirm)
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
