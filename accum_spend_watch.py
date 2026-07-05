"""
accum_spend_watch.py — TRIPWIRE horaire : depense spot quotidienne + stop de perte futures.

Classement : SAFE. AUCUN ordre, AUCUNE cle. Deux verifications par passage :
  1. SPOT : si la depense reelle du jour depasse la PROMESSE documentee
     (ACCUM_DAILY_PROMISE_USDT = 5 $/j), ALERTE Telegram — meme si le cap effectif
     l'a autorisee. Observe et signale, ne corrige rien.
  2. FUTURES (§45) : verifie PROACTIVEMENT le stop de perte journalier
     (futures_executor.daily_loss_breach) — sans ce passage horaire, le stop ne
     serait evalue qu'au moment d'un ordre : une equity qui plonge avec une
     position OUVERTE et aucune tentative d'ordre n'armerait pas le kill-switch.
     En cas de franchissement, daily_loss_breach ARME le kill-switch (ecriture
     protectrice, dedup d'alerte 1/jour dans le ledger executeur).

Dedup spot : alerte AU PLUS une fois par jour UTC (etat dans .accum_spend_alert.json,
gitignored) pour ne pas spammer a chaque passage horaire du timer.
"""

import json
import time
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / ".accum_spend_alert.json"


def _last_alert_day():
    try:
        return int(json.loads(STATE_FILE.read_text(encoding="utf-8")).get("day", -1))
    except Exception:
        return -1


def _mark_alert_day(day):
    try:
        try:
            st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            st = {}
        st["day"] = int(day)                       # fusion : ne pas écraser runway_day
        STATE_FILE.write_text(json.dumps(st), encoding="utf-8")
    except Exception:
        pass


def _watch_spot():
    try:
        import spot_executor as se
        breach, spent, promise = se.daily_spend_breach()
    except Exception as exc:
        print(f"accum_spend_watch: spot indisponible ({type(exc).__name__}).")
        return
    if not breach:
        print(f"accum_spend_watch: dépense du jour {spent}$ <= promesse {promise}$/j. "
              f"Aucun dépassement.")
        return
    day = int(time.time() // 86400)
    if _last_alert_day() == day:
        print(f"accum_spend_watch: dépassement {spent}$ déjà alerté aujourd'hui (dédup). Silencieux.")
        return
    msg = (f"⚠️ Dépense spot RÉELLE du jour = {spent}$ > promesse {promise}$/j. "
           f"Le cap effectif l'a autorisée (cap possiblement relevé via variable d'env). "
           f"À vérifier — la promesse documentée est {promise}$/jour.")
    try:
        import telegram_notifier as tn
        tn.send_telegram_message(msg)
    except Exception:
        pass
    _mark_alert_day(day)
    print("accum_spend_watch: ALERTE ->", msg)


def _watch_runway():
    """Autonomie du DCA (audit P2) : si l'USDT spot LIBRE passe sous le seuil
    (~1 semaine d'achats), alerte de réapprovisionnement — sinon l'accumulation
    s'arrêterait en silence (refus de garde), découvert des jours plus tard.
    Dédup : 1 alerte/jour UTC (même état que l'alerte de dépense, clé dédiée)."""
    try:
        import spot_executor as se
        from config_utils import cfg as _cfg
        libre = se._spot_free_usdt()
        seuil = float(_cfg("ACCUM_RUNWAY_ALERT_USDT", 15.0))
        if libre is None:
            print("accum_spend_watch: USDT spot libre illisible (runway non évalué).")
            return
        if libre >= seuil:
            print(f"accum_spend_watch: runway spot OK ({libre:.2f}$ libres >= seuil {seuil}$).")
            return
        import json as _json
        day = int(time.time() // 86400)
        try:
            st = _json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            st = {}
        if int(st.get("runway_day", -1)) == day:
            print(f"accum_spend_watch: runway bas ({libre:.2f}$) déjà alerté aujourd'hui.")
            return
        try:
            import telegram_notifier as tn
            tn.send_telegram_message(
                f"⛽ RÉAPPROVISIONNEMENT : il ne reste que {libre:.2f} USDT libres sur le "
                f"spot (seuil {seuil}$). L'accumulation quotidienne (2–5 $/j) s'arrêtera "
                f"proprement quand le solde sera insuffisant — re-provisionner pour continuer.")
        except Exception:
            pass
        st["runway_day"] = day
        try:
            STATE_FILE.write_text(_json.dumps(st), encoding="utf-8")
        except Exception:
            pass
        print(f"accum_spend_watch: ALERTE runway spot bas ({libre:.2f}$ < {seuil}$).")
    except Exception as exc:
        print(f"accum_spend_watch: runway indisponible ({type(exc).__name__}).")


def _watch_futures():
    """Stop de perte journalier futures évalué PROACTIVEMENT (pas seulement à l'ordre) :
    equity qui plonge avec position ouverte + aucune tentative d'ordre -> le kill-switch
    s'arme quand même (via daily_loss_breach, dédup d'alerte 1/jour)."""
    try:
        import futures_executor as fe
        breach = fe.daily_loss_breach()
        print("accum_spend_watch: stop journalier futures "
              + ("FRANCHI — kill-switch armé." if breach else "ok."))
    except Exception as exc:
        print(f"accum_spend_watch: futures indisponible ({type(exc).__name__}).")


def positions_pres_liquidation(rows, seuil_pct=15.0):
    """PUR. Positions dont le prix de LIQUIDATION est à moins de seuil_pct du mark.
    En marge croisée (compte union), le stop de −5 % protège du drawdown mais rien
    ne surveillait la distance de liquidation quand plusieurs positions §47
    s'empilent. Lignes sans liquidationPrice/markPrice ignorées (fail-safe)."""
    from numeric_utils import safe_float
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        mark = safe_float(r.get("markPrice"))
        liq = safe_float(r.get("liquidationPrice"))
        if not mark or not liq or mark <= 0 or liq <= 0:
            continue
        dist = abs(mark - liq) / mark * 100.0
        if dist < float(seuil_pct):
            out.append({"symbol": str(r.get("symbol", "")).upper(),
                        "side": str(r.get("holdSide", "")).lower(),
                        "dist_pct": round(dist, 2)})
    return out


def _watch_marge():
    """Tripwire de MARGE : alerte si une position est à < N % de sa liquidation
    (répétée à chaque passage horaire tant que le danger persiste — un vrai danger
    de liquidation mérite le bruit). Lecture seule."""
    try:
        import futures_executor as fe
        from config_utils import cfg as _cfg
        rows = fe.positions_ouvertes()
        if rows is None:
            print("accum_spend_watch: marge — positions illisibles (watchdog couvre).")
            return
        seuil = float(_cfg("FUTURES_MARGE_ALERTE_DIST_PCT", 15.0))
        danger = positions_pres_liquidation(rows, seuil)
        if danger:
            detail = " · ".join(f"{d['side']} {d['symbol']} à {d['dist_pct']}% de liq."
                                for d in danger)
            print(f"accum_spend_watch: ALERTE MARGE — {detail}")
            try:
                import telegram_notifier as tn
                tn.send_telegram(f"🚨 MARGE : {detail} (seuil {seuil}%). Réduire ou "
                                 f"couper : touch KILL_SWITCH · voir /futures")
            except Exception:
                pass
        else:
            print(f"accum_spend_watch: marge ok ({len(rows)} position(s), "
                  f"toutes à > {seuil}% de la liquidation).")
    except Exception as exc:
        print(f"accum_spend_watch: marge indisponible ({type(exc).__name__}).")


def main():
    _watch_spot()
    _watch_runway()
    _watch_futures()
    _watch_marge()
    print("Tripwire lecture/alerte (seule écriture : kill-switch protecteur). VERDICT: SAFE")


if __name__ == "__main__":
    main()
