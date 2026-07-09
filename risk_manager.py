"""
risk_manager.py — garde-fous DURS avant toute exécution (kill-switch + limites).

Classement : SAFE. C'est de la LOGIQUE DE RISQUE : ce module ne passe AUCUN ordre.
Il dit seulement OUI/NON à un ordre proposé selon des limites non négociables.
Aucun trade réel ne doit jamais contourner cette couche.

Limites (réglables via .env, défauts conservateurs) :
  RISK_MAX_POSITION_USD     taille max d'une position (USD)         [50]
  RISK_MAX_LEVERAGE         levier max                              [3]
  RISK_MAX_OPEN_POSITIONS   nombre max de positions simultanées     [3]
  RISK_MAX_DAILY_LOSS_USD   perte max sur la journée -> halte       [25]

Kill-switch (arrêt d'urgence immédiat de TOUT trading) :
  - crée le fichier  KILL_SWITCH  (touch KILL_SWITCH)
  - ou  TRADING_HALT=1  dans l'environnement
"""

import os
from pathlib import Path

# Chemin ABSOLU (ancré au dépôt) : le kill-switch DOIT être vu quel que soit le cwd de
# l'appelant. Les boucles tournent cwd=dépôt, mais un run manuel/test lancé d'un autre
# répertoire ne doit jamais rater un KILL_SWITCH armé. (§revue chemin argent — Thème 1)
KILL_FILE = Path(__file__).resolve().parent / "KILL_SWITCH"


def _f(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


def _i(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return int(default)


from config_utils import cfg as _cfg


def load_limits():
    # défauts = config (source unique) ; surchargeables par .env (RISK_MAX_*)
    return {
        "max_position_usd": _f("RISK_MAX_POSITION_USD", _cfg("MAX_POSITION_USD", 50)),
        "max_leverage": _f("RISK_MAX_LEVERAGE", _cfg("MAX_LEVERAGE", 2)),
        "max_open_positions": _i("RISK_MAX_OPEN_POSITIONS", int(_cfg("MAX_OPEN_POSITIONS", 3))),
        "max_daily_loss_usd": _f("RISK_MAX_DAILY_LOSS_USD", _cfg("MAX_DAILY_LOSS_USD", 25)),
    }


def kill_switch_active():
    # Fail-CLOSED : si l'on ne peut pas PROUVER l'absence du fichier (erreur de stat :
    # permission, FS), on considère le kill-switch ACTIF. TRADING_HALT reste un
    # court-circuit d'urgence par l'environnement.
    if os.getenv("TRADING_HALT", "").lower() in ("1", "true", "yes", "on"):
        return True
    try:
        KILL_FILE.stat()
        return True                       # présent -> kill actif
    except FileNotFoundError:
        return False                      # absence AVÉRÉE -> OK
    except OSError:
        return True                       # indéterminable -> fail-closed (on bloque)


def check_trade(proposed, *, open_positions, daily_loss_usd, limits=None):
    """proposed = {notional_usd, leverage}. Retourne (autorisé: bool, raison: str).

    Fonction PURE et testée. Toute exécution réelle doit l'appeler AVANT d'agir.
    """
    limits = limits or load_limits()

    if kill_switch_active():
        return False, "KILL_SWITCH actif — tout trading est arrêté"

    if daily_loss_usd >= limits["max_daily_loss_usd"]:
        return False, f"perte du jour {daily_loss_usd:.2f} >= max {limits['max_daily_loss_usd']:.2f} — halte journalière"

    if open_positions >= limits["max_open_positions"]:
        return False, f"trop de positions ouvertes ({open_positions} >= {limits['max_open_positions']})"

    # fail-closed : une entrée non numérique est REJETÉE, jamais propagée en
    # exception (sinon l'appelant fail-safe pourrait laisser passer l'ordre).
    try:
        notional = float(proposed.get("notional_usd", 0) or 0)
    except (TypeError, ValueError):
        return False, "notional invalide (non numérique)"
    if notional <= 0:
        return False, "notional invalide (<= 0)"
    if notional > limits["max_position_usd"]:
        return False, f"taille {notional:.2f} > max {limits['max_position_usd']:.2f}"

    try:
        leverage = float(proposed.get("leverage", 1) or 1)
    except (TypeError, ValueError):
        return False, "levier invalide (non numérique)"
    if leverage <= 0:
        return False, "levier invalide (<= 0)"
    if leverage > limits["max_leverage"]:
        return False, f"levier {leverage:.1f} > max {limits['max_leverage']:.1f}"

    return True, "OK"


def status():
    limits = load_limits()
    return {
        "kill_switch": kill_switch_active(),
        "limits": limits,
    }


def main():
    import json
    print("=== RISK MANAGER ===")
    print(json.dumps(status(), indent=2))
    print("Kill-switch d'urgence : touch KILL_SWITCH  (ou TRADING_HALT=1)")
    print("Aucun ordre passé ici. VERDICT: SAFE")


if __name__ == "__main__":
    main()
