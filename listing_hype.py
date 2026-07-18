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
POS_PATH = ROOT / ".listing_hype_positions.json"


def _norm_sym(s):
    """Normalise un symbole (anti double-USDT du parseur de titres). PUR."""
    s = str(s or "").upper()
    while s.endswith("USDTUSDT"):
        s = s[:-4]
    return s


# Actions tokenisées / ETF (Bitget « Stock Perps ») : EXCLUES du listing-hype — classe
# d'actif différente (horaires de bourse, risque, gap week-end), comme l'univers d'analyse
# les exclut (§universe). Détection par le TITRE de l'annonce (« ... Stock Perps », « xStock »…).
_STOCK_KW = ("stock", "xstock", "tokenized", "equity", " etf", "pre-market", "premarket")


def _is_stock_listing(title):
    """PUR. Vrai si le titre d'annonce indique une action tokenisée / ETF -> à EXCLURE."""
    t = str(title or "").lower()
    return any(k in t for k in _STOCK_KW)


def new_listing_symbols(anns, seen):
    """PUR. Symboles de NOUVEAUX listings CRYPTO (type=='listing', hors actions tokenisées)
    absents de `seen`. Dédupliqué, symboles normalisés. `anns` = [{title,type,ts}].
    Retourne [(symbol, title, ts)]."""
    import bitget_announcements as ba
    seen = {_norm_sym(s) for s in (seen or [])}
    vus, out = set(), []
    for a in anns or []:
        if str(a.get("type", "")).lower() != "listing":
            continue
        title = str(a.get("title", ""))
        if _is_stock_listing(title):                 # actions tokenisées / ETF -> exclues
            continue
        for raw in ba.symbols_in(title):
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


def _load_positions(path=None):
    """Positions SIM ouvertes {symbol: {entry_price, entry_ts, notional}}. PUR si path injecté."""
    p = Path(path) if path else POS_PATH
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_positions(positions, path=None):
    try:
        (Path(path) if path else POS_PATH).write_text(json.dumps(positions), encoding="utf-8")
    except Exception:
        pass


def _spot_price(symbol):
    """Dernier prix spot (best-effort via candle_reader). None si indisponible (nouveau
    token sans flux propre) -> on retente au cycle suivant."""
    try:
        from candle_reader import get_bitget_candles
        c = get_bitget_candles(symbol, limit=1)
        return float(c[-1]["close"]) if c else None
    except Exception:
        return None


def _net_pnl(entry, exit_price, notional, fee_bps):
    """PnL DRY NET de frais (round-trip taker) d'une position hype. PUR."""
    try:
        entry = float(entry)
        exit_price = float(exit_price)
    except (TypeError, ValueError):
        return 0.0
    if entry <= 0:
        return 0.0
    gross = (exit_price - entry) / entry
    net = gross - 2.0 * float(fee_bps) / 1e4
    return round(net * float(notional), 4)


def cycle(anns=None, seen_path=None, journal_path=None, pos_path=None, now=None,
          cap_per_op=None, kill=None, price_fn=None, tp_pct=None, sl_pct=None, max_hold_s=None):
    """SIMULATION DRY (aucun ordre) pour MESURER la stratégie avant tout armement réel :
      1) SORTIES d'abord — pour chaque position sim ouverte, `exit_decision` sur le prix
         live -> si vente, PnL NET de frais journalisé et position fermée ;
      2) ENTRÉES — nouveaux listings (bitget_announcements) -> position sim ouverte au prix
         live, journalisée.
    L'exécution RÉELLE (spot_trader §67, gatée LISTING_HYPE_LIVE) reste l'étape suivante.
    Tout est injectable (anns, chemins, price_fn, params) pour test déterministe."""
    from config_utils import cfg as _cfg
    now = _time.time() if now is None else now
    price_fn = _spot_price if price_fn is None else price_fn
    fee_bps = float(_cfg("LISTING_HYPE_FEE_BPS", 6.0))
    tp = float(_cfg("LISTING_HYPE_TP_PCT", 0.15)) if tp_pct is None else float(tp_pct)
    sl = float(_cfg("LISTING_HYPE_SL_PCT", 0.08)) if sl_pct is None else float(sl_pct)
    hold = float(_cfg("LISTING_HYPE_MAX_HOLD_S", 1800)) if max_hold_s is None else float(max_hold_s)
    cap = float(_cfg("LISTING_HYPE_CAP_USDT", 3.0)) if cap_per_op is None else float(cap_per_op)
    notional = float(_cfg("LISTING_HYPE_NOTIONAL_USDT", 3.0))
    if kill is None:
        try:
            import risk_manager
            kill = bool(risk_manager.kill_switch_active())
        except Exception:
            kill = False
    if anns is None:
        try:
            import bitget_announcements as ba
            anns = ba.fetch_announcements()
        except Exception:
            anns = []
    jpath = Path(journal_path) if journal_path else JOURNAL
    positions = _load_positions(pos_path)
    seen = _load_seen(seen_path)
    out = {"kill": bool(kill), "entrees": [], "sorties": []}

    def _journal(rec):
        try:
            import journal_append as ja
            ja.append_jsonl(jpath, rec)
        except Exception:
            pass

    # 1. SORTIES d'abord (une position ne s'attarde pas)
    for sym in list(positions.keys()):
        p = positions[sym]
        px = price_fn(sym)
        if px is None:
            continue
        ed = exit_decision(p.get("entry_price"), px, p.get("entry_ts", now), now,
                           tp_pct=tp, sl_pct=sl, max_hold_s=hold)
        if ed["action"] == "sell":
            pnl = _net_pnl(p.get("entry_price"), px, p.get("notional", notional), fee_bps)
            rec = {"ts": int(now), "symbol": sym, "action": "sell_dry",
                   "entry_price": p.get("entry_price"), "exit_price": round(float(px), 8),
                   "notional": p.get("notional", notional), "pnl_net_usd": pnl, "reason": ed["reason"]}
            _journal(rec)
            out["sorties"].append(rec)
            del positions[sym]

    # 2. ENTRÉES (nouveaux listings)
    for sym, title, ts in new_listing_symbols(anns, seen):
        seen.add(sym)
        d = entry_decision(sym, notional, cap, kill=kill, live=False)
        if d["action"] != "buy":
            _journal({"ts": int(now), "symbol": sym, "action": "skip", "reason": d["reason"]})
            continue
        px = price_fn(sym)
        if px is None or float(px) <= 0:
            _journal({"ts": int(now), "symbol": sym, "action": "skip", "reason": "prix indisponible au listing"})
            continue
        positions[sym] = {"entry_price": round(float(px), 8), "entry_ts": int(now), "notional": d["notional"]}
        rec = {"ts": int(now), "symbol": sym, "action": "buy_dry", "entry_price": positions[sym]["entry_price"],
               "notional": d["notional"], "title": str(title)[:120], "reason": d["reason"]}
        _journal(rec)
        out["entrees"].append(rec)

    _save_positions(positions, pos_path)
    _save_seen(seen, seen_path)
    return out


def dry_report(journal_path=None):
    """Bilan DRY de la stratégie depuis le journal : round-trips fermés (sell_dry), taux de
    gain, PnL NET cumulé. PUR (fs). Pour JUGER la stratégie avant tout armement."""
    p = Path(journal_path) if journal_path else JOURNAL
    trips, wins, net = 0, 0, 0.0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("action") == "sell_dry":
                trips += 1
                pnl = float(r.get("pnl_net_usd") or 0.0)
                net += pnl
                wins += 1 if pnl > 0 else 0
    except Exception:
        pass
    return {"round_trips": trips, "win_rate": round(wins / trips, 3) if trips else None,
            "pnl_net_usd": round(net, 4)}


def main():
    r = cycle()
    rep = dry_report()
    print("=== LISTING-HYPE (SIMULATION DRY — aucun ordre réel) ===")
    print(f"kill-switch: {r['kill']} · entrées: {len(r['entrees'])} · sorties: {len(r['sorties'])}")
    for e in r["entrees"]:
        print(f"  ENTRÉE {e['symbol']} @ {e['entry_price']} ({e['notional']} $) — {e['reason']}")
    for s in r["sorties"]:
        print(f"  SORTIE {s['symbol']} @ {s['exit_price']} · PnL net {s['pnl_net_usd']:+.4f} $ — {s['reason']}")
    print(f"Bilan DRY : {rep['round_trips']} round-trips · win {rep['win_rate']} · PnL net {rep['pnl_net_usd']:+.4f} $")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
