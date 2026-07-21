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


def pearson_ic(pred, fwd):
    """IC de PEARSON ∈ [−1,1] entre prédictions et rendements futurs. Pur.

    Contrairement au Rank IC (ordinal), le Pearson est pondéré par la MAGNITUDE des
    votes — donc plus proche du PnL réel, puisque le bot dimensionne par |vote|. C'est
    la métrique que la cible RIDGE (§78, `_ridge_solve`) optimise. Les deux IC peuvent
    DIVERGER DE SIGNE (§96 : ~5 agents — technicals/derivs/liquidations/carry/geometric) :
    un vote qui vise juste « en rang » mais se trompe quand il crie fort a un Rank IC
    positif et un Pearson négatif. Afficher les DEUX (fin de l'angle mort d'observabilité)."""
    a, b = np.asarray(pred, float), np.asarray(fwd, float)
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[:n] - np.mean(a[:n]), b[:n] - np.mean(b[:n])
    d = math.sqrt(float((a ** 2).sum()) * float((b ** 2).sum()))
    return float((a * b).sum() / d) if d > 0 else 0.0


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
        return {"n": int(n), "ic": 0.0, "ic_t": 0.0, "pic": 0.0, "pic_t": 0.0,
                "hit": None, "sharpe": 0.0, "psr": 0.5}
    v, f = v[:n], f[:n]
    ic = rank_ic(v, f)
    pic = pearson_ic(v, f)                       # §96 : IC pondéré-magnitude (≈ métrique ridge)
    strat = np.sign(v) * f                      # rendement directionnel de l'agent
    nz = np.sign(v) != 0
    hit = float((np.sign(v[nz]) == np.sign(f[nz])).mean()) if nz.any() else None
    sr = sharpe(strat)
    sk, ku = _skew_kurt(strat)
    return {"n": int(n), "ic": round(ic, 4), "ic_t": round(ic_tstat(ic, n), 2),
            "pic": round(pic, 4), "pic_t": round(ic_tstat(pic, n), 2),
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


def _panel_profond():
    """Panel PROFOND multi-symboles de la validation §54 : le MÊME pour replay_annuel
    et cpcv_diagnostic (candles_history 1h, 6 ans, univers cœur — pas seulement BTC).
    Best-effort : {} si l'historique est indisponible (fail-open en aval)."""
    try:
        import candles_history as ch
        donnees = {s: ch.load(s, "1h") for s in
                   ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")}
        return {s: c for s, c in donnees.items() if len(c) > 500}
    except Exception:
        return {}


def replay_annuel(donnees=None, pas=24, horizon=8, warmup=80, agents=None):
    """IC ANNUEL des agents PURS sur l'historique profond (candles_history, §54).
    PUR si `donnees` est injecté ({symbol: bougies}). L'audit du 03/07 a montré que
    des fenêtres récentes, même « indépendantes », peuvent partager le MÊME régime
    (juin-juillet 2026 réversif : geometric §48 y faisait +0.11/+0.17 mais −0.07
    sur l'année) — le rejeu annuel est le 3e juge, câblé dans la porte d'edge :
    pas de promotion LIVE d'un artefact de régime. Retourne
    {agent: {ic, ic_t, n}} ; {} si pas de données (fail-open : la porte annuelle
    ne s'applique que si la mesure existe)."""
    import math
    if donnees is None:
        # LA consultation du holdout profond 6 ans -> consignée au registre d'usage
        # (hygiène anti-contamination : le holdout ne s'ouvre qu'une fois par version).
        # Best-effort ABSOLU : le registre ne casse JAMAIS la validation. Données
        # INJECTÉES (tests/labos) = pas le holdout -> pas de consignation (ERR-019).
        try:
            import holdout_registry
            holdout_registry.consigner("replay_annuel", periode="6y_1h",
                                       note="porte profonde §54")
        except Exception:
            pass
        donnees = _panel_profond()
    if not donnees:
        return {}
    agents = agents or PURE_AGENTS
    out = {}
    for nom, fn in agents.items():
        votes, fwd = [], []
        for s, c in donnees.items():
            # pas AUTO-PLAFONNÉ : ~400 échantillons max par symbole, sinon 6 ans
            # d'historique × HMM par échantillon dépassent le budget du timer de
            # validation (mesuré : > 10 min). Déterministe (fonction de len(c)).
            pas_eff = max(int(pas), (len(c) - warmup) // 400)
            for t_ in range(warmup, len(c) - horizon, pas_eff):
                try:
                    votes.append(float(fn(c[max(0, t_ - 200):t_ + 1]) or 0.0))
                    fwd.append(math.log(float(c[t_ + horizon][4]) / float(c[t_][4])))
                except Exception:
                    continue
        if len(votes) >= 50:
            m = evaluate(votes, fwd)
            out[nom] = {"ic": m.get("ic"), "ic_t": m.get("ic_t"), "n": m.get("n")}
    return out


# ---------- CPCV : Combinatorial Purged Cross-Validation (López de Prado) ----------
# Porté du labo geometric_v2 (scratchpad/geometric_v2_lab/cpcv_demo.py) comme check de
# promotion DURCI : au lieu d'UN chemin walk-forward, C(N,k) combinaisons purgées de
# groupes-test -> une DISTRIBUTION d'IC OOS. Un edge fragile s'effondre sur la
# dispersion (p10 ≤ 0), là où un point unique peut flatter un régime.

def cpcv_paths(n_points, grid_idx, n_groups=10, k_test=2, purge=8,
               min_train=50, min_test=50, max_paths=45):
    """Chemins CPCV : génère (combo, train_mask, test_mask) pour chaque combinaison de
    k_test groupes-test parmi n_groups (groupes CONTIGUS en temps), avec PURGE+EMBARGO
    de `purge` (en unités de grid_idx, ex. barres) autour de chaque bloc test — aucun
    point de train à moins de `purge` d'un point de test. PUR (numpy seul, générateur
    déterministe). Borne perf VPS (2 cœurs) : au plus `max_paths` chemins (défaut 45
    = C(10,2)) ; au-delà, sous-échantillonnage RÉGULIER déterministe des combinaisons.
    Les chemins trop petits (train < min_train ou test < min_test) sont sautés."""
    import itertools
    n_points = int(n_points)
    grid_idx = np.asarray(grid_idx, dtype=float)
    if n_points < max(2, int(n_groups)) or len(grid_idx) != n_points:
        return
    bounds = np.linspace(0, n_points, n_groups + 1).astype(int)
    groups = [np.arange(bounds[i], bounds[i + 1]) for i in range(n_groups)]
    combos = list(itertools.combinations(range(n_groups), int(k_test)))
    if len(combos) > int(max_paths):                 # borne dure : budget CPU du timer
        keep = np.unique(np.linspace(0, len(combos) - 1, int(max_paths)).round().astype(int))
        combos = [combos[i] for i in keep]
    for combo in combos:
        blocs = [groups[g] for g in combo if len(groups[g])]
        if not blocs:
            continue
        test_idx = np.concatenate(blocs)
        test_mask = np.zeros(n_points, bool); test_mask[test_idx] = True
        # purge : retirer du train tout point dont l'étiquette chevauche un bloc test
        purge_mask = np.zeros(n_points, bool)
        for g in combo:
            if not len(groups[g]):
                continue
            lo = grid_idx[groups[g][0]] - purge
            hi = grid_idx[groups[g][-1]] + purge
            purge_mask |= (grid_idx >= lo) & (grid_idx <= hi)
        train_mask = ~purge_mask
        if train_mask.sum() >= min_train and test_mask.sum() >= min_test:
            yield combo, train_mask, test_mask


def cpcv_diagnostic(donnees=None, pas=24, horizon=8, warmup=80, agents=None,
                    n_groups=10, k_test=2, max_paths=45):
    """DISTRIBUTION d'IC OOS des agents PURS par CPCV multi-chemins, sur le MÊME panel
    profond multi-symboles que replay_annuel (§54 — pas seulement BTCUSDT). Pour chaque
    agent : mêmes combinaisons de groupes-test sur tous les symboles (groupes = tranches
    contiguës de la timeline de CHAQUE symbole), points de test POOLÉS trans-symboles
    par chemin, puis Rank IC par chemin -> p10 / médiane / fraction de chemins ≤ 0.
    NON-GATING (hygiène d'armement) : purement JOURNALISÉ dans le rapport de validation
    (brain_validation, champ "cpcv") — ne modifie AUCUNE décision de palier/promotion ;
    l'armer en porte serait un commit isolé. PUR si `donnees` injecté ; fail-open
    ({} sans données ou échantillon trop mince). Coût borné comme replay_annuel
    (~400 échantillons/symbole) + max_paths chemins (défaut 45 = C(10,2))."""
    import math
    if donnees is None:
        donnees = _panel_profond()
    if not donnees:
        return {}
    agents = agents or PURE_AGENTS
    par_agent = {}
    for nom, fn in agents.items():
        series = {}                                  # symbole -> (votes, fwd, grid)
        for s, c in donnees.items():
            # même auto-plafond que replay_annuel (~400 échantillons/symbole) : budget
            # du timer de validation (§54). Déterministe (fonction de len(c)).
            pas_eff = max(int(pas), (len(c) - warmup) // 400)
            votes, fwd, grid = [], [], []
            for t_ in range(warmup, len(c) - horizon, pas_eff):
                try:
                    v = float(fn(c[max(0, t_ - 200):t_ + 1]) or 0.0)
                    f = math.log(float(c[t_ + horizon][4]) / float(c[t_][4]))
                except Exception:
                    continue
                votes.append(v); fwd.append(f); grid.append(t_)
            if len(votes) >= n_groups * 2:           # ≥ 2 points/groupe en moyenne
                series[s] = (np.asarray(votes, float), np.asarray(fwd, float),
                             np.asarray(grid, float))
        if not series:
            continue
        # par chemin (= combinaison de groupes), pool des points de test de TOUS les
        # symboles — la clé combo aligne les chemins entre symboles.
        par_chemin = {}
        for s, (v, f, g) in series.items():
            for combo, _tr, te in cpcv_paths(len(v), g, n_groups, k_test,
                                             purge=horizon, min_train=1, min_test=5,
                                             max_paths=max_paths):
                par_chemin.setdefault(combo, []).append((v[te], f[te]))
        ics = []
        for combo in sorted(par_chemin):
            vv = np.concatenate([m[0] for m in par_chemin[combo]])
            ff = np.concatenate([m[1] for m in par_chemin[combo]])
            if len(vv) >= 10:
                ics.append(rank_ic(vv, ff))
        if len(ics) >= 5:                            # distribution trop mince -> muet
            a = np.asarray(ics, float)
            par_agent[nom] = {
                "n_chemins": int(len(a)),
                "ic_median": round(float(np.median(a)), 4),
                "ic_p10": round(float(np.percentile(a, 10)), 4),
                "ic_p90": round(float(np.percentile(a, 90)), 4),
                "frac_neg": round(float((a <= 0.0).mean()), 3),
                "n_points": int(sum(len(v) for v, _f, _g in series.values())),
                "n_symbols": int(len(series)),
            }
    if not par_agent:
        return {}
    return {"agents": par_agent, "n_groups": int(n_groups), "k_test": int(k_test),
            "max_paths": int(max_paths), "horizon": int(horizon), "non_gating": True}


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


# ---------- chemin 1bis : breadth TRANSVERSALE (multi-symboles) ----------
# Loi fondamentale de la gestion (Grinold-Kahn) : IR ≈ IC·√(breadth). Sur un seul
# symbole, n est plafonné par la longueur d'historique (~64). Évaluer un agent en COUPE
# TRANSVERSALE sur l'univers liquide multiplie le nombre de paris directionnels — MAIS le
# crypto est très corrélé (beta commun), donc empiler 20 symboles ne donne PAS 20× d'info
# indépendante. On corrige par un n EFFECTIF (variance inflation) : sans ça, on promouvrait
# un agent en LIVE sur un edge factice -> trade réel sur du vent. Depuis §40, ce chemin
# EST le ranking préféré du rapport de validation (brain_validation, repli mono-symbole) :
# c'est ce qui rend le palier LIVE atteignable SANS baisser aucun seuil — la porte d'edge
# (mandate/edge_ladder) et ses seuils DSR/n/OOS/live restent inchangés.

def average_cross_correlation(panel):
    """Corrélation transversale MOYENNE (hors-diagonale) des séries de rendements-
    stratégie {symbole: returns}. PUR. Mesure combien les paris bougent ENSEMBLE (beta
    commun) -> sert à dégonfler le n. Retourne ρ̄ ∈ [−1,1] (0.0 si < 2 séries valides)."""
    rows = [np.asarray(r, float) for r in panel.values() if r is not None and len(r) >= 2]
    if len(rows) < 2:
        return 0.0
    L = min(len(r) for r in rows)
    if L < 2:
        return 0.0
    M = np.vstack([r[-L:] for r in rows])           # N×L : fenêtre commune la plus récente
    sd = M.std(axis=1)
    if np.any(sd <= 1e-12):                          # série constante -> corr indéfinie
        M = M[sd > 1e-12]
        if M.shape[0] < 2:
            return 0.0
    C = np.corrcoef(M)
    N = C.shape[0]
    off = (C.sum() - np.trace(C)) / (N * (N - 1))
    return float(np.clip(off, -1.0, 1.0))


def effective_sample_size(n_nominal, n_symbols, rho_bar, periods=None):
    """Taille d'échantillon EFFECTIVE corrigée de la corrélation transversale (variance
    inflation). PUR. Empiler des symboles corrélés ne crée PAS d'observations indépendantes :
        n_eff_par_période = N / (1 + (N−1)·ρ̄)        (ρ̄ écrêté ∈ [0,1])
        n_eff             = périodes · n_eff_par_période
    ρ̄→0 (indépendants) -> n_eff ≈ n_nominal ; ρ̄→1 (un seul beta) -> n_eff ≈ périodes (= n
    d'un seul symbole) : AUCUNE inflation. Conservateur pour une PORTE de promotion : la
    corrélation négative n'est PAS créditée (écrêtée à 0)."""
    N = max(1, int(n_symbols))
    rho = max(0.0, min(1.0, float(rho_bar)))         # pas de crédit pour ρ̄ < 0
    eff_per_period = N / (1.0 + (N - 1) * rho)
    per = (float(n_nominal) / N if N else 0.0) if periods is None else float(periods)
    return float(max(1.0, per * eff_per_period))


def _strat_and_series(signal_fn, candles, horizon, warmup, step=None):
    """Rendements directionnels sign(vote)·fwd + (votes, fwd) d'un agent sur un symbole."""
    votes, fwd = replay(signal_fn, candles, horizon, warmup, step)
    v, f = np.asarray(votes, float), np.asarray(fwd, float)
    return (np.sign(v) * f).tolist(), votes, fwd


def rank_pure_agents_xs(candles_by_symbol, horizon=8, warmup=80):
    """Validation TRANSVERSALE (breadth) des agents PURS sur plusieurs symboles. Met en
    commun les paris directionnels et calcule DSR/PSR/IC sur un n EFFECTIF corrigé de la
    corrélation transversale (anti-inflation). Ranking préféré du rapport de validation
    (§40) — les seuils de la porte d'edge restent inchangés, seul le n devient honnête.
    Retourne {agents:[...trié par DSR...], deflation, horizon, n_symbols}."""
    syms = [s for s, c in candles_by_symbol.items() if c and len(c) > warmup + horizon]
    raw = {}
    for name, fn in PURE_AGENTS.items():
        all_v, all_f, panel, per_sym_ic = [], [], {}, []
        for s in syms:
            strat, votes, fwd = _strat_and_series(fn, candles_by_symbol[s], horizon, warmup)
            if len(strat) >= 2:
                panel[s] = strat
                all_v.extend(votes); all_f.extend(fwd)
                if len(votes) >= 5:
                    per_sym_ic.append(rank_ic(votes, fwd))
        m = evaluate(all_v, all_f)                   # n NOMINAL = toutes les paires (sym×période)
        rho = average_cross_correlation(panel)
        n_eff = effective_sample_size(m["n"], len(panel), rho)
        frac = float(np.mean([1.0 if x > 0 else 0.0 for x in per_sym_ic])) if per_sym_ic else 0.0
        raw[name] = {"m": m, "rho": rho, "n_eff": n_eff, "n_sym": len(panel), "bread_frac": frac}
    # déflation multiple-testing (sur les agents testés), n EFFECTIF pour PSR/DSR/IC-t
    sharpes = [d["m"]["_strat_sharpe_raw"] for d in raw.values() if d["m"]["n"] >= 5]
    var_sr = float(np.var(sharpes, ddof=1)) if len(sharpes) >= 2 else 0.0
    n_trials = max(2, len(sharpes))
    out = []
    for name, d in raw.items():
        m, rho, n_eff = d["m"], d["rho"], d["n_eff"]
        sr = m["_strat_sharpe_raw"]; sk = m.get("skew", 0.0); ku = m.get("kurt", 3.0)
        ne = int(round(n_eff))
        dsr = deflated_sharpe(sr, ne, sk, ku, n_trials, var_sr) if m["n"] >= 5 else 0.0
        rr = replication_ratio(ne, sr=abs(sr)) if ne > 2 else None
        row = {k: v for k, v in m.items() if not k.startswith("_")}
        row["agent"] = name
        row["n"] = ne                                # n EFFECTIF (ce que lirait une porte)
        row["n_nominal"] = int(m["n"])               # paires brutes (transparence)
        row["n_symbols"] = d["n_sym"]
        row["rho_bar"] = round(rho, 3)
        row["ic_t"] = round(ic_tstat(row.get("ic", 0.0), ne), 2)   # IC-t sur n EFFECTIF
        row["psr"] = round(psr(sr, ne, sk, ku), 4)
        row["dsr"] = round(dsr, 4)
        row["repl_ratio"] = round(rr, 3) if rr is not None else None
        row["oos_sharpe"] = round(sr * rr, 4) if rr is not None else None
        row["wfa_pass"] = bool(d["bread_frac"] >= 2.0 / 3.0)       # cohérence transversale
        row["wfa_frac"] = round(d["bread_frac"], 3)
        out.append(row)
    out.sort(key=lambda r: (r["dsr"], r.get("ic", 0)), reverse=True)
    return {"agents": out, "horizon": horizon, "n_symbols": len(syms),
            "deflation": {"n_trials": n_trials, "var_sharpe": round(var_sr, 6),
                          "sr0_max": round(expected_max_sharpe(n_trials, var_sr), 4)}}


def run_xs(symbols=None, timeframe="1h", limit=600, horizon=8, top_n=12, warmup=80):
    """Replay TRANSVERSAL des agents purs sur l'univers liquide + breadth. Best-effort
    (réseau). Retourne le ranking transversal ou {error}. Lecture seule, aucun ordre."""
    if symbols is None:
        try:
            import universe
            symbols = universe.symbols()
        except Exception:
            symbols = ["BTCUSDT"]
    candles_by_symbol = {}
    for s in list(symbols)[:top_n]:
        try:
            import market_sources as ms
            c = ms.candles(s, timeframe, limit)
            if c and len(c) > warmup + horizon:
                candles_by_symbol[s] = c
        except Exception:
            pass
    if len(candles_by_symbol) < 2:
        return {"error": f"univers insuffisant pour la coupe transversale ({len(candles_by_symbol)} symbole(s))"}
    return rank_pure_agents_xs(candles_by_symbol, horizon=horizon, warmup=warmup)


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


# ---------- chemin 3 : edge TEMPOREL (market-timing) des agents marché-large ----------
# Frontière identifiée en §39 (RESEARCH_NOTES) : la coupe transversale zéro-note PAR
# CONSTRUCTION les agents marché-large (macro, sentiment, flows... votent pareil sur
# tous les symboles). Leur edge éventuel est TEMPOREL : le vote moyen au cycle t
# prédit-il le rendement MOYEN du marché h cycles plus tard ? Mesure time-gated
# (l'échantillon s'accumule avec les semaines de votes journalisés), ADVISORY.

def _cycles_from_log(log, bucket_s=240):
    """PUR. Regroupe les entrées de brain_log par CYCLE de scan : les entrées dont le
    ts est à moins de bucket_s du début du groupe appartiennent au même cycle (le scan
    journalise tous les symboles en quelques secondes, cadence 5 min). Retourne les
    cycles ordonnés : [{"ts", "prices": {sym: prix}, "votes": {agent: [votes]},
    "consensus": [floats]}]."""
    entries = sorted((e for e in log or [] if e.get("price") and e.get("ts")),
                     key=lambda e: e["ts"])
    cycles, cur, debut = [], None, None
    for e in entries:
        if cur is None or e["ts"] - debut > bucket_s:
            cur = {"ts": e["ts"], "prices": {}, "votes": {}, "consensus": []}
            debut = e["ts"]
            cycles.append(cur)
        sym = e.get("symbol")
        if sym:
            try:
                cur["prices"][sym] = float(e["price"])
            except (TypeError, ValueError):
                pass
        for ag, v in (e.get("votes") or {}).items():
            try:
                cur["votes"].setdefault(ag, []).append(float(v))
            except (TypeError, ValueError):
                pass
        if e.get("consensus") is not None:
            try:
                cur["consensus"].append(float(e["consensus"]))
            except (TypeError, ValueError):
                pass
    return cycles


def evaluate_market_timing(log, bucket_s=240, horizon_cycles=12, min_symbols=1):
    """Évalue l'edge TEMPOREL de chaque agent (+ le consensus, pseudo-agent
    'consensus') : IC/t/hit/Sharpe/PSR entre le vote MOYEN marché-large au cycle t et
    le rendement MOYEN du marché au cycle t+h. Échantillonnage NON CHEVAUCHANT
    (pas = horizon) : pas d'inflation de n par des rendements qui se recouvrent.
    horizon_cycles=12 ≈ 1 h à cadence 5 min (cohérent avec HORIZON_S du cerveau).
    PUR. Best-effort (peu de cycles au début -> métriques neutres)."""
    cycles = _cycles_from_log(log, bucket_s)
    h = max(1, int(horizon_cycles))
    pairs, n_echantillons, i = {}, 0, 0
    while i + h < len(cycles):
        c0, c1 = cycles[i], cycles[i + h]
        commun = [s for s in c0["prices"] if s in c1["prices"] and c0["prices"][s] > 0]
        if len(commun) >= min_symbols:
            fwd = sum(c1["prices"][s] / c0["prices"][s] - 1.0 for s in commun) / len(commun)
            for ag, vs in c0["votes"].items():
                if vs:
                    pairs.setdefault(ag, []).append((sum(vs) / len(vs), fwd))
            if c0["consensus"]:
                pairs.setdefault("consensus", []).append(
                    (sum(c0["consensus"]) / len(c0["consensus"]), fwd))
            n_echantillons += 1
        i += h                                   # non chevauchant : échantillons purgés
    out = []
    for ag, pv in pairs.items():
        m = evaluate([x[0] for x in pv], [x[1] for x in pv])
        m = {k: v for k, v in m.items() if not k.startswith("_")}
        m["agent"] = ag
        out.append(m)
    out.sort(key=lambda d: (d.get("ic", 0)), reverse=True)
    return {"agents": out, "n_cycles": len(cycles),
            "n_echantillons": n_echantillons, "horizon_cycles": h}


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
