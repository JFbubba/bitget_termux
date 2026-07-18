"""
geometric_agent.py — agent « savant géométrique » : perception de la STRUCTURE
GÉOMÉTRIQUE du marché (régime de queue, intrication de corrélation, toxicité d'ordre
supérieur). Classement : SAFE. Déterministe, lecture seule, AUCUN ordre, AUCUN NN.

Inspiré de 5 articles d'analyse géométrique / théorie des graphes / EDP fournis.
HONNÊTETÉ : ce sont des analogies. On n'implémente PAS les théorèmes à la lettre —
on implémente leur NOYAU CALCULABLE, qui coïncide avec des méthodes quant ÉTABLIES :

  1) Profils isopérimétriques / Grand-Lebesgue  -> détection de régime par
     CONCENTRATION DE QUEUE (réarrangement décroissant, sans échelle) ≈ tail-index ;
     blow-up de queue => marché « non-euclidien » => suivre la tendance, pas réverter.
  2) Rank-width / expansion d'arêtes            -> STABILITÉ du graphe de corrélation
     via la connectivité algébrique λ₂ (clustering spectral) ; λ₂ s'effondre =>
     l'intrication (co-intégration) se rompt => fermer l'arbitrage.
  3) p-Laplacien de Neumann / constante de Cheeger -> PARTITION de Cheeger (vecteur
     de Fiedler) du marché en 2 « ensembles de Cheeger » => allocation bêta-neutre.
  4) Talagrand / Eldan-Gross (Besov, ordre k>1) -> TOXICITÉ d'ordre supérieur :
     ratio variation d'ordre 2 / ordre 1 (les interactions d'ordre supérieur
     dominent) => flux toxique/spoofing => se retirer (anti-sélection adverse).
  5) Inégalité isopérimétrique quantitative      -> cadre de stabilité (déficit) qui
     sous-tend 1) : un déficit isopérimétrique élevé = forme de queue éloignée de la
     boule (gaussienne) = anomalie de régime.

Profil cognitif (neuro-atypique, cf. demande) traduit en CALCUL déterministe :
hyperacuité multi-échelle (lissage OU/Mehler), synesthésie (chiffres->géométrie de
graphe), mémoire eidétique (fenêtres complètes, sans élagage), saut logique
(indicateur direct sans arbre), bruit-carburant (la rugosité devient un signal).

Fonctions de calcul PURES et testables ; fetch réseau enveloppés, ne lèvent jamais.
"""

import math

import numpy as np


# ---------- utilitaires purs ----------

def _returns(closes):
    p = [float(c) for c in closes if c and c > 0]
    return [math.log(p[i] / p[i - 1]) for i in range(1, len(p))]


def _row(c):
    """Bougie dict OU liste [t,o,h,l,c,v] -> (o,h,l,c,v). Pur."""
    if isinstance(c, dict):
        return (float(c["open"]), float(c["high"]), float(c["low"]),
                float(c["close"]), float(c.get("volume", 0) or 0))
    return (float(c[1]), float(c[2]), float(c[3]), float(c[4]),
            float(c[5]) if len(c) > 5 else 0.0)


def _standardize(x):
    x = np.asarray(x, dtype=float)
    sd = x.std()
    return (x - x.mean()) / sd if sd > 1e-12 else x - x.mean()


# ========== 1) RÉGIME DE QUEUE (profil isopérimétrique, sans échelle) ==========

def tail_profile(returns, s0=0.5, n=40):
    """Indicateur Φ de CONCENTRATION DE QUEUE via réarrangement décroissant des
    |rendements| STANDARDISÉS (donc sans échelle : mesure la FORME de la queue, pas
    le niveau de vol). PUR. Φ élevé = masse concentrée dans quelques extrêmes
    (queue lourde / « non-euclidienne »)."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 12:
        return 0.0
    a = np.abs(_standardize(r))
    u = np.sort(a)[::-1]                       # réarrangement décroissant u*
    N = len(u)
    fracs = np.linspace(max(2.0 / N, 0.02), s0, n)
    vols = np.array([u[:max(2, int(N * f))].std() for f in fracs])
    fx = float(np.mean(1.0 / (vols + 1e-9)))   # ~ ∫ 1/profil (profil isopérimétrique inverse)
    return (1.0 / fx) if fx > 0 else 0.0


def hill_tail_index(returns, k_frac=0.12, min_k=12):
    """Indice de queue α par l'estimateur de HILL (loi de puissance), calibré crypto.
    PUR. Réf. arXiv:1803.08405 : pour BTC, α ∈ [2.0, 2.5] (queue lourde) ; α ≳ 3 = quasi
    gaussien. α FAIBLE = queue lourde / blow-up. Sur |rendements standardisés|.
    Retourne (alpha, se, k) ; (None, None, 0) si l'échantillon est trop court.
    NB : Hill est invariant d'échelle (ratios X_i/X_min) -> on centre sur la MÉDIANE
    (robuste) sans diviser par σ (diviser/soustraire la moyenne fausserait la queue)."""
    r = np.asarray(returns, dtype=float)
    a = np.sort(np.abs(r - np.median(r)))[::-1]
    a = a[a > 1e-12]
    npts = len(a)
    if npts < max(40, min_k * 3):
        return (None, None, 0)
    k = min(max(min_k, int(k_frac * npts)), npts - 1)
    xmin = a[k]
    if xmin <= 0:
        return (None, None, 0)
    s = float(np.sum(np.log(a[:k] / xmin)))
    if s <= 0:
        return (None, None, 0)
    alpha = k / s
    return (alpha, alpha / math.sqrt(k), k)


def tail_regime(returns, seed=12345):
    """Classe le régime de queue. PUR. Estimateur PRINCIPAL = indice de queue α de HILL
    (calibré crypto, arXiv:1803.08405) ; repli = Φ vs référence gaussienne.
      • α ≤ 2.5  -> queue lourde / blow-up -> NON_EUCLIDIEN (suivre la tendance) ;
      • α ≥ 3.0  -> quasi gaussien        -> EUCLIDIEN (réverter) ;
      • sinon                              -> TRANSITOIRE.
    Retourne {phi, phi_gauss, ratio, alpha, regime}."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 16:
        return {"phi": 0.0, "phi_gauss": 0.0, "ratio": 1.0, "alpha": None, "regime": "n/a"}
    phi = tail_profile(r)
    g = np.random.default_rng(seed).standard_normal(len(r))
    phi_g = tail_profile(g)
    ratio = (phi / phi_g) if phi_g > 0 else 1.0
    alpha, se, k = hill_tail_index(r)
    # HYBRIDE robuste : α (calibré crypto) tranche les cas DÉCISIFS ; sinon le proxy Φ
    # (stable sur fenêtre courte) décide — Hill est bruité sur < ~6 mois de données.
    w1 = w1_gauss(r)                                # géométrie de la distribution ENTIÈRE
    if alpha is not None and alpha <= 2.2:
        regime = "non_euclidien"                   # queue très lourde (blow-up)
    elif alpha is not None and alpha >= 3.5:
        regime = "euclidien"                       # nettement gaussien
    else:
        # DOUBLE voix (audit 03/07) : proxy de queue Φ ET distance W1 à la gaussienne
        # (calibrée : gaussien ≈ 0.06, t2.5 ≈ 0.24) — l'une OU l'autre tranche le lourd.
        lourd = (ratio >= 2.0) or (w1 is not None and w1 >= 0.22)
        leger = (ratio < 1.3) and (w1 is None or w1 < 0.10)
        regime = "non_euclidien" if lourd else ("euclidien" if leger else "transitoire")
    # Hurst : DFA d'abord (robuste sur n court, arXiv:2310.19051), repli R/S (2205.11122)
    hurst = dfa_hurst(r)
    if hurst is None:
        hurst = hurst_exponent(r)
    return {"phi": round(phi, 4), "phi_gauss": round(phi_g, 4), "ratio": round(ratio, 3),
            "alpha": round(alpha, 3) if alpha is not None else None,
            "w1": round(w1, 4) if w1 is not None else None,
            "hurst": round(hurst, 3) if hurst is not None else None, "regime": regime}


# ========== 6) SIGNATURE DE CHEMIN & GÉOMÉTRIE DE DISTRIBUTION (audit 03/07) ==========
# Recherche complémentaire : signatures de chemins pour la classification de régimes
# (arXiv:2107.00066), aire de Lévy signée en lead-lag (arXiv:2110.12288), robustesse
# des estimateurs de Hurst (arXiv:2310.19051, 1208.4158 : R/S biaisé sur n court, le
# DFA détrende), Hurst dynamique Bitcoin (arXiv:1709.08090).

def levy_area_tp(closes, window=64):
    """AIRE DE LÉVY du chemin (temps, prix) — terme ANTISYMÉTRIQUE du niveau 2 de la
    signature (rough paths). PUR. A = ½Σ(t_i·ΔX_{i+1} − X_i·Δt_{i+1}), t∈[0,1],
    X = log-prix ancré (X₀=0) et réduit par son écart-type.
    Géométrie : 0 = le mouvement suit sa CORDE (ligne droite) ; > 0 = gain concentré
    en FIN de fenêtre (ACCÉLÉRATION, x~t² -> +1/6) ; < 0 = mouvement essoufflé
    (décélération, x~√t -> −1/6). Mesure la CONVEXITÉ du mouvement, pas sa direction.
    Retourne tanh(6A) ∈ (−1,1) ; 0.0 si trop court."""
    p = [float(c) for c in closes if c and c > 0]
    if len(p) < 12:
        return 0.0
    p = p[-int(window):]
    x = np.log(np.asarray(p, dtype=float))
    x = x - x[0]
    sd = float(x.std())
    if sd < 1e-12:
        return 0.0
    x = x / sd
    n = len(x)
    t = np.linspace(0.0, 1.0, n)
    a = 0.5 * float(np.sum(t[:-1] * np.diff(x) - x[:-1] * np.diff(t)))
    return float(math.tanh(6.0 * a))


def dfa_hurst(returns, min_win=8):
    """Exposant de HURST par DFA(1) — plus ROBUSTE que R/S sur échantillon court
    (arXiv:2310.19051, 1208.4158 : R/S sur-estime et biaise sous n≈500 ; le DFA
    détrende chaque fenêtre avant de mesurer la fluctuation). PUR.
    Y = cumsum(r − r̄) ; F(n) = RMS du résidu d'un ajustement LINÉAIRE par fenêtre ;
    H = pente de log F(n) vs log n. None si trop court."""
    r = np.asarray(returns, dtype=float)
    N = len(r)
    if N < 4 * min_win:
        return None
    Y = np.cumsum(r - r.mean())
    tailles = []
    n = int(min_win)
    while n <= N // 4:
        tailles.append(n)
        n = int(round(n * 1.6)) if int(round(n * 1.6)) > n else n + 1
    logn, logf = [], []
    for n in tailles:
        res = []
        for b in range(N // n):
            seg = Y[b * n:(b + 1) * n]
            t = np.arange(n, dtype=float)
            coef = np.polyfit(t, seg, 1)
            res.append(float(np.mean((seg - np.polyval(coef, t)) ** 2)))
        if res:
            f = math.sqrt(max(float(np.mean(res)), 1e-24))
            logn.append(math.log(n)); logf.append(math.log(f))
    if len(logn) < 3:
        return None
    h = float(np.polyfit(logn, logf, 1)[0])
    return h if 0.0 < h < 1.5 else None


def w1_gauss(returns):
    """Distance de WASSERSTEIN-1 des rendements STANDARDISÉS à la gaussienne (le
    transport optimal en 1D = moyenne des |écarts de quantiles|). PUR. Géométrie de
    la DISTRIBUTION ENTIÈRE (Hill ne voit que la queue ; Φ est un proxy) :
    calibré numériquement n=160 : gaussien ≈ 0.06 (p90 0.08), t4 ≈ 0.15,
    t2.5 (crypto) ≈ 0.24. None si trop court."""
    from statistics import NormalDist
    r = np.asarray(returns, dtype=float)
    if len(r) < 32:
        return None
    x = _standardize(r)
    xs = np.sort(x)
    n = len(xs)
    nd = NormalDist()
    q = np.array([nd.inv_cdf((i + 0.5) / n) for i in range(n)])
    return float(np.mean(np.abs(xs - q)))


# ========== 4) TOXICITÉ D'ORDRE SUPÉRIEUR (Besov / Eldan-Gross) ==========

def _gauss_smooth(x, sigma):
    """Lissage gaussien (proxy du semi-groupe OU/Mehler P_t). Pur."""
    if sigma <= 0:
        return np.asarray(x, dtype=float)
    radius = max(1, int(3 * sigma))
    t = np.arange(-radius, radius + 1)
    k = np.exp(-(t ** 2) / (2 * sigma ** 2)); k /= k.sum()
    return np.convolve(np.asarray(x, dtype=float), k, mode="same")


def _rms_variation(x, k):
    """RMS de la variation d'ordre k : √moyenne(|Δ^k x|²). Échelle cohérente entre
    ordres (contrairement à |Δ|^(2/k) qui sous-/sur-évalue selon l'amplitude). Pur."""
    d = np.diff(np.asarray(x, dtype=float), n=k)
    return float(np.sqrt(np.mean(d ** 2))) if len(d) else 0.0


def higher_order_toxicity(series):
    """TOXICITÉ d'ordre supérieur ∈ [0,1] : domination de la variation d'ordre 2 sur
    l'ordre 1 (cf. Eldan-Gross k>1). PUR. Mesure la « rugosité » du chemin :
      • tendance/drift lisse -> Δ² ≈ 0, ordre 1 domine -> ~0 ;
      • flux iid (marche aléatoire) -> ratio ~√3 -> ~0.5 ;
      • flicker/spoofing (allers-retours rapides) -> ordre 2 domine -> ~1.
    Référence : un chemin gaussien donne ratio √(6/2)=√3 ; on recentre dessus."""
    x = _standardize(series)
    if len(x) < 8:
        return 0.0
    v1 = _rms_variation(x, 1)
    v2 = _rms_variation(x, 2)
    ratio = v2 / (v1 + 1e-9)
    return 1.0 - math.exp(-max(0.0, ratio - 1.0))   # borné [0,1], ~0 pour une tendance


def bipower_variation(returns):
    """Variation BIPOWER (Barndorff-Nielsen-Shephard) = (π/2)·Σ|r_{i-1}|·|r_i|. PUR.
    Estimateur de la variance intégrée ROBUSTE AUX SAUTS (les sauts isolés ne la
    gonflent pas, contrairement à la variance réalisée)."""
    r = np.abs(np.asarray(returns, dtype=float))
    if len(r) < 2:
        return 0.0
    return float((math.pi / 2.0) * np.sum(r[1:] * r[:-1]))


def relative_jump(returns):
    """Mesure de SAUT relatif BNS : (RV − BV)/RV ∈ [0,1). PUR. Réf. arXiv:1708.09520.
    Fraction de la variation due aux SAUTS (discontinuités = événements toxiques /
    sélection adverse). ~0 = diffusion lisse ; élevé = sauts dominants."""
    r = np.asarray(returns, dtype=float)
    rv = float(np.sum(r ** 2))
    if rv <= 0:
        return 0.0
    bv = bipower_variation(r)
    return float(max(0.0, min(0.999, (rv - bv) / rv)))


# ========== 2) & 3) GRAPHE DE CORRÉLATION : λ₂ (stabilité) + Cheeger ==========

def _normalized_laplacian(A):
    """Laplacien normalisé symétrique L = I − D^{-1/2} A D^{-1/2}. Pur."""
    deg = A.sum(1)
    dinv = np.where(deg > 1e-12, 1.0 / np.sqrt(deg), 0.0)
    return np.eye(len(A)) - (dinv[:, None] * A * dinv[None, :])


def rmt_denoise(C, q):
    """Débruitage RMT (clipping de Marchenko-Pastur) d'une matrice de CORRÉLATION. PUR.
    Réf. arXiv:1610.08104. q = N/T. Borne du « bulk » de bruit λ+ = (1+√q)² : les
    valeurs propres < λ+ (bruit d'échantillon) sont remplacées par leur moyenne (trace
    préservée), celles > λ+ (signal) sont gardées. Renormalise la diagonale à 1.
    Indispensable en crypto (T court, N/T grand) AVANT de bâtir le graphe."""
    C = np.asarray(C, dtype=float)
    w, V = np.linalg.eigh((C + C.T) / 2)
    lam_plus = (1.0 + math.sqrt(max(q, 1e-9))) ** 2
    bulk = w < lam_plus
    if bulk.sum() >= 1 and (~bulk).sum() >= 1:
        w = np.where(bulk, float(w[bulk].mean()), w)
        Cc = V @ np.diag(w) @ V.T
        d = np.sqrt(np.clip(np.diag(Cc), 1e-12, None))
        Cc = Cc / np.outer(d, d)
        return np.clip(Cc, -1.0, 1.0)
    return C


def _apply_denoise(C, q, method):
    """Débruitage de la matrice de corrélation. method: True/'rmt' = clip Marchenko-Pastur ;
    'rie' = shrinkage NON-LINÉAIRE de Ledoit-Péché (plus fin, garde les vecteurs propres) ;
    False = brut. Pur."""
    if not method:
        return C
    if method == "rie":
        return rie_denoise(C, q)
    return rmt_denoise(C, q)


def _market_mode(C):
    """MARKET MODE = λ₁/N (part de variance du mode dominant = risque SYSTÉMIQUE /
    co-mouvement ; littérature RMT : λ₁ élevé => tout bouge ensemble) + PARTICIPATION du
    mode dominant ∈ (0,1] (1 = mode réparti sur tout le panier ; petit = capturé par
    quelques actifs). Pur. Réf. arXiv:1911.08944 (facteur de marché crypto)."""
    w, V = np.linalg.eigh((C + C.T) / 2)
    N = len(w)
    i1 = int(np.argmax(w))
    v1 = V[:, i1]
    s2 = float(np.sum(v1 ** 2)) or 1.0
    pr = float((s2 ** 2) / (np.sum(v1 ** 4) + 1e-18) / N)      # participation normalisée
    return float(max(w)) / N, pr


def _laplacian_max_gap(A):
    """MAX SPECTRAL GAP du Laplacien COMBINATOIRE L=D−A (indicateur de CRASH/fragmentation,
    PLOS One 2024, PMC12273962 : maxΔλ = max_k(λ_{k+1}−λ_k) est GRAND quand le graphe se
    scinde en composantes — crash — et ≈0 en régime normal connecté). Pur."""
    deg = A.sum(1)
    L = np.diag(deg) - A
    ev = np.sort(np.linalg.eigvalsh((L + L.T) / 2))
    return float(np.max(np.diff(ev))) if len(ev) > 1 else 0.0


def correlation_graph_metrics(returns_matrix, thresh=0.5, denoise=True):
    """STABILITÉ d'intrication d'un panier d'actifs (analogue rank-width). PUR.
    Construit le graphe |corr|>seuil, renvoie la connectivité algébrique λ₂ et les
    bornes de Cheeger (Cheeger : λ₂/2 ≤ h ≤ √(2λ₂)). λ₂ ↑ = réseau intriqué/stable ;
    λ₂ → 0 = le réseau se fragmente (co-intégration en rupture).
    ENRICHI 18/07 (recherche « graphes isopérimétriques », grounded) — ajoute au spectre :
      • market_mode = λ₁/N (risque SYSTÉMIQUE / co-mouvement) + participation du mode ;
      • n_factors = nb de valeurs propres au-dessus du bulk Marchenko-Pastur (structure
        RÉELLE vs bruit d'échantillon) ;
      • max_gap = max spectral gap du Laplacien combinatoire (crash-indicator PLOS 2024).
    denoise: True/'rmt' (défaut, rétro-compatible) · 'rie' (Ledoit-Péché, plus fin) · False."""
    dflt = {"lambda2": 0.0, "cheeger_low": 0.0, "cheeger_high": 0.0, "n": 0,
            "market_mode": 0.0, "participation": 0.0, "n_factors": 0, "max_gap": 0.0}
    X = np.asarray(returns_matrix, dtype=float)
    if X.ndim != 2 or X.shape[1] < 3 or X.shape[0] < 5:
        return dflt
    q = X.shape[1] / X.shape[0]
    C = np.nan_to_num(np.corrcoef(X, rowvar=False))
    if denoise and X.shape[0] > X.shape[1]:        # débruitage (T > N requis)
        C = _apply_denoise(C, q, denoise)
    mm, pr = _market_mode(C)
    lam_plus = (1.0 + math.sqrt(max(q, 1e-9))) ** 2
    n_factors = int((np.linalg.eigvalsh((C + C.T) / 2) > lam_plus).sum())
    A = np.abs(C) * (np.abs(C) > thresh)
    np.fill_diagonal(A, 0.0)
    out = {**dflt, "n": X.shape[1], "market_mode": round(mm, 4),
           "participation": round(pr, 4), "n_factors": n_factors}
    if A.sum() <= 0:
        return out
    L = _normalized_laplacian(A)
    ev = np.sort(np.linalg.eigvalsh((L + L.T) / 2))
    lam2 = float(max(0.0, ev[1])) if len(ev) > 1 else 0.0
    out.update({"lambda2": round(lam2, 4), "cheeger_low": round(lam2 / 2, 4),
                "cheeger_high": round(math.sqrt(2 * lam2), 4),
                "max_gap": round(_laplacian_max_gap(A), 4)})
    return out


def connectivity_regime(metrics, hist=None):
    """RÉGIME DE CONNECTIVITÉ du marché depuis le spectre isopérimétrique (grounded, 2024).
    λ₁/N (market mode) haut = co-mouvement SYSTÉMIQUE (risk-off / crash-comovement) ;
    max_gap haut + λ₂ bas = FRAGMENTATION (graphe scindé, co-intégration rompue) ;
    sinon marché NORMAL/diversifié. `hist` optionnel = {clé: (moyenne, écart)} pour juger
    en Z-SCORE (DYNAMIQUE — recommandé, la littérature signale le CHANGEMENT, pas le niveau)
    plutôt qu'en seuil absolu. Retourne {regime, market_mode, fragmentation, systemic_z}. PUR."""
    mm = float(metrics.get("market_mode", 0.0))
    lam2 = float(metrics.get("lambda2", 0.0))
    gap = float(metrics.get("max_gap", 0.0))

    def _z(key, val):
        if hist and key in hist:
            mu, sd = hist[key]
            return (val - mu) / sd if sd and sd > 1e-9 else 0.0
        return None

    zmm, zgap = _z("market_mode", mm), _z("max_gap", gap)
    if zmm is not None:                                   # dynamique (préféré)
        if zmm >= 1.0:
            regime = "systemique"
        elif zgap is not None and zgap >= 1.0 and lam2 <= 0.05:
            regime = "fragmente"
        else:
            regime = "normal"
    else:                                                 # heuristique absolue (à calibrer)
        if mm >= 0.55:
            regime = "systemique"
        elif lam2 <= 0.05 and gap > 0:
            regime = "fragmente"
        else:
            regime = "normal"
    return {"regime": regime, "market_mode": round(mm, 4), "fragmentation": round(gap, 4),
            "lambda2": round(lam2, 4), "systemic_z": round(zmm, 2) if zmm is not None else None}


def cheeger_partition(returns_matrix, thresh=0.5, denoise=True):
    """PARTITION de Cheeger du marché en 2 clusters via le vecteur de FIEDLER
    (2e vecteur propre du Laplacien) — base d'une allocation BÊTA-NEUTRE. PUR.
    Corrélation débruitée par RMT (arXiv:1610.08104) avant la coupe.
    Retourne {clusters: [+1/−1 par actif], conductance, lambda2}."""
    X = np.asarray(returns_matrix, dtype=float)
    if X.ndim != 2 or X.shape[1] < 3 or X.shape[0] < 5:
        return {"clusters": [], "conductance": None, "lambda2": 0.0}
    C = np.nan_to_num(np.corrcoef(X, rowvar=False))
    if denoise and X.shape[0] > X.shape[1]:
        C = rmt_denoise(C, X.shape[1] / X.shape[0])
    A = np.abs(C) * (np.abs(C) > thresh); np.fill_diagonal(A, 0.0)
    if A.sum() <= 0:
        return {"clusters": [0] * X.shape[1], "conductance": None, "lambda2": 0.0}
    deg = A.sum(1)
    L = np.diag(deg) - A                          # Laplacien combinatoire
    w, V = np.linalg.eigh((L + L.T) / 2)
    fiedler = V[:, 1] if V.shape[1] > 1 else V[:, 0]
    clusters = np.where(fiedler >= 0, 1, -1)
    # conductance de la coupe (perimètre/volume) — « ratio de Cheeger » empirique
    s = clusters > 0
    cut = float(A[np.ix_(s, ~s)].sum())
    vol = float(min(deg[s].sum(), deg[~s].sum()))
    cond = (cut / vol) if vol > 0 else None
    return {"clusters": [int(c) for c in clusters],
            "conductance": round(cond, 4) if cond is not None else None,
            "lambda2": round(float(max(0.0, w[1])), 4)}


# ========== upgrades empiriques (papiers fournis, OHLCV uniquement) ==========

def hurst_exponent(returns, min_n=8):
    """Exposant de HURST par rescaled-range (R/S). PUR. Réf. arXiv:2205.11122.
    H > 0.5 = persistant (TENDANCE) ; H < 0.5 = anti-persistant (RÉVERSION) ; 0.5 =
    marche aléatoire. Retourne H ∈ ]0,1[ ou None si trop court."""
    r = np.asarray(returns, dtype=float)
    N = len(r)
    if N < 4 * min_n:
        return None
    ns = []
    n = min_n
    while n <= N // 2:
        ns.append(n); n *= 2
    logn, logrs = [], []
    for n in ns:
        rs = []
        for b in range(N // n):
            seg = r[b * n:(b + 1) * n]
            Y = np.cumsum(seg - seg.mean())
            R = float(Y.max() - Y.min()); S = float(seg.std())
            if S > 1e-12 and R > 0:
                rs.append(R / S)
        if rs:
            logn.append(math.log(n)); logrs.append(math.log(float(np.mean(rs))))
    if len(logn) < 2:
        return None
    return float(np.polyfit(logn, logrs, 1)[0])


def parkinson_vol(highs, lows):
    """Volatilité de PARKINSON (haut/bas) : σ = 0.6005612·ln(H/L) par barre. PUR.
    Réf. arXiv:2606.15715. 0.6005612 = 1/(2√ln2). Estimateur de vol efficace (OHLCV)."""
    h, l = np.asarray(highs, float), np.asarray(lows, float)
    m = (h > 0) & (l > 0) & (h >= l)
    return float(0.6005612 * np.mean(np.log(h[m] / l[m]))) if m.any() else 0.0


def rie_denoise(C, q, eta=None):
    """Débruitage RIE de LEDOIT-PÉCHÉ (shrinkage NON-LINÉAIRE). PUR. Réf. arXiv:1610.08104,
    2510.19130. ξ_k = λ_k / |1 − q + q·λ_k·s(λ_k − iη)|², s = Stieltjes empirique,
    η = N^{-1/2}. Garde les vecteurs propres, ne shrink que les valeurs propres
    (rotationnellement invariant). Plus fin que le clip-to-mean MP de rmt_denoise."""
    C = np.asarray(C, float)
    w, V = np.linalg.eigh((C + C.T) / 2)
    N = len(w)
    eta = N ** -0.5 if eta is None else eta
    xi = np.empty(N)
    for k in range(N):
        z = w[k] - 1j * eta
        s = np.mean(1.0 / (z - w))                  # transformée de Stieltjes empirique
        denom = abs(1 - q + q * w[k] * s) ** 2
        xi[k] = (w[k] / denom) if denom > 1e-12 else w[k]
    xi = np.clip(xi.real, 1e-8, None)               # ξ(λ_k) reste APPARIÉ à v_k (PAS de tri :
    Cc = V @ np.diag(xi) @ V.T                       # trier décorrélerait valeurs propres/vecteurs)
    d = np.sqrt(np.clip(np.diag(Cc), 1e-12, None))
    return np.clip(Cc / np.outer(d, d), -1.0, 1.0)


def sponge_partition(returns_matrix, tau=1.0, denoise=True):
    """Partition SIGNÉE (SPONGE, k=2) gérant les corrélations NÉGATIVES — legs
    long/short bêta-neutres. PUR. Réf. arXiv:1904.08575. τ⁺=τ⁻=1 (défaut du papier).
    Pencil (L⁺+τD⁻) x = μ (L⁻+τD⁺) x ; on prend le vecteur propre généralisé adapté.
    Retourne {clusters:[+1/−1], n}. Met les actifs anti-corrélés sur des legs OPPOSÉS."""
    X = np.asarray(returns_matrix, float)
    if X.ndim != 2 or X.shape[1] < 3 or X.shape[0] < 5:
        return {"clusters": [], "n": 0}
    C = np.nan_to_num(np.corrcoef(X, rowvar=False))
    if denoise and X.shape[0] > X.shape[1]:
        C = rmt_denoise(C, X.shape[1] / X.shape[0])
    np.fill_diagonal(C, 0.0)
    n = len(C)
    Ap, Am = np.maximum(C, 0.0), np.maximum(-C, 0.0)
    Dp, Dm = np.diag(Ap.sum(1)), np.diag(Am.sum(1))
    Lp, Lm = Dp - Ap, Dm - Am
    A = Lp + tau * Dm
    B = Lm + tau * Dp + 1e-6 * np.eye(n)            # SPD -> symétrisable proprement
    try:
        wB, VB = np.linalg.eigh((B + B.T) / 2)
        Bisq = VB @ np.diag(1.0 / np.sqrt(np.clip(wB, 1e-12, None))) @ VB.T
        M = Bisq @ ((A + A.T) / 2) @ Bisq           # symétrique -> eigh réel
        wM, VM = np.linalg.eigh((M + M.T) / 2)
        # plus petite valeur propre généralisée (minimise le quotient de Rayleigh) ;
        # on saute un vecteur quasi-constant (trivial) le cas échéant.
        idx = 0
        x = Bisq @ VM[:, 0]
        if float(np.std(x)) < 1e-9 and VM.shape[1] > 1:
            idx = 1; x = Bisq @ VM[:, 1]
    except Exception:
        return {"clusters": [0] * X.shape[1], "n": X.shape[1]}
    clusters = np.where(x >= np.median(x), 1, -1)
    return {"clusters": [int(c) for c in clusters], "n": X.shape[1]}


def _cluster_var(cov, idx):
    sub = cov[np.ix_(idx, idx)]
    iv = 1.0 / np.clip(np.diag(sub), 1e-12, None); iv /= iv.sum()
    return float(iv @ sub @ iv)


def hrp_weights(returns_matrix):
    """Hierarchical Risk Parity (López de Prado) : poids déterministes SANS inversion
    de matrice. PUR. Réf. arXiv:2202.02728. Sériation spectrale (Fiedler) →
    bisection récursive inverse-variance. Robuste à la covariance mal conditionnée
    (crypto). Retourne array de poids (somme=1, tous ≥0) ou None."""
    X = np.asarray(returns_matrix, float)
    if X.ndim != 2 or X.shape[1] < 2 or X.shape[0] < 5:
        return None
    cov = np.cov(X, rowvar=False)
    C = np.nan_to_num(np.corrcoef(X, rowvar=False))
    # quasi-diagonalisation : ordre par le vecteur de Fiedler de la distance corr
    A = np.abs(C); np.fill_diagonal(A, 0.0)
    try:
        L = _normalized_laplacian(A)
        _, Vf = np.linalg.eigh((L + L.T) / 2)
        order = list(np.argsort(Vf[:, 1])) if Vf.shape[1] > 1 else list(range(X.shape[1]))
    except Exception:
        order = list(range(X.shape[1]))
    w = {i: 1.0 for i in order}
    clusters = [order]
    while clusters:
        nxt = []
        for cl in clusters:
            if len(cl) > 1:
                h = len(cl) // 2
                c0, c1 = cl[:h], cl[h:]
                v0, v1 = _cluster_var(cov, c0), _cluster_var(cov, c1)
                a = 1.0 - v0 / (v0 + v1) if (v0 + v1) > 0 else 0.5
                for i in c0:
                    w[i] *= a
                for i in c1:
                    w[i] *= (1.0 - a)
                nxt += [c0, c1]
        clusters = nxt
    out = np.array([w[i] for i in range(X.shape[1])])
    s = out.sum()
    return out / s if s > 0 else out


def signed_volume_ofi(candles, window=10):
    """PROXY OHLCV d'Order-Flow Imbalance (PROXY DÉGRADÉ, PAS le vrai OFI carnet). PUR.
    Réf. arXiv:2112.13213 (dégradé). sOFI_t = signe(Δclose)·volume, somme glissante
    normalisée ∈ [−1,1]. ⚠️ Le VRAI OFI multi-niveau exige le carnet L2/L3 (cf.
    microstructure.py / collector) — ceci n'en est qu'une ombre au niveau bougie."""
    rows = [_row(c) for c in candles]
    if len(rows) < window + 1:
        return 0.0
    closes = [r[3] for r in rows]; vols = [r[4] for r in rows]
    s = [(1 if closes[i] > closes[i - 1] else -1 if closes[i] < closes[i - 1] else 0) * vols[i]
         for i in range(1, len(rows))]
    recent = s[-window:]
    vbar = float(np.mean([abs(x) for x in s[-window:]])) or 1.0
    return float(max(-1.0, min(1.0, sum(recent) / (window * vbar))))


# ========== signal de l'agent (par actif) : régime de queue + toxicité ==========

def signal(closes, order_flow=None, micro=None):
    """Cœur PUR de l'agent géométrique (par actif). Combine :
      • régime de queue (tool 1) : en blow-up « non-euclidien » -> SUIVI DE TENDANCE
        (ne pas réverter, cf. signal du papier) ; en euclidien -> légère réversion ;
      • toxicité d'ordre supérieur (tool 4) : rugosité + saut BNS, ENRICHIE par la
        microstructure RÉELLE (`micro` = microstructure.summary) si le buffer L2/tape
        est alimenté ; sinon repli sur les rendements. Toxicité haute -> on SE RETIRE.
    Déterministe, borné, aucun NN, aucun ordre."""
    out = {"regime": "n/a", "tail_ratio": 1.0, "toxicity": 0.0, "momentum": 0.0,
           "vote": 0.0, "confidence": 0.0, "note": "données insuffisantes"}
    rets = _returns(closes)
    if len(rets) < 16:
        return out
    tr = tail_regime(rets)
    flow = order_flow if (order_flow is not None and len(order_flow) >= 8) else rets
    # toxicité = rugosité d'ordre supérieur ⊕ saut BNS (indépendants, borné [0,1]) :
    # capte à la fois le flicker (ordre 2/ordre 1) et les SAUTS (RV vs bipower).
    tox_rough = higher_order_toxicity(flow)
    jump = relative_jump(rets)
    tox = 1.0 - (1.0 - tox_rough) * (1.0 - jump)
    # microstructure RÉELLE (carnet L2 + tape) si disponible : la markout adverse /
    # le spread élargi dominent quand le buffer est alimenté (sinon proxy OHLCV).
    if micro and micro.get("n", 0) >= 10:
        tox = 1.0 - (1.0 - tox) * (1.0 - float(micro.get("toxicity", 0.0)))

    r = np.asarray(rets)
    # ---- DIRECTION (réécrite à l'audit du 03/07, MESURÉE avant/après) ----
    # L'ancien cœur « suivre le momentum 8 barres » CONTREDISAIT le fait stylisé
    # mesuré par la recherche du dépôt (§35-38 : la réversion COURT TERME est réelle
    # en crypto) : IC replay poolé −0.05 (1h) / −0.09 (15m) sur 4 symboles. Nouveau
    # cœur MIX, hypothèse tirée de §35-38 + littérature signatures (2107.00066) :
    #   • RÉVERSION du mouvement COURT (z 8 barres) — toujours active ;
    #   • TENDANCE LONGUE (32 barres) qualifiée par Hurst (DFA, 2310.19051) et par
    #     l'AIRE DE LÉVY (accélération dans le sens de la tendance), COUPÉE en
    #     régime euclidien (gaussien : le suivi de tendance n'y a pas de support).
    # Mesuré sur bougies FIGÉES (replay étalon, 4 symboles, 2 fenêtres
    # indépendantes) : IC poolé −0.05 -> +0.11 (1h, t +1.8) et −0.09 -> +0.17
    # (15m, t +1.9), positif sur chacun des 4 symboles.
    # HONNÊTETÉ (§54, 1 AN d'historique) : sur 12 mois, ce cœur fait −0.07 (t −2.6)
    # quand l'ancien faisait +0.045 — les « 2 fenêtres indépendantes » partageaient
    # le MÊME régime réversif. Le split conditionnel mesuré sur l'an (queue lourde
    # -> réversion ; transitoire/gaussien -> momentum) échoue lui aussi hors
    # échantillon (15m −0.10). AUCUNE formulation ne passe les 3 fenêtres : le
    # signal est RÉGIME-DÉPENDANT par nature. Décision : v2 reste (colle au régime
    # courant), et c'est la couche adaptative qui arbitre — hit-rate EWMA (§51)
    # côté poids, porte ANNUELLE (§54) côté promotion LIVE.
    mom8 = math.tanh(float(r[-8:].sum()) / (r.std() * math.sqrt(8) + 1e-9) / 2.0)
    mom32 = math.tanh(float(r[-32:].sum()) / (r.std() * math.sqrt(32) + 1e-9) / 2.0)
    h = tr.get("hurst")
    htrend = max(0.5, min(1.5, 1.0 + 2.0 * (h - 0.5))) if h is not None else 1.0
    acc = levy_area_tp(closes)                     # convexité signée (signature niv. 2)
    reversion = -0.35 * mom8
    tendance = 0.2 * mom32 * htrend * (1.0 + 0.25 * acc * (1.0 if mom32 >= 0 else -1.0))
    base = reversion + (tendance if tr["regime"] != "euclidien" else 0.0)

    # gate de toxicité : flux toxique -> on se retire (réduit vote ET confiance)
    vote = max(-1.0, min(1.0, base * (1.0 - tox)))
    conf_base = 0.45 if tr["regime"] == "non_euclidien" else 0.35
    conf = conf_base * (1.0 - 0.8 * tox)

    note = (f"régime {tr['regime']}"
            + (f" (α{tr['alpha']})" if tr.get("alpha") is not None else f" (×{tr['ratio']})")
            + f" · rev{-mom8:+.2f} tend{mom32:+.2f} lévy{acc:+.2f}"
            + f" · toxicité {tox:.2f}" + (f" saut {jump:.2f}" if jump > 0.1 else "")
            + (" · RETRAIT" if tox > 0.6 else ""))
    out.update({"regime": tr["regime"], "tail_ratio": tr["ratio"], "alpha": tr.get("alpha"),
                "w1": tr.get("w1"), "hurst": tr.get("hurst"), "levy": round(acc, 3),
                "toxicity": round(tox, 3), "jump": round(jump, 3), "momentum": round(mom32, 3),
                "vote": round(vote, 3), "confidence": round(max(0.0, conf), 3), "note": note})
    return out


# ========== intégration : analyse live + agent + structure de portefeuille ==========

def _closes(symbol, limit=160):
    try:
        import market_sources as ms
        c = ms.closes(symbol, limit)
        if c and len(c) >= 40:
            return c
    except Exception:
        pass
    try:
        import technicals as tk
        return [float(x["close"]) for x in tk.fetch_candles(symbol, "15m", limit)]
    except Exception:
        return []


def analyze(symbol="BTCUSDT", ttl=45):
    """Analyse géométrique live (régime de queue + toxicité), cachée, best-effort."""
    import runtime_cache as rc

    def fetch():
        closes = _closes(symbol)
        if len(closes) < 40:
            return {"regime": "n/a", "vote": 0.0, "confidence": 0.0, "note": "n/a"}
        micro = None
        try:                                            # microstructure réelle si le collecteur tourne
            import microstructure
            micro = microstructure.summary(symbol)
        except Exception:
            micro = None
        return signal(closes, micro=micro)
    return rc.get(f"geom:{symbol.upper()}", ttl, fetch,
                  fallback={"regime": "n/a", "vote": 0.0, "confidence": 0.0, "note": "n/a"})


def agent(symbol="BTCUSDT"):
    """Adaptateur agent du cerveau (essaim) : {vote, confidence, note}. Best-effort."""
    a = analyze(symbol)
    return {"vote": a.get("vote", 0.0), "confidence": a.get("confidence", 0.0),
            "note": a.get("note", "n/a")}


def portfolio_structure(symbols=None, ttl=300):
    """ADVISORY multi-actifs : stabilité d'intrication (λ₂) + partition de Cheeger
    du panier suivi. Best-effort, caché. Réponse aux tools 2 & 3 (niveau portefeuille)."""
    import runtime_cache as rc

    def fetch():
        syms = symbols
        if not syms:
            try:
                import config
                syms = list(config.SYMBOLS)
            except Exception:
                syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        series = []
        used = []
        for s in syms[:24]:
            c = _closes(s, 120)
            r = _returns(c)
            if len(r) >= 40:
                series.append(r); used.append(s)
        if len(series) < 3:
            return {"symbols": used, "metrics": {}, "partition": {}}
        L = min(len(r) for r in series)
        M = np.array([r[-L:] for r in series]).T          # (T, D)
        met = correlation_graph_metrics(M, denoise="rie")  # RIE = shrinkage non-linéaire (plus fin que MP)
        regime = connectivity_regime(met)                  # spectre isopérimétrique -> régime (sort de la dormance)
        part = cheeger_partition(M)
        sponge = sponge_partition(M)                       # partition SIGNÉE (legs bêta-neutres)
        hrp = hrp_weights(M)                               # poids HRP (allocation intra-panier)
        return {"symbols": used, "metrics": met, "connectivity_regime": regime,
                "partition": {"clusters": dict(zip(used, part["clusters"])),
                              "conductance": part["conductance"]},
                "signed_legs": dict(zip(used, sponge["clusters"])) if sponge["clusters"] else {},
                "hrp_weights": dict(zip(used, [round(float(x), 4) for x in hrp])) if hrp is not None else {}}
    return rc.get("geom_portfolio", ttl, fetch, fallback={"symbols": [], "metrics": {}})


def build_report(a):
    return ("=== AGENT SAVANT GÉOMÉTRIQUE ===\n"
            f"Régime de queue : {a.get('regime', 'n/a')} (×{a.get('tail_ratio', 1)})\n"
            f"Toxicité d'ordre supérieur : {a.get('toxicity', 0)} "
            f"({'RETRAIT' if a.get('toxicity', 0) > 0.6 else 'OK'})\n"
            f"Vote {a.get('vote', 0):+} · conf {a.get('confidence', 0)} | {a.get('note', '')}\n"
            "Déterministe, LECTURE SEULE. Aucun ordre, aucun NN. VERDICT: SAFE")


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(analyze(sym)))
    ps = portfolio_structure()
    if ps.get("metrics"):
        m = ps["metrics"]; rg = ps.get("connectivity_regime", {})
        print(f"\nStructure panier (spectre isopérimétrique) :")
        print(f"  λ₂={m.get('lambda2')} (Cheeger {m.get('cheeger_low')}..{m.get('cheeger_high')}) "
              f"· fragmentation max_gap={m.get('max_gap')}")
        print(f"  market mode λ₁/N={m.get('market_mode')} (participation {m.get('participation')}, "
              f"{m.get('n_factors')} facteur(s) signif.) -> RÉGIME DE CONNECTIVITÉ : "
              f"{rg.get('regime','n/a').upper()}")


if __name__ == "__main__":
    main()
