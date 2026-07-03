"""
dashboard/server.py — dashboard web LECTURE SEULE (stdlib uniquement).

Classement : SAFE.
  - sert un tableau de bord HTML + un endpoint JSON /api/state
  - agrège des données read-only (stats, order-flow Bitget, macro, santé)
  - aucun ordre, aucun secret, aucune écriture de trading

Dépendances : bibliothèque standard Python seulement (http.server).
Les modules data (bitget_market_data, macro_context...) sont importés
paresseusement et de façon défensive : le dashboard démarre même si une
source est indisponible.

Lancement :
    python dashboard/server.py
Config (env) :
    DASH_HOST (défaut 127.0.0.1)   DASH_PORT (défaut 8787)
    DASH_SYMBOL (défaut BTCUSDT)
Voir dashboard/DEPLOY.md pour le déploiement VPS (SSH tunnel / nginx + ufw).
"""

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

STATIC_DIR = Path(__file__).resolve().parent
# La racine du repo (parent de dashboard/) doit être importable : les modules
# data (config, stats_report, ...) y vivent. Sinon `import config` échoue
# quand on lance `python dashboard/server.py`.
REPO_ROOT = STATIC_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_SYMBOL = os.getenv("DASH_SYMBOL", "BTCUSDT")
HOST = os.getenv("DASH_HOST", "127.0.0.1")
PORT = int(os.getenv("DASH_PORT", "8787"))

_CACHE = {}


def _cached(key, ttl, producer):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = producer()
    _CACHE[key] = (now, value)
    return value


def _safe(producer, default=None):
    try:
        return producer()
    except Exception:
        return default


def _num(value, default=None):
    """Convertit en float de façon défensive (None/'' -> default)."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def enrich_positions(positions, prices):
    """Ajoute prix courant + PnL % à chaque position (fonction pure, testable).
    Prix courant = prix live du symbole, repli sur last_close. PnL signé selon le sens."""
    prices = prices or {}
    out = []
    for p in positions or []:
        q = dict(p)
        entry = p.get("entry")
        cur = prices.get(p.get("symbol")) or p.get("last_close")
        q["current_price"] = cur
        pnl = None
        if entry and cur:
            chg = (cur - entry) / entry * 100.0
            pnl = chg if p.get("side") == "LONG" else -chg
        q["pnl_pct"] = round(pnl, 3) if pnl is not None else None
        out.append(q)
    # perdantes d'abord (PnL croissant), valeurs inconnues en fin
    out.sort(key=lambda x: (x.get("pnl_pct") is None, x.get("pnl_pct") if x.get("pnl_pct") is not None else 0.0))
    return out


def _count_csv(path):
    p = Path(path)
    if not p.exists():
        return 0
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        return max(sum(1 for _ in f) - 1, 0)


def edge_summary(rep):
    """Résumé de l'échelle d'edge pour le dashboard (fonction pure, testable) :
    paliers + « proche LIVE » + priors EARCP + provenance du ranking (§41)."""
    import edge_ladder as el
    rep = rep or {}
    pending = [r.get("agent") for r in rep.get("ranking", [])
               if el.live_pending(r, el._live_row(rep, r.get("agent")))]
    top = [{"agent": r.get("agent"), "dsr": r.get("dsr"), "n": r.get("n")}
           for r in rep.get("ranking", [])[:6]]
    return {"tiers": el.all_tiers(rep), "pending": pending,
            "priors": el.weight_priors(rep), "mode": rep.get("ranking_mode"),
            "n_symbols": rep.get("n_symbols"), "top": top}


def assemble_state(symbol, symbols, stats, orderflow, macro, health, market=None, candles=None, orderbook=None, brain=None, liquidations=None, positions=None):
    """Assemble l'état du dashboard (fonction pure, testable)."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "PAPER / DRY-RUN",
        "symbol": symbol,
        "symbols": list(symbols or []),
        "stats": stats or {},
        "orderflow": orderflow,
        "macro": macro,
        "market": market or {},
        "health": health or {},
        "candles": candles or [],
        "orderbook": orderbook or {"bids": [], "asks": []},
        "brain": brain or {},
        "liquidations": liquidations or {},
        "positions": positions or [],
    }


ALLOWED_TF = ("5m", "15m", "1h")


def build_state(symbol=None, tf="5m"):
    symbol = symbol or DEFAULT_SYMBOL
    tf = tf if tf in ALLOWED_TF else "5m"

    def _stats():
        import stats_report
        return stats_report.compute_stats(stats_report.load_rows())

    def _orderflow():
        import bitget_market_data
        return bitget_market_data.market_snapshot(symbol)

    def _macro():
        import macro_context
        return macro_context.macro_snapshot()

    def _health():
        import config
        return {
            "signals": _count_csv(config.SIGNALS_JOURNAL_FILE),
            "open_positions": _count_csv(config.OPEN_STATE_FILE),
            "finalized": _count_csv(config.FINAL_OUTCOMES_FILE),
        }

    def _positions():
        """Positions PAPER en cours (lecture seule du registre open_outcomes_state.csv).
        Renvoie une liste légère de dicts ; aucune valeur n'est calculée ici (prix
        live ajoutés ensuite par _enrich_positions). Défensif : [] si absent/illisible."""
        import config
        p = Path(config.OPEN_STATE_FILE)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if not p.exists():
            return []
        out = []
        with p.open("r", newline="", encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                sym = (row.get("symbol") or "").upper()
                side = (row.get("side") or "").upper()
                if not sym or not side:
                    continue
                out.append({
                    "symbol": sym, "side": side,
                    "entry": _num(row.get("entry")),
                    "stop_loss": _num(row.get("stop_loss")),
                    "take_profit": _num(row.get("take_profit")),
                    "last_close": _num(row.get("last_close")),
                    "outcome": row.get("outcome") or "",
                    "score": _num(row.get("score")),
                    "rsi": _num(row.get("rsi")),
                    "signal_timestamp": row.get("signal_timestamp") or "",
                })
        return out

    def _prices():
        """Derniers prix de TOUS les symboles en 1 requête mix (best-effort {})."""
        import bitget_market_data as bmd
        return bmd.mark_prices()

    def _symbols():
        # univers DYNAMIQUE (top-N liquide ∩ qualité), repli sur config.SYMBOLS
        try:
            import universe
            syms = list(universe.symbols())
            if syms and len(syms) >= 2:
                return syms
        except Exception:
            pass
        import config
        return config.SYMBOLS

    def _market():
        out = {}
        try:
            import sentiment_index
            out["fear_greed"] = sentiment_index.fetch_fear_greed()
        except Exception:
            out["fear_greed"] = None
        try:
            import defi_data
            out["defi"] = defi_data.fetch_chains(top=5)
        except Exception:
            out["defi"] = None
        return out

    def _candles():
        # source résiliente : Bitget (primaire) -> CoinGecko (repli), cachée
        import market_sources
        cs = market_sources.candles(symbol, tf, 60)
        if cs:
            return cs
        # repli ultime : ancien chemin direct (au cas où market_sources indisponible)
        import technicals
        raw = technicals.fetch_candles(symbol, tf, 60)
        return [[int(c["ts"] // 1000), c["open"], c["high"], c["low"], c["close"], c["volume"]] for c in raw]

    def _projection(candles, brain, liq):
        """Projection Black-Scholes : bandes ±1σ (mouvement attendu) + proba
        d'atteinte des clusters de liquidation. Pur côté maths, best-effort."""
        try:
            import black_scholes as bs
        except Exception:
            return {}
        cl = [c[4] for c in (candles or []) if len(c) >= 5]
        if len(cl) < 10:
            return {}
        S = cl[-1]
        sigma = bs.realized_vol(cl)            # σ par bougie (cohérent avec le TF affiché)
        horizon = 24                           # ~ 24 bougies devant
        try:
            em = bs.expected_move(S, sigma, horizon)
        except Exception:
            return {}
        regime = ((brain or {}).get("volatility") or {}).get("regime", "n/a")
        # enrichit chaque cluster de liquidation d'une proba d'atteinte (aimant)
        if sigma > 0 and isinstance(liq, dict):
            for c in (liq.get("clusters") or []):
                try:
                    K = S * (1.0 + (c.get("distance_pct", 0) or 0) / 100.0)
                    c["prob"] = round(bs.prob_touch(S, K, sigma, horizon), 3)
                except Exception:
                    pass
        # delta directionnel : P(prix final > / < prix actuel) à l'horizon (drift nul)
        try:
            p_up = bs.prob_above(S, S, sigma, horizon) if sigma > 0 else 0.5
        except Exception:
            p_up = 0.5
        return {
            "price": round(S, 2), "sigma": round(sigma, 6), "horizon": horizon,
            "exp_move": round(em, 2), "exp_move_pct": round(em / S * 100, 3) if S else 0.0,
            "low": round(S - em, 2), "high": round(S + em, 2), "regime": regime,
            "p_up": round(p_up, 4), "p_down": round(1.0 - p_up, 4),
        }

    def _book():
        import bitget_market_data as bmd
        ob = bmd.parse_orderbook(bmd.fetch_orderbook(symbol, limit=20))
        return {"bids": ob["bids"][:12], "asks": ob["asks"][:12]}

    def _future(brain):
        """Éventail d'issues futures (futurtester) : fan calibré sur l'actif +
        scénarios typés + régime macro Sentinel + stress-test du biais du cerveau.
        Best-effort, pur côté maths. Réutilise `brain` déjà lu (pas d'appel en plus)."""
        import futuretester as ft
        T = 0.25  # horizon ~3 mois, pertinent pour le trading
        fan = ft.from_market(symbol, T=T, n=8000)
        S0 = fan.get("S0", 100.0) if fan else 100.0
        scen = ft.run_all(S0, T=T, n=8000)
        scen_sum = {n: {"p5": s["p5_return_pct"], "median": s["median_return_pct"],
                        "p95": s["p95_return_pct"], "prob_up": s["prob_up"], "note": s["note"]}
                    for n, s in scen.items()}
        macro = {}
        try:
            import macro_sentinel as msx
            nc = msx.nowcast()
            macro = {"regime": nc.get("regime"), "confidence": nc.get("confidence"),
                     "stress": nc.get("stress"), "drivers": nc.get("drivers")}
        except Exception:
            pass
        bias = (brain or {}).get("bias", "NEUTRE")
        conv = (brain or {}).get("adjusted_conviction", (brain or {}).get("conviction", 0.0))
        stress = ft.stress_assessment(bias, conv, scen)
        esm_a = {}
        try:
            import esm
            esm_a = esm.analyze(symbol)
        except Exception:
            pass
        return {"horizon_years": T, "fan": fan, "scenarios": scen_sum,
                "macro": macro, "stress": stress, "esm": esm_a}

    def _brain():
        import swarm_brain
        return swarm_brain.peek(symbol)

    def _liq():
        import liquidations
        return liquidations.fetch_liquidations(symbol)

    def _accumulation():
        """État de l'accumulation BTC (LECTURE SEULE : lit les registres + l'opportunité
        courante via analyze, qui n'achète JAMAIS). Aucun ordre déclenché ici."""
        import accumulation_engine as ae
        out = {"autonomous_armed": _safe(ae._autonomous_live, False)}
        real = _safe(lambda: json.loads(
            (REPO_ROOT / "accumulation_real_ledger.json").read_text(encoding="utf-8")), {"buys": []})
        buys = (real or {}).get("buys", [])
        out["real_spent_usd"] = round(sum(float(b.get("amount_usdt", 0)) for b in buys), 2)
        out["real_n_buys"] = len(buys)
        out["paper"] = _safe(ae.load_ledger, {})
        a = _safe(lambda: ae.analyze("BTCUSDT"), {})        # analyze = lecture seule
        out["opportunity"] = a.get("score")
        out["dca_reco"] = a.get("amount_usd")
        # montant RÉEL prévu (sizing proportionnel §44) quand l'autonome est armé
        if out.get("autonomous_armed"):
            out["dca_real"] = _safe(lambda: ae.real_dca_amount(a.get("score")), None)
        out["rsi"] = a.get("rsi")
        out["fear_greed"] = a.get("fear_greed")
        out["premium_pct"] = a.get("premium_pct")           # premium Bitget vs médiane marché
        out["fair"] = a.get("fair")
        out["spot_free_usdt"] = _safe(lambda: __import__("spot_executor")._spot_free_usdt(), None)
        # réconciliation réelle (registre ↔ fills ↔ compte) : prix de revient RÉEL,
        # PnL latent, anomalies. Cache long (les fills bougent 1x/jour).
        out["reconcile"] = _cached("reconcile", 900,
                                   lambda: _safe(__import__("accum_reconcile").snapshot, None))
        return out

    def _mandate():
        import mandate
        return mandate.summary()

    def _edge():
        """Échelle d'edge ENRICHIE (§41) — voir edge_summary (pur, testé)."""
        import edge_ladder as el
        return edge_summary(el._load())

    def _onchain():
        """On-chain BTC (§40) : Hash Ribbons, congestion mempool, difficulté.
        Advisory LENT (observabilité seulement : rejeté comme entrée de sizing, §42)."""
        import onchain_btc as oc
        s = oc.snapshot()
        rb = s.get("ribbon") or {}
        return {"hashrate_ths": s.get("hashrate_ths"), "etat": oc.etat_ribbon(rb),
                "signal": rb.get("signal"), "congestion": s.get("congestion"),
                "frais_rapide": (s.get("frais") or {}).get("rapide"),
                "diff_pct": (s.get("difficulte") or {}).get("variation_pct")}

    def _flows():
        """Flux stablecoins (§40) : offre totale, momentum 7j/30j, signal dry-powder."""
        import stablecoin_flow as sf
        return sf.snapshot()

    def _vol_iv():
        """Vol implicite Deribit (§40) : DVOL, VRP = DVOL − RV, régime par devise."""
        import deribit_vol as dv
        return {"BTC": dv.snapshot("BTC"), "ETH": dv.snapshot("ETH")}

    def _futures_live():
        """Futures réel §45 (LECTURE SEULE) : préview de décision de la boucle auto,
        position, equity, stop journalier, PnL réalisé du bot — via futures_report."""
        import futures_report as fr
        s = fr.snapshot()
        b = s.get("boucle") or {}
        c = s.get("carry") or {}
        return {"armed": b.get("armed"), "consensus": b.get("consensus"),
                "position": b.get("position"), "positions": b.get("positions"),
                "symbol": b.get("symbol"), "funding": s.get("funding"),
                "decision": b.get("decision"),
                "throttle_pret": b.get("throttle_pret"),
                "equity": s.get("equity_usdt"), "stop": s.get("stop_journalier"),
                "stop_pct": s.get("stop_pct"), "fills_bot": s.get("fills_bot"),
                "caps": s.get("caps"), "events": s.get("events"),
                "carry": {"armed": c.get("armed"), "apr": c.get("apr_net_pct"),
                          "attrait": c.get("attrait"),
                          "couverture": c.get("couverture_usdt"),
                          "action": (c.get("decision") or {}).get("action")}}

    def _viz(symbol):
        """Données de VISUALISATION (lecture seule, best-effort) : courbes PnL/funding
        cumulés du bot (tous symboles §47), consensus de l'univers (ce que la boucle
        multi-symboles voit), palette synesthésique du symbole affiché (§50)."""
        out = {"pnl_serie": [], "funding_serie": [], "consensus_univers": [], "synesthesie": None}
        try:
            import futures_auto as fa
            import futures_report as fr
            events = fa._executor_events()
            debut = fr.premier_ordre_reel_ts(events)
            if debut:
                out["pnl_serie"] = fr.serie_pnl(fr.fetch_fills(), depuis_ts=debut)[-200:]
                out["funding_serie"] = fr.serie_funding(fr.fetch_bills(), depuis_ts=debut)[-200:]
            import futures_executor as fe
            import json as _json
            led = _json.loads(fe._ledger_path().read_text(encoding="utf-8"))
            out["equity_serie"] = [p for p in led.get("equity_intraday", [])
                                   if isinstance(p, list) and len(p) == 2][-200:]
            ents = fa._brain_entries()
            from config_utils import cfg as _cfg
            seuil = float(_cfg("FUTURES_AUTO_SEUIL_ENTREE", 0.35))
            cons = []
            for s in fa._universe():
                c = fa.consensus_frais(ents, symbol=s)
                cons.append({"s": s, "c": c})
            cons.sort(key=lambda r: -(abs(r["c"]) if r["c"] is not None else -1))
            out["consensus_univers"] = cons
            out["seuil"] = seuil
        except Exception:
            pass
        try:
            import market_sources as ms
            import savant_agent as sa
            closes = ms.closes(symbol, 80)
            if closes and len(closes) >= 30:
                syn = sa.synesthesie(closes)
                m, w = sa.motifs_ordinaux([float(c) for c in closes][-73:])
                freq = [0.0] * 6
                wt = sum(w) or 1e-12
                for mi, wi in zip(m, w):
                    freq[mi] += wi / wt
                syn["formes"] = [round(f, 4) for f in freq]
                out["synesthesie"] = syn
        except Exception:
            pass
        return out

    def _carry():
        """Cash-and-carry (§40, PAPER) : APR net par symbole, trié décroissant."""
        import carry_monitor as cm
        import config_utils as cu
        rows = [r for r in cm.evaluer() if r.get("apr_net_pct") is not None]
        rows.sort(key=lambda r: r["apr_net_pct"], reverse=True)
        return {"seuil_pct": cu.cfg("CARRY_SEUIL_APR_PCT", 5.0), "rows": rows[:6]}

    def _microstructure():
        """Edge microstructure accumulé (chemin 2) : n enregistrements + meilleure feature."""
        import microstructure as ms
        rep = ms.history_report()
        feats = rep.get("edge") or {}
        best = max(feats.values(), key=lambda m: abs(float(m.get("ic_t", 0) or 0)), default={})
        return {"n_records": rep.get("n_records", 0), "symbols": rep.get("symbols", []),
                "best_feature": best.get("feature"), "best_ic_t": best.get("ic_t"), "best_n": best.get("n")}

    def _market_timing():
        """Edge TEMPOREL market-timing (macro/sentiment) accumulé."""
        import market_timing as mt
        rep = mt.report(horizon=5)
        ed = rep.get("edge") or {}
        return {"n_records": rep.get("n_records", 0), "span_days": rep.get("span_days", 0),
                "macro_ic_t": (ed.get("macro") or {}).get("ic_t"),
                "sentiment_ic_t": (ed.get("sentiment") or {}).get("ic_t"),
                "n": (ed.get("macro") or {}).get("n", 0)}

    def _caps():
        """Statut des 3 couches de cap réel + tripwire dépense (lecture seule)."""
        import spot_executor as se
        breach, spent, promise = se.daily_spend_breach()
        return {"spent_today": spent, "promise": promise, "breach": bool(breach),
                "daily_eff": se._capped("ACCUM_REAL_MAX_DAILY_USDT", 5.0, se.ACCUM_ABS_MAX_DAILY_USDT),
                "per_buy_eff": se._capped("ACCUM_REAL_MAX_PER_BUY_USDT", 5.0, se.ACCUM_ABS_MAX_PER_BUY_USDT),
                "abs_daily": se.ACCUM_ABS_MAX_DAILY_USDT}

    def _microstructure_live():
        """Microstructure TEMPS RÉEL du collecteur (OFI, queue, trade-sign, spread, markout, toxicité)."""
        import microstructure as ms
        return ms.summary(symbol)

    def _system():
        """Santé du fleet systemd + collecteur + kill-switch (lecture seule, best-effort)."""
        out = {}
        try:
            import watchdog as wd
            st = wd.evaluate()
            out["loop"] = {"verdict": st.get("verdict"), "scan_age_min": st.get("age_min"),
                           "fresh": st.get("fresh")}
        except Exception:
            out["loop"] = {}
        svcs = {}
        try:
            import watchdog as wd
            for name in ("bitget-microstructure", "bitget-dashboard", "bitget-bot"):
                svcs[name.replace("bitget-", "")] = wd.service_active(name)
        except Exception:
            pass
        out["services"] = svcs
        try:
            import risk_manager as rm
            out["kill_switch"] = rm.kill_switch_active()
        except Exception:
            out["kill_switch"] = None
        try:
            import watchdog as wd
            out["micro_age_s"] = round(wd.microstructure_age("BTCUSDT"), 1) if wd.microstructure_age("BTCUSDT") is not None else None
        except Exception:
            out["micro_age_s"] = None
        return out

    # _stats recalcule sur TOUT le journal de signaux -> cache (evite le recalcul a chaque poll 5s)
    stats = _cached("stats", 30, lambda: _safe(_stats, {}))
    orderflow = _cached(f"of:{symbol}", 20, lambda: _safe(_orderflow, None))
    macro = _cached("macro", 300, lambda: _safe(_macro, None))
    market = _cached("market", 600, lambda: _safe(_market, {}))
    candles = _cached(f"cd:{symbol}:{tf}", 20, lambda: _safe(_candles, []))
    book = _cached(f"ob:{symbol}", 8, lambda: _safe(_book, {"bids": [], "asks": []}))
    # le cerveau réinterroge 13 agents (réseau) : cache plus long pour le polling.
    brain = _cached(f"br:{symbol}", 45, lambda: _safe(_brain, {}))
    liq = _cached(f"lq:{symbol}", 45, lambda: _safe(_liq, {}))
    health = _safe(_health, {})
    symbols = _cached("symbols", 300, lambda: _safe(_symbols, [symbol]))
    # positions PAPER en cours + prix live (1 requête tickers), enrichies à chaque appel
    positions_raw = _cached("positions", 15, lambda: _safe(_positions, []))
    prices = _cached("prices", 10, lambda: _safe(_prices, {}))
    positions = enrich_positions(positions_raw, prices)

    state = assemble_state(symbol, symbols, stats, orderflow, macro, health, market, candles, book, brain, liq, positions)
    state["tf"] = tf
    state["projection"] = _safe(lambda: _projection(candles, brain, liq), {})
    # futurtester : projection coûteuse (Monte Carlo) -> cache long, best-effort
    state["future"] = _cached(f"fut:{symbol}", 300, lambda: _safe(lambda: _future(brain), {}))
    # accumulation réelle + mandat + échelle d'edge (lecture seule, cachés)
    state["accumulation"] = _cached("accum", 60, lambda: _safe(_accumulation, {}))
    state["mandate"] = _cached("mandate", 60, lambda: _safe(_mandate, {}))
    state["edge_ladder"] = _cached("edge", 60, lambda: _safe(_edge, {}))
    # canaux d'edge accumulés (live, §37/§39) + statut des caps réels (lecture seule)
    state["microstructure"] = _cached("micro", 120, lambda: _safe(_microstructure, {}))
    state["market_timing"] = _cached("mtiming", 300, lambda: _safe(_market_timing, {}))
    state["caps"] = _cached("caps", 60, lambda: _safe(_caps, {}))
    state["micro_live"] = _cached(f"micL:{symbol}", 5, lambda: _safe(_microstructure_live, {}))
    state["system"] = _cached("system", 20, lambda: _safe(_system, {}))
    # sources orthogonales §40 (lentes par nature -> caches longs, best-effort)
    state["onchain"] = _cached("onchain", 3600, lambda: _safe(_onchain, {}))
    state["flows"] = _cached("flows", 3600, lambda: _safe(_flows, {}))
    state["vol_iv"] = _cached("voliv", 1800, lambda: _safe(_vol_iv, {}))
    state["carry"] = _cached("carry", 1800, lambda: _safe(_carry, {}))
    # futures réel §45 : préview de décision + réconciliation (lecture seule)
    state["futures_live"] = _cached("futlive", 60, lambda: _safe(_futures_live, {}))
    state["viz"] = _cached(f"viz:{symbol}", 90, lambda: _safe(lambda: _viz(symbol), {}))
    # mode HONNÊTE : futures/cerveau en paper, accumulation spot potentiellement RÉELLE
    armed = (state["accumulation"] or {}).get("autonomous_armed")
    fut_armed = (state.get("futures_live") or {}).get("armed")
    state["mode"] = (("RÉEL spot 2–5$/j" if armed else "paper accumulation")
                     + " · " + ("RÉEL futures borné §45" if fut_armed else "PAPER futures"))
    return state


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") in ("", "/index.html") or parsed.path == "/":
            try:
                html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            except OSError:
                self._send(500, "text/plain; charset=utf-8", b"index.html introuvable")
                return
            self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
        elif parsed.path == "/api/state":
            qs = parse_qs(parsed.query)
            symbol = (qs.get("symbol", [DEFAULT_SYMBOL])[0] or DEFAULT_SYMBOL).upper()
            tf = (qs.get("tf", ["5m"])[0] or "5m").lower()
            body = json.dumps(build_state(symbol, tf)).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif parsed.path == "/healthz":
            self._send(200, "text/plain; charset=utf-8", b"ok")
        elif parsed.path.startswith("/vendor/") and parsed.path.endswith(".js"):
            # sert les libs front vendorisées (ex. Lightweight Charts), sans traversée
            target = (STATIC_DIR / parsed.path.lstrip("/")).resolve()
            vendor = (STATIC_DIR / "vendor").resolve()
            if str(target).startswith(str(vendor) + os.sep) and target.is_file():
                self._send(200, "application/javascript; charset=utf-8", target.read_bytes())
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found")
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def log_message(self, *args):
        pass  # silencieux


def main():
    print(f"=== DASHBOARD (lecture seule) sur http://{HOST}:{PORT} ===")
    print("Mode: PAPER / DRY-RUN. Aucun ordre. VERDICT: SAFE")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
