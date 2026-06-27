"""
futures_executor.py — EXÉCUTION FUTURES (DRY-RUN strict). Étape 1 de RESEARCH_NOTES §34.

⚠️ 2e module d'exécution, destiné à devenir le SEUL endroit autorisé à passer un ordre
FUTURES réel BORNÉ. À l'ÉTAPE 1 il reste 100 % DRY-RUN : il CONSTRUIT et JOURNALISE une
demande bornée, mais le chemin réel n'est PAS câblé (lève NotImplementedError). Aucun
ordre futures réel ne peut partir tant que les TROIS conditions ne sont pas réunies :
  • un agent réellement éligible LIVE (mandate.futures_live_allowed — porte d'edge), ET
  • le DOUBLE verrou armé (MANDATE_LIVE_ENABLED ET FUTURES_AUTONOMOUS_LIVE), ET
  • le chemin réel implémenté (étape 2, sous GO explicite du propriétaire).

Périmètre BORNÉ par conception (calqué sur spot_executor.py / §31) :
  ouverture/réduction d'une position futures directionnelle (side 'long'/'short', reduce),
  levier ≤ mandate.max_leverage() (mur ×5), notional + exposition cumulée plafonnés.
  JAMAIS de retrait, JAMAIS de changement de levier hors mur, JAMAIS d'agent non-LIVE.

Gardes DURS (les 8 de §34, court-circuit au 1er échec) : voir guards().
Mode --dry par DÉFAUT : imprime le preview, n'exécute RIEN. Et même --confirm reste
inoffensif à l'étape 1 : le chemin réel lève NotImplementedError (futures non câblé).
"""

import json
import time
from pathlib import Path

SYMBOL = "BTCUSDT"
EXECUTION_MODE = "FUTURES_DRY_RUN_ONLY"   # verrou dur : aucun ordre réel à l'étape 1


def _cfg(name, fallback):
    try:
        import config
        return getattr(config, name, fallback)
    except Exception:
        return fallback


def _limit(name, fallback):
    """Plafond numérique : env > config > défaut (comme spot_executor)."""
    import os
    v = os.getenv(name)
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    return float(_cfg(name, fallback))


# ---------- journal DRY-RUN (gitignored) ----------

def _ledger_path():
    return Path(__file__).resolve().parent / str(_cfg("FUTURES_REAL_LEDGER", "futures_real_ledger.json"))


def _journal(event):
    """Journalise un évènement (best-effort). Le ledger est gitignored."""
    path = _ledger_path()
    try:
        led = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"events": []}
    except Exception:
        led = {"events": []}
    led.setdefault("events", []).append(event)
    led["events"] = led["events"][-1000:]
    try:
        path.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------- gardes DURS (les 8 de §34 ; purs si on injecte l'état) ----------

def guards(agent, notional_usdt, leverage, *, equity_curve=None, gross_open_usdt=0.0,
           client_oid=None, seen_oids=None, hour_utc=None, macro_events=None, now=None,
           live=None, autonomous=None, futures_live=None, kill=None):
    """Vérifie TOUTES les gardes avant un ordre futures. Retourne (ok, raisons).
    PUR si l'état est injecté (live/autonomous/futures_live/kill/equity_curve/...)."""
    reasons = []

    # 1. kill_switch absent
    if kill is None:
        try:
            import risk_manager
            kill = risk_manager.kill_switch_active()
        except Exception:
            kill = False
    if kill:
        reasons.append("kill_switch actif")

    # 2. DOUBLE verrou : MANDATE_LIVE_ENABLED ET FUTURES_AUTONOMOUS_LIVE
    if live is None:
        try:
            import mandate
            live = mandate.live_enabled()
        except Exception:
            live = False
    if autonomous is None:
        autonomous = bool(_cfg("FUTURES_AUTONOMOUS_LIVE", False))
    if not (live and autonomous):
        reasons.append("double verrou coupé (MANDATE_LIVE_ENABLED ET FUTURES_AUTONOMOUS_LIVE requis)")

    # 3. porte d'edge : agent réellement éligible LIVE (replay ET live)
    if futures_live is None:
        try:
            import mandate
            futures_live = mandate.futures_live_allowed(agent)
        except Exception:
            futures_live = False
    if not futures_live:
        reasons.append(f"agent '{agent}' non éligible LIVE (porte d'edge non franchie)")

    # 4. levier ≤ mur dur
    max_lev = _limit("MANDATE_MAX_LEVERAGE", 5.0)
    lev = float(leverage or 0)
    if lev <= 0:
        reasons.append("levier ≤ 0")
    elif lev > max_lev:
        reasons.append(f"levier {lev} > mur dur {max_lev}")

    # 5. caps notional par trade ET exposition cumulée
    notion = float(notional_usdt or 0)
    if notion <= 0:
        reasons.append("notional ≤ 0")
    per_cap = _limit("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0)
    if notion > per_cap:
        reasons.append(f"notional {notion} > plafond/trade {per_cap}")
    gross_cap = _limit("FUTURES_REAL_MAX_GROSS_USDT", 20.0)
    gross = float(gross_open_usdt or 0)
    if gross + notion > gross_cap:
        reasons.append(f"exposition cumulée dépassée ({gross}+{notion} > {gross_cap})")

    # 6. halte drawdown (equity réelle)
    if equity_curve is not None:
        try:
            import mandate
            halt, dd_pct = mandate.drawdown_halt(equity_curve)
            if halt:
                reasons.append(f"halte drawdown ({dd_pct}% ≥ MDD toléré)")
        except Exception:
            pass

    # 7. session active + pas de black-out macro
    if hour_utc is not None:
        try:
            import mandate
            if not mandate.in_active_session(hour_utc):
                reasons.append("hors fenêtre de session active")
        except Exception:
            pass
    if macro_events is not None:
        try:
            import mandate
            nw = time.time() if now is None else now
            if mandate.macro_blackout(nw, macro_events):
                reasons.append("black-out macro (annonce à fort impact)")
        except Exception:
            pass

    # 8. idempotence clientOid (rejoue sans doubler)
    if client_oid is not None and seen_oids is not None:
        if str(client_oid) in set(str(o) for o in seen_oids):
            reasons.append(f"clientOid déjà vu ({client_oid}) — anti-doublon")

    return (not reasons, reasons)


# ---------- construction de la demande (pure) ----------

def _qty(x, decimals=6):
    """Notation DÉCIMALE (jamais scientifique) — Bitget rejette '8.3e-05'."""
    return f"{round(float(x), decimals):.{decimals}f}"


def build_futures_order(agent, side, notional_usdt, leverage, entry=None,
                        stop_loss=None, take_profit=None, client_oid=None, *, reduce=False):
    """Construit la demande d'ordre futures BORNÉE. PUR, sans effet de bord.

      • side ∈ {'long','short'} (vocabulaire neutre — l'open/close venue vient à l'étape 2) ;
      • reduce=True -> réduit/ferme une position existante ; False -> ouvre/augmente ;
      • le levier est CLAMPÉ au mur dur (jamais au-delà de mandate.max_leverage()).
    Retourne un dict descriptif (symbole, side, reduce, notional, levier, marge, oid, SL/TP).
    """
    s = str(side).lower()
    if s not in ("long", "short"):
        raise ValueError(f"side invalide: {side!r} (attendu 'long' ou 'short')")
    max_lev = _limit("MANDATE_MAX_LEVERAGE", 5.0)
    lev = max(1.0, min(float(max_lev), float(leverage)))   # borné par le mur, jamais au-delà
    notion = float(notional_usdt)
    order = {
        "symbol": SYMBOL,
        "side": s,
        "reduce": bool(reduce),
        "agent": str(agent),
        "notional_usdt": round(notion, 2),
        "leverage": round(lev, 2),
        "marginUsdt": round(notion / lev, 2) if lev else None,
        "size": _qty(notion / float(entry)) if entry else None,
        "clientOid": str(client_oid) if client_oid is not None else None,
        "execution_mode": EXECUTION_MODE,
    }
    if entry is not None:
        order["entry"] = float(entry)
    if stop_loss is not None:
        order["stop_loss"] = float(stop_loss)
    if take_profit is not None:
        order["take_profit"] = float(take_profit)
    return order


# ---------- exécution (DRY à l'étape 1 ; réel NON câblé) ----------

def _place_real(order, runner=None):
    """Chemin RÉEL — NON CÂBLÉ à l'étape 1 (RESEARCH_NOTES §34). Passer un ordre futures
    réel exige l'étape 2 : agent LIVE éligible + extension auditée des portes + GO explicite
    du propriétaire. Tant que ce n'est pas fait, on REFUSE de prétendre exécuter."""
    raise NotImplementedError(
        "Futures réel non câblé (étape 1 DRY-RUN). Voir RESEARCH_NOTES §34 étape 2 : "
        "requiert un agent LIVE et le GO explicite du propriétaire.")


def execute(agent, side, notional_usdt, leverage, entry=None, stop_loss=None,
            take_profit=None, *, reduce=False, confirm=False, runner=None, now=None,
            equity_curve=None, gross_open_usdt=0.0, seen_oids=None, hour_utc=None,
            macro_events=None, journal=True, **gate_overrides):
    """Ordre futures SI confirm=True ET les 8 gardes passent — mais le réel reste NON câblé
    (lève NotImplementedError). Sinon DRY (construit, journalise, n'exécute rien). Retourne
    un dict de résultat. gate_overrides (live/autonomous/futures_live/kill) injectables."""
    now = time.time() if now is None else now
    oid = f"fut{str(agent)[:3]}{int(now * 1000)}"
    ok, reasons = guards(agent, notional_usdt, leverage, equity_curve=equity_curve,
                         gross_open_usdt=gross_open_usdt, client_oid=oid, seen_oids=seen_oids,
                         hour_utc=hour_utc, macro_events=macro_events, now=now, **gate_overrides)
    order = build_futures_order(agent, side, notional_usdt, leverage, entry, stop_loss,
                                take_profit, oid, reduce=reduce)
    preview = (f"[DRY] futures {order['side']}{' reduce' if order['reduce'] else ''} "
               f"{order['notional_usdt']}USDT x{order['leverage']} "
               f"agent={agent} oid={oid} [{EXECUTION_MODE}]")

    if not ok:
        if journal:
            _journal({"action": "FUTURES_REFUSED", "ts": now, "order": order,
                      "reasons": reasons, "real_order_sent": False})
        return {"ok": False, "executed": False, "reasons": reasons,
                "preview": preview, "clientOid": oid}

    if not confirm:
        if journal:
            _journal({"action": "FUTURES_DRY_RUN", "ts": now, "order": order,
                      "real_order_sent": False})
        return {"ok": True, "executed": False, "dry": True, "preview": preview,
                "clientOid": oid,
                "note": "DRY — étape 1. Le réel reste non câblé (NotImplementedError au confirm)."}

    # confirm=True ET gardes passées : chemin réel — NON câblé à l'étape 1.
    if journal:
        _journal({"action": "FUTURES_REAL_BLOCKED", "ts": now, "order": order,
                  "real_order_sent": False, "reason": "réel non câblé (étape 1)"})
    return _place_real(order, runner=runner)   # lève NotImplementedError


def main():
    import argparse
    p = argparse.ArgumentParser(description="Ordre futures borné (DRY-RUN, étape 1 §34).")
    p.add_argument("--agent", default="geometric", help="agent (doit être LIVE pour le réel)")
    p.add_argument("--side", default="long", choices=["long", "short"], help="sens")
    p.add_argument("--reduce", action="store_true", help="réduit/ferme au lieu d'ouvrir")
    p.add_argument("--usdt", type=float, default=10.0, help="notional en USDT")
    p.add_argument("--leverage", type=float, default=2.0, help="levier (clampé au mur ×5)")
    p.add_argument("--entry", type=float, help="prix d'entrée (optionnel)")
    p.add_argument("--sl", type=float, help="stop loss (optionnel)")
    p.add_argument("--tp", type=float, help="take profit (optionnel)")
    p.add_argument("--confirm", action="store_true",
                   help="tente le réel (étape 1 : lève NotImplementedError si les gardes passent)")
    args = p.parse_args()

    print("=== ORDRE FUTURES (DRY-RUN, étape 1 §34) ===")
    try:
        r = execute(args.agent, args.side, args.usdt, args.leverage, args.entry,
                    args.sl, args.tp, reduce=args.reduce, confirm=args.confirm)
    except NotImplementedError as e:
        print(f"Preview construit, mais réel NON câblé : {e}")
        return
    print(f"Preview : {r.get('preview')}")
    if not r.get("ok"):
        print("REFUSÉ par les gardes : " + " ; ".join(r.get("reasons", [])))
    elif r.get("dry"):
        print("Mode DRY — aucun ordre passé. " + r.get("note", ""))
    print("Périmètre : futures borné, DRY-RUN. Le réel reste hors d'atteinte (étape 2).")


if __name__ == "__main__":
    main()
