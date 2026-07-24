"""
grid_futures_measure.py — mesure COMPARATIVE de viabilité de la grille : SPOT vs FUTURES.

Classement : SAFE. Aucun ordre, aucune écriture réseau de trading. Réutilise
INTÉGRALEMENT le banc `grid_lab.py` (LECTURE SEULE, défaut OFF) : mêmes bougies,
même sweep de 8 configs, mêmes portes (PBO<0,5 · DSR≥0,95 · folds+≥0,6 · bat B&H ·
stress ×2 · règle d'or 3×coûts). La SEULE variable isolée est le RÉGIME DE FRAIS :

  • SPOT   : maker 8 bps/côté (déduction BGB MESURÉE) + slippage 2 bps sur seed/coupe.
             = référence historique du banc (cf. docs/GRID_STRATEGIES.md §4).
  • FUTURES: maker 2 bps/côté + slippage 4 bps sur seed/coupe (modélise le repli
             taker ~6 bps que le maker post-only subit à chaque cassure). Frais
             maker futures Bitget = 2 bps (cf. docs/BITGET_REFERENCE.md, mém.
             exec-fees-lever) → ~75 % moins cher que le spot.

But : répondre à « les frais futures 4× plus bas font-ils BASCULER la grille ? »
sans confondre l'effet frais avec autre chose. Modèle LONG-ONLY (grille à
inventaire de grid_lab : pas de short, pas de funding) pour que le frais reste le
facteur dominant du verdict. Un short/funding-grid relèverait d'une conception
Phase 3 SÉPARÉE (non couverte ici).

HONNÊTETÉS : héritées de grid_lab (fill sans file d'attente, 1 transition/cellule/
barre, seed+coupe en taker, comptabilité TOTAL-P&L = grid+latent−frais) → BORNE
SUPÉRIEURE, le réel fera MOINS bien. Le banc futures est un proxy fidèle du prix.

CLI (CONSULTATION, lecture seule) :
    python grid_futures_measure.py --status         # dernier résultat (aucun réseau)
    python grid_futures_measure.py --run            # BTC+ETH+SOL, échelle TF complète
    python grid_futures_measure.py --run --quick    # sous-ensemble H1/H4/D1 (rapide)
    python grid_futures_measure.py --run --sym BTCUSDT   # une seule paire (smoke test)
"""
import json
import time
from pathlib import Path

import grid_lab as gl

RESULT = Path(__file__).resolve().parent / ".grid_futures_result.json"

# Régimes de frais isolés (maker_bps, slip_bps). Le slip futures plus élevé modélise
# le repli taker que le post-only subit sur seed + coupe de cassure.
SPOT_REGIME = {"fee_bps": 8.0, "slip_bps": 2.0}
FUT_REGIME = {"fee_bps": 2.0, "slip_bps": 4.0}


def config_grille_regime(fee_bps, slip_bps):
    """Le sweep HONNÊTE de grid_lab (4 espacements × 2 k_atr = 8 configs) reprojeté
    sur un régime de frais donné. n_trials identique (déflation comparable)."""
    grille = []
    for spacing in (0.004, 0.007, 0.012, 0.02):
        for k in (2.5, 3.5):
            grille.append((f"g={spacing * 100:.1f}%·k={k}",
                           gl.config(spacing=spacing, k_atr=k,
                                     fee_bps=fee_bps, slip_bps=slip_bps)))
    return grille


def _cell(candles, regime):
    """Évalue le sweep sur un régime de frais → sous-ensemble compact du verdict."""
    grille = config_grille_regime(**regime)
    ev = gl.evaluate_symbol_tf(candles, cfg_list=grille)
    if not ev:
        return None
    f = ev["full"]
    return {
        "survives": ev["survives"], "viable_3x": ev["viable_3x"],
        "chosen": ev["chosen"],
        "total_pnl": round(f["total_pnl"], 4), "grid_profit": round(f["grid_profit"], 4),
        "latent_final": round(f["latent_final"], 4), "fees": round(f["fees"], 4),
        "cycles": f["cycles"], "deployments": f["deployments"], "cuts": f["cuts"],
        "oos_total": round(ev["oos"]["oos_total"], 4),
        "oos_sharpe": round(ev["oos"]["oos_sharpe"], 4),
        "folds_pos": ev["oos"]["folds_pos"], "beats_bh": ev["oos"]["beats_bh"],
        "pbo": ev["pbo"], "dsr": ev["dsr"], "survives_stress": ev["survives_stress"],
    }


def run(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"), tfs=None, verbose=True):
    """Télécharge une fois par (sym,TF), rejoue les DEUX régimes sur les MÊMES
    bougies, écrit le JSON et retourne le rapport. Aucun ordre. Fail-safe par cellule."""
    import candles_history as ch
    tfs = list(tfs or gl.TF_LADDER)
    resultats, lignes = [], []
    for s in symbols:
        for tf in tfs:
            gran = gl.TF_GRAN[tf]
            jours = gl.TF_JOURS[tf]
            try:
                ch.download(s, gran, jours=jours)
                candles = [r for r in ch.load(s, gran)
                           if r[0] >= (time.time() - jours * 86_400) * 1000]
            except Exception as e:
                lignes.append(f"⚠️ {s} {tf} : données indisponibles ({type(e).__name__}) — sauté")
                continue
            if len(candles) < 200:
                lignes.append(f"⚠️ {s} {tf} : pas assez de bougies ({len(candles)}) — sauté")
                continue
            spot = _cell(candles, SPOT_REGIME)
            fut = _cell(candles, FUT_REGIME)
            if not spot or not fut:
                lignes.append(f"⚠️ {s} {tf} : simulation vide — sauté")
                continue
            row = {"symbol": s, "tf": tf, "n_bars": len(candles),
                   "spot": spot, "futures": fut}
            resultats.append(row)
            ms = "✅" if spot["survives"] else "✗"
            mf = "✅" if fut["survives"] else "✗"
            lignes.append(
                f"{s} {tf} : SPOT {ms} TOTAL {spot['total_pnl']:+.2f}$ frais {spot['fees']:.2f} "
                f"DSR {spot['dsr']} | FUT {mf} TOTAL {fut['total_pnl']:+.2f}$ frais {fut['fees']:.2f} "
                f"DSR {fut['dsr']}")
    n_spot = sum(1 for r in resultats if r["spot"]["survives"])
    n_fut = sum(1 for r in resultats if r["futures"]["survives"])
    out = {"ts": int(time.time()), "symbols": list(symbols), "tfs": tfs,
           "spot_regime": SPOT_REGIME, "futures_regime": FUT_REGIME,
           "barre": gl.BARRE, "n_cells": len(resultats),
           "n_spot_survivantes": n_spot, "n_fut_survivantes": n_fut,
           "resultats": resultats,
           "note": ("BORNE SUPÉRIEURE (grid_lab : fill sans file, 1 transition/cellule/"
                    "barre, seed+coupe taker) — le réel fera MOINS bien. Frais = SEULE "
                    "variable isolée entre spot et futures. Long-only. Lecture seule.")}
    try:
        RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    if verbose:
        return {**out, "rapport": "\n".join(lignes)}
    return out


def status():
    """CONSULTATION pure (aucun réseau) : relit le dernier résultat mesuré."""
    if not RESULT.exists():
        return {"error": "aucun résultat — lancer `python grid_futures_measure.py --run`"}
    try:
        return json.loads(RESULT.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"résultat illisible ({type(e).__name__})"}


def main():
    import sys
    args = sys.argv[1:]
    if "--run" in args:
        if "--sym" in args:
            symbols = [args[args.index("--sym") + 1]]
        else:
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        tfs = gl.TF_QUICK if "--quick" in args else gl.TF_LADDER
        r = run(symbols, tfs)
        print(f"=== GRID FUTURES MEASURE (SPOT 8bps vs FUTURES 2bps, LECTURE SEULE) — "
              f"{', '.join(symbols)} · TF {'/'.join(tfs)} ===")
        print(f"barre : PBO<{gl.BARRE['pbo_max']} · DSR≥{gl.BARRE['dsr_min']} "
              f"· folds+≥{gl.BARRE['folds_pos_min']} · bat B&H · stress ×2 · règle d'or 3×coûts")
        print(r["rapport"])
        print(f"\nSPOT {r['n_spot_survivantes']}/{r['n_cells']} · "
              f"FUTURES {r['n_fut_survivantes']}/{r['n_cells']} (sym,TF) SURVIVENT toutes les portes.")
        print(r["note"])
        print("VERDICT: SAFE")
        return
    st = status()
    print("=== GRID FUTURES MEASURE — STATUT ===")
    if st.get("error"):
        print(st["error"])
    else:
        import datetime
        d = datetime.datetime.fromtimestamp(st["ts"], datetime.timezone.utc)
        print(f"dernier run {d:%Y-%m-%d %H:%M UTC} · SPOT {st['n_spot_survivantes']}/{st['n_cells']} "
              f"· FUTURES {st['n_fut_survivantes']}/{st['n_cells']} survivantes")
        for r in st["resultats"]:
            sp, fu = r["spot"], r["futures"]
            print(f"  {r['symbol']} {r['tf']} : SPOT TOTAL {sp['total_pnl']:+.2f}$ DSR {sp['dsr']} "
                  f"| FUT TOTAL {fu['total_pnl']:+.2f}$ DSR {fu['dsr']}")
    print("Défaut OFF : aucun chemin d'exécution réelle. VERDICT: SAFE")


if __name__ == "__main__":
    main()
