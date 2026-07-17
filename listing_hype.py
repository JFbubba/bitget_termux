#!/usr/bin/env python3
"""listing_hype.py — agent SPÉCULATIF : hype des NOUVEAUX listings Bitget (décision proprio).

Classement : SAFE. Ce module = DÉTECTION (via bitget_announcements) + DÉCISIONS PURES +
journal DRY. Il ne passe AUCUN ordre : l'exécution réelle est DÉLÉGUÉE à `spot_trader`
(surface §67 : verrou LIVE, kill-switch, caps durs) une fois armé — jamais ici.

Stratégie (bornée, DRY d'abord, MESURÉE) : un nouveau listing -> achat MINUSCULE, sortie
STRICTE (TP rapide OU stop serré OU délai max). Piège retail assumé (pump-puis-dump +
latence Francfort ~285 ms) : taille plafonnée §67, exit serré, on MESURE avant tout scaling.
Gating : LISTING_HYPE_LIVE (défaut OFF -> DRY).
"""
import json
import time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEEN_PATH = ROOT / ".listing_hype_seen.json"
JOURNAL = ROOT / ".listing_hype_journal.jsonl"


def _norm_sym(s):
    """Normalise un symbole (anti double-USDT du parseur de titres). PUR."""
    s = str(s or "").upper()
    while s.endswith("USDTUSDT"):
        s = s[:-4]
    return s


def new_listing_symbols(anns, seen):
    """PUR. Symboles de NOUVEAUX listings (type=='listing') absents de `seen`. Dédupliqué,
    symboles normalisés. `anns` = [{title,type,ts}] (bitget_announcements.fetch_announcements).
    Retourne [(symbol, title, ts)]."""
    import bitget_announcements as ba
    seen = {_norm_sym(s) for s in (seen or [])}
    vus, out = set(), []
    for a in anns or []:
        if str(a.get("type", "")).lower() != "listing":
            continue
        for raw in ba.symbols_in(str(a.get("title", ""))):
            sym = _norm_sym(raw)
            if sym and sym.endswith("USDT") and sym not in seen and sym not in vus:
                vus.add(sym)
                out.append((sym, a.get("title", ""), a.get("ts")))
    return out


def entry_decision(symbol, notional_usdt, cap_per_op, kill=False, live=False):
    """PUR. Entrée BORNÉE sur un nouveau listing. {action, symbol, notional, reason} ;
    action ∈ {'buy','skip'}. Ne dépasse JAMAIS le cap ; kill-switch -> skip."""
    if kill:
        return {"action": "skip", "symbol": symbol, "notional": 0.0, "reason": "kill-switch"}
    n = min(float(notional_usdt), float(cap_per_op))
    if n < 1.0:
        return {"action": "skip", "symbol": symbol, "notional": 0.0, "reason": "taille < 1$"}
    return {"action": "buy", "symbol": symbol, "notional": round(n, 2),
            "reason": f"nouveau listing -> hype ({'LIVE' if live else 'DRY'}, cap {cap_per_op:.0f}$)"}


def exit_decision(entry_price, price, ts_in, now, tp_pct=0.15, sl_pct=0.08, max_hold_s=1800):
    """PUR. Sortie hype STRICTE : TP (+tp_pct) | stop (−sl_pct) | délai max. {action, reason} ;
    action ∈ {'sell','hold'}. La hype se retourne en minutes -> on ne s'attarde pas."""
    try:
        ep, px = float(entry_price), float(price)
    except (TypeError, ValueError):
        return {"action": "hold", "reason": "prix illisible"}
    if ep <= 0 or px <= 0:
        return {"action": "hold", "reason": "prix invalide"}
    chg = (px - ep) / ep
    if chg >= tp_pct:
        return {"action": "sell", "reason": f"TP {chg*100:+.1f}% >= +{tp_pct*100:.0f}%"}
    if chg <= -sl_pct:
        return {"action": "sell", "reason": f"stop {chg*100:+.1f}% <= -{sl_pct*100:.0f}%"}
    if float(now) - float(ts_in) >= max_hold_s:
        return {"action": "sell", "reason": f"delai max {int(max_hold_s//60)}min (chg {chg*100:+.1f}%)"}
    return {"action": "hold", "reason": f"chg {chg*100:+.1f}% dans la fenetre"}


def _load_seen(path=None):
    """Symboles de listings déjà traités (anti-rachat). Set. PUR si path injecté."""
    p = Path(path) if path else SEEN_PATH
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_seen(seen, path=None):
    p = Path(path) if path else SEEN_PATH
    try:
        (Path(path) if path else SEEN_PATH).write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except Exception:
        pass


def cycle(anns=None, seen_path=None, journal_path=None, now=None, cap_per_op=None, kill=None):
    """DRY : détecte les NOUVEAUX listings Bitget (bitget_announcements), JOURNALISE la
    décision d'entrée BORNÉE, marque 'vu'. AUCUN ORDRE ici — l'exécution réelle (déléguée à
    spot_trader §67, gatée LISTING_HYPE_LIVE, défaut OFF) est l'étape SUIVANTE. Retourne
    {kill, nouveaux:[recs]}. Paramètres injectables pour test."""
    from config_utils import cfg as _cfg
    now = _time.time() if now is None else now
    if anns is None:
        try:
            import bitget_announcements as ba
            anns = ba.fetch_announcements()
        except Exception:
            anns = []
    if kill is None:
        try:
            import risk_manager
            kill = bool(risk_manager.kill_switch_active())
        except Exception:
            kill = False
    cap = float(_cfg("LISTING_HYPE_CAP_USDT", 3.0)) if cap_per_op is None else float(cap_per_op)
    notional = float(_cfg("LISTING_HYPE_NOTIONAL_USDT", 3.0))
    seen = _load_seen(seen_path)
    jpath = Path(journal_path) if journal_path else JOURNAL
    out = {"kill": bool(kill), "nouveaux": []}
    for sym, title, ts in new_listing_symbols(anns, seen):
        d = entry_decision(sym, notional, cap, kill=kill, live=False)     # DRY : jamais d'ordre
        rec = {"ts": int(now), "symbol": sym, "title": str(title)[:120], "listing_ts": ts, **d}
        try:
            import journal_append as ja
            ja.append_jsonl(jpath, rec)
        except Exception:
            pass
        seen.add(sym)
        out["nouveaux"].append(rec)
    _save_seen(seen, seen_path)
    return out


def main():
    r = cycle()
    print("=== LISTING-HYPE (DRY — détection + journal, AUCUN ordre) ===")
    print(f"kill-switch: {r['kill']} · nouveaux listings: {len(r['nouveaux'])}")
    for rec in r["nouveaux"]:
        print(f"  {rec['symbol']}: {rec['action']} {rec.get('notional')} $ — {rec['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
