#!/usr/bin/env python3
"""bitget_flows.py — flux « smart-money » depuis les endpoints REST Bitget (fund-flow, whale-net-flow).

Classement : SAFE. Lecture seule (market-data PUBLIQUE, sans clé), aucun ordre, aucun secret.

Sources AUTORITATIVES (vérifiées contre l'API réelle le 18/07/2026 — cf. docs/BITGET_REFERENCE.md) :
- `/api/v2/spot/market/fund-flow` : segmentation du volume acheteur/vendeur par TAILLE d'acteur
  (baleine / dauphin / poisson) + ratios -> composition « smart-money » instantanée.
- `/api/v2/spot/market/whale-net-flow` : flux NET des baleines par période (volume signé).

Le bot n'avait AUCUNE segmentation smart-money : c'est une capacité nouvelle. Endpoints SPOT
(symbole spot, ex. BTCUSDT).

⚠️ Discipline : FEATURE de mesure (labo/dashboard/ombre) — PAS branchée au vote du banc gelé à 14
sans preuve d'IC NETTE DE FRAIS. Prior honnête (recherche) : les flux intraday sont souvent
bruités -> mesurer avant tout armement. Les murs restent inchangés.
"""
import bitget_market_data as bmd

FUND_FLOW_ENDPOINT = "/api/v2/spot/market/fund-flow"
WHALE_NET_ENDPOINT = "/api/v2/spot/market/whale-net-flow"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def parse_fund_flow(d):
    """PUR. Snapshot fund-flow -> composition smart-money. None si illisible.
    {whale_buy, whale_sell, whale_net, whale_buy_ratio, dolphin_net, fish_net, net_all, whale_bias}."""
    if not isinstance(d, dict):
        return None
    wb, ws = _f(d.get("whaleBuyVolume")), _f(d.get("whaleSellVolume"))
    db, ds = _f(d.get("dolphinBuyVolume")), _f(d.get("dolphinSellVolume"))
    fb, fs = _f(d.get("fishBuyVolume")), _f(d.get("fishSellVolume"))
    whale_net = wb - ws
    tot_buy, tot_sell = wb + db + fb, ws + ds + fs
    return {
        "whale_buy": wb, "whale_sell": ws, "whale_net": whale_net,
        "whale_buy_ratio": (wb / (wb + ws)) if (wb + ws) else None,
        "dolphin_net": db - ds, "fish_net": fb - fs,
        "net_all": tot_buy - tot_sell,
        "whale_bias": "buy" if whale_net > 0 else ("sell" if whale_net < 0 else "neutral"),
    }


def whale_net_series(data):
    """PUR. [{date|ts, volume}] -> [{ts:int, net, cum}] trié ts ASC (net baleine par période, cumulé)."""
    rows = []
    for it in (data or []):
        try:
            ts = int(it.get("date") if it.get("date") is not None else it.get("ts"))
        except (TypeError, ValueError):
            continue
        rows.append({"ts": ts, "net": _f(it.get("volume"))})
    rows.sort(key=lambda r: r["ts"])
    cum = 0.0
    for r in rows:
        cum += r["net"]
        r["cum"] = cum
    return rows


def whale_net_summary(data):
    """PUR. {n, last_net, cum, bias} du flux net baleine. None si vide."""
    s = whale_net_series(data)
    if not s:
        return None
    return {"n": len(s), "last_net": s[-1]["net"], "cum": s[-1]["cum"],
            "bias": "buy" if s[-1]["cum"] > 0 else ("sell" if s[-1]["cum"] < 0 else "neutral")}


def fetch_fund_flow(symbol):
    """I/O best-effort : composition smart-money instantanée. None si indispo. Lecture seule."""
    try:
        return parse_fund_flow(bmd._get(FUND_FLOW_ENDPOINT, {"symbol": symbol}))
    except Exception:
        return None


def fetch_whale_net_flow(symbol, period="1h"):
    """I/O best-effort : série du flux net baleine (liste vide si indispo). Lecture seule."""
    try:
        d = bmd._get(WHALE_NET_ENDPOINT, {"symbol": symbol, "period": period})
        return d if isinstance(d, list) else []
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    ff = fetch_fund_flow(sym)
    wn = whale_net_summary(fetch_whale_net_flow(sym, "1h"))
    if ff:
        print(f"{sym} fund-flow · baleines net {ff['whale_net']:+.3f} "
              f"(ratio ach. {('%.1f%%' % (ff['whale_buy_ratio']*100)) if ff['whale_buy_ratio'] is not None else '—'}, "
              f"biais {ff['whale_bias']}) · net tous acteurs {ff['net_all']:+.3f}")
    if wn:
        print(f"{sym} whale-net-flow 1h · dernier {wn['last_net']:+.2f} · cumulé {wn['cum']:+.2f} · biais {wn['bias']} · {wn['n']} pts")
