"""Probe labo ISOLÉ (venv .venv/) — teste NHITS + AutoETS (Darts/statsforecast)
contre un baseline naïf, en walk-forward causal, sur l'échelle TF complète.

But : mesurer si un forecast de série de prix produit un edge DIRECTIONNEL
tradeable NET DE FRAIS. Verdict rendu par evaluate.py (Python système).

ISOLATION (ERR-004) : ce fichier tourne UNIQUEMENT dans scratchpad/openbb_forecast_lab/.venv
(Darts épingle sklearn ~1.3 ; le bot tourne sklearn 1.9 — jamais mélanger).
Il ne lit que data_history/*.json (bougies réelles, lecture seule), n'importe RIEN du bot.

Sortie : preds/{SYM}_{TF}_h{H}.json = pour chaque modèle, liste d'origines NON
chevauchantes {i (index barre), pred_ret, real_ret}. L'évaluation (IC, PnL net,
t-stat sur plis purgés) est faite séparément par evaluate.py.

Usage (dans le venv) :
    .venv/bin/python forecast_probe.py [--smoke]   # --smoke = 1 seul (SYM,TF,H)
"""
from __future__ import annotations

import json
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

LAB = Path(__file__).resolve().parent
DATA = LAB.parents[1] / "data_history"          # bougies réelles du bot (racine dépôt)
OUT = LAB / "preds"
OUT.mkdir(exist_ok=True)

# Échelle TF COMPLÈTE (ERR-001) — noms de fichiers tels que candles_history les écrit.
TFS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]
# Panier DIVERSIFIÉ ~21 (6 classes décorrélées) — probe élargi §OpenBB.
SYMBOLS = [
    "BTCUSDT", "ETHUSDT",                                   # crypto majeurs
    "SOLUSDT", "XRPUSDT", "BNBUSDT", "TRXUSDT", "ADAUSDT",  # L1/alt
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT",                     # memecoins
    "LINKUSDT", "UNIUSDT",                                  # DeFi/infra
    "XAUUSDT", "XAGUSDT",                                   # métaux
    "AAPLUSDT", "TSLAUSDT", "NVDAUSDT", "SPYUSDT",          # actions US
    "QQQUSDT", "COINUSDT", "MSTRUSDT",
]
HORIZONS = [1]                                  # h1 d'abord (h4 ensuite si edge)

CAP_BARS = 15000        # borne dure sur les barres gardées (les plus récentes) — LOGUÉ
N_ORIGINS = 250         # cible d'origines de test NON chevauchantes par (SYM,TF,H)
TRAIN_FRAC = 0.6        # part initiale pour l'entraînement NHITS


def load_closes(sym, tf):
    """Closes réelles triées (colonne 4 = close). [] si absent/court."""
    f = DATA / f"{sym}_{tf}.json"
    try:
        rows = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    rows = sorted(rows, key=lambda r: r[0])
    cl = np.array([float(r[4]) for r in rows], dtype=float)
    cl = cl[cl > 0]
    return cl


def run_one(sym, tf, H, log):
    from darts import TimeSeries
    from darts.dataprocessing.transformers import Scaler
    from darts.models import AutoETS, NHiTSModel, NaiveDrift

    cl = load_closes(sym, tf)
    if cl is None:
        log(f"  {sym} {tf} h{H} : fichier absent -> skip")
        return None
    n_all = len(cl)
    if n_all > CAP_BARS:
        cl = cl[-CAP_BARS:]
        log(f"  {sym} {tf} h{H} : {n_all} barres -> CAP {CAP_BARS} (les plus récentes)")
    n = len(cl)
    lookback = min(64, max(16, n // 20))
    need = lookback + H + 40
    if n < need:
        log(f"  {sym} {tf} h{H} : {n} barres < {need} requis -> skip")
        return None

    logp = np.log(cl)
    series = TimeSeries.from_values(logp.reshape(-1, 1))
    split = int(n * TRAIN_FRAC)
    if split < lookback + 30 or (n - split) < 3 * H + lookback:
        log(f"  {sym} {tf} h{H} : split infaisable (n={n}) -> skip")
        return None

    # Origines de test NON chevauchantes (espacées d'au moins H barres).
    n_test = n - split
    stride = max(H, n_test // N_ORIGINS)
    start_idx = split

    sc = Scaler()
    train_ts = series[:split]
    train_sc = sc.fit_transform(train_ts)
    full_sc = sc.transform(series)

    res = {"meta": {"sym": sym, "tf": tf, "H": H, "n": n, "lookback": lookback,
                    "split": split, "stride": stride, "n_all_before_cap": n_all},
           "models": {}}

    # ---- NHITS : entraîné UNE fois sur train, puis walk-forward SANS retrain (causal).
    t0 = time.perf_counter()
    try:
        nhits = NHiTSModel(
            input_chunk_length=lookback, output_chunk_length=H,
            num_stacks=2, num_blocks=1, num_layers=2, layer_widths=64,
            n_epochs=30, batch_size=64, random_state=7,
            pl_trainer_kwargs={"accelerator": "cpu", "enable_progress_bar": False,
                               "enable_model_summary": False, "logger": False})
        nhits.fit(train_sc)
        hf = nhits.historical_forecasts(
            full_sc, start=start_idx, forecast_horizon=H, stride=stride,
            retrain=False, last_points_only=True, verbose=False, show_warnings=False)
        res["models"]["nhits"] = _collect(hf, sc, series, H, logp)
        log(f"  {sym} {tf} h{H} : NHITS ok ({len(res['models']['nhits'])} orig, "
            f"{time.perf_counter()-t0:.0f}s)")
    except Exception as e:
        log(f"  {sym} {tf} h{H} : NHITS ÉCHEC {type(e).__name__}: {str(e)[:120]}")

    # ---- AutoETS : réajusté à chaque origine (rapide).
    t0 = time.perf_counter()
    try:
        ets = AutoETS(season_length=1)
        hf = ets.historical_forecasts(
            series, start=start_idx, forecast_horizon=H, stride=stride,
            retrain=True, last_points_only=True, verbose=False, show_warnings=False)
        res["models"]["autoets"] = _collect(hf, None, series, H, logp)
        log(f"  {sym} {tf} h{H} : AutoETS ok ({len(res['models']['autoets'])} orig, "
            f"{time.perf_counter()-t0:.0f}s)")
    except Exception as e:
        log(f"  {sym} {tf} h{H} : AutoETS ÉCHEC {type(e).__name__}: {str(e)[:120]}")

    # ---- Baseline NaiveDrift (référence à battre).
    try:
        nd = NaiveDrift()
        hf = nd.historical_forecasts(
            series, start=start_idx, forecast_horizon=H, stride=stride,
            retrain=True, last_points_only=True, verbose=False, show_warnings=False)
        res["models"]["naive"] = _collect(hf, None, series, H, logp)
    except Exception as e:
        log(f"  {sym} {tf} h{H} : Naive ÉCHEC {type(e).__name__}: {str(e)[:120]}")

    if not res["models"]:
        return None
    (OUT / f"{sym}_{tf}_h{H}.json").write_text(json.dumps(res))
    return res


def _collect(hf, scaler, series_logp, H, logp):
    """hf = série des prévisions (dernier point). Reconstruit par origine :
    pred_ret = pred_logp[i+H] - logp[i] ; real_ret = logp[i+H] - logp[i].
    i = index barre de l'ORIGINE (dernier point connu avant la prévision)."""
    if scaler is not None:
        hf = scaler.inverse_transform(hf)
    vals = hf.values().reshape(-1)
    times = [t for t in hf.time_index]           # positions RangeIndex = i+H
    out = []
    for k, tpos in enumerate(times):
        j = int(tpos)                            # index barre de la prévision (i+H)
        i = j - H
        if i < 0 or j >= len(logp):
            continue
        pred_logp_j = float(vals[k])
        out.append({"i": i,
                    "pred_ret": pred_logp_j - float(logp[i]),
                    "real_ret": float(logp[j]) - float(logp[i])})
    return out


def main():
    smoke = "--smoke" in sys.argv
    log_path = LAB / ("smoke.log" if smoke else "probe.log")
    fh = log_path.open("w", encoding="utf-8")

    def log(m):
        print(m, flush=True)
        fh.write(m + "\n"); fh.flush()

    log(f"== probe forecast {'SMOKE' if smoke else 'COMPLET'} — {time.strftime('%Y-%m-%d %H:%M')} ==")
    jobs = ([("BTCUSDT", "1H", 1)] if smoke
            else [(s, tf, H) for s in SYMBOLS for tf in TFS for H in HORIZONS])
    done = 0
    for sym, tf, H in jobs:
        try:
            if run_one(sym, tf, H, log) is not None:
                done += 1
        except Exception as e:
            log(f"  {sym} {tf} h{H} : ERREUR {type(e).__name__}: {str(e)[:140]}")
    log(f"== terminé : {done}/{len(jobs)} (SYM,TF,H) écrits -> preds/ ==")
    fh.close()


if __name__ == "__main__":
    main()
