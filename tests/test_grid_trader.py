import grid_trader as gt


def _cell(survives=True, surface="futures"):
    return {"survives": survives, "surface": surface, "mode": "neutral",
            "symbol": "BTCUSDT", "chosen": "futures/neutral g=1.2%·k=3.5"}


def test_dry_by_default_delegates_nothing():
    out = gt.plan_cycle(_cell(), dry=True)
    assert out["dry"] is True and out["delegated"] == 0
    assert out["intentions"]                      # intentions calculées mais NON exécutées


def test_refuse_non_surviving_config():
    out = gt.plan_cycle(_cell(survives=False), dry=True)
    assert out["refused"] and out["delegated"] == 0


def test_kill_switch_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(gt, "KILL_PATH", tmp_path / "KILL_SWITCH")
    (tmp_path / "KILL_SWITCH").write_text("x")
    monkeypatch.setattr(gt, "live_enabled", lambda: True)
    out = gt.plan_cycle(_cell(), dry=False)
    assert out["killed"] and out["delegated"] == 0


def test_live_off_forces_dry(monkeypatch):
    monkeypatch.setattr(gt, "live_enabled", lambda: False)
    out = gt.plan_cycle(_cell(), dry=False)   # demande live mais verrou OFF
    assert out["dry"] is True and out["delegated"] == 0
