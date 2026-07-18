#!/usr/bin/env python3
"""orderflow_watch.py — §B : veilleur d'edge orderflow aux horizons LONGS (auto-confirmation).

Classement : SAFE. Lecture seule (historique microstructure accumulé), aucun ordre, aucun secret.

Le problème (18/07) : l'edge `trade_sign` GRANDIT avec l'horizon (IC 0.025→0.059 de 30min→1h) mais
aux horizons 4h+ le nombre d'échantillons NON-CHEVAUCHANTS s'effondre (n≈366 à 4h sur 20 j) -> mirage.
Ce veilleur re-mesure PROPREMENT (non-chevauchant, t honnête, net de frais, t DÉFLATÉ par nb d'essais)
au fil de l'accumulation du collecteur, et ALERTE (Telegram) SEULEMENT si un edge net-positif ROBUSTE
émerge. Cron hebdo. Tant que n est trop petit : verdict « accumulation ». Jamais de branchement auto.
"""
import math
import microstructure as ms

FEE_MAKER_RT_BPS = 4.0                       # aller-retour maker futures (2×0,02 %) — plancher réaliste
FEATURES = ["trade_sign", "trade_delta", "ofi"]
HORIZONS = [60, 120, 240, 480, 720]          # ~1h, 2h, 4h, 8h, 12h (pas ≈ 1 min/enreg.)
MIN_N = 200                                  # sous ce n non-chevauchant : pas de verdict (accumulation)
T_ROBUST = 2.5                               # |t| déflaté requis pour crier à l'edge


def _rank(a):
    order = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def _pearson(x, y):
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    syy = sum((v - my) ** 2 for v in y)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0


def spearman(x, y):
    return _pearson(_rank(x), _rank(y))


def measure(rows, feature, h, n_tests=1):
    """PUR. IC non-chevauchant + edge net de frais + t DÉFLATÉ (nb d'essais). rows = historique
    microstructure. Retour {n, ic, t, t_defl, gross_bps, net_maker_bps, robuste}."""
    by = {}
    for r in rows:
        by.setdefault(r.get("symbol"), []).append(r)
    sig, ret = [], []
    for _s, rs in by.items():
        rs = sorted(rs, key=lambda x: x.get("ts", 0))
        for i in range(0, len(rs) - h, h):               # NON-CHEVAUCHANT
            m0, m1, v = rs[i].get("mid"), rs[i + h].get("mid"), rs[i].get(feature)
            if m0 and m1 and v is not None:
                sig.append(float(v)); ret.append(float(m1) / float(m0) - 1.0)
    if len(sig) < MIN_N:
        return {"feature": feature, "h": h, "n": len(sig), "verdict": "accumulation"}
    ic = spearman(sig, ret)
    t = ic * math.sqrt(len(sig))                          # t ≈ IC·√n (échantillons indépendants)
    t_defl = t / (1.0 + math.log(max(n_tests, 1)))        # déflaté par le nb d'essais (anti multi-tests)
    med = sorted(sig)[len(sig) // 2]
    gross = sum((1.0 if sig[i] > med else -1.0) * ret[i] for i in range(len(sig))) / len(sig) * 1e4
    net = gross - FEE_MAKER_RT_BPS
    robuste = abs(t_defl) >= T_ROBUST and net > 0
    return {"feature": feature, "h": h, "n": len(sig), "ic": round(ic, 4), "t": round(t, 2),
            "t_defl": round(t_defl, 2), "gross_bps": round(gross, 2), "net_maker_bps": round(net, 2),
            "robuste": robuste, "verdict": "ROBUSTE" if robuste else "sous-frais/bruit"}


def run(rows=None):
    rows = rows if rows is not None else ms.load_history()
    n_tests = len(FEATURES) * len(HORIZONS)
    out = []
    for feat in FEATURES:
        for h in HORIZONS:
            out.append(measure(rows, feat, h, n_tests=n_tests))
    return {"n_records": len(rows), "n_tests": n_tests, "results": out,
            "robustes": [r for r in out if r.get("robuste")]}


def main():
    rep = run()
    print(f"=== VEILLE EDGE ORDERFLOW (horizons longs) — {rep['n_records']} enreg. ===")
    for r in rep["results"]:
        if r.get("verdict") == "accumulation":
            print(f"  {r['feature']:12} h={r['h']:>3} · n={r['n']} -> accumulation (n<{MIN_N})")
        else:
            print(f"  {r['feature']:12} h={r['h']:>3} · n={r['n']} · IC {r['ic']:+.4f} · t_defl {r['t_defl']:+.2f}"
                  f" · net maker {r['net_maker_bps']:+.2f}bps -> {r['verdict']}")
    if rep["robustes"]:
        msg = "🟢 EDGE ORDERFLOW ROBUSTE détecté : " + " · ".join(
            f"{r['feature']} h={r['h']} net {r['net_maker_bps']:+.2f}bps (t {r['t_defl']:+.2f})" for r in rep["robustes"])
        print(msg)
        try:
            import telegram_notifier as tn
            tn.send_telegram(msg + " — À VÉRIFIER avant tout branchement (mesure-d'abord, banc gelé).")
        except Exception:
            pass
    else:
        print("Aucun edge robuste net-de-frais. (Normal tant que l'accumulation est courte aux horizons longs.)")


if __name__ == "__main__":
    main()
