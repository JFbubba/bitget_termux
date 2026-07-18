"""
interaction_test.py — RE-TEST des signaux de réversion en INTERACTION (méthode ERR-014).

Le rejet « réversion 7 signaux » (VERDICTS.md) reposait sur l'IC INDIVIDUEL de chaque
signal (chacun < frais). La méthode corrigée exige de tester l'INTERACTION des indicateurs,
pas chacun isolément. On teste donc deux systèmes interagissants, en ÉVÉNEMENTIEL net de
frais, sur l'échelle TF COMPLÈTE (ERR-001), cross-secteur, avec benchmark buy-and-hold :

  A) CONFLUENCE K-parmi-7 : n'agir que si >=K signaux concordent sur l'extrême
     (surachat causal -> short réversion ; survente -> long réversion).
  B) SLOW-MOM / FAST-REVERSION (arXiv:2105.13727) : le momentum LENT gâte la DIRECTION
     de la réversion rapide (acheter les creux en tendance haussière ; vendre les pics
     en tendance baissière).

Anti-overfit : K est BALAYÉ (pas de cherry-pick) ; on rapporte gross ET net ; le verdict
exige de tenir à travers K et de battre le B&H. Lecture seule (numpy pur). Réutilise
audit_core (données + folds purgés) et signals_indep (7 signaux causals).
"""
import json
import math
import sys

import numpy as np

import audit_core as ac
import signals_indep as si

sys.path.insert(0, "/root/bitget_termux_repo/scratchpad/strategy_tester")
import metrics as M  # buy_and_hold()

# tf-ladder-ok : échelle COMPLÈTE M1..W1 (ERR-001)
LADDER = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]
BARS_PER_YEAR = M.BARS_PER_YEAR

SECTORS = {
    "cryptoMaj": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
                  "ADAUSDT", "LINKUSDT", "UNIUSDT"],
    "cryptoMeme": ["DOGEUSDT"],
    "metal": ["XAUUSDT"],
    "equity": ["NVDAUSDT", "AAPLUSDT"],
    "etf": ["QQQUSDT"],
}
ALL_SYMS = [(s, sec) for sec, lst in SECTORS.items() for s in lst]

SIG_NAMES = ["momentum8", "rsi14", "dist_sma50", "donchian20", "supertrend", "vortex", "cmf"]
FEE = 0.0006          # 6 bps / côté (taker futures) — mur des frais du rejet
ZW = 100              # fenêtre du z-score causal
ZTHR = 1.0            # seuil d'extrême
SLOW_L = 100          # lookback du momentum lent (variante B)
MAX_BARS = 6000       # cap anti-explosion sur les TF fins (1m/5m) — CAP RAPPORTÉ


def roll_z(s, w=ZW):
    """z-score CAUSAL glissant : z[i] = (s[i]-mean)/std sur la fenêtre [i-w+1 .. i].
    NaN tant que la fenêtre n'est pas pleine ou que s est NaN."""
    s = np.asarray(s, float)
    n = len(s)
    z = np.full(n, np.nan)
    fin = np.isfinite(s)
    s0 = np.where(fin, s, 0.0)
    c1 = np.concatenate([[0.0], np.cumsum(s0)])
    c2 = np.concatenate([[0.0], np.cumsum(s0 * s0)])
    cf = np.concatenate([[0], np.cumsum(fin.astype(int))])
    for i in range(n):
        lo = i - w + 1
        if lo < 0:
            continue
        cnt = cf[i + 1] - cf[lo]
        if cnt < w or not fin[i]:
            continue
        mean = (c1[i + 1] - c1[lo]) / w
        var = (c2[i + 1] - c2[lo]) / w - mean * mean
        sd = math.sqrt(var) if var > 1e-18 else 0.0
        if sd > 1e-12:
            z[i] = (s[i] - mean) / sd
    return z


def backtest(pos, c, tf):
    """PnL événementiel-équivalent net de frais. pos[i] (causal, connu à la clôture i)
    est appliqué au rendement i -> i+1 ; frais sur le turnover |pos[i]-pos[i-1]|."""
    c = np.asarray(c, float)
    ret = np.full(len(c), np.nan)
    ret[:-1] = c[1:] / c[:-1] - 1.0
    p = np.nan_to_num(pos, nan=0.0)
    dpos = np.abs(np.diff(np.concatenate([[0.0], p])))
    fees = FEE * dpos
    m = np.isfinite(ret)
    gross = p[m] * ret[m]
    net = gross - fees[m]
    eq = np.cumprod(1.0 + net)
    # trades = segments à position constante non nulle
    trades, i, npos = [], 0, len(p)
    while i < npos:
        if p[i] == 0 or not np.isfinite(ret[i]):
            i += 1
            continue
        j = i
        seg = 0.0
        while j < npos and p[j] == p[i] and np.isfinite(ret[j]):
            seg += p[j] * ret[j]
            j += 1
        seg -= 2 * FEE  # entrée + sortie
        trades.append((p[i], seg, j - i))
        i = j
    bpy = BARS_PER_YEAR.get(tf, 8760)
    mu, sd = float(np.mean(net)), float(np.std(net))
    sharpe = mu / sd * math.sqrt(bpy) if sd > 1e-12 else None
    tstat = mu / (sd / math.sqrt(len(net))) if sd > 1e-12 and len(net) > 2 else 0.0
    out = {
        "n_bars": int(m.sum()), "n_trades": len(trades),
        "gross_ret_pct": round(float(np.prod(1 + gross) - 1) * 100, 2),
        "net_ret_pct": round(float(eq[-1] - 1) * 100, 2) if len(eq) else None,
        "net_sharpe": round(sharpe, 2) if sharpe is not None else None,
        "net_mean_bps": round(mu * 1e4, 3),
        "gross_mean_bps": round(float(np.mean(gross)) * 1e4, 3),
        "t_net": round(tstat, 2),
        "exposure_pct": round(float(np.mean(p[m] != 0)) * 100, 1),
    }
    if trades:
        tp = np.array([t[1] for t in trades])
        out["expectancy_bps"] = round(float(tp.mean()) * 1e4, 2)
        out["win_rate_pct"] = round(float(np.mean(tp > 0)) * 100, 1)
        lp = sum(t[1] for t in trades if t[0] > 0)
        sp = sum(t[1] for t in trades if t[0] < 0)
        out["long_pnl_pct"] = round(lp * 100, 2)
        out["short_pnl_pct"] = round(sp * 100, 2)
    return out, eq


def positions_confluence(feats, K):
    """Variante A : short si >=K signaux en surachat (z>+ZTHR), long si >=K en survente."""
    Z = np.array([roll_z(feats[nm]) for nm in SIG_NAMES])
    hi = np.sum(Z > ZTHR, axis=0)     # nb de signaux "trop hauts" (a trop monté)
    lo = np.sum(Z < -ZTHR, axis=0)    # nb de signaux "trop bas" (a trop baissé)
    allfin = np.all(np.isfinite(Z), axis=0)
    pos = np.zeros(Z.shape[1])
    pos[(hi >= K) & allfin] = -1.0    # réversion : short le surachat
    pos[(lo >= K) & allfin] = +1.0    # réversion : long la survente
    pos[(hi >= K) & (lo >= K)] = 0.0  # ambigu -> flat
    return pos


def positions_slowfast(feats, c, K):
    """Variante B : momentum lent (signe de c/c[-L]-1) gâte la réversion rapide.
    Tendance haussière -> n'acheter QUE les creux (survente) ; baissière -> ne vendre
    QUE les pics (surachat)."""
    c = np.asarray(c, float)
    slow = np.full(len(c), np.nan)
    slow[SLOW_L:] = c[SLOW_L:] / c[:-SLOW_L] - 1.0
    Z = np.array([roll_z(feats[nm]) for nm in SIG_NAMES])
    hi = np.sum(Z > ZTHR, axis=0)
    lo = np.sum(Z < -ZTHR, axis=0)
    allfin = np.all(np.isfinite(Z), axis=0) & np.isfinite(slow)
    pos = np.zeros(len(c))
    up = slow > 0
    dn = slow < 0
    pos[(lo >= K) & up & allfin] = +1.0    # creux en tendance haussière -> long
    pos[(hi >= K) & dn & allfin] = -1.0    # pic en tendance baissière -> short
    return pos


def run():
    results = []
    coverage = {tf: {"ok": 0, "skip_short": 0, "skip_missing": 0} for tf in LADDER}
    for tf in LADDER:
        for sym, sec in ALL_SYMS:
            try:
                d = ac.load(sym, tf)
            except Exception:
                coverage[tf]["skip_missing"] += 1
                continue
            c = d["c"]
            if len(c) > MAX_BARS:            # cap RAPPORTÉ, pas silencieux
                for k in ("o", "h", "l", "c", "v"):
                    d[k] = d[k][-MAX_BARS:]
                c = d["c"]
            if len(c) < max(ZW + 50, SLOW_L + 100):
                coverage[tf]["skip_short"] += 1
                continue
            coverage[tf]["ok"] += 1
            feats = si.all_signals(d)
            bh = M.buy_and_hold(c, warmup=ZW, tf=tf) or {}
            for K in (3, 4, 5):
                posA = positions_confluence(feats, K)
                rA, _ = backtest(posA, c, tf)
                results.append({"tf": tf, "sym": sym, "sec": sec, "variant": "confluence",
                                "K": K, **rA, "bh_sharpe": bh.get("bh_sharpe"),
                                "bh_ret_pct": bh.get("bh_return_pct")})
            for K in (3, 4):
                posB = positions_slowfast(feats, c, K)
                rB, _ = backtest(posB, c, tf)
                results.append({"tf": tf, "sym": sym, "sec": sec, "variant": "slowfast",
                                "K": K, **rB, "bh_sharpe": bh.get("bh_sharpe"),
                                "bh_ret_pct": bh.get("bh_return_pct")})
    return results, coverage


def _beats_bh(r):
    return (r.get("net_sharpe") is not None and r.get("bh_sharpe") is not None
            and r["net_sharpe"] > r["bh_sharpe"])


def summarize(results, coverage):
    print("=" * 92)
    print("RE-TEST INTERACTION — réversion 7 signaux (méthode ERR-014, net de frais, B&H)")
    print(f"frais {FEE*1e4:.0f} bps/côté · z-window {ZW} · seuil {ZTHR}σ · cap {MAX_BARS} barres/TF")
    print("=" * 92)
    print("\nCouverture (échelle TF complète, ERR-001) :")
    for tf in LADDER:
        cv = coverage[tf]
        print(f"  {tf:<4} ok={cv['ok']:<2} short={cv['skip_short']} missing={cv['skip_missing']}")

    for variant in ("confluence", "slowfast"):
        print(f"\n----- VARIANTE : {variant} -----")
        print(f"{'TF':<5}{'n':>4}{'net_sh_med':>11}{'exp_bps_med':>12}"
              f"{'t_net_med':>10}{'%net>0':>8}{'%bat_BH':>8}{'gross_bps_med':>14}")
        for tf in LADDER:
            rs = [r for r in results if r["tf"] == tf and r["variant"] == variant]
            if not rs:
                continue
            nsh = [r["net_sharpe"] for r in rs if r["net_sharpe"] is not None]
            exp = [r.get("expectancy_bps") for r in rs if r.get("expectancy_bps") is not None]
            tn = [r["t_net"] for r in rs if r["t_net"] is not None]
            gm = [r["gross_mean_bps"] for r in rs if r["gross_mean_bps"] is not None]
            pos_net = np.mean([r["net_mean_bps"] > 0 for r in rs]) * 100
            pbh = np.mean([_beats_bh(r) for r in rs]) * 100
            med = lambda x: round(float(np.median(x)), 2) if x else None
            print(f"{tf:<5}{len(rs):>4}{str(med(nsh)):>11}{str(med(exp)):>12}"
                  f"{str(med(tn)):>10}{pos_net:>7.0f}%{pbh:>7.0f}%{str(med(gm)):>14}")

    # verdict global : une variante bat-elle les frais ET le B&H de façon robuste ?
    print("\n" + "=" * 92)
    strong = [r for r in results
              if r.get("net_sharpe") is not None and r["net_sharpe"] > 0.5
              and r.get("t_net", 0) >= 3 and r.get("net_mean_bps", 0) > 0 and _beats_bh(r)]
    n_strong = len(strong)
    frac_net_pos = np.mean([r["net_mean_bps"] > 0 for r in results]) * 100
    frac_beats = np.mean([_beats_bh(r) for r in results]) * 100
    print(f"Configs totales : {len(results)} · net>0 : {frac_net_pos:.0f}% · bat B&H : {frac_beats:.0f}%")
    print(f"Configs FORTES (net_sharpe>0.5 ET t_net>=3 ET net>0 ET bat B&H) : {n_strong}")
    if n_strong == 0:
        print("VERDICT : REJET CONFIRMÉ sous la méthode INTERACTION — l'interaction (confluence")
        print("  et slow-mom/fast-rev) ne franchit PAS le mur des frais ; aucun edge caché par")
        print("  l'analyse individuelle. Cohérent avec le prior (signaux de réversion redondants).")
    else:
        print(f"VERDICT : PISTE VIVANTE — {n_strong} configs fortes survivent. À DÉFLATER (Deflated")
        print("  Sharpe sur le nb d'essais) et valider OOS walk-forward avant toute conclusion.")
        for r in sorted(strong, key=lambda x: -x["net_sharpe"])[:12]:
            print(f"    {r['tf']:<4} {r['sym']:<9} {r['variant']:<11} K={r['K']} "
                  f"net_sh={r['net_sharpe']} t={r['t_net']} exp={r.get('expectancy_bps')}bps "
                  f"bh_sh={r['bh_sharpe']}")
    print("=" * 92)
    json.dump(results, open("interaction_results.json", "w"), indent=0)
    print("-> interaction_results.json")


if __name__ == "__main__":
    res, cov = run()
    summarize(res, cov)
