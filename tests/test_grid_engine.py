import grid_engine as ge
import grid_lab as gl

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


def _serie_range(n=1000, base=100.0, amp=0.03, period=20.0):
    # série oscillante déterministe (pas d'aléa) autour de base, faible tendance ;
    # amp/period réglables (Task 4 réutilise ce helper, ne pas le figer sur un seul cas)
    import math
    out = []
    for i in range(n):
        px = base * (1 + amp * math.sin(i / period) + 0.00001 * i)
        h = px * 1.002; low = px * 0.998; vol = 1000.0
        out.append([1_700_000_000_000 + i * 3_600_000, px, h, low, px, vol])
    return out


# Régime relâché : déploiement garanti + aucune coupe forcée par le filtre. On isole
# les mécaniques short/funding/hedge — le filtre de régime est celui de grid_lab,
# déjà testé là-bas et réutilisé verbatim, donc rien de neuf à tester ici.
_RELAX = dict(adx_max=999.0, bb_expand_max=99.0, vol_expand_max=99.0,
              vol_spike=999.0, adx_exit=999.0, atr_exit_mult=999.0)


def test_simulate_g_longonly_parity():
    candles = _serie_range()
    # gates de régime relâchés (déploiement garanti, pas de coupe forcée par le
    # filtre) — IDENTIQUES des deux côtés pour une parité réelle plutôt qu'un 0==0
    # rung_notional monté (défaut grid_lab = 5.0) : l'écart introduit par la
    # convention de latent (rung/entry vs rung/c) est proportionnel au notional et
    # s'efface sous l'arrondi interne à 4 décimales des deux moteurs si rung=5 —
    # un rung plus gros rend la divergence mesurable (test discriminant, pas un
    # simple 0==0 déguisé). N'affecte pas les niveaux de grille (prix seuls),
    # donc n_buys/n_sells/cuts restent identiques quel que soit le rung.
    base = gl.config(spacing=0.008, k_atr=3.0, fee_bps=8, slip_bps=2,
                      rung_notional=500.0, **_RELAX)
    ref = gl.simulate(candles, base)
    cfg = ge.gconfig(mode="long_only", surface="spot", spacing=0.008, k_atr=3.0,
                      rung_notional=500.0, **_RELAX)
    got = ge.simulate_g(candles, cfg)
    assert ref is not None and got is not None
    assert ref["n_buys"] > 0 and ref["n_sells"] > 0, "la grille de référence doit REMPLIR (pas 0==0)"
    for k in ("total_pnl", "grid_profit", "fees", "n_buys", "n_sells", "cuts"):
        assert abs(got[k] - ref[k]) < 1e-6, f"divergence sur {k}: {got[k]} vs {ref[k]}"


def test_short_leg_profits_symmetric_range():
    # bidirectional sur un range : ouvertures ET fermetures des deux jambes
    candles = _serie_range(n=1000)
    cfg = ge.gconfig(mode="bidirectional", surface="futures", spacing=0.008, k_atr=3.0,
                     rung_notional=500.0, **_RELAX)
    r = ge.simulate_g(candles, cfg)
    assert r is not None
    assert r["n_buys"] > 0 and r["n_sells"] > 0        # la grille remplit vraiment

def test_neutral_hedge_shifts_delta_short():
    # Seule la couverture (short) distingue neutral de bidirectional sur la MÊME série :
    # fills IDENTIQUES, et le hedge déplace le delta net vers le short d'EXACTEMENT
    # hedge_qty>0 -> assertion DÉTERMINISTE (pas une inégalité |delta| fragile au dernier
    # barreau, qui n'est vraie qu'en moyenne).
    candles = _serie_range(n=1000)
    cbid = ge.gconfig(mode="bidirectional", surface="futures", spacing=0.008, k_atr=3.0,
                      rung_notional=500.0, **_RELAX)
    cneu = ge.gconfig(mode="neutral", surface="futures", spacing=0.008, k_atr=3.0,
                      rung_notional=500.0, **_RELAX)
    rb = ge.simulate_g(candles, cbid)
    rn = ge.simulate_g(candles, cneu)
    assert rb is not None and rn is not None
    assert rn["n_buys"] == rb["n_buys"] and rn["n_sells"] == rb["n_sells"]   # mêmes fills
    assert rn["net_delta_final"] < rb["net_delta_final"]                     # hedge = short

def test_accounting_identity():
    # TOTAL == grid_profit + latent_final + funding − fees − borrow (à la clôture)
    candles = _serie_range(n=1000)
    fund = [(candles[k][0], 0.0001) for k in range(0, len(candles), 8)]   # funding synthétique
    cfg = ge.gconfig(mode="neutral", surface="futures", spacing=0.008, k_atr=3.0,
                     funding_lean=0.5, rung_notional=500.0, **_RELAX)
    r = ge.simulate_g(candles, cfg, funding=fund)
    lhs = r["total_pnl"]
    rhs = r["grid_profit"] + r["latent_final"] + r["funding_pnl_total"] - r["fees"] - r["borrow_total"]
    assert abs(lhs - rhs) < 1e-2, f"identité rompue: {lhs} vs {rhs}"

def test_borrow_only_margin_short():
    candles = _serie_range(n=1000)
    cf = ge.gconfig(mode="neutral", surface="futures", spacing=0.008, k_atr=3.0,
                    borrow_bps_per_day=50, rung_notional=500.0, **_RELAX)
    cm = ge.gconfig(mode="neutral", surface="margin",  spacing=0.008, k_atr=3.0,
                    borrow_bps_per_day=50, rung_notional=500.0, **_RELAX)
    cmb = ge.gconfig(mode="bidirectional", surface="margin", spacing=0.008, k_atr=3.0,
                     borrow_bps_per_day=50, rung_notional=500.0, **_RELAX)
    assert ge.simulate_g(candles, cf)["borrow_total"] == 0.0       # futures : pas de borrow
    b_neutral = ge.simulate_g(candles, cm)["borrow_total"]
    b_bidir = ge.simulate_g(candles, cmb)["borrow_total"]
    assert b_neutral > 0.0                                          # marge short : borrow accumulé
    assert b_neutral > b_bidir                                     # le hedge neutre AJOUTE du borrow (spec §4.3)
