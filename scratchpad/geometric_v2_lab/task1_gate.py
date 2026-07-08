"""TÂCHE 1 — TEST EN GATE. Les features géométriques étant direction-agnostiques,
on ne les fait PAS voter : on teste si elles MODULENT utilement un signal
directionnel. Méthode : conditionnement par TERCILE du gate, IC directionnel du
signal de base DANS chaque tercile, walk-forward purgé, t inter-plis de l'écart
IC(tercile fort) − IC(tercile faible). Si l'edge se concentre dans un tercile de
régime -> le gate ajoute de la valeur.

Signaux de base : geom_vote (agent), rev8 (réversion −z(8)).
Gates : w1_drift, nolds_dfa, rvol (benchmark = vol réalisée simple).
TFs tradables : 5m,15m,30m,1H,4H. LECTURE SEULE. Aucun ordre.
"""
import json
import time
import numpy as np

import gate_lib as gl

PLAN = [("5m", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 2),
        ("15m", ["BTCUSDT", "ETHUSDT"], 3),
        ("30m", ["BTCUSDT", "ETHUSDT"], 2),
        ("1H", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 3),
        ("4H", ["BTCUSDT", "ETHUSDT"], 1)]
BASES = ["geom_vote", "rev8"]
GATES = ["w1_drift", "nolds_dfa", "rvol"]
HZ = (1, 4)


def gated_eval(grid, base, gate, fwd, h):
    """Par pli : IC directionnel du base dans tercile bas/haut du gate + IC 'gated'
    (base annulé hors tercile favorable, favorable choisi sur signe train)."""
    m = np.isfinite(base) & np.isfinite(gate) & np.isfinite(fwd)
    gi, b, g, f = grid[m], base[m], gate[m], fwd[m]
    if len(gi) < 200:
        return None
    folds = gl.purged_folds(gi, h)
    d_hi, d_lo, d_diff, ic_base, ic_gated = [], [], [], [], []
    for keep in folds:
        if len(keep) < 60:
            continue
        bb, gg, ff = b[keep], g[keep], f[keep]
        q1, q2 = np.quantile(gg, [1 / 3, 2 / 3])
        lo = gg <= q1; hi = gg >= q2
        if lo.sum() < 20 or hi.sum() < 20:
            continue
        ic_lo = gl.ic_rank(bb[lo], ff[lo])
        ic_hi = gl.ic_rank(bb[hi], ff[hi])
        ic_all = gl.ic_rank(bb, ff)
        if not (np.isfinite(ic_lo) and np.isfinite(ic_hi) and np.isfinite(ic_all)):
            continue
        d_hi.append(ic_hi); d_lo.append(ic_lo); d_diff.append(ic_hi - ic_lo)
        # signal gated : garder le base seulement dans le tercile où |IC| est plus fort
        fav_hi = abs(ic_hi) >= abs(ic_lo)
        sig = np.where(hi if fav_hi else lo, bb, 0.0)
        ic_gated.append(gl.ic_rank(sig, ff)); ic_base.append(ic_all)
    if len(d_diff) < 4:
        return None
    mdiff, tdiff, _ = gl.t_across_folds(d_diff)
    mgat, _, _ = gl.t_across_folds(ic_gated)
    mbas, _, _ = gl.t_across_folds(ic_base)
    _, thi, _ = gl.t_across_folds(d_hi)
    _, tlo, _ = gl.t_across_folds(d_lo)
    return {"ic_hi": round(float(np.mean(d_hi)), 4), "t_hi": round(thi, 2),
            "ic_lo": round(float(np.mean(d_lo)), 4), "t_lo": round(tlo, 2),
            "diff_hi_lo": round(mdiff, 4), "t_diff": round(tdiff, 2),
            "ic_base": round(mbas, 4), "ic_gated": round(mgat, 4),
            "gain_gated": round(mgat - mbas, 4), "n_folds": len(d_diff)}


def run():
    out = {}
    print("== TÂCHE 1 : GATE (tercile-conditionnel) ==", flush=True)
    print(f"{'TF':<4}{'sym':<9}{'base':<10}{'gate':<11}{'h':<3}"
          f"{'IC_bas':>8}{'IC_haut':>8}{'diff':>8}{'t_diff':>8}"
          f"{'IC_base':>9}{'IC_gated':>10}{'gain':>8}", flush=True)
    for gran, syms, stride in PLAN:
        for sym in syms:
            t0 = time.time()
            r = gl.build_features(sym, gran, stride=stride,
                                  want=("geom_vote", "w1_drift", "nolds_dfa", "rvol", "rev8"))
            if r is None:
                continue
            grid, F, FWD, K, depth = r
            for base in BASES:
                for gate in GATES:
                    for h in HZ:
                        res = gated_eval(grid.astype(float), F[base], F[gate], FWD[h], h)
                        if res:
                            out[f"{gran}|{sym}|{base}|{gate}|h{h}"] = res
                            if abs(res["t_diff"]) >= 2 or abs(res["gain_gated"]) >= 0.01:
                                print(f"{gran:<4}{sym:<9}{base:<10}{gate:<11}{h:<3}"
                                      f"{res['ic_lo']:>+8.3f}{res['ic_hi']:>+8.3f}"
                                      f"{res['diff_hi_lo']:>+8.3f}{res['t_diff']:>+8.2f}"
                                      f"{res['ic_base']:>+9.3f}{res['ic_gated']:>+10.3f}"
                                      f"{res['gain_gated']:>+8.3f}", flush=True)
            print(f"  [{gran} {sym} fait en {time.time()-t0:.0f}s, K_dfa={K}]", flush=True)
            gl.Path(gl.LAB / "task1_gate.json").write_text(json.dumps(out, indent=1))
    # bilan : gates qui concentrent l'edge de façon cohérente
    print("\n-- gates avec |t_diff|>=3 (edge concentré par régime) --", flush=True)
    for k, v in out.items():
        if abs(v["t_diff"]) >= 3:
            print(f"  {k}: diff {v['diff_hi_lo']:+.3f} t {v['t_diff']:+.2f} "
                  f"| gain_gated {v['gain_gated']:+.3f}", flush=True)
    print("TÂCHE1_TERMINÉE", flush=True)


if __name__ == "__main__":
    run()
