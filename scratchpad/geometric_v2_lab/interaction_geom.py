"""
interaction_geom.py — RE-TEST de geometric_v2 en INTERACTION (méthode ERR-014).

Le rejet « 0/14 features » testait chaque feature géométrique ISOLÉMENT (IC de rang
individuel). La méthode corrigée exige de prendre TOUS les indicateurs ENSEMBLE et de
tester si leur INTERACTION crée un signal. On construit donc le VECTEUR complet de
features (Wasserstein/POT + nolds complexité + geom_vote + corrélations cross-asset +
vol) et on teste un MODÈLE JOINT :
  - RandomForest (capture les interactions non linéaires entre features),
  - Ridge (baseline linéaire),
en WALK-FORWARD PURGÉ (plis non chevauchants, purge h), net de frais, avec un CONTRÔLE
SHUFFLE (labels permutés) pour déflater. Verdict : l'interaction jointe bat-elle (a) le
hasard (shuffle), (b) la meilleure feature isolée, (c) le mur des frais ? Lecture seule.
"""
import math
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB.parents[1]))

import candles_history as ch          # noqa: E402
import features_v2 as fv              # noqa: E402
import geometric_agent as ga          # noqa: E402
import gate_lib as gl                 # noqa: E402
from scipy.stats import spearmanr     # noqa: E402
from sklearn.ensemble import RandomForestRegressor  # noqa: E402
from sklearn.linear_model import Ridge              # noqa: E402

W = 160
HZ = (1, 4, 24)
FEE_BPS = 6.0                         # 6 bps/côté (frais Bitget futures taker, mur du rejet)
PLAN = [("30m", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 3),
        ("1H",  ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 3),
        ("4H",  ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 1),
        ("1D",  ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"], 1)]
REF = "BTCUSDT"                       # actif de référence pour les corrélations cross-asset
NOLDS_TARGET = 450                    # sous-échantillonnage nolds (coûteux) + forward-fill


def _load(sym, gran):
    ts, cl = gl.load_series(sym, gran)
    return ts, cl


def _align(ts_a, x_a, ts_b, x_b):
    """intersection des timestamps -> deux séries alignées (pour le cross-asset)."""
    common, ia, ib = np.intersect1d(ts_a, ts_b, return_indices=True)
    return x_a[ia], x_b[ib]


def _ffill(a):
    a = a.copy(); last = np.nan
    for i in range(len(a)):
        if np.isfinite(a[i]): last = a[i]
        elif np.isfinite(last): a[i] = last
    return a


def build_matrix(sym, gran, stride):
    ts, cl = _load(sym, gran)
    if len(cl) < 2 * W + 80:
        return None
    # série de référence alignée (returns) pour dcor/pearson cross-asset
    if sym == REF:
        ts_r, cl_r = _load("ETHUSDT", gran)   # BTC <-> ETH
    else:
        ts_r, cl_r = _load(REF, gran)
    ca, cb = _align(ts, cl, ts_r, cl_r)
    if len(ca) < 2 * W + 80:
        return None
    cl = ca                                   # on travaille sur la fenêtre commune
    ref = cb
    lr = np.diff(np.log(cl)); lr_ref = np.diff(np.log(ref))
    n = len(cl)
    grid = np.arange(2 * W, n - max(HZ), stride)
    Kn = max(1, math.ceil(len(grid) / NOLDS_TARGET))
    names = ["w1_gauss", "w1_drift", "w1_drift_shape", "dfa", "hurst", "sampen",
             "corr_dim", "geom_vote", "xcorr_pearson", "xcorr_dcor", "rvol"]
    X = {k: np.full(len(grid), np.nan) for k in names}
    Y = {h: np.full(len(grid), np.nan) for h in HZ}
    for gi, t in enumerate(grid):
        cur = lr[t - W:t]; prev = lr[t - 2 * W:t - W]
        cur_ref = lr_ref[t - W:t]
        X["w1_gauss"][gi] = fv.w1_gauss_pot(cur)
        X["w1_drift"][gi] = fv.w1_drift(prev, cur)
        X["w1_drift_shape"][gi] = fv.w1_drift_shape(prev, cur)
        X["geom_vote"][gi] = ga.signal(cl[t - W:t + 1].tolist())["vote"]
        X["rvol"][gi] = float(cur.std())
        # cross-asset (pearson toujours, dcor sous-échantillonné car coûteux)
        if cur.std() > 1e-12 and cur_ref.std() > 1e-12:
            X["xcorr_pearson"][gi] = float(np.corrcoef(cur, cur_ref)[0, 1])
        if gi % Kn == 0:
            X["dfa"][gi] = fv.nolds_dfa(cur)
            X["hurst"][gi] = fv.nolds_hurst_rs(cur)
            X["sampen"][gi] = fv.nolds_sampen(cur)
            X["corr_dim"][gi] = fv.nolds_corr_dim(cur)
            X["xcorr_dcor"][gi] = fv.dcor_pair(cur, cur_ref)
        for h in HZ:
            Y[h][gi] = math.log(cl[t + h] / cl[t])
    for k in ("dfa", "hurst", "sampen", "corr_dim", "xcorr_dcor"):
        X[k] = _ffill(X[k])
    return grid, names, X, Y


def net_pnl_bps(pred, fwd):
    """Position = signe(pred), PnL net de frais sur le turnover (bps/barre)."""
    pos = np.sign(pred)
    dpos = np.abs(np.diff(np.concatenate([[0.0], pos])))
    gross = pos * fwd
    net = gross - (FEE_BPS / 1e4) * dpos
    return float(net.mean() * 1e4), float(gross.mean() * 1e4), float(np.mean(pos != 0) * 100)


def wf_joint(grid, names, X, Y, h, seed_shuffle=False):
    """Walk-forward purgé : chaque pli = test, entraînement sur le reste (purgé h).
    Retourne (oos_ic_rf, oos_ic_ridge, net_bps_rf, gross_bps_rf, best_indiv_ic)."""
    M = np.column_stack([X[k] for k in names])
    y = Y[h]
    ok = np.all(np.isfinite(M), axis=1) & np.isfinite(y)
    M, y, g = M[ok], y[ok], grid[ok]
    if len(y) < 400:
        return None
    folds = gl.purged_folds(g, h)
    oos_pred_rf = np.full(len(y), np.nan); oos_pred_rg = np.full(len(y), np.nan)
    idx_all = np.arange(len(y))
    for test in folds:
        if len(test) < 40:
            continue
        tmask = np.zeros(len(y), bool); tmask[test] = True
        # purge : retire du train les points à moins de h de la fenêtre de test
        lo, hi = g[test].min() - h, g[test].max() + h
        train = idx_all[~tmask & ~((g >= lo) & (g <= hi))]
        if len(train) < 200:
            continue
        ytr = y[train].copy()
        if seed_shuffle:
            rng = np.random.default_rng(len(train))  # déterministe
            ytr = rng.permutation(ytr)
        rf = RandomForestRegressor(n_estimators=120, max_depth=5, min_samples_leaf=40,
                                   n_jobs=-1, random_state=0)
        rf.fit(M[train], ytr)
        oos_pred_rf[test] = rf.predict(M[test])
        rg = Ridge(alpha=10.0).fit(M[train], ytr)
        oos_pred_rg[test] = rg.predict(M[test])
    m = np.isfinite(oos_pred_rf)
    if m.sum() < 200:
        return None
    ic_rf = float(spearmanr(oos_pred_rf[m], y[m]).statistic)
    ic_rg = float(spearmanr(oos_pred_rg[m], y[m]).statistic)
    net_rf, gross_rf, expo = net_pnl_bps(oos_pred_rf[m], y[m])
    best_indiv = max(abs(float(spearmanr(M[m, j], y[m]).statistic)) for j in range(M.shape[1]))
    return dict(ic_rf=round(ic_rf, 4), ic_ridge=round(ic_rg, 4), net_bps=round(net_rf, 3),
                gross_bps=round(gross_rf, 3), expo=round(expo, 1),
                best_indiv_ic=round(best_indiv, 4), n=int(m.sum()))


def run():
    rows = []
    for gran, syms, stride in PLAN:
        for sym in syms:
            try:
                built = build_matrix(sym, gran, stride)
            except Exception as e:
                print(f"  skip {sym} {gran}: {e}"); continue
            if not built:
                continue
            grid, names, X, Y = built
            for h in HZ:
                r = wf_joint(grid, names, X, Y, h)
                sh = wf_joint(grid, names, X, Y, h, seed_shuffle=True)
                if r:
                    r.update(tf=gran, sym=sym, h=h,
                             shuffle_ic_rf=(sh["ic_rf"] if sh else None),
                             shuffle_net_bps=(sh["net_bps"] if sh else None))
                    rows.append(r)
                    print(f"  {gran:<3} {sym:<8} h={h:<3} | joint IC rf={r['ic_rf']:+.4f} "
                          f"ridge={r['ic_ridge']:+.4f} | best_indiv={r['best_indiv_ic']:.4f} | "
                          f"net={r['net_bps']:+.2f}bps gross={r['gross_bps']:+.2f} | "
                          f"shuffle_ic={r.get('shuffle_ic_rf')}", flush=True)
    return rows


def verdict(rows):
    import json
    print("\n" + "=" * 90)
    print("RE-TEST INTERACTION geometric_v2 — modèle JOINT (RF interactions + Ridge), WF purgé, net frais")
    print("=" * 90)
    if not rows:
        print("Aucune config exploitable."); return
    net = np.array([r["net_bps"] for r in rows])
    icrf = np.array([r["ic_rf"] for r in rows])
    sh = np.array([r["shuffle_ic_rf"] for r in rows if r.get("shuffle_ic_rf") is not None])
    beat_indiv = np.mean([abs(r["ic_rf"]) > r["best_indiv_ic"] + 0.01 for r in rows]) * 100
    print(f"configs {len(rows)} · net_bps médian {np.median(net):+.2f} (frais {FEE_BPS} bps) · "
          f"IC_rf médian {np.median(icrf):+.4f}")
    print(f"IC shuffle médian (contrôle) {np.median(sh):+.4f}" if len(sh) else "")
    print(f"% net>0 : {np.mean(net>0)*100:.0f}% · % IC joint bat best individuel (+0.01) : {beat_indiv:.0f}%")
    strong = [r for r in rows if r["net_bps"] > 0 and r["ic_rf"] > 0.03
              and (r.get("shuffle_ic_rf") is None or abs(r["ic_rf"]) > abs(r["shuffle_ic_rf"]) + 0.03)]
    if not strong:
        print("\nVERDICT : REJET CONFIRMÉ sous la méthode INTERACTION — le modèle joint (interactions")
        print("  non linéaires du vecteur géométrique complet) ne crée AUCUN signal net > frais que")
        print("  l'analyse individuelle aurait manqué. IC OOS ≈ contrôle shuffle = pas d'edge réel.")
    else:
        print(f"\nVERDICT : PISTE — {len(strong)} configs où l'interaction jointe dépasse individuel+shuffle+frais :")
        for r in sorted(strong, key=lambda x: -x["net_bps"])[:10]:
            print(f"    {r['tf']:<3} {r['sym']:<8} h={r['h']} net={r['net_bps']:+.2f}bps "
                  f"IC={r['ic_rf']:+.4f} (indiv {r['best_indiv_ic']:.3f}, shuffle {r.get('shuffle_ic_rf')})")
        print("  -> DÉFLATER (nb d'essais) + valider OOS sur données neuves avant toute conclusion.")
    json.dump(rows, open("interaction_geom_results.json", "w"), indent=0)
    print("-> interaction_geom_results.json")


if __name__ == "__main__":
    print("Recalcul features + modèle joint (peut prendre plusieurs minutes)...", flush=True)
    verdict(run())
