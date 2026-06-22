"""
tests_audit.py — tests unitaires du système Bitget local (sans réseau, sans ordre).

Classement : SAFE.

Lancement (Termux) :
    cd ~/bitget-agent
    python tests_audit.py
ou, si pytest est installé :
    pytest -q tests_audit.py

Les tests n'appellent JAMAIS l'API Bitget : les bougies sont synthétiques.
Aucun ordre, aucune clé, aucun secret.
"""

from datetime import datetime, timedelta

import indicators
import risk_limits
import security_agent
import order_signal_engine as ose
from outcome_state import check_outcome


# ---------- indicateurs ----------

def test_ema_basic():
    vals = [float(i) for i in range(1, 60)]
    e = indicators.ema(vals, 21)
    assert len(e) == len(vals) - 21 + 1

def test_rsi_all_gains_is_100():
    vals = [float(i) for i in range(1, 40)]
    r = indicators.calculate_rsi(vals, 14)
    assert round(r[-1], 6) == 100.0

def test_indicators_raise_on_short_data():
    for fn, arg in [(indicators.ema, [1.0, 2.0, 3.0]),
                    (indicators.calculate_rsi, [1.0, 2.0, 3.0])]:
        try:
            fn(arg, 14)
            assert False, "aurait dû lever ValueError"
        except ValueError:
            pass

def test_atr_length():
    candles = [{"high": 10 + i, "low": 9 + i, "close": 9.5 + i} for i in range(30)]
    a = indicators.calculate_atr(candles, 14)
    assert len(a) == (len(candles) - 1) - 14 + 1

def test_volume_anchored_level():
    candles = [
        {"open": 10, "close": 11, "high": 12, "low": 9, "volume": 100},
        {"open": 11, "close": 10, "high": 11, "low": 9, "volume": 500},  # plus gros volume
        {"open": 10, "close": 12, "high": 13, "low": 10, "volume": 200},
    ]
    assert indicators.volume_anchored_level(candles, lookback=20) == 10.0

def test_volume_bias_score_direction():
    bull = [{"open": i, "close": i + 1, "volume": 100 + i} for i in range(5)]
    bear = [{"open": i + 1, "close": i, "volume": 100 + i} for i in range(5)]
    flat = [{"open": 5, "close": 5, "volume": 100} for _ in range(5)]
    assert indicators.volume_bias_score(bull) > 0
    assert indicators.volume_bias_score(bear) < 0
    assert indicators.volume_bias_score(flat) == 0

def test_volume_indicators_validate_input():
    for fn in (indicators.volume_anchored_level, indicators.volume_bias_score):
        try:
            fn([], 5) if fn is indicators.volume_anchored_level else fn([{"open": 1, "close": 2, "volume": 1}], 0)
            assert False, "aurait dû lever ValueError"
        except ValueError:
            pass


# ---------- pro_indicators (purs, sans réseau) ----------

def test_momentum_roc():
    import pro_indicators as pro
    vals = [float(i) for i in range(1, 30)]
    roc = pro.momentum(vals, period=10)
    assert len(roc) == len(vals) - 10
    assert roc[-1] > 0  # série croissante -> momentum positif
    try:
        pro.momentum([1.0, 2.0], period=10)
        assert False
    except ValueError:
        pass

def test_volume_profile_poc():
    import pro_indicators as pro
    # gros volume concentré autour de 100 -> POC proche de 100
    candles = (
        [{"close": 100.0, "volume": 1000.0}]
        + [{"close": 101.0, "volume": 10.0}]
        + [{"close": 99.0, "volume": 10.0}]
    )
    vp = pro.volume_profile(candles, bins=10)
    assert 99.0 <= vp["poc"] <= 101.0
    assert vp["value_area_low"] <= vp["poc"] <= vp["value_area_high"]
    assert vp["total_volume"] == 1020.0

def test_sharpe_ratio():
    import pro_indicators as pro
    assert pro.sharpe_ratio([0.01, 0.02, 0.015, 0.005, 0.01]) > 0
    assert pro.sharpe_ratio([0.01, 0.01, 0.01]) == 0.0  # volatilité nulle
    try:
        pro.sharpe_ratio([0.01])
        assert False
    except ValueError:
        pass

def test_risk_based_position_size():
    import pro_indicators as pro
    r = pro.risk_based_position_size(capital=1000.0, risk_percent=1.0, entry=100.0, stop=95.0)
    assert r["risk_amount"] == 10.0
    assert r["distance"] == 5.0
    assert r["size"] == 2.0
    try:
        pro.risk_based_position_size(1000.0, 1.0, 100.0, 100.0)  # stop == entry
        assert False
    except ValueError:
        pass

def test_trading_sessions_brussels():
    import pro_indicators as pro
    from datetime import datetime
    assert pro.trading_sessions(datetime(2026, 1, 1, 9, 30)) == ["EU_MORNING"]
    assert set(pro.trading_sessions(datetime(2026, 1, 1, 16, 0))) == {"US_OPEN", "US_OPEN_PEAK"}
    assert pro.trading_sessions(datetime(2026, 1, 1, 12, 0)) == []
    assert pro.in_active_session(datetime(2026, 1, 1, 1, 30)) is True


# ---------- outcome LONG & SHORT ----------

def _sig(side, entry, sl, tp, t):
    return {"timestamp": t.isoformat(timespec="seconds"), "symbol": "BTCUSDT",
            "side": side, "entry": str(entry), "stop_loss": str(sl), "take_profit": str(tp)}

def _candle(t, high, low, close):
    return {"time": t, "high": high, "low": low, "close": close, "open": close}

def test_long_tp_and_sl():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    sig = _sig("LONG", 100, 95, 110, t0)
    tp_candle = _candle(t0 + timedelta(minutes=15), high=111, low=100, close=110)
    assert check_outcome(sig, [tp_candle], "LONG")["outcome"] == "TP TOUCHÉ"
    sl_candle = _candle(t0 + timedelta(minutes=15), high=101, low=94, close=95)
    assert check_outcome(sig, [sl_candle], "LONG")["outcome"] == "SL TOUCHÉ"

def test_short_tp_and_sl_now_supported():
    # C'était LE bug majeur : les shorts n'étaient jamais évalués.
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    sig = _sig("SHORT", 100, 110, 90, t0)
    tp_candle = _candle(t0 + timedelta(minutes=15), high=101, low=89, close=90)
    assert check_outcome(sig, [tp_candle], "SHORT")["outcome"] == "TP TOUCHÉ"
    sl_candle = _candle(t0 + timedelta(minutes=15), high=111, low=99, close=110)
    assert check_outcome(sig, [sl_candle], "SHORT")["outcome"] == "SL TOUCHÉ"

def test_short_running_sign():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    sig = _sig("SHORT", 100, 110, 90, t0)
    c = _candle(t0 + timedelta(minutes=15), high=100, low=98, close=99)  # prix baisse -> gagnant
    assert check_outcome(sig, [c], "SHORT")["outcome"] == "EN COURS +"

def test_ambiguous_same_candle():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    sig = _sig("LONG", 100, 95, 110, t0)
    c = _candle(t0 + timedelta(minutes=15), high=111, low=94, close=100)
    assert check_outcome(sig, [c], "LONG")["outcome"] == "AMBIGU"


# ---------- normalisation des signaux ----------

def test_normalize_side_variants():
    assert ose.normalize_side("LONG POSSIBLE") == "LONG"
    assert ose.normalize_side("biais short") == "SHORT"
    assert ose.normalize_side("buy") == "LONG"
    assert ose.normalize_side("NEUTRE") == "UNKNOWN"

def test_find_value_precedence():
    row = {"Symbol": "btcusdt", "pair": "ignored"}
    assert ose.find_value(row, ["symbol", "pair"]) == "btcusdt"


# ---------- risk_limits ----------

def test_risk_caps_notional():
    preorders = [
        {"id": "a", "status": "PENDING_APPROVAL", "notional_usdt": 200.0, "sl_distance_percent": 1.0},
        {"id": "b", "status": "PENDING_APPROVAL", "notional_usdt": 200.0, "sl_distance_percent": 1.0},
    ]
    extra = risk_limits.evaluate_portfolio_caps(preorders, open_positions_count=0,
                                                risk_per_trade_percent=1.0)
    # le 1er passe (200<=300), le 2e dépasse le notionnel cumulé
    assert "b" in extra and "a" not in extra

def test_risk_caps_dust_stop():
    preorders = [{"id": "x", "status": "PENDING_APPROVAL", "notional_usdt": 50.0,
                  "sl_distance_percent": 0.05}]
    extra = risk_limits.evaluate_portfolio_caps(preorders, 0, 1.0)
    assert "x" in extra


# ---------- sécurité ----------

def test_security_keyword_coverage():
    # tokens construits par concaténation pour ne pas déclencher le scanner.
    must_cover = ["open" + "_long", "open" + "_short", "close" + "_position",
                  "cancel" + "_order", "place" + "_order", "with" + "draw", "trans" + "fer"]
    kws = [k.lower() for k in security_agent.DANGEROUS_KEYWORDS]
    for token in must_cover:
        assert token in kws, f"mot-clé non couvert: {token}"

def test_telegram_auth_detection_robust():
    original = "if chat_id != str(ALLOWED_CHAT_ID):"
    refactored = "if not is_authorized(chat_id):  # ALLOWED_CHAT_ID"
    weak = "x = 1"
    assert security_agent.telegram_auth_is_present(original) == (True, True)
    assert security_agent.telegram_auth_is_present(refactored)[1] is True
    assert security_agent.telegram_auth_is_present(weak) == (False, False)


# ---------- git_version (lecture seule, sans git ni réseau) ----------

def test_git_version_report_clean():
    import git_version
    info = {
        "branch": "main", "commit_short": "abc1234", "subject": "fix: x",
        "commit_date": "2026-06-20 10:00:00",
        "last_tag": "stable-paper-dryrun-20260620", "tag_at_head": "",
        "dirty": False, "changed_count": 0, "ahead": "0", "behind": "0",
    }
    txt = git_version.build_report(info)
    assert "GIT VERSION" in txt
    assert "main" in txt and "abc1234" in txt
    assert "propre" in txt and "à jour" in txt
    assert "SAFE" in txt
    # aucun nom de secret ne doit fuiter dans le rapport
    for leak in ("BITGET_API_SECRET", "TELEGRAM_BOT_TOKEN", "PASSPHRASE"):
        assert leak not in txt

def test_git_version_report_dirty_and_tag_at_head():
    import git_version
    info = {
        "branch": "claude/x", "commit_short": "deadbee", "subject": "wip",
        "commit_date": "2026-06-20 11:00:00", "last_tag": "(aucun tag)",
        "tag_at_head": "stable-paper-dryrun-20260620",
        "dirty": True, "changed_count": 3,
    }
    txt = git_version.build_report(info)
    assert "MODIFIÉ" in txt and "3 fichier" in txt
    assert "Tag (HEAD)" in txt and "stable-paper-dryrun-20260620" in txt
    assert "Vs amont" not in txt  # pas d'info amont fournie


# ---------- watchdog agent_loop (décision pure, sans I/O) ----------

def test_watchdog_verdicts():
    import watchdog
    # (process_known, process_alive, data_known, fresh, paused) -> (verdict, alert)
    assert watchdog.decide_verdict(True, True, True, True, False) == ("RUNNING", False)
    assert watchdog.decide_verdict(True, True, True, False, False) == ("STALE", True)
    assert watchdog.decide_verdict(True, False, True, True, False) == ("DOWN", True)
    assert watchdog.decide_verdict(True, False, True, False, True) == ("PAUSE", False)
    assert watchdog.decide_verdict(False, False, True, True, False) == ("RUNNING?", False)
    assert watchdog.decide_verdict(False, False, True, False, False) == ("DOWN", True)
    assert watchdog.decide_verdict(False, False, False, False, False) == ("UNKNOWN", False)

def test_watchdog_report_alert_text():
    import watchdog
    running = {
        "pid_file_pid": 1234, "proc_scan": "found", "proc_scan_pid": 1234,
        "process_known": True, "process_alive": True,
        "data_known": True, "age_min": 1.0, "fresh": True, "interval_min": 15.0,
        "paused": False, "verdict": "RUNNING", "alert": False,
    }
    txt = watchdog.build_report(running)
    assert "WATCHDOG" in txt and "RUNNING" in txt
    assert "ALERTE" not in txt
    assert "Aucun redémarrage automatique" in txt

    down = dict(running, process_alive=False, verdict="DOWN", alert=True)
    txt2 = watchdog.build_report(down)
    assert "ALERTE" in txt2 and "DOWN" in txt2

def test_watchdog_is_agent_loop_precise():
    import watchdog
    # vrais matches
    assert watchdog._is_agent_loop(["python", "agent_loop.py"]) is True
    assert watchdog._is_agent_loop(["python3", "/home/u/agent_loop.py"]) is True
    # faux positifs a NE PAS confondre (le bug attrape par le test fonctionnel)
    assert watchdog._is_agent_loop(["grep", "agent_loop.py"]) is False
    assert watchdog._is_agent_loop(["pkill", "-f", "agent_loop.py"]) is False
    assert watchdog._is_agent_loop(["bash", "-c", "echo agent_loop.py"]) is False
    assert watchdog._is_agent_loop(["python", "watchdog.py"]) is False
    assert watchdog._is_agent_loop(["python"]) is False
    assert watchdog._is_agent_loop(None) is False


# ---------- agent_loop : PID file (arret/relance propre) ----------

def test_agent_loop_pid_file_lifecycle():
    import os
    import tempfile
    from pathlib import Path

    import agent_loop

    old = agent_loop.PID_FILE
    with tempfile.TemporaryDirectory() as d:
        agent_loop.PID_FILE = Path(d) / "agent_loop.pid"
        try:
            agent_loop.write_pid_file()
            assert agent_loop.PID_FILE.exists()
            assert agent_loop.PID_FILE.read_text().strip() == str(os.getpid())

            agent_loop.remove_pid_file()
            assert not agent_loop.PID_FILE.exists()

            # remove_pid_file ne touche pas un PID file appartenant a autrui
            agent_loop.PID_FILE.write_text("999999")
            agent_loop.remove_pid_file()
            assert agent_loop.PID_FILE.exists()
        finally:
            agent_loop.PID_FILE = old


# ---------- stats_report (lecture seule, sans réseau) ----------

def test_stats_compute_and_report():
    import stats_report
    rows = [
        {"symbol": "BTCUSDT", "side": "LONG", "outcome": "TP TOUCHÉ"},
        {"symbol": "BTCUSDT", "side": "LONG", "outcome": "SL TOUCHÉ"},
        {"symbol": "BTCUSDT", "side": "SHORT", "outcome": "TP TOUCHÉ"},
        {"symbol": "ETHUSDT", "side": "SHORT", "outcome": "AMBIGU"},
        {"symbol": "ETHUSDT", "side": "LONG", "outcome": "EN COURS +"},  # ignoré
    ]
    s = stats_report.compute_stats(rows)
    assert s["total"] == 4  # 3 TP/SL + 1 AMBIGU ; EN COURS exclu
    assert s["tp"] == 2 and s["sl"] == 1 and s["ambigu"] == 1
    assert round(s["win_rate"], 1) == round(2 / 3 * 100, 1)
    assert round(s["tp_sl_ratio"], 2) == 2.0
    assert s["by_symbol"]["BTCUSDT"]["tp"] == 2
    assert s["by_side"]["SHORT"]["tp"] == 1 and s["by_side"]["SHORT"]["ambigu"] == 1

    txt = stats_report.build_report(s)
    assert "STATS" in txt and "Par symbole" in txt and "Par sens" in txt
    assert "SAFE" in txt

def test_stats_empty():
    import stats_report
    s = stats_report.compute_stats([])
    assert s["total"] == 0
    assert s["win_rate"] is None and s["tp_sl_ratio"] is None
    txt = stats_report.build_report(s)
    assert "Aucun résultat finalisé" in txt and "SAFE" in txt


# ---------- system_health : compteurs (lecture seule, sans réseau) ----------

def test_system_health_preorder_counts():
    import json
    import tempfile
    from pathlib import Path

    import system_health

    old = system_health.PENDING_ORDERS_FILE
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "pending_orders.json"
        p.write_text(json.dumps({"orders": [
            {"id": "a", "status": "PENDING_APPROVAL"},
            {"id": "b", "status": "REJECTED"},
            {"id": "c", "status": "REJECTED", "guard_status": "OBSERVATION_BLOCKED"},
        ]}), encoding="utf-8")
        system_health.PENDING_ORDERS_FILE = p
        try:
            counts, blocked = system_health.count_pending_orders()
            assert counts["PENDING_APPROVAL"] == 1
            assert counts["REJECTED"] == 2
            assert blocked == 1
        finally:
            system_health.PENDING_ORDERS_FILE = old

def test_system_health_execution_journal_no_real_order():
    import json
    import tempfile
    from pathlib import Path

    import system_health

    old = system_health.EXECUTION_JOURNAL
    with tempfile.TemporaryDirectory() as d:
        j = Path(d) / "execution_dry_run_journal.jsonl"
        j.write_text(
            json.dumps({"action": "EXECUTION_DRY_RUN", "real_order_sent": False}) + "\n"
            + json.dumps({"action": "EXECUTION_DRY_RUN", "real_order_sent": False}) + "\n"
            + json.dumps({"action": "EXECUTION_DRY_RUN_REJECTED", "real_order_sent": False}) + "\n",
            encoding="utf-8",
        )
        system_health.EXECUTION_JOURNAL = j
        try:
            dry_run, real_sent = system_health.scan_execution_journal()
            assert dry_run == 2
            assert real_sent == 0
        finally:
            system_health.EXECUTION_JOURNAL = old


def test_preorder_guard_blocks_pending_when_observation():
    import csv
    import json
    import tempfile
    from pathlib import Path

    import preorder_guard

    old_open_state = preorder_guard.OPEN_STATE_FILE
    old_pending = preorder_guard.PENDING_ORDERS_FILE
    old_journal = preorder_guard.PREORDER_GUARD_JOURNAL_FILE

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        open_state = tmp / "open_outcomes_state.csv"
        pending = tmp / "pending_orders.json"
        journal = tmp / "preorder_guard_journal.jsonl"

        with open_state.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "side", "outcome"])
            writer.writeheader()
            writer.writerow({"symbol": "BTCUSDT", "side": "LONG", "outcome": "EN COURS -"})
            writer.writerow({"symbol": "ETHUSDT", "side": "LONG", "outcome": "EN COURS -"})
            writer.writerow({"symbol": "SOLUSDT", "side": "LONG", "outcome": "EN COURS -"})
            writer.writerow({"symbol": "XRPUSDT", "side": "LONG", "outcome": "EN COURS +"})

        pending.write_text(json.dumps({
            "orders": [
                {"id": "TEST_PENDING", "status": "PENDING_APPROVAL", "reasons": []},
                {"id": "TEST_REJECTED", "status": "REJECTED", "reasons": ["déjà rejeté"]},
            ]
        }), encoding="utf-8")

        preorder_guard.OPEN_STATE_FILE = str(open_state)
        preorder_guard.PENDING_ORDERS_FILE = pending
        preorder_guard.PREORDER_GUARD_JOURNAL_FILE = journal

        try:
            state, blocked = preorder_guard.apply_guard()

            data = json.loads(pending.read_text(encoding="utf-8"))
            orders = {o["id"]: o for o in data["orders"]}

            assert state["mode"] == "OBSERVATION"
            assert "TEST_PENDING" in blocked
            assert orders["TEST_PENDING"]["status"] == "REJECTED"
            assert orders["TEST_PENDING"]["guard_status"] == "OBSERVATION_BLOCKED"
            assert "OBSERVATION" in " ".join(orders["TEST_PENDING"]["reasons"])
            assert orders["TEST_REJECTED"]["status"] == "REJECTED"
            assert journal.exists()

        finally:
            preorder_guard.OPEN_STATE_FILE = old_open_state
            preorder_guard.PENDING_ORDERS_FILE = old_pending
            preorder_guard.PREORDER_GUARD_JOURNAL_FILE = old_journal

def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests OK")
    return passed == len(tests)


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run_all() else 1)
