"""
evolution.py — sep-CMA-ES : optimisation dérivée-libre (Ros & Hansen 2008).

Adopté de TRINITY (ICLR 2026, arXiv:2512.04695) : les auteurs montrent que le
*separable* CMA-ES bat RL / grid / random search dans LE régime qui est aussi le
nôtre — objectif SCALAIRE BRUITÉ (ex. score de backtest), AUCUN gradient,
évaluations COÛTEUSES (un backtest par essai), paramètres faiblement corrélés.

On n'emprunte QUE l'optimiseur (pas l'orchestration de LLM frontières de TRINITY,
contraire à notre cerveau déterministe). Couverture mémoire diagonale -> léger et
robuste en haute dimension. SAFE : calcul pur (numpy), aucune I/O, aucun ordre.

⚠️ Honnêteté : une recherche évolutionnaire sur UN backtest AMPLIFIE le
surapprentissage. Toute sortie reste soumise au garde-fou PBO / walk-forward.
"""

import numpy as np


def sep_cma_es(f, x0, sigma0=0.3, bounds=None, popsize=None, max_gen=60,
               seed=0, maximize=False):
    """sep-CMA-ES (covariance diagonale). Optimise `f` (scalaire) sans gradient.

    Retourne (x_best, f_best, history). `bounds` = (lo, hi) (listes/arrays) ou None.
    """
    rng = np.random.default_rng(seed)
    x0 = np.asarray(x0, dtype=float)
    n = len(x0)
    sign = -1.0 if maximize else 1.0            # on minimise sign·f
    lam = int(popsize or (4 + int(3 * np.log(max(n, 2)))))
    mu = max(1, lam // 2)
    w = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
    w = w / w.sum()
    mueff = 1.0 / np.sum(w ** 2)
    cc = (1 + 1 / n + mueff / n) / (n + 4 + 2 * mueff / n)
    cs = (mueff + 2) / (n + mueff + 5)
    c1 = 2 / ((n + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((n + 2) ** 2 + mueff))
    # facteur « separable » (Ros & Hansen) : accélère l'adaptation de la diagonale
    c1 *= (n + 2) / 3.0
    cmu *= (n + 2) / 3.0
    damps = 1 + 2 * max(0.0, np.sqrt((mueff - 1) / (n + 1)) - 1) + cs
    chiN = np.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))

    lo = np.asarray(bounds[0], float) if bounds else None
    hi = np.asarray(bounds[1], float) if bounds else None
    m = x0.copy()
    sigma = float(sigma0)
    C = np.ones(n)          # variances diagonales
    ps = np.zeros(n)
    pc = np.zeros(n)
    best_x, best_f, hist = m.copy(), np.inf, []

    for gen in range(max_gen):
        D = np.sqrt(C)
        Z = rng.standard_normal((lam, n))
        X = m + sigma * Z * D
        if bounds:
            X = np.clip(X, lo, hi)
        fs = np.array([sign * float(f(x)) for x in X])
        order = np.argsort(fs)
        if fs[order[0]] < best_f:
            best_f, best_x = fs[order[0]], X[order[0]].copy()
        sel = order[:mu]
        Xsel, Zsel = X[sel], Z[sel]
        m_old = m.copy()
        m = (w[:, None] * Xsel).sum(0)
        zmean = (w[:, None] * Zsel).sum(0)
        ps = (1 - cs) * ps + np.sqrt(cs * (2 - cs) * mueff) * zmean
        ps_norm = np.linalg.norm(ps)
        hsig = 1.0 if ps_norm / np.sqrt(1 - (1 - cs) ** (2 * (gen + 1))) / chiN \
            < 1.4 + 2 / (n + 1) else 0.0
        pc = (1 - cc) * pc + hsig * np.sqrt(cc * (2 - cc) * mueff) * (m - m_old) / sigma
        artmp = (Xsel - m_old) / sigma
        C = ((1 - c1 - cmu) * C
             + c1 * (pc ** 2 + (1 - hsig) * cc * (2 - cc) * C)
             + cmu * (w[:, None] * artmp ** 2).sum(0))
        sigma *= np.exp((cs / damps) * (ps_norm / chiN - 1))
        hist.append(sign * best_f)
        if sigma < 1e-12 or not np.isfinite(sigma):
            break
    return best_x, sign * best_f, hist
