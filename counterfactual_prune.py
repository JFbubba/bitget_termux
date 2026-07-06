"""
counterfactual_prune.py — CONTREFACTUEL « consensus élagué » (LECTURE SEULE). SAFE.

Question (§68/voie saine) : si on RETIRE du consensus les agents à IC live NÉGATIF
(flows, divergent, orderflow), l'edge du consensus bascule-t-il positif ? On le mesure
sur la MÊME donnée que l'audit IC (`brain_log_history.jsonl`, ~30k votes réellement
émis), SANS rien exécuter et SANS modifier aucun poids : on reconstruit le consensus
avec les poids EARCP courants, puis on met à 0 le poids des agents élagués (ce que fait
`BRAIN_WATCH_AGENTS`), et on compare :

  • IC du consensus (corrélation vote agrégé -> rendement forward) FULL vs ÉLAGUÉ ;
  • W (taux de bonne DIRECTION à l'horizon) et R (proxy de payoff = |move| favorable /
    |move| adverse), puis la fraction de Kelly qui en découle.

⚠️ Métrique DIRECTIONNELLE (signe du rendement à l'horizon, SANS SL/TP) : elle mesure la
qualité du SIGNAL, pas le PnL réalisé (qui dépend des sorties, cf. exit_lab). C'est le bon
instrument pour « l'élagage améliore-t-il l'edge ? ». Advisory : ne change AUCUN poids.

CLI : python counterfactual_prune.py [--prune flows,divergent,orderflow] [--horizon 3600]
      [--threshold 0.2]
"""
import math
from collections import defaultdict

DEFAULT_PRUNE = ["flows", "divergent", "orderflow"]     # IC live négatif significatif (§68)


def _pairs(entrees, weights, exclude, horizon_s):
    """(consensus_pondéré, rendement_forward) par entrée, à l'horizon. PUR.
    Consensus = Σ(vote·poids) / Σ(poids) sur les agents NON exclus (poids exclu -> 0)."""
    exclude = set(exclude or [])
    par_sym = defaultdict(list)
    for e in entrees or []:
        par_sym[e["symbol"]].append(e)
    cons, fwd = [], []
    for s, rows in par_sym.items():
        rows.sort(key=lambda x: x.get("ts", 0))
        for i, e in enumerate(rows):
            j = next((k for k in range(i + 1, len(rows))
                      if rows[k]["ts"] - e["ts"] >= horizon_s), None)
            if j is None:
                continue
            try:
                r = math.log(rows[j]["price"] / e["price"])
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            num = den = 0.0
            for ag, v in (e.get("votes") or {}).items():
                if ag in exclude:
                    continue
                w = float(weights.get(ag, 1.0))
                vote = v.get("vote") if isinstance(v, dict) else v
                if vote is None:
                    continue
                num += float(vote) * w
                den += w
            if den <= 0:
                continue
            cons.append(num / den)
            fwd.append(r)
    return cons, fwd


def _ic(cons, fwd):
    import agent_validation as av
    m = av.evaluate(cons, fwd)
    return {"ic": m.get("ic"), "ic_t": m.get("ic_t"), "n": m.get("n")}


def _directional(cons, fwd, threshold):
    """W (bonne direction | conviction > seuil) et R (payoff proxy = |move| favorable
    moyen / |move| adverse moyen), puis Kelly. PUR."""
    right_moves, wrong_moves = [], []
    for c, r in zip(cons, fwd):
        if abs(c) < threshold or r == 0:
            continue
        if (c > 0) == (r > 0):
            right_moves.append(abs(r))
        else:
            wrong_moves.append(abs(r))
    n = len(right_moves) + len(wrong_moves)
    if n == 0:
        return {"W": None, "R": None, "n": 0, "kelly_f": None}
    W = len(right_moves) / n
    avg_win = (sum(right_moves) / len(right_moves)) if right_moves else 0.0
    avg_loss = (sum(wrong_moves) / len(wrong_moves)) if wrong_moves else 0.0
    R = (avg_win / avg_loss) if avg_loss > 0 else None
    kf = None
    if R and R > 0:
        try:
            import kelly
            kf = kelly.kelly_fraction(W, R)["f_full"]
        except Exception:
            kf = W - (1 - W) / R
    return {"W": round(W, 4), "R": round(R, 4) if R else None, "n": n,
            "kelly_f": round(kf, 4) if kf is not None else None}


def run(prune=None, horizon_s=3600, threshold=0.2, entrees=None, weights=None):
    """Compare le consensus FULL vs ÉLAGUÉ (IC + directionnel + Kelly). Dict résultat."""
    import live_ic_audit as lia
    import swarm_brain as sb
    prune = DEFAULT_PRUNE if prune is None else prune
    entrees = lia.charger_entrees() if entrees is None else entrees
    weights = sb.load_weights() if weights is None else weights

    def _scen(exclude, label):
        cons, fwd = _pairs(entrees, weights, exclude, horizon_s)
        return {"label": label, "excluded": list(exclude),
                **_ic(cons, fwd), "dir": _directional(cons, fwd, threshold)}

    full = _scen([], "FULL (14 agents)")
    pruned = _scen(prune, f"ÉLAGUÉ (-{','.join(prune)})")
    return {"horizon_s": horizon_s, "threshold": threshold,
            "n_entries": len(entrees), "full": full, "pruned": pruned}


def _fmt(sc):
    d = sc["dir"]
    ic = f"IC {sc['ic']:+.4f} (t {sc['ic_t']:+.2f}, n {sc['n']})" if sc.get("ic") is not None else "IC n/a"
    dd = (f"W {d['W']} · R {d['R']} · Kelly f {d['kelly_f']} (n {d['n']})"
          if d.get("W") is not None else "directionnel n/a")
    return f"{sc['label']:<28} {ic}\n{'':<28} {dd}"


def main():
    import argparse
    p = argparse.ArgumentParser(description="Contrefactuel consensus élagué (lecture seule).")
    p.add_argument("--prune", default=",".join(DEFAULT_PRUNE), help="agents à retirer (virgule)")
    p.add_argument("--horizon", type=int, default=3600, help="horizon en s (défaut 1 h)")
    p.add_argument("--threshold", type=float, default=0.2, help="seuil de conviction (défaut 0.2)")
    a = p.parse_args()
    prune = [x.strip() for x in a.prune.split(",") if x.strip()]
    res = run(prune=prune, horizon_s=a.horizon, threshold=a.threshold)
    print(f"=== CONTREFACTUEL CONSENSUS ÉLAGUÉ — horizon {a.horizon // 60} min · "
          f"seuil {a.threshold} · {res['n_entries']} entrées ===")
    print(_fmt(res["full"]))
    print(_fmt(res["pruned"]))
    f, pr = res["full"], res["pruned"]
    d_ic = (pr["ic"] or 0) - (f["ic"] or 0)
    print(f"\nΔ IC (élagué − full) = {d_ic:+.4f}")
    kf_full, kf_pr = f["dir"].get("kelly_f"), pr["dir"].get("kelly_f")
    if kf_full is not None and kf_pr is not None:
        verdict = ("l'élagage FAIT BASCULER l'edge positif" if kf_pr > 0 >= kf_full
                   else "l'élagage améliore l'edge (reste négatif)" if kf_pr > kf_full
                   else "l'élagage n'améliore PAS l'edge")
        print(f"Kelly f : full {kf_full:+.4f} -> élagué {kf_pr:+.4f}  =>  {verdict}")
    print("\nLecture seule — advisory, aucun poids modifié. VERDICT: SAFE")


if __name__ == "__main__":
    main()
