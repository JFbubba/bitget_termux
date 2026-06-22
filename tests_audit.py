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

def test_savitzky_golay_denoise():
    import indicators
    # intérieur exact pour une droite (poly>=1 reproduit l'affine)
    lin = [2 * i + 3 for i in range(20)]
    sm = indicators.savitzky_golay(lin, window=11, poly=2)
    assert len(sm) == len(lin)
    assert all(abs(sm[i] - lin[i]) < 1e-6 for i in range(5, len(lin) - 5))
    # réduction du bruit : variation totale plus faible
    noisy = [i + (1.0 if i % 2 == 0 else -1.0) for i in range(60)]
    sm2 = indicators.savitzky_golay(noisy, window=11, poly=2)
    tv = lambda s: sum(abs(s[i + 1] - s[i]) for i in range(len(s) - 1))
    assert tv(sm2) < tv(noisy)
    # fenêtre trop courte -> identité, ne lève pas
    assert indicators.savitzky_golay([1, 2], window=11) == [1.0, 2.0]
    assert indicators.savitzky_golay([]) == []

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

def test_sector_rotation_and_cot():
    import pro_indicators as pro
    assert abs(pro.sector_rotation_ratio(100.0, 80.0) - 1.25) < 1e-9
    try:
        pro.sector_rotation_ratio(100.0, 0.0)
        assert False
    except ValueError:
        pass
    cot = pro.cot_net_positioning(600.0, 400.0)
    assert cot["net"] == 200.0 and abs(cot["net_pct"] - 20.0) < 1e-9 and cot["bias"] == "LONG"
    assert pro.cot_net_positioning(0.0, 0.0)["bias"] == "FLAT"

def test_trading_sessions_brussels():
    import pro_indicators as pro
    from datetime import datetime
    assert pro.trading_sessions(datetime(2026, 1, 1, 9, 30)) == ["EU_MORNING"]
    assert set(pro.trading_sessions(datetime(2026, 1, 1, 16, 0))) == {"US_OPEN", "US_OPEN_PEAK"}
    assert pro.trading_sessions(datetime(2026, 1, 1, 12, 0)) == []
    assert pro.in_active_session(datetime(2026, 1, 1, 1, 30)) is True


# ---------- order_flow (microstructure, purs) ----------

def test_cumulative_volume_delta():
    import order_flow as of
    trades = [
        {"side": "buy", "size": 3.0},
        {"side": "sell", "size": 1.0},
        {"side": "buy", "size": 2.0},
    ]
    r = of.cumulative_volume_delta(trades)
    assert r["cvd"] == 4.0
    assert r["buy_volume"] == 5.0 and r["sell_volume"] == 1.0
    assert r["series"][-1] == 4.0
    try:
        of.cumulative_volume_delta([])
        assert False
    except ValueError:
        pass

def test_order_book_imbalance():
    import order_flow as of
    bids = [[100.0, 40.0], [99.0, 20.0]]   # 60
    asks = [[101.0, 30.0], [102.0, 10.0]]  # 40
    r = of.order_book_imbalance(bids, asks)
    assert abs(r["imbalance"] - 0.2) < 1e-9
    assert r["bid_volume"] == 60.0 and r["ask_volume"] == 40.0

def test_liquidation_levels():
    import order_flow as of
    longs = of.liquidation_levels(100.0, [10, 5], side="long", maintenance_margin=0.0)
    prices = {lv["leverage"]: lv["price"] for lv in longs}
    assert abs(prices[10] - 90.0) < 1e-9   # 10x long -> -10%
    assert abs(prices[5] - 80.0) < 1e-9    # 5x long  -> -20%
    shorts = of.liquidation_levels(100.0, [10], side="short", maintenance_margin=0.0)
    assert abs(shorts[0]["price"] - 110.0) < 1e-9
    try:
        of.liquidation_levels(0.0, [10])
        assert False
    except ValueError:
        pass


# ---------- bitget_market_data : parseurs (purs, sans réseau) ----------

def test_bitget_parsers():
    import bitget_market_data as bmd
    ob = bmd.parse_orderbook({"bids": [[100, 2], ["99", "1"]], "asks": [[101, 3]]})
    assert ob["bids"] == [[100.0, 2.0], [99.0, 1.0]]
    assert ob["asks"] == [[101.0, 3.0]]

    trades = bmd.parse_trades([
        {"side": "Buy", "size": "0.5", "price": "100"},
        {"side": "sell", "size": "0.2", "price": "100"},
    ])
    assert trades[0]["side"] == "buy" and trades[0]["size"] == 0.5
    assert trades[1]["side"] == "sell"

    assert bmd.parse_open_interest({"openInterestList": [{"symbol": "BTCUSDT", "size": "100.5"}]}) == 100.5
    assert bmd.parse_open_interest({}) == 0.0
    assert abs(bmd.parse_funding_rate([{"fundingRate": "0.0001"}]) - 0.0001) < 1e-12
    assert bmd.parse_funding_rate([]) is None

def test_bitget_build_report():
    import bitget_market_data as bmd
    snap = {
        "symbol": "BTCUSDT", "mid_price": 64000.0, "book_imbalance": -0.5,
        "bid_volume": 3.0, "ask_volume": 9.0, "cvd": -0.2,
        "open_interest": 32584.0, "funding_rate": 0.00004,
    }
    txt = bmd.build_report(snap)
    assert "ORDER FLOW BTCUSDT" in txt and "SAFE" in txt
    assert "Funding" in txt


# ---------- macro_context : parseur + régime (purs, sans réseau) ----------

def test_macro_parse_fred_csv():
    import macro_context as mc
    csv = "observation_date,VIXCLS\n2024-01-01,13.20\n2024-01-02,.\n2024-01-03,14.05\n"
    rows = mc.parse_fred_csv(csv)
    assert rows == [("2024-01-01", 13.20), ("2024-01-03", 14.05)]
    assert mc.latest_value(rows) == 14.05
    assert mc.latest_value([]) is None

def test_dashboard_assemble_state():
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("dash_server", pathlib.Path("dashboard/server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    st = mod.assemble_state("BTCUSDT", ["BTCUSDT", "ETHUSDT"], {"total": 3, "tp": 2, "sl": 1}, None, None, {"signals": 5})
    assert st["symbol"] == "BTCUSDT" and st["mode"].startswith("PAPER")
    assert st["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert st["stats"]["tp"] == 2 and st["health"]["signals"] == 5
    assert st["orderflow"] is None
    assert st["brain"] == {} and st["candles"] == [] and st["liquidations"] == {}
    st2 = mod.assemble_state("BTCUSDT", [], {}, None, None, {}, brain={"bias": "LONG"},
                             liquidations={"skew": {"net": 0.3}})
    assert st2["brain"]["bias"] == "LONG" and st2["liquidations"]["skew"]["net"] == 0.3

def test_macro_risk_regime():
    import macro_context as mc
    on = mc.compute_risk_regime(vix=15.0, yield_2s10s=0.5, dxy_change_pct=-1.0)
    assert on["regime"] == "RISK_ON" and on["score"] > 0
    off = mc.compute_risk_regime(vix=30.0, yield_2s10s=-0.2, dxy_change_pct=1.0)
    assert off["regime"] == "RISK_OFF" and off["score"] < 0
    neutral = mc.compute_risk_regime()
    assert neutral["regime"] == "NEUTRE" and neutral["score"] == 0


# ---------- confluence_score (pur, sans réseau) ----------

def test_confluence_score():
    import confluence_score as c
    strong = c.confluence_score("LONG", book_imbalance=0.3, cvd=5.0, macro_regime="RISK_ON", volume_bias=2)
    assert strong["label"] == "FORTE CONFLUENCE" and strong["score"] >= 3
    against = c.confluence_score("SHORT", book_imbalance=0.3, cvd=5.0, macro_regime="RISK_ON")
    assert against["score"] < 0
    mixed = c.confluence_score("LONG")
    assert mixed["label"] == "MIXTE" and mixed["score"] == 0
    try:
        c.confluence_score("NEUTRE")
        assert False, "aurait dû lever ValueError"
    except ValueError:
        pass


# ---------- readers keyless (parseurs purs, sans réseau) ----------

def test_sentiment_parse():
    import sentiment_index as si
    fng = si.parse_fear_greed({"data": [{"value": "20", "value_classification": "Extreme Fear", "timestamp": "1"}]})
    assert fng["value"] == 20 and "Fear" in fng["classification"]
    assert si.parse_fear_greed({"data": []}) is None

def test_defi_parse():
    import defi_data as dd
    s = dd.parse_chains([{"name": "Ethereum", "tvl": 39e9, "tokenSymbol": "ETH"},
                         {"name": "BSC", "tvl": 5e9}], top=2)
    assert s["chain_count"] == 2 and s["top_chains"][0]["name"] == "Ethereum"
    assert abs(s["total_tvl"] - 44e9) < 1

def test_token_safety():
    import token_safety as ts
    gp = ts.parse_goplus({"result": {"0xabc": {"is_honeypot": "1", "buy_tax": "0.5",
        "sell_tax": "0.9", "is_open_source": "0", "holder_count": "10"}}}, "0xABC")
    assert gp["honeypot"] is True and "HONEYPOT" in gp["flags"] and "CLOSED_SOURCE" in gp["flags"]
    hp = ts.parse_honeypot({"honeypotResult": {"isHoneypot": True}, "simulationResult": {"buyTax": 1, "sellTax": 2}})
    assert hp["honeypot"] is True
    rc = ts.parse_rugcheck({"token": {"mintAuthority": "X", "freezeAuthority": None},
        "risks": [{"name": "High holder concentration"}], "score": 500})
    assert "MINT_AUTHORITY_ACTIVE" in rc["flags"] and "HIGH_HOLDER_CONCENTRATION" in rc["flags"]
    assert ts.risk_level(["HONEYPOT"]) == "CRITICAL"
    assert ts.risk_level(["MINT_AUTHORITY_ACTIVE"]) == "HIGH"
    assert ts.risk_level([], honeypot=False, taxes=(15, 1)) == "HIGH"
    assert ts.risk_level([]) == "LOW"

def test_dex_parse():
    import dex_scanner as ds
    pairs = ds.parse_pairs({"pairs": [
        {"chainId": "solana", "dexId": "ray", "baseToken": {"symbol": "AAA", "name": "A", "address": "x"},
         "priceUsd": "1", "liquidity": {"usd": 1000}, "volume": {"h24": 50}},
        {"chainId": "base", "dexId": "aero", "baseToken": {"symbol": "BBB"},
         "liquidity": {"usd": 5000}, "volume": {"h24": 10}},
    ]}, top=2)
    assert pairs[0]["symbol"] == "BBB" and pairs[0]["liquidity_usd"] == 5000

def test_assistant_tools_schema():
    from assistant import tools
    assert len(tools.TOOLS) >= 6
    names = {t["name"] for t in tools.TOOLS}
    for t in tools.TOOLS:
        assert t["name"] and t["description"]
        assert t["input_schema"]["type"] == "object"
        assert t["name"] in tools.TOOL_FUNCS
    assert "get_order_flow" in names and "check_token_safety" in names
    assert "inconnu" in tools.dispatch("nope", {})  # outil inconnu -> message, pas d'exception

def test_assistant_agent_loop():
    from assistant import agent, llm_client, tools
    seq = {"n": 0}

    def fake_chat(system, messages, tools=None, **kw):
        seq["n"] += 1
        if seq["n"] == 1:
            return {"stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "t1", "name": "get_fear_greed", "input": {}}]}
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Réponse finale."}]}

    orig_chat, orig_dispatch = llm_client.anthropic_chat, tools.dispatch
    llm_client.anthropic_chat = fake_chat
    tools.dispatch = lambda name, args: "RESULT_OK"
    try:
        text, msgs = agent.run("test question", use_memory=False)
    finally:
        llm_client.anthropic_chat = orig_chat
        tools.dispatch = orig_dispatch
    assert text == "Réponse finale." and seq["n"] == 2
    assert any(
        isinstance(m.get("content"), list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
        for m in msgs
    )

def test_assistant_openai_loop():
    from assistant import agent, llm_client, tools
    seq = {"n": 0}

    def fake_openai(messages, tools=None, **kw):
        seq["n"] += 1
        if seq["n"] == 1:
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "get_fear_greed", "arguments": "{}"}}]}}]}
        return {"choices": [{"message": {"role": "assistant", "content": "Réponse OpenAI."}}]}

    o_use, o_chat, o_disp = llm_client.use_openai, llm_client.openai_chat, tools.dispatch
    llm_client.use_openai = lambda: True
    llm_client.openai_chat = fake_openai
    tools.dispatch = lambda name, args: "RESULT_OK"
    try:
        text, msgs = agent.run("question", use_memory=False)
    finally:
        llm_client.use_openai, llm_client.openai_chat, tools.dispatch = o_use, o_chat, o_disp
    assert text == "Réponse OpenAI." and seq["n"] == 2
    assert any(isinstance(m, dict) and m.get("role") == "tool" for m in msgs)

def test_vision_build_messages():
    from assistant import vision
    msgs = vision.build_messages("analyse", "QkFTRTY0", "image/png")
    assert msgs[0]["role"] == "system" and "LECTURE SEULE" in msgs[0]["content"]
    parts = msgs[1]["content"]
    assert msgs[1]["role"] == "user"
    assert parts[0]["type"] == "text" and parts[0]["text"] == "analyse"
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,QkFTRTY0")

def test_assistant_memory():
    import pathlib
    import tempfile
    from assistant import memory
    orig = memory.STORE
    memory.STORE = pathlib.Path(tempfile.gettempdir()) / "conv_test_bitget.json"
    try:
        memory.reset()
        assert memory.load_messages() == []
        memory.save_turn("question1", "reponse1")
        memory.save_turn("question2", "reponse2")
        assert memory.load_messages() == [
            {"role": "user", "content": "question1"}, {"role": "assistant", "content": "reponse1"},
            {"role": "user", "content": "question2"}, {"role": "assistant", "content": "reponse2"},
        ]
        memory.reset()
        assert memory.load_messages() == []
    finally:
        memory.STORE = orig

def test_assistant_openai_tools_format():
    from assistant import llm_client, tools
    conv = llm_client.to_openai_tools(tools.TOOLS)
    assert conv and all(t["type"] == "function" and t["function"]["name"] for t in conv)
    assert conv[0]["function"]["parameters"]["type"] == "object"

def test_technicals_pure():
    import technicals as tk
    assert tk._norm_granularity("1h") == "1H" and tk._norm_granularity("1H") == "1H"
    assert tk._norm_granularity("15m") == "15m" and tk._norm_granularity("4h") == "4H"
    assert tk._norm_granularity("1d") == "1D" and tk._norm_granularity("1M") == "1M"
    candles = [
        {"ts": 1, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100},
        {"ts": 2, "open": 11, "high": 13, "low": 10, "close": 12, "volume": 200},
        {"ts": 3, "open": 12, "high": 14, "low": 11, "close": 13, "volume": 300},
    ]
    assert abs(tk.vwap(candles) - 12.0) < 1e-6
    vp = tk.volume_profile(candles, bins=10)
    assert vp["low"] == 9 and vp["high"] == 14 and vp["val"] <= vp["poc"] <= vp["vah"]
    tpo = tk.tpo_profile(candles, bins=10)
    assert tpo and 9 <= tpo["poc"] <= 14
    vs = tk.volume_sma(candles, period=2)
    assert vs["period"] == 2 and vs["avg_volume"] == 250
    lc = tk.liquidity_clusters({"bids": [[100, 5], [99, 20]], "asks": [[101, 3], [102, 8]]}, top=1)
    assert lc["bid_walls"][0]["price"] == 99 and lc["ask_walls"][0]["price"] == 102
    assert tk.parse_candles([["1", "10", "12", "9", "11", "100", "x"]])[0]["close"] == 11

def test_chart_module_imports():
    import chart
    assert hasattr(chart, "render") and callable(chart.render)

def test_risk_manager():
    import os
    import risk_manager as rm
    lim = {"max_position_usd": 50, "max_leverage": 3, "max_open_positions": 3, "max_daily_loss_usd": 25}
    ok, _ = rm.check_trade({"notional_usd": 30, "leverage": 2}, open_positions=1, daily_loss_usd=5, limits=lim)
    assert ok
    ok, r = rm.check_trade({"notional_usd": 80, "leverage": 2}, open_positions=1, daily_loss_usd=5, limits=lim)
    assert not ok and "taille" in r
    ok, r = rm.check_trade({"notional_usd": 30, "leverage": 5}, open_positions=1, daily_loss_usd=5, limits=lim)
    assert not ok and "levier" in r
    ok, r = rm.check_trade({"notional_usd": 30, "leverage": 2}, open_positions=3, daily_loss_usd=5, limits=lim)
    assert not ok and "positions" in r
    ok, r = rm.check_trade({"notional_usd": 30, "leverage": 2}, open_positions=1, daily_loss_usd=30, limits=lim)
    assert not ok and "halte" in r
    os.environ["TRADING_HALT"] = "1"
    try:
        ok, r = rm.check_trade({"notional_usd": 30, "leverage": 2}, open_positions=0, daily_loss_usd=0, limits=lim)
        assert not ok and "KILL_SWITCH" in r
    finally:
        del os.environ["TRADING_HALT"]

def test_polymarket_parse():
    import polymarket_data as pm
    data = [
        {"question": "Will BTC hit 100k?", "outcomes": '["Yes","No"]', "outcomePrices": '["0.62","0.38"]',
         "volumeNum": 1234567, "slug": "btc-100k", "endDate": "2026-12-31"},
        {"question": "Will USA win World Cup?", "outcomes": '["Yes","No"]', "outcomePrices": '["0.04","0.96"]',
         "volumeNum": 999, "slug": "usa-wc"},
    ]
    rows = pm.parse_markets(data, query="btc", limit=5)
    assert len(rows) == 1 and rows[0]["question"].startswith("Will BTC")
    assert rows[0]["outcomes"][0] == {"name": "Yes", "prob_pct": 62.0}
    assert "polymarket.com/market/btc-100k" in rows[0]["url"]
    assert len(pm.parse_markets(data, limit=5)) == 2

def test_aggregated_derivs():
    import aggregated_derivs as ad
    parts = [
        {"exchange": "binance", "funding": 0.0001, "oi_usd": 2_000_000_000},
        {"exchange": "bybit", "funding": 0.0003, "oi_usd": 1_000_000_000},
        {"exchange": "bitget", "funding": None, "oi_usd": None},  # exclu (pas d'OI)
    ]
    agg = ad.aggregate(parts)
    assert agg["total_oi_usd"] == 3_000_000_000 and len(agg["exchanges"]) == 2
    assert abs(agg["oi_weighted_funding"] - (5e5 / 3e9)) < 1e-12
    assert ad.aggregate([])["oi_weighted_funding"] is None

def test_coingecko_parse():
    import coingecko_data as cg
    assert cg.resolve_id("btc") == "bitcoin" and cg.resolve_id("solana") == "solana"
    m = cg.parse_markets([{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin",
        "current_price": 64000, "market_cap": 1e12, "price_change_percentage_24h": -1.5, "total_volume": 3e10}])
    assert m[0]["symbol"] == "BTC" and m[0]["price"] == 64000 and m[0]["change_24h"] == -1.5
    g = cg.parse_global({"data": {"total_market_cap": {"usd": 2.3e12},
        "market_cap_percentage": {"btc": 54.2}, "market_cap_change_percentage_24h_usd": 0.8}})
    assert g["btc_dominance"] == 54.2 and g["total_market_cap_usd"] == 2.3e12

def test_news_parse():
    import news_feed
    rows = news_feed.parse_news({"results": [{"title": "BTC pumps", "source": {"title": "CoinDesk"},
        "published_at": "2026-01-01", "currencies": [{"code": "BTC"}], "url": "http://x"}]}, limit=5)
    assert rows[0]["title"] == "BTC pumps" and rows[0]["source"] == "CoinDesk" and rows[0]["currencies"] == ["BTC"]

def test_check_env_masks_value():
    import check_env
    line = check_env.status_line("X_API_KEY", "supersecretvalue123", optional=True)
    assert "supersecretvalue123" not in line  # ne revele JAMAIS la valeur
    assert "OK" in line and "19" in line
    assert "non defini" in check_env.status_line("X_API_KEY", None, optional=True)
    assert "MANQUANT" in check_env.status_line("BITGET_API_KEY", "", optional=False)


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

def test_order_signal_confluence_annotation():
    row = {"symbol": "BTCUSDT", "side": "LONG", "entry": "100", "stop_loss": "95", "take_profit": "110"}
    strong = ose.build_signal_card(row, confluence={"label": "FORTE CONFLUENCE", "score": 4})
    assert "FORTE CONFLUENCE" in strong and "Confiance : ÉLEVÉE" in strong
    weak = ose.build_signal_card(row, confluence={"label": "CONTRE-SIGNAL", "score": -3})
    assert "CONTRE-SIGNAL" in weak and "Confiance : FAIBLE" in weak
    assert "Confluence" not in ose.build_signal_card(row)  # rien sans confluence
    # le filtre sécurité n'est JAMAIS écrasé par la confluence :
    bad = dict(row, implied_leverage="5")  # > MAX_SIGNAL_LEVERAGE -> REJETÉ
    card = ose.build_signal_card(bad, confluence={"label": "FORTE CONFLUENCE", "score": 4})
    assert "REJETÉ" in card and "Confiance : FAIBLE" in card


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


# ---------- cerveau (essaim d'agents) ----------

def test_brain_aggregate_bias_and_consensus():
    import swarm_brain as sb
    # consensus pondéré par vote*conf*poids ; seuil ±0.2 -> LONG/SHORT/NEUTRE
    votes = {
        "a": {"vote": 1.0, "confidence": 1.0},
        "b": {"vote": 1.0, "confidence": 0.5},
        "c": {"vote": -1.0, "confidence": 0.0},  # conf nulle -> ignoré
    }
    r = sb.aggregate(votes, {"a": 1.0, "b": 1.0, "c": 1.0})
    assert r["bias"] == "LONG" and r["consensus"] == 1.0 and r["conviction"] == 1.0
    # désaccord équilibré -> proche de 0 -> NEUTRE
    neutral = sb.aggregate(
        {"a": {"vote": 1.0, "confidence": 1.0}, "b": {"vote": -1.0, "confidence": 1.0}},
        {"a": 1.0, "b": 1.0},
    )
    assert neutral["bias"] == "NEUTRE" and abs(neutral["consensus"]) < 1e-9
    # vote baissier dominant -> SHORT
    short = sb.aggregate({"a": {"vote": -0.8, "confidence": 1.0}}, {"a": 1.0})
    assert short["bias"] == "SHORT" and short["consensus"] < -0.2

def test_brain_aggregate_weighting():
    import swarm_brain as sb
    # un agent à poids fort doit tirer le consensus vers son vote
    votes = {"strong": {"vote": 1.0, "confidence": 1.0}, "weak": {"vote": -1.0, "confidence": 1.0}}
    r = sb.aggregate(votes, {"strong": 3.0, "weak": 0.2})
    assert r["consensus"] > 0.2 and r["bias"] == "LONG"

def test_brain_aggregate_empty_is_neutral():
    import swarm_brain as sb
    r = sb.aggregate({}, {})
    assert r["consensus"] == 0.0 and r["bias"] == "NEUTRE" and r["agents"] == []

def test_brain_update_weights_rewards_correct():
    import swarm_brain as sb
    w = sb.update_weights({"good": 1.0, "bad": 1.0, "skip": 1.0},
                          {"good": True, "bad": False, "skip": None})
    # bon agent renforcé au-dessus du mauvais ; None ignoré
    assert w["good"] > w["bad"]
    # normalisation : moyenne ~1 (à l'arrondi 3 décimales près)
    assert abs(sum(w.values()) / len(w) - 1.0) < 1e-2

def test_brain_update_weights_clamped():
    import swarm_brain as sb
    # un agent toujours juste, un toujours faux, sur de nombreuses itérations :
    # les bornes [0.2,3.0] empêchent la divergence -> le ratio reste plafonné.
    w = {"good": 1.0, "bad": 1.0}
    for _ in range(200):
        w = sb.update_weights(w, {"good": True, "bad": False})
    assert w["good"] > w["bad"]
    assert w["good"] / w["bad"] <= 3.0 / 0.2 + 1e-6  # ratio borné par les clamps

def test_brain_earcp_weights():
    import swarm_brain as sb
    perf = {"a": 3.0, "b": 1.0, "c": 0.3, "d": 1.0}
    coh = {"a": 0.9, "b": 0.5, "c": 0.2, "d": 0.5}
    w = sb.earcp_weights(perf, coh)
    assert abs(sum(w.values()) - 1.0) < 1e-3            # normalisé
    assert w["a"] == max(w.values())                    # meilleur perf+cohérence domine
    assert all(v >= 0.05 - 1e-9 for v in w.values())    # plancher garanti (exploration)
    # β règle l'arbitrage perf vs cohérence ; "a" domine sur les deux ici
    assert max(sb.earcp_weights(perf, coh, beta=1.0), key=lambda k: sb.earcp_weights(perf, coh, beta=1.0)[k]) == "a"
    assert sb.earcp_weights({}, {}) == {}               # vide -> vide, ne lève pas
    # plancher infaisable (w_min*M>=1) -> garde-fou, ne lève pas
    big = {str(i): 1.0 for i in range(30)}
    wb = sb.earcp_weights(big, big, w_min=0.05)
    assert abs(sum(wb.values()) - 1.0) < 1e-2

def test_brain_volatility_regime():
    import swarm_brain as sb, random
    random.seed(0)
    calm = [100.0]
    for _ in range(150):
        calm.append(calm[-1] * (1 + random.uniform(-0.002, 0.002)))
    turb = calm[:120]
    for _ in range(30):
        turb.append(turb[-1] * (1 + random.uniform(-0.03, 0.03)))
    assert sb.volatility_regime(calm)["scale"] == 1.0            # calme -> pleine confiance
    vt = sb.volatility_regime(turb)
    assert vt["regime"] in ("stressed", "extreme")
    assert 0.6 <= vt["scale"] < 1.0                              # escompte, mais jamais < 0.6
    assert sb.volatility_regime([100, 101, 102])["scale"] == 1.0  # court -> non bloquant

def test_brain_coherence_scores():
    import swarm_brain as sb
    log = [
        {"consensus": 0.5, "votes": {"x": 0.4, "y": -0.3}},   # consensus LONG
        {"consensus": 0.3, "votes": {"x": 0.2, "y": -0.1}},
        {"consensus": -0.4, "votes": {"x": -0.2, "y": 0.5}},  # consensus SHORT
    ]
    c = sb._coherence_scores(log)
    assert c["x"] == 1.0    # x toujours d'accord avec le consensus
    assert c["y"] == 0.0    # y toujours en désaccord

def test_runtime_cache():
    import runtime_cache as rc
    # decide() est pur : miss / fresh / stale
    assert rc.decide(None, 10, 100)[0] == "miss"
    assert rc.decide({"ts": 100, "val": 7}, 10, 105) == ("fresh", 7)
    assert rc.decide({"ts": 100, "val": 7}, 10, 120) == ("stale", 7)
    # get() : on isole le disque pour un test hermétique
    orig_load, orig_save = rc._load_disk, rc._save_disk
    rc._MEM.clear()
    store = {}
    rc._load_disk = lambda: dict(store)
    rc._save_disk = lambda d: store.update(d)
    try:
        calls = {"n": 0}
        def ok():
            calls["n"] += 1
            return calls["n"]
        assert rc.get("k", 10, ok, now=1000) == 1 and calls["n"] == 1   # miss -> fetch
        assert rc.get("k", 10, ok, now=1005) == 1 and calls["n"] == 1   # frais -> pas de fetch
        def boom():
            raise RuntimeError("réseau mort")
        assert rc.get("k", 10, boom, now=1100) == 1                     # stale-while-error
        assert rc.get("k", 10, ok, now=1200) == 2 and calls["n"] == 2   # expiré -> rafraîchit
        assert rc.get("absent", 10, boom, fallback={"x": 0}, now=1300) == {"x": 0}  # miss+échec -> fallback
    finally:
        rc._load_disk, rc._save_disk = orig_load, orig_save
        rc._MEM.clear()


# ---------- cerveau : agent divergent + cognition ----------

def test_brain_divergent_score():
    import swarm_brain as sb
    up = [100 + i for i in range(30)]       # forte hausse -> fader -> vote < 0
    assert sb.divergent_score(up) < 0
    down = [100 - i for i in range(30)]      # forte baisse -> rebond -> vote > 0
    assert sb.divergent_score(down) > 0
    assert sb.divergent_score([100, 101, 102]) == 0.0   # trop court -> neutre

def test_brain_divergent_helpers():
    import swarm_brain as sb
    assert abs(sb._slope([0, 1, 2, 3]) - 1.0) < 1e-9
    assert abs(sb._slope([3, 2, 1, 0]) + 1.0) < 1e-9
    assert sb._slope([5, 5, 5]) == 0.0
    assert sb._slope([7]) == 0.0
    # autocorrélation lag-1 : persistant -> +1, alterné -> -1 (critical slowing down)
    assert sb._lag1_autocorr([1, 2, 3, 4, 5, 6, 7, 8]) > 0.99
    assert sb._lag1_autocorr([1, -1, 1, -1, 1, -1, 1, -1]) < -0.99
    assert sb._lag1_autocorr([1, 2]) == 0.0

def test_brain_divergent_anticipation():
    import swarm_brain as sb
    # divergence haussière : prix qui descend mais momentum qui remonte en fin
    # -> l'agent ANTICIPE le rebond (vote > 0), pas une simple opposition.
    series = [100 - i * 0.6 for i in range(24)] + [100 - 24 * 0.6 + j * 0.9 for j in range(1, 7)]
    assert sb.divergent_score(series) > 0

def test_brain_divergent_instability_amplifies():
    import swarm_brain as sb, random
    # même DIRECTION (hausse -> fader, vote<0) mais variance brute qui MONTE en
    # 2e moitié : le critical slowing down doit amplifier la conviction.
    random.seed(2)
    calm = [100 + i * 0.5 + random.uniform(-0.1, 0.1) for i in range(30)]
    random.seed(2)
    turb = ([100 + i * 0.5 + random.uniform(-0.1, 0.1) for i in range(15)] +
            [100 + i * 0.5 + random.uniform(-3, 3) for i in range(15, 30)])
    vc, vt = sb.divergent_score(calm), sb.divergent_score(turb)
    assert vc < 0 and vt < 0
    assert abs(vt) >= abs(vc)
    assert -1.0 <= vt <= 1.0

def test_brain_cognition_groupthink():
    import swarm_brain as sb
    votes = {"a": {"vote": 0.8, "confidence": 0.8}, "b": {"vote": 0.7, "confidence": 0.7},
             "c": {"vote": 0.9, "confidence": 0.6}}
    cog = sb.cognition(votes, {"a": 1.0, "b": 1.0, "c": 1.0}, 0.8)
    assert cog["groupthink"] is True and cog["prudence"] == 0.8
    assert cog["agreement"] == 1.0 and 0.0 <= cog["weight_entropy"] <= 1.0
    # désaccord -> pas de groupthink, pleine confiance
    mixed = {"a": {"vote": 0.8, "confidence": 0.8}, "b": {"vote": -0.4, "confidence": 0.8}}
    cog2 = sb.cognition(mixed, {"a": 1.0, "b": 1.0}, 0.2)
    assert cog2["groupthink"] is False and cog2["prudence"] == 1.0

def test_brain_read_attaches_cognition():
    import swarm_brain as sb
    # aggregate + cognition cohérents sur des votes synthétiques
    votes = {n: {"vote": 0.5, "confidence": 0.5} for n in ("a", "b", "c")}
    w = {"a": 1.0, "b": 1.0, "c": 1.0}
    res = sb.aggregate(votes, w)
    res = sb._attach_cognition(res, votes, w)
    assert "cognition" in res and "adjusted_conviction" in res
    # groupthink (accord total, conviction forte) -> conviction ajustée <= conviction
    assert res["adjusted_conviction"] <= res["conviction"]


# ---------- liquidations (modèle) ----------

def test_liquidation_levels_sides_and_distance():
    import liquidations as lq
    lvls = lq.liquidation_levels(100.0, 1_000_000.0, long_share=0.5)
    longs = [x for x in lvls if x["side"] == "long"]
    shorts = [x for x in lvls if x["side"] == "short"]
    assert longs and shorts
    # longs se liquident SOUS le prix, shorts AU-DESSUS
    assert all(x["price"] < 100.0 and x["distance_pct"] < 0 for x in longs)
    assert all(x["price"] > 100.0 and x["distance_pct"] > 0 for x in shorts)
    # 10x liquide à ±10%
    l10 = next(x for x in longs if x["leverage"] == 10)
    assert abs(l10["distance_pct"] + 10.0) < 1e-6
    # notionnel total ~ OI
    assert abs(sum(x["notional_usd"] for x in lvls) - 1_000_000.0) < 1.0

def test_liquidation_levels_guard_and_share():
    import liquidations as lq
    assert lq.liquidation_levels(0, 100) == [] and lq.liquidation_levels(100, 0) == []
    # plus de longs -> plus de notionnel côté long
    lvls = lq.liquidation_levels(100.0, 1000.0, long_share=0.8)
    lo = sum(x["notional_usd"] for x in lvls if x["side"] == "long")
    sh = sum(x["notional_usd"] for x in lvls if x["side"] == "short")
    assert lo > sh

def test_liquidation_skew_direction():
    import liquidations as lq
    price = 100.0
    # gros pool de shorts proche au-dessus -> net > 0 (aimant haussier)
    levels = [
        {"side": "short", "leverage": 50, "price": 102, "distance_pct": 2.0, "notional_usd": 900.0},
        {"side": "long", "leverage": 10, "price": 90, "distance_pct": -10.0, "notional_usd": 100.0},
    ]
    sk = lq.liquidation_skew(levels, price, band_pct=8.0)
    assert sk["net"] > 0 and sk["nearest_short"]["distance_pct"] == 2.0
    # hors bande : ignoré
    far = lq.liquidation_skew([{"side": "short", "leverage": 3, "price": 133,
                                "distance_pct": 33.0, "notional_usd": 1e9}], price, band_pct=8.0)
    assert far["net"] == 0.0

def test_liquidation_cluster_map_sorted():
    import liquidations as lq
    lvls = lq.liquidation_levels(100.0, 1_000_000.0, long_share=0.5)
    cm = lq.cluster_map(lvls, bucket_pct=1.0, top=5)
    assert len(cm) <= 5
    assert all(cm[i]["notional_usd"] >= cm[i + 1]["notional_usd"] for i in range(len(cm) - 1))


# ---------- calendrier éco (modèle pur) ----------

def test_econ_calendar_parse_filters():
    import econ_calendar as ec
    from datetime import datetime, timezone
    now = datetime(2026, 6, 22, 0, 0, tzinfo=timezone.utc)
    data = [
        {"title": "Core CPI m/m", "country": "USD", "impact": "High",
         "date": "2026-06-22T12:00:00+00:00", "forecast": "0.3%", "previous": "0.2%"},
        {"title": "Retail Sales", "country": "EUR", "impact": "Medium",
         "date": "2026-06-23T00:00:00+00:00"},
        {"title": "Bank Holiday", "country": "GBP", "impact": "Holiday",
         "date": "2026-06-22T00:00:00+00:00"},
    ]
    # impact High seulement -> 1 event, hours_until = 12
    high = ec.parse_calendar(data, impact_min="High", now=now)
    assert len(high) == 1 and high[0]["currency"] == "USD"
    assert abs(high[0]["hours_until"] - 12.0) < 1e-6
    # impact Medium -> inclut CPI + Retail Sales (triés par proximité)
    med = ec.parse_calendar(data, impact_min="Medium", now=now)
    assert [e["title"] for e in med] == ["Core CPI m/m", "Retail Sales"]
    # filtre devise
    assert ec.parse_calendar(data, impact_min="Medium", currencies=["EUR"], now=now)[0]["currency"] == "EUR"

def test_econ_calendar_within_and_next():
    import econ_calendar as ec
    from datetime import datetime, timezone
    now = datetime(2026, 6, 22, 0, 0, tzinfo=timezone.utc)
    data = [
        {"title": "Past", "country": "USD", "impact": "High", "date": "2026-06-21T00:00:00+00:00"},
        {"title": "Soon", "country": "USD", "impact": "High", "date": "2026-06-22T06:00:00+00:00"},
        {"title": "Later", "country": "USD", "impact": "High", "date": "2026-06-25T00:00:00+00:00"},
    ]
    win = ec.parse_calendar(data, impact_min="High", within_hours=24, now=now)
    assert [e["title"] for e in win] == ["Soon"]  # passé exclu, >24h exclu
    nxt = ec.next_high_impact(ec.parse_calendar(data, impact_min="High", now=now))
    assert nxt["title"] == "Soon"


# ---------- arbitrage / détection d'écarts (purs) ----------

def test_arbitrage_spot_spread():
    import arbitrage as ab
    assert ab.spot_spread({"a": 100.0}) is None         # < 2 cotations
    assert ab.spot_spread({"a": None, "b": None}) is None
    s = ab.spot_spread({"binance": 100.0, "okx": 101.0, "bybit": None})
    assert s["buy_at"] == "binance" and s["sell_at"] == "okx"
    assert abs(s["spread_pct"] - 1.0) < 1e-6

def test_arbitrage_basis_and_funding():
    import arbitrage as ab
    assert ab.basis(0, 100) is None and ab.basis(100, 0) is None
    b = ab.basis(100.0, 101.0)
    assert abs(b["basis_pct"] - 1.0) < 1e-6        # perp au-dessus du spot = contango
    parts = [{"exchange": "binance", "funding": 0.0003}, {"exchange": "bybit", "funding": -0.0001},
             {"exchange": "okx", "funding": None}]
    fs = ab.funding_spread(parts)
    # short là où funding le plus haut, long là où le plus bas
    assert fs["short_on"] == "binance" and fs["long_on"] == "bybit"
    assert abs(fs["spread"] - 0.0004) < 1e-9
    assert ab.funding_spread([{"exchange": "x", "funding": 0.1}]) is None


# ---------- macro TradFi (yfinance, modèle pur) ----------

def test_macro_data_summarize_regime():
    import macro_data as md
    # VIX bas + DXY en baisse -> risk-on
    on = md.summarize({"VIX": {"last": 15.0, "change_pct": -1.0},
                       "DXY": {"last": 100.0, "change_pct": -0.8}})
    assert on["regime"] == "RISK_ON" and on["score"] > 0
    # VIX élevé + DXY en hausse -> risk-off
    off = md.summarize({"VIX": {"last": 30.0, "change_pct": 4.0},
                        "DXY": {"last": 106.0, "change_pct": 1.0}})
    assert off["regime"] == "RISK_OFF" and off["score"] < 0
    # quotes vides -> neutre, ne lève pas
    assert md.summarize({})["regime"] == "NEUTRE"

def test_macro_data_degrades_without_lib(monkeypatch=None):
    import macro_data as md
    # si yfinance absent, fetch_macro renvoie une erreur claire et fetch_regime None
    orig = md._available
    md._available = lambda: False
    try:
        d = md.fetch_macro()
        assert d.get("error") and "yfinance" in d["error"] and d["regime"] == "NEUTRE"
        assert md.fetch_regime() is None
    finally:
        md._available = orig


# ---------- ccxt multi-exchange (purs + dégradation) ----------

def test_ccxt_symbol_conversion():
    import ccxt_markets as cm
    assert cm._to_spot("BTCUSDT") == "BTC/USDT"
    assert cm._to_swap("ETHUSDT") == "ETH/USDT:USDT"
    assert cm._to_spot("SOL/USDT:USDT") == "SOL/USDT"
    assert cm._split("BTCUSDC") == ("BTC", "USDC")

def test_ccxt_degrades_without_lib():
    import ccxt_markets as cm
    orig = cm.available
    cm.available = lambda: False
    try:
        assert "error" in cm.fetch_spot_prices("BTCUSDT")
        assert cm.cross_exchange("BTCUSDT").get("error")
    finally:
        cm.available = orig

def test_ccxt_cross_exchange_aggregates():
    import ccxt_markets as cm
    orig_av, orig_fp = cm.available, cm.fetch_spot_prices
    cm.available = lambda: True
    cm.fetch_spot_prices = lambda s, exchanges=None: {"binance": 100.0, "okx": 101.0, "bybit": None}
    try:
        out = cm.cross_exchange("BTCUSDT")
        assert out["venues"] == 2
        assert out["spread"]["buy_at"] == "binance" and out["spread"]["sell_at"] == "okx"
        assert abs(out["spread"]["spread_pct"] - 1.0) < 1e-6
    finally:
        cm.available, cm.fetch_spot_prices = orig_av, orig_fp


# ---------- backtester du cerveau (purs) ----------

def test_backtest_forward_returns():
    import backtest_brain as bt
    assert bt.forward_returns([100, 110, 121], 1) == [0.1, 0.1]
    assert bt.forward_returns([100, 100], 1) == [0.0]
    fr = bt.forward_returns([100, 50, 200], 2)
    assert len(fr) == 1 and abs(fr[0] - 1.0) < 1e-9

def test_backtest_evaluate_perfect_and_wrong():
    import backtest_brain as bt
    good = bt.evaluate([1, -1, 1], [0.1, -0.1, 0.1], fee=0.0)
    assert good["trades"] == 3 and good["hit_rate"] == 1.0 and good["total_return"] > 0
    bad = bt.evaluate([1, -1], [-0.1, 0.1], fee=0.0)
    assert bad["hit_rate"] == 0.0 and bad["total_return"] < 0
    # signal nul ignoré
    assert bt.evaluate([0, 1], [0.5, 0.1], fee=0.0)["trades"] == 1

def test_backtest_evaluate_fee_reduces_return():
    import backtest_brain as bt
    nofee = bt.evaluate([1, 1, 1], [0.01, 0.01, 0.01], fee=0.0)["total_return"]
    withfee = bt.evaluate([1, 1, 1], [0.01, 0.01, 0.01], fee=0.005)["total_return"]
    assert withfee < nofee

def test_backtest_technical_signal_trend():
    import backtest_brain as bt
    up = [{"open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 10} for i in range(60)]
    assert bt.technical_signal(up) > 0
    down = [{"open": 200 - i, "high": 201 - i, "low": 199 - i, "close": 200 - i, "volume": 10} for i in range(60)]
    assert bt.technical_signal(down) < 0

def test_backtest_walk_forward():
    import backtest_brain as bt
    folds = bt.walk_forward([0.01] * 10, k=5)
    assert len(folds) == 5 and all(f > 0 for f in folds)
    assert bt.walk_forward([0.01], k=5) == []          # trop court

def test_backtest_pbo_bounds_and_dominance():
    import backtest_brain as bt
    # config A domine partout -> meilleure IS = meilleure OOS -> aucun surapprentissage
    fam = {"A": [0.02] * 40, "B": [0.01] * 40}
    res = bt.pbo(fam, n_blocks=4)
    assert res["n_combos"] == 6 and 0.0 <= res["pbo"] <= 1.0
    assert res["pbo"] == 0.0
    # une seule config -> PBO indéfini (None), pas de crash
    assert bt.pbo({"only": [0.01] * 10})["pbo"] is None


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
