#!/usr/bin/env python3
"""bitget_watch.py — VEILLE autonome des faits Bitget autoritatifs (chantier #1). SAFE, lecture seule.

Un « agent Bitget-en-fond » : à chaque cycle (cron), lit les faits Bitget AUTORITATIFS via l'API
authentifiée (JAMAIS de scraping — bloqué + interdit, règle proprio) + les lecteurs read-only
existants (fee_rates, bitget_market_extras), les DIFFE contre une baseline, et sur CHANGEMENT :
alerte Telegram + journalise + MAPPE le fait au module concerné avec une recommandation.

FRONTIÈRE DE SÉCURITÉ (comme backlog_review) : SURFACE et RECOMMANDE seulement. N'édite JAMAIS un
agent / du code, ne passe AUCUN ordre, ne scrape RIEN. L'action (recalibrer carry, exclure un
symbole…) reste un acte RÉVISÉ qui passe les 3 portes. Certains faits sont DÉJÀ auto-injectés
(fee_rates fetch le trade-rate live ; universe filtre symbolStatus) — la veille les CONFIRME et
alerte surtout sur les non-auto-consommés (intervalle de funding, réservoir BGB, delisting).

CLI :
    python bitget_watch.py            # snapshot + diff vs baseline (lecture seule)
    python bitget_watch.py --alert    # + Telegram + journal + avance la baseline (pour cron)
    python bitget_watch.py --show     # snapshot courant brut
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, ".bitget_watch_state.json")
JOURNAL = os.path.join(ROOT, ".bitget_watch_journal.jsonl")
WATCH_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # ensemble borné (limite les appels API)

# fait -> (module concerné, recommandation) : l'INJECTION ciblée (surface, jamais auto-édition).
IMPACT = {
    "spot_fee_bps": ("accumulation/listing_hype/exit_calibration",
                     "recalibrer les frais spot (auto via fee_rates ; alerte de vigilance)"),
    "mix_maker_bps": ("carry/exit_calibration/futures_auto", "recalibrer les frais futures maker"),
    "mix_taker_bps": ("carry/exit_calibration/futures_auto", "recalibrer les frais futures taker"),
    "bgb_effective": ("fee_rates", "état de la remise BGB spot a changé"),
    "bgb_spot_balance_low": ("spot_trader (refuel)",
                             "REFUEL BGB : réservoir spot sous la poussière -> remise 8->10 bps perdue"),
    "bgb_crossed_margin": ("marge croisée (alt_carry) / remise BGB",
                           "variation du réservoir BGB marge (BAISSE = remise -20% ACTIVE, consommée par les frais)"),
    "bgb_crossed_low": ("refuel BGB marge (§67 spot->crossed_margin)",
                        "REFUEL BGB MARGE : réservoir croisé sous poussière -> remise marge -20% perdue"),
    "fund_interval_h": ("carry/funding_fade", "intervalle de funding changé -> recalibrer le carry"),
    "status": ("universe", "symbolStatus != normal -> exclure ce symbole (delisting/ST)"),
    "min_notional_usdt": ("futures_auto (faisabilité)", "notional minimal du contrat changé"),
    "max_lever": ("mandate", "levier max du contrat changé (le mur x5 reste absolu)"),
}


def snapshot():
    """Faits Bitget autoritatifs (API read-only, fail-safe champ par champ -> {} si tout tombe)."""
    snap = {}
    try:
        import fee_rates as fr
        snap["spot_fee_bps"] = round(fr.spot_fee_bps(), 3)
        mix = fr.trade_rate("mix")
        snap["mix_maker_bps"] = round(float(mix.get("maker") or 0) * 1e4, 3)
        snap["mix_taker_bps"] = round(float(mix.get("taker") or 0) * 1e4, 3)
        snap["bgb_effective"] = bool(fr.bgb_deduction_effective())
        try:
            snap["bgb_spot_balance"] = round(fr._bgb_spot_balance(), 4)
            snap["bgb_dust"] = fr.BGB_DUST
        except Exception:
            pass
    except Exception:
        pass
    try:                                              # BGB sur la MARGE CROISÉE (remise marge -20% alt_carry)
        import fee_rates as fr
        data = fr._signed_get("/api/v2/margin/crossed/account/assets", {"coin": "BGB"})
        if isinstance(data, dict):                    # _signed_get renvoie la data brute (liste) ou {data:[...]}
            data = data.get("data") or []
        snap["bgb_crossed_margin"] = round(sum(
            float(a.get("available") or 0) for a in (data or [])
            if isinstance(a, dict) and str(a.get("coin", "")).upper() == "BGB"), 4)
    except Exception:
        pass
    try:
        import bitget_market_extras as bme
        for sym in WATCH_SYMBOLS:
            c = bme.fetch_contract(sym)
            if c:
                snap[f"contract:{sym}"] = {k: c.get(k) for k in
                                           ("min_notional_usdt", "fund_interval_h", "max_lever", "status")}
    except Exception:
        pass
    return snap


def _flatten(snap):
    """{a:{b:v}} -> {'a.b':v} ; scalaires inchangés. PUR."""
    out = {}
    for k, v in (snap or {}).items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                out[f"{k}.{kk}"] = vv
        else:
            out[k] = v
    return out


def diff(old, new):
    """Liste [(clé, avant, après)] des faits qui ont changé. PUR."""
    fo, fn = _flatten(old), _flatten(new)
    return [(k, fo.get(k), fn.get(k)) for k in sorted(set(fo) | set(fn)) if fo.get(k) != fn.get(k)]


def _impact_for(key):
    """(module, reco) pour une clé de diff (base = dernier segment, hors préfixe contract:sym)."""
    base = key.split(".")[-1].split(":")[0]
    return IMPACT.get(base, (None, None))


def review(alert=False):
    new = snapshot()
    if not new:
        print("bitget_watch : API indisponible (aucun fait lu). Fail-safe. VERDICT: SAFE")
        return
    try:
        old = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    except Exception:
        old = {}
    changes = diff(old, new)
    bgb_low = ("bgb_spot_balance" in new and "bgb_dust" in new
               and new["bgb_spot_balance"] <= new["bgb_dust"])
    bgb_m_low = ("bgb_crossed_margin" in new and "bgb_dust" in new
                 and new["bgb_crossed_margin"] <= new["bgb_dust"])
    print(f"=== BITGET WATCH — {len(changes)} changement(s) vs baseline ===")
    lignes = []
    for k, a, b in changes:
        mod, rec = _impact_for(k)
        print(f"  • {k} : {a} -> {b}")
        if mod:
            print(f"      -> [{mod}] {rec}")
        lignes.append(f"{k}: {a} -> {b}" + (f"  [{mod}: {rec}]" if mod else ""))
    if bgb_low:
        mod, rec = IMPACT["bgb_spot_balance_low"]
        print(f"  ⚠ BGB réservoir bas : {new.get('bgb_spot_balance')} <= poussière {new.get('bgb_dust')}")
        print(f"      -> [{mod}] {rec}")
        lignes.append(f"BGB bas  [{mod}: {rec}]")
    if bgb_m_low:
        mod, rec = IMPACT["bgb_crossed_low"]
        print(f"  ⚠ BGB marge croisée bas : {new.get('bgb_crossed_margin')} <= poussière {new.get('bgb_dust')}")
        print(f"      -> [{mod}] {rec}")
        lignes.append(f"BGB marge bas  [{mod}: {rec}]")
    if not changes and not bgb_low and not bgb_m_low:
        print("  aucun changement. Faits Bitget stables.")
    if alert and (changes or bgb_low or bgb_m_low):
        try:
            import telegram_notifier as tn
            tn.send_telegram("🛰️ BITGET WATCH\n" + "\n".join(lignes))
        except Exception:
            pass
    if alert:
        try:
            json.dump(new, open(STATE, "w"))
            if changes or bgb_low or bgb_m_low:
                with open(JOURNAL, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": int(time.time()), "changes": lignes}) + "\n")
        except Exception:
            pass
    print("Veille seule — l'action reste un acte révisé (3 portes). Aucun ordre, aucun scraping. VERDICT: SAFE")


def main():
    if "--show" in sys.argv:
        print(json.dumps(snapshot(), indent=2, default=str))
        print("Lecture seule, aucun ordre. VERDICT: SAFE")
        return
    review(alert="--alert" in sys.argv)


if __name__ == "__main__":
    main()
