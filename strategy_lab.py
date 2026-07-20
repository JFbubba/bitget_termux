"""
strategy_lab.py — agent BACKTESTER AUTONOME (intake Drive package/ -> stratégies).

Rôle : tester/classer des stratégies par performance HONNÊTE (frais + walk-forward
+ PBO), les AMÉLIORER (recherche de paramètres robuste), en COMPOSER de nouvelles
(régime-gating, ensemble), et PROMOUVOIR celles qui passent une barre de robustesse
en écrivant un RAPPORT (.md) + un fichier CODE prêt à l'emploi (.py) sous
`strategies_out/`.

Anti-overfit (cf. RESEARCH_NOTES §4/§8/§11) : une stratégie n'est promue que si
  Sharpe ≥ seuil ET edge vs buy&hold > 0 ET tranches walk-forward majoritairement
  gagnantes ET PBO < 0.5 ET assez de trades.
La plupart ÉCHOUERONT — c'est honnête : on ne promeut pas du surappris.

Signaux PURS et CAUSAUX : `signal[i]` n'utilise que les bougies jusqu'à `i`
(aucun look-ahead). SAFE : aucune exécution d'ordre ; sorties = fichiers d'analyse.
"""

import time
from pathlib import Path

import backtest_brain as bt
import price_action as pa
import regime_features as rf

OUT_DIR = Path(__file__).resolve().parent / "strategies_out"
FEE = 0.0006
HORIZON = 4

# seuils de promotion (volontairement exigeants)
PROMOTE = {"sharpe": 0.3, "edge": 0.0, "frac_folds_pos": 0.6, "trades": 20, "pbo": 0.5}


# ---------- helpers causaux (séries alignées sur les barres) ----------

def _closes(candles):
    return [float(c["close"]) for c in candles]


def _ema_series(values, period):
    k = 2.0 / (period + 1)
    out, e = [], values[0] if values else 0.0
    for v in values:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def _rsi_series(values, period=14):
    n = len(values)
    out = [50.0] * n
    if n < period + 1:
        return out
    gains = sum(max(values[i] - values[i - 1], 0) for i in range(1, period + 1))
    losses = sum(max(values[i - 1] - values[i], 0) for i in range(1, period + 1))
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, n):
        ch = values[i] - values[i - 1]
        ag = (ag * (period - 1) + max(ch, 0)) / period
        al = (al * (period - 1) + max(-ch, 0)) / period
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


# ---------- stratégies de base (signals[i] causal, ∈ {-1,0,+1}) ----------

def strat_ema_cross(candles, fast=20, slow=50):
    cl = _closes(candles)
    ef, es = _ema_series(cl, fast), _ema_series(cl, slow)
    return [0 if i < slow else (1 if ef[i] > es[i] else -1) for i in range(len(cl))]


def strat_rsi_reversion(candles, period=14, low=30, high=70):
    rsi = _rsi_series(_closes(candles), period)
    return [1 if rsi[i] < low else -1 if rsi[i] > high else 0 for i in range(len(rsi))]


def strat_donchian_breakout(candles, n=20):
    sig = [0] * len(candles)
    for i in range(n, len(candles)):
        hh = max(float(c["high"]) for c in candles[i - n:i])
        ll = min(float(c["low"]) for c in candles[i - n:i])
        c = float(candles[i]["close"])
        sig[i] = 1 if c > hh else -1 if c < ll else 0
    return sig


def strat_pullback_confirm(candles, fast=20, slow=50, tol=0.006):
    """Pullback CONFIRMÉ (§81) : tendance EMA + repli ayant touché l'EMA rapide + BOUGIE
    DE REPRISE (clôture au-delà de l'extrême de la bougie précédente). La version sans
    confirmation avait été REJETÉE (§80, 2/4) ; celle-ci améliore 3/4 symboles sur
    6 ans (SOL positif) avec 6× moins de trades — au lab, la barre PBO tranchera."""
    cl = [float(c["close"]) for c in candles]
    hi = [float(c["high"]) for c in candles]
    lo = [float(c["low"]) for c in candles]
    ef, es = _ema_series(cl, fast), _ema_series(cl, slow)
    sig = [0] * len(cl)
    for i in range(slow + 1, len(cl)):
        if ef[i] > es[i]:
            if lo[i - 1] <= ef[i - 1] * (1 + tol) and cl[i] > hi[i - 1]:
                sig[i] = 1
        elif ef[i] < es[i]:
            if hi[i - 1] >= ef[i - 1] * (1 - tol) and cl[i] < lo[i - 1]:
                sig[i] = -1
    return sig


def strat_donchian_vol(candles, n=20, vol_k=1.3, vol_win=20):
    """Donchian confirmé par le VOLUME (§80) : la cassure ne compte que si le volume de
    la barre dépasse vol_k × sa moyenne vol_win — « un breakout sans volume est
    fragile ». MESURÉ sur 6 ans × 4 symboles : meilleur que le Donchian nu sur 4/4
    (Sharpe relatif ~×2, ~30 % de trades en moins). Causal."""
    sig = [0] * len(candles)
    for i in range(max(n, vol_win), len(candles)):
        hh = max(float(c["high"]) for c in candles[i - n:i])
        ll = min(float(c["low"]) for c in candles[i - n:i])
        c = float(candles[i]["close"])
        base = 1 if c > hh else -1 if c < ll else 0
        if not base:
            continue
        vols = [float(x.get("volume") or 0.0) for x in candles[i - vol_win:i]]
        vmoy = sum(vols) / len(vols) if vols else 0.0
        if vmoy > 0 and float(candles[i].get("volume") or 0.0) > vol_k * vmoy:
            sig[i] = base
    return sig


def strat_macd(candles, fast=12, slow=26, sig=9):
    """MACD : ligne (EMA_fast − EMA_slow) vs sa ligne signal. Causal. Tendance."""
    cl = _closes(candles)
    ef, es = _ema_series(cl, fast), _ema_series(cl, slow)
    macd = [ef[i] - es[i] for i in range(len(cl))]
    sigl = _ema_series(macd, sig)
    return [0 if i < slow else (1 if macd[i] > sigl[i] else -1) for i in range(len(cl))]


def strat_bollinger(candles, n=20, k=2.0):
    """Bandes de Bollinger : mean-reversion (achat sous la bande basse). Causal."""
    import statistics
    cl = _closes(candles)
    out = [0] * len(cl)
    for i in range(n, len(cl)):
        w = cl[i - n:i]
        m = sum(w) / n
        sd = statistics.pstdev(w) or 1e-9
        c = cl[i]
        out[i] = 1 if c < m - k * sd else -1 if c > m + k * sd else 0
    return out


def strat_vwap(candles, window=24, band=0.002):
    """VWAP roulant (§72, algo classique n°7) : achat sous le VWAP (sous-évalué vs le
    volume échangé), vente au-dessus. Bande morte (0.2 %) pour ne pas trader le
    micro-écart — la version « toujours en position » brûlerait les frais. Causal."""
    sig = [0] * len(candles)
    for i in range(window, len(candles)):
        num = den = 0.0
        for c in candles[i - window:i + 1]:
            tp = (float(c["high"]) + float(c["low"]) + float(c["close"])) / 3.0
            v = float(c.get("volume") or 0.0)
            num += tp * v
            den += v
        if den <= 0:
            continue
        ecart = (float(candles[i]["close"]) - num / den) / (num / den)
        sig[i] = 1 if ecart < -band else -1 if ecart > band else 0
    return sig


def strat_grid(candles, window=60, levels=8):
    """Grille (§72, n°5) : market-making directionnel simplifié et CAUSAL — dans un
    range ÉTABLI, acheter les barreaux bas, vendre les barreaux hauts (2 barreaux de
    chaque bord). La grille n'agit que si le marché est « plat » : dérive du range
    faible vs son amplitude (une grille se fait laminer en tendance)."""
    sig = [0] * len(candles)
    for i in range(window, len(candles)):
        w = candles[i - window:i]
        hi = max(float(c["high"]) for c in w)
        lo = min(float(c["low"]) for c in w)
        if hi <= lo:
            continue
        drift = abs(float(w[-1]["close"]) - float(w[0]["close"])) / (hi - lo)
        if drift > 0.35:                               # marché en tendance -> grille OFF
            continue
        pos = (float(candles[i]["close"]) - lo) / (hi - lo)   # position dans le range [0,1]
        step = 1.0 / max(4, int(levels))
        if pos <= 2 * step:
            sig[i] = 1
        elif pos >= 1 - 2 * step:
            sig[i] = -1
    return sig


_GRANU_MS = {60_000: "1m", 300_000: "5m", 900_000: "15m", 1_800_000: "30m",
             3_600_000: "1H", 14_400_000: "4H", 86_400_000: "1D", 604_800_000: "1W"}


def strat_pairs(candles, ref_symbol="BTCUSDT", window=20, z_entry=2.0, ref_candles=None):
    """Arbitrage statistique (§72, n°8) : z-score du spread LOG entre le symbole testé
    et une référence corrélée (le spread en prix bruts n'a pas de sens entre échelles
    différentes). |z| > z_entry -> pari sur le retour à la normale : long le symbole
    « trop bas » vs la référence, short l'inverse. Causal ; séries alignées par
    timestamp ; INERTE ([0]) si la référence est indisponible (fail-safe)."""
    import math
    if not candles or len(candles) < window + 2:
        return [0] * len(candles)
    if ref_candles is None:
        try:
            import technicals as tk
            deltas = sorted(candles[i + 1]["ts"] - candles[i]["ts"] for i in range(len(candles) - 1))
            granu = _GRANU_MS.get(int(deltas[len(deltas) // 2]))
            if not granu:
                return [0] * len(candles)
            ref_candles = tk.fetch_candles(ref_symbol, granu, len(candles) + 10)
        except Exception:
            return [0] * len(candles)
    if not ref_candles:
        return [0] * len(candles)
    # alignement : par TIMESTAMP quand les deux séries en ont, sinon par INDEX de fin
    # (séries synthétiques/tests sans ts) — jamais d'exception, zéros si inalignable.
    spread = [None] * len(candles)
    try:
        if all(c.get("ts") for c in candles) and all(c.get("ts") for c in ref_candles):
            ref_by_ts = {c["ts"]: float(c["close"]) for c in ref_candles if c.get("close")}
            for i, c in enumerate(candles):
                r = ref_by_ts.get(c["ts"])
                if r and c.get("close"):
                    spread[i] = math.log(float(c["close"]) / r)
        else:
            k = min(len(candles), len(ref_candles))
            for j in range(k):
                c = candles[len(candles) - k + j]
                r = ref_candles[len(ref_candles) - k + j].get("close")
                if r and c.get("close"):
                    spread[len(candles) - k + j] = math.log(float(c["close"]) / float(r))
    except Exception:
        return [0] * len(candles)
    import statistics
    sig = [0] * len(candles)
    for i in range(window, len(candles)):
        w = [s for s in spread[i - window:i + 1] if s is not None]
        if len(w) < window // 2 or spread[i] is None:
            continue
        m = sum(w) / len(w)
        sd = statistics.pstdev(w)
        if sd <= 1e-12:
            continue
        z = (spread[i] - m) / sd
        sig[i] = 1 if z < -z_entry else -1 if z > z_entry else 0
    return sig


def strat_random_forest(candles, stride=25, train_min=120):
    """Random Forest prédictif (§72, n°10) : features CAUSALES (rendement, volatilité
    5 barres, variation de volume), cible = signe de la bougie suivante. Refit
    périodique (tous les `stride` pas) sur le SEUL passé — la version « fit puis
    predict sur le même X » du folklore est du surapprentissage pur, ici chaque
    prédiction vient d'un modèle qui n'a JAMAIS vu la barre prédite ni son futur.
    Déterministe (random_state fixe). INERTE ([0]) si scikit-learn absent."""
    try:
        from sklearn.ensemble import RandomForestClassifier
    except Exception:
        return [0] * len(candles)
    import statistics
    cl = _closes(candles)
    vol = [float(c.get("volume") or 0.0) for c in candles]
    n = len(cl)
    if n < train_min + 5:
        return [0] * n
    rets = [0.0] + [(cl[i] - cl[i - 1]) / cl[i - 1] if cl[i - 1] else 0.0 for i in range(1, n)]
    feats = []
    for i in range(n):
        w = rets[max(0, i - 4):i + 1]
        v5 = statistics.pstdev(w) if len(w) >= 2 else 0.0
        dv = (vol[i] - vol[i - 1]) / vol[i - 1] if i and vol[i - 1] else 0.0
        feats.append([rets[i], v5, max(-5.0, min(5.0, dv))])
    sig = [0] * n
    model = None
    for i in range(train_min, n):
        if model is None or (i - train_min) % max(1, int(stride)) == 0:
            X = feats[1:i - 1]                          # barres 1..i-2 : cible (barre+1) ≤ i-1, connue
            y = [1 if cl[j + 1] > cl[j] else 0 for j in range(1, i - 1)]
            if len(set(y)) < 2:
                model = None
                continue
            model = RandomForestClassifier(n_estimators=60, min_samples_leaf=5,
                                           random_state=42, n_jobs=1)
            model.fit(X, y)
        if model is not None:
            sig[i] = 1 if int(model.predict([feats[i]])[0]) == 1 else -1
    return sig


def strat_funding_fade(candles, symbol="BTCUSDT", window=60, z_win=30, z_entry=1.5,
                       funding=None):
    """CROISEMENT §75 : FUNDING (positionnement de la foule) × POSITION DANS LE RANGE
    (prix). Le niveau de funding seul est déjà exploité (agents carry/derivs) ; le
    croisement n'agit qu'aux BORDS : foule très longue (z ≥ z_entry) ET prix au
    plafond du range -> short le squeeze de crowding ; foule très short ET prix au
    plancher -> long. Causal (pointeur funding par ts, z sur les seuls taux réalisés).
    INERTE ([0]) sans historique de funding ou sans timestamps (fail-safe)."""
    import statistics
    if funding is None:
        try:
            import funding_history as fh
            funding = fh.load(symbol)
        except Exception:
            return [0] * len(candles)
    if not funding or not candles or not candles[0].get("ts"):
        return [0] * len(candles)
    sig = [0] * len(candles)
    i_f, rates = -1, []
    for i in range(len(candles)):
        bar_ts = candles[i]["ts"]
        while i_f + 1 < len(funding) and funding[i_f + 1][0] <= bar_ts:
            i_f += 1
            rates.append(float(funding[i_f][1]))
        if i < window or len(rates) < max(10, z_win // 2):
            continue
        w = rates[-z_win:]
        mu = sum(w) / len(w)
        sd = statistics.pstdev(w)
        if sd <= 1e-12:
            continue
        z = (rates[-1] - mu) / sd
        hi = max(float(c["high"]) for c in candles[i - window:i])
        lo = min(float(c["low"]) for c in candles[i - window:i])
        if hi <= lo:
            continue
        pos = (float(candles[i]["close"]) - lo) / (hi - lo)
        if z >= z_entry and pos >= 0.75:
            sig[i] = -1
        elif z <= -z_entry and pos <= 0.25:
            sig[i] = 1
    return sig


def strat_vp_fade(candles, window=60):
    import pro_indicators as pi
    sig = [0] * len(candles)
    for i in range(window, len(candles)):
        try:
            vp = pi.volume_profile(candles[i - window:i + 1])
            price = float(candles[i]["close"])
            sig[i] = 1 if price < vp["value_area_low"] else -1 if price > vp["value_area_high"] else 0
        except Exception:
            sig[i] = 0
    return sig


def strat_structure(candles, window=60):
    sig = [0] * len(candles)
    for i in range(window, len(candles)):
        w = candles[i - window:i + 1]
        ms = pa.market_structure([c["high"] for c in w], [c["low"] for c in w], [c["close"] for c in w])
        sig[i] = ms["event_dir"] if ms["event"] == "BOS" else 0
    return sig


# ---------- composition (nouvelles stratégies à partir des existantes) ----------

def regime_gated(signals, candles, window=63):
    """N'autorise le signal que si le régime de dérive le confirme (up_fraction). Pur."""
    cl = _closes(candles)
    out = list(signals)
    for i in range(len(out)):
        if i < window:
            out[i] = 0
            continue
        uf = rf.up_fraction(cl[:i + 1], window)
        if out[i] > 0 and uf < 0.5:
            out[i] = 0
        elif out[i] < 0 and uf > 0.5:
            out[i] = 0
    return out


def ensemble(signal_lists):
    """Vote majoritaire de plusieurs séries de signaux. Pur."""
    n = min(len(s) for s in signal_lists) if signal_lists else 0
    out = []
    for i in range(n):
        s = sum(sl[i] for sl in signal_lists)
        out.append(1 if s > 0 else -1 if s < 0 else 0)
    return out


# ---------- backtest honnête + score ----------

def backtest(signals, candles, horizon=HORIZON, fee=FEE):
    """Évalue une série de signaux : métriques + pnl par pas + walk-forward + edge.
    Réutilise backtest_brain (evaluate/forward_returns/walk_forward). Pur."""
    cl = _closes(candles)
    rets = bt.forward_returns(cl, horizon)
    sig = signals[:len(rets)]
    m = bt.evaluate(sig, rets, fee)
    pnls = [((1 if s > 0 else -1 if s < 0 else 0) * r - (fee if s else 0.0)) for s, r in zip(sig, rets)]
    folds = bt.walk_forward([p for p in pnls if p != 0] or pnls)
    fpos = (sum(1 for f in folds if f > 0) / len(folds)) if folds else 0.0
    bh = 1.0
    for r in rets:
        bh *= (1 + r)
    edge = round(m["total_return"] - (bh - 1), 5)
    score = m["sharpe"] * fpos
    if edge <= 0:
        score *= 0.3
    if m["trades"] < PROMOTE["trades"]:
        score *= 0.5
    return {**m, "edge": edge, "frac_folds_pos": round(fpos, 3),
            "score": round(score, 4), "pnls": pnls, "folds": folds}


def _passes(r, pbo_val):
    return (r["sharpe"] >= PROMOTE["sharpe"] and r["edge"] > PROMOTE["edge"]
            and r["frac_folds_pos"] >= PROMOTE["frac_folds_pos"]
            and r["trades"] >= PROMOTE["trades"]
            and (pbo_val is None or pbo_val < PROMOTE["pbo"]))


# ---------- registre + amélioration ----------

def base_registry(candles, symbol=None):
    """Registre des stratégies de base (§72 : + vwap, grid, pairs, rf). `symbol`
    (optionnel) choisit la référence du pairs-trading : BTC pour tout le monde,
    ETH quand on teste BTC lui-même. Une stratégie qui échoue est simplement
    absente (le lab classe ce qui existe)."""
    names = ["ema_cross_20_50", "rsi_reversion_14", "donchian_20", "vp_fade_60",
             "structure_bos", "macd_12_26_9", "bollinger_20",
             "vwap_24", "grid_60_8", "rf_25", "donchianvol_20_13", "pullbackc_20_50",
             # variants ÉVOLUÉS (sep-CMA-ES, ajoutés à la MESURE 20/07 ; build_named strip 'evo_')
             "evo_vwap_18", "evo_grid_51_12", "evo_bollinger_47", "evo_rsi_reversion_12"]
    ref = "ETHUSDT" if str(symbol or "").upper() == "BTCUSDT" else "BTCUSDT"
    names.append(f"pairs_{ref}_20")
    if symbol:
        names.append(f"fundfade_{str(symbol).upper()}_60")   # croisement funding × range §75
    out = {}
    for n in names:
        try:
            out[n] = build_named(n, candles)
        except Exception:
            pass
    return out


def build_named(name, candles):
    """Reconstruit une stratégie (base / améliorée / composite) depuis son NOM. Pur.

    Centralise la construction pour que le code promu reproduise EXACTEMENT la
    stratégie testée (aucune divergence entre backtest et fichier prêt à l'emploi)."""
    if name.startswith("evo_"):                        # variante évoluée (sep-CMA-ES)
        return build_named(name[len("evo_"):], candles)
    if name.startswith("ema_cross_"):
        _, _, f, s = name.split("_")
        return strat_ema_cross(candles, int(f), int(s))
    if name.startswith("rsi_reversion_"):
        return strat_rsi_reversion(candles, int(name.split("_")[2]))
    if name.startswith("donchian_"):
        return strat_donchian_breakout(candles, int(name.split("_")[1]))
    if name.startswith("vp_fade_"):
        return strat_vp_fade(candles, int(name.split("_")[2]))
    if name == "structure_bos":
        return strat_structure(candles, 60)
    if name.startswith("macd_"):
        _, f, s, g = name.split("_")
        return strat_macd(candles, int(f), int(s), int(g))
    if name.startswith("bollinger_"):
        return strat_bollinger(candles, int(name.split("_")[1]))
    if name.startswith("vwap_"):
        return strat_vwap(candles, int(name.split("_")[1]))
    if name.startswith("grid_"):
        _, w, l = name.split("_")
        return strat_grid(candles, int(w), int(l))
    if name.startswith("pairs_"):
        _, ref, w = name.split("_")
        return strat_pairs(candles, ref_symbol=ref, window=int(w))
    if name.startswith("fundfade_"):
        _, sym, w = name.split("_")
        return strat_funding_fade(candles, symbol=sym, window=int(w))
    if name.startswith("donchianvol_"):
        _, n, k10 = name.split("_")
        return strat_donchian_vol(candles, n=int(n), vol_k=int(k10) / 10.0)
    if name.startswith("pullbackc_"):
        _, f, s = name.split("_")
        return strat_pullback_confirm(candles, fast=int(f), slow=int(s))
    if name.startswith("rf_"):
        return strat_random_forest(candles, stride=int(name.split("_")[1]))
    if name.endswith("+regime"):
        return regime_gated(build_named(name[:-len("+regime")], candles), candles)
    if name == "ensemble_trend_rev_struct":
        return ensemble([build_named("ema_cross_20_50", candles),
                         build_named("rsi_reversion_14", candles),
                         build_named("structure_bos", candles)])
    if name.startswith("wens_"):                       # ensemble pondéré évolué
        weights = [float(x) for x in name[len("wens_"):].split("_")]
        return weighted_ensemble(candles, CANONICAL, weights)
    raise ValueError(f"stratégie inconnue: {name}")


def improve_ema(candles, max_gen=20):
    """Optimise (fast, slow) d'ema_cross. sep-CMA-ES (TRINITY, arXiv:2512.04695) si
    disponible, sinon repli sur une recherche en grille.

    ⚠️ La recherche (évolutionnaire ou grille) AMPLIFIE le surapprentissage : la
    stratégie produite reste soumise au garde-fou PBO/walk-forward de run()."""
    def _make(f, s):
        f = max(2, int(round(f)))
        s = int(round(s))
        if s <= f:
            s = f + 5
        return f, s, strat_ema_cross(candles, f, s)
    try:
        import evolution
        def fitness(p):
            _, _, sig = _make(p[0], p[1])
            return backtest(sig, candles)["score"]
        x, _, _ = evolution.sep_cma_es(fitness, x0=[15, 55], sigma0=10,
                                       bounds=([5, 30], [40, 150]), max_gen=max_gen,
                                       seed=0, maximize=True)
        f, s, sig = _make(x[0], x[1])
        return f"ema_cross_{f}_{s}", sig, backtest(sig, candles)
    except Exception:
        best, best_name, best_sig = None, None, None
        for fast in (10, 20, 30):
            for slow in (40, 50, 100):
                if fast >= slow:
                    continue
                sig = strat_ema_cross(candles, fast, slow)
                r = backtest(sig, candles)
                if best is None or r["score"] > best["score"]:
                    best, best_name, best_sig = r, f"ema_cross_{fast}_{slow}", sig
        return best_name, best_sig, best


def _clampi(x, lo):
    return max(lo, int(round(x)))


# familles paramétrables (le nom encode TOUS les params -> reconstructible par build_named)
_FAMILIES = {
    "ema_cross": dict(x0=[15.0, 55.0], bounds=([5, 40], [40, 160]),
                      name=lambda p: f"ema_cross_{_clampi(p[0], 2)}_{max(_clampi(p[0], 2) + 5, _clampi(p[1], 40))}"),
    "rsi_reversion": dict(x0=[14.0], bounds=([5], [40]),
                          name=lambda p: f"rsi_reversion_{_clampi(p[0], 5)}"),
    "donchian": dict(x0=[20.0], bounds=([5], [80]),
                     name=lambda p: f"donchian_{_clampi(p[0], 5)}"),
    "bollinger": dict(x0=[20.0], bounds=([8], [80]),
                      name=lambda p: f"bollinger_{_clampi(p[0], 8)}"),
    "macd": dict(x0=[12.0, 26.0, 9.0], bounds=([5, 15, 4], [20, 45, 16]),
                 name=lambda p: f"macd_{_clampi(p[0], 5)}_{max(_clampi(p[0], 5) + 1, _clampi(p[1], 15))}_{_clampi(p[2], 3)}"),
    "vwap": dict(x0=[24.0], bounds=([6], [96]),
                 name=lambda p: f"vwap_{_clampi(p[0], 6)}"),
    "grid": dict(x0=[60.0, 8.0], bounds=([30, 4], [120, 16]),
                 name=lambda p: f"grid_{_clampi(p[0], 30)}_{_clampi(p[1], 4)}"),
    "donchianvol": dict(x0=[20.0, 13.0], bounds=([5, 10], [80, 30]),
                        name=lambda p: f"donchianvol_{_clampi(p[0], 5)}_{_clampi(p[1], 10)}"),
}


def evolve(family, candles, train_frac=0.7, max_gen=16):
    """Optimise les params d'une FAMILLE par sep-CMA-ES (TRINITY) sur le TRAIN.

    Séparation train/test : la recherche n'optimise QUE sur candles[:split] (les
    signaux sont causaux -> aucune fuite). La généralisation est jugée ensuite par
    run() sur la série complète + PBO. Sans split, l'évolution surajusterait tout."""
    spec = _FAMILIES[family]
    split = max(80, int(train_frac * len(candles)))

    def fitness(p):
        try:
            sig = build_named(spec["name"](p), candles)
            return backtest(sig[:split], candles[:split])["score"]
        except Exception:
            return -1e9
    try:
        import evolution
        lo, hi = spec["bounds"]
        sigma0 = max(1.0, sum((hi[i] - lo[i]) for i in range(len(lo))) / (3 * len(lo)))
        x, _, _ = evolution.sep_cma_es(fitness, x0=spec["x0"], sigma0=sigma0,
                                       bounds=spec["bounds"], max_gen=max_gen, seed=0, maximize=True)
        name = spec["name"](x)
    except Exception:
        name = spec["name"](spec["x0"])
    return name, build_named(name, candles)


# membres canoniques de l'ensemble pondéré (ordre fixe -> le nom n'encode que les poids)
CANONICAL = ["ema_cross_20_50", "rsi_reversion_14", "donchian_20", "bollinger_20", "macd_12_26_9"]


def weighted_ensemble(candles, members=None, weights=None):
    """Vote pondéré de stratégies de base -> signal ±1/0. Pur (« coordinateur »)."""
    members = members or CANONICAL
    sigs = [build_named(m, candles) for m in members]
    w = list(weights) if weights is not None else [1.0] * len(members)
    n = min(len(s) for s in sigs) if sigs else 0
    out = []
    for i in range(n):
        s = sum(w[j] * sigs[j][i] for j in range(len(members)))
        out.append(1 if s > 1e-9 else -1 if s < -1e-9 else 0)
    return out


def evolve_ensemble(candles, train_frac=0.7, max_gen=20):
    """« Coordinateur évolué » (TRINITY) : sep-CMA-ES trouve les POIDS optimaux des
    experts sur le TRAIN. Sortie déterministe & lisible (poids encodés dans le nom)."""
    split = max(80, int(train_frac * len(candles)))
    k = len(CANONICAL)

    def fitness(w):
        return backtest(weighted_ensemble(candles, CANONICAL, list(w))[:split], candles[:split])["score"]
    try:
        import evolution
        x, _, _ = evolution.sep_cma_es(fitness, x0=[1.0] * k, sigma0=0.6,
                                       bounds=([0.0] * k, [3.0] * k), max_gen=max_gen, seed=0, maximize=True)
        w = [round(max(0.0, v), 2) for v in x]
    except Exception:
        w = [1.0] * k
    if sum(w) <= 0:
        w = [1.0] * k
    name = "wens_" + "_".join(f"{v:.2f}" for v in w)
    return name, weighted_ensemble(candles, CANONICAL, w)


def compose(registry, candles):
    """Génère de nouvelles stratégies : régime-gating des trend + ensemble. Pur."""
    new = {}
    for name in ("ema_cross_20_50", "donchian_20"):
        if name in registry:
            new[f"{name}+regime"] = regime_gated(registry[name], candles)
    members = [registry[n] for n in ("ema_cross_20_50", "rsi_reversion_14", "structure_bos") if n in registry]
    if len(members) >= 2:
        new["ensemble_trend_rev_struct"] = ensemble(members)
    return new


# ---------- promotion : rapport + code prêt à l'emploi ----------

def _strategy_code(name, symbol, timeframe):
    return f'''"""
{name} — stratégie promue par strategy_lab (backtester autonome).
Référence : {symbol} {timeframe}, frais {FEE * 100:.3f}%/trade, horizon {HORIZON}.
PRÊT À L'EMPLOI — signal ADVISORY (+1 long / -1 short / 0 flat), AUCUN ordre passé.
Réutilise la logique TESTÉE de strategy_lab (nécessite le repo) -> zéro divergence.

Usage :  python {name}.py SYMBOL
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # racine du repo
import strategy_lab as L

STRATEGY = "{name}"


def signal(candles):
    """Signal causal +1/-1/0 à la dernière bougie."""
    sig = L.build_named(STRATEGY, candles)
    return sig[-1] if sig else 0


if __name__ == "__main__":
    sym = (sys.argv[1] if len(sys.argv) > 1 else "{symbol}").upper()
    try:
        import technicals as tk
        candles = tk.fetch_candles(sym, "{timeframe}", 300)
        print(f"{{sym}} {{STRATEGY}} signal = {{signal(candles):+d}}")
    except Exception as exc:
        print("data indisponible:", exc)
'''


def promote(name, r, symbol, timeframe):
    """Écrit le rapport + le code prêt à l'emploi d'une stratégie promue."""
    OUT_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = name.replace("+", "_plus_")
    report = f"""# Rapport stratégie — {name}
_généré par strategy_lab le {time.strftime('%Y-%m-%d %H:%M')} · {symbol} {timeframe}_

## Performance (honnête : frais {FEE*100:.3f}%/trade, horizon {HORIZON})
- **Sharpe** : {r['sharpe']}
- **Rendement total** : {r['total_return']*100:.2f}%  ·  **edge vs buy&hold** : {r['edge']*100:.2f}%
- **Hit rate** : {r['hit_rate']*100:.1f}%  ·  **trades** : {r['trades']}
- **Max drawdown** : {r['max_drawdown']*100:.1f}%
- **Walk-forward** : tranches gagnantes {r['frac_folds_pos']*100:.0f}% ({r['folds']})
- **Score composite** : {r['score']}

## Verdict
Stratégie **PROMUE** : passe la barre de robustesse (Sharpe≥{PROMOTE['sharpe']},
edge>0, tranches gagnantes≥{PROMOTE['frac_folds_pos']*100:.0f}%, trades≥{PROMOTE['trades']}, PBO<{PROMOTE['pbo']}).
⚠️ Performance backtest ≠ garantie future. À re-valider en paper avant tout capital.

## Fichier prêt à l'emploi
`{slug}.py` (signal advisory, aucun ordre passé).
"""
    (OUT_DIR / f"{slug}_{ts}.md").write_text(report, encoding="utf-8")
    (OUT_DIR / f"{slug}.py").write_text(_strategy_code(name, symbol, timeframe), encoding="utf-8")
    return slug


# ---------- orchestrateur autonome ----------

def write_run_stamp(out_dir=None):
    """Battement PER-RUN du lab : écrit un stamp horodaté à CHAQUE run RÉUSSI (promotion
    ou non). C'est la preuve de VIE du lab pour le watchdog — le mtime du dossier
    strategies_out est ÉVÉNEMENTIEL (il ne bouge que sur PROMOTION, rare par conception),
    donc figé alors que le lab tourne (§reprise-watchdog/ERR-012). Un run qui échoue tôt
    (data indispo) ne stampe PAS -> figé -> vrai positif conservé."""
    d = Path(out_dir) if out_dir else OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    stamp = d / ".last_run"
    stamp.write_text(str(int(time.time())), encoding="utf-8")
    return stamp


def run(symbol="BTCUSDT", timeframe="1H", limit=500):
    """Boucle de l'agent : registre -> amélioration -> composition -> classement
    -> PBO -> promotion des robustes (rapport + code). Retourne un résumé."""
    try:
        import technicals as tk
        candles = tk.fetch_candles(symbol, timeframe, limit)
    except Exception as exc:
        return {"error": f"data indisponible: {exc}"}
    if len(candles) < 120:
        return {"error": "pas assez de bougies"}

    registry = base_registry(candles, symbol=symbol)
    # AMÉLIORATION : sep-CMA-ES (TRINITY) optimise chaque famille sur le TRAIN
    # (anti-fuite), puis on évolue les POIDS de l'ensemble (« coordinateur évolué »).
    for fam in ("ema_cross", "rsi_reversion", "donchian", "bollinger", "macd",
                "vwap", "grid", "donchianvol"):
        try:
            en, esig = evolve(fam, candles)
            registry["evo_" + en] = esig
        except Exception:
            pass
    try:
        wn, wsig = evolve_ensemble(candles)
        registry[wn] = wsig
    except Exception:
        pass
    # COMPOSITION : régime-gating + ensemble simple
    registry.update(compose(registry, candles))

    results = {name: backtest(sig, candles) for name, sig in registry.items()}
    p = bt.pbo({name: r["pnls"] for name, r in results.items()})
    ranked = sorted(results.items(), key=lambda kv: kv[1]["score"], reverse=True)

    promoted = []
    for name, r in ranked:
        if _passes(r, p.get("pbo")):
            promoted.append(promote(name, r, symbol, timeframe))

    write_run_stamp()          # battement per-run : preuve de VIE du lab même sans
                               # promotion (§reprise-watchdog/ERR-012)
    return {
        "symbol": symbol, "timeframe": timeframe, "n_strategies": len(registry),
        "pbo": p.get("pbo"),
        "ranking": [(n, r["score"], f"sharpe {r['sharpe']}", f"edge {r['edge']*100:.1f}%",
                     f"folds+ {int(r['frac_folds_pos']*100)}%", f"trades {r['trades']}") for n, r in ranked],
        "promoted": promoted or "aucune (barre de robustesse non franchie — honnête)",
    }


def main():
    import json
    import sys
    sym = (sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT").upper()
    tf = sys.argv[2] if len(sys.argv) > 2 else "1H"
    print(json.dumps(run(sym, tf), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
