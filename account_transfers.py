"""
account_transfers.py — EXÉCUTION RÉELLE bornée : virements INTERNES entre comptes.

⚠️ MODULE D'EXÉCUTION AUTORISÉ. Déplace des fonds ENTRE tes propres comptes Bitget
(spot ↔ futures ↔ marge ↔ earn), BORNÉ par caps durs + verrou LIVE `TRANSFER_LIVE`
(défaut OFF) + kill-switch + allowlist de comptes. JAMAIS de retrait vers une adresse
externe (interdit par conception ; clé Trade-only de toute façon).

Gardes (via bitget_execute) : verrou LIVE OFF par défaut · kill-switch fail-closed ·
plafond/opération + journalier · comptes source/destination dans l'allowlist INTERNE ·
DRY par défaut.

CLI : python account_transfers.py --from spot --to futures_usdt --coin USDT --usdt 10 [--confirm]
"""
import bitget_execute as ex

LIVE_FLAG = "TRANSFER_LIVE"
SURFACE = "transfer"
ABS_PER_OP_USDT = 500.0
ABS_DAILY_USDT = 1000.0
# Comptes INTERNES autorisés (aucune destination externe possible). Extensible via config
# TRANSFER_ALLOWED_ACCOUNTS. Un type inconnu est REFUSÉ (fail-closed).
ALLOWED_ACCOUNTS = {"spot", "futures_usdt", "futures_coin", "usdt_futures", "coin_futures",
                    "margin_crossed", "margin_isolated", "isolated_margin", "crossed_margin",
                    "p2p", "earn"}


def _allowed():
    import os
    extra = str(os.getenv("TRANSFER_ALLOWED_ACCOUNTS", "") or ex._cfg("TRANSFER_ALLOWED_ACCOUNTS", "")).strip()
    base = set(ALLOWED_ACCOUNTS)
    if extra:
        base |= {s.strip().lower() for s in extra.split(",") if s.strip()}
    return base


def build_args(from_acct, to_acct, coin, usdt, oid):
    return ["account", "transfer", "--fromAccountType", from_acct, "--toAccountType", to_acct,
            "--coin", coin.upper(), "--amount", str(usdt), "--clientOid", str(oid)]


def execute(from_acct, to_acct, coin, usdt, confirm=False, runner=None, live=None, kill=None, spent=None):
    """Virement interne RÉEL SI confirm=True ET gardes vertes. Sinon DRY."""
    from_acct, to_acct = str(from_acct).lower(), str(to_acct).lower()
    allow = _allowed()
    extra = []
    if from_acct not in allow:
        extra.append(f"compte source '{from_acct}' hors allowlist interne")
    if to_acct not in allow:
        extra.append(f"compte destination '{to_acct}' hors allowlist interne")
    if from_acct == to_acct:
        extra.append("source = destination (virement inutile)")
    per_op = ex.capped("TRANSFER_MAX_PER_OP_USDT", 25.0, ABS_PER_OP_USDT)
    daily = ex.capped("TRANSFER_MAX_DAILY_USDT", 100.0, ABS_DAILY_USDT)
    ok, reasons = ex.guard(SURFACE, LIVE_FLAG, usdt, per_op, daily,
                           live=live, kill=kill, spent=spent, extra_reasons=extra)
    oid = ex.new_oid("trf")
    args = build_args(from_acct, to_acct, coin, usdt, oid)
    return ex.run(args, ok, reasons, SURFACE, usdt, oid, confirm=confirm, runner=runner,
                  meta={"from": from_acct, "to": to_acct, "coin": coin.upper()})


def main():
    import argparse
    p = argparse.ArgumentParser(description="Virements internes bornés (aucun retrait externe).")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.add_argument("--coin", default="USDT")
    p.add_argument("--usdt", type=float, required=True)
    p.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    r = execute(a.src, a.dst, a.coin, a.usdt, confirm=a.confirm)
    print("=== VIREMENT INTERNE (borné) ===")
    print("Commande :", r.get("preview"))
    print(("REFUSÉ : " + " ; ".join(r.get("reasons", []))) if not r.get("ok")
          else ("DRY — aucun mouvement. " + r.get("note", "")) if r.get("dry")
          else ("✅ RÉEL exécuté : " + str(r.get("clientOid"))) if r.get("executed")
          else ("⚠️ échec : " + str(r.get("response"))))


if __name__ == "__main__":
    main()
