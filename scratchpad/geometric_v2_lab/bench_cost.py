"""Banc de COÛT (µs/appel) des features v2 vs baseline geometric_agent.signal.
Fenêtre = 160 rendements (le live utilise 160 closes). LECTURE SEULE."""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import features_v2 as fv        # noqa: E402
import geometric_agent as ga    # noqa: E402

rng = np.random.default_rng(7)
W = 160
closes = 100.0 * np.exp(np.cumsum(0.002 * rng.standard_normal(W + 1)))
rets = np.diff(np.log(closes))
prev = 0.002 * rng.standard_normal(W)
M10 = 0.002 * rng.standard_normal((W, 10))   # panier 10 symboles (5m)
M4 = 0.002 * rng.standard_normal((W, 4))     # panier 4 symboles (1H)


def bench(fn, reps):
    fn()  # warm-up (numba jit de dcor, caches)
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t0) / reps * 1e6  # µs


CASES = [
    ("baseline geometric_agent.signal", lambda: ga.signal(list(closes)), 200),
    ("w1_gauss_pot", lambda: fv.w1_gauss_pot(rets), 500),
    ("w1_drift", lambda: fv.w1_drift(prev, rets), 500),
    ("w1_drift_shape", lambda: fv.w1_drift_shape(prev, rets), 500),
    ("w1_gauss numpy (agent, réf.)", lambda: ga.w1_gauss(rets), 500),
    ("dcor_pair (160)", lambda: fv.dcor_pair(rets, prev), 300),
    ("dcor_excess (160)", lambda: fv.dcor_excess(rets, prev), 300),
    ("lambda2_dcor_graph (10 sym)", lambda: fv.lambda2_dcor_graph(M10), 20),
    ("lambda2_pearson_graph (10 sym)", lambda: fv.lambda2_pearson_graph(M10), 200),
    ("lambda2_dcor_graph (4 sym)", lambda: fv.lambda2_dcor_graph(M4), 50),
    ("agent correlation_graph_metrics (10 sym, RMT)", lambda: ga.correlation_graph_metrics(M10), 200),
    ("nolds_dfa (160)", lambda: fv.nolds_dfa(rets), 100),
    ("nolds_hurst_rs (160)", lambda: fv.nolds_hurst_rs(rets), 100),
    ("nolds_sampen (160)", lambda: fv.nolds_sampen(rets), 100),
    ("nolds_corr_dim (160)", lambda: fv.nolds_corr_dim(rets), 50),
    ("agent dfa_hurst (réf.)", lambda: ga.dfa_hurst(rets), 100),
]

out = {}
for name, fn, reps in CASES:
    us = bench(fn, reps)
    out[name] = round(us, 1)
    print(f"{name:<48} {us:>12.1f} µs/appel", flush=True)

Path(__file__).with_name("cost_bench.json").write_text(json.dumps(out, indent=1))
print("OK")
