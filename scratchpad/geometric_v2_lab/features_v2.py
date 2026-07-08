"""Features géométriques v2 CANDIDATES — fonctions PURES, strictement CAUSALES
(chaque feature ne voit que la fenêtre passée qui lui est passée en argument).
Libs : POT 0.9.7 (Wasserstein), dcor 0.7 (corrélation de distance), nolds
(DFA / R-S / SampEn / dimension de corrélation). LECTURE SEULE, aucun ordre.

Baseline rejouée = geometric_agent.signal(closes_fenetre)["vote"] (fonctions pures
du dépôt, importées en lecture seule).
"""
import math
import warnings
from statistics import NormalDist

import numpy as np

warnings.filterwarnings("ignore")  # nolds émet des RuntimeWarning sur petits n

import ot          # noqa: E402  POT 0.9.7
import dcor        # noqa: E402  dcor 0.7
import nolds       # noqa: E402


# ---------- utilitaires ----------

def standardize(x):
    x = np.asarray(x, dtype=float)
    sd = x.std()
    return (x - x.mean()) / sd if sd > 1e-12 else x - x.mean()


_GQ_CACHE = {}


def gauss_quantiles(n):
    """Quantiles médians de N(0,1) (cachés par n). Pur."""
    if n not in _GQ_CACHE:
        nd = NormalDist()
        _GQ_CACHE[n] = np.array([nd.inv_cdf((i + 0.5) / n) for i in range(n)])
    return _GQ_CACHE[n]


# ---------- 1) POT / Wasserstein ----------

def w1_gauss_pot(rets):
    """W1(rendements standardisés de la fenêtre, N(0,1)) via POT = déficit
    isopérimétrique de la DISTRIBUTION (distance de forme à la boule gaussienne).
    Équivalent conceptuel de geometric_agent.w1_gauss mais via transport optimal POT."""
    x = standardize(rets)
    if len(x) < 32:
        return np.nan
    return float(ot.wasserstein_1d(x, gauss_quantiles(len(x))))


def w1_drift(prev_rets, cur_rets):
    """W1(fenêtre courante, fenêtre précédente) sur rendements BRUTS = VITESSE de
    dérive de régime (inclut les changements de vol). Normalisée par l'écart-type
    poolé pour rester sans échelle entre TF."""
    a = np.asarray(prev_rets, float)
    b = np.asarray(cur_rets, float)
    if len(a) < 16 or len(b) < 16:
        return np.nan
    sd = float(np.concatenate([a, b]).std())
    if sd < 1e-12:
        return np.nan
    return float(ot.wasserstein_1d(a, b)) / sd


def w1_drift_shape(prev_rets, cur_rets):
    """Comme w1_drift mais chaque fenêtre STANDARDISÉE séparément : dérive de la
    FORME seule (la composante vol est retirée)."""
    a, b = np.asarray(prev_rets, float), np.asarray(cur_rets, float)
    if len(a) < 16 or len(b) < 16 or a.std() < 1e-12 or b.std() < 1e-12:
        return np.nan
    return float(ot.wasserstein_1d(standardize(a), standardize(b)))


# ---------- 2) dcor : dépendance non linéaire ----------

def dcor_pair(x, y):
    """Corrélation de distance (dcor 0.7, algo rapide mergesort) ∈ [0,1]."""
    x = np.ascontiguousarray(x, dtype=float)
    y = np.ascontiguousarray(y, dtype=float)
    if len(x) < 32 or x.std() < 1e-12 or y.std() < 1e-12:
        return np.nan
    try:
        return float(dcor.distance_correlation(x, y, method="mergesort"))
    except Exception:
        return float(dcor.distance_correlation(x, y))


def dcor_excess(x, y):
    """dcor − |pearson| : excès de dépendance NON LINÉAIRE (queues, vol commune)
    invisible pour Pearson. Candidat « meilleurs yeux » pour les jambes 2-3."""
    d = dcor_pair(x, y)
    if not np.isfinite(d):
        return np.nan
    p = float(np.corrcoef(x, y)[0, 1])
    return d - abs(p)


def _lambda2_from_A(A):
    """λ₂ du Laplacien normalisé d'une matrice de poids A (diag nulle). Pur."""
    if A.sum() <= 0:
        return 0.0
    deg = A.sum(1)
    dinv = np.where(deg > 1e-12, 1.0 / np.sqrt(deg), 0.0)
    L = np.eye(len(A)) - (dinv[:, None] * A * dinv[None, :])
    ev = np.sort(np.linalg.eigvalsh((L + L.T) / 2))
    return float(max(0.0, ev[1])) if len(ev) > 1 else 0.0


def lambda2_dcor_graph(returns_matrix, thresh=0.5):
    """λ₂ du graphe re-pondéré en DCOR (au lieu de |Pearson|) — jambe 2 de l'agent
    avec des yeux non linéaires. Pas de débruitage RMT (Marchenko-Pastur n'est pas
    calibré pour une matrice de dcor — limite assumée)."""
    X = np.asarray(returns_matrix, float)
    if X.ndim != 2 or X.shape[1] < 3 or X.shape[0] < 32:
        return np.nan
    n = X.shape[1]
    A = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = dcor_pair(X[:, i], X[:, j])
            if np.isfinite(d) and d > thresh:
                A[i, j] = A[j, i] = d
    return _lambda2_from_A(A)


def lambda2_pearson_graph(returns_matrix, thresh=0.5):
    """λ₂ du graphe |Pearson| SANS débruitage (comparable 1:1 à lambda2_dcor_graph ;
    la version débruitée RMT = jambe 2 de l'agent, rejouée à part)."""
    X = np.asarray(returns_matrix, float)
    if X.ndim != 2 or X.shape[1] < 3 or X.shape[0] < 32:
        return np.nan
    C = np.nan_to_num(np.corrcoef(X, rowvar=False))
    A = np.abs(C) * (np.abs(C) > thresh)
    np.fill_diagonal(A, 0.0)
    return _lambda2_from_A(A)


# ---------- 3) nolds : rugosité / complexité ----------

def nolds_dfa(rets):
    try:
        h = float(nolds.dfa(np.asarray(rets, float)))
        return h if 0.0 < h < 2.0 else np.nan
    except Exception:
        return np.nan


def nolds_hurst_rs(rets):
    try:
        h = float(nolds.hurst_rs(np.asarray(rets, float)))
        return h if 0.0 < h < 1.5 else np.nan
    except Exception:
        return np.nan


def nolds_sampen(rets):
    try:
        s = float(nolds.sampen(standardize(rets)))
        return s if np.isfinite(s) else np.nan
    except Exception:
        return np.nan


def nolds_corr_dim(rets):
    try:
        d = float(nolds.corr_dim(standardize(rets), emb_dim=2))
        return d if np.isfinite(d) else np.nan
    except Exception:
        return np.nan
