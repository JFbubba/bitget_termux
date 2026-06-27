"""
dex_scanner.py — recherche de paires/tokens via DexScreener (LECTURE SEULE).

Classement : SAFE (donnee publique, aucune cle, aucun ordre, aucun secret).
Source : api.dexscreener.com (gratuit, sans cle).

Sert a EXPLORER/DETECTER des paires (liquidite, volume, age), jamais a trader.
CLI : python dex_scanner.py <query>   (ex. BTC, SOL, une adresse de token)
"""

import sys

import requests

SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_pairs(data, top=10):
    """data {"pairs":[...]} -> liste normalisee triee par liquidite."""
    pairs = []
    for p in (data.get("pairs") or []):
        base = p.get("baseToken") or {}
        pairs.append({
            "chain": p.get("chainId"),
            "dex": p.get("dexId"),
            "symbol": base.get("symbol"),
            "name": base.get("name"),
            "address": base.get("address"),
            "price_usd": _f(p.get("priceUsd")),
            "liquidity_usd": _f((p.get("liquidity") or {}).get("usd")),
            "volume_24h": _f((p.get("volume") or {}).get("h24")),
            "created_at": p.get("pairCreatedAt"),
            "url": p.get("url"),
        })
    pairs.sort(key=lambda x: x["liquidity_usd"], reverse=True)
    return pairs[:top]


def fetch_search(query, top=10):
    # best-effort : liste vide si la source est injoignable (jamais d'exception)
    try:
        r = requests.get(SEARCH_URL, params={"q": query}, timeout=12)
        r.raise_for_status()
        return parse_pairs(r.json(), top=top)
    except Exception:
        return []


def _human(n):
    for unit in ("", "K", "M", "B"):
        if abs(n) < 1000:
            return f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}T"


def build_report(pairs, query=""):
    lines = [f"=== DEX SCAN '{query}' (DexScreener) ==="]
    if not pairs:
        lines.append("Aucune paire trouvee.")
    for p in pairs:
        lines.append(
            f"- {str(p['symbol'] or '?'):<8} {str(p['chain'] or ''):<8} "
            f"liq ${_human(p['liquidity_usd'])} | vol24h ${_human(p['volume_24h'])}"
        )
    lines.append("")
    lines.append("Lecture seule (exploration). Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python dex_scanner.py <query>")
        raise SystemExit(2)
    query = " ".join(sys.argv[1:])
    print(build_report(fetch_search(query), query))


if __name__ == "__main__":
    main()
