

from candle_reader import get_bitget_candles


def ema(values, period):
    if len(values) < period:
        raise ValueError("Pas assez de données pour calculer l'EMA")

    multiplier = 2 / (period + 1)
    ema_values = []

    first_ema = sum(values[:period]) / period
    ema_values.append(first_ema)

    for price in values[period:]:
        next_ema = (price - ema_values[-1]) * multiplier + ema_values[-1]
        ema_values.append(next_ema)

    return ema_values


def calculate_rsi(values, period=14):
    if len(values) <= period:
        raise ValueError("Pas assez de données pour calculer le RSI")

    gains = []
    losses = []

    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    rsi_values = []

    if avg_loss == 0:
        rsi_values.append(100)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100 - (100 / (1 + rs)))

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]

        gain = max(change, 0)
        loss = abs(min(change, 0))

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            rsi_values.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))

    return rsi_values


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
