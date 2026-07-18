"""Stratégies de démonstration pour le Strategy Tester (contrat engine.py).
Chacune retourne {'signal': +1/-1/0, 'sl': frac|None, 'tp': frac|None}."""
from __future__ import annotations
import numpy as np


def _ema(x, span):
    a = 2.0 / (span + 1.0)
    e = x[0]
    for v in x[1:]:
        e = a * v + (1 - a) * e
    return e


def ema_cross(ctx):
    """Long si EMA rapide > EMA lente, short sinon. SL/TP optionnels via params."""
    c = ctx["c"]; p = ctx["params"]
    fast, slow = p.get("fast", 12), p.get("slow", 48)
    if len(c) < slow + 2:
        return {"signal": 0}
    sig = 1 if _ema(c[-slow * 3:], fast) > _ema(c[-slow * 3:], slow) else -1
    return {"signal": sig, "sl": p.get("sl"), "tp": p.get("tp")}


def donchian_breakout(ctx):
    """Long si close > plus haut des N barres précédentes ; short si < plus bas."""
    c, h, l = ctx["c"], ctx["h"], ctx["l"]; p = ctx["params"]
    n = p.get("lookback", 20)
    if len(c) < n + 2:
        return {"signal": 0}
    hh, ll = np.max(h[-n - 1:-1]), np.min(l[-n - 1:-1])
    if c[-1] >= hh:
        return {"signal": 1, "sl": p.get("sl"), "tp": p.get("tp")}
    if c[-1] <= ll:
        return {"signal": -1, "sl": p.get("sl"), "tp": p.get("tp")}
    return {"signal": None}     # conserver la position (breakout = tenir jusqu'au signal inverse)


STRATEGIES = {"ema_cross": ema_cross, "donchian_breakout": donchian_breakout}
