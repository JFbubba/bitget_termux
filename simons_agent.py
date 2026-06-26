"""
simons_agent.py — agent « stratégie Simons » (Renaissance/Medallion) adapté crypto.

Classement : SAFE. Aide à la décision DÉTERMINISTE, lecture seule, AUCUN ordre,
AUCUN réseau de neurones. Apprentissage statistique CLASSIQUE uniquement (c'est
exactement ce qu'employait Renaissance : Baum — le « B » de Baum-Welch — y a
développé les HMM).

CE QU'ON TRANSPOSE (parties exploitables du document fourni) :
  • RÉGIMES CACHÉS — Modèle de Markov Caché gaussien (Baum-Welch/EM + Viterbi) sur
    les log-rendements : détecte des états latents (range calme / tendance /
    stress-haute-vol) sans les observer directement. C'est la PIÈCE MAÎTRESSE.
  • ARBITRAGE STATISTIQUE — retour à la moyenne (processus d'Ornstein-Uhlenbeck) :
    z-score de l'écart à l'équilibre + demi-vie ; win-rate ténu × loi des grands
    nombres (Medallion ≈ 50.75 %). Pour un actif unique, l'analogue market-neutral
    est la réversion de la DÉVIATION.
  • GATING PAR RÉGIME — on ne réverte qu'en régime calme ; en stress on se RETIRE
    (discipline « speedbump »/coupe de levier quand les corrélations se rompent).
  • KELLY FRACTIONNAIRE — fraction f = espérance/variance, plafonnée, PUREMENT
    INDICATIVE (jamais de dimensionnement d'ordre réel ici).
  • RANK IC (Spearman) — métrique d'évaluation hors-échantillon d'un signal.

CE QU'ON N'IMPLÉMENTE PAS (et pourquoi, honnêtement) :
  • Market-making Avellaneda-Stoikov optimisé par RL : exige des ORDRES réels + un
    réseau de neurones (PPO/DDQN) -> hors cadre (advisory/paper, pas de NN).
  • Levier 12,5–20× : contexte institutionnel de Medallion ; en crypto retail =
    risque de ruine. On expose Kelly à titre indicatif, sans appliquer de levier.
  • L'« Agent de Code » LLM qui écrit des indicateurs : déjà couvert, autrement,
    par strategy_lab (backtester autonome) sous garde anti-surapprentissage.

Les fonctions de calcul sont PURES et testables ; les fetch réseau sont enveloppés
(try/except) et ne lèvent jamais vers l'appelant.
"""

import math

import numpy as np


# ---------- helpers purs ----------

def log_returns(closes):
    """Log-rendements d'une série de clôtures. Pur."""
    p = [float(c) for c in closes if c and c > 0]
    return [math.log(p[i] / p[i - 1]) for i in range(1, len(p))]


# ---------- HMM gaussien (Baum-Welch + Viterbi) : régimes cachés ----------

def _gauss(x, mu, var):
    var = max(var, 1e-12)
    return np.exp(-0.5 * (x - mu) ** 2 / var) / math.sqrt(2 * math.pi * var)


def _emission(obs, mu, var):
    """Matrice d'émission B[t,k] = N(obs_t ; mu_k, var_k). Pur."""
    T, K = len(obs), len(mu)
    B = np.empty((T, K))
    for k in range(K):
        B[:, k] = _gauss(obs, mu[k], var[k])
    return np.clip(B, 1e-300, None)


def fit_hmm(obs, k=3, iters=40, tol=1e-4, var_floor=1e-6):
    """Ajuste un HMM gaussien à 1 dimension par Baum-Welch (forward-backward avec
    facteurs d'échelle, EM). Initialisation DÉTERMINISTE par quantiles -> résultat
    reproductible (aucun aléa). Retourne (pi, A, mu, var, loglik). Pur.

    obs : observations 1D (log-rendements standardisés de préférence)."""
    x = np.asarray(obs, dtype=float)
    T = len(x)
    if T < k * 4:
        # trop court : un seul régime dégénéré
        return (np.ones(1), np.ones((1, 1)), np.array([x.mean() if T else 0.0]),
                np.array([max(x.var(), var_floor) if T else 1.0]), 0.0)
    # init déterministe : moyennes aux quantiles, variance globale, transitions « collantes »
    qs = np.linspace(0.0, 1.0, k + 2)[1:-1]
    mu = np.quantile(x, qs).astype(float)
    var = np.full(k, max(x.var(), var_floor))
    A = np.full((k, k), 0.1 / (k - 1)) if k > 1 else np.ones((1, 1))
    np.fill_diagonal(A, 0.9)
    pi = np.full(k, 1.0 / k)
    prev_ll = -np.inf
    for _ in range(iters):
        B = _emission(x, mu, var)
        # ---- forward avec scaling ----
        alpha = np.zeros((T, k)); c = np.zeros(T)
        alpha[0] = pi * B[0]; c[0] = alpha[0].sum() or 1e-300; alpha[0] /= c[0]
        for t in range(1, T):
            alpha[t] = (alpha[t - 1] @ A) * B[t]
            c[t] = alpha[t].sum() or 1e-300
            alpha[t] /= c[t]
        # ---- backward avec scaling ----
        beta = np.zeros((T, k)); beta[-1] = 1.0
        for t in range(T - 2, -1, -1):
            beta[t] = (A @ (B[t + 1] * beta[t + 1])) / c[t + 1]
        # ---- gamma / xi ----
        gamma = alpha * beta
        gamma /= np.clip(gamma.sum(1, keepdims=True), 1e-300, None)
        xi_sum = np.zeros((k, k))
        for t in range(T - 1):
            denom = (alpha[t][:, None] * A * (B[t + 1] * beta[t + 1])[None, :])
            s = denom.sum() or 1e-300
            xi_sum += denom / s
        # ---- M-step ----
        pi = gamma[0] + 1e-12; pi /= pi.sum()
        A = xi_sum + 1e-12; A /= A.sum(1, keepdims=True)
        gk = np.clip(gamma.sum(0), 1e-300, None)
        mu = (gamma * x[:, None]).sum(0) / gk
        var = (gamma * (x[:, None] - mu[None, :]) ** 2).sum(0) / gk
        var = np.clip(var, var_floor, None)
        ll = float(np.log(c).sum())
        if abs(ll - prev_ll) < tol:
            break
        prev_ll = ll
    return pi, A, mu, var, prev_ll


def viterbi(obs, pi, A, mu, var):
    """Chemin d'états le plus probable (MAP) en log-espace. Pur."""
    x = np.asarray(obs, dtype=float)
    T, k = len(x), len(pi)
    if k == 1:
        return np.zeros(T, dtype=int)
    logB = np.log(_emission(x, mu, var))
    logA = np.log(np.clip(A, 1e-300, None))
    delta = np.log(np.clip(pi, 1e-300, None)) + logB[0]
    psi = np.zeros((T, k), dtype=int)
    for t in range(1, T):
        m = delta[:, None] + logA
        psi[t] = m.argmax(0)
        delta = m.max(0) + logB[t]
    path = np.zeros(T, dtype=int)
    path[-1] = int(delta.argmax())
    for t in range(T - 2, -1, -1):
        path[t] = psi[t + 1, path[t + 1]]
    return path


def label_regime(state, mu, var, vol_ratio=1.0):
    """Étiquette DÉTERMINISTE du régime courant. PUR.
      • STRESS (retrait) = volatilité récente nettement élevée vs sa norme
        (vol_ratio > 1.8) — robuste, façon « speedbump sur ROC > seuil σ » du doc ;
      • sinon la MOYENNE de l'état caché (HMM) donne la direction : tendance si
        |mu| > 0.15 (en espace standardisé = 0.15σ de dérive/barre), sinon range
        (calme, favorable au retour à la moyenne).
    Le HMM porte la lecture DIRECTIONNELLE ; le gating de stress est découplé et
    robuste (ne dépend pas du ratio fragile des variances d'états)."""
    if vol_ratio > 1.8:
        return "stress"
    K = len(mu)
    if K == 1:
        return "range"
    m = mu[state]
    if m > 0.15:
        return "trend_up"
    if m < -0.15:
        return "trend_down"
    return "range"


# ---------- arbitrage statistique : réversion (Ornstein-Uhlenbeck) ----------

def zscore(closes, lookback=30):
    """z-score de l'écart du dernier prix à sa moyenne mobile (déviation OU). Pur."""
    p = [float(c) for c in closes if c and c > 0]
    if len(p) < lookback + 1:
        return 0.0
    window = np.asarray(p[-lookback:])
    sd = window.std()
    if sd <= 0:
        return 0.0
    return float((p[-1] - window.mean()) / sd)


def half_life(closes, lookback=60):
    """Demi-vie de retour à la moyenne via AR(1) sur la déviation. Pur (None si non
    réversif). hl = -ln2 / ln(1+b) avec Δy_t = a + b·y_{t-1}, b∈(-1,0)."""
    p = [float(c) for c in closes if c and c > 0]
    if len(p) < lookback + 2:
        return None
    y = np.asarray(p[-lookback:])
    dev = y - y.mean()
    y_lag = dev[:-1]
    dy = np.diff(dev)
    denom = float((y_lag ** 2).sum())
    if denom <= 0:
        return None
    b = float((y_lag * dy).sum() / denom)
    if b >= 0 or b <= -1:
        return None
    return -math.log(2) / math.log(1 + b)


def kelly_fraction(edge, variance, cap=0.25, fraction=0.5):
    """Fraction de Kelly (indicative) f = espérance/variance, demi-Kelly, plafonnée
    dans [-cap, cap]. PUR. NE dimensionne aucun ordre réel."""
    if variance is None or variance <= 0:
        return 0.0
    f = (edge / variance) * fraction
    return float(max(-cap, min(cap, f)))


# ---------- signal Simons (pur) : HMM + réversion + gating ----------

def signal(closes, k=3, lookback=30):
    """Cœur PUR de l'agent Simons. Combine :
      1) régime caché (HMM/Viterbi) sur log-rendements standardisés ;
      2) z-score de réversion (OU) + demi-vie ;
      3) gating : réversion en régime CALME, retrait en STRESS, biais réduit en
         tendance ; Kelly fractionnaire indicatif.
    Retourne un dict complet. Aucun réseau, aucun ordre."""
    p = [float(c) for c in closes if c and c > 0]
    rets = log_returns(p)
    out = {"regime": "n/a", "state": None, "n_states": k, "zscore": 0.0,
           "half_life": None, "vote": 0.0, "confidence": 0.0, "kelly": 0.0,
           "note": "données insuffisantes"}
    if len(rets) < max(k * 4, lookback):
        return out
    r = np.asarray(rets)
    sd = r.std() or 1.0
    z_obs = (r - r.mean()) / sd                      # standardisation (stabilité num.)
    pi, A, mu, var, _ = fit_hmm(z_obs, k=k)
    path = viterbi(z_obs, pi, A, mu, var)
    state = int(path[-1])
    # gating de stress robuste : vol récente vs vol de fond (vol-of-vol)
    base = r[-min(len(r), 80):]
    recent_w = r[-10:]
    vol_ratio = (recent_w.std() / base.std()) if base.std() > 0 else 1.0
    regime = label_regime(state, mu, var, vol_ratio)

    z = zscore(p, lookback)
    hl = half_life(p)
    recent = r[-lookback:]
    rec_var = float(recent.var()) or 1e-9

    if regime == "range":
        vote = -math.tanh(z * 0.8)                   # achète la faiblesse, vend la force
        conf = min(abs(z) / 2.0, 1.0) * 0.85
    elif regime == "stress":
        vote = 0.0                                    # retrait : on ne fournit pas d'edge
        conf = 0.1
    elif regime == "trend_up":
        vote = _bounded(0.3 - 0.2 * math.tanh(z))     # suit la tendance, réversion atténuée
        conf = 0.45
    else:  # trend_down
        vote = _bounded(-0.3 - 0.2 * math.tanh(z))
        conf = 0.45

    # Kelly indicatif : edge ≈ réversion attendue (−z·σ), variance = var récente
    edge = -z * sd if regime == "range" else vote * sd
    kelly = kelly_fraction(edge, rec_var * 1e4)       # variance remise à l'échelle prix

    note = f"régime {regime} · z {z:+.2f}" + (f" · demi-vie {hl:.0f}b" if hl else "")
    out.update({"regime": regime, "state": state, "n_states": int(len(mu)),
                "zscore": round(z, 3), "half_life": round(hl, 1) if hl else None,
                "vol_ratio": round(float(vol_ratio), 3),
                "vote": round(_bounded(vote), 3), "confidence": round(conf, 3),
                "kelly": round(kelly, 3), "note": note,
                "state_means": [round(float(m), 3) for m in mu],
                "state_vars": [round(float(v), 4) for v in var]})
    return out


def _bounded(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


# ---------- évaluation : Rank IC (Spearman) ----------

def _rankdata(a):
    """Rangs (moyenne des ex-aequo) — pur, sans scipy."""
    a = np.asarray(a, dtype=float)
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(len(a), dtype=float)
    # moyenne des rangs pour les ex-aequo
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    csum = np.cumsum(counts)
    starts = csum - counts
    avg = (starts + csum - 1) / 2.0
    return avg[inv]


def rank_ic(predictions, forward_returns):
    """Coefficient d'Information de Rang (Spearman) : corrélation monotone entre
    les rangs des prédictions et ceux des rendements futurs. PUR. ∈ [−1, 1].
    Mesure la valeur prédictive hors-échantillon d'un signal (cf. document)."""
    a, b = np.asarray(predictions, float), np.asarray(forward_returns, float)
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    ra, rb = _rankdata(a[:n]), _rankdata(b[:n])
    ra -= ra.mean(); rb -= rb.mean()
    denom = math.sqrt(float((ra ** 2).sum()) * float((rb ** 2).sum()))
    if denom <= 0:
        return 0.0
    return float((ra * rb).sum() / denom)


# ---------- intégration : agent du cerveau + analyse live ----------

def _closes(symbol, limit=160):
    """Clôtures 15m résilientes (market_sources -> technicals), best-effort. Ne lève jamais."""
    try:
        import market_sources as ms
        c = ms.closes(symbol, limit)
        if c and len(c) >= 60:
            return c
    except Exception:
        pass
    try:
        import technicals as tk
        return [float(x["close"]) for x in tk.fetch_candles(symbol, "15m", limit)]
    except Exception:
        return []


def analyze(symbol="BTCUSDT", ttl=45):
    """Analyse Simons live (HMM + réversion), cachée, best-effort. Ne lève jamais."""
    import runtime_cache as rc

    def fetch():
        closes = _closes(symbol)
        if len(closes) < 60:
            return {"regime": "n/a", "vote": 0.0, "confidence": 0.0,
                    "note": "données insuffisantes"}
        return signal(closes)
    return rc.get(f"simons:{symbol.upper()}", ttl, fetch,
                  fallback={"regime": "n/a", "vote": 0.0, "confidence": 0.0})


def agent(symbol="BTCUSDT"):
    """Adaptateur agent du cerveau (essaim) : {vote, confidence, note}. Best-effort."""
    a = analyze(symbol)
    return {"vote": a.get("vote", 0.0), "confidence": a.get("confidence", 0.0),
            "note": a.get("note", "n/a")}


def build_report(a):
    """Rapport texte de l'analyse Simons. Pur."""
    return ("=== AGENT SIMONS (Medallion adapté crypto) ===\n"
            f"Régime caché (HMM) : {a.get('regime', 'n/a')}  | état {a.get('state')}\n"
            f"Réversion : z {a.get('zscore', 0):+} · demi-vie {a.get('half_life')}\n"
            f"Vote {a.get('vote', 0):+} · conf {a.get('confidence', 0)} · "
            f"Kelly indicatif {a.get('kelly', 0)}\n"
            "Aide à la décision DÉTERMINISTE, LECTURE SEULE. Aucun ordre, aucun "
            "levier appliqué, aucun NN. VERDICT: SAFE")


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(analyze(sym)))


if __name__ == "__main__":
    main()
