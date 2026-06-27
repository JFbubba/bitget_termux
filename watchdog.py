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


def process_state_known(pid, scan_state):
    """Connaît-on l'état de la boucle de trading ? Vrai si un PID file est présent OU si un
    process `agent_loop` est TROUVÉ vivant. PUR.
    ⚠️ Architecture par TIMERS : la boucle persistante `agent_loop.py` a été remplacée par
    `bitget-scan.timer` ; son ABSENCE (`not_found`) n'est donc PAS un DOWN — la liveness réelle
    est la FRAÎCHEUR du scan. Sans PID ni process trouvé -> état INDÉTERMINÉ -> decide_verdict
    se fie aux données (RUNNING? si frais). Corrige les fausses alertes DOWN à répétition."""
    return (pid is not None) or (scan_state == "found")


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


def _proc_argv(pid_str):
    """Retourne la liste argv d'un process (depuis /proc), ou None."""
    try:
        with open(f"/proc/{pid_str}/cmdline", "rb") as f:
            raw = f.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    if not raw:
        return None
    return [part.decode("utf-8", "ignore") for part in raw.split(b"\x00") if part]


def _is_agent_loop(argv):
    """Vrai seulement si argv == 'python ... agent_loop.py' (match précis).

    Évite de confondre un process tiers dont la ligne de commande contient
    simplement la chaîne 'agent_loop.py' (editeur, grep, pkill, ce bot...).
    """
    if not argv or len(argv) < 2:
        return False
    if "python" not in argv[0]:
        return False
    return any(a == "agent_loop.py" or a.endswith("/agent_loop.py") for a in argv[1:])


def find_loop_process():
    """Cherche le process 'python agent_loop.py' dans /proc. Retourne (pid|None, etat)."""
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
        if _is_agent_loop(_proc_argv(entry.name)):
            return int(entry.name), "found"

    return None, "not_found"


def microstructure_fresh(rows, now, max_age_s=180):
    """Le buffer de microstructure est-il FRAIS ? PUR. True si le dernier snapshot
    date de moins de max_age_s. Réponse à l'audit (collecteur figé non détecté)."""
    if not rows:
        return False
    last_ts = rows[-1].get("ts")
    if last_ts is None:
        return False
    return (now - float(last_ts)) <= max_age_s


def should_halt(verdict, micro_required, micro_fresh, daily_loss, max_daily_loss):
    """Décision PURE : faut-il poser le KILL_SWITCH ? Retourne (halt, raison).
    Conditions sévères : boucle DOWN, perte du jour >= cap, ou microstructure exigée
    mais figée. Conservateur : le halt ne fait qu'ARRÊTER, jamais ouvrir."""
    if daily_loss is not None and max_daily_loss and daily_loss >= max_daily_loss:
        return True, f"perte du jour {daily_loss:.2f} >= cap {max_daily_loss:.2f}"
    if verdict == "DOWN":
        return True, "boucle de trading DOWN"
    if micro_required and not micro_fresh:
        return True, "microstructure figée (collecteur mort/bloqué)"
    return False, "ok"


def service_active(name):
    """systemctl is-active <name> -> bool. Best-effort (None si indéterminable)."""
    try:
        import subprocess
        r = subprocess.run(["systemctl", "is-active", name], capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() == "active"
    except Exception:
        return None


def microstructure_age(symbol="BTCUSDT", now=None):
    """Âge (s) du dernier snapshot de microstructure, ou None. Best-effort."""
    try:
        import time
        import microstructure
        rows = microstructure.recent(symbol, 1)
        if not rows or rows[-1].get("ts") is None:
            return None
        return (time.time() if now is None else now) - float(rows[-1]["ts"])
    except Exception:
        return None


def arm_kill_switch(reason):
    """Pose le fichier KILL_SWITCH (arrêt d'urgence). ACTION défensive : n'arrête que
    le trading, n'ouvre jamais rien. Best-effort. Réponse à l'audit (#6)."""
    try:
        import risk_manager
        risk_manager.KILL_FILE.write_text(f"auto-halt watchdog: {reason}\n", encoding="utf-8")
        return True
    except Exception:
        return False


def evaluate():
    """Rassemble les signaux I/O et applique decide_verdict."""
    status = {"paused": PAUSE_FILE.exists()}

    pid = read_pid_file()
    status["pid_file_pid"] = pid
    pid_alive = pid_is_alive(pid)

    scan_pid, scan_state = find_loop_process()
    status["proc_scan"] = scan_state
    status["proc_scan_pid"] = scan_pid

    status["process_known"] = process_state_known(pid, scan_state)
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

    # services systemd + fraîcheur microstructure (best-effort, informatif)
    svc_lines = []
    for svc in ("bitget-dashboard", "bitget-bot", "bitget-microstructure"):
        a = service_active(svc)
        svc_lines.append(f"  {svc}: {'active' if a else ('inactive' if a is False else 'n/a')}")
    age = microstructure_age()
    micro_fresh = (age is not None and age <= 180)
    print("\nServices :")
    print("\n".join(svc_lines))
    print(f"  microstructure: {'frais' if micro_fresh else 'figé/absent'}"
          + (f" (âge {age:.0f}s)" if age is not None else ""))

    # --arm-killswitch : pose KILL_SWITCH automatiquement sur anomalie SÉVÈRE (défensif)
    if "--arm-killswitch" in argv:
        try:
            import risk_state
            import risk_manager
            limits = risk_manager.load_limits()
            dl = risk_state.daily_realized_loss_usd()
            halt, why = should_halt(status.get("verdict"), micro_required=True,
                                    micro_fresh=micro_fresh, daily_loss=dl,
                                    max_daily_loss=limits["max_daily_loss_usd"])
            if halt and not risk_manager.kill_switch_active():
                arm_kill_switch(why)
                print(f"\n⛔ KILL_SWITCH posé automatiquement : {why}")
        except Exception as exc:
            print(f"\n[arm-killswitch indisponible: {type(exc).__name__}]")

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
