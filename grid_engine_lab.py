"""
grid_engine_lab.py — labo de MESURE exhaustif du moteur grid_engine.
Classement : SAFE (lecture seule + JSON). Balaie mode × surface × config ×
symbole × TF, juge par le pipeline OOS/DSR/PBO/stress de grid_lab. Défaut OFF,
aucun ordre. Cf. docs/superpowers/specs/2026-07-24-grid-engine-multi-surface-design.md.
"""
import json
import time
from pathlib import Path

import grid_lab as gl
import grid_engine as ge

RESULT = Path(__file__).resolve().parent / ".grid_engine_result.json"
LOW_POWER_FUNDING = 90          # < 90 intervalles 8 h ⇒ funding faible-puissance


def combos():
    """(surface, mode) valides : une surface ne fait que ce qu'elle permet."""
    return [("spot", "long_only"),
            ("margin", "bidirectional"), ("margin", "neutral"),
            ("futures", "bidirectional"), ("futures", "neutral")]


def config_sweep(mode, surface):
    """8 configs (4 spacing × 2 k_atr) via gconfig — n_trials maîtrisé."""
    out = []
    for spacing in (0.004, 0.007, 0.012, 0.02):
        for k in (2.5, 3.5):
            out.append((f"{surface}/{mode} g={spacing*100:.1f}%·k={k}",
                        ge.gconfig(mode=mode, surface=surface, spacing=spacing, k_atr=k)))
    return out


def _cost_stress_g(cfg, candles, funding, frac_train=0.6):
    """Stress de coûts pour simulate_g (rejoue sous frais ×{1.5,2})."""
    out = {}
    base = cfg["fee_bps"]
    for mult in (1.5, 2.0):
        c2 = dict(cfg); c2["fee_bps"] = base * mult
        r2 = ge.simulate_g(candles, c2, funding=funding)
        if not r2:
            out[f"x{mult}"] = None; continue
        p = r2["pnls"]; cut = int(len(p) * frac_train)
        out[f"x{mult}"] = round(sum(p[cut:]), 4)
    return {"stress": out, "survives_stress": all(v is not None and v > 0 for v in out.values())}


def evaluate_cell(candles, mode, surface, funding=None, cfg_list=None):
    """Juge une cellule : sweep 8 configs, sélection TRAIN, jugement OOS déflaté
    sur TOUT le sweep, PBO, stress, B&H apparié. Réutilise les métriques PURES de
    grid_lab. cfg_list=None -> config_sweep(mode, surface) (les tests injectent un
    sweep à régime relâché pour forcer le déploiement). Fail-safe -> None."""
    import agent_validation as av
    import backtest_brain as bt
    cfg_list = cfg_list if cfg_list is not None else config_sweep(mode, surface)
    closes = [r[4] for r in candles]
    sims = {}
    for label, cfg in cfg_list:
        try:
            r = ge.simulate_g(candles, cfg, funding=funding)
        except Exception:
            r = None
        if r:
            sims[label] = (cfg, r)
    if not sims:
        return None
    series = {lab: sims[lab][1]["pnls"] for lab in sims}
    sh_full = {lab: gl._sharpe(series[lab]) for lab in series}
    var_sr = gl._variance(list(sh_full.values()))
    n_trials = max(2, len(sims))                        # déflation sur TOUT le sweep
    pbo_res = bt.pbo(series, n_blocks=8)
    viable = {lab for lab in sims if sims[lab][1]["viable_3x"]}
    pool = viable or set(sims)
    best_lab, best_train = None, -1e9
    oos_by_lab = {}
    for lab in pool:
        m = gl._oos_metrics(sims[lab][0], sims[lab][1], closes)
        if not m:
            continue
        oos_by_lab[lab] = m
        if m["train_sharpe"] > best_train:
            best_train, best_lab = m["train_sharpe"], lab
    if best_lab is None:
        return None
    cfg_best, res_best = sims[best_lab]
    oos = oos_by_lab[best_lab]
    dsr = av.deflated_sharpe(oos["oos_sharpe"], oos["n_oos"], oos["skew"], oos["kurt"], n_trials, var_sr)
    stress = _cost_stress_g(cfg_best, candles, funding)
    # funding faible-puissance : nombre d'intervalles de funding effectifs
    n_fund = len(funding) if funding else 0
    low_power = bool(ge.SURFACE[surface]["funding"] and 0 < n_fund < LOW_POWER_FUNDING)
    survives = (oos["oos_total"] > 0 and oos["oos_sharpe"] > 0
                and oos["folds_pos"] >= gl.BARRE["folds_pos_min"]
                and pbo_res.get("pbo") is not None and pbo_res["pbo"] < gl.BARRE["pbo_max"]
                and dsr >= gl.BARRE["dsr_min"] and oos["beats_bh"]
                and stress["survives_stress"] and best_lab in viable
                and not low_power)                       # jamais un vert sur funding faible-puissance
    f = res_best
    return {"mode": mode, "surface": surface, "chosen": best_lab,
            "viable_3x": best_lab in viable, "n_trials": n_trials,
            "total_pnl": f["total_pnl"], "grid_profit": f["grid_profit"],
            "latent_final": f["latent_final"], "fees": f["fees"],
            "funding_pnl_total": f["funding_pnl_total"], "borrow_total": f["borrow_total"],
            "net_delta_final": f["net_delta_final"], "cycles": f["cycles"],
            "oos_total": oos["oos_total"], "oos_sharpe": oos["oos_sharpe"],
            "folds_pos": oos["folds_pos"], "beats_bh": oos["beats_bh"],
            "pbo": pbo_res.get("pbo"), "dsr": round(dsr, 4),
            "survives_stress": stress["survives_stress"],
            "n_funding": n_fund, "low_power_funding": low_power, "survives": survives}


def run(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"), tfs=None, verbose=True):
    """Balaie combos × symboles × TF. funding chargé pour les surfaces perp. Fail-safe."""
    import candles_history as ch
    import funding_history as fh
    tfs = list(tfs or gl.TF_LADDER)
    resultats, lignes = [], []
    for s in symbols:
        fund = fh.load(s) or None
        for tf in tfs:
            gran, jours = gl.TF_GRAN[tf], gl.TF_JOURS[tf]
            try:
                ch.download(s, gran, jours=jours)
                candles = [r for r in ch.load(s, gran)
                           if r[0] >= (time.time() - jours * 86_400) * 1000]
            except Exception as e:
                lignes.append(f"⚠️ {s} {tf} : données indispo ({type(e).__name__})"); continue
            if len(candles) < 200:
                lignes.append(f"⚠️ {s} {tf} : {len(candles)} bougies — sauté"); continue
            for (surface, mode) in combos():
                fnd = fund if ge.SURFACE[surface]["funding"] else None
                try:
                    ev = evaluate_cell(candles, mode, surface, funding=fnd)
                except Exception:
                    ev = None
                if not ev:
                    continue
                ev["symbol"], ev["tf"], ev["n_bars"] = s, tf, len(candles)
                resultats.append(ev)
                mark = "✅" if ev["survives"] else "✗"
                lp = " ⚠️lowfund" if ev["low_power_funding"] else ""
                lignes.append(f"{mark} {s} {tf} {surface}/{mode} TOTAL {ev['total_pnl']:+.2f}$ "
                              f"fund {ev['funding_pnl_total']:+.2f} DSR {ev['dsr']}{lp}")
    n_surv = sum(1 for r in resultats if r["survives"])
    out = {"ts": int(time.time()), "symbols": list(symbols), "tfs": tfs,
           "combos": combos(), "barre": gl.BARRE, "n_cells": len(resultats),
           "n_survivantes": n_surv, "resultats": resultats,
           "note": ("BORNE SUPÉRIEURE (fill sans file, seed+coupe taker) — le réel fera MOINS "
                    "bien. Déflation sur TOUT le sweep. B&H apparié à l'exposition. Funding "
                    "faible-puissance (<90 intervalles) => jamais un vert. Lecture seule.")}
    try:
        RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return {**out, "rapport": "\n".join(lignes)} if verbose else out


def status():
    if not RESULT.exists():
        return {"error": "aucun résultat — lancer `python grid_engine_lab.py --run`"}
    try:
        return json.loads(RESULT.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"illisible ({type(e).__name__})"}


def main():
    import sys
    args = sys.argv[1:]
    if "--run" in args:
        syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        if "--univers" in args:
            try:
                import universe
                syms = universe.symbols() or syms
            except Exception:
                pass
        tfs = gl.TF_QUICK if "--quick" in args else gl.TF_LADDER
        r = run(syms, tfs)
        print("=== GRID ENGINE LAB (multi-surface, LECTURE SEULE) ===")
        print(r["rapport"])
        print(f"\n{r['n_survivantes']}/{r['n_cells']} cellules SURVIVENT toutes les portes.")
        print(r["note"]); print("VERDICT: SAFE")
        return
    st = status()
    print("=== GRID ENGINE LAB — STATUT ===")
    print(st.get("error") or f"{st['n_survivantes']}/{st['n_cells']} survivantes")
    print("Défaut OFF : aucun chemin d'exécution réelle. VERDICT: SAFE")


if __name__ == "__main__":
    main()
