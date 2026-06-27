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


def tail_regime(returns, seed=12345):
    """Classe le régime de queue en comparant Φ du marché à Φ d'une RÉFÉRENCE
    gaussienne de même taille (auto-calibré, déterministe). PUR.
      ratio = Φ_marché / Φ_gauss : ~1 = euclidien (gaussien), >> 1 = blow-up de queue.
    Retourne {phi, phi_gauss, ratio, regime}."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 16:
        return {"phi": 0.0, "phi_gauss": 0.0, "ratio": 1.0, "regime": "n/a"}
    phi = tail_profile(r)
    g = np.random.default_rng(seed).standard_normal(len(r))
    phi_g = tail_profile(g)
    ratio = (phi / phi_g) if phi_g > 0 else 1.0
    regime = "euclidien" if ratio < 1.3 else "transitoire" if ratio < 2.0 else "non_euclidien"
    return {"phi": round(phi, 4), "phi_gauss": round(phi_g, 4),
            "ratio": round(ratio, 3), "regime": regime}


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


# ========== 2) & 3) GRAPHE DE CORRÉLATION : λ₂ (stabilité) + Cheeger ==========

def _normalized_laplacian(A):
    """Laplacien normalisé symétrique L = I − D^{-1/2} A D^{-1/2}. Pur."""
    deg = A.sum(1)
    dinv = np.where(deg > 1e-12, 1.0 / np.sqrt(deg), 0.0)
    return np.eye(len(A)) - (dinv[:, None] * A * dinv[None, :])


def correlation_graph_metrics(returns_matrix, thresh=0.3):
    """STABILITÉ d'intrication d'un panier d'actifs (analogue rank-width). PUR.
    Construit le graphe |corr|>seuil, renvoie la connectivité algébrique λ₂ et les
    bornes de Cheeger (Cheeger : λ₂/2 ≤ h ≤ √(2λ₂)). λ₂ ↑ = réseau intriqué/stable ;
    λ₂ → 0 = le réseau se fragmente (co-intégration en rupture)."""
    X = np.asarray(returns_matrix, dtype=float)
    if X.ndim != 2 or X.shape[1] < 3 or X.shape[0] < 5:
        return {"lambda2": 0.0, "cheeger_low": 0.0, "cheeger_high": 0.0, "n": 0}
    C = np.corrcoef(X, rowvar=False)
    C = np.nan_to_num(C)
    A = np.abs(C) * (np.abs(C) > thresh)
    np.fill_diagonal(A, 0.0)
    if A.sum() <= 0:
        return {"lambda2": 0.0, "cheeger_low": 0.0, "cheeger_high": 0.0, "n": X.shape[1]}
    L = _normalized_laplacian(A)
    ev = np.sort(np.linalg.eigvalsh((L + L.T) / 2))
    lam2 = float(max(0.0, ev[1])) if len(ev) > 1 else 0.0
    return {"lambda2": round(lam2, 4), "cheeger_low": round(lam2 / 2, 4),
            "cheeger_high": round(math.sqrt(2 * lam2), 4), "n": X.shape[1]}


def cheeger_partition(returns_matrix, thresh=0.3):
    """PARTITION de Cheeger du marché en 2 clusters via le vecteur de FIEDLER
    (2e vecteur propre du Laplacien) — base d'une allocation BÊTA-NEUTRE. PUR.
    Retourne {clusters: [+1/−1 par actif], conductance, lambda2}."""
    X = np.asarray(returns_matrix, dtype=float)
    if X.ndim != 2 or X.shape[1] < 3 or X.shape[0] < 5:
        return {"clusters": [], "conductance": None, "lambda2": 0.0}
    C = np.nan_to_num(np.corrcoef(X, rowvar=False))
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


# ========== signal de l'agent (par actif) : régime de queue + toxicité ==========

def signal(closes, order_flow=None):
    """Cœur PUR de l'agent géométrique (par actif). Combine :
      • régime de queue (tool 1) : en blow-up « non-euclidien » -> SUIVI DE TENDANCE
        (ne pas réverter, cf. signal du papier) ; en euclidien -> légère réversion ;
      • toxicité d'ordre supérieur (tool 4) sur l'order-flow (ou les rendements) :
        élevée -> on SE RETIRE (anti-sélection adverse / spoofing).
    Déterministe, borné, aucun NN, aucun ordre."""
    out = {"regime": "n/a", "tail_ratio": 1.0, "toxicity": 0.0, "momentum": 0.0,
           "vote": 0.0, "confidence": 0.0, "note": "données insuffisantes"}
    rets = _returns(closes)
    if len(rets) < 16:
        return out
    tr = tail_regime(rets)
    flow = order_flow if (order_flow is not None and len(order_flow) >= 8) else rets
    tox = higher_order_toxicity(flow)

    r = np.asarray(rets)
    mom = math.tanh(float(r[-8:].sum()) / (r.std() + 1e-9) / 4.0)   # tendance récente normalisée

    if tr["regime"] == "non_euclidien":
        base = 0.45 * mom                          # crise = tendance : suivre, ne pas fader
    elif tr["regime"] == "transitoire":
        base = 0.2 * mom
    else:  # euclidien : marché « gaussien » -> légère réversion
        z = float(r[-1] / (r.std() + 1e-9))
        base = -0.15 * math.tanh(z)

    # gate de toxicité : flux toxique -> on se retire (réduit vote ET confiance)
    vote = max(-1.0, min(1.0, base * (1.0 - tox)))
    conf_base = 0.5 if tr["regime"] == "non_euclidien" else 0.25
    conf = conf_base * (1.0 - 0.8 * tox)

    note = (f"régime {tr['regime']} (×{tr['ratio']}) · toxicité {tox:.2f}"
            + (" · RETRAIT" if tox > 0.6 else ""))
    out.update({"regime": tr["regime"], "tail_ratio": tr["ratio"], "toxicity": round(tox, 3),
                "momentum": round(mom, 3), "vote": round(vote, 3),
                "confidence": round(max(0.0, conf), 3), "note": note})
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
        return signal(closes)
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
        met = correlation_graph_metrics(M)
        part = cheeger_partition(M)
        return {"symbols": used, "metrics": met,
                "partition": {"clusters": dict(zip(used, part["clusters"])),
                              "conductance": part["conductance"]}}
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
        print(f"\nStructure panier : λ₂={ps['metrics'].get('lambda2')} "
              f"(Cheeger {ps['metrics'].get('cheeger_low')}..{ps['metrics'].get('cheeger_high')})")


if __name__ == "__main__":
    main()
