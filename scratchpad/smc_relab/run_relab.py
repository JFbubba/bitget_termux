"""
run_relab.py — MESURE le modèle ICT 2022 (top-down D1+4H + NY killzone) et rend le
verdict. LECTURE SEULE, aucun ordre. Re-test d'une idée REJETÉE (prior négatif fort).

Protocole rigoureux :
  - grille de configs (session{all/ny/silver} × OB × OTE × discount × align_D1) = 48
    combinaisons -> N_trials honnête pour la Deflated Sharpe ;
  - net de frais TAKER et MAKER (maker = notre seul levier prouvé) ;
  - POOL inter-majors (l'unité mesurable : par-major le setup filtré-session est trop
    rare, single-digit trades) ;
  - CONTRÔLE session ON/OFF (isole la valeur de la killzone NY — 2e angle mort) ;
  - t HAC/Newey-West + Deflated Sharpe (audit_core, validés Monte-Carlo) ;
  - Walk-forward OOS POOLED (sélection sur TRAIN, éval sur OOS = t honnête) ;
  - Benchmark buy-and-hold + décomposition long/short (détecte la capture de beta).

Critère de déploiement : edge net MAKER, OOS, B&H-positif, DSR>0.95 sur ≥3 majors.
Usage : /root/smc_venv/bin/python run_relab.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audit_indep"))
import audit_core as ac  # noqa: E402  (nw_tstat, deflated_sharpe — validés)
import ict_2022 as ict  # noqa: E402

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
LTF = "15m"

BOOL = [True, False]
SESSIONS = ["all", "ny", "silver"]
GRID = [
    ict.Cfg(require_ob=ob, require_ote=ote, require_discount=disc,
            session=ses, align_d1=d1)
    for ses in SESSIONS for ob in BOOL for ote in BOOL
    for disc in BOOL for d1 in BOOL
]
CANON = ict.Cfg(require_ob=True, require_ote=True, require_discount=True,
                session="ny", align_d1=True)      # ICT complet (session NY)
CORE = ict.Cfg(require_ob=False, require_ote=True, require_discount=False,
               session="ny", align_d1=False)      # base faithful mesurable, session NY


def _sharpe(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 2 or np.std(x, ddof=1) < 1e-15:
        return 0.0
    return float(np.mean(x) / np.std(x, ddof=1))


def build_symbol(sym):
    df15 = ict.load_df(sym, LTF)
    df4 = ict.load_df(sym, "4H")
    dfd = ict.load_df(sym, "1D")
    if df15 is None or df4 is None or dfd is None or len(df15) < 500:
        return None
    st4 = ict.htf_state(df4, 50, "4H")
    std = ict.htf_state(dfd, 50, "1D")
    ts15 = df15["ts"].to_numpy()
    bias4, mid4 = ict.map_htf_to_ltf(ts15, st4)
    biasD, _ = ict.map_htf_to_ltf(ts15, std)
    feats = ict.ltf_features(df15, CORE.ltf_swing)
    bh = float((df15["close"].iloc[-1] - df15["close"].iloc[0]) / df15["close"].iloc[0])
    return dict(sym=sym, df15=df15, feats=feats, bias15=bias4, mid15=mid4,
                biasD1=biasD, bh=bh, n15=len(df15))


def trades_for(ctx, cfg):
    return ict.simulate(ctx["sym"], ctx["feats"], ctx["df15"], ctx["bias15"],
                        ctx["mid15"], ctx["biasD1"], cfg)


def netvec(trades, scenario):
    return np.array([ict.net_return(t, scenario) for t in trades], float)


def line(rets, label):
    n = len(rets)
    if n == 0:
        return f"{label:26} N=0"
    mean = np.mean(rets) * 1e4
    sh = _sharpe(rets)
    nw = ac.nw_tstat(rets) if n >= 20 else None
    t = nw["t_nw"] if nw else float("nan")
    return f"{label:26} N={n:>4}  mean={mean:>8.2f}bps  Sharpe={sh:>6.2f}  t_HAC={t:>7.2f}"


def pooled(ctxs, cfg, scenario="maker", train=None):
    """Rendements pool inter-majors pour une config. train: None=tout, 'train'/'oos'."""
    out = []
    for ctx in ctxs.values():
        split = int(ctx["n15"] * 0.60)
        for tr in trades_for(ctx, cfg):
            if train == "train" and tr["entry_bar"] >= split:
                continue
            if train == "oos" and tr["entry_bar"] < split:
                continue
            out.append(ict.net_return(tr, scenario))
    return np.array(out, float)


def main():
    print("=" * 94)
    print("RÉ-TEST ICT 2022 — top-down (D1+4H) + NY equity-overlap killzone — LTF 15m")
    print(f"N_trials (grille) = {len(GRID)}  [session{{all,ny,silver}} × OB × OTE × discount × align_D1]")
    print("Frais : taker 6bps/côté | maker 2bps entrée+TP / 6bps stop | maker_ideal 2bps partout")
    print("=" * 94)

    ctxs = {}
    for s in SYMS:
        c = build_symbol(s)
        if c is None:
            print(f"  {s}: données insuffisantes — ignoré")
            continue
        ctxs[s] = c

    # ---------- A) RARETÉ par major (canonique complet vs core) ----------
    print("\n### A) COMPTES par major — le setup filtré-session est RARE")
    print(f"{'sym':8} {'B&H%':>8} | {'CANON N':>8} {'CORE N':>7} {'CORE net_mk_bps':>16}")
    for s, ctx in ctxs.items():
        tc = trades_for(ctx, CANON)
        tk = trades_for(ctx, CORE)
        mk = netvec(tk, "maker")
        m = np.mean(mk) * 1e4 if len(mk) else float("nan")
        print(f"{s:8} {ctx['bh']*100:>7.1f}% | {len(tc):>8} {len(tk):>7} {m:>16.2f}")

    # ---------- B) CONTRÔLE SESSION (core model, POOLED) ----------
    print("\n### B) VALEUR DE LA KILLZONE — core model POOLED, session all vs ny vs silver")
    for ses in SESSIONS:
        cfg = ict.Cfg(require_ob=False, require_ote=True, require_discount=False,
                      align_d1=False, session=ses)
        r_mk = pooled(ctxs, cfg, "maker")
        r_tk = pooled(ctxs, cfg, "taker")
        print("  " + line(r_mk, f"session={ses} (maker)"))
        print("  " + line(r_tk, f"session={ses} (taker)"))

    # ---------- C) POOLED GRID : best + canonique + DSR ----------
    print("\n### C) POOLED sur la grille (maker) — best de grille + DSR déflatée")
    sr_trials, best = [], (-9, None, None)
    for cfg in GRID:
        r = pooled(ctxs, cfg, "maker")
        sh = _sharpe(r) if len(r) >= 15 else 0.0
        sr_trials.append(sh)
        if len(r) >= 25 and sh > best[0]:
            best = (sh, cfg, r)
    var_sr = float(np.var(sr_trials, ddof=1))
    print(f"   var[SR] sur {len(GRID)} essais = {var_sr:.4f} ; "
          f"SR0 attendu sous H0 = {ac.expected_max_sharpe(var_sr, len(GRID)):.3f}")
    if best[1] is not None:
        cfg = best[1]
        r = best[2]
        tag = (f"sess={cfg.session} ob{int(cfg.require_ob)} ote{int(cfg.require_ote)} "
               f"disc{int(cfg.require_discount)} d1{int(cfg.align_d1)}")
        print("   BEST : " + tag)
        print("   " + line(r, "  best pooled (maker)"))
        print("   " + line(pooled(ctxs, cfg, "taker"), "  best pooled (taker)"))
        d = ac.deflated_sharpe(r, var_sr=var_sr, n_trials=len(GRID))
        if d:
            print(f"   DSR_best = {d['dsr']:.4f}  (SR_bar={d['sr_bar']:.3f}, skew={d['skew']:.2f}, "
                  f"kurt={d['kurt']:.2f}, N={d['n']})   [seuil 0.95]")
    # canonique pooled
    rc = pooled(ctxs, CANON, "maker")
    print("   " + line(rc, "canonique pooled (maker)"))
    if len(rc) >= 20:
        dc = ac.deflated_sharpe(rc, var_sr=var_sr, n_trials=len(GRID))
        if dc:
            print(f"   DSR_canon = {dc['dsr']:.4f}")

    # long/short decomposition du best (capture de beta ?)
    if best[1] is not None:
        cfg = best[1]
        L, S = [], []
        for ctx in ctxs.values():
            for tr in trades_for(ctx, cfg):
                (L if tr["dir"] == 1 else S).append(ict.net_return(tr, "maker"))
        L, S = np.array(L), np.array(S)
        print(f"   long: N={len(L)} mean={np.mean(L)*1e4 if len(L) else float('nan'):.2f}bps | "
              f"short: N={len(S)} mean={np.mean(S)*1e4 if len(S) else float('nan'):.2f}bps  "
              f"(asymétrie forte = beta, pas alpha)")

    # ---------- D) WALK-FORWARD OOS POOLED ----------
    print("\n### D) WALK-FORWARD OOS POOLED (best config choisie sur TRAIN 60%, éval OOS 40%)")
    best_tr = (-9, None)
    for cfg in GRID:
        rtr = pooled(ctxs, cfg, "maker", train="train")
        if len(rtr) >= 20:
            sh = _sharpe(rtr)
            if sh > best_tr[0]:
                best_tr = (sh, cfg)
    if best_tr[1] is not None:
        cfg = best_tr[1]
        tag = (f"sess={cfg.session} ob{int(cfg.require_ob)} ote{int(cfg.require_ote)} "
               f"disc{int(cfg.require_discount)} d1{int(cfg.align_d1)}")
        roos = pooled(ctxs, cfg, "maker", train="oos")
        rtk = pooled(ctxs, cfg, "taker", train="oos")
        print(f"   config sélectionnée sur TRAIN : {tag}")
        print("   " + line(roos, "OOS pooled (maker)"))
        print("   " + line(rtk, "OOS pooled (taker)"))
    else:
        print("   TRAIN trop mince pour sélectionner une config (N<20 partout).")

    # B&H moyen
    bh = np.mean([c["bh"] for c in ctxs.values()]) * 100
    print(f"\n   Benchmark buy-and-hold moyen (période 15m) = {bh:.1f}%")
    print("=" * 94)


if __name__ == "__main__":
    main()
