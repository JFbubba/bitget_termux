"""
stop_guardian.py — ENFORCEUR du stop de perte journalier −5 % (Couche 2).

Classement : SAFE. Ne contient AUCUN code d'ordre : il DÉLÈGUE tout à
`futures_executor` (le seul module d'exécution futures autorisé, audité à part).
Sa seule écriture propre est un fichier de battement (observabilité).

RAISON D'ÊTRE (incident : le stop dépendait de la cadence de brain/scan) :
  Un organe TOTALEMENT INDÉPENDANT de la boucle cerveau/scan, à cadence serrée
  (défaut 20 s, contre l'évaluation HORAIRE du tripwire spend-watch), qui à chaque
  tick :
    1. évalue le stop journalier (futures_executor.enforce_daily_loss) ;
    2. au franchissement CONFIRMÉ : arme le kill-switch (déjà fait par l'exécuteur)
       ET SOLDE toutes les positions (flatten reduceOnly) — armer le kill-switch
       bloque les NOUVEAUX ordres mais ne ferme rien : sans flatten, une position
       perdante continue de saigner sous le seuil.

INDÉPENDANCE (défense en profondeur) :
  • process séparé, supervisé par systemd (Restart=always + WatchdogSec via sd_notify) ;
  • surface de dépendance minimale : n'importe NI swarm_brain, NI le scanner, NI les
    agents — seulement l'exécuteur (lecture equity + réduction) ;
  • ne dépend JAMAIS de la bonne santé de brain/scan ni du superviseur, ni l'inverse.
  Le filet ULTIME (mort totale de l'host) reste le SL préréglé côté exchange (Couche 1).

Usage :
    python stop_guardian.py            # daemon (boucle infinie, heartbeat systemd)
    python stop_guardian.py --once     # un seul tick (tests, cron de secours)
    python stop_guardian.py --status   # lecture seule : état du dernier battement
"""

import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

from config_utils import cfg as _cfg

HEARTBEAT_FILE = Path(__file__).resolve().parent / ".stop_guardian_heartbeat.json"

_STOP = {"flag": False}


def _sd_notify(state):
    """Envoie un message au gestionnaire systemd (sd_notify) si NOTIFY_SOCKET est
    présent. Best-effort, sans dépendance externe. 'READY=1' au démarrage,
    'WATCHDOG=1' à chaque battement (rearme le WatchdogSec)."""
    addr = os.getenv("NOTIFY_SOCKET")
    if not addr:
        return False
    try:
        if addr.startswith("@"):                       # namespace abstrait Linux
            addr = "\0" + addr[1:]
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.connect(addr)
        sock.sendall(state.encode("utf-8"))
        sock.close()
        return True
    except Exception:
        return False


_DEADMAN = {"last": 0.0}


def _deadman_ping(now=None, min_interval_s=60.0):
    """DEAD-MAN SWITCH externe (Couche ultime) : ping best-effort vers une URL de type
    healthchecks.io (config/env GUARDIAN_HEARTBEAT_URL). Si le host devient TOTALEMENT
    muet (guardian mort, systemd mort, machine gelee), le service tiers cesse de recevoir
    le ping et ALERTE de lui-meme — le seul moyen d'etre prevenu d'un silence total.
    Throttle a min_interval_s (inutile de pinger a chaque tick). Aucun secret transmis."""
    now = time.time() if now is None else now
    if now - _DEADMAN["last"] < float(min_interval_s):
        return False
    url = _cfg("GUARDIAN_HEARTBEAT_URL", "") or os.getenv("GUARDIAN_HEARTBEAT_URL", "")
    if not url:
        return False
    try:
        import urllib.request
        req = urllib.request.Request(str(url), headers={"User-Agent": "stop-guardian"})
        urllib.request.urlopen(req, timeout=5).read(64)
        _DEADMAN["last"] = now
        return True
    except Exception:
        _DEADMAN["last"] = now       # ne pas marteler en boucle si l'URL est injoignable
        return False


def _write_heartbeat(payload):
    """Battement d'observabilité (best-effort, atomique). Alimente la carte de
    fraîcheur du watchdog : un guardian qui se tait devient visible."""
    try:
        tmp = HEARTBEAT_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, HEARTBEAT_FILE)
    except Exception:
        pass


def _breakeven_on():
    """Gate FUTURES_BREAKEVEN (§89, armé par décision propriétaire du 07/07)."""
    v = (os.getenv("FUTURES_BREAKEVEN") or "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return bool(_cfg("FUTURES_BREAKEVEN", False))


def _breakeven_decision(rows, opens, frac=0.5, buf=0.0004):
    """PUR. Décide les fermetures « breakeven » : pour chaque position dont le TP1
    partiel a ENCAISSÉ (taille restante ≤ (1 − frac·0.8) × taille d'ouverture) et
    dont le prix est REVENU à l'entrée (± buffer de frais), fermer le reste — le
    trade fini au pire à ~0 au lieu de repartir au SL (leçon ETH §88 : +0.11R puis
    retour à −0.32R). Le SL préréglé d'origine reste le filet dur derrière.
      rows  : positions ouvertes [{symbol, holdSide, total, openPriceAvg, markPrice}]
      opens : {(symbol, side): size_btc à l'OUVERTURE (ledger)}
    -> [{symbol, side, size, mark}]"""
    fermetures = []
    for r in rows or []:
        try:
            sym = str(r.get("symbol") or "").upper()
            side = str(r.get("holdSide") or "").lower()
            taille = float(r.get("total") or 0)
            entree = float(r.get("openPriceAvg") or r.get("averageOpenPrice") or 0)
            mark = float(r.get("markPrice") or r.get("marketPrice") or 0)
        except (TypeError, ValueError):
            continue
        ouverte = opens.get((sym, side))
        if not (sym and side in ("long", "short") and taille > 0 and entree > 0
                and mark > 0 and ouverte):
            continue
        if taille > float(ouverte) * (1.0 - float(frac) * 0.8):
            continue                                   # TP1 pas (encore) encaissé
        touche = (mark <= entree * (1.0 + buf)) if side == "long"             else (mark >= entree * (1.0 - buf))
        if touche:
            fermetures.append({"symbol": sym, "side": side, "size": taille, "mark": mark})
    return fermetures


def _tailles_ouverture(fe):
    """{(symbol, side): size_btc} de la DERNIÈRE ouverture du ledger par position."""
    opens = {}
    try:
        led = json.loads(fe._ledger_path().read_text(encoding="utf-8"))
        for e in led.get("events", []):
            if e.get("action") != "FUTURES_REAL":
                continue
            o = e.get("order") or {}
            if o.get("reduce"):
                continue
            k = (str(o.get("symbol") or "").upper(), str(o.get("side") or "").lower())
            if o.get("size_btc"):
                opens[k] = float(o["size_btc"])
    except Exception:
        pass
    return opens


def _enforce_breakeven(fe, now=None):
    """Applique les fermetures breakeven décidées (réductions pures : exemptes des
    caps d'ouverture, permises même kill-switch armé — fermer n'aggrave jamais).
    Best-effort : un échec réessaie au tick suivant."""
    if not _breakeven_on():
        return None
    rows = fe.positions_ouvertes() or []
    if not rows:
        return {"n": 0}
    import futures_auto as fa
    frac = float(os.getenv("FUTURES_TP_PARTIAL_FRAC") or _cfg("FUTURES_TP_PARTIAL_FRAC", 0.5))
    fermetures = _breakeven_decision(rows, _tailles_ouverture(fe), frac=frac)
    faits = []
    for f in fermetures:
        try:
            res = fe.execute("breakeven", f["side"], round(f["size"] * f["mark"], 2), 1.0,
                             symbol=f["symbol"], reduce=True, size_btc=f["size"],
                             confirm=True, gross_open_usdt=fa.gross_book_usdt(),
                             equity_curve=fe.equity_curve())
            faits.append({"symbol": f["symbol"], "ok": bool(res.get("executed"))})
            if res.get("executed"):
                try:
                    import telegram_notifier as tn
                    tn.send_telegram(f"⚖️ BREAKEVEN : reste de {f['side']} {f['symbol']} "
                                     f"soldé à ~l'entrée (TP1 déjà encaissé) — trade fini ≥ 0.")
                except Exception:
                    pass
        except Exception:
            faits.append({"symbol": f["symbol"], "ok": False})
    return {"n": len(fermetures), "faits": faits}


def tick(now=None):
    """Un cycle d'enforcement (best-effort, fail-closed). Retourne un récapitulatif.
    Toute exception est absorbée en un état d'erreur (le daemon ne meurt jamais sur
    un tick raté ; systemd le relancerait de toute façon)."""
    now = time.time() if now is None else now
    out = {"ts": int(now), "ok": True}
    try:
        import futures_executor as fe
        recap = fe.enforce_daily_loss(now=now)
        out.update(recap)
        if recap.get("confirme"):
            flat = recap.get("flatten") or {}
            out["note"] = (f"STOP −5 % CONFIRMÉ — {flat.get('soldees', 0)}/"
                           f"{flat.get('tentees', 0)} position(s) soldée(s).")
            _alerter_flatten(flat)
        bk = _enforce_breakeven(fe, now=now)          # §89 : runner protégé après TP1
        if bk and bk.get("n"):
            out["breakeven"] = bk
    except Exception as exc:
        out["ok"] = False
        out["erreur"] = type(exc).__name__
    _write_heartbeat(out)
    return out


def _alerter_flatten(flat):
    """Alerte Telegram APRÈS un flatten (l'exécuteur a déjà alerté du franchissement ;
    ici on rend compte du SOLDE effectif). Best-effort, dédup naturelle (ne s'exécute
    que sur un breach confirmé, lui-même dédupé côté ledger)."""
    if not flat or not flat.get("tentees"):
        return
    try:
        import telegram_notifier as tn
        detail = " · ".join(f"{p['side']} {p['symbol']} ({'ok' if p['executed'] else 'ÉCHEC'})"
                            for p in flat.get("positions", []))
        erreurs = ("  ⚠️ " + " ; ".join(flat["erreurs"])) if flat.get("erreurs") else ""
        tn.send_telegram(
            f"🧯 STOP −5 % — flatten : {flat.get('soldees', 0)}/{flat.get('tentees', 0)} "
            f"position(s) soldée(s). {detail}{erreurs}. Kill-switch armé (aucun nouvel ordre). "
            "Lever : supprimer KILL_SWITCH une fois la cause comprise.")
    except Exception:
        pass


def _install_signal_handlers():
    def _handler(signum, frame):
        _STOP["flag"] = True
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


def run_forever():
    """Boucle daemon : tick toutes FUTURES_GUARDIAN_INTERVAL_S secondes, heartbeat
    systemd entre chaque. S'arrête proprement sur SIGTERM/SIGINT."""
    interval = max(5.0, float(_cfg("FUTURES_GUARDIAN_INTERVAL_S", 20.0)))
    _install_signal_handlers()
    _sd_notify("READY=1")
    print(f"stop_guardian: démarré (intervalle {interval:.0f}s). Enforce stop −5 % "
          "INDÉPENDAMMENT de brain/scan.")
    while not _STOP["flag"]:
        out = tick()
        _sd_notify("WATCHDOG=1")                        # rearme le WatchdogSec de systemd
        _deadman_ping()                                 # dead-man externe (throttle 60s)
        if out.get("confirme"):
            print(f"stop_guardian: {out.get('note')}")
        elif not out.get("ok"):
            print(f"stop_guardian: tick en erreur ({out.get('erreur')}) — on continue.")
        # sommeil FRACTIONNÉ : réagit vite à SIGTERM sans manquer la cadence.
        dormi = 0.0
        while dormi < interval and not _STOP["flag"]:
            time.sleep(min(1.0, interval - dormi))
            dormi += 1.0
    _sd_notify("STOPPING=1")
    print("stop_guardian: arrêt propre (SIGTERM).")


def status():
    """Lecture seule : dernier battement + âge. Aucun effet de bord."""
    try:
        hb = json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8"))
        age = time.time() - float(hb.get("ts", 0))
        print("=== STOP GUARDIAN (état) ===")
        print(f"Dernier battement : il y a {age:.0f}s")
        print(f"Breach            : {hb.get('breach')}  (confirmé: {hb.get('confirme')})")
        if hb.get("note"):
            print(f"Note              : {hb['note']}")
        if not hb.get("ok"):
            print(f"Dernier tick      : ERREUR ({hb.get('erreur')})")
    except Exception:
        print("stop_guardian: aucun battement lisible (jamais démarré ?).")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--status" in argv:
        status()
    elif "--once" in argv:
        out = tick()
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        run_forever()


if __name__ == "__main__":
    main()
