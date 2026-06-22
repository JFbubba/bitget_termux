"""
backtest_brain.py — backtest hors-ligne du signal du cerveau (LECTURE SEULE).

Classement : SAFE. Aucun ordre. Rejoue un signal directionnel sur l'historique
des bougies et le compare aux rendements réalisés (taux de réussite, rendement,
Sharpe, drawdown) face au buy & hold.

⚠️ HONNÊTETÉ DU PÉRIMÈTRE : seul l'agent TECHNIQUE du cerveau est reconstructible
sur l'historique (EMA/RSI/biais volume se recalculent depuis les bougies). Les
autres agents (order-flow, dérivés, sentiment, macro, liquidations) n'ont pas de
flux historique ici, donc ce backtest valide la COUCHE TECHNIQUE, pas l'essaim
complet. Le harnais (evaluate) est générique : tout autre signal reconstructible
peut y être branché ensuite.

evaluate() et forward_returns() sont PURS et testables ; run_backtest() ajoute
le réseau (bougies).

CLI : python backtest_brain.py [SYMBOL] [TIMEFRAME]
"""

import math
import sys

import indicators


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def technical_signal(window):
    """Vote technique [-1..1] depuis une fenêtre de bougies. Miroir de
    swarm_brain.agent_technicals, recalculé sur l'historique."""
    closes = [c["close"] for c in window]
    vote = 0.0
    try:
        if indicators.ema(closes, 20)[-1] > indicators.ema(closes, 50)[-1]:
            vote += 0.5
        else:
            vote -= 0.5
    except Exception:
        pass
    try:
        rsi = indicators.calculate_rsi(closes)[-1]
        vote += 0.3 if rsi < 35 else -0.3 if rsi > 65 else 0.0
    except Exception:
        pass
    try:
        vote += _clamp(indicators.volume_bias_score(window) / 10.0) * 0.4
    except Exception:
        pass
    return _clamp(vote)


def forward_returns(closes, horizon):
    """Rendement à `horizon` barres en avant pour chaque indice. Pur."""
    return [((closes[i + horizon] - closes[i]) / closes[i]) if closes[i] else 0.0
            for i in range(len(closes) - horizon)]


def evaluate(signals, rets, fee=0.0):
    """Évalue une suite de (signal, rendement futur) en trades indépendants. Pur.

    position = signe(signal) ; pnl = position*rendement - frais. Compose l'équité.
    """
    trades = correct = 0
    n_long = n_short = 0
    sum_long = sum_short = 0.0
    pnls = []
    equity = 1.0
    curve = [equity]
    for s, r in zip(signals, rets):
        pos = 1 if s > 0 else -1 if s < 0 else 0
        if pos == 0:
            continue
        trades += 1
        pnl = pos * r - fee
        pnls.append(pnl)
        if r != 0 and (pos > 0) == (r > 0):
            correct += 1
        if pos > 0:
            sum_long += r
            n_long += 1
        else:
            sum_short += r
            n_short += 1
        equity *= (1 + pnl)
        curve.append(equity)
    avg = (sum(pnls) / len(pnls)) if pnls else 0.0
    sd = (sum((x - avg) ** 2 for x in pnls) / len(pnls)) ** 0.5 if pnls else 0.0
    sharpe = (avg / sd * math.sqrt(len(pnls))) if sd > 0 else 0.0
    peak, mdd = curve[0], 0.0
    for e in curve:
        peak = max(peak, e)
        if peak > 0:
            mdd = min(mdd, e / peak - 1)
    return {
        "trades": trades,
        "hit_rate": round(correct / trades, 4) if trades else 0.0,
        "avg_return_long": round(sum_long / n_long, 5) if n_long else None,
        "avg_return_short": round(sum_short / n_short, 5) if n_short else None,
        "total_return": round(equity - 1, 5),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(mdd, 4),
        "final_equity": round(equity, 4),
    }


def run_backtest(symbol="BTCUSDT", timeframe="1H", limit=500, horizon=4, fee=0.0006, warmup=55):
    import technicals
    candles = technicals.fetch_candles(symbol, timeframe, limit)
    closes = [c["close"] for c in candles]
    if len(closes) <= warmup + horizon:
        return {"error": "pas assez de bougies", "symbol": symbol, "timeframe": timeframe}
    rets_all = forward_returns(closes, horizon)
    signals, rets = [], []
    i = warmup
    while i < len(closes) - horizon:          # pas = horizon -> trades non chevauchants
        signals.append(technical_signal(candles[:i + 1]))
        rets.append(rets_all[i])
        i += horizon
    stats = evaluate(signals, rets, fee)
    bh = (closes[-1] - closes[warmup]) / closes[warmup] if closes[warmup] else 0.0
    stats.update({"symbol": symbol, "timeframe": timeframe, "horizon": horizon,
                  "bars": len(candles), "fee": fee, "buy_hold_return": round(bh, 5),
                  "signal": "technical (couche reconstructible du cerveau)"})
    return stats


def build_report(s):
    if s.get("error"):
        return f"=== BACKTEST {s.get('symbol', '')} ===\n{s['error']}\nVERDICT: SAFE"
    edge = s["total_return"] - s["buy_hold_return"]
    lines = [
        f"=== BACKTEST CERVEAU (technique) {s['symbol']} {s['timeframe']} ===",
        f"Barres {s['bars']} | horizon {s['horizon']} | frais {s['fee'] * 100:.3f}%/trade",
        f"Trades {s['trades']} | réussite {s['hit_rate'] * 100:.1f}%",
        f"Rendement {s['total_return'] * 100:+.2f}%  |  buy&hold {s['buy_hold_return'] * 100:+.2f}%  "
        f"(edge {edge * 100:+.2f}%)",
        f"Sharpe {s['sharpe']} | max DD {s['max_drawdown'] * 100:.1f}%",
        f"Long {('%+.2f%%' % (s['avg_return_long'] * 100)) if s['avg_return_long'] is not None else '—'}/trade"
        f" · Short {('%+.2f%%' % (s['avg_return_short'] * 100)) if s['avg_return_short'] is not None else '—'}/trade",
        "",
        "⚠️ Rejoue UNIQUEMENT l'agent technique (seul reconstructible sur l'historique).",
        "Lecture seule. Aucun ordre. VERDICT: SAFE",
    ]
    return "\n".join(lines)


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "1H"
    print(build_report(run_backtest(symbol, timeframe)))


if __name__ == "__main__":
    main()
