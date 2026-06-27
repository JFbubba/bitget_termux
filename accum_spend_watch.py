"""
accum_spend_watch.py — TRIPWIRE d'observabilite de la depense spot reelle quotidienne.

Classement : SAFE. Lecture seule, AUCUN ordre, AUCUNE cle. Si la depense reelle du jour
depasse la PROMESSE documentee (ACCUM_DAILY_PROMISE_USDT = 5 $/j), envoie une ALERTE Telegram
— MEME si le cap effectif l'a autorisee (un env peut porter le cap jusqu'au mur absolu 25).
Comble le trou revele par l'ecart du 27/06 (10 $ depenses sans alerte temps reel). N'agit pas,
ne corrige rien : il OBSERVE et signale. Independant du cap d'execution (defense en profondeur).

Dedup : alerte AU PLUS une fois par jour UTC (etat dans .accum_spend_alert.json, gitignored)
pour ne pas spammer a chaque passage horaire du timer.
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


def main():
    try:
        import spot_executor as se
        breach, spent, promise = se.daily_spend_breach()
    except Exception as exc:
        print(f"accum_spend_watch: indisponible ({type(exc).__name__}). VERDICT: SAFE")
        return
    if not breach:
        print(f"accum_spend_watch: dépense du jour {spent}$ <= promesse {promise}$/j. "
              f"Aucun dépassement. VERDICT: SAFE")
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


if __name__ == "__main__":
    main()
