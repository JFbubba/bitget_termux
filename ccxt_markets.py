"""
ccxt_markets.py — données multi-exchange via CCXT (LECTURE SEULE).

Classement : SAFE. CCXT unifie 100+ exchanges ; on n'utilise QUE des méthodes de
LECTURE (fetch_ticker / fetch_funding_rate / fetch_open_interest). AUCUN ordre,
aucune clé requise pour ces endpoints publics.

Élargit la couverture de prix spot et de funding/OI bien au-delà des exchanges
codés en dur dans arbitrage.py / aggregated_derivs.py. Réutilise
arbitrage.spot_spread pour le calcul d'écart.

⚠️ CCXT est une dépendance OPTIONNELLE (pip install ccxt). Si absente, le reader
dégrade proprement (message clair) et le reste du système continue.

Conversion de symbole et availability() sont purs/testables.
CLI : python ccxt_markets.py [SYMBOL]
"""

import importlib.util
import sys

SPOT_EXCHANGES = ["binance", "bybit", "okx", "kucoin", "gateio", "bitget"]
DERIV_EXCHANGES = ["binance", "bybit", "okx", "bitget", "gateio"]
_QUOTES = ("USDT", "USDC", "USD", "BTC", "ETH", "EUR")


def available():
    return importlib.util.find_spec("ccxt") is not None


def _split(symbol):
    s = str(symbol).upper().replace("/", "").split(":")[0]
    for q in _QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return s[:-len(q)], q
    return s, "USDT"


def _to_spot(symbol):
    base, quote = _split(symbol)
    return f"{base}/{quote}"


def _to_swap(symbol):
    base, quote = _split(symbol)
    return f"{base}/{quote}:{quote}"


def _client(ex, swap=False):
    import ccxt
    opts = {"enableRateLimit": True, "timeout": 8000}
    if swap:
        opts["options"] = {"defaultType": "swap"}
    return getattr(ccxt, ex)(opts)


def fetch_spot_prices(symbol, exchanges=None):
    if not available():
        return {"error": "ccxt non installé — pip install ccxt"}
    sym = _to_spot(symbol)
    out = {}
    for ex in (exchanges or SPOT_EXCHANGES):
        try:
            out[ex] = _client(ex).fetch_ticker(sym).get("last")
        except Exception:
            out[ex] = None
    return out


def fetch_derivs(symbol, exchanges=None):
    if not available():
        return {"error": "ccxt non installé — pip install ccxt"}
    sym = _to_swap(symbol)
    out = {}
    for ex in (exchanges or DERIV_EXCHANGES):
        try:
            client = _client(ex, swap=True)
            funding = client.fetch_funding_rate(sym).get("fundingRate")
            oi = None
            try:
                o = client.fetch_open_interest(sym)
                oi = o.get("openInterestValue") or o.get("openInterestAmount")
            except Exception:
                oi = None
            out[ex] = {"funding": funding, "oi_usd": oi}
        except Exception:
            out[ex] = None
    return out


def cross_exchange(symbol="BTCUSDT", with_derivs=False):
    if not available():
        return {"error": "ccxt non installé — pip install ccxt", "symbol": str(symbol).upper()}
    prices = fetch_spot_prices(symbol)
    import arbitrage
    out = {
        "symbol": str(symbol).upper(),
        "prices": prices,
        "spread": arbitrage.spot_spread(prices),
        "venues": len([v for v in prices.values() if v]),
        "note": "prix spot multi-exchange (ccxt). Écart BRUT hors frais. Lecture seule.",
    }
    if with_derivs:
        out["derivs"] = fetch_derivs(symbol)
    return out


def build_report(d):
    if d.get("error"):
        return f"=== MULTI-EXCHANGE {d.get('symbol', '')} ===\n{d['error']}\nVERDICT: SAFE"
    lines = [f"=== MULTI-EXCHANGE {d['symbol']} (ccxt · {d['venues']} venues) ==="]
    for ex, p in (d.get("prices") or {}).items():
        lines.append(f"- {ex:<9} {p if p is not None else '—'}")
    s = d.get("spread")
    if s:
        lines.append(f"Écart spot : {s['spread_pct']:+.3f}%  (acheter {s['buy_at']} → vendre {s['sell_at']})")
    for ex, v in (d.get("derivs") or {}).items():
        if v and v.get("funding") is not None:
            lines.append(f"  funding {ex:<8} {v['funding'] * 100:+.4f}%")
    lines.append("")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(cross_exchange(symbol, with_derivs=True)))


if __name__ == "__main__":
    main()
