"""Comparaison de variantes de la stratégie ADM sur l'échelle COMPLÈTE de TF (ERR-001)
et 6 symboles crypto, NET DE FRAIS Bitget. Teste le système entier (ERR-002) puis
attribue par ablation des filtres. Agrégats robustes (médianes), pas de cherry-pick.

  python3 run_adm_compare.py           # taker 9 bps/côté
  python3 run_adm_compare.py --maker   # maker 4 bps/côté (sensibilité aux frais)
"""
import sys
import numpy as np
import engine as E
import metrics as M
from adm_strategy import make_adm

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
TFS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]

# variantes : (nom, kwargs de make_adm)
VARIANTS = [
    ("littéral fiche (cross K=1, pente ON, EMA200 ON)",
     dict(cross_lookback=1, require_rising=True, use_ema200=True)),
    ("cross récent K=3 (pente ON, EMA200 ON)",
     dict(cross_lookback=3, require_rising=True, use_ema200=True)),
    ("cross récent K=5 (pente ON, EMA200 ON)",
     dict(cross_lookback=5, require_rising=True, use_ema200=True)),
    ("cross récent K=3, SANS pente ADX (EMA200 ON)",
     dict(cross_lookback=3, require_rising=False, use_ema200=True)),
    ("cross récent K=3, pente ON, SANS EMA200",
     dict(cross_lookback=3, require_rising=True, use_ema200=False)),
    ("DMI classique nu (cross K=1, ADX>25, sans pente, sans EMA200)",
     dict(cross_lookback=1, require_rising=False, use_ema200=False)),
]


def run_variant(kwargs, cfg):
    warmup = 210 if kwargs.get("use_ema200", True) else 40
    cells = []
    for sym in SYMS:
        for tf in TFS:
            d = E.load_ohlcv(sym, tf)
            if d is None or len(d["c"]) < warmup + 30:
                continue
            fn = make_adm(d, period=14, adx_min=25.0, atr_mult=2.0, **kwargs)
            res = E.run_backtest(d, fn, cfg, params={}, warmup=warmup)
            m = M.compute(res, tf)
            if m.get("degenerate") or m.get("n_trades", 0) == 0:
                cells.append({"tf": tf, "empty": True})
                continue
            cells.append({"tf": tf, "ret": m.get("total_return_pct"),
                          "pf": m.get("profit_factor"), "sh": m.get("sharpe"),
                          "nt": m.get("n_trades")})
    return cells


def summarize(cells):
    live = [c for c in cells if not c.get("empty")]
    rets = [c["ret"] for c in live if c["ret"] is not None]
    pfs = [c["pf"] for c in live if c["pf"] is not None]
    shs = [c["sh"] for c in live if c["sh"] is not None]
    nts = [c["nt"] for c in live if c["nt"] is not None]
    pos = sum(1 for x in rets if x > 0)
    return {
        "cells": len(live), "trades": int(sum(nts)),
        "posfrac": (pos, len(rets)),
        "ret_med": np.median(rets) if rets else float("nan"),
        "ret_mean": np.mean(rets) if rets else float("nan"),
        "pf_med": np.median(pfs) if pfs else float("nan"),
        "sh_med": np.median(shs) if shs else float("nan"),
    }


def main():
    maker = "--maker" in sys.argv
    cfg = (E.ExecConfig(commission_bps=2, spread_bps=1, slippage_bps=1) if maker
           else E.ExecConfig(commission_bps=6, spread_bps=2, slippage_bps=1))
    tag = "MAKER 4 bps/côté" if maker else "TAKER 9 bps/côté"
    print(f"===== ADM — comparaison de variantes — {tag} =====")
    print(f"{'variante':58} {'cell':>4} {'trades':>6} {'net+':>7} {'ret_méd':>8} {'ret_moy':>8} {'PF_méd':>6} {'Sh_méd':>7}")
    print("-" * 118)
    best = None
    for name, kwargs in VARIANTS:
        s = summarize(run_variant(kwargs, cfg))
        p, tot = s["posfrac"]
        print(f"{name:58} {s['cells']:>4} {s['trades']:>6} {p:>3}/{tot:<3} "
              f"{s['ret_med']:>+8.2f} {s['ret_mean']:>+8.2f} {s['pf_med']:>6.2f} {s['sh_med']:>+7.2f}")
        cand = (s["pf_med"], s["ret_med"])
        if best is None or cand > best[1]:
            best = (name, cand, s)
    print("-" * 118)
    print("Lecture : PF_méd>1 ET net+ majoritaire ET ret_moy>0 = edge net de frais crédible.")
    print(f"Meilleure variante (PF médian) : {best[0]}  → PF_méd {best[2]['pf_med']:.2f}, "
          f"ret_moy {best[2]['ret_mean']:+.2f}%, net+ {best[2]['posfrac'][0]}/{best[2]['posfrac'][1]}")


if __name__ == "__main__":
    main()
