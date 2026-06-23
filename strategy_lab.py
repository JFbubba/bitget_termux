"""
strategy_lab.py — agent BACKTESTER AUTONOME (intake Drive package/ -> stratégies).

Rôle : tester/classer des stratégies par performance HONNÊTE (frais + walk-forward
+ PBO), les AMÉLIORER (recherche de paramètres robuste), en COMPOSER de nouvelles
(régime-gating, ensemble), et PROMOUVOIR celles qui passent une barre de robustesse
en écrivant un RAPPORT (.md) + un fichier CODE prêt à l'emploi (.py) sous
`strategies_out/`.

Anti-overfit (cf. RESEARCH_NOTES §4/§8/§11) : une stratégie n'est promue que si
  Sharpe ≥ seuil ET edge vs buy&hold > 0 ET tranches walk-forward majoritairement
  gagnantes ET PBO < 0.5 ET assez de trades.
La plupart ÉCHOUERONT — c'est honnête : on ne promeut pas du surappris.

Signaux PURS et CAUSAUX : `signal[i]` n'utilise que les bougies jusqu'à `i`
(aucun look-ahead). SAFE : aucune exécution d'ordre ; sorties = fichiers d'analyse.
"""

import time
from pathlib import Path

import backtest_brain as bt
import price_action as pa
import regime_features as rf

OUT_DIR = Path(__file__).resolve().parent / "strategies_out"
FEE = 0.0006
HORIZON = 4

# seuils de promotion (volontairement exigeants)
PROMOTE = {"sharpe": 0.3, "edge": 0.0, "frac_folds_pos": 0.6, "trades": 20, "pbo": 0.5}


# ---------- helpers causaux (séries alignées sur les barres) ----------

def _closes(candles):
    return [float(c["close"]) for c in candles]


def _ema_series(values, period):
    k = 2.0 / (period + 1)
    out, e = [], values[0] if values else 0.0
    for v in values:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def _rsi_series(values, period=14):
    n = len(values)
    out = [50.0] * n
    if n < period + 1:
        return out
    gains = sum(max(values[i] - values[i - 1], 0) for i in range(1, period + 1))
    losses = sum(max(values[i - 1] - values[i], 0) for i in range(1, period + 1))
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, n):
        ch = values[i] - values[i - 1]
        ag = (ag * (period - 1) + max(ch, 0)) / period
        al = (al * (period - 1) + max(-ch, 0)) / period
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


# ---------- stratégies de base (signals[i] causal, ∈ {-1,0,+1}) ----------

def strat_ema_cross(candles, fast=20, slow=50):
    cl = _closes(candles)
    ef, es = _ema_series(cl, fast), _ema_series(cl, slow)
    return [0 if i < slow else (1 if ef[i] > es[i] else -1) for i in range(len(cl))]


def strat_rsi_reversion(candles, period=14, low=30, high=70):
    rsi = _rsi_series(_closes(candles), period)
    return [1 if rsi[i] < low else -1 if rsi[i] > high else 0 for i in range(len(rsi))]


def strat_donchian_breakout(candles, n=20):
    sig = [0] * len(candles)
    for i in range(n, len(candles)):
        hh = max(float(c["high"]) for c in candles[i - n:i])
        ll = min(float(c["low"]) for c in candles[i - n:i])
        c = float(candles[i]["close"])
        sig[i] = 1 if c > hh else -1 if c < ll else 0
    return sig


def strat_vp_fade(candles, window=60):
    import pro_indicators as pi
    sig = [0] * len(candles)
    for i in range(window, len(candles)):
        try:
            vp = pi.volume_profile(candles[i - window:i + 1])
            price = float(candles[i]["close"])
            sig[i] = 1 if price < vp["value_area_low"] else -1 if price > vp["value_area_high"] else 0
        except Exception:
            sig[i] = 0
    return sig


def strat_structure(candles, window=60):
    sig = [0] * len(candles)
    for i in range(window, len(candles)):
        w = candles[i - window:i + 1]
        ms = pa.market_structure([c["high"] for c in w], [c["low"] for c in w], [c["close"] for c in w])
        sig[i] = ms["event_dir"] if ms["event"] == "BOS" else 0
    return sig


# ---------- composition (nouvelles stratégies à partir des existantes) ----------

def regime_gated(signals, candles, window=63):
    """N'autorise le signal que si le régime de dérive le confirme (up_fraction). Pur."""
    cl = _closes(candles)
    out = list(signals)
    for i in range(len(out)):
        if i < window:
            out[i] = 0
            continue
        uf = rf.up_fraction(cl[:i + 1], window)
        if out[i] > 0 and uf < 0.5:
            out[i] = 0
        elif out[i] < 0 and uf > 0.5:
            out[i] = 0
    return out


def ensemble(signal_lists):
    """Vote majoritaire de plusieurs séries de signaux. Pur."""
    n = min(len(s) for s in signal_lists) if signal_lists else 0
    out = []
    for i in range(n):
        s = sum(sl[i] for sl in signal_lists)
        out.append(1 if s > 0 else -1 if s < 0 else 0)
    return out


# ---------- backtest honnête + score ----------

def backtest(signals, candles, horizon=HORIZON, fee=FEE):
    """Évalue une série de signaux : métriques + pnl par pas + walk-forward + edge.
    Réutilise backtest_brain (evaluate/forward_returns/walk_forward). Pur."""
    cl = _closes(candles)
    rets = bt.forward_returns(cl, horizon)
    sig = signals[:len(rets)]
    m = bt.evaluate(sig, rets, fee)
    pnls = [((1 if s > 0 else -1 if s < 0 else 0) * r - (fee if s else 0.0)) for s, r in zip(sig, rets)]
    folds = bt.walk_forward([p for p in pnls if p != 0] or pnls)
    fpos = (sum(1 for f in folds if f > 0) / len(folds)) if folds else 0.0
    bh = 1.0
    for r in rets:
        bh *= (1 + r)
    edge = round(m["total_return"] - (bh - 1), 5)
    score = m["sharpe"] * fpos
    if edge <= 0:
        score *= 0.3
    if m["trades"] < PROMOTE["trades"]:
        score *= 0.5
    return {**m, "edge": edge, "frac_folds_pos": round(fpos, 3),
            "score": round(score, 4), "pnls": pnls, "folds": folds}


def _passes(r, pbo_val):
    return (r["sharpe"] >= PROMOTE["sharpe"] and r["edge"] > PROMOTE["edge"]
            and r["frac_folds_pos"] >= PROMOTE["frac_folds_pos"]
            and r["trades"] >= PROMOTE["trades"]
            and (pbo_val is None or pbo_val < PROMOTE["pbo"]))


# ---------- registre + amélioration ----------

def base_registry(candles):
    return {n: build_named(n, candles) for n in
            ("ema_cross_20_50", "rsi_reversion_14", "donchian_20", "vp_fade_60", "structure_bos")}


def build_named(name, candles):
    """Reconstruit une stratégie (base / améliorée / composite) depuis son NOM. Pur.

    Centralise la construction pour que le code promu reproduise EXACTEMENT la
    stratégie testée (aucune divergence entre backtest et fichier prêt à l'emploi)."""
    if name.startswith("ema_cross_"):
        _, _, f, s = name.split("_")
        return strat_ema_cross(candles, int(f), int(s))
    if name.startswith("rsi_reversion_"):
        return strat_rsi_reversion(candles, int(name.split("_")[2]))
    if name.startswith("donchian_"):
        return strat_donchian_breakout(candles, int(name.split("_")[1]))
    if name.startswith("vp_fade_"):
        return strat_vp_fade(candles, int(name.split("_")[2]))
    if name == "structure_bos":
        return strat_structure(candles, 60)
    if name.endswith("+regime"):
        return regime_gated(build_named(name[:-len("+regime")], candles), candles)
    if name == "ensemble_trend_rev_struct":
        return ensemble([build_named("ema_cross_20_50", candles),
                         build_named("rsi_reversion_14", candles),
                         build_named("structure_bos", candles)])
    raise ValueError(f"stratégie inconnue: {name}")


def improve_ema(candles):
    """Recherche de paramètres robuste pour ema_cross : meilleur score. Pur-ish."""
    best, best_name, best_sig = None, None, None
    for fast in (10, 20, 30):
        for slow in (40, 50, 100):
            if fast >= slow:
                continue
            sig = strat_ema_cross(candles, fast, slow)
            r = backtest(sig, candles)
            if best is None or r["score"] > best["score"]:
                best, best_name, best_sig = r, f"ema_cross_{fast}_{slow}", sig
    return best_name, best_sig, best


def compose(registry, candles):
    """Génère de nouvelles stratégies : régime-gating des trend + ensemble. Pur."""
    new = {}
    for name in ("ema_cross_20_50", "donchian_20"):
        if name in registry:
            new[f"{name}+regime"] = regime_gated(registry[name], candles)
    members = [registry[n] for n in ("ema_cross_20_50", "rsi_reversion_14", "structure_bos") if n in registry]
    if len(members) >= 2:
        new["ensemble_trend_rev_struct"] = ensemble(members)
    return new


# ---------- promotion : rapport + code prêt à l'emploi ----------

def _strategy_code(name, symbol, timeframe):
    return f'''"""
{name} — stratégie promue par strategy_lab (backtester autonome).
Référence : {symbol} {timeframe}, frais {FEE * 100:.3f}%/trade, horizon {HORIZON}.
PRÊT À L'EMPLOI — signal ADVISORY (+1 long / -1 short / 0 flat), AUCUN ordre passé.
Réutilise la logique TESTÉE de strategy_lab (nécessite le repo) -> zéro divergence.

Usage :  python {name}.py SYMBOL
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # racine du repo
import strategy_lab as L

STRATEGY = "{name}"


def signal(candles):
    """Signal causal +1/-1/0 à la dernière bougie."""
    sig = L.build_named(STRATEGY, candles)
    return sig[-1] if sig else 0


if __name__ == "__main__":
    sym = (sys.argv[1] if len(sys.argv) > 1 else "{symbol}").upper()
    try:
        import technicals as tk
        candles = tk.fetch_candles(sym, "{timeframe}", 300)
        print(f"{{sym}} {{STRATEGY}} signal = {{signal(candles):+d}}")
    except Exception as exc:
        print("data indisponible:", exc)
'''


def promote(name, r, symbol, timeframe):
    """Écrit le rapport + le code prêt à l'emploi d'une stratégie promue."""
    OUT_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = name.replace("+", "_plus_")
    report = f"""# Rapport stratégie — {name}
_généré par strategy_lab le {time.strftime('%Y-%m-%d %H:%M')} · {symbol} {timeframe}_

## Performance (honnête : frais {FEE*100:.3f}%/trade, horizon {HORIZON})
- **Sharpe** : {r['sharpe']}
- **Rendement total** : {r['total_return']*100:.2f}%  ·  **edge vs buy&hold** : {r['edge']*100:.2f}%
- **Hit rate** : {r['hit_rate']*100:.1f}%  ·  **trades** : {r['trades']}
- **Max drawdown** : {r['max_drawdown']*100:.1f}%
- **Walk-forward** : tranches gagnantes {r['frac_folds_pos']*100:.0f}% ({r['folds']})
- **Score composite** : {r['score']}

## Verdict
Stratégie **PROMUE** : passe la barre de robustesse (Sharpe≥{PROMOTE['sharpe']},
edge>0, tranches gagnantes≥{PROMOTE['frac_folds_pos']*100:.0f}%, trades≥{PROMOTE['trades']}, PBO<{PROMOTE['pbo']}).
⚠️ Performance backtest ≠ garantie future. À re-valider en paper avant tout capital.

## Fichier prêt à l'emploi
`{slug}.py` (signal advisory, aucun ordre passé).
"""
    (OUT_DIR / f"{slug}_{ts}.md").write_text(report, encoding="utf-8")
    (OUT_DIR / f"{slug}.py").write_text(_strategy_code(name, symbol, timeframe), encoding="utf-8")
    return slug


# ---------- orchestrateur autonome ----------

def run(symbol="BTCUSDT", timeframe="1H", limit=500):
    """Boucle de l'agent : registre -> amélioration -> composition -> classement
    -> PBO -> promotion des robustes (rapport + code). Retourne un résumé."""
    try:
        import technicals as tk
        candles = tk.fetch_candles(symbol, timeframe, limit)
    except Exception as exc:
        return {"error": f"data indisponible: {exc}"}
    if len(candles) < 120:
        return {"error": "pas assez de bougies"}

    registry = base_registry(candles)
    # amélioration (recherche de params) + composition (nouvelles stratégies)
    en, esig, _ = improve_ema(candles)
    registry[en] = esig
    registry.update(compose(registry, candles))

    results = {name: backtest(sig, candles) for name, sig in registry.items()}
    p = bt.pbo({name: r["pnls"] for name, r in results.items()})
    ranked = sorted(results.items(), key=lambda kv: kv[1]["score"], reverse=True)

    promoted = []
    for name, r in ranked:
        if _passes(r, p.get("pbo")):
            promoted.append(promote(name, r, symbol, timeframe))

    return {
        "symbol": symbol, "timeframe": timeframe, "n_strategies": len(registry),
        "pbo": p.get("pbo"),
        "ranking": [(n, r["score"], f"sharpe {r['sharpe']}", f"edge {r['edge']*100:.1f}%",
                     f"folds+ {int(r['frac_folds_pos']*100)}%", f"trades {r['trades']}") for n, r in ranked],
        "promoted": promoted or "aucune (barre de robustesse non franchie — honnête)",
    }


def main():
    import json
    import sys
    sym = (sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT").upper()
    tf = sys.argv[2] if len(sys.argv) > 2 else "1H"
    print(json.dumps(run(sym, tf), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
