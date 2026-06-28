"""
accumulation_engine.py — ACCUMULATION BTC (spot DCA) pilotée par le cerveau.

Classement : SAFE. Paper/advisory, lecture seule, AUCUN ordre réel. S'AJOUTE au bot
futures (ne le remplace pas) : un moteur séparé qui répond à « accumuler au meilleur
prix, hold, earn ».

Principe (≠ trading futures) :
  • SPOT, aucun levier, aucune liquidation, on ne VEND jamais (hold) ;
  • DCA de base RÉGULIER + renforts quand le BTC est « bon marché » (score d'opportunité
    déterministe : drawdown, RSI bas, Fear&Greed bas, prix sous moyenne longue) ;
  • le CERVEAU sert de détecteur de capitulation (queue baissière, peur) ;
  • registre paper (prix moyen d'accumulation) ; EARN = piste documentée (API Bitget Earn,
    nécessite permission compte -> hors paper, à activer plus tard).

Fonctions de calcul PURES et testables ; fetch réseau enveloppés (ne lèvent jamais).
"""

import json
import math
import time
from pathlib import Path

LEDGER_FILE = Path(__file__).resolve().parent / "accumulation_ledger.json"

# Paramètres DCA (défauts conservateurs ; surchargeables via config)
DCA_BASE_USD = 10.0          # achat de base par intervalle
DCA_MAX_MULTIPLIER = 5.0     # renfort max quand l'opportunité est maximale
DCA_INTERVAL_H = 24.0        # un achat au plus toutes les 24 h (DCA quotidien)
# Affûtage du TIMING d'entrée (RESEARCH_NOTES §38) : mélange une composante de survente
# COURT TERME au score d'opportunité (lent). Validé en backtest cost-basis (avantage OOS
# +0.69%->+0.77%, robuste sur 15 symboles ; plateau stable). st_weight=0 -> comportement
# historique inchangé. NON-directionnel : améliore l'entrée d'un achat fait de toute façon.
DCA_ST_WEIGHT = 0.30         # poids de la survente court-terme dans le score (0 = désactivé)
DCA_ST_WINDOW = 24           # fenêtre (barres) de la moyenne mobile courte


def _cfg(name, fallback):
    try:
        import config
        return getattr(config, name, fallback)
    except Exception:
        return fallback


# ---------- indicateurs purs ----------

def rsi(closes, period=14):
    """RSI de Wilder (0..100). Pur. None si trop court."""
    p = [float(c) for c in closes if c and c > 0]
    if len(p) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = p[i] - p[i - 1]
        gains += max(d, 0.0); losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    for i in range(period + 1, len(p)):
        d = p[i] - p[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _clamp01(x):
    return max(0.0, min(1.0, x))


def short_term_oversold(closes, window=24):
    """Survente COURT TERME ∈ [0,1] : ampleur (z-score) du prix SOUS sa moyenne mobile
    courte. Élevé = repli court-terme -> meilleur point d'entrée. PUR. C'est du TIMING
    d'entrée (acheter sur faiblesse court-terme ce qu'on accumule de toute façon), PAS une
    prédiction de direction. La reversion court-terme est réelle (RESEARCH_NOTES §35-38)."""
    p = [float(c) for c in closes if c and c > 0]
    if len(p) < int(window) + 1:
        return 0.0
    w = p[-int(window):]
    ma = sum(w) / len(w)
    rets = [math.log(w[i] / w[i - 1]) for i in range(1, len(w)) if w[i - 1] > 0]
    if len(rets) < 2:
        return 0.0
    mu = sum(rets) / len(rets)
    sd = (sum((x - mu) ** 2 for x in rets) / len(rets)) ** 0.5     # écart-type population
    price = p[-1]
    if sd <= 1e-9 or price <= 0:
        return 0.0
    z = (ma - price) / (price * sd)                                # >0 = sous la MA courte
    return _clamp01(z / 3.0)


def opportunity_score(closes, fear_greed=None, dd_window=90, st_weight=None, st_window=None):
    """Score d'OPPORTUNITÉ D'ACHAT ∈ [0,1] (1 = BTC bon marché -> accumuler fort). PUR.
    Combine : drawdown vs plus-haut récent, RSI bas (survente), Fear&Greed bas (peur),
    prix sous la moyenne longue, ET une survente COURT TERME (affûtage timing, §38).
    Tous les sous-signaux : élevé = bon marché. st_weight=0 -> score historique inchangé."""
    p = [float(c) for c in closes if c and c > 0]
    if len(p) < 20:
        return {"score": 0.0, "parts": {}, "n": len(p)}
    price = p[-1]
    win = p[-dd_window:] if len(p) >= dd_window else p
    hi = max(win)
    s_dd = _clamp01((hi - price) / hi / 0.30) if hi > 0 else 0.0      # -30% = max
    r = rsi(p)
    s_rsi = _clamp01((50.0 - r) / 40.0) if r is not None else 0.0     # RSI 10 -> 1
    ma = sum(win) / len(win)
    s_ma = _clamp01((ma - price) / ma / 0.20) if ma > 0 else 0.0      # 20% sous la MA = 1
    s_fg = _clamp01((50.0 - float(fear_greed)) / 50.0) if fear_greed is not None else 0.0
    # pondération : drawdown + survente dominants, sentiment en appoint
    w = {"drawdown": 0.35, "rsi": 0.25, "below_ma": 0.20, "fear": 0.20}
    score = w["drawdown"] * s_dd + w["rsi"] * s_rsi + w["below_ma"] * s_ma + w["fear"] * s_fg
    parts = {"drawdown": round(s_dd, 3), "rsi": round(s_rsi, 3),
             "below_ma": round(s_ma, 3), "fear": round(s_fg, 3)}
    # affûtage TIMING (§38) : mélange la survente court-terme (validé cost-basis OOS).
    stw = _cfg("ACCUM_ST_WEIGHT", DCA_ST_WEIGHT) if st_weight is None else st_weight
    stk = _cfg("ACCUM_ST_WINDOW", DCA_ST_WINDOW) if st_window is None else st_window
    s_st = short_term_oversold(p, stk) if stw else 0.0
    score = (1.0 - float(stw)) * score + float(stw) * s_st
    parts["short_term"] = round(s_st, 3)
    return {"score": round(_clamp01(score), 3), "parts": parts,
            "rsi": round(r, 1) if r is not None else None,
            "price": round(price, 2), "n": len(p)}


def dca_amount(score, base=None, max_mult=None):
    """Montant à accumuler ce cycle (USD). PUR. DCA de base + renfort ∝ score.
    montant = base · (1 + (max_mult−1)·score). Jamais de vente, jamais 0 (on accumule
    toujours un minimum)."""
    base = _cfg("DCA_BASE_USD", DCA_BASE_USD) if base is None else base
    max_mult = _cfg("DCA_MAX_MULTIPLIER", DCA_MAX_MULTIPLIER) if max_mult is None else max_mult
    return round(float(base) * (1.0 + (float(max_mult) - 1.0) * _clamp01(score)), 2)


def should_buy(last_buy_ts, now, interval_h=None):
    """Throttle DCA : a-t-on attendu l'intervalle depuis le dernier achat ? PUR."""
    interval_h = _cfg("DCA_INTERVAL_H", DCA_INTERVAL_H) if interval_h is None else interval_h
    if last_buy_ts is None:
        return True
    return (now - float(last_buy_ts)) >= interval_h * 3600.0


# ---------- registre paper d'accumulation ----------

def load_ledger():
    try:
        return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"total_btc": 0.0, "total_cost_usd": 0.0, "avg_price": 0.0,
                "n_buys": 0, "last_buy_ts": None, "buys": []}


def apply_buy(ledger, amount_usd, price, ts=None, score=None):
    """Applique un achat PAPER au registre (pur). Met à jour BTC, coût, prix moyen."""
    qty = amount_usd / price if price > 0 else 0.0
    led = dict(ledger)
    led["total_btc"] = round(float(led.get("total_btc", 0)) + qty, 8)
    led["total_cost_usd"] = round(float(led.get("total_cost_usd", 0)) + amount_usd, 2)
    led["avg_price"] = round(led["total_cost_usd"] / led["total_btc"], 2) if led["total_btc"] > 0 else 0.0
    led["n_buys"] = int(led.get("n_buys", 0)) + 1
    led["last_buy_ts"] = int(ts if ts is not None else time.time())
    buys = list(led.get("buys", []))
    buys.append({"ts": led["last_buy_ts"], "amount_usd": amount_usd, "price": round(price, 2),
                 "qty_btc": round(qty, 8), "score": score})
    led["buys"] = buys[-500:]
    return led


def save_ledger(led):
    try:
        LEDGER_FILE.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------- live (best-effort) ----------

def _closes(symbol, limit=200):
    try:
        import market_sources as ms
        c = ms.closes(symbol, limit)
        if c and len(c) >= 30:
            return c
    except Exception:
        pass
    try:
        import technicals as tk
        return [float(x["close"]) for x in tk.fetch_candles(symbol, "1d", limit)]
    except Exception:
        return []


def _fear_greed():
    try:
        import sentiment_index
        fg = sentiment_index.fetch_fear_greed()
        return float(fg.get("value")) if fg and fg.get("value") is not None else None
    except Exception:
        return None


def _fair(symbol):
    try:
        import fair_price as fp
        return fp.fair_value(symbol)
    except Exception:
        return {}


def analyze(symbol="BTCUSDT"):
    """Évalue l'opportunité d'accumulation + le montant DCA recommandé. Best-effort."""
    closes = _closes(symbol)
    if len(closes) < 20:
        return {"score": 0.0, "amount_usd": dca_amount(0.0), "note": "données insuffisantes"}
    fg = _fear_greed()
    opp = opportunity_score(closes, fg)
    amt = dca_amount(opp["score"])
    fv = _fair(symbol)               # prix de référence cross-exchange (meilleur prix)
    return {"symbol": symbol.upper(), "score": opp["score"], "parts": opp.get("parts", {}),
            "rsi": opp.get("rsi"), "fear_greed": fg, "price": opp.get("price"),
            "amount_usd": amt, "premium_pct": fv.get("premium_pct"), "fair": fv.get("fair"),
            "note": f"opportunité {opp['score']:.2f} -> DCA {amt}$"}


def _live_armed():
    """Le trading RÉEL est-il armé par le mandat ? False par défaut -> paper.
    Le réel (achat spot) passera par le MCP Bitget (Agent Hub), JAMAIS d'ordre en
    dur ici : ce dépôt reste le cerveau, le MCP est les mains."""
    try:
        import mandate
        return bool(mandate.live_enabled())
    except Exception:
        return False


def real_spot_balance():
    """Solde SPOT réel (USDT) via le pont Agent Hub, en lecture seule. None si indispo."""
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


def gate_advice(amount_usd, spot_balance):
    """Avis ADVISORY du mandat sur l'achat DCA (jamais d'ordre). Distingue le verrou
    paper des vrais blocages. Retourne {verdict, would_if_armed, blocks, live} ou None."""
    try:
        import bitget_hub_bridge as hub
        eq = spot_balance if spot_balance is not None else _cfg("MANDATE_CAPITAL_USDT", 1000.0)
        v = hub.gate_decision({"market": "spot", "symbol": "BTCUSDT", "side": "buy",
                               "equity_usd": eq, "notional_usd": amount_usd or 0,
                               "equity_curve": [eq]})
        non_lock = [b for b in v.get("blocks", []) if "verrou" not in b.lower()]
        return {"verdict": v.get("verdict"), "would_if_armed": not non_lock,
                "blocks": non_lock, "live": v.get("live")}
    except Exception:
        return None


def _autonomous_decision(second_lock, live_armed):
    """Double verrou (PUR, testable) : l'autonome réel exige les DEUX verrous."""
    return bool(second_lock) and bool(live_armed)


def _autonomous_live():
    """L'accumulation RÉELLE autonome est-elle armée ? DOUBLE verrou : le verrou réel
    global (MANDATE_LIVE_ENABLED) ET le verrou dédié ACCUM_AUTONOMOUS_LIVE. Les deux
    doivent être True pour qu'un achat réel parte tout seul.

    Le 2e verrou s'arme via .env (ACCUM_AUTONOMOUS_LIVE=1) OU config — l'option .env
    évite d'éditer un fichier suivi par git (sinon `git pull --ff-only` échouerait)."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    env_on = os.getenv("ACCUM_AUTONOMOUS_LIVE", "").strip().lower() in ("1", "true", "yes", "on")
    second = env_on or bool(_cfg("ACCUM_AUTONOMOUS_LIVE", False))
    return _autonomous_decision(second, _live_armed())


def _run_real(a, now):
    """Cycle d'accumulation RÉELLE autonome (double verrou armé). Achat via spot_executor
    (toutes ses gardes : USDT libre, kill-switch, plafonds, idempotence), throttlé sur le
    registre RÉEL (1/jour), montant plafonné. Ne passe par AUCUN ordre en dur ici."""
    import spot_executor as se
    buys = se._load_real().get("buys", [])
    last_real = buys[-1]["ts"] if buys else None
    # Plafond/achat ALIGNÉ sur spot_executor (fallback 5 $, jamais 50) : on clampe le
    # montant DCA au cap réel au lieu de proposer plus, ce que spot_executor rejetterait
    # en bloc. spot_executor reste le backstop strict (mur absolu 25, _capped).
    amount = min(float(a.get("amount_usd") or 0), float(_cfg("ACCUM_REAL_MAX_PER_BUY_USDT", 5.0)))
    a["mode"] = "RÉEL (auto)"
    # garde MEILLEUR PRIX : pas d'achat si Bitget cote en premium vs la médiane marché.
    # FAIL-CLOSED : si la garde premium est illisible (fair_price KO), on s'abstient
    # plutôt que d'acheter à l'aveugle au-dessus du marché.
    try:
        import fair_price as fp
        fair_ok = fp.is_fair_to_buy(a.get("premium_pct"), _cfg("ACCUM_MAX_PREMIUM_PCT", 0.30))
    except Exception:
        fair_ok = False
    if a.get("price") and amount > 0 and fair_ok and should_buy(last_real, now):
        res = se.execute(amount, confirm=True, now=now)
        a["bought"] = bool(res.get("executed"))
        a["real_exec"] = {"executed": res.get("executed"), "reasons": res.get("reasons")}
        buys = se._load_real().get("buys", [])
    else:
        a["bought"] = False
        if not fair_ok:
            a["skip_reason"] = ("garde premium indisponible ou Bitget en premium "
                                f"({a.get('premium_pct')}%) -> on n'accumule pas au-dessus du marché")
    a["ledger"] = {"real_spent_usd": round(sum(float(b.get("amount_usdt", 0)) for b in buys), 2),
                   "n_buys": len(buys)}
    return a


def run(symbol="BTCUSDT", now=None):
    """Un cycle d'accumulation. PAPER par défaut ; RÉEL autonome seulement si le DOUBLE
    verrou est armé (MANDATE_LIVE_ENABLED + ACCUM_AUTONOMOUS_LIVE). Best-effort.

    En réel : achat spot BTC via spot_executor (gardes : USDT libre, kill-switch,
    plafond/achat, plafond journalier, idempotence), throttlé 1/jour. Sinon paper."""
    a = analyze(symbol)
    now = time.time() if now is None else now
    a["live_armed"] = _live_armed()
    a["spot_balance"] = real_spot_balance()
    a["gate"] = gate_advice(a.get("amount_usd"), a.get("spot_balance"))

    if _autonomous_live():
        return _run_real(a, now)

    # --- chemin PAPER (défaut) ---
    led = load_ledger()
    a["mode"] = "paper"
    if a.get("price") and should_buy(led.get("last_buy_ts"), now):
        led = apply_buy(led, a["amount_usd"], a["price"], ts=now, score=a["score"])
        save_ledger(led)
        a["bought"] = True
    else:
        a["bought"] = False
    a["ledger"] = {k: led.get(k) for k in ("total_btc", "total_cost_usd", "avg_price", "n_buys")}
    return a


def build_report(a):
    led = a.get("ledger", {})
    mode = a.get("mode", "paper")
    bal = a.get("spot_balance")
    g = a.get("gate") or {}
    if g:
        if g.get("would_if_armed"):
            advis = "passerait le mandat (seul le verrou paper bloque)" if not g.get("live") \
                else "AUTORISÉ par le mandat"
        else:
            advis = "bloqué par le mandat : " + " ; ".join(g.get("blocks", []))
    else:
        advis = "avis mandat indisponible"
    bal_line = (f"Solde spot libre : {round(bal, 2)} USDT\n" if bal is not None
                else "Solde spot libre : non lu\n")
    p = a.get("premium_pct")
    prem_line = (f"Prix vs marché : Bitget {p:+.2f}% vs médiane cross-exchange\n"
                 if p is not None else "")
    skip_line = (f"⚠ {a.get('skip_reason')}\n" if a.get("skip_reason") else "")
    if "real_spent_usd" in led:
        cumul = (f"Cumul RÉEL : {led.get('real_spent_usd', 0)} $ investis "
                 f"({led.get('n_buys', 0)} achats)")
    else:
        cumul = (f"Cumul paper : {led.get('total_btc', 0)} BTC · prix moyen "
                 f"{led.get('avg_price', 0)} $ ({led.get('n_buys', 0)} achats)")
    return ("=== ACCUMULATION BTC (spot DCA) ===\n"
            f"Mode : {mode}\n"
            + bal_line + prem_line + skip_line +
            f"Opportunité d'achat : {a.get('score', 0):.2f}  (RSI {a.get('rsi')} · "
            f"F&G {a.get('fear_greed')})\n"
            f"DCA recommandé : {a.get('amount_usd')} $  ({advis})  "
            f"{('-> ACHAT ' + mode + ' journalisé') if a.get('bought') else '(intervalle non écoulé)'}\n"
            + cumul + "\n"
            "Spot, on ne vend jamais (hold). EARN: piste future. VERDICT: SAFE")


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(run(sym)))


if __name__ == "__main__":
    main()
