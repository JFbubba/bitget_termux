"""
audit_core.py — MACHINERIE IC INDÉPENDANTE, écrite de zéro.
Ne réutilise AUCUN module du dépôt (ni candles_history, ni gate_lib, ni signals_*).
Lecture seule : lit uniquement les fichiers JSON de data_history/.
numpy + scipy.stats purs. Single-thread.
"""
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import norm, rankdata

DATA = Path("/root/bitget_termux_repo/data_history")


# ----------------------------------------------------------------------------
# Chargement INDÉPENDANT (je relis le JSON brut, je trie et déduplique moi-même)
# ----------------------------------------------------------------------------
def load(sym, gran):
    """Retourne dict o,h,l,c,v,ts en numpy float64, trié par ts, dédupliqué.
    Format fichier : liste de [ts,o,h,l,c,v]."""
    p = DATA / f"{sym}_{gran}.json"
    raw = json.loads(p.read_text())
    # tri + dédup par ts (garde la DERNIÈRE occurrence rencontrée après tri stable)
    rows = [r for r in raw if len(r) >= 6]
    rows.sort(key=lambda r: r[0])
    ts, seen = [], {}
    for r in rows:
        seen[int(r[0])] = r  # dernière valeur pour un ts donné
    keys = sorted(seen)
    a = np.array([[seen[k][1], seen[k][2], seen[k][3], seen[k][4], seen[k][5]] for k in keys],
                 dtype=float)
    return {"ts": np.array(keys, dtype=np.int64),
            "o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3], "v": a[:, 4],
            "n_raw": len(raw), "n_dedup": len(keys)}


def integrity(sym, gran):
    """Vérifie tri croissant, doublons, régularité du pas temporel."""
    raw = json.loads((DATA / f"{sym}_{gran}.json").read_text())
    ts_file = np.array([int(r[0]) for r in raw], dtype=np.int64)
    already_sorted = bool(np.all(np.diff(ts_file) > 0))
    n_dupes = len(ts_file) - len(np.unique(ts_file))
    d = load(sym, gran)
    dts = np.diff(d["ts"])
    step = int(np.median(dts)) if len(dts) else 0
    n_gaps = int(np.sum(dts != step))
    return {"n_raw": len(raw), "already_sorted_in_file": already_sorted,
            "n_dupes": n_dupes, "median_step_ms": step,
            "n_irregular_steps": n_gaps, "n_after_dedup": d["n_dedup"]}


# ----------------------------------------------------------------------------
# IC : mes propres implémentations (deux méthodes indépendantes)
# ----------------------------------------------------------------------------
def _pearson(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 3 or np.std(x) < 1e-15 or np.std(y) < 1e-15:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def rank_ic(x, y):
    """Spearman = Pearson sur les RANGS. Implémenté à la main (rankdata + corrcoef)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 8 or np.std(x) < 1e-15 or np.std(y) < 1e-15:
        return np.nan
    return _pearson(rankdata(x), rankdata(y))


def pearson_ic(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    return _pearson(x[m], y[m])


# ----------------------------------------------------------------------------
# Plis temporels NON CHEVAUCHANTS + purge (ma version, indépendante)
# ----------------------------------------------------------------------------
def purged_folds(bar_idx, h, n_folds=6):
    """bar_idx : indices de barre (croissants) des points évalués.
    Découpe l'AXE TEMPOREL en n_folds blocs contigus ; dans chaque bloc on garde
    des points espacés d'AU MOINS h barres (labels non chevauchants) et on purge
    les h premières barres du bloc (frontière). Renvoie une liste de tableaux
    d'indices (dans l'espace de bar_idx)."""
    bar_idx = np.asarray(bar_idx)
    lo, hi = bar_idx.min(), bar_idx.max()
    edges = [lo + (hi - lo) * k / n_folds for k in range(n_folds + 1)]
    folds = []
    for k in range(n_folds):
        sel = (bar_idx >= edges[k] + h) & (bar_idx < edges[k + 1])
        keep, last = [], -10**18
        for j in np.where(sel)[0]:
            if bar_idx[j] >= last + h:
                keep.append(j)
                last = bar_idx[j]
        folds.append(np.array(keep, dtype=int))
    return folds


def ic_across_folds(bar_idx, feat, fwd, h, n_folds=6, min_per_fold=25, method="rank"):
    """IC par pli non chevauchant + t-stat inter-plis. method: 'rank' ou 'pearson'.
    Retourne (ic_moyen, t, n_plis_valides, liste_ic)."""
    bar_idx = np.asarray(bar_idx); feat = np.asarray(feat, float); fwd = np.asarray(fwd, float)
    m = np.isfinite(feat) & np.isfinite(fwd)
    bi, ft, fw = bar_idx[m], feat[m], fwd[m]
    if len(bi) < n_folds * min_per_fold:
        return None
    fn = rank_ic if method == "rank" else pearson_ic
    ics = []
    for keep in purged_folds(bi, h, n_folds):
        if len(keep) < min_per_fold or np.std(ft[keep]) < 1e-15:
            continue
        v = fn(ft[keep], fw[keep])
        if np.isfinite(v):
            ics.append(v)
    if len(ics) < 3:
        return None
    ics = np.array(ics, float)
    se = ics.std(ddof=1) / math.sqrt(len(ics))
    t = float(ics.mean() / se) if se > 1e-15 else 0.0
    return float(ics.mean()), t, len(ics), ics.tolist()


def fwd_logret(c, h):
    """Rendement log forward h barres : fwd[t] = log(c[t+h]/c[t]). NaN au-delà."""
    c = np.asarray(c, float)
    out = np.full(len(c), np.nan)
    out[:len(c) - h] = np.log(c[h:] / c[:len(c) - h])
    return out


# ----------------------------------------------------------------------------
# Erreurs-types robustes à l'autocorrélation (Newey-West / HAC) & Deflated Sharpe
# Ratio EXACT (Bailey & López de Prado 2014). Ajout 18/07 — corrige deux angles
# morts de mesure du labo confirmés contre la littérature :
#   (1) le t = moyenne/(σ/√n) suppose des jours i.i.d. ; les rendements d'une
#       stratégie sont AUTOCORRÉLÉS (positions persistantes) -> σ sous-estimée,
#       t GONFLÉ. Fix standard : erreur-type HAC de Newey-West (noyau de Bartlett).
#   (2) `t > √(2·ln N)` n'était qu'une APPROXIMATION du max attendu. La vraie DSR
#       déflate le Sharpe par la dispersion cross-essais des Sharpe (théorème des
#       fausses stratégies) ET corrige la non-normalité (skew/kurtosis).
# ----------------------------------------------------------------------------
_EULER_MASCHERONI = 0.5772156649015329


def nw_lag(n):
    """Fenêtre de troncature Newey-West (règle plug-in 1994) : floor(4·(n/100)^(2/9))."""
    return int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


def nw_tstat(x, lag=None):
    """t-stat de la MOYENNE de x robuste hétéroscédasticité+autocorrélation (HAC),
    noyau de Bartlett (Newey-West 1987). H0 : moyenne = 0. Le noyau de Bartlett
    garantit une variance de long terme ≥ 0. Retourne
    dict(mean, se_ols, se_nw, t_ols, t_nw, lag, n) ou None si n < 20."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    n = len(x)
    if n < 20:
        return None
    mu = float(np.mean(x))
    xm = x - mu
    g0 = float(np.dot(xm, xm) / n)                  # autocovariance lag 0 = variance
    if g0 < 1e-24:
        return None
    L = nw_lag(n) if lag is None else int(lag)
    L = max(0, min(L, n - 1))
    s = g0
    for j in range(1, L + 1):
        w = 1.0 - j / (L + 1.0)                      # poids de Bartlett
        gj = float(np.dot(xm[j:], xm[:n - j]) / n)   # autocovariance lag j
        s += 2.0 * w * gj
    s = max(s, 1e-24)
    se_ols = math.sqrt(g0 / n)
    se_nw = math.sqrt(s / n)
    return dict(mean=mu, se_ols=se_ols, se_nw=se_nw,
                t_ols=mu / se_ols, t_nw=mu / se_nw, lag=L, n=n)


def expected_max_sharpe(var_sr, n_trials):
    """SR maximal ATTENDU sous H0 (théorème des fausses stratégies, Bailey & LdP) :
        SR0 = √V[SR]·[(1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e))]
    var_sr = variance des Sharpe (MÊME unité, typiquement PAR BARRE) sur les N essais.
    Renvoie SR0 dans cette même unité. 0 si N ≤ 1 ou var_sr ≤ 0."""
    N = int(n_trials)
    if N <= 1 or var_sr <= 0:
        return 0.0
    g = _EULER_MASCHERONI
    return math.sqrt(var_sr) * ((1 - g) * norm.ppf(1 - 1.0 / N)
                                + g * norm.ppf(1 - 1.0 / (N * math.e)))


def probabilistic_sharpe(returns, sr_benchmark=0.0):
    """PSR(SR*) — probabilité que le VRAI Sharpe (par barre) dépasse SR* (Bailey & LdP),
    corrigée de la non-normalité (skew, kurtosis). SR* est PAR BARRE (non annualisé).
    Retourne dict(psr, sr_bar, skew, kurt, n) ou None si n < 20."""
    r = np.asarray(returns, float); r = r[np.isfinite(r)]
    n = len(r)
    if n < 20:
        return None
    mu = float(np.mean(r)); sd = float(np.std(r, ddof=1))
    if sd < 1e-24:
        return None
    sr = mu / sd                                    # Sharpe PAR BARRE (non annualisé)
    z = (r - mu) / sd
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))                   # kurtosis NON excédentaire (normale = 3)
    denom = math.sqrt(max(1e-24, 1 - skew * sr + ((kurt - 1) / 4.0) * sr ** 2))
    psr = float(norm.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / denom))
    return dict(psr=psr, sr_bar=sr, skew=skew, kurt=kurt, n=n)


def deflated_sharpe(returns, sr_trials=None, var_sr=None, n_trials=None):
    """DSR EXACT — PSR de la stratégie SÉLECTIONNÉE évaluée au SR-max attendu sous H0.
    returns   : rendements PAR BARRE de la stratégie retenue (série complète).
    sr_trials : Sharpe PAR BARRE de TOUS les essais explorés (donne V[SR] et N) — ou
                passer directement var_sr ET n_trials.
    DSR > 0.95 ⇒ significatif à 5 % APRÈS correction de sélection multiple + non-normalité.
    Retourne dict(dsr, sr0, sr_bar, skew, kurt, var_sr, n_trials, n)."""
    if sr_trials is not None:
        srt = np.asarray(sr_trials, float); srt = srt[np.isfinite(srt)]
        if n_trials is None:
            n_trials = len(srt)
        if var_sr is None:
            var_sr = float(np.var(srt, ddof=1)) if len(srt) > 1 else 0.0
    if var_sr is None or n_trials is None:
        raise ValueError("deflated_sharpe : fournir sr_trials, ou (var_sr ET n_trials)")
    sr0 = expected_max_sharpe(var_sr, n_trials)
    base = probabilistic_sharpe(returns, sr_benchmark=sr0)
    if base is None:
        return None
    base["dsr"] = base.pop("psr")
    base.update(sr0=sr0, var_sr=float(var_sr), n_trials=int(n_trials))
    return base
