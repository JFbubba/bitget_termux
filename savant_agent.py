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


def corwin_schultz(h1, l1, h2, l2):
    """Estimateur de SPREAD bid-ask de Corwin-Schultz (2012) sur 2 barres haut/bas.
    PUR. Proxy de liquidité calculable en OHLCV pur : le spread s'élargit quand la
    liquidité se retire — confirmation de dislocation pour un trader. 0 si dégénéré."""
    try:
        if min(h1, l1, h2, l2) <= 0 or h1 < l1 or h2 < l2:
            return 0.0
        beta = math.log(h1 / l1) ** 2 + math.log(h2 / l2) ** 2
        gamma = math.log(max(h1, h2) / min(l1, l2)) ** 2
        k = 3.0 - 2.0 * math.sqrt(2.0)
        alpha = (math.sqrt(2.0 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
        s = 2.0 * (math.exp(alpha) - 1.0) / (1.0 + math.exp(alpha))
        return max(0.0, s)
    except (ValueError, ZeroDivisionError):
        return 0.0


def feature_matrix(candles, enrichi=False):
    """Construit le TENSEUR de features hétérogènes (T-1 × D). PUR. D=5 par défaut :
      [ rendement, |rendement|, pression(CLV), amplitude relative, volume ].
    `enrichi=True` ajoute 2 proxies de liquidité OHLCV (audit 03/07) : spread de
    Corwin-Schultz (2012) et illiquidité d'Amihud (2002, log-échelle), avec volume
    en LOG. MESURE HONNÊTE : l'enrichissement a été testé dans le chemin du VOTE et
    l'a DÉGRADÉ (IC replay poolé +0.09 -> −0.02 en D7 : les dimensions de liquidité
    diluent la détection Mahalanobis) — il reste disponible pour l'observabilité,
    PAS pour le vote."""
    rows = [_row(c) for c in candles]
    feats = []
    for i in range(1, len(rows)):
        o, h, l, c, v = rows[i]
        po, ph, pl, pc, pv = rows[i - 1]
        if pc <= 0 or c <= 0:
            continue
        ret = math.log(c / pc)
        rng = h - l
        clv = (((c - l) - (h - c)) / rng) if rng > 0 else 0.0
        base = [ret, abs(ret), clv, rng / pc, v]
        if enrichi:
            cs = corwin_schultz(ph, pl, h, l)
            dollar_vol = c * v
            amihud = math.log1p(abs(ret) / dollar_vol * 1e9) if dollar_vol > 0 else 0.0
            base = [ret, abs(ret), clv, rng / pc, math.log1p(max(v, 0.0)), cs, amihud]
        feats.append(base)
    return np.asarray(feats, dtype=float)


def _standardize(X):
    """Centre-réduit chaque colonne (z-score). Colonne plate -> 0. Pur."""
    mu = X.mean(0)
    sd = X.std(0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    return (X - mu) / sd


def _standardize_robuste(X):
    """Centre-réduit par MÉDIANE/MAD (×1.4826). PUR. Esprit Mahalanobis++
    (arXiv:2505.18032) : avec moyenne/écart-type, les anomalies CONTAMINENT leur
    propre baseline (la dislocation gonfle σ et se banalise) ; médiane/MAD sont
    insensibles aux queues — la baseline reste « le normal »."""
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0) * 1.4826
    mad = np.where(mad > 1e-12, mad, 1.0)
    return (X - med) / mad


def turbulence_series(X, ridge=1e-2):
    """d² de Mahalanobis de CHAQUE point vs le nuage (μ, Σ robustes globaux). PUR.
    C'est l'indice de TURBULENCE de Kritzman-Li (2010) appliqué au tenseur."""
    Z = _standardize_robuste(np.asarray(X, dtype=float))
    mu = Z.mean(0)
    cov = np.cov(Z, rowvar=False) + ridge * np.eye(Z.shape[1])
    inv = np.linalg.pinv(cov)
    D = Z - mu
    return np.einsum("ij,jk,ik->i", D, inv, D)


def turbulence_percentile(X, min_n=20):
    """(d² du dernier point, son PERCENTILE dans sa propre histoire). PUR. Le seuil
    devient ADAPTATIF : « turbulent » = rare PAR RAPPORT À CE MARCHÉ-CI, pas un
    seuil absolu arbitraire (pratique standard de l'indice de turbulence)."""
    X = np.asarray(X, dtype=float)
    if len(X) < max(min_n, X.shape[1] + 3):
        return 0.0, 0.0
    d = turbulence_series(X)
    last = float(d[-1])
    pct = float(np.mean(d[:-1] <= last))
    return last, pct


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


# ========== SYNESTHÉSIE : l'alphabet de FORMES (motifs ordinaux, Bandt-Pompe) ==========
# La « synesthésie » du savant rendue RIGOUREUSE (audit 03/07) : les chiffres
# deviennent des FORMES. Chaque fenêtre de `dim` clôtures est traduite en son motif
# ordinal (le rang relatif des valeurs) — la série de prix devient une suite de
# formes, et la PALETTE de formes du marché se lit statistiquement :
#   • entropie de permutation PONDÉRÉE par l'amplitude (Bandt-Pompe 2002 ;
#     arXiv:2207.01169) : 1 = bruit (toutes les formes équiprobables),
#     bas = le marché « dessine » (structure exploitable) ;
#   • asymétrie des formes MONOTONES (montée franche vs descente franche) =
#     irréversibilité temporelle directionnelle (arXiv:2307.08612, crypto) ;
#   • motifs INTERDITS (jamais tracés) = signature de déterminisme (arXiv:0711.0729).

_MOTIFS3 = {(0, 1, 2): 0, (0, 2, 1): 1, (1, 0, 2): 2, (1, 2, 0): 3, (2, 0, 1): 4, (2, 1, 0): 5}


def motifs_ordinaux(closes, dim=3):
    """Traduit les clôtures en (motifs, poids). PUR. motif = rang ordinal de la
    fenêtre (dim=3 -> 6 formes ; 0 = montée franche, 5 = descente franche) ;
    poids = variance de la fenêtre (weighted PE : une forme tracée sur un mouvement
    AMPLE compte plus qu'une forme dans le bruit de fond). ([], []) si trop court."""
    p = [float(c) for c in closes if c and c > 0]
    if len(p) < dim + 1:
        return [], []
    motifs, poids = [], []
    for i in range(len(p) - dim + 1):
        w = p[i:i + dim]
        ordre = tuple(int(r) for r in np.argsort(np.argsort(w)))
        m = _MOTIFS3.get(ordre)
        if m is None:
            continue
        motifs.append(m)
        mu = sum(w) / dim
        poids.append(sum((x - mu) ** 2 for x in w) / dim)
    return motifs, poids


def synesthesie(closes, dim=3, window=72):
    """Perception SYNESTHÉSIQUE du marché. PUR. Retourne :
      entropie ∈ [0,1] (permutation pondérée, normalisée), biais ∈ [-1,1]
      (asymétrie pondérée montée-franche vs descente-franche), interdits (nb de
      formes jamais tracées), signal ∈ [-1,1] = biais × structure (1−entropie) —
      le marché ne « dit » quelque chose que quand il dessine ET penche."""
    out = {"entropie": 1.0, "biais": 0.0, "interdits": 0, "signal": 0.0}
    p = [float(c) for c in closes if c and c > 0][-(int(window) + 1):]
    motifs, poids = motifs_ordinaux(p, dim)
    if len(motifs) < 24:
        return out
    n_formes = 6
    w_tot = sum(poids) or 1e-12
    freq = [0.0] * n_formes
    for m, w in zip(motifs, poids):
        freq[m] += w
    freq = [f / w_tot for f in freq]
    H = -sum(f * math.log(f) for f in freq if f > 0) / math.log(n_formes)
    monte, descend = freq[0], freq[5]
    biais = (monte - descend) / (monte + descend + 1e-12)
    interdits = sum(1 for f in freq if f == 0.0)
    signal = max(-1.0, min(1.0, biais * (1.0 - H) * 4.0))   # ×4 : (1−H)~0.05-0.2 typique
    out.update({"entropie": round(H, 4), "biais": round(biais, 4),
                "interdits": interdits, "signal": round(signal, 4)})
    return out


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

def signal(candles, fear_greed=None, thresh=0.55, window=72):
    """Cœur PUR : perçoit la rupture de symétrie du tenseur (Mahalanobis), en déduit
    un signal À CONTRE-COURANT de la dislocation, immunisé au bruit, VaR indicative.
    Déterministe, aucun NN.

    FENÊTRE BORNÉE (audit 03/07 — la SEULE amélioration survivante de la mesure) :
    l'ancienne fenêtre non bornée faisait diverger le replay de validation (qui
    passait tout l'historique) du live (80 bougies) ; borner à 72 aligne les deux
    ET améliore : IC replay poolé +0.039 -> +0.095 (1h) et +0.145 -> +0.185
    (15m, t 3.0), plateau stable fen ∈ [56,72]. Variantes REJETÉES à la mesure :
    tenseur enrichi liquidité (−0.02), seuil percentile adaptatif (−0.005),
    direction z 3 barres (−0.009) — cf. §49.

    fear_greed : conservé pour compat ; n'influence PLUS le vote (délégué à
    l'agent `sentiment`, cf. §39)."""
    out = {"anomaly": 0.0, "symmetry_break": 0.0, "direction": 0, "vote": 0.0,
           "confidence": 0.0, "var": {}, "note": "données insuffisantes"}
    X = feature_matrix(candles[-(int(window) + 1):])
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
    vote = max(-1.0, min(1.0, vote))
    conf = min(sb, 1.0) * (0.7 if sb >= thresh else 0.2)

    # SYNESTHÉSIE (audit 03/07) : perception de la PALETTE de formes du marché —
    # calculée et EXPOSÉE, mais PAS votante : sa contribution au vote a échoué à la
    # barre des deux fenêtres (1h : +0.089->+0.102 ; 15m : +0.172->+0.084 — la
    # dégradation dépasse le gain, cf. §50). L'agent la « voit », la rapporte, et
    # les consommateurs (rapports, futurs travaux) peuvent la lire.
    closes = [_row(c)[3] for c in candles[-(int(window) + 1):]]
    syn = synesthesie(closes)
    note = f"anomalie {sb:.2f}" + (
        f" · rupture {'baissière' if direction < 0 else 'haussière'} -> fade" if vote else " · sous seuil")
    if syn["entropie"] < 0.85:
        pente = "montante" if syn["biais"] > 0.15 else "descendante" if syn["biais"] < -0.15 else "plate"
        note += f" · palette H{syn['entropie']:.2f} {pente}"
    out.update({"anomaly": round(sb, 3), "symmetry_break": round(sb, 3),
                "mahalanobis": round(d2, 2), "direction": direction,
                "vote": round(vote, 3), "confidence": round(conf, 3),
                "synesthesie": syn, "var": var, "note": note})
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
