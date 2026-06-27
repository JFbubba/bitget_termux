"""
polymarket_data.py — cotes Polymarket (marchés de prédiction) en LECTURE SEULE.

Classement : SAFE. Donnée publique (Gamma API, keyless). Aucun ordre, aucun pari,
aucun secret. Ne sert qu'à LIRE les probabilités implicites comme signal/sentiment.

CLI : python polymarket_data.py [recherche]   (ex. bitcoin, fed, election)
"""

import json
import sys

import requests

GAMMA = "https://gamma-api.polymarket.com/markets"
SEARCH = "https://gamma-api.polymarket.com/public-search"
UA = {"User-Agent": "Mozilla/5.0"}


def parse_markets(data, query=None, limit=8):
    """Filtre par texte (sur la question) et normalise outcomes + probabilités."""
    out = []
    q = (query or "").lower()
    for m in data or []:
        question = m.get("question") or ""
        if q and q not in question.lower():
            continue
        try:
            outcomes = json.loads(m.get("outcomes") or "[]")
            prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        except Exception:
            outcomes, prices = [], []
        out.append({
            "question": question,
            "outcomes": [{"name": n, "prob_pct": round(p * 100, 1)} for n, p in zip(outcomes, prices)],
            "volume_usd": float(m.get("volumeNum") or m.get("volume") or 0),
            "end_date": m.get("endDate"),
            "url": f"https://polymarket.com/market/{m.get('slug')}" if m.get("slug") else None,
        })
        if len(out) >= limit:
            break
    return out


def fetch_markets(query=None, limit=8):
    # best-effort : liste vide si la source est injoignable (jamais d'exception)
    try:
        if query:
            # vraie recherche plein-texte : public-search renvoie des events -> markets
            r = requests.get(SEARCH, params={"q": query, "limit_per_type": "10"}, headers=UA, timeout=15)
            r.raise_for_status()
            markets = []
            for event in (r.json().get("events") or []):
                for m in (event.get("markets") or []):
                    if not m.get("closed"):
                        markets.append(m)
            markets.sort(key=lambda m: float(m.get("volumeNum") or 0), reverse=True)
            return parse_markets(markets, None, limit)
        # sans mot-clé : top marchés par volume
        r = requests.get(GAMMA, params={
            "closed": "false", "active": "true", "limit": "150",
            "order": "volumeNum", "ascending": "false",
        }, headers=UA, timeout=15)
        r.raise_for_status()
        return parse_markets(r.json(), None, limit)
    except Exception:
        return []


def _human(n):
    for unit in ("", "K", "M", "B"):
        if abs(n) < 1000:
            return f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}T"


def build_report(rows, query=""):
    lines = [f"=== POLYMARKET '{query}' ===" if query else "=== POLYMARKET (top volume) ==="]
    if not rows:
        lines.append("Aucun marché trouvé.")
    for m in rows:
        odds = " / ".join(f"{o['name']} {o['prob_pct']}%" for o in m["outcomes"][:3])
        lines.append(f"- {m['question'][:70]}")
        lines.append(f"    {odds}  | vol ${_human(m['volume_usd'])}")
    lines.append("")
    lines.append("Lecture seule (cotes/sentiment). Aucun pari, aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    query = " ".join(sys.argv[1:]) or None
    print(build_report(fetch_markets(query), query or ""))


if __name__ == "__main__":
    main()
