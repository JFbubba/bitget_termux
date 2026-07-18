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
from scipy.stats import rankdata

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
