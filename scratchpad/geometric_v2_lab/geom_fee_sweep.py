"""
geom_fee_sweep.py — CRIBLE MAKER sur le modèle joint geometric_v2 (task 3, 18/07).

interaction_geom rejette geometric_v2 avec des frais TAKER (6 bps). On réutilise EXACTEMENT
son calcul de features + son WF purgé, mais on capture les prédictions OOS une seule fois et
on calcule le net à PLUSIEURS niveaux de frais (taker 6 -> maker 1-2 -> brut 0) + shuffle.
Réponse : le vecteur géométrique complet crée-t-il un edge net que le maker sauverait ?
Lecture seule. Réutilise interaction_geom (build_matrix) + gate_lib (folds).
"""
import numpy as np
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor

import interaction_geom as ig
import gate_lib as gl

FEES_BPS = [6.0, 2.0, 1.0, 0.0]


def wf_pred(grid, names, X, Y, h, shuffle=False):
    M = np.column_stack([X[k] for k in names]); y = Y[h]
    ok = np.all(np.isfinite(M), axis=1) & np.isfinite(y)
    M, y, g = M[ok], y[ok], grid[ok]
    if len(y) < 400:
        return None
    folds = gl.purged_folds(g, h)
    oos = np.full(len(y), np.nan); idx = np.arange(len(y))
    for test in folds:
        if len(test) < 40:
            continue
        tmask = np.zeros(len(y), bool); tmask[test] = True
        lo, hi = g[test].min() - h, g[test].max() + h
        train = idx[~tmask & ~((g >= lo) & (g <= hi))]
        if len(train) < 200:
            continue
        ytr = y[train].copy()
        if shuffle:
            ytr = np.random.default_rng(len(train)).permutation(ytr)
        rf = RandomForestRegressor(n_estimators=120, max_depth=5, min_samples_leaf=40,
                                   n_jobs=-1, random_state=0)
        oos[test] = rf.fit(M[train], ytr).predict(M[test])
    m = np.isfinite(oos)
    if m.sum() < 200:
        return None
    return oos[m], y[m]


def net_at(pred, fwd, fee):
    pos = np.sign(pred); dpos = np.abs(np.diff(np.concatenate([[0.0], pos])))
    return float((pos * fwd - fee / 1e4 * dpos).mean() * 1e4)


def main():
    print("CRIBLE MAKER — modèle joint geometric_v2 (WF purgé, net frais balayés, shuffle)\n", flush=True)
    hdr = (f"{'tf':<4}{'sym':<9}{'h':>3}{'IC_rf':>8}{'IC_shuf':>9}{'gross':>8}"
           + "".join(f"{'net@'+str(int(f)):>9}" for f in FEES_BPS))
    print(hdr); print("-" * len(hdr))
    rows = []
    for gran, syms, stride in ig.PLAN:
        for sym in syms:
            try:
                built = ig.build_matrix(sym, gran, stride)
            except Exception as e:
                print(f"  skip {sym} {gran}: {e}"); continue
            if not built:
                continue
            grid, names, X, Y = built
            for h in ig.HZ:
                pr = wf_pred(grid, names, X, Y, h)
                if pr is None:
                    continue
                pred, fwd = pr
                sh = wf_pred(grid, names, X, Y, h, shuffle=True)
                ic = float(spearmanr(pred, fwd).statistic)
                ic_sh = float(spearmanr(*sh).statistic) if sh else float("nan")
                gross = net_at(pred, fwd, 0.0)
                nets = {f: net_at(pred, fwd, f) for f in FEES_BPS}
                print(f"{gran:<4}{sym:<9}{h:>3}{ic:>8.4f}{ic_sh:>9.4f}{gross:>8.2f}"
                      + "".join(f"{nets[f]:>9.2f}" for f in FEES_BPS), flush=True)
                rows.append(dict(tf=gran, sym=sym, h=h, ic=round(ic, 4), ic_shuffle=round(ic_sh, 4),
                                 net={int(f): round(nets[f], 3) for f in FEES_BPS}))
    print("\n" + "=" * 92)
    if rows:
        strong = [r for r in rows if r["ic"] > r["ic_shuffle"] + 0.02
                  and (r["net"].get(1, -9) > 0 or r["net"].get(2, -9) > 0)]
        pos0 = np.mean([r["net"].get(0, -9) > 0 for r in rows]) * 100
        print(f"configs {len(rows)} · %gross>0 {pos0:.0f}% · "
              f"IC>shuffle+0.02 {np.mean([r['ic']>r['ic_shuffle']+0.02 for r in rows])*100:.0f}%")
        print(f"configs fortes (bat shuffle+0.02 ET net>0 à maker 1-2 bps) : {len(strong)}")
        for r in sorted(strong, key=lambda x: -(x['ic']-x['ic_shuffle'])):
            print(f"    {r['tf']:<3} {r['sym']:<9} h={r['h']} IC={r['ic']:+.4f} (shuf {r['ic_shuffle']:+.4f}) "
                  f"net@2={r['net'].get(2)} net@1={r['net'].get(1)} net@0={r['net'].get(0)}")
        if not strong:
            print("\nVERDICT : le vecteur géométrique joint ne franchit pas shuffle+frais MAKER — même")
            print("  la lentille maker ne révèle pas d'edge géométrique caché. Complétude + crible clos.")
        else:
            print("\nPISTE (maker) -> déflater + OOS neuf avant conclusion.")
        import json
        json.dump(rows, open("geom_fee_sweep_results.json", "w"), indent=0)
        print("-> geom_fee_sweep_results.json")
    print("=" * 92)


if __name__ == "__main__":
    main()
