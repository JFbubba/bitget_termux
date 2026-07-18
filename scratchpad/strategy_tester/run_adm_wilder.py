"""Test du VRAI système de Wilder (machine à états, adm_wilder.py) sur l'échelle
COMPLÈTE de TF (ERR-001) × 6 symboles crypto, NET DE FRAIS Bitget, AVEC benchmark
BUY-AND-HOLD — pour distinguer un EDGE d'un simple BETA de tendance.

  python3 run_adm_wilder.py            # taker 9 bps/côté
  python3 run_adm_wilder.py --maker    # maker 4 bps/côté

Un trend-follower quasi-permanent en bull market affiche un gros rendement SANS edge :
la question n'est pas « ret>0 » mais « bat-il le B&H en rendement AJUSTÉ DU RISQUE
(Sharpe, max drawdown) ? ». On mesure aussi le split long/short (le PnL vient-il des
shorts, ou seulement des longs = beta ?).
"""
import sys
import numpy as np
import engine as E
import metrics as M
from adm_wilder import make_adm_wilder

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
TFS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]

CONFIGS = [
    ("Wilder FIDÈLE (extreme+reverse+ADX↑+EMA200)",
     dict(entry_trigger="extreme", reverse=True, require_rising=True, use_ema200=True)),
    ("Wilder sans filtre pente ADX",
     dict(entry_trigger="extreme", reverse=True, require_rising=False, use_ema200=True)),
    ("Wilder sans EMA200",
     dict(entry_trigger="extreme", reverse=True, require_rising=True, use_ema200=False)),
    ("Wilder sortie-flat (reverse=False)+exit ADX-drop",
     dict(entry_trigger="extreme", reverse=False, require_rising=True, use_ema200=True,
          exit_adx_drop=True)),
    ("[contraste] entrée IMMÉDIATE au croisement (ancien modèle)",
     dict(entry_trigger="immediate", reverse=True, require_rising=True, use_ema200=True)),
]


def buy_and_hold(c, warmup, bpy):
    """Rendement / Sharpe / maxDD d'un achat-conservation sur [warmup:] (même fenêtre)."""
    px = c[warmup:]
    if len(px) < 10:
        return None
    rets = np.diff(px) / px[:-1]
    rets = rets[np.isfinite(rets)]
    peak = np.maximum.accumulate(px)
    mdd = float(((px - peak) / peak).min())
    sd = np.std(rets)
    return {
        "ret": px[-1] / px[0] - 1.0,
        "sharpe": (np.mean(rets) / sd * np.sqrt(bpy)) if sd > 1e-12 else float("nan"),
        "mdd": mdd,
    }


def long_short_pnl(trades):
    lp = sum(t.pnl for t in trades if t.direction == 1)
    sp = sum(t.pnl for t in trades if t.direction == -1)
    return lp, sp


def run_config(kwargs, cfg):
    rows = []
    for sym in SYMS:
        for tf in TFS:
            d = E.load_ohlcv(sym, tf)
            warmup = 210 if kwargs.get("use_ema200", True) else 40
            if d is None or len(d["c"]) < warmup + 30:
                continue
            fn = make_adm_wilder(d, period=14, adx_min=25.0, atr_mult=2.0, **kwargs)
            res = E.run_backtest(d, fn, cfg, params={}, warmup=warmup)
            m = M.compute(res, tf)
            if m.get("degenerate") or m.get("n_trades", 0) == 0:
                continue
            bpy = M.BARS_PER_YEAR.get(tf, 8760)
            bh = buy_and_hold(np.asarray(d["c"], float), warmup, bpy)
            lp, sp = long_short_pnl(res.trades)
            rows.append({
                "sym": sym, "tf": tf, "nt": m["n_trades"],
                "ret": m.get("total_return_pct"), "sh": m.get("sharpe"),
                "mdd": m.get("max_drawdown_pct"), "expo": m.get("exposure_pct"),
                "pf": m.get("profit_factor"),
                "bh_ret": bh["ret"] * 100 if bh else None,
                "bh_sh": bh["sharpe"] if bh else None,
                "bh_mdd": bh["mdd"] * 100 if bh else None,
                "long_pnl": lp, "short_pnl": sp,
            })
    return rows


def summarize(name, rows):
    print(f"\n### {name}   ({len(rows)} cellules avec trades)")
    if not rows:
        print("   (aucune cellule tradée)")
        return
    # bat le B&H en Sharpe ? en drawdown (|mdd| plus petit) ?
    beat_sh = [r for r in rows if r["sh"] is not None and r["bh_sh"] is not None
               and r["sh"] > r["bh_sh"]]
    beat_dd = [r for r in rows if r["mdd"] is not None and r["bh_mdd"] is not None
               and abs(r["mdd"]) < abs(r["bh_mdd"])]
    beat_both = [r for r in rows if r in beat_sh and r in beat_dd]
    shs = [r["sh"] for r in rows if r["sh"] is not None]
    bhshs = [r["bh_sh"] for r in rows if r["bh_sh"] is not None]
    tot_long = sum(r["long_pnl"] for r in rows)
    tot_short = sum(r["short_pnl"] for r in rows)
    print(f"   Sharpe médian système {np.median(shs):+.2f}  vs  B&H {np.median(bhshs):+.2f}")
    print(f"   bat B&H en Sharpe : {len(beat_sh)}/{len(rows)}   |   en drawdown : {len(beat_dd)}/{len(rows)}"
          f"   |   LES DEUX : {len(beat_both)}/{len(rows)}")
    print(f"   PnL total  LONG {tot_long:+.0f} $   SHORT {tot_short:+.0f} $   "
          f"(short>0 ? {'oui' if tot_short > 0 else 'NON → edge = beta long'})")
    # top cellules par Sharpe pour inspection
    top = sorted([r for r in rows if r["sh"] is not None], key=lambda r: -r["sh"])[:5]
    print("   top-5 Sharpe (sym tf | sys ret/Sh/DD | B&H ret/Sh/DD | expo | short$):")
    for r in top:
        print(f"     {r['sym']:8} {r['tf']:>3} | {r['ret']:+7.0f}%/{r['sh']:+.2f}/{r['mdd']:+.0f}% "
              f"| B&H {r['bh_ret']:+7.0f}%/{r['bh_sh']:+.2f}/{r['bh_mdd']:+.0f}% "
              f"| expo {r['expo']:.0f}% | short {r['short_pnl']:+.0f}$")


def main():
    maker = "--maker" in sys.argv
    cfg = (E.ExecConfig(commission_bps=2, spread_bps=1, slippage_bps=1) if maker
           else E.ExecConfig(commission_bps=6, spread_bps=2, slippage_bps=1))
    print(f"===== ADM Wilder (machine à états) vs BUY-AND-HOLD — "
          f"{'MAKER 4bps' if maker else 'TAKER 9bps'}/côté =====")
    print("Critère d'edge : battre le B&H en Sharpe ET en drawdown, et gagner AUSSI en short.")
    for name, kw in CONFIGS:
        summarize(name, run_config(kw, cfg))


if __name__ == "__main__":
    main()
