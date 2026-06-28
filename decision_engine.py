

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
    }


if __name__ == "__main__":
    result = analyze_decision("BTCUSDT")

    print("=== BITGET DECISION ENGINE ===")
    print(f"Symbole: {result['symbol']}")
    print(f"Dernier close: {result['last_close']:.2f}")
    print(f"EMA 9: {result['ema9']:.2f}")
    print(f"EMA 21: {result['ema21']:.2f}")
    print(f"Distance EMA9/EMA21: {result['ema_distance_percent']:.4f}%")
    print(f"RSI 14: {result['rsi']:.2f}")
    print(f"Score: {result['score']}")
    print(f"Décision: {result['decision']}")
    print("Raisons:")
    for reason in result["reasons"]:
        print(f"- {reason}")
