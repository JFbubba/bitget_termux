import requests


def get_bitget_ticker(symbol="BTCUSDT", product_type="USDT-FUTURES"):
    url = "https://api.bitget.com/api/v2/mix/market/ticker"

    params = {
        "symbol": symbol,
        "productType": product_type,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    result = response.json()

    if result.get("code") != "00000":
        raise RuntimeError(f"Erreur Bitget: {result}")

    data = result["data"][0]

    return {
        "symbol": data["symbol"],
        "last_price": float(data["lastPr"]),
        "mark_price": float(data["markPrice"]),
        "bid": float(data["bidPr"]),
        "ask": float(data["askPr"]),
        "high_24h": float(data["high24h"]),
        "low_24h": float(data["low24h"]),
        "change_24h_percent": float(data["change24h"]) * 100,
        "funding_rate_percent": float(data["fundingRate"]) * 100,
        "volume_base_24h": float(data["baseVolume"]),
        "volume_usdt_24h": float(data["usdtVolume"]),
    }


if __name__ == "__main__":
    ticker = get_bitget_ticker("BTCUSDT")

    print("=== BITGET MARKET READER ===")
    print(f"Symbole: {ticker['symbol']}")
    print(f"Dernier prix: {ticker['last_price']}")
    print(f"Mark price: {ticker['mark_price']}")
    print(f"Bid: {ticker['bid']}")
    print(f"Ask: {ticker['ask']}")
    print(f"Haut 24h: {ticker['high_24h']}")
    print(f"Bas 24h: {ticker['low_24h']}")
    print(f"Variation 24h: {ticker['change_24h_percent']:.2f}%")
    print(f"Funding rate: {ticker['funding_rate_percent']:.4f}%")
    print(f"Volume 24h: {ticker['volume_base_24h']:.2f} BTC")
    print(f"Volume USDT 24h: {ticker['volume_usdt_24h']:.2f} USDT")
