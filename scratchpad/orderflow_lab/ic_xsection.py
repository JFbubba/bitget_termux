#!/usr/bin/env python3
"""ic_xsection.py — MESURE PUISSANTE de l'IC du Volume Delta (coupe transversale univers).

Corrige le labo n=30 : l'endpoint taker-buy-sell plafonne à 30 barres/symbole. Solution =
COUPE TRANSVERSALE sur les ~40 futures les plus liquides. À chaque barre t : classer les symboles
par Volume Delta, corréler (Spearman) aux rendements forward. -> série de ~30 IC transversaux ->
moyenne + t-stat (méthode factor-IC standard). Bien plus robuste + teste la GÉNÉRALISATION (pas
seulement BTC). Frais RÉALISTES : maker-both 4bps, mixte (maker+taker) 8bps, taker-both 12bps.

Lecture seule, mesure, aucun ordre. ERR-001 : échelle taker {5m..1day} (M1/W1 non offerts).
"""
import sys
sys.path.insert(0, "/root/bitget_termux_repo")
import math
import taker_flow
import technicals
import bitget_market_data as bmd

TOP_N = 30
LADDER = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1H", "4h": "4H", "12h": "12H"}
HORIZONS = [1, 2, 3]
FEES = {"maker_4": 4.0, "mixte_8": 8.0, "taker_12": 12.0}


def liquid_symbols(n=TOP_N):
    rows = bmd.fetch_tickers("usdt-futures") or []
    def vol(r):
        try:
            return float(r.get("usdtVolume") or r.get("quoteVolume") or 0)
        except (TypeError, ValueError):
            return 0.0
    syms = [r.get("symbol") for r in sorted(rows, key=vol, reverse=True) if r.get("symbol")]
    # garde USDT perp "purs" (évite les paires exotiques sans bougies)
    return [s for s in syms if str(s).endswith("USDT")][:n]


def _rank(a):
    order = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def _pearson(x, y):
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    syy = sum((v - my) ** 2 for v in y)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def spearman(x, y):
    return _pearson(_rank(x), _rank(y))


def build_panel(symbols, taker_period, gran):
    """{symbol: {ts: delta}} + {symbol: {ts: close}} sur l'intersection des ts."""
    deltas, closes = {}, {}
    for s in symbols:
        try:
            b = taker_flow.volume_delta_series(taker_flow.fetch(s, taker_period) or [])
            c = technicals.fetch_candles(s, gran, limit=60) or []
        except Exception:
            continue
        if len(b) < 10 or len(c) < 10:
            continue
        deltas[s] = {x["ts"]: x["delta"] for x in b}
        cc = {}
        for row in c:
            try:
                cc[int(row["ts"])] = float(row["close"])
            except (KeyError, TypeError, ValueError):
                continue
        closes[s] = cc
    return deltas, closes


def xsection_ic(deltas, closes, cs_idx, h):
    """deltas/closes pré-construits (une fois par période), cs_idx = {s: (sorted_ts, {ts:idx})}."""
    if len(deltas) < 5:
        return None
    all_ts = {}
    for s in deltas:
        for ts in deltas[s]:
            all_ts[ts] = all_ts.get(ts, 0) + 1
    ts_list = sorted(t for t, k in all_ts.items() if k >= 5)
    ics, longshort = [], []
    for ts in ts_list:
        sig, ret = [], []
        for s in deltas:
            if ts not in deltas[s] or s not in cs_idx:
                continue
            cs, idxmap = cs_idx[s]
            idx = idxmap.get(ts)
            if idx is None or idx + h >= len(cs):
                continue
            c0, ch = closes[s][cs[idx]], closes[s][cs[idx + h]]
            if c0 <= 0:
                continue
            sig.append(deltas[s][ts])
            ret.append(ch / c0 - 1.0)
        if len(sig) < 5:
            continue
        ic = spearman(sig, ret)
        if ic is not None:
            ics.append(ic)
            med = sorted(sig)[len(sig) // 2]
            ls = sum((1.0 if sig[i] > med else -1.0) * ret[i] for i in range(len(sig))) / len(sig)
            longshort.append(ls)
    if len(ics) < 8:
        return None
    n = len(ics)
    mean_ic = sum(ics) / n
    sd = math.sqrt(sum((x - mean_ic) ** 2 for x in ics) / (n - 1)) if n > 1 else 0.0
    t_ic = mean_ic / (sd / math.sqrt(n)) if sd > 0 else 0.0
    mean_ls_bps = (sum(longshort) / len(longshort)) * 1e4
    return {"n_slices": n, "n_symbols": len(deltas), "mean_IC": mean_ic, "t_IC": t_ic,
            "gross_ls_bps": mean_ls_bps}


def main():
    syms = liquid_symbols()
    print(f"=== IC TRANSVERSAL — Volume Delta — {len(syms)} symboles liquides ===")
    print(f"Frais aller-retour testés : maker 4bps · mixte 8bps · taker 12bps")
    print(f"Univers: {', '.join(syms[:15])}{'…' if len(syms) > 15 else ''}\n")
    findings = []
    for tp, gran in LADDER.items():
        deltas, closes = build_panel(syms, tp, gran)          # UNE fetch par période, réutilisée
        cs_idx = {}
        for s in closes:
            cs = sorted(closes[s])
            cs_idx[s] = (cs, {ts: i for i, ts in enumerate(cs)})
        for h in HORIZONS:
            try:
                r = xsection_ic(deltas, closes, cs_idx, h)
            except Exception as e:
                print(f"[{tp:4} h={h}] ERREUR {type(e).__name__}: {e}")
                continue
            if not r:
                print(f"[{tp:4} h={h}] données insuffisantes")
                continue
            nets = {k: r["gross_ls_bps"] - f for k, f in FEES.items()}
            sig = "★" if abs(r["t_IC"]) >= 2.0 else " "
            print(f"[{tp:4} h={h}]{sig} IC {r['mean_IC']:+.4f} (t={r['t_IC']:+.2f}, {r['n_slices']} tranches, "
                  f"{r['n_symbols']} sym) · brut {r['gross_ls_bps']:+.1f}bps -> "
                  f"maker {nets['maker_4']:+.1f} / mixte {nets['mixte_8']:+.1f} / taker {nets['taker_12']:+.1f}")
            findings.append((tp, h, r["mean_IC"], r["t_IC"], r["gross_ls_bps"], nets))
    print("\n=== SYNTHÈSE (honnête, t-stat déflaté par le nb d'essais) ===")
    if not findings:
        print("Aucune mesure exploitable.")
        return
    n_tests = len(findings)
    sig_ic = [f for f in findings if abs(f[3]) >= 2.0]
    # seuil déflaté Bonferroni-lite pour n essais : |t| >= ~ t tel que p*n < 0.05
    import math as _m
    t_defl = 2.0 + _m.log(max(n_tests, 1))  # heuristique conservatrice
    sig_defl = [f for f in findings if abs(f[3]) >= t_defl]
    net_pos_maker = [f for f in findings if f[5]["maker_4"] > 0]
    net_pos_mixte = [f for f in findings if f[5]["mixte_8"] > 0]
    best = max(findings, key=lambda f: abs(f[3]))
    print(f"Essais : {n_tests} · |t|>=2 : {len(sig_ic)} · |t|>={t_defl:.1f} (déflaté) : {len(sig_defl)}")
    print(f"Edge L/S net POSITIF : maker {len(net_pos_maker)}/{n_tests} · mixte {len(net_pos_mixte)}/{n_tests}")
    print(f"Meilleur |t| : {best[3]:+.2f} @ {best[0]} h={best[1]} · IC {best[2]:+.4f} · net mixte {best[5]['mixte_8']:+.1f}bps")
    if sig_defl and any(f[5]["mixte_8"] > 0 for f in sig_defl):
        print("VERDICT : signal CANDIDAT (t déflaté OK + net positif mixte) -> à re-mesurer sur plus de tranches.")
    elif sig_ic:
        print("VERDICT : traces (|t|>=2 brut) mais NON déflatées -> probable bruit multi-tests, à surveiller.")
    else:
        print("VERDICT : pas de signal transversal significatif à cette profondeur (30 tranches).")


if __name__ == "__main__":
    main()
