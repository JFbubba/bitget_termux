"""trade_plan.py — CLI plan de trade à stop STRUCTUREL seul (1re génération). SAFE.
Logique partagée extraite dans decision_core (refactor des 4 clones, iso-comportement)."""

from candle_reader import get_bitget_candles

import decision_core


def analyze_decision(symbol="BTCUSDT"):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    return decision_core.analyze(symbol, candles, with_atr=False,
                                 with_ema_levels=True, include_candles=True)


def build_trade_plan(analysis):
    return decision_core.build_plan(analysis, rr=2.0, use_atr_stop=False)


if __name__ == "__main__":
    analysis = analyze_decision("BTCUSDT")
    plan = build_trade_plan(analysis)

    print("=== BITGET TRADE PLAN ===")
    print(f"Symbole: {analysis['symbol']}")
    print(f"Décision: {analysis['decision']}")
    print(f"Score: {analysis['score']}")
    print(f"RSI 14: {analysis['rsi']:.2f}")
    print(f"Distance EMA9/EMA21: {analysis['ema_distance_percent']:.4f}%")
    print()

    print("Raisons:")
    for reason in analysis["reasons"]:
        print(f"- {reason}")

    print()

    if plan is None:
        print("Aucun plan de trade théorique : signal insuffisant ou risque invalide.")
    else:
        print("Plan théorique:")
        print(f"Side: {plan['side']}")
        print(f"Entrée: {plan['entry']:.2f}")
        print(f"Stop-loss: {plan['stop_loss']:.2f}")
        print(f"Take-profit: {plan['take_profit']:.2f}")
        print(f"Risque: {plan['risk_percent']:.3f}%")
        print(f"Gain potentiel: {plan['reward_percent']:.3f}%")
        print(f"Ratio reward/risk: {plan['reward_risk_ratio']:.2f}")
        print()
        print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
