"""TÂCHE 2 — CROSS-TF À CALENDRIER FIXÉ. Lève l'ambiguïté : le flip de signe de
w1_drift à 15m (canal vol) était-il un effet TF réel, ou un artefact de calendrier
(15m ne couvrait que 13 mois vs 1m=55j vs 1D=6ans) ? On mesure l'IC vol
(feature vs |rendement forward|) à plusieurs TFs SUR LA MÊME FENÊTRE calendaire.

Deux bandes :
  A (profonde) : 1H,4H,1D sur l'intersection calendaire BTC/ETH (~2021-2026) ;
  B (probe du flip 15m) : 15m,30m,1H sur l'intersection (~2025-06 -> 2026-07).
Features : w1_drift, nolds_dfa (per-symbole) ; dcor, pearson (BTC↔ETH).
LECTURE SEULE. Aucun ordre.
"""
import json
import math
import time
import numpy as np

import gate_lib as gl
import features_v2 as fv

BANDS = {"A_profonde": (["1H", "4H", "1D"]),
         "B_probe15m": (["15m", "30m", "1H"])}
HZ = (1, 4)


def common_calendar(gran_list, syms=("BTCUSDT", "ETHUSDT")):
    lo, hi = 0, 10 ** 20
    for g in gran_list:
        for s in syms:
            ts, cl = gl.load_series(s, g)
            if len(ts) < 100:
                return None
            lo = max(lo, ts[0]); hi = min(hi, ts[-1])
    return lo, hi


def vol_ic_feature(sym, gran, lo, hi, feat, w=160, stride=2):
    """IC rang (vs |fwd|) par pli d'une feature per-symbole, restreint à [lo,hi]."""
    ts, cl = gl.load_series(sym, gran)
    sel = (ts >= lo) & (ts <= hi)
    ts, cl = ts[sel], cl[sel]
    n = len(cl)
    if n < 2 * w + 80:
        return None
    lr = gl.logret(cl)
    grid = np.arange(2 * w, n - max(HZ), stride)
    K = max(1, math.ceil(len(grid) / 1500))
    vals = {h: [] for h in HZ}
    fv_arr = np.full(len(grid), np.nan)
    afwd = {h: np.full(len(grid), np.nan) for h in HZ}
    for gi, t in enumerate(grid):
        cur = lr[t - w:t]; prev = lr[t - 2 * w:t - w]
        if feat == "w1_drift":
            fv_arr[gi] = fv.w1_drift(prev, cur)
        elif feat == "nolds_dfa":
            if gi % K == 0:
                fv_arr[gi] = fv.nolds_dfa(cur)
        for h in HZ:
            afwd[h][gi] = abs(math.log(cl[t + h] / cl[t]))
    res = {}
    for h in HZ:
        m = np.isfinite(fv_arr) & np.isfinite(afwd[h])
        gi2 = grid[m].astype(float); x = fv_arr[m]; y = afwd[h][m]
        if len(gi2) < 120:
            continue
        ics = []
        for keep in gl.purged_folds(gi2, h):
            if len(keep) < 40:
                continue
            ic = gl.ic_rank(x[keep], y[keep])
            if np.isfinite(ic):
                ics.append(ic)
        if len(ics) >= 4:
            m_, t_, _ = gl.t_across_folds(ics)
            res[f"h{h}"] = {"vol_ic": round(m_, 4), "t": round(t_, 2), "n_folds": len(ics),
                            "n": int(len(gi2))}
    return res


def vol_ic_corr(gran, lo, hi, kind, w=160, stride=2):
    """IC vol de corr(BTC,ETH) [dcor/pearson] vs |fwd BTC|, restreint à [lo,hi]."""
    tb, cb = gl.load_series("BTCUSDT", gran)
    te, ce = gl.load_series("ETHUSDT", gran)
    db = dict(zip(tb.tolist(), cb.tolist())); de = dict(zip(te.tolist(), ce.tolist()))
    common = sorted(set(db) & set(de))
    common = [t for t in common if lo <= t <= hi]
    if len(common) < 2 * w + 80:
        return None
    B = np.array([db[t] for t in common]); E = np.array([de[t] for t in common])
    rb = np.diff(np.log(B)); re = np.diff(np.log(E))
    n = len(rb)
    grid = np.arange(w, n - max(HZ), stride)
    fv_arr = np.full(len(grid), np.nan)
    afwd = {h: np.full(len(grid), np.nan) for h in HZ}
    for gi, t in enumerate(grid):
        wb, we = rb[t - w:t], re[t - w:t]
        if kind == "pearson":
            fv_arr[gi] = float(np.corrcoef(wb, we)[0, 1])
        else:
            fv_arr[gi] = fv.dcor_pair(wb, we)
        for h in HZ:
            afwd[h][gi] = abs(math.log(B[t + h] / B[t]))
    res = {}
    for h in HZ:
        m = np.isfinite(fv_arr) & np.isfinite(afwd[h])
        gi2 = grid[m].astype(float); x = fv_arr[m]; y = afwd[h][m]
        if len(gi2) < 120:
            continue
        ics = []
        for keep in gl.purged_folds(gi2, h):
            if len(keep) < 40:
                continue
            ic = gl.ic_rank(x[keep], y[keep])
            if np.isfinite(ic):
                ics.append(ic)
        if len(ics) >= 4:
            m_, t_, _ = gl.t_across_folds(ics)
            res[f"h{h}"] = {"vol_ic": round(m_, 4), "t": round(t_, 2), "n_folds": len(ics)}
    return res


def run():
    out = {}
    print("== TÂCHE 2 : CROSS-TF CALENDRIER FIXÉ (canal vol) ==", flush=True)
    for band, tfs in BANDS.items():
        cc = common_calendar(tfs)
        if not cc:
            continue
        lo, hi = cc
        import datetime
        utc = datetime.timezone.utc
        d0 = datetime.datetime.fromtimestamp(lo / 1000, utc).date()
        d1 = datetime.datetime.fromtimestamp(hi / 1000, utc).date()
        print(f"\n--- bande {band} : {tfs} sur {d0} -> {d1} ---", flush=True)
        out[band] = {"calendrier": [str(d0), str(d1)], "tfs": tfs, "res": {}}
        for feat in ("w1_drift", "nolds_dfa"):
            for gran in tfs:
                for sym in ("BTCUSDT", "ETHUSDT"):
                    t0 = time.time()
                    r = vol_ic_feature(sym, gran, lo, hi, feat)
                    if r:
                        for h, v in r.items():
                            out[band]["res"][f"{feat}|{sym}|{gran}|{h}"] = v
                            print(f"  {feat:<11}{sym:<9}{gran:<5}{h:<4}"
                                  f"vol_ic {v['vol_ic']:+.4f}  t {v['t']:+.2f}  "
                                  f"(n_plis {v['n_folds']}, {time.time()-t0:.0f}s)", flush=True)
        for kind in ("dcor", "pearson"):
            for gran in tfs:
                r = vol_ic_corr(gran, lo, hi, kind)
                if r:
                    for h, v in r.items():
                        out[band]["res"][f"corr_{kind}|BTCETH|{gran}|{h}"] = v
                        print(f"  corr_{kind:<6}BTCETH   {gran:<5}{h:<4}"
                              f"vol_ic {v['vol_ic']:+.4f}  t {v['t']:+.2f}", flush=True)
        gl.Path(gl.LAB / "task2_crosstf.json").write_text(json.dumps(out, indent=1))
    print("\n-- verdict sign-stabilité (par bande/feature, h1) --", flush=True)
    for band, d in out.items():
        for feat in ("w1_drift", "nolds_dfa", "corr_dcor", "corr_pearson"):
            sigs = [np.sign(v["vol_ic"]) for k, v in d["res"].items()
                    if k.startswith(feat) and k.endswith("h1")]
            if sigs:
                stable = len(set(sigs)) == 1
                print(f"  {band} {feat}: signes {sigs} -> "
                      f"{'STABLE' if stable else 'INSTABLE (flip)'}", flush=True)
    print("TÂCHE2_TERMINÉE", flush=True)


if __name__ == "__main__":
    run()
