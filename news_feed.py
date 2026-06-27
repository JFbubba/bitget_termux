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

import prompt_guard  # anti prompt-injection : on assainit les titres externes à la source

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

URL = "https://cryptopanic.com/api/v1/posts/"

# Valeurs « non configurées » fréquentes (placeholder / commentaire collé).
_PLACEHOLDERS = {"", "none", "null", "changeme", "your_token", "xxx", "todo"}


def _token():
    """Token CryptoPanic *valide* ou None. Rejette les valeurs non configurées
    (vide, placeholder, ou commentaire/phrase collé dans .env) pour DÉGRADER
    proprement au lieu de crasher sur un 404. Un vrai token est un identifiant
    compact (sans espace ni '#')."""
    t = (os.getenv("CRYPTOPANIC_API_TOKEN") or "").strip()
    if not t or t.lower() in _PLACEHOLDERS:
        return None
    if "#" in t or " " in t or len(t) < 16:
        return None
    return t


def parse_news(data, limit=10):
    out = []
    for p in (data.get("results") or [])[:limit]:
        out.append({
            # titres/sources = texte EXTERNE non fiable -> assaini dès l'ingestion
            "title": prompt_guard.sanitize(p.get("title") or "", max_len=300),
            "source": prompt_guard.sanitize((p.get("source") or {}).get("title") or "", max_len=120),
            "published_at": p.get("published_at"),
            "currencies": [c.get("code") for c in (p.get("currencies") or [])],
            "url": p.get("url"),
        })
    return out


def fetch_news(currencies=None, filter_=None, limit=10):
    """News CryptoPanic. Best-effort : renvoie [] si le token n'est pas configuré
    OU si la source est injoignable (jamais d'exception vers l'appelant)."""
    token = _token()
    if not token:
        return []
    params = {"auth_token": token, "public": "true", "kind": "news"}
    if currencies:
        params["currencies"] = currencies
    if filter_:
        params["filter"] = filter_
    try:
        r = requests.get(URL, params=params, timeout=8)
        r.raise_for_status()
        return parse_news(r.json(), limit)
    except Exception:
        return []


def build_report(rows, configured=True):
    lines = ["=== NEWS (CryptoPanic) ==="]
    if not configured:
        lines.append("Source non configurée : ajoute un token gratuit "
                     "CRYPTOPANIC_API_TOKEN=<token> dans .env "
                     "(https://cryptopanic.com/developers/api/).")
    elif not rows:
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
    configured = _token() is not None
    print(build_report(fetch_news(currencies=currencies, filter_=filter_), configured=configured))


if __name__ == "__main__":
    main()
