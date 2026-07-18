"""
signals_indep.py — RÉIMPLÉMENTATION INDÉPENDANTE des signaux + mesure IC.
Tous causals (feature[t] n'utilise que o/h/l/c/v jusqu'à l'indice t inclus).
Signaux demandés : momentum(8), RSI(14), distance SMA(50), breakout Donchian(20).
+ réimplémentation SuperTrend / Vortex / CMF pour trancher la colinéarité.
Convention de SIGNE : valeur POSITIVE = "haussier / le prix vient de monter".
IC>0 => momentum (suivi de tendance paie) ; IC<0 => réversion.
"""
import math
import numpy as np
import audit_core as ac

# tf-ladder-ok : audit ciblé h-court/h-long sur BTC/ETH/XRP ; l'échelle COMPLÈTE
# M1..W1 est traitée dans ladder_check.py (ERR-001). Ici : profondeur maximale.
SYMS_1H = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
SYMS_1D = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
HZ = (1, 4, 24, 96)


# ----------------------- signaux causals (numpy pur) ------------------------
def momentum8(c):
    """Somme des 8 derniers rendements log (normalisée par la vol de fenêtre).
    Positif = a récemment monté."""
    lr = np.diff(np.log(c))
    out = np.full(len(c), np.nan)
    for i in range(9, len(c)):
        w = lr[i - 8:i]
        sd = w.std()
        out[i] = (w.sum() / (sd * math.sqrt(8))) if sd > 1e-12 else 0.0
    return out


def rsi(c, n=14):
    """RSI de Wilder, causal. Centré-orienté : RSI haut = a monté (momentum)."""
    d = np.diff(c)
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    out = np.full(len(c), np.nan)
    if len(d) < n:
        return out
    au = up[:n].mean(); ad = dn[:n].mean()
    for i in range(n, len(d)):
        au = (au * (n - 1) + up[i]) / n
        ad = (ad * (n - 1) + dn[i]) / n
        rs = au / ad if ad > 1e-12 else np.inf
        out[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    return out   # 0..100, >50 = a monté


def dist_sma(c, n=50):
    """(close - SMA50)/SMA50, causal. Positif = au-dessus de la moyenne (a monté)."""
    out = np.full(len(c), np.nan)
    csum = np.cumsum(np.insert(c, 0, 0.0))
    for i in range(n, len(c)):
        sma = (csum[i + 1] - csum[i + 1 - n]) / n
        out[i] = (c[i] - sma) / sma if sma > 0 else np.nan
    return out


def donchian(c, h_, l_, n=20):
    """Position dans le canal Donchian(20) : 2*(c-mid)/(hh-ll) ∈ [-1,1], causal.
    +1 = au plus haut 20 barres (breakout haussier). Positif = a monté."""
    out = np.full(len(c), np.nan)
    for i in range(n, len(c)):
        hh = h_[i - n:i].max(); ll = l_[i - n:i].min()
        rng = hh - ll
        out[i] = 2.0 * (c[i] - (hh + ll) / 2.0) / rng if rng > 1e-12 else 0.0
    return out


def atr(h_, l_, c, n=14):
    tr = np.maximum(h_[1:] - l_[1:], np.maximum(np.abs(h_[1:] - c[:-1]), np.abs(l_[1:] - c[:-1])))
    out = np.full(len(c), np.nan)
    if len(tr) >= n:
        a = np.convolve(tr, np.ones(n) / n, mode="valid")
        out[n:] = a[:len(c) - n]
    return out


def supertrend_dist(o, h_, l_, c, p=10, mult=3.0):
    """(close - ligne SuperTrend)/ATR, causal. Positif = au-dessus (état haussier)."""
    a = atr(h_, l_, c, p)
    hl2 = (h_ + l_) / 2.0
    up = hl2 - mult * a; dn = hl2 + mult * a
    st = np.full(len(c), np.nan)
    cur_up, cur_dn, state = -np.inf, np.inf, 1
    for i in range(1, len(c)):
        if not np.isfinite(a[i]):
            continue
        cur_up = max(up[i], cur_up) if c[i - 1] > cur_up else up[i]
        cur_dn = min(dn[i], cur_dn) if c[i - 1] < cur_dn else dn[i]
        if c[i] > cur_dn:
            state = 1
        elif c[i] < cur_up:
            state = -1
        st[i] = cur_up if state == 1 else cur_dn
    return (c - st) / (a + 1e-12)


def vortex(h_, l_, c, n=14):
    """VI+ - VI-, causal. Positif = pression haussière (a monté)."""
    tr = np.maximum(h_[1:] - l_[1:], np.maximum(np.abs(h_[1:] - c[:-1]), np.abs(l_[1:] - c[:-1])))
    vmp = np.abs(h_[1:] - l_[:-1]); vmm = np.abs(l_[1:] - h_[:-1])
    out = np.full(len(c), np.nan)
    for i in range(n, len(tr) + 1):
        s = tr[i - n:i].sum()
        if s > 1e-12:
            out[i] = (vmp[i - n:i].sum() - vmm[i - n:i].sum()) / s
    return out


def cmf(h_, l_, c, v, n=20):
    """Chaikin Money Flow(20), causal. Positif = accumulation (proxy de hausse)."""
    rng = h_ - l_
    mfm = np.where(rng > 1e-12, ((c - l_) - (h_ - c)) / rng, 0.0)
    mfv = mfm * v
    out = np.full(len(c), np.nan)
    for i in range(n, len(c) + 1):
        sv = v[i - n:i].sum()
        if sv > 1e-12:
            out[i - 1] = mfv[i - n:i].sum() / sv
    return out


def all_signals(d):
    o, h_, l_, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    return {"momentum8": momentum8(c), "rsi14": rsi(c), "dist_sma50": dist_sma(c),
            "donchian20": donchian(c, h_, l_), "supertrend": supertrend_dist(o, h_, l_, c),
            "vortex": vortex(h_, l_, c), "cmf": cmf(h_, l_, c, v)}


# ------------------------------- mesure IC ----------------------------------
def measure(sym, gran, stride):
    d = ac.load(sym, gran)
    c = d["c"]; n = len(c)
    if n < 600:
        return None
    feats = all_signals(d)
    grid = np.arange(120, n - max(HZ), stride)
    res = {}
    for hh in HZ:
        fwd_full = ac.fwd_logret(c, hh)
        fwd = fwd_full[grid]
        for name, arr in feats.items():
            r = ac.ic_across_folds(grid.astype(float), arr[grid], fwd, hh, method="rank")
            if r:
                res[(name, hh)] = (r[0], r[1], r[2])
    return res, feats, grid


def colinearity(feats, grid):
    """Corrélation de RANG entre les features (sur la même grille) — teste si
    SuperTrend/Vortex/CMF/momentum sont des PROXYS du même 'le prix vient de monter'."""
    from scipy.stats import rankdata
    names = ["momentum8", "rsi14", "dist_sma50", "donchian20", "supertrend", "vortex", "cmf"]
    cols = []
    for nm in names:
        cols.append(feats[nm][grid])
    M = np.array(cols)
    mask = np.all(np.isfinite(M), axis=0)
    R = np.array([rankdata(row[mask]) for row in M])
    C = np.corrcoef(R)
    return names, C


def main():
    print("############ RÉPLIQUE INDÉPENDANTE — IC de RANG (t inter-plis, 6 plis purgés) ############")
    print("Signe: +val = 'a récemment monté'.  IC>0 => momentum paie ; IC<0 => réversion.\n")
    plan = [("1H", SYMS_1H, 4), ("1D", SYMS_1D, 1)]
    order = ["momentum8", "rsi14", "dist_sma50", "donchian20", "supertrend", "vortex", "cmf"]
    for gran, syms, stride in plan:
        for sym in syms:
            out = measure(sym, gran, stride)
            if not out:
                continue
            res, feats, grid = out
            print(f"===== {sym} {gran} (n={len(ac.load(sym,gran)['c'])}, pts={len(grid)}) =====")
            print(f"{'feature':<12}" + "".join(f"  h={hh:<3}(t)     " for hh in HZ))
            for nm in order:
                row = f"{nm:<12}"
                for hh in HZ:
                    if (nm, hh) in res:
                        ic, t, nf = res[(nm, hh)]
                        row += f" {ic:+.3f}({t:+4.1f}) "
                    else:
                        row += f" {'--':>11} "
                print(row)
            # colinéarité
            names, C = colinearity(feats, grid)
            print("  -- corrélation de RANG entre signaux (colinéarité) --")
            print("            " + "".join(f"{n[:7]:>8}" for n in names))
            for i, nm in enumerate(names):
                print(f"  {nm[:9]:<9} " + "".join(f"{C[i,j]:+7.2f}" for j in range(len(names))))
            print()


if __name__ == "__main__":
    main()
