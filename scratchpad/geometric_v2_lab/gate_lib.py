"""Helpers partagés des 3 tâches parallèles (gate / cross-TF / replay profond).
LECTURE SEULE : ne lit que data_history/. Aucun ordre, aucune exécution.
Direction-agnostique => on teste RÉGIME/VOL et GATE, pas le rendement signé seul.
"""
import math
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB.parents[1]))
sys.path.insert(0, str(LAB))

import candles_history as ch     # noqa: E402
import features_v2 as fv         # noqa: E402
import geometric_agent as ga     # noqa: E402
from scipy.stats import spearmanr  # noqa: E402


def load_series(sym, gran):
    rows = ch.load(sym, gran)
    ts = np.array([r[0] for r in rows], dtype=np.int64)
    cl = np.array([r[4] for r in rows], dtype=float)
    ok = cl > 0
    return ts[ok], cl[ok]


def logret(cl):
    return np.diff(np.log(cl))


def t_across_folds(vals):
    v = np.asarray([x for x in vals if np.isfinite(x)], dtype=float)
    if len(v) < 3:
        return 0.0, 0.0, len(v)
    se = v.std(ddof=1) / math.sqrt(len(v))
    return float(v.mean()), (float(v.mean() / se) if se > 1e-12 else 0.0), len(v)


def purged_folds(idx, h, n_folds=6):
    """Renvoie une liste de masques booléens (dans l'espace des points de `idx`),
    étiquettes NON chevauchantes (espacement >= h barres), purge h en tête de pli.
    `idx` = indices de barre (croissants) des points évalués."""
    idx = np.asarray(idx)
    lo, hi = idx.min(), idx.max()
    bounds = [lo + (hi - lo) * k / n_folds for k in range(n_folds + 1)]
    out = []
    for k in range(n_folds):
        s = (idx >= bounds[k] + h) & (idx < bounds[k + 1])
        keep, last = [], -10 ** 9
        for j in np.where(s)[0]:
            if idx[j] >= last + h:
                keep.append(j); last = idx[j]
        out.append(np.array(keep, dtype=int))
    return out


def ic_rank(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 8 or x.std() < 1e-12 or y.std() < 1e-12:
        return np.nan
    return float(spearmanr(x, y).statistic)


def build_features(sym, gran, w=160, stride=2, nolds_target=1500,
                   want=("geom_vote", "w1_drift", "nolds_dfa", "rvol", "rev8")):
    """Grille causale de features par symbole. Retourne (idx, dict feat->array, fwd dict h).
    rvol = vol réalisée fenêtre (benchmark de gate), rev8 = signal réversion −z(somme 8)."""
    ts, cl = load_series(sym, gran)
    n = len(cl)
    if n < 2 * w + 60:
        return None
    lr = logret(cl)
    HORIZ = (1, 4, 24)
    maxh = max(HORIZ)
    grid = np.arange(2 * w, n - maxh, stride)
    K = max(1, math.ceil(len(grid) / nolds_target))
    F = {k: np.full(len(grid), np.nan) for k in want}
    FWD = {h: np.full(len(grid), np.nan) for h in HORIZ}
    for gi, t in enumerate(grid):
        cur = lr[t - w:t]
        prev = lr[t - 2 * w:t - w]
        if "geom_vote" in want:
            F["geom_vote"][gi] = ga.signal(cl[t - w:t + 1].tolist())["vote"]
        if "w1_drift" in want:
            F["w1_drift"][gi] = fv.w1_drift(prev, cur)
        if "rvol" in want:
            F["rvol"][gi] = float(cur.std())
        if "rev8" in want:
            sd = cur.std()
            F["rev8"][gi] = -math.tanh(float(cur[-8:].sum()) / (sd * math.sqrt(8) + 1e-9) / 2.0) if sd > 0 else 0.0
        if "nolds_dfa" in want and gi % K == 0:
            F["nolds_dfa"][gi] = fv.nolds_dfa(cur)
        for h in HORIZ:
            FWD[h][gi] = math.log(cl[t + h] / cl[t])
    return grid, F, FWD, K, (ts[0], ts[-1], n)
