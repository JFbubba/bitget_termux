"""
equity_curve.py — courbe d'equity REALISEE (paper) + etat de drawdown.

Classement : SAFE. Lecture seule, aucun ordre, aucun reseau.

Pourquoi : mandate.drawdown_halt() (halte MDD) etait code mais n'etait JAMAIS appele,
faute de courbe d'equity a lui donner (audit). Ce module construit cette courbe a partir
des positions paper CLOSES (paper_positions.json) :
    CLOSED_TP  -> +risk_usdt * RR      (gain realise)
    CLOSED_SL  -> -risk_usdt           (perte realisee)
    CLOSED_SOURCE / OPEN / AMBIGU      -> ignorees (PnL non realisee/neutre)
PnL REALISEE uniquement : conservateur, deterministe, testable (PUR si payload injecte).
"""


def _cfg(name, default):
    try:
        import config
        return getattr(config, name, default)
    except Exception:
        return default


def realized_curve(payload=None, start_equity=None, rr=None):
    """Courbe d'equity realisee (liste, du depart au present), positions closes triees
    par date de cloture. PUR si payload injecte."""
    rr = float(_cfg("RISK_REWARD_RATIO", 2.0) if rr is None else rr)
    start = float(_cfg("DEFAULT_PAPER_EQUITY_USDT", 100.0) if start_equity is None else start_equity)
    if payload is None:
        try:
            import paper_positions
            payload = paper_positions.load_paper_positions()
        except Exception:
            payload = {"positions": []}
    closed = [p for p in payload.get("positions", [])
              if p.get("status") in ("CLOSED_SL", "CLOSED_TP")]
    closed.sort(key=lambda p: str(p.get("closed_at", "")))
    eq = start
    curve = [round(eq, 4)]
    for p in closed:
        risk = abs(float(p.get("risk_usdt") or p.get("risk_usd") or 0) or 0)
        eq += (risk * rr) if p.get("status") == "CLOSED_TP" else (-risk)
        curve.append(round(eq, 4))
    return curve


def drawdown_state(payload=None, start_equity=None, rr=None, max_dd_pct=None):
    """Etat de drawdown realise : (halt, dd_pct, equity, peak, n_closed). Halte si le
    drawdown depuis le plus-haut depasse le MDD tolere (mandate). Best-effort."""
    curve = realized_curve(payload, start_equity, rr)
    try:
        import mandate
        halt, dd_pct = mandate.drawdown_halt(curve, max_dd_pct=max_dd_pct)
    except Exception:
        halt, dd_pct = False, 0.0
    return {"halt": bool(halt), "dd_pct": dd_pct, "equity": curve[-1],
            "peak": round(max(curve), 4), "n_closed": len(curve) - 1}


def main():
    import json
    print("=== EQUITY CURVE (paper, PnL realisee) ===")
    print(json.dumps(drawdown_state(), indent=2))
    print("Lecture seule. Aucun ordre. VERDICT: SAFE")


if __name__ == "__main__":
    main()
