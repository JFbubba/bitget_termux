"""
failsafe_escalate.py — alerte IMMEDIATE sur echec dur d'un service decisionnel.

Classement : SAFE. Declenche par systemd (OnFailure=bitget-failsafe@%n.service) quand
un cycle brain/scan ENTRE en etat 'failed' (crash, timeout). Ne fait QUE notifier et
journaliser : AUCUN ordre, AUCUNE cle, AUCUNE action de trading. L'escalade persistante
(rearmement des timers, kill-switch fail-safe) appartient au watchdog --heal.

Dedup : au plus une alerte par (unite, tranche de DEDUP_S) pour ne pas spammer si un
service crash-loope minute apres minute. Etat dans .failsafe_state.json (gitignored).
"""

import json
import sys
import time
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / ".failsafe_state.json"
DEDUP_S = 900          # 15 min : une alerte par service par quart d'heure au plus


def should_alert(state, unit, now, dedup_s=DEDUP_S):
    """PUR. Faut-il alerter pour cette unite maintenant ? Vrai si jamais alertee ou si
    la derniere alerte de CETTE unite date de plus de dedup_s. Retourne (bool, nouvel_etat)."""
    state = dict(state or {})
    last = state.get(str(unit))
    try:
        recent = last is not None and (float(now) - float(last)) < float(dedup_s)
    except (TypeError, ValueError):
        recent = False
    if recent:
        return False, state
    state[str(unit)] = int(now)
    return True, state


def _load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state):
    try:
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    unit = argv[0] if argv else "service inconnu"
    now = time.time()
    alert, state = should_alert(_load_state(), unit, now)
    if not alert:
        print(f"failsafe: echec {unit} deja alerte recemment (dedup). Silencieux.")
        return
    _save_state(state)
    msg = (f"⚠️ FAIL-SAFE : le service decisionnel {unit} a ECHOUE (crash/timeout). "
           "Le watchdog --heal va tenter de rearmer le timer ; le stop -5% reste enforced "
           "par stop_guardian. Diagnostiquer : journalctl -u " + str(unit).replace(".service", ""))
    try:
        import telegram_notifier as tn
        tn.send_telegram(msg)
    except Exception:
        pass
    print("failsafe: ALERTE ->", msg)


if __name__ == "__main__":
    main()
