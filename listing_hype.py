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
