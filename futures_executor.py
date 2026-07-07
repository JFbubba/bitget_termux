"""
futures_executor.py — EXÉCUTION FUTURES RÉELLE BORNÉE. Étape 2 (RESEARCH_NOTES §45).

⚠️ 2e module d'exécution AUTORISÉ — avec spot_executor, les SEULS endroits qui peuvent
passer un ordre réel. Le chemin réel est CÂBLÉ depuis le §45 : décision explicite du
propriétaire (02/07/2026, trois questions d'engagement répondues : périmètre carry +
directionnel, directement réel, plafond = solde). La porte d'edge (agent LIVE) peut
être OUTREPASSÉE par `FUTURES_EDGE_GATE_OVERRIDE` (config, décision §45) — remettre
à 0 la referme instantanément.

Périmètre BORNÉ par conception :
  ouverture/réduction d'une position futures (side 'long'/'short', reduce), marge
  ISOLÉE (la perte max d'une position = sa marge), levier ≤ mur ×5, notional/trade et
  exposition cumulée plafonnés par _capped (env/config peuvent ABAISSER, JAMAIS
  dépasser les murs absolus en dur), stop de perte JOURNALIER (arme le kill-switch).
  JAMAIS de retrait, JAMAIS de virement, JAMAIS d'annulation ici.

Gardes DURS (8 de §34 + pré-vol perte journalière) : voir guards() et execute().
Mode --dry par DÉFAUT : imprime le preview, n'exécute RIEN sans --confirm.
"""

import json
import time
from pathlib import Path

SYMBOL = "BTCUSDT"
PRODUCT_TYPE = "USDT-FUTURES"
MARGIN_COIN = "USDT"

# Murs ABSOLUS en dur (defense-in-depth, comme spot_executor) : ni .env ni config ne
# peuvent les DÉPASSER (les abaisser, oui). Le plafond réel effectif démarre BAS
# (config : 15/trade, 60 cumulé) et monte progressivement si l'exécution est propre —
# le mur cumulé 250 ≈ le solde autorisé par le propriétaire (§45).
FUT_ABS_MAX_PER_TRADE_USDT = 50.0
FUT_ABS_MAX_GROSS_USDT = 250.0
FUT_ABS_MAX_LEVERAGE = 5.0   # mur dur levier : ni .env ni config ne peuvent le DÉPASSER


from config_utils import cfg as _cfg


def _limit(name, fallback):
    """Plafond numérique : env > config > défaut (comme spot_executor)."""
    import os
    v = os.getenv(name)
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    return float(_cfg(name, fallback))


def _capped(name, fallback, absolute):
    """Plafond EFFECTIF = min(env > config > défaut, mur ABSOLU en dur). PUR (lit l'env)."""
    return min(_limit(name, fallback), float(absolute))


def _autonomous_on():
    """2e verrou FUTURES_AUTONOMOUS_LIVE : .env OU config (comme l'accumulation —
    l'option .env évite d'éditer un fichier suivi par git)."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    env_on = os.getenv("FUTURES_AUTONOMOUS_LIVE", "").strip().lower() in ("1", "true", "yes", "on")
    return env_on or bool(_cfg("FUTURES_AUTONOMOUS_LIVE", False))


def _execution_mode():
    """Mode affiché dans les previews/journaux : RÉEL borné si le double verrou est armé."""
    try:
        import mandate
        live = bool(mandate.live_enabled())
    except Exception:
        live = False
    return "FUTURES_REAL_BOUNDED" if (live and _autonomous_on()) else "FUTURES_DRY_RUN_ONLY"


# ---------- journal DRY-RUN (gitignored) ----------

def _ledger_path():
    return Path(__file__).resolve().parent / str(_cfg("FUTURES_REAL_LEDGER", "futures_real_ledger.json"))


def _journal(event):
    """Journalise un évènement (best-effort). Le ledger est gitignored."""
    path = _ledger_path()
    try:
        led = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"events": []}
    except Exception:
        led = {"events": []}
    led.setdefault("events", []).append(event)
    led["events"] = led["events"][-1000:]
    _write_ledger(led)                # atomique (journal d'argent réel, audit P3)


# ---------- gardes DURS (les 8 de §34 ; purs si on injecte l'état) ----------

def guards(agent, notional_usdt, leverage, *, equity_curve=None, gross_open_usdt=0.0,
           client_oid=None, seen_oids=None, hour_utc=None, macro_events=None, now=None,
           live=None, autonomous=None, futures_live=None, kill=None, edge_override=None,
           reduce=False):
    """Vérifie TOUTES les gardes avant un ordre futures. Retourne (ok, raisons).
    PUR si l'état est injecté (live/autonomous/futures_live/kill/equity_curve/...)."""
    reasons = []

    # 1. kill_switch : bloque les OUVERTURES. Une RÉDUCTION reste permise (audit P3) :
    # fermer n'aggrave jamais le risque — après un stop journalier, la boucle doit
    # pouvoir sortir d'une position même kill-switch armé (même principe que le
    # pré-vol daily_loss d'execute()).
    if kill is None:
        try:
            import risk_manager
            kill = risk_manager.kill_switch_active()
        except Exception:
            kill = False
    if kill and not reduce:
        reasons.append("kill_switch actif")

    # 2. DOUBLE verrou : MANDATE_LIVE_ENABLED ET FUTURES_AUTONOMOUS_LIVE
    if live is None:
        try:
            import mandate
            live = mandate.live_enabled()
        except Exception:
            live = False
    if autonomous is None:
        autonomous = _autonomous_on()
    if not (live and autonomous):
        reasons.append("double verrou coupé (MANDATE_LIVE_ENABLED ET FUTURES_AUTONOMOUS_LIVE requis)")

    # 3. porte d'edge : agent réellement éligible LIVE (replay ET live). Peut être
    # OUTREPASSÉE par FUTURES_EDGE_GATE_OVERRIDE — décision propriétaire §45
    # (02/07/2026), consciente que 0 agent n'a d'edge mesuré. Remettre à 0 la referme.
    if futures_live is None:
        try:
            import mandate
            futures_live = mandate.futures_live_allowed(agent)
        except Exception:
            futures_live = False
    if edge_override is None:
        edge_override = int(_cfg("FUTURES_EDGE_GATE_OVERRIDE", 0) or 0)
    if not futures_live and not edge_override:
        reasons.append(f"agent '{agent}' non éligible LIVE (porte d'edge non franchie)")

    # 4. levier ≤ mur dur (fail-closed : non numérique -> rejeté, jamais d'exception)
    #    _capped (pas _limit) : env/config peuvent ABAISSER le levier, JAMAIS dépasser ×5.
    max_lev = _capped("MANDATE_MAX_LEVERAGE", 5.0, FUT_ABS_MAX_LEVERAGE)
    try:
        lev = float(leverage or 0)
    except (TypeError, ValueError):
        lev = None
        reasons.append("levier invalide (non numérique)")
    if lev is not None:
        if lev <= 0:
            reasons.append("levier ≤ 0")
        elif lev > max_lev:
            reasons.append(f"levier {lev} > mur dur {max_lev}")

    # 5. caps notional par trade ET exposition cumulée (fail-closed sur non numérique)
    try:
        notion = float(notional_usdt or 0)
    except (TypeError, ValueError):
        notion = None
        reasons.append("notional invalide (non numérique)")
    if notion is not None:
        if notion <= 0:
            reasons.append("notional ≤ 0")
        # Les caps notional s'appliquent aux OUVERTURES : une RÉDUCTION (reduceOnly,
        # bornée à la position côté exchange) ne crée aucune exposition — l'exempter
        # permet de fermer en UN ordre une position construite par tranches
        # (cap carry 200, décision propriétaire 03/07).
        if not reduce:
            per_cap = _capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0, FUT_ABS_MAX_PER_TRADE_USDT)
            if notion > per_cap:
                reasons.append(f"notional {notion} > plafond/trade {per_cap}")
            gross_cap = _capped("FUTURES_REAL_MAX_GROSS_USDT", 20.0, FUT_ABS_MAX_GROSS_USDT)
            gross = float(gross_open_usdt or 0)
            if gross + notion > gross_cap:
                reasons.append(f"exposition cumulée dépassée ({gross}+{notion} > {gross_cap})")

    # 6. halte drawdown (equity réelle)
    if equity_curve is not None:
        try:
            import mandate
            halt, dd_pct = mandate.drawdown_halt(equity_curve)
            if halt:
                reasons.append(f"halte drawdown ({dd_pct}% ≥ MDD toléré)")
        except Exception:
            pass

    # 7. session active + pas de black-out macro
    if hour_utc is not None:
        try:
            import mandate
            if not mandate.in_active_session(hour_utc):
                reasons.append("hors fenêtre de session active")
        except Exception:
            pass
    if macro_events is not None:
        try:
            import mandate
            nw = time.time() if now is None else now
            if mandate.macro_blackout(nw, macro_events):
                reasons.append("black-out macro (annonce à fort impact)")
        except Exception:
            pass

    # 8. idempotence clientOid (rejoue sans doubler)
    if client_oid is not None and seen_oids is not None:
        if str(client_oid) in set(str(o) for o in seen_oids):
            reasons.append(f"clientOid déjà vu ({client_oid}) — anti-doublon")

    return (not reasons, reasons)


# ---------- construction de la demande (pure) ----------

def _qty(x, decimals=6):
    """Notation DÉCIMALE (jamais scientifique) — Bitget rejette '8.3e-05'."""
    return f"{round(float(x), decimals):.{decimals}f}"


def build_futures_order(agent, side, notional_usdt, leverage, entry=None,
                        stop_loss=None, take_profit=None, client_oid=None, *, reduce=False,
                        size_btc=None, symbol=None):
    """Construit la demande d'ordre futures BORNÉE. PUR, sans effet de bord.

      • side ∈ {'long','short'} (vocabulaire neutre — l'open/close venue vient à l'étape 2) ;
      • reduce=True -> réduit/ferme une position existante ; False -> ouvre/augmente ;
      • le levier est CLAMPÉ au mur dur (jamais au-delà de mandate.max_leverage()).
    Retourne un dict descriptif (symbole, side, reduce, notional, levier, marge, oid, SL/TP).
    """
    s = str(side).lower()
    if s not in ("long", "short"):
        raise ValueError(f"side invalide: {side!r} (attendu 'long' ou 'short')")
    max_lev = _capped("MANDATE_MAX_LEVERAGE", 5.0, FUT_ABS_MAX_LEVERAGE)
    lev = max(1.0, min(float(max_lev), float(leverage)))   # borné par le mur, jamais au-delà
    notion = float(notional_usdt)
    order = {
        "symbol": str(symbol or SYMBOL).upper(),
        "side": s,
        "reduce": bool(reduce),
        "agent": str(agent),
        "notional_usdt": round(notion, 2),
        "leverage": round(lev, 2),
        "marginUsdt": round(notion / lev, 2) if lev else None,
        "size": _qty(notion / float(entry)) if entry else None,
        "clientOid": str(client_oid) if client_oid is not None else None,
        "execution_mode": _execution_mode(),
    }
    if size_btc is not None:
        # taille EXPLICITE (fermetures : la taille exacte de la position, pas un
        # notional re-converti qui laisserait une poussière infermable après floor)
        order["size_btc"] = float(size_btc)
    if entry is not None:
        order["entry"] = float(entry)
    if stop_loss is not None:
        order["stop_loss"] = float(stop_loss)
    if take_profit is not None:
        order["take_profit"] = float(take_profit)
    return order


def liquidity_capped_notional(notional, side, top_of_book):
    """PUR (§98). Plafonne le notionnel d'OUVERTURE par la liquidité AFFICHÉE au top-of-book,
    du côté que l'ordre TRAVERSE (long achète -> traverse l'ASK ; short vend -> traverse le BID) :
    on ne balaie jamais plus que ce qui est visible. Via data_guards.cap_by_liquidity — NE PEUT
    QUE réduire (jamais augmenter). FAIL-OPEN : top illisible / taille nulle / side inconnu ->
    notional INCHANGÉ (une garde de données ne doit pas empêcher de trader quand la profondeur
    est illisible). Retourne (notional_capé, a_capé:bool). Réservé aux OUVERTURES par l'appelant
    (jamais une réduction : fermer doit rester possible en entier)."""
    try:
        import data_guards as dg
        n = float(notional)
    except (TypeError, ValueError):
        return notional, False
    if not top_of_book or n <= 0:
        return notional, False
    s = str(side).lower()
    if s == "long":
        price, size = top_of_book.get("ask"), top_of_book.get("ask_size")
    elif s == "short":
        price, size = top_of_book.get("bid"), top_of_book.get("bid_size")
    else:
        return notional, False
    capped = dg.cap_by_liquidity(n, price, size)
    if capped is None:
        return notional, False
    capped = round(float(capped), 2)
    return (capped, capped < n - 1e-9)


# ---------- stop de perte JOURNALIER (arme le kill-switch, fail-closed) ----------

def daily_loss_state_check(equity, state, now=None, stop_pct=None, cliff_pct=None):
    """PUR. Compare l'equity courante à l'equity d'OUVERTURE du jour (mémorisée dans
    `state` = {"day", "open_equity", "last_equity"}). Retourne (breach, nouvel_état).
    Nouveau jour -> l'equity courante devient l'ouverture. Equity illisible -> BREACH
    (fail-closed : on ne trade pas à l'aveugle).

    RE-BASELINE sur FLUX DE CAPITAL (correctif faux breach 05/07) : un saut du livre
    d'un tick à l'autre > cliff_pct de l'ouverture est impossible en P&L de trading
    borné (murs 50/250, progressif) -> c'est un dépôt/retrait/CONVERT (ex. conversion
    BGBTC). On DÉCALE l'ouverture du même montant : le stop continue de mesurer le P&L,
    jamais un mouvement de fonds. Une vraie perte, elle, s'accumule par petits pas et ne
    franchit jamais ce seuil -> le stop la capte normalement."""
    stop_pct = float(_cfg("FUTURES_DAILY_LOSS_STOP_PCT", 5.0) if stop_pct is None else stop_pct)
    cliff_pct = float(_cfg("FUTURES_BOOK_CLIFF_REBASE_PCT", 15.0) if cliff_pct is None else cliff_pct)
    now = time.time() if now is None else now
    day = int(now // 86400)
    from numeric_utils import safe_float
    eq = safe_float(equity)
    state = dict(state or {})
    if eq is None or eq <= 0:
        return True, state                        # aveugle -> on n'ouvre pas
    if state.get("day") != day or safe_float(state.get("open_equity")) is None:
        state = {"day": day, "open_equity": eq, "last_equity": eq}
        return False, state
    ouverture = float(state["open_equity"])
    last = safe_float(state.get("last_equity"))
    if last is not None and cliff_pct > 0 and abs(eq - last) > ouverture * cliff_pct / 100.0:
        ouverture += (eq - last)                   # la baseline SUIT le flux de capital
        state["open_equity"] = ouverture
    state["last_equity"] = eq
    breach = eq < ouverture * (1.0 - stop_pct / 100.0)
    return breach, state


def _futures_equity():
    """Equity USDT du wallet futures (lecture seule). None si illisible."""
    try:
        import bitget_balance_reader as br
        from numeric_utils import safe_float
        for r in (br.get_futures_accounts() or {}).get("data") or []:
            if str(r.get("marginCoin", "")).upper() == MARGIN_COIN:
                return safe_float(r.get("accountEquity") or r.get("usdtEquity")
                                  or r.get("available"))
    except Exception:
        pass
    return None


def _expo_spot_btc_usdt():
    """Valeur USDT de l'exposition BTC SPOT (BTC + wrappers décotés, mêmes tokens
    que la couverture carry). None si illisible. Lecture seule."""
    try:
        import bitget_balance_reader as br
        from numeric_utils import safe_float
        tokens = dict(_cfg("CARRY_COUVERTURE_TOKENS", {"BTC": 1.0, "BGBTC": 0.9}))
        quantite, vu = 0.0, False
        for r in (br.get_spot_assets() or {}).get("data") or []:
            coin = str(r.get("coin", "")).upper()
            if coin in tokens:
                vu = True
                quantite += ((safe_float(r.get("available")) or 0.0)
                             + (safe_float(r.get("frozen")) or 0.0)) * float(tokens[coin])
        if not vu:
            return None
        prix = _mark_price()
        return quantite * prix if prix else None
    except Exception:
        return None


def _book_equity():
    """Equity du LIVRE piloté = wallet futures + exposition BTC spot (la jambe longue
    des carrys). C'est la base du stop journalier depuis le cap carry 200 (décision
    propriétaire 03/07) : un short carry HEDGÉ par le spot ferait osciller l'equity
    futures seule (faux breach kill-switch sur tout BTC +6 %) alors que le livre
    couvert, lui, est stable. None si UNE composante est illisible (bases mélangées
    entre deux mesures = faux breach garanti — on préfère l'aveu d'aveuglement)."""
    fut = _futures_equity()
    expo = _expo_spot_btc_usdt()
    if fut is None or expo is None:
        return None
    return fut + expo


def _write_ledger(led):
    """Écriture ATOMIQUE du ledger (tmp + os.replace — audit P3 : un write direct
    concurrent scan/CLI pouvait laisser un JSON à moitié écrit sur le journal
    d'ARGENT RÉEL). Best-effort."""
    import os
    path = _ledger_path()
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass


def daily_loss_breach(now=None):
    """Stop de perte JOURNALIER réel : lit l'equity futures, compare à l'ouverture du
    jour (état persisté dans le ledger). Deux régimes distincts (audit P3) :
      • equity LISIBLE et stop franchi -> BREACH CONFIRMÉ : KILL-SWITCH armé + alerte
        (dédup 1/jour) ;
      • equity ILLISIBLE (blip API/réseau) -> True (on n'OUVRE pas à l'aveugle,
        fail-closed) mais SANS armer le kill-switch global — un raté de lecture
        horaire gelait toute la machine, accumulation spot comprise."""
    path = _ledger_path()
    try:
        led = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        led = {}
    ancien = led.get("daily_loss_state") or {}
    equity = _book_equity()                       # livre couvert (futures + expo BTC spot)
    breach, state = daily_loss_state_check(equity, led.get("daily_loss_state"), now=now)
    led["daily_loss_state"] = state
    if state.get("day") is not None and state.get("day") != ancien.get("day"):
        # journal d'EQUITY quotidien (une ligne par jour UTC, cap 400) : la courbe
        # qui tranchera la revue des caps — gratuite, le tripwire lit déjà l'equity.
        led.setdefault("equity_journal", []).append(
            {"day": state["day"], "open_equity": state.get("open_equity")})
        led["equity_journal"] = led["equity_journal"][-400:]
    confirme = breach and equity is not None and equity > 0 and state.get("open_equity")
    jour = int((time.time() if now is None else now) // 86400)
    deja_alerte = int(led.get("daily_loss_alert_day", -1) or -1) == jour
    if confirme and not deja_alerte:
        led["daily_loss_alert_day"] = jour            # dédup : une alerte par jour UTC
    _write_ledger(led)
    if confirme:
        try:
            (Path(__file__).resolve().parent / "KILL_SWITCH").touch()   # idempotent
        except Exception:
            pass
        if not deja_alerte:
            try:
                import telegram_notifier as tn
                tn.send_telegram("🛑 STOP PERTE JOURNALIER FUTURES franchi — kill-switch ARMÉ "
                                 "(plus aucun ordre réel). Lever : supprimer KILL_SWITCH.")
            except Exception:
                pass
    return breach


def journal_equity_point(now=None, min_interval_s=600, cap=2016):
    """Point d'équité INTRAJOURNALIÈRE du LIVRE dans le ledger (best-effort,
    throttlé ≥10 min, plafonné 2016 points ≈ 7 jours à 5 min). Appelé par la boucle
    auto à chaque cycle : avec 1 point/jour, la halte MDD (garde 6) raisonnait sur
    2 points — elle raisonne désormais sur une vraie courbe. True si écrit."""
    now = time.time() if now is None else now
    try:
        led = json.loads(_ledger_path().read_text(encoding="utf-8"))
    except Exception:
        led = {}
    pts = [p for p in led.get("equity_intraday", []) if isinstance(p, list) and len(p) == 2]
    if pts and (now - float(pts[-1][0])) < float(min_interval_s):
        return False
    eq = _book_equity()
    if not eq or eq <= 0:
        return False                              # illisible -> pas de faux point
    pts.append([int(now), round(float(eq), 6)])
    led["equity_intraday"] = pts[-int(cap):]
    _write_ledger(led)
    return True


def place_partial_tp(symbol, side, size_btc, price, runner=None):
    """TP PARTIEL (§82) : ordre LIMITE GTC de RÉDUCTION qui écrème une fraction de la
    position au premier objectif (TP1) — le TP/SL PRÉRÉGLÉ à l'ouverture couvre le
    reste (et si le SL ferme tout, l'ordre réduction devient caduc côté exchange).
    RÉDUCTION pure : n'ouvre jamais d'exposition (même exemption de caps que les
    reduce §45) ; kill-switch respecté ; sous les minima du contrat -> refus propre
    (c'est le « quand c'est possible ») ; échec journalisé, JAMAIS bloquant — le
    préréglé reste le filet."""
    from numeric_utils import safe_float
    symbol = str(symbol or SYMBOL).upper()
    if (Path(__file__).resolve().parent / "KILL_SWITCH").exists():
        return {"ok": False, "executed": False, "reasons": ["kill-switch actif"]}
    spec = _contract_spec(symbol)
    px = safe_float(price)
    size = safe_float(size_btc)
    if not spec or not px or px <= 0 or not size or size <= 0:
        return {"ok": False, "executed": False, "reasons": ["spec/prix/taille illisibles"]}
    step = safe_float(spec.get("step")) or 0.0001
    mini = safe_float(spec.get("min_size")) or step
    vol_place = int(safe_float(spec.get("vol_place")) or 4)
    price_place = int(safe_float(spec.get("price_place")) or 1)
    size = round(int(size / step) * step, vol_place)
    if size < mini:
        return {"ok": False, "executed": False,
                "reasons": [f"tranche TP1 {size} sous le minimum {mini} (partiel impossible)"]}
    marge_mode = _marge_mode()
    pos_mode = resolve_pos_mode(positions_ouvertes(), _cfg("FUTURES_POSITION_MODE", "hedge_mode"))
    long_ = str(side) == "long"
    o = {"symbol": symbol, "productType": PRODUCT_TYPE, "marginCoin": MARGIN_COIN,
         "marginMode": str(marge_mode or "isolated"),
         "size": f"{size:.{vol_place}f}",
         "orderType": "limit", "force": "gtc",
         "price": f"{round(px, price_place):.{price_place}f}",
         "clientOid": f"tp1{int(time.time() * 1000)}"}
    if str(pos_mode) == "hedge_mode":
        o["side"] = "buy" if long_ else "sell"        # côté de la POSITION à réduire
        o["tradeSide"] = "close"
    else:
        o["side"] = "sell" if long_ else "buy"
        o["reduceOnly"] = "YES"
    out = _run(["futures", "futures_place_order", "--orders", json.dumps([o])], runner=runner)
    compact = (out or "").replace(" ", "").lower()
    ok = bool(out) and '"ok":false' not in compact and "error" not in compact
    _journal({"ts": int(time.time()), "action": "FUTURES_TP_PARTIAL",
              "order": {"symbol": symbol, "side": side, "size_btc": size,
                        "price": round(px, price_place), "clientOid": o["clientOid"]},
              "ok": ok, "response": str(out)[:300]})
    return {"ok": ok, "executed": ok, "clientOid": o["clientOid"], "response": out}


def drawdown_status():
    """État LECTURE SEULE de la halte drawdown (garde 6) : {halt, dd_pct, max_dd_pct,
    peak, equity, n_points}. Best-effort ({} si illisible) — consommé par
    futures_report et futures_auto --status pour que la halte soit VISIBLE (une
    halte silencieuse laissait croire que la boucle allait ouvrir alors que chaque
    tentative était refusée)."""
    try:
        import mandate
        curve = equity_curve()
        halt, dd_pct = mandate.drawdown_halt(curve)
        return {"halt": bool(halt), "dd_pct": dd_pct,
                "max_dd_pct": float(_cfg("MANDATE_MAX_DRAWDOWN_PCT", 20.0)),
                "peak": round(max(curve), 2) if curve else None,
                "equity": round(curve[-1], 2) if curve else None,
                "n_points": len(curve)}
    except Exception:
        return {}


def rebase_equity(confirm=False, now=None):
    """OUTIL PROPRIÉTAIRE : réancre la courbe d'equity intrajournalière APRÈS un
    mouvement de capital délibéré (dépôt/retrait/virement hors du livre piloté).

    Pourquoi : la garde 6 (halte MDD) mesure le drawdown du LIVRE (wallet futures +
    expo BTC spot). Un retrait légitime y est indistinguable d'une perte -> halte
    « fantôme » qui ne se lève pas d'elle-même (le pic reste ~7 j dans la fenêtre
    intrajournalière, même si les fonds reviennent). Constaté le 05/07 : equity
    402 -> 240 par mouvement de capital (PnL bot −0.10 $), halte 40 % permanente.

    Ce réancrage est une DÉCISION PROPRIÉTAIRE EXPLICITE (--confirm obligatoire,
    DRY sinon) : il repart la courbe du point courant. Il ne desserre AUCUN mur
    (caps 50/250, levier ×5, stop journalier, kill-switch, porte d'edge intacts)
    et JOURNALISE l'état remplacé (pic, dd, n points) dans le ledger — traçable.
    Refus si l'equity du livre est illisible (fail-closed)."""
    now = time.time() if now is None else now
    avant = drawdown_status()
    eq = _book_equity()
    if eq is None or eq <= 0:
        return {"ok": False, "avant": avant,
                "raison": "equity du livre illisible — réancrage refusé (fail-closed)"}
    if not confirm:
        return {"ok": True, "dry": True, "avant": avant, "equity_livre": round(float(eq), 2),
                "note": "préview — relancer avec --confirm pour réancrer la courbe"}
    try:
        led = json.loads(_ledger_path().read_text(encoding="utf-8"))
    except Exception:
        led = {}
    led["equity_intraday"] = [[int(now), round(float(eq), 6)]]
    _write_ledger(led)
    _journal({"ts": int(now), "action": "FUTURES_EQUITY_REBASE", "avant": avant,
              "equity_livre": round(float(eq), 6),
              "note": "réancrage propriétaire après mouvement de capital"})
    return {"ok": True, "dry": False, "avant": avant, "apres": drawdown_status(),
            "equity_livre": round(float(eq), 2)}


def equity_curve():
    """Courbe d'equity du LIVRE : points INTRAJOURNALIERS (equity_intraday, écrits
    par la boucle via journal_equity_point) sinon repli sur les ouvertures
    JOURNALIÈRES (equity_journal, écrites par le tripwire) ; + point courant.
    Alimente la HALTE DRAWDOWN du mandat (garde 6) sur le chemin réel. [] si rien
    (pas de halte sans historique : la protection grandit avec les points)."""
    try:
        led = json.loads(_ledger_path().read_text(encoding="utf-8"))
    except Exception:
        led = {}
    from numeric_utils import safe_float
    pts = [safe_float(p[1]) for p in led.get("equity_intraday", [])
           if isinstance(p, list) and len(p) == 2]
    pts = [p for p in pts if p and p > 0]
    if not pts:                                   # repli : journal quotidien (1 pt/jour)
        pts = [safe_float(r.get("open_equity")) for r in led.get("equity_journal", [])
               if isinstance(r, dict)]
        pts = [p for p in pts if p and p > 0]
    eq = _book_equity()                           # même base que le journal (livre couvert)
    if eq:
        pts.append(eq)
    return pts


# ---------- mode de marge ADAPTATIF (union -> crossed forcé) ----------

def resolve_marge_mode(mode_cfg, asset_mode):
    """PUR. Mode de marge EFFECTIF : en mode multi-devises (assetMode 'union'),
    Bitget INTERDIT l'isolé (« currencies mixed » -> HTTP 400) — on force 'crossed'.
    Compte en mode mono-devise (ou illisible) -> le mode configuré (défaut isolé :
    perte max d'une position = sa marge)."""
    if str(asset_mode or "").lower() == "union":
        return "crossed"
    return str(mode_cfg or "isolated")


def _asset_mode():
    """assetMode du compte futures ('union'/'single'), caché 1h. None si illisible."""
    def _fetch():
        import bitget_balance_reader as br
        for r in (br.get_futures_accounts() or {}).get("data") or []:
            if str(r.get("marginCoin", "")).upper() == MARGIN_COIN:
                return r.get("assetMode")
        return None
    try:
        import runtime_cache as rc
        return rc.get("fut_asset_mode", 3600, _fetch, fallback=None)
    except Exception:
        return None


def _marge_mode():
    """Mode de marge effectif du moment (adaptatif au réglage du compte)."""
    return resolve_marge_mode(_cfg("FUTURES_MARGIN_MODE", "isolated"), _asset_mode())


# ---------- mapping vers l'API Bitget v2 (purs) ----------

def size_for(notional_usdt, price, spec):
    """PUR. Taille en BTC : notional/prix, arrondie VERS LE BAS au pas du contrat.
    None si spec/prix illisibles, sous la taille minimale ou sous le notional minimal
    (on n'envoie jamais un ordre que l'exchange rejetterait ou gonflerait)."""
    from numeric_utils import safe_float
    notional, price = safe_float(notional_usdt), safe_float(price)
    if not spec or notional is None or price is None or price <= 0 or notional <= 0:
        return None
    step = safe_float(spec.get("step")) or 0.0001
    mini = safe_float(spec.get("min_size")) or step
    min_usdt = safe_float(spec.get("min_usdt")) or 5.0
    vol_place = int(safe_float(spec.get("vol_place")) or 4)
    brut = notional / price
    size = int(brut / step) * step                # arrondi VERS LE BAS au pas
    size = round(size, vol_place)
    if size < mini or size * price < min_usdt:
        return None
    return size


def to_bitget_order(order, spec, price, marge_mode=None, pos_mode=None):
    """PUR. Demande bornée -> ordre API Bitget v2, au FORMAT DU MODE DE POSITION :
      • hedge_mode (cible depuis le 03/07 — long ET short simultanés) : side = côté
        de la POSITION (buy=long, sell=short, convention Bitget), tradeSide
        open/close, pas de reduceOnly ;
      • one_way_mode (transitoire tant qu'une position historique est ouverte) :
        side = direction d'exécution + reduceOnly YES/NO.
    Ouvertures en limit IOC plafonné (anti-slippage), RÉDUCTIONS en market ;
    marge selon `marge_mode` (crossed forcé en compte multi-devises) ; TP/SL
    préréglés au tick. None si la taille est infaisable (sous les minima)."""
    from numeric_utils import safe_float
    reduce = bool(order.get("reduce"))
    explicite = safe_float(order.get("size_btc")) if reduce else None
    if explicite is not None and explicite > 0:
        # fermeture à taille EXACTE : reduceOnly borne à la position côté exchange,
        # on relève au minimum du contrat pour que même une poussière soit fermable.
        mini = safe_float((spec or {}).get("min_size")) or 0.0001
        size = max(explicite, mini)
    else:
        size = size_for(order.get("notional_usdt"), price, spec)
    if size is None:
        return None
    long_ = str(order.get("side")) == "long"
    vol_place = int((spec or {}).get("vol_place") or 4)
    price_place = int((spec or {}).get("price_place") or 1)
    o = {"symbol": str(order.get("symbol") or SYMBOL).upper(),
         "productType": PRODUCT_TYPE, "marginCoin": MARGIN_COIN,
         "marginMode": str(marge_mode or _cfg("FUTURES_MARGIN_MODE", "isolated")),
         "size": f"{size:.{vol_place}f}"}
    pm = str(pos_mode or _cfg("FUTURES_POSITION_MODE", "hedge_mode"))
    if pm == "hedge_mode":
        o["side"] = "buy" if long_ else "sell"        # côté de la POSITION (convention Bitget)
        o["tradeSide"] = "close" if reduce else "open"
        side_exec = o["side"]                          # ouverture : buy exécute achat, sell exécute vente
    else:
        side_exec = ("sell" if long_ else "buy") if reduce else ("buy" if long_ else "sell")
        o["side"] = side_exec
        o["reduceOnly"] = "YES" if reduce else "NO"
    # style d'exécution (parité avec spot_executor, audit « plein potentiel ») :
    #   • OUVERTURE en limit IOC plafonné à ±tol% du prix : remplit immédiatement
    #     comme un market mais JAMAIS au-delà du plafond (anti-slippage borné ;
    #     remplissage partiel possible = risque réduit, jamais aggravé) ;
    #   • RÉDUCTION en market : la sortie doit TOUJOURS réussir.
    style = str(_cfg("FUTURES_EXEC_STYLE", "limit_ioc")).lower()
    if not reduce and style == "limit_ioc" and safe_float(price):
        tol = float(_cfg("FUTURES_SLIPPAGE_TOL_PCT", 0.10)) / 100.0
        cap = float(price) * (1.0 + tol) if side_exec == "buy" else float(price) * (1.0 - tol)
        o["orderType"] = "limit"
        o["force"] = "ioc"
        o["price"] = f"{round(cap, price_place):.{price_place}f}"
    else:
        o["orderType"] = "market"
    if order.get("clientOid"):
        o["clientOid"] = str(order["clientOid"])
    if not reduce:                                # TP/SL préréglés à l'ouverture seulement
        if order.get("take_profit") is not None:
            o["presetStopSurplusPrice"] = f"{round(float(order['take_profit']), price_place):.{price_place}f}"
        if order.get("stop_loss") is not None:
            o["presetStopLossPrice"] = f"{round(float(order['stop_loss']), price_place):.{price_place}f}"
    return o


# ---------- lectures marché (best-effort, cachées) ----------

def _contract_spec(symbol=None):
    """Spécifications du contrat (pas, minima, décimales), PAR SYMBOLE. None si illisible."""
    symbol = str(symbol or SYMBOL).upper()
    def _fetch():
        import bitget_hub_bridge as hub
        from numeric_utils import safe_float
        d = hub._read(["futures", "futures_get_contracts", "--productType", PRODUCT_TYPE,
                       "--symbol", symbol])
        rows = (d or {}).get("data") or []
        r = rows[0] if rows else {}
        if not r:
            return None
        return {"min_size": safe_float(r.get("minTradeNum")),
                "step": safe_float(r.get("sizeMultiplier")),
                "vol_place": int(safe_float(r.get("volumePlace")) or 4),
                "price_place": int(safe_float(r.get("pricePlace")) or 1),
                "min_usdt": safe_float(r.get("minTradeUSDT"))}
    try:
        import runtime_cache as rc
        return rc.get(f"fut_contract_spec:{symbol}", 86400, _fetch, fallback=None)
    except Exception:
        return None


def _mark_price(symbol=None):
    """Dernier prix d'un perp (lecture seule). None si illisible."""
    try:
        import bitget_hub_bridge as hub
        from numeric_utils import safe_float
        d = hub._read(["futures", "futures_get_ticker", "--productType", PRODUCT_TYPE,
                       "--symbol", str(symbol or SYMBOL).upper()])
        rows = (d or {}).get("data") or []
        r = rows[0] if rows else {}
        return safe_float(r.get("lastPr") or r.get("markPrice") or r.get("last"))
    except Exception:
        return None


def _top_of_book(symbol=None):
    """Meilleur bid/ask + TAILLES du perp (MÊME ticker que _mark_price, aucune requête en
    plus). Sert de plafond de liquidité (§98). Lecture seule, best-effort -> None si illisible
    (fail-open : pas de cap). Gardé par hub.available() (hermétique hors-ligne / tests)."""
    try:
        import bitget_hub_bridge as hub
        from numeric_utils import safe_float
        if not hub.available():
            return None
        d = hub._read(["futures", "futures_get_ticker", "--productType", PRODUCT_TYPE,
                       "--symbol", str(symbol or SYMBOL).upper()])
        rows = (d or {}).get("data") or []
        r = rows[0] if rows else {}
        bid, ask = safe_float(r.get("bidPr")), safe_float(r.get("askPr"))
        if bid and ask and bid > 0 and ask > 0:
            return {"bid": bid, "ask": ask,
                    "bid_size": safe_float(r.get("bidSz")) or 0.0,
                    "ask_size": safe_float(r.get("askSz")) or 0.0}
    except Exception:
        pass
    return None


# ---------- exécution RÉELLE (étape 2, §45) ----------

def _run(cmd, runner=None):
    """Lance la commande bgc d'ÉCRITURE (sans --read-only). runner injectable (tests)."""
    if runner is not None:
        return runner(cmd)
    try:
        import bitget_hub_bridge as hub
        if not hub.available():
            return None
        import subprocess
        p = subprocess.run(["bgc", *cmd], capture_output=True, text=True,
                           timeout=30, env=hub._hub_env())
        return ((p.stdout or "") + (p.stderr or "")).strip() or None
    except Exception:
        return None


_POS_MODE_MEMO = {"ts": 0.0, "mode": None}


def positions_ouvertes(runner=None, symbol=None):
    """Lignes de positions ouvertes (lecture seule) — TOUS les symboles par défaut
    (multi-symbole §47), filtre optionnel. None si illisible."""
    try:
        import bitget_hub_bridge as hub
        d = hub._read(["futures", "futures_get_positions", "--productType", PRODUCT_TYPE])
        rows = (d or {}).get("data")
        if rows is None:
            return None
        if symbol:
            return [r for r in rows if str(r.get("symbol", "")).upper() == str(symbol).upper()]
        return rows
    except Exception:
        return None


def resolve_pos_mode(rows_positions, mode_cfg):
    """PUR. Mode de position EFFECTIF : une position OUVERTE fait AUTORITÉ (Bitget
    refuse de changer de mode en position — son posMode est la seule vérité) ;
    à plat -> le mode CIBLE configuré (hedge_mode depuis la décision du 03/07)."""
    for r in rows_positions or []:
        pm = str((r or {}).get("posMode") or "")
        if pm in ("one_way_mode", "hedge_mode"):
            return pm
    return str(mode_cfg or "hedge_mode")


def _ensure_position_mode(runner=None, rows=None):
    """Aligne le compte sur le mode de position EFFECTIF (resolve_pos_mode) :
    à plat, bascule vers le mode cible (hedge_mode — déclaré par le propriétaire
    03/07, permet carry ET directionnel simultanés) ; en position, AUCUN appel de
    bascule (l'exchange refuserait : on formate les ordres au mode de la position).
    Retourne le mode effectif, ou None si l'alignement échoue (fail-closed).
    `rows` injectable (tests) ; avec runner injecté et rows omis -> à plat."""
    cible = str(_cfg("FUTURES_POSITION_MODE", "hedge_mode"))
    if runner is None and time.time() - _POS_MODE_MEMO["ts"] < 3600 and _POS_MODE_MEMO["mode"]:
        return _POS_MODE_MEMO["mode"]
    if rows is None:
        rows = positions_ouvertes() if runner is None else []
    if rows is None:
        return None                                  # positions illisibles -> pas d'ordre
    effectif = resolve_pos_mode(rows, cible)
    if rows:                                         # en position : pas de bascule possible
        if runner is None:
            _POS_MODE_MEMO.update(ts=0.0, mode=None)  # re-résoudre à chaque ordre
        return effectif
    out = _run(["futures", "futures_update_config", "--setting", "positionMode",
                "--value", effectif, "--symbol", SYMBOL,
                "--productType", PRODUCT_TYPE, "--marginCoin", MARGIN_COIN],
               runner=runner)
    compact = (out or "").replace(" ", "").lower()
    ok = bool(out) and "error" not in compact and '"ok":false' not in compact
    if not ok:
        return None
    if runner is None:
        _POS_MODE_MEMO.update(ts=time.time(), mode=effectif)
    return effectif


def _ensure_leverage(leverage, runner=None, marge_mode=None, symbol=None):
    """Fixe le levier (déjà borné au mur par build_futures_order) AVANT l'ordre.
    Marge isolée : les deux holdSide ; crossed : un appel sans holdSide.
    Fail-closed : échec -> False (pas d'ordre)."""
    lev = str(int(max(1, round(float(leverage)))))
    mode = str(marge_mode or _cfg("FUTURES_MARGIN_MODE", "isolated"))
    sides = ["long", "short"] if mode == "isolated" else [None]
    for hs in sides:
        cmd = ["futures", "futures_set_leverage", "--symbol", str(symbol or SYMBOL).upper(),
               "--productType", PRODUCT_TYPE, "--marginCoin", MARGIN_COIN,
               "--leverage", lev]
        if hs:
            cmd += ["--holdSide", hs]
        out = _run(cmd, runner=runner)
        compact = (out or "").replace(" ", "").lower()
        if not out or "error" in compact or '"ok":false' in compact:
            return False
    return True


def _place_real(order, runner=None, spec=None, price=None, marge_mode=None, pos_mode=None):
    """Chemin RÉEL (étape 2, §45). Résout le mode de position EFFECTIF (position
    ouverte = autorité ; à plat = bascule vers la cible hedge_mode, décision 03/07),
    mappe la demande au format de CE mode, fixe le levier borné, exécute via l'Agent
    Hub. FAIL-CLOSED à chaque étape illisible. Retourne un dict."""
    symbole = str(order.get("symbol") or SYMBOL).upper()
    spec = _contract_spec(symbole) if spec is None else spec
    if not spec:
        return {"ok": False, "executed": False,
                "reasons": ["spécifications contrat illisibles (fail-closed)"]}
    price = (order.get("entry") or _mark_price(symbole)) if price is None else price
    if not price:
        return {"ok": False, "executed": False,
                "reasons": ["prix du perp illisible (fail-closed)"]}
    marge_mode = _marge_mode() if marge_mode is None else marge_mode   # adaptatif : union -> crossed
    if pos_mode is None:
        pos_mode = _ensure_position_mode(runner=runner)                # adaptatif + bascule à plat
    if pos_mode is None:
        return {"ok": False, "executed": False,
                "reasons": ["mode de position irrésoluble/refusé (fail-closed)"]}
    bo = to_bitget_order(order, spec, price, marge_mode=marge_mode, pos_mode=pos_mode)
    if bo is None:
        return {"ok": False, "executed": False,
                "reasons": [f"taille infaisable (notional {order.get('notional_usdt')} "
                            "sous les minima du contrat)"]}
    if not _ensure_leverage(order.get("leverage") or 1, runner=runner, marge_mode=marge_mode,
                            symbol=symbole):
        return {"ok": False, "executed": False,
                "reasons": ["réglage du levier refusé par l'exchange (fail-closed)"]}
    out = _run(["futures", "futures_place_order", "--orders", json.dumps([bo])], runner=runner)
    compact = (out or "").replace(" ", "").lower()
    success = (bool(out) and '"ok":false' not in compact and "error" not in compact
               and ("orderid" in compact or '"data"' in compact))
    return {"ok": True, "executed": success, "bitget_order": bo,
            "response": (out or "")[:2000], "clientOid": order.get("clientOid")}


def execute(agent, side, notional_usdt, leverage, entry=None, stop_loss=None,
            take_profit=None, *, reduce=False, confirm=False, runner=None, now=None,
            equity_curve=None, gross_open_usdt=0.0, seen_oids=None, hour_utc=None,
            macro_events=None, journal=True, daily_loss=None, spec=None, price=None,
            marge_mode=None, size_btc=None, pos_mode=None, symbol=None,
            top_of_book=None, **gate_overrides):
    """Ordre futures RÉEL SI confirm=True ET les 8 gardes passent ET le stop de perte
    journalier n'est pas franchi. Sinon DRY (construit, journalise, n'exécute rien).
    Retourne un dict de résultat. gate_overrides (live/autonomous/futures_live/kill/
    edge_override) + daily_loss/spec/price injectables (tests hermétiques)."""
    now = time.time() if now is None else now
    oid = f"fut{str(agent)[:3]}{int(now * 1000)}"
    # §98 : cap de LIQUIDITÉ sur les OUVERTURES — ne pas balayer plus que le top-of-book affiché
    # (thin alts : LAB/HYPE/BGB). Réservé à reduce=False (une fermeture doit rester entière).
    # AVANT guards() -> les caps durs voient le notionnel déjà réduit. Fail-open (pas de carnet
    # -> inchangé). Le carnet est FOURNI par l'appelant (futures_auto lit fe._top_of_book à côté
    # de _mark_price) : execute() ne déclenche aucune requête réseau lui-même -> tests hermétiques.
    notional_capped_from = None
    if not reduce and top_of_book is not None:
        capped, binds = liquidity_capped_notional(notional_usdt, side, top_of_book)
        if binds:
            notional_capped_from, notional_usdt = float(notional_usdt), capped
    ok, reasons = guards(agent, notional_usdt, leverage, equity_curve=equity_curve,
                         gross_open_usdt=gross_open_usdt, client_oid=oid, seen_oids=seen_oids,
                         hour_utc=hour_utc, macro_events=macro_events, now=now,
                         reduce=reduce, **gate_overrides)
    order = build_futures_order(agent, side, notional_usdt, leverage, entry, stop_loss,
                                take_profit, oid, reduce=reduce, size_btc=size_btc,
                                symbol=symbol)
    if notional_capped_from is not None:          # trace : le cap de liquidité a mordu
        order["liquidity_capped_from"] = round(notional_capped_from, 2)
    mode = order.get("execution_mode")
    preview = (f"futures {order['side']}{' reduce' if order['reduce'] else ''} "
               f"{order['notional_usdt']}USDT x{order['leverage']} "
               f"agent={agent} oid={oid} [{mode}]")

    if not ok:
        if journal:
            _journal({"action": "FUTURES_REFUSED", "ts": now, "order": order,
                      "reasons": reasons, "real_order_sent": False})
        return {"ok": False, "executed": False, "reasons": reasons,
                "preview": preview, "clientOid": oid}

    if not confirm:
        if journal:
            _journal({"action": "FUTURES_DRY_RUN", "ts": now, "order": order,
                      "real_order_sent": False})
        return {"ok": True, "executed": False, "dry": True, "preview": preview,
                "clientOid": oid,
                "note": "DRY — ajouter confirm=True pour le RÉEL (gardes + stop journalier)."}

    # confirm=True ET gardes passées : PRÉ-VOL stop de perte journalier (fail-closed),
    # puis chemin RÉEL (étape 2, §45). L'ouverture est bloquée après breach ; une
    # RÉDUCTION reste permise (fermer une position n'aggrave jamais le risque).
    if daily_loss is None and not reduce:
        daily_loss = daily_loss_breach(now=now)
    if daily_loss and not reduce:
        if journal:
            _journal({"action": "FUTURES_REFUSED", "ts": now, "order": order,
                      "reasons": ["stop de perte journalier franchi"], "real_order_sent": False})
        return {"ok": False, "executed": False, "preview": preview, "clientOid": oid,
                "reasons": ["stop de perte journalier franchi (kill-switch armé)"]}
    res = _place_real(order, runner=runner, spec=spec, price=price, marge_mode=marge_mode,
                      pos_mode=pos_mode)
    if journal:
        _journal({"action": "FUTURES_REAL" if res.get("executed") else "FUTURES_REAL_FAILED",
                  "ts": now, "order": order, "bitget_order": res.get("bitget_order"),
                  "real_order_sent": bool(res.get("executed")),
                  "reasons": res.get("reasons"), "response": res.get("response")})
    return {**res, "preview": preview, "clientOid": oid}


# ---------- ENFORCEUR de stop (Couche 2, indépendant de brain/scan) ----------

def flatten_all(runner=None, now=None, motif="stop journalier"):
    """SOLDE toutes les positions futures ouvertes en RÉDUCTION market (reduceOnly).
    Fail-safe : fermer n'aggrave JAMAIS le risque — un flatten de sécurité ne dépend
    d'AUCUN verrou d'OUVERTURE (double verrou, porte d'edge, kill-switch) : on passe
    les overrides pour qu'une réduction reste TOUJOURS exécutable, même mandat coupé.

    Idempotent (à plat -> aucun ordre). Fail-closed par position : une ligne illisible
    n'empêche pas de solder les autres. Retourne un récapitulatif (aucun secret)."""
    now = time.time() if now is None else now
    from numeric_utils import safe_float
    rows = positions_ouvertes(runner=runner)
    if rows is None:
        return {"lisible": False, "tentees": 0, "soldees": 0, "positions": [],
                "erreurs": ["positions illisibles (fail-closed) — nouvelle tentative au prochain tick"]}
    recap = {"lisible": True, "motif": str(motif), "tentees": 0, "soldees": 0,
             "positions": [], "erreurs": []}
    for r in rows:
        if not isinstance(r, dict):
            continue
        cote = str(r.get("holdSide", "")).lower()
        taille = safe_float(r.get("total") or r.get("size")) or 0.0
        symbole = str(r.get("symbol", "")).upper()
        if cote not in ("long", "short") or taille <= 1e-12 or not symbole:
            continue
        prix = safe_float(r.get("markPrice")) or _mark_price(symbole)
        notional = round(taille * prix, 2) if prix and prix > 0 else 1.0
        if notional <= 0:
            notional = 1.0
        recap["tentees"] += 1
        try:
            res = execute("guardian", cote, notional, 1.0, reduce=True, confirm=True,
                          now=now, size_btc=taille, symbol=symbole, runner=runner,
                          live=True, autonomous=True, futures_live=True, edge_override=1,
                          kill=False)
            ok = bool(res.get("executed"))
            recap["positions"].append({"symbol": symbole, "side": cote,
                                       "size": round(taille, 6), "executed": ok})
            if ok:
                recap["soldees"] += 1
            else:
                recap["erreurs"].append(f"{cote} {symbole}: {res.get('reasons') or 'échec exchange'}")
        except Exception as exc:
            recap["erreurs"].append(f"{cote} {symbole}: {type(exc).__name__}")
    return recap


def enforce_daily_loss(runner=None, now=None):
    """ENFORCEUR complet du stop journalier −5 % (Couche 2). Appelé par un organe
    INDÉPENDANT de brain/scan (stop_guardian) à cadence serrée :
      1) daily_loss_breach() : arme le kill-switch + alerte Telegram (dédup 1/jour),
         persiste l'état — inchangé ;
      2) si le breach est CONFIRMÉ (equity LISIBLE sous le seuil, signalé par
         daily_loss_alert_day == jour dans le ledger), SOLDE toutes les positions.
         Un breach 'aveugle' (API illisible) NE solde RIEN (jamais de fermeture sur
         un simple blip de lecture ; fail-closed = on n'OUVRE pas, pas on ne ferme).
    Retourne {breach, confirme, flatten}."""
    now = time.time() if now is None else now
    breach = daily_loss_breach(now=now)               # effets protecteurs (kill-switch + alerte)
    jour = int(now // 86400)
    try:
        led = json.loads(_ledger_path().read_text(encoding="utf-8"))
    except Exception:
        led = {}
    confirme = int(led.get("daily_loss_alert_day", -1) or -1) == jour
    recap = {"breach": bool(breach), "confirme": bool(confirme), "flatten": None}
    if confirme:
        recap["flatten"] = flatten_all(runner=runner, now=now, motif="stop journalier -5%")
    return recap


def opens_sans_stop(events=None, agents_directionnels=("auto_dir", "directional", "dir")):
    """PUR (si events injecté). Ouvertures RÉELLES directionnelles passées SANS
    stop-loss préréglé côté exchange (invariant Couche 1). Le carry est exclu :
    short volontairement couvert par le spot (sans SL, protégé par le stop du LIVRE).
    Retourne [{ts, agent, symbol, oid}] — [] = tout ordre directionnel portait son SL."""
    if events is None:
        try:
            events = json.loads(_ledger_path().read_text(encoding="utf-8")).get("events", [])
        except Exception:
            events = []
    nus = []
    for e in events or []:
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        order = e.get("order") or {}
        if order.get("reduce"):
            continue                                  # une réduction n'a pas à porter de SL
        agent = str(order.get("agent", ""))
        if not any(agent.startswith(a) for a in agents_directionnels):
            continue                                  # carry/autres : hors invariant
        if order.get("stop_loss") is None:
            nus.append({"ts": e.get("ts"), "agent": agent,
                        "symbol": order.get("symbol"), "oid": order.get("clientOid")})
    return nus


def main():
    import argparse
    p = argparse.ArgumentParser(description="Ordre futures RÉEL borné (étape 2, §45).")
    p.add_argument("--agent", default="carry", help="origine de l'ordre (agent/stratégie)")
    p.add_argument("--side", default="long", choices=["long", "short"], help="sens")
    p.add_argument("--reduce", action="store_true", help="réduit/ferme au lieu d'ouvrir")
    p.add_argument("--usdt", type=float, default=10.0, help="notional en USDT")
    p.add_argument("--leverage", type=float, default=2.0, help="levier (clampé au mur ×5)")
    p.add_argument("--entry", type=float, help="prix d'entrée (optionnel)")
    p.add_argument("--sl", type=float, help="stop loss (optionnel)")
    p.add_argument("--tp", type=float, help="take profit (optionnel)")
    p.add_argument("--confirm", action="store_true",
                   help="exécute le VRAI ordre (sinon DRY : preview seulement)")
    p.add_argument("--rebase-equity", action="store_true",
                   help="OUTIL PROPRIÉTAIRE : réancre la courbe d'equity après un "
                        "mouvement de capital (halte MDD fantôme). DRY sans --confirm.")
    args = p.parse_args()

    if args.rebase_equity:
        print("=== RÉANCRAGE EQUITY (halte MDD, garde 6) — décision propriétaire ===")
        r = rebase_equity(confirm=args.confirm)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        if r.get("dry"):
            print("Mode DRY — rien n'a été modifié. Ajouter --confirm pour réancrer.")
        elif r.get("ok"):
            print("✅ Courbe réancrée. La garde 6 repart du point courant (murs intacts).")
        return

    print("=== ORDRE FUTURES RÉEL BORNÉ (étape 2, §45) ===")
    r = execute(args.agent, args.side, args.usdt, args.leverage, args.entry,
                args.sl, args.tp, reduce=args.reduce, confirm=args.confirm)
    print(f"Preview : {r.get('preview')}")
    if not r.get("ok"):
        print("REFUSÉ : " + " ; ".join(r.get("reasons", [])))
    elif r.get("dry"):
        print("Mode DRY — aucun ordre passé. " + r.get("note", ""))
    elif r.get("executed"):
        print(f"✅ ORDRE RÉEL exécuté (clientOid {r.get('clientOid')}).")
        print(f"Réponse : {str(r.get('response'))[:400]}")
    else:
        print(f"⚠️ Échec d'exécution : {r.get('reasons') or str(r.get('response'))[:400]}")
    print("Périmètre : futures borné (murs 50/trade · 250 cumulé · stop journalier -> kill-switch).")


if __name__ == "__main__":
    main()
