"""
bitget_execute.py — noyau d'exécution BORNÉ partagé (gating · kill-switch · caps · DRY).

Classement : SAFE par construction. Ce noyau NE contient AUCUN mot-clé d'exécution
(le runner est générique : l'appelant passe la liste d'arguments `bgc`). Il centralise
UNE fois la logique de sûreté que les exécuteurs de surface réutilisent :

  • GATING défaut OFF : chaque surface a son verrou LIVE (env > config, défaut False).
    Tant qu'il est OFF, `execute()` refuse -> rien ne part.
  • KILL-SWITCH fail-CLOSED : si l'état ne peut être lu, on BLOQUE (sécurité argent).
  • CAPS DURS par opération + journaliers, avec un PLAFOND ABSOLU en dur qu'aucun
    env/config ne peut dépasser (defense-in-depth, comme spot_executor §45).
  • DRY PAR DÉFAUT : `run(confirm=False)` imprime la commande et n'exécute RIEN.
    Une opération réelle exige confirm=True ET toutes les gardes vertes.
  • Journal RÉEL partagé (`trading_real_ledger.json`) pour les caps journaliers.

⚠️ Les RETRAITS sortants restent INTERDITS partout (clé Bitget = Trade-only) : aucun
exécuteur n'a le droit de contenir ce mot-clé (vérifié par security_agent). Les murs
argent de `futures_executor.guards()` restent par ailleurs absolus et indépendants.
"""
import json
import os
import time
from pathlib import Path

from config_utils import cfg as _cfg

LEDGER = Path(__file__).resolve().parent / "trading_real_ledger.json"
# Sentinel « journal non fiable » (§revue chemin argent — Thème 3, chemin exécution) : posé
# quand une écriture de journal échoue -> ledger_ok() fail-closed (surfaces §67 SUSPENDUES)
# jusqu'à réconciliation manuelle par le propriétaire (retrait du fichier).
LEDGER_UNRELIABLE = Path(__file__).resolve().parent / "trading_ledger_unreliable.flag"


def gate(flag_name):
    """Verrou LIVE d'une surface : env PRIORITAIRE > config > défaut OFF. Tant qu'il est
    False, l'exécuteur refuse toute opération réelle (comportement inchangé du bot)."""
    v = os.getenv(flag_name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg(flag_name, False))


def kill_active(kill=None):
    """Kill-switch, fail-CLOSED : si l'état ne peut PAS être déterminé, on considère le
    kill ACTIF (on bloque). L'argent ne prend pas le risque d'un état inconnu."""
    if kill is not None:
        return bool(kill)
    try:
        import risk_manager
        return bool(risk_manager.kill_switch_active())
    except Exception:
        return True                       # inconnu -> on BLOQUE (plus strict que la lecture seule)


def limit(name, fallback):
    """Plafond numérique : env > config > défaut. PUR (lit l'env)."""
    v = os.getenv(name)
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    return float(_cfg(name, fallback))


def capped(name, fallback, absolute):
    """Plafond EFFECTIF = min(env>config>défaut, mur ABSOLU en dur). L'absolu ne peut
    JAMAIS être dépassé par env/config. Relever un palier = augmenter l'env SOUS l'absolu ;
    dépasser l'absolu exige une revue + commit (comme §45)."""
    return min(limit(name, fallback), float(absolute))


# ---------- journal RÉEL partagé (caps journaliers) ----------

def _load():
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {"ops": []}


def ledger_ok():
    """False si le journal RÉEL EXISTE mais est illisible/corrompu : la dépense du jour est
    alors invérifiable -> les gardes doivent BLOQUER (fail-closed) au lieu de repartir de 0.
    Fichier ABSENT = 0 engagé légitime -> True. (§revue chemin argent — Thème 3)
    Fail-closed AUSSI si le sentinel « journal non fiable » est présent (écriture ratée)."""
    try:
        if LEDGER_UNRELIABLE.exists():
            return False                # une écriture de journal a échoué -> engagement non fiable -> BLOQUE
    except Exception:
        return False
    try:
        if not LEDGER.exists():
            return True
        json.loads(LEDGER.read_text(encoding="utf-8"))
        return True
    except Exception:
        return False


def _mark_ledger_unreliable():
    """Pose le sentinel -> ledger_ok() fail-closed (surfaces §67 SUSPENDUES) jusqu'à
    réconciliation manuelle. Best-effort (sans sentinel, l'ALERTE reste le filet)."""
    try:
        LEDGER_UNRELIABLE.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass


def _alert(message):
    """Alerte Telegram best-effort — jamais bloquante, jamais d'exception propagée."""
    try:
        import telegram_notifier as tn
        tn.send_telegram(message)
    except Exception:
        pass


def today_spent(surface, now=None, ledger=None):
    """Total RÉEL engagé aujourd'hui sur une surface (USDT). PUR si ledger injecté."""
    now = time.time() if now is None else now
    day = int(now // 86400)
    led = ledger if ledger is not None else _load()
    return round(sum(float(o.get("amount_usdt", 0)) for o in led.get("ops", [])
                     if o.get("surface") == surface and int(float(o.get("ts", 0)) // 86400) == day), 2)


def record(surface, amount_usdt, oid, meta=None, now=None):
    """Journalise une opération RÉELLE exécutée (best-effort, jamais bloquant)."""
    now = time.time() if now is None else now
    led = _load()
    row = {"ts": now, "surface": surface, "amount_usdt": round(float(amount_usdt or 0), 6), "clientOid": oid}
    for k, v in (meta or {}).items():
        if isinstance(v, (int, float, str)) and k not in row:
            row[k] = v
    led.setdefault("ops", []).append(row)
    led["ops"] = led["ops"][-2000:]
    try:
        tmp = Path(str(LEDGER) + ".tmp")
        tmp.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, LEDGER)                     # ATOMIQUE : jamais de JSON à moitié écrit
        return True
    except Exception:
        return False                                # écriture ratée -> l'appelant alerte + fail-closed


# ---------- gardes communes (pures si l'état est injecté) ----------

def guard(surface, live_flag, amount_usdt, per_op_cap, daily_cap,
          live=None, kill=None, spent=None, balance=None, extra_reasons=None):
    """Vérifie TOUTES les gardes communes avant une opération réelle. Retourne
    (ok, reasons). PUR si live/kill/spent/balance sont injectés.

    - live_flag : nom du verrou LIVE de la surface (ex. 'SPOT_TRADE_LIVE') ;
    - per_op_cap / daily_cap : plafonds EFFECTIFS déjà résolus (via capped()) ;
    - extra_reasons : raisons supplémentaires spécifiques à la surface (liste)."""
    reasons = list(extra_reasons or [])
    on = gate(live_flag) if live is None else bool(live)
    if not on:
        reasons.append(f"{live_flag}=False (verrou LIVE coupé, défaut OFF)")
    if kill_active(kill):
        reasons.append("kill_switch actif (ou état illisible)")
    try:
        amt = float(amount_usdt or 0)
    except (TypeError, ValueError):
        reasons.append("montant invalide (non numérique)")
        return (False, reasons)
    if amt <= 0:
        reasons.append("montant ≤ 0")
    if amt > per_op_cap:
        reasons.append(f"montant {amt} > plafond/opération {per_op_cap}")
    if spent is None and not ledger_ok():
        # Journal présent mais corrompu -> engagement du jour invérifiable -> on BLOQUE au
        # lieu de repartir de 0 (ce qui ré-ouvrirait le cap). (§revue chemin argent — Thème 3)
        reasons.append("journal réel illisible/corrompu — opération bloquée (fail-closed)")
    sp = today_spent(surface) if spent is None else float(spent)
    if sp + amt > daily_cap:
        reasons.append(f"plafond journalier dépassé ({sp}+{amt} > {daily_cap})")
    if balance is not None and amt > float(balance):
        reasons.append(f"montant {amt} > solde disponible {balance}")
    return (not reasons, reasons)


# ---------- runner générique (DRY par défaut) ----------

def _run_bgc(args, runner=None):
    """Lance `bgc <args>` (écriture). runner injectable pour les tests. None si l'Agent
    Hub est indisponible. Concatène stdout+stderr pour ne rien perdre des erreurs."""
    if runner is not None:
        return runner(args)
    try:
        import bitget_hub_bridge as hub
        if not hub.available():
            return None
        import subprocess
        p = subprocess.run(["bgc", *args], capture_output=True, text=True,
                           timeout=30, env=hub._hub_env())
        return ((p.stdout or "") + (p.stderr or "")).strip() or None
    except Exception:
        return None


def _ok_response(out):
    """Heuristique de succès d'une réponse Bitget (mêmes règles que spot_executor)."""
    compact = (out or "").replace(" ", "").lower()
    return (bool(out) and '"ok":false' not in compact and "error" not in compact
            and ("orderid" in compact or '"data"' in compact or '"ok":true'
                 in compact or '"code":"00000"' in compact))


def run(args, ok, reasons, surface, amount_usdt, oid, confirm=False, runner=None, meta=None):
    """Point d'exécution BORNÉ commun. Si les gardes échouent -> refus. Sinon, DRY par
    défaut (aperçu, rien exécuté) ; confirm=True -> exécute réellement via bgc, journalise.
    Retourne un dict de résultat homogène pour toutes les surfaces."""
    preview = "bgc " + " ".join(str(a) for a in args)
    if not ok:
        return {"ok": False, "executed": False, "reasons": reasons, "preview": preview}
    if not confirm:
        return {"ok": True, "executed": False, "dry": True, "preview": preview,
                "note": "DRY — vérifie la commande puis relance avec --confirm pour le RÉEL"}
    out = _run_bgc(args, runner=runner)
    success = _ok_response(out)
    result = {"ok": True, "executed": success, "preview": preview, "response": out, "clientOid": oid}
    if success:
        if not record(surface, amount_usdt, oid, meta=meta):     # Thème 3 sous-item 1 : journal NON écrit
            _mark_ledger_unreliable()                            # -> ledger_ok() fail-closed (§67 SUSPENDUES)
            result["ledger_write_failed"] = True
            _alert(f"🛑 Journal §67 ({surface}) NON écrit (oid {oid} · {amount_usdt}$) — surfaces "
                   "bornées SUSPENDUES (fail-closed) jusqu'à réconciliation (retirer le sentinel).")
    elif not out:                                                # Thème 3 sous-item 2 : réponse PERDUE/vide
        result["ambiguous"] = True                               # l'op a PEUT-ÊTRE eu lieu -> pas de silence
        _alert(f"⚠️ Opération §67 ({surface}) AMBIGUË (réponse perdue) oid {oid} · {amount_usdt}$ — "
               "vérifier l'état réel (possible opération non journalisée).")
    return result


def new_oid(prefix):
    """clientOid idempotent horodaté."""
    return f"{prefix}{int(time.time() * 1000)}"
