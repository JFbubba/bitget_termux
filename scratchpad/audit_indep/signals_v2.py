"""
signals_v2.py — constituants CORRIGÉS suite à l'audit de complétude (ERR-014, 18/07).

Corrections vs signals_indep / global_interaction (specs canoniques vérifiées) :
  1. supertrend : ATR de WILDER (RMA) au lieu de SMA (écart canonique réel — TradingView).
  2. momentum cross-sectionnel : SKIP-1 + formation paramétrable. Sans skip, le rang du
     rendement récent MÉLANGE momentum et reversal court terme (Jegadeesh-Titman : skip-1
     pour isoler ; Dobrynskaya crypto : momentum ~2 sem, FLIP reversal > 1 mois). Aux TF
     intraday la version d'origine capte du REVERSAL (signe inversé) — d'où « pas de momentum ».
  3. lead-lag SEESAW : rendement retardé du MENEUR (BTC/ETH) comme prédicteur d'une alt
     (signe négatif attendu ; edge cross-actif le mieux prouvé net de frais — recherche B).

Réutilise les signaux DÉJÀ canoniques de signals_indep (rsi/dist_sma/donchian/vortex/cmf/
momentum8). Causal, numpy pur.
"""
import numpy as np

import signals_indep as si


def wilder_atr(h_, l_, c, n=14):
    """ATR de Wilder (RMA) — canonique pour SuperTrend. Causal."""
    tr = np.maximum(h_[1:] - l_[1:], np.maximum(np.abs(h_[1:] - c[:-1]), np.abs(l_[1:] - c[:-1])))
    atr = np.full(len(c), np.nan)
    if len(tr) < n:
        return atr
    a = float(tr[:n].mean())
    atr[n] = a
    for i in range(n, len(tr)):
        a = (a * (n - 1) + tr[i]) / n
        atr[i + 1] = a
    return atr


def supertrend_wilder(o, h_, l_, c, p=10, mult=3.0):
    """SuperTrend canonique (ATR Wilder). (close − ligne)/ATR, causal."""
    a = wilder_atr(h_, l_, c, p)
    hl2 = (h_ + l_) / 2.0
    up = hl2 - mult * a
    dn = hl2 + mult * a
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


def formation_ret(c, lookback=14, skip=1):
    """Rendement de FORMATION [t−lookback−skip .. t−skip] — SKIP-1 (isole le momentum
    du reversal court terme). Positif = a monté sur la fenêtre de formation. Causal."""
    out = np.full(len(c), np.nan)
    lo = lookback + skip
    for i in range(lo, len(c)):
        denom = c[i - lookback - skip]
        if denom > 0 and c[i - skip] > 0:
            out[i] = np.log(c[i - skip] / denom)
    return out


def leader_ret(c_leader, lookback=4):
    """Rendement récent du MENEUR sur `lookback` barres (aligné par index de barre).
    Prédicteur lead-lag (signe négatif attendu = seesaw). Causal."""
    out = np.full(len(c_leader), np.nan)
    if lookback < len(c_leader):
        out[lookback:] = np.log(c_leader[lookback:] / c_leader[:-lookback])
    return out


def price_signals_v2(d):
    """7 signaux de prix, supertrend CORRIGÉ (Wilder), le reste inchangé (déjà canonique)."""
    o, h_, l_, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    return {"momentum8": si.momentum8(c), "rsi14": si.rsi(c), "dist_sma50": si.dist_sma(c),
            "donchian20": si.donchian(c, h_, l_), "supertrend": supertrend_wilder(o, h_, l_, c),
            "vortex": si.vortex(h_, l_, c), "cmf": si.cmf(h_, l_, c, v)}


if __name__ == "__main__":
    import audit_core as ac
    d = ac.load("BTCUSDT", "1D")
    c = d["c"]
    s_old = si.supertrend_dist(d["o"], d["h"], d["l"], c)
    s_new = supertrend_wilder(d["o"], d["h"], d["l"], c)
    m = np.isfinite(s_old) & np.isfinite(s_new)
    print(f"SuperTrend SMA vs Wilder — corr={np.corrcoef(s_old[m], s_new[m])[0,1]:.4f} "
          f"écart méd |Δ|={np.median(np.abs(s_old[m]-s_new[m])):.4f} (sur {m.sum()} barres)")
    fr = formation_ret(c, lookback=14, skip=1)
    ll = leader_ret(c, lookback=4)
    print(f"formation_ret(14,skip1) : couv={np.mean(np.isfinite(fr))*100:.0f}% "
          f"méd={np.nanmedian(fr):+.4f} | leader_ret(4) : couv={np.mean(np.isfinite(ll))*100:.0f}%")
