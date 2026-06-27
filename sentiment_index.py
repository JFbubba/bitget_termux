"""
sentiment_index.py — Fear & Greed Index crypto (LECTURE SEULE).

Classement : SAFE (donnee publique, aucune cle, aucun ordre, aucun secret).
Source : alternative.me (gratuit, sans cle).

CLI : python sentiment_index.py
"""

import requests

FNG_URL = "https://api.alternative.me/fng/"


def parse_fear_greed(data):
    """data {"data":[{"value","value_classification","timestamp"}]} -> dict."""
    items = data.get("data") or []
    if not items:
        return None
    first = items[0]
    try:
        value = int(first.get("value"))
    except (TypeError, ValueError):
        value = None
    return {
        "value": value,
        "classification": first.get("value_classification"),
        "timestamp": first.get("timestamp"),
    }


def fetch_fear_greed(limit=1):
    # best-effort : None si la source est injoignable (jamais d'exception).
    # Tous les appelants gèrent déjà None (poids sentiment neutre).
    try:
        response = requests.get(FNG_URL, params={"limit": str(limit)}, timeout=10)
        response.raise_for_status()
        return parse_fear_greed(response.json())
    except Exception:
        return None


def build_report(fng):
    if not fng:
        return "=== FEAR & GREED ===\nIndisponible.\nVERDICT: SAFE"
    return "\n".join([
        "=== FEAR & GREED (crypto) ===",
        f"Indice  : {fng['value']} / 100",
        f"Etat    : {fng['classification']}",
        "",
        "Lecture seule. Aucun ordre. VERDICT: SAFE",
    ])


def main():
    print(build_report(fetch_fear_greed()))


if __name__ == "__main__":
    main()
