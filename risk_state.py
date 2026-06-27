"""
risk_state.py — état de risque LIVE (positions ouvertes + perte réalisée du jour)
pour alimenter risk_manager.check_trade. Classement : SAFE. Lecture seule, aucun ordre.

Pourquoi : risk_manager.check_trade a besoin de `open_positions` et `daily_loss_usd`,
qui n'étaient alimentés par AUCUNE source (cap journalier inopérant — cf. audit). Ce
module les calcule depuis l'état PAPER (paper_positions.json), de façon best-effort.

Conservateur : la perte du jour = somme des risques des positions soldées en STOP
aujourd'hui (CLOSED_SL) — chaque SL ≈ le montant risqué (1 %). Proxy prudent et
déterministe. Fonctions PURES quand on injecte le payload (testables).
"""

from datetime import date


def open_positions_count(payload=None):
    """Nombre de positions paper OUVERTES. Best-effort (0 si illisible)."""
    payload = _payload(payload)
    return sum(1 for p in payload.get("positions", []) if p.get("status") == "OPEN")


def daily_realized_loss_usd(payload=None, today=None):
    """Perte RÉALISÉE du jour (USD, positive) = somme des risques des positions
    soldées en stop aujourd'hui (CLOSED_SL). PUR si payload injecté. Best-effort."""
    payload = _payload(payload)
    today = today or date.today().isoformat()
    loss = 0.0
    for p in payload.get("positions", []):
        if p.get("status") == "CLOSED_SL" and str(p.get("closed_at", ""))[:10] == today:
            loss += abs(float(p.get("risk_usdt") or p.get("risk_usd") or 0) or 0)
    return round(loss, 4)


def snapshot(payload=None, today=None):
    """État de risque consolidé pour check_trade. Best-effort."""
    payload = _payload(payload)
    return {"open_positions": open_positions_count(payload),
            "daily_loss_usd": daily_realized_loss_usd(payload, today)}


def _payload(payload):
    if payload is not None:
        return payload
    try:
        import paper_positions
        return paper_positions.load_paper_positions()
    except Exception:
        return {"positions": []}


def main():
    import json
    print("=== RISK STATE (paper) ===")
    print(json.dumps(snapshot(), indent=2))
    print("Lecture seule. Aucun ordre. VERDICT: SAFE")


if __name__ == "__main__":
    main()
