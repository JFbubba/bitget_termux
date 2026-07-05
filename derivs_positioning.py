"""derivs_positioning.py — positionnement dérivés multi-venues (LECTURE SEULE).

Classement : SAFE. Reseau public en lecture seule, aucun ordre, aucun secret.

But : exposer la famille de données JAMAIS couverte par la recherche d'alpha du
dépôt — le positionnement dérivés : funding, open interest, basis perp-spot et
ratio de comptes long/short. Motif empirique : RESEARCH_NOTES §36-37 n'ont
balayé que des signaux dérivés des bougies (201 + ~350 variants, tous négatifs
sous déflation multiple-testing) ; le funding et la foule L/S portent une
information ORTHOGONALE au prix (le coût du levier et le côté du troupeau).
Consommé en aval par l'agent « carry » du cerveau et le moniteur de carry.

Contrat d'échec (fail-safe) : chaque fetch est best-effort derrière
runtime_cache (stale-while-error) : dans le TTL -> mémoire, panne -> dernière
valeur connue, panne totale -> valeur neutre ({} / [] / None, foule 0.0).
JAMAIS d'exception propagée à l'appelant.

CLI : python derivs_positioning.py [SYMBOL]   (ex. BTCUSDT)
"""

import statistics
import sys
import time

import requests

from config_utils import cfg as _cfg
from numeric_utils import safe_float

BITGET_MIX_TICKER_URL = "https://api.bitget.com/api/v2/mix/market/ticker"
BITGET_SPOT_TICKER_URL = "https://api.bitget.com/api/v2/spot/market/tickers"
BITGET_LS_URL = "https://api.bitget.com/api/v2/mix/market/account-long-short"
BITGET_FUND_HIST_URL = "https://api.bitget.com/api/v2/mix/market/history-fund-rate"
BINANCE_PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
BYBIT_FUND_HIST_URL = "https://api.bybit.com/v5/market/funding/history"
UA = {"User-Agent": "Mozilla/5.0"}
PRODUCT_TYPE = "usdt-futures"


# ---------- coeurs purs (testables) ----------

def basis_en_pct(perp, spot):
    """PUR. Basis perp vs spot en % : 100*(perp-spot)/spot.

    None si l'une des entrées est absente/illisible ou si spot <= 0."""
    p = safe_float(perp)
    s = safe_float(spot)
    if p is None or s is None or s <= 0:
        return None
    return 100.0 * (p - s) / s


def funding_zscore(historique, courant):
    """PUR. Z-score du funding courant vs son historique (stdlib, sans numpy).

    None si courant illisible, moins de 10 points valides dans l'historique,
    ou écart-type ~0 (funding épinglé : le z n'a pas de sens)."""
    c = safe_float(courant)
    if c is None:
        return None
    vals = [safe_float(v) for v in (historique or [])]
    vals = [v for v in vals if v is not None]
    if len(vals) < 10:
        return None
    moyenne = statistics.fmean(vals)
    ecart = statistics.stdev(vals)
    if ecart <= 1e-12:
        return None
    return (c - moyenne) / ecart


def foule(ls_ratio):
    """PUR. Score de foule dans [-1, +1] depuis le ratio de comptes long/short.

    Formule fermée continue (symétrique en inversant le ratio) :
      ratio >= 1 : +clamp((ratio - 1) / 1.5)      -> 1.0 = équilibre = 0,
                                                     >= 2.5 = +1.0 (foule très long)
      ratio <  1 : -clamp((1/ratio - 1) / 1.5)    -> <= 0.4 = -1.0 (foule très short)
    Neutre 0.0 si ratio None/illisible/<= 0. Graduel entre les bornes ; lecture
    contrarienne : +1 = troupeau massivement long, -1 = massivement short."""
    r = safe_float(ls_ratio)
    if r is None or r <= 0:
        return 0.0
    if r >= 1.0:
        return min(1.0, (r - 1.0) / 1.5)
    return -min(1.0, (1.0 / r - 1.0) / 1.5)


def parse_ticker_mix(payload):
    """PUR. Payload Bitget mix ticker -> {funding, oi, mark, index, perp_last}.

    Tolère None/{}/champs manquants : chaque champ illisible devient None."""
    rows = (payload or {}).get("data") or []
    first = rows[0] if rows and isinstance(rows[0], dict) else {}
    return {
        "funding": safe_float(first.get("fundingRate")),
        "oi": safe_float(first.get("holdingAmount")),
        "mark": safe_float(first.get("markPrice")),
        "index": safe_float(first.get("indexPrice")),
        "perp_last": safe_float(first.get("lastPr")),
    }


def parse_spot_last(payload):
    """PUR. Payload Bitget spot tickers -> dernier prix spot (float|None)."""
    rows = (payload or {}).get("data") or []
    first = rows[0] if rows and isinstance(rows[0], dict) else {}
    return safe_float(first.get("lastPr"))


def parse_ls_serie(payload):
    """PUR. Payload account-long-short -> [longShortAccountRatio] trié par ts ASC.

    L'API rend des strings, potentiellement dans le désordre ; les points
    illisibles sont ignorés. Le plus récent est EN DERNIER."""
    points = []
    for item in (payload or {}).get("data") or []:
        if not isinstance(item, dict):
            continue
        ratio = safe_float(item.get("longShortAccountRatio"))
        ts = safe_float(item.get("ts"), default=0.0)
        if ratio is not None:
            points.append((ts, ratio))
    points.sort(key=lambda p: p[0])
    return [r for _, r in points]


def parse_funding_history(payload):
    """PUR. Payload history-fund-rate -> [fundingRate] trié par fundingTime ASC.

    Le plus récent est EN DERNIER ; les points illisibles sont ignorés."""
    points = []
    for item in (payload or {}).get("data") or []:
        if not isinstance(item, dict):
            continue
        rate = safe_float(item.get("fundingRate"))
        ts = safe_float(item.get("fundingTime"), default=0.0)
        if rate is not None:
            points.append((ts, rate))
    points.sort(key=lambda p: p[0])
    return [r for _, r in points]


def moyenne_venues(venues):
    """PUR. {venue: funding|None} -> (moyenne des non-None | None, nb de venues valides)."""
    valides = [v for v in (venues or {}).values() if safe_float(v) is not None]
    if not valides:
        return None, 0
    return sum(float(v) for v in valides) / len(valides), len(valides)


def _fmt_funding(x):
    """PUR. Fraction de funding -> pourcentage lisible ('n/a' si None)."""
    return "n/a" if x is None else f"{100.0 * x:+.4f} %"


def _fmt(x, dec=2):
    """PUR. Nombre -> chaîne ('n/a' si None)."""
    return "n/a" if x is None else f"{x:.{dec}f}"


# ---------- reseau (best-effort) ----------

def _get_json(url, params):
    """GET public unique (timeout 8 s, UNE tentative, sans retry) -> JSON décodé."""
    reponse = requests.get(url, params=params, headers=UA, timeout=8)
    reponse.raise_for_status()
    return reponse.json()


def _funding_bitget(sym):
    """Funding Bitget courant (fraction). Peut lever : l'appelant enveloppe."""
    return parse_ticker_mix(_get_json(
        BITGET_MIX_TICKER_URL, {"symbol": sym, "productType": PRODUCT_TYPE}))["funding"]


def _funding_binance(sym):
    """Funding Binance courant (fraction). Peut lever : l'appelant enveloppe."""
    data = _get_json(BINANCE_PREMIUM_URL, {"symbol": sym})
    return safe_float((data or {}).get("lastFundingRate"))


def _funding_okx(sym):
    """Funding OKX courant (fraction). BASE-USDT-SWAP (BASE = symbole sans USDT)."""
    base = sym[:-4] if sym.endswith("USDT") else sym
    rows = (_get_json(OKX_FUNDING_URL, {"instId": f"{base}-USDT-SWAP"}) or {}).get("data") or []
    return safe_float(rows[0].get("fundingRate")) if rows and isinstance(rows[0], dict) else None


def _funding_bybit(sym):
    """Funding Bybit courant (fraction), via son historique (dernier point)."""
    data = _get_json(BYBIT_FUND_HIST_URL,
                     {"category": "linear", "symbol": sym, "limit": "1"})
    rows = ((data or {}).get("result") or {}).get("list") or []
    return safe_float(rows[0].get("fundingRate")) if rows and isinstance(rows[0], dict) else None


def fetch_snapshot(symbol="BTCUSDT"):
    """Snapshot positionnement dérivés Bitget (funding, OI, basis, foule L/S).

    Caché 300 s (clé 'pos:{SYM}'), best-effort : {} si la source est injoignable
    (jamais d'exception). Le spot et la série L/S sont optionnels : leur panne
    isolée laisse leurs champs à None sans invalider le reste."""
    import runtime_cache as rc
    sym = str(symbol or "BTCUSDT").upper()
    ttl = _cfg("DERIVS_POS_SNAP_TTL_S", 300)

    def _fetch():
        tick = parse_ticker_mix(_get_json(
            BITGET_MIX_TICKER_URL, {"symbol": sym, "productType": PRODUCT_TYPE}))
        try:
            spot_last = parse_spot_last(_get_json(BITGET_SPOT_TICKER_URL, {"symbol": sym}))
        except Exception:
            spot_last = None
        try:
            serie = parse_ls_serie(_get_json(
                BITGET_LS_URL, {"symbol": sym, "productType": PRODUCT_TYPE, "period": "1h"}))
        except Exception:
            serie = []
        return {
            "symbol": sym,
            "funding": tick["funding"],
            "funding_interval_h": 8,
            "oi": tick["oi"],
            "mark": tick["mark"],
            "index": tick["index"],
            "perp_last": tick["perp_last"],
            "spot_last": spot_last,
            "basis_pct": basis_en_pct(tick["perp_last"], spot_last),
            "ls_ratio": serie[-1] if serie else None,
            "ls_serie": serie,
            "ts": int(time.time()),
        }

    try:
        return rc.get(f"pos:{sym}", ttl, _fetch, fallback={}) or {}
    except Exception:
        return {}


def fetch_funding_multi(symbol="BTCUSDT"):
    """Funding courant par venue (Bitget/Binance/OKX/Bybit) + moyenne inter-venues.

    Caché 900 s (clé 'fundmulti:{SYM}'), best-effort : {} si AUCUNE venue ne
    répond (jamais d'exception). Chaque venue est sous son propre try/except ->
    un symbole coté sur une seule venue (ex. XAUTUSDT) reste exploitable."""
    import runtime_cache as rc
    sym = str(symbol or "BTCUSDT").upper()
    ttl = _cfg("DERIVS_POS_MULTI_TTL_S", 900)

    def _fetch():
        venues = {}
        for nom, fn in (("bitget", _funding_bitget), ("binance", _funding_binance),
                        ("okx", _funding_okx), ("bybit", _funding_bybit)):
            try:
                venues[nom] = fn(sym)
            except Exception:
                venues[nom] = None
        moyenne, nb = moyenne_venues(venues)
        if nb == 0:
            raise RuntimeError("aucune venue joignable")   # -> stale puis fallback {}
        venues["moyenne"] = moyenne
        venues["venues"] = nb
        return venues

    try:
        return rc.get(f"fundmulti:{sym}", ttl, _fetch, fallback={}) or {}
    except Exception:
        return {}


def fetch_funding_history(symbol="BTCUSDT", limit=60):
    """Historique du funding Bitget, chronologique ASC (récent EN DERNIER).

    Caché 3600 s (clé 'fundhist:{SYM}'), best-effort : [] si la source est
    injoignable (jamais d'exception)."""
    import runtime_cache as rc
    sym = str(symbol or "BTCUSDT").upper()
    ttl = _cfg("DERIVS_POS_HIST_TTL_S", 3600)

    def _fetch():
        return parse_funding_history(_get_json(
            BITGET_FUND_HIST_URL,
            {"symbol": sym, "productType": PRODUCT_TYPE, "pageSize": str(int(limit))}))

    try:
        out = rc.get(f"fundhist:{sym}", ttl, _fetch, fallback=[])
        return out if isinstance(out, list) else []
    except Exception:
        return []


def build_report(symbol="BTCUSDT"):
    sym = str(symbol or "BTCUSDT").upper()
    snap = fetch_snapshot(sym)
    multi = fetch_funding_multi(sym)
    hist = fetch_funding_history(sym)
    z = funding_zscore(hist, snap.get("funding"))
    crowd = foule(snap.get("ls_ratio"))
    lignes = [
        f"=== POSITIONNEMENT DÉRIVÉS — {sym} (lecture seule) ===",
        (f"Funding Bitget : {_fmt_funding(snap.get('funding'))} / "
         f"{snap.get('funding_interval_h', 8)} h | z vs {len(hist)} derniers : "
         f"{_fmt(z)}"),
        (f"Open interest  : {_fmt(snap.get('oi'), 1)} (base) | "
         f"mark {_fmt(snap.get('mark'))} | index {_fmt(snap.get('index'))}"),
        (f"Basis perp/spot: {_fmt(snap.get('basis_pct'), 4)} % "
         f"(perp {_fmt(snap.get('perp_last'))} vs spot {_fmt(snap.get('spot_last'))})"),
        (f"Ratio L/S      : {_fmt(snap.get('ls_ratio'))} sur "
         f"{len(snap.get('ls_serie') or [])} pts 1h -> foule {crowd:+.2f} "
         f"(+1 = troupeau très long, -1 = très short)"),
        ("Funding venues : "
         + " | ".join(f"{v} {_fmt_funding(multi.get(v))}"
                      for v in ("bitget", "binance", "okx", "bybit"))),
        (f"Moyenne venues : {_fmt_funding(multi.get('moyenne'))} "
         f"({multi.get('venues', 0)} venue(s))"),
        "",
        "Lecture seule. Aucun ordre. VERDICT: SAFE",
    ]
    return "\n".join(lignes)


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(symbol))


if __name__ == "__main__":
    main()
