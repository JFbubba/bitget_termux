"""
ladder_check.py — ERR-001 : échelle COMPLÈTE M1·M5·M15·M30·H1·H4·D1·W1.
On suit UN signal momentum canonique (momentum8) + supertrend à travers TOUTE
l'échelle pour voir OÙ l'IC bascule de réversion (h court) à momentum (h long/TF long).
BTCUSDT a les 8 TF ; ETHUSDT idem. Lecture seule.
"""
import numpy as np
import audit_core as ac
import signals_indep as si

# tf-ladder-ok : échelle complète explicite (M1..W1) — c'est le test ERR-001 lui-même.
LADDER = [("1m", 8), ("5m", 4), ("15m", 4), ("30m", 2),
          ("1H", 2), ("4H", 1), ("1D", 1), ("1W", 1)]
HZ = (1, 4, 24, 96)


def run(sym):
    print(f"\n########## ÉCHELLE COMPLÈTE — {sym} — IC de rang (t inter-plis) ##########")
    print("momentum8 (haut = a monté) : IC<0 réversion, IC>0 momentum\n")
    print(f"{'TF':<5}{'n':>7} " + "".join(f"  h={hh:<3}(t)    " for hh in HZ))
    for gran, stride in LADDER:
        try:
            d = ac.load(sym, gran)
        except Exception:
            print(f"{gran:<5}  (absent)"); continue
        c = d["c"]; n = len(c)
        if n < 400:
            print(f"{gran:<5}{n:>7}  (trop court)"); continue
        feat = si.momentum8(c)
        grid = np.arange(120, n - max(HZ), stride)
        row = f"{gran:<5}{n:>7} "
        for hh in HZ:
            fwd = ac.fwd_logret(c, hh)[grid]
            r = ac.ic_across_folds(grid.astype(float), feat[grid], fwd, hh, method="rank")
            if r:
                row += f" {r[0]:+.3f}({r[1]:+4.1f})"
            else:
                row += f" {'--':>11}"
        print(row)


if __name__ == "__main__":
    for s in ("BTCUSDT", "ETHUSDT"):
        run(s)
    print("\nLecture : négatif à h court sur TOUS les TF rapides = réversion réelle ;")
    print("le signe remonte vers 0/positif quand h grandit et/ou le TF s'allonge.")
