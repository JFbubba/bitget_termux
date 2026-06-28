"""candle_reader.py — source UNIQUE et RÉSILIENTE des bougies OHLCV (lecture seule).

Classement : SAFE. Données marché publiques, aucun ordre, aucun secret.

Cette fonction est le SEUL point d'accès aux bougies pour le cerveau et les
scanners (decision_engine, ranked_scanner, atr_trade_plan, position_sizer, ...).
Auparavant chaque module dupliquait un `requests.get` brut sans aucune protection :
un simple blip transitoire de l'API Bitget (timeout / rate-limit) renvoyait alors
une exception ou une série vide qui se propageait dans la décision. On centralise
ici avec deux couches de résilience, comme le fait déjà `market_sources` pour le
dashboard :

  1. Bitget REST avec RETRY + backoff (3 tentatives) ;
  2. repli CoinGecko (hôte indépendant) si Bitget reste KO — best-effort,
     granularité ~30 min et SANS volume (`volume_base = volume_quote = 0.0`),
     mieux qu'une série vide quand le primaire est indisponible.

Contrat d'échec préservé : si Bitget ET CoinGecko échouent, on LÈVE (comme avant),
pour que l'appelant saute le symbole comme aujourd'hui. On ajoute de la
résilience, on ne change pas la sémantique d'échec.
"""

import time
from datetime import datetime

import requests

BITGET_CANDLES_URL = "https://api.bitget.com/api/v2/mix/market/candles"
_RETRIES = 3
_BACKOFF_BASE = 0.5  # 0.5s, 1s, 2s entre les tentatives


def _bitget_candles(symbol, product_type, granularity, limit):
    """Fetch Bitget avec retry + backoff. Lève si les 3 tentatives échouent."""
    params = {
        "symbol": symbol,
        "productType": product_type,
        "granularity": granularity,
        "limit": str(limit),
    }
    last_error = None
    for attempt in range(_RETRIES):
        try:
            response = requests.get(BITGET_CANDLES_URL, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            if result.get("code") != "00000":
                raise RuntimeError(f"Erreur Bitget: {result}")
            return [
                {
                    "time": datetime.fromtimestamp(int(row[0]) / 1000),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume_base": float(row[5]),
                    "volume_quote": float(row[6]),
                }
                for row in result["data"]
            ]
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            last_error = exc
            if attempt < _RETRIES - 1:
                time.sleep(_BACKOFF_BASE * (2 ** attempt))
    raise last_error


def _coingecko_candles(symbol, limit):
    """Repli best-effort CoinGecko (sans volume). Lève si indisponible."""
    import market_sources  # import paresseux : évite tout coût/circularité au chargement

    cid = market_sources.coingecko_id(symbol)
    if not cid:
        raise RuntimeError(f"Pas d'identifiant CoinGecko pour {symbol}")
    url = f"https://api.coingecko.com/api/v3/coins/{cid}/ohlc?vs_currency=usd&days=1"
    response = requests.get(url, timeout=8)
    response.raise_for_status()
    rows = response.json()
    candles = [
        {
            "time": datetime.fromtimestamp(int(row[0]) / 1000),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume_base": 0.0,
            "volume_quote": 0.0,
        }
        for row in rows
        if len(row) >= 5
    ]
    if not candles:
        raise RuntimeError(f"CoinGecko OHLC vide pour {symbol}")
    return candles[-limit:]


def get_bitget_candles(symbol="BTCUSDT", product_type="USDT-FUTURES", granularity="15m", limit=100):
    """Bougies OHLCV [dict ...] résilientes : Bitget (retry) -> repli CoinGecko.

    Renvoie une liste de dicts triés par temps croissant :
    {time, open, high, low, close, volume_base, volume_quote}.
    Lève si les deux fournisseurs échouent (contrat d'échec inchangé)."""
    try:
        candles = _bitget_candles(symbol, product_type, granularity, limit)
    except Exception:
        # Bitget KO après retries : on tente le repli indépendant CoinGecko.
        candles = _coingecko_candles(symbol, limit)

    candles.sort(key=lambda candle: candle["time"])
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
