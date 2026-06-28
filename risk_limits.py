"""
risk_limits.py — garde-fous de risque AGRÉGÉS au niveau portefeuille.

Classement : REVIEW_REQUIRED (modifie la logique d'acceptation des pré-ordres,
mais n'envoie toujours AUCUN ordre — purement local / paper).

Problème adressé :
  L'ancien preorder_engine ne vérifiait le risque qu'ordre PAR ordre
  (1% chacun, levier <= 2x). Il manquait :
    - un plafond du NOMBRE de positions simultanées,
    - un plafond du NOTIONNEL total,
    - un plafond du RISQUE total (somme des 1%),
    - un plancher de distance de stop (les actifs très peu volatils comme
      XAUTUSDT produisaient des tailles énormes -> levier 16x, rejeté ensuite,
      mais autant le bloquer en amont proprement).

Intégration (voir AUDIT_BITGET.md) : appeler evaluate_portfolio_caps() dans
preorder_engine.main() après construction des pré-ordres.
"""

# Plafonds — SOURCE UNIQUE : config (réconciliation audit #4), repli si config absent.
from config_utils import cfg as _cfg


MAX_CONCURRENT_POSITIONS = int(_cfg("MAX_OPEN_POSITIONS", 3))   # = gate par-ordre (cohérent)
MAX_TOTAL_NOTIONAL_USDT = float(_cfg("MAX_TOTAL_NOTIONAL_USDT", 300.0))
MAX_TOTAL_RISK_PERCENT = float(_cfg("MAX_TOTAL_RISK_PERCENT", 5.0))
MIN_SL_DISTANCE_PERCENT = float(_cfg("MIN_SL_DISTANCE_PERCENT", 0.20))
MAX_PREORDERS_PER_CYCLE = 5


def evaluate_portfolio_caps(preorders, open_positions_count, risk_per_trade_percent):
    """
    Renvoie un dict {order_id: [raisons supplémentaires]} pour les pré-ordres
    qui font dépasser un plafond agrégé. N'exécute rien.

    `preorders` : liste de dicts pré-ordres (déjà construits par preorder_engine).
    `open_positions_count` : nb de positions déjà ouvertes (open_outcomes_state).
    """
    extra = {}

    # On ne considère que les pré-ordres encore acceptables individuellement.
    candidates = [o for o in preorders if o.get("status") == "PENDING_APPROVAL"]

    running_notional = 0.0
    running_risk = 0.0
    running_count = open_positions_count

    for order in candidates:
        oid = order.get("id")
        reasons = []

        notional = order.get("notional_usdt") or 0.0
        risk_pct = risk_per_trade_percent
        sl_dist = order.get("sl_distance_percent")

        if sl_dist is not None and sl_dist < MIN_SL_DISTANCE_PERCENT:
            reasons.append(
                f"distance stop {sl_dist:.3f}% < plancher {MIN_SL_DISTANCE_PERCENT:.2f}%"
            )

        if running_count + 1 > MAX_CONCURRENT_POSITIONS:
            reasons.append(
                f"plafond positions atteint ({MAX_CONCURRENT_POSITIONS})"
            )

        if running_notional + notional > MAX_TOTAL_NOTIONAL_USDT:
            reasons.append(
                f"notionnel cumulé {running_notional + notional:.1f} "
                f"> max {MAX_TOTAL_NOTIONAL_USDT:.0f} USDT"
            )

        if running_risk + risk_pct > MAX_TOTAL_RISK_PERCENT:
            reasons.append(
                f"risque cumulé {running_risk + risk_pct:.1f}% "
                f"> max {MAX_TOTAL_RISK_PERCENT:.1f}%"
            )

        if reasons:
            extra[oid] = reasons
        else:
            # accepté -> il consomme du budget agrégé
            running_notional += notional
            running_risk += risk_pct
            running_count += 1

    return extra
