#!/usr/bin/env python3
"""Dissection qml_shadow : l'IC live +0.042 est-il STABLE (edge réel injustement gaté)
ou CONCENTRÉ en régime calme (chance de régime -> le gate a raison) ? LECTURE SEULE.
Réutilise l'appariement vote↔rendement forward de live_ic_audit + le juge agent_validation."""
import math
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, "/root/bitget_termux_repo")
import live_ic_audit as la
import agent_validation as av

HORIZON = 3600
VOICE = "qml_shadow"


def pairs_voice(voice=VOICE, horizon=HORIZON):
    entrees = la.charger_entrees(la.OVERLAY)
    par_sym = defaultdict(list)
    for e in entrees:
        par_sym[e["symbol"]].append(e)
    out = []
    for s, rows in par_sym.items():
        rows.sort(key=lambda x: x.get("ts", 0))
        for i, e in enumerate(rows):
            j = next((k for k in range(i + 1, len(rows)) if rows[k]["ts"] - e["ts"] >= horizon), None)
            if j is None:
                continue
            try:
                fwd = math.log(rows[j]["price"] / e["price"])
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            v = (e.get("votes") or {}).get(voice)
            vote = v.get("vote") if isinstance(v, dict) else v
            if vote is None:
                continue
            out.append((e["ts"], float(vote), fwd))
    out.sort()
    return out


def line(tag, chunk):
    vv = [c[1] for c in chunk]
    ff = [c[2] for c in chunk]
    m = av.evaluate(vv, ff)
    vol = st.mean(abs(f) for f in ff) * 1e4 if ff else 0
    drift = st.mean(ff) * 1e4 if ff else 0
    t0 = datetime.fromtimestamp(chunk[0][0], timezone.utc).strftime("%m-%d %H:%M")
    t1 = datetime.fromtimestamp(chunk[-1][0], timezone.utc).strftime("%m-%d %H:%M")
    pic = m.get("pic"); pic_t = m.get("pic_t"); ic = m.get("ic")
    print(f"{tag:<10} [{t0}→{t1}] n={m.get('n'):>5} | "
          f"pearsonIC {0 if pic is None else pic:+.4f} (t{0 if pic_t is None else pic_t:+.1f}) · "
          f"rank {0 if ic is None else ic:+.4f} | vol {vol:.0f}bps · drift {drift:+.0f}bps")


def main():
    P = pairs_voice()
    print(f"=== DISSECTION {VOICE} — {len(P)} paires vote↔fwd({HORIZON//60}min), lecture seule ===\n")
    line("GLOBAL", P)
    print("\n-- par tranches temporelles (6) : stabilité dans le temps --")
    N = 6
    sz = len(P) // N
    for b in range(N):
        chunk = P[b * sz:(b + 1) * sz] if b < N - 1 else P[b * sz:]
        if chunk:
            line(f"t{b}", chunk)
    print("\n-- par |drift| de la fenêtre : signal en CHOP vs TENDANCE --")
    # trie chaque paire par |drift local| approché = |fwd| ; sépare calme vs agité
    med = st.median(abs(f) for _, _, f in P)
    calme = [p for p in P if abs(p[2]) <= med]
    agite = [p for p in P if abs(p[2]) > med]
    line("CALME", calme)
    line("AGITE", agite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
