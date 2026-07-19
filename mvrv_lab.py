"""mvrv_lab.py — banc de MESURE du signal on-chain MVRV Z-score (backtest, LECTURE SEULE).

Classement : SAFE. Aucun ordre, aucun réseau de trading, aucun secret. Sorties =
console + un JSON de résultats (.mvrv_lab_result.json, gitignoré). DÉFAUT OFF : ce
module n'a AUCUN chemin d'exécution ni AUCUN câblage au cerveau — il rejoue le
MVRV-Z sur l'historique et rapporte des chiffres. Un éventuel tilt DCA réel resterait
un opt-in `.env` (MVRV_TILT_ENABLED, défaut OFF) à décider par le propriétaire — il
n'est PAS branché ici (ce serait, au plus tard, un facteur ×m sur `accumulation_engine`
SOUS les caps, jamais un signal directionnel futures).

Pourquoi un banc À PART (comme grid_lab / vpin_lab / mm_lab) : le strategy_lab (§68)
juge des signaux DIRECTIONNELS intraday sur bougies ; le MVRV-Z est un signal de CYCLE
LENT, on-chain, DAILY-NATIF (valorisation vs coût de base réalisé du réseau). Il ne se
mesure pas au setup intraday mais sur des ANNÉES / des cycles.

DONNÉES — Coin Metrics community, KEYLESS (vérifié 19/07), GET public stdlib :
  https://community-api.coinmetrics.io/v4/timeseries/asset-metrics
  metrics = CapMVRVCur (ratio MVRV), CapMrktCurUSD (market cap), PriceUSD (prix BTC).
  CapRealUSD est PRO (403 Forbidden) -> realized_cap DÉRIVÉ = market_cap / MVRV
  (car CapMVRVCur = market_cap / realized_cap, par définition Coin Metrics).
  PriceUSD (community-free) donne le prix BTC réel depuis 2013 -> historique COMPLET
  (~4 cycles), ce qui est indispensable pour un signal de cycle. Cross-check avec
  candles_history.load('BTCUSDT','1D') (prix Bitget) sur la fenêtre commune.

MVRV Z-score = (market_cap − realized_cap) / std(market_cap) :
  • mode 'full'      : std sur TOUT l'échantillon (définition on-chain classique ;
    léger look-ahead d'ÉCHELLE — non causal ; cross-check seulement).
  • mode 'expanding' : std cumulée jusqu'à t (CAUSALE, tradable, SANS look-ahead) —
    c'est la version HONNÊTE pour l'IC et pour le tilt DCA.

ERR-001 (échelle de timeframes) : le MVRV est calculé UNE fois par jour sur l'état de
la chaîne (UTXO/coût réalisé) — il n'existe PAS de MVRV M1..H4 (natif indisponible,
comme la tape M1 pour VPIN). L'échelle pertinente d'un signal de cycle lent = les
HORIZONS forward EN JOURS, de ~D1 (1-7 j) à > W1 (30-90 j). On les balaie tous.

HONNÊTETÉ (prior imposé) : N ≈ 3-4 cycles seulement -> tout « edge » MVRV est d'abord
un BETA DE CYCLE. On déflate AGRESSIVEMENT (Deflated Sharpe, n_trials = h × modes),
walk-forward, benchmark buy-and-hold, et on dit clairement si l'IC survit ou non.

CLI (CONSULTATION, lecture seule) :
    python mvrv_lab.py --status     # dernier résultat mesuré (aucun réseau)
    python mvrv_lab.py --run        # fetch (ou cache) + mesure complète
    python mvrv_lab.py --run --no-net   # force le cache disque (offline)
"""
import json
import math
import time
import urllib.request
import urllib.error
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
CACHE = _ROOT / ".mvrv_lab_cache.json"
RESULT = _ROOT / ".mvrv_lab_result.json"

CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
CM_METRICS = "CapMVRVCur,CapMrktCurUSD,PriceUSD"
CM_START = "2013-01-01"

# Horizons forward en JOURS. Tête (demande) = {7,14,30} ; l'échelle ÉTENDUE couvre le
# spectre d'un signal lent (ERR-001 adapté : jours, pas M1..H4 qui n'existent pas ici).
HORIZONS = [7, 14, 30]
HORIZONS_EXT = [1, 7, 14, 30, 60, 90]
MODES = ["expanding", "full"]

# Budget DCA de référence (USD/jour) — la comparaison flat vs tilt est INVARIANTE
# d'échelle (on compare des coûts moyens à budget total ÉGAL), la valeur importe peu.
DCA_BASE_USD = 10.0
# Le tilt normalise sa moyenne à 1 -> même budget total que le DCA plat : on mesure
# la QUALITÉ du timing, pas « dépenser plus ».
TILT_ALPHA = 0.5
TILT_LO, TILT_HI = 0.25, 2.5
# En dessous de min_window points, la std cumulée (expanding) est instable -> z = None.
MIN_WINDOW = 365


# ======================================================================
# FONCTIONS PURES (stdlib seul, hermétiques, testables sans réseau)
# ======================================================================

def realized_cap(market_cap, mvrv):
    """Realized cap DÉRIVÉ : realized = market_cap / MVRV (CapRealUSD est Pro).
    CapMVRVCur = market_cap / realized_cap par définition Coin Metrics. PUR.
    Retourne None si entrée invalide (fail-safe)."""
    try:
        mc, mv = float(market_cap), float(mvrv)
    except (TypeError, ValueError):
        return None
    if mv <= 0 or mc <= 0:
        return None
    return mc / mv


def _std(xs, ddof=0):
    """Écart-type d'une liste (pur, stdlib). 0.0 si < 2 points."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    d = n - ddof if n - ddof > 0 else n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / d)


def mvrv_zscores(market_caps, mvrvs, mode="expanding", min_window=MIN_WINDOW):
    """MVRV Z-score par date = (market_cap − realized_cap) / std(market_cap). PUR.

    numérateur = market_cap − market_cap/MVRV = market_cap · (1 − 1/MVRV).
    - mode 'expanding' : std cumulée jusqu'à t (CAUSAL) ; None tant que t < min_window.
    - mode 'full'      : std sur tout l'échantillon (classique, non causal).
    Retourne une liste de z (même longueur que les entrées ; None quand indéfini)."""
    n = min(len(market_caps), len(mvrvs))
    caps = [None] * n
    num = [None] * n                      # numérateur (market_cap − realized_cap)
    for i in range(n):
        rc = realized_cap(market_caps[i], mvrvs[i])
        if rc is None:
            continue
        try:
            mc = float(market_caps[i])
        except (TypeError, ValueError):
            continue
        caps[i] = mc
        num[i] = mc - rc
    if mode == "full":
        valid = [c for c in caps if c is not None]
        sd = _std(valid)
        return [None if (num[i] is None or sd <= 0) else num[i] / sd for i in range(n)]
    # expanding (causal)
    out = [None] * n
    seen = []
    for i in range(n):
        if caps[i] is not None:
            seen.append(caps[i])
        if num[i] is None or len(seen) < max(2, min_window):
            continue
        sd = _std(seen)
        if sd > 0:
            out[i] = num[i] / sd
    return out


def forward_returns(prices, h):
    """Rendement forward (chevauchant) close[t+h]/close[t]−1. PUR.
    Retourne (idx, fwd) alignés sur t ∈ [0, len−h)."""
    h = max(1, int(h))
    idx, fwd = [], []
    for t in range(0, len(prices) - h):
        p0, p1 = prices[t], prices[t + h]
        if p0 and p1 and p0 > 0 and p1 > 0:
            idx.append(t)
            fwd.append(p1 / p0 - 1.0)
    return idx, fwd


def _rankdata(a):
    """Rangs moyens (ties = moyenne). Pur, stdlib."""
    order = sorted(range(len(a)), key=lambda i: a[i])
    ranks = [0.0] * len(a)
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_ic(pred, fwd):
    """Rank IC de Spearman ∈ [−1,1] (pur, stdlib — hermétique, sans numpy). 0.0 si n<3."""
    n = min(len(pred), len(fwd))
    if n < 3:
        return 0.0
    ra, rb = _rankdata(list(pred[:n])), _rankdata(list(fwd[:n]))
    ma, mb = sum(ra) / n, sum(rb) / n
    ra = [x - ma for x in ra]
    rb = [x - mb for x in rb]
    num = sum(a * b for a, b in zip(ra, rb))
    den = math.sqrt(sum(a * a for a in ra) * sum(b * b for b in rb))
    return num / den if den > 0 else 0.0


def ic_tstat(ic, n):
    """t-stat de l'IC (pur). n = nb d'échantillons INDÉPENDANTS (non chevauchants)."""
    if n < 3 or abs(ic) >= 1:
        return 0.0
    return ic * math.sqrt((n - 2) / (1 - ic ** 2))


def tilt_multipliers(zs, alpha=TILT_ALPHA, lo=TILT_LO, hi=TILT_HI):
    """Multiplicateur d'achat DCA ∝ z BAS (acheter plus quand MVRV-Z bas). PUR.

    m_raw = clamp(1 − alpha·z, lo, hi) — monotone décroissant en z (z haut/cher -> peu ;
    z bas/bon marché -> plus). Puis NORMALISÉ pour que la moyenne des multiplicateurs
    ACTIFS = 1 -> budget total IDENTIQUE au DCA plat : la comparaison de coût moyen est
    équitable (qualité de timing, PAS « dépenser plus »). z=None -> multiplicateur None
    (jour ignoré côté tilt, fail-safe)."""
    raw = []
    for z in zs:
        if z is None:
            raw.append(None)
        else:
            raw.append(max(lo, min(hi, 1.0 - alpha * float(z))))
    active = [r for r in raw if r is not None]
    mean = sum(active) / len(active) if active else 1.0
    if mean <= 0:
        return raw
    return [None if r is None else r / mean for r in raw]


def simulate_dca(prices, mults, base=DCA_BASE_USD):
    """DCA événementiel : à chaque date on dépense base·mult USD au prix du jour. PUR.
    Retourne {cost_basis (VWAP = dépensé/BTC), btc, spent, n_buys}. mult None -> jour
    sauté (permet de comparer flat vs tilt sur EXACTEMENT les mêmes dates actives)."""
    spent = 0.0
    btc = 0.0
    nb = 0
    for p, m in zip(prices, mults):
        if m is None or not p or p <= 0:
            continue
        s = base * float(m)
        spent += s
        btc += s / p
        nb += 1
    cost = spent / btc if btc > 0 else 0.0
    return {"cost_basis": cost, "btc": btc, "spent": spent, "n_buys": nb}


# ======================================================================
# I/O (réseau + disque) — SÉPARÉ des fonctions pures, tout FAIL-SAFE
# ======================================================================

def _http_get_json(url, timeout=25):
    """GET public -> JSON, ou None (fail-safe, jamais d'exception propagée)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mvrv-lab/1.0 (read-only)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def fetch_coinmetrics(start=CM_START, use_net=True, max_pages=60):
    """Série on-chain BTC quotidienne [{date, mvrv, mktcap, price}] triée par date.

    Fail-safe : réseau KO -> repli sur le cache disque ; cache absent -> None (jamais
    de crash). Cache le JSON consolidé pour re-run offline. LECTURE SEULE."""
    rows = []
    if use_net:
        url = (f"{CM_URL}?assets=btc&metrics={CM_METRICS}&frequency=1d"
               f"&start_time={start}&page_size=10000")
        pages = 0
        while url and pages < max_pages:
            d = _http_get_json(url)
            pages += 1
            if not d or "data" not in d:
                break
            for e in d["data"]:
                try:
                    date = str(e["time"])[:10]
                    mv = e.get("CapMVRVCur")
                    mc = e.get("CapMrktCurUSD")
                    pr = e.get("PriceUSD")
                    if mv is None or mc is None or pr is None:
                        continue
                    rows.append({"date": date, "mvrv": float(mv),
                                 "mktcap": float(mc), "price": float(pr)})
                except (KeyError, TypeError, ValueError):
                    continue
            url = d.get("next_page_url")
            time.sleep(0.1)
    if rows:
        rows.sort(key=lambda r: r["date"])
        try:
            CACHE.write_text(json.dumps(rows), encoding="utf-8")   # cache pour offline
        except Exception:
            pass
        return rows
    # repli cache disque
    try:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if isinstance(cached, list) and cached:
            cached.sort(key=lambda r: r["date"])
            return cached
    except Exception:
        pass
    return None


def bitget_daily_prices():
    """{date -> close} depuis candles_history.load('BTCUSDT','1D') (prix Bitget).
    Best-effort, {} si indisponible. Pour le CROSS-CHECK du prix (pas la mesure primaire)."""
    try:
        import candles_history as ch
        import datetime
        utc = datetime.timezone.utc
        out = {}
        for row in ch.load("BTCUSDT", "1D"):
            try:
                d = datetime.datetime.fromtimestamp(row[0] / 1000, utc).date().isoformat()
                out[d] = float(row[4])
            except (IndexError, TypeError, ValueError):
                continue
        return out
    except Exception:
        return {}


# ======================================================================
# MESURE
# ======================================================================

def _price_crosscheck(rows):
    """Corrélation (rang) PriceUSD (Coin Metrics) vs close Bitget sur la fenêtre commune.
    Confirme que le prix on-chain suit le prix tradable. Retourne dict ou None."""
    bg = bitget_daily_prices()
    if not bg:
        return None
    pa, pb = [], []
    for r in rows:
        c = bg.get(r["date"])
        if c and c > 0 and r["price"] > 0:
            pa.append(r["price"])
            pb.append(c)
    if len(pa) < 30:
        return None
    return {"n_overlap": len(pa), "spearman": round(spearman_ic(pa, pb), 4),
            "first": rows and next((r["date"] for r in rows if bg.get(r["date"])), None)}


def _ic_row(zs, prices, h):
    """IC (Spearman) du z-score BRUT vs rendement forward h, avec t-stat sur n
    INDÉPENDANT (≈ usable/h, l'overlapping gonfle sinon). Le z BRUT devrait avoir un IC
    NÉGATIF (MVRV haut = surévalué -> rendement futur bas = réversion de valeur)."""
    idx, fwd = forward_returns(prices, h)
    pred, ret = [], []
    for k, t in enumerate(idx):
        if t < len(zs) and zs[t] is not None:
            pred.append(zs[t])
            ret.append(fwd[k])
    n = len(pred)
    if n < 10:
        return {"h": h, "n": n, "ic": None, "ic_buy": None, "t_indep": None, "n_indep": n}
    ic = spearman_ic(pred, ret)
    n_indep = max(3, n // h)
    return {"h": h, "n": n, "ic": round(ic, 4), "ic_buy": round(-ic, 4),
            "t_indep": round(ic_tstat(ic, n_indep), 2), "n_indep": n_indep}


def _nonoverlap_strat(zs, prices, h):
    """Série de rendements NON CHEVAUCHANTS de la stratégie sign(−z)·fwd (acheter
    quand z bas) au pas h, et le B&H apparié (toujours long = fwd). Pour Sharpe/DSR."""
    strat, bench = [], []
    t = 0
    N = len(prices)
    while t + h < N:
        z = zs[t] if t < len(zs) else None
        p0, p1 = prices[t], prices[t + h]
        if z is not None and p0 and p1 and p0 > 0 and p1 > 0:
            r = p1 / p0 - 1.0
            side = -1.0 if z > 0 else 1.0        # z haut (cher) -> short ; z bas -> long
            strat.append(side * r)
            bench.append(r)
        t += h
    return strat, bench


def _sharpe(xs):
    if len(xs) < 2:
        return 0.0
    sd = _std(xs, ddof=1)
    return (sum(xs) / len(xs)) / sd if sd > 1e-12 else 0.0


def _skew_kurt(xs):
    n = len(xs)
    if n < 3:
        return 0.0, 3.0
    m = sum(xs) / n
    sd = _std(xs)
    if sd <= 1e-12:
        return 0.0, 3.0
    z = [(x - m) / sd for x in xs]
    return (sum(v ** 3 for v in z) / n, sum(v ** 4 for v in z) / n)


def run(use_net=True, verbose=True):
    """Mesure complète MVRV-Z. Écrit RESULT, retourne le dict. FAIL-SAFE : données
    indispo -> verdict 'no_data', jamais de crash."""
    rows = fetch_coinmetrics(use_net=use_net)
    if not rows or len(rows) < 400:
        out = {"status": "no_data", "ts": int(time.time()),
               "note": "Coin Metrics community indisponible et pas de cache — verdict non rendu."}
        _save(out)
        if verbose:
            print("MVRV-Z : donnees INDISPONIBLES (reseau KO + pas de cache). "
                  "Aucune mesure. Lecture seule, aucun ordre. VERDICT: SAFE")
        return out

    prices = [r["price"] for r in rows]
    mktcaps = [r["mktcap"] for r in rows]
    mvrvs = [r["mvrv"] for r in rows]
    span = {"start": rows[0]["date"], "end": rows[-1]["date"], "n_days": len(rows)}

    z_by_mode = {m: mvrv_zscores(mktcaps, mvrvs, mode=m) for m in MODES}

    # --- Mesure A : IC par mode × horizon (tête {7,14,30} + échelle étendue) ---
    ic = {}
    for m in MODES:
        ic[m] = {"head": [_ic_row(z_by_mode[m], prices, h) for h in HORIZONS],
                 "ext": [_ic_row(z_by_mode[m], prices, h) for h in HORIZONS_EXT]}

    # --- Mesure B : tilt DCA vs DCA plat (z CAUSAL expanding, budget égal) ---
    z_causal = z_by_mode["expanding"]
    mult_tilt = tilt_multipliers(z_causal)
    # DCA plat sur EXACTEMENT les mêmes dates actives (mult=1 là où le tilt est défini).
    mult_flat = [None if t is None else 1.0 for t in mult_tilt]
    dca_flat = simulate_dca(prices, mult_flat)
    dca_tilt = simulate_dca(prices, mult_tilt)
    cb_f, cb_t = dca_flat["cost_basis"], dca_tilt["cost_basis"]
    improve_pct = 100.0 * (cb_f - cb_t) / cb_f if cb_f > 0 else 0.0
    btc_uplift_pct = 100.0 * (dca_tilt["btc"] - dca_flat["btc"]) / dca_flat["btc"] if dca_flat["btc"] > 0 else 0.0
    # Benchmark achat unique (lump-sum) au 1er jour actif = borne « tout de suite ».
    first_active = next((prices[i] for i, mm in enumerate(mult_tilt) if mm is not None and prices[i] > 0), None)
    dca = {"cost_basis_flat": round(cb_f, 2), "cost_basis_tilt": round(cb_t, 2),
           "improve_pct": round(improve_pct, 3), "btc_uplift_pct": round(btc_uplift_pct, 3),
           "n_buys": dca_flat["n_buys"], "lump_sum_price_first": round(first_active, 2) if first_active else None,
           "final_price": round(prices[-1], 2)}

    # --- Mesure C : Sharpe / Deflated Sharpe / walk-forward / B&H ---
    n_trials = len(HORIZONS) * len(MODES)          # essais du balayage (déflation)
    trial_sr = []
    dsr_rows = []
    for m in MODES:
        for h in HORIZONS:
            strat, bench = _nonoverlap_strat(z_by_mode[m], prices, h)
            sr = _sharpe(strat)
            trial_sr.append(sr)
            dsr_rows.append({"mode": m, "h": h, "n": len(strat), "sharpe": round(sr, 4),
                             "bh_sharpe": round(_sharpe(bench), 4)})
    var_sr = _std(trial_sr) ** 2 if len(trial_sr) > 1 else 0.0
    # Config tête pour la déflation : expanding, h=30 (le plus lent, le moins overlappé).
    strat30, bench30 = _nonoverlap_strat(z_causal, prices, 30)
    sr30 = _sharpe(strat30)
    sk, ku = _skew_kurt(strat30)
    try:
        import agent_validation as av
        dsr = av.deflated_sharpe(sr30, len(strat30), sk, ku, n_trials, var_sr)
        emax = av.expected_max_sharpe(n_trials, var_sr)
    except Exception:
        dsr, emax = None, None
    # Walk-forward : moitié 1 (train) choisit l'orientation par IC ; moitié 2 (test) mesure.
    wf = _walk_forward(z_causal, prices, 30)
    bh_total = round(100.0 * (prices[-1] / prices[0] - 1.0), 1)

    valid = {"n_trials": n_trials, "var_sr": round(var_sr, 6),
             "headline": {"mode": "expanding", "h": 30, "n": len(strat30),
                          "sharpe": round(sr30, 4), "bh_sharpe": round(_sharpe(bench30), 4),
                          "skew": round(sk, 3), "kurt": round(ku, 3),
                          "deflated_sharpe": round(dsr, 4) if dsr is not None else None,
                          "expected_max_sharpe_H0": round(emax, 4) if emax is not None else None},
             "trials": dsr_rows, "walk_forward": wf,
             "buy_hold_total_return_pct": bh_total}

    out = {"status": "ok", "ts": int(time.time()), "span": span,
           "price_crosscheck_bitget": _price_crosscheck(rows),
           "ic": ic, "dca_tilt": dca, "validation": valid,
           "verdict": _verdict(ic, dca, valid)}
    _save(out)
    if verbose:
        _print(out)
    return out


def _walk_forward(zs, prices, h):
    """Split 50/50 temporel. Train : signe de l'IC (orientation du signal). Test :
    IC OOS + Sharpe OOS de la stratégie orientée sur le train. HONNÊTE mais N≈2 cycles
    par moitié -> à lire comme tel."""
    idx, fwd = forward_returns(prices, h)
    pred, ret = [], []
    for k, t in enumerate(idx):
        if t < len(zs) and zs[t] is not None:
            pred.append(zs[t])
            ret.append(fwd[k])
    n = len(pred)
    if n < 60:
        return {"n": n, "note": "insuffisant"}
    cut = n // 2
    ic_tr = spearman_ic(pred[:cut], ret[:cut])
    ic_te = spearman_ic(pred[cut:], ret[cut:])
    sign = -1.0 if ic_tr < 0 else 1.0        # orientation apprise sur le train
    strat_te = [sign * (-1.0 if pred[cut + i] > 0 else 1.0) * ret[cut + i] for i in range(n - cut)]
    return {"n": n, "ic_train": round(ic_tr, 4), "ic_test": round(ic_te, 4),
            "t_test_indep": round(ic_tstat(ic_te, max(3, (n - cut) // h)), 2),
            "oos_sharpe": round(_sharpe(strat_te), 4)}


def _verdict(ic, dca, valid):
    """Verdict textuel HONNÊTE (beta de cycle probable)."""
    ic30 = next((r["ic"] for r in ic["expanding"]["head"] if r["h"] == 30 and r["ic"] is not None), None)
    dsr = valid["headline"].get("deflated_sharpe")
    wf_t = valid.get("walk_forward", {}).get("t_test_indep")
    survives = (dsr is not None and dsr >= 0.95) and (wf_t is not None and abs(wf_t) >= 2.0)
    v = []
    if ic30 is not None:
        sens = "reversion de valeur (z haut -> rendement bas)" if ic30 < 0 else "momentum (z haut -> rendement haut)"
        v.append(f"IC(z,fwd30j)={ic30:+.3f} [{sens}]")
    v.append(f"tilt DCA: cout moyen {dca['improve_pct']:+.2f}% vs DCA plat "
             f"(BTC {dca['btc_uplift_pct']:+.2f}%)")
    if dsr is not None:
        v.append(f"Deflated Sharpe={dsr:.3f} (seuil 0.95)")
    if wf_t is not None:
        v.append(f"walk-forward OOS t={wf_t}")
    v.append("VERDICT: " + ("SIGNAL SURVIT a la deflation (rare, re-verifier)"
                            if survives else
                            "BETA DE CYCLE — l'edge NE survit PAS a la deflation/WF (N cycles trop faible)"))
    return " | ".join(v)


def _save(out):
    try:
        RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _print(out):
    s = out["span"]
    print(f"MVRV-Z lab — BTC {s['start']} -> {s['end']} ({s['n_days']} jours, "
          f"Coin Metrics community keyless ; realized_cap DÉRIVÉ = mktcap/MVRV)")
    xc = out.get("price_crosscheck_bitget")
    if xc:
        print(f"  cross-check prix vs Bitget D1 : Spearman {xc['spearman']} sur {xc['n_overlap']} jours communs")
    print("  IC(z BRUT, rendement forward) — attendu NÉGATIF (réversion de valeur) :")
    for m in MODES:
        cells = " ".join(f"h{r['h']}={r['ic']}(t{r['t_indep']})" for r in out["ic"][m]["head"] if r["ic"] is not None)
        print(f"    mode {m:9s}: {cells}")
    d = out["dca_tilt"]
    print(f"  Tilt DCA (z causal, budget ÉGAL, {d['n_buys']} achats) : coût moyen "
          f"flat {d['cost_basis_flat']}$ vs tilt {d['cost_basis_tilt']}$ "
          f"-> {d['improve_pct']:+.2f}% (BTC {d['btc_uplift_pct']:+.2f}%)")
    h = out["validation"]["headline"]
    wf = out["validation"]["walk_forward"]
    print(f"  Déflation (n_trials={out['validation']['n_trials']}) : Sharpe(exp,h30)={h['sharpe']} "
          f"vs B&H {h['bh_sharpe']} ; Deflated Sharpe={h['deflated_sharpe']} (seuil 0.95) ; "
          f"E[maxSharpe|H0]={h['expected_max_sharpe_H0']}")
    print(f"  Walk-forward : IC train {wf.get('ic_train')} -> test {wf.get('ic_test')} "
          f"(t OOS {wf.get('t_test_indep')}, Sharpe OOS {wf.get('oos_sharpe')}) ; "
          f"buy-and-hold total {out['validation']['buy_hold_total_return_pct']}%")
    print("  " + out["verdict"])
    print("  Lecture seule, aucun ordre, défaut OFF. VERDICT: SAFE")


def status():
    """Dernier résultat mesuré (aucun réseau). Lecture seule."""
    try:
        out = json.loads(RESULT.read_text(encoding="utf-8"))
    except Exception:
        print("MVRV-Z : aucun résultat en cache. Lancer `python mvrv_lab.py --run`. VERDICT: SAFE")
        return None
    if out.get("status") == "ok":
        _print(out)
    else:
        print(f"MVRV-Z : {out.get('note', 'pas de mesure')}. VERDICT: SAFE")
    return out


def main():
    import sys
    args = sys.argv[1:]
    if "--status" in args:
        status()
        return
    if "--run" in args:
        run(use_net="--no-net" not in args)
        return
    print(__doc__.strip().splitlines()[0])
    print("Usage : python mvrv_lab.py --status | --run [--no-net]   (lecture seule, aucun ordre)")


if __name__ == "__main__":
    main()
