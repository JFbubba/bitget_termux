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


from config_utils import cfg as _cfg


def _anchors():
    return [s.upper() for s in _cfg("SYMBOLS", ["BTCUSDT"])]


# bases stablecoin : peg ~1.00, aucune tendance -> hors univers d'ANALYSE (inutiles)
_STABLE_BASES = {"USDC", "DAI", "TUSD", "FDUSD", "USDD", "BUSD", "PYUSD", "USDP",
                 "GUSD", "USDE", "FRAX", "LUSD", "EURT", "EUR", "USD1", "XUSD",
                 # USDGO (Global Dollar, peg ~1.001, amplitude 24h ~0.07 %) avait
                 # échappé au filtre : univers pollué + bruit de journal à chaque
                 # cycle (« Pas d'identifiant CoinGecko ») — audit 03/07
                 "USDGO", "USDG"}

# Filtre QUALITÉ de repli (si CoinGecko indispo) : cryptos majeures. Garantit un univers
# CRYPTO même hors-ligne et exclut de facto les actions tokenisées (xStocks : RAAPL, RNVDA…)
# et le junk -> jamais de volume non filtré. CoinGecko (top mcap) l'élargit quand dispo.
_FALLBACK_CRYPTO = {
    "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "AVAX", "LINK", "DOT", "TRX", "MATIC",
    "POL", "LTC", "BCH", "SHIB", "UNI", "ATOM", "XLM", "ETC", "FIL", "APT", "ARB", "OP",
    "SUI", "SEI", "TIA", "INJ", "NEAR", "AAVE", "MKR", "RUNE", "LDO", "RNDR", "RENDER",
    "IMX", "HBAR", "VET", "ALGO", "GRT", "FTM", "SAND", "MANA", "AXS", "PEPE", "WIF",
    "BONK", "FLOKI", "JUP", "PYTH", "ENA", "ONDO", "HYPE", "TON", "KAS", "STX", "FET",
    "TAO", "WLD", "ORDI", "DYDX", "GALA", "CRV", "COMP", "BGB", "CRO", "OKB",
}


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
        base = sym[:-4]                          # retire 'USDT'
        if base in _STABLE_BASES:                # stablecoin (peg) -> hors analyse
            continue
        if quality is not None and base not in quality:
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


def _coingecko_top_bases(n=250):
    """BASES (tickers majuscules) du top-N market-cap CoinGecko. Best-effort -> None si KO
    (rate-limit tier gratuit fréquent ; clé COINGECKO_API_KEY recommandée). 2 tentatives."""
    try:
        import requests
        import coingecko_data as cg
        params = {"vs_currency": "usd", "order": "market_cap_desc",
                  "per_page": min(n, 250), "page": 1}
        for _ in range(2):
            try:
                r = requests.get(f"{cg.BASE}/coins/markets", params=params,
                                 headers=cg._headers(), timeout=12)
                if r.status_code == 200:
                    bases = {str(c.get("symbol", "")).upper() for c in r.json() if isinstance(c, dict)}
                    if bases:
                        return bases
            except Exception:
                pass
        return None
    except Exception:
        return None


def build_universe(top_n=None, min_volume=None, use_coingecko=True):
    """Construit l'univers (best-effort). QUALITÉ toujours appliquée : CoinGecko top-mcap si
    dispo, sinon repli crypto majeur -> jamais de volume non filtré (exclut xStocks/junk).
    Repli sur les ancres si le réseau Bitget échoue."""
    top_n = int(_cfg("UNIVERSE_TOP_N", 20) if top_n is None else top_n)
    min_volume = float(_cfg("UNIVERSE_MIN_VOLUME_USDT", 5_000_000) if min_volume is None else min_volume)
    tickers = _bitget_tickers()
    if not tickers:
        return _anchors()
    quality = (_coingecko_top_bases() if use_coingecko else None) or _FALLBACK_CRYPTO
    return rank_by_volume(tickers, top_n=top_n, min_volume=min_volume, quality=quality)


def _enabled():
    """Univers dynamique armé ? Via .env (DYNAMIC_UNIVERSE=1) OU config — l'option .env
    évite d'éditer un fichier suivi par git (sinon `git pull --ff-only` échouerait)."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    if os.getenv("DYNAMIC_UNIVERSE", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(_cfg("DYNAMIC_UNIVERSE", False))


def symbols(ttl=900):
    """Liste de symboles à analyser. Si l'univers dynamique n'est pas armé -> config.SYMBOLS
    (comportement historique). Sinon univers dynamique, caché `ttl` s. Ne lève jamais."""
    if not _enabled():
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
    dyn = _enabled()
    return ("=== UNIVERS D'ANALYSE ===\n"
            f"Mode : {'DYNAMIQUE top-N (Bitget volume + filtre CoinGecko)' if dyn else 'liste figée (config.SYMBOLS)'}\n"
            f"{len(uni)} symboles : {', '.join(uni[:25])}{' …' if len(uni) > 25 else ''}\n"
            "Lecture seule, aucun ordre. VERDICT: SAFE")


def main():
    print(build_report())


if __name__ == "__main__":
    main()
