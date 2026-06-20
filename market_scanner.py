import requests
import time


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "XAUTUSDT",
]


def get_bitget_ticker(symbol, product_type="USDT-FUTURES"):
    url = "https://api.bitget.com/api/v2/mix/market/ticker"

    params = {
        "symbol": symbol,
        "productType": product_type,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    result = response.json()

    if result.get("code") != "00000":
        return {
            "symbol": symbol,
            "error": result.get("msg", "Erreur inconnue"),
        }

    data = result["data"][0]

    return {
        "symbol": data["symbol"],
        "last_price": float(data["lastPr"]),
        "mark_price": float(data["markPrice"]),
        "change_24h_percent": float(data["change24h"]) * 100,
        "funding_rate_percent": float(data["fundingRate"]) * 100,
        "high_24h": float(data["high24h"]),
        "low_24h": float(data["low24h"]),
        "volume_usdt_24h": float(data["usdtVolume"]),
    }


def print_market_row(ticker):
    if "error" in ticker:
        print(f"{ticker['symbol']:<10} ERREUR: {ticker['error']}")
        return

    print(
        f"{ticker['symbol']:<10} "
        f"Prix: {ticker['last_price']:>12,.4f} | "
        f"24h: {ticker['change_24h_percent']:>7.2f}% | "
        f"Funding: {ticker['funding_rate_percent']:>8.4f}% | "
        f"Volume: {ticker['volume_usdt_24h']:>15,.0f} USDT"
    )


if __name__ == "__main__":
    print("=== BITGET MARKET SCANNER ===")
    print()

    for symbol in SYMBOLS:
        ticker = get_bitget_ticker(symbol)
        print_market_row(ticker)
        time.sleep(0.2)
