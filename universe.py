"""
universe.py — UNIVERS DYNAMIQUE top-N des paires Bitget les plus liquides.

Classement : SAFE. Lecture seule, aucun ordre. Remplace les listes blanches figées par
un univers construit à chaque cycle :
  • LIQUIDITÉ (primaire) : volume 24 h en USDT des tickers spot Bitget (la liquidité sur
    le marché où l'on trade réellement) ;
  • QUALITÉ (filtre) : on ne garde que les bases présentes dans le top market-cap CoinGecko
    -> écarte les tokens à fort volume mais sans capitalisation (hype/rug) ;
  • ANCRES : config.SYMBOLS sont toujours inclus (majors suivis).

Gated par config.DYNAMIC_UNIVERSE (False = comportement historique, juste config.SYMBOLS).
Fonctions de tri/filtre PURES et testables ; fetch réseau best-effort (ne lèvent jamais).
"""

import time

_CACHE = {}


def _cfg(name, fallback):
    try:
        import config
        return getattr(config, name, fallback)
    except Exception:
        return fallback


def _anchors():
    return [s.upper() for s in _cfg("SYMBOLS", ["BTCUSDT"])]


# ---------- tri / filtre (PURS) ----------

def parse_tickers(data):
    """Parse les tickers spot Bitget -> [{symbol, usdt_volume}] (paires USDT). PUR."""
    rows = (data or {}).get("data", data) if isinstance(data, dict) else data
    out = []
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol", "")).upper()
        if not sym.endswith("USDT"):
            continue
        try:
            vol = float(r.get("usdtVolume") or r.get("quoteVolume") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        out.append({"symbol": sym, "usdt_volume": vol})
    return out


def rank_by_volume(tickers, top_n=20, min_volume=0.0, quality=None, anchors=None):
    """Univers = ancres + top-N par volume (≥ min_volume), filtré qualité. PUR.
    quality = set de BASES autorisées (ex. top market-cap CoinGecko) ou None (pas de filtre).
    Dédupliqué, ancres en tête."""
    anchors = anchors if anchors is not None else _anchors()
    elig = [t for t in tickers if t.get("usdt_volume", 0) >= min_volume]
    elig.sort(key=lambda t: t.get("usdt_volume", 0), reverse=True)
    out = list(anchors)
    for t in elig:
        sym = t["symbol"]
        if sym in out:
            continue
        if quality is not None:
            base = sym[:-4]                      # retire 'USDT'
            if base not in quality:
                continue
        out.append(sym)
        if len(out) >= top_n + len(anchors):
            break
    return out[:max(top_n, len(anchors))]


# ---------- fetch (best-effort) ----------

def _bitget_tickers():
    try:
        import requests
        r = requests.get("https://api.bitget.com/api/v2/spot/market/tickers",
                         headers={"User-Agent": "bitget-termux/1.0"}, timeout=10).json()
        return parse_tickers(r)
    except Exception:
        return []


def _coingecko_top_bases(n=200):
    """BASES (tickers majuscules) du top-N market-cap CoinGecko. Best-effort -> None si KO
    (auquel cas pas de filtre qualité). Réutilise coingecko_data (clé optionnelle)."""
    try:
        import requests
        import coingecko_data as cg
        params = {"vs_currency": "usd", "order": "market_cap_desc",
                  "per_page": min(n, 250), "page": 1}
        r = requests.get(f"{cg.BASE}/coins/markets", params=params,
                         headers=cg._headers(), timeout=12).json()
        bases = {str(c.get("symbol", "")).upper() for c in r if isinstance(c, dict)}
        return bases or None
    except Exception:
        return None


def build_universe(top_n=None, min_volume=None, use_coingecko=True):
    """Construit l'univers (best-effort). Repli sur les ancres si le réseau échoue."""
    top_n = int(_cfg("UNIVERSE_TOP_N", 20) if top_n is None else top_n)
    min_volume = float(_cfg("UNIVERSE_MIN_VOLUME_USDT", 5_000_000) if min_volume is None else min_volume)
    tickers = _bitget_tickers()
    if not tickers:
        return _anchors()
    quality = _coingecko_top_bases() if use_coingecko else None
    return rank_by_volume(tickers, top_n=top_n, min_volume=min_volume, quality=quality)


def symbols(ttl=900):
    """Liste de symboles à analyser. Si DYNAMIC_UNIVERSE est False -> config.SYMBOLS
    (comportement historique). Sinon univers dynamique, caché `ttl` s. Ne lève jamais."""
    if not bool(_cfg("DYNAMIC_UNIVERSE", False)):
        return _anchors()
    now = time.time()
    hit = _CACHE.get("u")
    if hit and now - hit[0] < ttl:
        return hit[1]
    uni = build_universe()
    _CACHE["u"] = (now, uni)
    return uni


def build_report():
    uni = symbols()
    dyn = bool(_cfg("DYNAMIC_UNIVERSE", False))
    return ("=== UNIVERS D'ANALYSE ===\n"
            f"Mode : {'DYNAMIQUE top-N (Bitget volume + filtre CoinGecko)' if dyn else 'liste figée (config.SYMBOLS)'}\n"
            f"{len(uni)} symboles : {', '.join(uni[:25])}{' …' if len(uni) > 25 else ''}\n"
            "Lecture seule, aucun ordre. VERDICT: SAFE")


def main():
    print(build_report())


if __name__ == "__main__":
    main()
