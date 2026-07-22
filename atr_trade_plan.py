"""atr_trade_plan.py — CLI plan de trade à stop ATR, ratio TP configurable (1re gén.). SAFE.
Logique partagée extraite dans decision_core (refactor des 4 clones, iso-comportement) ;
reste ici : le knob _rr (env ATR_TRADE_RR > config > 1.5, §68 B), évalué à CHAQUE appel."""

from candle_reader import get_bitget_candles

import decision_core


def _rr():
    """Ratio take-profit / risque (§68 B). env ATR_TRADE_RR > config > 1.5 (optimum mesuré)."""
    import os
    v = os.getenv("ATR_TRADE_RR")
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    try:
        from config_utils import cfg
        return float(cfg("ATR_TRADE_RR", 1.5))
    except Exception:
        return 1.5


def analyze_decision(symbol="BTCUSDT"):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    return decision_core.analyze(symbol, candles, with_atr=True,
                                 with_ema_levels=False, include_candles=True)


def build_trade_plan(analysis):
    return decision_core.build_plan(analysis, rr=_rr(), use_atr_stop=True)


if __name__ == "__main__":
    analysis = analyze_decision("BTCUSDT")
    plan = build_trade_plan(analysis)

    print("=== BITGET ATR TRADE PLAN ===")
    print(f"Symbole: {analysis['symbol']}")
    print(f"Décision: {analysis['decision']}")
    print(f"Score: {analysis['score']}")
    print(f"RSI 14: {analysis['rsi']:.2f}")
    print(f"Distance EMA9/EMA21: {analysis['ema_distance_percent']:.4f}%")
    print(f"ATR 14: {analysis['atr']:.2f}")
    print(f"ATR %: {analysis['atr_percent']:.4f}%")
    print()

    print("Raisons:")
    for reason in analysis["reasons"]:
        print(f"- {reason}")

    print()

    if plan is None:
        print("Aucun plan de trade théorique : signal insuffisant ou risque invalide.")
    else:
        print("Plan théorique avec protection ATR:")
        print(f"Side: {plan['side']}")
        print(f"Entrée: {plan['entry']:.2f}")
        print(f"Stop structurel: {plan['structural_stop']:.2f}")
        print(f"Stop ATR 1.5x: {plan['atr_stop']:.2f}")
        print(f"Stop-loss retenu: {plan['stop_loss']:.2f}")
        print(f"Take-profit: {plan['take_profit']:.2f}")
        print(f"Risque: {plan['risk_percent']:.3f}%")
        print(f"Gain potentiel: {plan['reward_percent']:.3f}%")
        print(f"Ratio reward/risk: {plan['reward_risk_ratio']:.2f}")
        print()
        print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
