"""Suite pytest de risk_limits.py — plafonds AGRÉGÉS portefeuille (paper, aucun ordre).

Les plafonds du module sont lus dans config À L'IMPORT : la fixture `caps_fixes`
les épingle par monkeypatch.setattr (valeurs connues, restaurées après chaque
test) — les tests ne dépendent jamais du config.py de la machine.
"""
import pytest

import risk_limits


@pytest.fixture
def caps_fixes(monkeypatch):
    """Plafonds déterministes : 3 positions, 300 USDT, 5 % de risque, SL ≥ 0.20 %."""
    monkeypatch.setattr(risk_limits, "MAX_CONCURRENT_POSITIONS", 3)
    monkeypatch.setattr(risk_limits, "MAX_TOTAL_NOTIONAL_USDT", 300.0)
    monkeypatch.setattr(risk_limits, "MAX_TOTAL_RISK_PERCENT", 5.0)
    monkeypatch.setattr(risk_limits, "MIN_SL_DISTANCE_PERCENT", 0.20)


def _preordre(oid, notional=50.0, sl_dist=1.0, status="PENDING_APPROVAL"):
    """Fabrique de pré-ordre minimal (pattern factory du skill)."""
    return {"id": oid, "notional_usdt": notional,
            "sl_distance_percent": sl_dist, "status": status}


def test_caps_liste_vide_renvoie_dict_vide(caps_fixes):
    assert risk_limits.evaluate_portfolio_caps([], 0, 1.0) == {}


def test_caps_statut_non_pending_ignore(caps_fixes):
    # Un pré-ordre déjà rejeté/exécuté n'est ni évalué ni compté dans le budget
    ordres = [_preordre("a", status="REJECTED"), _preordre("b", status="DONE")]
    assert risk_limits.evaluate_portfolio_caps(ordres, 0, 1.0) == {}


def test_caps_ordre_valide_accepte_sans_raison(caps_fixes):
    extra = risk_limits.evaluate_portfolio_caps([_preordre("a")], 0, 1.0)
    assert extra == {}


def test_caps_plafond_positions_bloque_au_dela(caps_fixes):
    # 3 positions déjà ouvertes = plafond atteint -> tout candidat est bloqué
    extra = risk_limits.evaluate_portfolio_caps([_preordre("a")], 3, 1.0)
    assert "a" in extra
    assert any("plafond positions" in r for r in extra["a"])


def test_caps_plafond_notionnel_cumule(caps_fixes):
    # 200 + 200 > 300 : le premier passe, le deuxième dépasse le cumul
    ordres = [_preordre("a", notional=200.0), _preordre("b", notional=200.0)]
    extra = risk_limits.evaluate_portfolio_caps(ordres, 0, 1.0)
    assert "a" not in extra
    assert any("notionnel cumulé" in r for r in extra["b"])


def test_caps_plafond_risque_cumule(caps_fixes):
    # 2 % par trade, max 5 % : deux passent (4 %), le troisième dépasse (6 %)
    ordres = [_preordre(o) for o in ("a", "b", "c")]
    extra = risk_limits.evaluate_portfolio_caps(ordres, 0, 2.0)
    assert "a" not in extra and "b" not in extra
    assert any("risque cumulé" in r for r in extra["c"])


def test_caps_plancher_distance_stop(caps_fixes):
    # SL trop serré (taille énorme -> levier excessif en aval) : bloqué en amont
    extra = risk_limits.evaluate_portfolio_caps(
        [_preordre("a", sl_dist=0.10)], 0, 1.0)
    assert any("distance stop" in r for r in extra["a"])


def test_caps_sl_inconnu_ne_declenche_pas_le_plancher(caps_fixes):
    # sl_distance_percent absent -> le plancher SL ne s'applique pas (les autres caps si)
    extra = risk_limits.evaluate_portfolio_caps(
        [_preordre("a", sl_dist=None)], 0, 1.0)
    assert extra == {}


def test_caps_ordre_rejete_ne_consomme_pas_le_budget(caps_fixes):
    # COMPORTEMENT CLÉ : « a » (SL trop serré) est rejeté et ne doit consommer ni
    # notionnel ni risque ni slot -> « b », identique mais valide, passe
    ordres = [_preordre("a", notional=250.0, sl_dist=0.05),
              _preordre("b", notional=250.0)]
    extra = risk_limits.evaluate_portfolio_caps(ordres, 0, 1.0)
    assert "a" in extra
    assert "b" not in extra


def test_caps_raisons_multiples_cumulees_sur_un_ordre(caps_fixes):
    # SL trop serré + plafond positions + notionnel : toutes les raisons remontent
    extra = risk_limits.evaluate_portfolio_caps(
        [_preordre("a", notional=500.0, sl_dist=0.05)], 3, 1.0)
    assert len(extra["a"]) == 3


def test_caps_notionnel_absent_traite_comme_zero(caps_fixes):
    # notional_usdt None -> 0.0 : pas de crash, pas de consommation de notionnel
    ordres = [_preordre("a", notional=None), _preordre("b", notional=300.0)]
    extra = risk_limits.evaluate_portfolio_caps(ordres, 0, 1.0)
    assert extra == {}
