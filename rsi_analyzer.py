

from candle_reader import get_bitget_candles


def calculate_rsi(values, period=14):
    if len(values) <= period:
        raise ValueError("Pas assez de données pour calculer le RSI")

    gains = []
    losses = []

    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

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


def interpret_rsi(rsi):
    if rsi >= 70:
        return "SURACHAT"
    elif rsi <= 30:
        return "SURVENTE"
    elif rsi > 55:
        return "BIAIS HAUSSIER"
    elif rsi < 45:
        return "BIAIS BAISSIER"
    else:
        return "NEUTRE"


def analyze_rsi(symbol="BTCUSDT"):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    closes = [candle["close"] for candle in candles]

    rsi_values = calculate_rsi(closes, period=14)
    last_rsi = rsi_values[-1]
    interpretation = interpret_rsi(last_rsi)

    return {
        "symbol": symbol,
        "last_close": closes[-1],
        "rsi": last_rsi,
        "interpretation": interpretation,
    }


if __name__ == "__main__":
    result = analyze_rsi("BTCUSDT")

    print("=== BITGET RSI ANALYZER ===")
    print(f"Symbole: {result['symbol']}")
    print(f"Dernier close: {result['last_close']:.2f}")
    print(f"RSI 14: {result['rsi']:.2f}")
    print(f"Lecture RSI: {result['interpretation']}")
