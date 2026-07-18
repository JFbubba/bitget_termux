"""Backtest de la stratégie ADM (ADX/DMI de Wilder) sur l'échelle COMPLÈTE de
timeframes (ERR-001) et plusieurs symboles crypto, NET DE FRAIS Bitget.

  python3 run_adm.py               # taker réaliste (9 bps/côté), params canoniques fiche
  python3 run_adm.py --maker       # frais maker (4 bps/côté) — test de sensibilité
  python3 run_adm.py --no-ema200   # ablation : retire le filtre de tendance EMA200
  python3 run_adm.py --reverse     # renverse la position sur croisement inverse

Params canoniques (fiche) : ADX(14), seuil 25, pente ADX montante, filtre EMA200,
SL = 2×ATR(14), sortie sur croisement inverse OU ADX en baisse 3 barres.
"""
import sys
import numpy as np
import engine as E
import metrics as M
from adm_strategy import make_adm

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
TFS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]


def run_one(sym, tf, cfg, adm_kwargs, warmup):
    d = E.load_ohlcv(sym, tf)
    if d is None or len(d["c"]) < warmup + 30:
        return None
    fn = make_adm(d, **adm_kwargs)
    res = E.run_backtest(d, fn, cfg, params={}, warmup=warmup)
    m = M.compute(res, tf)
    return m


def main():
    maker = "--maker" in sys.argv
    no_ema = "--no-ema200" in sys.argv
    reverse = "--reverse" in sys.argv

    # frais : taker Bitget futures ~9 bps/côté (commission 6 + spread 2 + slippage 1) ;
    # maker ~4 bps/côté (commission 2 + spread 1 + slippage 1) — cf. mémoire exec=levier.
    cfg = (E.ExecConfig(commission_bps=2, spread_bps=1, slippage_bps=1) if maker
           else E.ExecConfig(commission_bps=6, spread_bps=2, slippage_bps=1))
    adm_kwargs = dict(period=14, adx_min=25.0, atr_mult=2.0,
                      use_ema200=not no_ema, reverse=reverse)
    warmup = 210 if not no_ema else 40

    tag = ("MAKER 4bps/côté" if maker else "TAKER 9bps/côté")
    tag += " · sans EMA200" if no_ema else " · EMA200 ON"
    tag += " · REVERSE" if reverse else ""
    print(f"=== Stratégie ADM (ADX/DMI Wilder) — {tag} ===")
    print("params: ADX(14)>25, pente montante, SL 2×ATR, sortie croisement/ADX-drop3\n")
    hdr = f"{'sym':9} {'tf':>4} {'trades':>6} {'ret%':>8} {'sharpe':>7} {'PF':>5} {'win%':>6} {'maxDD%':>8} {'expo%':>6}"
    print(hdr); print("-" * len(hdr))

    rows = []
    for sym in SYMS:
        for tf in TFS:
            m = run_one(sym, tf, cfg, adm_kwargs, warmup)
            if m is None:
                continue
            if m.get("degenerate") or m.get("n_trades", 0) == 0:
                print(f"{sym:9} {tf:>4} {m.get('n_trades',0):>6}   (aucun trade / dégénéré)")
                rows.append({**m, "sym": sym, "tf": tf, "empty": True})
                continue
            print(f"{sym:9} {tf:>4} {m['n_trades']:>6} {m.get('total_return_pct',0):>8.2f} "
                  f"{str(m.get('sharpe')):>7} {str(m.get('profit_factor')):>5} "
                  f"{str(m.get('win_rate_pct')):>6} {m.get('max_drawdown_pct',0):>8.2f} "
                  f"{m.get('exposure_pct',0):>6.1f}")
            rows.append({**m, "sym": sym, "tf": tf})

    # ---------- agrégat ----------
    live = [r for r in rows if not r.get("empty") and r.get("n_trades", 0) > 0]
    print("\n=== AGRÉGAT ===")
    print(f"cellules (sym×TF) avec trades : {len(live)} / {len(rows)}")
    if live:
        rets = [r["total_return_pct"] for r in live if r.get("total_return_pct") is not None]
        pfs = [r["profit_factor"] for r in live if r.get("profit_factor") is not None]
        shs = [r["sharpe"] for r in live if r.get("sharpe") is not None]
        pos = sum(1 for x in rets if x > 0)
        print(f"net-positifs (ret>0)          : {pos} / {len(rets)}  ({100*pos/max(len(rets),1):.0f}%)")
        print(f"rendement total  médian/moyen : {np.median(rets):+.2f}% / {np.mean(rets):+.2f}%")
        print(f"profit factor    médian       : {np.median(pfs):.2f}  (PF>1 = gagnant net)" if pfs else "PF: n/a")
        print(f"sharpe           médian       : {np.median(shs):+.2f}" if shs else "sharpe: n/a")
        # concentration par TF (la fiche prétend : mieux sur H1/H4/D1, pire <15m)
        print("\n  par TF (rendement médian net, PF médian, #cellules gagnantes) :")
        for tf in TFS:
            g = [r for r in live if r["tf"] == tf]
            if not g:
                continue
            gr = [r["total_return_pct"] for r in g if r.get("total_return_pct") is not None]
            gp = [r["profit_factor"] for r in g if r.get("profit_factor") is not None]
            wins = sum(1 for x in gr if x > 0)
            print(f"    {tf:>4} : ret méd {np.median(gr):+7.2f}%  PF méd {np.median(gp) if gp else float('nan'):.2f}  "
                  f"gagnants {wins}/{len(gr)}")


if __name__ == "__main__":
    main()
