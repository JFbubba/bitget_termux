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


def _cluster_t(votes, fwd, ts, bucket_s=3600):
    """t de l'IC ROBUSTE au clustering par FENÊTRE-TEMPS (façon Fama-MacBeth / cluster-by-period)
    + n_eff. Corrige la NON-INDÉPENDANCE massive de l'audit poolé (§82, mesure-d'abord). Le journal
    timestampe chaque (symbole×cycle) DISTINCTEMENT (pas de ts partagé), donc les ~99k paires
    (symbole×temps) semblent indépendantes ALORS QUE : un agent symbol-AGNOSTIQUE (macro/flows/
    sentiment) émet ~le même vote sur les ~24 symboles ET ~lentement dans le temps -> le vrai n
    ≈ nb de FENÊTRES, pas de paires. On cluster les scores par fenêtre de `bucket_s` (= l'horizon,
    blocs ~non-recouvrants) : la SE clusterisée gonfle quand les obs d'une fenêtre sont corrélées
    -> le |t| déflate honnêtement (agent symbol-agnostique déflaté à fond ; agent à vraie variation
    transversale/temporelle beaucoup moins). n_eff = # fenêtres distinctes. Mesuré en réel : n_eff
    ~224 (vs 99k) ; macro −20,9->−4,0, mais technicals/carry/liquidations s'évaporent (< 2σ).
    PUR (numpy). Retour (ic_t_clust, pic_t_clust, n_eff)."""
    import numpy as np
    v = np.asarray(votes, float)
    f = np.asarray(fwd, float)
    t = list(ts)
    b = max(1.0, float(bucket_s))
    n = min(len(v), len(f), len(t))
    if n < 5:
        return 0.0, 0.0, len({int(x // b) for x in t})
    v, f, t = v[:n], f[:n], t[:n]
    buckets = [int(x // b) for x in t]

    def _z(x):
        sd = x.std()
        return (x - x.mean()) / sd if sd > 0 else np.zeros_like(x)

    def _ct(zx, zy):
        s = zx * zy                                   # score par obs ; IC = moyenne des scores
        ic = float(s.mean())
        acc = defaultdict(float)
        for bk, si in zip(buckets, (s - ic).tolist()):  # somme des scores centrés PAR fenêtre
            acc[bk] += si
        num = sum(u * u for u in acc.values())         # Σ_g (Σ_{i∈g} s_i)²  -> SE clusterisée-période
        se = (num ** 0.5) / n if num > 0 else 0.0
        return round(ic / se, 2) if se > 1e-9 else 0.0

    def _rank(x):
        return np.argsort(np.argsort(x)).astype(float)

    ic_t = _ct(_z(_rank(v)), _z(_rank(f)))            # Spearman (rank, dashboard)
    pic_t = _ct(_z(v), _z(f))                          # Pearson (magnitude, métrique poids §96)
    return ic_t, pic_t, len(set(buckets))


def ic_par_agent(entrees, horizon_s=3600):
    """PUR. {agent: {ic, ic_t, ic_t_clust, pic, pic_t, pic_t_clust, n, n_eff, pct_votants}} :
    vote de chaque agent vs rendement forward au premier point >= horizon_s (par symbole).
    *_t_clust = t ROBUSTES au clustering par fenêtre-horizon (déflate la non-indépendance
    cross-sectionnelle + temporelle, cf. _cluster_t) ; n_eff = # fenêtres (« n : le vrai poids)."""
    import agent_validation as av
    par_sym = defaultdict(list)
    for e in entrees or []:
        par_sym[e["symbol"]].append(e)
    for s in par_sym:
        par_sym[s].sort(key=lambda x: x.get("ts", 0))
    donnees = defaultdict(lambda: ([], [], []))
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
                donnees[ag][2].append(e.get("ts", i))
    out = {}
    for ag, (votes, fwd, ts) in donnees.items():
        if len(votes) < 50:
            continue
        m = av.evaluate(votes, fwd)
        ic_tc, pic_tc, n_eff = _cluster_t(votes, fwd, ts, bucket_s=horizon_s)
        nz = 100.0 * sum(1 for v in votes if v != 0) / len(votes)
        out[ag] = {"ic": m.get("ic"), "ic_t": m.get("ic_t"), "ic_t_clust": ic_tc,
                   "pic": m.get("pic"), "pic_t": m.get("pic_t"), "pic_t_clust": pic_tc,
                   "n": m.get("n"), "n_eff": n_eff, "pct_votants": round(nz, 1)}
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
EPOCHS = Path(__file__).resolve().parent / "voice_epochs.json"


def charger_epochs(chemin=None):
    """§107 — {voix: ts_min}. Quand l'implémentation d'une voix CHANGE (correction,
    réentraînement, étage coupé), ses votes d'ombre antérieurs ne mesurent plus la même
    chose : les garder mélangerait deux populations et fabriquerait un IC qui ne
    correspond à aucune version du code. Fichier COMMITTÉ (c'est une décision de mesure,
    pas de l'état runtime). Best-effort {} : jamais d'exception, jamais de blocage."""
    try:
        d = json.loads(Path(chemin or EPOCHS).read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for voix, v in (d or {}).items():
        if str(voix).startswith("_"):          # clés de documentation (_lisezmoi)
            continue
        try:                                   # une entrée illisible n'invalide pas les AUTRES
            ts = v.get("since_ts") if isinstance(v, dict) else v
            if ts is not None:
                out[str(voix)] = float(ts)
        except Exception:
            continue
    return out


def filtrer_epochs(entrees, epochs):
    """PURE. Retire les votes d'une voix ANTÉRIEURS à son epoch — VOIX PAR VOIX, jamais la
    ligne entière (plusieurs voix partagent le journal d'ombre). Renvoie
    (entrees_filtrees, {voix: n_écartés}) : le compte est rendu VISIBLE, un filtrage
    silencieux serait son propre piège (on croirait mesurer tout l'historique)."""
    if not epochs:
        return entrees, {}
    out, ignores = [], {}
    for e in entrees:
        votes, garde = e.get("votes") or {}, {}
        ts = float(e.get("ts", 0) or 0)
        for voix, v in votes.items():
            if voix in epochs and ts < epochs[voix]:
                ignores[voix] = ignores.get(voix, 0) + 1
            else:
                garde[voix] = v
        if garde:
            out.append({**e, "votes": garde})
    return out, ignores


def overlay_snapshot(horizon_s=3600):
    """IC des VOIX OPT-IN (llm/nn/classics, §77) — même juge que les 14, journal
    séparé (.overlay_votes.jsonl, écrit par _record quand une voix PARLE).
    §107 : les votes antérieurs à l'epoch d'une voix sont ÉCARTÉS (voice_epochs.json)."""
    entrees, ignores = filtrer_epochs(charger_entrees(OVERLAY), charger_epochs())
    res = ic_par_agent(entrees, horizon_s)
    tri = sorted(res.items(), key=lambda x: -(x[1]["ic"] if x[1]["ic"] is not None else -9))
    return {"horizon_s": horizon_s, "agents": [{"agent": a, **m} for a, m in tri],
            "epochs_ignores": ignores}


def snapshot(horizon_s=3600):
    """Audit à l'horizon de trading (1 h par défaut), trié IC décroissant."""
    res = ic_par_agent(charger_entrees(), horizon_s)
    tri = sorted(res.items(), key=lambda x: -(x[1]["ic"] if x[1]["ic"] is not None else -9))
    return {"horizon_s": horizon_s, "agents": [{"agent": a, **m} for a, m in tri]}


def build_report(s=None):
    s = snapshot() if s is None else s
    lignes = [f"=== AUDIT IC LIVE — votes réellement émis, horizon {s['horizon_s'] // 60} min ===",
              "  rankIC = ordinal (dashboard) · pearsonIC = pondéré-magnitude ≈ PnL (métrique RIDGE §78)",
              "  clust = t robuste au clustering-timestamp (déflate la pseudo-réplication symbol-agnostique, §82)"]
    for r in s.get("agents", []):
        pic = r.get("pic"); pic_t = r.get("pic_t"); pic_tc = r.get("pic_t_clust")
        ic_tc = r.get("ic_t_clust"); n = r.get("n"); n_eff = r.get("n_eff")
        pbloc = (f"pearsonIC {pic:+.4f} (t {pic_t:+.2f}·clust {pic_tc:+.2f})" if pic is not None
                 else "pearsonIC —")
        flag = "  ⚠ SIGNES OPPOSÉS" if _signe_divergent(r) else ""
        ghost = ""
        if n_eff and n and n_eff < n * 0.5 and abs(pic_t or 0) >= 3 and abs(pic_tc or 0) < 2:
            ghost = "  ⚠ t POOLÉ FANTÔME (clust < 2σ : significativité illusoire, obs non-indépendantes)"
        lignes.append(f"  {r['agent']:<12} rankIC {r['ic']:+.4f} (t {r['ic_t']:+.2f}·clust {ic_tc:+.2f}) · "
                      f"{pbloc} · n {n}(eff {n_eff}), votants {r['pct_votants']}%{flag}{ghost}")
    if not s.get("agents"):
        lignes.append("  historique insuffisant (< 50 obs/agent)")
    div = [r["agent"] for r in s.get("agents", []) if _signe_divergent(r)]
    if div:
        lignes.append("  ⚠ divergence rankIC↔pearsonIC : " + ", ".join(div)
                      + " — le POIDS suit le pearson (ridge), le dashboard montrait le rank (§96)")
    ovs = overlay_snapshot(s["horizon_s"])
    ov = ovs.get("agents", [])
    lignes.append("--- voix opt-in (llm/nn/classics, §77) ---")
    ign = ovs.get("epochs_ignores") or {}
    if ign:                                    # §107 : jamais d'écartement SILENCIEUX
        lignes.append("  ⓘ votes écartés (epoch de voix, voice_epochs.json) : "
                      + ", ".join(f"{v} −{n}" for v, n in sorted(ign.items())))
    if ov:
        for r in ov:
            lignes.append(f"  {r['agent']:<12} IC {r['ic']:+.4f} (t {r['ic_t']:+.2f}·clust "
                          f"{r.get('ic_t_clust', 0.0):+.2f}, n {r['n']} eff {r.get('n_eff', r['n'])})")
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
