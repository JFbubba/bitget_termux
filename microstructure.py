"""
microstructure.py — features de MICROSTRUCTURE (carnet L2 + tape) pour débloquer T4.

Classement : SAFE. Données PUBLIQUES, lecture seule, AUCUN ordre, AUCUNE clé.

Pourquoi : les outils T4 (toxicité / sélection adverse / OFI) exigent le carnet et la
tape — pas seulement l'OHLCV. Le bot a déjà le plumbing REST (bitget_market_data :
merge-depth L2 + recent trades). Ce module ajoute :
  1. les FEATURES PURES (testables) calculées depuis des snapshots de carnet + tape ;
  2. un COLLECTEUR best-effort (REST-poll) qui maintient l'état précédent et écrit un
     buffer roulant que les agents lisent (découplé, ne bloque jamais).

HONNÊTETÉ (cf. 2112.13213, 2606.15715, 2504.15908) :
  • L2 + tape via REST/WebSocket public Bitget : OFI (Cont-Kukanov), queue imbalance,
    trade-sign, markout/sélection adverse -> FAISABLES.
  • Vrai L3 (ordre-par-ordre, durée de vie, spoofing) : INDISPONIBLE sur le flux public
    -> hors de portée ; seuls des proxies L2 (flicker depuis les deltas) sont possibles.
  • Le REST-poll (~1-2 s) est BASSE FIDÉLITÉ : l'OFI par-événement exige le WebSocket
    `wss://ws.bitget.com/v2/ws/public` (canaux books/trade) — upgrade noté (cf. run()).

Les fonctions de calcul sont PURES ; les fetch réseau sont enveloppés (ne lèvent jamais).
"""

import json
import time
from pathlib import Path

BUFFER_FILE = Path(__file__).resolve().parent / ".microstructure_buffer.json"
_PREV = {}                       # état du carnet précédent par symbole (pour l'OFI)


# ---------- helpers purs ----------

def _best(side_levels, want="bid"):
    """Meilleur niveau (prix, taille). bids triés desc, asks asc -> on prend [0]. Pur."""
    if not side_levels:
        return (0.0, 0.0)
    p, s = side_levels[0]
    return (float(p), float(s))


def mid_price(book):
    """Prix milieu (meilleur bid+ask)/2. Pur. 0 si carnet vide."""
    pb, _ = _best(book.get("bids", []))
    pa, _ = _best(book.get("asks", []))
    return (pb + pa) / 2.0 if pb > 0 and pa > 0 else 0.0


def spread(book):
    """Spread bid-ask absolu et relatif (en bps). Pur."""
    pb, _ = _best(book.get("bids", []))
    pa, _ = _best(book.get("asks", []))
    if pb <= 0 or pa <= 0:
        return {"abs": 0.0, "bps": 0.0}
    mid = (pb + pa) / 2.0
    return {"abs": round(pa - pb, 8), "bps": round((pa - pb) / mid * 1e4, 3) if mid > 0 else 0.0}


def queue_imbalance(book, levels=5):
    """Déséquilibre de file sur les `levels` premiers niveaux ∈ [−1,1]. Pur.
    >0 = profondeur acheteuse dominante. Réf. order-flow imbalance (2112.13213)."""
    bids = book.get("bids", [])[:levels]
    asks = book.get("asks", [])[:levels]
    qb = sum(float(s) for _, s in bids)
    qa = sum(float(s) for _, s in asks)
    tot = qb + qa
    return round((qb - qa) / tot, 4) if tot > 0 else 0.0


def book_ofi(book_prev, book_now):
    """Order-Flow Imbalance de CONT-KUKANOV (niveau 1) entre deux snapshots. Pur.
    OFI = ΔW_bid − ΔW_ask, où une montée du bid / une baisse de l'ask = pression
    ACHETEUSE (OFI>0). Réf. arXiv:2112.13213. Nécessite deux carnets consécutifs."""
    if not book_prev or not book_now:
        return 0.0
    pb0, qb0 = _best(book_prev.get("bids", []))
    pa0, qa0 = _best(book_prev.get("asks", []))
    pb1, qb1 = _best(book_now.get("bids", []))
    pa1, qa1 = _best(book_now.get("asks", []))
    if min(pb0, pa0, pb1, pa1) <= 0:
        return 0.0
    # côté bid
    if pb1 > pb0:
        dwb = qb1
    elif pb1 == pb0:
        dwb = qb1 - qb0
    else:
        dwb = -qb0
    # côté ask (miroir)
    if pa1 > pa0:
        dwa = -qa0
    elif pa1 == pa0:
        dwa = qa1 - qa0
    else:
        dwa = qa1
    return round(dwb - dwa, 6)


def trade_sign_imbalance(trades):
    """Déséquilibre de la tape ∈ [−1,1] depuis le côté agresseur. Pur.
    >0 = volume acheteur agressif dominant (flux directionnel)."""
    buy = sum(t.get("size", 0.0) for t in trades if str(t.get("side", "")).startswith("b"))
    sell = sum(t.get("size", 0.0) for t in trades if str(t.get("side", "")).startswith("s"))
    tot = buy + sell
    return round((buy - sell) / tot, 4) if tot > 0 else 0.0


def markout(entry_price, side, future_mid):
    """Markout / sélection adverse : P&L (en bps) d'un fill `side` après coup, vu au
    `future_mid`. PUR. Négatif = flux TOXIQUE (le prix part contre le preneur de
    liquidité). Réf. arXiv:2606.15715."""
    if entry_price <= 0 or future_mid <= 0:
        return 0.0
    sgn = 1.0 if str(side).startswith("b") else -1.0
    return round(sgn * (future_mid - entry_price) / entry_price * 1e4, 3)


def features(book_prev, book_now, trades, levels=5):
    """Snapshot de features de microstructure (pur). Combine carnet (mid, spread,
    queue imbalance, OFI) et tape (trade-sign). markout se calcule a posteriori
    depuis le buffer (il faut un mid FUTUR)."""
    return {
        "mid": round(mid_price(book_now), 8),
        "spread_bps": spread(book_now)["bps"],
        "queue_imbalance": queue_imbalance(book_now, levels),
        "ofi": book_ofi(book_prev, book_now),
        "trade_sign": trade_sign_imbalance(trades or []),
    }


# ---------- buffer roulant (disque) ----------

def _load_buffer():
    try:
        return json.loads(BUFFER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_buffer(buf):
    try:
        BUFFER_FILE.write_text(json.dumps(buf)[:4_000_000], encoding="utf-8")
    except Exception:
        pass


def append_snapshot(symbol, snap, max_len=600):
    """Ajoute un snapshot horodaté au buffer roulant du symbole. Best-effort."""
    buf = _load_buffer()
    key = symbol.upper()
    rows = buf.get(key, [])
    rows.append(snap)
    buf[key] = rows[-max_len:]
    _save_buffer(buf)


def recent(symbol, n=120):
    """Derniers `n` snapshots de microstructure du symbole (pour les agents). Best-effort."""
    return _load_buffer().get(symbol.upper(), [])[-n:]


def realized_markout(rows, h=5):
    """Markout RÉALISÉ moyen (bps) depuis une suite de snapshots : pour chaque
    snapshot, P&L du côté agresseur (trade_sign) `h` pas plus tard. PUR.
    NÉGATIF = flux TOXIQUE (les agresseurs obtiennent de mauvais prix). Réf. 2606.15715."""
    mk = []
    for i in range(len(rows) - h):
        m0 = rows[i].get("mid", 0.0); m1 = rows[i + h].get("mid", 0.0)
        sgn = rows[i].get("trade_sign", 0.0)
        if m0 > 0 and m1 > 0 and sgn != 0:
            mk.append((1 if sgn > 0 else -1) * (m1 - m0) / m0 * 1e4)
    return float(sum(mk) / len(mk)) if mk else 0.0


def summary(symbol, n=60, markout_h=5):
    """Résumé des features récentes (ce que lit un agent T4). Best-effort. Pur-ish.
    `toxicity` ∈ [0,1] = markout adverse (négatif) + élargissement du spread (heuristique
    calibrable, pas un seuil de papier)."""
    rows = recent(symbol, n)
    if not rows:
        return {"n": 0, "ofi": 0.0, "queue_imbalance": 0.0, "trade_sign": 0.0,
                "spread_bps": 0.0, "markout_bps": 0.0, "toxicity": 0.0}
    def avg(k):
        vals = [r.get(k, 0.0) for r in rows]
        return sum(vals) / len(vals) if vals else 0.0
    mk = realized_markout(rows, markout_h)
    sp = avg("spread_bps")
    tox = max(0.0, min(1.0, max(0.0, -mk) / 10.0 + max(0.0, sp - 2.0) / 20.0))
    return {"n": len(rows), "ofi": round(avg("ofi"), 4),
            "queue_imbalance": round(avg("queue_imbalance"), 4),
            "trade_sign": round(avg("trade_sign"), 4),
            "spread_bps": round(sp, 3), "markout_bps": round(mk, 3),
            "toxicity": round(tox, 3)}


# ---------- collecteur best-effort (REST-poll) ----------

def collect_once(symbol="BTCUSDT"):
    """Une passe de collecte (REST) : carnet + tape -> features -> buffer. Maintient
    l'état précédent pour l'OFI. Best-effort, ne lève jamais. Retourne le snapshot."""
    try:
        import bitget_market_data as bmd
        book = bmd.parse_orderbook(bmd.fetch_orderbook(symbol, limit="50"))
        trades = bmd.parse_trades(bmd.fetch_recent_trades(symbol, limit=100))
    except Exception:
        return {}
    key = symbol.upper()
    prev = _PREV.get(key)
    snap = features(prev, book, trades)
    snap["ts"] = int(time.time())
    _PREV[key] = book
    append_snapshot(symbol, snap)
    return snap


def run(symbol="BTCUSDT", interval=2.0, iterations=None):
    """Boucle de collecte (pour un service systemd). interval en secondes. Best-effort.
    ⚠️ BASSE FIDÉLITÉ (REST). HAUTE FIDÉLITÉ = WebSocket public Bitget
    `wss://ws.bitget.com/v2/ws/public` (canaux books + trade) -> upgrade futur."""
    i = 0
    while iterations is None or i < iterations:
        collect_once(symbol)
        i += 1
        if iterations is not None and i >= iterations:
            break
        time.sleep(max(0.5, interval))


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    snap = collect_once(sym)
    print("=== MICROSTRUCTURE (L2 + tape, lecture seule) ===")
    print(json.dumps(snap, ensure_ascii=False, indent=2) if snap else "données indisponibles")
    print("résumé récent :", summary(sym))
    print("Aucun ordre, aucune clé, aucun L3. VERDICT: SAFE")


if __name__ == "__main__":
    main()
