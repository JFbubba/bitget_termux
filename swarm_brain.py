"""
swarm_brain.py — essaim d'agents analytiques + cerveau (LECTURE SEULE).

Classement : SAFE. Aucun ordre. Le « cerveau » agrège plusieurs AGENTS
spécialisés (chacun lit UNE facette du marché et vote une direction) en un
CONSENSUS (biais LONG/SHORT/NEUTRE + conviction). Il s'ÉDUQUE : il journalise
ses décisions, les juge après coup contre le mouvement réel du prix, et ajuste
la confiance (poids) accordée à chaque agent selon son taux de réussite.

C'est de l'aide à la décision adaptative — pas un oracle ni une machine à gagner.

CLI : python swarm_brain.py [SYMBOL]
"""

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEIGHTS_FILE = ROOT / "brain_weights.json"
LOG_FILE = ROOT / "brain_log.json"
HORIZON_S = int(os.getenv("BRAIN_HORIZON_S", "3600"))  # délai avant de juger une décision

AGENTS = ["orderflow", "technicals", "macro", "sentiment", "derivs"]


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


# ---------- agents (symbol -> {vote[-1..1], confidence[0..1], note}) ----------

def agent_orderflow(symbol):
    import bitget_market_data as bmd
    s = bmd.market_snapshot(symbol)
    imb = s.get("book_imbalance") or 0.0
    cvd = s.get("cvd") or 0.0
    vote = _clamp(imb * 2 + (0.3 if cvd > 0 else -0.3 if cvd < 0 else 0))
    return {"vote": vote, "confidence": min(abs(imb) * 1.5, 1.0), "note": f"imbalance {imb:.2f}, CVD {cvd:.2f}"}


def agent_technicals(symbol):
    import technicals as tk
    t = tk.technicals(symbol, "15m")
    ema20, ema50, rsi = t.get("ema20"), t.get("ema50"), t.get("rsi14")
    vb = t.get("volume_bias") or 0
    vote = 0.0
    if ema20 and ema50:
        vote += 0.5 if ema20 > ema50 else -0.5
    if rsi is not None:
        vote += 0.3 if rsi < 35 else -0.3 if rsi > 65 else 0
    vote += _clamp(vb / 10.0) * 0.4
    return {"vote": _clamp(vote), "confidence": 0.6, "note": f"RSI {rsi}, EMA {'+' if (ema20 or 0) > (ema50 or 0) else '-'}, vbias {vb}"}


def agent_macro(symbol):
    import macro_context as mc
    reg = (mc.macro_snapshot() or {}).get("regime")
    vote = 0.6 if reg == "RISK_ON" else -0.6 if reg == "RISK_OFF" else 0.0
    return {"vote": vote, "confidence": 0.5 if reg in ("RISK_ON", "RISK_OFF") else 0.1, "note": f"régime {reg}"}


def agent_sentiment(symbol):
    import sentiment_index as si
    fg = si.fetch_fear_greed()
    v = fg.get("value") if fg else None
    if v is None:
        return {"vote": 0, "confidence": 0, "note": "n/a"}
    vote = _clamp((50 - v) / 50.0)  # contrarian : peur -> achat
    return {"vote": vote, "confidence": min(abs(50 - v) / 50.0, 1.0), "note": f"F&G {v} ({fg.get('classification')})"}


def agent_derivs(symbol):
    import aggregated_derivs as ad
    f = (ad.fetch_aggregate(symbol) or {}).get("oi_weighted_funding")
    if f is None:
        return {"vote": 0, "confidence": 0, "note": "n/a"}
    vote = _clamp(-f * 2000)  # funding très positif = longs surchargés -> contrarian
    return {"vote": vote, "confidence": min(abs(f) * 2000, 1.0), "note": f"funding {f * 100:.4f}%"}


AGENT_FUNCS = {
    "orderflow": agent_orderflow, "technicals": agent_technicals, "macro": agent_macro,
    "sentiment": agent_sentiment, "derivs": agent_derivs,
}


# ---------- agrégation + apprentissage (purs, testables) ----------

def aggregate(votes, weights):
    num = den = 0.0
    contrib = []
    for name, v in votes.items():
        w = weights.get(name, 1.0)
        conf = v.get("confidence", 0) or 0
        vote = v.get("vote", 0) or 0
        num += vote * conf * w
        den += conf * w
        contrib.append({"agent": name, "vote": round(vote, 2), "conf": round(conf, 2), "weight": round(w, 2)})
    consensus = (num / den) if den else 0.0
    bias = "LONG" if consensus > 0.2 else "SHORT" if consensus < -0.2 else "NEUTRE"
    return {"consensus": round(consensus, 3), "bias": bias, "conviction": round(abs(consensus), 3), "agents": contrib}


def update_weights(weights, agent_correct):
    """agent_correct = {name: bool|None}. Renforce les bons agents, normalise (moy ~1)."""
    w = dict(weights)
    for name, correct in agent_correct.items():
        if correct is None:
            continue
        w[name] = max(0.2, min(3.0, w.get(name, 1.0) * (1.05 if correct else 0.96)))
    avg = (sum(w.values()) / len(w)) if w else 1.0
    if avg > 0:
        w = {k: round(v / avg, 3) for k, v in w.items()}
    return w


# ---------- persistance ----------

def load_weights():
    try:
        return json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {a: 1.0 for a in AGENTS}


def save_weights(w):
    try:
        WEIGHTS_FILE.write_text(json.dumps(w), encoding="utf-8")
    except Exception:
        pass


def _read_log():
    try:
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_log(log):
    try:
        LOG_FILE.write_text(json.dumps(log[-500:]), encoding="utf-8")
    except Exception:
        pass


def _price(symbol):
    import bitget_market_data as bmd
    return bmd.market_snapshot(symbol).get("mid_price")


def _record(symbol, votes, result, price):
    log = _read_log()
    log.append({
        "ts": int(time.time()), "symbol": symbol, "price": price,
        "votes": {n: round(v.get("vote", 0), 3) for n, v in votes.items()},
        "consensus": result["consensus"], "evaluated": False,
    })
    _write_log(log)


def learn(symbol, price_now, weights):
    """Juge les décisions passées matures de ce symbole et met à jour les poids."""
    if not price_now:
        return weights
    log = _read_log()
    now = int(time.time())
    correctness, changed = {}, False
    for e in log:
        if e.get("evaluated") or e.get("symbol") != symbol or (now - e.get("ts", now)) < HORIZON_S:
            continue
        realized = 1 if price_now > e["price"] else -1 if price_now < e["price"] else 0
        for name, vote in (e.get("votes") or {}).items():
            if vote == 0 or realized == 0:
                continue
            correctness.setdefault(name, []).append((vote > 0) == (realized > 0))
        e["evaluated"] = True
        changed = True
    if correctness:
        agent_correct = {n: (sum(v) / len(v) >= 0.5) for n, v in correctness.items()}
        weights = update_weights(weights, agent_correct)
        save_weights(weights)
    if changed:
        _write_log(log)
    return weights


def gather_votes(symbol):
    votes = {}
    for name in AGENTS:
        try:
            votes[name] = AGENT_FUNCS[name](symbol)
        except Exception as exc:
            votes[name] = {"vote": 0, "confidence": 0, "note": f"err {type(exc).__name__}"}
    return votes


def read(symbol="BTCUSDT", do_learn=True):
    symbol = symbol.upper()
    weights = load_weights()
    votes = gather_votes(symbol)
    result = aggregate(votes, weights)
    result["symbol"] = symbol
    result["weights"] = weights
    try:
        price = _price(symbol)
        if do_learn:
            learn(symbol, price, weights)
        _record(symbol, votes, result, price)
        result["price"] = price
    except Exception:
        pass
    result["notes"] = {n: v.get("note") for n, v in votes.items()}
    return result


def build_report(r):
    lines = [
        f"=== CERVEAU (essaim) {r['symbol']} ===",
        f"BIAIS : {r['bias']}  |  consensus {r['consensus']:+.2f}  |  conviction {r['conviction']:.2f}",
        "",
        "Agents (vote · conf · poids appris) :",
    ]
    for a in r["agents"]:
        note = r.get("notes", {}).get(a["agent"], "")
        lines.append(f"- {a['agent']:<11} {a['vote']:+.2f} · {a['conf']:.2f} · w{a['weight']:.2f}  | {note}")
    lines.append("")
    lines.append("Aide à la décision adaptative, LECTURE SEULE. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    import sys
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(read(symbol)))


if __name__ == "__main__":
    main()
