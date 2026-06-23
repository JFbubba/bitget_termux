"""
futuretester.py — « futurtester » : simulateur d'ISSUES FUTURES (l'inverse du backtest).

Classement : SAFE (Monte Carlo pur, aucune I/O, aucun ordre).

⚠️ HONNÊTETÉ : ce n'est PAS un prédicteur. C'est un générateur de **plages d'issues
CONDITIONNELLES** — « SI ces hypothèses tiennent, voilà l'éventail des résultats et
leurs probabilités ». Garbage-in/garbage-out : la qualité = celle des hypothèses.
On expose toujours la fourchette (P5..P95) et les hypothèses, jamais un point.

Axes couverts :
  • project_forecast  — plages impliquées par des prévisions institutionnelles (bas/base/haut) ;
  • SCENARIOS/run_scenario — futurs typés (dont convergence IA+blockchain↔TradFi) ;
  • macro_markov_path — évolution macro mondiale (chaîne de Markov de régimes) ;
  • actor_evolution   — évolution des parts d'acteurs (dynamique du réplicateur) ;
  • adoption_logistic — courbe d'adoption techno en S (IA/blockchain dans la finance) ;
  • simulate_terminal — moteur GBM + sauts (Merton) ; fan_stats — stats d'éventail.
"""

import math

import numpy as np


# ---------- moteur Monte Carlo ----------

def simulate_terminal(S0, mu, sigma, T, n=20000, jump_prob=0.0, jump_mu=0.0,
                      jump_sigma=0.0, seed=0):
    """Prix terminaux S_T : GBM + sauts lognormaux (Merton). mu/sigma ANNUALISÉS,
    T en années. jump_prob = intensité Poisson/an. Retourne array(n). Pur."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    drift = (mu - 0.5 * sigma ** 2) * T + sigma * math.sqrt(T) * z
    if jump_prob > 0:
        nj = rng.poisson(jump_prob * T, n)
        drift = drift + rng.normal(nj * jump_mu, jump_sigma * np.sqrt(nj))
    return S0 * np.exp(drift)


def fan_stats(terminals, S0):
    """Statistiques d'éventail (fan chart) d'une distribution d'issues. Pur."""
    t = np.asarray(terminals, dtype=float)
    p5, p25, p50, p75, p95 = np.percentile(t, [5, 25, 50, 75, 95])
    return {
        "S0": round(float(S0), 4),
        "p5": round(float(p5), 4), "p25": round(float(p25), 4),
        "p50": round(float(p50), 4), "p75": round(float(p75), 4),
        "p95": round(float(p95), 4),
        "prob_up": round(float((t > S0).mean()), 4),
        "median_return_pct": round(float((p50 / S0 - 1) * 100), 2),
        "p5_return_pct": round(float((p5 / S0 - 1) * 100), 2),
        "p95_return_pct": round(float((p95 / S0 - 1) * 100), 2),
    }


# ---------- prévisions institutionnelles -> plages ----------

def drift_from_forecasts(S0, low, base, high, T):
    """Drifts annualisés implicites de cibles de prix à horizon T : mu=ln(cible/S0)/T."""
    f = lambda target: math.log(target / S0) / T
    return f(low), f(base), f(high)


def project_forecast(S0, low, base, high, T, sigma=0.6, n=20000, seed=0):
    """Simule la PLAGE d'issues impliquée par des cibles institutionnelles
    (bas/base/haut) à horizon T, avec incertitude de volatilité. Pur.

    Le drift est tiré en triangulaire(bas, base, haut) ; la vol ajoute la dispersion."""
    ml, mb, mh = drift_from_forecasts(S0, low, base, high, T)
    rng = np.random.default_rng(seed)
    mus = rng.triangular(ml, mb, mh, n)
    z = rng.standard_normal(n)
    term = S0 * np.exp((mus - 0.5 * sigma ** 2) * T + sigma * math.sqrt(T) * z)
    st = fan_stats(term, S0)
    st["drift_range"] = (round(ml, 3), round(mb, 3), round(mh, 3))
    return st


# ---------- adoption technologique (S-curve) ----------

def adoption_logistic(t, ceiling=1.0, midpoint=5.0, steepness=1.0):
    """Adoption en S (logistique) — ex. IA/blockchain dans la finance. t en années. Pur."""
    return ceiling / (1.0 + math.exp(-steepness * (t - midpoint)))


# ---------- macro mondiale (chaîne de Markov de régimes) ----------

REGIMES = {
    "expansion": (0.15, 0.45),
    "slowdown": (0.03, 0.55),
    "recession": (-0.25, 0.85),
    "recovery": (0.12, 0.60),
}
# matrice de transition par défaut (lignes = état courant), ordre = liste REGIME_NAMES
REGIME_NAMES = ["expansion", "slowdown", "recession", "recovery"]
DEFAULT_P = [
    [0.85, 0.12, 0.02, 0.01],
    [0.20, 0.60, 0.18, 0.02],
    [0.02, 0.10, 0.70, 0.18],
    [0.30, 0.10, 0.05, 0.55],
]


def macro_markov_path(P, n_steps, start=0, names=None, seed=0):
    """Trajectoire de régime macro (chaîne de Markov). P = matrice de transition. Pur."""
    names = names or REGIME_NAMES
    rng = np.random.default_rng(seed)
    s = start
    path = [s]
    P = np.asarray(P, dtype=float)
    for _ in range(n_steps - 1):
        s = int(rng.choice(len(names), p=P[s]))
        path.append(s)
    return [names[i] for i in path]


# ---------- évolution des acteurs (dynamique du réplicateur) ----------

def replicator_step(shares, fitness):
    """Un pas de dynamique du réplicateur : les parts croissent avec la fitness
    relative (incumbents vs challengers vs nouveaux entrants). Somme = 1. Pur."""
    sh = np.asarray(shares, dtype=float)
    fit = np.asarray(fitness, dtype=float)
    avg = float(np.sum(sh * fit))
    new = sh * fit / (avg if avg != 0 else 1.0)
    s = new.sum()
    return (new / s) if s > 0 else sh


def actor_evolution(shares0, fitness, steps):
    """Projette l'évolution des parts d'acteurs sur `steps` périodes. Retourne
    trajectoire array(steps+1, k). HYPOTHÈSE : la détection des VRAIS futurs acteurs
    exige des données externes ; ici on projette des candidats fournis. Pur."""
    sh = np.asarray(shares0, dtype=float)
    sh = sh / sh.sum() if sh.sum() > 0 else sh
    traj = [sh.copy()]
    for _ in range(steps):
        sh = replicator_step(sh, fitness)
        traj.append(sh.copy())
    return np.array(traj)


# ---------- scénarios typés ----------

SCENARIOS = {
    "base": dict(mu=0.10, sigma=0.60, jump_prob=0.2, jump_mu=-0.05, jump_sigma=0.15,
                 note="poursuite tendancielle, volatilité crypto élevée"),
    "convergence_bull": dict(mu=0.45, sigma=0.55, jump_prob=0.15, jump_mu=0.0, jump_sigma=0.12,
                             note="IA+blockchain intégrées à la TradFi (adoption haute), afflux institutionnel"),
    "reg_bear": dict(mu=-0.25, sigma=0.70, jump_prob=0.35, jump_mu=-0.12, jump_sigma=0.20,
                     note="durcissement réglementaire, défiance, sorties de capitaux"),
    "stagnation": dict(mu=0.0, sigma=0.40, jump_prob=0.10, jump_mu=-0.03, jump_sigma=0.10,
                       note="range prolongé, adoption lente, liquidité atone"),
    "tail_crisis": dict(mu=-0.50, sigma=1.00, jump_prob=0.60, jump_mu=-0.25, jump_sigma=0.30,
                        note="choc systémique : deleveraging, contagion, ruée vers la liquidité"),
}


def run_scenario(name, S0, T=1.0, n=20000, seed=0):
    """Lance un scénario typé -> stats d'éventail + hypothèses explicites. Pur."""
    p = SCENARIOS[name]
    term = simulate_terminal(S0, p["mu"], p["sigma"], T, n,
                             p["jump_prob"], p["jump_mu"], p["jump_sigma"], seed)
    st = fan_stats(term, S0)
    st["scenario"] = name
    st["assumptions"] = {k: p[k] for k in ("mu", "sigma", "jump_prob")}
    st["note"] = p["note"]
    return st


def run_all(S0, T=1.0, n=20000, seed=0):
    """Tous les scénarios -> tableau d'issues (pour stress-tester une décision). Pur."""
    return {name: run_scenario(name, S0, T, n, seed) for name in SCENARIOS}


# ---------- calibration depuis l'historique (étape 4 : σ/sauts par actif) ----------

def calibrate(closes, periods_per_year=365.0, jump_k=3.5):
    """Calibre σ diffusive ANNUALISÉE + paramètres de sauts (Merton) depuis un
    historique de clôtures. PUR. Méthode du seuil robuste (MAD) :
      • un rendement au-delà de jump_k·σ_robuste est classé « saut » (Merton) ;
      • le reste donne la volatilité diffusive ; les sauts donnent prob/μ/σ.
    Retourne {sigma, jump_prob, jump_mu, jump_sigma, mu_hist, n}. Crypto = 365 j/an.

    ⚠️ `mu_hist` (drift historique annualisé) est FOURNI mais NON recommandé comme
    prévision (le passé n'est pas le futur) : par défaut on simule à drift nul."""
    pts = [float(c) for c in closes if c and c > 0]
    if len(pts) < 5:
        return {"sigma": 0.0, "jump_prob": 0.0, "jump_mu": 0.0, "jump_sigma": 0.0,
                "mu_hist": 0.0, "n": len(pts)}
    rets = [math.log(pts[i] / pts[i - 1]) for i in range(1, len(pts))]
    arr = np.asarray(rets, dtype=float)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    robust_sigma = 1.4826 * mad if mad > 0 else float(np.std(arr))
    if robust_sigma <= 0:
        robust_sigma = 1e-9
    thr = jump_k * robust_sigma
    is_jump = np.abs(arr - med) > thr
    diff = arr[~is_jump]
    jumps = arr[is_jump]
    sqp = math.sqrt(periods_per_year)
    sigma = float(np.std(diff)) * sqp if diff.size >= 2 else float(np.std(arr)) * sqp
    jprob = float(jumps.size) / arr.size * periods_per_year
    jmu = float(np.mean(jumps)) if jumps.size >= 1 else 0.0
    jsig = float(np.std(jumps)) if jumps.size >= 2 else float(thr)
    mu_hist = float(np.mean(arr)) * periods_per_year
    return {"sigma": round(sigma, 4), "jump_prob": round(jprob, 3),
            "jump_mu": round(jmu, 4), "jump_sigma": round(jsig, 4),
            "mu_hist": round(mu_hist, 4), "n": int(arr.size)}


def _daily_closes(symbol, limit=200):
    """Clôtures journalières résilientes (cachées), best-effort. Ne lève jamais."""
    import runtime_cache as rc

    def fetch():
        try:
            import market_sources as ms
            cs = ms.candles(symbol, "1d", limit)
            cl = [row[4] for row in cs if len(row) >= 5]
            if len(cl) >= 30:
                return cl
        except Exception:
            pass
        try:
            import technicals as tk
            return [float(c["close"]) for c in tk.fetch_candles(symbol, "1d", limit)]
        except Exception:
            return []
    return rc.get(f"future_daily:{symbol.upper()}", 3600, fetch, fallback=[])


def from_market(symbol="BTCUSDT", T=1.0, n=20000, seed=0, mu=0.0):
    """Projection d'éventail à partir des ENTRÉES RÉELLES de l'actif (étape 1) :
    σ et sauts calibrés sur l'historique journalier, drift `mu` par défaut NUL
    (baseline honnête « sans edge »). Best-effort : renvoie {} si pas de données."""
    closes = _daily_closes(symbol)
    if len(closes) < 30:
        return {}
    cal = calibrate(closes)
    S0 = closes[-1]
    term = simulate_terminal(S0, mu, cal["sigma"], T, n,
                             cal["jump_prob"], cal["jump_mu"], cal["jump_sigma"], seed)
    st = fan_stats(term, S0)
    st["symbol"] = symbol.upper()
    st["calibration"] = cal
    st["mu_used"] = mu
    st["note"] = "σ/sauts calibrés sur l'historique ; drift imposé (def. 0 = sans edge)"
    return st


# ---------- couplage au CERVEAU (étape 2 : stress-test du biais) ----------

def stress_assessment(bias, conviction, scenarios):
    """Confronte le BIAIS du cerveau aux scénarios futurs. PUR.

    `bias` ∈ {LONG, SHORT, NEUTRE}. Pour un biais LONG, le RISQUE est la queue
    BASSE (P5) des scénarios adverses ; pour SHORT, la queue HAUTE (P95). On
    expose la pire issue plausible et un drapeau si la conviction est forte alors
    que la queue adverse est sévère. Retourne {worst_scenario, worst_tail_pct, flag, lines}."""
    b = str(bias).upper()
    adverse_key = "p5_return_pct" if b == "LONG" else "p95_return_pct" if b == "SHORT" else None
    lines = []
    worst_scn, worst_tail = None, None
    for name, s in scenarios.items():
        p5 = s.get("p5_return_pct"); p95 = s.get("p95_return_pct")
        lines.append({"scenario": name, "p5_pct": p5, "median_pct": s.get("median_return_pct"),
                      "p95_pct": p95, "prob_up": s.get("prob_up")})
        if adverse_key is None:
            continue
        tail = s.get(adverse_key)
        if tail is None:
            continue
        if worst_tail is None or (b == "LONG" and tail < worst_tail) or (b == "SHORT" and tail > worst_tail):
            worst_tail, worst_scn = tail, name
    flag = False
    severe = (worst_tail is not None) and (
        (b == "LONG" and worst_tail < -30.0) or (b == "SHORT" and worst_tail > 30.0))
    if severe and float(conviction or 0) >= 0.4:
        flag = True
    return {"bias": b, "conviction": round(float(conviction or 0), 3),
            "worst_scenario": worst_scn, "worst_tail_pct": worst_tail,
            "high_conviction_vs_severe_tail": flag, "scenarios": lines}


def stress_brain(symbol="BTCUSDT", T=1.0, n=20000, seed=0):
    """Lit le biais du cerveau (peek) et le stress-teste contre tous les scénarios
    (S0 = prix réel). Best-effort. Réponse à « si je suis LONG, quel P5 en crise ? »."""
    bias, conviction, S0 = "NEUTRE", 0.0, 100.0
    try:
        import swarm_brain
        r = swarm_brain.peek(symbol)
        bias = r.get("bias", "NEUTRE")
        conviction = r.get("adjusted_conviction", r.get("conviction", 0.0))
    except Exception:
        pass
    closes = _daily_closes(symbol)
    if closes:
        S0 = closes[-1]
    scen = run_all(S0, T, n, seed)
    out = stress_assessment(bias, conviction, scen)
    out["symbol"] = symbol.upper()
    out["S0"] = round(float(S0), 4)
    return out


# ---------- couplage MACRO (étape 1 : macro pilotée par les données) ----------

def macro_outlook(n_steps=12, seed=0):
    """Trajectoire macro projetée DEPUIS le régime courant détecté (Sentinel),
    et non un point de départ arbitraire. Best-effort. Réponse à « entrées réelles »."""
    start, regime, conf = 0, "n/a", 0.0
    try:
        import macro_sentinel as msx
        nc = msx.nowcast()
        regime = nc.get("regime", "n/a")
        conf = nc.get("confidence", 0.0)
        start = msx.regime_index(regime)
    except Exception:
        pass
    path = macro_markov_path(DEFAULT_P, n_steps, start=start, seed=seed)
    # part de temps passé dans chaque régime sur la trajectoire
    dist = {r: round(path.count(r) / len(path), 3) for r in REGIME_NAMES}
    return {"current_regime": regime, "confidence": conf, "path": path,
            "time_in_regime": dist}


def main():
    import json
    import sys
    S0 = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
    T = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    out = {"S0": S0, "horizon_ans": T,
           "AVERTISSEMENT": "Plages CONDITIONNELLES, pas une prédiction (GIGO).",
           "scenarios": {n: {k: s[k] for k in ("p5_return_pct", "median_return_pct",
                                               "p95_return_pct", "prob_up", "note")}
                         for n, s in run_all(S0, T).items()}}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
