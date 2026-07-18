"""
global_interaction_funding.py — LA feature orthogonale manquante crée-t-elle l'edge ?

Le modèle joint GLOBAL n'interagissait que sur des proxys de PRIX colinéaires (+ gates
dérivés du prix + rang de momentum) -> IC ≈ shuffle. Hypothèse (méthode ERR-014, « tous
les indicateurs ensemble ») : il MANQUE la feature orthogonale au prix. La seule
historisée chez nous = le FUNDING (BTC/ETH/SOL/XRP/DOGE, ~3 mois, 8 h).

Design PROPRE : on compare PRICE-ONLY vs PRICE+FUNDING sur les MÊMES lignes (la fenêtre
où le funding existe), même modèle joint (RF WF purgé pooled cross-sectionnel), pour
ISOLER la contribution marginale du funding. Balayage de frais (taker 6 -> maker 1-2 ->
brut 0). Réutilise global_interaction (build/gates/xs_rank) + funding_features (causal).
Lecture seule.
"""
import json
import math

import numpy as np
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor

import audit_core as ac
import global_interaction as gi
import funding_features as ff

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]   # ont du funding
gi.SYMS = SYMS                                                   # rang XS parmi ces 5
LADDER = ["5m", "15m", "30m", "1H"]                              # fenêtre funding = assez de barres
HZ = (1, 4, 24)
FEES_BPS = [6.0, 2.0, 1.0, 0.0]
PRICE_F = gi.SIG + ["ker", "bb_bw", "sma200", "rvol"]            # 11 features de prix (+ xs_rank ajouté)
FUND_F = ["fund_level", "fund_z", "fund_sign"]


def assemble(tf, h):
    built = gi.run_tf(tf)
    if not built:
        return None
    data, order, common, pos_in, xs_rank = built
    for s in order:
        data[s]["F"] = ff.funding_features(s, data[s]["ts"])
    Xp, Xf, y, tk, sj = [], [], [], [], []
    for j, s in enumerate(order):
        b = data[s]; pin = pos_in[s]; c = b["c"]; F = b["F"]
        for k, t in enumerate(common):
            bi = pin[int(t)]
            if bi + h >= len(c):
                continue
            pv = [b["M"][fn][bi] for fn in PRICE_F] + [xs_rank[k, j]]
            fv = [F["fund_level"][bi], F["fund_z"][bi], F["fund_sign"][bi]]
            vec = pv + fv
            if not all(np.isfinite(v) for v in vec):   # fenêtre funding + tout fini
                continue
            Xp.append(pv); Xf.append(vec)
            y.append(math.log(c[bi + h] / c[bi])); tk.append(k); sj.append(j)
    if len(y) < 500:
        return None
    return (np.array(Xp), np.array(Xf), np.array(y),
            np.array(tk), np.array(sj))


def wf_oos(X, y, tk, h):
    folds = ac.purged_folds(tk, h, n_folds=6)
    oos = np.full(len(y), np.nan); idx = np.arange(len(y))
    for keep in folds:
        if len(keep) < 60:
            continue
        ttk = set(tk[keep].tolist()); tmask = np.isin(tk, list(ttk))
        lo, hi = min(ttk) - h, max(ttk) + h
        train = idx[~tmask & ~((tk >= lo) & (tk <= hi))]; te = idx[tmask]
        if len(train) < 300 or len(te) < 40:
            continue
        rf = RandomForestRegressor(n_estimators=60, max_depth=5, min_samples_leaf=60,
                                   n_jobs=-1, random_state=0)
        oos[te] = rf.fit(X[train], y[train]).predict(X[te])
    return oos


def net_at_fee(oos, y, sj, fee):
    m = np.isfinite(oos); nets = []
    for j in np.unique(sj):
        sm = m & (sj == j)
        if sm.sum() < 20:
            continue
        oo = oos[sm]; yy = y[sm]; posn = np.sign(oo)
        dpos = np.abs(np.diff(np.concatenate([[0.0], posn])))
        nets.append(posn * yy - fee * dpos)
    return float(np.concatenate(nets).mean() * 1e4) if nets else 0.0


def ic(oos, y):
    m = np.isfinite(oos)
    return float(spearmanr(oos[m], y[m]).statistic) if m.sum() > 100 else float("nan")


def main():
    print("PRICE-ONLY vs PRICE+FUNDING — contribution marginale de la feature orthogonale")
    print("(joint RF, WF purgé pooled, mêmes lignes, fenêtre funding · 5 symboles)\n", flush=True)
    hdr = (f"{'tf':<4}{'h':>3}{'n':>7}{'IC_prix':>9}{'IC_+fund':>10}{'ΔIC':>8}"
           + "".join(f"{'net@'+str(int(f)):>9}" for f in FEES_BPS)
           + "".join(f"{'Δ@'+str(int(f)):>8}" for f in FEES_BPS))
    print(hdr); print("-" * len(hdr))
    allrows = []
    for tf in LADDER:
        for h in HZ:
            try:
                a = assemble(tf, h)
            except Exception as e:
                print(f"{tf:<4}{h:>3} err {e}"); continue
            if a is None:
                continue
            Xp, Xf, y, tk, sj = a
            oop = wf_oos(Xp, y, tk, h)
            oof = wf_oos(Xf, y, tk, h)
            m = np.isfinite(oop) & np.isfinite(oof)
            if m.sum() < 100:
                continue
            icp, icf = ic(oop, y), ic(oof, y)
            nets_p = {f: net_at_fee(oop, y, sj, f / 1e4) for f in FEES_BPS}
            nets_f = {f: net_at_fee(oof, y, sj, f / 1e4) for f in FEES_BPS}
            row = (f"{tf:<4}{h:>3}{int(m.sum()):>7}{icp:>9.4f}{icf:>10.4f}{icf-icp:>8.4f}"
                   + "".join(f"{nets_f[f]:>9.2f}" for f in FEES_BPS)
                   + "".join(f"{nets_f[f]-nets_p[f]:>8.2f}" for f in FEES_BPS))
            print(row, flush=True)
            allrows.append(dict(tf=tf, h=h, n=int(m.sum()), ic_price=round(icp, 4),
                                ic_fund=round(icf, 4), d_ic=round(icf - icp, 4),
                                net_price={int(f): round(nets_p[f], 3) for f in FEES_BPS},
                                net_fund={int(f): round(nets_f[f], 3) for f in FEES_BPS}))
    print("\n" + "=" * 96)
    if allrows:
        dic = [r["d_ic"] for r in allrows]
        # le funding aide-t-il ? ΔIC positif robuste ET une config +fund net>0 à frais maker
        maker_pos = [r for r in allrows if r["net_fund"].get(1, -9) > 0 or r["net_fund"].get(2, -9) > 0]
        print(f"configs {len(allrows)} · ΔIC médian (fund−prix) {np.median(dic):+.4f} · "
              f"ΔIC>0 : {np.mean(np.array(dic) > 0)*100:.0f}%")
        print(f"configs PRICE+FUNDING net>0 à frais maker (1 ou 2 bps) : {len(maker_pos)}")
        for r in sorted(maker_pos, key=lambda x: -max(x['net_fund'].get(1,-9), x['net_fund'].get(2,-9)))[:10]:
            print(f"    {r['tf']:<4} h={r['h']:<3} ΔIC={r['d_ic']:+.4f} "
                  f"net@2={r['net_fund'].get(2)} net@1={r['net_fund'].get(1)} net@0={r['net_fund'].get(0)}")
        if np.median(dic) <= 0.005 and not maker_pos:
            print("\nVERDICT : le FUNDING n'ajoute PAS d'edge net exploitable — même la feature")
            print("  orthogonale la mieux documentée ne franchit pas les frais. Complétude testée.")
        else:
            print("\nPISTE : le funding déplace l'IC/le net -> à déflater + valider OOS neuf.")
        json.dump(allrows, open("global_interaction_funding_results.json", "w"), indent=0)
        print("-> global_interaction_funding_results.json")
    else:
        print("Aucune config exploitable (fenêtre funding trop courte à ces TF).")
    print("=" * 96)


if __name__ == "__main__":
    main()
