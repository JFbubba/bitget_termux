"""
macro_data.py — contexte TradFi en quasi-temps réel via yfinance (LECTURE SEULE).

Classement : SAFE (donnée publique, aucun ordre, aucun secret). Complète
`macro_context.py` (qui lit FRED, parfois en retard) avec des cotations TradFi
fraîches : VIX, indice dollar (DXY), S&P 500, rendement 10 ans, or, pétrole WTI,
et BTC pour recoupement. Réutilise `compute_risk_regime` pour rester cohérent.

⚠️ yfinance est une dépendance OPTIONNELLE (pip install yfinance). Si absente,
le reader dégrade proprement : le reste du système (FRED) continue de marcher.

summarize() est PURE et testable. fetch_macro() ajoute le réseau.
CLI : python macro_data.py
"""

import importlib.util

# nom lisible -> ticker Yahoo Finance
TICKERS = {
    "VIX": "^VIX", "DXY": "DX-Y.NYB", "SPX": "^GSPC", "US10Y": "^TNX",
    "GOLD": "GC=F", "WTI": "CL=F", "BTC": "BTC-USD",
}


def _available():
    return importlib.util.find_spec("yfinance") is not None


def _quote(sym):
    import yfinance as yf
    hist = yf.Ticker(sym).history(period="5d")
    if hist is None or hist.empty:
        return None
    closes = [c for c in hist["Close"].tolist() if c == c]  # drop NaN
    if not closes:
        return None
    last = closes[-1]
    prev = closes[-2] if len(closes) > 1 else last
    return {"last": round(last, 3),
            "change_pct": round((last - prev) / prev * 100, 3) if prev else 0.0}


def summarize(quotes):
    """Régime risk-on/off à partir des cotations TradFi. Fonction pure."""
    vix = (quotes.get("VIX") or {}).get("last")
    dxy_chg = (quotes.get("DXY") or {}).get("change_pct")
    try:
        import macro_context as mc
        reg = mc.compute_risk_regime(vix=vix, dxy_change_pct=dxy_chg)
    except Exception:
        reg = {"regime": "NEUTRE", "score": 0, "notes": []}
    return {"quotes": quotes, "regime": reg["regime"], "score": reg["score"],
            "notes": reg.get("notes", []), "source": "yfinance"}


def fetch_macro():
    if not _available():
        return {"error": "yfinance non installé — pip install yfinance",
                "quotes": {}, "regime": "NEUTRE", "score": 0, "notes": []}
    quotes = {}
    for name, sym in TICKERS.items():
        try:
            quotes[name] = _quote(sym)
        except Exception:
            quotes[name] = None
    return summarize(quotes)


def fetch_regime():
    """Régime risk-on/off léger (VIX + DXY uniquement) pour le cerveau.

    Renvoie None si yfinance est absent ou si rien n'a pu être lu, pour laisser
    l'appelant retomber sur macro_context (FRED).
    """
    if not _available():
        return None
    q = {}
    for name in ("VIX", "DXY"):
        try:
            q[name] = _quote(TICKERS[name])
        except Exception:
            q[name] = None
    if not (q.get("VIX") or q.get("DXY")):
        return None
    return summarize(q)["regime"]


def build_report(d):
    if d.get("error"):
        return f"=== MACRO TRADFI ===\n{d['error']}\nLe régime FRED (/macro) reste disponible. VERDICT: SAFE"
    lines = [f"=== MACRO TRADFI (yfinance) — régime {d['regime']} (score {d['score']:+d}) ==="]
    for name in TICKERS:
        q = d["quotes"].get(name)
        if q:
            lines.append(f"- {name:<6} {q['last']:>12}  ({q['change_pct']:+.2f}%)")
        else:
            lines.append(f"- {name:<6} —")
    if d.get("notes"):
        lines.append("")
        lines.append("Signaux : " + " · ".join(d["notes"]))
    lines.append("")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    print(build_report(fetch_macro()))


if __name__ == "__main__":
    main()
