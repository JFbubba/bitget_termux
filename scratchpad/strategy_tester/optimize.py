"""Optimisation de paramètres + WALK-FORWARD (in-sample/out-of-sample), comme le
'forward testing' du MT5 Strategy Tester. Le walk-forward est ce qui distingue une
vraie mesure d'un backtest sur-ajusté : on optimise sur le passé, on VALIDE sur du
futur jamais vu, et seule la perf out-of-sample compte.
"""
from __future__ import annotations
import itertools
import numpy as np

import engine as E
import metrics as M


def grid_combos(grid):
    keys = list(grid)
    for vals in itertools.product(*(grid[k] for k in keys)):
        yield dict(zip(keys, vals))


def _slice(ohlcv, a, b):
    return {k: v[a:b] for k, v in ohlcv.items()}


def optimize(ohlcv, strategy_fn, cfg, grid, tf, objective="sharpe", warmup=160):
    """Meilleur combo sur CETTE tranche (in-sample), par métrique objectif."""
    best, best_score = None, -1e18
    for combo in grid_combos(grid):
        res = E.run_backtest(ohlcv, strategy_fn, cfg, params=combo, warmup=warmup)
        m = M.compute(res, tf)
        s = m.get(objective)
        if s is None or (isinstance(s, float) and not np.isfinite(s)):
            continue
        if s > best_score:
            best, best_score = combo, s
    return best, best_score


def walk_forward(ohlcv, strategy_fn, cfg, grid, tf, n_folds=4,
                 objective="sharpe", warmup=160):
    """Anchored walk-forward : in-sample grandissant, OOS = tranche suivante.
    Retourne la perf agrégée OUT-OF-SAMPLE (equity concaténée) + combos choisis."""
    n = len(ohlcv["c"])
    if n < warmup + 6 * n_folds:
        return {"error": "série trop courte pour le walk-forward"}
    bounds = np.linspace(warmup, n, n_folds + 2).astype(int)
    oos_equity, oos_trades, picks = [], [], []
    for k in range(1, n_folds + 1):
        in_a, in_b = warmup, bounds[k]           # in-sample : [warmup, bounds[k])
        oo_a, oo_b = bounds[k], bounds[k + 1]     # OOS      : [bounds[k], bounds[k+1])
        combo, sc = optimize(_slice(ohlcv, 0, in_b), strategy_fn, cfg, grid, tf,
                             objective, warmup)
        if combo is None:
            continue
        res = E.run_backtest(_slice(ohlcv, oo_a - warmup, oo_b), strategy_fn, cfg,
                             params=combo, warmup=warmup)
        eq = res.equity[warmup:]
        if len(eq):
            # rebaser sur la fin de l'OOS précédente pour une equity continue
            base = oos_equity[-1] if oos_equity else cfg.capital
            oos_equity.extend(list(eq / eq[0] * base))
        oos_trades.extend(res.trades)
        picks.append({"fold": k, "combo": combo, f"in_{objective}": round(sc, 3),
                      "n_trades_oos": len(res.trades)})
    if not oos_equity:
        return {"error": "aucune tranche OOS exploitable"}
    agg = E.Result(equity=np.array(oos_equity), trades=oos_trades, cfg=cfg,
                   meta={"walk_forward": True})
    return {"oos_metrics": M.compute(agg, tf), "picks": picks, "oos_result": agg}
