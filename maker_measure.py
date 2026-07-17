#!/usr/bin/env python3
"""maker_measure.py — MESURE l'effet réel du mode maker (§exec-frais) via les fills.

Classement : SAFE. Lecture seule (fills réels, aucun ordre, aucun secret).

Le mode maker (post-only + repli taker gardé, §exec-frais) n'économise des frais QUE si
le post-only REMPLIT ; sinon il annule et replie en taker (gain ~nul, +latence). Comme
`exec_style` n'est journalisé nulle part, on mesure la VÉRITÉ TERRAIN via `tradeScope`
(maker/taker) des fills Bitget. Le maker ne cible que les OUVERTURES (tradeSide=open) ->
on les isole. On ne mesure JAMAIS avant l'armement (les ouvertures pré-maker sont
forcément taker et dilueraient le taux).

Usage :
  python maker_measure.py [SYMBOL=BTCUSDT] [--days N] [--limit N] [--alert]
    --days N : fenêtre glissante (bornée à l'armement) ; sinon depuis l'armement.
    --alert  : Telegram SEULEMENT si la décision est mûre (assez d'ouvertures ET verdict
               actionnable extend/tune). Sinon silence -> pas de bruit hebdomadaire.
"""
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

MIN_OPENS = 12          # échantillon minimal pour un verdict actionnable (Telegram)
# Armement du maker BTC (.env, §exec-frais 09/07) : borne basse de toute fenêtre de mesure.
MAKER_ARMED_TS = datetime(2026, 7, 9, 10, 24, 22, tzinfo=timezone.utc).timestamp()


def _bps(fee, quote):
    return (fee / quote * 1e4) if quote else 0.0


def _fmt_ts(ts):
    try:
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%m-%d %H:%M")
    except Exception:
        return "?"


def agreger(fills, sym="BTCUSDT", cutoff_ts=None):
    """PURE. Agrège la part maker/taker des OUVERTURES d'un symbole (tradeScope des
    fills). Exclut : fills avant cutoff_ts, autres symboles ; les fermetures sont
    comptées à part (le maker ne cible que les ouvertures). Retourne un dict de mesure."""
    fam = [x for x in fills if str(x.get("symbol") or "").upper() == sym]
    if cutoff_ts is not None:
        fam = [x for x in fam if float(x.get("ts") or 0) >= cutoff_ts]
    if not fam:
        return {"symbol": sym, "n_fills": 0}
    opens = [x for x in fam if x.get("trade_side") == "open"]
    closes = [x for x in fam if x.get("trade_side") == "close"]
    agg = defaultdict(lambda: {"n": 0, "quote": 0.0, "fee": 0.0})
    for x in opens:
        a = agg[(x.get("scope") or "?").lower()]
        a["n"] += 1
        a["quote"] += float(x.get("quote") or 0)
        a["fee"] += float(x.get("fee") or 0)
    mk = agg.get("maker", {"n": 0, "quote": 0.0, "fee": 0.0})
    tk = agg.get("taker", {"n": 0, "quote": 0.0, "fee": 0.0})
    tot = mk["n"] + tk["n"]
    return {
        "symbol": sym, "n_fills": len(fam),
        "fenetre": f"{_fmt_ts(fam[0]['ts'])} → {_fmt_ts(fam[-1]['ts'])} UTC",
        "opens": len(opens), "closes": len(closes),
        "open_maker_n": mk["n"], "open_taker_n": tk["n"],
        "autres": {k: v["n"] for k, v in agg.items() if k not in ("maker", "taker")},
        "maker_fill_rate": (mk["n"] / tot) if tot else None,
        "bps_maker": _bps(mk["fee"], mk["quote"]),
        "bps_taker": _bps(tk["fee"], tk["quote"]),
        "bps_close": _bps(sum(float(x.get("fee") or 0) for x in closes),
                          sum(float(x.get("quote") or 0) for x in closes)),
    }


def mesure(sym="BTCUSDT", limit=300, since_days=None):
    """I/O : récupère les fills réels et agrège (fenêtre bornée à l'armement maker)."""
    import trade_forensics as tf
    fills = tf.charger_fills(limit=limit)
    cutoff = MAKER_ARMED_TS
    if since_days:
        cutoff = max(cutoff, time.time() - float(since_days) * 86400.0)
    return agreger(fills, sym=sym, cutoff_ts=cutoff)


def verdict(r):
    """PURE. (clef, message court). clef ∈ {novol, building, extend, tune, mixte}.
    Actionnable (extend/tune) seulement avec ≥ MIN_OPENS ouvertures post-armement."""
    if r.get("n_fills", 0) == 0:
        return "novol", f"maker {r.get('symbol', '?')} : aucun fill dans la fenêtre."
    tot = r["open_maker_n"] + r["open_taker_n"]
    rate = r["maker_fill_rate"]
    base = (f"maker {r['symbol']} (depuis armement 09/07) : "
            f"fill {0 if rate is None else round(rate * 100)}% sur {tot} ouvertures · "
            f"{r['bps_maker']:.1f} bps maker vs {r['bps_taker']:.1f} taker")
    if tot < MIN_OPENS:
        return "building", base + f" — échantillon en construction (<{MIN_OPENS}), silence."
    eco = r["bps_taker"] - r["bps_maker"]
    if rate >= 0.5 and eco > 0.5:
        return "extend", ("📉 " + base + f" → maker FIABLE (−{eco:.1f} bps). "
                          "Prêt à étendre : FUTURES_MAKER_SYMBOLS=BTCUSDT,ETHUSDT.")
    if rate < 0.25:
        return "tune", ("📉 " + base + " → post-only remplit PEU (replie en taker, gain ~nul). "
                        "Régler FUTURES_MAKER_WAIT_S / le prix posté, ou rester taker.")
    return "mixte", "📉 " + base + " → signal mixte, re-mesurer."


def _telegram(msg):
    try:
        import telegram_notifier as tn
        return bool(tn.send_telegram_message(msg))
    except Exception:
        return False


def _opt(args, flag, default=None):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            return args[i + 1]
    return default


def main():
    args = sys.argv[1:]
    alert = "--alert" in args
    days = _opt(args, "--days")
    days = int(days) if days else None
    limit = int(_opt(args, "--limit", "300"))
    consumed = {_opt(args, "--days"), _opt(args, "--limit")}
    positional = [a for a in args if not a.startswith("--") and a not in consumed]
    sym = (positional[0] if positional else "BTCUSDT").upper()

    r = mesure(sym, limit, since_days=days)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"=== MESURE MODE MAKER — {sym} · {stamp} (lecture seule) ===")
    if r.get("n_fills", 0) == 0:
        print("aucun fill pour ce symbole dans la fenêtre.")
        return 0
    print(f"fenêtre : {r['fenetre']}  ·  {r['n_fills']} fills "
          f"({r['opens']} ouvertures / {r['closes']} fermetures)")
    print("OUVERTURES (le maker ne cible QUE les opens) :")
    print(f"  maker : {r['open_maker_n']:>3}  @ {r['bps_maker']:.2f} bps")
    print(f"  taker : {r['open_taker_n']:>3}  @ {r['bps_taker']:.2f} bps")
    if r["autres"]:
        print(f"  autres/scope inconnu : {r['autres']}")
    print(f"FERMETURES (taker par conception) : {r['bps_close']:.2f} bps")
    key, msg = verdict(r)
    print(f"VERDICT[{key}] : {msg}")
    if alert and key in ("extend", "tune"):
        print("[telegram]", _telegram(msg))
    elif alert:
        print("[telegram] silencieux (non actionnable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
