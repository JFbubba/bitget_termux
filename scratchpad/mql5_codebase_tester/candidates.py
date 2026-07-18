"""Réimplémentations Python de la LOGIQUE de candidats de la code base mql5.
Chaque candidat = une fonction de signal causale conforme au contrat du harness
(voir harness.py). La logique est reconstruite depuis la DESCRIPTION de l'article,
JAMAIS copiée/exécutée depuis un .mq5 (ligne rouge).

Registre CANDIDATS : nom -> (fonction, source_article).
"""
import math
import numpy as np


def kalman_slope(win):
    """Kalman 'local linear trend' (niveau+vitesse), signal = signe de la vitesse.
    Source : 'A Practical Kalman Filter Price Smoother in MQL5' (score triage +5).
    Modèle constant-velocity : x=[niveau,vitesse]; obs=log-prix+bruit.
    Vote = tanh(vitesse estimée normalisée par la vol)."""
    c = win["c"]
    if len(c) < 40:
        return 0.0
    z = np.log(np.clip(c, 1e-12, None))
    q_lvl, q_vel, r = 1e-5, 1e-6, 1e-3      # bruits process/observation (adaptatif léger)
    x = np.array([z[0], 0.0])
    P = np.eye(2) * 1e-2
    F = np.array([[1.0, 1.0], [0.0, 1.0]])
    H = np.array([[1.0, 0.0]])
    Q = np.array([[q_lvl, 0.0], [0.0, q_vel]])
    for zt in z[1:]:
        x = F @ x
        P = F @ P @ F.T + Q
        y = zt - (H @ x)[0]
        S = (H @ P @ H.T)[0, 0] + r
        K = (P @ H.T).reshape(2) / S
        x = x + K * y
        P = (np.eye(2) - np.outer(K, H)) @ P
    vel = x[1]
    vol = float(np.std(np.diff(z[-40:]))) or 1e-9
    return float(np.tanh(vel / vol * 3.0))


# ---------------------------------------------------------------------------
# Structural break tests — AFML Chapitre 17 (López de Prado), réimplémentés
# depuis la DESCRIPTION de l'article MQL5 "Feature Engineering for ML (Part 9):
# Structural Break Tests in Python" (art. 23158). Les tests d'origine sont des
# FEATURES pour un modèle ML ; toute lecture DIRECTIONNELLE ci-dessous est une
# construction du testeur (documentée dans le verdict). Tout est causal (fenêtre
# du harness) et n'utilise JAMAIS le futur. Aucun code MQL5 exécuté (ligne rouge).
# ---------------------------------------------------------------------------

_B05 = 4.6      # b_alpha ~ 4.6 pour alpha=0.05 (seuil critique CSW, AFML 17.2)


def _ols_t(X, y):
    """OLS -> (beta, t) avec t = beta / SE(beta). None si mal conditionné."""
    try:
        XtX = X.T @ X
        XtXinv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        return None, None
    beta = XtXinv @ (X.T @ y)
    dof = len(y) - X.shape[1]
    if dof < 5:
        return None, None
    resid = y - X @ beta
    s2 = float(resid @ resid) / dof
    se = np.sqrt(np.maximum(np.diag(XtXinv) * s2, 1e-30))
    return beta, beta / se


def _adf_t(yv, L=1):
    """t-stat ADF du coefficient de niveau : Δy_i = α + β·y_{i-1} + Σγ_j Δy_{i-j}.
    β>0 -> explosif ; β<0 -> retour à la moyenne. Renvoie le t de β (None si court)."""
    yv = np.asarray(yv, float)
    N = len(yv)
    if N < L + 15:
        return None
    dy = np.diff(yv)                       # dy[k] = Δy_{k+1}
    i = np.arange(L + 1, N)                # obs i = L+1 .. N-1
    dep = dy[i - 1]                        # Δy_i
    cols = [np.ones(len(i)), yv[i - 1]]    # const, niveau y_{i-1}
    for j in range(1, L + 1):
        cols.append(dy[i - 1 - j])         # Δy_{i-j}
    b, t = _ols_t(np.column_stack(cols), dep)
    return None if t is None else float(t[1])


def _sadf(yv, min_w=40, L=1, step=4):
    """Supremum ADF (AFML 17.4) : sup des t-ADF sur fenêtres de départ étendues,
    fin fixée à la barre courante. Grand SADF = régime EXPLOSIF (bulle)."""
    yv = np.asarray(yv, float)
    N = len(yv)
    if N < min_w + 5:
        return None
    stats = []
    for t0 in range(0, N - min_w, step):
        tt = _adf_t(yv[t0:N], L)
        if tt is not None:
            stats.append(tt)
    return max(stats) if stats else None


def _csw(yv, min_span=5):
    """Chu-Stinchcombe-White CUSUM (AFML 17.2) sur les niveaux (log-prix).
    S_{n,t}=(y_t-y_n)/(σ̂·√(t-n)) ; renvoie (S* signé au n* de |S| max, seuil c, n*)."""
    yv = np.asarray(yv, float)
    N = len(yv)
    if N < 20:
        return 0.0, 0.0, None
    dy = np.diff(yv)
    sig = math.sqrt(max(float(np.mean(dy * dy)), 1e-18))
    t = N - 1
    n = np.arange(0, t - min_span + 1)
    if len(n) == 0:
        return 0.0, 0.0, None
    span = (t - n).astype(float)
    S = (yv[t] - yv[n]) / (sig * np.sqrt(span))
    k = int(np.argmax(np.abs(S)))
    n_star = int(n[k])
    c = math.sqrt(_B05 + math.log(max(t - n_star, 1)))
    return float(S[k]), c, n_star


def csw_cusum(win):
    """Vote directionnel CSW : signe/ampleur de la rupture standardisée / seuil critique.
    Prix loin AU-DESSUS d'une référence -> rupture haussière -> long."""
    yv = np.log(np.clip(win["c"], 1e-12, None))
    s, c, n_star = _csw(yv)
    if n_star is None or c <= 0:
        return 0.0
    return float(np.tanh(s / c))


def sadf_dir(win):
    """Vote SADF : ampleur d'explosivité (gate) × sens de la dérive récente.
    Régime explosif + prix qui monte -> momentum long ; explosif + baisse -> short."""
    yv = np.log(np.clip(win["c"], 1e-12, None))
    sadf = _sadf(yv)
    if sadf is None:
        return 0.0
    mag = math.tanh(max(0.0, (sadf + 0.5)) / 1.5)     # ~0 en régime calme, monte si explosif
    m = min(40, len(yv) - 1)
    drift = yv[-1] - yv[-1 - m]
    return float(mag * np.sign(drift))


def _chow(yv, fracs=(0.3, 0.4, 0.5, 0.6, 0.7)):
    """Chow-type Dickey-Fuller (AFML 17.3) : Δy_i = δ·y_{i-1}·1[i>τ] + ε, sup|t(δ)|.
    δ>0 -> bascule vers l'explosif à la rupture ; renvoie le t(δ) signé du meilleur τ."""
    yv = np.asarray(yv, float)
    N = len(yv)
    if N < 30:
        return 0.0
    dy = np.diff(yv)
    i = np.arange(1, N)
    dep = dy[i - 1]
    lev = yv[i - 1]
    best_t = 0.0
    for f in fracs:
        tau = int(f * N)
        x = lev * (i > tau).astype(float)
        sx2 = float(np.dot(x, x))
        if sx2 < 1e-18:
            continue
        delta = float(np.dot(x, dep)) / sx2
        dof = len(dep) - 1
        if dof < 5:
            continue
        resid = dep - delta * x
        s2 = float(np.dot(resid, resid)) / dof
        se = math.sqrt(max(s2 / sx2, 1e-30))
        tval = delta / se
        if abs(tval) > abs(best_t):
            best_t = tval
    return best_t


def chow_dir(win):
    """Vote Chow-type DF : sens/force de la bascule explosive à la rupture estimée."""
    yv = np.log(np.clip(win["c"], 1e-12, None))
    return float(np.tanh(_chow(yv) / 3.0))


def struct_break_suite(win):
    """SUITE HOLISTIQUE (testée EN PREMIER, ERR-002) : moyenne des trois lectures
    directionnelles CSW + SADF×dérive + Chow. Ensemble équipondéré des tests d'AFML 17."""
    v = (csw_cusum(win) + sadf_dir(win) + chow_dir(win)) / 3.0
    return float(max(-1.0, min(1.0, v)))


def struct_break_sequence(win):
    """SÉQUENCE ORDONNÉE (re-test audit ERR-014) : au lieu de la MOYENNE simultanée,
    on exige l'ENCHAÎNEMENT TEMPOREL des trois tests, chacun sur une sous-fenêtre PLUS
    RÉCENTE que le précédent (arme→confirme→localise) :
      1. CSW marque une rupture significative dans le passé moyen  (fenêtre .. n-2·lag) ;
      2. PUIS SADF confirme l'explosivité plus récemment            (fenêtre .. n-lag) ;
      3. PUIS Chow localise la bascule MAINTENANT                    (fenêtre complète).
    Direction = momentum (dérive récente) au moment de la rupture confirmée. 0 si la
    séquence n'est pas complète. (Lecture directionnelle = construction du testeur ;
    AFML donne ces tests comme features parallèles — d'où l'intérêt de vérifier l'ordre.)"""
    c = win["c"]
    n = len(c)
    if n < 80:
        return 0.0
    yv = np.log(np.clip(c, 1e-12, None))
    lag = max(5, n // 20)
    s, cc, ns = _csw(yv[:n - 2 * lag])              # 1. rupture CSW (la plus ancienne)
    if ns is None or abs(s) < cc:
        return 0.0
    sadf_mid = _sadf(yv[:n - lag])                  # 2. explosivité SADF (ensuite)
    if sadf_mid is None or sadf_mid < 0.5:
        return 0.0
    chow_now = _chow(yv)                            # 3. bascule Chow (maintenant)
    if abs(chow_now) < 2.0:
        return 0.0
    m = min(40, n - 1)
    drift = yv[-1] - yv[-1 - m]
    return float(np.tanh(chow_now / 3.0) * np.sign(drift))


_SB_SRC = "Feature Engineering for ML (Part 9): Structural Break Tests in Python (AFML Ch.17)"

CANDIDATES = {
    "kalman_slope": (kalman_slope, "A Practical Kalman Filter Price Smoother in MQL5"),
    "struct_break_suite": (struct_break_suite, _SB_SRC),
    "struct_break_sequence": (struct_break_sequence, _SB_SRC),
    "csw_cusum": (csw_cusum, _SB_SRC),
    "sadf_dir": (sadf_dir, _SB_SRC),
    "chow_dir": (chow_dir, _SB_SRC),
}
