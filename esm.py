"""
esm.py — analyseur INSPIRÉ du « Extended Samuelson Model » (ESM, Han & Keen 2021 ;
Han 2025), adapté crypto. Classement : SAFE (pur côté maths, lecture seule).

⚠️ HONNÊTETÉ : ce n'est PAS le NED original. L'estimateur exact de la Demande
Excédentaire Normalisée (NED = (D−S)/(D+S)) des auteurs repose sur des données
propriétaires non publiées dans l'article. Ici on en construit un **proxy
transparent et observable** à partir de l'OHLCV : le *money-flow* de type Chaikin
(Close-Location-Value pondéré par le volume), borné dans [−1, 1] comme le NED.
On adopte ENSUITE la structure exploitable de l'ESM, qui est l'apport réel :

  • 8 ÉTATS DE MARCHÉ = signe du NED-proxy sur 3 échelles de temps (court/moyen/long).
    État 1 (tout négatif) = creux/le plus pessimiste … État 8 (tout positif) =
    sommet/le plus euphorique  (Table 1 de l'article).
  • 6 SIGNAUX DIRECTIONNELS = divergences NED↔prix (tendance, retournements,
    distribution/accumulation des preneurs informés).
  • COMPATIBILITÉ TEMPORELLE : le fin contient le grossier (multi-timeframe).

Pourquoi c'est utile ici : l'agent « divergent » du cerveau est précisément
l'agent d'ANTICIPATION (signaux subtils, angle différent). Les signaux 3/4
(retournement par divergence) et 5/6 (preneurs informés aux extrêmes) lui donnent
un fondement microstructure causal, sans réseau de neurones.
"""

import math

# ---------- NED-proxy (money-flow borné, observable) ----------

def _row(c):
    """Normalise une bougie (dict OU liste [t,o,h,l,c,v]) -> (h,l,c,v). Pur."""
    if isinstance(c, dict):
        return (float(c["high"]), float(c["low"]), float(c["close"]),
                float(c.get("volume", 0) or 0))
    return (float(c[2]), float(c[3]), float(c[4]), float(c[5]) if len(c) > 5 else 0.0)


def clv(high, low, close):
    """Close-Location-Value ∈ [−1, 1] : où, dans la barre, le prix a clôturé.
    +1 = clôture au plus haut (acheteurs gagnent), −1 = au plus bas. Pur."""
    rng = high - low
    if rng <= 0:
        return 0.0
    return max(-1.0, min(1.0, ((close - low) - (high - close)) / rng))


def ned_proxy(candles):
    """Proxy de Demande Excédentaire Normalisée ∈ [−1, 1] sur la fenêtre fournie :
    money-flow de Chaikin = Σ(CLV·V)/Σ(V). Sans volume -> moyenne des CLV. Pur."""
    rows = [_row(c) for c in candles]
    if not rows:
        return 0.0
    num = den = 0.0
    clvs = []
    for h, l, c, v in rows:
        x = clv(h, l, c)
        clvs.append(x)
        num += x * v
        den += v
    if den > 0:
        return max(-1.0, min(1.0, num / den))
    return sum(clvs) / len(clvs)


def rolling_ned(candles, window=5):
    """Série du NED-proxy (oscillateur) calculé en fenêtre glissante. Pur."""
    rows = list(candles)
    if len(rows) < window:
        return [ned_proxy(rows)] if rows else []
    return [ned_proxy(rows[i - window + 1:i + 1]) for i in range(window - 1, len(rows))]


# ---------- 8 états de marché (Table 1 de l'ESM) ----------

STATE_LABELS = {
    1: "le plus pessimiste (creux)", 2: "pessimiste", 3: "prudent", 4: "neutre-bas",
    5: "neutre-haut", 6: "optimiste", 7: "fort", 8: "le plus euphorique (sommet)",
}


def market_state(ned_short, ned_medium, ned_long):
    """État de marché 1..8 = combinaison des SIGNES du NED sur 3 échelles. Pur.

    Encodage fidèle à la Table 1 : state = 1 + (court>0) + 2·(moyen>0) + 4·(long>0).
    État 1 = tout négatif (creux) ; État 8 = tout positif (sommet)."""
    return 1 + (1 if ned_short > 0 else 0) + (2 if ned_medium > 0 else 0) \
             + (4 if ned_long > 0 else 0)


# ---------- 6 signaux directionnels (divergences NED↔prix) ----------

def _extrema(s, w=2):
    """Indices des maxima/minima locaux (fenêtre ±w). Pur."""
    peaks, troughs = [], []
    for i in range(w, len(s) - w):
        seg = s[i - w:i + w + 1]
        if s[i] == max(seg) and s[i] > min(seg):
            peaks.append(i)
        if s[i] == min(seg) and s[i] < max(seg):
            troughs.append(i)
    return peaks, troughs


# bias directionnel par signal : 1,3,6 haussiers ; 2,4,5 baissiers
SIGNAL_NAMES = {
    0: ("aucun", 0), 1: ("tendance haussière", 1), 2: ("tendance baissière", -1),
    3: ("retournement haussier (divergence)", 1), 4: ("retournement baissier (divergence)", -1),
    5: ("vente preneurs informés (distribution)", -1), 6: ("achat preneurs informés (accumulation)", 1),
}


def directional_signal(ned, price, w=2):
    """Classe le signal directionnel ESM (1..6, ou 0=aucun) depuis les séries
    NED et prix ALIGNÉES. PUR. Priorité aux retournements (3/4) puis tendance
    (1/2) puis preneurs informés (5/6). Retourne (numéro, nom, bias∈{-1,0,1})."""
    n = min(len(ned), len(price))
    if n < 2 * w + 3:
        return (0,) + SIGNAL_NAMES[0]
    ned, price = ned[-n:], price[-n:]
    pk, tr = _extrema(price, w)

    def last_two(idxs):
        return (idxs[-2], idxs[-1]) if len(idxs) >= 2 else None

    sig = 0
    pp, tt = last_two(pk), last_two(tr)
    # retournements par divergence (les plus précieux, anticipatoires)
    if tt:  # deux derniers creux de prix
        a, b = tt
        if price[b] > price[a] and ned[b] <= ned[a]:
            sig = 3  # prix higher-low mais NED lower-low -> reverse to uptrend
    if sig == 0 and pp:  # deux derniers sommets de prix
        a, b = pp
        if price[b] < price[a] and ned[b] >= ned[a]:
            sig = 4  # prix lower-high mais NED higher-high -> reverse to downtrend
    # tendance
    if sig == 0 and pp:
        a, b = pp
        if price[b] > price[a] and ned[b] > ned[a]:
            sig = 1
        elif price[b] < price[a] and ned[b] < ned[a]:
            sig = 2
    # preneurs informés aux extrêmes (NED qui roule à un extrême de prix)
    if sig == 0 and pk and pk[-1] >= n - (w + 2):       # sommet de prix très récent
        if ned[-1] < ned[pk[-1]]:
            sig = 5
    if sig == 0 and tr and tr[-1] >= n - (w + 2):       # creux de prix très récent
        if ned[-1] > ned[tr[-1]]:
            sig = 6
    name, bias = SIGNAL_NAMES[sig]
    return (sig, name, bias)


# ---------- analyse multi-timeframe résiliente ----------

# court / moyen / long (intraday crypto) — « le fin contient le grossier »
TIMEFRAMES = ("5m", "15m", "1h")


def _candles(symbol, tf, limit):
    """Bougies résilientes (market_sources -> technicals), best-effort. Ne lève jamais."""
    try:
        import market_sources as ms
        cs = ms.candles(symbol, tf, limit)
        if cs and len(cs) >= 20:
            return cs
    except Exception:
        pass
    try:
        import technicals as tk
        return tk.fetch_candles(symbol, tf, limit)
    except Exception:
        return []


def analyze(symbol="BTCUSDT", ttl=45):
    """Analyse ESM live multi-timeframe : NED par échelle, état 1..8, signal
    directionnel (sur l'échelle courte). Cachée, best-effort, ne lève jamais."""
    import runtime_cache as rc

    def fetch():
        neds = {}
        short_series = None
        for tf in TIMEFRAMES:
            cs = _candles(symbol, tf, 60)
            neds[tf] = ned_proxy(cs[-20:]) if cs else 0.0
            if tf == TIMEFRAMES[0] and cs:
                short_series = cs
        st = market_state(neds[TIMEFRAMES[0]], neds[TIMEFRAMES[1]], neds[TIMEFRAMES[2]])
        sig_no, sig_name, bias = 0, "aucun", 0
        if short_series and len(short_series) >= 20:
            ned_ser = rolling_ned(short_series, window=5)
            price = [_row(c)[2] for c in short_series][-len(ned_ser):]
            sig_no, sig_name, bias = directional_signal(ned_ser, price)
        return {
            "state": st, "state_label": STATE_LABELS.get(st, "?"),
            "ned": {k: round(v, 3) for k, v in neds.items()},
            "signal": sig_no, "signal_name": sig_name, "signal_bias": bias,
            "timeframes": list(TIMEFRAMES),
        }
    return rc.get(f"esm:{symbol.upper()}", ttl, fetch,
                  fallback={"state": None, "signal": 0, "signal_bias": 0, "ned": {}})


def anticipation_nudge(symbol="BTCUSDT"):
    """Petit biais ANTICIPATOIRE borné ∈ [−0.2, 0.2] pour l'agent divergent :
    issu des signaux de retournement/preneurs informés de l'ESM. Best-effort -> 0."""
    try:
        a = analyze(symbol)
        bias = a.get("signal_bias", 0) or 0
        # retournements (3/4) et distribution/accumulation (5/6) = anticipation forte
        strong = a.get("signal") in (3, 4, 5, 6)
        return max(-0.2, min(0.2, bias * (0.2 if strong else 0.1)))
    except Exception:
        return 0.0


def build_report(a):
    """Rapport texte de l'analyse ESM. Pur."""
    return ("=== ESM (inspiré) ===\n"
            f"État {a.get('state', '?')} — {a.get('state_label', '?')}\n"
            f"NED par échelle : {a.get('ned', {})}\n"
            f"Signal : {a.get('signal', 0)} — {a.get('signal_name', 'aucun')} "
            f"(bias {a.get('signal_bias', 0):+d})\n"
            "Proxy NED (money-flow), LECTURE SEULE. Aucun ordre. VERDICT: SAFE")


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(analyze(sym)))


if __name__ == "__main__":
    main()
