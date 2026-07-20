#!/usr/bin/env python3
"""variant_shadows.py — voix d'OMBRE MESURÉES de variantes d'agents (§75). SAFE, lecture seule.

Calcule des VARIANTES optimisées (mesure-d'abord) de deux agents du banc et les journalise dans
`.overlay_votes.jsonl` — JAMAIS dans le consensus — pour que `live_ic_audit` les mesure vs l'agent LIVE :
  • **sentiment_shadow** : Fear & Greed en PERCENTILE de son historique (déjà téléchargé mais ignoré
    par le vote live) + emphase aux EXTRÊMES, au lieu du contrarian linéaire ancré sur 50.
  • **savant_shadow** : Mahalanobis avec standardisation ROBUSTE (médiane/MAD, déjà écrite) dans le
    chemin du vote, au lieu de la standardisation moyenne/σ — MÊMES bougies 15m que l'agent live (A/B propre).

N'arme RIEN, ne vote RIEN, ne desserre aucun mur. Adoption seulement si l'IC HONNÊTE (clusterisé) de la
variante dépasse l'agent live sur la durée. CLI : `python variant_shadows.py` (cron : accumule l'ombre).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OVERLAY = ROOT / ".overlay_votes.jsonl"
WATCH = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BGBUSDT", "ADAUSDT", "AVAXUSDT"]


def _price(sym):
    try:
        import bitget_market_data as bmd
        return (bmd.mark_prices() or {}).get(sym)
    except Exception:
        return None


def cycle(symbols=None, now=None):
    """Calcule + journalise sentiment_shadow / savant_shadow par symbole dans l'overlay. Fail-safe
    (ne lève jamais). Retourne le nb de lignes journalisées."""
    import time
    ts = int(now if now is not None else time.time())
    syms = symbols or WATCH
    sent = {"vote": 0.0, "confidence": 0.0}            # sentiment = MARCHÉ-LARGE (même vote tous symboles)
    try:
        import sentiment_index as si
        sent = si.shadow_vote() or sent
    except Exception:
        pass
    n = 0
    for sym in syms:
        price = _price(sym)
        if not price:
            continue
        votes = {}
        if (sent.get("confidence") or 0) > 0:
            votes["sentiment_shadow"] = round(float(sent["vote"]), 3)
        try:
            import savant_agent as sa
            candles = sa._candles(sym)                 # MÊME fetch 15m que l'agent live
            if candles and len(candles) > 90:
                sv = sa.signal(candles, robust=True) or {}
                if (sv.get("confidence") or 0) > 0:
                    votes["savant_shadow"] = round(float(sv["vote"]), 3)
        except Exception:
            pass
        if votes:
            try:
                import journal_append as ja
                ja.append_jsonl(OVERLAY, {"ts": ts, "symbol": sym, "price": float(price), "votes": votes})
                n += 1
            except Exception:
                pass
    return n


def main():
    n = cycle()
    print(f"variant_shadows : {n} ligne(s) d'ombre journalisée(s) (sentiment_shadow / savant_shadow). "
          f"Mesuré par live_ic_audit (overlay) vs l'agent live. N'arme rien, ne vote rien. VERDICT: SAFE")


if __name__ == "__main__":
    main()
