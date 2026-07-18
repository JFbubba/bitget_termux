"""RE-ANALYSE (le propriétaire a raison, 2e fois) : un IC uniformément négatif à
h court = artefact de RÉVERSION crypto, pas « signaux nuls ». On décompose par
HORIZON (1/4/24/96 barres) et on monte en TF (jusqu'à D1/W1) pour voir où l'edge
BASCULE. Contrôle = 'mom' (rendement récent brut) : s'il bascule pareil, c'est bien
la réversion→momentum, pas un bug de signe.

Signaux : SuperTrend(dist), Vortex(VI+-VI-), CMF, + mom (contrôle). LECTURE SEULE.
"""
import math
import sys
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(LAB.parents[1]))
import gate_lib as gl                 # noqa: E402
from signals_72 import load_ohlcv, supertrend_dist, vortex, cmf  # noqa: E402
from scipy.stats import spearmanr     # noqa: E402

HZ = (1, 4, 24, 96)
PLAN = [("5m", ["BTCUSDT", "ETHUSDT"], 4),
        ("1H", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 4),
        ("4H", ["BTCUSDT", "ETHUSDT"], 1),
        ("1D", ["BTCUSDT", "ETHUSDT", "XRPUSDT"], 1)]


def mom_recent(c, n=8):
    """Rendement récent brut normalisé (contrôle de réversion→momentum)."""
    out = np.full(len(c), np.nan)
    lr = np.diff(np.log(c))
    for i in range(n + 1, len(c)):
        w = lr[i - n:i]; sd = w.std()
        out[i] = math.tanh(float(w.sum()) / (sd * math.sqrt(n) + 1e-9) / 2.0) if sd > 0 else 0.0
    return out


def ic_folds(gi, x, fwd, h):
    m = np.isfinite(x) & np.isfinite(fwd)
    g, xx, ff = gi[m], x[m], fwd[m]
    if len(g) < 150:
        return None
    ics = []
    for keep in gl.purged_folds(g, h):
        if len(keep) < 30 or xx[keep].std() < 1e-12:
            continue
        ic = spearmanr(xx[keep], ff[keep]).statistic
        if np.isfinite(ic):
            ics.append(float(ic))
    if len(ics) < 4:
        return None
    m_, t_, _ = gl.t_across_folds(ics)
    return round(m_, 4), round(t_, 2)


def main():
    print("== Structure par HORIZON : où l'edge bascule-t-il ? (IC rang, t inter-plis) ==")
    print("   (négatif = réversion ; positif = momentum/suivi de tendance)\n")
    # agrège par (feature, horizon) : signe dominant + moyenne t
    agg = {}
    for gran, syms, stride in PLAN:
        for sym in syms:
            try:
                o, h_, l, c, v = load_ohlcv(sym, gran)
            except Exception:
                continue
            if len(c) < 500:
                continue
            feats = {"supertrend": supertrend_dist(o, h_, l, c),
                     "vortex": vortex(h_, l, c), "cmf": cmf(h_, l, c, v),
                     "mom(ctrl)": mom_recent(c)}
            n = len(c)
            grid = np.arange(100, n - max(HZ), stride)
            for hh in HZ:
                fwd = np.array([math.log(c[t + hh] / c[t]) for t in grid])
                for fname, arr in feats.items():
                    r = ic_folds(grid.astype(float), arr[grid], fwd, hh)
                    if r:
                        agg.setdefault((fname, hh), []).append((r[0], r[1], f"{gran}:{sym}"))
    feats_order = ["mom(ctrl)", "supertrend", "vortex", "cmf"]
    print(f"{'feature':<12}" + "".join(f"h={hh:<3}          " for hh in HZ))
    for f in feats_order:
        row = f"{f:<12}"
        for hh in HZ:
            cells = agg.get((f, hh), [])
            if not cells:
                row += f"{'—':<14}"; continue
            ics = np.array([x[0] for x in cells]); ts = np.array([x[1] for x in cells])
            pos = int((ts >= 2).sum()); neg = int((ts <= -2).sum())
            row += f"{ics.mean():+.3f}(+{pos}/-{neg})  "
        print(row)
    print("\nLecture : pour CHAQUE feature, l'IC moyen par horizon + (nb TF/sym à t>=+2 / t<=-2).")
    print("Si négatif à h court PUIS positif à h long -> réversion→momentum (réel, pas bug).")
    print("Le contrôle 'mom' doit montrer le MÊME profil (preuve que c'est le régime, pas un signe inversé).")


if __name__ == "__main__":
    main()
