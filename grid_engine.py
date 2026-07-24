"""
grid_engine.py — moteur de grille PUR généralisé (mode × surface × funding).
Classement : SAFE. Aucun I/O, aucun réseau, aucun ordre. Généralise
grid_lab.simulate (long-only) aux jambes SHORT (marge/futures) et au FUNDING
(perp), avec comptabilité TOTAL = grid + latent + funding − frais − borrow.
Réutilise les helpers PURS de grid_lab (grid_lines, _prepare, _regime_ok, _cut,
regle_dor). Cf. docs/superpowers/specs/2026-07-24-grid-engine-multi-surface-design.md.
"""
import grid_lab as gl

# Frais autoritatifs (docs/BITGET_REFERENCE.md §1). slip futures=4 modélise le
# repli taker ~6 bps du post-only sur seed/coupe (cf. grid_futures_measure.py).
SURFACE = {
    "spot":    {"maker_bps": 8, "slip_bps": 2, "short": False, "funding": False,
                "lev_max": 1, "cap_op": 200, "cap_day": 500},
    "margin":  {"maker_bps": 8, "slip_bps": 2, "short": True,  "funding": False,
                "lev_max": 1, "cap_op": 200, "cap_day": 500},
    "futures": {"maker_bps": 2, "slip_bps": 4, "short": True,  "funding": True,
                "lev_max": 5, "cap_op": 50,  "cap_day": 250},
}
MODES = ("long_only", "bidirectional", "neutral")


def gconfig(mode="neutral", surface="futures", funding_lean=0.0,
            borrow_bps_per_day=0.0, **grid_lab_kw):
    """Config généralisée : grid_lab.config + {mode, surface, funding_lean, borrow}.
    Les frais/slip viennent de la SURFACE (écrasent tout fee_bps/slip_bps passé). PUR."""
    if mode not in MODES:
        raise ValueError(f"mode invalide: {mode!r} (attendu {MODES})")
    if surface not in SURFACE:
        raise ValueError(f"surface invalide: {surface!r} (attendu {tuple(SURFACE)})")
    s = SURFACE[surface]
    grid_lab_kw["fee_bps"] = s["maker_bps"]
    grid_lab_kw["slip_bps"] = s["slip_bps"]
    cfg = gl.config(**grid_lab_kw)
    cfg.update({"mode": mode, "surface": surface,
                "funding_lean": float(funding_lean),
                "borrow_bps_per_day": float(borrow_bps_per_day)})
    return cfg


def funding_pnl(net_qty, price, rate):
    """P&L de funding sur UN intervalle 8 h. net_qty>0 long, <0 short. Convention
    Bitget : le LONG paie le SHORT quand rate>0 -> P&L pour nous = -net_qty*price*rate. PUR."""
    return -float(net_qty) * float(price) * float(rate)


def _center(window):
    """VWAP de la fenêtre, repli SMA des clôtures. PUR. None si vide."""
    if not window:
        return None
    try:
        import technicals as tk
        v = tk.vwap([{"high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in window])
        if v:
            return v
    except Exception:
        pass
    return sum(r[4] for r in window) / len(window)


def _funding_at(funding, t0, t1):
    """Somme des taux dont ts_ms ∈ ]t0, t1]. funding=[(ts,taux),...] trié. PUR."""
    if not funding:
        return 0.0
    return sum(r[1] for r in funding if t0 < r[0] <= t1)


def simulate_g(candles, cfg, funding=None):
    """Simule la grille généralisée barre par barre. PUR, fail-safe -> None.
    mode long_only : parité grid_lab. bidirectional : + jambes SHORT au-dessus du
    centre. neutral : + hedge de base (short) pour delta≈0, funding_lean l'incline.
    Comptabilité TOTAL = realized − fees + latent + funding − borrow."""
    n = len(candles)
    warmup = max(cfg["window"], 2 * cfg["adx_period"] + 2, cfg["bb_period"],
                 cfg["vol_period"]) + 1
    if n < warmup + 30:
        return None
    prep = gl._prepare(candles, cfg)
    fee = cfg["fee_bps"] / 1e4
    slip = cfg["slip_bps"] / 1e4
    rung = cfg["rung_notional"]
    mode = cfg["mode"]
    surf = SURFACE[cfg["surface"]]
    can_short = surf["short"] and mode in ("bidirectional", "neutral")
    use_funding = bool(surf["funding"] and funding)
    borrow_day = (cfg["borrow_bps_per_day"] / 1e4) if (cfg["surface"] == "margin") else 0.0
    bar_h = _bar_hours(candles)
    exposure_cap = cfg["max_levels"] * rung

    active = False
    lines, cells = [], []
    atr_deploy = None
    hedge_qty = 0.0          # position short de couverture (mode neutral), qty>0 = short
    hedge_entry = 0.0
    realized = fees = fund_tot = borrow_tot = 0.0
    pnls = []
    equity_prev = 0.0
    exposure_max = 0.0
    deployments = cuts = n_buys = n_sells = 0
    active_bars = 0
    cut_motifs = {}
    last_cut = -10 ** 9
    prev_ts = candles[warmup][0]

    def _net_delta():
        # qty nette signée : long inventaire (+), short cells (−), hedge (−)
        d = 0.0
        for cl in cells:
            if cl["side"] == "long" and cl["state"] == "coin":
                d += rung / cl["entry"]
            elif cl["side"] == "short" and cl["state"] == "short":
                d -= rung / cl["entry"]
        return d - hedge_qty

    for i in range(warmup, n):
        c = prep["closes"][i]; h = prep["highs"][i]; low = prep["lows"][i]; ts = candles[i][0]

        # ---- déploiement ----
        if not active and (i - last_cut) >= cfg["cooldown_bars"] and gl._regime_ok(prep, i, cfg):
            atr = prep["atr"][i]
            window = candles[i - cfg["window"] + 1:i + 1]
            center = _center(window)
            if atr and center and atr > 0:
                lo = center - cfg["k_atr"] * atr
                hi = center + cfg["k_atr"] * atr
                lns = gl.grid_lines(lo, hi, cfg["spacing"], cfg["max_levels"])
                if lns:
                    lines = lns
                    cells = []
                    for j in range(len(lines) - 1):
                        if can_short:
                            # symétrique : sous le centre = long (achat bas), au-dessus = short (vente haut)
                            m = 0.5 * (lines[j] + lines[j + 1])
                            if m < center:
                                cells.append({"lo": lines[j], "hi": lines[j + 1],
                                              "side": "long", "state": "cash", "entry": c})
                            else:
                                cells.append({"lo": lines[j], "hi": lines[j + 1],
                                              "side": "short", "state": "flat", "entry": c})
                        else:
                            # long_only : parité grid_lab (cellule au-dessus du prix = seed coin)
                            above = lines[j] >= c
                            cells.append({"lo": lines[j], "hi": lines[j + 1], "side": "long",
                                          "state": "coin" if above else "cash", "entry": c})
                    if not can_short:
                        seeds = sum(1 for cl in cells if cl["state"] == "coin")
                        if seeds:
                            fees += seeds * rung * (fee + slip)   # seed taker
                    else:
                        # hedge de base (neutral seulement) : short ≈ demi-notional de la jambe long
                        if mode == "neutral":
                            n_long = sum(1 for cl in cells if cl["side"] == "long")
                            lean = 1.0
                            if use_funding:
                                rnow = _funding_at(funding, prev_ts, ts)
                                lean = 1.0 + cfg["funding_lean"] * (1.0 if rnow > 0 else (-1.0 if rnow < 0 else 0.0))
                            hedge_notional = max(0.0, 0.5 * n_long * rung * lean)
                            if hedge_notional > 0 and c > 0:
                                hedge_qty = hedge_notional / c
                                hedge_entry = c
                                fees += hedge_notional * (fee + slip)   # ouverture hedge taker
                    active = True
                    deployments += 1
                    atr_deploy = atr

        # ---- gestion active ----
        if active:
            active_bars += 1
            do_cut, motif = gl._cut(prep, i, cfg, lines, atr_deploy)
            if do_cut:
                for cl in cells:
                    if cl["side"] == "long" and cl["state"] == "coin":
                        q = rung / c
                        realized += q * (c - cl["entry"]); fees += rung * (fee + slip); cl["state"] = "cash"
                    elif cl["side"] == "short" and cl["state"] == "short":
                        q = rung / c
                        realized += q * (cl["entry"] - c); fees += rung * (fee + slip); cl["state"] = "flat"
                if hedge_qty:                                   # solde le hedge au marché
                    realized += hedge_qty * (hedge_entry - c); fees += hedge_qty * c * (fee + slip); hedge_qty = 0.0
                active = False; cuts += 1; last_cut = i
                cut_motifs[motif] = cut_motifs.get(motif, 0) + 1
            else:
                for cl in cells:
                    if cl["side"] == "long" and cl["state"] == "cash" and low <= cl["lo"]:
                        fees += rung * fee; cl["state"] = "coin"; cl["entry"] = cl["lo"]; n_buys += 1
                    elif cl["side"] == "long" and cl["state"] == "coin" and h >= cl["hi"]:
                        q = rung / cl["hi"]; realized += q * (cl["hi"] - cl["entry"])
                        fees += rung * fee; cl["state"] = "cash"; n_sells += 1
                    elif cl["side"] == "short" and cl["state"] == "flat" and h >= cl["hi"]:
                        fees += rung * fee; cl["state"] = "short"; cl["entry"] = cl["hi"]; n_buys += 1
                    elif cl["side"] == "short" and cl["state"] == "short" and low <= cl["lo"]:
                        q = rung / cl["lo"]; realized += q * (cl["entry"] - cl["lo"])
                        fees += rung * fee; cl["state"] = "flat"; n_sells += 1

        # ---- funding (perp) + borrow (marge short) sur l'intervalle ----
        if use_funding:
            rate = _funding_at(funding, prev_ts, ts)
            if rate:
                fund_tot += funding_pnl(_net_delta(), c, rate)
        if borrow_day:
            short_notional = sum(rung for cl in cells
                                 if cl["side"] == "short" and cl["state"] == "short")
            borrow_tot += short_notional * borrow_day * (bar_h / 24.0)
        prev_ts = ts

        # ---- mark-to-market (convention grid_lab : q = rung/c, notional constant/rung) ----
        latent = 0.0
        if active and c > 0:
            for cl in cells:
                if cl["side"] == "long" and cl["state"] == "coin":
                    latent += (rung / c) * (c - cl["entry"])
                elif cl["side"] == "short" and cl["state"] == "short":
                    latent += (rung / c) * (cl["entry"] - c)
        hedge_latent = hedge_qty * (hedge_entry - c) if hedge_qty else 0.0
        equity = realized - fees + latent + hedge_latent + fund_tot - borrow_tot
        pnls.append(equity - equity_prev)
        equity_prev = equity
        n_open = sum(1 for cl in cells
                     if (cl["side"] == "long" and cl["state"] == "coin")
                     or (cl["side"] == "short" and cl["state"] == "short")) if active else 0
        exposure_max = max(exposure_max, n_open * rung)

    # latent final (convention grid_lab : q = rung/cc)
    latent_final = 0.0
    cc = prep["closes"][n - 1]
    if active and cc > 0:
        for cl in cells:
            if cl["side"] == "long" and cl["state"] == "coin":
                latent_final += (rung / cc) * (cc - cl["entry"])
            elif cl["side"] == "short" and cl["state"] == "short":
                latent_final += (rung / cc) * (cl["entry"] - cc)
    if hedge_qty:
        latent_final += hedge_qty * (hedge_entry - cc)

    pic = dd = cours = 0.0
    for pv in pnls:
        cours += pv; pic = max(pic, cours); dd = min(dd, cours - pic)
    bh_return = (cc / prep["closes"][warmup] - 1.0) if prep["closes"][warmup] else 0.0
    viable, cost_ar = gl.regle_dor(cfg["spacing"], cfg["fee_bps"], cfg["slip_bps"])

    return {
        "total_pnl": round(equity_prev, 4), "grid_profit": round(realized, 4),
        "latent_final": round(latent_final, 4), "fees": round(fees, 4),
        "funding_pnl_total": round(fund_tot, 4), "borrow_total": round(borrow_tot, 4),
        "net_delta_final": round(_net_delta(), 6),
        "n_buys": n_buys, "n_sells": n_sells, "cycles": n_sells,
        "deployments": deployments, "cuts": cuts, "cut_motifs": cut_motifs,
        "max_dd": round(dd, 4), "exposure_max": round(exposure_max, 4),
        "exposure_cap": round(exposure_cap, 4),
        "frac_active": round(active_bars / max(1, len(pnls)), 3),
        "viable_3x": viable, "cost_ar_frac": round(cost_ar, 5),
        "bh_return": round(bh_return, 5), "warmup": warmup,
        "bars": len(pnls), "pnls": pnls,
    }


def _bar_hours(candles):
    """Durée d'une barre en heures (médiane des deltas ts). PUR. Défaut 1.0."""
    if len(candles) < 3:
        return 1.0
    deltas = sorted(candles[k + 1][0] - candles[k][0] for k in range(min(20, len(candles) - 1)))
    d = deltas[len(deltas) // 2]
    return (d / 3_600_000.0) if d > 0 else 1.0
