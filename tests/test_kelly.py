"""Suite pytest de kelly.py — banc unitaire du calculateur de mise §111 (SAFE, PUR).

Patterns exercés : AAA, nommage test_<unité>_<scénario>_<attendu>, parametrize,
fixtures, monkeypatch d'environnement, pytest.approx, tests de propriétés
(monotonie, bornes). Toutes les fonctions testées sont PURES avec paramètres
injectés — aucun réseau, aucun fichier écrit.
"""
import math

import pytest

import kelly


# ---------------------------------------------------------------------------
# kelly_fraction — forme binaire f = W − (1−W)/R, fractionnaire, bornée
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "W, R, f_full_attendu",
    [
        (0.6, 2.0, 0.4),      # cas nominal : edge positif
        (0.5, 1.0, 0.0),      # break-even exact
        (0.3, 1.0, -0.4),     # edge négatif
        (0.55, 1.5, 0.25),    # cotes asymétriques
    ],
)
def test_kelly_fraction_formule_binaire(W, R, f_full_attendu):
    # Arrange : paramètres INJECTÉS (indépendance vis-à-vis du .env)
    # Act
    k = kelly.kelly_fraction(W, R, fraction=0.5, cap=0.25)
    # Assert
    assert k["f_full"] == pytest.approx(f_full_attendu, abs=1e-4)
    f_attendu = min(max(0.0, f_full_attendu) * 0.5, 0.25)
    assert k["f"] == pytest.approx(f_attendu, abs=1e-4)


def test_kelly_fraction_edge_negatif_renvoie_mise_zero():
    k = kelly.kelly_fraction(0.3, 1.0, fraction=0.5, cap=0.25)
    assert k["f"] == 0.0
    assert k["edge_positive"] is False
    assert "edge négatif" in k["note"]


def test_kelly_fraction_payoff_non_positif_renvoie_mise_zero():
    k = kelly.kelly_fraction(0.6, 0.0, fraction=0.5, cap=0.25)
    assert k["f"] == 0.0
    assert k["edge_positive"] is False


def test_kelly_fraction_entrees_illisibles_renvoie_mise_zero():
    k = kelly.kelly_fraction(None, "n/a", fraction=0.5, cap=0.25)
    assert k["f"] == 0.0
    assert k["edge_positive"] is None  # indécidable, pas « faux »


def test_kelly_fraction_plafond_dur_ecrete_meme_le_full_kelly():
    # W=0.9, R=5 -> f_full=0.88 ; en full-Kelly (fraction=1) le plafond doit mordre
    k = kelly.kelly_fraction(0.9, 5.0, fraction=1.0, cap=0.25)
    assert k["f_full"] == pytest.approx(0.88, abs=1e-4)
    assert k["f"] == 0.25


def test_kelly_fraction_knob_env_prioritaire(env_kelly):
    # Arrange : l'env pilote fraction/cap quand rien n'est injecté
    env_kelly(fraction="0.25", max_fraction="0.25")
    # Act
    k = kelly.kelly_fraction(0.6, 2.0)
    # Assert : f = 0.4 × 0.25 = 0.1
    assert k["f"] == pytest.approx(0.1, abs=1e-4)
    assert k["fraction"] == 0.25


def test_kelly_fraction_env_illisible_replie_sur_defaut(env_kelly):
    # Un knob env corrompu ne doit pas crasher : repli cfg/défaut (0.5)
    env_kelly(fraction="pas-un-nombre", max_fraction="0.25")
    k = kelly.kelly_fraction(0.6, 2.0)
    assert k["fraction"] == 0.5
    assert k["f"] == pytest.approx(0.2, abs=1e-4)


# ---------------------------------------------------------------------------
# kelly_general — forme de Thorp f* = p/a − (1−p)/b ; a=1 ≡ forme binaire
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("p, b", [(0.6, 2.0), (0.55, 1.5), (0.3, 1.0)])
def test_kelly_general_a_egal_1_equivaut_forme_binaire(p, b):
    g = kelly.kelly_general(p, b, a=1.0)
    k = kelly.kelly_fraction(p, b, fraction=1.0, cap=1.0)
    assert g["f_full"] == pytest.approx(k["f_full"], abs=1e-4)


@pytest.mark.parametrize(
    "p, b, a",
    [
        (1.5, 2.0, 1.0),   # p hors [0,1]
        (0.6, 0.0, 1.0),   # b ≤ 0
        (0.6, 2.0, 0.0),   # a ≤ 0
        ("x", 2.0, 1.0),   # illisible
    ],
)
def test_kelly_general_entrees_invalides_renvoie_none(p, b, a):
    assert kelly.kelly_general(p, b, a)["f_full"] is None


# ---------------------------------------------------------------------------
# kelly_bayes — prior Beta centré break-even : pas de pari sans preuve
# ---------------------------------------------------------------------------

def test_kelly_bayes_sans_donnees_mise_zero():
    # n=0 -> posterior = break-even exactement -> f0 = 0
    kb = kelly.kelly_bayes(0, 0, R=2.0, prior_strength=100)
    assert kb["f0"] == 0.0
    assert kb["p_post"] == pytest.approx(kb["p0"], abs=1e-4)


def test_kelly_bayes_posterior_sous_break_even_mise_zero():
    kb = kelly.kelly_bayes(40, 60, R=1.0, prior_strength=100)
    assert kb["f0"] == 0.0
    assert "break-even" in kb["note"]


def test_kelly_bayes_posterior_au_dessus_du_break_even():
    # p0=0.5 ; p_post=(60+50)/200=0.55 ; f0 = 0.55 − 0.45/1 = 0.10
    kb = kelly.kelly_bayes(60, 40, R=1.0, prior_strength=100)
    assert kb["p_post"] == pytest.approx(0.55, abs=1e-4)
    assert kb["f0"] == pytest.approx(0.10, abs=1e-4)


def test_kelly_bayes_monotone_en_wins():
    # Propriété : à n de pertes fixe, plus de gains ne réduit jamais la mise
    f_prec = -1.0
    for wins in range(0, 200, 20):
        f0 = kelly.kelly_bayes(wins, 50, R=1.5, prior_strength=100)["f0"]
        assert f0 >= f_prec
        f_prec = f0


def test_kelly_bayes_prior_plus_fort_ecrase_la_mise():
    # Même échantillon : k=10 (prior faible) doit miser plus que k=1000 (sceptique)
    faible = kelly.kelly_bayes(60, 40, R=1.0, prior_strength=10)["f0"]
    fort = kelly.kelly_bayes(60, 40, R=1.0, prior_strength=1000)["f0"]
    assert faible > fort > 0.0


@pytest.mark.parametrize(
    "wins, losses, R, k",
    [
        (10, 10, 0.0, 100),    # R ≤ 0
        (-1, 10, 1.5, 100),    # compte négatif
        (10, 10, 1.5, 0),      # prior invalide
        ("x", 10, 1.5, 100),   # illisible
    ],
)
def test_kelly_bayes_entrees_invalides_mise_zero(wins, losses, R, k):
    assert kelly.kelly_bayes(wins, losses, R, prior_strength=k)["f0"] == 0.0


# ---------------------------------------------------------------------------
# dd_fraction — fraction c dérivée du mandat MDD (Thorp eq. 7.13)
# ---------------------------------------------------------------------------

def test_dd_fraction_mandat_mdd20_conf10_donne_environ_018():
    # Valeur documentée §111 : c ≈ 0.18 ; recalcul indépendant de la formule
    c = kelly.dd_fraction(mdd=0.20, conf=0.10)
    attendu = 2.0 / (1.0 + math.log(0.10) / math.log(0.80))
    assert c == pytest.approx(attendu, abs=1e-6)
    assert c == pytest.approx(0.18, abs=0.01)


def test_dd_fraction_confiance_lache_pas_de_resserrage():
    # Tolérance si lâche que le full Kelly passe : c écrêté à 1
    assert kelly.dd_fraction(mdd=0.5, conf=0.9) == 1.0


@pytest.mark.parametrize("mdd, conf", [(0.0, 0.1), (1.0, 0.1), (0.2, 0.0), (0.2, 1.0)])
def test_dd_fraction_parametres_invalides_neutre(mdd, conf):
    assert kelly.dd_fraction(mdd=mdd, conf=conf) == 1.0


def test_dd_fraction_toujours_dans_l_intervalle_0_1():
    # Propriété de borne sur une grille de mandats/confiances valides
    for mdd in (0.05, 0.1, 0.2, 0.5, 0.9):
        for conf in (0.01, 0.1, 0.5, 0.99):
            c = kelly.dd_fraction(mdd=mdd, conf=conf)
            assert 0.0 < c <= 1.0


# ---------------------------------------------------------------------------
# kelly_empirical — argmax_f Σ log(1+f·r) sur distribution réelle
# ---------------------------------------------------------------------------

def test_kelly_empirical_sans_donnees_mise_zero():
    assert kelly.kelly_empirical([], cap=0.25) == 0.0
    assert kelly.kelly_empirical(None, cap=0.25) == 0.0
    assert kelly.kelly_empirical([float("nan"), "x"], cap=0.25) == 0.0


def test_kelly_empirical_distribution_perdante_mise_zero():
    assert kelly.kelly_empirical([-0.5, -0.2, -0.1], cap=0.25) == 0.0


def test_kelly_empirical_distribution_favorable_ecretee_au_cap():
    # [1.0, 1.0, −0.5] : l'optimum non contraint est f=1 -> le cap doit mordre
    assert kelly.kelly_empirical([1.0, 1.0, -0.5], cap=0.25) == pytest.approx(0.25)


def test_kelly_empirical_perte_totale_optimum_interieur():
    # [2.0, −1.0] : g(f)=log((1+2f)(1−f)), optimum analytique f*=0.25 ;
    # la borne de ruine (f < 1/|min r|) doit être respectée
    f = kelly.kelly_empirical([2.0, -1.0], cap=1.0, grid=2000)
    assert f == pytest.approx(0.25, abs=0.01)
    assert f < 1.0


def test_kelly_empirical_respecte_toujours_le_cap():
    for cap in (0.05, 0.1, 0.25):
        assert kelly.kelly_empirical([0.5, 0.3, -0.1], cap=cap) <= cap + 1e-9


# ---------------------------------------------------------------------------
# recommended_usdt — chemin PUR (tout injecté) : reborné par le cap de surface
# ---------------------------------------------------------------------------

def test_recommended_usdt_reborne_par_le_cap_de_surface():
    # f = 0.2 sur capital 1000 -> 200 $ bruts, mais cap/opération 50 $
    montant, k = kelly.recommended_usdt(
        per_op_cap=50.0, W=0.6, R=2.0, capital=1000.0, fraction=0.5, cap=0.25)
    assert montant == 50.0
    assert k["f"] == pytest.approx(0.2, abs=1e-4)


def test_recommended_usdt_edge_negatif_montant_zero():
    montant, k = kelly.recommended_usdt(
        per_op_cap=50.0, W=0.3, R=1.0, capital=1000.0, fraction=0.5, cap=0.25)
    assert montant == 0.0
    assert k["edge_positive"] is False
