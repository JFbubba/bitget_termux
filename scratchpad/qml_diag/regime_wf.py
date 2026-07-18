#!/usr/bin/env python3
"""Validation RÉGIME-CONDITIONNELLE de la 18e voix (QML), OOS walk-forward.

Question : en EXCLUANT les régimes de forte tendance, le wf_edge (acc − base, la
métrique du gate) devient-il positif hors-échantillon, avec un filtre SIMPLE et
robuste — ou faut-il un filtre alambiqué (= sur-ajustement, à tuer) ?

Protocole PRÉ-ENREGISTRÉ (anti-overfit) :
  • UN seul filtre causal : |ret_60m| (feature index 19 = momentum récent), grand =
    régime tendanciel (c'est ce qui fait le base-rate 80% des plis 4-5).
  • Seuil appris sur le TRAIN de chaque pli (percentiles 60 & 75) -> appliqué au VAL
    (aucun look-ahead, aucun réglage sur le val).
  • Même refit qml, même _acc_base que le gate. Edge évalué séparément sur chop (|ret|≤τ)
    et tendance (|ret|>τ), par pli ET poolé (OOS agrégé, plus stable).
  • Verdict lit : edge chop poolé, rétention (%), et sensibilité au seuil.
À exécuter dans le venv qml : ./qml_prototype/.venv/bin/python scratchpad/qml_diag/regime_wf.py
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "qml_prototype"))

import neural_net as nnmod
import train_voice as tv

RET60_IDX = nnmod.FEATURES.__len__() + nnmod.EXTRA_FEATURES.index("ret_60m")   # =19


def _edge(z, y):
    acc, base = tv._acc_base(z, y)
    return acc - base, acc, base


def main():
    X, y, ts = nnmod._dataset(with_ts=True)
    if len(X) > tv.MAX_N:
        X, y, ts = X[-tv.MAX_N:], y[-tv.MAX_N:], ts[-tv.MAX_N:]
    Xa = np.asarray(X, dtype=float)
    ya = np.asarray(y, dtype=float)
    trend = np.abs(Xa[:, RET60_IDX])            # |ret_60m| causal
    n = len(Xa)
    folds = nnmod.WF_FOLDS
    block = n // (folds + 1)
    print(f"=== VALIDATION RÉGIME-CONDITIONNELLE QML — {n} exemples · {folds} plis · "
          f"filtre |ret_60m| (idx {RET60_IDX}) ===\n")
    print(f"{'pli':<4} {'edge_tot':>9} {'base':>6} | "
          f"{'edge_chop60':>11} {'ret%':>5} {'edge_trend60':>12} | "
          f"{'edge_chop75':>11} {'ret%':>5}")
    pool = {"chop60": [[], []], "trend60": [[], []], "chop75": [[], []], "all": [[], []]}
    for f in range(folds):
        lo = (f + 1) * block
        hi = (f + 2) * block if f < folds - 1 else n
        tr_idx = nnmod._purged_train_idx(ts, lo)
        if len(tr_idx) < 100 or hi - lo < 50:
            continue
        w = tv._fit_quantum([X[i] for i in tr_idx], [y[i] for i in tr_idx], seed=tv.SEED + f)
        with torch.no_grad():
            z = tv.circuit(torch.tensor(Xa[lo:hi], dtype=torch.float64),
                           torch.tensor(w, dtype=torch.float64)).numpy()
        yv = ya[lo:hi]
        tv_trend = trend[lo:hi]
        tau60, tau75 = np.percentile(trend[tr_idx], [60, 75])   # seuils appris sur TRAIN
        e_tot, _, base = _edge(z, yv)
        m60 = tv_trend <= tau60
        m75 = tv_trend <= tau75
        e_c60 = _edge(z[m60], yv[m60])[0] if m60.sum() > 20 else float("nan")
        e_t60 = _edge(z[~m60], yv[~m60])[0] if (~m60).sum() > 20 else float("nan")
        e_c75 = _edge(z[m75], yv[m75])[0] if m75.sum() > 20 else float("nan")
        print(f"{f:<4} {e_tot:>+9.4f} {base:>6.3f} | "
              f"{e_c60:>+11.4f} {100*m60.mean():>4.0f}% {e_t60:>+12.4f} | "
              f"{e_c75:>+11.4f} {100*m75.mean():>4.0f}%")
        for arr, mask in (("chop60", m60), ("trend60", ~m60), ("chop75", m75)):
            pool[arr][0].extend(list(z[mask])); pool[arr][1].extend(list(yv[mask]))
        pool["all"][0].extend(list(z)); pool["all"][1].extend(list(yv))

    print("\n-- POOLÉ (tous plis, OOS agrégé) --")
    for k in ("all", "chop60", "chop75", "trend60"):
        zz, yy = pool[k]
        if len(zz) > 20:
            e, acc, base = _edge(np.asarray(zz), np.asarray(yy))
            print(f"  {k:<8} n={len(zz):>5} · edge {e:+.4f} (acc {acc:.3f} vs base {base:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
