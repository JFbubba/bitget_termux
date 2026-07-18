"""
cross_sectional_1d.py — TEST 1D CIBLÉ : momentum cross-sectionnel canonique (loose end 18/07).

Le joint BASE à 1D h=1 avait un IC +0,018 battant le shuffle (non reproduit par V2, non
déflaté). On teste ici la forme CANONIQUE du momentum cross-sectionnel crypto (Dobrynskaya /
Jegadeesh-Titman) : chaque jour, trier TOUT l'univers par rendement de FORMATION (skip-1,
lookback L), portefeuille LONG top-k / SHORT bottom-k équipondéré, rebalance quotidien, NET
DE FRAIS. C'est l'ENSEMBLE cross-actifs (pas un indicateur isolé). On balaie L et k (déflaté),
crible de frais taker->maker->0, contrôle SHUFFLE (permutation cross-sectionnelle = null).

Signe : rendement du portefeuille momentum (long gagnants − short perdants). Positif =
momentum paie ; négatif = REVERSAL (les gagnants reviennent). Lecture seule, numpy pur.
"""
import glob
import math
import os

import numpy as np

import audit_core as ac

# Univers CRYPTO auto-découvert dans data_history (hors actions/métaux/token exchange) —
# élargi pour le test de PUISSANCE du momentum cross-sectionnel.
_EXCLUDE = {"AAPLUSDT", "NVDAUSDT", "TSLAUSDT", "MSTRUSDT", "COINUSDT", "QQQUSDT",
            "SPYUSDT", "XAUUSDT", "XAGUSDT", "BGBUSDT"}


def _discover_crypto():
    syms = []
    for p in glob.glob("/root/bitget_termux_repo/data_history/*_1D.json"):
        b = os.path.basename(p)
        if b.startswith("FUNDING_"):
            continue
        s = b.replace("_1D.json", "")
        if s not in _EXCLUDE:
            syms.append(s)
    return sorted(syms)


CRYPTO = _discover_crypto()
LOOKBACKS = [7, 14, 21]          # jours de formation (skip-1)
KS = [3, 5, 8]                    # nb de coins par jambe (univers élargi -> jambes plus larges)
SKIP = 1
FEES_BPS = [6.0, 1.0, 0.0]       # par côté : taker 6 · maker ~1 · brut 0
BARS_PER_YEAR = 365


def load_all():
    data = {}
    for s in CRYPTO:
        try:
            d = ac.load(s, "1D")
            if len(d["c"]) > 60:
                data[s] = (d["ts"].astype(np.int64), d["c"].astype(float))
        except Exception:
            pass
    return data


def formation(c, L):
    out = np.full(len(c), np.nan)
    for i in range(L + SKIP, len(c)):
        a, b = c[i - L - SKIP], c[i - SKIP]
        if a > 0 and b > 0:
            out[i] = math.log(b / a)
    return out


def fwd1(c):
    out = np.full(len(c), np.nan)
    out[:-1] = np.log(c[1:] / c[:-1])
    return out


def build_panels(data):
    """Matrices (dates × coins) alignées sur l'union des ts : formation par L, et fwd 1j."""
    all_ts = sorted(set().union(*[set(ts.tolist()) for ts, _ in data.values()]))
    tindex = {t: i for i, t in enumerate(all_ts)}
    D, N = len(all_ts), len(data)
    coins = list(data.keys())
    fwd = np.full((D, N), np.nan)
    forms = {L: np.full((D, N), np.nan) for L in LOOKBACKS}
    for j, s in enumerate(coins):
        ts, c = data[s]
        rows = np.array([tindex[int(t)] for t in ts])
        fwd[rows, j] = fwd1(c)
        for L in LOOKBACKS:
            forms[L][rows, j] = formation(c, L)
    return coins, np.array(all_ts), fwd, forms


def portfolio(form, fwd, k, shuffle_seed=None):
    """Renvoie la série quotidienne (gross_ret, weights) du LS momentum top-k/bottom-k."""
    D, N = form.shape
    rets, W = [], np.zeros(N)
    weights_hist = []
    rng = np.random.default_rng(shuffle_seed) if shuffle_seed is not None else None
    for d in range(D):
        avail = np.where(np.isfinite(form[d]) & np.isfinite(fwd[d]))[0]
        w = np.zeros(N)
        if len(avail) >= 2 * k:
            fvals = form[d, avail].copy()
            if rng is not None:
                fvals = rng.permutation(fvals)     # null : casse le lien tri->coin
            order = avail[np.argsort(fvals)]
            lo, hi = order[:k], order[-k:]
            w[hi] = 1.0 / k                          # long gagnants
            w[lo] = -1.0 / k                         # short perdants
        gross = float(np.nansum(w * fwd[d]))
        rets.append(gross)
        weights_hist.append(w)
    return np.array(rets), np.array(weights_hist)


def net_series(gross, weights, fee_side):
    turn = np.zeros(len(gross))
    for d in range(1, len(weights)):
        turn[d] = np.sum(np.abs(weights[d] - weights[d - 1]))
    return gross - (fee_side / 1e4) * turn


def stats(net):
    m = net[np.abs(net) > 0]         # jours actifs
    if len(m) < 30:
        return None
    mu, sd = float(np.mean(net)), float(np.std(net))
    sharpe = mu / sd * math.sqrt(BARS_PER_YEAR) if sd > 1e-12 else 0.0
    t = mu / (sd / math.sqrt(len(net))) if sd > 1e-12 else 0.0
    nw = ac.nw_tstat(net)            # t HAC (robuste à l'autocorrélation des rendements)
    return dict(sharpe=round(sharpe, 3), mean_bps=round(mu * 1e4, 3),
                t=round(t, 2), t_nw=round(nw["t_nw"], 2) if nw else float("nan"),
                nw_lag=(nw["lag"] if nw else None),
                sr_bar=(mu / sd if sd > 1e-12 else 0.0),   # Sharpe PAR BARRE (pour la DSR)
                n=int(len(net)), n_active=int(len(m)))


def main():
    data = load_all()
    print(f"TEST 1D cross-sectionnel canonique — {len(data)} cryptos · skip-{SKIP} · "
          f"long-short top-k/bottom-k · rebalance quotidien\n", flush=True)
    coins, ts, fwd, forms = build_panels(data)
    print(f"{'L':>3}{'k':>3}{'gross_bps':>11}{'sharpe@0':>10}{'t@0':>7}"
          + "".join(f"{'net@'+str(int(f)):>9}" for f in FEES_BPS)
          + f"{'tNW@1':>8}{'shuf_sh':>9}{'shuf_bps':>10}")
    print("-" * 92)
    trials = []
    for L in LOOKBACKS:
        for k in KS:
            gross, W = portfolio(forms[L], fwd, k)
            s0 = stats(gross)
            if not s0:
                continue
            nets = {f: net_series(gross, W, f) for f in FEES_BPS}
            snets = {f: stats(nets[f]) for f in FEES_BPS}
            gsh, Wsh = portfolio(forms[L], fwd, k, shuffle_seed=1000 + L * 10 + k)
            ssh = stats(gsh)
            tnw1 = snets[1.0]["t_nw"] if snets[1.0] else float("nan")
            row = (f"{L:>3}{k:>3}{s0['mean_bps']:>11.3f}{s0['sharpe']:>10.3f}{s0['t']:>7.2f}"
                   + "".join(f"{(snets[f]['mean_bps'] if snets[f] else float('nan')):>9.3f}" for f in FEES_BPS)
                   + f"{tnw1:>8.2f}{(ssh['sharpe'] if ssh else float('nan')):>9.3f}{(ssh['mean_bps'] if ssh else float('nan')):>10.3f}")
            print(row, flush=True)
            trials.append(dict(L=L, k=k, gross=s0, nets=snets, shuffle=ssh, net1=nets[1.0]))
    print("\n" + "=" * 92)
    if not trials:
        print("Aucun essai exploitable."); return
    def net_maker(tr): return tr["nets"].get(1.0)
    scored = [(tr, net_maker(tr)) for tr in trials if net_maker(tr)]
    # (a) garde-fou approximatif CONSERVÉ pour mémoire : max attendu du t sous H0 ~ sqrt(2·ln N)
    N = len(scored) * 2                              # L×k×signe (momentum OU reversal)
    defl_t = math.sqrt(2 * math.log(N))
    # (b) t HONNÊTE = HAC (Newey-West) : robuste à l'autocorrélation des rendements de stratégie
    best = max(scored, key=lambda x: abs(x[1]["mean_bps"]), default=None)
    survivors = [tr for tr, s in scored
                 if abs(s["t_nw"]) > defl_t and abs(s["mean_bps"]) > 0
                 and (tr["shuffle"] is None or abs(s["sharpe"]) > abs(tr["shuffle"]["sharpe"]) + 0.3)]
    d = None
    print(f"Déflation (approx.) : {N} essais -> barre ~ sqrt(2·ln N) = {defl_t:.2f}, comparée au t_NW (HAC honnête)")
    if best:
        b, bs = best
        sign = "MOMENTUM (long gagnants paie)" if bs["mean_bps"] > 0 else "REVERSAL (gagnants reviennent)"
        print(f"Meilleur (net maker 1bps) : L={b['L']} k={b['k']} -> {bs['mean_bps']:+.3f} bps/j "
              f"Sharpe {bs['sharpe']:+.2f}  t_naif={bs['t']:+.2f}  t_NW={bs['t_nw']:+.2f} (lag {bs['nw_lag']})  [{sign}]")
        # (c) DSR EXACTE (Bailey & LdP) : déflate par la dispersion cross-essais des Sharpe + non-normalité.
        # V[SR] = dispersion OBSERVÉE des essais réellement lancés (méthode canonique, non symétrisée) ;
        # N compté ×2 pour la liberté momentum-OU-reversal (conservateur sur la sélection multiple).
        srs = [s["sr_bar"] for _, s in scored]
        d = ac.deflated_sharpe(best[0]["net1"], sr_trials=srs, n_trials=len(srs) * 2)
        if d:
            verdict = "SIGNIFICATIF (>0.95)" if d["dsr"] > 0.95 else "NON significatif (<0.95)"
            print(f"DSR EXACTE (Deflated Sharpe, Bailey & LdP) : {d['dsr']:.4f}  [SR0={d['sr0']:.4f} "
                  f"sr_bar={d['sr_bar']:.4f} skew={d['skew']:.2f} kurt={d['kurt']:.2f} N={d['n_trials']}] -> {verdict}")
    print(f"Essais survivant (|t_NW|>{defl_t:.2f} ET net>0 maker ET bat shuffle) : {len(survivors)}")
    for tr in survivors:
        s = tr["nets"][1.0]
        print(f"    L={tr['L']} k={tr['k']} : {s['mean_bps']:+.3f} bps/j Sharpe {s['sharpe']:+.2f} "
              f"t_naif={s['t']:+.2f} t_NW={s['t_nw']:+.2f} (shuffle Sharpe {tr['shuffle']['sharpe'] if tr['shuffle'] else None})")
    dsr_ok = bool(d and d["dsr"] > 0.95)
    if dsr_ok and survivors:
        print("\nVERDICT : PISTE 1D survit à la DSR EXACTE (>0.95) + HAC + shuffle -> valider OOS (walk-forward)")
        print("  sur période RÉSERVÉE avant toute promotion. À rapporter.")
    elif survivors:
        print(f"\nVERDICT : le t_NW passe la barre approx. √(2·ln N), MAIS la DSR EXACTE ({d['dsr']:.2f}<0.95) REJETTE :")
        print("  l'edge in-sample s'explique par la sélection multiple + la NON-NORMALITÉ (kurtosis "
              f"{d['kurt']:.1f}), pas par un vrai Sharpe. La barre √(2·ln N) était trop indulgente. -> trancher au walk-forward.")
    else:
        print("\nVERDICT : le momentum cross-sectionnel 1D canonique NE SURVIT PAS à la déflation")
        print("  net de frais maker SOUS t HAC. La curiosité 1D BASE était un artefact non robuste. Loose end CLOS.")
    print("=" * 92)


if __name__ == "__main__":
    main()
