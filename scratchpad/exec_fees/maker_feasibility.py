"""Classement de FAISABILITÉ MAKER par symbole — prêt à dégainer pour étendre
`FUTURES_MAKER_SYMBOLS` après validation BTC. LECTURE SEULE (ticker + bougies cache).

Un bon candidat maker (post-only au bid, repli taker après FUTURES_MAKER_WAIT_S) :
  • spread SERRÉ         -> le post-only remplit sans que le prix parte ; faible regret si repli
  • volume ÉLEVÉ         -> le bid se fait taper (probabilité de fill maker)
  • faible mouvement 12s -> pas de dérive adverse pendant l'attente avant repli taker
Économie maker si fill : ~4 bps de frais (taker 6 -> maker 2) + capture d'une partie du spread.
Risque : sur symbole fin/volatil, le post-only rate -> repli taker à un PIRE prix.
"""
import json, math, time, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # racine du dépôt
import numpy as np
import futures_executor as fe
import bitget_hub_bridge as hub
from numeric_utils import safe_float
import candles_history as ch
import universe

WAIT_S = float(fe._cfg("FUTURES_MAKER_WAIT_S", 12) if hasattr(fe, "_cfg") else 12)
OUT = os.path.join(os.path.dirname(__file__), "maker_feasibility.json")


def ticker(sym):
    d = hub._read(["futures", "futures_get_ticker", "--productType", fe.PRODUCT_TYPE, "--symbol", sym])
    rows = (d or {}).get("data") or []
    return rows[0] if rows else {}


def vol_1m_bps(sym, n=120):
    try:
        rows = ch.load(sym, "1m")
        if not rows or len(rows) < 30:
            return None
        c = np.array([r[4] for r in sorted(rows, key=lambda x: x[0])[-n:]], float)
        lr = np.diff(np.log(np.clip(c, 1e-12, None)))
        return float(np.std(lr)) * 1e4
    except Exception:
        return None


def analyse(sym):
    r = ticker(sym)
    bid, ask = safe_float(r.get("bidPr")), safe_float(r.get("askPr"))
    if not (bid and ask and bid > 0 and ask > 0):
        return {"sym": sym, "lisible": False}
    mid = 0.5 * (bid + ask)
    spread_bps = (ask - bid) / mid * 1e4
    bidsz, asksz = safe_float(r.get("bidSz")) or 0.0, safe_float(r.get("askSz")) or 0.0
    top_depth_usd = min(bidsz, asksz) * mid
    vol24_usd = safe_float(r.get("usdtVolume")) or 0.0
    sig1m = vol_1m_bps(sym)
    move12 = (sig1m * math.sqrt(WAIT_S / 60.0)) if sig1m is not None else None
    # score : liquidité (log$) pénalisée par spread et dérive 12s (plus haut = meilleur maker)
    score = math.log10(max(vol24_usd, 1.0))
    score -= spread_bps / 5.0
    score -= (move12 / 5.0) if move12 is not None else 2.0
    return {"sym": sym, "lisible": True, "mid": round(mid, 6),
            "spread_bps": round(spread_bps, 2), "top_depth_usd": round(top_depth_usd, 0),
            "vol24_musd": round(vol24_usd / 1e6, 1),
            "sig1m_bps": round(sig1m, 1) if sig1m is not None else None,
            "move12s_bps": round(move12, 2) if move12 is not None else None,
            "score": round(score, 2)}


def verdict(a):
    """Tiers interprétables (ET sur les 3 axes). move12s absent -> prudent."""
    if not a.get("lisible"):
        return "ILLISIBLE"
    sp, v, m = a["spread_bps"], a["vol24_musd"], a["move12s_bps"]
    m = 99 if m is None else m
    if v >= 200 and sp <= 4 and m <= 4:
        return "PRIORITÉ"        # dégainer en premier
    if v >= 50 and sp <= 10 and m <= 8:
        return "OK"              # 2e vague
    return "RISQUÉ"              # garder taker


def main():
    syms = universe.symbols()
    res = []
    for s in syms:
        try:
            a = analyse(s)
        except Exception as e:
            a = {"sym": s, "lisible": False, "err": str(e)[:60]}
        a["verdict"] = verdict(a)
        res.append(a)
        time.sleep(0.15)   # GET poli
    res.sort(key=lambda x: (x.get("score") is not None, x.get("score", -1e9)), reverse=True)

    print(f"=== FAISABILITÉ MAKER par symbole (attente post-only {WAIT_S:.0f}s · lecture seule) ===")
    print(f"{'sym':<10}{'spread':>7}{'vol24h':>9}{'depth$':>9}{'σ1m':>6}{'move12s':>8}{'score':>7}  verdict")
    print(f"{'':<10}{'bps':>7}{'M$':>9}{'top':>9}{'bps':>6}{'bps':>8}{'':>7}")
    for a in res:
        if not a.get("lisible"):
            print(f"{a['sym']:<10}  (illisible)"); continue
        print(f"{a['sym']:<10}{a['spread_bps']:>7.2f}{a['vol24_musd']:>9.1f}"
              f"{a['top_depth_usd']:>9.0f}{str(a['sig1m_bps']):>6}"
              f"{str(a['move12s_bps']):>8}{a['score']:>7.2f}  {a['verdict']}")

    prio = [a["sym"] for a in res if a["verdict"] == "PRIORITÉ"]
    ok = [a["sym"] for a in res if a["verdict"] == "OK"]
    print(f"\n-> PRIORITÉ (dégainer) : {','.join(prio) or '(aucun)'}")
    print(f"-> 2e vague (OK)       : {','.join(ok) or '(aucun)'}")
    print(f"-> RISQUÉ (rester taker): {','.join(a['sym'] for a in res if a['verdict']=='RISQUÉ') or '(aucun)'}")
    reco = ",".join(prio) if prio else "BTCUSDT"
    print(f"\nPRÊT À DÉGAINER (après validation BTC) : FUTURES_MAKER_SYMBOLS={reco}")
    print(f"puis élargir à : FUTURES_MAKER_SYMBOLS={','.join(prio + ok) or 'BTCUSDT'}")

    snap = {"ts": time.time(), "wait_s": WAIT_S, "univers": syms,
            "prioritte": prio, "ok": ok, "reco_immediate": reco,
            "reco_elargie": prio + ok, "rangs": res}
    json.dump(snap, open(OUT, "w"), ensure_ascii=False, indent=1, default=str)
    print(f"\nsnapshot -> {OUT}")


if __name__ == "__main__":
    main()
