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
        if not isinstance(r, dict) or str(r.get("symbol", "")).upper() != SYMBOL:
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
    events = fa._executor_events()
    debut = premier_ordre_reel_ts(events)
    led = {}
    try:
        led = json.loads(fe._ledger_path().read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "boucle": st,
        "equity_usdt": fe._futures_equity(),
        "stop_journalier": led.get("daily_loss_state") or {},
        "stop_pct": float(_cfg("FUTURES_DAILY_LOSS_STOP_PCT", 5.0)),
        "events": compte_events(events),
        "derniers_events": [{"action": e.get("action"), "ts": e.get("ts"),
                             "agent": (e.get("order") or {}).get("agent"),
                             "side": (e.get("order") or {}).get("side"),
                             "notional": (e.get("order") or {}).get("notional_usdt"),
                             "reasons": e.get("reasons")}
                            for e in (events or [])[-5:]],
        "fills_bot": resume_fills(fetch_fills(), depuis_ts=debut) if debut else
                     {"n_fills": 0, "note": "aucun ordre réel du bot encore"},
        "caps": {"per_trade": fe._capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0,
                                         fe.FUT_ABS_MAX_PER_TRADE_USDT),
                 "gross": fe._capped("FUTURES_REAL_MAX_GROSS_USDT", 20.0,
                                     fe.FUT_ABS_MAX_GROSS_USDT),
                 "mur_per_trade": fe.FUT_ABS_MAX_PER_TRADE_USDT,
                 "mur_gross": fe.FUT_ABS_MAX_GROSS_USDT},
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
        f"Equity : {_n(s.get('equity_usdt'))} USDT · stop journalier −{s.get('stop_pct')} % "
        f"(ouverture du jour : {_n(stj.get('open_equity'))})",
        f"Caps : {_n(caps.get('per_trade'))} $/trade · {_n(caps.get('gross'))} $ cumulé "
        f"(murs {_n(caps.get('mur_per_trade'))}/{_n(caps.get('mur_gross'))})",
        f"Journal exécuteur : {s.get('events') or 'vide'}",
    ]
    if fb.get("n_fills"):
        lignes.append(f"Fills du BOT : {fb['n_fills']} · volume {_n(fb.get('volume_usdt'))} $ · "
                      f"PnL réalisé {_n(fb.get('pnl_realise_usdt'), '{:+.4f}')} $ · "
                      f"frais {_n(fb.get('frais_usdt'), '{:.4f}')} $ · "
                      f"NET {_n(fb.get('net_usdt'), '{:+.4f}')} $")
    else:
        lignes.append(f"Fills du BOT : {fb.get('note', 'aucun')}")
    lignes.append("Lecture seule (préview de décision, jamais d'exécution ici). VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
