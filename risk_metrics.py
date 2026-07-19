#!/usr/bin/env python3
"""risk_metrics.py — descripteurs de RISQUE du livre (VaR / ES-CVaR / Sortino / beta). SAFE, lecture seule.

Inspiré des métriques Aladdin (BlackRock) ADAPTÉES au crypto : les rendements crypto ont des queues
LOURDES et des sauts -> la VaR paramétrique-normale SOUS-ESTIME le tail risk. On calcule donc VaR et ES
EMPIRIQUES (historiques, quantiles bruts), + le Sortino (déviation à la baisse, mieux que Sharpe quand
la distribution est asymétrique) + le beta systématique (sensibilité au marché).

Ce sont des DESCRIPTEURS de risque (ERR-016/017 : jugés sur la PROTECTION/le sizing, JAMAIS une IC ;
ce n'est pas un signal directionnel). Ils N'AJOUTENT AUCUN MUR — les caps durs (50/250), le stop −5 %
et le kill-switch restent LE contrôle ; risk_metrics rend le risque VISIBLE (CLI + dashboard + alerte),
il ne décide rien. Purs (numpy), fail-safe.

CLI :
    python risk_metrics.py            # descripteurs du livre courant (lecture seule)
    python risk_metrics.py --alert    # idem, format concis (cron/Telegram)
"""
import json
import os
import sys

import numpy as np

from config_utils import cfg as _cfg

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".risk_alert_state.json")


def _arr(x):
    a = np.asarray([v for v in (x or []) if v is not None], float)
    return a[np.isfinite(a)]


def returns_from_curve(curve):
    """Rendements simples d'une courbe d'equity (pct-change). PUR. [] si < 2 points valides."""
    c = _arr(curve)
    if c.size < 2:
        return []
    prev = c[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(prev != 0, c[1:] / prev - 1.0, 0.0)
    return list(r[np.isfinite(r)])


def var_historical(returns, alpha=0.95):
    """VaR EMPIRIQUE : perte (positive) au quantile (1-alpha) des rendements. 0.0 si < 10 obs."""
    a = _arr(returns)
    if a.size < 10:
        return 0.0
    return float(max(0.0, -np.quantile(a, 1.0 - alpha)))


def expected_shortfall(returns, alpha=0.95):
    """ES / CVaR : moyenne des pertes PIRES que la VaR (tail risk, robuste aux queues lourdes).
    ES >= VaR toujours. 0.0 si < 10 obs."""
    a = _arr(returns)
    if a.size < 10:
        return 0.0
    thr = np.quantile(a, 1.0 - alpha)
    tail = a[a <= thr]
    return float(max(0.0, -(tail.mean() if tail.size else thr)))


def sortino(returns, rf=0.0):
    """Sortino = moyenne excédentaire / déviation À LA BAISSE (RMS des rendements négatifs).
    Meilleur que Sharpe quand la distribution est asymétrique (crypto). 0.0 si pas de downside."""
    a = _arr(returns)
    if a.size < 10:
        return 0.0
    ex = a - rf
    downside = ex[ex < 0]
    dd = float(np.sqrt((downside ** 2).mean())) if downside.size else 0.0
    return float(ex.mean() / dd) if dd > 0 else 0.0


def beta(returns, market):
    """Beta systématique = Cov(r, market)/Var(market), séries alignées par la fin. 0.0 si < 10 obs
    communes ou variance de marché nulle."""
    ax, ay = np.asarray(returns, float), np.asarray(market, float)
    n = min(ax.size, ay.size)
    if n < 10:
        return 0.0
    ax, ay = ax[-n:], ay[-n:]
    mask = np.isfinite(ax) & np.isfinite(ay)
    ax, ay = ax[mask], ay[mask]
    if ax.size < 10 or ay.var() <= 0:
        return 0.0
    return float(np.cov(ax, ay, bias=True)[0, 1] / ay.var())   # bias=True -> ddof=0, cohérent avec .var()


def report():
    """Descripteurs du livre courant. PRIORITÉ à l'equity RÉELLE du livre futures couvert
    (futures_executor.equity_curve, points intraday/journaliers) ; repli sur les courbes paper
    (realized -> outcomes signaux). La source est indiquée. Fail-safe -> {}."""
    curve, source = None, None
    try:
        import futures_executor as fx
        c = fx.equity_curve()
        if c and len(c) >= 3:
            curve, source = c, "livre futures réel"
    except Exception:
        pass
    if curve is None:
        try:
            import equity_curve as ec
            c = ec.realized_curve()
            if c and len(c) >= 3:
                curve, source = c, "paper réalisé"
            else:
                curve, source = ec.outcomes_curve(), "paper signaux (fixed-fractional)"
        except Exception:
            curve = None
    rets = returns_from_curve(curve) if curve else []
    if len(rets) < 10:
        return {"n": len(rets), "source": source, "note": "historique insuffisant (< 10 rendements)"}
    return {
        "n": len(rets), "source": source,
        "var_95": round(var_historical(rets, 0.95), 5),
        "es_95": round(expected_shortfall(rets, 0.95), 5),
        "var_99": round(var_historical(rets, 0.99), 5),
        "es_99": round(expected_shortfall(rets, 0.99), 5),
        "sortino": round(sortino(rets), 4),
    }


def _alert(r):
    """Alerte Telegram de TAIL-RISK : ES99 >= plancher configurable (RISK_ES99_ALERT, défaut 2 %/point)
    OU >= 2× la dernière valeur (spike de régime de risque). Dédupliqué via .risk_alert_state.json,
    fail-safe. NE DÉCIDE RIEN — les caps 50/250 + stop −5 % + kill-switch restent le contrôle."""
    if "note" in r or r.get("es_99") is None:
        return False
    es99 = float(r["es_99"])
    try:
        floor = float(_cfg("RISK_ES99_ALERT", 0.02))
    except (TypeError, ValueError):
        floor = 0.02
    try:
        last = float(json.load(open(STATE, encoding="utf-8")).get("es_99", 0.0))
    except Exception:
        last = 0.0
    breach = es99 >= floor or (last > 0 and es99 >= 2.0 * last)
    if breach:
        try:
            import telegram_notifier as tn
            tn.send_telegram(f"⚠️ TAIL-RISK\nES99 {es99:.2%} · VaR99 {r['var_99']:.2%} · "
                             f"Sortino {r['sortino']} (n={r['n']}, {r.get('source')})\n"
                             f"Descripteur — les caps 50/250 + stop −5 % contrôlent.")
        except Exception:
            pass
    try:
        json.dump({"es_99": es99}, open(STATE, "w"))
    except Exception:
        pass
    return breach


def main():
    r = report()
    alert = "--alert" in sys.argv
    if alert:
        _alert(r)
    if alert:
        if "note" in r:
            print(f"RISK: {r['note']}")
        else:
            print(f"RISK (n={r['n']}): VaR95 {r['var_95']:.2%} · ES95 {r['es_95']:.2%} · "
                  f"VaR99 {r['var_99']:.2%} · ES99 {r['es_99']:.2%} · Sortino {r['sortino']}")
    else:
        print("=== DESCRIPTEURS DE RISQUE (livre, lecture seule — n'ajoute aucun mur) ===")
        print(f"  source         : {r.get('source') or '—'}")
        if "note" in r:
            print(f"  {r['note']}")
        else:
            print(f"  n rendements   : {r['n']}")
            print(f"  VaR 95% / 99%  : {r['var_95']:.2%} / {r['var_99']:.2%}  (perte au quantile)")
            print(f"  ES  95% / 99%  : {r['es_95']:.2%} / {r['es_99']:.2%}  (CVaR = tail au-delà VaR)")
            print(f"  Sortino        : {r['sortino']}  (rendement / déviation baissière)")
        print("Descripteur seul — les caps durs + stop −5 % restent LE contrôle. VERDICT: SAFE")


if __name__ == "__main__":
    main()
