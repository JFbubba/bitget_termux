"""Suite pytest d'indicators.py — indicateurs PURS du chemin de décision (SAFE).

Verrouille en particulier le correctif du BUG SILENCIEUX documenté en tête de
module : données insuffisantes -> ValueError EXPLICITE, jamais une valeur fausse.
"""
import pytest

import indicators


# ---------------------------------------------------------------------------
# ema — EMA seed SMA ; le contrat anti-bug-silencieux est la garantie clé
# ---------------------------------------------------------------------------

def test_ema_donnees_insuffisantes_leve_valueerror():
    # AVANT le correctif : division par period sur données courtes -> valeur
    # fausse SANS erreur. Le contrat est désormais : lever, jamais approximer.
    with pytest.raises(ValueError, match="insuffisantes"):
        indicators.ema([1.0, 2.0, 3.0], period=3)


@pytest.mark.parametrize("period", [0, -1])
def test_ema_periode_invalide_leve_valueerror(period):
    with pytest.raises(ValueError, match="période invalide"):
        indicators.ema([1.0, 2.0, 3.0, 4.0], period=period)


def test_ema_seed_sma_puis_recurrence():
    # seed = SMA des 3 premières = 2.0 ; multiplicateur 2/(3+1)=0.5 -> (4−2)×0.5+2 = 3.0
    assert indicators.ema([1.0, 2.0, 3.0, 4.0], period=3) == pytest.approx([2.0, 3.0])


def test_ema_serie_constante_reste_constante():
    assert indicators.ema([5.0] * 10, period=3) == pytest.approx([5.0] * 8)


def test_ema_longueur_de_sortie():
    # 1 valeur seed + une par bougie au-delà de la période
    assert len(indicators.ema(list(range(1, 21)), period=9)) == 20 - 9 + 1


# ---------------------------------------------------------------------------
# calculate_rsi — RSI Wilder, borné [0, 100]
# ---------------------------------------------------------------------------

def test_rsi_donnees_insuffisantes_leve_valueerror():
    with pytest.raises(ValueError, match="insuffisantes"):
        indicators.calculate_rsi([1.0] * 14, period=14)


def test_rsi_hausse_monotone_vaut_100():
    # Aucune perte -> avg_loss = 0 -> RSI = 100 partout
    rsi = indicators.calculate_rsi([float(i) for i in range(1, 21)], period=14)
    assert rsi == pytest.approx([100.0] * len(rsi))


def test_rsi_baisse_monotone_vaut_0():
    rsi = indicators.calculate_rsi([float(i) for i in range(20, 0, -1)], period=14)
    assert rsi == pytest.approx([0.0] * len(rsi))


def test_rsi_alternance_equilibree_demarre_a_50():
    # +1/−1 en alternance : gains moyens = pertes moyennes -> 50 au premier point
    values = [10.0 + (i % 2) for i in range(15)]
    assert indicators.calculate_rsi(values, period=14)[0] == pytest.approx(50.0)


def test_rsi_toujours_borne_0_100():
    values = [100.0, 103.0, 99.0, 104.0, 98.0, 105.0, 97.0, 106.0, 96.0,
              107.0, 95.0, 108.0, 94.0, 109.0, 93.0, 110.0, 92.0, 111.0]
    for r in indicators.calculate_rsi(values, period=14):
        assert 0.0 <= r <= 100.0


# ---------------------------------------------------------------------------
# calculate_atr — ATR Wilder sur bougies {high, low, close}, gaps compris
# ---------------------------------------------------------------------------

def _bougie(high, low, close, **extra):
    return {"high": high, "low": low, "close": close, **extra}


def test_atr_donnees_insuffisantes_leve_valueerror():
    with pytest.raises(ValueError, match="insuffisantes"):
        indicators.calculate_atr([_bougie(2, 1, 1.5)] * 14, period=14)


def test_atr_range_constant_sans_gap():
    # Range 2 constant, clôtures alignées -> TR = 2 partout -> ATR = 2 partout
    candles = [_bougie(102.0, 100.0, 101.0) for _ in range(16)]
    atr = indicators.calculate_atr(candles, period=14)
    assert atr == pytest.approx([2.0] * len(atr))


def test_atr_le_gap_compte_dans_le_true_range():
    # c2 gap haussier : TR = |high − close précédent| = 9.5 domine le range 1.0
    candles = [_bougie(100.5, 99.5, 100.0),
               _bougie(101.0, 100.0, 100.5),
               _bougie(110.0, 109.0, 109.5)]
    assert indicators.calculate_atr(candles, period=2) == pytest.approx([5.25])


# ---------------------------------------------------------------------------
# volume_anchored_level — S/R = clôture de la bougie au plus gros volume
# ---------------------------------------------------------------------------

def test_volume_anchored_level_prend_le_max_volume_de_la_fenetre():
    candles = ([{"close": 999.0, "volume": 1000.0}]          # hors lookback : ignoré
               + [{"close": 10.0, "volume": 1.0}] * 15
               + [{"close": 42.0, "volume": 50.0}]           # max DANS la fenêtre
               + [{"close": 11.0, "volume": 2.0}] * 4)
    assert indicators.volume_anchored_level(candles, lookback=20) == 42.0


def test_volume_anchored_level_entrees_invalides():
    with pytest.raises(ValueError, match="lookback"):
        indicators.volume_anchored_level([{"close": 1.0, "volume": 1.0}], lookback=0)
    with pytest.raises(ValueError, match="aucune bougie"):
        indicators.volume_anchored_level([], lookback=20)


# ---------------------------------------------------------------------------
# volume_bias_score — conviction pondérée par le volume
# ---------------------------------------------------------------------------

def test_volume_bias_haussier_volume_croissant():
    # 1re bougie : poids 1 (pas de volume précédent) ; puis +3, +3 -> total 7
    candles = [{"open": 1.0, "close": 2.0, "volume": float(v)} for v in (1, 2, 3)]
    assert indicators.volume_bias_score(candles, lookback=20) == 7


def test_volume_bias_baissier_volume_decroissant():
    # Baissier + volume en baisse -> −1 chacun
    candles = [{"open": 2.0, "close": 1.0, "volume": float(v)} for v in (3, 2, 1)]
    assert indicators.volume_bias_score(candles, lookback=20) == -3


def test_volume_bias_doji_contribution_nulle():
    candles = [{"open": 1.0, "close": 1.0, "volume": float(v)} for v in (1, 2, 3)]
    assert indicators.volume_bias_score(candles, lookback=20) == 0


def test_volume_bias_lookback_invalide_leve():
    with pytest.raises(ValueError, match="lookback"):
        indicators.volume_bias_score([], lookback=0)


# ---------------------------------------------------------------------------
# savitzky_golay — lissage pur ; préserve longueur et tendances
# ---------------------------------------------------------------------------

def test_savgol_vide_renvoie_vide():
    assert indicators.savitzky_golay([]) == []


def test_savgol_preserve_la_longueur():
    values = [float(i % 5) for i in range(30)]
    assert len(indicators.savitzky_golay(values, window=11, poly=2)) == 30


def test_savgol_serie_courte_retombe_sur_l_entree():
    assert indicators.savitzky_golay([1.0, 2.0]) == [1.0, 2.0]


def test_savgol_droite_preservee_hors_bords():
    # Un polynôme d'ordre ≥ 1 reproduit exactement une droite (hors bords répliqués)
    values = [float(i) for i in range(20)]
    out = indicators.savitzky_golay(values, window=5, poly=2)
    assert out[2:-2] == pytest.approx(values[2:-2], abs=1e-6)


def test_savgol_attenue_le_bruit_alternant():
    # Bruit ±1 pur : le lissage doit réduire l'amplitude au centre
    values = [1.0 if i % 2 == 0 else -1.0 for i in range(20)]
    out = indicators.savitzky_golay(values, window=5, poly=2)
    assert all(abs(v) < 1.0 for v in out[2:-2])
