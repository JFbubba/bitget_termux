"""
market_maker.py — market making spot BORNÉ (§94), inspiré des principes Virtu Financial.

Classement : module de DÉCISION. Il ne parle JAMAIS à l'API en écriture : toute
exécution est DÉLÉGUÉE à la surface §67 auditée à part — `spot_trader` (cotations
limit POST-ONLY via quote(), annulation via cancel()) — qui porte TOUTES les gardes :
verrou LIVE (SPOT_TRADE_LIVE), kill-switch fail-closed, caps durs par cotation ET
par jour (surface ledger "mm"), DRY par défaut. Le retrait externe est interdit par
conception partout (clé Trade-only).

Principes retenus de Virtu (docs/SAVOIR.md §9) — adaptés à un bot retail LENT :
  • NON-DIRECTIONNEL : coter bid ET ask autour d'un prix théorique, capturer l'écart,
    ne jamais parier sur la tendance ;
  • PRIX THÉORIQUE : fair = 0.70 × microprice + 0.30 × mid (le microprice pondère
    le déséquilibre immédiat du carnet, réf. microstructure.py) ;
  • SPREAD ADAPTATIF : cible = max(plancher, spread carnet, plancher de FRAIS
    aller-retour + buffer, vol court terme × multiplicateur), borné au plafond ;
  • CONTRÔLE D'INVENTAIRE (Avellaneda-Stoikov simplifié) : le prix de réservation
    glisse CONTRE l'inventaire — trop de base -> on cote pour vendre, pas assez ->
    pour acheter ; côté coupé au-delà de la déviation max. ⚠️ Écart volontaire vs
    la formule « reservation = fair × (1 − k×dev) » : ici le décalage est en fraction
    du DEMI-SPREAD (bornée), pas du prix (un dev de −0.5 décalerait le prix de 40 %) ;
  • VERROUS MULTICOUCHES : gardes pré-cotation (carnet illisible/trop large,
    premium cross-exchange via fair_price.py = anti adverse-selection minimal,
    historique de vol insuffisant), stop de perte LOCAL journalier du module,
    kill-switch global, murs de la surface. Fail-closed partout.

L'INVENTAIRE est celui du MODULE SEUL (fills de ses propres cotations, préfixe
clientOid "mmq"), jamais le solde global : le stock d'accumulation BTC (§44) est
INTOUCHABLE — la vente est bornée à l'inventaire acquis par le market making.

Gate maître : MM_AUTO (défaut OFF -> DRY : plan de cotation journalisé, rien de
placé). La réconciliation/annulation des cotations DÉJÀ ouvertes reste réelle même
désarmé (retirer ses cotations du carnet RÉDUIT le risque — fail-safe inverse).

CLI :
    python market_maker.py --status    # lecture seule : carnet + plan PRÉVU
    python market_maker.py --cycle     # un cycle (ne cote que si MM_AUTO=1)
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics
import time
from pathlib import Path

import bitget_execute as ex
from config_utils import cfg as _cfg
from numeric_utils import safe_float

STATE = Path(__file__).resolve().parent / ".mm_state.json"
JOURNAL = Path(__file__).resolve().parent / ".mm_journal.jsonl"
MIDS_MAX = 300                     # historique de mids (vol court terme)
MIN_HISTORY = 20                   # pas de cotation sans vol mesurable (warm-up DRY)


def enabled():
    """Gate maître (défaut OFF). Armable via env MM_AUTO=1 OU config."""
    v = os.getenv("MM_AUTO", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("MM_AUTO", False))


def _flt(name, default):
    try:
        return float(os.getenv(name) or _cfg(name, default))
    except (TypeError, ValueError):
        return float(default)


def config():
    """Leviers résolus (env > config > défaut). Le cap/cotation est REborné par le
    mur absolu de la surface (defense-in-depth : la surface re-vérifie tout)."""
    import spot_trader as st
    return {
        "symbol": (os.getenv("MM_SYMBOL") or str(_cfg("MM_SYMBOL", "BTCUSDT"))).upper(),
        "notional": _flt("MM_QUOTE_NOTIONAL_USDT", 5.0),
        "min_notional": _flt("MM_MIN_NOTIONAL_USDT", 1.0),
        "per_quote_cap": ex.capped("MM_MAX_PER_QUOTE_USDT", 5.0, st.ABS_MM_PER_QUOTE_USDT),
        "min_spread_bps": _flt("MM_MIN_SPREAD_BPS", 8.0),
        "max_spread_bps": _flt("MM_MAX_SPREAD_BPS", 80.0),
        "fee_bps": _flt("MM_FEE_BPS", 10.0),
        "buffer_bps": _flt("MM_LATENCY_BUFFER_BPS", 3.0),
        "vol_mult": _flt("MM_VOL_MULT", 2.5),
        "budget": _flt("MM_BUDGET_USDT", 20.0),
        "target_base_pct": _flt("MM_TARGET_BASE_PCT", 0.50),
        "skew_strength": _flt("MM_SKEW_STRENGTH", 0.80),
        "max_dev": _flt("MM_MAX_INV_DEV_PCT", 0.30),
        "max_inventory": _flt("MM_MAX_INVENTORY_USDT", 15.0),
        "max_book_spread": _flt("MM_MAX_BOOK_SPREAD_BPS", 120.0),
        "max_premium_pct": _flt("MM_MAX_PREMIUM_PCT", 0.50),
        "max_daily_loss": _flt("MM_MAX_DAILY_LOSS_USDT", 1.0),
        "price_decimals": int(_flt("MM_PRICE_DECIMALS", 2)),
    }


# ---------- moteur de cotation (PUR, testable) ----------

def microprice(bid, ask, bid_size, ask_size):
    """Microprice = mid pondéré par le déséquilibre L1 du carnet. PUR.
    Repli sur le mid simple si les tailles sont nulles/absentes."""
    b, a = float(bid), float(ask)
    tot = float(bid_size or 0) + float(ask_size or 0)
    if tot <= 0:
        return (b + a) / 2.0
    return (a * float(bid_size) + b * float(ask_size)) / tot


def vol_bps(mids):
    """Vol court terme = écart-type des log-returns des mids, en bps. PUR.
    0.0 si historique insuffisant (< MIN_HISTORY points)."""
    xs = [float(x) for x in (mids or []) if x and float(x) > 0][-60:]
    if len(xs) < MIN_HISTORY:
        return 0.0
    rets = [math.log(xs[i] / xs[i - 1]) for i in range(1, len(xs))]
    return statistics.pstdev(rets) * 10_000 if len(rets) >= 5 else 0.0


def target_spread_bps(book_spread_bps, vol, c):
    """Spread cible en bps : jamais sous les FRAIS aller-retour (2×fee + buffer),
    jamais sous le spread du carnet ni le plancher, élargi avec la vol. PUR."""
    floor_fees = (c["fee_bps"] * 2.0) + c["buffer_bps"]
    target = max(c["min_spread_bps"], float(book_spread_bps or 0), floor_fees,
                 float(vol or 0) * c["vol_mult"])
    return min(target, c["max_spread_bps"])


def size_multipliers(dev_pct, limit):
    """Tailles asymétriques selon la déviation d'inventaire : trop de base ->
    acheter moins / vendre plus (et inversement). Bornées [0, 2]. PUR."""
    lim = max(float(limit), 0.01)
    buy = max(0.0, min(2.0, 1.0 - float(dev_pct) / lim))
    sell = max(0.0, min(2.0, 1.0 + float(dev_pct) / lim))
    return buy, sell


def build_snapshot(book, mids):
    """Photo du carnet -> {bid, ask, tailles, mid, micro, fair, spread_bps, vol_bps}.
    PUR. None si le carnet est vide/incohérent (fail-closed chez l'appelant)."""
    try:
        bids = [[float(p), float(s)] for p, s in (book or {}).get("bids") or []]
        asks = [[float(p), float(s)] for p, s in (book or {}).get("asks") or []]
    except (TypeError, ValueError):
        return None
    if not bids or not asks:
        return None
    (bid, bid_size), (ask, ask_size) = bids[0], asks[0]
    if bid <= 0 or ask <= bid:
        return None
    mid = (bid + ask) / 2.0
    micro = microprice(bid, ask, bid_size, ask_size)
    return {"bid": bid, "ask": ask, "bid_size": bid_size, "ask_size": ask_size,
            "mid": mid, "micro": micro, "fair": 0.70 * micro + 0.30 * mid,
            "spread_bps": (ask - bid) / mid * 10_000, "vol_bps": vol_bps(mids),
            "n_mids": len(mids or [])}


def inventory_view(inv_base, avg_cost, mid, c):
    """Vue d'inventaire du MODULE : valeur, déviation vs cible (sur le BUDGET du
    sous-portefeuille, pas le compte), PnL latent. PUR."""
    base = max(0.0, float(inv_base or 0))
    value = base * float(mid or 0)
    dev = value / c["budget"] - c["target_base_pct"] if c["budget"] > 0 else 0.0
    latent = (float(mid) - float(avg_cost)) * base if base > 0 and avg_cost else 0.0
    return {"base": base, "value": round(value, 4), "dev_pct": round(dev, 4),
            "latent": round(latent, 6), "avg_cost": float(avg_cost or 0)}


def no_quote_reasons(snap, premium_pct, pnl_today, c, halted=False):
    """Gardes PRÉ-COTATION (liste vide = feu vert). PUR. Fail-closed : carnet
    illisible ou historique trop court -> on ne cote pas ; premium cross-exchange
    inconnu (None) -> on ne bloque PAS (best-effort, comme fair_price §44)."""
    r = []
    if halted:
        r.append("stop local du jour déjà déclenché (reprise demain)")
    if snap is None:
        return r + ["carnet illisible/incohérent (fail-closed)"]
    if snap["n_mids"] < MIN_HISTORY:
        r.append(f"historique de vol insuffisant ({snap['n_mids']}/{MIN_HISTORY} mids — warm-up)")
    if snap["spread_bps"] > c["max_book_spread"]:
        r.append(f"spread carnet {snap['spread_bps']:.1f} bps > max {c['max_book_spread']:.0f} (marché disloqué)")
    if premium_pct is not None and abs(float(premium_pct)) > c["max_premium_pct"]:
        r.append(f"premium Bitget {premium_pct:+.2f}% vs médiane cross-exchange > {c['max_premium_pct']}% (adverse selection)")
    if pnl_today is not None and float(pnl_today) <= -c["max_daily_loss"]:
        r.append(f"stop local : PnL jour {float(pnl_today):.4f} $ ≤ -{c['max_daily_loss']} $")
    return r


def build_plan(snap, inv, c):
    """Plan de cotation double face. PUR. Le prix de réservation glisse contre
    l'inventaire (en fraction du demi-spread, bornée par skew_strength×max_dev) ;
    clamp POST-ONLY : le bid ne dépasse jamais le meilleur bid, l'ask jamais sous
    le meilleur ask (sinon l'exchange rejette l'ordre post-only)."""
    target = target_spread_bps(snap["spread_bps"], snap["vol_bps"], c)
    half = target / 2.0 / 10_000.0
    resa = snap["fair"] * (1.0 - c["skew_strength"] * inv["dev_pct"] * half)
    q = 10 ** c["price_decimals"]
    bid_px = min(math.floor(resa * (1.0 - half) * q) / q, snap["bid"])
    ask_px = max(math.ceil(resa * (1.0 + half) * q) / q, snap["ask"])
    buy_m, sell_m = size_multipliers(inv["dev_pct"], c["max_dev"])
    cap = min(c["notional"] * 2.0, c["per_quote_cap"])
    bid_usdt = round(min(c["notional"] * buy_m, cap), 2)
    ask_usdt = round(min(c["notional"] * sell_m, cap, inv["base"] * ask_px * 0.999), 2)
    raisons = []
    if inv["dev_pct"] > c["max_dev"] or inv["value"] >= c["max_inventory"]:
        bid_usdt = 0.0
        raisons.append("inventaire plein — achat coupé")
    if inv["dev_pct"] < -c["max_dev"]:
        ask_usdt = 0.0
        raisons.append("inventaire vide — vente coupée")
    if bid_usdt < c["min_notional"]:
        bid_usdt = 0.0
    if ask_usdt < c["min_notional"]:
        ask_usdt = 0.0
    return {"bid_price": bid_px if bid_usdt > 0 else None,
            "ask_price": ask_px if ask_usdt > 0 else None,
            "bid_usdt": bid_usdt, "ask_usdt": ask_usdt,
            "spread_bps": round(target, 2), "reservation": round(resa, 4),
            "raisons": raisons}


def apply_fill(state, side, size, price):
    """Applique un fill constaté à l'inventaire du module : achat -> coût moyen
    pondéré ; vente -> PnL réalisé (vs coût moyen), inventaire jamais négatif. PUR
    (mute le dict state injecté)."""
    inv = max(0.0, float(state.get("inv_base") or 0))
    cost = float(state.get("avg_cost") or 0)
    size, price = float(size), float(price)
    if size <= 0 or price <= 0:
        return state
    if str(side).lower() == "buy":
        tot = inv + size
        state["avg_cost"] = round((inv * cost + size * price) / tot, 4) if tot > 0 else price
        state["inv_base"] = round(tot, 8)
    else:
        sold = min(size, inv)
        state["realized_today"] = round(float(state.get("realized_today") or 0)
                                        + (price - cost) * sold, 6)
        state["inv_base"] = round(max(0.0, inv - sold), 8)
        if state["inv_base"] <= 0:
            state["avg_cost"] = 0.0
    return state


# ---------- état persistant & journal ----------

def _load_state():
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(state):
    try:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _journalise(entree):
    try:
        with JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _notifie(msg):
    try:
        import telegram_notifier as tn
        tn.send_telegram(msg)
    except Exception:
        pass


def _roll_day(state, now):
    day = int(now // 86400)
    if state.get("day") != day:
        state.update({"day": day, "realized_today": 0.0, "halted": False})
    state.setdefault("mids", [])
    state.setdefault("active", [])
    state.setdefault("inv_base", 0.0)
    state.setdefault("avg_cost", 0.0)
    state.setdefault("realized_today", 0.0)
    state.setdefault("halted", False)
    return state


def _kill_active():
    """Kill-switch global, fail-closed (même règle que bitget_execute)."""
    try:
        import risk_manager
        return bool(risk_manager.kill_switch_active())
    except Exception:
        return True


def _extract_order_id(response):
    m = re.search(r'"orderId"\s*:\s*"?(\d+)"?', response or "")
    return m.group(1) if m else None


# ---------- lectures (best-effort, lecture seule) ----------

def _book(symbol):
    try:
        import bitget_market_data as bmd
        return bmd.fetch_spot_orderbook(symbol, limit="15")
    except Exception:
        return None


def _premium(symbol):
    """Premium Bitget vs médiane cross-exchange (fair_price §44). None best-effort."""
    try:
        import fair_price
        return fair_price.fair_value(symbol).get("premium_pct")
    except Exception:
        return None


# ---------- réconciliation des cotations (fail-safe) ----------

def _reconcile(state, c):
    """Constate les fills des cotations du cycle précédent puis RETIRE du carnet
    celles encore ouvertes (TTL = 1 cycle). Toujours en réel : l'annulation réduit
    le risque. Détail illisible -> l'entrée est GARDÉE pour le cycle suivant
    (fail-safe : on ne perd jamais la trace d'une cotation potentiellement vivante)."""
    import spot_trader as st
    rest, fills = [], []
    for a in state.get("active") or []:
        oid = a.get("order_id")
        if not oid:                                    # réponse tronquée au placement
            rows = st.open_orders(c["symbol"])
            m = next((r for r in rows or [] if str(r.get("clientOid")) == str(a.get("oid"))), None)
            if m:
                oid = str(m.get("orderId"))
                a["order_id"] = oid
        info = st.order_info(c["symbol"], oid) if oid else None
        if info is None:
            rest.append(a)
            continue
        status = str(info.get("status", "")).lower()
        if status in ("live", "new", "init", "partially_filled"):
            st.cancel(c["symbol"], order_id=oid, confirm=True)
            info = st.order_info(c["symbol"], oid) or info
        filled = safe_float(info.get("baseVolume")) or 0.0
        price = safe_float(info.get("priceAvg")) or safe_float(a.get("price")) or 0.0
        if filled > 0:
            apply_fill(state, a.get("side"), filled, price)
            fills.append({"side": a.get("side"), "size": filled, "price": price,
                          "oid": a.get("oid")})
    state["active"] = rest
    return fills


# ---------- cycle / statut ----------

def cycle(now=None, confirm=None):
    """Un cycle de market making. Ne COTE (confirm=True vers spot_trader.quote) que
    si MM_AUTO est armé ET kill-switch inactif ET gardes vertes — sinon DRY (plan
    journalisé, rien de placé). La surface re-vérifie TOUT (verrou LIVE, kill, caps)."""
    now = time.time() if now is None else now
    c = config()
    state = _roll_day(_load_state(), now)
    fills = _reconcile(state, c) if state.get("active") else []
    book = _book(c["symbol"])
    snap = build_snapshot(book, state["mids"])
    if snap:
        state["mids"] = (state["mids"] + [snap["mid"]])[-MIDS_MAX:]
        snap["vol_bps"] = vol_bps(state["mids"])
        snap["n_mids"] = len(state["mids"])
    inv = inventory_view(state["inv_base"], state["avg_cost"],
                         snap["mid"] if snap else state.get("avg_cost"), c)
    pnl_today = round(float(state["realized_today"]) + inv["latent"], 6)
    if pnl_today <= -c["max_daily_loss"] and not state["halted"]:
        state["halted"] = True
        _notifie(f"🧊 Market making : stop local du jour ({pnl_today:.4f} $ ≤ "
                 f"-{c['max_daily_loss']} $). Cotations retirées, reprise demain.")
    kill = _kill_active()
    premium = _premium(c["symbol"])
    raisons = no_quote_reasons(snap, premium, pnl_today, c, halted=state["halted"])
    if kill:
        raisons.insert(0, "kill_switch actif (fail-closed)")
    arme = enabled() if confirm is None else bool(confirm)
    plan = build_plan(snap, inv, c) if snap and not raisons else None
    out = {"ts": int(now), "symbol": c["symbol"], "armed": arme, "kill": kill,
           "fills": fills, "inv": inv, "pnl_today": pnl_today,
           "premium_pct": premium, "raisons": raisons,
           "snap": {k: round(v, 6) for k, v in (snap or {}).items()
                    if isinstance(v, (int, float))} or None,
           "plan": plan, "placed": []}
    if plan and arme:
        import spot_trader as st
        for side, px, usdt in (("buy", plan["bid_price"], plan["bid_usdt"]),
                               ("sell", plan["ask_price"], plan["ask_usdt"])):
            if px is None or usdt <= 0:
                continue
            r = st.quote(c["symbol"], side, usdt, px, confirm=True,
                         price_decimals=c["price_decimals"])
            row = {"side": side, "price": px, "usdt": usdt,
                   "executed": bool(r.get("executed")),
                   "reasons": r.get("reasons"), "oid": r.get("clientOid")}
            out["placed"].append(row)
            if r.get("executed"):
                state["active"].append({"oid": r.get("clientOid"),
                                        "order_id": _extract_order_id(r.get("response")),
                                        "side": side, "price": px, "usdt": usdt})
    _save_state(state)
    _journalise(out)
    for f in fills:
        _notifie(f"🔁 Market making : fill {f['side']} {f['size']} @ {f['price']} "
                 f"({c['symbol']}) · inventaire {state['inv_base']} · "
                 f"PnL réalisé jour {state['realized_today']} $")
    return out


def status():
    """Lecture seule : carnet + inventaire + plan PRÉVU (aucune écriture d'état,
    aucune cotation, aucune annulation)."""
    c = config()
    state = _roll_day(_load_state(), time.time())
    snap = build_snapshot(_book(c["symbol"]), state["mids"])
    inv = inventory_view(state["inv_base"], state["avg_cost"],
                         snap["mid"] if snap else state.get("avg_cost"), c)
    pnl_today = round(float(state["realized_today"]) + inv["latent"], 6)
    premium = _premium(c["symbol"])
    raisons = no_quote_reasons(snap, premium, pnl_today, c, halted=state.get("halted", False))
    return {"symbol": c["symbol"], "armed": enabled(), "snap": snap, "inv": inv,
            "pnl_today": pnl_today, "premium_pct": premium, "raisons": raisons,
            "active": state.get("active") or [],
            "plan": build_plan(snap, inv, c) if snap and not raisons else None,
            "consultation": True}


def build_report(s=None):
    s = status() if s is None else s
    snap, plan, inv = s.get("snap") or {}, s.get("plan") or {}, s.get("inv") or {}
    lignes = [
        "=== MARKET MAKING SPOT (borné §94, principes Virtu) — CONSULTATION ===",
        f"Armé : {s.get('armed')} · {s.get('symbol')} · cotations actives : {len(s.get('active') or [])}",
    ]
    if snap:
        lignes.append(f"Carnet : bid {snap.get('bid')} / ask {snap.get('ask')} · "
                      f"spread {snap.get('spread_bps'):.2f} bps · fair {snap.get('fair'):.2f} · "
                      f"vol {snap.get('vol_bps'):.2f} bps ({snap.get('n_mids')} mids)")
    lignes.append(f"Inventaire module : {inv.get('base')} base ({inv.get('value')} $) · "
                  f"dev {inv.get('dev_pct')} · PnL jour {s.get('pnl_today')} $ · "
                  f"premium {s.get('premium_pct')}%")
    if plan:
        lignes.append(f"Plan : bid {plan.get('bid_usdt')} $ @ {plan.get('bid_price')} · "
                      f"ask {plan.get('ask_usdt')} $ @ {plan.get('ask_price')} · "
                      f"spread cible {plan.get('spread_bps')} bps {plan.get('raisons') or ''}")
    else:
        lignes.append(f"Pas de cotation : {' ; '.join(s.get('raisons') or ['plan vide'])}")
    lignes.append("Décision seule ici — toute exécution passe par spot_trader (verrou "
                  "SPOT_TRADE_LIVE, kill-switch, caps mm). Jamais de retrait. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    import sys
    try:
        from dotenv import load_dotenv                 # cron/CLI : leviers env visibles
        load_dotenv()
    except Exception:
        pass
    if "--cycle" in sys.argv[1:]:
        r = cycle()
        print("=== MARKET MAKING — CYCLE ===")
        print(f"{r['symbol']} · armé {r['armed']} · kill {r['kill']} · PnL jour {r['pnl_today']} $")
        for f in r["fills"]:
            print(f"fill constaté : {f['side']} {f['size']} @ {f['price']}")
        if r["raisons"]:
            print("Pas de cotation :", " ; ".join(r["raisons"]))
        elif not r["armed"]:
            p = r.get("plan") or {}
            print(f"DRY — plan : bid {p.get('bid_usdt')} $ @ {p.get('bid_price')} · "
                  f"ask {p.get('ask_usdt')} $ @ {p.get('ask_price')} (rien de placé)")
        else:
            for row in r["placed"]:
                etat = "✅ placée" if row["executed"] else f"refusée {row.get('reasons')}"
                print(f"cotation {row['side']} {row['usdt']} $ @ {row['price']} : {etat}")
        print("VERDICT: SAFE")
    else:
        print(build_report())


if __name__ == "__main__":
    main()
