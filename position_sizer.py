"""position_sizer.py — CLI plan de trade + money management (1re génération). SAFE.
Logique partagée extraite dans decision_core (refactor des 4 clones, iso-comportement) ;
reste ici : le sizing (calculate_position_size) et les constantes de démonstration."""

ACCOUNT_EQUITY_USDT = 100.0
RISK_PER_TRADE_PERCENT = 1.0


from candle_reader import get_bitget_candles

import decision_core


def analyze_decision(symbol="BTCUSDT"):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    return decision_core.analyze(symbol, candles, with_atr=True,
                                 with_ema_levels=False, include_candles=True)


def build_trade_plan(analysis):
    return decision_core.build_plan(analysis, rr=2.0, use_atr_stop=True,
                                    include_risk_per_unit=True)


def calculate_position_size(plan, account_equity, risk_percent):
    max_risk_usdt = account_equity * (risk_percent / 100)
    risk_per_btc = plan["risk_per_unit"]

    btc_size = max_risk_usdt / risk_per_btc
    notional_position_usdt = btc_size * plan["entry"]

    return {
        "account_equity": account_equity,
        "risk_percent": risk_percent,
        "max_risk_usdt": max_risk_usdt,
        "btc_size": btc_size,
        "notional_position_usdt": notional_position_usdt,
    }


if __name__ == "__main__":
    analysis = analyze_decision("BTCUSDT")
    plan = build_trade_plan(analysis)

    print("=== BITGET POSITION SIZER ===")
    print(f"Symbole: {analysis['symbol']}")
    print(f"Décision: {analysis['decision']}")
    print(f"Score: {analysis['score']}")
    print(f"RSI 14: {analysis['rsi']:.2f}")
    print(f"Distance EMA9/EMA21: {analysis['ema_distance_percent']:.4f}%")
    print(f"ATR 14: {analysis['atr']:.2f}")
    print(f"ATR %: {analysis['atr_percent']:.4f}%")
    print()

    if plan is None:
        print("Aucun plan exploitable : signal insuffisant ou risque invalide.")
    else:
        sizing = calculate_position_size(
            plan,
            ACCOUNT_EQUITY_USDT,
            RISK_PER_TRADE_PERCENT
        )

        print("Plan théorique:")
        print(f"Side: {plan['side']}")
        print(f"Entrée: {plan['entry']:.2f}")
        print(f"Stop-loss: {plan['stop_loss']:.2f}")
        print(f"Take-profit: {plan['take_profit']:.2f}")
        print(f"Risque prix par BTC: {plan['risk_per_unit']:.2f} USDT")
        print(f"Risque % prix: {plan['risk_percent']:.3f}%")
        print(f"Gain potentiel: {plan['reward_percent']:.3f}%")
        print(f"Ratio reward/risk: {plan['reward_risk_ratio']:.2f}")
        print()

        print("Money management:")
        print(f"Capital théorique: {sizing['account_equity']:.2f} USDT")
        print(f"Risque par trade: {sizing['risk_percent']:.2f}%")
        print(f"Risque maximum: {sizing['max_risk_usdt']:.2f} USDT")
        print(f"Taille position: {sizing['btc_size']:.8f} BTC")
        print(f"Valeur notionnelle: {sizing['notional_position_usdt']:.2f} USDT")
        print()
        print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
