#!/usr/bin/env python3
"""wyckoff_lab.py — banc de MESURE « climax de volume » (le SEUL angle Wyckoff mesurable).

Classement : SAFE. LECTURE SEULE (bougies disque `data_history/` via `audit_core.load` +
lecture read-only fail-safe des frais réels via `fee_rates`), AUCUN ordre, AUCUN secret,
AUCUN chemin d'exécution (ni `spot_trader`, ni noyau `bitget_execute`, ni mot-clé de passage
d'ordre). Défaut OFF : sans verbe CLI le module n'imprime qu'un usage/statut ; il ne fait QUE
du CALCUL sur historique. Sorties = console + un JSON de résultats (`.wyckoff_lab_result.jsonl`,
gitignoré via le glob existant `*.jsonl` — voir NOTE artefact plus bas). Aucun gate LIVE n'est
câblé : le prior du dépôt est que ces événements finissent fee-killed en taker (docs/WYCKOFF.md
Partie II) ; on MESURE, on ne branche rien.

POURQUOI CE LABO (docs/WYCKOFF.md Parties II & IV) : Wyckoff en tant que MÉTHODE (lecture
discrétionnaire de phases) = même piège que SMC/ICT (rejetés, ERR-014) — look-ahead intrinsèque
(un « spring » n'est un spring qu'APRÈS le test réussi), labellisation discrétionnaire,
multiple-testing massif. La SEULE nuance falsifiable : Wyckoff met le VOLUME au centre, et le
volume anormal a une signature académique réelle (high-volume return premium, Gervais-Kaniel-
Mingelgrin 2001 ; sur-réaction crypto post-choc, Caporale-Plastun 2020). Donc un sous-ensemble
d'événements est objectivement définissable AU CLOSE, SANS look-ahead : les CLIMAX de volume
(SC/BC) et le SPRING/UPTHRUST intrabar. C'est le seul angle mesurable.

ÉVÉNEMENT (100 % connu au close de la barre t, AUCUN look-ahead) :
  • vol_z = (vol[t] − mean(vol, N trailing)) / std(vol, N trailing) ≥ seuil z ;
  • range large : range[t] = high−low ≥ 90ᵉ percentile trailing du range ;
  • contexte : nouveau plus-bas N-barres (SC/spring) / plus-haut N-barres (BC/upthrust) ;
  • close-location CLV = (close−low)/(high−low) : SC → CLV≥0,6 (long) ; BC → CLV≤0,4 (short) ;
  • SPRING intrabar (variante) : low[t] < min(low, M trailing) ET close[t] > min(low, M trailing)
    (fausse cassure sous le support, refermée au-dessus) ; UPTHRUST = miroir en haut.
  Sur ce labo à THÈME climax, le spring/upthrust exige AUSSI vol_z≥z (shakeout à volume ; on
  reste on-theme et look-ahead-free — déviation ASSUMÉE vs la variante prix-seule du design,
  annotée). Entrée open t+1 ; SC/spring → long, BC/upthrust → short.

MESURE & VALIDATION STRICTE (barre anti-sur-testing) :
  • rendement forward NET DE FRAIS à h∈{1,2,4,8,16}, en TAKER ET MAKER (frais réels via
    `fee_rates.futures_fee_bps` si dispo, sinon défauts futures 6/2 bps ; spot 10/8 en param) ;
  • échelle TF COMPLÈTE M1·5m·15m·30m·H1·H4·D1·W1 (ERR-001) ; univers LIQUIDE (8 majors) ;
  • t HAC/Newey-West (`audit_core.nw_tstat`) — corrige le t gonflé par l'autocorrélation ;
  • Deflated Sharpe (`audit_core.deflated_sharpe`) sur N_trials = TF×h×directions×seuils = 480 ;
  • walk-forward OOS : le seuil z est choisi sur le TRAIN, évalué en OOS uniquement ;
  • permutation/shuffle : l'edge doit s'effondrer (mean → ~0) contre un tirage aléatoire ;
  • contrôle positif : réversion 1h connue (gross) + oracle synthétique (sanity du harnais) ;
  • benchmark buy-and-hold apparié (alpha vs beta, ERR-014).
  CRITÈRE PRÉ-ENREGISTRÉ (PASS) : net>0 OOS ∧ t_HAC≥3 ∧ DSR≥0,95 ∧ cohérent ≥2 TF adjacents
  ∧ > B&H. Sinon → réel-non-tradable (on ne branche rien).

NOTE artefact : le résultat est écrit dans `.wyckoff_lab_result.jsonl` (UN objet JSON sur une
ligne). Le suffixe `.jsonl` n'est pas sémantique — il fait hériter l'artefact du glob gitignore
EXISTANT `*.jsonl` sans éditer `.gitignore` (fichier partagé, gelé pendant la fenêtre multi-agents).

CLI :
    python wyckoff_lab.py --status [SYMBOL]        # config + disponibilité data (consultation)
    python wyckoff_lab.py --run SYMBOL [GRAN]      # 1 symbole détaillé (grille events×h×z)
    python wyckoff_lab.py --run-all                # univers × échelle TF + validation + verdict
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

# --- réutilisation de la MACHINERIE VALIDÉE (ne rien recoder : HAC, DSR, load) -----------
# audit_core vit dans scratchpad/audit_indep/ ; on l'importe par insertion de chemin (import
# read-only, numpy/scipy purs). Fail-safe : si indisponible, le labo le signale et s'abstient.
_AUDIT_DIR = Path(__file__).resolve().parent / "scratchpad" / "audit_indep"
if str(_AUDIT_DIR) not in sys.path:
    sys.path.insert(0, str(_AUDIT_DIR))
try:
    import audit_core as ac  # nw_tstat (HAC), deflated_sharpe, expected_max_sharpe, load
    _HAS_AUDIT = True
except Exception:            # pragma: no cover - garde fail-safe
    ac = None
    _HAS_AUDIT = False

RESULT = Path(__file__).resolve().parent / ".wyckoff_lab_result.jsonl"

# ===================== PARAMÈTRES (tous exposés / pré-enregistrés) =====================
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
           "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]   # univers LIQUIDE (exclut alts fragiles)
GRANS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]  # échelle COMPLÈTE (ERR-001)
H_GRID = [1, 2, 4, 8, 16]                                   # horizons forward (barres)
Z_GRID = [2.5, 3.0, 3.5]                                    # seuils vol_z (les « seuils »)
Z_PRIMARY = 3.0                                             # seuil pré-enregistré du run détaillé
N_BASE = 100                # fenêtre trailing (vol_z, percentile range, contexte plus-bas/haut)
M_SPRING = 20               # fenêtre trailing du spring/upthrust intrabar
RANGE_PCTL = 90.0           # percentile trailing du range (« range large »)
CLV_LONG = 0.6              # SC/spring : close near high
CLV_SHORT = 0.4             # BC/upthrust : close near low
MIN_EVENTS = 20             # sous ce seuil : pas de t HAC (annoté, jamais fabriqué)
ROBUST_N = 50               # plancher d'échantillon pour le CHOIX du gagnant « tête d'affiche »
                            # (évite qu'un pic 1W/1D n=20 sur-appris pilote le verdict — c'est
                            # précisément le piège multiple-testing ; il reste visible à part)

# frais par CÔTÉ (bps). Défaut = FUTURES (les bougies data_history sont mix/USDT-FUTURES).
FEE_FUT_TAKER_BPS = 6.0
FEE_FUT_MAKER_BPS = 2.0
FEE_SPOT_TAKER_BPS = 10.0   # exposés en param (spot) ; non utilisés par défaut
FEE_SPOT_MAKER_BPS = 8.0    # spot avec déduction BGB effective

# directions d'événement -> sens (+1 long / −1 short)
EVENTS = {"sc_long": +1, "bc_short": -1, "spring_long": +1, "upthrust_short": -1}
# N_trials déflation = TF × h × directions × seuils (search space pré-enregistré)
N_TRIALS = len(GRANS) * len(H_GRID) * len(EVENTS) * len(Z_GRID)   # 8*5*4*3 = 480


# ===================== frais (réels si dispo, sinon défauts) =====================
def resolve_fees(market="futures", use_live=False):
    """Frais {'taker','maker'} par côté en bps. FAIL-SAFE : défauts en dur si `fee_rates`
    indisponible / erreur réseau. `use_live` tente une lecture read-only des taux du compte."""
    if market == "spot":
        taker, maker = FEE_SPOT_TAKER_BPS, FEE_SPOT_MAKER_BPS
    else:
        taker, maker = FEE_FUT_TAKER_BPS, FEE_FUT_MAKER_BPS
    if use_live:
        try:
            import fee_rates as fr
            if market == "spot":
                s = fr.spot_fee_bps()
                taker = maker = float(s)   # spot : maker=taker au tier VIP0
            else:
                f = fr.futures_fee_bps()
                taker, maker = float(f["taker"]), float(f["maker"])
        except Exception:
            pass                            # fail-safe : on garde les défauts
    return {"taker": round(taker, 4), "maker": round(maker, 4)}


# ===================== I/O read-only (fail-safe) =====================
def _load(sym, gran):
    """Bougies numpy via audit_core.load. None si indispo / trop court. Ne lève JAMAIS."""
    if not _HAS_AUDIT:
        return None
    try:
        d = ac.load(sym, gran)
        if d is None or d["n_dedup"] < N_BASE + max(H_GRID) + 5:
            return None
        return d
    except Exception:
        return None


# ===================== DÉTECTION D'ÉVÉNEMENTS (PURE, look-ahead-free) =====================
def _trailing_mean_std(v, N):
    """PUR. mean/std (population) des N barres PRÉCÉDENTES [t−N, t−1], via sommes cumulées.
    Renvoie (mean, std) alignés sur t ; NaN pour t < N (pas assez d'historique). Exclut la
    barre courante -> le climax se démarque de son propre passé (causal)."""
    v = np.asarray(v, float)
    n = len(v)
    cs = np.concatenate([[0.0], np.cumsum(v)])
    cs2 = np.concatenate([[0.0], np.cumsum(v * v)])
    mean = np.full(n, np.nan)
    std = np.full(n, np.nan)
    if n <= N:
        return mean, std
    idx = np.arange(N, n)
    s = cs[idx] - cs[idx - N]
    s2 = cs2[idx] - cs2[idx - N]
    m = s / N
    var = np.maximum(s2 / N - m * m, 0.0)
    mean[idx] = m
    std[idx] = np.sqrt(var)
    return mean, std


def _sliding(arr, win):
    """PUR. Vue fenêtres glissantes (n−win+1, win) : ligne i = arr[i:i+win]."""
    return np.lib.stride_tricks.sliding_window_view(np.asarray(arr, float), win)


def detect_events(o, h, l, c, v, N=N_BASE, M=M_SPRING, z=Z_PRIMARY,
                  range_pctl=RANGE_PCTL, clv_long=CLV_LONG, clv_short=CLV_SHORT):
    """PUR & LOOK-AHEAD-FREE. Détecte les 4 familles d'événements au CLOSE de chaque barre t.
    Toutes les fenêtres sont trailing/inclusives ≤ t ; l'entrée (gérée ailleurs) est open t+1.
    Retourne {event_name: np.array d'indices t}. Cas connus testés : flux normal -> peu/pas
    d'événements ; barre à volume extrême + close haut + nouveau plus-bas -> sc_long détecté."""
    o = np.asarray(o, float); h = np.asarray(h, float)
    l = np.asarray(l, float); c = np.asarray(c, float); v = np.asarray(v, float)
    n = len(c)
    out = {k: np.array([], dtype=int) for k in EVENTS}
    if n < N + M + 2:
        return out

    rng = h - l
    with np.errstate(divide="ignore", invalid="ignore"):
        clv = np.where(rng > 0, (c - l) / rng, 0.5)

    mean_v, std_v = _trailing_mean_std(v, N)
    with np.errstate(divide="ignore", invalid="ignore"):
        vol_z = np.where(std_v > 0, (v - mean_v) / std_v, 0.0)

    # percentile trailing du range sur [t−N, t−1] (exclut la barre courante)
    rng_pct = np.full(n, np.nan)
    if n > N:
        W = _sliding(rng[:-1], N)                      # ligne i -> rng[i:i+N] = [i, i+N-1]
        pct = np.percentile(W, range_pctl, axis=1)     # aligné : pct[i] concerne la barre i+N
        rng_pct[N:] = pct[: n - N]

    # contexte : nouveau plus-bas / plus-haut sur N barres INCLUANT t (fenêtre [t−N+1, t])
    newlow = np.zeros(n, bool)
    newhigh = np.zeros(n, bool)
    if n >= N:
        Wl = _sliding(l, N)                            # ligne i -> l[i:i+N]
        Wh = _sliding(h, N)
        roll_min = Wl.min(axis=1)                      # aligné sur t = i+N-1
        roll_max = Wh.max(axis=1)
        newlow[N - 1:] = l[N - 1:] <= roll_min + 1e-12
        newhigh[N - 1:] = h[N - 1:] >= roll_max - 1e-12

    # spring / upthrust intrabar : réf = min/max des M barres PRÉCÉDENTES [t−M, t−1]
    spring = np.zeros(n, bool)
    upthrust = np.zeros(n, bool)
    if n > M:
        Wlm = _sliding(l[:-1], M)                      # ligne i -> l[i:i+M] = [i, i+M-1]
        Whm = _sliding(h[:-1], M)
        prior_low = Wlm.min(axis=1)                    # prior_low[i] concerne la barre i+M
        prior_high = Whm.max(axis=1)
        pl = np.full(n, np.nan); ph = np.full(n, np.nan)
        pl[M:] = prior_low[: n - M]
        ph[M:] = prior_high[: n - M]
        spring[M:] = (l[M:] < pl[M:]) & (c[M:] > pl[M:])
        upthrust[M:] = (h[M:] > ph[M:]) & (c[M:] < ph[M:])

    big_vol = np.nan_to_num(vol_z, nan=0.0) >= z
    wide = rng >= np.nan_to_num(rng_pct, nan=np.inf)

    sc = big_vol & wide & newlow & (clv >= clv_long)
    bc = big_vol & wide & newhigh & (clv <= clv_short)
    sp = big_vol & spring                              # shakeout à volume (on-theme)
    up = big_vol & upthrust

    out["sc_long"] = np.where(sc)[0]
    out["bc_short"] = np.where(bc)[0]
    out["spring_long"] = np.where(sp)[0]
    out["upthrust_short"] = np.where(up)[0]
    return out


# ===================== RENDEMENTS FORWARD NETS DE FRAIS =====================
def forward_net(o, idx, h, sens, rt_fee_bps):
    """PUR. Pour chaque événement t de `idx` : entrée open[t+1], sortie open[t+1+h].
    gross_bps = sens·(sortie−entrée)/entrée·1e4 ; net = gross − rt_fee_bps (frais aller-retour).
    Écarte les t sans barre de sortie (look-ahead-free). Retourne (gross_arr, net_arr)."""
    o = np.asarray(o, float)
    n = len(o)
    idx = np.asarray(idx, int)
    idx = idx[(idx + 1 + h) < n]
    if len(idx) == 0:
        return np.array([]), np.array([])
    entry = o[idx + 1]
    exit_ = o[idx + 1 + h]
    with np.errstate(divide="ignore", invalid="ignore"):
        gross = sens * (exit_ - entry) / entry * 1e4
    gross = gross[np.isfinite(gross)]
    net = gross - rt_fee_bps
    return gross, net


def _stats(net):
    """mean/n/sr(par-événement)/t_HAC. sr = mean/std (ddof1). t via nw_tstat (HAC) si n≥MIN."""
    net = np.asarray(net, float)
    net = net[np.isfinite(net)]
    n = len(net)
    if n == 0:
        return dict(n=0, mean=float("nan"), sr=float("nan"), t_hac=float("nan"))
    mean = float(np.mean(net))
    sd = float(np.std(net, ddof=1)) if n > 1 else 0.0
    sr = mean / sd if sd > 1e-12 else float("nan")
    t_hac = float("nan")
    if _HAS_AUDIT and n >= MIN_EVENTS:
        r = ac.nw_tstat(net)
        if r is not None:
            t_hac = float(r["t_nw"])
    return dict(n=n, mean=mean, sr=sr, t_hac=t_hac)


# ===================== ÉVALUATION D'UNE CONFIG (poolée sur l'univers) =====================
def pool_forward(loaded, gran, event, h, z, fees):
    """Concatène les rendements forward nets (taker & maker) de TOUS les symboles chargés
    pour une config (gran, event, h, z). `loaded` = {sym: dict bougies}. Retourne dict avec
    séries taker/maker + les indices ts (pour walk-forward) + gross (pour permutation)."""
    sens = EVENTS[event]
    rt_taker = 2.0 * fees["taker"]
    rt_maker = 2.0 * fees["maker"]
    tk, mk, gr, tss = [], [], [], []
    for sym, d in loaded.items():
        ev = detect_events(d["o"], d["h"], d["l"], d["c"], d["v"], N=N_BASE, M=M_SPRING, z=z)
        idx = ev.get(event, np.array([], dtype=int))
        if len(idx) == 0:
            continue
        idx = idx[(idx + 1 + h) < len(d["o"])]
        if len(idx) == 0:
            continue
        gross, net_t = forward_net(d["o"], idx, h, sens, rt_taker)
        _, net_m = forward_net(d["o"], idx, h, sens, rt_maker)
        m = min(len(gross), len(net_t), len(net_m), len(idx))
        tk.append(net_t[:m]); mk.append(net_m[:m]); gr.append(gross[:m])
        tss.append(d["ts"][idx[:m]])
    if not tk:
        return None
    return dict(taker=np.concatenate(tk), maker=np.concatenate(mk),
                gross=np.concatenate(gr), ts=np.concatenate(tss))


def benchmark_bh(loaded, gran, h, sens, fee_maker_rt):
    """Buy-and-hold apparié = rendement forward NET moyen d'une entrée ALÉATOIRE (toutes barres),
    même sens & frais maker. C'est la « beta » ; l'edge de l'événement doit la battre (ERR-014)."""
    vals = []
    for sym, d in loaded.items():
        o = d["o"]; n = len(o)
        k = np.arange(0, n - 1 - h)
        if len(k) == 0:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            g = sens * (o[k + 1 + h] - o[k + 1]) / o[k + 1] * 1e4
        vals.append(g[np.isfinite(g)] - fee_maker_rt)
    if not vals:
        return float("nan")
    return float(np.mean(np.concatenate(vals)))


# ===================== VALIDATEURS =====================
def walk_forward_oos(loaded, gran, event, h, fees, train_frac=0.6):
    """Seuil z choisi sur le TRAIN (max Sharpe maker), évalué en OOS. Split temporel unique
    (événements poolés triés par ts). Retourne dict(z_star, oos_mean, oos_t, n_oos) ou None."""
    per_z = {}
    for z in Z_GRID:
        p = pool_forward(loaded, gran, event, h, z, fees)
        if p is None or len(p["maker"]) < 2 * MIN_EVENTS:
            continue
        per_z[z] = p
    if not per_z:
        return None
    # split temporel commun : médiane des ts de la plus fine grille (z minimal = plus d'événements)
    z_ref = min(per_z)
    ts_all = np.sort(per_z[z_ref]["ts"])
    if len(ts_all) < 2 * MIN_EVENTS:
        return None
    cut = ts_all[int(len(ts_all) * train_frac)]
    best_z, best_sr = None, -1e18
    for z, p in per_z.items():
        tr = p["maker"][p["ts"] <= cut]
        tr = tr[np.isfinite(tr)]
        if len(tr) < MIN_EVENTS:
            continue
        sd = np.std(tr, ddof=1)
        sr = np.mean(tr) / sd if sd > 1e-12 else -1e18
        if sr > best_sr:
            best_sr, best_z = sr, z
    if best_z is None:
        return None
    p = per_z[best_z]
    oos = p["maker"][p["ts"] > cut]
    st = _stats(oos)
    return dict(z_star=best_z, oos_mean=st["mean"], oos_t=st["t_hac"], n_oos=st["n"])


def permutation_pvalue(loaded, gran, event, h, obs_series, sens, fee_maker_rt, n_perm=500, seed=0):
    """Null par RÉ-ÉCHANTILLONNAGE : tire n_obs rendements forward maker de barres ALÉATOIRES
    (même univers/TF/sens/frais) -> distribution du mean sous H0 « le timing du climax n'importe
    pas ». p = P(null_mean ≥ obs_mean). L'edge doit s'EFFONDRER (obs dans le null -> p ~0,5)."""
    rng = np.random.RandomState(seed)
    pool = []
    for sym, d in loaded.items():
        o = d["o"]; n = len(o)
        k = np.arange(0, n - 1 - h)
        if len(k) == 0:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            g = sens * (o[k + 1 + h] - o[k + 1]) / o[k + 1] * 1e4
        pool.append(g[np.isfinite(g)] - fee_maker_rt)
    if not pool:
        return None
    pool = np.concatenate(pool)
    n_obs = int(np.sum(np.isfinite(obs_series)))
    if n_obs < MIN_EVENTS or len(pool) < n_obs:
        return None
    obs_mean = float(np.mean(np.asarray(obs_series)[np.isfinite(obs_series)]))
    null_means = np.array([np.mean(rng.choice(pool, n_obs, replace=False)) for _ in range(n_perm)])
    p = float(np.mean(null_means >= obs_mean))
    return dict(obs_mean=obs_mean, null_mean=float(np.mean(null_means)),
                null_std=float(np.std(null_means)), p_value=p, n_perm=n_perm, n_obs=n_obs)


def positive_controls(loaded, fees):
    """(a) réversion 1h connue (gross, doit être DÉTECTABLE) : entrée long après barre baissière
    (< −1σ), rendement forward gross h=1 sur H1. (b) oracle synthétique (SANITY du harnais, peek
    NON-tradable) : signal = rendement forward + bruit -> t ÉNORME attendu. Prouve que le harnais
    sait détecter un vrai effet (cf. arXiv falsification, contrôles positifs t≈5,8)."""
    out = {}
    # (a) réversion 1h — gross, sans frais (on teste la DÉTECTION d'un effet connu)
    revvals = []
    for sym, d in loaded.items():
        c = d["c"]; o = d["o"]; n = len(c)
        if n < 60:
            continue
        ret = np.zeros(n)
        ret[1:] = (c[1:] - c[:-1]) / c[:-1]
        sd = np.std(ret[1:], ddof=1)
        sig = ret <= -1.0 * sd                       # barre nettement baissière
        idx = np.where(sig)[0]
        idx = idx[(idx + 2) < n]
        if len(idx) == 0:
            continue
        g = (o[idx + 2] - o[idx + 1]) / o[idx + 1] * 1e4   # long h=1, gross
        revvals.append(g[np.isfinite(g)])
    if revvals:
        rv = np.concatenate(revvals)
        st = _stats(rv)
        out["reversion_1h_gross"] = dict(mean_bps=st["mean"], t_hac=st["t_hac"], n=st["n"])
    # (b) oracle synthétique — peek CLAIREMENT non-tradable, pur test de câblage
    d = loaded.get("BTCUSDT") or next(iter(loaded.values()), None)
    if d is not None:
        o = d["o"]; n = len(o)
        k = np.arange(0, n - 2)
        fwd = (o[k + 2] - o[k + 1]) / o[k + 1] * 1e4
        rng = np.random.RandomState(0)
        signal = fwd + rng.randn(len(fwd)) * (np.std(fwd) + 1e-9)   # corrélé au futur (triche)
        sel = signal > np.median(signal)
        st = _stats(fwd[sel])
        out["oracle_peek_sanity"] = dict(mean_bps=st["mean"], t_hac=st["t_hac"], n=st["n"],
                                         note="peek NON-tradable — sanity harnais")
    return out


# ===================== RUN =====================
def run_all(use_live_fees=False, market="futures", n_perm=500, verbose=True):
    """Batterie complète : univers liquide × échelle TF × 4 événements × grille z, validation,
    gate pré-enregistré, verdict. Retourne le dict de résultats (aussi écrit dans RESULT)."""
    if not _HAS_AUDIT:
        return {"error": "audit_core indisponible", "verdict": "ABSTENTION (fail-safe)"}
    fees = resolve_fees(market=market, use_live=use_live_fees)
    grid = []                        # toutes les configs évaluées (poolées)
    per_tf = {}                      # meilleure config maker par TF (cohérence)
    sr_trials = []                   # Sharpe maker par config -> DSR
    loaded_by_gran = {}

    for gran in GRANS:
        loaded = {}
        for sym in SYMBOLS:
            d = _load(sym, gran)
            if d is not None:
                loaded[sym] = d
        if not loaded:
            per_tf[gran] = {"note": "aucune data"}
            continue
        loaded_by_gran[gran] = loaded
        tf_best = None
        for event, sens in EVENTS.items():
            for h in H_GRID:
                for z in Z_GRID:
                    p = pool_forward(loaded, gran, event, h, z, fees)
                    if p is None:
                        continue
                    st_t = _stats(p["taker"])
                    st_m = _stats(p["maker"])
                    bh = benchmark_bh(loaded, gran, h, sens, 2.0 * fees["maker"])
                    row = dict(gran=gran, event=event, h=h, z=z, n=st_m["n"],
                               net_taker_bps=st_t["mean"], net_maker_bps=st_m["mean"],
                               t_hac_taker=st_t["t_hac"], t_hac_maker=st_m["t_hac"],
                               sr_maker=st_m["sr"], bh_maker_bps=bh,
                               alpha_maker_bps=(st_m["mean"] - bh)
                               if np.isfinite(bh) and np.isfinite(st_m["mean"]) else float("nan"))
                    grid.append(row)
                    if np.isfinite(st_m["sr"]) and st_m["n"] >= MIN_EVENTS:
                        sr_trials.append(st_m["sr"])
                        if tf_best is None or (st_m["sr"] > tf_best["sr_maker"]):
                            tf_best = row
        per_tf[gran] = tf_best if tf_best else {"note": "pas de config valide"}
        if verbose:
            b = per_tf[gran]
            if b and "sr_maker" in b:
                print(f"  [{gran}] best maker: {b['event']} h={b['h']} z={b['z']} "
                      f"net={b['net_maker_bps']:.2f}bps t_HAC={b['t_hac_maker']:.2f} "
                      f"sr={b['sr_maker']:.3f} n={b['n']} (taker net={b['net_taker_bps']:.2f})")

    # config gagnante GLOBALE (max Sharpe maker). On EXIGE n≥ROBUST_N pour la tête d'affiche
    # du gate ; le pic sur-appris à petit n est conservé À PART (transparence, pas au gate).
    valid = [r for r in grid if np.isfinite(r["sr_maker"]) and r["n"] >= MIN_EVENTS]
    if not valid:
        res = {"error": "aucune config valide (data trop courte)", "fees": fees,
               "verdict": "ABSTENTION"}
        _write(res)
        return res
    outlier = max(valid, key=lambda r: r["sr_maker"])           # max Sharpe brut (peut être n=20)
    robust = [r for r in valid if r["n"] >= ROBUST_N]
    best = max(robust, key=lambda r: r["sr_maker"]) if robust else outlier
    # config la PLUS SIGNIFICATIVE (max |t_HAC| maker) parmi n≥ROBUST_N — informative pour le DSR
    best_by_t = max(robust, key=lambda r: abs(r["t_hac_maker"])
                    if np.isfinite(r["t_hac_maker"]) else -1.0) if robust else None

    # Deflated Sharpe sur la config gagnante, déflaté par N_TRIALS (search space complet)
    dsr = None
    loaded = loaded_by_gran.get(best["gran"], {})
    pb = pool_forward(loaded, best["gran"], best["event"], best["h"], best["z"], fees)
    if pb is not None and len(pb["maker"]) >= MIN_EVENTS and len(sr_trials) > 1:
        try:
            ds = ac.deflated_sharpe(pb["maker"], sr_trials=np.array(sr_trials), n_trials=N_TRIALS)
            if ds is not None:
                dsr = {k: float(v) for k, v in ds.items()}
        except Exception:
            dsr = None

    # DSR de la config la PLUS SIGNIFICATIVE (max |t_HAC|) — montre que même le t≥3 mid-TF
    # ne survit PAS à la déflation par 480 essais (le vrai test anti-sur-testing).
    dsr_by_t = None
    if best_by_t is not None:
        ld2 = loaded_by_gran.get(best_by_t["gran"], {})
        pt = pool_forward(ld2, best_by_t["gran"], best_by_t["event"],
                          best_by_t["h"], best_by_t["z"], fees)
        if pt is not None and len(pt["maker"]) >= MIN_EVENTS and len(sr_trials) > 1:
            try:
                d2 = ac.deflated_sharpe(pt["maker"], sr_trials=np.array(sr_trials),
                                        n_trials=N_TRIALS)
                if d2 is not None:
                    dsr_by_t = {k: float(v) for k, v in d2.items()}
            except Exception:
                dsr_by_t = None

    # walk-forward OOS sur la famille (event,h) gagnante
    wf = walk_forward_oos(loaded, best["gran"], best["event"], best["h"], fees)

    # permutation / shuffle sur la config gagnante (maker)
    perm = None
    if pb is not None:
        perm = permutation_pvalue(loaded, best["gran"], best["event"], best["h"],
                                  pb["maker"], EVENTS[best["event"]], 2.0 * fees["maker"],
                                  n_perm=n_perm)

    # contrôles positifs (réversion 1h gross + oracle) sur H1
    controls = {}
    if "1H" in loaded_by_gran:
        controls = positive_controls(loaded_by_gran["1H"], fees)

    # cohérence : ≥2 TF ADJACENTS où la famille gagnante est net>0 & t_HAC≥3 (maker)
    win_family = best["event"]
    tf_pass = []
    for gran in GRANS:
        rows = [r for r in grid if r["gran"] == gran and r["event"] == win_family
                and r["n"] >= MIN_EVENTS]
        ok = any((np.isfinite(r["net_maker_bps"]) and r["net_maker_bps"] > 0
                  and np.isfinite(r["t_hac_maker"]) and r["t_hac_maker"] >= 3.0) for r in rows)
        tf_pass.append(ok)
    adj_ok = any(tf_pass[i] and tf_pass[i + 1] for i in range(len(tf_pass) - 1))

    # ===== GATE pré-enregistré =====
    net_oos_pos = bool(wf and np.isfinite(wf["oos_mean"]) and wf["oos_mean"] > 0)
    t_ok = bool(np.isfinite(best["t_hac_maker"]) and best["t_hac_maker"] >= 3.0)
    dsr_ok = bool(dsr and np.isfinite(dsr.get("dsr", float("nan"))) and dsr["dsr"] >= 0.95)
    bh_ok = bool(np.isfinite(best.get("alpha_maker_bps", float("nan")))
                 and best["alpha_maker_bps"] > 0)
    gate = {"net_oos_positif": net_oos_pos, "t_hac>=3": t_ok, "dsr>=0.95": dsr_ok,
            "coherent_2TF_adjacents": adj_ok, "bat_buy_and_hold": bh_ok}
    passed = all(gate.values())
    verdict = ("TRADABLE (à confirmer réel)" if passed
               else "réel-non-tradable (climax de volume fee-killed / non robuste)")

    res = {"ts": int(time.time()), "market": market, "fees_bps": fees, "n_trials": N_TRIALS,
           "universe": SYMBOLS, "grans": GRANS, "h_grid": H_GRID, "z_grid": Z_GRID,
           "params": {"N": N_BASE, "M": M_SPRING, "range_pctl": RANGE_PCTL,
                      "clv_long": CLV_LONG, "clv_short": CLV_SHORT},
           "best": best, "best_by_t_hac": best_by_t, "small_sample_outlier": outlier,
           "deflated_sharpe": dsr, "deflated_sharpe_best_t": dsr_by_t,
           "walk_forward_oos": wf,
           "permutation": perm, "positive_controls": controls,
           "per_tf_best": per_tf, "coherence_tf_pass": dict(zip(GRANS, tf_pass)),
           "gate": gate, "gate_passed": passed, "verdict": verdict,
           "grid_size": len(grid)}
    _write(res)
    if verbose:
        _print_verdict(res)
    return res


def run_one(sym, gran=None, use_live_fees=False, market="futures"):
    """1 symbole détaillé : grille events×h×z (z primaire mis en avant). Consultation lisible."""
    if not _HAS_AUDIT:
        print("audit_core indisponible — ABSTENTION (fail-safe).")
        return None
    fees = resolve_fees(market=market, use_live=use_live_fees)
    grans = [gran] if gran else GRANS
    print(f"=== wyckoff_lab --run {sym} (frais {market} taker={fees['taker']} "
          f"maker={fees['maker']} bps/côté) ===")
    rows = []
    for g in grans:
        d = _load(sym, g)
        if d is None:
            print(f"  [{g}] data insuffisante")
            continue
        loaded = {sym: d}
        for event, sens in EVENTS.items():
            for h in H_GRID:
                p = pool_forward(loaded, g, event, h, Z_PRIMARY, fees)
                if p is None:
                    continue
                st_m = _stats(p["maker"]); st_t = _stats(p["taker"])
                rows.append((g, event, h, st_m["n"], st_t["mean"], st_m["mean"], st_m["t_hac"]))
        for r in [x for x in rows if x[0] == g]:
            g_, ev, h, nn, nt, nm, t = r
            if nn:
                print(f"  [{g_}] {ev:15s} h={h:<2} n={nn:<4} "
                      f"net_taker={nt:7.2f} net_maker={nm:7.2f} t_HAC={t:6.2f}")
    print("Lecture seule, aucun ordre. VERDICT: SAFE")
    return rows


def status(sym=None):
    """Consultation légère : config + disponibilité data. Aucun calcul lourd."""
    print("=== wyckoff_lab --status (labo climax de volume — SAFE, défaut OFF) ===")
    print(f"audit_core (HAC/DSR) importé : {_HAS_AUDIT}")
    print(f"univers liquide : {', '.join(SYMBOLS)}")
    print(f"échelle TF      : {', '.join(GRANS)}  (ERR-001)")
    print(f"horizons h      : {H_GRID}   seuils z : {Z_GRID}   N_trials(DSR) : {N_TRIALS}")
    print(f"params event    : N={N_BASE} M={M_SPRING} range_pctl={RANGE_PCTL} "
          f"CLV long≥{CLV_LONG} short≤{CLV_SHORT}")
    fees = resolve_fees("futures")
    print(f"frais futures   : taker {fees['taker']} / maker {fees['maker']} bps/côté (défauts)")
    syms = [sym] if sym else SYMBOLS[:3]
    if _HAS_AUDIT:
        print("disponibilité data (bougies par TF) :")
        for s in syms:
            avail = []
            for g in GRANS:
                d = _load(s, g)
                avail.append(f"{g}:{d['n_dedup'] if d else 0}")
            print(f"  {s:9s} " + "  ".join(avail))
    if RESULT.exists():
        try:
            prev = json.loads(RESULT.read_text())
            print(f"dernier verdict : {prev.get('verdict')} "
                  f"(gate_passed={prev.get('gate_passed')})")
        except Exception:
            pass
    print("Lecture seule, aucun ordre, défaut OFF. VERDICT: SAFE")


def _write(res):
    try:
        RESULT.write_text(json.dumps(res, default=float), encoding="utf-8")
    except Exception:
        pass


def _print_verdict(res):
    print("\n=== VERDICT WYCKOFF-LAB (climax de volume) ===")
    b = res["best"]
    print(f"config gagnante (max Sharpe maker) : {b['event']} {b['gran']} h={b['h']} z={b['z']}")
    print(f"  net maker {b['net_maker_bps']:.2f} bps | net taker {b['net_taker_bps']:.2f} bps "
          f"| t_HAC {b['t_hac_maker']:.2f} | n={b['n']} | alpha vs B&H {b.get('alpha_maker_bps'):.2f}")
    ds = res.get("deflated_sharpe")
    if ds:
        print(f"  Deflated Sharpe : DSR={ds['dsr']:.3f} (seuil 0,95 ; SR0={ds['sr0']:.4f} "
              f"var_sr={ds['var_sr']:.5f} N_trials={ds['n_trials']})")
    bt = res.get("best_by_t_hac"); dbt = res.get("deflated_sharpe_best_t")
    if bt and dbt:
        print(f"  plus significatif (n≥{ROBUST_N}) : {bt['event']} {bt['gran']} h={bt['h']} "
              f"z={bt['z']} net_maker={bt['net_maker_bps']:.2f} t_HAC={bt['t_hac_maker']:.2f} "
              f"n={bt['n']} -> DSR={dbt['dsr']:.3f} (<0,95 = tué par la déflation)")
    ol = res.get("small_sample_outlier")
    if ol and ol is not res.get("best"):
        print(f"  pic sur-appris (n={ol['n']}, HORS gate) : {ol['event']} {ol['gran']} "
              f"h={ol['h']} net_maker={ol['net_maker_bps']:.1f}bps sr={ol['sr_maker']:.3f}")
    wf = res.get("walk_forward_oos")
    if wf:
        print(f"  walk-forward OOS : z*={wf['z_star']} net_OOS={wf['oos_mean']:.2f} bps "
              f"t_OOS={wf['oos_t']:.2f} n_OOS={wf['n_oos']}")
    pm = res.get("permutation")
    if pm:
        print(f"  permutation/shuffle : obs={pm['obs_mean']:.2f} null={pm['null_mean']:.2f}"
              f"±{pm['null_std']:.2f} p={pm['p_value']:.3f} (edge doit s'effondrer -> p~0,5)")
    pc = res.get("positive_controls", {})
    if "reversion_1h_gross" in pc:
        r = pc["reversion_1h_gross"]
        print(f"  contrôle+ réversion 1h (gross) : {r['mean_bps']:.2f} bps t_HAC={r['t_hac']:.2f} "
              f"n={r['n']}")
    if "oracle_peek_sanity" in pc:
        r = pc["oracle_peek_sanity"]
        print(f"  contrôle+ oracle (sanity peek) : t_HAC={r['t_hac']:.1f} (doit être ÉNORME)")
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
        sym = rest[0] if rest else "BTCUSDT"
        gran = rest[1] if len(rest) > 1 else None
        run_one(sym, gran, use_live_fees=live)
    elif args[0] == "--run-all":
        print("=== wyckoff_lab --run-all (univers × échelle TF, validation stricte) ===")
        run_all(use_live_fees=live)
    else:
        print("usage: --status | --run SYMBOL [GRAN] | --run-all   [--live-fees]")


if __name__ == "__main__":
    main()
