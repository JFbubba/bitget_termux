"""Rapport texte façon MT5 Strategy Tester + equity curve ASCII."""
from __future__ import annotations
import numpy as np


def _sparkline(eq, width=64):
    eq = np.asarray(eq, float)
    if len(eq) > width:
        idx = np.linspace(0, len(eq) - 1, width).astype(int)
        eq = eq[idx]
    lo, hi = eq.min(), eq.max()
    blocks = "▁▂▃▄▅▆▇█"
    if hi - lo < 1e-9:
        return blocks[0] * len(eq)
    return "".join(blocks[min(7, int((v - lo) / (hi - lo) * 7))] for v in eq)


def render(m, result=None, name=""):
    L = []
    L.append(f"=== RAPPORT STRATEGY TESTER : {name} [{m.get('tf','?')}] ===")
    if m.get("degenerate"):
        L.append("  (equity dégénérée / trop peu de barres)")
        return "\n".join(L)
    g = lambda k: m.get(k)
    L.append(f"  Rendement total : {g('total_return_pct')}%   ·   CAGR : {g('cagr_pct')}%")
    L.append(f"  Sharpe : {g('sharpe')}   ·   Sortino : {g('sortino')}")
    L.append(f"  Max drawdown : {g('max_drawdown_pct')}%   ·   Recovery factor : {g('recovery_factor')}")
    L.append(f"  Trades : {g('n_trades')}   ·   Win rate : {g('win_rate_pct')}%   ·   Exposition : {g('exposure_pct')}%")
    L.append(f"  Profit factor : {g('profit_factor')}   ·   Expectancy : {g('expectancy_usd')} $/trade")
    L.append(f"  Gain moyen : {g('avg_win_usd')} $   ·   Perte moyenne : {g('avg_loss_usd')} $   ·   Payoff : {g('payoff_ratio')}")
    if g("bh_return_pct") is not None:   # benchmark alpha vs beta (ERR-014 §2)
        L.append(f"  --- vs BUY-AND-HOLD : ret {g('bh_return_pct')}%  ·  Sharpe {g('bh_sharpe')}  ·  maxDD {g('bh_max_drawdown_pct')}%")
        verdict = []
        if g("beats_bh_sharpe") is not None:
            verdict.append(f"bat le B&H en Sharpe : {'OUI' if g('beats_bh_sharpe') else 'NON'}")
        if g("beats_bh_drawdown") is not None:
            verdict.append(f"en drawdown : {'OUI' if g('beats_bh_drawdown') else 'NON'}")
        if g("short_pnl_usd") is not None:
            verdict.append(f"PnL long {g('long_pnl_usd')}$ / short {g('short_pnl_usd')}$")
        L.append("      " + "   ·   ".join(verdict))
    if result is not None and len(result.equity):
        L.append(f"  Equity : {_sparkline(result.equity)}")
    return "\n".join(L)
