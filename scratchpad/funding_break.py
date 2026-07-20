#!/usr/bin/env python3
"""Point de rupture funding ~10/07/2026 (échantillon du premium index 1/min -> 1/5 s).
Mesure AVANT/APRÈS par symbole. Lecture seule, aucun ordre."""
import sys, glob, os, datetime, statistics as st
sys.path.insert(0, "/root/bitget_termux_repo")
import funding_history as fh

RUPTURE = datetime.datetime(2026, 7, 10, tzinfo=datetime.UTC).timestamp() * 1000


def autocorr(xs, lag=1):
    n = len(xs)
    if n <= lag + 2:
        return None
    m = sum(xs) / n
    num = sum((xs[i] - m) * (xs[i + lag] - m) for i in range(n - lag))
    den = sum((x - m) ** 2 for x in xs)
    return num / den if den > 0 else None


def stats(xs):
    if len(xs) < 3:
        return None
    return {"n": len(xs), "moy": st.mean(xs), "sd": st.pstdev(xs),
            "med_abs": st.median([abs(x) for x in xs]), "ac1": autocorr(xs)}


def f_test_var(a, b):
    """Rapport de variances + verdict grossier (pas de p-value exacte sans scipy)."""
    if not a or not b or len(a) < 3 or len(b) < 3:
        return None
    va, vb = st.pvariance(a), st.pvariance(b)
    if va <= 0 or vb <= 0:
        return None
    return vb / va


def main():
    print(f"RUPTURE testée : 2026-07-10 (premium index 1/min -> 1/5 s, x12)")
    print(f"{'symbole':12s} {'n_av':>5s} {'n_ap':>5s} {'sd_av':>10s} {'sd_ap':>10s} {'var_ap/av':>10s} "
          f"{'ac1_av':>7s} {'ac1_ap':>7s} {'moy_av':>10s} {'moy_ap':>10s}")
    ratios, ac_av, ac_ap = [], [], []
    for p in sorted(glob.glob("/root/bitget_termux_repo/data_history/FUNDING_*.json")):
        sym = os.path.basename(p)[8:-5]
        rows = fh.load(sym)
        if not rows:
            continue
        av = [r[1] for r in rows if r[0] < RUPTURE]
        ap = [r[1] for r in rows if r[0] >= RUPTURE]
        sa, sb = stats(av), stats(ap)
        if not sa or not sb:
            continue
        ratio = f_test_var(av, ap)
        ratios.append((sym, ratio))
        if sa["ac1"] is not None: ac_av.append(sa["ac1"])
        if sb["ac1"] is not None: ac_ap.append(sb["ac1"])
        print(f"{sym:12s} {sa['n']:5d} {sb['n']:5d} {sa['sd']:10.6f} {sb['sd']:10.6f} "
              f"{(ratio if ratio else 0):10.3f} "
              f"{(sa['ac1'] if sa['ac1'] is not None else 0):7.3f} "
              f"{(sb['ac1'] if sb['ac1'] is not None else 0):7.3f} "
              f"{sa['moy']:10.6f} {sb['moy']:10.6f}")
    rs = [r for _, r in ratios if r]
    print()
    print(f"symboles testés : {len(rs)}")
    if rs:
        print(f"rapport de variance APRÈS/AVANT — médiane {st.median(rs):.3f} · "
              f"min {min(rs):.3f} · max {max(rs):.3f}")
        print(f"  variance RÉDUITE (<1) sur {sum(1 for r in rs if r < 1)}/{len(rs)} symboles")
    if ac_av and ac_ap:
        print(f"autocorrélation lag-1 — médiane AVANT {st.median(ac_av):+.3f} · "
              f"APRÈS {st.median(ac_ap):+.3f}")
    print()
    print("CAVEAT DE PUISSANCE : la rupture date du 10/07 et nous sommes le 20/07 — "
          "10 jours d'après-rupture.")
    print("Un rapport de variance sur ~30-60 points n'a pas la puissance de conclure. "
          "Ceci est un RELEVÉ, pas un test.")


if __name__ == "__main__":
    main()
