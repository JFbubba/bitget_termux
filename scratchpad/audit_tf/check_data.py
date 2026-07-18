import json, os
from pathlib import Path
DH = Path("/root/bitget_termux_repo/data_history")
GRAN_MS = {"1m":60_000,"5m":300_000,"15m":900_000,"30m":1_800_000,
           "1H":3_600_000,"4H":14_400_000,"1D":86_400_000,"1W":604_800_000}

def check(fn):
    gran = fn.split("_")[-1].replace(".json","")
    step = GRAN_MS.get(gran)
    rows = json.loads((DH/fn).read_text())
    ts = [r[0] for r in rows]
    n = len(ts)
    # monotonie stricte croissante SUR DISQUE (avant tri)
    asc = all(ts[i] < ts[i+1] for i in range(n-1))
    non_dec = all(ts[i] <= ts[i+1] for i in range(n-1))
    dups = n - len(set(ts))
    # desordre : nb d'inversions
    inv = sum(1 for i in range(n-1) if ts[i+1] < ts[i])
    # trous : gaps != step
    gaps_big = 0; max_gap = 0; irregular = 0
    sd = sorted(set(ts))
    for i in range(len(sd)-1):
        d = sd[i+1]-sd[i]
        if step and d != step:
            irregular += 1
            if step and d > step: 
                if d > 5*step: gaps_big += 1
            max_gap = max(max_gap, d)
    import datetime
    utc=datetime.timezone.utc
    d0=datetime.datetime.fromtimestamp(min(ts)/1000,utc)
    d1=datetime.datetime.fromtimestamp(max(ts)/1000,utc)
    span_days=(max(ts)-min(ts))/86400000
    print(f"\n=== {fn} (step={step}ms) ===")
    print(f" n={n}  {d0.date()} -> {d1.date()}  span={span_days:.0f}j")
    print(f" strictement croissant sur disque: {asc}   non-decroissant: {non_dec}")
    print(f" doublons de ts: {dups}   inversions (desordre): {inv}")
    print(f" intervalles irreguliers (!=step): {irregular}   trous >5x step: {gaps_big}   max_gap={max_gap}ms ({max_gap/step:.1f}x step)")

for fn in ["BTCUSDT_1H.json","ETHUSDT_1H.json"]:
    check(fn)
