"""
watchdog.py — surveillance LECTURE SEULE de la boucle agent_loop.py.

Classement : SAFE.
  - ne fait QUE constater (PID, /proc, fraicheur du dernier scan)
  - n'envoie aucun ordre, ne touche jamais au trading
  - par defaut : alerte uniquement. Avec --heal (Couche 3, sur l'hote) : SUPERVISION
    ACTIVE — rearme les timers brain/scan morts, escalade en fail-safe (kill-switch)
    apres N cycles STALE/DOWN. Aucune action de trading : seulement systemctl restart
    des timers + kill-switch defensif (n'ouvre jamais rien).
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

import json
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


# ---------- SUPERVISION ACTIVE (Couche 3 : réanimer brain/scan, escalade fail-safe) ----------

# Les DEUX services décisionnels dont l'incident a montré qu'ils n'étaient ni
# supervisés ni redémarrés : pilotés par timer, un timer désarmé = mort silencieuse.
UNITES_DECISION = ("bitget-brain.timer", "bitget-scan.timer")
HEAL_STATE_FILE = Path(".watchdog_heal_state.json")


def timers_a_rearmer(active_map):
    """PUR. Parmi les unités décisionnelles, celles à REDÉMARRER = celles qui ne sont
    pas 'active' de façon certaine (False ou None/indéterminé -> on réarme, fail-safe :
    mieux vaut un restart inutile qu'un timer mort ignoré)."""
    return [u for u, a in active_map.items() if a is not True]


def heal_escalade(consecutifs, seuil):
    """PUR. Faut-il ESCALADER (fail-safe) ? Vrai si le nombre de cycles STALE/DOWN
    consécutifs (malgré les réarmements) atteint le seuil : brain/scan restent morts,
    personne ne gère les positions -> on arme le kill-switch (le guardian, lui,
    continue d'enforcer le stop −5 %)."""
    try:
        return int(consecutifs) >= int(seuil) and int(seuil) > 0
    except (TypeError, ValueError):
        return False


def restart_unit(name):
    """systemctl restart <name>. ACTION défensive (réarme un timer décisionnel mort).
    Best-effort : True si la commande a réussi, None si systemctl indisponible."""
    try:
        import subprocess
        r = subprocess.run(["systemctl", "restart", name], capture_output=True,
                           text=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return None


def _reset_failed(name):
    """Purge l'état 'failed' d'un service (un cycle oneshot bloqué/tué par timeout
    laisse le .service en échec, ce qui peut bloquer les relances). Best-effort."""
    try:
        import subprocess
        subprocess.run(["systemctl", "reset-failed", name.replace(".timer", ".service")],
                       capture_output=True, text=True, timeout=10)
    except Exception:
        pass


def _load_heal_state():
    try:
        return json.loads(HEAL_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"consecutifs": 0}


def _save_heal_state(state):
    try:
        HEAL_STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def heal(verdict, *, seuil_escalade=None):
    """SUPERVISION ACTIVE. Sur STALE/DOWN : réarme les timers brain/scan morts, purge
    les cycles bloqués, et compte les échecs CONSÉCUTIFS ; à partir du seuil, ESCALADE
    en fail-safe (kill-switch + alerte forte). Sur RUNNING : remet le compteur à zéro.
    Retourne un récapitulatif d'actions (aucun secret)."""
    from config_utils import cfg as _cfg
    seuil = int(_cfg("WATCHDOG_HEAL_ESCALADE_SEUIL", 3)) if seuil_escalade is None else int(seuil_escalade)
    state = _load_heal_state()
    actions = {"verdict": verdict, "rearmes": [], "escalade": False}

    # KILL_SWITCH armé = HALTE VOLONTAIRE : brain/scan sont SENSÉS être au repos
    # (leur ExecCondition les saute). Un scan périmé n'est alors PAS une panne -> ni
    # réarmement, ni escalade, ni fausse alerte ; on remet le compteur à zéro. Le
    # stop_guardian, lui, continue d'enforcer le stop indépendamment.
    if _kill_actif():
        actions["halte_volontaire"] = True
        if state.get("consecutifs"):
            state["consecutifs"] = 0
            _save_heal_state(state)
        return actions

    if verdict in ("RUNNING", "RUNNING?", "PAUSE"):
        if state.get("consecutifs"):
            state["consecutifs"] = 0
            _save_heal_state(state)
        return actions

    # STALE / DOWN / UNKNOWN : brain/scan possiblement morts -> tenter de réanimer.
    active_map = {u: service_active(u) for u in UNITES_DECISION}
    for unit in timers_a_rearmer(active_map):
        _reset_failed(unit)
        ok = restart_unit(unit)
        actions["rearmes"].append({"unit": unit, "ok": ok})

    state["consecutifs"] = int(state.get("consecutifs", 0)) + 1
    actions["consecutifs"] = state["consecutifs"]
    if heal_escalade(state["consecutifs"], seuil):
        actions["escalade"] = True
        # Vérifier que l'armement a RÉELLEMENT pris (write_text peut échouer : disque,
        # permission). On ne doit pas annoncer une halte qui n'existe pas.
        kill_ok = _kill_actif()
        if not kill_ok:
            kill_ok = bool(arm_kill_switch(
                f"supervision : brain/scan STALE/DOWN x{state['consecutifs']} "
                f"(seuil {seuil}) — fail-safe")) and _kill_actif()
        actions["kill_arme"] = bool(kill_ok)
        try:
            import telegram_notifier as tn
            if kill_ok:
                tn.send_telegram(
                    f"🚑 SUPERVISION : brain/scan {verdict} depuis {state['consecutifs']} cycles "
                    f"malgré réarmement des timers. Kill-switch ARMÉ (fail-safe : plus aucune "
                    "OUVERTURE ; le stop −5 % reste enforced par stop_guardian). "
                    "Intervention requise : journalctl -u bitget-scan -u bitget-brain.")
            else:
                tn.send_telegram(
                    f"🚨 SUPERVISION : brain/scan {verdict} depuis {state['consecutifs']} cycles "
                    "ET **l'armement du kill-switch a ÉCHOUÉ** (écriture impossible ?). "
                    "Le trading n'est PEUT-ÊTRE PAS halté. Intervention MANUELLE IMMÉDIATE : "
                    "touch ~/bitget_termux_repo/KILL_SWITCH")
        except Exception:
            pass
    _save_heal_state(state)
    return actions


def _kill_actif():
    try:
        import risk_manager
        return risk_manager.kill_switch_active()
    except Exception:
        return False


def audit_ouvertures_nues():
    """Invariant Couche 1 (observabilité) : alerte si une ouverture directionnelle
    RÉELLE est partie SANS stop-loss préréglé côté exchange. Best-effort, lecture
    seule. Dédup 1/jour (fichier d'état). Retourne la liste des ouvertures nues."""
    try:
        import futures_executor as fe
        nus = fe.opens_sans_stop()
    except Exception:
        return []
    if not nus:
        return []
    try:
        jour = int(time.time() // 86400)
        st = _load_heal_state()
        if int(st.get("nus_alert_day", -1)) != jour:
            detail = " · ".join(f"{n.get('agent')} {n.get('symbol')} (oid {n.get('oid')})"
                                for n in nus[-5:])
            import telegram_notifier as tn
            tn.send_telegram(f"🩹 INVARIANT SL : {len(nus)} ouverture(s) directionnelle(s) "
                             f"RÉELLE(S) sans stop-loss exchange — {detail}. À corriger : toute "
                             "position directionnelle doit porter son SL préréglé.")
            st["nus_alert_day"] = jour
            _save_heal_state(st)
    except Exception:
        pass
    return nus


def audit_positions_sans_sl_exchange():
    """Invariant Couche 1 (observabilité, EXCHANGE) : alerte si une position directionnelle
    RÉELLE OUVERTE n'a PAS de SL plan côté exchange (§durcis-sl Étape 2). Complète
    `audit_ouvertures_nues` (qui prouve l'INTENTION au ledger) en réconciliant le SL RÉELLEMENT
    préréglé (ordre plan/TPSL live). Best-effort, LECTURE SEULE, dédup 1/jour. Fail-closed :
    None (sources illisibles) -> pas d'alerte (ni faux vert, ni cri en aveugle)."""
    try:
        import futures_executor as fe
        nus = fe.positions_sans_sl_exchange_live()
    except Exception:
        return []
    if not nus:                                       # [] = couvert · None = illisible -> pas d'alerte
        return nus or []
    try:
        jour = int(time.time() // 86400)
        st = _load_heal_state()
        if int(st.get("nus_exch_alert_day", -1)) != jour:
            detail = " · ".join(f"{n.get('agent')} {n.get('symbol')} {n.get('side')}" for n in nus[-5:])
            import telegram_notifier as tn
            tn.send_telegram(f"🛑 INVARIANT SL EXCHANGE : {len(nus)} position(s) directionnelle(s) "
                             f"OUVERTE(S) sans SL plan côté exchange — {detail}. Le SL préréglé a pu "
                             "être lâché au fill ou annulé après coup : re-poser immédiatement.")
            st["nus_exch_alert_day"] = jour
            _save_heal_state(st)
    except Exception:
        pass
    return nus


# BATTEMENT PER-CYCLE du cœur décisionnel (§reprise-watchdog, incident 14/07).
# brain_cycle.py écrit brain_log.json (+ son history) à CHAQUE cycle,
# INCONDITIONNELLEMENT : frais = cerveau vivant, figé = cerveau à l'arrêt/mort. C'est
# la BONNE preuve de vie du scan — contrairement à signals_journal.csv, qui est
# ÉVÉNEMENTIEL (dédupliqué) : une plage de signaux stables >30 min le fige alors que le
# scan tourne, d'où le faux DOWN -> kill-switch du 14/07. Artefacts choisis PROPRES :
# écrits SEULEMENT par le cycle décisionnel. On EXCLUT sciemment .runtime_cache.json et
# .stop_guardian_heartbeat.json — ils continuent de tourner PENDANT la halte volontaire,
# donc ils MASQUERAIENT une vraie mort de la boucle.
SCAN_HEARTBEAT = [
    ("brain_log.json", 20),
    ("brain_log_history.jsonl", 20),
]


def heartbeat_present(carte=None, racine=None):
    """PUR (fs). True si AU MOINS UN artefact de battement existe (quel que soit son
    âge) -> on a une SOURCE de liveness. Aucun -> état indéterminable (UNKNOWN)."""
    racine = Path(racine) if racine else Path(".")
    return any((racine / nom).exists() for nom, _ in (carte or SCAN_HEARTBEAT))


def heartbeat_fresh(carte=None, now=None, racine=None):
    """PUR (fs). True si AU MOINS UN artefact de battement per-cycle est présent ET
    dans son seuil. Preuve de vie robuste : le cycle écrit plusieurs artefacts -> un
    seul frais suffit ; TOUS figés/absents = machinerie silencieuse (vrai DOWN)."""
    now = time.time() if now is None else now
    racine = Path(racine) if racine else Path(".")
    for nom, seuil_min in (carte or SCAN_HEARTBEAT):
        p = racine / nom
        if p.exists() and (now - p.stat().st_mtime) / 60.0 <= seuil_min:
            return True
    return False


def heartbeat_age(carte=None, now=None, racine=None):
    """PUR (fs). Âge (min) de l'artefact de battement le PLUS FRAIS présent, ou None si
    aucun. Pour l'affichage honnête du rapport (le verdict, lui, passe par
    heartbeat_fresh, qui respecte le seuil PROPRE à chaque artefact)."""
    now = time.time() if now is None else now
    racine = Path(racine) if racine else Path(".")
    ages = [(now - (racine / nom).stat().st_mtime) / 60.0
            for nom, _ in (carte or SCAN_HEARTBEAT) if (racine / nom).exists()]
    return round(min(ages), 1) if ages else None


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

    now = time.time()
    if signals.exists():
        age_min = (now - signals.stat().st_mtime) / 60.0
        status["age_min"] = age_min
        signals_fresh = age_min <= 2 * interval_min
    else:
        status["age_min"] = None
        signals_fresh = False

    # §reprise-watchdog (incident 14/07) : la VIE du scan se juge sur le BATTEMENT
    # per-cycle (brain_log.json), PAS sur signals_journal.csv (événementiel/dédupliqué,
    # figé quand les signaux sont stables alors que le scan tourne). signals_journal
    # frais reste une corroboration POSITIVE (un signal neuf récent prouve aussi la vie)
    # -> fresh = OR ; DOWN seulement si AUCUNE source récente.
    hb_fresh = heartbeat_fresh(now=now)
    status["signals_fresh"] = signals_fresh
    status["heartbeat_fresh"] = hb_fresh
    status["heartbeat_age_min"] = heartbeat_age(now=now)
    status["data_known"] = signals.exists() or heartbeat_present()
    status["fresh"] = signals_fresh or hb_fresh

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
        age = status.get("age_min")
        hb = status.get("heartbeat_age_min")
        fresh = "frais" if status.get("fresh") else "PÉRIMÉ"
        journal = f"journal {age:.1f} min" if age is not None else "journal absent"
        battement = f"battement cerveau {hb:.1f} min" if hb is not None else "battement absent"
        lines.append(
            f"Dernier scan : {journal} · {battement} "
            f"(seuil scan {2 * status.get('interval_min', 0):.0f} min) -> {fresh}"
        )
    else:
        lines.append("Dernier scan : aucune source de vie (journal + battement absents)")

    lines.append(f"Pause        : {'OUI' if status.get('paused') else 'non'}")
    lines.append("")
    lines.append(f"VERDICT: {status.get('verdict')}")

    if status.get("alert"):
        lines.append("⚠️ ALERTE: agent_loop semble arrêté ou le scan est périmé.")

    lines.append("")
    lines.append("Mode: aucun ordre réel. Réarmement des timers brain/scan seulement avec --heal.")
    return "\n".join(lines)


# CARTE DE FRAÎCHEUR (§61 suite) : chaque boucle ÉCRIT quelque part — un writer
# qui se tait (exception avalée, étape sautée, service mort) FIGE son artefact.
# Surveiller les sorties couvre TOUTES les causes de silence d'un coup.
# (validation : 420 min = 6 h de cadence + marge ; carry : journal throttlé 1 h.)
CARTE_FRAICHEUR = [
    ("brain_log.json", 20), ("brain_log_history.jsonl", 20),
    ("futures_auto_journal.jsonl", 20), (".futures_pos_state.json", 20),
    ("brain_hitrates.json", 90), ("brain_weights.json", 90),
    (".runtime_cache.json", 20), (".carry_journal.json", 120),
    ("microstructure_history.jsonl", 20), ("validation_report.json", 420),
    (".stop_guardian_heartbeat.json", 5),   # enforceur stop −5 % (tick ~20s) : mort visible
    # §89 : la machinerie §76-88 aussi — « rien d'aveugle » vaut pour les nouveaux organes.
    (".alt_carry_journal.jsonl", 130),      # moisson funding (cron :35, marge 2 cycles)
    (".liquidity_journal.jsonl", 130),      # gestion de liquidité (cron :15)
    (".mm_journal.jsonl", 20),              # market making §94 (cron */5 posée le 07/07, marge 4 cycles)
    (".daily_digest_stamp", 26 * 60),       # digest quotidien 07:00
    ("neural_net_meta.json", 26 * 60),      # fine-tune NN 04:20
    # §reprise-watchdog/ERR-012 : STAMP per-run (écrit à chaque run RÉUSSI), PAS le mtime
    # du dossier — événementiel (ne bouge que sur promotion, rare) -> figé alors que le
    # lab tourne. Un crash/data-indispo ne stampe pas -> figé -> vrai positif conservé.
    ("strategies_out/.last_run", 80 * 60),  # lab mar/jeu/sam (gap max sam->mar + marge)
]


def artefacts_figes(carte=None, now=None, racine=None):
    """PUR (fs seulement). [(nom, age_min|None)] des artefacts FIGÉS (âge > seuil)
    ou ABSENTS. [] = rien d'aveugle."""
    import time as _t
    now = _t.time() if now is None else now
    racine = Path(racine) if racine else Path(".")
    figes = []
    for nom, seuil_min in (carte or CARTE_FRAICHEUR):
        p = racine / nom
        if not p.exists():
            figes.append((nom, None))
            continue
        age = (now - p.stat().st_mtime) / 60.0
        if age > seuil_min:
            figes.append((nom, round(age, 1)))
    return figes


def brain_age(chemin=None):
    """Âge (s) de la dernière entrée de brain_log.json — None si illisible. PUR
    si chemin injecté."""
    import json
    import time
    try:
        log = json.loads((Path(chemin) if chemin else Path("brain_log.json")).read_text(encoding="utf-8"))
        ts = max(e.get("ts", 0) for e in log if isinstance(e, dict))
        return max(0.0, time.time() - ts)
    except Exception:
        return None


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
    # CARTE DE FRAÎCHEUR complète (§61 suite) : le gel du cerveau (4.7 h de
    # NameError avalé) n'était surveillé par RIEN — désormais chaque artefact
    # de chaque boucle a son seuil ; le moindre silence devient une alerte.
    figes = artefacts_figes()
    if figes:
        detail = " · ".join(f"{n} ({'absent' if a is None else str(a) + ' min'})"
                            for n, a in figes)
        print(f"  artefacts FIGÉS : {detail}")
        try:
            import telegram_notifier as tn
            tn.send_telegram(f"🚨 WATCHDOG : {len(figes)} artefact(s) FIGÉ(S) — {detail}. "
                             "Une boucle s'est tue (exception avalée ou service mort) : "
                             "voir journalctl -u bitget-scan.")
        except Exception:
            pass
    else:
        print(f"  artefacts : {len(CARTE_FRAICHEUR)}/{len(CARTE_FRAICHEUR)} frais (rien d'aveugle)")

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

    # --heal : SUPERVISION ACTIVE (Couche 3). Réarme les timers brain/scan morts sur
    # STALE/DOWN, escalade en fail-safe après N cycles. À N'ACTIVER que sur l'hôte
    # (le timer bitget-watchdog) — le mode par défaut reste alerte seule.
    if "--heal" in argv:
        try:
            actions = heal(status.get("verdict"))
            if actions.get("rearmes"):
                detail = " · ".join(f"{r['unit']}={'ok' if r['ok'] else 'échec'}"
                                    for r in actions["rearmes"])
                print(f"\n🚑 Supervision : réarmement -> {detail}"
                      + (f" [x{actions.get('consecutifs')} consécutifs]" if actions.get('consecutifs') else ""))
            if actions.get("escalade"):
                print("⛔ ESCALADE fail-safe : kill-switch armé (brain/scan persistants DOWN).")
        except Exception as exc:
            print(f"\n[supervision --heal indisponible: {type(exc).__name__}]")

    # Invariant SL (Couche 1) : alerte si une ouverture directionnelle est partie nue
    # (INTENTION au ledger) ET si une position ouverte n'a pas de SL plan EXCHANGE (§durcis-sl Étape 2).
    try:
        audit_ouvertures_nues()
        audit_positions_sans_sl_exchange()
        # Auto-POSE du SL exchange manquant (§durcis-sl Étape 2) — SEULEMENT si armé
        # (FUTURES_SL_AUTOHEAL) ; sinon l'alerte ci-dessus suffit. Protectif, idempotent (ne
        # pose que pour une position ACTUELLEMENT nue, via le tool hub futures_place_tpsl_order).
        from config_utils import env_flag as _envf
        if _envf("FUTURES_SL_AUTOHEAL", False):
            import futures_executor as _fe
            _fe.enforce_position_sl()
    except Exception:
        pass

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
