"""CLI du Strategy Tester Python (inspiré du MT5 Strategy Tester, données Bitget).

    python3 run.py backtest <stratégie> <SYM> <TF>     # backtest simple + rapport
    python3 run.py wf       <stratégie> <SYM> <TF>     # walk-forward (OOS) + rapport

stratégies : ema_cross, donchian_breakout      (frais Bitget taker par défaut)
"""
import sys
import engine as E, metrics as M, report as R, optimize as O
from strategies import STRATEGIES

# grilles d'optimisation par stratégie (bornées)
GRIDS = {
    "ema_cross": {"fast": [8, 16, 32], "slow": [48, 96, 192], "sl": [0.02, 0.04], "tp": [0.04, 0.08]},
    "donchian_breakout": {"lookback": [10, 20, 55], "sl": [0.02, 0.04], "tp": [0.04, 0.08]},
}
DEFAULT_PARAMS = {"ema_cross": {"fast": 12, "slow": 48, "sl": 0.03, "tp": 0.06},
                  "donchian_breakout": {"lookback": 20, "sl": 0.03, "tp": 0.06}}


def main():
    if len(sys.argv) < 5 or sys.argv[2] not in STRATEGIES:
        print(__doc__); print("stratégies dispo :", ", ".join(STRATEGIES)); return
    mode, strat, sym, tf = sys.argv[1], sys.argv[2], sys.argv[3].upper(), sys.argv[4]
    fn = STRATEGIES[strat]
    d = E.load_ohlcv(sym, tf)
    if d is None:
        print(f"pas de données pour {sym} {tf} (télécharger via candles_history)"); return
    cfg = E.ExecConfig(commission_bps=6, spread_bps=2, slippage_bps=1)   # taker Bitget
    if mode == "backtest":
        res = E.run_backtest(d, fn, cfg, params=DEFAULT_PARAMS[strat])
        m = M.compute(res, tf, bench_close=d["c"], warmup=160)   # + benchmark buy-and-hold
        print(R.render(m, res, f"{strat} {DEFAULT_PARAMS[strat]}"))
    elif mode == "wf":
        wf = O.walk_forward(d, fn, cfg, GRIDS[strat], tf, n_folds=4, objective="sharpe")
        if "error" in wf:
            print("WF:", wf["error"]); return
        print(R.render(wf["oos_metrics"], wf["oos_result"], f"{strat} WALK-FORWARD OOS"))
        print("\nCombos choisis par tranche in-sample :")
        for p in wf["picks"]:
            print("  ", p)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
