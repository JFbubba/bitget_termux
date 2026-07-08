"""TÂCHE 3 — REPLAY PROFOND 6 ANS (§79-style) du meilleur candidat RÉGIME/VOL.
Le signal vol récent tient-il sur 5,7 ans, et AJOUTE-t-il à un prédicteur trivial
(vol réalisée) ? + valeur ÉCONOMIQUE (vol-targeting).

Données : 1H BTC/ETH/SOL/XRP, historique complet (~5,7 ans). Purged WF 8 plis.
(1) vol-IC de w1_drift / rvol(bench) / nolds_dfa vs |rendement fwd|, par pli, t.
(2) VALEUR INCRÉMENTALE : IC de w1_drift vs le RÉSIDU de |fwd| après régression sur
    rvol (w1_drift bat-il la vol réalisée triviale ?).
(3) ÉCONOMIE : Sharpe d'une stratégie de base sign(rev8)·ret dimensionnée par
    1/vol_prédite (w1_drift vs rvol vs plat), par pli.
LECTURE SEULE. Aucun ordre. Toujours mono-thread, nice.
"""
import json
import math
import time
import numpy as np

import gate_lib as gl
import features_v2 as fv

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
GRAN = "1H"
HZ = (1, 4, 24)
N_FOLDS = 8
W = 160
STRIDE = 4


def build(sym):
    ts, cl = gl.load_series(sym, GRAN)
    n = len(cl)
    if n < 2 * W + 200:
        return None
    lr = gl.logret(cl)
    grid = np.arange(2 * W, n - max(HZ), STRIDE)
    K = max(1, math.ceil(len(grid) / 2500))
    w1 = np.full(len(grid), np.nan); rvol = np.full(len(grid), np.nan)
    dfa = np.full(len(grid), np.nan); rev8 = np.full(len(grid), np.nan)
    fwd = {h: np.full(len(grid), np.nan) for h in HZ}
    afwd = {h: np.full(len(grid), np.nan) for h in HZ}
    for gi, t in enumerate(grid):
        cur = lr[t - W:t]; prev = lr[t - 2 * W:t - W]
        w1[gi] = fv.w1_drift(prev, cur)
        sd = float(cur.std()); rvol[gi] = sd
        rev8[gi] = -math.tanh(float(cur[-8:].sum()) / (sd * math.sqrt(8) + 1e-9) / 2.0) if sd > 0 else 0.0
        if gi % K == 0:
            dfa[gi] = fv.nolds_dfa(cur)
        for h in HZ:
            fwd[h][gi] = math.log(cl[t + h] / cl[t]); afwd[h][gi] = abs(fwd[h][gi])
    return grid, dict(w1=w1, rvol=rvol, dfa=dfa, rev8=rev8), fwd, afwd, K, (ts[0], ts[-1], n)


def sharpe(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std() + 1e-12) * math.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def run():
    out = {}
    print("== TÂCHE 3 : REPLAY PROFOND 6 ANS (1H) ==", flush=True)
    for sym in SYMS:
        t0 = time.time()
        r = build(sym)
        if r is None:
            print(f"  {sym}: insuffisant", flush=True)
            continue
        grid, F, fwd, afwd, K, depth = r
        import datetime
        utc = datetime.timezone.utc
        d0 = datetime.datetime.fromtimestamp(depth[0] / 1000, utc).date()
        d1 = datetime.datetime.fromtimestamp(depth[1] / 1000, utc).date()
        print(f"\n-- {sym} : {depth[2]} barres {d0}->{d1}, {len(grid)} pts, K_dfa={K}, "
              f"{time.time()-t0:.0f}s --", flush=True)
        sym_out = {"depth": [str(d0), str(d1), int(depth[2])]}
        # (1) vol-IC par feature/horizon
        for h in HZ:
            for feat in ("w1", "rvol", "dfa"):
                x = F[feat]; y = afwd[h]
                m = np.isfinite(x) & np.isfinite(y)
                gi2 = grid[m].astype(float)
                if len(gi2) < 200:
                    continue
                ics = [gl.ic_rank(x[m][k], y[m][k]) for k in gl.purged_folds(gi2, h, N_FOLDS)
                       if len(k) >= 40]
                ics = [i for i in ics if np.isfinite(i)]
                if len(ics) >= 5:
                    mm, tt, nf = gl.t_across_folds(ics)
                    sym_out[f"volic_{feat}_h{h}"] = {"ic": round(mm, 4), "t": round(tt, 2), "nf": nf}
            # (2) valeur incrémentale w1 au-delà de rvol : résidu de |fwd| ~ rvol
            x1, xr, y = F["w1"], F["rvol"], afwd[h]
            m = np.isfinite(x1) & np.isfinite(xr) & np.isfinite(y)
            gi2 = grid[m].astype(float); a, rv, yy = x1[m], xr[m], y[m]
            incr = []
            for k in gl.purged_folds(gi2, h, N_FOLDS):
                if len(k) < 60:
                    continue
                # résidu OOS-ish : régression rang de yy sur rv dans le pli, IC de a vs résidu
                ry = np.argsort(np.argsort(yy[k])).astype(float)
                rr = np.argsort(np.argsort(rv[k])).astype(float)
                b = np.polyfit(rr, ry, 1)
                resid = ry - np.polyval(b, rr)
                ic = gl.ic_rank(a[k], resid)
                if np.isfinite(ic):
                    incr.append(ic)
            if len(incr) >= 5:
                mm, tt, nf = gl.t_across_folds(incr)
                sym_out[f"incr_w1_over_rvol_h{h}"] = {"ic": round(mm, 4), "t": round(tt, 2), "nf": nf}
        # (3) économie : vol-targeting Sharpe sur sign(rev8), h=1
        h = 1
        x1, xr, sg, ret = F["w1"], F["rvol"], np.sign(F["rev8"]), fwd[h]
        m = np.isfinite(x1) & np.isfinite(xr) & np.isfinite(ret) & (sg != 0)
        gi2 = grid[m].astype(float); a, rv, s, rr = x1[m], xr[m], sg[m], ret[m]
        sh_flat, sh_w1, sh_rv = [], [], []
        for k in gl.purged_folds(gi2, h, N_FOLDS):
            if len(k) < 80:
                continue
            base = s[k] * rr[k]
            pv_w1 = np.clip(a[k], np.quantile(a[k], .05), None)
            pv_rv = np.clip(rv[k], np.quantile(rv[k], .05), None)
            tgt = np.median(pv_w1)
            sh_flat.append(sharpe(base))
            sh_w1.append(sharpe(base * (tgt / pv_w1)))
            sh_rv.append(sharpe(base * (np.median(pv_rv) / pv_rv)))
        if len(sh_flat) >= 5:
            sym_out["econ_sharpe"] = {
                "flat": round(float(np.mean(sh_flat)), 3),
                "vt_w1": round(float(np.mean(sh_w1)), 3),
                "vt_rvol": round(float(np.mean(sh_rv)), 3),
                "t_w1_vs_flat": round(gl.t_across_folds(np.array(sh_w1) - np.array(sh_flat))[1], 2),
                "t_w1_vs_rvol": round(gl.t_across_folds(np.array(sh_w1) - np.array(sh_rv))[1], 2),
                "nf": len(sh_flat)}
        out[sym] = sym_out
        for k2, v in sym_out.items():
            if isinstance(v, dict) and "t" in v:
                print(f"    {k2:<28} ic {v['ic']:+.4f}  t {v['t']:+.2f}  (plis {v['nf']})", flush=True)
        if "econ_sharpe" in sym_out:
            e = sym_out["econ_sharpe"]
            print(f"    econ Sharpe: flat {e['flat']:+.2f} | vt_w1 {e['vt_w1']:+.2f} "
                  f"(t vs flat {e['t_w1_vs_flat']:+.2f}, t vs rvol {e['t_w1_vs_rvol']:+.2f}) | "
                  f"vt_rvol {e['vt_rvol']:+.2f}", flush=True)
        gl.Path(gl.LAB / "task3_deepreplay.json").write_text(json.dumps(out, indent=1))
    print("TÂCHE3_TERMINÉE", flush=True)


if __name__ == "__main__":
    run()
