"""Backtest de SMC/ICT (machine à états causale, smc_ict.py) sur l'échelle COMPLÈTE de
TF (ERR-001) × 6 symboles crypto, NET DE FRAIS Bitget, AVEC benchmark buy-and-hold.
Re-test corrigé du rejet SMC suspecté ERR-014.

  python3 run_smc.py           # taker 9 bps/côté
  python3 run_smc.py --maker   # maker 4 bps/côté
"""
import sys
import numpy as np
import engine as E
import metrics as M
from smc_ict import make_smc_ict

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
TFS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]
WARMUP = 50

CONFIGS = [
    ("ICT COMPLET (target structurel + OTE 0.62)", dict(structural_target=True, entry_depth=0.62)),
    ("ICT OTE 0.5 (équilibre)", dict(structural_target=True, entry_depth=0.5)),
    ("ICT OTE 0.79 (discount profond)", dict(structural_target=True, entry_depth=0.79)),
    ("ICT RR fixe 2R (target structurel OFF — ancienne variante)",
     dict(structural_target=False, entry_depth=0.62, rr=2.0)),
]


def run_config(kwargs, cfg):
    rows = []
    for sym in SYMS:
        for tf in TFS:
            d = E.load_ohlcv(sym, tf)
            if d is None or len(d["c"]) < WARMUP + 30:
                continue
            fn = make_smc_ict(d, **kwargs)
            res = E.run_backtest(d, fn, cfg, params={}, warmup=WARMUP)
            m = M.compute(res, tf, bench_close=d["c"], warmup=WARMUP)
            if m.get("degenerate") or m.get("n_trades", 0) == 0:
                rows.append({"sym": sym, "tf": tf, "empty": True, "nt": m.get("n_trades", 0)})
                continue
            rows.append({"sym": sym, "tf": tf, "nt": m["n_trades"],
                         "ret": m.get("total_return_pct"), "sh": m.get("sharpe"),
                         "pf": m.get("profit_factor"), "wr": m.get("win_rate_pct"),
                         "bh_sh": m.get("bh_sharpe"), "beat_sh": m.get("beats_bh_sharpe"),
                         "beat_dd": m.get("beats_bh_drawdown"),
                         "lp": m.get("long_pnl_usd"), "sp_pnl": m.get("short_pnl_usd")})
    return rows


def summarize(name, rows):
    live = [r for r in rows if not r.get("empty")]
    empt = [r for r in rows if r.get("empty")]
    print(f"\n### {name}   ({len(live)} cellules tradées, {len(empt)} vides)")
    if not live:
        print("   (aucune cellule tradée — setups trop rares sur toutes les cellules)")
        return None
    rets = [r["ret"] for r in live if r["ret"] is not None]
    pfs = [r["pf"] for r in live if r["pf"] is not None]
    shs = [r["sh"] for r in live if r["sh"] is not None]
    beat_sh = sum(1 for r in live if r.get("beat_sh"))
    beat_both = sum(1 for r in live if r.get("beat_sh") and r.get("beat_dd"))
    pos = sum(1 for x in rets if x > 0)
    tot_l = sum(r["lp"] for r in live if r.get("lp") is not None)
    tot_s = sum(r["sp_pnl"] for r in live if r.get("sp_pnl") is not None)
    med_nt = np.median([r["nt"] for r in live])
    print(f"   trades/cellule médian {med_nt:.0f}   |   net-positifs {pos}/{len(rets)}   |   PF médian {np.median(pfs):.2f}")
    print(f"   Sharpe médian système {np.median(shs):+.2f}   |   bat B&H en Sharpe {beat_sh}/{len(live)}   |   Sharpe+DD {beat_both}/{len(live)}")
    print(f"   PnL total LONG {tot_l:+.0f}$  SHORT {tot_s:+.0f}$  (short>0 ? {'oui' if tot_s > 0 else 'NON = beta long'})")
    # robustes ≥15 trades
    rob = [r for r in live if r["nt"] >= 15]
    if rob:
        rr_pos = sum(1 for r in rob if r["ret"] > 0)
        print(f"   [échantillon robuste ≥15 trades] {len(rob)} cellules, net-positives {rr_pos}/{len(rob)}, "
              f"bat B&H Sharpe {sum(1 for r in rob if r.get('beat_sh'))}/{len(rob)}")
    return {"beat_both": beat_both, "n": len(live)}


def main():
    maker = "--maker" in sys.argv
    cfg = (E.ExecConfig(commission_bps=2, spread_bps=1, slippage_bps=1) if maker
           else E.ExecConfig(commission_bps=6, spread_bps=2, slippage_bps=1))
    print(f"===== SMC/ICT (machine à états causale) vs BUY-AND-HOLD — "
          f"{'MAKER 4bps' if maker else 'TAKER 9bps'}/côté =====")
    print("Critère d'edge : PF>1 + net-positifs majoritaires + battre le B&H en Sharpe ET DD + gagner en short.")
    for name, kw in CONFIGS:
        summarize(name, run_config(kw, cfg))


if __name__ == "__main__":
    main()
