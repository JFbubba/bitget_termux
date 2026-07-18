"""
fee_sweep.py — RÉPONSE à « négatif net ≠ négatif signal » (demande proprio 18/07).

interaction_test.py rejette la réversion croisée avec des frais TAKER (6 bps/côté).
Mais le LEVIER documenté du bot est l'exécution MAKER (~1-2 bps). Ce script réutilise
les positions EXACTES d'interaction_test (aucune refonte, mêmes signaux causals) et
re-backteste chaque configuration à PLUSIEURS niveaux de frais pour trouver le point
de BASCULE. Positions calculées UNE fois (indépendantes des frais) ; seul le backtest
varie. Lecture seule, numpy pur. Répond : y a-t-il un edge brut, et à quel niveau de
frais (donc quel mode d'exécution) devient-il net-positif ?
"""
import numpy as np

import interaction_test as it

FEES_BPS = [6.0, 4.0, 2.0, 1.0, 0.0]     # taker(6) .. maker(1-2) .. sans frais(0)
BANDS = {"rapide (1m-30m)": ["1m", "5m", "15m", "30m"],
         "moyen (1H-4H)": ["1H", "4H"],
         "lent (1D-1W)": ["1D", "1W"]}


def precompute():
    """Calcule les positions (indépendantes des frais) + rendements/BH une seule fois."""
    configs = []
    for tf in it.LADDER:
        for sym, sec in it.ALL_SYMS:
            try:
                d = it.ac.load(sym, tf)
            except Exception:
                continue
            c = d["c"]
            if len(c) > it.MAX_BARS:
                for k in ("o", "h", "l", "c", "v"):
                    d[k] = d[k][-it.MAX_BARS:]
                c = d["c"]
            if len(c) < max(it.ZW + 50, it.SLOW_L + 100):
                continue
            feats = it.si.all_signals(d)
            bh = it.M.buy_and_hold(c, warmup=it.ZW, tf=tf) or {}
            for K in (3, 4, 5):
                configs.append((tf, sym, sec, "confluence", K,
                                it.positions_confluence(feats, K), c, bh))
            for K in (3, 4):
                configs.append((tf, sym, sec, "slowfast", K,
                                it.positions_slowfast(feats, c, K), c, bh))
    return configs


def backtest_at_fee(pos, c, tf, fee):
    prev = it.FEE
    it.FEE = fee                      # backtest() lit le global FEE
    try:
        r, _ = it.backtest(pos, c, tf)
    finally:
        it.FEE = prev
    return r


def run():
    configs = precompute()
    print("=" * 96)
    print("BALAYAGE DE FRAIS — réversion croisée (positions d'interaction_test, méthode ERR-014)")
    print(f"{len(configs)} configs · frais balayés {FEES_BPS} bps/côté · brut = frais 0")
    print("=" * 96)
    hdr = f"{'frais/côté':>11}{'n_strong':>9}{'%net>0':>8}{'%bat_BH':>8}{'net_sh_med':>11}"
    for band in BANDS:
        hdr += f"{band.split()[0][:6]+'_med':>12}"
    print(hdr)

    rows_by_fee = {}
    for fee_bps in FEES_BPS:
        fee = fee_bps / 1e4
        rows = []
        for (tf, sym, sec, variant, K, pos, c, bh) in configs:
            r = backtest_at_fee(pos, c, tf, fee)
            r.update({"tf": tf, "sym": sym, "variant": variant, "K": K,
                      "bh_sharpe": bh.get("bh_sharpe"), "bh_ret_pct": bh.get("bh_return_pct")})
            rows.append(r)
        rows_by_fee[fee_bps] = rows

        strong = [r for r in rows if r.get("net_sharpe") is not None
                  and r["net_sharpe"] > 0.5 and r.get("t_net", 0) >= 3
                  and r.get("net_mean_bps", 0) > 0 and it._beats_bh(r)]
        pnet = np.mean([r["net_mean_bps"] > 0 for r in rows]) * 100
        pbh = np.mean([it._beats_bh(r) for r in rows]) * 100
        nsh = [r["net_sharpe"] for r in rows if r["net_sharpe"] is not None]
        med = lambda xs: round(float(np.median(xs)), 2) if xs else None
        line = (f"{fee_bps:>10.0f} {len(strong):>8} {pnet:>6.0f}% {pbh:>6.0f}% "
                f"{str(med(nsh)):>10}")
        for band, tfs in BANDS.items():
            b = [r["net_sharpe"] for r in rows if r["tf"] in tfs and r["net_sharpe"] is not None]
            line += f"{str(med(b)):>12}"
        print(line)

    # zoom : à frais MAKER (2 et 1 bps), lister les configs qui deviennent net-positives ET t>=2
    print("\n" + "-" * 96)
    for fee_bps in (2.0, 1.0):
        rows = rows_by_fee[fee_bps]
        pos_cfg = [r for r in rows if r.get("net_mean_bps", 0) > 0 and r.get("t_net", 0) >= 2]
        pos_cfg.sort(key=lambda r: -(r.get("net_sharpe") or -9))
        print(f"\nMAKER {fee_bps:.0f} bps/côté — configs net>0 ET t_net>=2 : {len(pos_cfg)}")
        for r in pos_cfg[:15]:
            print(f"   {r['tf']:<4} {r['sym']:<9} {r['variant']:<11} K={r['K']} "
                  f"net_sh={r['net_sharpe']} t={r['t_net']} exp={r.get('expectancy_bps')}bps "
                  f"net={r.get('net_mean_bps')}bps/barre bat_BH={it._beats_bh(r)}")
    print("=" * 96)
    print("Lecture : si n_strong reste 0 même à 0 bps -> pas d'edge BRUT (signal absent).")
    print("Si des configs basculent net>0 à 1-2 bps -> edge RÉEL mangé par le taker,")
    print("le levier est l'exécution maker (à déflater/valider OOS avant toute promotion).")


if __name__ == "__main__":
    run()
