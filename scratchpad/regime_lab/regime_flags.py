"""
regime_flags.py — flags de régime STRICTEMENT CAUSAUX (labo régime, lecture seule).

Motivation §102 : l'edge du banc s'affaisse sur les plis récents — un virage de
régime non détecté. Question : un flag de régime CAUSAL a-t-il de la valeur ?

Causalité — règles non négociables :
  - HMM (hmmlearn) : ajusté sur la fenêtre TRAIN seule ; le décodage utilise le
    FILTRAGE FORWARD pas-à-pas (récurrence manuelle alpha_t ∝ (alpha_{t-1}·A)·b_t)
    -> P(état_t | observations ≤ t). JAMAIS model.predict / predict_proba /
    Viterbi (forward-backward = regard en avant).
  - ruptures (Pelt rbf) : détection sur fenêtre GLISSANTE finissant à t
    (r[t-w+1 .. t], passé seul) -> âge du régime courant, rupture récente.
  - vol EWMA : sigma²_t = lam·sigma²_{t-1} + (1-lam)·r_t² (r_t connu à la
    clôture t, donc utilisable pour prédire le rendement forward depuis t).

Aucun ordre, aucune écriture hors scratchpad/regime_lab/. VERDICT: SAFE.
"""

import numpy as np

SEED = 42


# ---------------------------------------------------------------- primitives

def log_prices(closes):
    c = np.asarray(closes, dtype=float)
    c = np.where(c > 0, c, np.nan)
    return np.log(c)


def log_returns(logp):
    r = np.zeros_like(logp)
    r[1:] = logp[1:] - logp[:-1]
    r[~np.isfinite(r)] = 0.0
    return r


def ewma_vol(r, lam=0.94):
    """sigma_t : EWMA de r² INCLUANT r_t (connu à la clôture t). Causal pour
    tout usage prédictif du rendement forward depuis t."""
    n = len(r)
    s2 = np.empty(n)
    v = float(np.var(r[: min(50, n)])) or 1e-10
    for t in range(n):
        v = lam * v + (1.0 - lam) * r[t] * r[t]
        s2[t] = v
    return np.sqrt(np.maximum(s2, 1e-16))


def momentum_signal(logp, vol, lookbacks):
    """Momentum multi-périodes normalisé vol, clip ±5. Causal (passé seul)."""
    n = len(logp)
    m = np.zeros(n)
    cnt = np.zeros(n)
    for L in lookbacks:
        if L >= n:
            continue
        d = np.full(n, np.nan)
        d[L:] = (logp[L:] - logp[:-L]) / (np.maximum(vol[L:], 1e-8) * np.sqrt(L))
        ok = np.isfinite(d)
        m[ok] += d[ok]
        cnt[ok] += 1.0
    out = np.where(cnt > 0, m / np.maximum(cnt, 1), 0.0)
    return np.clip(out, -5.0, 5.0)


# ------------------------------------------------------------------- HMM

def hmm_fit(obs_train, n_states, seed=SEED):
    """GaussianHMM diag ajusté sur le TRAIN seul ; états RÉORDONNÉS par variance
    croissante (état K-1 = plus haute vol). Retourne dict de paramètres ou None."""
    from hmmlearn.hmm import GaussianHMM
    x = np.asarray(obs_train, dtype=float).reshape(-1, 1)
    if len(x) < 300 or float(np.std(x)) < 1e-10:
        return None
    try:
        m = GaussianHMM(n_components=n_states, covariance_type="diag",
                        n_iter=60, tol=1e-3, random_state=seed)
        m.fit(x)
    except Exception:
        return None
    means = m.means_.ravel()
    covs = np.maximum(m.covars_.reshape(n_states, -1)[:, 0], 1e-10)
    order = np.argsort(covs)                       # variance croissante
    A = m.transmat_[order][:, order]
    pi = m.startprob_[order]
    # garde-fou : lignes de transition dégénérées
    A = np.maximum(A, 1e-8)
    A = A / A.sum(axis=1, keepdims=True)
    pi = np.maximum(pi, 1e-8)
    pi = pi / pi.sum()
    return {"pi": pi, "A": A, "mu": means[order], "var": covs[order],
            "n_states": n_states}


def forward_filter(obs, params):
    """Filtrage forward MANUEL : alpha[t] = P(état_t | obs_0..t). Aucun regard
    en avant (pas de forward-backward, pas de Viterbi)."""
    x = np.asarray(obs, dtype=float)
    mu, var, A, pi = params["mu"], params["var"], params["A"], params["pi"]
    K = params["n_states"]
    n = len(x)
    # log-vraisemblances d'émission (vectorisé)
    logb = -0.5 * ((x[:, None] - mu[None, :]) ** 2 / var[None, :]
                   + np.log(2 * np.pi * var[None, :]))
    alpha = np.empty((n, K))
    a = pi * np.exp(logb[0] - logb[0].max())
    s = a.sum()
    a = a / s if s > 0 else np.full(K, 1.0 / K)
    alpha[0] = a
    for t in range(1, n):
        a = (a @ A) * np.exp(logb[t] - logb[t].max())
        s = a.sum()
        if not np.isfinite(s) or s <= 0:
            a = np.full(K, 1.0 / K)
        else:
            a = a / s
        alpha[t] = a
    return alpha


# ------------------------------------------------------------------ ruptures

def ruptures_ages(r_obs, sample_idx, window, pen, min_size=8, jump=2):
    """Pour chaque t de sample_idx : Pelt(rbf) sur r_obs[t-w+1..t] (PASSÉ seul).
    Retourne ages[t] = nb de barres depuis la dernière rupture (w si aucune,
    censuré). Causal par construction."""
    import ruptures as rpt
    ages = np.full(len(sample_idx), float(window))
    for i, t in enumerate(sample_idx):
        lo = t - window + 1
        if lo < 0:
            continue
        seg = r_obs[lo:t + 1].reshape(-1, 1)
        if float(np.std(seg)) < 1e-12:
            continue
        try:
            algo = rpt.Pelt(model="rbf", min_size=min_size, jump=jump).fit(seg)
            bkps = algo.predict(pen=pen)
        except Exception:
            continue
        if len(bkps) >= 2:                        # bkps[-1] == len(seg) toujours
            ages[i] = float(len(seg) - bkps[-2])
    return ages


def calibre_pen(r_obs, calib_idx, window, min_size=8, jump=2,
                grille=(1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0), cible=60.0):
    """Choisit pen (déterministe) : durée moyenne de segment la plus proche de
    `cible` barres, mesurée sur des fenêtres du DÉBUT de l'historique (amorçage,
    jamais les plis de test)."""
    import ruptures as rpt
    meilleurs = []
    for pen in grille:
        durees = []
        for t in calib_idx:
            lo = t - window + 1
            if lo < 0:
                continue
            seg = r_obs[lo:t + 1].reshape(-1, 1)
            if float(np.std(seg)) < 1e-12:
                continue
            try:
                bkps = rpt.Pelt(model="rbf", min_size=min_size,
                                jump=jump).fit(seg).predict(pen=pen)
            except Exception:
                continue
            durees.append(window / max(1, len(bkps)))
        if durees:
            meilleurs.append((abs(float(np.mean(durees)) - cible), pen,
                              float(np.mean(durees))))
    if not meilleurs:
        return 5.0, None
    meilleurs.sort()
    return meilleurs[0][1], meilleurs[0][2]


# ------------------------------------------------------------------ baselines

def flag_vol_ewma(vol, sample_idx, trail):
    """Baseline honnête : vol EWMA au-dessus de sa médiane GLISSANTE (trail
    barres, passé seul). 1 = haute vol."""
    out = np.zeros(len(sample_idx), dtype=int)
    for i, t in enumerate(sample_idx):
        lo = max(0, t - trail + 1)
        out[i] = int(vol[t] > np.median(vol[lo:t + 1]))
    return out


def markov_null_flags(flags_obs, n_seeds=100, seed0=1234):
    """Flags ALÉATOIRES à même taux de bascule : chaîne de Markov 2 états dont
    p01/p10 sont estimés sur le flag observé. Retourne (n_seeds, n) ou None."""
    f = np.asarray(flags_obs, dtype=int)
    n = len(f)
    if n < 10 or f.min() == f.max():
        return None
    t01 = np.sum((f[:-1] == 0) & (f[1:] == 1))
    n0 = max(1, np.sum(f[:-1] == 0))
    t10 = np.sum((f[:-1] == 1) & (f[1:] == 0))
    n1 = max(1, np.sum(f[:-1] == 1))
    p01 = min(max(t01 / n0, 1e-4), 1 - 1e-4)
    p10 = min(max(t10 / n1, 1e-4), 1 - 1e-4)
    out = np.empty((n_seeds, n), dtype=int)
    for s in range(n_seeds):
        rng = np.random.default_rng(seed0 + s)
        u = rng.random(n)
        x = f[0]
        for t in range(n):
            if t > 0:
                x = (1 if u[t] < p01 else 0) if x == 0 else (0 if u[t] < p10 else 1)
            out[s, t] = x
    return out


# ------------------------------------------------------------------ métriques

def ic_pair(scores, rets, min_n=15):
    """(pearson, rang) — (None, None) si dégénéré."""
    s = np.asarray(scores, dtype=float)
    r = np.asarray(rets, dtype=float)
    ok = np.isfinite(s) & np.isfinite(r)
    s, r = s[ok], r[ok]
    if len(s) < min_n or s.std() < 1e-12 or r.std() < 1e-12:
        return None, None
    pearson = float(np.corrcoef(s, r)[0, 1])
    rs = np.argsort(np.argsort(s)).astype(float)
    rr = np.argsort(np.argsort(r)).astype(float)
    rang = float(np.corrcoef(rs, rr)[0, 1])
    return pearson, rang


def rank_ic(scores, rets, min_n=15):
    return ic_pair(scores, rets, min_n)[1]
