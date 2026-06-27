"""
defi_data.py — contexte DeFi via DefiLlama (LECTURE SEULE).

Classement : SAFE (donnee publique, aucune cle, aucun ordre, aucun secret).
Source : api.llama.fi (gratuit, sans cle).

Fournit la TVL DeFi totale et le top des chaines (contexte marche).
CLI : python defi_data.py
"""

import requests

CHAINS_URL = "https://api.llama.fi/v2/chains"


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_chains(data, top=8):
    """data [{"name","tvl","tokenSymbol"}] -> {total_tvl, top_chains[]}."""
    rows = []
    for item in data or []:
        rows.append({
            "name": item.get("name"),
            "symbol": item.get("tokenSymbol"),
            "tvl": _f(item.get("tvl")),
        })
    total = sum(r["tvl"] for r in rows)
    rows.sort(key=lambda r: r["tvl"], reverse=True)
    return {"total_tvl": total, "chain_count": len(rows), "top_chains": rows[:top]}


def fetch_chains(top=8):
    # best-effort : agrégat vide si la source est injoignable (jamais d'exception)
    try:
        response = requests.get(CHAINS_URL, timeout=15)
        response.raise_for_status()
        return parse_chains(response.json(), top=top)
    except Exception:
        return {"total_tvl": 0.0, "chain_count": 0, "top_chains": []}


def _human(n):
    for unit in ("", "K", "M", "B", "T"):
        if abs(n) < 1000:
            return f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}P"


def build_report(summary):
    lines = [
        "=== DEFI (DefiLlama) ===",
        f"TVL totale : ${_human(summary['total_tvl'])} sur {summary['chain_count']} chaines",
        "",
        "Top chaines :",
    ]
    for chain in summary["top_chains"]:
        lines.append(f"- {str(chain['name'])[:16]:<16} ${_human(chain['tvl'])}")
    lines.append("")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    print(build_report(fetch_chains()))


if __name__ == "__main__":
    main()
