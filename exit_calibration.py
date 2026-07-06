"""
exit_calibration.py — calibration des SORTIES sur les trades PAPER (LECTURE SEULE). SAFE.

Question (§68/voie saine, étape B) : le R RÉALISÉ (0.56) est bien pire que le R
directionnel (~1.2) -> les sorties (SL 1.5·ATR / RR 2, conventions jamais mesurées §60)
saignent le payoff. Cet outil MESURE, sur les 248 issues paper finalisées :
  1. le chemin de prix réel après chaque entrée (bougies publiques rejouées) ;
  2. la MFE/MAE (excursion max favorable/adverse) en unités de RISQUE (distance du stop) ;
  3. une RECHERCHE sur grille (SL en ATR × RR) du couple qui maximise l'ESPÉRANCE par
     trade (E = W·RR − (1−W), en unités de risque), avec simulation first-touch.

Advisory PUR : ne change AUCUN paramètre (le SL/TP réel reste décidé séparément via le
mandat). Aucun ordre. Rejoue des bougies publiques (candle_reader résilient).

CLI : python exit_calibration.py [--hours 48] [--granularity 15m] [--max 200]
"""
import csv
from datetime import datetime
from pathlib import Path

# Convention actuelle (à battre) : stop = 1.5·ATR, take-profit = RR·stop avec RR = 2.
CUR_SL_ATR = 1.5
CUR_RR = 2.0
SL_GRID = (1.0, 1.5, 2.0, 2.5, 3.0)     # multiples d'ATR pour le stop
RR_GRID = (1.0, 1.5, 2.0, 2.5, 3.0)     # ratio take-profit / stop


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


def _symbol_candles(symbol, granularity, limit=1000):
    """Bougies récentes du symbole (couvre la fenêtre des signaux récents), triées, en
    (ts_epoch, high, low). Best-effort []."""
    try:
        import candle_reader as cr
        cs = cr.get_bitget_candles(symbol, product_type="USDT-FUTURES",
                                   granularity=granularity, limit=limit)
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


def grid_search(trades, paths, sl_grid=SL_GRID, rr_grid=RR_GRID):
    """Pour chaque (sl_mult, rr), simule tous les trades et calcule W, R et l'espérance
    par trade E = W·rr − (1−W) (en unités de risque). Trié par E décroissant."""
    results = []
    for sl in sl_grid:
        for rr in rr_grid:
            tp = won = lost = 0
            for tr in trades:
                path = paths.get(id(tr))
                if not path:
                    continue
                res = simulate(tr["entry"], tr["side"], path, tr["atr"], sl, rr)
                if res == "TP":
                    won += 1
                elif res == "SL":
                    lost += 1
                # None (ni TP ni SL) : trade non résolu dans la fenêtre -> ignoré
            n = won + lost
            if n < 20:
                continue
            W = won / n
            E = W * rr - (1 - W)                    # espérance par trade (unités de risque)
            results.append({"sl_atr": sl, "rr": rr, "W": round(W, 4),
                            "expectancy_R": round(E, 4), "n": n})
    results.sort(key=lambda x: -x["expectancy_R"])
    return results


def run(hours=48, granularity="15m", max_rows=None):
    """Charge les trades, rejoue les chemins (1 fetch/symbole), calcule MFE/MAE + grille."""
    trades = _load_outcomes(max_rows=max_rows)
    symbols = sorted({t["symbol"] for t in trades})
    cache = {s: _symbol_candles(s, granularity) for s in symbols}
    paths, mfe_list, mae_list = {}, [], []
    for tr in trades:
        pth = _path(cache.get(tr["symbol"], []), tr["ts"], hours)
        paths[id(tr)] = pth
        mfe, mae = mfe_mae_R(tr["entry"], tr["side"], pth, tr["risk"])
        if mfe is not None:
            mfe_list.append(mfe)
            mae_list.append(mae)
    grid = grid_search(trades, paths)
    cur = next((g for g in grid if g["sl_atr"] == CUR_SL_ATR and g["rr"] == CUR_RR), None)

    def _med(xs):
        xs = sorted(xs)
        return round(xs[len(xs) // 2], 3) if xs else None
    return {"n_trades": len(trades), "n_with_path": len(mfe_list),
            "mfe_med_R": _med(mfe_list), "mae_med_R": _med(mae_list),
            "current": cur, "best": grid[0] if grid else None, "grid": grid[:8]}


def main():
    import argparse
    p = argparse.ArgumentParser(description="Calibration des sorties sur trades paper (lecture seule).")
    p.add_argument("--hours", type=int, default=48)
    p.add_argument("--granularity", default="15m")
    p.add_argument("--max", type=int, default=None, help="limiter aux N derniers trades")
    a = p.parse_args()
    r = run(hours=a.hours, granularity=a.granularity, max_rows=a.max)
    print(f"=== CALIBRATION DES SORTIES — {r['n_with_path']}/{r['n_trades']} trades rejoués "
          f"(fenêtre {a.hours} h, {a.granularity}) ===")
    print(f"MFE médiane {r['mfe_med_R']} R  ·  MAE médiane {r['mae_med_R']} R  "
          f"(R = distance du stop actuel)")
    cur, best = r["current"], r["best"]
    if cur:
        print(f"\nActuel  (SL {cur['sl_atr']}·ATR, RR {cur['rr']}) : "
              f"W {cur['W']} · espérance {cur['expectancy_R']:+} R/trade (n {cur['n']})")
    if best:
        print(f"OPTIMAL (SL {best['sl_atr']}·ATR, RR {best['rr']}) : "
              f"W {best['W']} · espérance {best['expectancy_R']:+} R/trade (n {best['n']})")
        if cur and best["expectancy_R"] > cur["expectancy_R"]:
            print(f"-> gain d'espérance {best['expectancy_R'] - cur['expectancy_R']:+.3f} R/trade "
                  f"en passant à SL {best['sl_atr']}·ATR / RR {best['rr']}")
    print("\nTop couples (espérance décroissante) :")
    for g in r["grid"]:
        print(f"  SL {g['sl_atr']}·ATR RR {g['rr']} : W {g['W']} · E {g['expectancy_R']:+} R (n {g['n']})")
    print("\nAdvisory — aucun paramètre changé. VERDICT: SAFE")


if __name__ == "__main__":
    main()
