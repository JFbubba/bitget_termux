#!/usr/bin/env python3
"""vpin_lab.py — banc de MESURE VPIN (toxicité du flux, Easley-López de Prado-O'Hara).

Classement : SAFE. LECTURE SEULE (bougies disque `data_history/` + fetch PUBLIC read-only
via `taker_flow`), AUCUN ordre, AUCUN secret, AUCUN chemin d'exécution (ni `spot_trader`, ni
noyau `bitget_execute`, ni mot-clé de passage d'ordre). Défaut OFF : ce module ne fait que du
CALCUL sur historique + une consultation `--status`. Sorties = console + un JSON de résultats
(`.vpin_lab_result.json`, gitignoré). Un éventuel gate LIVE resterait un opt-in `.env` à
décider par le propriétaire — il n'est PAS câblé ici (repérage seul dans docs/VPIN_LAB.md).

CE QU'EST VPIN (Volume-synchronized Probability of INformed trading — Easley, López de Prado,
O'Hara 2012) : on ré-échantillonne le flux en BUCKETS de VOLUME ÉGAL V (pas de temps égal), et
VPIN = moyenne mobile sur N buckets de |buy − sell| / (buy + sell). C'est une proxy de la
probabilité que le flux soit INFORMÉ (toxique) : un déséquilibre acheteur/vendeur persistant
par unité de volume = sélection adverse pour le fournisseur de liquidité (nous, en maker).

POURQUOI un banc À PART (comme mm_lab §94 / grid_lab) : ce n'est PAS un signal directionnel
(signal×rendement, jugé par strategy_lab §68) — c'est une claim de QUALITÉ DE FILL à coût de
frais quasi nul : « nos fills maker sont-ils empoisonnés quand VPIN est haut ? ». Le prior du
dépôt (edges orderflow < frais) ne s'applique PAS directement : la question du gate est
orthogonale (éviter les fills toxiques, pas parier une direction).

SUBSTRAT DE DONNÉES (réutilise l'existant, ne duplique rien) :
  • buy/sell taker DIRECT : `taker_flow.volume_delta_series` — mais l'endpoint `taker-buy-sell`
    ne rend que ~30 barres/appel (sous-alimenté, cf. orderflow_lab) → réservé au SNAPSHOT
    `--status` (VPIN courant), pas au backtest ;
  • BVC (Bulk Volume Classification) sur BOUGIES : fraction acheteuse = Φ(Δclose/σ(Δclose))
    via `black_scholes._norm_cdf` — repli CANONIQUE du VPIN quand le buy/sell signé manque.
    C'est ce qui rend le test statistique faisable (30k barres/TF sur disque) ;
  • markout post-fill (sélection adverse) : `microstructure.markout` réutilisé tel quel ;
  • validation : `agent_validation.deflated_sharpe/psr/sharpe`, `backtest_brain.walk_forward/pbo`.

HONNÊTETÉS DU MODÈLE (à lire avant de croire un chiffre) :
  • fill maker = post-only SANS file d'attente : buy rempli si low ≤ bid, sell si high ≥ ask,
    fair = clôture PRÉCÉDENTE (causal) — cas FAVORABLE, BORNE SUPÉRIEURE (le réel fera moins) ;
  • VPIN aligné aux fills est CAUSAL (buckets formés de barres ≤ barre précédente) ;
  • markout = mid FUTUR proxy par close_{i+h} (aucun carnet L1 historique) ;
  • ÉCHELLE TF (ERR-001) : BVC couvre M1·5m·15m·30m·H1·H4·D1·W1. Le VPIN signé DIRECT ne
    couvre que 5m..1day (l'endpoint n'a PAS de M1) ; le VPIN W1 est DÉGÉNÉRÉ (trop peu de
    buckets) — les deux limites sont SIGNALÉES, jamais fabriquées.

CLI :
    python vpin_lab.py --status [SYMBOL] [PERIOD]   # VPIN courant (consultation, read-only)
    python vpin_lab.py --run [SYMBOL] [GRAN]        # 1 (sym,TF) détaillé
    python vpin_lab.py --run-all                    # BTC/ETH/SOL × échelle TF (le verdict)
"""
import bisect
import json
import math
import time
from pathlib import Path

import black_scholes as bs          # _norm_cdf pour la classification BVC
import microstructure as ms         # markout (sélection adverse) — réutilisé tel quel

RESULT = Path(__file__).resolve().parent / ".vpin_lab_result.json"

FEE_MAKER_RT_BPS = 4.0              # aller-retour maker futures (2×0,02 %) — défaut
FEE_SPOT_BGB_RT_BPS = 8.0          # aller-retour maker spot avec déduction BGB (paramètre alt)
VPIN_WINDOW = 50                   # nb de buckets de la moyenne mobile (standard Easley-LdP)
BVC_SIGMA_WINDOW = 50              # fenêtre de σ(Δclose) pour la BVC (causale)
QUANTILE = 0.20                    # décile ~haut/bas VPIN pour le contraste de markout
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
# Échelle TF COMPLÈTE (ERR-001) — grans candles_history. 1m/1W inclus mais annotés (limites).
GRANS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]
# Périodes de l'endpoint taker-buy-sell (VPIN signé DIRECT — snapshot only) :
DIRECT_PERIODS = ["5m", "15m", "30m", "1h", "4h", "12h", "1day"]


# ===================== fonctions PURES : VPIN =====================

def _imbalance(buy, sell):
    """|buy − sell| / (buy + sell) ∈ [0,1]. PUR. 0 = flux parfaitement équilibré."""
    tot = buy + sell
    return abs(buy - sell) / tot if tot > 0 else 0.0


def volume_buckets(series, bucket_volume):
    """PUR. Ré-échantillonne une série [{ts, buy, sell}] en BUCKETS de VOLUME ÉGAL
    `bucket_volume`, en SPLITTANT proportionnellement les barres qui débordent (méthode
    Easley-LdP). Chaque bucket = {ts, buy, sell} avec buy+sell ≈ bucket_volume. [] si dégénéré."""
    if bucket_volume is None or bucket_volume <= 0:
        return []
    buckets = []
    cur_buy = cur_sell = 0.0
    cur_ts = None
    for r in (series or []):
        buy = float(r.get("buy", 0.0) or 0.0)
        sell = float(r.get("sell", 0.0) or 0.0)
        vol = buy + sell
        if vol <= 0:
            continue
        b_ratio, s_ratio = buy / vol, sell / vol
        remaining = vol
        cur_ts = r.get("ts")
        while remaining > 1e-12:
            need = bucket_volume - (cur_buy + cur_sell)
            take = remaining if remaining < need else need
            cur_buy += take * b_ratio
            cur_sell += take * s_ratio
            remaining -= take
            if (cur_buy + cur_sell) >= bucket_volume - 1e-9:
                buckets.append({"ts": cur_ts, "buy": cur_buy, "sell": cur_sell})
                cur_buy = cur_sell = 0.0
    return buckets


def compute_vpin(series, bucket_volume, window=VPIN_WINDOW):
    """PUR. VPIN Easley-López de Prado : buckets à volume égal V, puis VPIN = moyenne
    mobile sur `window` buckets de |buy−sell|/(buy+sell). series = [{ts, buy, sell}].
    Retour [{ts, vpin, imbalance}] (1 point/bucket dès qu'on a `window` buckets). [] si
    données vides / < window buckets. Cas connus : flux équilibré -> 0 ; déséquilibré -> 1."""
    buckets = volume_buckets(series, bucket_volume)
    w = max(1, int(window))
    imb = [_imbalance(b["buy"], b["sell"]) for b in buckets]
    out = []
    run_sum = 0.0
    for i in range(len(buckets)):
        run_sum += imb[i]
        if i >= w:
            run_sum -= imb[i - w]
        if i >= w - 1:
            out.append({"ts": buckets[i]["ts"], "vpin": run_sum / w, "imbalance": imb[i]})
    return out


def _rolling_std(dp, i, win):
    """σ (ddof=1) des deltas dp[max(0,i-win):i] (causal, dernier = dp[i-1]). PUR helper.
    (i = indice de barre ≥ 1 ; dp[k] = close[k+1]-close[k].)"""
    lo = max(0, i - win)
    sub = dp[lo:i]
    n = len(sub)
    if n < 2:
        return 0.0
    m = sum(sub) / n
    var = sum((d - m) ** 2 for d in sub) / (n - 1)
    return math.sqrt(var) if var > 0 else 0.0


def bvc_series(candles, sigma_window=BVC_SIGMA_WINDOW):
    """PUR. Bulk Volume Classification (Easley-LdP-O'Hara 2012) : depuis des bougies
    [ts,o,h,l,c,v], fraction acheteuse d'une barre = Φ(Δclose / σ(Δclose)) avec σ roulant
    CAUSAL. Retour [{ts, buy, sell, delta}] aligné aux bougies (dès la 2e). Substitut du
    buy/sell taker signé quand l'endpoint direct est trop court (~30 barres)."""
    cl, vol, ts = [], [], []
    for c in (candles or []):
        if len(c) >= 6:
            ts.append(c[0]); cl.append(float(c[4])); vol.append(float(c[5]))
    if len(cl) < 3:
        return []
    dp = [cl[k] - cl[k - 1] for k in range(1, len(cl))]
    out = []
    for i in range(1, len(cl)):
        sd = _rolling_std(dp, i, sigma_window)          # deltas jusqu'à dp[i-1] inclus
        z = (dp[i - 1] / sd) if sd > 0 else 0.0
        bf = bs._norm_cdf(z)
        v = vol[i]
        buy, sell = v * bf, v * (1.0 - bf)
        out.append({"ts": ts[i], "buy": buy, "sell": sell, "delta": buy - sell})
    return out


# ===================== fonctions PURES : fills maker + markout =====================

def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def median_bar_volume(candles):
    """PUR. Volume médian par barre (pour dimensionner un bucket de volume). 0.0 si vide."""
    return _median([float(c[5]) for c in candles if len(c) >= 6])


def typical_range_bps(candles):
    """PUR. (high-low)/close médian en bps — sert à caler un demi-spread réaliste. 0 si vide."""
    r = [(float(c[2]) - float(c[3])) / float(c[4]) * 1e4
         for c in candles if len(c) >= 6 and float(c[4]) > 0]
    return _median(r)


def simulate_and_tag(candles, cfg):
    """PUR (sur bougies). Rejoue des fills maker post-only, TAG chaque fill du VPIN causal
    (BVC) et du sens du flux, calcule le markout NET `markout_h` barres plus tard.

    cfg = {spread_bps, markout_h, fee_bps, bucket_volume, window, sigma_window}.
    Fill : fair = close précédente ; bid = fair·(1−s/2), ask = fair·(1+s/2) ; buy rempli si
    low ≤ bid, sell si high ≥ ask (post-only, sans file d'attente = borne sup).
    flow_against : pour un buy, flux CONTRE = delta<0 (vendeurs agressifs) ; pour un sell,
    flux CONTRE = delta>0. Retour [{ts,i,side,price,vpin,delta,flow_against,markout_bps,net_bps}]."""
    n = len(candles)
    h = max(1, int(cfg["markout_h"]))
    fee = float(cfg["fee_bps"])
    hs = float(cfg["spread_bps"]) / 2.0 / 1e4
    ser = bvc_series(candles, cfg["sigma_window"])
    vp = compute_vpin(ser, cfg["bucket_volume"], cfg["window"])
    if not vp or n < h + 3:
        return []
    vp_ts = [p["ts"] for p in vp]
    vp_val = [p["vpin"] for p in vp]
    delta_by_ts = {r["ts"]: r["delta"] for r in ser}
    fills = []
    for i in range(2, n - h):
        prev = candles[i - 1]
        fair = float(prev[4])
        if fair <= 0:
            continue
        cutoff_ts = prev[0]                              # VPIN connu à la clôture précédente
        k = bisect.bisect_right(vp_ts, cutoff_ts) - 1    # dernier bucket ≤ cutoff (causal)
        if k < 0:
            continue
        vpin = vp_val[k]
        delta = delta_by_ts.get(cutoff_ts, 0.0)
        low, high = float(candles[i][3]), float(candles[i][2])
        ts = candles[i][0]
        future_mid = float(candles[i + h][4])
        bid, ask = fair * (1 - hs), fair * (1 + hs)
        if low <= bid:
            mk = ms.markout(bid, "buy", future_mid)
            fills.append({"ts": ts, "i": i, "side": "buy", "price": bid, "vpin": vpin,
                          "delta": delta, "flow_against": delta < 0,
                          "markout_bps": mk, "net_bps": mk - fee})
        if high >= ask:
            mk = ms.markout(ask, "sell", future_mid)
            fills.append({"ts": ts, "i": i, "side": "sell", "price": ask, "vpin": vpin,
                          "delta": delta, "flow_against": delta > 0,
                          "markout_bps": mk, "net_bps": mk - fee})
    return fills


def condition_by_vpin(fills, q=QUANTILE):
    """PUR. Sépare les fills par QUANTILE de VPIN : décile haut (top q) vs bas (bottom q).
    L'EXPÉRIENCE CENTRALE. diff<0 = markout NET plus TOXIQUE en VPIN élevé (fill-and-be-killed).
    Retour {n, hi_n, lo_n, hi_mean_net, lo_mean_net, diff, t, ...} ou None si trop peu de fills."""
    vals = [f for f in fills if f.get("vpin") is not None]
    if len(vals) < 20:
        return None
    s = sorted(vals, key=lambda f: f["vpin"])
    k = max(1, int(len(s) * q))
    lo = [f["net_bps"] for f in s[:k]]
    hi = [f["net_bps"] for f in s[-k:]]
    hm, lm = sum(hi) / len(hi), sum(lo) / len(lo)
    t = _welch_t(hi, lo)
    return {"n": len(vals), "hi_n": len(hi), "lo_n": len(lo),
            "hi_mean_net": round(hm, 4), "lo_mean_net": round(lm, 4),
            "diff": round(hm - lm, 4), "t": round(t, 2),
            "hi_vpin_min": round(s[-k]["vpin"], 4), "lo_vpin_max": round(s[k - 1]["vpin"], 4)}


def apply_gate(fills, vpin_threshold, directional=True):
    """PUR. Gate de QUALITÉ DE FILL : écarte un fill si VPIN ≥ seuil (ET, si directional, le
    flux taker est CONTRE notre côté). MONOTONE par construction : ne garde JAMAIS un fill de
    plus que sans gate (kept ⊆ fills). Retourne la sous-liste GARDÉE."""
    kept = []
    for f in fills:
        toxic = f.get("vpin", 0.0) >= vpin_threshold and (f.get("flow_against", False) if directional else True)
        if not toxic:
            kept.append(f)
    return kept


def gate_gain(fills, vpin_threshold, directional=True):
    """PUR. Gain NET du gate = markout des fills GARDÉS vs TOUS (moyenne par fill = qualité ;
    somme = P&L incluant le coût d'opportunité des fills bénins manqués). Un gate n'est retenu
    que s'il AMÉLIORE le markout moyen net (mean_kept > mean_all) ET écarte des fills pires."""
    if not fills:
        return None
    kept_net, rem_net, all_net = [], [], []
    for f in fills:                                       # une seule passe (pas de O(n²))
        net = f["net_bps"]
        all_net.append(net)
        toxic = f.get("vpin", 0.0) >= vpin_threshold and (f.get("flow_against", False) if directional else True)
        (rem_net if toxic else kept_net).append(net)
    mean = lambda a: (sum(a) / len(a)) if a else 0.0
    return {"n_all": len(all_net), "n_kept": len(kept_net), "n_removed": len(rem_net),
            "mean_all": round(mean(all_net), 4), "mean_kept": round(mean(kept_net), 4),
            "mean_removed": round(mean(rem_net), 4),
            "sum_all": round(sum(all_net), 2), "sum_kept": round(sum(kept_net), 2),
            "delta_mean": round(mean(kept_net) - mean(all_net), 4),
            "improves": mean(kept_net) > mean(all_net) and mean(rem_net) < mean(kept_net)}


# ===================== fonctions PURES : stats / validation =====================

def _welch_t(a, b):
    """t de Welch (variances inégales) entre deux échantillons. PUR. 0 si dégénéré."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    denom = math.sqrt(va / na + vb / nb)
    return (ma - mb) / denom if denom > 0 else 0.0


def bootstrap_diff(hi, lo, n_boot=2000, seed=12345):
    """DÉTERMINISTE (seed). Bootstrap de la DIFFÉRENCE de markout moyen (VPIN haut − bas),
    vectorisé numpy. Retour {mean, lo95, hi95, p_ge0} : p_ge0 = fraction de rééchantillons
    avec diff ≥ 0 (petit => VPIN élevé robustement PIRE). Remise, longueur conservée."""
    if len(hi) < 5 or len(lo) < 5:
        return None
    import numpy as np
    rng = np.random.default_rng(seed)
    a, b = np.asarray(hi, float), np.asarray(lo, float)
    sh = a[rng.integers(0, len(a), size=(n_boot, len(a)))].mean(axis=1)
    sl = b[rng.integers(0, len(b), size=(n_boot, len(b)))].mean(axis=1)
    diffs = np.sort(sh - sl)
    return {"mean": round(float(diffs.mean()), 4),
            "lo95": round(float(diffs[int(0.025 * n_boot)]), 4),
            "hi95": round(float(diffs[min(n_boot - 1, int(0.975 * n_boot))]), 4),
            "p_ge0": round(float((diffs >= 0).mean()), 4)}


def non_overlapping(fills, h):
    """PUR. Sous-échantillon de fills espacés d'au moins `h` barres (indice `i`) — évite la
    fuite par chevauchement des fenêtres de markout. Glouton, tri par `i`."""
    out, last = [], -10 ** 9
    for f in sorted(fills, key=lambda x: x["i"]):
        if f["i"] - last >= h:
            out.append(f)
            last = f["i"]
    return out


# ===================== orchestration (I/O best-effort, read-only) =====================

def _load_candles(symbol, gran, max_bars):
    try:
        import candles_history as ch
        rows = ch.load(symbol, gran)
        return rows[-max_bars:] if max_bars and len(rows) > max_bars else rows
    except Exception:
        return []


def default_grid():
    """Petite grille HONNÊTE (pas d'optimisation fine = pas de surapprentissage) : taille de
    bucket (× vol médian) et horizon de markout. Chaque config = 1 essai (déflation)."""
    return [("bpb1·h3", 1, 3), ("bpb1·h6", 1, 6), ("bpb3·h3", 3, 3), ("bpb3·h6", 3, 6)]


def run_symbol_gran(symbol, gran, fee_bps=FEE_MAKER_RT_BPS, max_bars=12000,
                    window=VPIN_WINDOW, q=QUANTILE):
    """Une (sym, TF) : fills BVC-VPIN, expérience de contraste, gate, validation. Read-only.
    Renvoie un dict par config + un résumé. FAIL-SAFE : données maigres -> verdict explicite."""
    candles = _load_candles(symbol, gran, max_bars)
    if len(candles) < window * 4 + 50:
        return {"symbol": symbol, "gran": gran, "verdict": "donnees_insuffisantes",
                "n_candles": len(candles)}
    med_vol = median_bar_volume(candles)
    spread_bps = max(1.0, typical_range_bps(candles))    # demi-spread ~ excursion typique
    degenerate = gran in ("1W",)                          # VPIN W1 dégénéré (trop peu de buckets)
    configs = []
    for label, bpb, h in default_grid():
        cfg = {"spread_bps": spread_bps, "markout_h": h, "fee_bps": fee_bps,
               "bucket_volume": med_vol * bpb, "window": window,
               "sigma_window": BVC_SIGMA_WINDOW}
        fills = simulate_and_tag(candles, cfg)
        cond = condition_by_vpin(fills, q)
        if not cond:
            configs.append({"label": label, "n_fills": len(fills), "cond": None})
            continue
        s = sorted(fills, key=lambda f: f["vpin"])
        k = max(1, int(len(s) * q))
        hi_net = [f["net_bps"] for f in s[-k:]]
        lo_net = [f["net_bps"] for f in s[:k]]
        boot = bootstrap_diff(hi_net, lo_net)
        thr = s[-k]["vpin"]                               # seuil VPIN = borne du décile haut
        gain = gate_gain(fills, thr, directional=True)
        nov = non_overlapping(fills, h)
        net_series = [f["net_bps"] for f in nov]          # non-chevauchant pour Sharpe/DSR
        configs.append({"label": label, "n_fills": len(fills), "n_nonoverlap": len(nov),
                        "spread_bps": round(spread_bps, 2), "vpin_threshold": round(thr, 4),
                        "cond": cond, "boot": boot, "gate": gain,
                        "_net_series": net_series})
    return {"symbol": symbol, "gran": gran, "n_candles": len(candles),
            "med_vol": round(med_vol, 4), "degenerate": degenerate, "configs": configs}


def run_all(fee_bps=FEE_MAKER_RT_BPS, symbols=None, grans=None, max_bars=12000):
    """LE VERDICT : BTC/ETH/SOL × échelle TF. Déflate par le NB TOTAL d'essais (sym×TF×config)
    via Deflated Sharpe + t déflaté. Écrit le JSON. Read-only."""
    import agent_validation as av
    import backtest_brain as bt
    symbols = symbols or SYMBOLS
    grans = grans or GRANS
    per_cell = []
    for s in symbols:
        for g in grans:
            per_cell.append(run_symbol_gran(s, g, fee_bps=fee_bps, max_bars=max_bars))
    # rassemble les essais valides (pour var_sr + déflation)
    trials = []
    for cell in per_cell:
        for c in cell.get("configs", []):
            if c.get("cond"):
                trials.append((cell, c))
    n_trials = max(1, len(trials))
    sharpes = []
    pbo_inputs = {}
    for cell, c in trials:
        ser = c.get("_net_series") or []
        sr = av.sharpe(ser) if len(ser) >= 5 else 0.0
        c["sharpe"] = round(sr, 4)
        sharpes.append(sr)
        if len(ser) >= 20:
            pbo_inputs[f"{cell['symbol']}·{cell['gran']}·{c['label']}"] = ser
    var_sr = 0.0
    if len(sharpes) >= 2:
        m = sum(sharpes) / len(sharpes)
        var_sr = sum((x - m) ** 2 for x in sharpes) / (len(sharpes) - 1)
    # DSR + t déflaté du contraste VPIN par essai
    for cell, c in trials:
        ser = c.get("_net_series") or []
        if len(ser) >= 5:
            sk, ku = av._skew_kurt(ser)
            c["dsr"] = round(av.deflated_sharpe(av.sharpe(ser), len(ser), sk, ku, n_trials, var_sr), 4)
        else:
            c["dsr"] = None
        t = c["cond"]["t"]
        c["t_defl"] = round(t / (1.0 + math.log(n_trials)), 2)   # déflaté (comme orderflow_watch)
        c.pop("_net_series", None)
    # PBO sur la grille (surapprentissage du choix de config)
    try:
        pbo = bt.pbo(pbo_inputs) if len(pbo_inputs) >= 2 else {"pbo": None}
    except Exception:
        pbo = {"pbo": None}
    # sélection des essais ROBUSTES : contraste négatif (VPIN haut pire) + t déflaté fort +
    # bootstrap qui exclut 0 + gate qui améliore + DSR élevé.
    robustes = []
    for cell, c in trials:
        cond, boot, gate = c.get("cond"), c.get("boot"), c.get("gate")
        if not (cond and boot and gate):
            continue
        ok = (cond["diff"] < 0 and abs(c["t_defl"]) >= 2.5 and boot["hi95"] < 0
              and gate.get("improves") and (c.get("dsr") or 0) >= 0.95)
        if ok:
            robustes.append({"symbol": cell["symbol"], "gran": cell["gran"], "label": c["label"],
                             "diff": cond["diff"], "t_defl": c["t_defl"], "boot": boot,
                             "delta_mean_gate": gate["delta_mean"], "dsr": c.get("dsr")})
    out = {"ts": int(time.time()), "fee_bps": fee_bps, "n_cells": len(per_cell),
           "n_trials": n_trials, "var_sr": round(var_sr, 5), "pbo": pbo,
           "robustes": robustes, "cells": per_cell,
           "note": ("BORNE SUP (fill post-only sans file, fair causal, markout=close futur). "
                    "VPIN signé DIRECT limité au snapshot (~30 barres) ; le backtest = BVC sur "
                    "bougies. M1 direct indisponible, W1 dégénéré (annotés).")}
    try:
        RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=1)[:8_000_000], encoding="utf-8")
    except Exception:
        pass
    return out


# ===================== snapshot live (consultation, read-only) =====================

def status(symbol="BTCUSDT", period="1h"):
    """Consultation : VPIN COURANT. Signé DIRECT (taker_flow, ~30 barres) si dispo, SINON BVC
    sur bougies récentes. Aucun réseau de trading. Retour dict (jamais d'exception)."""
    out = {"symbol": symbol, "period": period, "direct": None, "bvc": None}
    try:
        import taker_flow as tf
        bars = tf.fetch(symbol, period)
        ser = tf.volume_delta_series(bars)               # [{ts,buy,sell,delta,cvd}]
        if len(ser) >= 4:
            med = _median([r["buy"] + r["sell"] for r in ser]) or 1.0
            w = max(2, min(VPIN_WINDOW, len(ser) // 2))
            vp = compute_vpin(ser, med, w)
            if vp:
                out["direct"] = {"n_bars": len(ser), "window": w,
                                 "vpin": round(vp[-1]["vpin"], 4),
                                 "last_imbalance": round(vp[-1]["imbalance"], 4)}
            else:
                out["direct"] = {"n_bars": len(ser), "note": "trop peu de buckets (endpoint court)"}
    except Exception as e:
        out["direct"] = {"error": type(e).__name__}
    try:
        # mapping d'INPUT `period`->granularité pour le PROBE de STATUT (snapshot VPIN direct) ; la
        # MESURE d'edge, elle, couvre GRANS complet M1..W1 (M1 direct indispo / W1 dégénéré annotés).
        gran = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1H", "4h": "4H",  # tf-ladder-ok : probe de statut, pas un test-ladder
                "12h": "1H", "1day": "1D"}.get(period, "1H")
        candles = _load_candles(symbol, gran, 3000)
        if len(candles) >= VPIN_WINDOW * 4:
            ser = bvc_series(candles)
            vp = compute_vpin(ser, median_bar_volume(candles), VPIN_WINDOW)
            if vp:
                vals = [p["vpin"] for p in vp]
                rank = sum(1 for v in vals if v <= vp[-1]["vpin"]) / len(vals)
                out["bvc"] = {"n_candles": len(candles), "gran": gran,
                              "vpin": round(vp[-1]["vpin"], 4),
                              "pct_rank": round(rank, 3)}       # position vs historique
    except Exception as e:
        out["bvc"] = {"error": type(e).__name__}
    return out


# ===================== CLI =====================

def _fmt_cell(cell):
    lines = []
    tag = " [DÉGÉNÉRÉ W1]" if cell.get("degenerate") else ""
    head = f"— {cell['symbol']} {cell['gran']}{tag} (n_bougies {cell.get('n_candles','?')})"
    if cell.get("verdict") == "donnees_insuffisantes":
        return head + " : données insuffisantes"
    lines.append(head)
    for c in cell.get("configs", []):
        cond = c.get("cond")
        if not cond:
            lines.append(f"    {c['label']:10} : {c.get('n_fills',0)} fills — pas d'expérience")
            continue
        boot = c.get("boot") or {}
        gate = c.get("gate") or {}
        lines.append(
            f"    {c['label']:10} : {c['n_fills']} fills · VPIN haut {cond['hi_mean_net']:+.3f} vs "
            f"bas {cond['lo_mean_net']:+.3f} bps (diff {cond['diff']:+.3f}, t_défl {c.get('t_defl','?')}) "
            f"· boot95 [{boot.get('lo95','?')},{boot.get('hi95','?')}] "
            f"· gate Δmoy {gate.get('delta_mean','?'):+} ({'AMÉLIORE' if gate.get('improves') else 'non'}) "
            f"· DSR {c.get('dsr')}")
    return "\n".join(lines)


def main():
    import sys
    args = sys.argv[1:]
    flags = [a for a in args if a.startswith("--")]
    pos = [a for a in args if not a.startswith("--")]
    if "--status" in flags or not flags:
        sym = (pos[0] if pos else "BTCUSDT").upper()
        per = pos[1] if len(pos) > 1 else "1h"
        st = status(sym, per)
        print(f"=== VPIN LAB (consultation, lecture seule) — {sym} {per} ===")
        d = st.get("direct")
        print(f"  signé DIRECT (taker_flow) : {d}")
        print(f"  BVC (bougies)             : {st.get('bvc')}")
        print("VERDICT: SAFE")
        return
    if "--run" in flags:
        sym = (pos[0] if pos else "BTCUSDT").upper()
        gran = pos[1] if len(pos) > 1 else "1H"
        cell = run_symbol_gran(sym, gran)
        print(f"=== VPIN LAB (banc de mesure, lecture seule) — {sym} {gran} ===")
        print(_fmt_cell(cell))
        print("VERDICT: SAFE")
        return
    if "--run-all" in flags:
        rep = run_all()
        print("=== VPIN LAB — VERDICT (BTC/ETH/SOL × échelle TF), lecture seule ===")
        print(f"essais {rep['n_trials']} · var_sr {rep['var_sr']} · PBO {rep['pbo'].get('pbo')}")
        for cell in rep["cells"]:
            print(_fmt_cell(cell))
        if rep["robustes"]:
            print("\n🟢 GATE VPIN ROBUSTE (à VÉRIFIER, jamais branché ici) :")
            for r in rep["robustes"]:
                print(f"   {r['symbol']} {r['gran']} {r['label']} : diff {r['diff']:+.3f} bps "
                      f"t_défl {r['t_defl']} DSR {r['dsr']} gateΔ {r['delta_mean_gate']:+}")
        else:
            print("\nAucun gate VPIN déflation-robuste (diff<0 ∧ t_défl≥2.5 ∧ boot95<0 ∧ "
                  "gate améliore ∧ DSR≥0.95). Voir docs/VERDICTS.md.")
        print(rep["note"])
        print("VERDICT: SAFE")
        return
    print("usage : python vpin_lab.py [--status SYM PERIOD | --run SYM GRAN | --run-all]")


if __name__ == "__main__":
    main()
