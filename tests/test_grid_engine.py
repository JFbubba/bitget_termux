import grid_engine as ge

def test_surface_descriptors():
    assert ge.SURFACE["spot"]["maker_bps"] == 8 and ge.SURFACE["spot"]["short"] is False
    assert ge.SURFACE["margin"]["maker_bps"] == 8 and ge.SURFACE["margin"]["short"] is True
    assert ge.SURFACE["futures"]["maker_bps"] == 2 and ge.SURFACE["futures"]["funding"] is True
    assert ge.SURFACE["futures"]["lev_max"] == 5 and ge.SURFACE["futures"]["cap_op"] == 50

def test_gconfig_injects_surface_fees():
    cfg = ge.gconfig(mode="bidirectional", surface="futures", spacing=0.01, k_atr=3.0)
    assert cfg["mode"] == "bidirectional" and cfg["surface"] == "futures"
    assert cfg["fee_bps"] == 2 and cfg["slip_bps"] == 4          # de la surface futures
    assert cfg["spacing"] == 0.01 and cfg["k_atr"] == 3.0        # passe à grid_lab.config
    assert cfg["funding_lean"] == 0.0 and cfg["borrow_bps_per_day"] == 0.0

def test_funding_sign():
    # rate>0 : le LONG paie -> P&L négatif ; le SHORT encaisse -> P&L positif
    assert ge.funding_pnl(net_qty=1.0, price=100.0, rate=0.0001) < 0
    assert ge.funding_pnl(net_qty=-1.0, price=100.0, rate=0.0001) > 0
    # symétrie exacte
    assert ge.funding_pnl(1.0, 100.0, 0.0001) == -ge.funding_pnl(-1.0, 100.0, 0.0001)
    # rate=0 ou net_qty=0 -> 0
    assert ge.funding_pnl(1.0, 100.0, 0.0) == 0.0
    assert ge.funding_pnl(0.0, 100.0, 0.0001) == 0.0
    # magnitude : |net_qty * price * rate|
    assert abs(ge.funding_pnl(2.0, 100.0, 0.0001) - (-2.0 * 100.0 * 0.0001)) < 1e-12
