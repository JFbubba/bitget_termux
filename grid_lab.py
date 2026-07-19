"""
grid_lab.py — banc de MESURE du grid trading (backtest dédié, LECTURE SEULE).

Classement : SAFE. Aucun ordre, aucune écriture réseau de trading — sorties =
console + un JSON de résultats (.grid_lab_result.json, gitignoré). Défaut OFF :
ce module n'a AUCUN chemin d'exécution réelle (pas de spot_trader, pas de noyau
`bitget_execute`) ; il rejoue une grille sur des bougies historiques. Un éventuel
branchement live (cron) resterait un opt-in `.env` (GRID_LAB_ENABLED, défaut OFF)
à décider par le propriétaire — il n'est PAS câblé ici.

Pourquoi un banc À PART (comme mm_lab §94) : le strategy_lab (§68) juge des
stratégies DIRECTIONNELLES (signal ∈ {-1,0,+1} × rendement forward) ; le
strat_grid existant y est un SIGNAL de range arithmétique. Ici on mesure une
grille à INVENTAIRE non-directionnelle (barreaux d'achat/vente géométriques) dont
le P&L vient des FILLS qui oscillent dans une plage, pas d'un pari de direction —
donc mécanique de fills façon mm_lab, pas signal×rendement.

SYNTHÈSE OPTIMISÉE mesurée (traité distillé — cf. docs/GRID_STRATEGIES.md) :
  • espacement GÉOMÉTRIQUE (chaque niveau à % constant), N = ln(hi/lo)/ln(1+g) ;
  • bornes ATR-adaptatives : centre = VWAP, [centre−k·ATR, centre+k·ATR], k∈[2,4] ;
  • filtre de RÉGIME (activation) : ADX < seuil ET largeur Bollinger stable ET
    volume non-expansif → n'active la grille qu'en CONSOLIDATION ;
  • COUPE sur cassure (sortie disciplinée) : clôture hors range OU ADX élevé OU
    expansion ATR OU pic de volume → liquide l'inventaire au marché et reste FLAT
    jusqu'à la prochaine consolidation (jamais d'élargissement automatique = anti-DCA) ;
  • porte ≥3× coûts (règle d'or) : espacement g ≥ 3·(2·frais + slippage) sinon rejet ;
  • comptabilité TOTAL-P&L = grid-profit réalisé + P&L LATENT de l'inventaire
    (mark-to-market) − frais — JAMAIS le grid-profit seul (piège documenté) ;
  • cap d'exposition ANTI-MARTINGALE : barreaux de taille FIXE, exposition bornée
    par max_levels·rung (aucun doublement, aucun ajout de niveau après lancement).

HONNÊTETÉS DU MODÈLE (à lire avant de croire un chiffre) :
  • un fill de grille exige que le prix TRAVERSE le niveau dans la barre
    (low ≤ barreau d'achat / high ≥ barreau de vente) — SANS file d'attente : cas
    FAVORABLE (le réel, priorité temps/prix + latence, fera MOINS bien) → BORNE SUP ;
  • une même barre ne fait qu'UNE transition par cellule (pas d'aller-retour
    intra-barre) : conservateur ;
  • fills de grille = MAKER (ordres limites) ; le seed initial et la coupe sur
    cassure = TAKER (frais maker + slippage) — réaliste ;
  • frais maker de référence = 8 bps/côté (spot, déduction BGB MESURÉE) ; exposé
    en paramètre et STRESSÉ ×{1, 1.5, 2} ;
  • bougies via candles_history (endpoint MIX/futures = proxy fidèle du prix spot
    BTC/ETH pour la trajectoire) ; le grid réel serait SPOT (détenir la coin).

CLI (CONSULTATION, lecture seule) :
    python grid_lab.py --status            # dernier résultat mesuré (aucun réseau)
    python grid_lab.py --run               # BTC+ETH, échelle TF complète M1..W1
    python grid_lab.py --run --quick       # sous-ensemble H1/H4/D1 (rapide)
    python grid_lab.py --run --sol         # ajoute SOLUSDT
"""
import json
import math
import time
from pathlib import Path

RESULT = Path(__file__).resolve().parent / ".grid_lab_result.json"

# Frais maker MESURÉS sur nos fills réels (mm_lab §94, feeDetail spot) : 10 bps de
# base, 8 bps avec la déduction BGB ACTIVE. Référence spot du banc = 8 bps/côté.
FEE_MAKER_BGB_BPS = 8.0
FEE_MAKER_BPS = 10.0

# Échelle COMPLÈTE de timeframes (ERR-001, NON négociable) + profondeur visée par TF
# (compromis nombre-de-bougies / poids réseau). Le grid W1 a peu de barres = faible
# puissance statistique (histoire crypto courte) : c'est honnête, on le rapporte.
TF_LADDER = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]
TF_GRAN = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
           "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w"}
TF_JOURS = {"M1": 3, "M5": 14, "M15": 45, "M30": 90,
            "H1": 180, "H4": 720, "D1": 1800, "W1": 2200}
TF_QUICK = ["H1", "H4", "D1"]

# Barre du banc (esprit PROMOTE du lab + garde-fous López de Prado) : une config
# ne « survit » que si elle est robuste OOS ET déflatée ET bat le buy-and-hold ET
# résiste au stress de coûts.
BARRE = {"pbo_max": 0.5, "dsr_min": 0.95, "folds_pos_min": 0.60}


# ==================== indicateurs purs et testables ====================

def _n_levels(lo, hi, spacing):
    """Nombre de niveaux géométriques entre lo et hi à espacement `spacing` (fraction).
    N ≈ ln(hi/lo) / ln(1+g). PUR."""
    if lo <= 0 or hi <= lo or spacing <= 0:
        return 0
    return int(math.log(hi / lo) / math.log(1.0 + spacing))


def grid_lines(lo, hi, spacing, max_levels):
    """Barreaux géométriques lo·(1+g)^j, bornés à max_levels cellules. PUR.
    Retourne [] si dégénéré (moins de 2 cellules)."""
    n = min(int(max_levels), _n_levels(lo, hi, spacing))
    if n < 2:
        return []
    return [lo * (1.0 + spacing) ** j for j in range(n + 1)]


def regle_dor(spacing, fee_bps, slip_bps):
    """Règle d'or (≥3× coûts A/R). PUR. Retourne (ok, cout_ar_fraction).
    coût A/R = 2·frais + 2·slippage (deux fills : achat + vente)."""
    cost_ar = 2.0 * (fee_bps + slip_bps) / 10_000.0
    return spacing >= 3.0 * cost_ar, cost_ar


def dmi_adx(highs, lows, closes, period=14):
    """ADX de Wilder (Directional Movement Index), aligné à l'indice de barre
    absolu (None pendant le warmup ~2·period). PUR. N'EXISTE PAS ailleurs en prod
    (seulement dans des labos scratchpad) — implémentation propre portée ici,
    testée (test_grid_lab_adx_*). Références Wilder 1978."""
    n = len(highs)
    adx = [None] * n
    if n < 2 * period + 2:
        return adx
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > dn and up > 0) else 0.0
        minus_dm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]))
    atr_s = sum(tr[1:period + 1])
    pdm_s = sum(plus_dm[1:period + 1])
    mdm_s = sum(minus_dm[1:period + 1])

    def _dx(pdm, mdm, atr):
        if atr <= 0:
            return 0.0
        pdi = 100.0 * pdm / atr
        mdi = 100.0 * mdm / atr
        s = pdi + mdi
        return (100.0 * abs(pdi - mdi) / s) if s > 0 else 0.0

    dxs = [_dx(pdm_s, mdm_s, atr_s)]
    dx_idx = [period]
    for i in range(period + 1, n):
        atr_s = atr_s - atr_s / period + tr[i]
        pdm_s = pdm_s - pdm_s / period + plus_dm[i]
        mdm_s = mdm_s - mdm_s / period + minus_dm[i]
        dxs.append(_dx(pdm_s, mdm_s, atr_s))
        dx_idx.append(i)
    if len(dxs) >= period:
        val = sum(dxs[:period]) / period
        adx[dx_idx[period - 1]] = val
        for k in range(period, len(dxs)):
            val = (val * (period - 1) + dxs[k]) / period
            adx[dx_idx[k]] = val
    return adx


# ==================== configuration ====================

def config(spacing=0.007, k_atr=2.5, fee_bps=FEE_MAKER_BGB_BPS, slip_bps=2.0,
           rung_notional=5.0, max_levels=40, adx_max=22.0, adx_exit=30.0,
           atr_exit_mult=1.8, vol_spike=3.0, bb_expand_max=1.4, vol_expand_max=1.6,
           window=100, cooldown_bars=3, atr_period=14, adx_period=14,
           bb_period=20, vol_period=20, core_notional=0.0):
    """Config du banc (dict plat, esprit mm_lab.config_banc). PUR, sans env.
    cooldown_bars = attente MINIMALE après une coupe avant de re-tester le régime
    (évite de redéployer instantanément dans une cassure en cours)."""
    return {"spacing": spacing, "k_atr": k_atr, "fee_bps": fee_bps,
            "slip_bps": slip_bps, "rung_notional": rung_notional,
            "max_levels": max_levels, "adx_max": adx_max, "adx_exit": adx_exit,
            "atr_exit_mult": atr_exit_mult, "vol_spike": vol_spike,
            "bb_expand_max": bb_expand_max, "vol_expand_max": vol_expand_max,
            "window": window, "cooldown_bars": cooldown_bars,
            "atr_period": atr_period, "adx_period": adx_period,
            "bb_period": bb_period, "vol_period": vol_period,
            "core_notional": core_notional}


def config_grille():
    """Sweep HONNÊTE et PETIT (n_trials maîtrisé pour la déflation) : espacement ×
    k_atr. Le 0.4 % est SOUS la règle d'or à 8 bps → sera marqué non-viable (montre
    la porte). Pas d'optimisation fine = moins de surapprentissage."""
    grille = []
    for spacing in (0.004, 0.007, 0.012, 0.02):
        for k in (2.5, 3.5):
            grille.append((f"g={spacing * 100:.1f}%·k={k}",
                           config(spacing=spacing, k_atr=k)))
    return grille


# ==================== préparation des séries ====================

def _prepare(candles, cfg):
    """Séries pleines (None pendant warmup) : ATR (reuse indicators), ADX (Wilder),
    largeur de Bollinger + sa SMA, SMA de volume. PUR (calcul)."""
    import indicators
    n = len(candles)
    highs = [r[2] for r in candles]
    lows = [r[3] for r in candles]
    closes = [r[4] for r in candles]
    vols = [r[5] for r in candles]
    atr = [None] * n
    try:
        dicts = [{"high": r[2], "low": r[3], "close": r[4]} for r in candles]
        vals = indicators.calculate_atr(dicts, cfg["atr_period"])
        for j, v in enumerate(vals):
            idx = cfg["atr_period"] + j
            if idx < n:
                atr[idx] = v
    except Exception:
        pass
    adx = dmi_adx(highs, lows, closes, cfg["adx_period"])
    p = cfg["bb_period"]
    bbw = [None] * n
    for i in range(p - 1, n):
        w = closes[i - p + 1:i + 1]
        m = sum(w) / p
        if m > 0:
            sd = (sum((x - m) ** 2 for x in w) / p) ** 0.5
            bbw[i] = 4.0 * sd / m                     # largeur ≈ (haut−bas)/mid, k=2
    bbw_sma = [None] * n
    for i in range(n):
        seg = [bbw[j] for j in range(max(0, i - p + 1), i + 1) if bbw[j] is not None]
        if seg:
            bbw_sma[i] = sum(seg) / len(seg)
    vp = cfg["vol_period"]
    vol_sma = [None] * n
    for i in range(vp - 1, n):
        vol_sma[i] = sum(vols[i - vp + 1:i + 1]) / vp
    return {"highs": highs, "lows": lows, "closes": closes, "vols": vols,
            "atr": atr, "adx": adx, "bbw": bbw, "bbw_sma": bbw_sma,
            "vol_sma": vol_sma}


def _regime_ok(prep, i, cfg):
    """Filtre d'ACTIVATION : consolidation = ADX bas ET Bollinger stable ET volume
    non-expansif. PUR. False si l'une des séries manque (fail-safe)."""
    adx = prep["adx"][i]
    bbw, bbw_sma = prep["bbw"][i], prep["bbw_sma"][i]
    vol_sma = prep["vol_sma"][i]
    if adx is None or bbw is None or bbw_sma is None or vol_sma is None:
        return False
    if adx >= cfg["adx_max"]:
        return False
    if bbw_sma > 0 and bbw > cfg["bb_expand_max"] * bbw_sma:
        return False
    if vol_sma > 0 and prep["vols"][i] > cfg["vol_expand_max"] * vol_sma:
        return False
    return True


def _cut(prep, i, cfg, lines, atr_deploy):
    """Conditions de COUPE sur cassure (sortie). PUR. Retourne (bool, motif)."""
    c = prep["closes"][i]
    if c < lines[0]:
        return True, "sous_range"
    if c > lines[-1]:
        return True, "sur_range"
    adx = prep["adx"][i]
    if adx is not None and adx > cfg["adx_exit"]:
        return True, "adx"
    atr = prep["atr"][i]
    if atr is not None and atr_deploy and atr > cfg["atr_exit_mult"] * atr_deploy:
        return True, "atr_expansion"
    vs = prep["vol_sma"][i]
    if vs and prep["vols"][i] > cfg["vol_spike"] * vs:
        return True, "volume"
    return False, ""


# ==================== simulation barre-par-barre ====================

def simulate(candles, cfg):
    """Rejoue la grille barre par barre. PUR. candles = [[ts,o,h,l,c,v], ...] triées
    asc. Fail-safe : retourne None si insuffisant / incohérent (jamais d'exception
    qui remonte). Comptabilité TOTAL-P&L = grid-profit réalisé + latent − frais."""
    try:
        import technicals as tk
    except Exception:
        tk = None
    n = len(candles)
    warmup = max(cfg["window"], 2 * cfg["adx_period"] + 2, cfg["bb_period"],
                 cfg["vol_period"]) + 1
    if n < warmup + 30:
        return None
    prep = _prepare(candles, cfg)
    fee = cfg["fee_bps"] / 10_000.0
    slip = cfg["slip_bps"] / 10_000.0
    rung = cfg["rung_notional"]
    exposure_cap = cfg["max_levels"] * rung           # cap anti-martingale, AVANT lancement

    active = False
    lines = []
    cells = []              # {"lo","hi","state":"coin"/"cash","entry"}
    atr_deploy = None
    inv_qty = 0.0
    realized = 0.0
    fees = 0.0
    core_qty = 0.0
    core_entry = 0.0
    pnls = []
    equity_prev = 0.0
    exposure_max = 0.0
    deployments = cuts = n_sells = n_buys = 0
    active_bars = 0
    cut_motifs = {}
    last_cut = -10 ** 9

    for i in range(warmup, n):
        c = prep["closes"][i]
        h = prep["highs"][i]
        low = prep["lows"][i]

        # ---- déploiement DÈS qu'une consolidation est détectée (cooldown après coupe) ----
        if not active and (i - last_cut) >= cfg["cooldown_bars"] and _regime_ok(prep, i, cfg):
            atr = prep["atr"][i]
            window = candles[i - cfg["window"] + 1:i + 1]
            center = None
            if tk is not None:
                try:
                    center = tk.vwap([{"high": r[2], "low": r[3], "close": r[4],
                                       "volume": r[5]} for r in window])
                except Exception:
                    center = None
            if center is None:
                center = sum(r[4] for r in window) / len(window)
            if atr and center and atr > 0:
                lo = center - cfg["k_atr"] * atr
                hi = center + cfg["k_atr"] * atr
                lns = grid_lines(lo, hi, cfg["spacing"], cfg["max_levels"])
                if lns:
                    lines = lns
                    cells = []
                    for j in range(len(lines) - 1):
                        above = lines[j] >= c            # cellule au-dessus du prix → seed COIN
                        cells.append({"lo": lines[j], "hi": lines[j + 1],
                                      "state": "coin" if above else "cash",
                                      "entry": c})
                    # seed de l'inventaire des cellules COIN (achat au marché = taker)
                    seeds = sum(1 for cl in cells if cl["state"] == "coin")
                    if seeds:
                        q = rung / c
                        inv_qty += seeds * q
                        fees += seeds * rung * (fee + slip)
                    # poche CORE optionnelle (hybride core+grille) — B&H séparé, non revendu
                    if cfg["core_notional"] > 0 and core_qty == 0:
                        core_qty = cfg["core_notional"] / c
                        core_entry = c
                        fees += cfg["core_notional"] * (fee + slip)
                    active = True
                    deployments += 1
                    atr_deploy = atr

        # ---- gestion de la grille active ----
        if active:
            active_bars += 1
            do_cut, motif = _cut(prep, i, cfg, lines, atr_deploy)
            if do_cut:
                # liquide l'inventaire de grille au marché (taker) — le grid-profit
                # RÉEL inclut cette coupe (piège de la cassure honoré)
                q = rung / c
                for cl in cells:
                    if cl["state"] == "coin":
                        realized += q * (c - cl["entry"])
                        fees += rung * (fee + slip)
                        inv_qty -= q
                        cl["state"] = "cash"
                active = False
                cuts += 1
                last_cut = i
                cut_motifs[motif] = cut_motifs.get(motif, 0) + 1
            else:
                # fills de grille (maker) — 1 transition max par cellule (état de début de barre)
                for cl in cells:
                    if cl["state"] == "cash" and low <= cl["lo"]:
                        q = rung / cl["lo"]
                        inv_qty += q
                        fees += rung * fee
                        cl["state"] = "coin"
                        cl["entry"] = cl["lo"]
                        n_buys += 1
                    elif cl["state"] == "coin" and h >= cl["hi"]:
                        q = rung / cl["hi"]
                        realized += q * (cl["hi"] - cl["entry"])
                        inv_qty -= q
                        fees += rung * fee
                        cl["state"] = "cash"
                        n_sells += 1

        # ---- mark-to-market (TOTAL-P&L) ----
        latent = 0.0
        if active:
            q = rung / c
            for cl in cells:
                if cl["state"] == "coin":
                    latent += q * (c - cl["entry"])
        core_latent = core_qty * (c - core_entry) if core_qty else 0.0
        equity = realized - fees + latent + core_latent
        pnls.append(equity - equity_prev)
        equity_prev = equity
        # exposition au COÛT (Σ barreaux détenus × notional) = vraie garantie
        # anti-martingale, bornée par le cap ; la valeur de marché peut dériver
        # au-dessus (c'est du latent, déjà compté ailleurs).
        n_coin = sum(1 for cl in cells if cl["state"] == "coin") if active else 0
        exposure_max = max(exposure_max, n_coin * rung + cfg["core_notional"])

    latent_final = 0.0
    if active and cells:
        cc = prep["closes"][n - 1]
        q = rung / cc
        for cl in cells:
            if cl["state"] == "coin":
                latent_final += q * (cc - cl["entry"])
    core_latent_final = core_qty * (prep["closes"][n - 1] - core_entry) if core_qty else 0.0

    pic = dd = cours = 0.0
    for pv in pnls:
        cours += pv
        pic = max(pic, cours)
        dd = min(dd, cours - pic)

    bh_return = (prep["closes"][n - 1] / prep["closes"][warmup] - 1.0) if prep["closes"][warmup] else 0.0
    viable, cost_ar = regle_dor(cfg["spacing"], cfg["fee_bps"], cfg["slip_bps"])
    total = equity_prev
    grid_profit = realized

    return {
        "total_pnl": round(total, 4),
        "grid_profit": round(grid_profit, 4),
        "latent_final": round(latent_final + core_latent_final, 4),
        "fees": round(fees, 4),
        "n_buys": n_buys, "n_sells": n_sells, "cycles": n_sells,
        "deployments": deployments, "cuts": cuts, "cut_motifs": cut_motifs,
        "max_dd": round(dd, 4), "exposure_max": round(exposure_max, 4),
        "exposure_cap": round(exposure_cap, 4),
        "frac_active": round(active_bars / max(1, len(pnls)), 3),
        "viable_3x": viable, "cost_ar_frac": round(cost_ar, 5),
        "bh_return": round(bh_return, 5), "warmup": warmup,
        "bars": len(pnls), "pnls": pnls,
    }


# ==================== métriques / validation ====================

def _sharpe(returns):
    import agent_validation as av
    return av.sharpe(returns)


def _skew_kurt(returns):
    n = len(returns)
    if n < 3:
        return 0.0, 3.0
    m = sum(returns) / n
    sd = (sum((x - m) ** 2 for x in returns) / n) ** 0.5
    if sd <= 1e-12:
        return 0.0, 3.0
    z = [(x - m) / sd for x in returns]
    return sum(v ** 3 for v in z) / n, sum(v ** 4 for v in z) / n


def _variance(xs):
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _oos_metrics(cfg, res, closes, frac_train=0.6):
    """Découpe TRAIN/TEST le long du temps ; sélection sur TRAIN, jugement OOS.
    Retourne les métriques du segment OOS (test)."""
    import agent_validation as av
    import backtest_brain as bt
    pnls = res["pnls"]
    cut = int(len(pnls) * frac_train)
    train, test = pnls[:cut], pnls[cut:]
    if len(test) < 20:
        return None
    sr = av.sharpe(test)
    sk, ku = _skew_kurt(test)
    wf = bt.walk_forward(test, k=5)
    folds_pos = (sum(1 for x in wf if x > 0) / len(wf)) if wf else 0.0
    total_oos = sum(test)
    # B&H apparié : même capital que l'exposition RÉELLEMENT engagée
    warmup = res["warmup"]
    i0 = warmup + cut
    bh_oos = (closes[-1] / closes[i0] - 1.0) if i0 < len(closes) and closes[i0] else 0.0
    bh_pnl_matched = res["exposure_max"] * bh_oos
    return {"train_sharpe": round(av.sharpe(train), 4), "oos_sharpe": round(sr, 4),
            "oos_total": round(total_oos, 4), "folds_pos": round(folds_pos, 3),
            "wf": [round(x, 5) for x in wf], "bh_oos": round(bh_oos, 5),
            "bh_pnl_matched": round(bh_pnl_matched, 4),
            "beats_bh": total_oos > bh_pnl_matched, "skew": round(sk, 3),
            "kurt": round(ku, 3), "n_oos": len(test)}


def _cost_stress(cfg, candles, frac_train=0.6):
    """Stress de coûts (AutoQuant 2512.22476) : rejoue la config sous frais ×{1.5, 2}.
    Survivant = OOS total > 0 aux DEUX multiplicateurs. Retourne dict."""
    out = {}
    base = cfg["fee_bps"]
    closes = [r[4] for r in candles]
    for mult in (1.5, 2.0):
        c2 = dict(cfg)
        c2["fee_bps"] = base * mult
        r2 = simulate(candles, c2)
        if not r2:
            out[f"x{mult}"] = None
            continue
        pnls = r2["pnls"]
        cutp = int(len(pnls) * frac_train)
        out[f"x{mult}"] = round(sum(pnls[cutp:]), 4)
    survives = all(v is not None and v > 0 for v in out.values())
    return {"stress": out, "survives_stress": survives}


def evaluate_symbol_tf(candles, cfg_list=None):
    """Sweep de configs sur un (symbole, TF) : PBO croisé, DSR déflatée par n_trials,
    sélection TRAIN → jugement OOS, stress de coûts, verdict. Fail-safe."""
    import agent_validation as av
    import backtest_brain as bt
    cfg_list = cfg_list or config_grille()
    closes = [r[4] for r in candles]
    sims = {}
    for label, cfg in cfg_list:
        try:
            r = simulate(candles, cfg)
        except Exception:
            r = None
        if r:
            sims[label] = (cfg, r)
    if not sims:
        return None
    series = {lab: sims[lab][1]["pnls"] for lab in sims}
    sh_full = {lab: _sharpe(series[lab]) for lab in series}
    var_sr = _variance(list(sh_full.values()))
    n_trials = max(2, len(sims))
    pbo_res = bt.pbo(series, n_blocks=8)

    viable = {lab for lab in sims if sims[lab][1]["viable_3x"]}
    pool = viable or set(sims)                    # si rien de viable, on juge quand même (flag)
    # sélection : meilleur Sharpe TRAIN parmi les viables
    best_lab, best_train = None, -1e9
    oos_by_lab = {}
    for lab in pool:
        m = _oos_metrics(sims[lab][0], sims[lab][1], closes)
        if not m:
            continue
        oos_by_lab[lab] = m
        if m["train_sharpe"] > best_train:
            best_train, best_lab = m["train_sharpe"], lab
    if best_lab is None:
        return None
    cfg_best, res_best = sims[best_lab]
    oos = oos_by_lab[best_lab]
    sr = oos["oos_sharpe"]
    n_oos = oos["n_oos"]
    dsr = av.deflated_sharpe(sr, n_oos, oos["skew"], oos["kurt"], n_trials, var_sr)
    stress = _cost_stress(cfg_best, candles)

    survives = (oos["oos_total"] > 0 and sr > 0
                and oos["folds_pos"] >= BARRE["folds_pos_min"]
                and (pbo_res.get("pbo") is not None and pbo_res["pbo"] < BARRE["pbo_max"])
                and dsr >= BARRE["dsr_min"]
                and oos["beats_bh"]
                and stress["survives_stress"]
                and best_lab in viable)
    return {"chosen": best_lab, "viable_3x": best_lab in viable,
            "cfg": {k: cfg_best[k] for k in ("spacing", "k_atr", "fee_bps", "rung_notional")},
            "full": {k: v for k, v in res_best.items() if k != "pnls"},
            "oos": oos, "pbo": pbo_res.get("pbo"), "dsr": round(dsr, 4),
            "n_trials": n_trials, "var_sr": round(var_sr, 6),
            **stress, "survives": survives}


# ==================== orchestration ====================

def run(symbols=("BTCUSDT", "ETHUSDT"), tfs=None, verbose=True):
    """Télécharge (incrémental, lecture seule), rejoue le sweep sur l'échelle TF,
    écrit le JSON et retourne le rapport. Aucun ordre. Fail-safe par (sym,TF)."""
    import candles_history as ch
    tfs = list(tfs or TF_LADDER)
    resultats, lignes = [], []
    for s in symbols:
        for tf in tfs:
            gran = TF_GRAN[tf]
            jours = TF_JOURS[tf]
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
            ev = evaluate_symbol_tf(candles)
            if not ev:
                lignes.append(f"⚠️ {s} {tf} : simulation vide — sauté")
                continue
            ev["symbol"], ev["tf"], ev["n_bars"] = s, tf, len(candles)
            resultats.append(ev)
            f = ev["full"]
            mark = "✅" if ev["survives"] else ("·" if ev["viable_3x"] else "✗")
            lignes.append(
                f"{mark} {s} {tf} [{ev['chosen']}] : TOTAL {f['total_pnl']:+.2f}$ "
                f"(grid {f['grid_profit']:+.2f} / latent {f['latent_final']:+.2f} / "
                f"frais {f['fees']:.2f}) · cycles {f['cycles']} · OOS {ev['oos']['oos_total']:+.2f}$ "
                f"Sh {ev['oos']['oos_sharpe']:+.2f} folds+ {ev['oos']['folds_pos']} · "
                f"PBO {ev['pbo']} DSR {ev['dsr']} · vs B&H {'bat' if ev['oos']['beats_bh'] else 'sous'} "
                f"· stress {'OK' if ev['survives_stress'] else 'KO'} · viable3x {ev['viable_3x']}")
    n_surv = sum(1 for r in resultats if r["survives"])
    out = {"ts": int(time.time()), "symbols": list(symbols), "tfs": tfs,
           "fee_maker_bps": FEE_MAKER_BGB_BPS, "barre": BARRE,
           "n_configs_testees": len(resultats), "n_survivantes": n_surv,
           "resultats": resultats,
           "note": ("BORNE SUPÉRIEURE (fill sans file d'attente, 1 transition/cellule/barre, "
                    "seed+coupe en taker) — le réel fera MOINS bien. Comptabilité TOTAL-P&L "
                    "(grid+latent−frais). Grid en bull = souvent du BETA (latent) : le juge = "
                    "vs buy-and-hold apparié. Lecture seule, aucun ordre.")}
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
        return {"error": "aucun résultat — lancer `python grid_lab.py --run`"}
    try:
        return json.loads(RESULT.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"résultat illisible ({type(e).__name__})"}


def main():
    import sys
    args = sys.argv[1:]
    if "--run" in args:
        symbols = ["BTCUSDT", "ETHUSDT"]
        if "--sol" in args:
            symbols.append("SOLUSDT")
        tfs = TF_QUICK if "--quick" in args else TF_LADDER
        r = run(symbols, tfs)
        print(f"=== GRID LAB (banc grid trading, LECTURE SEULE) — {', '.join(symbols)} "
              f"· TF {'/'.join(tfs)} · frais maker {FEE_MAKER_BGB_BPS} bps (BGB) ===")
        print(f"barre : PBO<{BARRE['pbo_max']} · DSR≥{BARRE['dsr_min']} · folds+≥{BARRE['folds_pos_min']} "
              f"· bat B&H · survit stress ×2 · règle d'or 3×coûts")
        print(r["rapport"])
        print(f"\n{r['n_survivantes']}/{r['n_configs_testees']} (sym,TF) SURVIVENT toutes les portes.")
        print(r["note"])
        print("VERDICT: SAFE")
        return
    # défaut = statut (consultation, aucun réseau)
    st = status()
    print("=== GRID LAB (banc grid trading, LECTURE SEULE) — STATUT ===")
    if st.get("error"):
        print(st["error"])
    else:
        import datetime
        d = datetime.datetime.fromtimestamp(st["ts"], datetime.timezone.utc)
        print(f"dernier run {d:%Y-%m-%d %H:%M UTC} · {st['n_survivantes']}/{st['n_configs_testees']} "
              f"survivantes · frais {st['fee_maker_bps']} bps")
        for r in st["resultats"]:
            f = r["full"]
            mark = "✅" if r["survives"] else ("·" if r["viable_3x"] else "✗")
            print(f"  {mark} {r['symbol']} {r['tf']} : TOTAL {f['total_pnl']:+.2f}$ "
                  f"OOS {r['oos']['oos_total']:+.2f}$ PBO {r['pbo']} DSR {r['dsr']}")
    print("Défaut OFF : aucun chemin d'exécution réelle. VERDICT: SAFE")


if __name__ == "__main__":
    main()
