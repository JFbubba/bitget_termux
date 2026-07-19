"""
mandate.py — le MANDAT DE GESTION encodé en règles DURES et testables.

Classement : SAFE. Pur / lecture seule, AUCUN ordre. Ce module ne TRADE pas :
il dit seulement ce qui est AUTORISÉ. Il traduit les choix du propriétaire
(« au bot de gérer comme un trader pro ») en politique exécutable :

  • objectif : MAXIMISER le rendement SOUS CONTRAINTE de drawdown (MDD ≤ 20 %) ;
  • levier : le bot l'ajuste SEUL mais SOUS un mur dur (×5) — vol-targeting ;
  • porte d'edge paper -> réel : un agent futures ne passe en RÉEL que s'il bat
    le seuil déflaté (DSR) sur un échantillon suffisant (cf. validation T5) ;
  • numéraire dynamique : si le dollar se déprécie, tourner hors USD (BTC / or) ;
  • fenêtres de session (ouvertures Asie/Londres/NY) + black-out macro (CPI/FOMC).

Tout est paramétré dans config.py (bloc MANDATE_*). Fonctions PURES -> testables
sans réseau. Le verrou MANDATE_LIVE_ENABLED garde le réel coupé par défaut.
"""

import json
from pathlib import Path

VALIDATION_REPORT = Path(__file__).resolve().parent / "validation_report.json"


from config_utils import cfg as _cfg
import math


# ---------- verrou réel ----------

def live_enabled():
    """Le trading RÉEL est-il armé ? False par défaut -> tout reste paper."""
    import os
    if os.getenv("MANDATE_LIVE", "").lower() in ("1", "true", "yes", "on"):
        return bool(_cfg("MANDATE_LIVE_ENABLED", False))  # env ne peut qu'ACTIVER si config l'autorise
    return bool(_cfg("MANDATE_LIVE_ENABLED", False))


# ---------- levier (mur dur + ajustement autonome) ----------

# Mur ABSOLU de levier — identique à futures_executor.FUT_ABS_MAX_LEVERAGE. Jamais dépassable.
FUT_ABS_MAX_LEVERAGE = 5.0

def max_leverage():
    """Plafond DUR de levier. La config peut l'ABAISSER, jamais dépasser le mur absolu ×5
    (aligné sur futures_executor) — le bot ne peut JAMAIS le dépasser. (§revue chemin argent)"""
    try:
        lev = float(_cfg("MANDATE_MAX_LEVERAGE", 5.0))
    except (TypeError, ValueError):
        return FUT_ABS_MAX_LEVERAGE
    if not math.isfinite(lev) or lev <= 0:
        return FUT_ABS_MAX_LEVERAGE
    return min(FUT_ABS_MAX_LEVERAGE, lev)


def target_leverage(conviction, volatility, base_vol=0.02):
    """Levier visé par le bot (vol-targeting), TOUJOURS borné par le mur. PUR.

    conviction ∈ [0,1] (force du signal de l'essaim) ; volatility = vol réalisée
    (ex. écart-type des rendements). Plus la conviction est haute ET la vol basse,
    plus on autorise de levier — mais jamais au-delà de max_leverage().
    """
    cap = max_leverage()
    try:
        conv, vol, bv = float(conviction), float(volatility), float(base_vol)
    except (TypeError, ValueError):
        return 1.0
    # Non-finis (NaN/inf) -> plancher 1.0 (JAMAIS le levier max) : un contrôle de risque
    # doit échouer vers le BAS. (§revue chemin argent — Thème 4)
    if not (math.isfinite(conv) and math.isfinite(vol) and math.isfinite(bv)):
        return 1.0
    c = max(0.0, min(1.0, conv))
    vol = max(1e-6, vol)
    # cible ∝ conviction, atténuée par la vol relative ; plancher 1 (pas de levier).
    lev = 1.0 + (cap - 1.0) * c * min(1.0, bv / vol)
    if not math.isfinite(lev):
        return 1.0
    return round(max(1.0, min(cap, lev)), 2)


def conditional_volatility(closes):
    """Vol CONDITIONNELLE (GARCH(1,1), repli EWMA/écart-type) pour le vol-targeting.
    Best-effort -> None si indisponible. Réactive aux chocs récents (mieux qu'un σ plat)."""
    try:
        import volatility
        return volatility.conditional_vol(closes)
    except Exception:
        return None


def leverage_for(conviction, closes, base_vol=0.02):
    """Levier visé À PARTIR DES PRIX : vol conditionnelle GARCH -> target_leverage borné
    par le mur. Si la vol n'est pas calculable, retombe sur base_vol. PUR (best-effort).

    ⚠️ ADVISORY/PAPER (audit B-3) : ce vol-targeting n'est consommé que par `preorder_engine`
    (paper) et `bitget_hub_bridge` (advisory). La boucle futures RÉELLE (`futures_auto`) passe un
    levier FIXE `FUTURES_AUTO_LEVERAGE` (défaut 2.0, clampé au mur ×5) — le risque réel est piloté
    par les caps de notional (50/250), le SL, `FUTURES_RISK_PCT_PER_TRADE` et le gate systémique
    `GEOMETRIC_RISK_SIZING`, PAS par ce levier vol-ciblé. Brancher au réel = décision proprio."""
    vol = conditional_volatility(closes)
    return target_leverage(conviction, vol if vol and vol > 0 else base_vol, base_vol=base_vol)


# ---------- contrainte de drawdown (la limite qui rend « MAX » cohérent) ----------

def drawdown_from_peak(equity_curve):
    """Drawdown courant (fraction, ≥0) depuis le plus-haut de la courbe d'equity. PUR."""
    vals = [float(x) for x in equity_curve if x is not None]
    if len(vals) < 2:
        return 0.0
    peak = vals[0]
    dd = 0.0
    for v in vals:
        peak = max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak)
    return round(dd, 4)


def drawdown_halt(equity_curve, max_dd_pct=None):
    """Faut-il HALTER tout nouveau risque ? (drawdown ≥ MDD toléré). PUR.
    Retourne (halt: bool, dd_pct: float)."""
    max_dd = float(_cfg("MANDATE_MAX_DRAWDOWN_PCT", 20.0) if max_dd_pct is None else max_dd_pct)
    present = [x for x in (equity_curve or []) if x is not None]
    finite, corrupt = [], False
    for x in present:
        try:
            xf = float(x)
        except (TypeError, ValueError):
            corrupt = True
            continue
        if math.isfinite(xf):
            finite.append(xf)
        else:
            corrupt = True
    # Courbe corrompue (NaN/inf/non numérique) -> HALTE : on ne peut pas prouver l'absence
    # de drawdown. (§revue chemin argent — Thème 4). N'empêche que d'OUVRIR, jamais de sortir.
    if corrupt:
        return (True, 0.0)
    dd_pct = drawdown_from_peak(finite) * 100.0
    return (dd_pct >= max_dd, round(dd_pct, 2))


# ---------- porte d'edge : paper -> réel (futures) ----------

def _load_report(path=None):
    try:
        p = Path(path) if path else VALIDATION_REPORT
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _passes_edge(agent, report, dsr_min, min_n):
    """L'agent bat-il la porte d'edge ? Exige l'edge REPLAY (DSR ≥ seuil ET echantillon
    suffisant dans 'ranking') ET une confirmation sur les VOTES REELS ('live' : echantillon
    suffisant ET IC significatif). PUR, INDEPENDANT du verrou reel -> testable seul.
    Conservateur : pas de preuve live -> False (on ne risque pas du reel sur un edge non
    confirme par les votes reellement emis)."""
    rep = report or {}
    ranking_ok = False
    for row in rep.get("ranking", []):
        if str(row.get("agent")) == str(agent):
            ranking_ok = (float(row.get("dsr", 0) or 0) >= float(dsr_min)
                          and int(row.get("n", 0) or 0) >= int(min_n))
            break
    if not ranking_ok:
        return False
    live_min_n = int(_cfg("MANDATE_LIVE_MIN_SAMPLES", 60))
    live_min_t = float(_cfg("MANDATE_LIVE_MIN_IC_T", 2.0))
    for r in (rep.get("live", {}) or {}).get("agents", []):
        if str(r.get("agent")) == str(agent):
            return (int(r.get("n", 0) or 0) >= live_min_n
                    and float(r.get("ic_t", 0) or 0) >= live_min_t)
    return False


def futures_live_allowed(agent, report=None, dsr_min=None, min_samples=None):
    """Un agent futures a-t-il le DROIT de trader en RÉEL ? PUR (report injectable).

    Exige : trading réel armé ET l'agent passe la porte d'edge. Le verrou réel
    (live_enabled) prime : tant qu'il est coupé, la réponse est toujours False.
    """
    if not live_enabled():
        return False
    rep = report if report is not None else _load_report()
    dsr_min = _cfg("MANDATE_FUTURES_DSR_MIN", 0.90) if dsr_min is None else dsr_min
    min_n = _cfg("MANDATE_FUTURES_MIN_SAMPLES", 120) if min_samples is None else min_samples
    return _passes_edge(agent, rep, dsr_min, min_n)


def live_agents(report=None):
    """Liste des agents futures autorisés en réel (passent la porte d'edge). PUR."""
    rep = report if report is not None else _load_report()
    return [row.get("agent") for row in rep.get("ranking", [])
            if futures_live_allowed(row.get("agent"), rep)]


# ---------- numéraire dynamique (couverture contre la baisse du dollar) ----------

def numeraire_recommendation(usd_change_pct, refuges=None, threshold=None):
    """Si le dollar se déprécie au-delà du seuil, recommander de tourner hors USD
    vers un refuge (BTC / or tokenisé). PUR. Retourne {hold, rotate, reason}."""
    refuges = list(_cfg("MANDATE_NUMERAIRE_REFUGES", ["BTCUSDT", "XAUTUSDT"]) if refuges is None else refuges)
    thr = float(_cfg("MANDATE_USD_WEAK_THRESHOLD", -3.0) if threshold is None else threshold)
    if usd_change_pct is not None and float(usd_change_pct) <= thr:
        return {"hold": "REFUGE", "rotate": refuges,
                "reason": f"USD {usd_change_pct:+.1f}% ≤ {thr:.1f}% -> rotation hors dollar"}
    return {"hold": "USDT", "rotate": [], "reason": "dollar stable -> rester en USDT"}


# ---------- fenêtres de session ----------

def in_active_session(hour_utc, sessions=None):
    """Sommes-nous dans une fenêtre de session active (ouvertures de bourses) ? PUR.
    ⚠️ ADVISORY (audit B-6) : NON appliqué sur le chemin réel — `futures_executor.guards` appelle ce
    filtre seulement si `hour_utc` est fourni, or la boucle futures réelle passe `hour_utc=None`
    (crypto 24/7, aucune restriction de session par conception). Utilisé en advisory (hub_bridge)."""
    sessions = _cfg("MANDATE_ACTIVE_SESSIONS_UTC", [[0, 3], [7, 10], [13, 17]]) if sessions is None else sessions
    h = float(hour_utc) % 24
    return any(float(a) <= h < float(b) for a, b in sessions)


# ---------- black-out macro (CPI / FOMC) ----------

def macro_blackout(now_ts, event_ts_list, pre_min=None, post_min=None):
    """Sommes-nous dans la fenêtre de black-out autour d'une annonce à fort impact ?
    PUR. event_ts_list = timestamps (s) des annonces. On dégage le risque pré/post."""
    pre = float(_cfg("MANDATE_MACRO_BLACKOUT_PRE_MIN", 30) if pre_min is None else pre_min) * 60.0
    post = float(_cfg("MANDATE_MACRO_BLACKOUT_POST_MIN", 15) if post_min is None else post_min) * 60.0
    now = float(now_ts)
    for ev in event_ts_list or []:
        ev = float(ev)
        if (ev - pre) <= now <= (ev + post):
            return True
    return False


# ---------- sizing ----------

def risk_per_trade_usd(equity_usd, pct=None):
    """Montant à risquer sur UN trade (USD). PUR."""
    pct = float(_cfg("MANDATE_RISK_PER_TRADE_PCT", 0.75) if pct is None else pct)
    return round(float(equity_usd) * pct / 100.0, 2)


def deployable_usd(equity_usd, cash_floor_pct=None):
    """Capital déployable (USD) en gardant la réserve cash plancher. PUR."""
    floor = float(_cfg("MANDATE_CASH_FLOOR_PCT", 10.0) if cash_floor_pct is None else cash_floor_pct)
    return round(float(equity_usd) * (1.0 - floor / 100.0), 2)


# ---------- rapport ----------

def summary():
    rep = _load_report()
    allowed = live_agents(rep)
    return {
        "live_enabled": live_enabled(),
        "capital_usdt": _cfg("MANDATE_CAPITAL_USDT", 1000.0),
        "target": _cfg("MANDATE_TARGET", "MAX"),
        "max_drawdown_pct": _cfg("MANDATE_MAX_DRAWDOWN_PCT", 20.0),
        "max_leverage": max_leverage(),
        "risk_per_trade_pct": _cfg("MANDATE_RISK_PER_TRADE_PCT", 0.75),
        "futures_live_agents": allowed,
        "futures_dsr_min": _cfg("MANDATE_FUTURES_DSR_MIN", 0.90),
        "numeraire_refuges": _cfg("MANDATE_NUMERAIRE_REFUGES", []),
    }


def build_report():
    s = summary()
    lock = "ARMÉ (RÉEL)" if s["live_enabled"] else "VERROUILLÉ (paper / dry-run)"
    fut = ", ".join(s["futures_live_agents"]) if s["futures_live_agents"] else "aucun (edge non prouvé)"
    return ("=== MANDAT DE GESTION (encodé) ===\n"
            f"Verrou réel : {lock}\n"
            f"Capital : {s['capital_usdt']} USDT · objectif : {s['target']} "
            f"SOUS drawdown ≤ {s['max_drawdown_pct']}%\n"
            f"Levier : mur dur ×{s['max_leverage']} (le bot ajuste sous ce plafond)\n"
            f"Risque/trade : {s['risk_per_trade_pct']}% · réserve cash gardée\n"
            f"Futures autorisés en RÉEL : {fut}  (seuil DSR ≥ {s['futures_dsr_min']})\n"
            f"Numéraire refuge si USD faiblit : {', '.join(s['numeraire_refuges'])}\n"
            "Pur / lecture seule. AUCUN ordre passé ici. VERDICT: SAFE")


def main():
    print(build_report())


if __name__ == "__main__":
    main()
