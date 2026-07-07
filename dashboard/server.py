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


import threading
from concurrent.futures import ThreadPoolExecutor

_CACHE_LOCK = threading.Lock()


def _cached(key, ttl, producer):
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = producer()                       # HORS verrou : les producteurs sont lents (réseau)
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
    return value


def _prewarm(specs, workers=8):
    """Pré-calcule EN PARALLÈLE une liste de producteurs INDÉPENDANTS (key, ttl, thunk) pour
    peupler le cache : la construction de l'état passe d'une SOMME séquentielle de latences
    réseau à leur MAX. Best-effort — une clé qui échoue est simplement recalculée en séquence
    plus tard (aucune conséquence de correction). Ne prewarm QUE les producteurs sans
    dépendance sur d'autres (les dépendants restent séquentiels après)."""
    stale = [(k, ttl, thunk) for (k, ttl, thunk) in specs
             if not (lambda h: h and time.time() - h[0] < ttl)(_CACHE.get(k))]
    if not stale:
        return
    with ThreadPoolExecutor(max_workers=min(workers, len(stale))) as ex:
        for k, ttl, thunk in stale:
            ex.submit(_cached, k, ttl, thunk)


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


def radar_univers(entries, symbols, now=None, fenetre_s=21600, max_pts=48,
                  frais_s=900, deadband=0.1):
    """Radar de consensus de l'univers (PUR, testable) — la matière du panneau
    « MiroFish · Radar de consensus ». Pour chaque symbole, depuis brain_log :
      • c        : dernier consensus SI FRAIS (< frais_s, comme consensus_frais —
                   c'est exactement ce que la boucle §47 accepte de trader), sinon None ;
      • dernier  : dernière valeur même périmée (affichée estompée) + age_s ;
      • serie    : [(ts, consensus)] sur `fenetre_s` (6 h), downsamplée à max_pts ;
      • pour/contre : décompte des voix d'agents au-delà d'une bande morte ±deadband
                   (le vote à ~0 n'est pas une opinion), n_votes = voix journalisées.
    Tri : |consensus frais| décroissant, symboles muets en fin."""
    import time as _t
    now = _t.time() if now is None else now
    par = {}
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        s = str(e.get("symbol") or "").upper()
        ts, c = e.get("ts"), e.get("consensus")
        if (s and isinstance(ts, (int, float)) and isinstance(c, (int, float))
                and now - ts <= fenetre_s):
            par.setdefault(s, []).append(e)
    out = []
    for s in symbols or []:
        s = str(s).upper()
        rows = sorted(par.get(s) or [], key=lambda e: e["ts"])
        serie = [[int(e["ts"]), round(float(e["consensus"]), 3)] for e in rows]
        if len(serie) > max_pts:                 # downsample uniforme, garde le DERNIER point
            pas = len(serie) / float(max_pts)
            serie = [serie[int(i * pas)] for i in range(max_pts - 1)] + [serie[-1]]
        dern = rows[-1] if rows else None
        age = int(now - dern["ts"]) if dern else None
        votes = (dern or {}).get("votes") or {}
        nums = [v for v in votes.values() if isinstance(v, (int, float))]
        c_now = round(float(dern["consensus"]), 3) if dern else None
        out.append({"s": s,
                    "c": c_now if (age is not None and age <= frais_s) else None,
                    "dernier": c_now, "age_s": age, "serie": serie,
                    "pour": sum(1 for v in nums if v > deadband),
                    "contre": sum(1 for v in nums if v < -deadband),
                    "n_votes": len(nums)})
    out.sort(key=lambda r: -(abs(r["c"]) if r["c"] is not None else -1))
    return out


def chat_context(state):
    """Contexte COMPACT pour le chat du dashboard (PUR, testable) : l'essentiel de
    l'état déjà construit, SANS les blobs (bougies, carnet, viz, smc, future…) et
    sans aucun secret. Tout est en lecture seule — le chat ne peut RIEN exécuter."""
    st = state or {}
    brain = st.get("brain") or {}
    fu = st.get("futures_live") or {}
    rp = st.get("real_positions") or {}
    ac = st.get("accumulation") or {}
    meth = st.get("methodes") or {}
    agents = [{"agent": a.get("agent"), "vote": a.get("vote"), "conf": a.get("conf")}
              for a in (brain.get("agents") or [])[:17]]
    return {
        "horodatage_utc": st.get("timestamp"),
        "mode": st.get("mode"),
        "symbole_affiche": st.get("symbol"),
        "portefeuille_usdt": st.get("portfolio"),
        "cerveau": {"bias": brain.get("bias"), "consensus": brain.get("consensus"),
                    "conviction_ajustee": brain.get("adjusted_conviction",
                                                    brain.get("conviction")),
                    "cognition": brain.get("cognition"), "agents": agents},
        "boucle_futures": {"armee": fu.get("armed"), "consensus": fu.get("consensus"),
                           "decision": fu.get("decision"),
                           "throttle_pret": fu.get("throttle_pret"),
                           "positions": fu.get("positions"), "equity": fu.get("equity"),
                           "stop_journalier": fu.get("stop"), "caps": fu.get("caps"),
                           "pnl_bot": fu.get("fills_bot"), "carry": fu.get("carry")},
        "positions_reelles": {"spot": (rp.get("spot") or [])[:8],
                              "futures": rp.get("futures") or [],
                              "totaux": rp.get("totals")},
        "accumulation_btc": {k: ac.get(k) for k in
                             ("autonomous_armed", "real_spent_usd", "real_n_buys",
                              "opportunity", "dca_real", "premium_pct",
                              "spot_free_usdt") if k in ac},
        # méthodes : l'ESSENTIEL seulement (armé/position/halte) — les journaux bruts
        # gonfleraient le prompt (mesuré : 3.3k chars sur 7.4k au 07/07)
        "methodes_autonomes": {
            "alt_carry": {k: (meth.get("alt_carry") or {}).get(k)
                          for k in ("armed", "position")},
            "liquidite": {"armed": (meth.get("liquidite") or {}).get("armed")},
            "market_making": {k: (meth.get("market_making") or {}).get(k)
                              for k in ("armed", "symbols", "actives", "halted")},
            "lab_promus": [p.get("nom") for p in
                           ((meth.get("lab") or {}).get("promus") or [])[:8]],
        },
        "gardes": {"kill_switch": (st.get("system") or {}).get("kill_switch"),
                   "caps_accumulation_jour": st.get("caps"),
                   "murs": "futures 50/250 $ · levier ≤×5 · stop −5 % · retrait impossible"},
        "evenements_recents": (st.get("bord") or [])[:8],
        "rendez_vous": st.get("rdv") or [],
        "consensus_univers": ((st.get("viz") or {}).get("consensus_univers") or [])[:10],
    }


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


ALLOWED_TF = ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w")


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

    def _smc():
        """Analyse Smart Money Concepts (§64, LECTURE SEULE) : FVG, swings, liquidity
        sweeps, ChoCh valide, BPR, kill zones, Power of Three, SMT. Renvoie le setup
        PAPER indicatif + l'overlay graphique. Aucun ordre. Bougies dédiées (profondes)
        pour une meilleure structure ; paire SMT corrélée (BTC↔ETH) best-effort."""
        import smc
        import market_sources
        cs = market_sources.candles(symbol, tf, 150) or candles
        smt_map = {"BTCUSDT": "ETHUSDT", "ETHUSDT": "BTCUSDT"}
        cs_smt = None
        peer = smt_map.get(symbol)
        if peer:
            cs_smt = _safe(lambda: market_sources.candles(peer, tf, 150), None)
        return smc.analyze(cs, candles_smt=cs_smt)

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
                "executions": s.get("derniers_events"),
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
            # radar §47 enrichi : série 6 h + voix ± + fraîcheur (c = vue de la boucle)
            cons = radar_univers(ents, fa._universe())
            for r in cons:                       # minima contrat vs notional §75 (spec cachée)
                r["faisable"] = _safe(lambda s=r["s"]: bool(fa._taille_faisable(s, ents)), True)
            out["consensus_univers"] = cons
            out["seuil"] = seuil
        except Exception:
            pass
        try:
            # ORDRES RÉELS du symbole affiché -> marqueurs sur le graphique (§55)
            trades = []
            if symbol == "BTCUSDT":
                import spot_executor as se
                for b in (se._load_real().get("buys") or [])[-100:]:
                    trades.append({"ts": b.get("ts"), "type": "dca", "prix": b.get("price")})
            import futures_auto as fa2
            for e in (fa2._executor_events() or [])[-200:]:
                if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
                    continue
                o = e.get("order") or {}
                if str(o.get("symbol") or "BTCUSDT").upper() != symbol:
                    continue
                trades.append({"ts": e.get("ts"),
                               "type": "reduce" if o.get("reduce") else "open",
                               "side": o.get("side"), "prix": o.get("entry")})
            out["trades"] = sorted([x for x in trades if x.get("ts")],
                                   key=lambda x: x["ts"])[-120:]
        except Exception:
            pass
        try:
            # labo xs paper + percentile de funding + audit IC live (§60/§63)
            import xs_paper
            out["xs_paper"] = xs_paper.status()
        except Exception:
            pass
        try:
            import funding_history as fhy
            out["funding_pctl"] = fhy.percentile_courant("BTCUSDT")
        except Exception:
            pass
        try:
            import live_ic_audit as lia
            audit = _cached("audit_live", 900, lambda: lia.snapshot())
            out["audit_live"] = (audit or {}).get("agents", [])[:14]
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

    def _journal_de_bord():
        """Derniers ÉVÉNEMENTS notables, fusionnés (§63). Source UNIQUE partagée
        avec la commande Telegram /bord : journal_de_bord.evenements(). Lecture
        seule, [] best-effort."""
        try:
            import journal_de_bord as jdb
            return jdb.evenements(12)
        except Exception:
            return []

    def _rendez_vous():
        """Prochains RENDEZ-VOUS du système (§63) : [{txt, ts}] triés. Best-effort."""
        import time as _t
        now = _t.time()
        rv = []
        rv.append({"txt": "règlement funding", "ts": (int(now) // 28800 + 1) * 28800})
        try:                                       # fenêtre DCA (16-20h UTC, 1/jour)
            import spot_executor as se
            buys = se._load_real().get("buys") or []
            dernier = buys[-1]["ts"] if buys else 0
            possible = dernier + 24 * 3600
            jour = int(max(now, possible) // 86400) * 86400
            cible = jour + 16 * 3600
            while cible < max(now, possible):
                cible += 86400 if cible + 4 * 3600 < max(now, possible) else (
                    0 if cible + 4 * 3600 > max(now, possible) else 86400)
                if cible >= max(now, possible) or cible + 4 * 3600 > max(now, possible):
                    break
            rv.append({"txt": "fenêtre DCA (16-20h)", "ts": int(max(cible, possible))})
        except Exception:
            pass
        try:                                       # throttle directionnel
            import futures_auto as fa
            dernier = fa.dernier_ordre_auto_ts(fa._executor_events())
            if dernier:
                from config_utils import cfg as _c
                rv.append({"txt": "throttle directionnel libéré",
                           "ts": int(dernier + float(_c("FUTURES_AUTO_MIN_INTERVAL_H", 4)) * 3600)})
        except Exception:
            pass
        try:                                       # prochaine validation (6 h)
            import json as _json
            from pathlib import Path as _P
            rep = _json.loads((_P(REPO_ROOT) / "validation_report.json").read_text())
            rv.append({"txt": "validation (porte profonde)",
                       "ts": int(rep.get("generated_at", 0)) + 6 * 3600})
        except Exception:
            pass
        try:                                       # échéance macro (Kalshi)
            import kalshi_probe as kp
            pe = (kp.snapshot() or {}).get("prochain")
            if pe:
                rv.append({"txt": f"macro : {str(pe.get('titre'))[:28]}", "ts": pe["echeance_ts"]})
        except Exception:
            pass
        rv = [r for r in rv if r.get("ts") and r["ts"] > now]
        rv.sort(key=lambda x: x["ts"])
        return rv[:6]

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

    # PRÉ-CHAUFFE EN PARALLÈLE tous les producteurs INDÉPENDANTS (appels réseau/signés) :
    # la latence de build passe de leur SOMME (~22 s à froid) à leur MAX (~3-4 s). Les
    # producteurs DÉPENDANTS (projection/future/neural/kelly, qui lisent brain/smc/…) restent
    # séquentiels après. Clés/TTL identiques aux assignations ci-dessous (cache partagé).
    _prewarm([
        ("stats", 30, lambda: _safe(_stats, {})),
        (f"of:{symbol}", 20, lambda: _safe(_orderflow, None)),
        ("macro", 300, lambda: _safe(_macro, None)),
        ("market", 600, lambda: _safe(_market, {})),
        (f"cd:{symbol}:{tf}", 20, lambda: _safe(_candles, [])),
        (f"ob:{symbol}", 8, lambda: _safe(_book, {"bids": [], "asks": []})),
        (f"br:{symbol}", 45, lambda: _safe(_brain, {})),
        (f"lq:{symbol}", 45, lambda: _safe(_liq, {})),
        ("symbols", 300, lambda: _safe(_symbols, [symbol])),
        ("positions", 15, lambda: _safe(_positions, [])),
        ("prices", 10, lambda: _safe(_prices, {})),
        ("accum", 60, lambda: _safe(_accumulation, {})),
        ("mandate", 60, lambda: _safe(_mandate, {})),
        ("edge", 60, lambda: _safe(_edge, {})),
        ("micro", 120, lambda: _safe(_microstructure, {})),
        ("mtiming", 300, lambda: _safe(_market_timing, {})),
        ("caps", 60, lambda: _safe(_caps, {})),
        (f"micL:{symbol}", 5, lambda: _safe(_microstructure_live, {})),
        ("system", 20, lambda: _safe(_system, {})),
        ("onchain", 3600, lambda: _safe(_onchain, {})),
        ("flows", 3600, lambda: _safe(_flows, {})),
        ("voliv", 1800, lambda: _safe(_vol_iv, {})),
        ("carry", 1800, lambda: _safe(_carry, {})),
        ("futlive", 60, lambda: _safe(_futures_live, {})),
        (f"viz:{symbol}", 90, lambda: _safe(lambda: _viz(symbol), {})),
        (f"smc:{symbol}:{tf}", 60, lambda: _safe(_smc, {})),
        ("realpos", 10, lambda: _safe(lambda: __import__("real_positions").snapshot(), {})),
        ("tsurf", 20, lambda: _safe(lambda: __import__("trading_status").snapshot(), [])),
        ("portfolio", 120, lambda: _safe(
            lambda: __import__("real_positions").all_account_balance(), {})),
    ])

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
    # Smart Money Concepts §64 (lecture seule) : setup PAPER + overlay graphique
    state["smc"] = _cached(f"smc:{symbol}:{tf}", 60, lambda: _safe(_smc, {}))
    # Réseau neuronal de fusion §65 (lecture seule) : carte de connectivité + prédiction.
    # Réutilise le `brain` déjà calculé (pas de recalcul) ; fail-safe {} si torch/poids absents.
    state["neural"] = _cached(f"neural:{symbol}", 60,
                              lambda: _safe(lambda: __import__("neural_net").connectivity_map(
                                  symbol, brain=brain, smc=state.get("smc") or {}), {}))
    # Positions RÉELLES en cours (lecture seule) : spot · marge iso · marge cross · futures.
    # 4 GET signés best-effort -> cache 30 s (indépendant du symbole affiché).
    state["real_positions"] = _cached("realpos", 10,
                                      lambda: _safe(lambda: __import__("real_positions").snapshot(), {}))
    # Surfaces de trading bornées §67 : état armé/OFF + caps effectifs + dépensé du jour.
    # Lecture seule (lit les verrous LIVE via .env chargé) — aucun ordre. Défaut OFF.
    state["trading_surfaces"] = _cached("tsurf", 20,
                                        lambda: _safe(lambda: __import__("trading_status").snapshot(), []))
    # Portefeuille TOTAL (tous comptes : spot/futures/earn/bots/marge/funding) —
    # 1 GET signé de consultation, ventilation officielle. Lecture seule, cache 2 min.
    state["portfolio"] = _cached("portfolio", 120, lambda: _safe(
        lambda: __import__("real_positions").all_account_balance(), {}))

    # --- MÉTHODES AUTONOMES §76-83 (fichiers locaux uniquement — zéro appel réseau) ---
    def _tail_jsonl(path, n=1):
        try:
            lines = [l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
            return [json.loads(l) for l in lines[-n:]]
        except Exception:
            return []

    def _methodes():
        out = {}
        try:                                          # alt-carry : état + dernier cycle journalisé
            import alt_carry as ac
            st_ac = ac._etat()
            dern = _tail_jsonl(REPO_ROOT / ".alt_carry_journal.jsonl", 1)
            out["alt_carry"] = {"armed": ac.enabled(), "neg": ac._neg_on(),
                                "position": st_ac.get("position"),
                                "dernier": dern[0] if dern else None}
        except Exception:
            out["alt_carry"] = {}
        try:                                          # liquidité : dernier cycle journalisé
            import liquidity_manager as lm
            dern = _tail_jsonl(REPO_ROOT / ".liquidity_journal.jsonl", 1)
            out["liquidite"] = {"armed": lm.enabled(), "dernier": dern[0] if dern else None}
        except Exception:
            out["liquidite"] = {}
        try:                                          # market making §94 : dernier cycle + état
            import market_maker as mm
            dern = _tail_jsonl(REPO_ROOT / ".mm_journal.jsonl", 1)
            st_mm = json.loads((REPO_ROOT / ".mm_state.json").read_text(encoding="utf-8"))
            poches = st_mm.get("symbols") or {}
            actives = (sum(len(p.get("active") or []) for p in poches.values())
                       if poches else len(st_mm.get("active") or []))
            out["market_making"] = {"armed": mm.enabled(), "symbols": mm.symbols(),
                                    "dernier": dern[0] if dern else None,
                                    "actives": actives,
                                    "halted": bool(st_mm.get("halted"))}
        except Exception:
            out["market_making"] = {}
        try:                                          # labo : promotions récentes (strategies_out)
            outdir = REPO_ROOT / "strategies_out"
            mds = sorted(outdir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            promus, vus = [], set()
            for f in mds[:24]:
                nom = f.stem.rsplit("_", 2)[0]
                if nom not in vus:
                    vus.add(nom)
                    promus.append({"nom": nom, "ts": int(f.stat().st_mtime)})
            out["lab"] = {"promus": promus[:8],
                          "dernier_run": int(mds[0].stat().st_mtime) if mds else None}
        except Exception:
            out["lab"] = {}
        try:                                          # barre de promotion xs
            import xs_paper
            out["xs"] = xs_paper.promotion_status()
        except Exception:
            out["xs"] = {}
        try:                                          # tableau des promotions (§88)
            import promotion_board as pb
            out["board"] = pb.snapshot().get("items", [])
        except Exception:
            out["board"] = []
        return out
    state["methodes"] = _cached("methodes", 60, lambda: _safe(_methodes, {}))

    def _overlay_ic():
        """IC des voix opt-in (§77) + compte de votes parlés (même sous la barre des 50)."""
        try:
            import live_ic_audit as lia
            snap = lia.overlay_snapshot(3600)
            comptes = {}
            for e in lia.charger_entrees(lia.OVERLAY, max_lignes=50_000):
                for k in (e.get("votes") or {}):
                    comptes[k] = comptes.get(k, 0) + 1
            return {"agents": snap.get("agents", []), "comptes": comptes}
        except Exception:
            return {}
    state["overlay_ic"] = _cached("overlay_ic", 300, lambda: _safe(_overlay_ic, {}))

    # Critère de Kelly (advisory, lecture seule) : W/R mesurés -> fraction bornée + taille
    # recommandée/surface. Edge négatif -> 0. Aucun ordre.
    # capital & W/R RÉUTILISÉS de l'état déjà calculé (real_positions + futures_live + stats)
    # -> kelly ne re-fetch RIEN (coût ~4 s -> ~0). Fail-safe si champs absents.
    _rp = (state.get("real_positions") or {}).get("totals") or {}
    _cap = (_rp.get("spot_usdt") or 0.0) + ((state.get("futures_live") or {}).get("equity") or 0.0)
    _wr = state.get("stats") or {}
    _W = (_wr.get("win_rate") / 100.0) if _wr.get("win_rate") is not None else None
    state["kelly"] = _cached("kelly", 60, lambda: _safe(lambda: __import__("kelly").snapshot(
        {s.get("surface"): s.get("per_op") for s in (state.get("trading_surfaces") or [])
         if s.get("surface") in ("spot", "margin")} or None,
        capital=(_cap or None), W=_W, R=_wr.get("tp_sl_ratio")), {}))
    state["bord"] = _cached("bord", 60, lambda: _safe(_journal_de_bord, []))
    state["rdv"] = _cached("rdv", 120, lambda: _safe(_rendez_vous, []))
    try:
        import json as _json
        state["hitrates"] = _cached("hitrates", 120, lambda: _safe(
            lambda: _json.loads((REPO_ROOT / "brain_hitrates.json").read_text()), {}))
    except Exception:
        pass
    # mode HONNÊTE : futures/cerveau en paper, accumulation spot potentiellement RÉELLE
    armed = (state["accumulation"] or {}).get("autonomous_armed")
    fut_armed = (state.get("futures_live") or {}).get("armed")
    state["mode"] = (("RÉEL spot 2–5$/j" if armed else "paper accumulation")
                     + " · " + ("RÉEL futures borné §45" if fut_armed else "PAPER futures"))
    return state


# --------------------------------------------------------------------------- #
#  Modèle INCRÉMENTAL : delta versionné (n'envoyer que les clés qui ont changé) #
# --------------------------------------------------------------------------- #
_VERSIONS = {}          # "symbol:tf" -> {clé: [version, hash]}
_GLOBAL_V = [0]         # compteur de version MONOTONE global
_VER_LOCK = threading.Lock()


def _hash_val(v):
    """Empreinte stable d'une valeur d'état (pour détecter un changement). PUR."""
    import hashlib
    return hashlib.md5(json.dumps(v, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


def build_delta(symbol, tf, since):
    """État INCRÉMENTAL. Construit l'état complet (rapide : cache chaud ~0.04 s), verse une
    version MONOTONE à chaque clé qui change, et renvoie :
      • FULL {v, full:true, state}       si `since` absent / invalide / postérieur au serveur
                                          (client neuf, changement de symbole, redémarrage serveur) ;
      • DELTA {v, full:false, changed}   sinon — uniquement les clés de version > `since`.
    Stateless & multi-clients : les versions vivent côté serveur par symbole:tf, le client
    ne porte qu'un curseur entier `since`."""
    state = build_state(symbol, tf)
    scope = f"{symbol}:{tf}"
    with _VER_LOCK:
        vers = _VERSIONS.setdefault(scope, {})
        for k, v in state.items():
            h = _hash_val(v)
            rec = vers.get(k)
            if not rec or rec[1] != h:
                _GLOBAL_V[0] += 1
                vers[k] = [_GLOBAL_V[0], h]
        cur = _GLOBAL_V[0]
        # clés du scope courant disparues de l'état (rare : clés stables) -> à retirer côté client
        removed = [k for k in vers if k not in state]
        for k in removed:
            vers.pop(k, None)
        if since is None or since < 0 or since > cur:
            return {"v": cur, "full": True, "state": state}
        changed = {k: state[k] for k, rec in vers.items() if rec[0] > since and k in state}
        return {"v": cur, "full": False, "changed": changed, "removed": removed}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass                    # client parti en cours de réponse (normal, pas une erreur)

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
            # modèle INCRÉMENTAL : `since` = curseur de version du client (absent -> FULL,
            # rétro-compatible). Renvoie soit l'état complet, soit uniquement les clés changées.
            since_raw = qs.get("since", [None])[0]
            try:
                since = int(since_raw) if since_raw not in (None, "") else None
            except (TypeError, ValueError):
                since = None
            body = json.dumps(build_delta(symbol, tf, since)).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif parsed.path == "/api/stream":
            # PUSH temps réel (Server-Sent Events) : une connexion persistante par client
            # (thread dédié via ThreadingHTTPServer). On envoie un FULL puis des DELTAS à
            # cadence fixe ; à la déconnexion l'écriture lève -> le thread se termine.
            qs = parse_qs(parsed.query)
            symbol = (qs.get("symbol", [DEFAULT_SYMBOL])[0] or DEFAULT_SYMBOL).upper()
            tf = (qs.get("tf", ["5m"])[0] or "5m").lower()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")     # pas de buffering (nginx éventuel)
                self.end_headers()
                interval = float(os.getenv("DASH_SSE_INTERVAL", "2"))
                since = None
                while True:
                    payload = build_delta(symbol, tf, since)
                    since = payload["v"]
                    self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(interval)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return                                          # client déconnecté (normal)
            except Exception:
                return
        elif parsed.path == "/api/bitget":
            # Explorateur API Bitget (LECTURE SEULE, sections whitelistées) :
            # sans ?sec= -> liste des sections ; avec -> données de la section (cache 30 s).
            qs = parse_qs(parsed.query)
            sec = (qs.get("sec", [""])[0] or "").strip()
            symbol = (qs.get("symbol", [DEFAULT_SYMBOL])[0] or DEFAULT_SYMBOL).upper()
            import bitget_explorer as bx
            if not sec:
                payload = {"sections": _safe(bx.sections, [])}
            else:
                payload = _cached(f"bx:{sec}:{symbol}", 30,
                                  lambda: _safe(lambda: bx.fetch(sec, symbol),
                                                {"ok": False, "erreur": "indisponible"}))
            self._send(200, "application/json; charset=utf-8",
                       json.dumps(payload, default=str).encode("utf-8"))
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

    def do_POST(self):
        # /api/chat : questions en langage naturel sur l'état du bot. LECTURE SEULE —
        # le LLM reçoit un contexte compact (chat_context) et rend du texte ; il ne
        # peut déclencher AUCUNE action. Fail-safe : toute erreur -> JSON lisible.
        parsed = urlparse(self.path)
        if parsed.path != "/api/chat":
            self._send(404, "text/plain; charset=utf-8", b"not found")
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 65536)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            self._send(400, "application/json; charset=utf-8",
                       b'{"ok": false, "erreur": "corps JSON illisible"}')
            return
        q = str(body.get("q") or "").strip()
        if not q:
            self._send(400, "application/json; charset=utf-8",
                       b'{"ok": false, "erreur": "question vide"}')
            return
        symbol = str(body.get("symbol") or DEFAULT_SYMBOL).upper()
        backend = str(body.get("backend") or "local")
        history = body.get("history") if isinstance(body.get("history"), list) else []

        def _reponse():
            import dash_chat
            ctx = chat_context(build_state(symbol))     # cache chaud : ~0.05 s
            return dash_chat.repondre(q[:2000], ctx, backend=backend, history=history)
        res = _safe(_reponse, {"ok": False, "erreur": "chat indisponible (erreur interne)"})
        self._send(200, "application/json; charset=utf-8",
                   json.dumps(res, default=str).encode("utf-8"))

    def log_message(self, *args):
        pass  # silencieux


def main():
    # Charge le .env (gitignored) : le service systemd bitget-dashboard n'a pas
    # d'EnvironmentFile, donc sans ceci les leviers .env (LLM_AGENT_ENABLED,
    # NN_AGENT_ENABLED) ne seraient pas vus -> le dashboard afficherait les voix
    # opt-in OFF alors qu'elles sont armées en prod. Best-effort, lecture seule.
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
    except Exception:
        pass
    print(f"=== DASHBOARD (lecture seule) sur http://{HOST}:{PORT} ===")
    print("Mode: PAPER / DRY-RUN. Aucun ordre. VERDICT: SAFE")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    # §93 : écoute AUSSI sur l'IP Tailscale si présente (accès smartphone via le
    # tailnet privé WireGuard — l'IP 100.64/10 n'est PAS routable depuis Internet ;
    # l'interface publique du VPS reste fermée, on ne bind JAMAIS 0.0.0.0).
    extra = None
    try:
        import subprocess
        ts_ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True,
                               text=True, timeout=5).stdout.strip().splitlines()
        ts_ip = ts_ip[0].strip() if ts_ip else ""
        if ts_ip.startswith("100.") and ts_ip != HOST:
            import threading
            extra = ThreadingHTTPServer((ts_ip, PORT), Handler)
            threading.Thread(target=extra.serve_forever, daemon=True).start()
            print(f"Dashboard aussi sur le tailnet : http://{ts_ip}:{PORT}")
    except Exception:
        extra = None                                   # pas de tailscale -> localhost seul
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du dashboard.")
    finally:
        server.server_close()
        if extra is not None:
            extra.server_close()


if __name__ == "__main__":
    main()
