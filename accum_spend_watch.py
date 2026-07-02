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
        STATE_FILE.write_text(json.dumps({"day": int(day)}), encoding="utf-8")
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


def main():
    _watch_spot()
    _watch_futures()
    print("Tripwire lecture/alerte (seule écriture : kill-switch protecteur). VERDICT: SAFE")


if __name__ == "__main__":
    main()
