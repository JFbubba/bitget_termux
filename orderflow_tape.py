#!/usr/bin/env python3
"""orderflow_tape.py — lecture de la TAPE (fills) Bitget : footprint, gros trades, CVD spot vs futures.

Classement : SAFE. Lecture seule (market-data PUBLIQUE, fills SANS clé), aucun ordre, aucun secret.

Comble les 3 manques d'orderflow identifiés le 18/07 (les autres existent déjà : `taker_flow`,
`microstructure`, `technicals` VWAP/volume-profile/basis/heatmap, `liquidations`, `funding_history`,
`bitget_market_data` OI/depth) :
- FOOTPRINT bid×ask : delta (buy−sell) par bin de PRIX — l'empreinte d'agressivité par niveau.
- GROS TRADES : prints de la tape au-dessus d'un seuil USD (+ split buy/sell).
- CVD SPOT vs FUTURES : divergence des flux agressifs spot et futures (signal institutionnel connu).

Sources vérifiées live 18/07 : `/api/v2/spot/market/fills` et `/api/v2/mix/market/fills`
(item `{symbol, tradeId, side(buy/sell agressif), price, size, ts}`).

⚠️ FEATURE de MESURE (labo/dashboard/ombre) — NON branchée au banc gelé à 14 sans preuve d'IC NETTE
de frais. Murs inchangés. Prior honnête : la tape est bruitée intraday -> mesurer avant tout armement.
"""
import bitget_market_data as bmd

SPOT_FILLS_EP = "/api/v2/spot/market/fills"
FUT_FILLS_EP = "/api/v2/mix/market/fills"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _i(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def parse_fills(raw):
    """PUR. Fills Bitget (bruts) -> [{ts:int, price, size, side}] triés ts ASC, side minuscule. [] si vide."""
    out = []
    for it in (raw or []):
        if not isinstance(it, dict):
            continue
        out.append({"ts": _i(it.get("ts")), "price": _f(it.get("price")),
                    "size": _f(it.get("size")), "side": str(it.get("side") or "").lower()})
    out.sort(key=lambda r: r["ts"])
    return out


def cvd(fills):
    """PUR. Tape parsée -> CVD agressif {n, buy, sell, delta, bias}. None si vide."""
    if not fills:
        return None
    buy = sum(_f(x.get("size")) for x in fills if str(x.get("side")).lower() == "buy")
    sell = sum(_f(x.get("size")) for x in fills if str(x.get("side")).lower() == "sell")
    delta = buy - sell
    return {"n": len(fills), "buy": buy, "sell": sell, "delta": delta,
            "bias": "buy" if delta > 0 else ("sell" if delta < 0 else "neutral")}


def footprint(fills, bins=12):
    """PUR. Tape parsée -> footprint : delta (buy−sell) par bin de PRIX. [] si vide.
    Retour [{price_lo, price_hi, buy, sell, delta}] par prix croissant (bins non vides seulement)."""
    if not fills:
        return []
    prices = [_f(x.get("price")) for x in fills if _f(x.get("price")) > 0]
    if not prices:
        return []
    lo, hi = min(prices), max(prices)
    if hi <= lo:                                       # tout au même prix -> 1 bin
        buy = sum(_f(x.get("size")) for x in fills if str(x.get("side")).lower() == "buy")
        sell = sum(_f(x.get("size")) for x in fills if str(x.get("side")).lower() == "sell")
        return [{"price_lo": lo, "price_hi": hi, "buy": buy, "sell": sell, "delta": buy - sell}]
    width = (hi - lo) / bins
    acc = {}
    for x in fills:
        side = str(x.get("side")).lower()
        if side not in ("buy", "sell"):
            continue
        idx = min(int((_f(x.get("price")) - lo) / width), bins - 1)
        b = acc.setdefault(idx, {"buy": 0.0, "sell": 0.0})
        b[side] += _f(x.get("size"))
    rows = []
    for idx in sorted(acc):
        buy, sell = acc[idx]["buy"], acc[idx]["sell"]
        rows.append({"price_lo": round(lo + idx * width, 6), "price_hi": round(lo + (idx + 1) * width, 6),
                     "buy": buy, "sell": sell, "delta": buy - sell})
    return rows


def large_trades(fills, min_usd=50000.0):
    """PUR. Tape parsée -> prints dont price*size >= min_usd. Toujours un dict (n=0 si aucun).
    {n, prints:[{ts, price, size, side, usd}] (tri USD desc), buy_usd, sell_usd}."""
    prints, buy_usd, sell_usd = [], 0.0, 0.0
    for x in (fills or []):
        usd = _f(x.get("price")) * _f(x.get("size"))
        if usd >= min_usd and usd > 0:
            side = str(x.get("side")).lower()
            prints.append({"ts": _i(x.get("ts")), "price": _f(x.get("price")),
                           "size": _f(x.get("size")), "side": side, "usd": round(usd, 2)})
            if side == "buy":
                buy_usd += usd
            elif side == "sell":
                sell_usd += usd
    prints.sort(key=lambda p: -p["usd"])
    return {"n": len(prints), "prints": prints, "buy_usd": round(buy_usd, 2), "sell_usd": round(sell_usd, 2)}


def cvd_divergence(spot_fills, fut_fills):
    """PUR. CVD spot vs CVD futures -> divergence. None si l'un des deux est vide.
    {spot_delta, fut_delta, diverge(signes opposés), note}. La divergence spot/futures est un
    signal institutionnel connu (qui MÈNE) — À MESURER, jamais supposé."""
    cs, cf = cvd(spot_fills), cvd(fut_fills)
    if cs is None or cf is None:
        return None
    sd, fd = cs["delta"], cf["delta"]
    diverge = (sd > 0 > fd) or (sd < 0 < fd)
    if diverge:
        note = "futures mène (spot oppose)" if abs(fd) >= abs(sd) else "spot mène (futures oppose)"
    else:
        note = "alignés"
    return {"spot_delta": sd, "fut_delta": fd, "diverge": diverge, "note": note}


# ---------- I/O best-effort (lecture seule, [] si indispo) ----------

def fetch_fills(symbol, venue="futures", limit=100):
    """Tape (fills) PARSÉE pour `venue` ∈ {spot, futures}. [] si indispo. Lecture seule."""
    try:
        if venue == "spot":
            raw = bmd._get(SPOT_FILLS_EP, {"symbol": symbol, "limit": str(limit)})
        else:
            raw = bmd._get(FUT_FILLS_EP, {"symbol": symbol, "productType": "usdt-futures", "limit": str(limit)})
        return parse_fills(raw)
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    fut = fetch_fills(sym, "futures", 100)
    spot = fetch_fills(sym, "spot", 100)
    c = cvd(fut)
    if c:
        print(f"{sym} CVD futures · buy {c['buy']:.3f} − sell {c['sell']:.3f} = {c['delta']:+.3f} "
              f"({c['bias']}) · {c['n']} prints")
    lt = large_trades(fut, min_usd=50000)
    print(f"{sym} gros trades futures (≥50k$) · {lt['n']} · buy {lt['buy_usd']:,.0f}$ vs sell {lt['sell_usd']:,.0f}$")
    fp = footprint(fut, bins=8)
    if fp:
        pk = max(fp, key=lambda b: abs(b["delta"]))
        print(f"{sym} footprint · bin dominant {pk['price_lo']:.1f}–{pk['price_hi']:.1f} · delta {pk['delta']:+.3f}")
    dv = cvd_divergence(spot, fut)
    if dv:
        print(f"{sym} CVD spot {dv['spot_delta']:+.3f} vs futures {dv['fut_delta']:+.3f} -> "
              f"{'DIVERGENCE' if dv['diverge'] else 'alignés'} ({dv['note']})")
