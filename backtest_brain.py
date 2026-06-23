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
    swarm_brain.agent_technicals, recalculé sur l'historique. Les clôtures sont
    débruitées (Savitzky–Golay) avant calcul des indicateurs (arXiv:2506.05764)."""
    closes = [c["close"] for c in window]
    try:
        closes = indicators.savitzky_golay(closes, window=11, poly=2)
    except Exception:
        pass
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


def walk_forward(returns, k=5):
    """Découpe `returns` en k tranches séquentielles et retourne le rendement
    composé de chaque tranche (out-of-sample « marche en avant »). Pur."""
    n = len(returns)
    if n < k:
        return []
    bounds = [round(i * n / k) for i in range(k + 1)]
    folds = []
    for i in range(k):
        eq = 1.0
        for r in returns[bounds[i]:bounds[i + 1]]:
            eq *= (1 + r)
        folds.append(round(eq - 1, 5))
    return folds


def pbo(returns_by_config, n_blocks=8):
    """Probability of Backtest Overfitting (Bailey & López de Prado, CSCV). Pur.

    returns_by_config : {label: [rendements par pas]} (mêmes longueurs). On forme
    toutes les combinaisons IS/OOS de blocs ; pour chacune on prend la config la
    meilleure IN-SAMPLE et on regarde son rang OUT-OF-SAMPLE. Si la meilleure IS
    finit sous la médiane OOS (logit ≤ 0), c'est un signe de surapprentissage.
    PBO = fraction de telles combinaisons. PBO élevé (≈>0.5) = peu fiable.
    """
    import itertools
    import math
    import statistics
    labels = list(returns_by_config)
    series = [returns_by_config[l] for l in labels]
    if len(series) < 2:
        return {"pbo": None, "n_combos": 0, "n_configs": len(series), "n_blocks": n_blocks}
    T = min(len(s) for s in series)
    series = [s[:T] for s in series]
    n_blocks = max(2, min(n_blocks, T))
    if n_blocks % 2:
        n_blocks -= 1
    bounds = [round(i * T / n_blocks) for i in range(n_blocks + 1)]
    blocks = [list(range(bounds[i], bounds[i + 1])) for i in range(n_blocks)]

    def perf(idxs, c):
        r = [series[c][i] for i in idxs]
        if not r:
            return 0.0
        m = statistics.fmean(r)
        sd = statistics.pstdev(r) if len(r) > 1 else 0.0
        return (m / sd) if sd > 0 else m          # Sharpe-ish (ou moyenne si σ=0)

    half = n_blocks // 2
    lam = []
    for IS in itertools.combinations(range(n_blocks), half):
        OOS = [b for b in range(n_blocks) if b not in IS]
        is_idx = [i for b in IS for i in blocks[b]]
        oos_idx = [i for b in OOS for i in blocks[b]]
        is_perf = [perf(is_idx, c) for c in range(len(series))]
        oos_perf = [perf(oos_idx, c) for c in range(len(series))]
        best = max(range(len(series)), key=lambda c: is_perf[c])
        order = sorted(range(len(series)), key=lambda c: oos_perf[c])  # croissant
        rank = order.index(best) + 1
        omega = min(max(rank / (len(series) + 1), 1e-6), 1 - 1e-6)
        lam.append(math.log(omega / (1 - omega)))
    pbo_val = sum(1 for x in lam if x <= 0) / len(lam) if lam else 0.0
    return {"pbo": round(pbo_val, 4), "n_combos": len(lam),
            "n_configs": len(series), "n_blocks": n_blocks}


def run_backtest(symbol="BTCUSDT", timeframe="1H", limit=500, horizon=4, fee=0.0006, warmup=55):
    import technicals
    candles = technicals.fetch_candles(symbol, timeframe, limit)
    closes = [c["close"] for c in candles]
    if len(closes) <= warmup + horizon:
        return {"error": "pas assez de bougies", "symbol": symbol, "timeframe": timeframe}
    # signaux techniques reconstruits, calculés une seule fois
    sig_at = {i: technical_signal(candles[:i + 1]) for i in range(warmup, len(closes) - 1)}
    rets_all = forward_returns(closes, horizon)
    # backtest principal : trades non chevauchants (pas = horizon)
    signals, rets = [], []
    i = warmup
    while i < len(closes) - horizon:
        signals.append(sig_at[i])
        rets.append(rets_all[i])
        i += horizon
    stats = evaluate(signals, rets, fee)
    bh = (closes[-1] - closes[warmup]) / closes[warmup] if closes[warmup] else 0.0
    # robustesse anti-surapprentissage : famille de seuils d'action -> CSCV/PBO + walk-forward
    fwd1 = [(closes[j + 1] - closes[j]) / closes[j] for j in range(warmup, len(closes) - 1)]
    bar_sigs = [sig_at[j] for j in range(warmup, len(closes) - 1)]
    family = {}
    for th in (0.1, 0.2, 0.3, 0.4, 0.5):
        family[f"th={th}"] = [((1 if s > th else -1 if s < -th else 0) * r
                               - (fee if abs(s) > th else 0.0)) for s, r in zip(bar_sigs, fwd1)]
    pbo_res = pbo(family, n_blocks=8)
    wf = walk_forward(family["th=0.2"], k=5)
    stats.update({"symbol": symbol, "timeframe": timeframe, "horizon": horizon,
                  "bars": len(candles), "fee": fee, "buy_hold_return": round(bh, 5),
                  "signal": "technical (couche reconstructible du cerveau)",
                  "pbo": pbo_res["pbo"], "pbo_combos": pbo_res["n_combos"],
                  "walk_forward": wf,
                  "folds_positive": round(sum(1 for x in wf if x > 0) / len(wf), 3) if wf else 0.0})
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
    ]
    pbo_v = s.get("pbo")
    if pbo_v is not None:
        verdict = "robuste" if pbo_v < 0.3 else "douteux" if pbo_v < 0.5 else "PROBABLEMENT SURAPPRIS"
        lines.append(f"PBO (surapprentissage) : {pbo_v:.2f} sur {s.get('pbo_combos', 0)} combinaisons → {verdict}")
    wf = s.get("walk_forward")
    if wf:
        folds = " ".join(f"{x * 100:+.1f}%" for x in wf)
        lines.append(f"Walk-forward (5 tranches) : {folds} · gagnantes {s.get('folds_positive', 0) * 100:.0f}%")
    lines += [
        "",
        "⚠️ Rejoue UNIQUEMENT l'agent technique (seul reconstructible sur l'historique).",
        "PBO/walk-forward = garde-fous anti-surapprentissage (CSCV, López de Prado).",
        "Lecture seule. Aucun ordre. VERDICT: SAFE",
    ]
    return "\n".join(lines)


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "1H"
    print(build_report(run_backtest(symbol, timeframe)))


if __name__ == "__main__":
    main()
