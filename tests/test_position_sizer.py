"""Suite pytest de position_sizer.py — plan de trade + sizing (ANALYSE SEULE, aucun ordre).

`build_trade_plan` et `calculate_position_size` sont PURES (analyse injectée) ;
`analyze_decision` est testée avec `get_bitget_candles` mocké par monkeypatch —
aucun appel réseau.
"""
import pytest

import position_sizer


def _analyse(decision, entry=100.0, atr=2.0, low=95.0, high=105.0):
    """Analyse minimale injectable : 10 bougies récentes encadrant low/high."""
    candles = [{"low": low + 1.0, "high": high - 1.0, "close": entry}] * 9
    candles.append({"low": low, "high": high, "close": entry})
    return {"decision": decision, "last_close": entry, "atr": atr,
            "candles": candles}


# ---------------------------------------------------------------------------
# build_trade_plan — choix du stop (structurel vs ATR) et R/R fixe 2:1
# ---------------------------------------------------------------------------

def test_plan_long_stop_structurel_plus_large_retenu():
    # LONG : min(structurel 95, ATR 97) = 95 -> risque 5, TP = 110, R/R = 2
    plan = position_sizer.build_trade_plan(_analyse("LONG POSSIBLE"))
    assert plan["side"] == "LONG"
    assert plan["stop_loss"] == 95.0
    assert plan["take_profit"] == pytest.approx(110.0)
    assert plan["reward_risk_ratio"] == pytest.approx(2.0)


def test_plan_long_stop_atr_plus_large_retenu():
    # Structure serrée (low 99) : le stop ATR 97 est plus bas -> retenu
    plan = position_sizer.build_trade_plan(_analyse("BIAIS LONG", low=99.0))
    assert plan["stop_loss"] == pytest.approx(97.0)
    assert plan["structural_stop"] == 99.0


def test_plan_short_miroir():
    # SHORT : max(structurel 105, ATR 103) = 105 -> risque 5, TP = 90
    plan = position_sizer.build_trade_plan(_analyse("SHORT POSSIBLE"))
    assert plan["side"] == "SHORT"
    assert plan["stop_loss"] == 105.0
    assert plan["take_profit"] == pytest.approx(90.0)
    assert plan["reward_risk_ratio"] == pytest.approx(2.0)


def test_plan_neutre_renvoie_none():
    assert position_sizer.build_trade_plan(_analyse("NEUTRE / ATTENDRE")) is None


def test_plan_risque_nul_renvoie_none():
    # ATR 0 et structure au niveau de l'entrée : risque 0 -> pas de plan
    assert position_sizer.build_trade_plan(
        _analyse("LONG POSSIBLE", atr=0.0, low=100.0)) is None


# ---------------------------------------------------------------------------
# calculate_position_size — money management pur
# ---------------------------------------------------------------------------

def test_sizing_risque_1_pour_cent():
    # Equity 100, risque 1 % -> 1 USDT max ; risque/unité 5 -> 0.2 unité, 20 $ notionnel
    plan = {"risk_per_unit": 5.0, "entry": 100.0}
    s = position_sizer.calculate_position_size(plan, account_equity=100.0,
                                               risk_percent=1.0)
    assert s["max_risk_usdt"] == pytest.approx(1.0)
    assert s["btc_size"] == pytest.approx(0.2)
    assert s["notional_position_usdt"] == pytest.approx(20.0)


def test_sizing_coherence_notionnel():
    plan = {"risk_per_unit": 2.5, "entry": 50.0}
    s = position_sizer.calculate_position_size(plan, 1000.0, 0.5)
    assert s["notional_position_usdt"] == pytest.approx(s["btc_size"] * 50.0)


# ---------------------------------------------------------------------------
# analyze_decision — fetcher MOCKÉ (aucun réseau) : invariants de sortie
# ---------------------------------------------------------------------------

def test_analyze_decision_avec_bougies_synthetiques(monkeypatch):
    def bougies_synthetiques(symbol, granularity, limit):
        out = []
        for i in range(limit):
            close = 100.0 + i * 0.5
            out.append({"open": close - 0.2, "close": close,
                        "high": close + 0.5, "low": close - 0.7,
                        "volume": 10.0 + i})
        return out

    monkeypatch.setattr(position_sizer, "get_bitget_candles", bougies_synthetiques)
    a = position_sizer.analyze_decision("BTCUSDT")

    assert a["symbol"] == "BTCUSDT"
    assert a["last_close"] == pytest.approx(100.0 + 99 * 0.5)
    assert a["decision"] in {"LONG POSSIBLE", "SHORT POSSIBLE", "BIAIS LONG",
                             "BIAIS SHORT", "NEUTRE / ATTENDRE"}
    assert "EMA9 > EMA21" in a["reasons"]          # tendance haussière franche
    assert a["atr"] > 0
    assert 0.0 <= a["rsi"] <= 100.0
    assert len(a["candles"]) == 100
