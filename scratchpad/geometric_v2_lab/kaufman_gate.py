"""Point #7 du backlog : le GATE d'efficience de tendance (Kaufman Efficiency Ratio)
concentre-t-il l'edge d'un signal momentum ? Thème convergent de toutes les sources
(BuildAlpha 200-SMA, BlackBull MTF, TradingView Kaufman ER). Ma Tâche 1 a montré que
gater sur la VOL/dérive géométrique ne sert à rien ; ici on gate sur une variable
DIFFÉRENTE — l'efficience directionnelle ER — non testée.

ER = |close - close[n]| / somme(|close[i]-close[i-1]|)  ∈ [0,1]  (causal, pur).
ER haut = tendance efficiente ; ER bas = chop. Hypothèse : un signal MOMENTUM
(mom8 = tanh(somme 8 barres)) a un IC directionnel plus fort quand ER est haut.

Mesure : IC directionnel du momentum DANS le tercile ER-haut vs ER-bas, walk-forward
purgé, t inter-plis de l'écart. Échelle multi-TF (5m/15m/1H/4H) + multi-symboles.
LECTURE SEULE. Réutilise gate_lib (déjà écrit).
"""
import math
import sys
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
import gate_lib as gl  # noqa: E402


def er_kaufman(closes, n):
    """Efficiency Ratio causal sur une fenêtre finissant à l'indice courant."""
    c = np.asarray(closes, float)
    if len(c) < n + 1:
        return np.nan
    direction = abs(c[-1] - c[-1 - n])
    volatility = np.sum(np.abs(np.diff(c[-1 - n:])))
    return direction / volatility if volatility > 1e-12 else np.nan


PLAN = [("5m", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 2),
        ("15m", ["BTCUSDT", "ETHUSDT"], 3),
        ("1H", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 4),
        ("4H", ["BTCUSDT", "ETHUSDT"], 1)]
W = 160
ER_N = 10
HZ = (1, 4)


def build(sym, gran, stride):
    ts, cl = gl.load_series(sym, gran)
    n = len(cl)
    if n < 2 * W + 60:
        return None
    lr = gl.logret(cl)
    grid = np.arange(2 * W, n - max(HZ), stride)
    er = np.full(len(grid), np.nan)
    mom8 = np.full(len(grid), np.nan)
    fwd = {h: np.full(len(grid), np.nan) for h in HZ}
    for gi, t in enumerate(grid):
        er[gi] = er_kaufman(cl[t - ER_N - 1:t + 1], ER_N)     # ER sur les 10 dernières barres closes
        cur = lr[t - W:t]; sd = cur.std()
        mom8[gi] = math.tanh(float(cur[-8:].sum()) / (sd * math.sqrt(8) + 1e-9) / 2.0) if sd > 0 else 0.0
        for h in HZ:
            fwd[h][gi] = math.log(cl[t + h] / cl[t])
    return grid, er, mom8, fwd


def gated_ic(grid, er, mom, fwd, h):
    m = np.isfinite(er) & np.isfinite(mom) & np.isfinite(fwd)
    gi, e, mm, f = grid[m], er[m], mom[m], fwd[m]
    if len(gi) < 200:
        return None
    d_hi, d_lo, d_diff = [], [], []
    for keep in gl.purged_folds(gi, h):
        if len(keep) < 60:
            continue
        ee, mo, ff = e[keep], mm[keep], f[keep]
        q1, q2 = np.quantile(ee, [1 / 3, 2 / 3])
        lo, hi = ee <= q1, ee >= q2
        if lo.sum() < 20 or hi.sum() < 20:
            continue
        ic_hi = gl.ic_rank(mo[hi], ff[hi]); ic_lo = gl.ic_rank(mo[lo], ff[lo])
        if np.isfinite(ic_hi) and np.isfinite(ic_lo):
            d_hi.append(ic_hi); d_lo.append(ic_lo); d_diff.append(ic_hi - ic_lo)
    if len(d_diff) < 4:
        return None
    mdiff, tdiff, nf = gl.t_across_folds(d_diff)
    return {"ic_mom_ERhaut": round(float(np.mean(d_hi)), 4),
            "ic_mom_ERbas": round(float(np.mean(d_lo)), 4),
            "diff": round(mdiff, 4), "t_diff": round(tdiff, 2), "nf": nf}


def main():
    print("== GATE Kaufman ER sur momentum 8-barres (edge concentré par efficience ?) ==")
    print(f"{'TF':<5}{'sym':<9}{'h':<3}{'IC_mom|ERbas':>13}{'IC_mom|ERhaut':>14}{'diff':>9}{'t_diff':>8}")
    strong = 0; tot = 0
    for gran, syms, stride in PLAN:
        for sym in syms:
            r = build(sym, gran, stride)
            if r is None:
                continue
            grid, er, mom, fwd = r
            for h in HZ:
                res = gated_ic(grid.astype(float), er, mom, fwd[h], h)
                if res:
                    tot += 1
                    flag = "  <==" if abs(res["t_diff"]) >= 3 else ""
                    if abs(res["t_diff"]) >= 3:
                        strong += 1
                    print(f"{gran:<5}{sym:<9}{h:<3}{res['ic_mom_ERbas']:>+13.4f}"
                          f"{res['ic_mom_ERhaut']:>+14.4f}{res['diff']:>+9.4f}{res['t_diff']:>+8.2f}{flag}")
    print(f"\ncellules |t_diff|>=3 : {strong}/{tot}")
    print("Lecture : si IC_mom|ERhaut >> IC_mom|ERbas de façon cohérente (|t|>=3 sur plis"
          " ET TFs), le gate ER concentre l'edge momentum -> CANDIDAT. Sinon, comme la"
          " Tâche 1, le gate n'ajoute rien.")


if __name__ == "__main__":
    main()
