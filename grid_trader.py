"""
grid_trader.py — adaptateur d'EXÉCUTION de la grille (surface bornée §67).
Classement : surface §67 (audité à part par security_agent/safe_push_check).
NE PLACE AUCUN ORDRE lui-même : DÉLÈGUE à spot_trader/margin_trader/futures_executor
(modèle market_maker.py §94). Défaut OFF (GRID_TRADE_LIVE=0) -> DRY. Kill-switch
fail-closed. Caps §67 SOUS les murs. Retrait impossible (clé Trade-only).
Ne déploie qu'une config `survives=True` du labo (ou override proprio journalisé §92).

CÂBLAGE DIFFÉRÉ (décision proprio 24/07) : la mesure exhaustive (docs/GRID_STRATEGIES.md
§6, grid_engine_lab) trouve 0/120 cellule survivante — aucun edge sur les 3 surfaces,
même avec short/neutre/funding. `_delegate` reste donc NON CÂBLÉ (aucun import
d'exécuteur, aucun chemin d'ordre réel) : ce module est le SQUELETTE de sûreté PRÊT
(défaut OFF/DRY, gardes prouvées) à câbler SEULEMENT si une config franchit un jour la
porte (rabais VIP profond, actif structurellement range-bound). Les 4 tests
court-circuitent tous AVANT `_delegate`.
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
    """Un cycle borné. Fail-safe. Ordre des gardes : survives -> surface valide ->
    kill-switch -> verrou LIVE -> délégation.
    SÉMANTIQUE DRY (money-path — NE PAS desserrer) : le LIVE exige un `dry=False`
    EXPLICITE **ET** `live_enabled()`. `dry=None` (défaut) est INCONDITIONNELLEMENT
    DRY quel que soit `live_enabled()`. Ne JAMAIS remplacer `dry is False` par
    `not dry` : cela rendrait un simple `plan_cycle(cell)` live-éligible."""
    res = {"dry": True, "refused": False, "killed": False, "delegated": 0, "intentions": []}
    if not cell.get("survives"):
        res["refused"] = True
        return res
    if cell.get("surface") not in ge.SURFACE:          # surface inconnue -> refus gracieux (pas de KeyError)
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
    """Route l'intention vers l'exécuteur audité de la surface. NON CÂBLÉ (décision
    proprio 24/07 : 0/120 survivant mesuré -> pas de chemin d'ordre réel pour une
    stratégie sans edge ; cf. docstring module + docs/GRID_STRATEGIES.md §6). À
    câbler SEULEMENT si un survivant apparaît (délègue alors à spot_trader/
    margin_trader/futures_executor, + classification §67)."""
    surface = intention["surface"]
    if surface in ("spot", "margin", "futures"):
        raise NotImplementedError(f"câblage différé ({surface}) — aucun survivant mesuré")
    raise ValueError(f"surface inconnue: {surface}")
