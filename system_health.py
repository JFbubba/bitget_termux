"""
system_health.py — bilan de santé LECTURE SEULE du système Bitget local.

Classement : SAFE (lecture seule, n'envoie aucun ordre, n'affiche aucun secret).

Commande Telegram associée proposée : /system_health
(ajouter dans telegram_command_bot.handle_command — voir AUDIT_BITGET.md).

Vérifie :
  - fichiers attendus présents / manquants (vs manifest),
  - fraîcheur des journaux (dernier scan trop ancien ?),
  - compteurs open / final,
  - tous les agents can_trade=False,
  - PRÉSENCE (booléenne) de la config Telegram — jamais les valeurs,
  - état pause.

Sortie : un bloc lisible + une ligne HEALTH: OK / DEGRADED.
Le système reste en lecture seule : VERDICT trading = DISABLED.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
import time
from pathlib import Path

import config
from agents_manifest import AGENTS

SIGNALS_FILE = Path(config.SIGNALS_JOURNAL_FILE)
OPEN_FILE = Path(config.OPEN_STATE_FILE)
FINAL_FILE = Path(config.FINAL_OUTCOMES_FILE)
PENDING_ORDERS_FILE = Path("pending_orders.json")
PAUSE_FILE = Path("agent_paused.flag")

EXPECTED_FILES = [a["file"] for a in AGENTS]


def file_age_minutes(path):
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 60.0


def count_csv_rows(path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        return max(sum(1 for _ in f) - 1, 0)  # -1 pour l'entête


def main():
    issues = []
    print("=== SYSTEM HEALTH (lecture seule) ===")
    print()

    # Fichiers attendus
    missing = [f for f in EXPECTED_FILES if not Path(f).exists()]
    print("Fichiers (manifest):")
    print(f"- attendus: {len(EXPECTED_FILES)} | manquants: {len(missing)}")
    if missing:
        print(f"  -> manquants: {', '.join(sorted(missing))}")
        issues.append(f"{len(missing)} fichier(s) du manifest manquant(s)")
    print()

    # Fraîcheur du dernier scan
    age = file_age_minutes(SIGNALS_FILE)
    loop_min = config.LOOP_INTERVAL_SECONDS / 60.0
    print("Fraîcheur des données:")
    if age is None:
        print(f"- {SIGNALS_FILE}: absent")
        issues.append("journal de signaux absent")
    else:
        stale = age > 2 * loop_min
        print(f"- dernier scan il y a {age:.1f} min (intervalle {loop_min:.0f} min)"
              f" -> {'PÉRIMÉ' if stale else 'frais'}")
        if stale:
            issues.append(f"scan périmé ({age:.0f} min)")
    print()

    # Compteurs
    print("Compteurs:")
    print(f"- signaux journalisés: {count_csv_rows(SIGNALS_FILE)}")
    print(f"- positions ouvertes (open_state): {count_csv_rows(OPEN_FILE)}")
    print(f"- résultats finalisés: {count_csv_rows(FINAL_FILE)}")
    print(f"- pending_orders.json présent: {PENDING_ORDERS_FILE.exists()}")
    print()

    # Garde trading
    print("Garde trading:")
    can_trade_true = [a["id"] for a in AGENTS if a.get("can_trade") is not False]
    print(f"- agents can_trade!=False: {len(can_trade_true)}")
    if can_trade_true:
        issues.append(f"agents can_trade!=False: {can_trade_true}")
    print("- exécution réelle: DISABLED (dry-run uniquement)")
    print()

    # Telegram — PRÉSENCE uniquement, jamais les valeurs
    print("Config Telegram (présence uniquement):")
    print(f"- TELEGRAM_BOT_TOKEN défini: {os.getenv('TELEGRAM_BOT_TOKEN') is not None}")
    print(f"- TELEGRAM_CHAT_ID défini: {os.getenv('TELEGRAM_CHAT_ID') is not None}")
    print()

    # Pause
    print(f"État pause: {'EN PAUSE' if PAUSE_FILE.exists() else 'ACTIF'}")
    print()

    if issues:
        print("HEALTH: DEGRADED")
        for i in issues:
            print(f"- {i}")
    else:
        print("HEALTH: OK")
    print()
    print("VERDICT: SAFE")  # lecture seule, aucun ordre réel possible ici


if __name__ == "__main__":
    main()
