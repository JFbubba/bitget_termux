"""Harnais de mesure « geometric v2 » — IC walk-forward à plis purgés.

Protocole (mission) :
  - fenêtre causale W=160 rendements (le live donne 160 closes à l'agent) ;
  - baseline = geometric_agent.signal(fenêtre)["vote"] rejoué aux MÊMES points ;
  - features v2 : POT (W1 gaussien, dérive de régime), dcor (BTC↔ETH + λ₂ de graphe
    re-pondéré dcor vs Pearson), nolds (DFA, R/S, SampEn, dim. de corrélation —
    SOUS-ÉCHANTILLONNÉS tous les K pas, K = ceil(n_grille/2000), coût oblige) ;
  - cibles : rendement log forward à h ∈ {1, 4, 24} pas (+ diagnostic |fwd| = vol) ;
  - 6 plis temporels contigus, purge = horizon en tête de pli, étiquettes NON
    CHEVAUCHANTES (espacement ≥ h barres, sélection gloutonne) ;
  - IC de RANG et PEARSON par pli (§96 : ils divergent souvent) ; t = moyenne des
    ICs de plis / erreur-type inter-plis ;
  - baseline recalculée sur le MASQUE de chaque feature (comparaison à échantillons
    égaux, indispensable pour les features nolds sous-échantillonnées).
ERR-001 : échelle complète 1m·5m·15m·30m·1H·4H·1D·1W, profondeurs annotées.
LECTURE SEULE : ne lit que data_history/, n'écrit que dans ce dossier. Aucun ordre.
"""
import json
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB.parents[1]))
sys.path.insert(0, str(LAB))

import candles_history as ch     # noqa: E402
import features_v2 as fv         # noqa: E402
import geometric_agent as ga     # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

W = 160                    # fenêtre de rendements
HORIZONS = (1, 4, 24)      # pas forward
N_FOLDS = 6
MIN_N_FOLD = 10            # IC calculé si n>=10 (n annoté ; D1 h=24 est peu peuplé)
NOLDS_TARGET = 2000        # évaluations nolds max par série (coût)

# (gran, symboles mesurés, stride grille, symboles du graphe multi-actifs)
ALL5M = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
         "BGBUSDT", "HYPEUSDT", "LABUSDT", "LITUSDT", "XAUTUSDT"]
PLAN = [
    ("1m",  ["BTCUSDT", "ETHUSDT"],                       4, ["BTCUSDT", "ETHUSDT"]),
    ("5m",  ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 2, ALL5M),
    ("15m", ["BTCUSDT", "ETHUSDT"],                       4, ["BTCUSDT", "ETHUSDT"]),
    ("30m", ["BTCUSDT", "ETHUSDT"],                       2, ["BTCUSDT", "ETHUSDT"]),
    ("1H",  ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 4,
     ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]),
    ("4H",  ["BTCUSDT", "ETHUSDT"],                       1, ["BTCUSDT", "ETHUSDT"]),
    ("1D",  ["BTCUSDT", "ETHUSDT", "XRPUSDT"],            1,
     ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]),
    ("1W",  ["BTCUSDT", "ETHUSDT"],                       1, ["BTCUSDT", "ETHUSDT"]),
]
W_PAR_TF = {"1W": 64}      # W1 : ~300 bougies seulement -> fenêtre réduite (ANNOTÉ)


def load_series(sym, gran):
    rows = ch.load(sym, gran)
    ts = np.array([r[0] for r in rows], dtype=np.int64)
    cl = np.array([r[4] for r in rows], dtype=float)
    ok = cl > 0
    return ts[ok], cl[ok]


# ---------- features marché (multi-actifs), calculées au stride 1 ----------

def market_features(gran, graph_syms, w):
    data = {}
    for s in graph_syms:
        ts, cl = load_series(s, gran)
        if len(cl) > w + 30:
            data[s] = dict(zip(ts.tolist(), cl.tolist()))
    syms = [s for s in ("BTCUSDT", "ETHUSDT") if s in data] + \
           [s for s in data if s not in ("BTCUSDT", "ETHUSDT")]
    if "BTCUSDT" not in data or "ETHUSDT" not in data:
        return {}, []
    common = set.intersection(*[set(d.keys()) for d in data.values()])
    ts_c = np.array(sorted(common), dtype=np.int64)
    if len(ts_c) < w + 30:
        return {}, []
    C = np.array([[data[s][t] for s in syms] for t in ts_c.tolist()], dtype=float)
    R = np.diff(np.log(C), axis=0)            # R[i] = rendement ts[i] -> ts[i+1]
    n_sym = len(syms)
    i_btc, i_eth = syms.index("BTCUSDT"), syms.index("ETHUSDT")
    out = {}
    t0 = time.time()
    for t in range(w, R.shape[0] + 1):        # feature à la close ts_c[t]
        win = R[t - w:t]
        b, e = win[:, i_btc], win[:, i_eth]
        p = float(np.corrcoef(b, e)[0, 1])
        d = fv.dcor_pair(b, e)
        f = {"pearson_btc_eth": p, "dcor_btc_eth": d,
             "dcor_excess_btc_eth": (d - abs(p)) if np.isfinite(d) else np.nan}
        if n_sym >= 3:
            l2p = fv.lambda2_pearson_graph(win)
            l2d = fv.lambda2_dcor_graph(win)
            f["lambda2_pearson"] = l2p
            f["lambda2_dcor"] = l2d
            f["d_lambda2_dcor_pearson"] = (l2d - l2p) if (np.isfinite(l2d) and np.isfinite(l2p)) else np.nan
            f["lambda2_agent_rmt"] = ga.correlation_graph_metrics(win)["lambda2"]
        out[int(ts_c[t])] = f
    print(f"    marché {gran}: {len(out)} pts ({n_sym} sym) en {time.time()-t0:.0f}s", flush=True)
    return out, syms


# ---------- IC par plis purgés ----------

def fold_ics(bar_idx, feat, base, fwd, h, n_folds=N_FOLDS):
    """ICs par pli (rang+pearson) de feat ET de la baseline sur le MÊME masque,
    étiquettes non chevauchantes (espacement ≥ h barres), purge h en tête de pli."""
    m = np.isfinite(feat) & np.isfinite(fwd) & np.isfinite(base)
    if m.sum() < 60:
        return None
    bi, fe, ba, fw = bar_idx[m], feat[m], base[m], fwd[m]
    afw = np.abs(fw)
    lo, hi = bi.min(), bi.max()
    bounds = [lo + (hi - lo) * k / n_folds for k in range(n_folds + 1)]
    folds = []
    for k in range(n_folds):
        s = (bi >= bounds[k] + h) & (bi < bounds[k + 1])   # purge h en tête
        idx = np.where(s)[0]
        keep, last = [], -10**9
        for i in idx:                                       # espacement >= h barres
            if bi[i] >= last + h:
                keep.append(i); last = bi[i]
        keep = np.array(keep, dtype=int)
        if len(keep) < MIN_N_FOLD:
            continue
        x, b2, y, ay = fe[keep], ba[keep], fw[keep], afw[keep]
        if x.std() < 1e-12 or y.std() < 1e-12:
            continue
        ic_r = float(spearmanr(x, y).statistic)
        ic_p = float(np.corrcoef(x, y)[0, 1])
        b_r = float(spearmanr(b2, y).statistic) if b2.std() > 1e-12 else 0.0
        b_p = float(np.corrcoef(b2, y)[0, 1]) if b2.std() > 1e-12 else 0.0
        v_r = float(spearmanr(x, ay).statistic) if ay.std() > 1e-12 else 0.0
        folds.append({"n": int(len(keep)), "ic_r": ic_r, "ic_p": ic_p,
                      "base_r": b_r, "base_p": b_p, "vol_r": v_r})
    if len(folds) < 4:
        return None

    def t_of(key):
        v = np.array([f[key] for f in folds])
        se = v.std(ddof=1) / math.sqrt(len(v))
        return float(v.mean()), (float(v.mean() / se) if se > 1e-12 else 0.0)

    mr, tr = t_of("ic_r"); mp, tp = t_of("ic_p")
    br, btr = t_of("base_r"); bp, btp = t_of("base_p")
    vr, vtr = t_of("vol_r")
    return {"folds": [{k: (round(v, 4) if isinstance(v, float) else v)
                       for k, v in f.items()} for f in folds],
            "n_tot": int(sum(f["n"] for f in folds)),
            "ic_r": round(mr, 4), "t_r": round(tr, 2),
            "ic_p": round(mp, 4), "t_p": round(tp, 2),
            "base_ic_r": round(br, 4), "base_t_r": round(btr, 2),
            "base_ic_p": round(bp, 4), "base_t_p": round(btp, 2),
            "vol_ic_r": round(vr, 4), "vol_t_r": round(vtr, 2)}


# ---------- boucle principale ----------

def run():
    results = {"meta": {"window_returns": W, "horizons": list(HORIZONS),
                        "n_folds": N_FOLDS, "nolds_target": NOLDS_TARGET,
                        "w_par_tf": W_PAR_TF, "depths": {}, "nolds_substride": {},
                        "strides": {}},
               "tables": {}}
    for gran, syms, stride, graph_syms in PLAN:
        w = W_PAR_TF.get(gran, W)
        print(f"== TF {gran} (W={w}, stride {stride}) ==", flush=True)
        mkt, mkt_syms = market_features(gran, graph_syms, w)
        results["meta"]["strides"][gran] = stride
        tf_tab = {}
        for sym in syms:
            ts, cl = load_series(sym, gran)
            n = len(cl)
            if n < w + 60:
                print(f"  {sym}: {n} bougies — INSUFFISANT", flush=True)
                continue
            import datetime
            utc = datetime.timezone.utc
            results["meta"]["depths"][f"{sym}_{gran}"] = {
                "n": int(n),
                "de": str(datetime.datetime.fromtimestamp(ts[0] / 1000, utc).date()),
                "a": str(datetime.datetime.fromtimestamp(ts[-1] / 1000, utc).date())}
            lr = np.diff(np.log(cl))                     # lr[i] = close i -> i+1
            maxh = max(HORIZONS)
            grid = np.arange(2 * w, n - maxh, stride)    # 2w : fenêtre précédente dispo
            K = max(1, math.ceil(len(grid) / NOLDS_TARGET))
            results["meta"]["nolds_substride"][f"{sym}_{gran}"] = K
            t0 = time.time()
            F = {k: np.full(len(grid), np.nan) for k in
                 ["geom_vote", "w1_gauss_pot", "w1_drift", "w1_drift_shape",
                  "nolds_dfa", "nolds_hurst_rs", "nolds_sampen", "nolds_corr_dim"]}
            mkeys = ["pearson_btc_eth", "dcor_btc_eth", "dcor_excess_btc_eth",
                     "lambda2_pearson", "lambda2_dcor", "d_lambda2_dcor_pearson",
                     "lambda2_agent_rmt"]
            for k in mkeys:
                F[k] = np.full(len(grid), np.nan)
            FWD = {h: np.full(len(grid), np.nan) for h in HORIZONS}
            for gi, t in enumerate(grid):
                cur = lr[t - w:t]
                prev = lr[t - 2 * w:t - w]
                F["geom_vote"][gi] = ga.signal(cl[t - w:t + 1].tolist())["vote"]
                F["w1_gauss_pot"][gi] = fv.w1_gauss_pot(cur)
                F["w1_drift"][gi] = fv.w1_drift(prev, cur)
                F["w1_drift_shape"][gi] = fv.w1_drift_shape(prev, cur)
                if gi % K == 0:
                    F["nolds_dfa"][gi] = fv.nolds_dfa(cur)
                    F["nolds_hurst_rs"][gi] = fv.nolds_hurst_rs(cur)
                    F["nolds_sampen"][gi] = fv.nolds_sampen(cur)
                    F["nolds_corr_dim"][gi] = fv.nolds_corr_dim(cur)
                mf = mkt.get(int(ts[t]))
                if mf:
                    for k in mkeys:
                        if k in mf:
                            F[k][gi] = mf[k]
                for h in HORIZONS:
                    FWD[h][gi] = math.log(cl[t + h] / cl[t])
            print(f"  {sym}: {len(grid)} pts (K_nolds={K}) en {time.time()-t0:.0f}s", flush=True)
            sym_tab = {}
            for feat_name, vals in F.items():
                per_h = {}
                for h in HORIZONS:
                    r = fold_ics(grid.astype(float), vals, F["geom_vote"], FWD[h], h)
                    if r:
                        per_h[f"h{h}"] = r
                if per_h:
                    sym_tab[feat_name] = per_h
            tf_tab[sym] = sym_tab
        results["tables"][gran] = tf_tab
        (LAB / "resultats.json").write_text(json.dumps(results, indent=1))
    try:
        cost = json.loads((LAB / "cost_bench.json").read_text())
        results["meta"]["cout_us_par_appel"] = cost
    except Exception:
        pass
    (LAB / "resultats.json").write_text(json.dumps(results, indent=1))
    print("TERMINE — resultats.json écrit", flush=True)


if __name__ == "__main__":
    run()
