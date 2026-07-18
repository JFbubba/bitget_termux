"""Backlog #9 : mesurer les signaux TradingView causaux au §72 — SuperTrend,
Vortex (VI+ - VI-), Chaikin Money Flow — en IC directionnel vs rendement forward.
Barre : |t|>=3 cohérent plis ET TFs. LECTURE SEULE, réutilise les bougies OHLCV.
"""
import math
import sys
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(LAB.parents[1]))
import gate_lib as gl          # noqa: E402
import candles_history as ch   # noqa: E402
from scipy.stats import spearmanr  # noqa: E402


def load_ohlcv(sym, gran):
    rows = ch.load(sym, gran)
    a = np.array([[r[1], r[2], r[3], r[4], r[5]] for r in rows if len(r) >= 6], float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]   # o,h,l,c,v


def atr(h, l, c, n=14):
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.full(len(c), np.nan)
    if len(tr) >= n:
        a = np.convolve(tr, np.ones(n) / n, mode="valid")
        out[n:] = a[:len(c) - n]
    return out


def supertrend_dist(o, h, l, c, p=10, mult=3.0):
    """État SuperTrend et distance normalisée (close-ST)/ATR, causal. Retourne array."""
    a = atr(h, l, c, p)
    hl2 = (h + l) / 2.0
    up = hl2 - mult * a; dn = hl2 + mult * a
    st = np.full(len(c), np.nan); state = np.full(len(c), np.nan)
    cur_up, cur_dn, cur_state = -np.inf, np.inf, 1
    for i in range(len(c)):
        if np.isnan(a[i]):
            continue
        cur_up = max(up[i], cur_up) if c[i - 1] > cur_up else up[i]
        cur_dn = min(dn[i], cur_dn) if c[i - 1] < cur_dn else dn[i]
        if c[i] > cur_dn:
            cur_state = 1
        elif c[i] < cur_up:
            cur_state = -1
        st[i] = cur_up if cur_state == 1 else cur_dn
        state[i] = cur_state
    dist = (c - st) / (a + 1e-12)
    return dist   # feature continue (signe = état, magnitude = éloignement)


def vortex(h, l, c, n=14):
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    vmp = np.abs(h[1:] - l[:-1]); vmm = np.abs(l[1:] - h[:-1])
    out = np.full(len(c), np.nan)
    for i in range(n, len(tr) + 1):
        s = tr[i - n:i].sum()
        if s > 1e-12:
            out[i] = vmp[i - n:i].sum() / s - vmm[i - n:i].sum() / s
    return out


def cmf(h, l, c, v, n=20):
    rng = (h - l)
    mfm = np.where(rng > 1e-12, ((c - l) - (h - c)) / rng, 0.0)
    mfv = mfm * v
    out = np.full(len(c), np.nan)
    for i in range(n, len(c) + 1):
        sv = v[i - n:i].sum()
        if sv > 1e-12:
            out[i - 1] = mfv[i - n:i].sum() / sv
    return out


PLAN = [("5m", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 2),
        ("15m", ["BTCUSDT", "ETHUSDT"], 3),
        ("1H", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 4),
        ("4H", ["BTCUSDT", "ETHUSDT"], 1),
        ("1D", ["BTCUSDT", "ETHUSDT", "XRPUSDT"], 1)]
HZ = (1, 4)


def ic_folds(gi, x, fwd, h):
    m = np.isfinite(x) & np.isfinite(fwd)
    g, xx, ff = gi[m], x[m], fwd[m]
    if len(g) < 200:
        return None
    ics = []
    for keep in gl.purged_folds(g, h):
        if len(keep) < 40 or xx[keep].std() < 1e-12:
            continue
        ic = spearmanr(xx[keep], ff[keep]).statistic
        if np.isfinite(ic):
            ics.append(float(ic))
    if len(ics) < 4:
        return None
    m_, t_, nf = gl.t_across_folds(ics)
    return round(m_, 4), round(t_, 2), nf


def main():
    print("== Backlog #9 : SuperTrend / Vortex / CMF au §72 (IC rang vs forward) ==")
    print(f"{'TF':<5}{'sym':<9}{'feat':<11}{'h':<3}{'IC_rang':>9}{'t':>7}{'nf':>4}")
    tallies = {}
    for gran, syms, stride in PLAN:
        for sym in syms:
            try:
                o, h, l, c, v = load_ohlcv(sym, gran)
            except Exception:
                continue
            if len(c) < 400:
                continue
            feats = {"supertrend": supertrend_dist(o, h, l, c),
                     "vortex": vortex(h, l, c),
                     "cmf": cmf(h, l, c, v)}
            n = len(c)
            grid = np.arange(60, n - max(HZ), stride)
            fwd = {hh: np.array([math.log(c[t + hh] / c[t]) for t in grid]) for hh in HZ}
            for fname, arr in feats.items():
                fv = arr[grid]
                for hh in HZ:
                    r = ic_folds(grid.astype(float), fv, fwd[hh], hh)
                    if r:
                        ic, t, nf = r
                        key = fname
                        tallies.setdefault(key, []).append(t)
                        if abs(t) >= 3:
                            print(f"{gran:<5}{sym:<9}{fname:<11}{hh:<3}{ic:>+9.4f}{t:>+7.2f}{nf:>4}  <==")
    print("\n-- synthèse par feature (cohérence) --")
    for f, ts in sorted(tallies.items()):
        ts = np.array(ts)
        strong = int((np.abs(ts) >= 3).sum())
        pos = int((ts >= 3).sum()); neg = int((ts <= -3).sum())
        print(f"  {f:<11}: {strong}/{len(ts)} cellules |t|>=3  (t>+3:{pos}  t<-3:{neg})  "
              f"médiane t {np.median(ts):+.2f}")
    print("\nBarre : candidat seulement si |t|>=3 cohérent en SIGNE sur plis ET plusieurs TFs.")


if __name__ == "__main__":
    main()
