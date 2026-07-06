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
    import os
    sl_pct = float(_cfg("FUTURES_AUTO_SL_PCT", 1.5) if sl_pct is None else sl_pct)
    # RR env-aware (§68 B : calibration -> 1.5 ; env prioritaire pour effet immédiat)
    rr = float((os.getenv("FUTURES_AUTO_RR") or _cfg("FUTURES_AUTO_RR", 1.5)) if rr is None else rr)
    a = safe_float(atr)
    dist = 1.5 * a if (a is not None and a > 0) else p * sl_pct / 100.0
    if str(side) == "long":
        return p - dist, p + dist * rr
    return p + dist, p - dist * rr


def consensus_frais(entries, now=None, max_age_s=900, symbol=None):
    """PUR. Dernier consensus d'UN symbole dans brain_log s'il est FRAIS
    (< max_age_s), sinon None (on ne trade jamais sur une lecture périmée)."""
    now = time.time() if now is None else now
    symbol = str(symbol or SYMBOL).upper()
    for e in reversed(entries or []):
        if not isinstance(e, dict) or e.get("symbol") != symbol:
            continue
        ts = safe_float(e.get("ts"))
        if ts is None or now - ts > max_age_s:
            return None
        return safe_float(e.get("consensus"))
    return None


def parser_positions(rows):
    """PUR. Lignes API -> {"long": pos|None, "short": pos|None} (mode hedge : les
    deux côtés peuvent coexister ; en one-way un seul est non-nul). pos = {side,
    size_btc, notional_usdt}."""
    out = {"long": None, "short": None}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        cote = str(r.get("holdSide", "")).lower()
        taille = safe_float(r.get("total") or r.get("size")) or 0.0
        if cote in out and taille > 1e-12:
            out[cote] = {"side": cote, "size_btc": round(taille, 6),
                         "notional_usdt": round(taille * (safe_float(r.get("markPrice")) or 0.0), 2)}
    return out


def positions_cotes(symbol=None):
    """Positions par CÔTÉ d'UN symbole (lecture seule). {"erreur": ...} si illisible."""
    try:
        import futures_executor as fe
        rows = fe.positions_ouvertes(symbol=str(symbol or SYMBOL).upper())
        if rows is None:
            return {"erreur": "positions illisibles"}
        return parser_positions(rows)
    except Exception:
        return {"erreur": "positions illisibles"}


def positions_par_symbole():
    """{symbol: {"long": pos|None, "short": pos|None}} sur TOUS les symboles.
    {"erreur": ...} si illisible."""
    try:
        import futures_executor as fe
        rows = fe.positions_ouvertes()
        if rows is None:
            return {"erreur": "positions illisibles"}
        out = {}
        for r in rows or []:
            sym = str((r or {}).get("symbol", "")).upper()
            if sym:
                out.setdefault(sym, []).append(r)
        return {sym: parser_positions(rs) for sym, rs in out.items()}
    except Exception:
        return {"erreur": "positions illisibles"}


def gross_book_usdt(par_sym=None):
    """Notional total ouvert sur TOUT le livre futures (tous symboles ET côtés).
    Sert de gross_open_usdt CROSS-LIVRE pour la garde de cap cumulé (§45) : un
    appelant ne doit jamais présenter sa seule jambe, sinon le mur 250 $ est aveugle
    au reste du livre. Retourne None si le livre est illisible -> l'appelant DOIT
    fail-closed (ne pas ouvrir à l'aveugle), jamais retomber sur 0."""
    if par_sym is None:
        par_sym = positions_par_symbole()
    if not isinstance(par_sym, dict) or par_sym.get("erreur"):
        return None
    return round(sum((cotes.get(k) or {}).get("notional_usdt") or 0.0
                     for cotes in par_sym.values() if isinstance(cotes, dict)
                     for k in ("long", "short")), 2)


def proprietaire_cote(events, cote, symbol=None):
    """PUR. Agent PROPRIÉTAIRE d'un (SYMBOLE, CÔTÉ) : l'agent du dernier ordre RÉEL
    d'OUVERTURE sur ce côté de ce symbole. En mode hedge chaque côté a son
    propriétaire — carry gère son short BTC pendant qu'auto_dir gère ses positions.
    Un côté ouvert par un autre agent (ex. 'validation' manuelle) n'est JAMAIS
    touché. Les événements historiques sans champ symbol valent BTCUSDT."""
    symbol = str(symbol or SYMBOL).upper()
    for e in reversed(events or []):
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        order = e.get("order") or {}
        sym_e = str(order.get("symbol") or SYMBOL).upper()
        if not order.get("reduce") and str(order.get("side")) == str(cote) and sym_e == symbol:
            return order.get("agent")
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


def report_funding(now, side, taux_funding, marge_min=None):
    """PUR (§60). Raison de REPORT si un règlement de funding (00/08/16 UTC)
    tombe dans les marge_min prochaines minutes ET que le côté à ouvrir PAIERAIT
    (long paie si taux > 0, short paie si taux < 0) : ouvrir juste APRÈS le
    règlement évite un paiement sec (SAVOIR.md §5). Ne s'applique qu'aux
    OUVERTURES ; taux illisible/nul -> None (fail-open)."""
    from numeric_utils import safe_float
    taux = safe_float(taux_funding)
    if not taux:
        return None
    paie = (side == "long" and taux > 0) or (side == "short" and taux < 0)
    if not paie:
        return None
    marge_min = float(_cfg("FUTURES_FUNDING_TIMING_MIN", 20) if marge_min is None else marge_min)
    prochain = (int(now) // 28800 + 1) * 28800          # prochain multiple de 8 h UTC
    minutes = (prochain - now) / 60.0
    if minutes <= marge_min:
        return (f"règlement de funding dans {minutes:.0f} min et le {side} paierait "
                f"({taux:+.6f}) — report après règlement")
    return None


def blackout_macro(now=None, evenements=None):
    """Raison de black-out macro si une annonce (Fed/CPI, calendrier VIVANT
    Kalshi §59) est imminente — le mandat le prévoyait (MANDATE_MACRO_BLACKOUT_*)
    sans calendrier réel jusqu'ici. Ne bloque que les OUVERTURES (fermer reste
    permis : réduire le risque n'attend pas). None si rien d'imminent ou si le
    calendrier est muet (fail-open)."""
    try:
        if evenements is None:
            import kalshi_probe as kp
            evenements = kp.fetch_evenements()
        import kalshi_probe as kp
        e = kp.evenement_imminent(
            evenements, now=now,
            pre_min=float(_cfg("MANDATE_MACRO_BLACKOUT_PRE_MIN", 30)),
            post_min=float(_cfg("MANDATE_MACRO_BLACKOUT_POST_MIN", 15)))
        if e:
            return f"black-out macro : {e.get('titre')} imminent (±fenêtre mandat)"
    except Exception:
        return None
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


def _atr(limit=60, symbol=None):
    """ATR 15m courant. calculate_atr prend des BOUGIES {high,low,close} — l'ancien
    appel (highs, lows, closes) levait TypeError avalé en silence : le SL retombait
    TOUJOURS sur le % fixe au lieu de l'ATR (bug trouvé à l'audit, corrigé)."""
    try:
        import technicals as tk
        import indicators
        candles = tk.fetch_candles(str(symbol or SYMBOL).upper(), "15m", limit)
        return float(indicators.calculate_atr(candles)[-1])
    except Exception:
        return None


# ---------- cycle ----------

def _journal_decision(out):
    """Journal APPEND-ONLY des décisions de cycle (audit P2) : une ligne JSONL par
    cycle — la revue J+14 mesure la distribution réelle du consensus et la
    fréquence de franchissement des seuils sur l'HISTORIQUE, pas sur 6 h."""
    try:
        import journal_append as ja
        d = out.get("decision") or {}
        res = out.get("resultat") or {}
        ja.append_jsonl(Path(__file__).resolve().parent / "futures_auto_journal.jsonl",
                        {"ts": out.get("ts"), "boucle": out.get("boucle", "auto_dir"),
                         "symbol": out.get("symbol"),
                         "consensus": out.get("consensus"),
                         "apr_net_pct": out.get("apr_net_pct"),
                         "position": (out.get("position") or {}).get("side"),
                         "action": d.get("action"), "side": d.get("side"),
                         "raison": d.get("raison"),
                         "executed": res.get("executed")},
                        max_bytes=20_000_000)
    except Exception:
        pass


def run(now=None):
    """Un cycle de décision directionnelle (journalisé, voir _journal_decision)."""
    out = _run_cycle(now)
    _journal_decision(out)
    try:                                          # courbe d'équité intrajournalière
        import futures_executor as fe             # (best-effort, throttlé ≥10 min)
        fe.journal_equity_point(now)
    except Exception:
        pass
    return out


def _notional_cfg():
    """Notional par trade, ENV-AWARE (env prioritaire > config, comme FUTURES_AUTO_RR) :
    monter/baisser la taille = décision propriétaire par levier env, effet immédiat."""
    import os
    try:
        return float(os.getenv("FUTURES_AUTO_NOTIONAL_USDT") or _cfg("FUTURES_AUTO_NOTIONAL_USDT", 10.0))
    except (TypeError, ValueError):
        return float(_cfg("FUTURES_AUTO_NOTIONAL_USDT", 10.0))


def _prix_entry(entries, sym):
    """Dernier prix journalisé du symbole (journal du cerveau). None sinon. PUR."""
    for e in reversed(entries or []):
        if e.get("symbol") == sym and e.get("price"):
            try:
                return float(e["price"])
            except (TypeError, ValueError):
                return None
    return None


def _taille_faisable(sym, entries, notional=None):
    """Le notional CONFIGURÉ passe-t-il les MINIMA du contrat ? (§75) Sans ce filtre,
    la boucle choisissait un candidat infaisable, l'exécuteur refusait « taille
    infaisable » et la boucle restait FLAT en boucle (3 refus réels journalisés :
    ETH ×2 le 05/07, LAB le 06/07). On écarte le symbole À LA DÉCISION — la place
    revient au candidat suivant. MONTER le notional reste une décision propriétaire
    (FUTURES_AUTO_NOTIONAL_USDT). Fail-open si spec/prix illisibles : l'exécuteur
    reste le juge final (fail-closed)."""
    try:
        import futures_executor as fe
        notional = _notional_cfg() if notional is None else float(notional)
        spec = fe._contract_spec(sym)
        px = _prix_entry(entries, sym)
        if not spec or not px:
            return True
        return fe.size_for(notional, px, spec) is not None
    except Exception:
        return True


def _universe():
    """Symboles surveillés par la boucle (univers dynamique, repli BTCUSDT)."""
    try:
        import universe
        syms = [str(s).upper() for s in universe.symbols()]
        return syms or [SYMBOL]
    except Exception:
        return [SYMBOL]


def _mes_positions(par_symbole, events):
    """[(symbol, pos)] possédés par auto_dir, sur tous les symboles."""
    miennes = []
    for sym, cotes in (par_symbole or {}).items():
        if not isinstance(cotes, dict):
            continue
        for cote in ("long", "short"):
            pos = cotes.get(cote)
            if pos and proprietaire_cote(events, cote, symbol=sym) == "auto_dir":
                miennes.append((sym, pos))
    return miennes


ETAT_POS_FILE = Path(__file__).resolve().parent / ".futures_pos_state.json"
AGENTS_BOT = ("auto_dir", "carry")


def fermetures_exchange(precedentes, actuelles, events, depuis_ts):
    """PUR. Positions du bot DISPARUES sans ordre de fermeture du bot depuis
    depuis_ts = fermées CÔTÉ EXCHANGE (SL/TP préréglé, liquidation, ou manuel).
    Le round-trip du 03/07 : le SL préréglé a fermé un long EN SILENCE — aucune
    alerte. `precedentes`/`actuelles` = [{symbol, side, agent}]."""
    act = {(p.get("symbol"), p.get("side")) for p in actuelles or []}
    reduites_bot = set()
    for e in events or []:
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        if (safe_float(e.get("ts")) or 0) < float(depuis_ts or 0):
            continue
        o = e.get("order") or {}
        if o.get("reduce"):
            reduites_bot.add((str(o.get("symbol") or SYMBOL).upper(), o.get("side")))
    disparues = []
    for p in precedentes or []:
        cle = (p.get("symbol"), p.get("side"))
        if cle not in act and cle not in reduites_bot:
            disparues.append(p)
    return disparues


def _surveille_fermetures_exchange(par_sym, events, now):
    """Compare l'état des positions du bot au cycle précédent : toute disparition
    sans ordre du bot -> alerte push (sinon le SL/TP côté exchange travaille en
    silence) + ligne au journal de décision. Best-effort, n'affecte jamais le cycle."""
    try:
        actuelles = []
        for sym, cotes in (par_sym or {}).items():
            if not isinstance(cotes, dict):
                continue
            for cote in ("long", "short"):
                pos = cotes.get(cote)
                if pos:
                    agent = proprietaire_cote(events, cote, symbol=sym)
                    if agent in AGENTS_BOT:
                        actuelles.append({"symbol": sym, "side": cote, "agent": agent,
                                          "notional_usdt": pos.get("notional_usdt")})
        try:
            etat = json.loads(ETAT_POS_FILE.read_text(encoding="utf-8"))
        except Exception:
            etat = {}
        disparues = fermetures_exchange(etat.get("positions"), actuelles, events,
                                        etat.get("ts", 0))
        for p in disparues:
            try:
                import telegram_notifier as tn
                tn.send_telegram(f"⚡ Position {p.get('side')} {p.get('symbol')} "
                                 f"({p.get('agent')}) fermée CÔTÉ EXCHANGE (SL/TP préréglé "
                                 f"probable) — voir /futures pour le PnL réalisé.")
            except Exception:
                pass
            try:
                import journal_append as ja
                ja.append_jsonl(Path(__file__).resolve().parent / "futures_auto_journal.jsonl",
                                {"ts": int(now), "boucle": p.get("agent"),
                                 "symbol": p.get("symbol"), "action": "fermee_exchange",
                                 "side": p.get("side"), "raison": "SL/TP côté exchange"},
                                max_bytes=20_000_000)
            except Exception:
                pass
        ETAT_POS_FILE.write_text(json.dumps({"ts": int(now), "positions": actuelles},
                                            ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _finaliser(out, d, res):
    """Résultat + alertes push (succès ⚡ / échec ⚠️), commun fermer/ouvrir."""
    out["resultat"] = {"executed": bool(res.get("executed")), "ok": res.get("ok"),
                       "reasons": res.get("reasons"), "clientOid": res.get("clientOid")}
    sym = d.get("symbol") or SYMBOL
    try:
        import telegram_notifier as tn
        if out["resultat"]["executed"]:
            tn.send_telegram(f"⚡ FUTURES RÉEL (boucle auto §45) : {d['action'].upper()} "
                             f"{d.get('side') or ''} {sym} — {d['raison']}. "
                             f"oid {res.get('clientOid')} · voir /futures")
        else:
            tn.send_telegram(f"⚠️ FUTURES boucle auto : ÉCHEC {d['action']} "
                             f"{d.get('side') or ''} {sym} — "
                             f"{res.get('reasons') or 'réponse exchange'}. "
                             f"Retente après throttle · voir /futures")
    except Exception:
        pass
    return out


def _run_cycle(now=None):
    """Cycle MULTI-SYMBOLES (§47 — « passer les agents en réel » : le cerveau vote
    sur TOUT l'univers depuis la réparation de l'audit, la boucle trade désormais le
    canal consensus de chaque symbole). Politique frugale inchangée, étendue :
      1) FERMETURES d'abord (une par cycle max, NON throttlées : réduire le risque
         n'attend pas) sur les positions possédées par la boucle ;
      2) sinon OUVERTURE : au plus FUTURES_AUTO_MAX_POSITIONS positions, une par
         symbole, un ordre par throttle — le candidat au |consensus| MAX ≥ seuil,
         côté libre, jamais de netting en one-way transitoire."""
    now = time.time() if now is None else now
    out = {"ts": int(now), "armed": bool(int(_cfg("FUTURES_AUTO_DIRECTIONAL", 1) or 0))}
    if not out["armed"]:
        out["decision"] = {"action": "rien", "raison": "FUTURES_AUTO_DIRECTIONAL=0 (débrayé)"}
        return out
    par_sym = positions_par_symbole()
    if isinstance(par_sym, dict) and par_sym.get("erreur"):
        out["decision"] = {"action": "rien", "raison": par_sym["erreur"] + " (fail-closed)"}
        return out
    events = _executor_events()
    entries = _brain_entries()
    _surveille_fermetures_exchange(par_sym, events, now)   # SL/TP exchange ≠ silence
    miennes = _mes_positions(par_sym, events)
    out["positions"] = [{"symbol": s, **pos} for s, pos in miennes]
    out["position"] = ({"symbol": miennes[0][0], **miennes[0][1]} if miennes else None)
    gross = gross_book_usdt(par_sym) or 0.0
    out["gross_usdt"] = round(gross, 2)
    import futures_executor as fe

    # 1) FERMETURES d'abord — non throttlées : réduire le risque n'attend pas
    for sym, pos in miennes:
        c = consensus_frais(entries, now=now, symbol=sym)
        d = decider(c, pos.get("side"))
        if d["action"] == "fermer":
            out["symbol"], out["consensus"] = sym, c
            out["decision"] = {**d, "symbol": sym}
            res = fe.execute("auto_dir", pos["side"],
                             float(pos.get("notional_usdt") or 0) or 1.0,
                             float(_cfg("FUTURES_AUTO_LEVERAGE", 2.0)),
                             reduce=True, confirm=True, now=now,
                             size_btc=pos.get("size_btc"), symbol=sym)
            return _finaliser(out, out["decision"], res)

    # 2) OUVERTURE : plafond de positions, puis meilleur candidat, puis throttle
    max_pos = int(_cfg("FUTURES_AUTO_MAX_POSITIONS", 3))
    if len(miennes) >= max_pos:
        out["consensus"] = consensus_frais(entries, now=now, symbol=SYMBOL)
        out["decision"] = {"action": "rien",
                           "raison": f"{len(miennes)} position(s) (plafond {max_pos}) — on gère l'existant"}
        return out
    mode = fe.resolve_pos_mode(fe.positions_ouvertes(),
                               _cfg("FUTURES_POSITION_MODE", "hedge_mode"))
    deja = {s for s, _ in miennes}
    candidats = []
    for sym in _universe():
        if sym in deja:
            continue                                  # une position max par symbole
        c = consensus_frais(entries, now=now, symbol=sym)
        d = decider(c, None)
        if d["action"] != "ouvrir":
            continue
        try:                                          # véto annonces (delisting/suspension) — fail-open
            import bitget_announcements as ba
            if ba.symbol_blocked(sym):
                out["annonce_veto"] = out.get("annonce_veto", 0) + 1
                continue
        except Exception:
            pass
        cotes = par_sym.get(sym) or {}
        if cotes.get(d["side"]):
            continue                                  # côté occupé par un autre agent
        if mode == "one_way_mode" and (cotes.get("long") or cotes.get("short")):
            continue                                  # netting interdit en one-way
        if not _taille_faisable(sym, entries):
            out.setdefault("infaisables", []).append(sym)   # minima contrat > notional §75
            continue
        candidats.append((abs(c), sym, c, d))
    out["n_candidats"] = len(candidats)
    out["consensus"] = consensus_frais(entries, now=now, symbol=SYMBOL)
    if not candidats:
        out["decision"] = {"action": "rien",
                           "raison": "aucun consensus ≥ seuil sur l'univers (côtés libres)"}
        return out
    candidats.sort(key=lambda x: (-x[0], x[1]))
    _, sym, c, d = candidats[0]
    out["symbol"], out["consensus"] = sym, c
    raison_bo = blackout_macro(now=now)            # annonces Fed/CPI : pas d'OUVERTURE
    if raison_bo:
        out["decision"] = {**d, "action": "rien", "symbol": sym,
                           "raison": d["raison"] + f" [{sym}] — {raison_bo}"}
        return out
    try:                                           # timing de funding (§60, fail-open)
        import carry_monitor as cm
        import derivs_positioning as dp
        taux = (dp.fetch_snapshot(sym) or {}).get("funding")
    except Exception:
        taux = None
    raison_fd = report_funding(now, d["side"], taux)
    if raison_fd:
        out["decision"] = {**d, "action": "rien", "symbol": sym,
                           "raison": d["raison"] + f" [{sym}] — {raison_fd}"}
        return out
    if not throttle_ok(dernier_ordre_auto_ts(events), now=now):
        out["decision"] = {**d, "action": "rien", "symbol": sym,
                           "raison": d["raison"] + f" [{sym}] — throttle ordre (intervalle non écoulé)"}
        return out
    out["decision"] = {**d, "symbol": sym}
    prix = fe._mark_price(sym)
    sl, tp = sl_tp(d["side"], prix, atr=_atr(symbol=sym))
    if sl is None:
        # Invariant Couche 1 : JAMAIS d'ouverture directionnelle sans stop-loss préréglé
        # côté exchange (le seul filet qui survive à la mort de l'host). Prix illisible
        # -> sl_tp rend (None, None) : on s'abstient (fail-closed) plutôt que d'ouvrir nu.
        out["decision"] = {**d, "action": "rien", "symbol": sym,
                           "raison": d["raison"] + f" [{sym}] — SL introuvable (prix illisible), "
                                     "ouverture refusée (invariant SL exchange)"}
        return out
    res = fe.execute("auto_dir", d["side"],
                     _notional_cfg(),
                     float(_cfg("FUTURES_AUTO_LEVERAGE", 2.0)),
                     entry=prix, stop_loss=sl, take_profit=tp,
                     confirm=True, now=now, symbol=sym,
                     gross_open_usdt=gross,            # exposition TOUS symboles/côtés
                     equity_curve=fe.equity_curve())   # halte MDD du mandat (garde 6)
    return _finaliser(out, out["decision"], res)


def status(now=None):
    """Décision PRÉVISUALISÉE, STRICTEMENT LECTURE SEULE, multi-symboles : même
    lecture que le cycle mais n'appelle JAMAIS l'exécuteur (Telegram /futures,
    dashboard, CLI --status)."""
    now = time.time() if now is None else now
    out = {"ts": int(now), "consultation": True,
           "armed": bool(int(_cfg("FUTURES_AUTO_DIRECTIONAL", 1) or 0))}
    try:                                              # halte MDD VISIBLE (garde 6) : sans elle
        import futures_executor as fe                 # le statut affichait « OUVRIR » alors que
        dd = fe.drawdown_status()                     # chaque tentative était refusée
        if dd:
            out["drawdown"] = dd
    except Exception:
        pass
    par_sym = positions_par_symbole()
    if isinstance(par_sym, dict) and par_sym.get("erreur"):
        out["position"] = None
        out["decision"] = {"action": "rien", "raison": par_sym["erreur"] + " (fail-closed)"}
        return out
    events = _executor_events()
    entries = _brain_entries()
    miennes = _mes_positions(par_sym, events)
    out["positions"] = [{"symbol": s, **pos} for s, pos in miennes]
    out["position"] = ({"symbol": miennes[0][0], **miennes[0][1]} if miennes else None)
    # fermeture en attente ?
    for sym, pos in miennes:
        c = consensus_frais(entries, now=now, symbol=sym)
        d = decider(c, pos.get("side"))
        if d["action"] == "fermer":
            out["symbol"], out["consensus"] = sym, c
            out["decision"] = {**d, "symbol": sym}
            out["throttle_pret"] = True               # les fermetures ne sont pas throttlées
            return out
    # meilleur candidat d'ouverture
    deja = {s for s, _ in miennes}
    best = None
    for sym in _universe():
        if sym in deja:
            continue
        c = consensus_frais(entries, now=now, symbol=sym)
        d = decider(c, None)
        if d["action"] != "ouvrir":
            continue
        if (par_sym.get(sym) or {}).get(d["side"]):
            continue
        if not _taille_faisable(sym, entries):
            out.setdefault("infaisables", []).append(sym)   # minima contrat > notional §75
            continue
        if best is None or abs(c) > best[0]:
            best = (abs(c), sym, c, d)
    if best:
        _, sym, c, d = best
        out["symbol"], out["consensus"] = sym, c
        out["decision"] = {**d, "symbol": sym}
    else:
        out["consensus"] = consensus_frais(entries, now=now, symbol=SYMBOL)
        out["decision"] = {"action": "rien",
                           "raison": "aucun consensus ≥ seuil sur l'univers (côtés libres)"}
    out["throttle_pret"] = throttle_ok(dernier_ordre_auto_ts(events), now=now)
    return out


def build_report(r=None):
    r = run() if r is None else r
    d = r.get("decision") or {}
    lignes = ["=== BOUCLE FUTURES DIRECTIONNELLE (§45, bornée) ==="]
    lignes.append(f"Armée : {r.get('armed')} · consensus {r.get('consensus')} · "
                  f"position {r.get('position') or 'flat'}")
    lignes.append(f"Décision : {d.get('action', 'rien').upper()} "
                  f"{d.get('side') or ''} {d.get('symbol') or ''} — {d.get('raison', '')}")
    inf = r.get("infaisables") or []
    if inf:
        lignes.append(f"Écartés (minima contrat > notional configuré) : {', '.join(inf)} — "
                      "monter FUTURES_AUTO_NOTIONAL_USDT = décision propriétaire")
    dd = r.get("drawdown") or {}
    if dd.get("halt"):
        lignes.append(f"🛑 HALTE DRAWDOWN ACTIVE ({dd.get('dd_pct')} % ≥ {dd.get('max_dd_pct')} %) : "
                      "toute OUVERTURE est refusée par la garde 6 — mouvement de capital ? "
                      "voir futures_executor --rebase-equity (décision propriétaire)")
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
