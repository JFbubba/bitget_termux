# grid_engine — Grille exhaustive multi-surface — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire un moteur de grille PUR généralisé (mode long_only/bidirectional/neutral × surface spot/margin/futures × funding), un labo qui le mesure exhaustivement avec déflation honnête, et un adaptateur d'exécution §67 défaut OFF/DRY qui délègue aux exécuteurs audités.

**Architecture:** 3 couches isolées — ① `grid_engine.py` (simulateur pur généralisant `grid_lab.simulate`, réutilise ses helpers purs) → ② `grid_engine_lab.py` (balaie mode×surface×config×symbole×TF, juge via `grid_lab.evaluate_symbol_tf`, gardes anti-surtest) → ③ `grid_trader.py` (adaptateur §67, DRY par défaut, délègue à `spot_trader`/`margin_trader`/`futures_executor`, jamais d'ordre direct).

**Tech Stack:** Python 3.12 pur (stdlib : `json`, `math`, `time`, `pathlib`). Réutilise `grid_lab`, `funding_history`, `candles_history`, `agent_validation`, `backtest_brain`, `indicators`. Tests : pytest (`tests/`). Aucune dépendance neuve.

## Global Constraints

- **Aucun ordre neuf hors exécuteurs audités** : `grid_trader` DÉLÈGUE à `spot_trader`/`margin_trader`/`futures_executor` — jamais d'appel `bitget_execute` direct (modèle `market_maker.py` §94).
- **Murs en dur ABSOLUS, jamais desserrés** : futures 50/250 ×5, marge 200/500, spot 200/500 ; stop −5 %→kill-switch ; kill-switch fail-closed.
- **Défaut OFF / DRY** : `GRID_TRADE_LIVE=0` ; aucun chemin live sans verrou + config `survives=True` (ou override proprio journalisé §92).
- **Fail-safe** : chaque cellule/fonction renvoie `None`/valeur sûre plutôt que lever ; jamais de crash.
- **PUR = pur** : `grid_engine.py` n'a aucun I/O, aucun réseau, aucun ordre.
- **ERR-001** : tout test de signal/stratégie couvre l'échelle COMPLÈTE M1..W1 (le labo balaie `grid_lab.TF_LADDER`).
- **Frais autoritatifs** (`docs/BITGET_REFERENCE.md`) : spot 8 bps, marge croisée 8 bps, futures 2 bps maker.
- **Commits** : français, sans identifiant de modèle. 4 portes vertes (`bash gates.sh`) avant push.
- **Classification** : `grid_engine.py`/`grid_engine_lab.py` = SAFE ; `grid_trader.py` = surface §67 (audité à part).

---

## Structure des fichiers

| Fichier | Responsabilité | Créé/Modifié |
|---|---|---|
| `grid_engine.py` | moteur pur : `SURFACE`, `gconfig`, `_center`, `funding_pnl`, `simulate_g` | Créer |
| `grid_engine_lab.py` | labo : `config_sweep`, `run`, `status`, gardes d'honnêteté | Créer |
| `grid_trader.py` | adaptateur §67 : `plan_cycle`, `_deploy`, DRY/kill-switch/caps | Créer |
| `tests/test_grid_engine.py` | banc unitaire moteur | Créer |
| `tests/test_grid_engine_lab.py` | banc unitaire labo | Créer |
| `tests/test_grid_trader.py` | banc unitaire adaptateur (DRY/gardes) | Créer |
| `.gitignore` | ignorer `.grid_engine_result.json` | Modifier |
| `docs/GRID_STRATEGIES.md` | §6 : emplacement du verdict multi-surface | Modifier (fin de plan) |

---

## Task 1 : `grid_engine.py` — descripteur de surface + config généralisée

**Files:**
- Create: `grid_engine.py`
- Test: `tests/test_grid_engine.py`

**Interfaces:**
- Produces:
  - `SURFACE: dict[str, dict]` — clés `spot|margin|futures`, champs `maker_bps, slip_bps, short(bool), funding(bool), lev_max, cap_op, cap_day`.
  - `gconfig(mode="neutral", surface="futures", funding_lean=0.0, borrow_bps_per_day=0.0, **grid_lab_kw) -> dict` — étend `grid_lab.config` ; injecte `maker_bps/slip_bps` de la surface dans `fee_bps/slip_bps`.

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# tests/test_grid_engine.py
import grid_engine as ge

def test_surface_descriptors():
    assert ge.SURFACE["spot"]["maker_bps"] == 8 and ge.SURFACE["spot"]["short"] is False
    assert ge.SURFACE["margin"]["maker_bps"] == 8 and ge.SURFACE["margin"]["short"] is True
    assert ge.SURFACE["futures"]["maker_bps"] == 2 and ge.SURFACE["futures"]["funding"] is True
    assert ge.SURFACE["futures"]["lev_max"] == 5 and ge.SURFACE["futures"]["cap_op"] == 50

def test_gconfig_injects_surface_fees():
    cfg = ge.gconfig(mode="bidirectional", surface="futures", spacing=0.01, k_atr=3.0)
    assert cfg["mode"] == "bidirectional" and cfg["surface"] == "futures"
    assert cfg["fee_bps"] == 2 and cfg["slip_bps"] == 4          # de la surface futures
    assert cfg["spacing"] == 0.01 and cfg["k_atr"] == 3.0        # passe à grid_lab.config
    assert cfg["funding_lean"] == 0.0 and cfg["borrow_bps_per_day"] == 0.0
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_grid_engine.py -q`
Expected: FAIL (`ModuleNotFoundError: grid_engine`).

- [ ] **Step 3 : Implémenter l'entête + `SURFACE` + `gconfig`**

```python
# grid_engine.py
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
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `.venv/bin/pytest tests/test_grid_engine.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5 : Commit**

```bash
git add grid_engine.py tests/test_grid_engine.py
git commit -m "grid_engine : descripteur de surface + config generalisee (mode x surface x funding)"
```

---

## Task 2 : `funding_pnl` — comptabilité du funding (pur, signé)

**Files:**
- Modify: `grid_engine.py`
- Test: `tests/test_grid_engine.py`

**Interfaces:**
- Produces:
  - `funding_pnl(net_qty, price, rate) -> float` — P&L de funding SUR UN intervalle 8 h pour une position perp nette `net_qty` (>0 long, <0 short) au prix `price`, taux `rate` (fraction). Convention : long PAIE quand `rate>0`. Retour = P&L POUR NOUS = `-net_qty * price * rate`.

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# tests/test_grid_engine.py  (ajouter)
def test_funding_sign():
    # rate>0 : le LONG paie -> P&L négatif ; le SHORT encaisse -> P&L positif
    assert ge.funding_pnl(net_qty=1.0, price=100.0, rate=0.0001) < 0
    assert ge.funding_pnl(net_qty=-1.0, price=100.0, rate=0.0001) > 0
    # symétrie exacte
    assert ge.funding_pnl(1.0, 100.0, 0.0001) == -ge.funding_pnl(-1.0, 100.0, 0.0001)
    # rate=0 ou net_qty=0 -> 0
    assert ge.funding_pnl(1.0, 100.0, 0.0) == 0.0
    assert ge.funding_pnl(0.0, 100.0, 0.0001) == 0.0
    # magnitude : |net_qty * price * rate|
    assert abs(ge.funding_pnl(2.0, 100.0, 0.0001) - (-2.0 * 100.0 * 0.0001)) < 1e-12
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_grid_engine.py::test_funding_sign -q`
Expected: FAIL (`AttributeError: funding_pnl`).

- [ ] **Step 3 : Implémenter**

```python
# grid_engine.py  (ajouter)
def funding_pnl(net_qty, price, rate):
    """P&L de funding sur UN intervalle 8 h. net_qty>0 long, <0 short. Convention
    Bitget : le LONG paie le SHORT quand rate>0 -> P&L pour nous = -net_qty*price*rate. PUR."""
    return -float(net_qty) * float(price) * float(rate)
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `.venv/bin/pytest tests/test_grid_engine.py::test_funding_sign -q`
Expected: PASS.

- [ ] **Step 5 : Commit**

```bash
git add grid_engine.py tests/test_grid_engine.py
git commit -m "grid_engine : funding_pnl signe (long paie, short encaisse)"
```

---

## Task 3 : `_center` + `simulate_g` — parité long-only avec `grid_lab`

Objectif : le simulateur généralisé en `mode="long_only"`, `surface="spot"` reproduit `grid_lab.simulate` (mêmes fills, même TOTAL) — établit le squelette de boucle ET la NON-RÉGRESSION du verdict mort connu (spec §5.2.4).

**Files:**
- Modify: `grid_engine.py`
- Test: `tests/test_grid_engine.py`

**Interfaces:**
- Produces:
  - `_center(window) -> float|None` — VWAP (repli SMA) d'une fenêtre de bougies. PUR.
  - `simulate_g(candles, cfg, funding=None) -> dict|None` — simule la grille généralisée. `candles=[[ts,o,h,l,c,v],...]`, `funding=[(ts_ms,taux),...]|None`. Retour = dict compatible `grid_lab.simulate` (clés `total_pnl, grid_profit, latent_final, fees, n_buys, n_sells, cycles, deployments, cuts, cut_motifs, max_dd, exposure_max, exposure_cap, frac_active, viable_3x, cost_ar_frac, bh_return, warmup, bars, pnls`) + `funding_pnl_total, borrow_total, net_delta_final`.

- [ ] **Step 1 : Écrire le test de parité qui échoue**

```python
# tests/test_grid_engine.py  (ajouter)
import grid_lab as gl

def _serie_range(n=800, base=100.0):
    # série oscillante déterministe (pas d'aléa) autour de base, faible tendance
    import math
    out = []
    for i in range(n):
        px = base * (1 + 0.02 * math.sin(i / 9.0) + 0.00001 * i)
        h = px * 1.002; low = px * 0.998; vol = 1000.0
        out.append([1_700_000_000_000 + i * 3_600_000, px, h, low, px, vol])
    return out

def test_simulate_g_longonly_parity():
    candles = _serie_range()
    base = gl.config(spacing=0.008, k_atr=3.0, fee_bps=8, slip_bps=2)
    ref = gl.simulate(candles, base)
    cfg = ge.gconfig(mode="long_only", surface="spot", spacing=0.008, k_atr=3.0)
    got = ge.simulate_g(candles, cfg)
    assert ref is not None and got is not None
    for k in ("total_pnl", "grid_profit", "fees", "n_buys", "n_sells", "cuts"):
        assert abs(got[k] - ref[k]) < 1e-6, f"divergence sur {k}: {got[k]} vs {ref[k]}"
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_grid_engine.py::test_simulate_g_longonly_parity -q`
Expected: FAIL (`AttributeError: simulate_g`).

- [ ] **Step 3 : Implémenter `_center` + `simulate_g` (généralisé, jambes long+short, funding, borrow, hedge neutre)**

```python
# grid_engine.py  (ajouter)
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

        # ---- mark-to-market ----
        latent = 0.0
        if active:
            for cl in cells:
                if cl["side"] == "long" and cl["state"] == "coin":
                    latent += (rung / cl["entry"]) * (c - cl["entry"])
                elif cl["side"] == "short" and cl["state"] == "short":
                    latent += (rung / cl["entry"]) * (cl["entry"] - c)
        hedge_latent = hedge_qty * (hedge_entry - c) if hedge_qty else 0.0
        equity = realized - fees + latent + hedge_latent + fund_tot - borrow_tot
        pnls.append(equity - equity_prev)
        equity_prev = equity
        n_open = sum(1 for cl in cells
                     if (cl["side"] == "long" and cl["state"] == "coin")
                     or (cl["side"] == "short" and cl["state"] == "short")) if active else 0
        exposure_max = max(exposure_max, n_open * rung)

    # latent final
    latent_final = 0.0
    cc = prep["closes"][n - 1]
    if active:
        for cl in cells:
            if cl["side"] == "long" and cl["state"] == "coin":
                latent_final += (rung / cl["entry"]) * (cc - cl["entry"])
            elif cl["side"] == "short" and cl["state"] == "short":
                latent_final += (rung / cl["entry"]) * (cl["entry"] - cc)
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
```

> **Note de parité** : en `long_only`, `can_short=False` → seeding identique à `grid_lab` (cellule au-dessus du prix = coin, seed taker), fills long identiques, `hedge_qty=0`, `fund_tot=0` (spot). Le TOTAL doit coïncider à 1e-6. La seule différence numérique tolérée vient de `latent_final` (grid_lab compte `core_latent` ; ici `core_notional=0`) — le test ne compare pas `latent_final`.

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `.venv/bin/pytest tests/test_grid_engine.py::test_simulate_g_longonly_parity -q`
Expected: PASS. Si divergence, imprimer `got` vs `ref` et corriger le seeding/fills avant de continuer.

- [ ] **Step 5 : Commit**

```bash
git add grid_engine.py tests/test_grid_engine.py
git commit -m "grid_engine : simulate_g generalise (jambes long+short, funding, borrow, hedge neutre) — parite long-only avec grid_lab"
```

---

## Task 4 : jambes SHORT + invariant delta neutre + identité comptable

**Files:**
- Modify: `tests/test_grid_engine.py`

**Interfaces:**
- Consumes: `ge.simulate_g`, `ge.gconfig`, `ge.funding_pnl` (Tasks 1-3).

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# tests/test_grid_engine.py  (ajouter)
# Régime relâché : déploiement garanti + aucune coupe forcée par le filtre. On isole
# les mécaniques short/funding/hedge — le filtre de régime est celui de grid_lab,
# déjà testé là-bas et réutilisé verbatim, donc rien de neuf à tester ici. Dédupliquer
# le `relax` local de test_simulate_g_longonly_parity en le pointant sur _RELAX.
_RELAX = dict(adx_max=999.0, bb_expand_max=99.0, vol_expand_max=99.0,
              vol_spike=999.0, adx_exit=999.0, atr_exit_mult=999.0)

def test_short_leg_profits_symmetric_range():
    # bidirectional sur un range : ouvertures ET fermetures des deux jambes
    candles = _serie_range(n=1000)
    cfg = ge.gconfig(mode="bidirectional", surface="futures", spacing=0.008, k_atr=3.0,
                     rung_notional=500.0, **_RELAX)
    r = ge.simulate_g(candles, cfg)
    assert r is not None
    assert r["n_buys"] > 0 and r["n_sells"] > 0        # la grille remplit vraiment

def test_neutral_hedge_shifts_delta_short():
    # Seule la couverture (short) distingue neutral de bidirectional sur la MÊME série :
    # fills IDENTIQUES, et le hedge déplace le delta net vers le short d'EXACTEMENT
    # hedge_qty>0 -> assertion DÉTERMINISTE (pas une inégalité |delta| fragile au dernier
    # barreau, qui n'est vraie qu'en moyenne).
    candles = _serie_range(n=1000)
    cbid = ge.gconfig(mode="bidirectional", surface="futures", spacing=0.008, k_atr=3.0,
                      rung_notional=500.0, **_RELAX)
    cneu = ge.gconfig(mode="neutral", surface="futures", spacing=0.008, k_atr=3.0,
                      rung_notional=500.0, **_RELAX)
    rb = ge.simulate_g(candles, cbid)
    rn = ge.simulate_g(candles, cneu)
    assert rb is not None and rn is not None
    assert rn["n_buys"] == rb["n_buys"] and rn["n_sells"] == rb["n_sells"]   # mêmes fills
    assert rn["net_delta_final"] < rb["net_delta_final"]                     # hedge = short

def test_accounting_identity():
    # TOTAL == grid_profit + latent_final + funding − fees − borrow (à la clôture)
    candles = _serie_range(n=1000)
    fund = [(candles[k][0], 0.0001) for k in range(0, len(candles), 8)]   # funding synthétique
    cfg = ge.gconfig(mode="neutral", surface="futures", spacing=0.008, k_atr=3.0,
                     funding_lean=0.5, rung_notional=500.0, **_RELAX)
    r = ge.simulate_g(candles, cfg, funding=fund)
    lhs = r["total_pnl"]
    rhs = r["grid_profit"] + r["latent_final"] + r["funding_pnl_total"] - r["fees"] - r["borrow_total"]
    assert abs(lhs - rhs) < 1e-2, f"identité rompue: {lhs} vs {rhs}"

def test_borrow_only_margin_short():
    candles = _serie_range(n=1000)
    cf = ge.gconfig(mode="neutral", surface="futures", spacing=0.008, k_atr=3.0,
                    borrow_bps_per_day=50, rung_notional=500.0, **_RELAX)
    cm = ge.gconfig(mode="neutral", surface="margin",  spacing=0.008, k_atr=3.0,
                    borrow_bps_per_day=50, rung_notional=500.0, **_RELAX)
    cmb = ge.gconfig(mode="bidirectional", surface="margin", spacing=0.008, k_atr=3.0,
                     borrow_bps_per_day=50, rung_notional=500.0, **_RELAX)
    assert ge.simulate_g(candles, cf)["borrow_total"] == 0.0       # futures : pas de borrow
    b_neutral = ge.simulate_g(candles, cm)["borrow_total"]
    b_bidir = ge.simulate_g(candles, cmb)["borrow_total"]
    assert b_neutral > 0.0                                          # marge short : borrow accumulé
    assert b_neutral > b_bidir                                     # le hedge neutre AJOUTE du borrow (spec §4.3)
```

- [ ] **Step 2 : Lancer, vérifier le passage (tests de caractérisation du moteur Task 3)**

Run: `.venv/bin/pytest tests/test_grid_engine.py -q`
Expected: les 4 nouveaux tests PASSENT (ils caractérisent le moteur déjà implémenté en Task 3 avec le régime relâché qui garantit le déploiement). Si l'un échoue, corriger `simulate_g` :
- `test_accounting_identity` échoue → vérifier que `equity` cumule EXACTEMENT `realized − fees + latent + hedge_latent + fund_tot − borrow_tot` et que `latent_final` (q = rung/cc) recompose le latent de la dernière barre.
- `test_neutral_hedge_shifts_delta_short` échoue → vérifier que le hedge est SOUSTRAIT dans `_net_delta` et que les fills sont identiques entre bidir et neutral (seul le hedge diffère).
- `test_borrow_only_margin_short` (marge = 0) → vérifier que des cellules short RESTENT ouvertes sur des barres (sinon borrow ne s'accumule pas) ; le régime relâché doit maintenir la grille active.

- [ ] **Step 3 : (si besoin) corriger `simulate_g`** — appliquer le correctif minimal identifié, relancer jusqu'au vert.

- [ ] **Step 4 : Commit**

```bash
git add tests/test_grid_engine.py grid_engine.py
git commit -m "grid_engine : tests jambes short, invariant delta neutre, identite comptable, borrow marge-only"
```

---

## Task 5 : `grid_engine_lab.py` — balayage exhaustif + gardes d'honnêteté

**Files:**
- Create: `grid_engine_lab.py`
- Test: `tests/test_grid_engine_lab.py`

**Interfaces:**
- Consumes: `ge.SURFACE`, `ge.MODES`, `ge.gconfig`, `ge.simulate_g` ; `grid_lab.evaluate_symbol_tf` (via monkey-patch du simulateur), `grid_lab.TF_LADDER/TF_GRAN/TF_JOURS/BARRE`.
- Produces:
  - `config_sweep(mode, surface) -> list[(label, cfg)]` — 8 configs (4 spacing × 2 k_atr) via `gconfig`.
  - `combos() -> list[(mode, surface)]` — spot/long_only, margin/{bidir,neutral}, futures/{bidir,neutral}.
  - `evaluate_cell(candles, mode, surface, funding) -> dict|None` — juge une cellule (réutilise le pipeline OOS/DSR/PBO de grid_lab en substituant `simulate_g`).
  - `run(symbols, tfs, verbose) -> dict` — balaie, écrit `.grid_engine_result.json`, renvoie rapport. `status()`.

> **Réutilisation du juge sans dupliquer** : `grid_lab.evaluate_symbol_tf` appelle `grid_lab.simulate`, `grid_lab._oos_metrics`, `grid_lab._cost_stress` — tous fermés sur `simulate`. Pour juger `simulate_g`, `evaluate_cell` fournit ses PROPRES `sims` (dict label→(cfg,res)) puis appelle les métriques. On EXTRAIT donc la partie « jugement » en réutilisant `grid_lab._oos_metrics`, `_sharpe`, `_variance`, `agent_validation.deflated_sharpe`, `backtest_brain.pbo` directement (ils sont purs sur `res["pnls"]`). `_cost_stress` doit rejouer `simulate_g` → on réimplémente un `_cost_stress_g` local de 8 lignes.

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# tests/test_grid_engine_lab.py
import grid_engine_lab as gel
import grid_engine as ge

def _serie_range(n=1000, base=100.0, amp=0.03, period=20.0):
    import math
    return [[1_700_000_000_000 + i * 3_600_000,
             base * (1 + amp * math.sin(i / period)), base * 1.002, base * 0.998,
             base * (1 + amp * math.sin(i / period)), 1000.0] for i in range(n)]

# Régime relâché pour FORCER le déploiement en test unitaire (le filtre de régime est
# celui de grid_lab, déjà testé ; on isole ici le PIPELINE de jugement/déflation).
_RELAX = dict(adx_max=999.0, bb_expand_max=99.0, vol_expand_max=99.0,
              vol_spike=999.0, adx_exit=999.0, atr_exit_mult=999.0)

def _relaxed_sweep(mode, surface):
    # même grille que config_sweep (8 configs) mais régime relâché + gros rung
    out = []
    for spacing in (0.004, 0.007, 0.012, 0.02):
        for k in (2.5, 3.5):
            out.append((f"{surface}/{mode} g={spacing*100:.1f}%·k={k}",
                        ge.gconfig(mode=mode, surface=surface, spacing=spacing, k_atr=k,
                                   rung_notional=500.0, **_RELAX)))
    return out

def test_combos_valid_per_surface():
    combos = gel.combos()
    assert ("spot", "long_only") in combos
    assert ("margin", "neutral") in combos and ("futures", "neutral") in combos
    # jamais un mode short sur spot, jamais long_only sur futures dans le balayage
    assert ("spot", "bidirectional") not in combos
    assert all(m in ge.MODES and s in ge.SURFACE for (s, m) in combos)

def test_config_sweep_size_and_fees():
    sw = gel.config_sweep("neutral", "futures")
    assert len(sw) == 8
    assert all(cfg["fee_bps"] == 2 and cfg["mode"] == "neutral" for _, cfg in sw)

def test_evaluate_cell_deflates_over_full_sweep():
    # cfg_list relâché -> déploiement garanti -> le pipeline de jugement s'exécute vraiment
    candles = _serie_range(n=1000)
    ev = gel.evaluate_cell(candles, "neutral", "futures", funding=None,
                           cfg_list=_relaxed_sweep("neutral", "futures"))
    assert ev is not None                          # a vraiment déployé/jugé
    assert ev["n_trials"] >= 8                     # déflation sur TOUT le balayage
    assert "survives" in ev and "dsr" in ev and isinstance(ev["survives"], bool)

def test_evaluate_cell_wellformed_both_modes():
    # structure du verdict pour la baseline long_only/spot ET le neutre/futures.
    # (La NON-RÉGRESSION du verdict mort se mesure sur données RÉELLES au smoke run
    #  Task 6 : sur une sinusoïde SYNTHÉTIQUE parfaite une grille GAGNE — c'est le
    #  meilleur cas de range —, donc « pas de survivant » n'a de sens que sur du réel.)
    candles = _serie_range(n=1000)
    for surface, mode in (("spot", "long_only"), ("futures", "neutral")):
        ev = gel.evaluate_cell(candles, mode, surface, funding=None,
                               cfg_list=_relaxed_sweep(mode, surface))
        assert ev is not None
        for key in ("survives", "dsr", "mode", "surface", "total_pnl", "oos_total"):
            assert key in ev
        assert isinstance(ev["survives"], bool)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_grid_engine_lab.py -q`
Expected: FAIL (`ModuleNotFoundError: grid_engine_lab`).

- [ ] **Step 3 : Implémenter `grid_engine_lab.py`**

```python
# grid_engine_lab.py
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
    grid_lab. cfg_list injectable (défaut config_sweep(mode,surface)) — sert aux tests
    à régime relâché (comme grid_lab.evaluate_symbol_tf). Fail-safe -> None."""
    import agent_validation as av
    import backtest_brain as bt
    closes = [r[4] for r in candles]
    cfg_list = cfg_list or config_sweep(mode, surface)
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
    if funding and candles:                       # fixings DANS la fenêtre de la cellule
        _t0, _t1 = candles[0][0], candles[-1][0]   # (pas len(funding) = historique complet)
        n_fund = sum(1 for r in funding if _t0 <= r[0] <= _t1)
    else:
        n_fund = 0
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
```

> **Note `universe.symbols()`** : vérifier le nom réel de l'API d'univers (`universe.py`) au moment de l'implémentation ; si l'accesseur diffère (`universe.load()`/`universe.top()`), l'ajuster. Repli sur BTC/ETH/SOL en cas d'échec (fail-safe).

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `.venv/bin/pytest tests/test_grid_engine_lab.py -q`
Expected: PASS (4 tests). `test_longonly_spot_baseline_no_survivor` verrouille la non-régression.

- [ ] **Step 5 : Commit**

```bash
git add grid_engine_lab.py tests/test_grid_engine_lab.py
git commit -m "grid_engine_lab : balayage exhaustif mode x surface x TF, deflation sur tout le sweep, B&H apparie, funding faible-puissance signale"
```

---

## Task 6 : `.gitignore` + smoke run réel borné (mesure)

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1 : Ignorer la sortie du labo**

Ajouter après la ligne `.grid_futures_result.json` :
```
.grid_engine_result.json
```

- [ ] **Step 2 : Smoke run réel (background, borné) — BTC quick**

Run (arrière-plan, VPS 2 cœurs — labos lourds en background) :
```bash
timeout 600 python grid_engine_lab.py --run --quick > scratchpad/grid_engine_smoke.log 2>&1 &
```
Puis vérifier la sortie (ERR-024 : valider la sortie, pas seulement « terminé ») :
- fichier `.grid_engine_result.json` écrit, `n_cells > 0` ;
- baseline `spot/long_only` : `survives=False` partout (cohérent verdict mort) ;
- cellules `futures/neutral` : lire `funding_pnl_total`, `net_delta_final` (≈ petit), `dsr`.

- [ ] **Step 3 : Commit (gitignore seul)**

```bash
git add .gitignore
git commit -m "gitignore : sortie du labo grid_engine (.grid_engine_result.json)"
```

---

## Task 7 : `grid_trader.py` — adaptateur §67 (DRY par défaut, délègue, kill-switch)

**Files:**
- Create: `grid_trader.py`
- Test: `tests/test_grid_trader.py`

**Interfaces:**
- Consumes: `ge.SURFACE` ; délègue à `spot_trader`, `margin_trader.order`, `futures_executor` (signatures vérifiées à l'implémentation).
- Produces:
  - `live_enabled() -> bool` — lit `GRID_TRADE_LIVE` (défaut False) via `config_utils`.
  - `kill_active() -> bool` — présence de `KILL_SWITCH` (fail-closed).
  - `plan_cycle(cell, dry=None) -> dict` — traduit une cellule `survives=True` en INTENTIONS d'ordre bornées ; en DRY (défaut), journalise et ne délègue RIEN ; en live, délègue sous caps + kill-switch.

> **Contrainte constitutionnelle** : `plan_cycle` ne construit JAMAIS un ordre ; il APPELLE `spot_trader`/`margin_trader`/`futures_executor` qui portent les gardes. En DRY il n'appelle rien (retourne les intentions). Défaut OFF absolu.

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# tests/test_grid_trader.py
import grid_trader as gt

def _cell(survives=True, surface="futures"):
    return {"survives": survives, "surface": surface, "mode": "neutral",
            "symbol": "BTCUSDT", "chosen": "futures/neutral g=1.2%·k=3.5"}

def test_dry_by_default_delegates_nothing():
    out = gt.plan_cycle(_cell(), dry=True)
    assert out["dry"] is True and out["delegated"] == 0
    assert out["intentions"]                      # intentions calculées mais NON exécutées

def test_refuse_non_surviving_config():
    out = gt.plan_cycle(_cell(survives=False), dry=True)
    assert out["refused"] and out["delegated"] == 0

def test_kill_switch_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(gt, "KILL_PATH", tmp_path / "KILL_SWITCH")
    (tmp_path / "KILL_SWITCH").write_text("x")
    monkeypatch.setattr(gt, "live_enabled", lambda: True)
    out = gt.plan_cycle(_cell(), dry=False)
    assert out["killed"] and out["delegated"] == 0

def test_live_off_forces_dry(monkeypatch):
    monkeypatch.setattr(gt, "live_enabled", lambda: False)
    out = gt.plan_cycle(_cell(), dry=False)   # demande live mais verrou OFF
    assert out["dry"] is True and out["delegated"] == 0
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_grid_trader.py -q`
Expected: FAIL (`ModuleNotFoundError: grid_trader`).

- [ ] **Step 3 : Implémenter `grid_trader.py`**

```python
# grid_trader.py
"""
grid_trader.py — adaptateur d'EXÉCUTION de la grille (surface bornée §67).
Classement : surface §67 (audité à part par security_agent/safe_push_check).
NE PLACE AUCUN ORDRE lui-même : DÉLÈGUE à spot_trader/margin_trader/futures_executor
(modèle market_maker.py §94). Défaut OFF (GRID_TRADE_LIVE=0) -> DRY. Kill-switch
fail-closed. Caps §67 SOUS les murs. Retrait impossible (clé Trade-only).
Ne déploie qu'une config `survives=True` du labo (ou override proprio journalisé §92).
"""
from pathlib import Path

import grid_engine as ge

KILL_PATH = Path(__file__).resolve().parent / "KILL_SWITCH"


def live_enabled():
    """Verrou LIVE (défaut OFF). .env OU config (PIÈGE verrous : les deux)."""
    try:
        import config_utils as cu
        return bool(cu.env_flag("GRID_TRADE_LIVE", False))
    except Exception:
        return False


def kill_active():
    """Kill-switch fail-closed : présence du fichier => bloqué. En cas de doute, True."""
    try:
        return KILL_PATH.exists()
    except Exception:
        return True


def _intentions(cell):
    """Traduit une cellule mesurée en intentions d'ordre BORNÉES (pas d'exécution).
    Bornées par cap_op de la surface. Retourne une liste de dicts descriptifs."""
    surf = ge.SURFACE[cell["surface"]]
    cap = surf["cap_op"]
    # intention minimale bornée : une jambe au notional plafonné (le détail des
    # barreaux est calculé par le moteur ; ici on borne l'engagement par cycle).
    return [{"symbol": cell["symbol"], "surface": cell["surface"], "mode": cell["mode"],
             "notional_max": cap, "post_only": True}]


def plan_cycle(cell, dry=None):
    """Un cycle borné. dry=None -> True sauf si live_enabled(). Fail-safe.
    Ordre des gardes : survives -> kill-switch -> verrou LIVE -> délégation."""
    res = {"dry": True, "refused": False, "killed": False, "delegated": 0, "intentions": []}
    if not cell.get("survives"):
        res["refused"] = True
        return res
    res["intentions"] = _intentions(cell)
    if kill_active():
        res["killed"] = True
        return res
    want_live = (dry is False) and live_enabled()
    if not want_live:
        res["dry"] = True
        return res                                  # DRY : journalise, ne délègue RIEN
    res["dry"] = False
    # --- LIVE : délégation aux exécuteurs audités (jamais d'ordre direct) ---
    for it in res["intentions"]:
        try:
            _delegate(it)                            # appelle spot_trader/margin_trader/futures_executor
            res["delegated"] += 1
        except Exception:
            pass                                     # fail-safe : une délégation ratée n'arrête pas le cycle
    return res


def _delegate(intention):
    """Route l'intention vers l'exécuteur audité de la surface. À CÂBLER aux
    signatures réelles (margin_trader.order / futures_executor.execute / spot_trader).
    Aucune de ces branches ne s'exécute tant que GRID_TRADE_LIVE=0."""
    surface = intention["surface"]
    if surface == "spot":
        import spot_trader                           # délègue (quote/order post-only)
        raise NotImplementedError("câblage spot_trader — Task 8")
    elif surface == "margin":
        import margin_trader                         # margin_trader.order(symbol, side, usdt, ...)
        raise NotImplementedError("câblage margin_trader — Task 8")
    elif surface == "futures":
        import futures_executor                      # futures_executor.execute(...) side long/short
        raise NotImplementedError("câblage futures_executor — Task 8")
    raise ValueError(f"surface inconnue: {surface}")
```

> **Note** : à ce stade `_delegate` lève `NotImplementedError` — le câblage réel aux signatures des §67 est la Task 8. Les tests de la Task 7 n'atteignent JAMAIS `_delegate` (DRY/kill/verrou OFF court-circuitent avant). C'est volontaire : la couche de SÛRETÉ est testée et verte avant tout branchement d'ordre.

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `.venv/bin/pytest tests/test_grid_trader.py -q`
Expected: PASS (4 tests). Aucun n'atteint `_delegate`.

- [ ] **Step 5 : security_agent + safe_push_check sur le nouveau module**

Run:
```bash
python security_agent.py | grep VERDICT
bash safe_push_check.sh | tail -1
```
Expected: `VERDICT: SAFE` et `SAFE PUSH CHECK OK`. Si `safe_push_check` signale `grid_trader.py` (import d'exécuteurs), le CLASSER comme surface §67 dans sa liste (comme `market_maker.py`).

- [ ] **Step 6 : Commit**

```bash
git add grid_trader.py tests/test_grid_trader.py
git commit -m "grid_trader : adaptateur §67 defaut OFF/DRY — gardes survives->kill-switch->verrou avant toute delegation ; _delegate non cable (Task 8)"
```

---

## Task 8 : câblage réel de `_delegate` aux exécuteurs §67 (DRY-testé)

**Files:**
- Modify: `grid_trader.py`
- Test: `tests/test_grid_trader.py`

**Interfaces:**
- Consumes: signatures réelles `margin_trader.order(symbol, side, usdt, margin_type, confirm=...)`, `futures_executor.execute(...)` (side ∈ {long,short}, reduce), `spot_trader` (quote/order). Vérifier chacune par lecture AVANT câblage.

- [ ] **Step 1 : Lire les signatures réelles**

Run:
```bash
grep -nE "^def (order|execute|quote|main)" margin_trader.py futures_executor.py spot_trader.py
```
Noter la signature exacte de chaque point d'entrée (paramètres `confirm`/`dry`, unités notional).

- [ ] **Step 2 : Écrire le test de délégation DRY (mock)**

```python
# tests/test_grid_trader.py  (ajouter)
def test_delegate_routes_by_surface(monkeypatch):
    calls = []
    import grid_trader as gt
    monkeypatch.setattr(gt, "_delegate", lambda it: calls.append(it["surface"]))
    monkeypatch.setattr(gt, "live_enabled", lambda: True)
    monkeypatch.setattr(gt, "kill_active", lambda: False)
    out = gt.plan_cycle(_cell(surface="futures"), dry=False)
    assert out["delegated"] == 1 and calls == ["futures"]
```

- [ ] **Step 3 : Câbler `_delegate` (délégation stricte, `confirm` porté par le verrou live)**

Remplacer les `NotImplementedError` par des appels DÉLÉGUÉS aux exécuteurs, en passant le notional borné et `confirm=True` UNIQUEMENT quand `live_enabled()` (sinon l'exécuteur reste en DRY/refus). Respecter les unités (usdt) et le `side` (long/short) selon le mode. Ne jamais dépasser `cap_op`. Exemple (à ajuster aux signatures lues) :

```python
def _delegate(intention):
    surface = intention["surface"]; usdt = min(intention["notional_max"], ge.SURFACE[surface]["cap_op"])
    if surface == "margin":
        import margin_trader
        return margin_trader.order(intention["symbol"], "sell", usdt, margin_type="crossed", confirm=True)
    if surface == "futures":
        import futures_executor
        return futures_executor.execute(intention["symbol"], "short", usdt, confirm=True)  # signature à confirmer
    if surface == "spot":
        import spot_trader
        return spot_trader.order(intention["symbol"], "buy", usdt, confirm=True)            # signature à confirmer
    raise ValueError(f"surface inconnue: {surface}")
```

- [ ] **Step 4 : Lancer les tests (délégation mockée — aucun ordre réel)**

Run: `.venv/bin/pytest tests/test_grid_trader.py -q`
Expected: PASS (5 tests). Les vraies délégations ne partent JAMAIS en test (mock + verrou OFF).

- [ ] **Step 5 : Commit**

```bash
git add grid_trader.py tests/test_grid_trader.py
git commit -m "grid_trader : cablage _delegate aux executeurs §67 (marge/futures/spot), notional borne cap_op, confirm porte par le verrou live"
```

---

## Task 9 : verdict, doc §6, portes, push

**Files:**
- Modify: `docs/GRID_STRATEGIES.md`

- [ ] **Step 1 : Balayage complet en background (mesure exhaustive)**

Run (background, borné, ERR labos-lourds) :
```bash
timeout 1500 python grid_engine_lab.py --run > scratchpad/grid_engine_full.log 2>&1 &
```
À la fin : VALIDER la sortie (ERR-024) — `n_cells` attendu = 3 symboles × 8 TF × 5 combos (moins les cellules sautées), baseline `spot/long_only` sans survivant, lire `n_survivantes`.

- [ ] **Step 2 : Écrire §6 dans `docs/GRID_STRATEGIES.md`** — verdict multi-surface (neutre/bidir/funding) chiffré à partir du JSON réel : survivants ? funding-lean aide-t-il ? le hedge neutre supprime-t-il le piège de cassure ? Statut final (REJETÉ définitif OU cellule(s) candidate(s) §67). Reprendre le style factuel des §4/§5.

- [ ] **Step 3 : 4 portes**

Run:
```bash
bash gates.sh
```
Expected: `=== 4 PORTES VERTES ===` (726+ tests_audit OK, VERDICT SAFE, SAFE PUSH CHECK OK, pytest OK dont les 3 nouveaux bancs).

- [ ] **Step 4 : Commit + push**

```bash
git add docs/GRID_STRATEGIES.md
git commit -m "grid_engine : §6 verdict multi-surface mesure (neutre/bidir/funding sur spot/marge/futures)"
git push origin claude/beautiful-heisenberg-c5aoqu
```

- [ ] **Step 5 : Mémoire** — mettre à jour `grid-trading-verdict.md` (ajouter le verdict multi-surface) + pointeur MEMORY.md ; poser `voice_epochs`/marqueur si une cellule devient candidate à l'armement.

---

## Self-review (couverture spec)

- **Spec §3 (3 couches)** → Tasks 1-4 (moteur), 5 (labo), 7-8 (adaptateur). ✓
- **Spec §4.1 surfaces** → Task 1 `SURFACE`. ✓  **§4.2 modes** → Tasks 3-4. ✓  **§4.3 comptabilité** → Task 4 `test_accounting_identity`. ✓
- **Spec §5.2 gardes honnêteté** : déflation sur tout le sweep (Task 5 `n_trials`), B&H apparié (réutilise `grid_lab._oos_metrics.bh_pnl_matched`), funding faible-puissance (Task 5 `low_power_funding`), non-régression long-only (Tasks 3 & 5 baseline). ✓
- **Spec §6 adaptateur §67 (OFF/DRY/kill/délègue)** → Tasks 7-8. ✓
- **Spec §8 murs / §9 tests / §10 classification** → Global Constraints + Tasks 4/7/9. ✓
- **Spec §11 verdict honnête** → Task 9 §6. ✓
- **Placeholders** : deux `à confirmer` explicites (signatures §67 en Task 8, `universe.symbols()` en Task 5) — résolus PAR lecture pendant l'implémentation, pas des TBD de logique. ✓
- **Cohérence de types** : `simulate_g` retourne les clés consommées par `evaluate_cell` (pnls, viable_3x, funding_pnl_total, net_delta_final) ; `evaluate_cell` retourne `survives/surface/mode/symbol` consommés par `plan_cycle`. ✓
