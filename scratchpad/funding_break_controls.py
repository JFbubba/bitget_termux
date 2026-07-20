#!/usr/bin/env python3
"""Deux CONTRÔLES pour discriminer méthodologie vs régime de marché.

C1 — PLACEBO : rejouer le même test sur des dates de rupture FICTIVES. Si la chute de
     variance apparaît aussi à des dates arbitraires, ce n'est pas une rupture.
C2 — VOLATILITÉ DU PRIX : une accalmie de marché ferait baisser la vol du PRIX en même
     temps que celle du funding. Si le funding se lisse SANS que le prix se calme, c'est
     l'instrument qui a changé, pas le marché.
Lecture seule, aucun ordre.
"""
import sys, glob, os, datetime, statistics as st
sys.path.insert(0, "/root/bitget_termux_repo")
import funding_history as fh

D = lambda y, m, d: datetime.datetime(y, m, d, tzinfo=datetime.UTC).timestamp() * 1000
VRAIE = D(2026, 7, 10)
PLACEBOS = [D(2026, 5, 10), D(2026, 5, 25), D(2026, 6, 10), D(2026, 6, 25), VRAIE]


def ratio_var(rows, coupe, fenetre_j=10):
    """Variance sur les `fenetre_j` jours APRÈS la coupe / variance avant la coupe."""
    fin = coupe + fenetre_j * 86400_000
    av = [r[1] for r in rows if r[0] < coupe]
    ap = [r[1] for r in rows if coupe <= r[0] < fin]
    if len(av) < 30 or len(ap) < 15:
        return None
    va, vb = st.pvariance(av), st.pvariance(ap)
    return vb / va if va > 0 else None


def main():
    syms = [os.path.basename(p)[8:-5]
            for p in sorted(glob.glob("/root/bitget_termux_repo/data_history/FUNDING_*.json"))]
    data = {s: fh.load(s) for s in syms}
    data = {s: r for s, r in data.items() if r}

    print("=== C1 — PLACEBO : même test à des dates de rupture FICTIVES ===")
    print("(fenêtre de 10 j après chaque coupe, pour comparer des choses comparables)")
    for c in PLACEBOS:
        lab = datetime.datetime.fromtimestamp(c / 1000, datetime.UTC).strftime("%Y-%m-%d")
        rs = [x for x in (ratio_var(r, c) for r in data.values()) if x]
        if not rs:
            print(f"  {lab}  (pas assez de données)")
            continue
        sous1 = sum(1 for x in rs if x < 1)
        etoile = "   <-- LA VRAIE" if c == VRAIE else ""
        print(f"  {lab}  n={len(rs):2d}  variance après/avant : médiane {st.median(rs):6.3f}  "
              f"· réduite sur {sous1}/{len(rs)}{etoile}")

    print()
    print("=== C2 — VOLATILITÉ DU PRIX sur les MÊMES fenêtres ===")
    print("(si le marché s'était calmé, la vol du prix baisserait AUSSI)")
    try:
        import candles_history as ch
    except Exception as e:
        print("  candles_history indisponible :", type(e).__name__)
        return
    lignes = []
    for s in list(data)[:14]:
        try:
            c = ch.load(s, "1H") if hasattr(ch, "load") else None
        except Exception:
            c = None
        if not c:
            continue
        # c : [[ts_ms, o, h, l, cl, v], ...]
        def rets(a, b):
            xs = [row for row in c if a <= row[0] < b]
            out = []
            for i in range(1, len(xs)):
                p0, p1 = float(xs[i - 1][4]), float(xs[i][4])
                if p0 > 0:
                    out.append((p1 - p0) / p0)
            return out
        av = rets(VRAIE - 30 * 86400_000, VRAIE)
        ap = rets(VRAIE, VRAIE + 10 * 86400_000)
        if len(av) < 50 or len(ap) < 20:
            continue
        va, vb = st.pvariance(av), st.pvariance(ap)
        if va > 0:
            lignes.append((s, vb / va))
    if not lignes:
        print("  pas de bougies exploitables — contrôle NON concluant, à dire tel quel")
        return
    for s, r in lignes:
        print(f"  {s:12s} variance des rendements 1H après/avant : {r:6.3f}")
    rs = [r for _, r in lignes]
    print(f"  MÉDIANE vol du PRIX après/avant : {st.median(rs):.3f} "
          f"· réduite sur {sum(1 for r in rs if r < 1)}/{len(rs)}")


if __name__ == "__main__":
    main()
