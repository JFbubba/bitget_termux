import requests
from datetime import datetime


def get_bitget_candles(symbol="BTCUSDT", product_type="USDT-FUTURES", granularity="15m", limit=20):
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


if __name__ == "__main__":
    candles = get_bitget_candles("BTCUSDT", granularity="15m", limit=20)

    print("=== BITGET CANDLE READER ===")
    print("Symbole: BTCUSDT")
    print("Timeframe: 15m")
    print()

    for candle in candles[-10:]:
        print(
            f"{candle['time']} | "
            f"O: {candle['open']} | "
            f"H: {candle['high']} | "
            f"L: {candle['low']} | "
            f"C: {candle['close']} | "
            f"Vol: {candle['volume_base']:.2f}"
        )
