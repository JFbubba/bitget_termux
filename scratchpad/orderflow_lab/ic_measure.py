#!/usr/bin/env python3
"""ic_measure.py — Labo de MESURE de l'IC net de frais des signaux orderflow (§orderflow, mesure).

Discipline : MESURE seulement, aucun ordre, lecture seule. Constitution : banc GELÉ à 14 — rien
n'est branché sans preuve d'IC NETTE DE FRAIS ; ce labo produit justement cette preuve (ou son absence).

Ce qui est MESURABLE en backtest (a de l'historique) :
  - VOLUME DELTA / CVD FUTURES via `taker_flow` (endpoint à barres périodiques {5m..1day}).
    On mesure : IC (Spearman) signal→rendement forward, hit-rate, et EDGE NET de frais
    (E[sign(signal)·ret] − frais aller-retour) sur plusieurs horizons et toute l'échelle dispo.

Ce qui N'EST PAS backtestable (tape-only, pas d'historique) :
  - footprint, CVD spot-vs-futures, gros trades -> nécessitent une COLLECTE LIVE (cf. collect_live.py).

ERR-001 : l'échelle taker-buy-sell {5m,15m,30m,1h,4h,12h,1day} est la plus proche dispo de
M1·M5·M15·M30·H1·H4·D1·W1 ; M1 et W1 ne sont pas offerts par cet endpoint (noté honnêtement).
"""
import sys
sys.path.insert(0, "/root/bitget_termux_repo")
import math
import taker_flow
import technicals

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
# période taker -> granularité bougie Bitget (casse différente : 1h->1H, 1day->1D)
LADDER = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1H", "4h": "4H", "12h": "12H", "1day": "1D"}
HORIZONS = [1, 3, 6]
FEE_RT_BPS = {"taker": 12.0, "maker": 4.0}   # aller-retour futures (2 côtés) : taker ~6bps, maker ~2bps
LIMIT = 1000


def _rank(a):
    order = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def _pearson(x, y):
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    syy = sum((yi - my) ** 2 for yi in y)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def spearman(x, y):
    return _pearson(_rank(x), _rank(y))


def measure_period(symbol, taker_period, gran):
    bars = taker_flow.volume_delta_series(taker_flow.fetch(symbol, taker_period, limit=LIMIT) or [])
    cndl = technicals.fetch_candles(symbol, gran, limit=LIMIT) or []      # déjà [{ts, close, ...}]
    if len(bars) < 15 or len(cndl) < 15:
        return {"period": taker_period, "n_bars": len(bars), "n_candles": len(cndl), "skip": "données insuffisantes"}
    close_by_ts = {}
    for c in cndl:
        try:
            close_by_ts[int(c["ts"])] = float(c["close"])
        except (KeyError, TypeError, ValueError):
            continue
    ts_sorted = sorted(close_by_ts)
    idx_of = {ts: i for i, ts in enumerate(ts_sorted)}
    overlap = sum(1 for b in bars if b["ts"] in close_by_ts)
    out = {"period": taker_period, "n_bars": len(bars), "n_candles": len(cndl), "overlap": overlap, "horizons": {}}
    for h in HORIZONS:
        sig, ret = [], []
        for b in bars:
            ts = b["ts"]
            i = idx_of.get(ts)
            if i is None or i + h >= len(ts_sorted):
                continue
            c0 = close_by_ts[ts_sorted[i]]
            ch = close_by_ts[ts_sorted[i + h]]
            if c0 <= 0:
                continue
            sig.append(b["delta"])
            ret.append(ch / c0 - 1.0)
        if len(sig) < 15:
            out["horizons"][h] = {"n": len(sig), "skip": "trop peu de paires alignées"}
            continue
        ic = spearman(sig, ret)
        # edge net : espérance de trader dans le SENS du signe du delta, moins les frais
        gross = sum((1.0 if s > 0 else -1.0 if s < 0 else 0.0) * r for s, r in zip(sig, ret)) / len(sig)
        hit = sum(1 for s, r in zip(sig, ret) if (s > 0 and r > 0) or (s < 0 and r < 0)) / len(sig)
        out["horizons"][h] = {
            "n": len(sig),
            "IC_spearman": round(ic, 4),
            "hit_rate": round(hit, 3),
            "gross_edge_bps": round(gross * 1e4, 2),
            "net_edge_taker_bps": round(gross * 1e4 - FEE_RT_BPS["taker"], 2),
            "net_edge_maker_bps": round(gross * 1e4 - FEE_RT_BPS["maker"], 2),
        }
    return out


def main():
    print(f"=== LABO IC net de frais — Volume Delta/CVD futures — {SYMBOL} ===")
    print(f"Frais aller-retour : taker {FEE_RT_BPS['taker']}bps · maker {FEE_RT_BPS['maker']}bps\n")
    verdicts = []
    for tp, gran in LADDER.items():
        try:
            r = measure_period(SYMBOL, tp, gran)
        except Exception as e:
            print(f"[{tp}] ERREUR {type(e).__name__}: {e}")
            continue
        if r.get("skip"):
            print(f"[{tp:5}] SKIP ({r['skip']} — {r['n_bars']} barres / {r['n_candles']} bougies)")
            continue
        print(f"[{tp:5}] {r['n_bars']} barres · overlap {r.get('overlap')}")
        for h, hr in r["horizons"].items():
            if hr.get("skip"):
                print(f"        h={h}: {hr['skip']} (n={hr['n']})")
                continue
            print(f"        h={h:>1} (n={hr['n']:>3}) · IC {hr['IC_spearman']:+.4f} · hit {hr['hit_rate']:.3f}"
                  f" · edge brut {hr['gross_edge_bps']:+.2f}bps -> net taker {hr['net_edge_taker_bps']:+.2f}"
                  f" / maker {hr['net_edge_maker_bps']:+.2f}")
            verdicts.append((tp, h, hr["IC_spearman"], hr["net_edge_taker_bps"], hr["net_edge_maker_bps"]))
    # synthèse
    print("\n=== SYNTHÈSE ===")
    if not verdicts:
        print("Aucune mesure exploitable (données/alignement insuffisants).")
        return
    pos_net_maker = [v for v in verdicts if v[4] > 0]
    pos_net_taker = [v for v in verdicts if v[3] > 0]
    best = max(verdicts, key=lambda v: abs(v[2]))
    print(f"Combinaisons mesurées : {len(verdicts)}")
    print(f"Net POSITIF après frais maker : {len(pos_net_maker)} · après frais taker : {len(pos_net_taker)}")
    print(f"|IC| max : {best[2]:+.4f} @ {best[0]} h={best[1]} (net taker {best[3]:+.2f}bps / maker {best[4]:+.2f})")
    verdict = ("EDGE NET plausible (maker)" if pos_net_maker
               else "AUCUN edge net de frais — signal mangé par les frais (confirme le prior)")
    print(f"VERDICT : {verdict}")


if __name__ == "__main__":
    main()
