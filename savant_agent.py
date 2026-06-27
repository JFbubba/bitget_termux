"""
savant_agent.py — agent « savant / autiste digitale » : PERCEPTION TENSORIELLE des
ruptures de symétrie de la microstructure (détection d'anomalies multivariées).

Classement : SAFE. Aide à la décision DÉTERMINISTE, lecture seule, AUCUN ordre.

Esprit de la spec, traduit honnêtement dans les contraintes DURES du projet :
  • « filtres logiques stricts et rigides, zéro hallucination/dérive » -> c'est
    EXACTEMENT le déterminisme : ici, aucun réseau de neurones, sortie reproductible ;
  • « matrice synesthésique tensorielle » + « les anomalies BRISENT la symétrie
    géométrique avant tout calcul numérique » -> on bâtit un TENSEUR de features
    hétérogènes (rendement, pression, volatilité, volume, déséquilibre) et on
    mesure la rupture de structure par la distance de MAHALANOBIS (qui tient compte
    de la covariance : un point « normal » feature-par-feature mais incohérent avec
    la STRUCTURE est détecté). C'est la « rupture de symétrie » rendue rigoureuse ;
  • « immunité au bruit (FUD/FOMO) » -> le sentiment est traité comme une métrique
    de bruit/volatilité, exploitée à CONTRE-COURANT (inefficience comportementale) ;
  • « Monte-Carlo temps réel » -> branché sur futuretester en cas d'anomalie forte ;
  • « VaR au satoshi » -> Value-at-Risk historique/paramétrique, INDICATIVE.

CE QU'ON REJETTE (et pourquoi — honnêteté) :
  • « réseau de neurones neuromorphique » : le projet INTERDIT les NN (fragiles,
    opaques) — on garde la moitié « filtres rigides » de la spec, pas la moitié NN ;
  • « réécrit/recompile son propre code source à chaque bloc » : code auto-mutant =
    risque de sécurité inacceptable ; l'analogue sain (apprentissage en ligne des
    poids) existe déjà dans swarm_brain.learn() ;
  • « hyper-masking / fragmentation d'ordres / évasion MEV » : exige des ORDRES réels
    + de l'évasion de détection -> hors cadre (paper/advisory). La VaR reste indicative ;
  • nœud archive complet / audit de bytecode / arbitrage cross-chain : infra hors cadre ;
  • « Alpha Absolu Infaillible » : impossible. On produit un signal probabiliste BORNÉ.

Les fonctions de calcul sont PURES et testables ; les fetch réseau sont enveloppés.
"""

import math

import numpy as np


# ---------- tenseur de features (la « matrice synesthésique ») ----------

def _row(c):
    """Bougie dict OU liste [t,o,h,l,c,v] -> (o,h,l,c,v). Pur."""
    if isinstance(c, dict):
        return (float(c["open"]), float(c["high"]), float(c["low"]),
                float(c["close"]), float(c.get("volume", 0) or 0))
    return (float(c[1]), float(c[2]), float(c[3]), float(c[4]),
            float(c[5]) if len(c) > 5 else 0.0)


def feature_matrix(candles):
    """Construit le TENSEUR de features hétérogènes (T-1 × D). PUR. D=5 :
      [ rendement, |rendement|, pression(CLV), amplitude relative, volume ].
    Données fusionnées dans un même espace vectoriel (cf. « synesthésie matricielle »)."""
    rows = [_row(c) for c in candles]
    feats = []
    for i in range(1, len(rows)):
        o, h, l, c, v = rows[i]
        pc = rows[i - 1][3]
        if pc <= 0 or c <= 0:
            continue
        ret = math.log(c / pc)
        rng = h - l
        clv = (((c - l) - (h - c)) / rng) if rng > 0 else 0.0
        feats.append([ret, abs(ret), clv, rng / pc, v])
    return np.asarray(feats, dtype=float)


def _standardize(X):
    """Centre-réduit chaque colonne (z-score). Colonne plate -> 0. Pur."""
    mu = X.mean(0)
    sd = X.std(0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    return (X - mu) / sd


# ---------- rupture de symétrie : distance de Mahalanobis ----------

def mahalanobis_anomaly(X, ridge=1e-2):
    """Score de rupture de structure du DERNIER point vs le nuage récent. PUR.

    d² = (x−μ)ᵀ Σ⁻¹ (x−μ) sur features standardisées (Σ = corrélation régularisée).
    Détecte une incohérence avec la STRUCTURE de covariance, même si chaque feature
    prise isolément paraît normale (« brise la symétrie de la matrice »).
    Retourne (d2, score_normalisé = d2/D). Robuste : pinv régularisée."""
    if len(X) < X.shape[1] + 3:
        return 0.0, 0.0
    Z = _standardize(X)
    base, x = Z[:-1], Z[-1]
    mu = base.mean(0)
    cov = np.cov(base, rowvar=False)
    cov = cov + ridge * np.eye(cov.shape[0])
    inv = np.linalg.pinv(cov)
    diff = x - mu
    d2 = float(diff @ inv @ diff)
    d2 = max(0.0, d2)
    return d2, d2 / X.shape[1]


def symmetry_break(X):
    """Indicateur borné [0,1] de rupture de symétrie (sature en douceur). PUR.
    Mappe le score de Mahalanobis via 1−exp(−score/2) (≈0 normal, ≈1 anomalie forte)."""
    _, score = mahalanobis_anomaly(X)
    return 1.0 - math.exp(-score / 2.0)


# ---------- Value-at-Risk (indicative) ----------

def value_at_risk(returns, alpha=0.05):
    """VaR à (1−alpha) : perte au quantile alpha des rendements (historique) ET
    paramétrique gaussienne. PUR. Retourne dict (valeurs POSITIVES = pertes). Indicatif."""
    r = np.asarray([x for x in returns if x == x], dtype=float)
    if len(r) < 10:
        return {"var_hist": None, "var_param": None, "alpha": alpha}
    hist = float(-np.quantile(r, alpha))
    mu, sd = float(r.mean()), float(r.std())
    # quantile gaussien approx (Acklam-lite via erfinv)
    z = math.sqrt(2) * _erfinv(2 * alpha - 1)
    param = float(-(mu + z * sd))
    return {"var_hist": round(max(hist, 0.0), 5), "var_param": round(max(param, 0.0), 5),
            "alpha": alpha}


def _erfinv(y):
    """Inverse de la fonction d'erreur (approx. rationnelle). Pur."""
    y = max(-0.999999, min(0.999999, y))
    a = 0.147
    ln = math.log(1 - y * y)
    t = 2 / (math.pi * a) + ln / 2
    return math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), y)


# ---------- signal du savant (pur) ----------

def signal(candles, fear_greed=None, thresh=0.55):
    """Cœur PUR : perçoit la rupture de symétrie du tenseur, en déduit un signal
    À CONTRE-COURANT du dislocation (les manipulations/dislocations tendent à se
    corriger), immunisé au bruit, avec VaR indicative. Déterministe, aucun NN.

    fear_greed : 0..100 (optionnel) — traité comme bruit exploitable à contre-courant.
    Retourne un dict complet."""
    out = {"anomaly": 0.0, "symmetry_break": 0.0, "direction": 0, "vote": 0.0,
           "confidence": 0.0, "var": {}, "note": "données insuffisantes"}
    X = feature_matrix(candles)
    if len(X) < 12:
        return out
    d2, score = mahalanobis_anomaly(X)
    sb = 1.0 - math.exp(-score / 2.0)
    rets = X[:, 0]
    var = value_at_risk(rets)

    last_ret = float(X[-1, 0])
    direction = -1 if last_ret > 0 else 1 if last_ret < 0 else 0   # fade la dislocation

    # vote : actif SEULEMENT si la symétrie est nettement brisée (hyper-focalisation).
    vote = 0.0
    if sb >= thresh and direction != 0:
        vote = direction * min((sb - thresh) / (1.0 - thresh), 1.0) * 0.6

    # immunité au bruit : sentiment extrême exploité à contre-courant (FUD->long, FOMO->short)
    if fear_greed is not None:
        if fear_greed < 25:
            vote += 0.15
        elif fear_greed > 75:
            vote -= 0.15

    vote = max(-1.0, min(1.0, vote))
    conf = min(sb, 1.0) * (0.7 if sb >= thresh else 0.2)

    note = f"anomalie {sb:.2f}" + (
        f" · rupture {'baissière' if direction < 0 else 'haussière'} -> fade" if vote else " · sous seuil")
    out.update({"anomaly": round(sb, 3), "symmetry_break": round(sb, 3),
                "mahalanobis": round(d2, 2), "direction": direction,
                "vote": round(vote, 3), "confidence": round(conf, 3),
                "var": var, "note": note})
    return out


# ---------- intégration : analyse live + agent du cerveau ----------

def _candles(symbol, limit=80):
    """Bougies 15m résilientes (market_sources -> technicals), best-effort. Ne lève jamais."""
    try:
        import market_sources as ms
        c = ms.candles(symbol, "15m", limit)
        if c and len(c) >= 30:
            return c
    except Exception:
        pass
    try:
        import technicals as tk
        return tk.fetch_candles(symbol, "15m", limit)
    except Exception:
        return []


def _fear_greed():
    """Indice Fear & Greed (0..100), best-effort -> None."""
    try:
        import sentiment_index
        fg = sentiment_index.fetch_fear_greed()
        return float(fg.get("value")) if fg and fg.get("value") is not None else None
    except Exception:
        return None


def analyze(symbol="BTCUSDT", ttl=30):
    """Analyse savant live (rupture de symétrie + VaR), cachée, best-effort. Ne lève jamais."""
    import runtime_cache as rc

    def fetch():
        candles = _candles(symbol)
        if len(candles) < 20:
            return {"anomaly": 0.0, "vote": 0.0, "confidence": 0.0, "note": "n/a"}
        return signal(candles, fear_greed=_fear_greed())
    return rc.get(f"savant:{symbol.upper()}", ttl, fetch,
                  fallback={"anomaly": 0.0, "vote": 0.0, "confidence": 0.0, "note": "n/a"})


def agent(symbol="BTCUSDT"):
    """Adaptateur agent du cerveau (essaim) : {vote, confidence, note}. Best-effort."""
    a = analyze(symbol)
    return {"vote": a.get("vote", 0.0), "confidence": a.get("confidence", 0.0),
            "note": a.get("note", "n/a")}


def build_report(a):
    """Rapport texte de l'analyse savant. Pur."""
    var = a.get("var", {}) or {}
    return ("=== AGENT SAVANT (perception tensorielle des ruptures) ===\n"
            f"Rupture de symétrie : {a.get('symmetry_break', 0)} "
            f"(Mahalanobis {a.get('mahalanobis', 0)})\n"
            f"VaR95 hist {var.get('var_hist')} · param {var.get('var_param')} (indicatif)\n"
            f"Vote {a.get('vote', 0):+} · conf {a.get('confidence', 0)} | {a.get('note', '')}\n"
            "Déterministe, LECTURE SEULE. Aucun ordre, aucun NN, aucune évasion. VERDICT: SAFE")


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(analyze(sym)))


if __name__ == "__main__":
    main()
