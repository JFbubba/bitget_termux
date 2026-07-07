"""
mm_lab.py — banc de MESURE du market making §94 (backtest dédié, LECTURE SEULE).

Classement : SAFE. Aucun ordre, aucune écriture réseau — sorties = console + un
JSON de résultats (.mm_lab_result.json, gitignoré).

Pourquoi un banc À PART : le strategy_lab (§68) juge des stratégies
DIRECTIONNELLES (signal ∈ {-1,0,+1} × rendement forward) — le market making n'y
entre pas : son PnL vient des FILLS de cotations (spread capturé vs adverse
selection + frais), pas d'un pari de direction. Ce banc rejoue la MÉCANIQUE de
market_maker.py sur bougies 5 m (la cadence réelle du cycle cron) en réutilisant
ses fonctions PURES — build_plan/apply_fill/inventory_view/vol_bps — pour zéro
divergence banc/prod (même esprit que build_named du lab).

HONNÊTETÉS DU MODÈLE (à lire avant de croire un chiffre) :
  • un fill exige que le prix TRAVERSE strictement le niveau coté
    (low < bid, high > ask) — approximation SANS file d'attente : c'est le cas
    FAVORABLE ; le réel (priorité temps/prix, latence REST) fera MOINS bien.
    Le banc donne une BORNE SUPÉRIEURE : négatif ici => pire en réel ;
  • fair = clôture de la barre PRÉCÉDENTE (causal, aucun look-ahead) ; pas de
    microprice (aucun carnet L1 historique) — snapshot synthétique serré ;
  • frais MAKER déduits à chaque fill ; mark-to-market à chaque barre ; stop
    local journalier simulé comme en prod (halted -> plus de cotation ce jour).
Verdict de barre (esprit PROMOTE du lab) : PnL net > 0 ET ≥60 % de tranches
walk-forward positives ET ≥30 fills (que la loi des grands nombres parle).

CLI :
    python mm_lab.py                      # BTCUSDT, 30 j de 5 m, grille de configs
    python mm_lab.py ETHUSDT 14           # symbole + profondeur (jours)
"""
import json
import time
from pathlib import Path

import backtest_brain as bt
import market_maker as mm

RESULT = Path(__file__).resolve().parent / ".mm_lab_result.json"
BARRE = {"pnl": 0.0, "frac_folds_pos": 0.60, "fills": 30}


def config_banc(fee_bps=10.0, vol_mult=2.5, notional=5.0, book_spread_bps=2.0,
                max_daily_loss=1.0):
    """Config du banc = mêmes clés que market_maker.config() (PUR, sans env)."""
    return {"symbol": "BTCUSDT", "notional": notional, "min_notional": 1.0,
            "per_quote_cap": 5.0, "min_spread_bps": 8.0, "max_spread_bps": 80.0,
            "fee_bps": fee_bps, "buffer_bps": 3.0, "vol_mult": vol_mult,
            "budget": 20.0, "target_base_pct": 0.50, "skew_strength": 0.80,
            "max_dev": 0.30, "max_inventory": 15.0, "max_book_spread": 120.0,
            "max_premium_pct": 0.50, "max_daily_loss": max_daily_loss,
            "price_decimals": 2, "book_spread_bps": book_spread_bps}


def simulate(candles, c):
    """Rejoue le cycle de cotation barre par barre. PUR. candles = [[ts_ms, open,
    high, low, close, vol], ...] triées asc. Retourne métriques + PnL par barre."""
    etat = {"inv_base": 0.0, "avg_cost": 0.0, "realized_today": 0.0}
    mids, pnls, equity_prev = [], [], 0.0
    realized_cum = fees_cum = 0.0
    fills_buy = fills_sell = 0
    jour_courant, halted = None, False
    sp = c["book_spread_bps"] / 10_000.0
    for i in range(1, len(candles)):
        ts, high, low, close = candles[i][0], candles[i][2], candles[i][3], candles[i][4]
        fair = candles[i - 1][4]                      # clôture précédente : causal
        mids.append(fair)
        jour = int(ts // 86_400_000)
        if jour != jour_courant:
            jour_courant, halted = jour, False
            etat["realized_today"] = 0.0
        inv = mm.inventory_view(etat["inv_base"], etat["avg_cost"], fair, c)
        if not halted and (etat["realized_today"] + inv["latent"]) <= -c["max_daily_loss"]:
            halted = True                             # stop local : plus de cotation ce jour
        plan = None
        if not halted and len(mids) >= mm.MIN_HISTORY:
            snap = {"bid": fair * (1 - sp / 2), "ask": fair * (1 + sp / 2),
                    "mid": fair, "micro": fair, "fair": fair,
                    "spread_bps": c["book_spread_bps"],
                    "vol_bps": mm.vol_bps(mids), "n_mids": len(mids)}
            plan = mm.build_plan(snap, inv, c)
        avant = etat["realized_today"]
        if plan and plan["bid_price"] is not None and low < plan["bid_price"]:
            size = plan["bid_usdt"] / plan["bid_price"]
            mm.apply_fill(etat, "buy", size, plan["bid_price"])
            fees_cum += plan["bid_usdt"] * c["fee_bps"] / 10_000.0
            fills_buy += 1
        if plan and plan["ask_price"] is not None and high > plan["ask_price"]:
            size = plan["ask_usdt"] / plan["ask_price"]
            mm.apply_fill(etat, "sell", size, plan["ask_price"])
            fees_cum += plan["ask_usdt"] * c["fee_bps"] / 10_000.0
            fills_sell += 1
        realized_cum += etat["realized_today"] - avant
        latent = (close - etat["avg_cost"]) * etat["inv_base"] if etat["inv_base"] > 0 else 0.0
        equity = realized_cum - fees_cum + latent
        pnls.append(equity - equity_prev)
        equity_prev = equity
    folds = bt.walk_forward(pnls) if pnls else []
    fpos = (sum(1 for f in folds if f > 0) / len(folds)) if folds else 0.0
    pic = dd = cours = 0.0
    for p in pnls:
        cours += p
        pic = max(pic, cours)
        dd = min(dd, cours - pic)
    jours = max(1.0, (candles[-1][0] - candles[0][0]) / 86_400_000.0)
    return {"pnl_net": round(equity_prev, 4), "pnl_jour": round(equity_prev / jours, 4),
            "realized": round(realized_cum, 4), "fees": round(fees_cum, 4),
            "latent_final": round(equity_prev - realized_cum + fees_cum, 4),
            "fills_buy": fills_buy, "fills_sell": fills_sell,
            "round_trips": min(fills_buy, fills_sell),
            "frac_folds_pos": round(fpos, 3), "max_dd": round(dd, 4),
            "inv_final_base": round(etat["inv_base"], 8), "jours": round(jours, 1),
            "pnls": pnls}


def verdict(r):
    """Barre du banc (esprit PROMOTE du lab). PUR."""
    total_fills = r["fills_buy"] + r["fills_sell"]
    return (r["pnl_net"] > BARRE["pnl"] and r["frac_folds_pos"] >= BARRE["frac_folds_pos"]
            and total_fills >= BARRE["fills"])


def grille():
    """Petit sweep HONNÊTE (pas d'optimisation fine = pas de surapprentissage) :
    frais réels vs réduits (BGB/VIP), prudence de vol, + un scénario SANS frais
    qui isole la part des frais dans le résultat."""
    return [
        ("frais 10 bps · vol ×2.5 (prod)", config_banc(fee_bps=10.0, vol_mult=2.5)),
        ("frais 10 bps · vol ×1.5 (serré)", config_banc(fee_bps=10.0, vol_mult=1.5)),
        ("frais 10 bps · vol ×3.5 (large)", config_banc(fee_bps=10.0, vol_mult=3.5)),
        ("frais 8 bps · vol ×2.5 (réduit)", config_banc(fee_bps=8.0, vol_mult=2.5)),
        ("frais 0 (théorique — part des frais)", config_banc(fee_bps=0.0, vol_mult=2.5)),
    ]


def run(symbol="BTCUSDT", jours=30):
    """Télécharge (incrémental) les 5 m, rejoue la grille, écrit le JSON de
    résultats et retourne le résumé. Lecture seule côté marché."""
    import candles_history as ch
    n = ch.download(symbol, "5m", jours=jours)
    candles = [r for r in ch.load(symbol, "5m")
               if r[0] >= (time.time() - jours * 86_400) * 1000]
    if len(candles) < 500:
        return {"error": f"pas assez de bougies 5m ({len(candles)}) — download={n}"}
    lignes, resultats = [], []
    for nom, c in grille():
        r = simulate(candles, c)
        pnls = r.pop("pnls")
        ok = verdict(r)
        resultats.append({"config": nom, "verdict": "PASSE" if ok else "ÉCHOUE", **r})
        lignes.append(f"{'✅' if ok else '❌'} {nom} : PnL net {r['pnl_net']} $ "
                      f"({r['pnl_jour']} $/j) · fills {r['fills_buy']}b/{r['fills_sell']}s "
                      f"· folds+ {r['frac_folds_pos']} · maxDD {r['max_dd']} $ "
                      f"· frais {r['fees']} $")
        _ = pnls
    out = {"ts": int(time.time()), "symbol": symbol, "jours": jours,
           "barres_5m": len(candles), "barre": BARRE, "resultats": resultats,
           "note": ("BORNE SUPÉRIEURE (fill sans file d'attente, fair causal, "
                    "pas de microprice) — le réel fera moins bien ; le juge final "
                    "reste le DRY live (.mm_journal.jsonl).")}
    try:
        RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return {**out, "rapport": "\n".join(lignes)}


def main():
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    symbol = (args[0] if args else "BTCUSDT").upper()
    jours = int(args[1]) if len(args) > 1 else 30
    r = run(symbol, jours)
    print(f"=== MM LAB (banc §94, lecture seule) — {symbol} · {jours} j de 5 m ===")
    if r.get("error"):
        print("ERREUR :", r["error"])
        return
    print(f"{r['barres_5m']} barres · barre du banc : PnL>{BARRE['pnl']} $, "
          f"folds+ ≥{BARRE['frac_folds_pos']}, fills ≥{BARRE['fills']}")
    print(r["rapport"])
    print(r["note"])
    print("VERDICT: SAFE")


if __name__ == "__main__":
    main()
