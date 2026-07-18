"""Matrice de corrélation des rendements (1H) du panier — documente la
DÉCORRÉLATION réelle (surtout inter-classes) et élague les paires > 0.85.
Python système (lecture seule data_history/). Répond à l'exigence proprio :
'des tokens crypto qui ne sont pas corrélés ensemble'.
"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import candles_history as ch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import CLASSES  # noqa: E402  (mapping symbole->classe)

SYMBOLS = list(CLASSES.keys())
THR = 0.85
GRAN = "1H"


def logret_by_ts(sym):
    rows = ch.load(sym, GRAN)
    d = {}
    prev_ts = prev_c = None
    for r in sorted(rows, key=lambda x: x[0]):
        ts, c = int(r[0]), float(r[4])
        if c <= 0:
            continue
        if prev_c:
            d[ts] = np.log(c / prev_c)
        prev_ts, prev_c = ts, c
    return d


def main():
    series = {s: logret_by_ts(s) for s in SYMBOLS}
    series = {s: d for s, d in series.items() if len(d) >= 200}
    syms = list(series.keys())
    common = set.intersection(*[set(d) for d in series.values()]) if syms else set()
    common = sorted(common)
    print(f"Symboles: {len(syms)} · barres 1H communes: {len(common)}")
    if len(common) < 100:
        print("Fenêtre commune trop courte (actions récentes) — corrélations sur paires disponibles.")
    M = np.array([[series[s][t] for t in common] for s in syms])  # syms × T
    C = np.corrcoef(M)

    # paires > seuil (candidates élagage)
    hi = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            if abs(C[i, j]) >= THR:
                hi.append((C[i, j], syms[i], syms[j]))
    hi.sort(reverse=True)
    print(f"\nPaires |corr| >= {THR} (candidates à l'élagage) : {len(hi)}")
    for c, a, b in hi:
        print(f"  {a:9} ~ {b:9} : {c:+.2f}  [{CLASSES[a]} / {CLASSES[b]}]")

    # corrélation moyenne inter-classes
    print("\nCorrélation moyenne INTER-classes (|corr|) :")
    cls_of = {s: CLASSES[s] for s in syms}
    classes = sorted(set(cls_of.values()))
    for ci in range(len(classes)):
        for cj in range(ci, len(classes)):
            vals = [abs(C[i, j]) for i in range(len(syms)) for j in range(len(syms))
                    if i < j and cls_of[syms[i]] == classes[ci] and cls_of[syms[j]] == classes[cj]]
            if vals:
                print(f"  {classes[ci]:14} × {classes[cj]:14} : {np.mean(vals):.2f}")


if __name__ == "__main__":
    main()
