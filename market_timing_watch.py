"""
market_timing_watch.py — accumulation + check de l'edge TEMPOREL macro/sentiment (§39).

Classement : SAFE. Lecture seule, AUCUN ordre. Chaque jour : (1) journalise le relevé
(vote macro/sentiment + prix marché), (2) évalue l'IC temporelle ; alerte Telegram SEULEMENT
si un agent marché-large montre un edge temporel SIGNIFICATIF (|ic_t|>=seuil ET n>=min jours),
sinon silencieux. Dédup hebdomadaire. Ne promeut RIEN : toute promotion = déflation + OOS + GO.
"""

import json
import time
from pathlib import Path

MIN_N = 30           # jours minimum avant de juger (macro/F&G bougent lentement)
IC_T_ALERT = 2.5     # t-stat eleve et conservateur
STATE_FILE = Path(__file__).resolve().parent / ".market_timing_alert.json"


def _last_alert_week():
    try:
        return int(json.loads(STATE_FILE.read_text(encoding="utf-8")).get("week", -1))
    except Exception:
        return -1


def _mark_alert_week(week):
    try:
        STATE_FILE.write_text(json.dumps({"week": int(week)}), encoding="utf-8")
    except Exception:
        pass


def main():
    try:
        import market_timing as mt
        mt.log_daily()                       # accumule le releve du jour (throttle ~20h)
        rep = mt.report(horizon=5)
    except Exception as exc:
        print(f"market_timing_watch: indisponible ({type(exc).__name__}). VERDICT: SAFE")
        return
    hits = []
    for a, m in (rep.get("edge") or {}).items():
        try:
            n = int(m.get("n", 0) or 0)
            ic_t = float(m.get("ic_t", 0) or 0)
        except Exception:
            continue
        if n >= MIN_N and abs(ic_t) >= IC_T_ALERT:
            hits.append(f"{a}: IC={m.get('ic')} t={ic_t} (n={n}j, h={m.get('horizon_days')}j)")
    n_rec = rep.get("n_records", 0)
    if not hits:
        print(f"market_timing_watch: {n_rec} jours accumulés ({rep.get('span_days')}j), "
              f"aucun edge temporel significatif (|t|>={IC_T_ALERT}, n>={MIN_N}). VERDICT: SAFE")
        return
    week = int(time.time() // 86400 // 7)
    if _last_alert_week() == week:
        print(f"market_timing_watch: edge temporel déjà alerté cette semaine (dédup). {hits}")
        return
    msg = ("📈 Market-timing (macro/sentiment) — edge TEMPOREL À VÉRIFIER (advisory, NON promu) :\n"
           + "\n".join(hits)
           + "\n→ exige déflation + OOS + GO explicite avant toute promotion.")
    try:
        import telegram_notifier as tn
        tn.send_telegram_message(msg)
    except Exception:
        pass
    _mark_alert_week(week)
    print("market_timing_watch: ALERTE ->", hits)


if __name__ == "__main__":
    main()
