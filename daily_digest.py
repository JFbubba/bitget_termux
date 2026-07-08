"""
daily_digest.py — RAPPORT QUOTIDIEN unifié (§88). SAFE, lecture seule + Telegram.

Chaque matin (cron 07:00), UN message : PnL réel des dernières 24 h par méthode
(forensique des fills), allers-retours de la veille avec leur MFE/MAE, equity et
stop, positions ouvertes, actions des gestionnaires (alt-carry, liquidité), état
des voix, tableau des promotions, santé de l'apprentissage. Le propriétaire ne
devrait JAMAIS avoir à demander « pourquoi je ne vois pas X » : X est ici.

CLI : python daily_digest.py [--send]   (sans --send : imprime seulement)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _tail_jsonl(path, n=1):
    try:
        lignes = [l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
        return [json.loads(l) for l in lignes[-n:]]
    except Exception:
        return []


def build_message():
    """Compose le digest (best-effort par bloc — un bloc qui casse ne prive pas des autres)."""
    L = [time.strftime("📰 DIGEST QUOTIDIEN — %d/%m/%Y %H:%M UTC", time.gmtime())]

    try:                                            # — trades réels 24 h (forensique) —
        import trade_forensics as tf
        s = tf.snapshot(24)
        pnl = sum(t.get("pnl_usdt") or 0 for t in s["trips"])
        L.append(f"\n⚔️ FUTURES 24 h : {len(s['trips'])} aller(s)-retour(s) · PnL net {pnl:+.4f} $"
                 + (f" · ⚠️ {len(s['non_remplis'])} ordre(s) IOC non rempli(s)" if s.get("non_remplis") else ""))
        for t in s["trips"][:6]:
            ex = t.get("excursion") or {}
            L.append(f"  {t['symbol'].replace('USDT', ''):5s} {t['side']:5s} {t['duree_min']:6.1f} min"
                     f" · {t['pnl_usdt']:+.4f} $"
                     + (f" · R {t['r_realise']:+.2f}" if t.get("r_realise") is not None else "")
                     + (f" · MFE {ex['mfe_r']:+.2f}R" if ex.get("mfe_r") is not None else ""))
        if s.get("slippage_median_bps") is not None:
            L.append(f"  slippage médian {s['slippage_median_bps']:+.1f} bps")
        att = s.get("attribution") or {}
        if att:
            L.append("  par méthode : " + " · ".join(
                f"{k} {v['pnl']:+.3f}$ ({v['n']})" for k, v in sorted(att.items())))
    except Exception as e:
        L.append(f"\n⚔️ FUTURES : forensique indisponible ({type(e).__name__})")

    try:                                            # — equity, stop, positions —
        import futures_executor as fe
        dd = fe.drawdown_status() or {}
        L.append(f"\n💰 Equity {dd.get('equity')} $ · MDD {dd.get('dd_pct')} %"
                 + (" · ⛔ HALTE DRAWDOWN" if dd.get("halted") else ""))
        if (ROOT / "KILL_SWITCH").exists():
            L.append("🔴 KILL_SWITCH ACTIF")
    except Exception:
        pass

    try:                                            # — gestionnaires —
        ac = _tail_jsonl(ROOT / ".alt_carry_journal.jsonl", 1)
        if ac:
            d = ac[0].get("decision") or {}
            L.append(f"\n🌾 Alt-carry : {str(d.get('action', 'rien')).upper()} — {d.get('raison', '')[:90]}")
        lq = _tail_jsonl(ROOT / ".liquidity_journal.jsonl", 1)
        if lq:
            d = lq[0].get("decision") or {}
            spot, fut = lq[0].get("spot_usdt"), lq[0].get("fut_usdt")
            L.append(f"💧 Liquidité : {str(d.get('action', 'rien')).upper()}"
                     f" (spot {round(spot, 2) if spot is not None else '?'} $"
                     f" · fut {round(fut, 2) if fut is not None else '?'} $)")
    except Exception:
        pass

    try:                                            # — promotions (barres) —
        import promotion_board as pb
        s = pb.snapshot()
        L.append("\n🎓 Promotions :")
        for i in s["items"]:
            etat = "✅ PRÊT" if i.get("pret") else (
                f"{int((i.get('progression') or 0) * 100)} %" if i.get("progression") is not None else "—")
            L.append(f"  [{etat}] {i['nom']} — {i['etat'][:70]}")
    except Exception:
        pass

    try:                                            # — santé apprentissage —
        import learning_health as lh
        s = lh.snapshot()
        L.append(f"\n🧠 Apprentissage : {'SAIN' if s.get('healthy') else '⚠️ ALERTE'} — {s.get('note', '')[:100]}")
    except Exception:
        pass

    try:                                            # — collecte de données (§101) —
        from data_collector import digest_bloc
        L.extend(digest_bloc.bloc())
    except Exception:
        pass
    L.append("\n(lecture seule — détails : dashboard & rapports CLI)")
    return "\n".join(L)


def main():
    import sys
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    msg = build_message()
    try:
        (ROOT / ".daily_digest_stamp").write_text(str(int(time.time())), encoding="utf-8")
    except Exception:
        pass
    print(msg)
    if "--send" in sys.argv[1:]:
        try:
            import telegram_notifier as tn
            tn.send_telegram(msg)
            print("\n[envoyé sur Telegram]")
        except Exception as e:
            print(f"\n[envoi Telegram impossible : {type(e).__name__}]")
    print("VERDICT: SAFE")


if __name__ == "__main__":
    main()
