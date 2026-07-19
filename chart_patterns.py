#!/usr/bin/env python3
"""chart_patterns.py — détecteur de FIGURES CHARTISTES objectif & look-ahead-free.

COMPLÉMENT des événements « climax de volume » de `wyckoff_lab` (PAS un labo parallèle) :
mêmes bougies, MÊME harnais de mesure (net de frais, HAC/DSR/walk-forward/permutation/B&H).
Construit SUR les pivots fractals de `price_action.swing_points`. Classé SAFE : PUR, LECTURE
SEULE, AUCUN ordre, AUCUN secret, AUCUN chemin d'exécution. Défaut OFF (sans verbe CLI :
statut only).

POURQUOI (prior HONNÊTE — docs/VERDICTS.md, ERR-014, SMC/AIO rejeté) : les figures chartistes
« dessinées à l'œil » sont subjectives et data-snoopables ; Lo-Mamaysky-Wang (2000) ne trouvent
qu'un edge marginal, et Bulkowski lui-même chiffre des break-even failure rates élevés. En
intraday crypto elles sont a priori mangées par les frais. Ce module n'AFFIRME rien : il apporte
(1) la CAPACITÉ de détection OBJECTIVE (ancrage de `grok_vision`, structure pour le dashboard),
(2) une expérience de CONFLUENCE — la figure CONFIRMÉE par un climax Wyckoff proche et/ou par des
INDICATEURS (volume/RSI/tendance) bat-elle la figure seule ? C'est le sens de « les indicateurs
renforcent une confirmation ». On MESURE net de frais ; on ne branche RIEN sans preuve d'edge.

LOOK-AHEAD-FREE (règle d'or, ERR-002) : une figure est « détectée » à sa barre de CONFIRMATION t
= la clôture qui CASSE la neckline/ligne, et TOUS les pivots qui la composent sont strictement
antérieurs ET déjà confirmables (indice_pivot + k ≤ t, car un pivot fractal n'est connu que k
barres après). Entrée open t+1 (gérée par le harnais). Aucune fenêtre centrée, aucun pivot futur,
aucune neckline tracée avec un extremum non encore confirmé.

CLI :
    python chart_patterns.py --status [SYMBOL]        # config + disponibilité data
    python chart_patterns.py --run SYMBOL [GRAN]      # figures détectées + forward net (lisible)
    python chart_patterns.py --run-all                # univers × TF × figures × confluence + verdict
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

# --- briques VALIDÉES du dépôt (ne rien recoder) -----------------------------------------
from price_action import swing_points          # pivots fractals (PUR, testé)
import wyckoff_lab as wl                        # harnais de mesure + climax (SAFE, importe audit_core)

RESULT = Path(__file__).resolve().parent / ".chart_patterns_result.jsonl"

# ===================== PARAMÈTRES géométriques (pré-enregistrés, exposés) =====================
K_PIVOT = 3                 # demi-fenêtre fractale du pivot (confirmation = i + K_PIVOT)
TOL_EQ = 0.020             # tolérance « prix ~égaux » (épaules, sommets/creux jumeaux), 2 %
HEAD_MIN = 0.010           # tête ≥ 1 % au-dessus des épaules (H&S)
SLOPE_FLAT = 0.0010        # |pente| ≤ 0,1 %/barre => ligne « plate » (triangle/rectangle)
CONV_MIN = 0.15            # convergence min des deux lignes (largeur finale ≤ 85 % initiale)
MIN_SPAN = 5               # barres minimales entre 1er et dernier pivot d'une figure
MAX_WAIT_MULT = 1.0        # fenêtre de confirmation après le dernier pivot = MAX_WAIT_MULT × span
MAX_WAIT_MIN = 8           # plancher de la fenêtre de confirmation (barres)

# indicateurs de confluence
RSI_LEN = 14
VOL_MA = 20
SMA_TREND = 50
RSI_LONG_MAX = 72.0        # long : ne pas confirmer si déjà suracheté
RSI_SHORT_MIN = 28.0       # short : ne pas confirmer si déjà survendu
VOL_BREAK_MULT = 1.2       # volume de cassure ≥ 1,2 × sa moyenne (expansion)
CONFLUENCE_WYCKOFF_W = 5   # fenêtre (barres) pour « climax Wyckoff de même sens proche »

# figures -> sens fixe (+1 long / −1 short). Les figures directionnelles (sym-triangle,
# rectangle) émettent DEUX noms _long/_short (le sens se décide à la cassure, sens alors fixe).
PATTERNS = {
    "double_bottom": +1, "double_top": -1,
    "triple_bottom": +1, "triple_top": -1,
    "inverse_hs": +1, "head_shoulders": -1,
    "ascending_triangle": +1, "descending_triangle": -1,
    "falling_wedge": +1, "rising_wedge": -1,
    "sym_triangle_long": +1, "sym_triangle_short": -1,
    "rectangle_long": +1, "rectangle_short": -1,
    "bull_flag": +1, "bear_flag": -1,
}


# ===================== indicateurs PURS (numpy) pour la confluence =====================
def _sma(x, n):
    x = np.asarray(x, float)
    if len(x) < 1:
        return np.full(0, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(x)])
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _rsi(close, n=RSI_LEN):
    c = np.asarray(close, float)
    out = np.full(len(c), np.nan)
    if len(c) < n + 1:
        return out
    d = np.diff(c)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag = gain[:n].mean()
    al = loss[:n].mean()
    for i in range(n, len(c)):
        ag = (ag * (n - 1) + gain[i - 1]) / n
        al = (al * (n - 1) + loss[i - 1]) / n
        rs = ag / al if al > 1e-12 else np.inf
        out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


# ===================== pivots (avec indice de CONFIRMATION) + zigzag alterné =====================
def _pivot_seq(h, l, k=K_PIVOT):
    """PUR. Pivots fractals de `swing_points` enrichis de conf=i+k (barre où le pivot devient
    connu, look-ahead-free), zigzaggés en alternance H,L,H,L (on garde l'extrême en cas de
    doublon de type). Retourne une liste de dicts {i, price, kind, conf} triée par i."""
    piv = swing_points(h, l, k)                       # [(i, price, 'H'|'L')]
    raw = [{"i": i, "price": p, "kind": t, "conf": i + k} for (i, p, t) in piv]
    zz = []
    for p in raw:
        if zz and zz[-1]["kind"] == p["kind"]:
            prev = zz[-1]
            better = (p["price"] > prev["price"]) if p["kind"] == "H" else (p["price"] < prev["price"])
            if better:
                zz[-1] = p                            # garde l'extrême du même type
            continue
        zz.append(p)
    return zz


def _line(p1, p2):
    """Droite (pente, ordonnée) passant par deux pivots (indice, prix). dx>0 garanti (zigzag)."""
    dx = (p2["i"] - p1["i"]) or 1
    m = (p2["price"] - p1["price"]) / dx
    b = p1["price"] - m * p1["i"]
    return m, b


def _at(line, x):
    return line[0] * x + line[1]


def _first_break(c, start, stop, level_fn, direction):
    """PUR & look-ahead-free. Première clôture qui CASSE `level_fn(t)` dans `direction`
    (+1 au-dessus / −1 en dessous) sur t∈[start, stop], avec c[t-1] du BON côté (cassure
    FRAÎCHE). Retourne t ou None. `level_fn` n'utilise que des pivots de conf ≤ start ≤ t."""
    n = len(c)
    stop = min(stop, n - 1)
    for t in range(max(start, 1), stop + 1):
        lvl = level_fn(t)
        prev = level_fn(t - 1)
        if direction > 0:
            if c[t] > lvl and c[t - 1] <= prev:
                return t
        else:
            if c[t] < lvl and c[t - 1] >= prev:
                return t
    return None


def _wait_window(zz, j0, j1):
    """Fenêtre de confirmation [conf_dernier_pivot, conf_dernier_pivot + wait]."""
    span = zz[j1]["i"] - zz[j0]["i"]
    start = zz[j1]["conf"]
    wait = max(MAX_WAIT_MIN, int(MAX_WAIT_MULT * span))
    return start, start + wait


def _eq(a, b, tol=TOL_EQ):
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)


# ===================== DÉTECTION DES FIGURES (PURE, look-ahead-free) =====================
def detect_patterns(o, h, l, c, v, k=K_PIVOT):
    """PUR & LOOK-AHEAD-FREE. Retourne {figure: np.array d'indices de barre de CONFIRMATION t}.
    Chaque figure est confirmée par une CLÔTURE cassant sa neckline/ligne ; tous ses pivots ont
    conf ≤ t. Entrée (gérée par le harnais) = open t+1. Univers de figures = clés de PATTERNS."""
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    n = len(c)
    out = {name: [] for name in PATTERNS}
    if n < 4 * k + MIN_SPAN + MAX_WAIT_MIN:
        return {kk: np.array([], int) for kk in out}
    zz = _pivot_seq(h, l, k)

    def add(name, t):
        if t is not None:
            out[name].append(t)

    # --- figures à N pivots exacts (double/triple/H&S) : fenêtre glissante sur le zigzag ---
    for j in range(len(zz)):
        # ---- 3 pivots : double top (H,L,H) / double bottom (L,H,L) ----
        if j >= 2:
            a, b_, d = zz[j - 2], zz[j - 1], zz[j]
            if d["i"] - a["i"] >= MIN_SPAN:
                if a["kind"] == "H" and d["kind"] == "H" and _eq(a["price"], d["price"]):
                    neck = b_["price"]                      # creux intermédiaire
                    s, e = _wait_window(zz, j - 2, j)
                    add("double_top", _first_break(c, s, e, lambda t: neck, -1))
                if a["kind"] == "L" and d["kind"] == "L" and _eq(a["price"], d["price"]):
                    neck = b_["price"]
                    s, e = _wait_window(zz, j - 2, j)
                    add("double_bottom", _first_break(c, s, e, lambda t: neck, +1))
        # ---- 5 pivots : H&S (H,L,H,L,H) / inverse (L,H,L,H,L) / triple ----
        if j >= 4:
            p = zz[j - 4:j + 1]
            kinds = "".join(x["kind"] for x in p)
            span_ok = (p[4]["i"] - p[0]["i"]) >= MIN_SPAN
            if span_ok and kinds == "HLHLH":
                ls, hd, rs = p[0]["price"], p[2]["price"], p[4]["price"]
                t1, t2 = p[1], p[3]                          # creux = neckline
                s, e = _wait_window(zz, j - 4, j)
                # Head & Shoulders : tête au-dessus des épaules ~égales, neckline sloped
                if hd > ls * (1 + HEAD_MIN) and hd > rs * (1 + HEAD_MIN) and _eq(ls, rs):
                    ln = _line(t1, t2)
                    add("head_shoulders", _first_break(c, s, e, lambda t: _at(ln, t), -1))
                # Triple top : 3 sommets ~égaux ; neckline = min des deux creux
                if _eq(ls, hd) and _eq(hd, rs) and _eq(ls, rs):
                    neck = min(t1["price"], t2["price"])
                    add("triple_top", _first_break(c, s, e, lambda t: neck, -1))
            if span_ok and kinds == "LHLHL":
                ls, hd, rs = p[0]["price"], p[2]["price"], p[4]["price"]
                t1, t2 = p[1], p[3]                          # sommets = neckline
                s, e = _wait_window(zz, j - 4, j)
                if hd < ls * (1 - HEAD_MIN) and hd < rs * (1 - HEAD_MIN) and _eq(ls, rs):
                    ln = _line(t1, t2)
                    add("inverse_hs", _first_break(c, s, e, lambda t: _at(ln, t), +1))
                if _eq(ls, hd) and _eq(hd, rs) and _eq(ls, rs):
                    neck = max(t1["price"], t2["price"])
                    add("triple_bottom", _first_break(c, s, e, lambda t: neck, +1))

    # --- figures à deux LIGNES (triangles/wedges/rectangle) : 2 derniers H + 2 derniers L ---
    for j in range(len(zz)):
        highs = [p for p in zz[:j + 1] if p["kind"] == "H"][-2:]
        lows = [p for p in zz[:j + 1] if p["kind"] == "L"][-2:]
        if len(highs) < 2 or len(lows) < 2:
            continue
        i_first = min(highs[0]["i"], lows[0]["i"])
        i_last = max(highs[1]["i"], lows[1]["i"])
        if (i_last - i_first) < MIN_SPAN:
            continue
        up = _line(highs[0], highs[1]); dn = _line(lows[0], lows[1])
        # pentes normalisées en %/barre
        ref = max(abs(highs[1]["price"]), 1e-9)
        m_up = up[0] / ref; m_dn = dn[0] / ref
        w_start = max(abs(_at(up, i_first) - _at(dn, i_first)), 1e-9)
        w_end = abs(_at(up, i_last) - _at(dn, i_last))
        converging = w_end <= (1 - CONV_MIN) * w_start
        conf0 = max(highs[1]["conf"], lows[1]["conf"])
        wait = max(MAX_WAIT_MIN, int(MAX_WAIT_MULT * (i_last - i_first)))
        s, e = conf0, conf0 + wait
        res_lvl = (highs[0]["price"] + highs[1]["price"]) / 2.0
        sup_lvl = (lows[0]["price"] + lows[1]["price"]) / 2.0
        flat_up = abs(m_up) <= SLOPE_FLAT
        flat_dn = abs(m_dn) <= SLOPE_FLAT
        # rectangle : deux lignes plates -> cassure directionnelle
        if flat_up and flat_dn and _eq(highs[0]["price"], highs[1]["price"]) \
                and _eq(lows[0]["price"], lows[1]["price"]):
            add("rectangle_long", _first_break(c, s, e, lambda t: res_lvl, +1))
            add("rectangle_short", _first_break(c, s, e, lambda t: sup_lvl, -1))
        # triangle ascendant : résistance plate + support montant
        elif flat_up and m_dn > SLOPE_FLAT and converging:
            add("ascending_triangle", _first_break(c, s, e, lambda t: res_lvl, +1))
        # triangle descendant : support plat + résistance descendante
        elif flat_dn and m_up < -SLOPE_FLAT and converging:
            add("descending_triangle", _first_break(c, s, e, lambda t: sup_lvl, -1))
        # wedge montant (haussier de forme mais BAISSIER) : deux pentes > 0, support plus raide
        elif m_up > SLOPE_FLAT and m_dn > SLOPE_FLAT and m_dn > m_up and converging:
            add("rising_wedge", _first_break(c, s, e, lambda t: _at(dn, t), -1))
        # wedge descendant (baissier de forme mais HAUSSIER) : deux pentes < 0, résistance plus raide
        elif m_up < -SLOPE_FLAT and m_dn < -SLOPE_FLAT and m_up < m_dn and converging:
            add("falling_wedge", _first_break(c, s, e, lambda t: _at(up, t), +1))
        # triangle symétrique : résistance descend, support monte, convergence -> directionnel
        elif m_up < -SLOPE_FLAT and m_dn > SLOPE_FLAT and converging:
            add("sym_triangle_long", _first_break(c, s, e, lambda t: _at(up, t), +1))
            add("sym_triangle_short", _first_break(c, s, e, lambda t: _at(dn, t), -1))

    # --- flags/pennants : pôle d'impulsion puis petite consolidation, continuation ---
    _detect_flags(o, h, l, c, zz, out)

    return {name: np.array(sorted(set(ix)), int) for name, ix in out.items()}


def _detect_flags(o, h, l, c, zz, out, pole_min=0.05, pole_win=10):
    """Bull/Bear flag : impulsion (pôle) ≥ pole_min sur ≤ pole_win barres, puis consolidation
    bornée par les 2 derniers pivots opposés au pôle, cassure dans le sens du pôle. Look-ahead-free."""
    c = np.asarray(c, float); n = len(c)
    for j in range(1, len(zz)):
        p1, p2 = zz[j - 1], zz[j]
        if (p2["i"] - p1["i"]) > pole_win or (p2["i"] - p1["i"]) < 1:
            continue
        move = (p2["price"] - p1["price"]) / max(abs(p1["price"]), 1e-9)
        s = p2["conf"]; e = min(n - 1, p2["i"] + max(MAX_WAIT_MIN, pole_win))
        if move >= pole_min:                                    # pôle haussier -> bull flag
            add_break = _first_break(c, s, e, lambda t: p2["price"], +1)
            if add_break is not None:
                out["bull_flag"].append(add_break)
        elif move <= -pole_min:                                 # pôle baissier -> bear flag
            add_break = _first_break(c, s, e, lambda t: p2["price"], -1)
            if add_break is not None:
                out["bear_flag"].append(add_break)


# ===================== CONFLUENCE (indicateurs + climax Wyckoff) =====================
def confluence_mask(o, h, l, c, v, idx, sens, mode="volume"):
    """PUR & look-ahead-free (tout ≤ t). Filtre les confirmations `idx` d'une figure de sens
    `sens` par CONFLUENCE :
      • 'volume' : volume[t] ≥ VOL_BREAK_MULT × SMA(volume, VOL_MA)[t] (cassure en expansion) ;
      • 'full'   : volume ET RSI non-épuisé (long: RSI≤max ; short: RSI≥min) ET tendance SMA
                   alignée (long: close>SMA50 ; short: close<SMA50).
    Retourne le sous-tableau d'indices retenus."""
    idx = np.asarray(idx, int)
    if len(idx) == 0:
        return idx
    v = np.asarray(v, float); c = np.asarray(c, float)
    vma = _sma(v, VOL_MA)
    keep = np.ones(len(idx), bool)
    volok = np.zeros(len(idx), bool)
    for a, t in enumerate(idx):
        if t < len(vma) and np.isfinite(vma[t]) and vma[t] > 0:
            volok[a] = v[t] >= VOL_BREAK_MULT * vma[t]
    keep &= volok
    if mode == "full":
        rsi = _rsi(c, RSI_LEN)
        sma = _sma(c, SMA_TREND)
        for a, t in enumerate(idx):
            if not keep[a]:
                continue
            r = rsi[t] if t < len(rsi) else np.nan
            m = sma[t] if t < len(sma) else np.nan
            if sens > 0:
                ok = (not np.isfinite(r) or r <= RSI_LONG_MAX) and (not np.isfinite(m) or c[t] > m)
            else:
                ok = (not np.isfinite(r) or r >= RSI_SHORT_MIN) and (not np.isfinite(m) or c[t] < m)
            keep[a] = ok
    return idx[keep]


def wyckoff_confluence_mask(o, h, l, c, v, idx, sens, z=None, w=CONFLUENCE_WYCKOFF_W):
    """Sous-ensemble de `idx` où un CLIMAX Wyckoff de MÊME sens (`wyckoff_lab.detect_events`) a eu
    lieu dans [t−w, t]. C'est le « complément Wyckoff » : la figure confirmée par le volume-climax."""
    idx = np.asarray(idx, int)
    if len(idx) == 0:
        return idx
    z = wl.Z_PRIMARY if z is None else z
    ev = wl.detect_events(o, h, l, c, v, z=z)
    same = np.concatenate([ev[name] for name, s in wl.EVENTS.items() if s == sens]
                          ) if any(s == sens for s in wl.EVENTS.values()) else np.array([], int)
    if len(same) == 0:
        return np.array([], int)
    same = np.sort(same)
    keep = []
    for t in idx:
        lo = np.searchsorted(same, t - w, "left")
        hi = np.searchsorted(same, t, "right")
        if hi > lo:
            keep.append(t)
    return np.array(keep, int)


# ===================== MESURE (réutilise le harnais wyckoff_lab) =====================
def _confl_indices(d, confluence="none"):
    """Calcule UNE fois (par symbole/TF) le dict {figure: indices} pour un mode de confluence.
    Coûteux (détection) -> à mettre en cache avant de balayer les horizons h."""
    pats = detect_patterns(d["o"], d["h"], d["l"], d["c"], d["v"])
    if confluence == "none":
        return pats
    if confluence in ("volume", "full"):
        return {nm: confluence_mask(d["o"], d["h"], d["l"], d["c"], d["v"],
                                    pats[nm], PATTERNS[nm], confluence) for nm in PATTERNS}
    if confluence == "wyckoff":
        return {nm: wyckoff_confluence_mask(d["o"], d["h"], d["l"], d["c"], d["v"],
                                            pats[nm], PATTERNS[nm]) for nm in PATTERNS}
    return pats


def _pool_from_idx(loaded, idx_by_sym, name, h, fees):
    """Concatène les forward nets (taker & maker) de tous les symboles pour une figure `name` à
    horizon `h`, à partir d'indices DÉJÀ calculés (idx_by_sym[sym][name]). Réutilise wl.forward_net."""
    sens = PATTERNS[name]
    rt_tk, rt_mk = 2.0 * fees["taker"], 2.0 * fees["maker"]
    tk, mk, gr = [], [], []
    for sym, d in loaded.items():
        idx = np.asarray(idx_by_sym.get(sym, {}).get(name, np.array([], int)), int)
        if len(idx) == 0:
            continue
        idx = idx[(idx + 1 + h) < len(d["o"])]
        if len(idx) == 0:
            continue
        gross, net_t = wl.forward_net(d["o"], idx, h, sens, rt_tk)
        _, net_m = wl.forward_net(d["o"], idx, h, sens, rt_mk)
        m = min(len(gross), len(net_t), len(net_m))
        tk.append(net_t[:m]); mk.append(net_m[:m]); gr.append(gross[:m])
    if not tk:
        return None
    return dict(taker=np.concatenate(tk), maker=np.concatenate(mk), gross=np.concatenate(gr))


def _pool_pattern(loaded, name, h, fees, confluence="none"):
    """Chemin PRATIQUE (1 symbole/quelques TF) : détecte à la volée puis poole. Pour l'univers
    complet, préférer le cache (`_confl_indices` + `_pool_from_idx`) — voir run_patterns_all."""
    idx_by_sym = {sym: _confl_indices(d, confluence) for sym, d in loaded.items()}
    return _pool_from_idx(loaded, idx_by_sym, name, h, fees)


def run_patterns_all(use_live_fees=False, market="futures", verbose=True):
    """Univers liquide × échelle TF × figures × {seule, +volume, +full, +wyckoff}. Mesure net de
    frais + Deflated Sharpe déflaté par l'espace de recherche complet + verdict pré-enregistré."""
    if not wl._HAS_AUDIT:
        return {"error": "audit_core indisponible", "verdict": "ABSTENTION (fail-safe)"}
    fees = wl.resolve_fees(market=market, use_live=use_live_fees)
    confl_modes = ["none", "volume", "full", "wyckoff"]
    grid, sr_trials = [], []
    n_trials = len(wl.GRANS) * len(PATTERNS) * len(wl.H_GRID) * len(confl_modes)
    loaded_by_gran = {}
    for gran in wl.GRANS:
        loaded = {}
        for sym in wl.SYMBOLS:
            d = wl._load(sym, gran)
            if d is not None:
                loaded[sym] = d
        if not loaded:
            continue
        loaded_by_gran[gran] = loaded
        # CACHE : détection (coûteuse) UNE fois par (symbole, mode de confluence) ; l'horizon h
        # ne change pas les indices -> on ne balaie h que sur les forward nets (bon marché).
        idx_cache = {confl: {sym: _confl_indices(d, confl) for sym, d in loaded.items()}
                     for confl in confl_modes}
        for name in PATTERNS:
            for h in wl.H_GRID:
                for confl in confl_modes:
                    p = _pool_from_idx(loaded, idx_cache[confl], name, h, fees)
                    if p is None:
                        continue
                    st_t = wl._stats(p["taker"]); st_m = wl._stats(p["maker"])
                    row = dict(gran=gran, pattern=name, h=h, confluence=confl, n=st_m["n"],
                               net_taker_bps=st_t["mean"], net_maker_bps=st_m["mean"],
                               t_hac_maker=st_m["t_hac"], sr_maker=st_m["sr"])
                    grid.append(row)
                    if np.isfinite(st_m["sr"]) and st_m["n"] >= wl.MIN_EVENTS:
                        sr_trials.append(st_m["sr"])
        if verbose:
            best_g = [r for r in grid if r["gran"] == gran and np.isfinite(r["sr_maker"])
                      and r["n"] >= wl.MIN_EVENTS]
            if best_g:
                b = max(best_g, key=lambda r: r["sr_maker"])
                print(f"  [{gran}] best: {b['pattern']}/{b['confluence']} h={b['h']} "
                      f"net_maker={b['net_maker_bps']:.2f}bps t_HAC={b['t_hac_maker']:.2f} n={b['n']}")

    valid = [r for r in grid if np.isfinite(r["sr_maker"]) and r["n"] >= wl.ROBUST_N]
    if not valid:
        res = {"error": "aucune figure robuste (data trop courte / figures trop rares)",
               "n_trials": n_trials, "fees_bps": fees, "grid_size": len(grid),
               "verdict": "réel-non-tradable (figures trop rares pour un échantillon robuste)"}
        _write(res)
        if verbose:
            print(f"\n  >>> {res['verdict']} (grid={len(grid)}, aucune config n≥{wl.ROBUST_N})")
        return res
    best = max(valid, key=lambda r: r["sr_maker"])

    # Deflated Sharpe sur la figure gagnante, déflaté par n_trials complet
    dsr = None
    p = _pool_pattern(loaded_by_gran.get(best["gran"], {}), best["pattern"], best["h"], fees,
                      confluence=best["confluence"])
    if p is not None and len(p["maker"]) >= wl.MIN_EVENTS and len(sr_trials) > 1:
        try:
            ds = wl.ac.deflated_sharpe(p["maker"], sr_trials=np.array(sr_trials), n_trials=n_trials)
            if ds is not None:
                dsr = {kk: float(vv) for kk, vv in ds.items()}
        except Exception:
            dsr = None

    # confluence AIDE-T-ELLE ? net maker moyen par mode (n≥ROBUST_N), pondéré par n
    confl_effect = {}
    for cm in confl_modes:
        rows = [r for r in valid if r["confluence"] == cm]
        if rows:
            wsum = sum(r["n"] for r in rows)
            confl_effect[cm] = dict(
                mean_net_maker=float(sum(r["net_maker_bps"] * r["n"] for r in rows) / wsum),
                n_configs=len(rows), n_events=int(wsum))

    dsr_ok = bool(dsr and np.isfinite(dsr.get("dsr", float("nan"))) and dsr["dsr"] >= 0.95)
    t_ok = bool(np.isfinite(best["t_hac_maker"]) and best["t_hac_maker"] >= 3.0)
    net_ok = bool(np.isfinite(best["net_maker_bps"]) and best["net_maker_bps"] > 0)
    passed = dsr_ok and t_ok and net_ok
    verdict = ("TRADABLE (à confirmer réel)" if passed
               else "réel-non-tradable (figures chartistes fee-killed / non robustes — prior tenu)")

    res = {"ts": int(time.time()), "market": market, "fees_bps": fees, "n_trials": n_trials,
           "universe": wl.SYMBOLS, "grans": wl.GRANS, "h_grid": wl.H_GRID,
           "confluence_modes": confl_modes, "params": {"K_PIVOT": K_PIVOT, "TOL_EQ": TOL_EQ,
           "HEAD_MIN": HEAD_MIN, "CONV_MIN": CONV_MIN, "MIN_SPAN": MIN_SPAN},
           "best": best, "deflated_sharpe": dsr, "confluence_effect": confl_effect,
           "gate": {"net_maker>0": net_ok, "t_hac>=3": t_ok, "dsr>=0.95": dsr_ok},
           "gate_passed": passed, "verdict": verdict, "grid_size": len(grid)}
    _write(res)
    if verbose:
        _print_verdict(res)
    return res


def run_patterns_one(sym, gran=None, use_live_fees=False, market="futures"):
    """1 symbole : figures détectées par TF + forward net (seule vs +volume vs +wyckoff). Lisible."""
    if not wl._HAS_AUDIT:
        print("audit_core indisponible — ABSTENTION (fail-safe).")
        return None
    fees = wl.resolve_fees(market=market, use_live=use_live_fees)
    grans = [gran] if gran else wl.GRANS
    print(f"=== chart_patterns --run {sym} (frais {market} taker={fees['taker']} "
          f"maker={fees['maker']} bps/côté) ===")
    for g in grans:
        d = wl._load(sym, g)
        if d is None:
            print(f"  [{g}] data insuffisante")
            continue
        pats = detect_patterns(d["o"], d["h"], d["l"], d["c"], d["v"])
        counts = {k: len(x) for k, x in pats.items() if len(x)}
        if not counts:
            print(f"  [{g}] aucune figure")
            continue
        print(f"  [{g}] figures : " + ", ".join(f"{k}×{n}" for k, n in sorted(counts.items())))
        loaded = {sym: d}
        for name in [k for k, n in counts.items() if n]:
            for confl in ("none", "volume", "wyckoff"):
                p = _pool_pattern(loaded, name, 4, fees, confluence=confl)
                if p is None:
                    continue
                st = wl._stats(p["maker"])
                if st["n"]:
                    print(f"      {name:20s} h=4 {confl:8s} n={st['n']:<3} "
                          f"net_maker={st['mean']:7.2f}bps t_HAC={st['t_hac']:6.2f}")
    print("Lecture seule, aucun ordre. VERDICT: SAFE")


def status(sym=None):
    print("=== chart_patterns --status (figures chartistes — SAFE, défaut OFF) ===")
    print(f"audit_core (via wyckoff_lab) : {wl._HAS_AUDIT}")
    print(f"figures ({len(PATTERNS)}) : {', '.join(PATTERNS)}")
    print(f"univers : {', '.join(wl.SYMBOLS)}")
    print(f"échelle TF : {', '.join(wl.GRANS)}  (ERR-001)")
    print(f"params : K_PIVOT={K_PIVOT} TOL_EQ={TOL_EQ} HEAD_MIN={HEAD_MIN} "
          f"CONV_MIN={CONV_MIN} MIN_SPAN={MIN_SPAN}")
    print("confluence : none | volume | full | wyckoff (climax de même sens ≤ "
          f"{CONFLUENCE_WYCKOFF_W} barres)")
    if RESULT.exists():
        try:
            prev = json.loads(RESULT.read_text())
            print(f"dernier verdict : {prev.get('verdict')} (gate_passed={prev.get('gate_passed')})")
        except Exception:
            pass
    print("Lecture seule, aucun ordre, défaut OFF. VERDICT: SAFE")


def _write(res):
    try:
        RESULT.write_text(json.dumps(res, default=float), encoding="utf-8")
    except Exception:
        pass


def _print_verdict(res):
    print("\n=== VERDICT CHART-PATTERNS (figures chartistes) ===")
    b = res["best"]
    print(f"figure gagnante (max Sharpe maker) : {b['pattern']} {b['gran']} h={b['h']} "
          f"confluence={b['confluence']}")
    print(f"  net maker {b['net_maker_bps']:.2f} bps | net taker {b['net_taker_bps']:.2f} bps "
          f"| t_HAC {b['t_hac_maker']:.2f} | n={b['n']}")
    ds = res.get("deflated_sharpe")
    if ds:
        print(f"  Deflated Sharpe : DSR={ds['dsr']:.3f} (seuil 0,95 ; N_trials={res['n_trials']})")
    ce = res.get("confluence_effect", {})
    if ce:
        print("  effet confluence (net maker moyen pondéré) :")
        for cm, d in ce.items():
            print(f"      {cm:8s} : {d['mean_net_maker']:7.2f} bps "
                  f"({d['n_configs']} configs, {d['n_events']} events)")
    print(f"  gate : {res['gate']}")
    print(f"  >>> {res['verdict']}")
    print("Lecture seule, aucun ordre, défaut OFF. VERDICT: SAFE")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.split("CLI :")[-1].strip())
        print("\nDéfaut OFF : aucun verbe -> aucune mesure. VERDICT: SAFE")
        return
    live = "--live-fees" in args
    if args[0] == "--status":
        sym = next((a for a in args[1:] if not a.startswith("-")), None)
        status(sym)
    elif args[0] == "--run":
        rest = [a for a in args[1:] if not a.startswith("-")]
        run_patterns_one(rest[0] if rest else "BTCUSDT",
                         rest[1] if len(rest) > 1 else None, use_live_fees=live)
    elif args[0] == "--run-all":
        print("=== chart_patterns --run-all (univers × TF × figures × confluence) ===")
        run_patterns_all(use_live_fees=live)
    else:
        print("usage: --status | --run SYMBOL [GRAN] | --run-all   [--live-fees]")


if __name__ == "__main__":
    main()
