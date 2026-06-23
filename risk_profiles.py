"""
risk_profiles.py — profils d'agressivité & garde anti-martingale (intake Drive). Pur, SAFE.

Issu des docx « stratégie agressivité 3/5 & 5/5 » et « Martingale » de package/.
  • aggressiveness_profile(level) : un seul curseur 1..5 contraint sizing/RR/levier/
    fréquence (au lieu de tout régler à la main) ; >3 nécessite un override humain.
  • martingale_guard(...) : INTERDIT d'augmenter la taille après une perte sans
    nouveau signal indépendant. La martingale est bannie (edge négatif, ruine en
    présence de tail risk — et le marché en a). Cf. RESEARCH_NOTES §13.

Ces fonctions sont des garde-fous PURS et testables ; cible d'intégration :
`risk_manager`/`risk_limits`/`config_guard_agent` (pipeline d'ordres), pas le
cerveau en lecture seule.
"""

_GRID = {
    1: {"max_risk_pct": 0.5, "min_rr": 2.0, "max_leverage": 2,  "max_trades_day": 2},
    2: {"max_risk_pct": 1.0, "min_rr": 1.8, "max_leverage": 3,  "max_trades_day": 4},
    3: {"max_risk_pct": 2.0, "min_rr": 1.5, "max_leverage": 5,  "max_trades_day": 6},
    4: {"max_risk_pct": 3.0, "min_rr": 1.3, "max_leverage": 8,  "max_trades_day": 10},
    5: {"max_risk_pct": 5.0, "min_rr": 1.0, "max_leverage": 12, "max_trades_day": 20},
}


def aggressiveness_profile(level):
    """Profil d'agressivité 1..5 -> contraintes de risque. Pur.

    Plus le niveau est haut, plus c'est agressif. `acceptable=False` au-delà de 3 :
    le profil existe pour BORNER ce qu'on n'autorise pas sans override explicite."""
    level = max(1, min(5, int(level)))
    p = dict(_GRID[level])
    p["level"] = level
    p["acceptable"] = level <= 3
    return p


def martingale_guard(prev_was_loss, prev_size, new_size, new_independent_signal):
    """Refuse une escalade de taille après perte sans signal indépendant. Pur.

    Retourne (ok: bool, reason). Réduire la taille, ou l'augmenter avec un NOUVEAU
    signal indépendant, reste autorisé ; doubler « pour se refaire » est banni."""
    if prev_was_loss and new_size > prev_size and not new_independent_signal:
        return (False, "martingale interdite : taille en hausse après perte sans signal indépendant")
    return (True, "ok")
