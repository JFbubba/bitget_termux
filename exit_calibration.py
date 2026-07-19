"""
exit_calibration.py — calibration des SORTIES sur les trades PAPER (LECTURE SEULE). SAFE.

Question (§68/voie saine, étape B) : les sorties (SL 1.5·ATR / RR 2, conventions jamais
mesurées §60) saignent-elles le payoff ? Cet outil MESURE, sur les issues paper finalisées :
  1. le chemin de prix réel après chaque entrée (bougies PROFONDES rejouées, first-touch) ;
  2. la MFE/MAE (excursion max favorable/adverse) en unités de RISQUE (distance du stop) ;
  3. une RECHERCHE sur grille (SL·ATR × RR) du couple qui maximise l'espérance par trade,
     NETTE DE FRAIS (E = moyenne des résultats R − coût_frais_R par trade) ;
  4. la DÉFLATION du meilleur setup (Deflated Sharpe, Bailey & López de Prado) : la grille
     5×5=25 essais gonfle un « gagnant » même sans skill -> il doit battre se·√(2·ln N).

Acquis mesuré (§exit-calibration 18/07) : le SL n'est PAS trop serré (les trades morts au
SL ont une MFE médiane ~0,4R, ils partaient contre), monter le TP dégrade, et le LEVIER
reste les FRAIS (taker→maker bascule le profil du rouge au ~vert). ADVISORY PUR : ne change
AUCUN paramètre (le SL/TP réel reste décidé séparément via le mandat). Aucun ordre.

CLI : python exit_calibration.py [--hours 48] [--granularity 15m] [--max N] [--fee 10] [--write]
"""
import csv
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARTEFACT = ROOT / ".exit_calibration.json"

# Convention actuelle (à battre) : stop = 1.5·ATR, take-profit = RR·stop avec RR = 2.
CUR_SL_ATR = 1.5
CUR_RR = 2.0
SL_GRID = (1.0, 1.5, 2.0, 2.5, 3.0)     # multiples d'ATR pour le stop
RR_GRID = (1.0, 1.5, 2.0, 2.5, 3.0)     # ratio take-profit / stop
DEFAULT_FEE_BPS = 10.0                    # FALLBACK fail-safe A/R (si fee_rates indispo)


def _default_fee_bps():
    """Frais ALLER-RETOUR futures par défaut = borne haute (round-trip TAKER), lu du
    helper central `fee_rates` (taux LIVE du compte, pas de BGB en futures). FAIL-SAFE :
    DEFAULT_FEE_BPS en dur si fee_rates est indisponible. Reste surchargeable (--fee)."""
    try:
        import fee_rates
        return round(2.0 * float(fee_rates.futures_fee_bps()["taker"]), 4)
    except Exception:
        return DEFAULT_FEE_BPS


def _load_outcomes(max_rows=None):
    """Trades paper finalisés : {symbol, side, entry, stop, tp, ts}. `ts` en epoch."""
    import config
    p = Path(config.FINAL_OUTCOMES_FILE)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    out = []
    for r in csv.DictReader(p.open(encoding="utf-8", errors="ignore")):
        try:
            entry = float(r["entry"])
            stop = float(r["stop_loss"])
            ts = datetime.fromisoformat(r["signal_timestamp"]).timestamp()
        except (TypeError, ValueError, KeyError):
            continue
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        out.append({"symbol": (r.get("symbol") or "").upper(), "side": (r.get("side") or "").upper(),
                    "entry": entry, "stop": stop, "tp": float(r.get("take_profit") or 0),
                    "risk": risk, "atr": risk / CUR_SL_ATR, "ts": ts,
                    "outcome": r.get("outcome") or ""})
    if max_rows:
        out = out[-max_rows:]
    return out


def _symbol_candles(symbol, granularity, ts_min=None):
    """Bougies (ts_epoch, high, low) triées. PROFONDES d'abord (candles_history, cache disque
    + download si la couverture ne remonte pas jusqu'à ts_min), repli candle_reader (récent).
    La profondeur est indispensable : les issues finalisées datent de plusieurs semaines."""
    try:
        import candles_history as ch
        rows = ch.load(symbol, granularity)
        if ts_min is not None and (not rows or rows[0][0] / 1000.0 > ts_min):
            ch.download(symbol, granularity, jours=25, pause_s=0.05, max_pages=60)
            rows = ch.load(symbol, granularity)
        if rows:
            return [(r[0] / 1000.0, r[2], r[3]) for r in rows]   # (ts_epoch, high, low)
    except Exception:
        pass
    try:
        import candle_reader as cr
        cs = cr.get_bitget_candles(symbol, product_type="USDT-FUTURES",
                                   granularity=granularity, limit=1000)
        return [(c["time"].timestamp(), c["high"], c["low"]) for c in cs]
    except Exception:
        return []


def _path(candles, ts, hours):
    """Sous-chemin [ts, ts + hours] à partir des bougies pré-chargées du symbole."""
    fin = ts + hours * 3600
    return [(t, hi, lo) for (t, hi, lo) in candles if ts <= t <= fin]


def mfe_mae_R(entry, side, path, risk):
    """MFE/MAE en unités de RISQUE (distance du stop). PUR. (None, None) si pas de chemin."""
    if not path or risk <= 0:
        return None, None
    if side == "LONG":
        mfe = (max(hi for _, hi, _ in path) - entry) / risk
        mae = (entry - min(lo for _, _, lo in path)) / risk
    else:
        mfe = (entry - min(lo for _, _, lo in path)) / risk
        mae = (max(hi for _, hi, _ in path) - entry) / risk
    return mfe, mae


def simulate(entry, side, path, atr, sl_mult, rr):
    """First-touch : le prix touche-t-il TP (+rr·sl_mult·atr) ou SL (−sl_mult·atr) d'abord ?
    Renvoie 'TP', 'SL', ou None (ni l'un ni l'autre dans la fenêtre). PUR. Convention
    prudente : si une bougie touche les DEUX, on compte SL (pessimiste)."""
    sl_dist = sl_mult * atr
    tp_dist = rr * sl_dist
    if side == "LONG":
        sl_px, tp_px = entry - sl_dist, entry + tp_dist
        for _, hi, lo in path:
            if lo <= sl_px:
                return "SL"
            if hi >= tp_px:
                return "TP"
    else:
        sl_px, tp_px = entry + sl_dist, entry - tp_dist
        for _, hi, lo in path:
            if hi >= sl_px:
                return "SL"
            if lo <= tp_px:
                return "TP"
    return None


def grid_search(trades, paths, fee_bps=DEFAULT_FEE_BPS, sl_grid=SL_GRID, rr_grid=RR_GRID):
    """Pour chaque (sl_mult, rr), simule tous les trades et calcule l'espérance NETTE DE FRAIS
    par trade (moyenne des résultats R : +rr si TP, −1 si SL, moins le coût des frais en R),
    avec W et l'erreur-type (se). Le coût des frais en R = fee_rt·entry/(sl·atr) : un SL plus
    LARGE dilue les frais relatifs. Trié par espérance nette décroissante. PUR."""
    fee_rt = float(fee_bps) / 1e4
    results = []
    for sl in sl_grid:
        for rr in rr_grid:
            nets, won, lost = [], 0, 0
            for tr in trades:
                path = paths.get(id(tr))
                if not path or tr["atr"] <= 0:
                    continue
                res = simulate(tr["entry"], tr["side"], path, tr["atr"], sl, rr)
                if res is None:
                    continue                              # non résolu dans la fenêtre -> ignoré
                cost_r = fee_rt * tr["entry"] / (sl * tr["atr"])
                if res == "TP":
                    won += 1
                    nets.append(rr - cost_r)
                else:
                    lost += 1
                    nets.append(-1.0 - cost_r)
            n = won + lost
            if n < 20:
                continue
            E = statistics.fmean(nets)
            se = statistics.pstdev(nets) / (n ** 0.5) if n > 1 else 0.0
            results.append({"sl_atr": sl, "rr": rr, "W": round(won / n, 4),
                            "expectancy_R": round(E, 4), "se": round(se, 4), "n": n})
    results.sort(key=lambda x: -x["expectancy_R"])
    return results


def _deflate(best, n_trials):
    """Barre de déflation du meilleur setup (Deflated Sharpe sur n_trials cellules)."""
    import neural_net as nn
    bar = nn.deflation_bar(best.get("se", 0.0), n_trials)
    defl = round(best["expectancy_R"] - bar, 4)
    return {"deflation_bar": round(bar, 4), "deflated_R": defl, "robuste": bool(defl > 0)}


def run(hours=48, granularity="15m", max_rows=None, fee_bps=None):
    """Charge les trades, rejoue les chemins PROFONDS (1 série/symbole), calcule MFE/MAE +
    grille NETTE DE FRAIS + déflation du meilleur setup. `fee_bps=None` -> round-trip taker
    futures LIVE (fee_rates, fallback en dur), sinon la valeur fournie (--fee)."""
    fee_bps = _default_fee_bps() if fee_bps is None else float(fee_bps)
    trades = _load_outcomes(max_rows=max_rows)
    by_sym = {}
    for t in trades:
        by_sym.setdefault(t["symbol"], []).append(t["ts"])
    cache = {s: _symbol_candles(s, granularity, ts_min=min(ts)) for s, ts in by_sym.items()}
    paths, mfe_list, mae_list = {}, [], []
    for tr in trades:
        pth = _path(cache.get(tr["symbol"], []), tr["ts"], hours)
        paths[id(tr)] = pth
        mfe, mae = mfe_mae_R(tr["entry"], tr["side"], pth, tr["risk"])
        if mfe is not None:
            mfe_list.append(mfe)
            mae_list.append(mae)
    grid = grid_search(trades, paths, fee_bps=fee_bps)
    cur = next((g for g in grid if g["sl_atr"] == CUR_SL_ATR and g["rr"] == CUR_RR), None)
    best = grid[0] if grid else None
    defl = _deflate(best, len(SL_GRID) * len(RR_GRID)) if best else None

    def _med(xs):
        xs = sorted(xs)
        return round(xs[len(xs) // 2], 3) if xs else None
    return {"n_trades": len(trades), "n_with_path": len(mfe_list),
            "mfe_med_R": _med(mfe_list), "mae_med_R": _med(mae_list),
            "current": cur, "best": best, "deflation": defl, "grid": grid[:8],
            "fee_bps": float(fee_bps), "hours": hours, "granularity": granularity}


def snapshot(hours=48, granularity="15m", fee_bps=None, now=None):
    """Dict COMPACT pour la revue hebdo / le dashboard (advisory, lecture seule).
    `fee_bps=None` -> défaut round-trip taker futures LIVE (résolu par run())."""
    r = run(hours=hours, granularity=granularity, fee_bps=fee_bps)
    best, cur, defl = r.get("best"), r.get("current"), r.get("deflation") or {}
    gain = (round(best["expectancy_R"] - cur["expectancy_R"], 3)
            if best and cur else None)
    s = {"generated_at": int(time.time() if now is None else now),
         "fee_bps": r["fee_bps"], "hours": hours, "granularity": granularity,
         "n_trades": r["n_trades"], "n_with_path": r["n_with_path"],
         "coverage_pct": round(100 * r["n_with_path"] / max(r["n_trades"], 1), 1),
         "mfe_med_R": r["mfe_med_R"], "mae_med_R": r["mae_med_R"],
         "current": cur, "best": best, "best_deflated_R": defl.get("deflated_R"),
         "deflation_bar": defl.get("deflation_bar"), "robuste": defl.get("robuste"),
         "gain_vs_current_R": gain}
    s["verdict"] = _verdict(s)
    return s


def _verdict(s):
    parts = []
    mfe = s.get("mfe_med_R")
    if mfe is not None:
        parts.append(f"MFE médiane {mfe}R")
    cur = s.get("current") or {}
    if cur:
        parts.append(f"actuel (SL{cur['sl_atr']}·ATR/RR{cur['rr']}) espérance NETTE "
                     f"{cur['expectancy_R']:+}R @ {s['fee_bps']}bps")
    best = s.get("best") or {}
    if best:
        rob = "ROBUSTE (survit à la déflation)" if s.get("robuste") else "artefact de sur-testing (déflaté ≤0)"
        parts.append(f"meilleur SL{best['sl_atr']}·ATR/RR{best['rr']} {best['expectancy_R']:+}R "
                     f"(déflaté {s.get('best_deflated_R')}R -> {rob})")
    parts.append("le levier reste les FRAIS (maker), pas le SL/TP")
    return " · ".join(parts)


def build_report(s=None):
    s = snapshot() if s is None else s
    L = [f"=== CALIBRATION DES SORTIES — {s['n_with_path']}/{s['n_trades']} trades rejoués "
         f"(fenêtre {s['hours']}h, {s['granularity']}, frais {s['fee_bps']}bps A/R) ==="]
    L.append(f"MFE médiane {s['mfe_med_R']} R · MAE médiane {s['mae_med_R']} R "
             "(R = distance du stop actuel)")
    cur, best = s.get("current"), s.get("best")
    if cur:
        L.append(f"Actuel  (SL {cur['sl_atr']}·ATR, RR {cur['rr']}) : W {cur['W']} · "
                 f"espérance NETTE {cur['expectancy_R']:+} R/trade (n {cur['n']})")
    if best:
        rob = "ROBUSTE" if s.get("robuste") else "SUR-TESTÉ (déflaté ≤0)"
        L.append(f"OPTIMAL (SL {best['sl_atr']}·ATR, RR {best['rr']}) : W {best['W']} · "
                 f"espérance NETTE {best['expectancy_R']:+} R/trade · déflaté "
                 f"{s.get('best_deflated_R')} R -> {rob}")
        if s.get("gain_vs_current_R") and s["gain_vs_current_R"] > 0:
            L.append(f"-> gain brut {s['gain_vs_current_R']:+} R/trade MAIS ne l'appliquer que "
                     "si le déflaté reste > 0 (sinon = mirage de sur-testing)")
    L.append("VERDICT: " + s["verdict"])
    L.append("Advisory — aucun paramètre changé. Lecture seule. VERDICT: SAFE")
    return "\n".join(L)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Calibration des sorties sur trades paper (lecture seule).")
    p.add_argument("--hours", type=int, default=48)
    p.add_argument("--granularity", default="15m")
    p.add_argument("--max", type=int, default=None, help="limiter aux N derniers trades")
    p.add_argument("--fee", type=float, default=None,
                   help="frais aller-retour en bps (défaut = round-trip taker futures LIVE via fee_rates)")
    p.add_argument("--write", action="store_true", help="écrit .exit_calibration.json (revue/dashboard)")
    a = p.parse_args()
    s = snapshot(hours=a.hours, granularity=a.granularity, fee_bps=a.fee)
    print(build_report(s))
    if a.write:
        try:
            tmp = ARTEFACT.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(s), encoding="utf-8")
            import os
            os.replace(tmp, ARTEFACT)
            print(f"[écrit] {ARTEFACT.name}")
        except Exception as e:
            print(f"[artefact non écrit] {e}")


if __name__ == "__main__":
    main()
