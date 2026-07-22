"""Suite pytest de fair_price.py — référence cross-exchange + premium Bitget (SAFE).

Fonctions pures testées en direct ; `fair_value`/`build_report` testées avec un
FAUX module `arbitrage` injecté dans sys.modules (mock de la dépendance réseau,
restauré par monkeypatch) — aucun appel réseau réel.
"""
import sys
import types

import pytest

import fair_price


# ---------------------------------------------------------------------------
# median — médiane pure, filtre les valeurs absentes ou non positives
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "xs, attendu",
    [
        ([3.0], 3.0),                       # singleton
        ([3.0, 1.0, 2.0], 2.0),             # impair, non trié
        ([100.0, 103.0, 101.0, 102.0], 101.5),  # pair : moyenne des deux centraux
        (["3", 1], 2.0),                    # chaînes numériques acceptées
    ],
)
def test_median_valeurs_valides(xs, attendu):
    assert fair_price.median(xs) == pytest.approx(attendu)


@pytest.mark.parametrize("xs", [[], [None, None], [0.0, -1.0]])
def test_median_sans_valeur_positive_renvoie_none(xs):
    # None, zéro et négatifs sont filtrés : pas de prix -> pas de médiane
    assert fair_price.median(xs) is None


def test_median_ignore_none_et_non_positifs_au_milieu_de_valides():
    assert fair_price.median([None, 0.0, 5.0, -2.0, 3.0]) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# premium_pct — écart en % vs référence, arrondi à 4 décimales
# ---------------------------------------------------------------------------

def test_premium_pct_prix_au_dessus_positif():
    assert fair_price.premium_pct(103.0, 101.0) == pytest.approx(1.9802, abs=1e-4)


def test_premium_pct_prix_en_dessous_negatif():
    assert fair_price.premium_pct(99.0, 100.0) == pytest.approx(-1.0)


@pytest.mark.parametrize(
    "price, reference",
    [
        (None, 100.0),   # prix inconnu
        (100.0, None),   # référence inconnue
        (0.0, 100.0),    # prix nul (falsy)
        (100.0, 0.0),    # référence nulle : jamais de division par zéro
    ],
)
def test_premium_pct_entrees_absentes_ou_nulles_renvoie_none(price, reference):
    assert fair_price.premium_pct(price, reference) is None


# ---------------------------------------------------------------------------
# is_fair_to_buy — garde premium de l'accumulation (fail-open documenté)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "premium, attendu",
    [
        (None, True),    # inconnu -> on ne bloque JAMAIS faute de données
        (-1.5, True),    # discount : bonne affaire
        (0.30, True),    # exactement au seuil (≤)
        (0.31, False),   # au-dessus du seuil par défaut
    ],
)
def test_is_fair_to_buy_seuil_par_defaut(premium, attendu):
    assert fair_price.is_fair_to_buy(premium) is attendu


def test_is_fair_to_buy_seuil_injecte():
    assert fair_price.is_fair_to_buy(0.5, max_premium_pct=1.0) is True
    assert fair_price.is_fair_to_buy(1.5, max_premium_pct=1.0) is False


# ---------------------------------------------------------------------------
# fair_value / build_report — dépendance `arbitrage` MOCKÉE (aucun réseau)
# ---------------------------------------------------------------------------

def _faux_arbitrage(quotes):
    """Fabrique un faux module arbitrage : SPOT_FUNCS + _safe, prix imposés."""
    mod = types.ModuleType("arbitrage")
    mod.SPOT_FUNCS = {ex: (lambda sym, _p=p: _p) for ex, p in quotes.items()}
    mod._safe = lambda fn, sym: fn(sym)
    return mod


def test_fair_value_mediane_hors_bitget_et_premium(monkeypatch):
    # Arrange : Bitget cote 103, le marché 100/101/102 -> fair=101, premium=+1.98 %
    monkeypatch.setitem(sys.modules, "arbitrage", _faux_arbitrage(
        {"binance": 100.0, "bybit": 101.0, "okx": 102.0, "bitget": 103.0}))
    # Act
    fv = fair_price.fair_value("BTCUSDT")
    # Assert : Bitget est EXCLU de la référence (repère indépendant)
    assert fv["fair"] == pytest.approx(101.0)
    assert fv["n"] == 3
    assert fv["bitget"] == pytest.approx(103.0)
    assert fv["premium_pct"] == pytest.approx(1.9802, abs=1e-4)


def test_fair_value_source_en_echec_ignoree(monkeypatch):
    # Un exchange qui renvoie None (fetch raté) disparaît des sources et de la référence
    monkeypatch.setitem(sys.modules, "arbitrage", _faux_arbitrage(
        {"binance": 100.0, "bybit": None, "okx": 102.0, "bitget": 101.0}))
    fv = fair_price.fair_value("BTCUSDT")
    assert fv["n"] == 2
    assert "bybit" not in fv["sources"]
    assert fv["fair"] == pytest.approx(101.0)


def test_fair_value_import_casse_best_effort_sans_lever(monkeypatch):
    # sys.modules["arbitrage"] = None -> import impossible : tout None, jamais d'exception
    monkeypatch.setitem(sys.modules, "arbitrage", None)
    fv = fair_price.fair_value("BTCUSDT")
    assert fv == {"fair": None, "n": 0, "sources": {}, "bitget": None,
                  "premium_pct": None}


def test_build_report_tag_premium_et_verdict_safe(monkeypatch):
    # Bitget 5 % au-dessus du marché -> étiquette PREMIUM ; le rapport reste SAFE
    monkeypatch.setitem(sys.modules, "arbitrage", _faux_arbitrage(
        {"binance": 100.0, "bybit": 100.0, "okx": 100.0, "bitget": 105.0}))
    rapport = fair_price.build_report("BTCUSDT")
    assert "PREMIUM (cher)" in rapport
    assert "VERDICT: SAFE" in rapport
