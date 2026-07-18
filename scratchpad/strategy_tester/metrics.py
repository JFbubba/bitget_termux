"""Métriques de performance (style rapport MT5 Strategy Tester), calculées depuis
l'equity curve et la liste de trades produites par engine.run_backtest."""
from __future__ import annotations
import numpy as np

# barres par an par timeframe (pour annualiser Sharpe/CAGR)
BARS_PER_YEAR = {"1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520,
                 "1H": 8760, "4H": 2190, "1D": 365, "1W": 52}


def _max_drawdown(eq):
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    i = int(np.argmin(dd))
    return float(dd.min()), i


def buy_and_hold(close, warmup, tf):
    """Benchmark achat-conservation sur la MÊME fenêtre [warmup:] que le backtest.
    Indispensable pour un système DIRECTIONNEL exposé : un gros rendement brut en
    marché haussier est souvent du BETA capturé, pas de l'alpha (cf. ERR-014 §2)."""
    px = np.asarray(close, float)[warmup:]
    px = px[np.isfinite(px) & (px > 0)]
    if len(px) < 10:
        return None
    bpy = BARS_PER_YEAR.get(tf, 8760)
    rets = np.diff(px) / px[:-1]
    rets = rets[np.isfinite(rets)]
    sd = float(np.std(rets))
    peak = np.maximum.accumulate(px)
    return {
        "bh_return_pct": round((px[-1] / px[0] - 1.0) * 100, 2),
        "bh_sharpe": round(float(np.mean(rets)) / sd * np.sqrt(bpy), 2) if sd > 1e-12 else None,
        "bh_max_drawdown_pct": round(float(((px - peak) / peak).min()) * 100, 2),
    }


def compute(result, tf, bench_close=None, warmup=0):
    """Si bench_close (série de close) est fourni, ajoute le benchmark buy-and-hold et
    les verdicts alpha-vs-beta (bat le B&H en Sharpe ? en drawdown ?)."""
    eq = np.asarray(result.equity, float)
    eq = eq[np.isfinite(eq) & (eq > 0)]
    trades = result.trades
    cap = result.cfg.capital
    bpy = BARS_PER_YEAR.get(tf, 8760)
    out = {"tf": tf, "n_trades": len(trades)}
    if len(eq) < 10:
        out["degenerate"] = True
        return out

    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    total_ret = eq[-1] / cap - 1.0
    years = max(len(eq) / bpy, 1e-9)
    out["total_return_pct"] = round(total_ret * 100, 2)
    out["cagr_pct"] = round(((eq[-1] / cap) ** (1 / years) - 1.0) * 100, 2) if eq[-1] > 0 else None
    mu, sd = float(np.mean(rets)), float(np.std(rets))
    dn = float(np.std(rets[rets < 0])) if np.any(rets < 0) else 0.0
    out["sharpe"] = round(mu / sd * np.sqrt(bpy), 2) if sd > 1e-12 else None
    out["sortino"] = round(mu / dn * np.sqrt(bpy), 2) if dn > 1e-12 else None
    mdd, _ = _max_drawdown(eq)
    out["max_drawdown_pct"] = round(mdd * 100, 2)
    out["recovery_factor"] = round(total_ret / abs(mdd), 2) if mdd < -1e-9 else None
    out["exposure_pct"] = round(sum(t.bars for t in trades) / max(len(eq), 1) * 100, 1)

    if trades:
        pnls = np.array([t.pnl for t in trades])
        wins, losses = pnls[pnls > 0], pnls[pnls < 0]
        gross_win, gross_loss = float(wins.sum()), float(-losses.sum())
        out["win_rate_pct"] = round(len(wins) / len(trades) * 100, 1)
        out["profit_factor"] = round(gross_win / gross_loss, 2) if gross_loss > 1e-9 else None
        out["expectancy_usd"] = round(float(pnls.mean()), 2)
        out["avg_win_usd"] = round(float(wins.mean()), 2) if len(wins) else 0.0
        out["avg_loss_usd"] = round(float(losses.mean()), 2) if len(losses) else 0.0
        out["payoff_ratio"] = (round(abs(wins.mean() / losses.mean()), 2)
                               if len(wins) and len(losses) else None)

    # --- benchmark buy-and-hold + verdict alpha/beta (ERR-014 §2) ---
    if bench_close is not None:
        bh = buy_and_hold(bench_close, warmup, tf)
        if bh:
            out.update(bh)
            if out.get("sharpe") is not None and bh["bh_sharpe"] is not None:
                out["beats_bh_sharpe"] = out["sharpe"] > bh["bh_sharpe"]
            if out.get("max_drawdown_pct") is not None:
                out["beats_bh_drawdown"] = abs(out["max_drawdown_pct"]) < abs(bh["bh_max_drawdown_pct"])
            if trades:
                lp = sum(t.pnl for t in trades if t.direction == 1)
                sp = sum(t.pnl for t in trades if t.direction == -1)
                out["long_pnl_usd"], out["short_pnl_usd"] = round(lp, 2), round(sp, 2)
    return out
