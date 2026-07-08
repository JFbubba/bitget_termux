"""
live_ic_audit.py — audit PERMANENT de l'IC live des agents (lecture seule). SAFE.

§60 : l'audit qui a démasqué la saturation EARCP (§51 : poids inversés vs
pouvoir prédictif) était un calcul ad hoc. Le voici en module réutilisable,
branché à la revue hebdo : IC de CHAQUE agent, calculé sur ses VOTES RÉELLEMENT
ÉMIS (brain_log_history), à plusieurs horizons. C'est l'instrument qui, avec
des semaines de données, permettra d'auditer la FORMULATION des 9 agents
non rejouables hors-ligne (liquidations, derivs, orderflow, ...).

Fonctions PURES testables. AUCUN ordre, AUCUN vote modifié.
CLI : python live_ic_audit.py [horizon_s]
"""

import json
import math
from collections import defaultdict, deque
from pathlib import Path

HISTORY = Path(__file__).resolve().parent / "brain_log_history.jsonl"
HORIZONS_S = (900, 3600, 14400)               # 15 min, 1 h, 4 h


def charger_entrees(chemin=None, max_lignes=100_000):
    """Entrées exploitables de brain_log_history (votes + prix). Best-effort [].
    Le cap prend la QUEUE du journal (fenêtre récente) : lu depuis la tête, un
    journal append-only figerait l'instrument sur les données les plus anciennes
    dès qu'il dépasse max_lignes (ERR-006)."""
    entrees = []
    try:
        with open(chemin or HISTORY, "r", encoding="utf-8") as f:
            dernieres = deque(f, maxlen=max_lignes)
        for ligne in dernieres:
            try:
                e = json.loads(ligne)
                if e.get("votes") and e.get("price") and e.get("symbol"):
                    entrees.append(e)
            except Exception:
                continue
    except Exception:
        return []
    return entrees


def ic_par_agent(entrees, horizon_s=3600):
    """PUR. {agent: {ic, ic_t, n, pct_votants}} : vote de chaque agent vs
    rendement forward au premier point >= horizon_s (par symbole)."""
    import agent_validation as av
    par_sym = defaultdict(list)
    for e in entrees or []:
        par_sym[e["symbol"]].append(e)
    for s in par_sym:
        par_sym[s].sort(key=lambda x: x.get("ts", 0))
    donnees = defaultdict(lambda: ([], []))
    for s, rows in par_sym.items():
        for i, e in enumerate(rows):
            j = next((k for k in range(i + 1, len(rows))
                      if rows[k]["ts"] - e["ts"] >= horizon_s), None)
            if j is None:
                continue
            try:
                fwd = math.log(rows[j]["price"] / e["price"])
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            for ag, v in (e.get("votes") or {}).items():
                vote = v.get("vote") if isinstance(v, dict) else v
                if vote is None:
                    continue
                donnees[ag][0].append(float(vote))
                donnees[ag][1].append(fwd)
    out = {}
    for ag, (votes, fwd) in donnees.items():
        if len(votes) < 50:
            continue
        m = av.evaluate(votes, fwd)
        nz = 100.0 * sum(1 for v in votes if v != 0) / len(votes)
        out[ag] = {"ic": m.get("ic"), "ic_t": m.get("ic_t"),
                   "pic": m.get("pic"), "pic_t": m.get("pic_t"), "n": m.get("n"),
                   "pct_votants": round(nz, 1)}
    return out


def _signe_divergent(r):
    """True si Rank IC et Pearson IC d'un agent ont un signe OPPOSÉ, tous deux non
    négligeables (§96 : l'agent vise juste en rang mais se trompe quand il crie fort,
    ou l'inverse — c'est là que le poids ridge et le dashboard racontent deux histoires)."""
    ic, pic = r.get("ic"), r.get("pic")
    if ic is None or pic is None:
        return False
    return ic * pic < 0 and abs(ic) >= 0.01 and abs(pic) >= 0.01


OVERLAY = Path(__file__).resolve().parent / ".overlay_votes.jsonl"


def overlay_snapshot(horizon_s=3600):
    """IC des VOIX OPT-IN (llm/nn/classics, §77) — même juge que les 14, journal
    séparé (.overlay_votes.jsonl, écrit par _record quand une voix PARLE)."""
    res = ic_par_agent(charger_entrees(OVERLAY), horizon_s)
    tri = sorted(res.items(), key=lambda x: -(x[1]["ic"] if x[1]["ic"] is not None else -9))
    return {"horizon_s": horizon_s, "agents": [{"agent": a, **m} for a, m in tri]}


def snapshot(horizon_s=3600):
    """Audit à l'horizon de trading (1 h par défaut), trié IC décroissant."""
    res = ic_par_agent(charger_entrees(), horizon_s)
    tri = sorted(res.items(), key=lambda x: -(x[1]["ic"] if x[1]["ic"] is not None else -9))
    return {"horizon_s": horizon_s, "agents": [{"agent": a, **m} for a, m in tri]}


def build_report(s=None):
    s = snapshot() if s is None else s
    lignes = [f"=== AUDIT IC LIVE — votes réellement émis, horizon {s['horizon_s'] // 60} min ===",
              "  rankIC = ordinal (dashboard) · pearsonIC = pondéré-magnitude ≈ PnL (métrique RIDGE §78)"]
    for r in s.get("agents", []):
        pic = r.get("pic"); pic_t = r.get("pic_t")
        pbloc = (f"pearsonIC {pic:+.4f} (t {pic_t:+.2f})" if pic is not None else "pearsonIC —")
        flag = "  ⚠ SIGNES OPPOSÉS" if _signe_divergent(r) else ""
        lignes.append(f"  {r['agent']:<12} rankIC {r['ic']:+.4f} (t {r['ic_t']:+.2f}) · "
                      f"{pbloc} · n {r['n']}, votants {r['pct_votants']}%{flag}")
    if not s.get("agents"):
        lignes.append("  historique insuffisant (< 50 obs/agent)")
    div = [r["agent"] for r in s.get("agents", []) if _signe_divergent(r)]
    if div:
        lignes.append("  ⚠ divergence rankIC↔pearsonIC : " + ", ".join(div)
                      + " — le POIDS suit le pearson (ridge), le dashboard montrait le rank (§96)")
    ov = overlay_snapshot(s["horizon_s"]).get("agents", [])
    lignes.append("--- voix opt-in (llm/nn/classics, §77) ---")
    if ov:
        for r in ov:
            lignes.append(f"  {r['agent']:<12} IC {r['ic']:+.4f} (t {r['ic_t']:+.2f}, n {r['n']})")
    else:
        lignes.append("  accumule… (< 50 votes parlés par voix)")
    lignes.append("Lecture seule — l'instrument de vérité des poids (§51). VERDICT: SAFE")
    return "\n".join(lignes)


def conviction_par_quantile(entrees=None, horizon_s=3600, quantiles=(0.0, 0.5, 0.7, 0.9)):
    """§89.5 — MESURE du « filtre de conviction » : espérance du rendement forward
    ALIGNÉ au signe du consensus, par quantile de |consensus|. PUR si entrees injecté.
    Verdict du 07/07 (39 973 obs) : plus |c| est FORT, plus l'espérance 1 h est
    NÉGATIVE (top 10 % : −19 bps vs −9 global) — filtre REJETÉ ; à re-mesurer quand
    la cible ridge (§78) aura une semaine de vie dans les poids."""
    from collections import defaultdict
    entrees = charger_entrees() if entrees is None else entrees
    rows_sym = defaultdict(list)
    for e in entrees:
        c = e.get("consensus")
        if c is None or not e.get("price") or not e.get("symbol"):
            continue
        rows_sym[e["symbol"]].append((e["ts"], float(c), float(e["price"])))
    echant = []
    for sym, rows in rows_sym.items():
        rows.sort()
        j = 0
        for i, (ts, c, px) in enumerate(rows):
            if j <= i:
                j = i + 1
            while j < len(rows) and rows[j][0] < ts + horizon_s:
                j += 1
            if j >= len(rows):
                break
            fwd = rows[j][2] / px - 1.0
            if abs(c) > 1e-9:
                echant.append((abs(c), (fwd if c > 0 else -fwd) * 10000))
    echant.sort()
    n = len(echant)
    out = {"n": n, "quantiles": []}
    if n < 200:
        return out
    for q in quantiles:
        sous = [r for _, r in echant[int(n * q):]]
        out["quantiles"].append({"top_pct": round(100 - q * 100), "seuil": round(echant[int(n * q)][0], 3),
                                 "n": len(sous), "esperance_bps": round(sum(sous) / len(sous), 2)})
    return out


def bloc_mfe_mae_reels():
    """Bloc texte MFE/MAE des ROUND-TRIPS RÉELS (via exit_lab, §63) — pour /audit.
    Best-effort : chaîne vide si l'instrument n'est pas disponible. Lecture seule."""
    try:
        import exit_lab
        r = exit_lab.analyser_reels()
    except Exception:
        return ""
    if not isinstance(r, dict):
        return ""
    return ("\n=== MFE/MAE — round-trips RÉELS du bot (§63) ===\n"
            f"  {r.get('note', 'indisponible')}")


def main():
    import sys
    h = int(sys.argv[1]) if len(sys.argv) > 1 else 3600
    print(build_report(snapshot(h)))
    bloc = bloc_mfe_mae_reels()
    if bloc:
        print(bloc)


if __name__ == "__main__":
    main()
