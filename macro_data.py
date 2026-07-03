"""
macro_data.py — contexte TradFi en quasi-temps réel (LECTURE SEULE).

Classement : SAFE (donnée publique, aucun ordre, aucun secret). Complète
`macro_context.py` (FRED, parfois en retard) avec des cotations TradFi fraîches.

HISTORIQUE (§58) : la source initiale (yfinance) était morte — dépendance jamais
installée, l'agent macro était AVEUGLE côté TradFi. Réécrit sur les clés DÉJÀ
présentes dans le .env : AlphaVantage (clé testée OK) pour les proxys ETF
SPY (S&P), UUP (dollar), GLD (or) — 3 requêtes/rafraîchissement, cache 4 h ->
~18 appels/jour, SOUS le plafond gratuit (25/j) — et FRED sans clé pour les
NIVEAUX officiels : VIX (VIXCLS) et 10 ans US (DGS10). yfinance reste honoré
en premier s'il est un jour installé.

summarize() est PURE et testable. fetch_macro() ajoute le réseau (caché,
stale-while-error). CLI : python macro_data.py
"""

import importlib.util
import os

# nom lisible -> ticker Yahoo (si yfinance présent un jour)
TICKERS = {
    "VIX": "^VIX", "DXY": "DX-Y.NYB", "SPX": "^GSPC", "US10Y": "^TNX",
    "GOLD": "GC=F", "WTI": "CL=F", "BTC": "BTC-USD",
}
# nom lisible -> proxy ETF AlphaVantage (direction fidèle ; niveaux = proxys)
AV_PROXIES = {"SPX": "SPY", "DXY": "UUP", "GOLD": "GLD"}
# nom lisible -> symbole TwelveData (§59 : clé re-générée OK — forex/métaux réels,
# 800 req/j). L'or SPOT (XAU/USD) bat le proxy GLD ; le dollar se lit dans
# EUR/USD INVERSÉ (le franchissement de sens est géré dans _quote_td).
TD_SYMBOLS = {"GOLD": "XAU/USD", "DXY": "EUR/USD"}
# nom lisible -> série FRED (NIVEAUX officiels, sans clé)
FRED_SERIES = {"VIX": "VIXCLS", "US10Y": "DGS10"}
TTL_S = 4 * 3600                      # budget AlphaVantage gratuit : 25 req/jour


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


def parse_av_quote(payload):
    """GLOBAL_QUOTE AlphaVantage -> {last, change_pct}. PUR. None si illisible
    (y compris la réponse de rate-limit, qui n'a pas de Global Quote)."""
    try:
        q = (payload or {}).get("Global Quote") or {}
        last = float(q["05. price"])
        chg = float(str(q.get("10. change percent", "0")).rstrip("%"))
        return {"last": round(last, 3), "change_pct": round(chg, 3)}
    except (KeyError, TypeError, ValueError):
        return None


def parse_fred_quote(obs):
    """Deux dernières observations FRED [(date, val), ...] -> {last, change_pct}.
    PUR. None si vide."""
    vals = [v for _, v in (obs or []) if v is not None]
    if not vals:
        return None
    last = float(vals[-1])
    prev = float(vals[-2]) if len(vals) > 1 else last
    return {"last": round(last, 3),
            "change_pct": round((last - prev) / prev * 100, 3) if prev else 0.0}


def _av_key():
    key = os.getenv("ALPHAVANTAGE_API_KEY")
    if key:
        return key
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return os.getenv("ALPHAVANTAGE_API_KEY")
    except Exception:
        return None


def parse_td_quote(payload, inverse=False):
    """Quote TwelveData -> {last, change_pct}. PUR. inverse=True retourne la
    VARIATION opposée (EUR/USD inversé = direction du dollar). None si illisible."""
    try:
        last = float((payload or {})["close"])
        chg = float((payload or {}).get("percent_change", 0.0))
        if inverse:
            chg = -chg
        return {"last": round(last, 4), "change_pct": round(chg, 3)}
    except (KeyError, TypeError, ValueError):
        return None


def _td_key():
    key = os.getenv("TWELVEDATA_API_KEY")
    if key:
        return key
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return os.getenv("TWELVEDATA_API_KEY")
    except Exception:
        return None


def _quote_td(name):
    """Cotation TwelveData (forex/métaux réels), cachée TTL_S. Pour DXY la
    variation est celle d'EUR/USD INVERSÉE (le niveau affiché reste EUR/USD)."""
    sym = TD_SYMBOLS.get(name)
    key = _td_key()
    if not sym or not key:
        return None

    def fetch():
        import requests
        r = requests.get("https://api.twelvedata.com/quote",
                         params={"symbol": sym, "apikey": key}, timeout=12)
        r.raise_for_status()
        q = parse_td_quote(r.json(), inverse=(name == "DXY"))
        if q is None:
            raise ValueError("réponse TD illisible")
        return q
    try:
        import runtime_cache as rc
        return rc.get(f"macro_td:{sym}", TTL_S, fetch, fallback=None)
    except Exception:
        return None


def _quote_av(name):
    """Cotation via proxy ETF AlphaVantage, cachée TTL_S (stale-while-error)."""
    sym = AV_PROXIES.get(name)
    key = _av_key()
    if not sym or not key:
        return None

    def fetch():
        import requests
        r = requests.get("https://www.alphavantage.co/query",
                         params={"function": "GLOBAL_QUOTE", "symbol": sym,
                                 "apikey": key}, timeout=12)
        r.raise_for_status()
        q = parse_av_quote(r.json())
        if q is None:
            raise ValueError("réponse AV illisible (rate-limit ?)")
        return q
    try:
        import runtime_cache as rc
        return rc.get(f"macro_av:{sym}", TTL_S, fetch, fallback=None)
    except Exception:
        return None


def _quote_fred(name):
    """Niveau officiel via FRED (sans clé), caché TTL_S."""
    serie = FRED_SERIES.get(name)
    if not serie:
        return None

    def fetch():
        import macro_context as mc
        obs = mc.fetch_fred_series(serie)
        q = parse_fred_quote(obs[-3:] if obs else [])
        if q is None:
            raise ValueError("série FRED vide")
        return q
    try:
        import runtime_cache as rc
        return rc.get(f"macro_fred:{serie}", TTL_S, fetch, fallback=None)
    except Exception:
        return None


def summarize(quotes, source="td+av+fred"):
    """Régime risk-on/off à partir des cotations TradFi. Fonction pure."""
    vix = (quotes.get("VIX") or {}).get("last")
    dxy_chg = (quotes.get("DXY") or {}).get("change_pct")
    try:
        import macro_context as mc
        reg = mc.compute_risk_regime(vix=vix, dxy_change_pct=dxy_chg)
    except Exception:
        reg = {"regime": "NEUTRE", "score": 0, "notes": []}
    return {"quotes": quotes, "regime": reg["regime"], "score": reg["score"],
            "notes": reg.get("notes", []), "source": source}


def fetch_macro():
    if _available():                              # yfinance d'abord s'il existe
        quotes = {}
        for name, sym in TICKERS.items():
            try:
                quotes[name] = _quote(sym)
            except Exception:
                quotes[name] = None
        return summarize(quotes, source="yfinance")
    quotes = {}
    for name in ("VIX", "US10Y"):
        quotes[name] = _quote_fred(name)
    # TwelveData d'abord (or spot, dollar via EUR/USD inversé), AV en repli/SPX
    for name in ("GOLD", "DXY"):
        quotes[name] = _quote_td(name) or _quote_av(name)
    quotes["SPX"] = _quote_av("SPX")
    if not any(quotes.values()):
        return {"error": "TradFi indisponible (AlphaVantage/FRED muets)",
                "quotes": {}, "regime": "NEUTRE", "score": 0, "notes": []}
    return summarize(quotes)


def fetch_regime():
    """Régime risk-on/off léger (VIX + DXY uniquement) pour le cerveau.
    None si rien n'a pu être lu (l'appelant retombe sur macro_context/FRED)."""
    if _available():
        q = {}
        for name in ("VIX", "DXY"):
            try:
                q[name] = _quote(TICKERS[name])
            except Exception:
                q[name] = None
        if not (q.get("VIX") or q.get("DXY")):
            return None
        return summarize(q, source="yfinance")["regime"]
    q = {"VIX": _quote_fred("VIX"), "DXY": _quote_td("DXY") or _quote_av("DXY")}
    if not (q.get("VIX") or q.get("DXY")):
        return None
    return summarize(q)["regime"]


def build_report(d):
    if d.get("error"):
        return f"=== MACRO TRADFI ===\n{d['error']}\nLe régime FRED (/macro) reste disponible. VERDICT: SAFE"
    lines = [f"=== MACRO TRADFI ({d.get('source', '?')}) — régime {d['regime']} (score {d['score']:+d}) ==="]
    for name in ("VIX", "DXY", "SPX", "US10Y", "GOLD", "WTI", "BTC"):
        q = (d.get("quotes") or {}).get(name)
        if q:
            lines.append(f"- {name:<6} {q['last']:>12}  ({q['change_pct']:+.2f}%)")
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
