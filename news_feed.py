"""
news_feed.py — news crypto via CryptoPanic (LECTURE SEULE).

Classement : SAFE (agrégateur de news, aucun ordre, aucun secret en dur).
Clé CRYPTOPANIC_API_TOKEN (gratuite) requise.

CLI : python news_feed.py [BTC,ETH] [filter]
      filter : hot | rising | bullish | bearish | important
"""

import os
import sys

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

URL = "https://cryptopanic.com/api/v1/posts/"


def parse_news(data, limit=10):
    out = []
    for p in (data.get("results") or [])[:limit]:
        out.append({
            "title": p.get("title"),
            "source": (p.get("source") or {}).get("title"),
            "published_at": p.get("published_at"),
            "currencies": [c.get("code") for c in (p.get("currencies") or [])],
            "url": p.get("url"),
        })
    return out


def fetch_news(currencies=None, filter_=None, limit=10):
    token = os.getenv("CRYPTOPANIC_API_TOKEN")
    if not token:
        raise RuntimeError("CRYPTOPANIC_API_TOKEN manquant dans .env")
    params = {"auth_token": token, "public": "true", "kind": "news"}
    if currencies:
        params["currencies"] = currencies
    if filter_:
        params["filter"] = filter_
    r = requests.get(URL, params=params, timeout=12)
    r.raise_for_status()
    return parse_news(r.json(), limit)


def build_report(rows):
    lines = ["=== NEWS (CryptoPanic) ==="]
    if not rows:
        lines.append("Aucune news.")
    for n in rows:
        cur = (",".join(n["currencies"][:3])) if n["currencies"] else ""
        lines.append(f"- [{n.get('source') or '?'}] {n.get('title')}" + (f" ({cur})" if cur else ""))
    lines.append("")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    currencies = sys.argv[1] if len(sys.argv) > 1 else None
    filter_ = sys.argv[2] if len(sys.argv) > 2 else None
    print(build_report(fetch_news(currencies=currencies, filter_=filter_)))


if __name__ == "__main__":
    main()
