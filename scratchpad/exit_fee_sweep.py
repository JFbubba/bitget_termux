"""
exit_fee_sweep.py — CRIBLE FRAIS sur la calibration des SORTIES (task 4, 18/07).

exit_calibration mesure l'espérance R/trade NETTE DE FRAIS des sorties sur 344 trades paper,
mais le cache est à 10 bps (taker). Question honnête : à frais MAKER, le setup CURRENT
(SL1.5·ATR/RR2.0 — convention FIXE, pas un gagnant de grille sur-testé) bascule-t-il positif ?
On charge les chemins UNE fois puis on balaye les frais aller-retour. On rapporte :
  - current : espérance du setup RÉEL (mesure propre, non déflatable car non cherry-pické) ;
  - best + déflaté : le meilleur de grille ET sa barre de déflation (anti sur-testing).
Lecture seule. Réutilise exit_calibration (chargement, grille, déflation).
"""
import sys

sys.path.insert(0, "/root/bitget_termux_repo")
import exit_calibration as ec

FEES_RT = [12.0, 8.0, 4.0, 2.0, 0.0]   # aller-retour bps : taker ~12 · maker ~4 · brut 0
HOURS = 48
GRAN = "15m"


def main():
    trades = ec._load_outcomes()
    by_sym = {}
    for t in trades:
        by_sym.setdefault(t["symbol"], []).append(t["ts"])
    cache = {s: ec._symbol_candles(s, GRAN, ts_min=min(ts)) for s, ts in by_sym.items()}
    paths = {}
    for tr in trades:
        paths[id(tr)] = ec._path(cache.get(tr["symbol"], []), tr["ts"], HOURS)
    n_res = sum(1 for p in paths.values() if p)
    n_trials = len(ec.SL_GRID) * len(ec.RR_GRID)

    print(f"CRIBLE FRAIS — sorties · {len(trades)} trades, {n_res} avec chemin · {GRAN}, fenêtre {HOURS}h")
    print("Convention CURRENT = SL1.5·ATR / RR2.0 (fixe, non sur-testée = mesure propre)\n")
    print(f"{'fee_RT_bps':>11}{'current_E_R':>13}{'±se':>8}{'W':>7}   |"
          f"{'best_grid_E_R':>14}{'best_defl_R':>13}{'robuste':>9}")
    print("-" * 82)
    rows = []
    for fee in FEES_RT:
        grid = ec.grid_search(trades, paths, fee_bps=fee)
        cur = next((g for g in grid if g["sl_atr"] == ec.CUR_SL_ATR and g["rr"] == ec.CUR_RR), None)
        best = grid[0] if grid else None
        defl = ec._deflate(best, n_trials) if best else {}
        if cur:
            print(f"{fee:>11.0f}{cur['expectancy_R']:>13.4f}{cur['se']:>8.4f}{cur['W']:>7.3f}   |"
                  f"{best['expectancy_R']:>14.4f}{str(defl.get('deflated_R')):>13}{str(defl.get('robuste')):>9}")
            rows.append((fee, cur, best, defl))
    print("\n" + "=" * 82)
    # à quel frais le CURRENT devient-il positif (mesure propre) ? et reste-t-il > se ?
    flip = next((f for f, cur, *_ in rows if cur["expectancy_R"] > 0), None)
    flip_sig = next((f for f, cur, *_ in rows if cur["expectancy_R"] > cur["se"]), None)
    if flip is not None:
        print(f"Le setup CURRENT bascule POSITIF à partir de {flip:.0f} bps aller-retour "
              f"(≈ {flip/2:.0f} bps/côté).")
        print(f"Positif AU-DELÀ du bruit (E > se) à partir de : "
              f"{('%.0f bps' % flip_sig) if flip_sig is not None else 'JAMAIS dans la plage testée'}.")
    else:
        print("Le setup CURRENT reste NÉGATIF même à 0 frais -> le SL/TP saigne indépendamment des frais.")
    print("Note : le 'best_grid' déflaté ≤0 = artefact de sur-testing (25 essais) — NE PAS l'appliquer.")
    print("Le levier honnête = frais (maker) sur la convention EXISTANTE, pas un nouveau SL/TP.")
    print("=" * 82)


if __name__ == "__main__":
    main()
