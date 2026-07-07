"""
trade_forensics.py — analyse LECTURE SEULE des exécutions RÉELLES (§88).

Trois instruments sur les fills réels du compte (aucun ordre, aucun état modifié) :
  1. ROUND-TRIPS + MFE/MAE : reconstruit chaque aller-retour réel (ouverture par
     événement exécuteur, fermetures pilotées par les FILLS — les sorties par SL/TP
     préréglés et TP1 partiels n'émettent PAS d'événement), puis mesure sur bougies
     l'excursion favorable (MFE) et adverse (MAE) maximales pendant la vie du trade —
     en % et en R (distance au SL préréglé). C'est l'instrument qui juge la politique
     de sortie (RR 1.5, TP1 1R/50 %) sur NOS données, pas sur du papier.
  2. QUALITÉ D'EXÉCUTION : slippage réalisé = VWAP des fills d'ouverture vs clôture
     de la bougie 1 min de la décision (référence indépendante de l'ordre).
  3. ATTRIBUTION PAR MÉTHODE : PnL net (profits − frais) par agent (auto_dir, carry,
     alt_carry, …) — fondation du Kelly par méthode.

Appariement : les fills Bitget n'exposent PAS le clientOid -> on apparie par
(symbole, côté d'exécution, fenêtre temporelle) et on groupe par orderId.
Convention hedge-mode : ouvrir long = buy/open · fermer long = sell/close ·
ouvrir short = sell/open · fermer short = buy/close.

CLI : python trade_forensics.py [heures]   (défaut 168 = 7 j) — rapport lecture seule.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# ---------- chargement (lecture seule) ----------

def charger_events(depuis_ts=0):
    """Événements FUTURES_REAL du ledger (ouvertures ET réductions du bot)."""
    try:
        led = json.loads((ROOT / "futures_real_ledger.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for e in led.get("events", []):
        if e.get("action") != "FUTURES_REAL" or float(e.get("ts") or 0) < depuis_ts:
            continue
        o = e.get("order") or {}
        bo = e.get("bitget_order") or {}
        sl = None
        try:
            sl = float(bo.get("presetStopLossPrice")) if bo.get("presetStopLossPrice") else None
        except (TypeError, ValueError):
            sl = None
        out.append({"ts": float(e.get("ts") or 0), "symbol": str(o.get("symbol") or "").upper(),
                    "side": o.get("side"), "reduce": bool(o.get("reduce")),
                    "agent": o.get("agent") or "?", "notional": o.get("notional_usdt"),
                    "size_btc": o.get("size_btc"), "sl": sl})
    return sorted(out, key=lambda e: e["ts"])


def charger_fills(limit=200):
    """Fills réels normalisés (ts s, floats), plus anciens d'abord."""
    import futures_report as fr
    rows = fr.fetch_fills(limit=limit) or []
    out = []
    for r in rows:
        try:
            fee = sum(abs(float(f.get("totalFee") or 0)) for f in (r.get("feeDetail") or []))
        except Exception:
            fee = 0.0
        try:
            out.append({"ts": float(r.get("cTime") or 0) / 1000.0,
                        "symbol": str(r.get("symbol") or "").upper(),
                        "side": str(r.get("side") or "").lower(),
                        "trade_side": str(r.get("tradeSide") or "").lower(),
                        "price": float(r.get("price") or 0),
                        "base": float(r.get("baseVolume") or 0),
                        "quote": float(r.get("quoteVolume") or 0),
                        "profit": float(r.get("profit") or 0),
                        "fee": fee, "order_id": r.get("orderId"),
                        "scope": r.get("tradeScope")})
        except (TypeError, ValueError):
            continue
    return sorted(out, key=lambda f: f["ts"])


def _cote_exec(side, ouverture):
    """Côté attendu du FILL. Convention Bitget hedge-mode VÉRIFIÉE sur fills réels
    (§88) : `side` = côté de la POSITION (un short s'ouvre ET se ferme en `sell`,
    un long en `buy`) — seul `tradeSide` (open/close) distingue le sens."""
    return ("buy" if str(side) == "long" else "sell", "open" if ouverture else "close")


# ---------- reconstruction des round-trips (PUR sur entrées injectées) ----------

def round_trips(events, fills, tol_s=120):
    """Reconstruit les allers-retours : chaque OUVERTURE (événement reduce=False)
    consomme ses fills d'ouverture (même symbole, buy/open ou sell/open, fenêtre
    ±tol_s, groupés par orderId), puis les fills de FERMETURE suivants (sell/close
    ou buy/close) jusqu'à couvrir ~100 % de la taille — qu'ils viennent d'une
    réduction du bot, d'un SL/TP préréglé ou d'un TP1 partiel (pas d'événement).
    PUR. Retourne les trips clos ET la position résiduelle éventuelle."""
    fills = sorted(fills, key=lambda f: f["ts"])
    pris = set()
    trips, ouverts = [], []
    for ev in [e for e in events if not e["reduce"]]:
        side_x, tside = _cote_exec(ev["side"], True)
        ouverture = [f for i, f in enumerate(fills)
                     if id(f) not in pris and f["symbol"] == ev["symbol"]
                     and f["side"] == side_x and f["trade_side"] == tside
                     and abs(f["ts"] - ev["ts"]) <= tol_s]
        if not ouverture:
            continue
        for f in ouverture:
            pris.add(id(f))
        base = sum(f["base"] for f in ouverture)
        vwap_in = sum(f["price"] * f["base"] for f in ouverture) / max(base, 1e-12)
        ouverts.append({"ev": ev, "base": base, "vwap_in": vwap_in,
                        "fees": sum(f["fee"] for f in ouverture),
                        "fills_in": ouverture, "sorties": []})
    # fermetures : chaque fill close nourrit le trip ouvert le plus ancien du symbole/côté
    for f in fills:
        if id(f) in pris:
            continue
        for t in ouverts:
            if t.get("clos"):
                continue
            side_x, tside = _cote_exec(t["ev"]["side"], False)
            if (f["symbol"] == t["ev"]["symbol"] and f["side"] == side_x
                    and f["trade_side"] == tside and f["ts"] >= t["ev"]["ts"]):
                t["sorties"].append(f)
                pris.add(id(f))
                if sum(x["base"] for x in t["sorties"]) >= t["base"] * 0.98:
                    t["clos"] = True
                break
    for t in ouverts:
        sorties = t["sorties"]
        if not sorties:
            continue
        base_out = sum(f["base"] for f in sorties)
        vwap_out = sum(f["price"] * f["base"] for f in sorties) / max(base_out, 1e-12)
        pnl = sum(f["profit"] for f in sorties) - t["fees"] - sum(f["fee"] for f in sorties)
        ev = t["ev"]
        long_ = ev["side"] == "long"
        ret_pct = ((vwap_out / t["vwap_in"]) - 1.0) * (100.0 if long_ else -100.0)
        r_dist = abs(t["vwap_in"] - ev["sl"]) if ev.get("sl") else None
        trips.append({"symbol": ev["symbol"], "side": ev["side"], "agent": ev["agent"],
                      "ts_in": ev["ts"], "ts_out": max(f["ts"] for f in sorties),
                      "duree_min": round((max(f["ts"] for f in sorties) - ev["ts"]) / 60.0, 1),
                      "entry": round(t["vwap_in"], 6), "exit": round(vwap_out, 6),
                      "base": t["base"], "clos": bool(t.get("clos")),
                      "partiel": len({f.get("order_id") for f in sorties}) > 1,
                      "pnl_usdt": round(pnl, 4), "ret_pct": round(ret_pct, 3),
                      "sl": ev.get("sl"),
                      "r_realise": round((ret_pct / 100.0) * t["vwap_in"] / r_dist, 2)
                                   if r_dist else None})
    return {"trips": trips, "ouverts": [t for t in ouverts if not t.get("clos") and not t["sorties"]]}


def mfe_mae(trip, candles=None):
    """MFE/MAE d'un trip sur bougies (granularité adaptée à la durée). En % du prix
    d'entrée, et en R si le SL préréglé est connu. Best-effort (None si bougies
    indisponibles)."""
    try:
        if candles is None:
            import technicals as tk
            # la granularité se choisit par l'ÂGE du trip (il faut REMONTER jusqu'à
            # lui — fetch_candles rend les N dernières bougies), pas par sa durée
            age_s = max(60.0, time.time() - trip["ts_in"])
            gran, step = ("1m", 60) if age_s <= 55000 else (("5m", 300) if age_s <= 280000 else ("15m", 900))
            n = min(1000, int(age_s / step) + 10)
            candles = tk.fetch_candles(trip["symbol"], gran, n) or []
        fen = [c for c in candles
               if trip["ts_in"] <= (float(c.get("ts", 0)) / (1000.0 if float(c.get("ts", 0)) > 1e12 else 1.0)) <= trip["ts_out"] + 60]
        if not fen:
            return None
        hi = max(float(c["high"]) for c in fen)
        lo = min(float(c["low"]) for c in fen)
        e = trip["entry"]
        long_ = trip["side"] == "long"
        mfe_pct = ((hi / e) - 1.0) * 100.0 if long_ else ((e / lo) - 1.0) * 100.0
        mae_pct = ((e / lo) - 1.0) * -100.0 if long_ else ((hi / e) - 1.0) * -100.0
        out = {"mfe_pct": round(mfe_pct, 3), "mae_pct": round(mae_pct, 3)}
        if trip.get("sl"):
            r = abs(e - trip["sl"]) / e * 100.0
            if r > 0:
                out["mfe_r"] = round(mfe_pct / r, 2)
                out["mae_r"] = round(mae_pct / r, 2)
                out["exit_eff"] = round(trip["ret_pct"] / mfe_pct, 2) if mfe_pct > 0.02 else None
        return out
    except Exception:
        return None


# ---------- qualité d'exécution (§88.4) ----------

def slippage(trips_ou_events, fills=None, refs=None):
    """Slippage réalisé des OUVERTURES : VWAP des fills vs clôture de la bougie 1 min
    de la décision (référence indépendante). En points de base, signe = coût (positif
    = payé plus cher que la référence, dans le sens du trade). PUR si refs injecté
    ({(symbol, minute): close})."""
    out = []
    for t in trips_ou_events:
        try:
            minute = int(t["ts_in"] // 60) * 60
            ref = (refs or {}).get((t["symbol"], minute))
            if ref is None and refs is None:
                import technicals as tk
                cand = tk.fetch_candles(t["symbol"], "1m", 600) or []
                par_min = {}
                for c in cand:
                    ts = float(c.get("ts", 0))
                    ts = ts / 1000.0 if ts > 1e12 else ts
                    par_min[int(ts // 60) * 60] = float(c["close"])
                ref = par_min.get(minute) or par_min.get(minute - 60)
            if not ref:
                continue
            signe = 1.0 if t["side"] == "long" else -1.0
            bps = (t["entry"] - ref) / ref * 10000.0 * signe
            out.append({"symbol": t["symbol"], "side": t["side"], "bps": round(bps, 1)})
        except Exception:
            continue
    return out


# ---------- attribution par méthode (§88.5) ----------

def attribution(trips):
    """PnL net et statistiques PAR AGENT (méthode). PUR."""
    par = {}
    for t in trips:
        a = par.setdefault(t.get("agent") or "?", {"n": 0, "pnl": 0.0, "gagnes": 0,
                                                   "duree_min": []})
        a["n"] += 1
        a["pnl"] += t.get("pnl_usdt") or 0.0
        a["gagnes"] += 1 if (t.get("pnl_usdt") or 0) > 0 else 0
        a["duree_min"].append(t.get("duree_min") or 0)
    for k, a in par.items():
        a["pnl"] = round(a["pnl"], 4)
        a["win_rate"] = round(a["gagnes"] / a["n"], 3) if a["n"] else None
        a["duree_mediane_min"] = round(sorted(a["duree_min"])[len(a["duree_min"]) // 2], 1) \
            if a["duree_min"] else None
        del a["duree_min"]
    return par


# ---------- vue d'ensemble ----------

def snapshot(heures=168):
    """Instantané complet : trips + MFE/MAE + slippage + attribution. Lecture seule."""
    depuis = time.time() - heures * 3600
    events = charger_events(depuis)
    fills = [f for f in charger_fills(200) if f["ts"] >= depuis - 3600]
    rt = round_trips(events, fills)
    trips = rt["trips"]
    # ordres acceptés mais JAMAIS remplis (IOC 0 fill) : l'ouverture n'a pas eu lieu
    apparies = {(t["symbol"], t["ts_in"]) for t in trips}
    apparies |= {(o["ev"]["symbol"], o["ev"]["ts"]) for o in rt["ouverts"]}
    non_remplis = [{"symbol": e["symbol"], "ts": e["ts"], "side": e["side"]}
                   for e in events if not e["reduce"]
                   and (e["symbol"], e["ts"]) not in apparies]
    for t in trips:
        t["excursion"] = mfe_mae(t)
    slip = slippage(trips)
    return {"heures": heures, "n_events": len(events), "n_fills": len(fills),
            "trips": trips, "encore_ouverts": len(rt["ouverts"]),
            "non_remplis": non_remplis,
            "slippage": slip,
            "slippage_median_bps": (sorted(s["bps"] for s in slip)[len(slip) // 2]
                                    if slip else None),
            "attribution": attribution(trips)}


def build_report(s=None, heures=168):
    s = snapshot(heures) if s is None else s
    L = [f"=== FORENSIQUE DES TRADES RÉELS (§88, {s['heures']} h, lecture seule) ===",
         f"événements {s['n_events']} · fills {s['n_fills']} · round-trips {len(s['trips'])}"
         f" · encore ouverts {s['encore_ouverts']}"
         + (f" · ⚠️ NON REMPLIS {len(s['non_remplis'])} (IOC accepté, 0 fill)"
            if s.get("non_remplis") else "")]
    for t in s["trips"]:
        ex = t.get("excursion") or {}
        L.append(f"  {t['symbol']:9s} {t['side']:5s} {t['agent']:9s} {t['duree_min']:7.1f} min"
                 f" · PnL {t['pnl_usdt']:+7.4f} $ ({t['ret_pct']:+.2f} %)"
                 + (f" · R {t['r_realise']:+.2f}" if t.get("r_realise") is not None else "")
                 + (f" · MFE {ex.get('mfe_r'):+.2f}R/MAE {ex.get('mae_r'):+.2f}R"
                    if ex.get("mfe_r") is not None else
                    (f" · MFE {ex.get('mfe_pct'):+.2f}%/MAE {ex.get('mae_pct'):+.2f}%"
                     if ex.get("mfe_pct") is not None else ""))
                 + (" · sortie PARTIELLE" if t.get("partiel") else ""))
    if s.get("slippage_median_bps") is not None:
        L.append(f"slippage médian à l'ouverture : {s['slippage_median_bps']:+.1f} bps"
                 " (négatif = MIEUX que la référence 1 min)")
    L.append("— attribution par méthode —")
    for k, a in sorted((s.get("attribution") or {}).items()):
        L.append(f"  {k:10s} n={a['n']:3d} · PnL {a['pnl']:+8.4f} $ · win {a['win_rate']}"
                 f" · durée méd. {a['duree_mediane_min']} min")
    L.append("Aucun ordre. Lecture seule. VERDICT: SAFE")
    return "\n".join(L)


def main():
    import sys
    heures = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 168
    print(build_report(heures=heures))


if __name__ == "__main__":
    main()
