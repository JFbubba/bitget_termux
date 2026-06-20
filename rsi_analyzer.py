import requests
from datetime import datetime


def get_bitget_candles(symbol="BTCUSDT", product_type="USDT-FUTURES", granularity="15m", limit=100):
    url = "https://api.bitget.com/api/v2/mix/market/candles"

    params = {
        "symbol": symbol,
        "productType": product_type,
        "granularity": granularity,
        "limit": str(limit),
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    result = response.json()

    if result.get("code") != "00000":
        raise RuntimeError(f"Erreur Bitget: {result}")

    candles = []

    for row in result["data"]:
        timestamp_ms = int(row[0])

        candles.append({
            "time": datetime.fromtimestamp(timestamp_ms / 1000),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume_base": float(row[5]),
            "volume_quote": float(row[6]),
        })

    candles.sort(key=lambda x: x["time"])
    return candles


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
