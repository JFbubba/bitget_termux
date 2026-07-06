

from candle_reader import get_bitget_candles


from indicators import ema, calculate_rsi, calculate_atr


def _rr():
    """Ratio take-profit / risque (§68 B). env ATR_TRADE_RR > config > 1.5 (optimum mesuré)."""
    import os
    v = os.getenv("ATR_TRADE_RR")
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    try:
        from config_utils import cfg
        return float(cfg("ATR_TRADE_RR", 1.5))
    except Exception:
        return 1.5


def analyze_decision(symbol="BTCUSDT"):
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

        risk = entry - stop_loss
        if risk <= 0:
            return None

        take_profit = entry + (risk * _rr())

        return {
            "side": "LONG",
            "entry": entry,
            "stop_loss": stop_loss,
            "structural_stop": structural_stop,
            "atr_stop": atr_stop,
            "take_profit": take_profit,
            "risk_percent": (risk / entry) * 100,
            "reward_percent": ((take_profit - entry) / entry) * 100,
            "reward_risk_ratio": (take_profit - entry) / risk,
        }

    if decision in ["SHORT POSSIBLE", "BIAIS SHORT"]:
        structural_stop = recent_high
        atr_stop = entry + (atr * 1.5)
        stop_loss = max(structural_stop, atr_stop)

        risk = stop_loss - entry
        if risk <= 0:
            return None

        take_profit = entry - (risk * _rr())

        return {
            "side": "SHORT",
            "entry": entry,
            "stop_loss": stop_loss,
            "structural_stop": structural_stop,
            "atr_stop": atr_stop,
            "take_profit": take_profit,
            "risk_percent": (risk / entry) * 100,
            "reward_percent": ((entry - take_profit) / entry) * 100,
            "reward_risk_ratio": (entry - take_profit) / risk,
        }

    return None


if __name__ == "__main__":
    analysis = analyze_decision("BTCUSDT")
    plan = build_trade_plan(analysis)

    print("=== BITGET ATR TRADE PLAN ===")
    print(f"Symbole: {analysis['symbol']}")
    print(f"Décision: {analysis['decision']}")
    print(f"Score: {analysis['score']}")
    print(f"RSI 14: {analysis['rsi']:.2f}")
    print(f"Distance EMA9/EMA21: {analysis['ema_distance_percent']:.4f}%")
    print(f"ATR 14: {analysis['atr']:.2f}")
    print(f"ATR %: {analysis['atr_percent']:.4f}%")
    print()

    print("Raisons:")
    for reason in analysis["reasons"]:
        print(f"- {reason}")

    print()

    if plan is None:
        print("Aucun plan de trade théorique : signal insuffisant ou risque invalide.")
    else:
        print("Plan théorique avec protection ATR:")
        print(f"Side: {plan['side']}")
        print(f"Entrée: {plan['entry']:.2f}")
        print(f"Stop structurel: {plan['structural_stop']:.2f}")
        print(f"Stop ATR 1.5x: {plan['atr_stop']:.2f}")
        print(f"Stop-loss retenu: {plan['stop_loss']:.2f}")
        print(f"Take-profit: {plan['take_profit']:.2f}")
        print(f"Risque: {plan['risk_percent']:.3f}%")
        print(f"Gain potentiel: {plan['reward_percent']:.3f}%")
        print(f"Ratio reward/risk: {plan['reward_risk_ratio']:.2f}")
        print()
        print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
