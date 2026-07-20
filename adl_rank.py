#!/usr/bin/env python3
"""adl_rank.py — lecteur du RANG ADL (auto-deleveraging) des positions futures. SAFE, lecture seule.

Le rang ADL Bitget (1..5, **5 = deleveragé EN PREMIER**) mesure à quel point une position serait
force-fermée si le fonds d'assurance s'épuisait (cf. docs/BITGET_REFERENCE §8a/8f). C'est un
DESCRIPTEUR de RISQUE (ERR-016 : jugé sur la protection, JAMAIS une IC) — il N'AJOUTE AUCUN MUR et ne
décide RIEN. Le carry du bot est delta-neutre + levier ≤×5 → prior = rang BAS ; ce lecteur le CONFIRME
et alerte si un rang MONTE (ex. jambe nue à fort levier). Endpoint GET /api/v2/mix/position/adlRank
(renvoie [] quand aucune position ouverte). Réduire le rang = baisser le levier / hedger / delta-neutre.

CLI :
    python adl_rank.py            # rang ADL des positions futures (lecture seule)
    python adl_rank.py --alert    # + Telegram si rang élevé (cron), dédupliqué
"""
import json
import os
import sys

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".adl_rank_state.json")


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def fetch(product_type="USDT-FUTURES"):
    """Positions + rang ADL (lecture seule, fail-safe -> []). _signed_get renvoie la data brute
    (liste) ou {data:[...]}."""
    try:
        import fee_rates as fr
        data = fr._signed_get("/api/v2/mix/position/adlRank", {"productType": product_type})
        if isinstance(data, dict):
            data = data.get("data") or []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def parse(rows):
    """[{symbol, holdSide, adlRank*}] -> [{symbol, side, rank}]. PUR, robuste aux noms de champ
    (adlRankLong/adlRankShort par côté, ou adlRank générique + holdSide)."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        sym = r.get("symbol")
        found = False
        for k, v in r.items():
            kl = str(k).lower()
            if kl.startswith("adlrank"):
                rank = _num(v)
                if rank is None:
                    continue
                side = kl[len("adlrank"):] or str(r.get("holdSide") or "?")
                out.append({"symbol": sym, "side": side, "rank": rank})
                found = True
        if not found:
            rank = _num(r.get("adlRank"))
            if rank is not None:
                out.append({"symbol": sym, "side": str(r.get("holdSide") or "?"), "rank": rank})
    return out


def _label(mx):
    """Rang ADL 1..5 (5 = deleveragé EN PREMIER) -> étiquette de risque. PUR."""
    if mx is None:
        return "—"
    return "SÛR" if mx <= 2 else ("SURVEILLER" if mx <= 3 else "RISQUE ADL ÉLEVÉ")


def report():
    """Rang ADL des positions futures courantes. Fail-safe -> note si aucune position."""
    positions = parse(fetch())
    if not positions:
        return {"n": 0, "max_rank": None, "label": "—",
                "note": "aucune position futures ouverte (risque ADL N/A)"}
    ranks = [p["rank"] for p in positions if p.get("rank") is not None]
    mx = max(ranks) if ranks else None
    return {"n": len(positions), "max_rank": mx, "label": _label(mx), "positions": positions}


def _alert(r):
    """Telegram SI un rang ADL >= seuil (ADL_RANK_ALERT, défaut 4/5 = proche du deleveraging).
    Dédupliqué (.adl_rank_state.json), fail-safe. NE DÉCIDE RIEN (baisser le levier/hedger = décision)."""
    mx = r.get("max_rank")
    if mx is None:
        return False
    try:
        from config_utils import cfg as _cfg
        seuil = int(_cfg("ADL_RANK_ALERT", 4))
    except Exception:
        seuil = 4
    breach = mx >= seuil
    try:
        last = json.load(open(STATE, encoding="utf-8")).get("max_rank")
    except Exception:
        last = None
    if breach and mx != last:
        try:
            import telegram_notifier as tn
            det = ", ".join(f"{p['symbol']} {p['side']} r{p['rank']}" for p in r.get("positions", []))
            tn.send_telegram(f"⚠️ RANG ADL ÉLEVÉ ({mx}/5) — {det}\n"
                             f"Baisser le levier / hedger (delta-neutre) pour descendre dans la file ADL.")
        except Exception:
            pass
    try:
        json.dump({"max_rank": mx}, open(STATE, "w"))
    except Exception:
        pass
    return breach


def main():
    r = report()
    alert = "--alert" in sys.argv
    if alert:
        _alert(r)
        print(f"ADL: {r['note']}" if "note" in r
              else f"ADL rank max {r['max_rank']}/5 [{r['label']}] · {r['n']} position(s)")
    else:
        print("=== RANG ADL (auto-deleveraging, lecture seule — n'ajoute aucun mur) ===")
        if "note" in r:
            print(f"  {r['note']}")
        else:
            print(f"  positions : {r['n']} · rang MAX {r['max_rank']}/5 -> {r['label']}")
            for p in r["positions"]:
                print(f"    {p['symbol']} {p['side']}: rang {p['rank']}/5")
        print("Descripteur seul — baisser le levier/hedger reste LA décision. VERDICT: SAFE")


if __name__ == "__main__":
    main()
