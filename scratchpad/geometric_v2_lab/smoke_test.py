"""Test de fumée : exécute le harnais sur 1D seul (données locales) et imprime
un extrait. LECTURE SEULE."""
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB.parents[1]))
sys.path.insert(0, str(LAB))

import run_lab  # noqa: E402

run_lab.PLAN = [("1D", ["BTCUSDT"], 1, ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"])]
run_lab.LAB = LAB
# ne pas écraser resultats.json du run complet
orig = run_lab.run


def patched_write(*a, **k):
    pass


run_lab.run()
res = json.loads((LAB / "resultats.json").read_text())
tab = res["tables"]["1D"]["BTCUSDT"]
for feat, per_h in tab.items():
    for h, r in per_h.items():
        print(f"{feat:<26}{h:<5} ic_r{r['ic_r']:+.3f} t_r{r['t_r']:+.2f} "
              f"ic_p{r['ic_p']:+.3f} t_p{r['t_p']:+.2f} n{r['n_tot']} "
              f"(base ic_r{r['base_ic_r']:+.3f} t{r['base_t_r']:+.2f}) vol_r{r['vol_ic_r']:+.3f}")
