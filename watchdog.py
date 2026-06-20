"""
watchdog.py — surveillance LECTURE SEULE de la boucle agent_loop.py.

Classement : SAFE.
  - ne fait QUE constater (PID, /proc, fraicheur du dernier scan)
  - n'envoie aucun ordre, ne touche jamais au trading
  - ne REDEMARRE PAS la boucle (alerte uniquement, jamais d'action)
  - n'affiche aucun secret

Sources de liveness combinees (indépendantes, robustes sous Termux) :
  1. agent_loop.pid (si present)        -> process encore vivant ?
  2. scan /proc                          -> "python agent_loop.py" present ?
  3. fraicheur de signals_journal.csv    -> dernier scan recent ?

Usage CLI :
    python watchdog.py            # affiche l'etat
    python watchdog.py --alert    # + alerte Telegram si DOWN/STALE

Commande Telegram associee : /watchdog
"""

import os
import time
from pathlib import Path

import config

PID_FILE = Path("agent_loop.pid")
PAUSE_FILE = Path("agent_paused.flag")


def decide_verdict(process_known, process_alive, data_known, fresh, paused):
    """Decision pure (sans I/O, donc testable).

    Retourne (verdict, alert_bool).
      - PAUSE     : pause volontaire, jamais d'alerte
      - RUNNING   : process vivant + scan frais
      - STALE     : process vivant mais scan perime -> alerte
      - DOWN      : process mort, ou indetermine + scan perime -> alerte
      - RUNNING?  : process indetermine mais scan frais (presume actif)
      - UNKNOWN   : rien de fiable a constater
    """
    if paused:
        return "PAUSE", False

    if process_known and process_alive:
        if data_known and not fresh:
            return "STALE", True
        return "RUNNING", False

    if process_known and not process_alive:
        return "DOWN", True

    # Process indetermine (ni PID file, ni /proc exploitable) : on se fie aux donnees.
    if data_known:
        return ("RUNNING?", False) if fresh else ("DOWN", True)

    return "UNKNOWN", False


def read_pid_file():
    if not PID_FILE.exists():
        return None
    try:
        txt = PID_FILE.read_text().strip()
        return int(txt) if txt else None
    except (ValueError, OSError):
        return None


def pid_is_alive(pid):
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # le process existe mais ne nous appartient pas
    except OSError:
        return False


def _read_proc_cmdline(pid_str):
    try:
        with open(f"/proc/{pid_str}/cmdline", "rb") as f:
            return f.read().replace(b"\x00", b" ").decode("utf-8", "ignore")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None


def find_loop_process():
    """Cherche 'agent_loop.py' dans /proc. Retourne (pid|None, etat)."""
    proc = Path("/proc")
    if not proc.is_dir():
        return None, "unavailable"

    my_pid = os.getpid()
    try:
        entries = list(proc.iterdir())
    except OSError:
        return None, "unavailable"

    for entry in entries:
        if not entry.name.isdigit():
            continue
        if int(entry.name) == my_pid:
            continue
        cmd = _read_proc_cmdline(entry.name)
        if cmd and "agent_loop.py" in cmd:
            return int(entry.name), "found"

    return None, "not_found"


def evaluate():
    """Rassemble les signaux I/O et applique decide_verdict."""
    status = {"paused": PAUSE_FILE.exists()}

    pid = read_pid_file()
    status["pid_file_pid"] = pid
    pid_alive = pid_is_alive(pid)

    scan_pid, scan_state = find_loop_process()
    status["proc_scan"] = scan_state
    status["proc_scan_pid"] = scan_pid

    status["process_known"] = (pid is not None) or (scan_state in ("found", "not_found"))
    status["process_alive"] = bool(pid_alive) or (scan_state == "found")

    signals = Path(config.SIGNALS_JOURNAL_FILE)
    interval_min = config.LOOP_INTERVAL_SECONDS / 60.0
    status["interval_min"] = interval_min

    if signals.exists():
        age_min = (time.time() - signals.stat().st_mtime) / 60.0
        status["data_known"] = True
        status["age_min"] = age_min
        status["fresh"] = age_min <= 2 * interval_min
    else:
        status["data_known"] = False
        status["age_min"] = None
        status["fresh"] = False

    verdict, alert = decide_verdict(
        status["process_known"],
        status["process_alive"],
        status["data_known"],
        status["fresh"],
        status["paused"],
    )
    status["verdict"] = verdict
    status["alert"] = alert
    return status


def build_report(status):
    """Formate l'etat en texte lisible (Telegram / CLI). Aucun secret."""
    lines = ["=== WATCHDOG agent_loop ==="]

    pid = status.get("pid_file_pid")
    lines.append(f"PID file     : {pid if pid is not None else 'absent'}")

    scan = status.get("proc_scan")
    scan_pid = status.get("proc_scan_pid")
    lines.append(
        f"Scan /proc   : {scan}" + (f" (pid {scan_pid})" if scan_pid else "")
    )

    alive = status.get("process_alive")
    suffix = "" if status.get("process_known") else " (indeterminé)"
    lines.append(f"Process actif: {alive}{suffix}")

    if status.get("data_known"):
        age = status.get("age_min") or 0.0
        fresh = "frais" if status.get("fresh") else "PÉRIMÉ"
        lines.append(
            f"Dernier scan : il y a {age:.1f} min "
            f"(intervalle {status.get('interval_min', 0):.0f} min) -> {fresh}"
        )
    else:
        lines.append(f"Dernier scan : {config.SIGNALS_JOURNAL_FILE} absent")

    lines.append(f"Pause        : {'OUI' if status.get('paused') else 'non'}")
    lines.append("")
    lines.append(f"VERDICT: {status.get('verdict')}")

    if status.get("alert"):
        lines.append("⚠️ ALERTE: agent_loop semble arrêté ou le scan est périmé.")

    lines.append("")
    lines.append("Mode: lecture seule. Aucun ordre réel. Aucun redémarrage automatique.")
    return "\n".join(lines)


def main(argv=None):
    import sys

    argv = sys.argv[1:] if argv is None else argv
    status = evaluate()
    report = build_report(status)
    print(report)

    if "--alert" in argv and status.get("alert"):
        try:
            from telegram_notifier import send_telegram_message
            send_telegram_message(report)
            print()
            print("[alerte Telegram envoyée]")
        except Exception as exc:  # jamais de secret dans le message
            print()
            print(f"[alerte Telegram non envoyée: {type(exc).__name__}]")


if __name__ == "__main__":
    main()
