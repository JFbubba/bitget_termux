"""Strategy Tester Python — moteur de backtest ÉVÉNEMENTIEL inspiré du MT5
Strategy Tester, mais sur les VRAIES données Bitget (data_history/) et les frais
Bitget. LECTURE SEULE, aucun ordre réel.

Fidélité au MT5 tester :
- décision à la CLÔTURE de la barre t -> exécution à l'OUVERTURE de t+1 (anti look-ahead) ;
- prix de fill = open ± demi-spread ± slippage (côté défavorable) ;
- SL/TP vérifiés INTRABAR via high/low de chaque barre (mode "ohlc") ;
- commission (bps) à l'entrée ET à la sortie, funding (bps/barre) pour le perp ;
- equity marquée au marché (mark-to-market) à chaque clôture ;
- si SL et TP touchés dans la même barre -> on suppose SL d'abord (pessimiste).

Contrat de stratégie (comme un EA MQL5 OnTick, mais causal) :
    strategy_fn(ctx) -> dict | None
    ctx = {'i', 'o','h','l','c','v' (arrays causaux [0..i]), 'position' (+1/-1/0), 'params'}
    retour = {'signal': +1|-1|0, 'sl': frac|None, 'tp': frac|None}  ('sl'/'tp' en fraction, ex 0.02)
             None ou {'signal': None} = conserver la position courante.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import candles_history as ch  # noqa: E402


@dataclass
class ExecConfig:
    capital: float = 10_000.0
    exposure: float = 1.0          # fraction de l'equity engagée (1.0 = plein, >1 = levier)
    spread_bps: float = 2.0        # demi-spread appliqué au fill
    commission_bps: float = 6.0    # par côté (taker Bitget futures ~6 bps)
    slippage_bps: float = 1.0
    funding_bps_per_bar: float = 0.0   # coût de portage /barre (perp) — 0 par défaut
    default_sl: float | None = None    # SL/TP par défaut si la stratégie n'en fournit pas
    default_tp: float | None = None


@dataclass
class Trade:
    entry_i: int; exit_i: int; direction: int
    entry: float; exit: float; ret: float; pnl: float
    bars: int; reason: str


@dataclass
class Result:
    equity: np.ndarray = field(default_factory=lambda: np.array([]))
    trades: list = field(default_factory=list)
    cfg: ExecConfig = None
    meta: dict = field(default_factory=dict)


def load_ohlcv(sym, tf, cap=20000):
    rows = ch.load(sym, tf)
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r[0])[-cap:]
    a = np.array(rows, dtype=float)
    return {"o": a[:, 1], "h": a[:, 2], "l": a[:, 3], "c": a[:, 4], "v": a[:, 5]}


def run_backtest(ohlcv, strategy_fn, cfg: ExecConfig, params=None, warmup=160):
    o, h, l, c = ohlcv["o"], ohlcv["h"], ohlcv["l"], ohlcv["c"]
    n = len(c)
    fee = (cfg.commission_bps + cfg.spread_bps + cfg.slippage_bps) / 1e4   # coût par côté (fraction)
    fund = cfg.funding_bps_per_bar / 1e4
    cash = cfg.capital
    pos = None                      # dict: dir, entry, notional, sl, tp, entry_i
    equity_curve = np.full(n, cfg.capital, dtype=float)
    trades = []

    def close_pos(i, exit_price, reason):
        nonlocal cash, pos
        d = pos["dir"]
        ret = d * (exit_price / pos["entry"] - 1.0)
        gross = ret * pos["notional"]
        cost = fee * pos["notional"]                # sortie
        cash += gross - cost
        trades.append(Trade(pos["entry_i"], i, d, pos["entry"], exit_price,
                            ret, gross - cost - pos["entry_cost"], i - pos["entry_i"], reason))
        pos = None

    for t in range(warmup, n - 1):
        # --- 1. gérer SL/TP INTRABAR sur la barre t (position déjà ouverte) ---
        if pos is not None:
            hit = None
            if pos["dir"] == 1:
                if pos["sl"] and l[t] <= pos["sl"]:
                    hit = (pos["sl"], "SL")
                elif pos["tp"] and h[t] >= pos["tp"]:
                    hit = (pos["tp"], "TP")
            else:
                if pos["sl"] and h[t] >= pos["sl"]:
                    hit = (pos["sl"], "SL")
                elif pos["tp"] and l[t] <= pos["tp"]:
                    hit = (pos["tp"], "TP")
            if hit:
                close_pos(t, hit[0], hit[1])
            else:
                cash -= fund * pos["notional"]      # funding/barre tant qu'ouvert

        # --- 2. décision de la stratégie à la CLÔTURE de t ---
        ctx = {"i": t, "o": o[:t + 1], "h": h[:t + 1], "l": l[:t + 1],
               "c": c[:t + 1], "v": ohlcv["v"][:t + 1],
               "position": pos["dir"] if pos else 0, "params": params or {}}
        try:
            sig = strategy_fn(ctx) or {}
        except Exception:
            sig = {}
        target = sig.get("signal", None)

        # --- 3. exécution à l'OUVERTURE de t+1 ---
        if target is not None:
            cur = pos["dir"] if pos else 0
            if target != cur:
                fill_close = o[t + 1]
                if pos is not None:                 # fermer l'existante
                    exitp = fill_close * (1 - np.sign(pos["dir"]) * (cfg.spread_bps + cfg.slippage_bps) / 1e4)
                    close_pos(t + 1, exitp, "signal")
                if target != 0:                     # ouvrir la nouvelle
                    fillp = fill_close * (1 + np.sign(target) * (cfg.spread_bps + cfg.slippage_bps) / 1e4)
                    notional = cash * cfg.exposure
                    sl_frac = sig.get("sl", cfg.default_sl)
                    tp_frac = sig.get("tp", cfg.default_tp)
                    pos = {"dir": int(np.sign(target)), "entry": fillp, "notional": notional,
                           "entry_i": t + 1, "entry_cost": fee * notional,
                           "sl": fillp * (1 - np.sign(target) * sl_frac) if sl_frac else None,
                           "tp": fillp * (1 + np.sign(target) * tp_frac) if tp_frac else None}
                    cash -= pos["entry_cost"]

        # --- 4. mark-to-market equity à la clôture de t (ou t+1) ---
        mtm = 0.0
        if pos is not None:
            mtm = pos["dir"] * (c[t] / pos["entry"] - 1.0) * pos["notional"]
        equity_curve[t] = cash + mtm

    if pos is not None:                             # clôturer en fin de série
        close_pos(n - 1, c[-1], "fin")
    equity_curve[-1] = cash
    equity_curve[:warmup] = cfg.capital
    return Result(equity=equity_curve, trades=trades, cfg=cfg,
                  meta={"n": n, "warmup": warmup})
