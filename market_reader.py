"""market_reader.py — source UNIQUE et RÉSILIENTE du ticker Bitget (lecture seule).

Classement : SAFE. Données marché publiques, aucun ordre, aucun secret.

Pendant de `candle_reader` pour le ticker temps réel. Auparavant, le même
`requests.get` brut (sans protection) était dupliqué dans `market_scanner` et
`signal_scanner` : un simple blip transitoire de l'API (timeout / rate-limit)
faisait échouer la lecture. On centralise ici avec RETRY + backoff (3 tentatives).

Contrat : renvoie le dict complet (superset de champs) en succès, et LÈVE si les
3 tentatives échouent (contrat d'échec honnête, inchangé pour `market_reader`).
Les scanners enveloppent cet appel pour convertir l'échec en `{symbol, error}`
(cf. `market_scanner.get_bitget_ticker` / `signal_scanner.get_bitget_ticker`).
"""

import time

import requests

BITGET_TICKER_URL = "https://api.bitget.com/api/v2/mix/market/ticker"
_RETRIES = 3
_BACKOFF_BASE = 0.5  # 0.5s, 1s, 2s entre les tentatives


def get_bitget_ticker(symbol="BTCUSDT", product_type="USDT-FUTURES"):
    """Ticker Bitget [dict] résilient : Bitget REST avec retry + backoff.

    Renvoie un dict complet {symbol, last_price, mark_price, bid, ask, high_24h,
    low_24h, change_24h_percent, funding_rate_percent, volume_base_24h,
    volume_usdt_24h}. Lève si les 3 tentatives échouent (contrat d'échec)."""
    params = {
        "symbol": symbol,
        "productType": product_type,
    }
    last_error = None
    for attempt in range(_RETRIES):
        try:
            response = requests.get(BITGET_TICKER_URL, params=params, timeout=10)
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
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            last_error = exc
            if attempt < _RETRIES - 1:
                time.sleep(_BACKOFF_BASE * (2 ** attempt))
    raise last_error


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
