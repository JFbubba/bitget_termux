"""
macro_regime.py — affûtage de l'agent MACRO via la méthodo Bitget skill-hub.

Classement : SAFE. Pur / lecture seule, AUCUN ordre. Encode le framework
déterministe « 6 indicateurs macro -> posture monétaire -> biais BTC » des skills
btc-macro-analysis / macro-analyst (seuils de rate-keys.md), SANS embarquer leur
snapshot de données ni dépendre de leur endpoint tiers : on branche nos propres
sources (FRED via macro_data / macro_context). Seul le savoir-faire (les seuils)
est réutilisé.

Convention de signe : posture HAWKISH (inflation haute, marché du travail tendu,
taux réels hauts, dollar fort, VIX élevé) -> BAISSIER pour le BTC ; DOVISH ->
HAUSSIER. Chaque indicateur ne contribue que s'il est disponible (robuste aux trous).
"""


def _cfg(name, fallback):
    try:
        import config
        return getattr(config, name, fallback)
    except Exception:
        return fallback


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


# ---------- pressions par indicateur (pures ; >0 = hawkish = baissier BTC) ----------

def inflation_pressure(core_pce):
    """Core PCE (%, YoY). Seuils skill-hub : <2 dovish, 2-2.5 neutre, >2.5 hawkish, >3 fort."""
    if core_pce is None:
        return None
    c = float(core_pce)
    if c < 2.0:
        return -1.0
    if c <= 2.5:
        return 0.0
    if c <= 3.0:
        return 0.6
    return 1.0


def labor_pressure(unemployment=None, nfp_k=None):
    """Marché du travail. Unemp <4 tendu/hawkish, >5 slack/dovish ; NFP <100k dovish,
    >250k hawkish (NFP en milliers). Moyenne des sous-signaux disponibles."""
    parts = []
    if unemployment is not None:
        u = float(unemployment)
        parts.append(0.6 if u < 4.0 else -0.6 if u > 5.0 else _clamp((4.5 - u) / 0.5 * 0.6))
    if nfp_k is not None:
        n = float(nfp_k)
        parts.append(-0.6 if n < 100 else 0.6 if n > 250 else _clamp((n - 175) / 75 * 0.6))
    if not parts:
        return None
    return _clamp(sum(parts) / len(parts))


def real_rate_pressure(tips_10y):
    """Taux réel 10 ans (TIPS, %). Hauts taux réels = restrictif = baissier BTC.
    >2 hawkish, <1 dovish, linéaire entre."""
    if tips_10y is None:
        return None
    r = float(tips_10y)
    if r >= 2.0:
        return 1.0
    if r <= 1.0:
        return -0.6
    return _clamp((r - 1.5) / 0.5 * 0.8)


def dollar_pressure(dxy_change_pct):
    """Variation du DXY (%, fenêtre). Dollar fort = baissier BTC (lien numéraire)."""
    if dxy_change_pct is None:
        return None
    d = float(dxy_change_pct)
    if d >= 2.0:
        return 0.8
    if d <= -2.0:
        return -0.8
    return _clamp(d / 2.0 * 0.8)


def vix_pressure(vix):
    """VIX. Élevé = risk-off = baissier BTC ; calme = haussier. >25 hawkish, <15 dovish."""
    if vix is None:
        return None
    v = float(vix)
    if v >= 25.0:
        return 0.6
    if v <= 15.0:
        return -0.4
    return _clamp((v - 20.0) / 5.0 * 0.6)


# ---------- agrégation : posture -> biais BTC ----------

_WEIGHTS = {"inflation": 0.30, "labor": 0.20, "real_rate": 0.20, "dollar": 0.20, "vix": 0.10}


def policy_stance(indicators):
    """Posture monétaire pondérée ∈ [-1,1] (>0 hawkish). PUR. indicators = dict avec
    sous-ensemble de : core_pce, unemployment, nfp_k, tips_10y, dxy_change_pct, vix."""
    d = indicators or {}
    p = {"inflation": inflation_pressure(d.get("core_pce")),
         "labor": labor_pressure(d.get("unemployment"), d.get("nfp_k")),
         "real_rate": real_rate_pressure(d.get("tips_10y")),
         "dollar": dollar_pressure(d.get("dxy_change_pct")),
         "vix": vix_pressure(d.get("vix"))}
    num = den = 0.0
    parts = {}
    for k, v in p.items():
        if v is not None:
            num += _WEIGHTS[k] * v
            den += _WEIGHTS[k]
            parts[k] = round(v, 3)
    stance = round(num / den, 3) if den > 0 else 0.0
    return {"stance": stance, "parts": parts, "coverage": round(den, 3)}


def event_surprise(indicator, actual, forecast):
    """Surprise d'annonce -> pression hawkish/dovish. PUR. Pour CPI/PCE/PPI/NFP, un
    'actual' au-dessus du 'forecast' est HAWKISH ; pour unemployment/claims, c'est DOVISH."""
    if actual is None or forecast is None:
        return None
    try:
        a, f = float(actual), float(forecast)
    except (TypeError, ValueError):
        return None
    diff = a - f
    ind = str(indicator).lower()
    inverted = any(k in ind for k in ("unemploy", "claims", "jobless"))
    sign = -1.0 if inverted else 1.0
    scale = max(abs(f) * 0.1, 1e-6)
    return _clamp(sign * diff / scale)


def btc_macro_bias(indicators):
    """Biais MACRO pour le BTC ∈ [-1,1] (>0 haussier). PUR. = -posture (hawkish=baissier).
    Intègre la surprise d'événement si fournie (indicators['event'])."""
    st = policy_stance(indicators)
    bias = -st["stance"]                       # hawkish -> baissier
    ev = (indicators or {}).get("event")
    if ev:
        s = event_surprise(ev.get("indicator"), ev.get("actual"), ev.get("forecast"))
        if s is not None:
            bias = _clamp(0.7 * bias - 0.3 * s)   # surprise hawkish -> baissier
    return {"bias": round(_clamp(bias), 3), "stance": st["stance"],
            "parts": st["parts"], "coverage": st["coverage"]}


# ---------- chargement best-effort depuis NOS sources ----------

def load_indicators():
    """Récupère les 6 indicateurs depuis NOS sources FRED (sans clé, best-effort, ne lève
    jamais). Renvoie un dict partiel ; chaque champ absent est ignoré par le scorer."""
    out = {}
    try:
        import macro_context as mc
        snap = mc.macro_snapshot() or {}
        if snap.get("vix") is not None:
            out["vix"] = snap["vix"]
        if snap.get("dxy_change_pct") is not None:
            out["dxy_change_pct"] = snap["dxy_change_pct"]
        # taux réel 10 ans (TIPS) et chômage : valeur la plus récente
        rr = mc.latest_value(mc._safe_series("DFII10"))
        if rr is not None:
            out["tips_10y"] = rr
        u = mc.latest_value(mc._safe_series("UNRATE"))
        if u is not None:
            out["unemployment"] = u
        # core PCE en glissement annuel (%) à partir de l'indice PCEPILFE
        pce = mc._safe_series("PCEPILFE")
        if pce and len(pce) >= 13 and pce[-13][1]:
            out["core_pce"] = (pce[-1][1] / pce[-13][1] - 1.0) * 100.0
        # NFP : variation mensuelle (milliers) de l'emploi non agricole PAYEMS
        pay = mc._safe_series("PAYEMS")
        if pay and len(pay) >= 2:
            out["nfp_k"] = pay[-1][1] - pay[-2][1]
    except Exception:
        pass
    return out


def vote(symbol="BTCUSDT", indicators=None):
    """Vote compatible cerveau : {vote, confidence, note}. Best-effort.
    Le BTC est l'actif macro de référence -> on applique le biais tel quel."""
    ind = load_indicators() if indicators is None else indicators
    b = btc_macro_bias(ind)
    cov = b["coverage"]
    if cov <= 0:
        return {"vote": 0.0, "confidence": 0.0, "note": "macro indisponible"}
    conf = round(min(1.0, cov) * (0.4 + 0.6 * abs(b["bias"])), 3)
    stance_lbl = "hawkish" if b["stance"] > 0.15 else "dovish" if b["stance"] < -0.15 else "neutre"
    return {"vote": b["bias"], "confidence": conf,
            "note": f"macro {stance_lbl} (posture {b['stance']:+}) · biais BTC {b['bias']:+}",
            "parts": b["parts"]}


def build_report(symbol="BTCUSDT"):
    v = vote(symbol)
    return ("=== AGENT MACRO (framework 6 indicateurs) ===\n"
            f"{v['note']}\n"
            f"Détail : {v.get('parts', {})}\n"
            f"Vote {v['vote']:+} · confiance {v['confidence']}\n"
            "Lecture seule, aucun ordre. VERDICT: SAFE")


def main():
    import sys
    print(build_report(sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"))


if __name__ == "__main__":
    main()
