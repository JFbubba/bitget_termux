"""
volatility.py — estimateurs de volatilité conditionnelle (EWMA + GARCH(1,1)).

Classement : SAFE. Pur, aucun ordre. Idée reprise de la lib `arch` (modèles GARCH)
mais implémentée en quelques lignes -> aucune dépendance lourde. Sert le VOL-TARGETING
du levier (mandate) : une vol CONDITIONNELLE (réactive aux chocs récents) calibre mieux
la taille qu'un simple écart-type historique.
"""

import numpy as np


def _returns(closes):
    p = np.asarray([float(c) for c in closes if c and float(c) > 0], dtype=float)
    if len(p) < 3:
        return np.array([])
    return np.diff(np.log(p))


def ewma_vol(closes, lam=0.94):
    """Vol EWMA (RiskMetrics) par pas. PUR. None si trop court."""
    r = _returns(closes)
    if len(r) < 2:
        return None
    var = float(r[0] ** 2)
    for x in r[1:]:
        var = lam * var + (1.0 - lam) * float(x) ** 2
    return float(np.sqrt(var)) if var > 0 else None


def garch11_vol(closes, alpha=0.10, beta=0.85, omega=None):
    """Vol conditionnelle GARCH(1,1) au dernier pas. PUR. Variance-targeting si omega
    None (omega = (1−α−β)·variance d'échantillon). None si trop court / variance nulle."""
    r = _returns(closes)
    if len(r) < 5:
        return None
    sample_var = float(np.var(r))
    if sample_var <= 0:
        return None
    if omega is None:
        omega = max(1.0 - (alpha + beta), 1e-6) * sample_var
    var = sample_var
    for x in r:
        var = omega + alpha * float(x) ** 2 + beta * var
    return float(np.sqrt(max(var, 1e-12)))


def conditional_vol(closes):
    """Meilleure estimation dispo : GARCH(1,1) -> repli EWMA -> repli écart-type. PUR."""
    for fn in (garch11_vol, ewma_vol):
        v = fn(closes)
        if v is not None and v > 0:
            return v
    r = _returns(closes)
    return float(np.std(r)) if len(r) and np.std(r) > 0 else None


def build_report(closes):
    return ("=== VOLATILITÉ CONDITIONNELLE ===\n"
            f"GARCH(1,1) : {garch11_vol(closes)}\n"
            f"EWMA(0.94) : {ewma_vol(closes)}\n"
            f"retenue    : {conditional_vol(closes)}\n"
            "Pur, aucun ordre. VERDICT: SAFE")


if __name__ == "__main__":
    import math
    demo = [100 * math.exp(0.001 * i + 0.02 * math.sin(i)) for i in range(120)]
    print(build_report(demo))
