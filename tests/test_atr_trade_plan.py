"""Suite pytest d'atr_trade_plan.py — le DELTA vs position_sizer : ratio TP/risque
configurable par le knob _rr (env ATR_TRADE_RR > config > 1.5).

Le module duplique analyze/build de position_sizer (couvert par test_position_sizer) :
on ne re-teste ici que ce qui lui est propre — le knob et son repli fail-safe.
"""
import pytest

import atr_trade_plan
import config_utils


def _analyse(decision, entry=100.0, atr=2.0, low=95.0, high=105.0):
    candles = [{"low": low + 1.0, "high": high - 1.0, "close": entry}] * 9
    candles.append({"low": low, "high": high, "close": entry})
    return {"decision": decision, "last_close": entry, "atr": atr,
            "candles": candles}


def test_rr_pilote_par_env(monkeypatch):
    # RR 3 : risque 5 (stop 95) -> TP = 100 + 15 = 115
    monkeypatch.setenv("ATR_TRADE_RR", "3.0")
    plan = atr_trade_plan.build_trade_plan(_analyse("LONG POSSIBLE"))
    assert plan["take_profit"] == pytest.approx(115.0)
    assert plan["reward_risk_ratio"] == pytest.approx(3.0)


def test_rr_env_illisible_replie_sur_defaut(monkeypatch):
    # env corrompu -> repli cfg (épinglé au défaut) = 1.5, sans crash
    monkeypatch.setenv("ATR_TRADE_RR", "pas-un-nombre")
    monkeypatch.setattr(config_utils, "cfg", lambda key, default=None: default)
    plan = atr_trade_plan.build_trade_plan(_analyse("LONG POSSIBLE"))
    assert plan["take_profit"] == pytest.approx(107.5)
    assert plan["reward_risk_ratio"] == pytest.approx(1.5)


def test_rr_applique_au_short_miroir(monkeypatch):
    # SHORT : stop 105, risque 5, RR 2 -> TP = 100 − 10 = 90
    monkeypatch.setenv("ATR_TRADE_RR", "2.0")
    plan = atr_trade_plan.build_trade_plan(_analyse("SHORT POSSIBLE"))
    assert plan["side"] == "SHORT"
    assert plan["take_profit"] == pytest.approx(90.0)


def test_plan_neutre_renvoie_none(monkeypatch):
    monkeypatch.setenv("ATR_TRADE_RR", "2.0")
    assert atr_trade_plan.build_trade_plan(_analyse("NEUTRE / ATTENDRE")) is None
