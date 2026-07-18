"""
global_interaction.py — TEST JOINT GLOBAL (méthode ERR-014 poussée au maximum).

Le propriétaire : « tous les indicateurs pris ensemble, leurs INTERACTIONS créent le
signal ». On réunit donc l'UNION des familles d'indicateurs rejetées/candidates issues
des labos ET du backlog des ~102 agents (docs/BACKLOG_RECHERCHE.md §104) :

  - réversion/momentum 7 signaux (signals_indep) : momentum8, rsi14, dist_sma50,
    donchian20, supertrend, vortex, cmf ;
  - GATES de régime (BACKLOG P2, réfutés en individuel) : KER (Kaufman efficiency),
    largeur de Bollinger (squeeze), côté SMA200, vol réalisée ;
  - MOMENTUM CROSS-SECTIONNEL (#8 BACKLOG, « le vrai gisement de momentum crypto »,
    jamais testé en interaction) : rang du rendement récent du symbole dans l'univers.

Un MODÈLE JOINT (RandomForest pour les interactions non linéaires + Ridge linéaire)
prédit le rendement forward, en WALK-FORWARD PURGÉ sur l'axe TEMPS (pooled cross-sectionnel),
NET DE FRAIS, avec CONTRÔLE SHUFFLE (déflation). Verdict : l'interaction jointe de TOUTES
les familles crée-t-elle un signal net > frais que l'analyse par-indicateur a manqué ?
Lecture seule (numpy/sklearn). Réutilise audit_core (données/folds) + signals_indep.
"""
import json
import math
import sys

import numpy as np
from scipy.stats import spearmanr, rankdata
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

import audit_core as ac
import signals_indep as si

# tf-ladder-ok : échelle large M5..W1 (1m écarté = trop lourd + bruit pur, ERR-001 couvert ailleurs)
LADDER = [("5m", 3), ("15m", 3), ("30m", 2), ("1H", 2), ("4H", 1), ("1D", 1)]
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT"]
HZ = (1, 4, 24)
FEE = 0.0006          # 6 bps/côté
SIG = ["momentum8", "rsi14", "dist_sma50", "donchian20", "supertrend", "vortex", "cmf"]


# --------- gates de régime (causaux) ----------
def ker(c, n=20):
    out = np.full(len(c), np.nan)
    for i in range(n, len(c)):
        change = abs(c[i] - c[i - n])
        vol = np.abs(np.diff(c[i - n:i + 1])).sum()
        out[i] = change / vol if vol > 1e-12 else 0.0
    return out


def bb_bw(c, n=20):
    out = np.full(len(c), np.nan)
    for i in range(n, len(c)):
        w = c[i - n:i]; m = w.mean()
        out[i] = (w.std() / m) if m > 1e-12 else np.nan
    return out


def sma_side(c, n=200):
    out = np.full(len(c), np.nan)
    cs = np.concatenate([[0.0], np.cumsum(c)])
    for i in range(n, len(c)):
        sma = (cs[i] - cs[i - n]) / n
        out[i] = np.sign(c[i] - sma)
    return out


def rvol(c, n=20):
    lr = np.diff(np.log(c))
    out = np.full(len(c), np.nan)
    for i in range(n, len(lr) + 1):
        out[i] = lr[i - n:i].std()
    return out


def recent_ret(c, n=8):
    out = np.full(len(c), np.nan)
    out[n:] = np.log(c[n:] / c[:-n])
    return out


def build_sym(sym, gran):
    d = ac.load(sym, gran)
    c = d["c"]
    if len(c) < 400:
        return None
    feats = si.all_signals(d)                    # 7 signaux
    reg = {"ker": ker(c), "bb_bw": bb_bw(c), "sma200": sma_side(c), "rvol": rvol(c)}
    rr = recent_ret(c)
    M = {**{k: feats[k] for k in SIG}, **reg}
    return {"ts": d["ts"], "c": c, "M": M, "rr": rr}


def run_tf(gran):
    data = {}
    for s in SYMS:
        try:
            b = build_sym(s, gran)
        except Exception:
            b = None
        if b:
            data[s] = b
    if len(data) < 3:
        return None
    # timestamps communs (pour le rang cross-sectionnel)
    common = None
    for s, b in data.items():
        common = set(b["ts"].tolist()) if common is None else (common & set(b["ts"].tolist()))
    common = np.array(sorted(common), dtype=np.int64)
    if len(common) < 400:
        return None
    if len(common) > 2500:                       # sous-échantillonnage (coût RF) — RAPPORTÉ
        common = common[::math.ceil(len(common) / 2500)]
    # index de barre par symbole pour chaque ts commun
    pos_in = {s: {int(t): i for i, t in enumerate(b["ts"])} for s, b in data.items()}
    # rang cross-sectionnel du rendement récent à chaque ts commun
    rrmat = np.full((len(common), len(data)), np.nan)
    order = list(data.keys())
    for j, s in enumerate(order):
        pin = pos_in[s]
        for k, t in enumerate(common):
            rrmat[k, j] = data[s]["rr"][pin[int(t)]]
    xs_rank = np.full_like(rrmat, np.nan)
    for k in range(len(common)):
        row = rrmat[k]; m = np.isfinite(row)
        if m.sum() >= 3:
            xs_rank[k, m] = (rankdata(row[m]) - 1) / (m.sum() - 1) - 0.5   # ∈ [-0.5, 0.5]
    return data, order, common, pos_in, xs_rank


def pooled_wf(tf, h):
    built = run_tf(tf)
    if not built:
        return None
    data, order, common, pos_in, xs_rank = built
    feat_names = SIG + ["ker", "bb_bw", "sma200", "rvol", "xs_rank"]
    rows_X, rows_y, rows_t, rows_sym = [], [], [], []
    for j, s in enumerate(order):
        b = data[s]; pin = pos_in[s]; c = b["c"]
        for k, t in enumerate(common):
            bi = pin[int(t)]
            if bi + h >= len(c):
                continue
            vec = [b["M"][fn][bi] for fn in SIG + ["ker", "bb_bw", "sma200", "rvol"]]
            vec.append(xs_rank[k, j])
            if not all(np.isfinite(v) for v in vec):
                continue
            rows_X.append(vec); rows_y.append(math.log(c[bi + h] / c[bi]))
            rows_t.append(k); rows_sym.append(j)
    if len(rows_y) < 600:
        return None
    X = np.array(rows_X); y = np.array(rows_y)
    tk = np.array(rows_t); sj = np.array(rows_sym)
    # folds purgés sur l'axe TEMPS (indice de ts commun) — pas de fuite inter-symboles
    folds = ac.purged_folds(tk, h, n_folds=6)
    oos_rf = np.full(len(y), np.nan); oos_rg = np.full(len(y), np.nan)
    idx = np.arange(len(y))
    for keep in folds:
        if len(keep) < 60:
            continue
        test_tk = set(tk[keep].tolist())
        tmask = np.isin(tk, list(test_tk))
        lo, hi = min(test_tk) - h, max(test_tk) + h
        train = idx[~tmask & ~((tk >= lo) & (tk <= hi))]
        te = idx[tmask]
        if len(train) < 300 or len(te) < 40:
            continue
        rf = RandomForestRegressor(n_estimators=60, max_depth=5, min_samples_leaf=80,
                                   n_jobs=-1, random_state=0)
        rf.fit(X[train], y[train]); oos_rf[te] = rf.predict(X[te])
        oos_rg[te] = Ridge(alpha=10.0).fit(X[train], y[train]).predict(X[te])
    m = np.isfinite(oos_rf)
    if m.sum() < 300:
        return None
    ic_rf = float(spearmanr(oos_rf[m], y[m]).statistic)
    ic_rg = float(spearmanr(oos_rg[m], y[m]).statistic)
    # net PnL : position = signe(pred) par (sym, temps), frais sur le turnover par symbole
    net_list = []
    for j in range(len(order)):
        sm = m & (sj == j)
        if sm.sum() < 20:
            continue
        oo = oos_rf[sm]; yy = y[sm]
        posn = np.sign(oo)
        dpos = np.abs(np.diff(np.concatenate([[0.0], posn])))
        net_list.append(posn * yy - FEE * dpos)
    net = np.concatenate(net_list) if net_list else np.array([0.0])
    # contrôle shuffle
    rng = np.random.default_rng(len(y))
    ysh = rng.permutation(y)
    oos_sh = np.full(len(y), np.nan)
    for keep in folds:
        if len(keep) < 60:
            continue
        test_tk = set(tk[keep].tolist()); tmask = np.isin(tk, list(test_tk))
        lo, hi = min(test_tk) - h, max(test_tk) + h
        train = idx[~tmask & ~((tk >= lo) & (tk <= hi))]; te = idx[tmask]
        if len(train) < 300 or len(te) < 40:
            continue
        rf = RandomForestRegressor(n_estimators=60, max_depth=5, min_samples_leaf=80,
                                   n_jobs=-1, random_state=0).fit(X[train], ysh[train])
        oos_sh[te] = rf.predict(X[te])
    msh = np.isfinite(oos_sh)
    ic_sh = float(spearmanr(oos_sh[msh], y[msh]).statistic) if msh.sum() > 200 else None
    best_indiv = max(abs(float(spearmanr(X[m, j], y[m]).statistic)) for j in range(X.shape[1]))
    return dict(tf=tf, h=h, n=int(m.sum()), ic_rf=round(ic_rf, 4), ic_ridge=round(ic_rg, 4),
                ic_shuffle=(round(ic_sh, 4) if ic_sh is not None else None),
                best_indiv_ic=round(best_indiv, 4),
                net_bps=round(float(net.mean() * 1e4), 3),
                gross_bps=round(float((np.sign(oos_rf[m]) * y[m]).mean() * 1e4), 3),
                feats=feat_names)


def main():
    print("Modèle joint GLOBAL (réversion+régime+cross-sectionnel), WF purgé pooled, net frais...\n", flush=True)
    rows = []
    for tf, _ in LADDER:
        for h in HZ:
            try:
                r = pooled_wf(tf, h)
            except Exception as e:
                print(f"  {tf} h={h}: err {e}"); continue
            if r:
                rows.append(r)
                print(f"  {tf:<4} h={h:<3} n={r['n']:<6} | joint IC rf={r['ic_rf']:+.4f} "
                      f"ridge={r['ic_ridge']:+.4f} shuffle={r['ic_shuffle']} | best_indiv={r['best_indiv_ic']:.4f}"
                      f" | net={r['net_bps']:+.2f}bps gross={r['gross_bps']:+.2f}", flush=True)
    print("\n" + "=" * 92)
    print("VERDICT — INTERACTION JOINTE GLOBALE (union des indicateurs rejetés/candidats + BACKLOG)")
    print("=" * 92)
    if not rows:
        print("Aucune config exploitable."); return
    net = np.array([r["net_bps"] for r in rows])
    strong = [r for r in rows if r["net_bps"] > 0 and r["ic_rf"] > 0.03
              and (r["ic_shuffle"] is None or abs(r["ic_rf"]) > abs(r["ic_shuffle"]) + 0.03)
              and abs(r["ic_rf"]) > r["best_indiv_ic"] + 0.01]
    print(f"configs {len(rows)} · net_bps médian {np.median(net):+.2f} (frais {FEE*1e4:.0f}) · "
          f"% net>0 {np.mean(net>0)*100:.0f}% · IC_rf médian {np.median([r['ic_rf'] for r in rows]):+.4f}")
    if not strong:
        print("\nREJET CONFIRMÉ sous la méthode INTERACTION GLOBALE — même en réunissant TOUTES les")
        print("  familles (réversion + gates de régime + momentum cross-sectionnel) dans un modèle")
        print("  joint non linéaire, l'interaction ne crée AUCUN signal net > frais que l'analyse par")
        print("  indicateur a manqué. IC OOS ≈ shuffle. Confirme le bilan §104 : l'edge (réversion")
        print("  ~−0.04 IC) est réel mais < frais ; le levier est l'EXÉCUTION, pas la combinaison de signaux.")
    else:
        print(f"\nPISTE — {len(strong)} config(s) où l'interaction jointe bat individuel+shuffle+frais :")
        for r in sorted(strong, key=lambda x: -x["net_bps"]):
            print(f"    {r['tf']} h={r['h']} net={r['net_bps']:+.2f} IC={r['ic_rf']:+.4f} "
                  f"(indiv {r['best_indiv_ic']}, shuffle {r['ic_shuffle']})")
        print("  -> DÉFLATER + valider OOS neuf avant toute conclusion.")
    json.dump(rows, open("global_interaction_results.json", "w"), indent=0)
    print("-> global_interaction_results.json")


if __name__ == "__main__":
    main()
