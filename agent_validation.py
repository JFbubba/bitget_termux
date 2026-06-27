"""
agent_validation.py — protocole T5 : MESURER quels agents ajoutent de l'alpha
hors-échantillon, au lieu de leur donner du poids à l'aveugle.

Classement : SAFE. Pur/statistique, lecture seule, AUCUN ordre. Ne MODIFIE pas les
poids du cerveau — il PROPOSE (advisory).

Ancré recherche (arXiv vérifiés §25) :
  • Rank IC de Spearman (corrélation monotone vote→rendement futur) — AlphaEval 2508.13174 ;
  • Probabilistic Sharpe Ratio (PSR) — Bailey & López de Prado : proba que le vrai
    Sharpe > 0, en tenant compte de la SKEWNESS/KURTOSIS et de la LONGUEUR d'échantillon ;
  • Deflated Sharpe Ratio (DSR) — déflate pour le NOMBRE d'agents testés (multiple
    testing) : SR0 = max attendu sous H0 sur N essais. Réf. 2603.09219 ;
  • Purge (rendements futurs NON CHEVAUCHANTS, pas=horizon) pour éviter la fuite par
    auto-corrélation des labels — López de Prado.
Honnêteté (2501.03938, 2512.12924) : les historiques crypto sont COURTS -> faible
puissance statistique ; un IC ~0.04 est NORMAL ; on rapporte n, p-value et la mise en
garde plutôt qu'une courbe de backtest flatteuse.

Deux chemins :
  1) replay des agents PURS sur l'historique de bougies (simons/savant/geometric/
     divergent) — utilisable IMMÉDIATEMENT ;
  2) évaluation de TOUS les agents depuis brain_log.json (votes réels journalisés) —
     se renforce au fil du temps.
"""

import math

import numpy as np

GAMMA = 0.5772156649015329          # constante d'Euler-Mascheroni
EULER_E = math.e


# ---------- normale : CDF / quantile (purs) ----------

def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _erfinv(y):
    y = max(-0.999999, min(0.999999, y))
    a = 0.147
    ln = math.log(1 - y * y)
    t = 2 / (math.pi * a) + ln / 2
    return math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), y)


def _nppf(p):
    """Quantile normal inverse Φ⁻¹(p). Pur."""
    p = min(1 - 1e-9, max(1e-9, p))
    return math.sqrt(2.0) * _erfinv(2 * p - 1)


# ---------- Rank IC (Spearman) ----------

def _rankdata(a):
    a = np.asarray(a, dtype=float)
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(len(a), dtype=float)
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    csum = np.cumsum(counts); starts = csum - counts
    return ((starts + csum - 1) / 2.0)[inv]


def rank_ic(pred, fwd):
    """Rank IC de Spearman ∈ [−1,1] entre prédictions et rendements futurs. Pur."""
    a, b = np.asarray(pred, float), np.asarray(fwd, float)
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    ra, rb = _rankdata(a[:n]), _rankdata(b[:n])
    ra -= ra.mean(); rb -= rb.mean()
    d = math.sqrt(float((ra ** 2).sum()) * float((rb ** 2).sum()))
    return float((ra * rb).sum() / d) if d > 0 else 0.0


def ic_tstat(ic, n):
    """t-stat de l'IC (≈ significativité). Pur."""
    if n < 3 or abs(ic) >= 1:
        return 0.0
    return float(ic * math.sqrt((n - 2) / (1 - ic ** 2)))


# ---------- Sharpe / PSR / DSR ----------

def sharpe(returns):
    """Sharpe PAR PÉRIODE (non annualisé) = moyenne/écart-type. Pur."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 1e-12 else 0.0


def _skew_kurt(returns):
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 3:
        return 0.0, 3.0
    m = r.mean(); sd = r.std()
    if sd <= 1e-12:
        return 0.0, 3.0
    z = (r - m) / sd
    return float((z ** 3).mean()), float((z ** 4).mean())   # kurtosis NON-excess (normale=3)


def psr(sr, n, skew=0.0, kurt=3.0, sr_star=0.0):
    """Probabilistic Sharpe Ratio : P(vrai SR > sr_star) compte tenu de n, skew, kurt.
    Bailey & López de Prado. Pur. sr et sr_star = Sharpe PAR PÉRIODE."""
    if n < 2:
        return 0.5
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr ** 2))
    return _ncdf(((sr - sr_star) * math.sqrt(n - 1)) / denom)


def expected_max_sharpe(n_trials, var_sr):
    """Sharpe MAXIMAL attendu sous H0 (vrai SR=0) sur n_trials essais indépendants.
    Bailey & López de Prado. var_sr = variance des Sharpe estimés entre essais. Pur."""
    if n_trials < 2 or var_sr <= 0:
        return 0.0
    z1 = _nppf(1.0 - 1.0 / n_trials)
    z2 = _nppf(1.0 - 1.0 / (n_trials * EULER_E))
    return math.sqrt(var_sr) * ((1.0 - GAMMA) * z1 + GAMMA * z2)


def deflated_sharpe(sr, n, skew, kurt, n_trials, var_sr):
    """Deflated Sharpe Ratio : PSR avec benchmark = max attendu sous H0 sur n_trials
    essais (déflate le multiple testing). Pur. Retourne P(SR réel > SR0_max)."""
    sr0 = expected_max_sharpe(n_trials, var_sr)
    return psr(sr, n, skew, kurt, sr_star=sr0)


# ---------- rendements futurs purgés (non chevauchants) ----------

def purged_forward_returns(closes, horizon, step=None):
    """Indices t et rendements futurs (close[t+h]/close[t]−1) NON CHEVAUCHANTS
    (pas = horizon) pour éviter la fuite par auto-corrélation des labels. Pur.
    Retourne (idx, fwd)."""
    p = [float(c) for c in closes if c and c > 0]
    h = max(1, int(horizon))
    s = h if step is None else max(1, int(step))
    idx, fwd = [], []
    for t in range(0, len(p) - h, s):
        idx.append(t)
        fwd.append(p[t + h] / p[t] - 1.0)
    return idx, fwd


# ---------- évaluation d'un jeu (vote, rendement futur) ----------

def evaluate(votes, fwd):
    """Métriques OOS d'un agent : Rank IC (+t), hit-rate directionnel, Sharpe de la
    stratégie sign(vote)·fwd, PSR. PUR."""
    v, f = np.asarray(votes, float), np.asarray(fwd, float)
    n = min(len(v), len(f))
    if n < 5:
        return {"n": int(n), "ic": 0.0, "ic_t": 0.0, "hit": None, "sharpe": 0.0, "psr": 0.5}
    v, f = v[:n], f[:n]
    ic = rank_ic(v, f)
    strat = np.sign(v) * f                      # rendement directionnel de l'agent
    nz = np.sign(v) != 0
    hit = float((np.sign(v[nz]) == np.sign(f[nz])).mean()) if nz.any() else None
    sr = sharpe(strat)
    sk, ku = _skew_kurt(strat)
    return {"n": int(n), "ic": round(ic, 4), "ic_t": round(ic_tstat(ic, n), 2),
            "hit": round(hit, 3) if hit is not None else None,
            "sharpe": round(sr, 4), "skew": round(sk, 3), "kurt": round(ku, 3),
            "psr": round(psr(sr, n, sk, ku), 4), "_strat_sharpe_raw": sr}


# ---------- chemin 1 : replay des agents PURS sur bougies ----------

def _closes(candles):
    return [c[4] for c in candles if len(c) >= 5]


def _sig_simons(candles):
    import simons_agent
    return simons_agent.signal(_closes(candles)).get("vote", 0.0)


def _sig_savant(candles):
    import savant_agent
    return savant_agent.signal(candles).get("vote", 0.0)


def _sig_geometric(candles):
    import geometric_agent
    return geometric_agent.signal(_closes(candles)).get("vote", 0.0)


def _sig_divergent(candles):
    import swarm_brain
    return swarm_brain.divergent_score(_closes(candles))


PURE_AGENTS = {"simons": _sig_simons, "savant": _sig_savant,
               "geometric": _sig_geometric, "divergent": _sig_divergent}


def replay(signal_fn, candles, horizon, warmup=80, step=None):
    """Rejoue un signal pur sur l'historique : vote_t = f(bougies[:t+1]), rendement
    futur close[t+h]/close[t]−1. Pas de look-ahead. Pas = horizon (purge). Pur-ish
    (best-effort sur le signal). Retourne (votes, fwd)."""
    h = max(1, int(horizon)); s = h if step is None else max(1, int(step))
    closes = _closes(candles)
    votes, fwd = [], []
    for t in range(warmup, len(closes) - h, s):
        try:
            vt = signal_fn(candles[:t + 1])
        except Exception:
            vt = 0.0
        votes.append(float(vt or 0.0))
        fwd.append(closes[t + h] / closes[t] - 1.0)
    return votes, fwd


def rank_pure_agents(candles, horizon=8, warmup=80):
    """Évalue + classe les agents PURS sur l'historique de bougies, avec DSR déflaté
    pour le NOMBRE d'agents testés. Retourne {agents:[...trié...], deflation:{...}}."""
    raw, series = {}, {}
    for name, fn in PURE_AGENTS.items():
        votes, fwd = replay(fn, candles, horizon, warmup)
        raw[name] = evaluate(votes, fwd)
        series[name] = (votes, fwd)
    sharpes = [m["_strat_sharpe_raw"] for m in raw.values() if m["n"] >= 5]
    var_sr = float(np.var(sharpes, ddof=1)) if len(sharpes) >= 2 else 0.0
    n_trials = max(2, len(sharpes))
    out = []
    for name, m in raw.items():
        sr = m["_strat_sharpe_raw"]
        dsr = deflated_sharpe(sr, m["n"], m.get("skew", 0.0), m.get("kurt", 3.0),
                              n_trials, var_sr) if m["n"] >= 5 else 0.0
        # haircut de Sharpe (2501.03938) : fraction du Sharpe qui survit OOS, et OOS attendu
        rr = replication_ratio(m["n"], sr=abs(sr)) if m["n"] > 2 else None
        votes, fwd = series[name]
        wfa = walk_forward_quorum(votes, fwd)
        m = {k: v for k, v in m.items() if not k.startswith("_")}
        m["agent"] = name; m["dsr"] = round(dsr, 4)
        m["repl_ratio"] = round(rr, 3) if rr is not None else None
        m["oos_sharpe"] = round(sr * rr, 4) if rr is not None else None
        m["wfa_pass"] = wfa["passed"]; m["wfa_frac"] = wfa["pass_frac"]
        out.append(m)
    out.sort(key=lambda d: (d["dsr"], d["ic"]), reverse=True)
    return {"agents": out, "deflation": {"n_trials": n_trials, "var_sharpe": round(var_sr, 6),
            "sr0_max": round(expected_max_sharpe(n_trials, var_sr), 4)}, "horizon": horizon}


# ---------- chemin 2 : évaluation de TOUS les agents depuis brain_log ----------

def evaluate_from_log(log, horizon_entries=1):
    """Évalue chaque agent depuis brain_log.json : (vote journalisé, rendement futur
    réalisé) sur les entrées du même symbole. PUR. horizon_entries = nb d'entrées en
    avant pour le rendement. Best-effort (peu de données au début)."""
    by_symbol = {}
    for e in log:
        by_symbol.setdefault(e.get("symbol"), []).append(e)
    pairs = {}                                  # agent -> [(vote, fwd)]
    for sym, entries in by_symbol.items():
        entries = [e for e in entries if e.get("price")]
        for i in range(len(entries) - horizon_entries):
            p0 = entries[i]["price"]; p1 = entries[i + horizon_entries]["price"]
            if not p0 or not p1:
                continue
            fwd = p1 / p0 - 1.0
            for ag, vote in (entries[i].get("votes") or {}).items():
                pairs.setdefault(ag, []).append((float(vote), fwd))
    out = []
    for ag, pv in pairs.items():
        votes = [x[0] for x in pv]; fwd = [x[1] for x in pv]
        m = evaluate(votes, fwd); m = {k: v for k, v in m.items() if not k.startswith("_")}
        m["agent"] = ag
        out.append(m)
    out.sort(key=lambda d: (d.get("ic", 0)), reverse=True)
    return {"agents": out, "n_entries": len(log)}


def suggest_weight_priors(ranked, floor=0.4, cap=1.8):
    """ADVISORY : propose des poids a priori bornés à partir du DSR (ou IC). NE MODIFIE
    RIEN. Un agent à DSR/IC élevé -> poids > 1 ; non significatif -> vers le plancher.
    Pur. Retourne {agent: poids}. À CONFIRMER avant toute application au cerveau."""
    out = {}
    for m in ranked.get("agents", []):
        score = m.get("dsr", None)
        if score is None:
            score = _ncdf(m.get("ic_t", 0.0))   # repli sur la significativité de l'IC
        out[m["agent"]] = round(float(floor + (cap - floor) * max(0.0, min(1.0, score))), 3)
    return out


# ---------- haircut de Sharpe : replication ratio (arXiv:2501.03938) ----------

def true_sharpe_to_beta2(sr):
    """Inverse β² depuis le vrai Sharpe : SR = β²/√(2β⁴+β²) -> β² = SR²/(1−2SR²). PUR.
    None si SR² ≥ 0.5 (inatteignable avec un seul signal). Réf. 2501.03938."""
    s2 = float(sr) ** 2
    if s2 >= 0.5:
        return None
    return s2 / (1.0 - 2.0 * s2)


def replication_ratio(T1, sr=None, beta2=None):
    """Ratio de réplication SR_OOS/SR_IS ∈ (0,1] — fraction du Sharpe IN-SAMPLE qui
    SURVIT hors-échantillon (Eq 3.3 de 2501.03938, cas 1 actif/1 signal). PUR.
    T1 = nb de barres in-sample. Limites : β→∞ ou T1→∞ -> 1. None si non défini."""
    if T1 is None or T1 <= 2:
        return None
    if beta2 is None:
        beta2 = true_sharpe_to_beta2(sr) if sr is not None else None
    if beta2 is None or beta2 < 0:
        return None
    b2, b4 = beta2, beta2 * beta2
    var_is = 2 * b4 + (1 + 15.0 / (T1 - 2) - 2.0 / T1) * b2 + 4.0 / T1 - 3.0 / (T1 + 2) - 1.0 / T1 ** 2
    var_oos = 2 * b4 + (1 + 2.0 / (T1 - 2)) * b2 + 1.0 / (T1 - 2)
    if var_is <= 0 or var_oos <= 0:
        return None
    sr_is = (b2 + 1.0 / T1) / math.sqrt(var_is)
    sr_oos = b2 / math.sqrt(var_oos)
    return float(sr_oos / sr_is) if sr_is > 0 else None


def replication_ratio_multi(T1, p, m, k):
    """Ratio multivarié (Eq 3.4 + constantes 3.1) : p signaux × m actifs, cas pire
    (signaux indépendants, β=k·1). PUR. Pour le bot : p=#agents, m=#symboles, T1=#barres."""
    if T1 <= p + 1 or p < 1 or m < 1:
        return None
    G = (k ** 2) * p * m                          # tr(Gamma)
    G2 = G * G                                     # tr(Gamma²) (cas β=k·1)
    c1 = 1 + (p + 1.0) / (T1 - p - 1)
    c1t = (2 * p + 5.0) / (T1 - p - 1) + 2 * m * (p ** 2 + p + 2 * T1) / (T1 * (T1 - p - 1))
    c2 = m * p / (T1 - p - 1.0)
    c2t = m * p * (2 * m + p + T1 + 4.0) / (T1 * (T1 + 2)) - 2 * m ** 2 * p ** 2 / (T1 ** 2 * (T1 + 2)) - m * p / (T1 - p - 1.0)
    vis = 2 * G2 + (c1 + c1t) * G + c2 + c2t
    voos = 2 * G2 + c1 * G + c2
    if vis <= 0 or voos <= 0:
        return None
    sr_is = (G + p * m / T1) / math.sqrt(vis)
    sr_oos = G / math.sqrt(voos)
    return float(sr_oos / sr_is) if sr_is > 0 else None


# ---------- métriques équité + protocole IS-WFA-OOS (arXiv:2603.09219) ----------

def _equity(returns):
    return np.cumprod(1.0 + np.asarray(returns, dtype=float))


def max_drawdown(returns):
    """Drawdown maximal (MDD ∈ [0,1]) depuis la courbe d'équité. Pur."""
    eq = _equity(returns)
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    return float(np.max((peak - eq) / peak))


def cagr(returns, periods_per_year=252):
    """Taux de croissance annualisé composé. Pur."""
    eq = _equity(returns)
    if len(eq) < 2 or eq[-1] <= 0:
        return 0.0
    yrs = len(eq) / float(periods_per_year)
    return float(eq[-1] ** (1.0 / yrs) - 1.0) if yrs > 0 else 0.0


def calmar(returns, periods_per_year=252):
    """Ratio de Calmar = CAGR / MDD. Pur."""
    mdd = max_drawdown(returns)
    return float(cagr(returns, periods_per_year) / mdd) if mdd > 1e-9 else 0.0


# Benchmark par défaut de l'étude AlgoXpert (2603.09219) — seuils PRÉ-ENGAGÉS.
B_DEFAULT = {"sharpe_ann": 2.0, "calmar": 1.5, "max_dd": 0.07}


def walk_forward_quorum(votes, fwd, n_folds=3, purge=1, q=2.0 / 3.0):
    """Walk-forward PURGÉ (Eq.11 + Alg.1 de 2603.09219) sur la série (vote, rendement).
    PUR. Découpe en n_folds plis chronologiques, retire `purge` échantillons entre
    train et test, évalue l'IC par pli ; PASS si la fraction de plis à IC>0 ≥ quorum q.
    Retourne {folds:[ic...], pass_frac, passed}."""
    v, f = np.asarray(votes, float), np.asarray(fwd, float)
    n = min(len(v), len(f))
    if n < n_folds * 4:
        return {"folds": [], "pass_frac": 0.0, "passed": False, "n": int(n)}
    size = n // n_folds
    ics = []
    for i in range(n_folds):
        a, b = i * size, (i + 1) * size if i < n_folds - 1 else n
        a = min(a + purge, b)                       # purge en tête de pli (anti-fuite)
        if b - a >= 4:
            ics.append(rank_ic(v[a:b], f[a:b]))
    if not ics:
        return {"folds": [], "pass_frac": 0.0, "passed": False, "n": int(n)}
    frac = float(np.mean([1.0 if x > 0 else 0.0 for x in ics]))
    return {"folds": [round(x, 4) for x in ics], "pass_frac": round(frac, 3),
            "passed": bool(frac >= q), "n": int(n)}


# ---------- rapports ----------

def build_report(ranked):
    lines = [f"=== VALIDATION DES AGENTS (T5) · horizon {ranked.get('horizon', '?')} ===",
             "agent        n   RankIC  t    Sharpe  DSR   haircut OOS_Shp WFA"]
    for m in ranked.get("agents", []):
        rr = ('%.2f' % m['repl_ratio']) if m.get('repl_ratio') is not None else ' n/a'
        oos = ('%+.3f' % m['oos_sharpe']) if m.get('oos_sharpe') is not None else '  n/a'
        wfa = '✓' if m.get('wfa_pass') else '·'
        lines.append(f"{m['agent']:<11} {m['n']:>3}  {m.get('ic', 0):>+6.3f} "
                     f"{m.get('ic_t', 0):>4.1f}  {m.get('sharpe', 0):>+7.3f} {m.get('dsr', 0):>5.2f}  "
                     f"{rr:>6}  {oos:>6}  {wfa}({m.get('wfa_frac', 0):.2f})")
    d = ranked.get("deflation", {})
    if d:
        lines.append("")
        lines.append(f"Déflation multiple-testing : {d.get('n_trials')} essais · "
                     f"SR0_max={d.get('sr0_max')} (un agent doit BATTRE ce seuil).")
    lines += ["", "⚠️ Historique crypto COURT -> faible puissance ; un IC ~0.04 est normal.",
              "Mesure LECTURE SEULE, advisory. Aucun ordre. VERDICT: SAFE"]
    return "\n".join(lines)


def run(symbol="BTCUSDT", timeframe="1h", limit=600, horizon=8):
    """Replay live des agents purs sur l'historique + rapport. Best-effort."""
    candles = []
    try:
        import market_sources as ms
        candles = ms.candles(symbol, timeframe, limit)
    except Exception:
        pass
    if not candles:
        try:
            import technicals as tk
            raw = tk.fetch_candles(symbol, timeframe, limit)
            candles = [[int(c["ts"] // 1000), c["open"], c["high"], c["low"], c["close"], c["volume"]] for c in raw]
        except Exception:
            return {"error": "pas de données"}
    if len(candles) < 120:
        return {"error": f"historique insuffisant ({len(candles)} bougies)"}
    return rank_pure_agents(candles, horizon=horizon)


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    res = run(sym)
    if res.get("error"):
        print("Validation indisponible :", res["error"]); return
    print(build_report(res))
    print("\nPoids a priori suggérés (advisory) :", suggest_weight_priors(res))


if __name__ == "__main__":
    main()
