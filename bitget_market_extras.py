#!/usr/bin/env python3
"""bitget_market_extras.py — wrappers de market-data PUBLIQUE Bitget (endpoints v2 + v3).

Classement : SAFE. Lecture seule (market-data PUBLIQUE, SANS clé), aucun ordre, aucun secret.

Prolonge `bitget_market_data.py` / `bitget_flows.py` avec les endpoints publics à valeur
signal/référence cartographiés dans `docs/BITGET_API_CATALOG.md` et VÉRIFIÉS contre l'API réelle
le 18/07/2026 (discipline SDK≠live : chaque chemin ci-dessous a répondu `code=00000`).

Endpoints exposés (tous publics, sans clé) :
- Positionnement de foule (long/short), 3 angles :
  · `/api/v2/mix/market/long-short`          — ratio actif TAKER (buy/sell agressif)
  · `/api/v2/mix/market/position-long-short` — ratio par POSITIONS
  · `/api/v2/mix/market/account-long-short`  — ratio par COMPTES
- `/api/v3/market/liquidations`              — flux de liquidations PUBLIC (substitut gratuit Coinglass)
- `/api/v3/market/futures-active-buy-sell`   — volume actif buy/sell -> Volume Delta
- `/api/v2/mix/market/funding-time`          — prochain settlement + période
- `/api/v2/mix/market/contracts`             — config contrat (min-sizes, frais, leviers) -> faisabilité

⚠️ Discipline : FEATURES de MESURE (labo/dashboard/ombre) — RIEN n'est branché au vote du banc gelé
à 14 sans preuve d'IC NETTE DE FRAIS. Prior honnête : positionnement/liquidations sont des signaux
contrariens connus mais BRUITÉS -> mesurer avant tout armement. Les murs argent restent inchangés.
Sémantique du `side` des liquidations laissée BRUTE (non supposée) : à interpréter par la mesure.
"""
import bitget_market_data as bmd

LONG_SHORT_EP = "/api/v2/mix/market/long-short"             # ratio actif taker
POSITION_LS_EP = "/api/v2/mix/market/position-long-short"   # ratio par positions
ACCOUNT_LS_EP = "/api/v2/mix/market/account-long-short"     # ratio par comptes
LIQUIDATIONS_EP = "/api/v3/market/liquidations"
ACTIVE_BUY_SELL_EP = "/api/v3/market/futures-active-buy-sell"
FUNDING_TIME_EP = "/api/v2/mix/market/funding-time"
CONTRACTS_EP = "/api/v2/mix/market/contracts"

# jeux de champs par variante long/short (les 3 endpoints diffèrent de nom)
_LS_FIELDS = {
    "active":   ("longRatio", "shortRatio", "longShortRatio"),
    "position": ("longPositionRatio", "shortPositionRatio", "longShortPositionRatio"),
    "account":  ("longAccountRatio", "shortAccountRatio", "longShortAccountRatio"),
}


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


# ---------- positionnement de foule (long/short) ----------

def parse_long_short(data, kind="position"):
    """PUR. Liste de points {ratios, ts} -> dernier point (ts max). None si vide/illisible.
    kind ∈ {active, position, account}. Retour {long, short, ratio, bias, n, ts}."""
    if not isinstance(data, list) or not data or kind not in _LS_FIELDS:
        return None
    lf, sf, rf = _LS_FIELDS[kind]
    last = max(data, key=lambda d: _i(d.get("ts")))
    lo, sh = _f(last.get(lf)), _f(last.get(sf))
    ratio = _f(last.get(rf)) if last.get(rf) is not None else ((lo / sh) if sh else None)
    return {
        "long": lo, "short": sh, "ratio": ratio, "n": len(data), "ts": _i(last.get("ts")),
        "bias": "long" if lo > sh else ("short" if sh > lo else "neutral"),
    }


# ---------- liquidations (v3) ----------

def parse_liquidations(data):
    """PUR. {list:[{side, price, amount, ts}]} ou liste nue -> totaux notional buy/sell, net, biais.
    None si vide. `side` gardé BRUT (buy/sell) — pas de supposition directionnelle."""
    rows = data.get("list") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        return None
    ba = sa = bn = sn = 0.0
    for it in rows:
        if not isinstance(it, dict):
            continue
        amt, px = _f(it.get("amount")), _f(it.get("price"))
        notional = amt * px
        if str(it.get("side", "")).lower() == "buy":
            ba += amt; bn += notional
        else:
            sa += amt; sn += notional
    net = bn - sn
    return {
        "n": len(rows), "buy_amount": ba, "sell_amount": sa,
        "buy_notional": bn, "sell_notional": sn, "net_notional": net,
        "bias": "buy" if net > 0 else ("sell" if net < 0 else "neutral"),
    }


# ---------- volume delta actif (v3 futures-active-buy-sell) ----------

def parse_active_buy_sell(data):
    """PUR. Liste {buyVolume, sellVolume, ts} -> somme buy/sell, delta signé, biais. None si vide."""
    if not isinstance(data, list) or not data:
        return None
    buy = sum(_f(d.get("buyVolume")) for d in data if isinstance(d, dict))
    sell = sum(_f(d.get("sellVolume")) for d in data if isinstance(d, dict))
    delta = buy - sell
    return {"n": len(data), "buy": buy, "sell": sell, "delta": delta,
            "bias": "buy" if delta > 0 else ("sell" if delta < 0 else "neutral")}


# ---------- prochain funding (v2 funding-time) ----------

def parse_next_funding(data):
    """PUR. [{symbol, nextFundingTime, ratePeriod}] -> {next_ts, period_h}. None si vide."""
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    d = data[0]
    return {"next_ts": _i(d.get("nextFundingTime")), "period_h": _i(d.get("ratePeriod"))}


# ---------- config contrat (v2 contracts) — faisabilité ----------

def parse_contract(data):
    """PUR. [{...}] ou {...} -> min_qty / min_notional_usdt / frais / intervalle funding / leviers.
    None si vide. Sert au filtre de FAISABILITÉ (notional bot vs minima du contrat)."""
    d = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
    if not d:
        return None
    return {
        "min_qty": _f(d.get("minTradeNum")),
        "min_notional_usdt": _f(d.get("minTradeUSDT")),
        "size_mult": _f(d.get("sizeMultiplier")),
        "maker": _f(d.get("makerFeeRate")),
        "taker": _f(d.get("takerFeeRate")),
        "fund_interval_h": _i(d.get("fundInterval")),
        "min_lever": _i(d.get("minLever")),
        "max_lever": _i(d.get("maxLever")),
        "status": d.get("symbolStatus"),
    }


# ---------- I/O best-effort (fail-safe : None/[]/défaut si indispo) ----------

def fetch_long_short(symbol, kind="position", period="5m", product_type="usdt-futures"):
    """Lecture seule. Ratio long/short (variante `kind`). None si indispo."""
    ep = {"active": LONG_SHORT_EP, "position": POSITION_LS_EP, "account": ACCOUNT_LS_EP}.get(kind)
    if ep is None:
        return None
    params = {"symbol": symbol, "period": period}
    if kind == "account" or ep is LONG_SHORT_EP:
        params.setdefault("productType", product_type)
    try:
        return parse_long_short(bmd._get(ep, params), kind)
    except Exception:
        return None


def fetch_liquidations(symbol, category="USDT-FUTURES", limit=100):
    """Lecture seule. Flux de liquidations public agrégé. None si indispo."""
    try:
        return parse_liquidations(bmd._get(LIQUIDATIONS_EP,
                                           {"category": category, "symbol": symbol, "limit": str(limit)}))
    except Exception:
        return None


def fetch_active_buy_sell(symbol, period="5m"):
    """Lecture seule. Volume delta actif (buy/sell agressif). None si indispo."""
    try:
        return parse_active_buy_sell(bmd._get(ACTIVE_BUY_SELL_EP, {"symbol": symbol, "period": period}))
    except Exception:
        return None


def fetch_next_funding(symbol, product_type="usdt-futures"):
    """Lecture seule. Prochain settlement de funding + période. None si indispo."""
    try:
        return parse_next_funding(bmd._get(FUNDING_TIME_EP, {"symbol": symbol, "productType": product_type}))
    except Exception:
        return None


def fetch_contract(symbol, product_type="usdt-futures"):
    """Lecture seule. Config du contrat (minima, frais, leviers). None si indispo."""
    try:
        return parse_contract(bmd._get(CONTRACTS_EP, {"symbol": symbol, "productType": product_type}))
    except Exception:
        return None


def min_notional_usdt(symbol, product_type="usdt-futures"):
    """Notional minimal (USDT) pour ouvrir sur ce contrat — filtre de faisabilité. None si indispo."""
    c = fetch_contract(symbol, product_type)
    return c["min_notional_usdt"] if c else None


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    ls = fetch_long_short(sym, "position", "5m")
    li = fetch_liquidations(sym)
    ab = fetch_active_buy_sell(sym, "5m")
    nf = fetch_next_funding(sym)
    ct = fetch_contract(sym)
    if ls:
        print(f"{sym} positions L/S · long {ls['long']:.4f} / short {ls['short']:.4f} · biais {ls['bias']}")
    if li:
        print(f"{sym} liquidations · buy {li['buy_notional']:,.0f} vs sell {li['sell_notional']:,.0f} "
              f"· net {li['net_notional']:+,.0f} · biais {li['bias']} · {li['n']} evts")
    if ab:
        print(f"{sym} volume-delta actif · buy {ab['buy']:,.0f} - sell {ab['sell']:,.0f} = {ab['delta']:+,.0f} ({ab['bias']})")
    if nf:
        print(f"{sym} prochain funding · ts {nf['next_ts']} · période {nf['period_h']} h")
    if ct:
        print(f"{sym} contrat · min {ct['min_notional_usdt']:g} USDT / {ct['min_qty']:g} · "
              f"frais mk/tk {ct['maker']}/{ct['taker']} · levier ≤×{ct['max_lever']} · {ct['status']}")
