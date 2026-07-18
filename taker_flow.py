#!/usr/bin/env python3
"""taker_flow.py — Volume Delta / CVD depuis l'endpoint REST `taker-buy-sell` de Bitget.

Classement : SAFE. Lecture seule (market-data PUBLIQUE, sans clé), aucun ordre, aucun secret.

Source AUTORITATIVE (`/api/v2/mix/market/taker-buy-sell`, vérifiée contre l'API réelle le
18/07/2026 — cf. docs/BITGET_REFERENCE.md) : volume TAKER acheteur/vendeur PAR PÉRIODE, sur
TOUS les symboles perp. Elle donne un **Volume Delta aligné-période** et un **CVD cumulé**
SANS dépendre de la persistance de la tape WebSocket (qui ne couvre que 3 symboles BTC/ETH/SOL).
C'est un vrai delta d'AGRESSEUR (buy taker vs sell taker), pas un signe de bougie.

⚠️ Discipline : c'est une FEATURE de mesure (labo/dashboard/ombre) — elle N'est PAS branchée au
vote du banc gelé à 14 sans preuve d'IC NETTE DE FRAIS. Les murs restent inchangés.
"""
import bitget_market_data as bmd

ENDPOINT = "/api/v2/mix/market/taker-buy-sell"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def volume_delta_series(bars):
    """PUR. bars=[{ts, buyVolume, sellVolume}] -> [{ts:int, buy, sell, delta, cvd}] trié ts ASC.
    delta = buy - sell (Volume Delta d'agresseur, aligné-période) ; cvd = somme cumulée (CVD)."""
    rows = []
    for b in (bars or []):
        try:
            ts = int(b.get("ts"))
        except (TypeError, ValueError):
            continue
        buy, sell = _f(b.get("buyVolume")), _f(b.get("sellVolume"))
        rows.append({"ts": ts, "buy": buy, "sell": sell, "delta": buy - sell})
    rows.sort(key=lambda r: r["ts"])
    cvd = 0.0
    for r in rows:
        cvd += r["delta"]
        r["cvd"] = cvd
    return rows


def delta_summary(bars):
    """PUR. Lecture compacte du flux taker : {n, cvd, last_delta, last_buy_ratio, bias}.
    bias = signe du CVD ('buy'/'sell'/'neutral'). None si aucune barre exploitable."""
    s = volume_delta_series(bars)
    if not s:
        return None
    last = s[-1]
    tot = last["buy"] + last["sell"]
    return {
        "n": len(s),
        "cvd": last["cvd"],
        "last_delta": last["delta"],
        "last_buy_ratio": (last["buy"] / tot) if tot else None,
        "bias": "buy" if last["cvd"] > 0 else ("sell" if last["cvd"] < 0 else "neutral"),
    }


def fetch(symbol, period="5m", product_type=None, limit=None):
    """I/O best-effort : barres taker-buy-sell (liste vide si indispo). Lecture seule.
    `period` ∈ {5m,15m,30m,1h,4h,12h,1day} (comme les autres endpoints apidata Bitget)."""
    import config
    params = {"symbol": symbol, "productType": product_type or config.PRODUCT_TYPE, "period": period}
    if limit:
        params["limit"] = str(int(limit))
    try:
        d = bmd._get(ENDPOINT, params)
        return d if isinstance(d, list) else []
    except Exception:
        return []


def taker_delta(symbol, period="5m", product_type=None):
    """Convenience : fetch + delta_summary. None si indispo. Lecture seule."""
    return delta_summary(fetch(symbol, period=period, product_type=product_type))


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    per = sys.argv[2] if len(sys.argv) > 2 else "5m"
    r = taker_delta(sym, per)
    if r:
        print(f"{sym} {per} · CVD {r['cvd']:+.2f} · dernier delta {r['last_delta']:+.2f} "
              f"· ratio acheteur {('%.1f%%' % (r['last_buy_ratio']*100)) if r['last_buy_ratio'] is not None else '—'} "
              f"· biais {r['bias']} · {r['n']} barres")
    else:
        print(f"{sym} {per} : indisponible")
