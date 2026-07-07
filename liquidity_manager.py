"""
liquidity_manager.py — gestion AUTONOME BORNÉE de la liquidité entre outils Bitget (§76).

Classement : module de DÉCISION. Il ne parle JAMAIS à l'API en écriture : toute
exécution est DÉLÉGUÉE aux exécuteurs de surface §67 audités à part —
`account_transfers` (virements INTERNES spot<->futures) et `earn_manager`
(souscription/rachat Earn USDT flexible) — qui portent TOUTES les gardes :
verrous LIVE (TRANSFER_LIVE/EARN_LIVE), kill-switch fail-closed, caps durs
par opération ET par jour (§67 : 25 $/op · 100 $/j par surface), DRY par défaut.
Le RETRAIT externe est interdit par conception partout (clé Trade-only).

Politique (décision propriétaire du 06/07/2026 — « automatise la gestion totale ») :
  UNE action par cycle, la plus urgente d'abord, montants bornés [5 $, cap/op] :
    1. marge futures sous le plancher  -> virement spot -> futures (si le spot
       garde son propre plancher), sinon rachat Earn -> spot (le virement suit
       au cycle suivant : jamais deux mouvements dans le même cycle) ;
    2. float spot sous le plancher     -> rachat Earn -> spot (le DCA quotidien
       et la garde premium ont besoin de cash) ;
    3. float spot au-dessus du plafond -> souscription Earn du surplus
       (l'argent ne dort pas sans rendement) ;
    4. sinon                           -> rien.
  Gate maître : LIQUIDITY_AUTO (défaut OFF -> DRY : décision journalisée, aucun
  mouvement). Soldes illisibles -> rien (fail-closed). Chaque action est
  journalisée (.liquidity_journal.jsonl) et notifiée Telegram (best-effort).

CLI :
    python liquidity_manager.py --status    # lecture seule : soldes + décision PRÉVUE
    python liquidity_manager.py --cycle     # un cycle (n'agit que si LIQUIDITY_AUTO=1)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from config_utils import cfg as _cfg
from numeric_utils import safe_float

JOURNAL = Path(__file__).resolve().parent / ".liquidity_journal.jsonl"
MIN_MOVE_USDT = 5.0               # pas de micro-mouvements (frais d'attention > gain)


def enabled():
    """Gate maître (défaut OFF). Armable via env LIQUIDITY_AUTO=1 OU config."""
    v = os.getenv("LIQUIDITY_AUTO", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("LIQUIDITY_AUTO", False))


def _flt(name, default):
    try:
        return float(os.getenv(name) or _cfg(name, default))
    except (TypeError, ValueError):
        return float(default)


def decider(spot_usdt, fut_usdt, spot_min=None, spot_max=None, fut_min=None, cap_op=25.0,
            margin_usdt=None, margin_min=None):
    """PUR (testable). UNE action de liquidité par cycle — voir la politique du
    module. Renvoie {"action", "usdt", "raison"} ; action ∈ {"transfer_spot_futures",
    "transfer_spot_margin", "redeem", "subscribe", "rien"}. Soldes illisibles -> rien
    (fail-closed ; margin illisible -> on saute juste sa branche, §91)."""
    spot_min = _flt("LIQ_SPOT_MIN_USDT", 15.0) if spot_min is None else float(spot_min)
    spot_max = _flt("LIQ_SPOT_MAX_USDT", 120.0) if spot_max is None else float(spot_max)
    fut_min = _flt("LIQ_FUT_MIN_USDT", 40.0) if fut_min is None else float(fut_min)
    margin_min = _flt("LIQ_MARGIN_MIN_USDT", 25.0) if margin_min is None else float(margin_min)
    spot, fut = safe_float(spot_usdt), safe_float(fut_usdt)
    margin = safe_float(margin_usdt)
    if spot is None or fut is None:
        return {"action": "rien", "usdt": 0.0, "raison": "soldes illisibles (fail-closed)"}

    def _clamp(x):
        return round(max(MIN_MOVE_USDT, min(float(cap_op), x)), 2)

    # 1. la marge futures d'abord : c'est elle qui porte les stops/positions réelles
    if fut < fut_min:
        besoin = fut_min - fut
        if besoin >= MIN_MOVE_USDT:
            if spot - _clamp(besoin) >= spot_min:
                return {"action": "transfer_spot_futures", "usdt": _clamp(besoin),
                        "raison": f"marge futures {fut:.2f} < plancher {fut_min:.0f}"}
            return {"action": "redeem", "usdt": _clamp(besoin + max(0.0, spot_min - spot)),
                    "raison": (f"marge futures {fut:.2f} < plancher {fut_min:.0f} et spot "
                               f"{spot:.2f} trop juste — rachat Earn d'abord, virement au cycle suivant")}
    # 1bis. le collatéral marge croisée (§91, mandat propriétaire 07/07 : « alimente
    # le compte marge pour pouvoir emprunter ») : sans float USDT en marge, la jambe
    # reverse de l'alt-carry n'a pas de capacité d'emprunt.
    if margin is not None and margin < margin_min:
        besoin = margin_min - margin
        if besoin >= MIN_MOVE_USDT:
            if spot - _clamp(besoin) >= spot_min:
                return {"action": "transfer_spot_margin", "usdt": _clamp(besoin),
                        "raison": f"collatéral marge {margin:.2f} < plancher {margin_min:.0f}"}
            return {"action": "redeem", "usdt": _clamp(besoin + max(0.0, spot_min - spot)),
                    "raison": (f"collatéral marge {margin:.2f} < plancher {margin_min:.0f} et "
                               f"spot {spot:.2f} trop juste — rachat Earn d'abord")}
    # 2. le float spot ensuite : le DCA quotidien a besoin de cash
    if spot < spot_min:
        besoin = spot_min - spot + MIN_MOVE_USDT
        if besoin >= MIN_MOVE_USDT:
            return {"action": "redeem", "usdt": _clamp(besoin),
                    "raison": f"float spot {spot:.2f} < plancher {spot_min:.0f}"}
    # 3. le surplus dort -> Earn
    if spot > spot_max:
        surplus = spot - spot_max
        if surplus >= MIN_MOVE_USDT:
            return {"action": "subscribe", "usdt": _clamp(surplus),
                    "raison": f"float spot {spot:.2f} > plafond {spot_max:.0f} — le surplus va au rendement"}
    return {"action": "rien", "usdt": 0.0,
            "raison": f"équilibré (spot {spot:.2f} ∈ [{spot_min:.0f},{spot_max:.0f}], "
                      f"futures {fut:.2f} ≥ {fut_min:.0f})"}


# ---------- lectures de soldes (best-effort, lecture seule) ----------

def _spot_usdt():
    try:
        import bitget_balance_reader as br
        for row in (br.get_spot_assets("USDT") or {}).get("data") or []:
            if str(row.get("coin", "")).upper() == "USDT":
                return safe_float(row.get("available"))
        return None
    except Exception:
        return None


def _futures_usdt():
    try:
        import bitget_balance_reader as br
        for row in (br.get_futures_accounts() or {}).get("data") or []:
            if str(row.get("marginCoin", "")).upper() == "USDT":
                return safe_float(row.get("available") or row.get("crossedMaxAvailable"))
        return None
    except Exception:
        return None


def _produit_earn_usdt():
    """Premier produit Earn USDT FLEXIBLE (rachat à tout moment). None best-effort."""
    try:
        import earn_manager as em
        for p in em.products("USDT") or []:
            if str(p.get("periodType", "")).lower() in ("flexible", "flex", ""):
                pid = p.get("productId") or p.get("id")
                if pid:
                    return str(pid)
        return None
    except Exception:
        return None


def _journalise(entree):
    try:
        with JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _notifie(msg):
    try:
        import telegram_notifier as tn
        tn.send_telegram(msg)
    except Exception:
        pass


def _marge_usdt():
    """USDT disponible en marge CROISÉE (lecture seule). None si illisible."""
    try:
        import bitget_hub_bridge as hub
        d = hub._read(["margin", "margin_get_assets", "--marginType", "crossed"])
        for r in (d or {}).get("data") or []:
            if str(r.get("coin", "")).upper() == "USDT":
                return float(r.get("available") or 0)
        return 0.0
    except Exception:
        return None


def cycle(now=None, confirm=None):
    """Un cycle de gestion de liquidité. N'AGIT (confirm=True vers les exécuteurs §67)
    que si LIQUIDITY_AUTO est armé — sinon DRY (décision journalisée, aucun mouvement).
    Les exécuteurs re-vérifient TOUT (verrous LIVE, kill-switch, caps/op, caps/jour)."""
    now = time.time() if now is None else now
    spot, fut, marge = _spot_usdt(), _futures_usdt(), _marge_usdt()
    d = decider(spot, fut, margin_usdt=marge)
    arme = enabled() if confirm is None else bool(confirm)
    out = {"ts": int(now), "spot_usdt": spot, "fut_usdt": fut, "margin_usdt": marge,
           "decision": d, "armed": arme, "executed": False}
    if d["action"] == "rien":
        _journalise(out)
        return out
    res = None
    if d["action"] == "transfer_spot_futures":
        import account_transfers as at
        res = at.execute("spot", "usdt_futures", "USDT", d["usdt"], confirm=arme)
    elif d["action"] == "transfer_spot_margin":
        import account_transfers as at
        res = at.execute("spot", "crossed_margin", "USDT", d["usdt"], confirm=arme)
    elif d["action"] in ("redeem", "subscribe"):
        pid = _produit_earn_usdt()
        if not pid:
            out["decision"] = {**d, "raison": d["raison"] + " — produit Earn USDT flexible introuvable, rien"}
            _journalise(out)
            return out
        import earn_manager as em
        res = em.execute(d["action"], pid, "USDT", d["usdt"], confirm=arme)
    out["resultat"] = {k: res.get(k) for k in ("ok", "dry", "executed", "reasons", "clientOid")} if res else None
    out["executed"] = bool(res and res.get("executed"))
    _journalise(out)
    if out["executed"]:
        _notifie(f"💧 Liquidité : {d['action']} {d['usdt']} $ — {d['raison']} "
                 f"(spot {spot} · futures {fut}). Caps §67 et kill-switch respectés.")
    return out


def status():
    """Lecture seule : soldes + décision PRÉVUE (aucun mouvement, aucune écriture)."""
    spot, fut = _spot_usdt(), _futures_usdt()
    return {"spot_usdt": spot, "fut_usdt": fut, "armed": enabled(),
            "decision": decider(spot, fut, margin_usdt=_marge_usdt()), "consultation": True}


def build_report(s=None):
    s = status() if s is None else s
    d = s.get("decision") or {}
    return "\n".join([
        "=== LIQUIDITÉ (gestion autonome bornée §76) — CONSULTATION ===",
        f"Armée : {s.get('armed')} · spot {s.get('spot_usdt')} $ · futures {s.get('fut_usdt')} $",
        f"Décision : {str(d.get('action', 'rien')).upper()} {d.get('usdt') or ''} $ — {d.get('raison', '')}",
        "Décision seule ici — toute exécution passe par account_transfers/earn_manager "
        "(verrous LIVE, kill-switch, caps §67). Jamais de retrait externe. VERDICT: SAFE",
    ])


def main():
    import sys
    try:
        from dotenv import load_dotenv                 # cron/CLI : leviers env visibles
        load_dotenv()
    except Exception:
        pass
    if "--cycle" in sys.argv[1:]:
        r = cycle()
        d = r.get("decision") or {}
        print("=== LIQUIDITÉ — CYCLE ===")
        print(f"spot {r.get('spot_usdt')} $ · futures {r.get('fut_usdt')} $ · armée {r.get('armed')}")
        print(f"Décision : {str(d.get('action', 'rien')).upper()} {d.get('usdt') or ''} $ — {d.get('raison', '')}")
        rr = r.get("resultat") or {}
        if r.get("executed"):
            print(f"✅ EXÉCUTÉ ({rr.get('clientOid')})")
        elif rr:
            print(("DRY — aucun mouvement." if rr.get("dry") else
                   "REFUSÉ/échec : " + str(rr.get("reasons") or "")))
        print("VERDICT: SAFE")
    else:
        print(build_report())


if __name__ == "__main__":
    main()
