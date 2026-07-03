"""
coingecko_data.py — prix & marché via CoinGecko (LECTURE SEULE).

Classement : SAFE (donnée publique, aucun ordre, aucun secret en dur).
Clé COINGECKO_API_KEY (tier démo) optionnelle : marche aussi sans (rate-limité).

CLI : python coingecko_data.py BTC ETH SOL
"""

import os
import sys

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE = "https://api.coingecko.com/api/v3"

SYMBOL_TO_ID = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
    "BNB": "binancecoin", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "LINK": "chainlink", "MATIC": "matic-network", "DOT": "polkadot", "TRX": "tron",
    "USDT": "tether", "USDC": "usd-coin", "XAUT": "tether-gold",
}


def _headers():
    key = os.getenv("COINGECKO_API_KEY")
    return {"x-cg-demo-api-key": key} if key else {}


def _get(url, params=None, timeout=12):
    """GET CoinGecko avec repli SANS CLÉ sur 401 (audit 03/07 : la clé configurée est
    rejetée — error 10002 — et le fallback silencieux rendait des None alors que
    l'endpoint PUBLIC répond très bien sans clé). Lève si les deux échouent."""
    r = requests.get(url, params=params, headers=_headers(), timeout=timeout)
    if r.status_code == 401 and _headers():
        r = requests.get(url, params=params, timeout=timeout)   # repli keyless
    r.raise_for_status()
    return r


def resolve_id(token):
    up = str(token).strip().upper()
    return SYMBOL_TO_ID.get(up, str(token).strip().lower())


# ---------- parseurs (purs) ----------

def parse_markets(data):
    out = []
    for c in data or []:
        out.append({
            "id": c.get("id"),
            "symbol": str(c.get("symbol") or "").upper(),
            "name": c.get("name"),
            "price": c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "change_24h": c.get("price_change_percentage_24h"),
            "volume_24h": c.get("total_volume"),
        })
    return out


def parse_global(data):
    d = (data or {}).get("data") or {}
    return {
        "total_market_cap_usd": (d.get("total_market_cap") or {}).get("usd"),
        "btc_dominance": (d.get("market_cap_percentage") or {}).get("btc"),
        "mcap_change_24h": d.get("market_cap_change_percentage_24h_usd"),
    }


# ---------- réseau ----------

def fetch_markets(tokens):
    # best-effort : liste vide si CoinGecko est injoignable (jamais d'exception)
    try:
        ids = ",".join(resolve_id(t) for t in tokens)
        r = _get(f"{BASE}/coins/markets",
                 params={"vs_currency": "usd", "ids": ids, "price_change_percentage": "24h"})
        return parse_markets(r.json())
    except Exception:
        return []


def fetch_global():
    # best-effort : dict aux valeurs None si CoinGecko est injoignable
    try:
        r = _get(f"{BASE}/global")
        return parse_global(r.json())
    except Exception:
        return {"total_market_cap_usd": None, "btc_dominance": None, "mcap_change_24h": None}


def _human(n):
    if n is None:
        return "—"
    for unit in ("", "K", "M", "B", "T"):
        if abs(n) < 1000:
            return f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}P"


def build_report(markets):
    lines = ["=== PRIX (CoinGecko) ==="]
    for m in markets:
        ch = m.get("change_24h")
        ch_s = f"{ch:+.2f}%" if isinstance(ch, (int, float)) else "—"
        lines.append(f"- {m['symbol']:<6} ${m.get('price')} ({ch_s}) | mcap ${_human(m.get('market_cap'))}")
    lines.append("")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    tokens = [a for a in sys.argv[1:]] or ["BTC", "ETH", "SOL"]
    print(build_report(fetch_markets(tokens)))


if __name__ == "__main__":
    main()
