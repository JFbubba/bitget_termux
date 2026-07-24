"""
grid_trader.py — adaptateur d'EXÉCUTION de la grille (surface bornée §67).
Classement : surface §67 (audité à part par security_agent/safe_push_check).
NE PLACE AUCUN ORDRE lui-même : DÉLÈGUE à spot_trader/margin_trader/futures_executor
(modèle market_maker.py §94). Défaut OFF (GRID_TRADE_LIVE=0) -> DRY. Kill-switch
fail-closed. Caps §67 SOUS les murs. Retrait impossible (clé Trade-only).
Ne déploie qu'une config `survives=True` du labo (ou override proprio journalisé §92).

Task 7 (cette version) : couche de SÛRETÉ seule — `_delegate` NE CÂBLE AUCUN
exécuteur (aucun import spot_trader/margin_trader/futures_executor ici). Les
4 tests court-circuitent tous AVANT `_delegate` (DRY/refus/kill/verrou OFF).
Le câblage réel aux exécuteurs audités + la classification §67 arrivent en
Task 8.
"""
from pathlib import Path

import grid_engine as ge

KILL_PATH = Path(__file__).resolve().parent / "KILL_SWITCH"


def live_enabled():
    """Verrou LIVE (défaut OFF). .env OU config (PIÈGE verrous : les deux)."""
    try:
        import config_utils as cu
        return bool(cu.env_flag("GRID_TRADE_LIVE", False))
    except Exception:
        return False


def kill_active():
    """Kill-switch fail-closed : présence du fichier => bloqué. En cas de doute, True."""
    try:
        return KILL_PATH.exists()
    except Exception:
        return True


def _intentions(cell):
    """Traduit une cellule mesurée en intentions d'ordre BORNÉES (pas d'exécution).
    Bornées par cap_op de la surface. Retourne une liste de dicts descriptifs."""
    surf = ge.SURFACE[cell["surface"]]
    cap = surf["cap_op"]
    # intention minimale bornée : une jambe au notional plafonné (le détail des
    # barreaux est calculé par le moteur ; ici on borne l'engagement par cycle).
    return [{"symbol": cell["symbol"], "surface": cell["surface"], "mode": cell["mode"],
             "notional_max": cap, "post_only": True}]


def plan_cycle(cell, dry=None):
    """Un cycle borné. dry=None -> True sauf si live_enabled(). Fail-safe.
    Ordre des gardes : survives -> kill-switch -> verrou LIVE -> délégation."""
    res = {"dry": True, "refused": False, "killed": False, "delegated": 0, "intentions": []}
    if not cell.get("survives"):
        res["refused"] = True
        return res
    res["intentions"] = _intentions(cell)
    if kill_active():
        res["killed"] = True
        return res
    want_live = (dry is False) and live_enabled()
    if not want_live:
        res["dry"] = True
        return res                                  # DRY : journalise, ne délègue RIEN
    res["dry"] = False
    # --- LIVE : délégation aux exécuteurs audités (jamais d'ordre direct) ---
    for it in res["intentions"]:
        try:
            _delegate(it)                            # appelle spot_trader/margin_trader/futures_executor
            res["delegated"] += 1
        except Exception:
            pass                                     # fail-safe : une délégation ratée n'arrête pas le cycle
    return res


def _delegate(intention):
    """Route l'intention vers l'exécuteur audité de la surface. NON CÂBLÉ en Task 7
    (aucun import d'exécuteur — voir docstring de module). Câblage réel : Task 8."""
    surface = intention["surface"]
    if surface == "spot":
        raise NotImplementedError(f"câblage {surface} — Task 8")
    elif surface == "margin":
        raise NotImplementedError(f"câblage {surface} — Task 8")
    elif surface == "futures":
        raise NotImplementedError(f"câblage {surface} — Task 8")
    raise ValueError(f"surface inconnue: {surface}")
