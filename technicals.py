"""
technicals.py — indicateurs techniques sur bougies + carnet (LECTURE SEULE).

Classement : SAFE (analyse, aucun ordre, aucun secret).

Réutilise indicators.py (EMA/RSI/ATR/volume_bias, purs) et ajoute :
  - VWAP, Volume SMA (+ ratio)
  - Volume Profile (POC / VAH / VAL) ~ VPVR / VPSV
  - Profil temps-prix (TPO / Market Profile, approximation)
  - Clusters / murs de liquidité du carnet (~ OB heatmap, statique)

Les calculs sont PURS et testés ; fetch_* / technicals() ajoutent le réseau
(bougies Bitget) et dégradent proprement.
CLI : python technicals.py SYMBOL [granularity]   (ex. BTCUSDT 15m)
"""

import sys

import bitget_market_data as bmd
import config
import indicators

# Bitget veut les heures/jours/semaines en MAJUSCULE (1H, 4H, 1D, 1W) ; la minute
# reste en minuscule (1m) car 1M = 1 mois. On normalise pour accepter toute casse.
_UNIT = {"m": "m", "M": "M", "h": "H", "H": "H", "d": "D", "D": "D", "w": "W", "W": "W"}


def _norm_granularity(g):
    import re
    mt = re.match(r"^(\d+)([a-zA-Z])$", str(g).strip())
    if not mt:
        return str(g).strip()
    num, unit = mt.groups()
    return f"{num}{_UNIT.get(unit, unit)}"


# ---------- réseau ----------

def fetch_candles(symbol, granularity="15m", limit=200, product_type=None):
    raw = bmd._get("/api/v2/mix/market/candles", {
        "symbol": symbol,
        "productType": product_type or config.PRODUCT_TYPE,
        "granularity": _norm_granularity(granularity),
        "limit": str(limit),
    })
    return parse_candles(raw)


# ---------- parseurs / calculs (purs, testables) ----------

def parse_candles(raw):
    """raw [[ts,open,high,low,close,baseVol,quoteVol], ...] -> liste triée asc."""
    out = []
    for row in raw or []:
        try:
            out.append({
                "ts": int(row[0]),
                "open": float(row[1]), "high": float(row[2]),
                "low": float(row[3]), "close": float(row[4]),
                "volume": float(row[5]),
            })
        except (TypeError, ValueError, IndexError):
            continue
    out.sort(key=lambda c: c["ts"])
    return out


def vwap(candles):
    num = den = 0.0
    for c in candles:
        typical = (c["high"] + c["low"] + c["close"]) / 3.0
        num += typical * c["volume"]
        den += c["volume"]
    return (num / den) if den else None


def volume_sma(candles, period=20):
    vols = [c["volume"] for c in candles]
    if period <= 0 or len(vols) < period:
        return None
    avg = sum(vols[-period:]) / period
    last = vols[-1]
    return {"period": period, "avg_volume": avg, "last_volume": last,
            "ratio": (last / avg) if avg else None}


def _profile(candles, bins, weight_volume):
    """Histogramme prix : pondéré par le volume (VPVR) ou par le temps (TPO)."""
    if not candles:
        return None
    lo = min(c["low"] for c in candles)
    hi = max(c["high"] for c in candles)
    if hi <= lo:
        return None
    width = (hi - lo) / bins
    buckets = [0.0] * bins
    for c in candles:
        first = max(0, min(bins - 1, int((c["low"] - lo) / width)))
        last = max(0, min(bins - 1, int((c["high"] - lo) / width)))
        n = last - first + 1
        share = (c["volume"] / n) if weight_volume else (1.0 / n)
        for b in range(first, last + 1):
            buckets[b] += share
    total = sum(buckets)
    poc_idx = max(range(bins), key=lambda i: buckets[i])
    result = {"low": lo, "high": hi, "poc": lo + (poc_idx + 0.5) * width, "bins": bins}
    if weight_volume and total > 0:
        acc, area = 0.0, set()
        for i in sorted(range(bins), key=lambda i: buckets[i], reverse=True):
            area.add(i)
            acc += buckets[i]
            if acc >= 0.70 * total:
                break
        ordered = sorted(area)
        result["vah"] = lo + (ordered[-1] + 1) * width
        result["val"] = lo + ordered[0] * width
    return result


def volume_profile(candles, bins=24):
    """VPVR / VPSV : POC + zone de valeur (VAH/VAL)."""
    return _profile(candles, bins, weight_volume=True)


def tpo_profile(candles, bins=24):
    """TPO / Market Profile (approx. temps-prix) : POC."""
    return _profile(candles, bins, weight_volume=False)


def liquidity_clusters(orderbook, top=5):
    """OB heatmap (statique) : plus gros murs de liquidité bid/ask."""
    bids = sorted(orderbook.get("bids", []), key=lambda x: x[1], reverse=True)[:top]
    asks = sorted(orderbook.get("asks", []), key=lambda x: x[1], reverse=True)[:top]
    return {
        "bid_walls": [{"price": p, "size": s} for p, s in bids],
        "ask_walls": [{"price": p, "size": s} for p, s in asks],
    }


def _safe_last(fn, *args):
    try:
        value = fn(*args)
        return value[-1] if isinstance(value, list) and value else value
    except Exception:
        return None


# ---------- agrégateurs réseau ----------

def technicals(symbol, granularity="15m", limit=200):
    candles = fetch_candles(symbol, granularity, limit)
    closes = [c["close"] for c in candles]
    return {
        "symbol": symbol, "granularity": granularity, "candles": len(candles),
        "last_close": closes[-1] if closes else None,
        "vwap": vwap(candles),
        "volume_sma": volume_sma(candles),
        "volume_profile": volume_profile(candles),
        "tpo": tpo_profile(candles),
        "rsi14": _safe_last(indicators.calculate_rsi, closes),
        "atr14": _safe_last(indicators.calculate_atr, candles),
        "ema20": _safe_last(indicators.ema, closes, 20),
        "ema50": _safe_last(indicators.ema, closes, 50),
        "volume_bias": _safe_last(indicators.volume_bias_score, candles),
    }


def book_liquidity(symbol, depth=50):
    ob = bmd.parse_orderbook(bmd.fetch_orderbook(symbol, limit=depth))
    return liquidity_clusters(ob)


def build_report(t):
    vp = t.get("volume_profile") or {}
    vs = t.get("volume_sma") or {}
    tpo = t.get("tpo") or {}
    lines = [
        f"=== TECHNICALS {t['symbol']} ({t['granularity']}, {t['candles']} bougies) ===",
        f"Close {t.get('last_close')} | VWAP {t.get('vwap')}",
        f"RSI14 {t.get('rsi14')} | ATR14 {t.get('atr14')} | EMA20 {t.get('ema20')} | EMA50 {t.get('ema50')}",
        f"Volume: bias {t.get('volume_bias')}"
        + (f" | SMA{vs.get('period')} ratio {vs.get('ratio')}" if vs else ""),
    ]
    if vp:
        lines.append(f"Volume Profile: POC {vp.get('poc')} | VAL {vp.get('val')} - VAH {vp.get('vah')}")
    if tpo:
        lines.append(f"TPO POC: {tpo.get('poc')}")
    lines.append("")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python technicals.py SYMBOL [granularity]   (ex. BTCUSDT 15m)")
        raise SystemExit(2)
    symbol = sys.argv[1].upper()
    granularity = sys.argv[2] if len(sys.argv) > 2 else "15m"
    print(build_report(technicals(symbol, granularity)))


if __name__ == "__main__":
    main()
