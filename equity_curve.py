"""
equity_curve.py — courbe d'equity REALISEE + etat de drawdown (halte MDD).

Classement : SAFE. Lecture seule, aucun ordre, aucun reseau.

Source AUTONOME du PnL realise = final_outcomes_journal.csv (outcomes de SIGNAUX
finalises TP/SL) : la SEULE piste qui circule sans approbation manuelle (les positions
paper exigent execution_gateway + approbation, hors cycle -> paper_positions reste vide).
On en derive une courbe d'equity fixed-fractional (chaque signal risque
RISK_PER_TRADE_PERCENT de l'equity) :
    TP -> +RR_signal R   (RR = reward/risk du signal)
    SL -> -1 R
    AMBIGU / autre -> 0
mandate.drawdown_halt() (code mais sans courbe a manger) lit cette courbe -> la halte
MDD devient EFFECTIVE en autonome.

`realized_curve()` (positions paper closes) est conservee pour la piste positions.
"""
import csv
from pathlib import Path

FINAL_OUTCOMES_FILE = Path("final_outcomes_journal.csv")


def _cfg(name, default):
    try:
        import config
        return getattr(config, name, default)
    except Exception:
        return default


def _read_outcomes(path=None):
    p = Path(path) if path else FINAL_OUTCOMES_FILE
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _r_multiple(row):
    """R realise d'un outcome de signal : TP -> +reward/risk, SL -> -1, sinon 0. PUR."""
    out = str(row.get("outcome", "")).upper()
    try:
        entry = float(row.get("entry"))
        sl = float(row.get("stop_loss"))
        tp = float(row.get("take_profit"))
    except (TypeError, ValueError):
        entry = sl = tp = None
    if "TP" in out:
        if entry is None or sl is None or tp is None:
            return float(_cfg("RISK_REWARD_RATIO", 2.0))
        risk = abs(entry - sl)
        return round(abs(tp - entry) / risk, 4) if risk > 0 else 0.0
    if "SL" in out:
        return -1.0
    return 0.0


def outcomes_curve(rows=None, start_equity=None, risk_frac=None):
    """Courbe d'equity (fixed-fractional) depuis les outcomes de SIGNAUX, triee par date.
    PUR si rows injecte. risk_frac = fraction d'equity risquee par signal."""
    rows = _read_outcomes() if rows is None else rows
    start = float(_cfg("DEFAULT_PAPER_EQUITY_USDT", 100.0) if start_equity is None else start_equity)
    rf = float((_cfg("RISK_PER_TRADE_PERCENT", 1.0) / 100.0) if risk_frac is None else risk_frac)
    rows = sorted(rows, key=lambda r: str(r.get("updated_at") or r.get("signal_timestamp") or ""))
    eq = start
    curve = [round(eq, 6)]
    for r in rows:
        eq *= (1.0 + _r_multiple(r) * rf)
        curve.append(round(eq, 6))
    return curve


def realized_curve(payload=None, start_equity=None, rr=None):
    """Courbe d'equity depuis les positions paper CLOSES (piste positions). PUR si payload
    injecte. CLOSED_TP -> +risk*RR, CLOSED_SL -> -risk."""
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


def drawdown_state(rows=None, start_equity=None, risk_frac=None, max_dd_pct=None):
    """Etat de drawdown realise depuis les outcomes de SIGNAUX (piste autonome) :
    (halt, dd_pct, equity, peak, n). Halte si DD >= MDD tolere (mandate). Best-effort."""
    curve = outcomes_curve(rows, start_equity, risk_frac)
    try:
        import mandate
        halt, dd_pct = mandate.drawdown_halt(curve, max_dd_pct=max_dd_pct)
    except Exception:
        halt, dd_pct = False, 0.0
    return {"halt": bool(halt), "dd_pct": dd_pct, "equity": round(curve[-1], 4),
            "peak": round(max(curve), 4), "n": len(curve) - 1}


def main():
    import json
    print("=== EQUITY CURVE (paper, PnL realisee sur outcomes de signaux) ===")
    print(json.dumps(drawdown_state(), indent=2))
    print("Lecture seule. Aucun ordre. VERDICT: SAFE")


if __name__ == "__main__":
    main()
