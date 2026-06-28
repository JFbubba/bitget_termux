

from candle_reader import get_bitget_candles


from indicators import ema, calculate_rsi


def analyze_decision(symbol="BTCUSDT"):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    closes = [candle["close"] for candle in candles]

    ema9_values = ema(closes, 9)
    ema21_values = ema(closes, 21)
    rsi_values = calculate_rsi(closes, 14)

    last_close = closes[-1]
    last_ema9 = ema9_values[-1]
    last_ema21 = ema21_values[-1]
    last_rsi = rsi_values[-1]

    ema_distance_percent = ((last_ema9 - last_ema21) / last_ema21) * 100

    score = 0
    reasons = []

    if last_ema9 > last_ema21:
        score += 1
        reasons.append("EMA9 > EMA21")
    elif last_ema9 < last_ema21:
        score -= 1
        reasons.append("EMA9 < EMA21")

    if ema_distance_percent > 0.05:
        score += 1
        reasons.append("distance EMA haussière significative")
    elif ema_distance_percent < -0.05:
        score -= 1
        reasons.append("distance EMA baissière significative")

    if 55 <= last_rsi < 70:
        score += 1
        reasons.append("RSI haussier sans surachat")
    elif 30 < last_rsi <= 45:
        score -= 1
        reasons.append("RSI baissier sans survente")
    elif last_rsi >= 70:
        score -= 1
        reasons.append("RSI en surachat")
    elif last_rsi <= 30:
        score += 1
        reasons.append("RSI en survente")

    if score >= 3:
        decision = "LONG POSSIBLE"
    elif score <= -3:
        decision = "SHORT POSSIBLE"
    elif score == 2:
        decision = "BIAIS LONG"
    elif score == -2:
        decision = "BIAIS SHORT"
    else:
        decision = "NEUTRE / ATTENDRE"

    return {
        "symbol": symbol,
        "last_close": last_close,
        "ema9": last_ema9,
        "ema21": last_ema21,
        "ema_distance_percent": ema_distance_percent,
        "rsi": last_rsi,
        "score": score,
        "decision": decision,
        "reasons": reasons,
        "candles": candles,
    }


def build_trade_plan(analysis):
    decision = analysis["decision"]
    entry = analysis["last_close"]
    candles = analysis["candles"]

    recent_lows = [candle["low"] for candle in candles[-10:]]
    recent_highs = [candle["high"] for candle in candles[-10:]]

    recent_low = min(recent_lows)
    recent_high = max(recent_highs)

    if decision in ["LONG POSSIBLE", "BIAIS LONG"]:
        stop_loss = recent_low
        risk = entry - stop_loss

        if risk <= 0:
            return None

        take_profit = entry + (risk * 2)

        risk_percent = (risk / entry) * 100
        reward_percent = ((take_profit - entry) / entry) * 100
        reward_risk_ratio = (take_profit - entry) / risk

        return {
            "side": "LONG",
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_percent": risk_percent,
            "reward_percent": reward_percent,
            "reward_risk_ratio": reward_risk_ratio,
        }

    elif decision in ["SHORT POSSIBLE", "BIAIS SHORT"]:
        stop_loss = recent_high
        risk = stop_loss - entry

        if risk <= 0:
            return None

        take_profit = entry - (risk * 2)

        risk_percent = (risk / entry) * 100
        reward_percent = ((entry - take_profit) / entry) * 100
        reward_risk_ratio = (entry - take_profit) / risk

        return {
            "side": "SHORT",
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_percent": risk_percent,
            "reward_percent": reward_percent,
            "reward_risk_ratio": reward_risk_ratio,
        }

    return None


if __name__ == "__main__":
    analysis = analyze_decision("BTCUSDT")
    plan = build_trade_plan(analysis)

    print("=== BITGET TRADE PLAN ===")
    print(f"Symbole: {analysis['symbol']}")
    print(f"Décision: {analysis['decision']}")
    print(f"Score: {analysis['score']}")
    print(f"RSI 14: {analysis['rsi']:.2f}")
    print(f"Distance EMA9/EMA21: {analysis['ema_distance_percent']:.4f}%")
    print()

    print("Raisons:")
    for reason in analysis["reasons"]:
        print(f"- {reason}")

    print()

    if plan is None:
        print("Aucun plan de trade théorique : signal insuffisant ou risque invalide.")
    else:
        print("Plan théorique:")
        print(f"Side: {plan['side']}")
        print(f"Entrée: {plan['entry']:.2f}")
        print(f"Stop-loss: {plan['stop_loss']:.2f}")
        print(f"Take-profit: {plan['take_profit']:.2f}")
        print(f"Risque: {plan['risk_percent']:.3f}%")
        print(f"Gain potentiel: {plan['reward_percent']:.3f}%")
        print(f"Ratio reward/risk: {plan['reward_risk_ratio']:.2f}")
        print()
        print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
