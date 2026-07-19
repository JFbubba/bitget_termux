#!/usr/bin/env python3
"""smc_execution_lab.py — banc de MESURE d'EXÉCUTION du SMC (la BONNE lentille, ERR-016). SAFE.

LECTURE SEULE, PUR (bougies disque `data_history` via audit_core), AUCUN ordre, AUCUN secret,
AUCUN chemin d'exécution. Défaut OFF (sans verbe CLI : statut only).

POURQUOI (ERR-016 + correction propriétaire 19/07) : SMC n'est PAS un prédicteur directionnel —
c'est une RECONNAISSANCE de structure qui dit OÙ on est pour bien PLACER ses ordres. Le mesurer à
l'IC directionnelle (fait, ≈0) répond à la mauvaise question. La BONNE question, sur le SEUL levier
réel du bot (exécution/frais) : **un fill MAKER posé À un niveau de structure SMC (bord d'un FVG /
BPR / niveau balayé, du bon côté) a-t-il un meilleur MARKOUT — moins de sélection adverse — qu'un
fill maker naïf ?** Si oui, SMC a une valeur d'EXÉCUTION même sans edge directionnel.

MÉTHODE (mirror de `vpin_lab`, contexte = structure SMC au lieu de VPIN) :
  • fills maker post-only simulés (fair = close précédente ; bid/ask = fair·(1∓spread/2) ; buy
    rempli si low≤bid, sell si high≥ask — borne sup sans file d'attente) — IDENTIQUE à vpin_lab ;
  • markout NET `h` barres plus tard : `microstructure.markout` réutilisé tel quel, − frais maker ;
  • TAG SMC CAUSAL de chaque fill (zones établies ≤ i−2, look-ahead-free) : le fill tombe-t-il DANS
    un FVG/BPR/niveau balayé du CÔTÉ favorable (buy dans un FVG haussier = support/discount ; sell
    dans un FVG baissier = résistance/premium ; buy sur un swept-low, sell sur un swept-high) ;
  • EXPÉRIENCE : markout net des fills « À la structure & alignés » vs baseline (tous / hors-structure).
    Welch t + bootstrap + non-chevauchant + Deflated Sharpe déflaté par le nb d'essais (sym×TF×h).
  CRITÈRE (PASS) : delta = markout(structure) − markout(baseline) > 0, t≥2, bootstrap lo95>0,
  cohérent ≥2 TF, DSR≥0,95. Sinon → SMC n'améliore pas l'exécution (prior : fees dominent).

CLI :
    python smc_execution_lab.py --status [SYMBOL]
    python smc_execution_lab.py --run SYMBOL [GRAN]
    python smc_execution_lab.py --run-all
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

import microstructure as ms          # markout (sélection adverse) — réutilisé tel quel
import vpin_lab as vp                 # _welch_t, bootstrap_diff, non_overlapping, helpers vol — réutilisés
import smc                            # détecteurs de structure (FVG/BPR/sweeps) — réutilisés

_AUDIT_DIR = Path(__file__).resolve().parent / "scratchpad" / "audit_indep"
if str(_AUDIT_DIR) not in sys.path:
    sys.path.insert(0, str(_AUDIT_DIR))
try:
    import audit_core as ac
    _HAS_AUDIT = True
except Exception:                     # pragma: no cover
    ac = None
    _HAS_AUDIT = False

RESULT = Path(__file__).resolve().parent / ".smc_execution_lab_result.jsonl"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "BNBUSDT"]
GRANS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]     # échelle COMPLÈTE (ERR-001)
H_GRID = [3, 6, 12]                   # horizons de markout (barres)
FEE_MAKER_BPS = 2.0                   # frais maker par fill (futures VIP0) ; markout = qualité de fill
CONFIRM_LAG = 2                       # une zone n'est utilisable qu'à index+2 (fractale smc, causal)
EDGE_TOL = 0.0005                     # tolérance de proximité au bord de zone (5 bps de prix)
SWEEP_LOOKBACK = 30                   # un niveau balayé reste « chaud » ~30 barres
ZONE_LIFETIME = 40                    # une FVG/BPR n'est « active » que ~40 barres après création
                                      # (sinon les zones accumulées couvrent tout -> tag non discriminant)
MIN_FILLS = 30                        # plancher pour une expérience valide
MAX_BARS = 6000                       # borne (détecteurs smc ~O(n·swings))
N_TRIALS = len(SYMBOLS) * len(GRANS) * len(H_GRID)


# ===================== data (rows [ts,o,h,l,c,v] depuis audit_core) =====================
def _rows(sym, gran):
    if not _HAS_AUDIT:
        return []
    try:
        d = ac.load(sym, gran)
        if not d:
            return []
        ts = np.asarray(d["ts"], float)
        n = len(ts)
        if n < 200:
            return []
        o, h, l, c, v = (np.asarray(d[k], float) for k in ("o", "h", "l", "c", "v"))
        rows = [[float(ts[i]), float(o[i]), float(h[i]), float(l[i]), float(c[i]), float(v[i])]
                for i in range(n)]
        return rows[-MAX_BARS:] if n > MAX_BARS else rows
    except Exception:
        return []


# ===================== zones de structure SMC (PUR, causal) =====================
def structure_zones(candles):
    """PUR. Zones favorables établies dans le temps, chacune {est_index, side, lo, hi} où side =
    côté de fill FAVORISÉ (buy dans un FVG haussier / sur un swept-low ; sell dans un FVG baissier /
    sur un swept-high). BPR compte des deux côtés (mur). `est_index` = barre où la zone est CONNUE."""
    zones = []
    for g in smc.fair_value_gaps(candles, keep_filled=True):        # {type,top,bottom,index,...}
        side = "buy" if g["type"] == "bull" else "sell"
        zones.append({"est": g["index"], "side": side, "lo": g["bottom"], "hi": g["top"],
                      "expire": g["index"] + ZONE_LIFETIME})
    for z in smc.balanced_price_ranges(candles):                     # mur -> les deux côtés
        for sd in ("buy", "sell"):
            zones.append({"est": z["index"], "side": sd, "lo": z["bottom"], "hi": z["top"],
                          "expire": z["index"] + ZONE_LIFETIME})
    for s in smc.liquidity_sweeps(candles):                          # niveau balayé -> support/résist.
        lvl = s["level"]
        side = "buy" if s["side"] == "sell" else "sell"              # sell-sweep = support -> buy
        band = lvl * EDGE_TOL
        zones.append({"est": s["index"], "side": side, "lo": lvl - band, "hi": lvl + band,
                      "expire": s["index"] + SWEEP_LOOKBACK})
    return zones


def _at_structure(zones, i, price, side):
    """PUR & causal. True si `price` (fill de `side` à la barre i) tombe dans une zone FAVORABLE
    du même côté, établie ≤ i−CONFIRM_LAG (et non expirée pour les sweeps)."""
    band = price * EDGE_TOL
    for z in zones:
        if z["side"] != side or z["est"] > i - CONFIRM_LAG:
            continue
        if "expire" in z and i > z["expire"]:
            continue
        if (z["lo"] - band) <= price <= (z["hi"] + band):
            return True
    return False


# ===================== simulation de fills maker + tag SMC + markout =====================
def simulate_fills(candles, h, spread_bps, fee_bps=FEE_MAKER_BPS, zones=None):
    """PUR. Fills maker post-only (comme vpin_lab), markout net à +h, tag `at_structure` (le fill
    tombe-t-il à un niveau SMC favorable de son côté). Retour [{i,ts,side,price,at_structure,net_bps}].
    `zones` (h-indépendantes) peut être précalculé une fois par cellule (perf : détecteurs smc lourds)."""
    n = len(candles)
    if n < h + CONFIRM_LAG + 5:
        return []
    if zones is None:
        zones = structure_zones(candles)
    # index par barre de création -> ne tester QUE les zones ACTIVES à chaque fill (perf : sinon
    # O(n_fills × n_zones) avec ~7000 sweeps = milliards d'ops). Fenêtre = durée de vie max.
    by_est = {}
    for z in zones:
        by_est.setdefault(int(z["est"]), []).append(z)
    maxlife = max(ZONE_LIFETIME, SWEEP_LOOKBACK)
    hs = float(spread_bps) / 2.0 / 1e4
    fills = []
    for i in range(2, n - h):
        fair = float(candles[i - 1][4])
        if fair <= 0:
            continue
        active = []                                       # zones connues (est≤i−lag) et pas trop vieilles
        for e in range(max(0, i - maxlife), i - CONFIRM_LAG + 1):
            active.extend(by_est.get(e, ()))
        low, high = float(candles[i][3]), float(candles[i][2])
        future_mid = float(candles[i + h][4])
        ts = candles[i][0]
        bid, ask = fair * (1 - hs), fair * (1 + hs)
        if low <= bid:
            mk = ms.markout(bid, "buy", future_mid)
            fills.append({"i": i, "ts": ts, "side": "buy", "price": bid,
                          "at_structure": _at_structure(active, i, bid, "buy"),
                          "net_bps": mk - fee_bps})
        if high >= ask:
            mk = ms.markout(ask, "sell", future_mid)
            fills.append({"i": i, "ts": ts, "side": "sell", "price": ask,
                          "at_structure": _at_structure(active, i, ask, "sell"),
                          "net_bps": mk - fee_bps})
    return fills


# ===================== EXPÉRIENCE : markout structure vs baseline =====================
def condition_by_structure(fills):
    """PUR. L'EXPÉRIENCE CENTRALE : markout net moyen des fills À LA STRUCTURE (favorables) vs
    HORS-structure. delta>0 = poser le limit maker au niveau SMC AMÉLIORE le markout (moins de
    sélection adverse). Welch t. None si trop peu de fills d'un côté."""
    at = [f["net_bps"] for f in fills if f["at_structure"]]
    off = [f["net_bps"] for f in fills if not f["at_structure"]]
    if len(at) < MIN_FILLS or len(off) < 5:
        return None
    am, om = sum(at) / len(at), sum(off) / len(off)
    return {"n": len(fills), "n_at": len(at), "n_off": len(off),
            "at_mean_net": round(am, 4), "off_mean_net": round(om, 4),
            "delta": round(am - om, 4), "t": round(vp._welch_t(at, off), 2),
            "fill_rate_at": round(len(at) / max(1, len(fills)), 3)}


# ===================== run =====================
def run_symbol_gran(sym, gran, spread_bps=None):
    candles = _rows(sym, gran)
    if len(candles) < 250:
        return {"symbol": sym, "gran": gran, "verdict": "donnees_insuffisantes",
                "n_candles": len(candles)}
    if spread_bps is None:
        spread_bps = max(1.0, vp.typical_range_bps(candles))
    zones = structure_zones(candles)                      # h-indépendant : calculé UNE fois par cellule
    configs = []
    for h in H_GRID:
        fills = simulate_fills(candles, h, spread_bps, zones=zones)
        cond = condition_by_structure(fills)
        row = {"h": h, "n_fills": len(fills), "cond": cond}
        if cond:
            at = [f["net_bps"] for f in fills if f["at_structure"]]
            off = [f["net_bps"] for f in fills if not f["at_structure"]]
            row["boot"] = vp.bootstrap_diff(at, off)                 # diff structure − hors-structure
            nov = vp.non_overlapping([f for f in fills if f["at_structure"]], h)
            row["_net_series"] = [f["net_bps"] for f in nov]
            row["n_nonoverlap"] = len(nov)
        configs.append(row)
    return {"symbol": sym, "gran": gran, "n_candles": len(candles),
            "spread_bps": round(spread_bps, 2), "configs": configs}


def run_all(symbols=None, grans=None, verbose=True):
    """LE VERDICT : univers × échelle TF × horizons. Déflate par le nb total d'essais (DSR).
    Read-only, écrit le JSON."""
    if not _HAS_AUDIT:
        return {"error": "audit_core indisponible", "verdict": "ABSTENTION (fail-safe)"}
    import agent_validation as av
    symbols = symbols or SYMBOLS
    grans = grans or GRANS
    per_cell, trials = [], []
    for s in symbols:
        for g in grans:
            cell = run_symbol_gran(s, g)
            per_cell.append(cell)
            for c in cell.get("configs", []):
                if c.get("cond"):
                    trials.append((cell, c))
        if verbose:
            done = [c for cell, c in trials if cell["symbol"] == s]
            if done:
                b = max(done, key=lambda c: c["cond"]["delta"])
                print(f"  [{s}] meilleur delta markout = {b['cond']['delta']:+.2f} bps "
                      f"(t {b['cond']['t']:+.2f}, h={b['h']}, n_at={b['cond']['n_at']})")
    n_trials = max(1, len(trials))
    sharpes = []
    for cell, c in trials:
        ser = c.get("_net_series") or []
        sharpes.append(av.sharpe(ser) if len(ser) >= 5 else 0.0)
    var_sr = 0.0
    if len(sharpes) >= 2:
        m = sum(sharpes) / len(sharpes)
        var_sr = sum((x - m) ** 2 for x in sharpes) / (len(sharpes) - 1)
    for cell, c in trials:
        ser = c.get("_net_series") or []
        if len(ser) >= 5:
            sk, ku = av._skew_kurt(ser)
            c["dsr"] = round(av.deflated_sharpe(av.sharpe(ser), len(ser), sk, ku, n_trials, var_sr), 4)
        else:
            c["dsr"] = None
        c["t_defl"] = round(c["cond"]["t"] / (1.0 + math.log(n_trials)), 2)
        c.pop("_net_series", None)

    # essais ROBUSTES : delta>0 (structure meilleure) & t≥2 & bootstrap lo95>0 & DSR≥0.95
    robustes = []
    for cell, c in trials:
        cond, boot = c["cond"], c.get("boot") or {}
        if (cond["delta"] > 0 and cond["t"] >= 2.0
                and (boot.get("lo95") is not None and boot["lo95"] > 0)
                and (c.get("dsr") is not None and c["dsr"] >= 0.95)):
            robustes.append((cell["symbol"], cell["gran"], c))
    # cohérence ≥2 TF adjacents où delta>0 & t≥2
    tf_ok = []
    for g in grans:
        ok = any(c["cond"]["delta"] > 0 and c["cond"]["t"] >= 2.0
                 for cell, c in trials if cell["gran"] == g)
        tf_ok.append(ok)
    adj = any(tf_ok[i] and tf_ok[i + 1] for i in range(len(tf_ok) - 1))
    passed = bool(robustes) and adj
    best = max(trials, key=lambda t: t[1]["cond"]["delta"], default=None)
    verdict = ("SMC AIDE L'EXÉCUTION (à confirmer réel)" if passed
               else "SMC N'AMÉLIORE PAS l'exécution nette (fills à la structure ≈ naïfs — prior tenu)")
    res = {"ts": int(time.time()), "n_trials": N_TRIALS, "fee_maker_bps": FEE_MAKER_BPS,
           "universe": symbols, "grans": grans, "h_grid": H_GRID,
           "best": ({"symbol": best[0]["symbol"], "gran": best[0]["gran"], **best[1]["cond"],
                     "h": best[1]["h"], "dsr": best[1].get("dsr"), "boot": best[1].get("boot")}
                    if best else None),
           "n_robustes": len(robustes), "coherent_2TF": adj,
           "verdict": verdict, "gate_passed": passed}
    _write(res)
    if verbose:
        _print_verdict(res)
    return res


def run_one(sym, gran=None):
    if not _HAS_AUDIT:
        print("audit_core indisponible — ABSTENTION (fail-safe).")
        return None
    grans = [gran] if gran else GRANS
    print(f"=== smc_execution_lab --run {sym} (frais maker {FEE_MAKER_BPS} bps/fill) ===")
    for g in grans:
        cell = run_symbol_gran(sym, g)
        if cell.get("verdict") == "donnees_insuffisantes":
            print(f"  [{g}] data insuffisante"); continue
        for c in cell["configs"]:
            cd = c.get("cond")
            if not cd:
                print(f"  [{g}] h={c['h']} n_fills={c['n_fills']} (trop peu à la structure)")
                continue
            print(f"  [{g}] h={c['h']:<2} n_at={cd['n_at']:<4} fill_rate_at={cd['fill_rate_at']:.2f} "
                  f"markout structure={cd['at_mean_net']:+.2f} vs naïf {cd['off_mean_net']:+.2f} "
                  f"-> delta {cd['delta']:+.2f} bps (t {cd['t']:+.2f})")
    print("Lecture seule, aucun ordre. VERDICT: SAFE")


def status(sym=None):
    print("=== smc_execution_lab --status (mesure d'EXÉCUTION SMC — SAFE, défaut OFF) ===")
    print(f"audit_core : {_HAS_AUDIT} | frais maker {FEE_MAKER_BPS} bps/fill | h {H_GRID}")
    print(f"univers : {', '.join(SYMBOLS)}")
    print(f"échelle TF : {', '.join(GRANS)} (ERR-001) | N_trials(DSR)={N_TRIALS}")
    print("question : un fill MAKER à un niveau SMC (FVG/BPR/swept, bon côté) a-t-il un meilleur")
    print("           MARKOUT qu'un fill naïf ? (bonne lentille ERR-016 : exécution, pas direction)")
    if RESULT.exists():
        try:
            prev = json.loads(RESULT.read_text())
            print(f"dernier verdict : {prev.get('verdict')} (gate_passed={prev.get('gate_passed')})")
        except Exception:
            pass
    print("Lecture seule, aucun ordre, défaut OFF. VERDICT: SAFE")


def _write(res):
    try:
        RESULT.write_text(json.dumps(res, default=float), encoding="utf-8")
    except Exception:
        pass


def _print_verdict(res):
    print("\n=== VERDICT SMC-EXECUTION-LAB (markout des fills à la structure) ===")
    b = res.get("best")
    if b:
        print(f"meilleur essai : {b['symbol']} {b['gran']} h={b['h']} | markout structure "
              f"{b['at_mean_net']:+.2f} vs naïf {b['off_mean_net']:+.2f} -> delta {b['delta']:+.2f} bps "
              f"(t {b['t']:+.2f}, n_at={b['n_at']}, DSR={b.get('dsr')})")
        bo = b.get("boot") or {}
        if bo:
            print(f"  bootstrap diff : {bo.get('mean')} [{bo.get('lo95')}, {bo.get('hi95')}]")
    print(f"  essais robustes : {res['n_robustes']} | cohérent 2 TF : {res['coherent_2TF']}")
    print(f"  >>> {res['verdict']}")
    print("Lecture seule, aucun ordre, défaut OFF. VERDICT: SAFE")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.split("CLI :")[-1].strip())
        print("\nDéfaut OFF : aucun verbe -> aucune mesure. VERDICT: SAFE")
        return
    if args[0] == "--status":
        status(next((a for a in args[1:] if not a.startswith("-")), None))
    elif args[0] == "--run":
        rest = [a for a in args[1:] if not a.startswith("-")]
        run_one(rest[0] if rest else "BTCUSDT", rest[1] if len(rest) > 1 else None)
    elif args[0] == "--run-all":
        print("=== smc_execution_lab --run-all (univers × TF × horizons) ===")
        run_all()
    else:
        print("usage: --status | --run SYMBOL [GRAN] | --run-all")


if __name__ == "__main__":
    main()
