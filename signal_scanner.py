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


def analyze_market(ticker):
    if "error" in ticker:
        return "ERREUR", ticker["error"]

    change = ticker["change_24h_percent"]
    funding = ticker["funding_rate_percent"]
    price = ticker["last_price"]
    high = ticker["high_24h"]
    low = ticker["low_24h"]

    range_24h = high - low
    position_in_range = ((price - low) / range_24h) * 100 if range_24h > 0 else 50

    warnings = []

    if funding > 0.03:
        warnings.append("funding long cher")
    elif funding < -0.03:
        warnings.append("funding short cher")

    if position_in_range > 85:
        warnings.append("proche haut 24h")
    elif position_in_range < 15:
        warnings.append("proche bas 24h")

    if change > 3 and position_in_range > 75:
        signal = "SURCHAUFFE"
        reason = "forte hausse + prix haut dans le range 24h"
    elif change > 1 and 40 <= position_in_range <= 80:
        signal = "HAUSSIER"
        reason = "hausse modérée avec prix encore exploitable"
    elif -1 <= change <= 1:
        signal = "NEUTRE"
        reason = "variation 24h faible"
    elif change < -2 and position_in_range < 40:
        signal = "BAISSIER"
        reason = "baisse marquée et prix faible dans le range 24h"
    else:
        signal = "INCERTAIN"
        reason = "conditions mixtes"

    if warnings:
        reason += " | attention: " + ", ".join(warnings)

    return signal, reason


def print_signal_row(ticker):
    if "error" in ticker:
        print(f"{ticker['symbol']:<10} ERREUR: {ticker['error']}")
        return

    signal, reason = analyze_market(ticker)

    print(
        f"{ticker['symbol']:<10} "
        f"Prix: {ticker['last_price']:>12,.4f} | "
        f"24h: {ticker['change_24h_percent']:>7.2f}% | "
        f"Funding: {ticker['funding_rate_percent']:>8.4f}% | "
        f"Signal: {signal:<10} | "
        f"{reason}"
    )


if __name__ == "__main__":
    print("=== BITGET SIGNAL SCANNER ===")
    print()

    for symbol in SYMBOLS:
        ticker = get_bitget_ticker(symbol)
        print_signal_row(ticker)
        time.sleep(0.2)
