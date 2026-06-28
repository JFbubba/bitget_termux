

from candle_reader import get_bitget_candles


from indicators import calculate_rsi


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
