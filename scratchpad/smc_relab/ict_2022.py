"""
ict_2022.py — RÉ-TEST du modèle ICT 2022 (top-down + NY killzone equity-overlap).

Classement : SCRATCHPAD / LECTURE SEULE / AUCUN ordre. Re-test d'une idée REJETÉE
(prior fortement négatif, cf. VERDICTS.md « SMC / ICT »). N'est PAS un module repo,
n'est PAS dans tests_audit. Ne modifie rien hors scratchpad/smc_relab/.

Modèle mesuré (UNE variante, la seule jamais testée) :
  - BIAIS HTF : D1 + 4H via bos_choch(swing=50) + premium/discount (equilibrium 0.5).
  - ENTRÉE LTF : 15m, MACHINE À ÉTATS CAUSALE : sweep de liquidité -> MSS (CHoCH +
    displacement FVG) -> retest FVG -> entrée, UNIQUEMENT si aligné au biais HTF.
  - CONFLUENCE : FVG ∩ OB (proxy Unicorn) ET retracement OTE 0.62-0.79.
  - FILTRE SESSION : NY equity-overlap 8h30-11h ET = 13:30-16:00 UTC (option Silver
    Bullet 10-11 ET = 14:00-15:00 UTC). PAS de killzone Londres/forex (24/7 crypto).
  - STOP structurel (sous le sweep) ; T1 = extrême opposé du range LTF (-> break-even),
    T2 = extension 0.62 ; gestion 50/50.

Anti-look-ahead (CRITIQUE) :
  - swing_highs_lows regarde `swing` bougies APRÈS le pivot -> un pivot en i n'est
    CONNU qu'en i+swing. On n'utilise donc chaque évènement qu'à partir de son bar
    `available_at`. bos_choch : available = max(BrokenIndex, pivot+swing). FVG : i+1.
  - On n'utilise JAMAIS MitigatedIndex/BrokenIndex/Swept/End comme feature à l'instant t
    (indices FUTURS) — BrokenIndex ne sert QU'À dater l'`available_at` (bar où l'info
    devient réelle, on agit à/après ce bar).
  - HTF -> LTF mappé par timestamp de CLÔTURE (open_ts + durée) pour ne consommer une
    bougie HTF qu'une fois fermée. Vérifié par troncature (causality_check.py).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("SMC_CREDIT", "0")
from smartmoneyconcepts import smc  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data_history"

TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
         "1H": 3_600_000, "4H": 14_400_000, "1D": 86_400_000, "1W": 604_800_000}

# Marge de STABILISATION des swings : swing_highs_lows de la lib est STATEFUL
# (alternance high/low) -> un pivot peut être RECLASSÉ tardivement quand de nouvelles
# barres arrivent (micro look-ahead ~0.03% à lag=swing, cf. causality_check.py). On ne
# fait CONFIANCE à un pivot qu'après swing·(1+STAB_MULT) barres -> taux résiduel ~0.004%.
STAB_MULT = 2


def _stab(swing: int) -> int:
    return int(swing * STAB_MULT)


# ----------------------------------------------------------------------------- data
def load_df(sym: str, tf: str) -> pd.DataFrame | None:
    """Bougies disque -> DataFrame open/high/low/close/volume, index datetime UTC
    (index = open time). None si absent. `ts` (open ms) conservé en colonne."""
    f = DATA / f"{sym.upper()}_{tf}.json"
    if not f.exists():
        return None
    rows = json.loads(f.read_text())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df


# ------------------------------------------------------------------ HTF bias timeline
def _confirmed_swing_levels(df: pd.DataFrame, swing: int):
    """Renvoie deux arrays alignés sur df : last_conf_high[j], last_conf_low[j] =
    dernier niveau de swing haut/bas CONFIRMÉ (pivot connu = pivot+swing <= j). NaN
    tant qu'aucun swing confirmé. Causal."""
    shl = smc.swing_highs_lows(df, swing_length=swing)
    hl = shl["HighLow"].to_numpy()
    lvl = shl["Level"].to_numpy()
    n = len(df)
    hi = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    # évènements (pivot p) -> disponibles à p+swing
    events = []  # (avail_bar, type, level)
    lag = swing + _stab(swing)
    for p in range(n):
        if not np.isnan(hl[p]) and hl[p] != 0:
            events.append((p + lag, int(hl[p]), float(lvl[p])))
    events.sort()
    cur_hi = np.nan
    cur_lo = np.nan
    ei = 0
    for j in range(n):
        while ei < len(events) and events[ei][0] <= j:
            _, typ, level = events[ei]
            if typ == 1:
                cur_hi = level
            elif typ == -1:
                cur_lo = level
            ei += 1
        hi[j] = cur_hi
        lo[j] = cur_lo
    return hi, lo


def htf_state(df: pd.DataFrame, swing: int, tf: str):
    """Biais structurel causal + equilibrium par bar HTF. Renvoie DataFrame indexé
    par TIMESTAMP DE CLÔTURE (open_ts + durée TF) avec colonnes bias(+1/-1/0),
    mid, close. Le timestamp de clôture garantit qu'une bougie HTF n'est consommée
    qu'une fois FERMÉE côté LTF."""
    n = len(df)
    shl = smc.swing_highs_lows(df, swing_length=swing)
    bc = smc.bos_choch(df, shl)
    bos = bc["BOS"].to_numpy()
    choch = bc["CHOCH"].to_numpy()
    broken = bc["BrokenIndex"].to_numpy()
    # évènements de structure -> available = max(BrokenIndex, pivot+swing)
    ev = []
    for p in range(n):
        d = 0
        if not np.isnan(bos[p]) and bos[p] != 0:
            d = int(bos[p])
        elif not np.isnan(choch[p]) and choch[p] != 0:
            d = int(choch[p])
        if d == 0:
            continue
        b = broken[p]
        lag = p + swing + _stab(swing)
        avail = lag if (b is None or (isinstance(b, float) and np.isnan(b))) else max(int(b), lag)
        if avail < n:
            ev.append((avail, d))
    ev.sort()
    bias = np.zeros(n, dtype=int)
    ei = 0
    cur = 0
    for j in range(n):
        while ei < len(ev) and ev[ei][0] <= j:
            cur = ev[ei][1]
            ei += 1
        bias[j] = cur
    hi, lo = _confirmed_swing_levels(df, swing)
    mid = (hi + lo) / 2.0
    close_ts = df["ts"].to_numpy() + TF_MS[tf]  # ms de CLÔTURE
    out = pd.DataFrame({"close_ts": close_ts, "bias": bias, "mid": mid,
                        "close": df["close"].to_numpy()})
    return out


def map_htf_to_ltf(ltf_ts_ms: np.ndarray, htf: pd.DataFrame):
    """Pour chaque bar LTF (open ms), renvoie (bias, mid) de la dernière bougie HTF
    déjà FERMÉE (close_ts <= ltf open). searchsorted, causal."""
    cts = htf["close_ts"].to_numpy()
    idx = np.searchsorted(cts, ltf_ts_ms, side="right") - 1
    bias = np.zeros(len(ltf_ts_ms), dtype=int)
    mid = np.full(len(ltf_ts_ms), np.nan)
    ok = idx >= 0
    bias[ok] = htf["bias"].to_numpy()[idx[ok]]
    mid[ok] = htf["mid"].to_numpy()[idx[ok]]
    return bias, mid


# ------------------------------------------------------------------- LTF SMC features
def ltf_features(df: pd.DataFrame, ltf_swing: int):
    """Calcule une fois les features SMC LTF + leurs `available_at`. Renvoie un dict
    d'arrays exploitables causalement par la machine à états."""
    n = len(df)
    shl = smc.swing_highs_lows(df, swing_length=ltf_swing)
    hl = shl["HighLow"].to_numpy()
    lvl = shl["Level"].to_numpy()
    bc = smc.bos_choch(df, shl)
    choch = bc["CHOCH"].to_numpy()
    bos = bc["BOS"].to_numpy()
    bclvl = bc["Level"].to_numpy()
    broken = bc["BrokenIndex"].to_numpy()
    fvg = smc.fvg(df)
    fv = fvg["FVG"].to_numpy()
    ftop = fvg["Top"].to_numpy()
    fbot = fvg["Bottom"].to_numpy()
    ob = smc.ob(df, shl)
    obv = ob["OB"].to_numpy()
    otop = ob["Top"].to_numpy()
    obot = ob["Bottom"].to_numpy()

    # swings confirmés (pivot+swing+stab) : listes triées par available
    conf_low = []   # (avail, level)
    conf_high = []
    lag = ltf_swing + _stab(ltf_swing)
    for p in range(n):
        if np.isnan(hl[p]) or hl[p] == 0:
            continue
        if hl[p] == -1:
            conf_low.append((p + lag, float(lvl[p])))
        else:
            conf_high.append((p + lag, float(lvl[p])))

    # CHoCH/BOS structurels : (avail, dir, level_broken)
    mss = []
    for p in range(n):
        d = 0
        if not np.isnan(choch[p]) and choch[p] != 0:
            d = int(choch[p])
        elif not np.isnan(bos[p]) and bos[p] != 0:
            d = int(bos[p])
        if d == 0:
            continue
        b = broken[p]
        if b is None or (isinstance(b, float) and np.isnan(b)):
            avail = p + lag
        else:
            avail = max(int(b), p + lag)
        if avail < n:
            mss.append((avail, d, float(bclvl[p])))
    mss.sort()

    # FVG : (avail=i+1, dir, top, bottom)
    fvgs = []
    for i in range(n):
        if np.isnan(fv[i]) or fv[i] == 0:
            continue
        av = i + 1
        if av < n:
            fvgs.append((av, int(fv[i]), float(ftop[i]), float(fbot[i])))
    fvgs.sort()

    # OB : (avail=pivot+swing approx via index i, dir, top, bottom). L'OB de la lib est
    # posé à l'index du pivot -> on le rend dispo à i+ltf_swing (conservateur).
    obs = []
    for i in range(n):
        if np.isnan(obv[i]) or obv[i] == 0:
            continue
        av = i + lag
        if av < n:
            obs.append((av, int(obv[i]), float(otop[i]), float(obot[i])))
    obs.sort()

    return dict(conf_low=conf_low, conf_high=conf_high, mss=mss, fvgs=fvgs, obs=obs)


# ------------------------------------------------------------------------- state machine
@dataclass
class Cfg:
    require_ob: bool = True
    require_ote: bool = True
    require_discount: bool = True
    session: str = "ny"          # "ny" (13:30-16:00 UTC) | "silver" (14:00-15:00 UTC)
    align_d1: bool = True
    htf_swing: int = 50
    ltf_swing: int = 10
    sweep_lb: int = 24           # fenêtre sweep avant le MSS (bars 15m)
    mss_window: int = 16         # âge max du MSS avant le signal (bars)
    entry_valid: int = 24        # validité de l'ordre limit au repos (bars = 6 h)
    max_hold: int = 96           # durée max de portage (bars 15m = 24 h)
    ote_lo: float = 0.62
    ote_hi: float = 0.79


def _session_mask(df: pd.DataFrame, session: str) -> np.ndarray:
    """Masque des bougies dans la fenêtre NY equity-overlap (UTC). On travaille en
    UTC (les données sont en UTC) ; 8h30-11h ET = 13:30-16:00 UTC en heure d'été (EDT),
    12:30-15:00 en heure d'hiver (EST). La lib `sessions` ne gère pas le DST -> on
    calcule le décalage ET nous-mêmes via l'heure locale America/New_York (gère le DST)."""
    if session == "all":                   # CONTRÔLE : pas de filtre session (24/7)
        return np.ones(len(df), dtype=bool)
    ts = df.index.tz_convert("America/New_York")
    minute = ts.hour * 60 + ts.minute
    if session == "silver":
        lo, hi = 10 * 60, 11 * 60          # 10:00-11:00 ET (macro Silver Bullet)
    else:
        lo, hi = 8 * 60 + 30, 11 * 60      # 08:30-11:00 ET (equity overlap)
    return (minute >= lo) & (minute < hi)


def simulate(sym: str, feats: dict, df15: pd.DataFrame, bias15: np.ndarray,
             mid15: np.ndarray, biasD1: np.ndarray, cfg: Cfg, funnel: dict | None = None):
    """Machine à états causale -> liste de trades (dicts). AUCUN ordre : pur backtest.
    Si `funnel` (dict) est fourni, incrémente les compteurs d'entonnoir par stage."""
    def _f(stage):
        if funnel is not None:
            funnel[stage] = funnel.get(stage, 0) + 1
    n = len(df15)
    high = df15["high"].to_numpy()
    low = df15["low"].to_numpy()
    close = df15["close"].to_numpy()
    sess = _session_mask(df15, cfg.session)

    conf_low = feats["conf_low"]
    conf_high = feats["conf_high"]
    mss = feats["mss"]
    fvgs = feats["fvgs"]
    obs = feats["obs"]

    def last_before(lst, t, direction=None):
        """Dernier (avail,dir,...) de lst avec avail<=t (et dir si fourni)."""
        out = None
        for e in lst:
            if e[0] > t:
                break
            if direction is None or e[1] == direction:
                out = e
        return out

    def conf_level_before(lst, t):
        out = None
        for av, level in lst:
            if av > t:
                break
            out = level
        return out

    trades = []
    t = max(cfg.htf_swing, cfg.ltf_swing) + 2
    while t < n - 1:
        if not sess[t] or bias15[t] == 0 or np.isnan(mid15[t]):
            t += 1
            continue
        d = bias15[t]  # +1 long, -1 short
        _f("sess_bias")
        if cfg.align_d1 and biasD1[t] != d:
            t += 1
            continue
        _f("d1")
        if cfg.require_discount:
            if d == 1 and not (close[t] < mid15[t]):   # long exige discount HTF
                t += 1
                continue
            if d == -1 and not (close[t] > mid15[t]):   # short exige premium HTF
                t += 1
                continue
        _f("disc")

        # 1) MSS aligné, récent
        m = None
        for e in mss:
            if e[0] > t:
                break
            if e[1] == d and e[0] > t - cfg.mss_window:
                m = e
        if m is None:
            t += 1
            continue
        _f("mss")
        mss_avail, _, mss_level = m

        # 2) SWEEP de liquidité avant le MSS : liquidité opposée BALAYÉE (wick au-delà)
        #    puis RECLAIM (prix revenu du bon côté au moment du MSS). Faithful ICT.
        swept = None
        if d == 1:
            pool = conf_level_before(conf_low, mss_avail)  # liquidité SOUS le marché
            if pool is not None:
                lo_win = max(0, mss_avail - cfg.sweep_lb)
                seg = low[lo_win:mss_avail + 1]
                if seg.size and seg.min() < pool and close[mss_avail] > pool:
                    swept = float(seg.min())            # plancher du sweep
        else:
            pool = conf_level_before(conf_high, mss_avail)
            if pool is not None:
                lo_win = max(0, mss_avail - cfg.sweep_lb)
                seg = high[lo_win:mss_avail + 1]
                if seg.size and seg.max() > pool and close[mss_avail] < pool:
                    swept = float(seg.max())
        if swept is None:
            t += 1
            continue
        _f("sweep")

        # leg pour OTE / cibles : sweep (0%) -> extrême du MSS (100%)
        leg_lo = swept if d == 1 else mss_level
        leg_hi = mss_level if d == 1 else swept
        rng = leg_hi - leg_lo
        if rng <= 0:
            t += 1
            continue
        # bande OTE (discount/premium profond 0.62-0.79 du retracement)
        if d == 1:
            band_hi = leg_hi - cfg.ote_lo * rng
            band_lo = leg_hi - cfg.ote_hi * rng
        else:
            band_lo = leg_lo + cfg.ote_lo * rng
            band_hi = leg_lo + cfg.ote_hi * rng

        # 3) FVG d'entrée : dispo, sens du biais, formé après le sweep, dont la zone
        #    INTERSECTE l'OTE (= le FVG ICT d'entrée, pas juste le plus récent). Si
        #    OTE non exigée, on prend le FVG dispo le plus récent qui contient le prix.
        fvg_pick = None
        for av, fd, ftop, fbot in fvgs:
            if av > t:
                break
            if fd != d or av <= mss_avail - cfg.sweep_lb:
                continue
            if cfg.require_ote and (ftop < band_lo or fbot > band_hi):
                continue                                # zone FVG hors OTE
            fvg_pick = (av, fd, ftop, fbot)
        if fvg_pick is None:
            t += 1
            continue
        _f("fvg_ote")
        _, _, ftop, fbot = fvg_pick

        # 4) Confluence OB : le FVG chevauche un OB du même sens (avant de poser l'ordre)
        if cfg.require_ob:
            found = False
            for av, od, otop, obot in obs:
                if av > t:
                    break
                if od == d and not (otop < fbot or obot > ftop):
                    found = True
            if not found:
                t += 1
                continue
        _f("ob")

        # 5) ENTRÉE = ORDRE LIMIT AU REPOS au bord du FVG (modèle ICT : on pose le
        #    limit et on ATTEND le retest). Prix connu au bar de signal t (causal) ;
        #    le fill survient au 1er bar suivant qui touche le niveau, dans la
        #    fenêtre de validité. Découple fill/signal sans look-ahead.
        entry = ftop if d == 1 else fbot     # bord du gap touché en premier au retrace
        if d == 1:
            stop = swept * 0.999
            t1 = leg_hi                       # extrême opposé (BE)
            t2 = leg_hi + 0.62 * rng          # extension 0.62
        else:
            stop = swept * 1.001
            t1 = leg_lo
            t2 = leg_lo - 0.62 * rng
        risk = abs(entry - stop) / entry
        if not (0.001 <= risk <= 0.06):       # garde sanité (0.1%..6%)
            t += 1
            continue

        fill_bar = None
        vend = min(t + cfg.entry_valid, n - 1)
        for b in range(t + 1, vend + 1):
            if d == 1 and low[b] <= entry:
                fill_bar = b
                break
            if d == -1 and high[b] >= entry:
                fill_bar = b
                break
            # invalidation : le stop est atteint AVANT le fill -> setup mort
            if d == 1 and low[b] <= stop:
                break
            if d == -1 and high[b] >= stop:
                break
        if fill_bar is None:
            t += 1
            continue
        _f("retest")

        tr = _run_trade(sym, high, low, fill_bar, n, d, entry, stop, t1, t2, cfg, df15)
        if tr is not None:
            _f("trade")
            trades.append(tr)
            t = tr["exit_bar"] + 1            # pas de chevauchement
        else:
            t += 1
    return trades


def _run_trade(sym, high, low, t0, n, d, entry, stop, t1, t2, cfg, df15):
    """Simule un trade bracket 50/50 avec passage à BE après T1. Renvoie les gross
    par jambe + métadonnées. Frais appliqués en aval (net_returns)."""
    half_done = False
    be = False
    cur_stop = stop
    exit_bar = min(t0 + cfg.max_hold, n - 1)
    legs = []  # (frac, price, kind)  kind: 'tp'|'sl'|'time'
    end = min(t0 + cfg.max_hold, n - 1)
    for b in range(t0 + 1, end + 1):
        hi, lo = high[b], low[b]
        if d == 1:
            # stop d'abord (conservateur)
            if lo <= cur_stop:
                legs.append((1.0 if not half_done else 0.5, cur_stop,
                             "be" if be else "sl"))
                exit_bar = b
                break
            if not half_done and hi >= t1:
                legs.append((0.5, t1, "tp"))
                half_done = True
                be = True
                cur_stop = entry           # break-even
            if half_done and hi >= t2:
                legs.append((0.5, t2, "tp"))
                exit_bar = b
                break
        else:
            if hi >= cur_stop:
                legs.append((1.0 if not half_done else 0.5, cur_stop,
                             "be" if be else "sl"))
                exit_bar = b
                break
            if not half_done and lo <= t1:
                legs.append((0.5, t1, "tp"))
                half_done = True
                be = True
                cur_stop = entry
            if half_done and lo <= t2:
                legs.append((0.5, t2, "tp"))
                exit_bar = b
                break
    else:
        # fin de fenêtre : liquide le reliquat au close (time exit)
        frac = 1.0 if not half_done else 0.5
        legs.append((frac, df15["close"].to_numpy()[end], "time"))
        exit_bar = end
    if not legs:
        return None
    return dict(sym=sym, entry_bar=t0, exit_bar=exit_bar, dir=int(d),
                entry=float(entry), stop=float(stop), risk=abs(entry - stop) / entry,
                legs=legs, entry_ts=int(df15["ts"].to_numpy()[t0]))


# ------------------------------------------------------------------------------- fees
# Convention repo (mém. exec-fees-lever / fee_rates) : taker ~6 bps/côté, maker ~2 bps.
FEE = {
    "taker": dict(entry=6.0, tp=6.0, sl=6.0),        # tout taker
    "maker": dict(entry=2.0, tp=2.0, sl=6.0),        # entrée+TP post-only, stop taker (RÉALISTE)
    "maker_ideal": dict(entry=2.0, tp=2.0, sl=2.0),  # plafond optimiste (tout maker)
}


def net_return(tr: dict, scenario: str) -> float:
    """Rendement NET de frais du trade (fraction du notionnel), signé. 50/50."""
    f = FEE[scenario]
    d = tr["dir"]
    entry = tr["entry"]
    gross = 0.0
    fee = f["entry"] / 1e4                      # frais d'entrée sur le notionnel plein
    for frac, price, kind in tr["legs"]:
        gross += frac * ((price - entry) / entry) * d
        side = "tp" if kind == "tp" else ("sl" if kind in ("sl", "be", "time") else "sl")
        fee += frac * (f[side] / 1e4)
    return gross - fee


def net_R(tr: dict, scenario: str) -> float:
    return net_return(tr, scenario) / tr["risk"]
