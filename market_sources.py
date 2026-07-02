"""
market_sources.py — accès marché RÉSILIENT multi-fournisseurs (lecture seule).

Classement : SAFE. Données publiques, aucun ordre. Le cerveau ne doit pas être
aveuglé si UN fournisseur tombe : on lit chez un fournisseur PRIMAIRE (Bitget
REST, déjà utilisé partout) et, en cas d'échec, on REPLIE sur un fournisseur
INDÉPENDANT (CoinGecko — hôte différent, donc vraie redondance). Tout passe par
`runtime_cache` (TTL + stale-while-error), si bien qu'aucune source n'est
appelée plus souvent que nécessaire et qu'une panne ne bloque jamais la décision.

Note réseau (re-sondé 2026-07-02) : Binance et OKX répondent de nouveau 200
depuis ce VPS (l'ancien géo-blocage 451/403 constaté plus tôt a disparu — la
sortie réseau passe désormais par un POP différent). La redondance primaire
reste Bitget + CoinGecko ; les venues Binance/OKX/Bybit sont exploitées comme
sources ADDITIVES best-effort (derivs_positioning, aggregated_derivs), jamais
comme dépendance critique : chaque venue dégrade en None indépendamment.

Les helpers de mapping/normalisation sont PURS et testables ; les fetch réseau
sont enveloppés (try/except) et ne lèvent jamais vers l'appelant.
"""

import json
import urllib.request

import runtime_cache as rc

_QUOTES = ("USDT", "USDC", "USD", "BUSD")

# Map minimal symbole -> identifiant CoinGecko (majors ; étendable).
_COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "LTC": "litecoin", "LINK": "chainlink", "MATIC": "matic-network", "DOT": "polkadot",
    "TRX": "tron", "ATOM": "cosmos", "UNI": "uniswap", "BCH": "bitcoin-cash",
}


def split_symbol(symbol):
    """'BTCUSDT' -> ('BTC', 'USDT'). Pur. Quote vide si non reconnue."""
    s = str(symbol).upper()
    for q in _QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return s[:-len(q)], q
    return s, ""


def coingecko_id(symbol):
    """Identifiant CoinGecko pour le symbole, ou None. Pur."""
    base, _ = split_symbol(symbol)
    return _COINGECKO_IDS.get(base)


def _bitget_closes(symbol, limit):
    import technicals as tk
    return [float(c["close"]) for c in tk.fetch_candles(symbol, "15m", limit)]


def _coingecko_closes(symbol, limit):
    cid = coingecko_id(symbol)
    if not cid:
        return []
    url = f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart?vs_currency=usd&days=1"
    with urllib.request.urlopen(url, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    prices = [float(p[1]) for p in data.get("prices", []) if len(p) >= 2]
    return prices[-limit:]


def closes(symbol, limit=120, ttl=60):
    """Série de clôtures résiliente : Bitget (primaire) -> CoinGecko (repli).

    Passe par runtime_cache : dans le TTL aucune requête, et sur panne des deux
    fournisseurs on sert la dernière série connue (sinon liste vide). Best-effort,
    ne lève jamais."""
    def fetch():
        for provider in (_bitget_closes, _coingecko_closes):
            try:
                c = provider(symbol, limit)
                if c and len(c) >= 20:
                    return c
            except Exception:
                continue
        return []
    return rc.get(f"closes:{symbol.upper()}:15m", ttl, fetch, fallback=[])


def _bitget_candles(symbol, timeframe, limit):
    import technicals as tk
    cs = tk.fetch_candles(symbol, timeframe, limit)
    return [[int(c["ts"] // 1000), float(c["open"]), float(c["high"]),
             float(c["low"]), float(c["close"]), float(c.get("volume", 0) or 0)] for c in cs]


def _coingecko_candles(symbol, limit):
    cid = coingecko_id(symbol)
    if not cid:
        return []
    url = f"https://api.coingecko.com/api/v3/coins/{cid}/ohlc?vs_currency=usd&days=1"
    with urllib.request.urlopen(url, timeout=8) as r:
        rows = json.loads(r.read().decode("utf-8"))
    # CoinGecko /ohlc : [[ts_ms, o, h, l, c], ...] (granularité ~30 min, sans volume)
    out = [[int(x[0] // 1000), float(x[1]), float(x[2]), float(x[3]), float(x[4]), 0.0]
           for x in rows if len(x) >= 5]
    return out[-limit:]


def candles(symbol, timeframe="5m", limit=60, ttl=20):
    """Bougies OHLCV résilientes [t_s, o, h, l, c, v] : Bitget -> CoinGecko (repli).

    Le repli CoinGecko est best-effort (granularité ~30 min, volume=0) : mieux
    qu'un graphique vide quand le fournisseur primaire est indisponible. Cachée,
    ne lève jamais."""
    def fetch():
        for provider in ((lambda: _bitget_candles(symbol, timeframe, limit)),
                         (lambda: _coingecko_candles(symbol, limit))):
            try:
                c = provider()
                if c and len(c) >= 10:
                    return c
            except Exception:
                continue
        return []
    return rc.get(f"candles:{symbol.upper()}:{timeframe}", ttl, fetch, fallback=[])
