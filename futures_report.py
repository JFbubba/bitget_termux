"""
futures_report.py — état & réconciliation du FUTURES réel (LECTURE SEULE).

Classement : SAFE. Aucun ordre, aucune écriture (hors caches runtime). Miroir de
`accum_reconcile` (§43) pour la jambe futures du §45 : ce que la boucle auto a
DÉCIDÉ (journal de l'exécuteur) vs ce que Bitget a EXÉCUTÉ (fills : PnL réalisé,
frais, volumes) vs l'ÉTAT du compte (equity, position nette, stop journalier).

Le compte peut contenir des fills ANTÉRIEURS au bot (trading manuel du
propriétaire) : la réconciliation se borne aux fills postérieurs au PREMIER
ordre réel journalisé par l'exécuteur — jamais de mélange des genres.

CLI : python futures_report.py     (aussi servi par Telegram /futures — lecture seule)
"""

import json
import time

from config_utils import cfg as _cfg
from numeric_utils import safe_float

SYMBOL = "BTCUSDT"


# ---------- cœurs purs (testables) ----------

def resume_fills(rows, depuis_ts=None):
    """PUR. Agrège les fills futures : n, volume quote (USDT), PnL RÉALISÉ (champ
    `profit` de Bitget), frais USDT (valeur absolue), bornés aux fills >= depuis_ts
    (secondes). Entrées illisibles ignorées."""
    n = 0
    volume = pnl = frais = 0.0
    for r in rows or []:
        if not isinstance(r, dict):                     # multi-symboles §47 : tous comptent
            continue
        ts = safe_float(r.get("cTime"))
        if ts is None:
            continue
        if depuis_ts is not None and ts / 1000.0 < float(depuis_ts):
            continue
        n += 1
        volume += safe_float(r.get("quoteVolume")) or 0.0
        pnl += safe_float(r.get("profit")) or 0.0
        for f in r.get("feeDetail") or []:
            if isinstance(f, dict) and str(f.get("feeCoin", "")).upper() == "USDT":
                frais += abs(safe_float(f.get("totalFee")) or 0.0)
    return {"n_fills": n, "volume_usdt": round(volume, 4),
            "pnl_realise_usdt": round(pnl, 6), "frais_usdt": round(frais, 6),
            "net_usdt": round(pnl - frais, 6)}


def payoff_profile(rows, depuis_ts=None):
    """PUR (idée #3) : FORME de l'edge, pas seulement le PnL. Sépare gains/pertes
    réalisés (champ `profit` par fill) et classe l'edge — car scaler les caps (§45) sur
    un edge FRAGILE (gros taux de gain, gains minuscules, une grosse perte efface tout)
    est dangereux. Retourne win_rate, gain/perte moyens, payoff (gain moy / |perte moy|),
    espérance, et un verdict. `shape` : robuste / fragile / asymétrique+ / perdant / n/a."""
    gains, pertes = [], []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        ts = safe_float(r.get("cTime"))
        if ts is None or (depuis_ts is not None and ts / 1000.0 < float(depuis_ts)):
            continue
        p = safe_float(r.get("profit"))
        if p is None or p == 0:
            continue
        (gains if p > 0 else pertes).append(p)
    n = len(gains) + len(pertes)
    if n == 0:
        return {"n": 0, "shape": "n/a", "verdict": "pas de trade réalisé"}
    win_rate = len(gains) / n
    avg_win = sum(gains) / len(gains) if gains else 0.0
    avg_loss = sum(pertes) / len(pertes) if pertes else 0.0          # négatif
    payoff = (avg_win / abs(avg_loss)) if avg_loss else None
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss      # $/trade attendu
    if expectancy <= 0:
        shape, verdict = "perdant", "espérance ≤ 0 — NE PAS scaler les caps"
    elif win_rate >= 0.7 and (payoff is not None and payoff < 0.5):
        shape, verdict = "fragile", "gros taux de gain mais gains minuscules — une perte efface tout, prudence sur le scaling"
    elif win_rate <= 0.45 and (payoff is None or payoff >= 1.8):
        shape, verdict = "asymétrique+", "peu de gains mais gros — edge de queue, tolérer les séries perdantes"
    else:
        shape, verdict = "robuste", "profil équilibré — edge exploitable, scaling justifiable si soutenu"
    return {"n": n, "win_rate": round(win_rate, 3),
            "avg_win": round(avg_win, 4), "avg_loss": round(avg_loss, 4),
            "payoff": round(payoff, 2) if payoff is not None else None,
            "expectancy": round(expectancy, 4), "shape": shape, "verdict": verdict}


def stress_book(gross_usdt, equity_usdt, shock_pct, stop_pct=None):
    """PUR (idée Jasmine/stress) : impact CONSERVATEUR d'un choc de marché sur le livre.
    Pire cas : le choc est ADVERSE à toute l'exposition -> perte ≈ gross × shock%. Retourne
    {perte, equity_apres, breach_stop} — breach si la perte franchirait le stop journalier.
    Sanity-check avant d'ouvrir davantage (survivre à un crash −X% sans casser le stop)."""
    try:
        gross = float(gross_usdt or 0)
        eq = float(equity_usdt or 0)
        shock = abs(float(shock_pct or 0)) / 100.0
    except (TypeError, ValueError):
        return {"shock_pct": None, "perte_usdt": None, "breach_stop": None}
    stop = abs(float(stop_pct if stop_pct is not None
                     else _cfg("FUTURES_DAILY_LOSS_STOP_PCT", 5.0))) / 100.0
    perte = gross * shock
    breach = bool(eq > 0 and perte >= eq * stop)
    return {"shock_pct": round(shock * 100, 1), "perte_usdt": round(perte, 2),
            "equity_apres": round(eq - perte, 2), "breach_stop": breach}


def serie_pnl(rows, depuis_ts=None):
    """PUR. Série CUMULÉE du PnL réalisé NET du bot (profit − frais par fill, tous
    symboles §47), triée par temps : [[ts_s, cum_net], ...]. Pour la courbe du
    dashboard. Entrées illisibles ignorées."""
    pts = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        ts = safe_float(r.get("cTime"))
        if ts is None:
            continue
        ts_s = ts / 1000.0
        if depuis_ts is not None and ts_s < float(depuis_ts):
            continue
        net = safe_float(r.get("profit")) or 0.0
        for f in r.get("feeDetail") or []:
            if isinstance(f, dict) and str(f.get("feeCoin", "")).upper() == "USDT":
                net -= abs(safe_float(f.get("totalFee")) or 0.0)
        pts.append((ts_s, net))
    pts.sort()
    out, cum = [], 0.0
    for ts_s, net in pts:
        cum += net
        out.append([int(ts_s), round(cum, 6)])
    return out


def serie_funding(rows, depuis_ts=None):
    """PUR. Série CUMULÉE des règlements de funding : [[ts_s, cum], ...]."""
    pts = []
    for r in rows or []:
        if not isinstance(r, dict) or str(r.get("businessType", "")) != "contract_settle_fee":
            continue
        ts = safe_float(r.get("cTime"))
        if ts is None:
            continue
        ts_s = ts / 1000.0
        if depuis_ts is not None and ts_s < float(depuis_ts):
            continue
        pts.append((ts_s, safe_float(r.get("amount")) or 0.0))
    pts.sort()
    out, cum = [], 0.0
    for ts_s, v in pts:
        cum += v
        out.append([int(ts_s), round(cum, 6)])
    return out


def somme_funding(rows, depuis_ts=None):
    """PUR. Somme des règlements de FUNDING (businessType contract_settle_fee) des
    bills futures : c'est le REVENU réel du carry (et le coût de portage du
    directionnel). {n, total_usdt, recu_usdt, paye_usdt}."""
    n = 0
    total = recu = paye = 0.0
    for r in rows or []:
        if not isinstance(r, dict) or str(r.get("businessType", "")) != "contract_settle_fee":
            continue
        ts = safe_float(r.get("cTime"))
        if ts is None:
            continue
        if depuis_ts is not None and ts / 1000.0 < float(depuis_ts):
            continue
        v = safe_float(r.get("amount")) or 0.0
        n += 1
        total += v
        if v >= 0:
            recu += v
        else:
            paye += -v
    return {"n": n, "total_usdt": round(total, 6),
            "recu_usdt": round(recu, 6), "paye_usdt": round(paye, 6)}


def fetch_bills(limit=100):
    """Bills du compte futures (lecture seule, cachés 15 min). [] si indisponible."""
    def _fetch():
        import bitget_hub_bridge as hub
        d = hub._read(["account", "get_account_bills", "--accountType", "futures",
                       "--productType", "USDT-FUTURES", "--limit", str(int(limit))])
        rows = (d or {}).get("data")
        if isinstance(rows, dict):
            rows = rows.get("bills") or rows.get("list") or []
        return rows if isinstance(rows, list) else []
    try:
        import runtime_cache as rc
        return rc.get("fut_bills", 900, _fetch, fallback=[])
    except Exception:
        return []


def premier_ordre_reel_ts(events):
    """PUR. ts du PREMIER ordre réel journalisé par l'exécuteur (borne de la
    réconciliation : les fills antérieurs = trading manuel, hors périmètre)."""
    for e in events or []:
        if isinstance(e, dict) and e.get("action") == "FUTURES_REAL":
            return safe_float(e.get("ts"))
    return None


def compte_events(events):
    """PUR. Compte les évènements du journal exécuteur par action."""
    out = {}
    for e in events or []:
        if isinstance(e, dict):
            a = str(e.get("action", "?"))
            out[a] = out.get(a, 0) + 1
    return out


# ---------- lectures (best-effort, cachées) ----------

def fetch_fills(limit=100):
    """Fills futures BTCUSDT (lecture seule, cachés 10 min). [] si indisponible."""
    def _fetch():
        import bitget_hub_bridge as hub
        d = hub._read(["futures", "futures_get_fills", "--productType", "USDT-FUTURES",
                       "--symbol", SYMBOL, "--limit", str(int(limit))])
        rows = (d or {}).get("data")
        if isinstance(rows, dict):
            rows = rows.get("fillList") or rows.get("list") or []
        return rows if isinstance(rows, list) else []
    try:
        import runtime_cache as rc
        return rc.get("fut_fills", 600, _fetch, fallback=[])
    except Exception:
        return []


def snapshot():
    """État futures complet (lecture seule) : boucle auto (préview sans exécution),
    position, equity, stop journalier, journal exécuteur, fills réconciliés."""
    import futures_auto as fa
    import futures_executor as fe
    st = {}
    try:
        st = fa.status()
    except Exception:
        st = {"erreur": "status boucle indisponible"}
    carry = {}
    try:
        import carry_auto as ca
        carry = ca.status()
    except Exception:
        carry = {"erreur": "status carry indisponible"}
    events = fa._executor_events()
    debut = premier_ordre_reel_ts(events)
    led = {}
    try:
        led = json.loads(fe._ledger_path().read_text(encoding="utf-8"))
    except Exception:
        pass
    ej = led.get("equity_journal") or []
    delta7 = None
    eq_now = fe._futures_equity()
    if eq_now and len(ej) >= 2:
        base = None
        jour_now = int(time.time() // 86400)
        for row in ej:
            if isinstance(row, dict) and (jour_now - int(row.get("day", 0))) <= 7:
                base = safe_float(row.get("open_equity"))
                break
        if base:
            delta7 = round((eq_now / base - 1.0) * 100.0, 3)
    fills = fetch_fills() if debut else []          # une seule lecture -> fills_bot ET payoff
    return {
        "boucle": st,
        "carry": carry,
        "equity_usdt": eq_now,
        "equity_7j_delta_pct": delta7,
        "equity_journal_n": len(ej),
        "drawdown": fe.drawdown_status(),
        "stop_journalier": led.get("daily_loss_state") or {},
        "stop_pct": float(_cfg("FUTURES_DAILY_LOSS_STOP_PCT", 5.0)),
        "events": compte_events(events),
        "derniers_events": [{"action": e.get("action"), "ts": e.get("ts"),
                             "agent": (e.get("order") or {}).get("agent"),
                             "side": (e.get("order") or {}).get("side"),
                             "symbol": (e.get("order") or {}).get("symbol"),
                             "notional": (e.get("order") or {}).get("notional_usdt")
                                          or (e.get("order") or {}).get("size_btc"),
                             "reduce": bool((e.get("order") or {}).get("reduce")),
                             "reasons": e.get("reasons")}
                            for e in (events or [])
                            if e.get("action") in ("FUTURES_REAL", "FUTURES_TP_PARTIAL",
                                                   "FUTURES_EQUITY_REBASE")][-8:],
        "fills_bot": resume_fills(fills, depuis_ts=debut) if debut else
                     {"n_fills": 0, "note": "aucun ordre réel du bot encore"},
        "payoff": payoff_profile(fills, depuis_ts=debut) if debut else {"n": 0, "shape": "n/a"},
        "stress": stress_book((st or {}).get("gross_usdt", 0), eq_now,
                              _cfg("FUTURES_STRESS_SHOCK_PCT", 10)),
        "funding": somme_funding(fetch_bills(), depuis_ts=debut) if debut else {"n": 0},
        "caps": {"per_trade": fe._capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0,
                                         fe.FUT_ABS_MAX_PER_TRADE_USDT),
                 "gross": fe._capped("FUTURES_REAL_MAX_GROSS_USDT", 20.0,
                                     fe.FUT_ABS_MAX_GROSS_USDT),
                 "mur_per_trade": fe.FUT_ABS_MAX_PER_TRADE_USDT,
                 "mur_gross": fe.FUT_ABS_MAX_GROSS_USDT},
        # Compte CLASSIQUE (wallets cloisonnés). assetMode = réglage « Mode Multi-Actifs »
        # du wallet futures : 'union' (ON) force le crossed ; 'single' (OFF) permet l'isolé.
        # Le crossed ne puise QUE dans le wallet futures, jamais dans spot/earn/bots.
        "marge": {"asset_mode": fe._asset_mode(), "effectif": fe._marge_mode()},
    }


def _n(v, motif="{:.2f}"):
    return motif.format(v) if isinstance(v, (int, float)) else "—"


def build_report(s=None):
    """Rapport texte lisible (CLI + Telegram /futures). LECTURE SEULE."""
    s = snapshot() if s is None else s
    b = s.get("boucle") or {}
    d = b.get("decision") or {}
    stj = s.get("stop_journalier") or {}
    fb = s.get("fills_bot") or {}
    caps = s.get("caps") or {}
    lignes = [
        "=== FUTURES RÉEL (§45) — boucle auto · compte · réconciliation ===",
        f"Boucle : {'ARMÉE' if b.get('armed') else 'débrayée'} · consensus {b.get('consensus')} · "
        f"position {b.get('position') or 'flat'}",
        f"Décision (préview) : {str(d.get('action', '?')).upper()} {d.get('side') or ''} — {d.get('raison', '')}",
        (lambda c, cd: f"Carry : {'armé' if c.get('armed') else 'débrayé'} · APR net "
                       f"{c.get('apr_net_pct')} % ({c.get('attrait')}) · couverture "
                       f"{c.get('couverture_usdt')} $ -> {str(cd.get('action', 'rien')).upper()}"
         )(s.get("carry") or {}, (s.get("carry") or {}).get("decision") or {}),
        f"Equity wallet futures : {_n(s.get('equity_usdt'))} USDT · stop journalier −{s.get('stop_pct')} % "
        f"sur le LIVRE COUVERT (ouverture du jour : {_n(stj.get('open_equity'))} = futures + expo BTC carry)"
        + (f" · 7 j : {_n(s.get('equity_7j_delta_pct'), '{:+.2f}')} %"
           if s.get("equity_7j_delta_pct") is not None else ""),
        f"Caps : {_n(caps.get('per_trade'))} $/trade · {_n(caps.get('gross'))} $ cumulé "
        f"(murs {_n(caps.get('mur_per_trade'))}/{_n(caps.get('mur_gross'))})",
        (lambda mg: (lambda am, eff:
            f"Marge : {eff or '?'} — compte classique, Multi-Actifs "
            f"{'ON (union) → crossed forcé' if am == 'union' else 'OFF (single) → isolé' if am == 'single' else am or '?'}"
            f" · risque cloisonné au wallet futures (spot/earn/bots hors d'atteinte)"
         )(mg.get("asset_mode"), mg.get("effectif")))(s.get("marge") or {}),
        f"Journal exécuteur : {s.get('events') or 'vide'}",
    ]
    dd = s.get("drawdown") or {}
    if dd.get("halt"):
        lignes.insert(2, f"🛑 HALTE DRAWDOWN ACTIVE : dd {_n(dd.get('dd_pct'))} % ≥ MDD "
                         f"{_n(dd.get('max_dd_pct'), '{:.0f}')} % (pic {_n(dd.get('peak'))} $ / "
                         f"livre {_n(dd.get('equity'))} $) — TOUT NOUVEL ORDRE EST REFUSÉ (garde 6). "
                         "Si la baisse vient d'un RETRAIT/VIREMENT délibéré (pas d'une perte) : "
                         "python futures_executor.py --rebase-equity --confirm")
    elif dd:
        lignes.append(f"Halte MDD : non — dd {_n(dd.get('dd_pct'))} % / max "
                      f"{_n(dd.get('max_dd_pct'), '{:.0f}')} % (pic {_n(dd.get('peak'))} $, "
                      f"{dd.get('n_points')} pts)")
    if fb.get("n_fills"):
        lignes.append(f"Fills du BOT : {fb['n_fills']} · volume {_n(fb.get('volume_usdt'))} $ · "
                      f"PnL réalisé {_n(fb.get('pnl_realise_usdt'), '{:+.4f}')} $ · "
                      f"frais {_n(fb.get('frais_usdt'), '{:.4f}')} $ · "
                      f"NET {_n(fb.get('net_usdt'), '{:+.4f}')} $")
    else:
        lignes.append(f"Fills du BOT : {fb.get('note', 'aucun')}")
    po = s.get("payoff") or {}
    if po.get("n"):
        lignes.append(f"Forme de l'edge : {po.get('shape', '?').upper()} — "
                      f"win {round((po.get('win_rate') or 0) * 100)}% · payoff {_n(po.get('payoff'))} · "
                      f"espérance {_n(po.get('expectancy'), '{:+.4f}')} $/trade — {po.get('verdict', '')}")
    sx = s.get("stress") or {}
    if sx.get("shock_pct") is not None:
        lignes.append(f"Stress −{_n(sx.get('shock_pct'), '{:.0f}')}% : perte ~{_n(sx.get('perte_usdt'))} $ -> "
                      f"equity {_n(sx.get('equity_apres'))} $"
                      + (" · ⚠ FRANCHIRAIT le stop" if sx.get("breach_stop") else " · sous le stop ✓"))
    fu = s.get("funding") or {}
    if fu.get("n"):
        lignes.append(f"Funding (règlements 8h) : {_n(fu.get('total_usdt'), '{:+.6f}')} $ net "
                      f"({fu['n']} règlements : +{_n(fu.get('recu_usdt'), '{:.6f}')} reçus / "
                      f"−{_n(fu.get('paye_usdt'), '{:.6f}')} payés) — le REVENU du carry")
    lignes.append("Lecture seule (préview de décision, jamais d'exécution ici). VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
