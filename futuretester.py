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
