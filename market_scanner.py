import time

from market_reader import get_bitget_ticker as _read_ticker


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "XAUTUSDT",
]


def get_bitget_ticker(symbol, product_type="USDT-FUTURES"):
    """Ticker résilient (retry+backoff via market_reader), échec -> dict d'erreur.

    Préserve le contrat historique du scanner : en cas d'échec, renvoie
    `{symbol, error}` au lieu de lever, pour que `print_market_row` affiche la
    ligne d'erreur et continue sur les symboles suivants."""
    try:
        return _read_ticker(symbol, product_type)
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc)}


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
