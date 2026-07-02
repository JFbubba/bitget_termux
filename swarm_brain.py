"""
swarm_brain.py — essaim d'agents analytiques + cerveau (LECTURE SEULE).

Classement : SAFE. Aucun ordre. Le « cerveau » agrège plusieurs AGENTS
spécialisés (chacun lit UNE facette du marché et vote une direction) en un
CONSENSUS (biais LONG/SHORT/NEUTRE + conviction). Il s'ÉDUQUE : il journalise
ses décisions, les juge après coup contre le mouvement réel du prix, et ajuste
la confiance (poids) accordée à chaque agent selon son taux de réussite.

C'est de l'aide à la décision adaptative — pas un oracle ni une machine à gagner.

CLI : python swarm_brain.py [SYMBOL]
"""

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEIGHTS_FILE = ROOT / "brain_weights.json"
LOG_FILE = ROOT / "brain_log.json"
HORIZON_S = int(os.getenv("BRAIN_HORIZON_S", "3600"))  # délai avant de juger une décision

AGENTS = ["orderflow", "technicals", "macro", "sentiment", "derivs", "liquidations", "divergent", "structure", "simons", "savant", "geometric", "flows", "carry"]

# Bornes DURES des poids finaux d'agents (convention historique, cf. update_weights).
# La normalisation post-EARCP dans learn() les court-circuitait -> un agent pouvait
# dériver au-delà (bug observé : divergent ~4.7). On re-borne à la sortie ET à la
# lecture (auto-réparation du fichier obsolète). Surchargeable via config.
BRAIN_WEIGHT_MIN = 0.2
BRAIN_WEIGHT_MAX = 3.0


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def _clamp_weights(weights):
    """Re-borne des poids finaux dans [MIN, MAX]. PUR. Évite qu'un agent domine
    artificiellement le consensus après la normalisation post-EARCP."""
    from config_utils import cfg as _cfg
    lo = _cfg("BRAIN_WEIGHT_MIN", BRAIN_WEIGHT_MIN)
    hi = _cfg("BRAIN_WEIGHT_MAX", BRAIN_WEIGHT_MAX)
    return {k: round(max(lo, min(hi, v)), 3) for k, v in weights.items()}


def _slope(y):
    """Pente OLS de y sur l'index 0..n-1 (tendance locale). Pur."""
    n = len(y)
    if n < 2:
        return 0.0
    mx = (n - 1) / 2.0
    my = sum(y) / n
    num = sum((i - mx) * (y[i] - my) for i in range(n))
    den = sum((i - mx) ** 2 for i in range(n)) or 1e-9
    return num / den


def _lag1_autocorr(x):
    """Autocorrélation lag-1 (Pearson entre x[:-1] et x[1:]). Pur.

    Marqueur de « critical slowing down » : quand elle monte, le système met plus
    de temps à revenir à l'équilibre après un choc -> perte de résilience, signe
    avant-coureur d'une transition de régime (Scheffer 2009)."""
    n = len(x)
    if n < 3:
        return 0.0
    a, b = x[:-1], x[1:]
    ma = sum(a) / len(a)
    mb = sum(b) / len(b)
    num = sum((ai - ma) * (bi - mb) for ai, bi in zip(a, b))
    da = sum((ai - ma) ** 2 for ai in a)
    db = sum((bi - mb) ** 2 for bi in b)
    den = (da * db) ** 0.5
    return num / den if den > 0 else 0.0


# ---------- agents (symbol -> {vote[-1..1], confidence[0..1], note}) ----------

def agent_orderflow(symbol):
    import bitget_market_data as bmd
    import runtime_cache as rc
    s = rc.get(f"book:{symbol}", 10, lambda: bmd.market_snapshot(symbol) or {}, fallback={})
    imb = s.get("book_imbalance") or 0.0
    cvd = s.get("cvd") or 0.0
    vote = _clamp(imb * 2 + (0.3 if cvd > 0 else -0.3 if cvd < 0 else 0))
    return {"vote": vote, "confidence": min(abs(imb) * 1.5, 1.0), "note": f"imbalance {imb:.2f}, CVD {cvd:.2f}"}


def agent_technicals(symbol):
    import technicals as tk
    t = tk.technicals(symbol, "15m")
    ema20, ema50, rsi = t.get("ema20"), t.get("ema50"), t.get("rsi14")
    vb = t.get("volume_bias") or 0
    vote = 0.0
    if ema20 and ema50:
        vote += 0.5 if ema20 > ema50 else -0.5
    if rsi is not None:
        vote += 0.3 if rsi < 35 else -0.3 if rsi > 65 else 0
    vote += _clamp(vb / 10.0) * 0.4
    return {"vote": _clamp(vote), "confidence": 0.6, "note": f"RSI {rsi}, EMA {'+' if (ema20 or 0) > (ema50 or 0) else '-'}, vbias {vb}"}


def _fetch_macro_regime():
    # régime TradFi frais (yfinance) si dispo, sinon FRED (macro_context)
    try:
        import macro_data as md
        reg = md.fetch_regime()
    except Exception:
        reg = None
    if reg is None:
        import macro_context as mc
        reg = (mc.macro_snapshot() or {}).get("regime")
    return reg


def agent_macro(symbol):
    import runtime_cache as rc
    reg = rc.get("macro_regime", 1800, _fetch_macro_regime, fallback=None)  # 30 min
    base = 0.6 if reg == "RISK_ON" else -0.6 if reg == "RISK_OFF" else 0.0
    base_conf = 0.5 if reg in ("RISK_ON", "RISK_OFF") else 0.1
    # Affûtage skill-hub : framework 6 indicateurs (hawkish/dovish -> biais BTC).
    try:
        import macro_regime as mr
        fw = rc.get("macro_framework", 1800, lambda: mr.vote(symbol), fallback=None)
    except Exception:
        fw = None
    if fw and fw.get("confidence", 0) > 0:
        wc = base_conf + fw["confidence"]
        vote = _clamp((base * base_conf + fw["vote"] * fw["confidence"]) / wc) if wc > 0 else base
        return {"vote": round(vote, 3), "confidence": round(min(1.0, wc / 1.5), 3),
                "note": f"régime {reg} + {fw['note']}"}
    return {"vote": base, "confidence": base_conf, "note": f"régime {reg}"}


def agent_sentiment(symbol):
    import sentiment_index as si
    import runtime_cache as rc
    fg = rc.get("fear_greed", 900, lambda: si.fetch_fear_greed() or {}, fallback={})  # 15 min
    v = fg.get("value") if fg else None
    if v is None:
        return {"vote": 0, "confidence": 0, "note": "n/a"}
    vote = _clamp((50 - v) / 50.0)  # contrarian : peur -> achat
    return {"vote": vote, "confidence": min(abs(50 - v) / 50.0, 1.0), "note": f"F&G {v} ({fg.get('classification')})"}


def agent_derivs(symbol):
    import aggregated_derivs as ad
    import runtime_cache as rc
    agg = rc.get(f"derivs:{symbol}", 300, lambda: ad.fetch_aggregate(symbol) or {}, fallback={})  # 5 min
    f = (agg or {}).get("oi_weighted_funding")
    if f is None:
        return {"vote": 0, "confidence": 0, "note": "n/a"}
    vote = _clamp(-f * 2000)  # funding très positif = longs surchargés -> contrarian
    return {"vote": vote, "confidence": min(abs(f) * 2000, 1.0), "note": f"funding {f * 100:.4f}%"}


def agent_liquidations(symbol):
    import liquidations as lq
    import runtime_cache as rc
    d = rc.get(f"liq:{symbol}", 120, lambda: lq.fetch_liquidations(symbol) or {}, fallback={})  # 2 min
    sk = d.get("skew") or {}
    net = sk.get("net")
    if net is None:
        return {"vote": 0, "confidence": 0, "note": "n/a"}
    # net > 0 : pools de shorts au-dessus -> aimant haussier
    vote = _clamp(net)
    return {"vote": vote, "confidence": min(abs(net), 1.0),
            "note": f"aimant {net:+.2f}, longs ~{int(d.get('long_share', 0) * 100)}%"}


def divergent_score(closes):
    """Agent DIVERGENT — un angle neuro-atypique, PAS une simple opposition. Pur.

    Il ne se contente pas de voter contre le consensus : il perçoit ce que les
    agents de tendance ne voient pas encore. Trois facultés, ancrées dans les
    « early-warning signals » de transition de régime (critical slowing down :
    la variance et l'autocorrélation lag-1 montent AVANT le retournement —
    Scheffer Nature 2009 ; rising variability robuste sur les marchés,
    Guttal/Diks, PLOS One 2015) :

      • ANTICIPATION de direction — divergence prix/momentum : le RSI se retourne
        avant le prix (le prix baisse mais le momentum remonte -> rebond anticipé).
      • SENSIBILITÉ aux stimuli faibles — extension relative douce (z-score),
        SANS seuils RSI durs : on « lève les barrières » des paliers fixes pour
        percevoir en relatif et en dynamique.
      • ANTICIPATION d'intensité — instabilité (critical slowing down) mesurée sur
        les rendements BRUTS : quand la résilience chute, l'agent devient PLUS
        convaincu, là où les agents de tendance restent complaisants.

    >0 = retournement haussier anticipé ; <0 = retournement baissier anticipé.
    """
    if len(closes) < 20:
        return 0.0
    import statistics
    raw = list(closes)
    smoothed = raw
    try:
        import indicators
        smoothed = indicators.savitzky_golay(raw, window=11, poly=2)  # débruitage (arXiv:2506.05764)
    except Exception:
        pass

    # --- sensibilité : extension relative, sans seuil dur (mean-reversion douce) ---
    w20 = smoothed[-20:]
    mean = sum(w20) / len(w20)
    sd = statistics.pstdev(w20) or 1e-9
    z = (smoothed[-1] - mean) / sd
    reversion = -_clamp(z / 3.0) * 0.5

    # --- anticipation de direction : divergence prix / momentum (RSI) ---
    divergence = 0.0
    try:
        import indicators
        rsi = indicators.calculate_rsi(smoothed)
        n = min(14, len(rsi))
        if n >= 3:
            ps = _slope(smoothed[-n:])
            rs = _slope(rsi[-n:])
            if ps != 0 and rs != 0 and (ps > 0) != (rs > 0):
                divergence = _clamp(rs / 4.0)   # RSI monte alors que prix baisse -> +
    except Exception:
        pass

    direction = _clamp(divergence + reversion)

    # --- anticipation d'intensité : critical slowing down (rendements BRUTS) ---
    # le débruitage effacerait justement la variance que ce signal cherche.
    instability = 0.0
    rets = [raw[i] - raw[i - 1] for i in range(1, len(raw))]
    if len(rets) >= 20:
        half = len(rets) // 2
        v_recent = statistics.pvariance(rets[-half:]) or 1e-12
        v_base = statistics.pvariance(rets[:half]) or 1e-12
        var_ratio = v_recent / v_base
        d_ac = _lag1_autocorr(rets[-half:]) - _lag1_autocorr(rets[:half])
        # variance pondérée plus fort : preuve empirique plus robuste que l'autocorr
        instability = _clamp(0.5 * (var_ratio - 1.0) + 0.3 * d_ac)

    vote = direction * (1.0 + 0.6 * max(instability, 0.0))
    return _clamp(vote)


def agent_divergent(symbol):
    import technicals as tk
    candles = tk.fetch_candles(symbol, "15m", 60)
    closes = [c["close"] for c in candles]
    if len(closes) < 20:
        return {"vote": 0, "confidence": 0, "note": "n/a"}
    vote = divergent_score(closes)
    # apport ESM (inspiré Han & Keen) : nudge anticipatoire borné ±0.2, best-effort.
    # L'agent divergent EST l'agent d'anticipation -> les signaux de retournement
    # (divergence NED↔prix) et de preneurs informés le renforcent sans le dominer.
    try:
        import esm
        nudge = esm.anticipation_nudge(symbol)
    except Exception:
        nudge = 0.0
    vote = _clamp(vote + nudge)
    note = f"anticipation/divergence {vote:+.2f}" + (f" · ESM {nudge:+.2f}" if nudge else "")
    return {"vote": vote, "confidence": min(abs(vote) * 1.3, 1.0), "note": note}


def agent_structure(symbol):
    """Agent STRUCTURE (SMC + Volume Profile) — issu de l'intake Drive package/PDF.

    Combine la structure de marché (BOS/CHoCH), la position vs Value Area du Volume
    Profile (fade des extrêmes), et une confirmation chandelier (faible). Les
    patterns sont des CONFIRMATEURS, jamais des déclencheurs isolés."""
    import technicals as tk
    import price_action as pa
    candles = tk.fetch_candles(symbol, "15m", 120)
    if len(candles) < 30:
        return {"vote": 0, "confidence": 0, "note": "n/a"}
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    vote = 0.0
    parts = []
    try:
        ms = pa.market_structure(highs, lows, closes)
        # filtre « piège » : un BOS qui ressemble à un faux breakout est escompté
        broken = ms["last_swing_high"] if ms["event_dir"] > 0 else ms["last_swing_low"]
        trap = pa.is_likely_trap(candles, broken, ms["event_dir"]) if ms["event"] == "BOS" else False
        if ms["event"] == "BOS":
            vote += (0.2 if trap else 0.5) * ms["event_dir"]
            parts.append(f"BOS{ms['event_dir']:+d}" + ("(trap?)" if trap else ""))
        elif ms["event"] == "CHoCH":
            vote += 0.4 * ms["event_dir"]; parts.append(f"CHoCH{ms['event_dir']:+d}")
        elif ms["bias"]:
            vote += 0.2 * ms["bias"]; parts.append(ms["trend"])
    except Exception:
        pass
    try:
        import pro_indicators as pi
        vp = pi.volume_profile(candles)
        price = closes[-1]
        if price > vp["value_area_high"]:
            vote -= 0.3; parts.append("aboveVA")
        elif price < vp["value_area_low"]:
            vote += 0.3; parts.append("belowVA")
    except Exception:
        pass
    try:
        pats = pa.candlestick_patterns(candles)
        d = sum(p["dir"] for p in pats)
        if d:
            vote += 0.1 * _clamp(d); parts.append("/".join(p["name"] for p in pats)[:18])
    except Exception:
        pass
    vote = _clamp(vote)
    return {"vote": vote, "confidence": min(abs(vote) * 1.2, 1.0),
            "note": "struct " + (" ".join(parts) if parts else "neutre")}


def agent_simons(symbol):
    """Agent SIMONS (Medallion adapté crypto) — régime caché HMM (Baum-Welch/Viterbi)
    + arbitrage statistique (retour à la moyenne OU), gating par régime. Réverte en
    régime CALME, se retire en STRESS. Déterministe, aucun NN. Voir simons_agent.py."""
    try:
        import simons_agent
        return simons_agent.agent(symbol)
    except Exception:
        return {"vote": 0, "confidence": 0, "note": "n/a"}


def agent_savant(symbol):
    """Agent SAVANT (« autiste digitale ») — perception TENSORIELLE des ruptures de
    symétrie de la microstructure (anomalie de Mahalanobis multivariée), immunisé au
    bruit (FUD/FOMO à contre-courant). Fade les dislocations. Déterministe, aucun NN,
    aucun ordre, aucune évasion. Voir savant_agent.py."""
    try:
        import savant_agent
        return savant_agent.agent(symbol)
    except Exception:
        return {"vote": 0, "confidence": 0, "note": "n/a"}


def agent_geometric(symbol):
    """Agent SAVANT GÉOMÉTRIQUE — analyse géométrique (5 papiers) : régime de QUEUE
    (profil isopérimétrique : blow-up -> suivi de tendance) + TOXICITÉ d'ordre
    supérieur (Eldan-Gross : flux toxique -> retrait). Déterministe, aucun NN, aucun
    ordre. Voir geometric_agent.py."""
    try:
        import geometric_agent
        return geometric_agent.agent(symbol)
    except Exception:
        return {"vote": 0, "confidence": 0, "note": "n/a"}


def agent_flows(symbol):
    """Agent FLOWS — flux de capitaux marché-large : momentum de l'offre totale de
    stablecoins (DefiLlama). Expansion = liquidités entrantes (haussier), contraction
    = repli. Ignore le symbole (comme macro/sentiment) : son edge éventuel est
    TEMPOREL (market-timing, §39), mesuré par le chemin 3 de la validation.
    Déterministe, aucun NN. Voir flows_agent.py."""
    try:
        import flows_agent
        return flows_agent.agent(symbol)
    except Exception:
        return {"vote": 0, "confidence": 0, "note": "n/a"}


def agent_carry(symbol):
    """Agent CARRY — positionnement dérivés contrarian : funding extrême + foule
    long/short (ratio de comptes Bitget) + basis perp-spot. Fade le côté surpeuplé.
    Famille de données ORTHOGONALE à la recherche négative §36-37 (qui n'a balayé
    que des dérivés de bougies). Déterministe, aucun NN. Voir carry_agent.py."""
    try:
        import carry_agent
        return carry_agent.agent(symbol)
    except Exception:
        return {"vote": 0, "confidence": 0, "note": "n/a"}


AGENT_FUNCS = {
    "orderflow": agent_orderflow, "technicals": agent_technicals, "macro": agent_macro,
    "sentiment": agent_sentiment, "derivs": agent_derivs, "liquidations": agent_liquidations,
    "divergent": agent_divergent, "structure": agent_structure, "simons": agent_simons,
    "savant": agent_savant, "geometric": agent_geometric,
    "flows": agent_flows, "carry": agent_carry,
}


# ---------- agrégation + apprentissage (purs, testables) ----------

def aggregate(votes, weights):
    num = den = 0.0
    contrib = []
    for name, v in votes.items():
        w = weights.get(name, 1.0)
        conf = v.get("confidence", 0) or 0
        vote = v.get("vote", 0) or 0
        num += vote * conf * w
        den += conf * w
        contrib.append({"agent": name, "vote": round(vote, 2), "conf": round(conf, 2), "weight": round(w, 2)})
    consensus = (num / den) if den else 0.0
    bias = "LONG" if consensus > 0.2 else "SHORT" if consensus < -0.2 else "NEUTRE"
    return {"consensus": round(consensus, 3), "bias": bias, "conviction": round(abs(consensus), 3), "agents": contrib}


def cognition(votes, weights, consensus):
    """Méta-cognition du cerveau (« conscience » de son propre état). Pur.

    Inspiré d'EARCP (arXiv:2603.14651) : surveille l'entropie des poids et la
    cohérence entre agents, et détecte le « groupthink » (cohérence adverse) —
    quand les agents s'accordent trop fort, l'erreur peut être amplifiée. On en
    déduit un facteur de PRUDENCE qui escompte la conviction.

    Retourne entropy[0..1], agreement[0..1], dispersion, groupthink(bool),
    prudence[0..1] (1 = pleine confiance, <1 = escompter).
    """
    import math
    import statistics
    names = list(votes.keys())
    ws = [max(weights.get(n, 1.0), 1e-9) for n in names]
    tot = sum(ws) or 1.0
    probs = [w / tot for w in ws]
    H = -sum(p * math.log(p) for p in probs if p > 0)
    Hmax = math.log(len(probs)) if len(probs) > 1 else 1.0
    entropy = (H / Hmax) if Hmax > 0 else 1.0
    # accord directionnel parmi les agents qui s'expriment (conf > 0.05)
    voiced = [v.get("vote", 0) or 0 for v in votes.values() if (v.get("confidence", 0) or 0) > 0.05]
    nonzero = [x for x in voiced if x != 0]
    if nonzero and consensus != 0:
        agreement = sum(1 for x in nonzero if (x > 0) == (consensus > 0)) / len(nonzero)
    else:
        agreement = 0.0
    allv = [v.get("vote", 0) or 0 for v in votes.values()]
    dispersion = statistics.pstdev(allv) if len(allv) > 1 else 0.0
    groupthink = agreement >= 0.85 and abs(consensus) >= 0.4
    prudence = 0.8 if groupthink else 1.0
    return {"weight_entropy": round(entropy, 3), "agreement": round(agreement, 3),
            "dispersion": round(dispersion, 3), "groupthink": groupthink,
            "prudence": prudence}


def update_weights(weights, agent_correct):
    """agent_correct = {name: bool|None}. Renforce les bons agents, normalise (moy ~1)."""
    w = dict(weights)
    for name, correct in agent_correct.items():
        if correct is None:
            continue
        w[name] = max(0.2, min(3.0, w.get(name, 1.0) * (1.05 if correct else 0.96)))
    avg = (sum(w.values()) / len(w)) if w else 1.0
    if avg > 0:
        w = {k: round(v / avg, 3) for k, v in w.items()}
    return w


def earcp_weights(perf, coherence, beta=0.7, eta=5.0, w_min=0.05):
    """Pondération EARCP complète (arXiv:2603.14651). Pur.

    Combine PERFORMANCE et COHÉRENCE : chacune normalisée en [0,1], puis
    `s_i = β·P̃_i + (1−β)·C̃_i`, `w_i ∝ exp(η·s_i)`, **plancher** `w_min`
    (= exploration : aucun agent ne meurt), renormalisation (somme = 1).
    β≈0.7 favorise la performance ; η règle la concentration ; regret O(√(T·logM)).
    """
    names = list(perf)
    if not names:
        return {}
    import math

    def _norm(d):
        vals = [float(d.get(n, 0.0)) for n in names]
        lo, hi = min(vals), max(vals)
        rng = (hi - lo) or 1.0
        return {n: (float(d.get(n, 0.0)) - lo) / rng for n in names}

    M = len(names)
    if w_min * M >= 1.0:                         # garde-fou : plancher réalisable
        w_min = 0.5 / M
    P, C = _norm(perf), _norm(coherence)
    s = {n: beta * P[n] + (1.0 - beta) * C[n] for n in names}
    mx = max(s.values())                         # softmax stable numériquement
    ex = {n: math.exp(eta * (s[n] - mx)) for n in names}
    tot = sum(ex.values()) or 1.0
    sm = {n: ex[n] / tot for n in names}
    free = 1.0 - w_min * M                       # plancher garanti + somme = 1
    return {n: round(w_min + free * sm[n], 4) for n in names}


def _apply_edge_priors(weights):
    """Applique les priors ADVISORY de l'échelle d'edge (edge_ladder.weight_priors)
    aux poids EARCP — ils bornent/orientent l'apprentissage, ne l'écrasent pas :
    multiplicateur ADOUCI prior**alpha (alpha≤1), renormalisation à moyenne ~1,
    re-borne [MIN,MAX]. Un agent ABSENT du rapport de validation reste neutre
    (×1.0). Fail-safe NEUTRE : pas de rapport / module en panne -> poids inchangés.
    Débrayable : BRAIN_EDGE_PRIORS=0."""
    from config_utils import cfg as _cfg
    try:
        if not int(_cfg("BRAIN_EDGE_PRIORS", 1)):
            return weights
        import edge_ladder
        priors = edge_ladder.weight_priors()
        alpha = max(0.0, min(1.0, float(_cfg("BRAIN_EDGE_PRIOR_ALPHA", 0.5))))
    except Exception:
        return weights
    if not priors:
        return weights
    w = {k: v * (max(float(priors.get(k, 1.0)), 1e-9) ** alpha) for k, v in weights.items()}
    avg = (sum(w.values()) / len(w)) if w else 1.0
    if avg > 0:
        w = {k: round(v / avg, 3) for k, v in w.items()}
    return _clamp_weights(w)


def _coherence_scores(entries):
    """Cohérence EARCP : fréquence d'accord de chaque agent avec le consensus. Pur."""
    agree, total = {}, {}
    for e in entries:
        cons = e.get("consensus", 0) or 0
        if cons == 0:
            continue
        for name, vote in (e.get("votes") or {}).items():
            if not vote:
                continue
            total[name] = total.get(name, 0) + 1
            if (vote > 0) == (cons > 0):
                agree[name] = agree.get(name, 0) + 1
    return {n: agree.get(n, 0) / total[n] for n in total}


def volatility_regime(closes, short=14, long=100):
    """Coupure de régime de volatilité (CVIX-like). Pur.

    Compare la vol réalisée court terme à sa baseline longue -> ratio, régime, et
    un `scale`[0..1] qui escompte la conviction. VOLONTAIREMENT peu restrictif :
    pleine confiance en régime normal/calme, escompte SEULEMENT en stress/extrême,
    et ne descend jamais sous 0.6 (le risque ne doit pas brider la passation
    d'ordres — il la module). >1 = vol qui monte (instabilité), <1 = vol qui tombe.
    """
    if len(closes) < short + 2:
        return {"ratio": 1.0, "regime": "n/a", "scale": 1.0}
    import statistics
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes)) if closes[i - 1]]
    if len(rets) < short + 1:
        return {"ratio": 1.0, "regime": "n/a", "scale": 1.0}
    v_now = statistics.pstdev(rets[-short:]) or 1e-12
    base = rets[-long:] if len(rets) >= long else rets
    v_base = statistics.pstdev(base) or 1e-12
    ratio = v_now / v_base
    if ratio >= 2.5:
        regime, scale = "extreme", 0.6
    elif ratio >= 1.8:
        regime, scale = "stressed", 0.85
    elif ratio <= 0.5:
        regime, scale = "calm", 1.0
    else:
        regime, scale = "normal", 1.0
    return {"ratio": round(ratio, 3), "regime": regime, "scale": scale}


# ---------- persistance ----------

def load_weights():
    # Tout agent ABSENT du fichier (nouvel agent, ou agent n'ayant jamais voté)
    # retombe sur 1.0 ET est PERSISTÉ au prochain learn() : `update_weights` part de
    # `dict(weights)`, donc fournir tous les AGENTS ici évite la perte silencieuse
    # d'un agent du fichier de poids (auto-réparation : divergent/structure/simons).
    try:
        w = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        w = {}
    if not isinstance(w, dict):
        w = {}
    for a in AGENTS:
        w.setdefault(a, 1.0)
    return _clamp_weights(w)          # auto-répare un fichier obsolète hors bornes dès la lecture


def save_weights(w):
    try:
        WEIGHTS_FILE.write_text(json.dumps(w), encoding="utf-8")
    except Exception:
        pass


def _read_log():
    try:
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_log(log):
    try:
        LOG_FILE.write_text(json.dumps(log[-500:]), encoding="utf-8")
    except Exception:
        pass


def _price(symbol):
    import bitget_market_data as bmd
    return bmd.market_snapshot(symbol).get("mid_price")


def _record(symbol, votes, result, price):
    log = _read_log()
    log.append({
        "ts": int(time.time()), "symbol": symbol, "price": price,
        "votes": {n: round(v.get("vote", 0), 3) for n, v in votes.items()},
        "consensus": result["consensus"], "evaluated": False,
    })
    _write_log(log)


def learn(symbol, price_now, weights):
    """Juge les décisions passées matures de ce symbole et met à jour les poids."""
    if not price_now:
        return weights
    log = _read_log()
    now = int(time.time())
    correctness, changed = {}, False
    for e in log:
        if e.get("evaluated") or e.get("symbol") != symbol or (now - e.get("ts", now)) < HORIZON_S:
            continue
        realized = 1 if price_now > e["price"] else -1 if price_now < e["price"] else 0
        for name, vote in (e.get("votes") or {}).items():
            if vote == 0 or realized == 0:
                continue
            correctness.setdefault(name, []).append((vote > 0) == (realized > 0))
        e["evaluated"] = True
        changed = True
    if correctness:
        agent_correct = {n: (sum(v) / len(v) >= 0.5) for n, v in correctness.items()}
        perf_w = update_weights(weights, agent_correct)         # mémoire de performance (Hedge borné)
        coherence = _coherence_scores(log)                      # accord avec le consensus
        coh = {n: coherence.get(n, 0.5) for n in perf_w}        # neutre (0.5) si pas d'historique
        ew = earcp_weights(perf_w, coh)                         # EARCP : performance + cohérence
        avg = (sum(ew.values()) / len(ew)) if ew else 1.0
        weights = {k: round(v / avg, 3) for k, v in ew.items()}  # remise à moyenne ~1.0 (convention)
        weights = _clamp_weights(weights)                        # re-borne [MIN,MAX] (la norm. court-circuitait le clamp)
        weights = _apply_edge_priors(weights)                    # priors d'edge ADVISORY (edge mesuré borne l'appris)
        save_weights(weights)
    if changed:
        _write_log(log)
    return weights


def gather_votes(symbol):
    votes = {}
    for name in AGENTS:
        try:
            votes[name] = AGENT_FUNCS[name](symbol)
        except Exception as exc:
            votes[name] = {"vote": 0, "confidence": 0, "note": f"err {type(exc).__name__}"}
    return votes


def _attach_cognition(result, votes, weights, closes=None):
    """Ajoute la méta-cognition, le régime de volatilité (CVIX) et une conviction
    escomptée par la prudence × le scale de volatilité (peu restrictif)."""
    cog = cognition(votes, weights, result.get("consensus", 0.0))
    result["cognition"] = cog
    scale = 1.0
    if closes:
        vr = volatility_regime(closes)
        result["volatility"] = vr
        scale = vr["scale"]
    result["adjusted_conviction"] = round(result.get("conviction", 0.0) * cog["prudence"] * scale, 3)
    result["notes"] = {n: v.get("note") for n, v in votes.items()}
    return result


def _series(symbol):
    """Série de clôtures résiliente (Bitget -> CoinGecko, cachée) pour le CVIX."""
    try:
        import market_sources as ms
        return ms.closes(symbol, limit=120) or None
    except Exception:
        return None


def peek(symbol="BTCUSDT"):
    """Lecture instantanée du consensus SANS journaliser ni apprendre.

    Destinée au polling (dashboard) : ne touche ni brain_log.json ni les poids.
    """
    symbol = symbol.upper()
    weights = load_weights()
    votes = gather_votes(symbol)
    result = aggregate(votes, weights)
    result["symbol"] = symbol
    result["weights"] = weights
    return _attach_cognition(result, votes, weights, _series(symbol))


def read(symbol="BTCUSDT", do_learn=True):
    symbol = symbol.upper()
    weights = load_weights()
    votes = gather_votes(symbol)
    result = aggregate(votes, weights)
    result["symbol"] = symbol
    result["weights"] = weights
    try:
        price = _price(symbol)
        if do_learn:
            learn(symbol, price, weights)
        _record(symbol, votes, result, price)
        result["price"] = price
    except Exception:
        pass
    return _attach_cognition(result, votes, weights, _series(symbol))


def build_report(r):
    lines = [
        f"=== CERVEAU (essaim) {r['symbol']} ===",
        f"BIAIS : {r['bias']}  |  consensus {r['consensus']:+.2f}  |  conviction {r['conviction']:.2f}",
        "",
        "Agents (vote · conf · poids appris) :",
    ]
    for a in r["agents"]:
        note = r.get("notes", {}).get(a["agent"], "")
        lines.append(f"- {a['agent']:<11} {a['vote']:+.2f} · {a['conf']:.2f} · w{a['weight']:.2f}  | {note}")
    cog = r.get("cognition")
    if cog:
        lines.append("")
        gt = "  ⚠️ GROUPTHINK (prudence)" if cog.get("groupthink") else ""
        lines.append(f"Cognition : accord {cog['agreement'] * 100:.0f}% · entropie poids "
                     f"{cog['weight_entropy']:.2f} · dispersion {cog['dispersion']:.2f}{gt}")
        vr = r.get("volatility")
        if vr:
            lines.append(f"Volatilité (CVIX) : régime {vr['regime']} · ratio {vr['ratio']} · "
                         f"scale {vr['scale']:.2f}")
        lines.append(f"Conviction ajustée (prudence×vol) : {r.get('adjusted_conviction', r['conviction']):.2f}")
    lines.append("")
    lines.append("Aide à la décision adaptative, LECTURE SEULE. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    import sys
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(read(symbol)))


if __name__ == "__main__":
    main()
