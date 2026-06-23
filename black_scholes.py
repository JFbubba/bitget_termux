"""
black_scholes.py — Black-Scholes & probabilités lognormales (pur, testable).

Classement : SAFE (mathématiques pures, aucune I/O, aucun ordre).

On ne trade PAS d'options ici. Mais l'équation de Black-Scholes formalise LA
quantité qui compte vraiment — la volatilité σ — et fournit des outils
PROBABILISTES directement utiles à un bot directionnel crypto :
  • N(d2) = P(S_T > K) sous dynamique lognormale -> probabilité d'atteindre un
    niveau (ex. un aimant de liquidation) à horizon T ;
  • mouvement attendu ~ S·σ·√T -> enveloppe ±1σ (cône de volatilité) pour des
    bandes de range, stops et targets ;
  • greeks (delta/gamma/vega) pour la complétude et l'auditabilité.

Convention pratique : on passe σ et T dans les MÊMES unités (σ par bougie + T en
bougies, ou σ annualisé + T en années). r=0 par défaut = probabilité à drift nul,
honnête pour le court terme crypto.

Réfs : Black & Scholes (1973), Merton (1973).
EDP : ∂V/∂t + ½σ²S²·∂²V/∂S² + rS·∂V/∂S − rV = 0.
Forme fermée : C = S·N(d1) − K·e^{−rT}·N(d2),  d1 = [ln(S/K)+(r+σ²/2)T]/(σ√T),
d2 = d1 − σ√T.
"""

import math
import statistics


def _norm_cdf(x):
    """Fonction de répartition de la loi normale centrée réduite (via erf)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def d1_d2(S, K, sigma, T, r=0.0):
    """(d1, d2) de Black-Scholes. Lève ValueError sur entrées non valides. Pur."""
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        raise ValueError("black_scholes: S, K, sigma, T doivent être > 0")
    v = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / v
    return d1, d1 - v


def call_price(S, K, sigma, T, r=0.0):
    """Prix d'un call européen. Pur."""
    d1, d2 = d1_d2(S, K, sigma, T, r)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def put_price(S, K, sigma, T, r=0.0):
    """Prix d'un put européen. Pur."""
    d1, d2 = d1_d2(S, K, sigma, T, r)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def delta(S, K, sigma, T, r=0.0, kind="call"):
    """Delta (∂prix/∂S) = sensibilité directionnelle. Pur."""
    d1, _ = d1_d2(S, K, sigma, T, r)
    return _norm_cdf(d1) if kind == "call" else _norm_cdf(d1) - 1.0


def gamma(S, K, sigma, T, r=0.0):
    """Gamma (∂²prix/∂S²) = convexité. Pur."""
    d1, _ = d1_d2(S, K, sigma, T, r)
    return _norm_pdf(d1) / (S * sigma * math.sqrt(T))


def vega(S, K, sigma, T, r=0.0):
    """Vega (∂prix/∂σ) = sensibilité à la volatilité. Pur."""
    d1, _ = d1_d2(S, K, sigma, T, r)
    return S * _norm_pdf(d1) * math.sqrt(T)


def prob_above(S, K, sigma, T, r=0.0):
    """P(S_T > K) sous dynamique lognormale ( = N(d2) ). Pur."""
    _, d2 = d1_d2(S, K, sigma, T, r)
    return _norm_cdf(d2)


def prob_below(S, K, sigma, T, r=0.0):
    """P(S_T < K) = 1 − P(S_T > K). Pur."""
    return 1.0 - prob_above(S, K, sigma, T, r)


def prob_touch(S, K, sigma, T, r=0.0):
    """Approx. P(le prix ATTEINT K avant T) — principe de réflexion, drift nul.

    ≈ 2·P(terminal au-delà de K), bornée à 1. Bonne indication de la « force
    d'aimantation » vers un niveau (ex. cluster de liquidation). Pur."""
    p = prob_above(S, K, sigma, T, r) if K >= S else prob_below(S, K, sigma, T, r)
    return min(1.0, 2.0 * p)


def realized_vol(closes):
    """Volatilité réalisée PAR PÉRIODE = écart-type des log-rendements. Pur."""
    pts = [c for c in closes if c and c > 0]
    if len(pts) < 3:
        return 0.0
    rets = [math.log(pts[i] / pts[i - 1]) for i in range(1, len(pts))]
    return statistics.pstdev(rets) if len(rets) >= 2 else 0.0


def expected_move(S, sigma, T):
    """Amplitude ~1σ du mouvement (approx. lognormale S·σ·√T). Pur.

    σ et T dans les mêmes unités (σ par bougie -> T en bougies)."""
    if S <= 0 or sigma < 0 or T < 0:
        raise ValueError("black_scholes.expected_move: entrées non valides")
    return S * sigma * math.sqrt(T)
