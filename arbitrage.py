"""
arbitrage.py — DÉTECTION d'écarts de prix (LECTURE SEULE, AUCUNE exécution).

Classement : SAFE. Aucun ordre, aucun secret. Détecte trois types d'écarts à
partir de données publiques keyless :
  1. spread spot inter-exchange (même actif, prix différents)
  2. base spot↔perp (mark perp vs prix spot = premium/contango)
  3. spread de funding inter-exchange (cash-and-carry delta-neutre)

⚠️ Ce sont des écarts BRUTS : ils n'incluent PAS les frais, le slippage, ni les
coûts de retrait/dépôt entre plateformes. La plupart disparaissent une fois
ces coûts pris en compte. C'est de la DÉTECTION/veille, pas une promesse de
profit, et surtout PAS un exécuteur.

Fonctions pures et testables : spot_spread, basis, funding_spread.
CLI : python arbitrage.py [SYMBOL]
"""

import sys

import requests

UA = {"User-Agent": "Mozilla/5.0"}


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


# ---------- prix spot par exchange (keyless) ----------

def binance_spot(symbol):
    r = requests.get("https://api.binance.com/api/v3/ticker/price",
                     params={"symbol": symbol}, headers=UA, timeout=10).json()
    return float(r["price"])


def bybit_spot(symbol):
    r = requests.get("https://api.bybit.com/v5/market/tickers",
                     params={"category": "spot", "symbol": symbol}, headers=UA, timeout=10).json()
    return float(r["result"]["list"][0]["lastPrice"])


def okx_spot(symbol):
    inst = (symbol[:-4] + "-" + symbol[-4:]) if symbol.endswith("USDT") else symbol
    r = requests.get("https://www.okx.com/api/v5/market/ticker",
                     params={"instId": inst}, headers=UA, timeout=10).json()
    return float(r["data"][0]["last"])


def bitget_spot(symbol):
    r = requests.get("https://api.bitget.com/api/v2/spot/market/tickers",
                     params={"symbol": symbol}, headers=UA, timeout=10).json()
    return float(r["data"][0]["lastPr"])


SPOT_FUNCS = {"binance": binance_spot, "bybit": bybit_spot, "okx": okx_spot, "bitget": bitget_spot}


# ---------- détection (pure, testable) ----------

def spot_spread(quotes):
    """quotes = {exchange: prix}. Retourne le meilleur écart inter-exchange."""
    valid = {k: v for k, v in quotes.items() if v}
    if len(valid) < 2:
        return None
    hi = max(valid.items(), key=lambda x: x[1])
    lo = min(valid.items(), key=lambda x: x[1])
    return {"high_exchange": hi[0], "high": hi[1], "low_exchange": lo[0], "low": lo[1],
            "spread_pct": round((hi[1] - lo[1]) / lo[1] * 100, 4),
            "buy_at": lo[0], "sell_at": hi[0], "quotes": valid}


def basis(spot, perp):
    """Base perp↔spot en % (positif = perp au-dessus du spot = contango)."""
    if not spot or not perp:
        return None
    return {"spot": spot, "perp": perp, "basis_pct": round((perp - spot) / spot * 100, 4)}


def funding_spread(parts):
    """parts = liste {exchange, funding}. Spread de funding inter-exchange."""
    fs = [(p.get("exchange"), p.get("funding")) for p in (parts or []) if p.get("funding") is not None]
    if len(fs) < 2:
        return None
    hi = max(fs, key=lambda x: x[1])
    lo = min(fs, key=lambda x: x[1])
    return {"highest": hi[0], "highest_funding": hi[1], "lowest": lo[0], "lowest_funding": lo[1],
            "spread": round(hi[1] - lo[1], 6),
            # cash-and-carry delta-neutre : short le perp au funding le plus haut,
            # long le perp au funding le plus bas -> on encaisse l'écart.
            "short_on": hi[0], "long_on": lo[0]}


def detect(symbol="BTCUSDT"):
    symbol = symbol.upper()
    quotes = {ex: _safe(fn, symbol) for ex, fn in SPOT_FUNCS.items()}
    spread = spot_spread(quotes)
    try:
        import aggregated_derivs as ad
        agg = ad.fetch_aggregate(symbol)
    except Exception:
        agg = {}
    parts = agg.get("exchanges", [])
    marks = [(p.get("mark"), p.get("oi_usd")) for p in parts if p.get("mark")]
    perp = None
    if marks:
        tot = sum((o or 0) for _, o in marks)
        perp = (sum(m * (o or 0) for m, o in marks) / tot) if tot else marks[0][0]
    sv = sorted(v for v in quotes.values() if v)
    spot_ref = sv[len(sv) // 2] if sv else None
    return {
        "symbol": symbol,
        "spot_spread": spread,
        "basis": basis(spot_ref, perp),
        "funding_spread": funding_spread(parts),
        "note": "écarts BRUTS — hors frais/slippage/retrait/dépôt. DÉTECTION seule, aucune exécution.",
    }


def build_report(d):
    lines = [f"=== ARBITRAGE / ÉCARTS {d['symbol']} (détection) ==="]
    ss = d.get("spot_spread")
    if ss:
        lines.append(f"Spot : {ss['spread_pct']:+.3f}%  (acheter {ss['buy_at']} {ss['low']:.2f} → "
                     f"vendre {ss['sell_at']} {ss['high']:.2f})")
        lines.append("  " + " · ".join(f"{k} {v:.2f}" for k, v in ss["quotes"].items()))
    else:
        lines.append("Spot : pas assez de cotations.")
    b = d.get("basis")
    if b:
        lines.append(f"Base perp↔spot : {b['basis_pct']:+.3f}%  (spot {b['spot']:.2f} / perp {b['perp']:.2f})")
    fs = d.get("funding_spread")
    if fs:
        lines.append(f"Funding : spread {fs['spread'] * 100:+.4f}%  "
                     f"(short {fs['short_on']} / long {fs['long_on']})")
    lines.append("")
    lines.append("⚠️ Écarts BRUTS, hors frais/slippage/retrait. DÉTECTION seule.")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(detect(symbol)))


if __name__ == "__main__":
    main()
