"""
cross_sectional_1d_validate.py — STRESS-TEST de la piste 1D (loose end, 18/07).

La piste = momentum cross-sectionnel 1D (L=21, long-short) survit shuffle+déflation+maker.
Avant toute promotion, trois juges décisifs :
  1. HOLDOUT TEMPOREL : l'edge tient-il sur la 2e moitié (OOS) ? (overfit meurt ici)
  2. EXTENSION LOOKBACK : culmine vers 14-30j (vrai momentum Dobrynskaya) ou monte encore
     à 45-60j (= trend/beta déguisé — leçon ERR-014 alpha-vs-beta) ?
  3. ATTRIBUTION DES JAMBES : long-only vs short-only — une seule jambe = beta capturé.
Lecture seule, numpy pur. Réutilise cross_sectional_1d.
"""
import math

import numpy as np

import cross_sectional_1d as cs


def panel_for_L(data, L):
    all_ts = sorted(set().union(*[set(ts.tolist()) for ts, _ in data.values()]))
    tindex = {t: i for i, t in enumerate(all_ts)}
    D, N = len(all_ts), len(data)
    fwd = np.full((D, N), np.nan); form = np.full((D, N), np.nan)
    for j, (s, (ts, c)) in enumerate(data.items()):
        rows = np.array([tindex[int(t)] for t in ts])
        fwd[rows, j] = cs.fwd1(c); form[rows, j] = cs.formation(c, L)
    return np.array(all_ts), fwd, form


def mt(net, mask=None):
    x = net if mask is None else net[mask]
    x = x[np.isfinite(x)]
    if len(x) < 20:
        return (float("nan"), float("nan"), float("nan"))
    mu, sd = float(np.mean(x)), float(np.std(x))
    t = mu / (sd / math.sqrt(len(x))) if sd > 1e-12 else 0.0
    sh = mu / sd * math.sqrt(365) if sd > 1e-12 else 0.0
    return round(mu * 1e4, 2), round(t, 2), round(sh, 2)


def legs(form, fwd, k):
    """Rendements quotidiens des jambes LONG (top-k) et SHORT (−bottom-k) séparément + poids."""
    D, N = form.shape
    lr, sr = np.zeros(D), np.zeros(D)
    WL, WS = np.zeros((D, N)), np.zeros((D, N))
    for d in range(D):
        av = np.where(np.isfinite(form[d]) & np.isfinite(fwd[d]))[0]
        if len(av) >= 2 * k:
            order = av[np.argsort(form[d, av])]
            lo, hi = order[:k], order[-k:]
            WL[d, hi] = 1.0 / k; WS[d, lo] = -1.0 / k
            lr[d] = float(np.nansum(WL[d] * fwd[d]))
            sr[d] = float(np.nansum(WS[d] * fwd[d]))
    return lr, sr, WL, WS


def main():
    data = cs.load_all()
    print(f"STRESS-TEST piste 1D — {len(data)} cryptos · net maker 1 bps · k=2\n")

    print("1) LOOKBACK sweep + HOLDOUT TEMPOREL (mean bps/j, t)  [full | 1re moitié | 2e moitié OOS]")
    print(f"{'L':>4}{'full_bps':>10}{'full_t':>8}   {'H1_bps':>8}{'H1_t':>7}   {'H2_bps':>8}{'H2_t':>7}")
    for L in [10, 14, 21, 30, 45, 60]:
        ts, fwd, form = panel_for_L(data, L)
        gross, W = cs.portfolio(form, fwd, 2)
        net = cs.net_series(gross, W, 1.0)
        D = len(net); half = D // 2
        f_ = mt(net); h1 = mt(net, np.arange(D) < half); h2 = mt(net, np.arange(D) >= half)
        print(f"{L:>4}{f_[0]:>10.2f}{f_[1]:>8.2f}   {h1[0]:>8.2f}{h1[1]:>7.2f}   {h2[0]:>8.2f}{h2[1]:>7.2f}")

    print("\n2) ATTRIBUTION DES JAMBES (L=21, k=2, net maker 1bps) — long vs short vs combiné")
    ts, fwd, form = panel_for_L(data, 21)
    lr, sr, WL, WS = legs(form, fwd, 2)
    nl = cs.net_series(lr, WL, 1.0); ns = cs.net_series(sr, WS, 1.0)
    gross, W = cs.portfolio(form, fwd, 2); nc = cs.net_series(gross, W, 1.0)
    print(f"   LONG-only  : {mt(nl)[0]:+.2f} bps/j  t={mt(nl)[1]:+.2f}  Sharpe={mt(nl)[2]:+.2f}")
    print(f"   SHORT-only : {mt(ns)[0]:+.2f} bps/j  t={mt(ns)[1]:+.2f}  Sharpe={mt(ns)[2]:+.2f}")
    print(f"   COMBINÉ LS : {mt(nc)[0]:+.2f} bps/j  t={mt(nc)[1]:+.2f}  Sharpe={mt(nc)[2]:+.2f}")

    print("\n3) BENCHMARK BETA — buy&hold équipondéré de l'univers (le LS doit être NEUTRE au marché)")
    ew = np.nanmean(fwd, axis=1)
    print(f"   univers B&H équipondéré : {mt(ew)[0]:+.2f} bps/j  Sharpe={mt(ew)[2]:+.2f}")
    corr_beta = np.corrcoef(np.nan_to_num(nc), np.nan_to_num(ew))[0, 1]
    print(f"   corr(LS, marché) = {corr_beta:+.3f}  (proche 0 = vraiment market-neutral / alpha ;"
          f" élevé = beta déguisé)")

    print("\n" + "=" * 80)
    print("Lecture : si H2 (OOS) s'effondre -> overfit. Si l'edge MONTE encore à L=45-60 -> trend/beta,")
    print("pas le momentum ~2-3 sem de la littérature. Si SHORT-only porte tout ou corr(LS,marché) élevé")
    print("-> beta, pas alpha. Les trois doivent tenir pour parler d'edge cross-sectionnel réel.")
    print("=" * 80)


if __name__ == "__main__":
    main()
