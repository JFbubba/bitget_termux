import grid_engine_lab as gel
import grid_engine as ge


def _serie_range(n=1000, base=100.0, amp=0.03, period=20.0):
    import math
    return [[1_700_000_000_000 + i * 3_600_000,
             base * (1 + amp * math.sin(i / period)), base * 1.002, base * 0.998,
             base * (1 + amp * math.sin(i / period)), 1000.0] for i in range(n)]


# Régime relâché pour FORCER le déploiement en test unitaire (le filtre de régime est
# celui de grid_lab, déjà testé ; on isole ici le PIPELINE de jugement/déflation).
_RELAX = dict(adx_max=999.0, bb_expand_max=99.0, vol_expand_max=99.0,
              vol_spike=999.0, adx_exit=999.0, atr_exit_mult=999.0)


def _relaxed_sweep(mode, surface):
    # même grille que config_sweep (8 configs) mais régime relâché + gros rung
    out = []
    for spacing in (0.004, 0.007, 0.012, 0.02):
        for k in (2.5, 3.5):
            out.append((f"{surface}/{mode} g={spacing*100:.1f}%·k={k}",
                        ge.gconfig(mode=mode, surface=surface, spacing=spacing, k_atr=k,
                                   rung_notional=500.0, **_RELAX)))
    return out


def test_combos_valid_per_surface():
    combos = gel.combos()
    assert ("spot", "long_only") in combos
    assert ("margin", "neutral") in combos and ("futures", "neutral") in combos
    # jamais un mode short sur spot, jamais long_only sur futures dans le balayage
    assert ("spot", "bidirectional") not in combos
    assert all(m in ge.MODES and s in ge.SURFACE for (s, m) in combos)


def test_config_sweep_size_and_fees():
    sw = gel.config_sweep("neutral", "futures")
    assert len(sw) == 8
    assert all(cfg["fee_bps"] == 2 and cfg["mode"] == "neutral" for _, cfg in sw)


def test_evaluate_cell_deflates_over_full_sweep():
    # cfg_list relâché -> déploiement garanti -> le pipeline de jugement s'exécute vraiment
    candles = _serie_range(n=1000)
    ev = gel.evaluate_cell(candles, "neutral", "futures", funding=None,
                           cfg_list=_relaxed_sweep("neutral", "futures"))
    assert ev is not None                          # a vraiment déployé/jugé
    assert ev["n_trials"] >= 8                     # déflation sur TOUT le balayage
    assert "survives" in ev and "dsr" in ev and isinstance(ev["survives"], bool)


def test_evaluate_cell_wellformed_both_modes():
    # structure du verdict pour la baseline long_only/spot ET le neutre/futures.
    # (La NON-RÉGRESSION du verdict mort se mesure sur données RÉELLES au smoke run
    #  Task 6 : sur une sinusoïde SYNTHÉTIQUE parfaite une grille GAGNE — c'est le
    #  meilleur cas de range —, donc « pas de survivant » n'a de sens que sur du réel.)
    candles = _serie_range(n=1000)
    for surface, mode in (("spot", "long_only"), ("futures", "neutral")):
        ev = gel.evaluate_cell(candles, mode, surface, funding=None,
                               cfg_list=_relaxed_sweep(mode, surface))
        assert ev is not None
        for key in ("survives", "dsr", "mode", "surface", "total_pnl", "oos_total"):
            assert key in ev
        assert isinstance(ev["survives"], bool)


def test_low_power_funding_counts_in_window():
    # funding : 100 vieux fixings AVANT la fenêtre + seulement 5 DEDANS ->
    # la garde doit voir 5 (in-window), pas 105 (historique complet) -> low_power=True
    candles = _serie_range(n=200)                      # fenêtre ~8,3 jours (horaire)
    t0 = candles[0][0]
    old = [(t0 - (k + 1) * 8 * 3_600_000, 0.0001) for k in range(100)]   # hors fenêtre (avant)
    inw = [(t0 + (k + 1) * 8 * 3_600_000, 0.0001) for k in range(5)]     # 5 fixings 8h dans la fenêtre
    fund = sorted(old + inw)
    ev = gel.evaluate_cell(candles, "neutral", "futures", funding=fund,
                           cfg_list=_relaxed_sweep("neutral", "futures"))
    assert ev is not None
    assert ev["n_funding"] == 5              # seuls les fixings DANS la fenêtre comptent
    assert ev["low_power_funding"] is True   # 5 < 90
    assert ev["survives"] is False           # low_power bloque la survie
