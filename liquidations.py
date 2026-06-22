"""
liquidations.py — carte de liquidations / heatmap (LECTURE SEULE).

Classement : SAFE. Aucun ordre. Estime où se situent les **pools de
liquidations** (clusters) au-dessus et en dessous du prix, à partir de données
RÉELLES (prix + open interest multi-exchange via aggregated_derivs) et d'une
distribution de levier. Les grosses poches de liquidations agissent comme des
AIMANTS de liquidité : le prix a tendance à être attiré vers elles.

⚠️ C'est un MODÈLE (prix × levier × OI), PAS le flux de liquidations rapporté
par les exchanges (qui nécessite une clé Coinglass / un websocket). Les niveaux
sont des estimations d'aide à la décision, pas des chiffres officiels.

Fonctions pures et testables : liquidation_levels, liquidation_skew,
cluster_map. fetch_liquidations ajoute le réseau et dégrade proprement.

CLI : python liquidations.py [SYMBOL]
"""

import sys

# distribution de levier retail typique (somme des parts ~ 1.0)
DEFAULT_TIERS = [
    (100, 0.05), (50, 0.10), (25, 0.18), (20, 0.15),
    (10, 0.22), (5, 0.18), (3, 0.12),
]


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ---------- modèle (pur, testable) ----------

def liquidation_levels(price, oi_usd, long_share=0.5, tiers=None):
    """Niveaux de liquidation estimés autour du prix.

    long_share = part de l'OI détenue par les longs (>0.5 = longs surchargés).
    Retourne une liste de clusters {side, leverage, price, distance_pct,
    notional_usd}. Les longs se liquident SOUS le prix, les shorts AU-DESSUS.
    """
    if not price or not oi_usd or price <= 0 or oi_usd <= 0:
        return []
    long_share = _clamp(long_share, 0.1, 0.9)
    tiers = tiers or DEFAULT_TIERS
    out = []
    for lev, share in tiers:
        lp = price * (1 - 1.0 / lev)
        sp = price * (1 + 1.0 / lev)
        out.append({"side": "long", "leverage": lev, "price": round(lp, 2),
                    "distance_pct": round((lp - price) / price * 100, 2),
                    "notional_usd": oi_usd * long_share * share})
        out.append({"side": "short", "leverage": lev, "price": round(sp, 2),
                    "distance_pct": round((sp - price) / price * 100, 2),
                    "notional_usd": oi_usd * (1 - long_share) * share})
    return out


def liquidation_skew(levels, price, band_pct=8.0):
    """Déséquilibre des pools dans une bande ±band_pct, pondéré par la proximité.

    net dans [-1, 1] : >0 = les pools de SHORTS au-dessus dominent (aimant
    haussier) ; <0 = les pools de LONGS en dessous dominent (aimant baissier).
    """
    up = down = 0.0
    nearest_long = nearest_short = None
    for lv in levels:
        d = lv["distance_pct"]
        if abs(d) > band_pct:
            continue
        w = lv["notional_usd"] / (1.0 + abs(d))  # plus c'est proche, plus ça pèse
        if lv["side"] == "short":
            up += w
            if nearest_short is None or d < nearest_short["distance_pct"]:
                nearest_short = lv
        else:
            down += w
            if nearest_long is None or abs(d) < abs(nearest_long["distance_pct"]):
                nearest_long = lv
    tot = up + down
    net = ((up - down) / tot) if tot > 0 else 0.0
    return {"net": round(net, 3), "up_pool_usd": up, "down_pool_usd": down,
            "nearest_long": nearest_long, "nearest_short": nearest_short,
            "band_pct": band_pct}


def cluster_map(levels, bucket_pct=1.0, top=8):
    """Agrège les niveaux en buckets de prix (heatmap), triés par taille."""
    buckets = {}
    for lv in levels:
        key = round(lv["distance_pct"] / bucket_pct)
        b = buckets.setdefault(key, {"distance_pct": round(key * bucket_pct, 2),
                                     "side": lv["side"], "notional_usd": 0.0,
                                     "price": lv["price"]})
        b["notional_usd"] += lv["notional_usd"]
    return sorted(buckets.values(), key=lambda x: -x["notional_usd"])[:top]


# ---------- réseau (dégrade proprement) ----------

def fetch_liquidations(symbol="BTCUSDT", band_pct=8.0):
    symbol = symbol.upper()
    try:
        import aggregated_derivs as ad
        agg = ad.fetch_aggregate(symbol)
    except Exception:
        agg = {}
    oi = agg.get("total_oi_usd")
    funding = agg.get("oi_weighted_funding") or 0.0
    marks = [(p.get("mark"), p.get("oi_usd")) for p in agg.get("exchanges", []) if p.get("mark")]
    price = None
    if marks:
        tot = sum((o or 0) for _, o in marks)
        price = (sum(m * (o or 0) for m, o in marks) / tot) if tot else marks[0][0]
    # funding positif -> longs surchargés -> part long plus grande
    long_share = _clamp(0.5 + funding * 500, 0.2, 0.8)
    levels = liquidation_levels(price, oi, long_share)
    return {
        "symbol": symbol, "price": price, "total_oi_usd": oi, "funding": funding,
        "long_share": round(long_share, 3),
        "skew": liquidation_skew(levels, price, band_pct) if (levels and price) else None,
        "clusters": cluster_map(levels) if levels else [],
        "model": "estimation prix×levier×OI (pas un flux exchange)",
    }


def _human(n):
    if n is None:
        return "—"
    n = float(n)
    for unit in ("", "K", "M", "B", "T"):
        if abs(n) < 1000:
            return f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}P"


def build_report(d):
    sk = d.get("skew") or {}
    net = sk.get("net")
    lean = "—"
    if net is not None:
        lean = "haussier (short-liq au-dessus)" if net > 0.15 else \
               "baissier (long-liq en dessous)" if net < -0.15 else "équilibré"
    lines = [
        f"=== LIQUIDATIONS (modèle) {d['symbol']} ===",
        f"Prix {d.get('price')} | OI total ${_human(d.get('total_oi_usd'))} | "
        f"funding {d.get('funding', 0) * 100:+.4f}% | longs ~{int(d.get('long_share', 0) * 100)}%",
        f"Aimant net : {net:+.2f} ({lean})" if net is not None else "Aimant net : —",
        "",
        "Clusters majeurs (distance · côté · taille estimée) :",
    ]
    for c in d.get("clusters", []):
        lines.append(f"  {c['distance_pct']:+5.1f}%  {c['side']:<5} ${_human(c['notional_usd'])}")
    nl, ns = sk.get("nearest_long"), sk.get("nearest_short")
    if nl or ns:
        lines.append("")
        if nl:
            lines.append(f"Plus proche long  : {nl['distance_pct']:+.1f}% (${_human(nl['notional_usd'])})")
        if ns:
            lines.append(f"Plus proche short : {ns['distance_pct']:+.1f}% (${_human(ns['notional_usd'])})")
    lines.append("")
    lines.append("⚠️ Modèle estimatif, PAS un flux de liquidations exchange.")
    lines.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(fetch_liquidations(symbol)))


if __name__ == "__main__":
    main()
