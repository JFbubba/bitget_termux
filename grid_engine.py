"""
grid_engine.py — moteur de grille PUR généralisé (mode × surface × funding).
Classement : SAFE. Aucun I/O, aucun réseau, aucun ordre. Généralise
grid_lab.simulate (long-only) aux jambes SHORT (marge/futures) et au FUNDING
(perp), avec comptabilité TOTAL = grid + latent + funding − frais − borrow.
Réutilise les helpers PURS de grid_lab (grid_lines, _prepare, _regime_ok, _cut,
regle_dor). Cf. docs/superpowers/specs/2026-07-24-grid-engine-multi-surface-design.md.
"""
import grid_lab as gl

# Frais autoritatifs (docs/BITGET_REFERENCE.md §1). slip futures=4 modélise le
# repli taker ~6 bps du post-only sur seed/coupe (cf. grid_futures_measure.py).
SURFACE = {
    "spot":    {"maker_bps": 8, "slip_bps": 2, "short": False, "funding": False,
                "lev_max": 1, "cap_op": 200, "cap_day": 500},
    "margin":  {"maker_bps": 8, "slip_bps": 2, "short": True,  "funding": False,
                "lev_max": 1, "cap_op": 200, "cap_day": 500},
    "futures": {"maker_bps": 2, "slip_bps": 4, "short": True,  "funding": True,
                "lev_max": 5, "cap_op": 50,  "cap_day": 250},
}
MODES = ("long_only", "bidirectional", "neutral")


def gconfig(mode="neutral", surface="futures", funding_lean=0.0,
            borrow_bps_per_day=0.0, **grid_lab_kw):
    """Config généralisée : grid_lab.config + {mode, surface, funding_lean, borrow}.
    Les frais/slip viennent de la SURFACE (écrasent tout fee_bps/slip_bps passé). PUR."""
    if mode not in MODES:
        raise ValueError(f"mode invalide: {mode!r} (attendu {MODES})")
    if surface not in SURFACE:
        raise ValueError(f"surface invalide: {surface!r} (attendu {tuple(SURFACE)})")
    s = SURFACE[surface]
    grid_lab_kw["fee_bps"] = s["maker_bps"]
    grid_lab_kw["slip_bps"] = s["slip_bps"]
    cfg = gl.config(**grid_lab_kw)
    cfg.update({"mode": mode, "surface": surface,
                "funding_lean": float(funding_lean),
                "borrow_bps_per_day": float(borrow_bps_per_day)})
    return cfg
