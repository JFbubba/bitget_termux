"""
microstructure_watch.py — check PLANIFIE de l'edge microstructure (chemin 2).

Classement : SAFE. Lecture seule, AUCUN ordre, AUCUNE cle. Lance history_report() sur
l'historique accumule par le collecteur (book_collector) ; si une feature montre un IC
SIGNIFICATIF (|ic_t| >= seuil ET echantillon suffisant), envoie une ALERTE Telegram
(advisory). Sinon silencieux. Le verdict s'accumule DANS LE TEMPS.

⚠️ Une alerte ne PROMEUT RIEN : c'est un "viens regarder de plus pres". Toute promotion
vers le reel exige la discipline honnete complete (deflation multiple-testing + OOS + GO
explicite du proprietaire). Le t-stat poole ici ne corrige pas la correlation transversale
(n potentiellement gonfle) -> seuil volontairement HAUT, et c'est un signal de tri, pas un edge prouve.
"""

MIN_N = 500          # echantillon minimal (paires feature->rendement) avant de juger
IC_T_ALERT = 3.0     # t-stat eleve et conservateur (pas un seuil de promotion)


def assess(report, min_n=MIN_N, ic_t_alert=IC_T_ALERT):
    """PUR : depuis un history_report, decide s'il faut alerter. Retourne (alert, lignes)."""
    hits = []
    for feat, m in (report.get("edge") or {}).items():
        try:
            n = int(m.get("n", 0) or 0)
            ic_t = float(m.get("ic_t", 0) or 0)
        except Exception:
            continue
        if n >= int(min_n) and abs(ic_t) >= float(ic_t_alert):
            hits.append(f"{feat}: IC={m.get('ic')} t={ic_t} (n={n})")
    return (bool(hits), hits)


def main():
    try:
        import microstructure as ms
        rep = ms.history_report()
    except Exception as exc:
        print(f"microstructure_watch: indisponible ({type(exc).__name__}). VERDICT: SAFE")
        return
    alert, hits = assess(rep)
    n = rep.get("n_records", 0)
    if alert:
        msg = ("🔬 Microstructure — signal d'edge À VÉRIFIER (advisory, NON promu) :\n"
               + "\n".join(hits)
               + "\n→ exige déflation multiple-testing + OOS + GO explicite avant toute promotion.")
        try:
            import telegram_notifier as tn
            tn.send_telegram_message(msg)
        except Exception:
            pass
        print("microstructure_watch: ALERTE envoyée ->", hits)
    else:
        print(f"microstructure_watch: {n} enreg. accumulés, aucun edge significatif "
              f"(seuils |t|>={IC_T_ALERT}, n>={MIN_N}). Accumulation en cours. VERDICT: SAFE")


if __name__ == "__main__":
    main()
