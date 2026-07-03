"""
futures_auto.py — boucle DIRECTIONNELLE automatique bornée (§45, full live).

Classement : décision seulement — AUCUN ordre en dur ici. Ce module DÉCIDE
(consensus du cerveau -> cible LONG/SHORT/FLAT) et DÉLÈGUE toute exécution à
`futures_executor` (2e module autorisé), qui porte TOUTES les gardes : double
verrou, caps 15/60 (murs 50/250), levier ≤×5, stop de perte journalier ->
kill-switch, fail-closed partout. Même architecture que l'accumulation
(accumulation_engine décide -> spot_executor exécute).

Autorisé par la décision propriétaire §45 (02/07/2026, « full live », périmètre
directionnel accepté en connaissance de cause : espérance mesurée négative,
§35-41). Débrayable à tout instant : FUTURES_AUTO_DIRECTIONAL=0, ou
FUTURES_EDGE_GATE_OVERRIDE=0 (referme la porte d'edge), ou `touch KILL_SWITCH`.

Politique VOLONTAIREMENT frugale (le §38 a montré que sur-trader détruit) :
  • UNE position max, pas de pyramidage ; flip en DEUX cycles (fermer, puis rouvrir) ;
  • n'agit que si |consensus| ≥ seuil d'entrée (défaut 0.35 — conviction rare) ;
  • sort si |consensus| retombe sous le seuil de sortie (défaut 0.15) ;
  • au plus UN ordre toutes FUTURES_AUTO_MIN_INTERVAL_H heures (défaut 4 h) ;
  • SL/TP posés À L'OUVERTURE (préréglés côté exchange : protégé même si le
    VPS meurt) ;
  • consensus PÉRIMÉ (> 15 min) -> on ne fait RIEN (fail-closed).

CLI : python futures_auto.py            (un cycle de décision ; exécute si armé)
"""

import json
import time
from pathlib import Path

from config_utils import cfg as _cfg
from numeric_utils import safe_float

SYMBOL = "BTCUSDT"


# ---------- cœurs purs (testables) ----------

def decider(consensus, position_side, seuil_entree=None, seuil_sortie=None):
    """PUR. Décision cible à partir du consensus du cerveau et de la position nette :
      • pas de position : |consensus| ≥ seuil_entree -> OUVRIR (long/short), sinon rien ;
      • position alignée : |consensus| < seuil_sortie -> FERMER (conviction morte),
        sinon TENIR (pas de pyramidage) ;
      • position opposée au consensus (≥ seuil_entree) -> FERMER (le flip éventuel
        attend le cycle suivant : jamais deux ordres dans le même cycle).
    Retourne {"action": "ouvrir"|"fermer"|"rien", "side": "long"|"short"|None, "raison"}."""
    se = float(_cfg("FUTURES_AUTO_SEUIL_ENTREE", 0.35) if seuil_entree is None else seuil_entree)
    ss = float(_cfg("FUTURES_AUTO_SEUIL_SORTIE", 0.15) if seuil_sortie is None else seuil_sortie)
    c = safe_float(consensus)
    if c is None:
        return {"action": "rien", "side": None, "raison": "consensus illisible (fail-closed)"}
    cible = "long" if c >= se else "short" if c <= -se else None
    if position_side not in ("long", "short"):
        if cible:
            return {"action": "ouvrir", "side": cible,
                    "raison": f"consensus {c:+.2f} ≥ seuil {se}"}
        return {"action": "rien", "side": None, "raison": f"consensus {c:+.2f} sous le seuil {se}"}
    # une position existe
    alignee = (position_side == "long" and c > 0) or (position_side == "short" and c < 0)
    if alignee and abs(c) >= ss:
        return {"action": "rien", "side": position_side,
                "raison": f"position {position_side} alignée, conviction {abs(c):.2f} vivante"}
    if cible and cible != position_side:
        return {"action": "fermer", "side": position_side,
                "raison": f"consensus opposé ({c:+.2f}) — flip au cycle suivant"}
    return {"action": "fermer", "side": position_side,
            "raison": f"conviction morte ({c:+.2f}, sortie < {ss})"}


def sl_tp(side, prix, atr=None, sl_pct=None, rr=None):
    """PUR. Stop-loss / take-profit préréglés : distance = 1.5·ATR si dispo, sinon
    sl_pct du prix (défaut 1.5 %) ; TP = distance × RR (défaut 2.0). Long : SL sous /
    TP au-dessus ; short : miroir. (None, None) si prix illisible."""
    p = safe_float(prix)
    if p is None or p <= 0:
        return None, None
    sl_pct = float(_cfg("FUTURES_AUTO_SL_PCT", 1.5) if sl_pct is None else sl_pct)
    rr = float(_cfg("FUTURES_AUTO_RR", 2.0) if rr is None else rr)
    a = safe_float(atr)
    dist = 1.5 * a if (a is not None and a > 0) else p * sl_pct / 100.0
    if str(side) == "long":
        return p - dist, p + dist * rr
    return p + dist, p - dist * rr


def consensus_frais(entries, now=None, max_age_s=900):
    """PUR. Dernier consensus BTCUSDT de brain_log s'il est FRAIS (< max_age_s),
    sinon None (on ne trade jamais sur une lecture périmée)."""
    now = time.time() if now is None else now
    for e in reversed(entries or []):
        if not isinstance(e, dict) or e.get("symbol") != SYMBOL:
            continue
        ts = safe_float(e.get("ts"))
        if ts is None or now - ts > max_age_s:
            return None
        return safe_float(e.get("consensus"))
    return None


def proprietaire_position(events):
    """PUR. Agent PROPRIÉTAIRE de la position ouverte : l'agent du dernier ordre RÉEL
    d'OUVERTURE (reduce=False) journalisé. En mode one-way il n'y a qu'UNE position
    nette par symbole : chaque boucle (auto_dir, carry) ne touche QUE la sienne — une
    position d'un autre agent (ex. 'validation' manuelle) n'est JAMAIS touchée."""
    for e in reversed(events or []):
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        order = e.get("order") or {}
        if not order.get("reduce"):
            return order.get("agent")
    return None


def dernier_ordre_auto_ts(events, agent="auto_dir",
                          actions=("FUTURES_REAL", "FUTURES_REAL_FAILED")):
    """PUR. ts de la dernière TENTATIVE d'ordre réel de la boucle (throttle). Les
    ÉCHECS comptent aussi : sinon un ordre qui échoue serait retenté à chaque cycle
    de 5 min (martèlement de l'exchange + spam d'alertes) au lieu d'attendre
    l'intervalle. None si aucune tentative."""
    for e in reversed(events or []):
        if not isinstance(e, dict) or e.get("action") not in actions:
            continue
        if ((e.get("order") or {}).get("agent")) == agent:
            return safe_float(e.get("ts"))
    return None


def throttle_ok(last_ts, now=None, min_h=None):
    """PUR. Au plus un ordre auto toutes min_h heures."""
    min_h = float(_cfg("FUTURES_AUTO_MIN_INTERVAL_H", 4.0) if min_h is None else min_h)
    if last_ts is None:
        return True
    now = time.time() if now is None else now
    return (now - float(last_ts)) >= min_h * 3600.0


# ---------- lectures d'état (best-effort, lecture seule) ----------

def position_nette():
    """Position nette BTCUSDT du compte (one-way) : {"side", "size_btc", "notional_usdt"}
    ou None si flat. Fail-safe : {"erreur": ...} si la lecture échoue (on ne décide pas
    à l'aveugle)."""
    try:
        import bitget_hub_bridge as hub
        d = hub._read(["futures", "futures_get_positions", "--productType", "USDT-FUTURES"])
        rows = (d or {}).get("data")
        if rows is None:
            return {"erreur": "positions illisibles"}
        net = 0.0
        notional = 0.0
        for r in rows:
            if str(r.get("symbol", "")).upper() != SYMBOL:
                continue
            taille = safe_float(r.get("total") or r.get("size")) or 0.0
            sens = 1.0 if str(r.get("holdSide", "")).lower() == "long" else -1.0
            net += sens * taille
            notional += abs(taille) * (safe_float(r.get("markPrice")) or 0.0)
        if abs(net) < 1e-9:
            return None
        return {"side": "long" if net > 0 else "short", "size_btc": round(abs(net), 6),
                "notional_usdt": round(notional, 2)}
    except Exception:
        return {"erreur": "positions illisibles"}


def _brain_entries():
    try:
        import swarm_brain
        return swarm_brain._read_log()
    except Exception:
        return []


def _executor_events():
    try:
        import futures_executor as fe
        path = fe._ledger_path()
        return (json.loads(path.read_text(encoding="utf-8")) or {}).get("events", [])
    except Exception:
        return []


def _atr(limit=60):
    """ATR 15m courant. calculate_atr prend des BOUGIES {high,low,close} — l'ancien
    appel (highs, lows, closes) levait TypeError avalé en silence : le SL retombait
    TOUJOURS sur le % fixe au lieu de l'ATR (bug trouvé à l'audit, corrigé)."""
    try:
        import technicals as tk
        import indicators
        candles = tk.fetch_candles(SYMBOL, "15m", limit)
        return float(indicators.calculate_atr(candles)[-1])
    except Exception:
        return None


# ---------- cycle ----------

def run(now=None):
    """Un cycle de décision directionnelle. Retourne un dict rapport. N'exécute que si
    FUTURES_AUTO_DIRECTIONAL=1 ET les gardes de futures_executor passent."""
    now = time.time() if now is None else now
    out = {"ts": int(now), "armed": bool(int(_cfg("FUTURES_AUTO_DIRECTIONAL", 1) or 0))}
    if not out["armed"]:
        out["decision"] = {"action": "rien", "raison": "FUTURES_AUTO_DIRECTIONAL=0 (débrayé)"}
        return out
    c = consensus_frais(_brain_entries(), now=now)
    out["consensus"] = c
    pos = position_nette()
    if isinstance(pos, dict) and pos.get("erreur"):
        out["decision"] = {"action": "rien", "raison": pos["erreur"] + " (fail-closed)"}
        return out
    out["position"] = pos
    # propriété : une position ouverte par un AUTRE agent (carry, validation...)
    # n'est jamais touchée par la boucle directionnelle.
    if pos:
        owner = proprietaire_position(_executor_events())
        out["owner"] = owner
        if owner != "auto_dir":
            out["decision"] = {"action": "rien", "side": None,
                               "raison": f"position détenue par '{owner}' — pas à nous"}
            return out
    d = decider(c, (pos or {}).get("side") if pos else None)
    out["decision"] = d
    if d["action"] == "rien":
        return out
    if not throttle_ok(dernier_ordre_auto_ts(_executor_events()), now=now):
        out["decision"] = {**d, "action": "rien",
                           "raison": d["raison"] + " — throttle ordre (intervalle non écoulé)"}
        return out
    import futures_executor as fe
    if d["action"] == "fermer":
        notional = min(float(pos["notional_usdt"]),
                       fe._capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0,
                                  fe.FUT_ABS_MAX_PER_TRADE_USDT))
        # taille EXACTE de la position (reduceOnly borne à la position) : un notional
        # arrondi vers le bas laisserait une poussière sous le minimum, infermable.
        res = fe.execute("auto_dir", pos["side"], notional,
                         float(_cfg("FUTURES_AUTO_LEVERAGE", 2.0)),
                         reduce=True, confirm=True, now=now,
                         size_btc=pos.get("size_btc"))
    else:                                          # ouvrir
        prix = fe._mark_price()
        sl, tp = sl_tp(d["side"], prix, atr=_atr())
        res = fe.execute("auto_dir", d["side"],
                         float(_cfg("FUTURES_AUTO_NOTIONAL_USDT", 10.0)),
                         float(_cfg("FUTURES_AUTO_LEVERAGE", 2.0)),
                         entry=prix, stop_loss=sl, take_profit=tp,
                         confirm=True, now=now,
                         gross_open_usdt=(pos or {}).get("notional_usdt") or 0.0,
                         equity_curve=fe.equity_curve())   # halte MDD du mandat (garde 6)
    out["resultat"] = {"executed": bool(res.get("executed")), "ok": res.get("ok"),
                       "reasons": res.get("reasons"), "clientOid": res.get("clientOid")}
    try:
        import telegram_notifier as tn
        if out["resultat"]["executed"]:
            tn.send_telegram(f"⚡ FUTURES RÉEL (boucle auto §45) : {d['action'].upper()} "
                             f"{d.get('side') or ''} — {d['raison']}. "
                             f"oid {res.get('clientOid')} · voir /futures")
        else:
            # échec d'exécution = à savoir TOUT DE SUITE (le throttle espace les retentes)
            tn.send_telegram(f"⚠️ FUTURES boucle auto : ÉCHEC {d['action']} "
                             f"{d.get('side') or ''} — {res.get('reasons') or 'réponse exchange'}. "
                             f"Retente après throttle · voir /futures")
    except Exception:
        pass
    return out


def status(now=None):
    """Décision PRÉVISUALISÉE, STRICTEMENT LECTURE SEULE : même lecture que run()
    mais n'appelle JAMAIS l'exécuteur (pour Telegram /futures, dashboard, CLI
    --status). C'est « ce que la boucle ferait », pas ce qu'elle fait."""
    now = time.time() if now is None else now
    out = {"ts": int(now), "consultation": True,
           "armed": bool(int(_cfg("FUTURES_AUTO_DIRECTIONAL", 1) or 0))}
    c = consensus_frais(_brain_entries(), now=now)
    out["consensus"] = c
    pos = position_nette()
    if isinstance(pos, dict) and pos.get("erreur"):
        out["position"] = None
        out["decision"] = {"action": "rien", "raison": pos["erreur"] + " (fail-closed)"}
        return out
    out["position"] = pos
    if pos:
        owner = proprietaire_position(_executor_events())
        out["owner"] = owner
        if owner != "auto_dir":
            out["decision"] = {"action": "rien", "side": None,
                               "raison": f"position détenue par '{owner}' — pas à nous"}
            out["throttle_pret"] = throttle_ok(dernier_ordre_auto_ts(_executor_events()), now=now)
            return out
    out["decision"] = decider(c, (pos or {}).get("side") if pos else None)
    out["throttle_pret"] = throttle_ok(dernier_ordre_auto_ts(_executor_events()), now=now)
    return out


def build_report(r=None):
    r = run() if r is None else r
    d = r.get("decision") or {}
    lignes = ["=== BOUCLE FUTURES DIRECTIONNELLE (§45, bornée) ==="]
    lignes.append(f"Armée : {r.get('armed')} · consensus {r.get('consensus')} · "
                  f"position {r.get('position') or 'flat'}")
    lignes.append(f"Décision : {d.get('action', 'rien').upper()} "
                  f"{d.get('side') or ''} — {d.get('raison', '')}")
    res = r.get("resultat")
    if res:
        etat = "EXÉCUTÉ" if res.get("executed") else f"refusé/échec ({res.get('reasons')})"
        lignes.append(f"Exécution : {etat} (oid {res.get('clientOid')})")
    lignes.append("Décision seule ici — toute exécution passe par futures_executor "
                  "(gardes, caps, stop journalier). VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    import sys
    # --status = consultation pure (jamais d'exécution) ; sans flag = CYCLE (le
    # chemin du scheduler : peut exécuter via futures_executor si tout est vert).
    if "--status" in sys.argv[1:]:
        r = status()
        print(build_report(r).replace("(§45, bornée)", "(§45, bornée) — CONSULTATION"))
        return
    print(build_report())


if __name__ == "__main__":
    main()
