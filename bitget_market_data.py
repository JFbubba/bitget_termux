"""
bitget_market_data.py — lecteur de microstructure Bitget (LECTURE SEULE).

Classement : SAFE.
  - n'appelle QUE des endpoints PUBLICS Bitget (aucune clé, aucune signature)
  - aucune écriture, aucun ordre, aucun secret
  - sépare le fetch réseau (impur) des parseurs (purs, testables)

Endpoints publics utilisés (api.bitget.com, v2 mix) :
  - merge-depth        -> carnet d'ordres (bids/asks)
  - fills              -> tape / Time & Sales (transactions récentes)
  - open-interest      -> intérêt ouvert
  - current-fund-rate  -> funding

Alimente order_flow.py (CVD, déséquilibre carnet, niveaux de liquidation).
CLI : python bitget_market_data.py [SYMBOL]
"""

import sys
import time

import requests

import config
import order_flow

BASE_URL = "https://api.bitget.com"
_RETRIES = 3
_BACKOFF_BASE = 0.5  # 0.5s, 1s, 2s entre les tentatives


# ---------- réseau (impur) ----------

def _get(path, params):
    """Fetch public Bitget avec RETRY + backoff (3 tentatives).

    Lève si les 3 tentatives échouent : les appelants `fetch_*` capturent et
    dégradent alors vers une valeur vide (carnet/trades/OI/funding). Le retry
    encaisse les blips transitoires (timeout / rate-limit) qui, sans lui,
    privaient le cerveau de microstructure pour tout un cycle."""
    last_error = None
    for attempt in range(_RETRIES):
        try:
            response = requests.get(BASE_URL + path, params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != "00000":
                raise RuntimeError(f"Bitget {path}: {payload}")
            return payload["data"]
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            last_error = exc
            if attempt < _RETRIES - 1:
                time.sleep(_BACKOFF_BASE * (2 ** attempt))
    raise last_error


def fetch_orderbook(symbol, product_type=None, limit="50"):
    # best-effort : carnet vide si la source est injoignable (jamais d'exception)
    try:
        return _get("/api/v2/mix/market/merge-depth", {
            "symbol": symbol,
            "productType": product_type or config.PRODUCT_TYPE,
            "limit": str(limit),
        })
    except Exception:
        return {"bids": [], "asks": []}


def fetch_spot_orderbook(symbol, limit="15"):
    """Carnet d'ordres SPOT (public v2, sans clé). Best-effort : carnet vide si la
    source est injoignable. Sert le market making §94 (le carnet mix ci-dessus est
    celui des FUTURES — les cotations spot exigent le carnet spot)."""
    try:
        return _get("/api/v2/spot/market/orderbook", {
            "symbol": symbol,
            "limit": str(limit),
        })
    except Exception:
        return {"bids": [], "asks": []}


def fetch_recent_trades(symbol, product_type=None, limit=100):
    # best-effort : aucune trade si la source est injoignable
    try:
        return _get("/api/v2/mix/market/fills", {
            "symbol": symbol,
            "productType": product_type or config.PRODUCT_TYPE,
            "limit": str(limit),
        })
    except Exception:
        return []


def fetch_open_interest(symbol, product_type=None):
    # best-effort : OI vide si la source est injoignable
    try:
        return _get("/api/v2/mix/market/open-interest", {
            "symbol": symbol,
            "productType": product_type or config.PRODUCT_TYPE,
        })
    except Exception:
        return {"openInterestList": []}


def fetch_funding_rate(symbol, product_type=None):
    # best-effort : funding indisponible si la source est injoignable
    try:
        return _get("/api/v2/mix/market/current-fund-rate", {
            "symbol": symbol,
            "productType": product_type or config.PRODUCT_TYPE,
        })
    except Exception:
        return []


def fetch_tickers(product_type=None):
    # best-effort : tickers de TOUS les symboles en UNE requête (liste vide si KO)
    try:
        return _get("/api/v2/mix/market/tickers", {
            "productType": product_type or config.PRODUCT_TYPE,
        })
    except Exception:
        return []


# ---------- parseurs (purs, testables) ----------

def parse_orderbook(data):
    """data {"bids":[[p,s],...],"asks":[...]} -> {bids, asks} en flottants."""
    bids = [[float(p), float(s)] for p, s in data.get("bids", [])]
    asks = [[float(p), float(s)] for p, s in data.get("asks", [])]
    return {"bids": bids, "asks": asks}


def parse_trades(data):
    """data [{"side","size","price",...}] -> [{side, size, price}] normalisé."""
    out = []
    for trade in data or []:
        out.append({
            "side": str(trade.get("side", "")).lower(),
            "size": float(trade.get("size", 0.0)),
            "price": float(trade.get("price", 0.0)),
        })
    return out


def parse_open_interest(data):
    """data {"openInterestList":[{"size"}...]} -> total (float)."""
    levels = data.get("openInterestList") or []
    return sum(float(x.get("size", 0.0)) for x in levels)


def parse_funding_rate(data):
    """data [{"fundingRate"}] (ou dict) -> taux de funding (float) ou None."""
    if isinstance(data, list):
        return float(data[0]["fundingRate"]) if data else None
    if isinstance(data, dict) and "fundingRate" in data:
        return float(data["fundingRate"])
    return None


def parse_ticker_prices(data):
    """data [{"symbol","lastPr",...}] -> {SYMBOL: dernier prix (float)}. PUR.
    Ignore les lignes mal formées (prix absent/invalide)."""
    out = {}
    for row in data or []:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol", "")).upper()
        if not sym:
            continue
        try:
            out[sym] = float(row.get("lastPr"))
        except (TypeError, ValueError):
            continue
    return out


# ---------- agrégat lecture seule ----------

def market_snapshot(symbol="BTCUSDT", product_type=None, depth=20, trades_limit=100):
    """Instantané microstructure (lecture seule) prêt pour analyse.

    Best-effort : les fetch_* dégradent déjà en forme vide ; cette garde globale
    couvre toute exception résiduelle (calculs sur données partielles) et retourne
    un instantané neutre plutôt que de lever vers l'appelant."""
    product_type = product_type or config.PRODUCT_TYPE
    try:
        book = parse_orderbook(fetch_orderbook(symbol, product_type))
        trades = parse_trades(fetch_recent_trades(symbol, product_type, limit=trades_limit))
        open_interest = parse_open_interest(fetch_open_interest(symbol, product_type))
        funding = parse_funding_rate(fetch_funding_rate(symbol, product_type))

        imbalance = order_flow.order_book_imbalance(book["bids"], book["asks"], depth=depth)
        cvd = order_flow.cumulative_volume_delta(trades) if trades else {"cvd": 0.0}

        best_bid = book["bids"][0][0] if book["bids"] else None
        best_ask = book["asks"][0][0] if book["asks"] else None
        mid = (best_bid + best_ask) / 2 if (best_bid and best_ask) else None

        return {
            "symbol": symbol,
            "mid_price": mid,
            "book_imbalance": imbalance["imbalance"],
            "bid_volume": imbalance["bid_volume"],
            "ask_volume": imbalance["ask_volume"],
            "cvd": cvd["cvd"],
            "open_interest": open_interest,
            "funding_rate": funding,
        }
    except Exception:
        return {
            "symbol": symbol, "mid_price": None, "book_imbalance": 0.0,
            "bid_volume": 0.0, "ask_volume": 0.0, "cvd": 0.0,
            "open_interest": 0.0, "funding_rate": None,
        }


def mark_prices(product_type=None):
    """Derniers prix de TOUS les symboles en UNE requête : {SYMBOL: prix}.
    Best-effort : dict vide si la source est injoignable."""
    return parse_ticker_prices(fetch_tickers(product_type))


def build_report(snap):
    funding = snap["funding_rate"]
    funding_str = f"{funding * 100:.4f}%/8h" if funding is not None else "n/a"
    return "\n".join([
        f"=== ORDER FLOW {snap['symbol']} (lecture seule) ===",
        f"Prix mid     : {snap['mid_price']}",
        f"Déséquilibre : {snap['book_imbalance']:+.3f}  "
        f"(bid {snap['bid_volume']:.2f} / ask {snap['ask_volume']:.2f})",
        f"CVD (tape)   : {snap['cvd']:+.4f}",
        f"Open interest: {snap['open_interest']:.2f}",
        f"Funding      : {funding_str}",
        "",
        "Mode: lecture seule. Aucun ordre réel. VERDICT: SAFE",
    ])


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(market_snapshot(symbol)))


if __name__ == "__main__":
    main()
