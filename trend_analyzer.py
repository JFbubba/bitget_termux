

from candle_reader import get_bitget_candles


from indicators import ema


def analyze_trend(symbol="BTCUSDT"):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    closes = [candle["close"] for candle in candles]

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)

    last_close = closes[-1]
    last_ema9 = ema9[-1]
    last_ema21 = ema21[-1]

    previous_ema9 = ema9[-2]
    previous_ema21 = ema21[-2]

    if last_ema9 > last_ema21 and previous_ema9 <= previous_ema21:
        signal = "CROISEMENT HAUSSIER"
    elif last_ema9 < last_ema21 and previous_ema9 >= previous_ema21:
        signal = "CROISEMENT BAISSIER"
    elif last_ema9 > last_ema21:
        signal = "TENDANCE HAUSSIÈRE"
    elif last_ema9 < last_ema21:
        signal = "TENDANCE BAISSIÈRE"
    else:
        signal = "NEUTRE"

    distance_percent = ((last_ema9 - last_ema21) / last_ema21) * 100

    return {
        "symbol": symbol,
        "last_close": last_close,
        "ema9": last_ema9,
        "ema21": last_ema21,
        "distance_percent": distance_percent,
        "signal": signal,
    }


if __name__ == "__main__":
    result = analyze_trend("BTCUSDT")

    print("=== BITGET TREND ANALYZER ===")
    print(f"Symbole: {result['symbol']}")
    print(f"Dernier close: {result['last_close']:.2f}")
    print(f"EMA 9: {result['ema9']:.2f}")
    print(f"EMA 21: {result['ema21']:.2f}")
    print(f"Distance EMA9/EMA21: {result['distance_percent']:.4f}%")
    print(f"Signal: {result['signal']}")
