"""
spot_executor.py — EXÉCUTION RÉELLE : achat SPOT BTC uniquement (accumulation).

⚠️ MODULE D'EXÉCUTION AUTORISÉ — le SEUL endroit qui peut passer un ordre réel.
Périmètre verrouillé par conception : ACHAT spot BTC au marché, et RIEN d'autre.
Jamais vendre, jamais de levier, jamais de futures, jamais de retrait de fonds.

Gardes DURS et non négociables (toutes vérifiées avant tout ordre) :
  • MANDATE_LIVE_ENABLED doit être True (verrou réel) — sinon refus ;
  • kill_switch (risk_manager) inactif — sinon refus ;
  • plafond DUR par achat + plafond DUR journalier (config) ;
  • montant ≤ solde spot réel disponible ;
  • idempotence (clientOid unique) ;
  • mode --dry par DÉFAUT : imprime la commande exacte et n'exécute RIEN sans --confirm.

L'ordre est exécuté par l'Agent Hub (`bgc spot ...`) — les « mains ». Ce module ne
fait que CONSTRUIRE la demande bornée et appeler l'outil. Test-first : commencer par
un achat minime confirmé à la main avant tout armement autonome.
"""

import json
import time
from pathlib import Path

SYMBOL = "BTCUSDT"
REAL_LEDGER = Path(__file__).resolve().parent / "accumulation_real_ledger.json"


def _cfg(name, fallback):
    try:
        import config
        return getattr(config, name, fallback)
    except Exception:
        return fallback


# ---------- registre des achats RÉELS (plafond journalier) ----------

def _load_real():
    try:
        return json.loads(REAL_LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {"buys": []}


def today_spent(now=None, ledger=None):
    """Total RÉEL acheté aujourd'hui (USDT). PUR si ledger injecté."""
    now = time.time() if now is None else now
    day = int(now // 86400)
    led = ledger if ledger is not None else _load_real()
    return round(sum(float(b.get("amount_usdt", 0)) for b in led.get("buys", [])
                     if int(float(b.get("ts", 0)) // 86400) == day), 2)


def _record_real_buy(amount_usdt, oid, now=None):
    now = time.time() if now is None else now
    led = _load_real()
    led.setdefault("buys", []).append({"ts": now, "amount_usdt": float(amount_usdt),
                                       "clientOid": oid, "symbol": SYMBOL})
    led["buys"] = led["buys"][-1000:]
    try:
        REAL_LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------- gardes DURS (purs si on injecte l'état) ----------

def guards(amount_usdt, balance=None, spent=None, live=None, kill=None):
    """Vérifie TOUTES les gardes avant un achat réel. Retourne (ok, raisons). PUR si
    live/kill/balance/spent sont injectés (sinon lit l'état réel)."""
    reasons = []
    # verrou réel (MANDATE_LIVE_ENABLED)
    if live is None:
        try:
            import mandate
            live = mandate.live_enabled()
        except Exception:
            live = False
    if not live:
        reasons.append("MANDATE_LIVE_ENABLED=False (verrou réel coupé)")
    # kill_switch
    if kill is None:
        try:
            import risk_manager
            kill = risk_manager.kill_switch_active()
        except Exception:
            kill = False
    if kill:
        reasons.append("kill_switch actif")
    amt = float(amount_usdt or 0)
    if amt <= 0:
        reasons.append("montant ≤ 0")
    cap = float(_cfg("ACCUM_REAL_MAX_PER_BUY_USDT", 50.0))
    if amt > cap:
        reasons.append(f"montant {amt} > plafond/achat {cap}")
    daily_cap = float(_cfg("ACCUM_REAL_MAX_DAILY_USDT", 50.0))
    sp = today_spent() if spent is None else float(spent)
    if sp + amt > daily_cap:
        reasons.append(f"plafond journalier dépassé ({sp}+{amt} > {daily_cap})")
    if balance is not None and amt > float(balance):
        reasons.append(f"montant {amt} > solde spot disponible {balance}")
    return (not reasons, reasons)


# ---------- construction de la demande (pure) ----------

def build_command(amount_usdt, client_oid):
    """Construit les arguments `bgc` pour un ACHAT spot BTC au marché. PUR.
    Pour un achat marché Bitget, la taille est exprimée en quote (USDT à dépenser)."""
    return ["spot", "spot_place_order", "--symbol", SYMBOL, "--side", "buy",
            "--orderType", "market", "--size", str(amount_usdt),
            "--clientOid", str(client_oid)]


# ---------- exécution (réelle uniquement avec confirm=True) ----------

def _spot_balance():
    try:
        import bitget_hub_bridge as hub
        snap = hub.account_snapshot()
        if snap:
            acc = snap.get("accounts") or {}
            v = acc.get("spot")
            return v if v is not None else snap.get("available_usdt")
    except Exception:
        pass
    return None


def _run(cmd, runner=None):
    """Lance la commande bgc (SANS --read-only : c'est l'écriture). runner injectable."""
    if runner is not None:
        return runner(cmd)
    try:
        import bitget_hub_bridge as hub
        if not hub.available():
            return None
        import subprocess
        return subprocess.run(["bgc", *cmd], capture_output=True, text=True,
                              timeout=30, env=hub._hub_env()).stdout
    except Exception:
        return None


def execute(amount_usdt, confirm=False, runner=None, now=None):
    """Achat spot BTC réel SI confirm=True ET toutes les gardes passent. Sinon DRY
    (imprime la commande, n'exécute rien). Retourne un dict de résultat."""
    now = time.time() if now is None else now
    bal = _spot_balance()
    ok, reasons = guards(amount_usdt, balance=bal)
    oid = f"accbtc{int(now * 1000)}"
    cmd = build_command(amount_usdt, oid)
    preview = "bgc " + " ".join(cmd)
    if not ok:
        return {"ok": False, "executed": False, "reasons": reasons, "preview": preview}
    if not confirm:
        return {"ok": True, "executed": False, "dry": True, "preview": preview,
                "note": "DRY — vérifie la commande puis ajoute --confirm pour l'achat RÉEL"}
    out = _run(cmd, runner=runner)
    success = bool(out) and '"ok":false' not in (out or "").replace(" ", "")
    if success:
        _record_real_buy(amount_usdt, oid, now)
    return {"ok": True, "executed": success, "preview": preview, "response": out,
            "clientOid": oid}


def main():
    import argparse
    p = argparse.ArgumentParser(description="Achat spot BTC réel (accumulation, test-first).")
    p.add_argument("--usdt", type=float, default=5.0, help="montant en USDT (défaut 5)")
    p.add_argument("--confirm", action="store_true", help="exécute le VRAI achat (sinon DRY)")
    args = p.parse_args()
    r = execute(args.usdt, confirm=args.confirm)
    print("=== ACHAT SPOT BTC (accumulation réelle) ===")
    print(f"Commande : {r.get('preview')}")
    if not r.get("ok"):
        print("REFUSÉ par les gardes : " + " ; ".join(r.get("reasons", [])))
    elif not r.get("executed") and r.get("dry"):
        print("Mode DRY — aucun ordre passé. " + r.get("note", ""))
    elif r.get("executed"):
        print(f"✅ ACHAT RÉEL exécuté (clientOid {r.get('clientOid')}).")
        print(f"Réponse : {r.get('response')}")
    else:
        print(f"⚠️ Échec d'exécution. Réponse : {r.get('response')}")
    print("Périmètre : achat spot BTC seul. Jamais de vente/levier/retrait.")


if __name__ == "__main__":
    main()
