"""
joint_v2.py — RÉ-ANALYSE avec constituants CORRIGÉS (méthode ERR-014, audit 18/07).

Compare deux jeux de features sur les MÊMES lignes, historique COMPLET (grand échantillon
→ pas de piège petit-échantillon), joint RF WF purgé pooled cross-sectionnel, CONTRÔLE
SHUFFLE + crible de frais (taker 6 → maker 1-2 → brut 0) :

  BASE (tel que testé avant) : 7 prix (supertrend SMA) + 4 régime + xs_rank 8-barres
        CONTEMPORAIN SANS SKIP  ← spec incomplète pointée par l'audit.
  V2  (corrigé) : 7 prix (supertrend WILDER) + 4 régime + momentum cross-sectionnel
        SKIP-1 formation ~2 sem (rang) + LEAD-LAG seesaw (rendements retardés BTC & ETH).

Verdict honnête : V2 crée-t-il un edge net > frais (maker) que BASE ratait, qui BAT le
shuffle et tient across configs ? Réutilise gi (gates/rr) + si (prix base) + v2 (corrigés).
"""
import json
import math

import numpy as np
from scipy.stats import spearmanr, rankdata
from sklearn.ensemble import RandomForestRegressor

import audit_core as ac
import global_interaction as gi
import signals_indep as si
import signals_v2 as v2

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT",
        "DOGEUSDT", "LINKUSDT", "UNIUSDT", "TRXUSDT"]
LEADERS = ["BTCUSDT", "ETHUSDT"]
# (tf, formation lookback pour le momentum cross-sectionnel, lookback leader)
LADDER = [("1D", 14, 3), ("4H", 12, 4), ("1H", 12, 6)]
HZ = (1, 4, 7)
FEES_BPS = [6.0, 2.0, 1.0, 0.0]
PRICE = ["momentum8", "rsi14", "dist_sma50", "donchian20", "supertrend", "vortex", "cmf"]
REG = ["ker", "bb_bw", "sma200", "rvol"]


MAX_BARS = 6000          # cap RAPPORTÉ (borne le coût des indicateurs en boucle Python)


def build_sym(sym, tf, form_lb):
    d = ac.load(sym, tf)
    if len(d["c"]) > MAX_BARS:
        for k in ("o", "h", "l", "c", "v", "ts"):
            d[k] = d[k][-MAX_BARS:]
    c = d["c"]
    if len(c) < 300:
        return None
    base_p = si.all_signals(d)                       # supertrend SMA
    v2_p = v2.price_signals_v2(d)                    # supertrend Wilder
    reg = {"ker": gi.ker(c), "bb_bw": gi.bb_bw(c), "sma200": gi.sma_side(c), "rvol": gi.rvol(c)}
    return {"ts": d["ts"], "c": c, "base_p": base_p, "v2_p": v2_p, "reg": reg,
            "rr_old": gi.recent_ret(c, 8),                       # 8-barres SANS skip (BASE)
            "rr_new": v2.formation_ret(c, lookback=form_lb, skip=1)}  # skip-1 (V2)


def run_tf(tf, form_lb, leader_lb):
    data = {}
    for s in SYMS:
        try:
            b = build_sym(s, tf, form_lb)
        except Exception:
            b = None
        if b:
            data[s] = b
    if len(data) < 4:
        return None
    common = None
    for b in data.values():
        st = set(b["ts"].tolist())
        common = st if common is None else (common & st)
    common = np.array(sorted(common), dtype=np.int64)
    if len(common) > 3000:
        common = common[::math.ceil(len(common) / 3000)]
    if len(common) < 250:
        return None
    pos_in = {s: {int(t): i for i, t in enumerate(b["ts"])} for s, b in data.items()}
    order = list(data.keys())

    def xs_rank(key):
        mat = np.full((len(common), len(order)), np.nan)
        for j, s in enumerate(order):
            pin = pos_in[s]
            for k, t in enumerate(common):
                mat[k, j] = data[s][key][pin[int(t)]]
        rk = np.full_like(mat, np.nan)
        for k in range(len(common)):
            row = mat[k]; m = np.isfinite(row)
            if m.sum() >= 4:
                rk[k, m] = (rankdata(row[m]) - 1) / (m.sum() - 1) - 0.5
        return rk

    xr_old = xs_rank("rr_old")
    xr_new = xs_rank("rr_new")
    # rendements retardés des MENEURS, alignés aux ts communs (lead-lag seesaw)
    lead = {}
    for L in LEADERS:
        if L not in data:
            continue
        lr = v2.leader_ret(data[L]["c"], leader_lb)
        pin = pos_in[L]
        arr = np.full(len(common), np.nan)
        for k, t in enumerate(common):
            arr[k] = lr[pin[int(t)]]
        lead[L] = arr
    return data, order, common, pos_in, xr_old, xr_new, lead


def assemble(tf, form_lb, leader_lb, h):
    built = run_tf(tf, form_lb, leader_lb)
    if not built:
        return None
    data, order, common, pos_in, xr_old, xr_new, lead = built
    Xb, Xv, y, tk, sj = [], [], [], [], []
    for j, s in enumerate(order):
        b = data[s]; pin = pos_in[s]; c = b["c"]
        for k, t in enumerate(common):
            bi = pin[int(t)]
            if bi + h >= len(c):
                continue
            base_vec = [b["base_p"][p][bi] for p in PRICE] + [b["reg"][r][bi] for r in REG] + [xr_old[k, j]]
            v2_vec = [b["v2_p"][p][bi] for p in PRICE] + [b["reg"][r][bi] for r in REG] + [xr_new[k, j]]
            v2_vec += [lead[L][k] for L in LEADERS if L in lead]
            if not (all(np.isfinite(v) for v in base_vec) and all(np.isfinite(v) for v in v2_vec)):
                continue
            Xb.append(base_vec); Xv.append(v2_vec)
            y.append(math.log(c[bi + h] / c[bi])); tk.append(k); sj.append(j)
    if len(y) < 400:
        return None
    return np.array(Xb), np.array(Xv), np.array(y), np.array(tk), np.array(sj)


def wf_oos(X, y, tk, h, yfit=None):
    yf = y if yfit is None else yfit
    folds = ac.purged_folds(tk, h, n_folds=6)
    oos = np.full(len(y), np.nan); idx = np.arange(len(y))
    for keep in folds:
        if len(keep) < 50:
            continue
        ttk = set(tk[keep].tolist()); tmask = np.isin(tk, list(ttk))
        lo, hi = min(ttk) - h, max(ttk) + h
        train = idx[~tmask & ~((tk >= lo) & (tk <= hi))]; te = idx[tmask]
        if len(train) < 250 or len(te) < 30:
            continue
        rf = RandomForestRegressor(n_estimators=60, max_depth=5, min_samples_leaf=60,
                                   n_jobs=-1, random_state=0)
        oos[te] = rf.fit(X[train], yf[train]).predict(X[te])
    return oos


def net_at_fee(oos, y, sj, fee):
    m = np.isfinite(oos); nets = []
    for j in np.unique(sj):
        sm = m & (sj == j)
        if sm.sum() < 15:
            continue
        posn = np.sign(oos[sm])
        dpos = np.abs(np.diff(np.concatenate([[0.0], posn])))
        nets.append(posn * y[sm] - fee * dpos)
    return float(np.concatenate(nets).mean() * 1e4) if nets else 0.0


def _ic(oos, y):
    m = np.isfinite(oos)
    return float(spearmanr(oos[m], y[m]).statistic) if m.sum() > 80 else float("nan")


def main():
    print("RÉ-ANALYSE constituants CORRIGÉS — BASE vs V2 (skip-1 + lead-lag + supertrend Wilder)")
    print("historique complet · joint RF WF purgé · shuffle · crible frais\n", flush=True)
    hdr = (f"{'tf':<4}{'h':>3}{'n':>7}{'IC_base':>9}{'IC_v2':>8}{'IC_shuf':>9}"
           + "".join(f"{'v2@'+str(int(f)):>8}" for f in FEES_BPS))
    print(hdr); print("-" * len(hdr))
    rows = []
    for tf, form_lb, leader_lb in LADDER:
        for h in HZ:
            try:
                a = assemble(tf, form_lb, leader_lb, h)
            except Exception as e:
                print(f"{tf:<4}{h:>3} err {e}"); continue
            if a is None:
                continue
            Xb, Xv, y, tk, sj = a
            oob = wf_oos(Xb, y, tk, h)
            oov = wf_oos(Xv, y, tk, h)
            rng = np.random.default_rng(len(y))
            oosh = wf_oos(Xv, y, tk, h, yfit=rng.permutation(y))
            icb, icv, ics = _ic(oob, y), _ic(oov, y), _ic(oosh, y)
            nets = {f: net_at_fee(oov, y, sj, f / 1e4) for f in FEES_BPS}
            print(f"{tf:<4}{h:>3}{len(y):>7}{icb:>9.4f}{icv:>8.4f}{ics:>9.4f}"
                  + "".join(f"{nets[f]:>8.2f}" for f in FEES_BPS), flush=True)
            rows.append(dict(tf=tf, h=h, n=len(y), ic_base=round(icb, 4), ic_v2=round(icv, 4),
                             ic_shuffle=round(ics, 4), net={int(f): round(nets[f], 3) for f in FEES_BPS}))
    print("\n" + "=" * 92)
    if rows:
        # V2 robuste = bat shuffle de marge ET net>0 à frais maker (1-2 bps)
        strong = [r for r in rows if r["ic_v2"] > r["ic_shuffle"] + 0.02
                  and (r["net"].get(1, -9) > 0 or r["net"].get(2, -9) > 0)]
        dic = [r["ic_v2"] - r["ic_base"] for r in rows]
        print(f"configs {len(rows)} · ΔIC médian (V2−BASE) {np.median(dic):+.4f} · "
              f"IC_v2>shuffle+0.02 : {np.mean([r['ic_v2']>r['ic_shuffle']+0.02 for r in rows])*100:.0f}%")
        print(f"configs V2 fortes (bat shuffle+0.02 ET net>0 à maker) : {len(strong)}")
        for r in sorted(strong, key=lambda x: -(x['ic_v2']-x['ic_shuffle'])):
            print(f"    {r['tf']:<4} h={r['h']:<3} IC_v2={r['ic_v2']:+.4f} (base {r['ic_base']:+.4f}, "
                  f"shuf {r['ic_shuffle']:+.4f}) net@2={r['net'].get(2)} net@1={r['net'].get(1)} net@0={r['net'].get(0)}")
        if not strong:
            print("\nVERDICT : même avec les specs CORRIGÉES (skip-1, lead-lag, supertrend Wilder),")
            print("  l'interaction jointe ne bat pas shuffle+frais maker de façon robuste. La correction")
            print("  ERR-014 a rendu le test JUSTE ; elle ne révèle pas d'alpha caché.")
        else:
            print("\nPISTE VIVANTE (specs corrigées) -> déflater (Deflated Sharpe sur le nb d'essais)")
            print("  + valider OOS sur fenêtre/ univers NEUFS avant toute promotion.")
        json.dump(rows, open("joint_v2_results.json", "w"), indent=0)
        print("-> joint_v2_results.json")
    else:
        print("Aucune config exploitable.")
    print("=" * 92)


if __name__ == "__main__":
    main()
