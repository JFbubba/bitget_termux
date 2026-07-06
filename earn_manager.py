"""
earn_manager.py — EXÉCUTION RÉELLE bornée : Earn (souscription / rachat).

⚠️ MODULE D'EXÉCUTION AUTORISÉ. Souscrit/rachète des produits Earn (épargne/staking),
BORNÉ par caps durs + verrou LIVE `EARN_LIVE` (défaut OFF) + kill-switch. Jamais de
retrait externe.

Gardes (via bitget_execute) : verrou LIVE OFF par défaut · kill-switch fail-closed ·
plafond/opération + journalier · action ∈ {subscribe, redeem} · DRY par défaut.

CLI :
  python earn_manager.py products --coin USDT            (lecture seule)
  python earn_manager.py subscribe --product <id> --coin USDT --usdt 10 [--confirm]
  python earn_manager.py redeem    --product <id> --coin USDT --usdt 10 [--confirm]
"""
import bitget_execute as ex

LIVE_FLAG = "EARN_LIVE"
SURFACE = "earn"
ABS_PER_OP_USDT = 500.0
ABS_DAILY_USDT = 1000.0
ACTIONS = ("subscribe", "redeem")


def products(coin=None, product_type=None):
    """Produits Earn disponibles (LECTURE SEULE via l'Agent Hub). [] best-effort."""
    try:
        import bitget_hub_bridge as hub
        args = ["earn", "earn_get_products"]
        if coin:
            args += ["--coin", coin.upper()]
        if product_type:
            args += ["--productType", product_type]
        d = hub._read(args)
        return (d or {}).get("data") if isinstance(d, dict) else []
    except Exception:
        return []


def build_args(action, product_id, coin, usdt):
    return ["earn", "earn_subscribe_redeem", "--action", action, "--productId", str(product_id),
            "--amount", str(usdt), "--coin", coin.upper()]


def execute(action, product_id, coin, usdt, confirm=False, runner=None, live=None, kill=None, spent=None):
    """Souscription/rachat Earn RÉEL SI confirm=True ET gardes vertes. Sinon DRY."""
    action = str(action).lower()
    extra = [] if action in ACTIONS else [f"action invalide '{action}' (subscribe|redeem)"]
    if not product_id:
        extra.append("productId manquant")
    per_op = ex.capped("EARN_MAX_PER_OP_USDT", 25.0, ABS_PER_OP_USDT)
    daily = ex.capped("EARN_MAX_DAILY_USDT", 100.0, ABS_DAILY_USDT)
    ok, reasons = ex.guard(SURFACE, LIVE_FLAG, usdt, per_op, daily,
                           live=live, kill=kill, spent=spent, extra_reasons=extra)
    oid = ex.new_oid("ern")
    args = build_args(action, product_id, coin, usdt)
    return ex.run(args, ok, reasons, SURFACE, usdt, oid, confirm=confirm, runner=runner,
                  meta={"action": action, "product_id": str(product_id), "coin": coin.upper()})


def main():
    import argparse
    import json
    p = argparse.ArgumentParser(description="Gestion Earn bornée.")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("products"); pr.add_argument("--coin", default=None)
    for name in ACTIONS:
        sp = sub.add_parser(name); sp.add_argument("--product", required=True); sp.add_argument("--coin", default="USDT")
        sp.add_argument("--usdt", type=float, required=True); sp.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    if a.cmd == "products":
        print(json.dumps(products(a.coin), indent=2, ensure_ascii=False)[:2000])
        return
    r = execute(a.cmd, a.product, a.coin, a.usdt, confirm=a.confirm)
    print("=== EARN MANAGER (borné) ===")
    print("Commande :", r.get("preview"))
    print(("REFUSÉ : " + " ; ".join(r.get("reasons", []))) if not r.get("ok")
          else ("DRY — aucun mouvement. " + r.get("note", "")) if r.get("dry")
          else ("✅ RÉEL exécuté : " + str(r.get("clientOid"))) if r.get("executed")
          else ("⚠️ échec : " + str(r.get("response"))))


if __name__ == "__main__":
    main()
