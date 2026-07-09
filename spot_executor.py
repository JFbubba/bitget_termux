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


from config_utils import cfg as _cfg
import math


def _limit(name, fallback):
    """Plafond numérique : env > config > défaut. L'env permet une validation ponctuelle
    sans éditer config.py (qui ferait échouer `git pull --ff-only`)."""
    import os
    v = os.getenv(name)
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    return float(_cfg(name, fallback))


# Plafonds ABSOLUS en dur (defense-in-depth) : ni .env ni config ne peuvent les DÉPASSER.
# La promesse documentée est 5 $/j ; ces murs laissent une MARGE délibérée pour un tuning
# ponctuel (env/config peuvent ABAISSER le cap), mais bornent toute catastrophe (env ne peut
# JAMAIS relever au-dessus). Motivation : écart du 27/06 (cap relevé en env -> 10 $ au lieu de
# 5 $) ; un env var ne doit pas pouvoir desserrer un plafond d'argent réel sans revue/commit.
ACCUM_ABS_MAX_PER_BUY_USDT = 25.0    # mur dur par achat (5x la promesse)
ACCUM_ABS_MAX_DAILY_USDT = 25.0      # mur dur journalier (5x la promesse)
# Promesse DOCUMENTEE (CLAUDE.md) = 5 $/jour. Independante du cap effectif (qu'un env peut
# porter jusqu'au mur absolu 25). Sert de TRIPWIRE d'observabilite : si la depense reelle d'un
# jour la depasse, on ALERTE (meme si le cap effectif l'a autorisee). Comble le trou revele par
# l'ecart du 27/06 (10 $ depenses sans alerte temps reel).
ACCUM_DAILY_PROMISE_USDT = 5.0


def _capped(name, fallback, absolute):
    """Plafond EFFECTIF = min(env > config > défaut, mur ABSOLU en dur). L'absolu ne peut
    PAS être dépassé par env/config (mur réel infranchissable). PUR (lit l'env)."""
    return min(_limit(name, fallback), float(absolute))


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


def daily_spend_breach(promise=None, now=None, ledger=None):
    """TRIPWIRE d'observabilité (indépendant du cap) : la dépense RÉELLE du jour dépasse-t-elle
    la PROMESSE documentée (5 $/j) ? PUR si ledger injecté. Retourne (breach: bool, spent, promise).
    Le cap effectif (jusqu'à 25 via env) PEUT autoriser plus que la promesse -> on veut le SAVOIR."""
    promise = _limit("ACCUM_DAILY_PROMISE_USDT", ACCUM_DAILY_PROMISE_USDT) if promise is None else float(promise)
    spent = today_spent(now=now, ledger=ledger)
    return (spent > promise, spent, promise)


def _record_real_buy(amount_usdt, oid, now=None, extra=None, fill=None):
    """`extra` (audit P2) : contexte de décision journalisé AVEC l'achat (score
    d'opportunité, prix, premium) — la revue J+14 doit pouvoir relier chaque achat
    réel à ce que le moteur voyait. Champs numériques/str uniquement, best-effort.

    `fill` (idée #1) : fill RÉEL confirmé {amount_usdt, size_btc, price_avg}. En
    limit_ioc un ordre peut ne remplir que PARTIELLEMENT — on enregistre alors le
    montant EFFECTIVEMENT dépensé (le cap journalier et le prix de revient comptent
    le réel, plus le demandé). Sans confirmation -> on garde le demandé (conservateur :
    compte le plein montant contre le cap, jamais de sous-comptage)."""
    now = time.time() if now is None else now
    led = _load_real()
    montant = float(amount_usdt)
    row = {"ts": now, "amount_usdt": montant, "clientOid": oid, "symbol": SYMBOL}
    if fill and isinstance(fill, dict) and (fill.get("amount_usdt") or 0) > 0:
        row["amount_usdt"] = round(float(fill["amount_usdt"]), 6)   # RÉEL dépensé (écrase le demandé)
        row["requested_usdt"] = montant
        row["filled_btc"] = fill.get("size_btc")
        row["fill_price"] = fill.get("price_avg")
        row["fill_confirmed"] = True
    else:
        row["fill_confirmed"] = False                               # montant = demandé (non confirmé)
    for k, v in (extra or {}).items():
        if isinstance(v, (int, float, str)) and k not in row:
            row[k] = round(v, 6) if isinstance(v, float) else v
    led.setdefault("buys", []).append(row)
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
    # fail-closed gracieux : un montant non numérique est REJETÉ (avec les raisons
    # déjà accumulées), jamais propagé en exception qui crasherait l'appelant.
    try:
        amt = float(amount_usdt or 0)
    except (TypeError, ValueError):
        reasons.append("montant invalide (non numérique)")
        return (False, reasons)
    if not math.isfinite(amt):
        # NaN/inf défaisait toutes les comparaisons (amt<=0, amt>cap, sp+amt>cap tous False)
        # -> ok=True à tort. Fail-closed. (§revue chemin argent — Thème 4)
        reasons.append("montant non fini (NaN/inf)")
        return (False, reasons)
    if amt <= 0:
        reasons.append("montant ≤ 0")
    cap = _capped("ACCUM_REAL_MAX_PER_BUY_USDT", 5.0, ACCUM_ABS_MAX_PER_BUY_USDT)
    if amt > cap:
        reasons.append(f"montant {amt} > plafond/achat {cap}")
    daily_cap = _capped("ACCUM_REAL_MAX_DAILY_USDT", 5.0, ACCUM_ABS_MAX_DAILY_USDT)
    sp = today_spent() if spent is None else float(spent)
    if sp + amt > daily_cap:
        reasons.append(f"plafond journalier dépassé ({sp}+{amt} > {daily_cap})")
    if balance is not None and amt > float(balance):
        reasons.append(f"montant {amt} > solde spot disponible {balance}")
    return (not reasons, reasons)


# ---------- construction de la demande (pure) ----------

def _qty(x, decimals=6):
    """Quantité base en notation DÉCIMALE (jamais scientifique) — Bitget rejette '8.3e-05'."""
    return f"{round(float(x), decimals):.{decimals}f}"


def build_order(amount_usdt, client_oid, style="taker", quote=None, tol_pct=0.10):
    """Construit l'objet ordre d'ACHAT spot BTC selon le style. PUR.
      • taker     : ordre marché, size = montant en QUOTE (USDT à dépenser) ;
      • maker      : limite post-only au BID -> frais maker / meilleur prix (peut ne pas
                     remplir), size = montant en BASE (BTC) ;
      • limit_ioc  : limite IOC plafonnée juste au-dessus de l'ASK -> remplit tout de suite
                     mais JAMAIS au-delà du plafond (anti-slippage), size en BASE.
    Repli sur marché si le carnet (quote) est indisponible -> on achète quand même."""
    base = {"symbol": SYMBOL, "side": "buy", "clientOid": str(client_oid)}
    if style == "taker" or not quote:
        return {**base, "orderType": "market", "size": str(amount_usdt)}
    if style == "maker":
        price = float(quote["bid"])
        return {**base, "orderType": "limit", "force": "post_only",
                "price": str(round(price, 2)), "size": _qty(float(amount_usdt) / price)}
    price = float(quote["ask"]) * (1.0 + float(tol_pct) / 100.0)        # limit_ioc : plafond
    return {**base, "orderType": "limit", "force": "ioc",
            "price": str(round(price, 2)), "size": _qty(float(amount_usdt) / price)}


def build_command(amount_usdt, client_oid, style="taker", quote=None, tol_pct=0.10):
    """Args `bgc` (tableau JSON `orders`, format batch) pour l'ordre construit. PUR."""
    return ["spot", "spot_place_order", "--orders",
            json.dumps([build_order(amount_usdt, client_oid, style, quote, tol_pct)])]


# ---------- exécution (réelle uniquement avec confirm=True) ----------

def _extract_usdt_available(res):
    """USDT LIBRE (disponible) dans une réponse spot/account/assets. PUR."""
    try:
        for row in (res.get("data") or []):
            if str(row.get("coin", "")).upper() == "USDT":
                return float(row.get("available"))
    except Exception:
        pass
    return None


def _spot_free_usdt():
    """USDT LIBRE dans le wallet SPOT (pas la valeur totale du wallet). Best-effort.
    C'est CE solde qui finance un achat — la valeur agrégée du compte est trompeuse."""
    try:
        import bitget_balance_reader as br
        return _extract_usdt_available(br.get_spot_assets("USDT"))
    except Exception:
        return None


def _run(cmd, runner=None):
    """Lance la commande bgc (SANS --read-only : c'est l'écriture). Concatène stdout ET
    stderr pour ne RIEN perdre des erreurs (sinon réponse vide en cas d'échec). runner
    injectable pour les tests."""
    if runner is not None:
        return runner(cmd)
    try:
        import bitget_hub_bridge as hub
        if not hub.available():
            return None
        import subprocess
        p = subprocess.run(["bgc", *cmd], capture_output=True, text=True,
                           timeout=30, env=hub._hub_env())
        return ((p.stdout or "") + (p.stderr or "")).strip() or None
    except Exception:
        return None


def _exec_style():
    """Style d'exécution : env EXEC_STYLE > config > 'taker'."""
    import os
    return (os.getenv("EXEC_STYLE", "").strip().lower()
            or str(_cfg("EXEC_STYLE", "taker")).lower())


def _best_quote(symbol=SYMBOL):
    """Meilleur bid/ask spot (lecture seule via l'Agent Hub). None si indisponible."""
    try:
        import bitget_hub_bridge as hub
        d = hub._read(["spot", "spot_get_ticker", "--symbol", symbol])
        rows = (d or {}).get("data") if isinstance(d, dict) else None
        row = rows[0] if isinstance(rows, list) and rows else {}
        bid, ask = float(row.get("bidPr")), float(row.get("askPr"))
        return {"bid": bid, "ask": ask, "mid": (bid + ask) / 2.0}
    except Exception:
        return None


def _confirm_fill(oid, tries=None, delay=None, sleeper=None):
    """Idée #1 : confirme le fill RÉEL d'un ordre en re-pollant les fills spot pour cet
    orderId (les fills peuvent arriver avec un léger retard). Retourne le groupe agrégé
    {amount_usdt, size_btc, price_avg} ou None. FAIL-SAFE : n'ordonne rien, ne lève
    jamais (l'ordre est DÉJÀ passé — ceci ne fait que constater ce qui a été rempli)."""
    tries = int(_cfg("ACCUM_CONFIRM_FILL_TRIES", 5)) if tries is None else tries
    delay = float(_cfg("ACCUM_CONFIRM_FILL_DELAY_S", 1.0)) if delay is None else delay
    sleeper = sleeper or time.sleep
    try:
        import accum_reconcile as ar
    except Exception:
        return None
    for i in range(max(1, tries)):
        try:
            for g in ar.group_fills(ar.fetch_fills(limit=100)) or []:
                if str(g.get("order_id")) == str(oid) and (g.get("amount_usdt") or 0) > 0:
                    return {"amount_usdt": g.get("amount_usdt"), "size_btc": g.get("size_btc"),
                            "price_avg": g.get("price_avg")}
        except Exception:
            pass
        if i < tries - 1:
            sleeper(delay)
    return None


def _parse_error(out):
    """Idée #2 : extrait {code, msg} de la réponse Bitget en cas d'échec, pour un
    diagnostic clair. PAS de retry auto sur un ACHAT réel (risque de double ordre) —
    on se contente de rendre l'erreur lisible et actionnable pour l'appelant/journal."""
    try:
        import re
        m = re.search(r'"code"\s*:\s*"?(\d+)"?', out or "")
        mm = re.search(r'"msg"\s*:\s*"([^"]+)"', out or "")
        code = m.group(1) if m else None
        if code and code != "00000":
            return {"code": code, "msg": (mm.group(1)[:200] if mm else "")}
    except Exception:
        pass
    return None


def execute(amount_usdt, confirm=False, runner=None, now=None, balance=None, spent=None, style=None,
            extra=None):
    """Achat spot BTC réel SI confirm=True ET toutes les gardes passent. Sinon DRY
    (imprime la commande, n'exécute rien). Retourne un dict de résultat. balance/spent
    injectables (tests hermétiques) ; sinon lus en réel."""
    now = time.time() if now is None else now
    bal = balance if balance is not None else _spot_free_usdt()
    ok, reasons = guards(amount_usdt, balance=bal, spent=spent)
    oid = f"accbtc{int(now * 1000)}"
    style = style or _exec_style()
    quote = _best_quote() if style in ("maker", "limit_ioc") else None
    cmd = build_command(amount_usdt, oid, style=style, quote=quote,
                        tol_pct=float(_cfg("ACCUM_SLIPPAGE_TOL_PCT", 0.10)))
    preview = "bgc " + " ".join(cmd)
    if not ok:
        return {"ok": False, "executed": False, "reasons": reasons, "preview": preview}
    if not confirm:
        return {"ok": True, "executed": False, "dry": True, "preview": preview,
                "note": "DRY — vérifie la commande puis ajoute --confirm pour l'achat RÉEL"}
    out = _run(cmd, runner=runner)
    compact = (out or "").replace(" ", "").lower()
    success = (bool(out) and '"ok":false' not in compact and "error" not in compact
               and ("orderid" in compact or '"data"' in compact or '"ok":true' in compact))
    result = {"ok": True, "executed": success, "preview": preview, "response": out,
              "clientOid": oid}
    if success:
        # #1 : constate le fill RÉEL (limit_ioc partiel) et enregistre le réel dépensé.
        fill = _confirm_fill(oid) if bool(_cfg("ACCUM_CONFIRM_FILL", True)) else None
        _record_real_buy(amount_usdt, oid, now, extra=extra, fill=fill)
        if fill:
            result["fill"] = fill
    else:
        err = _parse_error(out)                # #2 : erreur Bitget lisible (pas de retry auto)
        if err:
            result["error"] = err
    return result


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
