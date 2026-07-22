"""Tests des wrappers decision_engine / trade_plan après extraction de decision_core.

Verrouille les FORMES de dict propres à chaque clone historique (le refactor est
iso-comportement : ces formes ne doivent jamais bouger), plus l'invariant de
parité position_sizer ↔ atr_trade_plan à RR égal. Fetchers mockés, zéro réseau.
"""
import pytest

import atr_trade_plan
import decision_engine
import position_sizer
import trade_plan


def _bougies_synthetiques(symbol, granularity, limit):
    out = []
    for i in range(limit):
        close = 100.0 + i * 0.5
        out.append({"open": close - 0.2, "close": close,
                    "high": close + 0.5, "low": close - 0.7,
                    "volume": 10.0 + i})
    return out


def _analyse(decision, entry=100.0, atr=2.0, low=95.0, high=105.0):
    candles = [{"low": low + 1.0, "high": high - 1.0, "close": entry}] * 9
    candles.append({"low": low, "high": high, "close": entry})
    return {"decision": decision, "last_close": entry, "atr": atr,
            "candles": candles}


def test_decision_engine_forme_sans_bougies_ni_atr(monkeypatch):
    # Forme historique : ema9/ema21 exposés, PAS de candles ni d'atr
    monkeypatch.setattr(decision_engine, "get_bitget_candles", _bougies_synthetiques)
    a = decision_engine.analyze_decision("BTCUSDT")
    assert "ema9" in a and "ema21" in a
    assert "candles" not in a
    assert "atr" not in a
    assert a["decision"] in {"LONG POSSIBLE", "SHORT POSSIBLE", "BIAIS LONG",
                             "BIAIS SHORT", "NEUTRE / ATTENDRE"}


def test_trade_plan_forme_avec_bougies_sans_atr(monkeypatch):
    monkeypatch.setattr(trade_plan, "get_bitget_candles", _bougies_synthetiques)
    a = trade_plan.analyze_decision("BTCUSDT")
    assert "ema9" in a and "candles" in a
    assert "atr" not in a


def test_trade_plan_stop_structurel_seul():
    # trade_plan ignore l'ATR : stop = plus bas récent, même sans clé atr
    analyse = _analyse("LONG POSSIBLE")
    del analyse["atr"]
    plan = trade_plan.build_trade_plan(analyse)
    assert plan["stop_loss"] == 95.0
    assert plan["take_profit"] == pytest.approx(110.0)
    assert "structural_stop" not in plan and "atr_stop" not in plan
    assert "risk_per_unit" not in plan


def test_trade_plan_short_miroir_et_neutre():
    analyse = _analyse("SHORT POSSIBLE")
    del analyse["atr"]
    plan = trade_plan.build_trade_plan(analyse)
    assert plan["stop_loss"] == 105.0
    assert plan["take_profit"] == pytest.approx(90.0)
    assert trade_plan.build_trade_plan(_analyse("NEUTRE / ATTENDRE")) is None


def test_parite_position_sizer_atr_trade_plan_a_rr_egal(monkeypatch):
    # À RR identique (2.0), les deux clones ATR doivent produire le MÊME plan,
    # au seul champ risk_per_unit près (delta historique de position_sizer)
    monkeypatch.setenv("ATR_TRADE_RR", "2.0")
    a = _analyse("LONG POSSIBLE")
    ps = dict(position_sizer.build_trade_plan(a))
    at = atr_trade_plan.build_trade_plan(a)
    ps.pop("risk_per_unit")
    assert ps == at
