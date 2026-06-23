"""
aggregated_derivs.py — funding & open interest AGRÉGÉS multi-exchange (LECTURE SEULE).

Classement : SAFE (donnée publique, aucun ordre, aucun secret).
Sources publiques : Binance (fapi), Bybit (v5), Bitget (réutilise bitget_market_data).

Fournit :
  - par exchange : funding rate + open interest (en USD)
  - agrégé : OI total (USD) + funding 8h **pondéré par l'OI** (l'indicateur
    "Aggregated Funding Rate OI-weighted 8h").

aggregate() est PUR et testé ; fetch_* ajoute le réseau et dégrade proprement
(si un exchange échoue, on agrège les autres).
CLI : python aggregated_derivs.py [SYMBOL]   (ex. BTCUSDT)
"""

import sys

import requests

UA = {"User-Agent": "Mozilla/5.0"}


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


# ---------- par exchange ----------

def binance(symbol="BTCUSDT"):
    pi = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex",
                      params={"symbol": symbol}, headers=UA, timeout=10).json()
    oi = requests.get("https://fapi.binance.com/fapi/v1/openInterest",
                      params={"symbol": symbol}, headers=UA, timeout=10).json()
    mark = float(pi["markPrice"])
    oi_base = float(oi["openInterest"])
    return {"exchange": "binance", "funding": float(pi["lastFundingRate"]),
            "mark": mark, "oi_usd": oi_base * mark}


def bybit(symbol="BTCUSDT"):
    r = requests.get("https://api.bybit.com/v5/market/tickers",
                     params={"category": "linear", "symbol": symbol}, headers=UA, timeout=10).json()
    t = r["result"]["list"][0]
    return {"exchange": "bybit", "funding": float(t["fundingRate"]),
            "mark": float(t["markPrice"]), "oi_usd": float(t["openInterestValue"])}


def bitget(symbol="BTCUSDT"):
    import bitget_market_data as bmd
    s = bmd.market_snapshot(symbol)
    mark = s.get("mid_price")
    oi_base = s.get("open_interest")
    return {"exchange": "bitget", "funding": s.get("funding_rate"), "mark": mark,
            "oi_usd": (oi_base * mark) if (oi_base and mark) else None}


# ---------- agrégation (pure, testable) ----------

def aggregate(parts):
    valid = [p for p in parts if p and p.get("oi_usd")]
    total = sum(p["oi_usd"] for p in valid)
    weighted = None
    if total > 0:
        fsum = sum(p["funding"] * p["oi_usd"] for p in valid if p.get("funding") is not None)
        weighted = fsum / total
    return {
        "exchanges": valid,
        "total_oi_usd": total,
        "oi_weighted_funding": weighted,
        "oi_weighted_funding_pct": (weighted * 100) if weighted is not None else None,
    }


def fetch_aggregate(symbol="BTCUSDT"):
    parts = [_safe(binance, symbol), _safe(bybit, symbol), _safe(bitget, symbol)]
    out = aggregate(parts)
    out["symbol"] = symbol
    return out


def _human(n):
    if n is None:
        return "—"
    for unit in ("", "K", "M", "B", "T"):
        if abs(n) < 1000:
            return f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}P"


def build_report(agg):
    lines = [f"=== DÉRIVÉS AGRÉGÉS {agg['symbol']} (Binance+Bybit+Bitget) ==="]
    for p in agg["exchanges"]:
        f = p.get("funding")
        fp = f"{f * 100:+.4f}%" if isinstance(f, (int, float)) else "—"
        lines.append(f"- {p['exchange']:<8} OI ${_human(p['oi_usd'])} | funding {fp}")
    lines.append(f"OI TOTAL : ${_human(agg['total_oi_usd'])}")
    wf = agg.get("oi_weighted_funding_pct")
    lines.append("Funding 8h OI-pondéré : " + (f"{wf:+.4f}%" if wf is not None else "—"))
    lines.append("")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(fetch_aggregate(symbol)))


if __name__ == "__main__":
    main()
