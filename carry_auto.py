"""
carry_auto.py — jambes CASH-AND-CARRY automatiques bornées (§45, full live).

Classement : décision seulement — AUCUN ordre en dur ici (délègue tout à
`futures_executor`, comme futures_auto). La stratégie : le BTC SPOT déjà détenu
par l'accumulation (jamais vendu — la politique hold est INTACTE) sert de jambe
longue ; quand le funding paie (carry_monitor : APR net ≥ seuil ATTRACTIF 5 %),
on ouvre un SHORT perp COUVERT par ce spot -> delta ≈ 0, on encaisse le funding
sans pari directionnel. C'est la SEULE famille de rendement mesurée positive
(§35-40). Sortie par hystérésis quand l'APR net retombe sous le seuil de sortie.

Règles de sûreté propres au carry :
  • le short est TOUJOURS ≤ la couverture spot (delta-neutre par construction,
    marge de 5 % pour les frais/poussières) — couverture insuffisante -> rien ;
  • levier ×1, PAS de SL/TP : la jambe est HEDGÉE par le spot (un SL casserait
    la neutralité en laissant le spot nu) ;
  • propriété de position (futures_auto.proprietaire_position) : le carry ne
    touche QUE ses propres shorts ; position d'un autre agent -> rien ;
  • relevé carry PÉRIMÉ (> 2 h) ou illisible -> rien (fail-closed à l'entrée) ;
    en POSITION, un relevé illisible ne force PAS la sortie (position hedgée,
    fermer à l'aveugle serait le vrai risque) ;
  • au plus un ordre carry toutes FUTURES_CARRY_MIN_INTERVAL_H heures (8 h =
    la période de funding : inutile d'agir plus vite).

Débrayage : FUTURES_AUTO_CARRY=0, ou KILL_SWITCH (gardes exécuteur).
CLI : python carry_auto.py [--status]
"""

import time

from config_utils import cfg as _cfg
from numeric_utils import safe_float

SYMBOL = "BTCUSDT"
MARGE_COUVERTURE = 0.95      # le short n'utilise que 95 % de la couverture spot


# ---------- cœurs purs (testables) ----------

def decider_carry(apr_net, attrait, position, owner, couverture_usdt,
                  seuil_sortie_pct=None, notional_cfg=None, min_notional=6.0,
                  tranche_max=None):
    """PUR. Décision carry (cible construite PAR TRANCHES depuis le cap 200, décision
    propriétaire 03/07 — un ordre reste ≤ tranche_max = cap/trade de l'exécuteur) :
      • FLAT : attrait ATTRACTIF ET couverture suffisante -> OUVRIR une tranche de
        min(cible, tranche_max) où cible = min(notional_cfg, 95 % couverture) ;
      • POSITION à nous (short) : APR < seuil de sortie -> FERMER (en un ordre,
        reduceOnly exempté des caps) ; attrait encore ATTRACTIF et position < cible
        -> RENFORCER d'une tranche (throttle 8 h entre tranches) ; APR entre sortie
        et entrée -> TENIR (on encaisse, pas de rajout) ; APR illisible -> TENIR ;
      • position d'un AUTRE agent ou d'un autre sens -> RIEN (pas à nous).
    Retourne {"action", "side", "notional", "raison"}."""
    sortie = float(_cfg("FUTURES_CARRY_SEUIL_SORTIE_PCT", 2.0)
                   if seuil_sortie_pct is None else seuil_sortie_pct)
    apr = safe_float(apr_net)
    plafond = float(_cfg("FUTURES_CARRY_NOTIONAL_USDT", 15.0)
                    if notional_cfg is None else notional_cfg)
    couverture = safe_float(couverture_usdt)
    cible = min(plafond, (couverture or 0.0) * MARGE_COUVERTURE)
    tranche_cap = safe_float(tranche_max)
    if position:
        if owner != "carry":
            return {"action": "rien", "side": None, "notional": None,
                    "raison": f"position détenue par '{owner}' — pas à nous"}
        if str(position.get("side")) != "short":
            return {"action": "rien", "side": None, "notional": None,
                    "raison": "position carry attendue SHORT — anomalie, on ne touche pas"}
        if apr is None:
            return {"action": "rien", "side": "short", "notional": None,
                    "raison": "APR illisible — position hedgée, on tient (pas de sortie aveugle)"}
        if apr < sortie:
            return {"action": "fermer", "side": "short",
                    "notional": position.get("notional_usdt"),
                    "raison": f"APR net {apr:+.2f} % < seuil de sortie {sortie} % — le carry ne paie plus"}
        deja = safe_float(position.get("notional_usdt")) or 0.0
        manque = cible - deja
        if str(attrait) == "ATTRACTIF" and couverture is not None and manque >= float(min_notional):
            tranche = min(manque, tranche_cap) if tranche_cap else manque
            if tranche >= float(min_notional):
                return {"action": "renforcer", "side": "short", "notional": round(tranche, 2),
                        "raison": f"carry ATTRACTIF (APR {apr:+.2f} %) — tranche vers la cible "
                                  f"{cible:.0f} $ ({deja:.0f} $ en place)"}
        return {"action": "rien", "side": "short", "notional": None,
                "raison": f"carry en place ({deja:.0f} $), APR net {apr:+.2f} % — on encaisse"}
    # flat
    if str(attrait) != "ATTRACTIF":
        return {"action": "rien", "side": None, "notional": None,
                "raison": f"carry {attrait or 'illisible'} — pas d'entrée"}
    if couverture is None:
        return {"action": "rien", "side": None, "notional": None,
                "raison": "couverture spot illisible (fail-closed à l'entrée)"}
    notional = min(cible, tranche_cap) if tranche_cap else cible
    if notional < float(min_notional):
        return {"action": "rien", "side": None, "notional": None,
                "raison": f"couverture spot insuffisante ({couverture:.2f} $ détenus, "
                          f"short possible {notional:.2f} $ < min {min_notional} $)"}
    return {"action": "ouvrir", "side": "short", "notional": round(notional, 2),
            "raison": f"carry ATTRACTIF (APR net {apr:+.2f} %) couvert par le spot — "
                      f"1re tranche vers la cible {cible:.0f} $"}


def releve_carry(journal_entry, max_age_s=7200, now=None):
    """PUR. (apr_net, attrait) du relevé BTCUSDT journalisé par carry_monitor,
    (None, None) si absent ou PÉRIMÉ (> max_age_s)."""
    now = time.time() if now is None else now
    e = journal_entry or {}
    ts = safe_float(e.get("ts"))
    if ts is None or now - ts > max_age_s:
        return None, None
    for r in e.get("resultats") or []:
        if isinstance(r, dict) and str(r.get("symbol", "")).upper() == SYMBOL:
            return safe_float(r.get("apr_net_pct")), r.get("attrait")
    return None, None


# ---------- lectures (best-effort, lecture seule) ----------

def _releve():
    try:
        import json as _json
        import carry_monitor as cm
        journal = _json.loads(cm.JOURNAL_FILE.read_text(encoding="utf-8"))
        return journal[-1] if journal else None
    except Exception:
        return None


# Tokens du portefeuille comptant comme COUVERTURE BTC de la jambe carry, avec
# leur décote : BTC natif plein, BGBTC (wrapper Bitget, suit le BTC 1:1) décoté
# 10 % par prudence (risque wrapper/dé-peg + friction de conversion). Audit
# portefeuille 03/07 : l'exposition BTC réelle du propriétaire est ~206 $
# (BTC 31 $ + BGBTC 175 $) — la couverture n'en comptait que 31.
COUVERTURE_TOKENS = {"BTC": 1.0, "BGBTC": 0.9}


def couverture_spot_usdt():
    """Valeur USDT de l'exposition BTC SPOT détenue (BTC + wrappers décotés) — la
    jambe longue déjà en portefeuille. None si illisible (fail-closed à l'entrée)."""
    try:
        import bitget_balance_reader as br
        import futures_executor as fe
        tokens = dict(_cfg("CARRY_COUVERTURE_TOKENS", COUVERTURE_TOKENS))
        quantite = 0.0
        vu = False
        for r in (br.get_spot_assets() or {}).get("data") or []:
            coin = str(r.get("coin", "")).upper()
            if coin in tokens:
                vu = True
                total = (safe_float(r.get("available")) or 0.0) + (safe_float(r.get("frozen")) or 0.0)
                quantite += total * float(tokens[coin])   # décote du wrapper appliquée
        if not vu:
            return None
        prix = fe._mark_price()
        return quantite * prix if prix else None
    except Exception:
        return None


# ---------- cycle ----------

def _etat(now=None):
    """Lectures communes run/status. Retourne (out, decision) sans exécuter."""
    import futures_auto as fa
    now = time.time() if now is None else now
    out = {"ts": int(now), "armed": bool(int(_cfg("FUTURES_AUTO_CARRY", 1) or 0))}
    if not out["armed"]:
        return out, {"action": "rien", "raison": "FUTURES_AUTO_CARRY=0 (débrayé)"}
    apr, attrait = releve_carry(_releve(), now=now)
    out["apr_net_pct"], out["attrait"] = apr, attrait
    # mode hedge (03/07) : le carry ne regarde que le côté SHORT — il peut coexister
    # avec un long directionnel. En one-way transitoire, l'ouverture est refusée si
    # un long d'un autre agent existe (netting interdit).
    cotes = fa.positions_cotes()
    if cotes.get("erreur"):
        return out, {"action": "rien", "raison": cotes["erreur"] + " (fail-closed)"}
    events = fa._executor_events()
    pos = cotes.get("short")
    out["position"] = pos
    out["cotes"] = {k: (v or {}).get("notional_usdt") for k, v in cotes.items()
                    if k in ("long", "short")}
    owner = fa.proprietaire_cote(events, "short") if pos else None
    out["owner"] = owner
    if not pos and cotes.get("long"):
        import futures_executor as fe
        mode = fe.resolve_pos_mode(fe.positions_ouvertes(),
                                   _cfg("FUTURES_POSITION_MODE", "hedge_mode"))
        if mode == "one_way_mode":
            return out, {"action": "rien", "side": None, "notional": None,
                         "raison": "compte encore en one-way avec un long ouvert — "
                                   "netting interdit, le carry attend le hedge"}
    couverture = couverture_spot_usdt()           # aussi EN position (cible des tranches)
    out["couverture_usdt"] = round(couverture, 2) if couverture is not None else None
    import futures_executor as fe
    tranche_max = fe._capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0,
                             fe.FUT_ABS_MAX_PER_TRADE_USDT)
    d = decider_carry(apr, attrait, pos, owner, couverture, tranche_max=tranche_max)
    return out, d


def status(now=None):
    """Préview STRICTEMENT LECTURE SEULE (jamais d'exécution)."""
    out, d = _etat(now)
    out["consultation"] = True
    out["decision"] = d
    return out


def run(now=None):
    """Un cycle carry (journalisé dans le même JSONL que la boucle directionnelle)."""
    out = _run_cycle(now)
    try:
        import futures_auto as fa
        fa._journal_decision({**out, "boucle": "carry"})
    except Exception:
        pass
    return out


def _run_cycle(now=None):
    """Le cycle lui-même. N'exécute que si armé, décision non-rien, throttle écoulé."""
    import futures_auto as fa
    now = time.time() if now is None else now
    out, d = _etat(now)
    out["decision"] = d
    if d["action"] == "rien":
        return out
    min_h = float(_cfg("FUTURES_CARRY_MIN_INTERVAL_H", 8.0))
    if not fa.throttle_ok(fa.dernier_ordre_auto_ts(fa._executor_events(), agent="carry"),
                          now=now, min_h=min_h):
        out["decision"] = {**d, "action": "rien",
                           "raison": d["raison"] + " — throttle carry (intervalle non écoulé)"}
        return out
    import futures_executor as fe
    if d["action"] == "fermer":
        notional = min(float(d.get("notional") or 0),
                       fe._capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0,
                                  fe.FUT_ABS_MAX_PER_TRADE_USDT))
        # taille EXACTE (reduceOnly borne à la position — pas de poussière infermable)
        res = fe.execute("carry", "short", notional, 1.0, reduce=True, confirm=True,
                         now=now, size_btc=(out.get("position") or {}).get("size_btc"))
    else:                                          # ouvrir/renforcer : short couvert, levier 1, sans SL/TP
        res = fe.execute("carry", "short", float(d["notional"]), 1.0,
                         confirm=True, now=now,
                         gross_open_usdt=(out.get("position") or {}).get("notional_usdt") or 0.0,
                         equity_curve=fe.equity_curve())   # halte MDD du mandat (garde 6)
    out["resultat"] = {"executed": bool(res.get("executed")), "ok": res.get("ok"),
                       "reasons": res.get("reasons"), "clientOid": res.get("clientOid")}
    try:
        import telegram_notifier as tn
        if out["resultat"]["executed"]:
            tn.send_telegram(f"⚡ CARRY RÉEL (§45) : {d['action'].upper()} short couvert — "
                             f"{d['raison']}. oid {res.get('clientOid')} · voir /futures")
        else:
            tn.send_telegram(f"⚠️ CARRY : ÉCHEC {d['action']} — "
                             f"{res.get('reasons') or 'réponse exchange'}. "
                             f"Retente après throttle · voir /futures")
    except Exception:
        pass
    return out


def build_report(r=None):
    r = run() if r is None else r
    d = r.get("decision") or {}
    lignes = ["=== JAMBES CASH-AND-CARRY (§45, couvertes par le spot) ==="
              + (" — CONSULTATION" if r.get("consultation") else "")]
    lignes.append(f"Armé : {r.get('armed')} · APR net {r.get('apr_net_pct')} % · "
                  f"attrait {r.get('attrait')} · position {r.get('position') or 'flat'}"
                  + (f" (owner {r.get('owner')})" if r.get("owner") else "")
                  + (f" · couverture spot {r.get('couverture_usdt')} $"
                     if r.get("couverture_usdt") is not None else ""))
    lignes.append(f"Décision : {str(d.get('action', 'rien')).upper()} — {d.get('raison', '')}")
    res = r.get("resultat")
    if res:
        etat = "EXÉCUTÉ" if res.get("executed") else f"refusé/échec ({res.get('reasons')})"
        lignes.append(f"Exécution : {etat} (oid {res.get('clientOid')})")
    lignes.append("Short TOUJOURS ≤ couverture spot (delta-neutre), levier ×1, sans SL "
                  "(hedgé). Toute exécution via futures_executor. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    import sys
    if "--status" in sys.argv[1:]:
        print(build_report(status()))
        return
    print(build_report())


if __name__ == "__main__":
    main()
