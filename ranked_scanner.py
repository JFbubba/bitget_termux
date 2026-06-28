import time


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "XAUTUSDT",
]

ACCOUNT_EQUITY_USDT = 100.0
RISK_PER_TRADE_PERCENT = 1.0
MAX_IMPLIED_LEVERAGE = 2.0


from candle_reader import get_bitget_candles


from indicators import ema, calculate_rsi, calculate_atr


def analyze_symbol(symbol):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    closes = [candle["close"] for candle in candles]

    ema9_values = ema(closes, 9)
    ema21_values = ema(closes, 21)
    rsi_values = calculate_rsi(closes, 14)
    atr_values = calculate_atr(candles, 14)

    last_close = closes[-1]
    last_ema9 = ema9_values[-1]
    last_ema21 = ema21_values[-1]
    last_rsi = rsi_values[-1]
    last_atr = atr_values[-1]

    ema_distance_percent = ((last_ema9 - last_ema21) / last_ema21) * 100
    atr_percent = (last_atr / last_close) * 100

    score = 0
    reasons = []

    if last_ema9 > last_ema21:
        score += 1
        reasons.append("EMA+")
    elif last_ema9 < last_ema21:
        score -= 1
        reasons.append("EMA-")

    if ema_distance_percent > 0.05:
        score += 1
        reasons.append("EMA distance+")
    elif ema_distance_percent < -0.05:
        score -= 1
        reasons.append("EMA distance-")

    if 55 <= last_rsi < 70:
        score += 1
        reasons.append("RSI+")
    elif 30 < last_rsi <= 45:
        score -= 1
        reasons.append("RSI-")
    elif last_rsi >= 70:
        score -= 1
        reasons.append("RSI surachat")
    elif last_rsi <= 30:
        score += 1
        reasons.append("RSI survente")

    if score >= 3:
        decision = "LONG POSSIBLE"
    elif score <= -3:
        decision = "SHORT POSSIBLE"
    elif score == 2:
        decision = "BIAIS LONG"
    elif score == -2:
        decision = "BIAIS SHORT"
    else:
        decision = "NEUTRE"

    return {
        "symbol": symbol,
        "last_close": last_close,
        "ema_distance_percent": ema_distance_percent,
        "rsi": last_rsi,
        "atr": last_atr,
        "atr_percent": atr_percent,
        "score": score,
        "decision": decision,
        "reasons": reasons,
        "candles": candles,
    }


def build_trade_plan(analysis):
    decision = analysis["decision"]
    entry = analysis["last_close"]
    candles = analysis["candles"]
    atr = analysis["atr"]

    recent_lows = [candle["low"] for candle in candles[-10:]]
    recent_highs = [candle["high"] for candle in candles[-10:]]

    recent_low = min(recent_lows)
    recent_high = max(recent_highs)

    if decision in ["LONG POSSIBLE", "BIAIS LONG"]:
        structural_stop = recent_low
        atr_stop = entry - (atr * 1.5)
        stop_loss = min(structural_stop, atr_stop)

        risk_per_unit = entry - stop_loss
        if risk_per_unit <= 0:
            return None

        take_profit = entry + (risk_per_unit * 2)
        side = "LONG"

    elif decision in ["SHORT POSSIBLE", "BIAIS SHORT"]:
        structural_stop = recent_high
        atr_stop = entry + (atr * 1.5)
        stop_loss = max(structural_stop, atr_stop)

        risk_per_unit = stop_loss - entry
        if risk_per_unit <= 0:
            return None

        take_profit = entry - (risk_per_unit * 2)
        side = "SHORT"

    else:
        return None

    risk_percent_price = (risk_per_unit / entry) * 100
    reward_percent_price = risk_percent_price * 2

    max_risk_usdt = ACCOUNT_EQUITY_USDT * (RISK_PER_TRADE_PERCENT / 100)
    base_size = max_risk_usdt / risk_per_unit
    notional_position_usdt = base_size * entry
    implied_leverage = notional_position_usdt / ACCOUNT_EQUITY_USDT

    accepted = implied_leverage <= MAX_IMPLIED_LEVERAGE

    if accepted:
        status = "ACCEPTÉ"
        rejection_reason = ""
    else:
        status = "REFUSÉ"
        rejection_reason = f"levier implicite {implied_leverage:.2f}x > max {MAX_IMPLIED_LEVERAGE:.2f}x"

    return {
        "side": side,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_percent_price": risk_percent_price,
        "reward_percent_price": reward_percent_price,
        "base_size": base_size,
        "notional_position_usdt": notional_position_usdt,
        "implied_leverage": implied_leverage,
        "accepted": accepted,
        "status": status,
        "rejection_reason": rejection_reason,
    }


def rank_score(analysis, plan):
    if plan is None:
        return -999

    score = analysis["score"]

    if plan["accepted"]:
        score += 2
    else:
        score -= 2

    if 55 <= analysis["rsi"] <= 65:
        score += 1

    if analysis["atr_percent"] > 1.0:
        score -= 1

    return score


def format_no_plan(analysis):
    reasons = ",".join(analysis["reasons"])

    return (
        f"{analysis['symbol']:<10} "
        f"PAS DE PLAN | "
        f"Prix: {analysis['last_close']:>12,.4f} | "
        f"Score: {analysis['score']:>2} | "
        f"RSI: {analysis['rsi']:>6.2f} | "
        f"ATR%: {analysis['atr_percent']:>6.3f}% | "
        f"Décision: {analysis['decision']:<14} | "
        f"{reasons}"
    )


def format_plan(analysis, plan, ranking):
    line = (
        f"{analysis['symbol']:<10} "
        f"{plan['status']:<7} | "
        f"{plan['side']:<5} | "
        f"Rank: {ranking:>2} | "
        f"Prix: {analysis['last_close']:>12,.4f} | "
        f"Score: {analysis['score']:>2} | "
        f"RSI: {analysis['rsi']:>6.2f} | "
        f"SL: {plan['stop_loss']:>12,.4f} | "
        f"TP: {plan['take_profit']:>12,.4f} | "
        f"Risque: {plan['risk_percent_price']:>6.3f}% | "
        f"Notionnel: {plan['notional_position_usdt']:>8.2f} USDT | "
        f"Lev: {plan['implied_leverage']:>5.2f}x"
    )

    if not plan["accepted"]:
        line += f" | {plan['rejection_reason']}"

    return line


if __name__ == "__main__":
    print("=== BITGET RANKED SCANNER ===")
    print(f"Capital théorique: {ACCOUNT_EQUITY_USDT:.2f} USDT")
    print(f"Risque par trade: {RISK_PER_TRADE_PERCENT:.2f}%")
    print(f"Levier implicite max: {MAX_IMPLIED_LEVERAGE:.2f}x")
    print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
    print()

    results = []

    for symbol in SYMBOLS:
        try:
            analysis = analyze_symbol(symbol)
            plan = build_trade_plan(analysis)
            ranking = rank_score(analysis, plan)

            results.append({
                "analysis": analysis,
                "plan": plan,
                "ranking": ranking,
            })

            time.sleep(0.2)

        except Exception as error:
            print(f"{symbol:<10} ERREUR: {error}")

    results.sort(key=lambda item: item["ranking"], reverse=True)

    for item in results:
        analysis = item["analysis"]
        plan = item["plan"]
        ranking = item["ranking"]

        if plan is None:
            print(format_no_plan(analysis))
        else:
            print(format_plan(analysis, plan, ranking))
