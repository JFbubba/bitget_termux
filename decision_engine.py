"""decision_engine.py — CLI d'analyse EMA/RSI (1re génération). SAFE, lecture seule.
Logique partagée extraite dans decision_core (refactor des 4 clones, iso-comportement)."""

from candle_reader import get_bitget_candles

import decision_core


def analyze_decision(symbol="BTCUSDT"):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    return decision_core.analyze(symbol, candles, with_atr=False,
                                 with_ema_levels=True, include_candles=False)


if __name__ == "__main__":
    result = analyze_decision("BTCUSDT")

    print("=== BITGET DECISION ENGINE ===")
    print(f"Symbole: {result['symbol']}")
    print(f"Dernier close: {result['last_close']:.2f}")
    print(f"EMA 9: {result['ema9']:.2f}")
    print(f"EMA 21: {result['ema21']:.2f}")
    print(f"Distance EMA9/EMA21: {result['ema_distance_percent']:.4f}%")
    print(f"RSI 14: {result['rsi']:.2f}")
    print(f"Score: {result['score']}")
    print(f"Décision: {result['decision']}")
    print("Raisons:")
    for reason in result["reasons"]:
        print(f"- {reason}")
